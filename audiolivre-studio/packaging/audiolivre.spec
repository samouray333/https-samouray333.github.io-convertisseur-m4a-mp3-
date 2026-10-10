# -*- mode: python ; coding: utf-8 -*-
# Spécification PyInstaller d'AudioLivre Studio (mode dossier, sans console).
# Usage : pyinstaller --noconfirm packaging/audiolivre.spec

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).resolve().parent
TOOLS = Path(SPECPATH).resolve() / "tools"
VERSION = os.environ.get("APP_VERSION", "1.0.0")
nums = tuple((list(map(int, VERSION.split("-")[0].split(".")[:3])) + [0, 0, 0, 0])[:4])

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=nums, prodvers=nums, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
    kids=[
        StringFileInfo([StringTable("040C04B0", [
            StringStruct("CompanyName", "AudioLivre"),
            StringStruct("FileDescription", "AudioLivre Studio — création de livres audio"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "AudioLivreStudio"),
            StringStruct("LegalCopyright", "Logiciel libre et gratuit"),
            StringStruct("OriginalFilename", "AudioLivreStudio.exe"),
            StringStruct("ProductName", "AudioLivre Studio"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
    ],
)

binaries = []
datas = [
    (str(ROOT / "audiolivre" / "resources"), "audiolivre/resources"),
    (str(ROOT / "audiolivre" / "worker" / "tts_worker.py"), "audiolivre/worker"),
]
# Outils externes (FFmpeg + ses DLL, uv) copiés tels quels dans _internal/tools
for exe_name in ("ffmpeg.exe", "ffprobe.exe", "uv.exe"):
    if not (TOOLS / exe_name).exists():
        print(f"ATTENTION : {TOOLS / exe_name} absent, il ne sera pas inclus")
if TOOLS.is_dir():
    for f in sorted(TOOLS.iterdir()):
        if f.suffix.lower() in (".exe", ".dll") and f.name.lower() != "ffplay.exe":
            datas.append((str(f), "tools"))

hiddenimports = collect_submodules("num2words") + [
    "win32com", "win32com.client", "pythoncom", "pywintypes", "win32crypt",
    "edge_tts", "aiohttp", "certifi",
    "ebooklib", "ebooklib.epub", "bs4", "lxml", "lxml.etree", "docx", "striprtf.striprtf", "pymupdf",
    "soundfile", "sounddevice", "soxr", "mutagen.mp4", "mutagen.id3", "mutagen.flac",
    "PySide6.QtSvg",
    "winrt.windows.media.ocr", "winrt.windows.graphics.imaging", "winrt.windows.storage.streams",
    "winrt.windows.globalization", "winrt.windows.foundation", "winrt.windows.foundation.collections",
]
try:
    hiddenimports += collect_submodules("winrt")
except Exception as exc:  # paquet absent hors Windows
    print("winrt non trouvé :", exc)

excludes = ["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "PyInstaller",
            "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
            "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtUiTools",
            "PySide6.QtLabsStyleKit", "PySide6.QtQmlFeatures", "PySide6.QtQuickTest"]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AudioLivreStudio",
    icon=str(ROOT / "audiolivre" / "resources" / "app.ico"),
    version=version_info,
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AudioLivreStudio")
