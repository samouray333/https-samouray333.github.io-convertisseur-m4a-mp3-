"""Nouvelle histoire : le parent écrit ou dicte une idée, choisit l'âge, la durée, le ton, une morale et le prénom
de l'enfant ; DeepSeek écrit le conte avec un narrateur et des personnages qui parlent."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QVBoxLayout)

from ...config import settings
from ...core import audio, story
from ...core.models import Chapter
from ...core.secrets import protect, unprotect
from .. import tasks, theme
from ..widgets import Card, ToggleSwitch, button, card_title, label

log = logging.getLogger(__name__)

IDEAS = ["un dragon qui a peur du noir", "une petite tortue qui veut gagner une course",
         "un nuage qui ne veut pas pleuvoir", "une sorcière qui rate toutes ses potions", "un robot qui apprend à rire",
         "un ours qui a perdu son doudou", "une fusée en carton qui part pour la Lune"]


def cover_folder(project) -> Path:
    if project.path is not None:
        d = project.path.parent / "couvertures"
    else:
        from ...core import project_io

        d = project_io.project_data_dir(project) / "couvertures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def draw_story_cover(project, chapter: Chapter) -> str:
    """Dessine la couverture d'une histoire et renvoie son chemin."""
    from ...core import covers
    from ...core.textproc import personalize

    child = project.metadata.child_name
    target = cover_folder(project) / f"{chapter.id}.png"
    covers.generate_cover(personalize(chapter.title, child), target,
                          chapter.description + " " + personalize(chapter.text[:800], child), chapter.bedtime,
                          subtitle=project.metadata.title if project.metadata.title else "")
    return str(target)


class StoryDialog(QDialog):
    def __init__(self, ctx, parent=None, chapter: Chapter | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.chapter = chapter  # histoire vide à remplir (sinon une nouvelle est ajoutée)
        self.created: Chapter | None = None
        self._story: story.Story | None = None
        self._task = None
        self._dictation = None
        self.setWindowTitle("Nouvelle histoire")
        self.resize(1160, 820)
        pr = ctx.project
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title("Nouvelle histoire",
                                 "Donnez une idée, même toute petite : l'assistant écrit un conte adapté à l'âge de "
                                 "l'enfant, avec un narrateur, des personnages qui parlent, des bruitages et des "
                                 "ambiances. Vous le relisez et le modifiez librement avant de le produire.",
                                 "sparkles"))

        self.key_card = Card(obj="CardFlat", margins=(14, 12, 14, 12))
        self.key_card.add(label("Collez votre clé API DeepSeek (platform.deepseek.com → API keys). Elle est "
                                "enregistrée chiffrée sur cet ordinateur et partagée avec les autres applications.",
                                "Hint", wrap=True))
        kr = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("sk-…")
        save = button("Enregistrer la clé", "save")
        save.clicked.connect(self._save_key)
        kr.addWidget(self.key, 1)
        kr.addWidget(save)
        self.key_card.add(kr)
        lay.addWidget(self.key_card)
        self.key_card.setVisible(not unprotect(settings().get("ai_key", "")))

        top = QHBoxLayout()
        top.setSpacing(16)
        left = QVBoxLayout()
        ir = QHBoxLayout()
        ir.addWidget(label("L'idée de l'histoire", "Muted"), 1)
        self.dictate_btn = button("Dicter", "mic", tooltip="Dites l'idée au micro : elle est écrite automatiquement "
                                  "(reconnaissance vocale Whisper, gratuite et hors ligne, à installer dans Moteurs IA)")
        self.dictate_btn.clicked.connect(self.toggle_dictation)
        ir.addWidget(self.dictate_btn)
        left.addLayout(ir)
        self.idea = QPlainTextEdit()
        self.idea.setPlaceholderText("Par exemple : " + " ; ".join(IDEAS[:3]) + "…\nVous pouvez aussi donner des "
                                     "détails : le doudou de l'enfant, son animal préféré, un souvenir de vacances…")
        self.idea.setMinimumHeight(110)
        left.addWidget(self.idea, 1)
        top.addLayout(left, 3)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.age = QComboBox()
        for key, prof in story.AGES.items():
            self.age.addItem(prof.label, key)
        self.minutes = QDoubleSpinBox()
        self.minutes.setRange(story.MIN_MINUTES, story.MAX_MINUTES)
        self.minutes.setDecimals(0)
        self.minutes.setSuffix(" min")
        self.tone = QComboBox()
        for key, (lbl, _d) in story.TONES.items():
            self.tone.addItem(lbl, key)
        self.moral = QLineEdit()
        self.moral.setPlaceholderText("Facultatif : « on a le droit d'avoir peur », « partager rend heureux »…")
        self.child = QLineEdit(pr.metadata.child_name)
        self.child.setPlaceholderText("Facultatif : l'enfant devient le héros")
        rows = [("Âge", self.age), ("Durée", self.minutes), ("Ton", self.tone), ("Morale", self.moral),
                ("Prénom de l'enfant", self.child)]
        for r, (name, w) in enumerate(rows):
            grid.addWidget(label(name, "Muted"), r, 0)
            grid.addWidget(w, r, 1)
        self.bedtime = ToggleSwitch("Histoire du soir (voix douce, berceuse à la fin)")
        self.bedtime.toggled.connect(self._bedtime_toggled)
        grid.addWidget(self.bedtime, len(rows), 0, 1, 2)
        self.series = ToggleSwitch("Reprendre les personnages de la collection")
        self.series.setToolTip("Pour une série : l'assistant garde les mêmes personnages, avec leur caractère")
        grid.addWidget(self.series, len(rows) + 1, 0, 1, 2)
        self.go = button("Écrire l'histoire", "sparkles", "primary")
        self.go.clicked.connect(self.start)
        grid.addWidget(self.go, len(rows) + 2, 0, 1, 2)
        top.addLayout(grid, 2)
        lay.addLayout(top)

        s = settings()
        self.age.setCurrentIndex(max(0, self.age.findData(s.get("story_age", "6-8"))))
        self.minutes.setValue(float(s.get("story_minutes", 8)))
        self.tone.setCurrentIndex(max(0, self.tone.findData(s.get("story_tone", "aventure"))))
        self.series.setChecked(bool(pr.hosts))
        self.series.setVisible(bool(pr.hosts))

        self.status = label("L'idée est envoyée à DeepSeek (service en ligne, environ un centime par histoire). "
                            "Sans clé, écrivez l'histoire vous-même dans la page Histoires.", "Hint", wrap=True)
        lay.addWidget(self.status)
        pv = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Titre de l'histoire")
        self.title_edit.setStyleSheet("font-size: 14pt; font-weight: 700;")
        pv.addWidget(self.title_edit, 1)
        lay.addLayout(pv)
        self.preview = QPlainTextEdit()
        self.preview.setPlaceholderText("L'histoire apparaîtra ici ; vous pourrez la retoucher avant de l'ajouter.")
        from ..pages.manuscript import ScriptHighlighter

        self._hl = ScriptHighlighter(self.preview.document())
        lay.addWidget(self.preview, 3)
        self.checks = label("", "Hint", wrap=True)
        self.checks.setStyleSheet(f"color: {theme.CURRENT.warning};")
        self.checks.hide()
        lay.addWidget(self.checks)

        bottom = QHBoxLayout()
        self.cover_toggle = ToggleSwitch("Dessiner une couverture")
        self.cover_toggle.setChecked(True)
        bottom.addWidget(self.cover_toggle)
        bottom.addStretch(1)
        close = button("Fermer", kind="ghost")
        close.clicked.connect(self.reject)
        self.use = button("Ajouter l'histoire", "check", "primary")
        self.use.setEnabled(False)
        self.use.clicked.connect(self._apply)
        self.preview.textChanged.connect(lambda: self.use.setEnabled(bool(self.preview.toPlainText().strip())))
        bottom.addWidget(close)
        bottom.addWidget(self.use)
        lay.addLayout(bottom)

    # -- réglages ----------------------------------------------------------------------
    def _bedtime_toggled(self, on: bool) -> None:
        if on:
            self.tone.setCurrentIndex(max(0, self.tone.findData("douce")))

    def _save_key(self) -> None:
        key = self.key.text().strip()
        if not key:
            return
        settings().set("ai_key", protect(key))
        settings().set("ai_model", "")
        self.key.clear()
        self.key_card.hide()
        self.ctx.toast("Clé DeepSeek enregistrée.", "success")

    def request(self) -> story.StoryRequest:
        pr = self.ctx.project
        chars = []
        if self.series.isChecked():
            chars = [story.StoryCharacter(h.name, h.bio or h.role_label) for h in pr.hosts if "{" not in h.name]
        previous = [c.title for c in pr.chapters if c.text.strip()] if self.series.isChecked() else []
        return story.StoryRequest(self.idea.toPlainText(), self.age.currentData(), self.minutes.value(),
                                  self.tone.currentData(), self.moral.text().strip(), self.child.text().strip(),
                                  self.bedtime.isChecked(), chars, previous, pr.metadata.language or "fr")

    # -- dictée ------------------------------------------------------------------------
    def toggle_dictation(self) -> None:
        from ...core import engines
        from .clone_wizard import Recorder

        if self._dictation is not None and self._dictation.recording:
            data = self._dictation.stop()
            self.dictate_btn.setText("Dicter")
            self._transcribe(data, self._dictation.sr)
            return
        tool = engines.get_tool("whisper")
        if tool is None or not tool.is_ready():
            self.ctx.toast("Pour dicter, installez d'abord la reconnaissance vocale Whisper (page Moteurs IA, gratuite "
                           "et hors ligne). Vous pouvez aussi utiliser la dictée de Windows : touche Windows + H.",
                           "info", 9000)
            return
        self._dictation = Recorder()
        self._dictation.error.connect(lambda m: self.ctx.toast(m, "error", 7000))
        if self._dictation.start(None):
            self.dictate_btn.setText("Terminer la dictée")
            self.status.setText("● Parlez : dites l'idée de l'histoire, puis cliquez sur « Terminer la dictée ».")

    def _transcribe(self, data: np.ndarray, sr: int) -> None:
        from ...core import engines

        if data.size < sr * 0.5:
            self.status.setText("Dictée trop courte : recommencez.")
            return
        tmp = Path(tempfile.mkdtemp(prefix="dictee-")) / "idee.wav"
        audio.write_audio(tmp, data.astype(np.float32), sr, subtype="PCM_16")
        self.status.setText("Reconnaissance de la dictée…")

        def done(text):
            text = " ".join(str(text or "").split())
            if text:
                old = self.idea.toPlainText().strip()
                self.idea.setPlainText((old + " " if old else "") + text)
                self.status.setText("Idée dictée : relisez-la, puis cliquez sur « Écrire l'histoire ».")
            else:
                self.status.setText("Rien n'a été entendu : rapprochez-vous du micro et recommencez.")

        self._dict_task = tasks.run(engines.get_tool("whisper").transcribe, tmp, "fr", on_done=done,
                                    on_error=lambda m, _t: self.status.setText(f"Dictée impossible : {m}"))

    # -- écriture ----------------------------------------------------------------------
    def start(self) -> None:
        req = self.request()
        s = settings()
        s.set("story_age", req.age, save=False)
        s.set("story_minutes", req.minutes, save=False)
        s.set("story_tone", req.tone)
        self.go.setEnabled(False)
        self.status.setText("DeepSeek écrit l'histoire… (de quelques secondes à une minute)")

        def work(task):
            from ...core import ai

            return story.write_story(req, ai.client_from_settings(), progress=task.report)

        self._task = tasks.Task(work, pass_reporter=True, on_done=self._done, on_error=self._failed,
                                on_progress=lambda m: self.status.setText(str(m))).start()

    def _done(self, st: story.Story) -> None:
        self.go.setEnabled(True)
        self._story = st
        self.title_edit.setText(st.title)
        script = story.story_to_script(st)
        self.preview.setPlainText(script)
        req = self.request()
        minutes = st.words / (story.age_profile(req.age).wpm * (0.88 if req.bedtime else 1.0))
        self.status.setText(f"« {st.title} » : {st.words} mots, ≈ {minutes:.0f} min d'écoute, "
                            f"{len(st.characters)} personnage(s). {st.summary}")
        self._show_checks(script)

    def _show_checks(self, script: str) -> None:
        notes = story.check_for_age(script, self.age.currentData())
        self.checks.setVisible(bool(notes))
        self.checks.setText("À vérifier : " + " ".join(notes) if notes else "")

    def _failed(self, msg: str, _tb: str) -> None:
        self.go.setEnabled(True)
        self.status.setText(msg)
        self.ctx.toast(msg, "error", 7000)

    def _apply(self) -> None:
        script = self.preview.toPlainText().strip()
        if not script:
            return
        pr = self.ctx.project
        req = self.request()
        if req.child_name and req.child_name != pr.metadata.child_name:
            pr.metadata.child_name = req.child_name
        title = self.title_edit.text().strip() or "Nouvelle histoire"
        st = self._story
        ch = self.chapter if self.chapter is not None else Chapter(title=title)
        ch.title, ch.text = title, script
        ch.age, ch.tone, ch.moral, ch.bedtime = req.age, req.tone, req.moral, req.bedtime
        if st is not None and st.summary:
            ch.description = st.summary
        if self.chapter is None:
            pr.chapters.append(ch)
        if st is not None:  # nouveaux personnages : une voix et une façon de parler chacun
            lib = self.ctx.library
            taken = [v for v in (lib.get(h.voice_id) for h in pr.hosts) if v is not None]
            taken += [v for v in (lib.get(pr.narrator_voice_id),) if v is not None]
            new_hosts = story.characters_to_hosts(st.characters, pr.hosts, taken, lib)
            pr.hosts.extend(new_hosts)
            for h in pr.hosts:
                pr.cast[h.name] = h.voice_id
            if new_hosts:
                self.ctx.voices_changed.emit()
        if self.cover_toggle.isChecked():
            try:
                ch.cover_path = draw_story_cover(pr, ch)
            except Exception as exc:
                log.warning("Couverture non dessinée : %s", exc)
        self.created = ch
        self.ctx.mark_dirty()
        self.accept()

    def done(self, r):
        if self._dictation is not None and self._dictation.recording:
            self._dictation.stop()
        super().done(r)
