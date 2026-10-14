"""Production : découpage en segments, synthèse avec cache, contrôle qualité et assemblage des chapitres."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
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
from . import asr, audio, course, engines, languages, project_io
from .emotions import apply_emotion
from .exporter import credits_text
from .models import Chapter, Project, VoiceProfile
from .textproc import EMPHASIS_RE, NormalizeOptions, chunk_text, normalize_for_speech, parse_script
from .voices import VoiceLibrary

log = logging.getLogger(__name__)

RENDER_VERSION = 3  # à incrémenter si le post-traitement change (invalide le cache)
SR = audio.DEFAULT_SR
NEURAL_ENGINES = {"xtts", "chatterbox", "kokoro", "fastclone"}
RETRY_ENGINES = {"xtts", "chatterbox", "fastclone", "rvc", "kokoro"}


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
    rate: float = 1.0  # débit relatif ([lent], [rapide]…)
    emphasis: list[str] = field(default_factory=list)  # mots mis en valeur (*mot*), texte normalisé
    pan: float = 0.0  # position stéréo -1 … 1
    overlap_ms: int = 0  # commence avant la fin du passage précédent (réaction « par-dessus »)
    source: str = ""  # fichier lu à la place de la synthèse : effet sonore (kind « sound ») ou prise au micro
    mark: str = ""  # chapitre qui commence avec ce passage
    host: bool = False  # réplique d'un intervenant de la page Intervenants
    lang: str = ""  # langue du passage (« fr », « es-MX »…) : normalisation et moteurs hors ligne
    base_speed: float = 1.0  # débit de base (voix d'explication ou voix natives)


@dataclass
class RenderChapter:
    id: str
    title: str
    kind: str = "chapter"  # opening | chapter | closing
    segments: list[Segment] = field(default_factory=list)
    head_ms: int = 1000
    tail_ms: int = 3000
    warnings: list[str] = field(default_factory=list)
    breaths: str = "off"  # off | light | natural
    stereo: bool = False

    @property
    def plan_hash(self) -> str:
        h = hashlib.sha1()
        h.update(f"{self.head_ms}|{self.tail_ms}|{RENDER_VERSION}|stereo:{self.stereo}".encode())
        if self.breaths != "off":
            h.update(f"breaths:{self.breaths}".encode())
        for s in self.segments:
            h.update(f"{s.key}|{s.pause_after_ms}|{s.overlap_ms}|{s.pan:.3f}|{s.mark};".encode())
        return h.hexdigest()

    def chapter_marks(self, timings: list[tuple[float, float]]) -> list[tuple[float, str]]:
        """Chapitres (début en secondes dans le rendu, titre) d'après les repères et intertitres."""
        marks = [(timings[i][0], s.mark) for i, s in enumerate(self.segments) if s.mark and i < len(timings)]
        if marks and marks[0][0] > 1.5:
            marks.insert(0, (0.0, "Introduction"))
        elif marks:
            marks[0] = (0.0, marks[0][1])
        return marks

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
    fp = [voice.engine, voice.engine_voice, refs, sorted((voice.params or {}).items())]
    if voice.engine in ("fastclone", "rvc") and not voice.engine_voice:
        from .engines.neural import clone_base_default

        fp.append(clone_base_default())  # voix de base « automatique » : Microsoft ou Kokoro
    return fp


def segment_key(text: str, voice: VoiceProfile, language: str, speed: float, trim: bool, emotion: str = "") -> str:
    parts = [RENDER_VERSION, text, _voice_fingerprint(voice), language, round(speed, 3), trim]
    if emotion:
        parts.append(emotion)
    payload = json.dumps(parts, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class VoiceResolver:
    """Choisit la voix de chaque passage : voix d'explication, voix natives des langues balisées, intervenants."""

    def __init__(self, project: Project, library: VoiceLibrary):
        self.project = project
        self.library = library
        self.warnings: list[str] = []
        self._speakers: dict[tuple[str, str], list[str]] = {}  # (langue, sexe) → intervenants dans l'ordre
        self._edge: list | None | bool = False
        self._installed: set[str] | None = None

    def _warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)

    # -- voix natives ------------------------------------------------------------------
    def edge_available(self) -> list | None:
        """Voix Microsoft connues (liste mise en cache, sans appel réseau) ; None : catalogue intégré."""
        if self._edge is False:
            eng = engines.get_engine("edge")
            try:
                self._edge = eng.cached_voices() if eng is not None and hasattr(eng, "cached_voices") else None
            except Exception:
                self._edge = None
        return self._edge or None

    def installed(self) -> set[str]:
        if self._installed is None:
            from .engines import installer

            out = set()
            for eng in ("kokoro", "xtts"):
                try:
                    if installer.is_installed(eng):
                        out.add(eng)
                except Exception:
                    pass
            self._installed = out
        return self._installed

    def native_ids(self, code: str, locale: str = "", gender: str = "") -> list[str]:
        """Voix natives d'une langue : celles choisies dans la page Langues, puis les autres, par préférence."""
        chosen = [v for v in self.project.language_voices.get(code, []) if self.library.get(v) is not None]
        mode = self.project.production.native_offline
        auto = [nv.id for nv in languages.native_voices(code, locale, gender, self.edge_available(), mode,
                                                         self.installed())]
        ids = chosen + [a for a in auto if a not in chosen]
        if gender:
            ids = [i for i in ids if (self.library.get(i) or VoiceProfile("", "")).gender == gender] or ids
        return ids

    def native(self, spec: str, chapter: Chapter | None, index: int = 0, gender: str = "") -> VoiceProfile:
        lang = languages.get(spec)
        if lang is None:
            return self.narrator(chapter)
        locale = spec if "-" in spec else ""
        tcode, tlocale = self.project.target_of(chapter)
        if not locale and languages.get(tcode) is lang:
            locale = tlocale
        ids = self.native_ids(lang.code, locale, gender)
        if not ids:
            self._warn(f"Aucune voix pour « {lang.name} » : la voix d'explication lira ces passages.")
            return self.narrator(chapter)
        return self.library.get(ids[index % len(ids)]) or self.narrator(chapter)

    def resolve_item(self, key: str | None, spec: str, chapter: Chapter | None) -> tuple[VoiceProfile, str]:
        """(voix, langue) d'un passage du script."""
        explain = course.explain_code(self.project)
        lang = languages.get(spec) if spec else None
        if key is None:
            if lang is None or (lang.code == explain and "-" not in spec):
                return self.narrator(chapter), explain
            if lang.code == explain and spec.lower() == (self.project.metadata.language or "").lower():
                return self.narrator(chapter), explain
            return self.native(spec, chapter), spec
        if key == "__dialogue__":
            v = self.library.get(self.project.production.dialogue_voice_id)
            if v is not None:
                return v, spec or explain
            return (self.native(spec, chapter), spec) if lang and lang.code != explain else \
                (self.narrator(chapter), explain)
        host = self.project.host_by_name(key)
        explicit = self.library.get(host.voice_id) if host and host.voice_id else None
        if explicit is None:
            for name, vid in self.project.cast.items():
                if name.strip().lower() == key.strip().lower() and self.library.get(vid) is not None:
                    explicit = self.library.get(vid)
                    break
        if not spec:
            spec = (host.language if host and host.language else "") or course.target_spec(self.project, chapter) \
                if chapter is not None else (host.language if host and host.language else
                                             self.project.metadata.target_language)
        if explicit is not None:
            return explicit, spec
        lang = languages.get(spec)
        if lang is None or (host is not None and host.role == "host" and lang.code == explain):
            return self.narrator(chapter), explain  # professeur : voix d'explication
        gender = host.gender if host else ""
        order = self._speakers.setdefault((lang.code, gender), [])
        if key.lower() not in order:
            order.append(key.lower())
        return self.native(spec, chapter, order.index(key.lower()), gender), spec

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
        host = self.project.host_by_name(key)
        if host is not None and self.library.get(host.voice_id) is not None:
            return self.library.get(host.voice_id)
        for name, vid in self.project.cast.items():
            if name.strip().lower() == key.strip().lower():
                v = self.library.get(vid)
                if v is not None:
                    return v
        msg = f"« {key} » n'a pas de voix attribuée (page Intervenants) : la voix principale sera utilisée."
        if msg not in self.warnings:
            self.warnings.append(msg)
        return narrator


# Respirations : niveau par rapport à la voix (dB) et probabilité après une pause entre phrases / paragraphes
BREATH_LEVELS = {"light": (-27.0, 0.3, 0.6), "natural": (-21.0, 0.5, 0.85)}
BREATH_MIN_GAP_MS = 450


def breath_before(seg: Segment, next_seg: Segment, mode: str) -> int:
    """Durée (ms) de la respiration à placer avant ``next_seg``, ou 0."""
    if mode not in BREATH_LEVELS or seg.pause_after_ms < BREATH_MIN_GAP_MS:
        return 0
    _lvl, p_sentence, p_paragraph = BREATH_LEVELS[mode]
    chance = p_paragraph if next_seg.paragraph != seg.paragraph else p_sentence
    roll = int(hashlib.sha1(f"breath|{seg.key}|{next_seg.key}".encode()).hexdigest()[:6], 16) / 0xFFFFFF
    if roll >= chance:
        return 0
    length = 300 + int(roll / max(chance, 1e-6) * 200)  # 300 à 500 ms
    return min(length, seg.pause_after_ms - 150)


def match_words(words: list[tuple[float, float, str]], phrases: list[str]) -> list[tuple[float, float]]:
    """Positions (début, fin) des mots à mettre en valeur dans la liste des mots prononcés."""
    def norm(w: str) -> str:
        return "".join(ch for ch in w.lower() if ch.isalnum())

    spoken = [norm(w[2]) for w in words]
    regions = []
    for phrase in phrases:
        target = [t for t in (norm(x) for x in phrase.split()) if t]
        if not target:
            continue
        for i in range(len(spoken) - len(target) + 1):
            if spoken[i:i + len(target)] == target:
                regions.append((words[i][0], words[i + len(target) - 1][1]))
                break
    return regions


# Pauses naturelles : durée selon la ponctuation finale (facteur appliqué à la pause réglée)
_END_FACTORS = (("...", 1.6), ("…", 1.6), ("?", 1.2), ("!", 1.15), (";", 0.8), (":", 0.85), (",", 0.6))
VOICE_CHANGE_MS = 150


def natural_pause(base_ms: int, text: str, seed: str, paragraph_end: bool = False) -> int:
    """Pause après un passage : allongée après « … », « ? », « ! », raccourcie après « ; », avec une variation
    de ±12 % (toujours la même pour un même passage, pour que le cache audio reste valable)."""
    if base_ms <= 0:
        return base_ms
    end = text.rstrip().rstrip("»\"”’)] ")
    factor = next((f for mark, f in _END_FACTORS if end.endswith(mark)), 1.0)
    if paragraph_end and len(text) < 60 and factor < 1.5:
        factor *= 0.8  # réplique courte : l'échange garde du rythme
    jitter = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:4], 16) / 0xFFFF  # 0..1
    return int(round(base_ms * factor * (0.88 + 0.24 * jitter)))


def takes_dir(project: Project) -> Path:
    """Dossier des prises enregistrées au micro (dans le dossier du projet)."""
    d = (project.path.parent / "prises") if project.path is not None else project_io.project_data_dir(project) / "prises"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_take(project: Project, name: str) -> Path | None:
    p = Path(name)
    for cand in ([p] if p.is_absolute() else []) + [takes_dir(project) / name]:
        if cand.is_file():
            return cand
    return None


def _file_key(kind: str, path: Path | None, *extra) -> str:
    stamp = [str(path), path.stat().st_size, int(path.stat().st_mtime)] if path and path.exists() else [str(path)]
    payload = json.dumps([RENDER_VERSION, kind, stamp, *extra], ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


REACTION_MAX_WORDS = 4


def is_reaction(text: str) -> bool:
    """Réplique très courte (« Ah oui ! », « Exactement. », « Hmm hmm ») qui peut chevaucher la précédente."""
    words = re.findall(r"[\w'’-]+", text)
    return 0 < len(words) <= REACTION_MAX_WORDS and len(text) <= 32


def _engine_limits(voice: VoiceProfile) -> tuple[int, int]:
    eng = engines.get_engine(voice.engine)
    if eng is None:
        return 300, 0
    return eng.info.max_chars, eng.info.min_chars


SLOW_TAG_RATE = 0.72  # valeur de « [ralenti] » dans textproc.RATE_ALIASES
NORMALIZED_LANGS = {"fr", "en"}  # nombres et abréviations écrits en toutes lettres ; ailleurs, la voix native les lit


def normalize_options(project: Project, spec: str) -> NormalizeOptions:
    lang = languages.get(spec)
    code = lang.code if lang else (spec or "fr").split("-")[0]
    prod = project.production
    full = code in NORMALIZED_LANGS
    return NormalizeOptions(language=code, numbers=prod.normalize_numbers and full,
                            abbreviations=prod.expand_abbreviations and full)


def build_chapter_plan(project: Project, chapter: Chapter, library: VoiceLibrary, kind: str = "chapter",
                       resolver: VoiceResolver | None = None) -> RenderChapter:
    prod = project.production
    explain = course.explain_code(project)
    resolver = resolver or VoiceResolver(project, library)
    rc = RenderChapter(id=chapter.id, title=chapter.title, kind=kind, head_ms=prod.chapter_head_ms,
                       tail_ms=prod.chapter_tail_ms, breaths=prod.breaths if prod.breaths in BREATH_LEVELS else "off",
                       stereo=prod.stereo)
    segs: list[Segment] = []
    paragraph = 0
    pending_mark = [""]
    project_dir = project.path.parent if project.path is not None else None

    def attach_mark() -> str:
        mark, pending_mark[0] = pending_mark[0], ""
        return mark

    def add_text(raw: str, voice: VoiceProfile, kind_: str, end_pause: int, emotion: str = "", rate: float = 1.0,
                 pan: float = 0.0, overlap: bool = False, mark: str = "", host: bool = False, lang: str = ""):
        nonlocal paragraph
        lang = lang or explain
        opts = normalize_options(project, lang)
        native = (languages.get(lang) or languages.get(explain)) is not languages.get(explain)
        base_speed = prod.target_speed if native else prod.speed
        emphasized = [normalize_for_speech(m.group(1), opts, project.lexicon) for m in EMPHASIS_RE.finditer(raw)]
        spoken = normalize_for_speech(raw, opts, project.lexicon)
        if not spoken.strip() or not any(ch.isalnum() for ch in spoken):
            if segs:
                segs[-1].pause_after_ms += end_pause
            return
        max_chars, min_chars = _engine_limits(voice)
        chunks = chunk_text(spoken, max_chars, min_chars)
        for i, c in enumerate(chunks):
            last = i == len(chunks) - 1
            emph = [w for w in emphasized if w and w.lower() in c.lower()]
            tag = emotion + ("|*" + "|".join(emph) if emph else "")
            key = segment_key(c, voice, lang, base_speed * rate, prod.trim_silence, tag)
            pause = end_pause if last else prod.pause_sentence_ms
            if prod.natural_pauses and kind_ == "para":
                pause = natural_pause(pause, c, f"{key}|{len(segs)}",
                                      last and end_pause == prod.pause_paragraph_ms and len(chunks) == 1)
            segs.append(Segment(
                index=len(segs), text=c, display=raw if len(chunks) == 1 else c, voice_id=voice.id,
                pause_after_ms=pause, kind=kind_, key=key, paragraph=paragraph, emotion=emotion, rate=rate,
                emphasis=emph, pan=pan, overlap_ms=prod.overlap_ms if overlap and i == 0 else 0,
                mark=(mark or attach_mark()) if i == 0 else "", host=host, lang=lang, base_speed=base_speed,
            ))
        paragraph += 1

    def add_file(kind_: str, path: Path | None, label: str, voice: VoiceProfile, pan: float, end_pause: int,
                 overlap: bool = False, name: str = ""):
        nonlocal paragraph
        if path is None:
            msg = (f"Son « {name} » introuvable (sons intégrés ou dossier « Mes sons ») : il est ignoré."
                   if kind_ == "sound" else f"Prise « {name} » introuvable dans le dossier « prises » : la voix "
                   "de synthèse lit le texte à la place.")
            if msg not in resolver.warnings:
                resolver.warnings.append(msg)
            return False
        key = _file_key(kind_, path, prod.trim_silence)
        segs.append(Segment(index=len(segs), text="", display=label, voice_id=voice.id, pause_after_ms=end_pause,
                            kind=kind_, key=key, paragraph=paragraph, pan=pan, source=str(path),
                            overlap_ms=prod.overlap_ms if overlap else 0, mark=attach_mark()))
        paragraph += 1
        return True

    if kind == "chapter" and prod.announce_module and chapter.module.strip() and project.first_of_module(chapter):
        add_text(course.module_spoken_title(project, chapter) + ".", resolver.narrator(chapter), "title",
                 prod.pause_heading_ms)
    announce = chapter.announce_title if chapter.announce_title is not None else prod.announce_chapter_titles
    if kind == "chapter" and announce and chapter.title.strip():
        title = course.lesson_spoken_title(project, chapter)
        title += "" if title.endswith(("?", "!", "…")) else "."
        add_text(title, resolver.narrator(chapter), "title", prod.pause_heading_ms)

    # Morceaux d'un même paragraphe (récit / répliques / langues) : regroupés tant que la voix ne change pas.
    pending: list[tuple[str, VoiceProfile, str, float, float, bool, bool, str]] = []

    def flush() -> None:
        for i, (text, voice, emotion, rate, pan, overlap, host, lang) in enumerate(pending):
            last = i == len(pending) - 1
            add_text(text, voice, "para", prod.pause_paragraph_ms if last else prod.pause_sentence_ms, emotion,
                     rate, pan, overlap, host=host, lang=lang)
        pending.clear()

    script = course.lesson_script(project, chapter) if kind == "chapter" else chapter.text
    for item in parse_script(script, prod.detect_dialogues, split=True,
                             incises=prod.narrator_reads_incises):
        if item.kind != "para":
            flush()
        if item.kind == "pause":
            if segs:
                segs[-1].pause_after_ms += item.pause_ms
            else:
                rc.head_ms += item.pause_ms
        elif item.kind == "heading":
            add_text(item.text.rstrip(".") + ".", resolver.narrator(chapter), "heading", prod.pause_heading_ms,
                     mark=item.text.strip())
        elif item.kind == "marker":
            pending_mark[0] = item.source
        elif item.kind == "sound":
            from . import sounds

            add_file("sound", sounds.resolve(item.source, project_dir), f"[son : {item.source}]",
                     resolver.narrator(chapter), 0.0, 350, name=item.source)
        else:
            voice, item_lang = resolver.resolve_item(item.voice_key, item.lang, chapter)
            if abs(item.rate - SLOW_TAG_RATE) < 1e-6:  # « [ralenti] » : débit réglé dans Production
                item.rate = prod.slow_rate
            pan = project.host_pan(item.voice_key) if prod.stereo else 0.0
            if item.take:
                flush()
                shown = item.text if item.text != "…" else f"[prise : {item.take}]"
                if add_file("take", resolve_take(project, item.take), shown, voice, pan, prod.pause_paragraph_ms,
                            item.overlap, item.take) or item.text == "…":
                    continue
            if (pending and pending[-1][1].id == voice.id and pending[-1][2] == item.emotion
                    and pending[-1][3] == item.rate and pending[-1][7] == item_lang and not item.overlap):
                pending[-1] = (pending[-1][0] + " " + item.text, voice, item.emotion, item.rate, pending[-1][4],
                               pending[-1][5], pending[-1][6], item_lang)
            else:
                is_host = bool(item.voice_key) and project.host_by_name(item.voice_key) is not None
                pending.append((item.text, voice, item.emotion, item.rate, pan, item.overlap, is_host, item_lang))
            if not item.joined:
                flush()
    flush()
    if prod.natural_pauses:
        for a, b in zip(segs, segs[1:]):
            if a.voice_id != b.voice_id:
                a.pause_after_ms += VOICE_CHANGE_MS  # petite respiration quand un autre personnage prend la parole
    # Réactions par-dessus : balise « [par-dessus] », ou réplique très courte d'une autre personne
    for a, b in zip(segs, segs[1:]):
        speech = a.kind in ("para", "take") and b.kind in ("para", "take")
        auto = (prod.overlap_reactions and b.kind == "para" and b.host and a.voice_id != b.voice_id
                and not b.mark and is_reaction(b.display))
        if speech and (b.overlap_ms or auto) and a.voice_id != b.voice_id:
            b.overlap_ms = b.overlap_ms or prod.overlap_ms
            a.pause_after_ms = 0
        elif b.overlap_ms and not speech:
            b.overlap_ms = 0
    if segs:
        segs[-1].pause_after_ms = 0
    rc.segments = segs
    rc.warnings = list(resolver.warnings)
    return rc


def credits_chapter(project: Project, kind: str) -> Chapter:
    """Crédits d'ouverture (« opening ») ou de fin (« closing ») sous forme de chapitre à lire."""
    e = project.export
    template = e.opening_credits if kind == "opening" else e.closing_credits
    return Chapter(id=f"__{kind}__", title="Crédits d'ouverture" if kind == "opening" else "Crédits de fin",
                   text=credits_text(template, project.metadata), voice_id=e.credits_voice_id)


def build_plan(project: Project, library: VoiceLibrary, chapter_ids: list[str] | None = None,
               include_credits: bool | None = None) -> list[RenderChapter]:
    resolver = VoiceResolver(project, library)
    plan: list[RenderChapter] = []
    credits = project.export.include_credits if include_credits is None else include_credits
    wanted = set(chapter_ids) if chapter_ids else None
    if credits and (wanted is None or "__opening__" in wanted):
        plan.append(build_chapter_plan(project, credits_chapter(project, "opening"), library, "opening", resolver))
    for ch in project.included_chapters():
        if wanted is None or ch.id in wanted:
            plan.append(build_chapter_plan(project, ch, library, "chapter", resolver))
    if credits and (wanted is None or "__closing__" in wanted):
        plan.append(build_chapter_plan(project, credits_chapter(project, "closing"), library, "closing", resolver))
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
    blocked: str = ""  # service en ligne qui refuse les demandes (production interrompue)


def expected_duration(text: str, speed: float = 1.0) -> float:
    return len(text) / 14.5 / max(0.3, speed)


TAKE_RMS_DB = -20.0  # niveau moyen d'une prise au micro, aligné sur celui des voix de synthèse
SOUND_PEAK_DB = -4.0  # crête des effets sonores

# Moteurs qui passent par le service en ligne de Microsoft (directement ou comme voix de base)
ONLINE_ENGINES = {"edge", "fastclone", "rvc"}


class Renderer:
    def _voice_label(self, voice_id: str) -> str:
        v = self._voice(voice_id)
        eng = engines.get_engine(v.engine)
        return f"« {v.name} » ({eng.info.name if eng else v.engine})"

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
        if seg.source:
            return self._prepare_file(seg, target)
        voice = self._voice(seg.voice_id)
        engine = engines.get_engine(voice.engine)
        if engine is None:
            raise RenderError(f"Moteur inconnu : {voice.engine}")
        voice, emo_speed, emo_gain = apply_emotion(voice, seg.emotion)
        lang = seg.lang or self.project.metadata.language or voice.language or "fr"
        speed = (seg.base_speed or self.project.production.speed) * emo_speed * (seg.rate or 1.0)
        fallback_used = ""
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
                    alt = self._offline_alternative(voice, exc)
                    if alt is None:
                        last_error = exc
                        log.warning("Échec segment %s (essai %d) : %s", seg.index, attempt + 1, exc)
                        if isinstance(exc, engines.ServiceBlocked) or (
                                isinstance(exc, engines.EngineError) and "pas installé" in str(exc)):
                            raise
                        time.sleep(0.5)
                        continue
                    # voix Microsoft injoignable : voix hors ligne de la même langue pour ce passage
                    voice, engine, fallback_used = alt, engines.get_engine(alt.engine), alt.name
                    self.cb.log(f"Voix Microsoft injoignable : « {alt.name} » (hors ligne) lit le passage "
                                f"{seg.index + 1}.")
                    try:
                        written = engine.synthesize(seg.text, voice, raw_target, lang, speed, base_seed)
                    except Exception as exc2:
                        last_error = exc2
                        log.warning("Échec de la voix hors ligne (passage %s) : %s", seg.index, exc2)
                        continue
                data, sr = audio.read_audio(written)
                if seg.emphasis:
                    regions = match_words(engines.read_words(written), seg.emphasis)
                    if regions:
                        data = audio.emphasize(data, sr, regions)
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
        if fallback_used:
            best[2]["fallback"] = fallback_used  # à régénérer avec la voix Microsoft une fois le service revenu
        qc_file = qc_path(self.project, seg.key)
        if best[2]:
            qc_file.write_text(json.dumps(best[2], ensure_ascii=False), encoding="utf-8")
            if best[2].get("wer", 0) > self.project.production.asr_threshold:
                self.cb.log(f"⚠ Passage {seg.index + 1} à vérifier à l'écoute : la relecture a entendu "
                            f"« {best[2].get('heard', '')} »")
        elif qc_file.exists():
            qc_file.unlink()
        return target

    def _offline_alternative(self, voice: VoiceProfile, exc: Exception) -> VoiceProfile | None:
        """Voix hors ligne installée pour remplacer une voix native Microsoft en échec (réseau, refus du service)."""
        if self.project.production.native_offline == "none" or not languages.is_native_id(voice.id) \
                or voice.engine != "edge" or not isinstance(exc, (engines.EngineError, OSError)):
            return None
        resolver = VoiceResolver(self.project, self.library)
        alt_id = languages.offline_alternative(voice.id, resolver.installed())
        alt = self.library.get(alt_id) if alt_id else None
        if alt is None or engines.get_engine(alt.engine) is None:
            return None
        return alt

    def _prepare_file(self, seg: Segment, target: Path) -> Path:
        """Effet sonore ou prise au micro : mis au format du rendu (et, pour une prise, au niveau des voix)."""
        src = Path(seg.source)
        if not src.is_file():
            raise RenderError(f"Fichier introuvable : {src}")
        data, sr = audio.read_audio(src)
        data = audio.remove_dc(audio.resample(data, sr, SR))
        if seg.kind == "take":
            if self.project.production.trim_silence:
                trimmed = audio.trim_silence(data, SR, -45.0, pad_ms=60)
                if trimmed.size > SR * 0.1:
                    data = trimmed
            rms = audio.lin_to_db(float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))) if data.size else -120
            if rms > -70:  # même niveau moyen que les voix de synthèse (≈ -20 dB RMS)
                gain = max(-20.0, min(24.0, TAKE_RMS_DB - rms))
                data = data * audio.db_to_lin(gain)
            peak = float(np.max(np.abs(data))) if data.size else 0.0
            if peak > 0.98:
                data = data * (0.98 / peak)
            data = audio.apply_fades(data.astype(np.float32), SR, 8, 30)
        else:
            peak = float(np.max(np.abs(data))) if data.size else 0.0
            if peak > 0:
                data = data * (audio.db_to_lin(SOUND_PEAK_DB) / peak)
            data = audio.apply_fades(data.astype(np.float32), SR, 3, 40)
        audio.write_audio(target, data.astype(np.float32), SR, subtype="PCM_24")
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
        """Assemble les passages : silences, respirations, réactions par-dessus, placement stéréo."""
        out = chapter_output(self.project, rc.id)
        tmp = out.with_suffix(".tmp.flac")
        timings: list[tuple[float, float]] = []
        channels = 2 if rc.stereo else 1
        pos = 0  # échantillons déjà écrits dans le fichier
        # Le dernier passage reste en mémoire (« held ») tant que le suivant peut venir le chevaucher.
        held = np.zeros((0, channels), dtype=np.float32)

        def place(mono: np.ndarray, pan: float) -> np.ndarray:
            if channels == 1:
                return mono.reshape(-1, 1).astype(np.float32)
            angle = (max(-1.0, min(1.0, pan)) + 1) * np.pi / 4  # panoramique à puissance constante
            return np.stack([mono * np.cos(angle), mono * np.sin(angle)], axis=1).astype(np.float32) * np.sqrt(2)

        with sf.SoundFile(str(tmp), "w", samplerate=SR, channels=channels, subtype="PCM_24", format="FLAC") as fh:
            held = place(audio.silence(rc.head_ms, SR), 0.0)
            for i, seg in enumerate(rc.segments):
                data, sr = audio.read_audio(cache_path(self.project, seg.key))
                if sr != SR:
                    data = audio.resample(data, sr, SR)
                block = place(data, seg.pan)
                ov = 0
                if seg.overlap_ms and i > 0:
                    # au plus 40 % de la réplique précédente, et jamais plus long que la réaction elle-même
                    prev_len = int((timings[-1][1] - timings[-1][0]) * SR)
                    ov = min(int(seg.overlap_ms * SR / 1000), int(prev_len * 0.4), len(held), max(0, len(block) - 1))
                if ov:
                    held[len(held) - ov:] += block[:ov] * audio.db_to_lin(-1.5)
                    start = pos + len(held) - ov
                    block = block[ov:]
                else:
                    start = pos + len(held)
                np.clip(held, -0.999, 0.999, out=held)  # deux voix superposées : jamais d'écrêtage numérique
                fh.write(held)
                pos += len(held)
                timings.append((start / SR, (start + ov + len(block)) / SR))
                gap = audio.silence(seg.pause_after_ms, SR)
                nxt = rc.segments[i + 1] if i + 1 < len(rc.segments) else None
                length = breath_before(seg, nxt, rc.breaths) if nxt is not None else 0
                if length > 0:
                    # niveau calé sur la voix qui va parler, juste avant qu'elle reprenne
                    ref = data[-SR:] if data.size else data
                    voice_db = audio.lin_to_db(float(np.sqrt(np.mean(ref.astype(np.float64) ** 2)))) if ref.size else -20
                    level = max(-60.0, min(voice_db, -14.0) + BREATH_LEVELS[rc.breaths][0])
                    b = audio.breath(SR, length, level, seed=int(nxt.key[:8], 16))
                    end = len(gap) - int(SR * 0.07)
                    if end - len(b) > 0:
                        gap[end - len(b):end] = b
                pan_next = nxt.pan if nxt is not None else 0.0
                held = np.concatenate([block, place(gap, pan_next)]) if len(gap) else block
            tail = place(audio.silence(max(rc.tail_ms, 500), SR), 0.0)
            held = np.concatenate([held, tail])
            np.clip(held, -0.999, 0.999, out=held)
            fh.write(held)
            pos += len(held)
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
                    workers = int(settings().get("edge_concurrency", 2) or 1)
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
                    if self.cancel_event.is_set() and not isinstance(exc, engines.ServiceBlocked):
                        return seg, "cancelled", None  # arrêt demandé pendant le passage : pas une erreur
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
                            if not isinstance(exc, engines.ServiceBlocked):
                                self.cb.log(f"Erreur sur « {rc.title} », passage {seg.index + 1} "
                                            f"({self._voice_label(seg.voice_id)}) : {exc}")
                        self.cb.progress(done, total, f"{rc.title} — passage {seg.index + 1}/{len(rc.segments)}")
                        if isinstance(exc, engines.ServiceBlocked) and not report.blocked:
                            online = sorted({self._voice_label(s.voice_id) for c in plan for s in c.segments
                                             if self._voice(s.voice_id).engine in ONLINE_ENGINES})
                            report.blocked = (f"Passage {seg.index + 1} de « {rc.title} », lu par "
                                              f"{self._voice_label(seg.voice_id)}.\n\n{exc}\n\nVoix de ce projet "
                                              "qui passent par Microsoft : " + ", ".join(online) + ".")
                            self.cb.log("Production interrompue : " + report.blocked)
                            self.cancel_event.set()
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
            max_chars: int = 1200, speed: float | None = None) -> Path:
    """Synthétise un court texte pour l'écoute ; résultat mis en cache."""
    project = project or Project()
    lang = language or (voice.language if voice.language not in ("", "multi") else "") \
        or project.metadata.language or "fr"
    opts = normalize_options(project, lang)
    spoken = normalize_for_speech(text[:max_chars], opts, project.lexicon)
    if not spoken.strip():
        raise RenderError("Rien à lire dans la sélection.")
    engine = engines.get_engine(voice.engine)
    if engine is None:
        raise RenderError(f"Moteur inconnu : {voice.engine}")
    if speed is None:
        native = languages.get(lang) is not languages.get(course.explain_code(project))
        speed = project.production.target_speed if native else project.production.speed
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
