# Bimys 1.3.0 (QMTech)

Visionneuse BIM pédagogique spécialisée génie thermique pour les Bac Pro **ICCER** et **MEE** : ouverture de maquettes IFC, exploration des réseaux, métrés, déperditions, maintenance et défis élèves. Application 100 % hors ligne (aucun serveur, aucun compte, aucune clé API), interface entièrement en français.

- Package Android : `com.qmtech.bimys`, versionCode 5, versionName 1.3.0
- Windows : installeur NSIS (installation par utilisateur, sans droits administrateur, raccourcis menu Démarrer et bureau, désinstallation depuis « Applications et fonctionnalités ») et version portable
- Rendu WebGL standard (aucune dépendance CUDA ou carte Nvidia)
- Interface 100 % en français, y compris les propriétés IFC normalisées (noms de Pset, propriétés, quantités et valeurs traduits, nom IFC d'origine affiché en petit) et les textes internes de Chromium sous Windows

## Télécharger

Les fichiers sont construits par GitHub Actions (workflow `.github/workflows/bimys.yml`) et publiés dans la **Release GitHub `bimys-v1.3.0`** du dépôt :

| Fichier | Usage |
| --- | --- |
| `Bimys-1.3.0.apk` | Android 7.0 et plus, installation directe (autoriser les sources inconnues) |
| `Bimys-Setup-1.3.0.exe` | Installeur Windows 10/11 (64 bits) |
| `Bimys-Portable-1.3.0.exe` | Version portable Windows, sans installation |

## Bibliothèque de maquettes (7 bâtiments complets)

Toutes en IFC4 avec architecture, pièces (surface, hauteur, volume), parois avec U, limites d'espaces, réseaux et équipements renseignés (marque, modèle, puissance, date de mise en service, n° de série fictif, fluide et charge pour les machines frigorifiques). Les émetteurs sont dimensionnés sur les déperditions calculées par Bimys ; quelques erreurs volontaires servent aux exercices.

| Fichier | Bâtiment | Techniques | Erreurs volontaires |
| --- | --- | --- | --- |
| `maison_chaudiere_gaz.ifc` | Maison R+1, 109 m² | Chaudière gaz condensation, radiateurs bitube cuivre / multicouche, ballon 150 L, VMC hygro B | Chambre 2 sous-dimensionnée, entrée surdimensionnée, séjour 2 sans robinet thermostatique, purgeur sans système |
| `maison_pac_air_eau.ifc` | Même maison | PAC air/eau monobloc R410A 2,4 kg (5,01 t éq. CO2), module hydraulique | Idem |
| `maison_plain_pied_pcbt.ifc` | Maison plain-pied RE 2020, 106 m² | PAC R32, plancher chauffant (boucles par pièce, collecteur, thermostats), VMC double flux, ballon thermodynamique | Chambre 3 sous-dimensionnée |
| `immeuble_collectif_r3.ifc` | Immeuble R+3, 14 logements T3 | Chaufferie collective (2 chaudières en cascade), colonnes montantes acier, compteurs d'énergie et d'eau par logement, ECS collective bouclée, VMC collective hygro B | Logement 07 chambre 2 et logement 12 séjour sous-dimensionnés, logement 03 : radiateur sans robinet thermostatique |
| `bureaux_r2_drv.ifc` | Bureaux R+2 | DRV / VRV R410A (2 unités extérieures, cassettes, liaisons frigorifiques, Refnet), CTA d'air neuf double flux, chauffe-eau électriques | Bureau R1-9 et salle de réunion R+2 sous-dimensionnés |
| `clinique_r2.ifc` | Clinique R+2, 64 chambres et consultations | Chaudières + groupe froid R32 38 kg, ventilo-convecteurs 4 tubes, eau glacée, CTA double flux à roue, CTA de bloc opératoire, ECS bouclée 1 500 L | Chambres R1S04 et R2N07 sous-dimensionnées, panneaux des blocs sans robinet thermostatique |
| `cinema_3_salles.ifc` | Cinéma 3 salles (120 à 220 places) | Rooftops réversibles par salle (propriété « Pièce desservie »), gaines rectangulaires, extraction sanitaires, chauffe-eau électrique | Salle 3 : rooftop sous-dimensionné |

Régénération : `npm run maquette` (maisons R+1) et `npm run batiments` (les 5 autres), Python 3 avec `pip install ifcopenshell`. Le moteur générique (`tools/batiments.py`) déduit cloisons, portes, fenêtres et limites d'espaces du plan des pièces : on peut y ajouter d'autres bâtiments en décrivant seulement les pièces et les réseaux.

## Fonctions

| Module | Contenu |
| --- | --- |
| Vue 3D | orbite, zoom, pan, vues dessus / face / iso, coupe horizontale par niveau + plan de coupe libre, mesure de distance, lots colorés (architecture en transparence, chauffage, ECS, eau froide, ventilation, équipements, électrique), isoler / masquer / tout afficher, arborescence Projet > Bâtiment > Niveaux > Pièces > Éléments synchronisée, propriétés avec types IFC traduits |
| Métré | longueurs par réseau, matériau et diamètre (cuivre `int x ext`, PER / multicouche `ext x épaisseur`), filtres par niveau et par réseau, chutes réglables, conditionnement (barres, couronnes, rouleaux) et quantités à commander, colliers estimés, contenance en eau des tubes, surface développée des gaines, raccords et accessoires, bouton « voir en 3D » sur chaque ligne, bon de commande PDF, export CSV et PDF |
| Équipements | nomenclature (générateurs, émetteurs, circulateurs, vases, soupapes, ventilation, régulation, sanitaires), export CSV et PDF |
| Déperditions | méthode par parois (U × S × b × ΔT + ponts thermiques forfaitaires + 0,34 × Qv × ΔT, parois pré-remplies depuis les limites d'espaces IFC) ou volumique (G × V × ΔT), Te de base modifiable (−10 °C par défaut, Saône-et-Loire), Ti par pièce, comparaison avec les émetteurs (sous-dimensionné / correct / surdimensionné, écart en %), correction de puissance selon le régime d'eau, export PDF |
| Cohérence | émetteurs sans robinet thermostatique, pièces humides sans extraction, éléments sans système, pièces chauffées sans émetteur |
| Maintenance | fiches équipements, check-lists (`src/data/maintenance.json`), contrôle d'étanchéité selon la charge en t éq. CO2, carnet d'interventions (photo, mesures, pièces), repères 3D (rouge : en retard, orange : en cours), rapport PDF avec signature au doigt ou à la souris |
| Énergie | consommations annuelles, ratio kWh/m².an, gains estimés (chaudière, PAC, isolation, fenêtres, régulation) avec hypothèses affichées, export PDF |
| Défis | questions générées depuis la maquette, correction avec tolérance, score, PDF du résultat, mode prof protégé par code (1234 au départ, modifiable) pour les corrigés et l'historique |

### Nouveautés 1.3

- Rendu 3D : matériaux réalistes avec éclairage d'ambiance, ombrage d'ambiance (haute qualité), arêtes des objets, fond dégradé, grille au sol. Réglage dans Paramètres > Affichage (qualité automatique, haute ou standard ; arêtes et grille activables)
- Maquettes : coudes, tés et réductions modélisés avec leurs emboîtures
- Métré professionnel : synthèse par réseau, graphique des longueurs, tableaux groupés, conditionnement, quantités à commander, colliers, contenance en eau, surface de tôle, bon de commande

### Version Windows (1.1)

- Barre de menus en français (Fichier, Affichage, Modules, Aide), fichiers récents dans le menu et la liste de raccourcis Windows, exemples, fermeture de maquette, ouverture du dossier des exports
- Taille et position de fenêtre mémorisées, une seule instance (un double-clic sur un .ifc s'ouvre dans la fenêtre existante)
- Démarrage garanti même si la carte graphique est refusée : modules sans 3D, puis bascule proposée en rendu 3D logiciel (Affichage > Rendu 3D logiciel)
- Journal d'erreurs (Aide > Ouvrir le journal d'erreurs), fenêtre « À propos », contrat de licence dans l'installeur
- Vue 3D : cube de navigation, vue orthographique, **plan 2D par niveau** (murs coupés en noir, nom et surface des pièces), clic droit contextuel, sélection multiple (Ctrl+clic), recherche (Ctrl+F), info-bulle au survol, mesure aimantée sur les sommets, points de vue enregistrés, capture PNG avec cartouche, isolement d'un réseau (IfcSystem), barre d'état

Raccourcis (F1 dans l'appli pour la liste complète) : `Ctrl+O` ouvrir, `Ctrl+F` rechercher, `Ctrl+Maj+S` capture, `Ctrl+1` à `Ctrl+8` modules, `F` cadrer, `H` masquer, `I` isoler, `A` tout afficher, `T` transparence, `O` orthographique, `P` plan 2D, `Page préc./suiv.` niveau, `M` mesure, `1` à `4` vues, `Échap` désélectionner, `F11` plein écran.

## Où sont enregistrés les fichiers

| Plateforme | Exports (PDF, CSV, sauvegardes) | Données de l'appli |
| --- | --- | --- |
| Windows | boîte « Enregistrer sous », `Documents\Bimys` par défaut, le dernier dossier utilisé est mémorisé | `%APPDATA%\Bimys` (données, `bimys-config.json`, journal `logs\bimys.log`) |
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

Test automatique de l'application de bureau (18 étapes : menus, ouverture, 3D, clic droit, recherche, plan 2D, exports, fenêtre mémorisée, journal) :

```bash
npm run build && node tools/e2e-electron.cjs
```

Sur Linux sans écran : `xvfb-run -a node tools/e2e-electron.cjs`. La CI lance ce test sur l'exe Windows empaqueté (`release/win-unpacked/Bimys.exe`).

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
