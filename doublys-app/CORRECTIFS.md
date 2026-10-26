# Correctifs (après la 1.0.0)

1. **Mise à jour sans perte de données** : si l'enregistrement du projet échoue et que vous choisissez de garder
   vos modifications, l'installateur n'est plus lancé et Doublys ne se ferme plus (`ui/main_window.py`).
2. **Installateur vérifié avant d'être lancé** : empreinte SHA-256 donnée par GitHub (champ `digest` des fichiers
   de Release), sinon fichier `Doublys-Setup-x.y.z.exe.sha256` ou `SHA256SUMS.txt` publié à côté. Empreinte absente
   ou différente : fichier supprimé, installation automatique annulée (`core/updates.py`).
   Conseil (filet de sécurité si GitHub ne fournit pas le `digest`) : ajouter au workflow, après NSIS :
   ```powershell
   Get-ChildItem Doublys-Setup-*.exe | ForEach-Object {
     "$((Get-FileHash $_ -Algorithm SHA256).Hash.ToLower())  $($_.Name)" |
       Out-File -Encoding ascii "$($_.FullName).sha256"
   }
   ```
   puis publier le `.sha256` avec l'exe dans la Release.
3. **Clé DeepSeek** : avertissement dans le journal et à l'écran quand elle n'a pas pu être chiffrée (DPAPI
   indisponible) ; message clair si une clé enregistrée est illisible (`core/secrets.py`, `ui/pages/settings.py`).
4. **Code mort retiré** de `core/textproc.py` (≈ 370 lignes héritées d'AudioLivre : balises de mise en scène,
   dialogues, incises, découpage en segments). La normalisation française est inchangée.
5. **Erreurs silencieuses** : les `except … pass` qui pouvaient cacher une vraie panne sont maintenant journalisés
   (arrêt des moteurs, liste des voix illisible, point d'accès Edge, mise en veille, dossier Documents).
6. **Genre de la voix** : zone « incertaine » de 150 à 185 Hz signalée (journal + page Personnes « incertain, à
   vérifier ») ; un genre choisi à la main n'est plus écrasé quand l'étape « Voix » est relancée ; le genre d'un
   personnage de série est conservé. Le choix « Inconnu » s'appelle « Automatique » (réestimation).

Tests ajoutés : `tests/test_fixes.py` (8 tests). Total : 58 tests OK, autotest complet OK.
