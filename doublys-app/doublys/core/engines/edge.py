"""Voix neuronales Microsoft Edge (gratuites, en ligne, excellente qualité)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from ... import paths
from ..models import VoiceProfile
from .base import (READY, UNAVAILABLE, BuiltinVoice, EngineError, EngineInfo, ParamSpec, ServiceBlocked, TTSEngine,
                   words_path)

log = logging.getLogger(__name__)

# Liste de secours si la liste en ligne n'est pas accessible
FALLBACK_VOICES = [
    ("fr-FR-DeniseNeural", "Denise", "F"), ("fr-FR-HenriNeural", "Henri", "M"),
    ("fr-FR-EloiseNeural", "Eloise", "F"), ("fr-FR-VivienneMultilingualNeural", "Vivienne (multilingue)", "F"),
    ("fr-FR-RemyMultilingualNeural", "Rémy (multilingue)", "M"), ("fr-CA-SylvieNeural", "Sylvie (Canada)", "F"),
    ("fr-CA-JeanNeural", "Jean (Canada)", "M"), ("fr-CA-AntoineNeural", "Antoine (Canada)", "M"),
    ("fr-CA-ThierryNeural", "Thierry (Canada)", "M"), ("fr-BE-CharlineNeural", "Charline (Belgique)", "F"),
    ("fr-BE-GerardNeural", "Gérard (Belgique)", "M"), ("fr-CH-ArianeNeural", "Ariane (Suisse)", "F"),
    ("fr-CH-FabriceNeural", "Fabrice (Suisse)", "M"), ("en-US-AriaNeural", "Aria", "F"),
    ("en-US-GuyNeural", "Guy", "M"), ("en-US-JennyNeural", "Jenny", "F"),
    ("en-US-AndrewMultilingualNeural", "Andrew (multilingual)", "M"),
    ("en-US-AvaMultilingualNeural", "Ava (multilingual)", "F"),
    ("en-US-EmmaMultilingualNeural", "Emma (multilingual)", "F"),
    ("en-US-BrianMultilingualNeural", "Brian (multilingual)", "M"),
    ("de-DE-SeraphinaMultilingualNeural", "Seraphina (multilingual)", "F"),
    ("de-DE-FlorianMultilingualNeural", "Florian (multilingual)", "M"), ("en-GB-SoniaNeural", "Sonia", "F"),
    ("en-GB-RyanNeural", "Ryan", "M"), ("es-ES-ElviraNeural", "Elvira", "F"), ("es-ES-AlvaroNeural", "Álvaro", "M"),
    ("de-DE-KatjaNeural", "Katja", "F"), ("de-DE-ConradNeural", "Conrad", "M"),
    ("it-IT-ElsaNeural", "Elsa", "F"), ("it-IT-DiegoNeural", "Diego", "M"),
]


def voice_language(short_name: str, locale: str) -> tuple[str, str]:
    """(langue, remarque) d'une voix : les voix « Multilingual » étrangères lisent aussi le français."""
    lang = locale.split("-")[0]
    if "Multilingual" in short_name and lang != "fr":
        return "multi", "lit aussi le français (léger accent possible)"
    return lang, ""


BLOCKED_MESSAGE = (
    "Le service de voix Microsoft refuse les demandes de cet ordinateur (erreur 403). Causes habituelles : "
    "trop de demandes en peu de temps (Microsoft bloque temporairement : attendez 30 à 60 minutes, puis "
    "réduisez « Requêtes simultanées » à 1 dans Paramètres → Performances) ; un VPN, un proxy ou un antivirus "
    "qui filtre Internet (désactivez-le le temps d'essayer) ; ou l'heure de l'ordinateur décalée (Paramètres "
    "Windows → Heure et langue → Synchroniser maintenant). En attendant, les voix hors ligne fonctionnent "
    "(Kokoro, XTTS-v2, voix Windows)."
)
LIMITED_MESSAGE = (
    "Le service de voix Microsoft limite temporairement les demandes (trop de demandes). Patientez 15 à 30 minutes "
    "et réduisez « Requêtes simultanées » à 1 dans Paramètres → Performances."
)


# Depuis octobre 2026, Microsoft migre le service vers api.msedgeservices.com : l'ancienne adresse répond 403
# dans certains pays (France, Espagne…). On bascule automatiquement sur la nouvelle et on s'en souvient.
_NEW_HOST = "api.msedgeservices.com/tts/cognitiveservices"
_endpoint = {"current": "legacy"}


def _endpoints():
    from edge_tts import constants

    token = constants.TRUSTED_CLIENT_TOKEN
    return {
        "legacy": (constants.WSS_URL, constants.VOICE_LIST),
        "new": (f"wss://{_NEW_HOST}/websocket/v1?Ocp-Apim-Subscription-Key={token}",
                f"https://{_NEW_HOST}/voices/list?Ocp-Apim-Subscription-Key={token}"),
    }


def use_endpoint(name: str) -> None:
    """Fait pointer edge-tts vers l'adresse choisie (« legacy » ou « new »)."""
    import edge_tts.communicate as cm
    import edge_tts.voices as vm

    wss, voices = _endpoints()[name]
    cm.WSS_URL = wss
    vm.VOICE_LIST = voices
    _endpoint["current"] = name


def _remember_endpoint() -> None:
    try:
        from ...config import settings

        settings().set("edge_endpoint", _endpoint["current"])
    except Exception:
        log.debug("Point d'accès Edge non mémorisé", exc_info=True)


def _restore_endpoint() -> None:
    if _endpoint.get("restored"):
        return
    _endpoint["restored"] = True
    try:
        from ...config import settings

        if settings().get("edge_endpoint") == "new":
            use_endpoint("new")
    except Exception:
        pass


class EdgeEngine(TTSEngine):
    info = EngineInfo(
        id="edge",
        name="Voix neuronales Microsoft",
        tagline="Gratuit · En ligne · Très naturel",
        description=(
            "Plus de 300 voix neuronales de très grande qualité (dont une quinzaine en français), "
            "gratuites, sans installation. Nécessite une connexion Internet. Ne permet pas le clonage."
        ),
        online=True,
        languages=["fr", "en", "es", "de", "it", "pt", "nl", "pl", "ja", "zh", "ar", "ru", "+"],
        license="Service en ligne Microsoft",
        max_chars=700,
        min_chars=40,
        max_workers=4,
        quality=5,
        speed=5,
        params=[
            ParamSpec("rate", "Débit", 0.5, 2.0, 1.0, 0.05, "Vitesse de lecture de cette voix"),
            ParamSpec("pitch", "Hauteur (Hz)", -50, 50, 0, 1, "Plus grave ou plus aigu", decimals=0),
        ],
        accent="#4FC3F7",
    )

    def __init__(self):
        self._voices: list[BuiltinVoice] | None = None

    def status(self):
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return UNAVAILABLE, "Module edge-tts absent"
        return READY, "Prêt (connexion Internet requise)"

    def _cache_file(self) -> Path:
        return paths.data_dir() / "edge_voices.json"

    def list_builtin_voices(self, refresh: bool = False) -> list[BuiltinVoice]:
        if self._voices is not None and not refresh:
            return self._voices
        raw = None
        cache = self._cache_file()
        if not refresh and cache.exists() and time.time() - cache.stat().st_mtime < 14 * 86400:
            try:
                raw = json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                raw = None
        if raw is None:
            try:
                import edge_tts

                _restore_endpoint()
                try:
                    raw = asyncio.run(edge_tts.list_voices())
                except Exception:
                    use_endpoint("new" if _endpoint["current"] == "legacy" else "legacy")
                    raw = asyncio.run(edge_tts.list_voices())
                cache.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                log.info("Liste des voix Edge indisponible (%s), liste intégrée utilisée", exc)
                if cache.exists():
                    try:
                        raw = json.loads(cache.read_text(encoding="utf-8"))
                    except Exception:
                        raw = None
        voices: list[BuiltinVoice] = []
        if raw:
            for v in raw:
                short = v.get("ShortName", "")
                locale = v.get("Locale", "")
                friendly = short.split("-")[-1].replace("Neural", "")
                friendly = friendly.replace("Multilingual", " (multilingue)")
                lang, note = voice_language(short, locale)
                traits = ", ".join(v.get("VoiceTag", {}).get("VoicePersonalities", []) or [])
                voices.append(BuiltinVoice(
                    id=short, name=friendly, language=lang, locale=locale,
                    gender="F" if v.get("Gender") == "Female" else "M",
                    description=" · ".join(x for x in (note, traits) if x),
                ))
        else:
            for vid, name, g in FALLBACK_VOICES:
                loc = "-".join(vid.split("-")[:2])
                lang, note = voice_language(vid, loc)
                voices.append(BuiltinVoice(id=vid, name=name.replace("multilingual", "multilingue"), language=lang,
                                           locale=loc, gender=g, description=note))
        voices.sort(key=lambda b: (b.language != "fr", b.locale, b.name))
        self._voices = voices
        return voices

    def synthesize(self, text, voice: VoiceProfile, out_path: Path, language: str, speed: float = 1.0,
                   seed: int | None = None) -> Path:
        import edge_tts

        params = self.merged_params(voice)
        rate_mult = float(params.get("rate", 1.0)) * float(speed or 1.0)
        rate = f"{int(round((rate_mult - 1.0) * 100)):+d}%"
        pitch = f"{int(round(float(params.get('pitch', 0)))):+d}Hz"
        target = Path(out_path).with_suffix(".mp3")
        voice_name = voice.engine_voice or "fr-FR-DeniseNeural"
        last_exc: Exception | None = None
        refused = 0
        _restore_endpoint()
        tried = {_endpoint["current"]}
        for attempt in range(5):
            try:
                comm = edge_tts.Communicate(text, voice_name, rate=rate, pitch=pitch, boundary="WordBoundary")
                # position de chaque mot : sert à mettre en valeur les mots marqués *ainsi*
                asyncio.run(comm.save(str(target), str(words_path(target))))
                if target.exists() and target.stat().st_size > 0:
                    _remember_endpoint()
                    return target
                raise EngineError("Aucun son reçu")
            except Exception as exc:  # erreurs réseau : on réessaie
                last_exc = exc
                status = getattr(exc, "status", None)
                if status == 403 and len(tried) < 2:
                    # l'autre adresse du service (migration de Microsoft) : essai immédiat
                    other = "new" if _endpoint["current"] == "legacy" else "legacy"
                    use_endpoint(other)
                    tried.add(other)
                    continue
                if status in (403, 429, 503):
                    # refus du service : un seul nouvel essai, espacé, puis arrêt (inutile d'insister)
                    refused += 1
                    if refused >= 2:
                        raise ServiceBlocked(BLOCKED_MESSAGE if status == 403 else LIMITED_MESSAGE) from None
                    time.sleep(10)
                    continue
                time.sleep(1.5 * (attempt + 1))
        raise EngineError(
            "Le service de voix Microsoft ne répond pas. Vérifiez votre connexion Internet. "
            f"Détail : {last_exc}"
        )
