"""Exécution de tâches longues en arrière-plan sans figer l'interface."""

from __future__ import annotations

import logging
import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class TaskSignals(QObject):
    done = Signal(object)
    failed = Signal(str, str)
    progress = Signal(object)
    message = Signal(str)


class Task:
    """Lance ``fn`` dans un thread ; les rappels sont exécutés dans le thread de l'interface."""

    _running: set["Task"] = set()

    def __init__(self, fn: Callable[..., Any], *args, on_done=None, on_error=None, on_progress=None,
                 on_message=None, pass_reporter: bool = False, **kwargs):
        self.signals = TaskSignals()
        self.cancel_event = threading.Event()
        if on_done:
            self.signals.done.connect(on_done)
        if on_error:
            self.signals.failed.connect(on_error)
        if on_progress:
            self.signals.progress.connect(on_progress)
        if on_message:
            self.signals.message.connect(on_message)
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self._pass_reporter = pass_reporter
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "Task":
        Task._running.add(self)
        # la tâche reste référencée jusqu'à la livraison du résultat dans le thread de l'interface
        self.signals.done.connect(self._finish)
        self.signals.failed.connect(self._finish)
        self._thread.start()
        return self

    def _finish(self, *_args) -> None:
        Task._running.discard(self)

    def report(self, value: Any) -> None:
        self.signals.progress.emit(value)

    def say(self, msg: str) -> None:
        self.signals.message.emit(msg)

    def _run(self) -> None:
        try:
            if self._pass_reporter:
                res = self._fn(self, *self._args, **self._kwargs)
            else:
                res = self._fn(*self._args, **self._kwargs)
            self.signals.done.emit(res)
        except Exception as exc:  # noqa: BLE001
            log.exception("Tâche en échec")
            self.signals.failed.emit(str(exc) or exc.__class__.__name__, traceback.format_exc())

    def is_running(self) -> bool:
        return self._thread.is_alive()


def run(fn: Callable[..., Any], *args, **kwargs) -> Task:
    return Task(fn, *args, **kwargs).start()
