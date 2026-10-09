"""Production : découpage en segments, synthèse avec cache, contrôle qualité et assemblage des chapitres."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from .. import paths
from ..config import settings
from . import asr, audio, engines, project_io
from .emotions import apply_emotion
from .exporter import credits_text
from .models import Chapter, Project, VoiceProfile
from .textproc import NormalizeOptions, chunk_text, normalize_for_speech, parse_script
from .voices import VoiceLibrary

log = logging.getLogger(__name__)

RENDER_VERSION = 3  # à incrémenter si le post-traitement change (invalide le cache)
SR = audio.DEFAULT_SR
NEURAL_ENGINES = {"xtts", "chatterbox", "kokoro", "fastclone"}
RETRY_ENGINES = {"xtts", "chatterbox", "fastclone", "kokoro"}


class RenderError(RuntimeError):
    pass


@dataclass
class Segment:
    index: int
    text: str  # texte normalisé envoyé au moteur
    display: str  # texte d'origine (affichage)
    voice_id: str
    pause_after_ms: int
    kind: str = "para"
    key: str = ""
    paragraph: int = 0
    emotion: str = ""


@dataclass
class RenderChapter:
    id: str
    title: str
    kind: str = "chapter"  # opening | chapter | closing
    segments: list[Segment] = field(default_factory=list)
    head_ms: int = 1000
    tail_ms: int = 3000
    warnings: list[str] = field(default_factory=list)

    @property
    def plan_hash(self) -> str:
        h = hashlib.sha1()
        h.update(f"{self.head_ms}|{self.tail_ms}|{RENDER_VERSION}".encode())
        for s in self.segments:
            h.update(f"{s.key}|{s.pause_after_ms};".encode())
        return h.hexdigest()

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.segments)


# =======================================================================================
# Plan de rendu
# =======================================================================================
def _voice_fingerprint(voice: VoiceProfile) -> list:
    refs = []
    for p in voice.reference_paths():
        try:
            st = p.stat()
            refs.append([p.name, st.st_size, int(st.st_mtime)])
        except OSError:
            refs.append([p.name, 0, 0])
    return [voice.engine, voice.engine_voice, refs, sorted((voice.params or {}).items())]


def segment_key(text: str, voice: VoiceProfile, language: str, speed: float, trim: bool, emotion: str = "") -> str:
    parts = [RENDER_VERSION, text, _voice_fingerprint(voice), language, round(speed, 3), trim]
    if emotion:
        parts.append(emotion)
    payload = json.dumps(parts, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class VoiceResolver:
    def __init__(self, project: Project, library: VoiceLibrary):
        self.project = project
        self.library = library
        self.warnings: list[str] = []

    def narrator(self, chapter: Chapter | None = None) -> VoiceProfile:
        candidates = [chapter.voice_id if chapter else "", self.project.narrator_voice_id]
        candidates.append(settings().get("default_voice_id", ""))
        for vid in candidates:
            v = self.library.get(vid)
            if v is not None:
                return v
        voices = self.library.all()
        if not voices:
            raise RenderError("Aucune voix disponible : créez ou ajoutez une voix dans la page Voix.")
        return voices[0]

    def resolve(self, key: str | None, chapter: Chapter | None) -> VoiceProfile:
        narrator = self.narrator(chapter)
        if key is None:
            return narrator
        if key == "__dialogue__":
            return self.library.get(self.project.production.dialogue_voice_id) or narrator
        for name, vid in self.project.cast.items():
            if name.strip().lower() == key.strip().lower():
                v = self.library.get(vid)
                if v is not None:
                    return v
        msg = f"Personnage « {key} » sans voix attribuée : la voix du narrateur sera utilisée."
        if msg not in self.warnings:
            self.warnings.append(msg)
        return narrator


def _engine_limits(voice: VoiceProfile) -> tuple[int, int]:
    eng = engines.get_engine(voice.engine)
    if eng is None:
        return 300, 0
    return eng.info.max_chars, eng.info.min_chars


def build_chapter_plan(project: Project, chapter: Chapter, library: VoiceLibrary, kind: str = "chapter",
                       resolver: VoiceResolver | None = None) -> RenderChapter:
    prod = project.production
    lang = project.metadata.language or "fr"
    opts = NormalizeOptions(language=lang, numbers=prod.normalize_numbers, abbreviations=prod.expand_abbreviations)
    resolver = resolver or VoiceResolver(project, library)
    rc = RenderChapter(id=chapter.id, title=chapter.title, kind=kind, head_ms=prod.chapter_head_ms,
                       tail_ms=prod.chapter_tail_ms)
    segs: list[Segment] = []
    paragraph = 0

    def add_text(raw: str, voice: VoiceProfile, kind_: str, end_pause: int, emotion: str = ""):
        nonlocal paragraph
        spoken = normalize_for_speech(raw, opts, project.lexicon)
        if not spoken.strip() or not any(ch.isalnum() for ch in spoken):
            if segs:
                segs[-1].pause_after_ms += end_pause
            return
        max_chars, min_chars = _engine_limits(voice)
        chunks = chunk_text(spoken, max_chars, min_chars)
        for i, c in enumerate(chunks):
            last = i == len(chunks) - 1
            segs.append(Segment(
                index=len(segs), text=c, display=raw if len(chunks) == 1 else c, voice_id=voice.id,
                pause_after_ms=end_pause if last else prod.pause_sentence_ms, kind=kind_,
                key=segment_key(c, voice, lang, prod.speed, prod.trim_silence, emotion), paragraph=paragraph,
                emotion=emotion,
            ))
        paragraph += 1

    announce = chapter.announce_title if chapter.announce_title is not None else prod.announce_chapter_titles
    if kind == "chapter" and announce and chapter.title.strip():
        add_text(chapter.title.strip().rstrip(".") + ".", resolver.narrator(chapter), "title", prod.pause_heading_ms)

    for item in parse_script(chapter.text, prod.detect_dialogues):
        if item.kind == "pause":
            if segs:
                segs[-1].pause_after_ms += item.pause_ms
            else:
                rc.head_ms += item.pause_ms
        elif item.kind == "heading":
            add_text(item.text.rstrip(".") + ".", resolver.narrator(chapter), "heading", prod.pause_heading_ms)
        else:
            voice = resolver.resolve(item.voice_key, chapter)
            add_text(item.text, voice, "para", prod.pause_paragraph_ms, item.emotion)
    if segs:
        segs[-1].pause_after_ms = 0
    rc.segments = segs
    rc.warnings = list(resolver.warnings)
    return rc


def build_plan(project: Project, library: VoiceLibrary, chapter_ids: list[str] | None = None,
               include_credits: bool | None = None) -> list[RenderChapter]:
    resolver = VoiceResolver(project, library)
    plan: list[RenderChapter] = []
    credits = project.export.include_credits if include_credits is None else include_credits
    wanted = set(chapter_ids) if chapter_ids else None
    if credits and (wanted is None or "__opening__" in wanted):
        text = credits_text(project.export.opening_credits, project.metadata)
        plan.append(build_chapter_plan(project, Chapter(id="__opening__", title="Crédits d'ouverture", text=text),
                                       library, "opening", resolver))
    for ch in project.included_chapters():
        if wanted is None or ch.id in wanted:
            plan.append(build_chapter_plan(project, ch, library, "chapter", resolver))
    if credits and (wanted is None or "__closing__" in wanted):
        text = credits_text(project.export.closing_credits, project.metadata)
        plan.append(build_chapter_plan(project, Chapter(id="__closing__", title="Crédits de fin", text=text),
                                       library, "closing", resolver))
    return plan


# =======================================================================================
# Cache
# =======================================================================================
def cache_path(project: Project, key: str) -> Path:
    d = project_io.cache_dir(project) / key[:2]
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.flac"


def qc_path(project: Project, key: str) -> Path:
    """Résultat de la relecture automatique d'un passage (texte entendu, taux d'erreur)."""
    return cache_path(project, key).with_suffix(".qc.json")


def read_qc(project: Project, key: str) -> dict:
    try:
        return json.loads(qc_path(project, key).read_text(encoding="utf-8"))
    except Exception:
        return {}


def chapter_output(project: Project, chapter_id: str) -> Path:
    return project_io.renders_dir(project) / f"{chapter_id}.flac"


def chapter_manifest(project: Project, chapter_id: str) -> Path:
    return project_io.renders_dir(project) / f"{chapter_id}.json"


def chapter_is_current(project: Project, rc: RenderChapter) -> bool:
    out = chapter_output(project, rc.id)
    man = chapter_manifest(project, rc.id)
    if not (out.exists() and man.exists()):
        return False
    try:
        return json.loads(man.read_text(encoding="utf-8")).get("plan_hash") == rc.plan_hash
    except Exception:
        return False


def chapter_progress(project: Project, rc: RenderChapter) -> tuple[int, int]:
    done = sum(1 for s in rc.segments if cache_path(project, s.key).exists())
    return done, len(rc.segments)


def segment_timings(project: Project, rc: RenderChapter) -> list[tuple[float, float]]:
    """Positions (début, fin) de chaque segment dans le rendu du chapitre."""
    man = chapter_manifest(project, rc.id)
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
        return [tuple(t) for t in data.get("timings", [])]
    except Exception:
        return []


# =======================================================================================
# Moteur de production
# =======================================================================================
@dataclass
class RenderCallbacks:
    progress: Callable[[int, int, str], None] = lambda done, total, msg: None
    segment: Callable[[str, int, str], None] = lambda chapter_id, index, status: None
    chapter: Callable[[str, str], None] = lambda chapter_id, status: None
    log: Callable[[str], None] = lambda msg: None
    eta: Callable[[float], None] = lambda seconds: None


@dataclass
class RenderReport:
    rendered_chapters: list[str] = field(default_factory=list)
    failed_segments: list[tuple[str, int, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cancelled: bool = False
    elapsed: float = 0.0


def expected_duration(text: str, speed: float = 1.0) -> float:
    return len(text) / 14.5 / max(0.3, speed)


class Renderer:
    def __init__(self, project: Project, library: VoiceLibrary, callbacks: RenderCallbacks | None = None):
        self.project = project
        self.library = library
        self.cb = callbacks or RenderCallbacks()
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()  # « set » = en pause
        self._stats_lock = threading.Lock()
        self._chars_done = 0
        self._time_spent = 0.0

    # -- contrôle ----------------------------------------------------------------------
    def cancel(self) -> None:
        self.cancel_event.set()
        self.pause_event.clear()

    def _wait_if_paused(self) -> None:
        while self.pause_event.is_set() and not self.cancel_event.is_set():
            time.sleep(0.2)

    # -- synthèse d'un segment ---------------------------------------------------------
    def _voice(self, voice_id: str) -> VoiceProfile:
        v = self.library.get(voice_id)
        if v is None:
            raise RenderError(f"Voix introuvable ({voice_id}).")
        return v

    def synth_segment(self, seg: Segment, seed: int | None = None, force: bool = False) -> Path:
        """Synthétise un segment (ou le reprend du cache) ; renvoie le fichier FLAC 44,1 kHz."""
        target = cache_path(self.project, seg.key)
        if target.exists() and not force:
            return target
        voice = self._voice(seg.voice_id)
        engine = engines.get_engine(voice.engine)
        if engine is None:
            raise RenderError(f"Moteur inconnu : {voice.engine}")
        voice, emo_speed, emo_gain = apply_emotion(voice, seg.emotion)
        lang = self.project.metadata.language or voice.language or "fr"
        speed = self.project.production.speed * emo_speed
        base_seed = int(seg.key[:8], 16) if seed is None else seed
        best: tuple[float, np.ndarray, dict] | None = None
        attempts = 3 if voice.engine in RETRY_ENGINES else 1
        check_asr = (self.project.production.asr_check and voice.engine in RETRY_ENGINES
                     and len(seg.text.split()) >= 3 and asr.asr_ready())
        last_error: Exception | None = None
        for attempt in range(attempts):
            if self.cancel_event.is_set():
                raise RenderError("Annulé")
            with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
                raw_target = Path(td) / "raw.wav"
                t0 = time.time()
                try:
                    written = engine.synthesize(seg.text, voice, raw_target, lang, speed,
                                                base_seed + attempt * 7919)
                except Exception as exc:
                    last_error = exc
                    log.warning("Échec segment %s (essai %d) : %s", seg.index, attempt + 1, exc)
                    if isinstance(exc, engines.EngineError) and "pas installé" in str(exc):
                        raise
                    time.sleep(0.5)
                    continue
                data, sr = audio.read_audio(written)
                elapsed = time.time() - t0
                qc: dict = {}
                if check_asr:
                    try:
                        heard = engines.get_tool("whisper").transcribe(written, lang)
                        qc = {"heard": heard, "wer": round(asr.word_error(seg.text, heard, lang), 3)}
                    except Exception as exc:  # la relecture ne doit jamais bloquer la production
                        log.warning("Relecture impossible : %s", exc)
            data = audio.resample(data, sr, SR)
            data = audio.remove_dc(data)
            if self.project.production.trim_silence:
                trimmed = audio.trim_silence(data, SR, -45.0, pad_ms=40)
                if trimmed.size > SR * 0.1:
                    data = trimmed
            if emo_gain:
                data = (data * audio.db_to_lin(emo_gain)).astype(np.float32)
            data = audio.apply_fades(data, SR, 5, 20)
            dur = len(data) / SR
            exp = expected_duration(seg.text, speed)
            rms = audio.lin_to_db(float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))) if data.size else -120
            ratio = dur / max(exp, 0.3)
            score = abs(np.log(max(ratio, 1e-3)))
            if rms < -55 - abs(emo_gain):
                score += 10
            wer = qc.get("wer", 0.0)
            score += 4 * wer
            with self._stats_lock:
                self._chars_done += len(seg.text)
                self._time_spent += elapsed
            if best is None or score < best[0]:
                best = (score, data, qc)
            reasons = []
            if len(seg.text) > 25 and (ratio > 2.3 or ratio < 0.35):
                reasons.append(f"durée {dur:.1f} s pour {exp:.1f} s attendues")
            if rms < -55 - abs(emo_gain):
                reasons.append("passage presque silencieux")
            if wer > self.project.production.asr_threshold:
                reasons.append(f"{int(wer * 100)} % de mots différents du texte")
            if not reasons:
                break
            if attempt + 1 < attempts:
                self.cb.log(f"Contrôle qualité : passage {seg.index + 1} à refaire ({', '.join(reasons)}), "
                            "nouvel essai…")
        if best is None:
            raise RenderError(str(last_error) if last_error else "Échec de la synthèse")
        audio.write_audio(target, best[1], SR, subtype="PCM_24")
        qc_file = qc_path(self.project, seg.key)
        if best[2]:
            qc_file.write_text(json.dumps(best[2], ensure_ascii=False), encoding="utf-8")
            if best[2].get("wer", 0) > self.project.production.asr_threshold:
                self.cb.log(f"⚠ Passage {seg.index + 1} à vérifier à l'écoute : la relecture a entendu "
                            f"« {best[2].get('heard', '')} »")
        elif qc_file.exists():
            qc_file.unlink()
        return target

    def regenerate_segment(self, seg: Segment) -> Path:
        """Nouvelle prise d'un passage (graine aléatoire), remplace celle du cache."""
        return self.synth_segment(seg, seed=random.randint(1, 2 ** 31 - 1), force=True)

    def eta_seconds(self, remaining_chars: int) -> float:
        with self._stats_lock:
            if self._chars_done < 50 or self._time_spent <= 0:
                return -1.0
            return remaining_chars * self._time_spent / self._chars_done

    # -- assemblage --------------------------------------------------------------------
    def assemble(self, rc: RenderChapter) -> Path:
        out = chapter_output(self.project, rc.id)
        tmp = out.with_suffix(".tmp.flac")
        timings: list[tuple[float, float]] = []
        pos = 0
        with sf.SoundFile(str(tmp), "w", samplerate=SR, channels=1, subtype="PCM_24", format="FLAC") as fh:
            head = audio.silence(rc.head_ms, SR)
            fh.write(head)
            pos += len(head)
            for seg in rc.segments:
                data, sr = audio.read_audio(cache_path(self.project, seg.key))
                if sr != SR:
                    data = audio.resample(data, sr, SR)
                timings.append((pos / SR, (pos + len(data)) / SR))
                fh.write(data)
                pos += len(data)
                gap = audio.silence(seg.pause_after_ms, SR)
                fh.write(gap)
                pos += len(gap)
            tail = audio.silence(max(rc.tail_ms, 500), SR)
            fh.write(tail)
            pos += len(tail)
        tmp.replace(out)
        chapter_manifest(self.project, rc.id).write_text(json.dumps({
            "plan_hash": rc.plan_hash, "title": rc.title, "kind": rc.kind, "duration": pos / SR,
            "timings": timings, "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False), encoding="utf-8")
        return out

    # -- production complète -----------------------------------------------------------
    def render(self, plan: list[RenderChapter]) -> RenderReport:
        from .power import keep_awake

        with keep_awake():
            return self._render(plan)

    def _render(self, plan: list[RenderChapter]) -> RenderReport:
        report = RenderReport()
        t_start = time.time()
        for rc in plan:
            report.warnings.extend(w for w in rc.warnings if w not in report.warnings)
        total = sum(len(rc.segments) for rc in plan)
        done = sum(chapter_progress(self.project, rc)[0] for rc in plan)
        remaining_chars = sum(len(s.text) for rc in plan for s in rc.segments
                              if not cache_path(self.project, s.key).exists())
        self.cb.progress(done, total, "Préparation…")

        # Préchargement des moteurs neuronaux utilisés (téléchargement du modèle au premier lancement)
        used = {self._voice(s.voice_id).engine for rc in plan for s in rc.segments if self.library.get(s.voice_id)}
        for eng_id in sorted(used):
            eng = engines.get_engine(eng_id)
            if eng is not None and eng_id in NEURAL_ENGINES:
                self.cb.log(f"Démarrage du moteur {eng.info.name}…")
                eng.warmup()

        for rc in plan:
            if self.cancel_event.is_set():
                break
            if chapter_is_current(self.project, rc):
                self.cb.chapter(rc.id, "done")
                continue
            self.cb.chapter(rc.id, "running")
            todo = [s for s in rc.segments if not cache_path(self.project, s.key).exists()]
            failed = False
            groups: dict[int, list[Segment]] = {}
            for s in todo:
                eng = engines.get_engine(self._voice(s.voice_id).engine)
                workers = eng.info.max_workers if eng else 1
                if eng is not None and eng.info.id == "edge":
                    workers = int(settings().get("edge_concurrency", 4) or 1)
                groups.setdefault(max(1, workers), []).append(s)

            def run_one(seg: Segment):
                self._wait_if_paused()
                if self.cancel_event.is_set():
                    return seg, "cancelled", None
                self.cb.segment(rc.id, seg.index, "running")
                try:
                    self.synth_segment(seg)
                    return seg, "done", None
                except Exception as exc:  # noqa: BLE001
                    return seg, "error", exc

            for workers, segs in groups.items():
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(run_one, s) for s in segs]
                    for fut in as_completed(futures):
                        seg, status, exc = fut.result()
                        if status == "cancelled":
                            continue
                        self.cb.segment(rc.id, seg.index, status)
                        if status == "done":
                            done += 1
                            remaining_chars -= len(seg.text)
                            self.cb.eta(self.eta_seconds(max(0, remaining_chars)))
                        else:
                            failed = True
                            report.failed_segments.append((rc.id, seg.index, str(exc)))
                            self.cb.log(f"Erreur sur « {rc.title} », passage {seg.index + 1} : {exc}")
                        self.cb.progress(done, total, f"{rc.title} — passage {seg.index + 1}/{len(rc.segments)}")
                        if isinstance(exc, engines.EngineError) and "pas installé" in str(exc):
                            self.cancel_event.set()
            if self.cancel_event.is_set():
                self.cb.chapter(rc.id, "pending")
                break
            if failed:
                self.cb.chapter(rc.id, "error")
                continue
            self.cb.progress(done, total, f"Assemblage : {rc.title}")
            try:
                self.assemble(rc)
                report.rendered_chapters.append(rc.id)
                self.cb.chapter(rc.id, "done")
            except Exception as exc:  # noqa: BLE001
                log.exception("Assemblage impossible")
                report.failed_segments.append((rc.id, -1, str(exc)))
                self.cb.chapter(rc.id, "error")
        report.cancelled = self.cancel_event.is_set()
        report.elapsed = time.time() - t_start
        self.cb.progress(done, total, "Production annulée" if report.cancelled else "Production terminée")
        return report


# =======================================================================================
# Écoute rapide (aperçu d'un texte ou d'une voix)
# =======================================================================================
def preview(text: str, voice: VoiceProfile, project: Project | None = None, language: str | None = None,
            max_chars: int = 1200) -> Path:
    """Synthétise un court texte pour l'écoute ; résultat mis en cache."""
    project = project or Project()
    lang = language or project.metadata.language or voice.language or "fr"
    opts = NormalizeOptions(language=lang, numbers=project.production.normalize_numbers,
                            abbreviations=project.production.expand_abbreviations)
    spoken = normalize_for_speech(text[:max_chars], opts, project.lexicon)
    if not spoken.strip():
        raise RenderError("Rien à lire dans la sélection.")
    engine = engines.get_engine(voice.engine)
    if engine is None:
        raise RenderError(f"Moteur inconnu : {voice.engine}")
    speed = project.production.speed
    key = segment_key(spoken, voice, lang, speed, True)
    out = paths.preview_cache_dir() / f"{key}.wav"
    if out.exists():
        return out
    max_c, min_c = engine.info.max_chars, engine.info.min_chars
    parts: list[np.ndarray] = []
    with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
        for i, chunk in enumerate(chunk_text(spoken, max_c, min_c)):
            written = engine.synthesize(chunk, voice, Path(td) / f"p{i}.wav", lang, speed, 1234 + i)
            data, sr = audio.read_audio(written)
            data = audio.resample(data, sr, SR)
            trimmed = audio.trim_silence(data, SR, -45.0, pad_ms=40)
            data = trimmed if trimmed.size > SR * 0.1 else data
            parts.append(audio.apply_fades(data, SR, 5, 20))
            parts.append(audio.silence(project.production.pause_sentence_ms, SR))
    full = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    audio.write_audio(out, audio.peak_normalize(full, -2.0), SR, subtype="PCM_16")
    return out
