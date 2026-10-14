"""Répétition espacée : révisions programmées à J+1, J+3, J+7, J+14 et J+30.

Quand une leçon est marquée « étudiée », chacun de ses mots et de ses phrases entre dans le calendrier : première
révision le lendemain, puis 3, 7, 14 et 30 jours après la révision précédente. Un mot raté revient à J+1.
Chaque séance donne un fichier audio de révision : le mot dans la langue d'explication, un silence pour le dire
dans la langue apprise, la bonne réponse, puis un silence pour la répéter.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from . import course, languages
from .models import REVIEW_STEPS, Chapter, Project, ReviewState, VocabItem


def today() -> dt.date:
    return dt.date.today()


def _d(value: str | dt.date | None) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def iso(day: dt.date) -> str:
    return day.isoformat()


def mark_studied(project: Project, chapter: Chapter, day: dt.date | None = None) -> int:
    """La leçon vient d'être étudiée : ses mots et phrases entrent dans le calendrier (première révision à J+1).

    Les éléments déjà programmés gardent leur progression. Renvoie le nombre d'éléments ajoutés."""
    day = day or today()
    project.studied[chapter.id] = iso(day)
    added = 0
    for it in chapter.vocab:
        if not it.term.strip() or it.id in project.reviews:
            continue
        project.reviews[it.id] = ReviewState(item_id=it.id, lesson_id=chapter.id, step=0,
                                             due=iso(day + dt.timedelta(days=REVIEW_STEPS[0])), seen=iso(day))
        added += 1
    return added


def unmark_studied(project: Project, chapter: Chapter) -> None:
    project.studied.pop(chapter.id, None)
    for it in chapter.vocab:
        project.reviews.pop(it.id, None)


def prune(project: Project) -> int:
    """Retire du calendrier les éléments supprimés des leçons."""
    alive = {v.id for _c, v in project.all_vocab()}
    dead = [k for k in project.reviews if k not in alive]
    for k in dead:
        del project.reviews[k]
    return len(dead)


def due_items(project: Project, day: dt.date | None = None, include_overdue: bool = True) -> list[ReviewState]:
    """Éléments à réviser ce jour-là (et ceux en retard)."""
    day = day or today()
    out = []
    for st in project.reviews.values():
        due = _d(st.due)
        if st.learned or due is None:
            continue
        if due == day or (include_overdue and due < day):
            out.append(st)
    out.sort(key=lambda s: (s.due, s.lesson_id))
    return out


def record_review(project: Project, item_id: str, success: bool = True, day: dt.date | None = None) -> ReviewState:
    """Note une révision : réussie → étape suivante (J+3, J+7…), ratée → retour à J+1."""
    day = day or today()
    st = project.reviews[item_id]
    st.last = iso(day)
    st.history.append(iso(day) + ("" if success else "!"))
    if success:
        st.step += 1
    else:
        st.step = 0
    if st.step < len(REVIEW_STEPS):
        st.due = iso(day + dt.timedelta(days=REVIEW_STEPS[st.step]))
    else:
        st.due = ""
    return st


def complete_session(project: Project, day: dt.date | None = None, failed: set[str] | None = None) -> int:
    """Séance terminée : chaque élément dû passe à l'étape suivante (sauf ceux ratés). Renvoie le nombre traité."""
    day = day or today()
    failed = failed or set()
    items = due_items(project, day)
    for st in items:
        record_review(project, st.item_id, st.item_id not in failed, day)
    return len(items)


def forecast(project: Project, start: dt.date | None = None, days: int = 30) -> dict[dt.date, list[ReviewState]]:
    """Calendrier prévisionnel : pour chaque jour, les éléments à réviser en supposant que chaque séance est
    faite et réussie à la date prévue (les retards sont rattachés au premier jour)."""
    start = start or today()
    end = start + dt.timedelta(days=days)
    out: dict[dt.date, list[ReviewState]] = {}
    for st in project.reviews.values():
        if st.learned:
            continue
        due = _d(st.due)
        step = st.step
        while due is not None and due <= end and step < len(REVIEW_STEPS):
            day = max(due, start)
            out.setdefault(day, []).append(st)
            step += 1
            due = due + dt.timedelta(days=REVIEW_STEPS[step]) if step < len(REVIEW_STEPS) else None
    return dict(sorted(out.items()))


@dataclass
class Progress:
    total: int  # éléments de toutes les leçons
    scheduled: int  # en cours de révision
    learned: int  # toutes les étapes franchies
    due_today: int
    lessons_studied: int
    lessons: int


def progress(project: Project, day: dt.date | None = None) -> Progress:
    total = len(project.all_vocab())
    learned = sum(1 for s in project.reviews.values() if s.learned)
    return Progress(total=total, scheduled=len(project.reviews) - learned, learned=learned,
                    due_today=len(due_items(project, day)),
                    lessons_studied=sum(1 for c in project.chapters if c.id in project.studied),
                    lessons=len(project.chapters))


def mastery(project: Project) -> float:
    """Avancement global (0 à 1) : chaque élément pèse selon le nombre d'étapes franchies."""
    items = project.all_vocab()
    if not items:
        return 0.0
    n = len(REVIEW_STEPS)
    score = sum(min(n, project.reviews[v.id].step) / n for _c, v in items if v.id in project.reviews)
    return score / len(items)


# ---------------------------------------------------------------------------------------
# Audio de révision
# ---------------------------------------------------------------------------------------
REVIEW_PREFIX = "__review_"


def review_id(day: dt.date) -> str:
    return f"{REVIEW_PREFIX}{iso(day)}__"


def is_review_id(chapter_id: str) -> bool:
    return chapter_id.startswith(REVIEW_PREFIX)


def items_for(project: Project, states: list[ReviewState]) -> list[tuple[Chapter, VocabItem]]:
    out = []
    for st in states:
        ch, it = project.vocab_by_id(st.item_id)
        if ch is not None and it is not None:
            out.append((ch, it))
    return out


def review_script(project: Project, pairs: list[tuple[Chapter, VocabItem]]) -> str:
    """Script d'une séance : consigne, puis pour chaque élément la traduction, un silence, la réponse, un silence."""
    if not pairs:
        return ""
    prod = project.production
    code, _locale = project.target_of(pairs[0][0])
    out = ["# " + course.t(project, "review_title"),
           course.t(project, "review_intro", n=len(pairs), language=course.target_name_for(project, code))]
    for ch, it in pairs:
        spec = course.target_spec(project, ch)
        lang = languages.get(spec)
        lcode = lang.code if lang else spec
        think = max(prod.translation_think_ms, languages.repeat_pause_ms(it.term, lcode, 1.0))
        repeat = languages.repeat_pause_ms(it.term, lcode, prod.repeat_factor)
        if it.translation.strip():
            out += [course.t(project, "how_say", text=course._clean(it.translation).rstrip(".?!")),
                    f"[pause {think}ms]"]
        out += [course._native(spec, it.term), f"[pause {repeat}ms]", course._native(spec, it.term), "[pause 800ms]"]
    out.append(course.t(project, "review_end"))
    return "\n\n".join(out)


def review_chapter(project: Project, day: dt.date, states: list[ReviewState] | None = None) -> Chapter | None:
    """Séance de révision d'un jour sous forme de « chapitre » à produire (None s'il n'y a rien à réviser)."""
    states = due_items(project, day) if states is None else states
    pairs = items_for(project, states)
    if not pairs:
        return None
    title = f"{course.t(project, 'review_title')} {day.strftime('%d/%m/%Y')} ({len(pairs)})"
    return Chapter(title=title, text=review_script(project, pairs), id=review_id(day))


def planned_sessions(project: Project, days: int = 30, start: dt.date | None = None) -> list[Chapter]:
    """Séances des ``days`` prochains jours (calendrier prévisionnel), prêtes à produire."""
    out = []
    for day, states in forecast(project, start, days).items():
        ch = review_chapter(project, day, states)
        if ch is not None:
            out.append(ch)
    return out
