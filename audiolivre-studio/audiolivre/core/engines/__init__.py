"""Registre des moteurs de synthèse vocale."""

from __future__ import annotations

import threading

from .base import NOT_INSTALLED, READY, UNAVAILABLE, BuiltinVoice, EngineError, EngineInfo, ParamSpec, TTSEngine

__all__ = ["all_engines", "get_engine", "shutdown_all", "register_engine", "TTSEngine", "EngineInfo",
           "EngineError", "BuiltinVoice", "ParamSpec", "READY", "NOT_INSTALLED", "UNAVAILABLE"]

_lock = threading.Lock()
_engines: dict[str, TTSEngine] | None = None
ORDER = ["edge", "xtts", "chatterbox", "kokoro", "sapi"]


def _build() -> dict[str, TTSEngine]:
    from .edge import EdgeEngine
    from .neural import WorkerEngine
    from .sapi import SapiEngine

    return {
        "edge": EdgeEngine(),
        "xtts": WorkerEngine("xtts"),
        "chatterbox": WorkerEngine("chatterbox"),
        "kokoro": WorkerEngine("kokoro"),
        "sapi": SapiEngine(),
    }


def _registry() -> dict[str, TTSEngine]:
    global _engines
    with _lock:
        if _engines is None:
            _engines = _build()
        return _engines


def all_engines() -> list[TTSEngine]:
    reg = _registry()
    return [reg[k] for k in ORDER if k in reg] + [v for k, v in reg.items() if k not in ORDER]


def get_engine(engine_id: str) -> TTSEngine | None:
    return _registry().get(engine_id)


def register_engine(engine: TTSEngine) -> None:
    _registry()[engine.info.id] = engine


def shutdown_all() -> None:
    if _engines is None:
        return
    for e in list(_engines.values()):
        try:
            e.shutdown()
        except Exception:
            pass
