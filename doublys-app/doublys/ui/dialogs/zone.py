"""Réglage de la bande des sous-titres incrustés : image de la vidéo, bords haut et bas déplaçables à la souris."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QSlider, QVBoxLayout, QWidget

from ... import paths
from ...core import media
from .. import theme
from ..widgets import button, label


class BandView(QWidget):
    """Image avec la bande des sous-titres ; on attrape un bord pour le déplacer."""

    def __init__(self, pixmap: QPixmap, top: float, bottom: float, on_change):
        super().__init__()
        self.pm = pixmap
        self.top, self.bottom = top, bottom
        self.on_change = on_change
        self._drag = None
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)

    def _img_rect(self) -> QRectF:
        if self.pm.isNull():
            return QRectF(self.rect())
        s = self.pm.size().scaled(self.size(), Qt.KeepAspectRatio)
        return QRectF((self.width() - s.width()) / 2, (self.height() - s.height()) / 2, s.width(), s.height())

    def paintEvent(self, e):
        p = QPainter(self)
        r = self._img_rect()
        if not self.pm.isNull():
            p.drawPixmap(r.toRect(), self.pm)
        y0 = r.top() + self.top * r.height()
        y1 = r.top() + self.bottom * r.height()
        shade = QColor(0, 0, 0, 120)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), y0 - r.top()), shade)
        p.fillRect(QRectF(r.left(), y1, r.width(), r.bottom() - y1), shade)
        pen = QPen(QColor(theme.CURRENT.accent), 3)
        p.setPen(pen)
        p.drawLine(int(r.left()), int(y0), int(r.right()), int(y0))
        p.drawLine(int(r.left()), int(y1), int(r.right()), int(y1))
        p.end()

    def _frac(self, y: float) -> float:
        r = self._img_rect()
        return max(0.0, min(1.0, (y - r.top()) / max(1.0, r.height())))

    def mousePressEvent(self, e):
        f = self._frac(e.position().y())
        self._drag = "top" if abs(f - self.top) <= abs(f - self.bottom) else "bottom"
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        f = self._frac(e.position().y())
        near = min(abs(f - self.top), abs(f - self.bottom)) < 0.03
        self.setCursor(Qt.SizeVerCursor if near or self._drag else Qt.ArrowCursor)
        if self._drag == "top":
            self.top = min(f, self.bottom - 0.03)
        elif self._drag == "bottom":
            self.bottom = max(f, self.top + 0.03)
        else:
            return
        self.update()
        self.on_change(self.top, self.bottom)

    def mouseReleaseEvent(self, e):
        self._drag = None


class ZoneDialog(QDialog):
    def __init__(self, parent, project):
        super().__init__(parent)
        self.setWindowTitle("Zone des sous-titres incrustés")
        self.project = project
        self.zone = None
        v = project.video
        top, bottom = (project.subs.zone if project.subs.zone and project.subs.zone[1] > project.subs.zone[0]
                       else (0.78, 0.98))
        self._times = [v.duration * k / 10 for k in range(1, 10)] if v.duration else [0.0]
        lay = QVBoxLayout(self)
        lay.addWidget(label("Faites glisser les deux traits pour encadrer les sous-titres (avec un peu de marge). "
                            "Changez d'image avec le curseur pour en trouver une où un sous-titre est affiché.",
                            "Hint", wrap=True))
        self.view = BandView(self._frame(len(self._times) // 2), top, bottom, self._changed)
        lay.addWidget(self.view, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, len(self._times) - 1)
        self.slider.setValue(len(self._times) // 2)
        self.slider.valueChanged.connect(self._seek)
        lay.addWidget(self.slider)
        self.info = label("", "Hint")
        lay.addWidget(self.info)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Annuler")
        cancel.clicked.connect(self.reject)
        ok = button("Utiliser cette zone", "check", "primary")
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self._changed(top, bottom)
        self.resize(820, 600)

    def _frame(self, k: int) -> QPixmap:
        src = Path(self.project.source_video)
        out = Path(tempfile.mkdtemp(dir=paths.temp_dir())) / "zone.jpg"
        try:
            media.thumbnail(src, self._times[k], out, 960)
            return QPixmap(str(out))
        except Exception:  # noqa: BLE001 - vidéo illisible : cadre vide
            return QPixmap()

    def _seek(self, k: int) -> None:
        self.view.pm = self._frame(k)
        self.view.update()

    def _changed(self, top: float, bottom: float) -> None:
        self.info.setText(f"Bande de {top:.0%} à {bottom:.0%} de la hauteur de l'image")

    def _accept(self) -> None:
        self.zone = (round(self.view.top, 3), round(self.view.bottom, 3))
        self.accept()
