# Calorys 1.1.0 (QMTech)

Compteur de calories et coach nutritionnel, inspiré des fonctionnalités de YAZIO, écrit de zéro (aucun code, texte, image ni donnée de YAZIO). La version 1.1 fusionne Calorys avec le moteur de **Nutravyn** (QMTech) : objectif adaptatif, mode sèche pour les pesées officielles, séances de sports de combat avec RPE et gamification par ceintures.

Pas de compte, pas de serveur, pas d'abonnement. Tout fonctionne **hors ligne**, sauf deux options en ligne facultatives : l'analyse photo par Gemini et les produits Open Food Facts sortis après la date du catalogue.

## Fonctionnalités

**Journal**
- Repas (petit-déjeuner, déjeuner, dîner, collations), anneau des calories restantes, macros, « Comme hier ».
- Ajout en un geste (« + »), annulation depuis la notification, rapport du jour imprimable ou en PDF.

**Aliments**
- **892 632 produits de marque hors ligne** (Open Food Facts, export France du 28/10/2026), avec Nutri-Score, portions et code-barres. Le catalogue se télécharge une seule fois (60 Mo, vérifié par SHA-256).
- Table Ciqual 2025 de l'ANSES (3 479 aliments génériques, 15 nutriments) et 336 aliments courants de Nutravyn.
- Scan de code-barres (caméra, photo ou saisie) : aliments perso, puis catalogue hors ligne, puis Open Food Facts en ligne.
- **Photo IA** : Gemini reconnaît chaque aliment de l'assiette et estime sa portion. Tu corriges avant d'ajouter. Il faut une clé gratuite Google AI Studio.
- Aliments perso, recettes perso, ajout rapide.

**Recettes**
- 72 recettes Nutravyn avec ingrédients, étapes, temps et filtres (sèche, protéinées, rapides, prise de masse…).
- Portions ajustables, ajout au journal, copie modifiable dans « Mes recettes », favoris.
- **Liste de courses** : regroupe les ingrédients, cases à cocher, partage.

**Moteur Nutravyn** (`app/js/engine.js`)
- **Objectif adaptatif** : la dépense réelle est mesurée sur 28 jours (calories moyennes + variation du poids lissé × 7 700 / jours). L'objectif se recale tout seul, même si le journal n'est pas parfait. Tant qu'il n'y a pas assez de données, l'estimation reste théorique (Mifflin-St Jeor).
- **Courbe de poids lissée** (moyenne mobile exponentielle) pour gommer les variations d'eau. Tour de taille facultatif.
- **Mode « Faire le poids »** : date de pesée officielle et poids de catégorie. Déficit plafonné à 25 %, plancher au métabolisme de base, protéines au moins 1,8 g/kg, alerte si la catégorie n'est pas atteignable proprement. Aucune coupe hydrique n'est planifiée.
- **Presets de macros** : équilibré, sèche, prise de masse, low-carb, cétogène, ou répartition perso.
- **Séances** : sparring, technique/pao, grappling, sac/shadow, renforcement, cardio, vélo, mobilité, avec intensité perçue (RPE) et estimation de la sudation. Il y a aussi 36 activités du quotidien.
- Calories des séances rendues à **50 %** par défaut (réglable).
- **Eau automatique** : 35 ml/kg + 500 ml par heure de séance.
- **Gamification** : ceintures de blanche à 2e dan, XP, séries, défis de la semaine, 9 badges. Seuls les comportements sont récompensés, jamais un déficit plus creux. Désactivable.

**Le reste**
- Jeûne intermittent (12:12 à 23:1), minuteur, étapes, historique.
- Analyse sur 7, 30 ou 90 jours : calories, macros, fibres, sucres, AG saturés, sel, dépense réelle, poids.
- **Rappels** : repas, eau, pesée, fin du jeûne. Notifications Android, même appli fermée. Sur Windows, tant que l'appli est ouverte.
- Export CSV, sauvegarde et restauration JSON, thème clair, sombre ou automatique.

## Téléchargements (`release/`)

| Fichier | Plateforme | Taille |
|---|---|---|
| `Calorys-1.1.0.apk` | Android 8.0 et plus (cible Android 15) | 1,3 Mo |
| `Calorys-Setup-1.1.0.exe` | Windows 10/11, installeur | 1,8 Mo |
| `Calorys-Portable-1.1.0.zip` | Windows 10/11, sans installation | 2,0 Mo |

Le catalogue de produits n'est pas dans ces fichiers : il se télécharge depuis l'appli (Profil > Catalogue produits hors ligne, ou depuis la recherche). Il est publié dans `catalog/` de ce dépôt.

**Android** : ouvre l'APK sur le téléphone. La 1.1 s'installe par-dessus la 1.0 sans perte de données (même clé de signature, versionCode 2).

**Windows** : installation sans droits administrateur dans `%LOCALAPPDATA%\Programs\Calorys`, raccourcis menu Démarrer et bureau, désinstallation via « Applications et fonctionnalités ». L'exe n'est pas signé avec un certificat de code : SmartScreen peut afficher un avertissement (« Informations complémentaires » puis « Exécuter quand même »). Calorys utilise Microsoft Edge WebView2, inclus dans Windows 11 et Windows 10 à jour.

## Où sont enregistrées les données

| Plateforme | Journal | Catalogue | Exports |
|---|---|---|---|
| Android | stockage interne (WebView + `calorys-data.json`) | stockage interne (`catalog.db`, 133 Mo) | `Documents/Calorys/`, bouton Partager |
| Windows | `%APPDATA%\Calorys\data.json` | `%APPDATA%\Calorys\catalog.db` | « Enregistrer sous », par défaut `Documents\Calorys` |
| Web | stockage du navigateur | IndexedDB (si l'espace le permet) | Téléchargements |

## Structure du projet

```
calorys/
├── app/                    Appli (HTML/CSS/JS, commune aux 3 plateformes)
│   ├── js/app.js           Interface et écrans
│   ├── js/engine.js        Moteur Nutravyn (objectifs, adaptatif, sèche, séances, gamification)
│   ├── js/nutrition.js     Ciqual, recherche, portions, Open Food Facts en ligne
│   ├── js/catalog.js       Catalogue hors ligne (SQLite natif Android, sql.js ailleurs)
│   ├── js/platform.js      Stockage et fichiers selon la plateforme
│   ├── js/charts.js        Graphiques SVG
│   ├── data/foods.js       Table Ciqual générée
│   └── data/nutravyn.js    Aliments courants et recettes Nutravyn
├── catalog/                Catalogue Open Food Facts (morceaux gzip + manifeste SHA-256)
├── android/                Coquille Android native (WebView, SQLite, rappels, impression)
├── windows/                Neutralino + installeur NSIS
├── tools/                  Scripts de génération des données et des icônes
└── release/                Fichiers prêts à installer
```

## Reconstruire

Données :

```bash
python3 tools/build_foods.py              # Ciqual -> app/data/foods.js
python3 tools/build_nutravyn.py           # Nutravyn -> app/data/nutravyn.js
node tools/make_icons.js                  # icônes (Playwright + Chromium)

# Catalogue Open Food Facts (environ 2 min, export public sur S3)
curl -s https://openfoodfacts-ds.s3.eu-west-3.amazonaws.com/fr.openfoodfacts.org.products.csv.zst \
  | zstd -dc | python3 tools/filter_off.py | gzip > off-fr.tsv.gz
python3 tools/build_catalog.py off-fr.tsv.gz catalog/ AAAA-MM-JJ
# puis régénérer app/js/catalog-manifest.js depuis catalog/catalog.json
```

APK Android :

```bash
cd android
ANDROID_JAR=/chemin/android-35/android.jar \
KEYSTORE=/chemin/calorys-release.jks KS_PASS='mot de passe' ./build.sh
```

Si ton `aapt2` refuse l'android.jar récent, ajoute `ANDROID_RES_JAR=/chemin/android-33/android.jar`. Avec le SDK officiel, ajoute `D8=/chemin/build-tools/35.0.0/d8`.

Windows (Linux ou WSL : neu, makensis, zip, et wine + rcedit pour l'icône) :

```bash
cd windows
NEU_ZIP=neutralinojs-v6.9.0.zip RCEDIT=rcedit-x64.exe ./build.sh
```

## Signature Android et mises à jour

APK signée avec `calorys-release.jks` (alias `calorys`). **La clé et son mot de passe ne sont pas dans ce dépôt public** : ils sont fournis à part (`CLE-SIGNATURE.txt`). Toutes les mises à jour doivent être signées avec cette clé.

Empreinte SHA-256 du certificat : `B4:5A:96:6C:49:59:27:2D:55:EC:AB:BC:CB:7F:29:07:99:54:95:22:E9:C2:29:4F:5E:AE:40:DC:D5:27:1B:E3`

Pour une nouvelle version, incrémente `versionCode` et `versionName` (`android/AndroidManifest.xml`), `version` (`windows/neutralino.config.json`), `APP_VERSION` (`app/js/app.js`) et le cache de `app/sw.js`.

## Sources, licences et publication

- **Table Ciqual 2025**, ANSES : Licence Ouverte / Open Licence Etalab 2.0 (réutilisation commerciale autorisée, source citée dans l'appli).
- **Open Food Facts** : base sous licence ODbL. Le catalogue dérivé de `catalog/` est redistribué sous la même licence, et la mention est affichée.
- **Nutravyn** (QMTech) : moteur, aliments courants et recettes, repris de ton propre projet.
- **ZXing** : Apache 2.0. **sql.js** : MIT. **Neutralinojs** : MIT. Aucun composant GPL.
- **Gemini** (facultatif) : sur le palier gratuit, Google peut utiliser les photos envoyées pour améliorer ses modèles. C'est indiqué dans l'appli.
- Pour le Play Store (marque QMTech) : compte développeur, politique de confidentialité, bundle AAB signé. Ne cite pas YAZIO dans la fiche.

Calorys ne remplace pas l'avis d'un médecin ou d'un diététicien.
