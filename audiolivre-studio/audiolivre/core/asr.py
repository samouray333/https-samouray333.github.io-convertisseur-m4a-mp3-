"""Relecture automatique : compare ce que la voix a dit (Whisper) au texte attendu."""

from __future__ import annotations

import difflib
import re
import unicodedata

from .textproc import NormalizeOptions, normalize_for_speech


def _words(text: str, language: str) -> list[str]:
    text = normalize_for_speech(text, NormalizeOptions(language=language))
    text = unicodedata.normalize("NFC", text.lower())
    text = text.replace("’", "'")
    text = re.sub(r"[-'«»\"“”]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return [w for w in text.split() if w]


def word_error(expected: str, heard: str, language: str = "fr") -> float:
    """Taux d'erreur approximatif (0 = identique, 1 = rien de commun)."""
    exp = _words(expected, language)
    got = _words(heard, language)
    if not exp:
        return 0.0
    sm = difflib.SequenceMatcher(a=exp, b=got, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    errors = max(len(exp), len(got)) - matched
    return min(1.0, errors / max(1, len(exp)))


def asr_ready() -> bool:
    from . import engines

    tool = engines.get_tool("whisper")
    return tool is not None and tool.is_ready()
