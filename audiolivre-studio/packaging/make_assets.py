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
    from audiolivre.ui import icons, theme

    theme.apply(app, "dark", "#7C5CFF")
    res = ROOT / "audiolivre" / "resources"
    res.mkdir(parents=True, exist_ok=True)
    big = qpixmap_to_pil(icons.app_logo(256))
    big.save(res / "app.png")
    big.save(res / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    out = ROOT / "packaging" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    # Grande image latérale de l'assistant d'installation (164 × 314, mise à l'échelle 2x)
    w, h = 328, 628
    side = Image.new("RGB", (w, h), (13, 14, 27))
    draw = ImageDraw.Draw(side)
    for y in range(h):
        t = y / h
        r = int(124 * (1 - t) + 255 * t * 0.55 + 13 * t * 0.45)
        g = int(92 * (1 - t) + 79 * t * 0.55 + 14 * t * 0.45)
        b = int(255 * (1 - t) + 163 * t * 0.55 + 27 * t * 0.45)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    for i in range(22):
        import math

        bh = 30 + abs(math.sin(i * 0.55)) * 170
        x = 24 + i * 13
        draw.rounded_rectangle([x, h * 0.72 - bh / 2, x + 7, h * 0.72 + bh / 2], radius=3, fill=(214, 200, 255),
                               outline=None)
    logo = big.resize((150, 150), Image.LANCZOS)
    side.paste(logo, ((w - 150) // 2, 70), logo)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 30)
        small = ImageFont.truetype("DejaVuSans.ttf", 18)
    except OSError:
        font = small = ImageFont.load_default()
    draw.text((w / 2, 260), "AudioLivre", font=font, fill="white", anchor="mm")
    draw.text((w / 2, 296), "Studio", font=small, fill=(235, 230, 255), anchor="mm")
    side.save(out / "wizard.bmp")
    side.resize((164, 314), Image.LANCZOS).save(out / "wizard-small-scale.bmp")
    small_img = Image.new("RGB", (110, 116), (255, 255, 255))
    small_img.paste(big.resize((100, 100), Image.LANCZOS), (5, 8), big.resize((100, 100), Image.LANCZOS))
    small_img.save(out / "wizard-icon.bmp")
    print("Ressources générées dans", res, "et", out)


if __name__ == "__main__":
    main()
