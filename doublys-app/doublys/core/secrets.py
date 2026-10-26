"""Stockage local des secrets (clé d'API) : chiffrés avec le compte Windows (DPAPI) quand c'est possible."""

from __future__ import annotations

import base64
import logging
import sys

log = logging.getLogger(__name__)


def protect(text: str) -> str:
    if not text:
        return ""
    if sys.platform == "win32":
        try:
            import win32crypt

            blob = win32crypt.CryptProtectData(text.encode("utf-8"), "Doublys", None, None, None, 0)
            return "dpapi:" + base64.b64encode(blob).decode("ascii")
        except Exception:
            log.warning("Chiffrement DPAPI indisponible : la clé est enregistrée sans chiffrement", exc_info=True)
    else:
        log.info("Hors Windows : la clé est enregistrée sans chiffrement (simple encodage base64)")
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
        log.warning("Clé enregistrée illisible (autre compte Windows ou fichier abîmé) : à ressaisir",
                    exc_info=True)
        return ""
    return value


def is_encrypted(value: str) -> bool:
    """La valeur enregistrée est-elle réellement chiffrée (et pas seulement encodée) ?"""
    return bool(value) and value.startswith("dpapi:")
