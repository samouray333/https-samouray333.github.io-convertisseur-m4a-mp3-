"""Page Paramètres : doublage du projet, apparence, performances, traduction en ligne, données."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout,
                               QLineEdit, QSpinBox, QToolButton)

from ... import __version__, paths
from ...config import settings
from ...core import ffmpeg
from ...core.engines import installer
from ...core.models import TRANSLATORS, WHISPER_MODELS
from ...core.secrets import protect, unprotect
from .. import theme
from ..widgets import Card, ToggleSwitch, button, card_title, label
from .base import Page


def _human(n: float) -> str:
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit in ("o", "Ko") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} Po"


def _spin(lo: float, hi: float, step: float, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    if suffix:
        s.setSuffix(suffix)
    return s


class SettingsPage(Page):
    name = "settings"

    def __init__(self, ctx, window):
        super().__init__(ctx, "Paramètres", "Réglages du doublage (pour le projet ouvert) et de Doublys.", scroll=True)
        self.window_ = window
        self._loading = False
        s = settings()

        # -- doublage (projet) ----------------------------------------------------------
        dub = Card()
        dub.add(card_title("Doublage du projet", "Modifier un réglage rend caduques les étapes concernées : elles "
                           "seront refaites au prochain lancement.", "film"))
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        r = 0
        self.t_sep = ToggleSwitch("Séparer les voix de la musique et des bruits (recommandé)")
        g.addWidget(self.t_sep, r, 0, 1, 2)
        r += 1
        self.duck = _spin(-40, -6, 1, 0, " dB")
        g.addWidget(label("Sans séparation : voix d'origine baissée de", "Muted"), r, 0)
        g.addWidget(self.duck, r, 1)
        r += 1
        self.whisper = QComboBox()
        for k, v in WHISPER_MODELS.items():
            self.whisper.addItem(v, k)
        g.addWidget(label("Transcription (Whisper)", "Muted"), r, 0)
        g.addWidget(self.whisper, r, 1)
        r += 1
        self.translator = QComboBox()
        for k, (v, _m) in TRANSLATORS.items():
            self.translator.addItem(v, k)
        g.addWidget(label("Traduction", "Muted"), r, 0)
        g.addWidget(self.translator, r, 1)
        r += 1
        self.pause = _spin(0.3, 2.0, 0.05, 2, " s")
        g.addWidget(label("Silence qui sépare deux répliques", "Muted"), r, 0)
        g.addWidget(self.pause, r, 1)
        r += 1
        self.max_line = _spin(6, 20, 0.5, 1, " s")
        g.addWidget(label("Durée maximale d'une réplique", "Muted"), r, 0)
        g.addWidget(self.max_line, r, 1)
        r += 1
        self.threshold = _spin(0.30, 0.95, 0.02, 2)
        self.threshold.setToolTip("Plus haut : moins de personnes (voix proches regroupées). Plus bas : plus de "
                                  "personnes.")
        g.addWidget(label("Regroupement des voix (seuil)", "Muted"), r, 0)
        g.addWidget(self.threshold, r, 1)
        r += 1
        self.max_spk = QSpinBox()
        self.max_spk.setRange(0, 20)
        self.max_spk.setSpecialValueText("Automatique")
        g.addWidget(label("Nombre maximal de personnes", "Muted"), r, 0)
        g.addWidget(self.max_spk, r, 1)
        r += 1
        self.max_rate = _spin(1.0, 1.6, 0.05, 2)
        self.max_rate.setPrefix("× ")
        g.addWidget(label("Débit maximal de la voix française", "Muted"), r, 0)
        g.addWidget(self.max_rate, r, 1)
        r += 1
        self.cps = _spin(10, 20, 0.5, 1, " car./s")
        g.addWidget(label("Débit de référence (traduction DeepSeek)", "Muted"), r, 0)
        g.addWidget(self.cps, r, 1)
        r += 1
        self.t_keep = ToggleSwitch("Laisser la voix d'origine faiblement sous la VF")
        g.addWidget(self.t_keep, r, 0, 1, 2)
        r += 1
        self.keep_db = _spin(-40, -6, 1, 0, " dB")
        g.addWidget(label("Niveau de la voix d'origine laissée", "Muted"), r, 0)
        g.addWidget(self.keep_db, r, 1)
        r += 1
        self.t_level = ToggleSwitch("Aligner le niveau de chaque réplique sur la voix d'origine")
        g.addWidget(self.t_level, r, 0, 1, 2)
        r += 1
        self.t_expr = ToggleSwitch("Répliques fortes (cris, colère) plus expressives avec Chatterbox "
                                   "(≈ 25 s de calcul chacune, 25 au plus)")
        g.addWidget(self.t_expr, r, 0, 1, 2)
        g.setColumnStretch(1, 1)
        dub.add(g)
        self.dub_card = dub
        self.body.addWidget(dub)
        for w in (self.t_sep, self.t_keep, self.t_level, self.t_expr):
            w.toggled.connect(self._save_project)
        for w in (self.whisper, self.translator):
            w.currentIndexChanged.connect(self._save_project)
        for w in (self.duck, self.pause, self.max_line, self.threshold, self.max_rate, self.cps, self.keep_db):
            w.editingFinished.connect(self._save_project)
        self.max_spk.editingFinished.connect(self._save_project)

        # -- traduction en ligne -----------------------------------------------------------
        aic = Card()
        aic.add(card_title("Traduction en ligne (DeepSeek)", "Option : traduit par lots avec le contexte et adapte la "
                           "longueur au temps disponible ; bouton « Raccourcir » du tableau.", "languages"))
        g4 = QGridLayout()
        g4.setHorizontalSpacing(14)
        g4.setVerticalSpacing(10)
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_key.setPlaceholderText("Clé enregistrée" if unprotect(s.get("ai_key", "")) else "sk-…")
        self.ai_key.editingFinished.connect(self._save_ai_key)
        g4.addWidget(label("Clé API", "Muted"), 0, 0)
        g4.addWidget(self.ai_key, 0, 1)
        test = button("Tester", "check")
        test.clicked.connect(self._test_ai)
        g4.addWidget(test, 0, 2)
        self.ai_model = QLineEdit(s.get("ai_model", ""))
        self.ai_model.setPlaceholderText("Automatique")
        self.ai_model.editingFinished.connect(lambda: s.set("ai_model", self.ai_model.text().strip()))
        g4.addWidget(label("Modèle", "Muted"), 1, 0)
        g4.addWidget(self.ai_model, 1, 1)
        g4.setColumnStretch(1, 1)
        aic.add(g4)
        self.ai_info = label("Créez une clé sur platform.deepseek.com (API keys). Elle est chiffrée sur cet ordinateur. "
                             "Service payant à l'usage (quelques centimes par heure de vidéo) ; le texte anglais des "
                             "répliques est envoyé à DeepSeek. Sans clé, la traduction reste 100 % locale (Opus-MT).",
                             "Hint", wrap=True)
        aic.add(self.ai_info)
        self.body.addWidget(aic)

        # -- apparence --------------------------------------------------------------------
        ap = Card()
        ap.add(card_title("Apparence", "", "palette"))
        g1 = QGridLayout()
        g1.setHorizontalSpacing(14)
        g1.setVerticalSpacing(10)
        self.theme = QComboBox()
        self.theme.addItem("Sombre", "dark")
        self.theme.addItem("Clair", "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.get("theme"))))
        self.theme.currentIndexChanged.connect(self._apply_theme)
        g1.addWidget(label("Thème", "Muted"), 0, 0)
        g1.addWidget(self.theme, 0, 1)
        g1.addWidget(label("Couleur d'accent", "Muted"), 1, 0)
        sw = QHBoxLayout()
        sw.setSpacing(8)
        for name, color in theme.ACCENTS.items():
            b = QToolButton()
            b.setFixedSize(30, 30)
            b.setToolTip(name)
            b.setCursor(Qt.PointingHandCursor)
            sel = color.lower() == str(s.get("accent")).lower()
            b.setStyleSheet(f"QToolButton {{ background: {color}; border-radius: 15px; border: "
                            f"{'3px solid white' if sel else 'none'}; }}")
            b.clicked.connect(lambda _=False, c=color: self._set_accent(c))
            sw.addWidget(b)
        sw.addStretch(1)
        g1.addLayout(sw, 1, 1)
        g1.setColumnStretch(1, 1)
        ap.add(g1)
        self.body.addWidget(ap)

        # -- général et performances ----------------------------------------------------------
        gen = Card()
        gen.add(card_title("Général et performances", "", "sliders"))
        g2 = QGridLayout()
        g2.setHorizontalSpacing(14)
        g2.setVerticalSpacing(10)
        self.proj_dir = QLineEdit(str(s.projects_dir()))
        self.proj_dir.editingFinished.connect(lambda: s.set("projects_dir", self.proj_dir.text().strip()))
        pb = button("Parcourir…", "folder")
        pb.clicked.connect(self._pick_projects)
        g2.addWidget(label("Dossier des projets", "Muted"), 0, 0)
        g2.addWidget(self.proj_dir, 0, 1)
        g2.addWidget(pb, 0, 2)
        self.device = QComboBox()
        for k, v in (("auto", "Automatique"), ("cuda", "Carte graphique NVIDIA (CUDA)"), ("cpu", "Processeur")):
            self.device.addItem(v, k)
        self.device.setCurrentIndex(max(0, self.device.findData(s.get("device"))))
        self.device.currentIndexChanged.connect(self._device_changed)
        g2.addWidget(label("Calcul neuronal", "Muted"), 1, 0)
        g2.addWidget(self.device, 1, 1)
        self.fc_mode = QComboBox()
        self.fc_mode.addItem("Rapide (recommandé sans carte NVIDIA)", "fast")
        self.fc_mode.addItem("Fidèle (plus lent)", "best")
        self.fc_mode.setCurrentIndex(max(0, self.fc_mode.findData(s.get("fastclone_mode", "fast"))))
        self.fc_mode.currentIndexChanged.connect(self._fastclone_changed)
        g2.addWidget(label("Conversion du clonage rapide", "Muted"), 2, 0)
        g2.addWidget(self.fc_mode, 2, 1)
        self.edge_conc = QSpinBox()
        self.edge_conc.setRange(1, 8)
        self.edge_conc.setValue(int(s.get("edge_concurrency", 2)))
        self.edge_conc.valueChanged.connect(lambda v: s.set("edge_concurrency", v))
        g2.addWidget(label("Requêtes simultanées (voix Microsoft)", "Muted"), 3, 0)
        g2.addWidget(self.edge_conc, 3, 1)
        self.preview = QLineEdit(s.get("preview_sentence"))
        self.preview.editingFinished.connect(lambda: s.set("preview_sentence", self.preview.text().strip()))
        g2.addWidget(label("Phrase d'essai des voix", "Muted"), 4, 0)
        g2.addWidget(self.preview, 4, 1, 1, 2)
        self.ffmpeg = QLineEdit(s.get("ffmpeg_path") or "")
        self.ffmpeg.setPlaceholderText("Automatique (FFmpeg intégré)")
        self.ffmpeg.editingFinished.connect(lambda: s.set("ffmpeg_path", self.ffmpeg.text().strip()))
        g2.addWidget(label("Chemin de FFmpeg", "Muted"), 5, 0)
        g2.addWidget(self.ffmpeg, 5, 1, 1, 2)
        self.autosave = QSpinBox()
        self.autosave.setRange(1, 30)
        self.autosave.setSuffix(" min")
        self.autosave.setValue(int(s.get("autosave_minutes", 2)))
        self.autosave.valueChanged.connect(lambda v: s.set("autosave_minutes", v))
        g2.addWidget(label("Sauvegarde automatique", "Muted"), 6, 0)
        g2.addWidget(self.autosave, 6, 1)
        g2.setColumnStretch(1, 1)
        gen.add(g2)
        self.ff_info = label("", "Hint", wrap=True)
        gen.add(self.ff_info)
        self.body.addWidget(gen)

        # -- données ------------------------------------------------------------------------
        data = Card()
        data.add(card_title("Données et stockage", "", "folder"))
        self.data_info = label("", "Muted", wrap=True)
        data.add(self.data_info)
        dr = QHBoxLayout()
        o1 = button("Dossier des données", "external")
        o1.clicked.connect(lambda: self._open(paths.data_dir()))
        o3 = button("Journal", "list")
        o3.clicked.connect(lambda: self._open(paths.logs_dir()))
        clear_proj = button("Vider le cache des voix du projet", "trash", "danger")
        clear_proj.clicked.connect(self._clear_project_cache)
        dr.addWidget(o1)
        dr.addWidget(o3)
        dr.addStretch(1)
        dr.addWidget(clear_proj)
        data.add(dr)
        self.body.addWidget(data)

        about = Card()
        about.add(card_title(f"Doublys {__version__} — Echo Matras", "Doublage vidéo anglais → français, sur votre "
                             "ordinateur.", "info"))
        about.add(label("Séparation : Demucs (MIT). Transcription : Whisper / faster-whisper (MIT). Personnes : "
                        "speechbrain ECAPA (Apache 2.0). Traduction : Opus-MT (CC-BY 4.0) ou DeepSeek (en ligne). "
                        "Voix : Kokoro (Apache 2.0), Chatterbox (MIT), XTTS-v2 (CPML, non commercial), RVC (MIT), "
                        "voix Microsoft (en ligne). Vidéo : FFmpeg (LGPL).", "Hint", wrap=True))
        about.add(label("Rappel : ne doublez avec une voix clonée que des personnes qui ont donné leur accord, et "
                        "assurez-vous de disposer des droits sur les vidéos que vous traduisez et diffusez.", "Hint",
                        wrap=True))
        self.t_updates = ToggleSwitch("Vérifier les mises à jour au démarrage", bool(s.get("check_updates", True)))
        self.t_updates.toggled.connect(lambda on: s.set("check_updates", on))
        about.add(self.t_updates)
        ar = QHBoxLayout()
        ab = button("À propos et licences", "info")
        ab.clicked.connect(window.about)
        upd = button("Vérifier les mises à jour", "refresh")
        upd.clicked.connect(lambda: window.check_updates(silent=False))
        ar.addWidget(ab)
        ar.addWidget(upd)
        ar.addStretch(1)
        about.add(ar)
        self.body.addWidget(about)
        self.body.addStretch(1)

    # -- projet -------------------------------------------------------------------------
    def on_project_changed(self) -> None:
        self._load_project()

    def _load_project(self) -> None:
        pr = self.ctx.project
        self.dub_card.setEnabled(pr is not None and not self.ctx.runner.running)
        if pr is None:
            return
        st = pr.settings
        self._loading = True
        self.t_sep.setChecked(st.separate)
        self.duck.setValue(st.no_separation_duck_db)
        self.whisper.setCurrentIndex(max(0, self.whisper.findData(st.whisper_model)))
        self.translator.setCurrentIndex(max(0, self.translator.findData(st.translator)))
        self.pause.setValue(st.pause_split)
        self.max_line.setValue(st.max_line)
        self.threshold.setValue(st.speaker_threshold)
        self.max_spk.setValue(st.max_speakers)
        self.max_rate.setValue(st.max_rate)
        self.cps.setValue(st.chars_per_second)
        self.t_keep.setChecked(st.keep_original_voice)
        self.keep_db.setValue(st.original_voice_db)
        self.t_level.setChecked(st.match_level)
        self.t_expr.setChecked(st.expressive)
        self._loading = False

    def _save_project(self, *_args) -> None:
        pr = self.ctx.project
        if pr is None or self._loading:
            return
        st = pr.settings
        before = dict(vars(st))
        st.separate = self.t_sep.isChecked()
        st.no_separation_duck_db = self.duck.value()
        st.whisper_model = self.whisper.currentData()
        st.translator = self.translator.currentData()
        st.pause_split = self.pause.value()
        st.max_line = self.max_line.value()
        st.speaker_threshold = self.threshold.value()
        st.max_speakers = self.max_spk.value()
        st.max_rate = self.max_rate.value()
        st.chars_per_second = self.cps.value()
        st.keep_original_voice = self.t_keep.isChecked()
        st.original_voice_db = self.keep_db.value()
        st.match_level = self.t_level.isChecked()
        st.expressive = self.t_expr.isChecked()
        changed = {k for k, v in vars(st).items() if before.get(k) != v}
        if not changed:
            return
        # première étape touchée par le changement : elle et les suivantes seront refaites
        first = {"separate": "separate", "whisper_model": "transcribe", "pause_split": "segment",
                 "max_line": "segment", "speaker_threshold": "speakers", "max_speakers": "speakers",
                 "translator": "translate", "chars_per_second": "translate", "max_rate": "dub",
                 "match_level": "dub", "expressive": "dub", "keep_original_voice": "mix", "original_voice_db": "mix",
                 "no_separation_duck_db": "mix"}
        from ...core.models import STEPS

        steps = [first[k] for k in changed if k in first]
        if steps:
            step = min(steps, key=STEPS.index)
            if step == "separate" and not st.separate:
                step = "transcribe"
            pr.invalidate_from(step)
        self.ctx.mark_dirty()

    def on_show(self) -> None:
        self._load_project()
        try:
            self.ff_info.setText("FFmpeg : " + ffmpeg.version())
        except Exception as exc:
            self.ff_info.setText(f"FFmpeg introuvable : {exc}")
        engines_size = installer.disk_usage(paths.engines_dir())
        models_size = installer.disk_usage(paths.models_dir())
        info = f"Moteurs installés : {_human(engines_size)} · Modèles : {_human(models_size)}"
        pr = self.ctx.project
        if pr is not None and pr.path is not None:
            from ...core import project as project_io

            info += f" · Projet ouvert : {_human(project_io.cache_size_bytes(pr))}"
        self.data_info.setText(info + f"\nDonnées : {paths.data_dir()}")

    # -- préférences ----------------------------------------------------------------------
    def _apply_theme(self) -> None:
        settings().set("theme", self.theme.currentData())
        theme.apply(QApplication.instance(), settings().get("theme"), settings().get("accent"))
        from ..main_window import apply_window_chrome

        apply_window_chrome(self.window_)
        self.ctx.toast("Thème appliqué. Redémarrez pour actualiser toutes les icônes.", "info")

    def _set_accent(self, color: str) -> None:
        settings().set("accent", color)
        self._apply_theme()

    def _device_changed(self) -> None:
        settings().set("device", self.device.currentData())
        from ...core.engines import shutdown_all

        shutdown_all()

    def _fastclone_changed(self) -> None:
        settings().set("fastclone_mode", self.fc_mode.currentData())
        from ...core.engines import get_engine

        get_engine("fastclone").shutdown()

    def _save_ai_key(self) -> None:
        key = self.ai_key.text().strip()
        if not key:
            return
        settings().set("ai_key", protect(key))
        settings().set("ai_model", "")
        self.ai_model.clear()
        self.ai_key.clear()
        self.ai_key.setPlaceholderText("Clé enregistrée")
        self.ctx.toast("Clé DeepSeek enregistrée.", "success")

    def _test_ai(self) -> None:
        from ...core import ai
        from .. import tasks

        self._save_ai_key()
        try:
            client = ai.client_from_settings()
        except ai.AIError as exc:
            self.ai_info.setText(str(exc))
            return
        self.ai_info.setText("Connexion à DeepSeek…")

        def ok(model: str) -> None:
            settings().set("ai_model", model)
            self.ai_model.setText(model)
            self.ai_info.setText(f"✓ Clé valide. Modèle utilisé : {model}.")

        self._ai_task = tasks.run(lambda: (client.list_models(), client.pick_model())[1], on_done=ok,
                                  on_error=lambda m, _t: self.ai_info.setText("⚠ " + m))

    def _pick_projects(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier des projets", self.proj_dir.text())
        if d:
            self.proj_dir.setText(d)
            settings().set("projects_dir", d)

    def _open(self, p) -> None:
        from ..main_window import open_path

        open_path(p)

    def _clear_project_cache(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from ...core import project as project_io

        pr = self.ctx.project
        if pr is None or pr.path is None:
            return
        if QMessageBox.question(self, "Vider le cache", "Supprimer toutes les voix françaises déjà produites pour ce "
                                "projet ? Il faudra relancer l'étape « Voix françaises et calage ».") != QMessageBox.Yes:
            return
        project_io.clear_voice_cache(pr)
        self.ctx.mark_dirty()
        self.ctx.lines_changed.emit()
        self.ctx.toast("Cache des voix supprimé.", "success")
