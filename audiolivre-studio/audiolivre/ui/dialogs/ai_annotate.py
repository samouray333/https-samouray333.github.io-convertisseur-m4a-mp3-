"""Assistant IA : propositions de DeepSeek (qui parle, émotions, noms propres) à valider avant application."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLineEdit,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ...config import settings
from ...core import ai
from ...core.secrets import protect, unprotect
from ...core.textproc import EMOTION_LABELS
from .. import tasks, theme
from ..widgets import Card, ToggleSwitch, button, card_title, label


class AIAnnotateDialog(QDialog):
    def __init__(self, ctx, chapter, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.chapter = chapter
        self.result: ai.Annotation | None = None
        self._task = None
        self.setWindowTitle("Assistant IA")
        self.resize(1020, 700)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title(f"Assistant IA — {chapter.title}",
                                 "DeepSeek repère qui parle, le ton des passages et les noms difficiles à "
                                 "prononcer. Votre texte n'est jamais réécrit : vous validez chaque proposition.",
                                 "sparkles"))

        self.key_card = Card(obj="CardFlat", margins=(14, 12, 14, 12))
        self.key_card.add(label("Collez votre clé API DeepSeek (platform.deepseek.com → API keys). Elle est "
                                "enregistrée chiffrée sur cet ordinateur.", "Hint", wrap=True))
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
        self.status = label("Le texte du chapitre sera envoyé à DeepSeek (service en ligne payant, quelques "
                            "centimes par livre).", "Muted", wrap=True)
        top.addWidget(self.status, 1)
        self.go = button("Analyser le chapitre", "sparkles", "primary")
        self.go.clicked.connect(self.start)
        top.addWidget(self.go)
        lay.addLayout(top)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Paragraphe", "Personnage qui parle", "Émotion"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setWordWrap(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Interactive)
        hh.setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 150)
        lay.addWidget(self.table, 3)

        self.names_title = label("Noms propres : prononciation proposée (ajoutée au lexique)", "Muted")
        lay.addWidget(self.names_title)
        self.names = QTableWidget(0, 3)
        self.names.setHorizontalHeaderLabels(["", "Nom écrit", "Se prononce"])
        self.names.verticalHeader().setVisible(False)
        nh = self.names.horizontalHeader()
        nh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        nh.setSectionResizeMode(1, QHeaderView.Stretch)
        nh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.names.setMaximumHeight(150)
        lay.addWidget(self.names, 1)

        self.auto_voices = ToggleSwitch("Donner une voix Microsoft différente à chaque nouveau personnage", True)
        lay.addWidget(self.auto_voices)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Fermer", kind="ghost")
        cancel.clicked.connect(self.reject)
        self.apply_btn = button("Appliquer les propositions", "check", "primary")
        self.apply_btn.clicked.connect(self._apply)
        self.apply_btn.setEnabled(False)
        row.addWidget(cancel)
        row.addWidget(self.apply_btn)
        lay.addLayout(row)
        self._show_names(False)

    # ------------------------------------------------------------------------------
    def _save_key(self) -> None:
        key = self.key.text().strip()
        if not key:
            return
        settings().set("ai_key", protect(key))
        settings().set("ai_model", "")
        self.key.clear()
        self.key_card.hide()
        self.ctx.toast("Clé DeepSeek enregistrée.", "success")

    def _show_names(self, on: bool) -> None:
        self.names_title.setVisible(on)
        self.names.setVisible(on)

    def start(self) -> None:
        if self.key_card.isVisible() and self.key.text().strip():
            self._save_key()
        try:
            client = ai.client_from_settings()
        except ai.AIError as exc:
            self.key_card.show()
            self.status.setText(str(exc))
            return
        self.go.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.status.setText("Connexion à DeepSeek…")
        known = list(self.ctx.project.cast.keys())
        text = self.chapter.text

        def work(task):
            return ai.annotate(text, client, known, progress=task.say, cancel=task.cancel_event)

        self._task = tasks.Task(work, pass_reporter=True, on_done=self._done, on_error=self._failed,
                                on_message=self.status.setText).start()

    def _failed(self, msg: str, _tb: str) -> None:
        self.go.setEnabled(True)
        self.status.setText("⚠ " + msg)
        self.status.setStyleSheet(f"color: {theme.CURRENT.warning};")

    def _done(self, result: ai.Annotation) -> None:
        self.go.setEnabled(True)
        self.go.setText("Relancer l'analyse")
        self.status.setStyleSheet("")
        if result.model and not settings().get("ai_model"):
            settings().set("ai_model", result.model)
        self.show_result(result)

    def show_result(self, result: ai.Annotation) -> None:
        self.result = result
        n = len(result.paragraphs)
        chars = ", ".join(result.characters) or "aucun"
        self.status.setText(f"{n} proposition(s) · personnages : {chars}. Décochez ce qui ne convient pas, "
                            "corrigez un nom si besoin, puis appliquez.")
        self.table.setRowCount(n)
        emotions = [("", "—")] + list(EMOTION_LABELS.items())
        for r, s in enumerate(result.paragraphs):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if s.accepted else Qt.Unchecked)
            self.table.setItem(r, 0, chk)
            ex = QTableWidgetItem(s.excerpt)
            ex.setFlags(Qt.ItemIsEnabled)
            ex.setToolTip(s.excerpt)
            self.table.setItem(r, 1, ex)
            self.table.setItem(r, 2, QTableWidgetItem(s.speaker or ""))
            combo = QComboBox()
            for key, lbl in emotions:
                combo.addItem(lbl, key)
            combo.setCurrentIndex(max(0, combo.findData(s.emotion)))
            self.table.setCellWidget(r, 3, combo)
        self.table.resizeRowsToContents()
        self.names.setRowCount(len(result.names))
        for r, nm in enumerate(result.names):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked)
            self.names.setItem(r, 0, chk)
            w = QTableWidgetItem(nm.word)
            w.setFlags(Qt.ItemIsEnabled)
            self.names.setItem(r, 1, w)
            self.names.setItem(r, 2, QTableWidgetItem(nm.say))
        self._show_names(bool(result.names))
        self.apply_btn.setEnabled(bool(n or result.names))

    def _collect(self) -> None:
        assert self.result is not None
        for r, s in enumerate(self.result.paragraphs):
            s.accepted = self.table.item(r, 0).checkState() == Qt.Checked
            s.speaker = (self.table.item(r, 2).text() or "").strip() or None
            s.emotion = self.table.cellWidget(r, 3).currentData() or ""
        for r, nm in enumerate(self.result.names):
            nm.accepted = self.names.item(r, 0).checkState() == Qt.Checked
            nm.say = self.names.item(r, 2).text().strip() or nm.say

    def _apply(self) -> None:
        if self.result is None:
            return
        self._collect()
        pr = self.ctx.project
        accepted = [s for s in self.result.paragraphs if s.accepted]
        self.chapter.text = ai.apply_suggestions(self.chapter.text, accepted)
        pr.lexicon.extend(ai.lexicon_entries(self.result.names, pr.lexicon))
        speakers = {s.speaker for s in accepted if s.speaker}
        new_chars = {n: self.result.characters.get(n, "?") for n in speakers
                     if not any(n.lower() == k.lower() for k in pr.cast)}
        assigned = 0
        if self.auto_voices.isChecked() and new_chars:
            lib = self.ctx.library
            taken = [v for v in (lib.get(pr.narrator_voice_id), lib.get(pr.production.dialogue_voice_id))
                     if v is not None] + [v for v in (lib.get(i) for i in pr.cast.values()) if v is not None]
            for name, voice in ai.voices_for_characters(new_chars, taken).items():
                pr.cast[name] = lib.save(voice).id
                assigned += 1
        for name in new_chars:
            pr.cast.setdefault(name, "")
        self.ctx.mark_dirty()
        msg = f"{len(accepted)} paragraphe(s) annoté(s)"
        if assigned:
            msg += f", {assigned} voix attribuée(s) (modifiables dans Distribution des rôles)"
        self.ctx.toast(msg + ".", "success")
        self.accept()

    def reject(self) -> None:
        if self._task is not None and self._task.is_running():
            self._task.cancel_event.set()
        super().reject()
