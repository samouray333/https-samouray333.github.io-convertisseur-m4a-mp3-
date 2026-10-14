"""Page d'accueil : démarrage rapide, collections récentes, état des moteurs."""

from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox, QToolButton, QVBoxLayout

from ...config import settings
from ...core import engines, project_io
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
        grad.setColorAt(0, QColor("#2F5BD3"))
        grad.setColorAt(0.6, QColor("#1D2A6B"))
        grad.setColorAt(1, QColor("#0F1530"))
        painter.fillPath(path, grad)
        painter.setClipPath(path)
        # ciel étoilé, lune et collines
        import random

        from PySide6.QtCore import QPointF

        painter.setPen(Qt.NoPen)
        rng = random.Random(3)
        for _ in range(90):
            x = self.width() * (0.45 + 0.55 * rng.random())
            y = self.height() * 0.75 * rng.random()
            r = rng.uniform(1.0, 2.6)
            painter.setBrush(QColor(255, 255, 255, rng.randint(90, 230)))
            painter.drawEllipse(QPointF(x, y), r, r)
        cx, cy, rad = self.width() - 170, 95, 54
        moon = QPainterPath()
        moon.addEllipse(QPointF(cx, cy), rad, rad)
        bite = QPainterPath()
        bite.addEllipse(QPointF(cx + 26, cy - 16), rad * 0.88, rad * 0.88)
        painter.fillPath(moon.subtracted(bite), QColor(p.accent2))
        painter.setBrush(QColor(255, 255, 255, 26))
        painter.drawEllipse(QRectF(self.width() * 0.55, self.height() * 0.72, self.width() * 0.6, self.height()))
        painter.setBrush(QColor(255, 255, 255, 16))
        painter.drawEllipse(QRectF(self.width() * 0.3, self.height() * 0.82, self.width() * 0.5, self.height()))
        painter.end()


class RecentCard(QFrame):
    def __init__(self, path: str, on_open, on_forget=None, on_delete=None, on_reveal=None):
        super().__init__()
        self.setObjectName("CardHover")
        self.setCursor(Qt.PointingHandCursor)
        self._path = path
        self._on_open = on_open
        self.menu = QMenu(self)
        self.menu.addAction(icons.icon("book", theme.CURRENT.text, 16), "Ouvrir", lambda: on_open(path))
        if on_reveal is not None:
            self.menu.addAction(icons.icon("folder", theme.CURRENT.text, 16), "Afficher dans l'explorateur",
                                lambda: on_reveal(path))
        self.menu.addSeparator()
        if on_forget is not None:
            self.menu.addAction(icons.icon("x", theme.CURRENT.text, 16), "Retirer de la liste",
                                lambda: on_forget(path))
        if on_delete is not None:
            self.menu.addAction(icons.icon("trash", theme.CURRENT.danger, 16), "Supprimer la collection…",
                                lambda: on_delete(path))
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
        self.more = QToolButton()
        self.more.setIcon(icons.icon("more", theme.CURRENT.text, 18))
        self.more.setToolTip("Retirer de la liste, supprimer…")
        self.more.setAutoRaise(True)
        self.more.setPopupMode(QToolButton.InstantPopup)
        self.more.setMenu(self.menu)
        top.addWidget(self.more)
        lay.addLayout(top)
        title = p.stem
        info = ""
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            title = data.get("metadata", {}).get("title") or title
            chapters = [c for c in data.get("chapters", []) if c.get("include", True)]
            words = sum(len(c.get("text", "").split()) for c in chapters)
            author = data.get("metadata", {}).get("author", "")
            info = f"{author + ' · ' if author else ''}{len(chapters)} histoire(s) · {words:,} mots".replace(",", " ")
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

    def contextMenuEvent(self, e):
        self.menu.exec(e.globalPos())


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
        kicker = label("CONTES ET HISTOIRES AUDIO POUR ENFANTS · 100 % GRATUIT")
        kicker.setStyleSheet("color: rgba(255,255,255,0.8); font-weight: 700; letter-spacing: 2px; font-size: 8.5pt;")
        title = label("Il était une fois… votre histoire.")
        title.setStyleSheet("color: white; font-size: 27pt; font-weight: 800;")
        sub = label("Une idée suffit : l'assistant écrit un conte adapté à l'âge de votre enfant, chaque personnage "
                    "a sa voix, les bruitages et la musique du soir sont créés pour vous. Votre enfant peut même devenir "
                    "le héros, raconté par la voix de papa ou de maman.", wrap=True)
        sub.setStyleSheet("color: rgba(255,255,255,0.88); font-size: 11pt;")
        sub.setFixedWidth(640)
        sub.setMinimumHeight(48)
        hl.addWidget(kicker)
        hl.addWidget(title)
        hl.addWidget(sub)
        hl.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        b1 = button("Nouvelle histoire", "sparkles")
        b1.setStyleSheet("QPushButton { background: #FFD166; color: #1D2A6B; border: none; padding: 10px 20px; "
                         "font-weight: 800; } QPushButton:hover { background: #FFE19A; }")
        b1.setIcon(icons.icon("sparkles", "#1D2A6B", 18))
        b1.clicked.connect(window.new_story)
        b0 = button("Histoires d'exemple", "star", icon_color="#FFFFFF")
        b2 = button("Ouvrir une collection", "folder", icon_color="#FFFFFF")
        b2.setStyleSheet("QPushButton { background: rgba(255,255,255,0.16); color: white; border: 1px solid "
                         "rgba(255,255,255,0.35); padding: 10px 18px; } QPushButton:hover { background: "
                         "rgba(255,255,255,0.26); }")
        b2.clicked.connect(window.open_project_dialog)
        b3 = button("Coin lecture", "star-filled", icon_color="#FFFFFF")
        b3.setStyleSheet(b2.styleSheet())
        b3.clicked.connect(window.open_kids_mode)
        b4 = button("Voix de papa ou maman", "mic", icon_color="#FFFFFF")
        b4.setStyleSheet(b2.styleSheet())
        b4.clicked.connect(lambda: self._clone())
        b0.setStyleSheet(b2.styleSheet())
        b0.clicked.connect(window.open_samples)
        for b in (b1, b0, b2, b3, b4):
            row.addWidget(b)
        row.addStretch(1)
        hl.addLayout(row)
        hl.addStretch(1)
        self.body.addWidget(hero)

        grid = QHBoxLayout()
        grid.setSpacing(18)
        exts = ", ".join(sorted({e.lstrip(".").upper() for e in SUPPORTED_EXTENSIONS if e not in (".htm", ".markdown")}))
        drop = DropZone("Glissez un conte ici", f"un texte déjà écrit, à faire lire par les voix — {exts}", "upload",
                        240)
        drop.files_dropped.connect(lambda files: window.import_document(files[0]))
        drop.clicked.connect(window.import_document_dialog)
        grid.addWidget(drop, 3)

        steps = Card()
        steps.add(card_title("Comment ça marche", "Quatre étapes, de l'idée à l'histoire du soir", "sparkles"))
        for i, (t, d) in enumerate([
            ("L'idée", "« Un dragon qui a peur du noir » : choisissez l'âge, la durée, le ton, une morale."),
            ("Les personnages", "Une voix par personnage, plus aiguë ou plus grave ; le narrateur peut être papa."),
            ("Produire", "Voix, bruitages, ambiances et, le soir, berceuse et pluie douce qui s'éteint."),
            ("Écouter", "MP3 avec couverture, livret en gros caractères, coin lecture pour l'enfant."),
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

        self.recent_title = QFrame()
        rt = QHBoxLayout(self.recent_title)
        rt.setContentsMargins(0, 0, 0, 0)
        rt.addWidget(label("Collections récentes", "SectionTitle"))
        rt.addStretch(1)
        clear = button("Vider la liste", "x", "ghost",
                       tooltip="Retire toutes les collections de cette liste (les fichiers ne sont pas supprimés)")
        clear.clicked.connect(self.clear_recent)
        rt.addWidget(clear)
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
            page.open_clone_wizard("Voix de maman")

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
            self.recent_grid.addWidget(RecentCard(r, self.window_.open_project, self.forget_recent,
                                                  self.delete_project, self._reveal), i // 3, i % 3)

    def _reveal(self, path: str) -> None:
        from ..main_window import open_path

        open_path(Path(path).parent)

    def forget_recent(self, path: str) -> None:
        settings().remove_recent(path)
        self._fill_recent()
        self.ctx.toast("Collection retirée de la liste (le fichier est conservé).", "info", 2500)

    def clear_recent(self) -> None:
        settings().clear_recent()
        self._fill_recent()
        self.ctx.toast("Liste des collections récentes vidée.", "info", 2500)

    def delete_project(self, path: str, confirm: bool = True) -> bool:
        p = Path(path)
        current = self.ctx.project.path
        if current is not None and Path(current).resolve() == p.resolve():
            QMessageBox.information(self, "Collection ouverte",
                                    "Cette collection est actuellement ouverte. Ouvrez ou créez une autre collection "
                                    "avant de la supprimer.")
            return False
        if confirm:
            r = QMessageBox.warning(
                self, "Supprimer la collection",
                f"Supprimer définitivement la collection « {p.stem} » ?\n\n"
                f"Seront supprimés : le fichier de la collection et ses fichiers de travail (audio en cache, "
                f"histoires déjà produites).\nVos MP3 exportés, livrets et couvertures sont conservés.\n\n"
                f"Dossier : {p.parent}",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if r != QMessageBox.Yes:
                return False
        try:
            project_io.delete_project_files(p)
        except OSError as exc:
            QMessageBox.warning(self, "Suppression impossible", f"{exc}\n\nLa collection est peut-être ouverte "
                                "dans un autre programme.")
            return False
        settings().remove_recent(path)
        self._fill_recent()
        self.ctx.toast(f"Collection « {p.stem} » supprimée.", "success", 3000)
        return True

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
