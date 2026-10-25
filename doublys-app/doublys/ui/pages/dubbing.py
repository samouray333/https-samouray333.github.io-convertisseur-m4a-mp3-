"""Page Doublage : bouton automatique, étapes relançables, tableau des répliques."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QTableWidget, QTableWidgetItem)

from ... import paths
from ...core import ai, audio, engines, media, mixer, pipeline, refs, segment, timing
from ...core import project as project_io
from ...core.engines.neural import LOG_LISTENERS
from ...core.models import LINE_STATES, STEP_LABELS, STEPS, Person
from ...core.speakers import COLORS
from ...core.textproc import format_duration
from .. import icons, tasks, theme
from ..videopreview import VideoPreview
from ..widgets import Card, IconButton, button, card_title, format_eta, label
from .base import Page

log = logging.getLogger(__name__)

COLS = ["#", "Début", "Durée", "Personne", "Anglais", "Français", "Calage", "État"]
C_NUM, C_START, C_LEN, C_PERSON, C_EN, C_FR, C_FIT, C_STATE = range(len(COLS))
STATE_KIND = {"ok": "success", "tempo": "success", "rate": "info", "long": "warning", "error": "danger", "": "muted"}


def fmt_t(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


class StepRow(QFrame):
    def __init__(self, page: "DubbingPage", step: str):
        super().__init__()
        self.step = step
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(16, 16)
        lay.addWidget(self.dot)
        self.name = label(STEP_LABELS[step])
        lay.addWidget(self.name, 1)
        self.info = label("", "Faint")
        lay.addWidget(self.info)
        self.btn = IconButton("refresh", "Relancer cette étape", 26, 14)
        m = QMenu(self)
        m.addAction(icons.icon("refresh", theme.CURRENT.text, 16), "Relancer cette étape seule",
                    lambda: page.run_step(step))
        m.addAction(icons.icon("chevron-right", theme.CURRENT.text, 16), "Relancer à partir d'ici jusqu'au bout",
                    lambda: page.run_from(step))
        self.btn.setMenu(m)
        self.btn.setPopupMode(self.btn.ToolButtonPopupMode.InstantPopup)
        lay.addWidget(self.btn)

    def set_state(self, state: str, detail: str = "") -> None:
        p = theme.CURRENT
        ic, color = {"done": ("check", p.success), "run": ("refresh", p.accent), "skip": ("x", p.faint)}.get(
            state, ("clock", p.faint))
        self.dot.setPixmap(icons.pixmap(ic, color, 16))
        self.name.setStyleSheet("font-weight: 700;" if state == "run" else "")
        self.info.setText(detail[:42])
        self.info.setToolTip(detail)


class DubbingPage(Page):
    name = "dubbing"

    def __init__(self, ctx, window):
        super().__init__(ctx, "Doublage", "Une vidéo, un bouton : la version française se crée toute seule.")
        self.window_ = window
        self._rows: dict[str, int] = {}
        self._filling = False
        self._thumb_task = None

        top = QHBoxLayout()
        top.setSpacing(18)
        # vignette
        vcard = Card(margins=(14, 14, 14, 14), spacing=8)
        self.thumb = VideoPreview(320, 180)
        vcard.add(self.thumb)
        self.video_info = label("", "Hint", wrap=True)
        self.video_info.setMaximumWidth(320)
        vcard.add(self.video_info)
        top.addWidget(vcard)

        # commande
        run = Card(spacing=10)
        r1 = QHBoxLayout()
        self.auto_btn = button("Créer la VF automatiquement", "wand", "primary")
        self.auto_btn.setMinimumHeight(46)
        self.auto_btn.setStyleSheet("font-size: 12pt; padding: 10px 22px;")
        self.auto_btn.clicked.connect(self.run_auto)
        self.stop_btn = button("Arrêter", "stop-circle", "danger")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.hide()
        r1.addWidget(self.auto_btn)
        r1.addWidget(self.stop_btn)
        r1.addStretch(1)
        self.open_btn = button("Ouvrir la vidéo doublée", "external")
        self.open_btn.clicked.connect(self._open_result)
        self.open_btn.hide()
        r1.addWidget(self.open_btn)
        run.add(r1)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        run.add(self.bar)
        r2 = QHBoxLayout()
        self.status = label("Prêt.", "Muted", wrap=True)
        self.eta = label("", "Faint")
        r2.addWidget(self.status, 1)
        r2.addWidget(self.eta)
        run.add(r2)
        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(4)
        self.step_rows: dict[str, StepRow] = {}
        for i, s in enumerate(STEPS):
            row = StepRow(self, s)
            self.step_rows[s] = row
            grid.addWidget(row, i % 5, i // 5)
        run.add(grid)
        top.addWidget(run, 1)
        self.body.addLayout(top)

        # tableau des répliques
        tc = Card(spacing=8, margins=(16, 14, 16, 14))
        th = QHBoxLayout()
        th.addWidget(card_title("Répliques", "Double-cliquez sur le français pour le modifier ; la voix sera refaite.",
                                "captions"), 1)
        self.only_issues = QCheckBox("Seulement les répliques à revoir")
        self.only_issues.toggled.connect(self._apply_filter)
        th.addWidget(self.only_issues, 0, Qt.AlignBottom)
        tc.add(th)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setWordWrap(True)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        for c, w in ((C_NUM, 44), (C_START, 76), (C_LEN, 60), (C_PERSON, 96), (C_FIT, 110), (C_STATE, 110)):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            self.table.setColumnWidth(c, w)
        hh.setSectionResizeMode(C_EN, QHeaderView.Stretch)
        hh.setSectionResizeMode(C_FR, QHeaderView.Stretch)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.doubleClicked.connect(self._double_clicked)
        tc.add(self.table)
        acts = QHBoxLayout()
        acts.setSpacing(6)
        self.actions = {}
        for key, text, ic, tip in [
            ("vo", "VO", "headphones", "Écouter la voix d'origine"),
            ("vf", "VF", "volume", "Écouter la voix française seule"),
            ("mix", "Mixé", "wave", "Écouter le mélange final"),
            ("preview", "Aperçu", "film", "Voir la réplique avec l'image et le sous-titre, ici (double-clic sur le "
                                             "numéro)"),
            ("retranslate", "Retraduire", "languages", "Nouvelle traduction automatique"),
            ("shorten", "Raccourcir", "scissors", "DeepSeek propose une version plus courte qui tient dans le temps"),
            ("redo", "Refaire la voix", "refresh", "Nouvelle prise de la voix française"),
            ("merge", "Fusionner", "merge", "Fusionner avec la réplique suivante"),
            ("split", "Couper", "scissors", "Couper la réplique en deux"),
            ("delete", "Supprimer", "trash", "Supprimer les répliques choisies (non doublées)"),
        ]:
            b = button(text, ic, "danger" if key == "delete" else "default", tooltip=tip)
            b.clicked.connect(lambda _=False, k=key: self.action(k))
            acts.addWidget(b)
            self.actions[key] = b
        acts.addStretch(1)
        tc.add(acts)
        self.body.addWidget(tc, 1)

        self.console = QPlainTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(3000)
        self.console.setFixedHeight(90)
        self.body.addWidget(self.console)

        r = ctx.runner
        r.started.connect(self._on_started)
        r.progress.connect(self._on_progress)
        r.log_line.connect(self._log)
        r.line_changed.connect(self._refresh_line)
        r.finished.connect(self._on_finished)
        LOG_LISTENERS.append(self._engine_log)
        self._engine_lines: list[str] = []
        self._flush = QTimer(self)
        self._flush.timeout.connect(self._flush_engine_log)
        self._flush.start(500)
        ctx.people_changed.connect(self.fill_table)
        ctx.lines_changed.connect(self.fill_table)
        self._update_buttons()

    # -- projet ---------------------------------------------------------------------------
    @property
    def project(self):
        return self.ctx.project

    def on_project_changed(self) -> None:
        pr = self.project
        self.console.clear()
        self.open_btn.setVisible(bool(pr and pr.last_export and Path(pr.last_export).exists()))
        if pr is None:
            self.header.title.setText("Doublage")
            self.video_info.setText("Aucun projet : glissez une vidéo sur l'accueil.")
            self.thumb.clear()
        else:
            self.header.title.setText(f"Doublage — {pr.display_title}")
            v = pr.video
            self.video_info.setText(f"{Path(pr.source_video).name}\n{format_duration(v.duration)} · {v.width}×"
                                    f"{v.height} · {v.video_codec} / {v.audio_codec}")
            self._project_thumbnail()
        self.fill_steps()
        self.fill_table()
        self._update_buttons()

    def on_show(self) -> None:
        self.fill_steps()

    def _project_thumbnail(self) -> None:
        pr = self.project
        try:
            t = project_io.work_file(pr, "vignette.jpg")
        except Exception:
            return
        if t.exists():
            self._set_thumb(t)
            return
        src = Path(pr.source_video)
        if src.is_file():
            self._thumb_task = tasks.run(media.thumbnail, src, pr.video.duration * 0.1, t, 640,
                                         on_done=self._set_thumb, on_error=lambda *_: None)

    def _set_thumb(self, path) -> None:
        if not self.thumb.is_playing():
            self.thumb.show_image(path)

    # -- étapes ---------------------------------------------------------------------------
    def fill_steps(self, running: str = "") -> None:
        pr = self.project
        for s, row in self.step_rows.items():
            if pr is None:
                row.set_state("todo")
                continue
            if s == "separate" and not pr.settings.separate:
                row.set_state("skip", "désactivée")
            elif s == running:
                row.set_state("run", "en cours…")
            elif pr.step_done(s):
                row.set_state("done", pr.steps[s].get("detail", ""))
            else:
                row.set_state("todo")
            row.btn.setEnabled(not self.ctx.runner.running)

    def _update_buttons(self) -> None:
        running = self.ctx.runner.running
        has = self.project is not None
        self.auto_btn.setVisible(not running)
        self.auto_btn.setEnabled(has)
        self.stop_btn.setVisible(running)
        lines = bool(has and self.project.lines)
        for k, b in self.actions.items():
            b.setEnabled(lines and (not running or k in ("vo", "vf", "mix", "preview")))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers if running else
                                   QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        if self.project is not None and not running:
            nxt = self.project.next_step()
            self.auto_btn.setText("Créer la VF automatiquement" if not self.project.steps else
                                  ("Terminer la VF automatiquement" if nxt else "Refaire l'export de la VF"))
            todo = pipeline.steps_to_run(self.project) + ["export"]
            est = pipeline.estimate_seconds(self.project, todo)
            idle = self.status.text() in ("Prêt.", "") or self.status.text().startswith("Temps de calcul")
            if nxt and idle:
                self.status.setText(f"Temps de calcul estimé sur cet ordinateur : environ {format_eta(est)} "
                                    "(l'ordinateur ne se mettra pas en veille ; vous pouvez arrêter et reprendre).")

    def _start(self, title: str, plan: list[str], fn) -> None:
        if self.project is None:
            return
        if self.project.path is None:
            return
        self.ctx.runner.start(title, plan, fn, on_stop=[engines.shutdown_all])

    def _save(self) -> None:
        try:
            self.ctx.save()
        except Exception as exc:
            log.warning("Enregistrement impossible : %s", exc)

    def run_auto(self) -> None:
        pr = self.project
        if pr is None or self.ctx.runner.running:
            return
        missing = self._missing_engines(pipeline.steps_to_run(pr))
        if missing:
            r = QMessageBox.question(self, "Moteurs à installer",
                                     "Il manque des moteurs pour doubler hors ligne :\n• " + "\n• ".join(missing)
                                     + "\n\nLes installer maintenant (une seule fois) ?")
            if r == QMessageBox.Yes:
                from .home import REQUIRED

                self.ctx.navigate("engines")
                self.window_.pages["engines"].install_many(REQUIRED)
            return
        plan = pipeline.steps_to_run(pr) + ["export"]

        def work(job):
            pipeline.run_all(pr, job, save=self._save)
            return pipeline.export_files(pr, job)

        self._start("Création de la VF", plan, work)

    def _missing_engines(self, steps: list[str]) -> list[str]:
        out = []
        need = {"separate": "analysis", "speakers": "analysis", "transcribe": "whisper"}
        if self.project.settings.translator != "deepseek":
            need["translate"] = "analysis"
        for s in steps:
            tool = need.get(s)
            if tool and not engines.get_tool(tool).is_ready():
                name = engines.get_tool(tool).info.name
                if name not in out:
                    out.append(name)
        if "dub" in steps:
            from ...core import dubvoice

            for p in self.project.people or [Person(name="—")]:
                ok, msg = dubvoice.engine_ready(self.project, p)
                if not ok and msg not in out:
                    out.append(msg)
        return out

    def run_step(self, step: str) -> None:
        pr = self.project
        if pr is None or self.ctx.runner.running:
            return
        self._start(STEP_LABELS[step], [step], lambda job: pipeline.run_step(pr, step, job, self._save))

    def run_from(self, step: str) -> None:
        pr = self.project
        if pr is None or self.ctx.runner.running:
            return
        plan = pipeline.steps_to_run(pr, step)
        self._start(f"À partir de « {STEP_LABELS[step]} »", plan,
                    lambda job: pipeline.run_all(pr, job, save=self._save, start=step))

    def stop(self) -> None:
        self.status.setText("Arrêt en cours…")
        self.ctx.runner.stop()

    # -- signaux du traitement -------------------------------------------------------------
    def _on_started(self, title: str) -> None:
        self.bar.setValue(0)
        self.status.setText(title + "…")
        self.eta.setText("")
        self._update_buttons()
        self.fill_steps()

    def _on_progress(self, step: str, frac: float, msg: str, overall: float, remaining: float) -> None:
        self.bar.setValue(int(overall * 1000))
        name = STEP_LABELS.get(step, "Export" if step == "export" else step)
        self.status.setText(f"{name} — {msg}" if msg and msg != name else name)
        self.eta.setText(f"{int(overall * 100)} % · reste {format_eta(remaining)}" if remaining >= 0 else
                         f"{int(overall * 100)} %")
        if step in self.step_rows:
            self.fill_steps(running=step)

    def _on_finished(self, ok: bool, msg: str, result) -> None:
        self._update_buttons()
        self.fill_steps()
        self.fill_table()
        self.ctx.mark_dirty()
        self._save()
        if ok:
            self.bar.setValue(1000)
            self.eta.setText("")
            files = result if isinstance(result, list) else []
            if self.ctx.runner.title == "Aperçu rapide":
                self.status.setText("Aperçu prêt.")
            elif files:
                self.status.setText(f"VF prête : {files[0]}")
                self.open_btn.show()
                long_ = sum(1 for ln in self.project.lines if ln.state == "long")
                extra = f" {long_} réplique(s) à raccourcir (filtre « à revoir »)." if long_ else ""
                self.ctx.toast("La version française est prête !" + extra, "success", 8000)
            else:
                self.status.setText("Terminé.")
        else:
            self.status.setText(msg)
            if msg != "Traitement arrêté." and self.isVisible():
                QMessageBox.warning(self, "Doublage interrompu", msg)
            elif msg != "Traitement arrêté." and not self.window_.pages["export"].isVisible():
                self.ctx.toast(msg, "error", 8000)
        self.ctx.lines_changed.emit()

    def _log(self, msg: str) -> None:
        self.console.appendPlainText(msg)

    def _engine_log(self, engine: str, line: str) -> None:  # thread du moteur
        self._engine_lines.append(f"[{engine}] {line}")

    def _flush_engine_log(self) -> None:
        if self._engine_lines:
            lines, self._engine_lines = self._engine_lines[:50], self._engine_lines[50:]
            for ln in lines:
                if "%|" not in ln:
                    self.console.appendPlainText(ln)

    def _open_result(self) -> None:
        from ..main_window import open_path

        if self.project and self.project.last_export:
            open_path(Path(self.project.last_export))

    # -- tableau ---------------------------------------------------------------------------
    def fill_table(self) -> None:
        self._filling = True
        self.table.setRowCount(0)
        self._rows.clear()
        pr = self.project
        if pr is not None:
            pr.lines.sort(key=lambda x: x.start)
            self.table.setRowCount(len(pr.lines))
            for i, ln in enumerate(pr.lines):
                self._rows[ln.id] = i
                self._fill_row(i, ln)
        self._filling = False
        self._apply_filter()
        self._update_buttons()

    def _fill_row(self, i: int, ln) -> None:
        pr = self.project
        person = pr.person(ln.person_id)
        values = [str(i + 1), fmt_t(ln.start), f"{ln.length:.1f} s", person.name if person else "—", ln.en, ln.fr]
        fit = ""
        if ln.audio:
            fit = f"{ln.duration:.1f} s"
            if ln.rate > 1.001 or ln.tempo > 1.001:
                fit += f" · ×{ln.rate * ln.tempo:.2f}"
            if ln.expressive:
                fit += " · ✦"
        values += [fit, LINE_STATES.get(ln.state, ln.state)]
        self._filling = True
        for c, v in enumerate(values):
            it = QTableWidgetItem(v)
            if c != C_FR:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if c == C_PERSON and person is not None:
                it.setForeground(QColor(person.color))
            if c == C_STATE:
                kind = STATE_KIND.get(ln.state, "muted")
                color = {"success": theme.CURRENT.success, "warning": theme.CURRENT.warning,
                         "danger": theme.CURRENT.danger, "info": theme.CURRENT.info}.get(kind, theme.CURRENT.faint)
                it.setForeground(QColor(color))
                if ln.message:
                    it.setToolTip(ln.message)
            if c in (C_EN, C_FR):
                it.setToolTip(v)
            self.table.setItem(i, c, it)
        self._filling = False

    def _refresh_line(self, line_id: str) -> None:
        pr = self.project
        if pr is None:
            return
        i = self._rows.get(line_id)
        ln = pr.line(line_id)
        if i is None or ln is None or i >= self.table.rowCount():
            return
        self._fill_row(i, ln)

    def _apply_filter(self) -> None:
        pr = self.project
        only = self.only_issues.isChecked()
        if pr is None:
            return
        for ln in pr.lines:
            i = self._rows.get(ln.id)
            if i is not None:
                self.table.setRowHidden(i, only and ln.state not in ("long", "error", ""))

    def selected_lines(self):
        pr = self.project
        if pr is None:
            return []
        rows = sorted({ix.row() for ix in self.table.selectionModel().selectedRows()})
        return [pr.lines[r] for r in rows if r < len(pr.lines)]

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != C_FR or self.project is None:
            return
        ln = self.project.lines[item.row()]
        text = item.text().strip()
        if text == ln.fr:
            return
        ln.fr = text
        ln.fr_edited = True
        ln.state, ln.message = "", "Texte modifié : voix à refaire"
        self._dirty_audio()
        self._refresh_line(ln.id)

    def _dirty_audio(self) -> None:
        pr = self.project
        pr.mark_step("dub", False)
        pr.mark_step("mix", False)
        self.ctx.mark_dirty()
        self.fill_steps()
        self._update_buttons()

    def _double_clicked(self, index) -> None:
        if index.column() == C_EN:
            self.action("vo")
        elif index.column() in (C_NUM, C_START, C_LEN):
            self.action("preview")

    def _selection_changed(self) -> None:
        sel = self.selected_lines()
        if len(sel) != 1 or self.project is None:
            return
        ln = sel[0]
        src = Path(self.project.source_video)
        if not src.is_file():
            return
        t = ln.start + min(1.0, ln.length / 2)
        try:
            out = project_io.work_dir(self.project) / "vignettes" / f"t{int(t * 10):07d}.jpg"
        except Exception:
            return
        if out.exists():
            self._set_thumb(out)
            return
        self._thumb_task = tasks.run(media.thumbnail, src, t, out, 640, on_done=self._set_thumb,
                                     on_error=lambda *_: None)

    def _context_menu(self, pos) -> None:
        sel = self.selected_lines()
        if not sel or self.project is None:
            return
        m = QMenu(self)
        for key in ("vo", "vf", "mix", "preview", "external", None, "retranslate", "shorten", "redo", None, "merge", "split",
                    "delete"):
            if key is None:
                m.addSeparator()
                continue
            if key == "external":
                a = m.addAction(icons.icon("external", theme.CURRENT.text, 16),
                                "Ouvrir 20 s dans le lecteur de Windows", lambda: self.action("external"))
                a.setEnabled(self.actions["preview"].isEnabled())
                continue
            b = self.actions[key]
            a = m.addAction(b.icon(), b.text(), lambda k=key: self.action(k))
            a.setEnabled(b.isEnabled())
        if not self.ctx.runner.running:
            sub = m.addMenu(icons.icon("users", theme.CURRENT.text, 16), "Attribuer à")
            for p in self.project.people:
                sub.addAction(p.name, lambda p=p: self._assign(sel, p.id))
            sub.addSeparator()
            sub.addAction("Nouvelle personne", lambda: self._assign(sel, None))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _assign(self, lines, person_id) -> None:
        pr = self.project
        if person_id is None:
            n = len(pr.people)
            p = Person(name=f"P{n + 1}", color=COLORS[n % len(COLORS)])
            pr.people.append(p)
            person_id = p.id
        for ln in lines:
            ln.person_id = person_id
            ln.state = ""
        pr.mark_step("voices", False)
        self._dirty_audio()
        self.ctx.people_changed.emit()

    # -- actions -----------------------------------------------------------------------
    def action(self, key: str) -> None:
        sel = self.selected_lines()
        pr = self.project
        if pr is None:
            return
        if not sel:
            self.ctx.toast("Choisissez d'abord une réplique dans le tableau.", "info")
            return
        ln = sel[0]
        try:
            getattr(self, f"_act_{key}")(sel, ln)
        except Exception as exc:
            log.exception("Action %s", key)
            self.ctx.toast(str(exc), "error", 6000)

    def _act_vo(self, sel, ln) -> None:
        src = pipeline.wf(self.project, pipeline.ORIGINAL)
        if not src.exists():
            raise RuntimeError("Le son n'est pas encore extrait.")
        self.ctx.play(src, f"VO — {ln.en[:60]}", max(0.0, ln.start - 0.2), ln.end + 0.3)

    def _act_vf(self, sel, ln) -> None:
        if not ln.audio or not project_io.resolve(self.project, ln.audio).exists():
            raise RuntimeError("La voix française de cette réplique n'est pas encore produite.")
        self.ctx.play(project_io.resolve(self.project, ln.audio), f"VF — {ln.fr[:60]}")

    def _mix_audio(self, ln, a: float, end: float) -> tuple[Path, float, float | None]:
        """Son mixé de [a, end] : (fichier, instant du fichier qui correspond à ``a``, fin de lecture)."""
        pr = self.project
        mix_path = pipeline.wf(pr, pipeline.MIX)
        if pr.step_done("mix") and mix_path.exists():
            return mix_path, a, end
        if not ln.audio:
            raise RuntimeError("La voix française de cette réplique n'est pas encore produite.")
        # mélange rapide de la seule réplique (le mixage complet n'est pas à jour)
        sep = pr.settings.separate and pipeline.wf(pr, pipeline.BACKGROUND).exists()
        tmp = Path(tempfile.mkdtemp(dir=paths.temp_dir())) / "replique.wav"
        bg_src = pipeline.wf(pr, pipeline.BACKGROUND if sep else pipeline.ORIGINAL)
        bg, sr = refs.read_span(bg_src, a, end)
        if not sep:
            bg = bg * audio.db_to_lin(pr.settings.no_separation_duck_db)
        voice, _vsr = audio.read_audio(project_io.resolve(pr, ln.audio), mixer.SR)
        bg = audio.resample(bg, sr, mixer.SR)
        off = int((ln.start - a) * mixer.SR)
        n = max(len(bg), off + len(voice))
        out = np.zeros(n, dtype=np.float32)
        out[:len(bg)] += bg
        out[off:off + len(voice)] += voice
        audio.write_audio(tmp, np.clip(out, -1, 1), mixer.SR, subtype="PCM_16")
        return tmp, 0.0, None

    def _act_mix(self, sel, ln) -> None:
        a = max(0.0, ln.start - 0.5)
        path, t0, end = self._mix_audio(ln, a, ln.start + max(ln.length, ln.duration) + 0.6)
        self.ctx.play(path, f"Mixé — {ln.fr[:60]}", t0, end)

    def _act_preview(self, sel, ln) -> None:
        """Aperçu dans la page : images de la vidéo synchronisées avec le son mixé et le sous-titre."""
        pr = self.project
        a = max(0.0, ln.start - 1.0)
        end = min(pr.video.duration or 1e9, a + min(20.0, max(ln.length, ln.duration) + 2.5))
        path, t0, stop = self._mix_audio(ln, a, end)
        frames_dir = Path(tempfile.mkdtemp(dir=paths.temp_dir()))
        fps = 12.0
        subs = [(x.start, x.start + max(x.length, x.duration), x.fr) for x in pr.lines
                if x.fr and x.start < end and x.start + max(x.length, x.duration) > a]
        self.status.setText("Préparation de l'aperçu…")

        def done(frames):
            self.status.setText(f"Aperçu de la réplique {pr.lines.index(ln) + 1}" if ln in pr.lines else "")
            if not frames:
                self.ctx.toast("Aucune image extraite de la vidéo.", "warning")
                return
            self.ctx.play(path, f"Aperçu — {ln.fr[:60]}", t0, stop)
            self.thumb.play(frames, fps, a, self.ctx.player, t0, subs)

        tasks.run(media.extract_frames, Path(pr.source_video), a, end - a, frames_dir, fps, 480,
                  on_done=done, on_error=lambda m, _t: self.ctx.toast(f"Aperçu impossible : {m}", "error"))

    def _act_external(self, sel, ln) -> None:
        pr = self.project
        mix_path = pipeline.wf(pr, pipeline.MIX)
        if not mix_path.exists():
            raise RuntimeError("Le mixage n'est pas encore fait : lancez la création de la VF.")
        out = project_io.work_dir(pr) / "apercu-replique.mp4"
        self.ctx.toast("Préparation de l'extrait…", "info", 2500)

        def done(path):
            from ..main_window import open_path

            open_path(path)

        tasks.run(media.preview_clip, Path(pr.source_video), mix_path, out, max(0.0, ln.start - 2.0), 20.0,
                  on_done=done, on_error=lambda m, _t: self.ctx.toast(f"Aperçu impossible : {m}", "error"))

    def _line_job(self, title: str, lines, fn, plan: list[str] | None = None) -> None:
        """Traitement de quelques répliques ; le mixage sera refait par « Terminer la VF »."""
        ids = [x.id for x in lines]

        def work(job):
            fn(job, ids)
            return None

        self._dirty_audio()
        self._start(title, plan or ["dub"], work)

    def _act_retranslate(self, sel, ln) -> None:
        pr = self.project

        def fn(job, ids):
            job.step = "translate"
            pipeline.step_translate(pr, job, only=ids, force=True)
            job.step = "dub"
            pipeline.step_dub(pr, job, only=ids)

        self._line_job("Nouvelle traduction", sel, fn, ["translate", "dub"])

    def _act_redo(self, sel, ln) -> None:
        pr = self.project
        for x in sel:
            x.seed = (x.seed or 0) + 1

        def fn(job, ids):
            job.step = "dub"
            pipeline.step_dub(pr, job, only=ids, force=True)

        self._line_job("Nouvelle prise de voix", sel, fn)

    def _act_shorten(self, sel, ln) -> None:
        pr = self.project
        try:
            client = ai.client_from_settings()
        except ai.AIError as exc:
            raise RuntimeError(f"{exc} (le raccourcissement utilise DeepSeek ; vous pouvez aussi modifier le texte "
                               "à la main).") from None

        def fn(job, ids):
            job.step = "dub"
            lines = pr.lines
            avail = timing.slots(lines, pr.settings, pr.video.duration)
            for k, i in enumerate(i for i, x in enumerate(lines) if x.id in ids):
                x = lines[i]
                # budget : le temps disponible, moins ce qui dépasse déjà
                budget = timing.char_budget(avail[i], pr.settings.chars_per_second)
                if x.duration > 0 and x.state == "long":
                    budget = min(budget, int(len(x.fr) * avail[i] / (x.duration * pr.settings.max_tempo)))
                before = lines[i - 1].fr if i > 0 else ""
                after = lines[i + 1].fr if i + 1 < len(lines) else ""
                job.progress(k / max(1, len(ids)), "DeepSeek raccourcit la réplique…")
                x.fr = ai.shorten_line(x.fr, x.en, max(8, budget), client, before, after)
                x.fr_edited = True
                job.line_changed(x.id)
            pipeline.step_dub(pr, job, only=ids)

        self._line_job("Raccourcissement", sel, fn)

    def _act_merge(self, sel, ln) -> None:
        pr = self.project
        i = pr.lines.index(ln)
        other = sel[1] if len(sel) > 1 else (pr.lines[i + 1] if i + 1 < len(pr.lines) else None)
        if other is None:
            raise RuntimeError("Pas de réplique suivante à fusionner.")
        merged = segment.merge_lines(ln, other)
        pr.lines = [x for x in pr.lines if x.id not in (ln.id, other.id)] + [merged]
        pr.lines.sort(key=lambda x: x.start)
        self._dirty_audio()
        self.fill_table()
        self._select(merged.id)

    def _act_split(self, sel, ln) -> None:
        pr = self.project
        parts = segment.split_line(ln)
        if parts is None:
            raise RuntimeError("Cette réplique est trop courte pour être coupée.")
        a, b = parts
        i = pr.lines.index(ln)
        pr.lines[i:i + 1] = [a, b]
        self._dirty_audio()
        self.fill_table()
        self._select(a.id)
        self.ctx.toast("Réplique coupée : lancez « Retraduire » pour traduire les deux morceaux.", "info", 5000)

    def _act_delete(self, sel, ln) -> None:
        pr = self.project
        if QMessageBox.question(self, "Supprimer", f"Supprimer {len(sel)} réplique(s) ? Elles ne seront pas "
                                "doublées (la voix d'origine reste dans le fond si la séparation est désactivée)."
                                ) != QMessageBox.Yes:
            return
        ids = {x.id for x in sel}
        pr.lines = [x for x in pr.lines if x.id not in ids]
        self._dirty_audio()
        self.fill_table()

    def _select(self, line_id: str) -> None:
        i = self._rows.get(line_id)
        if i is not None:
            self.table.selectRow(i)
