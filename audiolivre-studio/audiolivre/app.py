"""Point d'entrée de l'application graphique."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from pathlib import Path

from . import APP_ID, APP_NAME, ORG_NAME, __version__
from .logging_setup import setup_logging

log = logging.getLogger("audiolivre")


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="AudioLivreStudio", add_help=True)
    p.add_argument("file", nargs="?", help="Projet (.alsproj) ou document à ouvrir")
    p.add_argument("--selftest", metavar="RAPPORT", help="Exécute l'autotest et écrit un rapport JSON")
    p.add_argument("--version", action="store_true")
    return p.parse_args(argv)


def _install_excepthook(app) -> None:
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Erreur non gérée :\n%s", text)
        try:
            from PySide6.QtWidgets import QMessageBox

            box = QMessageBox()
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Erreur inattendue")
            box.setText("Une erreur inattendue s'est produite. Votre travail est en principe préservé ; "
                        "enregistrez votre projet par précaution.")
            box.setDetailedText(text)
            box.exec()
        except Exception:
            pass

    sys.excepthook = hook


def _load_translations(app) -> None:
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    tr = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    if tr.load(QLocale("fr_FR"), "qtbase", "_", path):
        app.installTranslator(tr)
        app._qt_tr = tr  # garde une référence


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    if args.version:
        print(f"{APP_NAME} {__version__}")
        return 0
    setup_logging()
    log.info("Démarrage de %s %s (Python %s)", APP_NAME, __version__, sys.version.split()[0])

    if args.selftest:
        from .selftest import run_selftest

        return run_selftest(Path(args.selftest))

    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{ORG_NAME}.{APP_ID}")
        except Exception:
            pass
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    QLocale.setDefault(QLocale(QLocale.French, QLocale.France))
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    _load_translations(app)

    from .config import settings
    from .ui import icons, theme

    theme.apply(app, settings().get("theme", "dark"), settings().get("accent", "#7C5CFF"))
    app.setWindowIcon(icons.app_icon())
    _install_excepthook(app)

    from .ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    if args.file:
        f = Path(args.file)
        if f.suffix.lower() == ".alsproj":
            win.open_project(str(f), confirm=False)
        elif f.exists():
            win.import_document(str(f))
    if settings().get("first_run", True):
        settings().set("first_run", False)
        win.ctx.toast("Bienvenue ! Glissez un document Word ou PDF sur l'accueil pour créer votre premier livre "
                      "audio.", "info", 9000)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
