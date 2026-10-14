"""Coin lecture : un écran simple pour l'enfant, en plein écran, sans menus. Les couvertures en grand, un grand
bouton lecture ; le parent quitte en maintenant le petit cadenas appuyé."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QScrollArea,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from ..config import settings
from ..core import library
from . import icons
from .pages.library import cover_pixmap

NIGHT = "#0F1530"
STAR = "#FFD166"
SKY = "#3B82F6"
HOLD_MS = 1500
BACK_STYLE = "QToolButton { background: rgba(255,255,255,0.1); border-radius: 30px; padding: 10px; }"


def kid_stories(collections: list[library.Collection]) -> list[library.StoryEntry]:
    """Histoires prêtes à écouter, favoris d'abord (puis dans l'ordre des collections)."""
    ready = [s for c in collections for s in c.stories if s.audio and Path(s.audio).is_file()]
    return sorted(ready, key=lambda s: not s.favorite)


class BigPlayButton(QAbstractButton):
    """Grand bouton rond lecture / pause."""

    def __init__(self, size: int = 150):
        super().__init__()
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.playing = False

    def set_playing(self, on: bool) -> None:
        self.playing = on
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(4, 4, self.width() - 8, self.height() - 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(STAR).lighter(110) if self.isDown() else QColor(STAR))
        p.drawEllipse(r)
        p.setBrush(QColor(NIGHT))
        c, s = r.center(), r.width()
        if self.playing:
            w, h = s * 0.11, s * 0.38
            p.drawRoundedRect(QRectF(c.x() - w * 1.6, c.y() - h / 2, w, h), 6, 6)
            p.drawRoundedRect(QRectF(c.x() + w * 0.6, c.y() - h / 2, w, h), 6, 6)
        else:
            tri = QPainterPath()
            tri.moveTo(c.x() - s * 0.13, c.y() - s * 0.22)
            tri.lineTo(c.x() + s * 0.24, c.y())
            tri.lineTo(c.x() - s * 0.13, c.y() + s * 0.22)
            tri.closeSubpath()
            p.fillPath(tri, QColor(NIGHT))
        p.end()


class HoldButton(QToolButton):
    """Petit cadenas : il faut le maintenir appuyé pour quitter (un enfant ne sort pas par erreur)."""

    def __init__(self, on_hold):
        super().__init__()
        self.setIcon(icons.icon("shield", "#AEB6DE", 22))
        self.setIconSize(QSize(22, 22))
        self.setToolTip("Parent : maintenez appuyé pour quitter le coin lecture")
        self.setStyleSheet("QToolButton { background: rgba(255,255,255,0.08); border-radius: 18px; padding: 8px; }")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(on_hold)
        self.pressed.connect(lambda: self._timer.start(HOLD_MS))
        self.released.connect(self._timer.stop)


class StoryCard(QFrame):
    def __init__(self, entry: library.StoryEntry, on_open, size: int = 250):
        super().__init__()
        self.entry = entry
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("StoryCard { background: rgba(255,255,255,0.07); border-radius: 22px; }"
                           "StoryCard:hover { background: rgba(255,209,102,0.22); }")
        self._on_open = on_open
        self.setFixedWidth(size + 28)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        img = QLabel()
        img.setFixedSize(size, size)
        img.setPixmap(cover_pixmap(entry.cover, size))
        lay.addWidget(img, 0, Qt.AlignHCenter)
        t = QLabel(("★ " if entry.favorite else "") + entry.title)
        t.setWordWrap(True)
        t.setAlignment(Qt.AlignCenter)
        t.setFixedWidth(size)
        t.setStyleSheet("color: white; font-size: 17pt; font-weight: 800; background: transparent;")
        lay.addWidget(t)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on_open(self.entry)


class KidsWindow(QWidget):
    def __init__(self, ctx, parent_window=None):
        super().__init__(None, Qt.Window)
        self.ctx = ctx
        self.player = ctx.player
        self.parent_window = parent_window
        self.setWindowTitle("Coin lecture")
        self.setWindowIcon(icons.app_icon())
        self.stories: list[library.StoryEntry] = []
        self.index = -1
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 20, 30, 24)
        root.setSpacing(12)
        top = QHBoxLayout()
        self.back = QToolButton()
        self.back.setIcon(icons.icon("chevron-left", "white", 40))
        self.back.setIconSize(QSize(40, 40))
        self.back.setStyleSheet(BACK_STYLE)
        self.back.setCursor(Qt.PointingHandCursor)
        self.back.clicked.connect(self.show_grid)
        top.addWidget(self.back)
        self.heading = QLabel()
        self.heading.setStyleSheet(f"color: {STAR}; font-size: 30pt; font-weight: 900; background: transparent;")
        top.addWidget(self.heading, 1, Qt.AlignCenter)
        top.addWidget(HoldButton(self.close))
        root.addLayout(top)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # -- grille des couvertures
        self.grid_holder = QWidget()
        self.grid_holder.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_holder)
        self.grid.setSpacing(26)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setStyleSheet("QScrollArea { background: transparent; } QScrollBar:vertical { width: 18px; }")
        area.viewport().setStyleSheet("background: transparent;")
        area.setWidget(self.grid_holder)
        self.stack.addWidget(area)

        # -- écoute
        play_page = QWidget()
        pl = QVBoxLayout(play_page)
        pl.setSpacing(18)
        self.cover = QLabel()
        self.cover.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.cover, 1)
        self.title = QLabel()
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.title.setStyleSheet("color: white; font-size: 26pt; font-weight: 900; background: transparent;")
        pl.addWidget(self.title)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(14)
        self.progress.setStyleSheet(f"QProgressBar {{ background: rgba(255,255,255,0.15); border: none; "
                                    f"border-radius: 7px; }} QProgressBar::chunk {{ background: {STAR}; "
                                    "border-radius: 7px; }")
        pl.addWidget(self.progress)
        ctrl = QHBoxLayout()
        ctrl.addStretch(1)
        self.prev_btn = self._round_icon("skip-back", self.previous)
        self.play_btn = BigPlayButton(160)
        self.play_btn.clicked.connect(self.toggle)
        self.next_btn = self._round_icon("skip-fwd", self.next)
        for w in (self.prev_btn, self.play_btn, self.next_btn):
            ctrl.addWidget(w)
            ctrl.addSpacing(30)
        ctrl.addStretch(1)
        pl.addLayout(ctrl)
        self.stack.addWidget(play_page)

        self.player.state_changed.connect(self._state)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)
        self.reload()
        self.show_grid()

    def _round_icon(self, name: str, fn) -> QToolButton:
        b = QToolButton()
        b.setIcon(icons.icon(name, "white", 48))
        b.setIconSize(QSize(48, 48))
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet("QToolButton { background: rgba(255,255,255,0.12); border-radius: 44px; padding: 20px; }"
                        "QToolButton:pressed { background: rgba(255,255,255,0.25); }")
        b.clicked.connect(fn)
        return b

    # -- contenu -----------------------------------------------------------------------
    def reload(self) -> None:
        extra = list(settings().recent_projects())
        if self.ctx.project.path is not None:
            extra.insert(0, str(self.ctx.project.path))
        cols = library.load_collections(library.find_projects([settings().projects_dir()], extra), self.ctx.project)
        self.stories = kid_stories(cols)
        child = self.ctx.project.metadata.child_name or next((c.child_name for c in cols if c.child_name), "")
        self._heading_text = f"Les histoires de {child}" if child else "Mes histoires"
        self.heading.setText(self._heading_text)
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if not self.stories:
            msg = QLabel("Pas encore d'histoire à écouter.\nDemande à un grand de produire une histoire !")
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet("color: white; font-size: 22pt; font-weight: 700; background: transparent;")
            self.grid.addWidget(msg, 0, 0)
            return
        cols_n = max(1, min(5, (self.width() - 60) // 300)) if self.width() > 400 else 4
        for i, s in enumerate(self.stories):
            self.grid.addWidget(StoryCard(s, self.open_story), i // cols_n, i % cols_n, Qt.AlignTop)

    def show_grid(self) -> None:
        self.stack.setCurrentIndex(0)
        self.back.setEnabled(False)
        self.back.setStyleSheet("QToolButton { background: transparent; border: none; }")
        self.back.setIcon(QIcon())  # pas de retour depuis la grille
        self.heading.setText(self._heading_text)

    def open_story(self, entry: library.StoryEntry) -> None:
        self.index = self.stories.index(entry)
        self._show_current(play=True)

    def _show_current(self, play: bool) -> None:
        entry = self.stories[self.index]
        self.stack.setCurrentIndex(1)
        self.back.setEnabled(True)
        self.back.setStyleSheet(BACK_STYLE)
        self.back.setIcon(icons.icon("chevron-left", "white", 40))
        self.heading.setText("")
        side = max(240, min(self.height() - 420, self.width() - 200, 620))
        self.cover.setPixmap(cover_pixmap(entry.cover, side))
        self.title.setText(entry.title)
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.stories) - 1)
        self.progress.setValue(0)
        if play:
            self.player.play_file(entry.audio, entry.title)

    # -- commandes ---------------------------------------------------------------------
    def toggle(self) -> None:
        if 0 <= self.index < len(self.stories) and self.player.path is None:
            self.player.play_file(self.stories[self.index].audio, self.stories[self.index].title)
        else:
            self.player.toggle()

    def previous(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._show_current(play=True)

    def next(self) -> None:
        if self.index < len(self.stories) - 1:
            self.index += 1
            self._show_current(play=True)

    def _state(self, state: str) -> None:
        self.play_btn.set_playing(state == "playing")

    def _tick(self) -> None:
        d = self.player.duration()
        if d > 0 and self.stack.currentIndex() == 1:
            self.progress.setValue(int(1000 * min(1.0, self.player.position() / d)))

    # -- fenêtre -----------------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor(NIGHT))
        g.setColorAt(1, QColor("#24306B"))
        p.fillRect(self.rect(), g)
        p.setPen(QPen(QColor(255, 255, 255, 140), 2))
        import random

        rng = random.Random(7)
        for _ in range(60):
            x, y = rng.random() * self.width(), rng.random() * self.height() * 0.6
            p.drawPoint(int(x), int(y))
        p.end()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space:
            self.toggle()
            return
        super().keyPressEvent(e)  # Échap ne ferme pas : seul le cadenas maintenu permet de quitter

    def closeEvent(self, e):
        self.player.stop()
        try:
            self.player.state_changed.disconnect(self._state)
        except (RuntimeError, TypeError):
            pass
        self._timer.stop()
        super().closeEvent(e)

