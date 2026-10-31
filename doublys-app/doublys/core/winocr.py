"""Lecture de secours des sous-titres incrustés avec l'OCR intégré à Windows (Windows.Media.Ocr).

Utilisée seulement si le moteur RapidOCR n'est pas installé et que la langue anglaise de reconnaissance de texte
est présente dans Windows (souvent absente sur un Windows français : Paramètres > Heure et langue > Langue >
Ajouter l'anglais avec la « reconnaissance optique de caractères »). Elle passe par Windows PowerShell 5.1, qui
sait appeler les API WinRT : rien à installer.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .. import paths
from . import ffmpeg

log = logging.getLogger(__name__)

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) {
    $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op))
    $null = $task.Wait(-1)
    $task.Result
}
$langs = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
"""

_CHECK = _PRELUDE + r"""
@{ languages = $langs } | ConvertTo-Json -Compress
"""

_READ = _PRELUDE + r"""
$tag = ($langs | Where-Object { $_ -like 'en*' } | Select-Object -First 1)
if (-not $tag) { throw 'Langue anglaise de reconnaissance de texte absente de Windows.' }
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($tag))
$out = @{}
foreach ($line in [System.IO.File]::ReadAllLines($args[0])) {
    if (-not $line) { continue }
    $name, $path = $line -split "`t", 2
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $out[$name] = (@($result.Lines | ForEach-Object { $_.Text }) -join ' ')
    $stream.Dispose()
}
$out | ConvertTo-Json -Compress
"""

_available: bool | None = None


def _powershell() -> str | None:
    if not paths.IS_WINDOWS:
        return None
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(exe) if exe.exists() else None


def _run(script: str, *args: str, timeout: float = 600) -> str:
    exe = _powershell()
    if exe is None:
        raise RuntimeError("Windows PowerShell introuvable.")
    with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
        ps1 = Path(td) / "ocr.ps1"
        ps1.write_text(script, encoding="utf-8-sig")
        res = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(ps1),
                              *args], capture_output=True, timeout=timeout, **ffmpeg.popen_kwargs())
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode("utf-8", "replace").strip()[-600:] or "OCR de Windows en échec.")
    return res.stdout.decode("utf-8", "replace").strip()


def languages() -> list[str]:
    """Langues de reconnaissance de texte installées dans Windows (vide hors Windows ou en cas d'erreur)."""
    try:
        data = json.loads(_run(_CHECK, timeout=60) or "{}")
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired):
        log.debug("OCR de Windows indisponible", exc_info=True)
        return []
    langs = data.get("languages") or []
    return [langs] if isinstance(langs, str) else list(langs)


def available() -> bool:
    """La lecture de secours est possible : Windows avec la langue anglaise de reconnaissance de texte."""
    global _available
    if _available is None:
        _available = any(str(t).lower().startswith("en") for t in languages())
    return _available


def status_message() -> str:
    if not paths.IS_WINDOWS:
        return "OCR de Windows : disponible seulement sous Windows."
    langs = languages()
    if any(str(t).lower().startswith("en") for t in langs):
        return "OCR de Windows prêt (anglais) : lecture de secours possible sans RapidOCR."
    shown = ", ".join(langs) or "aucune"
    return ("OCR de Windows : langue anglaise absente (langues installées : " + shown + "). Pour l'ajouter : "
            "Paramètres > Heure et langue > Langue > Ajouter une langue > Anglais, avec la reconnaissance optique "
            "de caractères. Sinon, installez le moteur « OCR » (page Moteurs IA).")


def _png(arr: np.ndarray, path: Path) -> None:
    from PySide6.QtGui import QImage

    a = np.ascontiguousarray(arr.astype(np.uint8))
    h, w = a.shape[:2]
    img = QImage(a.data, w, h, w, QImage.Format_Grayscale8).copy()
    if h < 40:  # l'OCR de Windows lit mal les petits caractères : agrandissement
        img = img.scaledToHeight(h * 2)
    if not img.save(str(path), "PNG"):
        raise RuntimeError(f"Image impossible à écrire : {path}")


class WindowsOcrTool:
    """Même interface que l'outil RapidOCR (``ocr_lines``), sans relecture complète ni confiance."""

    def __init__(self):
        from .engines.base import EngineInfo

        self.info = EngineInfo(id="winocr", name="OCR de Windows", tagline="Lecture de secours",
                               description="Windows.Media.Ocr")

    def is_ready(self) -> bool:
        return available()

    def ocr_lines(self, files: list[Path], on_progress=None) -> dict[str, list]:
        out: dict[str, list] = {}
        with tempfile.TemporaryDirectory(dir=paths.temp_dir()) as td:
            rows = []
            for f in files:
                with np.load(f) as z:
                    for name in z.files:
                        png = Path(td) / f"{name}.png"
                        _png(z[name], png)
                        rows.append(f"{name}\t{png}")
            listing = Path(td) / "images.txt"
            listing.write_text("\n".join(rows), encoding="utf-8")
            if on_progress:
                on_progress(0.1, f"OCR de Windows : {len(rows)} lignes")
            data = json.loads(_run(_READ, str(listing), timeout=3600) or "{}")
        for name, text in (data or {}).items():
            out[name] = [str(text or ""), 0.9 if str(text or "").strip() else 0.0]
        if on_progress:
            on_progress(1.0, f"{len(out)} lignes lues")
        return out
