"""Conte Studio est une application à part : installateur, exécutable, workflow et versions séparés des autres
applications du dépôt (seuls les moteurs IA, modèles, voix et clé DeepSeek sont partagés)."""

import re
from pathlib import Path

import pytest

from contestudio import APP_ID, ENV_HOME, RELEASE_TAG_PREFIX, SHARED_ID
from contestudio.core.project_io import PROJECT_EXT

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
OTHERS = ["audiolivre-studio", "podcast-studio", "lecon-studio"]


def app_ids() -> dict[str, str]:
    out = {}
    for folder in [ROOT.name] + OTHERS:
        iss = REPO / folder / "packaging" / "installer.iss"
        if iss.exists():
            out[folder] = re.search(r"^AppId=\{\{([0-9A-F-]+)\}", iss.read_text(encoding="utf-8-sig"), re.M).group(1)
    return out


def test_identity_is_its_own():
    assert (APP_ID, ENV_HOME, RELEASE_TAG_PREFIX, PROJECT_EXT) == ("ConteStudio", "CONTESTUDIO_HOME", "conte-v",
                                                                    ".ctsproj")
    assert SHARED_ID == "AudioLivreStudio"  # moteurs, modèles, voix et clé DeepSeek communs


def test_installer_has_unique_app_id_and_names():
    ids = app_ids()
    assert ROOT.name in ids
    assert len(set(ids.values())) == len(ids), ids  # chaque installateur a son identifiant : pas de mélange
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8-sig")
    assert '#define AppName "Conte Studio"' in iss and '#define AppExe "ConteStudio.exe"' in iss
    assert "ConteStudio-Setup-{#AppVersion}" in iss and ".ctsproj" in iss and ".pcsproj" not in iss
    spec = (ROOT / "packaging" / "contestudio.spec").read_text(encoding="utf-8")
    assert 'name="ConteStudio"' in spec and '"contestudio/resources"' in spec


def test_workflow_uses_own_tags_and_paths():
    wf = REPO / ".github" / "workflows" / "conte-studio-windows.yml"
    if not wf.exists():
        pytest.skip("workflow absent (copie isolée du dossier)")
    text = wf.read_text(encoding="utf-8")
    assert 'tags: ["conte-v*"]' in text and '"conte-studio/**"' in text
    assert "working-directory: conte-studio" in text and "group: conte-" in text
    # la version est lue après le préfixe du tag (« conte-v1.2.0 » → « 1.2.0 »)
    assert f".Substring({len(RELEASE_TAG_PREFIX)})" in text
    assert "dist/ConteStudio/ConteStudio.exe" in text and "packaging/contestudio.spec" in text
    for other in OTHERS:
        assert other not in text
    others = [p.read_text(encoding="utf-8") for p in wf.parent.glob("*.yml") if p != wf]
    assert others and all("conte-studio/**" not in t and "conte-v" not in t for t in others)


def test_resources_are_bundled():
    res = ROOT / "contestudio" / "resources"
    assert (res / "app.ico").stat().st_size > 1000 and (res / "histoires" / "exemples.json").exists()
