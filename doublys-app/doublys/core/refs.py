"""Extrait de référence de chaque personne (12 à 25 s de sa voix isolée) et estimation du genre."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from . import audio
from .models import Line

MIN_REF = 12.0
MAX_REF = 25.0
GAP = 0.15


def read_span(path: Path, start: float, end: float) -> tuple[np.ndarray, int]:
    """Lit [start, end] d'un WAV en mono sans charger tout le fichier."""
    info = sf.info(str(path))
    sr = int(info.samplerate)
    a = max(0, int(start * sr))
    b = min(int(info.frames), int(end * sr))
    if b <= a:
        return np.zeros(0, dtype=np.float32), sr
    data, _ = sf.read(str(path), start=a, stop=b, dtype="float32", always_2d=True)
    return data.mean(axis=1).astype(np.float32), sr


def pick_lines(lines: list[Line], offset: int = 0) -> list[Line]:
    """Répliques choisies pour l'extrait : les plus longues d'abord ; ``offset`` donne un autre choix."""
    cands = sorted([ln for ln in lines if ln.length >= 1.0], key=lambda x: -x.length)
    if not cands:
        cands = sorted(lines, key=lambda x: -x.length)
    if not cands:
        return []
    k = offset % len(cands)
    cands = cands[k:] + cands[:k]
    picked, total = [], 0.0
    for ln in cands:
        if total >= MIN_REF:
            break
        picked.append(ln)
        total += min(ln.length, MAX_REF - total)
        if total >= MAX_REF:
            break
    return sorted(picked, key=lambda x: x.start)


def build_reference(voice_wav: Path, lines: list[Line], out: Path, offset: int = 0) -> tuple[Path, float]:
    """Assemble l'extrait de référence (24 kHz mono, filtré et normalisé). Renvoie (chemin, durée)."""
    parts: list[np.ndarray] = []
    sr = 24000
    total = 0.0
    for ln in pick_lines(lines, offset):
        data, file_sr = read_span(voice_wav, ln.start - 0.05, ln.end + 0.1)
        data = audio.resample(data, file_sr, sr)
        data = audio.trim_silence(data, sr, -45.0, pad_ms=60)
        if data.size == 0:
            continue
        room = MAX_REF - total
        if room <= 0.5:
            break
        data = audio.apply_fades(data[: int(room * sr)], sr, 8, 20)
        parts += [data, audio.silence(GAP * 1000, sr)]
        total += len(data) / sr + GAP
    if not parts:
        raise ValueError("Aucune parole exploitable pour cette personne.")
    mix = np.concatenate(parts)
    tmp = out.with_name(out.stem + "-brut.wav")
    audio.write_audio(tmp, mix, sr, subtype="PCM_16")
    try:
        audio.prepare_reference(tmp, out, target_sr=sr)
    finally:
        tmp.unlink(missing_ok=True)
    return out, audio.duration_of(out)


def estimate_pitch(data: np.ndarray, sr: int) -> float:
    """Hauteur médiane (Hz) des passages voisés, par autocorrélation (50 à 400 Hz)."""
    if data.size < sr // 4:
        return 0.0
    if sr != 16000:
        data = audio.resample(data, sr, 16000)
        sr = 16000
    win, hop = int(0.04 * sr), int(0.02 * sr)
    lo, hi = int(sr / 400), int(sr / 60)
    db = audio.frame_rms_db(data, sr, 20.0)
    loud = float(db.max()) if db.size else -120
    f0s = []
    for start in range(0, len(data) - win, hop):
        frame = data[start:start + win].astype(np.float64)
        rms = np.sqrt(np.mean(frame ** 2))
        if 20 * np.log10(max(rms, 1e-9)) < loud - 22:
            continue
        frame = frame - frame.mean()
        ac = np.correlate(frame, frame, mode="full")[win - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        seg = ac[lo:hi]
        if seg.size == 0:
            continue
        k = int(np.argmax(seg))
        if seg[k] > 0.45:
            f0s.append(sr / (lo + k))
    if len(f0s) < 5:
        return 0.0
    return float(np.median(f0s))


# Zone où voix d'homme aiguës, voix de femme graves, ados et enfants se recouvrent : l'estimation est fragile.
UNCERTAIN_PITCH = (150.0, 185.0)


def gender_from_pitch(f0: float) -> str:
    """Meilleure estimation (M/F) ; voir ``gender_is_uncertain`` pour savoir s'il faut la faire vérifier."""
    if f0 <= 0:
        return ""
    return "M" if f0 < 165.0 else "F"


def gender_is_uncertain(f0: float) -> bool:
    return f0 > 0 and UNCERTAIN_PITCH[0] <= f0 <= UNCERTAIN_PITCH[1]
