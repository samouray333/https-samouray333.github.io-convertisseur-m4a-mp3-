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
| Actualiser l'adresse d'un lien expiré en gardant la progression, en collant le lien ou en recliquant dessus dans le navigateur | oui | oui (partage ou navigateur intégré) |
| Clic droit : télécharger les liens sélectionnés ou tous les fichiers de la page, avec fenêtre de choix | extension | partage de plusieurs liens |
| Identifiants par site, cookies, Referer, User-Agent, proxy HTTP / SOCKS5 | oui | oui |
| Vérification d'intégrité MD5 / SHA-1 / SHA-256 | oui | oui |
| Capture depuis le navigateur | extension Chrome / Edge / Brave / Opera / Firefox | « Partager », « Ouvrir avec » et navigateur intégré |
| Détection des vidéos et sons des pages | extension | navigateur intégré |
| Surveillance du presse-papiers | oui | à l'ouverture de « Ajouter » |
| Zone de notification, lancement au démarrage, glisser-déposer de liens, raccourcis clavier | oui | sans objet |
| Service au premier plan avec notification de progression, option Wi-Fi uniquement | sans objet | oui |
| Commande antivirus sur chaque fichier terminé | oui | non |
| Sauvegarde / restauration (JSON), export de l'historique (CSV) | oui | oui |
| Mises à jour automatiques depuis le dépôt GitHub privé, fichier vérifié (SHA-256) | oui | oui |
| Thème clair / sombre | oui | oui |

### Limites assumées

- **Pas de YouTube, Netflix, Prime Video, Disney+** ni d'autres flux protégés par DRM : c'est interdit par leurs conditions et techniquement verrouillé. Les flux en direct ne sont pas pris en charge non plus.
- Vidéo et son séparés dans des codecs que le MP4 n'accepte pas sans réencodage (VP9, AV1, Opus, souvent en WebM) : les deux pistes sont enregistrées côte à côte (`nom.webm` et `nom.audio.webm`). Les flux H.264 / H.265 + AAC (la grande majorité) donnent un seul MP4.
- DASH : seule la période principale d'un manifeste à plusieurs périodes est téléchargée (les autres sont en général des publicités).
- Extension navigateur : en attendant sa publication « non répertoriée » (invisible dans les boutiques, installable par lien), elle se charge en « mode développeur ». Marche à suivre, textes, captures et politique de confidentialité : `extension/PUBLICATION.md`.
- Android : pas d'intégration dans Chrome mobile (Android ne le permet pas), d'où le navigateur intégré et le partage. Android 15 limite ce type de service d'arrière-plan à 6 heures par jour : au-delà, l'appli met proprement en pause.
- Serveur sans reprise (pas d'en-tête Range) : une seule connexion, et une pause fait repartir de zéro (l'appli l'indique).

## Où sont les fichiers

- **Windows (installé)** : programme dans `%LOCALAPPDATA%\QMTech\Telechargys`. Fichiers téléchargés dans `Téléchargements\Telechargys\<Catégorie>` par défaut (modifiable dans Réglages). Liste et réglages : `%APPDATA%\Telechargys\moteur\state.json` (conservés à la désinstallation et repris par les mises à jour).
- **Windows (portable)** : tout reste dans le dossier dézippé (`donnees\`, `Téléchargements\`), grâce au fichier `portable.txt` posé à côté du programme.
- **Android** : `Téléchargements/Telechargys/<Catégorie>`. Données de l'appli dans son espace privé.
- Fichier en cours : `nom.ext.tlpart` à côté du fichier final (dossier `nom.ext.tlparts` pour un flux vidéo).

## Version Windows native

Depuis la 1.3.0, la version Windows est un seul programme Go de 9 Mo (installeur de 3 Mo) : moteur, interface affichée par
**Microsoft Edge WebView2** (composant de Windows, déjà présent sur Windows 11 et la plupart des Windows 10 ; sinon
l'appli propose la page de téléchargement de Microsoft), icône dans la zone de notification, notifications Windows,
surveillance du presse-papiers, démarrage avec Windows, une seule instance (un second lancement transmet ses liens).
L'installeur retire automatiquement l'ancienne version Electron et garde la liste et les réglages.

L'ancienne version Electron (`desktop/`) reste disponible en secours : `CLASSIQUE=1 ./build.sh` produit
`Telechargys-classique-X-Portable.exe`.

## Mises à jour automatiques (dépôt GitHub privé)

Au démarrage, l'appli (Windows et Android) consulte la dernière **Release** du dépôt GitHub privé. Si une version plus
récente existe, elle la propose ; le fichier est téléchargé, son empreinte SHA-256 est vérifiée avec `SHA256SUMS.txt`,
puis l'installeur Windows se lance en silencieux et relance Telechargys (sur Android : écran d'installation, qui exige en
plus la même signature que l'appli installée).

Le dépôt étant privé, il faut un **jeton d'accès en lecture seule** :

1. GitHub > Settings > Developer settings > Personal access tokens > **Fine-grained tokens** > Generate new token.
2. Repository access : **Only select repositories** > ce dépôt. Permissions : **Contents : Read-only**. Rien d'autre.
3. Soit chaque appareil le colle dans **Réglages > Mises à jour** (il reste sur l'appareil, jamais dans les sauvegardes),
   soit on l'enregistre dans `windows/update-token.txt` avant `./build.sh` pour l'intégrer aux applis (ce fichier est
   ignoré par Git). Attention : un jeton intégré peut être extrait de l'appli par quelqu'un de motivé ; il ne donne
   que la lecture de ce dépôt, et se révoque sur GitHub à tout moment.

### Publier une version

1. Augmenter la version : `Version` dans `engine/core/model.go`, `versionCode` (+1) et `versionName` dans
   `android/app/build.gradle.kts`, `version` dans `desktop/package.json` et dans `engine/cmd/telechargys-win/winres/winres.json`.
2. `./build.sh`
3. `./publier-version.sh "Notes de version"` (GitHub CLI, `gh auth login` une fois), **ou** à la main sur GitHub :
   Releases > Draft a new release > tag `v1.4.0` > joindre `Telechargys-1.4.0-Installation.exe`,
   `Telechargys-1.4.0-Portable.zip`, `Telechargys-1.4.0.apk` **et** `SHA256SUMS.txt` > Publish.
   Sans `SHA256SUMS.txt`, les applis refusent la mise à jour.

## Organisation du code

```
telechargys/
  engine/                     moteur commun, écrit en Go
    core/                     téléchargement segmenté (http.go), HLS (hls.go), DASH et fusion (dash.go), FTP (ftp.go),
                              files et planificateur (manager.go), aspirateur (grab.go), mises à jour (update.go),
                              API locale + sécurité (api.go), tests (*_test.go)
    ui/web/                   interface (HTML / CSS / JS sans dépendance), embarquée dans le moteur
    cmd/telechargys-win/      application Windows native (WebView2, zone de notification, notifications)
    cmd/telechargys-engine/   moteur seul (utilisé par la version Electron de secours)
    mobile/                   façade pour Android (gomobile)
  windows/                    installeur NSIS (telechargys.nsi) et icône
  desktop/                    ancienne application Windows (Electron), gardée en secours
  android/                    application Android (Kotlin) : écran principal, service au premier plan, navigateur intégré
  extension/                  extension navigateur (Chrome / Edge) ; extension/firefox pour Firefox ; PUBLICATION.md
  build.sh                    reconstruit tout dans livraison/
  publier-version.sh          publie livraison/ comme Release GitHub (mise à jour automatique)
```

Le moteur écoute uniquement sur `127.0.0.1` (port 47615 et suivants), exige un jeton secret, refuse les origines web étrangères et les attaques par « DNS rebinding ». L'extension doit être autorisée une fois depuis l'application.

## Reconstruire

Prérequis : Go 1.24+, JDK 17+, SDK Android avec NDK, `makensis` et `zip`. Pour la version Electron de secours : Node 20+ et Wine (32 et 64 bits) depuis Linux.

```bash
./build.sh                    # tests + installeur + portable Windows + APK + extensions + SHA256SUMS.txt dans livraison/
CLASSIQUE=1 ./build.sh        # idem + version Electron de secours
TY_SIGN_PFX=cert.pfx TY_SIGN_PASS=... ./build.sh   # avec signature de code Windows (voir extension/PUBLICATION.md)
```

## Signature Android (important)

Toutes les versions doivent être signées avec **la même clé**, sinon la mise à jour ne s'installe pas par-dessus l'ancienne.

- Fichier : `android/keystore/telechargys-release.jks`
- Alias : `telechargys`
- Mots de passe : dans `android/keystore/keystore.properties`

Ces deux fichiers ne sont **jamais** envoyés dans le dépôt Git : ils sont fournis dans l'archive du code source. Garde-les précieusement et remets-les dans `android/keystore/` avant chaque build. Sans eux, Gradle produit une APK non signée.

## Licences des composants

Go et ses bibliothèques (BSD), gomedia (MIT), jlaffaye/ftp (ISC), go-webview2 (MIT), fyne systray (Apache 2.0), sqweek/dialog (ISC), atotto/clipboard (BSD), WebView2 (composant Microsoft du système), AndroidX (Apache 2.0) ; version de secours : Electron (MIT, embarque Chromium et ffmpeg en LGPL). Aucun composant GPL : l'application peut être distribuée ou vendue. Le nom, l'icône et le code sont originaux (aucun élément repris d'Internet Download Manager).
