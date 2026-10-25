"""Chaîne de doublage : chaque étape lit et écrit dans le dossier de travail du projet et peut être relancée seule.

extraction → séparation → transcription → répliques → personnes → traduction → voix → doublage → mixage → export
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import ai, audio, dubvoice, engines, media, mixer, refs, segment, speakers, subtitles, timing
from . import project as project_io
from .engines import EngineError, ServiceBlocked
from .engines.neural import WorkerDied
from .ffmpeg import Cancelled
from .models import STEP_LABELS, STEPS, TRANSLATORS, Line, Project

log = logging.getLogger(__name__)

ORIGINAL = "original.wav"
ORIGINAL16 = "original16.wav"
VOICE = "voix.wav"
VOICE16 = "voix16.wav"
BACKGROUND = "fond.wav"
TRANSCRIPT = "transcription.json"
MIX = "vf_mix.wav"
VF_VOICES = "vf_voix.wav"


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
        label = {"analysis": "Analyse (voix, personnes, traduction)", "whisper": "Whisper (transcription)"}[name]
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
    media.extract_audio(src, wf(project, ORIGINAL), wf(project, ORIGINAL16), project.video.duration,
                        progress=lambda f: job.progress(f, "Extraction du son"), cancel=job.cancel)
    return f"{project.video.duration / 60:.1f} min de son extrait"


def step_separate(project: Project, job: Job) -> str:
    tool = _tool("analysis")
    t0 = time.time()
    job.progress(0.0, "Chargement de Demucs…")
    _guard(job, tool.separate, wf(project, ORIGINAL), wf(project, VOICE), wf(project, BACKGROUND),
           on_progress=lambda v, m: job.progress(v, m))
    job.check()
    media.to_mono16(wf(project, VOICE), wf(project, VOICE16), job.cancel)
    return f"voix et fond séparés en {time.time() - t0:.0f} s"


def step_transcribe(project: Project, job: Job) -> str:
    tool = _tool("whisper")
    _voice, voice16 = speech_source(project)
    job.progress(0.0, f"Chargement de Whisper « {project.settings.whisper_model} »…")
    res = _guard(job, tool.transcribe_words, voice16, project.settings.source_language,
                 project.settings.whisper_model, on_progress=lambda v, m: job.progress(v, m))
    wf(project, TRANSCRIPT).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    words = res.get("words", [])
    if not words:
        raise StepError("Whisper n'a reconnu aucune parole dans cette vidéo.")
    return f"{len(words)} mots reconnus"


def load_transcript(project: Project) -> dict:
    p = wf(project, TRANSCRIPT)
    if not p.exists():
        raise StepError("Transcription absente : relancez l'étape « Transcription ».")
    return json.loads(p.read_text(encoding="utf-8"))


def step_segment(project: Project, job: Job) -> str:
    s = project.settings
    words = load_transcript(project).get("words", [])
    lines = segment.lines_from_words(words, s.pause_split, s.max_line, s.min_fragment)
    # personnes déjà connues : chaque nouvelle réplique reprend celle de l'ancienne réplique qui la recouvre
    old = project.lines
    for ln in lines:
        best = max(old, key=lambda o: min(o.end, ln.end) - max(o.start, ln.start), default=None)
        if best is not None and min(best.end, ln.end) > max(best.start, ln.start):
            ln.person_id = best.person_id
    project.lines = lines
    job.progress(1.0)
    return f"{len(lines)} répliques"


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
    return f"{len(project.people)} personne(s)"


def step_translate(project: Project, job: Job, only: list[str] | None = None, force: bool = False) -> str:
    s = project.settings
    lines = sorted(project.lines, key=lambda x: x.start)
    project.lines = lines
    avail = timing.slots(lines, s, project.video.duration)
    todo = [i for i, ln in enumerate(lines) if (only is None or ln.id in only) and (force or not ln.fr_edited)
            and ln.en.strip()]
    if not todo:
        return "rien à traduire"
    if s.translator == "deepseek":
        client = ai.client_from_settings()
        items = [{"en": ln.en, "person": (project.person(ln.person_id).name if project.person(ln.person_id) else ""),
                  "budget": timing.char_budget(avail[i], s.chars_per_second)} for i, ln in enumerate(lines)]
        # tout le contexte est envoyé, seules les répliques demandées sont mises à jour
        if only is not None:
            sub = [items[i] for i in todo]
            res = ai.translate_lines(sub, client, lambda m: job.progress(0.5, m), job.cancel)
            result = dict(zip(todo, res))
        else:
            done = [0]

            def prog(msg):
                done[0] += 1
                job.progress(min(0.99, done[0] * ai.BATCH_LINES / max(1, len(items))), msg)

            res = ai.translate_lines(items, client, prog, job.cancel)
            result = {i: res[i] for i in todo}
    else:
        model = TRANSLATORS.get(s.translator, TRANSLATORS["opus_big"])[1]
        tool = _tool("analysis")
        job.progress(0.0, "Chargement du traducteur…")
        res = _guard(job, tool.translate, [lines[i].en for i in todo], model,
                     on_progress=lambda v, m: job.progress(v, m))
        result = dict(zip(todo, res))
    job.check()
    changed = 0
    for i, fr in result.items():
        if fr and fr != lines[i].fr:
            lines[i].fr = fr
            lines[i].fr_edited = False
            changed += 1
            job.line_changed(lines[i].id)
    return f"{len(result)} répliques traduites"


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
        data, sr = audio.read_audio(ref)
        person.pitch_hz = round(refs.estimate_pitch(data, sr), 1)
        g = refs.gender_from_pitch(person.pitch_hz)
        if g:
            person.gender = g
        job.progress((k + 1) / max(1, len(people)), person.name)
    return f"{len(people)} voix préparée(s)"


def _line_key(project: Project, line: Line, slot: float, vkey: str) -> str:
    s = project.settings
    blob = json.dumps([line.fr.strip(), vkey, round(slot, 2), s.max_rate, s.max_tempo, line.seed, s.match_level],
                      ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def dub_line(project: Project, index: int, avail: list[float], keys: dict[str, str], job: Job | None = None,
             force: bool = False) -> bool:
    """Produit et cale la voix française d'une réplique. Renvoie True si l'audio a été (re)fait."""
    line = project.lines[index]
    person = project.person(line.person_id)
    if person is None or not line.fr.strip():
        line.state, line.message, line.audio = "error", "Pas de texte français ou pas de personne.", ""
        return False
    vkey = keys.get(person.id) or dubvoice.voice_key(project, person)
    keys[person.id] = vkey
    key = _line_key(project, line, avail[index], vkey)
    target = project_io.voices_dir(project) / f"{line.id}.wav"
    if not force and line.audio_key == key and line.audio and project_io.resolve(project, line.audio).exists():
        return False
    voice = dubvoice.voice_profile(project, person)
    seed = line.seed or None

    def synth(rate: float):
        return dubvoice.synthesize(voice, line.fr, rate, seed)

    res = timing.fit(synth, avail[index], project.settings)
    data = audio.resample(res.data, res.sr, mixer.SR)
    gain = 0.0
    if project.settings.match_level:
        src, _ = speech_source(project)
        orig, osr = refs.read_span(src, line.start, line.end)
        data, gain = timing.match_level(data, mixer.SR, timing.active_rms_db(orig, osr))
    audio.write_audio(target, data, mixer.SR, subtype="PCM_16")
    line.audio = project_io.relative(project, target)
    line.audio_key = key
    line.duration = round(len(data) / mixer.SR, 3)
    line.rate, line.tempo, line.gain_db = round(res.rate, 3), round(res.tempo, 3), round(gain, 1)
    line.state, line.message = res.state, res.message
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
    idx = [i for i, ln in enumerate(lines) if only is None or ln.id in only]
    made = errors = long_ = 0
    t0 = time.time()
    for n, i in enumerate(idx):
        job.check()
        line = lines[i]
        try:
            if dub_line(project, i, avail, keys, job, force):
                made += 1
        except Cancelled:
            raise
        except ServiceBlocked:
            raise
        except (EngineError, WorkerDied, OSError, ValueError) as exc:
            if job.cancel.is_set():
                raise Cancelled() from None
            line.state, line.message = "error", str(exc)[:400]
            errors += 1
            job.log(f"Réplique {i + 1} : {exc}")
        if line.state == "long":
            long_ += 1
        job.line_changed(line.id)
        job.progress((n + 1) / max(1, len(idx)), f"Réplique {n + 1} sur {len(idx)}")
    msg = f"{made} répliques produites en {time.time() - t0:.0f} s"
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
    separated = s.separate and wf(project, BACKGROUND).exists()
    duration = project.video.duration or audio.duration_of(wf(project, ORIGINAL))
    mixer.mix(wf(project, MIX), duration, placed,
              background=wf(project, BACKGROUND) if separated else None,
              original_voice=wf(project, VOICE) if separated and s.keep_original_voice else None,
              original_voice_db=s.original_voice_db,
              duck_original=None if separated else wf(project, ORIGINAL), duck_db=s.no_separation_duck_db,
              voice_only=wf(project, VF_VOICES), progress=lambda f: job.progress(f, "Mixage"), cancel=job.cancel)
    return f"{len(placed)} répliques mixées"


STEP_FUNCS = {"extract": step_extract, "separate": step_separate, "transcribe": step_transcribe,
              "segment": step_segment, "speakers": step_speakers, "translate": step_translate,
              "voices": step_voices, "dub": step_dub, "mix": step_mix}


def run_step(project: Project, step: str, job: Job, save: Callable[[], None] | None = None) -> str:
    job.step = step
    job.log(f"— {STEP_LABELS[step]} —")
    job.progress(0.0, STEP_LABELS[step])
    project.invalidate_from(step)
    detail = STEP_FUNCS[step](project, job)
    project.mark_step(step, True, detail=detail)
    job.progress(1.0, detail)
    job.log(f"{STEP_LABELS[step]} : {detail}")
    if save:
        save()
    return detail


def steps_to_run(project: Project, start: str | None = None) -> list[str]:
    seq = [s for s in STEPS if s != "separate" or project.settings.separate]
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
    """Vidéo doublée (MP4/MKV), fichiers SRT, piste VF seule. ``preview`` : rapide, sans normalisation."""
    mix_path = wf(project, MIX)
    if not mix_path.exists() or not project.step_done("mix"):
        raise StepError("Le mixage n'est pas fait : lancez « Créer la VF automatiquement » ou l'étape Mixage.")
    o = project.export
    job.step = "export"
    out_dir = Path(out_dir or project_io.default_export_dir(project))
    out_dir.mkdir(parents=True, exist_ok=True)
    base = project_io.safe_name(project.display_title)
    files: list[Path] = []
    srt_fr = srt_en = None
    if not preview:
        srt_dir = out_dir if o.srt_files else project_io.work_dir(project)
        if o.subtitles_fr or o.srt_files or o.burn_subtitles:
            srt_fr = subtitles.write_srt(project.lines, srt_dir / f"{base}.fr.srt", "fr")
        if o.subtitles_en or o.srt_files:
            srt_en = subtitles.write_srt(project.lines, srt_dir / f"{base}.en.srt", "en")
        if o.srt_files:
            files += [p for p in (srt_fr, srt_en) if p is not None]
    ext = ".mkv" if o.container == "mkv" else ".mp4"
    target = (project_io.work_dir(project) / f"apercu{ext}") if preview else out_dir / f"{base} (VF){ext}"
    media.export_video(Path(project.source_video), mix_path, target, o, project.video.duration,
                       project.video.height or 1080,
                       srt_fr=None if preview else (srt_fr if (o.subtitles_fr or o.burn_subtitles) else None),
                       srt_en=None if preview else (srt_en if o.subtitles_en else None),
                       original_codec=project.video.audio_codec, normalize=False if preview else None,
                       progress=lambda f: job.progress(f * (0.85 if o.audio_only and not preview else 1.0),
                                                       "Préparation de la vidéo"),
                       cancel=job.cancel)
    files.insert(0, target)
    if o.audio_only in ("wav", "mp3") and not preview:
        files.append(media.export_audio(mix_path, out_dir / f"{base} (VF).{o.audio_only}", o.normalize,
                                        project.video.duration, cancel=job.cancel))
    job.progress(1.0, "Export terminé")
    if not preview:
        project.last_export = str(target)
    return files
