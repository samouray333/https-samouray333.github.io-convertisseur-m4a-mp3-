import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Données de test isolées (préférences, voix, moteurs)
_HOME = tempfile.mkdtemp(prefix="leconstudio-tests-")
os.environ["LECONSTUDIO_HOME"] = _HOME
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def has_ffmpeg() -> bool:
    from leconstudio import paths

    return paths.find_tool("ffmpeg") is not None


needs_ffmpeg = pytest.mark.skipif(not has_ffmpeg(), reason="FFmpeg absent")


@pytest.fixture
def tone_engine():
    from leconstudio.core import engines
    from leconstudio.selftest import make_tone_engine

    eng = make_tone_engine()
    engines.register_engine(eng)
    return eng


@pytest.fixture
def library(tmp_path):
    from leconstudio.core.voices import VoiceLibrary

    return VoiceLibrary(tmp_path / "voices")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_HOME, ignore_errors=True)
