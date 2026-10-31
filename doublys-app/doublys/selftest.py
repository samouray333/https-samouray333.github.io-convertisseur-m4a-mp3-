"""Autotest de bout en bout (intégration continue et support) : vidéo synthétique, chaîne complète avec des
moteurs factices, export vérifié.

Lancement : ``Doublys.exe --selftest rapport.json``
"""

from __future__ import annotations

import json
import logging
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

from . import __version__, paths

log = logging.getLogger(__name__)

# (début, durée, fréquence) des « répliques » de la vidéo de test : deux personnes (voix grave et aiguë)
SCRIPT = [(1.0, 2.4, 150.0), (4.2, 1.8, 260.0), (6.6, 3.0, 150.0), (10.4, 2.2, 260.0), (13.4, 1.6, 150.0)]
DURATION = 16.0


# ---------------------------------------------------------------------------------------
# Moteurs factices (sans IA, dans le processus)
# ---------------------------------------------------------------------------------------
def make_tone_engine(engine_id: str = "tone"):
    """Voix de test : une tonalité modulée dont la durée suit la longueur du texte et le débit."""
    from .core import audio
    from .core.engines.base import EngineInfo, ParamSpec, TTSEngine

    class ToneEngine(TTSEngine):
        info = EngineInfo(id=engine_id, name="Tonalité de test", tagline="Test", description="Test",
                          max_chars=400, params=[ParamSpec("rate", "Débit", 0.5, 2.0, 1.0)])

        def synthesize(self, text, voice, out_path, language, speed=1.0, seed=None):
            sr = 24000
            dur = max(0.5, len(text) / 15.0 / float(speed or 1.0))
            t = np.arange(int(sr * dur)) / sr
            f0 = 120.0 if voice.gender == "M" else 210.0
            sig = 0.25 * np.sin(2 * math.pi * f0 * t) * (0.55 + 0.45 * np.sin(2 * math.pi * 3.3 * t))
            target = Path(out_path).with_suffix(".wav")
            audio.write_audio(target, sig.astype(np.float32), sr, subtype="PCM_16")
            return target

    return ToneEngine()


class _FakeTool:
    def __init__(self, tool_id: str):
        from .core.engines.base import EngineInfo

        self.info = EngineInfo(id=tool_id, name=f"{tool_id} (test)", tagline="Test", description="Test")

    def status(self):
        return "ready", "Prêt (test)"

    def is_ready(self) -> bool:
        return True

    def shutdown(self) -> None:
        pass


class FakeAnalysis(_FakeTool):
    """Séparation par filtrage, empreinte = fréquence dominante, « traduction » préfixée."""

    def __init__(self):
        super().__init__("analysis")

    def separate(self, path, voice_out, background_out, block=30.0, context=2.0, on_progress=None, speech=None,
                 resume=False):
        import soundfile as sf

        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        spec = np.fft.rfft(data, axis=0)
        f = np.fft.rfftfreq(len(data), 1 / sr)
        mask = ((f > 100) & (f < 4000))[:, None]
        voice = np.fft.irfft(spec * mask, len(data), axis=0).astype(np.float32)
        sf.write(str(voice_out), np.clip(voice, -1, 1), sr, subtype="PCM_16")
        sf.write(str(background_out), np.clip(data - voice, -1, 1), sr, subtype="PCM_16")
        if on_progress:
            on_progress(1.0, "séparé")
        return {"duration": len(data) / sr}

    def embed(self, path, segments, on_progress=None):
        from .core import refs

        out = []
        for start, end in segments:
            x, sr = refs.read_span(Path(path), start, end)
            spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) if len(x) else np.zeros(2)
            freq = np.fft.rfftfreq(len(x), 1 / sr)[int(np.argmax(spec))] if len(x) else 0.0
            v = np.exp(-0.5 * ((np.arange(192) - freq / 4.0) / 3.0) ** 2)
            out.append(list(v / (np.linalg.norm(v) + 1e-9)))
        return out

    def translate(self, texts, model, on_progress=None, n_best=1):
        out = [f"Voici la traduction numéro {i + 1}." for i, _t in enumerate(texts)]
        return [[t, t.replace("Voici", "Voilà")] for t in out] if n_best > 1 else out


class FakeWhisper(_FakeTool):
    """Repère les passages sonores et y place des mots (une phrase par passage)."""

    language = "en"  # langue « détectée »

    def __init__(self):
        super().__init__("whisper")

    def detect_language(self, path, spans):
        return {"language": self.language, "probability": 0.97, "details": [[a, self.language, 0.97]
                                                                             for a, _b in spans]}

    def vad(self, path, threshold=0.5, min_speech_ms=250, min_silence_ms=600, pad_ms=200):
        from .core import audio

        data, sr = audio.read_audio(path)
        # énergie dans la bande de la voix (100 à 4000 Hz) : le fond grave n'est pas de la parole
        win = int(sr * 0.02)
        n = len(data) // win
        frames = data[:n * win].reshape(n, win) * np.hanning(win)
        spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
        f = np.fft.rfftfreq(win, 1 / sr)
        band = spec[:, (f > 100) & (f < 4000)].sum(axis=1)
        db = 10 * np.log10(np.maximum(band, 1e-12))
        # seuil bas : passages plus faibles retenus (comme Silero avec un seuil plus bas)
        on = np.append(db > (db.max() - (30 if threshold < 0.5 else 20)), False)
        regions, start = [], None
        for i, v in enumerate(on):
            if v and start is None:
                start = i * 0.02
            elif not v and start is not None:
                regions.append([start, i * 0.02])
                start = None
        return regions

    def transcribe_words(self, path, language="en", model="small", on_progress=None, start=0.0, end=None):
        from .core import audio

        data, sr = audio.read_audio(path)
        a = int(start * sr)
        data = data[a:int(end * sr) if end else len(data)]
        db = audio.frame_rms_db(data, sr, 20.0)
        active = db > (db.max() - 20)
        words, start = [], None
        for i, on in enumerate(np.append(active, False)):
            t = i * 0.02
            if on and start is None:
                start = t
            elif not on and start is not None:
                n = max(1, int((t - start) / 0.4))
                step = (t - start) / n
                off = a / sr
                for k in range(n):
                    w = f" word{len(words) + 1}" + ("." if k == n - 1 else "")
                    words.append([round(off + start + k * step, 3), round(off + start + (k + 1) * step - 0.05, 3),
                                  w, 0.9])
                start = None
        return {"words": words, "segments": [], "duration": len(data) / sr, "language": self.language,
                "dropped": []}


class FakeOcr(_FakeTool):
    """« Lecture » de test : le texte d'une ligne est déduit de sa largeur (les vidéos de test écrivent des
    sous-titres de longueurs différentes) ; la confiance est fixe."""

    def __init__(self):
        super().__init__("ocr")
        self.calls = 0

    def ocr_lines(self, files, on_progress=None):
        out = {}
        for f in files:
            with np.load(f) as z:
                for name in z.files:
                    self.calls += 1
                    h, w = z[name].shape[:2]
                    out[name] = [f"Subtitle line of {w} by {h} pixels.", 0.95]
        return out


def make_test_video(target: Path) -> Path:
    """Mire vidéo + « voix » (tonalités par personne) sur un fond musical grave."""
    from .core import audio, ffmpeg

    sr = 44100
    n = int(DURATION * sr)
    t = np.arange(n) / sr
    mix = 0.05 * np.sin(2 * math.pi * 55 * t)  # fond (hors de la bande des voix)
    for start, dur, f0 in SCRIPT:
        a, b = int(start * sr), int((start + dur) * sr)
        tt = t[a:b] - start
        env = np.minimum(1.0, np.minimum(tt, dur - tt) / 0.05)
        mix[a:b] += 0.3 * env * np.sin(2 * math.pi * f0 * tt) * (0.6 + 0.4 * np.sin(2 * math.pi * 4 * tt))
    wav = target.with_suffix(".wav")
    audio.write_audio(wav, np.stack([mix, mix], axis=1).astype(np.float32), sr, subtype="PCM_16")
    ffmpeg.run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=25:duration={DURATION}", "-i", str(wav),
                       "-c:v", "mpeg4", "-q:v", "8", "-c:a", "aac", "-b:a", "128k", "-shortest", str(target)])
    return target


# sous-titres anglais incrustés de la vidéo de test (calés sur les « répliques » de SCRIPT)
HARDSUBS = [(1.0, 3.4, "I can't believe it, Geki!"), (4.2, 6.0, "Let's go, Zyuranger!"),
            (6.6, 9.6, "We have to stop Bandora\nbefore it is too late."), (10.4, 12.6, "The Dragon is here."),
            (13.4, 15.0, "Ha!")]
FONT_CANDIDATES = {
    "win": ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/timesbd.ttf", "C:/Windows/Fonts/verdanab.ttf",
            "C:/Windows/Fonts/arial.ttf"],
    "other": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
}


def test_fonts() -> list[Path]:
    """Polices disponibles pour écrire des sous-titres de test (plusieurs styles si possible)."""
    found = [Path(f) for f in FONT_CANDIDATES["win" if paths.IS_WINDOWS else "other"] if Path(f).exists()]
    return found[:3]


def make_hardsub_video(target: Path, cues=None, size: str = "1280x720", noisy: bool = True,
                       background: str = "testsrc2") -> Path:
    """Vidéo de test avec sous-titres blancs à contour noir incrustés (une ou deux lignes, plusieurs polices, décor
    chargé) sur la voix de test : de quoi vérifier la lecture des sous-titres et leurs temps."""
    import shutil

    from .core import ffmpeg

    cues = HARDSUBS if cues is None else cues
    fonts = test_fonts()
    if not fonts:
        raise RuntimeError("Aucune police trouvée pour écrire les sous-titres de test.")
    sound = make_test_video(target.with_name(target.stem + "_son.mp4"))
    w, h = (int(x) for x in size.split("x"))
    fs = max(16, h // 18)
    with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
        filters = []
        for i, f in enumerate(fonts):
            shutil.copy(f, Path(td) / f"police{i}.ttf")
        for k, (a, b, text) in enumerate(cues):
            rows = text.split("\n")
            for j, row in enumerate(rows):
                (Path(td) / f"t{k}_{j}.txt").write_text(row, encoding="utf-8")
                y = f"h-{int(fs * 1.6 * (len(rows) - j) + fs * 0.6)}"
                filters.append(f"drawtext=fontfile=police{k % len(fonts)}.ttf:textfile=t{k}_{j}.txt:fontsize={fs}:"
                               f"fontcolor=white:borderw={max(2, fs // 14)}:bordercolor=black:x=(w-tw)/2:y={y}:"
                               f"enable='between(t,{a:.2f},{b - 0.01:.2f})'")
        base = (f"testsrc2=size={size}:rate=25:duration={DURATION}" if background == "testsrc2" else
                f"color=c={background}:size={size}:rate=25:duration={DURATION}")
        vf = (",noise=alls=8:allf=t" if noisy else "") + "," + ",".join(filters)
        ffmpeg.run_ffmpeg(["-f", "lavfi", "-i", base, "-i", str(sound), "-map", "0:v", "-map", "1:a",
                           "-vf", vf.lstrip(","), "-c:v", "mpeg4", "-q:v", "6", "-c:a", "copy", "-shortest",
                           str(Path(target).resolve())], cwd=td)
    sound.unlink(missing_ok=True)
    sound.with_suffix(".wav").unlink(missing_ok=True)
    return target


def burn_hardsubs(video: Path, target: Path, cues) -> Path:
    """Écrit des sous-titres blancs à contour noir dans l'image d'une vidéo existante (son copié)."""
    import shutil

    from .core import ffmpeg

    fonts = test_fonts()
    if not fonts:
        raise RuntimeError("Aucune police trouvée pour écrire les sous-titres de test.")
    info = ffmpeg.probe(video)
    v = next(s for s in info["streams"] if s.get("codec_type") == "video")
    fs = max(16, int(v["height"]) // 18)
    with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
        for i, f in enumerate(fonts):
            shutil.copy(f, Path(td) / f"police{i}.ttf")
        if len(cues) > 30:  # beaucoup de sous-titres : un fichier ASS (la ligne de commande Windows est limitée)
            from .core.subtitles import ass_time

            w, h = int(v["width"]), int(v["height"])
            rows = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "", "[V4+ Styles]",
                    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
                    "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                    f"Style: Default,Arial,{fs},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,"
                    f"{max(2, fs // 14)},0,2,20,20,{int(fs * 0.6)},1", "", "[Events]",
                    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
            rows += [f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{t.replace(chr(10), chr(92) + 'N')}"
                     for a, b, t in cues]
            (Path(td) / "st.ass").write_text("\n".join(rows) + "\n", encoding="utf-8")
            ffmpeg.run_ffmpeg(["-i", str(Path(video).resolve()), "-vf", "subtitles=st.ass:fontsdir=.", "-c:v",
                               "mpeg4", "-q:v", "5", "-c:a", "copy", str(Path(target).resolve())], cwd=td)
            return target
        filters = []
        for k, (a, b, text) in enumerate(cues):
            rows = text.split("\n")
            for j, row in enumerate(rows):
                (Path(td) / f"t{k}_{j}.txt").write_text(row, encoding="utf-8")
                y = f"h-{int(fs * 1.6 * (len(rows) - j) + fs * 0.6)}"
                filters.append(f"drawtext=fontfile=police{k % len(fonts)}.ttf:textfile=t{k}_{j}.txt:fontsize={fs}:"
                               f"fontcolor=white:borderw={max(2, fs // 14)}:bordercolor=black:x=(w-tw)/2:y={y}:"
                               f"enable='between(t,{a:.2f},{b:.2f})'")
        ffmpeg.run_ffmpeg(["-i", str(Path(video).resolve()), "-vf", ",".join(filters), "-c:v", "mpeg4", "-q:v", "5",
                           "-c:a", "copy", str(Path(target).resolve())], cwd=td)
    return target


def install_fakes() -> None:
    from .core import engines

    engines.register_engine(make_tone_engine("edge"))
    engines.register_tool("analysis", FakeAnalysis())
    engines.register_tool("whisper", FakeWhisper())
    engines.register_tool("ocr", FakeOcr())


# ---------------------------------------------------------------------------------------
# Autotest
# ---------------------------------------------------------------------------------------
def run_selftest(report_path: Path) -> int:
    results: list[dict] = []
    critical_failed = False

    def check(name: str, critical: bool = True):
        def deco(fn):
            nonlocal critical_failed
            t0 = time.time()
            try:
                detail = fn()
                results.append({"check": name, "ok": True, "detail": detail, "seconds": round(time.time() - t0, 2)})
            except Exception as exc:  # noqa: BLE001
                results.append({"check": name, "ok": False, "critical": critical, "detail": str(exc),
                                "trace": traceback.format_exc()[-3000:], "seconds": round(time.time() - t0, 2)})
                if critical:
                    critical_failed = True
            return fn
        return deco

    work = Path(tempfile.mkdtemp(prefix="doublys-selftest-"))
    os.environ.setdefault("DOUBLYS_HOME", str(work / "home"))

    @check("ffmpeg")
    def _():
        from .core import ffmpeg

        v = ffmpeg.version()
        assert "ffmpeg" in v.lower(), v
        for enc in ("aac", "libmp3lame", "mov_text", "srt", "pcm_s16le"):
            assert ffmpeg.has_encoder(enc), f"encodeur {enc} absent"
        return v

    @check("encodeur vidéo H.264 (incrustation des sous-titres)", critical=False)
    def _():
        from .core import media

        return media.video_encoder()

    @check("uv (installateur des moteurs)")
    def _():
        uv = paths.find_tool("uv")
        assert uv, "uv introuvable"
        from .core.ffmpeg import popen_kwargs

        out = subprocess.run([uv, "--version"], capture_output=True, text=True, **popen_kwargs())
        return out.stdout.strip()

    @check("script du processus moteur")
    def _():
        p = paths.worker_script()
        assert p.is_file(), f"absent : {p}"
        src = p.read_text(encoding="utf-8")
        compile(src, str(p), "exec")
        for name in ("AnalysisBackend", "transcribe_words", "def separate", "def embed", "def translate"):
            assert name in src, name
        return str(p)

    @check("normalisation du texte français")
    def _():
        from .core.textproc import normalize_for_speech

        out = normalize_for_speech("M. Dupont a payé 12,50 € le 1er mai à 14h30.")
        assert "Monsieur" in out and "douze euros cinquante" in out and "quatorze heures trente" in out, out
        return out

    holder: dict = {}

    @check("vidéo de test")
    def _():
        from .core import ffmpeg

        video = make_test_video(work / "video-test.mp4")
        holder["video"] = video
        return f"{ffmpeg.probe_duration(video):.1f} s"

    @check("chaîne de doublage complète (moteurs factices)")
    def _():
        from .config import settings
        from .core import pipeline
        from .core import project as project_io

        install_fakes()
        settings().set("projects_dir", str(work / "projets"))
        pr = project_io.create_project(holder["video"], work / "projets", "Autotest")
        pr.settings.voice_mode = "edge"
        steps = []
        job = pipeline.Job(on_progress=lambda s, f, m: steps.append(s) if not steps or steps[-1] != s else None)
        pipeline.run_all(pr, job, save=lambda: project_io.save_project(pr))
        assert len(pr.lines) == len(SCRIPT), [(round(x.start, 2), round(x.end, 2)) for x in pr.lines]
        assert len(pr.people) == 2, [p.name for p in pr.people]
        for ln, (_s, _d, f0) in zip(sorted(pr.lines, key=lambda x: x.start), SCRIPT):
            same = [x for x, (_a, _b, f) in zip(sorted(pr.lines, key=lambda x: x.start), SCRIPT) if f == f0]
            assert all(x.person_id == ln.person_id for x in same), "personnes mélangées"
        assert all(ln.audio and ln.state in ("ok", "tempo", "rate", "long") for ln in pr.lines), \
            [(ln.state, ln.message) for ln in pr.lines]
        genders = sorted(p.gender for p in pr.people)
        assert genders == ["F", "M"], genders
        loaded = project_io.load_project(pr.path)
        assert len(loaded.lines) == len(pr.lines) and loaded.step_done("mix")
        holder["pr"] = pr
        return f"{len(pr.lines)} répliques, {len(pr.people)} personnes, étapes : {', '.join(steps)}"

    @check("export MP4 (vidéo copiée, VF AAC normalisée, VO, sous-titres)")
    def _():
        from .core import ffmpeg, pipeline

        pr = holder["pr"]
        pr.export.keep_original_audio = True
        pr.export.subtitles_en = True
        pr.export.audio_only = "mp3"
        files = pipeline.export_files(pr, pipeline.Job())
        info = ffmpeg.probe(files[0])
        streams = info["streams"]
        kinds = [s["codec_type"] for s in streams]
        assert kinds.count("audio") == 2 and kinds.count("subtitle") == 2, kinds
        v = next(s for s in streams if s["codec_type"] == "video")
        assert v["codec_name"] == pr.video.video_codec, "la vidéo a été réencodée"
        a0 = next(s for s in streams if s["codec_type"] == "audio")
        assert a0["codec_name"] == "aac" and a0.get("tags", {}).get("language") == "fre", a0
        assert any(f.suffix == ".srt" for f in files) and any(f.suffix == ".mp3" for f in files)
        srt = next(f for f in files if f.name.endswith(".fr.srt")).read_text(encoding="utf-8")
        assert "-->" in srt and "traduction" in srt
        return [f.name for f in files]

    @check("export MKV et aperçu rapide")
    def _():
        from .core import ffmpeg, pipeline

        pr = holder["pr"]
        pr.export.container = "mkv"
        pr.export.audio_only = ""
        files = pipeline.export_files(pr, pipeline.Job(), out_dir=work / "mkv")
        subs = [s["codec_name"] for s in ffmpeg.probe(files[0])["streams"] if s["codec_type"] == "subtitle"]
        assert files[0].suffix == ".mkv" and subs == ["ass", "ass"], subs  # pistes ASS stylées
        prev = pipeline.export_files(pr, pipeline.Job(), preview=True)
        assert prev[0].exists() and ffmpeg.probe_duration(prev[0]) > DURATION - 1
        pr.export.container = "mp4"
        return [files[0].name, prev[0].name]

    @check("incrustation des sous-titres", critical=False)
    def _():
        from .core import ffmpeg, pipeline

        pr = holder["pr"]
        pr.export.burn_subtitles = True
        try:
            files = pipeline.export_files(pr, pipeline.Job(), out_dir=work / "incruste")
        finally:
            pr.export.burn_subtitles = False
        v = next(s for s in ffmpeg.probe(files[0])["streams"] if s["codec_type"] == "video")
        return f"{files[0].name} ({v['codec_name']})"

    @check("sous-titres seuls (VOSTFR, une couleur par personne)")
    def _():
        from .core import ffmpeg, pipeline
        from .core import project as project_io

        pr = project_io.create_project(holder["video"], work / "projets", "Autotest VOSTFR")
        pr.settings.subtitles_only = True
        steps = []
        job = pipeline.Job(on_progress=lambda s, f, m: steps.append(s) if not steps or steps[-1] != s else None)
        pipeline.run_all(pr, job)
        assert not set(steps) & {"voices", "dub", "mix"}, steps
        assert pr.next_step() is None and not any(ln.audio for ln in pr.lines)
        files = pipeline.export_files(pr, pipeline.Job(), out_dir=work / "vostfr")
        assert files[0].name == "Autotest VOSTFR (VOSTFR).mp4", files[0].name
        streams = ffmpeg.probe(files[0])["streams"]
        audio = [x for x in streams if x["codec_type"] == "audio"]
        subs = [x for x in streams if x["codec_type"] == "subtitle"]
        assert len(audio) == 1 and audio[0]["codec_name"] == pr.video.audio_codec, audio
        assert len(subs) == 1 and subs[0].get("disposition", {}).get("default") == 1, subs
        srt = next(f for f in files if f.name.endswith(".fr.srt")).read_text(encoding="utf-8")
        colors = {p.color.upper() for p in pr.people}
        assert all(f'<font color="{c}">' in srt for c in colors), srt[:300]
        return f"{len(pr.lines)} répliques, {len(colors)} couleurs, {files[0].name}"

    @check("sous-titres incrustés (bande, temps, chaîne OCR)", critical=False)
    def _():
        from .core import pipeline
        from .core import project as project_io

        video = make_hardsub_video(work / "incrustes.mp4", size="960x540", background="0x2a4060")
        pr = project_io.create_project(video, work / "projets", "Autotest OCR")
        for step in ("extract", "subtitles"):
            pipeline.run_step(pr, step, pipeline.Job())
        cues = pipeline.load_cues(pr)
        assert pr.subs.kind == "ocr" and len(cues) == len(HARDSUBS), (pr.subs.kind, len(cues))
        worst = max(max(abs(c.start - a), abs(c.end - b)) for c, (a, b, _t) in zip(cues, HARDSUBS))
        assert worst <= 0.15, worst
        return f"bande {pr.subs.zone[0]:.0%}-{pr.subs.zone[1]:.0%}, {len(cues)} sous-titres, écart max {worst:.2f} s"

    @check("voix Windows (SAPI)", critical=False)
    def _():
        from .core.engines.sapi import SapiEngine
        from .core.models import VoiceProfile

        e = SapiEngine()
        st, msg = e.status()
        if st != "ready":
            return f"ignoré : {msg}"
        voices = e.list_builtin_voices()
        if not voices:
            return "aucune voix installée"
        out = e.synthesize("Bonjour, ceci est un test.", VoiceProfile(name="t", engine="sapi",
                                                                       engine_voice=voices[0].id),
                           work / "sapi.wav", "fr")
        assert out.exists() and out.stat().st_size > 1000
        return f"{len(voices)} voix ; {voices[0].name}"

    @check("interface graphique")
    def _():
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from .ui import theme

        theme.apply(app, "dark")
        from .ui.main_window import MainWindow

        win = MainWindow()
        if holder.get("pr") is not None:
            win.ctx.set_project(holder["pr"])
        for key in win.pages:
            win.show_page(key)
            app.processEvents()
        rows = win.pages["dubbing"].table.rowCount()
        cards = len(win.pages["people"].cards)
        win.ctx.dirty = False
        win.close()
        return f"{len(win.pages)} pages, {rows} répliques affichées, {cards} personnes"

    report = {
        "version": __version__, "python": sys.version, "platform": platform.platform(),
        "frozen": paths.is_frozen(), "ok": not critical_failed, "results": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in results:
        log.info("[%s] %s — %s", "OK" if r["ok"] else "ÉCHEC", r["check"], r["detail"])
    return 0 if not critical_failed else 1
