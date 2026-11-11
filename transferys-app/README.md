# Transferys

Transfert de fichiers sans câble entre un PC Windows et un téléphone Android, dans les deux sens, sur le Wi-Fi local. Chiffré, sans serveur, sans Internet.

Marque : QMTech • Package Android : `fr.qmtech.transferys` • Version : 1.1.0

## Fonctionnalités

- Découverte automatique (multicast UDP + broadcast sur chaque sous-réseau, compatible point d'accès du téléphone), QR code, saisie d'IP
- Envoi de fichiers et de dossiers entiers, tous types, sans limite de taille
- Morceaux de 8 Mo, reprise automatique (10 min de tentatives, nouvelle IP retrouvée par la découverte), reprise même après redémarrage de l'appli (fichiers partiels conservés 7 jours)
- SHA-256 vérifié par le destinataire pour chaque fichier
- Progression par fichier et globale, Mo/s, temps restant, pause / reprise / annulation (des deux côtés)
- Doublons : renommer, remplacer ou ignorer
- TLS avec certificat ECDSA généré sur chaque appareil, épinglé ; appairage par code à 6 chiffres ; appareils de confiance révocables ; confirmation avant réception
- Windows : glisser-déposer, zone de notification, démarrage avec Windows, notifications, clic droit « Envoyer avec Transferys », « Envoyer vers », instance unique
- Android : sélecteurs natifs sans copie (lecture directe des `content://`), menu Partager, service au premier plan avec verrous Wi-Fi et processeur, galerie mise à jour, permissions expliquées
- Historique avec « Ouvrir le fichier » / « Ouvrir le dossier », thème clair / sombre, guide de démarrage
- **Accès à distance (v1.1, 100 % gratuit, sans serveur)** : ouverture automatique du port sur la box (UPnP IGD) + IPv6 ; les adresses Internet sont échangées pendant que les appareils sont sur le même Wi-Fi ; l'appairage reste interdit depuis Internet
- **Explorateur de dossiers partagés** dans les deux sens (onglet Parcourir), lecture seule ou dépôt autorisé par dossier ; un téléphone en 4G (injoignable) garde un canal inverse ouvert vers le PC (long polling), toutes les données passent par des connexions ouvertes par le téléphone

## Organisation du code (`lib/`)

| Dossier | Rôle |
|---|---|
| `core/` | Modèles, réglages, historique, appareils de confiance, formats FR, erreurs en français |
| `security/` | Identité TLS de l'appareil (`identity.dart`), protocole d'appairage par code (`pairing.dart`) |
| `network/` | Découverte UDP (`discovery.dart`), UPnP IGD (`upnp.dart`), adresses locales, QR code |
| `transfer/` | Protocole HTTPS, serveur et réception (`server.dart`, `receiver.dart`), envoi (`sender.dart`), téléchargement distant (`downloader.dart`), dossiers partagés (`fs_service.dart`), canal inverse (`tunnel.dart`), lecture Android par descripteur (`fd_reader.dart`), client épinglé, SHA-256 en isolate (`hasher.dart`) |
| `transport/` | Interface `Transport` : le Wi-Fi est l'implémentation v1, le Bluetooth (v2) s'y branchera sans toucher au reste |
| `worker/` | Le moteur tourne dans un isolate dédié (`engine_worker.dart`), l'interface le pilote via `engine_proxy.dart` |
| `platform/` | Android (`android_bridge.dart` + Kotlin), Windows (`windows_integration.dart`), notifications et ouverture de fichiers |
| `ui/` | Écrans et dialogues |
| `engine.dart` | Assemble le tout (Dart pur, testable sans Flutter) |

Natif Android : `android/app/src/main/kotlin/fr/qmtech/transferys/` (`MainActivity.kt`, `TransferService.kt`).
Installateur Windows : `windows/installer/transferys.nsi`.

## Protocole (v1)

HTTPS sur le port 53518 (repli automatique sur un port libre), découverte UDP sur 53517 (groupe 224.0.0.170).
Voir l'en-tête de `lib/transfer/protocol.dart` pour les routes et `lib/security/pairing.dart` pour l'appairage.

## Compiler

Prérequis : Flutter 3.47 (stable).

### APK Android

```bash
flutter pub get
flutter build apk --release
# → build/app/outputs/flutter-apk/app-release.apk
```

La signature utilise `android/key.properties` + `android/transferys-release.jks` (fournis à part, **jamais** dans un dépôt public, voir `SIGNATURE.txt`).
Sans ces fichiers, l'APK est signée avec la clé de debug et ne pourra pas mettre à jour une version déjà installée.
À chaque nouvelle version : augmenter `version:` dans `pubspec.yaml` (ex. `1.0.1+2`).

### Windows (sur un PC Windows avec Visual Studio 2022, charge « Développement Desktop en C++ »)

```bash
flutter pub get
flutter build windows --release
# → build\windows\x64\runner\Release\Transferys.exe
makensis /DVERSION=1.0.0 /DSRC=build\windows\x64\runner\Release windows\installer\transferys.nsi
```

La compilation automatique (tests + installateur + version portable) est faite par GitHub Actions : `.github/workflows/transferys-windows.yml`.

### Tests

```bash
flutter test test/engine_test.dart test/remote_test.dart   # 22 scénarios réels entre deux instances
TRANSFERYS_BIG=1 flutter test test/engine_test.dart --name "5 Go"
```

Scénarios : appairage (bon et mauvais code), fichiers + arborescence, sens inverse, 500 petits fichiers, coupure réseau en plein transfert, redémarrage du destinataire, espace disque insuffisant (contrôle préalable et disque plein en cours d'écriture), refus, pause longue, annulation, doublons, chemins malveillants, débit, 5 Go.

## Où sont les fichiers ?

- Reçus : Windows `Téléchargements\Transferys`, Android `Téléchargements/Transferys` (modifiable dans Réglages)
- Fichiers partiels pendant un transfert : sous-dossier caché `.transferys-partial` du dossier de réception
- Réglages, historique, appareils de confiance, certificat : Windows `%APPDATA%\QMTech\Transferys`, Android : données privées de l'appli
