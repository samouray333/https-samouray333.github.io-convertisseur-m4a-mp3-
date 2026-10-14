"""Enregistrement et ouverture des projets (.pcsproj)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..config import atomic_write_text
from .models import Project, now_iso

PROJECT_EXT = ".pcsproj"


class ProjectError(Exception):
    pass


def save_project(project: Project, path: str | Path | None = None) -> Path:
    target = Path(path) if path else project.path
    if target is None:
        raise ProjectError("Aucun emplacement d'enregistrement pour le projet.")
    if target.suffix.lower() != PROJECT_EXT:
        target = target.with_suffix(PROJECT_EXT)
    project.modified = now_iso()
    payload = json.dumps(project.to_dict(), indent=2, ensure_ascii=False)
    if target.exists():
        try:
            shutil.copy2(target, target.with_suffix(PROJECT_EXT + ".bak"))
        except OSError:
            pass
    atomic_write_text(target, payload)
    project.path = target
    return target


def load_project(path: str | Path) -> Project:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectError(f"Projet introuvable : {p}") from exc
    except json.JSONDecodeError as exc:
        backup = p.with_suffix(PROJECT_EXT + ".bak")
        if backup.exists():
            data = json.loads(backup.read_text(encoding="utf-8"))
        else:
            raise ProjectError(f"Le fichier de projet est endommagé : {exc}") from exc
    project = Project.from_dict(data)
    project.path = p
    return project


def delete_project_files(path: str | Path) -> list[Path]:
    """Supprime un projet du disque : fichier .pcsproj, sa sauvegarde et son dossier de travail.

    Le dossier du projet n'est retiré que s'il ne contient plus rien d'autre que la couverture ;
    les exports (MP3, M4B…) et les documents d'origine sont toujours conservés.
    """
    p = Path(path)
    removed: list[Path] = []
    for f in (p, p.with_suffix(PROJECT_EXT + ".bak")):
        if f.is_file():
            f.unlink()
            removed.append(f)
    work = p.parent / f"{p.stem}_fichiers"
    if work.is_dir():
        shutil.rmtree(work, ignore_errors=True)
        removed.append(work)
    folder = p.parent
    try:
        rest = list(folder.iterdir())
    except OSError:
        return removed
    if folder.name.startswith(p.stem) and all(f.is_file() and f.stem.lower() == "couverture" for f in rest):
        for f in rest:
            f.unlink()
            removed.append(f)
        try:
            folder.rmdir()
            removed.append(folder)
        except OSError:
            pass
    return removed


def project_data_dir(project: Project) -> Path:
    """Dossier de travail associé à un projet (cache audio, rendus)."""
    if project.path is None:
        from .. import paths

        d = paths.data_dir() / "unsaved" / project.id
    else:
        d = project.path.parent / f"{project.path.stem}_fichiers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir(project: Project) -> Path:
    d = project_data_dir(project) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def renders_dir(project: Project) -> Path:
    d = project_data_dir(project) / "chapitres"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_export_dir(project: Project) -> Path:
    if project.export.output_dir:
        return Path(project.export.output_dir)
    if project.path is not None:
        return project.path.parent / "Export"
    from ..config import settings

    return settings().projects_dir() / "Export"


def cache_size_bytes(project: Project) -> int:
    total = 0
    for f in project_data_dir(project).rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def clear_cache(project: Project) -> None:
    for sub in ("cache", "chapitres"):
        d = project_data_dir(project) / sub
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
