# -*- mode: python ; coding: utf-8 -*-
# Spécification PyInstaller de Doublys (mode dossier, sans console).
# Usage : pyinstaller --noconfirm packaging/doublys.spec

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).resolve().parent
TOOLS = Path(SPECPATH).resolve() / "tools"
VERSION = os.environ.get("APP_VERSION", "1.2.0")
nums = tuple((list(map(int, VERSION.split("-")[0].split(".")[:3])) + [0, 0, 0, 0])[:4])

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=nums, prodvers=nums, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
    kids=[
        StringFileInfo([StringTable("040C04B0", [
            StringStruct("CompanyName", "Echo Matras"),
            StringStruct("FileDescription", "Doublys — doublage vidéo anglais vers français"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "Doublys"),
            StringStruct("LegalCopyright", "Echo Matras"),
            StringStruct("OriginalFilename", "Doublys.exe"),
            StringStruct("ProductName", "Doublys"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
    ],
)

datas = [
    (str(ROOT / "doublys" / "resources"), "doublys/resources"),
    (str(ROOT / "doublys" / "worker" / "tts_worker.py"), "doublys/worker"),
]
# Outils externes (FFmpeg LGPL + ses DLL, uv) copiés tels quels dans _internal/tools
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
    "soundfile", "sounddevice", "soxr",
    "PySide6.QtSvg",
]

excludes = ["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "PyInstaller", "torch",
            "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
            "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtUiTools",
            "PySide6.QtLabsStyleKit", "PySide6.QtQmlFeatures", "PySide6.QtQuickTest"]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
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
    name="Doublys",
    icon=str(ROOT / "doublys" / "resources" / "app.ico"),
    version=version_info,
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Doublys")
