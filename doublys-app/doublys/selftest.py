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

    def __init__(self):
        super().__init__("whisper")

    def vad(self, path):
        from .core import audio

        data, sr = audio.read_audio(path)
        db = audio.frame_rms_db(data, sr, 20.0)
        on = np.append(db > (db.max() - 20), False)
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
        return {"words": words, "segments": [], "duration": len(data) / sr, "language": "en"}


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


def install_fakes() -> None:
    from .core import engines

    engines.register_engine(make_tone_engine("edge"))
    engines.register_tool("analysis", FakeAnalysis())
    engines.register_tool("whisper", FakeWhisper())


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
        kinds = [s["codec_type"] for s in ffmpeg.probe(files[0])["streams"]]
        assert files[0].suffix == ".mkv" and kinds.count("subtitle") == 2, kinds
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
