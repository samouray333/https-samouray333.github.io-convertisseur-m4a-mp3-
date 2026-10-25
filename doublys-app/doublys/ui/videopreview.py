"""Aperçu vidéo intégré, sans QtMultimedia : images extraites par FFmpeg, synchronisées sur le lecteur audio,
avec le sous-titre français de la réplique en cours."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel

from . import theme


class VideoPreview(QLabel):
    def __init__(self, width: int = 320, height: int = 180):
        super().__init__()
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"background: {theme.CURRENT.surface3}; border-radius: 10px;")
        self._frames: list[Path] = []
        self._cache: dict[int, QPixmap] = {}
        self._fps = 12.0
        self._t0 = 0.0
        self._audio_t0 = 0.0
        self._subs: list[tuple[float, float, str]] = []
        self._player = None
        self._shown = -1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # -- vignette fixe ----------------------------------------------------------------
    def show_image(self, path) -> None:
        self.stop()
        pm = QPixmap(str(path))
        if not pm.isNull():
            self.setPixmap(pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # -- extrait animé ----------------------------------------------------------------
    def play(self, frames: list[Path], fps: float, t0: float, player, audio_t0: float,
             subs: list[tuple[float, float, str]]) -> None:
        """``t0`` : instant de la vidéo de la première image ; ``audio_t0`` : instant du fichier audio joué qui
        correspond à ``t0`` ; ``subs`` : [(début, fin, texte)] en temps de la vidéo."""
        self._frames = frames
        self._cache.clear()
        self._fps = fps
        self._t0 = t0
        self._audio_t0 = audio_t0
        self._subs = subs
        self._player = player
        self._shown = -1
        self._timer.start(30)
        self._render(0)

    def stop(self) -> None:
        self._timer.stop()
        self._frames = []
        self._cache.clear()

    def is_playing(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        p = self._player
        if p is None or not self._frames:
            return
        if p.state() == "stopped" and self._shown >= 0:
            self._timer.stop()
            return
        t = p.position() - self._audio_t0  # secondes depuis le début de l'extrait
        idx = max(0, min(len(self._frames) - 1, int(t * self._fps)))
        if idx != self._shown:
            self._render(idx)

    def _render(self, idx: int) -> None:
        if not self._frames:
            return
        pm = self._cache.get(idx)
        if pm is None:
            src = QPixmap(str(self._frames[idx]))
            if src.isNull():
                return
            pm = src.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if len(self._cache) > 120:
                self._cache.clear()
            self._cache[idx] = pm
        t = self._t0 + idx / self._fps
        text = next((s for a, b, s in self._subs if a <= t <= b), "")
        self._shown = idx
        if not text:
            self.setPixmap(pm)
            return
        out = QPixmap(pm)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font())
        f.setPointSizeF(max(7.5, out.height() / 17))
        f.setBold(True)
        painter.setFont(f)
        rect = QRectF(6, out.height() * 0.62, out.width() - 12, out.height() * 0.36)
        flags = Qt.AlignHCenter | Qt.AlignBottom | Qt.TextWordWrap
        bound = painter.boundingRect(rect, flags, text)
        bg = QPainterPath()
        bg.addRoundedRect(bound.adjusted(-6, -3, 6, 3), 6, 6)
        painter.fillPath(bg, QColor(0, 0, 0, 160))
        painter.setPen(QPen(QColor("#FFFFFF")))
        painter.drawText(rect, flags, text)
        painter.end()
        self.setPixmap(out)
