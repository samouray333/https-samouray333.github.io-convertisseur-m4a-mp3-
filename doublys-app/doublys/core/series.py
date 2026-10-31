"""Séries : le casting (personnages, extraits, voix choisies, empreintes vocales), le glossaire et les réglages de
langue sont gardés d'un épisode à l'autre. Dans un nouvel épisode, chaque personne est reconnue grâce à son
empreinte vocale et reçoit automatiquement son nom et sa voix."""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import paths
from ..config import atomic_write_text
from . import project as project_io
from .models import Person, Project, _from_dict, new_id

log = logging.getLogger(__name__)

SERIES_FILE = "serie.json"
MATCH_SIMILARITY = 0.5  # ressemblance minimale (cosinus des empreintes moyennes) pour reconnaître un personnage
GENERIC_NAME = re.compile(r"^P\d+$")


@dataclass
class Character:
    name: str
    id: str = field(default_factory=lambda: new_id("c_"))
    color: str = "#FF6B4A"
    gender: str = ""
    pitch_hz: float = 0.0
    voice_mode: str = ""
    base_voice: str = ""
    params: dict = field(default_factory=dict)
    rvc_model: str = ""
    rvc_index: str = ""
    reference: str = ""  # fichier dans le dossier de la série
    embedding: list = field(default_factory=list)
    episodes: int = 0

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


@dataclass
class Series:
    name: str
    characters: list[Character] = field(default_factory=list)
    glossary: list = field(default_factory=list)
    source_language: str = ""
    translator: str = ""
    whisper_model: str = ""
    voice_mode: str = ""
    no_dub_ranges: list = field(default_factory=list)  # générique, plages « ne pas doubler » (mêmes à chaque épisode)
    ocr_zone: list = field(default_factory=list)  # bande des sous-titres incrustés

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d) -> "Series":
        s = _from_dict(cls, d)
        s.characters = [Character.from_dict(c) for c in d.get("characters", [])]
        return s


def root() -> Path:
    d = paths.config_dir() / "series"
    d.mkdir(parents=True, exist_ok=True)
    return d


def series_dir(name: str) -> Path:
    return root() / project_io.safe_name(name, "Série")


def list_series() -> list[str]:
    out = []
    for f in sorted(root().glob(f"*/{SERIES_FILE}")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")).get("name") or f.parent.name)
        except (OSError, ValueError):
            continue
    return sorted(out, key=str.lower)


def load(name: str) -> Series | None:
    f = series_dir(name) / SERIES_FILE
    if not f.exists():
        return None
    try:
        return Series.from_dict(json.loads(f.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        log.warning("Série illisible %s : %s", f, exc)
        return None


def save(series: Series) -> Path:
    d = series_dir(series.name)
    d.mkdir(parents=True, exist_ok=True)
    atomic_write_text(d / SERIES_FILE, json.dumps(series.to_dict(), indent=1, ensure_ascii=False))
    return d


def delete(name: str) -> None:
    shutil.rmtree(series_dir(name), ignore_errors=True)


def _unit(v) -> np.ndarray | None:
    if not v:
        return None
    a = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(a)
    return a / n if n > 0 else None


def match(people: list[Person], characters: list[Character],
          threshold: float = MATCH_SIMILARITY) -> dict[str, Character]:
    """Personne → personnage, par ressemblance décroissante, chaque personnage au plus une fois."""
    pairs = []
    for p in people:
        a = _unit(p.embedding)
        if a is None:
            continue
        for c in characters:
            b = _unit(c.embedding)
            if b is not None:
                pairs.append((float(a @ b), p.id, c))
    pairs.sort(key=lambda x: -x[0])
    out: dict[str, Character] = {}
    used: set[str] = set()
    for sim, pid, c in pairs:
        if sim < threshold:
            break
        if pid in out or c.id in used:
            continue
        out[pid] = c
        used.add(c.id)
    return out


def apply_to_project(project: Project) -> int:
    """Applique la série au projet (réglages, glossaire, personnages reconnus). Renvoie le nombre de personnages."""
    s = load(project.series) if project.series else None
    if s is None:
        return 0
    st = project.settings
    known = {str(g[0]) for g in st.glossary if g}
    st.glossary = list(st.glossary) + [g for g in s.glossary if g and str(g[0]) not in known]
    found = match(project.people, s.characters)
    d = series_dir(s.name)
    for person in project.people:
        c = found.get(person.id)
        if c is None:
            continue
        person.name, person.color, person.character = c.name, c.color, c.id
        person.voice_mode, person.base_voice, person.params = c.voice_mode, c.base_voice, dict(c.params)
        person.rvc_model, person.rvc_index = c.rvc_model, c.rvc_index
        if c.gender:
            person.gender = c.gender
            person.gender_locked = True  # genre validé dans un épisode précédent : on le garde
        ref = d / c.reference if c.reference else None
        if ref is not None and ref.exists() and project.path is not None:
            target = project_io.references_dir(project) / f"{person.id}-serie.wav"
            shutil.copyfile(ref, target)
            person.reference = project_io.relative(project, target)
            person.reference_source = "file"
    return len(found)


def save_from_project(project: Project, name: str) -> tuple[Series, int]:
    """Enregistre (ou complète) la série avec les personnes nommées du projet. Renvoie (série, nb personnages)."""
    s = load(name) or Series(name=name)
    s.source_language = project.settings.source_language
    s.translator = project.settings.translator
    s.whisper_model = project.settings.whisper_model
    s.voice_mode = project.settings.voice_mode
    s.no_dub_ranges = [list(r) for r in project.no_dub_ranges]
    if project.subs.kind == "ocr" and project.subs.zone and project.subs.zone[1] > project.subs.zone[0]:
        s.ocr_zone = list(project.subs.zone)
    known = {str(g[0]) for g in s.glossary if g}
    s.glossary += [list(g) for g in project.settings.glossary if g and str(g[0]) not in known]
    d = series_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    count = 0
    by_id = {c.id: c for c in s.characters}
    by_name = {c.name.lower(): c for c in s.characters}
    for p in project.people:
        if GENERIC_NAME.match(p.name.strip()) or not p.embedding:
            continue  # personne non nommée : rien à retenir
        c = by_id.get(p.character) or by_name.get(p.name.strip().lower())
        if c is None:
            c = Character(name=p.name.strip())
            s.characters.append(c)
        c.name, c.color, c.gender, c.pitch_hz = p.name.strip(), p.color, p.gender, p.pitch_hz
        c.voice_mode, c.base_voice, c.params = p.voice_mode, p.base_voice, dict(p.params)
        c.rvc_model, c.rvc_index = p.rvc_model, p.rvc_index
        old = _unit(c.embedding)
        new = _unit(p.embedding)
        # l'empreinte s'affine épisode après épisode
        merged = new if old is None else (old * min(c.episodes, 5) + new) / (min(c.episodes, 5) + 1)
        c.embedding = [round(float(v), 4) for v in merged / (np.linalg.norm(merged) + 1e-9)]
        c.episodes += 1
        ref = project_io.resolve(project, p.reference) if p.reference else None
        if ref is not None and ref.exists():
            c.reference = f"{c.id}.wav"
            shutil.copyfile(ref, d / c.reference)
        p.character = c.id
        count += 1
    project.series = name
    save(s)
    return s, count


def apply_settings(project: Project, name: str) -> None:
    """Nouveau projet d'une série : langue, traduction et voix par défaut de la série."""
    s = load(name)
    if s is None:
        return
    project.series = name
    st = project.settings
    if s.source_language:
        st.source_language = s.source_language
    if s.translator:
        st.translator = s.translator
    if s.whisper_model:
        st.whisper_model = s.whisper_model
    if s.voice_mode:
        st.voice_mode = s.voice_mode
    st.glossary = [list(g) for g in s.glossary]
    project.no_dub_ranges = [list(r) for r in s.no_dub_ranges]
    if s.ocr_zone:
        project.subs.zone = list(s.ocr_zone)
