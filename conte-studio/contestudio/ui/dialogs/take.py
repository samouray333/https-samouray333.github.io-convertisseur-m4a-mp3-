"""Enregistrer (ou importer) une réplique dite au micro : elle remplace la voix de synthèse pour ce passage."""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QVBoxLayout

from ...core import audio
from ...core.sounds import slug
from .. import theme
from ..widgets import Card, IconButton, LevelMeter, button, card_title, label
from .clone_wizard import Recorder


class TakeDialog(QDialog):
    def __init__(self, ctx, speaker: str, text: str, folder: Path, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.folder = folder
        self.speaker = speaker
        self.saved_name: str | None = None
        self._tmp = Path(tempfile.mkdtemp(prefix="prise-"))
        self._file: Path | None = None
        self.setWindowTitle("Enregistrer au micro")
        self.resize(760, 460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        who = f" — {speaker}" if speaker else ""
        lay.addWidget(card_title(f"Votre vraie voix{who}",
                                 "Lisez la réplique au micro : l'enregistrement remplace la voix de synthèse pour ce "
                                 "passage (son niveau est ajusté automatiquement). Idéal pour que papa ou maman "
                                 "joue un personnage.", "mic"))
        card = Card(obj="CardFlat")
        self.text_lbl = label(text or "(réplique sans texte : dites ce que vous voulez)", wrap=True)
        self.text_lbl.setStyleSheet("font-size: 14pt; font-weight: 600;")
        card.add(self.text_lbl)
        lay.addWidget(card)

        self.recorder = Recorder()
        self.recorder.error.connect(lambda m: self.ctx.toast(m, "error", 7000))
        dr = QHBoxLayout()
        dr.addWidget(label("Micro", "Muted"))
        self.devices = QComboBox()
        self.devices.addItem("Micro par défaut", None)
        for i, name in Recorder.devices():
            self.devices.addItem(name, i)
        dr.addWidget(self.devices, 1)
        lay.addLayout(dr)

        rr = QHBoxLayout()
        self.rec_btn = IconButton("record", "Enregistrer / arrêter", 56, 26, color=theme.CURRENT.danger)
        self.rec_btn.clicked.connect(self.toggle)
        rr.addWidget(self.rec_btn)
        col = QVBoxLayout()
        self.meter = LevelMeter()
        self.recorder.level.connect(self.meter.set_level)
        self.status = label("Cliquez sur le bouton rouge, lisez la réplique, puis cliquez à nouveau.", "Hint")
        col.addWidget(self.meter)
        col.addWidget(self.status)
        rr.addLayout(col, 1)
        self.play_btn = button("Écouter", "play")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(lambda: self._file and self.ctx.play(self._file, "Prise au micro"))
        rr.addWidget(self.play_btn)
        lay.addLayout(rr)
        imp = button("Importer un fichier audio…", "folder", tooltip="Une réplique déjà enregistrée (WAV, MP3, M4A…)")
        imp.clicked.connect(self._import)
        lay.addWidget(imp)
        lay.addWidget(QLabel())
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        self.ok = button("Utiliser cette prise", "check", "primary")
        self.ok.setEnabled(False)
        self.ok.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def toggle(self) -> None:
        if self.recorder.recording:
            self._timer.stop()
            data = self.recorder.stop()
            self.rec_btn.set_icon_name("record", theme.CURRENT.danger)
            if data.size < self.recorder.sr * 0.3:
                self.status.setText("Enregistrement trop court : recommencez.")
                return
            f = self._tmp / "prise.wav"
            audio.write_audio(f, data.astype(np.float32), self.recorder.sr, subtype="PCM_16")
            self._set_file(f, len(data) / self.recorder.sr)
        elif self.recorder.start(self.devices.currentData()):
            self.rec_btn.set_icon_name("stop", theme.CURRENT.danger)
            self._timer.start(200)

    def _tick(self) -> None:
        self.status.setText(f"● Enregistrement… {time.time() - self.recorder.started_at:0.0f} s")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un enregistrement", "",
                                              "Audio (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac)")
        if path:
            self._set_file(Path(path), audio.duration_of(path))

    def _set_file(self, f: Path, seconds: float) -> None:
        self._file = f
        st = audio.analyze_file(f)
        hint = " — un peu faible, rapprochez-vous du micro" if st.rms_db < -40 else ""
        hint = " — saturé, éloignez-vous un peu" if st.peak_db > -0.3 else hint
        self.status.setText(f"Prise de {seconds:.1f} s{hint}. Écoutez-la, puis utilisez-la ou recommencez.")
        self.play_btn.setEnabled(True)
        self.ok.setEnabled(True)

    def _save(self) -> None:
        if self._file is None:
            return
        base = slug(self.speaker or "prise") or "prise"
        name = f"{base}-{time.strftime('%Y%m%d-%H%M%S')}{self._file.suffix.lower()}"
        self.folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._file, self.folder / name)
        self.saved_name = name
        self.accept()

    def done(self, r):
        if self.recorder.recording:
            self.recorder.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().done(r)
