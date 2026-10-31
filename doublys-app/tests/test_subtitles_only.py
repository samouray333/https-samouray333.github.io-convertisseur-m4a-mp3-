"""Mode « sous-titres seuls » (VOSTFR) et couleur des sous-titres par personne."""

import pytest

from doublys.core import subtitles
from doublys.core.models import Line, Person, Project
from tests.conftest import needs_ffmpeg


def _project():
    pr = Project()
    pr.people = [Person(name="Lucie", color="#FF6B4A"), Person(name="Chef", color="#4fc3f7")]
    pr.lines = [Line(0.0, 1.5, "Hello.", "Bonjour.", pr.people[0].id),
                Line(2.0, 3.0, "Hi.", "Salut.", pr.people[1].id)]
    return pr


def test_active_steps_without_voices():
    pr = _project()
    assert "dub" in pr.active_steps()
    pr.settings.subtitles_only = True
    assert pr.active_steps() == ["extract", "subtitles", "separate", "transcribe", "segment", "speakers",
                                 "translate"]
    pr.settings.separate = False
    assert "separate" not in pr.active_steps()
    for s in pr.active_steps():
        pr.mark_step(s)
    assert pr.next_step() is None  # tout est fait : il ne reste que l'export


def test_colored_srt():
    pr = _project()
    colors = subtitles.person_colors(pr)
    srt = subtitles.build_srt(pr.lines, "fr", colors=colors)
    assert '<font color="#FF6B4A">Bonjour.</font>' in srt
    assert '<font color="#4FC3F7">Salut.</font>' in srt  # couleur remise en majuscules
    assert "<font" not in subtitles.build_srt(pr.lines, "fr")
    pr.export.subtitle_colors = False
    assert subtitles.person_colors(pr) == {}


def test_invalid_color_is_white():
    assert subtitles.subtitle_color("rouge") == "" and subtitles.subtitle_color("#12345") == ""
    assert subtitles.subtitle_color(" #a1b2c3 ") == "#A1B2C3"


@needs_ffmpeg
def test_subtitles_only_chain_and_burned_colors(tmp_path, test_video, fakes):
    import numpy as np

    from doublys.core import ffmpeg, media, pipeline
    from doublys.core import project as project_io

    pr = project_io.create_project(test_video, tmp_path / "projets", "Essai")
    pr.settings.subtitles_only = True
    pipeline.run_all(pr, pipeline.Job())
    assert pr.step_done("translate") and not pr.step_done("dub") and not any(ln.audio for ln in pr.lines)
    with pytest.raises(pipeline.StepError):
        pipeline.export_files(pr, pipeline.Job(), preview=True)
    for p in pr.people:
        p.color = "#00FF00"  # vert franc : facile à retrouver dans l'image
    pr.export.burn_subtitles = True
    try:
        media.video_encoder()
    except ffmpeg.FFmpegError:
        pytest.skip("aucun encodeur H.264")
    files = pipeline.export_files(pr, pipeline.Job(), out_dir=tmp_path / "out")
    assert files[0].name == "Essai (VOSTFR).mp4"
    kinds = [s["codec_type"] for s in ffmpeg.probe(files[0])["streams"]]
    assert kinds.count("audio") == 1 and kinds.count("subtitle") == 0  # incrustés dans l'image
    ln = pr.lines[0]
    frames = media.extract_frames(files[0], ln.start + 0.2, 0.2, tmp_path / "img", 5.0, 480)
    from PIL import Image

    img = np.asarray(Image.open(frames[0]).convert("RGB")).astype(int)
    green = (img[..., 1] > 180) & (img[..., 0] < 90) & (img[..., 2] < 90)
    assert green.sum() > 50, "sous-titre vert absent de l'image"


def test_ass_styles_per_person():
    pr = _project()
    pr.people[1].name = "Chef, le grand"
    ass = subtitles.build_ass(pr.lines, pr.people, "fr", subtitles.person_colors(pr), 1280, 720, "Essai")
    assert "PlayResX: 1920" in ass and "PlayResY: 1080" in ass
    assert "Style: Lucie,Arial,62,&H004A6BFF," in ass  # #FF6B4A en ordre BGR
    assert "Style: Chef le grand,Arial,62,&H00F7C34F," in ass  # virgule retirée (séparateur ASS)
    assert "Dialogue: 0,0:00:00.00,0:00:01.50,Lucie,Lucie,0,0,0,,Bonjour." in ass
    plain = subtitles.build_ass(pr.lines, pr.people, "fr", {}, 1280, 720)
    assert "Dialogue: 0,0:00:02.00,0:00:03.00,Défaut,Chef le grand," in plain  # sans couleur : style blanc
    assert subtitles.ass_time(3725.456) == "1:02:05.46"
    pr.lines[0].fr = "Texte {balise} avec \\ et une phrase assez longue pour passer sur deux lignes à l'écran."
    ass = subtitles.build_ass(pr.lines, pr.people, "fr", {}, 1920, 1080)
    assert "{" not in ass.split("[Events]")[1] and "\\N" in ass


@needs_ffmpeg
def test_mkv_ass_track(tmp_path, test_video, fakes):
    from doublys.core import ffmpeg, pipeline
    from doublys.core import project as project_io

    pr = project_io.create_project(test_video, tmp_path / "projets", "Essai")
    pr.settings.subtitles_only = True
    pipeline.run_all(pr, pipeline.Job())
    pr.export.container = "mkv"
    pr.export.subtitles_en = True
    files = pipeline.export_files(pr, pipeline.Job(), out_dir=tmp_path / "out")
    subs = [s for s in ffmpeg.probe(files[0])["streams"] if s["codec_type"] == "subtitle"]
    assert [s["codec_name"] for s in subs] == ["ass", "ass"]
    assert subs[0]["tags"]["language"] == "fre" and subs[0]["disposition"]["default"] == 1
    assert any(f.name.endswith(".fr.srt") for f in files)  # fichiers .srt toujours fournis à côté
    pr.export.ass_subtitles = False
    files = pipeline.export_files(pr, pipeline.Job(), out_dir=tmp_path / "out2")
    assert {s["codec_name"] for s in ffmpeg.probe(files[0])["streams"] if s["codec_type"] == "subtitle"} == {"subrip"}
