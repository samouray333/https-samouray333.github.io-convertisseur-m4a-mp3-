"""Rapport de bug (journal, réglages sans la clé, projet, système) et installation d'une mise à jour."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from .. import APP_NAME, __version__, paths
from ..config import settings

SECRET_KEYS = ("ai_key",)


def bug_report(project_path: Path | None = None, target_dir: Path | None = None) -> Path:
    """Archive à envoyer au support : rien de personnel au-delà du projet ouvert (texte des répliques)."""
    target_dir = target_dir or (paths.documents_dir() / "Doublys")
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"Doublys-rapport-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    info = {"application": f"{APP_NAME} {__version__}", "python": sys.version, "systeme": platform.platform(),
            "processeur": platform.processor(), "donnees": str(paths.data_dir())}
    try:
        from .engines import all_engines, all_tools

        info["moteurs"] = {e.info.id: e.status()[1] for e in all_tools() + all_engines()}
    except Exception as exc:  # noqa: BLE001
        info["moteurs"] = f"indisponible : {exc}"
    try:
        from . import ffmpeg

        info["ffmpeg"] = ffmpeg.version()
    except Exception as exc:  # noqa: BLE001
        info["ffmpeg"] = str(exc)
    prefs = {k: ("(masquée)" if k in SECRET_KEYS and v else v) for k, v in settings().data.items()}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("systeme.json", json.dumps(info, indent=2, ensure_ascii=False))
        zf.writestr("reglages.json", json.dumps(prefs, indent=2, ensure_ascii=False))
        for log in sorted(paths.logs_dir().glob("*.log*")):
            zf.write(log, f"journal/{log.name}")
        if project_path is not None and Path(project_path).exists():
            zf.write(project_path, f"projet/{Path(project_path).name}")
    return out


def launch_installer(installer: Path) -> None:
    """Lance l'installateur téléchargé (l'application se ferme ensuite pour qu'il remplace les fichiers)."""
    if sys.platform.startswith("win"):
        subprocess.Popen([str(installer)], close_fds=True)  # noqa: S603 - fichier téléchargé depuis nos Releases
    else:
        subprocess.Popen(["xdg-open", str(installer)])
