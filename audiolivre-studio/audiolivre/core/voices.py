"""Bibliothèque de voix de l'utilisateur (voix intégrées favorites, voix clonées, mélanges)."""

from __future__ import annotations

import json
import logging
import shutil
import threading
import zipfile
from pathlib import Path

from .. import paths
from ..config import atomic_write_text
from .models import VoiceProfile, new_id

log = logging.getLogger(__name__)

VOICE_FILE = "voice.json"
VOICE_PACK_EXT = ".alsvoice"

# Voix proposées au premier lancement (aucune installation nécessaire).
DEFAULT_VOICES = [
    VoiceProfile(name="Denise (Française)", engine="edge", engine_voice="fr-FR-DeniseNeural",
                 language="fr", gender="F", color="#FF7AB6",
                 description="Voix neuronale Microsoft, claire et chaleureuse. Nécessite Internet."),
    VoiceProfile(name="Henri (Français)", engine="edge", engine_voice="fr-FR-HenriNeural",
                 language="fr", gender="M", color="#4FC3F7",
                 description="Voix neuronale Microsoft, posée, idéale pour la narration. Nécessite Internet."),
    VoiceProfile(name="Vivienne (Multilingue)", engine="edge", engine_voice="fr-FR-VivienneMultilingualNeural",
                 language="fr", gender="F", color="#B388FF",
                 description="Voix multilingue très expressive. Nécessite Internet."),
    VoiceProfile(name="Rémy (Multilingue)", engine="edge", engine_voice="fr-FR-RemyMultilingualNeural",
                 language="fr", gender="M", color="#69F0AE",
                 description="Voix masculine multilingue naturelle. Nécessite Internet."),
]
DEFAULT_IDS = ["v_default_denise", "v_default_henri", "v_default_vivienne", "v_default_remy"]


class VoiceLibrary:
    def __init__(self, root: Path | None = None):
        self.root = root or paths.voices_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._voices: dict[str, VoiceProfile] = {}
        self.reload()
        if not self._voices:
            self._seed_defaults()

    def _seed_defaults(self) -> None:
        for vid, v in zip(DEFAULT_IDS, DEFAULT_VOICES):
            voice = VoiceProfile.from_dict(v.to_dict())
            voice.id = vid
            self.save(voice)

    def reload(self) -> None:
        with self._lock:
            self._voices.clear()
            for vf in sorted(self.root.glob(f"*/{VOICE_FILE}")):
                try:
                    voice = VoiceProfile.from_dict(json.loads(vf.read_text(encoding="utf-8")))
                    voice.dir = vf.parent
                    self._voices[voice.id] = voice
                except Exception as exc:
                    log.warning("Voix illisible %s : %s", vf, exc)

    def all(self) -> list[VoiceProfile]:
        with self._lock:
            return sorted(self._voices.values(), key=lambda v: (not v.favorite, v.kind != "clone", v.name.lower()))

    def get(self, voice_id: str | None) -> VoiceProfile | None:
        if not voice_id:
            return None
        with self._lock:
            return self._voices.get(voice_id)

    def voice_dir(self, voice: VoiceProfile) -> Path:
        d = self.root / voice.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, voice: VoiceProfile) -> VoiceProfile:
        with self._lock:
            d = self.voice_dir(voice)
            voice.dir = d
            atomic_write_text(d / VOICE_FILE, json.dumps(voice.to_dict(), indent=2, ensure_ascii=False))
            self._voices[voice.id] = voice
            return voice

    def delete(self, voice_id: str) -> None:
        with self._lock:
            voice = self._voices.pop(voice_id, None)
            if voice is not None:
                shutil.rmtree(self.root / voice.id, ignore_errors=True)

    def duplicate(self, voice_id: str) -> VoiceProfile | None:
        src = self.get(voice_id)
        if src is None:
            return None
        clone = VoiceProfile.from_dict(src.to_dict())
        clone.id = new_id("v_")
        clone.name = f"{src.name} (copie)"
        dst_dir = self.voice_dir(clone)
        for ref in src.reference_paths():
            if ref.exists():
                shutil.copy2(ref, dst_dir / ref.name)
        clone.references = [Path(r).name for r in src.references]
        return self.save(clone)

    def add_reference(self, voice: VoiceProfile, source_wav: Path, name: str | None = None) -> str:
        d = self.voice_dir(voice)
        idx = len(voice.references) + 1
        target_name = name or f"reference_{idx:02d}.wav"
        while (d / target_name).exists() and str(d / target_name) != str(source_wav):
            idx += 1
            target_name = f"reference_{idx:02d}.wav"
        if Path(source_wav).resolve() != (d / target_name).resolve():
            shutil.copy2(source_wav, d / target_name)
        if target_name not in voice.references:
            voice.references.append(target_name)
        return target_name

    # -- Partage de voix --------------------------------------------------------------
    def export_pack(self, voice_id: str, target: Path) -> Path:
        voice = self.get(voice_id)
        if voice is None:
            raise KeyError(voice_id)
        if target.suffix != VOICE_PACK_EXT:
            target = target.with_suffix(VOICE_PACK_EXT)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(VOICE_FILE, json.dumps(voice.to_dict(), indent=2, ensure_ascii=False))
            for ref in voice.reference_paths():
                if ref.exists():
                    zf.write(ref, ref.name)
        return target

    def import_pack(self, pack: Path) -> VoiceProfile:
        with zipfile.ZipFile(pack) as zf:
            data = json.loads(zf.read(VOICE_FILE).decode("utf-8"))
            voice = VoiceProfile.from_dict(data)
            voice.id = new_id("v_")
            d = self.voice_dir(voice)
            refs = []
            for name in voice.references:
                safe = Path(name).name
                if safe and safe in zf.namelist():
                    (d / safe).write_bytes(zf.read(safe))
                    refs.append(safe)
            voice.references = refs
        return self.save(voice)


_library: VoiceLibrary | None = None


def library() -> VoiceLibrary:
    global _library
    if _library is None:
        _library = VoiceLibrary()
    return _library
