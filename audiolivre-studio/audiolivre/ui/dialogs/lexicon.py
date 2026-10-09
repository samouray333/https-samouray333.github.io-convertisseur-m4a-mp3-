"""Dictionnaire de prononciation du projet."""

from __future__ import annotations

import copy
import csv
import re
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...core.models import LexiconEntry
from ...core.textproc import NormalizeOptions, normalize_for_speech
from ..widgets import Card, button, card_title, label

COLS = ["Texte écrit", "Prononciation", "Mot entier", "Casse exacte", "Expression régulière", "Actif"]


def _check(on: bool) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setAlignment(Qt.AlignCenter)
    cb = QCheckBox()
    cb.setChecked(on)
    lay.addWidget(cb)
    return w


class LexiconDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Lexique de prononciation")
        self.resize(940, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)
        lay.addWidget(card_title("Lexique de prononciation",
                                 "Indiquez comment lire les noms propres, sigles ou mots étrangers. "
                                 "Exemple : « GIEC » → « gièque », « Saint-Saëns » → « Saint-Sanss ».",
                                 "dictionary"))
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, len(COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        add = button("Ajouter", "plus")
        add.clicked.connect(lambda: self._add(LexiconEntry("", "")))
        rem = button("Supprimer", "trash", "danger")
        rem.clicked.connect(self._remove)
        detect = button("Détecter les sigles", "sparkles", tooltip="Repère les mots en majuscules du manuscrit")
        detect.clicked.connect(self._detect)
        imp = button("Importer CSV", "upload")
        imp.clicked.connect(self._import)
        exp = button("Exporter CSV", "download")
        exp.clicked.connect(self._export)
        for b in (add, rem, detect):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(imp)
        row.addWidget(exp)
        lay.addLayout(row)

        test = Card(obj="CardFlat", margins=(14, 12, 14, 12))
        tr = QHBoxLayout()
        self.test_in = QLineEdit()
        self.test_in.setPlaceholderText("Testez une phrase : « Le GIEC s'est réuni le 12/03/2024 à 14h30. »")
        self.test_in.textChanged.connect(self._test)
        listen = button("Écouter", "headphones")
        listen.clicked.connect(self._listen)
        tr.addWidget(self.test_in, 1)
        tr.addWidget(listen)
        test.add(tr)
        self.test_out = label("", "Muted", wrap=True, selectable=True)
        test.add(self.test_out)
        lay.addWidget(test)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Enregistrer le lexique", "check", "primary")
        ok.clicked.connect(self._accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

        for e in ctx.project.lexicon:
            self._add(e)

    def _add(self, e: LexiconEntry) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(e.pattern))
        self.table.setItem(r, 1, QTableWidgetItem(e.replacement))
        for c, v in zip(range(2, 6), (e.whole_word, e.case_sensitive, e.regex, e.enabled)):
            self.table.setCellWidget(r, c, _check(v))
        if not e.pattern:
            self.table.editItem(self.table.item(r, 0))

    def _remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def entries(self) -> list[LexiconEntry]:
        out = []
        for r in range(self.table.rowCount()):
            pat = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            rep = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            if not pat:
                continue
            flags = [self.table.cellWidget(r, c).findChild(QCheckBox).isChecked() for c in range(2, 6)]
            out.append(LexiconEntry(pattern=pat, replacement=rep, whole_word=flags[0], case_sensitive=flags[1],
                                    regex=flags[2], enabled=flags[3]))
        return out

    def _test(self) -> None:
        opts = NormalizeOptions(language=self.ctx.project.metadata.language or "fr")
        self.test_out.setText("→ " + normalize_for_speech(self.test_in.text(), opts, self.entries()))

    def _listen(self) -> None:
        text = self.test_in.text().strip()
        if not text:
            return
        voice = self.ctx.library.get(self.ctx.project.narrator_voice_id) or (self.ctx.library.all() or [None])[0]
        if voice is None:
            return
        trial = copy.copy(self.ctx.project)
        trial.lexicon = self.entries()
        self.ctx.preview_voice(voice, text, project=trial)

    def _detect(self) -> None:
        text = "\n".join(c.text for c in self.ctx.project.included_chapters())
        counts = Counter(re.findall(r"\b[A-ZÉÈ]{2,6}\b", text))
        existing = {e.pattern for e in self.entries()}
        common = {"OK", "TV", "USA", "UE", "ONU", "SNCF", "PDF", "CD", "DVD", "II", "III", "IV", "VI", "VII", "VIII",
                  "IX", "XI", "XII", "XV", "XX", "XIX", "XVI", "XVII", "XVIII", "XXI"}
        added = 0
        for word, n in counts.most_common(40):
            if word in existing or word in common or n < 2:
                continue
            self._add(LexiconEntry(word, " ".join(word), whole_word=True, case_sensitive=True))
            added += 1
        self.ctx.toast(f"{added} sigle(s) ajouté(s) : vérifiez leur prononciation." if added
                       else "Aucun nouveau sigle détecté.", "info")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer un lexique", "", "CSV (*.csv);;Tous (*)")
        if not path:
            return
        with open(path, encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(2048)
            fh.seek(0)
            delim = ";" if sample.count(";") >= sample.count(",") else ","
            for row in csv.reader(fh, delimiter=delim):
                if len(row) >= 2 and row[0].strip() and row[0].strip().lower() not in ("texte écrit", "pattern"):
                    self._add(LexiconEntry(row[0].strip(), row[1].strip()))

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le lexique", "lexique.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["Texte écrit", "Prononciation"])
            for e in self.entries():
                w.writerow([e.pattern, e.replacement])

    def _accept(self) -> None:
        self.ctx.project.lexicon = self.entries()
        self.accept()
