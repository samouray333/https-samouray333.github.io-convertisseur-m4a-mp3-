"""Traduction cohérente (tu / vous), vidéos longues (morceaux, reprise), estimation du temps."""

import json

import pytest

from doublys.core import translate
from doublys.core.models import Line
from tests.conftest import needs_ffmpeg


def test_split_sentences():
    assert translate.split_sentences("Almost. I need twenty more minutes, and then I'll send it.") == [
        "Almost.", "I need twenty more minutes, and then I'll send it."]
    assert translate.split_sentences("") == []


def test_register():
    assert translate.register("Je ne m'attendais pas à te voir.") == "tu"
    assert translate.register("Cette fois, vous payez !") == "vous"
    assert translate.register("Bonne idée.") == ""


def test_pair_register_is_consistent_and_sentences_kept():
    lines = [Line(start=0, end=2, en="I didn't expect to see you.", person_id="a"),
             Line(start=2.5, end=4, en="Almost. I could not sleep.", person_id="b"),
             Line(start=4.5, end=6, en="This time you are paying!", person_id="a"),
             Line(start=7, end=8, en="Can you help me?", person_id="b")]
    table = {
        "I didn't expect to see you.": ["Je ne m'attendais pas à te voir.", "Je ne m'attendais pas à vous voir."],
        "Almost.": ["Presque."],
        "I could not sleep.": ["Je n'ai pas pu dormir."],
        "This time you are paying!": ["Cette fois, vous payez !", "Cette fois, tu paies !"],
        "Can you help me?": ["Tu peux m'aider ?", "Pouvez-vous m'aider ?"],
    }
    calls = []

    def fn(sentences, n_best):
        calls.append(list(sentences))
        return [table[s] for s in sentences]

    out = translate.translate_lines(lines, [80, 80, 80, 80], fn)
    assert out[1] == "Presque. Je n'ai pas pu dormir."  # la phrase courte n'est plus avalée
    assert translate.register(out[0]) == translate.register(out[2]) == translate.register(out[3]) == "tu"
    assert len(calls) == 1 and len(calls[0]) == 5
    # une seule réplique retraduite : le registre de la paire vient des traductions existantes
    for i, fr in out.items():
        lines[i].fr = fr
    again = translate.translate_lines(lines, [80] * 4, fn, todo=[2])
    assert list(again) == [2] and again[2] == "Cette fois, tu paies !"


def test_length_budget_prefers_shorter_variant():
    assert translate.choose(["Une phrase vraiment beaucoup trop longue pour le temps.", "Phrase courte."], "",
                            16) == "Phrase courte."


def test_chunks_cut_in_silences():
    from doublys.core import pipeline

    speech = [[i * 10.0, i * 10.0 + 8.0] for i in range(200)]  # 2 s de silence toutes les 10 s
    chunks = pipeline.chunks_for(2000.0, speech, 600.0)
    assert chunks[0][0] == 0.0 and chunks[-1][1] == 2000.0
    for a, b in chunks[:-1]:
        assert abs(b % 10.0 - 9.0) < 0.01  # coupure au milieu d'un silence
    assert pipeline.chunks_for(500.0, speech) == [(0.0, 500.0)]


@needs_ffmpeg
def test_chunked_transcription_resumes(tmp_path, test_video, fakes, monkeypatch):
    from doublys.core import engines, pipeline
    from doublys.core import project as project_io

    pr = project_io.create_project(test_video, tmp_path / "p", "Long")
    pipeline.run_step(pr, "extract", pipeline.Job())
    pipeline.run_step(pr, "separate", pipeline.Job())
    assert json.loads(pipeline.wf(pr, pipeline.SPEECH).read_text())  # passages parlés repérés
    monkeypatch.setattr(pipeline, "CHUNK_SECONDS", 5.0)
    pipeline.run_step(pr, "transcribe", pipeline.Job())
    parts = sorted(pipeline.wf(pr, pipeline.TRANSCRIPT_PARTS).glob("*.json"))
    assert len(parts) >= 2
    words = json.loads(pipeline.wf(pr, pipeline.TRANSCRIPT).read_text())["words"]
    assert words == sorted(words, key=lambda w: w[0])

    # reprise : les morceaux déjà faits ne sont pas recalculés
    whisper = engines.get_tool("whisper")
    calls = []
    orig = whisper.transcribe_words
    monkeypatch.setattr(whisper, "transcribe_words", lambda *a, **k: calls.append(k) or orig(*a, **k))
    parts[-1].unlink()
    pr.mark_step("transcribe", False)
    pipeline.run_step(pr, "transcribe", pipeline.Job())
    assert len(calls) == 1
    # relance volontaire d'une étape déjà faite : tout est refait
    pipeline.run_step(pr, "transcribe", pipeline.Job())
    assert len(calls) == 1 + len(parts)


def test_estimate_and_learning(tmp_path):
    from doublys.config import settings
    from doublys.core import pipeline
    from doublys.core.models import Project, VideoInfo

    pr = Project(video=VideoInfo(duration=5400.0))
    pr.settings.expressive = False
    settings().set("speed_factors", {})
    full = pipeline.estimate_seconds(pr, pipeline.steps_to_run(pr) + ["export"])
    assert 1.5 * 3600 < full < 3.5 * 3600
    pipeline.learn_speed("dub", 2 * 5400.0, 5400.0)  # cet ordinateur est plus lent
    assert pipeline.estimate_seconds(pr, ["dub"]) > pipeline.DEFAULT_SPEED["dub"] * 5400
    settings().set("speed_factors", {})


@pytest.mark.parametrize("intensity,expected", [(9.0, True), (2.0, False)])
def test_expressive_selection(intensity, expected, monkeypatch):
    from doublys.core import engines, pipeline
    from doublys.core.models import Person, Project

    class Ready:
        def is_ready(self):
            return True

    monkeypatch.setattr(engines, "get_engine", lambda eid: Ready() if eid == "chatterbox" else None)
    p = Person(name="P1")
    pr = Project(people=[p], lines=[Line(start=0, end=2, person_id=p.id, intensity=intensity)])
    assert (pr.lines[0].id in pipeline.expressive_lines(pr)) is expected
