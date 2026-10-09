"""Appels à FFmpeg/FFprobe (livrés avec l'application sous Windows)."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable, Sequence

from .. import paths

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000 if paths.IS_WINDOWS else 0


class FFmpegError(RuntimeError):
    pass


class Cancelled(Exception):
    """Opération annulée par l'utilisateur."""


def ffmpeg_bin() -> str:
    from ..config import settings

    custom = settings().get("ffmpeg_path")
    if custom and Path(custom).is_file():
        return str(custom)
    found = paths.find_tool("ffmpeg")
    if not found:
        raise FFmpegError(
            "FFmpeg est introuvable. Réinstallez AudioLivre Studio ou indiquez le chemin de ffmpeg.exe "
            "dans les Paramètres."
        )
    return found


def ffprobe_bin() -> str:
    ff = Path(ffmpeg_bin())
    candidate = ff.with_name(ff.name.replace("ffmpeg", "ffprobe"))
    if candidate.is_file():
        return str(candidate)
    found = paths.find_tool("ffprobe")
    if not found:
        raise FFmpegError("FFprobe est introuvable.")
    return found


def popen_kwargs() -> dict:
    kw: dict = {}
    if paths.IS_WINDOWS:
        kw["creationflags"] = CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        kw["startupinfo"] = si
    return kw


def run_ffmpeg(
    args: Sequence[str],
    duration: float | None = None,
    progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> str:
    """Exécute ffmpeg ; ``progress`` reçoit une fraction 0..1 si ``duration`` est connue."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats", *map(str, args)]
    log.debug("ffmpeg %s", " ".join(cmd[1:]))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", **popen_kwargs())
    err_chunks: list[str] = []

    def read_err():
        assert proc.stderr is not None
        for line in proc.stderr:
            err_chunks.append(line)

    t = threading.Thread(target=read_err, daemon=True)
    t.start()
    assert proc.stdout is not None
    for line in proc.stdout:
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise Cancelled()
        if progress and duration and line.startswith("out_time_us="):
            try:
                us = int(line.split("=", 1)[1])
                progress(max(0.0, min(1.0, us / 1e6 / duration)))
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=2)
    err = "".join(err_chunks).strip()
    if proc.returncode != 0:
        raise FFmpegError(err[-2000:] or f"ffmpeg a échoué (code {proc.returncode})")
    if progress and duration:
        progress(1.0)
    return err


def run_ffmpeg_capture(args: Sequence[str]) -> str:
    """Exécute ffmpeg et renvoie stderr (utile pour les filtres d'analyse)."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", *map(str, args)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          **popen_kwargs())
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr[-2000:])
    return proc.stderr


def probe(path: str | Path) -> dict:
    cmd = [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
           "-show_chapters", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          **popen_kwargs())
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip() or "ffprobe a échoué")
    return json.loads(proc.stdout or "{}")


def probe_duration(path: str | Path) -> float:
    try:
        return float(probe(path).get("format", {}).get("duration", 0.0))
    except Exception:
        return 0.0


def decode_to_wav(src: str | Path, dst: str | Path, sample_rate: int | None = None, mono: bool = True,
                  extra_filters: str | None = None) -> Path:
    args = ["-i", str(src), "-vn"]
    if mono:
        args += ["-ac", "1"]
    if sample_rate:
        args += ["-ar", str(sample_rate)]
    if extra_filters:
        args += ["-af", extra_filters]
    args += ["-c:a", "pcm_f32le", str(dst)]
    run_ffmpeg(args)
    return Path(dst)


def escape_metadata(value: str) -> str:
    """Échappement pour les fichiers FFMETADATA."""
    return re.sub(r"([=;#\\\n])", r"\\\1", value or "")


def concat_list_file(files: Sequence[Path], target: Path) -> Path:
    lines = []
    for f in files:
        p = str(Path(f).resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{p}'")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def version() -> str:
    try:
        out = subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, text=True, **popen_kwargs())
        return out.stdout.splitlines()[0] if out.stdout else "?"
    except Exception as exc:
        return f"indisponible ({exc})"


def has_encoder(name: str) -> bool:
    try:
        out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-encoders"], capture_output=True, text=True,
                             **popen_kwargs())
        return re.search(rf"\s{re.escape(name)}\s", out.stdout) is not None
    except Exception:
        return False
