"""Registre des moteurs de synthèse vocale."""

from __future__ import annotations

import threading

from .base import (NOT_INSTALLED, READY, UNAVAILABLE, BuiltinVoice, EngineError, EngineInfo, ParamSpec,
                   ServiceBlocked, TTSEngine)

__all__ = ["all_engines", "get_engine", "get_tool", "all_tools", "shutdown_all", "register_engine", "TTSEngine",
           "EngineInfo", "EngineError", "ServiceBlocked", "BuiltinVoice", "ParamSpec", "READY", "NOT_INSTALLED", "UNAVAILABLE",
           "CLONING_ENGINES"]

_lock = threading.Lock()
_engines: dict[str, TTSEngine] | None = None
ORDER = ["edge", "xtts", "fastclone", "rvc", "chatterbox", "kokoro", "sapi"]
CLONING_ENGINES = ["xtts", "fastclone", "chatterbox"]
_tools: dict[str, TTSEngine] = {}


def _build() -> dict[str, TTSEngine]:
    from .edge import EdgeEngine
    from .neural import FastCloneEngine, RVCEngine, WorkerEngine
    from .sapi import SapiEngine

    return {
        "edge": EdgeEngine(),
        "xtts": WorkerEngine("xtts"),
        "fastclone": FastCloneEngine(),
        "rvc": RVCEngine(),
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


def get_tool(tool_id: str):
    """Outils neuronaux qui ne sont pas des voix (ex. Whisper pour la relecture)."""
    with _lock:
        if tool_id not in _tools and tool_id == "whisper":
            from .neural import WhisperTool

            _tools[tool_id] = WhisperTool()
        return _tools.get(tool_id)


def all_tools() -> list:
    return [t for t in (get_tool("whisper"),) if t is not None]


def shutdown_all() -> None:
    for t in list(_tools.values()):
        try:
            t.shutdown()
        except Exception:
            pass
    if _engines is None:
        return
    for e in list(_engines.values()):
        try:
            e.shutdown()
        except Exception:
            pass
