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

LICENSES = """Doublys — Echo Matras. Doublage vidéo anglais → français.
Construit sur le moteur d'AudioLivre Studio.

Composants intégrés :
• Qt for Python / PySide6 — LGPL v3
• FFmpeg — LGPL (version « lgpl » de BtbN : sans composant GPL)
• NumPy — BSD · soundfile / libsndfile — BSD / LGPL · python-soxr — LGPL · sounddevice / PortAudio — MIT
• num2words — LGPL · edge-tts — LGPL v3 · uv — MIT / Apache 2.0

Moteurs installés à la demande :
• Demucs (htdemucs, séparation des voix) — MIT
• faster-whisper — MIT ; modèles Whisper (OpenAI) — MIT
• speechbrain + modèle ECAPA spkrec-ecapa-voxceleb — Apache 2.0
• Opus-MT (Helsinki-NLP, opus-mt-tc-big-en-fr et opus-mt-en-fr) — CC-BY 4.0 : la mention
  « traduction Opus-MT, Helsinki-NLP » est requise si vous publiez les traductions
• transformers, sentencepiece — Apache 2.0
• Kokoro-82M — Apache 2.0
• Chatterbox (Resemble AI) — MIT (le son produit contient un filigrane inaudible « Perth »)
• XTTS-v2 (Coqui) — code MPL 2.0, modèle sous Coqui Public Model License (usage NON commercial)
• RVC, ContentVec, RMVPE — MIT ; faiss — MIT
• PyTorch — BSD

Services en ligne facultatifs : voix Microsoft (conditions de Microsoft Edge), DeepSeek (traduction,
payant à l'usage, avec votre clé).

Utilisation responsable : ne clonez une voix qu'avec l'accord de la personne concernée, et respectez
les droits d'auteur des vidéos que vous doublez et diffusez.
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("À propos de Doublys")
        self.resize(660, 620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 22)
        lay.setSpacing(12)
        top = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_logo(160).scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        top.addWidget(logo)
        col = QVBoxLayout()
        t = label(f"Doublys {__version__}")
        t.setStyleSheet("font-size: 18pt; font-weight: 800;")
        col.addWidget(t)
        col.addWidget(label("Echo Matras · vos vidéos en version française.", "Muted"))
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
