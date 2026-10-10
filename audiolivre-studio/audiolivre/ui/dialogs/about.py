"""Boîte « À propos »."""

from __future__ import annotations

import platform
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout

from ... import __version__, paths
from ...core import ffmpeg
from .. import icons
from ..widgets import button, label

LICENSES = """AudioLivre Studio — logiciel gratuit.

Composants utilisés :
• Qt for Python / PySide6 — LGPL v3
• FFmpeg — LGPL/GPL (binaires fournis par gyan.dev / BtbN)
• PyMuPDF — AGPL v3
• python-docx — MIT · EbookLib — AGPL v3 · BeautifulSoup — MIT · striprtf — BSD
• NumPy — BSD · soundfile / libsndfile — BSD / LGPL · python-soxr — LGPL · sounddevice / PortAudio — MIT
• mutagen — GPL v2 · num2words — LGPL · edge-tts — LGPL v3 · uv — MIT / Apache 2.0

Moteurs installés à la demande :
• XTTS-v2 (Coqui) — code MPL 2.0, modèle sous Coqui Public Model License (non commercial)
• Chatterbox (Resemble AI) — MIT (le son produit contient un filigrane inaudible « Perth »)
• RVC (Retrieval-based Voice Conversion), ContentVec, RMVPE — MIT ; faiss — MIT
• faster-whisper — MIT ; Whisper (OpenAI) — MIT
• Kokoro-82M — Apache 2.0
• PyTorch — BSD

Voix Microsoft : service en ligne de Microsoft Edge, soumis à ses conditions d'utilisation.

Utilisation responsable : ne clonez une voix qu'avec l'accord de la personne concernée et
respectez les droits d'auteur des textes que vous transformez en livres audio.
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("À propos d'AudioLivre Studio")
        self.resize(640, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 22)
        lay.setSpacing(12)
        top = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_logo(160).scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        top.addWidget(logo)
        col = QVBoxLayout()
        t = label(f"AudioLivre Studio {__version__}")
        t.setStyleSheet("font-size: 18pt; font-weight: 800;")
        col.addWidget(t)
        col.addWidget(label("Transformez vos documents en livres audio professionnels.", "Muted"))
        top.addLayout(col, 1)
        lay.addLayout(top)
        info = (f"Python {sys.version.split()[0]} · {platform.system()} {platform.release()} · "
                f"{ffmpeg.version()}\nDonnées : {paths.data_dir()}")
        lay.addWidget(label(info, "Hint", wrap=True, selectable=True))
        txt = QPlainTextEdit(LICENSES)
        txt.setReadOnly(True)
        lay.addWidget(txt, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = button("Fermer", kind="primary")
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addLayout(row)
