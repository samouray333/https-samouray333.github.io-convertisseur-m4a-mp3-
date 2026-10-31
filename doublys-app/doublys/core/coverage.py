"""Couverture de la VF : chaque passage parlé a une réplique doublée, ou il est signalé « Parole sans VF ».

La parole est détectée par Silero VAD (seuil bas) sur le son d'origine ET sur la voix isolée : un passage
manqué par l'un est rattrapé par l'autre (voix sous la musique, voix filtrée sous un casque, cri court).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import Project

log = logging.getLogger(__name__)

SPEECH_FILE = "parole_couverture.json"  # passages parlés (seuil bas, son d'origine + voix isolée)
DROPPED_FILE = "ecartes.json"  # éléments écartés du doublage, avec la raison
MIN_GAP = 0.4  # un passage parlé plus court sans réplique n'est pas signalé
EDGE = 0.25  # tolérance autour d'une réplique (fin des mots, souffle, marge du détecteur de parole)
SHORT_SHOUT = 1.0  # « garder les cris d'origine » : passages plus courts gardés en VO
VAD_OPTIONS = {"threshold": 0.35, "min_speech_ms": 150, "min_silence_ms": 300, "pad_ms": 100}
GAP_STATES = {"open": "à traiter", "ignored": "ne pas doubler", "vo": "voix d'origine gardée"}

_cache: dict[str, tuple[float, list]] = {}


# ---------------------------------------------------------------------------------------
# Intervalles
# ---------------------------------------------------------------------------------------
def merge(intervals, join: float = 0.0) -> list[list[float]]:
    """Union d'intervalles [[début, fin], …] (ceux séparés de moins de ``join`` secondes sont réunis)."""
    out: list[list[float]] = []
    for a, b in sorted([float(x[0]), float(x[1])] for x in intervals if float(x[1]) > float(x[0])):
        if out and a <= out[-1][1] + join:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def subtract(regions, covers) -> list[list[float]]:
    """Parties de ``regions`` non recouvertes par ``covers``."""
    covers = merge(covers)
    out = []
    for a, b in merge(regions):
        cur = a
        for c0, c1 in covers:
            if c1 <= cur or c0 >= b:
                continue
            if c0 > cur:
                out.append([cur, c0])
            cur = max(cur, c1)
            if cur >= b:
                break
        if cur < b:
            out.append([cur, b])
    return out


def total(intervals) -> float:
    return sum(b - a for a, b in merge(intervals))


# ---------------------------------------------------------------------------------------
# Parole détectée
# ---------------------------------------------------------------------------------------
def _work(project: Project, name: str) -> Path:
    from . import project as project_io

    return project_io.work_file(project, name)


def load_speech(project: Project) -> list[list[float]] | None:
    try:
        p = _work(project, SPEECH_FILE)
    except Exception:
        return None
    if not p.exists():
        return None
    key = str(p)
    mtime = p.stat().st_mtime
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    _cache[key] = (mtime, data)
    return data


def detect_speech(project: Project, tool, sources: list[Path]) -> list[list[float]]:
    """Union des passages parlés trouvés dans chaque source (WAV 16 kHz) ; enregistrée pour la suite."""
    found = []
    for src in sources:
        if src is not None and Path(src).exists():
            found += tool.vad(src, **VAD_OPTIONS)
    speech = merge(found, join=0.05)
    _work(project, SPEECH_FILE).write_text(json.dumps(speech), encoding="utf-8")
    return speech


# ---------------------------------------------------------------------------------------
# Éléments écartés (journal clair)
# ---------------------------------------------------------------------------------------
def load_dropped(project: Project) -> list[dict]:
    try:
        p = _work(project, DROPPED_FILE)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except (ValueError, OSError):
        return []


def save_dropped(project: Project, origin: str, items: list[dict]) -> None:
    """Remplace les éléments écartés par l'étape ``origin`` (« whisper », « sous-titres »…)."""
    keep = [d for d in load_dropped(project) if d.get("origin") != origin]
    keep += [{**d, "origin": origin} for d in items]
    keep.sort(key=lambda d: float(d.get("start", 0)))
    _work(project, DROPPED_FILE).write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------------------
# Passages parlés sans VF
# ---------------------------------------------------------------------------------------
def covered(project: Project) -> list[list[float]]:
    """Ce qui est traité : répliques (doublées ou volontairement laissées en VO), plages « ne pas doubler »,
    passages déjà marqués « ne pas doubler » ou « voix d'origine »."""
    out = [[ln.start, max(ln.end, ln.start + (ln.duration or 0.0))] for ln in project.lines]
    out += [[float(a), float(b)] for a, b in project.no_dub_ranges]
    out += [[g["start"], g["end"]] for g in project.gaps if g.get("state") in ("ignored", "vo")]
    return out


def update(project: Project, speech: list[list[float]] | None = None) -> list[dict]:
    """Recalcule ``project.gaps`` (les choix déjà faits sur un passage sont gardés)."""
    speech = speech if speech is not None else load_speech(project)
    if speech is None:
        return project.gaps
    decided = [g for g in project.gaps if g.get("state") in ("ignored", "vo")]
    base = [[ln.start - EDGE, max(ln.end, ln.start + (ln.duration or 0.0)) + EDGE] for ln in project.lines]
    base += [[float(a), float(b)] for a, b in project.no_dub_ranges]
    holes = [h for h in subtract(speech, base) if h[1] - h[0] >= MIN_GAP]
    dropped = load_dropped(project)
    gaps = []
    for a, b in holes:
        old = next((g for g in decided if min(g["end"], b) - max(g["start"], a) > 0.5 * (b - a)), None)
        state = old["state"] if old else "open"
        if old is None and project.settings.keep_original_shouts and b - a < SHORT_SHOUT:
            state = "vo"
        hint = next((d.get("text", "") for d in dropped if min(float(d["end"]), b) > max(float(d["start"]), a)
                     and d.get("text")), "")
        gaps.append({"start": round(a, 2), "end": round(b, 2), "state": state, "text": hint})
    project.gaps = gaps
    return gaps


def open_gaps(project: Project) -> list[dict]:
    return [g for g in project.gaps if g.get("state") == "open"]


def failed_lines(project: Project) -> list:
    return [ln for ln in project.lines if ln.state == "error" and not ln.no_dub]


def summary(project: Project) -> tuple[str, int]:
    """(texte de l'indicateur, nombre de problèmes)."""
    lines = [ln for ln in project.lines if not ln.no_dub]
    speech = load_speech(project)
    gaps = open_gaps(project)
    failed = failed_lines(project) if project.step_done("dub") else []
    problems = len(gaps) + len(failed)
    if speech is None:
        return f"{len(lines)} répliques", problems
    if not problems:
        return f"{len(lines)} répliques, 100 % de la parole couverte", 0
    parts = []
    if gaps:
        parts.append(f"{len(gaps)} passage{'s' if len(gaps) > 1 else ''} parlé{'s' if len(gaps) > 1 else ''} "
                     "sans VF")
    if failed:
        parts.append(f"{len(failed)} réplique{'s' if len(failed) > 1 else ''} en échec")
    talk = total(speech)
    pct = 100.0 * (1.0 - total([[g["start"], g["end"]] for g in gaps]) / talk) if talk > 0 else 100.0
    return f"{len(lines)} répliques, {pct:.0f} % de la parole couverte · " + ", ".join(parts), problems


# ---------------------------------------------------------------------------------------
# Actions sur un passage parlé sans VF
# ---------------------------------------------------------------------------------------
def _invalidate_audio(project: Project) -> None:
    project.mark_step("dub", False)
    project.mark_step("mix", False)


def nearest_line(project: Project, start: float, end: float, max_dist: float = 1.5):
    """Réplique la plus proche d'un passage (à moins de ``max_dist`` secondes), ou None."""
    best, dist = None, max_dist
    for ln in project.lines:
        d = max(0.0, ln.start - end, start - ln.end)
        if d <= dist:
            best, dist = ln, d
    return best


def extend_neighbor(project: Project, start: float, end: float):
    """La réplique voisine (le sous-titre d'à côté) est élargie pour couvrir le passage, sans empiéter sur les
    autres répliques. Renvoie la réplique, ou None s'il n'y en a pas assez près."""
    ln = nearest_line(project, start, end)
    if ln is None:
        return None
    others = sorted((x for x in project.lines if x is not ln), key=lambda x: x.start)
    lo = max([x.end + 0.02 for x in others if x.end <= ln.start + 0.01] + [0.0])
    hi = min([x.start - 0.02 for x in others if x.start >= ln.end - 0.01] + [1e9])
    ln.start = round(max(lo, min(ln.start, start)), 3)
    ln.end = round(min(hi, max(ln.end, end)), 3)
    ln.audio_key = ""  # créneau changé : voix à refaire
    _invalidate_audio(project)
    update(project)
    return ln


def add_line(project: Project, start: float, end: float, en: str = "", fr: str = "", source: str = "manual"):
    """Nouvelle réplique sur un passage ; la personne est celle de la réplique la plus proche."""
    from .models import Line

    near = nearest_line(project, start, end, max_dist=1e9)
    ln = Line(start=round(start, 3), end=round(end, 3), en=en.strip(), fr=fr.strip(), fr_edited=bool(fr.strip()),
              source=source, person_id=near.person_id if near is not None else "")
    if not ln.person_id and project.people:
        ln.person_id = project.people[0].id
    project.lines.append(ln)
    project.lines.sort(key=lambda x: x.start)
    _invalidate_audio(project)
    update(project)
    return ln


def set_state(project: Project, start: float, end: float, state: str) -> None:
    """« open » (à traiter), « ignored » (ne pas doubler : bruit, cri) ou « vo » (voix d'origine gardée)."""
    for g in project.gaps:
        if abs(g["start"] - start) < 0.01 and abs(g["end"] - end) < 0.01:
            g["state"] = state
    update(project)
