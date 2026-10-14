"""Fonctions « studio » héritées du moteur commun : chevauchements, stéréo, sons, prises au micro, réécriture."""

import json

import numpy as np
import soundfile as sf

from contestudio.core import ai, audio, project_io, renderer, sounds
from contestudio.core.models import Chapter, Host, Project, VoiceProfile

from .test_ai import FakeClient


def make(tmp_path, library, text, stereo=True):
    a = library.save(VoiceProfile(name="A", engine="tone"))
    b = library.save(VoiceProfile(name="B", engine="tone"))
    pr = Project(chapters=[Chapter("Épisode", text)], narrator_voice_id=a.id,
                 hosts=[Host("Alex", "host", a.id), Host("Sam", "cohost", b.id)])
    pr.production.stereo = stereo
    pr.production.overlap_reactions = True
    pr.production.announce_chapter_titles = False
    project_io.save_project(pr, tmp_path / "p" / "P.ctsproj")
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


def test_ai_rewrite_and_summary():
    client = FakeClient([json.dumps({"replique": "« Plus doux. »"})])
    assert ai.rewrite_line("Une phrase bien trop agitée.", "douce", client, "Pompon") == "Plus doux."
    assert "dormir" in client.calls[-1][2]["messages"][0]["content"]
    client = FakeClient([json.dumps({"resume": "  Un petit dragon   découvre la nuit. "})])
    assert ai.story_summary("Pompon", "@Pompon: [peur] J'ai peur.", client) == "Un petit dragon découvre la nuit."
