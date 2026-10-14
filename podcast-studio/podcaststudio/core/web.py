"""Récupération du texte d'une page web (article) pour en faire un épisode."""

from __future__ import annotations

import re
import ssl
import urllib.request

from .. import APP_ID, __version__

MAX_BYTES = 6_000_000


class WebError(RuntimeError):
    pass


def _context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def fetch_html(url: str, timeout: float = 25) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    req = urllib.request.Request(url, headers={
        "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {APP_ID}/{__version__}",
        "Accept": "text/html,application/xhtml+xml", "Accept-Language": "fr,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_context()) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype and "xml" not in ctype and ctype:
                raise WebError("Cette adresse n'est pas une page web (fichier ou image).")
            raw = resp.read(MAX_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
    except WebError:
        raise
    except Exception as exc:
        raise WebError(f"Page inaccessible ({exc}). Vérifiez l'adresse et votre connexion Internet.") from None
    return raw.decode(charset, errors="replace")


def extract_article(html: str) -> tuple[str, str]:
    """(titre, texte) : le contenu principal de la page, sans menus, publicités ni pied de page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg",
                     "button", "figure"]):
        tag.decompose()
    title = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()
    candidates = soup.find_all("article") or soup.find_all("main") or [soup.body or soup]
    best = max(candidates, key=lambda el: len(el.get_text(" ", strip=True)))
    blocks = []
    for el in best.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if len(text) < 25 and el.name not in ("h1", "h2", "h3"):
            continue
        if el.name in ("h1", "h2", "h3"):
            text = "# " + text
        if not blocks or blocks[-1] != text:
            blocks.append(text)
    body = "\n\n".join(blocks).strip()
    if len(body) < 80:  # page sans paragraphes balisés : tout le texte du bloc principal
        body = " ".join(best.get_text(" ", strip=True).split())
    if len(body) < 80:
        raise WebError("Aucun article lisible n'a été trouvé sur cette page.")
    return title, body


def fetch_article(url: str) -> tuple[str, str]:
    return extract_article(fetch_html(url))
