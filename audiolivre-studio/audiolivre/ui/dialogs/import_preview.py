"""Aperçu du découpage en chapitres avant la création du projet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QSplitter, QVBoxLayout, QWidget)

from ...core import importers
from ...core.models import Chapter
from ...core.textproc import clean_imported_text, format_duration
from .. import icons, theme
from ..widgets import IconButton, button, card_title, label


class ImportPreviewDialog(QDialog):
    def __init__(self, doc, source_name: str, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.original = [Chapter(title=c.title, text=c.text) for c in doc.chapters]
        self.chapters: list[Chapter] = [Chapter(title=c.title, text=c.text) for c in doc.chapters]
        self.setWindowTitle("Vérifier le découpage")
        self.resize(1080, 720)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title(f"Vérifiez les chapitres de « {source_name} »",
                                 "Décochez ce qui ne doit pas être lu (sommaire, mentions légales…), renommez ou "
                                 "fusionnez des chapitres, ou essayez un autre découpage.", "list"))
        top = QHBoxLayout()
        top.addWidget(label("Titre du livre", "Muted"))
        self.title = QLineEdit(doc.metadata.title)
        top.addWidget(self.title, 2)
        top.addSpacing(16)
        top.addWidget(label("Découpage", "Muted"))
        self.mode = QComboBox()
        for k, v in importers.SPLIT_MODES.items():
            self.mode.addItem(v, k)
        self.mode.currentIndexChanged.connect(self._resplit)
        top.addWidget(self.mode, 1)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show)
        self.list.itemChanged.connect(self._item_changed)
        ll.addWidget(self.list, 1)
        tb = QHBoxLayout()
        merge = IconButton("layers", "Fusionner avec le chapitre précédent", 34, 16)
        merge.clicked.connect(self._merge_prev)
        delete = IconButton("trash", "Supprimer ce chapitre", 34, 16, color=theme.CURRENT.danger)
        delete.clicked.connect(self._delete)
        tb.addWidget(merge)
        tb.addWidget(delete)
        tb.addStretch(1)
        self.stats = label("", "Hint")
        tb.addWidget(self.stats)
        ll.addLayout(tb)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 0, 0, 0)
        self.ch_title = QLineEdit()
        self.ch_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        self.ch_title.textEdited.connect(self._rename)
        rl.addWidget(self.ch_title)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        rl.addWidget(self.preview, 1)
        split.addWidget(right)
        split.setSizes([380, 680])
        lay.addWidget(split, 1)

        for w in doc.warnings:
            warn = label("⚠ " + w, wrap=True)
            warn.setStyleSheet(f"color: {theme.CURRENT.warning};")
            lay.addWidget(warn)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Créer le projet", "check", "primary")
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self._fill()

    # ------------------------------------------------------------------------------
    def _fill(self, select: int = 0) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for ch in self.chapters:
            words = ch.word_count()
            it = QListWidgetItem(icons.icon("book", theme.CURRENT.accent, 16),
                                 f"{ch.title}\n{words:,} mots · ≈ {format_duration(words / 155 * 60)}".replace(",", " "))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if ch.include else Qt.Unchecked)
            self.list.addItem(it)
        self.list.blockSignals(False)
        if self.chapters:
            self.list.setCurrentRow(max(0, min(select, len(self.chapters) - 1)))
        self._update_stats()

    def _update_stats(self) -> None:
        inc = [c for c in self.chapters if c.include]
        words = sum(c.word_count() for c in inc)
        self.stats.setText(f"{len(inc)}/{len(self.chapters)} chapitres · ≈ {format_duration(words / 155 * 60)}")

    def _row(self) -> int:
        return self.list.currentRow()

    def _show(self, row: int) -> None:
        if 0 <= row < len(self.chapters):
            ch = self.chapters[row]
            self.ch_title.setText(ch.title)
            self.preview.setPlainText(ch.text[:20000])

    def _item_changed(self, it: QListWidgetItem) -> None:
        row = self.list.row(it)
        if 0 <= row < len(self.chapters):
            self.chapters[row].include = it.checkState() == Qt.Checked
            self._update_stats()

    def _rename(self, text: str) -> None:
        row = self._row()
        if 0 <= row < len(self.chapters):
            self.chapters[row].title = text
            it = self.list.item(row)
            words = self.chapters[row].word_count()
            self.list.blockSignals(True)
            it.setText(f"{text}\n{words:,} mots · ≈ {format_duration(words / 155 * 60)}".replace(",", " "))
            self.list.blockSignals(False)

    def _merge_prev(self) -> None:
        row = self._row()
        if row <= 0:
            return
        prev, cur = self.chapters[row - 1], self.chapters[row]
        prev.text = (prev.text.rstrip() + "\n\n# " + cur.title + "\n\n" + cur.text.lstrip()).strip()
        del self.chapters[row]
        self._fill(row - 1)

    def _delete(self) -> None:
        row = self._row()
        if 0 <= row < len(self.chapters) and len(self.chapters) > 1:
            del self.chapters[row]
            self._fill(row)

    def _resplit(self) -> None:
        mode = self.mode.currentData()
        self.chapters = importers.resplit(self.original, mode, self.title.text().strip())
        self._fill()

    def _accept(self) -> None:
        kept = [c for c in self.chapters if c.text.strip() or c.title.strip()]
        for c in kept:
            c.text = clean_imported_text(c.text)
        self.doc.chapters = kept
        self.doc.metadata.title = self.title.text().strip() or self.doc.metadata.title
        self.accept()
