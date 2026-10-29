# Lisys (Echo Matras)

Appli Android qui lit à voix haute les **documents** et les **pages web**, en surlignant la phrase et le mot lus, dans l'esprit de la fonction « lecteur » de ZoomText. Tout le code est original : rien n'est copié de ZoomText.

- Version : 1.0 (versionCode 1)
- Package : `com.echomatras.lisys`
- Android 8.0 (API 26) minimum, cible Android 14 (API 34)
- 100 % local : la voix est celle de la synthèse vocale du téléphone. Aucun compte, aucun serveur, aucun abonnement.

## Fonctions

**Ce que l'appli sait lire**
- PDF (texte), Word `.docx`, OpenOffice/LibreOffice `.odt`, livres `.epub`, `.rtf`, `.html`, `.txt` et `.md`
- Pages web : l'appli garde l'article et retire les menus, publicités, bandeaux cookies et commentaires
- Navigateur intégré pour les sites qui demandent JavaScript ou une connexion. Le bouton « Lire cette page » lit toute la page, ou seulement la sélection.
- Texte copié dans le presse-papiers, ou saisi à la main

**Pour envoyer du texte vers Lisys depuis les autres applis**
- Sélectionne du texte dans n'importe quelle appli, puis choisis **« Lire avec Lisys »** dans le menu
- Partage vers Lisys depuis Chrome (un lien) ou depuis Mes fichiers (un document)
- « Ouvrir avec Lisys » sur un PDF, un EPUB, etc.

**Pendant la lecture**
- Surlignage de la phrase en cours et du mot prononcé (si le moteur vocal le permet ; la voix Google le permet)
- Mode **grand texte (loupe)** : la phrase en cours s'affiche en très gros caractères
- Taille du texte réglable de 14 à 60, et 4 thèmes : clair, sombre, **contraste élevé jaune sur noir**, sépia
- Toucher une phrase lance la lecture à cet endroit
- Phrase ou paragraphe précédent et suivant, barre de position, recherche dans le texte
- Vitesse de 0,5× à 3×, réglage de la tonalité, choix de la voix (françaises en premier)
- La lecture continue écran éteint. Les commandes sont dans la notification, sur l'écran de verrouillage et sur les boutons du casque. Elle se met en pause pendant un appel ou si on débranche le casque.
- Minuterie de sommeil
- L'appli reprend là où tu t'étais arrêté (bibliothèque des 60 derniers documents)
- **Export audio** : le document entier devient un fichier `.m4a` (livre audio), enregistré dans `Téléchargements/Lisys`. Bouton Partager dans la notification.

## Où sont les fichiers

| Quoi | Où |
|---|---|
| Fichiers audio exportés | `Téléchargements/Lisys/<titre>.m4a` |
| Textes extraits et positions de lecture | dans le stockage privé de l'appli (`files/docs`, `files/bibliotheque.json`) |
| Réglages | dans le stockage privé de l'appli (SharedPreferences `reglages`) |

Tes fichiers d'origine ne sont jamais modifiés.

## Rôle des fichiers du code

| Fichier | Rôle |
|---|---|
| `app/AndroidManifest.xml` | Déclaration de l'appli, du partage, de « Lire avec Lisys » et des services. **Numéro de version ici.** |
| `MainActivity.java` | Écran d'accueil : ouvrir un document, une page web ou du texte, liste des lectures, réglages |
| `ReaderActivity.java` | Écran de lecture : surlignage, mode loupe, commandes, voix, vitesse, recherche, export |
| `ReaderService.java` | Moteur de lecture en arrière-plan (synthèse vocale, notification, casque, focus audio) |
| `ExportService.java` + `AacEncoder.java` | Création du fichier audio `.m4a` |
| `WebActivity.java` | Navigateur intégré |
| `Extractor.java` | Extraction du texte : PDF, DOCX, ODT, EPUB, RTF, HTML, TXT |
| `WebExtractor.java` | Téléchargement d'une page web et extraction de l'article |
| `Sentences.java` | Découpage en phrases |
| `Library.java` | Bibliothèque locale et positions de lecture |
| `Prefs.java`, `Ui.java` | Réglages, couleurs des thèmes, composants d'interface |
| `libs/` | PdfBox-Android 2.0.27.0 (Apache 2.0) et jsoup 1.13.1 (MIT) |
| `tests/` | Tests sur PC des moteurs d'extraction (`tests/run-tests.sh fichier.pdf …`) |

## Reconstruire l'APK

Sur Ubuntu ou Debian, sans Android Studio :

```bash
sudo apt install openjdk-21-jdk-headless android-sdk android-framework-res apksigner dalvik-exchange zip unzip
./build.sh            # produit release/Lisys-<version>.apk, signée
```

`build.sh` télécharge une seule fois l'API Android 14 pour la compilation (`android-all` de Robolectric, sur Maven Central).

Il a besoin de la clé de signature dans `signing/` (`lisys-release.jks` et `signing.properties`). Cette clé n'est **pas** publiée sur GitHub : elle t'a été fournie à part. Garde-la précieusement.

### Signature

- Fichier : `signing/lisys-release.jks`
- Alias : `lisys`
- Mot de passe (magasin et clé) : dans `signing/signing.properties`, fourni à part

**Toutes les mises à jour doivent être signées avec cette même clé.** Sinon Android refuse de les installer par-dessus l'ancienne version, et il faut désinstaller (ce qui perd la bibliothèque).

Pour une nouvelle version : augmente `android:versionCode` (+1) et `android:versionName` dans `app/AndroidManifest.xml`, puis relance `./build.sh`.

## Limites connues

- Les PDF scannés (des images) ne contiennent pas de texte : il faudrait un module de reconnaissance de texte (OCR), pas encore inclus.
- L'ancien format Word `.doc` n'est pas pris en charge (il faut l'enregistrer en `.docx` ou en PDF).
- La qualité de la voix dépend du moteur installé sur le téléphone. Les voix Google « haute qualité » se téléchargent dans Paramètres > Synthèse vocale.
