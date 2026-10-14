"""Fonctions « studio » de PodCast Studio : chevauchements, stéréo, sons, prises au micro, chapitres, bande-annonce,
modèles d'émission, calendrier, page web, réécriture."""

import json
from datetime import date

import numpy as np
import soundfile as sf

from podcaststudio.core import ai, audio, project_io, renderer, schedule, sounds, templates, trailer, web
from podcaststudio.core.models import Chapter, Host, Project, VoiceProfile

from .conftest import needs_ffmpeg
from .test_ai import FakeClient


def make(tmp_path, library, text, stereo=True):
    a = library.save(VoiceProfile(name="A", engine="tone"))
    b = library.save(VoiceProfile(name="B", engine="tone"))
    pr = Project(chapters=[Chapter("Épisode", text)], narrator_voice_id=a.id,
                 hosts=[Host("Alex", "host", a.id), Host("Sam", "cohost", b.id)])
    pr.production.stereo = stereo
    pr.production.announce_chapter_titles = False
    project_io.save_project(pr, tmp_path / "p" / "P.pcsproj")
    return pr, a, b


def test_overlap_pan_and_markers_in_plan(tmp_path, tone_engine, library):
    pr, a, b = make(tmp_path, library, "[chapitre: Ouverture]\n\n@Alex: Voici une longue phrase d'introduction.\n\n"
                    "@Sam: Ah oui !\n\n@Alex: On continue avec une autre idée.\n\n@Sam: [par-dessus] Mais attends, "
                    "je ne suis pas d'accord du tout avec ça.\n\n# La suite\n\n@Alex: Bien.")
    segs = renderer.build_plan(pr, library)[0].segments
    by_text = {s.display: s for s in segs}
    assert segs[0].mark == "Ouverture" and by_text["La suite."].mark == "La suite"
    react = by_text["Ah oui !"]
    assert react.overlap_ms == pr.production.overlap_ms and segs[0].pause_after_ms == 0
    explicit = next(s for s in segs if s.display.startswith("Mais attends"))
    assert explicit.overlap_ms > 0  # balise explicite, même pour une longue réplique
    assert segs[0].pan < 0 < react.pan and by_text["La suite."].pan == 0.0
    pr.production.overlap_reactions = False
    segs2 = renderer.build_plan(pr, library)[0].segments
    assert next(s for s in segs2 if s.display == "Ah oui !").overlap_ms == 0
    pr.production.stereo = False
    assert all(s.pan == 0 for s in renderer.build_plan(pr, library)[0].segments)


def test_stereo_render_with_overlap_sound_and_take(tmp_path, tone_engine, library):
    pr, a, b = make(tmp_path, library, "@Alex: Bonjour à toutes et à tous, bienvenue.\n\n@Sam: Ah oui !\n\n"
                    "[son: ding]\n\n@Sam: [prise: moi.wav] Ma vraie voix.\n\n@Alex: [prise: absente.wav] Repli.")
    take = renderer.takes_dir(pr) / "moi.wav"
    audio.write_audio(take, (0.01 * np.sin(np.arange(44100) / 44100 * 2 * np.pi * 300)).astype(np.float32), 44100)
    plan = renderer.build_plan(pr, library)
    rc = plan[0]
    kinds = [s.kind for s in rc.segments]
    assert kinds == ["para", "para", "sound", "take", "para"]
    assert any("absente.wav" in w for w in rc.warnings)  # prise manquante : la synthèse lit le texte
    rep = renderer.Renderer(pr, library).render(plan)
    assert not rep.failed_segments
    out = renderer.chapter_output(pr, rc.id)
    info = sf.info(str(out))
    assert info.channels == 2
    t = renderer.segment_timings(pr, rc)
    assert t[1][0] < t[0][1]  # la réaction commence avant la fin de la réplique précédente
    data, sr = sf.read(str(out), always_2d=True)
    a0, a1 = int(t[0][0] * sr), int(t[0][1] * sr)
    left, right = np.abs(data[a0:a1, 0]).mean(), np.abs(data[a0:a1, 1]).mean()
    assert left > right * 1.3  # Alex est à gauche
    take_seg = rc.segments[3]
    take_audio, _ = audio.read_audio(renderer.cache_path(pr, take_seg.key))
    rms = audio.lin_to_db(float(np.sqrt(np.mean(take_audio.astype(np.float64) ** 2))))
    assert -23 < rms < -17  # prise remise au niveau des voix


def test_builtin_sounds_and_user_override(tmp_path, monkeypatch):
    for name in sounds.BUILTIN_LABELS:
        p = sounds.resolve(name)
        assert p is not None and sf.info(str(p)).duration > 0.5
    assert sounds.resolve("Jingle") == sounds.resolve("virgule")
    assert sounds.resolve("inexistant") is None
    proj = tmp_path / "projet"
    (proj / "sons").mkdir(parents=True)
    audio.write_audio(proj / "sons" / "Mon Rire.wav", np.zeros(4410, dtype=np.float32), 44100)
    assert sounds.resolve("mon rire", proj) == proj / "sons" / "Mon Rire.wav"
    assert any(n == "Mon Rire" for n, _l in sounds.available(proj))


@needs_ffmpeg
def test_chapters_in_mp3_notes_and_feed(tmp_path, tone_engine, library):
    from mutagen.id3 import ID3

    from podcaststudio.core.exporter import ExportItem, export_audiobook
    from podcaststudio.core.mastering import MasteringOptions

    pr, a, b = make(tmp_path, library, "[chapitre: Accueil]\n\n@Alex: Bonjour et bienvenue dans l'émission.\n\n"
                    "[chapitre: Le sujet]\n\n@Sam: Parlons maintenant du sujet principal du jour.")
    plan = renderer.build_plan(pr, library)
    renderer.Renderer(pr, library).render(plan)
    rc = plan[0]
    marks = rc.chapter_marks(renderer.segment_timings(pr, rc))
    assert [m[1] for m in marks] == ["Accueil", "Le sujet"] and marks[0][0] == 0.0
    pr.export.formats = ["mp3_chapters", "rss"]
    item = ExportItem("Épisode", renderer.chapter_output(pr, rc.id), id="g1", number=1, description="Résumé.",
                      chapters=marks)
    res = export_audiobook([item], pr.metadata, pr.export, MasteringOptions(preset="streaming"), tmp_path / "out")
    mp3 = res.episodes[0][1]
    tags = ID3(str(mp3))
    chaps = tags.getall("CHAP")
    assert len(chaps) == 2 and str(chaps[1].sub_frames["TIT2"]) == "Le sujet" and tags.getall("CTOC")
    assert "Chapitres :" in str(tags["COMM::fra"]) and "00:00 Accueil" in str(tags["COMM::fra"])
    assert json.loads(mp3.with_suffix(".chapters.json").read_text("utf-8"))["chapters"][1]["title"] == "Le sujet"
    assert "podcast:chapters" in res.feed.read_text("utf-8")
    assert sf.info(str(res.episodes[0][1])).channels == 2


@needs_ffmpeg
def test_trailer_fallback_and_build(tmp_path, tone_engine, library):
    pr, a, b = make(tmp_path, library, "@Alex: Une première phrase assez longue pour être choisie.\n\n"
                    "@Sam: [excité] Incroyable, cette histoire est vraiment folle !\n\n"
                    "@Alex: Et voici encore une phrase qui pourrait servir.")
    plan = renderer.build_plan(pr, library)
    renderer.Renderer(pr, library).render(plan)
    passages = trailer.candidates(pr, plan)
    assert len(passages) == 3
    chosen = trailer.pick_fallback(passages, 4)
    assert chosen and chosen[0].text.startswith("Incroyable")  # le passage le plus expressif d'abord
    out = trailer.build(passages, tmp_path / "ba.mp3", str(sounds.ensure_builtin("generique")))
    assert out.exists() and audio.duration_of(out) > sum(p.duration for p in passages)


def test_ai_trailer_rewrite_and_chapters():
    client = FakeClient([json.dumps({"passages": [2, 9, 1, 2]})])
    picked = ai.pick_trailer([(1, "E", "a", 10.0), (2, "E", "b", 12.0), (3, "E", "c", 30.0)], client, 30)
    assert picked == [2, 1]
    client = FakeClient([json.dumps({"replique": "« Plus court. »"})])
    assert ai.rewrite_line("Une réplique bien trop longue.", "courte", client, "Alex") == "Plus court."
    script = "@Alex: Bonjour.\n\n@Sam: Salut.\n\n@Alex: Sujet un.\n\n@Sam: Sujet deux."
    client = FakeClient([json.dumps({"chapitres": [{"debut": 3, "titre": "Le sujet"}, {"debut": 1, "titre": "Intro"},
                                                   {"debut": 99, "titre": "x"}]})])
    chapters = ai.propose_chapters(script, client)
    assert chapters == [(1, "Intro"), (3, "Le sujet")]
    new = ai.apply_chapters("[chapitre: Vieux]\n\n" + script, chapters)
    assert "Vieux" not in new and new.startswith("[chapitre: Intro]\n\n@Alex: Bonjour.")
    assert "[chapitre: Le sujet]\n\n@Alex: Sujet un." in new


def test_web_article_extraction():
    html = """<html><head><title>Titre</title><meta property="og:title" content="Le vrai titre"></head><body>
    <nav>Menu Accueil Contact</nav><article><h1>Le vrai titre</h1>
    <p>Premier paragraphe de l'article, assez long pour être gardé dans le texte.</p>
    <p>Second paragraphe de l'article qui explique les choses en détail, lui aussi.</p>
    <p>Pub</p></article><footer>Mentions légales</footer></body></html>"""
    title, text = web.extract_article(html * 3)
    assert title == "Le vrai titre" and "Premier paragraphe" in text and "Menu" not in text and "Pub" not in text


def test_templates_are_valid_scripts(tmp_path, tone_engine, library):
    from podcaststudio.core.textproc import parse_script

    for t in templates.TEMPLATES:
        items = parse_script(t.script, split=True)
        speakers = {i.voice_key for i in items if i.kind == "para"}
        assert speakers <= {n for n, _r, _b in t.hosts}, t.key
        assert any(i.kind == "marker" for i in items) and any(i.kind == "sound" for i in items)


def test_schedule_planning_and_status():
    eps = [Chapter("A", "x", pub_date="2026-11-02"), Chapter("B", "x"), Chapter("C", ""), Chapter("D", "x")]
    assert schedule.plan_dates(eps, date(2026, 10, 1), "week") == 3
    assert [c.pub_date for c in eps] == ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"]
    assert schedule.plan_dates(eps, date(2026, 1, 31), "month", only_missing=False) == 4
    assert [c.pub_date for c in eps][:3] == ["2026-01-31", "2026-02-28", "2026-03-31"]
    assert schedule.status(eps[2], False) == "À écrire" and schedule.status(eps[1], True) == "Produit"
    eps[1].published = True
    assert schedule.status(eps[1], True) == "Publié"
    assert schedule.next_episode(eps, date(2026, 3, 1)).title == "C"


def test_feed_only_due_episodes(tmp_path):
    from datetime import datetime, timezone

    from podcaststudio.core import rss
    from podcaststudio.core.exporter import ExportItem
    from podcaststudio.core.models import BookMetadata

    mp3 = tmp_path / "a.mp3"
    mp3.write_bytes(b"x")
    eps = [(ExportItem("Passé", mp3, pub_date="2026-01-01"), mp3, 10.0),
           (ExportItem("Futur", mp3, pub_date="2027-01-01"), mp3, 10.0)]
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    xml = rss.build_feed(BookMetadata(title="P"), eps, tmp_path, now=now, only_due=True)
    assert "Passé" in xml and "Futur" not in xml
    assert "Futur" in rss.build_feed(BookMetadata(title="P"), eps, tmp_path, now=now)
