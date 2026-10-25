"""Page File d'attente : plusieurs vidéos doublées l'une après l'autre, sans surveillance."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QMessageBox,
                               QTableWidget, QTableWidgetItem)

from ...config import settings
from ...core import jobqueue, pipeline
from ...core import project as project_io
from ...core import series as series_lib
from ...core.engines import shutdown_all
from ...core.textproc import format_duration
from ..widgets import Card, DropZone, ToggleSwitch, button, card_title, format_eta, label
from .base import Page

log = logging.getLogger(__name__)
TITLE = "File d'attente"


class QueuePage(Page):
    name = "queue"

    def __init__(self, ctx, window):
        super().__init__(ctx, "File d'attente", "Ajoutez plusieurs vidéos : elles sont doublées l'une après l'autre "
                         "(la nuit par exemple). Un arrêt ou une coupure ne fait rien perdre : la file reprend où "
                         "elle s'était arrêtée.")
        self.window_ = window
        self.active = False
        self.current = ""

        add = Card()
        top = QHBoxLayout()
        drop = DropZone("Glissez ici une ou plusieurs vidéos", "Chacune devient un projet dans Documents\\Doublys",
                        "upload", 120)
        drop.files_dropped.connect(self.add_videos)
        drop.clicked.connect(self.choose_videos)
        top.addWidget(drop, 2)
        opts = Card(obj="CardFlat", margins=(14, 12, 14, 12))
        opts.add(label("Série des nouvelles vidéos", "Muted"))
        self.series = QComboBox()
        opts.add(self.series)
        opts.add(label("Leurs personnages, leurs voix, leur langue et leur glossaire sont repris.", "Hint", wrap=True))
        self.t_export = ToggleSwitch("Exporter la vidéo doublée à la fin", True)
        opts.add(self.t_export)
        top.addWidget(opts, 1)
        add.add(top)
        self.body.addWidget(add)

        lst = Card()
        lst.add(card_title("Vidéos", "", "list"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Vidéo", "Durée", "État", "Détail"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 110)
        self.table.doubleClicked.connect(lambda _i: self.open_selected())
        lst.add(self.table)
        row = QHBoxLayout()
        self.start_btn = button("Lancer la file", "play", "primary")
        self.start_btn.clicked.connect(self.start)
        self.stop_btn = button("Arrêter", "stop-circle", "danger")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.hide()
        rm = button("Retirer", "x")
        rm.clicked.connect(self.remove_selected)
        clean = button("Retirer les terminées", "check")
        clean.clicked.connect(self.remove_done)
        op = button("Ouvrir le projet", "folder")
        op.clicked.connect(self.open_selected)
        for b in (self.start_btn, self.stop_btn):
            row.addWidget(b)
        row.addStretch(1)
        for b in (op, rm, clean):
            row.addWidget(b)
        lst.add(row)
        self.status = label("", "Muted", wrap=True)
        lst.add(self.status)
        self.body.addWidget(lst, 1)

        ctx.runner.progress.connect(self._progress)
        ctx.runner.finished.connect(self._finished)

    # -- affichage --------------------------------------------------------------------
    def on_show(self) -> None:
        self._fill_series()
        self.refresh()

    def _fill_series(self) -> None:
        cur = self.series.currentData() or settings().get("queue_series", "")
        self.series.blockSignals(True)
        self.series.clear()
        self.series.addItem("Aucune", "")
        for name in series_lib.list_series():
            self.series.addItem(name, name)
        self.series.setCurrentIndex(max(0, self.series.findData(cur)))
        self.series.blockSignals(False)

    def refresh(self) -> None:
        entries = jobqueue.items()
        self.table.setRowCount(len(entries))
        total = 0.0
        for i, e in enumerate(entries):
            dur = ""
            try:
                import json

                d = json.loads(Path(e.path).read_text(encoding="utf-8")).get("video", {}).get("duration", 0)
                dur = format_duration(float(d or 0))
                if e.state in (jobqueue.WAITING, jobqueue.RUNNING):
                    total += float(d or 0)
            except (OSError, ValueError):
                pass
            vals = [e.title, dur, jobqueue.STATE_LABELS.get(e.state, e.state), e.message or e.result]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, e.path)
                if c == 3:
                    it.setToolTip(v)
                self.table.setItem(i, c, it)
        pending = jobqueue.pending_count()
        self.start_btn.setVisible(not self.active)
        self.start_btn.setEnabled(pending > 0 and not self.ctx.runner.running)
        self.stop_btn.setVisible(self.active)
        if not self.active:
            self.status.setText(f"{pending} vidéo(s) en attente, {format_duration(total)} de vidéo au total."
                                if pending else "La file est vide.")

    # -- ajout --------------------------------------------------------------------------
    def choose_videos(self) -> None:
        start = str(settings().get("last_video_dir") or Path.home())
        files, _ = QFileDialog.getOpenFileNames(self, "Vidéos à doubler", start, project_io.VIDEO_FILTER)
        if files:
            self.add_videos(files)

    def add_videos(self, files: list[str]) -> None:
        name = self.series.currentData() or ""
        settings().set("queue_series", name)
        created, errors = [], []
        for f in files:
            if Path(f).suffix.lower() == ".doublys":
                created.append(f)
                continue
            try:
                pr = project_io.create_project(f, settings().projects_dir())
                if name:
                    series_lib.apply_settings(pr, name)
                    project_io.save_project(pr)
                created.append(str(pr.path))
                settings().add_recent(pr.path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f).name} : {exc}")
        if files:
            settings().set("last_video_dir", str(Path(files[0]).parent))
        n = jobqueue.add(created)
        self.refresh()
        if errors:
            QMessageBox.warning(self, "Vidéos ignorées", "\n".join(errors))
        if n:
            self.ctx.toast(f"{n} vidéo(s) ajoutée(s) à la file.", "success")

    def _selected_paths(self) -> list[str]:
        rows = sorted({ix.row() for ix in self.table.selectionModel().selectedRows()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows if self.table.item(r, 0)]

    def remove_selected(self) -> None:
        paths = [p for p in self._selected_paths() if p != self.current]
        jobqueue.remove(paths)
        self.refresh()

    def remove_done(self) -> None:
        jobqueue.remove([e.path for e in jobqueue.items() if e.state == jobqueue.DONE])
        self.refresh()

    def open_selected(self) -> None:
        paths = self._selected_paths()
        if paths and not self.active:
            self.window_.open_project(paths[0])

    # -- exécution ------------------------------------------------------------------------
    def start(self) -> None:
        if self.ctx.runner.running:
            self.ctx.toast("Un traitement est déjà en cours.", "warning")
            return
        missing = [e for e in jobqueue.items() if e.state in (jobqueue.WAITING, jobqueue.RUNNING)
                   and not Path(e.path).exists()]
        for e in missing:
            jobqueue.update(e.path, state=jobqueue.ERROR, message="Projet introuvable")
        self.active = True
        self._next()

    def stop(self) -> None:
        self.active = False
        if self.current:
            jobqueue.update(self.current, state=jobqueue.WAITING, message="Arrêtée : reprendra à cet endroit")
        self.ctx.runner.stop()
        self.refresh()

    def _next(self) -> None:
        if not self.active:
            self.refresh()
            return
        item = jobqueue.next_waiting()
        if item is None:
            self.active = False
            self.current = ""
            self.refresh()
            self.ctx.toast("File d'attente terminée ✔", "success", 8000)
            return
        try:
            cur = self.ctx.project
            if cur is not None and cur.path is not None and Path(cur.path) == Path(item.path):
                pr = cur  # projet ouvert : on travaille sur le même objet
            else:
                pr = project_io.load_project(item.path)
        except Exception as exc:  # noqa: BLE001
            jobqueue.update(item.path, state=jobqueue.ERROR, message=str(exc))
            self._next()
            return
        self.current = item.path
        jobqueue.update(item.path, state=jobqueue.RUNNING, message="")
        export = self.t_export.isChecked()
        plan = pipeline.steps_to_run(pr) + (["export"] if export else [])

        def save():
            project_io.save_project(pr)

        def work(job):
            pipeline.run_all(pr, job, save=save)
            files = pipeline.export_files(pr, job) if export else []
            save()
            return files

        self.refresh()
        self.ctx.runner.start(f"{TITLE} : {pr.display_title}", plan, work, on_stop=[shutdown_all])

    def _progress(self, step, frac, msg, overall, remaining) -> None:
        if not self.active or not self.ctx.runner.title.startswith(TITLE):
            return
        rest = f" · reste {format_eta(remaining)}" if remaining >= 0 else ""
        self.status.setText(f"{Path(self.current).stem} : {msg} ({int(overall * 100)} %{rest})")
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.data(Qt.UserRole) == self.current:
                self.table.item(r, 3).setText(f"{int(overall * 100)} % · {msg}")

    def _finished(self, ok: bool, msg: str, result) -> None:
        if not self.ctx.runner.title.startswith(TITLE) or not self.current:
            return
        path, self.current = self.current, ""
        if ok:
            out = str(result[0]) if isinstance(result, list) and result else ""
            jobqueue.update(path, state=jobqueue.DONE, message="", result=out)
        elif msg == "Traitement arrêté.":
            jobqueue.update(path, state=jobqueue.WAITING, message="Arrêtée : reprendra à cet endroit")
        else:
            jobqueue.update(path, state=jobqueue.ERROR, message=msg[:300])
        cur = self.ctx.project
        if cur is not None and cur.path is not None and Path(cur.path) == Path(path):
            self.ctx.project_changed.emit()
        shutdown_all()  # libère la mémoire des modèles entre deux vidéos
        self.refresh()
        if self.active:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(500, self._next)
