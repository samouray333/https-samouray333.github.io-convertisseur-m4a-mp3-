"""Page Production : génération des chapitres, suivi, réécoute et nouvelles prises."""

from __future__ import annotations

import json
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar, QScrollArea,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...core import engines, renderer
from ...core.engines.neural import LOG_LISTENERS
from ...core.textproc import format_duration
from .. import icons, tasks, theme
from ..widgets import (Badge, Card, IconButton, ProgressRing, StatTile, ToggleSwitch, button, card_title, format_eta,
                       label)
from .base import Page

STATUS = {
    "done": ("Prêt", "success"),
    "running": ("En cours", "accent"),
    "pending": ("À produire", "muted"),
    "partial": ("Partiel", "info"),
    "error": ("Erreur", "danger"),
}


class Bridge(QObject):
    progress = Signal(int, int, str)
    segment = Signal(str, int, str)
    chapter = Signal(str, str)
    log = Signal(str)
    eta = Signal(float)
    engine_log = Signal(str, str)


class ProductionPage(Page):
    name = "production"

    def __init__(self, ctx):
        super().__init__(ctx, "Production", "Générez l'audio de chaque chapitre. Les passages déjà produits sont "
                         "conservés : seuls les textes modifiés sont régénérés.")
        self.bridge = Bridge()
        self.bridge.progress.connect(self._on_progress)
        self.bridge.segment.connect(self._on_segment)
        self.bridge.chapter.connect(self._on_chapter)
        self.bridge.log.connect(self._log)
        self.bridge.eta.connect(self._on_eta)
        self.bridge.engine_log.connect(lambda e, m: self._log(f"[{e}] {m}"))
        LOG_LISTENERS.append(lambda e, m: self.bridge.engine_log.emit(e, m))

        self.renderer: renderer.Renderer | None = None
        self.plan: list[renderer.RenderChapter] = []
        self._chapter_status: dict[str, str] = {}
        self._seg_status: dict[tuple[str, int], str] = {}
        self._started = 0.0

        self.go_btn = button("Tout produire", "zap", "primary")
        self.go_btn.clicked.connect(lambda: self.start(None))
        self.sel_btn = button("Produire la sélection", "play")
        self.sel_btn.clicked.connect(self._start_selection)
        self.pause_btn = button("Pause", "pause")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.stop_btn = button("Arrêter", "stop", "danger")
        self.stop_btn.clicked.connect(self.stop)
        for b in (self.sel_btn, self.pause_btn, self.stop_btn, self.go_btn):
            self.header.add_action(b)

        # ---- tableau de bord
        dash = Card(margins=(22, 18, 22, 18))
        dl = QHBoxLayout()
        dl.setSpacing(24)
        self.ring = ProgressRing(150, 13)
        dl.addWidget(self.ring)
        right = QVBoxLayout()
        right.setSpacing(10)
        self.status_lbl = label("Prêt à produire", "SectionTitle")
        self.detail_lbl = label("", "Muted", wrap=True)
        right.addWidget(self.status_lbl)
        right.addWidget(self.detail_lbl)
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.t_chapters = StatTile("book", "0/0", "chapitres prêts")
        self.t_segments = StatTile("wave", "0/0", "passages synthétisés", theme.CURRENT.info)
        self.t_eta = StatTile("clock", "—", "temps restant estimé", theme.CURRENT.warning)
        self.t_duration = StatTile("headphones", "—", "durée estimée du livre", theme.CURRENT.success)
        for t in (self.t_chapters, self.t_segments, self.t_eta, self.t_duration):
            tiles.addWidget(t, 1)
        right.addLayout(tiles)
        dl.addLayout(right, 1)
        dash.add(dl)
        self.body.addWidget(dash)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        self.body.addWidget(split, 1)

        # ---- chapitres + passages
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(12)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Chapitre", "État", "Progression", "Durée", ""])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 80)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.itemSelectionChanged.connect(self._show_segments)
        ll.addWidget(self.table, 3)

        seg_card = Card(margins=(14, 12, 14, 12), spacing=8)
        sh = QHBoxLayout()
        self.seg_title = label("Passages", "SectionTitle")
        sh.addWidget(self.seg_title, 1)
        retake = button("Nouvelle prise", "refresh", tooltip="Régénère le passage sélectionné avec une autre "
                        "interprétation")
        retake.clicked.connect(self._retake)
        play_seg = button("Écouter", "play")
        play_seg.clicked.connect(self._play_segment)
        sh.addWidget(play_seg)
        sh.addWidget(retake)
        seg_card.add(sh)
        self.segments = QListWidget()
        self.segments.setWordWrap(True)
        self.segments.itemDoubleClicked.connect(lambda _i: self._play_segment())
        seg_card.add(self.segments)
        ll.addWidget(seg_card, 2)
        split.addWidget(left)

        # ---- réglages + journal
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 0, 0, 0)
        sl.setSpacing(12)
        st = Card(margins=(18, 14, 18, 14), spacing=10)
        st.add(card_title("Réglages de lecture", "S'appliquent à tout le livre.", "sliders"))
        g = QGridLayout()
        g.setVerticalSpacing(8)
        g.setHorizontalSpacing(10)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.7, 1.4)
        self.speed.setSingleStep(0.05)
        self.speed.setSuffix(" ×")
        self.p_sentence = self._ms_spin(0, 3000)
        self.p_para = self._ms_spin(0, 5000)
        self.p_head = self._ms_spin(0, 6000)
        self.p_start = self._ms_spin(500, 5000)
        self.p_end = self._ms_spin(1000, 5000)
        rows = [("Vitesse de lecture", self.speed), ("Pause entre phrases", self.p_sentence),
                ("Pause entre paragraphes", self.p_para), ("Pause après un titre", self.p_head),
                ("Silence en début de chapitre", self.p_start), ("Silence en fin de chapitre", self.p_end)]
        for i, (t, w) in enumerate(rows):
            g.addWidget(label(t, "Muted"), i, 0)
            g.addWidget(w, i, 1)
        st.add(g)
        self.t_announce = ToggleSwitch("Annoncer le titre de chaque chapitre")
        self.t_numbers = ToggleSwitch("Lire nombres, dates et heures en toutes lettres")
        self.t_abbr = ToggleSwitch("Développer les abréviations (M., Dr, etc.)")
        self.t_trim = ToggleSwitch("Uniformiser les silences des voix")
        for t in (self.t_announce, self.t_numbers, self.t_abbr, self.t_trim):
            st.add(t)
        for w in (self.speed, self.p_sentence, self.p_para, self.p_head, self.p_start, self.p_end):
            w.valueChanged.connect(self._settings_changed)
        for t in (self.t_announce, self.t_numbers, self.t_abbr, self.t_trim):
            t.toggled.connect(self._settings_changed)
        sl.addWidget(st)
        lg = Card(margins=(14, 12, 14, 12), spacing=6)
        lg.add(label("Journal", "SectionTitle"))
        self.console = QPlainTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(2000)
        lg.add(self.console)
        lg.setMinimumHeight(200)
        sl.addWidget(lg, 1)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setWidget(side)
        side_scroll.setMinimumWidth(400)
        split.addWidget(side_scroll)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([880, 440])

        self._plan_timer = QTimer(self)
        self._plan_timer.setSingleShot(True)
        self._plan_timer.timeout.connect(self.rebuild_plan)
        ctx.project_modified.connect(lambda: (not ctx.rendering) and self._plan_timer.start(1200))
        ctx.voices_changed.connect(lambda: self._plan_timer.start(500))
        self._loading = False
        self._update_buttons()

    @staticmethod
    def _ms_spin(lo: int, hi: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(50)
        s.setSuffix(" ms")
        return s

    # -- projet & plan -----------------------------------------------------------------
    def on_project_changed(self) -> None:
        self._load_settings()
        self.plan = []
        self.table.setRowCount(0)
        self.segments.clear()
        self.console.clear()
        self.rebuild_plan()

    def on_show(self) -> None:
        if not self.ctx.rendering:
            self.rebuild_plan()

    def _load_settings(self) -> None:
        p = self.ctx.project.production
        self._loading = True
        self.speed.setValue(p.speed)
        self.p_sentence.setValue(p.pause_sentence_ms)
        self.p_para.setValue(p.pause_paragraph_ms)
        self.p_head.setValue(p.pause_heading_ms)
        self.p_start.setValue(p.chapter_head_ms)
        self.p_end.setValue(p.chapter_tail_ms)
        self.t_announce.setChecked(p.announce_chapter_titles)
        self.t_numbers.setChecked(p.normalize_numbers)
        self.t_abbr.setChecked(p.expand_abbreviations)
        self.t_trim.setChecked(p.trim_silence)
        self._loading = False

    def _settings_changed(self, *_a) -> None:
        if self._loading:
            return
        p = self.ctx.project.production
        p.speed = round(self.speed.value(), 2)
        p.pause_sentence_ms = self.p_sentence.value()
        p.pause_paragraph_ms = self.p_para.value()
        p.pause_heading_ms = self.p_head.value()
        p.chapter_head_ms = self.p_start.value()
        p.chapter_tail_ms = self.p_end.value()
        p.announce_chapter_titles = self.t_announce.isChecked()
        p.normalize_numbers = self.t_numbers.isChecked()
        p.expand_abbreviations = self.t_abbr.isChecked()
        p.trim_silence = self.t_trim.isChecked()
        self.ctx.mark_dirty()

    def rebuild_plan(self) -> None:
        if self.ctx.rendering or not self.ctx.project.chapters:
            if not self.ctx.project.chapters:
                self.status_lbl.setText("Aucun projet")
                self.detail_lbl.setText("Importez un document pour commencer.")
            return
        project = self.ctx.project

        def work():
            plan = renderer.build_plan(project, self.ctx.library)
            stats = {}
            for rc in plan:
                done, total = renderer.chapter_progress(project, rc)
                current = renderer.chapter_is_current(project, rc)
                dur = None
                if current:
                    try:
                        dur = json.loads(renderer.chapter_manifest(project, rc.id).read_text("utf-8"))["duration"]
                    except Exception:
                        dur = None
                stats[rc.id] = (done, total, current, dur)
            return plan, stats

        self._plan_task = tasks.run(work, on_done=self._plan_ready,
                                    on_error=lambda m, _t: self._plan_error(m))

    def _plan_error(self, msg: str) -> None:
        self.status_lbl.setText("Production impossible")
        self.detail_lbl.setText(msg)

    def _plan_ready(self, res) -> None:
        if self.ctx.rendering:
            return
        plan, stats = res
        self.plan = plan
        self._chapter_status.clear()
        self._seg_status.clear()
        sel = self._selected_ids()
        self.table.setRowCount(len(plan))
        total_seg = done_seg = ready = 0
        total_dur = 0.0
        est = 0.0
        for row, rc in enumerate(plan):
            done, total, current, dur = stats[rc.id]
            total_seg += total
            done_seg += done
            status = "done" if current else ("partial" if done else "pending")
            if current:
                ready += 1
            self._chapter_status[rc.id] = status
            speed = max(0.3, self.ctx.project.production.speed)
            est += dur if dur else rc.char_count / 14.5 / speed + (rc.head_ms + rc.tail_ms) / 1000
            total_dur += dur or 0
            self._set_row(row, rc, status, done, total, dur)
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.UserRole) in sel:
                self.table.selectRow(row)
        self.t_chapters.set_value(f"{ready}/{len(plan)}")
        self.t_segments.set_value(f"{done_seg}/{total_seg}")
        self.t_duration.set_value(format_duration(est))
        frac = done_seg / total_seg if total_seg else 0.0
        self.ring.set_value(frac, sub="du livre")
        warnings = sorted({w for rc in plan for w in rc.warnings})
        if ready == len(plan) and plan:
            self.status_lbl.setText("Livre prêt à exporter ✨")
            self.detail_lbl.setText("Tous les chapitres sont produits. Rendez-vous dans Export pour créer vos "
                                    "fichiers.")
        else:
            self.status_lbl.setText("Prêt à produire")
            voices = {self.ctx.library.get(s.voice_id).name for rc in plan for s in rc.segments
                      if self.ctx.library.get(s.voice_id)}
            self.detail_lbl.setText(f"Voix utilisées : {', '.join(sorted(voices)) or '—'}."
                                    + (" " + " ".join(warnings) if warnings else ""))
        if not self.table.selectedItems() and plan:
            self.table.selectRow(0)
        self._update_buttons()

    def _set_row(self, row: int, rc, status: str, done: int, total: int, dur: float | None) -> None:
        kind_icon = {"opening": "sparkles", "closing": "award"}.get(rc.kind, "book")
        it = QTableWidgetItem(icons.icon(kind_icon, theme.CURRENT.muted, 16), rc.title)
        it.setData(Qt.UserRole, rc.id)
        self.table.setItem(row, 0, it)
        text, kind = STATUS[status]
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(6, 0, 6, 0)
        hl.addWidget(Badge(text, kind))
        self.table.setCellWidget(row, 1, holder)
        bar_holder = QWidget()
        bl = QHBoxLayout(bar_holder)
        bl.setContentsMargins(6, 0, 10, 0)
        bar = QProgressBar()
        bar.setRange(0, max(1, total))
        bar.setValue(done)
        bl.addWidget(bar)
        self.table.setCellWidget(row, 2, bar_holder)
        self.table.setItem(row, 3, QTableWidgetItem(format_duration(dur) if dur else "—"))
        actions = QWidget()
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 0, 6, 0)
        al.setSpacing(2)
        play = IconButton("play", "Écouter le chapitre", 30, 14, color=theme.CURRENT.accent)
        play.setEnabled(status == "done")
        play.clicked.connect(lambda _=False, cid=rc.id, t=rc.title: self._play_chapter(cid, t))
        redo = IconButton("refresh", "Produire ce chapitre", 30, 14)
        redo.clicked.connect(lambda _=False, cid=rc.id: self.start([cid]))
        al.addWidget(play)
        al.addWidget(redo)
        self.table.setCellWidget(row, 4, actions)

    def _row_of(self, chapter_id: str) -> int:
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.data(Qt.UserRole) == chapter_id:
                return r
        return -1

    def _selected_ids(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows if self.table.item(r, 0)]

    def _rc(self, chapter_id: str):
        return next((rc for rc in self.plan if rc.id == chapter_id), None)

    # -- passages ----------------------------------------------------------------------
    def _show_segments(self) -> None:
        ids = self._selected_ids()
        self.segments.clear()
        if not ids:
            return
        rc = self._rc(ids[0])
        if rc is None:
            return
        self.seg_title.setText(f"Passages — {rc.title}")
        p = theme.CURRENT
        for s in rc.segments:
            st = self._seg_status.get((rc.id, s.index))
            if st is None:
                st = "done" if renderer.cache_path(self.ctx.project, s.key).exists() else "pending"
            ic, col = {"done": ("check", p.success), "running": ("clock", p.accent), "error": ("alert", p.danger)}.get(
                st, ("clock", p.faint))
            v = self.ctx.library.get(s.voice_id)
            it = QListWidgetItem(icons.icon(ic, col, 16), f"{s.index + 1}. {s.text}" + (f"   — {v.name}" if v else ""))
            it.setData(Qt.UserRole, s.index)
            self.segments.addItem(it)

    def _current_segment(self):
        ids = self._selected_ids()
        it = self.segments.currentItem()
        if not ids or it is None:
            return None, None
        rc = self._rc(ids[0])
        if rc is None:
            return None, None
        idx = it.data(Qt.UserRole)
        return rc, next((s for s in rc.segments if s.index == idx), None)

    def _play_segment(self) -> None:
        rc, seg = self._current_segment()
        if seg is None:
            return
        path = renderer.cache_path(self.ctx.project, seg.key)
        if path.exists():
            self.ctx.play(path, f"{rc.title} — passage {seg.index + 1}")
        else:
            self.ctx.toast("Ce passage n'a pas encore été produit.", "warning")

    def _retake(self) -> None:
        rc, seg = self._current_segment()
        if seg is None or self.ctx.rendering:
            return
        r = renderer.Renderer(self.ctx.project, self.ctx.library)
        self.ctx.toast(f"Nouvelle prise du passage {seg.index + 1}…", "info", 2000)

        def work():
            path = r.regenerate_segment(seg)
            if all(renderer.cache_path(self.ctx.project, s.key).exists() for s in rc.segments):
                r.assemble(rc)
            return path

        def done(path):
            self.ctx.play(path, f"{rc.title} — passage {seg.index + 1} (nouvelle prise)")
            self.rebuild_plan()

        self._retake_task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 6000))

    def _play_chapter(self, chapter_id: str, title: str) -> None:
        path = renderer.chapter_output(self.ctx.project, chapter_id)
        if path.exists():
            self.ctx.play(path, title)

    # -- production --------------------------------------------------------------------
    def _start_selection(self) -> None:
        ids = self._selected_ids()
        if not ids:
            self.ctx.toast("Sélectionnez un ou plusieurs chapitres.", "warning")
            return
        self.start(ids)

    def start(self, chapter_ids: list[str] | None) -> None:
        if self.ctx.rendering:
            return
        pr = self.ctx.project
        if not pr.included_chapters():
            self.ctx.toast("Aucun chapitre à produire.", "warning")
            return
        try:
            plan = renderer.build_plan(pr, self.ctx.library, chapter_ids)
        except Exception as exc:
            QMessageBox.warning(self, "Production impossible", str(exc))
            return
        missing = set()
        for rc in plan:
            for s in rc.segments:
                v = self.ctx.library.get(s.voice_id)
                eng = engines.get_engine(v.engine) if v else None
                if eng is None or eng.status()[0] != engines.READY:
                    missing.add(eng.info.name if eng else (v.engine if v else "?"))
        if missing:
            r = QMessageBox.question(self, "Moteur non disponible",
                                     "Ces moteurs de voix ne sont pas prêts : " + ", ".join(sorted(missing)) +
                                     ".\n\nOuvrir la page Moteurs IA pour les installer ?")
            if r == QMessageBox.Yes:
                self.ctx.navigate("engines")
            return
        if pr.path is None:
            self.ctx.toast("Enregistrez d'abord le projet (Ctrl+S).", "warning")
            if not self.ctx.window.save_project():
                return
        else:
            self.ctx.window.save_project()
        cb = renderer.RenderCallbacks(
            progress=lambda d, t, m: self.bridge.progress.emit(d, t, m),
            segment=lambda c, i, s: self.bridge.segment.emit(c, i, s),
            chapter=lambda c, s: self.bridge.chapter.emit(c, s),
            log=lambda m: self.bridge.log.emit(m),
            eta=lambda s: self.bridge.eta.emit(s),
        )
        self.renderer = renderer.Renderer(pr, self.ctx.library, cb)
        self.ctx.rendering = True
        self._started = time.time()
        self._update_buttons()
        self.ring.set_busy(True)
        self.status_lbl.setText("Production en cours…")
        self._log(f"Production de {len(plan)} piste(s)…")
        self._task = tasks.run(self.renderer.render, plan, on_done=self._finished, on_error=self._failed)

    def _toggle_pause(self) -> None:
        if self.renderer is None:
            return
        if self.renderer.pause_event.is_set():
            self.renderer.pause_event.clear()
            self.pause_btn.setText("Pause")
            self.pause_btn.setIcon(icons.icon("pause", theme.CURRENT.text, 18))
            self.status_lbl.setText("Production en cours…")
        else:
            self.renderer.pause_event.set()
            self.pause_btn.setText("Reprendre")
            self.pause_btn.setIcon(icons.icon("play", theme.CURRENT.text, 18))
            self.status_lbl.setText("En pause (le passage en cours se termine)")

    def stop(self) -> None:
        if self.renderer is not None:
            self.renderer.cancel()
            self.status_lbl.setText("Arrêt en cours…")

    def _finished(self, report) -> None:
        self.ctx.rendering = False
        self.ring.set_busy(False)
        self.renderer = None
        self.pause_btn.setText("Pause")
        self._update_buttons()
        elapsed = format_duration(report.elapsed)
        if report.cancelled:
            self.ctx.toast("Production arrêtée. Les passages produits sont conservés.", "warning")
        elif report.failed_segments:
            self.ctx.toast(f"Production terminée avec {len(report.failed_segments)} erreur(s). Consultez le journal.",
                           "error", 7000)
        else:
            self.ctx.toast(f"Production terminée en {elapsed} 🎧", "success", 5000)
        for w in report.warnings:
            self._log("⚠ " + w)
        self.ctx.render_finished.emit()
        self.rebuild_plan()

    def _failed(self, msg: str, tb: str) -> None:
        self.ctx.rendering = False
        self.ring.set_busy(False)
        self.renderer = None
        self._update_buttons()
        self._log("ERREUR : " + msg)
        QMessageBox.warning(self, "Erreur de production", msg)
        self.rebuild_plan()

    def _update_buttons(self) -> None:
        running = self.ctx.rendering
        has = bool(self.ctx.project.chapters)
        self.go_btn.setEnabled(not running and has)
        self.sel_btn.setEnabled(not running and has)
        self.pause_btn.setEnabled(running)
        self.stop_btn.setEnabled(running)

    # -- signaux du moteur de rendu ----------------------------------------------------
    def _on_progress(self, done: int, total: int, msg: str) -> None:
        frac = done / total if total else 0
        self.ring.set_value(frac, sub=f"{done}/{total}")
        self.t_segments.set_value(f"{done}/{total}")
        self.detail_lbl.setText(msg)

    def _on_eta(self, seconds: float) -> None:
        self.t_eta.set_value(format_eta(seconds))

    def _on_segment(self, chapter_id: str, index: int, status: str) -> None:
        self._seg_status[(chapter_id, index)] = status
        row = self._row_of(chapter_id)
        if row >= 0 and status == "done":
            holder = self.table.cellWidget(row, 2)
            bar = holder.findChild(QProgressBar) if holder else None
            if bar is not None:
                bar.setValue(bar.value() + 1)
        ids = self._selected_ids()
        if ids and ids[0] == chapter_id:
            for i in range(self.segments.count()):
                it = self.segments.item(i)
                if it.data(Qt.UserRole) == index:
                    p = theme.CURRENT
                    ic, col = {"done": ("check", p.success), "running": ("clock", p.accent),
                               "error": ("alert", p.danger)}.get(status, ("clock", p.faint))
                    it.setIcon(icons.icon(ic, col, 16))
                    if status == "running":
                        self.segments.scrollToItem(it)
                    break

    def _on_chapter(self, chapter_id: str, status: str) -> None:
        self._chapter_status[chapter_id] = status
        row = self._row_of(chapter_id)
        if row < 0:
            return
        holder = self.table.cellWidget(row, 1)
        badge = holder.findChild(Badge) if holder else None
        if badge is not None:
            text, kind = STATUS.get(status, STATUS["pending"])
            badge.set(text, kind)
        if status == "running":
            self.table.selectRow(row)
        if status == "done":
            actions = self.table.cellWidget(row, 4)
            if actions is not None:
                btns = actions.findChildren(IconButton)
                if btns:
                    btns[0].setEnabled(True)
        ready = sum(1 for s in self._chapter_status.values() if s == "done")
        self.t_chapters.set_value(f"{ready}/{len(self.plan)}")

    def _log(self, msg: str) -> None:
        self.console.appendPlainText(time.strftime("%H:%M:%S  ") + msg)
