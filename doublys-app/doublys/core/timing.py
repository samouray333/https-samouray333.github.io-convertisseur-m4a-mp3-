"""Calage des voix françaises dans le créneau de chaque réplique."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import audio
from .models import DubSettings, Line


def slot_end(lines: list[Line], index: int, settings: DubSettings, video_duration: float = 0.0) -> float:
    """Fin du créneau : début de la réplique suivante moins 0,1 s, au plus 1 s après la fin d'origine."""
    line = lines[index]
    limit = line.end + settings.overhang
    if index + 1 < len(lines):
        limit = min(limit, lines[index + 1].start - settings.gap_before_next)
    if video_duration > 0:
        limit = min(limit, video_duration)
    return max(limit, line.start + 0.3)


def slots(lines: list[Line], settings: DubSettings, video_duration: float = 0.0) -> list[float]:
    """Durée disponible pour chaque réplique (les répliques doivent être triées)."""
    return [max(0.3, slot_end(lines, i, settings, video_duration) - ln.start) for i, ln in enumerate(lines)]


def char_budget(seconds: float, cps: float = 14.5) -> int:
    return max(8, int(round(seconds * cps)))


@dataclass
class FitResult:
    data: np.ndarray
    sr: int
    rate: float  # débit demandé au moteur
    tempo: float  # accélération appliquée ensuite
    state: str  # ok | tempo | rate | long
    message: str = ""

    @property
    def duration(self) -> float:
        return len(self.data) / float(self.sr) if self.sr else 0.0


def prepare(data: np.ndarray, sr: int) -> np.ndarray:
    data = audio.trim_silence(audio.remove_dc(data), sr, -45.0, pad_ms=40)
    return audio.apply_fades(data, sr, 5, 25)


def fit(synth: Callable[[float], tuple[np.ndarray, int]], slot: float, settings: DubSettings) -> FitResult:
    """``synth(débit)`` produit la voix ; renvoie la voix calée dans ``slot`` secondes.

    Trop longue : accélération (atempo) jusqu'à ×1,12 ; au-delà, nouvelle synthèse avec un débit plus rapide
    (au plus ``max_rate``) puis atempo du reste ; si ça dépasse encore, la réplique est signalée « trop longue »."""
    data, sr = synth(1.0)
    data = prepare(data, sr)
    dur = len(data) / sr
    if dur <= slot + 0.02 or dur == 0:
        return FitResult(data, sr, 1.0, 1.0, "ok")
    ratio = dur / slot
    if ratio <= settings.max_tempo:
        return FitResult(audio.change_speed(data, sr, ratio), sr, 1.0, ratio, "tempo")
    rate = min(settings.max_rate, ratio)
    data2, sr2 = synth(rate)
    data2 = prepare(data2, sr2)
    dur2 = len(data2) / sr2
    if dur2 >= dur * 0.98:  # moteur sans réglage de débit efficace : on garde la première version
        data2, sr2, dur2, rate = data, sr, dur, 1.0
    rest = dur2 / slot
    if rest <= settings.max_tempo:
        out = audio.change_speed(data2, sr2, rest) if rest > 1.01 else data2
        return FitResult(out, sr2, rate, max(1.0, rest), "rate")
    out = audio.change_speed(data2, sr2, settings.max_tempo)
    over = len(out) / sr2 - slot
    return FitResult(out, sr2, rate, settings.max_tempo, "long",
                     f"Dépasse de {over:.1f} s : raccourcis le texte.")


def active_rms_db(data: np.ndarray, sr: int) -> float:
    """Niveau efficace de la parole (fenêtres actives seulement)."""
    if data.size == 0:
        return -120.0
    db = audio.frame_rms_db(data, sr, 50.0)
    if db.size == 0:
        return -120.0
    top = float(db.max())
    act = db[db > max(top - 25.0, -60.0)]
    if act.size == 0:
        return -120.0
    return float(10 * np.log10(np.mean(10 ** (act / 10))))


def match_level(data: np.ndarray, sr: int, target_db: float, max_gain_db: float = 18.0) -> tuple[np.ndarray, float]:
    """Aligne le niveau de la voix française sur celui de la voix d'origine (crêtes protégées)."""
    cur = active_rms_db(data, sr)
    if cur <= -100 or target_db <= -70:
        return data, 0.0
    gain = max(-max_gain_db, min(max_gain_db, target_db - cur))
    out = data * audio.db_to_lin(gain)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 0.97:
        out = out * (0.97 / peak)
        gain += audio.lin_to_db(0.97 / peak)
    return out.astype(np.float32), gain


def _envelope_db(data: np.ndarray, sr: int, frame: float = 0.05, smooth: float = 0.3) -> np.ndarray:
    win = max(1, int(sr * frame))
    n = len(data) // win
    if n == 0:
        return np.zeros(0)
    rms = np.sqrt(np.mean(data[: n * win].astype(np.float64).reshape(n, win) ** 2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    k = max(1, int(smooth / frame))
    if k > 1 and n > k:
        db = np.convolve(db, np.ones(k) / k, mode="same")
    return db


def transfer_dynamics(vf: np.ndarray, sr: int, orig: np.ndarray, orig_sr: int, amount: float = 0.5,
                      limit_db: float = 6.0) -> np.ndarray:
    """Donne à la voix française les nuances de volume de la phrase d'origine (montée, chute, mot appuyé), à
    l'échelle de la phrase (lissage de 0,3 s) et avec mesure (± 6 dB au plus)."""
    frame = 0.05
    ev, eo = _envelope_db(vf, sr, frame), _envelope_db(orig, orig_sr, frame)
    if len(ev) < 6 or len(eo) < 6:
        return vf
    active_v = ev > ev.max() - 30
    active_o = eo > eo.max() - 30
    if active_v.sum() < 3 or active_o.sum() < 3:
        return vf
    rel_v = ev - np.median(ev[active_v])
    rel_o = np.interp(np.linspace(0, 1, len(ev)), np.linspace(0, 1, len(eo)), eo - np.median(eo[active_o]))
    gain = np.clip(amount * (rel_o - rel_v), -limit_db, limit_db)
    gain[~active_v] = 0.0
    win = int(sr * frame)
    g = np.interp(np.arange(len(vf)), np.arange(len(gain)) * win + win / 2, 10 ** (gain / 20))
    out = (vf * g).astype(np.float32)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    return out * (0.97 / peak) if peak > 0.97 else out
