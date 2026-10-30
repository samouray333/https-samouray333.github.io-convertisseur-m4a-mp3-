# Lisys : dossier Google Play

Tout ce qu'il faut copier-coller dans la Play Console, dans l'ordre où elle le demande.

- Package : `com.qmtech.lisys` (ne pourra plus changer)
- Éditeur : QMTech
- Fichier à envoyer : `release/Lisys-1.5.aab` (signé avec la clé d'envoi `lisys-release.jks`, alias `lisys`)
- Politique de confidentialité : `https://samouray333.github.io/https-samouray333.github.io-convertisseur-m4a-mp3-/lisys/confidentialite.html`
  (la page doit être en ligne : fusionner la branche dans `main`, vérifier que GitHub Pages est activé, et remplacer `[ADRESSE E-MAIL DE CONTACT]` dans `confidentialite.html`)

---

## 1. Créer l'appli

| Champ | Valeur |
|---|---|
| Nom de l'appli | Lisys : lecture à voix haute |
| Langue par défaut | Français (France) – fr-FR |
| Appli ou jeu | Appli |
| Gratuite ou payante | Gratuite (on peut passer de payante à gratuite, jamais l'inverse) |

## 2. Fiche principale du Store

**Nom (30 caractères max)** :
```
Lisys : lecture à voix haute
```

**Description courte (80 caractères max)** :
```
Lit à voix haute documents, pages web, photos et l’écran. Pour les malvoyants.
```

**Description complète** :
```
Lisys lit à voix haute tout ce que vous avez du mal à lire : vos documents, les pages web, le courrier papier et même ce qui est affiché dans vos autres applis. Pensé pour les personnes malvoyantes, les personnes dyslexiques et tous ceux qui préfèrent écouter.

📄 VOS DOCUMENTS
• PDF, Word (.docx), OpenOffice (.odt), livres EPUB, RTF, HTML, fichiers texte
• Ouvrez-les depuis Lisys, ou « Partager » / « Ouvrir avec » depuis n'importe quelle appli
• Lisys reprend là où vous vous étiez arrêté

📷 LE PAPIER ET LES PHOTOS
• Prenez en photo un courrier, une notice, une boîte de médicament : Lisys lit le texte
• Les PDF scannés sont aussi lus, page par page
• La reconnaissance de texte fonctionne sans internet, sur le téléphone

🌐 LES PAGES WEB
• Collez une adresse ou partagez une page depuis votre navigateur
• Lisys garde l'article et retire les menus, publicités et bandeaux

🔊 LE BOUTON FLOTTANT (dans toutes les applis)
• Un appui : Lisys lit le texte affiché à l'écran (mail, message, site, appli…)
• Appui long : lecture au doigt, Lisys lit la phrase sous votre doigt et l'entoure en jaune
• Deux doigts pour faire défiler la page
• Bulle réglable : 5 tailles, 8 couleurs bien contrastées
• Options : bandeau en très gros texte, lecture avec les boutons de volume, annonce des messages reçus

👁 CONFORT DE LECTURE
• Phrase et mot lus surlignés
• Mode loupe : la phrase en cours en très gros caractères
• Thèmes clair, sombre, sépia et contraste élevé jaune sur noir
• Texte de 14 à 60, vitesse de 0,5× à 3×, choix de la voix
• Lecture écran éteint, commandes sur l'écran de verrouillage et le casque
• Minuterie de sommeil
• Création d'un fichier audio (.m4a) à partir d'un document

🔒 RESPECT DE LA VIE PRIVÉE
• Aucun compte, aucune publicité, aucune collecte de données
• Tout est traité sur votre téléphone

Lisys utilise le service d'accessibilité d'Android uniquement pour lire à voix haute le texte affiché quand vous le demandez (bouton flottant, lecture au doigt) et, si vous activez l'option, pour annoncer les messages reçus. Ces informations ne quittent jamais votre téléphone.
```

**Éléments graphiques**
- Icône 512 × 512 : `play-store/icone-512.png`
- Image de présentation 1024 × 500 : `play-store/banniere-1024x500.png`
- Captures d'écran téléphone : **à faire sur un vrai téléphone** (de 2 à 8, format portrait). Idées, dans l'ordre :
  1. L'accueil de Lisys
  2. Un document en lecture, phrase surlignée
  3. Le thème contraste élevé (jaune sur noir) avec un grand texte
  4. La bulle 🔊 par-dessus un site ou un mail
  5. La lecture au doigt avec le cadre jaune
  6. La lecture d'une photo de courrier

**Catégorie** : Productivité (ou Outils). **Tags** : Accessibilité, Lecture, Synthèse vocale.
**Coordonnées** : une adresse e-mail (obligatoire, visible sur la fiche). Site web facultatif.

## 3. Contenu de l'appli (Politique de l'appli)

**Règles de confidentialité** : l'adresse de la page ci-dessus.

**Accès à l'appli** : « Toutes les fonctionnalités sont disponibles sans restriction d'accès » (pas de compte).

**Annonces** : « Non, mon appli ne contient pas d'annonces ».

**Classification du contenu** (questionnaire) : catégorie « Utilitaire, productivité, communication ou autre ».
- Violence, sexualité, langage grossier, drogues, jeux d'argent : Non partout.
- L'appli permet-elle aux utilisateurs d'interagir ou d'échanger du contenu ? Non.
- Partage de la position ? Non.
- Achats numériques ? Non.
- Navigateur web ou moteur de recherche ? **Oui, en partie** : Lisys a un navigateur intégré qui affiche des pages web choisies par l'utilisateur. La classification sera probablement « Tout public » ou « 12 ans et + » à cause de l'accès libre à internet, c'est normal.

**Public cible** : 18 ans et plus. L'appli convient à tous, mais choisir « adultes » évite les exigences du programme Familles.

**Appli d'actualités** : Non. **Appli de santé** : Non (c'est un outil d'accessibilité, pas une appli médicale). **Appli gouvernementale** : Non. **Fonctionnalités financières** : Aucune.

### Sécurité des données
- **Votre appli collecte-t-elle ou partage-t-elle des données utilisateur ?** → **Non**.
  Explication (pour toi) : selon les règles Google, les données traitées uniquement sur l'appareil, sans être envoyées au développeur ni à un tiers, ne sont pas « collectées ». Lisys n'a aucun serveur. Le téléchargement d'une page web demandée par l'utilisateur va directement au site concerné, comme dans un navigateur.
- Chiffrement en transit : sans objet (pas de collecte).
- Suppression des données : l'utilisateur peut tout effacer dans l'appli ou en la désinstallant.

### Autorisations et API sensibles

**API d'accessibilité** (formulaire « Utilisation de l'API AccessibilityService ») :
- L'appli est-elle un outil d'accessibilité ? **Oui** (déclaré dans l'appli avec `isAccessibilityTool="true"`).
- Description à coller :
```
Lisys est une appli de lecture à voix haute pour les personnes malvoyantes ou ayant des difficultés de lecture. Le service d'accessibilité est indispensable à sa fonction principale « bouton flottant » : quand l'utilisateur appuie sur la bulle Lisys (ou sur le bouton d'accessibilité, ou deux fois sur volume bas s'il a activé cette option), l'appli récupère le texte affiché à l'écran pour le lire à voix haute. En mode « lecture au doigt », elle lit la phrase située sous le doigt de l'utilisateur et l'entoure d'un cadre pour l'aider à suivre. Elle peut aussi faire défiler la page à la demande (geste à deux doigts) et, si l'utilisateur active l'option, annoncer à voix haute les messages reçus. Le texte est traité uniquement sur l'appareil, au moment où l'utilisateur le demande ; il n'est ni envoyé sur internet, ni partagé. Avant toute activation, l'appli affiche une information détaillée et demande l'accord explicite de l'utilisateur.
```
- **Vidéo** (obligatoire, YouTube en « non répertoriée », 30 s à 2 min). Script :
  1. Ouvrir Lisys, appuyer sur « Lire les autres applis et sites ».
  2. Montrer l'écran « Autorisation d'accessibilité » en entier, puis appuyer sur « J'accepte ».
  3. Activer « Lisys : bouton de lecture » dans les réglages d'accessibilité d'Android.
  4. Ouvrir un site ou un mail, appuyer sur la bulle 🔊 : Lisys lit.
  5. Appui long : lecture au doigt, avec le cadre jaune.

**Services au premier plan** (formulaire « Autorisations des services de premier plan ») :
- `mediaPlayback` : « Lecture audio à voix haute d'un document choisi par l'utilisateur. La lecture continue écran éteint ou appli en arrière-plan, avec les commandes dans la notification ; l'utilisateur la démarre et l'arrête lui-même. »
- `dataSync` : « Création, à la demande de l'utilisateur, d'un fichier audio (.m4a) à partir d'un document : traitement local du fichier par la synthèse vocale puis encodage, avec progression et bouton Annuler dans la notification. »
- Vidéo : lancer une lecture puis éteindre l'écran (la lecture continue) ; dans un document, menu ⋮ > « Créer un fichier audio » et montrer la notification de progression.

## 4. Tests obligatoires avant la publication

Pour un compte développeur personnel récent, Google exige un **test fermé avec au moins 12 testeurs inscrits pendant 14 jours d'affilée** avant d'autoriser la publication pour tout le monde.
1. Tests > Tests fermés > créer un canal, envoyer `Lisys-1.5.aab`.
2. Ajouter les adresses Gmail des testeurs (famille, amis, club…).
3. Leur envoyer le lien d'inscription : ils installent Lisys depuis le Play Store et la gardent 14 jours.
4. Ensuite : Production > demander l'accès, répondre aux questions sur le test, publier.

## 5. Signature

À la première publication, choisir **« Laisser Google gérer et protéger la clé de signature »** (Play App Signing). `lisys-release.jks` devient alors la **clé d'envoi** : toutes les mises à jour (`.aab`) doivent être signées avec elle. `./build.sh` puis `./build-aab.sh` le font automatiquement.
