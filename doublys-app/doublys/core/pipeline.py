"""Chaîne de doublage : chaque étape lit et écrit dans le dossier de travail du projet et peut être relancée seule.

extraction → sous-titres existants → séparation → transcription (langue, parole) → répliques → personnes →
traduction → voix → doublage → mixage → export

Avec des sous-titres (piste, fichier ou lecture de l'image), le texte vient des sous-titres et la parole détectée
ne sert qu'au recalage et au contrôle de couverture : chaque passage parlé a une VF ou il est signalé.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import align, ai, audio, coverage, dubvoice, engines, media, mixer, ocr, refs, segment, speakers, subsources
from . import subtitles, timing
from . import project as project_io
from . import qc
from . import translate as local_translate
from .engines import EngineError, ServiceBlocked
from .engines.neural import WorkerDied
from .ffmpeg import Cancelled
from .models import (AUTO_LANGUAGE, LANGUAGES, STEP_LABELS, TRANSLATORS, Line, Project, VoiceProfile,
                     language_name)

log = logging.getLogger(__name__)

ORIGINAL = "original.wav"
ORIGINAL16 = "original16.wav"
VOICE = "voix.wav"
VOICE16 = "voix16.wav"
BACKGROUND = "fond.wav"
TRANSCRIPT = "transcription.json"
SPEECH = "parole.json"
TRANSCRIPT_PARTS = "transcription"  # dossier : un fichier par morceau (reprise)
CHUNK_SECONDS = 600.0
MIX = "vf_mix.wav"
VF_VOICES = "vf_voix.wav"
CUES = "sous-titres.json"  # sous-titres retenus (texte des répliques)
SUBS_DIR = "sous-titres"  # pistes extraites
MAX_ATTEMPTS = 3  # essais de synthèse d'une réplique avant la voix de secours


class StepError(RuntimeError):
    pass


@dataclass
class Job:
    """Lien avec l'interface : avancement, messages, arrêt demandé."""

    on_progress: Callable[[str, float, str], None] | None = None
    on_log: Callable[[str], None] | None = None
    on_line: Callable[[str], None] | None = None  # une réplique a changé (identifiant)
    cancel: threading.Event = field(default_factory=threading.Event)
    step: str = ""
    resume: bool = False  # l'étape avait été interrompue : on garde le travail déjà fait
    save: Callable[[], None] | None = None

    def progress(self, value: float, msg: str = "") -> None:
        if self.on_progress:
            self.on_progress(self.step, max(0.0, min(1.0, value)), msg)

    def log(self, msg: str) -> None:
        log.info(msg)
        if self.on_log:
            self.on_log(msg)

    def check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def line_changed(self, line_id: str) -> None:
        if self.on_line:
            self.on_line(line_id)


def _tool(name: str):
    tool = engines.get_tool(name)
    if tool is None or not tool.is_ready():
        label = {"analysis": "Analyse (voix, personnes, traduction)", "whisper": "Whisper (transcription)",
                 "ocr": "OCR (sous-titres incrustés)"}[name]
        raise StepError(f"Le moteur « {label} » n'est pas installé : installez-le depuis la page Moteurs IA "
                        "(bouton « Installer tout ce qu'il faut » sur l'accueil).")
    return tool


def _guard(job: Job, fn, *args, **kwargs):
    """Appel à un processus moteur : un arrêt demandé (processus tué) devient une annulation."""
    try:
        return fn(*args, **kwargs)
    except (WorkerDied, EngineError):
        if job.cancel.is_set():
            raise Cancelled() from None
        raise


def wf(project: Project, name: str) -> Path:
    return project_io.work_file(project, name)


def speech_source(project: Project) -> tuple[Path, Path]:
    """(voix 44,1 kHz, voix 16 kHz) : voix isolée si la séparation est faite, sinon le son d'origine."""
    if project.settings.separate and wf(project, VOICE).exists() and wf(project, VOICE16).exists():
        return wf(project, VOICE), wf(project, VOICE16)
    return wf(project, ORIGINAL), wf(project, ORIGINAL16)


# ---------------------------------------------------------------------------------------
# Étapes
# ---------------------------------------------------------------------------------------
def step_extract(project: Project, job: Job) -> str:
    src = Path(project.source_video)
    if not src.is_file():
        raise StepError(f"La vidéo est introuvable : {src}. Remettez-la à sa place ou ouvrez-la à nouveau.")
    if not project.video.duration:
        project.video = project_io.probe_video(src)
    # le son change : les fichiers des étapes suivantes (éventuellement à moitié faits) ne valent plus rien
    for name in (VOICE, VOICE16, BACKGROUND, SPEECH, TRANSCRIPT):
        wf(project, name).unlink(missing_ok=True)
    shutil.rmtree(wf(project, TRANSCRIPT_PARTS), ignore_errors=True)
    media.extract_audio(src, wf(project, ORIGINAL), wf(project, ORIGINAL16), project.video.duration,
                        progress=lambda f: job.progress(f, "Extraction du son"), cancel=job.cancel)
    return f"{project.video.duration / 60:.1f} min de son extrait"


def glossary_terms(project: Project) -> list[str]:
    """Noms propres du glossaire (pour corriger la lecture des sous-titres)."""
    return [str(g[0]) for g in project.settings.glossary if g and str(g[0]).strip()]


def load_cues(project: Project) -> list[subsources.Cue]:
    p = wf(project, CUES)
    if not p.exists():
        return []
    try:
        return [subsources.Cue(**c) for c in json.loads(p.read_text(encoding="utf-8"))]
    except (ValueError, TypeError):
        return []


def subtitle_candidates(project: Project, job: Job, with_ocr: bool = True) -> list[subsources.Candidate]:
    """Pistes de la vidéo, fichiers voisins, et sous-titres incrustés si aucun des deux n'est utilisable."""
    src = Path(project.source_video)
    cands = subsources.find_tracks(src) + subsources.find_files(src)
    subs = project.subs
    need_ocr = subs.kind == "ocr" or not any(subsources.usable(c) for c in cands)
    if with_ocr and need_ocr:
        v = project.video
        if subs.kind == "ocr" and subs.zone and subs.zone[1] > subs.zone[0]:
            cands.append(subsources.Candidate("ocr", "en", "Sous-titres incrustés dans l'image"))
        else:
            job.progress(0.05, "Recherche de sous-titres dans l'image…")
            info = ocr.detect_zone(src, v.duration, v.width, v.height, cancel=job.cancel)
            if info is not None:
                subs.zone = [info.top, info.bottom]
                cands.append(subsources.Candidate("ocr", "en", f"Sous-titres incrustés dans l'image (présents sur "
                                                              f"{info.presence:.0%} des images)"))
    return cands


def step_subtitles(project: Project, job: Job) -> str:
    """Sous-titres existants (piste, fichier ou image) : ils donneront le texte des répliques."""
    st, subs = project.settings, project.subs
    wf(project, CUES).unlink(missing_ok=True)
    if not st.use_subtitles:
        subs.kind, subs.count, subs.label = "none", 0, ""
        return "non utilisés : le texte viendra de la voix (Whisper)"
    wanted = subs.kind
    cands = subtitle_candidates(project, job)
    subs.candidates = [c.to_dict() for c in cands]
    chosen = None
    if wanted == "track":
        chosen = next((c for c in cands if c.kind == "track" and c.track == subs.track), None)
    elif wanted == "file":
        chosen = next((c for c in cands if c.kind == "file" and c.path == subs.path), None)
        if chosen is None and subs.path and Path(subs.path).is_file():  # fichier glissé sur l'appli
            chosen = subsources.Candidate("file", subsources.lang_from_name(subs.path),
                                          f"Fichier « {Path(subs.path).name} »", path=subs.path)
    elif wanted == "ocr":
        chosen = next((c for c in cands if c.kind == "ocr"), None)
    if chosen is None and wanted != "none":
        ranked = [c for c in subsources.rank(cands) if subsources.usable(c)]
        chosen = ranked[0] if ranked else None
    if chosen is None:
        subs.kind, subs.count, subs.label = "none", 0, ""
        found = f" ({len(cands)} piste(s) non utilisable(s))" if cands else ""
        return f"aucun sous-titre utilisable{found} : le texte viendra de la voix (Whisper)"
    src = Path(project.source_video)
    if chosen.kind == "track":
        out_dir = wf(project, SUBS_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        job.progress(0.2, "Extraction de la piste de sous-titres…")
        path = subsources.extract_track(src, chosen, out_dir, job.cancel)
        raw = subsources.load_file(path)
    elif chosen.kind == "file":
        raw = subsources.load_file(Path(chosen.path))
    else:
        tool = _tool("ocr")
        v = project.video
        raw, ocr_dropped = ocr.read_hardsubs(src, v.duration, v.width, v.height, tuple(subs.zone), tool,
                                             st.ocr_fps, glossary_terms(project),
                                             progress=lambda f, m: job.progress(0.1 + 0.85 * f, m), cancel=job.cancel)
        coverage.save_dropped(project, "ocr", ocr_dropped)
        srt = src.with_name(f"{src.stem} (EN, OCR).srt")
        try:
            ocr.write_srt(raw, srt)
        except OSError:  # dossier de la vidéo en lecture seule : copie dans le projet
            srt = ocr.write_srt(raw, wf(project, f"{src.stem} (EN, OCR).srt"))
        job.log(f"Sous-titres lus dans l'image : {len(raw)}, enregistrés dans « {srt.name} »")
    cues, dropped = subsources.prepare(raw)
    cues = subsources.merge_fragments(cues)
    coverage.save_dropped(project, "sous-titres", dropped)
    lang = chosen.language or subsources.guess_language([c.text for c in cues]) or "en"
    wf(project, CUES).write_text(json.dumps([dataclasses.asdict(c) for c in cues], ensure_ascii=False),
                                 encoding="utf-8")
    subs.kind, subs.track, subs.path = chosen.kind, chosen.track, chosen.path
    subs.language, subs.label, subs.count = lang, chosen.label, len(cues)
    if dropped:
        job.log(f"{len(dropped)} sous-titre(s) écarté(s) du doublage (panneaux, génériques, vides) : voir Contrôle")
    if not cues:
        subs.kind = "none"
        return f"{chosen.label} : aucun dialogue trouvé, le texte viendra de la voix (Whisper)"
    return f"{len(cues)} sous-titres ({chosen.label}, {language_name(lang).lower()})"


def speech_regions(project: Project, job: Job) -> list[list[float]] | None:
    """Passages de parole du son d'origine (calculés une fois, en quelques secondes) ; None si indisponible."""
    p = wf(project, SPEECH)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    tool = engines.get_tool("whisper")
    if tool is None or not tool.is_ready():
        return None
    job.progress(0.0, "Repérage des passages parlés…")
    # seuil bas : un bloc jugé muet n'est pas séparé, et sa voix isolée serait vide (parole sous la musique)
    regions = _guard(job, tool.vad, wf(project, ORIGINAL16), threshold=0.35, min_speech_ms=150)
    p.write_text(json.dumps(regions), encoding="utf-8")
    return regions


def step_separate(project: Project, job: Job) -> str:
    tool = _tool("analysis")
    t0 = time.time()
    speech = speech_regions(project, job)
    job.progress(0.0, "Chargement de Demucs…")
    res = _guard(job, tool.separate, wf(project, ORIGINAL), wf(project, VOICE), wf(project, BACKGROUND),
                 on_progress=lambda v, m: job.progress(v, m), speech=speech, resume=job.resume)
    job.check()
    media.to_mono16(wf(project, VOICE), wf(project, VOICE16), job.cancel)
    total = float(res.get("duration") or 0) or 1.0
    skipped = max(0.0, 1 - float(res.get("separated", total)) / total)
    extra = f" ({skipped * 100:.0f} % sans parole, non traités)" if skipped > 0.05 else ""
    return f"voix et fond séparés en {(time.time() - t0) / 60:.1f} min{extra}"


def chunks_for(duration: float, speech: list[list[float]] | None, size: float | None = None) -> list[tuple]:
    """Morceaux d'environ ``size`` secondes, coupés au milieu d'un silence (aucun mot tranché)."""
    size = size or CHUNK_SECONDS
    if duration <= size * 1.3:
        return [(0.0, duration)]
    cuts = [0.0]
    gaps = []
    if speech:
        gaps = [((a[1] + b[0]) / 2, b[0] - a[1]) for a, b in zip(speech, speech[1:]) if b[0] - a[1] > 0.3]
    t = size
    while t < duration - size * 0.3:
        near = [g for g in gaps if abs(g[0] - t) < size * 0.25]
        cut = max(near, key=lambda g: g[1] - abs(g[0] - t) / 60)[0] if near else t
        cuts.append(round(cut, 2))
        t = cut + size
    cuts.append(duration)
    return list(zip(cuts, cuts[1:]))


def has_cues(project: Project) -> bool:
    return project.subs.kind in ("track", "file", "ocr") and project.subs.count > 0 and wf(project, CUES).exists()


def detect_language(project: Project, job: Job, tool, voice16: Path, speech: list | None) -> None:
    """Langue parlée votée sur 5 extraits pris dans la parole ; affichée et modifiable (jamais forcée en silence)."""
    st = project.settings
    duration = audio.duration_of(voice16) or project.video.duration
    regions = [r for r in (speech or []) if r[1] - r[0] >= 2.0] or [[0.0, duration]]
    picks = [regions[int(i * (len(regions) - 1) / 4)] for i in range(5)] if len(regions) > 1 else regions
    spans, seen = [], set()
    for a, _b in picks:
        a = round(min(max(0.0, a), max(0.0, duration - 5.0)), 1)
        if a not in seen:
            seen.add(a)
            spans.append([a, min(duration, a + 30.0)])
    job.progress(0.0, "Détection de la langue parlée…")
    res = _guard(job, tool.detect_language, voice16, spans)
    lang, prob = str(res.get("language") or ""), float(res.get("probability") or 0.0)
    if not lang:
        return
    st.detected_language, st.language_confidence = lang, round(prob, 3)
    job.log(f"Langue parlée détectée : {language_name(lang)} ({prob:.0%})")
    if st.source_language != AUTO_LANGUAGE and st.source_language != lang and prob > 0.8:
        job.log(f"⚠ La langue choisie ({language_name(st.source_language)}) n'est pas celle détectée "
                f"({language_name(lang)}) : vérifiez le réglage « Langue de la vidéo ».")


def step_transcribe(project: Project, job: Job) -> str:
    tool = _tool("whisper")
    _voice, voice16 = speech_source(project)
    speech = speech_regions(project, job)
    detect_language(project, job, tool, wf(project, ORIGINAL16), speech)
    # parole pour le recalage et le contrôle de couverture : son d'origine ET voix isolée, seuil bas
    job.progress(0.1, "Repérage fin de la parole…")
    sources = [wf(project, ORIGINAL16)] + ([voice16] if voice16 != wf(project, ORIGINAL16) else [])
    talk = _guard(job, coverage.detect_speech, project, tool, sources)
    if has_cues(project):
        wf(project, TRANSCRIPT).write_text(json.dumps({"words": [], "segments": [], "duration": 0.0}),
                                           encoding="utf-8")
        coverage.save_dropped(project, "whisper", [])
        return (f"{language_name(project.settings.language).lower()} ; {coverage.total(talk) / 60:.1f} min de "
                "parole repérée (texte pris dans les sous-titres)")
    model = project.settings.whisper_model
    duration = audio.duration_of(voice16) or project.video.duration
    chunks = chunks_for(duration, speech)
    parts_dir = wf(project, TRANSCRIPT_PARTS)
    if not job.resume:
        shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir(parents=True, exist_ok=True)
    words, segs, dropped = [], [], []
    job.progress(0.0, f"Chargement de Whisper « {model} »…")
    for k, (a, b) in enumerate(chunks):
        job.check()
        part = parts_dir / f"{k:03d}.json"
        key = [round(a, 2), round(b, 2), model, voice16.name, int(voice16.stat().st_mtime)]
        data = None
        if part.exists():
            try:
                data = json.loads(part.read_text(encoding="utf-8"))
                data = data if data.get("key") == key else None
            except ValueError:
                data = None
        if data is None:
            def prog(v, m, k=k):
                job.progress((k + v) / len(chunks), f"{m} · morceau {k + 1} sur {len(chunks)}")

            st = project.settings
            lang = st.detected_language if st.source_language == AUTO_LANGUAGE else st.source_language
            data = _guard(job, tool.transcribe_words, voice16, lang or None, model, on_progress=prog, start=a,
                          end=b)
            data["key"] = key
            part.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if project.settings.source_language == AUTO_LANGUAGE and not project.settings.detected_language:
            project.settings.detected_language = str(data.get("language") or "en")
            job.log(f"Langue détectée : {language_name(project.settings.detected_language)}")
        words += data.get("words", [])
        segs += data.get("segments", [])
        dropped += [{"start": d[0], "end": d[1], "text": d[2], "reason": f"Whisper : {d[3]}"}
                    for d in data.get("dropped", [])]
        job.progress((k + 1) / len(chunks), f"{len(words)} mots reconnus")
    wf(project, TRANSCRIPT).write_text(json.dumps({"words": words, "segments": segs, "duration": duration},
                                                  ensure_ascii=False), encoding="utf-8")
    coverage.save_dropped(project, "whisper", dropped)
    if dropped:
        job.log(f"{len(dropped)} passage(s) écarté(s) par Whisper (texte douteux) : listés dans Contrôle")
    if not words:
        raise StepError("Whisper n'a reconnu aucune parole dans cette vidéo.")
    return f"{len(words)} mots reconnus ({language_name(project.settings.language).lower()})"


def load_transcript(project: Project) -> dict:
    p = wf(project, TRANSCRIPT)
    if not p.exists():
        raise StepError("Transcription absente : relancez l'étape « Transcription ».")
    return json.loads(p.read_text(encoding="utf-8"))


def lines_from_cues(project: Project, job: Job) -> list[Line]:
    """Une réplique par sous-titre, recalée sur la parole réelle (décalage global puis début et fin)."""
    subs = project.subs
    cues = load_cues(project)
    talk = coverage.load_speech(project) or []
    auto, gain = align.global_offset([(c.start, c.end) for c in cues], talk)
    subs.auto_offset = auto
    if auto:
        job.log(f"Sous-titres décalés de {auto:+.2f} s pour suivre la parole (recouvrement +{gain:.0%})")
    shift = auto + subs.offset
    fr = subs.language == "fr"
    lines = []
    for c in cues:
        a, b = max(0.0, c.start + shift), max(0.0, c.end + shift)
        lines.append(Line(start=round(a, 3), end=round(b, 3), en=c.text, fr=c.text if fr else "", fr_edited=fr,
                          source=subs.kind, src_start=round(a, 3), src_end=round(b, 3), ocr_conf=c.conf))
    align.refine(lines, talk)
    return lines


def mark_songs(project: Project, lines: list[Line]) -> int:
    """Génériques chantés : longue suite de répliques où la musique domine nettement la voix (au moins 60 s) ;
    elles ne sont pas doublées (la musique d'origine reste). Plages « ne pas doubler » appliquées aussi."""
    n = 0
    for ln in lines:
        if any(float(a) <= ln.start and ln.end <= float(b) for a, b in project.no_dub_ranges):
            ln.no_dub, n = True, n + 1
    if not (project.settings.separate and wf(project, VOICE).exists() and wf(project, BACKGROUND).exists()):
        return n
    music = []
    for ln in lines:
        v, vsr = refs.read_span(wf(project, VOICE), ln.start, ln.end)
        bg, bsr = refs.read_span(wf(project, BACKGROUND), ln.start, ln.end)
        music.append(timing.active_rms_db(bg, bsr) - timing.active_rms_db(v, vsr) > 12.0)
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and music[j]:
            j += 1
        if j - i >= 2 and lines[j - 1].end - lines[i].start >= 60.0:
            for ln in lines[i:j]:
                if not ln.no_dub:
                    ln.no_dub, n = True, n + 1
        i = max(j, i + 1)
    return n


def step_segment(project: Project, job: Job) -> str:
    s = project.settings
    if has_cues(project):
        lines = lines_from_cues(project, job)
    else:
        words = load_transcript(project).get("words", [])
        lines = segment.lines_from_words(words, s.pause_split, s.max_line, s.min_fragment)
    # personnes déjà connues : chaque nouvelle réplique reprend celle de l'ancienne réplique qui la recouvre
    old = project.lines
    for ln in lines:
        best = max(old, key=lambda o: min(o.end, ln.end) - max(o.start, ln.start), default=None)
        if best is not None and min(best.end, ln.end) > max(best.start, ln.start):
            ln.person_id = best.person_id
    project.lines = lines
    songs = mark_songs(project, lines)
    if songs:
        job.log(f"{songs} réplique(s) chantée(s) ou en plage « ne pas doubler » : voix d'origine gardée")
    coverage.update(project)
    job.progress(1.0)
    src = {"track": "piste de sous-titres", "file": "fichier de sous-titres", "ocr": "sous-titres de l'image"}.get(
        project.subs.kind, "")
    return f"{len(lines)} répliques" + (f" (texte : {src})" if src and has_cues(project) else "")


def step_speakers(project: Project, job: Job) -> str:
    s = project.settings
    if not project.lines:
        raise StepError("Aucune réplique : relancez le découpage.")
    _voice, voice16 = speech_source(project)
    tool = _tool("analysis")
    job.progress(0.0, "Chargement du modèle d'empreintes vocales…")
    segs = [(ln.start, ln.end) for ln in project.lines]
    emb = _guard(job, tool.embed, voice16, segs, on_progress=lambda v, m: job.progress(v, m))
    embeddings = {ln.id: e for ln, e in zip(project.lines, emb)}
    before = {ln.id: ln.person_id for ln in project.lines}
    people = speakers.assign_people(project.lines, embeddings, s.speaker_threshold, s.max_speakers)
    project.people = speakers.keep_names(project.people, people, before, project.lines)
    speakers.score_lines(project.lines, embeddings, project.people)
    found = ""
    if project.series:
        from . import series as series_lib

        matched = series_lib.apply_to_project(project)
        if matched:
            found = f", dont {matched} personnage(s) de la série « {project.series} » reconnu(s)"
    return f"{len(project.people)} personne(s){found}"


def glossary(project: Project) -> list[tuple[str, str]]:
    """Termes à garder ou à rendre toujours de la même façon (noms, attaques, « Henshin »…)."""
    out = []
    for item in project.settings.glossary or []:
        if isinstance(item, (list, tuple)) and item and str(item[0]).strip():
            src = str(item[0]).strip()
            out.append((src, str(item[1]).strip() if len(item) > 1 and str(item[1]).strip() else src))
    return out


def apply_glossary(text: str, terms: list[tuple[str, str]]) -> str:
    import re

    for src, fr in sorted(terms, key=lambda t: -len(t[0])):
        if re.search(r"[A-Za-z]", src):
            text = re.sub(rf"\b{re.escape(src)}\b", fr, text, flags=re.IGNORECASE)
        else:  # japonais, chinois… : pas de limite de mot
            text = text.replace(src, fr)
    return text


def step_translate(project: Project, job: Job, only: list[str] | None = None, force: bool = False) -> str:
    s = project.settings
    lines = sorted(project.lines, key=lambda x: x.start)
    project.lines = lines
    avail = timing.slots(lines, s, project.video.duration)
    todo = [i for i, ln in enumerate(lines) if (only is None or ln.id in only) and (force or not ln.fr_edited)
            and ln.en.strip()]
    if not todo:
        return "rien à traduire"
    result = _translate_some(project, job, lines, avail, todo, only)
    job.check()
    # traduction vide (rare : phrase très courte, cri) : nouvelle tentative réplique par réplique
    empty = [i for i in todo if lines[i].en.strip() and not (result.get(i) or lines[i].fr).strip()]
    for i in empty:
        job.check()
        again = _translate_some(project, job, lines, avail, [i], [lines[i].id])
        if (again.get(i) or "").strip():
            result[i] = again[i]
        else:
            job.log(f"Réplique {i + 1} ({lines[i].start:.1f} s) : traduction vide, à saisir à la main")
    changed = 0
    for i, fr in result.items():
        lines[i].checked = False
        if fr and fr != lines[i].fr:
            lines[i].fr = fr
            lines[i].fr_edited = False
            changed += 1
            job.line_changed(lines[i].id)
    qc.check(project)
    return f"{len(result)} répliques traduites"


def _translate_some(project: Project, job: Job, lines: list[Line], avail: list[float], todo: list[int],
                    only: list[str] | None) -> dict[int, str]:
    s = project.settings
    if s.translator == "deepseek":
        client = ai.client_from_settings()
        items = [{"en": ln.en, "person": (project.person(ln.person_id).name if project.person(ln.person_id) else ""),
                  "budget": timing.char_budget(avail[i], s.chars_per_second)} for i, ln in enumerate(lines)]
        extra = {"source": language_name(s.language).lower(), "glossary": glossary(project)}
        # tout le contexte est envoyé, seules les répliques demandées sont mises à jour
        if only is not None:
            sub = [items[i] for i in todo]
            res = ai.translate_lines(sub, client, lambda m: job.progress(0.5, m), job.cancel, **extra)
            result = dict(zip(todo, res))
        else:
            done = [0]

            def prog(msg):
                done[0] += 1
                job.progress(min(0.99, done[0] * ai.BATCH_LINES / max(1, len(items))), msg)

            res = ai.translate_lines(items, client, prog, job.cancel, **extra)
            result = {i: res[i] for i in todo}
    else:
        to_fr = TRANSLATORS.get(s.translator if s.translator in ("opus", "opus_big") else "opus_big")[1]
        lang = s.language
        _name, _iso, direct, to_en = LANGUAGES.get(lang, ("", "", "", "Helsinki-NLP/opus-mt-mul-en"))
        tool = _tool("analysis")
        job.progress(0.0, "Chargement du traducteur…")
        budgets = [timing.char_budget(a, s.chars_per_second) for a in avail]
        terms = glossary(project)

        def fn(sentences, n_best):
            sentences = [apply_glossary(x, terms) for x in sentences]
            if lang == "en":
                model, src = to_fr, sentences
            elif direct:
                model, src = direct, sentences
            else:  # pas de traducteur direct : on passe par l'anglais
                job.progress(0.0, f"Traduction {language_name(lang).lower()} → anglais…")
                src = _guard(job, tool.translate, sentences, to_en, on_progress=lambda v, m: job.progress(v / 2, m))
                model = to_fr
            return _guard(job, tool.translate, src, model, on_progress=lambda v, m: job.progress(v, m),
                          n_best=n_best)

        result = local_translate.translate_lines(lines, budgets, fn, todo)
    return result


def step_voices(project: Project, job: Job, only: list[str] | None = None) -> str:
    voice, _v16 = speech_source(project)
    out_dir = project_io.references_dir(project)
    people = [p for p in project.people if only is None or p.id in only]
    for k, person in enumerate(people):
        job.check()
        mine = [ln for ln in project.lines if ln.person_id == person.id]
        ref = dubvoice.reference_path(project, person)
        if person.reference_source != "file" or ref is None:
            if not mine:
                continue
            target = out_dir / f"{person.id}.wav"
            path, dur = refs.build_reference(voice, mine, target, person.reference_offset)
            person.reference = project_io.relative(project, path)
            person.reference_source = "auto"
            ref = path
        # intensité de chaque réplique par rapport à la voix habituelle de la personne
        levels = []
        for ln in mine:
            seg, ssr = refs.read_span(voice, ln.start, ln.end)
            levels.append(timing.active_rms_db(seg, ssr))
        usable = sorted(v for v in levels if v > -90)
        median = usable[len(usable) // 2] if usable else -120.0
        for ln, v in zip(mine, levels):
            ln.intensity = round(v - median, 1) if v > -90 and median > -90 else 0.0
        data, sr = audio.read_audio(ref)
        person.pitch_hz = round(refs.estimate_pitch(data, sr), 1)
        g = refs.gender_from_pitch(person.pitch_hz)
        if g and not person.gender_locked:
            person.gender = g
            if refs.gender_is_uncertain(person.pitch_hz):
                job.log(f"{person.name} : voix à {person.pitch_hz:.0f} Hz, genre incertain "
                        f"(« {'homme' if g == 'M' else 'femme'} » choisi) : à vérifier dans la page Personnes.")
        job.progress((k + 1) / max(1, len(people)), person.name)
    return f"{len(people)} voix préparée(s)"


def _line_key(project: Project, line: Line, slot: float, vkey: str, expressive: bool = False) -> str:
    s = project.settings
    blob = json.dumps([line.fr.strip(), vkey, round(slot, 2), s.max_rate, s.max_tempo, line.seed, s.match_level,
                       expressive, s.dynamics], ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def expressive_lines(project: Project) -> set[str]:
    """Répliques fortes (cris, colère…) confiées à Chatterbox expressif, dans la limite fixée."""
    s = project.settings
    if not s.expressive or s.expressive_max <= 0:
        return set()
    cb = engines.get_engine("chatterbox")
    if cb is None or not cb.is_ready():
        return set()
    cands = []
    for ln in project.lines:
        person = project.person(ln.person_id)
        if person is None or not dubvoice.voice_mode(project, person).startswith("fastclone"):
            continue
        if ln.intensity >= s.expressive_db and ln.length >= 0.6:
            cands.append(ln)
    cands.sort(key=lambda x: -x.intensity)
    return {ln.id for ln in cands[:s.expressive_max]}


def dub_line(project: Project, index: int, avail: list[float], keys: dict[str, str], job: Job | None = None,
             force: bool = False, expressive: set[str] | None = None) -> bool:
    """Produit et cale la voix française d'une réplique. Renvoie True si l'audio a été (re)fait."""
    line = project.lines[index]
    if line.no_dub:
        line.state, line.message, line.audio = "skip", "Non doublée : la voix d'origine reste.", ""
        return False
    person = project.person(line.person_id)
    if person is None or not line.fr.strip():
        line.state, line.message, line.audio = "error", "Pas de texte français ou pas de personne.", ""
        return False
    vkey = keys.get(person.id) or dubvoice.voice_key(project, person)
    keys[person.id] = vkey
    strong = bool(expressive and line.id in expressive)
    key = _line_key(project, line, avail[index], vkey, strong)
    target = project_io.voices_dir(project) / f"{line.id}.wav"
    if not force and line.audio_key == key and line.audio and project_io.resolve(project, line.audio).exists():
        return False
    voice = dubvoice.voice_profile(project, person)
    if strong:
        # même extrait de voix, mais Chatterbox : intonation plus vive, d'autant plus que la réplique est forte
        gain = min(0.7, max(0.2, (line.intensity - 3.0) / 12.0))
        voice = dataclasses.replace(voice, engine="chatterbox", engine_voice="",
                                    params={"exaggeration": round(0.5 + gain, 2), "cfg_weight": 0.4})
    line.expressive = strong
    lexicon = dubvoice.pronunciations(project)
    # essais : même voix (graine différente), puis voix normale si la voix expressive échoue, puis voix de secours
    plans: list[tuple[VoiceProfile, int | None, str]] = [(voice, (line.seed or None) if k == 0 else (line.seed or 0)
                                                          + 101 * k, "") for k in range(MAX_ATTEMPTS)]
    if strong:
        plans.append((dubvoice.voice_profile(project, person), line.seed or None, ""))
    backup = dubvoice.fallback_profile(project, person, voice)
    if backup is not None:
        plans.append((backup, None, f"voix de secours ({backup.engine_voice or backup.engine})"))
    res, last, note = None, None, ""
    for attempt, (vp, seed, label) in enumerate(plans, 1):
        def synth(rate: float, vp=vp, seed=seed):
            return dubvoice.synthesize(vp, line.fr, rate, seed, lexicon)

        try:
            res = timing.fit(synth, avail[index], project.settings)
            line.attempts, note = attempt, label
            break
        except (Cancelled, ServiceBlocked):
            raise
        except (EngineError, WorkerDied, OSError, ValueError, RuntimeError) as exc:
            last = exc
            if job is not None:
                if job.cancel.is_set():
                    raise Cancelled() from None
                job.log(f"Réplique {index + 1} ({line.start:.1f} s), essai {attempt} : {str(exc)[:160]}")
    if res is None:
        line.attempts = len(plans)
        raise last if last is not None else EngineError("Synthèse impossible.")
    data = audio.resample(res.data, res.sr, mixer.SR)
    gain = 0.0
    if project.settings.match_level or project.settings.dynamics:
        src, _ = speech_source(project)
        orig, osr = refs.read_span(src, line.start, line.end)
        if project.settings.dynamics and not strong:
            data = timing.transfer_dynamics(data, mixer.SR, orig, osr)
        if project.settings.match_level:
            data, gain = timing.match_level(data, mixer.SR, timing.active_rms_db(orig, osr))
    audio.write_audio(target, data, mixer.SR, subtype="PCM_16")
    line.audio = project_io.relative(project, target)
    line.audio_key = key
    line.duration = round(len(data) / mixer.SR, 3)
    line.rate, line.tempo, line.gain_db = round(res.rate, 3), round(res.tempo, 3), round(gain, 1)
    line.state, line.message = res.state, res.message
    if note:
        line.message = (line.message + " " if line.message else "") + f"Produite avec la {note}."
    if res.state == "long" and index + 1 < len(project.lines):
        over = line.start + line.duration - project.lines[index + 1].start
        if over > 0:
            line.message = f"Chevauche la réplique suivante de {over:.1f} s : raccourcis le texte."
    return True


def step_dub(project: Project, job: Job, only: list[str] | None = None, force: bool = False) -> str:
    project.lines.sort(key=lambda x: x.start)
    lines = project.lines
    avail = timing.slots(lines, project.settings, project.video.duration)
    # moteurs prêts ?
    for person in project.people:
        if any(ln.person_id == person.id for ln in lines):
            ok, msg = dubvoice.engine_ready(project, person)
            if not ok:
                raise StepError(f"Voix de {person.name} : {msg}. Installez le moteur dans Moteurs IA ou changez "
                                "le mode de voix dans Personnes.")
    keys: dict[str, str] = {}
    strong = expressive_lines(project)
    idx = [i for i, ln in enumerate(lines) if only is None or ln.id in only]
    made = errors = long_ = 0
    t0 = time.time()
    for n, i in enumerate(idx):
        job.check()
        line = lines[i]
        try:
            if dub_line(project, i, avail, keys, job, force, strong):
                made += 1
        except Cancelled:
            raise
        except ServiceBlocked:
            raise
        except (EngineError, WorkerDied, OSError, ValueError, RuntimeError) as exc:
            if job.cancel.is_set():
                raise Cancelled() from None
            line.state, line.message = "error", f"Échec après {line.attempts or 1} essai(s) : {str(exc)[:360]}"
            line.audio = ""
            errors += 1
            job.log(f"Réplique {i + 1} ({line.start:.1f} s) en échec : la voix d'origine restera audible. {exc}")
        if line.state == "long":
            long_ += 1
        job.line_changed(line.id)
        if job.save and made and made % 25 == 0:  # vidéo longue : rien n'est perdu en cas d'arrêt
            job.save()
        job.progress((n + 1) / max(1, len(idx)), f"Réplique {n + 1} sur {len(idx)}")
    qc.check(project)
    skipped = sum(1 for ln in lines if ln.no_dub)
    msg = f"{made} répliques produites en {time.time() - t0:.0f} s"
    if skipped:
        msg += f", {skipped} laissée(s) en VO"
    if long_:
        msg += f", {long_} trop longue(s) à raccourcir"
    if errors:
        msg += f", {errors} en erreur"
    return msg


def step_mix(project: Project, job: Job) -> str:
    s = project.settings
    placed = []
    for ln in project.lines:
        if ln.audio and ln.state != "error":
            p = project_io.resolve(project, ln.audio)
            if p.exists():
                placed.append(mixer.Placed(ln.start, p))
    if not placed:
        raise StepError("Aucune voix française produite : lancez l'étape « Voix françaises et calage ».")
    separated = s.separate and wf(project, BACKGROUND).exists() and wf(project, VOICE).exists()
    duration = project.video.duration or audio.duration_of(wf(project, ORIGINAL))
    # voix d'origine : remise là où il n'y a pas de VF (filet de sécurité), atténuée sous les répliques doublées
    fallback = wf(project, VOICE) if separated and s.vo_fallback else None
    mixer.mix(wf(project, MIX), duration, placed,
              background=wf(project, BACKGROUND) if separated else None,
              original_voice=wf(project, VOICE) if separated and s.keep_original_voice and not fallback else None,
              original_voice_db=s.original_voice_db,
              fallback_voice=fallback, fallback_under_db=s.original_voice_db if s.keep_original_voice else -60.0,
              duck_original=None if separated else wf(project, ORIGINAL), duck_db=s.no_separation_duck_db,
              voice_only=wf(project, VF_VOICES), progress=lambda f: job.progress(f, "Mixage"), cancel=job.cancel)
    coverage.update(project)
    vo = "voix d'origine remise ailleurs" if fallback is not None or not separated else "silence ailleurs"
    return f"{len(placed)} répliques mixées ({vo})"


STEP_FUNCS = {"extract": step_extract, "subtitles": step_subtitles, "separate": step_separate, "transcribe": step_transcribe,
              "segment": step_segment, "speakers": step_speakers, "translate": step_translate,
              "voices": step_voices, "dub": step_dub, "mix": step_mix}


def run_step(project: Project, step: str, job: Job, save: Callable[[], None] | None = None) -> str:
    job.step = step
    job.save = save
    job.log(f"— {STEP_LABELS[step]} —")
    job.progress(0.0, STEP_LABELS[step])
    # étape interrompue (pas encore faite) : on reprend ; étape déjà faite et relancée : on refait tout
    job.resume = not project.step_done(step)
    project.invalidate_from(step)
    t0 = time.time()
    detail = STEP_FUNCS[step](project, job)
    learn_speed(step, time.time() - t0, project.video.duration, resumed=job.resume)
    project.mark_step(step, True, detail=detail)
    if step in ("segment", "speakers", "translate", "dub"):
        qc.check(project)
    job.progress(1.0, detail)
    job.log(f"{STEP_LABELS[step]} : {detail}")
    if save:
        save()
    return detail


def steps_to_run(project: Project, start: str | None = None) -> list[str]:
    seq = project.active_steps()
    if start is not None:
        return seq[seq.index(start):] if start in seq else []
    return [s for s in seq if not project.step_done(s)]


def run_all(project: Project, job: Job, save: Callable[[], None] | None = None, start: str | None = None) -> None:
    for step in steps_to_run(project, start):
        job.check()
        run_step(project, step, job, save)


# ---------------------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------------------
def export_files(project: Project, job: Job, out_dir: Path | None = None, preview: bool = False) -> list[Path]:
    """Vidéo doublée (MP4/MKV), fichiers SRT, piste VF seule. ``preview`` : rapide, sans normalisation.

    En mode « sous-titres seuls » : vidéo avec le son d'origine et les sous-titres français (VOSTFR)."""
    o = project.export
    vostfr = project.settings.subtitles_only
    mix_path = wf(project, MIX)
    if vostfr:
        if not project.step_done("translate"):
            raise StepError("La traduction n'est pas faite : lancez « Créer les sous-titres automatiquement ».")
        if preview:
            raise StepError("L'aperçu rapide sert à écouter la VF : il n'existe pas en mode « sous-titres seuls ».")
    elif not mix_path.exists() or not project.step_done("mix"):
        raise StepError("Le mixage n'est pas fait : lancez « Créer la VF automatiquement » ou l'étape Mixage.")
    job.step = "export"
    out_dir = Path(out_dir or project_io.default_export_dir(project))
    out_dir.mkdir(parents=True, exist_ok=True)
    base = project_io.safe_name(project.display_title)
    files: list[Path] = []
    srt_fr = srt_en = None
    want_fr = o.subtitles_fr or o.burn_subtitles or vostfr  # sous-titres seuls : toujours dans la vidéo
    if not preview:
        colors = subtitles.person_colors(project)
        srt_dir = out_dir if o.srt_files else project_io.work_dir(project)
        if want_fr or o.srt_files:
            srt_fr = subtitles.write_srt(project.lines, srt_dir / f"{base}.fr.srt", "fr", colors)
        if o.subtitles_en or o.srt_files:
            srt_en = subtitles.write_srt(project.lines, srt_dir / f"{base}.{project.settings.language}.srt", "orig",
                                         colors)
        if o.srt_files:
            files += [p for p in (srt_fr, srt_en) if p is not None]
        # ASS stylé : piste ASS dans les MKV (le MP4 n'accepte que des sous-titres simples) et incrustation
        if o.ass_subtitles and (o.container == "mkv" or o.burn_subtitles):
            v, wd = project.video, project_io.work_dir(project)
            if srt_fr is not None:
                srt_fr = subtitles.write_ass(project.lines, project.people, wd / "sous-titres.fr.ass", "fr", colors,
                                             v.width, v.height, project.display_title)
            if srt_en is not None and o.container == "mkv":
                srt_en = subtitles.write_ass(project.lines, project.people,
                                             wd / f"sous-titres.{project.settings.language}.ass", "orig", colors,
                                             v.width, v.height, project.display_title)
    ext = ".mkv" if o.container == "mkv" else ".mp4"
    suffix = "VOSTFR" if vostfr else "VF"
    target = (project_io.work_dir(project) / f"apercu{ext}") if preview else out_dir / f"{base} ({suffix}){ext}"
    media.export_video(Path(project.source_video), None if vostfr else mix_path, target, o, project.video.duration,
                       project.video.height or 1080,
                       srt_fr=None if preview else (srt_fr if want_fr else None),
                       srt_en=None if preview else (srt_en if o.subtitles_en else None),
                       original_codec=project.video.audio_codec, normalize=False if preview else None,
                       original_language=project.settings.language,
                       progress=lambda f: job.progress(f * (0.85 if o.audio_only and not preview and not vostfr
                                                            else 1.0),
                                                       "Préparation de la vidéo"),
                       cancel=job.cancel)
    files.insert(0, target)
    if o.audio_only in ("wav", "mp3") and not preview and not vostfr:
        files.append(media.export_audio(mix_path, out_dir / f"{base} (VF).{o.audio_only}", o.normalize,
                                        project.video.duration, cancel=job.cancel))
    job.progress(1.0, "Export terminé")
    if not preview:
        project.last_export = str(target)
    return files


# ---------------------------------------------------------------------------------------
# Temps de calcul : estimation apprise sur cet ordinateur
# ---------------------------------------------------------------------------------------
# secondes de calcul par seconde de vidéo, mesurées sur un portable 4 cœurs sans carte graphique
DEFAULT_SPEED = {"extract": 0.01, "subtitles": 0.02, "separate": 0.40, "transcribe": 0.13, "segment": 0.001, "speakers": 0.03,
                 "translate": 0.08, "voices": 0.005, "dub": 1.10, "mix": 0.01, "export": 0.02}


def learn_speed(step: str, seconds: float, duration: float, resumed: bool = False) -> None:
    """Moyenne glissante du rapport calcul / durée de la vidéo (étapes complètes de plus de 2 min de vidéo)."""
    if duration < 120 or resumed or seconds <= 0:
        return
    try:
        from ..config import settings

        speeds = dict(settings().get("speed_factors") or {})
        old = float(speeds.get(step, DEFAULT_SPEED.get(step, 0.05)))
        speeds[step] = round(0.5 * old + 0.5 * seconds / duration, 4)
        settings().set("speed_factors", speeds)
    except Exception:  # noqa: BLE001 - l'estimation ne doit jamais bloquer le doublage
        log.debug("Vitesse non enregistrée", exc_info=True)


def estimate_seconds(project: Project, steps: list[str]) -> float:
    from ..config import settings

    speeds = {**DEFAULT_SPEED, **(settings().get("speed_factors") or {})}
    d = project.video.duration
    total = 0.0
    for s in steps:
        f = float(speeds.get(s, 0.05))
        if s == "dub" and project.lines:  # répliques déjà produites : rien à refaire
            todo = [ln for ln in project.lines if not ln.audio]
            f *= len(todo) / max(1, len(project.lines))
        total += f * d
    if "dub" in steps and project.settings.expressive:
        total += 25.0 * min(project.settings.expressive_max, d / 120.0)  # répliques fortes (Chatterbox)
    return total
