"""Correction d'un passage depuis la Production : texte et prononciation d'un mot."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout

from ..widgets import button, card_title, label


class CorrectSegmentDialog(QDialog):
    def __init__(self, text: str, heard: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Corriger le passage")
        self.resize(720, 0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title("Corriger ce passage",
                                 "Modifiez le texte (il est aussi corrigé dans le manuscrit) ou indiquez comment "
                                 "prononcer un mot. Seul ce passage est ensuite refait.", "edit"))
        if heard:
            lay.addWidget(label(f"La relecture automatique a entendu : « {heard} »", "Hint", wrap=True))
        self.text = QPlainTextEdit(text)
        self.text.setObjectName("Editor")
        self.text.setMinimumHeight(110)
        lay.addWidget(self.text)
        lay.addWidget(label("Balises possibles : [pause 1s], [lent], [rapide], *mot* pour insister.", "Faint"))
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        self.word = QLineEdit()
        self.word.setPlaceholderText("ex. : Siobhan")
        self.say = QLineEdit()
        self.say.setPlaceholderText("ex. : Chivône")
        g.addWidget(label("Mot mal prononcé", "Muted"), 0, 0)
        g.addWidget(self.word, 0, 1)
        g.addWidget(label("Se prononce", "Muted"), 0, 2)
        g.addWidget(self.say, 0, 3)
        lay.addLayout(g)
        lay.addWidget(label("La prononciation est ajoutée au lexique du projet : elle s'applique à tout le livre.",
                            "Hint", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Corriger et refaire", "refresh", "primary")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def values(self) -> tuple[str, str, str]:
        return self.text.toPlainText().strip(), self.word.text().strip(), self.say.text().strip()
