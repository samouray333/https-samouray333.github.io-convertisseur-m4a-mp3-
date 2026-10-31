"""Page Moteurs IA : installation et test des moteurs (analyse, transcription, voix)."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit

from ...config import settings
from ...core import engines
from ...core.engines import installer
from ...core.models import VoiceProfile
from .. import icons, tasks, theme
from ..widgets import Badge, Card, RatingDots, Spinner, button, card_title, label
from .base import Page

DEVICES = [("auto", "Matériel : automatique"), ("cuda", "Carte graphique NVIDIA"), ("cpu", "Processeur")]

XTTS_LICENSE = (
    "Le modèle XTTS-v2 est distribué par Coqui sous la licence « Coqui Public Model License » (CPML).\n\n"
    "• Utilisation gratuite à des fins personnelles et non commerciales.\n"
    "• La vente ou la monétisation des vidéos doublées avec ce modèle n'est pas couverte par cette licence.\n"
    "• Pour un usage commercial, préférez Chatterbox (licence MIT) ou les voix Microsoft.\n\n"
    "Acceptez-vous les conditions de la licence CPML (https://coqui.ai/cpml) ?"
)


class EngineCard(Card):
    def __init__(self, page: "EnginesPage", eng):
        super().__init__(margins=(20, 18, 20, 18), spacing=10)
        self.page = page
        self.eng = eng
        info = eng.info
        top = QHBoxLayout()
        ic = QLabel()
        ic.setFixedSize(46, 46)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(icons.pixmap("mic" if info.supports_cloning else ("globe" if info.online else "cpu"),
                                  info.accent, 24))
        ic.setStyleSheet(f"background: {theme.rgba(info.accent, 0.15)}; border-radius: 14px;")
        top.addWidget(ic)
        col = QHBoxLayout()
        tcol = QGridLayout()
        tcol.setVerticalSpacing(2)
        name = label(info.name, wrap=True)
        name.setStyleSheet("font-weight: 800; font-size: 12pt;")
        tcol.addWidget(name, 0, 0)
        tcol.addWidget(label(info.tagline, "Hint", wrap=True), 1, 0)
        col.addLayout(tcol, 1)
        top.addLayout(col, 1)
        self.badge = Badge("", "muted")
        top.addWidget(self.badge, 0, Qt.AlignTop)
        self.add(top)
        self.add(label(info.description, "Muted", wrap=True))

        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(6)
        g.addWidget(label("Qualité", "Hint"), 0, 0)
        g.addWidget(RatingDots(info.quality, info.accent), 0, 1)
        g.addWidget(label("Rapidité", "Hint"), 0, 2)
        g.addWidget(RatingDots(info.speed, info.accent), 0, 3)
        g.addWidget(label("Clonage", "Hint"), 1, 0)
        g.addWidget(label("Oui" if info.supports_cloning else "Non"), 1, 1)
        g.addWidget(label("Licence", "Hint"), 1, 2)
        g.addWidget(label(info.license, wrap=True), 1, 3)
        langs = ", ".join(info.languages[:12]) + ("…" if len(info.languages) > 12 else "")
        g.addWidget(label("Langues", "Hint"), 2, 0)
        g.addWidget(label(langs, wrap=True), 2, 1, 1, 3)
        spec = installer.SPECS.get(info.install_id or info.id)
        if spec:
            g.addWidget(label("Espace disque", "Hint"), 3, 0)
            g.addWidget(label(f"{spec.size_gpu} (GPU) · {spec.size_cpu} (CPU) + modèle {spec.model_size}",
                              wrap=True), 3, 1, 1, 3)
        g.setColumnStretch(3, 1)
        self.add(g)

        self.status_lbl = label("", "Hint", wrap=True)
        self.add(self.status_lbl)
        row = QHBoxLayout()
        self.device = QComboBox()
        for k, v in DEVICES:
            self.device.addItem(v, k)
        self.install_btn = button("Installer", "download", "primary")
        self.install_btn.clicked.connect(lambda: page.install(self))
        self.test_btn = button("Tester", "headphones")
        self.test_btn.clicked.connect(lambda: page.test(self))
        self.remove_btn = button("Désinstaller", "trash", "danger")
        self.remove_btn.clicked.connect(lambda: page.uninstall(self))
        self.spinner = Spinner()
        self.spinner.hide()
        if info.requires_install and info.id != "whisper":
            row.addWidget(self.device)
        row.addWidget(self.spinner)
        row.addStretch(1)
        row.addWidget(self.test_btn)
        if info.requires_install:
            row.addWidget(self.remove_btn)
            row.addWidget(self.install_btn)
        self.add(row)
        self.refresh()

    def refresh(self) -> None:
        st, msg = self.eng.status()
        kind = {engines.READY: "success", engines.NOT_INSTALLED: "warning"}.get(st, "muted")
        text = {engines.READY: "Prêt", engines.NOT_INSTALLED: "Non installé"}.get(st, "Indisponible")
        self.badge.set(text, kind)
        self.status_lbl.setText(msg)
        ready = st == engines.READY
        self.test_btn.setEnabled(ready)
        self.remove_btn.setVisible(ready and self.eng.info.requires_install)
        self.install_btn.setText("Réinstaller" if ready else "Installer")
        self.install_btn.setObjectName("" if ready else "Primary")
        self.install_btn.style().unpolish(self.install_btn)
        self.install_btn.style().polish(self.install_btn)

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()
        for b in (self.install_btn, self.remove_btn, self.test_btn, self.device):
            b.setEnabled(not busy)
        if not busy:
            self.refresh()


class EnginesPage(Page):
    name = "engines"

    def __init__(self, ctx):
        super().__init__(ctx, "Moteurs IA", "Installez gratuitement les moteurs d'analyse, de transcription et de "
                         "voix. Tout fonctionne sur votre ordinateur, sans abonnement.", scroll=True)
        self.queue: list[str] = []
        self.hw = Card(obj="CardFlat", margins=(18, 14, 18, 14))
        hl = QHBoxLayout()
        self.hw_icon = QLabel()
        self.hw_lbl = label("", wrap=True)
        hl.addWidget(self.hw_icon)
        hl.addWidget(self.hw_lbl, 1)
        self.hw.add(hl)
        self.body.addWidget(self.hw)

        self.cards: list[EngineCard] = []
        grid = QGridLayout()
        grid.setSpacing(18)
        for i, eng in enumerate(engines.all_tools() + engines.all_engines()):
            c = EngineCard(self, eng)
            self.cards.append(c)
            grid.addWidget(c, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        logc = Card()
        logc.add(card_title("Journal d'installation", "Les téléchargements peuvent prendre de quelques minutes à "
                            "une demi-heure selon votre connexion.", "list"))
        self.console = QPlainTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(220)
        self.console.setMaximumBlockCount(5000)
        logc.add(self.console)
        self.body.addWidget(logc)
        self.body.addStretch(1)
        self._busy = False

    def on_show(self) -> None:
        gpus = installer.detect_gpus()
        p = theme.CURRENT
        if gpus:
            g = gpus[0]
            self.hw_icon.setPixmap(icons.pixmap("zap", p.success, 24))
            self.hw_lbl.setText(f"<b>Carte graphique détectée : {g.name}</b> ({g.vram_gb:.0f} Go). Choisissez « Carte "
                                "graphique NVIDIA » avant d'installer un moteur pour accélérer le calcul.")
        else:
            self.hw_icon.setPixmap(icons.pixmap("cpu", p.warning, 24))
            self.hw_lbl.setText("<b>Aucune carte graphique NVIDIA détectée.</b> Tout fonctionne sur le processeur : "
                                "comptez quelques minutes de calcul par minute de vidéo avec le clonage rapide hors "
                                "ligne (séparation, transcription et voix).")
        for c in self.cards:
            c.refresh()

    def _log(self, msg: str) -> None:
        self.console.appendPlainText(time.strftime("%H:%M:%S  ") + msg)

    def install(self, card: EngineCard) -> None:
        if self._busy:
            self.ctx.toast("Une installation est déjà en cours.", "warning")
            return
        eid = card.eng.info.install_id or card.eng.info.id
        if eid == "xtts" and not settings().get("xtts_tos_accepted"):
            r = QMessageBox.question(self, "Licence du modèle XTTS-v2", XTTS_LICENSE)
            if r != QMessageBox.Yes:
                return
            settings().set("xtts_tos_accepted", True)
        card.eng.shutdown()
        self._busy = True
        card.set_busy(True)
        device = card.device.currentData()
        self._log(f"=== Installation de {card.eng.info.name} ===")

        def work(task):
            return installer.install_engine(eid, device, log_cb=task.say, cancel=task.cancel_event)

        def done(info):
            self._busy = False
            card.set_busy(False)
            for c in self.cards:
                c.refresh()
            self.ctx.toast(f"{card.eng.info.name} est installé ✔", "success", 5000)
            self.ctx.engines_changed.emit()
            self._next_in_queue()

        def fail(msg, tb):
            self._busy = False
            card.set_busy(False)
            self.queue.clear()
            self._log("ÉCHEC : " + msg)
            QMessageBox.warning(self, "Installation impossible",
                                f"{msg}\n\nVérifiez votre connexion Internet et l'espace disque disponible, puis "
                                "réessayez. Le détail figure dans le journal.")

        self._task = tasks.Task(work, pass_reporter=True, on_done=done, on_error=fail, on_message=self._log).start()

    def install_many(self, ids: list[str]) -> None:
        """Installe à la suite les moteurs manquants (bouton « Installer tout ce qu'il faut »)."""
        todo = [i for i in ids if not installer.is_installed(i)]
        if not todo:
            self.ctx.toast("Tout est déjà installé ✔", "success")
            return
        self.queue = [i for i in todo if i not in self.queue] + self.queue
        names = ", ".join(c.eng.info.name.split(" — ")[0] for c in map(self._card_for, todo) if c is not None)
        self._log(f"Installation de : {names}")
        if not self._busy:
            self._next_in_queue()

    def _card_for(self, eid: str):
        return next((c for c in self.cards if c.eng.info.id == eid), None)

    def _next_in_queue(self) -> None:
        while self.queue:
            eid = self.queue.pop(0)
            card = self._card_for(eid)
            if card is not None and not installer.is_installed(eid):
                self.install(card)
                return

    def uninstall(self, card: EngineCard) -> None:
        if QMessageBox.question(self, "Désinstaller", f"Désinstaller {card.eng.info.name} et supprimer ses modèles ?"
                                ) != QMessageBox.Yes:
            return
        eid = card.eng.info.install_id or card.eng.info.id
        for c in self.cards:
            if (c.eng.info.install_id or c.eng.info.id) == eid:
                c.eng.shutdown()
        installer.uninstall_engine(eid)
        for c in self.cards:
            c.refresh()
        self.ctx.engines_changed.emit()
        self.ctx.toast("Moteur désinstallé.", "info")

    def test(self, card: EngineCard) -> None:
        from ...core import audio, dubvoice

        eng = card.eng
        eid = eng.info.id
        if eid in ("whisper", "analysis", "ocr"):
            self._test_tool(card)
            return
        if eid == "rvc":
            self.ctx.toast("Choisissez un modèle .pth pour une personne (page Personnes) puis faites un essai.", "info")
            return
        pr = self.ctx.project
        ref = None
        if pr is not None:
            ref = next((r for r in (dubvoice.reference_path(pr, p) for p in pr.people) if r is not None), None)
        cloning = eid in ("xtts", "chatterbox", "fastclone")
        if cloning and ref is None:
            self.ctx.toast("Ouvrez d'abord un projet dont les voix des personnes sont prêtes : l'essai utilise un "
                           "extrait de voix.", "warning", 6000)
            return
        base = {"fastclone": "kokoro:ff_siwis", "edge": "fr-FR-DeniseNeural", "kokoro": "ff_siwis"}.get(eid, "")
        if eid == "sapi":
            voices = eng.list_builtin_voices()
            base = next((v.id for v in voices if v.language == "fr"), voices[0].id if voices else "")
        voice = VoiceProfile(name="Essai", engine=eid, kind="clone" if cloning else "builtin", engine_voice=base,
                             references=[str(ref)] if cloning else [])
        card.set_busy(True)
        self._log(f"Essai de {eng.info.name}…")

        def work():
            import tempfile

            from ... import paths

            data, sr = dubvoice.synthesize(voice, settings().get("preview_sentence"))
            out = Path(tempfile.mkdtemp(dir=paths.temp_dir())) / "essai.wav"
            return audio.write_audio(out, data, sr, subtype="PCM_16")

        def done(path):
            card.set_busy(False)
            self._log("Essai réussi ✔")
            self.ctx.play(path, f"Essai — {eng.info.name}")

        def fail(msg, _tb):
            card.set_busy(False)
            self._log("Essai en échec : " + msg)

        self._task = tasks.run(work, on_done=done, on_error=fail)

    def _test_tool(self, card: EngineCard) -> None:
        import numpy as np

        from ...core import audio

        card.set_busy(True)
        self._log(f"Essai de {card.eng.info.name}…")

        def work():
            import tempfile

            from ... import paths

            d = Path(tempfile.mkdtemp(dir=paths.temp_dir()))
            sr = 16000
            t = np.arange(sr * 3) / sr
            sig = (0.2 * np.sin(2 * np.pi * 150 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
            wav = audio.write_audio(d / "essai.wav", sig, sr, subtype="PCM_16")
            if card.eng.info.id == "ocr":
                from PySide6.QtCore import Qt
                from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen

                img = QImage(520, 64, QImage.Format_Grayscale8)
                img.fill(QColor(70, 70, 70))
                painter = QPainter(img)
                painter.setRenderHint(QPainter.Antialiasing)
                path = QPainterPath()
                font = QFont("Arial", 26)
                font.setBold(True)
                path.addText(16, 44, font, "Let's go, Doublys!")
                painter.strokePath(path, QPen(Qt.black, 5))
                painter.fillPath(path, Qt.white)
                painter.end()
                ptr = img.constBits()
                arr = np.frombuffer(ptr, dtype=np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width()]
                np.savez(d / "essai.npz", ligne=arr.copy())
                text, conf = card.eng.ocr_lines([d / "essai.npz"]).get("ligne", ["", 0.0])
                return f"texte lu « {text} » (confiance {conf:.0%})"
            if card.eng.info.id == "whisper":
                card.eng.transcribe_words(wav, "en", settings().get("asr_model", "small"))
                return "modèle chargé, transcription possible"
            fr = card.eng.translate(["Hello, how are you?"], "Helsinki-NLP/opus-mt-tc-big-en-fr")
            emb = card.eng.embed(wav, [(0.0, 3.0)])
            return f"traduction « {fr[0]} », empreinte de {len(emb[0])} valeurs"

        def done(msg):
            card.set_busy(False)
            self._log(f"Essai réussi ✔ ({msg})")

        def fail(msg, _tb):
            card.set_busy(False)
            self._log("Essai en échec : " + msg)

        self._task = tasks.run(work, on_done=done, on_error=fail)
