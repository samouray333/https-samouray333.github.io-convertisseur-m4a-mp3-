# Extrays 1.0 (Echo Matras)

Appli Android pour couper des extraits de chansons, 100 % hors ligne.

## Fonctions
- Ouvre MP3, M4A, AAC, WAV, OGG, Opus, FLAC (tout ce que le téléphone sait décoder).
- Forme d'onde zoomable (pincer, boutons + / −), barre d'aperçu de toute la chanson.
- Début et fin : glisser les poignées D et F, saisir le temps (1:23.4 ou 83.4), ajuster à ±0,1 s / ±1 s,
  ou bouton **Ici** pour placer la borne à la position de lecture (pratique en écoutant).
- Écoute de l'extrait avec les fondus, en boucle si besoin.
- Fondu au début / à la fin (0 à 10 s), volume (−12 à +12 dB) ou normalisation à −1 dBFS.
- Export MP3 128 / 192 / 320 kbit/s ou WAV 16 bits, nom de fichier automatique modifiable.
- Fichiers enregistrés dans **Documents/Extrays** (repli : Android/data/com.echomatras.extrays/files/Extrays).
- Historique des extraits : écouter, partager, supprimer.

## Fichiers
- `src/index.html`, `src/style.css` : interface.
- `src/app.js` : logique (chargement, forme d'onde, gestes, lecture, enregistrement, historique).
- `src/audio.js` : découpe, fondus, volume, rééchantillonnage, encodeur WAV.
- `src/encoder-worker.js` : encodage MP3 (lamejs) en arrière-plan.
- `assets/icon.svg` : icône.
- `build.mjs` : construit `www/` (esbuild).
- `android/` : projet Android (Capacitor 7).
- `release/Extrays-1.0.apk` : APK signée.

## Reconstruire
```
npm install
node build.mjs
npx cap sync android
cd android && ./gradlew assembleRelease
# APK : android/app/build/outputs/apk/release/app-release.apk
```
Prérequis : Node 18+, JDK 17+, SDK Android (platform 35, build-tools 35), `android/local.properties` avec `sdk.dir=...`.

## Signature
La clé est dans `keystore/` (non versionnée, fournie à part dans le zip des sources) :
- fichier `keystore/extrays-release.jks`, alias `extrays`, mots de passe dans `keystore/keystore.properties`.
Toutes les mises à jour doivent être signées avec cette clé, sinon Android refusera l'installation par-dessus.
À chaque version : incrémenter `versionCode` et `versionName` dans `android/app/build.gradle`.

## Licences
- Capacitor : MIT.
- lamejs (encodeur MP3) : LGPL, utilisé tel quel comme fichier séparé (`lame.min.js`), compatible avec une appli vendue.
