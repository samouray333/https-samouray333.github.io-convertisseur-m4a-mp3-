"""Fonctions propres à PodCast Studio : dialogue écrit par l'IA, flux RSS, mises à jour, réglages partagés."""

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from podcaststudio.core import ai, rss, updates
from podcaststudio.core.exporter import ExportItem
from podcaststudio.core.models import BookMetadata, Chapter, Host, Project

from .test_ai import FakeClient

HOSTS = [("Alex", "Animateur·rice", "journaliste curieuse"), ("Sam", "Invité·e", "")]


def test_write_dialogue_maps_speakers_and_emotions():
    answer = json.dumps({"title": "La marche", "description": "On marche.", "lines": [
        {"speaker": "alex", "text": "Bonjour   et bienvenue !", "emotion": "joyeux"},
        {"speaker": "Sam", "text": "Merci Alex.", "emotion": "inconnue"},
        {"speaker": "Personne", "text": "Je ne suis pas prévu.", "emotion": ""},
        {"speaker": "Sam", "text": "", "emotion": ""}]})
    client = FakeClient([answer])
    title, desc, lines = ai.write_dialogue("La marche à pied", HOSTS, client, minutes=5)
    assert (title, desc) == ("La marche", "On marche.")
    assert [(ln.speaker, ln.text, ln.emotion) for ln in lines] == [
        ("Alex", "Bonjour et bienvenue !", "joyeux"), ("Sam", "Merci Alex.", ""), ("Alex", "Je ne suis pas prévu.", "")]
    body = client.calls[-1][2]
    assert body["temperature"] > 0.5 and "journaliste curieuse" in body["messages"][0]["content"]
    script = ai.dialogue_to_script(lines)
    assert script.split("\n\n")[0] == "@Alex: [joyeux] Bonjour et bienvenue !"
    from podcaststudio.core.textproc import parse_script

    items = parse_script(script)
    assert [i.voice_key for i in items] == ["Alex", "Sam", "Alex"] and items[0].emotion == "joyeux"


def test_write_dialogue_needs_notes_and_hosts():
    for notes, hosts in (("", HOSTS), ("sujet", [])):
        try:
            ai.write_dialogue(notes, hosts, FakeClient([]))
        except ai.AIError:
            continue
        raise AssertionError("erreur attendue")


def test_episode_notes():
    client = FakeClient([json.dumps({"title": "Nouveau titre", "description": "Résumé."})])
    assert ai.episode_notes("Ancien", "@Alex: [joyeux] Salut !", client) == ("Nouveau titre", "Résumé.")
    assert "[joyeux]" not in client.calls[-1][2]["messages"][1]["content"]


def test_feed_without_base_url_uses_relative_links(tmp_path):
    folder = tmp_path / "episodes"
    folder.mkdir()
    mp3 = folder / "001 - Un & deux.mp3"
    mp3.write_bytes(b"x" * 10)
    meta = BookMetadata(title="Mon <podcast>", author="Moi", explicit=True)
    it = ExportItem("Épisode & co", mp3, number=1, description="Ligne 1\n\nLigne 2", episode_type="full")
    xml = rss.build_feed(meta, [(it, mp3, 3725.4)], tmp_path, now=datetime(2026, 3, 1, tzinfo=timezone.utc))
    root = ET.fromstring(xml)
    item = root.find("channel/item")
    assert root.findtext("channel/title") == "Mon <podcast>"
    assert item.find("enclosure").get("url") == "episodes/001%20-%20Un%20%26%20deux.mp3"
    ns = {"itunes": rss.ITUNES_NS}
    assert item.findtext("itunes:duration", namespaces=ns) == "01:02:05"
    assert item.findtext("itunes:explicit", namespaces=ns) == "true"
    assert "<p>Ligne 1</p><p>Ligne 2</p>" in xml
    assert "01 Mar 2026" in item.findtext("pubDate")


def test_pick_release_filters_this_app():
    releases = [
        {"tag_name": "v9.0.0", "assets": []},
        {"tag_name": "lecon-v5.0.0", "assets": []},
        {"tag_name": "podcast-v1.2.0", "draft": True},
        {"tag_name": "podcast-v1.1.0", "html_url": "u", "assets": [{"name": "PodCastStudio-Setup-1.1.0.exe",
                                                                    "browser_download_url": "d"}]},
        {"tag_name": "podcast-v1.0.5", "assets": []},
    ]
    rel = updates.pick_release(releases)
    assert rel["version"] == "1.1.0" and rel["download"] == "d"
    assert updates.pick_release([{"tag_name": "v2.0.0"}]) is None


def test_shared_settings_from_audiolivre(tmp_path, monkeypatch):
    from podcaststudio import config, paths

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
    from podcaststudio import paths

    monkeypatch.delenv("PODCASTSTUDIO_HOME", raising=False)
    monkeypatch.setattr(paths, "_portable_home", lambda: None)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    assert paths.engines_dir() == tmp_path / "data" / "AudioLivreStudio" / "engines"
    assert paths.voices_dir() == tmp_path / "config" / "AudioLivreStudio" / "voices"
    assert paths.data_dir() == tmp_path / "data" / "PodCastStudio"
    assert paths.shared_settings_file() == tmp_path / "config" / "AudioLivreStudio" / "settings.json"


def test_project_roundtrip_with_hosts(tmp_path):
    from podcaststudio.core import project_io

    pr = Project(chapters=[Chapter("Ep", "x", number=3, season=2, description="d", pub_date="2026-05-01",
                                   episode_type="bonus")], hosts=[Host("Alex", "host", "v1", "bio")])
    pr.metadata.media_base_url = "https://x"
    back = project_io.load_project(project_io.save_project(pr, tmp_path / "p.pcsproj"))
    assert back.hosts[0].name == "Alex" and back.hosts[0].bio == "bio"
    c = back.chapters[0]
    assert (c.number, c.season, c.description, c.pub_date, c.episode_type) == (3, 2, "d", "2026-05-01", "bonus")
    assert back.metadata.media_base_url == "https://x"
    assert Path(tmp_path / "p.pcsproj").exists()
