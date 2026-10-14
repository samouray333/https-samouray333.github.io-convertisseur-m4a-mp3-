"""Page Glossaire : tous les mots et phrases du cours, par langue, avec les favoris et l'écoute."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLineEdit,
                               QTableWidget, QTableWidgetItem)

from ...core import handouts, languages, srs
from ...core.models import REVIEW_STEPS
from .. import theme
from ..widgets import Card, button, label
from .base import Page

COLUMNS = ["★", "Langue apprise", "Prononciation", "Traduction", "Exemple", "Leçon", "Révision"]


class GlossaryPage(Page):
    name = "glossary"

    def __init__(self, ctx):
        super().__init__(ctx, "Glossaire", "Tous les mots et phrases du cours, par langue. Double-cliquez sur ★ pour "
                         "ajouter une phrase à vos favoris ; les favoris s'exportent en flashcards et dans Anki.")
        flash = button("Flashcards des favoris", "star", tooltip="Flashcards imprimables recto-verso des favoris")
        flash.clicked.connect(lambda: self._export_cards(True))
        allc = button("Toutes les flashcards", "file")
        allc.clicked.connect(lambda: self._export_cards(False))
        listen = button("Écouter", "headphones", "primary")
        listen.clicked.connect(self._listen)
        for b in (allc, flash, listen):
            self.header.add_action(b)
        card = Card()
        row = QHBoxLayout()
        self.lang = QComboBox()
        self.lang.setMinimumWidth(220)
        self.lang.currentIndexChanged.connect(self._fill)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un mot, une traduction…")
        self.search.textChanged.connect(self._fill)
        self.fav = QCheckBox("Favoris seulement")
        self.fav.toggled.connect(self._fill)
        self.count = label("", "Faint")
        for w in (self.lang, self.search, self.fav, self.count):
            row.addWidget(w)
        row.setStretch(1, 1)
        card.add(row)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in range(1, len(COLUMNS)):
            hh.setSectionResizeMode(c, QHeaderView.Stretch if c in (1, 3, 4) else QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        card.add(self.table)
        self.body.addWidget(card, 1)
        self._rows: list = []

    def on_project_changed(self) -> None:
        self.reload()

    def on_show(self) -> None:
        self.reload()

    def reload(self) -> None:
        current = self.lang.currentData()
        groups = handouts.glossary(self.ctx.project)
        self.lang.blockSignals(True)
        self.lang.clear()
        self.lang.addItem("Toutes les langues", "")
        for code, pairs in groups.items():
            self.lang.addItem(f"{languages.language_name(code, True)} ({len(pairs)})", code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(current)))
        self.lang.blockSignals(False)
        self._fill()

    def _fill(self, *_a) -> None:
        pr = self.ctx.project
        code = self.lang.currentData() or ""
        q = self.search.text().strip().lower()
        groups = handouts.glossary(pr, self.fav.isChecked())
        rows = [(c, v) for lang, pairs in groups.items() if not code or lang == code for c, v in pairs
                if not q or q in f"{v.term} {v.translation} {v.translit} {v.example}".lower()]
        self._rows = rows
        self.table.setRowCount(len(rows))
        for r, (ch, it) in enumerate(rows):
            star = QTableWidgetItem("★" if it.favorite else "☆")
            star.setForeground(QColor(theme.CURRENT.accent2 if it.favorite else theme.CURRENT.faint))
            star.setTextAlignment(Qt.AlignCenter)
            st = pr.reviews.get(it.id)
            if st is None:
                rev = "—"
            elif st.learned:
                rev = "acquis"
            else:
                rev = f"J+{REVIEW_STEPS[min(st.step, len(REVIEW_STEPS) - 1)]} le {st.due[8:10]}/{st.due[5:7]}"
            vals = [it.term, it.translit, it.translation, it.example, ch.title, rev]
            self.table.setItem(r, 0, star)
            for c, v in enumerate(vals, 1):
                self.table.setItem(r, c, QTableWidgetItem(v))
        due = len(srs.due_items(pr))
        self.count.setText(f"{len(rows)} élément(s)" + (f" · {due} à réviser aujourd'hui" if due else ""))

    def _double_clicked(self, row: int, col: int) -> None:
        if not (0 <= row < len(self._rows)):
            return
        ch, it = self._rows[row]
        if col == 0:
            it.favorite = not it.favorite
            self.ctx.mark_dirty()
            self._fill()
        else:
            self._listen_item(ch, it)

    def _listen(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            self._listen_item(*self._rows[row])
        else:
            self.ctx.toast("Sélectionnez un mot.", "info")

    def _listen_item(self, ch, it) -> None:
        from ...core import course, renderer

        spec = course.target_spec(self.ctx.project, ch)
        voice = renderer.VoiceResolver(self.ctx.project, self.ctx.library).native(spec, ch)
        self.ctx.preview_voice(voice, it.term, language=spec)

    def _export_cards(self, favorites: bool) -> None:
        from PySide6.QtWidgets import QFileDialog

        from ...core import project_io
        from ..main_window import open_path

        pr = self.ctx.project
        if not pr.all_vocab():
            self.ctx.toast("Aucun mot dans le cours.", "warning")
            return
        if favorites and not any(v.favorite for _c, v in pr.all_vocab()):
            self.ctx.toast("Aucun favori : double-cliquez sur ☆ pour en ajouter.", "info")
            return
        out = project_io.default_export_dir(pr)
        out.mkdir(parents=True, exist_ok=True)
        default = out / ("Flashcards favoris.html" if favorites else "Flashcards.html")
        path, _ = QFileDialog.getSaveFileName(self, "Flashcards", str(default), "Page web (*.html)")
        if not path:
            return
        from pathlib import Path

        handouts.write_flashcards(pr, Path(path), favorites_only=favorites)
        open_path(Path(path))
        self.ctx.toast("Flashcards prêtes : imprimez en recto-verso, puis découpez.", "success")
