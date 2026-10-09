"""Jeu d'icônes vectorielles (dessinées en SVG, teintées à la volée)."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .. import paths

_STROKE = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>',
    "book": '<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>'
            '<path d="M8 13h8M8 17h8M8 9h2"/>',
    "file-plus": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M12 18v-6M9 15h6"/>',
    "mic": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1"/><path d="M12 18v4M8 22h8"/>',
    "users": '<circle cx="9" cy="8" r="4"/><path d="M2 21v-1a6 6 0 0 1 6-6h2a6 6 0 0 1 6 6v1"/>'
             '<path d="M16 3.5a4 4 0 0 1 0 8"/><path d="M19 14.5a6 6 0 0 1 3 5.5v1"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a7 7 0 0 1 16 0v1"/>',
    "sparkles": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 3v4M17 5h4M5 17v4M3 19h4"/>',
    "download": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    "upload": '<path d="M12 21V9"/><path d="m7 14 5-5 5 5"/><path d="M5 3h14"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "cpu": '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
           '<path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4"/>',
    "package": '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
    "edit": '<path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    "volume": '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
    "headphones": '<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1v-7h3zM3 19a2 2 0 0 0 2 2h1v-7H3z"/>',
    "wave": '<path d="M2 12h1M6 8v8M10 4v16M14 7v10M18 10v4M22 12h-1"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2'
           'M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "star": '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "up": '<path d="M12 19V5M5 12l7-7 7 7"/>',
    "down": '<path d="M12 5v14M19 12l-7 7-7-7"/>',
    "layers": '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "rocket": '<path d="M4.5 16.5c-1.5 1.3-2 5-2 5s3.7-.5 5-2c.7-.8.7-2.1-.1-2.9a2.2 2.2 0 0 0-2.9-.1z"/>'
              '<path d="M12 15l-3-3a22 22 0 0 1 2-3.9A12.9 12.9 0 0 1 22 2c0 2.7-.8 7.5-6 11a22.4 22.4 0 0 1-4 2z"/>'
              '<path d="M9 12H4s.6-3 2-4c1.6-1.1 5 0 5 0M12 15v5s3-.6 4-2c1.1-1.6 0-5 0-5"/>',
    "type": '<path d="M4 7V4h16v3M9 20h6M12 4v16"/>',
    "dictionary": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>'
                  '<path d="M9 7h6M9 11h4"/>',
    "external": '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "more": '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    "pause-mark": '<path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4"/>',
    "quote": '<path d="M3 21c3 0 7-1 7-8V5c0-1.2-.8-2-2-2H4c-1.3 0-2 .8-2 2v6c0 1.2.8 2 2 2h3c0 4-1 5-4 5z"/>'
             '<path d="M15 21c3 0 7-1 7-8V5c0-1.2-.8-2-2-2h-4c-1.3 0-2 .8-2 2v6c0 1.2.8 2 2 2h3c0 4-1 5-4 5z"/>',
    "palette": '<circle cx="13.5" cy="6.5" r="1"/><circle cx="17.5" cy="10.5" r="1"/><circle cx="8.5" cy="7.5" r="1"/>'
               '<circle cx="6.5" cy="12.5" r="1"/><path d="M12 2a10 10 0 0 0 0 20c1.7 0 2-1.3 2-2.2 0-1.5-1.2-1.8-1.2-3 0-1 .8-1.8 1.8-1.8H17a5 5 0 0 0 5-5C22 5.6 17.5 2 12 2z"/>',
    "keyboard": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 13h.01M18 13h.01M8 16h8M10 13h4"/>',
    "award": '<circle cx="12" cy="8" r="6"/><path d="M15.5 13 17 22l-5-3-5 3 1.5-9"/>',
    "skip-back": '<path d="M19 20 9 12l10-8z"/><path d="M5 19V5"/>',
    "skip-fwd": '<path d="m5 4 10 8-10 8z"/><path d="M19 5v14"/>',
}

_FILLED = {
    "play": '<path d="M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5z"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1.2"/><rect x="14" y="4" width="4" height="16" rx="1.2"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2.5"/>',
    "record": '<circle cx="12" cy="12" r="7"/>',
    "star-filled": '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/>',
}

_cache: dict[tuple, QIcon] = {}


def svg(name: str, color: str) -> bytes:
    if name in _FILLED:
        body = _FILLED[name]
        attrs = f'fill="{color}" stroke="none"'
    else:
        body = _STROKE.get(name, _STROKE["info"])
        attrs = f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {attrs}>{body}</svg>'.encode()


def pixmap(name: str, color: str | None = None, size: int = 20, dpr: float = 2.0) -> QPixmap:
    from . import theme

    color = color or theme.CURRENT.text
    renderer = QSvgRenderer(QByteArray(svg(name, color)))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    from . import theme

    color = color or theme.CURRENT.text
    key = (name, color, size)
    ic = _cache.get(key)
    if ic is None:
        ic = QIcon()
        ic.addPixmap(pixmap(name, color, size, 1.0))
        ic.addPixmap(pixmap(name, color, size, 2.0))
        _cache[key] = ic
    return ic


def clear_cache() -> None:
    _cache.clear()


def check_icon_file() -> str:
    target = paths.data_dir() / "ui" / "check.svg"
    target.parent.mkdir(parents=True, exist_ok=True)
    data = svg("check", "#FFFFFF").replace(b'stroke-width="2"', b'stroke-width="3.2"')
    if not target.exists() or target.read_bytes() != data:
        target.write_bytes(data)
    return str(target).replace("\\", "/")


def app_logo(size: int = 256) -> QPixmap:
    """Logo de l'application : livre ouvert sur fond dégradé avec onde sonore."""
    from . import theme

    p = theme.CURRENT
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, QColor(p.accent))
    grad.setColorAt(1, QColor(p.accent2))
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.24, size * 0.24)
    painter.fillPath(path, grad)
    renderer = QSvgRenderer(QByteArray(svg("book", "#FFFFFF").replace(b'stroke-width="2"', b'stroke-width="1.8"')))
    renderer.render(painter, QRectF(size * 0.2, size * 0.16, size * 0.6, size * 0.6))
    # onde sonore
    pen_color = QColor("#FFFFFF")
    painter.setPen(Qt.NoPen)
    painter.setBrush(pen_color)
    bars = [0.35, 0.7, 1.0, 0.6, 0.85, 0.45, 0.25]
    bw = size * 0.045
    gap = size * 0.03
    total = len(bars) * bw + (len(bars) - 1) * gap
    x = (size - total) / 2
    base_y = size * 0.83
    for h in bars:
        bh = size * 0.12 * h
        painter.drawRoundedRect(QRectF(x, base_y - bh / 2, bw, bh), bw / 2, bw / 2)
        x += bw + gap
    painter.end()
    return pm


def app_icon() -> QIcon:
    ico = paths.resource("app.ico")
    if ico.exists():
        return QIcon(str(ico))
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_logo(s))
    return ic
