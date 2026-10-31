"""Processus de calcul neuronal de Doublys (moteur d'AudioLivre Studio).

Ce script est exécuté par l'interpréteur Python de l'environnement d'un moteur
(XTTS-v2, Chatterbox, Kokoro, Whisper, analyse…), installé à la demande. Il ne dépend
pas du reste de l'application : il dialogue avec elle par des lignes JSON sur stdin/stdout.

Requêtes : {"id": 1, "cmd": "ping|load|speakers|synth|convert|transcribe|separate|embed|translate|quit", ...}
Réponses : {"id": 1, "ok": true, ...} ou {"id": 1, "ok": false, "error": "..."}
Événements : {"event": "log", "msg": "..."}, {"event": "progress", "id": 1, "value": 0.5, "msg": "..."}
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
CURRENT_ID = None  # requête en cours (pour les événements de progression)


def send(obj: dict) -> None:
    PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
    PROTO.flush()


def log(msg: str) -> None:
    send({"event": "log", "msg": str(msg)})


_last_progress = [0.0]


def progress(value: float, msg: str = "", force: bool = False) -> None:
    """Avancement de la requête en cours (0..1), limité à quatre messages par seconde."""
    now = time.time()
    if not force and now - _last_progress[0] < 0.25:
        return
    _last_progress[0] = now
    send({"event": "progress", "id": CURRENT_ID, "value": max(0.0, min(1.0, float(value))), "msg": msg})


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

    def translate(self, req):
        texts = req.get("texts") or []
        for i in range(len(texts)):
            progress((i + 1) / max(1, len(texts)), f"{i + 1}/{len(texts)}", force=True)
        return {"texts": [f"[fr] {t}" for t in texts]}


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
        self.conds_cache = {}
        log(f"Chatterbox prêt sur {self.device} en {time.time() - t0:.0f} s")
        return {"sr": self.sr, **device_info(self.device)}

    def synth(self, req):
        p = req.get("params", {})
        refs = req.get("refs") or []
        exaggeration = float(p.get("exaggeration", 0.5))
        if not refs:
            raise RuntimeError("Chatterbox nécessite une voix clonée (enregistrement de référence).")
        # une analyse par voix, gardée en mémoire : les personnes alternent d'une réplique à l'autre
        # (l'expressivité est ajustée ensuite par generate(), sans nouvelle analyse)
        key = (refs[0], os.path.getmtime(refs[0]))
        if key not in self.conds_cache:
            self.model.prepare_conditionals(refs[0], exaggeration=exaggeration)
            self.conds_cache[key] = self.model.conds
        self.model.conds = self.conds_cache[key]
        set_seed(req.get("seed"))
        lang = req.get("language", "fr").lower().split("-")[0]
        text = req["text"]
        # Sur un texte très court (« dit-il. »), Chatterbox ne s'arrête parfois pas et produit jusqu'à 1000 jetons
        # (40 s d'audio, plusieurs minutes de calcul) : limite selon la durée attendue (25 jetons par seconde).
        cap = min(1000, int(25 * max(2.0, len(text) / 14.5 * 2.5)) + 25)
        t3 = self.model.t3
        original = t3.inference

        def capped(*args, **kwargs):
            kwargs["max_new_tokens"] = min(kwargs.get("max_new_tokens") or cap, cap)
            return original(*args, **kwargs)

        t3.inference = capped
        try:
            wav = self.model.generate(
                text, language_id=lang, exaggeration=exaggeration,
                cfg_weight=float(p.get("cfg_weight", 0.5)), temperature=float(p.get("temperature", 0.8)),
            )
        finally:
            del t3.inference
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
    """Conversion de voix : transforme un enregistrement pour lui donner le timbre de la voix clonée.

    Le mode « rapide » utilise le décodeur distillé de Chatterbox Turbo (2 étapes de calcul au lieu de
    10 × 2), beaucoup plus rapide sur processeur ; le mode « fidèle » garde le décodeur d'origine.
    """

    def load(self, device, options):
        from chatterbox.vc import ChatterboxVC

        self.device = pick_device(device)
        self.mode = options.get("mode") or "fast"
        log("Chargement du convertisseur de voix (le premier lancement télécharge environ 1 Go)…")
        t0 = time.time()
        self.model = None
        if self.mode == "fast":
            try:
                self.model = self._load_turbo(ChatterboxVC)
            except Exception as exc:
                log(f"Décodeur rapide indisponible ({exc}) : décodeur standard utilisé")
                self.mode = "best"
        if self.model is None:
            self.model = ChatterboxVC.from_pretrained(self.device)
        self.sr = int(self.model.sr)
        self.ref_cache = {}
        log(f"Convertisseur ({'rapide' if self.mode == 'fast' else 'fidèle'}) prêt sur {self.device} "
            f"en {time.time() - t0:.0f} s")
        return {"sr": self.sr, "mode": self.mode, **device_info(self.device)}

    def _load_turbo(self, vc_cls):
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file
        from chatterbox.models.s3gen import S3Gen

        path = hf_hub_download(repo_id="ResembleAI/chatterbox-turbo", filename="s3gen_meanflow.safetensors")
        s3gen = S3Gen(meanflow=True)
        s3gen.load_state_dict(load_file(path), strict=True)
        s3gen.to(self.device).eval()
        return vc_cls(s3gen, self.device)

    def convert(self, req):
        import librosa
        import torch
        from chatterbox.models.s3tokenizer import S3_SR

        refs = req.get("refs") or []
        if not refs:
            raise RuntimeError("Aucun enregistrement de référence pour la conversion.")
        key = (refs[0], os.path.getmtime(refs[0]))
        if key not in self.ref_cache:  # une analyse par voix cible, gardée en mémoire
            self.model.set_target_voice(refs[0])
            self.ref_cache[key] = self.model.ref_dict
        self.model.ref_dict = self.ref_cache[key]
        m = self.model
        t0 = time.time()
        with torch.inference_mode():
            audio_16, _ = librosa.load(req["source"], sr=S3_SR)
            audio_16 = torch.from_numpy(audio_16).float().to(m.device)[None, ]
            tokens, _ = m.s3gen.tokenizer(audio_16)
            t1 = time.time()
            mels = m.s3gen.flow_inference(tokens, ref_dict=m.ref_dict, finalize=True)
            t2 = time.time()
            wav, _ = m.s3gen.hift_inference(mels.to(dtype=m.s3gen.dtype))
            wav[:, :len(m.s3gen.trim_fade)] *= m.s3gen.trim_fade
            wav = wav.squeeze(0).detach().cpu().numpy()
            wav = m.watermarker.apply_watermark(wav, sample_rate=self.sr)
        t3 = time.time()
        log(f"Conversion : analyse {t1 - t0:.1f} s, timbre {t2 - t1:.1f} s, son {t3 - t2:.1f} s")
        return {"duration": write_wav(req["out"], to_numpy(wav), self.sr)}


class RVCBackend(Backend):
    """Conversion RVC : modèle de voix .pth (+ index .index facultatif) appliqué à une voix lue par Microsoft.

    Code d'inférence du projet RVC (licence MIT) ; l'analyseur ContentVec est chargé avec transformers pour
    éviter fairseq, qui ne s'installe pas sous Windows sans compilateur.
    """

    CONTENTVEC = "lengyue233/content-vec-best"
    RMVPE = ("lj1995/VoiceConversionWebUI", "rmvpe.pt")

    def load(self, device, options):
        from torch import nn
        from transformers import HubertModel

        self.device = pick_device(device)
        log("Chargement de l'analyseur de voix RVC (le premier lancement télécharge environ 0,6 Go)…")
        t0 = time.time()

        class ContentVec(HubertModel):
            def __init__(self, config):
                super().__init__(config)
                self.final_proj = nn.Linear(config.hidden_size, config.classifier_proj_size)

        self.hubert = ContentVec.from_pretrained(self.CONTENTVEC).to(self.device).float().eval()
        self.rmvpe = None
        try:
            from huggingface_hub import hf_hub_download
            from rvc.lib.rmvpe import RMVPE

            self.rmvpe = RMVPE(hf_hub_download(*self.RMVPE), is_half=False, device=self.device)
        except Exception as exc:
            log(f"Détection de hauteur RMVPE indisponible ({exc}) : méthode simple utilisée")
        self.cur_key = None
        self.cur = None
        log(f"RVC prêt sur {self.device} en {time.time() - t0:.0f} s")
        return {"sr": 0, **device_info(self.device)}

    def _model(self, model_path, index_path):
        import torch
        from rvc.lib.infer_pack.models import (SynthesizerTrnMs256NSFsid, SynthesizerTrnMs256NSFsid_nono,
                                               SynthesizerTrnMs768NSFsid, SynthesizerTrnMs768NSFsid_nono)

        has_index = bool(index_path) and os.path.exists(index_path)
        key = (model_path, os.path.getmtime(model_path), index_path if has_index else "",
               os.path.getmtime(index_path) if has_index else 0)
        if key == self.cur_key:
            return self.cur
        try:
            # weights_only : un .pth est un fichier « pickle » ; ce mode refuse tout code caché dans le fichier
            cpt = torch.load(model_path, map_location="cpu", weights_only=True)
        except Exception as exc:
            raise RuntimeError("Ce fichier .pth ne peut pas être ouvert en toute sécurité : ce n'est pas un "
                               f"modèle RVC standard ({str(exc)[:200]}).") from None
        if not isinstance(cpt, dict) or "weight" not in cpt or "config" not in cpt:
            raise RuntimeError("Ce fichier .pth n'est pas un modèle de voix RVC utilisable (il manque « weight » "
                               "ou « config »). S'il s'agit d'un fichier d'entraînement (G_….pth, D_….pth), "
                               "utilisez le modèle final exporté.")
        vocoder = cpt.get("vocoder") or "HiFi-GAN"
        if vocoder != "HiFi-GAN":
            raise RuntimeError(f"Ce modèle utilise le vocodeur « {vocoder} », qui n'est pas encore pris en charge.")
        config = list(cpt["config"])
        sr = config[-1]
        sr = {"32k": 32000, "40k": 40000, "48k": 48000}.get(sr, sr) if isinstance(sr, str) else int(sr)
        config[-3] = cpt["weight"]["emb_g.weight"].shape[0]
        if_f0 = int(cpt.get("f0", 1))
        version = str(cpt.get("version", "v1"))
        cls = {("v1", 1): SynthesizerTrnMs256NSFsid, ("v1", 0): SynthesizerTrnMs256NSFsid_nono,
               ("v2", 1): SynthesizerTrnMs768NSFsid, ("v2", 0): SynthesizerTrnMs768NSFsid_nono
               }.get((version, if_f0), SynthesizerTrnMs256NSFsid)
        net = cls(*config, is_half=False)
        del net.enc_q
        net.load_state_dict(cpt["weight"], strict=False)
        net = net.float().eval().to(self.device)
        index = big = None
        if has_index:
            try:
                import faiss

                index = faiss.read_index(index_path)
                big = index.reconstruct_n(0, index.ntotal)
            except Exception as exc:
                log(f"Index ignoré ({exc})")
        log(f"Modèle RVC {version} chargé ({sr // 1000} kHz{', avec index' if index is not None else ''})")
        self.cur_key = key
        self.cur = {"net": net, "sr": int(sr), "f0": if_f0, "version": version, "index": index, "big": big}
        return self.cur

    def _f0(self, x, p_len, transpose):
        import numpy as np

        f0_min, f0_max = 50, 1100
        mel_min, mel_max = 1127 * np.log(1 + f0_min / 700), 1127 * np.log(1 + f0_max / 700)
        if self.rmvpe is not None:
            f0 = self.rmvpe.infer_from_audio(x, thred=0.03)
        else:
            import parselmouth

            f0 = parselmouth.Sound(x, 16000).to_pitch_ac(time_step=0.01, voicing_threshold=0.6, pitch_floor=f0_min,
                                                          pitch_ceiling=f0_max).selected_array["frequency"]
            pad = (p_len - len(f0) + 1) // 2
            if pad > 0 or p_len - len(f0) - pad > 0:
                f0 = np.pad(f0, [[pad, p_len - len(f0) - pad]], mode="constant")
        f0 = f0 * pow(2, transpose / 12)
        f0bak = f0.copy()
        f0_mel = 1127 * np.log(1 + f0 / 700)
        f0_mel[f0_mel > 0] = (f0_mel[f0_mel > 0] - mel_min) * 254 / (mel_max - mel_min) + 1
        f0_mel[f0_mel <= 1] = 1
        f0_mel[f0_mel > 255] = 255
        return np.rint(f0_mel).astype(np.int32), f0bak

    def _vc(self, m, sid, audio0, pitch, pitchf, index_rate, protect):
        import numpy as np
        import torch
        import torch.nn.functional as F

        feats = torch.from_numpy(np.ascontiguousarray(audio0, dtype=np.float32)).view(1, -1).to(self.device)
        with torch.no_grad():
            if m["version"] == "v1":
                feats = self.hubert.final_proj(self.hubert(feats, output_hidden_states=True).hidden_states[9])
            else:
                feats = self.hubert(feats).last_hidden_state
        hasp = pitch is not None and pitchf is not None
        feats0 = feats.clone() if protect < 0.5 and hasp else None
        if m["index"] is not None and index_rate > 0:
            npy = feats[0].cpu().numpy().astype("float32")
            score, ix = m["index"].search(npy, k=8)
            weight = np.square(1 / np.maximum(score, 1e-12))
            weight /= weight.sum(axis=1, keepdims=True)
            npy = np.sum(m["big"][ix] * np.expand_dims(weight, axis=2), axis=1)
            feats = torch.from_numpy(npy).unsqueeze(0).to(self.device) * index_rate + (1 - index_rate) * feats
        feats = F.interpolate(feats.permute(0, 2, 1), scale_factor=2).permute(0, 2, 1)
        if feats0 is not None:
            feats0 = F.interpolate(feats0.permute(0, 2, 1), scale_factor=2).permute(0, 2, 1)
        p_len = audio0.shape[0] // 160
        if feats.shape[1] < p_len:
            p_len = feats.shape[1]
            if hasp:
                pitch, pitchf = pitch[:, :p_len], pitchf[:, :p_len]
        if feats0 is not None:
            pitchff = pitchf.clone()
            pitchff[pitchf > 0] = 1
            pitchff[pitchf < 1] = protect
            pitchff = pitchff.unsqueeze(-1)
            feats = (feats * pitchff + feats0 * (1 - pitchff)).to(feats0.dtype)
        lengths = torch.tensor([p_len], device=self.device).long()
        with torch.no_grad():
            args = (feats, lengths, pitch, pitchf, sid) if hasp else (feats, lengths, sid)
            return m["net"].infer(*args)[0][0, 0].data.cpu().float().numpy()

    def _pipeline(self, m, audio, transpose, index_rate, protect, rms_mix):
        import numpy as np
        import torch
        from scipy import signal

        sr, window = 16000, 160
        t_pad, t_pad_tgt = sr * 1, m["sr"] * 1  # réglages RVC sans carte graphique (x_pad=1…)
        t_pad2, t_query, t_center, t_max = t_pad * 2, sr * 6, sr * 38, sr * 41
        bh, ah = signal.butter(N=5, Wn=48, btype="high", fs=16000)
        audio = signal.filtfilt(bh, ah, audio)
        audio_pad = np.pad(audio, (window // 2, window // 2), mode="reflect")
        opt_ts = []
        if audio_pad.shape[0] > t_max:
            audio_sum = np.zeros_like(audio)
            for i in range(window):
                audio_sum += np.abs(audio_pad[i:i - window])
            for t in range(t_center, audio.shape[0], t_center):
                seg = audio_sum[t - t_query:t + t_query]
                opt_ts.append(t - t_query + int(np.where(seg == seg.min())[0][0]))
        audio_pad = np.pad(audio, (t_pad, t_pad), mode="reflect")
        p_len = audio_pad.shape[0] // window
        sid = torch.tensor([0], device=self.device).long()
        pitch = pitchf = None
        if m["f0"]:
            coarse, fine = self._f0(audio_pad, p_len, transpose)
            pitch = torch.tensor(coarse[:p_len], device=self.device).unsqueeze(0).long()
            pitchf = torch.tensor(fine[:p_len].astype(np.float32), device=self.device).unsqueeze(0).float()
        out = []
        s, t = 0, None
        for t in opt_ts:
            t = t // window * window
            sl = slice(s // window, (t + t_pad2) // window)
            out.append(self._vc(m, sid, audio_pad[s:t + t_pad2 + window],
                                pitch[:, sl] if pitch is not None else None,
                                pitchf[:, sl] if pitchf is not None else None,
                                index_rate, protect)[t_pad_tgt:-t_pad_tgt])
            s = t
        start = t // window if t is not None else 0
        out.append(self._vc(m, sid, audio_pad[t:] if t is not None else audio_pad,
                            pitch[:, start:] if pitch is not None else None,
                            pitchf[:, start:] if pitchf is not None else None,
                            index_rate, protect)[t_pad_tgt:-t_pad_tgt])
        audio_opt = np.concatenate(out)
        if rms_mix != 1:
            audio_opt = self._change_rms(audio, audio_opt, m["sr"], rms_mix)
        return audio_opt

    @staticmethod
    def _change_rms(src, out, out_sr, rate):
        import librosa
        import torch
        import torch.nn.functional as F

        rms1 = librosa.feature.rms(y=src, frame_length=16000 // 2 * 2, hop_length=16000 // 2)
        rms2 = librosa.feature.rms(y=out, frame_length=out_sr // 2 * 2, hop_length=out_sr // 2)
        rms1 = F.interpolate(torch.from_numpy(rms1).unsqueeze(0), size=out.shape[0], mode="linear").squeeze()
        rms2 = F.interpolate(torch.from_numpy(rms2).unsqueeze(0), size=out.shape[0], mode="linear").squeeze()
        rms2 = torch.max(rms2, torch.zeros_like(rms2) + 1e-6)
        return out * (torch.pow(rms1, torch.tensor(1 - rate)) * torch.pow(rms2, torch.tensor(rate - 1))).numpy()

    def convert(self, req):
        import librosa
        import numpy as np

        m = self._model(req["model"], req.get("index"))
        audio, _ = librosa.load(req["source"], sr=16000, mono=True)
        peak = float(np.abs(audio).max()) / 0.95 if audio.size else 0.0
        if peak > 1:
            audio = audio / peak
        t0 = time.time()
        out = self._pipeline(m, audio.astype(np.float32), float(req.get("pitch", 0)),
                             float(req.get("index_rate", 0.75)), float(req.get("protect", 0.33)),
                             float(req.get("rms_mix", 0.25)))
        log(f"Conversion RVC : {len(audio) / 16000:.1f} s d'audio en {time.time() - t0:.1f} s")
        return {"duration": write_wav(req["out"], out, m["sr"])}


class WhisperBackend(Backend):
    """Reconnaissance vocale (relecture automatique des passages produits)."""

    def load(self, device, options):
        return self._load(options.get("model") or "base", options.get("model_dir"))

    def _load(self, size, model_dir=None):
        from faster_whisper import WhisperModel

        log(f"Chargement de Whisper « {size} » (le premier lancement télécharge le modèle)…")
        self.model_dir = model_dir or getattr(self, "model_dir", None)
        threads = max(1, min(8, (os.cpu_count() or 4)))
        self.model = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=threads,
                                  download_root=self.model_dir or None)
        self.size = size
        return {"sr": 16000, "device": "cpu", "model": size}

    def transcribe(self, req):
        lang = (req.get("language") or "fr").split("-")[0]
        segments, _info = self.model.transcribe(req["path"], language=lang, beam_size=1,
                                                condition_on_previous_text=False, vad_filter=False)
        return {"text": " ".join(seg.text.strip() for seg in segments).strip()}

    def vad(self, req):
        return vad_regions(req)

    def transcribe_words(self, req):
        """Transcription avec la position de chaque mot, sur [start, end] du fichier (doublage, par morceaux)."""
        from faster_whisper import BatchedInferencePipeline, decode_audio

        size = req.get("model") or self.size
        if size != self.size:
            self._load(size)
        lang = req.get("language")
        lang = lang.split("-")[0] if lang and lang != "auto" else None  # None : détection automatique
        a = int(float(req.get("start", 0.0)) * 16000)
        b = int(float(req["end"]) * 16000) if req.get("end") else None
        try:  # WAV 16 kHz : seul le morceau demandé est lu (vidéos longues)
            import soundfile as sf

            if sf.info(req["path"]).samplerate != 16000:
                raise ValueError("fréquence")
            audio, _ = sf.read(req["path"], start=a, stop=b, dtype="float32", always_2d=True)
            audio = audio.mean(axis=1)
        except Exception:
            audio = decode_audio(req["path"], sampling_rate=16000)[a:b]
        offset = a / 16000
        total = len(audio) / 16000
        pipe = BatchedInferencePipeline(model=self.model)
        # seuil de parole plus bas que celui par défaut (0,5) : voix sous la musique, cris courts, voix filtrées
        vad = {"threshold": float(req.get("vad_threshold", 0.35)), "min_speech_duration_ms": 150,
               "min_silence_duration_ms": 500, "speech_pad_ms": 200}
        segments, info = pipe.transcribe(audio, language=lang, beam_size=int(req.get("beam_size", 1)),
                                         batch_size=int(req.get("batch_size", 8)), word_timestamps=True,
                                         vad_filter=True, vad_parameters=vad, condition_on_previous_text=False)
        words, segs, dropped = [], [], []
        for seg in segments:
            why = is_hallucination(seg)
            if why:
                dropped.append([round(seg.start + offset, 3), round(seg.end + offset, 3), (seg.text or "").strip(),
                                why])
                continue
            segs.append([round(seg.start + offset, 3), round(seg.end + offset, 3), seg.text.strip()])
            for w in seg.words or []:
                words.append([round(w.start + offset, 3), round(w.end + offset, 3), w.word, round(float(w.probability), 3)])
            if total:
                progress(seg.end / total, f"{len(words)} mots reconnus")
        if dropped:
            log(f"{len(dropped)} passage(s) incompréhensible(s) ou répétitif(s) écarté(s) (listés dans Contrôle)")
        return {"words": words, "segments": segs, "duration": total, "language": info.language,
                "language_probability": float(getattr(info, "language_probability", 0.0) or 0.0),
                "dropped": dropped}

    def detect_language(self, req):
        """Langue parlée, votée sur plusieurs extraits [[début, fin], …] d'un WAV 16 kHz."""
        import numpy as np
        import soundfile as sf

        votes: dict[str, float] = {}
        details = []
        for a, b in req.get("spans") or []:
            audio, _ = sf.read(req["path"], start=int(float(a) * 16000), stop=int(float(b) * 16000),
                               dtype="float32", always_2d=True)
            audio = np.ascontiguousarray(audio.mean(axis=1))
            if len(audio) < 16000:
                continue
            try:
                lang, prob, _all = self.model.detect_language(audio)
            except (AttributeError, TypeError):  # faster-whisper plus ancien : détection par la transcription
                _segs, info = self.model.transcribe(audio[:16000 * 30], beam_size=1)
                lang, prob = info.language, info.language_probability
            votes[lang] = votes.get(lang, 0.0) + float(prob)
            details.append([round(float(a), 2), lang, round(float(prob), 3)])
        if not votes:
            return {"language": "", "probability": 0.0, "details": details}
        best = max(votes, key=votes.get)
        return {"language": best, "probability": round(votes[best] / max(1, len(details)), 3), "details": details}


def is_hallucination(seg) -> str:
    """Passage inventé par Whisper : texte qui tourne en boucle, ou bruit pris pour de la parole. Renvoie la
    raison (vide si le passage est gardé)."""
    import re
    import zlib

    text = (seg.text or "").strip()
    if not text:
        return "texte vide"
    ratio = getattr(seg, "compression_ratio", None)
    if ratio is None and len(text) > 20:
        raw = text.encode("utf-8")
        ratio = len(raw) / max(1, len(zlib.compress(raw)))
    if ratio is not None and ratio > 2.4:
        return "texte répétitif"
    # même groupe de mots répété en boucle (un cri court comme « Go! Go! Go! » reste permis)
    sep = r"[\s、,。.!！?？]*"
    if re.search(rf"(.{{5,30}}?)(?:{sep}\1){{3,}}", text) or re.search(rf"(.{{1,4}}?)(?:{sep}\1){{7,}}", text):
        return "texte en boucle"
    if getattr(seg, "no_speech_prob", 0.0) > 0.9 and getattr(seg, "avg_logprob", 0.0) < -1.0:
        return "bruit pris pour de la parole"
    return ""


def vad_regions(req):
    """Passages de parole [[début, fin], …] d'un WAV 16 kHz (détecteur Silero de faster-whisper)."""
    from faster_whisper import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio = decode_audio(req["path"], sampling_rate=16000)
    opts = VadOptions(threshold=float(req.get("threshold", 0.5)),
                      min_speech_duration_ms=int(req.get("min_speech_ms", 250)),
                      min_silence_duration_ms=int(req.get("min_silence_ms", 600)),
                      speech_pad_ms=int(req.get("pad_ms", 200)))
    ts = get_speech_timestamps(audio, opts)
    return {"speech": [[round(t["start"] / 16000, 2), round(t["end"] / 16000, 2)] for t in ts],
            "duration": len(audio) / 16000}


def fix_unknown(text: str, tok) -> str:
    """Le vocabulaire d'Opus-MT n'a pas de « Ç » : le modèle écrit un jeton inconnu suivi de « a » (« Ça va »)."""
    import re

    unk = tok.unk_token or "<unk>"
    text = re.sub(re.escape(unk) + r"\s*(?=a\b|a[ -'’])", "Ç", text)
    text = re.sub(re.escape(unk) + r"\s*(?=A\b)", "Ç", text)
    for t in {unk, tok.pad_token, tok.eos_token} - {None}:
        text = text.replace(t, "")
    return re.sub(r"\s+", " ", text).strip()


class AnalysisBackend(Backend):
    """Environnement « analyse » du doublage : séparation des voix (Demucs), empreintes vocales (ECAPA,
    speechbrain) et traduction locale (Opus-MT, transformers). Chaque modèle est chargé à sa première utilisation."""

    ECAPA = "speechbrain/spkrec-ecapa-voxceleb"

    def load(self, device, options):
        import torch

        self.device = pick_device(device)
        self.model_dir = options.get("model_dir") or os.getcwd()
        self.demucs = None
        self.ecapa = None
        self.mt = {}
        torch.set_grad_enabled(False)
        return {"sr": 0, **device_info(self.device)}

    # -- séparation ---------------------------------------------------------------------
    def _demucs(self, name):
        if self.demucs is None or self.demucs[0] != name:
            from demucs.pretrained import get_model

            log(f"Chargement de Demucs « {name} » (le premier lancement télécharge environ 80 Mo)…")
            model = get_model(name)
            model.eval()
            self.demucs = (name, model)
        return self.demucs[1]

    def separate(self, req):
        """Sépare la voix du reste par blocs (RAM stable) : voix.wav et fond.wav (= mélange moins la voix).

        Les blocs sans parole (``speech`` : [[début, fin], …]) ne passent pas par Demucs. Avec ``resume``, le
        travail reprend au dernier bloc complet des fichiers déjà écrits."""
        import numpy as np
        import soundfile as sf
        import torch
        from demucs.apply import apply_model

        model = self._demucs(req.get("model") or "htdemucs")
        src = req["path"]
        info = sf.info(src)
        sr = int(info.samplerate)
        if sr != model.samplerate:
            raise RuntimeError(f"Fréquence inattendue ({sr} Hz au lieu de {model.samplerate} Hz).")
        total = int(info.frames)
        block = int(float(req.get("block", 30.0)) * sr)
        ctx = int(float(req.get("context", 2.0)) * sr)
        speech = req.get("speech")
        vi = list(model.sources).index("vocals")
        start = 0
        vpath, bpath = req["voice_out"], req["background_out"]
        if req.get("resume") and os.path.exists(vpath) and os.path.exists(bpath):
            try:
                done = min(sf.info(vpath).frames, sf.info(bpath).frames)
                start = (done // block) * block
            except Exception:
                start = 0
        mode = "r+" if start > 0 else "w"
        if start:
            log(f"Reprise de la séparation à {start / sr:.0f} s")
        t0 = time.time()
        computed = 0
        fv = sf.SoundFile(vpath, mode, sr, 2, "PCM_16") if mode == "w" else sf.SoundFile(vpath, mode)
        fb = sf.SoundFile(bpath, mode, sr, 2, "PCM_16") if mode == "w" else sf.SoundFile(bpath, mode)
        try:
            fv.seek(start)
            fb.seek(start)
            pos = start
            while pos < total:
                n = min(block, total - pos)
                a, b = max(0, pos - ctx), min(total, pos + block + ctx)
                chunk, _ = sf.read(src, start=a, stop=b, dtype="float32", always_2d=True)
                if chunk.shape[1] == 1:
                    chunk = np.repeat(chunk, 2, axis=1)
                chunk = chunk[:, :2]
                mix = chunk[pos - a:pos - a + n]
                has_speech = speech is None or any(s0 < (pos + n) / sr + 0.5 and s1 > pos / sr - 0.5
                                                   for s0, s1 in speech)
                if has_speech:
                    x = torch.from_numpy(np.ascontiguousarray(chunk.T))
                    ref = x.mean(0)
                    mean, std = ref.mean(), ref.std() + 1e-8
                    out = apply_model(model, ((x - mean) / std)[None], device=self.device, split=True,
                                      overlap=float(req.get("overlap", 0.1)), progress=False)[0]
                    voice = (out[vi] * std + mean).cpu().numpy().T
                    keep = voice[pos - a:pos - a + n]
                    computed += n
                else:  # pas de parole : tout le son va dans le fond
                    keep = np.zeros_like(mix)
                fv.write(np.clip(keep, -1, 1))
                fb.write(np.clip(mix - keep, -1, 1))
                fv.flush()
                fb.flush()
                pos += n
                elapsed = time.time() - t0
                progress(pos / total, f"{pos / sr / 60:.1f} min sur {total / sr / 60:.1f} min "
                         f"({elapsed / 60:.1f} min de calcul)", True)
        finally:
            fv.close()
            fb.close()
        return {"duration": total / sr, "seconds": time.time() - t0, "separated": computed / sr}

    # -- empreintes vocales -------------------------------------------------------------
    def _ecapa(self):
        if self.ecapa is None:
            from speechbrain.inference.speaker import EncoderClassifier
            from speechbrain.utils.fetching import LocalStrategy

            log("Chargement du modèle d'empreintes vocales ECAPA (≈ 80 Mo au premier lancement)…")
            self.ecapa = EncoderClassifier.from_hparams(
                source=self.ECAPA, savedir=os.path.join(self.model_dir, "spkrec-ecapa-voxceleb"),
                run_opts={"device": self.device},
                # Windows : pas de liens symboliques (droits administrateur), on copie les fichiers
                local_strategy=LocalStrategy.COPY)
        return self.ecapa

    def embed(self, req):
        """Empreinte (192 valeurs, normée) de chaque extrait [début, fin] d'un WAV 16 kHz mono."""
        import numpy as np
        import soundfile as sf
        import torch

        model = self._ecapa()
        info = sf.info(req["path"])
        sr = int(info.samplerate)
        segs = req.get("segments") or []
        out = []
        for i, (start, end) in enumerate(segs):
            a = max(0, int(float(start) * sr))
            b = min(int(info.frames), int(min(float(end), float(start) + 12.0) * sr))
            data, _ = sf.read(req["path"], start=a, stop=max(a + 1, b), dtype="float32", always_2d=True)
            x = data.mean(axis=1)
            if len(x) < int(0.4 * sr):  # trop court : on répète l'extrait
                x = np.tile(x, int(np.ceil(0.4 * sr / max(1, len(x)))))
            emb = model.encode_batch(torch.from_numpy(np.ascontiguousarray(x))[None]).reshape(-1).cpu().numpy()
            emb = emb / (np.linalg.norm(emb) + 1e-9)
            out.append([round(float(v), 5) for v in emb])
            progress((i + 1) / max(1, len(segs)), f"{i + 1} répliques sur {len(segs)}")
        return {"embeddings": out}

    # -- traduction ---------------------------------------------------------------------
    def _mt(self, name):
        if name not in self.mt:
            from transformers import MarianMTModel, MarianTokenizer

            log(f"Chargement du traducteur « {name} » (le premier lancement télécharge le modèle)…")
            tok = MarianTokenizer.from_pretrained(name)
            model = MarianMTModel.from_pretrained(name).to(self.device).eval()
            self.mt = {name: (tok, model)}  # un seul modèle en mémoire
        return self.mt[name]

    def translate(self, req):
        """Traduit une liste de phrases ; avec ``n_best`` > 1, renvoie aussi les variantes (meilleure d'abord)."""
        import torch

        name = req.get("model") or "Helsinki-NLP/opus-mt-tc-big-en-fr"
        tok, model = self._mt(name)
        texts = [str(t or "") for t in req.get("texts") or []]
        batch = max(1, int(req.get("batch", 16)))
        n_best = max(1, int(req.get("n_best", 1)))
        beams = max(n_best, int(req.get("beams", 4)))
        out: list = []
        for i in range(0, len(texts), batch):
            part = texts[i:i + batch]
            todo = [t for t in part if t.strip()]
            res = []
            if todo:
                enc = tok(todo, return_tensors="pt", padding=True, truncation=True, max_length=512).to(self.device)
                with torch.inference_mode():
                    gen = model.generate(**enc, num_beams=beams, num_return_sequences=n_best, max_new_tokens=400)
                dec = [fix_unknown(d, tok) for d in tok.batch_decode(gen, skip_special_tokens=False)]
                res = [dec[k * n_best:(k + 1) * n_best] for k in range(len(todo))]
            it = iter(res)
            for t in part:
                cands = next(it) if t.strip() else [""]
                out.append(cands if n_best > 1 else cands[0])
            done = min(len(texts), i + batch)
            progress(done / max(1, len(texts)), f"{done} phrases sur {len(texts)}")
        return {"texts": out}



class OcrBackend(Backend):
    """Lecture des sous-titres incrustés : RapidOCR (modèles PP-OCR en ONNX), reconnaissance seule sur des lignes
    déjà découpées par l'application (beaucoup plus rapide que la détection complète)."""

    def load(self, device, options):
        from rapidocr_onnxruntime import RapidOCR

        self.engine = RapidOCR()
        return {"device": "cpu"}

    def ocr_lines(self, req):
        """{"files": [chemin .npz, …]} : chaque tableau (image grise d'une ligne) → [texte, confiance]."""
        import numpy as np

        out = {}
        files = list(req.get("files") or [])
        done = 0
        total = sum(1 for _ in files) or 1
        for k, f in enumerate(files):
            with np.load(f) as z:
                for name in z.files:
                    img = z[name]
                    if img.ndim == 2:
                        img = np.repeat(img[:, :, None], 3, axis=2)
                    res, _ = self.engine(np.ascontiguousarray(img), use_det=False, use_cls=False, use_rec=True)
                    text, conf = ("", 0.0)
                    if res:
                        text, conf = str(res[0][0]), float(res[0][1])
                    out[name] = [text, round(conf, 3)]
                    done += 1
            progress((k + 1) / total, f"{done} lignes lues")
        return {"texts": out}


BACKENDS = {"dummy": DummyBackend, "xtts": XttsBackend, "chatterbox": ChatterboxBackend, "kokoro": KokoroBackend,
            "chatterbox_vc": ChatterboxVCBackend, "whisper": WhisperBackend, "rvc": RVCBackend,
            "analysis": AnalysisBackend, "ocr": OcrBackend}
COMMANDS = ("convert", "transcribe", "transcribe_words", "vad", "detect_language", "separate", "embed", "translate",
            "ocr_lines")


# =======================================================================================
# Boucle principale
# =======================================================================================
def main() -> int:
    global PROTO, CURRENT_ID
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
        CURRENT_ID = rid
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
            elif cmd in COMMANDS:
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
