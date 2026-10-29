#!/bin/bash
# Construit l'APK signée de Lisys sans Android Studio ni Gradle.
# Outils : JDK 17+, aapt2, zipalign, apksigner, dalvik-exchange (dx)
#   Ubuntu/Debian : sudo apt install android-sdk android-framework-res apksigner dalvik-exchange
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD
B=$ROOT/build
VERSION_CODE=$(grep -o 'versionCode="[0-9]*"' app/AndroidManifest.xml | grep -o '[0-9]*')
VERSION_NAME=$(grep -o 'versionName="[^"]*"' app/AndroidManifest.xml | sed 's/.*="\(.*\)"/\1/')

FRAMEWORK=${FRAMEWORK:-/usr/share/android-framework-res/framework-res.apk}   # ressources Android 14
ANDROID_JAR=${ANDROID_JAR:-$HOME/deps/android-all.jar}                        # API Android 14 pour javac
if [ ! -f "$ANDROID_JAR" ]; then
  mkdir -p "$(dirname "$ANDROID_JAR")"
  curl -fL -o "$ANDROID_JAR" https://repo1.maven.org/maven2/org/robolectric/android-all/14-robolectric-10818077/android-all-14-robolectric-10818077.jar
fi
source signing/signing.properties

rm -rf "$B"; mkdir -p "$B"/{res,gen,classes,dex,pdfbox}
echo "== Bibliothèques"
(cd "$B/pdfbox" && unzip -q "$ROOT/libs/pdfbox-android-2.0.27.0.aar")
LIBS="$ROOT/libs/jsoup-1.13.1.jar:$B/pdfbox/classes.jar"

echo "== Ressources"
aapt2 compile --dir app/res -o "$B/res/res.zip"
aapt2 link -o "$B/base.apk" -I "$FRAMEWORK" --manifest app/AndroidManifest.xml \
  --java "$B/gen" -A "$B/pdfbox/assets" --min-sdk-version 26 --target-sdk-version 34 \
  --version-code "$VERSION_CODE" --version-name "$VERSION_NAME" "$B/res/res.zip"

echo "== Compilation Java"
find app/src "$B/gen" -name '*.java' > "$B/sources.txt"
javac -nowarn -encoding UTF-8 --release 8 -Xlint:-options -cp "$ANDROID_JAR:$LIBS" -d "$B/classes" @"$B/sources.txt"

echo "== Dex"
dalvik-exchange --dex --min-sdk-version=26 --multi-dex --output="$B/dex" "$B/classes" "$ROOT/libs/jsoup-1.13.1.jar" "$B/pdfbox/classes.jar"

echo "== Assemblage"
cp "$B/base.apk" "$B/unsigned.apk"
(cd "$B/dex" && zip -q -j "$B/unsigned.apk" classes*.dex)
zipalign -f -p 4 "$B/unsigned.apk" "$B/aligned.apk"
mkdir -p release
OUT=release/Lisys-$VERSION_NAME.apk
apksigner sign --ks "$KEYSTORE" --ks-key-alias "$KEY_ALIAS" --ks-pass "pass:$KEY_PASS" --key-pass "pass:$KEY_PASS" \
  --out "$OUT" "$B/aligned.apk"
apksigner verify --print-certs "$OUT" | head -3
ls -la "$OUT"
