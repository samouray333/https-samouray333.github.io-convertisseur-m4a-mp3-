"""Tests des algorithmes sans moteur d'IA : répliques, personnes, calage, sous-titres, projet."""

import json

import numpy as np
import pytest

from doublys.core import segment, speakers, subtitles, timing
from doublys.core.models import DubSettings, Line, Project


def words(spec):
    """[(début, fin, mot)] → format Whisper."""
    return [[a, b, w, 0.9] for a, b, w in spec]


# -- répliques -----------------------------------------------------------------------------
def test_segment_sentence_and_pause():
    w = words([(0.0, 0.3, " Hello"), (0.35, 0.7, " there."), (0.8, 1.1, " How"), (1.15, 1.4, " are"),
               (1.45, 1.8, " you?"), (3.0, 3.4, " Fine"), (3.45, 3.9, " thanks")])
    lines = segment.lines_from_words(w)
    assert [ln.en for ln in lines] == ["Hello there.", "How are you?", "Fine thanks"]
    assert lines[1].start == 0.8 and lines[1].end == 1.8


def test_segment_max_length_splits_at_comma():
    spec, t = [], 0.0
    for i in range(40):
        word = f" w{i}" + ("," if i == 24 else "")
        spec.append((t, t + 0.3, word))
        t += 0.35
    lines = segment.lines_from_words(words(spec), max_len=12.0)
    assert len(lines) >= 2
    assert all(ln.length <= 12.0 + 1e-6 for ln in lines)
    assert lines[0].en.endswith("w24,")


def test_segment_merges_short_fragment():
    w = words([(0.0, 0.3, " Yes."), (0.5, 0.8, " I"), (0.85, 1.2, " agree"), (1.25, 1.7, " completely.")])
    lines = segment.lines_from_words(w, min_fragment=0.6)
    assert len(lines) == 1 and lines[0].en == "Yes. I agree completely."


def test_split_and_merge_line():
    ln = Line(start=0.0, end=3.0, en="One two. Three four", person_id="p1",
              words=[[0.0, 0.4, " One"], [0.5, 1.0, " two."], [1.6, 2.0, " Three"], [2.1, 3.0, " four"]])
    a, b = segment.split_line(ln)
    assert a.en == "One two." and b.en == "Three four" and b.start == 1.6 and a.person_id == "p1"
    m = segment.merge_lines(b, a)
    assert m.en == "One two. Three four" and m.start == 0.0 and m.end == 3.0


# -- personnes -----------------------------------------------------------------------------
def _emb(center, rng, noise=0.05):
    v = np.zeros(192)
    v[center:center + 8] = 1.0
    v += rng.normal(0, noise, 192)
    return list(v / np.linalg.norm(v))


def test_agglomerate_two_speakers():
    rng = np.random.default_rng(0)
    emb = np.array([_emb(10, rng) for _ in range(5)] + [_emb(100, rng) for _ in range(4)])
    labels = speakers.agglomerate(emb, threshold=0.6)
    assert len(set(labels[:5])) == 1 and len(set(labels[5:])) == 1 and labels[0] != labels[5]
    assert len(set(speakers.agglomerate(emb, threshold=0.6, max_clusters=1))) == 1


def test_assign_people_order_and_short_lines():
    rng = np.random.default_rng(1)
    lines = [Line(start=i * 3.0, end=i * 3.0 + 2.0) for i in range(6)]
    lines.append(Line(start=18.5, end=18.8))  # trop courte : suit sa voisine
    centers = [100, 100, 10, 10, 100, 10]
    emb = {ln.id: _emb(c, rng) for ln, c in zip(lines, centers)}
    people = speakers.assign_people(lines, emb, threshold=0.6)
    assert [p.name for p in people] == ["P1", "P2"]
    assert lines[0].person_id == people[0].id and lines[2].person_id == people[1].id
    assert lines[6].person_id == lines[5].person_id


def test_keep_names_after_regrouping():
    rng = np.random.default_rng(2)
    lines = [Line(start=i * 3.0, end=i * 3.0 + 2.0) for i in range(4)]
    emb = {ln.id: _emb(c, rng) for ln, c in zip(lines, [10, 100, 10, 100])}
    old = speakers.assign_people(lines, emb)
    old[0].name, old[0].voice_mode = "Marie", "xtts"
    before = {ln.id: ln.person_id for ln in lines}
    new = speakers.keep_names(old, speakers.assign_people(lines, emb), before, lines)
    assert new[0].name == "Marie" and new[0].voice_mode == "xtts"


# -- calage --------------------------------------------------------------------------------
def test_slots():
    s = DubSettings()
    lines = [Line(start=0.0, end=2.0), Line(start=2.5, end=4.0), Line(start=10.0, end=11.0)]
    assert timing.slots(lines, s, 20.0) == pytest.approx([2.4, 2.5, 2.0])
    assert timing.char_budget(2.0) == 29


def _tone(seconds, sr=24000):
    t = np.arange(int(seconds * sr)) / sr
    return (0.3 * np.sin(2 * np.pi * 200 * t)).astype(np.float32), sr


@pytest.fixture
def fit_settings():
    return DubSettings()


def test_fit_ok(fit_settings):
    res = timing.fit(lambda rate: _tone(1.5 / rate), 2.0, fit_settings)
    assert res.state == "ok" and res.tempo == 1.0


def _needs_ffmpeg():
    from tests.conftest import has_ffmpeg

    if not has_ffmpeg():
        pytest.skip("FFmpeg absent")


def test_fit_tempo_rate_long(fit_settings):
    _needs_ffmpeg()
    res = timing.fit(lambda rate: _tone(2.1 / rate), 2.0, fit_settings)
    assert res.state == "tempo" and res.duration == pytest.approx(2.0, abs=0.08)
    calls = []

    def synth(rate):
        calls.append(rate)
        return _tone(2.6 / rate)

    res = timing.fit(synth, 2.0, fit_settings)
    assert res.state == "rate" and calls[1] == pytest.approx(1.3) and res.duration <= 2.08
    res = timing.fit(lambda rate: _tone(4.0 / rate), 2.0, fit_settings)
    assert res.state == "long" and "raccourcis" in res.message


def test_match_level():
    x, sr = _tone(1.0)
    out, gain = timing.match_level(x * 0.25, sr, timing.active_rms_db(x, sr))
    assert gain == pytest.approx(12.04, abs=0.5)
    assert timing.match_level(x * 0.01, sr, timing.active_rms_db(x, sr))[1] == 18.0  # gain plafonné
    assert np.max(np.abs(out)) <= 0.97 + 1e-6


# -- sous-titres et projet ----------------------------------------------------------------------
def test_srt():
    lines = [Line(start=1.0, end=2.0, en="Hi.", fr="Salut."), Line(start=2.5, end=3.0, en="Bye", fr="")]
    srt = subtitles.build_srt(lines, "fr")
    assert srt.startswith("1\n00:00:01,000 --> 00:00:02,000\nSalut.")
    assert "Bye" in subtitles.build_srt(lines, "en")
    assert subtitles.srt_time(3723.5) == "01:02:03,500"


def test_project_roundtrip(tmp_path):
    from doublys.core import project as project_io

    pr = Project(title="Essai", source_video="video.mp4", lines=[Line(start=0, end=1, en="Hi", fr="Salut")])
    pr.mark_step("extract")
    path = project_io.save_project(pr, tmp_path / "Essai" / "Essai.doublys")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["lines"][0]["fr"] == "Salut" and "path" not in data
    back = project_io.load_project(path)
    assert back.lines[0].en == "Hi" and back.step_done("extract") and back.next_step() == "separate"
    back.invalidate_from("extract")
    assert back.steps == {}


def test_load_bad_project(tmp_path):
    from doublys.core import project as project_io

    p = tmp_path / "x.doublys"
    p.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(project_io.ProjectError):
        project_io.load_project(p)


def test_pitch_and_gender():
    from doublys.core import refs

    sr = 16000
    t = np.arange(sr * 2) / sr
    low = (0.3 * np.sign(np.sin(2 * np.pi * 110 * t))).astype(np.float32)
    high = (0.3 * np.sign(np.sin(2 * np.pi * 220 * t))).astype(np.float32)
    assert refs.gender_from_pitch(refs.estimate_pitch(low, sr)) == "M"
    assert refs.gender_from_pitch(refs.estimate_pitch(high, sr)) == "F"


def test_deepseek_translation_parsing():
    from doublys.core import ai

    class Fake:
        def __init__(self):
            self.prompts = []

        def chat_json(self, system, user, max_tokens=8000):
            self.prompts.append(user)
            n = user.count("caractères]")
            return {"lines": [{"n": k, "fr": f" Réplique {k} "} for k in range(1, n + 1)]}

    items = [{"en": f"Line {i}", "person": "P1", "budget": 30} for i in range(45)]
    client = Fake()
    out = ai.translate_lines(items, client)
    assert out[0] == "Réplique 1" and out[44] == "Réplique 5" and len(client.prompts) == 2
    assert "Contexte précédent" in client.prompts[1] and "max 30 caractères" in client.prompts[0]
