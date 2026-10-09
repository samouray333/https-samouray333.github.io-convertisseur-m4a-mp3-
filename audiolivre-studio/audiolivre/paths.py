"""Emplacements des fichiers de l'application (ressources, données utilisateur, outils)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import APP_ID

IS_WINDOWS = sys.platform.startswith("win")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """Dossier du paquet ``audiolivre`` (fonctionne aussi une fois empaqueté)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "audiolivre"
    return Path(__file__).resolve().parent


def install_dir() -> Path:
    """Dossier d'installation (celui de l'exécutable une fois empaqueté)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return package_root().parent


def resource(*parts: str) -> Path:
    return package_root().joinpath("resources", *parts)


def worker_script() -> Path:
    return package_root() / "worker" / "tts_worker.py"


def _portable_home() -> Path | None:
    marker = install_dir() / "portable.txt"
    if marker.exists():
        return install_dir() / "data"
    return None


def _base_dir(kind: str) -> Path:
    override = os.environ.get("AUDIOLIVRE_HOME")
    if override:
        return Path(override) / kind
    portable = _portable_home()
    if portable is not None:
        return portable / kind
    if IS_WINDOWS:
        if kind == "config":
            root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        else:
            root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / APP_ID
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID / kind
    if kind == "config":
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_ID
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_ID


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    return _ensure(_base_dir("config"))


def data_dir() -> Path:
    return _ensure(_base_dir("data"))


def voices_dir() -> Path:
    return _ensure(config_dir() / "voices")


def engines_dir() -> Path:
    return _ensure(data_dir() / "engines")


def models_dir() -> Path:
    return _ensure(data_dir() / "models")


def logs_dir() -> Path:
    return _ensure(data_dir() / "logs")


def temp_dir() -> Path:
    return _ensure(data_dir() / "tmp")


def preview_cache_dir() -> Path:
    return _ensure(data_dir() / "preview-cache")


def documents_dir() -> Path:
    home = Path.home()
    if IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            # CSIDL_PERSONAL = 5 (Mes documents)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except Exception:
            pass
    for name in ("Documents", "Mes documents"):
        if (home / name).is_dir():
            return home / name
    return home


def default_projects_dir() -> Path:
    return documents_dir() / "AudioLivre Studio"


def find_tool(name: str) -> str | None:
    """Trouve un exécutable livré avec l'application (ffmpeg, ffprobe, uv) ou dans le PATH."""
    exe = name + (".exe" if IS_WINDOWS else "")
    candidates = [
        package_root().parent / "tools" / exe,
        install_dir() / "tools" / exe,
        install_dir() / "_internal" / "tools" / exe,
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    found = shutil.which(name)
    if found:
        return found
    if name == "uv":
        # uv installé comme paquet Python dans l'environnement courant
        try:
            import uv  # type: ignore

            p = uv.find_uv_bin()
            if p and Path(p).is_file():
                return str(p)
        except Exception:
            pass
    return None
