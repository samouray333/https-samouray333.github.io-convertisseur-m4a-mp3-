"""Projets Doublys : dossier Documents\\Doublys\\<titre>\\ avec le fichier .doublys (JSON) et un dossier de travail.

La vidéo source reste à sa place ; seul son chemin est enregistré.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .. import PROJECT_EXT
from ..config import atomic_write_text
from . import ffmpeg
from .models import Project, VideoInfo, now_iso

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".mts",
                    ".m2ts", ".3gp")
VIDEO_FILTER = "Vidéos (" + " ".join("*" + e for e in VIDEO_EXTENSIONS) + ");;Tous les fichiers (*)"
PROJECT_FILTER = f"Projets Doublys (*{PROJECT_EXT})"


class ProjectError(Exception):
    pass


def safe_name(text: str, fallback: str = "Vidéo") -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text or "").strip(" .")[:70]
    return name or fallback


def save_project(project: Project, path: str | Path | None = None) -> Path:
    if path is not None:
        project.path = Path(path)
    if project.path is None:
        raise ProjectError("Aucun emplacement pour le projet.")
    project.modified = now_iso()
    atomic_write_text(project.path, json.dumps(project.to_dict(), indent=1, ensure_ascii=False))
    return project.path


def load_project(path: str | Path) -> Project:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProjectError(f"Projet introuvable : {p}") from None
    except (OSError, ValueError) as exc:
        raise ProjectError(f"Le projet « {p.name} » est illisible ({exc}).") from None
    if not isinstance(data, dict):
        raise ProjectError(f"Le fichier « {p.name} » n'est pas un projet Doublys.")
    pr = Project.from_dict(data)
    pr.path = p
    return pr


def work_dir(project: Project) -> Path:
    if project.path is None:
        raise ProjectError("Le projet n'est pas encore enregistré.")
    d = project.path.parent / "travail"
    d.mkdir(parents=True, exist_ok=True)
    return d


def work_file(project: Project, name: str) -> Path:
    return work_dir(project) / name


def voices_dir(project: Project) -> Path:
    d = work_dir(project) / "voix"
    d.mkdir(parents=True, exist_ok=True)
    return d


def references_dir(project: Project) -> Path:
    d = work_dir(project) / "personnes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve(project: Project, rel: str) -> Path:
    """Chemin d'un fichier enregistré relativement au dossier de travail (ou absolu)."""
    p = Path(rel)
    return p if p.is_absolute() else work_dir(project) / p


def relative(project: Project, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(work_dir(project).resolve()).as_posix()
    except ValueError:
        return str(path)


def default_export_dir(project: Project) -> Path:
    if project.export.output_dir:
        return Path(project.export.output_dir)
    if project.path is not None:
        return project.path.parent
    return Path(project.source_video).parent


def probe_video(path: str | Path) -> VideoInfo:
    info = ffmpeg.probe(path)
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get(
        "attached_pic")), None)
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if v is None:
        raise ProjectError("Ce fichier ne contient pas d'image vidéo.")
    if not audios:
        raise ProjectError("Cette vidéo n'a pas de son : il n'y a rien à doubler.")
    fps = 0.0
    try:
        num, den = str(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        pass
    p = Path(path)
    st = p.stat()
    return VideoInfo(duration=float(info.get("format", {}).get("duration", 0) or 0), width=int(v.get("width", 0)),
                     height=int(v.get("height", 0)), fps=round(fps, 3), video_codec=v.get("codec_name", ""),
                     audio_codec=audios[0].get("codec_name", ""), audio_streams=len(audios), size=st.st_size,
                     mtime=st.st_mtime)


def create_project(video: str | Path, projects_root: Path, title: str | None = None) -> Project:
    """Crée le dossier du projet et le fichier .doublys pour une vidéo."""
    video = Path(video)
    if not video.is_file():
        raise ProjectError(f"Vidéo introuvable : {video}")
    info = probe_video(video)
    name = safe_name(title or video.stem)
    folder = projects_root / name
    n = 2
    while folder.exists() and any(folder.glob("*" + PROJECT_EXT)):
        folder = projects_root / f"{name} ({n})"
        n += 1
    folder.mkdir(parents=True, exist_ok=True)
    pr = Project(title=title or video.stem, source_video=str(video.resolve()), video=info)
    save_project(pr, folder / f"{folder.name}{PROJECT_EXT}")
    work_dir(pr)
    return pr


def source_changed(project: Project) -> bool:
    """La vidéo a été remplacée ou modifiée depuis la création du projet."""
    p = Path(project.source_video)
    if not p.is_file():
        return True
    st = p.stat()
    return bool(project.video.size) and (st.st_size != project.video.size)


def delete_project_files(path: str | Path) -> list[Path]:
    """Supprime le fichier du projet et son dossier de travail (pas la vidéo ni les exports)."""
    p = Path(path)
    removed: list[Path] = []
    work = p.parent / "travail"
    if work.is_dir():
        shutil.rmtree(work)
        removed.append(work)
    if p.exists():
        p.unlink()
        removed.append(p)
    try:
        p.parent.rmdir()  # dossier vide uniquement
    except OSError:
        pass
    return removed


def clear_voice_cache(project: Project) -> None:
    shutil.rmtree(work_dir(project) / "voix", ignore_errors=True)
    for line in project.lines:
        line.audio = ""
        line.audio_key = ""
        line.state = ""
    project.mark_step("dub", False)
    project.mark_step("mix", False)


def cache_size_bytes(project: Project) -> int:
    total = 0
    try:
        for f in work_dir(project).rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except (OSError, ProjectError):
        pass
    return total
