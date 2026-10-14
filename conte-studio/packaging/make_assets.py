"""Génère l'icône (.ico) et les images de l'installateur à partir du logo dessiné par l'application.

Usage : python packaging/make_assets.py
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def qpixmap_to_pil(pm) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main() -> None:
    app = QApplication.instance() or QApplication([])
    from contestudio import APP_NAME, BRAND_ACCENT, BRAND_ACCENT2
    from contestudio.ui import icons, theme

    theme.apply(app, "dark", BRAND_ACCENT)
    res = ROOT / "contestudio" / "resources"
    res.mkdir(parents=True, exist_ok=True)
    big = qpixmap_to_pil(icons.app_logo(256))
    big.save(res / "app.png")
    big.save(res / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    out = ROOT / "packaging" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    # Grande image latérale de l'assistant d'installation (164 × 314, mise à l'échelle 2x)
    w, h = 328, 628
    a1 = tuple(int(BRAND_ACCENT[i:i + 2], 16) for i in (1, 3, 5))
    a2 = tuple(int(BRAND_ACCENT2[i:i + 2], 16) for i in (1, 3, 5))
    bg = tuple(int(theme.CURRENT.bg[i:i + 2], 16) for i in (1, 3, 5))
    side = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(side)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(c1 * (1 - t) * 0.8 + c0 * (0.2 + 0.8 * t))
                                                for c1, c0 in zip(a1, bg)))  # bleu du soir vers bleu nuit
    import math
    import random

    rng = random.Random(4)  # ciel étoilé
    for _ in range(70):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(1, 2.6)
        if 60 < y < 320 and 50 < x < w - 50:  # pas d'étoile sur le logo ni sur le nom
            continue
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    for cx, cy, r in ((70, 430, 16), (250, 470, 11), (150, 540, 13), (270, 380, 8)):
        pts = [(cx + math.cos(-math.pi / 2 + k * math.pi / 5) * (r if k % 2 == 0 else r * 0.45),
                cy + math.sin(-math.pi / 2 + k * math.pi / 5) * (r if k % 2 == 0 else r * 0.45)) for k in range(10)]
        draw.polygon(pts, fill=a2)
    logo = big.resize((150, 150), Image.LANCZOS)
    side.paste(logo, ((w - 150) // 2, 70), logo)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 30)
        small = ImageFont.truetype("DejaVuSans.ttf", 18)
    except OSError:
        font = small = ImageFont.load_default()
    brand, _, rest = APP_NAME.rpartition(" ")
    draw.text((w / 2, 260), brand or APP_NAME, font=font, fill="white", anchor="mm")
    draw.text((w / 2, 296), rest if brand else "", font=small, fill=(255, 255, 255), anchor="mm")
    side.save(out / "wizard.bmp")
    side.resize((164, 314), Image.LANCZOS).save(out / "wizard-small-scale.bmp")
    small_img = Image.new("RGB", (110, 116), (255, 255, 255))
    small_img.paste(big.resize((100, 100), Image.LANCZOS), (5, 8), big.resize((100, 100), Image.LANCZOS))
    small_img.save(out / "wizard-icon.bmp")
    print("Ressources générées dans", res, "et", out)


if __name__ == "__main__":
    main()
