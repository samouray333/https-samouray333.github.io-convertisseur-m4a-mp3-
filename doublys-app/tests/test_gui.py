import pytest

from tests.conftest import needs_ffmpeg

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from doublys.ui import theme

    theme.apply(app, "dark")
    return app


def test_main_window_empty(app):
    from doublys.ui.main_window import MainWindow

    win = MainWindow()
    for key in win.pages:
        win.show_page(key)
        app.processEvents()
    assert win.windowTitle() == "Doublys"
    win.close()


@needs_ffmpeg
def test_dubbing_page_with_project(app, tmp_path, test_video, fakes):
    from doublys.core import pipeline
    from doublys.core import project as project_io
    from doublys.ui.main_window import MainWindow

    pr = project_io.create_project(test_video, tmp_path / "p", "Essai")
    pr.settings.voice_mode = "edge"
    pipeline.run_all(pr, pipeline.Job())
    win = MainWindow()
    win.ctx.set_project(pr)
    page = win.pages["dubbing"]
    win.show_page("dubbing")
    app.processEvents()
    assert page.table.rowCount() == len(pr.lines)
    # modification du français : la voix et le mixage sont à refaire
    page.table.item(0, 5).setText("Bonjour à tous.")
    assert pr.lines[0].fr == "Bonjour à tous." and pr.lines[0].fr_edited
    assert not pr.step_done("dub") and not pr.step_done("mix")
    # couper puis fusionner
    page.table.selectRow(0)
    n = len(pr.lines)
    page._act_merge(page.selected_lines(), pr.lines[0])
    assert len(pr.lines) == n - 1
    win.show_page("people")
    app.processEvents()
    assert len(win.pages["people"].cards) == 2
    win.show_page("export")
    win.show_page("settings")
    app.processEvents()
    win.ctx.dirty = False
    win.close()


def test_theme_light(app):
    from doublys.ui import theme

    p = theme.apply(app, "light", "#10B981")
    assert not p.dark
    theme.apply(app, "dark")
