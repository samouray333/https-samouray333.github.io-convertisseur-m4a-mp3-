# Bimys 1.0.0 (QMTech)

Visionneuse BIM pédagogique spécialisée génie thermique pour les Bac Pro **ICCER** et **MEE** : ouverture de maquettes IFC, exploration des réseaux, métrés, déperditions, maintenance et défis élèves. Application 100 % hors ligne (aucun serveur, aucun compte, aucune clé API), interface entièrement en français.

- Package Android : `com.qmtech.bimys`, versionCode 1, versionName 1.0.0
- Windows : installeur NSIS (installation par utilisateur, sans droits administrateur, raccourcis menu Démarrer et bureau, désinstallation depuis « Applications et fonctionnalités ») et version portable
- Rendu WebGL standard (aucune dépendance CUDA ou carte Nvidia)

## Télécharger

Les fichiers sont construits par GitHub Actions (workflow `.github/workflows/bimys.yml`) et publiés dans la **Release GitHub `bimys-v1.0.0`** du dépôt :

| Fichier | Usage |
| --- | --- |
| `Bimys-1.0.0.apk` | Android 7.0 et plus, installation directe (autoriser les sources inconnues) |
| `Bimys-Setup-1.0.0.exe` | Installeur Windows 10/11 (64 bits) |
| `Bimys-Portable-1.0.0.exe` | Version portable Windows, sans installation |

## Fonctions

| Module | Contenu |
| --- | --- |
| Vue 3D | orbite, zoom, pan, vues dessus / face / iso, coupe horizontale par niveau + plan de coupe libre, mesure de distance, lots colorés (architecture en transparence, chauffage, ECS, eau froide, ventilation, équipements, électrique), isoler / masquer / tout afficher, arborescence Projet > Bâtiment > Niveaux > Pièces > Éléments synchronisée, propriétés avec types IFC traduits |
| Métré | longueurs par système, matériau et diamètre (cuivre `int x ext`, PER / multicouche `ext x épaisseur`), gaines par section, raccords, vannes et accessoires, chutes réglables, export CSV et PDF |
| Équipements | nomenclature (générateurs, émetteurs, circulateurs, vases, soupapes, ventilation, régulation, sanitaires), export CSV et PDF |
| Déperditions | méthode par parois (U × S × b × ΔT + ponts thermiques forfaitaires + 0,34 × Qv × ΔT, parois pré-remplies depuis les limites d'espaces IFC) ou volumique (G × V × ΔT), Te de base modifiable (−10 °C par défaut, Saône-et-Loire), Ti par pièce, comparaison avec les émetteurs (sous-dimensionné / correct / surdimensionné, écart en %), correction de puissance selon le régime d'eau, export PDF |
| Cohérence | émetteurs sans robinet thermostatique, pièces humides sans extraction, éléments sans système, pièces chauffées sans émetteur |
| Maintenance | fiches équipements, check-lists (`src/data/maintenance.json`), contrôle d'étanchéité selon la charge en t éq. CO2, carnet d'interventions (photo, mesures, pièces), repères 3D (rouge : en retard, orange : en cours), rapport PDF avec signature au doigt ou à la souris |
| Énergie | consommations annuelles, ratio kWh/m².an, gains estimés (chaudière, PAC, isolation, fenêtres, régulation) avec hypothèses affichées, export PDF |
| Défis | questions générées depuis la maquette, correction avec tolérance, score, PDF du résultat, mode prof protégé par code (1234 au départ, modifiable) pour les corrigés et l'historique |

Raccourcis (Windows) : `Ctrl+O` ouvrir, `F` cadrer, `H` masquer, `I` isoler, `A` tout afficher, `Échap` désélectionner, `F11` plein écran.

## Où sont enregistrés les fichiers

| Plateforme | Exports (PDF, CSV, sauvegardes) | Données de l'appli |
| --- | --- | --- |
| Windows | boîte « Enregistrer sous », `Documents\Bimys` par défaut, le dernier dossier utilisé est mémorisé | IndexedDB dans `%APPDATA%\Bimys` |
| Android | `Documents/Bimys` (bouton **Partager** après chaque export) | stockage interne de l'application |
| Navigateur (test) | dossier de téléchargement | IndexedDB du navigateur |

Paramètres > Sauvegarde : export / restauration JSON de toutes les données locales (réglages, interventions avec photos et signatures, saisies de déperditions, bilans énergétiques, résultats des défis).

## Structure du projet

```
bimys/
├── src/
│   ├── core/          calculs purs (testés) : extraction IFC, lots, métré, nomenclature,
│   │                  déperditions, cohérence, maintenance, énergie, défis, CSV
│   ├── worker/        lecture IFC dans un Web Worker (web-ifc en WebAssembly)
│   ├── viewer/        vue 3D three.js (géométrie fusionnée par lot et couleur, BVH)
│   ├── ui/            interface (pages, icônes, signature)
│   ├── pdf/           rapports jsPDF + jspdf-autotable (police DejaVu embarquée)
│   ├── store/         IndexedDB (idb)
│   ├── platform/      Windows (Electron), Android (Capacitor), navigateur
│   └── data/maintenance.json   check-lists d'entretien éditables
├── public/samples/    maquettes exemple IFC4 (chaudière gaz, PAC air/eau)
├── public/wasm/       moteur web-ifc copié au build depuis node_modules (jamais de CDN)
├── electron/          processus principal et preload Windows
├── android/           projet Capacitor (plugin natif « Ouvrir avec » : BimysIntentPlugin.java)
├── build/             icônes (icon.png, icon.ico)
├── keystore/          clé de signature Android (voir plus bas)
├── tests/             tests Vitest des calculs sur la maquette exemple
└── tools/             generate_maquette.py (IfcOpenShell, non embarqué), icons.cjs, screens.cjs
```

## Reconstruire

Prérequis : Node.js 22, et selon la cible : Java 21 + SDK Android (Android Studio), ou Windows pour l'installeur.

```bash
cd bimys
npm ci
npm test                 # tests des calculs
npm run dev              # version navigateur pour développer
npm run build            # application web dans dist/
```

Android (APK release signée dans `android/app/build/outputs/apk/release/`) :

```bash
npm run android:release
```

Windows (installeur et portable dans `release/`, à lancer sous Windows) :

```bash
npm run dist:win
```

Maquettes exemple (Python 3 + `pip install ifcopenshell`) :

```bash
npm run maquette
```

Icônes et écrans de démarrage, captures d'écran de contrôle :

```bash
npm run icons
npm run screens
```

Les GlobalId de la maquette sont reproductibles : régénérer le fichier ne casse pas les interventions et saisies déjà enregistrées.

## Compléter les check-lists de maintenance

Éditez `src/data/maintenance.json` puis reconstruisez, ou importez un fichier JSON dans Paramètres > Check-lists de maintenance (pris en compte immédiatement, sans reconstruire). Chaque type contient `detection` (classes IFC, types prédéfinis, mots-clés), `periodiciteMois`, `checklist` et `mesures`. Le premier type qui correspond est retenu.

## Clé de signature Android

- Fichier : `keystore/bimys-release.jks` (JKS, RSA 4096, valable jusqu'en 2056)
- Alias : `bimys`
- Mot de passe (magasin et clé) : dans `keystore/keystore.properties`
- Empreinte SHA-256 : `5A:CA:E3:44:31:7B:84:A1:7B:D0:B3:5E:8D:0D:D2:88:1F:42:3C:56:66:DD:7B:CD:B1:4E:7E:94:97:71:EE:2D`

Toutes les versions futures doivent être signées avec cette clé (sinon la mise à jour ne s'installe pas par-dessus et les données sont perdues). Pensez à incrémenter `versionCode` et `versionName` dans `android/app/build.gradle` et `version` dans `package.json`.

Le dossier `keystore/` n'est pas publié tant que le dépôt GitHub est public. Pour que la CI signe l'APK : soit le dépôt passe en privé et le dossier est poussé, soit vous ajoutez les secrets `BIMYS_KEYSTORE_BASE64` (contenu du .jks en base64) et `BIMYS_KEYSTORE_PASSWORD` dans Settings > Secrets and variables > Actions. Sans clé, la CI produit une APK de test (debug) clairement nommée.

## Licences des dépendances

| Composant | Licence | Vente sur le Play Store |
| --- | --- | --- |
| three.js, three-mesh-bvh | MIT | OK |
| web-ifc | MPL-2.0 | OK (code non modifié ; si vous modifiez web-ifc lui-même, publier ces fichiers modifiés) |
| jsPDF, jspdf-autotable | MIT | OK |
| idb | ISC | OK |
| Capacitor (core, Filesystem, Share, Splash Screen) | MIT | OK |
| Electron, electron-builder | MIT (Chromium : BSD et tiers, fichier LICENSES.chromium.html fourni) | OK |
| DejaVu Sans (sous-ensemble embarqué) | Bitstream Vera / domaine public | OK |
| IfcOpenShell (outil de génération seulement, non distribué) | LGPL-3.0 | sans objet |

Aucune licence GPL ni licence restrictive n'est embarquée. Les marques et numéros de série de la maquette sont fictifs.
