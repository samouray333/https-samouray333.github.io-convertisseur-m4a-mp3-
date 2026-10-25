"""Traduction locale (Opus-MT) adaptée au doublage.

- Chaque réplique est traduite phrase par phrase : une phrase courte (« Almost. ») n'est plus avalée par sa voisine.
- Opus-MT propose plusieurs variantes par phrase ; on garde celle qui respecte le tutoiement ou le vouvoiement
  choisi entre les deux personnes qui se parlent (le même du début à la fin) et qui tient dans le temps disponible.
"""

from __future__ import annotations

import re
from collections import Counter

from .models import Line

N_BEST = 5
_SENT_SPLIT = re.compile(r"(?<=[.!?…])[\"')\]»”’]*\s+(?=[\"'(«“‘]*[A-Z0-9])")
TU_RE = re.compile(r"\b(tu|te|toi|ton|ta|tes|tien|tienne|tiens|tiennes)\b|\bt['’]", re.IGNORECASE)
VOUS_RE = re.compile(r"\b(vous|votre|vos|vôtre|vôtres)\b", re.IGNORECASE)
CONVERSATION_GAP = 10.0  # au-delà, deux répliques voisines ne sont pas une conversation


_CJK_SPLIT = re.compile(r"(?<=[。！？!?])(?=[^。！？!?」』）)\s])")


def split_sentences(text: str) -> list[str]:
    parts = []
    for chunk in _SENT_SPLIT.split(text.strip()):
        parts += [p.strip() for p in _CJK_SPLIT.split(chunk) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def register(text: str) -> str:
    """« tu », « vous » ou « » (aucun indice, ou les deux)."""
    tu, vous = bool(TU_RE.search(text)), bool(VOUS_RE.search(text))
    if tu and not vous:
        return "tu"
    if vous and not tu:
        return "vous"
    return ""


def listeners(lines: list[Line]) -> list[str]:
    """Personne à qui s'adresse chaque réplique : la plus proche voisine dite par quelqu'un d'autre."""
    out = []
    for i, ln in enumerate(lines):
        best, dist = "", CONVERSATION_GAP
        for j in range(max(0, i - 4), min(len(lines), i + 5)):
            other = lines[j]
            if j == i or not other.person_id or other.person_id == ln.person_id:
                continue
            d = (ln.start - other.end) if j < i else (other.start - ln.end)
            if d < dist:
                best, dist = other.person_id, max(0.0, d)
        out.append(best)
    return out


def pair_key(a: str, b: str) -> tuple[str, str] | None:
    return tuple(sorted((a, b))) if a and b else None


def choose(cands: list[str], wanted: str, budget: float) -> str:
    """Variante retenue : rang d'Opus-MT, registre voulu, longueur par rapport au budget de caractères."""
    best, best_score = cands[0] if cands else "", 1e9
    for rank, c in enumerate(cands):
        if not c:
            continue
        score = rank * 0.25
        reg = register(c)
        if wanted and reg and reg != wanted:
            score += 2.0
        if budget > 0 and len(c) > budget:
            score += (len(c) - budget) / max(8.0, budget) * 3.0
        if score < best_score:
            best, best_score = c, score
    return best


def translate_lines(lines: list[Line], budgets: list[float], translate_fn, todo: list[int] | None = None,
                    progress=None) -> dict[int, str]:
    """Traduit les répliques ``todo`` (toutes par défaut) de ``lines`` (triées) → {indice: français}.

    ``translate_fn(phrases, n_best)`` renvoie les variantes de chaque phrase. Les répliques déjà traduites et non
    refaites comptent dans le choix du tutoiement ou du vouvoiement de chaque paire de personnes."""
    todo = list(range(len(lines))) if todo is None else list(todo)
    sentences: list[str] = []
    owner: list[int] = []
    for i in todo:
        for sent in split_sentences(lines[i].en):
            sentences.append(sent)
            owner.append(i)
    per_line: dict[int, list[list[str]]] = {i: [] for i in todo}
    if sentences:
        cands = translate_fn(sentences, N_BEST)
        for k, i in enumerate(owner):
            c = cands[k]
            per_line[i].append(c if isinstance(c, list) else [c])

    # registre de chaque paire de personnes : vote sur les traductions existantes et les premières variantes
    who = listeners(lines)
    votes: dict[tuple, Counter] = {}
    for i, ln in enumerate(lines):
        key = pair_key(ln.person_id, who[i])
        if key is None:
            continue
        texts = [s[0] for s in per_line[i] if s] if i in per_line else [ln.fr]
        for t in texts:
            reg = register(t)
            if reg:
                votes.setdefault(key, Counter())[reg] += 1
    chosen = {k: c.most_common(1)[0][0] for k, c in votes.items() if c}

    out: dict[int, str] = {}
    for i in todo:
        wanted = chosen.get(pair_key(lines[i].person_id, who[i]), "")
        total = sum(len(s[0]) for s in per_line[i] if s) or 1
        parts = []
        for sent in per_line[i]:
            share = budgets[i] * len(sent[0]) / total if budgets[i] > 0 and sent else 0
            parts.append(choose(sent, wanted, share))
        out[i] = " ".join(p for p in parts if p).strip()
    if progress:
        progress(f"{len(todo)} répliques traduites")
    return out
