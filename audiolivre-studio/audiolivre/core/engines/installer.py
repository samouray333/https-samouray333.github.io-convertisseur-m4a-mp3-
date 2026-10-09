"""Installation à la demande des moteurs neuronaux dans des environnements Python isolés (via uv)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ... import paths
from ..ffmpeg import Cancelled, popen_kwargs

log = logging.getLogger(__name__)

LogCb = Callable[[str], None]

TORCH_INDEX = "https://download.pytorch.org/whl/{flavor}"


@dataclass
class GpuInfo:
    name: str
    compute_cap: float
    vram_gb: float

    @property
    def blackwell(self) -> bool:
        return self.compute_cap >= 12.0


@dataclass
class EngineSpec:
    id: str
    packages: list[str]
    torch_version: str | None = None  # None = pas de PyTorch
    torch_version_blackwell: str | None = None
    python: str = "3.11"
    pin_torch: bool = False  # force la version de torch installée (le paquet en exige une autre)
    downloads: list[tuple[str, str]] = field(default_factory=list)
    size_gpu: str = ""
    size_cpu: str = ""
    model_size: str = ""
    version: int = 1  # incrémenté si la recette d'installation change


SPECS: dict[str, EngineSpec] = {
    "xtts": EngineSpec(
        id="xtts",
        # transformers 5 a supprimé des fonctions utilisées par XTTS (isin_mps_friendly)
        packages=["coqui-tts==0.27.5", "transformers>=4.57,<5", "soundfile"],
        torch_version="2.8.0",
        torch_version_blackwell="2.8.0",
        size_gpu="≈ 5 Go", size_cpu="≈ 1,5 Go", model_size="1,8 Go",
    ),
    "chatterbox": EngineSpec(
        id="chatterbox",
        # le filigrane « perth » importe pkg_resources, retiré des versions récentes de setuptools
        packages=["chatterbox-tts==0.1.7", "setuptools<81", "soundfile"],
        torch_version="2.6.0",
        torch_version_blackwell="2.7.1",
        pin_torch=True,
        size_gpu="≈ 6 Go", size_cpu="≈ 2,5 Go", model_size="3 Go",
    ),
    "kokoro": EngineSpec(
        id="kokoro",
        packages=["kokoro-onnx==0.6.1", "soundfile"],
        downloads=[
            ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
             "kokoro-v1.0.onnx"),
            ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
             "voices-v1.0.bin"),
        ],
        size_gpu="≈ 0,6 Go", size_cpu="≈ 0,6 Go", model_size="0,3 Go",
    ),
}


# ---------------------------------------------------------------------------------------
# Détection du matériel
# ---------------------------------------------------------------------------------------
_gpu_cache: list[GpuInfo] | None = None


def detect_gpus(refresh: bool = False) -> list[GpuInfo]:
    global _gpu_cache
    if _gpu_cache is not None and not refresh:
        return _gpu_cache
    gpus: list[GpuInfo] = []
    exe = shutil.which("nvidia-smi")
    if exe is None and paths.IS_WINDOWS:
        cand = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        exe = str(cand) if cand.exists() else None
    if exe:
        try:
            out = subprocess.run(
                [exe, "--query-gpu=name,compute_cap,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=15, **popen_kwargs(),
            ).stdout
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    try:
                        gpus.append(GpuInfo(parts[0], float(parts[1]), round(float(parts[2]) / 1024, 1)))
                    except ValueError:
                        gpus.append(GpuInfo(parts[0], 0.0, 0.0))
        except Exception as exc:
            log.debug("nvidia-smi : %s", exc)
    _gpu_cache = gpus
    return gpus


def recommended_device() -> str:
    gpus = detect_gpus()
    return "cuda" if gpus and gpus[0].vram_gb >= 3.5 else "cpu"


# ---------------------------------------------------------------------------------------
# Emplacements
# ---------------------------------------------------------------------------------------
def engine_root(engine_id: str) -> Path:
    return paths.engines_dir() / engine_id


def env_dir(engine_id: str) -> Path:
    return engine_root(engine_id) / "env"


def env_python(engine_id: str) -> Path:
    d = env_dir(engine_id)
    return d / "Scripts" / "python.exe" if paths.IS_WINDOWS else d / "bin" / "python"


def model_dir(engine_id: str) -> Path:
    d = paths.models_dir() / engine_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def marker_file(engine_id: str) -> Path:
    return engine_root(engine_id) / "installed.json"


def installed_info(engine_id: str) -> dict | None:
    m = marker_file(engine_id)
    if not m.exists() or not env_python(engine_id).exists():
        return None
    try:
        return json.loads(m.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_installed(engine_id: str) -> bool:
    info = installed_info(engine_id)
    spec = SPECS.get(engine_id)
    return bool(info) and (spec is None or info.get("recipe", 1) >= spec.version)


def worker_env(engine_id: str) -> dict[str, str]:
    """Variables d'environnement pour le processus du moteur (modèles rangés dans nos dossiers)."""
    env = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(k, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["HF_HOME"] = str(paths.models_dir() / "huggingface")
    env["TTS_HOME"] = str(model_dir("xtts"))
    env["COQUI_TOS_AGREED"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["GRADIO_ANALYTICS_ENABLED"] = "False"
    return env


def _uv_env() -> dict[str, str]:
    env = worker_env("uv")
    env["UV_CACHE_DIR"] = str(paths.data_dir() / "uv-cache")
    env["UV_PYTHON_INSTALL_DIR"] = str(paths.data_dir() / "python")
    env["UV_NO_PROGRESS"] = "1"
    env["UV_LINK_MODE"] = "copy"
    env["UV_HTTP_TIMEOUT"] = "300"
    return env


def uv_binary() -> str:
    uv = paths.find_tool("uv")
    if not uv:
        raise RuntimeError("L'outil d'installation « uv » est introuvable. Réinstallez AudioLivre Studio.")
    return uv


# ---------------------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------------------
class InstallError(RuntimeError):
    pass


def _run(cmd: list[str], log_cb: LogCb, cancel: threading.Event | None, env: dict | None = None) -> None:
    log_cb("$ " + " ".join(Path(cmd[0]).name if i == 0 else c for i, c in enumerate(cmd)))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", env=env or _uv_env(), **popen_kwargs())
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log_cb(line)
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise Cancelled()
    proc.wait()
    if proc.returncode != 0:
        raise InstallError(f"La commande a échoué (code {proc.returncode}). Consultez le journal ci-dessus.")


def torch_flavor(device: str, gpu: GpuInfo | None) -> str:
    if device != "cuda":
        return "cpu"
    if gpu is not None and gpu.blackwell:
        return "cu128"
    return "cu126"


def download(url: str, dest: Path, log_cb: LogCb, cancel: threading.Event | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "AudioLivreStudio"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last = 0.0
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if time.time() - last > 1.0:
                last = time.time()
                pct = f" ({done * 100 // total} %)" if total else ""
                log_cb(f"Téléchargement de {dest.name} : {done / 1e6:.0f} Mo{pct}")
    os.replace(tmp, dest)
    log_cb(f"{dest.name} téléchargé ({done / 1e6:.0f} Mo)")


def install_engine(engine_id: str, device: str = "auto", log_cb: LogCb = print,
                   cancel: threading.Event | None = None) -> dict:
    """Crée l'environnement du moteur et installe ses dépendances. Peut prendre plusieurs minutes."""
    spec = SPECS[engine_id]
    if device == "auto":
        device = recommended_device()
    gpus = detect_gpus()
    gpu = gpus[0] if gpus else None
    uv = uv_binary()
    root = engine_root(engine_id)
    root.mkdir(parents=True, exist_ok=True)
    venv = env_dir(engine_id)
    marker_file(engine_id).unlink(missing_ok=True)
    if venv.exists():
        log_cb("Suppression de l'ancienne installation…")
        shutil.rmtree(venv, ignore_errors=True)

    log_cb(f"Création de l'environnement Python {spec.python} pour « {engine_id} »…")
    _run([uv, "venv", "--python", spec.python, "--python-preference", "only-managed", "--seed", str(venv)],
         log_cb, cancel)
    py = str(env_python(engine_id))

    flavor = None
    torch_ver = None
    if spec.torch_version:
        flavor = torch_flavor(device, gpu)
        torch_ver = spec.torch_version_blackwell if flavor == "cu128" else spec.torch_version
        if flavor == "cu128" and engine_id == "chatterbox":
            log_cb("Carte graphique récente détectée (RTX 50xx) : PyTorch compatible sélectionné.")
        log_cb(f"Installation de PyTorch {torch_ver} ({'GPU ' + flavor if flavor != 'cpu' else 'processeur'})… "
               "(téléchargement volumineux, patience)")
        _run([uv, "pip", "install", "--python", py, f"torch=={torch_ver}", f"torchaudio=={torch_ver}",
              # avec uv, l'index « extra » est prioritaire : PyTorch vient donc de l'index CUDA/CPU officiel
              "--index-url", "https://pypi.org/simple", "--extra-index-url", TORCH_INDEX.format(flavor=flavor)],
             log_cb, cancel)

    log_cb("Installation du moteur de synthèse…")
    cmd = [uv, "pip", "install", "--python", py, *spec.packages]
    override = None
    if spec.pin_torch and torch_ver:
        fd, name = tempfile.mkstemp(suffix=".txt", prefix="override-")
        os.close(fd)
        override = Path(name)
        override.write_text(f"torch=={torch_ver}\ntorchaudio=={torch_ver}\n", encoding="utf-8")
        cmd += ["--override", str(override)]
    try:
        _run(cmd, log_cb, cancel)
    finally:
        if override is not None:
            override.unlink(missing_ok=True)

    for url, name in spec.downloads:
        target = model_dir(engine_id) / name
        if not target.exists():
            download(url, target, log_cb, cancel)

    log_cb("Vérification de l'installation…")
    check = {"xtts": "import TTS, torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())",
             "chatterbox": "import chatterbox, perth, torch; assert perth.PerthImplicitWatermarker is not None, "
                           "'module perth incomplet'; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())",
             "kokoro": "import kokoro_onnx, onnxruntime; print('onnxruntime', onnxruntime.__version__)"}[engine_id]
    _run([py, "-c", check], log_cb, cancel, env=worker_env(engine_id))

    info = {"engine": engine_id, "device": device, "flavor": flavor, "torch": torch_ver, "recipe": spec.version,
            "gpu": gpu.name if gpu else None, "date": time.strftime("%Y-%m-%d %H:%M")}
    marker_file(engine_id).write_text(json.dumps(info, indent=2), encoding="utf-8")
    log_cb("Installation terminée ✔")
    return info


def uninstall_engine(engine_id: str, remove_models: bool = True) -> None:
    shutil.rmtree(engine_root(engine_id), ignore_errors=True)
    if remove_models:
        shutil.rmtree(paths.models_dir() / engine_id, ignore_errors=True)


def disk_usage(path: Path) -> int:
    total = 0
    if path.exists():
        for f in path.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
    return total
