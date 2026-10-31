"""Sous-titres incrustés dans l'image : bande détectée, images lues en flux, changements repérés, OCR des lignes.

1. Bande : sur 60 images réparties, pixels « texte clair entouré de sombre » (blanc ou jaune à contour noir) ;
   la bande retenue est la zone du bas où ce texte revient le plus souvent.
2. Lecture : FFmpeg décode la vidéo et ne renvoie que la bande, en niveaux de gris (mémoire stable).
3. Changements : un sous-titre commence quand le masque du texte apparaît ou change, et finit quand il disparaît
   ou change (précision : une image d'analyse, 0,08 s à 12,5 images/s).
4. OCR : pour chaque sous-titre, l'image la plus nette est découpée en lignes, lues par RapidOCR (environnement
   « ocr », reconnaissance seule : environ 25 ms par ligne sur le processeur).
5. Fusion des textes quasi identiques consécutifs, nettoyage des confusions de lecture, écarts journalisés.
"""

from __future__ import annotations

import difflib
import logging
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .. import paths
from . import ffmpeg
from .subsources import Cue

log = logging.getLogger(__name__)

BRIGHT = 185  # luminance minimale du texte (blanc, jaune clair)
DARK = 70  # luminance maximale du contour
SAMPLE_WIDTH = 640
MAX_WIDTH = 1280  # largeur de la bande analysée (1080p réduit, 720p tel quel)
BATCH = 64  # sous-titres par fichier envoyé à l'OCR

Progress = Callable[[float, str], None]


# ---------------------------------------------------------------------------------------
# Masque du texte
# ---------------------------------------------------------------------------------------
def dilate(m: np.ndarray, r: int) -> np.ndarray:
    """Dilatation carrée de rayon ``r`` (séparable, sans dépendance)."""
    if r <= 0:
        return m
    out = m.copy()
    for d in range(1, r + 1):
        out[:, d:] |= m[:, :-d]
        out[:, :-d] |= m[:, d:]
    tmp = out.copy()
    for d in range(1, r + 1):
        out[d:, :] |= tmp[:-d, :]
        out[:-d, :] |= tmp[d:, :]
    return out


def text_mask(g: np.ndarray, near: int = 2) -> np.ndarray:
    """Pixels clairs qui touchent (à ``near`` pixels près) un pixel sombre : le texte et son contour."""
    return (g >= BRIGHT) & dilate(g <= DARK, near)


def similar(a: np.ndarray, b: np.ndarray, tol: float = 0.25) -> bool:
    """Même texte à l'écran : les deux masques se recouvrent (à un pixel près) à ``1 - tol`` près."""
    sa, sb = int(a.sum()), int(b.sum())
    if sa == 0 or sb == 0:
        return sa == sb
    da, db = dilate(a, 1), dilate(b, 1)
    diff = int((a & ~db).sum()) + int((b & ~da).sum())
    return diff <= tol * (sa + sb)


# ---------------------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------------------
def _even(x: float) -> int:
    return max(2, int(round(x / 2.0)) * 2)


def frame_at(video: Path, t: float, width: int, height: int) -> np.ndarray | None:
    """Une image (niveaux de gris, ``width`` x ``height``) à l'instant ``t``."""
    cmd = [ffmpeg.ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}",
           "-i", str(video), "-frames:v", "1", "-an", "-sn", "-vf", f"scale={width}:{height},format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60, **ffmpeg.popen_kwargs()).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    if len(out) < width * height:
        return None
    return np.frombuffer(out[:width * height], dtype=np.uint8).reshape(height, width)


@dataclass
class ZoneInfo:
    top: float  # fraction de la hauteur
    bottom: float
    presence: float  # part des images échantillonnées où du texte apparaît dans la bande
    thumb: np.ndarray | None = field(default=None, repr=False)  # image où la bande est la plus remplie


def detect_zone(video: Path, duration: float, vw: int, vh: int, samples: int = 60,
                cancel: threading.Event | None = None) -> ZoneInfo | None:
    """Bande du bas où apparaissent des sous-titres incrustés ; None s'il n'y en a pas."""
    if duration <= 0 or vw <= 0 or vh <= 0:
        return None
    samples = max(12, min(samples, int(duration / 10)))  # vidéo courte : moins d'images suffisent
    w = SAMPLE_WIDTH
    h = _even(vh * w / vw)
    masks, frames = [], []
    for i in range(samples):
        if cancel is not None and cancel.is_set():
            raise ffmpeg.Cancelled()
        g = frame_at(video, duration * (i + 0.5) / samples, w, h)
        if g is not None:
            masks.append(text_mask(g))
            frames.append(g)
    if len(masks) < 8:
        return None
    stack = np.stack(masks)
    static = stack.mean(axis=0) > 0.6  # logo, incrustation permanente : ce n'est pas un sous-titre
    stack &= ~static
    rows = stack.sum(axis=2) >= max(6, int(0.01 * w))  # (images, lignes) : la ligne contient du texte
    freq = rows.mean(axis=0)
    y0 = int(h * 0.55)
    cand = np.where(freq[y0:] >= 0.12)[0] + y0
    if cand.size == 0:
        return None
    # groupe de lignes le plus fréquent (deux lignes de sous-titre séparées de quelques pixels = un groupe)
    groups, cur = [], [cand[0]]
    for y in cand[1:]:
        if y - cur[-1] <= int(0.08 * h) + 1:
            cur.append(y)
        else:
            groups.append(cur)
            cur = [y]
    groups.append(cur)
    best = max(groups, key=lambda g_: freq[g_].sum())
    r0, r1 = best[0], best[-1] + 1
    present = rows[:, r0:r1].any(axis=1)
    if present.mean() < 0.15 or (r1 - r0) < max(4, int(0.015 * h)):
        return None
    # un sous-titre est centré et assez large ; un motif du décor (damier, objet qui bouge) ne l'est pas
    centers, widths = [], []
    for m in stack[present][:, r0:r1]:
        cols = np.where(m.sum(axis=0) > 0)[0]
        if cols.size:
            weight = m.sum(axis=0)[cols]
            centers.append(float((cols * weight).sum() / weight.sum()) / w)
            widths.append((cols[-1] - cols[0]) / w)
    if not centers or abs(float(np.median(centers)) - 0.5) > 0.12 or float(np.median(widths)) < 0.1:
        return None
    margin = 0.04
    # une seule ligne vue le plus souvent : place pour une deuxième ligne au-dessus
    extra = 0.08 if (r1 - r0) / h < 0.08 else 0.0
    top = max(0.4, r0 / h - margin - extra)
    bottom = min(1.0, r1 / h + margin)
    k = int(np.argmax(stack[:, r0:r1].sum(axis=(1, 2))))
    return ZoneInfo(round(top, 3), round(bottom, 3), round(float(present.mean()), 3), frames[k])


# ---------------------------------------------------------------------------------------
# Découpage en lignes
# ---------------------------------------------------------------------------------------
def _central_span(cols_on: np.ndarray, gap: int) -> tuple[int, int] | None:
    """Groupe de colonnes (mots séparés de moins de ``gap``) le plus proche du centre : le sous-titre, pas un
    élément du décor sur le côté."""
    cols = np.where(cols_on)[0]
    if cols.size == 0:
        return None
    groups, start = [], cols[0]
    for prev, c in zip(cols, cols[1:]):
        if c - prev > gap:
            groups.append((start, prev))
            start = c
    groups.append((start, cols[-1]))
    mid = len(cols_on) / 2
    return min(groups, key=lambda g_: 0 if g_[0] <= mid <= g_[1] else min(abs(g_[0] - mid), abs(g_[1] - mid)))


def cut_lines(g: np.ndarray, max_lines: int = 3) -> list[np.ndarray]:
    """Lignes de texte d'une bande (niveaux de gris) : bandes horizontales riches en texte, recadrées."""
    m = text_mask(g, near=3)
    rows = m.sum(axis=1)
    if rows.max(initial=0) < 4:
        return []
    on = rows > max(3, rows.max() * 0.08)
    runs, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged: list[list[int]] = []
    for a, b in runs:  # accents, jambages : quelques pixels d'écart
        if merged and a - merged[-1][1] <= 3:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    if not merged:
        return []
    tallest = max(b - a for a, b in merged)
    lines = [r for r in merged if r[1] - r[0] >= max(8, 0.45 * tallest)]
    out = []
    for a, b in lines[:max_lines]:
        hgt = b - a
        span = _central_span(m[a:b].sum(axis=0) > 0, gap=int(1.5 * hgt) + 2)
        if span is None:
            continue
        pad = max(4, int(0.25 * hgt))
        x0, x1 = max(0, span[0] - 10), min(g.shape[1], span[1] + 11)
        y0, y1 = max(0, a - pad), min(g.shape[0], b + pad)
        out.append(np.ascontiguousarray(g[y0:y1, x0:x1]))
    return out


# ---------------------------------------------------------------------------------------
# Lecture de la vidéo
# ---------------------------------------------------------------------------------------
@dataclass
class Segment:
    start: float
    end: float
    names: list[str] = field(default_factory=list)  # lignes envoyées à l'OCR


def scan(video: Path, duration: float, vw: int, vh: int, zone: tuple[float, float], fps: float, out_dir: Path,
         progress: Progress | None = None, cancel: threading.Event | None = None) -> tuple[list[Segment], list[Path]]:
    """Parcourt la vidéo une fois : sous-titres (début, fin) et lignes découpées, rangées dans des .npz."""
    y0 = min(vh - 2, max(0, int(zone[0] * vh) // 2 * 2))
    y1 = min(vh, max(y0 + 2, _even(zone[1] * vh)))
    bh = y1 - y0
    tw = _even(min(vw, MAX_WIDTH))
    th = _even(bh * tw / vw)
    cmd = [ffmpeg.ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video), "-an", "-sn",
           "-vf", f"fps={fps},crop={vw}:{bh}:0:{y0},scale={tw}:{th},format=gray", "-f", "rawvideo",
           "-pix_fmt", "gray", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **ffmpeg.popen_kwargs())
    err: list[bytes] = []
    threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True).start()
    size = tw * th
    min_px = max(20, int(0.0015 * size / 4))
    c0, c1 = int(tw / 2 * 0.2), int(tw / 2 * 0.8)
    segments: list[Segment] = []
    batch: dict[str, np.ndarray] = {}
    files: list[Path] = []

    def flush():
        if batch:
            f = Path(out_dir) / f"lignes{len(files):04d}.npz"
            np.savez(f, **batch)
            files.append(f)
            batch.clear()

    cur = None  # [début, fin, masque de référence, meilleure image, nombre de pixels]

    def close(c):
        if c is None or c[1] - c[0] < 0.2:
            return
        seg = Segment(round(c[0], 3), round(c[1], 3))
        for j, crop in enumerate(cut_lines(c[3])):
            name = f"s{len(segments)}_l{j}"
            batch[name] = crop
            seg.names.append(name)
        if seg.names:
            segments.append(seg)
        if len(batch) >= BATCH:
            flush()

    k = 0
    try:
        assert proc.stdout is not None
        while True:
            if cancel is not None and cancel.is_set():
                raise ffmpeg.Cancelled()
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            g = np.frombuffer(buf, dtype=np.uint8).reshape(th, tw)
            t = k / fps
            k += 1
            m = text_mask(g[::2, ::2])[:, c0:c1]  # partie centrale : le décor sur les côtés ne compte pas
            n = int(m.sum())
            has = n >= min_px
            if cur is not None and has and similar(m, cur[2]):
                cur[1] = t + 1.0 / fps
                if n > cur[4] * 1.05:  # texte plus net (fondu d'entrée) : nouvelle référence
                    cur[2], cur[3], cur[4] = m, g.copy(), n
            else:
                close(cur)
                cur = [t, t + 1.0 / fps, m, g.copy(), n] if has else None
            if progress and k % 25 == 0 and duration > 0:
                progress(min(0.99, t / duration), f"Lecture des sous-titres : {int(t // 60)} min {int(t % 60):02d} s")
        close(cur)
        flush()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    if k == 0:
        raise ffmpeg.FFmpegError(b"".join(err).decode("utf-8", "replace")[-800:] or "Aucune image lue.")
    return segments, files


# ---------------------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------------------
def fix_text(text: str, terms: list[str] | None = None) -> str:
    """Confusions classiques de lecture (l/I/1, 0/O), apostrophes, ponctuation, noms du glossaire."""
    t = text.replace("’", "'").replace("‘", "'").replace("`", "'").replace("“", '"').replace("”", '"')
    t = t.replace("，", ",").replace("！", "!").replace("？", "?").replace("：", ":").replace("；", ";")
    t = re.sub(r"\bl(?=('m|'ll|'ve|'d)\b)", "I", t)
    t = re.sub(r"(?<![\w'])l(?![\w'])", "I", t)  # « l » seul : « I »
    t = re.sub(r"(?<=[a-z])I(?=[a-z])", "l", t)  # « heIlo » → « hello »
    t = re.sub(r"(?<=[a-z])1(?=[a-z])", "l", t)
    t = re.sub(r"(?<=[A-Za-z])0(?=[a-z])|(?<=[a-z])0(?=[A-Za-z])", "o", t)
    t = re.sub(r"\b0(?=[a-z]{2,})", "O", t)
    t = re.sub(r"\s+([,.!?;:…])", r"\1", t)
    t = re.sub(r"([,!?;])(?=[A-Za-z])", r"\1 ", t)
    t = re.sub(r"(?<=[a-z])\.(?=[A-Z][a-z])", ". ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    for term in terms or []:  # noms propres de la série : la lecture approchée est remplacée par le bon nom
        if len(term) < 4:
            continue
        for w in set(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]+", t)):
            if w == term or abs(len(w) - len(term)) > 1:
                continue
            a, b = _confusable(w), _confusable(term)
            if a == b or difflib.SequenceMatcher(a=a, b=b).ratio() >= 0.8:
                t = re.sub(rf"\b{re.escape(w)}\b", term, t)
    return t


def _confusable(word: str) -> str:
    """Forme où les lettres que l'OCR confond sont identiques (l, I, 1, i ; 0, o ; rn, m)."""
    w = word.lower().replace("rn", "m")
    return w.translate(str.maketrans({"l": "i", "1": "i", "|": "i", "0": "o"}))


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def build_cues(segments: list[Segment], texts: dict[str, list], duration: float,
               terms: list[str] | None = None) -> tuple[list[Cue], list[dict]]:
    """Sous-titres à partir des lectures : textes quasi identiques consécutifs réunis, écarts journalisés."""
    raw: list[Cue] = []
    dropped: list[dict] = []
    for seg in segments:
        parts = [texts.get(n, ["", 0.0]) for n in seg.names]
        parts = [(str(p[0]).strip(), float(p[1])) for p in parts if str(p[0]).strip()]
        if not parts:
            continue
        rows = [fix_text(p[0], terms) for p in parts]
        # point lu en fin de ligne alors que la phrase continue en minuscule à la ligne suivante : parasite
        rows = [r[:-1] if r.endswith(".") and not r.endswith("..") and k + 1 < len(rows) and rows[k + 1][:1].islower()
                else r for k, r in enumerate(rows)]
        text = "\n".join(rows)
        conf = min(p[1] for p in parts)
        short = len(_norm(text))
        # un seul signe : un élément du décor ; « Ha ! », « No ! » sont gardés s'ils sont nets
        if short <= 1 or conf < 0.4 or (short <= 2 and conf < 0.6):
            dropped.append({"start": seg.start, "end": seg.end, "text": text[:120],
                            "reason": f"lecture illisible (confiance {conf:.0%})"})
            continue
        raw.append(Cue(seg.start, seg.end, text, conf=round(conf, 3)))
    # même sous-titre coupé par un changement du décor : réuni
    cues: list[Cue] = []
    for c in raw:
        if cues:
            p = cues[-1]
            ratio = difflib.SequenceMatcher(a=_norm(p.text), b=_norm(c.text)).ratio()
            if ratio >= 0.8 and c.start - p.end <= 0.35:
                if (c.conf, c.end - c.start) > (p.conf, p.end - p.start):
                    p.text, p.conf = c.text, c.conf
                p.end = max(p.end, c.end)
                continue
        cues.append(c)
    # texte permanent (logo, titre de chaîne) : présent plus du quart de la vidéo
    by_text: dict[str, float] = {}
    for c in cues:
        by_text[_norm(c.text)] = by_text.get(_norm(c.text), 0.0) + c.end - c.start
    permanent = {k for k, v in by_text.items() if duration > 0 and v > 0.25 * duration}
    # génériques karaoké, crédits : texte qui change plus de deux fois par seconde pendant plus de 10 s
    fast = np.zeros(len(cues), dtype=bool)
    i = 0
    while i < len(cues):
        j = i
        while j + 1 < len(cues) and cues[j + 1].start - cues[j].start < 0.5:
            j += 1
        if j > i and cues[j].end - cues[i].start > 10.0:
            fast[i:j + 1] = True
        i = j + 1
    kept = []
    for c, quick in zip(cues, fast):
        if _norm(c.text) in permanent:
            dropped.append({"start": c.start, "end": c.end, "text": c.text[:120], "reason": "texte permanent (logo)"})
        elif quick:
            c.kind, c.reason = "song", "texte qui change très vite (générique, karaoké)"
            dropped.append({"start": c.start, "end": c.end, "text": c.text[:120], "reason": c.reason})
        else:
            kept.append(c)
    return kept, dropped


def read_hardsubs(video: Path, duration: float, vw: int, vh: int, zone: tuple[float, float], tool, fps: float = 12.5,
                  terms: list[str] | None = None, progress: Progress | None = None,
                  cancel: threading.Event | None = None) -> tuple[list[Cue], list[dict]]:
    """Chaîne complète : lecture de la bande, OCR des lignes, sous-titres."""
    with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
        segs, files = scan(video, duration, vw, vh, zone, fps, Path(td),
                           (lambda v, m: progress(v * 0.6, m)) if progress else None, cancel)
        if not segs:
            return [], []
        texts = tool.ocr_lines(files, on_progress=(lambda v, m: progress(0.6 + 0.4 * v, m)) if progress else None)
    return build_cues(segs, texts, duration, terms)


def write_srt(cues: list[Cue], path: Path) -> Path:
    from .subtitles import srt_time

    rows = [f"{i + 1}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}\n" for i, c in enumerate(cues)]
    path.write_text("\n".join(rows), encoding="utf-8")
    return path
