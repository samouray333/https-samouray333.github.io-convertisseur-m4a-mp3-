"""Doublys 1.2 : sous-titres existants (pistes, fichiers, image), recalage, couverture de la VF, filet VO."""

import json

import numpy as np
import pytest

from doublys.core import align, coverage, subsources
from doublys.core.models import Line, Project
from tests.conftest import needs_ffmpeg

ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.40,Default,,0,0,0,,{\\i1}I can't believe it,\\NGeki!{\\i0}
Dialogue: 0,0:00:04.20,0:00:06.00,OP,,0,0,0,,{\\k20}Ha{\\k30}ruka
Dialogue: 0,0:00:04.20,0:00:06.00,Signs,,0,0,0,,{\\an8}BANDORA PALACE
Dialogue: 0,0:00:06.60,0:00:09.60,Default,,0,0,0,,- Run! - Where?
Dialogue: 0,0:00:10.40,0:00:12.60,Default,,0,0,0,,The Dragon is here. (TL note: Dragonranger)
"""


# -- lecture et nettoyage ----------------------------------------------------------------------
def test_parse_and_prepare_ass():
    cues = subsources.parse_ass(ASS)
    assert len(cues) == 5
    kept, dropped = subsources.prepare(cues)
    assert [c.text for c in kept] == ["I can't believe it, Geki!", "Run!", "Where?", "The Dragon is here."]
    assert {d["reason"] for d in dropped} >= {"karaoké (générique chanté)", "texte en haut de l'image (panneau)"}
    run, where = kept[1], kept[2]
    assert run.start == 6.6 and where.end == 9.6 and run.end == pytest.approx(where.start)


def test_parse_srt_vtt_and_clean():
    srt = "1\n00:00:01,000 --> 00:00:02,500\n<i>Hello</i> &amp; bye\n\n2\n00:00:03,000 --> 00:00:04,000\n[Music]\n"
    cues = subsources.parse_srt(srt)
    assert [(c.start, c.end) for c in cues] == [(1.0, 2.5), (3.0, 4.0)]
    kept, dropped = subsources.prepare(cues)
    assert [c.text for c in kept] == ["Hello & bye"] and dropped[0]["reason"] == "sous-titre vide après nettoyage"
    vtt = "WEBVTT\n\n00:01.000 --> 00:02.000 align:start\nHi there\n"
    assert subsources.parse_srt(vtt)[0].text == "Hi there"


def test_merge_fragments_and_duplicates():
    cues = [subsources.Cue(1.0, 2.0, "We have to stop"), subsources.Cue(2.1, 3.0, "Bandora now."),
            subsources.Cue(3.5, 4.0, "Go."), subsources.Cue(4.1, 5.0, "Now.")]
    out = subsources.merge_fragments(cues)
    assert [c.text for c in out] == ["We have to stop Bandora now.", "Go.", "Now."]
    kept, _ = subsources.prepare([subsources.Cue(1, 2, "Hi"), subsources.Cue(2.1, 3, "Hi")])
    assert len(kept) == 1 and kept[0].end == 3


def test_language_and_files(tmp_path):
    video = tmp_path / "Episode 1.mkv"
    video.write_bytes(b"")
    for name in ("Episode 1.en.srt", "Episode 1.fre.ass", "Episode 10.srt", "Episode 1 (EN, OCR).srt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    files = subsources.find_files(video)
    assert sorted(f.language for f in files) == ["en", "en", "fr"]
    assert not any("Episode 10" in f.path for f in files)
    best = subsources.rank(files)[0]
    assert best.language == "fr"  # français d'abord : pas de traduction
    assert subsources.guess_language(["Je ne sais pas, c'est la vie et le temps"]) == "fr"
    assert subsources.guess_language(["I don't know what you are doing with the time"]) == "en"


# -- recalage ----------------------------------------------------------------------------------
def test_global_offset_found():
    speech = [[2.5, 4.9], [5.7, 7.5], [8.1, 11.1], [11.9, 14.1], [14.9, 16.5], [20.0, 22.0]]
    cues = [(a - 1.5, b - 1.5) for a, b in speech]  # sous-titres en avance de 1,5 s
    offset, gain = align.global_offset(cues, speech)
    assert offset == pytest.approx(1.5, abs=0.1) and gain > 0.1
    assert align.global_offset([(a, b) for a, b in speech], speech) == (0.0, 0.0)


def test_refine_tightens_and_extends():
    lines = [Line(start=1.0, end=4.0), Line(start=5.0, end=6.0)]
    speech = [[1.3, 3.5], [4.9, 6.8]]
    align.refine(lines, speech)
    assert lines[0].start == pytest.approx(1.3) and lines[0].end == pytest.approx(3.5)
    assert lines[1].start == pytest.approx(4.9) and lines[1].end == pytest.approx(6.8)  # parole qui déborde


# -- couverture --------------------------------------------------------------------------------
def test_intervals():
    assert coverage.merge([[3, 4], [1, 2], [1.5, 3.2]]) == [[1, 4]]
    assert coverage.subtract([[0, 10]], [[1, 2], [5, 6]]) == [[0, 1], [2, 5], [6, 10]]


def test_gaps_and_summary(tmp_path):
    from doublys.core import project as project_io

    pr = Project(title="Essai")
    project_io.save_project(pr, tmp_path / "Essai" / "Essai.doublys")
    pr.lines = [Line(start=1.0, end=2.0, en="Hi", fr="Salut"), Line(start=5.0, end=6.0, en="Go", fr="Vas-y")]
    speech = [[1.0, 2.0], [3.0, 3.6], [5.0, 6.0], [8.0, 8.2], [9.0, 9.7]]
    project_io.work_file(pr, coverage.SPEECH_FILE).write_text(json.dumps(speech))
    gaps = coverage.update(pr)
    assert [(g["start"], g["end"]) for g in gaps] == [(3.0, 3.6), (9.0, 9.7)]  # 0,2 s : trop court pour compter
    text, problems = coverage.summary(pr)
    assert problems == 2 and "2 passages parlés sans VF" in text
    pr.gaps[0]["state"] = "ignored"
    coverage.update(pr)
    assert coverage.summary(pr)[1] == 1 and pr.gaps[0]["state"] == "ignored"  # choix gardé
    pr.gaps = []
    pr.settings.keep_original_shouts = True
    coverage.update(pr)
    assert all(g["state"] == "vo" for g in pr.gaps)
    assert coverage.summary(pr) == ("2 répliques, 100 % de la parole couverte", 0)


def test_old_project_migration():
    data = Project(title="Ancien").to_dict()
    data["format_version"] = 1
    data["steps"] = {s: {"done": True} for s in ("extract", "separate", "transcribe", "segment")}
    pr = Project.from_dict(data)
    assert pr.step_done("subtitles") and pr.subs.kind == "none" and pr.next_step() == "speakers"
    pr.invalidate_from("subtitles")  # changer de sous-titres ne refait pas la séparation
    assert pr.step_done("separate") and not pr.step_done("segment")


# -- chaîne complète ---------------------------------------------------------------------------
@pytest.fixture
def make_project(tmp_path, fakes):
    from doublys.core import project as project_io

    def make(video, title="Essai"):
        pr = project_io.create_project(video, tmp_path / "projets", title)
        pr.settings.voice_mode = "edge"
        return pr

    return make


@needs_ffmpeg
def test_mkv_tracks_ass_srt(tmp_path, test_video, make_project):
    from doublys.core import ffmpeg, pipeline

    ass = tmp_path / "piste.ass"
    ass.write_text(ASS, encoding="utf-8")
    srt = tmp_path / "piste.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nBonjour à tous.\n", encoding="utf-8")
    mkv = tmp_path / "Episode.mkv"
    ffmpeg.run_ffmpeg(["-i", str(test_video), "-i", str(ass), "-i", str(srt), "-map", "0", "-map", "1", "-map", "2",
                       "-c", "copy", "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=fre", str(mkv)])
    pr = make_project(mkv)
    pipeline.run_step(pr, "extract", pipeline.Job())
    detail = pipeline.run_step(pr, "subtitles", pipeline.Job())
    assert pr.subs.kind == "track" and pr.subs.language == "fr" and pr.subs.track == 1, detail
    pr.subs.kind, pr.subs.track = "track", 0  # piste anglaise choisie à la main
    pipeline.run_step(pr, "subtitles", pipeline.Job())
    assert pr.subs.language == "en" and pr.subs.count == 4
    pipeline.run_all(pr, pipeline.Job())
    assert [ln.en for ln in pr.lines] == ["I can't believe it, Geki!", "Run!", "Where?", "The Dragon is here."]
    assert all(ln.source == "track" for ln in pr.lines)
    dropped = coverage.load_dropped(pr)
    assert any(d["reason"].startswith("karaoké") for d in dropped)


@needs_ffmpeg
def test_mp4_mov_text_and_french_file(tmp_path, test_video, make_project):
    from doublys.core import ffmpeg, pipeline

    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,400\nHello there.\n\n2\n00:00:04,200 --> 00:00:06,000\nGo!\n",
                   encoding="utf-8")
    mp4 = tmp_path / "Clip.mp4"
    ffmpeg.run_ffmpeg(["-i", str(test_video), "-i", str(srt), "-map", "0", "-map", "1", "-c", "copy", "-c:s",
                       "mov_text", str(mp4)])
    pr = make_project(mp4)
    pipeline.run_step(pr, "extract", pipeline.Job())
    pipeline.run_step(pr, "subtitles", pipeline.Job())
    assert pr.subs.kind == "track" and pr.subs.count == 2
    # fichier français à côté : préféré, la traduction est sautée
    (tmp_path / "Clip.fr.srt").write_text("1\n00:00:01,000 --> 00:00:03,400\nBonjour.\n", encoding="utf-8")
    pr.subs.kind = "auto"
    pipeline.run_step(pr, "subtitles", pipeline.Job())
    assert pr.subs.kind == "file" and pr.subs.language == "fr"
    pipeline.run_all(pr, pipeline.Job())
    assert pr.lines[0].fr == "Bonjour." and pr.lines[0].fr_edited


@needs_ffmpeg
def test_hardsubs_ocr_chain(tmp_path, make_project):
    from doublys.core import pipeline
    from doublys.selftest import HARDSUBS, make_hardsub_video

    video = make_hardsub_video(tmp_path / "Zyu.mp4", size="960x540", background="0x2a4060")
    pr = make_project(video, "Zyu")
    pipeline.run_step(pr, "extract", pipeline.Job())
    pipeline.run_step(pr, "subtitles", pipeline.Job())
    assert pr.subs.kind == "ocr" and pr.subs.count == len(HARDSUBS)
    assert 0.6 < pr.subs.zone[0] < pr.subs.zone[1] <= 1.0
    cues = pipeline.load_cues(pr)
    for c, (a, b, _t) in zip(cues, HARDSUBS):
        assert c.start == pytest.approx(a, abs=0.15) and c.end == pytest.approx(b, abs=0.15)
    assert (tmp_path / "Zyu (EN, OCR).srt").exists()
    pipeline.run_all(pr, pipeline.Job())
    assert len(pr.lines) == len(HARDSUBS) and all(ln.source == "ocr" and ln.audio for ln in pr.lines)
    assert pr.settings.detected_language == "en"


@needs_ffmpeg
def test_language_detected(tmp_path, test_video, make_project):
    from doublys.core import engines, pipeline

    engines.get_tool("whisper").language = "ja"
    pr = make_project(test_video)
    pr.settings.use_subtitles = False
    for step in ("extract", "subtitles", "separate", "transcribe"):
        pipeline.run_step(pr, step, pipeline.Job())
    assert pr.settings.detected_language == "ja" and pr.settings.language == "ja"
    assert pr.settings.language_confidence > 0.9


@needs_ffmpeg
def test_no_line_lost_and_vo_fallback(tmp_path, test_video, make_project):
    """Échec de synthèse simulé, réplique trop longue, passage parlé sans réplique : rien ne disparaît en silence,
    la voix d'origine revient là où il n'y a pas de VF."""
    from doublys.core import audio, engines, pipeline
    from doublys.selftest import SCRIPT

    pr = make_project(test_video)
    pr.settings.use_subtitles = False
    pipeline.run_all(pr, pipeline.Job(), start=None)
    assert len(pr.lines) == len(SCRIPT)
    edge = engines.get_engine("edge")
    calls = []
    real = edge.synthesize

    def flaky(text, voice, out_path, language, speed=1.0, seed=None):
        calls.append(text)
        if "Impossible" in text:
            raise engines.EngineError("moteur en panne")
        return real(text, voice, out_path, language, speed, seed)

    edge.synthesize = flaky
    try:
        pr.lines[1].fr = "Impossible à dire."
        pr.lines[2].fr = "Une réplique beaucoup trop longue pour son créneau, qui doit déborder sans disparaître du tout."
        removed = pr.lines.pop(4)  # passage parlé sans réplique
        pipeline.run_step(pr, "dub", pipeline.Job())
        pipeline.run_step(pr, "mix", pipeline.Job())
    finally:
        edge.synthesize = real
    failed = pr.lines[1]
    assert failed.state == "error" and failed.attempts >= 3 and "Échec" in failed.message
    assert sum(1 for t in calls if "Impossible" in t) >= 3  # essais avant d'abandonner
    long_line = pr.lines[2]
    assert long_line.audio and long_line.state in ("long", "rate", "tempo", "ok")
    gaps = coverage.open_gaps(pr)
    assert any(g["start"] <= removed.start + 0.3 and g["end"] >= removed.end - 0.3 for g in gaps)
    text, problems = coverage.summary(pr)
    assert problems >= 2 and "sans VF" in text and "en échec" in text
    mix, sr = audio.read_audio(pipeline.wf(pr, pipeline.MIX))
    voice, vsr = audio.read_audio(pipeline.wf(pr, pipeline.VOICE))

    def level(x, rate, a, b):
        seg = x[int(a * rate):int(b * rate)]
        return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0

    # la voix d'origine (tonalité de la personne) est audible là où il n'y a pas de VF
    for a, b in ((removed.start + 0.2, removed.end - 0.2), (failed.start + 0.2, failed.end - 0.2)):
        assert level(mix, sr, a, b) > 0.5 * level(voice, vsr, a, b) > 0.01
    pr.settings.vo_fallback = False
    pipeline.run_step(pr, "mix", pipeline.Job())
    mix2, _ = audio.read_audio(pipeline.wf(pr, pipeline.MIX))
    assert level(mix2, sr, removed.start + 0.2, removed.end - 0.2) < 0.3 * level(mix, sr, removed.start + 0.2,
                                                                               removed.end - 0.2)
