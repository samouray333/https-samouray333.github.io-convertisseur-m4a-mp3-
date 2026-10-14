"""Couvertures dessinées par l'application : un décor simple choisi d'après l'histoire, et le titre en grand.

Le dessin est fait avec Qt (aucune image extérieure) : la couverture est libre de droits et sert pour les MP3,
le livret et le coin lecture."""

from __future__ import annotations

import math
import random
import unicodedata
from pathlib import Path

SCENES = {
    "mer": ("mer", "océan", "ocean", "plage", "bateau", "pirate", "poisson", "sirène", "sirene", "baleine", "île",
            "ile", "dauphin", "crabe", "vague"),
    "espace": ("espace", "étoile filante", "fusée", "fusee", "planète", "planete", "astronaute", "galaxie", "lune",
               "comète", "comete", "extraterrestre", "martien"),
    "chateau": ("dragon", "château", "chateau", "princesse", "prince", "chevalier", "roi", "reine", "sorcier",
                "sorcière", "sorciere", "magie", "magique", "fée", "fee", "licorne", "royaume"),
    "neige": ("neige", "hiver", "noël", "noel", "pingouin", "manchot", "banquise", "flocon", "ours polaire", "luge"),
    "ferme": ("ferme", "vache", "mouton", "poule", "cochon", "tracteur", "âne", "ane", "cheval", "poussin", "canard"),
    "foret": ("forêt", "foret", "bois", "arbre", "loup", "renard", "ours", "hibou", "chouette", "écureuil",
              "ecureuil", "lutin", "champignon", "cabane", "hérisson", "herisson"),
}
NIGHT_WORDS = ("nuit", "dormir", "dodo", "noir", "lune", "étoile", "etoile", "rêve", "reve", "sommeil", "soir",
               "endormir", "berceuse")
FONT_FAMILIES = ["Comic Sans MS", "Segoe Print", "Arial Rounded MT Bold", "Segoe UI", "Verdana", "DejaVu Sans"]


def _plain(text: str) -> str:
    return unicodedata.normalize("NFC", (text or "").lower())


def pick_scene(*texts: str) -> str:
    """Décor de la couverture d'après le titre, l'idée ou le texte de l'histoire (« maison » par défaut)."""
    words = _plain(" ".join(texts))
    best, score = "maison", 0
    for scene, keys in SCENES.items():
        n = sum(words.count(k) for k in keys)
        if n > score:
            best, score = scene, n
    return best


def is_night(bedtime: bool, *texts: str) -> bool:
    words = _plain(" ".join(texts))
    return bedtime or sum(words.count(w) for w in NIGHT_WORDS) >= 2


def _ensure_gui():
    """Qt doit être démarré pour dessiner du texte ; une QApplication (et non une simple QGuiApplication) pour que
    l'interface puisse ensuite s'ouvrir dans le même programme (autotest, tests)."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def generate_cover(title: str, target: str | Path, context: str = "", bedtime: bool = False, subtitle: str = "",
                   size: int = 1400, seed: int | None = None, scene: str | None = None) -> Path:
    """Dessine la couverture et l'enregistre (PNG ou JPEG selon l'extension)."""
    _ensure_gui()
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter,
                               QPainterPath, QPen, QRadialGradient)

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    scene = scene or pick_scene(title, context)
    night = is_night(bedtime, title, context) or scene == "espace"
    rng = random.Random(seed if seed is not None else sum(map(ord, title + scene)))
    s = float(size)
    img = QImage(size, size, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    # -- ciel
    sky = QLinearGradient(0, 0, 0, s)
    if night:
        sky.setColorAt(0, QColor("#0B1033"))
        sky.setColorAt(0.65, QColor("#24306B"))
        sky.setColorAt(1, QColor("#3B4A8F"))
    elif scene == "neige":
        sky.setColorAt(0, QColor("#A9D6F5"))
        sky.setColorAt(1, QColor("#E8F4FF"))
    else:
        sky.setColorAt(0, QColor("#6EC6FF"))
        sky.setColorAt(0.7, QColor("#BDE7FF"))
        sky.setColorAt(1, QColor("#FFF3D6"))
    p.fillRect(QRectF(0, 0, s, s), sky)

    def ellipse(x, y, w, h, color):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(x * s, y * s, w * s, h * s))

    def star(cx, cy, r, color="#FFD166"):
        path = QPainterPath()
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.45
            pt = QPointF(cx * s + math.cos(ang) * rad * s, cy * s + math.sin(ang) * rad * s)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.fillPath(path, QColor(color))

    # -- astres
    if night:
        for _ in range(70):
            x, y = rng.random(), rng.random() * 0.62
            r = rng.uniform(0.002, 0.005)
            ellipse(x, y, r, r, QColor(255, 255, 255, rng.randint(120, 255)))
        for _ in range(6):
            star(rng.uniform(0.08, 0.92), rng.uniform(0.32, 0.6), rng.uniform(0.012, 0.022))
        glow = QRadialGradient(QPointF(0.78 * s, 0.4 * s), 0.16 * s)
        glow.setColorAt(0, QColor(255, 236, 170, 120))
        glow.setColorAt(1, QColor(255, 236, 170, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(0.78 * s, 0.4 * s), 0.16 * s, 0.16 * s)
        moon = QPainterPath()
        moon.addEllipse(QPointF(0.78 * s, 0.4 * s), 0.08 * s, 0.08 * s)
        bite = QPainterPath()
        bite.addEllipse(QPointF(0.81 * s, 0.375 * s), 0.07 * s, 0.07 * s)
        p.fillPath(moon.subtracted(bite), QColor("#FFE9A8"))
    else:
        ellipse(0.7, 0.3, 0.16, 0.16, "#FFD166")
        for cx, cy in ((0.18, 0.36), (0.5, 0.42)):
            for dx, dy, w in ((0, 0, 0.14), (0.07, -0.03, 0.12), (0.13, 0.01, 0.11)):
                ellipse(cx + dx, cy + dy, w, w * 0.6, QColor(255, 255, 255, 230))

    # -- décor
    ground_y = 0.74

    def hill(cx, cy, w, h, color):
        ellipse(cx - w / 2, cy, w, h, color)

    def tree(x, base, h, color="#2E7D32", trunk="#6D4C41"):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(trunk))
        p.drawRect(QRectF((x - 0.008) * s, (base - h * 0.25) * s, 0.016 * s, h * 0.25 * s))
        for k in range(3):
            tri = QPainterPath()
            top = base - h + k * h * 0.22
            wid = h * (0.32 + k * 0.1)
            tri.moveTo(x * s, top * s)
            tri.lineTo((x - wid / 2) * s, (top + h * 0.4) * s)
            tri.lineTo((x + wid / 2) * s, (top + h * 0.4) * s)
            tri.closeSubpath()
            p.fillPath(tri, QColor(color))

    def house(x, base, w, wall="#FFB74D", roof="#D84315"):
        h = w * 0.7
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(wall))
        p.drawRect(QRectF(x * s, (base - h) * s, w * s, h * s))
        r = QPainterPath()
        r.moveTo((x - w * 0.1) * s, (base - h) * s)
        r.lineTo((x + w / 2) * s, (base - h - w * 0.45) * s)
        r.lineTo((x + w * 1.1) * s, (base - h) * s)
        r.closeSubpath()
        p.fillPath(r, QColor(roof))
        light = "#FFE082" if night else "#81D4FA"
        p.setBrush(QColor(light))
        p.drawRect(QRectF((x + w * 0.15) * s, (base - h * 0.75) * s, w * 0.25 * s, w * 0.2 * s))
        p.setBrush(QColor("#5D4037"))
        p.drawRoundedRect(QRectF((x + w * 0.6) * s, (base - h * 0.55) * s, w * 0.22 * s, h * 0.55 * s), 6, 6)

    dark = night
    if scene == "mer":
        for k, col in enumerate(("#1565C0", "#1E88E5", "#42A5F5")):
            path = QPainterPath()
            y0 = 0.68 + k * 0.08
            path.moveTo(0, s)
            path.lineTo(0, y0 * s)
            for i in range(9):
                path.quadTo(QPointF((i + 0.5) / 8 * s, (y0 - 0.03) * s), QPointF((i + 1) / 8 * s, y0 * s))
            path.lineTo(s, s)
            path.closeSubpath()
            p.fillPath(path, QColor(col).darker(160) if dark else QColor(col))
        hull = QPainterPath()
        hull.moveTo(0.3 * s, 0.66 * s)
        hull.lineTo(0.6 * s, 0.66 * s)
        hull.lineTo(0.55 * s, 0.72 * s)
        hull.lineTo(0.35 * s, 0.72 * s)
        hull.closeSubpath()
        p.fillPath(hull, QColor("#8D6E63"))
        sail = QPainterPath()
        sail.moveTo(0.45 * s, 0.45 * s)
        sail.lineTo(0.45 * s, 0.64 * s)
        sail.lineTo(0.57 * s, 0.64 * s)
        sail.closeSubpath()
        p.fillPath(sail, QColor("#FFFFFF"))
    elif scene == "espace":
        ellipse(0.12, 0.5, 0.2, 0.2, "#FF8A65")
        p.setPen(QPen(QColor("#FFCC80"), 0.012 * s))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(0.06 * s, 0.57 * s, 0.32 * s, 0.06 * s))
        hill(0.5, 0.78, 1.6, 0.6, "#5C6BC0")
        for cx, cy, r in ((0.3, 0.86, 0.05), (0.62, 0.82, 0.035), (0.8, 0.9, 0.06)):
            ellipse(cx, cy, r, r * 0.5, "#3949AB")
        body = QPainterPath()
        body.addRoundedRect(QRectF(0.47 * s, 0.5 * s, 0.08 * s, 0.2 * s), 0.04 * s, 0.04 * s)
        p.fillPath(body, QColor("#ECEFF1"))
        ellipse(0.49, 0.55, 0.04, 0.04, "#4FC3F7")
        flame = QPainterPath()
        flame.moveTo(0.48 * s, 0.7 * s)
        flame.lineTo(0.51 * s, 0.78 * s)
        flame.lineTo(0.54 * s, 0.7 * s)
        flame.closeSubpath()
        p.fillPath(flame, QColor("#FFB300"))
    elif scene == "neige":
        hill(0.25, 0.68, 0.9, 0.6, "#FFFFFF")
        hill(0.8, 0.72, 0.9, 0.5, "#F1F8FF")
        tree(0.18, 0.78, 0.2, "#1B5E20")
        tree(0.85, 0.8, 0.16, "#1B5E20")
        house(0.42, 0.8, 0.16, "#EF9A9A", "#B71C1C")
        for _ in range(60):
            r = rng.uniform(0.004, 0.009)
            ellipse(rng.random(), rng.random() * 0.75, r, r, QColor(255, 255, 255, 220))
    else:
        g1, g2 = ("#2E7D32", "#43A047") if not dark else ("#1B4D2A", "#235C33")
        hill(0.2, 0.66, 1.0, 0.6, g2)
        hill(0.85, 0.7, 0.9, 0.5, g1)
        if scene == "foret":
            for x in (0.06, 0.16, 0.28, 0.72, 0.84, 0.95):
                tree(x, ground_y + rng.uniform(0.02, 0.06), rng.uniform(0.22, 0.32),
                     "#1B5E20" if not dark else "#12381F")
            ellipse(0.45, 0.8, 0.05, 0.03, "#E53935")
            p.setBrush(QColor("#FFF8E1"))
            p.drawRect(QRectF(0.468 * s, 0.82 * s, 0.014 * s, 0.03 * s))
        elif scene == "chateau":
            col = QColor("#B0BEC5") if not dark else QColor("#7986CB")
            for x, h in ((0.36, 0.26), (0.5, 0.34), (0.64, 0.26)):
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRect(QRectF((x - 0.05) * s, (0.72 - h) * s, 0.1 * s, h * s))
                roof = QPainterPath()
                roof.moveTo((x - 0.065) * s, (0.72 - h) * s)
                roof.lineTo(x * s, (0.72 - h - 0.1) * s)
                roof.lineTo((x + 0.065) * s, (0.72 - h) * s)
                roof.closeSubpath()
                p.fillPath(roof, QColor("#7E57C2"))
                p.setBrush(QColor("#FFE082") if dark else QColor("#5D4037"))
                p.drawRect(QRectF((x - 0.015) * s, (0.72 - h * 0.7) * s, 0.03 * s, 0.04 * s))
            p.setBrush(QColor("#5D4037"))
            p.drawRoundedRect(QRectF(0.47 * s, 0.63 * s, 0.06 * s, 0.09 * s), 10, 10)
        elif scene == "ferme":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#C62828"))
            p.drawRect(QRectF(0.55 * s, 0.56 * s, 0.24 * s, 0.18 * s))
            roof = QPainterPath()
            roof.moveTo(0.53 * s, 0.56 * s)
            roof.lineTo(0.67 * s, 0.44 * s)
            roof.lineTo(0.81 * s, 0.56 * s)
            roof.closeSubpath()
            p.fillPath(roof, QColor("#8E2424"))
            p.setBrush(QColor("#FFFFFF"))
            p.drawRect(QRectF(0.63 * s, 0.63 * s, 0.08 * s, 0.11 * s))
            for x in (0.1, 0.16, 0.22, 0.28, 0.34, 0.4):
                p.setBrush(QColor("#A1887F"))
                p.drawRect(QRectF(x * s, 0.74 * s, 0.012 * s, 0.06 * s))
            p.drawRect(QRectF(0.1 * s, 0.755 * s, 0.31 * s, 0.01 * s))
        else:  # maison
            house(0.4, 0.78, 0.2)
            tree(0.18, 0.8, 0.26)
            tree(0.8, 0.82, 0.22)
    # -- bandeau du titre
    title = " ".join((title or "Mon histoire").split())
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setBold(True)
    box = QRectF(0.07 * s, 0.05 * s, 0.86 * s, 0.25 * s)
    pt = 0.095 * s
    while pt > 0.035 * s:
        font.setPixelSize(int(pt))
        fm = QFontMetricsF(font)
        r = fm.boundingRect(QRectF(0, 0, box.width() - 0.06 * s, box.height()), Qt.TextWordWrap | Qt.AlignCenter,
                            title)
        if r.height() <= box.height() - 0.04 * s and r.width() <= box.width() - 0.05 * s:
            break
        pt *= 0.92
    banner = QPainterPath()
    banner.addRoundedRect(box, 0.05 * s, 0.05 * s)
    p.fillPath(banner, QColor(255, 255, 255, 215) if not night else QColor(255, 255, 255, 36))
    p.setFont(font)
    inner = box.adjusted(0.03 * s, 0.02 * s, -0.03 * s, -0.02 * s)
    p.setPen(QColor(0, 0, 0, 70))
    p.drawText(inner.translated(0.004 * s, 0.005 * s), Qt.TextWordWrap | Qt.AlignCenter, title)
    p.setPen(QColor("#FFD166") if night else QColor("#1D2A6B"))
    p.drawText(inner, Qt.TextWordWrap | Qt.AlignCenter, title)
    if subtitle:
        sf = QFont(font)
        sf.setPixelSize(int(0.04 * s))
        sf.setBold(False)
        p.setFont(sf)
        p.setPen(QColor(255, 255, 255, 230))
        sub_box = QRectF(0.05 * s, 0.9 * s, 0.9 * s, 0.07 * s)
        shade = QPainterPath()
        shade.addRoundedRect(sub_box, 0.03 * s, 0.03 * s)
        p.fillPath(shade, QColor(0, 0, 0, 80))
        p.drawText(sub_box, Qt.AlignCenter, subtitle)
    p.end()
    fmt = "JPG" if target.suffix.lower() in (".jpg", ".jpeg") else "PNG"
    if not img.save(str(target), fmt, 92):
        raise OSError(f"Impossible d'enregistrer la couverture : {target}")
    return target
