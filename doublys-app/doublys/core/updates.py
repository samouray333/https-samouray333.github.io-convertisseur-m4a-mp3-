"""Vérification des nouvelles versions publiées sur GitHub (page « Releases »)."""

from __future__ import annotations

import json
import re
import urllib.request

from .. import APP_ID, RELEASE_TAG_PREFIX, __version__

UPDATE_REPO = "samouray333/https-samouray333.github.io-convertisseur-m4a-mp3-"
RELEASES_PAGE = f"https://github.com/{UPDATE_REPO}/releases"


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - min(3, len(nums)))


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def latest_release(timeout: float = 8.0) -> dict | None:
    """Dernière version publiée de cette application : {version, url, download, notes} ou None.

    Le dépôt publie plusieurs applications : seules les versions dont l'étiquette commence par
    ``RELEASE_TAG_PREFIX`` (par exemple « podcast-v1.2.0 ») sont prises en compte."""
    req = urllib.request.Request(f"https://api.github.com/repos/{UPDATE_REPO}/releases?per_page=40",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": f"{APP_ID}/{__version__}"})
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
        if data.get("draft") or data.get("prerelease") or not tag.lower().startswith(RELEASE_TAG_PREFIX):
            continue
        version = tag[len(RELEASE_TAG_PREFIX):]
        if best is not None and parse_version(version) <= parse_version(best["version"]):
            continue
        assets = [a for a in data.get("assets", []) if isinstance(a, dict)]
        exe = next((a for a in assets if str(a.get("name", "")).lower().endswith(".exe")), None)
        download = exe.get("browser_download_url") if exe else None
        sha256 = ""
        sha256_url = None
        if exe:
            digest = str(exe.get("digest") or "")
            if digest.lower().startswith("sha256:"):
                sha256 = digest[7:].strip().lower()
            name = str(exe.get("name", "")).lower()
            sha256_url = next((a.get("browser_download_url") for a in assets
                               if str(a.get("name", "")).lower() in (name + ".sha256", "sha256sums.txt")), None)
        best = {"version": version, "url": data.get("html_url") or RELEASES_PAGE, "download": download,
                "sha256": sha256, "sha256_url": sha256_url, "notes": data.get("body") or ""}
    return best


def parse_checksum(text: str, filename: str) -> str:
    """Empreinte SHA-256 lue dans un fichier ``.sha256`` / ``SHA256SUMS.txt`` (format « empreinte  nom »)."""
    fallback = ""
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            continue
        name = parts[1].lstrip("*") if len(parts) > 1 else ""
        if not name or name.lower() == filename.lower():
            return parts[0].lower()
    return fallback


def expected_sha256(rel: dict, filename: str, timeout: float = 15.0) -> str:
    """Empreinte attendue de l'installateur : celle donnée par GitHub, sinon le fichier ``.sha256`` publié."""
    if rel.get("sha256"):
        return str(rel["sha256"])
    url = rel.get("sha256_url")
    if not url:
        return ""
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return parse_checksum(resp.read().decode("utf-8", "replace"), filename)
    except Exception:
        return ""


def file_sha256(path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class IntegrityError(RuntimeError):
    pass


def verify_installer(path, rel: dict) -> None:
    """Refuse un installateur dont l'empreinte est absente ou ne correspond pas (fichier abîmé ou modifié)."""
    from pathlib import Path

    path = Path(path)
    expected = expected_sha256(rel, path.name)
    if not expected:
        path.unlink(missing_ok=True)
        raise IntegrityError("Impossible de vérifier l'installateur (aucune empreinte SHA-256 publiée) : "
                             "installation automatique annulée par sécurité.")
    actual = file_sha256(path)
    if actual != expected:
        path.unlink(missing_ok=True)
        raise IntegrityError("L'installateur téléchargé ne correspond pas à la version publiée (empreinte "
                             "différente) : il a été supprimé. Réessayez plus tard.")


def check_for_update() -> dict | None:
    """Renvoie la version disponible si elle est plus récente que celle installée."""
    rel = latest_release()
    if rel and is_newer(rel["version"]):
        return rel
    return None
