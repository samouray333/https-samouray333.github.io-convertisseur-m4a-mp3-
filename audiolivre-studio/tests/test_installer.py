import hashlib
import io
import shutil
import tarfile

import pytest

from audiolivre import paths
from audiolivre.core.engines import installer


def _fake_archive(path):
    with tarfile.open(path, "w:gz") as tf:
        data = b"MZ fake python"
        info = tarfile.TarInfo("python/python.exe")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))


def test_base_python_download_and_checksum(tmp_path, monkeypatch):
    archive = tmp_path / "src.tar.gz"
    _fake_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    calls = []

    def fake_download(url, dest, log_cb, cancel=None):
        calls.append(url)
        if url == "https://bad":
            raise OSError("hors ligne")
        shutil.copy(archive, dest)

    shutil.rmtree(installer.base_python_dir(), ignore_errors=True)
    monkeypatch.setattr(installer, "download", fake_download)
    monkeypatch.setattr(installer, "BASE_PYTHON_URLS", ["https://bad", "https://ok"])
    monkeypatch.setattr(installer, "BASE_PYTHON_SHA256", "0" * 64)
    with pytest.raises(installer.InstallError):
        installer.ensure_base_python(lambda m: None)
    assert not (installer.base_python_dir() / "python.exe").exists()

    monkeypatch.setattr(installer, "BASE_PYTHON_SHA256", digest)
    exe = installer.ensure_base_python(lambda m: None)
    assert exe.read_bytes() == b"MZ fake python" and calls[-2:] == ["https://bad", "https://ok"]
    assert installer.ensure_base_python(lambda m: None) == exe  # déjà installé : pas de nouveau téléchargement
    assert len(calls) == 4


def test_remove_uv_links(tmp_path):
    folder = tmp_path / "python"
    (folder / "cpython-3.11.17").mkdir(parents=True)
    try:
        (folder / "cpython-3.11").symlink_to(folder / "cpython-3.11.17", target_is_directory=True)
    except OSError:
        pytest.skip("création de liens symboliques non autorisée")
    installer._remove_links(folder)
    assert [p.name for p in folder.iterdir()] == ["cpython-3.11.17"]
    assert paths.data_dir().exists()
