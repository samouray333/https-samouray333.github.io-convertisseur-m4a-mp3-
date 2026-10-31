"""Fenêtre principale : barre latérale, pages, lecteur, gestion des projets."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, PROJECT_EXT, __version__
from ..config import settings
from ..core import project as project_io
from ..core.engines import shutdown_all
from ..core.textproc import format_duration
from . import icons, tasks, theme
from .context import AppContext
from .player import PlayerBar
from .widgets import IconButton, label

log = logging.getLogger(__name__)

NAV = [
    ("home", "Accueil", "home"),
    ("dubbing", "Doublage", "film"),
    ("review", "Contrôle", "shield"),
    ("people", "Personnes", "users"),
    ("export", "Export", "package"),
    ("queue", "File d'attente", "list"),
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
        self.setFixedWidth(236)
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
        col.addWidget(label("Doublys", "BrandTitle"))
        col.addWidget(label("par Echo Matras", "BrandSub"))
        brand.addLayout(col, 1)
        self.menu_btn = IconButton("more", "Menu fichier", 32, 18)
        brand.addWidget(self.menu_btn)
        lay.addLayout(brand)
        lay.addSpacing(18)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        lay.addWidget(label("DOUBLAGE", "SidebarSection"))
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
        self.save_btn = QPushButton(" Enregistrer")
        self.save_btn.setIcon(icons.icon("save", theme.CURRENT.text, 16))
        self.save_btn.setCursor(Qt.PointingHandCursor)
        cl.addWidget(self.save_btn)
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
        self.setMinimumSize(1180, 740)
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

        from .pages.dubbing import DubbingPage
        from .pages.engines import EnginesPage
        from .pages.export import ExportPage
        from .pages.home import HomePage
        from .pages.people import PeoplePage
        from .pages.queuepage import QueuePage
        from .pages.review import ReviewPage
        from .pages.settings import SettingsPage

        self.pages = {
            "home": HomePage(self.ctx, self),
            "dubbing": DubbingPage(self.ctx, self),
            "review": ReviewPage(self.ctx, self),
            "people": PeoplePage(self.ctx),
            "export": ExportPage(self.ctx),
            "queue": QueuePage(self.ctx, self),
            "engines": EnginesPage(self.ctx),
            "settings": SettingsPage(self.ctx, self),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)

        self.ctx.navigate_requested.connect(self.show_page)
        self.ctx.project_modified.connect(self._update_title)
        self.ctx.project_changed.connect(self._on_project_changed)
        self.ctx.lines_changed.connect(self._update_title)
        self.ctx.runner.finished.connect(lambda *_: self._update_title())
        self.sidebar.save_btn.clicked.connect(self.save_project)
        self._build_menu()
        self._build_shortcuts()
        self.setAcceptDrops(True)

        self._autosave = QTimer(self)
        self._autosave.timeout.connect(self._autosave_tick)
        self._autosave.start(max(1, int(settings().get("autosave_minutes", 2) or 2)) * 60_000)

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
        QTimer.singleShot(1500, self._offer_queue_resume)

    def _offer_queue_resume(self) -> None:
        from ..core import jobqueue

        n = jobqueue.pending_count()
        if not n or not self.isVisible() or self.ctx.runner.running or self.pages["queue"].active:
            return
        r = QMessageBox.question(self, "File d'attente",
                                 f"{n} vidéo(s) de la file d'attente ne sont pas terminées. Reprendre maintenant ? "
                                 "(le travail déjà fait est conservé)")
        if r == QMessageBox.Yes:
            self.show_page("queue")
            self.pages["queue"].start()

    # -- mises à jour ------------------------------------------------------------------
    def check_updates(self, silent: bool = False) -> None:
        from ..core import updates

        def done(rel):
            if rel:
                self._update_info = rel
                self.sidebar.update_btn.setText(f"  Version {rel['version']} disponible")
                self.sidebar.update_btn.show()
                self.ctx.toast(f"Une nouvelle version de Doublys ({rel['version']}) est disponible : cliquez sur "
                               "le bouton en bas à gauche pour la télécharger.", "info", 9000)
            elif not silent:
                self.ctx.toast("Vous avez la dernière version de Doublys.", "success")

        def fail(msg, _tb):
            if not silent:
                self.ctx.toast(f"Vérification impossible : {msg}", "warning")

        self._update_task = tasks.run(updates.check_for_update, on_done=done, on_error=fail)

    def _open_update(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from ..core import updates

        rel = self._update_info or {}
        url = rel.get("download")
        if not url or self.ctx.runner.running:
            QDesktopServices.openUrl(QUrl(rel.get("url") or updates.RELEASES_PAGE))
            return
        r = QMessageBox.question(self, "Mise à jour",
                                 f"Télécharger et installer Doublys {rel.get('version')} maintenant ?\n\nDoublys se "
                                 "fermera pendant l'installation ; vos projets et vos moteurs sont conservés.")
        if r != QMessageBox.Yes:
            return
        self.sidebar.update_btn.setEnabled(False)
        self.sidebar.update_btn.setText("  Téléchargement…")

        def work(task):
            from .. import paths
            from ..core.engines.installer import download

            target = paths.temp_dir() / Path(url).name
            download(url, target, task.say, task.cancel_event)
            task.say("Vérification de l'installateur…")
            updates.verify_installer(target, rel)
            return target

        def done(path):
            from ..core import support

            if not self.confirm_discard():
                # l'enregistrement a échoué et l'utilisateur garde ses modifications : on n'installe pas
                self.sidebar.update_btn.setEnabled(True)
                self.sidebar.update_btn.setText(f"  Version {rel.get('version')} disponible")
                return
            support.launch_installer(path)
            self.close()

        def fail(msg, _tb):
            self.sidebar.update_btn.setEnabled(True)
            self.sidebar.update_btn.setText(f"  Version {rel.get('version')} disponible")
            QMessageBox.warning(self, "Mise à jour impossible", f"{msg}\n\nVous pouvez la télécharger depuis "
                                f"{updates.RELEASES_PAGE}")

        self._dl_task = tasks.Task(work, pass_reporter=True, on_done=done, on_error=fail,
                                   on_message=lambda m: self.sidebar.update_btn.setText("  " + m[-40:])).start()

    # -- menus & raccourcis ------------------------------------------------------------
    def _build_menu(self) -> None:
        m = QMenu(self)
        actions = [
            ("Doubler une vidéo…", "film", "Ctrl+I", self.choose_video),
            ("Ouvrir un projet…", "folder", "Ctrl+O", self.open_project_dialog),
            None,
            ("Enregistrer", "save", "Ctrl+S", self.save_project),
            None,
            ("Ouvrir le dossier du projet", "external", None, self.open_project_folder),
            ("Journal de l'application", "list", None, self.open_logs),
            ("Guide de démarrage", "sparkles", "F1", self.guide),
            ("Créer un rapport de bug…", "alert", None, self.bug_report),
            ("À propos de Doublys", "info", None, self.about),
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
        for keys, fn in (("Ctrl+Z", self.ctx.undo), ("Ctrl+Y", self.ctx.redo), ("Ctrl+Shift+Z", self.ctx.redo)):
            a = QAction(self)
            a.setShortcut(QKeySequence(keys))
            a.setShortcutContext(Qt.WindowShortcut)  # les zones de texte gardent leur propre Ctrl+Z
            a.triggered.connect(fn)
            self.addAction(a)
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

    # -- glisser-déposer sur toute la fenêtre ----------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.open_files(files)

    def open_files(self, files: list[str]) -> None:
        """Une vidéo : nouveau projet ; plusieurs : file d'attente."""
        if len(files) > 1:
            self.show_page("queue")
            self.pages["queue"].add_videos(files)
        else:
            self.open_any(files[0])

    def open_any(self, path: str) -> None:
        if Path(path).suffix.lower() == PROJECT_EXT:
            self.open_project(path)
        elif Path(path).suffix.lower() in (".srt", ".ass", ".ssa", ".vtt"):
            self.use_subtitle_file(path)
        else:
            self.new_project_from_video(path)

    def use_subtitle_file(self, path: str) -> None:
        """Fichier de sous-titres glissé sur l'appli : il donne le texte des répliques du projet ouvert."""
        pr = self.ctx.project
        if pr is None:
            self.ctx.toast("Ouvrez d'abord la vidéo, puis glissez son fichier de sous-titres.", "info", 5000)
            return
        if self.ctx.runner.running:
            self.ctx.toast("Attendez la fin du traitement en cours.", "warning")
            return
        from ..core import subsources

        self.ctx.checkpoint("sous-titres")
        pr.subs.kind, pr.subs.path = "file", str(Path(path))
        pr.subs.language = subsources.lang_from_name(path)
        pr.invalidate_from("subtitles")
        self.ctx.mark_dirty()
        self.ctx.project_changed.emit()
        self.show_page("dubbing")
        self.ctx.toast(f"Sous-titres « {Path(path).name} » choisis : relancez la création de la VF.", "success", 5000)

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
        if pr is None:
            self.setWindowTitle(APP_NAME)
            self.sidebar.proj_title.setText("Aucun projet")
            self.sidebar.proj_info.setText("Glissez une vidéo sur l'accueil pour commencer.")
            self.sidebar.save_btn.setEnabled(False)
            return
        star = "• " if self.ctx.dirty else ""
        self.setWindowTitle(f"{star}{pr.display_title} — {APP_NAME}")
        self.sidebar.proj_title.setText(pr.display_title)
        info = f"{format_duration(pr.video.duration)} · {len(pr.lines)} répliques · {len(pr.people)} personne(s)"
        self.sidebar.proj_info.setText(info + (" · non enregistré" if self.ctx.dirty else ""))
        self.sidebar.save_btn.setEnabled(True)

    # -- projets -----------------------------------------------------------------------
    def busy(self) -> bool:
        if self.ctx.runner.running:
            QMessageBox.information(self, "Traitement en cours",
                                    "Un traitement est en cours : arrêtez-le (page Doublage) avant de changer de "
                                    "projet.")
            return True
        return False

    def confirm_discard(self) -> bool:
        if not self.ctx.dirty or self.ctx.project is None:
            return True
        try:
            self.ctx.save()  # les projets sont toujours enregistrés dans leur dossier
            return True
        except Exception as exc:
            r = QMessageBox.question(self, "Enregistrement impossible",
                                     f"{exc}\n\nAbandonner les modifications ?")
            return r == QMessageBox.Yes

    def choose_video(self) -> None:
        start = str(settings().get("last_video_dir") or Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une vidéo à doubler", start,
                                              project_io.VIDEO_FILTER)
        if path:
            self.new_project_from_video(path)

    def new_project_from_video(self, path: str, auto: bool = False) -> None:
        if self.busy() or not self.confirm_discard():
            return
        settings().set("last_video_dir", str(Path(path).parent))
        try:
            pr = project_io.create_project(path, settings().projects_dir())
        except Exception as exc:
            QMessageBox.warning(self, "Vidéo inutilisable", str(exc))
            return
        settings().add_recent(pr.path)
        self.ctx.set_project(pr)
        self.ctx.toast(f"Projet créé : {pr.path.parent}", "success", 4000)
        self.show_page("dubbing")
        if auto:
            self.pages["dubbing"].run_auto()

    def open_project_dialog(self) -> None:
        if self.busy() or not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", str(settings().projects_dir()),
                                              project_io.PROJECT_FILTER)
        if path:
            self.open_project(path, confirm=False)

    def open_project(self, path: str, confirm: bool = True) -> None:
        if self.busy() or (confirm and not self.confirm_discard()):
            return
        try:
            pr = project_io.load_project(path)
        except Exception as exc:
            QMessageBox.warning(self, "Ouverture impossible", str(exc))
            settings().remove_recent(path)
            return
        self.ctx.set_project(pr)
        settings().add_recent(path)
        if not Path(pr.source_video).is_file():
            self._relocate_video(pr)
        self.ctx.toast(f"Projet « {pr.display_title} » ouvert", "success", 2500)
        self.show_page("dubbing")

    def _relocate_video(self, pr) -> None:
        r = QMessageBox.question(self, "Vidéo introuvable",
                                 f"La vidéo de ce projet a été déplacée ou supprimée :\n{pr.source_video}\n\n"
                                 "Voulez-vous indiquer son nouvel emplacement ?")
        if r != QMessageBox.Yes:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Nouvel emplacement de la vidéo",
                                              str(Path(pr.source_video).parent), project_io.VIDEO_FILTER)
        if path:
            pr.source_video = str(Path(path).resolve())
            self.ctx.mark_dirty()
            self.ctx.save()

    def save_project(self) -> bool:
        if self.ctx.project is None:
            return False
        try:
            self.ctx.save()
        except Exception as exc:
            QMessageBox.warning(self, "Enregistrement impossible", str(exc))
            return False
        settings().add_recent(self.ctx.project.path)
        self._update_title()
        self.ctx.toast("Projet enregistré", "success", 1800)
        return True

    def _autosave_tick(self) -> None:
        if self.ctx.dirty and self.ctx.project is not None and not self.ctx.runner.running:
            try:
                self.ctx.save()
                self._update_title()
            except Exception as exc:
                log.warning("Sauvegarde automatique impossible : %s", exc)

    def open_project_folder(self) -> None:
        pr = self.ctx.project
        if pr is not None and pr.path is not None:
            open_path(pr.path.parent)

    def open_logs(self) -> None:
        from .. import paths

        open_path(paths.logs_dir())

    def guide(self) -> None:
        from .dialogs.guide import GuideDialog

        GuideDialog(self).exec()

    def bug_report(self) -> None:
        from ..core import support

        pr = self.ctx.project
        try:
            out = support.bug_report(pr.path if pr is not None else None)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Rapport impossible", str(exc))
            return
        QMessageBox.information(self, "Rapport de bug", "Le rapport a été créé :\n"
                                f"{out}\n\nEnvoyez ce fichier avec une description du problème. Il contient le "
                                "journal, les réglages (sans votre clé DeepSeek) et le projet ouvert (texte des "
                                "répliques), mais aucune vidéo ni aucun son.")
        open_path(out.parent)

    def about(self) -> None:
        from .dialogs.about import AboutDialog

        AboutDialog(self).exec()

    # -- fermeture ---------------------------------------------------------------------
    def closeEvent(self, e):
        if self.ctx.runner.running:
            r = QMessageBox.question(self, "Traitement en cours",
                                     "Un doublage est en cours. Voulez-vous vraiment quitter ? Le travail déjà fait "
                                     "est conservé : il reprendra où il s'est arrêté.")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.ctx.runner.stop()
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
