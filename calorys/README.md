# Calorys 1.0.0 (QMTech)

Compteur de calories et journal alimentaire, inspiré des fonctionnalités de YAZIO mais écrit entièrement de zéro (aucun code, texte, image ni donnée de YAZIO). Calorys fonctionne **100 % hors ligne**, sans compte, sans serveur et sans abonnement.

## Fonctionnalités

- **Journal par repas** (petit-déjeuner, déjeuner, dîner, collations) : anneau des calories restantes, glucides, protéines et lipides, navigation par jour, bouton « Comme hier ».
- **Base d'aliments hors ligne** : table Ciqual 2025 de l'ANSES (3 479 aliments, 15 nutriments). Recherche insensible aux accents et aux pluriels, portions usuelles (tranche, pot, œuf moyen…), récents et favoris.
- **Ajout en un geste** : le bouton « + » d'un résultat ajoute la dernière quantité utilisée. Annulation possible depuis la notification.
- **Codes-barres** : scan par caméra (BarcodeDetector ou ZXing), photo ou saisie du code. Recherche du produit sur Open Food Facts (en ligne, facultatif), puis mise en cache.
- **Produits de marque** : recherche en ligne Open Food Facts depuis l'écran de recherche.
- **Aliments personnels** (valeurs de l'étiquette, portion, code-barres), **recettes** (ingrédients, nombre de portions) et **ajout rapide** de calories.
- **Eau** (verres à toucher), **activités** (36 activités avec valeurs MET, dont boxe et MMA), **pas**, **pesées** avec IMC.
- **Jeûne intermittent** : rythmes de 12:12 à 23:1, minuteur, étapes, historique.
- **Analyse** sur 7, 30 ou 90 jours : calories par jour comparées à l'objectif, répartition des macros, fibres, sucres, AG saturés et sel, courbe de poids.
- **Profil** : objectif calculé avec Mifflin-St Jeor (modifiable), répartition des macros, objectifs d'eau et de pas, thème clair, sombre ou automatique.
- **Données** : export du journal et des pesées en CSV (compatible Excel en français), sauvegarde et restauration JSON, partage sur Android.
- **Windows** : glisser-déposer d'une sauvegarde, boîte « Enregistrer sous » qui mémorise le dernier dossier, raccourcis clavier (← → jour, N ou Ctrl+F ajouter, T aujourd'hui, Ctrl+S sauvegarde, Échap fermer).

## Téléchargements (dossier `release/`)

| Fichier | Plateforme | Taille |
|---|---|---|
| `Calorys-1.0.0.apk` | Android 8.0 et plus (cible Android 15) | 1,1 Mo |
| `Calorys-Setup-1.0.0.exe` | Windows 10/11, installeur | 1,5 Mo |
| `Calorys-Portable-1.0.0.zip` | Windows 10/11, sans installation | 1,7 Mo |

Les empreintes SHA-256 sont dans `release/SHA256SUMS.txt`.

**Android** : ouvre l'APK sur le téléphone et autorise l'installation depuis cette source si Android le demande.

**Windows** : l'installeur s'installe sans droits administrateur dans `%LOCALAPPDATA%\Programs\Calorys`. Il crée les raccourcis du menu Démarrer et du bureau et apparaît dans « Applications et fonctionnalités » pour la désinstallation. L'exe n'est pas signé avec un certificat de code, donc SmartScreen peut afficher « Windows a protégé votre ordinateur » : clique sur « Informations complémentaires » puis « Exécuter quand même ». Calorys utilise Microsoft Edge WebView2, présent d'origine sur Windows 11 et sur Windows 10 à jour. L'installeur propose le lien de téléchargement s'il est absent.

**Navigateur** : le dossier `app/` est aussi une appli web installable (PWA), utilisable depuis GitHub Pages à l'adresse `…/calorys/app/`.

## Où sont enregistrées les données

| Plateforme | Journal (données de l'appli) | Exports CSV et sauvegardes |
|---|---|---|
| Android | stockage interne de l'appli (WebView + copie `calorys-data.json`) | `Documents/Calorys/` (Android 10 et plus), bouton Partager |
| Windows | `%APPDATA%\Calorys\data.json` (conservé à la désinstallation) | boîte « Enregistrer sous », par défaut `Documents\Calorys` |
| Web | stockage local du navigateur | dossier Téléchargements |

## Structure du projet

```
calorys/
├── app/                  Appli (HTML/CSS/JS, commune aux 3 plateformes)
│   ├── index.html
│   ├── css/style.css
│   ├── js/platform.js    Stockage et fichiers selon la plateforme
│   ├── js/nutrition.js   Base Ciqual, recherche, portions, calculs
│   ├── js/charts.js      Graphiques SVG
│   ├── js/app.js         Interface et logique
│   ├── js/vendor/        ZXing (codes-barres), client Neutralino
│   ├── data/foods.js     Table Ciqual générée
│   └── sw.js, manifest.webmanifest, img/
├── android/              Coquille Android native (WebView, sans AndroidX)
│   ├── AndroidManifest.xml, res/, src/
│   └── build.sh
├── windows/              Neutralino + installeur NSIS
│   ├── neutralino.config.json, installer.nsi, calorys.ico
│   └── build.sh
├── tools/                build_foods.py (Ciqual -> foods.js), make_icons.js
└── release/              Fichiers prêts à installer
```

## Reconstruire

Base d'aliments et icônes :

```bash
python3 tools/build_foods.py
node tools/make_icons.js          # nécessite Playwright + Chromium
```

APK Android (aapt2, javac, d8 ou dx, zipalign, apksigner) :

```bash
cd android
ANDROID_JAR=/chemin/android-35/android.jar \
KEYSTORE=/chemin/calorys-release.jks KS_PASS='mot de passe' ./build.sh
# -> android/build/Calorys-<version>.apk
```

Si ton `aapt2` est ancien et refuse l'android.jar récent, ajoute `ANDROID_RES_JAR=/chemin/android-33/android.jar`. Avec le SDK officiel, ajoute `D8=/chemin/build-tools/35.0.0/d8`.

Windows (sous Linux ou WSL : neu, makensis, zip, et wine + rcedit pour l'icône de l'exe) :

```bash
cd windows
NEU_ZIP=neutralinojs-v6.9.0.zip RCEDIT=rcedit-x64.exe ./build.sh
# -> windows/build/Calorys-Setup-<version>.exe et Calorys-Portable-<version>.zip
```

## Signature Android et mises à jour

L'APK est signée avec la clé `calorys-release.jks` (alias `calorys`). **La clé et son mot de passe ne sont pas dans ce dépôt**, parce qu'il est public. Ils sont fournis à part avec le fichier `CLE-SIGNATURE.txt`. Garde-les en lieu sûr : toutes les mises à jour doivent être signées avec cette même clé pour s'installer par-dessus sans perdre les données.

Empreinte SHA-256 du certificat : `B4:5A:96:6C:49:59:27:2D:55:EC:AB:BC:CB:7F:29:07:99:54:95:22:E9:C2:29:4F:5E:AE:40:DC:D5:27:1B:E3`

Pour une nouvelle version, incrémente `versionCode` et `versionName` dans `android/AndroidManifest.xml`, `version` dans `windows/neutralino.config.json` et `APP_VERSION` dans `app/js/app.js`.

## Sources, licences et publication

- **Table Ciqual 2025**, ANSES : Licence Ouverte / Open Licence Etalab 2.0. La réutilisation commerciale est autorisée avec mention de la source (affichée dans l'appli).
- **Open Food Facts** (recherche en ligne, facultative) : base sous licence ODbL. La mention est affichée. Les produits mis en cache restent sur l'appareil.
- **ZXing** : Apache 2.0. **Neutralinojs** : MIT.
- Aucun composant GPL. Pour publier sur le Play Store sous la marque QMTech, il faudra un compte développeur, une politique de confidentialité (simple, puisque rien ne quitte l'appareil sauf les requêtes Open Food Facts) et un bundle AAB signé. Évite aussi de citer YAZIO dans la fiche du store.

Calorys ne remplace pas l'avis d'un médecin ou d'un diététicien.
