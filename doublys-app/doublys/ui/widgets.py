"""Composants d'interface réutilisables (cartes, boutons, anneau de progression, forme d'onde…)."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import (Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget)

from . import icons, theme


# ---------------------------------------------------------------------------------------
# Mise en page
# ---------------------------------------------------------------------------------------
def hbox(*items, spacing: int = 10, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        _add(lay, it)
    return lay


def vbox(*items, spacing: int = 10, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        _add(lay, it)
    return lay


def _add(lay, it) -> None:
    if it is None:
        lay.addStretch(1)
    elif isinstance(it, int):
        lay.addSpacing(it)
    elif isinstance(it, QWidget):
        lay.addWidget(it)
    else:
        lay.addLayout(it)


def label(text: str = "", obj: str | None = None, wrap: bool = False, selectable: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lb


def divider() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    return f


class Card(QFrame):
    def __init__(self, parent=None, obj: str = "Card", margins=(20, 18, 20, 18), spacing: int = 12,
                 shadow: bool = False):
        super().__init__(parent)
        self.setObjectName(obj)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)
        if shadow and theme.CURRENT.dark:
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(28)
            eff.setOffset(0, 6)
            eff.setColor(QColor(0, 0, 0, 90))
            self.setGraphicsEffect(eff)

    def add(self, *items) -> "Card":
        for it in items:
            _add(self.body, it)
        return self


def card_title(title: str, subtitle: str = "", icon_name: str | None = None) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    if icon_name:
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, theme.CURRENT.accent, 20))
        lay.addWidget(ic, 0, Qt.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(2)
    col.addWidget(label(title, "SectionTitle"))
    if subtitle:
        col.addWidget(label(subtitle, "Hint", wrap=True))
    lay.addLayout(col, 1)
    return w


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.title = label(title, "PageTitle")
        self.subtitle = label(subtitle, "PageSubtitle", wrap=True)
        col.addWidget(self.title)
        if subtitle:
            col.addWidget(self.subtitle)
        lay.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)

    def add_action(self, w: QWidget) -> QWidget:
        self.actions.addWidget(w)
        return w


def button(text: str, icon_name: str | None = None, kind: str = "default", tooltip: str = "",
           icon_color: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if kind == "primary":
        b.setObjectName("Primary")
        icon_color = icon_color or "#FFFFFF"
    elif kind == "ghost":
        b.setObjectName("Ghost")
    elif kind == "danger":
        b.setObjectName("Danger")
        icon_color = icon_color or theme.CURRENT.danger
    if icon_name:
        b.setIcon(icons.icon(icon_name, icon_color or theme.CURRENT.text, 18))
        b.setIconSize(QSize(18, 18))
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


class IconButton(QToolButton):
    def __init__(self, icon_name: str, tooltip: str = "", size: int = 34, icon_size: int = 18,
                 color: str | None = None, obj: str | None = None, checkable: bool = False):
        super().__init__()
        self._icon_name = icon_name
        self._color = color
        self._icon_size = icon_size
        self.setIcon(icons.icon(icon_name, color or theme.CURRENT.text, icon_size))
        self.setIconSize(QSize(icon_size, icon_size))
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(checkable)
        if obj:
            self.setObjectName(obj)

    def set_icon_name(self, name: str, color: str | None = None) -> None:
        self._icon_name = name
        if color:
            self._color = color
        self.setIcon(icons.icon(name, self._color or theme.CURRENT.text, self._icon_size))


class Badge(QLabel):
    KINDS = {"accent": "accent", "success": "success", "warning": "warning", "danger": "danger", "info": "info",
             "muted": "muted"}

    def __init__(self, text: str = "", kind: str = "accent"):
        super().__init__(text)
        self.setObjectName("Badge")
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        p = theme.CURRENT
        color = {"accent": p.accent, "success": p.success, "warning": p.warning, "danger": p.danger,
                 "info": p.info, "muted": p.muted}.get(kind, p.accent)
        self.setStyleSheet(f"background: {theme.rgba(color, 0.16)}; color: {color};")

    def set(self, text: str, kind: str) -> None:
        self.setText(text)
        self.set_kind(kind)


class StatTile(QFrame):
    def __init__(self, icon_name: str, value: str, caption: str, color: str | None = None):
        super().__init__()
        self.setObjectName("CardFlat")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 16, 12)
        lay.setSpacing(12)
        color = color or theme.CURRENT.accent
        ic = QLabel()
        ic.setFixedSize(40, 40)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(icons.pixmap(icon_name, color, 20))
        ic.setStyleSheet(f"background: {theme.rgba(color, 0.15)}; border-radius: 12px;")
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.value = label(value, "BigNumber")
        self.value.setStyleSheet("font-size: 15pt; font-weight: 700;")
        self.caption = label(caption, "StatLabel")
        col.addWidget(self.value)
        col.addWidget(self.caption)
        lay.addLayout(col, 1)

    def set_value(self, v: str) -> None:
        self.value.setText(v)


class DropZone(QFrame):
    files_dropped = Signal(list)
    clicked = Signal()

    def __init__(self, title: str, subtitle: str = "", icon_name: str = "upload", height: int = 190):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(height)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        ic = QLabel()
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(icons.pixmap(icon_name, theme.CURRENT.accent, 40))
        lay.addWidget(ic)
        t = label(title, "SectionTitle")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        if subtitle:
            s = label(subtitle, "Hint", wrap=True)
            s.setAlignment(Qt.AlignCenter)
            lay.addWidget(s)

    def _set_hover(self, on: bool) -> None:
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, e):
        self._set_hover(False)

    def dropEvent(self, e):
        self._set_hover(False)
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.files_dropped.emit(files)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def enterEvent(self, e):
        self._set_hover(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._set_hover(False)
        super().leaveEvent(e)


class ToggleSwitch(QCheckBox):
    """Interrupteur animé façon mobile."""

    def __init__(self, text: str = "", checked: bool = False):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self.setChecked(checked)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_knob(self) -> float:
        return self._pos

    def set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        w = 44 + (fm.horizontalAdvance(self.text()) + 10 if self.text() else 0)
        return QSize(w, max(24, fm.height() + 6))

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, (self.height() - 22) / 2, 40, 22)
        off = QColor(p.surface3)
        on = QColor(p.accent)
        c = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        if not self.isEnabled():
            c.setAlpha(110)
        painter.setPen(Qt.NoPen)
        painter.setBrush(c)
        painter.drawRoundedRect(track, 11, 11)
        knob_x = track.left() + 3 + (track.width() - 22) * self._pos
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(knob_x, track.top() + 3, 16, 16))
        if self.text():
            painter.setPen(QColor(p.text if self.isEnabled() else p.faint))
            painter.drawText(QRectF(50, 0, self.width() - 50, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                             self.text())
        painter.end()


class ProgressRing(QWidget):
    def __init__(self, size: int = 150, thickness: int = 12):
        super().__init__()
        self._value = 0.0
        self._text = "0 %"
        self._sub = ""
        self._thickness = thickness
        self._spin = 0.0
        self._busy = False
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._spin = (self._spin + 6) % 360
        self.update()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self._timer.start(30)
        else:
            self._timer.stop()
        self.update()

    def set_value(self, v: float, text: str | None = None, sub: str | None = None) -> None:
        self._value = max(0.0, min(1.0, v))
        self._text = text if text is not None else f"{int(round(self._value * 100))} %"
        if sub is not None:
            self._sub = sub
        self.update()

    def paintEvent(self, e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        t = self._thickness
        r = QRectF(t / 2 + 2, t / 2 + 2, self.width() - t - 4, self.height() - t - 4)
        pen = QPen(QColor(p.surface3), t)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(r, 0, 360 * 16)
        grad = QConicalGradient(r.center(), 90 - (self._spin if self._busy else 0))
        grad.setColorAt(0.0, QColor(p.accent))
        grad.setColorAt(0.5, QColor(p.accent2))
        grad.setColorAt(1.0, QColor(p.accent))
        pen = QPen(QBrush(grad), t)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        span = int(-self._value * 360 * 16)
        if self._value > 0:
            painter.drawArc(r, 90 * 16, span)
        elif self._busy:
            painter.drawArc(r, int((90 - self._spin) * 16), -60 * 16)
        painter.setPen(QColor(p.text))
        f = QFont(self.font())
        f.setPointSizeF(19)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(0, -8 if self._sub else 0, self.width(), self.height()), Qt.AlignCenter, self._text)
        if self._sub:
            f.setPointSizeF(8.5)
            f.setBold(False)
            painter.setFont(f)
            painter.setPen(QColor(p.muted))
            painter.drawText(QRectF(0, 22, self.width(), self.height()), Qt.AlignCenter, self._sub)
        painter.end()


class Avatar(QWidget):
    def __init__(self, name: str, color: str, size: int = 44, icon_name: str | None = None):
        super().__init__()
        self._name = name
        self._color = color
        self._icon = icon_name
        self.setFixedSize(size, size)

    def set(self, name: str, color: str) -> None:
        self._name, self._color = name, color
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        c = QColor(self._color)
        grad.setColorAt(0, c.lighter(125))
        grad.setColorAt(1, c.darker(135))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(r)
        if self._icon:
            pm = icons.pixmap(self._icon, "#FFFFFF", int(self.width() * 0.5))
            painter.drawPixmap(int(self.width() * 0.25), int(self.height() * 0.25), pm)
        else:
            words = [w for w in self._name.replace("(", " ").split() if w[:1].isalnum()]
            initials = "".join(w[0] for w in words[:2]).upper() or "?"
            painter.setPen(QColor("#FFFFFF"))
            f = QFont(self.font())
            f.setBold(True)
            f.setPointSizeF(self.width() * 0.26)
            painter.setFont(f)
            painter.drawText(r, Qt.AlignCenter, initials)
        painter.end()


class RatingDots(QWidget):
    def __init__(self, value: int, color: str | None = None, total: int = 5):
        super().__init__()
        self._value, self._total = value, total
        self._color = color
        self.setFixedSize(total * 14, 12)

    def paintEvent(self, e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for i in range(self._total):
            painter.setBrush(QColor(self._color or p.accent) if i < self._value else QColor(p.surface3))
            painter.drawRoundedRect(QRectF(i * 14, 2, 10, 8), 4, 4)
        painter.end()


class ParamSlider(QWidget):
    """Curseur lié à un paramètre de moteur (ParamSpec)."""

    changed = Signal(str, float)

    def __init__(self, spec, value: float | None = None):
        super().__init__()
        self.spec = spec
        self._scale = 10 ** max(0, spec.decimals)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        self.name = label(spec.label)
        self.value_lbl = label("", "Muted")
        top.addWidget(self.name)
        top.addStretch(1)
        top.addWidget(self.value_lbl)
        lay.addLayout(top)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(round(spec.minimum * self._scale)), int(round(spec.maximum * self._scale)))
        self.slider.setSingleStep(max(1, int(round(spec.step * self._scale))))
        self.slider.valueChanged.connect(self._on_change)
        lay.addWidget(self.slider)
        if spec.help:
            self.setToolTip(spec.help)
        self.set_value(spec.default if value is None else value)

    def _fmt(self, v: float) -> str:
        return f"{v:.{self.spec.decimals}f}".replace(".", ",")

    def _on_change(self, raw: int) -> None:
        v = raw / self._scale
        self.value_lbl.setText(self._fmt(v))
        self.changed.emit(self.spec.key, v)

    def value(self) -> float:
        return self.slider.value() / self._scale

    def set_value(self, v: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(float(v) * self._scale)))
        self.slider.blockSignals(False)
        self.value_lbl.setText(self._fmt(self.value()))


class WaveformView(QWidget):
    """Forme d'onde avec sélection (glisser) et tête de lecture."""

    selection_changed = Signal(float, float)  # secondes
    seek_requested = Signal(float)

    def __init__(self, height: int = 140):
        super().__init__()
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._peaks: np.ndarray | None = None
        self._duration = 0.0
        self._sel: tuple[float, float] | None = None
        self._play = -1.0
        self._drag_from: float | None = None
        self.setMouseTracking(True)
        self.setCursor(Qt.IBeamCursor)

    def set_audio(self, data: np.ndarray, sr: int) -> None:
        from ..core.audio import waveform_peaks

        self._duration = len(data) / float(sr) if sr else 0.0
        peaks = waveform_peaks(data, 900)
        m = float(np.max(np.abs(peaks))) or 1.0
        self._peaks = peaks / m
        self.update()

    def clear(self) -> None:
        self._peaks = None
        self._sel = None
        self._duration = 0.0
        self.update()

    def set_selection(self, start: float, end: float, emit: bool = True) -> None:
        start, end = sorted((max(0.0, start), min(self._duration, end)))
        self._sel = (start, end)
        self.update()
        if emit:
            self.selection_changed.emit(start, end)

    def selection(self) -> tuple[float, float] | None:
        return self._sel

    def set_playhead(self, t: float) -> None:
        self._play = t
        self.update()

    def _x_to_t(self, x: float) -> float:
        return max(0.0, min(self._duration, x / max(1, self.width()) * self._duration))

    def mousePressEvent(self, e):
        if self._peaks is None:
            return
        self._drag_from = self._x_to_t(e.position().x())

    def mouseMoveEvent(self, e):
        if self._drag_from is not None and e.buttons() & Qt.LeftButton:
            t = self._x_to_t(e.position().x())
            self.set_selection(self._drag_from, t, emit=False)

    def mouseReleaseEvent(self, e):
        if self._drag_from is None:
            return
        t = self._x_to_t(e.position().x())
        if abs(t - self._drag_from) < 0.15:
            self.seek_requested.emit(t)
        else:
            self.set_selection(self._drag_from, t)
        self._drag_from = None

    def paintEvent(self, e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        painter.fillPath(path, QColor(p.surface2))
        if self._peaks is None or self._duration <= 0:
            painter.setPen(QColor(p.faint))
            painter.drawText(r, Qt.AlignCenter, "Aucun enregistrement")
            painter.end()
            return
        if self._sel:
            x0 = self._sel[0] / self._duration * self.width()
            x1 = self._sel[1] / self._duration * self.width()
            sel_color = QColor(p.accent)
            sel_color.setAlphaF(0.18)
            painter.fillRect(QRectF(x0, 0, x1 - x0, self.height()), sel_color)
            painter.setPen(QPen(QColor(p.accent), 2))
            painter.drawLine(QPointF(x0, 0), QPointF(x0, self.height()))
            painter.drawLine(QPointF(x1, 0), QPointF(x1, self.height()))
        mid = self.height() / 2
        n = len(self._peaks)
        w = self.width()
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0, QColor(p.accent))
        grad.setColorAt(1, QColor(p.accent2))
        painter.setPen(QPen(QBrush(grad), max(1.0, w / n * 0.7)))
        for i in range(n):
            x = i / n * w
            lo, hi = self._peaks[i]
            amp = max(abs(lo), abs(hi))
            h = max(1.0, amp * (self.height() * 0.42))
            painter.drawLine(QPointF(x, mid - h), QPointF(x, mid + h))
        if self._play >= 0:
            x = self._play / self._duration * w
            painter.setPen(QPen(QColor(p.text), 2))
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        painter.end()


class LevelMeter(QWidget):
    def __init__(self):
        super().__init__()
        self._db = -90.0
        self._peak = -90.0
        self.setFixedHeight(14)

    def set_level(self, db: float) -> None:
        self._db = db
        self._peak = max(db, self._peak - 1.5)
        self.update()

    def paintEvent(self, e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(p.surface3))
        painter.drawRoundedRect(r, 7, 7)
        frac = max(0.0, min(1.0, (self._db + 60) / 60))
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(p.success))
        grad.setColorAt(0.75, QColor(p.warning))
        grad.setColorAt(1.0, QColor(p.danger))
        painter.setBrush(grad)
        painter.drawRoundedRect(QRectF(0, 0, self.width() * frac, self.height()), 7, 7)
        pk = max(0.0, min(1.0, (self._peak + 60) / 60)) * self.width()
        painter.setBrush(QColor(p.text))
        painter.drawRect(QRectF(pk - 2, 0, 2, self.height()))
        painter.end()


class Spinner(QWidget):
    def __init__(self, size: int = 22):
        super().__init__()
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def start(self):
        self._timer.start(25)
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(theme.CURRENT.accent), 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(3, 3, self.width() - 6, self.height() - 6), -self._angle * 16, 100 * 16)
        painter.end()


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str = "", action: QWidget | None = None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(icons.pixmap(icon_name, theme.CURRENT.faint, 54))
        lay.addWidget(ic)
        t = label(title, "SectionTitle")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        if text:
            s = label(text, "Muted", wrap=True)
            s.setAlignment(Qt.AlignCenter)
            s.setMaximumWidth(480)
            lay.addWidget(s, 0, Qt.AlignCenter)
        if action is not None:
            lay.addSpacing(6)
            lay.addWidget(action, 0, Qt.AlignCenter)


class Toast(QFrame):
    """Notification éphémère en haut à droite de la fenêtre."""

    _active: list["Toast"] = []

    def __init__(self, parent: QWidget, message: str, kind: str = "info", duration: int = 3800):
        super().__init__(parent)
        self.setObjectName("Toast")
        p = theme.CURRENT
        color = {"success": p.success, "warning": p.warning, "error": p.danger, "info": p.accent}.get(kind, p.accent)
        icon_name = {"success": "check", "warning": "alert", "error": "alert", "info": "info"}.get(kind, "info")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 16, 12)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, color, 20))
        lay.addWidget(ic, 0, Qt.AlignTop)
        msg = label(message, wrap=True)
        msg.setMaximumWidth(360)
        lay.addWidget(msg, 1)
        self.setStyleSheet(f"#Toast {{ border-left: 4px solid {color}; }}")
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        self._fade = QPropertyAnimation(eff, b"opacity", self)
        self._fade.setDuration(220)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self.adjustSize()
        Toast._active.append(self)
        self._reposition()
        self.show()
        self.raise_()
        self._fade.start()
        QTimer.singleShot(duration, self._close)

    @classmethod
    def _reposition(cls) -> None:
        y = 18
        for t in cls._active:
            par = t.parentWidget()
            if par is None:
                continue
            t.adjustSize()
            t.move(par.width() - t.width() - 22, y)
            y += t.height() + 10

    def _close(self) -> None:
        self._fade.setDirection(QPropertyAnimation.Backward)
        self._fade.finished.connect(self._remove)
        self._fade.start()

    def _remove(self) -> None:
        if self in Toast._active:
            Toast._active.remove(self)
        self.deleteLater()
        Toast._reposition()

    def mousePressEvent(self, e):
        self._close()


def toast(parent: QWidget, message: str, kind: str = "info", duration: int = 3800) -> None:
    win = parent.window() if parent is not None else None
    if win is not None:
        Toast(win, message, kind, duration)


def format_eta(seconds: float) -> str:
    if seconds is None or seconds < 0 or math.isinf(seconds):
        return "calcul…"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"
