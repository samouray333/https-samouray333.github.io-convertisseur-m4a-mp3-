"""État partagé entre les pages : projet ouvert, lecteur, traitement en cours."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from ..core import project as project_io
from ..core.ffmpeg import Cancelled
from ..core.models import STEP_LABELS, Project
from . import tasks
from .player import AudioPlayer
from .widgets import toast

log = logging.getLogger(__name__)

# poids des étapes pour la barre de progression globale et le temps restant (ordinateur portable sans GPU)
STEP_WEIGHTS = {"extract": 0.02, "separate": 0.22, "transcribe": 0.18, "segment": 0.01, "speakers": 0.05,
                "translate": 0.07, "voices": 0.02, "dub": 0.38, "mix": 0.03, "export": 0.04}


class JobRunner(QObject):
    """Exécute une suite d'étapes dans un thread ; relaie l'avancement à l'interface."""

    started = Signal(str)  # titre
    progress = Signal(str, float, str, float, float)  # étape, fraction étape, message, fraction totale, restant (s)
    log_line = Signal(str)
    line_changed = Signal(str)
    finished = Signal(bool, str, object)  # réussi, message, résultat

    def __init__(self):
        super().__init__()
        self.cancel = threading.Event()
        self.running = False
        self.title = ""
        self._plan: list[str] = []
        self._done_weight = 0.0
        self._t0 = 0.0
        self._cur = ""
        self._stoppers: list[Callable[[], None]] = []

    def start(self, title: str, plan: list[str], fn: Callable, on_stop: list[Callable[[], None]] | None = None):
        """``fn(job)`` reçoit un ``pipeline.Job`` relié à ce lanceur ; ``plan`` : étapes prévues (pour le temps)."""
        from ..core.pipeline import Job

        if self.running:
            return None
        self.running = True
        self.title = title
        self.cancel = threading.Event()
        self._plan = list(plan) or ["export"]
        self._done_weight = 0.0
        self._cur = ""
        self._t0 = time.time()
        self._stoppers = list(on_stop or [])
        job = Job(on_progress=self._on_progress, on_log=self.log_line.emit, on_line=self.line_changed.emit,
                  cancel=self.cancel)
        self.started.emit(title)

        def work():
            from ..core.power import keep_awake

            with keep_awake():  # l'ordinateur ne se met pas en veille pendant un long doublage
                return fn(job)

        def done(res):
            self.running = False
            self.finished.emit(True, "", res)

        def fail(msg, tb):
            self.running = False
            if msg == "Cancelled" or self.cancel.is_set():
                self.finished.emit(False, "Traitement arrêté.", None)
            else:
                self.finished.emit(False, msg, None)

        self._task = tasks.run(_wrap_cancel(work), on_done=done, on_error=fail)
        return self._task

    def stop(self) -> None:
        if not self.running:
            return
        self.cancel.set()
        for fn in self._stoppers:  # les processus moteurs sont arrêtés (sinon un long calcul continuerait)
            try:
                fn()
            except Exception:
                log.debug("Arrêt du moteur", exc_info=True)

    def _total_weight(self) -> float:
        return sum(STEP_WEIGHTS.get(s, 0.05) for s in self._plan) or 1.0

    def _on_progress(self, step: str, frac: float, msg: str) -> None:
        if step != self._cur:
            if self._cur in self._plan:
                self._done_weight += STEP_WEIGHTS.get(self._cur, 0.05)
            self._cur = step
        total = self._total_weight()
        w = STEP_WEIGHTS.get(step, 0.05) if step in self._plan else 0.0
        overall = max(0.0, min(1.0, (self._done_weight + w * frac) / total))
        elapsed = time.time() - self._t0
        remaining = elapsed * (1 - overall) / overall if overall > 0.03 and elapsed > 5 else -1.0
        self.progress.emit(step, frac, msg or STEP_LABELS.get(step, ""), overall, remaining)


def _wrap_cancel(fn):
    def inner():
        try:
            return fn()
        except Cancelled:
            raise RuntimeError("Cancelled") from None
    return inner


class AppContext(QObject):
    project_changed = Signal()  # nouveau projet chargé
    project_modified = Signal()  # contenu modifié
    lines_changed = Signal()  # répliques (ajout, suppression, texte)
    people_changed = Signal()
    engines_changed = Signal()
    navigate_requested = Signal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.project: Project | None = None
        self.player = AudioPlayer()
        self.runner = JobRunner()
        self.dirty = False
        self.player.error.connect(lambda m: self.toast(m, "error"))
        self._save_lock = threading.Lock()

    # -- état du projet ----------------------------------------------------------------
    def mark_dirty(self) -> None:
        self.dirty = True
        self.project_modified.emit()

    def set_project(self, project: Project | None) -> None:
        self.project = project
        self.dirty = False
        self.project_changed.emit()

    def save(self) -> bool:
        if self.project is None or self.project.path is None:
            return False
        with self._save_lock:
            project_io.save_project(self.project)
        self.dirty = False
        return True

    # -- utilitaires -------------------------------------------------------------------
    def toast(self, message: str, kind: str = "info", duration: int = 3800) -> None:
        toast(self.window, message, kind, duration)

    def navigate(self, page: str) -> None:
        self.navigate_requested.emit(page)

    def play(self, path: str | Path, title: str = "", start: float = 0.0, end: float | None = None) -> None:
        self.player.play_file(path, title, start, end)


def format_exc_short(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()
