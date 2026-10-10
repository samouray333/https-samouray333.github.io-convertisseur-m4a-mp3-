import sys

import numpy as np
import pytest

from audiolivre.core import audio, project_io, renderer
from audiolivre.core.models import Chapter, Project, VoiceProfile

from .conftest import needs_ffmpeg


def make_project(tmp_path, voice_id, text="Bonjour. Voici un test.\n\n@Marie: Une réplique."):
    pr = Project(chapters=[Chapter(title="Chapitre 1", text=text), Chapter(title="Chapitre 2", text="Fin du livre.")],
                 narrator_voice_id=voice_id)
    pr.metadata.title = "Livre test"
    pr.metadata.author = "Auteur"
    project_io.save_project(pr, tmp_path / "p" / "Livre.alsproj")
    return pr


def test_project_roundtrip(tmp_path):
    pr = Project(chapters=[Chapter(title="A", text="x")])
    pr.metadata.title = "T"
    pr.cast["Marie"] = "v1"
    path = project_io.save_project(pr, tmp_path / "proj.alsproj")
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
    assert [rc.kind for rc in plan] == ["opening", "chapter", "chapter", "closing"]
    ch1 = plan[1]
    assert ch1.segments[0].kind == "title"
    assert ch1.segments[-1].voice_id == marie.id
    keys1 = [s.key for s in ch1.segments]
    pr.production.speed = 1.1
    keys2 = [s.key for s in renderer.build_plan(pr, library)[1].segments]
    assert keys1 != keys2  # le débit change la clé de cache


@needs_ffmpeg
def test_render_assemble_and_export(tmp_path, tone_engine, library):
    from audiolivre.core.exporter import ExportItem, export_audiobook
    from audiolivre.core.ffmpeg import probe
    from audiolivre.core.mastering import MasteringOptions

    v = library.save(VoiceProfile(name="Narrateur", engine="tone"))
    pr = make_project(tmp_path, v.id)
    plan = renderer.build_plan(pr, library)
    rep = renderer.Renderer(pr, library).render(plan)
    assert not rep.failed_segments
    assert all(renderer.chapter_is_current(pr, rc) for rc in plan)
    # Les silences de début/fin de chapitre sont respectés
    data, sr = audio.read_audio(renderer.chapter_output(pr, plan[1].id))
    assert np.max(np.abs(data[: int(sr * 0.9)])) < 1e-4
    # Une modification ne régénère que le chapitre concerné
    pr.chapters[1].text = "Fin modifiée du livre."
    plan2 = renderer.build_plan(pr, library)
    current = [renderer.chapter_is_current(pr, rc) for rc in plan2]
    assert current == [True, True, False, True]

    pr.export.formats = ["m4b", "mp3_chapters", "mp3_single"]
    items = [ExportItem(rc.title, renderer.chapter_output(pr, rc.id), rc.kind) for rc in plan]
    res = export_audiobook(items, pr.metadata, pr.export, MasteringOptions(), tmp_path / "out")
    assert res.acx_ok
    m4b = next(f for f in res.files if f.suffix == ".m4b")
    info = probe(m4b)
    assert len(info["chapters"]) == 4
    mp3s = [f for f in res.files if f.suffix == ".mp3" and "Extrait" not in f.name]
    assert len(mp3s) == 5  # 4 pistes + fichier unique
    assert res.report is not None and res.report.exists()


@needs_ffmpeg
def test_mastering_meets_acx(tmp_path):
    from audiolivre.core.mastering import MasteringOptions, master_file

    sr = 44100
    t = np.arange(sr * 20) / sr
    sig = (0.04 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 0.7 * t) > 0)).astype(np.float32)
    src = tmp_path / "raw.flac"
    audio.write_audio(src, sig, sr)
    stats = master_file(src, tmp_path / "m.wav", MasteringOptions(preset="acx"))
    assert stats.acx_ok, stats.acx_checks()


def test_worker_protocol(tmp_path, library):
    """Le processus moteur (protocole JSON) fonctionne avec l'interpréteur courant."""
    from audiolivre.core import engines
    from audiolivre.core.engines.neural import DummyWorkerEngine

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
    from audiolivre.core.exporter import safe_filename

    assert safe_filename(name) == expected


def test_emotion_changes_key_and_params(tmp_path, tone_engine, library):
    from audiolivre.core.emotions import apply_emotion

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
    from audiolivre.core.engines.neural import DummyWorkerEngine

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
    from audiolivre.core.asr import word_error

    assert word_error("Il revint le 1er mai 1984.", "il revint le premier mai 1984") == 0.0
    assert word_error("Bonjour tout le monde.", "bla bla") > 0.5


def test_srt_and_lrc():
    from audiolivre.core.exporter import split_cues, to_lrc, to_srt
    from audiolivre.core.models import BookMetadata

    cues = [(0.5, 2.0, "Bonjour."), (2.5, 10.0, "Une très longue phrase, " * 8)]
    srt = to_srt(cues)
    assert srt.startswith("1\n00:00:00,500 --> 00:00:02,000\nBonjour.")
    assert len(split_cues(cues)) > 2
    assert "[00:00.50]Bonjour." in to_lrc(cues, "T", BookMetadata())


@needs_ffmpeg
def test_music_mixing(tmp_path):
    from audiolivre.core import ffmpeg
    from audiolivre.core.exporter import add_music
    from audiolivre.core.models import ExportSettings

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
    from audiolivre.core.engines.edge import voice_language

    assert voice_language("en-US-AvaMultilingualNeural", "en-US")[0] == "multi"
    assert voice_language("fr-FR-VivienneMultilingualNeural", "fr-FR") == ("fr", "")
    assert voice_language("en-US-GuyNeural", "en-US") == ("en", "")


def test_credits_text_paragraphs_and_voice(tmp_path, tone_engine, library):
    from audiolivre.core.exporter import credits_text
    from audiolivre.core.models import BookMetadata

    meta = BookMetadata(title="Le Phare", author="Jeanne", narrator="Paul")
    text = credits_text("{title}.\n\n\n\nÉcrit par  {author}.\n\nMerci à {inconnu} {", meta)
    assert text == "Le Phare.\n\nÉcrit par Jeanne.\n\nMerci à {inconnu} {"
    narr = library.save(VoiceProfile(name="Narrateur", engine="tone"))
    annonce = library.save(VoiceProfile(name="Annonce", engine="tone"))
    pr = make_project(tmp_path, narr.id)
    pr.export.opening_credits = "{title}.\n\n[pause 1s]\n\nLu par {narrator}."
    pr.export.credits_voice_id = annonce.id
    plan = renderer.build_plan(pr, library)
    opening, closing = plan[0], plan[-1]
    assert [s.voice_id for s in opening.segments] == [annonce.id, annonce.id]
    assert opening.segments[0].pause_after_ms >= 1000
    assert closing.segments[0].voice_id == annonce.id
    pr.export.credits_voice_id = ""
    assert renderer.build_plan(pr, library)[0].segments[0].voice_id == narr.id
