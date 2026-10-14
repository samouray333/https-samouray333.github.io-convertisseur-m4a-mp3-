"""Supports écrits du cours : support HTML imprimable, flashcards recto-verso, export Anki (CSV + audio),
glossaire par langue."""

from __future__ import annotations

import csv
import html
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import course, languages
from .models import Chapter, Project, VocabItem
from .textproc import strip_language_tags

_TAG_RE = re.compile(r"\[[^\]\n]*\]")
ACCENT = "#1E88E5"
GOLD = "#FFC107"
INK = "#0F1B2D"


def _e(text: str) -> str:
    return html.escape(text or "")


def clean_for_reading(text: str) -> str:
    """Texte d'une leçon sans balises (le support écrit garde les répliques « Nom : … »)."""
    text = course.REFLECTION_RE.sub("🤔", text)
    text = strip_language_tags(text)
    text = _TAG_RE.sub("", text)
    text = re.sub(r"(?m)^@([^:\n]{1,40}):\s*", r"\1 : ", text)
    text = re.sub(r"(?m)^%%.*$", "", text)
    return re.sub(r"\*([^*\n]+)\*", r"\1", text)


def _paragraphs_html(text: str) -> str:
    out = []
    for block in re.split(r"\n\s*\n", clean_for_reading(text).strip()):
        b = block.strip()
        if not b:
            continue
        m = re.match(r"^(#{1,6})\s*(.+)$", b)
        if m:
            out.append(f"<h4>{_e(m.group(2))}</h4>")
        else:
            lines = [ln for ln in b.split("\n") if ln.strip()]
            out.append("<p dir=\"auto\">" + "<br>".join(_e(ln) for ln in lines) + "</p>")
    return "\n".join(out)


def _vocab_table(items: list[VocabItem], translit: bool, phrases: bool = False) -> str:
    if not items:
        return ""
    head = "<tr><th>" + ("Phrase" if phrases else "Mot") + "</th>" + ("<th>Prononciation</th>" if translit else "") \
        + "<th>Traduction</th>" + ("" if phrases else "<th>Exemple</th>") + "</tr>"
    rows = []
    for it in items:
        star = ' <span class="star">★</span>' if it.favorite else ""
        ex = ""
        if not phrases and it.example:
            ex = f'<span dir="auto">{_e(it.example)}</span>' + (f"<br><i>{_e(it.example_translation)}</i>"
                                                                 if it.example_translation else "")
        note = f'<div class="note">{_e(it.notes)}</div>' if it.notes else ""
        rows.append(f'<tr><td class="term" dir="auto">{_e(it.term)}{star}{note}</td>'
                    + (f'<td class="tr">{_e(it.translit)}</td>' if translit else "")
                    + f"<td>{_e(it.translation)}</td>" + ("" if phrases else f"<td>{ex}</td>") + "</tr>")
    return f'<table class="vocab">{head}{"".join(rows)}</table>'


def _questions_html(questions, title: str, open_answers: bool = False) -> str:
    qs = [q for q in questions if q.question.strip()]
    if not qs:
        return ""
    items, answers = [], []
    for q in qs:
        choices = "".join(f"<li>{course.LETTERS[j]}. {_e(ch)}</li>" for j, ch in enumerate(q.choices[:8]))
        items.append(f'<li dir="auto">{_e(q.question)}' + (f"<ul class='choices'>{choices}</ul>" if choices else "")
                     + "</li>")
        letter, answer = course._letter_answer(q)
        answers.append(f"<li>{_e((letter + '. ' if letter else '') + (answer or '—'))}"
                       + (f" — <i>{_e(q.explanation)}</i>" if q.explanation else "") + "</li>")
    return (f'<div class="quiz"><b>{_e(title)}</b><ol>' + "".join(items) + "</ol>"
            f'<details{" open" if open_answers else ""}><summary>Réponses</summary><ol>' + "".join(answers)
            + "</ol></details></div>")


def _style() -> str:
    return f"""
body{{font-family:'Segoe UI',system-ui,'Noto Sans','Microsoft YaHei','Yu Gothic','Malgun Gothic',sans-serif;
max-width:880px;margin:32px auto;padding:0 20px;color:{INK};line-height:1.55}}
h1{{color:{ACCENT};margin-bottom:0}} .sub{{color:#4b5d78;margin-bottom:24px}}
h2{{color:{ACCENT};border-bottom:3px solid {GOLD};padding-bottom:4px;margin-top:40px;page-break-before:always}}
h3{{margin-top:28px}} h4{{color:#2b4a74}}
table.vocab{{border-collapse:collapse;width:100%;margin:10px 0 16px;font-size:14px}}
table.vocab th{{background:{ACCENT};color:white;text-align:left;padding:6px 8px}}
table.vocab td{{border-bottom:1px solid #dbe5f1;padding:6px 8px;vertical-align:top}}
td.term{{font-weight:600;font-size:15px}} td.tr{{color:#4b5d78;font-style:italic}} .note{{font-weight:400;
font-size:12px;color:#6b7c95}} .star{{color:{GOLD}}}
.summary{{background:#eef5fd;border-left:4px solid {ACCENT};padding:10px 16px;margin:14px 0}}
.quiz{{background:#fffaf0;border:1px solid #f3dfa6;border-radius:8px;padding:10px 16px;margin:14px 0}}
.exercise{{background:#f5f8fc;border:1px solid #dbe5f1;border-radius:8px;padding:10px 16px;margin:14px 0}}
.choices{{list-style:none;padding-left:10px}} details{{margin-top:8px;color:#2b4a74}}
.meta{{color:#4b5d78;font-size:13px}}
@media print{{details{{display:block}} details>summary{{display:none}} a{{color:inherit;text-decoration:none}}}}
"""


def lesson_html(project: Project, chapter: Chapter) -> str:
    code, locale = project.target_of(chapter)
    lang = languages.get(code)
    translit = bool(lang and lang.non_latin) or any(v.translit for v in chapter.vocab)
    num = project.lesson_number(chapter)
    head = f"Leçon {num} — " if num else ""
    parts = [f'<section class="lesson"><h3>{head}{_e(chapter.title)}</h3>',
             f'<div class="meta">{_e(languages.locale_name(locale) if locale else languages.language_name(code))}'
             f' · niveau {_e(project.level_of(chapter))}' + (f" · {_e(chapter.theme)}" if chapter.theme else "")
             + "</div>"]
    if chapter.words():
        parts += ["<h4>Vocabulaire</h4>", _vocab_table(chapter.words(), translit)]
    if chapter.phrases():
        parts += ["<h4>Phrases utiles</h4>", _vocab_table(chapter.phrases(), translit, phrases=True)]
    if chapter.text.strip():
        parts.append(_paragraphs_html(chapter.text))
    parts.append(_questions_html(chapter.questions, "Questions de compréhension"))
    ex = project.exercises_of(chapter)
    pairs = [v for v in chapter.words() + chapter.phrases() if v.translation.strip()][:15]
    if "translation" in ex and pairs:
        rows = "".join(f"<li>{_e(v.translation)} → <span dir='auto'><b>{_e(v.term)}</b></span>"
                       + (f" <i>({_e(v.translit)})</i>" if v.translit else "") + "</li>" for v in pairs)
        parts.append(f'<div class="exercise"><b>Traduction différée — réponses</b><ol>{rows}</ol></div>')
    if "dictation" in ex:
        sentences = [p.term for p in chapter.phrases()] or [w.example for w in chapter.words() if w.example]
        if sentences:
            rows = "".join(f"<li dir='auto'>{_e(s)}</li>" for s in sentences[:5])
            parts.append(f'<div class="exercise"><b>Dictée — corrigé</b><ol>{rows}</ol></div>')
    if chapter.summary.strip():
        parts.append('<div class="summary"><b>Ce qu\'il faut retenir</b>' + _paragraphs_html(chapter.summary)
                     + "</div>")
    parts.append(_questions_html(chapter.quiz, "Quiz"))
    parts.append("</section>")
    return "\n".join(p for p in parts if p)


def glossary(project: Project, favorites_only: bool = False) -> dict[str, list[tuple[Chapter, VocabItem]]]:
    """Mots et phrases de toutes les leçons, par langue apprise, triés alphabétiquement."""
    out: dict[str, list[tuple[Chapter, VocabItem]]] = {}
    for ch, it in project.all_vocab():
        if favorites_only and not it.favorite:
            continue
        code, _loc = project.target_of(ch)
        out.setdefault(code, []).append((ch, it))
    for code in out:
        out[code].sort(key=lambda pair: pair[1].term.lower())
    return out


def glossary_html(project: Project) -> str:
    parts = []
    for code, pairs in glossary(project).items():
        lang = languages.get(code)
        translit = bool(lang and lang.non_latin) or any(v.translit for _c, v in pairs)
        parts.append(f"<h3>Glossaire — {_e(languages.language_name(code, True))}</h3>")
        parts.append(_vocab_table([v for _c, v in pairs], translit))
    return "\n".join(parts)


def handout_html(project: Project) -> str:
    meta = project.metadata
    title = meta.title or "Cours de langue"
    body, toc = [], []
    for mi, (module, lessons) in enumerate(project.modules(), 1):
        if module:
            anchor = f"m{mi}"
            toc.append(f'<li><a href="#{anchor}">{_e(module)}</a><ol>'
                       + "".join(f"<li>{_e(c.title)}</li>" for c in lessons) + "</ol></li>")
            body.append(f'<h2 id="{anchor}">{_e(module)}</h2>')
        else:
            toc += [f"<li>{_e(c.title)}</li>" for c in lessons]
        for c in lessons:
            body.append(lesson_html(project, c))
    gl = glossary_html(project)
    if gl:
        toc.append('<li><a href="#glossaire">Glossaire</a></li>')
        body.append(f'<h2 id="glossaire">Glossaire</h2>{gl}')
    target = languages.locale_name(meta.target_locale) if meta.target_locale else \
        languages.language_name(meta.target_language)
    author = f" — {_e(meta.author)}" if meta.author else ""
    return f"""<!doctype html><html lang="{_e(meta.language or 'fr')}"><head><meta charset="utf-8">
<title>{_e(title)}</title><style>{_style()}</style></head><body>
<h1>{_e(title)}</h1>
<div class="sub">{_e(target)} · niveau {_e(meta.level)}{author} · support écrit généré le {time.strftime('%d/%m/%Y')}
</div>
<h3>Sommaire</h3><ol>{''.join(toc)}</ol>
{''.join(body)}
</body></html>"""


def write_handout(project: Project, target: Path) -> Path:
    target.write_text(handout_html(project), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------------------
# Flashcards imprimables (recto-verso)
# ---------------------------------------------------------------------------------------
CARDS_PER_PAGE = 8  # 2 colonnes × 4 lignes sur une page A4


def flashcards_html(project: Project, items: list[tuple[Chapter, VocabItem]] | None = None) -> str:
    """Pages de recto (langue apprise) puis de verso (traduction), dans l'ordre miroir pour une impression
    recto-verso bord long : chaque traduction tombe au dos de son mot."""
    items = items if items is not None else project.all_vocab()
    pages = []
    for start in range(0, len(items), CARDS_PER_PAGE):
        chunk = items[start:start + CARDS_PER_PAGE]
        fronts, backs = [], []
        for ch, it in chunk:
            fronts.append(f'<div class="card front"><div class="term" dir="auto">{_e(it.term)}</div>'
                          + (f'<div class="tr">{_e(it.translit)}</div>' if it.translit else "")
                          + f'<div class="lesson">{_e(ch.title)}</div></div>')
            ex = (f'<div class="ex" dir="auto">{_e(it.example)}</div>' if it.example else "") + \
                 (f'<div class="ext">{_e(it.example_translation)}</div>' if it.example_translation else "")
            backs.append(f'<div class="card back"><div class="trans">{_e(it.translation)}</div>{ex}'
                         + (f'<div class="note">{_e(it.notes)}</div>' if it.notes else "") + "</div>")
        while len(fronts) < CARDS_PER_PAGE:
            fronts.append('<div class="card empty"></div>')
            backs.append('<div class="card empty"></div>')
        # verso : colonnes inversées sur chaque ligne (impression recto-verso)
        mirrored = []
        for row in range(0, CARDS_PER_PAGE, 2):
            mirrored += [backs[row + 1], backs[row]]
        pages.append('<div class="page">' + "".join(fronts) + "</div>")
        pages.append('<div class="page">' + "".join(mirrored) + "</div>")
    title = project.metadata.title or "Flashcards"
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>{_e(title)} — flashcards</title>
<style>
@page{{size:A4;margin:10mm}}
body{{margin:0;font-family:'Segoe UI',system-ui,'Noto Sans','Microsoft YaHei','Yu Gothic','Malgun Gothic',sans-serif;
color:{INK}}}
.help{{max-width:180mm;margin:10mm auto;color:#4b5d78}} @media print{{.help{{display:none}}}}
.page{{width:190mm;height:277mm;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:repeat(4,1fr);
gap:0;margin:0 auto;page-break-after:always}}
.card{{border:1px dashed #9fb3cc;display:flex;flex-direction:column;align-items:center;justify-content:center;
text-align:center;padding:6mm;box-sizing:border-box;position:relative}}
.front{{background:linear-gradient(160deg,#ffffff 60%,#eef5fd)}}
.front .term{{font-size:22pt;font-weight:700;color:{ACCENT}}} .front .tr{{margin-top:3mm;font-style:italic;
color:#4b5d78}} .front .lesson{{position:absolute;bottom:3mm;font-size:8pt;color:#9fb3cc}}
.back{{background:#fffdf5;border-color:{GOLD}}} .back .trans{{font-size:18pt;font-weight:600}}
.back .ex{{margin-top:4mm;font-size:11pt}} .back .ext{{font-size:10pt;color:#4b5d78;font-style:italic}}
.note{{margin-top:3mm;font-size:9pt;color:#6b7c95}} .empty{{border-color:transparent}}
</style></head><body>
<div class="help"><b>{_e(title)}</b> — {len(items)} cartes. Imprimez en recto-verso (retournement sur le bord long),
puis découpez en suivant les pointillés : chaque traduction se trouve au dos de son mot.</div>
{''.join(pages)}
</body></html>"""


def write_flashcards(project: Project, target: Path, favorites_only: bool = False) -> Path:
    items = [(c, v) for c, v in project.all_vocab() if v.favorite or not favorites_only]
    target.write_text(flashcards_html(project, items), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------------------
# Anki : CSV + un fichier audio par mot
# ---------------------------------------------------------------------------------------
@dataclass
class AnkiResult:
    csv: Path
    media_dir: Path
    cards: int
    audio: int
    errors: list[str]


AudioMaker = Callable[[Chapter, VocabItem, Path], Path | None]


def anki_media_name(it: VocabItem) -> str:
    return f"polyglotte_{it.id}.mp3"


def _tag(text: str) -> str:
    return re.sub(r"[^\w-]+", "_", text.strip(), flags=re.UNICODE).strip("_")[:40]


def write_anki(project: Project, out_dir: Path, make_audio: AudioMaker | None = None,
               progress: Callable[[int, int], None] | None = None, favorites_only: bool = False) -> AnkiResult:
    """CSV importable dans Anki (Fichier → Importer) et dossier des sons à copier dans « collection.media ».

    ``make_audio(chapitre, élément, cible)`` produit le MP3 d'un mot (voix native) ; sans lui, pas d'audio."""
    out_dir.mkdir(parents=True, exist_ok=True)
    media = out_dir / "collection.media"
    media.mkdir(exist_ok=True)
    name = course_name = project.metadata.title or "Polyglotte"
    target = out_dir / f"{_tag(name) or 'cours'}_anki.csv"
    items = [(c, v) for c, v in project.all_vocab() if v.favorite or not favorites_only]
    errors: list[str] = []
    n_audio = 0
    with target.open("w", encoding="utf-8", newline="") as fh:
        fh.write("#separator:Semicolon\n#html:true\n#columns:Recto;Verso;Prononciation;Exemple;Traduction de "
                 "l'exemple;Audio;Tags\n#tags column:7\n")
        w = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        for i, (ch, it) in enumerate(items, 1):
            sound = ""
            if make_audio is not None:
                try:
                    produced = make_audio(ch, it, media / anki_media_name(it))
                    if produced is not None and Path(produced).exists():
                        sound = f"[sound:{Path(produced).name}]"
                        n_audio += 1
                except Exception as exc:  # un mot sans audio ne bloque pas l'export
                    msg = f"Audio de « {it.term} » non produit : {exc}"
                    if len(errors) < 20:
                        errors.append(msg)
            code, _loc = project.target_of(ch)
            tags = " ".join(t for t in (_tag(course_name), _tag(ch.module), _tag(ch.title), code,
                                        "favori" if it.favorite else "", "phrase" if it.kind == "phrase" else "") if t)
            w.writerow([html.escape(it.term) + (" " + sound if sound else ""), html.escape(it.translation), html.escape(it.translit),
                        html.escape(it.example), html.escape(it.example_translation), sound, tags])
            if progress:
                progress(i, len(items))
    (out_dir / "Comment importer dans Anki.txt").write_text(
        "1. Copiez le contenu du dossier « collection.media » dans le dossier « collection.media » de votre profil "
        "Anki (Anki : Outils → Vérifier les médias → Afficher les fichiers, ou %APPDATA%\\Anki2\\<profil>\\"
        "collection.media).\n"
        f"2. Dans Anki : Fichier → Importer, choisissez « {target.name} ».\n"
        "3. Type de note : « Basique (et carte inversée) » conseillé ; les colonnes sont reconnues automatiquement "
        "(Recto, Verso, Prononciation, Exemple, Audio, Tags).\n"
        "4. Le son de chaque mot est joué avec le recto ; il figure aussi dans la colonne « Audio ».\n",
        encoding="utf-8")
    return AnkiResult(target, media, len(items), n_audio, errors)
