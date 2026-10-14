"""Nouveau cours : langue apprise et accent, langue d'explication, niveau, plan proposé par l'IA."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDialog, QGridLayout, QHBoxLayout, QLineEdit,
                               QSpinBox, QVBoxLayout)

from ...core import languages
from ...core.models import LEVEL_LABELS, LEVELS, Chapter, Project
from ..widgets import button, card_title, label


def language_combo(current: str = "", first: tuple[str, str] | None = None) -> QComboBox:
    """Liste déroulante de toutes les langues, avec recherche au clavier (« jap » → japonais)."""
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    if first:
        combo.addItem(first[1], first[0])
    for lang in languages.sorted_languages():
        text = lang.name if lang.native == lang.name else f"{lang.name} — {lang.native}"
        combo.addItem(text, lang.code)
    comp = combo.completer()
    comp.setFilterMode(Qt.MatchContains)
    comp.setCompletionMode(QCompleter.PopupCompletion)
    combo.setCurrentIndex(max(0, combo.findData(current)))
    return combo


def fill_locales(combo: QComboBox, code: str, current: str = "") -> None:
    combo.blockSignals(True)
    combo.clear()
    lang = languages.get(code)
    for loc, lbl in (lang.locales if lang else ()):
        n = len(languages.EDGE_CATALOG.get(loc, []))
        combo.addItem(f"{lbl} ({n} voix)" if n else lbl, loc)
    combo.setCurrentIndex(max(0, combo.findData(current)))
    combo.setEnabled(combo.count() > 1)
    combo.blockSignals(False)


class NewCourseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nouveau cours de langue")
        self.resize(760, 470)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title("Quelle langue voulez-vous apprendre ?",
                                 "Environ 80 langues et de nombreux accents régionaux, avec des voix natives "
                                 "gratuites. Tout se modifie ensuite (page Langues et voix).", "globe"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(label("Langue apprise", "Muted"), 0, 0)
        self.target = language_combo("en")
        self.target.currentIndexChanged.connect(self._target_changed)
        grid.addWidget(self.target, 0, 1)
        grid.addWidget(label("Accent", "Muted"), 0, 2)
        self.locale = QComboBox()
        grid.addWidget(self.locale, 0, 3)
        grid.addWidget(label("Expliquée en", "Muted"), 1, 0)
        self.explain = language_combo("fr")
        grid.addWidget(self.explain, 1, 1)
        grid.addWidget(label("Niveau", "Muted"), 1, 2)
        self.level = QComboBox()
        for lv in LEVELS:
            self.level.addItem(LEVEL_LABELS[lv], lv)
        grid.addWidget(self.level, 1, 3)
        grid.addWidget(label("Titre du cours", "Muted"), 2, 0)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Anglais pour débutants")
        grid.addWidget(self.title, 2, 1, 1, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        lay.addLayout(grid)
        self.ai_plan = QCheckBox("Proposer le plan du cours avec l'assistant IA (modules et leçons par thème)")
        lay.addWidget(self.ai_plan)
        pr = QHBoxLayout()
        self.modules = QSpinBox()
        self.modules.setRange(1, 12)
        self.modules.setValue(4)
        self.modules.setSuffix(" modules")
        self.lessons = QSpinBox()
        self.lessons.setRange(1, 10)
        self.lessons.setValue(4)
        self.lessons.setSuffix(" leçons par module")
        pr.addSpacing(26)
        pr.addWidget(self.modules)
        pr.addWidget(self.lessons)
        pr.addStretch(1)
        lay.addLayout(pr)
        self.ai_plan.toggled.connect(lambda on: (self.modules.setEnabled(on), self.lessons.setEnabled(on)))
        self.modules.setEnabled(False)
        self.lessons.setEnabled(False)
        self.info = label("", "Hint", wrap=True)
        lay.addWidget(self.info)
        lay.addStretch(1)
        br = QHBoxLayout()
        br.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Créer le cours", "check", "primary")
        ok.clicked.connect(self.accept)
        br.addWidget(cancel)
        br.addWidget(ok)
        lay.addLayout(br)
        self._target_changed()

    def _target_changed(self, *_a) -> None:
        code = self.target.currentData() or "en"
        fill_locales(self.locale, code)
        lang = languages.get(code)
        if lang is None:
            return
        n = sum(len(languages.EDGE_CATALOG.get(loc, [])) for loc, _ in lang.locales)
        offline = [e for e, ok in (("Kokoro", bool(languages.kokoro_voices_for(code))),
                                   ("XTTS", code in languages.XTTS_LANGS)) if ok]
        self.info.setText(f"{lang.name} ({lang.native}) : {n} voix natives Microsoft, {len(lang.locales)} accent(s)"
                          + (f", hors ligne avec {' et '.join(offline)}" if offline else "")
                          + (f". Prononciation écrite : {lang.translit}." if lang.translit else "."))
        self.title.setPlaceholderText(f"{lang.name} — niveau {self.level.currentData()}")

    def build_project(self) -> Project:
        pr = Project()
        m = pr.metadata
        m.target_language = self.target.currentData() or "en"
        m.target_locale = self.locale.currentData() or ""
        m.language = self.explain.currentData() or "fr"
        m.level = self.level.currentData() or "A1"
        lang = languages.get(m.target_language)
        m.title = " ".join(self.title.text().split()) or f"{lang.name if lang else m.target_language} — niveau {m.level}"
        if not self.ai_plan.isChecked():
            pr.chapters = [Chapter(title="Nouvelle leçon", module="Module 1")]
        return pr
