"""Fonctions propres à Leçon Studio : modules, pauses de réflexion, résumé et quiz, support écrit, mises à jour."""

import json

from polyglottestudio.core import ai, course, renderer, updates
from polyglottestudio.core.models import Chapter, Project, QuizQuestion, VoiceProfile
from polyglottestudio.core.textproc import parse_script

from .test_ai import FakeClient


def lessons():
    return [Chapter("Module 1 : Les bases", "Dans ce module, on découvre les bases."),
            Chapter("Les nombres", "Un nombre sert à compter."),
            Chapter("Les formes", "Un carré a quatre côtés."),
            Chapter("Partie II", "Introduction courte."),
            Chapter("Les fractions", "Une fraction partage un tout.")]


def test_infer_modules_from_imported_titles():
    out = course.infer_modules(lessons())
    assert [(c.title, c.module) for c in out] == [("Les nombres", "Module 1 : Les bases"),
                                                  ("Les formes", "Module 1 : Les bases"),
                                                  ("Les fractions", "Partie II")]
    assert out[0].text.startswith("Dans ce module")  # l'introduction du module rejoint la 1re leçon
    plain = [Chapter("A", "x"), Chapter("B", "y")]
    assert course.infer_modules(plain) == plain and not plain[0].module


def test_modules_numbers_and_grouping():
    pr = Project(chapters=course.infer_modules(lessons()) + [Chapter("Annexe", "z")])
    assert [(t, len(ls)) for t, ls in pr.modules()] == [("Module 1 : Les bases", 2), ("Partie II", 1), ("", 1)]
    c = pr.chapters
    assert [pr.module_number(x) for x in c] == [1, 1, 2, 0]
    assert [pr.lesson_number(x) for x in c] == [1, 2, 1, 1]
    assert [pr.first_of_module(x) for x in c] == [True, False, True, False]
    course.group_lessons(c, 3)
    assert [x.module for x in c] == ["Module 1"] * 3 + ["Module 2"]
    assert course.rename_module(c, "Module 1", "Bases") == 3 and course.module_titles(c) == ["Bases", "Module 2"]


def test_reflection_tags_become_pauses():
    assert course.expand_reflections("Pourquoi ? [réflexion] Et [Reflexion 10s] puis [réflexion 500ms]", 7000) == \
        "Pourquoi ? [pause 7000ms] Et [pause 10000ms] puis [pause 500ms]"
    items = parse_script("Une question ? [réflexion]\n\nLa suite.")
    assert [i.kind for i in items] == ["para", "pause", "para"] and items[1].pause_ms == 6000


def test_quiz_script_letters_and_answers():
    quiz = [QuizQuestion("Combien de côtés a un carré", ["Trois", "Quatre"], "quatre", "Comme un carré !"),
            QuizQuestion("Citez un nombre pair", [], "Deux"),
            QuizQuestion("2 + 2 = 4", ["Vrai", "Faux"], "A")]
    text = course.quiz_script(quiz, 4000)
    assert "Question 1. Combien de côtés a un carré." in text
    assert "A : Trois. B : Quatre." in text
    assert "La bonne réponse est B : Quatre. Comme un carré !" in text
    assert "La bonne réponse est Deux." in text and "La bonne réponse est A : Vrai." in text
    assert text.count("[pause 4000ms]") == 3 and text.startswith("# Quiz")


def test_lesson_plan_reads_module_title_summary_and_quiz(tmp_path, tone_engine, library):
    prof = library.save(VoiceProfile(name="Prof", engine="tone"))
    ch = Chapter("Les nombres", "Un nombre sert à compter. Pourquoi ? [réflexion]", module="Les bases",
                 summary="Retenez qu'un nombre sert à compter.",
                 quiz=[QuizQuestion("À quoi sert un nombre ?", ["Compter", "Chanter"], "Compter")])
    pr = Project(chapters=[ch, Chapter("Suite", "Encore.", module="Les bases")], narrator_voice_id=prof.id)
    pr.production.quiz_think_ms = 3000
    rc = renderer.build_plan(pr, library)[0]
    shown = [s.display for s in rc.segments]
    assert shown[0] == "Module 1. Les bases." and shown[1] == "Leçon 1. Les nombres."
    assert any("Retenez qu'un nombre" in t for t in shown) and any("Question 1." in t for t in shown)
    reflection = next(s for s in rc.segments if s.display.endswith("Pourquoi ?"))
    assert reflection.pause_after_ms >= 6000
    answer = next(i for i, s in enumerate(rc.segments) if "Chanter" in s.display)
    assert rc.segments[answer].pause_after_ms >= 3000  # temps de réponse avant la correction
    second = renderer.build_plan(pr, library)[1]
    assert second.segments[0].display == "Leçon 2. Suite."  # module annoncé une seule fois
    pr.production.include_quiz = pr.production.include_summary = False
    assert not any("Question" in s.display for s in renderer.build_plan(pr, library)[0].segments)


def test_lesson_review_and_reflections_with_ai():
    answer = json.dumps({"resume": "Retenez   ceci.", "quiz": [
        {"question": "Q1 ?", "choix": ["a", "b"], "reponse": "a", "explication": "car a"},
        {"question": "", "choix": []}, {"question": "Q3 ?", "choix": ["x"], "reponse": "x"}]})
    summary, quiz = ai.lesson_review("Titre", "@Prof: [calme] Texte de la leçon.", FakeClient([answer]), 2)
    assert summary == "Retenez ceci." and [q.question for q in quiz] == ["Q1 ?", "Q3 ?"]
    assert quiz[0].choices == ["a", "b"] and quiz[0].explanation == "car a"
    _s, open_quiz = ai.lesson_review("T", "Texte.", FakeClient([answer]), 3, kind="ouvert")
    assert all(not q.choices for q in open_quiz)

    text = "Premier paragraphe.\n\nDeuxième paragraphe.\n\nTroisième."
    client = FakeClient([json.dumps({"pauses": [{"apres": 1, "question": "Et vous ?"}, {"apres": 9, "question": "x"},
                                                {"apres": "2", "question": "Pourquoi ?"}]})])
    points = ai.reflection_points(text, client)
    assert [(p.number, p.question) for p in points] == [(1, "Et vous ?"), (2, "Pourquoi ?")]
    new = ai.apply_reflections(text, points[:1])
    assert new == "Premier paragraphe.\n\nEt vous ? [réflexion]\n\nDeuxième paragraphe.\n\nTroisième."


def test_organize_modules_with_ai():
    client = FakeClient([json.dumps({"modules": [{"titre": "Bases", "lecons": [1, 2]},
                                                 {"titre": "Suite", "lecons": [4]}]})])
    titles = ai.organize_modules([("A", "a"), ("B", "b"), ("C", "c"), ("D", "d")], client)
    assert titles == ["Bases", "Bases", "Bases", "Suite"]  # leçon oubliée : module précédent


def test_handout_contains_lessons_summary_and_answers(tmp_path):
    pr = Project(chapters=[Chapter("Les nombres", "Texte *important*. [réflexion]\n\n# Détail\n\nSuite.",
                                   module="Les bases", summary="Retenez <ceci>.",
                                   quiz=[QuizQuestion("Q ?", ["Oui", "Non"], "Oui", "Parce que.")])])
    pr.metadata.title = "Maths"
    from polyglottestudio.core import handouts

    html = handouts.write_handout(pr, tmp_path / "s.html").read_text("utf-8")
    assert "Les bases" in html and "Leçon 1 — Les nombres" in html and "Retenez &lt;ceci&gt;." in html
    assert "<h4>Détail</h4>" in html and "[réflexion]" not in html and "*important*" not in html
    assert "Parce que." in html and "A. Oui" in html


def test_pick_release_filters_this_app():
    rel = updates.pick_release([{"tag_name": "v3.0.0"}, {"tag_name": "podcast-v2.0.0"},
                                {"tag_name": "lecon-v4.0.0"},
                                {"tag_name": "polyglotte-v1.2.0", "assets": [{"name": "PolyglotteStudio-Setup-1.2.0.exe",
                                                                             "browser_download_url": "d"}]}])
    assert rel["version"] == "1.2.0" and rel["download"] == "d"


def test_project_roundtrip_with_quiz(tmp_path):
    from polyglottestudio.core import project_io

    pr = Project(chapters=[Chapter("L", "x", module="M", summary="s", quiz=[QuizQuestion("q", ["a"], "a", "e")])])
    back = project_io.load_project(project_io.save_project(pr, tmp_path / "c.plgproj"))
    c = back.chapters[0]
    assert (c.module, c.summary) == ("M", "s") and isinstance(c.quiz[0], QuizQuestion)
    assert c.quiz[0].choices == ["a"] and c.quiz[0].explanation == "e"
