"""Bibliothèque : collections d'histoires (une série avec les mêmes personnages), favoris, durées, histoires
d'exemple fournies avec l'application, et liste des histoires prêtes à écouter pour le coin lecture."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from . import project_io
from .models import Chapter, Host, Project, VoiceProfile
from .textproc import personalize

log = logging.getLogger(__name__)

SAMPLES_FILE = "exemples.json"
SAMPLES_FOLDER = "Histoires d'exemple"


@dataclass
class StoryEntry:
    project_path: Path
    collection: str
    chapter_id: str
    title: str
    cover: str = ""
    duration: float = 0.0  # secondes : MP3 exporté, sinon estimation
    estimated: bool = True
    favorite: bool = False
    bedtime: bool = False
    age: str = ""
    audio: str = ""  # fichier à écouter (MP3 exporté ou histoire produite), vide s'il n'existe pas encore
    summary: str = ""


@dataclass
class Collection:
    path: Path
    title: str
    cover: str = ""
    child_name: str = ""
    characters: list[str] = field(default_factory=list)
    stories: list[StoryEntry] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.stories)


def story_audio(project: Project, chapter: Chapter) -> str:
    """Fichier à écouter : le dernier MP3 exporté, sinon l'histoire produite (si elle est à jour)."""
    if chapter.audio_file and Path(chapter.audio_file).is_file():
        return chapter.audio_file
    if project.path is not None:
        rendered = project_io.project_data_dir(project) / "chapitres" / f"{chapter.id}.flac"
        if rendered.is_file():
            return str(rendered)
    return ""


def collection_from_project(project: Project) -> Collection:
    child = project.metadata.child_name
    col = Collection(project.path or Path(), project.display_title, project.metadata.cover_path, child,
                     [personalize(h.name, child) for h in project.hosts])
    for ch in project.chapters:
        if not ch.include:
            continue
        exported = ch.duration > 0 and bool(ch.audio_file) and Path(ch.audio_file).is_file()
        col.stories.append(StoryEntry(
            project.path or Path(), col.title, ch.id, personalize(ch.title, child),
            ch.cover_path or project.metadata.cover_path,
            ch.duration if exported else project.story_minutes(ch) * 60, not exported, ch.favorite, ch.bedtime, ch.age,
            story_audio(project, ch), personalize(ch.description, child)))
    return col


def find_projects(roots: list[Path], extra: list[str] | None = None, depth: int = 3) -> list[Path]:
    """Projets de collections (.ctsproj) dans les dossiers donnés (sans descendre trop loin) et dans ``extra``."""
    found: dict[str, Path] = {}
    for e in extra or []:
        p = Path(e)
        if p.is_file():
            found[str(p.resolve())] = p
    for root in roots:
        if not root.is_dir():
            continue
        for p in _walk(root, depth):
            found.setdefault(str(p.resolve()), p)
    return sorted(found.values(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


def _walk(root: Path, depth: int):
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for e in entries:
        if e.is_file() and e.suffix.lower() == project_io.PROJECT_EXT:
            yield e
        elif e.is_dir() and depth > 0 and not e.name.endswith("_fichiers") and not e.name.startswith("."):
            yield from _walk(e, depth - 1)


def load_collections(project_paths: list[Path], current: Project | None = None) -> list[Collection]:
    """Collections lues sur le disque ; le projet ouvert dans l'application est pris tel qu'il est en mémoire."""
    cols = []
    for p in project_paths:
        try:
            if current is not None and current.path is not None and Path(current.path).resolve() == p.resolve():
                pr = current
            else:
                pr = project_io.load_project(p)
        except Exception as exc:  # projet illisible : ignoré dans la bibliothèque
            log.warning("Collection illisible %s : %s", p, exc)
            continue
        cols.append(collection_from_project(pr))
    return cols


def set_favorite(project_path: Path, chapter_id: str, value: bool) -> bool:
    pr = project_io.load_project(project_path)
    ch = pr.chapter_by_id(chapter_id)
    if ch is None:
        return False
    ch.favorite = value
    project_io.save_project(pr)
    return True


def format_minutes(seconds: float, estimated: bool = False) -> str:
    m = max(1, int(round(seconds / 60))) if seconds > 0 else 0
    if not m:
        return ""
    return f"{'≈ ' if estimated else ''}{m} min"


# ---------------------------------------------------------------------------------------
# Histoires d'exemple
# ---------------------------------------------------------------------------------------
def samples_data() -> dict:
    return json.loads(paths.resource("histoires", SAMPLES_FILE).read_text(encoding="utf-8"))


def _voice_for(library, engine_voice: str, cache: dict[str, str]) -> str:
    if engine_voice in cache:
        return cache[engine_voice]
    same = next((v for v in library.all() if v.engine == "edge" and v.engine_voice == engine_voice and not v.params),
                None)
    if same is None:
        label = engine_voice.split("-")[2].replace("MultilingualNeural", "").replace("Neural", "")
        same = library.save(VoiceProfile(name=f"{label} (Microsoft)", engine="edge", engine_voice=engine_voice,
                                         language="fr", description="Voix neuronale Microsoft. Nécessite Internet."))
    cache[engine_voice] = same.id
    return same.id


def build_samples(library, child_name: str = "") -> Project:
    """Collection d'exemple (en mémoire) : personnages avec leurs voix, histoires prêtes à produire."""
    data = samples_data()
    cache: dict[str, str] = {}
    pr = Project()
    m = pr.metadata
    m.title, m.subtitle, m.author = data["title"], data.get("subtitle", ""), data.get("author", "")
    m.description, m.child_name = data.get("description", ""), child_name
    pr.narrator_voice_id = _voice_for(library, data["narrator"], cache)
    for c in data["characters"]:
        pr.hosts.append(Host(c["name"], c.get("role", "character"), _voice_for(library, c["voice"], cache),
                             c.get("bio", ""), style=c.get("style", "normal")))
    for h in pr.hosts:
        pr.cast[h.name] = h.voice_id
    for s in data["stories"]:
        pr.chapters.append(Chapter(s["title"], s["text"], age=s.get("age", "6-8"), tone=s.get("tone", "aventure"),
                                   bedtime=bool(s.get("bedtime")), favorite=bool(s.get("favorite")),
                                   moral=s.get("moral", ""), description=s.get("summary", "")))
    return pr


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*{}]', "", name).strip()[:60] or "Histoires"


def install_samples(library, folder: Path, child_name: str = "", with_covers: bool = True) -> Path:
    """Enregistre la collection d'exemple (et ses couvertures dessinées) dans ``folder`` ; renvoie le projet."""
    folder.mkdir(parents=True, exist_ok=True)
    pr = build_samples(library, child_name)
    target = folder / f"{safe_name(pr.metadata.title)}{project_io.PROJECT_EXT}"
    if with_covers:
        from . import covers

        try:
            m = pr.metadata
            m.cover_path = str(covers.generate_cover(m.title, folder / "couverture.png", m.description,
                                                     subtitle=m.subtitle))
            for i, ch in enumerate(pr.chapters, 1):
                ch.cover_path = str(covers.generate_cover(personalize(ch.title, child_name),
                                                          folder / f"couverture-{i:02d}.png",
                                                          ch.description + " " + ch.text[:600], ch.bedtime,
                                                          subtitle=m.title))
        except Exception as exc:  # sans affichage graphique : pas de couverture, rien de bloquant
            log.warning("Couvertures d'exemple non dessinées : %s", exc)
    project_io.save_project(pr, target)
    return target


def refresh_name_covers(project: Project) -> int:
    """Redessine les couvertures générées dont le titre contient « {prénom} » (le prénom de l'enfant a changé).

    Seules les couvertures dessinées par l'application (« couverture-NN.png » des exemples, ou celles du dossier
    « couvertures » de la collection) sont refaites ; une image choisie par l'utilisateur n'est jamais touchée."""
    from . import covers

    n = 0
    child = project.metadata.child_name
    for i, ch in enumerate(project.chapters, 1):
        if "{" not in ch.title or not ch.cover_path:
            continue
        p = Path(ch.cover_path)
        generated = p.suffix.lower() == ".png" and (p.stem.startswith("couverture-") or p.stem == ch.id)
        if not generated or not p.exists():
            continue
        try:
            covers.generate_cover(personalize(ch.title, child), p, ch.description + " " + ch.text[:600], ch.bedtime,
                                  subtitle=project.metadata.title)
            n += 1
        except Exception as exc:
            log.warning("Couverture non redessinée : %s", exc)
    return n
