"""Modèles de données : cours de langue, modules, leçons (vocabulaire, phrases, exercices, quiz), intervenants,
révisions espacées, voix, réglages de production et d'export.

Pour garder le moteur commun à AudioLivre Studio, une leçon est un « chapitre » (classe ``Chapter``) rattaché à un
module par son champ ``module`` ; les informations du cours sont rangées dans ``BookMetadata`` (``language`` est la
langue d'explication, ``target_language`` la langue apprise)."""

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
    genre: str = "Cours de langue"
    language: str = "fr"  # langue d'explication (consignes, traductions)
    description: str = ""
    copyright: str = ""
    series: str = ""
    series_index: str = ""
    isbn: str = ""
    cover_path: str = ""
    # cours de langue
    target_language: str = "en"  # langue apprise
    target_locale: str = ""  # accent préféré (« en-GB », « es-MX »…) ; vide : celui proposé par défaut
    level: str = "A1"  # niveau du cadre européen (A1 à C2)

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
class VocabItem:
    """Mot ou phrase de la leçon, dans la langue apprise, avec sa traduction dans la langue d'explication."""
    term: str
    translation: str = ""
    translit: str = ""  # translittération (pinyin, romaji…) pour les écritures non latines
    example: str = ""  # phrase d'exemple dans la langue apprise
    example_translation: str = ""
    notes: str = ""  # genre, pluriel, registre…
    kind: str = "word"  # word | phrase
    favorite: bool = False
    id: str = field(default_factory=lambda: new_id("w_"))

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
LEVEL_LABELS = {"A1": "A1 — Débutant", "A2": "A2 — Élémentaire", "B1": "B1 — Intermédiaire",
                "B2": "B2 — Intermédiaire avancé", "C1": "C1 — Avancé", "C2": "C2 — Maîtrise"}
# Exercices audio d'une leçon
EXERCISES = {
    "repeat": "Écoutez puis répétez (silence pour répéter, puis la bonne prononciation)",
    "slow_normal": "Lecture lente puis normale des phrases",
    "translation": "Traduction différée (le mot en français, un silence, puis la réponse)",
    "dictation": "Dictée (phrase lue lentement deux fois, temps pour écrire)",
    "comprehension": "Questions de compréhension après le texte",
}
DEFAULT_EXERCISES = ["repeat", "slow_normal", "translation", "comprehension"]


@dataclass
class Chapter:
    title: str
    text: str = ""
    id: str = field(default_factory=lambda: new_id("ch_"))
    include: bool = True
    voice_id: str = ""  # vide = voix du narrateur
    announce_title: bool | None = None  # None = réglage du projet
    # leçon de cours (modules, résumé et quiz)
    module: str = ""  # titre du module (les leçons d'un même module se suivent)
    summary: str = ""  # résumé lu en fin de leçon
    quiz: list[QuizQuestion] = field(default_factory=list)  # quiz lu en fin de leçon
    # leçon de langue
    target_language: str = ""  # vide : langue apprise du cours
    target_locale: str = ""  # vide : accent du cours
    level: str = ""  # vide : niveau du cours
    theme: str = ""  # se présenter, restaurant, voyage…
    vocab: list[VocabItem] = field(default_factory=list)  # mots (et phrases utiles, kind « phrase »)
    questions: list[QuizQuestion] = field(default_factory=list)  # compréhension, posées après le texte
    exercises: list[str] | None = None  # None : exercices réglés dans Production
    description: str = ""  # présentation courte (étiquettes MP3)

    def __post_init__(self):
        self.quiz = [q if isinstance(q, QuizQuestion) else QuizQuestion.from_dict(q) for q in self.quiz or []]
        self.questions = [q if isinstance(q, QuizQuestion) else QuizQuestion.from_dict(q)
                          for q in self.questions or []]
        self.vocab = [v if isinstance(v, VocabItem) else VocabItem.from_dict(v) for v in self.vocab or []]

    def words(self) -> list[VocabItem]:
        return [v for v in self.vocab if v.kind != "phrase" and v.term.strip()]

    def phrases(self) -> list[VocabItem]:
        return [v for v in self.vocab if v.kind == "phrase" and v.term.strip()]

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)

    def word_count(self) -> int:
        return len(self.text.split())


HOST_ROLES = {"host": "Professeur·e", "cohost": "Co-animateur·rice", "guest": "Personnage (dialogues)",
              "voiceover": "Voix off"}


@dataclass
class Host:
    """Personne qui parle dans les leçons : ses répliques s'écrivent « @Nom: … » dans le script.

    Sans voix choisie, une voix native de sa langue (et de son sexe) lui est attribuée automatiquement."""
    name: str
    role: str = "guest"  # host | cohost | guest | voiceover
    voice_id: str = ""  # vide : voix native automatique
    bio: str = ""  # présentation (aide l'assistant IA à écrire le dialogue)
    pan: float | None = None  # position stéréo -1 (gauche) … 1 (droite) ; None = automatique
    language: str = ""  # vide : langue apprise de la leçon
    gender: str = ""  # F | M | « » (indifférent)
    id: str = field(default_factory=lambda: new_id("h_"))

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)

    @property
    def role_label(self) -> str:
        return HOST_ROLES.get(self.role, self.role)


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
    "streaming": "Écoute nomade -16 LUFS (recommandé : téléphone, voiture)",
    "acx": "Voix posée (normes ACX / Audible)",
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
    speed: float = 1.0  # débit de la voix d'explication
    announce_chapter_titles: bool = True
    normalize_numbers: bool = True
    expand_abbreviations: bool = True
    detect_dialogues: bool = False
    dialogue_voice_id: str = ""
    narrator_reads_incises: bool = True  # « dit-il » lu par le narrateur, pas par la voix de la réplique
    trim_silence: bool = True
    room_tone: bool = True
    room_tone_db: float = -72.0
    mastering_preset: str = "streaming"
    denoise: bool = False
    deesser: bool = True
    sample_rate: int = 44100
    asr_check: bool = True  # relecture automatique par Whisper (si installé)
    stereo: bool = True  # chaque intervenant placé à gauche ou à droite, comme en studio
    stereo_width: float = 0.35  # écart stéréo des intervenants (0 = centre, 1 = complètement sur le côté)
    overlap_reactions: bool = False  # réactions courtes (« Ah oui ! ») lancées par-dessus la fin de la réplique
    overlap_ms: int = 450  # durée du chevauchement
    asr_threshold: float = 0.3
    # cours (modules, réflexion, résumé, quiz)
    reflection_pause_ms: int = 6000  # durée de « [réflexion] »
    include_summary: bool = True
    include_quiz: bool = True
    quiz_think_ms: int = 5000  # temps laissé pour répondre avant la réponse
    announce_module: bool = True
    announce_lesson_number: bool = True
    # langues
    target_speed: float = 0.95  # débit des voix natives (un peu posé pour mieux entendre)
    slow_rate: float = 0.72  # « lecture lente » des exercices
    exercises: list[str] = field(default_factory=lambda: list(DEFAULT_EXERCISES))
    include_vocabulary: bool = True  # section « Vocabulaire » lue avant le texte de la leçon
    include_phrases: bool = True  # section « Phrases utiles »
    repeat_factor: float = 1.6  # silence pour répéter = 1,6 × durée du mot
    translation_think_ms: int = 3500  # temps pour trouver la traduction
    dictation_pause_ms: int = 9000  # temps pour écrire une phrase de la dictée
    native_offline: str = "fallback"  # voix hors ligne : fallback (si Microsoft injoignable) | prefer | none

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


EXPORT_FORMATS = {
    "mp3_modules": "MP3 — un dossier par module, un fichier par leçon (étiquettes et chapitres)",
    "module_single": "MP3 — un fichier par module (leçons enchaînées, avec chapitres)",
    "reviews": "Révisions — un MP3 par séance programmée (J+1, J+3, J+7, J+14, J+30)",
    "anki": "Anki (CSV) avec l'audio de chaque mot et de chaque phrase",
    "flashcards": "Flashcards imprimables (recto : la langue apprise, verso : la traduction)",
    "handout": "Support écrit (HTML) : traductions, translittérations et réponses des exercices",
    "mp3_chapters": "MP3 — toutes les leçons dans un seul dossier",
    "mp3_single": "MP3 — le cours complet en un fichier avec chapitres",
    "m4b": "M4B — le cours complet, une leçon par chapitre",
    "wav": "WAV — masters 24 bits sans perte",
    "flac": "FLAC — sans perte compressé",
    "opus": "Opus — très compact (lecture en ligne)",
    "subtitles": "Sous-titres synchronisés (SRT et LRC) pour chaque leçon",
    "video": "Vidéo MP4 par leçon pour YouTube (couverture, onde animée, sous-titres)",
}


@dataclass
class ExportSettings:
    formats: list[str] = field(default_factory=lambda: ["mp3_modules", "module_single", "reviews", "anki",
                                                         "flashcards", "handout"])
    m4b_bitrate: str = "96k"
    mp3_bitrate: str = "128k"
    mp3_stereo: bool = False
    opus_bitrate: str = "48k"
    output_dir: str = ""
    include_credits: bool = False  # pas de pistes de crédits séparées : la présentation est dans la 1re leçon
    opening_credits: str = "{title}. {subtitle_sentence}Écrit par {author}. Lu par {narrator}."
    closing_credits: str = "Fin. Vous venez d'écouter {title}, écrit par {author}, lu par {narrator}."
    credits_voice_id: str = ""  # vide : voix du narrateur
    make_sample: bool = False
    sample_minutes: float = 3.0
    acx_cover: bool = False  # couverture 3000 × 3000 au lieu de 1400
    file_pattern: str = "{lesson:02d} - {title}"
    write_report: bool = True
    intro_music: str = ""  # jingle d'ouverture
    outro_music: str = ""  # jingle de fin
    jingles_each_module: bool = True  # jingles au début et à la fin de chaque module
    review_days: int = 30  # séances de révision exportées : celles des N prochains jours
    background_music: str = ""  # fond sonore sous la narration des chapitres
    background_level_db: float = -20.0  # niveau du fond sonore par rapport à la voix

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


REVIEW_STEPS = [1, 3, 7, 14, 30]  # jours entre deux révisions (J+1, J+3, J+7, J+14, J+30)


@dataclass
class ReviewState:
    """Où en est un mot ou une phrase dans la répétition espacée."""
    item_id: str
    lesson_id: str
    step: int = 0  # prochaine étape (indice dans REVIEW_STEPS) ; len(REVIEW_STEPS) = acquis
    due: str = ""  # AAAA-MM-JJ de la prochaine révision
    seen: str = ""  # première fois étudié
    last: str = ""  # dernière révision
    history: list[str] = field(default_factory=list)  # dates de révision (« 2026-10-15 » ou « 2026-10-15! »)

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)

    @property
    def learned(self) -> bool:
        return self.step >= len(REVIEW_STEPS)


@dataclass
class Project:
    metadata: BookMetadata = field(default_factory=BookMetadata)
    chapters: list[Chapter] = field(default_factory=list)
    narrator_voice_id: str = ""
    cast: dict[str, str] = field(default_factory=dict)  # personnage -> id de voix
    hosts: list[Host] = field(default_factory=list)  # intervenants des dialogues (voix prioritaires sur ``cast``)
    language_voices: dict[str, list[str]] = field(default_factory=dict)  # langue → voix natives choisies
    reviews: dict[str, ReviewState] = field(default_factory=dict)  # répétition espacée, par mot
    studied: dict[str, str] = field(default_factory=dict)  # leçon → date d'étude
    instructions: dict[str, str] = field(default_factory=dict)  # consignes traduites (langue d'explication)
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
            hosts=[Host.from_dict(h) for h in d.get("hosts", [])],
            language_voices={str(k): [str(x) for x in (v or [])] for k, v in (d.get("language_voices") or {}).items()},
            reviews={k: ReviewState.from_dict(v) for k, v in (d.get("reviews") or {}).items()},
            studied=dict(d.get("studied") or {}),
            instructions=dict(d.get("instructions") or {}),
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

    # -- modules et leçons -------------------------------------------------------------
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
        inc = self.included_chapters()
        for title, lessons in self.modules():
            for i, c in enumerate(lessons, 1):
                if c.id == chapter.id:
                    if title:
                        return i
                    return 1 + sum(1 for x in inc[:inc.index(c)] if not x.module)
        return 0

    def first_of_module(self, chapter: Chapter) -> bool:
        return any(lessons[0].id == chapter.id for title, lessons in self.modules() if title)

    # -- langues -----------------------------------------------------------------------
    def target_of(self, chapter: Chapter | None) -> tuple[str, str]:
        """(langue apprise, accent) d'une leçon : les siens, sinon ceux du cours."""
        lang = (chapter.target_language if chapter else "") or self.metadata.target_language or "en"
        if chapter and chapter.target_language and chapter.target_language != self.metadata.target_language:
            locale = chapter.target_locale
        else:
            locale = (chapter.target_locale if chapter else "") or self.metadata.target_locale
        return lang, locale

    def level_of(self, chapter: Chapter | None) -> str:
        return (chapter.level if chapter else "") or self.metadata.level or "A1"

    def exercises_of(self, chapter: Chapter | None) -> list[str]:
        if chapter is not None and chapter.exercises is not None:
            return list(chapter.exercises)
        return list(self.production.exercises)

    def all_vocab(self) -> list[tuple[Chapter, VocabItem]]:
        return [(c, v) for c in self.chapters for v in c.vocab if v.term.strip()]

    def vocab_by_id(self, item_id: str) -> tuple[Chapter, VocabItem] | tuple[None, None]:
        for c in self.chapters:
            for v in c.vocab:
                if v.id == item_id:
                    return c, v
        return None, None

    def host_pan(self, name: str | None) -> float:
        """Position stéréo d'un intervenant : la sienne, sinon alternée gauche / droite selon la liste."""
        if not name:
            return 0.0
        host = self.host_by_name(name)
        if host is None:
            return 0.0
        if host.pan is not None:
            return max(-1.0, min(1.0, host.pan))
        if len(self.hosts) == 1:
            return 0.0
        idx = self.hosts.index(host)
        pattern = [-1.0, 1.0, -0.5, 0.5, -0.75, 0.75, 0.0]
        return pattern[idx % len(pattern)] * self.production.stereo_width

    def host_by_name(self, name: str) -> Host | None:
        key = name.strip().lower()
        return next((h for h in self.hosts if h.name.strip().lower() == key), None)

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
