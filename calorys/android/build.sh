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
#   FLAVOR           apk (défaut, installation directe) ou play (Android App Bundle .aab pour le Play Store)
#   BUNDLETOOL       chemin de bundletool-all.jar (obligatoire si FLAVOR=play)
set -euo pipefail
cd "$(dirname "$0")"
HERE=$(pwd)
ANDROID_JAR=${ANDROID_JAR:?indique ANDROID_JAR}
ANDROID_RES_JAR=${ANDROID_RES_JAR:-$ANDROID_JAR}
KEYSTORE=${KEYSTORE:-$HERE/../keystore/calorys-release.jks}
KEY_ALIAS=${KEY_ALIAS:-calorys}
KS_PASS=${KS_PASS:?indique KS_PASS}
FLAVOR=${FLAVOR:-apk}
VERSION=$(grep -o 'versionName="[^"]*"' AndroidManifest.xml | cut -d'"' -f2)
OUT=build
[ "$FLAVOR" = play ] && OUT=build-play
rm -rf "$OUT" && mkdir -p "$OUT"/{gen,classes,assets/www}

# Manifeste : la version Play Store retire les droits réservés à d'autres types d'applis (lignes <!--apk-->)
# et active les lignes <!--play ... play-->.
MANIFEST=AndroidManifest.xml
if [ "$FLAVOR" = play ]; then
  MANIFEST="$OUT/AndroidManifest.xml"
  sed -e '/<!--apk-->/d' -e 's/<!--play \(.*\) play-->/\1/' AndroidManifest.xml > "$MANIFEST"
fi

echo "> Copie de l'appli web"
cp -r ../app/. "$OUT/assets/www/"
rm -f "$OUT/assets/www/sw.js" "$OUT/assets/www/js/vendor/neutralino.js" "$OUT/assets/www/js/vendor/sql-wasm.js" "$OUT/assets/www/js/vendor/sql-wasm.wasm"

echo "> Ressources (aapt2)"
aapt2 compile --dir res -o "$OUT/res.zip"
LINK_FMT=""
[ "$FLAVOR" = play ] && LINK_FMT="--proto-format"
aapt2 link $LINK_FMT -I "$ANDROID_RES_JAR" --manifest "$MANIFEST" -o "$OUT/base.apk" "$OUT/res.zip" \
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

if [ "$FLAVOR" = play ]; then
  BUNDLETOOL=${BUNDLETOOL:?indique BUNDLETOOL (bundletool-all.jar)}
  echo "> Module base et Android App Bundle"
  rm -rf "$OUT/module" && mkdir -p "$OUT/module/manifest" "$OUT/module/dex"
  (cd "$OUT/module" && unzip -q ../base.apk)
  mv "$OUT/module/AndroidManifest.xml" "$OUT/module/manifest/"
  cp "$OUT/classes.dex" "$OUT/module/dex/"
  (cd "$OUT/module" && zip -q -r -X ../base.zip .)
  AAB="$OUT/Calorys-$VERSION.aab"
  java -jar "$BUNDLETOOL" build-bundle --modules="$OUT/base.zip" --output="$AAB" --overwrite
  # Signature avec la clé d'importation (upload key) ; Google Play signe ensuite l'appli distribuée.
  jarsigner -sigalg SHA256withRSA -digestalg SHA-256 -keystore "$KEYSTORE" -storepass "$KS_PASS" -keypass "$KS_PASS" "$AAB" "$KEY_ALIAS" >/dev/null
  jarsigner -verify "$AAB" | tail -1
  java -jar "$BUNDLETOOL" validate --bundle="$AAB" >/dev/null
  echo "OK : android/$AAB"
  exit 0
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
