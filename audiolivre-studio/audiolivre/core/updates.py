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
    """Dernière version publiée : {version, url, download, notes} ou None si indisponible.

    Le dépôt publie aussi PodCast Studio (« podcast-v… ») et Leçon Studio (« lecon-v… ») : seules les
    étiquettes « v1.2.3 » d'AudioLivre Studio sont prises en compte."""
    req = urllib.request.Request(f"https://api.github.com/repos/{UPDATE_REPO}/releases?per_page=40",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": f"AudioLivreStudio/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            releases = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return pick_release(releases)


def pick_release(releases: list[dict]) -> dict | None:
    best = None
    for data in releases if isinstance(releases, list) else []:
        tag = str(data.get("tag_name") or "")
        if data.get("draft") or data.get("prerelease") or not re.match(r"^[vV]?\d", tag):
            continue
        version = tag.lstrip("vV")
        if best is not None and parse_version(version) <= parse_version(best["version"]):
            continue
        download = next((a.get("browser_download_url") for a in data.get("assets", [])
                         if str(a.get("name", "")).lower().endswith(".exe")), None)
        best = {"version": version, "url": data.get("html_url") or RELEASES_PAGE, "download": download,
                "notes": data.get("body") or ""}
    return best


def check_for_update() -> dict | None:
    """Renvoie la version disponible si elle est plus récente que celle installée."""
    rel = latest_release()
    if rel and is_newer(rel["version"]):
        return rel
    return None
