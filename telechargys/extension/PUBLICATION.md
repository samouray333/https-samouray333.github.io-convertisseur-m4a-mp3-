# Publier l'extension Telechargys en « non répertoriée »

« Non répertoriée » : l'extension est hébergée par la boutique (installation en un clic, mises à jour automatiques,
plus de mode développeur), mais elle n'apparaît dans aucune recherche. Seules les personnes à qui tu donnes le lien
peuvent l'installer. Le code de l'appli et ton dépôt GitHub restent privés.

Les paquets sont fabriqués par `build.sh` dans `livraison/` :

- `Telechargys-extension-chrome.zip` : Chrome, Edge, Brave, Opera
- `Telechargys-extension-firefox.zip` : Firefox

## 1. Chrome Web Store (Chrome, Brave, Opera)

1. Crée un compte développeur sur https://chrome.google.com/webstore/devconsole (5 $ une seule fois).
2. « Nouvel élément » : envoie `Telechargys-extension-chrome.zip`.
3. Onglet **Fiche** : reprends les textes ci-dessous ; icône `icons/128.png` ; au moins une capture 1280 x 800
   (fournies dans `extension/captures/`).
4. Onglet **Confidentialité** : objectif unique, justification des autorisations (ci-dessous), et l'adresse de la
   politique de confidentialité (voir section 4).
5. Onglet **Distribution** : visibilité **« Non répertorié »**. Envoie pour examen (quelques jours la première fois).
6. Une fois acceptée, la page de l'extension te donne le lien d'installation à partager.

## 2. Microsoft Edge Add-ons (Edge)

https://partner.microsoft.com/dashboard/microsoftedge (gratuit) : même zip, mêmes textes. Edge n'a pas de mode
« non répertorié » officiel ; si tu ne veux pas de fiche visible, les utilisateurs d'Edge peuvent installer la version
du Chrome Web Store (Edge l'accepte après avoir cliqué sur « Autoriser les extensions d'autres magasins »).

## 3. Firefox

https://addons.mozilla.org/developers/ > « Soumettre un nouveau module » > choisis **« Sur votre propre site »**
(distribution autonome, non listée). Envoie `Telechargys-extension-firefox.zip` : Mozilla le signe automatiquement
(quelques minutes) et te donne un fichier `.xpi`. Ce fichier s'installe en le glissant dans Firefox et reste installé
après redémarrage. Pour une nouvelle version, on renvoie le zip et on redonne le nouveau `.xpi`.

## 4. Politique de confidentialité (exigée par le Chrome Web Store)

La boutique demande une adresse web publique pour ce texte. Seule cette page est publique, pas le code. Le plus simple :
crée un document Google Docs avec le texte de `confidentialite.html` (ou ouvre ce fichier, copie le texte),
puis « Partager > Toute personne disposant du lien > Lecteur » et colle ce lien dans la boutique.

## Textes de la fiche

**Nom** : Telechargys : intégration navigateur

**Résumé (132 caractères max)** : Envoie vos téléchargements et les vidéos des pages à Telechargys, le gestionnaire de téléchargements accéléré.

**Objectif unique** : confier les téléchargements et les vidéos du navigateur à l'application Telechargys installée sur l'ordinateur.

**Description** :

Telechargys accélère vos téléchargements (jusqu'à 32 connexions par fichier), les reprend après une coupure et les range automatiquement. Cette extension relie votre navigateur à l'application Telechargys installée sur votre ordinateur :

- les téléchargements du navigateur sont confiés à Telechargys (Alt + clic pour garder le navigateur) ;
- bouton « Télécharger cette vidéo » sur les vidéos des pages, flux HLS et DASH compris ;
- clic droit : télécharger un lien, les liens sélectionnés ou tous les fichiers d'une page ;
- un lien expiré se répare en recliquant dessus ;
- liste des vidéos et sons détectés sur la page.

L'application Telechargys (Windows) doit être installée. Les contenus protégés (DRM) et YouTube ne sont pas pris en charge.

## Justification des autorisations

- **downloads** : reprendre les téléchargements lancés par le navigateur pour les confier à Telechargys.
- **contextMenus** : menu clic droit « Télécharger avec Telechargys ».
- **cookies** : transmettre à Telechargys les cookies du site, nécessaires pour les fichiers réservés aux utilisateurs connectés.
- **webRequest** : repérer les vidéos et les sons chargés par la page.
- **scripting, activeTab, tabs** : lire les liens de la page ou de la sélection quand l'utilisateur le demande, et afficher le bouton sur les vidéos.
- **storage** : mémoriser l'autorisation donnée par l'application.
- **Accès à tous les sites** : l'extension doit pouvoir capter un téléchargement ou une vidéo sur n'importe quel site.
- **Code distant** : aucun.

## Signer l'installeur Windows (facultatif)

Sans signature, Windows affiche « Windows a protégé votre ordinateur » au premier lancement de l'installeur
(cliquer sur « Informations complémentaires » puis « Exécuter quand même »). Pour un usage entre proches, ce n'est
pas gênant. Pour supprimer l'alerte, il faut un certificat de signature de code :

- certificat « OV » auprès d'une autorité (Certum, Sectigo, SSL.com…) : environ 100 à 400 € par an, l'alerte
  disparaît après quelques centaines de téléchargements (réputation SmartScreen) ;
- certificat « EV » : plus cher, mais l'alerte disparaît immédiatement.

`build.sh` signe tout seul si on lui donne le certificat :
`TY_SIGN_PFX=moncertificat.pfx TY_SIGN_PASS=motdepasse ./build.sh`
(les certificats récents sur clé matérielle demandent un outil fourni par l'autorité : la commande `sign()` du script
est l'endroit à adapter).
