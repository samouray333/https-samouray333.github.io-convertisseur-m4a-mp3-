"""Configuration de la journalisation (fichier tournant + console)."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from . import paths

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> str:
    log_file = paths.logs_dir() / "audiolivre.log"
    root = logging.getLogger()
    if getattr(root, "_audiolivre_configured", False):
        return str(log_file)
    root.setLevel(level)
    fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(fh)
    if sys.stderr is not None:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(sh)
    root._audiolivre_configured = True  # type: ignore[attr-defined]
    for noisy in ("asyncio", "urllib3", "aiohttp", "PIL", "fontTools"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return str(log_file)
