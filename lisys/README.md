# Lisys (Echo Matras)

Appli Android qui lit à voix haute les **documents** et les **pages web**, en surlignant la phrase et le mot lus, dans l'esprit de la fonction « lecteur » de ZoomText. Tout le code est original : rien n'est copié de ZoomText.

- Version : 1.4 (versionCode 5)
- Package : `com.echomatras.lisys`
- Android 8.0 (API 26) minimum, cible Android 14 (API 34)
- 100 % local : la voix est celle de la synthèse vocale du téléphone. Aucun compte, aucun serveur, aucun abonnement.

## Fonctions

**Ce que l'appli sait lire**
- PDF (texte), Word `.docx`, OpenOffice/LibreOffice `.odt`, livres `.epub`, `.rtf`, `.html`, `.txt` et `.md`
- Pages web : l'appli garde l'article et retire les menus, publicités, bandeaux cookies et commentaires
- Navigateur intégré pour les sites qui demandent JavaScript ou une connexion. Le bouton « Lire cette page » lit toute la page, ou seulement la sélection.
- Texte copié dans le presse-papiers, ou saisi à la main

**Lire le papier (photo) et les documents scannés (nouveau en 1.4)**
- Bouton « Lire une photo » : on photographie un courrier, une notice, une étiquette, et Lisys lit le texte. Un appui long sur le bouton permet de choisir une image dans la galerie. On peut aussi partager une image vers Lisys.
- Les PDF scannés (des images) sont proposés à la reconnaissance de texte, page par page.
- La reconnaissance se fait sur le téléphone, sans internet : Tesseract compilé en WebAssembly (`app/assets/ocr`, licence Apache 2.0, paquet npm tesseract-wasm 0.11), avec le modèle français `fra.traineddata` (tessdata_best_int). La photo est redressée automatiquement.

**Bouton flottant : lire n'importe quelle appli ou site**
- Un bouton 🔊 reste par-dessus toutes les applis (Chrome, Facebook, messages, mails…).
- **Un appui** : Lisys lit à voix haute le texte affiché, sans quitter l'appli. Sur une page web, la lecture continue sur la suite de la page. Un deuxième appui arrête.
- **Appui long** (la bulle devient ✋) : **lecture au doigt**. On glisse le doigt sur le texte et Lisys lit la phrase qui est dessous, entourée d'un cadre jaune. Quand on lève le doigt, la lecture continue. Touche la bulle pour quitter (ou arrêt automatique après 90 s sans rien).
- En mode doigt, **deux doigts** vers le haut ou le bas font défiler la page, et Lisys relit l'écran.
- Options à activer dans Réglages du bouton flottant (toutes désactivées par défaut) :
  - **Bandeau en très gros texte** : quand Lisys lit hors de son écran (bulle, arrière-plan), la phrase lue s'affiche en très gros, avec le mot prononcé surligné. Taille, couleurs et position (haut ou bas) réglables.
  - **Boutons de volume** : deux appuis rapides sur volume bas lisent l'écran, et un appui long (1 s) lance la lecture au doigt. Un seul appui baisse le son. Rien ne change pendant un appel.
  - **Annonce des messages reçus** (SMS, WhatsApp, Messenger, Telegram, Signal, mails…) : « Nouveau message de Paul, WhatsApp », et le texte si on le souhaite. Rien n'est annoncé pendant un appel, en mode Ne pas déranger ou pendant une lecture.
- **Bulle adaptée aux malvoyants** : 5 tailles (de 56 à 150 dp), 8 couleurs bien contrastées (jaune, noir sur jaune…), double bordure visible sur tous les fonds, vibration, annonces vocales (« Lecture au doigt »…) et actions TalkBack. Réglages : accueil > bouton flottant.
- On peut le déplacer en le faisant glisser (il se range contre le bord). Le bouton d'accessibilité d'Android fait la même chose.
- Pour l'activer : bouton « Lire les autres applis et sites » sur l'accueil, puis Paramètres > Accessibilité > « Lisys : bouton de lecture ». Sur Android 13 et plus, avec une APK installée depuis un fichier, il faut d'abord aller dans Infos appli > ⋮ > « Autoriser les paramètres restreints ».
- Lisys lit le contenu de l'écran seulement quand on appuie sur le bouton, et rien n'est envoyé sur internet.

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
| `OcrActivity.java`, `OcrEngine.java`, `PhotoProvider.java`, `assets/ocr/` | Lecture des photos et des PDF scannés (reconnaissance de texte hors ligne) |
| `ScreenReaderService.java` + `res/xml/accessibility_config.xml` | Bouton flottant (service d'accessibilité) qui lit l'écran des autres applis |
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

- Mails et pages web (WebView) : Lisys réessaie automatiquement quelques fois si le contenu n'est pas encore prêt. En cas de souci, Réglages du bouton flottant > « Rapport de la dernière lecture » donne ce que Lisys a vu (à copier pour le dépannage).
- Le bouton flottant lit le texte que l'appli fournit à Android. Les jeux, les vidéos et certaines applis qui affichent le texte comme une image n'en fournissent pas : il n'y a alors rien à lire.

- Reconnaissance de texte : l'écriture manuscrite est mal reconnue. Il faut une photo nette, à plat et bien éclairée.
- L'ancien format Word `.doc` n'est pas pris en charge (il faut l'enregistrer en `.docx` ou en PDF).
- La qualité de la voix dépend du moteur installé sur le téléphone. Les voix Google « haute qualité » se téléchargent dans Paramètres > Synthèse vocale.
