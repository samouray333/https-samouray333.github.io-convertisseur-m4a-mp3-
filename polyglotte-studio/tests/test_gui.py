import pytest

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from polyglottestudio.ui import theme

    theme.apply(app, "dark")
    return app


def test_main_window_pages(app, tmp_path):
    from polyglottestudio.core.models import Chapter, Project
    from polyglottestudio.ui.main_window import MainWindow

    win = MainWindow()
    pr = Project(chapters=[Chapter(title="Chapitre 1", text="Bonjour.\n\n@Paul: Salut !")])
    pr.metadata.title = "Test"
    win.ctx.set_project(pr)
    for key in win.pages:
        win.show_page(key)
        app.processEvents()
    assert win.windowTitle().endswith("Polyglotte Studio")
    win.ctx.dirty = False
    win.close()


def test_clone_wizard_steps(app):
    import numpy as np

    from polyglottestudio.ui.dialogs.clone_wizard import CloneWizard
    from polyglottestudio.ui.main_window import MainWindow

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
    from polyglottestudio.ui import theme

    p = theme.apply(app, "light", "#10B981")
    assert not p.dark
    theme.apply(app, "dark")


def test_import_preview_dialog(app):
    from PySide6.QtCore import Qt

    from polyglottestudio.core.importers import ImportedDocument
    from polyglottestudio.core.models import BookMetadata, Chapter
    from polyglottestudio.ui.dialogs.import_preview import ImportPreviewDialog

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

    from polyglottestudio.core import ai
    from polyglottestudio.core.models import Chapter, Project
    from polyglottestudio.ui.dialogs.ai_annotate import AIAnnotateDialog
    from polyglottestudio.ui.main_window import MainWindow

    win = MainWindow()
    ch = Chapter(title="Chapitre 1", text="Marie entra.\n\n— Bonjour ! dit-elle.\n\n— Salut, répondit Paul.")
    win.ctx.set_project(Project(chapters=[ch]))
    dlg = AIAnnotateDialog(win.ctx, ch, win)
    dlg.show_result(ai.Annotation(
        paragraphs=[ai.ParagraphSuggestion(1, "Marie entra.", None, "", pause_ms=1000),
                    ai.ParagraphSuggestion(2, "— Bonjour ! dit-elle.", "Marie", "joyeux"),
                    ai.ParagraphSuggestion(3, "— Salut, répondit Paul.", "Paul", "")],
        names=[ai.NameSuggestion("Marie", "Mari")], characters={"Marie": "F", "Paul": "M"}))
    assert dlg.apply_btn.isEnabled()
    dlg.table.item(2, 2).setText("Paulo")  # correction manuelle du nom
    pc = dlg.table.cellWidget(0, 6)
    pc.setCurrentIndex(pc.findData(2000))  # pause allongée à la main
    dlg.names.item(0, 0).setCheckState(Qt.Unchecked)
    dlg._apply()
    assert ch.text == "Marie entra. [pause 2s]\n\n@Marie: [joyeux] — Bonjour ! dit-elle.\n\n@Paulo: — Salut, répondit Paul."
    pr = win.ctx.project
    assert set(pr.cast) == {"Marie", "Paulo"} and all(pr.cast.values())
    assert win.ctx.library.get(pr.cast["Marie"]).engine == "edge"
    assert pr.lexicon == []
    for vid in pr.cast.values():
        win.ctx.library.delete(vid)
    win.ctx.dirty = False
    win.close()


def test_credits_dialog(app):
    from polyglottestudio.core.models import Chapter, Project
    from polyglottestudio.ui.dialogs.credits import CreditsDialog
    from polyglottestudio.ui.main_window import MainWindow

    win = MainWindow()
    pr = Project(chapters=[Chapter(title="Chapitre 1", text="Bonjour.")])
    pr.metadata.title = "Le Phare"
    win.ctx.set_project(pr)
    dlg = CreditsDialog(win.ctx, win)
    dlg._template("opening")
    dlg.editors["closing"].setPlainText("Fin.\n\nMerci à ma famille.")
    from PySide6.QtGui import QTextCursor

    dlg.editors["closing"].moveCursor(QTextCursor.End)
    dlg._focused = dlg.editors["closing"]
    dlg._insert("{title}")
    assert "mots" in dlg.counts.text()
    assert dlg._chapter("opening").text.startswith("Le Phare.")
    dlg._save()
    assert pr.export.closing_credits == "Fin.\n\nMerci à ma famille.{title}"
    assert "{author}" in pr.export.opening_credits
    win.show_page("export")
    app.processEvents()
    win.ctx.dirty = False
    win.close()


def test_rvc_import_from_zip(app, tmp_path):
    import io
    import zipfile

    from polyglottestudio.ui.dialogs.rvc_import import RVCImportDialog, clean_name, find_files
    from polyglottestudio.ui.main_window import MainWindow

    pth = io.BytesIO()
    with zipfile.ZipFile(pth, "w") as inner:  # un .pth PyTorch est une archive zip
        inner.writestr("archive/data.pkl", b"x")
    archive = tmp_path / "Narrateur_v2_Ov2_450e.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Narrateur/G_2333.pth", b"PK checkpoint")
        zf.writestr("Narrateur/Narrateur.pth", pth.getvalue())
        zf.writestr("Narrateur/trained_IVF775_Flat_nprobe_1_Narrateur_v2.index", b"t")
        zf.writestr("Narrateur/added_IVF775_Flat_nprobe_1_Narrateur_v2.index", b"index")
    assert find_files(archive) == ("Narrateur/Narrateur.pth",
                                   "Narrateur/added_IVF775_Flat_nprobe_1_Narrateur_v2.index")
    assert clean_name("JamyModel_v2") == "JamyModel"

    win = MainWindow()
    dlg = RVCImportDialog(win.ctx, win)
    dlg.set_source(archive)
    assert dlg.name.text() == "Narrateur" and not dlg.ok.isEnabled()
    dlg.consent.setChecked(True)
    assert dlg.ok.isEnabled()
    dlg._import()
    v = dlg.voice
    assert v is not None and v.engine == "rvc" and v.consent and v.is_clone
    assert [p.name for p in v.reference_paths()] == ["modele.pth", "modele.index"]
    assert (v.reference_paths()[1]).read_bytes() == b"index"
    editor = win.pages["voices"].editor
    editor.set_voice(v)  # éditeur : modèle affiché, moteur verrouillé sur RVC
    assert editor.engine.currentData() == "rvc" and not editor.engine.isEnabled()
    assert editor.refs.count() == 2 and not editor.ref_add.isEnabled()
    win.ctx.library.delete(v.id)
    win.ctx.dirty = False
    win.close()


def test_recent_projects_forget_and_delete(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from polyglottestudio.config import settings
    from polyglottestudio.core import project_io
    from polyglottestudio.core.models import Chapter, Project
    from polyglottestudio.ui.main_window import MainWindow

    paths = []
    for name in ("Livre A", "Livre B"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "couverture.jpg").write_bytes(b"x")
        pr = Project(chapters=[Chapter(title="Ch", text="Bonjour.")])
        target = project_io.save_project(pr, folder / f"{name}.plgproj")
        project_io.save_project(pr, target)  # crée aussi le .bak
        project_io.cache_dir(pr)
        settings().add_recent(target)
        paths.append(target)
    keep = tmp_path / "Livre B" / "Export"
    keep.mkdir()
    (keep / "livre.m4b").write_bytes(b"audio")

    win = MainWindow()
    home = win.pages["home"]
    home.on_show()
    cards = [home.recent_grid.itemAt(i).widget() for i in range(home.recent_grid.count())]
    assert len(cards) == 2 and cards[0].menu.actions()

    home.forget_recent(str(paths[0]))
    assert str(paths[0]) not in settings().recent_projects() and paths[0].exists()

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)
    assert home.delete_project(str(paths[1]))
    assert not paths[1].exists() and not (tmp_path / "Livre B" / "Livre B_fichiers").exists()
    assert (keep / "livre.m4b").exists()  # les exports sont conservés
    assert str(paths[1]) not in settings().recent_projects()

    # un dossier qui ne contient plus que la couverture est retiré
    project_io.delete_project_files(paths[0])
    assert not (tmp_path / "Livre A").exists()

    settings().add_recent(paths[0])
    win._clear_recent()
    assert settings().get("recent_projects") == []
    win.ctx.dirty = False
    win.close()


def test_rate_emphasis_tools_and_correction(app, tmp_path):
    from PySide6.QtGui import QTextCursor

    from polyglottestudio.core import engines, project_io, renderer
    from polyglottestudio.core.models import Chapter, Project, VoiceProfile
    from polyglottestudio.selftest import make_tone_engine
    from polyglottestudio.ui.main_window import MainWindow

    engines.register_engine(make_tone_engine())
    win = MainWindow()
    voice = win.ctx.library.save(VoiceProfile(name="Test tonalité", engine="tone"))
    ch = Chapter(title="Chapitre 1", text="@Paul: [triste] Il ne reviendrait jamais.\n\nLe soir tombait.")
    pr = Project(chapters=[ch], narrator_voice_id=voice.id)
    pr.export.include_credits = False
    pr.production.announce_chapter_titles = False
    project_io.save_project(pr, tmp_path / "Livre.plgproj")
    win.ctx.set_project(pr)

    # Manuscrit : débit et mise en valeur
    win.show_page("manuscript")
    page = win.pages["manuscript"]
    ed = page.editor
    ed.moveCursor(QTextCursor.Start)
    page._tag_rate("lent")
    page._tag_rate("très rapide")
    assert ed.toPlainText().startswith("@Paul: [triste] [très rapide] Il ne")
    page._tag_rate("")
    cur = ed.textCursor()
    pos = ed.toPlainText().index("jamais")
    cur.setPosition(pos + 2)
    ed.setTextCursor(cur)
    page.emphasize_selection()
    assert "*jamais*" in ed.toPlainText() and "[très rapide]" not in ed.toPlainText()
    page.emphasize_selection()  # deuxième clic : retire
    assert "*jamais*" not in ed.toPlainText()

    # Production : respirations et correction d'un seul passage
    page._save_timer.stop()  # sinon l'enregistrement différé de l'éditeur réécrirait ch.text pendant le rendu
    ch.text = "Le soir tombait sur Siobhan.\n\nTout était calme."
    win.show_page("production")
    prod = win.pages["production"]
    prod.breaths.setCurrentIndex(prod.breaths.findData("natural"))
    assert pr.production.breaths == "natural"
    plan = renderer.build_plan(pr, win.ctx.library)
    renderer.Renderer(pr, win.ctx.library).render(plan)
    prod.plan = plan
    prod.table.setRowCount(1)
    from PySide6.QtWidgets import QTableWidgetItem

    item = QTableWidgetItem(plan[0].title)
    item.setData(256, plan[0].id)
    prod.table.setItem(0, 0, item)
    prod._selected_ids = lambda: [plan[0].id]
    prod._show_segments()
    prod.segments.setCurrentRow(0)
    old_key = plan[0].segments[0].key
    prod.correct_segment(("Le soir tombait doucement sur Siobhan.", "Siobhan", "Chivône"))
    import time

    for _ in range(200):
        app.processEvents()
        if prod._retake_task is not None and not prod._retake_task.is_running():
            break
        time.sleep(0.02)
    app.processEvents()
    assert ch.text.startswith("Le soir tombait doucement sur Siobhan.")
    assert pr.lexicon[-1].replacement == "Chivône"
    new_rc = renderer.build_plan(pr, win.ctx.library)[0]
    assert new_rc.segments[0].key != old_key and "Chivône" in new_rc.segments[0].text
    assert renderer.chapter_is_current(pr, new_rc)  # seul ce passage a été refait, chapitre réassemblé

    # Voix : la voix de base peut être Kokoro (hors ligne)
    clone = win.ctx.library.save(VoiceProfile(name="Moi", engine="fastclone", kind="clone"))
    win.show_page("voices")
    editor = win.pages["voices"].editor
    editor.set_voice(clone)
    i = editor.base.findData("kokoro:ff_siwis")
    assert i > 0 and editor.base.findData("fr-FR-DeniseNeural") > 0
    editor.base.setCurrentIndex(i)
    assert win.ctx.library.get(clone.id).engine_voice == "kokoro:ff_siwis"
    win.ctx.library.delete(clone.id)
    win.ctx.library.delete(voice.id)
    win.ctx.dirty = False
    win.close()


def test_hosts_page_rename_and_dialogue(app):
    from polyglottestudio.core import ai
    from polyglottestudio.core.models import VoiceProfile
    from polyglottestudio.ui.dialogs.write_dialogue import WriteDialogueDialog
    from polyglottestudio.ui.main_window import MainWindow, new_podcast

    win = MainWindow()
    lib = win.ctx.library
    va = lib.save(VoiceProfile(name="Voix A", engine="edge", gender="F"))
    vb = lib.save(VoiceProfile(name="Voix B", engine="edge", gender="M"))
    pr = new_podcast(lib)
    assert [h.name for h in pr.hosts] == ["Alex", "Sam"]
    assert pr.hosts[0].voice_id and pr.hosts[0].voice_id != pr.hosts[1].voice_id
    win.ctx.set_project(pr)
    page = win.pages["hosts"]
    win.show_page("hosts")
    row = page.rows[0]
    row.name.setText("Camille")
    row._renamed()
    assert pr.hosts[0].name == "Camille"
    assert "@Camille:" in pr.chapters[0].text and "@Alex:" not in pr.chapters[0].text
    assert pr.cast.get("Camille") == pr.hosts[0].voice_id
    page.add("guest")
    assert pr.hosts[-1].role == "guest" and pr.hosts[-1].name == "Invité"

    ch = pr.chapters[0]
    ch.title = "Épisode 1"
    dlg = WriteDialogueDialog(win.ctx, ch, win)
    assert dlg.notes.toPlainText() == ""  # le script est déjà un dialogue
    dlg._done(("Titre IA", "Desc IA", [ai.DialogueLine("Camille", "Bonjour !", "joyeux"),
                                       ai.DialogueLine("Sam", "Salut.")]))
    assert dlg.use.isEnabled()
    dlg._apply()
    assert ch.text == "@Camille: [joyeux] Bonjour !\n\n@Sam: Salut."
    assert ch.title == "Titre IA" and ch.description == "Desc IA"

    ep = win.pages["manuscript"]
    win.show_page("manuscript")
    ep.list.setCurrentRow(0)
    ep.ep_number.setValue(7)
    ep.ep_type.setCurrentIndex(ep.ep_type.findData("bonus"))
    assert ch.number == 7 and ch.episode_type == "bonus"
    assert ep.list.item(0).text().startswith("Bonus · Titre IA")
    for key in win.pages:
        win.show_page(key)
        app.processEvents()
    for v in (va, vb):
        lib.delete(v.id)
    win.ctx.dirty = False
    win.close()


def test_calendar_templates_and_studio_tools(app, monkeypatch):
    from PySide6.QtCore import QDate

    from polyglottestudio.core.models import VoiceProfile
    from polyglottestudio.ui.dialogs.templates import TemplateDialog
    from polyglottestudio.ui.main_window import MainWindow, new_podcast

    win = MainWindow()
    lib = win.ctx.library
    vs = [lib.save(VoiceProfile(name=f"V{i}", engine="edge", gender="FM"[i % 2])) for i in range(3)]
    pr = new_podcast(lib, "debat")
    assert [h.name for h in pr.hosts] == ["Nora", "Paul", "Zoé"]
    assert len({h.voice_id for h in pr.hosts}) == 3
    win.ctx.set_project(pr)
    dlg = TemplateDialog(win, for_episode=True)
    dlg._choose("interview")
    assert dlg.selected_name == "Interview"
    ep = win.pages["manuscript"]
    win.show_page("manuscript")
    ep.list.setCurrentRow(0)
    monkeypatch.setattr(TemplateDialog, "exec", lambda self: (self._choose("interview"), True)[1])
    ep.add_from_template()
    assert len(pr.chapters) == 2 and pr.host_by_name("Camille") is not None
    ep.list.setCurrentRow(0)
    cur = ep.editor.textCursor()
    cur.movePosition(cur.MoveOperation.Start)
    while cur.block().isValid() and not cur.block().text().startswith("@Paul:"):
        cur.movePosition(cur.MoveOperation.NextBlock)
    ep.editor.setTextCursor(cur)
    ep.tag_overlap()
    assert "@Paul: [par-dessus]" in ep.editor.toPlainText()
    ep._insert_block("[son: ding]")
    assert "\n[son: ding]\n" in ep.editor.toPlainText()
    ep._fill_sounds()
    assert ep.sound_menu.actions()

    cal = win.pages["calendar"]
    win.show_page("calendar")
    cal.start.setDate(QDate(2026, 11, 2))
    cal.plan()
    assert [c.pub_date for c in pr.chapters] == ["2026-11-02", "2026-11-09"]
    assert cal.table.rowCount() == 2 and cal.table.item(0, 3).text() in ("Écrit", "À écrire")
    hosts = win.pages["hosts"]
    win.show_page("hosts")
    hosts.rows[1].pan.setCurrentIndex(hosts.rows[1].pan.findData(1.0))
    assert pr.hosts[1].pan == 1.0 and pr.host_pan("Paul") == 1.0
    for key in win.pages:
        win.show_page(key)
        app.processEvents()
    for v in vs:
        lib.delete(v.id)
    win.ctx.dirty = False
    win.close()
