"""Vérification des nouvelles versions publiées sur GitHub (page « Releases »)."""

from __future__ import annotations

import json
import re
import urllib.request

from .. import __version__

UPDATE_REPO = "samouray333/https-samouray333.github.io-convertisseur-m4a-mp3-"
RELEASES_PAGE = f"https://github.com/{UPDATE_REPO}/releases"


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - min(3, len(nums)))


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def latest_release(timeout: float = 8.0) -> dict | None:
    """Dernière version publiée : {version, url, download, notes} ou None si indisponible."""
    req = urllib.request.Request(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": f"AudioLivreStudio/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tag = str(data.get("tag_name") or "").lstrip("vV")
    if not tag:
        return None
    download = next((a.get("browser_download_url") for a in data.get("assets", [])
                     if str(a.get("name", "")).lower().endswith(".exe")), None)
    return {"version": tag, "url": data.get("html_url") or RELEASES_PAGE, "download": download,
            "notes": data.get("body") or ""}


def check_for_update() -> dict | None:
    """Renvoie la version disponible si elle est plus récente que celle installée."""
    rel = latest_release()
    if rel and is_newer(rel["version"]):
        return rel
    return None
