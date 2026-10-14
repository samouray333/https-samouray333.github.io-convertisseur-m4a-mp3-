"""Modèles de données : cours, modules, leçons, voix, réglages de production et d'export.

Pour garder le moteur commun à AudioLivre Studio, une leçon est un « chapitre » (classe ``Chapter``) rattaché à
un module par son champ ``module`` ; les informations du cours sont rangées dans ``BookMetadata``."""

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
    genre: str = "Cours audio"
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
class QuizQuestion:
    question: str
    choices: list[str] = field(default_factory=list)  # vide : question ouverte
    answer: str = ""
    explanation: str = ""

    @classmethod
    def from_dict(cls, d):
        q = _from_dict(cls, d)
        q.choices = [str(c) for c in (q.choices or []) if str(c).strip()]
        return q


@dataclass
class Chapter:
    title: str
    text: str = ""
    id: str = field(default_factory=lambda: new_id("ch_"))
    include: bool = True
    voice_id: str = ""  # vide = voix du narrateur
    announce_title: bool | None = None  # None = réglage du projet
    # leçon de cours
    module: str = ""  # titre du module (les leçons d'un même module se suivent)
    summary: str = ""  # résumé lu en fin de leçon
    quiz: list[QuizQuestion] = field(default_factory=list)  # quiz lu en fin de leçon

    def __post_init__(self):
        self.quiz = [q if isinstance(q, QuizQuestion) else QuizQuestion.from_dict(q) for q in self.quiz or []]

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
    breaths: str = "light"  # respirations entre les phrases : off | light | natural
    natural_pauses: bool = True  # pauses selon la ponctuation, légère variation, respiration entre voix
    chapter_head_ms: int = 1000
    chapter_tail_ms: int = 3000
    speed: float = 0.95  # un peu plus posé qu'une lecture : on écoute pour apprendre
    announce_chapter_titles: bool = True
    normalize_numbers: bool = True
    expand_abbreviations: bool = True
    detect_dialogues: bool = False
    dialogue_voice_id: str = ""
    narrator_reads_incises: bool = True  # « dit-il » lu par le narrateur, pas par la voix de la réplique
    trim_silence: bool = True
    room_tone: bool = True
    room_tone_db: float = -72.0
    mastering_preset: str = "acx"  # voix posée et claire, idéale pour l'écoute studieuse
    denoise: bool = False
    deesser: bool = True
    sample_rate: int = 44100
    asr_check: bool = True  # relecture automatique par Whisper (si installé)
    # cours
    reflection_pause_ms: int = 6000  # durée de « [réflexion] »
    include_summary: bool = True  # lire le résumé en fin de leçon
    include_quiz: bool = True  # lire le quiz en fin de leçon
    quiz_think_ms: int = 5000  # temps laissé pour répondre avant la réponse
    announce_module: bool = True  # « Module 2 : … » avant la première leçon d'un module
    announce_lesson_number: bool = True  # « Leçon 3. » avant le titre
    asr_threshold: float = 0.3

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


EXPORT_FORMATS = {
    "mp3_modules": "MP3 — un dossier par module, un fichier par leçon",
    "module_single": "MP3 — un fichier par module (leçons enchaînées, avec marqueurs)",
    "m4b_modules": "M4B — un fichier par module, une leçon par chapitre (Apple, Smart AudioBook…)",
    "m4b": "M4B — le cours complet, une leçon par chapitre",
    "handout": "Support écrit (HTML imprimable) : texte des leçons, résumés et quiz avec réponses",
    "mp3_chapters": "MP3 — toutes les leçons dans un seul dossier",
    "mp3_single": "MP3 — le cours complet en un fichier avec marqueurs",
    "wav": "WAV — masters 24 bits sans perte",
    "flac": "FLAC — sans perte compressé",
    "opus": "Opus — très compact (lecture en ligne)",
    "subtitles": "Sous-titres synchronisés (SRT et LRC) pour chaque leçon",
    "video": "Vidéo MP4 par leçon pour YouTube (couverture, onde animée, sous-titres)",
}


@dataclass
class ExportSettings:
    formats: list[str] = field(default_factory=lambda: ["mp3_modules", "module_single", "handout"])
    m4b_bitrate: str = "96k"
    mp3_bitrate: str = "128k"
    opus_bitrate: str = "48k"
    output_dir: str = ""
    include_credits: bool = False  # pas de pistes de crédits séparées : la présentation est dans la 1re leçon
    opening_credits: str = "{title}. {subtitle_sentence}Écrit par {author}. Lu par {narrator}."
    closing_credits: str = "Fin. Vous venez d'écouter {title}, écrit par {author}, lu par {narrator}."
    credits_voice_id: str = ""  # vide : voix du narrateur
    make_sample: bool = False
    sample_minutes: float = 3.0
    acx_cover: bool = False
    file_pattern: str = "{lesson:02d} - {title}"
    write_report: bool = True
    intro_music: str = ""  # jingle avant la première piste
    outro_music: str = ""  # jingle après la dernière piste
    jingles_each_module: bool = True  # jingles au début et à la fin de chaque module
    background_music: str = ""  # fond sonore sous la narration des chapitres
    background_level_db: float = -20.0  # niveau du fond sonore par rapport à la voix

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
        return "Cours sans titre"

    def included_chapters(self) -> list[Chapter]:
        return [c for c in self.chapters if c.include and c.text.strip()]

    def word_count(self) -> int:
        return sum(c.word_count() for c in self.included_chapters())

    def estimated_minutes(self, wpm: float = 155.0) -> float:
        speed = self.production.speed or 1.0
        return self.word_count() / (wpm * speed)

    def modules(self) -> list[tuple[str, list[Chapter]]]:
        """Modules dans l'ordre des leçons incluses : [(titre, leçons)] ; titre vide = leçons hors module."""
        out: list[tuple[str, list[Chapter]]] = []
        for c in self.included_chapters():
            if out and out[-1][0] == c.module:
                out[-1][1].append(c)
            else:
                out.append((c.module, [c]))
        return out

    def module_number(self, chapter: Chapter) -> int:
        """Numéro (1, 2…) du module de la leçon ; 0 si elle n'appartient à aucun module."""
        n = 0
        for title, lessons in self.modules():
            if title:
                n += 1
            if any(c.id == chapter.id for c in lessons):
                return n if title else 0
        return 0

    def lesson_number(self, chapter: Chapter) -> int:
        """Numéro de la leçon dans son module (ou dans le cours, hors module)."""
        for title, lessons in self.modules():
            for i, c in enumerate(lessons, 1):
                if c.id == chapter.id:
                    if title:
                        return i
                    return 1 + sum(1 for x in self.included_chapters()[:self.included_chapters().index(c)]
                                   if not x.module)
        return 0

    def first_of_module(self, chapter: Chapter) -> bool:
        return any(lessons[0].id == chapter.id for title, lessons in self.modules() if title)

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
