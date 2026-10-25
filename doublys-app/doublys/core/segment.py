"""Découpage de la transcription (mots horodatés) en répliques à doubler."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Line

_SENT_END = re.compile(r"[.!?…]+[\"')\]»”’]*$")
_SOFT_END = re.compile(r"[,;:—–-]+[\"')\]»”’]*$")


@dataclass
class Word:
    start: float
    end: float
    text: str

    @property
    def sentence_end(self) -> bool:
        return bool(_SENT_END.search(self.text.strip()))

    @property
    def soft_end(self) -> bool:
        return bool(_SOFT_END.search(self.text.strip()))


def to_words(raw: list) -> list[Word]:
    """[[début, fin, mot, …], …] (Whisper) → mots propres, triés, sans durée négative."""
    out: list[Word] = []
    for item in raw or []:
        try:
            start, end, text = float(item[0]), float(item[1]), str(item[2])
        except (IndexError, TypeError, ValueError):
            continue
        if not text.strip():
            continue
        if out and start < out[-1].end:
            start = out[-1].end
        out.append(Word(start, max(start + 0.02, end), text))
    return out


def join_words(words: list[Word]) -> str:
    text = "".join(w.text if w.text.startswith((" ", "'", "’")) or i == 0 else " " + w.text
                   for i, w in enumerate(words))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.!?;:…])", r"\1", text)


def _best_split(words: list[Word], min_part: float) -> int:
    """Indice après lequel couper une réplique trop longue : ponctuation et pauses privilégiées."""
    t0, t1 = words[0].start, words[-1].end
    best, best_score = len(words) // 2, -1e9
    for i in range(len(words) - 1):
        left, right = words[i].end - t0, t1 - words[i + 1].start
        if left < min_part or right < min_part:
            continue
        gap = words[i + 1].start - words[i].end
        score = gap * 4.0 + (3.0 if words[i].sentence_end else 1.5 if words[i].soft_end else 0.0)
        score -= abs(left - right) / max(1.0, t1 - t0)  # parts équilibrées à égalité
        if score > best_score:
            best, best_score = i, score
    return best + 1


def segment_words(words: list[Word], pause: float = 0.7, max_len: float = 12.0, soft_len: float = 10.0,
                  min_fragment: float = 0.6) -> list[list[Word]]:
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            gap = w.start - cur[-1].end
            dur = cur[-1].end - cur[0].start
            if gap > pause or cur[-1].sentence_end or (dur >= soft_len and cur[-1].soft_end):
                groups.append(cur)
                cur = []
        cur.append(w)
        if cur[-1].end - cur[0].start > max_len and len(cur) > 1:
            i = _best_split(cur, min(3.0, max_len / 3))
            groups.append(cur[:i])
            cur = cur[i:]
    if cur:
        groups.append(cur)
    # fragments très courts : rattachés au voisin le plus proche s'il n'est pas loin
    i = 0
    while i < len(groups):
        g = groups[i]
        if len(groups) > 1 and g[-1].end - g[0].start < min_fragment:
            gap_prev = g[0].start - groups[i - 1][-1].end if i > 0 else 1e9
            gap_next = groups[i + 1][0].start - g[-1].end if i + 1 < len(groups) else 1e9
            target = i - 1 if gap_prev <= gap_next else i + 1
            if min(gap_prev, gap_next) <= max(pause, 1.0):
                merged = groups[target] + g if target < i else g + groups[target]
                if merged[-1].end - merged[0].start <= max_len + 2.0:
                    groups[min(i, target)] = merged
                    del groups[max(i, target)]
                    i = max(0, min(i, target))
                    continue
        i += 1
    return groups


def lines_from_words(raw_words: list, pause: float = 0.7, max_len: float = 12.0,
                     min_fragment: float = 0.6) -> list[Line]:
    words = to_words(raw_words)
    soft = max(4.0, min(10.0, max_len - 2.0))
    lines = []
    for g in segment_words(words, pause, max_len, soft, min_fragment):
        lines.append(Line(start=round(g[0].start, 3), end=round(g[-1].end, 3), en=join_words(g),
                          words=[[round(w.start, 3), round(w.end, 3), w.text] for w in g]))
    return lines


def split_line(line: Line, at: float | None = None) -> tuple[Line, Line] | None:
    """Coupe une réplique en deux (au mot le plus proche de ``at``, sinon au meilleur endroit)."""
    words = to_words(line.words)
    if len(words) < 2:
        return None
    if at is None:
        i = _best_split(words, 0.0)
    else:
        i = min(range(1, len(words)), key=lambda k: abs(words[k].start - at))
    a, b = words[:i], words[i:]
    first = Line(start=line.start, end=a[-1].end, en=join_words(a), person_id=line.person_id,
                 words=[[w.start, w.end, w.text] for w in a])
    second = Line(start=b[0].start, end=line.end, en=join_words(b), person_id=line.person_id,
                  words=[[w.start, w.end, w.text] for w in b])
    return first, second


def merge_lines(a: Line, b: Line) -> Line:
    first, second = (a, b) if a.start <= b.start else (b, a)
    fr = " ".join(t for t in (first.fr.strip(), second.fr.strip()) if t)
    return Line(start=first.start, end=max(first.end, second.end), en=f"{first.en} {second.en}".strip(), fr=fr,
                person_id=first.person_id or second.person_id, words=first.words + second.words,
                fr_edited=first.fr_edited or second.fr_edited)
