"""Page Moteurs IA : installation et test des moteurs de synthèse."""

from __future__ import annotations

import time

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
    "• La vente des livres audio produits avec ce modèle n'est pas couverte par cette licence.\n"
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
        super().__init__(ctx, "Moteurs IA", "Installez gratuitement les moteurs de voix neuronales et de clonage. "
                         "Tout fonctionne sur votre ordinateur, sans abonnement.", scroll=True)
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
        for i, eng in enumerate(engines.all_engines() + engines.all_tools()):
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
            self.hw_lbl.setText(f"<b>Carte graphique détectée : {g.name}</b> ({g.vram_gb:.0f} Go). Les moteurs de "
                                "clonage utiliseront l'accélération CUDA : production rapide.")
        else:
            self.hw_icon.setPixmap(icons.pixmap("cpu", p.warning, 24))
            self.hw_lbl.setText("<b>Aucune carte graphique NVIDIA détectée.</b> Les moteurs de clonage fonctionneront "
                                "sur le processeur, nettement plus lentement (comptez plusieurs heures pour un livre). "
                                "Les voix Microsoft et Kokoro restent rapides.")
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
            self.ctx.voices_changed.emit()

        def fail(msg, tb):
            self._busy = False
            card.set_busy(False)
            self._log("ÉCHEC : " + msg)
            QMessageBox.warning(self, "Installation impossible",
                                f"{msg}\n\nVérifiez votre connexion Internet et l'espace disque disponible, puis "
                                "réessayez. Le détail figure dans le journal.")

        self._task = tasks.Task(work, pass_reporter=True, on_done=done, on_error=fail, on_message=self._log).start()

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
        eng = card.eng
        if eng.info.id == "whisper":
            self._test_whisper(card)
            return
        voice = next((v for v in self.ctx.library.all() if v.engine == eng.info.id), None)
        if voice is None and eng.info.id == "fastclone":
            voice = next((v for v in self.ctx.library.all() if v.is_clone), None)
            if voice is not None:
                voice = VoiceProfile.from_dict({**voice.to_dict(), "engine": "fastclone", "params": {}})
                voice.dir = self.ctx.library.get(voice.id).dir
        if voice is None and eng.info.id == "rvc":
            self.ctx.toast("Importez d'abord un modèle .pth (Voix & clonage → Modèle .pth) pour tester ce moteur.",
                           "warning")
            return
        if voice is None:
            if eng.info.id in ("chatterbox", "fastclone"):
                self.ctx.toast("Créez d'abord une voix clonée (Voix & clonage) pour tester ce moteur.", "warning")
                return
            builtin = eng.list_builtin_voices()
            vid = next((b.id for b in builtin if b.language in ("fr", "multi")), builtin[0].id if builtin else "")
            voice = VoiceProfile(name=f"Test {eng.info.name}", engine=eng.info.id, engine_voice=vid, language="fr")
        card.set_busy(True)
        self._log(f"Test de {eng.info.name} avec « {voice.name} »…")
        self.ctx.preview_voice(voice, on_done=lambda ok: (card.set_busy(False),
                                                          self._log("Test réussi ✔" if ok else "Test en échec")))

    def _test_whisper(self, card: EngineCard) -> None:
        from ...core import renderer
        from ...core.engines.edge import FALLBACK_VOICES

        phrase = "Bonjour, ceci est un test de relecture automatique des passages produits."
        voice = VoiceProfile(name="Test", engine="edge", engine_voice=FALLBACK_VOICES[0][0], language="fr")
        card.set_busy(True)
        self._log("Test de Whisper : génération d'une phrase puis transcription…")

        def work():
            from ...core.asr import word_error

            wav = renderer.preview(phrase, voice)
            heard = card.eng.transcribe(wav, "fr")
            return heard, word_error(phrase, heard)

        def done(res):
            heard, wer = res
            card.set_busy(False)
            self._log(f"Whisper a entendu : « {heard} » ({int((1 - wer) * 100)} % de mots reconnus) ✔")

        def fail(msg, _tb):
            card.set_busy(False)
            self._log("Test en échec : " + msg)

        self._task = tasks.run(work, on_done=done, on_error=fail)
