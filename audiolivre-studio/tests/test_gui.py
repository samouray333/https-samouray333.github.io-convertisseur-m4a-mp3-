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


def test_import_preview_dialog(app):
    from PySide6.QtCore import Qt

    from audiolivre.core.importers import ImportedDocument
    from audiolivre.core.models import BookMetadata, Chapter
    from audiolivre.ui.dialogs.import_preview import ImportPreviewDialog

    chapters = [Chapter("Sommaire", "1. A\n\n2. B"), Chapter("Chapitre 1", "Texte.\n\n# Partie\n\nSuite."),
                Chapter("Chapitre 2", "Fin.")]
    doc = ImportedDocument(chapters=chapters, metadata=BookMetadata(title="Livre"))
    dlg = ImportPreviewDialog(doc, "livre.docx")
    dlg.list.item(0).setCheckState(Qt.Unchecked)
    assert not dlg.chapters[0].include
    dlg.mode.setCurrentIndex(dlg.mode.findData("deep"))
    assert [c.title for c in dlg.chapters][-3:] == ["Chapitre 1", "Partie", "Chapitre 2"]
    dlg.mode.setCurrentIndex(dlg.mode.findData("auto"))
    dlg.list.setCurrentRow(2)
    dlg._merge_prev()
    dlg._accept()
    assert len(doc.chapters) == 2


def test_ai_assistant_dialog_applies_suggestions(app):
    from PySide6.QtCore import Qt

    from audiolivre.core import ai
    from audiolivre.core.models import Chapter, Project
    from audiolivre.ui.dialogs.ai_annotate import AIAnnotateDialog
    from audiolivre.ui.main_window import MainWindow

    win = MainWindow()
    ch = Chapter(title="Chapitre 1", text="Marie entra.\n\n— Bonjour ! dit-elle.\n\n— Salut, répondit Paul.")
    win.ctx.set_project(Project(chapters=[ch]))
    dlg = AIAnnotateDialog(win.ctx, ch, win)
    dlg.show_result(ai.Annotation(
        paragraphs=[ai.ParagraphSuggestion(2, "— Bonjour ! dit-elle.", "Marie", "joyeux"),
                    ai.ParagraphSuggestion(3, "— Salut, répondit Paul.", "Paul", "")],
        names=[ai.NameSuggestion("Marie", "Mari")], characters={"Marie": "F", "Paul": "M"}))
    assert dlg.apply_btn.isEnabled()
    dlg.table.item(1, 2).setText("Paulo")  # correction manuelle du nom
    dlg.names.item(0, 0).setCheckState(Qt.Unchecked)
    dlg._apply()
    assert ch.text == "Marie entra.\n\n@Marie: [joyeux] — Bonjour ! dit-elle.\n\n@Paulo: — Salut, répondit Paul."
    pr = win.ctx.project
    assert set(pr.cast) == {"Marie", "Paulo"} and all(pr.cast.values())
    assert win.ctx.library.get(pr.cast["Marie"]).engine == "edge"
    assert pr.lexicon == []
    for vid in pr.cast.values():
        win.ctx.library.delete(vid)
    win.ctx.dirty = False
    win.close()
