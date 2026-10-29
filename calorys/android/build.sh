#!/usr/bin/env bash
# Construit l'APK Android de Calorys sans Gradle (aapt2 + javac + d8/dx + apksigner).
#
# Variables :
#   ANDROID_JAR      android.jar pour compiler le Java (API 35 conseillé)
#   ANDROID_RES_JAR  android.jar pour lier les ressources (défaut : ANDROID_JAR ; API 33 si aapt2 est ancien)
#   KEYSTORE         fichier .jks de signature (défaut : ../keystore/calorys-release.jks)
#   KS_PASS          mot de passe du keystore (obligatoire)
#   KEY_ALIAS        alias de la clé (défaut : calorys)
#   D8               commande d8 (Android SDK build-tools) ; sinon dalvik-exchange (dx) est utilisé
set -euo pipefail
cd "$(dirname "$0")"
HERE=$(pwd)
ANDROID_JAR=${ANDROID_JAR:?indique ANDROID_JAR}
ANDROID_RES_JAR=${ANDROID_RES_JAR:-$ANDROID_JAR}
KEYSTORE=${KEYSTORE:-$HERE/../keystore/calorys-release.jks}
KEY_ALIAS=${KEY_ALIAS:-calorys}
KS_PASS=${KS_PASS:?indique KS_PASS}
VERSION=$(grep -o 'versionName="[^"]*"' AndroidManifest.xml | cut -d'"' -f2)
OUT=build
rm -rf "$OUT" && mkdir -p "$OUT"/{gen,classes,assets/www}

echo "> Copie de l'appli web"
cp -r ../app/. "$OUT/assets/www/"
rm -f "$OUT/assets/www/sw.js" "$OUT/assets/www/js/vendor/neutralino.js"

echo "> Ressources (aapt2)"
aapt2 compile --dir res -o "$OUT/res.zip"
aapt2 link -I "$ANDROID_RES_JAR" --manifest AndroidManifest.xml -o "$OUT/base.apk" "$OUT/res.zip" \
  --java "$OUT/gen" -A "$OUT/assets" --auto-add-overlay -0 json -0 js

echo "> Compilation Java"
javac --release 8 -nowarn -Xlint:-options -encoding UTF-8 -classpath "$ANDROID_JAR" -d "$OUT/classes" \
  $(find src "$OUT/gen" -name '*.java')

echo "> Dex"
if [ -n "${D8:-}" ]; then
  $D8 --release --min-api 26 --lib "$ANDROID_JAR" --output "$OUT" $(find "$OUT/classes" -name '*.class')
else
  dalvik-exchange --dex --min-sdk-version=26 --output="$OUT/classes.dex" "$OUT/classes"
fi

echo "> Assemblage, alignement, signature"
cp "$OUT/base.apk" "$OUT/unsigned.apk"
(cd "$OUT" && zip -q -X unsigned.apk classes.dex)
zipalign -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
apksigner sign --ks "$KEYSTORE" --ks-key-alias "$KEY_ALIAS" --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
  --out "$OUT/Calorys-$VERSION.apk" "$OUT/aligned.apk"
apksigner verify "$OUT/Calorys-$VERSION.apk"
echo "OK : android/$OUT/Calorys-$VERSION.apk"
