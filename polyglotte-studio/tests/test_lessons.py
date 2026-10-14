"""Exercices audio, répétition espacée, supports écrits (HTML, flashcards, Anki), assistant DeepSeek et export."""

import csv
import datetime as dt
import json

from polyglottestudio.core import course, handouts, lang_ai, project_io, renderer, srs
from polyglottestudio.core.models import REVIEW_STEPS, Chapter, Project, QuizQuestion, VocabItem, VoiceProfile

from .conftest import needs_ffmpeg
from .test_ai import FakeClient

D0 = dt.date(2026, 10, 1)


def lesson(**kw):
    ch = Chapter("Au café", "@Maria: [es] Un café, por favor.\nUn café, s'il vous plaît.", module="Module 1",
                 vocab=[VocabItem("el café", "le café", example="Me gusta el café.", example_translation="J'aime le café."),
                        VocabItem("la leche", "le lait"),
                        VocabItem("¿Cuánto cuesta?", "Combien ça coûte ?", kind="phrase")],
                 questions=[QuizQuestion("Que commande Maria ?", answer="Un café")],
                 quiz=[QuizQuestion("« Le lait » ?", ["la leche", "el café"], "la leche", "Leche = lait.")],
                 summary="Café se dit café.", **kw)
    pr = Project(chapters=[ch])
    pr.metadata.target_language = "es"
    pr.metadata.title = "Espagnol A1"
    return pr, ch


# ---------------------------------------------------------------------------------------
# Script des exercices
# ---------------------------------------------------------------------------------------
def test_lesson_script_sections_and_exercises():
    pr, ch = lesson()
    pr.production.exercises = ["repeat", "slow_normal", "translation", "dictation", "comprehension"]
    names = [n for n, _t in course.lesson_sections(pr, ch)]
    assert names == course.SECTION_ORDER
    script = course.lesson_script(pr, ch)
    # écoutez puis répétez : le mot, un silence, le mot, la traduction
    assert "[es] el café\n\n[pause " in script and "ms]\n\n[es] el café\n\nle café." in script
    # lecture lente puis normale des phrases utiles
    assert "[es] [ralenti] ¿Cuánto cuesta?\n\n[pause" in script
    # traduction différée
    assert "Comment dit-on : le lait ?\n\n[pause 3500ms]\n\n[es] la leche" in script
    assert "Dites-le en espagnol" in script and "# Dictée" in script and "Phrase 1." in script
    assert "Question 1. Que commande Maria ?\n\n[pause 6000ms]\n\nRéponse : Un café." in script
    assert "La bonne réponse est A : la leche. Leche = lait." in script
    items = [i for i in __import__("polyglottestudio.core.textproc", fromlist=["x"]).parse_script(script, split=True)
             if i.kind == "para"]
    assert {i.lang for i in items} == {"", "es"}


def test_lesson_specific_exercises_accent_and_long_repeat_pause():
    pr, ch = lesson(exercises=["repeat"], target_locale="es-AR")
    pr.production.include_quiz = False
    script = course.lesson_script(pr, ch)
    assert "[es-AR] el café" in script and "Comment dit-on" not in script and "# Quiz" not in script
    from polyglottestudio.core import languages

    assert languages.repeat_pause_ms("ありがとうございます", "ja") > languages.repeat_pause_ms("gato", "es") >= 1500


def test_instructions_in_explanation_language_and_ai_translation():
    pr, ch = lesson()
    pr.metadata.language = "en"
    script = course.lesson_script(pr, ch)
    assert "# Vocabulary" in script and "Say it in Spanish" in script and "Lesson" not in script
    pr.metadata.language = "ja"  # consignes non intégrées : anglais tant qu'elles ne sont pas traduites
    assert "# Vocabulary" in course.lesson_script(pr, ch)
    client = FakeClient([json.dumps({k: v.replace("Vocabulary", "語彙") for k, v in course.INSTRUCTIONS["en"].items()}
                                    | {"how_say": "sans le paramètre"})])
    tr = lang_ai.translate_instructions(client, "ja")
    assert tr["vocab_title"] == "語彙" and "how_say" not in tr  # traduction sans {text} refusée
    pr.instructions = tr
    assert "# 語彙" in course.lesson_script(pr, ch)


def test_rendered_plan_announces_module_and_lesson(library, tone_engine):
    pr, ch = lesson()
    narr = library.save(VoiceProfile(name="Explication", engine="tone", language="fr"))
    pr.narrator_voice_id = narr.id
    tone = library.save(VoiceProfile(name="Natif", engine="tone", language="es"))
    pr.language_voices["es"] = [tone.id]
    segs = renderer.build_plan(pr, library)[0].segments
    assert segs[0].display == "Module 1." and segs[1].display == "Leçon 1. Au café."
    assert {s.voice_id for s in segs if s.lang == "es"} == {tone.id}
    assert [s.mark for s in segs if s.mark][:2] == ["Vocabulaire", "Phrases utiles"]


# ---------------------------------------------------------------------------------------
# Répétition espacée
# ---------------------------------------------------------------------------------------
def test_spaced_repetition_schedule():
    pr, ch = lesson()
    assert srs.mark_studied(pr, ch, D0) == 3 and srs.mark_studied(pr, ch, D0) == 0
    assert not srs.due_items(pr, D0)
    day = D0
    for step, gap in enumerate(REVIEW_STEPS):
        day = day + dt.timedelta(days=gap) if step else D0 + dt.timedelta(days=1)
        due = srs.due_items(pr, day)
        assert len(due) == 3 and all(s.step == step for s in due), (step, day)
        srs.complete_session(pr, day, failed={ch.vocab[2].id} if step == 1 else None)
        if step == 1:  # raté : revient le lendemain
            failed = pr.reviews[ch.vocab[2].id]
            assert failed.step == 0 and failed.due == (day + dt.timedelta(days=1)).isoformat()
            failed.step, failed.due = 2, pr.reviews[ch.vocab[0].id].due  # on le remet au même rythme
    assert all(s.learned for s in pr.reviews.values()) and srs.mastery(pr) == 1.0


def test_forecast_overdue_and_review_session_script():
    pr, ch = lesson()
    srs.mark_studied(pr, ch, D0)
    fc = srs.forecast(pr, D0, 30)
    assert [(d - D0).days for d in fc] == [1, 4, 11, 25]  # J+1, puis +3, +7, +14
    late = D0 + dt.timedelta(days=5)
    assert len(srs.due_items(pr, late)) == 3 and not srs.due_items(pr, late, include_overdue=False)
    session = srs.review_chapter(pr, D0 + dt.timedelta(days=1))
    assert srs.is_review_id(session.id) and "(3)" in session.title
    assert "3 mots et phrases" in session.text and "Comment dit-on : le café ?" in session.text
    assert session.text.count("[es] el café") == 2 and session.text.rstrip().endswith("prochaine séance !")
    assert len(srs.planned_sessions(pr, 30, D0)) == 4
    p = srs.progress(pr, D0)
    assert (p.total, p.scheduled, p.lessons_studied) == (3, 3, 1)
    ch.vocab.pop()
    assert srs.prune(pr) == 1


# ---------------------------------------------------------------------------------------
# Supports écrits
# ---------------------------------------------------------------------------------------
def test_handout_flashcards_and_anki(tmp_path):
    pr, ch = lesson()
    pr.metadata.target_language = "ja"
    ch.vocab.append(VocabItem("ありがとう", "merci", "arigatō", favorite=True))
    ch.exercises = ["translation", "dictation"]
    html = handouts.write_handout(pr, tmp_path / "s.html").read_text("utf-8")
    assert "Prononciation" in html and "arigatō" in html and "Japonais" in html
    assert "Traduction différée — réponses" in html and "Dictée — corrigé" in html and "Un café" in html
    assert "[es]" not in html and "Maria : Un café, por favor." in html and "Glossaire" in html
    cards = handouts.write_flashcards(pr, tmp_path / "f.html").read_text("utf-8")
    assert cards.count('class="card front"') == 4 and cards.count('class="page"') == 2
    fav = handouts.flashcards_html(pr, [(c, v) for c, v in pr.all_vocab() if v.favorite])
    assert fav.count('class="card front"') == 1

    def fake_audio(_ch, it, target):
        if it.term == "la leche":
            raise RuntimeError("réseau")
        target.write_bytes(b"ID3")
        return target

    res = handouts.write_anki(pr, tmp_path / "anki", fake_audio)
    assert (res.cards, res.audio) == (4, 3) and len(res.errors) == 1
    lines = res.csv.read_text("utf-8").splitlines()
    assert lines[0] == "#separator:Semicolon" and lines[3] == "#tags column:7"
    rows = list(csv.reader(lines[4:], delimiter=";"))
    assert rows[0][0].startswith("el café [sound:polyglotte_") and rows[0][5].startswith("[sound:")
    assert rows[1][5] == "" and "favori" in rows[-1][6] and "ja" in rows[-1][6].split()
    assert (tmp_path / "anki" / "collection.media" / handouts.anki_media_name(ch.vocab[0])).exists()


# ---------------------------------------------------------------------------------------
# Assistant DeepSeek
# ---------------------------------------------------------------------------------------
LESSON_JSON = {
    "titre": "Commander au café", "description": "Commander une boisson.",
    "vocabulaire": [{"mot": "el café", "traduction": "le café", "exemple": "Un café, por favor.",
                     "exemple_traduction": "Un café, s'il vous plaît."}, {"mot": "[x] el té", "traduction": "le thé"}],
    "phrases": [{"phrase": "¿Algo más?", "traduction": "Autre chose ?"}],
    "intervenants": [{"nom": "Lucía", "sexe": "F"}, {"nom": "Marco", "sexe": "M"}],
    "script": "```\n# Dialogue\n\n@Lucía: Hola, un café.\nBonjour, un café.\n\n@Marco: [es] Claro.\n```",
    "questions": [{"question": "Que veut Lucía ?", "reponse": "Un café"}],
    "quiz": [{"question": "Thé ?", "choix": ["el té", "el café"], "reponse": "el té", "explication": "Té."}],
    "resume": "On commande avec « un café, por favor ».",
}


def test_generate_and_apply_lesson():
    pr, ch = lesson()
    pr.metadata.target_locale = "es-MX"
    client = FakeClient([json.dumps(LESSON_JSON)])
    content = lang_ai.generate_lesson(client, pr, ch, "Au café", ["vocabulary", "phrases", "dialogue"])
    system = next(c for c in client.calls if c[1] == "/chat/completions")[2]["messages"][0]["content"]
    assert "[es-MX]" in system and "Au café" in system and "A1" in system
    assert "Mots déjà étudiés" not in system  # seuls les mots des autres leçons sont rappelés
    assert [v.term for v in content.vocab] == ["el café", "(x) el té", "¿Algo más?"]
    assert content.vocab[2].kind == "phrase"
    assert content.script.startswith("# Dialogue") and "@Lucía: [es-MX] Hola, un café." in content.script
    assert "@Marco: [es] Claro." in content.script
    lang_ai.apply_lesson(pr, ch, content, replace=True, theme="Au café")
    assert ch.title == "Commander au café" and ch.theme == "Au café" and len(ch.quiz) == 1
    assert [(h.name, h.gender, h.language) for h in pr.hosts] == [("Lucía", "F", "es"), ("Marco", "M", "es")]
    assert ch.questions[0].answer == "Un café" and ch.summary.startswith("On commande")


def test_course_plan_and_transliterations():
    client = FakeClient([json.dumps({"modules": [
        {"titre": "Premiers pas", "lecons": [{"titre": "Se présenter", "theme": "Se présenter"}, "Les chiffres"]},
        {"titre": "", "lecons": ["x"]}]})])
    plan = lang_ai.course_plan(client, "ko", "fr", "A1", 1, 2)
    assert plan == [("Premiers pas", [("Se présenter", "Se présenter"), ("Les chiffres", "Les chiffres")])]
    pr = Project()
    added = lang_ai.apply_plan(pr, plan)
    assert [c.module for c in added] == ["Module 1 : Premiers pas"] * 2
    items = [VocabItem("안녕하세요"), VocabItem("감사합니다", translit="déjà")]
    client = FakeClient([json.dumps({"translit": [{"n": 1, "translit": "annyeonghaseyo"}]})])
    assert lang_ai.fill_transliterations(client, items, "ko") == 1 and items[0].translit == "annyeonghaseyo"
    assert lang_ai.fill_transliterations(client, [VocabItem("hola")], "es") == 0  # écriture latine


def test_project_roundtrip_reviews(tmp_path):
    pr, ch = lesson()
    srs.mark_studied(pr, ch, D0)
    pr.instructions = {"vocab_title": "X"}
    back = project_io.load_project(project_io.save_project(pr, tmp_path / "c.plgproj"))
    st = back.reviews[ch.vocab[0].id]
    assert st.due == "2026-10-02" and back.studied[ch.id] == "2026-10-01" and back.instructions == {"vocab_title": "X"}


# ---------------------------------------------------------------------------------------
# Export complet (voix de test : pas de réseau)
# ---------------------------------------------------------------------------------------
@needs_ffmpeg
def test_full_export_with_reviews_and_written_materials(tmp_path, library, tone_engine, monkeypatch):
    from mutagen.id3 import ID3

    from polyglottestudio.ui.pages.export import run_export
    from polyglottestudio.core.mastering import MasteringOptions

    pr, ch = lesson()
    narr = library.save(VoiceProfile(name="Explication", engine="tone", language="fr"))
    native = library.save(VoiceProfile(name="Natif", engine="tone", language="es"))
    pr.narrator_voice_id = narr.id
    pr.language_voices["es"] = [native.id]
    pr.production.exercises = ["repeat"]
    pr.production.include_quiz = pr.production.include_summary = False
    pr.cast["Maria"] = native.id
    project_io.save_project(pr, tmp_path / "p" / "c.plgproj")
    srs.mark_studied(pr, ch, srs.today())
    plan = renderer.build_plan(pr, library)
    assert not renderer.Renderer(pr, library).render(plan).failed_segments
    from polyglottestudio.core.exporter import ExportItem

    rc = plan[0]
    items = [ExportItem(rc.title, renderer.chapter_output(pr, rc.id), module=ch.module, module_index=1, lesson=1,
                        chapters=rc.chapter_marks(renderer.segment_timings(pr, rc)))]
    pr.export.formats = ["mp3_modules", "reviews", "handout", "flashcards", "anki"]
    pr.export.review_days = 5
    monkeypatch.setattr("polyglottestudio.core.exporter.word_audio",
                        lambda p, lib, c, it, target: (target.write_bytes(b"ID3"), target)[1])
    res = run_export(pr, library, items, MasteringOptions(preset="streaming"), tmp_path / "out")
    names = sorted(f.name for f in res.files)
    assert "01 - Au café.mp3" in names and "Espagnol A1 - Support écrit.html" in names
    assert "Espagnol A1 - Flashcards.html" in names and any(n.endswith("_anki.csv") for n in names)
    review = [f for f in res.files if f.parent.name.endswith("Révisions")]
    assert len(review) == 2  # séances à J+1 et J+4 dans les 5 prochains jours
    lesson_mp3 = next(f for f in res.files if f.name == "01 - Au café.mp3")
    chaps = [str(c.sub_frames["TIT2"]) for c in ID3(str(lesson_mp3)).getall("CHAP")]
    assert "Vocabulaire" in chaps and "Phrases utiles" in chaps
