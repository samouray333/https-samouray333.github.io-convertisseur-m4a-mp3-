"""Page Histoires : les histoires de la collection et l'éditeur de texte avec balises de mise en scène."""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QSplitter, QToolButton,
                               QVBoxLayout, QWidget)

from ...core import story
from ...core.models import Chapter
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
            (QRegularExpression(r"^#{1,6}\s.*$"), fmt(p.accent, bold=True)),
            (QRegularExpression(r"\[\s*(pause|PAUSE)[^\]]*\]"), fmt(p.info, bold=True, bg=theme.rgba(p.info, 0.12))),
            (QRegularExpression(r"\[\s*(son|bruitage|effet|virgule|jingle)\b[^\]]*\]",
                                QRegularExpression.CaseInsensitiveOption),
             fmt(p.accent, bold=True, bg=theme.rgba(p.accent, 0.16))),
            (QRegularExpression(r"\[\s*(/\s*ambiance|fin\s+(de\s+l.)?ambiance|ambiance|fond)\b[^\]]*\]",
                                QRegularExpression.CaseInsensitiveOption),
             fmt(p.info, bold=True, bg=theme.rgba(p.info, 0.16))),
            (QRegularExpression(r"\{\s*pr[ée]nom\s*\}", QRegularExpression.CaseInsensitiveOption),
             fmt(p.accent2, bold=True, bg=theme.rgba(p.accent2, 0.2))),
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
        super().__init__(ctx, "Histoires", "Les histoires de la collection. Le narrateur lit le récit ; une "
                         "réplique commence par le nom du personnage (« @Pompon: »).")
        self._loading = False
        self._current: Chapter | None = None

        self.voice_combo_narr = QComboBox()
        self.voice_combo_narr.setMinimumWidth(240)
        self.voice_combo_narr.setToolTip("Voix du narrateur (vous pouvez cloner la voix de papa, maman, papi ou mamie "
                                         "dans la page Voix)")
        self.voice_combo_narr.currentIndexChanged.connect(self._narrator_changed)
        self.header.add_action(label("Narrateur :", "Muted"))
        self.header.add_action(self.voice_combo_narr)
        write = button("Nouvelle histoire", "sparkles", "primary", tooltip="L'assistant écrit un conte à partir de "
                       "votre idée, adapté à l'âge de l'enfant")
        write.clicked.connect(self.new_story_ai)
        self.header.add_action(write)
        lex = button("Lexique", "dictionary", tooltip="Dictionnaire de prononciation de la collection")
        lex.clicked.connect(self._open_lexicon)
        self.header.add_action(lex)
        go = button("Produire", "wave")
        go.clicked.connect(lambda: self.ctx.navigate("production"))
        self.header.add_action(go)

        empty_box = QWidget()
        eb = QHBoxLayout(empty_box)
        eb.setContentsMargins(0, 0, 0, 0)
        new_btn = button("Nouvelle histoire", "sparkles", "primary")
        new_btn.clicked.connect(lambda: self.ctx.window.new_story())
        samples_btn = button("Histoires d'exemple", "star")
        samples_btn.clicked.connect(lambda: self.ctx.window.open_samples())
        blank_btn = button("Écrire moi-même", "edit")
        blank_btn.clicked.connect(self.add_chapter)
        for b in (new_btn, samples_btn, blank_btn):
            eb.addWidget(b)
        self.empty = EmptyState("book", "Aucune histoire",
                                "Donnez une idée à l'assistant (« un dragon qui a peur du noir »), écrivez votre "
                                "propre conte, ou découvrez les histoires d'exemple.", empty_box)
        self.body.addWidget(self.empty, 1)

        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.body.addWidget(self.split, 1)

        # ---- liste des chapitres
        left = Card(margins=(12, 14, 12, 12), spacing=8)
        left.setMinimumWidth(270)
        left.setMaximumWidth(420)
        tl = QHBoxLayout()
        tl.addWidget(label("Histoires", "SectionTitle"), 1)
        self.count_lbl = label("", "Faint")
        tl.addWidget(self.count_lbl)
        left.add(tl)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setStyleSheet("QListWidget { border: none; background: transparent; padding: 0; }")
        self.list.setIconSize(QSize(46, 46))
        self.list.currentRowChanged.connect(self._select_row)
        self.list.itemChanged.connect(self._item_changed)
        self.list.model().rowsMoved.connect(self._rows_moved)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        left.add(self.list)
        tb = QHBoxLayout()
        tb.setSpacing(2)
        for ic, tip, fn in [("plus", "Ajouter une histoire (vide)", self.add_chapter),
                            ("trash", "Supprimer l'histoire", self.delete_chapter),
                            ("up", "Monter", lambda: self.move(-1)), ("down", "Descendre", lambda: self.move(1)),
                            ("star", "Favori", self.toggle_favorite),
                            ("scissors", "Couper l'histoire au curseur", self.split_at_cursor)]:
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
        self.title_edit.setPlaceholderText("Titre de l'histoire")
        self.title_edit.setStyleSheet("font-size: 15pt; font-weight: 700; padding: 8px 12px;")
        self.title_edit.textEdited.connect(self._title_changed)
        top.addWidget(self.title_edit, 1)
        self.chapter_voice = QComboBox()
        self.chapter_voice.setMinimumWidth(220)
        self.chapter_voice.setToolTip("Voix du narrateur pour cette histoire")
        self.chapter_voice.currentIndexChanged.connect(self._chapter_voice_changed)
        top.addWidget(self.chapter_voice)
        rl.addLayout(top)

        # ---- informations de l'histoire (âge, ton, histoire du soir, couverture, résumé)
        info = QFrame()
        info.setObjectName("CardFlat")
        il = QHBoxLayout(info)
        il.setContentsMargins(10, 8, 12, 8)
        il.setSpacing(12)
        self.cover_btn = QToolButton()
        self.cover_btn.setFixedSize(92, 92)
        self.cover_btn.setIconSize(QSize(86, 86))
        self.cover_btn.setToolTip("Couverture de l'histoire (MP3, livret, coin lecture)")
        self.cover_btn.setPopupMode(QToolButton.InstantPopup)
        cm = QMenu(self)
        cm.addAction(icons.icon("sparkles", theme.CURRENT.text, 16), "Dessiner une couverture", self.draw_cover)
        cm.addAction(icons.icon("image", theme.CURRENT.text, 16), "Choisir une image…", self.pick_cover)
        cm.addAction(icons.icon("x", theme.CURRENT.text, 16), "Retirer (couverture de la collection)",
                     lambda: self._set_cover(""))
        self.cover_btn.setMenu(cm)
        il.addWidget(self.cover_btn)
        col = QVBoxLayout()
        col.setSpacing(6)
        ir = QHBoxLayout()
        ir.setSpacing(8)
        self.st_age = QComboBox()
        for key, prof in story.AGES.items():
            self.st_age.addItem(prof.label, key)
        self.st_tone = QComboBox()
        for key, (lbl, _d) in story.TONES.items():
            self.st_tone.addItem(lbl, key)
        self.st_bedtime = ToggleSwitch("Histoire du soir")
        self.st_bedtime.setToolTip("Voix douce et ralentie, berceuse à la fin, puis pluie ou bruit blanc qui "
                                   "s'éteint doucement (réglages dans Export)")
        self.st_fav = ToggleSwitch("Favori")
        summary_btn = button("Résumé IA", "sparkles", tooltip="DeepSeek propose un résumé de l'histoire")
        summary_btn.clicked.connect(self.ai_summary)
        for w in (label("Âge", "Muted"), self.st_age, label("Ton", "Muted"), self.st_tone, self.st_bedtime,
                  self.st_fav):
            ir.addWidget(w)
        ir.addStretch(1)
        ir.addWidget(summary_btn)
        col.addLayout(ir)
        mr = QHBoxLayout()
        self.st_summary = QLineEdit()
        self.st_summary.setPlaceholderText("Résumé (MP3, livret, bibliothèque)")
        self.st_moral = QLineEdit()
        self.st_moral.setPlaceholderText("Morale (facultatif, écrite à la fin du livret)")
        mr.addWidget(self.st_summary, 3)
        mr.addWidget(self.st_moral, 2)
        col.addLayout(mr)
        il.addLayout(col, 1)
        for sig in (self.st_age.currentIndexChanged, self.st_tone.currentIndexChanged, self.st_bedtime.toggled,
                    self.st_fav.toggled, self.st_summary.textEdited, self.st_moral.textEdited):
            sig.connect(self._episode_info_changed)
        rl.addWidget(info)

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
        self.sound_btn = button("Bruitage", "music", tooltip="Bruitage ponctuel : porte qui grince, pas, hibou, "
                                "cloche magique… (« [son: porte] »)")
        self.sound_menu = QMenu(self)
        self.sound_menu.aboutToShow.connect(self._fill_sounds)
        self.sound_btn.setMenu(self.sound_menu)
        self.amb_btn = button("Ambiance", "wave", tooltip="Fond continu sous une scène : forêt, pluie, mer… "
                              "(« [ambiance: pluie] » jusqu'à « [ambiance: fin] »)")
        self.amb_menu = QMenu(self)
        self.amb_menu.aboutToShow.connect(self._fill_ambiences)
        self.amb_btn.setMenu(self.amb_menu)
        studio = button("Scène", "sparkles", tooltip="Prénom de l'enfant, enregistrement au micro, "
                        "réécriture par l'IA, vérification pour l'âge…")
        sm = QMenu(self)
        sm.addAction(icons.icon("user", theme.CURRENT.text, 16), "Insérer le prénom de l'enfant ({prénom})",
                     lambda: self.insert("{prénom}"))
        sm.addAction(icons.icon("mic", theme.CURRENT.text, 16), "Enregistrer cette réplique au micro…",
                     self.record_take)
        sm.addSeparator()
        rw = sm.addMenu(icons.icon("sparkles", theme.CURRENT.text, 16), "Réécrire le passage avec l'IA")
        for key, text in (("simple", "Plus simple (pour les petits)"), ("drole", "Plus drôle"),
                          ("douce", "Plus doux (pour dormir)"), ("courte", "Plus court"),
                          ("vivante", "Plus vivant")):
            rw.addAction(text, lambda k=key: self.rewrite_line(k))
        sm.addAction(icons.icon("type", theme.CURRENT.text, 16), "Insister sur le mot sélectionné (*mot*)",
                     self.emphasize_selection)
        sm.addSeparator()
        sm.addAction(icons.icon("shield", theme.CURRENT.text, 16), "Vérifier pour l'âge choisi",
                     self.check_age)
        studio.setMenu(sm)
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
        heading.hide()  # « # Partie » s'écrit directement ; place gagnée pour les outils des contes
        for b, tip in ((clean, "Nettoyer le texte importé"), (pause, "Insérer une pause [pause 1s]"),
                       (preview, "Aperçu de lecture"), (self.emo_btn, "Émotion du paragraphe"),
                       (self.rate_btn, "Débit du paragraphe"), (self.role_btn, "Réplique d'un personnage"),
                       (ia, "Assistant IA")):
            b.setText("")  # icône seule (info-bulle) : de la place pour Bruitage, Ambiance…
            b.setFixedWidth(56 if b.menu() is not None else 44)
            b.setToolTip(tip + " — " + b.toolTip() if b.toolTip() and tip not in b.toolTip() else tip)
        stress.hide()  # dans le menu Studio

        for w in (clean, pause, self.sound_btn, self.amb_btn, self.role_btn, self.emo_btn, self.rate_btn, studio, ia,
                  preview):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(find)
        bar.addWidget(listen)
        rl.addLayout(bar)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText("Il était une fois…")
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
        self.help = label("Astuces : « @Pompon: réplique », « [son: porte] », « [ambiance: pluie] » … « [ambiance: fin] », "
                          "« {prénom} », « [pause 2s] », « [chuchoté] », « %% note »", "Faint")
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
            marks = ("★ " if ch.favorite else "") + ("☾ " if ch.bedtime else "")
            age = story.AGES.get(ch.age)
            it.setText(f"{marks}{ch.title}\n{age.label if age else ''} · {words:,} mots · "
                       f"≈ {format_duration(pr.story_minutes(ch) * 60)}".replace(",", " "))
            it.setCheckState(Qt.Checked if ch.include else Qt.Unchecked)
            it.setForeground(QColor(theme.CURRENT.text if ch.include else theme.CURRENT.faint))
            it.setToolTip("Décochez pour exclure cette histoire de la production et de l'export")
            cover = ch.cover_path or pr.metadata.cover_path
            pm = QPixmap(cover) if cover else QPixmap()
            it.setIcon(QIcon(pm) if not pm.isNull() else icons.icon("book", theme.CURRENT.muted, 40))
        self._loading = False
        inc = pr.included_chapters()
        self.count_lbl.setText(f"{len(inc)}/{len(pr.chapters)}")

    def _fill_voice_combos(self) -> None:
        pr = self.ctx.project
        voices = self.ctx.library.all()
        for combo, current, first in ((self.voice_combo_narr, pr.narrator_voice_id, None),
                                      (self.chapter_voice, self._current.voice_id if self._current else "",
                                       "Narrateur de la collection")):
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
        self._load_episode_info(ch)
        self._loading = False
        self._update_stats()

    def _load_episode_info(self, ch: Chapter | None) -> None:
        self.st_age.setCurrentIndex(max(0, self.st_age.findData(ch.age if ch else "6-8")))
        self.st_tone.setCurrentIndex(max(0, self.st_tone.findData(ch.tone if ch else "aventure")))
        self.st_bedtime.setChecked(bool(ch and ch.bedtime))
        self.st_fav.setChecked(bool(ch and ch.favorite))
        self.st_summary.setText(ch.description if ch else "")
        self.st_moral.setText(ch.moral if ch else "")
        self._update_cover_btn()

    def _update_cover_btn(self) -> None:
        ch = self._current
        path = (ch.cover_path if ch else "") or self.ctx.project.metadata.cover_path
        pm = QPixmap(path) if path else QPixmap()
        if pm.isNull():
            self.cover_btn.setIcon(icons.icon("image", theme.CURRENT.faint, 40))
            self.cover_btn.setText("")
        else:
            self.cover_btn.setIcon(QIcon(pm))

    def _episode_info_changed(self, *_a) -> None:
        ch = self._current
        if self._loading or ch is None:
            return
        ch.age = self.st_age.currentData() or "6-8"
        ch.tone = self.st_tone.currentData() or "aventure"
        ch.bedtime = self.st_bedtime.isChecked()
        ch.favorite = self.st_fav.isChecked()
        ch.description = self.st_summary.text().strip()
        ch.moral = self.st_moral.text().strip()
        self.ctx.mark_dirty()
        self._refresh_items()
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
        minutes = tot.story_minutes(Chapter("", text, bedtime=bool(self._current and self._current.bedtime)))
        s = f"{words:,} mots · ≈ {format_duration(minutes * 60)} d'écoute".replace(",", " ")
        s += f"  ·  Collection : ≈ {format_duration(tot.estimated_minutes() * 60)}"
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
        pr.chapters.insert(row, Chapter(title=f"Histoire {len(pr.chapters) + 1}", text=""))
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
        if QMessageBox.question(self, "Supprimer l'histoire",
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
            self.ctx.toast("Placez le curseur à l'endroit où commence la nouvelle histoire.", "warning")
            return
        title = "Nouvelle histoire"
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
        m.addAction(icons.icon("sparkles", theme.CURRENT.text, 16), "Nouvelle histoire avec l'IA…", self.new_story_ai)
        m.addAction(icons.icon("plus", theme.CURRENT.text, 16), "Ajouter une histoire vide", self.add_chapter)
        m.addAction(icons.icon("star", theme.CURRENT.text, 16), "Favori", self.toggle_favorite)
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
        name, ok = QInputDialog.getText(self, "Renommer", "Titre de l'histoire :", text=self._current.title)
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
            self.ctx.toast("Aucun intertitre « # » trouvé dans cette histoire.", "warning")
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
        self.ctx.toast(f"{len(new)} histoires créées", "success")

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
        self.role_menu.addAction(icons.icon("plus", theme.CURRENT.text, 16), "Nouveau personnage…", self._new_role)
        self.role_menu.addAction(icons.icon("users", theme.CURRENT.text, 16), "Gérer les personnages…",
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
            host = self.ctx.project.host_by_name(m.group(1))
            vid = host.voice_id if host and host.voice_id else next(
                (v for k, v in self.ctx.project.cast.items() if k.lower() == m.group(1).strip().lower()), "")
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

    # -- contes : nouvelle histoire, couverture, favori, résumé -------------------------
    def new_story_ai(self) -> None:
        self._commit_text()
        from ..dialogs.story import StoryDialog

        target = self._current if self._current is not None and not self._current.text.strip() else None
        dlg = StoryDialog(self.ctx, self, target)
        if dlg.exec() and dlg.created is not None:
            pr = self.ctx.project
            self.ctx.project_changed.emit()  # personnages et prénom de l'enfant ont pu changer
            self.ctx.dirty = True
            self.ctx.project_modified.emit()
            self._reload_list(pr.chapters.index(dlg.created))
            self.ctx.toast(f"« {dlg.created.title} » ajoutée : relisez-la, écoutez un passage, puis produisez-la.",
                           "success", 6000)

    def toggle_favorite(self) -> None:
        if self._current is not None:
            self.st_fav.setChecked(not self._current.favorite)

    def draw_cover(self) -> None:
        ch = self._current
        if ch is None:
            return
        self._commit_text()
        from ..dialogs.story import draw_story_cover

        try:
            self._set_cover(draw_story_cover(self.ctx.project, ch))
        except Exception as exc:
            self.ctx.toast(f"Couverture impossible : {exc}", "error")

    def pick_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une image de couverture", "",
                                              "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if path:
            self._set_cover(path)

    def _set_cover(self, path: str) -> None:
        if self._current is None:
            return
        self._current.cover_path = path
        self.ctx.mark_dirty()
        self._update_cover_btn()
        self._refresh_items()

    def check_age(self) -> None:
        ch = self._current
        if ch is None:
            return
        self._commit_text()
        notes = story.check_for_age(ch.text, ch.age)
        if notes:
            QMessageBox.information(self, "Vérification pour l'âge", "\n\n".join(notes))
        else:
            self.ctx.toast(f"Rien à signaler pour {story.age_profile(ch.age).label}.", "success")

    def ai_summary(self) -> None:
        ch = self._current
        if ch is None:
            return
        self._commit_text()
        if not ch.text.strip():
            self.ctx.toast("Écrivez d'abord l'histoire.", "warning")
            return
        from ...core import ai
        from .. import tasks

        def work():
            return ai.story_summary(ch.title, ch.text, ai.client_from_settings())

        def done(summary):
            if self._current is ch and summary:
                self.st_summary.setText(summary)
                self._episode_info_changed()
                self.ctx.toast("Résumé proposé.", "success")

        self.ctx.toast("DeepSeek résume l'histoire…", "info", 2500)
        self._notes_task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 7000))

    # -- bruitages, ambiances, prises au micro, réécriture --------------------------------
    def _project_dir(self):
        pr = self.ctx.project
        return pr.path.parent if pr.path is not None else None

    def _fill_sounds(self) -> None:
        from ...core import sounds

        m = self.sound_menu
        m.clear()
        listen = QMenu("Écouter", m)
        hidden = {"virgule", "generique", "transition", "notification", "roulement", "suspense", "ding",
                  "applaudissements"}
        for name, text in sounds.available(self._project_dir()):
            if name in hidden:
                continue
            m.addAction(icons.icon("music", theme.CURRENT.muted, 16), text,
                        lambda n=name: self._insert_block(f"[son: {n}]"))
            listen.addAction(text, lambda n=name: self._play_sound(n))
        m.addSeparator()
        m.addMenu(listen).setIcon(icons.icon("headphones", theme.CURRENT.text, 16))
        m.addAction(icons.icon("folder", theme.CURRENT.text, 16), "Ajouter mes propres sons…", self._open_my_sounds)

    def _fill_ambiences(self) -> None:
        from ...core import sounds

        m = self.amb_menu
        m.clear()
        listen = QMenu("Écouter", m)
        for key, text in sounds.AMBIENCE_LABELS.items():
            m.addAction(icons.icon("wave", theme.CURRENT.info, 16), text,
                        lambda k=key: self._insert_block(f"[ambiance: {k}]"))
            listen.addAction(text, lambda k=key: self._play_ambience(k))
        m.addSeparator()
        m.addAction(icons.icon("x", theme.CURRENT.text, 16), "Fin de l'ambiance", lambda: self._insert_block(
            "[ambiance: fin]"))
        m.addMenu(listen).setIcon(icons.icon("headphones", theme.CURRENT.text, 16))

    def _play_ambience(self, key: str) -> None:
        from ...core import sounds

        self.ctx.play(sounds.ensure_ambience(key), f"Ambiance — {sounds.AMBIENCE_LABELS.get(key, key)}")

    def _play_sound(self, name: str) -> None:
        from ...core import sounds

        path = sounds.resolve(name, self._project_dir())
        if path is not None:
            self.ctx.play(path, f"Son — {name}")

    def _open_my_sounds(self) -> None:
        from ...core import sounds
        from ..main_window import open_path

        open_path(sounds.user_dir())
        self.ctx.toast("Déposez vos fichiers audio (MP3, WAV…) dans ce dossier, puis écrivez « [son: nom du fichier] » "
                       "ou « [ambiance: nom du fichier] ». "
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
