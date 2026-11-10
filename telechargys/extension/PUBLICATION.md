# Publier l'extension Telechargys

Deux paquets sont fabriqués par `build.sh` dans `livraison/` :

- `Telechargys-extension-chrome.zip` : Chrome Web Store (sert aussi pour Edge, Brave, Opera)
- `Telechargys-extension-firefox.zip` : addons.mozilla.org

## Chrome Web Store

1. Compte développeur sur https://chrome.google.com/webstore/devconsole (frais d'inscription unique de 5 $).
2. « Nouvel élément », envoyer `Telechargys-extension-chrome.zip`.
3. Fiche : reprendre les textes ci-dessous, ajouter l'icône 128 px (`icons/128.png`) et au moins une capture d'écran 1280 x 800.
4. Onglet « Confidentialité » : coller les justifications ci-dessous et l'adresse de la politique de confidentialité.

Edge : même zip sur https://partner.microsoft.com/dashboard/microsoftedge (gratuit).

## Firefox

https://addons.mozilla.org/developers/ : « Soumettre un nouveau module », envoyer `Telechargys-extension-firefox.zip`. Une fois signé par Mozilla, il reste installé après redémarrage du navigateur.

## Textes de la fiche

**Nom** : Telechargys : intégration navigateur

**Résumé (132 caractères max)** : Envoie vos téléchargements et les vidéos des pages à Telechargys, le gestionnaire de téléchargements accéléré.

**Description** :

Telechargys accélère vos téléchargements (jusqu'à 32 connexions par fichier), les reprend après une coupure et les range automatiquement. Cette extension relie votre navigateur à l'application Telechargys installée sur votre ordinateur :

- les téléchargements du navigateur sont confiés à Telechargys (Alt + clic pour garder le navigateur) ;
- bouton « Télécharger cette vidéo » sur les vidéos des pages, flux HLS et DASH compris ;
- clic droit : télécharger un lien, les liens sélectionnés ou tous les fichiers d'une page ;
- liste des vidéos et sons détectés sur la page.

L'application Telechargys (Windows) doit être installée. Les contenus protégés (DRM) et YouTube ne sont pas pris en charge.

## Justification des autorisations

- **downloads** : reprendre les téléchargements lancés par le navigateur pour les confier à Telechargys.
- **contextMenus** : menu clic droit « Télécharger avec Telechargys ».
- **cookies** : transmettre à Telechargys les cookies du site, nécessaires pour les fichiers réservés aux utilisateurs connectés.
- **webRequest** : repérer les vidéos et les sons chargés par la page.
- **scripting, activeTab, tabs** : lire les liens de la page ou de la sélection quand l'utilisateur le demande.
- **storage** : mémoriser l'autorisation donnée par l'application.
- **Accès à tous les sites** : l'extension doit pouvoir capter un téléchargement ou une vidéo sur n'importe quel site.

## Politique de confidentialité (à publier, par exemple sur GitHub Pages)

L'extension Telechargys ne collecte, ne stocke et ne transmet aucune donnée personnelle à un serveur. Les adresses des fichiers, les cookies du site concerné et le titre de la page sont envoyés uniquement à l'application Telechargys installée sur le même ordinateur (adresse locale 127.0.0.1), et seulement pour effectuer le téléchargement demandé. Aucune donnée n'est partagée avec des tiers.
