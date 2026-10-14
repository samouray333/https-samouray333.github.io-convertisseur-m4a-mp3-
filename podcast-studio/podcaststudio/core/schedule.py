"""Calendrier de publication : dates des épisodes, planification régulière, état de chaque épisode."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from .models import Chapter

FREQUENCIES = {"week": "Chaque semaine", "2weeks": "Toutes les deux semaines", "month": "Chaque mois",
               "day": "Chaque jour"}


def parse(d: str) -> date | None:
    try:
        return date.fromisoformat(d[:10]) if d else None
    except ValueError:
        return None


def add_step(d: date, every: str, n: int = 1) -> date:
    if every == "day":
        return d + timedelta(days=n)
    if every == "2weeks":
        return d + timedelta(weeks=2 * n)
    if every == "month":
        month = d.month - 1 + n
        year = d.year + month // 12
        month = month % 12 + 1
        return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))
    return d + timedelta(weeks=n)


def plan_dates(episodes: list[Chapter], start: date, every: str = "week", only_missing: bool = True) -> int:
    """Donne une date aux épisodes (dans l'ordre de la liste) ; renvoie le nombre d'épisodes planifiés.

    Avec ``only_missing``, les dates déjà fixées sont gardées et la suite reprend après la plus récente."""
    targets = [c for c in episodes if c.include and (not only_missing or not parse(c.pub_date))]
    if not targets:
        return 0
    current = start
    if only_missing:
        fixed = [parse(c.pub_date) for c in episodes if parse(c.pub_date)]
        if fixed and max(fixed) >= current:
            current = add_step(max(fixed), every)
    for i, c in enumerate(targets):  # calculé depuis la date de départ : pas de dérive en fin de mois
        c.pub_date = add_step(current, every, i).isoformat()
    return len(targets)


def status(chapter: Chapter, produced: bool) -> str:
    if chapter.published:
        return "Publié"
    if not chapter.text.strip():
        return "À écrire"
    return "Produit" if produced else "Écrit"


def next_episode(episodes: list[Chapter], today: date | None = None) -> Chapter | None:
    today = today or date.today()
    upcoming = [(parse(c.pub_date), c) for c in episodes if c.include and parse(c.pub_date) and not c.published]
    upcoming = [(d, c) for d, c in upcoming if d >= today]
    return min(upcoming, key=lambda x: x[0])[1] if upcoming else None
