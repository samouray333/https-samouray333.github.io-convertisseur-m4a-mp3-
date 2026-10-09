"""Processus de synthèse neuronale d'AudioLivre Studio.

Ce script est exécuté par l'interpréteur Python de l'environnement d'un moteur
(XTTS-v2, Chatterbox, Kokoro…), installé à la demande. Il ne dépend pas du reste
de l'application : il dialogue avec elle par des lignes JSON sur stdin/stdout.

Requêtes : {"id": 1, "cmd": "ping|load|speakers|synth|quit", ...}
Réponses : {"id": 1, "ok": true, ...} ou {"id": 1, "ok": false, "error": "..."}
Événements : {"event": "log", "msg": "..."}
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
import wave

PROTO = None  # flux réservé au protocole (le stdout d'origine)


def send(obj: dict) -> None:
    PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
    PROTO.flush()


def log(msg: str) -> None:
    send({"event": "log", "msg": str(msg)})


def write_wav(path: str, samples, sr: int) -> float:
    """Écrit un WAV 16 bits mono sans dépendance externe ; renvoie la durée."""
    import numpy as np

    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    arr = np.nan_to_num(arr)
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 1.0:
        arr = arr / peak
    pcm = (np.clip(arr, -1.0, 1.0) * 32767.0).astype("<i2")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())
    return len(arr) / float(sr)


def to_numpy(x):
    if hasattr(x, "detach"):
        x = x.detach().cpu().float().numpy()
    import numpy as np

    return np.asarray(x, dtype=np.float32).reshape(-1)


def pick_device(requested: str) -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    if requested in ("cuda", "auto") and torch.cuda.is_available():
        return "cuda"
    if requested in ("mps", "auto") and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def set_seed(seed) -> None:
    if seed is None:
        return
    import random

    random.seed(int(seed))
    try:
        import numpy as np

        np.random.seed(int(seed) % (2 ** 32))
    except Exception:
        pass
    try:
        import torch

        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))
    except Exception:
        pass


def device_info(device: str) -> dict:
    info = {"device": device}
    try:
        import torch

        info["torch"] = torch.__version__
        if device == "cuda":
            info["gpu"] = torch.cuda.get_device_name(0)
            info["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 1024 ** 3, 1)
    except Exception:
        pass
    return info


# =======================================================================================
# Moteurs
# =======================================================================================
class Backend:
    sr = 24000
    device = "cpu"

    def load(self, device: str, options: dict) -> dict:
        raise NotImplementedError

    def speakers(self) -> list:
        return []

    def synth(self, req: dict) -> dict:
        raise NotImplementedError


class DummyBackend(Backend):
    """Moteur de test : produit une tonalité dont la durée suit la longueur du texte."""

    def load(self, device, options):
        self.device = "cpu"
        return {"sr": self.sr, "device": "cpu"}

    def speakers(self):
        return [{"id": "test", "name": "Test", "language": "fr", "gender": ""}]

    def synth(self, req):
        import numpy as np

        dur = max(0.4, len(req.get("text", "")) * 0.055 / float(req.get("params", {}).get("speed", 1.0) or 1.0))
        t = np.arange(int(dur * self.sr)) / self.sr
        sig = 0.3 * np.sin(2 * math.pi * 220 * t) * (0.6 + 0.4 * np.sin(2 * math.pi * 4 * t))
        return {"duration": write_wav(req["out"], sig, self.sr)}

    def convert(self, req):
        import shutil

        shutil.copyfile(req["source"], req["out"])
        return {"duration": 0.0}

    def transcribe(self, req):
        return {"text": req.get("expected", "")}


XTTS_LANGS = {"zh": "zh-cn"}


class XttsBackend(Backend):
    MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

    def load(self, device, options):
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.api import TTS

        self.device = pick_device(device)
        log("Chargement du modèle XTTS-v2 (le premier lancement télécharge environ 1,8 Go)…")
        t0 = time.time()
        self.tts = TTS(self.MODEL, progress_bar=False).to(self.device)
        self.model = self.tts.synthesizer.tts_model
        self.sr = int(getattr(self.model.config.audio, "output_sample_rate", 24000) or 24000)
        self.cache = {}
        log(f"XTTS-v2 prêt sur {self.device} en {time.time() - t0:.0f} s")
        return {"sr": self.sr, **device_info(self.device)}

    def speakers(self):
        sm = getattr(self.model, "speaker_manager", None)
        if not sm:
            return []
        return [{"id": n, "name": n, "language": "multi", "gender": ""} for n in sorted(sm.speakers.keys())]

    def _latents(self, refs, speaker):
        if refs:
            key = tuple((r, os.path.getmtime(r)) for r in refs)
            if key not in self.cache:
                log("Analyse de la voix de référence…")
                self.cache[key] = self.model.get_conditioning_latents(
                    audio_path=list(refs), gpt_cond_len=30, gpt_cond_chunk_len=4, max_ref_length=60
                )
            return self.cache[key]
        sm = self.model.speaker_manager
        name = speaker if speaker in sm.speakers else sorted(sm.speakers.keys())[0]
        values = list(sm.speakers[name].values())
        return values[0], values[1]

    def synth(self, req):
        p = req.get("params", {})
        lang = req.get("language", "fr").lower()
        lang = XTTS_LANGS.get(lang, lang.split("-")[0])
        gpt, spk = self._latents(req.get("refs") or [], req.get("speaker"))
        set_seed(req.get("seed"))
        out = self.model.inference(
            req["text"], lang, gpt, spk,
            temperature=float(p.get("temperature", 0.7)),
            length_penalty=1.0,
            repetition_penalty=float(p.get("repetition_penalty", 5.0)),
            top_k=int(p.get("top_k", 50)),
            top_p=float(p.get("top_p", 0.85)),
            speed=float(p.get("speed", 1.0)),
            enable_text_splitting=False,
        )
        return {"duration": write_wav(req["out"], to_numpy(out["wav"]), self.sr)}


class ChatterboxBackend(Backend):
    def load(self, device, options):
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        self.device = pick_device(device)
        log("Chargement de Chatterbox multilingue (le premier lancement télécharge environ 3 Go)…")
        t0 = time.time()
        self.model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
        self.sr = int(self.model.sr)
        self.current = None
        log(f"Chatterbox prêt sur {self.device} en {time.time() - t0:.0f} s")
        return {"sr": self.sr, **device_info(self.device)}

    def synth(self, req):
        p = req.get("params", {})
        refs = req.get("refs") or []
        exaggeration = float(p.get("exaggeration", 0.5))
        key = (refs[0] if refs else None, os.path.getmtime(refs[0]) if refs else 0, exaggeration)
        if refs and key != self.current:
            self.model.prepare_conditionals(refs[0], exaggeration=exaggeration)
            self.current = key
        elif not refs and self.current is not None:
            raise RuntimeError("Chatterbox nécessite une voix clonée (enregistrement de référence).")
        set_seed(req.get("seed"))
        lang = req.get("language", "fr").lower().split("-")[0]
        wav = self.model.generate(
            req["text"], language_id=lang, exaggeration=exaggeration,
            cfg_weight=float(p.get("cfg_weight", 0.5)), temperature=float(p.get("temperature", 0.8)),
        )
        return {"duration": write_wav(req["out"], to_numpy(wav), self.sr)}


KOKORO_LANGS = {"fr": "fr-fr", "en": "en-us", "en-gb": "en-gb", "es": "es", "it": "it", "pt": "pt-br",
                "hi": "hi", "ja": "ja", "zh": "cmn"}


class KokoroBackend(Backend):
    def load(self, device, options):
        from kokoro_onnx import Kokoro

        model_dir = options.get("model_dir") or os.path.join(os.path.dirname(sys.executable), "kokoro")
        model = os.path.join(model_dir, "kokoro-v1.0.onnx")
        voices = os.path.join(model_dir, "voices-v1.0.bin")
        if not (os.path.exists(model) and os.path.exists(voices)):
            raise RuntimeError("Fichiers du modèle Kokoro manquants : réinstallez le moteur.")
        self.kokoro = Kokoro(model, voices)
        self.sr = 24000
        self.device = "cpu"
        return {"sr": self.sr, "device": "cpu"}

    def speakers(self):
        out = []
        for v in sorted(self.kokoro.get_voices()):
            prefix = v[:1]
            lang = {"a": "en", "b": "en", "f": "fr", "e": "es", "i": "it", "p": "pt", "h": "hi", "j": "ja",
                    "z": "zh"}.get(prefix, "")
            out.append({"id": v, "name": v, "language": lang, "gender": "F" if v[1:2] == "f" else "M"})
        return out

    def _style(self, spec: str):
        # « ff_siwis » ou mélange « ff_siwis:0.6,af_bella:0.4 »
        if ":" not in spec and "," not in spec:
            return spec
        total = None
        weights = 0.0
        for part in spec.split(","):
            name, _, w = part.partition(":")
            w = float(w or 1.0)
            style = self.kokoro.get_voice_style(name.strip()) * w
            total = style if total is None else total + style
            weights += w
        return total / max(weights, 1e-6)

    def synth(self, req):
        p = req.get("params", {})
        lang = req.get("language", "fr").lower()
        lang = KOKORO_LANGS.get(lang, KOKORO_LANGS.get(lang.split("-")[0], "en-us"))
        samples, sr = self.kokoro.create(req["text"], voice=self._style(req.get("speaker") or "ff_siwis"),
                                         speed=float(p.get("speed", 1.0)), lang=lang)
        return {"duration": write_wav(req["out"], samples, sr)}


class ChatterboxVCBackend(Backend):
    """Conversion de voix : transforme un enregistrement pour lui donner le timbre de la voix clonée."""

    def load(self, device, options):
        from chatterbox.vc import ChatterboxVC

        self.device = pick_device(device)
        log("Chargement du convertisseur de voix (le premier lancement télécharge environ 1 Go)…")
        t0 = time.time()
        self.model = ChatterboxVC.from_pretrained(self.device)
        self.sr = int(self.model.sr)
        self.current = None
        log(f"Convertisseur prêt sur {self.device} en {time.time() - t0:.0f} s")
        return {"sr": self.sr, **device_info(self.device)}

    def convert(self, req):
        refs = req.get("refs") or []
        if not refs:
            raise RuntimeError("Aucun enregistrement de référence pour la conversion.")
        key = (refs[0], os.path.getmtime(refs[0]))
        if key != self.current:
            self.model.set_target_voice(refs[0])
            self.current = key
        wav = self.model.generate(req["source"])
        return {"duration": write_wav(req["out"], to_numpy(wav), self.sr)}


class WhisperBackend(Backend):
    """Reconnaissance vocale (relecture automatique des passages produits)."""

    def load(self, device, options):
        from faster_whisper import WhisperModel

        size = options.get("model") or "base"
        log(f"Chargement de Whisper « {size} » (le premier lancement télécharge le modèle)…")
        self.model = WhisperModel(size, device="cpu", compute_type="int8",
                                  download_root=options.get("model_dir") or None)
        return {"sr": 16000, "device": "cpu", "model": size}

    def transcribe(self, req):
        lang = (req.get("language") or "fr").split("-")[0]
        segments, _info = self.model.transcribe(req["path"], language=lang, beam_size=1,
                                                condition_on_previous_text=False, vad_filter=False)
        return {"text": " ".join(seg.text.strip() for seg in segments).strip()}


BACKENDS = {"dummy": DummyBackend, "xtts": XttsBackend, "chatterbox": ChatterboxBackend, "kokoro": KokoroBackend,
            "chatterbox_vc": ChatterboxVCBackend, "whisper": WhisperBackend}


# =======================================================================================
# Boucle principale
# =======================================================================================
def main() -> int:
    global PROTO
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=sorted(BACKENDS))
    args = parser.parse_args()

    # Le stdout d'origine est réservé au protocole ; tout le reste (bibliothèques, C) va sur stderr.
    PROTO = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    stdin = open(sys.stdin.fileno(), "r", encoding="utf-8", closefd=False)

    backend = BACKENDS[args.engine]()
    loaded = False
    send({"event": "ready", "engine": args.engine, "python": sys.version.split()[0]})
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        cmd = req.get("cmd")
        try:
            if cmd == "ping":
                send({"id": rid, "ok": True, "loaded": loaded})
            elif cmd == "load":
                info = backend.load(req.get("device", "auto"), req.get("options", {}))
                loaded = True
                send({"id": rid, "ok": True, **info})
            elif cmd == "speakers":
                send({"id": rid, "ok": True, "speakers": backend.speakers()})
            elif cmd == "synth":
                if not loaded:
                    backend.load(req.get("device", "auto"), req.get("options", {}))
                    loaded = True
                t0 = time.time()
                res = backend.synth(req)
                send({"id": rid, "ok": True, "out": req["out"], "elapsed": time.time() - t0, **res})
            elif cmd in ("convert", "transcribe"):
                if not loaded:
                    backend.load(req.get("device", "auto"), req.get("options", {}))
                    loaded = True
                t0 = time.time()
                res = getattr(backend, cmd)(req)
                send({"id": rid, "ok": True, "elapsed": time.time() - t0, **res})
            elif cmd == "quit":
                send({"id": rid, "ok": True})
                break
            else:
                send({"id": rid, "ok": False, "error": f"Commande inconnue : {cmd}"})
        except Exception as exc:  # noqa: BLE001
            msg = str(exc) or exc.__class__.__name__
            if "out of memory" in msg.lower():
                msg = ("Mémoire de la carte graphique insuffisante. Essayez le mode processeur (CPU) "
                       "dans les Paramètres ou fermez les autres applications. Détail : " + msg)
            send({"id": rid, "ok": False, "error": msg, "trace": traceback.format_exc()[-4000:]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
