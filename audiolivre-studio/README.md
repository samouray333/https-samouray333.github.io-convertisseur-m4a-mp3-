# 🎧 AudioLivre Studio

**Transformez vos documents Word, PDF ou EPUB en livres audio de qualité professionnelle — gratuitement, avec votre propre voix si vous le souhaitez.**

AudioLivre Studio est une application Windows (installateur `.exe`) qui réunit tout le nécessaire pour produire un livre audio prêt à publier :
import du manuscrit, découpage en chapitres, choix ou **clonage de voix**, distribution des rôles, production avec contrôle qualité,
**mastering aux normes ACX / Audible** et export en **M4B chapitré**, MP3, FLAC, WAV ou Opus.

---

## ✨ Fonctionnalités

| | |
|---|---|
| 📄 **Import intelligent** | Word (.docx), PDF, EPUB, ODT, RTF, Markdown, HTML, TXT, **PDF scannés et photos de pages (OCR intégré à Windows)**. Détection automatique des chapitres, suppression des en-têtes/pieds de page, réparation des césures, **aperçu du découpage avant import** (5 modes, inclusion, fusion, renommage). |
| ✍️ **Éditeur de manuscrit** | Coloration des balises, chapitres réorganisables par glisser-déposer, fusion/découpe, rechercher-remplacer, statistiques et durée estimée, « Écouter la sélection », **aperçu de lecture** (le texte exact qui sera lu). |
| 🗣️ **Voix gratuites** | Plus de 300 voix neuronales Microsoft (dont ~15 en français, très naturelles), voix Windows hors ligne, Kokoro hors ligne. |
| ⚡ **Clonage rapide** | Une voix Microsoft lit le texte puis un convertisseur gratuit (décodeur Chatterbox Turbo) lui donne votre timbre : environ 1 minute de calcul par minute de livre sur un ordinateur portable sans carte graphique. |
| 🔎 **Relecture automatique** | Whisper (gratuit, hors ligne) réécoute chaque passage produit, refait ceux où des mots manquent et signale les passages à vérifier. |
| 🎭 **Émotions** | Balises `[joyeux]`, `[triste]`, `[colère]`, `[chuchoté]`, `[calme]`, `[peur]`, `[excité]` et menu « Émotion » dans l'éditeur. |
| 🧬 **Clonage de voix** | Assistant en 4 étapes : importez un enregistrement (audio ou vidéo) ou enregistrez-vous au micro, l'application choisit automatiquement le meilleur extrait, analyse la qualité (bruit, saturation), réduit le bruit, puis vous testez la voix. Moteurs **XTTS-v2** et **Chatterbox** (expressivité réglable), 100 % hors ligne. |
| 🎭 **Distribution des rôles** | Narrateur, voix des dialogues (détection automatique des « — » et « »), une voix par personnage (`@Marie: …`), voix différente par chapitre. |
| 🔤 **Prononciation** | Nombres, dates, heures, monnaies, pourcentages, unités, abréviations (M., Mme, Dr…), chiffres romains (Louis XIV, XIXe siècle) lus en toutes lettres. **Lexique** personnalisé avec détection des sigles et test d'écoute. |
| ⚙️ **Production** | Cache intelligent (seuls les passages modifiés sont régénérés), pause/reprise, estimation du temps restant, **contrôle qualité automatique** (détection des passages ratés et nouvel essai), nouvelle prise passage par passage, réécoute immédiate. |
| 🎚️ **Mastering pro** | Préréglages ACX/Audible (RMS -19,5 dB, crêtes ≤ -3,6 dB, bruit de fond -72 dB), Streaming (-16 LUFS), Naturel ; de-esser, compression, égalisation, réduction de bruit, ambiance de pièce, silences de début/fin conformes. |
| 📦 **Export** | M4B avec chapitres et couverture (Apple Books, Smart AudioBook Player…), MP3 par chapitre 192 kb/s CBR 44,1 kHz (ACX), MP3 unique chapitré, WAV 24 bits, FLAC, Opus, playlist M3U, **crédits d'ouverture et de fin**, **extrait commercial**, couverture 2400 × 2400, étiquettes complètes et **rapport qualité ACX** en HTML. |
| 🎵 **Musique** | Jingles d'ouverture et de fin, fond sonore baissé automatiquement quand la voix parle. |
| 🎬 **Sous-titres et vidéo** | Sous-titres synchronisés SRT/LRC et vidéo MP4 par chapitre pour YouTube (couverture, onde animée, sous-titres intégrés). |
| 🔔 **Mises à jour** | L'application vous prévient quand une nouvelle version est publiée. |
| 💾 **Projets** | Enregistrement automatique, projets récents, partage de voix (`.alsvoice`), mode portable, thèmes sombre/clair et couleurs d'accent. |

---

## 📥 Installation

1. Téléchargez `AudioLivreStudio-Setup-x.y.z.exe` depuis l'onglet **Releases** du dépôt GitHub
   (ou, pour une version de développement, l'artefact du dernier workflow « AudioLivre Studio — build Windows » dans l'onglet **Actions**).
2. Lancez l'installateur. Windows peut afficher *« Windows a protégé votre ordinateur »* car l'application n'est pas signée :
   cliquez sur **Informations complémentaires → Exécuter quand même**.
3. Aucun droit administrateur n'est nécessaire (installation pour l'utilisateur courant possible).

Une **version portable** (`.zip`) est également produite : décompressez-la et lancez `AudioLivreStudio.exe`.

**Configuration conseillée** : Windows 10/11 64 bits, 8 Go de RAM. Pour le clonage de voix, une carte graphique **NVIDIA**
(4 Go de mémoire vidéo ou plus) accélère énormément la production ; sans elle, le processeur est utilisé (plus lent).

**Temps de calcul mesurés sans carte graphique** (processeur 4 cœurs, par minute de livre audio) :

| Voix | Calcul | Remarque |
|---|---|---|
| Voix Microsoft | quelques secondes | Internet requis |
| Kokoro | moins d'une minute | hors ligne |
| Clonage rapide | ≈ 1 min | Internet requis ; mode « Fidèle » (≈ 5 min) dans Paramètres → Performances |
| XTTS-v2 (clonage) | ≈ 3 min | ressemblance la plus fidèle |
| Chatterbox (clonage) | ≈ 20 min | à réserver aux cartes NVIDIA |

---

## 🚀 Prise en main

1. **Accueil** → glissez votre document Word/PDF. Le projet est créé dans `Documents\AudioLivre Studio`.
2. **Manuscrit** → relisez, ajustez les chapitres, choisissez le narrateur. Utilisez **Aperçu de lecture** pour vérifier la prononciation.
3. **Voix & clonage** → écoutez les voix du catalogue ou cliquez sur **Cloner une voix**.
4. **Moteurs IA** → installez gratuitement XTTS-v2, Chatterbox ou Kokoro (téléchargement unique, automatique).
5. **Production** → **Tout produire**. Réécoutez, refaites une prise si besoin.
6. **Export** → renseignez titre, auteur, couverture, choisissez vos formats, puis **Exporter le livre audio**.

### Balises de mise en scène (dans le manuscrit)

| Balise | Effet |
|---|---|
| `# Intertitre` | Intertitre lu avec une pause plus longue |
| `[pause 2s]` ou `[pause 500ms]` | Silence |
| `@Marie: Bonjour !` | Paragraphe lu par la voix du personnage « Marie » |
| `[voix:Paul]` … `[/voix]` | Passage lu par la voix de « Paul » |
| `%% note` | Commentaire ignoré à la lecture |
| `[triste]` (ligne seule) … `[neutre]` | Ton des paragraphes suivants (joyeux, triste, colère, chuchoté, calme, peur, excité) |
| `[joyeux] Youpi !` ou `@Marie: [colère] Non !` | Ton d'un seul paragraphe |

### Conseils pour cloner une voix

- 10 à 30 secondes de parole continue, **une seule voix**, sans musique ni bruit de fond.
- Ton naturel et posé, comme pour lire un livre ; micro proche de la bouche, pièce calme.
- Plusieurs extraits (bouton **Ajouter** dans l'éditeur de voix) améliorent la ressemblance avec XTTS-v2.
- ⚠️ Ne clonez que votre voix ou celle d'une personne qui vous a donné son **accord explicite**.

---

## 🧠 Moteurs de voix

| Moteur | Clonage | Hors ligne | Licence | Remarques |
|---|---|---|---|---|
| Voix neuronales Microsoft | — | Non | Service en ligne | Excellente qualité, très rapide, aucune installation |
| XTTS-v2 (Coqui) | ✅ | ✅ | CPML (non commercial) | Meilleure prosodie en français, 17 langues |
| Clonage rapide (Microsoft + Chatterbox VC) | ✅ | Non | MIT + service Microsoft | Le plus rapide sans carte graphique |
| Chatterbox multilingue (Resemble AI) | ✅ | ✅ | MIT | Expressivité réglable, usage commercial autorisé, filigrane inaudible |
| Kokoro-82M | mélange de voix | ✅ | Apache 2.0 | Très rapide sans carte graphique |
| Voix Windows (SAPI/OneCore) | — | ✅ | Windows | Toujours disponible, qualité basique |

Les moteurs neuronaux sont installés à la demande dans des environnements Python isolés (`%LOCALAPPDATA%\AudioLivreStudio\engines`)
grâce à [uv](https://github.com/astral-sh/uv), avec PyTorch CUDA si une carte NVIDIA est détectée (RTX 50xx comprises).

> **Publication commerciale** : le modèle XTTS-v2 est sous licence non commerciale. Pour vendre votre livre audio,
> utilisez Chatterbox (MIT), et vérifiez les conditions d'utilisation des voix Microsoft. Assurez-vous également de détenir les droits sur le texte.

---

## 🛠️ Développement

```bash
cd audiolivre-studio
pip install -r requirements-dev.txt
python main.py                 # lancer l'application
python -m pytest               # tests (FFmpeg requis pour les tests audio)
python main.py --selftest r.json   # autotest de bout en bout
```

### Compiler l'installateur Windows

La compilation est automatisée par GitHub Actions (`.github/workflows/audiolivre-windows.yml`) : tests, PyInstaller,
autotest de l'exécutable, puis installateur Inno Setup. Pour publier une version : créez un tag `v1.0.0`.
L'option « Tester l'installation réelle des moteurs IA » du lancement manuel vérifie l'installation de Kokoro, XTTS-v2 et Chatterbox sous Windows.

Manuellement sous Windows :

```powershell
pip install -r requirements-dev.txt
# placer ffmpeg.exe, ffprobe.exe (+ DLL) et uv.exe dans packaging\tools\
python packaging\make_assets.py
pyinstaller --noconfirm packaging\audiolivre.spec
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
```

### Architecture

```
audiolivre/
  core/        import, normalisation du texte, rendu, mastering, export, bibliothèque de voix
  core/engines Microsoft Edge, SAPI, moteurs neuronaux (processus séparé) + installateur uv
  worker/      processus de synthèse exécuté dans l'environnement de chaque moteur
  ui/          interface PySide6 (pages, assistant de clonage, lecteur intégré, thème)
packaging/     PyInstaller, Inno Setup, icônes
tests/         tests automatisés
```

---

## 📜 Licences

AudioLivre Studio est gratuit. Il s'appuie sur Qt for Python (LGPL), FFmpeg (LGPL), PyMuPDF (AGPL), python-docx (MIT),
EbookLib (AGPL), mutagen (GPL), edge-tts (LGPL), num2words (LGPL), NumPy (BSD), libsndfile (LGPL), PortAudio (MIT), uv (MIT/Apache).
Le détail figure dans **Paramètres → À propos et licences**.
