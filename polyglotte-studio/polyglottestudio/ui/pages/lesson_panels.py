"""Onglets de l'éditeur de leçon : vocabulaire et phrases utiles, exercices, questions, résumé et quiz."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QMessageBox,
                               QPlainTextEdit, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...core import languages
from ...core.models import EXERCISES, Chapter, QuizQuestion, VocabItem
from .. import theme
from ..widgets import IconButton, button, label

VOCAB_COLUMNS = ["★", "Type", "Langue apprise", "Prononciation", "Traduction", "Exemple", "Traduction de l'exemple",
                 "Notes"]
_FIELDS = [None, None, "term", "translit", "translation", "example", "example_translation", "notes"]


class VocabPanel(QWidget):
    """Tableau des mots et des phrases utiles d'une leçon."""

    changed = Signal()
    listen_requested = Signal(object)  # VocabItem

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.chapter: Chapter | None = None
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.info = label("", "Hint", wrap=True)
        top.addWidget(self.info, 1)
        add_w = button("Mot", "plus", tooltip="Ajouter un mot")
        add_w.clicked.connect(lambda: self.add("word"))
        add_p = button("Phrase", "plus", tooltip="Ajouter une phrase utile")
        add_p.clicked.connect(lambda: self.add("phrase"))
        self.listen_btn = button("Écouter", "headphones", "primary", tooltip="Écouter le mot sélectionné avec la voix "
                                 "native de la leçon")
        self.listen_btn.clicked.connect(self._listen)
        self.translit_btn = button("Translittérations IA", "sparkles", tooltip="DeepSeek complète la prononciation "
                                   "(pinyin, romaji…) des mots qui n'en ont pas")
        self.translit_btn.clicked.connect(self.ai_translit)
        rm = IconButton("trash", "Supprimer la ligne sélectionnée", 34, 16, color=theme.CURRENT.danger)
        rm.clicked.connect(self.remove)
        up = IconButton("up", "Monter", 34, 16)
        up.clicked.connect(lambda: self.move(-1))
        down = IconButton("down", "Descendre", 34, 16)
        down.clicked.connect(lambda: self.move(1))
        for w in (add_w, add_p, self.translit_btn, self.listen_btn, up, down, rm):
            top.addWidget(w)
        lay.addLayout(top)
        self.table = QTableWidget(0, len(VOCAB_COLUMNS))
        self.table.setHorizontalHeaderLabels(VOCAB_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for c in range(2, len(VOCAB_COLUMNS)):
            hh.setSectionResizeMode(c, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        lay.addWidget(self.table, 1)
        lay.addWidget(label("Les mots sont lus dans la section « Vocabulaire », les phrases dans « Phrases utiles », "
                            "avant le texte de la leçon. Double-cliquez sur ★ pour ajouter aux favoris, sur le type pour "
                            "passer de mot à phrase.", "Faint", wrap=True))

    # -- chargement --------------------------------------------------------------------
    def load(self, chapter: Chapter | None) -> None:
        self.chapter = chapter
        self._loading = True
        self.table.setRowCount(0)
        for it in (chapter.vocab if chapter else []):
            self._append(it)
        self._loading = False
        self._update_info()

    def _append(self, it: VocabItem) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        star = QTableWidgetItem("★" if it.favorite else "☆")
        star.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        star.setForeground(QColor(theme.CURRENT.accent2 if it.favorite else theme.CURRENT.faint))
        star.setData(Qt.UserRole, it.id)
        star.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(r, 0, star)
        kind = QTableWidgetItem("Phrase" if it.kind == "phrase" else "Mot")
        kind.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(r, 1, kind)
        for c, f in enumerate(_FIELDS):
            if f:
                self.table.setItem(r, c, QTableWidgetItem(getattr(it, f)))

    def _by_id(self, item_id: str) -> VocabItem | None:
        if self.chapter is None:
            return None
        return next((v for v in self.chapter.vocab if v.id == item_id), None)

    def _row_item(self, row: int) -> VocabItem | None:
        cell = self.table.item(row, 0)
        return self._by_id(cell.data(Qt.UserRole)) if cell else None

    def _update_info(self) -> None:
        ch = self.chapter
        if ch is None:
            self.info.setText("")
            return
        code, locale = self.ctx.project.target_of(ch)
        lang = languages.get(code)
        self.translit_btn.setVisible(bool(lang and lang.non_latin))
        self.info.setText(f"{len(ch.words())} mot(s) et {len(ch.phrases())} phrase(s) en "
                          f"{languages.locale_name(locale) if locale else languages.language_name(code)}"
                          + (f" — prononciation : {lang.translit}" if lang and lang.translit else ""))

    # -- édition -----------------------------------------------------------------------
    def _item_changed(self, cell: QTableWidgetItem) -> None:
        if self._loading or self.chapter is None:
            return
        it = self._row_item(cell.row())
        field = _FIELDS[cell.column()] if cell.column() < len(_FIELDS) else None
        if it is None or not field:
            return
        value = " ".join(cell.text().split())
        if field == "term":
            value = value.replace("[", "(").replace("]", ")")
        setattr(it, field, value)
        self._update_info()
        self.changed.emit()

    def _double_clicked(self, row: int, col: int) -> None:
        it = self._row_item(row)
        if it is None:
            return
        if col == 0:
            it.favorite = not it.favorite
        elif col == 1:
            it.kind = "word" if it.kind == "phrase" else "phrase"
        else:
            return
        self.load(self.chapter)
        self.table.selectRow(row)
        self.changed.emit()

    def add(self, kind: str = "word") -> None:
        if self.chapter is None:
            return
        it = VocabItem("", kind=kind)
        self.chapter.vocab.append(it)
        self._loading = True
        self._append(it)
        self._loading = False
        r = self.table.rowCount() - 1
        self.table.setCurrentCell(r, 2)
        self.table.editItem(self.table.item(r, 2))
        self._update_info()
        self.changed.emit()

    def remove(self) -> None:
        r = self.table.currentRow()
        it = self._row_item(r)
        if it is None or self.chapter is None:
            return
        self.chapter.vocab = [v for v in self.chapter.vocab if v.id != it.id]
        self.ctx.project.reviews.pop(it.id, None)
        self.load(self.chapter)
        self.table.selectRow(min(r, self.table.rowCount() - 1))
        self.changed.emit()

    def move(self, delta: int) -> None:
        r = self.table.currentRow()
        if self.chapter is None or r < 0 or not (0 <= r + delta < len(self.chapter.vocab)):
            return
        v = self.chapter.vocab
        v[r], v[r + delta] = v[r + delta], v[r]
        self.load(self.chapter)
        self.table.selectRow(r + delta)
        self.changed.emit()

    def _listen(self) -> None:
        it = self._row_item(self.table.currentRow())
        if it is None or not it.term.strip():
            self.ctx.toast("Sélectionnez un mot à écouter.", "info")
            return
        self.listen_requested.emit(it)

    def ai_translit(self) -> None:
        ch = self.chapter
        if ch is None:
            return
        from ...core import ai, lang_ai
        from .. import tasks

        code, _loc = self.ctx.project.target_of(ch)

        def work():
            return lang_ai.fill_transliterations(ai.client_from_settings(), ch.vocab, code)

        def done(n):
            if self.chapter is ch:
                self.load(ch)
            self.changed.emit()
            self.ctx.toast(f"{n} prononciation(s) ajoutée(s)." if n else "Rien à compléter.", "success")

        self.ctx.toast("DeepSeek ajoute les prononciations…", "info", 2500)
        self._task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 7000))


class ExercisesPanel(QWidget):
    """Exercices de la leçon, questions de compréhension, résumé et quiz."""

    changed = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.chapter: Chapter | None = None
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(8)
        ex_row = QHBoxLayout()
        self.custom = QCheckBox("Exercices propres à cette leçon")
        self.custom.setToolTip("Décoché : les exercices réglés pour tout le cours dans Production")
        self.custom.toggled.connect(self._exercises_changed)
        ex_row.addWidget(self.custom)
        ex_row.addStretch(1)
        lay.addLayout(ex_row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        self.ex_boxes: dict[str, QCheckBox] = {}
        for i, (key, text) in enumerate(EXERCISES.items()):
            cb = QCheckBox(text)
            cb.toggled.connect(self._exercises_changed)
            self.ex_boxes[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        lay.addLayout(grid)

        qh = QHBoxLayout()
        qh.addWidget(label("Questions de compréhension (posées après le texte, réponse après un temps de réflexion)",
                           "Muted"), 1)
        add = IconButton("plus", "Ajouter une question", 30, 15)
        add.clicked.connect(self._add_question)
        rm = IconButton("trash", "Supprimer la question sélectionnée", 30, 15)
        rm.clicked.connect(self._remove_question)
        qh.addWidget(add)
        qh.addWidget(rm)
        lay.addLayout(qh)
        self.q_table = QTableWidget(0, 2)
        self.q_table.setHorizontalHeaderLabels(["Question", "Réponse"])
        self.q_table.verticalHeader().setVisible(False)
        self.q_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.q_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.q_table.setMaximumHeight(150)
        self.q_table.itemChanged.connect(self._questions_changed)
        lay.addWidget(self.q_table)

        top = QHBoxLayout()
        top.addWidget(label("Résumé et quiz, lus à la fin de la leçon", "Muted"), 1)
        self.q_count = QSpinBox()
        self.q_count.setRange(1, 10)
        self.q_count.setValue(4)
        self.q_count.setSuffix(" questions")
        self.q_kind = QComboBox()
        for key, text in (("qcm", "Choix multiples"), ("vrai_faux", "Vrai ou faux"), ("ouvert", "Questions ouvertes")):
            self.q_kind.addItem(text, key)
        self.review_btn = button("Résumé et quiz IA", "sparkles", tooltip="DeepSeek rédige le résumé et le quiz à "
                                 "partir de la leçon")
        self.review_btn.clicked.connect(self.ai_review)
        for x in (self.q_count, self.q_kind, self.review_btn):
            top.addWidget(x)
        lay.addLayout(top)
        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setPlaceholderText("Ce qu'il faut retenir : « Retenez que… »")
        self.summary_edit.setMaximumHeight(90)
        self.summary_edit.textChanged.connect(self._summary_changed)
        lay.addWidget(self.summary_edit)
        qz = QHBoxLayout()
        qz.addWidget(label("Quiz", "Muted"), 1)
        addq = IconButton("plus", "Ajouter une question de quiz", 30, 15)
        addq.clicked.connect(self._add_quiz)
        rmq = IconButton("trash", "Supprimer la question de quiz sélectionnée", 30, 15)
        rmq.clicked.connect(self._remove_quiz)
        qz.addWidget(addq)
        qz.addWidget(rmq)
        lay.addLayout(qz)
        self.quiz_table = QTableWidget(0, 4)
        self.quiz_table.setHorizontalHeaderLabels(["Question", "Choix (séparés par « ; »)", "Bonne réponse",
                                                   "Explication"])
        self.quiz_table.verticalHeader().setVisible(False)
        self.quiz_table.setWordWrap(True)
        for c in range(4):
            self.quiz_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
        self.quiz_table.itemChanged.connect(self._quiz_changed)
        lay.addWidget(self.quiz_table, 1)

    # -- chargement --------------------------------------------------------------------
    def load(self, chapter: Chapter | None) -> None:
        self.chapter = chapter
        self._loading = True
        own = chapter is not None and chapter.exercises is not None
        self.custom.setChecked(own)
        active = self.ctx.project.exercises_of(chapter)
        for key, cb in self.ex_boxes.items():
            cb.setChecked(key in active)
            cb.setEnabled(own)
        self.q_table.setRowCount(0)
        for q in (chapter.questions if chapter else []):
            self._append_q(q)
        self.summary_edit.setPlainText(chapter.summary if chapter else "")
        self.quiz_table.setRowCount(0)
        for q in (chapter.quiz if chapter else []):
            self._append_quiz(q)
        self._loading = False

    def _append_q(self, q: QuizQuestion) -> None:
        r = self.q_table.rowCount()
        self.q_table.insertRow(r)
        self.q_table.setItem(r, 0, QTableWidgetItem(q.question))
        self.q_table.setItem(r, 1, QTableWidgetItem(q.answer))

    def _append_quiz(self, q: QuizQuestion) -> None:
        r = self.quiz_table.rowCount()
        self.quiz_table.insertRow(r)
        for c, text in enumerate((q.question, " ; ".join(q.choices), q.answer, q.explanation)):
            self.quiz_table.setItem(r, c, QTableWidgetItem(text))

    # -- édition -----------------------------------------------------------------------
    def _exercises_changed(self, *_a) -> None:
        if self._loading or self.chapter is None:
            return
        own = self.custom.isChecked()
        for cb in self.ex_boxes.values():
            cb.setEnabled(own)
        self.chapter.exercises = [k for k, cb in self.ex_boxes.items() if cb.isChecked()] if own else None
        if not own:
            self._loading = True
            active = self.ctx.project.exercises_of(self.chapter)
            for key, cb in self.ex_boxes.items():
                cb.setChecked(key in active)
            self._loading = False
        self.changed.emit()

    @staticmethod
    def _cells(table: QTableWidget, r: int, n: int) -> list[str]:
        return [(table.item(r, c).text() if table.item(r, c) else "").strip() for c in range(n)]

    def _questions_changed(self, *_a) -> None:
        if self._loading or self.chapter is None:
            return
        out = []
        for r in range(self.q_table.rowCount()):
            q, a = self._cells(self.q_table, r, 2)
            if q:
                out.append(QuizQuestion(q, answer=a))
        self.chapter.questions = out
        self.changed.emit()

    def _add_question(self) -> None:
        if self.chapter is None:
            return
        self._loading = True
        self._append_q(QuizQuestion("Nouvelle question ?"))
        self._loading = False
        self._questions_changed()
        r = self.q_table.rowCount() - 1
        self.q_table.setCurrentCell(r, 0)
        self.q_table.editItem(self.q_table.item(r, 0))

    def _remove_question(self) -> None:
        r = self.q_table.currentRow()
        if r >= 0:
            self.q_table.removeRow(r)
            self._questions_changed()

    def _summary_changed(self) -> None:
        if self._loading or self.chapter is None:
            return
        self.chapter.summary = self.summary_edit.toPlainText().strip()
        self.changed.emit()

    def _quiz_changed(self, *_a) -> None:
        if self._loading or self.chapter is None:
            return
        quiz = []
        for r in range(self.quiz_table.rowCount()):
            cells = self._cells(self.quiz_table, r, 4)
            if cells[0]:
                quiz.append(QuizQuestion(cells[0], [x.strip() for x in cells[1].split(";") if x.strip()], cells[2],
                                         cells[3]))
        self.chapter.quiz = quiz
        self.changed.emit()

    def _add_quiz(self) -> None:
        if self.chapter is None:
            return
        self._loading = True
        self._append_quiz(QuizQuestion("Nouvelle question ?"))
        self._loading = False
        self._quiz_changed()
        r = self.quiz_table.rowCount() - 1
        self.quiz_table.setCurrentCell(r, 0)
        self.quiz_table.editItem(self.quiz_table.item(r, 0))

    def _remove_quiz(self) -> None:
        r = self.quiz_table.currentRow()
        if r >= 0:
            self.quiz_table.removeRow(r)
            self._quiz_changed()

    def ai_review(self) -> None:
        ch = self.chapter
        if ch is None:
            return
        from ...core import ai, course
        from .. import tasks

        text = course.lesson_script(self.ctx.project, ch)
        if not text.strip():
            self.ctx.toast("La leçon est vide.", "warning")
            return
        if (ch.summary.strip() or ch.quiz) and QMessageBox.question(
                self, "Remplacer", "Remplacer le résumé et le quiz actuels de cette leçon ?") != QMessageBox.Yes:
            return
        count, kind = self.q_count.value(), self.q_kind.currentData()
        lang = self.ctx.project.metadata.language or "fr"

        def work():
            return ai.lesson_review(ch.title, text, ai.client_from_settings(), count, kind, lang)

        def done(res):
            ch.summary, ch.quiz = res
            if self.chapter is ch:
                self.load(ch)
            self.review_btn.setEnabled(True)
            self.changed.emit()
            self.ctx.toast(f"Résumé et {len(ch.quiz)} question(s) prêts : relisez-les et corrigez si besoin.",
                           "success")

        def fail(msg, _tb):
            self.review_btn.setEnabled(True)
            self.ctx.toast(msg, "error", 7000)

        self.review_btn.setEnabled(False)
        self.ctx.toast("DeepSeek prépare le résumé et le quiz…", "info", 3000)
        self._task = tasks.run(work, on_done=done, on_error=fail)
