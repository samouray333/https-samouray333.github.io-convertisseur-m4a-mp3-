"""Voix française de chaque personne : choix du moteur, de la voix de base et synthèse d'une réplique."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

from .. import paths
from . import audio, engines, project as project_io
from .engines import EngineError
from .models import DEFAULT_VOICE_MODE, VOICE_MODES, Person, Project, VoiceProfile
from .textproc import NormalizeOptions, normalize_for_speech

KOKORO_FR = "kokoro:ff_siwis"
EDGE_BY_GENDER = {"M": "fr-FR-HenriNeural", "F": "fr-FR-DeniseNeural", "": "fr-FR-RemyMultilingualNeural"}
EDGE_CHOICES = [("fr-FR-HenriNeural", "Henri (homme)"), ("fr-FR-DeniseNeural", "Denise (femme)"),
                ("fr-FR-RemyMultilingualNeural", "Rémy (homme)"), ("fr-FR-VivienneMultilingualNeural",
                                                                   "Vivienne (femme)"),
                ("fr-FR-EloiseNeural", "Éloïse (jeune femme)"), ("fr-CA-JeanNeural", "Jean (Québec)"),
                ("fr-CA-SylvieNeural", "Sylvie (Québec)"), ("fr-BE-GerardNeural", "Gérard (Belgique)"),
                ("fr-CH-ArianeNeural", "Ariane (Suisse)")]
KOKORO_CHOICES = [("ff_siwis", "Siwis (française)")]


def voice_mode(project: Project, person: Person) -> str:
    mode = person.voice_mode or project.settings.voice_mode or DEFAULT_VOICE_MODE
    return mode if mode in VOICE_MODES else DEFAULT_VOICE_MODE


def engine_for_mode(mode: str) -> str:
    return VOICE_MODES.get(mode, VOICE_MODES[DEFAULT_VOICE_MODE])[1]


def needs_reference(mode: str) -> bool:
    return mode in ("fastclone_offline", "fastclone_ms", "xtts", "chatterbox")


def base_choices(mode: str) -> list[tuple[str, str]]:
    """Voix de base proposées pour un mode : [(identifiant, libellé)] ; « » = automatique selon le genre."""
    auto = [("", "Automatique (selon la voix d'origine)")]
    if mode == "fastclone_offline":
        return [("", "Siwis (Kokoro, hors ligne)")]
    if mode in ("fastclone_ms", "edge"):
        return auto + EDGE_CHOICES
    if mode == "rvc":
        return auto + [(KOKORO_FR, "Siwis (Kokoro, hors ligne)")] + EDGE_CHOICES
    if mode == "kokoro":
        return KOKORO_CHOICES
    if mode == "sapi":
        eng = engines.get_engine("sapi")
        try:
            voices = eng.list_builtin_voices() if eng is not None and eng.is_ready() else []
        except Exception:
            voices = []
        return auto + [(v.id, v.name) for v in voices]
    return [("", "—")]


def reference_path(project: Project, person: Person) -> Path | None:
    if not person.reference:
        return None
    p = project_io.resolve(project, person.reference)
    return p if p.exists() else None


def voice_profile(project: Project, person: Person) -> VoiceProfile:
    mode = voice_mode(project, person)
    engine = engine_for_mode(mode)
    ref = reference_path(project, person)
    refs = [str(ref)] if ref is not None and needs_reference(mode) else []
    if needs_reference(mode) and not refs:
        raise EngineError(f"{person.name} n'a pas encore d'extrait de voix : lancez l'étape « Voix des personnes » "
                          "ou choisissez un fichier dans la page Personnes.")
    base = person.base_voice
    if mode == "fastclone_offline":
        base = KOKORO_FR
    elif mode in ("fastclone_ms", "edge") and not base:
        base = EDGE_BY_GENDER.get(person.gender, EDGE_BY_GENDER[""])
    elif mode == "rvc":
        base = base or EDGE_BY_GENDER.get(person.gender, EDGE_BY_GENDER[""])
        refs = [p for p in (person.rvc_model, person.rvc_index) if p]
        if not person.rvc_model:
            raise EngineError(f"Choisissez le modèle .pth de {person.name} (page Personnes).")
    elif mode == "kokoro":
        base = (base or "ff_siwis").replace("kokoro:", "")
    elif mode == "sapi" and not base:
        eng = engines.get_engine("sapi")
        voices = eng.list_builtin_voices() if eng is not None and eng.is_ready() else []
        fr = [v for v in voices if v.language == "fr"] or voices
        pick = next((v for v in fr if person.gender and v.gender == person.gender), fr[0] if fr else None)
        base = pick.id if pick else ""
    elif mode == "chatterbox":
        base = ""
    return VoiceProfile(name=person.name, engine=engine, kind="clone" if refs else "builtin", engine_voice=base,
                        language="fr", gender=person.gender, references=refs, params=dict(person.params or {}))


def voice_key(project: Project, person: Person) -> str:
    """Empreinte de la voix : la changer refait les répliques de cette personne."""
    from ..config import settings

    v = voice_profile(project, person)
    refs = []
    for r in v.references:
        try:
            st = Path(r).stat()
            refs.append([Path(r).name, st.st_size, int(st.st_mtime)])
        except OSError:
            refs.append([r, 0, 0])
    blob = json.dumps([voice_mode(project, person), v.engine, v.engine_voice, v.params, refs,
                       settings().get("fastclone_mode", "fast")], sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def speech_text(text: str) -> str:
    return normalize_for_speech(text, NormalizeOptions(language="fr"))


def synthesize(voice: VoiceProfile, text: str, rate: float = 1.0, seed: int | None = None) -> tuple[np.ndarray, int]:
    """Synthèse d'un texte français → (mono float32, fréquence)."""
    eng = engines.get_engine(voice.engine)
    if eng is None:
        raise EngineError(f"Moteur « {voice.engine} » indisponible.")
    spoken = speech_text(text)
    if not spoken:
        raise EngineError("Texte français vide.")
    with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
        out = eng.synthesize(spoken, voice, Path(td) / "replique.wav", "fr", speed=rate, seed=seed)
        data, sr = audio.read_audio(out)
    return data, sr


def engine_ready(project: Project, person: Person) -> tuple[bool, str]:
    mode = voice_mode(project, person)
    eng = engines.get_engine(engine_for_mode(mode))
    if eng is None:
        return False, "moteur absent"
    st, msg = eng.status()
    if st != engines.READY:
        return False, msg
    if mode == "fastclone_offline" and not engines.get_engine("kokoro").is_ready():
        return False, "Kokoro (voix de base hors ligne) n'est pas installé"
    return True, msg
