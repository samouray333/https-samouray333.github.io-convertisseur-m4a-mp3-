"""Assistant d'écriture : DeepSeek transforme des notes en dialogue entre les animateurs et invités du podcast."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QVBoxLayout)

from ...config import settings
from ...core import ai
from ...core.secrets import protect, unprotect
from .. import tasks
from ..widgets import Card, button, card_title, label

STYLE_LABELS = {"conversation": "Conversation détendue", "interview": "Interview", "debat": "Débat",
                "recit": "Récit à plusieurs voix", "info": "Émission d'information"}


def notes_from_script(text: str) -> str:
    """Texte de départ proposé comme notes : le texte de l'épisode sans les balises de mise en scène."""
    if re.search(r"(?m)^@[^:\n]{1,40}:", text):
        return ""  # déjà un dialogue : l'utilisateur écrit de nouvelles notes
    return re.sub(r"\[[^\]\n]*\]", "", text).strip()


class WriteDialogueDialog(QDialog):
    def __init__(self, ctx, chapter, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.chapter = chapter
        self._task = None
        self._result: tuple[str, str, list[ai.DialogueLine]] | None = None
        self.setWindowTitle("Écrire l'épisode avec l'IA")
        self.resize(1100, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title(f"Écrire l'épisode — {chapter.title}",
                                 "Donnez le sujet, un plan ou collez un article : DeepSeek écrit un dialogue naturel "
                                 "entre vos animateurs et invités. Relisez-le et modifiez-le librement avant de "
                                 "produire l'épisode.", "sparkles"))

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

        row = QHBoxLayout()
        row.setSpacing(14)
        left = QVBoxLayout()
        left.addWidget(label("Sujet, plan ou notes de l'épisode", "Muted"))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Exemple : les bienfaits de la marche à pied. 1) pourquoi c'est bon pour le "
                                      "cœur 2) combien de pas par jour 3) trois astuces pour s'y mettre. "
                                      "Ton léger, avec une anecdote d'Alex.")
        self.notes.setPlainText(notes_from_script(chapter.text))
        left.addWidget(self.notes, 1)
        row.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(label("Qui participe ?", "Muted"))
        self.people = QListWidget()
        self.people.setMaximumWidth(320)
        for h in ctx.project.hosts:
            it = QListWidgetItem(f"{h.name} — {h.role_label}")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setData(Qt.UserRole, h.id)
            self.people.addItem(it)
        right.addWidget(self.people, 1)
        if not ctx.project.hosts:
            right.addWidget(label("Ajoutez d'abord vos animateurs dans la page Animateurs.", "Hint", wrap=True))
        right.addWidget(label("Style", "Muted"))
        self.style = QComboBox()
        for key, text in STYLE_LABELS.items():
            self.style.addItem(text, key)
        self.style.setCurrentIndex(max(0, self.style.findData(settings().get("podcast_style", "conversation"))))
        right.addWidget(self.style)
        right.addWidget(label("Durée visée", "Muted"))
        self.minutes = QDoubleSpinBox()
        self.minutes.setRange(1, 60)
        self.minutes.setSingleStep(1)
        self.minutes.setDecimals(0)
        self.minutes.setSuffix(" min")
        self.minutes.setValue(float(settings().get("podcast_minutes", 8)))
        right.addWidget(self.minutes)
        self.go = button("Écrire le dialogue", "sparkles", "primary")
        self.go.clicked.connect(self.start)
        right.addWidget(self.go)
        row.addLayout(right, 1)
        lay.addLayout(row, 2)

        self.status = label("Les notes sont envoyées à DeepSeek (service en ligne, quelques centimes par épisode). "
                            "Sans clé, écrivez le dialogue vous-même : « @Nom: réplique ».", "Hint", wrap=True)
        lay.addWidget(self.status)
        lay.addWidget(label("Script proposé", "Muted"))
        self.preview = QPlainTextEdit()
        self.preview.setPlaceholderText("Le dialogue apparaîtra ici ; vous pouvez le retoucher avant de l'utiliser.")
        from ..pages.manuscript import ScriptHighlighter

        self._hl = ScriptHighlighter(self.preview.document())
        lay.addWidget(self.preview, 3)

        bottom = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("Remplacer le script de l'épisode", "replace")
        self.mode.addItem("Ajouter à la fin du script", "append")
        if not chapter.text.strip():
            self.mode.setEnabled(False)
        bottom.addWidget(self.mode)
        bottom.addStretch(1)
        cancel = button("Fermer", kind="ghost")
        cancel.clicked.connect(self.reject)
        self.use = button("Utiliser ce script", "check", "primary")
        self.use.setEnabled(False)
        self.use.clicked.connect(self._apply)
        self.preview.textChanged.connect(lambda: self.use.setEnabled(bool(self.preview.toPlainText().strip())))
        bottom.addWidget(cancel)
        bottom.addWidget(self.use)
        lay.addLayout(bottom)

    def _save_key(self) -> None:
        key = self.key.text().strip()
        if not key:
            return
        settings().set("ai_key", protect(key))
        settings().set("ai_model", "")
        self.key.clear()
        self.key_card.hide()
        self.ctx.toast("Clé DeepSeek enregistrée.", "success")

    def _participants(self) -> list[tuple[str, str, str]]:
        chosen = []
        for i in range(self.people.count()):
            it = self.people.item(i)
            if it.checkState() != Qt.Checked:
                continue
            h = next((h for h in self.ctx.project.hosts if h.id == it.data(Qt.UserRole)), None)
            if h is not None:
                chosen.append((h.name, h.role_label, h.bio))
        return chosen

    def start(self) -> None:
        hosts = self._participants()
        notes = self.notes.toPlainText()
        style = self.style.currentData()
        minutes = self.minutes.value()
        settings().set("podcast_style", style)
        settings().set("podcast_minutes", minutes)
        lang = self.ctx.project.metadata.language or "fr"
        self.go.setEnabled(False)
        self.status.setText("DeepSeek écrit le dialogue… (de quelques secondes à une minute)")

        def work():
            return ai.write_dialogue(notes, hosts, ai.client_from_settings(), minutes, style, lang)

        self._task = tasks.run(work, on_done=self._done, on_error=self._failed)

    def _done(self, res) -> None:
        self.go.setEnabled(True)
        self._result = res
        title, desc, lines = res
        self.preview.setPlainText(ai.dialogue_to_script(lines))
        words = sum(len(ln.text.split()) for ln in lines)
        self.status.setText(f"{len(lines)} répliques, {words} mots (≈ {words / ai.WORDS_PER_MINUTE:.0f} min). "
                            f"Titre proposé : « {title or self.chapter.title} ».")

    def _failed(self, msg: str, _tb: str) -> None:
        self.go.setEnabled(True)
        self.status.setText(msg)
        self.ctx.toast(msg, "error", 7000)

    def _apply(self) -> None:
        script = self.preview.toPlainText().strip()
        if not script:
            return
        ch = self.chapter
        if self.mode.currentData() == "append" and ch.text.strip():
            ch.text = ch.text.rstrip() + "\n\n" + script
        else:
            ch.text = script
        if self._result is not None:
            title, desc, _lines = self._result
            if title and (not ch.title.strip() or re.fullmatch(r"(Épisode|Nouvel épisode)\s*\d*", ch.title.strip())):
                ch.title = title
            if desc and not ch.description.strip():
                ch.description = desc
        self.accept()
