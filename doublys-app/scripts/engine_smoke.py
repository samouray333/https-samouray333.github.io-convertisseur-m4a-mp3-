"""Test réel des moteurs et de la chaîne de doublage complète (CPU).

Usage :
  python scripts/engine_smoke.py --engine analysis|whisper|kokoro|chatterbox|xtts   (installation + essai d'un moteur)
  python scripts/engine_smoke.py --full   (vidéo anglaise à deux voix → VF complète avec les vrais modèles)
  python scripts/engine_smoke.py --full --lang ja --hardsubs   (japonais + sous-titres anglais incrustés, OCR)
  python scripts/engine_smoke.py --ocr-bench 22   (temps de lecture des sous-titres incrustés sur 22 min)
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
DIALOGUE4 = [  # quatre personnes : deux hommes, deux femmes (le cas difficile)
    ("am_michael", "Alright team, listen up. We only have ten minutes before they arrive."),
    ("bf_emma", "I've checked the doors on the east side. Everything is locked."),
    ("bm_george", "Good. I will stay near the window and keep an eye on the street."),
    ("af_heart", "And what about me? I don't want to wait here doing nothing."),
    ("am_michael", "You take the radio. If anything moves, you call us immediately."),
    ("bm_george", "Did anyone see where the captain went this morning?"),
    ("bf_emma", "He left early. He said he had to meet someone downtown."),
    ("af_heart", "That sounds strange. He never leaves without telling me."),
    ("am_michael", "We will ask him later. Right now, everybody to your positions."),
    ("bf_emma", "Understood. Good luck, everyone."),
]
DIALOGUES = {
    "en": (DIALOGUE, "en"),
    "en4": (DIALOGUE4, "en"),
    "ja": ([
        ("am_michael", "おはよう。こんなに早く会えるとは思わなかった。"),
        ("af_heart", "眠れなかったの。嵐のせいで一晩中起きていたから。"),
        ("am_michael", "会議の資料はできた？みんな数字を待っているよ。"),
        ("af_heart", "もう少し。あと二十分で全員に送るね。"),
        ("am_michael", "完璧だ。終わるまでコーヒーでも飲もう。"),
        ("af_heart", "いいね。今度はあなたのおごりよ！"),
    ], "ja"),
}
# sous-titres anglais incrustés de la vidéo japonaise (--hardsubs)
HARDSUBS_JA = [
    "Good morning. I didn't think\nI'd see you this early.",
    "I couldn't sleep. The storm\nkept me up all night.",
    "Is the meeting material ready?\nEveryone is waiting for the numbers.",
    "Almost. I'll send it to everyone\nin twenty minutes.",
    "Perfect. Let's have a coffee\nuntil you're done.",
    "Nice. This time it's your treat!",
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


def make_video(work: Path, minutes: float = 0.0, lang: str = "en") -> tuple[Path, list[tuple[float, float, str]]]:
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
    dialogue, kokoro_lang = DIALOGUES[lang]
    refs = {}
    if kokoro_lang != "en":
        # Kokoro ne parle pas bien japonais (eSpeak) : Chatterbox multilingue lit le japonais avec le timbre
        # d'une voix Kokoro anglaise
        for voice in {v for v, _t in dialogue}:
            refs[voice] = eng.synthesize("This is a reference recording, spoken calmly and clearly for several "
                                         "seconds, so that the voice can be cloned properly.",
                                         VoiceProfile(name=voice, engine="kokoro", engine_voice=voice),
                                         work / f"ref-{voice}.wav", "en")
        eng = get_engine("chatterbox")
    for i, (voice, text) in enumerate(dialogue):
        vp = (VoiceProfile(name=voice, engine="chatterbox", kind="clone", references=[str(refs[voice])])
              if refs else VoiceProfile(name=voice, engine="kokoro", engine_voice=voice, language=kokoro_lang))
        out = eng.synthesize(text, vp, work / f"src{i}.wav", kokoro_lang)
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


def full(device: str, mode: str, translator: str, minutes: float = 0.0, lang: str = "en",
         hardsubs: bool = False) -> int:
    from doublys.config import settings
    from doublys.core import engines, ffmpeg, pipeline
    from doublys.core import project as project_io
    from doublys.core.engines.neural import LOG_LISTENERS

    for eid in ("analysis", "whisper", "kokoro", "chatterbox") + (("ocr",) if hardsubs else ()):
        ensure(eid, device)
    LOG_LISTENERS.append(lambda e, m: log(f"[{e}] {m}"))
    work = Path(tempfile.mkdtemp(prefix="doublys-full-"))
    video, truth = make_video(work, minutes, lang)
    expected_subs = []
    if hardsubs:
        from doublys.selftest import burn_hardsubs

        texts = HARDSUBS_JA if lang == "ja" else [t for _v, t in DIALOGUES[lang][0]]
        expected_subs = [(a, b, texts[i % len(texts)]) for i, (a, b, _v) in enumerate(truth)]
        video = burn_hardsubs(video, work / "test-sous-titres.mp4", expected_subs)
    log(f"Vidéo de test : {video} ({ffmpeg.probe_duration(video):.1f} s)")
    settings().set("projects_dir", str(work / "projets"))
    pr = project_io.create_project(video, work / "projets", "Test réel")
    pr.settings.voice_mode = mode
    pr.settings.translator = translator
    pr.settings.source_language = "auto" if hardsubs else DIALOGUES[lang][1]
    if lang in ("ja", "zh", "ko"):
        pr.settings.whisper_model = "medium"
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
    expected = len({v for _a, _b, v in truth})
    if len(pr.people) != expected:
        errors.append(f"{len(pr.people)} personnes trouvées au lieu de {expected}")
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
    from doublys.core import coverage

    text, problems = coverage.summary(pr)
    log(f"Couverture : {text}")
    for g in pr.gaps:
        log(f"  passage sans VF {g['start']:.2f}-{g['end']:.2f} ({g['state']}) {g.get('text', '')}")
    for d in coverage.load_dropped(pr):
        log(f"  écarté {d['start']:.2f}-{d['end']:.2f} {d['reason']} : {d.get('text', '')}")
    if problems:
        errors.append(f"couverture incomplète : {text}")
    if hardsubs:
        import difflib

        if pr.subs.kind != "ocr":
            errors.append(f"sous-titres incrustés non utilisés ({pr.subs.kind})")
        if lang != "en" and pr.settings.detected_language != lang:
            errors.append(f"langue détectée {pr.settings.detected_language} au lieu de {lang}")
        cues = pipeline.load_cues(pr)
        if len(cues) != len(expected_subs):
            errors.append(f"{len(cues)} sous-titres lus au lieu de {len(expected_subs)}")
        for c, (a, b, t) in zip(cues, expected_subs):
            ratio = difflib.SequenceMatcher(a=c.text.replace("\n", " "), b=t.replace("\n", " ")).ratio()
            log(f"  OCR [{c.start:6.2f}-{c.end:6.2f}] attendu [{a:6.2f}-{b:6.2f}] {ratio:.0%} « {c.text} »")
            if ratio < 0.95:
                errors.append(f"lecture « {c.text} » au lieu de « {t} »")
            if abs(c.start - a) > 0.15 or abs(c.end - b) > 0.15:
                errors.append(f"temps du sous-titre {c.start:.2f}-{c.end:.2f} au lieu de {a:.2f}-{b:.2f}")
    (work / "rapport.json").write_text(json.dumps({"seconds": total, "errors": errors}, indent=2), encoding="utf-8")
    engines.shutdown_all()
    if errors:
        log("ÉCHEC : " + " ; ".join(errors))
        return 1
    log(f"SUCCÈS — résultat : {files[0]}")
    return 0


def series_test(device: str) -> int:
    """Épisode 1 (4 personnes nommées, enregistrées dans une série) puis épisode 2 (autres phrases, deux des
    mêmes voix) : les personnages doivent être reconnus avec leur nom."""
    from doublys.config import settings
    from doublys.core import engines, pipeline, series
    from doublys.core import project as project_io

    for eid in ("analysis", "whisper", "kokoro", "chatterbox"):
        ensure(eid, device)
    names = {"am_michael": "Chef", "bf_emma": "Emma", "bm_george": "George", "af_heart": "Lucie"}
    work = Path(tempfile.mkdtemp(prefix="doublys-serie-"))
    settings().set("projects_dir", str(work / "projets"))
    series.delete("Série de test")
    steps = ["extract", "separate", "transcribe", "segment", "speakers", "translate", "voices"]

    def episode(lang: str, title: str):
        (work / title).mkdir(parents=True, exist_ok=True)
        video, truth = make_video(work / title, 0.0, lang)
        pr = project_io.create_project(video, work / "projets", title)
        pr.series = "Série de test"
        for st in steps:
            pipeline.run_step(pr, st, pipeline.Job(on_log=log))
        voice_of = {}
        for ln in pr.lines:
            mid = (ln.start + ln.end) / 2
            who = next((v for a, b, v in truth if a - 0.3 <= mid <= b + 0.3), None)
            voice_of.setdefault(ln.person_id, who)
        return pr, voice_of

    ep1, v1 = episode("en4", "Episode 1")
    for p in ep1.people:
        p.name = names[v1[p.id]]
    _s, n = series.save_from_project(ep1, "Série de test")
    log(f"Épisode 1 : {n} personnages enregistrés")
    ep2, v2 = episode("en", "Episode 2")
    errors = []
    for p in ep2.people:
        expected = names.get(v2.get(p.id), "?")
        log(f"Épisode 2 : {p.name} (attendu : {expected})")
        if p.name != expected:
            errors.append(f"{p.name} au lieu de {expected}")
    engines.shutdown_all()
    series.delete("Série de test")
    if errors:
        log("ÉCHEC : " + " ; ".join(errors))
        return 1
    log("SUCCÈS — personnages reconnus d'un épisode à l'autre")
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


def ocr_bench(device: str, minutes: float) -> int:
    """Lecture des sous-titres incrustés sur une longue vidéo 1080p (objectif : 22 min lues en moins de 10 min)."""
    import random

    from doublys.core import engines, ffmpeg, ocr
    from doublys.core import project as project_io

    ensure("ocr", device)
    work = Path(tempfile.mkdtemp(prefix="doublys-ocr-"))
    dur = minutes * 60
    rnd = random.Random(7)
    words = ("the dragon is here we have to stop bandora before it is too late geki let's go zyuranger never give "
             "up my friends power of the guardian beasts").split()
    cues, t = [], 2.0
    while t < dur - 4:
        n = rnd.randint(1, 3)
        length = rnd.uniform(1.0, 4.0)
        text = " ".join(rnd.choice(words) for _ in range(rnd.randint(3, 7))).capitalize() + "."
        if n == 2:
            text += "\n" + " ".join(rnd.choice(words) for _ in range(rnd.randint(3, 6))).capitalize() + "!"
        cues.append((round(t, 2), round(t + length, 2), text))
        t += length + rnd.uniform(0.3, 2.5)
    plain = work / "fond.mp4"
    log(f"Création de {minutes:.0f} min de vidéo 1080p avec {len(cues)} sous-titres…")
    ffmpeg.run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size=1920x1080:rate=25:duration={dur:.0f}", "-f", "lavfi",
                       "-i", f"sine=frequency=220:duration={dur:.0f}", "-c:v", "mpeg4", "-q:v", "8", "-c:a", "aac",
                       "-shortest", str(plain)])
    from doublys.selftest import burn_hardsubs

    video = burn_hardsubs(plain, work / "sous-titres.mp4", cues)
    info = project_io.probe_video(video)
    t0 = time.time()
    zone = ocr.detect_zone(video, info.duration, info.width, info.height)
    if zone is None:
        log("ÉCHEC : bande des sous-titres non trouvée")
        return 1
    tz = time.time() - t0
    found, dropped = ocr.read_hardsubs(video, info.duration, info.width, info.height, (zone.top, zone.bottom),
                                       engines.get_tool("ocr"), 12.5,
                                       progress=lambda f, m: log(f"  {f * 100:5.1f} % {m}") if int(f * 1000) % 100 == 0
                                       else None)
    total = time.time() - t0
    engines.shutdown_all()
    import difflib

    good = 0
    for c in cues:
        best = max(found, key=lambda x: min(x.end, c[1]) - max(x.start, c[0]), default=None)
        if best is not None and difflib.SequenceMatcher(a=best.text, b=c[2]).ratio() > 0.9 and \
                abs(best.start - c[0]) <= 0.15:
            good += 1
    log(f"OCR de {minutes:.0f} min : {total / 60:.1f} min (zone {tz:.0f} s) ; {len(found)} sous-titres lus, "
        f"{good}/{len(cues)} exacts (texte ≥ 90 %, début à ± 0,15 s), {len(dropped)} écartés")
    limit = minutes / 22 * 10 * 60
    ok = total <= limit and good >= 0.9 * len(cues)
    log(("SUCCÈS" if ok else "ÉCHEC") + f" (limite {limit / 60:.1f} min, 90 % exacts)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["analysis", "whisper", "kokoro", "chatterbox", "xtts", "ocr"])
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--series", action="store_true", help="reconnaissance des personnages d'un épisode à l'autre")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--mode", default="fastclone_offline")
    ap.add_argument("--translator", default="opus_big")
    ap.add_argument("--minutes", type=float, default=0.0, help="durée de la vidéo de test (--full)")
    ap.add_argument("--lang", default="en", choices=sorted(DIALOGUES), help="langue de la vidéo de test (--full)")
    ap.add_argument("--hardsubs", action="store_true", help="sous-titres anglais incrustés lus par OCR (--full)")
    ap.add_argument("--ocr-bench", type=float, default=0.0, help="temps de l'OCR sur N minutes de vidéo 1080p")
    args = ap.parse_args()
    if args.series:
        return series_test(args.device)
    if args.ocr_bench:
        return ocr_bench(args.device, args.ocr_bench)
    if args.full:
        return full(args.device, args.mode, args.translator, args.minutes, args.lang, args.hardsubs)
    if args.engine == "ocr":
        return ocr_bench(args.device, 2.0)
    if args.engine:
        return single(args.engine, args.device)
    ap.error("--engine ou --full")
    return 2


if __name__ == "__main__":
    sys.exit(main())
