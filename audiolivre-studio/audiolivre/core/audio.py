"""Outils audio : lecture/écriture, rééchantillonnage, silences, analyse (normes ACX)."""

from __future__ import annotations

import logging
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)

DEFAULT_SR = 44100
BLOCK = 65536


def db_to_lin(db: float) -> float:
    return float(10 ** (db / 20.0))


def lin_to_db(x: float) -> float:
    return 20.0 * math.log10(max(float(x), 1e-12))


# ---------------------------------------------------------------------------------------
# Lecture / écriture
# ---------------------------------------------------------------------------------------
def read_audio(path: str | Path, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    """Lit un fichier audio en mono float32 (via FFmpeg si libsndfile ne sait pas le lire)."""
    p = Path(path)
    try:
        data, sr = sf.read(str(p), dtype="float32", always_2d=True)
    except Exception:
        from . import ffmpeg

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "decoded.wav"
            ffmpeg.decode_to_wav(p, tmp, sample_rate=target_sr)
            data, sr = sf.read(str(tmp), dtype="float32", always_2d=True)
    mono = data.mean(axis=1).astype(np.float32) if data.shape[1] > 1 else data[:, 0].astype(np.float32)
    if target_sr and sr != target_sr:
        mono = resample(mono, sr, target_sr)
        sr = target_sr
    return mono, sr


def write_audio(path: str | Path, data: np.ndarray, sr: int, subtype: str | None = None) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fmt = p.suffix.lower().lstrip(".")
    if subtype is None:
        subtype = "PCM_24" if fmt in ("wav", "flac") else None
    sf.write(str(p), np.clip(data, -1.0, 1.0), sr, subtype=subtype)
    return p


def resample(data: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to or data.size == 0:
        return data.astype(np.float32)
    try:
        import soxr

        return soxr.resample(data, sr_from, sr_to, quality="HQ").astype(np.float32)
    except ImportError:  # repli : interpolation linéaire
        n = int(round(len(data) * sr_to / sr_from))
        x_old = np.linspace(0, 1, len(data), endpoint=False)
        x_new = np.linspace(0, 1, n, endpoint=False)
        return np.interp(x_new, x_old, data).astype(np.float32)


def duration_of(path: str | Path) -> float:
    try:
        info = sf.info(str(path))
        return info.frames / float(info.samplerate)
    except Exception:
        from . import ffmpeg

        return ffmpeg.probe_duration(path)


# ---------------------------------------------------------------------------------------
# Traitements simples
# ---------------------------------------------------------------------------------------
def frame_rms_db(data: np.ndarray, sr: int, win_ms: float = 20.0) -> np.ndarray:
    win = max(1, int(sr * win_ms / 1000))
    n = len(data) // win
    if n == 0:
        return np.array([lin_to_db(np.sqrt(np.mean(data ** 2)) if data.size else 0)])
    frames = data[: n * win].reshape(n, win)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-9))


def trim_silence(data: np.ndarray, sr: int, threshold_db: float = -45.0, pad_ms: float = 60.0,
                 relative: bool = True) -> np.ndarray:
    """Supprime les silences en début et fin (seuil relatif au pic du signal)."""
    if data.size == 0:
        return data
    win_ms = 10.0
    db = frame_rms_db(data, sr, win_ms)
    thr = threshold_db
    if relative:
        thr = max(threshold_db, float(db.max()) - 40.0) if db.size else threshold_db
    idx = np.where(db > thr)[0]
    if idx.size == 0:
        return data[:0]
    win = int(sr * win_ms / 1000)
    pad = int(sr * pad_ms / 1000)
    start = max(0, idx[0] * win - pad)
    end = min(len(data), (idx[-1] + 1) * win + pad)
    return data[start:end]


def apply_fades(data: np.ndarray, sr: int, fade_in_ms: float = 8.0, fade_out_ms: float = 15.0) -> np.ndarray:
    out = data.astype(np.float32, copy=True)
    fi = min(len(out), int(sr * fade_in_ms / 1000))
    fo = min(len(out), int(sr * fade_out_ms / 1000))
    if fi > 0:
        out[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    if fo > 0:
        out[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    return out


def remove_dc(data: np.ndarray) -> np.ndarray:
    if data.size == 0:
        return data
    return (data - np.mean(data)).astype(np.float32)


def peak_normalize(data: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak < 1e-6:
        return data
    return (data * (db_to_lin(peak_db) / peak)).astype(np.float32)


def silence(ms: float, sr: int) -> np.ndarray:
    return np.zeros(max(0, int(sr * ms / 1000)), dtype=np.float32)


def room_tone(n: int, level_db: float, rng: np.random.Generator | None = None) -> np.ndarray:
    """Bruit de fond « rose » très faible, plus naturel qu'un silence numérique absolu."""
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    rng = rng or np.random.default_rng(1234)
    white = rng.standard_normal(n).astype(np.float32)
    # Filtre rose approximatif (Paul Kellet, version économique)
    b = np.zeros(3, dtype=np.float64)
    out = np.empty(n, dtype=np.float32)
    for i in range(0, n, 4096):
        chunk = white[i:i + 4096]
        res = np.empty_like(chunk)
        for j, w in enumerate(chunk):
            b[0] = 0.99765 * b[0] + w * 0.0990460
            b[1] = 0.96300 * b[1] + w * 0.2965164
            b[2] = 0.57000 * b[2] + w * 1.0526913
            res[j] = b[0] + b[1] + b[2] + w * 0.1848
        out[i:i + 4096] = res
    rms = float(np.sqrt(np.mean(out.astype(np.float64) ** 2))) or 1.0
    return (out * (db_to_lin(level_db) / rms)).astype(np.float32)


_ROOM_TONE_CACHE: dict[tuple[int, float], np.ndarray] = {}


def room_tone_loop(n: int, level_db: float, sr: int = DEFAULT_SR) -> np.ndarray:
    """Bruit de fond calculé une fois puis répété (rapide pour de longs fichiers)."""
    key = (sr, round(level_db, 1))
    base = _ROOM_TONE_CACHE.get(key)
    if base is None:
        base = room_tone(sr * 4, level_db)
        _ROOM_TONE_CACHE[key] = base
    if n <= len(base):
        return base[:n]
    reps = int(math.ceil(n / len(base)))
    return np.tile(base, reps)[:n]


def change_speed(data: np.ndarray, sr: int, factor: float) -> np.ndarray:
    """Change le débit sans changer la hauteur (via FFmpeg atempo)."""
    if abs(factor - 1.0) < 0.01 or data.size == 0:
        return data
    from . import ffmpeg

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.wav"
        dst = Path(td) / "out.wav"
        sf.write(str(src), data, sr, subtype="FLOAT")
        f = max(0.5, min(2.0, factor))
        ffmpeg.run_ffmpeg(["-i", str(src), "-af", f"atempo={f:.3f}", "-c:a", "pcm_f32le", str(dst)])
        out, _ = sf.read(str(dst), dtype="float32")
    return out.astype(np.float32)


# ---------------------------------------------------------------------------------------
# Analyse (critères ACX)
# ---------------------------------------------------------------------------------------
@dataclass
class AudioStats:
    duration: float
    peak_db: float
    rms_db: float
    noise_floor_db: float
    sample_rate: int

    def acx_checks(self) -> dict[str, tuple[bool, str]]:
        return {
            "rms": (-23.0 <= self.rms_db <= -18.0, f"RMS {self.rms_db:.1f} dB (attendu : -23 à -18 dB)"),
            "peak": (self.peak_db <= -3.0, f"Crête {self.peak_db:.1f} dB (maximum : -3 dB)"),
            "noise": (self.noise_floor_db <= -60.0, f"Bruit de fond {self.noise_floor_db:.1f} dB (maximum : -60 dB)"),
            "length": (self.duration <= 120 * 60, f"Durée {self.duration / 60:.1f} min (maximum : 120 min)"),
        }

    @property
    def acx_ok(self) -> bool:
        return all(ok for ok, _ in self.acx_checks().values())


def analyze_array(data: np.ndarray, sr: int) -> AudioStats:
    if data.size == 0:
        return AudioStats(0.0, -120.0, -120.0, -120.0, sr)
    d = data.astype(np.float64)
    peak = lin_to_db(np.max(np.abs(d)))
    rms = lin_to_db(np.sqrt(np.mean(d ** 2)))
    win = int(sr * 0.5)
    if len(d) >= win:
        n = len(d) // win
        frames = d[: n * win].reshape(n, win)
        floor = lin_to_db(np.min(np.sqrt(np.mean(frames ** 2, axis=1))))
    else:
        floor = rms
    return AudioStats(len(d) / sr, peak, rms, floor, sr)


def analyze_file(path: str | Path) -> AudioStats:
    """Analyse en flux (sans charger tout le fichier en mémoire)."""
    p = Path(path)
    try:
        info = sf.info(str(p))
    except Exception:
        data, sr = read_audio(p)
        return analyze_array(data, sr)
    sr = info.samplerate
    win = int(sr * 0.5)
    total = 0
    sumsq = 0.0
    peak = 0.0
    min_win = float("inf")
    carry = np.zeros(0, dtype=np.float64)
    for block in sf.blocks(str(p), blocksize=win * 32, dtype="float64", always_2d=True):
        mono = block.mean(axis=1)
        total += len(mono)
        sumsq += float(np.sum(mono ** 2))
        if mono.size:
            peak = max(peak, float(np.max(np.abs(mono))))
        buf = np.concatenate([carry, mono])
        n = len(buf) // win
        if n:
            frames = buf[: n * win].reshape(n, win)
            min_win = min(min_win, float(np.min(np.sqrt(np.mean(frames ** 2, axis=1)))))
        carry = buf[n * win:]
    if total == 0:
        return AudioStats(0.0, -120.0, -120.0, -120.0, sr)
    rms = math.sqrt(sumsq / total)
    floor = min_win if min_win != float("inf") else rms
    return AudioStats(total / sr, lin_to_db(peak), lin_to_db(rms), lin_to_db(floor), sr)


def waveform_peaks(data: np.ndarray, bins: int = 1200) -> np.ndarray:
    """Enveloppe (min/max) pour l'affichage d'une forme d'onde."""
    if data.size == 0:
        return np.zeros((bins, 2), dtype=np.float32)
    bins = max(1, min(bins, len(data)))
    edges = np.linspace(0, len(data), bins + 1, dtype=np.int64)
    out = np.zeros((bins, 2), dtype=np.float32)
    for i in range(bins):
        seg = data[edges[i]:edges[i + 1]]
        if seg.size:
            out[i, 0] = seg.min()
            out[i, 1] = seg.max()
    return out


def best_speech_window(data: np.ndarray, sr: int, seconds: float = 15.0) -> tuple[int, int]:
    """Choisit la portion la plus « parlée » (énergie stable, peu de silences) pour le clonage."""
    win = int(seconds * sr)
    if len(data) <= win:
        return 0, len(data)
    db = frame_rms_db(data, sr, 50.0)
    voiced = (db > (db.max() - 30)).astype(np.float64)
    frames_per_win = max(1, int(seconds * 1000 / 50))
    if len(voiced) <= frames_per_win:
        return 0, len(data)
    csum = np.concatenate([[0], np.cumsum(voiced)])
    scores = csum[frames_per_win:] - csum[:-frames_per_win]
    best = int(np.argmax(scores))
    start = best * int(sr * 0.05)
    return start, min(len(data), start + win)


def prepare_reference(src: str | Path, dst: str | Path, start_s: float | None = None, end_s: float | None = None,
                      denoise: bool = False, target_sr: int = 24000) -> Path:
    """Prépare un enregistrement de référence pour le clonage : mono, filtré, normalisé."""
    from . import ffmpeg

    filters = ["highpass=f=70", "lowpass=f=12000"]
    if denoise:
        filters.append("afftdn=nf=-25")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "ref.wav"
        args = []
        if start_s is not None:
            args += ["-ss", f"{max(0.0, start_s):.3f}"]
        if end_s is not None and start_s is not None:
            args += ["-t", f"{max(0.1, end_s - start_s):.3f}"]
        elif end_s is not None:
            args += ["-t", f"{end_s:.3f}"]
        args += ["-i", str(src), "-vn", "-ac", "1", "-ar", str(target_sr), "-af", ",".join(filters),
                 "-c:a", "pcm_f32le", str(tmp)]
        ffmpeg.run_ffmpeg(args)
        data, sr = sf.read(str(tmp), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = trim_silence(data, sr, -45.0, pad_ms=120)
    data = remove_dc(data)
    data = peak_normalize(data, -1.5)
    data = apply_fades(data, sr, 10, 30)
    return write_audio(dst, data, sr, subtype="PCM_16")
