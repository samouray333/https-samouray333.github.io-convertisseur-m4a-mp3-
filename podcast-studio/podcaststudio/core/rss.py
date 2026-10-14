"""Flux RSS du podcast (RSS 2.0 + balises iTunes reconnues par Apple Podcasts, Spotify, Deezer…).

Le flux décrit l'émission et chaque épisode ; les fichiers MP3 doivent être déposés en ligne à l'adresse
``BookMetadata.media_base_url`` (par exemple un site GitHub Pages gratuit), dans le dossier ``episodes``.
"""

from __future__ import annotations

import email.utils
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from .. import APP_NAME, __version__
from .models import BookMetadata

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CATEGORIES = {
    "Society & Culture": "Société et culture",
    "Education": "Éducation",
    "Arts": "Arts",
    "Business": "Économie et entreprise",
    "Comedy": "Humour",
    "Fiction": "Fiction",
    "Health & Fitness": "Santé et forme",
    "History": "Histoire",
    "Kids & Family": "Enfants et famille",
    "Leisure": "Loisirs",
    "Music": "Musique",
    "News": "Actualités",
    "Religion & Spirituality": "Religion et spiritualité",
    "Science": "Sciences",
    "Sports": "Sport",
    "Technology": "Technologie",
    "True Crime": "Faits divers",
    "TV & Film": "Cinéma et télévision",
}


def media_url(base_url: str, relative: str) -> str:
    """Adresse publique d'un fichier du dossier d'export (lien relatif sans adresse de publication)."""
    quoted = "/".join(urllib.parse.quote(part) for part in relative.replace("\\", "/").split("/"))
    if not base_url.strip():
        return quoted
    return base_url.strip().rstrip("/") + "/" + quoted


def rfc822(date: str, fallback: datetime) -> str:
    """Date au format des flux RSS ; ``date`` est AAAA-MM-JJ (vide ou invalide : ``fallback``)."""
    dt = fallback
    if date:
        try:
            dt = datetime.strptime(date[:10], "%Y-%m-%d").replace(hour=6, tzinfo=timezone.utc)
        except ValueError:
            pass
    return email.utils.format_datetime(dt)


def hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _el(tag: str, text: str, indent: int = 4) -> str:
    return f"{' ' * indent}<{tag}>{escape(text)}</{tag}>"


def build_feed(meta: BookMetadata, episodes: list, out_dir: Path, cover: Path | None = None,
               now: datetime | None = None, only_due: bool = False) -> str:
    """Texte XML du flux. ``episodes`` : [(ExportItem, fichier MP3, durée en secondes)] dans l'ordre d'écoute."""
    now = now or datetime.now(timezone.utc)
    base = meta.media_base_url.strip()
    title = meta.title or "Podcast"
    summary = meta.description or meta.subtitle or title
    lang = (meta.language or "fr").split("-")[0]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<rss version="2.0" xmlns:itunes="{ITUNES_NS}" xmlns:atom="http://www.w3.org/2005/Atom" '
             'xmlns:content="http://purl.org/rss/1.0/modules/content/" '
             'xmlns:podcast="https://podcastindex.org/namespace/1.0">',
             "  <channel>",
             _el("title", title),
             _el("description", summary),
             _el("language", lang),
             _el("generator", f"{APP_NAME} {__version__}"),
             _el("lastBuildDate", email.utils.format_datetime(now))]
    if meta.website or base:
        lines.append(_el("link", meta.website or base))
    if base:
        lines.append(f'    <atom:link href="{escape(media_url(base, "feed.xml"))}" rel="self" '
                     'type="application/rss+xml"/>')
    if meta.copyright:
        lines.append(_el("copyright", meta.copyright))
    if meta.author:
        lines.append(_el("itunes:author", meta.author))
    lines.append(_el("itunes:summary", summary))
    lines.append(_el("itunes:explicit", "true" if meta.explicit else "false"))
    lines.append("    <itunes:type>episodic</itunes:type>")
    category = meta.category or "Society & Culture"
    lines.append(f'    <itunes:category text="{escape(category, {chr(34): "&quot;"})}"/>')
    if meta.author or meta.owner_email:
        lines.append("    <itunes:owner>")
        lines.append(_el("itunes:name", meta.author or title, 6))
        if meta.owner_email:
            lines.append(_el("itunes:email", meta.owner_email, 6))
        lines.append("    </itunes:owner>")
    if cover is not None:
        img = media_url(base, cover.name)
        lines.append(f'    <itunes:image href="{escape(img)}"/>')
        lines += ["    <image>", _el("url", img, 6), _el("title", title, 6),
                  _el("link", meta.website or base or img, 6), "    </image>"]

    # Le plus récent en premier, comme dans tous les flux de podcast. Sans date, les épisodes sont espacés
    # d'une semaine en remontant depuis aujourd'hui, dans l'ordre de la liste.
    if only_due:  # épisodes programmés plus tard : absents du flux jusqu'à leur date
        today = now.strftime("%Y-%m-%d")
        episodes = [e for e in episodes if not e[0].pub_date or e[0].pub_date[:10] <= today]
    count = len(episodes)
    for pos, (it, mp3, duration) in reversed(list(enumerate(episodes))):
        fallback = now - timedelta(days=7 * (count - 1 - pos))
        rel = f"{mp3.parent.name}/{mp3.name}" if mp3.parent != out_dir else mp3.name
        try:
            size = mp3.stat().st_size
        except OSError:
            size = 0
        desc = it.description or it.title
        lines.append("    <item>")
        lines.append(_el("title", it.title, 6))
        lines.append(_el("description", desc, 6))
        lines.append(f"      <content:encoded><![CDATA[{_cdata(desc)}]]></content:encoded>")
        lines.append(_el("itunes:summary", desc, 6))
        lines.append(f'      <enclosure url="{escape(media_url(base, rel))}" length="{size}" type="audio/mpeg"/>')
        chap = mp3.with_suffix(".chapters.json")
        if chap.exists():
            crel = f"{chap.parent.name}/{chap.name}" if chap.parent != out_dir else chap.name
            lines.append(f'      <podcast:chapters url="{escape(media_url(base, crel))}" '
                         'type="application/json+chapters"/>')
        lines.append(f'      <guid isPermaLink="false">{escape(it.id or mp3.stem)}</guid>')
        lines.append(_el("pubDate", rfc822(it.pub_date, fallback), 6))
        lines.append(_el("itunes:duration", hms(duration), 6))
        lines.append(_el("itunes:episodeType", it.episode_type or "full", 6))
        if it.number and (it.episode_type or "full") == "full":
            lines.append(_el("itunes:episode", str(it.number), 6))
        if it.season:
            lines.append(_el("itunes:season", str(it.season), 6))
        lines.append(_el("itunes:explicit", "true" if meta.explicit else "false", 6))
        lines.append("    </item>")
    lines += ["  </channel>", "</rss>", ""]
    return "\n".join(lines)


def _cdata(text: str) -> str:
    paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    body = "".join(f"<p>{escape(p).replace(chr(10), '<br/>')}</p>" for p in paras)
    return body.replace("]]>", "]]&gt;")


def write_feed(meta: BookMetadata, episodes: list, target: Path, cover: Path | None = None,
               only_due: bool = False) -> Path:
    target.write_text(build_feed(meta, episodes, target.parent, cover, only_due=only_due), encoding="utf-8")
    return target


def today() -> str:
    return time.strftime("%Y-%m-%d")
