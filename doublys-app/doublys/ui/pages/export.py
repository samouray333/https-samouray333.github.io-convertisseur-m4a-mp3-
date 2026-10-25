"""Page Export : vidéo doublée (MP4 / MKV), pistes, sous-titres, piste VF seule, aperçu rapide."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox, QProgressBar

from ...core import ffmpeg, pipeline
from ...core import project as project_io
from ..widgets import Card, ToggleSwitch, button, card_title, label
from .base import Page


class ExportPage(Page):
    name = "export"

    def __init__(self, ctx):
        super().__init__(ctx, "Export", "La vidéo est copiée telle quelle (sans perte) ; seule la piste son "
                         "française est ajoutée, avec les sous-titres si vous le souhaitez.", scroll=True)
        self._loading = False

        fmt = Card()
        fmt.add(card_title("Vidéo doublée", "", "film"))
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        self.container = QComboBox()
        self.container.addItem("MP4 (lu partout : Windows, téléphones, TV)", "mp4")
        self.container.addItem("MKV (toutes les pistes, sous-titres texte)", "mkv")
        self.container.currentIndexChanged.connect(self._save)
        g.addWidget(label("Format", "Muted"), 0, 0)
        g.addWidget(self.container, 0, 1)
        self.bitrate = QComboBox()
        for b in ("128k", "160k", "192k", "256k", "320k"):
            self.bitrate.addItem(f"AAC {b.replace('k', ' kb/s')}", b)
        self.bitrate.currentIndexChanged.connect(self._save)
        g.addWidget(label("Qualité du son", "Muted"), 1, 0)
        g.addWidget(self.bitrate, 1, 1)
        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Dossier du projet")
        self.out_dir.editingFinished.connect(self._save)
        pick = button("Parcourir…", "folder")
        pick.clicked.connect(self._pick_dir)
        g.addWidget(label("Dossier", "Muted"), 2, 0)
        g.addWidget(self.out_dir, 2, 1)
        g.addWidget(pick, 2, 2)
        g.setColumnStretch(1, 1)
        fmt.add(g)
        self.t_norm = ToggleSwitch("Normaliser le volume de la VF (-16 LUFS, comme les plateformes de vidéo)")
        self.t_vo = ToggleSwitch("Garder aussi la piste anglaise d'origine (choix de la langue dans le lecteur)")
        for t in (self.t_norm, self.t_vo):
            t.toggled.connect(self._save)
            fmt.add(t)
        self.body.addWidget(fmt)

        sub = Card()
        sub.add(card_title("Sous-titres", "", "captions"))
        self.t_sfr = ToggleSwitch("Sous-titres français intégrés (désactivés par défaut dans le lecteur)")
        self.t_sen = ToggleSwitch("Sous-titres anglais intégrés")
        self.t_srt = ToggleSwitch("Fichiers .srt à côté de la vidéo (français et anglais)")
        self.t_burn = ToggleSwitch("Incruster les sous-titres français dans l'image (réencode la vidéo : plus long)")
        for t in (self.t_sfr, self.t_sen, self.t_srt, self.t_burn):
            t.toggled.connect(self._save)
            sub.add(t)
        self.enc_info = label("", "Hint", wrap=True)
        sub.add(self.enc_info)
        self.body.addWidget(sub)

        aud = Card()
        aud.add(card_title("Piste VF seule", "Le son français complet (voix + fond), sans l'image.", "volume"))
        row = QHBoxLayout()
        self.audio_only = QComboBox()
        self.audio_only.addItem("Non", "")
        self.audio_only.addItem("WAV (sans perte)", "wav")
        self.audio_only.addItem("MP3 192 kb/s", "mp3")
        self.audio_only.currentIndexChanged.connect(self._save)
        row.addWidget(self.audio_only)
        row.addStretch(1)
        aud.add(row)
        self.body.addWidget(aud)

        go = Card()
        r = QHBoxLayout()
        self.export_btn = button("Exporter la vidéo doublée", "package", "primary")
        self.export_btn.clicked.connect(self.export)
        self.preview_btn = button("Aperçu rapide", "eye", tooltip="Vidéo complète sans normalisation ni sous-titres, "
                                  "ouverte dans le lecteur de Windows")
        self.preview_btn.clicked.connect(self.preview)
        self.open_btn = button("Ouvrir le dossier", "external")
        self.open_btn.clicked.connect(self._open_dir)
        r.addWidget(self.export_btn)
        r.addWidget(self.preview_btn)
        r.addStretch(1)
        r.addWidget(self.open_btn)
        go.add(r)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        go.add(self.bar)
        self.status = label("", "Muted", wrap=True)
        go.add(self.status)
        self.body.addWidget(go)
        self.body.addStretch(1)

        ctx.runner.progress.connect(self._progress)
        ctx.runner.finished.connect(self._finished)
        ctx.runner.started.connect(lambda _t: self._enable())

    # -- réglages ---------------------------------------------------------------------
    def on_show(self) -> None:
        self._load()
        try:
            enc = next((e for e in ("libx264", "libopenh264", "h264_mf") if ffmpeg.has_encoder(e)), None)
        except Exception:
            enc = None
        self.enc_info.setText(f"Encodeur pour l'incrustation : {enc}." if enc else
                              "Aucun encodeur H.264 trouvé : l'incrustation des sous-titres est indisponible.")
        self._enable()

    def on_project_changed(self) -> None:
        self._load()
        self._enable()

    def _load(self) -> None:
        pr = self.ctx.project
        if pr is None:
            return
        o = pr.export
        self._loading = True
        self.container.setCurrentIndex(max(0, self.container.findData(o.container)))
        self.bitrate.setCurrentIndex(max(0, self.bitrate.findData(o.audio_bitrate)))
        self.out_dir.setText(o.output_dir)
        self.out_dir.setPlaceholderText(str(project_io.default_export_dir(pr)))
        self.t_norm.setChecked(o.normalize)
        self.t_vo.setChecked(o.keep_original_audio)
        self.t_sfr.setChecked(o.subtitles_fr)
        self.t_sen.setChecked(o.subtitles_en)
        self.t_srt.setChecked(o.srt_files)
        self.t_burn.setChecked(o.burn_subtitles)
        self.audio_only.setCurrentIndex(max(0, self.audio_only.findData(o.audio_only)))
        self._loading = False

    def _save(self, *_args) -> None:
        pr = self.ctx.project
        if pr is None or self._loading:
            return
        o = pr.export
        o.container = self.container.currentData()
        o.audio_bitrate = self.bitrate.currentData()
        o.output_dir = self.out_dir.text().strip()
        o.normalize = self.t_norm.isChecked()
        o.keep_original_audio = self.t_vo.isChecked()
        o.subtitles_fr = self.t_sfr.isChecked()
        o.subtitles_en = self.t_sen.isChecked()
        o.srt_files = self.t_srt.isChecked()
        o.burn_subtitles = self.t_burn.isChecked()
        o.audio_only = self.audio_only.currentData() or ""
        self.ctx.mark_dirty()

    def _pick_dir(self) -> None:
        pr = self.ctx.project
        start = self.out_dir.text() or (str(project_io.default_export_dir(pr)) if pr else "")
        d = QFileDialog.getExistingDirectory(self, "Dossier d'export", start)
        if d:
            self.out_dir.setText(d)
            self._save()

    def _enable(self) -> None:
        pr = self.ctx.project
        ready = pr is not None and pr.step_done("mix")
        busy = self.ctx.runner.running
        self.export_btn.setEnabled(ready and not busy)
        self.preview_btn.setEnabled(ready and not busy)
        self.open_btn.setEnabled(pr is not None)
        if pr is None:
            self.status.setText("Aucun projet.")
        elif not ready and not busy:
            self.status.setText("La VF n'est pas encore mixée : lancez « Créer la VF automatiquement » (page Doublage).")
        elif not busy and pr.last_export:
            self.status.setText(f"Dernier export : {pr.last_export}")

    # -- export -----------------------------------------------------------------------
    def export(self) -> None:
        pr = self.ctx.project
        if pr is None:
            return
        self._save()
        self._preview = False
        self.ctx.runner.start("Export", ["export"], lambda job: pipeline.export_files(pr, job))

    def preview(self) -> None:
        pr = self.ctx.project
        if pr is None:
            return
        self._preview = True
        self.ctx.runner.start("Aperçu rapide", ["export"], lambda job: pipeline.export_files(pr, job, preview=True))

    def _progress(self, step, frac, msg, overall, remaining) -> None:
        if step == "export":
            self.bar.setValue(int(frac * 1000))
            self.status.setText(msg)

    def _finished(self, ok: bool, msg: str, result) -> None:
        self._enable()
        if not isinstance(result, list) or not result:
            if not ok and self.isVisible() and msg != "Traitement arrêté.":
                QMessageBox.warning(self, "Export impossible", msg)
            return
        from ..main_window import open_path

        self.bar.setValue(1000)
        if getattr(self, "_preview", False):
            self.status.setText("Aperçu prêt : ouverture dans le lecteur de Windows…")
            open_path(Path(result[0]))
            return
        names = ", ".join(Path(f).name for f in result)
        self.status.setText(f"Exporté : {names}")
        self.ctx.toast("Vidéo doublée exportée ✔", "success", 5000)
        self.ctx.save()

    def _open_dir(self) -> None:
        from ..main_window import open_path

        pr = self.ctx.project
        if pr is not None:
            open_path(project_io.default_export_dir(pr))
