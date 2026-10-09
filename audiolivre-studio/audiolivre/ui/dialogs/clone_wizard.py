"""Assistant de clonage de voix en quatre étapes."""

from __future__ import annotations

import random
import tempfile
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit,
                               QPlainTextEdit, QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from ... import paths
from ...core import audio, engines
from ...core.models import VoiceProfile
from .. import icons, tasks, theme
from ..pages.voices import COLORS, LANGS
from ..widgets import (Card, DropZone, IconButton, LevelMeter, ParamSlider, Spinner, ToggleSwitch, WaveformView,
                       button, card_title, label)

AUDIO_FILTER = "Audio et vidéo (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac *.wma *.mp4 *.mkv *.webm *.mov)"

READING_SCRIPT = (
    "Le vieux phare se dressait au bout de la jetée, battu par les vents du large. Chaque soir, Mathilde "
    "gravissait les cent douze marches pour allumer la grande lanterne. « Crois-tu qu'ils reviendront ? » "
    "demanda-t-elle doucement à son frère. Personne ne répondit. Pourtant, au loin, une lumière vacillante "
    "perçait déjà le brouillard, et son cœur se mit à battre plus vite. Elle sourit : l'hiver serait moins long "
    "cette année."
)


class StepIndicator(QWidget):
    def __init__(self, steps: list[str]):
        super().__init__()
        self.steps = steps
        self.current = 0
        self.setFixedHeight(56)

    def set_current(self, i: int) -> None:
        self.current = i
        self.update()

    def paintEvent(self, e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        n = len(self.steps)
        w = self.width() / n
        f = QFont(self.font())
        for i, name in enumerate(self.steps):
            cx = w * i + w / 2
            if i < n - 1:
                painter.setPen(QPen(QColor(p.accent if i < self.current else p.surface3), 3))
                painter.drawLine(int(cx + 18), 16, int(cx + w - 18), 16)
            done, active = i < self.current, i == self.current
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(p.accent if (done or active) else p.surface3))
            painter.drawEllipse(QRectF(cx - 14, 2, 28, 28))
            painter.setPen(QColor("#FFFFFF" if (done or active) else p.muted))
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(QRectF(cx - 14, 2, 28, 28), Qt.AlignCenter, "✓" if done else str(i + 1))
            f.setBold(active)
            painter.setFont(f)
            painter.setPen(QColor(p.text if active else p.muted))
            painter.drawText(QRectF(cx - w / 2, 34, w, 20), Qt.AlignCenter, name)
        painter.end()


class Recorder(QObject):
    level = Signal(float)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self.sr = 44100
        self._last_db = -90.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.level.emit(self._last_db))
        self.started_at = 0.0

    @staticmethod
    def devices() -> list[tuple[int, str]]:
        try:
            import sounddevice as sd

            out = []
            for i, d in enumerate(sd.query_devices()):
                if d.get("max_input_channels", 0) > 0:
                    out.append((i, d["name"]))
            return out
        except Exception:
            return []

    def start(self, device: int | None) -> bool:
        try:
            import sounddevice as sd

            self._chunks = []
            self._stream = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32", device=device,
                                          callback=self._cb)
            self._stream.start()
            self.started_at = time.time()
            self._timer.start(60)
            return True
        except Exception as exc:
            self.error.emit(f"Impossible d'ouvrir le micro : {exc}")
            return False

    def _cb(self, indata, frames, t, status):
        block = indata[:, 0].copy()
        self._chunks.append(block)
        rms = float(np.sqrt(np.mean(block.astype(np.float64) ** 2))) if block.size else 0.0
        self._last_db = audio.lin_to_db(rms)

    def stop(self) -> np.ndarray:
        self._timer.stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.level.emit(-90.0)
        return np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)

    @property
    def recording(self) -> bool:
        return self._stream is not None


class CloneWizard(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.voice: VoiceProfile | None = None
        self._saved_voice = False
        self.data: np.ndarray | None = None
        self.sr = 44100
        self.source_file: Path | None = None
        self._tmpdir = Path(tempfile.mkdtemp(prefix="clone-", dir=paths.temp_dir()))
        self.setWindowTitle("Cloner une voix")
        self.resize(1000, 780)
        self.setMinimumSize(900, 680)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        lay.addWidget(card_title("Cloner une voix", "Quelques secondes d'enregistrement suffisent. Utilisez "
                                 "uniquement votre voix ou celle d'une personne qui vous a donné son accord.", "mic"))
        self.steps = StepIndicator(["Enregistrement", "Préparation", "Identité", "Essai"])
        lay.addWidget(self.steps)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        for page in (self._page_source(), self._page_prepare(), self._page_identity(), self._page_test()):
            self.stack.addWidget(self._scrollable(page))

        nav = QHBoxLayout()
        self.cancel_btn = button("Annuler", kind="ghost")
        self.cancel_btn.clicked.connect(self.reject)
        self.back_btn = button("Retour", "chevron-left")
        self.back_btn.clicked.connect(self._back)
        self.next_btn = button("Continuer", "chevron-right", "primary")
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.cancel_btn)
        nav.addStretch(1)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        lay.addLayout(nav)
        self._go(0)

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(page)
        return area

    # ================================================================== étape 1
    def _page_source(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        left = Card()
        left.add(card_title("Importer un enregistrement", "Fichier audio ou vidéo : interview, podcast, "
                            "mémo vocal… La meilleure portion sera choisie automatiquement.", "upload"))
        drop = DropZone("Déposez un fichier audio", "WAV, MP3, M4A, FLAC, OGG, vidéo…", "wave", 170)
        drop.files_dropped.connect(lambda f: self._load_file(f[0]))
        drop.clicked.connect(self._browse)
        left.add(drop)
        tips = label("Conseils pour un clone réussi :\n• 10 à 30 secondes de parole continue\n• une seule voix, sans "
                     "musique ni bruit de fond\n• un ton naturel, comme pour lire un livre\n• un bon micro près de "
                     "la bouche, pièce calme", "Hint", wrap=True)
        left.add(tips)
        left.add(None)
        lay.addWidget(left, 1)

        right = Card()
        right.add(card_title("Enregistrer avec le micro", "Lisez le texte ci-dessous d'une voix posée.", "mic"))
        self.devices = QComboBox()
        self.devices.addItem("Micro par défaut", None)
        for i, name in Recorder.devices():
            self.devices.addItem(name, i)
        right.add(self.devices)
        script = QPlainTextEdit(READING_SCRIPT)
        script.setReadOnly(True)
        script.setStyleSheet("font-size: 11pt;")
        script.setMinimumHeight(140)
        right.add(script)
        self.meter = LevelMeter()
        right.add(self.meter)
        row = QHBoxLayout()
        self.rec_btn = IconButton("record", "Démarrer / arrêter l'enregistrement", 56, 26, color=theme.CURRENT.danger)
        self.rec_btn.setStyleSheet(f"QToolButton {{ border-radius: 28px; background: "
                                   f"{theme.rgba(theme.CURRENT.danger, 0.14)}; }}")
        self.rec_btn.clicked.connect(self._toggle_record)
        self.rec_time = label("Prêt à enregistrer", "Muted")
        row.addWidget(self.rec_btn)
        row.addWidget(self.rec_time, 1)
        right.add(row)
        lay.addWidget(right, 1)

        self.recorder = Recorder()
        self.recorder.level.connect(self.meter.set_level)
        self.recorder.error.connect(lambda m: self.ctx.toast(m, "error", 6000))
        self._rec_timer = QTimer(self)
        self._rec_timer.timeout.connect(self._rec_tick)
        self.source_status = label("", "Hint")
        return w

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un enregistrement", "", AUDIO_FILTER)
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        self.ctx.toast("Analyse de l'enregistrement…", "info", 1800)

        def work():
            data, sr = audio.read_audio(path, target_sr=44100)
            return data, sr

        def done(res):
            self.data, self.sr = res
            self.source_file = Path(path)
            if len(self.data) < self.sr * 3:
                self.ctx.toast("Enregistrement trop court (3 secondes minimum).", "warning")
                return
            self._go(1)

        self._task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(f"Lecture impossible : {m}",
                                                                                           "error"))

    def _toggle_record(self) -> None:
        if self.recorder.recording:
            data = self.recorder.stop()
            self._rec_timer.stop()
            self.rec_btn.set_icon_name("record", theme.CURRENT.danger)
            if len(data) < self.recorder.sr * 3:
                self.rec_time.setText("Trop court : enregistrez au moins 6 secondes.")
                return
            f = self._tmpdir / "enregistrement.wav"
            audio.write_audio(f, data, self.recorder.sr, subtype="PCM_16")
            self.data, self.sr = data, self.recorder.sr
            self.source_file = f
            self.rec_time.setText(f"Enregistré : {len(data) / self.sr:.1f} s")
            self._go(1)
        else:
            dev = self.devices.currentData()
            if self.recorder.start(dev):
                self.rec_btn.set_icon_name("stop", theme.CURRENT.danger)
                self._rec_timer.start(200)

    def _rec_tick(self) -> None:
        t = time.time() - self.recorder.started_at
        hint = "continuez…" if t < 10 else ("parfait !" if t < 30 else "vous pouvez arrêter")
        self.rec_time.setText(f"● Enregistrement {t:0.0f} s — {hint}")

    # ================================================================== étape 2
    def _page_prepare(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        c = Card()
        c.add(card_title("Choisissez l'extrait de référence",
                         "La portion surlignée sera utilisée pour cloner la voix. Faites glisser sur la forme d'onde "
                         "pour la modifier ; cliquez pour écouter à partir d'un point.", "scissors"))
        self.wave = WaveformView(140)
        self.wave.selection_changed.connect(self._sel_changed)
        self.wave.seek_requested.connect(self._play_from)
        c.add(self.wave)
        row = QHBoxLayout()
        auto = button("Sélection automatique", "sparkles")
        auto.clicked.connect(self._auto_select)
        play = button("Écouter la sélection", "play", "primary")
        play.clicked.connect(self._play_selection)
        self.len_slider = QSlider(Qt.Horizontal)
        self.len_slider.setRange(6, 30)
        self.len_slider.setValue(18)
        self.len_slider.setFixedWidth(160)
        self.len_slider.valueChanged.connect(lambda v: (self.len_lbl.setText(f"Durée cible : {v} s"),
                                                        self._auto_select()))
        self.len_lbl = label("Durée cible : 18 s", "Muted")
        row.addWidget(auto)
        row.addWidget(play)
        row.addStretch(1)
        row.addWidget(self.len_lbl)
        row.addWidget(self.len_slider)
        c.add(row)
        self.sel_info = label("", "Muted")
        c.add(self.sel_info)
        lay.addWidget(c)

        q = Card()
        q.add(card_title("Analyse de qualité", "", "shield"))
        self.quality = QGridLayout()
        self.quality.setHorizontalSpacing(24)
        self.quality.setVerticalSpacing(6)
        q.add(self.quality)
        self.denoise = ToggleSwitch("Réduire le bruit de fond (recommandé pour les enregistrements au téléphone)")
        q.add(self.denoise)
        lay.addWidget(q)
        lay.addStretch(1)
        return w

    def _analyze(self) -> None:
        while self.quality.count():
            it = self.quality.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if self.data is None:
            return
        db = audio.frame_rms_db(self.data, self.sr, 50)
        peak = audio.lin_to_db(float(np.max(np.abs(self.data))) if self.data.size else 0)
        noise = float(np.percentile(db, 10))
        speech = float(np.percentile(db, 90))
        snr = speech - noise
        dur = len(self.data) / self.sr
        checks = [
            (dur >= 6, f"Durée totale : {dur:.1f} s" + ("" if dur >= 6 else " — trop court, 6 s minimum")),
            (peak < -0.5, f"Niveau maximal : {peak:.1f} dB" + ("" if peak < -0.5 else " — saturation détectée")),
            (snr >= 25, f"Rapport signal/bruit : {snr:.0f} dB" + ("" if snr >= 25 else
                                                                   " — bruit de fond élevé, activez la réduction")),
            (speech > -38, f"Volume de la voix : {speech:.0f} dB" + ("" if speech > -38 else
                                                                      " — voix faible, rapprochez le micro")),
        ]
        p = theme.CURRENT
        for i, (ok, text) in enumerate(checks):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            ic = label()
            ic.setPixmap(icons.pixmap("check" if ok else "alert", p.success if ok else p.warning, 16))
            row.addWidget(ic)
            row.addWidget(label(text, wrap=True), 1)
            holder = QWidget()
            holder.setLayout(row)
            self.quality.addWidget(holder, i // 2, i % 2)
        if snr < 25:
            self.denoise.setChecked(True)

    def _auto_select(self) -> None:
        if self.data is None:
            return
        s, e = audio.best_speech_window(self.data, self.sr, float(self.len_slider.value()))
        self.wave.set_selection(s / self.sr, e / self.sr)

    def _sel_changed(self, start: float, end: float) -> None:
        d = end - start
        tip = "idéal" if 10 <= d <= 30 else ("un peu court" if d < 10 else "long : 30 s max. conseillées")
        self.sel_info.setText(f"Extrait sélectionné : {start:.1f} s → {end:.1f} s ({d:.1f} s, {tip})")

    def _play_selection(self) -> None:
        sel = self.wave.selection()
        if self.source_file is None or sel is None:
            return
        self.ctx.play(self._source_wav(), "Extrait de référence", sel[0], sel[1])

    def _play_from(self, t: float) -> None:
        if self.source_file is not None:
            self.ctx.play(self._source_wav(), "Enregistrement source", t)

    def _source_wav(self) -> Path:
        f = self._tmpdir / "source.wav"
        if not f.exists() and self.data is not None:
            audio.write_audio(f, self.data, self.sr, subtype="PCM_16")
        return f

    # ================================================================== étape 3
    def _page_identity(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        c = Card()
        c.add(card_title("Identité de la voix", "", "user"))
        g = QGridLayout()
        g.setVerticalSpacing(10)
        g.setHorizontalSpacing(12)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Ex. : Ma voix, Grand-père Louis…")
        self.lang = QComboBox()
        for code, n in LANGS[:-1]:
            self.lang.addItem(n, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.ctx.project.metadata.language or "fr")))
        self.gender = QComboBox()
        for code, n in (("", "Non précisé"), ("F", "Féminine"), ("M", "Masculine")):
            self.gender.addItem(n, code)
        self.desc = QLineEdit()
        self.desc.setPlaceholderText("Description (facultatif) : chaleureuse, posée…")
        g.addWidget(label("Nom", "Muted"), 0, 0)
        g.addWidget(self.name, 0, 1)
        g.addWidget(label("Langue", "Muted"), 1, 0)
        g.addWidget(self.lang, 1, 1)
        g.addWidget(label("Timbre", "Muted"), 2, 0)
        g.addWidget(self.gender, 2, 1)
        g.addWidget(label("Description", "Muted"), 3, 0)
        g.addWidget(self.desc, 3, 1)
        c.add(g)
        self.consent = QCheckBox("Je certifie qu'il s'agit de ma voix, ou que la personne enregistrée m'a donné son "
                                 "accord pour cloner sa voix et l'utiliser dans ce livre audio.")
        self.consent.setStyleSheet("QCheckBox { font-weight: 600; }")
        c.add(None)
        c.add(self.consent)
        lay.addWidget(c, 1)

        e = Card()
        e.add(card_title("Moteur de clonage", "Vous pourrez en changer à tout moment.", "cpu"))
        self.engine_cards: dict[str, QFrame] = {}
        self.engine_choice = "xtts"
        from ...core.engines import installer

        has_gpu = bool(installer.detect_gpus())
        for eid in engines.CLONING_ENGINES:
            eng = engines.get_engine(eid)
            card = QFrame()
            card.setObjectName("CardHover")
            card.setCursor(Qt.PointingHandCursor)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(4)
            t = label(eng.info.name)
            t.setStyleSheet("font-weight: 700;")
            cl.addWidget(t)
            cl.addWidget(label(eng.info.tagline, "Hint"))
            st, msg = eng.status()
            sl = label(("✓ " if st == engines.READY else "⚠ ") + msg, "Hint", wrap=True)
            sl.setStyleSheet(f"color: {theme.CURRENT.success if st == engines.READY else theme.CURRENT.warning};")
            cl.addWidget(sl)
            if not has_gpu:
                speed = {"xtts": ("✓ Ressemblance la plus fidèle : environ 3 min de calcul par minute de livre", True),
                         "fastclone": ("✓ Le plus rapide : environ 1 min de calcul par minute de livre (Internet requis)",
                                       True),
                         "chatterbox": ("Très lent sans carte NVIDIA : environ 20 min de calcul par minute", False)}
                text, good = speed[eid]
                hl = label(text, "Hint", wrap=True)
                hl.setStyleSheet(f"color: {theme.CURRENT.success if good else theme.CURRENT.warning};")
                cl.addWidget(hl)
            card.mouseReleaseEvent = lambda _e, eid=eid: self._choose_engine(eid)
            self.engine_cards[eid] = card
            e.add(card)
        installed = [eid for eid in engines.CLONING_ENGINES if engines.get_engine(eid).is_ready()]
        if not has_gpu and "chatterbox" in installed and len(installed) > 1:
            installed.remove("chatterbox")
        e.add(label("Les moteurs de clonage s'installent une seule fois depuis la page « Moteurs IA » "
                    "(téléchargement gratuit) et fonctionnent ensuite sur votre ordinateur.", "Hint", wrap=True))
        e.add(None)
        lay.addWidget(e, 1)
        self._choose_engine(installed[0] if installed else "xtts")
        return w

    def _choose_engine(self, eid: str) -> None:
        self.engine_choice = eid
        p = theme.CURRENT
        for k, card in self.engine_cards.items():
            card.setStyleSheet(f"#CardHover {{ border: 2px solid {p.accent}; }}" if k == eid else "")

    # ================================================================== étape 4
    def _page_test(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        c = Card()
        c.add(card_title("Essayez votre nouvelle voix", "Écrivez une phrase et écoutez le résultat.", "headphones"))
        from ...config import settings

        self.test_text = QPlainTextEdit(settings().get("preview_sentence"))
        self.test_text.setMaximumHeight(110)
        c.add(self.test_text)
        row = QHBoxLayout()
        self.gen_btn = button("Générer un essai", "sparkles", "primary")
        self.gen_btn.clicked.connect(self._generate)
        self.spinner = Spinner()
        self.spinner.hide()
        row.addWidget(self.gen_btn)
        row.addWidget(self.spinner)
        row.addStretch(1)
        ref = button("Écouter la référence", "play")
        ref.clicked.connect(lambda: self.voice and self.ctx.play(self.voice.reference_paths()[0], "Référence"))
        row.addWidget(ref)
        c.add(row)
        self.test_status = label("", "Muted", wrap=True)
        c.add(self.test_status)
        self.install_btn = button("Installer le moteur maintenant", "download")
        self.install_btn.clicked.connect(self._go_install)
        self.install_btn.hide()
        c.add(self.install_btn)
        c.add(None)
        lay.addWidget(c, 3)
        self.param_card = Card()
        self.param_card.add(card_title("Réglages", "", "sliders"))
        self.params_box = QVBoxLayout()
        self.param_card.add(self.params_box)
        self.param_card.add(None)
        lay.addWidget(self.param_card, 2)
        return w

    def _build_params(self) -> None:
        while self.params_box.count():
            it = self.params_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        eng = engines.get_engine(self.engine_choice)
        for spec in eng.info.params:
            s = ParamSlider(spec, (self.voice.params if self.voice else {}).get(spec.key, spec.default))
            s.changed.connect(self._param)
            self.params_box.addWidget(s)

    def _param(self, key: str, value: float) -> None:
        if self.voice is not None:
            self.voice.params[key] = value
            self.ctx.library.save(self.voice)

    def _create_voice(self) -> bool:
        sel = self.wave.selection()
        if self.data is None or sel is None:
            return False
        name = self.name.text().strip() or "Ma voix"
        if self.voice is None:
            self.voice = VoiceProfile(name=name, engine=self.engine_choice, kind="clone",
                                      language=self.lang.currentData(), gender=self.gender.currentData(),
                                      description=self.desc.text().strip(), consent=True,
                                      color=random.choice(COLORS))
        else:
            self.voice.name = name
            self.voice.engine = self.engine_choice
            self.voice.language = self.lang.currentData()
            self.voice.gender = self.gender.currentData()
            self.voice.description = self.desc.text().strip()
        vdir = self.ctx.library.voice_dir(self.voice)
        target = vdir / "reference_01.wav"
        try:
            audio.prepare_reference(self._source_wav(), target, sel[0], sel[1], denoise=self.denoise.isChecked())
        except Exception as exc:
            self.ctx.toast(f"Préparation impossible : {exc}", "error", 7000)
            return False
        self.voice.references = ["reference_01.wav"]
        self.ctx.library.save(self.voice)
        self._saved_voice = True
        return True

    def _generate(self) -> None:
        if self.voice is None:
            return
        eng = engines.get_engine(self.voice.engine)
        if not eng.is_ready():
            self.test_status.setText(f"Le moteur « {eng.info.name} » n'est pas encore installé. Votre voix est "
                                     "enregistrée : installez le moteur pour l'entendre.")
            self.install_btn.show()
            return
        self.gen_btn.setEnabled(False)
        self.spinner.start()
        self.test_status.setText("Génération en cours… (le premier essai charge le modèle, cela peut prendre une "
                                 "minute ou plus)")

        def done(_ok):
            self.gen_btn.setEnabled(True)
            self.spinner.stop()
            self.test_status.setText("Écoutez le résultat. Ajustez les réglages ou l'extrait si besoin.")

        self.ctx.preview_voice(self.voice, self.test_text.toPlainText().strip() or None, on_done=done)

    def _go_install(self) -> None:
        self.accept()
        self.ctx.navigate("engines")

    # ================================================================== navigation
    def _go(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        self.steps.set_current(i)
        self.back_btn.setVisible(i > 0)
        self.next_btn.setVisible(i > 0)
        self.next_btn.setText("Terminer" if i == 3 else "Continuer")
        self.next_btn.setIcon(icons.icon("check" if i == 3 else "chevron-right", "#FFFFFF", 18))
        if i == 1 and self.data is not None:
            self.wave.set_audio(self.data, self.sr)
            (self._tmpdir / "source.wav").unlink(missing_ok=True)
            self._auto_select()
            self._analyze()
        if i == 2 and not self.name.text().strip() and self.source_file is not None:
            stem = self.source_file.stem
            self.name.setText("Ma voix" if stem == "enregistrement" else stem[:40])
        if i == 3:
            self._build_params()
            eng = engines.get_engine(self.engine_choice)
            ready = eng.is_ready()
            self.install_btn.setVisible(not ready)
            self.test_status.setText("" if ready else
                                     f"Le moteur « {eng.info.name} » n'est pas installé : vous pourrez l'installer "
                                     "depuis la page Moteurs IA puis tester la voix.")

    def _next(self) -> None:
        i = self.stack.currentIndex()
        if i == 1:
            sel = self.wave.selection()
            if sel is None or sel[1] - sel[0] < 3:
                self.ctx.toast("Sélectionnez au moins 3 secondes de parole.", "warning")
                return
        if i == 2:
            if not self.consent.isChecked():
                self.ctx.toast("Merci de confirmer que vous avez le droit de cloner cette voix.", "warning")
                return
            if not self._create_voice():
                return
        if i == 3:
            self.ctx.toast(f"Voix « {self.voice.name} » ajoutée à votre bibliothèque.", "success")
            self.accept()
            return
        self._go(i + 1)

    def _back(self) -> None:
        i = self.stack.currentIndex()
        if i > 0:
            self._go(i - 1)

    def reject(self) -> None:
        if self.recorder.recording:
            self.recorder.stop()
        if self._saved_voice and self.voice is not None:
            self.ctx.library.delete(self.voice.id)
            self.voice = None
        super().reject()
