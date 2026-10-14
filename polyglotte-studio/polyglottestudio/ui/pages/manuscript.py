"""Page Leçons : modules et leçons, éditeur du script (balises de langue et de mise en scène), vocabulaire,
exercices, résumé et quiz."""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QSplitter,
                               QTabWidget, QVBoxLayout, QWidget)

from ...core import course, languages, srs
from ...core.models import LEVELS, Chapter
from ...core.textproc import (EMOTION_ALIASES, EMOTION_LABELS, EMPHASIS_RE, RATE_ALIASES, clean_imported_text, find_characters,
                              format_duration)
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
            # balises de langue : [en], [es-MX], [/es], [/]
            (QRegularExpression(r"\[\s*/?\s*(?:[a-zA-Z]{2,3}(?:[-_][A-Za-z0-9]{2,9}){0,2})?\s*\]"),
             fmt(p.accent2, bold=True, bg=theme.rgba(p.accent2, 0.18))),
            (QRegularExpression(r"^#{1,6}\s.*$"), fmt(p.accent, bold=True)),
            (QRegularExpression(r"\[\s*r[ée]flexion[^\]]*\]", QRegularExpression.CaseInsensitiveOption),
             fmt(p.success, bold=True, bg=theme.rgba(p.success, 0.16))),
            (QRegularExpression(r"\[\s*(pause|PAUSE)[^\]]*\]"), fmt(p.info, bold=True, bg=theme.rgba(p.info, 0.12))),
            (QRegularExpression(r"\[\s*(son|bruitage|effet|virgule|jingle)\b[^\]]*\]",
                                QRegularExpression.CaseInsensitiveOption),
             fmt(p.accent, bold=True, bg=theme.rgba(p.accent, 0.16))),
            (QRegularExpression(r"\[\s*chapitre\s*[:=][^\]]*\]", QRegularExpression.CaseInsensitiveOption),
             fmt(p.success, bold=True, bg=theme.rgba(p.success, 0.14))),
            (QRegularExpression(r"\[\s*(prise|par[- ]dessus|chevauche\w*)[^\]]*\]",
                                QRegularExpression.CaseInsensitiveOption),
             fmt(p.accent2, bold=True, bg=theme.rgba(p.accent2, 0.16))),
            (QRegularExpression(r"^@[^:\n]{1,40}:"), fmt(p.accent2, bold=True)),
            (QRegularExpression(r"^\[\s*/?\s*(voix|voice)[^\]]*\]"), fmt(p.accent2, bold=True,
                                                                     bg=theme.rgba(p.accent2, 0.12))),
            (QRegularExpression(r"^\s*[—–]\s.*$"), fmt(p.text, italic=True)),
            (QRegularExpression(r"«[^»]*»"), fmt(_soft(p), italic=False)),
            (QRegularExpression(r"^%%.*$"), fmt(p.faint, italic=True)),
            (QRegularExpression(r"\[\s*/?\s*(" + "|".join(EMOTION_ALIASES) + r")\s*\]",
                                QRegularExpression.CaseInsensitiveOption),
             fmt(p.warning, bold=True, bg=theme.rgba(p.warning, 0.12))),
            (QRegularExpression(r"\[\s*/?\s*(?:débit\s*[:=]\s*)?(" + "|".join(RATE_ALIASES) + r")\s*\]",
                                QRegularExpression.CaseInsensitiveOption),
             fmt(p.success, bold=True, bg=theme.rgba(p.success, 0.12))),
            (QRegularExpression(r"(?<![\w*])\*(?![\s*])[^*\n]{1,60}?(?<!\s)\*(?![\w*])"), fmt(p.accent, bold=True)),
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
        super().__init__(ctx, "Leçons", "Vocabulaire, phrases utiles, dialogue, histoire, grammaire et exercices : "
                         "les passages dans la langue apprise s'écrivent entre balises, « [es]¿Qué tal?[/es] ».")
        self._loading = False
        self._current: Chapter | None = None

        self.voice_combo_narr = QComboBox()
        self.voice_combo_narr.setMinimumWidth(240)
        self.voice_combo_narr.setToolTip("Voix d'explication : lit les consignes, traductions et explications")
        self.voice_combo_narr.currentIndexChanged.connect(self._narrator_changed)
        self.header.add_action(label("Voix d'explication :", "Muted"))
        self.header.add_action(self.voice_combo_narr)
        write = button("Créer avec l'IA", "sparkles", tooltip="DeepSeek écrit la leçon selon la langue, le niveau et "
                       "le thème : vocabulaire, phrases, dialogue, histoire, grammaire, questions et quiz")
        write.clicked.connect(self.ai_lesson)
        self.header.add_action(write)
        lex = button("Lexique", "dictionary", tooltip="Dictionnaire de prononciation du projet")
        lex.clicked.connect(self._open_lexicon)
        self.header.add_action(lex)
        go = button("Produire", "wave", "primary")
        go.clicked.connect(lambda: self.ctx.navigate("production"))
        self.header.add_action(go)

        import_btn = button("Importer un document", "file-plus", "primary")
        import_btn.clicked.connect(lambda: self.ctx.window.import_document_dialog())
        self.empty = EmptyState("globe", "Aucune leçon",
                                "Créez un nouveau cours depuis l'accueil (l'assistant IA peut proposer tout le plan), "
                                "ou importez un document Word, PDF ou texte : chaque partie deviendra une leçon.",
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
        tl.addWidget(label("Leçons", "SectionTitle"), 1)
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
        for ic, tip, fn in [("plus", "Ajouter une leçon", self.add_chapter),
                            ("trash", "Supprimer la leçon", self.delete_chapter),
                            ("up", "Monter", lambda: self.move(-1)), ("down", "Descendre", lambda: self.move(1)),
                            ("layers", "Fusionner avec le suivant", self.merge_next),
                            ("scissors", "Couper la leçon au curseur", self.split_at_cursor)]:
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
        self.title_edit.setPlaceholderText("Titre de la leçon")
        self.title_edit.setStyleSheet("font-size: 15pt; font-weight: 700; padding: 8px 12px;")
        self.title_edit.textEdited.connect(self._title_changed)
        top.addWidget(self.title_edit, 1)
        self.chapter_voice = QComboBox()
        self.chapter_voice.setMinimumWidth(220)
        self.chapter_voice.setToolTip("Voix d'explication de cette leçon")
        self.chapter_voice.currentIndexChanged.connect(self._chapter_voice_changed)
        top.addWidget(self.chapter_voice)
        rl.addLayout(top)

        # ---- module, langue, niveau, thème
        mr = QHBoxLayout()
        mr.setSpacing(8)
        mr.addWidget(label("Module", "Muted"))
        self.module_combo = QComboBox()
        self.module_combo.setEditable(True)
        self.module_combo.setMinimumWidth(240)
        self.module_combo.setToolTip("Module de la leçon : choisissez-en un ou tapez un nouveau titre")
        self.module_combo.lineEdit().setPlaceholderText("Hors module — ex. « Module 1 : Premiers pas »")
        self.module_combo.lineEdit().editingFinished.connect(self._module_changed)
        self.module_combo.activated.connect(lambda _i: self._module_changed())
        mr.addWidget(self.module_combo, 1)
        group = button("Modules", "layers", tooltip="Regrouper les leçons en modules (IA ou par nombre)")
        gm = QMenu(self)
        gm.addAction(icons.icon("sparkles", theme.CURRENT.text, 16), "Proposition de l'assistant IA…",
                     self.ai_modules)
        gm.addAction(icons.icon("layers", theme.CURRENT.text, 16), "Par nombre de leçons…", self.group_by_count)
        gm.addAction(icons.icon("edit", theme.CURRENT.text, 16), "Renommer ce module…", self.rename_module)
        gm.addAction(icons.icon("x", theme.CURRENT.text, 16), "Retirer les modules", self.clear_modules)
        group.setMenu(gm)
        mr.addWidget(group)
        self.lang_combo = QComboBox()
        self.lang_combo.setToolTip("Langue apprise dans cette leçon (par défaut : celle du cours)")
        self.lang_combo.currentIndexChanged.connect(self._lesson_meta_changed)
        mr.addWidget(self.lang_combo)
        self.level_combo = QComboBox()
        self.level_combo.addItem("Niveau du cours", "")
        for lv in LEVELS:
            self.level_combo.addItem(lv, lv)
        self.level_combo.currentIndexChanged.connect(self._lesson_meta_changed)
        mr.addWidget(self.level_combo)
        self.theme_edit = QLineEdit()
        self.theme_edit.setPlaceholderText("Thème (restaurant, voyage…)")
        self.theme_edit.setMaximumWidth(200)
        self.theme_edit.editingFinished.connect(self._lesson_meta_changed)
        mr.addWidget(self.theme_edit)
        self.studied_btn = button("Étudiée", "check", tooltip="Marque la leçon comme étudiée aujourd'hui : ses mots "
                                  "entrent dans le calendrier de révision (J+1, J+3, J+7, J+14, J+30)")
        self.studied_btn.setCheckable(True)
        self.studied_btn.clicked.connect(self._toggle_studied)
        mr.addWidget(self.studied_btn)
        rl.addLayout(mr)

        from .lesson_panels import ExercisesPanel, VocabPanel

        self.tabs = QTabWidget()
        tab_text = QWidget()
        tl1 = QVBoxLayout(tab_text)
        tl1.setContentsMargins(0, 10, 0, 0)
        tl1.setSpacing(10)
        self.vocab_panel = VocabPanel(ctx)
        self.vocab_panel.changed.connect(self._panel_changed)
        self.vocab_panel.listen_requested.connect(self._listen_item)
        self.ex_panel = ExercisesPanel(ctx)
        self.ex_panel.changed.connect(self._panel_changed)
        self.tabs.addTab(self.vocab_panel, icons.icon("dictionary", theme.CURRENT.muted, 16), "Vocabulaire et phrases")
        self.tabs.addTab(tab_text, icons.icon("book", theme.CURRENT.muted, 16), "Texte de la leçon")
        self.tabs.addTab(self.ex_panel, icons.icon("help-circle", theme.CURRENT.muted, 16),
                         "Exercices, résumé et quiz")
        self.tabs.setCurrentIndex(1)

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
        self.rate_btn = button("Débit", "clock", tooltip="Lire le paragraphe plus lentement ou plus vite")
        rate_menu = QMenu(self)
        for key, lbl in (("très lent", "Très lent"), ("lent", "Lent"), ("rapide", "Rapide"),
                         ("très rapide", "Très rapide")):
            rate_menu.addAction(lbl, lambda k=key: self._tag_rate(k))
        rate_menu.addSeparator()
        rate_menu.addAction("Normal (retirer)", lambda: self._tag_rate(""))
        self.rate_btn.setMenu(rate_menu)
        stress = button("Insister", "type", tooltip="Met en valeur le mot sélectionné (*mot*) : lu un peu plus fort, "
                        "précédé d'un court temps (voix Microsoft, clonage rapide et RVC)")
        stress.clicked.connect(self.emphasize_selection)
        self.sound_btn = button("Son", "music", tooltip="Effet sonore ou jingle de transition (« [son: …] », "
                                "« [virgule] »)")
        self.sound_menu = QMenu(self)
        self.sound_menu.aboutToShow.connect(self._fill_sounds)
        self.sound_btn.setMenu(self.sound_menu)
        studio = button("Studio", "podcast", tooltip="Réaction par-dessus, chapitres, prise au micro, réécriture par "
                        "l'IA…")
        sm = QMenu(self)
        sm.addAction(icons.icon("users", theme.CURRENT.text, 16), "Réaction par-dessus la réplique précédente",
                     self.tag_overlap)
        sm.addAction(icons.icon("mic", theme.CURRENT.text, 16), "Enregistrer cette réplique au micro…",
                     self.record_take)
        sm.addSeparator()
        sm.addAction(icons.icon("list", theme.CURRENT.text, 16), "Insérer un chapitre ici…", self.insert_chapter)
        sm.addAction(icons.icon("sparkles", theme.CURRENT.text, 16), "Chapitres proposés par l'IA",
                     self.ai_chapters)
        sm.addSeparator()
        rw = sm.addMenu(icons.icon("sparkles", theme.CURRENT.text, 16), "Réécrire la réplique avec l'IA")
        for key, text in (("courte", "Plus courte"), ("drole", "Plus drôle"), ("naturelle", "Plus naturelle"),
                          ("simple", "Plus simple"), ("enthousiaste", "Plus enthousiaste")):
            rw.addAction(text, lambda k=key: self.rewrite_line(k))
        sm.addAction(icons.icon("type", theme.CURRENT.text, 16), "Insister sur le mot sélectionné (*mot*)",
                     self.emphasize_selection)
        studio.setMenu(sm)
        self.role_btn = button("Réplique", "users", tooltip="Attribue le paragraphe à un intervenant (@Nom:)")
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
        think = button("Réflexion", "lightbulb", tooltip="Pause de réflexion après une question posée à l'auditeur "
                       "(durée réglée dans Production, ou [réflexion 10s])")
        tm = QMenu(self)
        tm.addAction("Pause de réflexion (durée par défaut)", lambda: self.insert(" [réflexion]"))
        for sec in (5, 10, 20, 30):
            tm.addAction(f"Pause de réflexion de {sec} s", lambda sec=sec: self.insert(f" [réflexion {sec}s]"))
        tm.addSeparator()
        tm.addAction(icons.icon("sparkles", theme.CURRENT.text, 16), "Proposées par l'assistant IA…",
                     self.ai_reflections)
        think.setMenu(tm)
        self.lang_btn = button("Langue", "globe", "primary", tooltip="Passage lu par une voix native : entoure la "
                               "sélection d'une balise de langue, « [es]…[/es] », ou l'ajoute en tête du paragraphe")
        self.lang_menu = QMenu(self)
        self.lang_menu.aboutToShow.connect(self._fill_lang_menu)
        self.lang_btn.setMenu(self.lang_menu)
        heading.hide()  # « # Rubrique » s'écrit directement ; place gagnée pour les outils
        for b, tip in ((clean, "Nettoyer le texte importé"), (pause, "Insérer une pause [pause 1s]"),
                       (preview, "Aperçu de lecture"), (think, "Pause de réflexion"), (self.emo_btn, "Émotion"),
                       (self.rate_btn, "Débit")):
            b.setText("")  # icône seule (info-bulle) : de la place pour Son, Studio…
            b.setFixedWidth(44)
            b.setToolTip(tip + " — " + b.toolTip() if b.toolTip() and tip not in b.toolTip() else tip)
        stress.hide()  # dans le menu Studio
        ia.setText("IA")
        ia.setToolTip("Assistant IA : " + ia.toolTip())
        for w in (self.lang_btn, clean, pause, think, self.sound_btn, self.role_btn, self.emo_btn, self.rate_btn,
                  studio, ia, preview):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(find)
        bar.addWidget(listen)
        tl1.addLayout(bar)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText("Le texte de la leçon : dialogue, petite histoire, grammaire…\n\n"
                                       "@Maria: [es] Hola, ¿qué tal?\nBonjour, comment ça va ?\n\n"
                                       "Le mot [es]gracias[/es] veut dire merci.")
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.editor.textChanged.connect(self._text_changed)
        self.highlighter = ScriptHighlighter(self.editor.document())
        self.find_bar = FindBar(self.editor, lambda m: self.ctx.toast(m, "success"))
        self.find_bar.hide()
        tl1.addWidget(self.find_bar)
        tl1.addWidget(self.editor, 1)
        rl.addWidget(self.tabs, 1)
        from PySide6.QtGui import QShortcut, QKeySequence

        QShortcut(QKeySequence("Ctrl+F"), self.editor, activated=self.toggle_find)

        status = QHBoxLayout()
        self.stats = label("", "Hint")
        status.addWidget(self.stats, 1)
        self.help = label("Astuces : « [es]mot[/es] », « [ja] phrase », « @Maria: réplique », « [ralenti] », "
                          "« [réflexion] », « [pause 2s] », « [son: ding] », « %% note »", "Faint")
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
            num = pr.lesson_number(ch) if ch.include else 0
            head = f"Leçon {num} · {ch.title}" if num else ch.title
            code, _loc = pr.target_of(ch)
            extra = [f"{len(ch.words())} mots" if ch.words() else "", f"{len(ch.phrases())} phrases"
                     if ch.phrases() else "", f"quiz {len(ch.quiz)}" if ch.quiz else "",
                     "étudiée ✓" if ch.id in pr.studied else ""]
            it.setText(f"{head}\n{ch.module or 'Hors module'} · {languages.language_name(code)}\n"
                       + (" · ".join(x for x in extra if x) or "à écrire"))
            it.setCheckState(Qt.Checked if ch.include else Qt.Unchecked)
            it.setForeground(QColor(theme.CURRENT.text if ch.include else theme.CURRENT.faint))
            it.setToolTip("Décochez pour exclure cette leçon du cours audio")
        self._loading = False
        inc = pr.included_chapters()
        self.count_lbl.setText(f"{len(inc)}/{len(pr.chapters)}")

    def _fill_voice_combos(self) -> None:
        pr = self.ctx.project
        voices = self.ctx.library.all()
        for combo, current, first in ((self.voice_combo_narr, pr.narrator_voice_id, None),
                                      (self.chapter_voice, self._current.voice_id if self._current else "",
                                       "Voix d'explication du cours")):
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
        self._load_lesson_extras(ch)
        self._loading = False
        self._update_stats()

    def _load_lesson_extras(self, ch: Chapter | None) -> None:
        self._fill_modules()
        pr = self.ctx.project
        self.lang_combo.blockSignals(True)
        self.lang_combo.clear()
        self.lang_combo.addItem(f"Langue du cours ({languages.language_name(pr.metadata.target_language)})", "")
        for lang in languages.sorted_languages():
            self.lang_combo.addItem(lang.name, lang.code)
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(ch.target_language if ch else "")))
        self.lang_combo.blockSignals(False)
        self.level_combo.blockSignals(True)
        self.level_combo.setCurrentIndex(max(0, self.level_combo.findData(ch.level if ch else "")))
        self.level_combo.blockSignals(False)
        self.theme_edit.setText(ch.theme if ch else "")
        self.studied_btn.setChecked(bool(ch and ch.id in pr.studied))
        self.studied_btn.setText(f"Étudiée le {pr.studied[ch.id][8:10]}/{pr.studied[ch.id][5:7]}"
                                 if ch and ch.id in pr.studied else "Étudiée")
        self.vocab_panel.load(ch)
        self.ex_panel.load(ch)

    def _lesson_meta_changed(self, *_a) -> None:
        ch = self._current
        if self._loading or ch is None:
            return
        code = self.lang_combo.currentData() or ""
        if code != ch.target_language:
            ch.target_language = code
            ch.target_locale = ""
        ch.level = self.level_combo.currentData() or ""
        ch.theme = " ".join(self.theme_edit.text().split())[:80]
        self.ctx.mark_dirty()
        self.vocab_panel.load(ch)
        self._refresh_items()

    def _panel_changed(self) -> None:
        self.ctx.mark_dirty()
        self._refresh_items()

    def _toggle_studied(self) -> None:
        ch = self._current
        if ch is None:
            return
        pr = self.ctx.project
        if ch.id in pr.studied:
            if QMessageBox.question(self, "Leçon étudiée", "Retirer cette leçon (et ses mots) du calendrier de "
                                    "révision ?") == QMessageBox.Yes:
                srs.unmark_studied(pr, ch)
        else:
            n = srs.mark_studied(pr, ch)
            self.ctx.toast(f"{n} mot(s) et phrase(s) ajouté(s) aux révisions : première révision demain." if n else
                           "Leçon notée comme étudiée (aucun nouveau mot à réviser).", "success", 5000)
        self.ctx.mark_dirty()
        self._loading = True
        self._load_lesson_extras(ch)
        self._loading = False
        self._refresh_items()

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
        s = f"{words:,} mots dans le texte".replace(",", " ")
        tags = languages_in_text(text)
        if tags:
            s += "  ·  Langues : " + ", ".join(languages.locale_name(t) for t in tags[:5])
        if chars:
            s += f"  ·  Intervenants : {', '.join(chars[:6])}"
        if tot.chapters:
            s += f"  ·  Cours : {len(tot.chapters)} leçon(s)"
        self.stats.setText(s)

    # -- actions sur les chapitres -----------------------------------------------------
    def _row(self) -> int:
        return self.list.currentRow()

    def add_chapter(self) -> None:
        self._commit_text()
        pr = self.ctx.project
        row = self._row() + 1 if self._row() >= 0 else len(pr.chapters)
        module = self._current.module if self._current else ""
        pr.chapters.insert(row, Chapter(title="Nouvelle leçon", text="", module=module))
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
        if QMessageBox.question(self, "Supprimer la leçon",
                                f"Supprimer définitivement « {ch.title} » ?") != QMessageBox.Yes:
            return
        del pr.chapters[row]
        for it in ch.vocab:
            pr.reviews.pop(it.id, None)
        pr.studied.pop(ch.id, None)
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
            self.ctx.toast("Placez le curseur à l'endroit où commence la nouvelle leçon.", "warning")
            return
        title = "Nouvelle leçon"
        first = after.split("\n", 1)[0].strip()
        if first.startswith("#") or (len(first) < 80 and not first.endswith((".", ",", ";"))):
            title = first.lstrip("#").strip() or title
            after = after.split("\n", 1)[1].lstrip() if "\n" in after else ""
        pr = self.ctx.project
        row = self._row()
        self._current.text = before
        pr.chapters.insert(row + 1, Chapter(title=title, text=after, voice_id=self._current.voice_id,
                                            module=self._current.module))
        self.ctx.mark_dirty()
        self._reload_list(row + 1)

    def _list_menu(self, pos) -> None:
        m = QMenu(self)
        m.addAction(icons.icon("plus", theme.CURRENT.text, 16), "Ajouter une leçon", self.add_chapter)
        m.addAction(icons.icon("sparkles", theme.CURRENT.text, 16), "Créer la leçon avec l'IA…", self.ai_lesson)
        m.addAction(icons.icon("layers", theme.CURRENT.text, 16), "Fusionner avec le suivant", self.merge_next)
        m.addAction(icons.icon("scissors", theme.CURRENT.text, 16), "Découper aux intertitres (#)",
                    self.split_on_headings)
        m.addAction(icons.icon("edit", theme.CURRENT.text, 16), "Renommer…", self.rename)
        m.addSeparator()
        m.addAction(icons.icon("sparkles", theme.CURRENT.text, 16), "Organiser en modules (assistant IA)…",
                    self.ai_modules)
        m.addAction(icons.icon("layers", theme.CURRENT.text, 16), "Organiser en modules par nombre de leçons…",
                    self.group_by_count)
        m.addAction(icons.icon("edit", theme.CURRENT.text, 16), "Renommer le module…", self.rename_module)
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
        name, ok = QInputDialog.getText(self, "Renommer", "Titre de la leçon :", text=self._current.title)
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
            self.ctx.toast("Aucun intertitre « # » trouvé dans cette leçon.", "warning")
            return
        pr = self.ctx.project
        row = self._row()
        head = parts[0].strip()
        new = []
        for i in range(1, len(parts), 2):
            new.append(Chapter(title=parts[i].strip(), text=parts[i + 1].strip(), voice_id=self._current.voice_id,
                               module=self._current.module))
        if head:
            self._current.text = head
            pr.chapters[row + 1:row + 1] = new
        else:
            pr.chapters[row:row + 1] = new
        self.ctx.mark_dirty()
        self._reload_list(row)
        self.ctx.toast(f"{len(new)} leçons créées", "success")

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
        pr = self.ctx.project
        names = list(dict.fromkeys([h.name for h in pr.hosts] + list(pr.cast.keys())
                                   + find_characters(self.editor.toPlainText())))
        for n in names:
            self.role_menu.addAction(icons.icon("user", theme.CURRENT.accent2, 16), n, lambda n=n: self._tag_role(n))
        if names:
            self.role_menu.addSeparator()
        self.role_menu.addAction(icons.icon("plus", theme.CURRENT.text, 16), "Nouvel intervenant…", self._new_role)
        self.role_menu.addAction(icons.icon("users", theme.CURRENT.text, 16), "Gérer les intervenants…",
                                 lambda: self.ctx.navigate("hosts"))

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

    def _tag_rate(self, rate: str) -> None:
        """Ajoute, remplace ou retire la balise de débit au début du paragraphe courant."""
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.StartOfBlock)
        line = cur.block().text()
        m = re.match(r"^@[^:\n]{1,40}:\s*", line)
        start = m.end() if m else 0
        tags = re.match(r"(?:\[[^\]\n]*\]\s*)*", line[start:]).group(0)
        rate_rx = r"\[\s*(?:débit\s*[:=]\s*)?(?:" + "|".join(RATE_ALIASES) + r")\s*\]\s*"
        new_tags = re.sub(rate_rx, "", tags, flags=re.I) + (f"[{rate}] " if rate else "")
        cur.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, start)
        cur.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(tags))
        cur.insertText(new_tags)
        self.editor.setFocus()

    def emphasize_selection(self) -> None:
        """Entoure la sélection (ou le mot sous le curseur) d'astérisques, ou les retire."""
        cur = self.editor.textCursor()
        if not cur.hasSelection():
            block = cur.block()
            col = cur.position() - block.position()
            for m in EMPHASIS_RE.finditer(block.text()):
                if m.start() <= col <= m.end():  # curseur sur un mot déjà mis en valeur : on retire
                    cur.setPosition(block.position() + m.start())
                    cur.setPosition(block.position() + m.end(), QTextCursor.KeepAnchor)
                    cur.insertText(m.group(1))
                    self.editor.setFocus()
                    return
            cur.select(QTextCursor.WordUnderCursor)
        text = cur.selectedText().strip()
        if not text:
            self.ctx.toast("Sélectionnez le mot à mettre en valeur.", "info")
            return
        if len(text) > 2 and text.startswith("*") and text.endswith("*"):
            cur.insertText(text[1:-1])
        else:
            doc = self.editor.document()
            a, b = cur.selectionStart(), cur.selectionEnd()
            before = doc.characterAt(a - 1) if a > 0 else ""
            after = doc.characterAt(b)
            if before == "*" and after == "*":  # déjà mis en valeur : on retire
                cur.setPosition(a - 1)
                cur.setPosition(b + 1, QTextCursor.KeepAnchor)
                cur.insertText(text)
            else:
                cur.insertText(f"*{text}*")
        self.editor.setFocus()

    def _new_role(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvel intervenant", "Nom de l'intervenant :")
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
        from ...core import renderer
        from ...core.textproc import parse_script, strip_language_tags

        items = [i for i in parse_script(text, split=True) if i.kind == "para"]
        if not items:
            self.ctx.toast("Rien à lire dans la sélection.", "warning")
            return
        resolver = renderer.VoiceResolver(self.ctx.project, self.ctx.library)
        # la voix du premier passage dans une autre langue que l'explication, sinon celle du premier passage
        first = next((i for i in items if i.lang or i.voice_key), items[0])
        voice, lang = resolver.resolve_item(first.voice_key, first.lang, self._current)
        if len(items) > 1 and any(i.lang != first.lang or i.voice_key != first.voice_key for i in items):
            items = [i for i in items if i.lang == first.lang and i.voice_key == first.voice_key]
            self.ctx.toast("Plusieurs voix dans la sélection : écoute du premier passage dans cette langue.", "info")
        spoken = strip_language_tags(" ".join(i.text for i in items))
        self.ctx.preview_voice(voice, spoken, language=lang)

    def _listen_item(self, item) -> None:
        from ...core import course, renderer

        ch = self._current
        spec = course.target_spec(self.ctx.project, ch) if ch else self.ctx.project.metadata.target_language
        voice = renderer.VoiceResolver(self.ctx.project, self.ctx.library).native(spec, ch)
        self.ctx.preview_voice(voice, item.term, language=spec)

    # -- balises de langue -------------------------------------------------------------
    def _fill_lang_menu(self) -> None:
        m = self.lang_menu
        m.clear()
        pr = self.ctx.project
        ch = self._current
        spec = course.target_spec(pr, ch) if ch else pr.metadata.target_language
        name = languages.locale_name(spec)
        m.addAction(icons.icon("globe", theme.CURRENT.accent2, 16), f"{name} — passage sélectionné [{spec}]…[/{spec}]",
                    lambda: self.tag_language(spec))
        m.addAction(icons.icon("globe", theme.CURRENT.text, 16), f"{name} — tout le paragraphe [{spec}]",
                    lambda: self.tag_language(spec, paragraph=True))
        explain = pr.metadata.language or "fr"
        m.addAction(icons.icon("user", theme.CURRENT.text, 16),
                    f"Langue d'explication ({languages.language_name(explain)}) [{explain}]",
                    lambda: self.tag_language(explain))
        lang = languages.get(spec)
        if lang and len(lang.locales) > 1:
            acc = m.addMenu(icons.icon("globe", theme.CURRENT.text, 16), "Autre accent de la même langue")
            for loc, lbl in lang.locales:
                acc.addAction(f"{lbl} [{loc}]", lambda loc=loc: self.tag_language(loc))
        others = m.addMenu(icons.icon("globe", theme.CURRENT.text, 16), "Autre langue")
        for lg in languages.sorted_languages():
            others.addAction(f"{lg.name} [{lg.code}]", lambda c=lg.code: self.tag_language(c))
        m.addSeparator()
        m.addAction(icons.icon("info", theme.CURRENT.text, 16), "Comment ça marche ?", self._lang_help)

    def tag_language(self, spec: str, paragraph: bool = False) -> None:
        """Entoure la sélection de [spec]…[/spec], ou place [spec] en tête du paragraphe (après « @Nom: »)."""
        cur = self.editor.textCursor()
        if cur.hasSelection() and not paragraph:
            text = cur.selectedText().replace("\u2029", "\n")
            if "\n" in text.strip():
                cur.insertText(f"[{spec}]\n{text.strip()}\n[/{spec}]")
            else:
                cur.insertText(f"[{spec}]{text.strip()}[/{spec}]")
        else:
            cur.movePosition(QTextCursor.StartOfBlock)
            line = cur.block().text()
            m = re.match(r"^@[^:\n]{1,40}:\s*", line)
            start = m.end() if m else 0
            old = re.match(r"\[\s*[a-zA-Z]{2,3}(?:[-_][A-Za-z0-9]{2,9}){0,2}\s*\]\s*", line[start:])
            cur.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, start)
            if old and languages.is_language_tag(old.group(0).strip(" []")):
                cur.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, old.end())
            cur.insertText(f"[{spec}] ")
        self.editor.setFocus()

    def _lang_help(self) -> None:
        QMessageBox.information(
            self, "Balises de langue",
            "Les passages dans une autre langue que la langue d'explication sont lus par une voix native :\n\n"
            "• au milieu d'une phrase : « Le mot [es]gato[/es] veut dire chat. »\n"
            "• pour tout un paragraphe : « [ja] おはようございます。 »\n"
            "• pour plusieurs paragraphes : une ligne « [en-GB] », le texte, puis une ligne « [/en] »\n"
            "• dans un dialogue : « @Maria: [es] Hola » — chaque intervenant a sa propre voix native "
            "(page Intervenants).\n\n"
            "L'accent se choisit avec la variante : [en-GB], [en-US], [en-AU], [es-MX], [pt-BR], [zh-TW]…\n"
            "Les voix natives se règlent dans la page Langues et voix.")

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

    # -- assistant IA : leçon complète ----------------------------------------------------
    def ai_lesson(self) -> None:
        if self._current is None:
            self.add_chapter()
        if self._current is None:
            return
        self._commit_text()
        from ..dialogs.lesson_ai import LessonAIDialog

        dlg = LessonAIDialog(self.ctx, self._current, self)
        if dlg.exec():
            self._loading = True
            self.title_edit.setText(self._current.title)
            self.editor.setPlainText(self._current.text)
            self._load_lesson_extras(self._current)
            self._loading = False
            self.ctx.mark_dirty()
            self._update_stats()
            self._refresh_items()
            self.tabs.setCurrentIndex(0)

    # -- cours : modules ---------------------------------------------------------------
    def _fill_modules(self) -> None:
        self.module_combo.blockSignals(True)
        current = self._current.module if self._current else ""
        self.module_combo.clear()
        self.module_combo.addItem("")  # hors module
        for title in course.module_titles(self.ctx.project.chapters):
            self.module_combo.addItem(title)
        self.module_combo.setCurrentText(current)
        self.module_combo.blockSignals(False)

    def _module_changed(self) -> None:
        if self._loading or self._current is None:
            return
        title = " ".join(self.module_combo.currentText().split())[:80]
        if title != self._current.module:
            self._current.module = title
            self.ctx.mark_dirty()
            self._fill_modules()
            self._refresh_items()

    def _apply_modules(self, titles: list[str], lessons: list[Chapter]) -> None:
        for c, t in zip(lessons, titles):
            c.module = t
        self.ctx.mark_dirty()
        self._fill_modules()
        self._refresh_items()
        n = len(course.module_titles(lessons))
        self.ctx.toast(f"{len(lessons)} leçons réparties en {n} modules.", "success")

    def group_by_count(self) -> None:
        pr = self.ctx.project
        if not pr.chapters:
            return
        n, ok = QInputDialog.getInt(self, "Organiser en modules", "Nombre de leçons par module :", 4, 1, 50)
        if not ok:
            return
        self._commit_text()
        course.group_lessons(pr.chapters, n)
        self._apply_modules([c.module for c in pr.chapters], pr.chapters)

    def rename_module(self) -> None:
        old = self._current.module if self._current else ""
        if not old:
            self.ctx.toast("Cette leçon n'appartient à aucun module.", "info")
            return
        new, ok = QInputDialog.getText(self, "Renommer le module", "Titre du module :", text=old)
        new = " ".join(new.split())[:80]
        if ok and new and new != old:
            course.rename_module(self.ctx.project.chapters, old, new)
            self.ctx.mark_dirty()
            self._fill_modules()
            self._refresh_items()

    def clear_modules(self) -> None:
        if QMessageBox.question(self, "Retirer les modules", "Retirer toutes les leçons de leur module ?") \
                != QMessageBox.Yes:
            return
        for c in self.ctx.project.chapters:
            c.module = ""
        self.ctx.mark_dirty()
        self._fill_modules()
        self._refresh_items()

    def ai_modules(self) -> None:
        pr = self.ctx.project
        lessons = list(pr.chapters)
        if len(lessons) < 2:
            self.ctx.toast("Il faut au moins deux leçons pour former des modules.", "info")
            return
        self._commit_text()
        from ...core import ai
        from .. import tasks

        payload = [(c.title, (c.theme + ". " if c.theme else "") + c.text[:1500]) for c in lessons]

        def work():
            return ai.organize_modules(payload, ai.client_from_settings())

        def done(titles):
            preview = "\n".join(f"• {t}" for t in dict.fromkeys(titles))
            if QMessageBox.question(self, "Modules proposés", f"L'assistant propose ces modules :\n\n{preview}\n\n"
                                    "Les appliquer ? (les leçons gardent leur ordre)") == QMessageBox.Yes:
                self._apply_modules(titles, lessons)

        self.ctx.toast("DeepSeek organise les leçons en modules…", "info", 3000)
        self._ai_task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 7000))

    def ai_reflections(self) -> None:
        ch = self._current
        if ch is None:
            return
        self._commit_text()
        if not ch.text.strip():
            self.ctx.toast("Le texte de la leçon est vide.", "warning")
            return
        from ...core import ai
        from .. import tasks

        def work():
            return ai.reflection_points(ch.text, ai.client_from_settings())

        def done(points):
            if not points:
                self.ctx.toast("Aucune pause de réflexion proposée pour cette leçon.", "info")
                return
            from ..dialogs.reflections import ReflectionsDialog

            dlg = ReflectionsDialog(points, self)
            if dlg.exec() and self._current is ch:
                ch.text = ai.apply_reflections(ch.text, dlg.accepted_points())
                self._loading = True
                self.editor.setPlainText(ch.text)
                self._loading = False
                self.ctx.mark_dirty()
                self._update_stats()
                self._refresh_items()

        self.ctx.toast("DeepSeek cherche les bons moments pour faire réfléchir…", "info", 3000)
        self._refl_task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 7000))

    # -- studio : sons, réactions, chapitres, prises, réécriture --------------------------
    def _project_dir(self):
        pr = self.ctx.project
        return pr.path.parent if pr.path is not None else None

    def _fill_sounds(self) -> None:
        from ...core import sounds

        m = self.sound_menu
        m.clear()
        m.addAction(icons.icon("music", theme.CURRENT.accent, 16), "Virgule (jingle de transition)",
                    lambda: self._insert_block("[virgule]"))
        m.addSeparator()
        listen = QMenu("Écouter", m)
        for name, text in sounds.available(self._project_dir()):
            if name == "virgule":
                continue
            m.addAction(icons.icon("music", theme.CURRENT.muted, 16), text,
                        lambda n=name: self._insert_block(f"[son: {n}]"))
        for name, text in sounds.available(self._project_dir()):
            listen.addAction(text, lambda n=name: self._play_sound(n))
        m.addSeparator()
        m.addMenu(listen).setIcon(icons.icon("headphones", theme.CURRENT.text, 16))
        m.addAction(icons.icon("folder", theme.CURRENT.text, 16), "Ajouter mes propres sons…", self._open_my_sounds)

    def _play_sound(self, name: str) -> None:
        from ...core import sounds

        path = sounds.resolve(name, self._project_dir())
        if path is not None:
            self.ctx.play(path, f"Son — {name}")

    def _open_my_sounds(self) -> None:
        from ...core import sounds
        from ..main_window import open_path

        open_path(sounds.user_dir())
        self.ctx.toast("Déposez vos fichiers audio (MP3, WAV…) dans ce dossier, puis écrivez « [son: nom du fichier] ». "
                       "Utilisez uniquement des sons libres de droits.", "info", 8000)

    def _insert_block(self, tag: str) -> None:
        """Insère une balise sur sa propre ligne, après le paragraphe du curseur."""
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.EndOfBlock)
        cur.insertText("\n\n" + tag + "\n")
        self.editor.setTextCursor(cur)
        self.editor.setFocus()

    def _block_prefix(self, line: str) -> int:
        """Longueur des balises de tête (« @Nom: », émotions…) d'une réplique."""
        m = re.match(r"^(?:@[^:\n]{1,40}:\s*)?(?:\[[^\]\n]*\]\s*)*", line)
        return m.end() if m else 0

    def tag_overlap(self) -> None:
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.StartOfBlock)
        line = cur.block().text()
        if re.search(r"\[\s*par[- ]dessus\s*\]", line, re.I):
            self.ctx.toast("Cette réplique est déjà lancée par-dessus la précédente.", "info")
            return
        m = re.match(r"^@[^:\n]{1,40}:\s*", line)
        cur.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, m.end() if m else 0)
        cur.insertText("[par-dessus] ")
        self.editor.setFocus()
        self.ctx.toast("La réplique commencera juste avant la fin de la précédente (réglage dans Production).", "info")

    def insert_chapter(self) -> None:
        name, ok = QInputDialog.getText(self, "Chapitre", "Titre du chapitre (affiché dans les applications "
                                        "d'écoute) :")
        if ok and name.strip():
            cur = self.editor.textCursor()
            cur.movePosition(QTextCursor.StartOfBlock)
            cur.insertText(f"[chapitre: {name.strip()}]\n\n")
            self.editor.setFocus()

    def _current_line(self) -> tuple[str, str, str]:
        """(nom de l'intervenant, balises de tête, texte) de la réplique sous le curseur."""
        line = self.editor.textCursor().block().text()
        n = self._block_prefix(line)
        m = re.match(r"^@([^:\n]{1,40}):", line)
        return (m.group(1).strip() if m else ""), line[:n], line[n:]

    def rewrite_line(self, style: str) -> None:
        if self._current is None:
            return
        speaker, prefix, body = self._current_line()
        if len(body.split()) < 2:
            self.ctx.toast("Placez le curseur dans une réplique à réécrire.", "warning")
            return
        from ...core import ai
        from .. import tasks

        block = self.editor.textCursor().block()
        doc = self.editor.document()
        context = "\n".join(doc.findBlockByNumber(i).text() for i in range(max(0, block.blockNumber() - 4),
                                                                         min(doc.blockCount(), block.blockNumber() + 5)))

        def work():
            return ai.rewrite_line(body, style, ai.client_from_settings(), speaker, context)

        def done(new):
            if block.text() != prefix + body:
                self.ctx.toast("La réplique a changé entre-temps : réécriture abandonnée.", "warning")
                return
            cur = QTextCursor(block)
            cur.movePosition(QTextCursor.StartOfBlock)
            cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cur.insertText(prefix + new)
            self.ctx.toast("Réplique réécrite (Ctrl+Z pour revenir à l'ancienne).", "success")

        self.ctx.toast("DeepSeek réécrit la réplique…", "info", 2000)
        self._rw_task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 7000))

    def ai_chapters(self) -> None:
        ch = self._current
        if ch is None:
            return
        self._commit_text()
        from ...core import ai
        from .. import tasks

        def work():
            return ai.propose_chapters(ch.text, ai.client_from_settings())

        def done(chapters):
            listing = "\n".join(f"• {t}" for _n, t in chapters)
            if QMessageBox.question(self, "Chapitres proposés", f"Chapitres proposés pour « {ch.title} » :\n\n"
                                    f"{listing}\n\nLes insérer dans le script (repères « [chapitre: …] », non lus) ?") \
                    != QMessageBox.Yes or self._current is not ch:
                return
            ch.text = ai.apply_chapters(ch.text, chapters)
            self._loading = True
            self.editor.setPlainText(ch.text)
            self._loading = False
            self.ctx.mark_dirty()
            self.ctx.toast("Chapitres ajoutés : ils apparaîtront dans les MP3 des leçons.", "success")

        self.ctx.toast("DeepSeek découpe la leçon en chapitres…", "info", 2500)
        self._chap_task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 7000))

    def record_take(self) -> None:
        if self._current is None:
            return
        speaker, prefix, body = self._current_line()
        block = self.editor.textCursor().block()
        from ...core import renderer
        from ..dialogs.take import TakeDialog

        dlg = TakeDialog(self.ctx, speaker, re.sub(r"\[[^\]\n]*\]", "", body).strip(),
                         renderer.takes_dir(self.ctx.project), self)
        if not dlg.exec() or dlg.saved_name is None:
            return
        new_prefix = re.sub(r"\[\s*prise\s*[:=][^\]\n]*\]\s*", "", prefix)
        m = re.match(r"^@[^:\n]{1,40}:\s*", new_prefix)
        head = m.group(0) if m else ""
        tag = f"[prise: {dlg.saved_name}] "
        text = head + tag + new_prefix[len(head):] + body
        cur = QTextCursor(block)
        cur.movePosition(QTextCursor.StartOfBlock)
        cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cur.insertText(text)
        self.ctx.toast("Prise enregistrée : votre voix remplacera la synthèse pour cette réplique.", "success")


def languages_in_text(text: str) -> list[str]:
    from ...core.textproc import languages_in

    return languages_in(text)
