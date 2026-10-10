"""Moteurs neuronaux exécutés dans un processus séparé (XTTS-v2, Chatterbox, Kokoro)."""

from __future__ import annotations

import collections
import itertools
import json
import logging
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from ... import paths
from ..ffmpeg import popen_kwargs
from ..models import VoiceProfile
from . import installer
from .base import NOT_INSTALLED, READY, BuiltinVoice, EngineError, EngineInfo, ParamSpec, TTSEngine

log = logging.getLogger(__name__)

LOG_LISTENERS: list[Callable[[str, str], None]] = []


def emit_log(engine_id: str, line: str) -> None:
    log.info("[%s] %s", engine_id, line)
    for cb in list(LOG_LISTENERS):
        try:
            cb(engine_id, line)
        except Exception:
            pass


class WorkerDied(EngineError):
    pass


class WorkerProcess:
    """Processus Python du moteur, piloté par des messages JSON."""

    def __init__(self, engine_id: str, worker_name: str, python: Path, env: dict, cwd: Path | None = None):
        self.engine_id = engine_id
        self.cwd = cwd or installer.engine_root(engine_id)
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.worker_name = worker_name
        self.python = python
        self.env = env
        self.proc: subprocess.Popen | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, queue.Queue] = {}
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._ready = threading.Event()
        self.stderr_tail: collections.deque[str] = collections.deque(maxlen=60)

    def start(self, timeout: float = 180.0) -> None:
        script = paths.worker_script()
        cmd = [str(self.python), "-u", str(script), "--engine", self.worker_name]
        log.info("Démarrage du moteur %s : %s", self.engine_id, cmd)
        self._ready.clear()
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", env=self.env, cwd=str(self.cwd),
            bufsize=1, **popen_kwargs(),
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        deadline = time.time() + timeout
        while not self._ready.wait(0.2):
            if self.proc.poll() is not None:
                raise WorkerDied(self._death_message())
            if time.time() > deadline:
                self.stop()
                raise EngineError("Le moteur ne démarre pas (délai dépassé).")

    def _death_message(self) -> str:
        tail = "\n".join(list(self.stderr_tail)[-12:])
        return f"Le moteur « {self.engine_id} » s'est arrêté de manière inattendue.\n{tail}"

    def _read_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                emit_log(self.engine_id, line)
                continue
            if msg.get("event") == "ready":
                self._ready.set()
            elif msg.get("event") == "log":
                emit_log(self.engine_id, msg.get("msg", ""))
            elif "id" in msg:
                with self._lock:
                    q = self._pending.get(msg["id"])
                if q is not None:
                    q.put(msg)
        # le processus est terminé : on réveille les attentes
        with self._lock:
            for q in self._pending.values():
                q.put({"ok": False, "error": self._death_message(), "dead": True})

    def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        last_emit = 0.0
        for line in self.proc.stderr:
            line = line.rstrip()
            if not line:
                continue
            self.stderr_tail.append(line)
            # les barres de progression (téléchargement du modèle) sont limitées à une ligne/s
            if "%|" in line or "it/s" in line or "B/s" in line:
                if time.time() - last_emit < 1.0:
                    continue
                last_emit = time.time()
            if "warn" in line.lower() and "futurewarning" in line.lower():
                continue
            emit_log(self.engine_id, line)

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def request(self, cmd: str, timeout: float = 900.0, **payload) -> dict:
        if not self.alive():
            raise WorkerDied(self._death_message())
        rid = next(self._ids)
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._pending[rid] = q
        try:
            with self._send_lock:
                assert self.proc and self.proc.stdin
                self.proc.stdin.write(json.dumps({"id": rid, "cmd": cmd, **payload}, ensure_ascii=False) + "\n")
                self.proc.stdin.flush()
            try:
                msg = q.get(timeout=timeout)
            except queue.Empty as exc:
                raise EngineError(f"Le moteur ne répond pas (délai de {int(timeout)} s dépassé).") from exc
        except (BrokenPipeError, OSError) as exc:
            raise WorkerDied(self._death_message()) from exc
        finally:
            with self._lock:
                self._pending.pop(rid, None)
        if msg.get("dead"):
            raise WorkerDied(msg.get("error", "Moteur arrêté"))
        if not msg.get("ok"):
            if msg.get("trace"):
                log.error("Erreur du moteur %s :\n%s", self.engine_id, msg["trace"])
            raise EngineError(msg.get("error", "Erreur inconnue du moteur"))
        return msg

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            if self.alive():
                try:
                    with self._send_lock:
                        assert self.proc.stdin
                        self.proc.stdin.write(json.dumps({"id": 0, "cmd": "quit"}) + "\n")
                        self.proc.stdin.flush()
                except Exception:
                    pass
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        finally:
            self.proc = None


XTTS_LANGUAGES = ["fr", "en", "es", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh", "ja", "hu", "ko", "hi"]
CHATTERBOX_LANGUAGES = ["fr", "en", "es", "de", "it", "pt", "nl", "pl", "ru", "sv", "da", "fi", "no", "el", "he",
                        "ar", "hi", "ja", "ko", "zh", "ms", "sw", "tr"]
KOKORO_LANGUAGES = ["fr", "en", "es", "it", "pt", "hi", "ja", "zh"]

XTTS_SPEAKERS = [
    "Claribel Dervla", "Daisy Studious", "Gracie Wise", "Tammie Ema", "Alison Dietlinde", "Ana Florence",
    "Annmarie Nele", "Asya Anara", "Brenda Stern", "Gitta Nikolina", "Henriette Usha", "Sofia Hellen",
    "Tammy Grit", "Tanja Adelina", "Vjollca Johnnie", "Andrew Chipper", "Badr Odhiambo", "Dionisio Schuyler",
    "Royston Min", "Viktor Eka", "Abrahan Mack", "Adde Michal", "Baldur Sanjin", "Craig Gutsy", "Damien Black",
    "Gilberto Mathias", "Ilkin Urbano", "Kazuhiko Atallah", "Ludvig Milivoj", "Suad Qasim", "Torcull Diarmuid",
    "Viktor Menelaos", "Zacharie Aimilios",
]
KOKORO_VOICES = ["ff_siwis", "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "am_adam", "am_michael",
                 "bf_emma", "bf_isabella", "bm_george", "bm_lewis"]


ENGINE_INFOS = {
    "xtts": EngineInfo(
        id="xtts",
        name="XTTS-v2 — clonage de voix",
        tagline="Clonage · Hors ligne · 17 langues",
        description=(
            "Clone une voix à partir de 6 à 30 secondes d'enregistrement, avec une excellente prosodie en "
            "français. Fonctionne hors ligne. Une carte graphique NVIDIA accélère fortement la production "
            "(sinon le processeur est utilisé, plus lentement). Licence du modèle : Coqui Public Model "
            "License (usage non commercial)."
        ),
        supports_cloning=True, requires_install=True, languages=XTTS_LANGUAGES,
        license="CPML (non commercial)", max_chars=240, min_chars=30, quality=5, speed=3,
        params=[
            ParamSpec("temperature", "Créativité", 0.1, 1.0, 0.7, 0.05,
                      "Plus haut = plus expressif mais moins stable"),
            ParamSpec("top_p", "Diversité (top-p)", 0.5, 1.0, 0.85, 0.01),
            ParamSpec("repetition_penalty", "Anti-répétition", 1.0, 15.0, 5.0, 0.5,
                      "Évite les bégaiements et répétitions", decimals=1),
            ParamSpec("speed", "Débit", 0.7, 1.4, 1.0, 0.05),
        ],
        accent="#B388FF",
    ),
    "chatterbox": EngineInfo(
        id="chatterbox",
        name="Chatterbox — clonage expressif",
        tagline="Clonage · Émotions réglables · Licence MIT",
        description=(
            "Clonage de voix multilingue (23 langues dont le français) avec un réglage de l'intensité "
            "émotionnelle. Licence MIT : utilisation commerciale autorisée. Recommandé avec une carte "
            "graphique NVIDIA (4 Go de mémoire vidéo ou plus). Le son produit contient un filigrane inaudible."
        ),
        supports_cloning=True, requires_install=True, languages=CHATTERBOX_LANGUAGES,
        license="MIT", max_chars=280, min_chars=30, quality=5, speed=2,
        params=[
            ParamSpec("exaggeration", "Expressivité", 0.25, 2.0, 0.5, 0.05,
                      "0,5 = neutre ; plus haut = plus dramatique"),
            ParamSpec("cfg_weight", "Guidage (rythme)", 0.0, 1.0, 0.5, 0.05,
                      "Plus bas = débit plus posé, utile avec une forte expressivité"),
            ParamSpec("temperature", "Créativité", 0.05, 1.5, 0.8, 0.05),
        ],
        accent="#FF7AB6",
    ),
    "kokoro": EngineInfo(
        id="kokoro",
        name="Kokoro — hors ligne et léger",
        tagline="Hors ligne · Rapide sans carte graphique",
        description=(
            "Petit modèle neuronal (82 M de paramètres) très rapide même sur un ordinateur portable, "
            "avec une voix française et de nombreuses voix anglaises. Permet de mélanger des voix pour "
            "en créer de nouvelles. Licence Apache 2.0."
        ),
        supports_cloning=False, requires_install=True, languages=KOKORO_LANGUAGES,
        license="Apache 2.0", max_chars=380, min_chars=30, quality=4, speed=5,
        params=[ParamSpec("speed", "Débit", 0.6, 1.6, 1.0, 0.05)],
        accent="#69F0AE",
    ),
}


ENGINE_INFOS["fastclone"] = EngineInfo(
    id="fastclone",
    name="Clonage rapide — Microsoft + conversion",
    tagline="Clonage · Rapide sans carte graphique",
    description=(
        "Une voix Microsoft lit le texte avec une intonation très naturelle, puis un convertisseur gratuit "
        "lui donne le timbre de votre voix clonée. Sans carte graphique, environ 1 minute de calcul par minute "
        "de livre, soit 3 fois plus vite que XTTS-v2 ; la ressemblance est un peu moins fidèle. Nécessite "
        "Internet et le moteur Chatterbox (licence MIT)."
    ),
    supports_cloning=True, requires_install=True, online=True, languages=CHATTERBOX_LANGUAGES,
    license="MIT + service Microsoft", max_chars=400, min_chars=40, quality=4, speed=4,
    params=[
        ParamSpec("rate", "Débit", 0.6, 1.6, 1.0, 0.05),
        ParamSpec("pitch", "Hauteur de la voix de base (Hz)", -40, 40, 0, 1,
                  "Rapproche la voix de base de la hauteur de votre voix", decimals=0),
    ],
    accent="#FFB74D",
    install_id="chatterbox",
)

ENGINE_INFOS["rvc"] = EngineInfo(
    id="rvc",
    name="Modèles de voix RVC (.pth)",
    tagline="Clonage · Modèle .pth + .index",
    description=(
        "Importez un modèle de voix RVC (fichier .pth, avec son index .index si vous l'avez) : une voix Microsoft "
        "lit le texte, puis le modèle lui donne son timbre. Gratuit (code RVC, licence MIT), nécessite Internet. "
        "N'utilisez que des modèles de votre voix, d'une personne qui vous a donné son accord, ou dont la licence "
        "l'autorise."
    ),
    supports_cloning=True, requires_install=True, online=True, languages=CHATTERBOX_LANGUAGES,
    license="MIT + service Microsoft", max_chars=400, min_chars=40, quality=4, speed=3,
    params=[
        ParamSpec("rate", "Débit", 0.6, 1.6, 1.0, 0.05),
        ParamSpec("transpose", "Hauteur (demi-tons)", -24, 24, 0, 1,
                  "−12 : une octave plus grave ; +12 : une octave plus aiguë", decimals=0),
        ParamSpec("index_rate", "Fidélité au timbre", 0.0, 1.0, 0.75, 0.05,
                  "Plus haut : plus proche du modèle (utilise l'index) ; plus bas : moins d'artefacts"),
        ParamSpec("protect", "Protection des consonnes", 0.0, 0.5, 0.33, 0.01,
                  "Évite les sifflements et la voix robotique sur les consonnes"),
    ],
    accent="#4DD0E1",
    install_id="rvc",
)

ENGINE_INFOS["whisper"] = EngineInfo(
    id="whisper",
    name="Whisper — relecture automatique",
    tagline="Contrôle qualité · Hors ligne",
    description=(
        "Réécoute chaque passage produit par une voix neuronale, le compare au texte et refait automatiquement "
        "les passages où des mots sont sautés, mal prononcés ou inventés. Modèle de reconnaissance vocale "
        "gratuit (OpenAI Whisper, licence MIT), exécuté sur votre ordinateur."
    ),
    requires_install=True, languages=["fr", "en", "es", "de", "it", "pt", "nl", "+"], license="MIT",
    quality=4, speed=4, accent="#26C6DA",
)

# Voix Microsoft utilisées comme base du clonage rapide (langue, timbre)
FASTCLONE_BASES = {
    ("fr", "F"): "fr-FR-DeniseNeural", ("fr", "M"): "fr-FR-HenriNeural", ("fr", ""): "fr-FR-RemyMultilingualNeural",
    ("en", "F"): "en-US-AvaMultilingualNeural", ("en", "M"): "en-US-AndrewMultilingualNeural",
    ("en", ""): "en-US-AndrewMultilingualNeural",
}


def fastclone_base(voice: VoiceProfile, language: str) -> str:
    if voice.engine_voice and "-" in voice.engine_voice:
        return voice.engine_voice
    lang = (language or voice.language or "fr").split("-")[0]
    lang = lang if lang in ("fr", "en") else "fr"
    return FASTCLONE_BASES.get((lang, voice.gender or ""), FASTCLONE_BASES[(lang, "")])


class WorkerEngine(TTSEngine):
    def __init__(self, engine_id: str, env_id: str | None = None, worker_name: str | None = None,
                 info: EngineInfo | None = None):
        self.info = info or ENGINE_INFOS[engine_id]
        self.engine_id = engine_id
        self.env_id = env_id or engine_id  # environnement Python (moteur installé)
        self.worker_name = worker_name or engine_id  # moteur chargé dans le processus
        self._worker: WorkerProcess | None = None
        self._lock = threading.RLock()
        self.load_info: dict = {}

    # -- état ---------------------------------------------------------------------------
    def status(self):
        if not installer.is_installed(self.env_id):
            spec = installer.SPECS[self.env_id]
            if self.env_id != self.engine_id:
                return NOT_INSTALLED, f"Nécessite le moteur Chatterbox ({spec.size_cpu} sans GPU) — gratuit"
            return NOT_INSTALLED, f"À installer ({spec.size_gpu} avec GPU, {spec.size_cpu} sans) — gratuit"
        info = installer.installed_info(self.env_id) or {}
        where = "carte graphique" if info.get("device") == "cuda" else "processeur"
        return READY, f"Installé · {where}"

    def _device(self) -> str:
        from ...config import settings

        pref = settings().get("device", "auto")
        if pref == "auto":
            info = installer.installed_info(self.env_id) or {}
            return "cuda" if info.get("device") == "cuda" else "cpu"
        return pref

    def _ensure(self) -> WorkerProcess:
        with self._lock:
            if self._worker is not None and self._worker.alive():
                return self._worker
            if not installer.is_installed(self.env_id):
                raise EngineError(f"Le moteur « {self.info.name} » n'est pas installé. "
                                  "Installez-le depuis la page Moteurs.")
            w = WorkerProcess(self.engine_id, self.worker_name, installer.env_python(self.env_id),
                              installer.worker_env(self.env_id), installer.engine_root(self.env_id))
            w.start()
            emit_log(self.engine_id, "Chargement du modèle…")
            self.load_info = w.request("load", timeout=3600, device=self._device(),
                                       options=self.load_options())
            self._worker = w
            self._save_speakers(w)
            return w

    def load_options(self) -> dict:
        return {"model_dir": str(installer.model_dir(self.env_id))}

    def _speakers_file(self) -> Path:
        return installer.engine_root(self.engine_id) / "speakers.json"

    def _save_speakers(self, w: WorkerProcess) -> None:
        try:
            sp = w.request("speakers", timeout=60).get("speakers", [])
            if sp:
                self._speakers_file().write_text(json.dumps(sp, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            log.debug("Liste des voix intégrées indisponible : %s", exc)

    def list_builtin_voices(self, refresh: bool = False) -> list[BuiltinVoice]:
        f = self._speakers_file()
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                return [BuiltinVoice(id=d["id"], name=d.get("name", d["id"]), language=d.get("language", ""),
                                     gender=d.get("gender", "")) for d in data]
            except Exception:
                pass
        if self.engine_id == "xtts":
            return [BuiltinVoice(id=n, name=n, language="multi") for n in XTTS_SPEAKERS]
        if self.engine_id == "kokoro":
            return [BuiltinVoice(id=v, name=v, language="fr" if v.startswith("f") else "en",
                                 gender="F" if v[1] == "f" else "M") for v in KOKORO_VOICES]
        return []

    def warmup(self) -> None:
        self._ensure()

    # -- synthèse -----------------------------------------------------------------------
    def synthesize(self, text, voice: VoiceProfile, out_path: Path, language: str, speed: float = 1.0,
                   seed: int | None = None) -> Path:
        refs = [str(p) for p in voice.reference_paths() if p.exists()]
        if self.engine_id == "chatterbox" and not refs:
            raise EngineError("Cette voix n'a pas d'enregistrement de référence : Chatterbox ne fonctionne "
                              "qu'avec des voix clonées.")
        if voice.is_clone and not refs:
            raise EngineError(f"Les enregistrements de référence de la voix « {voice.name} » sont introuvables.")
        params = self.merged_params(voice)
        native_speed = self.engine_id in ("xtts", "kokoro")
        if native_speed:
            params["speed"] = float(params.get("speed", 1.0)) * float(speed or 1.0)
        target = Path(out_path).with_suffix(".wav")
        payload = dict(text=text, language=language, refs=refs, speaker=voice.engine_voice or None,
                       out=str(target), params=params, seed=seed, device=self._device())
        for attempt in range(2):
            w = self._ensure()
            try:
                w.request("synth", timeout=900, **payload)
                break
            except WorkerDied:
                with self._lock:
                    self._worker = None
                if attempt == 1:
                    raise
                emit_log(self.engine_id, "Le moteur a redémarré, nouvelle tentative…")
        if not native_speed and abs(float(speed or 1.0) - 1.0) > 0.01:
            from .. import audio

            data, sr = audio.read_audio(target)
            audio.write_audio(target, audio.change_speed(data, sr, float(speed)), sr, subtype="PCM_16")
        return target

    def shutdown(self) -> None:
        with self._lock:
            if self._worker is not None:
                self._worker.stop()
                self._worker = None


class DummyWorkerEngine(WorkerEngine):
    """Moteur de test utilisant le processus de synthèse avec l'interpréteur courant."""

    def __init__(self, python: Path | None = None):
        import sys

        self.info = EngineInfo(id="dummy", name="Moteur de test", tagline="Test", description="Tonalité de test",
                               max_chars=200, params=[ParamSpec("speed", "Débit", 0.5, 2.0, 1.0)])
        self.engine_id = "dummy"
        self.env_id = "dummy"
        self.worker_name = "dummy"
        self._worker = None
        self._lock = threading.RLock()
        self.load_info = {}
        self._python = python or Path(sys.executable)

    def status(self):
        return READY, "Prêt"

    def _device(self) -> str:
        return "cpu"

    def _ensure(self) -> WorkerProcess:
        with self._lock:
            if self._worker is not None and self._worker.alive():
                return self._worker
            installer.engine_root("dummy").mkdir(parents=True, exist_ok=True)
            w = WorkerProcess("dummy", "dummy", self._python, installer.worker_env("dummy"))
            w.start()
            self.load_info = w.request("load", device="cpu", options={})
            self._worker = w
            return w

    def list_builtin_voices(self, refresh: bool = False):
        return [BuiltinVoice(id="test", name="Test", language="fr")]


class FastCloneEngine(WorkerEngine):
    """Voix Microsoft convertie vers le timbre d'une voix clonée (Chatterbox VC)."""

    def __init__(self, engine_id: str = "fastclone", env_id: str = "chatterbox", worker_name: str = "chatterbox_vc"):
        super().__init__(engine_id, env_id=env_id, worker_name=worker_name)

    def _base_params(self, params: dict) -> dict:
        return {"rate": params.get("rate", 1.0), "pitch": params.get("pitch", 0)}

    def _convert_args(self, voice: VoiceProfile, params: dict) -> dict:
        refs = [str(p) for p in voice.reference_paths() if p.exists()]
        if not refs:
            raise EngineError(f"La voix « {voice.name} » n'a pas d'enregistrement de référence.")
        return {"refs": refs}

    def load_options(self) -> dict:
        from ...config import settings

        return {**super().load_options(), "mode": settings().get("fastclone_mode", "fast")}

    def list_builtin_voices(self, refresh: bool = False) -> list[BuiltinVoice]:
        return []

    def synthesize(self, text, voice: VoiceProfile, out_path: Path, language: str, speed: float = 1.0,
                   seed: int | None = None) -> Path:
        import tempfile

        from .. import audio
        from . import get_engine

        params = self.merged_params(voice)
        extra = self._convert_args(voice, params)
        base = VoiceProfile(name="base", engine="edge", engine_voice=fastclone_base(voice, language),
                            params=self._base_params(params))
        edge = get_engine("edge")
        target = Path(out_path).with_suffix(".wav")
        with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
            spoken = edge.synthesize(text, base, Path(td) / "base.mp3", language, speed, seed)
            data, sr = audio.read_audio(spoken)
            src = audio.write_audio(Path(td) / "base.wav", data, sr, subtype="PCM_16")
            for attempt in range(2):
                w = self._ensure()
                try:
                    w.request("convert", timeout=900, source=str(src), out=str(target), device=self._device(),
                              **extra)
                    break
                except WorkerDied:
                    with self._lock:
                        self._worker = None
                    if attempt == 1:
                        raise
        return target


class RVCEngine(FastCloneEngine):
    """Voix Microsoft convertie avec un modèle de voix RVC (.pth + .index)."""

    def __init__(self):
        super().__init__("rvc", env_id="rvc", worker_name="rvc")

    def load_options(self) -> dict:
        return WorkerEngine.load_options(self)

    def _base_params(self, params: dict) -> dict:
        return {"rate": params.get("rate", 1.0)}

    def _convert_args(self, voice: VoiceProfile, params: dict) -> dict:
        files = [p for p in voice.reference_paths() if p.exists()]
        model = next((p for p in files if p.suffix.lower() == ".pth"), None)
        if model is None:
            raise EngineError(f"La voix « {voice.name} » n'a pas de modèle .pth (réimportez-le).")
        index = next((p for p in files if p.suffix.lower() == ".index"), None)
        return {"model": str(model), "index": str(index) if index else "", "pitch": params.get("transpose", 0),
                "index_rate": params.get("index_rate", 0.75), "protect": params.get("protect", 0.33)}


class WhisperTool(WorkerEngine):
    """Reconnaissance vocale pour la relecture automatique (pas une voix)."""

    def __init__(self):
        super().__init__("whisper")

    def load_options(self) -> dict:
        from ...config import settings

        return {"model_dir": str(installer.model_dir("whisper")), "model": settings().get("asr_model", "base")}

    def list_builtin_voices(self, refresh: bool = False) -> list[BuiltinVoice]:
        return []

    def synthesize(self, *args, **kwargs):  # pragma: no cover - outil sans voix
        raise EngineError("Whisper ne produit pas de voix.")

    def transcribe(self, path: Path, language: str = "fr") -> str:
        for attempt in range(2):
            w = self._ensure()
            try:
                return w.request("transcribe", timeout=600, path=str(path), language=language).get("text", "")
            except WorkerDied:
                with self._lock:
                    self._worker = None
                if attempt == 1:
                    raise
        return ""

