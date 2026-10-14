# 🌍 Polyglotte Studio

**Apprenez les langues à l'écoute, avec des voix natives.** Application Windows gratuite (installateur ou version
portable) pour créer des cours de langue audio : environ 80 langues et de nombreux accents régionaux, des leçons
écrites par l'assistant DeepSeek selon votre niveau et le thème choisi, des exercices « écoutez puis répétez », des
révisions espacées et des exports pour le téléphone, l'imprimante et Anki.

Couleurs : **bleu `#1E88E5`** et **or `#FFC107`** sur bleu nuit `#0F1B2D`. Versions publiées avec les tags
**`polyglotte-v*`**, sans se mélanger aux autres applications du dépôt.

Polyglotte Studio reprend la base de **PodCast Studio** (plusieurs voix, stéréo, effets sonores, prises au micro,
chapitres, assistant DeepSeek, mastering, export) et les **modules, leçons, pauses de réflexion, résumés et quiz** de
**Leçon Studio**.

---

## ✨ Fonctionnalités

### Langues et voix natives
- **78 langues, 143 accents, plus de 300 voix Microsoft gratuites**, femmes et hommes : anglais (Royaume-Uni,
  États-Unis, Australie, Inde, Irlande…), espagnol (Espagne, Mexique, Argentine, Colombie… 22 pays), portugais
  (Portugal, Brésil), allemand (Allemagne, Autriche, Suisse), arabe (16 pays), chinois (mandarin de Chine et de Taïwan,
  cantonais de Hong Kong), japonais, coréen, hindi, ourdou, bengali, tamoul, télougou, marathi, gujarati, pendjabi,
  thaï, vietnamien, indonésien, malais, filipino, swahili, amharique, zoulou, afrikaans, catalan, basque, galicien,
  gallois, irlandais, islandais, langues baltes et slaves, géorgien, arménien, azéri, kazakh, ouzbek, mongol, népalais,
  khmer, lao, birman, somali, pachto, maltais…
- Chaque cours (et chaque leçon) a une **langue apprise** et une **langue d'explication** (français par défaut,
  n'importe quelle langue possible : consignes intégrées en français, anglais, espagnol, allemand, italien, portugais
  et néerlandais, traduites une fois pour toutes par l'IA pour les autres).
- Le catalogue propose automatiquement les **voix natives** de chaque langue, l'accent choisi en premier, femmes et
  hommes en alternance. Page **Langues et voix** : écouter, cocher et ordonner ses voix préférées.
- **Voix hors ligne de secours** : Kokoro (anglais, espagnol, français, hindi, italien, japonais, portugais, chinois)
  et XTTS-v2 (17 langues) prennent le relais si le service Microsoft ne répond pas, ou passent en premier si vous le
  souhaitez. Langue sans voix native disponible : voix « multilingues » de Microsoft en dernier recours.

### Balises de langue dans le script

```
Le mot [es]gato[/es] veut dire « chat ».          ← au milieu d'une phrase
[ja] おはようございます。                            ← tout le paragraphe
[en-GB]                                            ← plusieurs paragraphes, avec l'accent
Good morning. How are you?
[/en]
@Maria: [es-MX] ¿Qué tal?                          ← dialogue : chaque personnage a sa voix native
[es] [ralenti] ¿Dónde está la estación?            ← lecture lente
```

Le texte sans balise est lu par la **voix d'explication**. Les balises acceptent les accents (`[es-MX]`, `[pt-BR]`,
`[zh-TW]`, `[zh-HK]`…), les alias (`[jp]`, `[cn]`, `[kr]`) et la fermeture courte `[/]`. Les intervenants
(page **Intervenants**) ont une langue et un sexe : une voix native différente leur est attribuée automatiquement.
Les balises habituelles restent disponibles : `[pause 2s]`, `[réflexion]`, `[lent]`, `[joyeux]`, `*mot important*`,
`[son: ding]`, `[chapitre: Titre]`, `[prise: fichier.wav]`, `%% note non lue`.

### Leçons écrites par DeepSeek
Selon la langue, le niveau (**A1 à C2**) et le thème (se présenter, restaurant, voyage, travail, santé, achats,
chiffres, verbes…) : **listes de vocabulaire** avec traductions et exemples, **phrases utiles**, **dialogues de la vie
courante**, **petites histoires graduées**, **points de grammaire** expliqués simplement, **conseils de prononciation**
et **translittérations** pour les écritures non latines (pinyin, romaji, arabe, russe, coréen, hindi…), questions de
compréhension, quiz et résumé. L'assistant peut aussi proposer **le plan complet du cours** (modules et leçons) et
réutilise les mots déjà vus.

### Exercices audio (générés à partir du vocabulaire)
- **Écoutez puis répétez** : le mot, un silence pour le répéter, puis la bonne prononciation.
- **Lecture lente puis normale** des phrases utiles.
- **Traduction différée** : « Comment dit-on : le lait ? », un silence, puis la réponse dans la langue apprise.
- **Dictée** : chaque phrase lue lentement deux fois, avec le temps d'écrire.
- **Questions de compréhension** après le texte, **résumé** et **quiz** en fin de leçon (repris de Leçon Studio).

Les durées (silence pour répéter, temps pour traduire ou écrire, débit des voix natives et de la lecture lente) se
règlent dans **Production** ; chaque leçon peut avoir ses propres exercices.

### Révisions espacées
Marquez une leçon comme **étudiée** : ses mots et phrases reviennent à **J+1, J+3, J+7, J+14 puis J+30**. La page
**Révisions** montre le calendrier, les mots du jour, produit la **séance audio** (traduction, silence, réponse,
silence pour répéter) et enregistre les mots ratés (retour à J+1).

### Parcours
Modules et leçons par niveau, progression (mots en révision, mots acquis, maîtrise du cours), **glossaire par
langue** et **phrases favorites**.

### Export
- **MP3 par leçon** (un dossier par module) et **MP3 par module**, avec étiquettes, couverture et **chapitres**
  (Vocabulaire, Phrases utiles, Dialogue, Quiz…) ; M4B, WAV, FLAC, Opus, sous-titres et vidéo restent disponibles.
- **Séances de révision** des 30 prochains jours, une par fichier.
- **Support écrit HTML** imprimable : vocabulaire, prononciation, traductions, texte des leçons, réponses des
  exercices (traduction, dictée, compréhension, quiz) et glossaire.
- **Flashcards imprimables** recto-verso (la traduction tombe au dos de son mot).
- **Export Anki** (CSV) avec **l'audio de chaque mot** lu par la voix native.

---

## 📥 Installation

1. Ouvrez la page **Releases** du dépôt et téléchargez `PolyglotteStudio-Setup-x.y.z.exe` (tag `polyglotte-vx.y.z`).
2. Lancez l'installateur (aucun droit administrateur nécessaire). Windows peut afficher « Windows a protégé votre
   ordinateur » (application non signée) : « Informations complémentaires » puis « Exécuter quand même ».
3. Ou bien décompressez `PolyglotteStudio-Portable-x.y.z.zip` et lancez `PolyglotteStudio.exe`.

**Rien à réinstaller** si vous utilisez déjà AudioLivre Studio, PodCast Studio ou Leçon Studio : les moteurs IA, les
modèles, les voix clonées et la clé DeepSeek sont dans le dossier commun `%LOCALAPPDATA%\AudioLivreStudio`.
Tout est gratuit et fonctionne sur un portable sans carte NVIDIA ; l'assistant DeepSeek (facultatif) coûte quelques
centimes par leçon.

## 🚀 Prise en main

1. **Accueil → Nouveau cours** : langue apprise et accent, langue d'explication, niveau ; cochez « Proposer le plan
   du cours avec l'assistant IA » si vous le souhaitez.
2. **Leçons → Créer avec l'IA** : thème, contenus voulus, nombre de mots et de phrases. Relisez et modifiez
   (onglets *Vocabulaire et phrases*, *Texte de la leçon*, *Exercices, résumé et quiz*).
3. **Langues et voix** : écoutez les voix natives et cochez vos préférées.
4. **Production** : génère l'audio (les passages déjà produits sont gardés en cache).
5. **Export** : MP3, révisions, support écrit, flashcards, Anki.
6. Après l'écoute d'une leçon, bouton **Étudiée** ; chaque jour, page **Révisions**.

---

## 🛠️ Développement

```bash
cd polyglotte-studio
pip install -r requirements-dev.txt
python main.py                     # lancer l'application
python -m pytest                   # tests (FFmpeg requis pour les tests audio)
python main.py --selftest r.json   # autotest de bout en bout
```

La compilation est automatisée par GitHub Actions (`.github/workflows/polyglotte-studio-windows.yml`) : tests,
PyInstaller, autotest de l'exécutable, puis installateur Inno Setup. Pour publier une version, poussez un tag
**`polyglotte-v1.0.0`** : l'installateur et la version portable sont ajoutés à la Release. La vérification des mises
à jour dans l'application ne regarde que les tags `polyglotte-v*`.

```
polyglottestudio/
  core/languages.py   catalogue des langues, accents et voix natives (Microsoft, Kokoro, XTTS)
  core/textproc.py    balises de mise en scène et de langue ([es]…[/es]), normalisation, découpage
  core/course.py      modules, script des leçons, exercices audio, consignes par langue d'explication
  core/srs.py         répétition espacée et séances de révision
  core/handouts.py    support écrit HTML, flashcards, export Anki
  core/lang_ai.py     assistant DeepSeek : leçons, plan de cours, consignes, translittérations
  core/renderer.py    choix de la voix de chaque passage, synthèse, secours hors ligne, assemblage stéréo
  ui/pages            accueil, leçons, langues et voix, intervenants, production, export, révisions, glossaire…
packaging/            PyInstaller, Inno Setup, icône et images de l'installateur
tests/                tests automatisés (test_languages.py, test_lessons.py…)
```

## 📜 Licences

Polyglotte Studio est gratuit. Il s'appuie sur Qt for Python (LGPL), FFmpeg (LGPL), PyMuPDF (AGPL), python-docx (MIT),
EbookLib (AGPL), mutagen (GPL), edge-tts (LGPL), num2words (LGPL), NumPy (BSD), libsndfile (LGPL), PortAudio (MIT),
uv (MIT/Apache). Voix Microsoft : service en ligne soumis aux conditions d'utilisation de Microsoft. XTTS-v2 : licence
non commerciale (CPML). Le détail figure dans **Paramètres → À propos et licences**.
