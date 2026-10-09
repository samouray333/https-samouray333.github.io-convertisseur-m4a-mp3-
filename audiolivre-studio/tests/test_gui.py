import pytest

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from audiolivre.ui import theme

    theme.apply(app, "dark")
    return app


def test_main_window_pages(app, tmp_path):
    from audiolivre.core.models import Chapter, Project
    from audiolivre.ui.main_window import MainWindow

    win = MainWindow()
    pr = Project(chapters=[Chapter(title="Chapitre 1", text="Bonjour.\n\n@Paul: Salut !")])
    pr.metadata.title = "Test"
    win.ctx.set_project(pr)
    for key in win.pages:
        win.show_page(key)
        app.processEvents()
    assert win.windowTitle().endswith("AudioLivre Studio")
    win.ctx.dirty = False
    win.close()


def test_clone_wizard_steps(app):
    import numpy as np

    from audiolivre.ui.dialogs.clone_wizard import CloneWizard
    from audiolivre.ui.main_window import MainWindow

    win = MainWindow()
    dlg = CloneWizard(win.ctx, win)
    sr = 44100
    t = np.arange(sr * 12) / sr
    dlg.data = (0.3 * np.sin(2 * np.pi * 200 * t)).astype("float32")
    dlg.sr = sr
    from pathlib import Path

    dlg.source_file = Path("enregistrement.wav")
    dlg._go(1)
    assert dlg.wave.selection() is not None
    dlg._go(2)
    dlg.consent.setChecked(True)
    dlg.name.setText("Voix test")
    dlg._next()  # crée la voix
    assert dlg.voice is not None and dlg.voice.reference_paths()[0].exists()
    dlg.reject()  # annuler supprime la voix créée
    assert win.ctx.library.get(dlg.voice.id if dlg.voice else "") is None
    win.ctx.dirty = False
    win.close()


def test_theme_light(app):
    from audiolivre.ui import theme

    p = theme.apply(app, "light", "#10B981")
    assert not p.dark
    theme.apply(app, "dark")
