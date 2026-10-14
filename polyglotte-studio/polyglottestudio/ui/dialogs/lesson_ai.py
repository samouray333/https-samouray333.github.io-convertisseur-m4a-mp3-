"""Création d'une leçon par l'assistant DeepSeek : langue, niveau, thème et contenus voulus."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QSpinBox, QVBoxLayout)

from ...config import settings
from ...core import languages, lang_ai
from ...core.models import LEVEL_LABELS, LEVELS
from ...core.secrets import protect, unprotect
from .. import tasks
from ..widgets import Card, button, card_title, label


class AIKeyCard(Card):
    """Encadré pour saisir la clé DeepSeek (masqué si elle est déjà enregistrée, y compris dans AudioLivre Studio)."""

    def __init__(self, ctx):
        super().__init__(obj="CardFlat", margins=(14, 12, 14, 12))
        self.ctx = ctx
        self.add(label("Collez votre clé API DeepSeek (platform.deepseek.com → API keys). Elle est enregistrée "
                       "chiffrée sur cet ordinateur et partagée avec les autres applications du studio.", "Hint",
                       wrap=True))
        kr = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("sk-…")
        save = button("Enregistrer la clé", "save")
        save.clicked.connect(self._save)
        kr.addWidget(self.key, 1)
        kr.addWidget(save)
        self.add(kr)
        self.setVisible(not unprotect(settings().get("ai_key", "")))

    def _save(self) -> None:
        k = self.key.text().strip()
        if k:
            settings().set("ai_key", protect(k))
            self.hide()
            self.ctx.toast("Clé DeepSeek enregistrée.", "success")


class LessonAIDialog(QDialog):
    def __init__(self, ctx, chapter, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.chapter = chapter
        self._task = None
        pr = ctx.project
        code, locale = pr.target_of(chapter)
        self.setWindowTitle("Créer la leçon avec l'IA")
        self.resize(860, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title(f"Leçon de {languages.locale_name(locale) if locale else languages.language_name(code)}"
                                 f" — expliquée en {languages.language_name(pr.metadata.language).lower()}",
                                 "DeepSeek écrit la leçon pour l'écoute : vocabulaire avec traductions et exemples, "
                                 "phrases utiles, dialogue entre locuteurs natifs, petite histoire, point de "
                                 "grammaire, translittérations, questions et quiz. Tout reste modifiable.", "sparkles"))
        self.key_card = AIKeyCard(ctx)
        lay.addWidget(self.key_card)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(label("Niveau", "Muted"), 0, 0)
        self.level = QComboBox()
        for lv in LEVELS:
            self.level.addItem(LEVEL_LABELS[lv], lv)
        self.level.setCurrentIndex(max(0, self.level.findData(pr.level_of(chapter))))
        grid.addWidget(self.level, 0, 1)
        grid.addWidget(label("Thème", "Muted"), 0, 2)
        self.theme = QComboBox()
        self.theme.setEditable(True)
        self.theme.addItems(lang_ai.THEMES)
        self.theme.setCurrentText(chapter.theme or (chapter.title if chapter.title != "Nouvelle leçon" else
                                                    lang_ai.THEMES[0]))
        grid.addWidget(self.theme, 0, 3)
        self.n_words = QSpinBox()
        self.n_words.setRange(0, 40)
        self.n_words.setValue(10)
        self.n_words.setSuffix(" mots")
        self.n_phrases = QSpinBox()
        self.n_phrases.setRange(0, 20)
        self.n_phrases.setValue(6)
        self.n_phrases.setSuffix(" phrases")
        self.n_questions = QSpinBox()
        self.n_questions.setRange(0, 10)
        self.n_questions.setValue(3)
        self.n_questions.setSuffix(" questions")
        self.n_quiz = QSpinBox()
        self.n_quiz.setRange(0, 10)
        self.n_quiz.setValue(4)
        self.n_quiz.setSuffix(" quiz")
        grid.addWidget(label("Quantités", "Muted"), 1, 0)
        row = QHBoxLayout()
        for w in (self.n_words, self.n_phrases, self.n_questions, self.n_quiz):
            row.addWidget(w)
        row.addStretch(1)
        grid.addLayout(row, 1, 1, 1, 3)
        lay.addLayout(grid)

        parts = Card(obj="CardFlat", margins=(14, 12, 14, 12))
        parts.add(label("Contenu de la leçon", "Muted"))
        pg = QGridLayout()
        self.parts: dict[str, QCheckBox] = {}
        for i, (key, text) in enumerate(lang_ai.CONTENT_PARTS.items()):
            cb = QCheckBox(text)
            cb.setChecked(key in lang_ai.DEFAULT_PARTS)
            self.parts[key] = cb
            pg.addWidget(cb, i // 3, i % 3)
        parts.add(pg)
        lay.addWidget(parts)
        lay.addWidget(label("Indications (facultatif)", "Muted"))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Exemple : dialogue entre un client et une serveuse dans un café de Mexico ; "
                                      "insister sur « quisiera » et les nombres de 1 à 20.")
        self.notes.setMaximumHeight(90)
        lay.addWidget(self.notes)
        self.replace = QCheckBox("Remplacer le contenu actuel de la leçon (sinon, ajouter à la suite)")
        self.replace.setChecked(not (chapter.text.strip() or chapter.vocab))
        lay.addWidget(self.replace)
        self.status = label("", "Hint", wrap=True)
        lay.addWidget(self.status)
        lay.addStretch(1)
        br = QHBoxLayout()
        br.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        self.go = button("Créer la leçon", "sparkles", "primary")
        self.go.clicked.connect(self.generate)
        br.addWidget(cancel)
        br.addWidget(self.go)
        lay.addLayout(br)

    def generate(self) -> None:
        from ...core import ai

        pr, ch = self.ctx.project, self.chapter
        parts = [k for k, cb in self.parts.items() if cb.isChecked()]
        theme = " ".join(self.theme.currentText().split()) or lang_ai.THEMES[0]
        level = self.level.currentData()
        notes = self.notes.toPlainText()
        counts = (self.n_words.value(), self.n_phrases.value(), self.n_questions.value(), self.n_quiz.value())
        replace = self.replace.isChecked()
        if level != pr.level_of(ch):
            ch.level = level

        def work():
            return lang_ai.generate_lesson(ai.client_from_settings(), pr, ch, theme, parts, *counts, notes=notes)

        def done(content):
            lang_ai.apply_lesson(pr, ch, content, replace=replace, theme=theme)
            self.ctx.toast(f"Leçon « {ch.title} » créée : {len(ch.words())} mots, {len(ch.phrases())} phrases. "
                           "Relisez-la, puis écoutez-la ou produisez-la.", "success", 7000)
            self.accept()

        def fail(msg, _tb):
            self.go.setEnabled(True)
            self.status.setText(msg)

        self.go.setEnabled(False)
        self.status.setText("DeepSeek écrit la leçon… (20 à 60 secondes)")
        self._task = tasks.run(work, on_done=done, on_error=fail)
