# 🎓 Leçon Studio

**Transformez vos cours Word ou PDF en cours audio — modules, leçons, voix du professeur, pauses de réflexion, résumés et quiz — gratuitement, sur un simple portable.**

Leçon Studio est une application Windows (installateur `.exe`) de la même famille qu'AudioLivre Studio : même interface, mêmes
moteurs de voix (Microsoft, Kokoro, XTTS, Chatterbox, clonage rapide, RVC), même assistant DeepSeek, même mastering.
Elle est pensée pour l'enseignement : un cours découpé en modules et en leçons, une voix posée, des moments pour réfléchir,
et un résumé suivi d'un quiz à la fin de chaque leçon.

> Couleurs : vert ardoise `#27AE60` et vert menthe `#6FCF97`. Icône : livre ouvert coiffé d'une toque de diplômé.

---

## ✨ Fonctionnalités

| | |
|---|---|
| 📄 **Import de cours** | Word (.docx), PDF (même scanné, grâce à la reconnaissance de texte de Windows), ODT, RTF, EPUB, TXT. Les titres « Module 2 », « Partie I », « Unité 3 », « Séquence 1 »… deviennent des **modules**, les sections des **leçons**. |
| 🗂️ **Modules et leçons** | Chaque leçon appartient à un module (liste modifiable). Regroupement **par l'assistant IA** (titres de modules proposés) ou par nombre de leçons, renommage, réorganisation par glisser-déposer. |
| 👩‍🏫 **Voix du professeur** | Voix Microsoft gratuites, Kokoro hors ligne, voix Windows, ou **votre propre voix clonée** (clonage rapide sans carte graphique, XTTS-v2, Chatterbox, modèles RVC). Débit un peu plus posé par défaut. |
| 🤔 **Pauses de réflexion** | `[réflexion]` (durée réglable) ou `[réflexion 10s]` après une question posée à l'élève. L'assistant IA peut proposer les bons moments et la question à poser. |
| 📝 **Résumé et quiz audio** | Onglet « Résumé et quiz » de chaque leçon : résumé « Ce qu'il faut retenir », quiz à choix multiples, vrai/faux ou questions ouvertes, avec temps de réponse puis correction expliquée. Rédigés par DeepSeek en un clic, entièrement modifiables. |
| 🔊 **Lecture structurée** | Annonce « Module 2. … » au début de chaque module et « Leçon 3. … » avant chaque leçon ; intertitres, émotions, débit, mots mis en valeur. |
| 📦 **Export par module** | Un dossier par module avec un MP3 par leçon, un MP3 ou un M4B par module (une leçon par chapitre), le cours complet en M4B, WAV, FLAC, Opus, sous-titres, vidéo YouTube, rapport qualité. |
| 🖨️ **Support écrit** | Page HTML imprimable : sommaire, texte des leçons, résumés et quiz (réponses repliables). |
| ♻️ **Partagé avec AudioLivre Studio** | Moteurs IA, modèles, voix clonées et clé DeepSeek déjà installés dans AudioLivre Studio sont repris automatiquement : **rien à réinstaller**. |

---

## 📥 Installation

1. Téléchargez `LeconStudio-Setup-x.y.z.exe` depuis l'onglet **Releases** du dépôt GitHub
   (ou l'artefact du dernier workflow « Leçon Studio — build Windows » dans l'onglet **Actions**).
2. Lancez l'installateur. Si Windows affiche *« Windows a protégé votre ordinateur »* (application non signée) :
   **Informations complémentaires → Exécuter quand même**. Aucun droit administrateur n'est nécessaire.

Une **version portable** (`.zip`) est également produite. Tout fonctionne **sans carte graphique NVIDIA** : voix Microsoft
(quelques secondes de calcul par minute), Kokoro hors ligne (moins d'une minute), clonage rapide (≈ 1 min par minute d'audio).

---

## 🚀 Prise en main

1. **Accueil** → glissez votre cours Word ou PDF : modules et leçons sont détectés (sinon, **Organiser en modules**).
2. **Cours** → relisez chaque leçon, ajoutez des **pauses de réflexion**, puis onglet **Résumé et quiz → Résumé et quiz IA**.
3. **Voix & clonage** → choisissez la voix du professeur, ou clonez la vôtre.
4. **Production** → réglez la pause de réflexion et le temps de réponse au quiz, puis **Tout produire**.
5. **Export** → titre du cours, matière, couverture, formats (par module, support écrit…), puis **Exporter le cours**.

### Balises utiles

| Balise | Effet |
|---|---|
| `# Intertitre` | Intertitre annoncé, avec une pause plus longue |
| `[réflexion]` / `[réflexion 10s]` | Silence pour laisser l'élève réfléchir (durée par défaut réglée dans Production) |
| `[pause 2s]` | Silence |
| `[lent]`, `[calme]`, `*mot important*` | Débit, ton, mise en valeur |
| `%% note` | Note pour vous, non lue |

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

> **Publication commerciale** : le modèle XTTS-v2 est sous licence non commerciale. Pour vendre votre cours,
> utilisez Chatterbox (MIT), et vérifiez les conditions d'utilisation des voix Microsoft. Assurez-vous également de détenir les droits sur le texte.

---

## 🛠️ Développement

```bash
cd lecon-studio
pip install -r requirements-dev.txt
python main.py                     # lancer l'application
python -m pytest                   # tests (FFmpeg requis pour les tests audio)
python main.py --selftest r.json   # autotest de bout en bout
```

La compilation est automatisée par GitHub Actions (`.github/workflows/lecon-studio-windows.yml`) : tests, PyInstaller,
autotest de l'exécutable, puis installateur Inno Setup. Pour publier une version, poussez un tag **`lecon-v1.0.0`** :
l'installateur et la version portable sont ajoutés automatiquement à la Release (les tags `v*` restent ceux d'AudioLivre Studio).

```
leconstudio/
  core/        rendu, mastering, export par module, course.py (modules, réflexion, quiz, support écrit), ai.py
  core/engines Microsoft Edge, SAPI, moteurs neuronaux + installateur uv (dossier commun AudioLivreStudio)
  ui/pages     accueil, cours (leçons, modules, résumé et quiz), voix, production, export, moteurs, paramètres
packaging/     PyInstaller, Inno Setup, icônes
tests/         tests automatisés
```

---

## 📜 Licences

Leçon Studio est gratuit. Il s'appuie sur Qt for Python (LGPL), FFmpeg (LGPL), PyMuPDF (AGPL), python-docx (MIT),
EbookLib (AGPL), mutagen (GPL), edge-tts (LGPL), num2words (LGPL), NumPy (BSD), libsndfile (LGPL), PortAudio (MIT), uv (MIT/Apache).
Le détail figure dans **Paramètres → À propos et licences**.
