"""Page d'accueil : démarrage rapide, projets récents, état des moteurs."""

from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from ...config import settings
from ...core import engines
from ...core.importers import SUPPORTED_EXTENSIONS
from .. import icons, theme
from ..widgets import Badge, Card, DropZone, button, card_title, label
from .base import Page


class HeroBanner(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(290)

    def paintEvent(self, e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(r, 22, 22)
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        c1, c2 = QColor(p.accent), QColor(p.accent2)
        grad.setColorAt(0, c1.darker(150) if p.dark else c1.lighter(105))
        grad.setColorAt(0.55, c1 if p.dark else c1.lighter(115))
        grad.setColorAt(1, c2)
        painter.fillPath(path, grad)
        painter.setClipPath(path)
        # onde décorative
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 34))
        import math

        n = 46
        w = self.width() * 0.45
        x0 = self.width() - w - 30
        for i in range(n):
            h = (math.sin(i * 0.45) * 0.5 + 0.5) * (0.35 + 0.65 * abs(math.sin(i * 0.17 + 1)))
            bh = 18 + h * self.height() * 0.62
            x = x0 + i * (w / n)
            painter.drawRoundedRect(QRectF(x, (self.height() - bh) / 2, w / n * 0.55, bh), 3, 3)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawEllipse(QRectF(self.width() - 220, -120, 360, 360))
        painter.end()


class RecentCard(QFrame):
    def __init__(self, path: str, on_open):
        super().__init__()
        self.setObjectName("CardHover")
        self.setCursor(Qt.PointingHandCursor)
        self._path = path
        self._on_open = on_open
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        top = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("book", theme.CURRENT.accent, 22))
        top.addWidget(ic)
        top.addStretch(1)
        p = Path(path)
        try:
            mtime = time.strftime("%d/%m/%Y", time.localtime(p.stat().st_mtime))
        except OSError:
            mtime = ""
        top.addWidget(label(mtime, "Faint"))
        lay.addLayout(top)
        title = p.stem
        info = ""
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            title = data.get("metadata", {}).get("title") or title
            chapters = [c for c in data.get("chapters", []) if c.get("include", True)]
            words = sum(len(c.get("text", "").split()) for c in chapters)
            author = data.get("metadata", {}).get("author", "")
            info = f"{author + ' · ' if author else ''}{len(chapters)} chapitres · {words:,} mots".replace(",", " ")
        except Exception:
            pass
        t = label(title, wrap=True)
        t.setStyleSheet("font-weight: 700; font-size: 11pt;")
        lay.addWidget(t)
        lay.addWidget(label(info, "Hint", wrap=True))
        lay.addStretch(1)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on_open(self._path)


class HomePage(Page):
    name = "home"

    def __init__(self, ctx, window):
        super().__init__(ctx, "", "", scroll=True)
        self.window_ = window
        self.header.hide()

        hero = HeroBanner()
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(38, 34, 38, 30)
        hl.setSpacing(10)
        kicker = label("STUDIO DE LIVRES AUDIO · 100 % GRATUIT")
        kicker.setStyleSheet("color: rgba(255,255,255,0.8); font-weight: 700; letter-spacing: 2px; font-size: 8.5pt;")
        title = label("Donnez une voix à vos livres.")
        title.setStyleSheet("color: white; font-size: 27pt; font-weight: 800;")
        sub = label("Importez un document Word ou PDF, choisissez ou clonez une voix, et obtenez un livre audio "
                    "masterisé aux normes professionnelles (ACX / Audible), avec chapitres et couverture.", wrap=True)
        sub.setStyleSheet("color: rgba(255,255,255,0.88); font-size: 11pt;")
        sub.setFixedWidth(640)
        sub.setMinimumHeight(48)
        hl.addWidget(kicker)
        hl.addWidget(title)
        hl.addWidget(sub)
        hl.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        b1 = button("Importer un document", "file-plus")
        b1.setStyleSheet("QPushButton { background: white; color: #17182E; border: none; padding: 10px 20px; }"
                         "QPushButton:hover { background: #F1EEFF; }")
        b1.setIcon(icons.icon("file-plus", "#17182E", 18))
        b1.clicked.connect(window.import_document_dialog)
        b2 = button("Ouvrir un projet", "folder", icon_color="#FFFFFF")
        b2.setStyleSheet("QPushButton { background: rgba(255,255,255,0.16); color: white; border: 1px solid "
                         "rgba(255,255,255,0.35); padding: 10px 18px; } QPushButton:hover { background: "
                         "rgba(255,255,255,0.26); }")
        b2.clicked.connect(window.open_project_dialog)
        b3 = button("Cloner une voix", "mic", icon_color="#FFFFFF")
        b3.setStyleSheet(b2.styleSheet())
        b3.clicked.connect(lambda: self._clone())
        for b in (b1, b2, b3):
            row.addWidget(b)
        row.addStretch(1)
        hl.addLayout(row)
        hl.addStretch(1)
        self.body.addWidget(hero)

        grid = QHBoxLayout()
        grid.setSpacing(18)
        exts = ", ".join(sorted({e.lstrip(".").upper() for e in SUPPORTED_EXTENSIONS if e not in (".htm", ".markdown")}))
        drop = DropZone("Glissez votre manuscrit ici", f"ou cliquez pour parcourir — {exts}", "upload", 240)
        drop.files_dropped.connect(lambda files: window.import_document(files[0]))
        drop.clicked.connect(window.import_document_dialog)
        grid.addWidget(drop, 3)

        steps = Card()
        steps.add(card_title("Comment ça marche", "Quatre étapes vers un livre audio professionnel", "sparkles"))
        for i, (t, d) in enumerate([
            ("Importer", "Word, PDF, EPUB… Les chapitres sont détectés automatiquement."),
            ("Choisir les voix", "Voix neuronales gratuites ou votre propre voix clonée."),
            ("Produire", "Synthèse, contrôle qualité automatique et mastering ACX."),
            ("Exporter", "M4B chapitré, MP3 pour Audible, couverture et rapport qualité."),
        ], 1):
            r = QHBoxLayout()
            r.setSpacing(12)
            num = QLabel(str(i))
            num.setFixedSize(28, 28)
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet(f"background: {theme.rgba(theme.CURRENT.accent, 0.18)}; color: {theme.CURRENT.accent};"
                              "border-radius: 14px; font-weight: 800;")
            r.addWidget(num, 0, Qt.AlignTop)
            c = QVBoxLayout()
            c.setSpacing(0)
            tl = label(t)
            tl.setStyleSheet("font-weight: 700;")
            c.addWidget(tl)
            c.addWidget(label(d, "Hint", wrap=True))
            r.addLayout(c, 1)
            steps.add(r)
        grid.addWidget(steps, 2)
        self.body.addLayout(grid)

        self.recent_title = label("Projets récents", "SectionTitle")
        self.body.addWidget(self.recent_title)
        self.recent_grid = QGridLayout()
        self.recent_grid.setSpacing(14)
        self.body.addLayout(self.recent_grid)

        self.body.addWidget(label("Moteurs de voix", "SectionTitle"))
        self.engines_row = QHBoxLayout()
        self.engines_row.setSpacing(12)
        self.body.addLayout(self.engines_row)
        self.body.addStretch(1)
        self.ctx.engines_changed.connect(self._fill_engines)

    def _clone(self):
        self.ctx.navigate("voices")
        page = self.window_.pages.get("voices")
        if page is not None:
            page.open_clone_wizard()

    def on_show(self) -> None:
        self._fill_recent()
        self._fill_engines()

    def _fill_recent(self) -> None:
        while self.recent_grid.count():
            it = self.recent_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        recents = settings().recent_projects()[:6]
        self.recent_title.setVisible(bool(recents))
        for i, r in enumerate(recents):
            self.recent_grid.addWidget(RecentCard(r, self.window_.open_project), i // 3, i % 3)

    def _fill_engines(self) -> None:
        while self.engines_row.count():
            it = self.engines_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for eng in engines.all_engines():
            status, msg = eng.status()
            chip = QFrame()
            chip.setObjectName("CardFlat")
            chip.setCursor(Qt.PointingHandCursor)
            lay = QVBoxLayout(chip)
            lay.setContentsMargins(14, 12, 14, 12)
            lay.setSpacing(6)
            top = QHBoxLayout()
            dot = QLabel()
            dot.setFixedSize(10, 10)
            color = {engines.READY: theme.CURRENT.success, engines.NOT_INSTALLED: theme.CURRENT.warning}.get(
                status, theme.CURRENT.faint)
            dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
            top.addWidget(dot)
            n = label(eng.info.name.split(" — ")[0])
            n.setStyleSheet("font-weight: 700;")
            top.addWidget(n, 1)
            lay.addLayout(top)
            lay.addWidget(label(eng.info.tagline, "Hint", wrap=True))
            badge = Badge({engines.READY: "Prêt", engines.NOT_INSTALLED: "À installer"}.get(status, "Indisponible"),
                          {engines.READY: "success", engines.NOT_INSTALLED: "warning"}.get(status, "muted"))
            lay.addWidget(badge, 0, Qt.AlignLeft)
            chip.mouseReleaseEvent = lambda e: self.ctx.navigate("engines")
            self.engines_row.addWidget(chip, 1)
