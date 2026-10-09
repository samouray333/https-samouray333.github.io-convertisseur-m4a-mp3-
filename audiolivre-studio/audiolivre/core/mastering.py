"""Mastering : égalisation, compression, de-essing et normalisation (normes ACX/Audible)."""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from . import audio, ffmpeg

log = logging.getLogger(__name__)


@dataclass
class MasteringOptions:
    preset: str = "acx"  # acx | streaming | natural | none
    denoise: bool = False
    deesser: bool = True
    room_tone: bool = True
    room_tone_db: float = -72.0
    sample_rate: int = 44100


PRESET_TARGETS = {
    # (RMS cible dB, plafond de crête dBFS)
    "acx": (-19.5, -3.6),
    "natural": (-20.0, -3.6),
}


def _pre_filters(opts: MasteringOptions) -> list[str]:
    f: list[str] = ["highpass=f=75:poles=2"]
    if opts.denoise:
        f.append("afftdn=nf=-32:nr=10")
    if opts.preset in ("acx", "streaming"):
        if opts.deesser:
            f.append("deesser=i=0.35:m=0.5:f=0.5:s=o")
        f.append("acompressor=threshold=-22dB:ratio=2.6:attack=6:release=140:knee=4:makeup=1")
        f.append("equalizer=f=3200:t=q:w=1.4:g=1.2")
    elif opts.preset == "natural":
        if opts.deesser:
            f.append("deesser=i=0.25:m=0.5:f=0.5:s=o")
        f.append("acompressor=threshold=-20dB:ratio=1.8:attack=10:release=200:knee=6:makeup=1")
    return f


def _limiter(ceiling_db: float) -> str:
    limit = max(0.0625, min(1.0, audio.db_to_lin(ceiling_db)))
    return f"alimiter=limit={limit:.4f}:attack=4:release=60:level=0"


def _loudnorm_measure(src: Path, target_i: float, tp: float, lra: float) -> dict:
    out = ffmpeg.run_ffmpeg_capture([
        "-i", str(src), "-af", f"loudnorm=I={target_i}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-",
    ])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", out, re.S)
    if not m:
        raise ffmpeg.FFmpegError("Mesure de loudness impossible")
    return json.loads(m.group(0))


def master_file(
    src: str | Path,
    dst: str | Path,
    opts: MasteringOptions,
    progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> audio.AudioStats:
    """Applique la chaîne de mastering à ``src`` et écrit un WAV 24 bits ``dst``."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    duration = audio.duration_of(src) or None
    sr = opts.sample_rate

    def prog(base: float, span: float):
        if progress is None:
            return None
        return lambda f: progress(base + span * f)

    with tempfile.TemporaryDirectory(prefix="master-") as td:
        td = Path(td)
        stage1 = td / "stage1.wav"
        stage2 = td / "stage2.wav"

        if opts.preset == "none":
            ffmpeg.run_ffmpeg(["-i", str(src), "-ac", "1", "-ar", str(sr), "-c:a", "pcm_f32le", str(stage2)],
                              duration, prog(0, 0.8), cancel)
        else:
            ffmpeg.run_ffmpeg(["-i", str(src), "-ac", "1", "-ar", str(sr), "-af", ",".join(_pre_filters(opts)),
                               "-c:a", "pcm_f32le", str(stage1)], duration, prog(0, 0.4), cancel)
            if opts.preset == "streaming":
                m = _loudnorm_measure(stage1, -16.0, -1.5, 11.0)
                ln = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                      f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                      f"offset={m['target_offset']}:linear=true")
                chain = f"{ln},aresample={sr},{_limiter(-1.5)}"
            else:
                target_rms, ceiling = PRESET_TARGETS.get(opts.preset, PRESET_TARGETS["acx"])
                stats = audio.analyze_file(stage1)
                gain = target_rms - stats.rms_db if stats.rms_db > -90 else 0.0
                gain = max(-20.0, min(30.0, gain))
                chain = f"volume={gain:.2f}dB,{_limiter(ceiling)}"
            ffmpeg.run_ffmpeg(["-i", str(stage1), "-af", chain, "-ar", str(sr), "-c:a", "pcm_f32le", str(stage2)],
                              duration, prog(0.4, 0.4), cancel)

        _finalize(stage2, dst, opts)
        if progress:
            progress(1.0)
    return audio.analyze_file(dst)


def _finalize(src: Path, dst: Path, opts: MasteringOptions) -> None:
    """Ajoute l'ambiance (room tone), garantit le plafond de crête et écrit en 24 bits."""
    info = sf.info(str(src))
    sr = info.samplerate
    ceiling = audio.db_to_lin(PRESET_TARGETS.get(opts.preset, (0, -3.6))[1]) if opts.preset in PRESET_TARGETS else 1.0
    pos = 0
    with sf.SoundFile(str(dst), "w", samplerate=sr, channels=1, subtype="PCM_24") as out:
        for block in sf.blocks(str(src), blocksize=sr * 10, dtype="float32", always_2d=True):
            mono = block.mean(axis=1) if block.shape[1] > 1 else block[:, 0]
            if opts.room_tone and opts.preset != "none":
                mono = mono + audio.room_tone_loop(len(mono), opts.room_tone_db, sr)[: len(mono)]
            np.clip(mono, -ceiling, ceiling, out=mono)
            out.write(mono)
            pos += len(mono)


def copy_or_master(src: Path, dst: Path, opts: MasteringOptions, **kw) -> audio.AudioStats:
    if not src.exists():
        raise FileNotFoundError(src)
    if opts.preset == "none" and src.suffix.lower() == ".wav":
        shutil.copy2(src, dst)
        return audio.analyze_file(dst)
    return master_file(src, dst, opts, **kw)
