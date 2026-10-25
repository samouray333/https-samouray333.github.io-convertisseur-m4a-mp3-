import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Données de test isolées (préférences, moteurs)
_HOME = tempfile.mkdtemp(prefix="doublys-tests-")
os.environ["DOUBLYS_HOME"] = _HOME
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def has_ffmpeg() -> bool:
    from doublys import paths

    return paths.find_tool("ffmpeg") is not None


needs_ffmpeg = pytest.mark.skipif(not has_ffmpeg(), reason="FFmpeg absent")


@pytest.fixture
def fakes():
    """Moteurs factices (voix « edge » = tonalité, analyse et Whisper simulés)."""
    from doublys.core import engines
    from doublys.selftest import install_fakes

    install_fakes()
    yield
    with engines._lock:
        engines._tools.clear()
        engines._engines = None


@pytest.fixture(scope="session")
def test_video(tmp_path_factory):
    from doublys.selftest import make_test_video

    return make_test_video(tmp_path_factory.mktemp("video") / "test.mp4")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_HOME, ignore_errors=True)
