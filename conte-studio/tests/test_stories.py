"""Fonctions des contes : écriture par l'IA adaptée à l'âge, personnages, bruitages et ambiances, histoire du soir,
prénom de l'enfant, couvertures, livret, bibliothèque et histoires d'exemple."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from contestudio.core import audio, booklet, covers, project_io, renderer, sounds, story
from contestudio.core import library as biblio
from contestudio.core.models import VOICE_STYLES, Chapter, Host, Project, VoiceProfile
from contestudio.core.textproc import parse_script, personalize

from .conftest import needs_ffmpeg
from .test_ai import FakeClient


def make(tmp_path, library_, text, **chapter):
    narr = library_.save(VoiceProfile(name="Narrateur", engine="tone"))
    dragon = library_.save(VoiceProfile(name="Dragon", engine="tone"))
    pr = Project(chapters=[Chapter("Le dragon", text, **chapter)], narrator_voice_id=narr.id,
                 hosts=[Host("Dragon", "animal", dragon.id, style="dragon"), Host("{prénom}", "hero", dragon.id,
                                                                                  style="enfant")])
    pr.production.announce_chapter_titles = False
    pr.production.speed = 1.0
    project_io.save_project(pr, tmp_path / "c" / "Contes.ctsproj")
    return pr, narr, dragon


# ---------------------------------------------------------------------------------------
# Texte : ambiances et prénom de l'enfant
# ---------------------------------------------------------------------------------------
def test_ambience_tags_and_child_name():
    text = ("[ambiance: Forêt]\n\nIl était une fois {prénom}. [son: hibou] Puis la pluie. [ambiance: pluie] Ploc."
            "\n\n@{Prénom}: [joyeux] Coucou !\n\n[fin ambiance]\n\n[/ambiance]\n\n[ambiance: aucune]")
    items = parse_script(personalize(text, "Emma"), split=True)
    kinds = [(i.kind, i.source or i.text) for i in items]
    assert kinds == [("ambience", "Forêt"), ("para", "Il était une fois Emma."), ("sound", "hibou"),
                     ("para", "Puis la pluie."), ("ambience", "pluie"), ("para", "Ploc."), ("para", "Coucou !"),
                     ("ambience", ""), ("ambience", ""), ("ambience", "")]
    assert items[6].voice_key == "Emma" and items[6].emotion == "joyeux"
    assert personalize("Bonjour {prénom} !", "") == "Bonjour Lou !"  # prénom par défaut
    assert personalize("{ PRENOM }", "  Léo  ") == "Léo"


def test_host_named_child_placeholder_matches_child_name():
    pr = Project(hosts=[Host("{prénom}", "hero", "v1"), Host("Pompon", "animal", "v2")])
    pr.metadata.child_name = "Emma"
    assert pr.host_by_name("emma").voice_id == "v1"
    assert pr.host_by_name("Pompon").voice_id == "v2"
    pr.metadata.child_name = ""
    assert pr.host_by_name("Lou").voice_id == "v1"


# ---------------------------------------------------------------------------------------
# Sons générés
# ---------------------------------------------------------------------------------------
def test_all_sounds_and_ambiences_are_generated():
    for name in sounds.BUILTIN_LABELS:
        data, sr = audio.read_audio(sounds.ensure_builtin(name))
        assert sr == sounds.SR and len(data) > sr * 0.4 and np.max(np.abs(data)) > 0.3, name
    for name in sounds.AMBIENCE_LABELS:
        data, sr = audio.read_audio(sounds.ensure_ambience(name))
        assert len(data) >= sr * 18, name
        rms = audio.lin_to_db(float(np.sqrt(np.mean(data.astype(np.float64) ** 2))))
        assert abs(rms - sounds.AMBIENCE_RMS_DB) < 1.5, (name, rms)
        # boucle sans coupure : la fin rejoint le début sans saut brutal
        jump = abs(float(data[-1]) - float(data[0]))
        assert jump < 0.2, (name, jump)


def test_sound_names_and_aliases(tmp_path):
    assert sounds.resolve_name("Porte qui grince") == "porte"
    assert sounds.resolve_name("miaou") == "chat" and sounds.resolve_name("Cloche magique") == "cloche_magique"
    assert sounds.resolve_name("inconnu") is None
    assert sounds.ambience_key("Forêt") == "foret" and sounds.ambience_key("feu de cheminée") == "feu"
    assert sounds.ambience_key("pluie douce") == "pluie" and sounds.ambience_key("rien") is None
    assert sounds.resolve("vagues") == sounds.ensure_ambience("mer")  # « [son: vagues] » : un extrait de la mer
    own = tmp_path / "proj"
    (own / "sons").mkdir(parents=True)
    audio.write_audio(own / "sons" / "Jungle.wav", np.zeros(4410, dtype=np.float32), 44100)
    assert sounds.resolve_ambience("jungle", own) == own / "sons" / "Jungle.wav"


def test_lullaby_and_sleep_noise_fade_out():
    lull = sounds.lullaby(40)
    assert abs(len(lull) / sounds.SR - 40) < 0.01
    first, last = np.abs(lull[: sounds.SR * 10]).max(), np.abs(lull[-sounds.SR:]).max()
    assert first > 0.2 and last < first * 0.05  # s'éteint en fondu
    noise = sounds.sleep_noise("pluie", 60)
    n = len(noise)
    level = [float(np.sqrt(np.mean(noise[i:i + n // 6] ** 2))) for i in range(0, n, n // 6)][:6]
    assert all(a > b for a, b in zip(level[1:], level[2:]))  # baisse régulièrement jusqu'au silence
    assert float(np.abs(noise[-100:]).max()) < 1e-3
    assert not sounds.sleep_noise("none", 10).any()


@needs_ffmpeg
def test_pitch_shift_keeps_length():
    sr = 44100
    t = np.arange(sr) / sr
    tone = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

    def freq(x):
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        return np.argmax(spec) * sr / len(x)

    up = audio.pitch_shift(tone, sr, 12)
    down = audio.pitch_shift(tone, sr, -5)
    assert abs(len(up) - sr) < sr * 0.03 and abs(len(down) - sr) < sr * 0.03
    assert abs(freq(up) - 440) < 15 and abs(freq(down) - 220 * 2 ** (-5 / 12)) < 10
    assert audio.pitch_shift(tone, sr, 0) is tone


# ---------------------------------------------------------------------------------------
# Plan de lecture : personnages, histoire du soir, ambiances
# ---------------------------------------------------------------------------------------
def test_character_styles_bedtime_and_child_name_in_plan(tmp_path, tone_engine, library):
    text = "Il était une fois {prénom}.\n\n@Dragon: Bonjour !\n\n@{prénom}: [joyeux] Salut, Dragon !"
    pr, narr, dragon = make(tmp_path, library, text)
    pr.metadata.child_name = "Emma"
    day = renderer.build_plan(pr, library)[0].segments
    assert [s.display for s in day] == ["Il était une fois Emma.", "Bonjour !", "Salut, Dragon !"]
    assert day[0].pitch == 0 and day[1].pitch == VOICE_STYLES["dragon"][1] and day[2].pitch == 3.0
    assert day[1].rate == pytest.approx(VOICE_STYLES["dragon"][2]) and day[1].voice_id == dragon.id
    assert not renderer.build_plan(pr, library)[0].warnings
    pr.chapters[0].bedtime = True
    night = renderer.build_plan(pr, library)[0].segments
    assert night[0].emotion == "calme" and night[2].emotion == "joyeux"  # une émotion écrite est gardée
    assert night[0].rate == pytest.approx(pr.production.bedtime_speed)
    assert night[0].pause_after_ms > day[0].pause_after_ms
    assert night[0].key != day[0].key  # nouvelle synthèse, plus douce
    pr.hosts[0].pitch = -2.0  # réglage fin : remplace la hauteur du style
    assert renderer.build_plan(pr, library)[0].segments[1].pitch == -2.0


def test_ambience_regions_cover_scene(tmp_path, tone_engine, library):
    text = ("[ambiance: forêt]\n\nDans la forêt.\n\n@Dragon: Chut.\n\n[ambiance: pluie]\n\nIl pleut.\n\n"
            "[ambiance: fin]\n\nAu sec.\n\n[ambiance: xyz]\n\nFin.")
    pr, *_ = make(tmp_path, library, text)
    rc = renderer.build_plan(pr, library)[0]
    amb = [Path(s.ambience).name if s.ambience else "" for s in rc.segments]
    assert amb == ["ambiance-foret.wav", "ambiance-foret.wav", "ambiance-pluie.wav", "", ""]
    assert any("xyz" in w for w in rc.warnings)
    timings = [(2.0, 3.0), (3.5, 4.0), (4.5, 5.5), (6.0, 7.0), (7.5, 8.0)]
    regions = rc.ambience_regions(timings, 10.0)
    assert [(a, b, Path(f).name) for a, b, f in regions] == [
        (2.0 - renderer.AMBIENCE_LEAD_S, 4.5, "ambiance-foret.wav"),  # la forêt s'installe avant la 1re phrase
        (4.5 - renderer.AMBIENCE_LEAD_S, 6.0, "ambiance-pluie.wav")]  # et la pluie la remplace en fondu
    assert rc.ambience_regions(timings[:1], 3.5)[0][0] == pytest.approx(2.0 - renderer.AMBIENCE_LEAD_S)
    assert rc.ambience_regions([(0.5, 1.0)], 2.0)[0][0] == 0.0


def test_render_mixes_ambience_bed(tmp_path, tone_engine, library):
    text = "[ambiance: pluie]\n\nIl pleut fort ce soir.\n\nVraiment très fort.\n\n[ambiance: fin]\n\nPuis plus rien."
    pr, *_ = make(tmp_path, library, text)
    pr.production.stereo = False
    plan = renderer.build_plan(pr, library)
    rep = renderer.Renderer(pr, library).render(plan)
    assert not rep.failed_segments
    data, sr = sf.read(str(renderer.chapter_output(pr, plan[0].id)), always_2d=True)
    t = renderer.segment_timings(pr, plan[0])

    def rms(a, b):
        x = data[int(a * sr):int(b * sr), 0]
        return audio.lin_to_db(float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0)

    under = rms(t[0][1] + 0.05, t[1][0] - 0.05)  # pause dans la scène de pluie
    after = rms(t[2][1] + 1.6, len(data) / sr - 0.1)  # silence final, après la fin de l'ambiance
    assert -60 < under < -35 and after < -80
    # changer le niveau des ambiances refait l'assemblage
    old = plan[0].plan_hash
    pr.production.ambience_db = -30
    assert renderer.build_plan(pr, library)[0].plan_hash != old


# ---------------------------------------------------------------------------------------
# Écriture des contes par l'IA
# ---------------------------------------------------------------------------------------
STORY = {"title": "Pompon et la nuit", "summary": "Un petit dragon découvre les étoiles.",
         "characters": [{"name": "Pompon", "description": "petit dragon vert", "kind": "hero", "voice": "aiguë",
                         "gender": "M"},
                        {"name": "Narrateur", "kind": "character"},
                        {"name": "Lili", "description": "une luciole", "kind": "magic", "voice": "aigue"}],
         "paragraphs": [{"speaker": "", "text": "Il était une fois Emma.", "ambiance": "Forêt"},
                        {"speaker": "pompon", "text": "— J'ai peur du noir.", "emotion": "effrayé",
                         "sound": "chouette"},
                        {"speaker": "Lili", "text": "Je brille pour toi.", "sound": "explosion"},
                        {"speaker": "Hibou", "text": "Hou hou.", "ambiance": "pluie"},
                        {"speaker": "narrateur", "text": "Et tout le monde s'endormit.", "ambiance": "fin"},
                        {"text": ""}]}


def test_write_story_and_script():
    client = FakeClient([json.dumps(STORY)])
    req = story.StoryRequest("un dragon qui a peur du noir", age="3-5", minutes=6, tone="douce",
                             moral="on a le droit d'avoir peur", child_name="Emma", bedtime=True)
    st = story.write_story(req, client)
    system = client.calls[-1][2]["messages"][0]["content"]
    assert "3 à 5 ans" in system and "RIEN d'effrayant" in system and "Emma" in system
    assert "on a le droit d'avoir peur" in system and "s'endort" in system
    assert f"{story.target_words(6, '3-5', True)} mots" in system
    assert st.title == "Pompon et la nuit" and st.summary.startswith("Un petit dragon")
    assert [c.name for c in st.characters] == ["Pompon", "Lili", "Hibou"]  # narrateur ignoré, Hibou ajouté
    assert st.paragraphs[1].speaker == "Pompon" and st.paragraphs[1].text == "J'ai peur du noir."
    assert st.paragraphs[1].emotion == "peur" and st.paragraphs[1].sound == "chouette"
    assert st.paragraphs[2].sound == ""  # bruitage inconnu : retiré
    script = story.story_to_script(st)
    assert script.split("\n\n") == [
        "[ambiance: foret]", "Il était une fois Emma.", "@Pompon: [peur] J'ai peur du noir.", "[son: hibou]",
        "@Lili: Je brille pour toi.", "[ambiance: pluie]", "@Hibou: Hou hou.", "[ambiance: fin]",
        "Et tout le monde s'endormit."]
    with pytest.raises(story.AIError):
        story.write_story(story.StoryRequest("  "), FakeClient([]))


def test_long_story_is_written_in_parts():
    part = {"paragraphs": [{"speaker": "", "text": "Suite de l'histoire."}]}
    client = FakeClient([json.dumps(STORY), json.dumps(part), json.dumps(part)])
    req = story.StoryRequest("une aventure", age="9-12", minutes=20, child_name="Léo",
                             characters=[story.StoryCharacter("Pompon", "dragon de la série")],
                             previous=["Pompon à la mer"])
    words = story.target_words(20, "9-12")
    parts = -(-words // story.WORDS_PER_PART)
    client.answers = client.answers[:parts]
    st = story.write_story(req, client)
    chats = [c for c in client.calls if c[1] == "/chat/completions"]
    assert len(chats) == parts >= 2
    first, last = chats[0][2]["messages"], chats[-1][2]["messages"]
    assert "Pompon : dragon de la série" in first[0]["content"] and "Pompon à la mer" in first[0]["content"]
    assert f"partie {parts} sur {parts}" in last[0]["content"] and "Écris la suite" in last[1]["content"]
    assert st.paragraphs[-1].text == "Suite de l'histoire."


def test_target_words_and_age_checks():
    assert story.target_words(10, "3-5") < story.target_words(10, "6-8") < story.target_words(10, "9-12")
    assert story.target_words(10, "6-8", bedtime=True) < story.target_words(10, "6-8")
    assert story.target_words(1, "6-8") == story.target_words(5, "6-8")  # 5 minutes au minimum
    assert story.target_words(60, "6-8") == story.target_words(20, "6-8")
    scary = "@Loup: Je vais te dévorer ! Le fantôme hurla dans le noir."
    assert any("effrayants" in n for n in story.check_for_age(scary, "3-5"))
    assert all("effrayants" not in n for n in story.check_for_age(scary, "9-12"))
    long_sentences = " ".join(["Le petit lapin courait très vite dans la grande prairie verte et fleurie, "
                               "sous le soleil, avec ses amis les écureuils et les oiseaux du matin."] * 4)
    assert any("Phrases longues" in n for n in story.check_for_age(long_sentences, "3-5"))
    assert story.check_for_age("Pompon dort. Il rêve. Il sourit.", "3-5") == []


def test_character_styles_and_voices(library):
    sc = story.StoryCharacter
    assert story.style_for(sc("Pompon", "un petit dragon", "hero", "aigue")) == "enfant"
    assert story.style_for(sc("Grondor", "un énorme dragon", "villain", "grave")) == "dragon"
    assert story.style_for(sc("Mimi", "une petite souris", "animal")) == "petit"
    assert story.style_for(sc("Brun", "un ours", "animal", "grave")) == "geant"
    assert story.style_for(sc("Mamie Rose", "la grand-mère", "parent")) == "ancien"
    assert story.style_for(sc("Clochette", "une fée", "magic")) == "fee"
    assert story.style_for(sc("Bip", "un robot", "character")) == "robot"
    existing = [Host("Pompon", "hero", "vx")]
    eloise = library.save(VoiceProfile(name="Eloise", engine="edge", engine_voice="fr-FR-EloiseNeural"))
    count = len(library.all())
    hosts = story.characters_to_hosts([sc("Pompon"), sc("Lili", "une luciole", "magic", "aigue", "F"),
                                       sc("Grondor", "un dragon", "villain", "grave", "M")], existing, [], library)
    assert [h.name for h in hosts] == ["Lili", "Grondor"]  # Pompon garde sa voix
    assert hosts[0].voice_id == eloise.id  # voix déjà dans la bibliothèque : réutilisée
    assert hosts[1].voice_id == "v_default_henri" and hosts[1].style == "dragon"  # voix par défaut réutilisée
    assert len(library.all()) == count  # aucune voix en double dans la bibliothèque commune
    fresh = story.characters_to_hosts([sc("Zoé", "une petite fille", "hero", "aigue", "F"),
                                       sc("Ariane", "une reine", "character", "normale", "F")], hosts + existing,
                                      [eloise, library.get("v_default_denise"), library.get("v_default_vivienne")],
                                      library)
    # voix d'enfant déjà prise : voix féminine encore libre, puis la suivante (créées dans la bibliothèque)
    assert [library.get(h.voice_id).engine_voice for h in fresh] == ["fr-CA-SylvieNeural", "fr-BE-CharlineNeural"]
    assert len(library.all()) == count + 2


# ---------------------------------------------------------------------------------------
# Couvertures et livret
# ---------------------------------------------------------------------------------------
def test_cover_scene_and_image(tmp_path):
    from PySide6.QtGui import QImage

    assert covers.pick_scene("Capitaine Moustache", "un bateau de pirate sur la mer") == "mer"
    assert covers.pick_scene("Le château du dragon") == "chateau"
    assert covers.pick_scene("Une fusée pour la planète Mars") == "espace"
    assert covers.pick_scene("Léo fait du vélo") == "maison"
    assert covers.is_night(True) and covers.is_night(False, "La lune et les étoiles, la nuit") \
        and not covers.is_night(False, "Le soleil")
    out = covers.generate_cover("Le petit dragon qui avait peur du noir", tmp_path / "c.jpg", "forêt", True,
                                subtitle="Les histoires d'Emma", size=600)
    img = QImage(str(out))
    assert not img.isNull() and img.width() == img.height() == 600
    band = [img.pixelColor(x, y) for x in range(0, 600, 7) for y in range(330, 360, 5)]
    assert sum(c.blue() for c in band) > 1.5 * sum(c.red() for c in band)  # ciel de nuit bleu


def test_booklet_blocks_html_and_pdf(tmp_path):
    text = ("[ambiance: nuit]\n\n%% note pour moi\n\nIl était une fois {prénom}. [son: hibou] La nuit tombe.\n\n"
            "@Pompon: [chuchoté] [lent] J'ai *peur* du noir.\n\n[pause 2s]\n\n# La luciole\n\n"
            "@Lili: [prise: lili.wav] Je brille !\n\n[ambiance: fin]")
    blocks = booklet.script_blocks(text, "Emma")
    assert [(b.kind, b.speaker, b.text) for b in blocks] == [
        ("narration", "", "Il était une fois Emma."), ("sound", "", "Hibou (hou-hou)"),
        ("narration", "", "La nuit tombe."), ("line", "Pompon", "J'ai *peur* du noir."),
        ("heading", "", "La luciole"), ("line", "Lili", "Je brille !")]
    cover = covers.generate_cover("Pompon", tmp_path / "pompon.png", size=200)
    stories = [booklet.BookletStory("Pompon", text, str(cover), "Un dragon.", "On a le droit d'avoir peur.", 245),
               booklet.BookletStory("Deux", "Bonjour.")]
    opts = booklet.BookletOptions("Mes contes", child_name="Emma", font_pt=24)
    html = booklet.render_html(stories, opts)
    assert "data:image/png;base64," in html and "font-size:24pt" in html and "4 min d'écoute" in html
    assert "« J'ai <b>peur</b> du noir. »" in html and "[" not in html.split("<body")[1]
    assert html.count('page-break-before: always') == 2
    h = booklet.write_html(stories, opts, tmp_path / "livret.html")
    pdf = booklet.write_pdf(stories, opts, tmp_path / "livret.pdf")
    assert h.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 5000


@needs_ffmpeg
def test_export_bedtime_tail_story_cover_and_booklet(tmp_path, tone_engine, library):
    from mutagen.id3 import ID3

    from contestudio.core.exporter import ExportItem, export_audiobook
    from contestudio.core.mastering import MasteringOptions

    pr, *_ = make(tmp_path, library, "Il était une fois {prénom}.\n\n@Dragon: Bonne nuit !")
    pr.chapters.append(Chapter("Le jour", "Le soleil brille sur la colline."))
    pr.metadata.title, pr.metadata.child_name = "Contes", "Emma"
    plan = renderer.build_plan(pr, library)
    assert not renderer.Renderer(pr, library).render(plan).failed_segments
    cover = covers.generate_cover("Le dragon", tmp_path / "dragon.png", size=300)
    pr.export.formats = ["mp3_chapters", "mp3_single", "booklet_html", "booklet_pdf"]
    pr.export.lullaby_seconds, pr.export.sleep_noise, pr.export.sleep_noise_minutes = 30, "pluie", 1
    items = [ExportItem(rc.title, renderer.chapter_output(pr, rc.id), rc.kind, id=rc.id, number=i,
                        bedtime=i == 1, cover=str(cover) if i == 1 else "", text=pr.chapters[i - 1].text,
                        description=f"Résumé {i}") for i, rc in enumerate(plan, 1)]
    res = export_audiobook(items, pr.metadata, pr.export, MasteringOptions(preset="streaming"), tmp_path / "out")
    (it1, mp3_1, d1), (it2, mp3_2, d2) = res.episodes
    raw = audio.duration_of(renderer.chapter_output(pr, plan[0].id))
    assert d1 > raw + 30 + 55  # berceuse (30 s) puis une minute de pluie
    assert abs(d2 - audio.duration_of(renderer.chapter_output(pr, plan[1].id))) < 1.0
    data, sr = audio.read_audio(mp3_1)
    end = data[-sr * 2:]
    assert float(np.sqrt(np.mean(end ** 2))) < 0.003  # la pluie s'est éteinte
    t1, t2 = ID3(str(mp3_1)), ID3(str(mp3_2))
    assert t1.getall("APIC") and not t2.getall("APIC")  # couverture propre à la première histoire
    assert "Emma" in str(t1.getall("USLT")[0]) and "{prénom}" not in str(t1.getall("USLT")[0])
    assert str(t1["TCON"]) == "Contes pour enfants"
    assert [b.suffix for b in res.booklets] == [".html", ".pdf"]
    # compilation : la berceuse de la première histoire n'est pas intercalée avant la deuxième
    single = next(f for f in res.files if f.suffix == ".mp3" and f.parent == tmp_path / "out")
    assert audio.duration_of(single) < d1 + d2 - 60
    assert "Il était une fois Emma." in res.booklets[0].read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------
# Bibliothèque et histoires d'exemple
# ---------------------------------------------------------------------------------------
def test_samples_are_valid_and_personalized(tmp_path, library):
    data = biblio.samples_data()
    assert len(data["stories"]) >= 4
    pr = biblio.build_samples(library, "Emma")
    assert len(pr.chapters) == len(data["stories"]) and any(c.bedtime for c in pr.chapters)
    assert any("{prénom}" in c.title for c in pr.chapters)
    assert all(library.get(h.voice_id) is not None for h in pr.hosts)
    plan = renderer.build_plan(pr, library)
    for rc in plan:
        assert not rc.warnings, (rc.title, rc.warnings)  # personnages, bruitages et ambiances connus
        assert "{" not in rc.title
    forest = next(rc for rc in plan if "forêt qui chante" in rc.title)
    assert forest.title.startswith("Emma")
    hero = pr.host_by_name("Emma")
    assert hero is not None and any(s.voice_id == hero.voice_id and s.pitch > 0 for s in forest.segments)
    for c in pr.chapters:
        assert not story.check_for_age(c.text, c.age), c.title


def test_library_collections_favorites_and_install(tmp_path, library):
    target = biblio.install_samples(library, tmp_path / "Contes" / biblio.SAMPLES_FOLDER, "Emma")
    assert target.exists() and (target.parent / "couverture-01.png").exists()
    other, *_ = make(tmp_path / "autre", library, "Bonjour.")
    (tmp_path / "Contes" / "x_fichiers").mkdir()
    (tmp_path / "Contes" / "x_fichiers" / "piege.ctsproj").write_text("{}", encoding="utf-8")
    found = biblio.find_projects([tmp_path / "Contes"], [str(other.path)])
    assert {p.name for p in found} == {target.name, other.path.name}
    cols = biblio.load_collections(found)
    samples = next(c for c in cols if c.title == "Histoires d'exemple")
    assert "Emma" in samples.characters and samples.duration > 60
    first = samples.stories[0]
    assert first.favorite and first.bedtime and first.estimated and first.audio == ""
    assert Path(first.cover).is_file()
    assert biblio.set_favorite(target, samples.stories[1].chapter_id, True)
    again = biblio.load_collections([target])[0]
    assert again.stories[1].favorite
    # histoire exportée : durée réelle et fichier à écouter
    pr = project_io.load_project(target)
    mp3 = tmp_path / "a.wav"
    audio.write_audio(mp3, np.zeros(4410, dtype=np.float32), 44100)
    pr.chapters[0].audio_file, pr.chapters[0].duration = str(mp3), 321.0
    col = biblio.collection_from_project(pr)
    assert col.stories[0].audio == str(mp3) and col.stories[0].duration == 321.0 and not col.stories[0].estimated
    assert biblio.format_minutes(321) == "5 min" and biblio.format_minutes(100, True) == "≈ 2 min"
    from contestudio.ui.kids import kid_stories

    assert [s.title for s in kid_stories([col])] == [pr.chapters[0].title]


def test_name_covers_follow_child_name(tmp_path, library):
    target = biblio.install_samples(library, tmp_path / "ex", "")
    pr = project_io.load_project(target)
    forest = next(c for c in pr.chapters if "{" in c.title)
    other = next(c for c in pr.chapters if "{" not in c.title)
    before = Path(forest.cover_path).read_bytes(), Path(other.cover_path).read_bytes()
    pr.metadata.child_name = "Emma"
    assert biblio.refresh_name_covers(pr) == 1
    assert Path(forest.cover_path).read_bytes() != before[0]  # « Emma et la forêt qui chante »
    assert Path(other.cover_path).read_bytes() == before[1]
    mine = tmp_path / "ma-photo.png"
    covers.generate_cover("Photo", mine, size=100)
    forest.cover_path = str(mine)
    assert biblio.refresh_name_covers(pr) == 0  # une image choisie par l'utilisateur n'est jamais redessinée
