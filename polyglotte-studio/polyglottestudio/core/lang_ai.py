"""Assistant DeepSeek pour les cours de langue : leçons complètes (vocabulaire, phrases utiles, dialogue,
petite histoire graduée, point de grammaire, prononciation, translittérations, questions, quiz, résumé),
plan de cours par niveau et par thème, consignes traduites dans la langue d'explication."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import course, languages
from .ai import AIError, DeepSeekClient
from .models import Chapter, Host, Project, QuizQuestion, VocabItem

THEMES = [
    "Se présenter", "Salutations et politesse", "Les chiffres et l'heure", "La famille", "Au café",
    "Au restaurant", "Faire les courses", "Les achats et les prix", "Voyage et transports", "À l'hôtel",
    "Demander son chemin", "La météo", "Le travail", "Les loisirs", "La santé et le corps", "Chez le médecin",
    "La maison", "Les jours, les mois et les saisons", "Les couleurs et les vêtements", "Les verbes essentiels",
    "Parler du passé", "Parler de l'avenir", "Donner son opinion", "Au téléphone", "Les émotions",
    "Fêtes et traditions",
]
CONTENT_PARTS = {
    "vocabulary": "Liste de vocabulaire",
    "phrases": "Phrases utiles",
    "dialogue": "Dialogue de la vie courante",
    "story": "Petite histoire graduée",
    "grammar": "Point de grammaire expliqué simplement",
    "pronunciation": "Conseils de prononciation",
}
DEFAULT_PARTS = ["vocabulary", "phrases", "dialogue", "grammar"]
LEVEL_HINTS = {
    "A1": "débutant complet : mots très courants, phrases très courtes, présent uniquement",
    "A2": "élémentaire : phrases simples du quotidien, passé simple courant",
    "B1": "intermédiaire : conversations du quotidien, plusieurs temps, connecteurs simples",
    "B2": "intermédiaire avancé : nuances, opinions argumentées, expressions idiomatiques courantes",
    "C1": "avancé : langue riche et naturelle, registres, expressions idiomatiques",
    "C2": "maîtrise : langue authentique, subtilités culturelles et stylistiques",
}


def _lang_label(code: str) -> str:
    lang = languages.get(code)
    if lang is None:
        return code
    return f"{lang.name} ({lang.native})" if lang.native != lang.name else lang.name


def _flat(value) -> str:
    return " ".join(str(value or "").split())


@dataclass
class LessonContent:
    title: str = ""
    description: str = ""
    vocab: list[VocabItem] = field(default_factory=list)
    script: str = ""
    speakers: list[Host] = field(default_factory=list)
    questions: list[QuizQuestion] = field(default_factory=list)
    quiz: list[QuizQuestion] = field(default_factory=list)
    summary: str = ""


def lesson_prompt(target: str, locale: str, explain: str, level: str, theme: str, parts: list[str],
                  n_words: int = 10, n_phrases: int = 6, n_questions: int = 3, n_quiz: int = 4,
                  known_words: list[str] | None = None) -> str:
    """Consigne système envoyée à DeepSeek pour écrire une leçon."""
    lang = languages.get(target)
    tag = locale or (lang.code if lang else target)
    region = (lang.locale_label(locale) if lang and locale else "") or ""
    translit = (f"Pour chaque mot et chaque phrase, donne la translittération ({lang.translit}) dans « translit »."
                if lang and lang.non_latin else "Laisse « translit » vide (écriture latine).")
    wanted = ", ".join(CONTENT_PARTS[p] for p in parts if p in CONTENT_PARTS) or CONTENT_PARTS["dialogue"]
    known = ""
    if known_words:
        known = ("Mots déjà étudiés dans les leçons précédentes (réutilise-les, n'en fais pas de nouveaux mots) : "
                 + ", ".join(known_words[:80]) + ".")
    exp = _lang_label(explain)
    nw = max(0, n_words) if "vocabulary" in parts else 0
    np = max(0, n_phrases) if "phrases" in parts else 0
    return f"""Tu es un excellent professeur de langue qui prépare une leçon AUDIO (elle sera lue par des voix de
synthèse : une voix pour les explications, des voix natives pour la langue apprise).
Langue apprise : {_lang_label(target)}{f", accent {region}" if region else ""} — balise [{tag}].
Langue d'explication : {exp}. Niveau : {level} ({LEVEL_HINTS.get(level, '')}). Thème : {theme}.
Contenu demandé : {wanted}.

Réponds en JSON avec exactement ces clés :
{{"titre": "titre court de la leçon, en {exp}",
 "description": "une phrase de présentation, en {exp}",
 "vocabulaire": [{{"mot": "...", "traduction": "...", "translit": "...", "exemple": "phrase courte dans la langue
   apprise", "exemple_traduction": "...", "notes": "genre, pluriel, registre… (facultatif)"}}],
 "phrases": [{{"phrase": "...", "traduction": "...", "translit": "..."}}],
 "intervenants": [{{"nom": "prénom typique du pays", "sexe": "F ou M"}}],
 "script": "texte lu de la leçon",
 "questions": [{{"question": "question de compréhension, en {exp}", "reponse": "réponse courte"}}],
 "quiz": [{{"question": "...", "choix": ["...", "...", "..."], "reponse": "texte exact du bon choix",
   "explication": "une phrase"}}],
 "resume": "3 à 5 phrases à l'oral, en {exp}, qui reprennent l'essentiel"}}

Règles :
- {nw} mots dans « vocabulaire » et {np} phrases dans « phrases », adaptés au niveau et au thème, avec
  l'article quand la langue en a.
- {translit}
- Traductions et explications dans la langue d'explication ; mots et phrases dans la langue apprise, avec la
  graphie native (caractères chinois, kana et kanji, alphabet arabe, cyrillique, devanagari…).
- « script » : le texte lu APRÈS les listes de vocabulaire (ne les répète pas). Paragraphes séparés par une ligne
  vide. Les explications sont écrites sans balise. TOUT passage dans la langue apprise est balisé : au milieu
  d'une phrase « le mot [{tag}]gato[/{tag}] veut dire chat », ou en tête de ligne « [{tag}] ¿Dónde está? ».
  Dialogue : une réplique par ligne « @Prénom: [{tag}] réplique », les prénoms étant ceux de « intervenants » ;
  pour les niveaux A1 à A2, fais suivre chaque réplique de sa traduction sur la ligne suivante (sans balise).
  Sections précédées d'un intertitre « # Dialogue », « # Petite histoire », « # Grammaire », « # Prononciation »
  (intertitres dans la langue d'explication). N'écris jamais la translittération ni de crochets autres que les
  balises de langue dans « script » ; tu peux utiliser « [pause 2s] » pour laisser l'auditeur répéter.
- {n_questions} questions de compréhension sur le dialogue ou l'histoire et {n_quiz} questions de quiz à choix
  multiples sur le vocabulaire et la grammaire de la leçon.
{known}"""


def _vocab(entries, kind: str) -> list[VocabItem]:
    out = []
    for e in entries or []:
        if isinstance(e, str):
            e = {"mot": e}
        if not isinstance(e, dict):
            continue
        term = _flat(e.get("mot") or e.get("phrase") or e.get("term") or e.get("word"))
        if not term:
            continue
        out.append(VocabItem(term=term.replace("[", "(").replace("]", ")"),
                             translation=_flat(e.get("traduction") or e.get("translation")),
                             translit=_flat(e.get("translit") or e.get("transliteration") or e.get("prononciation")),
                             example=_flat(e.get("exemple") or e.get("example")),
                             example_translation=_flat(e.get("exemple_traduction") or e.get("example_translation")),
                             notes=_flat(e.get("notes")), kind=kind))
    return out


def _questions(entries, with_choices: bool) -> list[QuizQuestion]:
    out = []
    for q in entries or []:
        if not isinstance(q, dict) or not _flat(q.get("question")):
            continue
        choices = [_flat(c) for c in (q.get("choix") or q.get("choices") or []) if _flat(c)] if with_choices else []
        out.append(QuizQuestion(_flat(q.get("question")), choices[:6], _flat(q.get("reponse") or q.get("answer")),
                                _flat(q.get("explication") or q.get("explanation"))))
    return out


def _clean_script(script: str, target_tag: str, speakers: list[str]) -> str:
    """Nettoie le script renvoyé : fins de ligne, balises « ``` », répliques sans balise de langue."""
    s = str(script or "").replace("\r\n", "\n").strip()
    s = re.sub(r"^```\w*\n|\n```$", "", s)
    lines = []
    known = {n.lower() for n in speakers}
    for line in s.split("\n"):
        m = re.match(r"^@([^:\n]{1,40}):\s*(.*)$", line)
        if m and m.group(1).strip().lower() in known and not re.match(r"^\[", m.group(2).strip()):
            line = f"@{m.group(1).strip()}: [{target_tag}] {m.group(2).strip()}"
        lines.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_lesson(data: dict, target_tag: str) -> LessonContent:
    """Réponse JSON de DeepSeek → contenu de leçon (tolère les variantes de clés en anglais)."""
    if not isinstance(data, dict):
        raise AIError("Réponse de DeepSeek illisible.")
    speakers = []
    for sp in data.get("intervenants") or data.get("speakers") or []:
        if isinstance(sp, str):
            sp = {"nom": sp}
        if not isinstance(sp, dict):
            continue
        name = _flat(sp.get("nom") or sp.get("name"))[:40].replace(":", "")
        if name and all(h.name.lower() != name.lower() for h in speakers):
            g = _flat(sp.get("sexe") or sp.get("gender")).upper()[:1]
            speakers.append(Host(name=name, role="guest", gender="F" if g in ("F", "W") else "M" if g in ("M", "H")
                                 else ""))
    content = LessonContent(
        title=_flat(data.get("titre") or data.get("title"))[:100],
        description=_flat(data.get("description")),
        vocab=_vocab(data.get("vocabulaire") or data.get("vocabulary"), "word")
        + _vocab(data.get("phrases"), "phrase"),
        script=_clean_script(data.get("script") or data.get("texte") or "", target_tag, [h.name for h in speakers]),
        speakers=speakers,
        questions=_questions(data.get("questions"), False),
        quiz=_questions(data.get("quiz"), True),
        summary=_flat(data.get("resume") or data.get("summary")),
    )
    if not content.vocab and not content.script:
        raise AIError("DeepSeek n'a pas renvoyé de leçon exploitable. Réessayez.")
    return content


def generate_lesson(client: DeepSeekClient, project: Project, chapter: Chapter, theme: str, parts: list[str],
                    n_words: int = 10, n_phrases: int = 6, n_questions: int = 3, n_quiz: int = 4,
                    notes: str = "") -> LessonContent:
    code, locale = project.target_of(chapter)
    tag = locale or code
    known = [v.term for c, v in project.all_vocab() if c.id != chapter.id][:80]
    system = lesson_prompt(code, locale, course.explain_code(project), project.level_of(chapter), theme, parts,
                           n_words, n_phrases, n_questions, n_quiz, known)
    user = f"Leçon : {chapter.title or theme}." + (f"\nIndications du professeur : {notes}" if notes.strip() else "")
    data = client.chat_json(system, user, max_tokens=8000, temperature=0.6)
    return parse_lesson(data, tag)


def apply_lesson(project: Project, chapter: Chapter, content: LessonContent, replace: bool = True,
                 theme: str = "") -> None:
    """Range le contenu généré dans la leçon (et ajoute les intervenants du dialogue au projet)."""
    if content.title and (replace or not chapter.title.strip() or chapter.title.startswith("Nouvelle leçon")):
        chapter.title = content.title
    if theme:
        chapter.theme = theme
    if content.description:
        chapter.description = content.description
    if replace:
        chapter.vocab = content.vocab
        chapter.text = content.script
        chapter.questions = content.questions
        chapter.quiz = content.quiz
        chapter.summary = content.summary
    else:
        have = {v.term.lower() for v in chapter.vocab}
        chapter.vocab += [v for v in content.vocab if v.term.lower() not in have]
        chapter.text = (chapter.text.rstrip() + "\n\n" + content.script).strip()
        chapter.questions += content.questions
        chapter.quiz += content.quiz
        chapter.summary = chapter.summary or content.summary
    code, _loc = project.target_of(chapter)
    for sp in content.speakers:
        if project.host_by_name(sp.name) is None:
            sp.language = code
            project.hosts.append(sp)


# ---------------------------------------------------------------------------------------
# Plan de cours
# ---------------------------------------------------------------------------------------
def course_plan(client: DeepSeekClient, target: str, explain: str, level: str, modules: int = 4,
                lessons_per_module: int = 4, themes: list[str] | None = None) -> list[tuple[str, list[tuple[str, str]]]]:
    """Plan proposé : [(titre du module, [(titre de la leçon, thème)])]."""
    wish = ("Thèmes souhaités : " + ", ".join(themes) + ".") if themes else "Choisis des thèmes utiles au quotidien."
    system = f"""Tu conçois un cours AUDIO de {_lang_label(target)} pour des personnes dont la langue est
{_lang_label(explain)}, niveau {level} ({LEVEL_HINTS.get(level, '')}). {wish}
Propose {modules} modules de {lessons_per_module} leçons, dans une progression logique (chaque leçon réutilise les
précédentes). Titres en {_lang_label(explain)}, courts et parlants.
Réponds en JSON : {{"modules": [{{"titre": "...", "lecons": [{{"titre": "...", "theme": "..."}}]}}]}}."""
    data = client.chat_json(system, "Plan du cours.", max_tokens=3000, temperature=0.5)
    out = []
    for m in data.get("modules") or []:
        if not isinstance(m, dict):
            continue
        title = _flat(m.get("titre") or m.get("title"))[:80]
        lessons = []
        for le in m.get("lecons") or m.get("lessons") or []:
            if isinstance(le, str):
                le = {"titre": le}
            if isinstance(le, dict) and _flat(le.get("titre") or le.get("title")):
                lessons.append((_flat(le.get("titre") or le.get("title"))[:100],
                                _flat(le.get("theme")) or _flat(le.get("titre") or le.get("title"))))
        if title and lessons:
            out.append((title, lessons))
    if not out:
        raise AIError("DeepSeek n'a pas proposé de plan exploitable. Réessayez.")
    return out


def apply_plan(project: Project, plan: list[tuple[str, list[tuple[str, str]]]]) -> list[Chapter]:
    """Ajoute au projet les leçons (vides) du plan, rangées dans leurs modules."""
    added = []
    for mi, (module, lessons) in enumerate(plan, 1):
        name = module if course.MODULE_TITLE_RE.match(module) else f"Module {mi} : {module}"
        for title, theme in lessons:
            ch = Chapter(title=title, module=name, theme=theme)
            project.chapters.append(ch)
            added.append(ch)
    return added


# ---------------------------------------------------------------------------------------
# Consignes et translittérations
# ---------------------------------------------------------------------------------------
def translate_instructions(client: DeepSeekClient, explain: str) -> dict[str, str]:
    """Consignes lues (« Écoutez puis répétez »…) traduites dans une langue d'explication non intégrée."""
    import json

    source = course.INSTRUCTIONS["en"]
    system = f"""Translate the values of this JSON object from English into {_lang_label(explain)}, for an audio
language course (spoken instructions, natural and friendly). Keep the keys and the placeholders in braces such as
{{n}}, {{text}}, {{answer}}, {{language}} exactly as they are. Answer with the JSON object only."""
    data = client.chat_json(system, json.dumps(source, ensure_ascii=False), max_tokens=3000, temperature=0.2)
    out = {}
    for key, value in source.items():
        tr = _flat(data.get(key))
        wanted = set(re.findall(r"\{\w+\}", value))
        if tr and set(re.findall(r"\{\w+\}", tr)) == wanted:
            out[key] = tr
    if len(out) < len(source) // 2:
        raise AIError("Traduction des consignes incomplète. Réessayez.")
    return out


def fill_transliterations(client: DeepSeekClient, items: list[VocabItem], target: str) -> int:
    """Complète les translittérations manquantes (pinyin, romaji…). Renvoie le nombre d'éléments complétés."""
    lang = languages.get(target)
    todo = [it for it in items if it.term.strip() and not it.translit.strip()]
    if not todo or lang is None or not lang.non_latin:
        return 0
    listing = "\n".join(f"[{i}] {it.term}" for i, it in enumerate(todo, 1))
    system = f"""Donne la translittération ({lang.translit}) de chaque élément en {_lang_label(target)}.
Réponds en JSON : {{"translit": [{{"n": numéro, "translit": "..."}}]}}."""
    data = client.chat_json(system, listing[:12000], max_tokens=3000, temperature=0.1)
    n = 0
    for e in data.get("translit") or []:
        if not isinstance(e, dict):
            continue
        try:
            i = int(e.get("n")) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(todo) and _flat(e.get("translit")):
            todo[i].translit = _flat(e.get("translit"))
            n += 1
    return n
