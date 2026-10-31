# Publier Calorys sur le Google Play Store (compte QMTech)

Tout est prêt dans ce dossier. Il reste les clics dans la Play Console, dans l'ordre ci-dessous.

| Fichier | À quoi il sert |
|---|---|
| `Calorys-1.5.1.aab` (dans `release/`) | L'appli à envoyer (Android App Bundle signé avec ta clé d'importation) |
| `icone-512.png` | Icône de la fiche (512 × 512) |
| `banniere-1024x500.png` | Bannière de la fiche (« Image de présentation ») |
| `captures/01…08.png` | Captures d'écran téléphone (1080 × 2160) |
| `../site/confidentialite.html` | Copie de la politique de confidentialité |

---

## Étape 0 : rendre la politique de confidentialité publique (1 minute)

Le document « Calorys - Politique de confidentialité » est déjà dans ton Google Drive :
https://docs.google.com/document/d/1VvGzBh47u9nN8BlWkMAGq6YrBVnhbmG-kdH4GWH0DHY/edit

1. Ouvre-le, clique **Partager**.
2. Sous « Accès général », choisis **Tous les utilisateurs disposant du lien**, rôle **Lecteur**. Valide.
3. L'adresse à donner à Google (c'est aussi celle du bouton dans Calorys > À propos) :
   **https://docs.google.com/document/d/1VvGzBh47u9nN8BlWkMAGq6YrBVnhbmG-kdH4GWH0DHY/view**

Vérifie-la dans une fenêtre de navigation privée : elle doit s'ouvrir sans connexion.

---

## Étape 1 : créer l'appli

Play Console > **Créer une application** :
- Nom : **Calorys**
- Langue par défaut : **Français (France) – fr-FR**
- Type : **Application** · **Gratuite**
- Coche les deux déclarations (règles du programme, lois d'exportation).

---

## Étape 2 : la fiche Play Store

Menu **Développer l'audience > Fiche Play Store principale**.

**Nom de l'application** (30 max) :
```
Calorys : calories et jeûne
```

**Description courte** (80 max) :
```
Calories, eau, poids et jeûne 16:8, sans compte. Tes données restent chez toi.
```

**Description complète** :
```
Calorys t'aide à manger mieux et à atteindre ton poids, sans compte, sans publicité et sans envoyer ton journal sur Internet. Tout reste sur ton téléphone.

COMPTEUR DE CALORIES COMPLET
• Plus de 3 000 aliments de la table Ciqual (ANSES) et un catalogue de près de 900 000 produits de marque Open Food Facts, utilisable hors ligne
• Scan des codes-barres, ajout rapide, recettes, « Comme hier »
• Glucides, protéines, lipides, fibres et objectifs adaptés à ton profil
• Analyse d'une photo de repas par IA (facultatif, avec ta propre clé Google Gemini)

OBJECTIF ADAPTATIF
• Objectif calculé avec l'équation de Mifflin-St Jeor, puis ajusté à ta vraie dépense mesurée sur ton journal et tes pesées
• Courbe de poids lissée pour ne pas paniquer à chaque variation d'eau
• Mode sèche avec date de pesée pour les sportifs

JEÛNE INTERMITTENT ET PROGRAMMES
• Minuteur de jeûne 16:8, 18:6, 20:4… avec les étapes du jeûne
• Programmes prêts à l'emploi : 16:8 sans petit-déjeuner, 18:6, 5:2, rééquilibrage 3 repas, sèche sports de combat
• Le programme règle l'appli pour toi : fenêtre de repas, repas supprimés, eau à boire et notifications
• Crée et importe tes propres programmes (fichier JSON)

EAU ET RAPPELS
• Objectif d'eau réaliste, ajusté au poids et à la transpiration des séances
• Rappels à tes heures, un grand verre avant chaque repas, rappels vocaux en option
• Rappels de repas, de pesée et de fin de jeûne, même appli fermée

ACTIVITÉS
• Marche et course (y compris sur tapis à 4, 5, 5,5 et 8 km/h) avec estimation des pas
• Musculation, sports de combat et séances avec intensité (RPE)

ET AUSSI
• Analyse sur 7, 30 et 90 jours, rapport du jour imprimable en PDF
• Ceintures et défis pour rester motivé
• Thèmes de couleurs, mode sombre
• Synchronisation chiffrée avec la version Windows de Calorys, directement sur ton Wi-Fi
• Export CSV et sauvegarde JSON

TES DONNÉES T'APPARTIENNENT
Pas de compte, pas de serveur, pas de traceur. Les seules connexions sont facultatives : téléchargement du catalogue, recherche Open Food Facts, analyse photo avec ta clé.

Calorys ne remplace pas l'avis d'un médecin ou d'un diététicien. Le jeûne est déconseillé aux mineurs, aux femmes enceintes ou allaitantes et aux personnes diabétiques ou ayant des troubles alimentaires.

Données produits : Open Food Facts (licence ODbL), table Ciqual de l'ANSES (Licence Ouverte).
```

**Éléments graphiques** :
- Icône : `icone-512.png`
- Image de présentation : `banniere-1024x500.png`
- Captures téléphone : les 8 fichiers de `captures/`, dans l'ordre.
- Tablettes : facultatif, tu peux laisser vide.

**Catégorie** (Paramètres de la fiche) : Application > **Santé et remise en forme**.
Tags conseillés : *Compteur de calories*, *Nutrition*, *Perte de poids*, *Jeûne*.
**Coordonnées** : l'e-mail de contact QMTech (il sera public sur la fiche). Site web : facultatif.

---

## Étape 3 : « Contenu de l'application » (Règles et programmes > Contenu de l'application)

### Politique de confidentialité
Colle l'adresse de l'étape 0.

### Accès à l'application
**Toutes les fonctionnalités sont disponibles sans restriction d'accès** (pas de connexion).

### Annonces
**Non, mon application ne contient pas d'annonces.**

### Classification du contenu
Questionnaire IARC, adresse e-mail QMTech, catégorie **« Toutes les autres catégories d'applications »** (pas un jeu). Réponds **Non** partout :
violence, peur, sexualité, grossièretés, drogues, alcool, tabac, jeux d'argent, interactions entre utilisateurs, partage de la position, achats numériques.
Résultat attendu : PEGI 3 / Tout public.

### Public cible et contenu
- Tranche d'âge : **18 ans et plus** uniquement (à cause du jeûne et de la perte de poids).
- L'appli n'est pas destinée aux enfants : **Non** à « susceptible d'attirer les enfants ».

### Sécurité des données
- « Votre application collecte-t-elle ou partage-t-elle des types de données obligatoires ? » **Oui** (à cause des fonctions facultatives en ligne).
- « Toutes les données sont-elles chiffrées en transit ? » **Oui**.
- « Proposez-vous un moyen de demander la suppression des données ? » **Non** : QMTech ne conserve rien ; l'utilisateur efface tout dans l'appli (Profil > Tout effacer).

Types de données à déclarer :

| Type | Collecté | Partagé | Facultatif | Éphémère | Finalité |
|---|---|---|---|---|---|
| Photos et vidéos > **Photos** | Oui | Non | Oui (analyse IA lancée par l'utilisateur) | Non | Fonctionnalités de l'application |
| Activité dans les applis > **Historique des recherches dans l'application** | Oui | Non | Oui (recherche en ligne Open Food Facts) | Non | Fonctionnalités de l'application |

Tout le reste (santé, poids, repas, nom, position…) : **non collecté**, car ça ne quitte jamais le téléphone. La sauvegarde Android de Google ne compte pas comme collecte.

### Application gouvernementale, fonctionnalités financières, actualités
Non / Aucune / Non.

### Applis de santé (déclaration)
Coche **Nutrition et gestion du poids** et **Activité physique et remise en forme**.
Ce n'est **pas** un dispositif médical, pas de recherche sur des sujets humains, pas d'accès à Santé Connect.

### Identifiant publicitaire
**Non**, l'appli n'utilise pas l'identifiant publicitaire.

---

## Étape 4 : signature de l'appli

À la première importation, Google propose « Signature d'application par Google Play » :
- Choisis **Laisser Google générer et gérer la clé de signature** (recommandé).
- Le fichier `.aab` est déjà signé avec ta clé d'importation (`keystore/calorys-release.jks`, mot de passe dans `CLE-SIGNATURE.txt`). **Garde ce fichier précieusement** : sans lui, plus de mises à jour (Google peut la réinitialiser, mais c'est long).

⚠️ La version Play Store sera signée par Google : elle ne pourra pas s'installer par-dessus l'APK installée à la main. Sur ton téléphone : Profil > Sauvegarder mes données (ou synchronise avec le PC), désinstalle l'ancienne, installe depuis le Play Store, puis Profil > Restaurer une sauvegarde.

---

## Étape 5 : test fermé (obligatoire pour un compte personnel)

Un compte développeur personnel créé après novembre 2023 doit faire un **test fermé avec au moins 12 testeurs pendant 14 jours d'affilée** avant d'accéder à la production. (Si QMTech est enregistré comme **organisation**, cette étape n'est pas obligatoire : passe directement à l'étape 6.)

1. **Tester > Tests fermés > Créer un canal** (ou utiliser « Alpha »).
2. **Testeurs** : crée une liste avec les adresses Gmail d'au moins 12 personnes (famille, amis, collègues avec un téléphone Android).
3. **Créer une release** : importe `Calorys-1.5.1.aab`. Notes de version :
   ```
   Première version de Calorys sur le Play Store : compteur de calories, jeûne intermittent, programmes, eau et rappels (aussi vocaux).
   ```
4. Envoie la release en examen (souvent 1 à 3 jours la première fois).
5. Une fois validée, copie le **lien de participation** et envoie-le aux testeurs : chacun clique « Devenir testeur », puis installe Calorys depuis le Play Store **et la garde installée 14 jours**. Demande-leur de l'ouvrir de temps en temps.
6. Au bout de 14 jours : **Tableau de bord > Demander l'accès à la production**, et réponds au petit questionnaire (comment tu as trouvé tes testeurs, ce qu'ils ont remonté, ce que tu as amélioré).

---

## Étape 6 : production

1. **Production > Pays/régions** : France, Belgique, Suisse, Luxembourg, Canada (ou tous les pays).
2. **Créer une release** avec le même `.aab` (ou une version plus récente), puis **Envoyer pour examen**.
3. L'examen prend en général de quelques heures à quelques jours.

---

## Mises à jour suivantes

1. Augmente `versionCode` (+1) et `versionName` dans `android/AndroidManifest.xml` (et les autres numéros, voir le README).
2. Construis l'AAB :
   ```
   cd android
   FLAVOR=play BUNDLETOOL=/chemin/bundletool-all.jar ANDROID_JAR=… ANDROID_RES_JAR=… KS_PASS='…' ./build.sh
   ```
   Le fichier sort dans `android/build-play/`.
3. Play Console > la piste voulue > Créer une release > importe le `.aab`.

---

## À savoir

- **Différences avec l'APK directe** : la version Play Store ne demande pas d'office les alarmes exactes ni l'exception batterie (règles Google). Calorys affiche alors dans Profil > Rappels des boutons rouges « Activer » et « Ouvrir les réglages batterie » : un appui suffit.
- **Catalogue hors ligne** : il est téléchargé depuis ce dépôt GitHub (branche `main`, sinon la branche de travail actuelle). Ne supprime pas cette branche tant que le catalogue n'est pas aussi sur `main`, sinon le téléchargement du catalogue échouera dans l'appli publiée.
- **Ne cite pas YAZIO** ni d'autre appli dans la fiche (règle « métadonnées trompeuses »).
- **Open Food Facts** : l'attribution est faite dans la fiche et dans Calorys > À propos.
- Calorys vise **Android 16 (API 36)**, comme Google l'exige pour les nouvelles applis depuis fin août 2026.
