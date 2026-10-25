"""Test réel des moteurs et de la chaîne de doublage complète (CPU).

Usage :
  python scripts/engine_smoke.py --engine analysis|whisper|kokoro|chatterbox|xtts   (installation + essai d'un moteur)
  python scripts/engine_smoke.py --full   (vidéo anglaise à deux voix → VF complète avec les vrais modèles)
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DIALOGUE = [
    ("am_michael", "Hello Sarah. I didn't expect to see you here so early this morning."),
    ("af_heart", "Well, I couldn't sleep. The storm kept me awake all night, so I came to the office."),
    ("am_michael", "Did you finish the report for the meeting? Everyone is waiting for the numbers."),
    ("af_heart", "Almost. I need twenty more minutes, and then I will send it to the whole team."),
    ("am_michael", "Perfect. Let's grab a coffee while you finish it. I think we both need one."),
    ("af_heart", "Good idea. And this time, you are paying!"),
]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def ensure(eid: str, device: str) -> None:
    from doublys.core.engines import installer

    if installer.is_installed(eid):
        log(f"{eid} déjà installé")
        return
    t0 = time.time()
    installer.install_engine(eid, device, log_cb=lambda m: log(f"[install {eid}] {m}"))
    log(f"{eid} installé en {time.time() - t0:.0f} s")


def make_video(work: Path, minutes: float = 0.0) -> tuple[Path, list[tuple[float, float, str]]]:
    """Vidéo de test : deux voix anglaises (Kokoro) sur une musique, image de mire.

    Avec ``minutes``, le dialogue est répété jusqu'à cette durée, avec des passages de musique seule (sans
    parole) et une réplique criée (+9 dB) à chaque tour."""
    import numpy as np

    from doublys.core import audio, ffmpeg
    from doublys.core.engines import get_engine
    from doublys.core.models import VoiceProfile

    eng = get_engine("kokoro")
    sr = 44100
    clips = []
    for i, (voice, text) in enumerate(DIALOGUE):
        out = eng.synthesize(text, VoiceProfile(name=voice, engine="kokoro", engine_voice=voice, language="en"),
                             work / f"en{i}.wav", "en")
        data, s0 = audio.read_audio(out)
        clips.append((voice, audio.resample(audio.trim_silence(data, s0), s0, sr)))
    parts, truth, t, rep = [audio.silence(1200, sr)], [], 1.2, 0
    while True:
        for i, (voice, data) in enumerate(clips):
            if minutes and i == len(clips) - 1:
                data = np.clip(data * 2.8, -1, 1)  # réplique criée
            truth.append((t, t + len(data) / sr, voice))
            parts += [data, audio.silence(700, sr)]
            t += len(data) / sr + 0.7
        rep += 1
        if not minutes or t >= minutes * 60:
            break
        if rep % 3 == 0:  # passage de musique seule
            parts.append(audio.silence(25000, sr))
            t += 25.0
    voice = np.concatenate(parts + [audio.silence(1500, sr)])
    n = len(voice)
    tt = np.arange(n) / sr
    chords = [(220.0, 277.2, 329.6), (196.0, 246.9, 293.7), (174.6, 220.0, 261.6), (196.0, 246.9, 311.1)]
    music = np.zeros(n)
    for k in range(0, n, 2 * sr):
        seg = slice(k, min(n, k + 2 * sr))
        for f in chords[(k // (2 * sr)) % 4]:
            music[seg] += np.sin(2 * np.pi * f * tt[seg])
    music *= 0.04 * (0.7 + 0.3 * np.sin(2 * np.pi * 0.5 * tt))
    kick = np.exp(-((tt % 0.5) * 30)) * np.sin(2 * np.pi * 60 * tt) * 0.15
    mix = np.stack([voice * 0.8 + music + kick, voice * 0.8 + music * 0.9 + kick], axis=1).astype(np.float32)
    wav = work / "bande.wav"
    import soundfile as sf

    sf.write(str(wav), mix, sr, subtype="PCM_16")
    video = work / "test-en.mp4"
    dur = n / sr
    ffmpeg.run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=25:duration={dur:.2f}", "-i", str(wav),
                       "-c:v", "mpeg4", "-q:v", "6", "-c:a", "aac", "-b:a", "160k", "-shortest", str(video)])
    return video, truth


def full(device: str, mode: str, translator: str, minutes: float = 0.0) -> int:
    from doublys.config import settings
    from doublys.core import engines, ffmpeg, pipeline
    from doublys.core import project as project_io
    from doublys.core.engines.neural import LOG_LISTENERS

    for eid in ("analysis", "whisper", "kokoro", "chatterbox"):
        ensure(eid, device)
    LOG_LISTENERS.append(lambda e, m: log(f"[{e}] {m}"))
    work = Path(tempfile.mkdtemp(prefix="doublys-full-"))
    video, truth = make_video(work, minutes)
    log(f"Vidéo de test : {video} ({ffmpeg.probe_duration(video):.1f} s)")
    settings().set("projects_dir", str(work / "projets"))
    pr = project_io.create_project(video, work / "projets", "Test réel")
    pr.settings.voice_mode = mode
    pr.settings.translator = translator
    timings = {}
    last = {"step": ""}

    def prog(step, frac, msg):
        if step != last["step"]:
            last["step"] = step
            timings[step] = time.time()
        log(f"  {step} {frac * 100:5.1f} % {msg}")

    job = pipeline.Job(on_progress=prog, on_log=log)
    t0 = time.time()
    pipeline.run_all(pr, job, save=lambda: project_io.save_project(pr))
    files = pipeline.export_files(pr, job)
    total = time.time() - t0
    project_io.save_project(pr)
    log(f"Chaîne complète en {total:.0f} s pour {pr.video.duration:.0f} s de vidéo")
    for s, d in pr.steps.items():
        log(f"  {s}: {d.get('detail')}")
    order = sorted(timings.items(), key=lambda kv: kv[1]) + [("fin", time.time())]
    for (s, t0_), (_n, t1_) in zip(order, order[1:]):
        log(f"  durée {s} : {(t1_ - t0_) / 60:.1f} min ({(t1_ - t0_) / pr.video.duration:.2f} × la vidéo)")
    for ln in pr.lines:
        person = pr.person(ln.person_id)
        log(f"  [{ln.start:6.2f}-{ln.end:6.2f}] {person.name if person else '?'} {ln.state:5} "
            f"débit {ln.rate:.2f} tempo {ln.tempo:.2f} | {ln.en} → {ln.fr}")
    for p in pr.people:
        log(f"  {p.name}: genre {p.gender} ({p.pitch_hz} Hz), extrait {p.reference}")
    info = ffmpeg.probe(files[0])
    kinds = [s.get("codec_type") for s in info.get("streams", [])]
    log(f"Fichiers : {[f.name for f in files]} ; flux : {kinds}")
    errors = []
    if len(pr.people) != 2:
        errors.append(f"{len(pr.people)} personnes trouvées au lieu de 2")
    # chaque réplique doit être attribuée à la bonne voix
    bad = 0
    for ln in pr.lines:
        mid = (ln.start + ln.end) / 2
        who = next((v for a, b, v in truth if a - 0.3 <= mid <= b + 0.3), None)
        same = [x for x in pr.lines if next((v for a, b, v in truth if a - 0.3 <= (x.start + x.end) / 2 <= b + 0.3),
                                            None) == who]
        if same and any(x.person_id != ln.person_id for x in same):
            bad += 1
    if bad:
        errors.append(f"{bad} répliques mal attribuées")
    if any(not ln.fr for ln in pr.lines):
        errors.append("répliques sans traduction")
    if any(ln.state == "error" for ln in pr.lines):
        errors.append("répliques en erreur : " + "; ".join(ln.message for ln in pr.lines if ln.state == "error"))
    if "subtitle" not in kinds or kinds.count("audio") < 1:
        errors.append(f"flux inattendus : {kinds}")
    (work / "rapport.json").write_text(json.dumps({"seconds": total, "errors": errors}, indent=2), encoding="utf-8")
    engines.shutdown_all()
    if errors:
        log("ÉCHEC : " + " ; ".join(errors))
        return 1
    log(f"SUCCÈS — résultat : {files[0]}")
    return 0


def single(eid: str, device: str) -> int:
    from doublys.core import audio, engines
    from doublys.core.engines.neural import LOG_LISTENERS
    from doublys.core.models import VoiceProfile

    ensure(eid, device)
    LOG_LISTENERS.append(lambda e, m: log(f"[{e}] {m}"))
    work = Path(tempfile.mkdtemp(prefix="doublys-engine-"))
    if eid in ("analysis", "whisper"):
        ensure("kokoro", device)
        kok = engines.get_engine("kokoro")
        text = "Hello, this is a short test of the speech recognition."
        src = kok.synthesize(text, VoiceProfile(name="t", engine="kokoro", engine_voice="am_michael"), work / "a.wav",
                             "en")
        data, sr = audio.read_audio(src, 16000)
        wav16 = audio.write_audio(work / "a16.wav", data, 16000, "PCM_16")
        if eid == "whisper":
            res = engines.get_tool("whisper").transcribe_words(wav16, "en", "small")
            heard = " ".join(w[2].strip() for w in res["words"])
            log(f"Whisper : « {heard} »")
            assert "test" in heard.lower(), heard
        else:
            tool = engines.get_tool("analysis")
            emb = tool.embed(wav16, [(0.0, 1.5), (1.5, 3.0)])
            assert len(emb) == 2 and len(emb[0]) == 192
            fr = tool.translate(["Hello, how are you today?"], "Helsinki-NLP/opus-mt-tc-big-en-fr")
            log(f"Traduction : {fr}")
            assert fr and fr[0]
            st, _ = audio.read_audio(src, 44100)
            import numpy as np
            import soundfile as sf

            sf.write(str(work / "st.wav"), np.stack([st, st], 1), 44100, subtype="PCM_16")
            tool.separate(work / "st.wav", work / "v.wav", work / "f.wav")
            assert audio.duration_of(work / "v.wav") > 1
    else:
        ensure("kokoro", device)
        mode_engine = {"chatterbox": "fastclone", "xtts": "xtts", "kokoro": "kokoro"}[eid]
        ref = engines.get_engine("kokoro").synthesize(
            "This is the reference voice, speaking clearly for a few seconds so that the clone sounds right.",
            VoiceProfile(name="r", engine="kokoro", engine_voice="am_michael"), work / "ref.wav", "en")
        voice = VoiceProfile(name="t", engine=mode_engine, kind="clone" if eid != "kokoro" else "builtin",
                             engine_voice="kokoro:ff_siwis" if eid == "chatterbox" else "ff_siwis",
                             references=[str(ref)] if eid != "kokoro" else [])
        t0 = time.time()
        out = engines.get_engine(mode_engine).synthesize("Bonjour, ceci est un essai de voix française.", voice,
                                                          work / "fr.wav", "fr")
        log(f"{eid} : {audio.duration_of(out):.1f} s produites en {time.time() - t0:.0f} s")
    engines.shutdown_all()
    log("SUCCÈS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["analysis", "whisper", "kokoro", "chatterbox", "xtts"])
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--mode", default="fastclone_offline")
    ap.add_argument("--translator", default="opus_big")
    ap.add_argument("--minutes", type=float, default=0.0, help="durée de la vidéo de test (--full)")
    args = ap.parse_args()
    if args.full:
        return full(args.device, args.mode, args.translator, args.minutes)
    if args.engine:
        return single(args.engine, args.device)
    ap.error("--engine ou --full")
    return 2


if __name__ == "__main__":
    sys.exit(main())
