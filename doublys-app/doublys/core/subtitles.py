"""Sous-titres SRT (français et anglais) à partir des répliques."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from .models import Line


def srt_time(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wrap(text: str, width: int = 42) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    lines = textwrap.wrap(text, width) or [""]
    if len(lines) > 2:  # au plus deux lignes : on élargit
        lines = textwrap.wrap(text, max(width, len(text) // 2 + 6))
    return "\n".join(lines)


def build_srt(lines: list[Line], lang: str = "fr", min_duration: float = 0.8) -> str:
    rows = sorted([ln for ln in lines if (ln.fr if lang == "fr" else ln.en).strip()], key=lambda x: x.start)
    out = []
    for i, ln in enumerate(rows):
        text = ln.fr if lang == "fr" else ln.en
        end = max(ln.end, ln.start + (ln.duration if lang == "fr" and ln.duration else 0.0), ln.start + min_duration)
        if i + 1 < len(rows):
            end = min(end, rows[i + 1].start - 0.04)
        end = max(end, ln.start + 0.3)
        out.append(f"{len(out) + 1}\n{srt_time(ln.start)} --> {srt_time(end)}\n{wrap(text)}\n")
    return "\n".join(out)


def write_srt(lines: list[Line], path: Path, lang: str = "fr") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_srt(lines, lang), encoding="utf-8")
    return path
