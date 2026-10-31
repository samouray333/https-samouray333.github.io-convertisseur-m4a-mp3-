"""Contrôle qualité : signale les répliques à vérifier pour ne pas avoir à relire toute la vidéo."""

from __future__ import annotations

import re

from .models import Line, Project

ISSUE_LABELS = {
    "asr": "mots mal reconnus ?",
    "translation": "traduction à vérifier",
    "speaker": "personne incertaine",
    "overlap": "voix mêlées ou bruit",
    "long": "trop longue",
    "error": "erreur de voix",
    "ocr": "lecture des sous-titres douteuse",
}
LOW_OCR = 0.80
LOW_WORD = 0.35  # confiance de Whisper sous laquelle un mot est douteux
LOW_MEAN = 0.6
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
_LOOP = re.compile(r"(\b\w+(?:\W+\w+){0,3}\b)(?:\W+\1\b){3,}", re.IGNORECASE)


def check_line(line: Line, language: str = "en") -> list[list[str]]:
    issues: list[list[str]] = []
    if line.no_dub:
        return issues
    if line.source == "ocr" and line.ocr_conf < LOW_OCR:
        issues.append(["ocr", f"Sous-titre lu dans l'image avec une confiance de {line.ocr_conf:.0%} : relisez "
                              "le texte d'origine."])
    probs = [float(w[3]) for w in line.words if len(w) > 3 and w[3] is not None]
    if probs:
        doubtful = [str(w[2]).strip() for w in line.words if len(w) > 3 and w[3] is not None and w[3] < LOW_WORD]
        mean = sum(probs) / len(probs)
        if doubtful or mean < LOW_MEAN:
            shown = ", ".join(f"« {d} »" for d in doubtful[:4]) if doubtful else f"confiance {mean:.0%}"
            issues.append(["asr", f"Whisper hésite : {shown}"])
    en, fr = line.en.strip(), line.fr.strip()
    if en and not fr:
        issues.append(["translation", "Pas de traduction."])
    elif en and fr:
        if _CJK.search(fr) or fr.lower() == en.lower():
            issues.append(["translation", "Le texte n'a pas été traduit."])
        elif _LOOP.search(fr):
            issues.append(["translation", "Mots répétés en boucle."])
        elif not _CJK.search(en):  # rapport de longueur peu parlant pour le japonais ou le chinois
            ratio = len(fr) / max(1, len(en))
            if len(en) >= 12 and ratio < 0.4:
                issues.append(["translation", "Traduction bien plus courte que l'original : un passage manque ?"])
            elif len(en) >= 12 and ratio > 2.6:
                issues.append(["translation", "Traduction bien plus longue que l'original."])
    if line.person_id and line.length >= 0.8:
        if line.speaker_score < 0.35:
            issues.append(["overlap", "Voix peu ressemblante à sa personne : deux voix mêlées, musique ou bruit ?"])
        elif line.speaker_margin < 0.05:
            issues.append(["speaker", "Pourrait être dite par une autre personne."])
    if line.state == "long":
        issues.append(["long", line.message or "Trop longue pour le temps disponible."])
    elif line.state == "error":
        issues.append(["error", line.message or "La voix n'a pas pu être produite."])
    return issues


def check(project: Project) -> int:
    """Met à jour ``issues`` de chaque réplique ; renvoie le nombre de répliques à vérifier."""
    n = 0
    for ln in project.lines:
        ln.issues = [] if ln.checked else check_line(ln, project.settings.language)
        n += bool(ln.issues)
    from . import coverage

    try:
        coverage.update(project)  # passages parlés sans VF (rapide : comparaison d'intervalles)
    except Exception:  # noqa: BLE001 - projet sans dossier de travail (tests)
        pass
    return n


def summary(project: Project) -> str:
    counts: dict[str, int] = {}
    for ln in project.lines:
        for code, _msg in ln.issues:
            counts[code] = counts.get(code, 0) + 1
    if not counts:
        return "Aucune réplique à vérifier."
    parts = [f"{n} {ISSUE_LABELS.get(code, code)}" for code, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    total = sum(1 for ln in project.lines if ln.issues)
    return f"{total} réplique(s) à vérifier : " + ", ".join(parts) + "."
