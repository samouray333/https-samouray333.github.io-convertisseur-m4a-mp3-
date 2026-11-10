#!/usr/bin/env bash
# Reconstruit tout Telechargys et dépose les fichiers dans livraison/ :
#   Telechargys-X-Installation.exe   installeur Windows (version native WebView2, ~3 Mo)
#   Telechargys-X-Portable.zip       version portable Windows (données à côté du programme)
#   Telechargys-X.apk                Android (signée avec android/keystore)
#   Telechargys-extension-*.zip      extensions Chrome/Edge et Firefox
#   SHA256SUMS.txt                   empreintes, OBLIGATOIRES dans chaque Release pour la mise à jour automatique
#
# Options (variables d'environnement) :
#   CLASSIQUE=1        construit aussi l'ancienne version Electron (portable, secours)
#   TY_SIGN_PFX=...    certificat de signature de code (.pfx) ; TY_SIGN_PASS = son mot de passe
# Fichier facultatif, jamais envoyé sur GitHub : windows/update-token.txt (jeton GitHub en lecture seule
# intégré aux applis pour les mises à jour depuis le dépôt privé ; sinon chacun le saisit dans les Réglages).
#
# Prérequis : Go 1.24+, JDK 17+, SDK Android + NDK (ANDROID_HOME), makensis, zip ; Node 20+ et Wine pour CLASSIQUE=1.
set -euo pipefail
cd "$(dirname "$0")"
export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$(ls -d "$ANDROID_HOME"/ndk/* | tail -1)}"
export PATH="$PATH:$(go env GOPATH)/bin"

VERSION=$(grep -oP 'const Version = "\K[^"]+' engine/core/model.go)
LDX=""
if [ -s windows/update-token.txt ]; then
  LDX="-X telechargys/engine/core.BuiltinToken=$(tr -d ' \r\n' < windows/update-token.txt)"
  echo "Jeton de mise à jour intégré (windows/update-token.txt)."
fi
OUT=livraison
mkdir -p "$OUT"
rm -f "$OUT"/Telechargys-*

echo "== Tests du moteur =="
(cd engine && go test ./core/)

echo "== Windows : programme natif =="
command -v go-winres >/dev/null || go install github.com/tc-hib/go-winres@latest
(cd engine/cmd/telechargys-win && go-winres make --in winres/winres.json --out rsrc --arch amd64 --file-version "$VERSION.0" --product-version "$VERSION.0")
STAGE=$(mktemp -d)
mkdir -p "$STAGE/extension"
(cd engine && GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w -H windowsgui $LDX" -o "$STAGE/Telechargys.exe" ./cmd/telechargys-win)
cp -r extension/manifest.json extension/background.js extension/content.js extension/popup.html extension/popup.js extension/icons extension/firefox "$STAGE/extension/"

sign() { # signature de code facultative (évite l'alerte SmartScreen « éditeur inconnu » une fois la réputation acquise)
  [ -n "${TY_SIGN_PFX:-}" ] || return 0
  osslsigncode sign -pkcs12 "$TY_SIGN_PFX" -pass "${TY_SIGN_PASS:-}" -n "Telechargys" -i "https://qmtech.app" \
    -t http://timestamp.digicert.com -h sha256 -in "$1" -out "$1.signe" && mv "$1.signe" "$1"
  echo "Signé : $1"
}
sign "$STAGE/Telechargys.exe"

echo "== Windows : installeur =="
makensis -V2 -DVERSION="$VERSION" -DSRC="$STAGE" -DOUT="$PWD/$OUT/Telechargys-$VERSION-Installation.exe" windows/telechargys.nsi
sign "$OUT/Telechargys-$VERSION-Installation.exe"

echo "== Windows : portable =="
printf 'Ce fichier active le mode portable : les réglages et la liste restent dans le dossier « donnees ».\r\n' > "$STAGE/portable.txt"
(cd "$STAGE" && zip -qr "$OLDPWD/$OUT/Telechargys-$VERSION-Portable.zip" Telechargys.exe portable.txt extension)
rm -rf "$STAGE"

echo "== Android =="
command -v gomobile >/dev/null || go install golang.org/x/mobile/cmd/gomobile@latest golang.org/x/mobile/cmd/gobind@latest
mkdir -p android/app/libs
(cd engine && gomobile bind -target=android/arm64,android/arm -androidapi 24 -ldflags "-s -w $LDX" -trimpath -o ../android/app/libs/engine.aar ./mobile)
(cd android && ./gradlew --no-daemon -q assembleRelease)
cp android/app/build/outputs/apk/release/app-release.apk "$OUT/Telechargys-$VERSION.apk"

echo "== Extensions =="
(cd extension && zip -qr "../$OUT/Telechargys-extension-chrome.zip" manifest.json background.js content.js popup.html popup.js icons)
(cd extension/firefox && zip -qr "../../$OUT/Telechargys-extension-firefox.zip" .)

if [ "${CLASSIQUE:-}" = "1" ]; then
  echo "== Ancienne version Electron (secours) =="
  mkdir -p desktop/engine-bin/win
  (cd engine && GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w -H windowsgui $LDX" -o ../desktop/engine-bin/win/telechargys-engine.exe ./cmd/telechargys-engine)
  (cd desktop && npm install --no-audit --no-fund && npx electron-builder --win portable --x64)
  cp desktop/dist/Telechargys-classique-*-Portable.exe "$OUT/"
fi

echo "== Empreintes =="
(cd "$OUT" && sha256sum Telechargys-* > SHA256SUMS.txt && cat SHA256SUMS.txt)
ls -la "$OUT"
echo "Pour publier la mise à jour : ./publier-version.sh (ou voir README, section « Publier une version »)."
