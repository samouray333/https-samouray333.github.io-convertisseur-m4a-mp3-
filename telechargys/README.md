# Telechargys

Gestionnaire de téléchargements accéléré pour **Windows** et **Android** (marque QMTech).
Même moteur et même interface sur les deux plateformes, 100 % local : pas de serveur, pas de compte, pas d'abonnement.

## Ce que fait l'application

| Fonction | Ordinateur | Téléphone |
|---|---|---|
| Accélération : jusqu'à 32 connexions par fichier, découpage dynamique des segments | oui | oui |
| Pause, reprise, reprise après coupure réseau ou fermeture de l'appli | oui | oui |
| Files d'attente, téléchargements simultanés réglables, planificateur (heure de début / fin, jours) | oui | oui (appli ouverte) |
| Action en fin de file : quitter, veille, veille prolongée, extinction | oui | non |
| Catégories automatiques (Vidéos, Musique, Archives, Programmes, Documents, Images) et dossiers associés | oui | oui |
| Limiteur de débit global et par téléchargement | oui | oui |
| Téléchargement par lot (motif `[001-120]`, liste collée, fichier .txt) | oui | oui |
| Aspirateur de site (profondeur, même site, filtre par type) | oui | oui |
| Flux vidéo HLS (.m3u8) : choix de la qualité, déchiffrement AES-128, conversion en MP4 sans réencodage | oui | oui |
| Flux vidéo DASH (.mpd) : choix de la qualité, vidéo et son fusionnés en un seul MP4 sans réencodage | oui | oui |
| Bouton « Télécharger cette vidéo » posé sur les vidéos des pages | extension | navigateur intégré |
| Fenêtre de progression par téléchargement (segments, vitesse) et fenêtre « Téléchargement terminé » | oui | notification |
| Doublons : « Ce lien est déjà dans la liste », avec choix de retélécharger ou d'afficher l'existant | oui | oui |
| Relance automatique des téléchargements en erreur (délai réglable, 5 essais) | oui | oui |
| Sites exclus de la capture, Alt + clic pour laisser le navigateur télécharger | extension | sans objet |
| Export / import de listes d'adresses (.txt) | oui | oui |
| Lien copié détecté au retour dans l'appli | surveillance continue | oui |
| FTP (reprise incluse) | oui | oui |
| Actualiser l'adresse d'un lien expiré en gardant la progression | oui | oui |
| Identifiants par site, cookies, Referer, User-Agent, proxy HTTP / SOCKS5 | oui | oui |
| Vérification d'intégrité MD5 / SHA-1 / SHA-256 | oui | oui |
| Capture depuis le navigateur | extension Chrome / Edge / Brave / Opera / Firefox | « Partager », « Ouvrir avec » et navigateur intégré |
| Détection des vidéos et sons des pages | extension | navigateur intégré |
| Surveillance du presse-papiers | oui | à l'ouverture de « Ajouter » |
| Zone de notification, lancement au démarrage, glisser-déposer de liens, raccourcis clavier | oui | sans objet |
| Service au premier plan avec notification de progression, option Wi-Fi uniquement | sans objet | oui |
| Commande antivirus sur chaque fichier terminé | oui | non |
| Sauvegarde / restauration (JSON), export de l'historique (CSV) | oui | oui |
| Thème clair / sombre | oui | oui |

### Limites assumées

- **Pas de YouTube, Netflix, Prime Video, Disney+** ni d'autres flux protégés par DRM : c'est interdit par leurs conditions et techniquement verrouillé. Les flux en direct ne sont pas pris en charge non plus.
- Vidéo et son séparés dans des codecs que le MP4 n'accepte pas sans réencodage (VP9, AV1, Opus, souvent en WebM) : les deux pistes sont enregistrées côte à côte (`nom.webm` et `nom.audio.webm`). Les flux H.264 / H.265 + AAC (la grande majorité) donnent un seul MP4.
- DASH : seule la période principale d'un manifeste à plusieurs périodes est téléchargée (les autres sont en général des publicités).
- Extension navigateur : à charger en « mode développeur » (elle n'est pas publiée sur les boutiques). Sur Firefox, un module non signé doit être rechargé à chaque démarrage du navigateur.
- Android : pas d'intégration dans Chrome mobile (Android ne le permet pas), d'où le navigateur intégré et le partage. Android 15 limite ce type de service d'arrière-plan à 6 heures par jour : au-delà, l'appli met proprement en pause.
- Serveur sans reprise (pas d'en-tête Range) : une seule connexion, et une pause fait repartir de zéro (l'appli l'indique).

## Où sont les fichiers

- **Windows** : `Téléchargements\Telechargys\<Catégorie>` par défaut (modifiable dans Réglages). Données de l'appli : `%APPDATA%\Telechargys\moteur\state.json`.
- **Android** : `Téléchargements/Telechargys/<Catégorie>`. Données de l'appli dans son espace privé.
- Fichier en cours : `nom.ext.tlpart` à côté du fichier final (dossier `nom.ext.tlparts` pour un flux HLS).

## Organisation du code

```
telechargys/
  engine/                moteur commun, écrit en Go
    core/                téléchargement segmenté (http.go), HLS (hls.go), FTP (ftp.go), files et planificateur (manager.go),
                         aspirateur (grab.go), API locale + sécurité (api.go), tests (engine_test.go)
    ui/web/              interface (HTML / CSS / JS sans dépendance), embarquée dans le moteur
    cmd/telechargys-engine/   exécutable du moteur pour l'ordinateur
    mobile/              façade pour Android (gomobile)
  desktop/               application Windows (Electron) : fenêtre, zone de notification, presse-papiers, installeur NSIS
  android/               application Android (Kotlin) : écran principal, service au premier plan, navigateur intégré
  extension/             extension navigateur (Chrome / Edge) ; extension/firefox pour Firefox
  build.sh               reconstruit tout
```

Le moteur écoute uniquement sur `127.0.0.1` (port 47615 et suivants), exige un jeton secret, refuse les origines web étrangères et les attaques par « DNS rebinding ». L'extension doit être autorisée une fois depuis l'application.

## Reconstruire

Prérequis : Go 1.24+, Node 20+, JDK 17+, SDK Android avec NDK, et Wine (32 et 64 bits) si l'installeur Windows est fabriqué depuis Linux.

```bash
./build.sh            # tests + installeur Windows + portable + APK, copiés dans livraison/
```

Étape par étape :

```bash
cd engine && go test ./core/                      # tests du moteur
cd desktop && npm install && npm run dist         # Windows : dist/Telechargys-x.y.z-Installation.exe et -Portable.exe
cd engine && gomobile bind -target=android/arm64,android/arm -androidapi 24 -o ../android/app/libs/engine.aar ./mobile
cd android && ./gradlew assembleRelease           # app/build/outputs/apk/release/app-release.apk
```

## Signature Android (important)

Toutes les versions doivent être signées avec **la même clé**, sinon la mise à jour ne s'installe pas par-dessus l'ancienne.

- Fichier : `android/keystore/telechargys-release.jks`
- Alias : `telechargys`
- Mots de passe : dans `android/keystore/keystore.properties`

Ces deux fichiers ne sont **pas** dans le dépôt Git (dépôt public) : ils sont fournis dans l'archive du code source. Garde-les précieusement et remets-les dans `android/keystore/` avant chaque build. Sans eux, Gradle produit une APK non signée.

À chaque nouvelle version : augmenter `versionCode` et `versionName` dans `android/app/build.gradle.kts`, `version` dans `desktop/package.json` et `Version` dans `engine/core/model.go`.

## Licences des composants

Go et ses bibliothèques (BSD), gomedia (MIT), jlaffaye/ftp (ISC), Electron (MIT, embarque Chromium et sa bibliothèque ffmpeg en LGPL), AndroidX (Apache 2.0). Aucun composant GPL : l'application peut être distribuée ou vendue. Le nom, l'icône et le code sont originaux (aucun élément repris d'Internet Download Manager).
