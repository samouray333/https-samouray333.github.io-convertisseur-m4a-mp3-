# Transferys : installation et utilisation (pas à pas)

## 1. Installer sur le PC Windows

1. Double-cliquez sur **Transferys-Setup-1.0.0.exe**.
2. Si Windows affiche « Windows a protégé votre ordinateur » : cliquez sur **Informations complémentaires** puis **Exécuter quand même** (l'installateur n'est pas signé par un certificat payant).
3. Acceptez la demande d'autorisation (droits administrateur : c'est ce qui permet d'ouvrir Transferys dans le pare-feu).
4. Suivant, Suivant, Terminer. Transferys se lance.

Version portable (sans installation) : dézippez **Transferys-Portable-1.0.0.zip** et lancez `Transferys.exe`. Au premier lancement, Windows demande l'accès réseau : cochez **Réseaux privés** puis **Autoriser**.

## 2. Installer sur le téléphone Android

1. Copiez **Transferys-1.0.0.apk** sur le téléphone (câble, mail, Drive…) et touchez-le.
2. Si Android bloque : autorisez « Installer des applis inconnues » pour l'appli qui ouvre l'APK (Fichiers, Chrome…).
3. Ouvrez Transferys et suivez les 3 écrans du guide (donnez un nom : « Tel Quentin »).
4. Acceptez les **notifications** (pour voir la progression).
5. Conseillé : Réglages de Transferys > **Ne pas limiter la batterie** (évite les coupures écran éteint).

## 3. Connecter les deux appareils (une seule fois)

1. Les deux appareils sur **le même Wi-Fi** (ou le PC connecté au point d'accès du téléphone).
2. Transferys ouvert sur les deux. Chacun voit l'autre dans « Appareils à proximité » au bout de quelques secondes.
3. Sur le téléphone, touchez **Appairer** à côté du PC.
4. Le PC affiche un **code à 6 chiffres** : tapez-le sur le téléphone.
5. C'est fait : les deux appareils sont « de confiance » et se reconnaîtront ensuite.

S'ils ne se voient pas : sur le PC, **Ajouter > Mon QR code** ; sur le téléphone, **Ajouter > Scanner** et visez l'écran du PC. Ou saisissez l'adresse IP affichée en haut de l'écran du PC.

## 4. Envoyer du téléphone vers le PC

- Dans Transferys : **Envoyer des fichiers**, **Photos et vidéos** ou **Dossier**, puis touchez **Envoyer** à côté du PC.
- Ou depuis la galerie (ou n'importe quelle appli) : **Partager > Transferys**, puis **Envoyer**.
- Le PC demande « Tel Quentin veut vous envoyer… » : cliquez **Accepter**.
- Les fichiers arrivent dans **Téléchargements\Transferys** sur le PC.

## 5. Envoyer du PC vers le téléphone

- Glissez-déposez des fichiers ou dossiers dans la fenêtre Transferys, puis **Envoyer** à côté du téléphone.
- Ou clic droit sur un fichier / dossier dans l'explorateur : **Envoyer avec Transferys** (Windows 11 : « Afficher d'autres options »), ou **Envoyer vers > Transferys** pour plusieurs fichiers d'un coup.
- Acceptez sur le téléphone. Les fichiers arrivent dans **Téléchargements/Transferys** (visibles dans la galerie).

## 6. Pendant un transfert

- Onglet **Transferts** : progression, vitesse, temps restant, boutons **Pause**, **Reprendre**, **Annuler**.
- Si le Wi-Fi coupe : Transferys réessaie tout seul pendant 10 minutes et reprend où il s'était arrêté.
- Le PC peut rester fermé dans la **zone de notification** (icône près de l'horloge) : il reçoit quand même.

## 7. Réglages utiles

Nom de l'appareil, dossier de réception, thème clair/sombre, confirmation avant réception, gestion des doublons (renommer / remplacer / ignorer), lancement au démarrage de Windows, appareils de confiance (retirer un appareil à tout moment).

## Problèmes fréquents

- **« Le PC ne répond pas » / le téléphone voit le PC mais n'arrive pas à s'y connecter** : pare-feu Windows. Réinstallez avec l'installateur, ou Démarrer > « Autoriser une application via le Pare-feu Windows » > cochez Transferys en **Privé**. Vérifiez aussi que le Wi-Fi du PC est en réseau **Privé**.
- **Aucun appareil détecté** : Wi-Fi « invité » ou isolation des clients sur la box. Utilisez le QR code ou le réseau principal.
- **Réinstallation de l'appli** : retirez l'appareil des appareils de confiance des deux côtés puis appairez à nouveau.
