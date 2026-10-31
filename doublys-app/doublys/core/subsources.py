"""Sous-titres déjà présents : pistes de la vidéo, fichier à côté, lecture (SRT, ASS/SSA, WebVTT), nettoyage.

Ordre de choix : français (la traduction est alors sautée), puis anglais, puis autre langue ; à langue égale, une
piste intégrée passe avant un fichier. Les sous-titres incrustés dans l'image (OCR) sont proposés quand il n'y a
ni piste ni fichier.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import ffmpeg

TEXT_CODECS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}
IMAGE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}
SIDE_EXTS = (".srt", ".ass", ".ssa", ".vtt")
LANG_TAGS = {"eng": "en", "en": "en", "fre": "fr", "fra": "fr", "fr": "fr", "jpn": "ja", "ja": "ja", "spa": "es",
             "es": "es", "ger": "de", "deu": "de", "de": "de", "ita": "it", "it": "it", "por": "pt", "pt": "pt",
             "kor": "ko", "ko": "ko", "chi": "zh", "zho": "zh", "zh": "zh", "rus": "ru", "ru": "ru"}
# styles ASS à ne pas doubler : panneaux, génériques, chansons
SKIP_STYLE = re.compile(r"sign|^op\b|^ed\b|opening|ending|karaok|song|title|insert|lyric|kfx|credit|note|\bop[ _-]|"
                        r"\bed[ _-]|_op\b|_ed\b", re.IGNORECASE)
_FR_WORDS = {"le", "la", "les", "des", "est", "et", "je", "tu", "vous", "nous", "pas", "une", "un", "que", "qui",
             "ce", "c'est", "dans", "pour", "avec", "mais", "il", "elle", "on", "ne", "du", "au", "mon", "ton"}
_EN_WORDS = {"the", "and", "you", "is", "are", "to", "of", "it", "i", "we", "that", "this", "what", "my", "your",
             "don't", "i'm", "it's", "be", "have", "do", "not", "with", "for", "on", "in", "me", "he", "she"}


@dataclass
class Cue:
    start: float
    end: float
    text: str
    style: str = ""
    kind: str = "dialog"  # dialog | sign (panneau) | song (générique chanté) | empty
    conf: float = 1.0  # confiance (OCR)
    reason: str = ""  # pourquoi il est écarté du doublage

    @property
    def dub(self) -> bool:
        return self.kind == "dialog"


@dataclass
class Candidate:
    kind: str  # track | file | ocr
    language: str = ""
    label: str = ""
    track: int = -1
    path: str = ""
    codec: str = ""
    forced: bool = False
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "language": self.language, "label": self.label, "track": self.track,
                "path": self.path, "codec": self.codec, "forced": self.forced}


# ---------------------------------------------------------------------------------------
# Langue
# ---------------------------------------------------------------------------------------
def lang_from_tag(tag: str) -> str:
    return LANG_TAGS.get((tag or "").strip().lower(), "")


def guess_language(texts: list[str]) -> str:
    """Français ou anglais d'après les mots les plus courants (vide si on ne sait pas)."""
    fr = en = 0
    for t in texts[:300]:
        for w in re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", t.lower()):
            fr += w in _FR_WORDS
            en += w in _EN_WORDS
    if fr + en < 5:
        return ""
    return "fr" if fr > en else "en"


def lang_from_name(name: str) -> str:
    """Suffixe de langue d'un fichier : « Episode.en.srt », « Episode.fre.ass », « Episode (EN, OCR).srt »."""
    stem = Path(name).stem.lower()
    m = re.search(r"[.\-_ (\[]([a-z]{2,3})(?:[,)\] ].*)?$", stem)
    return lang_from_tag(m.group(1)) if m else ""


# ---------------------------------------------------------------------------------------
# Lecture des formats
# ---------------------------------------------------------------------------------------
def _ts(text: str) -> float:
    text = text.strip().replace(",", ".")
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError:
        return -1.0


_TIMING = re.compile(r"(\d+:\d{2}(?::\d{2})?[.,]\d{1,3})\s*-->\s*(\d+:\d{2}(?::\d{2})?[.,]\d{1,3})")


def parse_srt(text: str) -> list[Cue]:
    """SRT et WebVTT (mêmes blocs « début --> fin » puis texte)."""
    cues = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff"))
    for block in blocks:
        lines = block.strip("\n").split("\n")
        for i, row in enumerate(lines):
            m = _TIMING.search(row)
            if m:
                body = "\n".join(lines[i + 1:]).strip()
                a, b = _ts(m.group(1)), _ts(m.group(2))
                if a >= 0 and b > a:
                    cues.append(Cue(a, b, body))
                break
    return cues


def parse_ass(text: str) -> list[Cue]:
    cues = []
    fmt = ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]
    in_events = False
    for row in text.replace("\r\n", "\n").lstrip("\ufeff").split("\n"):
        s = row.strip()
        if s.startswith("["):
            in_events = s.lower() == "[events]"
            continue
        if not in_events:
            continue
        if s.lower().startswith("format:"):
            fmt = [x.strip().lower() for x in s.split(":", 1)[1].split(",")]
            continue
        if not s.lower().startswith("dialogue:"):
            continue
        values = s.split(":", 1)[1].split(",", len(fmt) - 1)
        if len(values) < len(fmt):
            continue
        d = dict(zip(fmt, (v.strip() if k != "text" else v for k, v in zip(fmt, values))))
        a, b = _ts(d.get("start", "")), _ts(d.get("end", ""))
        if a < 0 or b <= a:
            continue
        raw = d.get("text", "")
        cue = Cue(a, b, raw, style=d.get("style", ""))
        if re.search(r"\\an?[789]\b|\\an8|\\pos\(", raw) and not re.search(r"\\an?[123]\b", raw):
            cue.kind, cue.reason = "sign", "texte en haut de l'image (panneau)"
        if re.search(r"\\k[fo]?\d", raw, re.IGNORECASE):
            cue.kind, cue.reason = "song", "karaoké (générique chanté)"
        if cue.kind == "dialog" and SKIP_STYLE.search(cue.style or ""):
            cue.kind, cue.reason = "song" if re.search(r"op|ed|song|karaok|lyric", cue.style, re.I) else "sign", \
                f"style « {cue.style} »"
        if (d.get("effect") or "").strip() and not cue.reason:
            cue.kind, cue.reason = "sign", f"effet « {d['effect'].strip()} »"
        cues.append(cue)
    return cues


def load_file(path: Path) -> list[Cue]:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            if enc == "utf-16" and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            break
        except UnicodeDecodeError:
            continue
    ext = Path(path).suffix.lower()
    if ext in (".ass", ".ssa"):
        return parse_ass(text)
    return parse_srt(text)


# ---------------------------------------------------------------------------------------
# Nettoyage
# ---------------------------------------------------------------------------------------
def clean_text(text: str) -> str:
    """Balises ASS et HTML retirées, notes de traducteur ôtées, espaces normalisés (sauts de ligne gardés)."""
    t = text.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
    t = re.sub(r"\{[^}]*\}", "", t)  # {\an8}, {\i1}, {\k20}…
    t = re.sub(r"</?(?:i|b|u|s|font)[^>]*>", "", t, flags=re.IGNORECASE)
    t = html.unescape(t)
    t = re.sub(r"\((?:TL|T/N|TN|Note)[^)]*\)|\[(?:TL|T/N|TN|Note)[^\]]*\]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"(?im)^\s*(?:TL|T/N|TN)\s*(?:note)?\s*:.*$", "", t)
    t = re.sub(r"^\s*\[[^\]]{1,40}\]\s*", "", t)  # [musique], [Geki] en début de ligne
    t = re.sub(r"♪+|♫+", "", t)
    lines = [re.sub(r"[ \t]+", " ", x).strip() for x in t.split("\n")]
    return "\n".join(x for x in lines if x)


def split_two_voices(cue: Cue) -> list[Cue]:
    """« - Salut ! - Bonjour. » (sur une ou deux lignes) → deux sous-titres ; temps partagé au prorata des
    caractères (le recalage sur la parole affine ensuite)."""
    t = cue.text.strip()
    parts = [p.strip() for p in re.split(r"(?:^|\n|(?<=[.!?…»\"])\s+)[-–—]\s*", t) if p.strip()]
    starts_with_dash = bool(re.match(r"^[-–—]\s*\S", t))
    if len(parts) < 2 or not (starts_with_dash or "\n-" in t or "\n–" in t):
        return [cue]
    total_chars = sum(len(p) for p in parts) or 1
    out, cur = [], cue.start
    span = cue.end - cue.start
    for i, p in enumerate(parts):
        end = cue.end if i == len(parts) - 1 else cur + span * len(p) / total_chars
        out.append(Cue(round(cur, 3), round(end, 3), p.replace("\n", " "), cue.style, cue.kind, cue.conf))
        cur = end
    return out


def prepare(cues: list[Cue]) -> tuple[list[Cue], list[dict]]:
    """Nettoie, classe et coupe les sous-titres. Renvoie (gardés, écartés avec la raison)."""
    kept: list[Cue] = []
    dropped: list[dict] = []
    for c in sorted(cues, key=lambda x: (x.start, x.end)):
        text = clean_text(c.text)
        if not text or not re.search(r"\w", text):
            if c.text.strip():
                dropped.append({"start": c.start, "end": c.end, "text": c.text.strip()[:120],
                                "reason": "sous-titre vide après nettoyage"})
            continue
        c.text = text
        if c.kind != "dialog":
            dropped.append({"start": c.start, "end": c.end, "text": text[:120], "reason": c.reason or c.kind})
            continue
        for part in split_two_voices(c):
            part.text = re.sub(r"\s*\n\s*", " ", part.text).strip()
            if kept and kept[-1].text == part.text and part.start - kept[-1].end < 0.5:
                kept[-1].end = max(kept[-1].end, part.end)  # même sous-titre répété (doublon)
                continue
            kept.append(part)
    return kept, dropped


def merge_fragments(cues: list[Cue], max_gap: float = 0.3) -> list[Cue]:
    """Morceaux d'une même phrase très rapprochés (phrase non terminée, écart de moins de 0,3 s) réunis."""
    out: list[Cue] = []
    for c in cues:
        if out:
            prev = out[-1]
            unfinished = not re.search(r"[.!?…。！？\"»”)]\s*$", prev.text)
            if unfinished and 0 <= c.start - prev.end < max_gap and len(prev.text) + len(c.text) < 160:
                prev.end = max(prev.end, c.end)
                prev.text = f"{prev.text} {c.text}".strip()
                prev.conf = min(prev.conf, c.conf)
                continue
        out.append(Cue(c.start, c.end, c.text, c.style, c.kind, c.conf))
    return out


# ---------------------------------------------------------------------------------------
# Sources disponibles
# ---------------------------------------------------------------------------------------
def find_tracks(video: Path) -> list[Candidate]:
    try:
        streams = ffmpeg.probe(video).get("streams", [])
    except Exception:
        return []
    out = []
    n = 0
    for s in streams:
        if s.get("codec_type") != "subtitle":
            continue
        tags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
        disp = s.get("disposition") or {}
        codec = s.get("codec_name", "")
        lang = lang_from_tag(tags.get("language", ""))
        title = tags.get("title", "")
        forced = bool(disp.get("forced"))
        label = f"Piste {n + 1}" + (f" « {title} »" if title else "") + (f" ({lang})" if lang else "")
        c = Candidate("track", lang, label, n, codec=codec, forced=forced)
        if codec in IMAGE_CODECS:
            c.label += " : sous-titres en images, non pris en charge"
        elif forced or re.search(r"sign|song|forced", title, re.I):
            c.label += " : panneaux seulement"
        out.append(c)
        n += 1
    return out


def find_files(video: Path) -> list[Candidate]:
    video = Path(video)
    out = []
    try:
        siblings = sorted(video.parent.iterdir())
    except OSError:
        return []
    stem = video.stem.lower()
    for f in siblings:
        if f.suffix.lower() not in SIDE_EXTS or not f.is_file():
            continue
        name = f.name.lower()
        if not name.startswith(stem):
            continue
        rest = name[len(stem):len(name) - len(f.suffix)]
        if rest and not re.match(r"^[ ._\-(\[]", rest):
            continue  # « Episode 10.srt » n'est pas un fichier de « Episode 1.mkv »
        lang = lang_from_name(f.name)
        out.append(Candidate("file", lang, f"Fichier « {f.name} »", path=str(f)))
    return out


def usable(c: Candidate) -> bool:
    return c.kind == "ocr" or (c.kind == "file") or (c.codec in TEXT_CODECS and not c.forced
                                                     and "panneaux" not in c.label)


def rank(candidates: list[Candidate]) -> list[Candidate]:
    """Utilisables d'abord ; français, anglais puis autres ; piste avant fichier, fichier avant OCR."""
    lang_order = {"fr": 0, "en": 1}
    kind_order = {"track": 0, "file": 1, "ocr": 2}
    return sorted(candidates, key=lambda c: (not usable(c), lang_order.get(c.language, 2 if c.language else 3),
                                             kind_order.get(c.kind, 3)))


def extract_track(video: Path, cand: Candidate, out_dir: Path, cancel=None) -> Path:
    """Extrait une piste texte (ASS/SSA gardés en .ass pour leurs styles, le reste en .srt)."""
    ext = ".ass" if cand.codec in ("ass", "ssa") else ".srt"
    out = Path(out_dir) / f"piste{cand.track}{ext}"
    ffmpeg.run_ffmpeg(["-i", str(video), "-map", f"0:s:{cand.track}", "-c:s", "ass" if ext == ".ass" else "srt",
                       str(out)], cancel=cancel)
    return out
