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


def _timed_rows(lines: list[Line], lang: str, min_duration: float) -> list[tuple[Line, float, float, str]]:
    """(réplique, début, fin, texte) : fin allongée pour la lecture, sans chevaucher la réplique suivante."""
    rows = sorted([ln for ln in lines if (ln.fr if lang == "fr" else ln.en).strip()], key=lambda x: x.start)
    out = []
    for i, ln in enumerate(rows):
        end = max(ln.end, ln.start + (ln.duration if lang == "fr" and ln.duration else 0.0), ln.start + min_duration)
        if i + 1 < len(rows):
            end = min(end, rows[i + 1].start - 0.04)
        out.append((ln, ln.start, max(end, ln.start + 0.3), ln.fr if lang == "fr" else ln.en))
    return out


def build_srt(lines: list[Line], lang: str = "fr", min_duration: float = 0.8,
              colors: dict[str, str] | None = None) -> str:
    """``colors`` : personne -> « #RRGGBB » (balise <font color> lue par VLC, MPC, mpv et l'incrustation)."""
    out = []
    for ln, start, end, text in _timed_rows(lines, lang, min_duration):
        text = wrap(text)
        color = (colors or {}).get(ln.person_id)
        if color:
            text = f'<font color="{color}">{text}</font>'
        out.append(f"{len(out) + 1}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
    return "\n".join(out)


def write_srt(lines: list[Line], path: Path, lang: str = "fr", colors: dict[str, str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_srt(lines, lang, colors=colors), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------------------
# ASS (Advanced SubStation) : un style par personne, police, contour et couleurs garantis
# ---------------------------------------------------------------------------------------
ASS_FORMAT = ("Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
              "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
              "MarginL, MarginR, MarginV, Encoding")


def ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_color(color: str) -> str:
    """« #RRGGBB » -> « &H00BBGGRR » (ordre inversé de l'ASS, opaque)."""
    c = subtitle_color(color) or "#FFFFFF"
    return f"&H00{c[5:7]}{c[3:5]}{c[1:3]}"


def _ass_field(text: str) -> str:
    """Nom de style ou de personne : pas de virgule (séparateur des champs ASS)."""
    return re.sub(r"\s+", " ", (text or "").replace(",", " ")).strip() or "?"


def _ass_text(text: str) -> str:
    # accolades et barres obliques inverses : réservées aux balises ASS
    return wrap(text).replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(lines: list[Line], people: list, lang: str = "fr", colors: dict[str, str] | None = None,
              width: int = 1920, height: int = 1080, title: str = "", min_duration: float = 0.8) -> str:
    """Sous-titres ASS : style « Défaut » (blanc) et un style coloré par personne ; nom de la personne gardé."""
    res_y = 1080
    res_x = int(round(res_y * width / height)) if width > 0 and height > 0 else 1920
    size = 62 if res_x >= res_y else 48  # vidéo verticale : texte plus petit pour tenir en largeur

    def style(name: str, color: str) -> str:
        return (f"Style: {name},Arial,{size},{ass_color(color)},&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,"
                f"0,1,3.2,1.5,2,{res_x // 24},{res_x // 24},{res_y // 18},1")

    styles = {"": "Défaut"}
    out_styles = [style("Défaut", "#FFFFFF")]
    names = {p.id: _ass_field(p.name) for p in people}
    for p in people:
        color = (colors or {}).get(p.id)
        if not color:
            continue
        name = names[p.id]
        while name in styles.values():  # deux personnes du même nom
            name += "+"
        styles[p.id] = name
        out_styles.append(style(name, color))
    out = ["[Script Info]", f"Title: {_ass_field(title) if title else 'Doublys'}", "ScriptType: v4.00+",
           "WrapStyle: 0", "ScaledBorderAndShadow: yes", f"PlayResX: {res_x}", f"PlayResY: {res_y}",
           "YCbCr Matrix: TV.709", "", "[V4+ Styles]", f"Format: {ASS_FORMAT}", *out_styles, "", "[Events]",
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for ln, start, end, text in _timed_rows(lines, lang, min_duration):
        st = styles.get(ln.person_id, "Défaut")
        out.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{st},{names.get(ln.person_id, '')},0,0,0,,"
                   f"{_ass_text(text)}")
    return "\n".join(out) + "\n"


def write_ass(lines: list[Line], people: list, path: Path, lang: str = "fr", colors: dict[str, str] | None = None,
              width: int = 1920, height: int = 1080, title: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # BOM UTF-8 : certains logiciels de sous-titres le demandent pour les accents
    path.write_text(build_ass(lines, people, lang, colors, width, height, title), encoding="utf-8-sig")
    return path
