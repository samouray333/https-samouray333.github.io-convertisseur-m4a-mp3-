"""Éditeur de calage : forme d'onde de la voix d'origine autour de la réplique choisie ; chaque réplique (bande du
haut) se déplace ou s'étire à la souris, la voix française produite est affichée dessous."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme

EDGE_PX = 7
MIN_LEN = 0.3


class TimelineView(QWidget):
    edited = Signal(str, float, float)  # réplique, nouveau début, nouvelle fin
    selected = Signal(str)

    def __init__(self, height: int = 96):
        super().__init__()
        self.setMinimumHeight(height)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self.t0 = 0.0
        self.t1 = 10.0
        self.peaks = None  # (n, 2) min/max
        self.lines = []  # [(id, début, fin, durée de la voix française, couleur, libellé)]
        self.current = ""
        self._drag = None  # (mode, id, t_press, start, end)
        self._preview: tuple[float, float] | None = None
        self.setToolTip("Glissez une réplique pour la déplacer, tirez ses bords pour changer sa durée.")

    def set_view(self, t0: float, t1: float, peaks, lines, current: str) -> None:
        self.t0, self.t1 = t0, max(t0 + 1.0, t1)
        self.peaks = peaks
        self.lines = lines
        self.current = current
        self._preview = None
        self.update()

    def clear(self) -> None:
        self.peaks = None
        self.lines = []
        self.update()

    # -- coordonnées ------------------------------------------------------------------
    def _x(self, t: float) -> float:
        return (t - self.t0) / (self.t1 - self.t0) * self.width()

    def _t(self, x: float) -> float:
        return self.t0 + x / max(1, self.width()) * (self.t1 - self.t0)

    def _band(self) -> tuple[float, float]:
        return 6.0, self.height() * 0.42

    def _hit(self, pos: QPointF):
        y0, y1 = self._band()
        if not (y0 <= pos.y() <= y1 + 4):
            return None
        for lid, start, end, _vf, _c, _l in self.lines:
            x0, x1 = self._x(start), self._x(end)
            if x0 - EDGE_PX <= pos.x() <= x1 + EDGE_PX:
                if abs(pos.x() - x0) <= EDGE_PX:
                    return "start", lid, start, end
                if abs(pos.x() - x1) <= EDGE_PX:
                    return "end", lid, start, end
                return "move", lid, start, end
        return None

    # -- souris -----------------------------------------------------------------------
    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._drag is None:
            hit = self._hit(pos)
            shape = Qt.ArrowCursor
            if hit and hit[1] == self.current:
                shape = Qt.SizeHorCursor if hit[0] in ("start", "end") else Qt.OpenHandCursor
            self.setCursor(shape)
            return
        mode, lid, t_press, start, end = self._drag
        dt = self._t(pos.x()) - t_press
        if mode == "move":
            ns, ne = max(0.0, start + dt), max(0.0, start + dt) + (end - start)
        elif mode == "start":
            ns, ne = min(max(0.0, start + dt), end - MIN_LEN), end
        else:
            ns, ne = start, max(start + MIN_LEN, end + dt)
        self._preview = (round(ns, 3), round(ne, 3))
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        hit = self._hit(e.position())
        if hit is None:
            return
        mode, lid, start, end = hit
        if lid != self.current:
            self.selected.emit(lid)
            return
        self._drag = (mode, lid, self._t(e.position().x()), start, end)
        if mode == "move":
            self.setCursor(Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, e):
        if self._drag is None:
            return
        _mode, lid, _t, start, end = self._drag
        self._drag = None
        prev, self._preview = self._preview, None
        self.setCursor(Qt.ArrowCursor)
        if prev and (abs(prev[0] - start) > 0.02 or abs(prev[1] - end) > 0.02):
            self.edited.emit(lid, prev[0], prev[1])
        self.update()

    # -- dessin ------------------------------------------------------------------------
    def paintEvent(self, _e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(p.surface2))
        w, h = self.width(), self.height()
        y0, y1 = self._band()
        # forme d'onde (voix d'origine) dans la moitié basse
        if self.peaks is not None and len(self.peaks):
            mid = h * 0.72
            amp = h * 0.24
            painter.setPen(QPen(QColor(p.muted), 1))
            n = len(self.peaks)
            for i in range(0, w, 2):
                k = min(n - 1, int(i / max(1, w) * n))
                lo, hi = self.peaks[k]
                painter.drawLine(QPointF(i, mid - hi * amp), QPointF(i, mid - lo * amp))
        # graduations (secondes)
        painter.setPen(QPen(QColor(p.faint), 1))
        t = int(self.t0)
        while t <= self.t1:
            x = self._x(t)
            painter.drawLine(QPointF(x, h - 6), QPointF(x, h))
            t += 1
        for lid, start, end, vf_dur, color, text in self.lines:
            if lid == self.current and self._preview:
                start, end = self._preview
            vf_end = start + vf_dur
            cur = lid == self.current
            c = QColor(color)
            c.setAlpha(230 if cur else 110)
            r = QRectF(self._x(start), y0, max(3.0, self._x(end) - self._x(start)), y1 - y0)
            painter.setPen(QPen(QColor("#FFFFFF"), 2) if cur else QPen(Qt.NoPen))
            painter.setBrush(c)
            painter.drawRoundedRect(r, 5, 5)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(r.adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
            # voix française produite (durée réelle) sous la réplique
            if vf_end > start:
                vr = QRectF(self._x(start), y1 + 3, max(2.0, self._x(vf_end) - self._x(start)), 5)
                over = vf_end > end + 0.05
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(p.warning if over else p.accent))
                painter.drawRoundedRect(vr, 2, 2)
        painter.end()
