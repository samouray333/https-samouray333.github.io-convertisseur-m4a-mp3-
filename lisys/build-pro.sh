#!/bin/bash
# Construit la clé « Lisys Pro » (APK + AAB), signée avec la même clé que Lisys.
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD; B=$ROOT/build/pro
FRAMEWORK=${FRAMEWORK:-/usr/share/android-framework-res/framework-res.apk}
ANDROID_JAR=${ANDROID_JAR:-$HOME/deps/android-all.jar}
BUNDLETOOL=${BUNDLETOOL:-$HOME/deps/bundletool-1.18.3.jar}
source signing/signing.properties
rm -rf "$B"; mkdir -p "$B"/{gen,classes,dex,aab/base/manifest,aab/base/dex}
aapt2 compile --dir pro-key/res -o "$B/res.zip"
aapt2 link -o "$B/base.apk" -I "$FRAMEWORK" --manifest pro-key/AndroidManifest.xml --java "$B/gen" --min-sdk-version 26 --target-sdk-version 36 "$B/res.zip"
javac -nowarn -encoding UTF-8 --release 8 -Xlint:-options -cp "$ANDROID_JAR" -d "$B/classes" $(find pro-key/src "$B/gen" -name '*.java')
dalvik-exchange --dex --min-sdk-version=26 --output="$B/dex/classes.dex" "$B/classes"
cp "$B/base.apk" "$B/unsigned.apk"; (cd "$B/dex" && zip -q -j "$B/unsigned.apk" classes.dex)
zipalign -f -p 4 "$B/unsigned.apk" "$B/aligned.apk"
mkdir -p release
apksigner sign --ks "$KEYSTORE" --ks-key-alias "$KEY_ALIAS" --ks-pass "pass:$KEY_PASS" --key-pass "pass:$KEY_PASS" --out release/Lisys-Pro-cle-1.0.apk "$B/aligned.apk"
aapt2 link --proto-format -o "$B/proto.apk" -I "$FRAMEWORK" --manifest pro-key/AndroidManifest.xml --min-sdk-version 26 --target-sdk-version 36 "$B/res.zip"
(cd "$B/aab/base" && unzip -q ../../proto.apk && mv AndroidManifest.xml manifest/ && cp ../../dex/classes.dex dex/ && zip -q -r ../base.zip .)
rm -f release/Lisys-Pro-cle-1.0.aab
java -jar "$BUNDLETOOL" build-bundle --modules="$B/aab/base.zip" --output=release/Lisys-Pro-cle-1.0.aab
jarsigner -sigalg SHA256withRSA -digestalg SHA-256 -keystore "$KEYSTORE" -storepass "$KEY_PASS" -keypass "$KEY_PASS" release/Lisys-Pro-cle-1.0.aab "$KEY_ALIAS" >/dev/null
ls -la release/Lisys-Pro-cle-1.0.*
