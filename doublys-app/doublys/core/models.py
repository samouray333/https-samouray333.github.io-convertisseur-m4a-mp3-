"""Modèles de données : projet de doublage, répliques, personnes, réglages."""

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


@dataclass
class VoiceProfile:
    """Voix telle que la comprennent les moteurs (construite à la volée pour chaque personne)."""

    name: str
    engine: str  # edge | sapi | xtts | chatterbox | kokoro | fastclone | rvc
    kind: str = "builtin"  # builtin | clone
    engine_voice: str = ""
    language: str = "fr"
    gender: str = ""
    description: str = ""
    references: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    color: str = "#FF6B4A"
    favorite: bool = False
    consent: bool = False
    id: str = field(default_factory=lambda: new_id("v_"))
    created: str = field(default_factory=now_iso)
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


# ---------------------------------------------------------------------------------------
# Doublage
# ---------------------------------------------------------------------------------------
# mode de voix -> (libellé, moteur, clonage)
VOICE_MODES: dict[str, tuple[str, str, bool]] = {
    "fastclone_offline": ("Clonage rapide hors ligne (Kokoro + conversion)", "fastclone", True),
    "fastclone_ms": ("Clonage rapide Microsoft (Henri/Denise + conversion)", "fastclone", True),
    "xtts": ("XTTS-v2 (clonage fidèle, non commercial)", "xtts", True),
    "chatterbox": ("Chatterbox (clonage expressif)", "chatterbox", True),
    "rvc": ("Modèle RVC (.pth)", "rvc", True),
    "edge": ("Voix Microsoft (sans clonage)", "edge", False),
    "kokoro": ("Kokoro hors ligne (sans clonage)", "kokoro", False),
    "sapi": ("Voix Windows (sans clonage)", "sapi", False),
}
DEFAULT_VOICE_MODE = "fastclone_offline"

LINE_STATES = {
    "": "à produire",
    "ok": "calée",
    "tempo": "accélérée",
    "rate": "débit augmenté",
    "long": "trop longue",
    "error": "erreur",
}

STEPS = ["extract", "separate", "transcribe", "segment", "speakers", "translate", "voices", "dub", "mix"]
VOICE_STEPS = ("voices", "dub", "mix")  # inutiles en mode « sous-titres seuls »
STEP_LABELS = {
    "extract": "Extraction du son",
    "separate": "Séparation voix / fond",
    "transcribe": "Transcription (Whisper)",
    "segment": "Découpage en répliques",
    "speakers": "Reconnaissance des personnes",
    "translate": "Traduction",
    "voices": "Voix des personnes",
    "dub": "Voix françaises et calage",
    "mix": "Mixage",
}

TRANSLATORS = {
    "opus_big": ("Opus-MT grand modèle (hors ligne, recommandé)", "Helsinki-NLP/opus-mt-tc-big-en-fr"),
    "opus": ("Opus-MT rapide (hors ligne)", "Helsinki-NLP/opus-mt-en-fr"),
    "deepseek": ("DeepSeek (en ligne, tient compte du temps disponible)", ""),
}

# langue de la vidéo -> (nom, code ISO 639-2 des pistes, traducteur direct vers le français, traducteur vers
# l'anglais pour passer par l'anglais quand il n'y a pas de traducteur direct)
LANGUAGES: dict[str, tuple[str, str, str, str]] = {
    "en": ("Anglais", "eng", "", ""),
    "ja": ("Japonais", "jpn", "Helsinki-NLP/opus-mt-ja-fr", "Helsinki-NLP/opus-mt-ja-en"),
    "es": ("Espagnol", "spa", "Helsinki-NLP/opus-mt-es-fr", "Helsinki-NLP/opus-mt-es-en"),
    "de": ("Allemand", "deu", "Helsinki-NLP/opus-mt-de-fr", "Helsinki-NLP/opus-mt-de-en"),
    "it": ("Italien", "ita", "Helsinki-NLP/opus-mt-it-fr", "Helsinki-NLP/opus-mt-it-en"),
    "pt": ("Portugais", "por", "", "Helsinki-NLP/opus-mt-mul-en"),
    "ko": ("Coréen", "kor", "Helsinki-NLP/opus-mt-ko-fr", "Helsinki-NLP/opus-mt-ko-en"),
    "zh": ("Chinois", "zho", "", "Helsinki-NLP/opus-mt-zh-en"),
    "ru": ("Russe", "rus", "Helsinki-NLP/opus-mt-ru-fr", "Helsinki-NLP/opus-mt-ru-en"),
    "ar": ("Arabe", "ara", "Helsinki-NLP/opus-mt-ar-fr", "Helsinki-NLP/opus-mt-ar-en"),
    "nl": ("Néerlandais", "nld", "Helsinki-NLP/opus-mt-nl-fr", "Helsinki-NLP/opus-mt-nl-en"),
    "tr": ("Turc", "tur", "Helsinki-NLP/opus-mt-tr-fr", "Helsinki-NLP/opus-mt-tr-en"),
    "pl": ("Polonais", "pol", "Helsinki-NLP/opus-mt-pl-fr", "Helsinki-NLP/opus-mt-pl-en"),
}
AUTO_LANGUAGE = "auto"
CJK_LANGUAGES = ("ja", "zh", "ko")  # Whisper « small » y fait trop d'erreurs : « medium » conseillé


def language_name(code: str) -> str:
    return LANGUAGES.get(code, (code or "langue d'origine",))[0]
WHISPER_MODELS = {"small": "small (rapide, défaut)", "medium": "medium (plus précis)",
                  "large-v3-turbo": "large-v3-turbo (le plus précis)"}


@dataclass
class Line:
    """Réplique : un morceau de phrase dit par une personne, à doubler dans son créneau."""

    start: float
    end: float
    en: str = ""
    fr: str = ""
    person_id: str = ""
    id: str = field(default_factory=lambda: new_id("l_"))
    words: list[list] = field(default_factory=list)  # [[début, fin, mot], …] (pour couper)
    fr_edited: bool = False  # texte français modifié à la main (pas retraduit automatiquement)
    state: str = ""  # voir LINE_STATES
    message: str = ""
    audio: str = ""  # voix française calée (relatif au dossier de travail)
    audio_key: str = ""  # empreinte des réglages qui ont produit ``audio``
    duration: float = 0.0  # durée de la voix française calée
    rate: float = 1.0  # débit demandé au moteur
    tempo: float = 1.0  # accélération appliquée ensuite (atempo)
    gain_db: float = 0.0
    seed: int = 0
    intensity: float = 0.0  # niveau de la réplique d'origine par rapport à la voix habituelle de la personne (dB)
    expressive: bool = False  # voix produite par Chatterbox expressif (réplique forte)
    speaker_score: float = 1.0  # ressemblance avec la voix de sa personne (empreintes, 0..1)
    speaker_margin: float = 1.0  # écart avec la personne la plus proche après elle
    issues: list = field(default_factory=list)  # contrôle qualité : [[code, message], …]
    checked: bool = False  # vérifiée à la main : plus signalée

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)

    @property
    def length(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Person:
    name: str
    id: str = field(default_factory=lambda: new_id("p_"))
    color: str = "#FF6B4A"
    gender: str = ""  # F | M | "" (estimé par la hauteur de la voix)
    gender_locked: bool = False  # choisi à la main : n'est plus réestimé
    pitch_hz: float = 0.0
    reference: str = ""  # extrait de référence (relatif au dossier de travail ou absolu)
    reference_source: str = "auto"  # auto | file
    reference_offset: int = 0  # « autre extrait » : décalage dans le choix des répliques
    voice_mode: str = ""  # vide : mode par défaut du projet
    base_voice: str = ""  # voix de base (Kokoro, Microsoft, Windows) ; vide : choisie selon le genre
    params: dict[str, Any] = field(default_factory=dict)
    rvc_model: str = ""
    rvc_index: str = ""
    embedding: list = field(default_factory=list)  # empreinte vocale moyenne (reconnaissance dans une série)
    character: str = ""  # personnage de la série reconnu (identifiant)

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


@dataclass
class DubSettings:
    separate: bool = True  # sinon : VO baissée sous la VF
    no_separation_duck_db: float = -18.0
    whisper_model: str = "small"
    source_language: str = "en"  # code de LANGUAGES ou « auto » (détectée par Whisper)
    detected_language: str = ""  # langue trouvée par Whisper quand source_language vaut « auto »
    glossary: list = field(default_factory=list)  # [[terme d'origine, rendu en français], …] (noms, attaques…)
    pause_split: float = 0.7  # silence qui coupe une réplique (s)
    max_line: float = 12.0  # durée maximale d'une réplique (s) ; coupure préférée après 10 s
    min_fragment: float = 0.6  # fragments plus courts fusionnés avec leur voisin
    speaker_threshold: float = 0.62  # distance cosinus maximale entre deux répliques d'une même personne
    max_speakers: int = 0  # 0 = automatique
    translator: str = "opus_big"
    chars_per_second: float = 14.5
    voice_mode: str = DEFAULT_VOICE_MODE
    max_rate: float = 1.30  # débit maximal demandé au moteur
    max_tempo: float = 1.12  # accélération maximale sans nouvelle synthèse
    gap_before_next: float = 0.1
    overhang: float = 1.0  # la VF peut dépasser la fin de la réplique d'origine de 1 s au plus
    keep_original_voice: bool = False  # voix d'origine laissée faible sous la VF
    original_voice_db: float = -20.0
    match_level: bool = True  # niveau de la VF aligné sur la voix d'origine
    dynamics: bool = True  # nuances de volume de la phrase d'origine reproduites
    expressive: bool = True  # répliques fortes (cris, colère) refaites avec Chatterbox expressif
    expressive_db: float = 6.0  # à partir de combien de dB au-dessus de la voix habituelle
    expressive_max: int = 25  # au plus N répliques par vidéo (environ 25 s de calcul chacune sans GPU)
    subtitles_only: bool = False  # sous-titres français seulement : pas de voix française (VOSTFR)

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)

    @property
    def language(self) -> str:
        """Langue réelle de la vidéo (« en » tant que la détection automatique n'a pas eu lieu)."""
        if self.source_language == AUTO_LANGUAGE:
            return self.detected_language or "en"
        return self.source_language or "en"


@dataclass
class ExportOptions:
    container: str = "mp4"  # mp4 | mkv
    keep_original_audio: bool = False
    normalize: bool = True  # loudnorm -16 LUFS
    audio_bitrate: str = "192k"
    subtitles_fr: bool = True
    subtitles_en: bool = False
    srt_files: bool = True
    burn_subtitles: bool = False
    subtitle_colors: bool = True  # une couleur par personne (choisie dans la page Personnes)
    audio_only: str = ""  # "" | wav | mp3 : piste VF seule
    output_dir: str = ""

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


@dataclass
class VideoInfo:
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    audio_streams: int = 0
    size: int = 0
    mtime: float = 0.0

    @classmethod
    def from_dict(cls, d):
        return _from_dict(cls, d)


@dataclass
class Project:
    title: str = ""
    source_video: str = ""
    video: VideoInfo = field(default_factory=VideoInfo)
    settings: DubSettings = field(default_factory=DubSettings)
    export: ExportOptions = field(default_factory=ExportOptions)
    lines: list[Line] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    steps: dict[str, dict] = field(default_factory=dict)  # étape -> {"done": True, "date": …}
    last_export: str = ""
    series: str = ""  # série (casting réutilisé d'un épisode à l'autre)
    id: str = field(default_factory=lambda: new_id("prj_"))
    created: str = field(default_factory=now_iso)
    modified: str = field(default_factory=now_iso)
    format_version: int = 1
    path: Path | None = field(default=None, compare=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d.pop("path", None)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        p = cls(
            title=d.get("title", ""),
            source_video=d.get("source_video", ""),
            video=VideoInfo.from_dict(d.get("video")),
            settings=DubSettings.from_dict(d.get("settings")),
            export=ExportOptions.from_dict(d.get("export")),
            lines=[Line.from_dict(x) for x in d.get("lines", [])],
            people=[Person.from_dict(x) for x in d.get("people", [])],
            steps=dict(d.get("steps", {})),
            last_export=d.get("last_export", ""),
            series=d.get("series", ""),
        )
        for key in ("id", "created", "modified", "format_version"):
            if key in d:
                setattr(p, key, d[key])
        return p

    @property
    def display_title(self) -> str:
        return self.title or (self.path.stem if self.path else "") or "Projet sans titre"

    def person(self, person_id: str) -> Person | None:
        return next((p for p in self.people if p.id == person_id), None)

    def line(self, line_id: str) -> Line | None:
        return next((x for x in self.lines if x.id == line_id), None)

    def step_done(self, step: str) -> bool:
        return bool(self.steps.get(step, {}).get("done"))

    def mark_step(self, step: str, done: bool = True, **info) -> None:
        if done:
            self.steps[step] = {"done": True, "date": now_iso(), **info}
        else:
            self.steps.pop(step, None)

    def invalidate_from(self, step: str) -> None:
        """Une étape refaite rend les suivantes caduques (leurs données sont gardées jusqu'au nouveau calcul)."""
        if step in STEPS:
            for s in STEPS[STEPS.index(step):]:
                self.steps.pop(s, None)

    def active_steps(self) -> list[str]:
        """Étapes utiles : sans séparation si elle est désactivée, sans voix ni mixage pour les sous-titres seuls."""
        skip = set() if self.settings.separate else {"separate"}
        if self.settings.subtitles_only:
            skip |= set(VOICE_STEPS)
        return [s for s in STEPS if s not in skip]

    def next_step(self) -> str | None:
        for s in self.active_steps():
            if not self.step_done(s):
                return s
        return None
