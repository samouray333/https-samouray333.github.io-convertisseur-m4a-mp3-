"""Import de documents (Word, PDF, EPUB, ODT, RTF, HTML, Markdown, texte) avec détection des chapitres."""

from __future__ import annotations

import logging
import re
import statistics
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import BookMetadata, Chapter

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".docx": "Document Word",
    ".pdf": "Document PDF",
    ".epub": "Livre numérique EPUB",
    ".odt": "Document OpenDocument",
    ".rtf": "Texte enrichi RTF",
    ".txt": "Texte brut",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".html": "Page HTML",
    ".htm": "Page HTML",
}

FILE_FILTER = "Documents ({});;Tous les fichiers (*)".format(
    " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)
)

# Titres de chapitres reconnus dans le texte brut
CHAPTER_RE = re.compile(
    r"^\s*(?:"
    r"(?:chapitre|chapter|partie|part|livre|book|prologue|épilogue|epilogue|préface|preface|"
    r"avant-propos|introduction|conclusion|postface|interlude|annexe|appendix)\b[^\n]{0,80}"
    r"|[IVXLC]{1,7}\.?"  # chiffres romains seuls
    r"|\d{1,3}\.?"  # numéros seuls
    r"|\*{3}|\* \* \*"
    r")\s*$",
    re.IGNORECASE,
)


class ImportErrorUser(Exception):
    """Erreur d'import affichable à l'utilisateur."""


@dataclass
class ImportedDocument:
    chapters: list[Chapter] = field(default_factory=list)
    metadata: BookMetadata = field(default_factory=BookMetadata)
    cover_bytes: bytes | None = None
    cover_ext: str = ".jpg"
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Block:
    text: str
    level: int = 0  # 0 = paragraphe, 1..3 = titres


# ---------------------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------------------
def import_document(path: str | Path, split_chapters: bool = True) -> ImportedDocument:
    p = Path(path)
    if not p.exists():
        raise ImportErrorUser(f"Fichier introuvable : {p}")
    ext = p.suffix.lower()
    try:
        if ext == ".docx":
            doc = _import_docx(p)
        elif ext == ".pdf":
            doc = _import_pdf(p)
        elif ext == ".epub":
            doc = _import_epub(p)
        elif ext == ".odt":
            doc = _from_blocks(_odt_blocks(p))
        elif ext == ".rtf":
            doc = _from_blocks(_text_blocks(_read_rtf(p)))
        elif ext in (".html", ".htm"):
            doc = _from_blocks(_html_blocks(_read_text(p)))
        elif ext in (".md", ".markdown"):
            doc = _from_blocks(_markdown_blocks(_read_text(p)))
        elif ext == ".txt" or ext == "":
            doc = _from_blocks(_text_blocks(_read_text(p)))
        elif ext == ".doc":
            raise ImportErrorUser(
                "Le format .doc (Word 97-2003) n'est pas pris en charge. "
                "Ouvrez-le dans Word et enregistrez-le au format .docx."
            )
        else:
            raise ImportErrorUser(f"Format non pris en charge : {ext}")
    except ImportErrorUser:
        raise
    except Exception as exc:  # pragma: no cover - dépend des fichiers
        log.exception("Échec de l'import de %s", p)
        raise ImportErrorUser(f"Impossible de lire « {p.name} » : {exc}") from exc

    if not doc.metadata.title:
        doc.metadata.title = _title_from_filename(p)
    if not split_chapters and doc.chapters:
        merged = "\n\n".join(
            (f"# {c.title}\n\n{c.text}" if c.title else c.text) for c in doc.chapters if c.text.strip()
        )
        doc.chapters = [Chapter(title=doc.metadata.title or "Texte intégral", text=merged)]
    doc.chapters = [c for c in doc.chapters if c.text.strip() or c.title.strip()]
    if not doc.chapters:
        raise ImportErrorUser(
            "Aucun texte n'a été trouvé dans ce document. S'il s'agit d'un PDF scanné (images), "
            "il faut d'abord le passer dans un logiciel de reconnaissance de caractères (OCR)."
        )
    for i, ch in enumerate(doc.chapters, 1):
        if not ch.title.strip():
            ch.title = f"Chapitre {i}"
    return doc


def _title_from_filename(p: Path) -> str:
    name = re.sub(r"[_]+", " ", p.stem).strip()
    return name[:1].upper() + name[1:] if name else "Sans titre"


def _read_text(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return text
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------------------
# Construction des chapitres à partir de blocs
# ---------------------------------------------------------------------------------------
def _from_blocks(blocks: list[_Block], metadata: BookMetadata | None = None) -> ImportedDocument:
    doc = ImportedDocument(metadata=metadata or BookMetadata())
    doc.chapters = blocks_to_chapters(blocks)
    return doc


def blocks_to_chapters(blocks: list[_Block]) -> list[Chapter]:
    blocks = [b for b in blocks if b.text.strip()]
    if not blocks:
        return []
    levels = sorted({b.level for b in blocks if b.level > 0})
    chapters: list[Chapter] = []
    if levels:
        # On coupe au niveau de titre le plus haut présent au moins deux fois, sinon au plus haut.
        counts = Counter(b.level for b in blocks if b.level > 0)
        split_level = next((lv for lv in levels if counts[lv] >= 2), levels[0])
        current: Chapter | None = None
        preamble: list[str] = []
        for b in blocks:
            if b.level and b.level <= split_level:
                if current is not None:
                    chapters.append(current)
                current = Chapter(title=_clean_title(b.text), text="")
                continue
            line = (("#" * max(1, b.level - split_level)) + " " + b.text.strip()) if b.level else b.text.strip()
            if current is None:
                preamble.append(line)
            else:
                current.text = (current.text + "\n\n" + line) if current.text else line
        if current is not None:
            chapters.append(current)
        if preamble:
            text = "\n\n".join(preamble)
            if len(text.split()) > 25:
                chapters.insert(0, Chapter(title="Ouverture", text=text))
            elif chapters:
                chapters[0].text = text + "\n\n" + chapters[0].text
        return chapters

    # Pas de styles de titres : recherche de motifs « Chapitre X ».
    current = None
    preamble = []
    found = False
    for b in blocks:
        t = b.text.strip()
        if len(t) < 90 and CHAPTER_RE.match(t) and not t.startswith("*"):
            found = True
            if current is not None:
                chapters.append(current)
            current = Chapter(title=_clean_title(t), text="")
            continue
        if current is None:
            preamble.append(t)
        else:
            current.text = (current.text + "\n\n" + t) if current.text else t
    if current is not None:
        chapters.append(current)
    if not found:
        return _split_by_size("\n\n".join(b.text.strip() for b in blocks))
    if preamble:
        text = "\n\n".join(preamble)
        if len(text.split()) > 25:
            chapters.insert(0, Chapter(title="Ouverture", text=text))
        elif chapters:
            chapters[0].text = text + "\n\n" + chapters[0].text
    # Fusionne les titres consécutifs (« Chapitre 1 » suivi de « Le départ »)
    merged: list[Chapter] = []
    for ch in chapters:
        if merged and not merged[-1].text.strip():
            merged[-1].title = f"{merged[-1].title} — {ch.title}"
            merged[-1].text = ch.text
        else:
            merged.append(ch)
    return merged


def _split_by_size(text: str, target_words: int = 4500) -> list[Chapter]:
    """Découpe un long texte sans titres en parties d'environ 30 minutes."""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    total = sum(len(p.split()) for p in paras)
    if total <= target_words * 1.5:
        return [Chapter(title="Texte intégral", text="\n\n".join(paras))]
    chapters: list[Chapter] = []
    buf: list[str] = []
    count = 0
    for p in paras:
        buf.append(p)
        count += len(p.split())
        if count >= target_words:
            chapters.append(Chapter(title=f"Partie {len(chapters) + 1}", text="\n\n".join(buf)))
            buf, count = [], 0
    if buf:
        chapters.append(Chapter(title=f"Partie {len(chapters) + 1}", text="\n\n".join(buf)))
    return chapters


def _clean_title(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip().strip("#").strip()
    return t[:120]


# ---------------------------------------------------------------------------------------
# Texte brut / Markdown / HTML / RTF / ODT
# ---------------------------------------------------------------------------------------
def _text_blocks(text: str) -> list[_Block]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paras = re.split(r"\n\s*\n", text)
    if len(paras) <= 2 and text.count("\n") > 20:
        # Fichier avec un paragraphe par ligne
        paras = text.split("\n")
    blocks = []
    for p in paras:
        p = re.sub(r"[ \t]*\n[ \t]*", " ", p.strip())
        if p:
            blocks.append(_Block(p))
    return blocks


def _markdown_blocks(text: str) -> list[_Block]:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    blocks: list[_Block] = []
    para: list[str] = []

    def flush():
        if para:
            blocks.append(_Block(_strip_md(" ".join(para))))
            para.clear()

    for line in text.split("\n"):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            blocks.append(_Block(_strip_md(m.group(2)), level=min(len(m.group(1)), 3)))
        elif not line.strip():
            flush()
        else:
            para.append(line.strip())
    flush()
    return blocks


def _strip_md(s: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"(\*\*|__|\*|_|`)", "", s)
    s = re.sub(r"^\s*[-*+>]\s+", "", s)
    return s.strip()


def _html_blocks(html: str) -> list[_Block]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "sup"]):
        tag.decompose()
    blocks: list[_Block] = []
    body = soup.body or soup
    for el in body.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "div"]):
        if el.name == "div" and el.find(["p", "h1", "h2", "h3", "h4", "div", "li"]):
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if not text:
            continue
        level = int(el.name[1]) if el.name in ("h1", "h2", "h3") else (3 if el.name == "h4" else 0)
        blocks.append(_Block(text, level=level))
    return blocks


def _read_rtf(p: Path) -> str:
    from striprtf.striprtf import rtf_to_text

    return rtf_to_text(_read_text(p), errors="ignore")


_ODT_NS = {
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}


def _odt_blocks(p: Path) -> list[_Block]:
    with zipfile.ZipFile(p) as zf:
        root = ET.fromstring(zf.read("content.xml"))
    blocks: list[_Block] = []
    t_ns = "{%s}" % _ODT_NS["text"]
    body = root.find("office:body", _ODT_NS)
    if body is None:
        return blocks
    for el in body.iter():
        if el.tag == t_ns + "h":
            level = int(el.get(t_ns + "outline-level", "1") or 1)
            blocks.append(_Block(_odt_text(el), level=min(level, 3)))
        elif el.tag == t_ns + "p":
            blocks.append(_Block(_odt_text(el)))
    return blocks


def _odt_text(el) -> str:
    t_ns = "{%s}" % _ODT_NS["text"]
    parts: list[str] = []

    def walk(node):
        if node.tag in (t_ns + "note",):
            return  # notes de bas de page ignorées
        if node.text:
            parts.append(node.text)
        for child in node:
            if child.tag == t_ns + "s":
                parts.append(" " * int(child.get(t_ns + "c", "1") or 1))
            elif child.tag in (t_ns + "tab", t_ns + "line-break"):
                parts.append(" ")
            else:
                walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


# ---------------------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------------------
_HEADING_STYLE_RE = re.compile(r"^(heading|titre|título|titolo|überschrift|kop)\s*(\d)", re.IGNORECASE)


def _import_docx(p: Path) -> ImportedDocument:
    import docx  # python-docx

    d = docx.Document(str(p))
    blocks: list[_Block] = []
    for para in d.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name if para.style is not None else "") or ""
        level = 0
        m = _HEADING_STYLE_RE.match(style)
        if m:
            level = min(int(m.group(2)), 3)
        elif style.lower() in ("title", "titre"):
            level = 1
        else:
            outline = _docx_outline_level(para)
            if outline is not None and outline < 3:
                level = outline + 1
        blocks.append(_Block(text, level=level))

    meta = BookMetadata()
    cp = d.core_properties
    if cp.title:
        meta.title = cp.title.strip()
    if cp.author:
        meta.author = cp.author.strip()
    if cp.subject:
        meta.description = cp.subject.strip()
    if cp.language:
        meta.language = cp.language.split("-")[0].lower()

    # Le style « Titre » en tête de document sert de titre du livre.
    if blocks and blocks[0].level == 1 and sum(1 for b in blocks if b.level == 1) == 1 and not meta.title:
        meta.title = blocks[0].text
        blocks = blocks[1:]
    doc = _from_blocks(blocks, meta)
    return doc


def _docx_outline_level(para) -> int | None:
    try:
        ppr = para._p.pPr
        if ppr is None:
            return None
        for child in ppr.iterchildren():
            if child.tag.endswith("}outlineLvl"):
                val = child.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
                return int(val) if val is not None else None
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------------------
def _import_pdf(p: Path) -> ImportedDocument:
    import pymupdf as fitz

    doc = fitz.open(str(p))
    if doc.needs_pass:
        raise ImportErrorUser("Ce PDF est protégé par un mot de passe.")
    meta = BookMetadata()
    md = doc.metadata or {}
    if md.get("title"):
        meta.title = md["title"].strip()
    if md.get("author"):
        meta.author = md["author"].strip()

    pages_lines: list[list[tuple]] = []
    sizes: list[float] = []
    for page in doc:
        height = page.rect.height or 1
        lines: list[tuple] = []
        data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
        for block in data.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in line["spans"]).rstrip()
                size = max(s.get("size", 0) for s in spans)
                bold = all((s.get("flags", 0) & 16) or "Bold" in s.get("font", "") for s in spans)
                y0 = line["bbox"][1]
                rel_y = y0 / height
                lines.append((text, size, bold, rel_y, block["bbox"]))
                sizes.extend([size] * max(1, len(text) // 20))
        pages_lines.append(lines)

    if not sizes:
        raise ImportErrorUser(
            "Ce PDF ne contient pas de texte sélectionnable (probablement un scan). "
            "Utilisez un logiciel d'OCR pour le convertir avant l'import."
        )
    body_size = statistics.median(sizes)

    # En-têtes et pieds de page répétés à éliminer (petits caractères en haut ou en bas de page ;
    # les titres de chapitres, plus gros, sont conservés même s'ils se répètent).
    edge_counter: Counter[str] = Counter()
    for lines in pages_lines:
        for text, size, _bold, rel_y, _ in lines:
            if (rel_y < 0.08 or rel_y > 0.92) and size <= body_size * 1.15:
                edge_counter[_normalize_edge(text)] += 1
    n_pages = max(1, len(pages_lines))
    repeated = {t for t, c in edge_counter.items() if t and c >= max(3, n_pages * 0.3)}

    toc_titles = []
    try:
        toc = doc.get_toc(simple=True)
        toc_titles = [(lvl, re.sub(r"\s+", " ", title).strip()) for lvl, title, _ in toc if title.strip()]
    except Exception:
        toc_titles = []

    blocks: list[_Block] = []
    para: list[str] = []
    last_bbox_bottom = None

    def flush():
        nonlocal para
        if para:
            blocks.append(_Block(_join_pdf_lines(para)))
            para = []

    for lines in pages_lines:
        for text, size, bold, rel_y, bbox in lines:
            stripped = text.strip()
            if (rel_y < 0.08 or rel_y > 0.92) and size <= body_size * 1.15 and (
                _normalize_edge(stripped) in repeated or re.fullmatch(r"[\-–— ]*\d{1,4}[\-–— ]*", stripped)
            ):
                continue
            if re.fullmatch(r"\d{1,4}", stripped) and (rel_y < 0.1 or rel_y > 0.9):
                continue  # numéro de page
            is_heading = (
                len(stripped) < 100
                and (size >= body_size * 1.25 or (bold and size >= body_size * 1.05 and len(stripped) < 70))
                and not stripped.endswith((",", ";"))
            )
            if is_heading:
                flush()
                level = 1 if size >= body_size * 1.6 else 2
                if blocks and blocks[-1].level == level and len(blocks[-1].text) < 60:
                    blocks[-1].text += " " + stripped  # titre sur deux lignes
                else:
                    blocks.append(_Block(stripped, level=level))
                last_bbox_bottom = None
                continue
            # Nouveau paragraphe : bloc différent, ligne courte précédente ou alinéa
            if para and last_bbox_bottom is not None and bbox != last_bbox_bottom:
                prev = para[-1]
                if prev.rstrip().endswith((".", "!", "?", "»", "…", ":", '"')):
                    flush()
            para.append(text)
            last_bbox_bottom = bbox
        # Fin de page : on ne force pas la fin du paragraphe (phrases à cheval)
    flush()

    # Si les titres détectés sont peu fiables mais qu'une table des matières existe, on l'utilise.
    if toc_titles and sum(1 for b in blocks if b.level) < 2:
        blocks = _apply_toc(blocks, toc_titles)

    result = _from_blocks(blocks, meta)
    # Couverture : image de la première page si elle est essentiellement graphique.
    try:
        first = doc[0]
        if len(first.get_text().strip()) < 40:
            pix = first.get_pixmap(dpi=150)
            result.cover_bytes = pix.tobytes("png")
            result.cover_ext = ".png"
    except Exception:
        pass
    return result


def _normalize_edge(t: str) -> str:
    return re.sub(r"\d+", "#", t.strip().lower())


def _join_pdf_lines(lines: list[str]) -> str:
    out = ""
    for line in lines:
        line = line.strip()
        if not out:
            out = line
        elif re.search(r"\w-$", out) and line[:1].islower():
            out = out[:-1] + line  # césure
        elif out.endswith("­"):
            out = out[:-1] + line
        else:
            out += " " + line
    return re.sub(r"\s+", " ", out).strip()


def _apply_toc(blocks: list[_Block], toc: list[tuple[int, str]]) -> list[_Block]:
    top = min(lvl for lvl, _ in toc)
    titles = [t for lvl, t in toc if lvl == top]
    norm = lambda s: re.sub(r"\W+", "", s.lower())  # noqa: E731
    wanted = {norm(t): t for t in titles}
    out: list[_Block] = []
    for b in blocks:
        n = norm(b.text)
        if n in wanted:
            out.append(_Block(wanted[n], level=1))
            continue
        hit = next((k for k in wanted if k and n.startswith(k) and len(k) > 3), None)
        if hit:
            out.append(_Block(wanted[hit], level=1))
            rest = b.text[len(wanted[hit]):].strip()
            if rest:
                out.append(_Block(rest))
        else:
            out.append(b)
    return out


# ---------------------------------------------------------------------------------------
# EPUB
# ---------------------------------------------------------------------------------------
def _import_epub(p: Path) -> ImportedDocument:
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(p), options={"ignore_ncx": True})
    meta = BookMetadata()
    for key, attr in (("title", "title"), ("creator", "author"), ("description", "description"),
                      ("publisher", "publisher"), ("language", "language"), ("date", "year")):
        vals = book.get_metadata("DC", key)
        if vals:
            val = str(vals[0][0]).strip()
            if attr == "language":
                val = val.split("-")[0].lower()
            if attr == "year":
                val = val[:4]
            setattr(meta, attr, val)

    chapters: list[Chapter] = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        blocks = _html_blocks(item.get_content().decode("utf-8", errors="replace"))
        if not blocks:
            continue
        title = next((b.text for b in blocks if b.level), "")
        body = []
        for b in blocks:
            if b.level and b.text == title:
                continue
            body.append(("## " + b.text) if b.level else b.text)
        text = "\n\n".join(body)
        if len(text.split()) < 8 and not title:
            continue
        chapters.append(Chapter(title=_clean_title(title) or f"Chapitre {len(chapters) + 1}", text=text))

    doc = ImportedDocument(chapters=chapters, metadata=meta)
    try:
        cover = None
        for item in book.get_items_of_type(ebooklib.ITEM_COVER):
            cover = item
            break
        if cover is None:
            for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                if "cover" in item.get_name().lower():
                    cover = item
                    break
        if cover is not None:
            doc.cover_bytes = cover.get_content()
            doc.cover_ext = Path(cover.get_name()).suffix or ".jpg"
    except Exception:
        pass
    return doc
