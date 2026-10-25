"""Génère l'icône (.ico) et les images de l'installateur NSIS à partir du logo dessiné par l'application.

Usage : python packaging/make_assets.py
"""

from __future__ import annotations

import io
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ACCENT = "#FF6B4A"


def qpixmap_to_pil(pm) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def _fonts(big: int, small: int):
    for bold, regular in (("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"), ("arialbd.ttf", "arial.ttf"),
                          ("segoeuib.ttf", "segoeui.ttf")):
        try:
            return ImageFont.truetype(bold, big), ImageFont.truetype(regular, small)
        except OSError:
            continue
    return ImageFont.load_default(), ImageFont.load_default()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    from doublys.ui import icons, theme

    theme.apply(app, "dark", ACCENT)
    res = ROOT / "doublys" / "resources"
    res.mkdir(parents=True, exist_ok=True)
    big = qpixmap_to_pil(icons.app_logo(256))
    big.save(res / "app.png")
    big.save(res / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    out = ROOT / "packaging" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    # Image latérale des pages d'accueil et de fin (164 × 314)
    w, h = 164, 314
    top, bottom = (255, 107, 74), (120, 40, 90)
    side = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(side)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    for i in range(12):
        bh = 14 + abs(math.sin(i * 0.6)) * 80
        x = 14 + i * 12
        draw.rounded_rectangle([x, h * 0.74 - bh / 2, x + 6, h * 0.74 + bh / 2], radius=3, fill=(255, 225, 215))
    logo = big.resize((92, 92), Image.LANCZOS)
    side.paste(logo, ((w - 92) // 2, 40), logo)
    font, small = _fonts(22, 12)
    draw.text((w / 2, 156), "Doublys", font=font, fill="white", anchor="mm")
    draw.text((w / 2, 180), "Echo Matras", font=small, fill=(255, 235, 228), anchor="mm")
    side.save(out / "wizard.bmp")
    # Bandeau des autres pages (150 × 57)
    header = Image.new("RGB", (150, 57), (255, 255, 255))
    hl = big.resize((48, 48), Image.LANCZOS)
    header.paste(hl, (98, 4), hl)
    hd = ImageDraw.Draw(header)
    f2, _s = _fonts(16, 10)
    hd.text((6, 28), "Doublys", font=f2, fill=(40, 24, 30), anchor="lm")
    header.save(out / "header.bmp")
    print("Ressources générées dans", res, "et", out)


if __name__ == "__main__":
    main()
