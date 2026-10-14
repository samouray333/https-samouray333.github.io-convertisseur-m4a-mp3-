"""Modèles de données : collection d'histoires, histoires, personnages, voix, réglages de production et d'export.

Pour garder le moteur commun à AudioLivre Studio, une histoire est un « chapitre » (classe ``Chapter``) et une
collection (une série d'histoires avec les mêmes personnages) est un projet ; ses informations sont rangées dans
``BookMetadata``."""

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
    genre: str = "Contes pour enfants"
    language: str = "fr"
    description: str = ""
    copyright: str = ""
    series: str = ""
    series_index: str = ""
    isbn: str = ""
    cover_path: str = ""
    child_name: str = ""  # prénom de l'enfant, héros des histoires (« {prénom} » dans le texte)
    # hérités du moteur commun (non utilisés pour les contes)
    website: str = ""
    owner_email: str = ""
    category: str = "Kids & Family"
    explicit: bool = False
    media_base_url: str = ""

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
    # histoire pour enfants
    number: int = 0  # 0 = numéro selon la position dans la collection
    season: int = 0
    description: str = ""  # résumé (étiquettes MP3, livret, bibliothèque)
    pub_date: str = ""
    episode_type: str = "full"
    published: bool = False
    age: str = "6-8"  # tranche d'âge : 3-5 | 6-8 | 9-12
    tone: str = "aventure"  # drole | aventure | douce | educative
    moral: str = ""  # morale facultative
    bedtime: bool = False  # histoire du soir : voix douce et ralentie, berceuse et fondu à la fin
    favorite: bool = False
    cover_path: str = ""  # couverture de l'histoire (sinon celle de la collection)
    audio_file: str = ""  # dernier MP3 exporté (coin lecture)
    duration: float = 0.0  # durée du dernier MP3 exporté, en secondes

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)

    def word_count(self) -> int:
        return len(self.text.split())


HOST_ROLES = {"hero": "Héros / héroïne", "character": "Personnage", "animal": "Animal", "magic": "Créature magique",
              "villain": "Méchant (gentil quand même)", "parent": "Parent, grand-parent"}

# Façons de parler d'un personnage : hauteur de voix (demi-tons) et débit relatif
VOICE_STYLES: dict[str, tuple[str, float, float]] = {
    "normal": ("Voix normale", 0.0, 1.0),
    "enfant": ("Enfant (plus aiguë)", 3.0, 1.04),
    "petit": ("Tout petit animal (très aiguë)", 6.0, 1.08),
    "fee": ("Fée, lutin (aiguë et légère)", 4.0, 1.0),
    "grand": ("Grand personnage (plus grave)", -3.0, 0.96),
    "geant": ("Géant, ogre, ours (très grave)", -6.0, 0.9),
    "dragon": ("Dragon (grave et lent)", -5.0, 0.86),
    "ancien": ("Vieux sage, grand-mère (posée)", -1.5, 0.9),
    "robot": ("Robot (un peu aiguë, rapide)", 1.5, 1.08),
}


@dataclass
class Host:
    """Personnage de l'histoire : ses répliques s'écrivent « @Nom: … » dans le texte."""
    name: str
    role: str = "character"  # voir HOST_ROLES
    voice_id: str = ""
    bio: str = ""  # description (aide l'assistant IA à écrire l'histoire)
    pan: float | None = None  # position stéréo -1 (gauche) … 1 (droite) ; None = automatique
    style: str = "normal"  # voir VOICE_STYLES
    pitch: float | None = None  # hauteur en demi-tons ; None = celle du style
    id: str = field(default_factory=lambda: new_id("h_"))

    @property
    def pitch_semitones(self) -> float:
        if self.pitch is not None:
            return max(-8.0, min(8.0, float(self.pitch)))
        return VOICE_STYLES.get(self.style, VOICE_STYLES["normal"])[1]

    @property
    def style_rate(self) -> float:
        return VOICE_STYLES.get(self.style, VOICE_STYLES["normal"])[2]

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
    "streaming": "Écoute sur enceinte ou téléphone -16 LUFS (recommandé)",
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
    speed: float = 0.96
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
    announce_episode_number: bool = False  # pas de « Épisode 3. » avant le titre d'une histoire
    stereo: bool = True  # chaque intervenant placé à gauche ou à droite, comme en studio
    stereo_width: float = 0.35  # écart stéréo des intervenants (0 = centre, 1 = complètement sur le côté)
    overlap_reactions: bool = False  # réactions courtes (« Ah oui ! ») lancées par-dessus la fin de la réplique
    overlap_ms: int = 450  # durée du chevauchement
    asr_threshold: float = 0.3
    ambience_db: float = -26.0  # niveau des fonds d'ambiance (« [ambiance: pluie] ») par rapport aux voix
    bedtime_speed: float = 0.88  # histoire du soir : débit de lecture
    bedtime_pause_factor: float = 1.35  # histoire du soir : pauses allongées

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


EXPORT_FORMATS = {
    "mp3_chapters": "MP3 — un fichier par histoire, avec couverture et métadonnées",
    "mp3_single": "MP3 — compilation de toutes les histoires, avec repères",
    "booklet_html": "Livret à lire en même temps (HTML, gros caractères)",
    "booklet_pdf": "Livret imprimable (PDF, gros caractères)",
    "wav": "WAV — masters 24 bits sans perte",
    "flac": "FLAC — sans perte compressé",
    "subtitles": "Texte synchronisé (SRT et LRC) pour chaque histoire",
}

NOISE_KINDS = {"none": "Rien", "pluie": "Pluie douce", "bruit_blanc": "Bruit blanc", "bruit_rose": "Bruit rose (plus doux)",
               "mer": "Vagues", "vent": "Vent léger"}


@dataclass
class ExportSettings:
    formats: list[str] = field(default_factory=lambda: ["mp3_chapters", "booklet_html", "booklet_pdf"])
    m4b_bitrate: str = "96k"
    mp3_bitrate: str = "128k"
    mp3_stereo: bool = False
    opus_bitrate: str = "48k"
    output_dir: str = ""
    include_credits: bool = False  # pas de pistes de crédits séparées
    opening_credits: str = "{title}. {subtitle_sentence}Écrit par {author}. Lu par {narrator}."
    closing_credits: str = "Fin. Vous venez d'écouter {title}, écrit par {author}, lu par {narrator}."
    credits_voice_id: str = ""  # vide : voix du narrateur
    make_sample: bool = False
    sample_minutes: float = 3.0
    acx_cover: bool = False  # couverture 3000 × 3000 au lieu de 1400
    file_pattern: str = "{number:02d} - {title}"
    write_report: bool = True
    intro_music: str = ""  # jingle d'ouverture
    outro_music: str = ""  # jingle de fin
    jingles_each_episode: bool = True  # musiques au début et à la fin de chaque histoire
    chapters_in_notes: bool = True  # chapitres horodatés ajoutés à la description (flux RSS, étiquettes)
    trailer_seconds: int = 30  # durée de la bande-annonce
    rss_only_due: bool = False  # hérité (non utilisé)
    background_music: str = ""  # fond sonore sous la narration des chapitres
    background_level_db: float = -20.0  # niveau du fond sonore par rapport à la voix
    # histoire du soir
    lullaby: bool = True  # berceuse générée à la fin des histoires du soir
    lullaby_seconds: int = 75
    sleep_noise: str = "pluie"  # voir NOISE_KINDS : continue après la berceuse
    sleep_noise_minutes: float = 5.0
    booklet_font_pt: int = 20  # taille du texte du livret

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


@dataclass
class Project:
    metadata: BookMetadata = field(default_factory=BookMetadata)
    chapters: list[Chapter] = field(default_factory=list)
    narrator_voice_id: str = ""
    cast: dict[str, str] = field(default_factory=dict)  # personnage -> id de voix
    hosts: list[Host] = field(default_factory=list)  # personnages (voix prioritaires sur ``cast``)
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
        return "Histoires sans titre"

    def included_chapters(self) -> list[Chapter]:
        return [c for c in self.chapters if c.include and c.text.strip()]

    def word_count(self) -> int:
        return sum(c.word_count() for c in self.included_chapters())

    def estimated_minutes(self, wpm: float = 140.0) -> float:
        return sum(self.story_minutes(c, wpm) for c in self.included_chapters())

    def story_minutes(self, chapter: Chapter, wpm: float = 140.0) -> float:
        """Durée estimée d'une histoire (débit des contes, plus lent le soir), hors berceuse."""
        speed = (self.production.speed or 1.0) * (self.production.bedtime_speed if chapter.bedtime else 1.0)
        return chapter.word_count() / (wpm * max(0.3, speed))

    def episode_number(self, chapter: Chapter) -> int:
        """Numéro de l'histoire : celui saisi, sinon sa position parmi les histoires incluses."""
        if chapter.number:
            return chapter.number
        n = 0
        for c in self.chapters:
            if c.include and c.episode_type == "full":
                n += 1
            if c.id == chapter.id:
                return max(n, 1)
        return 0

    def host_pan(self, name: str | None) -> float:
        """Position stéréo d'un personnage : la sienne, sinon alternée gauche / droite selon la liste."""
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
        """Personnage par son nom ; « {prénom} » correspond aussi au prénom de l'enfant."""
        from .textproc import personalize

        key = name.strip().lower()
        found = next((h for h in self.hosts if h.name.strip().lower() == key), None)
        if found is None:
            found = next((h for h in self.hosts if "{" in h.name
                          and personalize(h.name, self.metadata.child_name).strip().lower() == key), None)
        return found

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
