"""Pauses de réflexion proposées par l'assistant IA, à cocher avant de les insérer dans la leçon."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout

from ..widgets import button, card_title


class ReflectionsDialog(QDialog):
    def __init__(self, points, parent=None):
        super().__init__(parent)
        self.points = list(points)
        self.setWindowTitle("Pauses de réflexion")
        self.resize(900, 420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.addWidget(card_title("Pauses de réflexion proposées",
                                 "La question est lue après le paragraphe, puis un silence laisse l'élève réfléchir. "
                                 "Décochez ce que vous ne voulez pas ; les questions sont modifiables.", "lightbulb"))
        self.table = QTableWidget(len(self.points), 3)
        self.table.setHorizontalHeaderLabels(["", "Après le paragraphe", "Question posée"])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for r, p in enumerate(self.points):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, chk)
            ex = QTableWidgetItem(f"{p.number}. {p.excerpt}")
            ex.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 1, ex)
            self.table.setItem(r, 2, QTableWidgetItem(p.question))
        self.table.resizeRowsToContents()
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Insérer les pauses", "check", "primary")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def accepted_points(self):
        out = []
        for r, p in enumerate(self.points):
            if self.table.item(r, 0).checkState() == Qt.Checked:
                q = " ".join(self.table.item(r, 2).text().split())
                if q:
                    p.question = q
                    out.append(p)
        return out
