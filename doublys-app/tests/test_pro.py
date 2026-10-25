"""Séries, contrôle qualité, annuler/rétablir, file d'attente, éditeur de calage, nuances, rapport de bug."""

import numpy as np
import pytest

from doublys.core import qc, series, timing
from doublys.core.models import Line, Person, Project
from tests.conftest import needs_ffmpeg


def _vec(center, rng=None, noise=0.03):
    rng = rng or np.random.default_rng(0)
    v = np.zeros(192)
    v[center:center + 8] = 1
    v += rng.normal(0, noise, 192)
    return list(v / np.linalg.norm(v))


# -- séries -------------------------------------------------------------------------------
def test_series_save_and_recognize(tmp_path):
    from doublys.core import project as project_io

    rng = np.random.default_rng(1)
    ep1 = Project(title="Épisode 1")
    project_io.save_project(ep1, tmp_path / "ep1" / "ep1.doublys")
    red = Person(name="Red", gender="M", voice_mode="xtts", embedding=_vec(10, rng))
    blue = Person(name="Blue", gender="F", embedding=_vec(60, rng))
    extra = Person(name="P3", embedding=_vec(120, rng))  # non nommée : pas retenue
    ref = project_io.references_dir(ep1) / "red.wav"
    ref.write_bytes(b"RIFF")
    red.reference = project_io.relative(ep1, ref)
    ep1.people = [red, blue, extra]
    ep1.settings.glossary = [["変身", "Henshin"]]
    s, n = series.save_from_project(ep1, "Sentai test")
    assert n == 2 and {c.name for c in s.characters} == {"Red", "Blue"}
    assert "Sentai test" in series.list_series()

    ep2 = Project(title="Épisode 2", series="Sentai test")
    project_io.save_project(ep2, tmp_path / "ep2" / "ep2.doublys")
    p1, p2, p3 = (Person(name="P1", embedding=_vec(60, rng)), Person(name="P2", embedding=_vec(10, rng)),
                  Person(name="P3", embedding=_vec(170, rng)))
    ep2.people = [p1, p2, p3]
    assert series.apply_to_project(ep2) == 2
    assert (p1.name, p2.name, p3.name) == ("Blue", "Red", "P3")
    assert p2.voice_mode == "xtts" and p2.reference_source == "file" and p2.character
    assert ["変身", "Henshin"] in ep2.settings.glossary
    series.delete("Sentai test")
    assert "Sentai test" not in series.list_series()


# -- contrôle qualité ----------------------------------------------------------------------
def test_qc_flags():
    good = Line(start=0, end=2, en="Hello there my friend.", fr="Bonjour mon ami.", person_id="p",
                words=[[0, 1, " Hello", 0.9], [1, 2, " there", 0.95]])
    asr = Line(start=0, end=2, en="Hello there.", fr="Bonjour.", words=[[0, 1, " Hello", 0.2]])
    missing = Line(start=0, end=3, en="I need twenty more minutes before we go.", fr="Oui.")
    untranslated = Line(start=0, end=1, en="変身！", fr="変身！")
    loop = Line(start=0, end=2, en="Go now", fr="en chinois, en chinois, en chinois, en chinois, en chinois")
    spk = Line(start=0, end=2, en="Hi there.", fr="Salut toi.", person_id="p", speaker_score=0.7, speaker_margin=0.01)
    noisy = Line(start=0, end=2, en="Hi there.", fr="Salut toi.", person_id="p", speaker_score=0.2)
    codes = lambda ln: [c for c, _m in qc.check_line(ln)]  # noqa: E731
    assert codes(good) == []
    assert codes(asr) == ["asr"]
    assert codes(missing) == ["translation"]
    assert codes(untranslated) == ["translation"]
    assert codes(loop) == ["translation"]
    assert codes(spk) == ["speaker"]
    assert codes(noisy) == ["overlap"]
    pr = Project(lines=[good, asr, spk])
    assert qc.check(pr) == 2 and "2 réplique(s) à vérifier" in qc.summary(pr)
    asr.checked = True
    assert qc.check(pr) == 1


def test_speaker_scores():
    from doublys.core import speakers

    rng = np.random.default_rng(3)
    lines = [Line(start=i * 3, end=i * 3 + 2, person_id="a" if i < 3 else "b") for i in range(6)]
    emb = {ln.id: _vec(10 if ln.person_id == "a" else 100, rng) for ln in lines}
    people = [Person(name="A", id="a"), Person(name="B", id="b")]
    speakers.score_lines(lines, emb, people)
    assert all(ln.speaker_score > 0.9 and ln.speaker_margin > 0.5 for ln in lines)
    assert len(people[0].embedding) == 192


# -- nuances --------------------------------------------------------------------------------
def test_transfer_dynamics_follows_original():
    sr = 16000
    t = np.arange(sr * 2) / sr
    flat = (0.2 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    rising = (flat * np.linspace(0.2, 1.0, len(t))).astype(np.float32)
    out = timing.transfer_dynamics(flat, sr, rising, sr, amount=0.5)
    first, last = np.abs(out[: sr // 2]).mean(), np.abs(out[-sr // 2:]).mean()
    assert last > first * 1.5 and np.max(np.abs(out)) <= 0.971


# -- rapport de bug -------------------------------------------------------------------------
def test_bug_report_hides_key(tmp_path):
    import zipfile

    from doublys.config import settings
    from doublys.core import support

    settings().set("ai_key", "b64:c2VjcmV0")
    out = support.bug_report(None, tmp_path)
    with zipfile.ZipFile(out) as zf:
        prefs = zf.read("reglages.json").decode("utf-8")
        assert "c2VjcmV0" not in prefs and "masquée" in prefs and "systeme.json" in zf.namelist()
    settings().set("ai_key", "")


# -- interface : annuler, calage, file d'attente -------------------------------------------------
@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from doublys.ui import theme

    theme.apply(app, "dark")
    return app


@pytest.mark.gui
@needs_ffmpeg
def test_undo_redo_and_timing_editor(app, tmp_path, test_video, fakes):
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
    before = pr.lines[0].fr
    page.table.item(0, 5).setText("Texte modifié.")
    assert win.ctx.project.lines[0].fr == "Texte modifié." and win.ctx.can_undo()
    win.ctx.undo()
    assert win.ctx.project.lines[0].fr == before and win.ctx.can_redo()
    win.ctx.redo()
    assert win.ctx.project.lines[0].fr == "Texte modifié."
    # éditeur de calage : la réplique déplacée est recalée (voix refaite)
    page.table.selectRow(1)
    app.processEvents()
    ln = win.ctx.project.lines[1]
    start0, end0 = ln.start, ln.end
    assert page.timeline.lines and page.timeline.current == ln.id
    page.timeline.resize(800, 120)
    page.timeline.grab()  # dessin réel de l'éditeur
    page.timeline.edited.emit(ln.id, start0 + 0.2, end0 + 0.2)
    for _ in range(200):
        app.processEvents()
        if not win.ctx.runner.running:
            break
        import time

        time.sleep(0.02)
    moved = win.ctx.project.line(ln.id)
    assert abs(moved.start - (start0 + 0.2)) < 1e-6 and moved.audio and moved.audio_key
    win.ctx.undo()
    win.ctx.dirty = False
    win.close()


@pytest.mark.gui
@needs_ffmpeg
def test_queue_runs_two_videos(app, tmp_path, test_video, fakes, monkeypatch):
    import shutil

    from doublys.config import settings
    from doublys.core import jobqueue
    from doublys.ui.main_window import MainWindow

    settings().set("projects_dir", str(tmp_path / "projets"))
    videos = []
    for name in ("Episode 1.mp4", "Episode 2.mp4"):
        shutil.copy(test_video, tmp_path / name)
        videos.append(str(tmp_path / name))
    win = MainWindow()
    page = win.pages["queue"]
    page.add_videos(videos)
    assert jobqueue.pending_count() == 2
    # moteurs factices : voix « edge »
    from doublys.core import project as project_io

    for e in jobqueue.items():
        pr = project_io.load_project(e.path)
        pr.settings.voice_mode = "edge"
        project_io.save_project(pr)
    page.start()
    import time

    deadline = time.time() + 240
    while (page.active or win.ctx.runner.running) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    states = [(e.state, e.message) for e in jobqueue.items()]
    assert all(s == jobqueue.DONE for s, _m in states), states
    assert all(e.result.endswith("(VF).mp4") for e in jobqueue.items())
    settings().set("queue", [])
    win.close()


@pytest.mark.gui
def test_guide_dialog(app):
    from doublys.ui.dialogs.guide import GuideDialog

    d = GuideDialog()
    for _ in range(10):
        d._go(1)
    assert d.result() == d.DialogCode.Accepted
