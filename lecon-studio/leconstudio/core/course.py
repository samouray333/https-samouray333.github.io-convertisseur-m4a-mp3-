"""Cours audio : modules, script lu d'une leçon (pauses de réflexion, résumé, quiz) et support écrit."""

from __future__ import annotations

import html
import re
import time
from pathlib import Path

from .models import Chapter, Project, QuizQuestion

# « [réflexion] » (durée réglée dans la production) ou « [réflexion 10s] »
REFLECTION_RE = re.compile(r"\[\s*r[ée]flexion(?:\s*[:= ]?\s*(\d+(?:[.,]\d+)?)\s*(ms|s)?)?\s*\]", re.IGNORECASE)
DEFAULT_REFLECTION_MS = 6000
LETTERS = "ABCDEFGH"
# Titre de partie importé qui annonce un module : « Module 2 », « Partie I : … », « Unité 3 », « Séquence 1 »
MODULE_TITLE_RE = re.compile(r"^\s*(module|partie|unit[ée]|s[ée]quence|bloc|semaine|th[èe]me)\s+([\w]+)\b",
                             re.IGNORECASE)


def expand_reflections(text: str, default_ms: int = DEFAULT_REFLECTION_MS) -> str:
    """Remplace les balises de réflexion par des pauses ordinaires."""
    def repl(m: re.Match) -> str:
        if m.group(1):
            v = float(m.group(1).replace(",", "."))
            ms = int(v if (m.group(2) or "s").lower() == "ms" else v * 1000)
        else:
            ms = default_ms
        return f"[pause {max(0, ms)}ms]"

    return REFLECTION_RE.sub(repl, text)


def _sentence(text: str) -> str:
    t = " ".join(text.split()).strip()
    return t if not t or t[-1] in ".!?…" else t + "."


def quiz_script(quiz: list[QuizQuestion], think_ms: int) -> str:
    """Texte lu du quiz : chaque question, ses choix, un temps de réponse, puis la correction."""
    questions = [q for q in quiz if q.question.strip()]
    if not questions:
        return ""
    n = len(questions)
    intro = ("Pour terminer, une petite question pour vérifier ce que vous avez retenu."
             if n == 1 else f"Pour terminer, {n} questions pour vérifier ce que vous avez retenu.")
    out = ["# Quiz", intro + " Mettez l'écoute en pause si vous avez besoin de plus de temps."]
    for i, q in enumerate(questions, 1):
        out.append(f"Question {i}. {_sentence(q.question)}")
        if q.choices:
            out.append(" ".join(f"{LETTERS[j]} : {_sentence(c)}" for j, c in enumerate(q.choices[:len(LETTERS)])))
        out.append(f"[pause {max(0, think_ms)}ms]")
        answer = q.answer.strip()
        letter = ""
        if q.choices and answer:
            lowered = [c.strip().lower() for c in q.choices]
            if answer.lower() in lowered:
                letter = LETTERS[lowered.index(answer.lower())]
                answer = q.choices[lowered.index(answer.lower())].strip()
            elif len(answer) == 1 and answer.upper() in LETTERS[:len(q.choices)]:
                letter = answer.upper()
                answer = q.choices[LETTERS.index(letter)]
        if answer:
            out.append(f"La bonne réponse est {letter + ' : ' if letter else ''}{_sentence(answer)} "
                       + _sentence(q.explanation))
    return "\n\n".join(p.strip() for p in out if p.strip())


def lesson_script(project: Project, chapter: Chapter) -> str:
    """Texte complet lu pour une leçon : la leçon, puis son résumé et son quiz selon les réglages."""
    prod = project.production
    parts = [expand_reflections(chapter.text, prod.reflection_pause_ms)]
    if prod.include_summary and chapter.summary.strip():
        parts.append("# Ce qu'il faut retenir\n\n" + expand_reflections(chapter.summary.strip(),
                                                                       prod.reflection_pause_ms))
    if prod.include_quiz and chapter.quiz:
        quiz = quiz_script(chapter.quiz, prod.quiz_think_ms)
        if quiz:
            parts.append(quiz)
    return "\n\n".join(p for p in parts if p.strip())


# ---------------------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------------------
def infer_modules(chapters: list[Chapter]) -> list[Chapter]:
    """Après un import : les parties titrées « Module 2 », « Partie I »… deviennent des modules.

    Une telle partie presque vide (introduction de moins de 120 mots) disparaît et son texte passe en tête de
    la leçon suivante ; une partie longue reste une leçon, rattachée à son propre module."""
    if not any(MODULE_TITLE_RE.match(c.title) for c in chapters):
        return chapters
    out: list[Chapter] = []
    current = ""
    carry = ""
    for c in chapters:
        if MODULE_TITLE_RE.match(c.title):
            current = c.title.strip()
            if c.word_count() < 120:
                carry = c.text.strip()
                continue
        if carry:
            c.text = (carry + "\n\n" + c.text).strip()
            carry = ""
        c.module = current
        out.append(c)
    if carry:  # module sans leçon : on garde son introduction comme leçon
        out.append(Chapter(title=current, text=carry, module=current))
    return out


def group_lessons(chapters: list[Chapter], per_module: int, prefix: str = "Module") -> None:
    """Range les leçons par paquets de ``per_module`` : « Module 1 », « Module 2 »…"""
    per_module = max(1, per_module)
    for i, c in enumerate(chapters):
        c.module = f"{prefix} {i // per_module + 1}"


def module_titles(chapters: list[Chapter]) -> list[str]:
    return list(dict.fromkeys(c.module for c in chapters if c.module))


def rename_module(chapters: list[Chapter], old: str, new: str) -> int:
    n = 0
    for c in chapters:
        if c.module == old:
            c.module = new
            n += 1
    return n


# ---------------------------------------------------------------------------------------
# Support écrit (HTML imprimable)
# ---------------------------------------------------------------------------------------
_TAG_RE = re.compile(r"\[[^\]\n]*\]")


def _clean_for_reading(text: str) -> str:
    text = REFLECTION_RE.sub("🤔", text)
    text = _TAG_RE.sub("", text)
    text = re.sub(r"(?m)^@[^:\n]{1,40}:\s*", "", text)
    text = re.sub(r"(?m)^%%.*$", "", text)
    return re.sub(r"\*([^*\n]+)\*", r"\1", text)


def _paragraphs_html(text: str) -> str:
    out = []
    for block in re.split(r"\n\s*\n", _clean_for_reading(text).strip()):
        b = block.strip()
        if not b:
            continue
        m = re.match(r"^(#{1,6})\s*(.+)$", b)
        if m:
            out.append(f"<h4>{html.escape(m.group(2))}</h4>")
        else:
            out.append("<p>" + html.escape(b).replace("\n", "<br>") + "</p>")
    return "\n".join(out)


def handout_html(project: Project) -> str:
    meta = project.metadata
    title = meta.title or "Cours"
    body = []
    toc = []
    for mi, (module, lessons) in enumerate(project.modules(), 1):
        if module:
            anchor = f"m{mi}"
            toc.append(f'<li><a href="#{anchor}">{html.escape(module)}</a><ol>'
                       + "".join(f"<li>{html.escape(c.title)}</li>" for c in lessons) + "</ol></li>")
            body.append(f'<h2 id="{anchor}">{html.escape(module)}</h2>')
        else:
            toc += [f"<li>{html.escape(c.title)}</li>" for c in lessons]
        for c in lessons:
            num = project.lesson_number(c)
            body.append(f'<section class="lesson"><h3>Leçon {num} — {html.escape(c.title)}</h3>')
            body.append(_paragraphs_html(c.text))
            if c.summary.strip():
                body.append('<div class="summary"><b>Ce qu\'il faut retenir</b>' + _paragraphs_html(c.summary)
                            + "</div>")
            qs = [q for q in c.quiz if q.question.strip()]
            if qs:
                items = []
                answers = []
                for i, q in enumerate(qs, 1):
                    choices = "".join(f"<li>{LETTERS[j]}. {html.escape(ch)}</li>"
                                      for j, ch in enumerate(q.choices[:len(LETTERS)]))
                    items.append(f"<li>{html.escape(q.question)}" + (f"<ul class='choices'>{choices}</ul>"
                                                                     if choices else "") + "</li>")
                    answers.append(f"<li>{html.escape(q.answer or '—')}"
                                   + (f" — <i>{html.escape(q.explanation)}</i>" if q.explanation else "") + "</li>")
                body.append('<div class="quiz"><b>Quiz</b><ol>' + "".join(items) + "</ol>"
                            '<details><summary>Réponses</summary><ol>' + "".join(answers) + "</ol></details></div>")
            body.append("</section>")
    author = f" — {html.escape(meta.author)}" if meta.author else ""
    return f"""<!doctype html><html lang="{html.escape(meta.language or 'fr')}"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;max-width:820px;margin:32px auto;padding:0 20px;color:#14231c;
line-height:1.55}} h1{{color:#1e8449;margin-bottom:0}} .sub{{color:#56705f;margin-bottom:24px}}
h2{{color:#1e8449;border-bottom:2px solid #6fcf97;padding-bottom:4px;margin-top:40px;page-break-before:always}}
h3{{margin-top:28px}} .summary{{background:#eaf7ef;border-left:4px solid #27ae60;padding:10px 16px;margin:14px 0}}
.quiz{{background:#f4f8f6;border:1px solid #d9e6df;border-radius:8px;padding:10px 16px;margin:14px 0}}
.choices{{list-style:none;padding-left:10px}} details{{margin-top:8px;color:#3d5a4a}}
@media print{{details{{display:block}} details>summary{{display:none}} a{{color:inherit;text-decoration:none}}}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="sub">{html.escape(meta.subtitle)}{author} · support écrit généré le {time.strftime('%d/%m/%Y')}</div>
<h3>Sommaire</h3><ol>{''.join(toc)}</ol>
{''.join(body)}
</body></html>"""


def write_handout(project: Project, target: Path) -> Path:
    target.write_text(handout_html(project), encoding="utf-8")
    return target
