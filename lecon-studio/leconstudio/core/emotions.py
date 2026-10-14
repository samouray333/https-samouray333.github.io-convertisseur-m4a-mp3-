"""Émotions par passage : ajustements des réglages de chaque moteur."""

from __future__ import annotations

import dataclasses

from .models import VoiceProfile

# speed : multiplicateur de débit ; gain_db : correction de volume après synthèse ;
# les autres clés sont des réglages propres à chaque moteur.
EMOTION_SETTINGS: dict[str, dict] = {
    "joyeux": {"speed": 1.04, "chatterbox": {"exaggeration": 0.8, "cfg_weight": 0.45},
               "xtts": {"temperature": 0.8}, "edge": {"pitch": 6}, "fastclone": {"pitch": 6}},
    "triste": {"speed": 0.9, "chatterbox": {"exaggeration": 0.35, "cfg_weight": 0.3},
               "xtts": {"temperature": 0.6}, "edge": {"pitch": -6}, "fastclone": {"pitch": -6}},
    "colère": {"speed": 1.05, "chatterbox": {"exaggeration": 1.1, "cfg_weight": 0.35},
               "xtts": {"temperature": 0.85}, "edge": {"pitch": 3}, "fastclone": {"pitch": 3}},
    "chuchoté": {"speed": 0.94, "gain_db": -7.0, "chatterbox": {"exaggeration": 0.3},
                 "xtts": {"temperature": 0.6}, "edge": {"pitch": -2}, "fastclone": {"pitch": -2}},
    "calme": {"speed": 0.95, "chatterbox": {"exaggeration": 0.3, "cfg_weight": 0.4},
              "xtts": {"temperature": 0.55}},
    "peur": {"speed": 1.06, "chatterbox": {"exaggeration": 0.9, "cfg_weight": 0.35},
             "xtts": {"temperature": 0.85}, "edge": {"pitch": 4}, "fastclone": {"pitch": 4}},
    "excité": {"speed": 1.08, "chatterbox": {"exaggeration": 1.2, "cfg_weight": 0.3},
               "xtts": {"temperature": 0.9}, "edge": {"pitch": 8}, "fastclone": {"pitch": 8}},
}


def apply_emotion(voice: VoiceProfile, emotion: str) -> tuple[VoiceProfile, float, float]:
    """Renvoie (voix ajustée, multiplicateur de débit, gain en dB) pour une émotion."""
    cfg = EMOTION_SETTINGS.get(emotion or "")
    if not cfg:
        return voice, 1.0, 0.0
    params = dict(voice.params or {})
    for key, value in cfg.get(voice.engine, {}).items():
        if key == "pitch":
            params[key] = float(params.get(key, 0)) + value
        else:
            params[key] = value
    adjusted = dataclasses.replace(voice, params=params)
    adjusted.dir = voice.dir
    return adjusted, float(cfg.get("speed", 1.0)), float(cfg.get("gain_db", 0.0))
