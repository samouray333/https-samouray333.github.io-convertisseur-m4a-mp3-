#!/usr/bin/env bash
# Publie le contenu de livraison/ comme nouvelle Release du dépôt privé : les applis installées la proposeront en mise à jour.
# Nécessite GitHub CLI (https://cli.github.com) connecté à ton compte : gh auth login
set -euo pipefail
cd "$(dirname "$0")"
REPO="samouray333/https-samouray333.github.io-convertisseur-m4a-mp3-"
VERSION=$(grep -oP 'const Version = "\K[^"]+' engine/core/model.go)
NOTES="${1:-Telechargys $VERSION}"

for f in "livraison/Telechargys-$VERSION-Installation.exe" "livraison/Telechargys-$VERSION.apk" livraison/SHA256SUMS.txt; do
  [ -f "$f" ] || { echo "Fichier manquant : $f (lance d'abord ./build.sh)"; exit 1; }
done
(cd livraison && sha256sum -c SHA256SUMS.txt)

gh release create "v$VERSION" --repo "$REPO" --title "Telechargys $VERSION" --notes "$NOTES" \
  "livraison/Telechargys-$VERSION-Installation.exe" \
  "livraison/Telechargys-$VERSION-Portable.zip" \
  "livraison/Telechargys-$VERSION.apk" \
  livraison/SHA256SUMS.txt
echo "Version v$VERSION publiée : les applis la proposeront au prochain démarrage."
