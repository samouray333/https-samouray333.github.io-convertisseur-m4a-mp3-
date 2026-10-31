"""Page Contrôle : passages parlés sans VF en tête, puis répliques à risque, puis éléments écartés du doublage."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QTableWidget,
                               QTableWidgetItem)

from ...core import coverage, pipeline, qc
from ...core import project as project_io
from .. import tasks, theme
from ..widgets import Card, button, card_title, label
from .base import Page

log = logging.getLogger(__name__)


def fmt_t(t: float) -> str:
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:05.2f}"


def _table(cols: list[str], stretch: int, height: int = 190) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setWordWrap(True)
    hh = t.horizontalHeader()
    for c in range(len(cols)):
        hh.setSectionResizeMode(c, QHeaderView.Stretch if c == stretch else QHeaderView.ResizeToContents)
    t.setMinimumHeight(height)
    return t


class ReviewPage(Page):
    name = "review"

    def __init__(self, ctx, window):
        super().__init__(ctx, "Contrôle", "Ce qui reste à vérifier, du plus important au moins important : passages "
                         "parlés sans VF, répliques en échec ou à risque, éléments écartés.", scroll=True)
        self.window_ = window
        self._gaps: list[dict] = []
        self._lines: list = []
        self._dropped: list[dict] = []

        top = QHBoxLayout()
        top.setSpacing(18)
        sumc = Card(spacing=8)
        sumc.add(card_title("Couverture de la VF", "", "shield"))
        self.cov = label("", "Muted", wrap=True)
        self.cov.setStyleSheet("font-size: 12pt; font-weight: 600;")
        sumc.add(self.cov)
        self.qc_info = label("", "Hint", wrap=True)
        sumc.add(self.qc_info)
        self.src_info = label("", "Hint", wrap=True)
        sumc.add(self.src_info)
        top.addWidget(sumc, 1)
        imgc = Card(margins=(12, 12, 12, 12), spacing=6)
        self.image = QLabel()
        self.image.setFixedSize(320, 180)
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setStyleSheet("background: rgba(0,0,0,0.25); border-radius: 8px;")
        imgc.add(self.image)
        self.image_info = label("Choisissez une ligne pour voir l'image.", "Hint", wrap=True)
        self.image_info.setMaximumWidth(320)
        imgc.add(self.image_info)
        top.addWidget(imgc)
        self.body.addLayout(top)

        # 1. passages parlés sans VF
        gc = Card(spacing=8)
        gc.add(card_title("Passages parlés sans VF", "Quelqu'un parle mais aucune réplique ne sera doublée ici. Là où "
                          "il n'y a pas de VF, la voix d'origine reste audible (réglable dans Paramètres).", "alert"))
        self.gap_table = _table(["Début", "Durée", "État", "Indice"], 3)
        self.gap_table.itemSelectionChanged.connect(self._gap_selected)
        self.gap_table.doubleClicked.connect(lambda _i: self._gap_listen())
        gc.add(self.gap_table)
        row = QHBoxLayout()
        self.g_listen = button("Écouter", "play", tooltip="Écouter le passage (voix d'origine)")
        self.g_listen.clicked.connect(self._gap_listen)
        self.g_extend = button("Étendre la réplique voisine", "merge",
                               tooltip="Le sous-titre d'à côté couvre ce passage (même phrase dite plus longtemps)")
        self.g_extend.clicked.connect(self._gap_extend)
        self.g_type = button("Saisir le texte", "edit", tooltip="Écrire la réplique française de ce passage")
        self.g_type.clicked.connect(self._gap_type)
        self.g_asr = button("Transcrire", "mic", tooltip="Faire écrire ce passage par Whisper, puis le traduire")
        self.g_asr.clicked.connect(self._gap_transcribe)
        self.g_vo = button("Garder la VO", "volume", tooltip="Cri, bruit, mot court : la voix d'origine reste")
        self.g_vo.clicked.connect(lambda: self._gap_state("vo"))
        self.g_skip = button("Ne pas doubler", "x", tooltip="Pas de la parole (bruit, musique)")
        self.g_skip.clicked.connect(lambda: self._gap_state("ignored"))
        self.g_open = button("Remettre à traiter", "refresh")
        self.g_open.clicked.connect(lambda: self._gap_state("open"))
        for b in (self.g_listen, self.g_extend, self.g_type, self.g_asr):
            row.addWidget(b)
        row.addStretch(1)
        gc.add(row)
        row2 = QHBoxLayout()
        for b in (self.g_vo, self.g_skip, self.g_open):
            row2.addWidget(b)
        row2.addStretch(1)
        gc.add(row2)
        self.body.addWidget(gc)

        # 2. répliques en échec ou à risque
        lc = Card(spacing=8)
        lc.add(card_title("Répliques à vérifier", "Échecs de voix d'abord, puis lecture douteuse des sous-titres, "
                          "réplique trop longue ou trop accélérée, personne incertaine.", "captions"))
        self.line_table = _table(["#", "Début", "Problème", "Original", "Français"], 3, 230)
        self.line_table.itemSelectionChanged.connect(self._line_selected)
        self.line_table.doubleClicked.connect(lambda _i: self._line_go())
        lc.add(self.line_table)
        row = QHBoxLayout()
        self.l_go = button("Aller à la réplique", "chevron-right", "primary")
        self.l_go.clicked.connect(self._line_go)
        self.l_vo = button("Écouter VO", "play")
        self.l_vo.clicked.connect(lambda: self._line_listen(False))
        self.l_vf = button("Écouter VF", "headphones")
        self.l_vf.clicked.connect(lambda: self._line_listen(True))
        self.l_ok = button("Vérifiée", "check")
        self.l_ok.clicked.connect(self._line_ok)
        for b in (self.l_go, self.l_vo, self.l_vf, self.l_ok):
            row.addWidget(b)
        row.addStretch(1)
        lc.add(row)
        self.body.addWidget(lc)

        # 3. éléments écartés
        dc = Card(spacing=8)
        dc.add(card_title("Écartés du doublage", "Panneaux, génériques, lectures illisibles, passages douteux pour "
                          "Whisper : rien n'est retiré sans être listé ici.", "list"))
        self.drop_table = _table(["Début", "Raison", "Texte"], 2, 150)
        self.drop_table.itemSelectionChanged.connect(self._drop_selected)
        dc.add(self.drop_table)
        row = QHBoxLayout()
        self.d_listen = button("Écouter", "play")
        self.d_listen.clicked.connect(self._drop_listen)
        self.d_dub = button("Doubler quand même", "plus", tooltip="Créer une réplique avec ce texte")
        self.d_dub.clicked.connect(self._drop_dub)
        row.addWidget(self.d_listen)
        row.addWidget(self.d_dub)
        row.addStretch(1)
        dc.add(row)
        self.body.addWidget(dc)
        self.body.addStretch(1)

        ctx.lines_changed.connect(self.refresh)
        ctx.runner.finished.connect(lambda *_a: self.refresh())
        self.refresh()

    # -- données ----------------------------------------------------------------------
    @property
    def project(self):
        return self.ctx.project

    def on_show(self) -> None:
        self.refresh()

    def on_project_changed(self) -> None:
        self.image.clear()
        self.refresh()

    def refresh(self) -> None:
        pr = self.project
        busy = self.ctx.runner.running
        for t in (self.gap_table, self.line_table, self.drop_table):
            t.setRowCount(0)
        if pr is None:
            self.cov.setText("Aucun projet.")
            self.qc_info.setText("")
            self.src_info.setText("")
            self._enable()
            return
        try:
            coverage.update(pr)
        except Exception:  # noqa: BLE001 - projet sans dossier de travail
            log.debug("Couverture indisponible", exc_info=True)
        text, problems = coverage.summary(pr)
        color = theme.CURRENT.success if not problems else theme.CURRENT.warning
        self.cov.setText(text)
        self.cov.setStyleSheet(f"font-size: 12pt; font-weight: 600; color: {color};")
        self.qc_info.setText(qc.summary(pr) if pr.lines else "Pas encore de répliques : lancez la création de la VF.")
        subs = pr.subs
        src = {"track": "piste de sous-titres", "file": "fichier de sous-titres", "ocr": "sous-titres de l'image",
               "none": "voix (Whisper)"}.get(subs.kind, "à déterminer")
        lang = pr.settings.detected_language or pr.settings.source_language
        self.src_info.setText(f"Texte : {src}" + (f" ({subs.count})" if subs.count else "") +
                              f" · audio : {lang}" + (f" ({pr.settings.language_confidence:.0%})"
                                                      if pr.settings.language_confidence else ""))
        # passages : à traiter d'abord
        order = {"open": 0, "vo": 1, "ignored": 2}
        self._gaps = sorted(pr.gaps, key=lambda g: (order.get(g.get("state"), 3), g["start"]))
        for g in self._gaps:
            self._row(self.gap_table, [fmt_t(g["start"]), f"{g['end'] - g['start']:.1f} s",
                                       coverage.GAP_STATES.get(g.get("state"), ""), g.get("text", "")],
                      theme.CURRENT.warning if g.get("state") == "open" else None)
        # répliques : échecs, puis problèmes du contrôle qualité
        failed = coverage.failed_lines(pr) if pr.step_done("dub") else []
        risky = [ln for ln in pr.lines if ln.issues and ln not in failed]
        self._lines = failed + sorted(risky, key=lambda x: x.start)
        index = {ln.id: i for i, ln in enumerate(pr.lines)}
        for ln in self._lines:
            msg = ln.message if ln in failed else "; ".join(m for _c, m in ln.issues)
            self._row(self.line_table, [str(index.get(ln.id, 0) + 1), fmt_t(ln.start), msg, ln.en, ln.fr],
                      theme.CURRENT.danger if ln in failed else None)
        self._dropped = coverage.load_dropped(pr)
        for d in self._dropped:
            self._row(self.drop_table, [fmt_t(d.get("start", 0)), d.get("reason", ""), d.get("text", "")])
        self.setEnabled(True)
        self._enable(busy)

    def _row(self, table: QTableWidget, values: list[str], color: str | None = None) -> None:
        r = table.rowCount()
        table.insertRow(r)
        for c, v in enumerate(values):
            it = QTableWidgetItem(str(v))
            if color and c in (0, 2):
                it.setForeground(QColor(color))
            table.setItem(r, c, it)

    def _enable(self, busy: bool = False) -> None:
        pr = self.project
        g = self._sel(self.gap_table, self._gaps)
        ln = self._sel(self.line_table, self._lines)
        d = self._sel(self.drop_table, self._dropped)
        cues_lang = pr is not None and pipeline.has_cues(pr) and pr.text_language != pr.settings.language
        for b in (self.g_listen,):
            b.setEnabled(g is not None)
        for b in (self.g_type, self.g_vo, self.g_skip, self.g_open):
            b.setEnabled(g is not None and not busy)
        self.g_extend.setEnabled(g is not None and not busy and
                                 coverage.nearest_line(pr, g["start"], g["end"]) is not None)
        # texte des sous-titres dans une autre langue que l'audio : une transcription ne se traduirait pas pareil
        self.g_asr.setEnabled(g is not None and not busy and not cues_lang)
        for b in (self.l_go, self.l_vo):
            b.setEnabled(ln is not None)
        self.l_vf.setEnabled(ln is not None and bool(ln.audio))
        self.l_ok.setEnabled(ln is not None and not busy)
        self.d_listen.setEnabled(d is not None)
        self.d_dub.setEnabled(d is not None and not busy and bool(d.get("text")))

    @staticmethod
    def _sel(table: QTableWidget, items: list):
        rows = table.selectionModel().selectedRows()
        if not rows:
            return None
        r = rows[0].row()
        return items[r] if 0 <= r < len(items) else None

    # -- image ------------------------------------------------------------------------
    def _show_image(self, t: float, text: str) -> None:
        pr = self.project
        if pr is None or not Path(pr.source_video).is_file():
            return
        from ...core import media

        target = project_io.work_dir(pr) / "controle" / f"{int(t * 10):07d}.jpg"
        self.image_info.setText(f"{fmt_t(t)} · {text[:120]}" if text else fmt_t(t))

        def done(path):
            pm = QPixmap(str(path))
            if not pm.isNull():
                self.image.setPixmap(pm.scaled(self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        if target.exists():
            done(target)
            return
        tasks.run(media.thumbnail, Path(pr.source_video), t, target, 480, on_done=done, on_error=lambda *_a: None)

    def _play_vo(self, a: float, b: float, title: str) -> None:
        src = pipeline.wf(self.project, pipeline.ORIGINAL)
        if not src.exists():
            self.ctx.toast("Le son n'est pas encore extrait.", "info")
            return
        self.ctx.play(src, title, max(0.0, a - 0.3), b + 0.3)

    # -- passages ---------------------------------------------------------------------
    def _gap_selected(self) -> None:
        g = self._sel(self.gap_table, self._gaps)
        self._enable(self.ctx.runner.running)
        if g is not None:
            self._show_image((g["start"] + g["end"]) / 2, g.get("text", ""))

    def _gap_listen(self) -> None:
        g = self._sel(self.gap_table, self._gaps)
        if g is not None:
            self._play_vo(g["start"], g["end"], f"VO — passage à {fmt_t(g['start'])}")

    def _gap_state(self, state: str) -> None:
        g = self._sel(self.gap_table, self._gaps)
        if g is None:
            return
        self.ctx.checkpoint("passage parlé")
        coverage.set_state(self.project, g["start"], g["end"], state)
        if state in ("vo", "ignored") or g.get("state") in ("vo", "ignored"):
            self.project.mark_step("mix", False)  # la voix d'origine à cet endroit dépend de ce choix
        self.ctx.mark_dirty()
        self.refresh()

    def _dub_lines(self, title: str, lines, translate: bool) -> None:
        pr = self.project

        def fn(job, ids):
            if translate:
                job.step = "translate"
                pipeline.step_translate(pr, job, only=ids, force=True)
            job.step = "dub"
            pipeline.step_dub(pr, job, only=ids)

        self.window_.pages["dubbing"]._line_job(title, lines, fn, ["translate", "dub"] if translate else ["dub"],
                                                checkpoint=False)
        self.ctx.lines_changed.emit()

    def _gap_extend(self) -> None:
        g = self._sel(self.gap_table, self._gaps)
        if g is None:
            return
        self.ctx.checkpoint("réplique élargie")
        ln = coverage.extend_neighbor(self.project, g["start"], g["end"])
        if ln is None:
            self.ctx.toast("Aucune réplique assez proche (1,5 s) : saisissez le texte.", "info")
            return
        self.ctx.mark_dirty()
        self._dub_lines("Réplique élargie", [ln], False)

    def _gap_type(self) -> None:
        g = self._sel(self.gap_table, self._gaps)
        if g is None:
            return
        text, ok = QInputDialog.getText(self, "Réplique française",
                                        f"Ce qui est dit de {fmt_t(g['start'])} à {fmt_t(g['end'])} (en français) :")
        if not ok or not text.strip():
            return
        self.ctx.checkpoint("réplique ajoutée")
        ln = coverage.add_line(self.project, g["start"], g["end"], en="", fr=text)
        self.ctx.mark_dirty()
        self._dub_lines("Réplique ajoutée", [ln], False)

    def _gap_transcribe(self) -> None:
        g = self._sel(self.gap_table, self._gaps)
        pr = self.project
        if g is None:
            return
        from ...core import engines

        tool = engines.get_tool("whisper")
        if tool is None or not tool.is_ready():
            self.ctx.toast("Whisper n'est pas installé (page Moteurs IA).", "warning")
            return
        _voice, voice16 = pipeline.speech_source(pr)
        a, b = max(0.0, g["start"] - 0.2), g["end"] + 0.2

        def work():
            res = tool.transcribe_words(voice16, pr.settings.language, pr.settings.whisper_model, start=a, end=b)
            return " ".join(s[2] for s in res.get("segments", [])).strip()

        def done(text):
            if not text:
                self.ctx.toast("Whisper n'entend rien de clair ici : saisissez le texte ou gardez la VO.", "info",
                               5000)
                return
            self.ctx.checkpoint("réplique transcrite")
            ln = coverage.add_line(pr, g["start"], g["end"], en=text, source="")
            self.ctx.mark_dirty()
            self._dub_lines("Réplique transcrite", [ln], True)

        self.ctx.toast("Transcription du passage…", "info")
        tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(f"Transcription impossible : {m}",
                                                                              "error", 6000))

    # -- répliques --------------------------------------------------------------------
    def _line_selected(self) -> None:
        ln = self._sel(self.line_table, self._lines)
        self._enable(self.ctx.runner.running)
        if ln is not None:
            self._show_image((ln.start + ln.end) / 2, ln.en)

    def _line_go(self) -> None:
        ln = self._sel(self.line_table, self._lines)
        if ln is None:
            return
        self.ctx.navigate("dubbing")
        self.window_.pages["dubbing"]._select(ln.id)

    def _line_listen(self, vf: bool) -> None:
        ln = self._sel(self.line_table, self._lines)
        if ln is None:
            return
        if vf and ln.audio:
            self.ctx.play(project_io.resolve(self.project, ln.audio), f"VF — {ln.fr[:60]}")
        else:
            self._play_vo(ln.start, ln.end, f"VO — {ln.en[:60]}")

    def _line_ok(self) -> None:
        ln = self._sel(self.line_table, self._lines)
        if ln is None:
            return
        self.ctx.checkpoint("réplique vérifiée")
        ln.checked = True
        ln.issues = []
        self.ctx.mark_dirty()
        self.refresh()

    # -- écartés ----------------------------------------------------------------------
    def _drop_selected(self) -> None:
        d = self._sel(self.drop_table, self._dropped)
        self._enable(self.ctx.runner.running)
        if d is not None:
            self._show_image((float(d["start"]) + float(d["end"])) / 2, d.get("text", ""))

    def _drop_listen(self) -> None:
        d = self._sel(self.drop_table, self._dropped)
        if d is not None:
            self._play_vo(float(d["start"]), float(d["end"]), f"VO — {d.get('text', '')[:60]}")

    def _drop_dub(self) -> None:
        d = self._sel(self.drop_table, self._dropped)
        if d is None:
            return
        self.ctx.checkpoint("réplique ajoutée")
        ln = coverage.add_line(self.project, float(d["start"]), float(d["end"]), en=str(d.get("text", "")),
                               source=self.project.subs.kind if self.project.subs.kind != "none" else "")
        self.ctx.mark_dirty()
        self._dub_lines("Réplique ajoutée", [ln], True)
