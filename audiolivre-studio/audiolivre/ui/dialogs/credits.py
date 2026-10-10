"""Rédaction des crédits d'ouverture et de fin."""

from __future__ import annotations

from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QGridLayout, QHBoxLayout, QPlainTextEdit,
                               QToolButton, QVBoxLayout)

from ...core import renderer
from ...core.exporter import credits_text
from ...core.textproc import parse_script
from .. import icons
from ..widgets import button, card_title, label

VARIABLES = [("{title}", "Titre"), ("{subtitle}", "Sous-titre"), ("{author}", "Auteur"),
             ("{narrator}", "Narrateur"), ("{publisher}", "Éditeur"), ("{year}", "Année"),
             ("{copyright}", "Copyright")]

TEMPLATE_OPENING = ("{title}.\n\n{subtitle_sentence}Écrit par {author}.\n\nLu par {narrator}.\n\n"
                    "[pause 1s]")
TEMPLATE_CLOSING = ("Fin.\n\n[pause 1s]\n\nVous venez d'écouter {title}, écrit par {author}, lu par {narrator}.\n\n"
                    "{copyright}")


class CreditsDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        e = ctx.project.export
        self.setWindowTitle("Crédits d'ouverture et de fin")
        self.resize(980, 700)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title("Crédits d'ouverture et de fin",
                                 "Écrivez librement : plusieurs paragraphes, remerciements, dédicace, mentions "
                                 "légales… Les balises du manuscrit fonctionnent aussi ([pause 2s], [calme], "
                                 "@Personnage:).", "award"))

        vr = QHBoxLayout()
        vr.addWidget(label("Voix des crédits", "Muted"))
        self.voice = QComboBox()
        self.voice.addItem("Voix du narrateur", "")
        for v in ctx.library.all():
            self.voice.addItem(icons.icon("mic" if v.is_clone else "user", v.color, 16), v.name, v.id)
        self.voice.setCurrentIndex(max(0, self.voice.findData(e.credits_voice_id)))
        vr.addWidget(self.voice, 1)
        vr.addStretch(1)
        lay.addLayout(vr)

        vars_row = QHBoxLayout()
        vars_row.addWidget(label("Insérer :", "Hint"))
        for var, name in VARIABLES:
            b = QToolButton()
            b.setText(name)
            b.setToolTip(f"Insère {var} (remplacé par la valeur saisie dans Métadonnées)")
            b.clicked.connect(lambda _=False, v=var: self._insert(v))
            vars_row.addWidget(b)
        vars_row.addStretch(1)
        lay.addLayout(vars_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        self.editors: dict[str, QPlainTextEdit] = {}
        for col, (kind, title, text) in enumerate((("opening", "Crédits d'ouverture", e.opening_credits),
                                                    ("closing", "Crédits de fin", e.closing_credits))):
            grid.addWidget(label(title, "Muted"), 0, col)
            ed = QPlainTextEdit(text)
            ed.setObjectName("Editor")
            ed.textChanged.connect(self._update_counts)
            self.editors[kind] = ed
            grid.addWidget(ed, 1, col)
            row = QHBoxLayout()
            listen = button("Écouter", "headphones")
            listen.clicked.connect(lambda _=False, k=kind: self._listen(k))
            prev = button("Aperçu de lecture", "eye")
            prev.clicked.connect(lambda _=False, k=kind: self._preview(k))
            reset = button("Modèle", "refresh", "ghost", tooltip="Remplace par un modèle de crédits à compléter")
            reset.clicked.connect(lambda _=False, k=kind: self._template(k))
            row.addWidget(listen)
            row.addWidget(prev)
            row.addStretch(1)
            row.addWidget(reset)
            grid.addLayout(row, 2, col)
        lay.addLayout(grid, 1)
        self.counts = label("", "Hint")
        lay.addWidget(self.counts)
        lay.addWidget(label("Audible/ACX demande au minimum le titre, l'auteur et le narrateur au début, et « Fin » "
                            "(ou une formule équivalente) à la fin.", "Faint", wrap=True))

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Enregistrer", "check", "primary")
        ok.clicked.connect(self._save)
        bottom.addWidget(cancel)
        bottom.addWidget(ok)
        lay.addLayout(bottom)
        self._focused = self.editors["opening"]
        QApplication.instance().focusChanged.connect(self._focus_changed)
        self._update_counts()

    # ------------------------------------------------------------------------------
    def _focus_changed(self, _old, new) -> None:
        if new in self.editors.values():
            self._focused = new

    def done(self, result: int) -> None:
        QApplication.instance().focusChanged.disconnect(self._focus_changed)
        super().done(result)

    def _insert(self, var: str) -> None:
        self._focused.insertPlainText(var)
        self._focused.setFocus()

    def _template(self, kind: str) -> None:
        self.editors[kind].setPlainText(TEMPLATE_OPENING if kind == "opening" else TEMPLATE_CLOSING)

    def _update_counts(self) -> None:
        meta = self.ctx.project.metadata
        parts = []
        for kind, name in (("opening", "ouverture"), ("closing", "fin")):
            words = len(credits_text(self.editors[kind].toPlainText(), meta).split())
            parts.append(f"{name} : {words} mots (≈ {max(1, round(words / 2.6))} s)")
        self.counts.setText("Durée estimée — " + " · ".join(parts))

    def _apply(self) -> None:
        e = self.ctx.project.export
        e.opening_credits = self.editors["opening"].toPlainText().strip()
        e.closing_credits = self.editors["closing"].toPlainText().strip()
        e.credits_voice_id = self.voice.currentData() or ""

    def _chapter(self, kind: str):
        e = self.ctx.project.export
        saved = (e.opening_credits, e.closing_credits, e.credits_voice_id)
        self._apply()
        try:
            return renderer.credits_chapter(self.ctx.project, kind)
        finally:
            e.opening_credits, e.closing_credits, e.credits_voice_id = saved

    def _listen(self, kind: str) -> None:
        ch = self._chapter(kind)
        if not ch.text.strip():
            self.ctx.toast("Les crédits sont vides.", "warning")
            return
        voice = renderer.VoiceResolver(self.ctx.project, self.ctx.library).narrator(ch)
        text = " ".join(i.text for i in parse_script(ch.text) if i.kind in ("para", "heading"))
        self.ctx.preview_voice(voice, text)

    def _preview(self, kind: str) -> None:
        from .reading_preview import ReadingPreviewDialog

        ReadingPreviewDialog(self.ctx, self._chapter(kind), self).exec()

    def _save(self) -> None:
        self._apply()
        self.ctx.mark_dirty()
        self.accept()
