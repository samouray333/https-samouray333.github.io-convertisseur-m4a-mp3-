"""État partagé entre les pages de l'interface."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..config import settings
from ..core.models import Project, VoiceProfile
from ..core.voices import VoiceLibrary, library
from . import tasks
from .player import AudioPlayer
from .widgets import toast

log = logging.getLogger(__name__)


class AppContext(QObject):
    project_changed = Signal()  # nouveau projet chargé
    project_modified = Signal()  # contenu modifié
    voices_changed = Signal()
    engines_changed = Signal()
    chapters_changed = Signal()
    render_finished = Signal()
    navigate_requested = Signal(str)
    production_requested = Signal(list)  # identifiants de chapitres (vide = tout)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.project: Project = Project()
        self.library: VoiceLibrary = library()
        self.player = AudioPlayer()
        self.dirty = False
        self.rendering = False
        self.player.error.connect(lambda m: self.toast(m, "error"))

    # -- état du projet ----------------------------------------------------------------
    def mark_dirty(self) -> None:
        self.dirty = True
        self.project_modified.emit()

    def set_project(self, project: Project) -> None:
        self.project = project
        self.dirty = False
        if not project.narrator_voice_id:
            default = settings().get("default_voice_id") or ""
            voice = self.library.get(default) or (self.library.all()[0] if self.library.all() else None)
            if voice is not None:
                project.narrator_voice_id = voice.id
                self.dirty = project.path is not None
        self.project_changed.emit()

    # -- utilitaires -------------------------------------------------------------------
    def toast(self, message: str, kind: str = "info", duration: int = 3800) -> None:
        toast(self.window, message, kind, duration)

    def navigate(self, page: str) -> None:
        self.navigate_requested.emit(page)

    def play(self, path: str | Path, title: str = "", start: float = 0.0, end: float | None = None) -> None:
        self.player.play_file(path, title, start, end)

    def preview_voice(self, voice: VoiceProfile, text: str | None = None, on_done=None,
                      project: Project | None = None) -> tasks.Task:
        from ..core import renderer

        sample = text or settings().get("preview_sentence")
        language = None
        if voice.language == "en" and not text:
            language = "en"
            sample = ("Hello, I am the voice that will read your book. Once upon a time, in a small village "
                      "by the sea, an extraordinary story began.")

        def done(path):
            self.play(path, f"Aperçu — {voice.name}")
            if on_done:
                on_done(True)

        def fail(msg, _tb):
            self.toast(f"Aperçu impossible : {msg}", "error", 6500)
            if on_done:
                on_done(False)

        self.toast(f"Génération de l'aperçu « {voice.name} »…", "info", 2200)
        return tasks.run(renderer.preview, sample, voice, project or self.project, language, on_done=done,
                         on_error=fail)
