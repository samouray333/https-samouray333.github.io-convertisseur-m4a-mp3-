"""Bande-annonce du podcast : les meilleurs passages des épisodes produits (≈ 30 s), posés sur le jingle."""

from __future__ import annotations

import logging
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from . import audio, ffmpeg, renderer
from .mastering import MasteringOptions, master_file
from .models import Project

log = logging.getLogger(__name__)
SR = 44100


@dataclass
class Passage:
    number: int  # numéro envoyé à l'IA
    episode: str  # titre de l'épisode
    text: str
    source: Path  # rendu de l'épisode
    start: float
    end: float
    emotion: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


def candidates(project: Project, plan: list) -> list[Passage]:
    """Passages parlés des épisodes déjà produits, assez longs pour être compris seuls (2 à 12 s)."""
    out: list[Passage] = []
    for rc in plan:
        if rc.kind != "chapter" or not renderer.chapter_is_current(project, rc):
            continue
        timings = renderer.segment_timings(project, rc)
        src = renderer.chapter_output(project, rc.id)
        for seg, (a, b) in zip(rc.segments, timings):
            if seg.kind not in ("para", "take") or len(seg.display.split()) < 4 or not 2.0 <= b - a <= 12.0:
                continue
            out.append(Passage(len(out) + 1, rc.title, " ".join(seg.display.split()), src, a, b, seg.emotion))
    return out


def pick_fallback(passages: list[Passage], seconds: float) -> list[Passage]:
    """Sans assistant IA : passages expressifs (émotion, exclamation, question), répartis entre les épisodes."""
    def score(p: Passage) -> float:
        s = 2.0 if p.emotion in ("excité", "joyeux", "peur") else 0.0
        s += 1.0 if p.text.rstrip().endswith(("!", "?")) else 0.0
        return s - abs(p.duration - 5.0) * 0.2

    chosen: list[Passage] = []
    used: dict[str, int] = {}
    for p in sorted(passages, key=lambda p: (-score(p), p.number)):
        if sum(c.duration for c in chosen) + p.duration > seconds + 2:
            continue
        if used.get(p.episode, 0) >= 2 and len({x.episode for x in passages}) > 1:
            continue
        chosen.append(p)
        used[p.episode] = used.get(p.episode, 0) + 1
        if sum(c.duration for c in chosen) >= seconds - 3:
            break
    return sorted(chosen, key=lambda p: p.number)


def assemble(passages: list[Passage], target: Path, gap_ms: int = 350) -> Path:
    """Enchaîne les passages (fondus courts) dans un WAV ; garde la stéréo des rendus."""
    channels = max((audio.channels_of(p.source) for p in passages), default=1)
    parts: list[np.ndarray] = []
    for p in passages:
        with sf.SoundFile(str(p.source)) as f:
            a = max(0, int((p.start - 0.08) * f.samplerate))
            b = min(f.frames, int((p.end + 0.15) * f.samplerate))
            f.seek(a)
            data = f.read(b - a, dtype="float32", always_2d=True)
            sr = f.samplerate
        if data.shape[1] < channels:
            data = np.repeat(data[:, :1], channels, axis=1)
        if sr != SR:
            data = np.stack([audio.resample(data[:, c], sr, SR) for c in range(channels)], axis=1)
        n = len(data)
        fade_in, fade_out = min(n, int(SR * 0.03)), min(n, int(SR * 0.12))
        data[:fade_in] *= np.linspace(0, 1, fade_in).reshape(-1, 1)
        data[n - fade_out:] *= np.linspace(1, 0, fade_out).reshape(-1, 1)
        parts += [data, np.zeros((int(SR * gap_ms / 1000), channels), dtype=np.float32)]
    full = np.concatenate(parts) if parts else np.zeros((SR, channels), dtype=np.float32)
    sf.write(str(target), full, SR, subtype="FLOAT")
    return target


def build(passages: list[Passage], out_mp3: Path, music: str = "", bitrate: str = "128k",
          mastering: MasteringOptions | None = None, cancel: threading.Event | None = None) -> Path:
    """Bande-annonce complète : passages, jingle en fond (baissé sous les voix), mastering, MP3."""
    if not passages:
        raise ValueError("Aucun passage produit pour la bande-annonce : produisez d'abord des épisodes.")
    with tempfile.TemporaryDirectory(prefix="bande-annonce-") as td:
        td = Path(td)
        voice = assemble(passages, td / "voix.wav")
        mixed = voice
        bed = Path(music) if music else None
        if bed is not None and bed.is_file():
            dur = audio.duration_of(voice)
            layout = "stereo" if audio.channels_of(voice) == 2 else "mono"
            v_db = audio.analyze_file(voice).rms_db
            gain = v_db - 14.0 - audio.analyze_file(bed).rms_db
            fmt = f"aresample={SR},aformat=sample_fmts=fltp:channel_layouts={layout}"
            graph = (f"[1:a]{fmt},volume={gain:.2f}dB,afade=t=in:d=0.6,afade=t=out:st={max(0.0, dur + 0.5):.2f}:d=1.5[m];"
                     f"[0:a]{fmt},adelay=1200:all=1,apad=pad_dur=1.6,asplit=2[v1][v2];"
                     f"[m][v2]sidechaincompress=threshold=0.04:ratio=6:attack=30:release=500[duck];"
                     f"[v1][duck]amix=inputs=2:duration=first:normalize=0[out]")
            mixed = td / "mix.wav"
            ffmpeg.run_ffmpeg(["-i", str(voice), "-stream_loop", "-1", "-i", str(bed), "-filter_complex", graph,
                               "-map", "[out]", "-c:a", "pcm_f32le", str(mixed)], None, None, cancel)
        mastered = td / "master.wav"
        master_file(mixed, mastered, mastering or MasteringOptions(preset="streaming", room_tone=False), cancel=cancel)
        ac = str(audio.channels_of(mastered))
        ffmpeg.run_ffmpeg(["-i", str(mastered), "-c:a", "libmp3lame", "-b:a", bitrate, "-ar", "44100", "-ac", ac,
                           "-id3v2_version", "3", str(out_mp3)], cancel=cancel)
    return out_mp3
