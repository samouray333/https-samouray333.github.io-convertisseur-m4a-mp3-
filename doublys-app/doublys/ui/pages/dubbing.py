"""Page Doublage : bouton automatique, étapes relançables, tableau des répliques."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPlainTextEdit,
                               QProgressBar, QTableWidget, QTableWidgetItem)

from ... import paths
from ...core import ai, audio, coverage, engines, media, mixer, pipeline, qc, refs, segment, subsources, subtitles, timing
from ...core import project as project_io
from ...core.engines.neural import LOG_LISTENERS
from ...core.models import AUTO_LANGUAGE, LANGUAGES, LINE_STATES, STEP_LABELS, STEPS, VOICE_STEPS, Person
from ...core.speakers import COLORS
from ...core.textproc import format_duration
from .. import icons, tasks, theme
from ..timeline import TimelineView
from ..videopreview import VideoPreview
from ..widgets import Card, IconButton, button, card_title, format_eta, label
from .base import Page

log = logging.getLogger(__name__)

COLS = ["#", "Début", "Durée", "Personne", "Original", "Français", "Calage", "État"]
C_NUM, C_START, C_LEN, C_PERSON, C_EN, C_FR, C_FIT, C_STATE = range(len(COLS))
STEP_SHORT = {"extract": "Extraction", "subtitles": "Sous-titres", "separate": "Séparation", "transcribe": "Transcription",
              "segment": "Répliques", "speakers": "Personnes", "translate": "Traduction", "voices": "Voix",
              "dub": "Doublage", "mix": "Mixage"}
STATE_KIND = {"ok": "success", "tempo": "success", "rate": "info", "long": "warning", "error": "danger", "": "muted",
              "skip": "muted"}


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
        self.name = label(STEP_SHORT.get(step, STEP_LABELS[step]))
        lay.addWidget(self.name, 1)
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
        self.setToolTip(f"{STEP_LABELS[self.step]}" + (f" : {detail}" if detail else ""))


class DubbingPage(Page):
    name = "dubbing"

    def __init__(self, ctx, window):
        super().__init__(ctx, "Doublage", "Une vidéo, un bouton : la version française se crée toute seule.",
                         scroll=True)
        self.window_ = window
        self._rows: dict[str, int] = {}
        self._filling = False
        self._thumb_task = None
        self.undo_btn = IconButton("chevron-left", "Annuler (Ctrl+Z)", 34, 18)
        self.undo_btn.clicked.connect(ctx.undo)
        self.redo_btn = IconButton("chevron-right", "Rétablir (Ctrl+Y)", 34, 18)
        self.redo_btn.clicked.connect(ctx.redo)
        self.header.add_action(self.undo_btn)
        self.header.add_action(self.redo_btn)
        ctx.history_changed.connect(self._history_buttons)

        top = QHBoxLayout()
        top.setSpacing(18)
        # vignette
        vcard = Card(margins=(14, 14, 14, 14), spacing=8)
        self.thumb = VideoPreview(256, 144)
        vcard.add(self.thumb)
        self.video_info = label("", "Hint", wrap=True)
        self.video_info.setMaximumWidth(256)
        vcard.add(self.video_info)
        top.addWidget(vcard)

        # commande
        run = Card(spacing=10)
        r0 = QHBoxLayout()
        r0.addWidget(label("Résultat", "Muted"))
        self.result_mode = QComboBox()
        self.result_mode.addItem("Vidéo doublée en français (VF)", False)
        self.result_mode.addItem("Sous-titres français seulement (voix d'origine gardée)", True)
        self.result_mode.setToolTip("Sous-titres seuls : pas de voix française, beaucoup plus rapide. Une couleur "
                                    "par personne, choisie dans la page Personnes.")
        self.result_mode.currentIndexChanged.connect(self._mode_changed)
        r0.addWidget(self.result_mode)
        r0.addStretch(1)
        run.add(r0)
        rs = QHBoxLayout()
        rs.addWidget(label("Texte", "Muted"))
        self.source_combo = QComboBox()
        self.source_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.source_combo.setMinimumContentsLength(14)
        self.source_combo.setToolTip("D'où vient le texte des répliques : sous-titres de la vidéo (piste, fichier, "
                                     "sous-titres incrustés dans l'image) ou reconnaissance de la voix (Whisper).")
        self.source_combo.activated.connect(self._source_changed)
        rs.addWidget(self.source_combo, 1)
        self.zone_btn = button("Zone…", "image", tooltip="Bande de l'image où se trouvent les sous-titres incrustés")
        self.zone_btn.clicked.connect(self._edit_zone)
        rs.addWidget(self.zone_btn)
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-30.0, 30.0)
        self.offset.setSingleStep(0.1)
        self.offset.setDecimals(2)
        self.offset.setSuffix(" s")
        self.offset.setToolTip("Décalage manuel des sous-titres (en plus du décalage trouvé automatiquement)")
        self.offset.editingFinished.connect(self._offset_changed)
        rs.addWidget(self.offset)
        rs.addSpacing(10)
        rs.addWidget(label("Audio", "Muted"))
        self.audio_lang = QComboBox()
        self.audio_lang.addItem("Détection automatique", AUTO_LANGUAGE)
        for k, (name, _iso, _d, _e) in LANGUAGES.items():
            self.audio_lang.addItem(name, k)
        self.audio_lang.setToolTip("Langue parlée dans la vidéo : détectée automatiquement sur plusieurs extraits")
        self.audio_lang.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.audio_lang.setMinimumContentsLength(9)
        self.offset.setMaximumWidth(96)
        self.audio_lang.activated.connect(self._audio_lang_changed)
        rs.addWidget(self.audio_lang)
        run.add(rs)
        self.lang_info = label("", "Hint", wrap=True)
        run.add(self.lang_info)
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
        self.coverage_lbl = QLabel()
        self.coverage_lbl.setTextFormat(Qt.RichText)
        self.coverage_lbl.setCursor(Qt.PointingHandCursor)
        self.coverage_lbl.setToolTip("Ouvrir la page Contrôle")
        self.coverage_lbl.linkActivated.connect(lambda _l: self.ctx.navigate("review"))
        run.add(self.coverage_lbl)
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
            grid.addWidget(row, i // 3, i % 3)
        run.add(grid)
        top.addWidget(run, 1)
        self.body.addLayout(top)

        # tableau des répliques
        tc = Card(spacing=8, margins=(16, 14, 16, 14))
        th = QHBoxLayout()
        th.addWidget(card_title("Répliques", "Double-cliquez sur le français pour le modifier ; la voix sera refaite.",
                                "captions"), 1)
        self.only_issues = QCheckBox("Seulement les répliques à vérifier")
        self.only_issues.toggled.connect(self._apply_filter)
        th.addWidget(self.only_issues, 0, Qt.AlignBottom)
        tc.add(th)
        self.qc_label = label("", "Hint", wrap=True)
        tc.add(self.qc_label)
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
        self.table.setMinimumHeight(330)
        tc.add(self.table)
        acts = QHBoxLayout()
        acts.setSpacing(6)
        acts2 = QHBoxLayout()
        acts2.setSpacing(6)
        self.actions = {}
        for key, text, ic, tip in [
            ("vo", "VO", "headphones", "Écouter la version originale"),
            ("vf", "VF", "volume", "Écouter la voix française seule"),
            ("mix", "Mixé", "wave", "Écouter le mélange final"),
            ("preview", "Aperçu", "film", "Voir la réplique avec l'image et le sous-titre, ici (double-clic sur le "
                                             "numéro)"),
            ("retranslate", "Retraduire", "languages", "Nouvelle traduction automatique"),
            ("shorten", "Raccourcir", "scissors", "DeepSeek propose une version plus courte qui tient dans le temps"),
            ("redo", "Refaire", "refresh", "Nouvelle prise de la voix française"),
            ("merge", "Fusionner", "merge", "Fusionner avec la réplique suivante"),
            ("split", "Couper", "scissors", "Couper la réplique en deux"),
            ("delete", "Supprimer", "trash", "Supprimer les répliques choisies (non doublées)"),
        ]:
            compact = key in ("merge", "split", "delete")
            b = button("" if compact else text, ic, "danger" if key == "delete" else "default",
                       tooltip=f"{text} : {tip}" if compact else tip)
            if compact:
                b.setText("")
                b.setAccessibleName(text)
            b.clicked.connect(lambda _=False, k=key: self.action(k))
            (acts if key in ("vo", "vf", "mix", "preview") else acts2).addWidget(b)
            self.actions[key] = b
        acts.addStretch(1)
        self.ok_btn = button("", "check", tooltip="Vérifiée : ne plus signaler cette réplique au contrôle qualité")
        self.ok_btn.clicked.connect(lambda: self.action("checked"))
        acts2.addWidget(self.ok_btn)
        acts2.addStretch(1)
        tc.add(acts)
        tc.add(acts2)
        self.timeline = TimelineView()
        self.timeline.edited.connect(self._timing_edited)
        self.timeline.selected.connect(self._select)
        tc.add(self.timeline)
        self.body.addWidget(tc, 1)

        self.console = QPlainTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(3000)
        self.console.setFixedHeight(64)
        self.console.setToolTip("Journal du traitement")
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
            if pr.lines and pr.step_done("translate"):
                qc.check(pr)  # projets créés avant le contrôle qualité
            v = pr.video
            self.video_info.setText(f"{Path(pr.source_video).name}\n{format_duration(v.duration)} · {v.width}×"
                                    f"{v.height} · {v.video_codec} / {v.audio_codec}")
            self._project_thumbnail()
        self.result_mode.blockSignals(True)
        self.result_mode.setCurrentIndex(1 if pr is not None and pr.settings.subtitles_only else 0)
        self.result_mode.blockSignals(False)
        self._fill_sources()
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
            elif s in VOICE_STEPS and pr.settings.subtitles_only:
                row.set_state("skip", "inutile pour les sous-titres seuls")
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
            if self.project.settings.subtitles_only:
                self.auto_btn.setText("Créer les sous-titres automatiquement" if not self.project.steps else
                                      ("Terminer les sous-titres automatiquement" if nxt else
                                       "Refaire l'export des sous-titres"))
            else:
                self.auto_btn.setText("Créer la VF automatiquement" if not self.project.steps else
                                      ("Terminer la VF automatiquement" if nxt else "Refaire l'export de la VF"))
            todo = pipeline.steps_to_run(self.project) + ["export"]
            est = pipeline.estimate_seconds(self.project, todo)
            idle = self.status.text() in ("Prêt.", "") or self.status.text().startswith("Temps de calcul")
            if nxt and idle:
                self.status.setText(f"Temps de calcul estimé sur cet ordinateur : environ {format_eta(est)} "
                                    "(l'ordinateur ne se mettra pas en veille ; vous pouvez arrêter et reprendre).")
        self.result_mode.setEnabled(has and not running)
        for w in (self.source_combo, self.audio_lang, self.offset):
            w.setEnabled(has and not running)
        self.zone_btn.setEnabled(has and not running and self.project.subs.kind in ("ocr", "auto"))
        self._update_coverage()
        only = has and self.project.settings.subtitles_only
        self.open_btn.setText("Ouvrir la vidéo sous-titrée" if only else "Ouvrir la vidéo doublée")

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

        self._start("Création des sous-titres" if pr.settings.subtitles_only else "Création de la VF", plan, work)

    # -- texte de départ et langue ---------------------------------------------------------
    def _fill_sources(self) -> None:
        """Choix du texte : automatique, pistes et fichiers trouvés, sous-titres de l'image, voix seule."""
        pr = self.project
        combo = self.source_combo
        combo.blockSignals(True)
        combo.clear()
        if pr is None:
            combo.blockSignals(False)
            return
        subs = pr.subs
        combo.addItem("Automatique (sous-titres s'il y en a)", {"kind": "auto"})
        seen = set()
        cands = [dict(c) for c in subs.candidates]
        if not cands and Path(pr.source_video).exists():
            try:
                found = subsources.find_tracks(Path(pr.source_video)) + subsources.find_files(Path(pr.source_video))
                cands = [c.to_dict() for c in found]
            except Exception:  # noqa: BLE001 - vidéo illisible : la liste reste courte
                cands = []
        if subs.kind == "file" and subs.path and not any(c.get("path") == subs.path for c in cands):
            cands.append({"kind": "file", "path": subs.path, "track": -1, "language": subs.language,
                          "label": f"Fichier « {Path(subs.path).name} »"})
        if not any(c.get("kind") == "ocr" for c in cands):
            cands.append({"kind": "ocr", "track": -1, "path": "", "language": "en",
                          "label": "Sous-titres incrustés dans l'image (lecture OCR)"})
        for c in cands:
            key = (c.get("kind"), c.get("track"), c.get("path"))
            if key in seen:
                continue
            seen.add(key)
            combo.addItem(c.get("label") or c.get("kind"), c)
        combo.addItem("Choisir un fichier de sous-titres…", {"kind": "pick"})
        combo.addItem("Voix seule (Whisper, sans sous-titres)", {"kind": "none"})
        idx = 0
        for i in range(combo.count()):
            d = combo.itemData(i) or {}
            if d.get("kind") == subs.kind and (subs.kind not in ("track", "file") or
                                               (d.get("track") == subs.track if subs.kind == "track"
                                                else d.get("path") == subs.path)):
                idx = i
                break
        if not pr.settings.use_subtitles:
            idx = combo.count() - 1
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        self.offset.blockSignals(True)
        self.offset.setValue(subs.offset)
        self.offset.blockSignals(False)
        self.offset.setVisible(subs.kind in ("track", "file", "ocr"))
        self.zone_btn.setVisible(subs.kind in ("ocr", "auto"))
        self.audio_lang.blockSignals(True)
        self.audio_lang.setCurrentIndex(max(0, self.audio_lang.findData(pr.settings.source_language)))
        self.audio_lang.blockSignals(False)
        st = pr.settings
        info = []
        if st.detected_language:
            from ...core.models import language_name

            info.append(f"Audio détecté : {language_name(st.detected_language).lower()}"
                        + (f" ({st.language_confidence:.0%})" if st.language_confidence else ""))
        if subs.kind in ("track", "file", "ocr") and subs.count:
            info.append(f"{subs.count} sous-titres ({subs.language or '?'})")
            if subs.auto_offset:
                info.append(f"décalage automatique {subs.auto_offset:+.2f} s")
        self.lang_info.setText(" · ".join(info))
        self.lang_info.setVisible(bool(info))

    def _source_changed(self) -> None:
        pr = self.project
        if pr is None:
            return
        d = dict(self.source_combo.currentData() or {})
        if d.get("kind") == "pick":
            start = str(Path(pr.source_video).parent)
            path, _ = QFileDialog.getOpenFileName(self, "Fichier de sous-titres", start,
                                                  "Sous-titres (*.srt *.ass *.ssa *.vtt);;Tous (*)")
            if not path:
                self._fill_sources()
                return
            d = {"kind": "file", "path": path, "track": -1, "language": subsources.lang_from_name(path)}
        self.ctx.checkpoint("texte de départ")
        subs = pr.subs
        pr.settings.use_subtitles = d.get("kind") != "none"
        subs.kind = d.get("kind", "auto")
        subs.track = int(d.get("track", -1) if d.get("track") is not None else -1)
        subs.path = d.get("path", "") or ""
        if d.get("language"):
            subs.language = d["language"]
        pr.invalidate_from("subtitles")
        self.ctx.mark_dirty()
        self._fill_sources()
        self.fill_steps()
        self._update_buttons()

    def _offset_changed(self) -> None:
        pr = self.project
        if pr is None:
            return
        delta = round(self.offset.value() - pr.subs.offset, 3)
        if abs(delta) < 0.001:
            return
        self.ctx.checkpoint("décalage des sous-titres")
        pr.subs.offset = self.offset.value()
        for ln in pr.lines:  # répliques venues des sous-titres : décalées, voix à recaler
            if ln.source in ("track", "file", "ocr"):
                ln.start = round(max(0.0, ln.start + delta), 3)
                ln.end = round(max(ln.start + 0.2, ln.end + delta), 3)
                ln.audio_key = ""
        pr.mark_step("dub", False)
        pr.mark_step("mix", False)
        coverage.update(pr)
        self.ctx.mark_dirty()
        self.fill_table()
        self.fill_steps()

    def _audio_lang_changed(self) -> None:
        pr = self.project
        if pr is None:
            return
        lang = self.audio_lang.currentData()
        if lang == pr.settings.source_language:
            return
        self.ctx.checkpoint("langue de la vidéo")
        pr.settings.source_language = lang
        pr.invalidate_from("transcribe")
        self.ctx.mark_dirty()
        self.fill_steps()
        self._update_buttons()

    def _edit_zone(self) -> None:
        pr = self.project
        if pr is None:
            return
        from ..dialogs.zone import ZoneDialog

        dlg = ZoneDialog(self, pr)
        if dlg.exec() and dlg.zone is not None:
            self.ctx.checkpoint("zone des sous-titres")
            pr.subs.zone = list(dlg.zone)
            pr.subs.kind = "ocr"
            pr.settings.use_subtitles = True
            pr.invalidate_from("subtitles")
            self.ctx.mark_dirty()
            self._fill_sources()
            self.fill_steps()
            self._update_buttons()

    def _update_coverage(self) -> None:
        pr = self.project
        if pr is None or not pr.lines:
            self.coverage_lbl.setText("")
            self.coverage_lbl.hide()
            return
        try:
            text, problems = coverage.summary(pr)
        except Exception:  # noqa: BLE001
            text, problems = f"{len(pr.lines)} répliques", 0
        color = theme.CURRENT.success if not problems else theme.CURRENT.warning
        mark = "✔" if not problems else "⚠"
        self.coverage_lbl.setText(f'<a href="review" style="color:{color}; text-decoration:none; font-weight:600;">'
                                  f"{mark} {text}</a>")
        self.coverage_lbl.show()

    def _mode_changed(self) -> None:
        pr = self.project
        if pr is None:
            return
        only = bool(self.result_mode.currentData())
        if only == pr.settings.subtitles_only:
            return
        self.ctx.checkpoint("résultat")
        pr.settings.subtitles_only = only
        self.ctx.mark_dirty()
        self.open_btn.hide()
        self.fill_steps()
        self._update_buttons()

    def _missing_engines(self, steps: list[str]) -> list[str]:
        out = []
        need = {"separate": "analysis", "speakers": "analysis", "transcribe": "whisper"}
        st, subs = self.project.settings, self.project.subs
        if st.use_subtitles and subs.kind in ("auto", "ocr"):
            need["subtitles"] = "ocr"  # lecture des sous-titres incrustés (si la vidéo en a)
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
        if self.ctx.runner.title.startswith("File d'attente"):  # géré par la page File d'attente
            self._update_buttons()
            self.fill_steps()
            self.status.setText("Prêt.")
            return
        self._fill_sources()
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
                _text, problems = coverage.summary(self.project)
                if problems:
                    extra += f" {problems} point(s) à vérifier dans Contrôle."
                self.ctx.toast("La version française est prête !" + extra, "success" if not problems else "warning",
                               9000)
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
        self.qc_label.setText(qc.summary(pr) if pr is not None and pr.lines else "")
        self._update_timeline()

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
        state = LINE_STATES.get(ln.state, ln.state)
        if not ln.state and self.project.settings.subtitles_only:
            state = "sous-titrée"
        if ln.issues and ln.state not in ("long", "error"):
            state = "⚠ à vérifier"
        values += [fit, state]
        self._filling = True
        for c, v in enumerate(values):
            it = QTableWidgetItem(v)
            if c != C_FR:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if c == C_PERSON and person is not None:
                it.setForeground(QColor(person.color))
            if c == C_EN and ln.source:
                origin = {"track": "piste de sous-titres", "file": "fichier de sous-titres",
                          "ocr": f"sous-titre lu dans l'image (confiance {ln.ocr_conf:.0%})",
                          "manual": "réplique ajoutée à la main"}.get(ln.source, ln.source)
                it.setToolTip(f"Texte : {origin}")
            if ln.no_dub and c in (C_EN, C_FR):
                it.setForeground(QColor(theme.CURRENT.faint))
            if c == C_STATE:
                kind = "warning" if ln.issues else STATE_KIND.get(ln.state, "muted")
                color = {"success": theme.CURRENT.success, "warning": theme.CURRENT.warning,
                         "danger": theme.CURRENT.danger, "info": theme.CURRENT.info}.get(kind, theme.CURRENT.faint)
                it.setForeground(QColor(color))
                tips = [m for _c, m in ln.issues] or ([ln.message] if ln.message else [])
                if tips:
                    it.setToolTip("\n".join(tips))
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
                self.table.setRowHidden(i, only and not ln.issues and ln.state not in ("long", "error"))

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
        self.ctx.checkpoint("modification du français")
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
        self._update_timeline()
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
        for key in ("vo", "vf", "mix", "preview", "external", None, "checked", "deepseek", "retranslate", "shorten", "redo", None, "merge", "split",
                    "delete"):
            if key is None:
                m.addSeparator()
                continue
            if key == "checked":
                a = m.addAction(icons.icon("check", theme.CURRENT.text, 16), "Marquer comme vérifiée",
                                lambda: self.action("checked"))
                a.setEnabled(not self.ctx.runner.running)
                continue
            if key == "deepseek":
                a = m.addAction(icons.icon("sparkles", theme.CURRENT.text, 16), "Retraduire avec DeepSeek",
                                lambda: self.action("deepseek"))
                a.setEnabled(not self.ctx.runner.running)
                continue
            if key == "external":
                a = m.addAction(icons.icon("external", theme.CURRENT.text, 16),
                                "Ouvrir 20 s dans le lecteur de Windows", lambda: self.action("external"))
                a.setEnabled(self.actions["preview"].isEnabled())
                continue
            b = self.actions[key]
            a = m.addAction(b.icon(), b.accessibleName() or b.text(), lambda k=key: self.action(k))
            a.setEnabled(b.isEnabled())
        if not self.ctx.runner.running:
            keep = all(x.no_dub for x in sel)
            m.addAction(icons.icon("volume", theme.CURRENT.text, 16),
                        "Doubler à nouveau" if keep else "Ne pas doubler (garder la voix d'origine)",
                        lambda: self._set_no_dub(sel, not keep))
            sub = m.addMenu(icons.icon("users", theme.CURRENT.text, 16), "Attribuer à")
            for p in self.project.people:
                sub.addAction(p.name, lambda p=p: self._assign(sel, p.id))
            sub.addSeparator()
            sub.addAction("Nouvelle personne", lambda: self._assign(sel, None))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _set_no_dub(self, lines, value: bool) -> None:
        self.ctx.checkpoint("ne pas doubler" if value else "doubler à nouveau")
        for ln in lines:
            ln.no_dub = value
            ln.audio_key = ""
            if value:
                ln.audio, ln.state, ln.message = "", "skip", "Non doublée : la voix d'origine reste."
            elif ln.state == "skip":
                ln.state, ln.message = "", ""
        self.project.mark_step("dub", False)
        self.project.mark_step("mix", False)
        qc.check(self.project)
        self.ctx.mark_dirty()
        self.fill_table()
        self.fill_steps()

    def _assign(self, lines, person_id) -> None:
        pr = self.project
        self.ctx.checkpoint("changement de personne")
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
        if pr.settings.subtitles_only:  # sous-titres seuls : on écoute la voix d'origine
            return pipeline.wf(pr, pipeline.ORIGINAL), a, end
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
        colors = subtitles.person_colors(pr)
        subs = [(x.start, x.start + max(x.length, x.duration), x.fr, colors.get(x.person_id, "")) for x in pr.lines
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

    def _act_checked(self, sel, ln) -> None:
        self.ctx.checkpoint("réplique vérifiée")
        for x in sel:
            x.checked = True
            x.issues = []
        self.ctx.mark_dirty()
        self.fill_table()

    def _act_deepseek(self, sel, ln) -> None:
        pr = self.project
        try:
            ai.client_from_settings()
        except ai.AIError as exc:
            raise RuntimeError(f"{exc}") from None
        old = pr.settings.translator

        def fn(job, ids):
            pr.settings.translator = "deepseek"
            try:
                job.step = "translate"
                pipeline.step_translate(pr, job, only=ids, force=True)
            finally:
                pr.settings.translator = old
            job.step = "dub"
            pipeline.step_dub(pr, job, only=ids)

        self._line_job("Traduction DeepSeek", sel, fn, ["translate", "dub"])

    def _history_buttons(self) -> None:
        u, r = self.ctx.can_undo(), self.ctx.can_redo()
        self.undo_btn.setEnabled(bool(u))
        self.redo_btn.setEnabled(bool(r))
        self.undo_btn.setToolTip(f"Annuler : {u} (Ctrl+Z)" if u else "Rien à annuler")
        self.redo_btn.setToolTip(f"Rétablir : {r} (Ctrl+Y)" if r else "Rien à rétablir")

    # -- éditeur de calage ---------------------------------------------------------------
    def _update_timeline(self) -> None:
        pr = self.project
        sel = self.selected_lines() if pr is not None else []
        if not sel:
            self.timeline.clear()
            return
        ln = sel[0]
        t0 = max(0.0, ln.start - 4.0)
        t1 = max(ln.end, ln.start + ln.duration) + 5.0
        peaks = None
        try:
            src, _src16 = pipeline.speech_source(pr)
            if src.exists():
                data, sr = refs.read_span(src, t0, t1)
                peaks = audio.waveform_peaks(data, 600) if data.size else None
        except Exception:
            peaks = None
        items = []
        for x in pr.lines:
            if x.end < t0 or x.start > t1:
                continue
            person = pr.person(x.person_id)
            items.append((x.id, x.start, x.end, x.duration if x.audio else 0.0,
                          person.color if person else theme.CURRENT.faint,
                          f"{pr.lines.index(x) + 1} · {person.name if person else ''}"))
        self.timeline.set_view(t0, t1, peaks, items, ln.id)

    def _timing_edited(self, line_id: str, start: float, end: float) -> None:
        pr = self.project
        ln = pr.line(line_id) if pr is not None else None
        if ln is None or self.ctx.runner.running:
            self._update_timeline()
            return
        self.ctx.checkpoint("calage modifié")
        ln.start, ln.end = start, end
        ln.state, ln.message = "", "Calage modifié : voix à refaire"
        self._dirty_audio()
        self.fill_table()
        self._select(line_id)
        if ln.fr and ln.audio:  # la voix est recalée tout de suite

            def fn(job, ids):
                job.step = "dub"
                pipeline.step_dub(pr, job, only=ids)

            self._line_job("Nouveau calage", [ln], fn, checkpoint=False)

    def _line_job(self, title: str, lines, fn, plan: list[str] | None = None, checkpoint: bool = True) -> None:
        """Traitement de quelques répliques ; le mixage sera refait par « Terminer la VF »."""
        ids = [x.id for x in lines]
        if checkpoint:
            self.ctx.checkpoint(title.lower())

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
        self.ctx.checkpoint("nouvelle prise de voix")
        for x in sel:
            x.seed = (x.seed or 0) + 1

        def fn(job, ids):
            job.step = "dub"
            pipeline.step_dub(pr, job, only=ids, force=True)

        self._line_job("Nouvelle prise de voix", sel, fn, checkpoint=False)

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
        self.ctx.checkpoint("fusion de répliques")
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
        self.ctx.checkpoint("coupure de réplique")
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
        self.ctx.checkpoint("suppression de répliques")
        pr.lines = [x for x in pr.lines if x.id not in ids]
        self._dirty_audio()
        self.fill_table()

    def _select(self, line_id: str) -> None:
        i = self._rows.get(line_id)
        if i is not None:
            self.table.selectRow(i)
