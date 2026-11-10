#!/usr/bin/env bash
# Reconstruit tout Telechargys : moteur, installeur Windows, version portable et APK Android.
# Prérequis : Go 1.24+, Node 20+, JDK 17+, SDK Android (ANDROID_HOME) avec NDK, Wine 32+64 bits (pour l'installeur depuis Linux).
set -euo pipefail
cd "$(dirname "$0")"
export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$(ls -d "$ANDROID_HOME"/ndk/* | tail -1)}"
export PATH="$PATH:$(go env GOPATH)/bin"

echo "== Tests du moteur =="
(cd engine && go test ./core/)

echo "== Moteur Windows et Linux =="
mkdir -p desktop/engine-bin/win desktop/engine-bin/linux
(cd engine && GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w -H windowsgui" -o ../desktop/engine-bin/win/telechargys-engine.exe ./cmd/telechargys-engine)
(cd engine && go build -trimpath -ldflags "-s -w" -o ../desktop/engine-bin/linux/telechargys-engine ./cmd/telechargys-engine)

echo "== Application Windows (installeur + portable) =="
(cd desktop && npm install --no-audit --no-fund && npx electron-builder --win nsis portable --x64)

echo "== Moteur Android (gomobile) =="
command -v gomobile >/dev/null || go install golang.org/x/mobile/cmd/gomobile@latest golang.org/x/mobile/cmd/gobind@latest
mkdir -p android/app/libs
(cd engine && gomobile bind -target=android/arm64,android/arm -androidapi 24 -ldflags "-s -w" -trimpath -o ../android/app/libs/engine.aar ./mobile)

echo "== APK Android =="
(cd android && ./gradlew --no-daemon assembleRelease)

mkdir -p livraison
cp desktop/dist/Telechargys-*-Installation.exe desktop/dist/Telechargys-*-Portable.exe livraison/
cp android/app/build/outputs/apk/release/app-release.apk "livraison/Telechargys-$(grep versionName android/app/build.gradle.kts | cut -d'"' -f2).apk"
ls -la livraison
