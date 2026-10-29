#!/bin/bash
# Construit Lisys pour Windows (exe, installeur NSIS, version portable), depuis Linux ou Windows (Git Bash).
# Outils : .NET SDK 8 (dotnet), NSIS 3 (makensis), zip.
set -euo pipefail
cd "$(dirname "$0")"
VERSION=$(grep -o '<Version>[^<]*' Lisys/Lisys.csproj | sed 's/<Version>//')
rm -rf dist
mkdir -p dist/Lisys
dotnet build Lisys/Lisys.csproj -c Release -nologo -v quiet
cp Lisys/bin/Release/net48/*.dll Lisys/bin/Release/net48/Lisys.exe Lisys/bin/Release/net48/Lisys.exe.config dist/Lisys/
cp ../README.md dist/Lisys/LISEZMOI.md 2>/dev/null || true
makensis -V2 -DVERSION="$VERSION" -DSOURCE="../dist/Lisys" -DOUTFILE="../dist/Lisys-$VERSION-installation.exe" installer/lisys.nsi
(cd dist && zip -qr "Lisys-$VERSION-portable.zip" Lisys)
ls -la dist
