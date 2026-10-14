"""Balises de langue dans le script, catalogue des langues et choix des voix natives."""

from polyglottestudio.core import languages, renderer
from polyglottestudio.core.models import Chapter, Host, Project, VoiceProfile
from polyglottestudio.core.textproc import (languages_in, parse_script, split_language_runs, split_sentences,
                                             strip_language_tags)


def paras(text, **kw):
    return [(i.text, i.lang, i.voice_key, i.joined) for i in parse_script(text, split=True, **kw) if i.kind == "para"]


# ---------------------------------------------------------------------------------------
# Balises de langue
# ---------------------------------------------------------------------------------------
def test_inline_tag_splits_the_sentence():
    assert paras("Le mot [es]gato[/es] veut dire chat.") == [
        ("Le mot", "", None, True), ("gato", "es", None, True), ("veut dire chat.", "", None, False)]


def test_paragraph_prefix_and_block_tags():
    text = "[ja] おはようございます。\n\nRetour au français.\n\n[en-GB]\nGood morning.\n\nHow are you?\n[/en]\n\nFin."
    assert [(t, lang) for t, lang, _k, _j in paras(text)] == [
        ("おはようございます。", "ja"), ("Retour au français.", ""), ("Good morning.", "en-GB"),
        ("How are you?", "en-GB"), ("Fin.", "")]


def test_locale_normalisation_aliases_and_generic_close():
    runs = split_language_runs("[es-mx]Hola[/]. [jp]はい[/jp] [zh-hk]你好[/zh-hk] [langue: pt-br]Olá[/pt]")
    # « . » isolé rattaché au passage précédent ; [jp] → japonais ; [zh-hk] → cantonais de Hong Kong
    assert runs == [("es-MX", "Hola."), ("ja", "はい"), ("zh-HK", "你好"), ("pt-BR", "Olá")]
    assert split_language_runs("Bonjour [es]hola", "fr") == [("fr", "Bonjour"), ("es", "hola")]


def test_dialogue_line_with_tag_and_other_bracket_tags_untouched():
    items = paras("@Maria: [es] [lent] Hola, ¿qué tal?\n\n[son] et [pause] et [joyeux] ne sont pas des langues.")
    assert items[0] == ("Hola, ¿qué tal?", "es", "Maria", False)
    item = next(i for i in parse_script("@Maria: [es] [lent] Hola", split=True) if i.kind == "para")
    assert item.rate == 0.9
    assert items[1][1] == ""


def test_ralenti_tag_and_pause_inside_foreign_passage():
    items = parse_script("[ja] [ralenti] ありがとう\n\nLe mot [en]good[pause 1s]morning[/en].", split=True)
    assert items[0].lang == "ja" and items[0].rate == 0.72
    kinds = [(i.kind, i.lang) for i in items[1:]]
    assert kinds == [("para", ""), ("para", "en"), ("pause", ""), ("para", "en")]


def test_helpers_strip_and_list_languages():
    text = "Le mot [es]gato[/es], puis [ja] ねこ et [es-MX]carro[/es]."
    assert strip_language_tags(text) == "Le mot gato, puis ねこ et carro."
    assert languages_in(text) == ["es", "ja", "es-MX"]


def test_cjk_and_arabic_sentence_split():
    assert split_sentences("你好。我叫王明。你呢？") == ["你好。", "我叫王明。", "你呢？"]
    assert split_sentences("مرحبا. كيف حالك؟ أنا بخير.") == ["مرحبا.", "كيف حالك؟", "أنا بخير."]


# ---------------------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------------------
REQUIRED = ["en-GB", "en-US", "en-AU", "en-IN", "es-ES", "es-MX", "es-AR", "pt-PT", "pt-BR", "de", "it", "nl", "sv",
            "nb", "da", "fi", "pl", "cs", "sk", "hu", "ro", "bg", "el", "hr", "sr", "sl", "uk", "ru", "tr", "ar-SA",
            "ar-EG", "ar-MA", "he", "fa", "hi", "ur", "bn", "ta", "te", "mr", "gu", "pa", "th", "vi", "id", "ms",
            "fil", "zh-CN", "zh-HK", "zh-TW", "ja", "ko", "sw", "am", "zu", "af", "ca", "eu", "gl", "cy", "ga", "is",
            "et", "lv", "lt", "sq", "mk", "ka", "hy", "az", "kk", "uz", "mn", "ne", "km", "lo", "my", "so", "ps", "mt"]


def test_catalog_covers_requested_languages_and_accents():
    assert len(languages.LANGUAGES) >= 75
    for tag in REQUIRED:
        lang = languages.get(tag)
        assert lang is not None, tag
        if "-" in tag:
            assert any(loc == tag for loc, _ in lang.locales), tag
        assert languages.edge_voices_for(lang.code, tag if "-" in tag else ""), tag
        assert languages.sample_sentence(lang.code), tag
    assert languages.get("zh-HK").code == "yue" and languages.get("jp").code == "ja"
    assert languages.get("ja").translit == "romaji" and languages.get("zh").translit == "pinyin"
    assert languages.get("ar").rtl and not languages.get("es").rtl
    assert languages.locale_name("es-MX") == "Espagnol (Mexique)"
    assert languages.get("klingon") is None and not languages.is_language_tag("son")


# ---------------------------------------------------------------------------------------
# Choix des voix natives
# ---------------------------------------------------------------------------------------
def test_native_voices_accent_first_and_gender_alternation():
    vs = languages.native_voices("es", "es-AR", offline="none")
    assert [v.locale for v in vs[:2]] == ["es-AR", "es-AR"] and [v.gender for v in vs[:2]] == ["F", "M"]
    assert {v.locale for v in vs} >= {"es-ES", "es-MX"}
    assert languages.native_voices("en", "en-AU", "M", offline="none")[0].voice == "en-AU-WilliamNeural"
    # les voix « multilingues » viennent après les voix natives classiques
    us = languages.native_voices("en", "en-US", offline="none")
    assert "Multilingual" not in us[0].voice and any(v.multilingual for v in us)


def test_offline_voices_as_fallback_or_preferred():
    ja = languages.native_voices("ja", offline="fallback")
    assert ja[0].engine == "edge" and {v.engine for v in ja} == {"edge", "kokoro", "xtts"}
    pref = languages.native_voices("ja", offline="prefer", installed={"kokoro"})
    assert pref[0].engine == "kokoro" and "xtts" not in {v.engine for v in pref}
    assert all(v.engine == "edge" for v in languages.native_voices("sw", offline="prefer"))  # pas de hors ligne
    assert languages.native_voices("en", "en-GB", offline="prefer", installed={"kokoro"})[0].voice.startswith("b")
    alt = languages.offline_alternative("native:edge:ja-JP-KeitaNeural", {"kokoro"})
    assert alt == "native:kokoro:jm_kumo:ja"
    assert languages.offline_alternative("native:edge:sw-KE-ZuriNeural", {"kokoro", "xtts"}) == ""


def test_live_list_is_authoritative_and_multilingual_fallback():
    from polyglottestudio.core.engines.base import BuiltinVoice

    live = [BuiltinVoice("de-DE-KatjaNeural", "Katja", "de", "F", "de-DE")]
    assert [v.voice for v in languages.native_voices("de", available=live, offline="none")] == ["de-DE-KatjaNeural"]
    none = languages.native_voices("hy", available=live, offline="fallback")
    assert none and all(v.multilingual for v in none)  # langue absente du service : voix multilingues


def test_native_profiles_and_library(library):
    v = library.get("native:edge:es-MX-DaliaNeural")
    assert (v.engine, v.engine_voice, v.language, v.gender) == ("edge", "es-MX-DaliaNeural", "es", "F")
    assert "Mexique" in v.name and library.get("native:edge:es-MX-DaliaNeural") is v
    k = library.get("native:kokoro:jf_alpha:ja")
    assert (k.engine, k.engine_voice, k.language, k.gender) == ("kokoro", "jf_alpha", "ja", "F")
    x = library.get("native:xtts:Ana Florence:ko")
    assert (x.engine, x.engine_voice, x.language) == ("xtts", "Ana Florence", "ko")
    saved = library.save_native("native:edge:ja-JP-NanamiNeural")
    assert saved.id != "native:edge:ja-JP-NanamiNeural" and library.get(saved.id).engine_voice == "ja-JP-NanamiNeural"
    assert languages.pick_voice("ko", gender="M", offline="none") == "native:edge:ko-KR-InJoonNeural"


def make_project(narr_id):
    pr = Project(narrator_voice_id=narr_id)
    pr.metadata.target_language = "es"
    pr.metadata.target_locale = "es-MX"
    pr.production.announce_chapter_titles = False
    return pr


def test_resolver_picks_explanation_native_and_distinct_speaker_voices(library):
    narr = library.save(VoiceProfile(name="Explication", engine="tone", language="fr"))
    pr = make_project(narr.id)
    pr.hosts = [Host("Ana", gender="F"), Host("Luis", gender="M"), Host("Prof", "host", language="fr"),
                Host("Ines", gender="F")]
    text = ("Bonjour. Le mot [es]hola[/es], et en Espagne [es-ES]vale[/es].\n\n@Ana: Hola.\n\n@Luis: ¿Qué tal?\n\n"
            "@Ines: Bien.\n\n@Prof: Très bien.\n\n@Inconnu: [ja] こんにちは\n\n[fr] Fin.")
    pr.chapters = [Chapter("L", text)]
    segs = renderer.build_plan(pr, library)[0].segments
    by = {s.display: (library.get(s.voice_id), s.lang) for s in segs}
    assert by["Bonjour. Le mot"][0].id == narr.id and by["Bonjour. Le mot"][1] == "fr"
    assert by["hola"][0].engine_voice == "es-MX-DaliaNeural" and by["hola"][1] == "es"
    assert by["vale."][0].engine_voice.startswith("es-ES")
    ana, luis, ines = by["Hola."][0], by["¿Qué tal?"][0], by["Bien."][0]
    assert ana.gender == "F" and luis.gender == "M" and ines.gender == "F" and ana.id != ines.id
    assert by["Très bien."][0].id == narr.id  # le professeur parle avec la voix d'explication
    assert by["こんにちは"][0].engine_voice.startswith("ja-JP") and by["Fin."][0].id == narr.id
    # voix choisies dans la page Langues : la première lit les passages balisés
    tone = library.save(VoiceProfile(name="Natif", engine="tone", language="es"))
    pr.language_voices["es"] = [tone.id]
    segs = renderer.build_plan(pr, library)[0].segments
    assert next(s for s in segs if s.display == "hola").voice_id == tone.id
    # une voix choisie pour un intervenant l'emporte
    pr.hosts[0].voice_id = narr.id
    assert next(s for s in renderer.build_plan(pr, library)[0].segments if s.display == "Hola.").voice_id == narr.id


def test_plan_language_speed_and_normalisation(library):
    narr = library.save(VoiceProfile(name="Explication", engine="tone", language="fr"))
    pr = make_project(narr.id)
    pr.production.target_speed = 0.85
    pr.production.slow_rate = 0.6
    pr.chapters = [Chapter("L", "J'ai 3 chats.\n\n[es] Tengo 3 gatos.\n\n[es] [ralenti] Tengo 3 gatos.")]
    segs = renderer.build_plan(pr, library)[0].segments
    assert segs[0].text == "J'ai trois chats." and segs[0].base_speed == 1.0
    assert segs[1].text == "Tengo 3 gatos." and segs[1].base_speed == 0.85  # la voix native lit le nombre
    assert segs[2].rate == 0.6 and segs[1].key != segs[2].key


def test_offline_fallback_when_microsoft_is_unreachable(tmp_path, library, monkeypatch, tone_engine):
    from polyglottestudio.core import engines, project_io
    from polyglottestudio.core.engines.base import EngineError

    narr = library.save(VoiceProfile(name="Explication", engine="tone", language="fr"))
    pr = make_project(narr.id)
    pr.chapters = [Chapter("L", "[ja] こんにちは、元気ですか。")]
    project_io.save_project(pr, tmp_path / "p" / "c.plgproj")
    edge = engines.get_engine("edge")
    monkeypatch.setattr(edge, "synthesize", lambda *a, **k: (_ for _ in ()).throw(EngineError("hors ligne")))
    kokoro = engines.get_engine("kokoro")
    monkeypatch.setattr(kokoro, "synthesize", tone_engine.synthesize)
    monkeypatch.setattr(renderer.VoiceResolver, "installed", lambda self: {"kokoro"})
    plan = renderer.build_plan(pr, library)
    logs = []
    rep = renderer.Renderer(pr, library, renderer.RenderCallbacks(log=logs.append)).render(plan)
    assert not rep.failed_segments and not rep.blocked
    assert any("hors ligne" in m for m in logs)
    assert renderer.read_qc(pr, plan[0].segments[0].key)["fallback"].startswith("Alpha")
