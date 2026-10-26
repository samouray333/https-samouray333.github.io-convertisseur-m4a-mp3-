"""Opérations FFmpeg sur la vidéo : extraction du son, vignettes, export de la version française."""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Callable

from .. import paths
from . import ffmpeg
from .ffmpeg import FFmpegError
from .models import ExportOptions

log = logging.getLogger(__name__)

Progress = Callable[[float], None]
H264_ENCODERS = ("libx264", "libopenh264", "h264_mf")
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def extract_audio(video: Path, out44: Path, out16: Path, duration: float = 0.0, progress: Progress | None = None,
                  cancel: threading.Event | None = None) -> None:
    """Première piste son → original.wav (44,1 kHz stéréo) et original16.wav (16 kHz mono)."""
    ffmpeg.run_ffmpeg(["-i", str(video), "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le",
                       str(out44), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                       str(out16)], duration=duration or None, progress=progress, cancel=cancel)


def to_mono16(src: Path, dst: Path, cancel: threading.Event | None = None) -> Path:
    ffmpeg.run_ffmpeg(["-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)], cancel=cancel)
    return dst


def thumbnail(video: Path, t: float, out: Path, width: int = 320) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run_ffmpeg(["-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1", "-vf",
                       f"scale={width}:-2", "-q:v", "4", str(out)])
    return out


def extract_frames(video: Path, start: float, length: float, out_dir: Path, fps: float = 12.0,
                   width: int = 480) -> list[Path]:
    """Images d'un passage de la vidéo (aperçu intégré)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg.run_ffmpeg(["-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.1, length):.3f}", "-i", str(video),
                       "-vf", f"fps={fps},scale={width}:-2", "-q:v", "5", str(out_dir / "%05d.jpg")])
    return sorted(out_dir.glob("*.jpg"))


def video_encoder() -> str:
    for enc in H264_ENCODERS:
        if ffmpeg.has_encoder(enc):
            return enc
    raise FFmpegError("Aucun encodeur vidéo H.264 disponible (libx264, libopenh264 ou Media Foundation).")


def encoder_args(enc: str, height: int = 1080, fast: bool = False) -> list[str]:
    bitrate = "2M" if fast else ("4M" if height <= 720 else "8M" if height <= 1080 else "16M")
    if enc == "libx264":
        return ["-c:v", "libx264", "-preset", "ultrafast" if fast else "medium", "-crf", "26" if fast else "20",
                "-pix_fmt", "yuv420p"]
    if enc == "libopenh264":
        return ["-c:v", "libopenh264", "-b:v", bitrate, "-pix_fmt", "yuv420p"]
    return ["-c:v", enc, "-b:v", bitrate, "-pix_fmt", "yuv420p"]


def _subtitle_filter(srt_name: str) -> str:
    return f"subtitles={srt_name}:force_style='Fontsize=22'"


def export_video(video: Path, vf_audio: Path | None, out: Path, opts: ExportOptions, duration: float = 0.0,
                 height: int = 1080, srt_fr: Path | None = None, srt_en: Path | None = None,
                 original_codec: str = "", progress: Progress | None = None,
                 cancel: threading.Event | None = None, normalize: bool | None = None,
                 original_language: str = "en") -> Path:
    """Vidéo copiée sans réencodage + piste VF (AAC normalisée), VO en option, sous-titres intégrés.

    ``vf_audio`` vide : sous-titres seuls (VOSTFR), le son d'origine est gardé et les sous-titres français sont
    affichés par défaut."""
    from .models import LANGUAGES, language_name

    iso = LANGUAGES.get(original_language, ("", "und"))[1]
    orig_name = language_name(original_language)
    container = "mkv" if out.suffix.lower() == ".mkv" else "mp4"
    norm = opts.normalize if normalize is None else normalize
    burn = opts.burn_subtitles and srt_fr is not None
    subs = [] if burn else [(p, lang) for p, lang in ((srt_fr, "fre"), (srt_en, iso)) if p is not None]
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
        cwd = None
        vostfr = vf_audio is None
        args = ["-i", str(video)] + ([] if vostfr else ["-i", str(vf_audio)])
        first_sub = 1 if vostfr else 2
        for p, _lang in subs:
            args += ["-i", str(p)]
        args += ["-map", "0:v:0", "-map", "0:a:0" if vostfr else "1:a:0"]
        if opts.keep_original_audio and not vostfr:
            args += ["-map", "0:a:0"]
        for k in range(len(subs)):
            args += ["-map", f"{first_sub + k}:0"]
        args += ["-map_metadata", "0", "-map_chapters", "0"]
        video_args = ["-c:v", "copy"]
        if burn:
            local = Path(td) / "fr.srt"
            shutil.copyfile(srt_fr, local)
            cwd = td
            video_args = ["-vf", _subtitle_filter("fr.srt"), *encoder_args(video_encoder(), height)]
        copy_ok = container == "mkv" or original_codec in ("aac", "mp3", "ac3", "eac3")
        if vostfr:  # son d'origine copié tel quel (pas de normalisation : rien n'est mixé)
            a = (["-c:a:0", "copy"] if copy_ok else ["-c:a:0", "aac", "-b:a:0", opts.audio_bitrate or "192k"])
            a += ["-metadata:s:a:0", f"language={iso}", "-metadata:s:a:0", f"title={orig_name} (VO)",
                  "-disposition:a:0", "default"]
        else:
            a = ["-c:a:0", "aac", "-b:a:0", opts.audio_bitrate or "192k", "-ar:a:0", "48000"]
            if norm:
                a += ["-filter:a:0", LOUDNORM]
            a += ["-metadata:s:a:0", "language=fre", "-metadata:s:a:0", "title=Français (VF)", "-disposition:a:0",
                  "default"]
        if opts.keep_original_audio and not vostfr:
            a += (["-c:a:1", "copy"] if copy_ok else ["-c:a:1", "aac", "-b:a:1", "192k"])
            a += ["-metadata:s:a:1", f"language={iso}", "-metadata:s:a:1", f"title={orig_name} (VO)", "-disposition:a:1",
                  "0"]
        s = []
        for k, (_p, lang) in enumerate(subs):
            s += [f"-c:s:{k}", "mov_text" if container == "mp4" else "srt", f"-metadata:s:s:{k}",
                  f"language={lang}", f"-metadata:s:s:{k}",
                  f"title={'Français' if lang == 'fre' else orig_name}", f"-disposition:s:{k}",
                  "default" if vostfr and lang == "fre" else "0"]
        tail = ["-movflags", "+faststart"] if container == "mp4" else []
        cmd = args + video_args + a + s + tail + [str(out)]
        try:
            ffmpeg.run_ffmpeg(cmd, duration=duration or None, progress=progress, cancel=cancel, cwd=cwd)
        except FFmpegError as exc:
            if burn:
                raise
            # codec vidéo refusé par le conteneur : réencodage en H.264
            log.warning("Copie de la vidéo impossible (%s) : réencodage", str(exc)[-300:])
            i = cmd.index("-c:v")
            cmd[i:i + 2] = encoder_args(video_encoder(), height)
            ffmpeg.run_ffmpeg(cmd, duration=duration or None, progress=progress, cancel=cancel, cwd=cwd)
    return out


def export_audio(vf_audio: Path, out: Path, normalize: bool = True, duration: float = 0.0,
                 progress: Progress | None = None, cancel: threading.Event | None = None) -> Path:
    """Piste VF seule en WAV ou MP3."""
    args = ["-i", str(vf_audio)]
    if normalize:
        args += ["-af", LOUDNORM]
    if out.suffix.lower() == ".mp3":
        args += ["-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100"]
    else:
        args += ["-c:a", "pcm_s16le", "-ar", "48000"]
    ffmpeg.run_ffmpeg(args + [str(out)], duration=duration or None, progress=progress, cancel=cancel)
    return out


def preview_clip(video: Path, vf_audio: Path, out: Path, start: float, length: float, height: int = 1080,
                 cancel: threading.Event | None = None) -> Path:
    """Extrait court de la vidéo avec la VF (image réencodée en petite taille : calage exact)."""
    enc = video_encoder()
    args = ["-ss", f"{max(0.0, start):.3f}", "-t", f"{length:.3f}", "-i", str(video),
            "-ss", f"{max(0.0, start):.3f}", "-t", f"{length:.3f}", "-i", str(vf_audio),
            "-map", "0:v:0", "-map", "1:a:0", "-vf", "scale=-2:'min(480,ih)'", *encoder_args(enc, 480, fast=True),
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    ffmpeg.run_ffmpeg(args, cancel=cancel)
    return out
