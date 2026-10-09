"""Aperçu de lecture : le texte exact envoyé aux voix, segment par segment."""

from __future__ import annotations

from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ...core import renderer
from .. import icons, theme
from ..widgets import IconButton, button, card_title, label


class ReadingPreviewDialog(QDialog):
    def __init__(self, ctx, chapter, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"Aperçu de lecture — {chapter.title}")
        self.resize(1000, 680)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title(f"Aperçu de lecture — {chapter.title}",
                                 "Voici exactement ce que les voix vont lire : abréviations, nombres et dates sont "
                                 "écrits en toutes lettres. Corrigez le manuscrit ou le lexique si besoin.", "eye"))
        try:
            self.plan = renderer.build_chapter_plan(ctx.project, chapter, ctx.library)
        except Exception as exc:
            lay.addWidget(label(f"Impossible de préparer l'aperçu : {exc}", wrap=True))
            self.plan = None
        if self.plan is not None:
            for w in self.plan.warnings:
                warn = label("⚠ " + w, wrap=True)
                warn.setStyleSheet(f"color: {theme.CURRENT.warning};")
                lay.addWidget(warn)
            table = QTableWidget(len(self.plan.segments), 5)
            table.setHorizontalHeaderLabels(["", "Voix", "Texte lu", "Pause", "Type"])
            table.verticalHeader().hide()
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setWordWrap(True)
            hh = table.horizontalHeader()
            hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            hh.setSectionResizeMode(2, QHeaderView.Stretch)
            hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
            kinds = {"title": "Titre", "heading": "Intertitre", "para": "Texte"}
            for i, s in enumerate(self.plan.segments):
                v = ctx.library.get(s.voice_id)
                play = IconButton("play", "Écouter ce passage", 30, 14, color=theme.CURRENT.accent)
                play.clicked.connect(lambda _=False, s=s: self._listen(s))
                table.setCellWidget(i, 0, play)
                vi = QTableWidgetItem(v.name if v else "?")
                if v:
                    vi.setIcon(icons.icon("mic" if v.is_clone else "user", v.color, 16))
                table.setItem(i, 1, vi)
                table.setItem(i, 2, QTableWidgetItem(s.text))
                table.setItem(i, 3, QTableWidgetItem(f"{s.pause_after_ms / 1000:.1f} s".replace(".", ",")))
                table.setItem(i, 4, QTableWidgetItem(kinds.get(s.kind, s.kind)))
            table.resizeRowsToContents()
            lay.addWidget(table, 1)
            chars = self.plan.char_count
            lay.addWidget(label(f"{len(self.plan.segments)} segments · {chars:,} caractères".replace(",", " "),
                                "Hint"))
        row = QHBoxLayout()
        row.addStretch(1)
        close = button("Fermer", kind="primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _listen(self, seg) -> None:
        voice = self.ctx.library.get(seg.voice_id)
        if voice is not None:
            # le texte est déjà normalisé : on évite une seconde normalisation des nombres
            self.ctx.preview_voice(voice, seg.text)

