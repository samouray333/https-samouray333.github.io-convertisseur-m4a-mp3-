"""Chaîne complète avec moteurs factices : extraction, séparation, répliques, personnes, voix, mixage, export."""

import pytest

from tests.conftest import needs_ffmpeg

pytestmark = needs_ffmpeg


@pytest.fixture
def project(tmp_path, test_video, fakes):
    from doublys.core import project as project_io

    pr = project_io.create_project(test_video, tmp_path / "projets", "Essai")
    pr.settings.voice_mode = "edge"
    return pr


def test_full_chain_and_cache(project):
    from doublys.core import ffmpeg, pipeline
    from doublys.core import project as project_io
    from doublys.selftest import SCRIPT

    pr = project
    progress = []
    job = pipeline.Job(on_progress=lambda s, f, m: progress.append((s, f)))
    pipeline.run_all(pr, job, save=lambda: project_io.save_project(pr))
    assert pr.next_step() is None
    assert len(pr.lines) == len(SCRIPT) and len(pr.people) == 2
    assert {p.gender for p in pr.people} == {"M", "F"}
    assert all(p.reference and project_io.resolve(pr, p.reference).exists() for p in pr.people)
    assert all(0.0 <= f <= 1.0 for _s, f in progress)
    assert ffmpeg.probe_duration(pipeline.wf(pr, pipeline.MIX)) == pytest.approx(pr.video.duration, abs=0.1)

    # rien n'a changé : aucune voix refaite
    keys = [ln.audio_key for ln in pr.lines]
    assert pipeline.step_dub(pr, pipeline.Job()).startswith("0 répliques produites")
    # texte modifié : seule cette réplique est refaite
    pr.lines[1].fr = "Une autre phrase, bien plus courte."
    assert pipeline.step_dub(pr, pipeline.Job()).startswith("1 répliques produites")
    assert [ln.audio_key for ln in pr.lines][0] == keys[0] and pr.lines[1].audio_key != keys[1]


def test_without_separation_and_export(project, tmp_path):
    from doublys.core import ffmpeg, pipeline

    pr = project
    pr.settings.separate = False
    pr.settings.translator = "opus"
    pipeline.run_all(pr, pipeline.Job())
    assert not pr.step_done("separate") and pr.step_done("mix")
    assert not pipeline.wf(pr, pipeline.BACKGROUND).exists()
    pr.export.container = "mkv"
    pr.export.keep_original_audio = True
    pr.export.audio_only = "wav"
    files = pipeline.export_files(pr, pipeline.Job(), out_dir=tmp_path / "sortie")
    streams = ffmpeg.probe(files[0])["streams"]
    assert files[0].suffix == ".mkv"
    assert [s["codec_type"] for s in streams].count("audio") == 2
    assert any(f.suffix == ".wav" for f in files)


def test_export_requires_mix(project):
    from doublys.core import pipeline

    with pytest.raises(pipeline.StepError):
        pipeline.export_files(project, pipeline.Job())


def test_cancel(project):
    from doublys.core import pipeline
    from doublys.core.ffmpeg import Cancelled

    job = pipeline.Job()
    job.cancel.set()
    with pytest.raises(Cancelled):
        pipeline.run_all(project, job)


def test_missing_engine_message(project):
    from doublys.core import engines, pipeline

    with engines._lock:
        engines._tools.clear()
    project.mark_step("extract")
    with pytest.raises(pipeline.StepError, match="Moteurs IA"):
        pipeline.run_step(project, "separate", pipeline.Job())
