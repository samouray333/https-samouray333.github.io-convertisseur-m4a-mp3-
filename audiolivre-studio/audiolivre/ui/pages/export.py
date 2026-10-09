"""Page Export : métadonnées, couverture, formats, mastering et rapport qualité."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar, QSlider)

from ...core import renderer
from ...core.exporter import ExportItem, export_audiobook
from ...core.mastering import MasteringOptions
from ...core.models import EXPORT_FORMATS, MASTERING_PRESETS
from ...core.project_io import default_export_dir
from .. import icons, tasks, theme
from ..widgets import Badge, Card, ToggleSwitch, button, card_title, label
from .base import Page

GENRES = ["Livre audio", "Roman", "Policier / Thriller", "Science-fiction", "Fantasy", "Jeunesse", "Biographie",
          "Histoire", "Développement personnel", "Essai", "Poésie", "Théâtre", "Conte", "Documentaire", "Religion"]
PRESET_HELP = {
    "acx": "Égalisation, de-essing, compression douce, RMS -19,5 dB, crêtes ≤ -3,6 dB, bruit de fond -72 dB. "
           "Conforme aux exigences d'Audible / ACX.",
    "streaming": "Normalisation EBU R128 à -16 LUFS, crêtes -1,5 dBTP : idéal pour Spotify, YouTube, podcasts.",
    "natural": "Traitement léger qui préserve la dynamique naturelle de la voix.",
    "none": "Aucun traitement : l'audio brut des voix est exporté tel quel.",
}


class CoverView(QLabel):
    def __init__(self, on_drop):
        super().__init__()
        self.setFixedSize(230, 230)
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self._on_drop = on_drop
        self.set_path("")

    def set_path(self, path: str) -> None:
        p = theme.CURRENT
        if path and Path(path).exists():
            pm = QPixmap(path)
            if not pm.isNull():
                self.setPixmap(pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.setStyleSheet(f"background: {p.surface2}; border-radius: 14px;")
                return
        self.setPixmap(icons.pixmap("image", p.faint, 54))
        self.setStyleSheet(f"background: {p.surface2}; border: 2px dashed {p.border}; border-radius: 14px;")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self._on_drop(urls[0])


class ExportPage(Page):
    name = "export"

    def __init__(self, ctx):
        super().__init__(ctx, "Export", "Créez les fichiers de votre livre audio, prêts à publier.", scroll=True)
        self._loading = False
        self.export_btn = button("Exporter le livre audio", "download", "primary")
        self.export_btn.clicked.connect(self.export)
        self.header.add_action(self.export_btn)

        # ---- prêt ?
        self.ready_card = Card(obj="CardFlat", margins=(16, 12, 16, 12))
        rr = QHBoxLayout()
        self.ready_icon = QLabel()
        self.ready_lbl = label("", wrap=True)
        rr.addWidget(self.ready_icon)
        rr.addWidget(self.ready_lbl, 1)
        self.produce_btn = button("Aller à la production", "wave")
        self.produce_btn.clicked.connect(lambda: self.ctx.navigate("production"))
        rr.addWidget(self.produce_btn)
        self.ready_card.add(rr)
        self.body.addWidget(self.ready_card)

        # ---- métadonnées + couverture
        row1 = QHBoxLayout()
        row1.setSpacing(18)
        meta = Card()
        meta.add(card_title("Informations du livre", "Elles sont inscrites dans les fichiers (titre, auteur, "
                            "narrateur…) et affichées par les lecteurs audio.", "book"))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        self.f = {}
        fields = [("title", "Titre"), ("subtitle", "Sous-titre"), ("author", "Auteur"), ("narrator", "Narrateur"),
                  ("publisher", "Éditeur"), ("year", "Année"), ("series", "Série"), ("series_index", "Tome"),
                  ("isbn", "ISBN"), ("copyright", "Copyright")]
        for i, (key, name) in enumerate(fields):
            w = QLineEdit()
            w.textEdited.connect(self._meta_changed)
            self.f[key] = w
            g.addWidget(label(name, "Muted"), i // 2, (i % 2) * 2)
            g.addWidget(w, i // 2, (i % 2) * 2 + 1)
        r = len(fields) // 2
        self.genre = QComboBox()
        self.genre.setEditable(True)
        self.genre.addItems(GENRES)
        self.genre.currentTextChanged.connect(self._meta_changed)
        self.lang = QComboBox()
        from .voices import LANGS

        for code, name in LANGS[:-1]:
            self.lang.addItem(name, code)
        self.lang.currentIndexChanged.connect(self._meta_changed)
        g.addWidget(label("Genre", "Muted"), r, 0)
        g.addWidget(self.genre, r, 1)
        g.addWidget(label("Langue", "Muted"), r, 2)
        g.addWidget(self.lang, r, 3)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        meta.add(g)
        meta.add(label("Résumé", "Muted"))
        self.desc = QPlainTextEdit()
        self.desc.setMaximumHeight(90)
        self.desc.textChanged.connect(self._meta_changed)
        meta.add(self.desc)
        row1.addWidget(meta, 3)

        cov = Card()
        cov.add(card_title("Couverture", "Image carrée conseillée (au moins 2400 × 2400 pour Audible).", "image"))
        self.cover = CoverView(self._set_cover)
        cov.add(self.cover)
        cr = QHBoxLayout()
        pick = button("Choisir…", "folder")
        pick.clicked.connect(self._pick_cover)
        rm = button("Retirer", kind="ghost")
        rm.clicked.connect(lambda: self._set_cover(""))
        cr.addWidget(pick)
        cr.addWidget(rm)
        cov.add(cr)
        self.acx_cover = ToggleSwitch("Format ACX 2400 × 2400")
        self.acx_cover.toggled.connect(self._export_changed)
        cov.add(self.acx_cover)
        cov.add(None)
        row1.addWidget(cov, 1)
        self.body.addLayout(row1)

        # ---- formats + mastering
        row2 = QHBoxLayout()
        row2.setSpacing(18)
        fm = Card()
        fm.add(card_title("Formats de sortie", "", "package"))
        self.fmt_toggles: dict[str, ToggleSwitch] = {}
        for key, desc in EXPORT_FORMATS.items():
            t = ToggleSwitch(desc)
            t.toggled.connect(self._export_changed)
            self.fmt_toggles[key] = t
            fm.add(t)
        br = QGridLayout()
        self.m4b_rate = QComboBox()
        self.m4b_rate.addItems(["64k", "96k", "128k", "192k"])
        self.mp3_rate = QComboBox()
        self.mp3_rate.addItems(["128k", "192k", "256k", "320k"])
        for c in (self.m4b_rate, self.mp3_rate):
            c.currentTextChanged.connect(self._export_changed)
        br.addWidget(label("Débit M4B", "Muted"), 0, 0)
        br.addWidget(self.m4b_rate, 0, 1)
        br.addWidget(label("Débit MP3", "Muted"), 0, 2)
        br.addWidget(self.mp3_rate, 0, 3)
        fm.add(br)
        row2.addWidget(fm, 1)

        ms = Card()
        ms.add(card_title("Mastering", "Le son final, homogène d'un chapitre à l'autre.", "sliders"))
        self.preset = QComboBox()
        for k, v in MASTERING_PRESETS.items():
            self.preset.addItem(v, k)
        self.preset.currentIndexChanged.connect(self._export_changed)
        ms.add(self.preset)
        self.preset_help = label("", "Hint", wrap=True)
        ms.add(self.preset_help)
        self.t_denoise = ToggleSwitch("Réduction de bruit (voix clonées bruitées)")
        self.t_deess = ToggleSwitch("De-esser (adoucit les « s » sifflants)")
        self.t_room = ToggleSwitch("Ambiance de pièce entre les phrases (évite le « vide » numérique)")
        for t in (self.t_denoise, self.t_deess, self.t_room):
            t.toggled.connect(self._export_changed)
            ms.add(t)
        ms.add(None)
        row2.addWidget(ms, 1)
        self.body.addLayout(row2)

        # ---- musique
        mus = Card()
        mus.add(card_title("Musique", "Jingle d'ouverture et de fin, fond sonore discret sous la narration (baissé "
                           "automatiquement quand la voix parle). Utilisez des musiques libres de droits.", "headphones"))
        mg = QGridLayout()
        mg.setHorizontalSpacing(10)
        mg.setVerticalSpacing(8)
        self.music_fields: dict[str, QLineEdit] = {}
        for row, (key, name) in enumerate((("intro_music", "Jingle d'ouverture"), ("outro_music", "Jingle de fin"),
                                           ("background_music", "Fond sonore"))):
            le = QLineEdit()
            le.setPlaceholderText("Aucune musique")
            le.setReadOnly(True)
            pick = button("Choisir…", "folder")
            pick.clicked.connect(lambda _=False, k=key: self._pick_music(k))
            clear = button("", "x", "ghost", tooltip="Retirer")
            clear.clicked.connect(lambda _=False, k=key: self._set_music(k, ""))
            self.music_fields[key] = le
            mg.addWidget(label(name, "Muted"), row, 0)
            mg.addWidget(le, row, 1)
            mg.addWidget(pick, row, 2)
            mg.addWidget(clear, row, 3)
        mg.setColumnStretch(1, 1)
        mus.add(mg)
        lr = QHBoxLayout()
        lr.addWidget(label("Volume du fond sonore", "Muted"))
        self.bg_level = QSlider(Qt.Horizontal)
        self.bg_level.setRange(-35, -10)
        self.bg_level.valueChanged.connect(self._bg_level_changed)
        self.bg_level_lbl = label("", "Muted")
        lr.addWidget(self.bg_level, 1)
        lr.addWidget(self.bg_level_lbl)
        mus.add(lr)
        mus.add(label("Audible/ACX refuse la musique sous la narration : gardez le fond sonore pour YouTube, les "
                      "podcasts ou une diffusion personnelle.", "Hint", wrap=True))
        self.body.addWidget(mus)

        # ---- crédits + destination
        row3 = QHBoxLayout()
        row3.setSpacing(18)
        cr_card = Card()
        cr_card.add(card_title("Crédits et extrait", "Audible exige des crédits d'ouverture et de fin, ainsi qu'un "
                               "extrait de 1 à 5 minutes.", "award"))
        self.t_credits = ToggleSwitch("Ajouter les crédits d'ouverture et de fin")
        self.t_credits.toggled.connect(self._export_changed)
        cr_card.add(self.t_credits)
        self.open_tpl = QLineEdit()
        self.close_tpl = QLineEdit()
        for w in (self.open_tpl, self.close_tpl):
            w.textEdited.connect(self._export_changed)
        cr_card.add(label("Crédits d'ouverture", "Muted"))
        cr_card.add(self.open_tpl)
        cr_card.add(label("Crédits de fin", "Muted"))
        cr_card.add(self.close_tpl)
        cr_card.add(label("Variables : {title} {subtitle} {author} {narrator} {publisher} {year}", "Faint"))
        sr = QHBoxLayout()
        self.t_sample = ToggleSwitch("Créer un extrait de")
        self.t_sample.toggled.connect(self._export_changed)
        self.sample_min = QDoubleSpinBox()
        self.sample_min.setRange(1, 5)
        self.sample_min.setSingleStep(0.5)
        self.sample_min.setSuffix(" min")
        self.sample_min.valueChanged.connect(self._export_changed)
        sr.addWidget(self.t_sample)
        sr.addWidget(self.sample_min)
        sr.addStretch(1)
        cr_card.add(sr)
        row3.addWidget(cr_card, 1)

        dest = Card()
        dest.add(card_title("Destination", "", "folder"))
        dr = QHBoxLayout()
        self.out_dir = QLineEdit()
        self.out_dir.textEdited.connect(self._export_changed)
        browse = button("Parcourir…", "folder")
        browse.clicked.connect(self._pick_dir)
        dr.addWidget(self.out_dir, 1)
        dr.addWidget(browse)
        dest.add(dr)
        dest.add(label("Nom des pistes", "Muted"))
        self.pattern = QLineEdit()
        self.pattern.textEdited.connect(self._export_changed)
        dest.add(self.pattern)
        dest.add(label("Variables : {index:02d} (numéro), {title} (chapitre), {book} (livre)", "Faint"))
        self.t_report = ToggleSwitch("Générer un rapport qualité (HTML)")
        self.t_report.toggled.connect(self._export_changed)
        dest.add(self.t_report)
        dest.add(None)
        row3.addWidget(dest, 1)
        self.body.addLayout(row3)

        # ---- progression & résultats
        self.prog_card = Card()
        self.prog_card.add(card_title("Export", "", "rocket"))
        self.prog_lbl = label("", "Muted")
        self.prog = QProgressBar()
        self.prog.setRange(0, 1000)
        self.prog_card.add(self.prog_lbl)
        self.prog_card.add(self.prog)
        self.results = QListWidget()
        self.results.setMinimumHeight(160)
        self.results.itemDoubleClicked.connect(self._open_result)
        self.prog_card.add(self.results)
        rb = QHBoxLayout()
        self.open_dir = button("Ouvrir le dossier", "external")
        self.open_dir.clicked.connect(self._open_output)
        self.open_report = button("Voir le rapport qualité", "shield")
        self.open_report.clicked.connect(self._open_report_file)
        self.verdict = Badge("", "success")
        rb.addWidget(self.verdict)
        rb.addStretch(1)
        rb.addWidget(self.open_report)
        rb.addWidget(self.open_dir)
        self.prog_card.add(rb)
        self.prog_card.hide()
        self.body.addWidget(self.prog_card)
        self.body.addStretch(1)
        self._last_result = None
        ctx.render_finished.connect(self._update_ready)

    # -- chargement --------------------------------------------------------------------
    def on_project_changed(self) -> None:
        pr = self.ctx.project
        m, e, prod = pr.metadata, pr.export, pr.production
        self._loading = True
        for key, w in self.f.items():
            w.setText(str(getattr(m, key, "") or ""))
        self.genre.setCurrentText(m.genre or "Livre audio")
        self.lang.setCurrentIndex(max(0, self.lang.findData(m.language or "fr")))
        self.desc.setPlainText(m.description)
        self.cover.set_path(m.cover_path)
        self.acx_cover.setChecked(e.acx_cover)
        for k, t in self.fmt_toggles.items():
            t.setChecked(k in e.formats)
        self.m4b_rate.setCurrentText(e.m4b_bitrate)
        self.mp3_rate.setCurrentText(e.mp3_bitrate)
        self.preset.setCurrentIndex(max(0, self.preset.findData(prod.mastering_preset)))
        self.preset_help.setText(PRESET_HELP.get(prod.mastering_preset, ""))
        self.t_denoise.setChecked(prod.denoise)
        self.t_deess.setChecked(prod.deesser)
        self.t_room.setChecked(prod.room_tone)
        self.t_credits.setChecked(e.include_credits)
        self.open_tpl.setText(e.opening_credits)
        self.close_tpl.setText(e.closing_credits)
        self.t_sample.setChecked(e.make_sample)
        self.sample_min.setValue(e.sample_minutes)
        self.out_dir.setText(str(default_export_dir(pr)))
        self.pattern.setText(e.file_pattern)
        self.t_report.setChecked(e.write_report)
        for key, le in self.music_fields.items():
            le.setText(getattr(e, key, "") or "")
        self.bg_level.setValue(int(round(e.background_level_db)))
        self.bg_level_lbl.setText(f"{int(round(e.background_level_db))} dB sous la voix")
        self._loading = False
        self.prog_card.hide()

    def on_show(self) -> None:
        self.on_project_changed()
        self._update_ready()

    def _update_ready(self) -> None:
        pr = self.ctx.project
        p = theme.CURRENT
        if not pr.chapters:
            self.ready_icon.setPixmap(icons.pixmap("info", p.muted, 22))
            self.ready_lbl.setText("Aucun projet ouvert.")
            self.export_btn.setEnabled(False)
            return
        try:
            plan = renderer.build_plan(pr, self.ctx.library)
        except Exception as exc:
            self.ready_lbl.setText(str(exc))
            return
        ready = [rc for rc in plan if renderer.chapter_is_current(pr, rc)]
        self.export_btn.setEnabled(bool(ready) and not self.ctx.rendering)
        if len(ready) == len(plan):
            self.ready_icon.setPixmap(icons.pixmap("check", p.success, 22))
            self.ready_lbl.setText(f"Les {len(plan)} pistes sont produites et prêtes à être exportées.")
            self.produce_btn.hide()
        else:
            self.ready_icon.setPixmap(icons.pixmap("alert", p.warning, 22))
            self.ready_lbl.setText(f"{len(ready)} piste(s) prête(s) sur {len(plan)}. Produisez les chapitres "
                                   "manquants ou modifiés avant l'export.")
            self.produce_btn.show()

    # -- modifications -----------------------------------------------------------------
    def _meta_changed(self, *_a) -> None:
        if self._loading:
            return
        m = self.ctx.project.metadata
        for key, w in self.f.items():
            setattr(m, key, w.text().strip())
        m.genre = self.genre.currentText().strip()
        m.language = self.lang.currentData() or "fr"
        m.description = self.desc.toPlainText().strip()
        self.ctx.mark_dirty()

    def _export_changed(self, *_a) -> None:
        if self._loading:
            return
        pr = self.ctx.project
        e, prod = pr.export, pr.production
        e.formats = [k for k, t in self.fmt_toggles.items() if t.isChecked()]
        e.m4b_bitrate = self.m4b_rate.currentText()
        e.mp3_bitrate = self.mp3_rate.currentText()
        e.acx_cover = self.acx_cover.isChecked()
        e.include_credits = self.t_credits.isChecked()
        e.opening_credits = self.open_tpl.text()
        e.closing_credits = self.close_tpl.text()
        e.make_sample = self.t_sample.isChecked()
        e.sample_minutes = self.sample_min.value()
        e.file_pattern = self.pattern.text() or "{index:02d} - {title}"
        e.write_report = self.t_report.isChecked()
        out = self.out_dir.text().strip()
        e.output_dir = out if out and pr.path is not None and Path(out) != pr.path.parent / "Export" else ""
        prod.mastering_preset = self.preset.currentData()
        self.preset_help.setText(PRESET_HELP.get(prod.mastering_preset, ""))
        prod.denoise = self.t_denoise.isChecked()
        prod.deesser = self.t_deess.isChecked()
        prod.room_tone = self.t_room.isChecked()
        self.ctx.mark_dirty()

    def _pick_music(self, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une musique", "",
                                              "Audio (*.mp3 *.wav *.flac *.m4a *.ogg *.opus *.aac)")
        if path:
            self._set_music(key, path)

    def _set_music(self, key: str, path: str) -> None:
        setattr(self.ctx.project.export, key, path)
        self.music_fields[key].setText(path)
        self.ctx.mark_dirty()

    def _bg_level_changed(self, v: int) -> None:
        self.bg_level_lbl.setText(f"{v} dB sous la voix")
        if not self._loading:
            self.ctx.project.export.background_level_db = float(v)
            self.ctx.mark_dirty()

    def _pick_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une couverture", "",
                                              "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if path:
            self._set_cover(path)

    def _set_cover(self, path: str) -> None:
        self.ctx.project.metadata.cover_path = path
        self.cover.set_path(path)
        self.ctx.mark_dirty()

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier d'export", self.out_dir.text())
        if d:
            self.out_dir.setText(d)
            self._export_changed()

    # -- export ------------------------------------------------------------------------
    def export(self) -> None:
        pr = self.ctx.project
        if self.ctx.rendering:
            self.ctx.toast("Attendez la fin de la production.", "warning")
            return
        if not pr.export.formats:
            self.ctx.toast("Choisissez au moins un format de sortie.", "warning")
            return
        plan = renderer.build_plan(pr, self.ctx.library)
        ready = [rc for rc in plan if renderer.chapter_is_current(pr, rc)]
        if len(ready) < len(plan):
            box = QMessageBox(self)
            box.setWindowTitle("Chapitres non produits")
            box.setText(f"{len(plan) - len(ready)} piste(s) ne sont pas encore produites ou ont été modifiées.")
            produce = box.addButton("Produire d'abord", QMessageBox.AcceptRole)
            partial = box.addButton("Exporter les pistes prêtes", QMessageBox.DestructiveRole)
            box.addButton("Annuler", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is produce:
                self.ctx.navigate("production")
                self.ctx.window.pages["production"].start(None)
                return
            if box.clickedButton() is not partial:
                return
        if not ready:
            return
        items = []
        for rc in ready:
            timings = renderer.segment_timings(pr, rc)
            cues = [(a, b, seg.display or seg.text) for (a, b), seg in zip(timings, rc.segments)]
            items.append(ExportItem(rc.title, renderer.chapter_output(pr, rc.id), rc.kind, cues))
        prod = pr.production
        mopts = MasteringOptions(preset=prod.mastering_preset, denoise=prod.denoise, deesser=prod.deesser,
                                 room_tone=prod.room_tone, room_tone_db=prod.room_tone_db,
                                 sample_rate=prod.sample_rate)
        out = Path(self.out_dir.text().strip() or default_export_dir(pr))
        if pr.path is not None:
            self.ctx.window.save_project()
        self.prog_card.show()
        self.results.clear()
        self.verdict.hide()
        self.open_report.hide()
        self.export_btn.setEnabled(False)
        self.prog.setValue(0)

        def work(task):
            return export_audiobook(items, pr.metadata, pr.export, mopts, out,
                                    progress=lambda m, f: task.report((m, f)), cancel=task.cancel_event)

        def progress(v):
            msg, frac = v
            self.prog_lbl.setText(msg)
            self.prog.setValue(int(frac * 1000))

        self._task = tasks.Task(work, pass_reporter=True, on_done=self._done, on_progress=progress,
                                on_error=self._failed).start()

    def _done(self, result) -> None:
        self._last_result = result
        self.export_btn.setEnabled(True)
        self.prog.setValue(1000)
        self.prog_lbl.setText(f"Export terminé — {len(result.files)} fichier(s) dans {result.output_dir}")
        p = theme.CURRENT
        for f in result.files:
            ic = {".m4b": "book", ".mp3": "headphones", ".jpg": "image", ".mp4": "image",
                  ".srt": "type"}.get(f.suffix.lower(), "file")
            try:
                size = f.stat().st_size / 1e6
            except OSError:
                size = 0
            it = QListWidgetItem(icons.icon(ic, p.accent, 18), f"{f.name}   ·   {size:.1f} Mo")
            it.setData(Qt.UserRole, str(f))
            self.results.addItem(it)
        self.verdict.show()
        if result.acx_ok:
            self.verdict.set("✓ Conforme ACX / Audible", "success")
        else:
            self.verdict.set("Certains critères ACX ne sont pas atteints", "warning")
        self.open_report.setVisible(result.report is not None)
        self.ctx.toast("Votre livre audio est prêt ! 🎉", "success", 6000)

    def _failed(self, msg: str, _tb: str) -> None:
        self.export_btn.setEnabled(True)
        self.prog_lbl.setText("Échec de l'export : " + msg)
        QMessageBox.warning(self, "Export impossible", msg)

    def _open_output(self) -> None:
        from ..main_window import open_path

        target = self._last_result.output_dir if self._last_result else Path(self.out_dir.text())
        target.mkdir(parents=True, exist_ok=True)
        open_path(target)

    def _open_report_file(self) -> None:
        if self._last_result and self._last_result.report:
            from ..main_window import open_path

            open_path(self._last_result.report)

    def _open_result(self, item) -> None:
        path = Path(item.data(Qt.UserRole))
        if path.suffix.lower() in (".mp3", ".wav", ".flac"):
            self.ctx.play(path, path.stem)
            return
        from ..main_window import open_path

        open_path(path)
