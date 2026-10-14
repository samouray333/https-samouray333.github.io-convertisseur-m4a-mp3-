"""Empêche la mise en veille de Windows pendant une longue production."""

from __future__ import annotations

import sys
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextmanager
def keep_awake():
    """L'écran peut s'éteindre, mais l'ordinateur ne se met pas en veille tant que le bloc s'exécute."""
    active = False
    if sys.platform.startswith("win"):
        try:
            import ctypes

            active = bool(ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
        except Exception:
            active = False
    try:
        yield active
    finally:
        if active:
            try:
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            except Exception:
                pass
