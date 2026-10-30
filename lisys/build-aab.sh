#!/bin/bash
# Construit l'App Bundle (.aab) signé pour le Google Play Store. À lancer après ./build.sh (il réutilise le dex).
# Outils : aapt2, bundletool (jar), jarsigner (JDK).
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD
B=$ROOT/build
BUNDLETOOL=${BUNDLETOOL:-$HOME/deps/bundletool-1.18.3.jar}
FRAMEWORK=${FRAMEWORK:-/usr/share/android-framework-res/framework-res.apk}
VERSION_CODE=$(grep -o 'versionCode="[0-9]*"' app/AndroidManifest.xml | grep -o '[0-9]*')
VERSION_NAME=$(grep -o 'versionName="[^"]*"' app/AndroidManifest.xml | sed 's/.*="\(.*\)"/\1/')
source signing/signing.properties
[ -f "$B/dex/classes.dex" ] || { echo "Lance d'abord ./build.sh"; exit 1; }

echo "== Ressources au format App Bundle"
rm -rf "$B/aab" && mkdir -p "$B/aab/base/manifest" "$B/aab/base/dex"
aapt2 link --proto-format -o "$B/aab/proto.apk" -I "$FRAMEWORK" --manifest app/AndroidManifest.xml \
  -A "$B/pdfbox/assets" -A app/assets --min-sdk-version 26 --target-sdk-version 36 \
  --version-code "$VERSION_CODE" --version-name "$VERSION_NAME" "$B/res/res.zip"
(cd "$B/aab/base" && unzip -q ../proto.apk && mv AndroidManifest.xml manifest/)
cp "$B"/dex/classes*.dex "$B/aab/base/dex/"
(cd "$B/aab/base" && zip -q -r ../base.zip .)

echo "== App Bundle"
mkdir -p release
OUT=release/Lisys-$VERSION_NAME.aab
rm -f "$OUT"
java -jar "$BUNDLETOOL" build-bundle --modules="$B/aab/base.zip" --output="$OUT"
jarsigner -sigalg SHA256withRSA -digestalg SHA-256 -keystore "$KEYSTORE" -storepass "$KEY_PASS" -keypass "$KEY_PASS" "$OUT" "$KEY_ALIAS" >/dev/null
java -jar "$BUNDLETOOL" validate --bundle="$OUT" | head -5
jarsigner -verify "$OUT" | tail -1
ls -la "$OUT"
