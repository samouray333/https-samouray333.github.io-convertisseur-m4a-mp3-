"""Tests des correctifs : vérification des mises à jour, stockage de la clé, genre estimé."""

import hashlib

import pytest

from doublys.core import refs, secrets, updates


def _release(digest=None, extra_assets=()):
    exe = {"name": "Doublys-Setup-1.1.0.exe", "browser_download_url": "https://example.invalid/setup.exe"}
    if digest:
        exe["digest"] = digest
    return [{"tag_name": "doublys-v1.1.0", "html_url": "https://example.invalid/rel",
             "assets": [exe, *extra_assets], "body": ""}]


def test_release_digest_from_github():
    rel = updates.pick_release(_release(digest="sha256:" + "ab" * 32))
    assert rel["sha256"] == "ab" * 32
    assert rel["sha256_url"] is None


def test_release_sha256_asset():
    side = {"name": "Doublys-Setup-1.1.0.exe.sha256", "browser_download_url": "https://example.invalid/s"}
    rel = updates.pick_release(_release(extra_assets=[side]))
    assert rel["sha256"] == "" and rel["sha256_url"] == "https://example.invalid/s"


def test_parse_checksum_formats():
    h = "cd" * 32
    assert updates.parse_checksum(f"{h}  Doublys-Setup-1.1.0.exe\n", "Doublys-Setup-1.1.0.exe") == h
    assert updates.parse_checksum(f"{h} *Doublys-Setup-1.1.0.exe", "doublys-setup-1.1.0.exe") == h
    assert updates.parse_checksum(h, "x.exe") == h  # empreinte seule
    assert updates.parse_checksum(f"{h}  autre.exe", "x.exe") == ""


def test_verify_installer_ok_and_mismatch(tmp_path):
    f = tmp_path / "setup.exe"
    f.write_bytes(b"installateur")
    good = hashlib.sha256(b"installateur").hexdigest()
    updates.verify_installer(f, {"sha256": good})
    assert f.exists()
    with pytest.raises(updates.IntegrityError):
        updates.verify_installer(f, {"sha256": "00" * 32})
    assert not f.exists()  # fichier suspect supprimé


def test_verify_installer_without_checksum_refuses(tmp_path):
    f = tmp_path / "setup.exe"
    f.write_bytes(b"x")
    with pytest.raises(updates.IntegrityError):
        updates.verify_installer(f, {})
    assert not f.exists()


def test_secret_roundtrip_and_flag():
    stored = secrets.protect("sk-test")
    assert secrets.unprotect(stored) == "sk-test"
    assert secrets.is_encrypted("dpapi:xxx") and not secrets.is_encrypted("b64:eHg=")
    assert secrets.unprotect("dpapi:%%%") == ""  # illisible : vide, sans exception


def test_gender_uncertain_zone():
    assert refs.gender_from_pitch(120) == "M" and not refs.gender_is_uncertain(120)
    assert refs.gender_from_pitch(220) == "F" and not refs.gender_is_uncertain(220)
    assert refs.gender_is_uncertain(170) and refs.gender_from_pitch(170) == "F"
    assert not refs.gender_is_uncertain(0)


def test_person_gender_lock_roundtrip():
    from doublys.core.models import Person

    p = Person.from_dict({"name": "P1", "gender": "F", "gender_locked": True})
    assert p.gender_locked
    assert not Person.from_dict({"name": "P2"}).gender_locked  # anciens projets
