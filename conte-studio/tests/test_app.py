"""Fonctions propres à Conte Studio : mises à jour séparées des autres applications, réglages et dossiers partagés,
enregistrement des collections."""

import json
from pathlib import Path

from contestudio.core import updates
from contestudio.core.models import Chapter, Host, Project


def test_pick_release_filters_this_app():
    releases = [
        {"tag_name": "v9.0.0", "assets": []},
        {"tag_name": "lecon-v5.0.0", "assets": []},
        {"tag_name": "podcast-v4.0.0", "assets": []},
        {"tag_name": "conte-v1.2.0", "draft": True},
        {"tag_name": "conte-v1.1.0", "html_url": "u", "assets": [{"name": "ConteStudio-Setup-1.1.0.exe",
                                                                    "browser_download_url": "d"}]},
        {"tag_name": "conte-v1.0.5", "assets": []},
    ]
    rel = updates.pick_release(releases)
    assert rel["version"] == "1.1.0" and rel["download"] == "d"
    assert updates.pick_release([{"tag_name": "v2.0.0"}]) is None


def test_shared_settings_from_audiolivre(tmp_path, monkeypatch):
    from contestudio import config, paths

    other = tmp_path / "audiolivre" / "settings.json"
    other.parent.mkdir()
    other.write_text(json.dumps({"ai_key": "b64:c2stYQ==", "device": "cpu", "accent": "#123456"}), "utf-8")
    monkeypatch.setattr(paths, "shared_settings_file", lambda: other)
    own = tmp_path / "own.json"
    own.write_text(json.dumps({"device": "cuda"}), "utf-8")
    s = config.Settings(own)
    assert s.get("ai_key") == "b64:c2stYQ=="  # clé DeepSeek reprise d'AudioLivre Studio
    assert s.get("device") == "cuda"  # réglage propre conservé
    assert s.get("accent") != "#123456"  # couleurs propres à chaque application


def test_shared_dirs(monkeypatch, tmp_path):
    from contestudio import paths

    monkeypatch.delenv("CONTESTUDIO_HOME", raising=False)
    monkeypatch.setattr(paths, "_portable_home", lambda: None)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    assert paths.engines_dir() == tmp_path / "data" / "AudioLivreStudio" / "engines"
    assert paths.voices_dir() == tmp_path / "config" / "AudioLivreStudio" / "voices"
    assert paths.data_dir() == tmp_path / "data" / "ConteStudio"
    assert paths.shared_settings_file() == tmp_path / "config" / "AudioLivreStudio" / "settings.json"


def test_project_roundtrip_with_story_fields(tmp_path):
    from contestudio.core import project_io

    pr = Project(chapters=[Chapter("Pompon", "x", age="3-5", tone="douce", moral="m", bedtime=True, favorite=True,
                                   cover_path="c.png", audio_file="a.mp3", duration=12.5, description="d")],
                 hosts=[Host("Pompon", "hero", "v1", "bio", style="enfant", pitch=2.0)])
    pr.metadata.child_name = "Emma"
    pr.export.sleep_noise, pr.export.lullaby_seconds = "mer", 90
    target = project_io.save_project(pr, tmp_path / "p")
    assert target.suffix == ".ctsproj"  # extension propre : pas de conflit avec PodCast Studio (.pcsproj)
    back = project_io.load_project(target)
    h = back.hosts[0]
    assert (h.name, h.role, h.style, h.pitch, h.pitch_semitones) == ("Pompon", "hero", "enfant", 2.0, 2.0)
    c = back.chapters[0]
    assert (c.age, c.tone, c.moral, c.bedtime, c.favorite, c.cover_path, c.audio_file, c.duration) == \
        ("3-5", "douce", "m", True, True, "c.png", "a.mp3", 12.5)
    assert back.metadata.child_name == "Emma"
    assert (back.export.sleep_noise, back.export.lullaby_seconds) == ("mer", 90)
    assert Path(tmp_path / "p.ctsproj").exists()
