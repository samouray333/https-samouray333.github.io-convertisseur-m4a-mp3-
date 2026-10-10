"""Stockage local des secrets (clé d'API) : chiffrés avec le compte Windows (DPAPI) quand c'est possible."""

from __future__ import annotations

import base64
import sys


def protect(text: str) -> str:
    if not text:
        return ""
    if sys.platform == "win32":
        try:
            import win32crypt

            blob = win32crypt.CryptProtectData(text.encode("utf-8"), "AudioLivreStudio", None, None, None, 0)
            return "dpapi:" + base64.b64encode(blob).decode("ascii")
        except Exception:
            pass
    return "b64:" + base64.b64encode(text.encode("utf-8")).decode("ascii")


def unprotect(value: str) -> str:
    if not value:
        return ""
    try:
        if value.startswith("dpapi:"):
            import win32crypt

            _desc, data = win32crypt.CryptUnprotectData(base64.b64decode(value[6:]), None, None, None, 0)
            return data.decode("utf-8")
        if value.startswith("b64:"):
            return base64.b64decode(value[4:]).decode("utf-8")
    except Exception:
        return ""
    return value
