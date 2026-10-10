"""Interface commune des moteurs de synthèse vocale."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import VoiceProfile


class EngineError(RuntimeError):
    """Erreur de synthèse affichable à l'utilisateur."""


class ServiceBlocked(EngineError):
    """Le service en ligne refuse les demandes : inutile de réessayer chaque passage, la production s'arrête."""


@dataclass
class ParamSpec:
    key: str
    label: str
    minimum: float
    maximum: float
    default: float
    step: float = 0.05
    help: str = ""
    decimals: int = 2


@dataclass
class EngineInfo:
    id: str
    name: str
    tagline: str
    description: str
    supports_cloning: bool = False
    online: bool = False
    requires_install: bool = False
    languages: list[str] = field(default_factory=list)
    license: str = ""
    max_chars: int = 400
    min_chars: int = 0
    max_workers: int = 1
    quality: int = 3  # 1..5
    speed: int = 3  # 1..5
    disk_size: str = ""
    params: list[ParamSpec] = field(default_factory=list)
    accent: str = "#7C5CFF"
    install_id: str = ""  # moteur à installer (s'il diffère de l'identifiant)


@dataclass
class BuiltinVoice:
    id: str
    name: str
    language: str = ""
    gender: str = ""
    locale: str = ""
    description: str = ""


READY = "ready"
NOT_INSTALLED = "not_installed"
UNAVAILABLE = "unavailable"


class TTSEngine(ABC):
    info: EngineInfo

    def status(self) -> tuple[str, str]:
        return READY, "Prêt"

    def is_ready(self) -> bool:
        return self.status()[0] == READY

    def list_builtin_voices(self, refresh: bool = False) -> list[BuiltinVoice]:
        return []

    def default_params(self) -> dict[str, Any]:
        return {p.key: p.default for p in self.info.params}

    def merged_params(self, voice: VoiceProfile) -> dict[str, Any]:
        params = self.default_params()
        params.update({k: v for k, v in (voice.params or {}).items() if v is not None})
        return params

    @abstractmethod
    def synthesize(self, text: str, voice: VoiceProfile, out_path: Path, language: str,
                   speed: float = 1.0, seed: int | None = None) -> Path:
        """Synthétise ``text`` et écrit un fichier audio ; renvoie le chemin réellement écrit."""

    def warmup(self) -> None:
        """Prépare le moteur (chargement du modèle) avant une longue production."""

    def shutdown(self) -> None:
        pass
