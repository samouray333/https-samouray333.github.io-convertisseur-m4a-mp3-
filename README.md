# https-samouray333.github.io-convertisseur-m4a-mp3-
convertisseur m4a en mp3

## 🎧 AudioLivre Studio (application Windows)

Le dossier [`audiolivre-studio/`](audiolivre-studio/README.md) contient **AudioLivre Studio**, une application Windows gratuite
avec installateur qui transforme vos documents Word/PDF en livres audio professionnels (clonage de voix, mastering ACX,
export M4B/MP3). L'installateur est compilé automatiquement par GitHub Actions.

## 🎙️ PodCast Studio et 🎓 Leçon Studio

Deux applications de la même famille, chacune avec son dossier, ses couleurs, son icône et son installateur :

- [`podcast-studio/`](podcast-studio/README.md) — **PodCast Studio** (orange) : animateurs et invités avec leurs voix,
  script en dialogue écrit avec l'assistant DeepSeek, jingles, épisodes, export MP3 avec métadonnées et flux RSS.
  Versions publiées avec les tags `podcast-v*`.
- [`lecon-studio/`](lecon-studio/README.md) — **Leçon Studio** (vert) : import de cours Word/PDF, modules et leçons,
  voix du professeur, pauses de réflexion, résumés et quiz audio de fin de leçon, export par module.
  Versions publiées avec les tags `lecon-v*`.

## 🌍 Polyglotte Studio

[`polyglotte-studio/`](polyglotte-studio/README.md) — **Polyglotte Studio** (bleu et or) : apprendre les langues à
l'écoute, ~80 langues et leurs accents avec des voix natives gratuites, balises de langue `[es]…[/es]` dans le script,
leçons écrites par DeepSeek par niveau (A1 à C2) et par thème, exercices « écoutez puis répétez », traduction
différée et dictée, révisions espacées (J+1 à J+30), export MP3, flashcards, support écrit et Anki.
Versions publiées avec les tags `polyglotte-v*`.

Les quatre applications partagent les moteurs IA, les modèles, les voix clonées et la clé DeepSeek
(`%LOCALAPPDATA%\AudioLivreStudio`) : un moteur installé dans l'une est disponible dans les autres.
