import sys

import numpy as np
import pytest

from podcaststudio.core import audio, project_io, renderer
from podcaststudio.core.models import Chapter, Project, VoiceProfile

from .conftest import needs_ffmpeg


def make_project(tmp_path, voice_id, text="Bonjour. Voici un test.\n\n@Marie: Une réplique."):
    pr = Project(chapters=[Chapter(title="Premier épisode", text=text),
                           Chapter(title="Deuxième épisode", text="Fin de l'émission.")],
                 narrator_voice_id=voice_id)
    pr.metadata.title = "Podcast test"
    pr.metadata.author = "Auteur"
    project_io.save_project(pr, tmp_path / "p" / "Podcast.pcsproj")
    return pr


def test_project_roundtrip(tmp_path):
    pr = Project(chapters=[Chapter(title="A", text="x")])
    pr.metadata.title = "T"
    pr.cast["Marie"] = "v1"
    path = project_io.save_project(pr, tmp_path / "proj.pcsproj")
    back = project_io.load_project(path)
    assert back.metadata.title == "T"
    assert back.chapters[0].title == "A"
    assert back.cast == {"Marie": "v1"}


def test_plan_voices_and_cache_keys(tmp_path, tone_engine, library):
    narr = library.save(VoiceProfile(name="Narrateur", engine="tone"))
    marie = library.save(VoiceProfile(name="Marie", engine="tone"))
    pr = make_project(tmp_path, narr.id)
    pr.cast["Marie"] = marie.id
    plan = renderer.build_plan(pr, library)
    assert [rc.kind for rc in plan] == ["chapter", "chapter"]  # pas de crédits séparés dans un podcast
    ch1 = plan[0]
    assert ch1.segments[0].kind == "title"
    assert ch1.segments[0].display.startswith("Épisode 1.")
    assert ch1.segments[-1].voice_id == marie.id
    keys1 = [s.key for s in ch1.segments]
    pr.production.speed = 1.1
    keys2 = [s.key for s in renderer.build_plan(pr, library)[0].segments]
    assert keys1 != keys2  # le débit change la clé de cache


def test_host_voice_has_priority(tmp_path, tone_engine, library):
    from podcaststudio.core.models import Host

    narr = library.save(VoiceProfile(name="Principale", engine="tone"))
    old = library.save(VoiceProfile(name="Ancienne", engine="tone"))
    sam = library.save(VoiceProfile(name="Sam", engine="tone"))
    pr = make_project(tmp_path, narr.id, "@sam: Salut !\n\n@Inconnu: Qui suis-je ?")
    pr.cast["Sam"] = old.id
    pr.hosts = [Host("Sam", "cohost", sam.id)]
    pr.chapters[0].number = 12
    pr.chapters[0].episode_type = "full"
    rc = renderer.build_plan(pr, library)[0]
    assert rc.segments[0].display.startswith("Épisode 12.")
    assert rc.segments[1].voice_id == sam.id  # nom insensible à la casse, voix de l'animateur
    assert rc.segments[2].voice_id == narr.id
    assert any("Inconnu" in w for w in rc.warnings)
    pr.chapters[1].episode_type = "trailer"
    assert not renderer.build_plan(pr, library)[1].segments[0].display.startswith("Épisode")
    assert pr.episode_number(pr.chapters[1]) == 1


@needs_ffmpeg
def test_render_assemble_and_export(tmp_path, tone_engine, library):
    from podcaststudio.core.exporter import ExportItem, export_audiobook
    from podcaststudio.core.ffmpeg import probe_duration

    v = library.save(VoiceProfile(name="Narrateur", engine="tone"))
    pr = make_project(tmp_path, v.id)
    plan = renderer.build_plan(pr, library)
    rep = renderer.Renderer(pr, library).render(plan)
    assert not rep.failed_segments
    assert all(renderer.chapter_is_current(pr, rc) for rc in plan)
    # Les silences de début/fin de chapitre sont respectés
    data, sr = audio.read_audio(renderer.chapter_output(pr, plan[1].id))
    assert np.max(np.abs(data[: int(sr * 0.9)])) < 1e-4
    # Une modification ne régénère que l'épisode concerné
    pr.chapters[1].text = "Fin modifiée de l'émission."
    plan2 = renderer.build_plan(pr, library)
    current = [renderer.chapter_is_current(pr, rc) for rc in plan2]
    assert current == [True, False]

    import xml.etree.ElementTree as ET

    from mutagen.id3 import ID3

    from podcaststudio.core.mastering import MasteringOptions as MO

    pr.metadata.media_base_url = "https://exemple.github.io/podcast/"
    pr.metadata.owner_email = "moi@exemple.fr"
    pr.export.formats = ["rss", "mp3_single"]  # le flux impose les MP3 par épisode
    jingle = tmp_path / "jingle.wav"
    audio.write_audio(jingle, (0.2 * np.sin(np.arange(44100 * 2) / 44100 * 2 * np.pi * 440)).astype(np.float32),
                      44100)
    pr.export.intro_music = str(jingle)
    items = [ExportItem(rc.title, renderer.chapter_output(pr, rc.id), rc.kind, id=f"g{i}", number=i,
                        description=f"Notes {i}", pub_date=f"2026-01-0{i}") for i, rc in enumerate(plan, 1)]
    res = export_audiobook(items, pr.metadata, pr.export, MO(preset="streaming"), tmp_path / "out")
    assert res.acx_ok, [(t, s.acx_checks()) for t, s in res.stats]
    episodes = [f for f in res.files if f.suffix == ".mp3" and f.parent.name == "episodes"]
    assert len(episodes) == 2 and len([f for f in res.files if f.suffix == ".mp3"]) == 3
    # jingle d'intro sur chaque épisode (pas seulement le premier)
    raw = [audio.duration_of(renderer.chapter_output(pr, rc.id)) for rc in plan]
    assert all(probe_duration(f) > d + 1.5 for f, d in zip(episodes, raw))
    tags = ID3(str(episodes[1]))
    assert str(tags["TCON"]) == "Podcast" and str(tags["TRCK"]) == "2" and "PCST" in tags
    root = ET.parse(res.feed).getroot()
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    items_xml = root.findall("channel/item")
    assert [i.findtext("title") for i in items_xml] == ["Deuxième épisode", "Premier épisode"]  # récent d'abord
    enc = items_xml[0].find("enclosure")
    assert enc.get("url").startswith("https://exemple.github.io/podcast/episodes/")
    assert int(enc.get("length")) == episodes[1].stat().st_size
    assert items_xml[0].findtext("itunes:episode", namespaces=ns) == "2"
    assert "02 Jan 2026" in items_xml[0].findtext("pubDate")
    assert root.find("channel/itunes:owner/itunes:email", ns).text == "moi@exemple.fr"
    assert res.report is not None and res.report.exists()


@needs_ffmpeg
def test_mastering_meets_acx(tmp_path):
    from podcaststudio.core.mastering import MasteringOptions, master_file

    sr = 44100
    t = np.arange(sr * 20) / sr
    sig = (0.04 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 0.7 * t) > 0)).astype(np.float32)
    src = tmp_path / "raw.flac"
    audio.write_audio(src, sig, sr)
    stats = master_file(src, tmp_path / "m.wav", MasteringOptions(preset="acx"))
    assert stats.acx_ok, stats.acx_checks()


def test_worker_protocol(tmp_path, library):
    """Le processus moteur (protocole JSON) fonctionne avec l'interpréteur courant."""
    from podcaststudio.core import engines
    from podcaststudio.core.engines.neural import DummyWorkerEngine

    eng = DummyWorkerEngine()
    engines.register_engine(eng)
    try:
        v = VoiceProfile(name="Test", engine="dummy")
        out = eng.synthesize("Bonjour tout le monde.", v, tmp_path / "a.wav", "fr", 1.0, 1)
        data, sr = audio.read_audio(out)
        assert len(data) / sr > 0.5
        eng._worker.proc.kill()
        eng._worker.proc.wait()
        out2 = eng.synthesize("Après redémarrage.", v, tmp_path / "b.wav", "fr")
        assert out2.exists()
    finally:
        eng.shutdown()
    assert sys.executable


def test_trim_and_best_window():
    sr = 16000
    sig = np.concatenate([np.zeros(sr), 0.5 * np.ones(sr * 2), np.zeros(sr)]).astype(np.float32)
    trimmed = audio.trim_silence(sig, sr, pad_ms=0)
    assert abs(len(trimmed) / sr - 2.0) < 0.05
    s, e = audio.best_speech_window(np.concatenate([sig, sig]), sr, 2.0)
    assert e - s == 2 * sr


def test_voice_pack_roundtrip(tmp_path, library):
    v = library.save(VoiceProfile(name="Clone", engine="xtts", kind="clone"))
    ref = library.voice_dir(v) / "reference_01.wav"
    audio.write_audio(ref, np.zeros(1600, dtype=np.float32), 16000)
    v.references = ["reference_01.wav"]
    library.save(v)
    pack = library.export_pack(v.id, tmp_path / "voix")
    imported = library.import_pack(pack)
    assert imported.id != v.id
    assert imported.reference_paths()[0].exists()


@pytest.mark.parametrize("name, expected", [("a/b:c?", "abc"), ("CON", "_CON"), ("  titre. ", "titre")])
def test_safe_filename(name, expected):
    from podcaststudio.core.exporter import safe_filename

    assert safe_filename(name) == expected


def test_emotion_changes_key_and_params(tmp_path, tone_engine, library):
    from podcaststudio.core.emotions import apply_emotion

    v = library.save(VoiceProfile(name="N", engine="tone"))
    pr = make_project(tmp_path, v.id, text="[triste]\n\nIl pleuvait.\n\n[neutre]\n\nIl pleuvait.")
    pr.export.include_credits = False
    segs = renderer.build_plan(pr, library)[0].segments
    sad, neutral = segs[1], segs[2]
    assert sad.emotion == "triste" and neutral.emotion == ""
    assert sad.key != neutral.key
    cb = VoiceProfile(name="C", engine="chatterbox", params={"exaggeration": 0.5})
    adj, speed, gain = apply_emotion(cb, "colère")
    assert adj.params["exaggeration"] > 0.5 and speed > 1.0 and gain == 0.0
    assert cb.params["exaggeration"] == 0.5  # la voix d'origine n'est pas modifiée
    _, _, whisper_gain = apply_emotion(cb, "chuchoté")
    assert whisper_gain < 0


def test_worker_convert_and_transcribe(tmp_path):
    from podcaststudio.core.engines.neural import DummyWorkerEngine

    eng = DummyWorkerEngine()
    try:
        w = eng._ensure()
        src = tmp_path / "src.wav"
        audio.write_audio(src, np.zeros(1600, dtype=np.float32), 16000, "PCM_16")
        w.request("convert", source=str(src), refs=[str(src)], out=str(tmp_path / "out.wav"))
        assert (tmp_path / "out.wav").exists()
        assert w.request("transcribe", path=str(src), expected="bonjour")["text"] == "bonjour"
    finally:
        eng.shutdown()


def test_word_error():
    from podcaststudio.core.asr import word_error

    assert word_error("Il revint le 1er mai 1984.", "il revint le premier mai 1984") == 0.0
    assert word_error("Bonjour tout le monde.", "bla bla") > 0.5


def test_srt_and_lrc():
    from podcaststudio.core.exporter import split_cues, to_lrc, to_srt
    from podcaststudio.core.models import BookMetadata

    cues = [(0.5, 2.0, "Bonjour."), (2.5, 10.0, "Une très longue phrase, " * 8)]
    srt = to_srt(cues)
    assert srt.startswith("1\n00:00:00,500 --> 00:00:02,000\nBonjour.")
    assert len(split_cues(cues)) > 2
    assert "[00:00.50]Bonjour." in to_lrc(cues, "T", BookMetadata())


@needs_ffmpeg
def test_music_mixing(tmp_path):
    from podcaststudio.core import ffmpeg
    from podcaststudio.core.exporter import add_music
    from podcaststudio.core.models import ExportSettings

    sr = 44100
    t = np.arange(sr * 4) / sr
    voice = tmp_path / "v.flac"
    audio.write_audio(voice, (0.1 * np.sin(2 * np.pi * 200 * t)).astype(np.float32), sr)
    music = tmp_path / "m.wav"
    ffmpeg.run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=5", str(music)])
    st = ExportSettings(intro_music=str(music), outro_music=str(music), background_music=str(music))
    out, offset = add_music(voice, tmp_path / "out.wav", st, "chapter", first=True, last=True)
    assert offset > 4.5
    assert audio.duration_of(out) > 4 + 4.5 + 4
    same, off2 = add_music(voice, tmp_path / "o2.wav", ExportSettings(), "chapter", True, True)
    assert same == voice and off2 == 0.0


def test_dialogue_voice_inside_paragraphs(tmp_path, tone_engine, library):
    narr = library.save(VoiceProfile(name="Narrateur", engine="tone"))
    dlg = library.save(VoiceProfile(name="Dialogues", engine="tone"))
    text = "Marie se retourna et dit : « Qui est là ? »\n\n— Moi, répondit Paul."
    pr = make_project(tmp_path, narr.id, text=text)
    pr.export.include_credits = False
    pr.production.announce_chapter_titles = False
    pr.production.detect_dialogues = True
    pr.production.dialogue_voice_id = dlg.id
    pr.production.natural_pauses = False
    segs = renderer.build_plan(pr, library)[0].segments
    assert [(s.display, s.voice_id) for s in segs] == [
        ("Marie se retourna et dit :", narr.id), ("Qui est là ?", dlg.id),
        ("Moi,", dlg.id), ("répondit Paul.", narr.id)]
    assert segs[0].pause_after_ms == pr.production.pause_sentence_ms
    assert segs[1].pause_after_ms == pr.production.pause_paragraph_ms
    # Même voix pour le récit et les dialogues : un seul passage par paragraphe, comme avant
    pr.production.dialogue_voice_id = ""
    segs = renderer.build_plan(pr, library)[0].segments
    assert [s.display for s in segs] == ["Marie se retourna et dit : Qui est là ?", "Moi, répondit Paul."]


def test_edge_multilingual_voices_listed_for_french():
    from podcaststudio.core.engines.edge import voice_language

    assert voice_language("en-US-AvaMultilingualNeural", "en-US")[0] == "multi"
    assert voice_language("fr-FR-VivienneMultilingualNeural", "fr-FR") == ("fr", "")
    assert voice_language("en-US-GuyNeural", "en-US") == ("en", "")


def test_credits_text_paragraphs_and_voice(tmp_path, tone_engine, library):
    from podcaststudio.core.exporter import credits_text
    from podcaststudio.core.models import BookMetadata

    meta = BookMetadata(title="Le Phare", author="Jeanne", narrator="Paul")
    text = credits_text("{title}.\n\n\n\nÉcrit par  {author}.\n\nMerci à {inconnu} {", meta)
    assert text == "Le Phare.\n\nÉcrit par Jeanne.\n\nMerci à {inconnu} {"
    narr = library.save(VoiceProfile(name="Narrateur", engine="tone"))
    annonce = library.save(VoiceProfile(name="Annonce", engine="tone"))
    pr = make_project(tmp_path, narr.id)
    pr.export.include_credits = True
    pr.export.opening_credits = "{title}.\n\n[pause 1s]\n\nLu par {narrator}."
    pr.export.credits_voice_id = annonce.id
    plan = renderer.build_plan(pr, library)
    opening, closing = plan[0], plan[-1]
    assert [s.voice_id for s in opening.segments] == [annonce.id, annonce.id]
    assert opening.segments[0].pause_after_ms >= 1000
    assert closing.segments[0].voice_id == annonce.id
    pr.export.credits_voice_id = ""
    assert renderer.build_plan(pr, library)[0].segments[0].voice_id == narr.id


def test_edge_refusal_stops_quickly(tmp_path, monkeypatch):
    import edge_tts

    from podcaststudio.core.engines import ServiceBlocked
    from podcaststudio.core.engines import edge as edge_mod

    calls = []

    class Refused(Exception):
        status = 403

    class FakeCommunicate:
        def __init__(self, *a, **k):
            calls.append(a)

        async def save(self, path, meta=None):
            raise Refused("403, message='Invalid response status'")

    monkeypatch.setattr(edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.setattr(edge_mod.time, "sleep", lambda s: None)
    voice = VoiceProfile(name="Denise", engine="edge", engine_voice="fr-FR-DeniseNeural")
    edge_mod._endpoint.update(current="legacy", restored=True)
    import edge_tts.communicate as cm

    try:
        with pytest.raises(ServiceBlocked) as err:
            edge_mod.EdgeEngine().synthesize("Bonjour.", voice, tmp_path / "x.mp3", "fr")
        assert "api.msedgeservices.com" in cm.WSS_URL  # bascule sur la nouvelle adresse de Microsoft
        assert len(calls) == 3 and "403" in str(err.value) and "hors ligne" in str(err.value)
    finally:
        edge_mod.use_endpoint("legacy")


def test_edge_switches_to_new_endpoint(tmp_path, monkeypatch):
    import edge_tts
    import edge_tts.communicate as cm

    from podcaststudio.core.engines import edge as edge_mod

    class Refused(Exception):
        status = 403

    class FakeCommunicate:
        def __init__(self, *a, **k):
            pass

        async def save(self, path, meta=None):
            if "msedgeservices" not in cm.WSS_URL:
                raise Refused("403")
            Path(path).write_bytes(b"ID3audio")

    from pathlib import Path

    monkeypatch.setattr(edge_tts, "Communicate", FakeCommunicate)
    edge_mod._endpoint.update(current="legacy", restored=True)
    try:
        voice = VoiceProfile(name="Denise", engine="edge", engine_voice="fr-FR-DeniseNeural")
        out = edge_mod.EdgeEngine().synthesize("Bonjour.", voice, tmp_path / "x.mp3", "fr")
        assert out.exists() and edge_mod._endpoint["current"] == "new"
    finally:
        edge_mod.use_endpoint("legacy")


@needs_ffmpeg
def test_blocked_service_stops_production(tmp_path, library):
    from podcaststudio.core import engines
    from podcaststudio.core.engines import ServiceBlocked
    from podcaststudio.selftest import make_tone_engine

    base = make_tone_engine()
    calls = []

    class Blocked(type(base)):
        info = type(base).info.__class__(**{**type(base).info.__dict__, "id": "blocked", "name": "Bloqué"})

        def synthesize(self, *a, **k):
            calls.append(1)
            raise ServiceBlocked("Le service refuse les demandes (erreur 403).")

    engines.register_engine(Blocked())
    v = library.save(VoiceProfile(name="B", engine="blocked"))
    text = "\n\n".join(f"Paragraphe numéro {i} du livre." for i in range(12))
    pr = make_project(tmp_path, v.id, text=text)
    pr.export.include_credits = False
    logs = []
    rep = renderer.Renderer(pr, library, renderer.RenderCallbacks(log=logs.append)).render(
        renderer.build_plan(pr, library))
    assert rep.blocked and rep.cancelled
    assert len(calls) <= 3  # arrêt immédiat au lieu de 12 passages × 4 essais
    assert any(m.startswith("Production interrompue") for m in logs)


def test_natural_pauses(tmp_path, tone_engine, library):
    narr = library.save(VoiceProfile(name="Narrateur", engine="tone"))
    paul = library.save(VoiceProfile(name="Paul", engine="tone"))
    text = ("Il hésita longuement devant la porte close...\n\nQuelqu'un était-il resté dans la maison ?\n\n"
            "* * *\n\nLe lendemain matin, le soleil brillait sur toute la vallée endormie.\n\n@Paul: Bonjour.\n\n"
            "Fin du chapitre, après une longue journée de marche dans les collines.")
    pr = make_project(tmp_path, narr.id, text=text)
    pr.cast["Paul"] = paul.id
    pr.export.include_credits = False
    pr.production.announce_chapter_titles = False
    base = pr.production.pause_paragraph_ms
    segs = renderer.build_plan(pr, library)[0].segments
    assert [s.display for s in segs][2] == "Le lendemain matin, le soleil brillait sur toute la vallée endormie."
    assert segs[0].pause_after_ms > base * 1.35  # « ... » : pause de suspense
    assert segs[1].pause_after_ms >= 2000  # « * * * » : changement de scène, sans lire les étoiles
    assert segs[2].pause_after_ms >= int(base * 0.88) + renderer.VOICE_CHANGE_MS  # respiration avant Paul
    assert segs[3].pause_after_ms < base + renderer.VOICE_CHANGE_MS  # réplique courte
    again = renderer.build_plan(pr, library)[0].segments
    assert [s.pause_after_ms for s in again] == [s.pause_after_ms for s in segs]  # stable d'une fois à l'autre
    pr.production.natural_pauses = False
    flat = renderer.build_plan(pr, library)[0].segments
    assert flat[0].pause_after_ms == base and flat[1].pause_after_ms == base + 2000


def test_rate_emphasis_and_breaths(tmp_path, tone_engine, library, monkeypatch):
    import json as _json

    from podcaststudio.core import engines

    calls = []
    original = tone_engine.synthesize

    def with_words(text, voice, out_path, language, speed=1.0, seed=None):
        calls.append((text, round(speed, 3)))
        target = original(text, voice, out_path, language, speed, seed)
        words = text.split()
        step = audio.duration_of(target) / max(1, len(words))
        with open(engines.words_path(target), "w", encoding="utf-8") as fh:
            for i, w in enumerate(words):
                fh.write(_json.dumps({"type": "WordBoundary", "offset": int(i * step * 1e7),
                                      "duration": int(step * 0.9 * 1e7), "text": w.strip(".,!")}) + "\n")
        return target

    monkeypatch.setattr(tone_engine, "synthesize", with_words)
    narr = library.save(VoiceProfile(name="Narrateur", engine="tone"))
    text = ("[lent] Il ne reviendrait *jamais* dans cette maison abandonnée.\n\n"
            "[rapide] Alors il courut.\n\nLe soir tombait doucement sur la ville silencieuse.")
    pr = make_project(tmp_path, narr.id, text=text)
    pr.export.include_credits = False
    pr.production.announce_chapter_titles = False
    pr.production.breaths = "natural"
    plan = renderer.build_plan(pr, library)
    segs = plan[0].segments
    assert [s.rate for s in segs] == [0.9, 1.1, 1.0]
    assert segs[0].emphasis == ["jamais"] and "*" not in segs[0].text
    plain = renderer.build_plan(make_project(tmp_path / "b", narr.id, text=text.replace("*", "")), library)
    assert plain[0].segments[0].key != segs[0].key  # la mise en valeur change le passage

    r = renderer.Renderer(pr, library)
    path = r.synth_segment(segs[0])
    assert calls[-1][1] == 0.9  # débit lent transmis au moteur
    stressed, _ = audio.read_audio(path)
    flat, _ = audio.read_audio(r.synth_segment(plain[0].segments[0]))
    assert len(stressed) > len(flat) + int(renderer.SR * 0.04)  # court temps avant le mot mis en valeur

    report = r.render(plan)
    assert not report.failed_segments
    data, sr = audio.read_audio(renderer.chapter_output(pr, plan[0].id))
    manifest = _json.loads(renderer.chapter_manifest(pr, plan[0].id).read_text("utf-8"))
    gaps = [data[int(a[1] * sr):int(b[0] * sr)] for a, b in zip(manifest["timings"], manifest["timings"][1:])]
    assert any(np.max(np.abs(g)) > 1e-3 for g in gaps)  # au moins une respiration
    assert all(np.max(np.abs(g)) < 0.1 for g in gaps)  # toujours discrète
    pr.production.breaths = "off"
    assert not renderer.chapter_is_current(pr, renderer.build_plan(pr, library)[0])


def test_clone_base_can_be_offline(tmp_path, monkeypatch):
    from podcaststudio.config import settings
    from podcaststudio.core.engines import EngineError, installer
    from podcaststudio.core.engines.neural import FastCloneEngine, fastclone_base

    v = VoiceProfile(name="Moi", engine="fastclone", kind="clone", gender="M", language="fr")
    assert fastclone_base(v, "fr") == "fr-FR-HenriNeural"
    key_online = renderer.segment_key("Bonjour.", v, "fr", 1.0, True)
    settings().set("clone_base", "kokoro")
    try:
        assert fastclone_base(v, "fr") == "kokoro:ff_siwis"
        assert renderer.segment_key("Bonjour.", v, "fr", 1.0, True) != key_online  # cache distinct
        v.engine_voice = "fr-FR-DeniseNeural"  # choix propre à la voix : prioritaire
        assert fastclone_base(v, "fr") == "fr-FR-DeniseNeural"
        v.engine_voice = ""
        monkeypatch.setattr(installer, "is_installed", lambda env: False)
        eng = FastCloneEngine()
        monkeypatch.setattr(eng, "_convert_args", lambda voice, params: {"refs": ["x.wav"]})
        with pytest.raises(EngineError, match="pas installé"):
            eng.synthesize("Bonjour.", v, tmp_path / "o.wav", "fr")
    finally:
        settings().set("clone_base", "microsoft")
