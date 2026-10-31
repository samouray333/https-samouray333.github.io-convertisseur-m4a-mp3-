"""Guide de démarrage (premier lancement, puis menu ou F1)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from .. import icons, theme
from ..widgets import button, label

STEPS = [
    ("cpu", "1. Installer les moteurs (une seule fois)",
     "Sur l'accueil, cliquez sur « Installer tout ce qu'il faut ». Doublys télécharge gratuitement la séparation des "
     "voix, la transcription, la traduction et les voix (environ 6 Go, 20 à 40 minutes). Ensuite tout fonctionne "
     "sans Internet."),
    ("film", "2. Glisser une vidéo",
     "Glissez la vidéo sur l'accueil (plusieurs vidéos : elles partent dans la file d'attente). Elle reste à sa place ; "
     "le projet est créé dans Documents\\Doublys. La langue parlée est détectée toute seule ; s'il y a des sous-titres "
     "(piste, fichier .srt à côté, ou sous-titres incrustés dans l'image), leur texte est utilisé."),
    ("wand", "3. Créer la VF automatiquement",
     "Page Doublage : un clic. Le temps estimé s'affiche ; l'ordinateur ne se met pas en veille et vous pouvez arrêter "
     "puis reprendre à tout moment sans rien perdre."),
    ("alert", "4. Vérifier ce qui est signalé",
     "Page Contrôle : passages où quelqu'un parle sans VF, voix en échec, sous-titres mal lus. Sur la page Doublage, "
     "cochez « Seulement les répliques à vérifier » : mots mal compris, traduction douteuse, personne incertaine, "
     "réplique trop longue. Double-cliquez sur le français pour le corriger, faites glisser une réplique sur la forme "
     "d'onde pour la recaler, double-cliquez sur son numéro pour la voir avec l'image. Ctrl+Z annule."),
    ("users", "5. Les personnes et les séries",
     "Page Personnes : renommez P1, P2… avec le nom des personnages, choisissez leur voix, faites un essai. Pour une "
     "série, enregistrez les personnages : dans les épisodes suivants, ils sont reconnus tout seuls."),
    ("package", "6. Exporter",
     "La vidéo doublée (MP4 ou MKV, image non réencodée) est créée à côté du projet, avec les sous-titres si vous le "
     "souhaitez. Ne doublez que des vidéos dont vous avez les droits, et ne clonez que des voix avec accord."),
]


class GuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bien démarrer avec Doublys")
        self.resize(640, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(14)
        self.stack = QStackedWidget()
        for ic, title, text in STEPS:
            w = QWidget()
            v = QVBoxLayout(w)
            v.setSpacing(12)
            top = QHBoxLayout()
            pic = QLabel()
            pic.setPixmap(icons.pixmap(ic, theme.CURRENT.accent, 44))
            top.addWidget(pic)
            t = label(title)
            t.setStyleSheet("font-size: 15pt; font-weight: 800;")
            top.addWidget(t, 1)
            v.addLayout(top)
            body = label(text, wrap=True)
            body.setStyleSheet("font-size: 11pt;")
            v.addWidget(body)
            v.addStretch(1)
            self.stack.addWidget(w)
        lay.addWidget(self.stack, 1)
        row = QHBoxLayout()
        self.pos = label("", "Hint")
        row.addWidget(self.pos)
        row.addStretch(1)
        self.prev = button("Précédent", "chevron-left")
        self.prev.clicked.connect(lambda: self._go(-1))
        self.next = button("Suivant", "chevron-right", "primary")
        self.next.clicked.connect(lambda: self._go(1))
        row.addWidget(self.prev)
        row.addWidget(self.next)
        lay.addLayout(row)
        self._go(0)

    def _go(self, delta: int) -> None:
        i = self.stack.currentIndex() + delta
        if i >= self.stack.count():
            self.accept()
            return
        i = max(0, i)
        self.stack.setCurrentIndex(i)
        self.pos.setText(f"{i + 1} / {self.stack.count()}")
        self.prev.setEnabled(i > 0)
        self.next.setText("C'est parti !" if i == self.stack.count() - 1 else "Suivant")
        self.next.setFocus(Qt.OtherFocusReason)
