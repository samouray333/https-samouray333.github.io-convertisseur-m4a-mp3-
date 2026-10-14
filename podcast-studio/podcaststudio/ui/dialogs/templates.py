"""Choix du modèle d'émission à la création d'un podcast (ou d'un nouvel épisode)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QDialog, QFrame, QGridLayout, QHBoxLayout, QRadioButton, QVBoxLayout

from ...core.models import HOST_ROLES
from ...core.templates import TEMPLATES
from .. import theme
from ..widgets import button, card_title, label

ICONS = {"conversation": "users", "interview": "mic", "chronique": "user", "revue": "list", "debat": "quote"}


class TemplateDialog(QDialog):
    def __init__(self, parent=None, title: str = "Nouveau podcast", for_episode: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 520)
        self.selected = TEMPLATES[0].key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)
        sub = ("La trame de l'épisode (rubriques, jingles, chapitres) est ajoutée : il ne reste qu'à la compléter."
               if for_episode else "Choisissez un format d'émission : les intervenants et la trame du premier "
               "épisode sont préparés pour vous. Tout reste modifiable.")
        lay.addWidget(card_title("Quel type d'émission ?", sub, "podcast"))
        grid = QGridLayout()
        grid.setSpacing(12)
        self.group = QButtonGroup(self)
        p = theme.CURRENT
        for i, t in enumerate(TEMPLATES):
            card = QFrame()
            card.setObjectName("CardFlat")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            rb = QRadioButton(t.name)
            rb.setStyleSheet("font-weight: 700; font-size: 11pt;")
            rb.setChecked(i == 0)
            rb.toggled.connect(lambda on, k=t.key: on and self._choose(k))
            self.group.addButton(rb)
            cl.addWidget(rb)
            cl.addWidget(label(t.description, "Hint", wrap=True))
            who = ", ".join(f"{n} ({HOST_ROLES.get(r, r).lower()})" for n, r, _b in t.hosts)
            cl.addWidget(label(f"Intervenants : {who}", "Faint", wrap=True))
            cl.addWidget(label(f"≈ {t.minutes} min par épisode", "Faint"))
            card.setStyleSheet(f"QFrame#CardFlat {{ border: 1px solid {p.border}; }}")
            card.mousePressEvent = lambda _e, rb=rb: rb.setChecked(True)
            grid.addWidget(card, i // 3, i % 3)
        lay.addLayout(grid, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Créer" if not for_episode else "Ajouter l'épisode", "check", "primary")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

    def _choose(self, key: str) -> None:
        self.selected = key

    @property
    def selected_name(self) -> str:
        return next(t.name for t in TEMPLATES if t.key == self.selected)
