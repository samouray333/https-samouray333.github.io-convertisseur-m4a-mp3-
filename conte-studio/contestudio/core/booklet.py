"""Livret à lire en même temps que l'histoire : texte du conte en gros caractères, couverture, répliques des
personnages en couleur. Exporté en HTML (à ouvrir dans le navigateur) et en PDF (à imprimer)."""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path

from .textproc import (AMBIENCE_RE, CHARACTER_LINE_RE, EMOTION_END_RE, EMPHASIS_RE, MARK_RE, PAUSE_RE, RATE_END_RE,
                       SOUND_RE, VOICE_END_RE, VOICE_SWITCH_RE, parse_prefixes, personalize, strip_podcast_prefixes)

PALETTE = ["#C2185B", "#1565C0", "#2E7D32", "#6A1B9A", "#EF6C00", "#00838F", "#AD1457", "#4E342E"]


@dataclass
class BookletStory:
    title: str
    text: str
    cover: str = ""  # image de l'histoire
    summary: str = ""
    moral: str = ""
    duration: float = 0.0  # secondes (0 = inconnue)


@dataclass
class Block:
    kind: str  # heading | narration | line | sound
    text: str
    speaker: str = ""


@dataclass
class BookletOptions:
    title: str = "Mes histoires"
    subtitle: str = ""
    author: str = ""
    child_name: str = ""
    font_pt: int = 20
    cover: str = ""  # couverture de la collection
    colors: dict[str, str] = field(default_factory=dict)  # couleur des personnages


def script_blocks(text: str, child_name: str = "", sound_labels: dict[str, str] | None = None) -> list[Block]:
    """Ce que l'enfant lit : les balises techniques (émotions, pauses, ambiances…) sont retirées, les bruitages
    deviennent de petites indications."""
    from . import sounds

    labels = sound_labels or sounds.BUILTIN_LABELS
    blocks: list[Block] = []
    paragraphs = re.split(r"\n\s*\n|\n(?=#)|\n(?=@)|\n(?=\[)|(?<=\])\n", personalize(text, child_name)
                          .replace("\r\n", "\n"))
    for raw in paragraphs:
        para = " ".join(ln.strip() for ln in raw.split("\n") if not ln.strip().startswith("%%")).strip()
        if not para or VOICE_SWITCH_RE.match(para) or VOICE_END_RE.match(para) or EMOTION_END_RE.match(para) \
                or RATE_END_RE.match(para) or MARK_RE.fullmatch(para) or AMBIENCE_RE.fullmatch(para):
            continue
        hm = re.match(r"^#{1,6}\s*(.+)$", para)
        if hm:
            blocks.append(Block("heading", hm.group(1).strip()))
            continue
        speaker = ""
        cm = CHARACTER_LINE_RE.match(para)
        if cm:
            speaker = cm.group(1).strip()
            if speaker.lower() in ("narrateur", "narratrice"):
                speaker = ""
            para = cm.group(2)
        para = strip_podcast_prefixes(para)[0]
        para = parse_prefixes(para)[0]
        para = strip_podcast_prefixes(para)[0]
        # bruitages en ligne : indiqués entre les morceaux de texte
        pos = 0
        pieces: list[Block] = []
        for sm in SOUND_RE.finditer(para):
            before = para[pos:sm.start()]
            if before.strip():
                pieces.append(Block("line" if speaker else "narration", before, speaker))
            name = (sm.group(1) or sm.group(2) or "").strip()
            key = sounds.resolve_name(name) or name
            pieces.append(Block("sound", labels.get(key, name)))
            pos = sm.end()
        rest = para[pos:]
        if rest.strip():
            pieces.append(Block("line" if speaker else "narration", rest, speaker))
        for b in pieces:
            if b.kind != "sound":
                b.text = " ".join(AMBIENCE_RE.sub("", PAUSE_RE.sub("", MARK_RE.sub("", b.text))).split())
            if b.text:
                blocks.append(b)
    return blocks


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    return EMPHASIS_RE.sub(lambda m: f"<b>{m.group(1)}</b>", out)


def _data_uri(path: str) -> str:
    p = Path(path)
    if not path or not p.is_file():
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def _duration(seconds: float) -> str:
    if seconds <= 0:
        return ""
    m = int(round(seconds / 60))
    return f"{max(1, m)} min d'écoute"


def color_for(name: str, colors: dict[str, str]) -> str:
    if name in colors:
        return colors[name]
    return PALETTE[sum(map(ord, name)) % len(PALETTE)]


def render_html(stories: list[BookletStory], opts: BookletOptions, image_src=None, for_print: bool = False) -> str:
    """Livret complet. ``image_src(chemin) -> adresse`` (par défaut : image incluse dans le fichier).

    Les styles principaux sont écrits sur chaque élément : le moteur PDF de Qt ne lit qu'une partie du CSS."""
    image_src = image_src or _data_uri
    size = max(12, min(40, int(opts.font_pt)))
    blue, brown = "#3B82F6", "#7A6A3A"

    def pt(f: float) -> str:
        return f"font-size:{int(round(size * f))}pt;"

    def picture(src: str, width: int) -> str:
        size_attr = "" if for_print else f' width="{width}"'  # PDF : image déjà mise à la bonne taille
        return (f'<p align="center" style="text-align:center; line-height:100%;">'
                f'<img class="cover" src="{src}"{size_attr}></p>')

    def heading(text: str, factor: float, level: int) -> str:
        # paragraphe en gras plutôt que <h1>/<h2> : le moteur PDF de Qt impose sa propre taille aux titres
        return (f'<p class="h{level}" align="center" style="{pt(factor)} color:{blue}; font-weight:bold; '
                f'text-align:center; margin-top:12px;">{html.escape(text)}</p>')

    parts: list[str] = ['<div class="front">']
    cover = image_src(opts.cover) if opts.cover else ""
    if cover:
        parts.append(picture(cover, 360 if for_print else 480))
    parts.append(heading(opts.title, 1.9, 1))
    if opts.subtitle:
        parts.append(f'<p align="center" style="{pt(0.75)} color:{brown};">{html.escape(opts.subtitle)}</p>')
    if len(stories) > 1:
        parts.append(f'<ol style="{pt(0.9)}">' + "".join(
            f"<li>{html.escape(s.title)}" + (f' <span style="color:{brown}; {pt(0.7)}">· {_duration(s.duration)}'
                                              "</span>" if s.duration else "") + "</li>" for s in stories) + "</ol>")
    if opts.author:
        parts.append(f'<p align="center" style="{pt(0.75)} color:{brown};">{html.escape(opts.author)}</p>')
    parts.append("</div>")
    for st in stories:
        parts.append('<div class="story" style="page-break-before: always;">')
        img = image_src(st.cover) if st.cover and st.cover != opts.cover else ""
        if img:
            parts.append(picture(img, 260 if for_print else 320))
        parts.append(heading(st.title, 1.5, 2))
        if st.duration:
            parts.append(f'<p align="center" style="{pt(0.7)} color:{brown};">{_duration(st.duration)}</p>')
        if st.summary:
            parts.append(f'<p align="center" style="{pt(0.8)} color:#555555; font-style:italic;">'
                         f"{html.escape(st.summary)}</p>")
        for b in script_blocks(st.text, opts.child_name):
            if b.kind == "heading":
                parts.append(heading(b.text, 1.15, 3))
            elif b.kind == "sound":
                parts.append(f'<p align="center" style="{pt(0.7)} color:#9A8A5A; font-style:italic;">'
                             f"♪ {html.escape(b.text)}</p>")
            elif b.kind == "line":
                c = color_for(b.speaker, opts.colors)
                parts.append(f'<p style="{pt(1)} margin-left:28px; color:{c};">'
                             f'<span style="{pt(0.75)} font-weight:bold;">{html.escape(b.speaker.upper())}</span>'
                             f"<br>« {_inline(b.text)} »</p>")
            else:
                parts.append(f'<p style="{pt(1)}">{_inline(b.text)}</p>')
        if st.moral:
            parts.append(f'<p class="moral" align="center" style="{pt(1)} background-color:#FFF0C2;">'
                         f"{html.escape(st.moral)}</p>")
        parts.append(f'<p align="center" style="{pt(1.1)} color:{blue}; font-weight:bold;">Fin</p></div>')
    body = "\n".join(parts)
    css = f"""
body {{ font-family: 'Comic Sans MS', 'Segoe Print', 'Arial Rounded MT Bold', Verdana, sans-serif;
       font-size: {size}pt; line-height: 1.6; color: #1D2A6B; background: #FFF9EE; margin: 0; }}
.front, .story {{ max-width: 900px; margin: 0 auto; padding: 36px 48px; }}
.story {{ break-before: page; }}
.cover {{ border-radius: 24px; box-shadow: 0 6px 24px rgba(29,42,107,.25); max-width: 100%; height: auto; }}
.moral {{ margin-top: 28px; padding: 14px 20px; border-radius: 16px; }}
@media print {{ body {{ background: white; }} .cover {{ box-shadow: none; }} }}
"""
    return (f'<!DOCTYPE html>\n<html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(opts.title)}</title><style>{css}</style></head>"
            f'<body style="font-size:{size}pt; color:#1D2A6B;">{body}</body></html>')


def write_html(stories: list[BookletStory], opts: BookletOptions, target: str | Path) -> Path:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(stories, opts), encoding="utf-8")
    return target


def write_pdf(stories: list[BookletStory], opts: BookletOptions, target: str | Path) -> Path:
    """Livret imprimable A4 (mise en page de Qt, sans logiciel supplémentaire)."""
    from PySide6.QtCore import QMarginsF, QSizeF, Qt, QUrl
    from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPdfWriter, QTextDocument

    from .covers import _ensure_gui

    _ensure_gui()
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = QTextDocument()
    images: dict[str, str] = {}

    def image_src(path: str) -> str:
        if not path or not Path(path).is_file():
            return ""
        if path not in images:
            name = f"image{len(images)}"
            img = QImage(path)
            if img.isNull():
                return ""
            width = 520 if not images else 380  # couverture de la collection, puis celles des histoires
            img = img.scaledToWidth(width, Qt.SmoothTransformation)
            doc.addResource(QTextDocument.ImageResource, QUrl(name), img)
            images[path] = name
        return images[path]

    writer = QPdfWriter(str(target))
    writer.setTitle(opts.title)
    writer.setCreator("Conte Studio")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(16, 16, 16, 16),
                                     QPageLayout.Millimeter))
    writer.setResolution(150)
    doc.setHtml(render_html(stories, opts, image_src, for_print=True))
    doc.setPageSize(QSizeF(writer.width(), writer.height()))
    doc.print_(writer)
    return target
