"""Bibliothèque de sons : effets intégrés (générés par l'application, donc libres de droits) et sons personnels.

Dans le script : « [son: applaudissements] », « [virgule] » (petit jingle entre deux rubriques), « [son: mon_fichier] »
pour un son ajouté dans le dossier « Mes sons » ou dans le dossier « sons » du projet.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import unicodedata
from pathlib import Path

import numpy as np

from .. import paths
from . import audio

SR = 44100
LIBRARY_VERSION = 1
AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus", ".aac")

BUILTIN_LABELS = {
    "virgule": "Virgule (jingle de transition)",
    "applaudissements": "Applaudissements",
    "transition": "Transition (souffle)",
    "ding": "Ding",
    "cloche": "Cloche",
    "roulement": "Roulement de tambour",
    "suspense": "Suspense",
    "notification": "Notification",
    "generique": "Mini générique",
}
ALIASES = {"jingle": "virgule", "applause": "applaudissements", "bravo": "applaudissements", "whoosh": "transition",
           "souffle": "transition", "tambour": "roulement", "bell": "cloche", "générique": "generique"}


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def builtin_dir() -> Path:
    d = paths.shared_data_dir() / "sons" / f"integres-v{LIBRARY_VERSION}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_dir() -> Path:
    """« Mes sons » : commun aux applications, l'utilisateur y dépose ses propres effets."""
    d = paths.shared_data_dir() / "sons" / "mes-sons"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------------------
# Synthèse des sons intégrés
# ---------------------------------------------------------------------------------------
def _t(seconds: float) -> np.ndarray:
    return np.arange(int(SR * seconds)) / SR


def _env(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a, r = int(SR * attack), int(SR * release)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.exp(-np.linspace(0, 6, r))
    return e


def _tone(freq: float, seconds: float, harmonics=(1.0, 0.4, 0.2), decay: float = 3.0) -> np.ndarray:
    t = _t(seconds)
    sig = sum(a * np.sin(2 * np.pi * freq * (k + 1) * t) for k, a in enumerate(harmonics))
    return sig * np.exp(-decay * t)


def _place(out: np.ndarray, sig: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * SR)
    j = min(len(out), i + len(sig))
    out[i:j] += sig[: j - i] * gain


def _lowpass(x: np.ndarray, alpha: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # filtre du premier ordre (sons courts : assez rapide)
        acc += alpha * (v - acc)
        y[i] = acc
    return y


def _virgule(rng) -> np.ndarray:
    out = np.zeros(int(SR * 1.6))
    for i, f in enumerate((523.25, 659.25, 783.99, 1046.5)):  # do mi sol do
        _place(out, _tone(f, 1.2, (1, 0.5, 0.25, 0.1), 4.0), i * 0.11, 0.5)
    return out


def _generique(rng) -> np.ndarray:
    out = np.zeros(int(SR * 3.2))
    notes = [(392.0, 0), (523.25, 0.25), (659.25, 0.5), (587.33, 0.85), (659.25, 1.1), (783.99, 1.35)]
    for f, at in notes:
        _place(out, _tone(f, 1.0, (1, 0.45, 0.2), 3.0), at, 0.45)
    for f in (261.63, 329.63, 392.0):  # accord final
        _place(out, _tone(f, 1.6, (1, 0.3), 1.8), 1.6, 0.3)
    return out


def _applause(rng) -> np.ndarray:
    n = int(SR * 3.5)
    out = np.zeros(n)
    claps = int(260 * 3.5)
    for _ in range(claps):
        at = rng.uniform(0, 3.3)
        length = int(SR * rng.uniform(0.008, 0.02))
        burst = rng.standard_normal(length) * np.exp(-np.linspace(0, 8, length))
        _place(out, burst, at, rng.uniform(0.15, 0.5))
    out = out - _lowpass(out, 0.05)  # retire les graves : son plus « mains »
    return out * _env(n, 0.4, 1.2)


def _transition(rng) -> np.ndarray:
    n = int(SR * 1.2)
    noise = rng.standard_normal(n)
    sweep = np.linspace(0.02, 0.35, n) ** 1.5
    y = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc += sweep[i] * (noise[i] - acc)
        y[i] = acc
    return y * np.sin(np.linspace(0, np.pi, n)) ** 2 * 1.4


def _ding(rng) -> np.ndarray:
    return _tone(1318.5, 1.4, (1, 0.25, 0.1), 3.5) * 0.7


def _cloche(rng) -> np.ndarray:
    t = _t(3.0)
    partials = [(1.0, 1.0), (2.0, 0.6), (2.76, 0.4), (5.4, 0.25), (8.9, 0.12)]
    sig = sum(a * np.sin(2 * np.pi * 440 * r * t) * np.exp(-t * (1.2 + r * 0.5)) for r, a in partials)
    return sig * 0.5


def _roulement(rng) -> np.ndarray:
    n = int(SR * 2.4)
    out = np.zeros(n)
    t = 0.0
    while t < 2.0:
        hit = rng.standard_normal(int(SR * 0.05)) * np.exp(-np.linspace(0, 10, int(SR * 0.05)))
        _place(out, hit, t, 0.25 + 0.45 * t / 2.0)
        t += 0.045 + rng.uniform(-0.006, 0.006)
    boom = _tone(70, 0.6, (1, 0.5), 6.0) + rng.standard_normal(int(SR * 0.6)) * np.exp(-_t(0.6) * 12) * 0.6
    _place(out, boom, 2.0, 0.9)
    return out - _lowpass(out, 0.01)


def _suspense(rng) -> np.ndarray:
    t = _t(4.0)
    sig = (np.sin(2 * np.pi * 55 * t) + 0.6 * np.sin(2 * np.pi * 58.3 * t) + 0.3 * np.sin(2 * np.pi * 110.4 * t))
    swell = np.minimum(1.0, t / 3.0) ** 2 * np.exp(-np.maximum(0, t - 3.4) * 8)
    return sig * swell * 0.6


def _notification(rng) -> np.ndarray:
    out = np.zeros(int(SR * 0.9))
    _place(out, _tone(880, 0.5, (1, 0.3), 6.0), 0, 0.6)
    _place(out, _tone(1318.5, 0.6, (1, 0.3), 5.0), 0.14, 0.6)
    return out


_GENERATORS = {"virgule": _virgule, "applaudissements": _applause, "transition": _transition, "ding": _ding,
               "cloche": _cloche, "roulement": _roulement, "suspense": _suspense, "notification": _notification,
               "generique": _generique}


_LOCK = threading.Lock()


def ensure_builtin(name: str) -> Path:
    target = builtin_dir() / f"{name}.wav"
    if target.exists():
        return target
    with _LOCK:  # plusieurs pages peuvent demander le même son en même temps
        if not target.exists():
            rng = np.random.default_rng(sum(map(ord, name)))
            sig = _GENERATORS[name](rng).astype(np.float64)
            peak = float(np.max(np.abs(sig))) or 1.0
            sig = sig / peak * audio.db_to_lin(-3.0)
            sig = audio.apply_fades(sig.astype(np.float32), SR, 3, 30)
            fd, tmp = tempfile.mkstemp(suffix=".wav", prefix=f".{name}-", dir=str(target.parent))
            os.close(fd)
            audio.write_audio(tmp, sig, SR, subtype="PCM_16")
            os.replace(tmp, target)
    return target


# ---------------------------------------------------------------------------------------
# Recherche d'un son par son nom
# ---------------------------------------------------------------------------------------
def user_sounds(project_dir: Path | None = None) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for d in [user_dir()] + ([project_dir / "sons"] if project_dir else []):
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in AUDIO_EXT:
                    found[slug(f.stem)] = f
    return found


def available(project_dir: Path | None = None) -> list[tuple[str, str]]:
    """[(nom à écrire dans la balise, libellé)] : sons intégrés puis sons personnels."""
    out = [(k, v) for k, v in BUILTIN_LABELS.items()]
    out += [(f.stem, f"{f.stem} (mes sons)") for f in user_sounds(project_dir).values()]
    return out


def resolve(name: str, project_dir: Path | None = None) -> Path | None:
    key = slug(name)
    key = ALIASES.get(key, key)
    mine = user_sounds(project_dir)
    if key in mine:  # un son personnel du même nom remplace le son intégré
        return mine[key]
    if key in _GENERATORS:
        return ensure_builtin(key)
    p = Path(name.strip())
    if p.is_absolute() and p.is_file():
        return p
    return None
