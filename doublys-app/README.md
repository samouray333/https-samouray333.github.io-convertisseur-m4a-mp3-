# 🎬 Doublys — Echo Matras

**Vos vidéos en version française (anglais, japonais, espagnol, allemand…), créées sur votre ordinateur.**
Glissez une vidéo, cliquez sur **« Créer la VF automatiquement »** : Doublys isole les voix, écrit ce qui est dit,
reconnaît qui parle, traduit, donne à chaque personne une voix française proche de la sienne et la cale sur le temps
d'origine. La musique et les bruits sont gardés, la vidéo n'est pas réencodée.

Application Windows (installateur `.exe` ou version portable), 100 % locale par défaut, sans carte graphique.
Construite sur le moteur d'AudioLivre Studio (même dépôt, dossier `audiolivre-studio/`).

---

## ✨ Ce que fait Doublys

| Étape | Outil | Détail |
|---|---|---|
| 1. Extraction | FFmpeg | `original.wav` (44,1 kHz stéréo) et `original16.wav` (16 kHz mono) |
| 2. Séparation | Demucs htdemucs | par blocs de 30 s avec 2 s de contexte (mémoire stable) → `voix.wav` + `fond.wav` (fond = mélange − voix). Option sans séparation : VO baissée de 18 dB sous la VF |
| 3. Transcription | faster-whisper | modèle *small* par défaut (*medium*, *large-v3-turbo* en option), position de chaque mot, filtre de silence, progression |
| 4. Répliques | — | coupure aux fins de phrase, aux silences > 0,7 s, 12 s au plus (coupure préférée après 10 s, sur une virgule ou une pause), fragments < 0,6 s fusionnés |
| 5. Personnes | speechbrain ECAPA | empreinte vocale par réplique, regroupement hiérarchique (cosinus, seuil réglable, nombre maximal optionnel), petits groupes fusionnés, P1…Pn par ordre d'apparition |
| 6. Traduction | Opus-MT / DeepSeek | `opus-mt-tc-big-en-fr` (défaut) ou `opus-mt-en-fr` (rapide), hors ligne ; ou DeepSeek en ligne, par lots, avec le contexte et un nombre de caractères par réplique (≈ 14,5 car./s) |
| 7. Voix | voir ci-dessous | extrait de référence de 12 à 25 s pris dans les répliques de chaque personne (voix isolée), genre estimé par la hauteur |
| 8. Calage | FFmpeg atempo | créneau = début de la réplique → début de la suivante − 0,1 s (au plus 1 s après la fin d'origine). Trop long : accélération jusqu'à ×1,12 ; au-delà, nouvelle synthèse plus rapide (×1,30 au plus, réglable) puis accélération du reste ; sinon alerte « raccourcis le texte » et bouton **Raccourcir** (DeepSeek). Niveau aligné sur la voix d'origine |
| 9. Mixage | — | par blocs : fond + VF (option : voix d'origine laissée faible) |
| 10. Export | FFmpeg | MP4 ou MKV, vidéo copiée sans réencodage, piste VF AAC 192 kb/s normalisée à −16 LUFS, VO en option, sous-titres FR/EN intégrés (mov_text ou srt) et fichiers `.srt`, incrustation en option (libx264, sinon libopenh264, sinon Media Foundation), piste VF seule en WAV/MP3, aperçu rapide sans normalisation |

### Langues de départ

Anglais, **japonais**, espagnol, allemand, italien, portugais, coréen, chinois, russe, arabe, néerlandais, turc,
polonais, ou **détection automatique** (Paramètres → Langue de la vidéo). Traduction locale directe vers le
français quand Opus-MT en propose une, sinon en passant par l'anglais (chinois, portugais). Pour le japonais, le
chinois et le coréen, Whisper « medium » est choisi automatiquement (bien plus précis) ; DeepSeek donne une
traduction nettement meilleure pour ces langues. **Mots à ne pas traduire** (Paramètres) : noms de personnages,
d'attaques, « 変身 = Henshin »… Les passages que Whisper invente en boucle sur de la musique ou du bruit sont
écartés automatiquement.

### Pensé pour les vidéos longues (jusqu'à 1 h 30 et plus)

- **Passages sans parole sautés** : les silences et la musique seule ne passent pas par Demucs.
- **Reprise après un arrêt** : la séparation reprend au dernier bloc de 30 s, la transcription au dernier morceau
  d'environ 10 min (coupé dans un silence), le doublage à la dernière réplique ; le projet est enregistré toutes
  les 25 répliques. Fermer l'application, une coupure de courant ou « Arrêter » ne font rien perdre.
- **Pas de mise en veille** de l'ordinateur pendant le traitement (l'écran peut s'éteindre).
- **Temps estimé** affiché avant le lancement, et appris sur votre ordinateur au fil des projets.
- **Réglages rapides** : Whisper par lots, Demucs avec un recouvrement réduit, une seule analyse par voix
  gardée en mémoire pour la conversion de timbre.

### Traduction soignée

- Chaque réplique est traduite **phrase par phrase** : une phrase courte (« Almost. ») n'est plus avalée.
- Opus-MT propose 5 variantes par phrase ; Doublys garde celle qui respecte **le tutoiement ou le vouvoiement
  choisi entre les deux personnes qui se parlent** (le même tout au long de la vidéo) et qui **tient dans le temps**.

### Voix expressives

Les répliques nettement plus fortes que la voix habituelle de la personne (cris, colère, au moins +6 dB) sont
refaites avec **Chatterbox expressif** (25 au plus par vidéo, environ 25 s de calcul chacune sans carte graphique ;
désactivable dans Paramètres). Elles sont marquées ✦ dans la colonne Calage.

### Aperçu intégré

Double-cliquez sur le numéro d'une réplique (ou bouton **Aperçu**) : l'image de la vidéo défile dans la page
Doublage, synchronisée avec le son français, avec le sous-titre de la réplique. Clic droit → « Ouvrir 20 s dans le
lecteur de Windows » pour un extrait vidéo complet.

### Modes de voix (page Personnes)

| Mode | Hors ligne | Remarques |
|---|---|---|
| **Clonage rapide hors ligne** (défaut) | ✅ | Kokoro (voix française Siwis) lit le texte, Chatterbox VC lui donne le timbre de la personne |
| Clonage rapide Microsoft | ❌ | Henri ou Denise (selon le genre) + conversion Chatterbox : intonation plus naturelle |
| XTTS-v2 | ✅ | ressemblance la plus fidèle, plus lent, **usage non commercial** |
| Chatterbox | ✅ | clonage expressif, lent sans carte graphique |
| Modèle RVC (.pth) | ✅/❌ | modèle `.pth` (+ `.index`) entraîné pour la personne ; voix de base Microsoft (Henri, Denise…) ou Kokoro hors ligne. RVC ne clone pas depuis l'extrait de la vidéo |
| Voix Microsoft / Kokoro / Windows | ❌ / ✅ / ✅ | sans clonage |

---

## 📥 Installation

1. Téléchargez `Doublys-Setup-x.y.z.exe` (onglet **Releases** du dépôt, étiquettes `doublys-v…`, ou artefact du
   workflow « Doublys — build Windows » dans l'onglet **Actions**).
2. Lancez-le : **aucun droit administrateur** n'est nécessaire (installation dans `%LOCALAPPDATA%\Programs\Doublys`,
   raccourcis menu Démarrer et bureau, désinstallation dans « Applications et fonctionnalités »).
   Windows peut afficher « Windows a protégé votre ordinateur » (application non signée) :
   **Informations complémentaires → Exécuter quand même**.
3. Au premier lancement, cliquez sur **« Installer tout ce qu'il faut »** (accueil) : analyse, Whisper, Kokoro et
   Chatterbox sont téléchargés une fois (≈ 6 Go, 20 à 40 min selon la connexion), puis tout fonctionne hors ligne.

**Version portable** : décompressez `Doublys-Portable-x.y.z.zip` et lancez `Doublys.exe` (les données restent dans
le dossier `data` à côté de l'exécutable tant que le fichier `portable.txt` est présent).

**Configuration conseillée** : Windows 10/11 64 bits, 8 Go de RAM (16 Go confortable), 10 Go libres.
Sur un portable sans carte graphique, comptez quelques minutes de calcul par minute de vidéo (mesure sur 4 cœurs :
31 s de vidéo à deux voix doublées en 3 min, chargement des modèles compris).

---

## 🚀 Utilisation

1. **Accueil** → glissez la vidéo (MP4, MKV, MOV, AVI, WEBM…). Le projet est créé dans
   `Documents\Doublys\<titre>\` ; la vidéo reste à sa place.
2. **Doublage** → **Créer la VF automatiquement**. Progression, temps restant et bouton **Arrêter** ; tout ce qui est
   fait est gardé : la relance reprend où elle s'est arrêtée. Chaque étape peut être relancée seule (bouton ⟳).
3. Tableau des répliques : début, durée, personne, anglais, **français modifiable** (double-clic), calage, état.
   Boutons : écouter VO / VF / mixé, aperçu vidéo (20 s dans le lecteur de Windows), retraduire, raccourcir,
   refaire la voix, fusionner, couper, supprimer ; clic droit → « Attribuer à » une autre personne.
4. **Personnes** → nom, extrait (écouter, autre extrait, fichier), mode de voix, voix de base, **Essai**.
5. **Export** → MP4/MKV, pistes, sous-titres, piste VF seule, aperçu rapide.

### Fichiers d'un projet

```
Documents\Doublys\Ma vidéo\
  Ma vidéo.doublys        projet (JSON : réglages, répliques, personnes, étapes faites)
  Ma vidéo (VF).mp4       vidéo doublée (exportée ici par défaut)
  Ma vidéo.fr.srt / .en.srt
  travail\                original.wav, voix.wav, fond.wav, transcription.json, vf_mix.wav,
                          personnes\ (extraits de référence), voix\ (voix française de chaque réplique, en cache)
```

Moteurs et modèles : `%LOCALAPPDATA%\Doublys` ; préférences et clé DeepSeek (chiffrée DPAPI) : `%APPDATA%\Doublys`.

---

## 🛠️ Développement

```bash
cd doublys-app
pip install -r requirements-dev.txt
python main.py                          # lancer l'application
python -m pytest                        # tests (FFmpeg requis pour les tests audio et vidéo)
python main.py --selftest rapport.json  # autotest : vidéo synthétique, chaîne complète (moteurs factices), export vérifié
python scripts/engine_smoke.py --full   # test réel : installe les moteurs et double une vidéo anglaise à deux voix
```

### Compilation Windows

Automatisée par `.github/workflows/doublys-windows.yml` : tests Linux + autotest, puis sous Windows : tests,
FFmpeg **LGPL** (BtbN), PyInstaller, autotest de l'exécutable, installateur **NSIS**, test d'installation et de
désinstallation silencieuses, version portable et zip des sources. Un tag `doublys-v1.0.0` publie une Release.
Le lancement manuel « Tester les vrais moteurs IA » (ou `[engines]` dans le message de commit) installe et essaie
les moteurs sur le processeur du runner Windows, puis double une vidéo de test complète.

À la main sous Windows :

```powershell
pip install -r requirements-dev.txt
# placer ffmpeg.exe, ffprobe.exe (+ DLL, build LGPL) et uv.exe dans packaging\tools\
python packaging\make_assets.py
pyinstaller --noconfirm packaging\doublys.spec
& "C:\Program Files (x86)\NSIS\makensis.exe" /DAPP_VERSION=1.0.0 packaging\installer.nsi
```

### Architecture

```
doublys/
  core/            pipeline (étapes), segment (répliques), speakers (personnes), timing (calage), mixer,
                   media (FFmpeg : extraction, vignettes, export), refs (extraits, genre), dubvoice (voix),
                   ai (DeepSeek), project (fichiers .doublys), subtitles
  core/engines/    repris d'AudioLivre : installateur uv, processus moteurs JSON, Edge, SAPI, XTTS, Chatterbox,
                   Kokoro, clonage rapide, RVC, Whisper + environnement « analyse » (Demucs, ECAPA, Opus-MT)
  worker/          processus de calcul exécuté dans l'environnement de chaque moteur
  ui/              interface PySide6 (Accueil, Doublage, Personnes, Export, Moteurs IA, Paramètres)
packaging/         PyInstaller, NSIS, icônes
scripts/           engine_smoke.py (tests réels des moteurs)
tests/             tests automatisés
```

---

## 📜 Licences et usage commercial

Doublys intègre Qt for Python (LGPL), FFmpeg en version **LGPL** (BtbN), NumPy (BSD), libsndfile (LGPL),
num2words (LGPL), edge-tts (LGPL), uv (MIT/Apache). Moteurs installés à la demande :
Demucs (MIT), faster-whisper et Whisper (MIT), speechbrain ECAPA (Apache 2.0), **Opus-MT (CC-BY 4.0 : citer
« traduction Opus-MT, Helsinki-NLP » si vous publiez)**, Kokoro (Apache 2.0), Chatterbox (MIT, filigrane inaudible),
**XTTS-v2 (CPML : usage non commercial uniquement)**, RVC (MIT), PyTorch (BSD).

Pour vendre ou monétiser une vidéo doublée : évitez XTTS-v2 (préférez le clonage rapide ou Chatterbox), vérifiez les
conditions des voix Microsoft si vous les utilisez, et assurez-vous d'avoir **les droits sur la vidéo d'origine et
l'accord des personnes dont la voix est clonée**.
