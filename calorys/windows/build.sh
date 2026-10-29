#!/usr/bin/env bash
# Construit Calorys pour Windows : exe Neutralino + installeur NSIS + version portable.
# Prérequis : neu (npm i -g @neutralinojs/neu), makensis, zip ; wine + rcedit pour l'icône de l'exe (facultatif).
#   NEU_ZIP   archive neutralinojs-v6.9.0.zip (binaires officiels, GitHub releases)
#   RCEDIT    chemin de rcedit-x64.exe (facultatif)
#   SIGN_PFX  certificat de signature de code .pfx (facultatif) + SIGN_PASS : signe l'exe,
#             le désinstalleur et l'installeur (voir sign.sh)
set -euo pipefail
cd "$(dirname "$0")"
NEU_ZIP=${NEU_ZIP:?indique NEU_ZIP}
VERSION=$(grep -o '"version": "[^"]*"' neutralino.config.json | cut -d'"' -f4)
B=build
rm -rf "$B" && mkdir -p "$B/project/bin" "$B/dist"

echo "> Projet Neutralino"
cp neutralino.config.json "$B/project/"
cp -r ../app "$B/project/resources"
rm -f "$B/project/resources/sw.js"
sed -i 's#<!--NEUTRALINO-->#<script src="js/vendor/neutralino.js"></script>#' "$B/project/resources/index.html"
unzip -q -o "$NEU_ZIP" 'neutralino-win_x64.exe' 'neutralino-linux_x64' -d "$B/project/bin"
chmod +x "$B/project/bin/neutralino-linux_x64"
(cd "$B/project" && neu build > /dev/null)

APPDIR="$B/project/dist/Calorys"
cp "$APPDIR/Calorys-win_x64.exe" "$B/dist/Calorys.exe"
cp "$APPDIR/resources.neu" "$B/dist/resources.neu"
cp "$APPDIR/Calorys-linux_x64" "$B/Calorys-linux_x64"

if [ -n "${RCEDIT:-}" ] && command -v wine > /dev/null; then
  echo "> Icône et informations de version (rcedit)"
  WINEDEBUG=-all wine "$RCEDIT" "$B/dist/Calorys.exe" --set-icon calorys.ico \
    --set-version-string ProductName Calorys --set-version-string CompanyName QMTech \
    --set-version-string FileDescription "Calorys - compteur de calories" \
    --set-version-string LegalCopyright QMTech --set-file-version "$VERSION" --set-product-version "$VERSION" 2>/dev/null
fi

SIGNDEF=()
if [ -n "${SIGN_PFX:-}" ]; then
  echo "> Signature de l'exe"
  ./sign.sh "$B/dist/Calorys.exe"
  SIGNDEF=(-DSIGN="$(pwd)/sign.sh")
fi

echo "> Installeur NSIS"
makensis -V2 -WX -DVERSION="$VERSION" -DOUTFILE="$B/Calorys-Setup-$VERSION.exe" "${SIGNDEF[@]}" -NOCD installer.nsi > /dev/null
# makensis résout File relativement au script : on le lance depuis le dossier windows/ avec dist dans build/.
echo "> Version portable"
rm -f "$B/Calorys-Portable-$VERSION.zip"
(cd "$B/dist" && mkdir -p Calorys-Portable && cp Calorys.exe resources.neu Calorys-Portable/ && cp ../../calorys.ico Calorys-Portable/ \
  && printf 'Calorys %s (version portable)\r\n\r\nLance Calorys.exe. Aucune installation nécessaire.\r\nTes données sont enregistrées dans %%APPDATA%%\\Calorys\\data.json.\r\nNécessite Microsoft Edge WebView2 (inclus dans Windows 10 à jour et Windows 11).\r\n' "$VERSION" > Calorys-Portable/LISEZMOI.txt \
  && zip -q -r "../Calorys-Portable-$VERSION.zip" Calorys-Portable && rm -rf Calorys-Portable)
ls -la "$B"/*.exe "$B"/*.zip
