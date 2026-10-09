"""Modèles de données : projet, chapitres, voix, réglages de production et d'export."""

from __future__ import annotations

import dataclasses
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _from_dict(cls, data: dict[str, Any] | None):
    """Construit une dataclass en ignorant les clés inconnues (compatibilité ascendante)."""
    data = data or {}
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class BookMetadata:
    title: str = ""
    subtitle: str = ""
    author: str = ""
    narrator: str = ""
    publisher: str = ""
    year: str = ""
    genre: str = "Livre audio"
    language: str = "fr"
    description: str = ""
    copyright: str = ""
    series: str = ""
    series_index: str = ""
    isbn: str = ""
    cover_path: str = ""

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


@dataclass
class Chapter:
    title: str
    text: str = ""
    id: str = field(default_factory=lambda: new_id("ch_"))
    include: bool = True
    voice_id: str = ""  # vide = voix du narrateur
    announce_title: bool | None = None  # None = réglage du projet

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)

    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class LexiconEntry:
    pattern: str
    replacement: str
    regex: bool = False
    case_sensitive: bool = False
    whole_word: bool = True
    enabled: bool = True
    note: str = ""

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


MASTERING_PRESETS = {
    "acx": "ACX / Audible (recommandé)",
    "streaming": "Streaming / Podcast (-16 LUFS)",
    "natural": "Naturel (traitement léger)",
    "none": "Aucun traitement",
}


@dataclass
class ProductionSettings:
    pause_sentence_ms: int = 350
    pause_paragraph_ms: int = 850
    pause_heading_ms: int = 1300
    chapter_head_ms: int = 1000
    chapter_tail_ms: int = 3000
    speed: float = 1.0
    announce_chapter_titles: bool = True
    normalize_numbers: bool = True
    expand_abbreviations: bool = True
    detect_dialogues: bool = False
    dialogue_voice_id: str = ""
    trim_silence: bool = True
    room_tone: bool = True
    room_tone_db: float = -72.0
    mastering_preset: str = "acx"
    denoise: bool = False
    deesser: bool = True
    sample_rate: int = 44100

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


EXPORT_FORMATS = {
    "m4b": "M4B — livre audio avec chapitres (Apple Books, Smart AudioBook…)",
    "mp3_chapters": "MP3 — un fichier par chapitre (ACX / Audible : 192 kb/s, 44,1 kHz)",
    "mp3_single": "MP3 — fichier unique avec marqueurs de chapitres",
    "wav": "WAV — masters 24 bits sans perte",
    "flac": "FLAC — sans perte compressé",
    "opus": "Opus — très compact (lecture en ligne)",
}


@dataclass
class ExportSettings:
    formats: list[str] = field(default_factory=lambda: ["m4b", "mp3_chapters"])
    m4b_bitrate: str = "96k"
    mp3_bitrate: str = "192k"
    opus_bitrate: str = "48k"
    output_dir: str = ""
    include_credits: bool = True
    opening_credits: str = "{title}. {subtitle_sentence}Écrit par {author}. Lu par {narrator}."
    closing_credits: str = "Fin. Vous venez d'écouter {title}, écrit par {author}, lu par {narrator}."
    make_sample: bool = True
    sample_minutes: float = 3.0
    acx_cover: bool = True
    file_pattern: str = "{index:02d} - {title}"
    write_report: bool = True

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


@dataclass
class Project:
    metadata: BookMetadata = field(default_factory=BookMetadata)
    chapters: list[Chapter] = field(default_factory=list)
    narrator_voice_id: str = ""
    cast: dict[str, str] = field(default_factory=dict)  # personnage -> id de voix
    lexicon: list[LexiconEntry] = field(default_factory=list)
    production: ProductionSettings = field(default_factory=ProductionSettings)
    export: ExportSettings = field(default_factory=ExportSettings)
    source_file: str = ""
    id: str = field(default_factory=lambda: new_id("prj_"))
    created: str = field(default_factory=now_iso)
    modified: str = field(default_factory=now_iso)
    format_version: int = 1
    # non sérialisé
    path: Path | None = field(default=None, compare=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d.pop("path", None)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        p = cls(
            metadata=BookMetadata.from_dict(d.get("metadata")),
            chapters=[Chapter.from_dict(c) for c in d.get("chapters", [])],
            narrator_voice_id=d.get("narrator_voice_id", ""),
            cast=dict(d.get("cast", {})),
            lexicon=[LexiconEntry.from_dict(e) for e in d.get("lexicon", [])],
            production=ProductionSettings.from_dict(d.get("production")),
            export=ExportSettings.from_dict(d.get("export")),
            source_file=d.get("source_file", ""),
        )
        for key in ("id", "created", "modified", "format_version"):
            if key in d:
                setattr(p, key, d[key])
        return p

    @property
    def display_title(self) -> str:
        if self.metadata.title:
            return self.metadata.title
        if self.path:
            return self.path.stem
        return "Projet sans titre"

    def included_chapters(self) -> list[Chapter]:
        return [c for c in self.chapters if c.include and c.text.strip()]

    def word_count(self) -> int:
        return sum(c.word_count() for c in self.included_chapters())

    def estimated_minutes(self, wpm: float = 155.0) -> float:
        speed = self.production.speed or 1.0
        return self.word_count() / (wpm * speed)

    def chapter_by_id(self, chapter_id: str) -> Chapter | None:
        for c in self.chapters:
            if c.id == chapter_id:
                return c
        return None


@dataclass
class VoiceProfile:
    name: str
    engine: str  # edge | sapi | xtts | chatterbox | kokoro
    kind: str = "builtin"  # builtin | clone | blend
    engine_voice: str = ""
    language: str = "fr"
    gender: str = ""
    description: str = ""
    references: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    color: str = "#7C5CFF"
    favorite: bool = False
    consent: bool = False
    id: str = field(default_factory=lambda: new_id("v_"))
    created: str = field(default_factory=now_iso)
    # non sérialisé : dossier de la voix
    dir: Path | None = field(default=None, compare=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d.pop("dir", None)
        return d

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)

    def reference_paths(self) -> list[Path]:
        if not self.dir:
            return [Path(r) for r in self.references]
        return [(self.dir / r) if not Path(r).is_absolute() else Path(r) for r in self.references]

    @property
    def is_clone(self) -> bool:
        return self.kind == "clone"
