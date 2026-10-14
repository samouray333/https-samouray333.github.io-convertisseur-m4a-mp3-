"""Préférences de l'application, enregistrées en JSON dans le dossier de configuration."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from . import BRAND_ACCENT, paths

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "theme": "dark",  # dark | light
    "accent": BRAND_ACCENT,
    "language": "fr",
    "device": "auto",  # auto | cuda | cpu
    "projects_dir": "",
    "recent_projects": [],
    "autosave_minutes": 3,
    "ffmpeg_path": "",
    "default_voice_id": "",
    "edge_concurrency": 2,  # au-delà, Microsoft peut bloquer temporairement
    "preview_sentence": "Il était une fois, dans une petite maison au bord de la forêt, un enfant qui adorait "
    "les histoires. Installe-toi bien confortablement : celle-ci commence maintenant !",
    "window_geometry": "",
    "first_run": True,
    "xtts_tos_accepted": False,
    "player_volume": 0.9,
    "check_updates": True,
    "asr_model": "base",
    "fastclone_mode": "fast",  # fast (décodeur Turbo) | best
    "clone_base": "microsoft",  # voix de base du clonage rapide et des modèles RVC : microsoft | kokoro
    "ai_key": "",  # clé DeepSeek chiffrée (voir core/secrets.py)
    "ai_model": "",  # vide : choisi automatiquement parmi les modèles du compte
    "ai_base_url": "https://api.deepseek.com",
    "ai_pauses": True,  # l'assistant propose aussi des pauses dramatiques
    "ai_prosody": True,  # débit et mots mis en valeur
}


# Réglages repris d'AudioLivre Studio tant qu'ils n'ont pas été changés ici (clé DeepSeek, carte graphique…)
SHARED_KEYS = ("ai_key", "ai_model", "ai_base_url", "device", "clone_base", "fastclone_mode", "xtts_tos_accepted",
               "asr_model", "edge_concurrency", "default_voice_id")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or (paths.config_dir() / "settings.json")
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        own: dict[str, Any] = {}
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    own = loaded
        except Exception as exc:  # fichier corrompu : on repart des valeurs par défaut
            log.warning("Préférences illisibles (%s), valeurs par défaut utilisées", exc)
        self.data.update(self._shared(own))
        self.data.update(own)

    def _shared(self, own: dict[str, Any]) -> dict[str, Any]:
        try:
            f = paths.shared_settings_file()
            if f is None or not f.exists():
                return {}
            other = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(other, dict):
            return {}
        return {k: other[k] for k in SHARED_KEYS if k in other and other[k] not in ("", None) and own.get(k) in ("", None)}

    def save(self) -> None:
        atomic_write_text(self.path, json.dumps(self.data, indent=2, ensure_ascii=False))

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.data:
            return self.data[key]
        return DEFAULTS.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self.data[key] = value
        if save:
            self.save()

    def projects_dir(self) -> Path:
        p = self.get("projects_dir")
        return Path(p) if p else paths.default_projects_dir()

    def add_recent(self, project_path: str | Path) -> None:
        p = str(Path(project_path))
        recents = [r for r in self.get("recent_projects", []) if r != p]
        recents.insert(0, p)
        self.set("recent_projects", recents[:12])

    def remove_recent(self, project_path: str | Path) -> None:
        p = str(Path(project_path))
        self.set("recent_projects", [r for r in self.get("recent_projects", []) if r != p])

    def clear_recent(self) -> None:
        self.set("recent_projects", [])

    def recent_projects(self) -> list[str]:
        return [r for r in self.get("recent_projects", []) if Path(r).exists()]


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
