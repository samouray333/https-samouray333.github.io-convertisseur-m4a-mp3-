"""Test réel d'un moteur neuronal : installation via uv, synthèse d'une voix intégrée et d'une voix clonée.

Usage : python scripts/engine_smoke.py --engine kokoro|xtts|chatterbox [--device cpu]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["kokoro", "xtts", "chatterbox", "whisper"])
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    from audiolivre.core import audio, engines, renderer
    from audiolivre.core.engines import installer
    from audiolivre.core.engines.neural import LOG_LISTENERS
    from audiolivre.core.models import Chapter, Project, VoiceProfile
    from audiolivre.core.voices import VoiceLibrary

    LOG_LISTENERS.append(lambda e, m: log(f"[{e}] {m}"))
    work = Path(tempfile.mkdtemp(prefix="engine-smoke-"))

    t0 = time.time()
    info = installer.install_engine(args.engine, args.device, log_cb=lambda m: log(m))
    log(f"Installation terminée en {time.time() - t0:.0f} s : {info}")

    if args.engine == "whisper":
        from audiolivre.core.asr import word_error
        from audiolivre.core.engines.edge import EdgeEngine

        phrase = "Il était une fois, dans un petit village au bord de la mer, une histoire extraordinaire."
        src = EdgeEngine().synthesize(phrase, VoiceProfile(name="Denise", engine="edge",
                                                           engine_voice="fr-FR-DeniseNeural"), work / "w.mp3", "fr")
        data, sr = audio.read_audio(src)
        wav = audio.write_audio(work / "w.wav", data, sr, "PCM_16")
        tool = engines.get_tool("whisper")
        assert tool.is_ready(), tool.status()
        t1 = time.time()
        heard = tool.transcribe(wav, "fr")
        wer = word_error(phrase, heard)
        log(f"Whisper : « {heard} » en {time.time() - t1:.0f} s (erreur {wer:.2f})")
        assert wer < 0.3, "transcription trop éloignée"
        engines.shutdown_all()
        log("SUCCÈS")
        return 0

    eng = engines.get_engine(args.engine)
    assert eng.is_ready(), eng.status()
    lib = VoiceLibrary(work / "voices")

    voices: list[VoiceProfile] = []
    if args.engine in ("kokoro", "xtts"):
        builtin = "ff_siwis" if args.engine == "kokoro" else "Claribel Dervla"
        voices.append(lib.save(VoiceProfile(name="Intégrée", engine=args.engine, engine_voice=builtin)))
    if args.engine in ("xtts", "chatterbox"):
        # Référence de clonage : une voix Microsoft (réseau) ou, à défaut, une tonalité
        ref_src = work / "ref_src.mp3"
        try:
            from audiolivre.core.engines.edge import EdgeEngine

            ref_src = EdgeEngine().synthesize(
                "Bonjour, je m'appelle Henri. Je vais vous lire une histoire qui se déroule au bord de la mer, "
                "dans un petit village de pêcheurs, au début du siècle dernier.",
                VoiceProfile(name="Henri", engine="edge", engine_voice="fr-FR-HenriNeural"), ref_src, "fr")
        except Exception as exc:
            log(f"Voix Microsoft indisponible ({exc}), référence synthétique utilisée")
            import numpy as np

            sr = 24000
            t = np.arange(sr * 8) / sr
            ref_src = work / "ref_src.wav"
            audio.write_audio(ref_src, (0.3 * np.sin(2 * np.pi * 160 * t)).astype("float32"), sr, "PCM_16")
        clone = VoiceProfile(name="Clone", engine=args.engine, kind="clone", consent=True)
        lib.save(clone)
        audio.prepare_reference(ref_src, lib.voice_dir(clone) / "reference_01.wav")
        clone.references = ["reference_01.wav"]
        voices.append(lib.save(clone))

    for v in voices:
        t1 = time.time()
        out = eng.synthesize("Il était une fois, dans un petit village au bord de la mer, une histoire extraordinaire.",
                             v, work / f"{v.name}.wav", "fr", 1.0, 42)
        data, sr = audio.read_audio(out)
        stats = audio.analyze_array(data, sr)
        log(f"Voix {v.name} : {stats.duration:.1f} s en {time.time() - t1:.0f} s (RMS {stats.rms_db:.1f} dB)")
        assert stats.duration > 1.5, "audio trop court"
        assert stats.rms_db > -45, "audio silencieux"

    # Clonage rapide (voix Microsoft + conversion), qui utilise l'environnement de Chatterbox
    if args.engine == "chatterbox":
        fast = engines.get_engine("fastclone")
        assert fast.is_ready(), fast.status()
        clone = voices[-1]
        fc = lib.save(VoiceProfile(name="Clone rapide", engine="fastclone", kind="clone", consent=True,
                                   references=list(clone.references)))
        import shutil

        shutil.copy2(clone.reference_paths()[0], lib.voice_dir(fc) / clone.references[0])
        for i in range(2):  # le premier passage inclut le chargement du modèle
            t1 = time.time()
            out = fast.synthesize("Il était une fois, dans un petit village au bord de la mer, une histoire "
                                  "extraordinaire qui allait changer la vie de tous ses habitants.",
                                  fc, work / f"fast{i}.wav", "fr", 1.0, 1)
            data, sr = audio.read_audio(out)
            stats = audio.analyze_array(data, sr)
            log(f"Clonage rapide (essai {i + 1}) : {stats.duration:.1f} s d'audio en {time.time() - t1:.0f} s "
                f"(RMS {stats.rms_db:.1f} dB)")
            assert stats.duration > 2 and stats.rms_db > -45

    # Production complète d'un mini-projet avec le moteur réel
    pr = Project(chapters=[Chapter(title="Chapitre 1", text="Bonjour. Ceci est un test de production complet.")],
                 narrator_voice_id=voices[-1].id)
    pr.metadata.title = "Test"
    pr.export.include_credits = False
    from audiolivre.core import project_io

    project_io.save_project(pr, work / "proj" / "Test.alsproj")
    plan = renderer.build_plan(pr, lib)
    rep = renderer.Renderer(pr, lib, renderer.RenderCallbacks(log=log)).render(plan)
    assert not rep.failed_segments, rep.failed_segments
    log(f"Production OK en {rep.elapsed:.0f} s")
    engines.shutdown_all()
    log("SUCCÈS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
