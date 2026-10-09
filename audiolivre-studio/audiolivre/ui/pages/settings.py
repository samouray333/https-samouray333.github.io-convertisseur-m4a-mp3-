"""Page Paramètres : apparence, préférences, performances, données."""

from __future__ import annotations

import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QSpinBox,
                               QToolButton)

from ... import __version__, paths
from ...config import settings
from ...core import ffmpeg
from ...core.engines import installer
from .. import theme
from ..widgets import Card, button, card_title, label
from .base import Page


def _human(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit in ("o", "Ko") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} Po"


class SettingsPage(Page):
    name = "settings"

    def __init__(self, ctx, window):
        super().__init__(ctx, "Paramètres", "Personnalisez AudioLivre Studio.", scroll=True)
        self.window_ = window
        s = settings()

        ap = Card()
        ap.add(card_title("Apparence", "", "palette"))
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        self.theme = QComboBox()
        self.theme.addItem("Sombre", "dark")
        self.theme.addItem("Clair", "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.get("theme"))))
        self.theme.currentIndexChanged.connect(self._apply_theme)
        g.addWidget(label("Thème", "Muted"), 0, 0)
        g.addWidget(self.theme, 0, 1)
        g.addWidget(label("Couleur d'accent", "Muted"), 1, 0)
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
        g.addLayout(sw, 1, 1)
        g.setColumnStretch(1, 1)
        ap.add(g)
        ap.add(label("Le changement de thème s'applique immédiatement ; certains éléments sont actualisés au "
                     "prochain démarrage.", "Hint", wrap=True))
        self.body.addWidget(ap)

        gen = Card()
        gen.add(card_title("Général", "", "sliders"))
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
        self.autosave = QSpinBox()
        self.autosave.setRange(1, 30)
        self.autosave.setSuffix(" min")
        self.autosave.setValue(int(s.get("autosave_minutes", 3)))
        self.autosave.valueChanged.connect(lambda v: s.set("autosave_minutes", v))
        g2.addWidget(label("Sauvegarde automatique", "Muted"), 1, 0)
        g2.addWidget(self.autosave, 1, 1)
        self.preview = QLineEdit(s.get("preview_sentence"))
        self.preview.editingFinished.connect(lambda: s.set("preview_sentence", self.preview.text().strip()))
        g2.addWidget(label("Phrase d'aperçu des voix", "Muted"), 2, 0)
        g2.addWidget(self.preview, 2, 1, 1, 2)
        g2.setColumnStretch(1, 1)
        gen.add(g2)
        self.body.addWidget(gen)

        perf = Card()
        perf.add(card_title("Performances", "", "zap"))
        g3 = QGridLayout()
        g3.setHorizontalSpacing(14)
        g3.setVerticalSpacing(10)
        self.device = QComboBox()
        for k, v in (("auto", "Automatique"), ("cuda", "Carte graphique NVIDIA (CUDA)"), ("cpu", "Processeur")):
            self.device.addItem(v, k)
        self.device.setCurrentIndex(max(0, self.device.findData(s.get("device"))))
        self.device.currentIndexChanged.connect(self._device_changed)
        g3.addWidget(label("Calcul des voix neuronales", "Muted"), 0, 0)
        g3.addWidget(self.device, 0, 1)
        self.edge_conc = QSpinBox()
        self.edge_conc.setRange(1, 8)
        self.edge_conc.setValue(int(s.get("edge_concurrency", 4)))
        self.edge_conc.valueChanged.connect(lambda v: s.set("edge_concurrency", v))
        g3.addWidget(label("Requêtes simultanées (voix Microsoft)", "Muted"), 1, 0)
        g3.addWidget(self.edge_conc, 1, 1)
        self.ffmpeg = QLineEdit(s.get("ffmpeg_path") or "")
        self.ffmpeg.setPlaceholderText("Automatique (FFmpeg intégré)")
        self.ffmpeg.editingFinished.connect(lambda: s.set("ffmpeg_path", self.ffmpeg.text().strip()))
        g3.addWidget(label("Chemin de FFmpeg", "Muted"), 2, 0)
        g3.addWidget(self.ffmpeg, 2, 1)
        g3.setColumnStretch(1, 1)
        perf.add(g3)
        self.ff_info = label("", "Hint", wrap=True)
        perf.add(self.ff_info)
        self.body.addWidget(perf)

        data = Card()
        data.add(card_title("Données et stockage", "", "folder"))
        self.data_info = label("", "Muted", wrap=True)
        data.add(self.data_info)
        dr = QHBoxLayout()
        o1 = button("Ouvrir le dossier des données", "external")
        o1.clicked.connect(lambda: self._open(paths.data_dir()))
        o2 = button("Ouvrir le dossier des voix", "mic")
        o2.clicked.connect(lambda: self._open(paths.voices_dir()))
        o3 = button("Journal", "list")
        o3.clicked.connect(lambda: self._open(paths.logs_dir()))
        clear = button("Vider le cache des aperçus", "trash", "danger")
        clear.clicked.connect(self._clear_preview)
        clear_proj = button("Vider le cache audio du projet", "trash", "danger")
        clear_proj.clicked.connect(self._clear_project_cache)
        for b in (o1, o2, o3):
            dr.addWidget(b)
        dr.addStretch(1)
        data.add(dr)
        dr2 = QHBoxLayout()
        dr2.addWidget(clear)
        dr2.addWidget(clear_proj)
        dr2.addStretch(1)
        data.add(dr2)
        self.body.addWidget(data)

        about = Card()
        about.add(card_title(f"AudioLivre Studio {__version__}", "Logiciel libre et gratuit de création de livres "
                             "audio.", "info"))
        about.add(label("Voix neuronales : Microsoft Edge (service en ligne gratuit), XTTS-v2 (Coqui, licence CPML), "
                        "Chatterbox (Resemble AI, MIT), Kokoro (Apache 2.0). Traitement audio : FFmpeg. Interface : "
                        "Qt for Python (PySide6). Lecture PDF : PyMuPDF.", "Hint", wrap=True))
        about.add(label("Rappel : n'utilisez le clonage qu'avec votre propre voix ou avec l'accord explicite de la "
                        "personne concernée, et assurez-vous de disposer des droits sur les textes que vous "
                        "enregistrez.", "Hint", wrap=True))
        ab = button("À propos et licences", "info")
        ab.clicked.connect(window.about)
        about.add(ab, None)
        self.body.addWidget(about)
        self.body.addStretch(1)

    def on_show(self) -> None:
        try:
            self.ff_info.setText("FFmpeg : " + ffmpeg.version())
        except Exception as exc:
            self.ff_info.setText(f"FFmpeg introuvable : {exc}")
        engines_size = installer.disk_usage(paths.engines_dir())
        models_size = installer.disk_usage(paths.models_dir())
        prev = installer.disk_usage(paths.preview_cache_dir())
        self.data_info.setText(f"Moteurs installés : {_human(engines_size)} · Modèles : {_human(models_size)} · "
                               f"Aperçus : {_human(prev)}\nDonnées : {paths.data_dir()}")

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

    def _pick_projects(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier des projets", self.proj_dir.text())
        if d:
            self.proj_dir.setText(d)
            settings().set("projects_dir", d)

    def _open(self, p) -> None:
        from ..main_window import open_path

        open_path(p)

    def _clear_preview(self) -> None:
        shutil.rmtree(paths.preview_cache_dir(), ignore_errors=True)
        paths.preview_cache_dir()
        self.on_show()
        self.ctx.toast("Cache des aperçus vidé.", "success")

    def _clear_project_cache(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from ...core import project_io

        if self.ctx.project.path is None:
            return
        if QMessageBox.question(self, "Vider le cache", "Supprimer tout l'audio déjà produit pour ce projet ? "
                                "Il faudra relancer la production.") != QMessageBox.Yes:
            return
        project_io.clear_cache(self.ctx.project)
        self.ctx.toast("Cache audio du projet supprimé.", "success")
