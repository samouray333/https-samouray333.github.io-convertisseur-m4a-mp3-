# 🎙️ PodCast Studio

**Créez vos podcasts à plusieurs voix — animateurs, invités, jingles, épisodes et flux RSS — gratuitement, sur un simple portable.**

PodCast Studio est une application Windows (installateur `.exe`) de la même famille qu'AudioLivre Studio : même interface, mêmes
moteurs de voix (Microsoft, Kokoro, XTTS, Chatterbox, clonage rapide, RVC), même assistant DeepSeek, même mastering.
Elle est pensée pour le podcast : un script en dialogue, une voix par intervenant, des jingles sur chaque épisode et un flux RSS
prêt pour Apple Podcasts, Spotify ou Deezer.

> Couleurs : orange corail `#FF6B35` et ambre `#FFB627`. Icône : micro de studio et ses ondes.

---

## ✨ Fonctionnalités

| | |
|---|---|
| 👥 **Animateurs et invités** | Page « Animateurs » : animateur·rice, co-animateur·rice, invité·e, voix off. Chacun reçoit sa voix (catalogue Microsoft, Kokoro hors ligne, voix Windows ou **voix clonée**), une présentation qui guide l'IA, un bouton d'écoute. Renommer quelqu'un met à jour toutes ses répliques. |
| 💬 **Script en dialogue** | Une réplique par paragraphe : `@Alex: Bonjour !`. Émotions (`[joyeux]`, `[calme]`…), débit (`[lent]`), mots mis en valeur (`*mot*`), pauses (`[pause 2s]`), rubriques (`# Rubrique`). |
| 🤖 **Écrire avec l'IA (DeepSeek)** | Donnez un sujet, un plan ou collez un article : DeepSeek écrit un dialogue naturel entre les participants choisis, au style voulu (conversation, interview, débat, récit, info) et à la durée visée. Il propose aussi le titre et la description de l'épisode. Facultatif (quelques centimes par épisode). |
| 🗂️ **Épisodes** | Numéro (automatique ou saisi), saison, type (épisode, bande-annonce, bonus), date de publication, notes d'épisode. Import d'un document Word/PDF : chaque partie devient un épisode ; fusion, découpe, réorganisation. |
| 🎵 **Jingles et fond musical** | Jingle d'intro et d'outro **sur chaque épisode** (ou seulement au début et à la fin de la série), fond musical baissé automatiquement quand quelqu'un parle. |
| 🎚️ **Mastering podcast** | Normalisation à **-16 LUFS** (Apple Podcasts, Spotify), de-esser, compression, réduction de bruit ; contrôle automatique des passages par Whisper. |
| 📦 **Export** | Un **MP3 par épisode** (128 kb/s conseillé) avec couverture et étiquettes podcast (titre, numéro, saison, description, date), compilation MP3, WAV, FLAC, Opus, sous-titres SRT/LRC, vidéo YouTube, rapport qualité. |
| 📡 **Flux RSS** | `feed.xml` au format RSS 2.0 + balises iTunes (catégorie, auteur, e-mail, explicite, durée, numéros) : déposez-le avec les MP3 à votre adresse de publication et soumettez-le aux plateformes. |
| ♻️ **Partagé avec AudioLivre Studio** | Moteurs IA, modèles, voix clonées et clé DeepSeek déjà installés dans AudioLivre Studio sont repris automatiquement : **rien à réinstaller**. |

---

## 📥 Installation

1. Téléchargez `PodCastStudio-Setup-x.y.z.exe` depuis l'onglet **Releases** du dépôt GitHub
   (ou l'artefact du dernier workflow « PodCast Studio — build Windows » dans l'onglet **Actions**).
2. Lancez l'installateur. Si Windows affiche *« Windows a protégé votre ordinateur »* (application non signée) :
   **Informations complémentaires → Exécuter quand même**. Aucun droit administrateur n'est nécessaire.

Une **version portable** (`.zip`) est également produite. Tout fonctionne **sans carte graphique NVIDIA** : voix Microsoft
(quelques secondes de calcul par minute), Kokoro hors ligne (moins d'une minute), clonage rapide (≈ 1 min par minute d'audio).

---

## 🚀 Prise en main

1. **Accueil → Nouveau podcast** : un podcast d'exemple est créé avec deux animateurs (Alex et Sam) et un premier épisode.
2. **Animateurs** : renommez-les, ajoutez des invités, choisissez une voix différente pour chacun (ou **Cloner une voix**).
3. **Épisodes** : écrivez le script (`@Alex: …`) ou cliquez sur **Écrire avec l'IA** ; renseignez numéro, date et description.
4. **Production** : **Tout produire**, réécoutez, refaites une prise si besoin.
5. **Export & RSS** : nom du podcast, auteur, e-mail, catégorie, couverture carrée, jingles, **adresse de publication**, puis **Exporter les épisodes**.

### Publier gratuitement

Le dossier d'export contient `episodes/` (les MP3), `couverture.jpg` et `feed.xml`. Déposez-les à l'adresse indiquée dans
« Adresse de publication » — par exemple un site **GitHub Pages** gratuit (`https://votre-nom.github.io/mon-podcast`) —
puis soumettez l'adresse du flux (`…/feed.xml`) à Apple Podcasts Connect, Spotify for Creators, Deezer, Podcast Addict…

---

## 🧠 Moteurs de voix

| Moteur | Clonage | Hors ligne | Licence | Remarques |
|---|---|---|---|---|
| Voix neuronales Microsoft | — | Non | Service en ligne | Excellente qualité, très rapide, aucune installation |
| XTTS-v2 (Coqui) | ✅ | ✅ | CPML (non commercial) | Meilleure prosodie en français, 17 langues |
| Clonage rapide (Microsoft + Chatterbox VC) | ✅ | Non | MIT + service Microsoft | Le plus rapide sans carte graphique |
| Modèles RVC (.pth) | ✅ | Non | MIT + service Microsoft | Modèle de voix importé ; ≈ 1,5 min de calcul par minute d'audio sans carte graphique |
| Chatterbox multilingue (Resemble AI) | ✅ | ✅ | MIT | Expressivité réglable, usage commercial autorisé, filigrane inaudible |
| Kokoro-82M | mélange de voix | ✅ | Apache 2.0 | Très rapide sans carte graphique |
| Voix Windows (SAPI/OneCore) | — | ✅ | Windows | Toujours disponible, qualité basique |

Les moteurs neuronaux sont installés à la demande dans des environnements Python isolés (`%LOCALAPPDATA%\AudioLivreStudio\engines`, dossier **commun** à AudioLivre Studio, PodCast Studio et Leçon Studio)
grâce à [uv](https://github.com/astral-sh/uv), avec PyTorch CUDA si une carte NVIDIA est détectée (RTX 50xx comprises).

> **Publication commerciale** : le modèle XTTS-v2 est sous licence non commerciale. Pour un podcast monétisé,
> utilisez Chatterbox (MIT), et vérifiez les conditions d'utilisation des voix Microsoft. Assurez-vous également de détenir les droits sur les textes et les musiques.

---

## 🛠️ Développement

```bash
cd podcast-studio
pip install -r requirements-dev.txt
python main.py                     # lancer l'application
python -m pytest                   # tests (FFmpeg requis pour les tests audio)
python main.py --selftest r.json   # autotest de bout en bout
```

La compilation est automatisée par GitHub Actions (`.github/workflows/podcast-studio-windows.yml`) : tests, PyInstaller,
autotest de l'exécutable, puis installateur Inno Setup. Pour publier une version, poussez un tag **`podcast-v1.0.0`** :
l'installateur et la version portable sont ajoutés automatiquement à la Release (les tags `v*` restent ceux d'AudioLivre Studio).

```
podcaststudio/
  core/        rendu, mastering, export (MP3 par épisode, étiquettes podcast), rss.py (flux), ai.py (dialogue)
  core/engines Microsoft Edge, SAPI, moteurs neuronaux + installateur uv (dossier commun AudioLivreStudio)
  ui/pages     accueil, épisodes, animateurs, voix, production, export & RSS, moteurs, paramètres
packaging/     PyInstaller, Inno Setup, icônes
tests/         tests automatisés
```

---

## 📜 Licences

PodCast Studio est gratuit. Il s'appuie sur Qt for Python (LGPL), FFmpeg (LGPL), PyMuPDF (AGPL), python-docx (MIT),
EbookLib (AGPL), mutagen (GPL), edge-tts (LGPL), num2words (LGPL), NumPy (BSD), libsndfile (LGPL), PortAudio (MIT), uv (MIT/Apache).
Le détail figure dans **Paramètres → À propos et licences**.
