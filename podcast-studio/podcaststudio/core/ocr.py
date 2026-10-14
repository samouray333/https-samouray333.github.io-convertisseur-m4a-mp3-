"""Reconnaissance de texte (OCR) des pages scannées avec le moteur intégré à Windows 10/11.

Aucun téléchargement : Windows fournit l'OCR pour les langues installées (le français sur un
Windows français). Les pages PDF sont rendues en image par PyMuPDF.
"""

from __future__ import annotations

import asyncio
import logging
import re
import statistics
import sys
from typing import Callable

log = logging.getLogger(__name__)


def ocr_available() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401

        return True
    except Exception:
        return False


def _engine(language: str):
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    engine = None
    for tag in (language, {"fr": "fr-FR", "en": "en-US"}.get(language, language)):
        try:
            lang = Language(tag)
            if OcrEngine.is_language_supported(lang):
                engine = OcrEngine.try_create_from_language(lang)
                if engine is not None:
                    break
        except Exception:
            continue
    if engine is None:
        engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("Aucune langue de reconnaissance de texte n'est installée dans Windows.")
    return engine


async def _recognize(engine, png: bytes):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    return await engine.recognize_async(bitmap)


def lines_to_text(lines: list[tuple[float, float, str]]) -> str:
    """Regroupe les lignes reconnues (haut, hauteur, texte) en paragraphes."""
    if not lines:
        return ""
    lines = sorted(lines, key=lambda x: x[0])
    heights = [h for _y, h, _t in lines if h > 0] or [10.0]
    med = statistics.median(heights)
    paras: list[str] = []
    cur = ""
    prev_bottom = None
    for y, h, text in lines:
        text = text.strip()
        if not text:
            continue
        gap = (y - prev_bottom) if prev_bottom is not None else 0
        if cur and gap > med * 0.9:
            paras.append(cur)
            cur = ""
        if not cur:
            cur = text
        elif re.search(r"\w-$", cur) and text[:1].islower():
            cur = cur[:-1] + text
        else:
            cur += " " + text
        prev_bottom = y + h
    if cur:
        paras.append(cur)
    return "\n\n".join(paras)


def ocr_image_bytes(png: bytes, language: str = "fr", engine=None) -> str:
    engine = engine or _engine(language)
    result = asyncio.run(_recognize(engine, png))
    lines = []
    for line in result.lines:
        words = list(line.words)
        if words:
            ys = [w.bounding_rect.y for w in words]
            hs = [w.bounding_rect.height for w in words]
            lines.append((min(ys), max(hs), line.text))
        else:
            lines.append((0.0, 0.0, line.text))
    return lines_to_text(lines)


def ocr_pdf(path, language: str = "fr", progress: Callable[[int, int], None] | None = None,
            dpi: int = 250) -> list[str]:
    """Texte de chaque page d'un PDF scanné."""
    import pymupdf

    doc = pymupdf.open(str(path))
    engine = _engine(language)
    from winrt.windows.media.ocr import OcrEngine

    max_dim = int(OcrEngine.max_image_dimension or 10000)
    pages = []
    for i, page in enumerate(doc):
        zoom = dpi / 72.0
        longest = max(page.rect.width, page.rect.height) * zoom
        if longest > max_dim:
            zoom *= max_dim / longest
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
        pages.append(ocr_image_bytes(pix.tobytes("png"), language, engine))
        if progress:
            progress(i + 1, len(doc))
    return pages
