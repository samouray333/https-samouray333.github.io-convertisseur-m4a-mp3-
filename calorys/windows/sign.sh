#!/usr/bin/env bash
# Signe un exécutable Windows (Authenticode SHA-256, horodaté) avec osslsigncode.
# Usage : SIGN_PFX=certificat.pfx SIGN_PASS=motdepasse ./sign.sh fichier.exe
# Horodatage : SIGN_TS (défaut http://timestamp.digicert.com). Sans horodatage, la
# signature expire avec le certificat ; avec, elle reste valide.
set -euo pipefail
f="$1"
: "${SIGN_PFX:?indique SIGN_PFX}"
TS=${SIGN_TS:-http://timestamp.digicert.com}
args=(sign -pkcs12 "$SIGN_PFX" -pass "${SIGN_PASS:-}" -h sha256 -n "Calorys" -i "https://github.com/samouray333" -in "$f" -out "$f.signed")
if [ "$TS" != "none" ]; then args+=(-ts "$TS"); fi
osslsigncode "${args[@]}" > /dev/null
mv "$f.signed" "$f"
echo "signé : $f"
