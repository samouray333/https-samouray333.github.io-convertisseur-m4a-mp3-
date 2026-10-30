# Calorys 1.4.1 (QMTech)

Compteur de calories et coach nutritionnel, inspiré des fonctionnalités de YAZIO, écrit de zéro (aucun code, texte, image ni donnée de YAZIO). La version 1.1 fusionne Calorys avec le moteur de **Nutravyn** (QMTech) : objectif adaptatif, mode sèche pour les pesées officielles, séances de sports de combat avec RPE et gamification par ceintures.

Pas de compte, pas de serveur, pas d'abonnement. Tout fonctionne **hors ligne**, sauf deux options en ligne facultatives : l'analyse photo par Gemini et les produits Open Food Facts sortis après la date du catalogue.

## Fonctionnalités

**Journal**
- Repas (petit-déjeuner, déjeuner, dîner, collations), anneau des calories restantes, macros, « Comme hier ».
- Ajout en un geste (« + »), annulation depuis la notification, rapport du jour imprimable ou en PDF.

**Aliments**
- **894 337 produits de marque hors ligne** (Open Food Facts, export France du 28/10/2026), avec Nutri-Score, photo, portions et code-barres. Le catalogue se télécharge une seule fois (62 Mo, vérifié par SHA-256).
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
- **Séances** : sparring, technique/pao, grappling, sac/shadow, renforcement, cardio, vélo, mobilité, avec intensité perçue (RPE) et estimation de la sudation. Il y a aussi 40 activités du quotidien, dont la marche sur tapis à 4, 5 et 5,5 km/h et la course sur tapis à 8 km/h. Pour la marche et la course, les pas sont estimés (distance / foulée déduite de la taille) et comptés dans l'objectif de pas.
- Calories des séances rendues à **50 %** par défaut (réglable).
- **Eau automatique** : repères EFSA en boisson (environ 2 L pour un homme, 1,6 L pour une femme, ajustés au poids), plus la sueur estimée des séances du jour.
- **Gamification** : ceintures de blanche à 2e dan, XP, séries, défis de la semaine, 9 badges. Seuls les comportements sont récompensés, jamais un déficit plus creux. Désactivable.

**Nouveau en 1.4 : programmes**
- **Programmes importables** (Profil > Programmes) : un fichier `.json` règle l'appli. Il fixe la fenêtre de jeûne avec un minuteur lancé et arrêté automatiquement, les repas supprimés (par exemple pas de petit-déjeuner), la répartition des calories, l'objectif, les macros et les jours spéciaux (5:2). Il programme aussi l'eau (heure et quantité, créneaux à cocher dans le journal) et les notifications (avec jours de la semaine), et fournit des règles et un conseil du jour.
- Carte du programme dans le journal : jour X/Y, fenêtre de repas ouverte ou fermée avec compte à rebours, conseil du jour. Un avertissement s'affiche si on note un aliment pendant le jeûne.
- 5 programmes fournis : Jeûne 16:8 sans petit-déjeuner, Rééquilibrage 3 repas, Jeûne 18:6, Jeûne 5:2, Sèche sports de combat. On peut importer ses propres fichiers, les partager, exporter un modèle à remplir (format détaillé dans `programmes/LISEZMOI.md`).
- Arrêter un programme rétablit les réglages d'avant.

**Nouveau en 1.3**
- **Apparence** (Profil > Apparence) : 10 couleurs (Émeraude, Océan, Lagon, Lavande, Framboise, Corail, Ambre, Combat, Graphite et « Ma ceinture », qui prend la couleur de ta ceinture et change à chaque grade). S'y ajoutent le mode **Couleurs vives** (dégradés, fonds teintés, activé par défaut) et le thème clair, sombre ou automatique.

**Nouveau en 1.2**
- **Synchronisation téléphone ↔ PC** (ou entre deux téléphones), sans compte ni serveur. Le téléphone affiche une adresse et un code sur le Wi-Fi local, l'autre appareil s'y connecte. Chaque élément (aliment noté, séance, pesée, recette, liste de courses, profil…) est daté automatiquement, et la fusion garde la version la plus récente de chacun. Les suppressions sont propagées, et les données voyagent chiffrées (AES-256-GCM, clé dérivée du code). Un nouvel appareil peut tout récupérer dès l'accueil (« Déjà utilisateur ? »).
- **Photos des produits** : miniature dans la recherche et le journal, grande photo sur la fiche (95 % des 894 337 produits). Elles sont chargées depuis Open Food Facts quand il y a du réseau, et masquées sinon.
- **Rappels Windows même appli fermée** : via le Planificateur de tâches, sans droits administrateur, en notifications Windows au nom de Calorys avec un bouton « Ouvrir Calorys ».
- **Signature de l'exe prête** : `windows/sign.sh` signe l'exe, l'installeur et le désinstalleur dès qu'un certificat est fourni (voir plus bas).

**Le reste**
- Jeûne intermittent (12:12 à 23:1), minuteur, étapes, historique.
- Analyse sur 7, 30 ou 90 jours : calories, macros, fibres, sucres, AG saturés, sel, dépense réelle, poids.
- **Rappels** : repas, eau, pesée, fin du jeûne. Notifications Android et Windows, même appli fermée.
- Export CSV, sauvegarde et restauration JSON, thème clair, sombre ou automatique.

## Téléchargements (`release/`)

| Fichier | Plateforme | Taille |
|---|---|---|
| `Calorys-1.4.1.apk` | Android 8.0 et plus (cible Android 15) | 1,3 Mo |
| `Calorys-Setup-1.4.1.exe` | Windows 10/11, installeur | 1,8 Mo |
| `Calorys-Portable-1.4.1.zip` | Windows 10/11, sans installation | 2,0 Mo |

Le catalogue de produits n'est pas dans ces fichiers : il se télécharge depuis l'appli (Profil > Catalogue produits hors ligne, ou depuis la recherche). Il est publié dans `catalog/` de ce dépôt.

**Android** : ouvre l'APK sur le téléphone. La 1.3 s'installe par-dessus les versions précédentes sans perte de données (même clé de signature, versionCode 8). Si le catalogue de la 1.1 est installé, l'appli propose « Mettre à jour » pour récupérer les photos.

**Synchroniser** : sur le téléphone, Profil > Synchroniser mes appareils > « Ce téléphone sert d'hôte ». Sur le PC, même menu : saisis l'adresse et le code affichés, puis Synchroniser. Les deux appareils doivent être sur le même Wi-Fi.

**Windows** : installation sans droits administrateur dans `%LOCALAPPDATA%\Programs\Calorys`, raccourcis menu Démarrer et bureau, désinstallation via « Applications et fonctionnalités ». L'exe n'est pas encore signé avec un certificat de code : SmartScreen peut afficher un avertissement (« Informations complémentaires » puis « Exécuter quand même »). Voir « Signature de l'exe Windows » plus bas. Calorys utilise Microsoft Edge WebView2, inclus dans Windows 11 et Windows 10 à jour.

## Où sont enregistrées les données

| Plateforme | Journal | Catalogue | Exports |
|---|---|---|---|
| Android | stockage interne (WebView + `calorys-data.json`) | stockage interne (`catalog.db`, 139 Mo) | `Documents/Calorys/`, bouton Partager |
| Windows | `%APPDATA%\Calorys\data.json` | `%APPDATA%\Calorys\catalog.db.gz` (62 Mo) | « Enregistrer sous », par défaut `Documents\Calorys` |
| Web | stockage du navigateur | IndexedDB (si l'espace le permet) | Téléchargements |

## Structure du projet

```
calorys/
├── app/                    Appli (HTML/CSS/JS, commune aux 3 plateformes)
│   ├── js/app.js           Interface et écrans
│   ├── js/engine.js        Moteur Nutravyn (objectifs, adaptatif, sèche, séances, gamification)
│   ├── js/nutrition.js     Ciqual, recherche, portions, Open Food Facts en ligne
│   ├── js/catalog.js       Catalogue hors ligne (SQLite natif Android, sql.js ailleurs)
│   ├── js/program.js       Programmes (validation, fenêtre de repas, notifications)
│   ├── js/sync.js          Synchronisation (horodatage, fusion, chiffrement, transport Wi-Fi)
│   ├── js/winrem.js        Rappels Windows (Planificateur de tâches + notifications)
│   ├── js/platform.js      Stockage et fichiers selon la plateforme
│   ├── js/charts.js        Graphiques SVG
│   ├── data/foods.js       Table Ciqual générée
│   └── data/nutravyn.js    Aliments courants et recettes Nutravyn
├── catalog/                Catalogue Open Food Facts (morceaux gzip + manifeste SHA-256)
├── programmes/             Programmes fournis (.json) et description du format
├── android/                Coquille Android native (WebView, SQLite, rappels, impression, serveur de synchro)
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

## Signature de l'exe Windows (SmartScreen)

Sans signature de code, Windows SmartScreen affiche « Windows a protégé votre ordinateur » au premier lancement. La chaîne de signature est prête et testée (exe, désinstalleur et installeur signés en SHA-256, avec horodatage) :

```bash
cd windows
NEU_ZIP=… RCEDIT=… SIGN_PFX=certificat.pfx SIGN_PASS='mot de passe' ./build.sh
```

Il faut un certificat de signature de code reconnu par Windows, qui ne peut pas se générer soi-même :
- **Azure Trusted Signing** (Microsoft), la solution la moins chère pour un particulier ou une micro-entreprise : abonnement mensuel modeste, vérification d'identité. Il se pilote avec leur outil plutôt qu'un fichier .pfx.
- **Certificat OV** d'une autorité (Certum, Sectigo…) : quelques dizaines à quelques centaines d'euros par an. La réputation SmartScreen se construit au fil des téléchargements.
- **Microsoft Store** : l'appli est signée par Microsoft et SmartScreen ne s'affiche plus.

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
