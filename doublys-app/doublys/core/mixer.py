"""Mixage par blocs (mémoire stable même pour un film entier) : fond + voix françaises.

Là où aucune voix française n'est posée, la voix d'origine (piste voix de Demucs) revient, avec un fondu : une
réplique manquante ou en échec ne laisse jamais un trou dans le son."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from . import audio
from .ffmpeg import Cancelled

SR = 44100
BLOCK_SECONDS = 30.0
RAMP = 0.15
FALLBACK_RAMP = 0.08  # fondu de la voix d'origine remise entre les répliques doublées
OVERLAP_DB = -6.0  # réplique chevauchée par la précédente (trop longue) : baissée pendant le chevauchement


@dataclass
class Placed:
    start: float
    path: Path


def _read_block(path: Path, a: int, b: int, channels: int) -> np.ndarray:
    data, _ = sf.read(str(path), start=a, stop=b, dtype="float32", always_2d=True)
    if data.shape[1] != channels:
        data = np.repeat(data.mean(axis=1, keepdims=True), channels, axis=1)
    if len(data) < b - a:
        data = np.pad(data, ((0, b - a - len(data)), (0, 0)))
    return data


def _soft_limit(x: np.ndarray, ceiling: float = 0.98) -> np.ndarray:
    """Écrête en douceur ce qui dépasse (rare : voix forte sur musique forte)."""
    over = np.abs(x) > 0.9
    if not over.any():
        return x
    y = x.copy()
    s = np.sign(y[over])
    m = np.abs(y[over])
    y[over] = s * (0.9 + (ceiling - 0.9) * np.tanh((m - 0.9) / (ceiling - 0.9)))
    return y


def duck_envelope(n: int, a: int, regions: list[tuple[float, float]], level_db: float, sr: int = SR,
                  ramp: float = RAMP) -> np.ndarray:
    """Gain (n échantillons à partir de ``a``) : ``level_db`` pendant les régions, 0 dB ailleurs, avec des rampes."""
    t = (a + np.arange(n, dtype=np.float64)) / sr
    depth = np.zeros(n, dtype=np.float64)
    t0, t1 = t[0] if n else 0.0, t[-1] if n else 0.0
    for start, end in regions:
        if end + ramp < t0 or start - ramp > t1:
            continue
        d = np.minimum((t - (start - ramp)) / ramp, ((end + ramp) - t) / ramp)
        depth = np.maximum(depth, np.clip(d, 0.0, 1.0))
    low = audio.db_to_lin(level_db)
    return (1.0 - depth * (1.0 - low)).astype(np.float32)


class Compressor:
    """Compresseur léger de la piste VF (2:1 au-dessus de -18 dBFS, attaque 10 ms, relâche 150 ms), par trames de
    5 ms ; l'état est gardé d'un bloc à l'autre."""

    def __init__(self, sr: int = SR, threshold_db: float = -18.0, ratio: float = 2.0, attack: float = 0.01,
                 release: float = 0.15, frame: float = 0.005):
        self.sr, self.th, self.ratio = sr, threshold_db, ratio
        self.win = max(1, int(sr * frame))
        self.att = float(np.exp(-frame / attack))
        self.rel = float(np.exp(-frame / release))
        self.env = -120.0

    def __call__(self, x: np.ndarray) -> np.ndarray:
        n = len(x) // self.win
        if n == 0:
            return x
        rms = np.sqrt(np.mean(x[:n * self.win].astype(np.float64).reshape(n, self.win) ** 2, axis=1))
        level = 20 * np.log10(np.maximum(rms, 1e-6))
        gains = np.empty(n)
        env = self.env
        for i, v in enumerate(level):
            coef = self.att if v > env else self.rel
            env = coef * env + (1 - coef) * v
            over = env - self.th
            gains[i] = -over * (1 - 1 / self.ratio) if over > 0 else 0.0
        self.env = env
        g = 10 ** (np.repeat(gains, self.win) / 20)
        g = np.concatenate([g, np.full(len(x) - len(g), g[-1])])
        return (x * g).astype(np.float32)


def mix(out: Path, duration: float, placed: list[Placed], background: Path | None = None,
        original_voice: Path | None = None, original_voice_db: float = -20.0,
        fallback_voice: Path | None = None, fallback_under_db: float = -60.0,
        duck_original: Path | None = None, duck_db: float = -18.0, voice_only: Path | None = None,
        compress: bool = True, progress: Callable[[float], None] | None = None,
        cancel: threading.Event | None = None) -> Path:
    """Écrit le mélange stéreo 44,1 kHz.

    ``background`` : fond séparé (musique, bruits) ; ``original_voice`` : voix d'origine laissée faible partout ;
    ``fallback_voice`` : voix d'origine à plein niveau là où il n'y a pas de VF, ``fallback_under_db`` sous la VF ;
    ``duck_original`` : sans séparation, le son d'origine baissé de ``duck_db`` pendant les répliques françaises."""
    total = int(round(duration * SR))
    block = int(BLOCK_SECONDS * SR)
    items = sorted(placed, key=lambda p: p.start)
    cache: dict[Path, np.ndarray] = {}
    regions = []
    for p in items:
        d = audio.duration_of(p.path)
        regions.append((p.start, p.start + d))
    # réplique qui commence pendant la précédente (trop longue) : baissée de 6 dB pendant le chevauchement
    overlaps = [max(0.0, (regions[k - 1][1] if k else 0.0)) for k in range(len(items))]
    comp = Compressor() if compress else None
    out.parent.mkdir(parents=True, exist_ok=True)
    vo = sf.SoundFile(str(voice_only), "w", SR, 1, "PCM_16") if voice_only else None
    try:
        with sf.SoundFile(str(out), "w", SR, 2, "PCM_16") as fh:
            pos = 0
            while pos < total:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                n = min(block, total - pos)
                acc = np.zeros((n, 2), dtype=np.float32)
                if background is not None:
                    acc += _read_block(background, pos, pos + n, 2)
                if duck_original is not None:
                    env = duck_envelope(n, pos, regions, duck_db)
                    acc += _read_block(duck_original, pos, pos + n, 2) * env[:, None]
                if original_voice is not None:
                    acc += _read_block(original_voice, pos, pos + n, 2) * audio.db_to_lin(original_voice_db)
                if fallback_voice is not None:
                    env = duck_envelope(n, pos, regions, fallback_under_db, ramp=FALLBACK_RAMP)
                    acc += _read_block(fallback_voice, pos, pos + n, 2) * env[:, None]
                voice = np.zeros(n, dtype=np.float32)
                for k, (p, (r0, r1)) in enumerate(zip(items, regions)):
                    s = int(round(r0 * SR))
                    e = int(round(r1 * SR))
                    if e <= pos or s >= pos + n:
                        continue
                    data = cache.get(p.path)
                    if data is None:
                        data, sr = audio.read_audio(p.path)
                        if sr != SR:
                            data = audio.resample(data, sr, SR)
                        cache[p.path] = data
                    a = max(pos, s)
                    b = min(pos + n, s + len(data))
                    if b > a:
                        piece = data[a - s:b - s]
                        prev_end = int(round(overlaps[k] * SR))
                        if prev_end > a:  # chevauchement avec la réplique précédente
                            cut = min(b, prev_end) - a
                            piece = piece.copy()
                            piece[:cut] *= audio.db_to_lin(OVERLAP_DB)
                        voice[a - pos:b - pos] += piece
                # on libère les voix déjà passées
                for p, (r0, r1) in zip(items, regions):
                    if r1 * SR < pos and p.path in cache:
                        del cache[p.path]
                if comp is not None:
                    voice = comp(voice)
                acc += voice[:, None]
                fh.write(_soft_limit(acc))
                if vo is not None:
                    vo.write(np.clip(voice, -1, 1))
                pos += n
                if progress:
                    progress(pos / max(1, total))
    finally:
        if vo is not None:
            vo.close()
    return out
