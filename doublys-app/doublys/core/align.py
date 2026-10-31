"""Recalage des sous-titres sur la parole réelle : décalage global, début et fin resserrés, jamais coupés."""

from __future__ import annotations

import numpy as np

from .models import Line

RATE = 50  # échantillons par seconde des indicatrices (20 ms)


def _indicator(intervals, n: int) -> np.ndarray:
    x = np.zeros(n, dtype=np.float32)
    for a, b in intervals:
        i, j = max(0, int(a * RATE)), min(n, int(b * RATE))
        if j > i:
            x[i:j] = 1.0
    return x


def global_offset(cues: list[tuple[float, float]], speech: list[list[float]], max_shift: float = 10.0,
                  min_gain: float = 0.10) -> tuple[float, float]:
    """Décalage (s) à ajouter aux sous-titres pour qu'ils recouvrent au mieux la parole, et le gain obtenu
    (part de recouvrement en plus) ; (0, 0) si le décalage n'améliore pas nettement les choses."""
    if not cues or not speech:
        return 0.0, 0.0
    end = max(max(b for _a, b in cues), max(b for _a, b in speech)) + max_shift + 1
    n = int(end * RATE)
    sub = _indicator(cues, n)
    sp = _indicator(speech, n)
    size = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(sp, size) * np.conj(np.fft.rfft(sub, size)), size)
    k = int(max_shift * RATE)
    lags = np.concatenate([np.arange(0, k + 1), np.arange(-k, 0)])
    vals = np.concatenate([corr[:k + 1], corr[size - k:]])
    best = int(np.argmax(vals))
    base = float(corr[0])
    gain = (float(vals[best]) - base) / max(1.0, float(sub.sum()))
    if gain < min_gain:
        return 0.0, 0.0
    return round(lags[best] / RATE, 2), round(gain, 3)


def refine(lines: list[Line], speech: list[list[float]], margin: float = 0.6) -> int:
    """Début et fin de chaque réplique resserrés sur la parole qu'elle recouvre (± ``margin``), ou élargis si la
    parole déborde ; une réplique n'est jamais raccourcie au point de perdre de la parole, ni étendue sur la
    suivante. Renvoie le nombre de répliques modifiées."""
    if not speech:
        return 0
    lines.sort(key=lambda x: x.start)
    changed = 0
    for i, ln in enumerate(lines):
        lo = lines[i - 1].end + 0.02 if i > 0 else 0.0
        hi = lines[i + 1].start - 0.02 if i + 1 < len(lines) else 1e9
        near = [r for r in speech if r[1] > ln.start - margin and r[0] < ln.end + margin]
        if not near:
            continue
        start = max(lo, min(near[0][0], ln.end - 0.2) if near[0][0] > ln.start - margin else ln.start)
        end = min(hi, max(near[-1][1], start + 0.2))
        if near[-1][1] > ln.end + margin:  # la parole continue au-delà : la réplique est élargie jusque-là
            end = min(hi, near[-1][1])
        if end - start < 0.2:
            continue
        if abs(start - ln.start) > 0.01 or abs(end - ln.end) > 0.01:
            ln.start, ln.end = round(start, 3), round(end, 3)
            changed += 1
    return changed
