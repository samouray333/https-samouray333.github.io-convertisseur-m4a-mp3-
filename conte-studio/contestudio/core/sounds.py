"""Bibliothèque de sons : bruitages et fonds d'ambiance intégrés (générés par l'application, donc libres de droits),
berceuse et sons personnels.

Dans le texte d'une histoire : « [son: porte] » (bruitage ponctuel), « [ambiance: pluie] » … « [ambiance: fin] »
(fond continu sous une scène), « [son: mon_fichier] » pour un son ajouté dans « Mes sons » ou dans le dossier
« sons » de la collection.
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
LIBRARY_VERSION = 2
AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus", ".aac")

BUILTIN_LABELS = {
    # bruitages ponctuels
    "porte": "Porte qui grince",
    "pas": "Bruits de pas",
    "cloche_magique": "Cloche magique",
    "magie": "Formule magique (scintillement)",
    "rire": "Rire",
    "tonnerre": "Coup de tonnerre",
    "toc_toc": "On frappe à la porte",
    "chat": "Chat (miaou)",
    "chien": "Chien (ouaf)",
    "vache": "Vache (meuh)",
    "mouton": "Mouton (bêê)",
    "canard": "Canard (coin-coin)",
    "hibou": "Hibou (hou-hou)",
    "oiseau": "Petit oiseau",
    "grenouille": "Grenouille (croâ)",
    "loup": "Loup qui hurle (de loin)",
    "cheval": "Cheval au galop",
    "ronflement": "Ronflement",
    "cloche": "Cloche",
    "ding": "Ding",
    "applaudissements": "Applaudissements",
    "transition": "Transition (souffle)",
    "virgule": "Petite musique de transition",
    "generique": "Petit générique",
    "suspense": "Suspense (doux)",
}
# Fonds d'ambiance : répétés sans coupure sous une scène (« [ambiance: foret] »)
AMBIENCE_LABELS = {
    "foret": "Forêt (oiseaux, brise)",
    "pluie": "Pluie",
    "orage": "Orage",
    "mer": "Mer (vagues)",
    "vent": "Vent",
    "feu": "Feu de cheminée",
    "nuit": "Nuit d'été (grillons)",
    "riviere": "Rivière",
    "bruit_blanc": "Bruit blanc",
    "bruit_rose": "Bruit rose (doux)",
}
ALIASES = {"jingle": "virgule", "applause": "applaudissements", "bravo": "applaudissements", "whoosh": "transition",
           "souffle": "transition", "tambour": "roulement", "bell": "cloche", "generique": "generique",
           "foret": "foret", "bois": "foret", "oiseaux": "foret", "rain": "pluie", "tempete": "orage",
           "ocean": "mer", "vagues": "mer", "plage": "mer", "cheminee": "feu", "feu_de_cheminee": "feu",
           "feu_de_camp": "feu", "grillons": "nuit", "ruisseau": "riviere", "eau": "riviere",
           "porte_qui_grince": "porte", "grincement": "porte", "pas_": "pas", "bruits_de_pas": "pas",
           "clochette": "cloche_magique", "cloche_magique": "cloche_magique", "fee": "magie", "baguette": "magie",
           "etincelles": "magie", "rires": "rire", "eclat_de_rire": "rire", "miaou": "chat", "ouaf": "chien",
           "wouf": "chien", "meuh": "vache", "bee": "mouton", "coin_coin": "canard", "chouette": "hibou",
           "hou_hou": "hibou", "pioupiou": "oiseau", "croa": "grenouille", "hurlement": "loup", "galop": "cheval",
           "toctoc": "toc_toc", "frapper": "toc_toc", "zzz": "ronflement", "blanc": "bruit_blanc",
           "rose": "bruit_rose"}


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


# ---------------------------------------------------------------------------------------
# Outils de synthèse (filtres par FFT : rapides même pour des sons longs)
# ---------------------------------------------------------------------------------------
def _spectral(x: np.ndarray, shape) -> np.ndarray:
    """Filtre ``x`` par une réponse en fréquence ``shape(f)`` (f en Hz)."""
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    return np.fft.irfft(np.fft.rfft(x) * shape(f), n)


def _band(lo: float, hi: float, soft: float = 0.25):
    def shape(f):
        lf = np.log(np.maximum(f, 1.0))
        return (1 / (1 + np.exp(-(lf - np.log(lo)) / soft))) * (1 / (1 + np.exp((lf - np.log(hi)) / soft)))
    return shape


def _pink(n: int, rng) -> np.ndarray:
    return _spectral(rng.standard_normal(n), lambda f: 1 / np.sqrt(np.maximum(f, 20.0)))


def _brown(n: int, rng) -> np.ndarray:
    return _spectral(rng.standard_normal(n), lambda f: 1 / np.maximum(f, 20.0))


def _norm(x: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    return x / peak if peak > 0 else x


def _lfo(n: int, rate: float, rng, depth: float = 1.0) -> np.ndarray:
    """Variation lente et irrégulière entre 1 - depth et 1."""
    t = np.arange(n) / SR
    v = sum(np.sin(2 * np.pi * rate * k * t + rng.uniform(0, 6.28)) / k for k in (1, 1.618, 2.718))
    v = (v - v.min()) / max(1e-9, v.max() - v.min())
    return 1 - depth + depth * v


def _loopable(x: np.ndarray, xfade: float = 2.0) -> np.ndarray:
    """Boucle sans coupure : la fin est fondue dans le début."""
    k = int(SR * xfade)
    if len(x) <= 2 * k:
        return x
    w = np.linspace(0, 1, k)
    head = x[:k] * w + x[-k:] * (1 - w)
    return np.concatenate([head, x[k:-k]])


def _chirp(f0: float, f1: float, seconds: float, curve: float = 1.0) -> np.ndarray:
    t = np.linspace(0, 1, int(SR * seconds), endpoint=False)
    f = f0 + (f1 - f0) * t ** curve
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


# Voix d'animaux (synthèse additive : harmoniques de la note, filtrées par les formants d'une voyelle)
_VOWELS = {"a": (800, 1200, 2500), "o": (500, 900, 2400), "ou": (350, 800, 2300), "e": (450, 1700, 2500),
           "i": (300, 2300, 3000), "eu": (400, 1400, 2400), "è": (600, 1800, 2600)}


def _voice(f0: np.ndarray, vowels: list[str], bw: float = 120.0, breath: float = 0.05, rng=None,
           nasal: bool = False) -> np.ndarray:
    """Son voisé dont la hauteur suit ``f0`` (Hz, un par échantillon) et la voyelle passe d'une forme à l'autre."""
    n = len(f0)
    t = np.linspace(0, 1, n)
    pos = t * (len(vowels) - 1)
    i0 = np.minimum(pos.astype(int), len(vowels) - 1)
    i1 = np.minimum(i0 + 1, len(vowels) - 1)
    frac = pos - i0
    forms = np.array([_VOWELS[v] for v in vowels], dtype=float)
    fmts = forms[i0] * (1 - frac[:, None]) + forms[i1] * frac[:, None]  # (n, 3)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    out = np.zeros(n)
    kmax = int(min(40, 9000 / max(60.0, float(np.min(f0)))))
    for k in range(1, kmax + 1):
        fk = f0 * k
        amp = np.zeros(n)
        for j, gain in enumerate((1.0, 0.6, 0.3)):
            width = bw * (1 + j) * (1.6 if nasal else 1.0)
            amp += gain * np.exp(-0.5 * ((fk - fmts[:, j]) / width) ** 2)
        amp *= 1 / k ** 0.6
        amp[fk > SR / 2 - 500] = 0
        out += amp * np.sin(k * phase)
    if breath and rng is not None:
        out += breath * _spectral(rng.standard_normal(n), _band(800, 6000)) * np.std(out) * 6
    return out


def _shape(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a, r = max(1, int(n * attack)), max(1, int(n * release))
    e[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    e[-r:] *= np.cos(np.linspace(0, np.pi / 2, r)) ** 2
    return e


# ---------------------------------------------------------------------------------------
# Bruitages ponctuels
# ---------------------------------------------------------------------------------------
def _porte(rng) -> np.ndarray:
    """Grincement : frottement « collé-glissé » (impulsions irrégulières) résonnant dans le bois."""
    secs = 2.2
    n = int(SR * secs)
    t = np.arange(n) / SR
    rate = 90 + 160 * np.sin(np.pi * t / secs) ** 1.5 + 25 * np.sin(2 * np.pi * 1.7 * t)
    phase = np.cumsum(rate / SR)
    pulses = np.diff(np.floor(phase), prepend=0.0) * (0.6 + 0.4 * rng.random(n))
    body = _spectral(pulses, lambda f: np.exp(-0.5 * ((f - 900) / 380) ** 2) + 0.6 * np.exp(-0.5 * ((f - 2300) / 500) ** 2))
    return body * _shape(n, 0.08, 0.2)


def _pas(rng) -> np.ndarray:
    out = np.zeros(int(SR * 3.2))
    at = 0.15
    for i in range(6):
        k = int(SR * 0.16)
        thump = _tone(70 + rng.uniform(-8, 8), 0.16, (1, 0.3), 22.0)
        crunch = _spectral(rng.standard_normal(k), _band(500, 4000)) * np.exp(-np.linspace(0, 9, k)) * 0.5
        _place(out, thump + crunch, at, 0.9 if i % 2 == 0 else 0.75)
        at += 0.48 + rng.uniform(-0.03, 0.03)
    return out


def _cloche_magique(rng) -> np.ndarray:
    out = np.zeros(int(SR * 3.4))
    notes = [1568.0, 1760.0, 2093.0, 2349.3, 2637.0, 3136.0, 3520.0, 4186.0]
    for i, f in enumerate(notes):
        t = _t(2.2)
        tone = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t)) * np.exp(-t * 3.2)
        _place(out, tone, i * 0.085 + rng.uniform(0, 0.02), 0.32)
    shimmer = _spectral(rng.standard_normal(len(out)), _band(6000, 12000)) * np.exp(-np.linspace(0, 4, len(out)))
    return out + shimmer * 0.25


def _magie(rng) -> np.ndarray:
    n = int(SR * 2.4)
    out = np.zeros(n)
    for _ in range(70):
        at = rng.uniform(0, 1.9)
        f = 2000 + 3500 * (at / 1.9) + rng.uniform(-300, 300)
        tt = _t(0.35)
        _place(out, np.sin(2 * np.pi * f * tt) * np.exp(-tt * 14), at, rng.uniform(0.08, 0.22))
    sweep = _chirp(500, 2500, 1.6, 1.4) * 0.2
    _place(out, sweep * _shape(len(sweep), 0.2, 0.5), 0.0)
    return out


def _rire(rng) -> np.ndarray:
    """« Ha ha ha ha » : syllabes voisées sur un « a », de plus en plus graves."""
    out = np.zeros(int(SR * 2.0))
    at = 0.05
    for i in range(6):
        d = 0.13
        n = int(SR * d)
        f0 = np.full(n, 290.0 - i * 14) * (1 + 0.04 * np.linspace(1, -1, n))
        syl = _voice(f0, ["a", "a"], bw=140, breath=0.25, rng=rng)
        _place(out, syl * _shape(n, 0.25, 0.45), at, 1.0 - i * 0.08)
        h = int(SR * 0.06)  # petit souffle entre deux « ha »
        _place(out, _spectral(rng.standard_normal(h), _band(900, 4000)) * _shape(h, 0.3, 0.6), at + d, 0.15)
        at += 0.21
    return out


def _tonnerre(rng) -> np.ndarray:
    n = int(SR * 5.0)
    t = np.arange(n) / SR
    rumble = _brown(n, rng)
    env = np.exp(-t * 0.9) * (0.6 + 0.4 * _lfo(n, 2.5, rng))
    crack = _spectral(rng.standard_normal(n), _band(300, 5000)) * np.exp(-t * 9)
    return _norm(rumble) * env + 0.35 * _norm(crack)


def _toc_toc(rng) -> np.ndarray:
    out = np.zeros(int(SR * 1.4))
    for i, at in enumerate((0.05, 0.3, 0.55)):
        k = int(SR * 0.12)
        knock = _tone(180, 0.12, (1, 0.5, 0.2), 30.0) + _spectral(rng.standard_normal(k), _band(400, 2500)) * \
            np.exp(-np.linspace(0, 14, k)) * 0.6
        _place(out, knock, at, 0.9)
    return out


def _chat(rng) -> np.ndarray:
    n = int(SR * 0.95)
    t = np.linspace(0, 1, n)
    f0 = 480 + 330 * np.sin(np.pi * np.minimum(1, t * 1.25)) ** 1.2 - 80 * t
    return _voice(f0, ["i", "è", "a", "o", "ou"], bw=150, breath=0.05, rng=rng) * _shape(n, 0.12, 0.35)


def _chien(rng) -> np.ndarray:
    out = np.zeros(int(SR * 1.2))
    for at in (0.02, 0.42):
        n = int(SR * 0.22)
        t = np.linspace(0, 1, n)
        f0 = 360 + 120 * np.exp(-t * 6) - 60 * t
        bark = _voice(f0, ["ou", "a", "o"], bw=180, breath=0.6, rng=rng)
        _place(out, bark * _shape(n, 0.05, 0.5), at)
    return out


def _vache(rng) -> np.ndarray:
    n = int(SR * 1.9)
    t = np.linspace(0, 1, n)
    f0 = 118 + 22 * np.sin(np.pi * t) - 14 * t
    return _voice(f0, ["eu", "eu", "ou"], bw=90, breath=0.08, rng=rng) * _shape(n, 0.15, 0.3)


def _mouton(rng) -> np.ndarray:
    n = int(SR * 1.2)
    t = np.arange(n) / SR
    f0 = 310 * (1 + 0.06 * np.sin(2 * np.pi * 7.5 * t)) - 30 * t
    return _voice(f0, ["è", "è", "e"], bw=150, breath=0.12, rng=rng) * _shape(n, 0.08, 0.3) * \
        (0.75 + 0.25 * np.sin(2 * np.pi * 7.5 * t))


def _canard(rng) -> np.ndarray:
    out = np.zeros(int(SR * 1.0))
    for at in (0.02, 0.36):
        n = int(SR * 0.22)
        f0 = np.full(n, 420.0) * (1 - 0.1 * np.linspace(0, 1, n))
        q = _voice(f0, ["a", "è"], bw=260, breath=0.3, rng=rng, nasal=True)
        _place(out, q * _shape(n, 0.06, 0.4), at)
    return out


def _hibou(rng) -> np.ndarray:
    out = np.zeros(int(SR * 2.4))
    for at, f, d in ((0.05, 410, 0.5), (0.85, 380, 0.35), (1.3, 395, 0.8)):
        n = int(SR * d)
        f0 = np.full(n, float(f)) * (1 + 0.015 * np.sin(np.linspace(0, np.pi, n)))
        _place(out, _voice(f0, ["ou", "ou"], bw=70, breath=0.04, rng=rng) * _shape(n, 0.3, 0.5), at)
    return out


def _oiseau(rng) -> np.ndarray:
    out = np.zeros(int(SR * 1.6))
    at = 0.03
    for _ in range(int(rng.integers(4, 7))):
        d = rng.uniform(0.05, 0.12)
        f0, f1 = rng.uniform(2800, 4200), rng.uniform(3000, 5200)
        c = _chirp(f0, f1, d, rng.uniform(0.6, 1.6))
        _place(out, c * _shape(len(c), 0.2, 0.4), at, rng.uniform(0.4, 0.8))
        at += d + rng.uniform(0.04, 0.16)
    return out


def _grenouille(rng) -> np.ndarray:
    out = np.zeros(int(SR * 1.3))
    for at in (0.05, 0.6):
        n = int(SR * 0.38)
        t = np.arange(n) / SR
        f0 = np.full(n, 120.0)
        croak = _voice(f0, ["o", "a"], bw=110, breath=0.1, rng=rng)
        croak *= (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 28 * t))) * _shape(n, 0.1, 0.35)
        _place(out, croak, at)
    return out


def _loup(rng) -> np.ndarray:
    n = int(SR * 3.2)
    t = np.linspace(0, 1, n)
    f0 = 380 + 260 * np.sin(np.pi * np.minimum(1, t * 1.4)) ** 0.7 - 120 * t
    howl = _voice(f0 * (1 + 0.01 * np.sin(2 * np.pi * 5 * t * 3.2)), ["ou", "o", "ou"], bw=90, breath=0.06, rng=rng)
    howl = howl * _shape(n, 0.2, 0.35)
    echo = np.zeros_like(howl)  # lointain : un peu d'écho
    d = int(SR * 0.23)
    echo[d:] = howl[:-d] * 0.35
    return _spectral(howl + echo, _band(250, 3000))


def _cheval(rng) -> np.ndarray:
    out = np.zeros(int(SR * 2.6))
    at = 0.05
    while at < 2.3:
        for off in (0.0, 0.07, 0.14):  # galop : trois appuis rapprochés
            k = int(SR * 0.08)
            hit = _tone(110, 0.08, (1, 0.4), 30.0) + _spectral(rng.standard_normal(k), _band(300, 3000)) * \
                np.exp(-np.linspace(0, 12, k)) * 0.5
            _place(out, hit, at + off, 0.8)
        at += 0.42
    return out


def _ronflement(rng) -> np.ndarray:
    n = int(SR * 3.6)
    t = np.arange(n) / SR
    buzz = _voice(np.full(n, 75.0), ["o", "o"], bw=120, breath=0.4, rng=rng)
    breathe = np.clip(np.sin(2 * np.pi * t / 3.6) * 1.4, 0, 1) ** 1.5
    whistle = _spectral(rng.standard_normal(n), _band(1500, 4000)) * np.clip(-np.sin(2 * np.pi * t / 3.6), 0, 1) * 0.6
    return _norm(buzz) * breathe + whistle * 0.25


# ---------------------------------------------------------------------------------------
# Fonds d'ambiance (boucles de 20 à 30 secondes)
# ---------------------------------------------------------------------------------------
def _amb_pluie(rng, secs: float = 24.0) -> np.ndarray:
    n = int(SR * (secs + 2))
    bed = _spectral(rng.standard_normal(n), _band(500, 9000, 0.4)) * _lfo(n, 0.07, rng, 0.25)
    drops = np.zeros(n)
    for _ in range(int(secs * 40)):
        k = int(SR * 0.012)
        d = rng.standard_normal(k) * np.exp(-np.linspace(0, 10, k))
        i = int(rng.integers(0, n - k))
        drops[i:i + k] += d * rng.uniform(0.2, 1.0)
    drops = _spectral(drops, _band(1500, 9000))
    return _loopable(_norm(bed) + 0.5 * _norm(drops))


def _amb_orage(rng, secs: float = 30.0) -> np.ndarray:
    rain = _amb_pluie(rng, secs)
    n = len(rain)
    out = rain * 0.8
    for at in (3.0, 15.5, 24.0):
        th = _tonnerre(rng)
        i = int(at * SR)
        j = min(n, i + len(th))
        out[i:j] += th[: j - i] * 0.9
    return out


def _amb_mer(rng, secs: float = 28.0) -> np.ndarray:
    n = int(SR * (secs + 2))
    t = np.arange(n) / SR
    swell = (0.5 + 0.5 * np.sin(2 * np.pi * t / 7.0 - 1.2)) ** 2.2  # une vague toutes les 7 secondes
    surf = _spectral(rng.standard_normal(n), _band(200, 5000, 0.5)) * swell
    deep = _brown(n, rng) * (0.6 + 0.4 * swell)
    return _loopable(_norm(surf) + 0.5 * _norm(deep))


def _amb_vent(rng, secs: float = 26.0) -> np.ndarray:
    n = int(SR * (secs + 2))
    gust = _lfo(n, 0.09, rng, 0.8)
    body = _spectral(rng.standard_normal(n), _band(150, 1200, 0.35)) * gust
    t = np.arange(n) / SR
    f = 520 + 180 * gust + 30 * np.sin(2 * np.pi * 0.3 * t)
    whistle = np.sin(2 * np.pi * np.cumsum(f) / SR) * (gust - 0.4).clip(0) * 0.08
    return _loopable(_norm(body) + whistle)


def _amb_foret(rng, secs: float = 30.0) -> np.ndarray:
    n = int(SR * (secs + 2))
    breeze = _spectral(rng.standard_normal(n), _band(200, 2500, 0.4)) * _lfo(n, 0.06, rng, 0.6)
    out = _norm(breeze) * 0.35
    at = 0.5
    while at < secs:
        song = _oiseau(rng)
        i = int(at * SR)
        j = min(n, i + len(song))
        out[i:j] += song[: j - i] * rng.uniform(0.15, 0.4)
        at += rng.uniform(1.5, 4.5)
    return _loopable(out)


def _amb_feu(rng, secs: float = 24.0) -> np.ndarray:
    n = int(SR * (secs + 2))
    roar = _brown(n, rng) * _lfo(n, 0.2, rng, 0.4)
    crackle = np.zeros(n)
    for _ in range(int(secs * 18)):
        k = int(SR * rng.uniform(0.002, 0.008))
        i = int(rng.integers(0, n - k))
        crackle[i:i + k] += rng.standard_normal(k) * rng.uniform(0.1, 1.0) ** 2
    crackle = _spectral(crackle, _band(1200, 9000))
    return _loopable(_norm(roar) * 0.5 + _norm(crackle))


def _amb_nuit(rng, secs: float = 24.0) -> np.ndarray:
    n = int(SR * (secs + 2))
    t = np.arange(n) / SR
    out = _norm(_spectral(rng.standard_normal(n), _band(150, 1500))) * 0.12
    for f, rate, ph in ((4400, 0.9, 0.0), (4750, 1.15, 1.7), (4100, 0.7, 3.1)):
        chirps = (np.sin(2 * np.pi * 28 * t) > 0.2) * (np.sin(2 * np.pi * rate * t + ph) > 0.55)
        smooth = _spectral(chirps.astype(float), lambda fr: np.exp(-fr / 200))
        out += np.sin(2 * np.pi * f * t) * smooth * 0.12
    return _loopable(out)


def _amb_riviere(rng, secs: float = 24.0) -> np.ndarray:
    n = int(SR * (secs + 2))
    flow = _spectral(rng.standard_normal(n), _band(300, 6000, 0.35)) * _lfo(n, 0.5, rng, 0.35)
    bubbles = np.zeros(n)
    for _ in range(int(secs * 12)):
        d = rng.uniform(0.02, 0.06)
        c = _chirp(rng.uniform(500, 900), rng.uniform(900, 1600), d)
        i = int(rng.integers(0, n - len(c)))
        bubbles[i:i + len(c)] += c * _shape(len(c), 0.2, 0.5) * rng.uniform(0.1, 0.5)
    return _loopable(_norm(flow) + 0.4 * _norm(bubbles))


def _amb_blanc(rng, secs: float = 20.0) -> np.ndarray:
    return _loopable(_spectral(rng.standard_normal(int(SR * (secs + 2))), _band(40, 12000, 0.2)))


def _amb_rose(rng, secs: float = 20.0) -> np.ndarray:
    return _loopable(_pink(int(SR * (secs + 2)), rng))


_AMBIENCES = {"foret": _amb_foret, "pluie": _amb_pluie, "orage": _amb_orage, "mer": _amb_mer, "vent": _amb_vent,
              "feu": _amb_feu, "nuit": _amb_nuit, "riviere": _amb_riviere, "bruit_blanc": _amb_blanc,
              "bruit_rose": _amb_rose}


def _roulement(rng) -> np.ndarray:  # conservé pour les anciens textes (« [son: roulement] »)
    n = int(SR * 2.4)
    out = np.zeros(n)
    t = 0.0
    while t < 2.0:
        hit = rng.standard_normal(int(SR * 0.05)) * np.exp(-np.linspace(0, 10, int(SR * 0.05)))
        _place(out, hit, t, 0.25 + 0.45 * t / 2.0)
        t += 0.045 + rng.uniform(-0.006, 0.006)
    boom = _tone(70, 0.6, (1, 0.5), 6.0) + rng.standard_normal(int(SR * 0.6)) * np.exp(-_t(0.6) * 12) * 0.6
    _place(out, boom, 2.0, 0.9)
    return out - _spectral(out, lambda f: np.exp(-f / 80))


_GENERATORS = {"virgule": _virgule, "applaudissements": _applause, "transition": _transition, "ding": _ding,
               "cloche": _cloche, "roulement": _roulement, "suspense": _suspense, "notification": _notification,
               "generique": _generique, "porte": _porte, "pas": _pas, "cloche_magique": _cloche_magique,
               "magie": _magie, "rire": _rire, "tonnerre": _tonnerre, "toc_toc": _toc_toc, "chat": _chat,
               "chien": _chien, "vache": _vache, "mouton": _mouton, "canard": _canard, "hibou": _hibou,
               "oiseau": _oiseau, "grenouille": _grenouille, "loup": _loup, "cheval": _cheval,
               "ronflement": _ronflement, "berceuse": lambda rng: lullaby(75.0)}


_LOCK = threading.Lock()


def _write_generated(target: Path, sig: np.ndarray, peak_db: float = -3.0, fades: tuple[float, float] = (3, 30)) -> None:
    sig = sig.astype(np.float64)
    peak = float(np.max(np.abs(sig))) or 1.0
    sig = sig / peak * audio.db_to_lin(peak_db)
    if fades:
        sig = audio.apply_fades(sig.astype(np.float32), SR, *fades)
    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix=f".{target.stem}-", dir=str(target.parent))
    os.close(fd)
    audio.write_audio(tmp, sig.astype(np.float32), SR, subtype="PCM_16")
    os.replace(tmp, target)


def ensure_builtin(name: str) -> Path:
    target = builtin_dir() / f"{name}.wav"
    if target.exists():
        return target
    with _LOCK:  # plusieurs pages peuvent demander le même son en même temps
        if not target.exists():
            rng = np.random.default_rng(sum(map(ord, name)))
            _write_generated(target, _GENERATORS[name](rng))
    return target


def ensure_ambience(name: str) -> Path:
    """Boucle d'ambiance (normalisée en niveau moyen, sans fondu : elle se répète sans coupure)."""
    target = builtin_dir() / f"ambiance-{name}.wav"
    if target.exists():
        return target
    with _LOCK:
        if not target.exists():
            rng = np.random.default_rng(sum(map(ord, name)) + 7)
            sig = _AMBIENCES[name](rng).astype(np.float64)
            rms = float(np.sqrt(np.mean(sig ** 2))) or 1.0
            sig = sig * (audio.db_to_lin(AMBIENCE_RMS_DB) / rms)
            peak = float(np.max(np.abs(sig)))
            if peak > 0.95:
                sig *= 0.95 / peak
            fd, tmp = tempfile.mkstemp(suffix=".wav", prefix=f".{name}-", dir=str(target.parent))
            os.close(fd)
            audio.write_audio(tmp, sig.astype(np.float32), SR, subtype="PCM_16")
            os.replace(tmp, target)
    return target


AMBIENCE_RMS_DB = -20.0  # niveau moyen des boucles, comparable à celui des voix


def ambience_key(name: str) -> str | None:
    """Nom canonique d'un fond d'ambiance (« Forêt », « pluie douce »…), ou None s'il n'existe pas."""
    key = slug(name)
    key = ALIASES.get(key, key)
    if key in _AMBIENCES:
        return key
    first = key.split("_")[0]
    first = ALIASES.get(first, first)
    return first if first in _AMBIENCES else None


def resolve_ambience(name: str, project_dir: Path | None = None) -> Path | None:
    """Fichier d'un fond d'ambiance : boucle intégrée, ou son personnel du même nom."""
    mine = user_sounds(project_dir)
    key = slug(name)
    if key in mine:
        return mine[key]
    canon = ambience_key(name)
    return ensure_ambience(canon) if canon else None


def loop_to(data: np.ndarray, n: int) -> np.ndarray:
    """Répète une boucle jusqu'à ``n`` échantillons."""
    if n <= 0 or data.size == 0:
        return np.zeros(max(0, n), dtype=np.float32)
    reps = int(np.ceil(n / len(data)))
    return np.tile(data, reps)[:n].astype(np.float32)


# ---------------------------------------------------------------------------------------
# Berceuse (« Au clair de la lune », chanson traditionnelle du domaine public, en boîte à musique)
# ---------------------------------------------------------------------------------------
_C4 = 261.63
_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _note_freq(name: str) -> float:
    octave = int(name[-1])
    return _C4 * 2 ** ((_SEMI[name[0]] + 12 * (octave - 4)) / 12)


# (note, durée en temps)
LULLABY_MELODY = (
    [("C5", 1), ("C5", 1), ("C5", 1), ("D5", 1), ("E5", 2), ("D5", 2), ("C5", 1), ("E5", 1), ("D5", 1), ("D5", 1),
     ("C5", 4)] * 2
    + [("D5", 1), ("D5", 1), ("D5", 1), ("D5", 1), ("A4", 2), ("A4", 2), ("D5", 1), ("C5", 1), ("B4", 1), ("A4", 1),
       ("G4", 4)]
    + [("C5", 1), ("C5", 1), ("C5", 1), ("D5", 1), ("E5", 2), ("D5", 2), ("C5", 1), ("E5", 1), ("D5", 1), ("D5", 1),
       ("C5", 4)]
)
# accord de chaque mesure (4 temps)
LULLABY_CHORDS = ["C", "C", "G", "C", "C", "C", "G", "C", "G", "D", "D", "G", "C", "C", "G", "C"]
_CHORD_NOTES = {"C": ("C3", "G3", "E4"), "G": ("G2", "D3", "B3"), "D": ("D3", "A3", "F4")}


def _music_box(freq: float, seconds: float) -> np.ndarray:
    t = _t(seconds)
    partials = [(1.0, 1.0, 2.2), (2.0, 0.35, 3.5), (3.0, 0.12, 5.0), (4.2, 0.08, 7.0)]
    return sum(a * np.sin(2 * np.pi * freq * r * t) * np.exp(-t * d) for r, a, d in partials) * \
        (1 - np.exp(-t * 400))


def lullaby(seconds: float = 75.0, bpm: float = 70.0) -> np.ndarray:
    """Berceuse en boîte à musique sur une nappe d'accords, de plus en plus lente, qui s'éteint en fondu."""
    seconds = max(20.0, float(seconds))
    n = int(SR * seconds)
    out = np.zeros(n + SR * 6)
    at = 1.0
    beat = 60.0 / bpm
    beats_done = 0
    while at < seconds:  # la mélodie reprend tant que la durée n'est pas atteinte
        for note, beats in LULLABY_MELODY:
            if at >= seconds:
                break
            slow = 1.0 + 0.35 * (at / seconds) ** 2  # ralentit peu à peu
            if beats_done % 4 == 0:  # début de mesure : accord tenu très doucement
                chord = LULLABY_CHORDS[(beats_done // 4) % len(LULLABY_CHORDS)]
                tt = _t(4 * beat * slow + 0.6)
                pad = sum(np.sin(2 * np.pi * _note_freq(nm) * tt) for nm in _CHORD_NOTES[chord])
                _place(out, pad * _shape(len(tt), 0.35, 0.45), at, 0.06)
            _place(out, _music_box(_note_freq(note), 2.5), at, 0.5)
            at += beats * beat * slow
            beats_done += beats
    out = out[:n]
    fade = np.ones(n)
    k = int(min(n * 0.4, SR * 20))
    fade[-k:] = np.cos(np.linspace(0, np.pi / 2, k)) ** 2
    return (out * fade).astype(np.float32)


def sleep_noise(kind: str, seconds: float) -> np.ndarray:
    """Bruit d'endormissement (pluie, bruit blanc…) qui s'éteint très progressivement."""
    n = int(SR * max(0.0, seconds))
    if n == 0 or kind not in _AMBIENCES:
        return np.zeros(n, dtype=np.float32)
    loop, _sr = audio.read_audio(ensure_ambience(kind))
    data = loop_to(loop, n)
    t = np.linspace(0, 1, n)
    env = np.minimum(1.0, t / 0.03) * (1 - t) ** 1.6  # monte en 3 %, puis baisse doucement jusqu'au silence
    return (data * env).astype(np.float32)


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
    """[(nom à écrire dans la balise, libellé)] : bruitages intégrés puis sons personnels."""
    out = [(k, v) for k, v in BUILTIN_LABELS.items()]
    out += [(f.stem, f"{f.stem} (mes sons)") for f in user_sounds(project_dir).values()]
    return out


def resolve_name(name: str) -> str | None:
    """Nom canonique d'un bruitage intégré (« Porte qui grince » → « porte »), sans générer le son."""
    key = slug(name)
    key = ALIASES.get(key, key)
    if key in _GENERATORS or key in _AMBIENCES:
        return key
    first = ALIASES.get(key.split("_")[0], key.split("_")[0])
    return first if first in _GENERATORS else None


def resolve(name: str, project_dir: Path | None = None) -> Path | None:
    key = slug(name)
    key = ALIASES.get(key, key)
    mine = user_sounds(project_dir)
    if key in mine:  # un son personnel du même nom remplace le son intégré
        return mine[key]
    if key in _GENERATORS:
        return ensure_builtin(key)
    if key in _AMBIENCES:  # « [son: pluie] » : quelques secondes du fond d'ambiance
        return ensure_ambience(key)
    p = Path(name.strip())
    if p.is_absolute() and p.is_file():
        return p
    return None
