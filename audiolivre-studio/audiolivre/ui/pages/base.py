"""Classe de base des pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ..widgets import PageHeader


class Page(QWidget):
    name = "page"

    def __init__(self, ctx, title: str, subtitle: str = "", scroll: bool = False):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.content = QWidget()
        self.content.setObjectName("PageContent")
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(34, 28, 34, 24)
        self.body.setSpacing(18)
        self.header = PageHeader(title, subtitle)
        self.body.addWidget(self.header)
        if scroll:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setWidget(self.content)
            outer.addWidget(area)
        else:
            outer.addWidget(self.content)

    def on_show(self) -> None:
        """Appelée quand la page devient visible."""

    def on_project_changed(self) -> None:
        """Appelée quand un autre projet est chargé."""
