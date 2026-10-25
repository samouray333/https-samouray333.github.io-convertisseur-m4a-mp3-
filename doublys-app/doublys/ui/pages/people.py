"""Page Personnes : une carte par personne (nom, extrait de voix, mode de voix, voix de base, essai)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox, QVBoxLayout

from ... import paths
from ...config import settings
from ...core import audio, dubvoice, pipeline, refs
from ...core import project as project_io
from ...core.models import VOICE_MODES
from .. import tasks
from ..widgets import Avatar, Card, EmptyState, button, card_title, label
from .base import Page

log = logging.getLogger(__name__)

AUDIO_FILTER = "Audio ou vidéo (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac *.mp4 *.mkv *.mov *.webm);;Tous (*)"


def narrow(combo: QComboBox, chars: int = 20) -> None:
    """Liste déroulante qui ne force pas la largeur de la carte (texte long affiché en entier une fois ouverte)."""
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(chars)
    combo.view().setMinimumWidth(380)


class PersonCard(Card):
    def __init__(self, page: "PeoplePage", person):
        super().__init__(margins=(18, 16, 18, 16), spacing=10)
        self.page = page
        self.person = person
        pr = page.ctx.project
        mine = [ln for ln in pr.lines if ln.person_id == person.id]
        talk = sum(ln.length for ln in mine)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.avatar = Avatar(person.name, person.color, 46)
        top.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.name = QLineEdit(person.name)
        self.name.setPlaceholderText("Nom de la personne")
        self.name.editingFinished.connect(self._rename)
        col.addWidget(self.name)
        g = {"M": "voix d'homme", "F": "voix de femme"}.get(person.gender, "genre inconnu")
        pitch = f" ({person.pitch_hz:.0f} Hz)" if person.pitch_hz else ""
        known = " · ★ personnage de la série" if person.character else ""
        col.addWidget(label(f"{len(mine)} répliques · {talk:.0f} s de parole · {g}{pitch}{known}", "Hint"))
        top.addLayout(col, 1)
        self.add(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(label("Extrait de voix", "Muted"), 0, 0)
        ref = dubvoice.reference_path(pr, person)
        dur = audio.duration_of(ref) if ref else 0.0
        src = "fichier choisi" if person.reference_source == "file" else "pris dans ses répliques"
        self.ref_info = label(f"{dur:.0f} s, {src}" if ref else "pas encore d'extrait", "Hint")
        rr = QHBoxLayout()
        rr.setSpacing(6)
        grid.addWidget(self.ref_info, 0, 1)
        play = button("Écouter", "play")
        play.setEnabled(ref is not None)
        play.clicked.connect(self._play_ref)
        other = button("Autre extrait", "refresh", tooltip="Prendre d'autres répliques de cette personne")
        other.clicked.connect(self._other_ref)
        other.setEnabled(bool(mine))
        pick = button("Fichier…", "folder", tooltip="Utiliser un enregistrement de cette personne (10 à 30 s)")
        pick.clicked.connect(self._pick_ref)
        rr.addWidget(play)
        rr.addWidget(other)
        rr.addWidget(pick)
        rr.addStretch(1)
        grid.addLayout(rr, 1, 1)

        grid.addWidget(label("Mode de voix", "Muted"), 2, 0)
        self.mode = QComboBox()
        default = VOICE_MODES[pr.settings.voice_mode][0] if pr.settings.voice_mode in VOICE_MODES else ""
        self.mode.addItem(f"Par défaut du projet ({default})", "")
        for key, (text, _eng, _clone) in VOICE_MODES.items():
            self.mode.addItem(text, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(person.voice_mode or "")))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        grid.addWidget(self.mode, 2, 1)

        grid.addWidget(label("Voix de base", "Muted"), 3, 0)
        self.base = QComboBox()
        self.base.currentIndexChanged.connect(self._base_changed)
        grid.addWidget(self.base, 3, 1)

        grid.addWidget(label("Genre", "Muted"), 4, 0)
        self.gender = QComboBox()
        for k, v in (("", "Inconnu"), ("M", "Homme"), ("F", "Femme")):
            self.gender.addItem(v, k)
        self.gender.setCurrentIndex(max(0, self.gender.findData(person.gender)))
        self.gender.currentIndexChanged.connect(self._gender_changed)
        grid.addWidget(self.gender, 4, 1)

        rvc_row = QHBoxLayout()
        self.rvc_lbl = label(Path(person.rvc_model).name if person.rvc_model else "aucun modèle", "Hint")
        rvc_btn = button("Modèle .pth…", "folder")
        rvc_btn.clicked.connect(self._pick_rvc)
        rvc_row.addWidget(self.rvc_lbl, 1)
        rvc_row.addWidget(rvc_btn)
        self.rvc_title = label("Modèle RVC", "Muted")
        grid.addWidget(self.rvc_title, 5, 0)
        grid.addLayout(rvc_row, 5, 1)
        self._rvc_widgets = [self.rvc_title, self.rvc_lbl, rvc_btn]
        grid.setColumnStretch(1, 1)
        self.add(grid)

        bottom = QHBoxLayout()
        self.status = label("", "Hint", wrap=True)
        bottom.addWidget(self.status, 1)
        self.try_btn = button("Essai", "headphones", "primary", tooltip="Écouter une phrase avec cette voix")
        self.try_btn.clicked.connect(self._try)
        bottom.addWidget(self.try_btn)
        self.add(bottom)
        for combo in (self.mode, self.base, self.gender):
            narrow(combo)
        self._fill_bases()

    # -- modifications ----------------------------------------------------------------
    def _changed(self, voice: bool = True) -> None:
        pr = self.page.ctx.project
        if voice:
            pr.mark_step("dub", False)
            pr.mark_step("mix", False)
        self.page.ctx.mark_dirty()

    def _rename(self) -> None:
        name = self.name.text().strip() or self.person.name
        if name != self.person.name:
            self.page.ctx.checkpoint("renommage")
            self.person.name = name
            self.avatar.set(name, self.person.color)
            self._changed(voice=False)
            self.page.ctx.people_changed.emit()

    def _mode(self) -> str:
        return dubvoice.voice_mode(self.page.ctx.project, self.person)

    def _fill_bases(self) -> None:
        mode = self._mode()
        self.base.blockSignals(True)
        self.base.clear()
        for vid, name in dubvoice.base_choices(mode):
            self.base.addItem(name, vid)
        self.base.setCurrentIndex(max(0, self.base.findData(self.person.base_voice)))
        self.base.setEnabled(self.base.count() > 1)
        self.base.blockSignals(False)
        for w in self._rvc_widgets:
            w.setVisible(mode == "rvc")
        ok, msg = dubvoice.engine_ready(self.page.ctx.project, self.person)
        self.status.setText("" if ok else f"⚠ {msg} (page Moteurs IA)")

    def _mode_changed(self) -> None:
        self.page.ctx.checkpoint("mode de voix")
        self.person.voice_mode = self.mode.currentData() or ""
        self.person.base_voice = ""
        self._fill_bases()
        self._changed()

    def _base_changed(self) -> None:
        self.page.ctx.checkpoint("voix de base")
        self.person.base_voice = self.base.currentData() or ""
        self._changed()

    def _gender_changed(self) -> None:
        self.page.ctx.checkpoint("genre")
        self.person.gender = self.gender.currentData() or ""
        self._changed()

    def _pick_rvc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Modèle de voix RVC", str(Path.home()), "Modèle RVC (*.pth)")
        if not path:
            return
        self.person.rvc_model = path
        index = next(iter(sorted(Path(path).parent.glob("*.index"))), None)
        self.person.rvc_index = str(index) if index else ""
        self.rvc_lbl.setText(Path(path).name + (" + index" if index else ""))
        self._changed()
        self._fill_bases()

    # -- extrait ----------------------------------------------------------------------
    def _play_ref(self) -> None:
        ref = dubvoice.reference_path(self.page.ctx.project, self.person)
        if ref is not None:
            self.page.ctx.play(ref, f"Extrait — {self.person.name}")

    def _other_ref(self) -> None:
        pr = self.page.ctx.project
        if not (pipeline.wf(pr, pipeline.VOICE).exists() or pipeline.wf(pr, pipeline.ORIGINAL).exists()):
            self.page.ctx.toast("Le son de la vidéo n'est pas encore extrait.", "warning")
            return
        self.person.reference_offset += 1
        self.person.reference_source = "auto"
        pid = self.person.id

        def work():
            pipeline.step_voices(pr, pipeline.Job(), only=[pid])

        def done(_):
            self._changed()
            self.page.refresh()
            self.page.ctx.toast(f"Nouvel extrait pour {self.person.name}.", "success")
            self.page.play_reference(pid)

        self.page._task = tasks.run(work, on_done=done,
                                    on_error=lambda m, _t: self.page.ctx.toast(f"Extrait impossible : {m}", "error"))

    def _pick_ref(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"Enregistrement de {self.person.name}", str(Path.home()),
                                              AUDIO_FILTER)
        if not path:
            return
        pr = self.page.ctx.project
        target = project_io.references_dir(pr) / f"{self.person.id}-fichier.wav"

        def work():
            data, sr = audio.read_audio(path)
            s, e = audio.best_speech_window(data, sr, 20.0)
            out = audio.prepare_reference(path, target, s / sr, e / sr)
            d, r = audio.read_audio(out)
            return out, refs.estimate_pitch(d, r)

        def done(res):
            out, f0 = res
            self.person.reference = project_io.relative(pr, out)
            self.person.reference_source = "file"
            self.person.pitch_hz = round(f0, 1)
            if refs.gender_from_pitch(f0):
                self.person.gender = refs.gender_from_pitch(f0)
            self._changed()
            self.page.refresh()

        self.page._task = tasks.run(work, on_done=done,
                                    on_error=lambda m, _t: QMessageBox.warning(self, "Fichier inutilisable", m))

    # -- essai ------------------------------------------------------------------------
    def _try(self) -> None:
        pr = self.page.ctx.project
        try:
            voice = dubvoice.voice_profile(pr, self.person)
        except Exception as exc:
            self.page.ctx.toast(str(exc), "warning", 6000)
            return
        sample = next((ln.fr for ln in pr.lines if ln.person_id == self.person.id and len(ln.fr) > 20), "") or \
            settings().get("preview_sentence")
        self.try_btn.setEnabled(False)
        self.status.setText("Synthèse de l'essai… (le premier essai charge le modèle)")

        def work():
            data, sr = dubvoice.synthesize(voice, sample)
            out = Path(tempfile.mkdtemp(dir=paths.temp_dir())) / "essai.wav"
            return audio.write_audio(out, data, sr, subtype="PCM_16")

        def done(path):
            self.try_btn.setEnabled(True)
            self.status.setText(f"« {sample[:80]} »")
            self.page.ctx.play(path, f"Essai — {self.person.name}")

        def fail(msg, _tb):
            self.try_btn.setEnabled(True)
            self.status.setText("⚠ " + msg[:300])

        self.page._task = tasks.run(work, on_done=done, on_error=fail)


class PeoplePage(Page):
    name = "people"

    def __init__(self, ctx):
        super().__init__(ctx, "Personnes", "Chaque personne reçoit une voix française proche de la sienne. "
                         "Renommez-les, changez d'extrait ou de mode de voix, puis faites un essai.", scroll=True)
        self.cards: list[PersonCard] = []
        top = Card(obj="CardFlat", margins=(18, 14, 18, 14))
        row = QHBoxLayout()
        row.addWidget(card_title("Mode de voix du projet", "Utilisé pour toutes les personnes, sauf choix contraire "
                                 "sur leur carte.", "mic"), 1)
        self.default_mode = QComboBox()
        for key, (text, _e, _c) in VOICE_MODES.items():
            self.default_mode.addItem(text, key)
        self.default_mode.currentIndexChanged.connect(self._default_changed)
        narrow(self.default_mode, 30)
        row.addWidget(self.default_mode)
        top.add(row)
        top.add(label("Clonage rapide hors ligne : Kokoro lit le texte français, puis Chatterbox lui donne le timbre "
                      "de la personne (le plus rapide sans carte graphique). XTTS-v2 ressemble davantage mais "
                      "interdit l'usage commercial. Ne clonez que des voix de personnes qui ont donné leur accord ou "
                      "dont vous avez les droits.", "Hint", wrap=True))
        self.body.addWidget(top)

        ser = Card(obj="CardFlat", margins=(18, 14, 18, 14))
        srow = QHBoxLayout()
        srow.addWidget(card_title("Série", "Gardez les personnages (nom, extrait, voix) d'un épisode à l'autre : ils "
                                  "sont reconnus automatiquement dans les épisodes suivants.", "layers"), 1)
        self.series = QComboBox()
        narrow(self.series, 16)
        self.series.currentIndexChanged.connect(self._series_changed)
        srow.addWidget(self.series)
        self.save_series = button("Enregistrer les personnages", "save",
                                  tooltip="Ajoute ou met à jour les personnes nommées dans la série")
        self.save_series.clicked.connect(self._save_series)
        srow.addWidget(self.save_series)
        ser.add(srow)
        self.series_info = label("", "Hint", wrap=True)
        ser.add(self.series_info)
        self.body.addWidget(ser)
        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.body.addLayout(self.grid)
        self.empty = EmptyState("users", "Aucune personne pour l'instant",
                                "Les personnes sont reconnues automatiquement pendant le doublage (étape « Reconnaissance "
                                "des personnes »).")
        self.body.addWidget(self.empty)
        self.body.addStretch(1)
        self._task = None
        ctx.people_changed.connect(self.refresh)
        ctx.runner.finished.connect(lambda *_: self.refresh() if self.isVisible() else None)

    def on_show(self) -> None:
        self.refresh()

    def on_project_changed(self) -> None:
        self.refresh()

    # -- série ------------------------------------------------------------------------
    def _fill_series(self) -> None:
        from ...core import series as series_lib

        pr = self.ctx.project
        self.series.blockSignals(True)
        self.series.clear()
        self.series.addItem("Aucune série", "")
        for name in series_lib.list_series():
            self.series.addItem(name, name)
        self.series.addItem("Nouvelle série…", "__new__")
        cur = pr.series if pr is not None else ""
        self.series.setCurrentIndex(max(0, self.series.findData(cur)))
        self.series.blockSignals(False)
        self.series.setEnabled(pr is not None)
        self.save_series.setEnabled(pr is not None and bool(cur))
        if pr is None or not cur:
            self.series_info.setText("Astuce : nommez les personnes (P1 → « Red », P2 → « Blue »…), choisissez leur "
                                     "voix, puis enregistrez-les dans une série.")
            return
        s = series_lib.load(cur)
        names = ", ".join(c.name for c in s.characters) if s and s.characters else "aucun personnage enregistré"
        self.series_info.setText(f"Personnages de « {cur} » : {names}.")

    def _series_changed(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        from ...core import series as series_lib

        pr = self.ctx.project
        if pr is None:
            return
        name = self.series.currentData() or ""
        if name == "__new__":
            name, ok = QInputDialog.getText(self, "Nouvelle série", "Nom de la série :")
            name = name.strip()
            if not ok or not name:
                self._fill_series()
                return
            series_lib.save(series_lib.Series(name=name))
        self.ctx.checkpoint("série")
        pr.series = name
        found = series_lib.apply_to_project(pr) if name else 0
        self.ctx.mark_dirty()
        if found:
            pr.mark_step("dub", False)
            pr.mark_step("mix", False)
            self.ctx.toast(f"{found} personnage(s) de « {name} » reconnu(s) dans cet épisode.", "success", 5000)
            self.ctx.people_changed.emit()
        self.refresh()

    def _save_series(self) -> None:
        from ...core import series as series_lib

        pr = self.ctx.project
        if pr is None or not pr.series:
            return
        if not any(p.embedding for p in pr.people):
            self.ctx.toast("Lancez d'abord la reconnaissance des personnes (page Doublage).", "warning")
            return
        _s, n = series_lib.save_from_project(pr, pr.series)
        self.ctx.mark_dirty()
        if n:
            self.ctx.toast(f"{n} personnage(s) enregistré(s) dans « {pr.series} ».", "success")
        else:
            self.ctx.toast("Aucune personne nommée : renommez d'abord P1, P2… avec le nom des personnages.",
                           "warning", 6000)
        self._fill_series()

    def play_reference(self, person_id: str) -> None:
        for card in self.cards:
            if card.person.id == person_id:
                card._play_ref()

    def _default_changed(self) -> None:
        pr = self.ctx.project
        if pr is None:
            return
        mode = self.default_mode.currentData()
        if mode and mode != pr.settings.voice_mode:
            pr.settings.voice_mode = mode
            pr.mark_step("dub", False)
            pr.mark_step("mix", False)
            self.ctx.mark_dirty()
            self.refresh()

    def refresh(self) -> None:
        pr = self.ctx.project
        self._fill_series()
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.cards = []
        self.default_mode.blockSignals(True)
        if pr is not None:
            self.default_mode.setCurrentIndex(max(0, self.default_mode.findData(pr.settings.voice_mode)))
        self.default_mode.blockSignals(False)
        self.default_mode.setEnabled(pr is not None)
        people = pr.people if pr is not None else []
        used = {ln.person_id for ln in pr.lines} if pr is not None else set()
        people = [p for p in people if p.id in used] or people
        self.empty.setVisible(not people)
        for i, p in enumerate(people):
            c = PersonCard(self, p)
            self.cards.append(c)
            self.grid.addWidget(c, i // 2, i % 2, Qt.AlignTop)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
