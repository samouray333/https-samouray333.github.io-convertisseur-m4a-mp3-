"""Fenêtre principale : barre latérale, pages, lecteur, gestion des projets."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..config import settings
from ..core import importers, project_io
from ..core.engines import shutdown_all
from ..core.models import Chapter, Project
from ..core.textproc import clean_imported_text, format_duration
from . import icons, tasks, theme
from .context import AppContext
from .player import PlayerBar
from .widgets import IconButton, label

log = logging.getLogger(__name__)

NAV = [
    ("home", "Accueil", "home"),
    ("manuscript", "Manuscrit", "book"),
    ("voices", "Voix && clonage", "mic"),
    ("production", "Production", "wave"),
    ("export", "Export", "package"),
]
TOOLS = [
    ("engines", "Moteurs IA", "cpu"),
    ("settings", "Paramètres", "sliders"),
]


def apply_window_chrome(win: QWidget) -> None:
    """Barre de titre assortie au thème sous Windows 10/11."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        hwnd = int(win.winId())
        dark = ctypes.c_int(1 if theme.CURRENT.dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                break
        c = QColor(theme.CURRENT.sidebar)
        colorref = ctypes.c_int(c.red() | (c.green() << 8) | (c.blue() << 16))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))
    except Exception:
        pass


class Sidebar(QFrame):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(248)
        self.window_ = window
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(icons.app_logo(84).scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label("AudioLivre", "BrandTitle"))
        col.addWidget(label("Studio professionnel", "BrandSub"))
        brand.addLayout(col, 1)
        self.menu_btn = IconButton("more", "Menu fichier", 32, 18)
        brand.addWidget(self.menu_btn)
        lay.addLayout(brand)
        lay.addSpacing(18)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        lay.addWidget(label("CRÉATION", "SidebarSection"))
        for key, text, ic in NAV:
            lay.addWidget(self._nav(key, text, ic))
        lay.addSpacing(8)
        lay.addWidget(label("OUTILS", "SidebarSection"))
        for key, text, ic in TOOLS:
            lay.addWidget(self._nav(key, text, ic))
        lay.addStretch(1)

        self.update_btn = QPushButton("  Mise à jour disponible")
        self.update_btn.setObjectName("Primary")
        self.update_btn.setIcon(icons.icon("download", "#FFFFFF", 16))
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.hide()
        lay.addWidget(self.update_btn)
        lay.addSpacing(8)

        chip = QFrame()
        chip.setObjectName("ProjectChip")
        cl = QVBoxLayout(chip)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(4)
        self.proj_title = label("Aucun projet", wrap=True)
        self.proj_title.setStyleSheet("font-weight: 700;")
        self.proj_info = label("", "Hint", wrap=True)
        cl.addWidget(label("PROJET EN COURS", "SidebarSection"))
        cl.addWidget(self.proj_title)
        cl.addWidget(self.proj_info)
        row = QHBoxLayout()
        self.save_btn = QPushButton(" Enregistrer")
        self.save_btn.setIcon(icons.icon("save", theme.CURRENT.text, 16))
        self.save_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.save_btn, 1)
        cl.addLayout(row)
        lay.addWidget(chip)

    def _nav(self, key: str, text: str, ic: str) -> QPushButton:
        b = QPushButton("  " + text)
        b.setObjectName("NavButton")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(icons.icon(ic, theme.CURRENT.muted, 19))
        b.setIconSize(QSize(19, 19))
        b.toggled.connect(lambda on, b=b, ic=ic: b.setIcon(
            icons.icon(ic, theme.CURRENT.accent if on else theme.CURRENT.muted, 19)))
        b.clicked.connect(lambda _=False, k=key: self.window_.show_page(k))
        self.group.addButton(b)
        self.buttons[key] = b
        return b


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(1180, 760)
        self.ctx = AppContext(self)

        root = QWidget()
        root.setObjectName("Root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = Sidebar(self)
        h.addWidget(self.sidebar)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        self.player_bar = PlayerBar(self.ctx.player)
        right.addWidget(self.player_bar)
        h.addLayout(right, 1)
        self.setCentralWidget(root)

        from .pages.engines import EnginesPage
        from .pages.export import ExportPage
        from .pages.home import HomePage
        from .pages.manuscript import ManuscriptPage
        from .pages.production import ProductionPage
        from .pages.settings import SettingsPage
        from .pages.voices import VoicesPage

        self.pages = {
            "home": HomePage(self.ctx, self),
            "manuscript": ManuscriptPage(self.ctx),
            "voices": VoicesPage(self.ctx),
            "production": ProductionPage(self.ctx),
            "export": ExportPage(self.ctx),
            "engines": EnginesPage(self.ctx),
            "settings": SettingsPage(self.ctx, self),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)

        self.ctx.navigate_requested.connect(self.show_page)
        self.ctx.project_modified.connect(self._update_title)
        self.ctx.project_changed.connect(self._on_project_changed)
        self.sidebar.save_btn.clicked.connect(self.save_project)
        self._build_menu()
        self._build_shortcuts()

        self._autosave = QTimer(self)
        self._autosave.timeout.connect(self._autosave_tick)
        self._autosave.start(max(1, int(settings().get("autosave_minutes", 3) or 3)) * 60_000)

        geo = settings().get("window_geometry")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
            except Exception:
                pass
        else:
            self.resize(1440, 900)
        self.show_page("home")
        self._on_project_changed()
        apply_window_chrome(self)
        self._update_info: dict | None = None
        self.sidebar.update_btn.clicked.connect(self._open_update)
        if settings().get("check_updates", True):
            QTimer.singleShot(5000, lambda: self.check_updates(silent=True))

    # -- mises à jour ------------------------------------------------------------------
    def check_updates(self, silent: bool = False) -> None:
        from ..core import updates

        def done(rel):
            if rel:
                self._update_info = rel
                self.sidebar.update_btn.setText(f"  Version {rel['version']} disponible")
                self.sidebar.update_btn.show()
                self.ctx.toast(f"Une nouvelle version ({rel['version']}) d'AudioLivre Studio est disponible : "
                               "cliquez sur le bouton en bas à gauche pour la télécharger.", "info", 9000)
            elif not silent:
                self.ctx.toast("Vous avez la dernière version d'AudioLivre Studio.", "success")

        def fail(msg, _tb):
            if not silent:
                self.ctx.toast(f"Vérification impossible : {msg}", "warning")

        self._update_task = tasks.run(updates.check_for_update, on_done=done, on_error=fail)

    def _open_update(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from ..core import updates

        rel = self._update_info or {}
        QDesktopServices.openUrl(QUrl(rel.get("download") or rel.get("url") or updates.RELEASES_PAGE))

    # -- menus & raccourcis ------------------------------------------------------------
    def _build_menu(self) -> None:
        m = QMenu(self)
        actions = [
            ("Nouveau projet depuis un document…", "file-plus", "Ctrl+I", self.import_document_dialog),
            ("Nouveau projet vide", "plus", "Ctrl+N", self.new_empty_project),
            ("Ouvrir un projet…", "folder", "Ctrl+O", self.open_project_dialog),
            None,
            ("Enregistrer", "save", "Ctrl+S", self.save_project),
            ("Enregistrer sous…", "copy", "Ctrl+Shift+S", self.save_project_as),
            None,
            ("Ouvrir le dossier du projet", "external", None, self.open_project_folder),
            ("Journal de l'application", "list", None, self.open_logs),
            ("À propos d'AudioLivre Studio", "info", "F1", self.about),
            None,
            ("Quitter", "x", "Ctrl+Q", self.close),
        ]
        for a in actions:
            if a is None:
                m.addSeparator()
                continue
            text, ic, sc, fn = a
            act = QAction(icons.icon(ic, theme.CURRENT.text, 16), text, self)
            if sc:
                act.setShortcut(QKeySequence(sc))
                act.setShortcutContext(Qt.ApplicationShortcut)
                self.addAction(act)
            act.triggered.connect(fn)
            m.addAction(act)
        self.recent_menu = m.addMenu(icons.icon("clock", theme.CURRENT.text, 16), "Projets récents")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        self.sidebar.menu_btn.setMenu(m)
        self.sidebar.menu_btn.setPopupMode(self.sidebar.menu_btn.ToolButtonPopupMode.InstantPopup)

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        recents = settings().recent_projects()
        if not recents:
            a = self.recent_menu.addAction("Aucun projet récent")
            a.setEnabled(False)
        for r in recents:
            self.recent_menu.addAction(Path(r).stem, lambda r=r: self.open_project(r))

    def _build_shortcuts(self) -> None:
        play = QAction(self)
        play.setShortcut(QKeySequence("Ctrl+Space"))
        play.setShortcutContext(Qt.ApplicationShortcut)
        play.triggered.connect(self.ctx.player.toggle)
        self.addAction(play)
        for i, (key, _t, _i) in enumerate(NAV + TOOLS, 1):
            a = QAction(self)
            a.setShortcut(QKeySequence(f"Ctrl+{i}"))
            a.setShortcutContext(Qt.ApplicationShortcut)
            a.triggered.connect(lambda _=False, k=key: self.show_page(k))
            self.addAction(a)

    # -- navigation --------------------------------------------------------------------
    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        btn = self.sidebar.buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        try:
            page.on_show()
        except Exception:
            log.exception("Erreur à l'affichage de la page %s", key)

    def _on_project_changed(self) -> None:
        for p in self.pages.values():
            try:
                p.on_project_changed()
            except Exception:
                log.exception("Erreur de mise à jour de la page")
        self._update_title()

    def _update_title(self) -> None:
        pr = self.ctx.project
        has = bool(pr.chapters) or pr.path is not None
        star = "• " if self.ctx.dirty else ""
        self.setWindowTitle(f"{star}{pr.display_title} — {APP_NAME}" if has else APP_NAME)
        if has:
            self.sidebar.proj_title.setText(pr.display_title)
            mins = pr.estimated_minutes()
            self.sidebar.proj_info.setText(
                f"{len(pr.included_chapters())} chapitres · {pr.word_count():,} mots · ≈ {format_duration(mins * 60)}"
                .replace(",", " ")
                + (" · non enregistré" if self.ctx.dirty else "")
            )
        else:
            self.sidebar.proj_title.setText("Aucun projet")
            self.sidebar.proj_info.setText("Importez un document Word ou PDF pour commencer.")
        self.sidebar.save_btn.setEnabled(has)

    # -- projets -----------------------------------------------------------------------
    def confirm_discard(self) -> bool:
        if not self.ctx.dirty:
            return True
        r = QMessageBox.question(
            self, "Modifications non enregistrées",
            f"Le projet « {self.ctx.project.display_title} » a des modifications non enregistrées.\n"
            "Voulez-vous les enregistrer ?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self.save_project()
        return True

    def new_empty_project(self) -> None:
        if not self.confirm_discard():
            return
        pr = Project()
        pr.metadata.title = "Nouveau livre"
        pr.chapters = [Chapter(title="Chapitre 1", text="Écrivez ou collez votre texte ici.")]
        self.ctx.set_project(pr)
        self.ctx.dirty = True
        self.show_page("manuscript")

    def import_document_dialog(self) -> None:
        start = str(settings().get("last_import_dir") or Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un document à transformer en livre audio", start,
                                              importers.FILE_FILTER)
        if path:
            self.import_document(path)

    def import_document(self, path: str) -> None:
        if not self.confirm_discard():
            return
        settings().set("last_import_dir", str(Path(path).parent))
        self.ctx.toast(f"Import de « {Path(path).name} »…", "info", 2500)

        def work():
            return importers.import_document(path)

        def done(doc):
            self._create_project_from(doc, path)

        def fail(msg, _tb):
            QMessageBox.warning(self, "Import impossible", msg)

        self._import_task = tasks.run(work, on_done=done, on_error=fail)

    def _create_project_from(self, doc, source: str) -> None:
        from .dialogs.import_preview import ImportPreviewDialog

        dlg = ImportPreviewDialog(doc, Path(source).name, self)
        if not dlg.exec():
            return
        pr = Project(metadata=doc.metadata, source_file=source)
        for ch in doc.chapters:
            ch.text = clean_imported_text(ch.text)
        pr.chapters = doc.chapters
        base = settings().projects_dir()
        name = re.sub(r'[<>:"/\\|?*]', "", pr.metadata.title or Path(source).stem).strip()[:60] or "Livre"
        folder = base / name
        n = 2
        while folder.exists() and any(folder.glob("*.alsproj")):
            folder = base / f"{name} ({n})"
            n += 1
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{name}.alsproj"
        if doc.cover_bytes:
            cover = folder / f"couverture{doc.cover_ext}"
            cover.write_bytes(doc.cover_bytes)
            pr.metadata.cover_path = str(cover)
        try:
            project_io.save_project(pr, target)
            settings().add_recent(target)
        except Exception as exc:
            QMessageBox.warning(self, "Enregistrement impossible", str(exc))
        self.ctx.set_project(pr)
        words = pr.word_count()
        self.ctx.toast(f"Projet créé : {len(pr.chapters)} chapitres, {words:,} mots détectés.".replace(",", " "),
                       "success", 5000)
        self.show_page("manuscript")

    def open_project_dialog(self) -> None:
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", str(settings().projects_dir()),
                                              "Projets AudioLivre (*.alsproj)")
        if path:
            self.open_project(path, confirm=False)

    def open_project(self, path: str, confirm: bool = True) -> None:
        if confirm and not self.confirm_discard():
            return
        try:
            pr = project_io.load_project(path)
        except Exception as exc:
            QMessageBox.warning(self, "Ouverture impossible", str(exc))
            return
        self.ctx.set_project(pr)
        settings().add_recent(path)
        self.ctx.toast(f"Projet « {pr.display_title} » ouvert", "success", 2500)
        self.show_page("manuscript")

    def save_project(self) -> bool:
        pr = self.ctx.project
        if pr.path is None:
            return self.save_project_as()
        try:
            project_io.save_project(pr)
        except Exception as exc:
            QMessageBox.warning(self, "Enregistrement impossible", str(exc))
            return False
        self.ctx.dirty = False
        settings().add_recent(pr.path)
        self._update_title()
        self.ctx.toast("Projet enregistré", "success", 1800)
        return True

    def save_project_as(self) -> bool:
        pr = self.ctx.project
        default = settings().projects_dir() / f"{pr.display_title}.alsproj"
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le projet", str(default),
                                              "Projets AudioLivre (*.alsproj)")
        if not path:
            return False
        pr.path = Path(path)
        return self.save_project()

    def _autosave_tick(self) -> None:
        if self.ctx.dirty and self.ctx.project.path is not None and not self.ctx.rendering:
            try:
                project_io.save_project(self.ctx.project)
                self.ctx.dirty = False
                self._update_title()
            except Exception as exc:
                log.warning("Sauvegarde automatique impossible : %s", exc)

    def open_project_folder(self) -> None:
        pr = self.ctx.project
        if pr.path is not None:
            open_path(pr.path.parent)

    def open_logs(self) -> None:
        from .. import paths

        open_path(paths.logs_dir())

    def about(self) -> None:
        from .dialogs.about import AboutDialog

        AboutDialog(self).exec()

    # -- fermeture ---------------------------------------------------------------------
    def closeEvent(self, e):
        if self.ctx.rendering:
            r = QMessageBox.question(self, "Production en cours",
                                     "Une production est en cours. Voulez-vous vraiment quitter ?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            prod = self.pages.get("production")
            if prod is not None:
                prod.stop()
        if not self.confirm_discard():
            e.ignore()
            return
        settings().set("window_geometry", bytes(self.saveGeometry().toBase64()).decode())
        self.ctx.player.stop()
        shutdown_all()
        e.accept()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        from .widgets import Toast

        Toast._reposition()


def open_path(path: Path) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def version_string() -> str:
    return f"{APP_NAME} {__version__}"
