"""Mises à jour propres à Polyglotte Studio, réglages et dossiers partagés avec AudioLivre Studio."""

import json
from pathlib import Path

from polyglottestudio.core import updates
from polyglottestudio.core.models import Chapter, Host, Project, VocabItem


def test_pick_release_filters_this_app():
    releases = [
        {"tag_name": "v9.0.0", "assets": []},
        {"tag_name": "lecon-v5.0.0", "assets": []},
        {"tag_name": "polyglotte-v1.2.0", "draft": True},
        {"tag_name": "polyglotte-v1.1.0", "html_url": "u", "assets": [{"name": "PolyglotteStudio-Setup-1.1.0.exe",
                                                                    "browser_download_url": "d"}]},
        {"tag_name": "polyglotte-v1.0.5", "assets": []},
    ]
    rel = updates.pick_release(releases)
    assert rel["version"] == "1.1.0" and rel["download"] == "d"
    assert updates.pick_release([{"tag_name": "v2.0.0"}]) is None


def test_shared_settings_from_audiolivre(tmp_path, monkeypatch):
    from polyglottestudio import config, paths

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
    from polyglottestudio import paths

    monkeypatch.delenv("POLYGLOTTESTUDIO_HOME", raising=False)
    monkeypatch.setattr(paths, "_portable_home", lambda: None)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    assert paths.engines_dir() == tmp_path / "data" / "AudioLivreStudio" / "engines"
    assert paths.voices_dir() == tmp_path / "config" / "AudioLivreStudio" / "voices"
    assert paths.data_dir() == tmp_path / "data" / "PolyglotteStudio"
    assert paths.shared_settings_file() == tmp_path / "config" / "AudioLivreStudio" / "settings.json"


def test_project_roundtrip_with_hosts(tmp_path):
    from polyglottestudio.core import project_io

    pr = Project(chapters=[Chapter("Leçon", "x", description="d", theme="Au café", level="A2",
                                   vocab=[VocabItem("café", "coffee", favorite=True)], exercises=["repeat"])],
                 hosts=[Host("Maria", "guest", "", "bio", language="es", gender="F")],
                 language_voices={"es": ["native:edge:es-MX-DaliaNeural"]})
    pr.metadata.target_language = "es"
    pr.metadata.target_locale = "es-MX"
    back = project_io.load_project(project_io.save_project(pr, tmp_path / "p.plgproj"))
    h = back.hosts[0]
    assert (h.name, h.bio, h.language, h.gender) == ("Maria", "bio", "es", "F")
    c = back.chapters[0]
    assert (c.description, c.theme, c.level, c.exercises) == ("d", "Au café", "A2", ["repeat"])
    assert isinstance(c.vocab[0], VocabItem) and c.vocab[0].favorite
    assert back.language_voices == {"es": ["native:edge:es-MX-DaliaNeural"]}
    assert (back.metadata.target_language, back.metadata.target_locale) == ("es", "es-MX")
    assert Path(tmp_path / "p.plgproj").exists()
