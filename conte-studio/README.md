# 🌙 Conte Studio

**Créez des contes et des histoires audio pour vos enfants — un narrateur, des personnages qui parlent, des bruitages,
des histoires du soir — gratuitement, sur un simple portable.**

Conte Studio est une application Windows (installateur `.exe`) de la même famille qu'AudioLivre Studio, PodCast Studio et
Leçon Studio : même interface, mêmes moteurs de voix (Microsoft, Kokoro, XTTS, Chatterbox, clonage rapide, RVC), même
assistant DeepSeek, même mastering. Elle est pensée pour les enfants : une idée suffit pour obtenir un conte adapté à leur
âge, chaque personnage a sa voix, et le soir l'histoire se termine par une berceuse puis une pluie douce qui s'éteint.

> Couleurs « Nuit étoilée » : bleu ciel du soir `#3B82F6` et jaune étoile `#FFD166`, sur fond bleu nuit (thème sombre) ou
> crème (thème clair). Icône : un livre ouvert d'où sortent une lune et deux étoiles, sur un rond bleu nuit.

---

## ✨ Fonctionnalités

| | |
|---|---|
| ✍️ **Nouvelle histoire** | Écrivez ou **dictez** une idée (« un dragon qui a peur du noir »), choisissez l'**âge** (3-5, 6-8, 9-12 ans), la **durée** (5 à 20 min), le **ton** (drôle, aventure, douce pour dormir, éducative) et une **morale** facultative. L'assistant DeepSeek écrit le conte avec un narrateur et des personnages qui parlent (`@Nom:`), des bruitages et des ambiances. Les longues histoires sont écrites en plusieurs parties. |
| 👶 **Adapté à l'âge** | Vocabulaire, longueur des phrases et ton suivent l'âge choisi ; rien d'effrayant pour les petits. Le menu **Mise en scène → Vérifier pour l'âge** signale les mots qui font peur et les phrases trop longues ; **Réécrire avec l'IA** rend un passage plus simple, plus drôle, plus doux, plus court ou plus vivant. |
| ⭐ **L'enfant est le héros** | Son prénom (page Personnages) est inséré par l'IA dans les nouvelles histoires et remplace `{prénom}` dans le texte, les titres et le livret. |
| 🎭 **Personnages** | Une voix par personnage (narrateur, héros, animaux, fées…) et une **façon de parler** : enfant (plus aiguë), tout petit animal, fée, grand personnage, géant, dragon (grave et lent), vieux sage, robot. Le réglage fonctionne avec toutes les voix, même clonées. Les nouveaux personnages reçoivent automatiquement une voix différente. |
| 👨‍👩‍👧 **La voix de papa ou maman** | Boutons « Voix de papa / maman / papi / mamie » : une minute de lecture suffit pour cloner la voix du narrateur, avec la **case de consentement** de l'assistant de clonage. Une réplique peut aussi être enregistrée directement au micro. |
| 🔔 **Bruitages** | Générés par l'application, **libres de droits** : porte qui grince, pas, cloche magique, formule magique, rire, tonnerre, on frappe à la porte, chat, chien, vache, mouton, canard, hibou, oiseau, grenouille, loup, cheval au galop, ronflement… `[son: porte]`. Vos propres sons dans « Mes sons ». |
| 🌲 **Fonds d'ambiance** | Forêt, pluie, orage, mer, vent, feu de cheminée, nuit d'été, rivière, bruit blanc, bruit rose : un fond continu sous une scène, de `[ambiance: pluie]` à `[ambiance: fin]`, qui s'installe et s'éteint en fondu, au niveau réglable. |
| 🌙 **Histoire du soir** | Voix très douce et ralentie, pauses plus longues, puis une **berceuse** générée (« Au clair de la lune » en boîte à musique, de plus en plus lente) et, si vous le souhaitez, une **pluie**, des vagues ou un **bruit blanc** qui continue quelques minutes en baissant jusqu'au silence. |
| 📚 **Bibliothèque** | Les **collections** (une série avec les mêmes personnages, que l'IA reprend d'une histoire à l'autre), les **favoris**, la **durée** de chaque histoire, des filtres (âge, histoires du soir, prêtes à écouter). **Cinq histoires d'exemple** sont fournies. |
| 🖼️ **Couvertures** | Image importée, ou **dessin simple généré** par l'application avec le titre (forêt, mer, château, espace, neige, ferme ou maison, ciel de nuit pour les histoires du soir). Utilisées dans les MP3, le livret et le coin lecture. |
| 📦 **Export** | Un **MP3 par histoire** avec sa couverture et ses métadonnées (titre, collection, résumé, texte de l'histoire en paroles), une **compilation**, WAV, FLAC, texte synchronisé, et un **livret imprimable** (HTML et PDF) avec le texte du conte en **gros caractères** pour lire en même temps. |
| 🧸 **Coin lecture** | Un écran plein écran pour l'enfant, sans menus : les couvertures en grand, un **grand bouton lecture**, histoire suivante et précédente. Pour quitter, le parent maintient le petit cadenas appuyé. |
| ♻️ **Partagé avec les autres applications** | Moteurs IA, modèles, voix clonées et clé DeepSeek déjà installés dans AudioLivre Studio, PodCast Studio ou Leçon Studio sont repris automatiquement (`%LOCALAPPDATA%\AudioLivreStudio`) : **rien à réinstaller**. |

---

## 📥 Installation

1. Téléchargez `ConteStudio-Setup-x.y.z.exe` depuis l'onglet **Releases** du dépôt GitHub (versions `conte-v…`),
   ou l'artefact du dernier workflow « Conte Studio — build Windows » dans l'onglet **Actions**.
2. Lancez l'installateur. Si Windows affiche *« Windows a protégé votre ordinateur »* (application non signée) :
   **Informations complémentaires → Exécuter quand même**. Aucun droit administrateur n'est nécessaire.

Une **version portable** (`.zip`) est également produite. Tout fonctionne **sans carte graphique NVIDIA** : voix Microsoft
(quelques secondes de calcul par minute d'histoire), Kokoro hors ligne, clonage rapide (≈ 1 min par minute d'audio).
L'assistant DeepSeek est facultatif (environ un centime par histoire) : sans clé, écrivez vos histoires vous-même ou
utilisez les histoires d'exemple.

---

## 🚀 Prise en main

1. **Accueil → Histoires d'exemple** pour découvrir l'application, ou **Nouvelle histoire** pour écrire la vôtre.
2. **Personnages** : prénom de l'enfant, voix du narrateur (ou « Voix de maman »), voix et façon de parler de chaque personnage.
3. **Histoires** : relisez, ajoutez des bruitages et des ambiances, cochez « Histoire du soir », choisissez la couverture.
4. **Production** : **Tout produire**, réécoutez, refaites une prise si besoin.
5. **Export & livret** : MP3, livret, réglages de la berceuse et du bruit d'endormissement, puis **Exporter les histoires**.
6. **Coin lecture** : l'enfant choisit son histoire et appuie sur le grand bouton.

### Balises du texte

| Balise | Effet |
|---|---|
| `@Pompon: J'ai peur du noir !` | Réplique de Pompon (avec sa voix et sa façon de parler) |
| `{prénom}` | Prénom de l'enfant (page Personnages) ; `@{prénom}:` pour le faire parler |
| `[son: porte]` | Bruitage ponctuel |
| `[ambiance: forêt]` … `[ambiance: fin]` | Fond d'ambiance continu sous la scène |
| `[chuchoté]`, `[joyeux]`, `[lent]`, `*mot*`, `[pause 2s]` | Ton, débit, mise en valeur, silence |
| `@Lili: [prise: maman-1.wav] …` | Réplique enregistrée au micro (dossier « prises » de la collection) |
| `%% note` | Note pour vous, jamais lue |

---

## 🧠 Moteurs de voix

| Moteur | Clonage | Hors ligne | Licence | Remarques |
|---|---|---|---|---|
| Voix neuronales Microsoft | — | Non | Service en ligne | Excellente qualité, très rapide, aucune installation ; voix d'enfant (Eloise) |
| XTTS-v2 (Coqui) | ✅ | ✅ | CPML (non commercial) | Meilleure prosodie en français |
| Clonage rapide (Microsoft + Chatterbox VC) | ✅ | Non | MIT + service Microsoft | Le plus rapide sans carte graphique |
| Modèles RVC (.pth) | ✅ | Non | MIT + service Microsoft | Modèle de voix importé |
| Chatterbox multilingue (Resemble AI) | ✅ | ✅ | MIT | Expressivité réglable |
| Kokoro-82M | mélange de voix | ✅ | Apache 2.0 | Très rapide sans carte graphique |
| Voix Windows (SAPI/OneCore) | — | ✅ | Windows | Toujours disponible, qualité basique |

Les moteurs neuronaux sont installés à la demande dans des environnements Python isolés, dans le dossier **commun**
`%LOCALAPPDATA%\AudioLivreStudio\engines` (avec PyTorch CUDA si une carte NVIDIA est détectée).

> **Voix clonées** : clonez uniquement votre voix ou celle d'une personne qui vous a donné son accord (case de
> consentement obligatoire). **Musiques** : les bruitages, ambiances et la berceuse sont générés par l'application ; pour
> une musique ajoutée, vérifiez qu'elle est libre de droits.

---

## 🛠️ Développement

```bash
cd conte-studio
pip install -r requirements-dev.txt
python main.py                     # lancer l'application
python -m pytest                   # tests (FFmpeg requis pour les tests audio)
python main.py --selftest r.json   # autotest de bout en bout
```

La compilation est automatisée par GitHub Actions (`.github/workflows/conte-studio-windows.yml`) : tests, PyInstaller,
autotest de l'exécutable, puis installateur Inno Setup. Pour publier une version, poussez un tag **`conte-v1.0.0`** :
l'installateur et la version portable sont ajoutés à la Release. Les autres applications gardent leurs propres tags
(`v*` pour AudioLivre Studio, `podcast-v*`, `lecon-v*`) et la recherche de mises à jour de Conte Studio ne regarde que
les versions `conte-v*` : les releases ne se mélangent pas.

```
contestudio/
  core/story.py     écriture des contes (âge, durée, ton, morale, prénom), personnages et voix proposées
  core/sounds.py    bruitages, fonds d'ambiance, berceuse et bruit d'endormissement (générés, libres de droits)
  core/renderer.py  rendu : voix des personnages (hauteur, débit), histoire du soir, ambiances sous les scènes
  core/exporter.py  MP3 par histoire (couverture, paroles), compilation, berceuse et fondu, livret
  core/covers.py    couvertures dessinées ;  core/booklet.py  livret HTML/PDF ;  core/library.py  bibliothèque
  ui/pages          accueil, histoires, personnages, voix, production, export & livret, bibliothèque
  ui/kids.py        coin lecture (mode enfant)
  resources/histoires/exemples.json   histoires d'exemple
packaging/          PyInstaller, Inno Setup, icônes
tests/              tests automatisés
```

---

## 📜 Licences

Conte Studio est gratuit. Il s'appuie sur Qt for Python (LGPL), FFmpeg (LGPL), PyMuPDF (AGPL), python-docx (MIT),
EbookLib (AGPL), mutagen (GPL), edge-tts (LGPL), num2words (LGPL), NumPy (BSD), libsndfile (LGPL), PortAudio (MIT), uv (MIT/Apache).
« Au clair de la lune » est une chanson traditionnelle du domaine public. Le détail figure dans
**Paramètres → À propos et licences**.
