"""Sous-titres SRT (français et langue d'origine) à partir des répliques, avec une couleur par personne."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from .models import Line, Project


def srt_time(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wrap(text: str, width: int = 42) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if " " not in text and len(text) > 22:  # japonais, chinois : coupure au caractère, deux lignes équilibrées
        half = (len(text) + 1) // 2
        return text[:half] + "\n" + text[half:]
    lines = textwrap.wrap(text, width) or [""]
    if len(lines) > 2:  # au plus deux lignes : on élargit
        lines = textwrap.wrap(text, max(width, len(text) // 2 + 6))
    return "\n".join(lines)


def subtitle_color(color: str) -> str:
    """Couleur « #RRGGBB » valide, sinon chaîne vide (texte blanc par défaut)."""
    color = (color or "").strip()
    return color.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) else ""


def person_colors(project: Project) -> dict[str, str]:
    """Personne -> couleur de ses sous-titres (vide si l'option « une couleur par personne » est désactivée)."""
    if not project.export.subtitle_colors:
        return {}
    return {p.id: c for p in project.people if (c := subtitle_color(p.color))}


def build_srt(lines: list[Line], lang: str = "fr", min_duration: float = 0.8,
              colors: dict[str, str] | None = None) -> str:
    """``colors`` : personne -> « #RRGGBB » (balise <font color> lue par VLC, MPC, mpv et l'incrustation)."""
    rows = sorted([ln for ln in lines if (ln.fr if lang == "fr" else ln.en).strip()], key=lambda x: x.start)
    out = []
    for i, ln in enumerate(rows):
        text = wrap(ln.fr if lang == "fr" else ln.en)
        color = (colors or {}).get(ln.person_id)
        if color:
            text = f'<font color="{color}">{text}</font>'
        end = max(ln.end, ln.start + (ln.duration if lang == "fr" and ln.duration else 0.0), ln.start + min_duration)
        if i + 1 < len(rows):
            end = min(end, rows[i + 1].start - 0.04)
        end = max(end, ln.start + 0.3)
        out.append(f"{len(out) + 1}\n{srt_time(ln.start)} --> {srt_time(end)}\n{text}\n")
    return "\n".join(out)


def write_srt(lines: list[Line], path: Path, lang: str = "fr", colors: dict[str, str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_srt(lines, lang, colors=colors), encoding="utf-8")
    return path
