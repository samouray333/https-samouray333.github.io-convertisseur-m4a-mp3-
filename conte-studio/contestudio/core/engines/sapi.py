"""Voix installées dans Windows (SAPI 5 et voix « OneCore » : Hortense, Julie, Paul…)."""

from __future__ import annotations

import logging
import math
import sys
import threading
from pathlib import Path

from ..models import VoiceProfile
from .base import READY, UNAVAILABLE, BuiltinVoice, EngineError, EngineInfo, ParamSpec, TTSEngine

log = logging.getLogger(__name__)

ONECORE_KEY = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"
SAFT22K16BIT_MONO = 22
SSFM_CREATE_FOR_WRITE = 3
SVSF_IS_NOT_XML = 16

LCID_LANG = {0x40C: "fr", 0xC0C: "fr", 0x80C: "fr", 0x100C: "fr", 0x409: "en", 0x809: "en", 0xC0A: "es",
             0x40A: "es", 0x407: "de", 0x410: "it", 0x416: "pt", 0x816: "pt", 0x413: "nl", 0x411: "ja", 0x804: "zh"}


class SapiEngine(TTSEngine):
    info = EngineInfo(
        id="sapi",
        name="Voix de Windows",
        tagline="Hors ligne · Instantané · Basique",
        description=(
            "Utilise les voix déjà installées dans Windows (par exemple Microsoft Hortense, Julie ou Paul). "
            "Fonctionne sans Internet ni installation, mais la qualité est moins naturelle que les voix neuronales."
        ),
        languages=["fr", "en", "+"],
        license="Inclus dans Windows",
        max_chars=900,
        max_workers=1,
        quality=2,
        speed=5,
        params=[ParamSpec("rate", "Débit", 0.5, 2.0, 1.0, 0.05, "Vitesse de lecture")],
        accent="#90A4AE",
    )

    def __init__(self):
        self._local = threading.local()
        self._voices: list[BuiltinVoice] | None = None

    def status(self):
        if not sys.platform.startswith("win"):
            return UNAVAILABLE, "Disponible uniquement sous Windows"
        try:
            import win32com.client  # noqa: F401
        except ImportError:
            return UNAVAILABLE, "Composant pywin32 absent"
        return READY, "Prêt (hors ligne)"

    def _com(self):
        if getattr(self._local, "voice", None) is None:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            self._local.voice = win32com.client.Dispatch("SAPI.SpVoice")
            self._local.tokens = {}
            self._collect_tokens(self._local)
        return self._local

    def _collect_tokens(self, local) -> None:
        import win32com.client

        tokens = {}
        try:
            coll = local.voice.GetVoices()
            for i in range(coll.Count):
                t = coll.Item(i)
                tokens[t.Id] = t
        except Exception as exc:
            log.debug("Voix SAPI : %s", exc)
        try:
            cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
            cat.SetId(ONECORE_KEY, False)
            coll = cat.EnumerateTokens()
            for i in range(coll.Count):
                t = coll.Item(i)
                tokens.setdefault(t.Id, t)
        except Exception as exc:
            log.debug("Voix OneCore : %s", exc)
        local.tokens = tokens

    def list_builtin_voices(self, refresh: bool = False) -> list[BuiltinVoice]:
        if self._voices is not None and not refresh:
            return self._voices
        voices: list[BuiltinVoice] = []
        if self.status()[0] != READY:
            self._voices = voices
            return voices
        try:
            local = self._com()
            if refresh:
                self._collect_tokens(local)
            for tid, t in local.tokens.items():
                desc = t.GetDescription()
                try:
                    lcid = int((t.GetAttribute("Language") or "0").split(";")[0], 16)
                except Exception:
                    lcid = 0
                try:
                    gender = "F" if (t.GetAttribute("Gender") or "").lower() == "female" else "M"
                except Exception:
                    gender = ""
                voices.append(BuiltinVoice(id=tid, name=desc, language=LCID_LANG.get(lcid, ""), gender=gender,
                                           description="Voix Windows"))
        except Exception as exc:
            log.warning("Impossible de lister les voix Windows : %s", exc)
        voices.sort(key=lambda v: (v.language != "fr", v.name))
        self._voices = voices
        return voices

    def synthesize(self, text, voice: VoiceProfile, out_path: Path, language: str, speed: float = 1.0,
                   seed: int | None = None) -> Path:
        import win32com.client

        local = self._com()
        params = self.merged_params(voice)
        mult = max(0.3, min(3.0, float(params.get("rate", 1.0)) * float(speed or 1.0)))
        rate = int(round(10 * math.log(mult) / math.log(3)))
        target = Path(out_path).with_suffix(".wav")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
        fmt.Type = SAFT22K16BIT_MONO
        stream.Format = fmt
        try:
            stream.Open(str(target), SSFM_CREATE_FOR_WRITE, False)
            sp = local.voice
            token = local.tokens.get(voice.engine_voice)
            if token is None and voice.engine_voice:
                self._collect_tokens(local)
                token = local.tokens.get(voice.engine_voice)
            if token is not None:
                sp.Voice = token
            sp.Rate = max(-10, min(10, rate))
            sp.Volume = 100
            sp.AudioOutputStream = stream
            sp.Speak(text, SVSF_IS_NOT_XML)
        except Exception as exc:
            raise EngineError(f"Échec de la voix Windows : {exc}") from exc
        finally:
            try:
                stream.Close()
            except Exception:
                pass
            try:
                local.voice.AudioOutputStream = None
            except Exception:
                pass
        return target
