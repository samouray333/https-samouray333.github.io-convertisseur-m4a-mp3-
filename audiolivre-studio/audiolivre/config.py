"""Préférences de l'application, enregistrées en JSON dans le dossier de configuration."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "theme": "dark",  # dark | light
    "accent": "#7C5CFF",
    "language": "fr",
    "device": "auto",  # auto | cuda | cpu
    "projects_dir": "",
    "recent_projects": [],
    "autosave_minutes": 3,
    "ffmpeg_path": "",
    "default_voice_id": "",
    "edge_concurrency": 4,
    "preview_sentence": "Bonjour, je suis la voix qui va lire votre livre. "
    "Il était une fois, dans un petit village au bord de la mer, une histoire extraordinaire.",
    "window_geometry": "",
    "first_run": True,
    "xtts_tos_accepted": False,
    "player_volume": 0.9,
    "check_updates": True,
    "asr_model": "base",
    "fastclone_mode": "fast",  # fast (décodeur Turbo) | best
}


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
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
        except Exception as exc:  # fichier corrompu : on repart des valeurs par défaut
            log.warning("Préférences illisibles (%s), valeurs par défaut utilisées", exc)

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

    def recent_projects(self) -> list[str]:
        return [r for r in self.get("recent_projects", []) if Path(r).exists()]


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
