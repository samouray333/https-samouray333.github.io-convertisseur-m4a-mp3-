"""Page Manuscrit : chapitres et éditeur de texte avec balises de mise en scène."""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QSplitter,
                               QVBoxLayout, QWidget)

from ...core.models import Chapter
from ...core.textproc import EMOTION_ALIASES, EMOTION_LABELS, clean_imported_text, find_characters, format_duration
from .. import icons, theme
from ..widgets import Card, EmptyState, IconButton, ToggleSwitch, button, label
from .base import Page


class ScriptHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        p = theme.CURRENT

        def fmt(color, bold=False, italic=False, bg=None):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            f.setFontItalic(italic)
            if bg:
                f.setBackground(QColor(bg))
            return f

        self.rules = [
            (QRegularExpression(r"^#{1,6}\s.*$"), fmt(p.accent, bold=True)),
            (QRegularExpression(r"\[\s*(pause|PAUSE)[^\]]*\]"), fmt(p.info, bold=True, bg=theme.rgba(p.info, 0.12))),
            (QRegularExpression(r"^@[^:\n]{1,40}:"), fmt(p.accent2, bold=True)),
            (QRegularExpression(r"^\[\s*/?\s*(voix|voice)[^\]]*\]"), fmt(p.accent2, bold=True,
                                                                     bg=theme.rgba(p.accent2, 0.12))),
            (QRegularExpression(r"^\s*[—–]\s.*$"), fmt(p.text, italic=True)),
            (QRegularExpression(r"«[^»]*»"), fmt(_soft(p), italic=False)),
            (QRegularExpression(r"^%%.*$"), fmt(p.faint, italic=True)),
            (QRegularExpression(r"\[\s*/?\s*(" + "|".join(EMOTION_ALIASES) + r")\s*\]",
                                QRegularExpression.CaseInsensitiveOption),
             fmt(p.warning, bold=True, bg=theme.rgba(p.warning, 0.12))),
        ]

    def highlightBlock(self, text):
        for rx, f in self.rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), f)


def _soft(p) -> str:
    c = QColor(p.text)
    a = QColor(p.accent)
    return QColor((c.red() * 3 + a.red()) // 4, (c.green() * 3 + a.green()) // 4, (c.blue() * 3 + a.blue()) // 4).name()


class FindBar(QFrame):
    def __init__(self, editor: QPlainTextEdit, on_change):
        super().__init__()
        self.editor = editor
        self.on_change = on_change
        self.setObjectName("CardFlat")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        self.find = QLineEdit()
        self.find.setPlaceholderText("Rechercher…")
        self.repl = QLineEdit()
        self.repl.setPlaceholderText("Remplacer par…")
        self.case = ToggleSwitch("Respecter la casse")
        nxt = button("Suivant", "chevron-down")
        one = button("Remplacer")
        allb = button("Tout remplacer", kind="primary")
        close = IconButton("x", "Fermer", 30, 16)
        for w in (self.find, self.repl, self.case, nxt, one, allb, close):
            lay.addWidget(w)
        self.find.returnPressed.connect(self.next)
        nxt.clicked.connect(self.next)
        one.clicked.connect(self.replace_one)
        allb.clicked.connect(self.replace_all)
        close.clicked.connect(self.hide)

    def _flags(self):
        return QTextDocument.FindCaseSensitively if self.case.isChecked() else QTextDocument.FindFlag(0)

    def next(self) -> bool:
        text = self.find.text()
        if not text:
            return False
        if self.editor.find(text, self._flags()):
            return True
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.Start)
        self.editor.setTextCursor(cur)
        return self.editor.find(text, self._flags())

    def replace_one(self) -> None:
        cur = self.editor.textCursor()
        sel = cur.selectedText()
        if sel and (sel == self.find.text() or (not self.case.isChecked() and sel.lower() == self.find.text().lower())):
            cur.insertText(self.repl.text())
        self.next()

    def replace_all(self) -> None:
        text = self.find.text()
        if not text:
            return
        flags = 0 if self.case.isChecked() else re.IGNORECASE
        new, n = re.subn(re.escape(text), lambda _m: self.repl.text(), self.editor.toPlainText(), flags=flags)
        if n:
            cur = self.editor.textCursor()
            cur.select(QTextCursor.Document)
            cur.insertText(new)
        self.on_change(f"{n} remplacement(s) effectué(s)")


class ManuscriptPage(Page):
    name = "manuscript"

    def __init__(self, ctx):
        super().__init__(ctx, "Manuscrit", "Relisez, découpez et mettez en scène votre texte avant la production.")
        self._loading = False
        self._current: Chapter | None = None

        self.voice_combo_narr = QComboBox()
        self.voice_combo_narr.setMinimumWidth(240)
        self.voice_combo_narr.setToolTip("Voix principale du livre")
        self.voice_combo_narr.currentIndexChanged.connect(self._narrator_changed)
        self.header.add_action(label("Narrateur :", "Muted"))
        self.header.add_action(self.voice_combo_narr)
        lex = button("Lexique", "dictionary", tooltip="Dictionnaire de prononciation du projet")
        lex.clicked.connect(self._open_lexicon)
        self.header.add_action(lex)
        go = button("Produire", "wave", "primary")
        go.clicked.connect(lambda: self.ctx.navigate("production"))
        self.header.add_action(go)

        import_btn = button("Importer un document", "file-plus", "primary")
        import_btn.clicked.connect(lambda: self.ctx.window.import_document_dialog())
        self.empty = EmptyState("book", "Aucun manuscrit",
                                "Importez un document Word, PDF, EPUB ou texte depuis l'accueil pour commencer.",
                                import_btn)
        self.body.addWidget(self.empty, 1)

        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.body.addWidget(self.split, 1)

        # ---- liste des chapitres
        left = Card(margins=(12, 14, 12, 12), spacing=8)
        left.setMinimumWidth(270)
        left.setMaximumWidth(420)
        tl = QHBoxLayout()
        tl.addWidget(label("Chapitres", "SectionTitle"), 1)
        self.count_lbl = label("", "Faint")
        tl.addWidget(self.count_lbl)
        left.add(tl)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setStyleSheet("QListWidget { border: none; background: transparent; padding: 0; }")
        self.list.currentRowChanged.connect(self._select_row)
        self.list.itemChanged.connect(self._item_changed)
        self.list.model().rowsMoved.connect(self._rows_moved)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        left.add(self.list)
        tb = QHBoxLayout()
        tb.setSpacing(2)
        for ic, tip, fn in [("plus", "Ajouter un chapitre", self.add_chapter),
                            ("trash", "Supprimer le chapitre", self.delete_chapter),
                            ("up", "Monter", lambda: self.move(-1)), ("down", "Descendre", lambda: self.move(1)),
                            ("layers", "Fusionner avec le suivant", self.merge_next),
                            ("scissors", "Couper le chapitre au curseur", self.split_at_cursor)]:
            b = IconButton(ic, tip, 32, 16)
            b.clicked.connect(fn)
            tb.addWidget(b)
        tb.addStretch(1)
        left.add(tb)
        self.split.addWidget(left)

        # ---- éditeur
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 0, 0, 0)
        rl.setSpacing(10)
        top = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Titre du chapitre")
        self.title_edit.setStyleSheet("font-size: 15pt; font-weight: 700; padding: 8px 12px;")
        self.title_edit.textEdited.connect(self._title_changed)
        top.addWidget(self.title_edit, 1)
        self.chapter_voice = QComboBox()
        self.chapter_voice.setMinimumWidth(220)
        self.chapter_voice.setToolTip("Voix utilisée pour ce chapitre")
        self.chapter_voice.currentIndexChanged.connect(self._chapter_voice_changed)
        top.addWidget(self.chapter_voice)
        rl.addLayout(top)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        clean = button("Nettoyer", "sparkles", tooltip="Répare césures, retours à la ligne, numéros de page…")
        clean.clicked.connect(self.clean_text)
        pause = button("Pause", "pause-mark", tooltip="Insère une pause [pause 1s]")
        pause.clicked.connect(lambda: self.insert("[pause 1s]"))
        heading = button("Titre", "type", tooltip="Transforme la ligne en intertitre (#)")
        heading.clicked.connect(self.make_heading)
        self.emo_btn = button("Émotion", "sparkles", tooltip="Ton du paragraphe : joyeux, triste, chuchoté…")
        emo_menu = QMenu(self)
        for key, lbl in EMOTION_LABELS.items():
            emo_menu.addAction(lbl, lambda k=key: self._tag_emotion(k))
        emo_menu.addSeparator()
        emo_menu.addAction("Neutre (retirer)", lambda: self._tag_emotion(""))
        self.emo_btn.setMenu(emo_menu)
        self.role_btn = button("Réplique", "users", tooltip="Attribue le paragraphe à un personnage (@Nom:)")
        self.role_menu = QMenu(self)
        self.role_menu.aboutToShow.connect(self._fill_roles)
        self.role_btn.setMenu(self.role_menu)
        ia = button("Assistant IA", "sparkles", tooltip="DeepSeek repère qui parle, les émotions et les noms difficiles "
                    "à prononcer ; vous validez chaque proposition")
        ia.clicked.connect(self.ai_assistant)
        preview = button("Aperçu", "eye",
                         tooltip="Aperçu de lecture : montre exactement ce qui sera lu, segment par segment")
        preview.clicked.connect(self.reading_preview)
        listen = button("Écouter", "headphones", "primary", tooltip="Écoute la sélection (ou le paragraphe)")
        listen.clicked.connect(self.listen_selection)
        find = IconButton("search", "Rechercher / remplacer (Ctrl+F)", 36, 18)
        find.clicked.connect(self.toggle_find)
        for w in (clean, pause, heading, self.role_btn, self.emo_btn, ia, preview):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(find)
        bar.addWidget(listen)
        rl.addLayout(bar)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText("Le texte du chapitre…")
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.editor.textChanged.connect(self._text_changed)
        self.highlighter = ScriptHighlighter(self.editor.document())
        self.find_bar = FindBar(self.editor, lambda m: self.ctx.toast(m, "success"))
        self.find_bar.hide()
        rl.addWidget(self.find_bar)
        rl.addWidget(self.editor, 1)
        from PySide6.QtGui import QShortcut, QKeySequence

        QShortcut(QKeySequence("Ctrl+F"), self.editor, activated=self.toggle_find)

        status = QHBoxLayout()
        self.stats = label("", "Hint")
        status.addWidget(self.stats, 1)
        self.help = label("Astuces : « # Titre », « [pause 2s] », « @Marie: réplique », « [joyeux] », "
                          "« [voix:Paul] … [/voix] », « %% commentaire »", "Faint")
        status.addWidget(self.help)
        rl.addLayout(status)
        self.split.addWidget(right)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([300, 900])

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._commit_text)
        self.ctx.voices_changed.connect(self._fill_voice_combos)

    # -- synchronisation projet --------------------------------------------------------
    def on_project_changed(self) -> None:
        self._current = None
        self._fill_voice_combos()
        self._reload_list()

    def on_show(self) -> None:
        self._fill_voice_combos()
        self._refresh_items()

    def _has_project(self) -> bool:
        return bool(self.ctx.project.chapters)

    def _reload_list(self, select: int = 0) -> None:
        pr = self.ctx.project
        has = self._has_project()
        self.empty.setVisible(not has)
        self.split.setVisible(has)
        self._loading = True
        self.list.clear()
        for ch in pr.chapters:
            it = QListWidgetItem()
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setData(Qt.UserRole, ch.id)
            self.list.addItem(it)
        self._loading = False
        self._refresh_items()
        if pr.chapters:
            self.list.setCurrentRow(max(0, min(select, len(pr.chapters) - 1)))

    def _refresh_items(self) -> None:
        pr = self.ctx.project
        self._loading = True
        for i in range(self.list.count()):
            it = self.list.item(i)
            ch = pr.chapter_by_id(it.data(Qt.UserRole))
            if ch is None:
                continue
            words = ch.word_count()
            it.setText(f"{ch.title}\n{words:,} mots · ≈ {format_duration(words / 155 * 60)}".replace(",", " "))
            it.setCheckState(Qt.Checked if ch.include else Qt.Unchecked)
            it.setForeground(QColor(theme.CURRENT.text if ch.include else theme.CURRENT.faint))
            it.setToolTip("Décochez pour exclure ce chapitre du livre audio")
        self._loading = False
        inc = pr.included_chapters()
        self.count_lbl.setText(f"{len(inc)}/{len(pr.chapters)}")

    def _fill_voice_combos(self) -> None:
        pr = self.ctx.project
        voices = self.ctx.library.all()
        for combo, current, first in ((self.voice_combo_narr, pr.narrator_voice_id, None),
                                      (self.chapter_voice, self._current.voice_id if self._current else "",
                                       "Voix du narrateur")):
            combo.blockSignals(True)
            combo.clear()
            if first:
                combo.addItem(icons.icon("user", theme.CURRENT.muted, 16), first, "")
            for v in voices:
                ic = "mic" if v.is_clone else "user"
                combo.addItem(icons.icon(ic, v.color, 16), v.name, v.id)
            idx = combo.findData(current)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)

    def _narrator_changed(self, _i: int) -> None:
        vid = self.voice_combo_narr.currentData()
        if vid and vid != self.ctx.project.narrator_voice_id:
            self.ctx.project.narrator_voice_id = vid
            self.ctx.mark_dirty()

    def _chapter_voice_changed(self, _i: int) -> None:
        if self._loading or self._current is None:
            return
        self._current.voice_id = self.chapter_voice.currentData() or ""
        self.ctx.mark_dirty()

    def _select_row(self, row: int) -> None:
        self._commit_text()
        pr = self.ctx.project
        if row < 0 or row >= self.list.count():
            self._current = None
            return
        ch = pr.chapter_by_id(self.list.item(row).data(Qt.UserRole))
        self._current = ch
        self._loading = True
        self.title_edit.setText(ch.title if ch else "")
        self.editor.setPlainText(ch.text if ch else "")
        idx = self.chapter_voice.findData(ch.voice_id if ch else "")
        self.chapter_voice.setCurrentIndex(max(0, idx))
        self._loading = False
        self._update_stats()

    def _item_changed(self, it: QListWidgetItem) -> None:
        if self._loading:
            return
        ch = self.ctx.project.chapter_by_id(it.data(Qt.UserRole))
        if ch is not None:
            inc = it.checkState() == Qt.Checked
            if inc != ch.include:
                ch.include = inc
                self.ctx.mark_dirty()
                self._refresh_items()

    def _rows_moved(self, *args) -> None:
        pr = self.ctx.project
        order = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        by_id = {c.id: c for c in pr.chapters}
        pr.chapters = [by_id[i] for i in order if i in by_id]
        self.ctx.mark_dirty()

    def _title_changed(self, text: str) -> None:
        if self._current is not None:
            self._current.title = text
            self.ctx.mark_dirty()
            self._refresh_items()

    def _text_changed(self) -> None:
        if self._loading:
            return
        self._save_timer.start(400)
        self._update_stats()

    def _commit_text(self) -> None:
        if self._current is None or self._loading:
            return
        text = self.editor.toPlainText()
        if text != self._current.text:
            self._current.text = text
            self.ctx.mark_dirty()
            self._refresh_items()

    def _update_stats(self) -> None:
        text = self.editor.toPlainText()
        words = len(text.split())
        chars = find_characters(text)
        tot = self.ctx.project
        s = f"{words:,} mots · ≈ {format_duration(words / 155 * 60)} pour ce chapitre".replace(",", " ")
        s += f"  ·  Livre : ≈ {format_duration(tot.estimated_minutes() * 60)}"
        if chars:
            s += f"  ·  Personnages : {', '.join(chars[:6])}"
        self.stats.setText(s)

    # -- actions sur les chapitres -----------------------------------------------------
    def _row(self) -> int:
        return self.list.currentRow()

    def add_chapter(self) -> None:
        self._commit_text()
        pr = self.ctx.project
        row = self._row() + 1 if self._row() >= 0 else len(pr.chapters)
        pr.chapters.insert(row, Chapter(title=f"Chapitre {len(pr.chapters) + 1}", text=""))
        self.ctx.mark_dirty()
        self._reload_list(row)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def delete_chapter(self) -> None:
        row = self._row()
        pr = self.ctx.project
        if row < 0:
            return
        ch = pr.chapters[row]
        if QMessageBox.question(self, "Supprimer le chapitre",
                                f"Supprimer définitivement « {ch.title} » ?") != QMessageBox.Yes:
            return
        del pr.chapters[row]
        self._current = None
        self.ctx.mark_dirty()
        self._reload_list(row)

    def move(self, delta: int) -> None:
        self._commit_text()
        row = self._row()
        pr = self.ctx.project
        new = row + delta
        if row < 0 or not (0 <= new < len(pr.chapters)):
            return
        pr.chapters[row], pr.chapters[new] = pr.chapters[new], pr.chapters[row]
        self.ctx.mark_dirty()
        self._reload_list(new)

    def merge_next(self) -> None:
        self._commit_text()
        row = self._row()
        pr = self.ctx.project
        if row < 0 or row + 1 >= len(pr.chapters):
            return
        a, b = pr.chapters[row], pr.chapters[row + 1]
        a.text = (a.text.rstrip() + "\n\n# " + b.title + "\n\n" + b.text.lstrip()).strip()
        del pr.chapters[row + 1]
        self.ctx.mark_dirty()
        self._reload_list(row)
        self.ctx.toast(f"« {b.title} » fusionné dans « {a.title} »", "success")

    def split_at_cursor(self) -> None:
        if self._current is None:
            return
        self._commit_text()
        pos = self.editor.textCursor().position()
        text = self.editor.toPlainText()
        before, after = text[:pos].rstrip(), text[pos:].lstrip()
        if not after:
            self.ctx.toast("Placez le curseur à l'endroit où commence le nouveau chapitre.", "warning")
            return
        title = "Nouveau chapitre"
        first = after.split("\n", 1)[0].strip()
        if first.startswith("#") or (len(first) < 80 and not first.endswith((".", ",", ";"))):
            title = first.lstrip("#").strip() or title
            after = after.split("\n", 1)[1].lstrip() if "\n" in after else ""
        pr = self.ctx.project
        row = self._row()
        self._current.text = before
        pr.chapters.insert(row + 1, Chapter(title=title, text=after, voice_id=self._current.voice_id))
        self.ctx.mark_dirty()
        self._reload_list(row + 1)

    def _list_menu(self, pos) -> None:
        m = QMenu(self)
        m.addAction(icons.icon("plus", theme.CURRENT.text, 16), "Ajouter un chapitre", self.add_chapter)
        m.addAction(icons.icon("layers", theme.CURRENT.text, 16), "Fusionner avec le suivant", self.merge_next)
        m.addAction(icons.icon("scissors", theme.CURRENT.text, 16), "Découper aux intertitres (#)",
                    self.split_on_headings)
        m.addAction(icons.icon("edit", theme.CURRENT.text, 16), "Renommer…", self.rename)
        m.addSeparator()
        m.addAction(icons.icon("check", theme.CURRENT.text, 16), "Tout inclure", lambda: self._include_all(True))
        m.addAction(icons.icon("x", theme.CURRENT.text, 16), "Tout exclure", lambda: self._include_all(False))
        m.addSeparator()
        m.addAction(icons.icon("trash", theme.CURRENT.danger, 16), "Supprimer", self.delete_chapter)
        m.exec(self.list.mapToGlobal(pos))

    def _include_all(self, on: bool) -> None:
        for c in self.ctx.project.chapters:
            c.include = on
        self.ctx.mark_dirty()
        self._refresh_items()

    def rename(self) -> None:
        if self._current is None:
            return
        name, ok = QInputDialog.getText(self, "Renommer", "Titre du chapitre :", text=self._current.title)
        if ok and name.strip():
            self._current.title = name.strip()
            self.title_edit.setText(self._current.title)
            self.ctx.mark_dirty()
            self._refresh_items()

    def split_on_headings(self) -> None:
        if self._current is None:
            return
        self._commit_text()
        parts = re.split(r"(?m)^#\s+(.+)$", self._current.text)
        if len(parts) < 3:
            self.ctx.toast("Aucun intertitre « # » trouvé dans ce chapitre.", "warning")
            return
        pr = self.ctx.project
        row = self._row()
        head = parts[0].strip()
        new = []
        for i in range(1, len(parts), 2):
            new.append(Chapter(title=parts[i].strip(), text=parts[i + 1].strip(), voice_id=self._current.voice_id))
        if head:
            self._current.text = head
            pr.chapters[row + 1:row + 1] = new
        else:
            pr.chapters[row:row + 1] = new
        self.ctx.mark_dirty()
        self._reload_list(row)
        self.ctx.toast(f"{len(new)} chapitres créés", "success")

    # -- actions sur le texte ----------------------------------------------------------
    def insert(self, snippet: str) -> None:
        cur = self.editor.textCursor()
        cur.insertText(snippet)
        self.editor.setFocus()

    def make_heading(self) -> None:
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.StartOfBlock)
        line = cur.block().text()
        if not line.startswith("#"):
            cur.insertText("# ")
        self.editor.setFocus()

    def _fill_roles(self) -> None:
        self.role_menu.clear()
        names = list(dict.fromkeys(list(self.ctx.project.cast.keys()) + find_characters(self.editor.toPlainText())))
        for n in names:
            self.role_menu.addAction(icons.icon("user", theme.CURRENT.accent2, 16), n, lambda n=n: self._tag_role(n))
        if names:
            self.role_menu.addSeparator()
        self.role_menu.addAction(icons.icon("plus", theme.CURRENT.text, 16), "Nouveau personnage…", self._new_role)
        self.role_menu.addAction(icons.icon("users", theme.CURRENT.text, 16), "Gérer la distribution…",
                                 lambda: (self.ctx.navigate("voices"), self.ctx.window.pages["voices"].show_cast()))

    def _tag_emotion(self, emotion: str) -> None:
        """Ajoute (ou remplace) une balise d'émotion au début du paragraphe courant."""
        import re as _re

        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.StartOfBlock)
        line = cur.block().text()
        prefix = ""
        m = _re.match(r"^@[^:\n]{1,40}:\s*", line)
        if m:
            prefix = m.group(0)
            cur.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, len(prefix))
        rest = line[len(prefix):]
        em = _re.match(r"^\[\s*(?:émotion\s*[:=]\s*)?(" + "|".join(EMOTION_ALIASES) + r")\s*\]\s*", rest, _re.I)
        if em:
            cur.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, em.end())
        cur.insertText(f"[{emotion}] " if emotion else "")
        self.editor.setFocus()

    def _new_role(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau personnage", "Nom du personnage :")
        if ok and name.strip():
            self._tag_role(name.strip())

    def _tag_role(self, name: str) -> None:
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.StartOfBlock)
        line = cur.block().text()
        m = re.match(r"^@[^:\n]{1,40}:\s*", line)
        if m:
            cur.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, m.end())
        cur.insertText(f"@{name}: ")
        self.editor.setFocus()

    def clean_text(self) -> None:
        if self._current is None:
            return
        old = self.editor.toPlainText()
        new = clean_imported_text(old)
        if new == old:
            self.ctx.toast("Le texte est déjà propre.", "success")
            return
        cur = self.editor.textCursor()
        cur.select(QTextCursor.Document)
        cur.insertText(new)
        self.ctx.toast("Texte nettoyé (Ctrl+Z pour annuler).", "success")

    def toggle_find(self) -> None:
        self.find_bar.setVisible(not self.find_bar.isVisible())
        if self.find_bar.isVisible():
            sel = self.editor.textCursor().selectedText()
            if sel:
                self.find_bar.find.setText(sel)
            self.find_bar.find.setFocus()
            self.find_bar.find.selectAll()

    def _selection_or_paragraph(self) -> str:
        cur = self.editor.textCursor()
        text = cur.selectedText().replace(" ", "\n")
        if not text.strip():
            text = cur.block().text()
        return text.strip()

    def listen_selection(self) -> None:
        text = self._selection_or_paragraph()
        if not text:
            self.ctx.toast("Sélectionnez un passage à écouter.", "warning")
            return
        from ...core.textproc import CHARACTER_LINE_RE

        voice = None
        m = CHARACTER_LINE_RE.match(text)
        if m:
            vid = next((v for k, v in self.ctx.project.cast.items() if k.lower() == m.group(1).strip().lower()), "")
            voice = self.ctx.library.get(vid)
            text = m.group(2)
        text = re.sub(r"^#+\s*", "", text)
        if voice is None:
            vid = (self._current.voice_id if self._current else "") or self.ctx.project.narrator_voice_id
            voice = self.ctx.library.get(vid) or (self.ctx.library.all() or [None])[0]
        if voice is None:
            self.ctx.toast("Aucune voix disponible.", "error")
            return
        self.ctx.preview_voice(voice, text)

    def ai_assistant(self) -> None:
        if self._current is None:
            return
        self._commit_text()
        from ..dialogs.ai_annotate import AIAnnotateDialog

        if AIAnnotateDialog(self.ctx, self._current, self).exec():
            self._loading = True
            self.editor.setPlainText(self._current.text)
            self._loading = False
            self._update_stats()
            self._refresh_items()

    def reading_preview(self) -> None:
        if self._current is None:
            return
        self._commit_text()
        from ..dialogs.reading_preview import ReadingPreviewDialog

        ReadingPreviewDialog(self.ctx, self._current, self).exec()

    def _open_lexicon(self) -> None:
        from ..dialogs.lexicon import LexiconDialog

        dlg = LexiconDialog(self.ctx, self)
        if dlg.exec():
            self.ctx.mark_dirty()
