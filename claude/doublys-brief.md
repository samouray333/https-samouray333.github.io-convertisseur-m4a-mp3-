# Doublys 1.2 : sous-titres existants, OCR des sous-titres incrustés, aucune réplique oubliée

Brief de développement, complété à partir du retour de l'utilisateur et d'une relecture du code de la 1.1.0
(branche `claude/doublys-windows-app-0tping`, commit `e6a80c8`, dossier `doublys-app/`).

> Numéro de version : la 1.1.0 est déjà publiée (sous-titres seuls, couleurs par personne, piste ASS). Ce lot sort
> donc en **1.2.0**. Le titre « Doublys 1.1 » du retour utilisateur désigne ce même lot.

---

## 1. Retour utilisateur et objectif

Un épisode de *Zyuranger* a été doublé avec la 1.0. Résultat jugé « très approximatif ».

Ce qui est confirmé par l'utilisateur :

| Point | Valeur |
|---|---|
| Langue de l'audio | japonais |
| Sous-titres présents | anglais, **incrustés dans l'image** (hardsubs) : ni piste, ni fichier |
| Traduction | pas le problème principal |
| Problème principal | par moments, les personnages parlent mais **il n'y a pas de VF** (répliques manquantes) |

**Chemin à réussir en premier (critère d'acceptation n° 1)** :

```
vidéo japonaise + sous-titres anglais incrustés
  → OCR des sous-titres (texte anglais horodaté)
  → traduction anglais → français (Opus-MT tc-big, le meilleur modèle local disponible)
  → VF calée sur la parole japonaise réelle
  → aucune réplique oubliée : chaque passage parlé a une VF, ou est listé « Parole sans VF »,
    et la voix d'origine revient là où il n'y a pas de VF (jamais de trou)
```

Ce chemin a une conséquence importante : le texte anglais vient de l'OCR, donc la traduction se fait avec
`opus-mt-tc-big-en-fr` (bon modèle) au lieu de `opus-mt-ja-fr` (modèle faible) ou de Whisper forcé en anglais.

---

## 2. Diagnostic de la 1.0 / 1.1 (vérifié dans le code)

Le journal de l'utilisateur n'est pas disponible. Il faudra le demander : `%LOCALAPPDATA%\Doublys\logs\doublys.log`
et le fichier du projet `Documents\Doublys\<titre>\<titre>.doublys`. Les constats ci-dessous viennent de la lecture
du code. Chemins relatifs à `doublys-app/`.

| # | Cause supposée | Constat dans le code | Verdict |
|---|---|---|---|
| 1 | Whisper forcé en anglais sur du japonais | `DubSettings.source_language` vaut `"en"` par défaut (`doublys/core/models.py:220`). La langue « auto » existe, mais seulement si on la choisit dans Paramètres, et la détection ne regarde que le premier morceau (`core/pipeline.py:211`). Rien n'avertit qu'on force l'anglais. Whisper forcé en `en` sur du japonais traduit à la volée, de façon très libre, ou rend des segments peu sûrs. | **Confirmé, cause la plus probable** |
| 1b | Segments supprimés comme « hallucinations » | `is_hallucination` (`doublys/worker/tts_worker.py:698`) supprime un segment entier si `compression_ratio > 2.4`, s'il contient une répétition en boucle, ou si `no_speech_prob > 0.7` et `avg_logprob < -1.0`. En langue forcée incorrecte, ces seuils sont souvent franchis. Seul un compteur part dans le journal (`tts_worker.py:694`), sans horodatage, et rien n'apparaît dans l'interface. | **Confirmé** |
| 2 | `vad_filter` qui coupe la parole sous la musique | `transcribe_words` appelle le pipeline Whisper par lots avec `vad_filter=True` (`tts_worker.py:681`) et les options Silero par défaut (seuil 0,5). Parole sous musique, explosions, voix sous casque : non transmise à Whisper. | **Confirmé** |
| 3 | Demucs laisse une voix trop faible | Avant Demucs, une VAD sur le son d'origine (`tts_worker.py:727`, seuil par défaut) décide des blocs de 30 s à séparer. Un bloc jugé sans parole n'est pas séparé : sa voix isolée est **mise à zéro** (`tts_worker.py:833`), alors que Whisper ne lit que la voix isolée (`speech_source`, `core/pipeline.py:101`). Effet en chaîne : parole manquée par la VAD → voix isolée muette → aucune réplique. Le son japonais reste dans le fond : on l'entend, mais sans VF. | **Confirmé (indirect)** |
| 4 | Répliques écartées par le découpage ou le calage | Découpage : un fragment de moins de 0,6 s est **fusionné** avec son voisin, jamais supprimé (`core/segment.py:106`). Calage : une réplique trop longue est accélérée jusqu'à ×1,12 puis garde l'état `long` (`core/timing.py:78`). Elle est quand même mixée en entier et peut chevaucher la suivante. En revanche, un cri court absent de la sortie mot à mot de Whisper ne devient jamais une réplique. | **Infirmé pour la suppression ; cris perdus en amont (cause 2)** |
| 5 | Échec de synthèse ignoré | Une erreur de moteur passe la réplique en `error` (`core/pipeline.py:492`), sans nouvel essai. Une réplique sans texte français est aussi mise en `error` (`pipeline.py:423`, par exemple quand Opus-MT renvoie un texte vide). Le mixage **saute** les répliques en erreur (`pipeline.py:514`). L'échec est visible en rouge dans le tableau et compté dans l'étape, mais il n'y a ni nouvel essai ni filet. | **Confirmé (partiel)** |
| 6 | Trou audio quand une réplique manque | Avec la séparation (cas par défaut), le mixage ne met que le fond et la VF. La voix d'origine n'est remise que si `keep_original_voice` est activé, et alors partout à -20 dB (`pipeline.py:524`, `core/mixer.py`). Toute réplique absente ou en erreur donne donc un **silence de voix**. | **Confirmé** |
| 7 | (nouveau) Aucun contrôle de couverture | Le contrôle qualité (`core/qc.py`) ne regarde que les répliques existantes. Aucune comparaison entre la parole détectée et les répliques : un passage parlé sans réplique est invisible. | **Confirmé** |
| 8 | (nouveau) Sous-titres existants ignorés | `probe_video` (`core/project.py:106`) ne lit que la vidéo et l'audio. Aucune lecture de piste de sous-titres, de fichier voisin ni d'OCR. | **Confirmé** |

**Conclusion** : les répliques manquantes viennent surtout de la **détection de la parole** (causes 1, 1b, 2 et 3),
pas du découpage ni du calage. Le **trou audio** qui les rend visibles vient du mixage (cause 6). Les deux se
corrigent indépendamment :

- en amont, le texte vient des sous-titres, avec un contrôle de couverture ;
- en aval, la voix d'origine revient là où il n'y a pas de VF.

---

## 3. Exigences

Identifiants `R…` pour le suivi. **Bloquant** : à livrer avant tout le reste.

### 3.1 Aucune réplique oubliée (bloquant)

- **R1. Texte issu des sous-titres** : quand une source de sous-titres existe (pistes, fichier, OCR), chaque
  sous-titre retenu donne une réplique à doubler. Whisper ne décide plus s'il y a de la parole ; il ne sert qu'au
  recalage temporel.
- **R2. Contrôle de couverture**, après l'analyse et après le doublage :
  - parole détectée par Silero VAD sur la piste d'origine **et** sur la voix isolée (union des deux), avec un seuil
    plus bas que la 1.0 : `threshold = 0.35`, `min_speech_duration_ms = 150`, `speech_pad_ms = 100` ;
  - comparaison avec les répliques : toute zone de parole de plus de 0,4 s non recouverte par une réplique est
    listée « Parole sans VF », avec son horodatage, une écoute VO, et une vignette de l'image au milieu de la zone ;
  - actions sur chaque zone :
    - « Créer la réplique depuis le sous-titre voisin » (texte du sous-titre le plus proche à moins de 1,5 s) ;
    - « Saisir le texte » ;
    - « Ne pas doubler » (cri, bruit), mémorisé (`Gap.ignored = True`).
- **R3. Aucune suppression silencieuse** :
  - une réplique trop longue est accélérée jusqu'au maximum, puis **déborde** sur le silence suivant (VAD) ;
    si le silence manque, elle **chevauche** légèrement la suivante (au plus 0,5 s, la suivante étant baissée de
    6 dB pendant le chevauchement) ; jamais supprimée ;
  - un échec de synthèse est **retenté 2 fois** (graine différente), puis avec **une autre voix de base** du même
    genre ; s'il échoue encore, la réplique passe en rouge avec la raison, et compte dans l'indicateur R6 ;
  - un texte français vide après traduction déclenche une nouvelle traduction de la phrase seule ; à défaut, la
    réplique est signalée (jamais doublée en silence).
- **R4. Cris et répliques très courtes** (moins de 1 s : « Ha ! », noms d'attaque, cri de transformation) : doublés
  comme les autres. Option « Garder les cris d'origine » (désactivée par défaut) : une zone de parole courte
  **sans texte de sous-titre** garde la voix japonaise au lieu d'être listée en R2.
- **R5. Filet de sécurité au mixage** : là où aucune VF n'est posée, la voix d'origine (piste voix de Demucs) est
  remise, avec un fondu de 80 ms en entrée et en sortie. Réglage « Là où il n'y a pas de VF » : « Voix d'origine »
  (par défaut) ou « Silence ». Pendant les répliques doublées, la voix d'origine résiduelle reste atténuée
  (R33).
- **R6. Indicateur de couverture** sur la page Doublage, cliquable (ouvre la vue Contrôle, section 3.8) :
  - « 312 répliques, 100 % de la parole couverte » ;
  - ou « 7 passages parlés sans VF, 2 répliques en échec ».
- **R7. Journal des répliques écartées** : chaque élément écarté (segment Whisper, sous-titre de générique,
  panneau, doublon) est enregistré dans `travail/ecartes.json` avec horodatage, texte et raison, et visible dans la
  vue Contrôle. Fini le compteur anonyme de `is_hallucination`.

### 3.2 Langue de l'audio

- **R8.** Détection automatique de la langue parlée à l'ouverture de la vidéo, sur 5 extraits répartis de 30 s
  chacun, pris dans les zones de parole. Méthode : `WhisperModel.detect_language` (faster-whisper ≥ 1.1), vote
  pondéré par la probabilité.
- **R9.** La langue détectée s'affiche sur la page Doublage (« Audio : japonais, détecté »), modifiable.
- **R10.** La valeur par défaut devient « auto ». **Plus jamais de langue forcée sans le dire** : si l'utilisateur
  force une langue différente de la langue détectée avec une probabilité supérieure à 0,8, l'appli l'avertit.
- **R11.** Audio japonais avec sous-titres : Whisper (en japonais) ne sert qu'au recalage temporel (R18). Le texte
  vient des sous-titres.

### 3.3 Sources de sous-titres

Détection automatique à l'ouverture de la vidéo, par ordre de priorité :

1. **R12. Pistes intégrées** (MKV/MP4 : SRT, ASS/SSA, mov_text, WebVTT) :
   - liste des pistes via ffprobe (langue, titre, `disposition.forced`, `disposition.hearing_impaired`) ;
   - extraction avec FFmpeg en `.ass` (garde les styles) ou en `.srt` ;
   - choix : français > anglais > autre ; pistes « forced » (panneaux seuls) écartées par défaut.
   - Les sous-titres image (PGS, VobSub) sont signalés « non pris en charge dans cette version ».
2. **R13. Fichier à côté de la vidéo** : même nom de base, extensions `.srt`, `.ass`, `.ssa`, `.vtt`, avec ou
   sans suffixe de langue (`.en`, `.eng`, `.fr`, `.fre`, `.fra`). Le glisser-déposer d'un fichier sur l'appli
   fonctionne aussi.
3. **R14. Sous-titres incrustés** (OCR, section 3.4) : proposés automatiquement s'il n'y a ni piste ni fichier et
   qu'un texte est détecté dans la bande du bas sur l'échantillon d'images.

L'utilisateur voit la source retenue et peut en changer (liste « Texte de départ » : Whisper seul, piste n, fichier,
OCR).

**Nettoyage commun (R15)** :

- balises ASS (`{\an8}`, `{\i1}`, `{\pos(...)}`…) retirées, `\N` remplacé par un saut de ligne ;
- répliques en `\an8` (en haut de l'écran) traitées comme panneaux ;
- styles dont le nom contient « sign », « op », « ed », « karaoke », « song », « title », « insert » écartés du
  doublage (gardés comme sous-titres si demandé) ;
- notes de traducteur (`TL note`, `T/N`, texte entre crochets en début de ligne) retirées ;
- doublons et lignes vides retirés ;
- balises HTML d'un SRT (`<i>`, `<font>`) retirées.

**R16. Répliques à deux voix** : une ligne « - Salut ! - Bonjour. » (ou deux lignes commençant chacune par un tiret)
est coupée en deux répliques. Le temps est partagé selon la parole détectée (pause la plus proche du point de
partage proportionnel), sinon au prorata des caractères.

**R17.** Si une piste ou un fichier **français** existe : la traduction est sautée et le texte français est
utilisé tel quel (marqué `fr_edited` pour ne pas être retraduit).

**Usage des sous-titres dans la chaîne** :

- **R18. Recalage** :
  - début et fin resserrés sur la parole réelle (VAD sur la voix isolée, sinon énergie), dans une marge de ± 0,6 s ;
  - si la parole déborde du sous-titre, la réplique est **élargie**, jamais coupée ;
  - décalage global automatique : corrélation entre l'indicatrice « sous-titre présent » et l'indicatrice « parole
    détectée », sur ± 10 s, par pas de 20 ms ; appliqué si le gain de recouvrement dépasse 10 % ;
  - décalage manuel (+/- secondes) sur la page Doublage.
- **R19. Fusion** seulement des morceaux d'une même phrase très rapprochés : écart de moins de 0,3 s, phrase non
  terminée (pas de `.`, `!`, `?`, `…` à la fin), même personne probable.
- **R20. Génériques chantés (OP/ED)** : musique d'origine conservée, pas de doublage. Ils sont repérés par :
  - le style ASS ou le texte karaoké (`{\k…}`) ;
  - ou une part de musique élevée dans Demucs (énergie du fond supérieure de 12 dB à celle de la voix pendant plus
    de 60 s d'affilée) ;
  - ou une plage manuelle « Ne pas doubler de … à … » (plusieurs plages possibles, mémorisées par série).

### 3.4 OCR des sous-titres incrustés (cœur du lot)

**R21. Zone de lecture** :

- bande du bas détectée automatiquement sur 60 images réparties sur la vidéo : pour chaque image, masque des pixels
  « texte clair entouré de sombre » (luminance > 200 et pixel à moins de 3 px d'un pixel de luminance < 60) ;
- la bande retenue couvre les lignes où ce masque est le plus fréquent (au moins 15 % des images), avec une marge
  de 8 % de la hauteur ;
- elle est affichée sur une vignette et réglable à la souris (bords haut et bas) ;
- zone du haut en option, pour les panneaux.

**R22. Échantillonnage** :

- 4 images par seconde par défaut (réglable de 2 à 10) ;
- FFmpeg décode directement la bande réduite : `-vf fps=4,crop=W:H:0:Y,scale=-2:120,format=gray`, sortie
  `rawvideo` lue en flux par un tuyau ;
- mémoire stable : une seule image en mémoire à la fois, plus la précédente (cible : moins de 300 Mo pour un épisode
  de 22 min, mesurée dans les tests).

**R23. Détection des changements** :

- masque binaire du texte (blanc ou jaune avec contour noir), légèrement dilaté ;
- comparaison avec le masque précédent (part de pixels différents, rapportée aux pixels de texte) ;
- l'OCR n'est lancé que quand le masque change (seuil 12 %) et qu'il contient du texte.

**R24. Moteur OCR local** :

- par défaut : **RapidOCR** (modèles PP-OCR en ONNX, onnxruntime CPU, Apache 2.0), dans un environnement
  « ocr » installé à la demande (page Moteurs IA, environ 80 Mo) comme les autres moteurs ;
- repli : `Windows.Media.Ocr`, seulement si la langue anglaise d'OCR est installée dans Windows. Sur un Windows
  français elle est souvent absente : le vérifier (`OcrEngine.AvailableRecognizerLanguages`) et le dire, avec la
  marche à suivre (« Paramètres > Heure et langue > Langue > Ajouter l'anglais, avec la reconnaissance optique ») ;
- vérification de la confiance moyenne par ligne (sortie RapidOCR).

**R25. Prétraitement** :

- agrandissement ×2 (Lanczos) ;
- isolement du texte par couleur et contour : on garde les pixels clairs proches d'un contour sombre, le reste
  passe en gris neutre ;
- plusieurs lignes gérées : boîtes de détection triées de haut en bas, une ligne de sous-titre par boîte ou par
  groupe de boîtes alignées.

**R26. Fusion dans le temps** :

- textes identiques ou quasi identiques consécutifs (distance d'édition normalisée < 0,2) regroupés en un sous-titre
  avec début et fin ;
- début et fin précis : autour de chaque changement détecté à 4 im/s, la fenêtre de 0,25 s qui le précède est
  redécodée à 25 im/s (bande seule) et on cherche la première image où le masque change (dichotomie sur ces
  images) ; précision visée ± 0,04 s, tolérance des tests ± 0,15 s.

**R27. Nettoyage OCR** :

- confusions classiques corrigées : `l`/`I`/`1`, `0`/`O`, `rn`/`m`, `vv`/`w` ;
- apostrophes et guillemets typographiques, espaces avant la ponctuation ;
- choix guidé par un dictionnaire anglais (liste de mots fréquents embarquée, environ 50 000 mots, licence libre)
  et par le glossaire de la série (R30) ;
- lignes à faible confiance (moyenne < 0,80, ou un mot < 0,5 absent du dictionnaire) marquées « OCR à vérifier ».
- **Option DeepSeek** : correction des fautes d'OCR avec le contexte (répliques voisines et glossaire), sans
  reformuler. Le texte n'est envoyé qu'avec l'accord déjà donné pour DeepSeek.

**R28. Éléments à écarter du doublage** (gardés en sous-titres si demandé) :

- panneaux : texte en haut de l'image ;
- génériques karaoké et crédits : texte qui change plus de 2 fois par seconde pendant plus de 10 s, ou qui suit la
  musique (R20) ;
- textes d'un ou deux caractères isolés.

**R29. Export de l'OCR** : le résultat est enregistré en `<nom> (EN, OCR).srt` à côté de la vidéo. Il est réutilisé
au lieu de relancer l'OCR si on rouvre la vidéo (empreinte : taille, date et durée de la vidéo, réglages de zone).

### 3.5 Les sous-titres anglais restent visibles dans l'image

**R36. Masquage à l'export** (activé par défaut quand des sous-titres incrustés ont été détectés) :

- flou fort (`boxblur`) ou bandeau sombre sur la zone détectée, **uniquement pendant les moments où un sous-titre
  est présent** (`enable='between(t,a,b)+…'`, expression découpée par blocs si elle devient trop longue) ;
- en option, sous-titres français incrustés à la place (même zone, style ASS existant) ;
- réencodage nécessaire, donc plus lent. Encodeur compatible LGPL : `h264_mf` sous Windows (Media Foundation),
  sinon `libopenh264`, qualité réglable (débit : 4, 8 ou 12 Mb/s pour du 1080p) ;
- sans cette option, la vidéo reste copiée telle quelle.

### 3.6 Qualité de la traduction (utile, pas prioritaire)

- **R30. Glossaire par série** :
  - noms propres et termes fixes : Geki, Goushi, Dan, Boi, Mei, Bandora, Burai, Dragonranger, Daizyujin,
    Zyusouken ;
  - chaque terme a une prononciation française (« Daizyujin » → « Daïzyoudjine ») utilisée par la synthèse ;
  - proposé automatiquement : mots en majuscule fréquents dans les sous-titres et absents du dictionnaire ;
  - réutilisable entre épisodes (déjà prévu dans `core/series.py`) et utilisé aussi pour corriger l'OCR.
- **R31. Traduction avec contexte** : par blocs de répliques voisines (2 avant, 2 après en contexte) au lieu de
  ligne par ligne.
- **R32. Option DeepSeek** : traduction adaptée au doublage (longueur visée, oralité), glossaire injecté (déjà en
  partie dans `core/ai.py`).

### 3.7 Calage, voix, mixage

**Calage et rythme**

- Budget de longueur dès la traduction, calculé sur la durée de parole réelle détectée (VAD), pas sur la durée du
  sous-titre.
- Accélération maximale plus douce : `max_rate` passe de 1,30 à **1,20**, et `max_tempo` reste 1,12 ;
  le débordement prend le relais (R3).
- Rapport des répliques trop longues ou trop accélérées, avec « Raccourcir » en un clic (fonction existante).

**Voix et personnes**

- Empreintes calculées sur la voix isolée (déjà le cas) ; répliques de moins de 1 s rattachées au groupe le plus
  proche au lieu de créer une personne.
- Fusion et séparation de personnes sur la page Personnes (« Fusionner avec… », « Séparer ces répliques »).
- Extrait de clonage choisi parmi les répliques les plus propres. Critères :
  - rapport voix / fond élevé (> 15 dB) ;
  - niveau proche de la médiane de la personne (pas de cri) ;
  - pas de voix filtrée sous casque (largeur de bande > 5 kHz).

  L'extrait reste modifiable (fonction existante).
- Émotion : répliques criées détectées (niveau et hauteur), voix de base plus intense (Chatterbox expressif
  existant) pour les cris de transformation et les combats.

**Mixage**

- **R33.** Voix d'origine résiduelle atténuée (-20 dB par défaut) **pendant** les répliques doublées, et remise à
  plein niveau **là où il n'y a pas de VF** (R5), avec des rampes de 80 ms.
- Niveau de la VF calé sur l'original réplique par réplique (existant), puis compresseur léger sur la piste VF
  (ratio 2:1, seuil -18 dBFS, attaque 10 ms, relâche 150 ms).

### 3.8 Relecture rapide

- **R34. Vue « Contrôle »** (nouvel onglet de la page Doublage), triée par gravité :
  1. passages parlés sans VF (R2) ;
  2. répliques en échec de voix ;
  3. répliques à risque : OCR douteux, réplique trop accélérée ou qui déborde, personne incertaine ;
  4. éléments écartés (R7), repliés.

  Pour chaque entrée : la vignette de l'image du sous-titre, une écoute immédiate VO et VF, et l'action adaptée.
- **R35. Réexport rapide** après corrections : seules les répliques modifiées sont régénérées (cache par réplique
  déjà en place), puis remixage et export.

---

## 4. Architecture proposée

### 4.1 Nouveaux modules

| Module | Rôle |
|---|---|
| `core/subsources.py` | Liste des pistes de sous-titres (ffprobe), fichiers voisins, extraction FFmpeg, lecture SRT / ASS / VTT, nettoyage R15, coupe des répliques à deux voix R16 |
| `core/ocr.py` | Côté appli : détection de la bande R21, décodage FFmpeg en flux R22, masques et changements R23, fusion R26, nettoyage R27 |
| `worker` (environnement « ocr ») | Commande `ocr_lines` : RapidOCR sur un lot d'images de bande, renvoie texte, boîtes et confiances |
| `core/winocr.py` | Repli `Windows.Media.Ocr` (paquets `winrt-*`), test de présence de la langue anglaise |
| `core/align.py` | Recalage R18 : VAD, décalage global par corrélation, resserrage et élargissement |
| `core/coverage.py` | Couverture R2 : union des VAD, zones sans réplique, actions, indicateur R6 |
| `core/langdetect.py` | Détection de la langue sur plusieurs extraits R8 |

### 4.2 Modèle de données (compatible avec les anciens projets)

- `Line` :
  - `source` : `"asr"`, `"track"`, `"file"` ou `"ocr"` ;
  - `src_start`, `src_end` : temps d'origine du sous-titre ;
  - `ocr_conf` ;
  - `frame` : vignette relative ;
  - `no_dub` : générique, panneau, « ne pas doubler » ;
  - `attempts` : essais de synthèse.
- `Project` :
  - `subtitle_source` : type, piste ou chemin, langue ;
  - `ocr_zone` : haut et bas en fraction de la hauteur, option zone du haut ;
  - `subtitle_offset` ;
  - `gaps` : zones de parole sans VF, avec état ;
  - `no_dub_ranges`.
- `DubSettings` :
  - `source_language = "auto"` ;
  - `language_confidence` ;
  - `vo_fallback = True` ;
  - `keep_original_shouts = False` ;
  - `ocr_fps = 4` ;
  - `max_rate = 1.20`.
- `ExportOptions` : `mask_hardsubs`, `mask_style` (`"blur"` | `"band"`), `replace_with_fr`, `video_bitrate`.

### 4.3 Étapes du pipeline

```
extract → language → subtitles → separate → transcribe(*) → segment(**) → align → speakers → translate(***)
        → voices → dub → mix → coverage
```

- `language`, `subtitles`, `align`, `coverage` : nouvelles étapes, relançables comme les autres.
- (*) Avec des sous-titres : transcription dans la langue détectée, utilisée seulement pour le recalage (mots
  horodatés) ; elle peut être sautée si la VAD suffit.
- (**) Avec des sous-titres : une réplique par sous-titre (après nettoyage, coupe des deux voix, fusion R19).
- (***) Sautée si la source est française (R17).
- `coverage` tourne aussi après chaque modification de réplique (rapide : comparaison d'intervalles).

### 4.4 Paramètres par défaut

| Paramètre | 1.1 | 1.2 |
|---|---|---|
| Langue de l'audio | `en` | `auto` (5 extraits) |
| Whisper `vad_filter` | activé, seuil 0,5 | sans sous-titres : seuil 0,35 ; avec sous-titres : recalage seulement |
| VAD de couverture | aucune | Silero 0,35, original + voix isolée |
| Seuil « parole sans VF » | aucun | 0,4 s |
| Suppression « hallucination » | silencieuse | journalisée (R7), segment gardé « à vérifier » si `no_speech_prob` < 0,9 |
| `max_rate` | 1,30 | 1,20 |
| Réplique trop longue | accélérée, puis chevauchement non géré | accélérée, débordement sur le silence, puis chevauchement ≤ 0,5 s |
| Échec de voix | erreur, sautée au mixage | 2 essais, autre voix, puis rouge + filet VO |
| Là où il n'y a pas de VF | silence | voix d'origine (fondu 80 ms) |
| OCR | aucun | 4 im/s, RapidOCR |

---

## 5. Licences

| Composant | Licence | Remarque |
|---|---|---|
| RapidOCR, modèles PP-OCR (PaddleOCR) | Apache 2.0 | redistribution possible, mention dans « À propos » |
| onnxruntime | MIT | |
| Silero VAD (via faster-whisper) | MIT | déjà utilisé |
| winrt (Windows.Media.Ocr) | MIT (paquets Python) | moteur fourni par Windows |
| FFmpeg BtbN LGPL | LGPL 2.1 | déjà utilisé ; `h264_mf` et `libopenh264` compatibles, pas de libx264 (GPL) |
| Dictionnaire anglais embarqué | à choisir sous licence libre (par exemple SCOWL, licence permissive) | vérifier avant intégration |

Le flou des sous-titres d'origine n'enlève rien aux droits sur la vidéo : avertissement existant sur l'usage
personnel et les voix clonées inchangé.

---

## 6. Plan par lots

Chaque lot est livré testé (tests Linux, autotest, build Windows vert) avant le suivant.

| Lot | Contenu | Critère de fin |
|---|---|---|
| **A (bloquant)** | Langue auto R8 à R11 ; filet VO R5 et R33 ; aucune suppression R3 ; couverture R2, R6, R7 ; cris R4 | Test « couverture » vert (section 7) ; sur la vidéo synthétique, aucun passage parlé sans VF ni signalement |
| **B** | Pistes et fichiers de sous-titres R12 à R17 ; recalage R18 ; fusion R19 ; génériques R20 | Tests MKV/MP4/fichier voisin et décalage +1,5 s verts |
| **C (cœur)** | OCR R21 à R29, environnement « ocr », repli Windows | Test OCR synthétique (texte et timings ± 0,15 s) ; OCR de 22 min en moins de 10 min sur le runner Windows |
| **D** | Masquage des sous-titres d'origine R36 | Test « zone floutée seulement pendant les sous-titres » |
| **E** | Qualité : glossaire R30, contexte R31, DeepSeek R32, calage, personnes, compresseur | Tests unitaires ; écoute sur l'épisode réel |
| **F** | Vue Contrôle R34, réexport rapide R35 | Test d'interface : correction d'une zone puis réexport sans refaire les autres répliques |

Validation finale sur **le vrai épisode de Zyuranger** : demander à l'utilisateur un extrait de 2 à 3 minutes avec
les sous-titres incrustés (ou l'épisode), à garder hors du dépôt.

---

## 7. Tests

| Test | Contenu | Attendu |
|---|---|---|
| Couverture | Vidéo synthétique : paroles sous musique forte (-6 dB voix / musique), 3 cris courts (< 0,6 s), une réplique très longue pour son créneau, un échec de synthèse simulé (moteur factice qui lève une erreur 3 fois sur une réplique) | Chaque passage parlé a une VF ou figure dans « Parole sans VF » ; aucune réplique supprimée en silence (chaque écart est dans `ecartes.json`) ; la voix d'origine revient là où il n'y a pas de VF (énergie mesurée dans le mixage) ; la réplique longue déborde sans être coupée ; l'échec est retenté puis affiché en rouge |
| OCR | Vidéo synthétique avec sous-titres incrustés (FFmpeg `drawtext` : blanc à contour noir, 3 polices, 1 et 2 lignes, fond chargé `testsrc2` + bruit) et audio de parole | Texte OCR comparé au texte attendu (taux d'erreur par caractère < 3 %) ; début et fin à ± 0,15 s |
| Langue | Extrait japonais synthétique (Chatterbox multilingue, comme le test `full-ja` existant) | « ja » détecté |
| Sources | MKV avec une piste ASS (styles OP, ED, Signs et Default) et une piste SRT ; MP4 avec mov_text ; fichier `.en.srt` à côté | Bonne piste choisie ; OP/ED/Signs écartés du doublage ; balises retirées ; français prioritaire |
| Recalage | Sous-titres décalés de +1,5 s | Décalage retrouvé à ± 0,1 s |
| Deux voix | « - Salut ! - Bonjour. » | Deux répliques, temps partagé sur la pause |
| Masquage | Export avec masquage | Zone floutée seulement pendant les sous-titres (images comparées avant, pendant et après) |
| Performance OCR | 22 min de vidéo 1080p synthétique, runner Windows (job `engines`, matrice `ocr`) | Moins de 10 min ; mémoire maximale < 300 Mo pour le processus de lecture |
| Non-régression | Suite existante (65 tests) et autotest (13 contrôles) | Verts |

Les tests lourds (OCR réel, langue, performance) vont dans le job optionnel « Test réel des moteurs IA » du workflow
(`[engines]`). Les tests rapides utilisent des moteurs factices, comme aujourd'hui.

---

## 8. Risques et points ouverts

- **Temps de l'OCR** : PP-OCR (détection et reconnaissance) sur CPU coûte environ 0,2 à 0,5 s par image de bande.
  Avec la détection des changements, un épisode de 22 min demande environ 600 à 900 OCR, soit 3 à 7 min. Si c'est
  trop lent, on saute le modèle de détection : la bande est déjà connue, les lignes sont découpées par projection
  horizontale du masque, puis seule la reconnaissance tourne.
- **Sous-titres jaunes ou à fond opaque** : le masque « clair à contour sombre » est paramétré pour blanc et jaune.
  Un fond opaque (bandeau noir) demande une variante, détectée automatiquement par la bande.
- **Fansubs avec effets** (karaoké animé, texte qui bouge) : écartés du doublage par R28, pas lus mot à mot.
- **Recalage sur du japonais** : la VAD suffit dans la plupart des cas. Whisper japonais n'est utile que pour les
  sous-titres très décalés ou fusionnés.
- **Windows.Media.Ocr** : nécessite les paquets `winrt` dans l'exécutable PyInstaller, à vérifier sur le runner
  Windows.
- **À demander à l'utilisateur** :
  - le journal `%LOCALAPPDATA%\Doublys\logs\doublys.log` de l'essai 1.0 ;
  - le fichier projet `.doublys` ;
  - un extrait de l'épisode, pour confirmer le diagnostic (section 2) et servir de test réel.

## 9. Hors périmètre de ce lot

- OCR de sous-titres image dans une piste (PGS, VobSub) : signalé, pas lu.
- OCR d'autres langues que l'anglais (le moteur le permet, mais ce n'est pas testé).
- Synchronisation labiale (lip-sync) de l'image.


---

## 10. État de réalisation (1.2.0)

| Exigence | État | Remarque |
|---|---|---|
| R1 texte issu des sous-titres | fait | `core/pipeline.py` : étape « Sous-titres existants », `lines_from_cues` |
| R2 couverture (VAD 0,35, original + voix isolée, > 0,4 s) | fait | `core/coverage.py` ; actions dans la page Contrôle |
| R3 aucune suppression (débordement, chevauchement -6 dB, 3 essais + voix de secours, traduction vide retentée) | fait | `dub_line`, `mixer.mix`, `step_translate` |
| R4 cris courts doublés, option « garder les cris d'origine » | fait | OCR : « Ha ! » gardé s'il est net ; seuil VAD bas |
| R5 / R33 voix d'origine là où il n'y a pas de VF (fondu 80 ms), atténuée sous la VF | fait | réglable : voix d'origine ou silence |
| R6 indicateur de couverture cliquable | fait | page Doublage → page Contrôle |
| R7 journal des éléments écartés | fait | `travail/ecartes.json`, section « Écartés du doublage » |
| R8 à R11 langue détectée sur 5 extraits, « auto » par défaut, avertissement si forcée autrement | fait | `detect_language` (worker Whisper) |
| R12 à R17 pistes, fichiers, nettoyage, deux voix, français prioritaire | fait | `core/subsources.py` ; sous-titres image (PGS) signalés non pris en charge |
| R18 recalage (décalage global par corrélation, resserrage, élargissement, décalage manuel) | fait | `core/align.py` |
| R19 fusion des morceaux de phrase | fait | |
| R20 génériques chantés (style, karaoké, musique dominante ≥ 60 s, plages « ne pas doubler ») | fait | plages et zone OCR gardées par série |
| R21 bande détectée et réglable à la souris | fait | bouton « Zone… » ; la zone du haut (panneaux) n'est pas lue : ils ne sont pas doublés |
| R22 / R23 lecture en flux et détection des changements | fait, **méthode modifiée** | au lieu de 4 im/s + dichotomie à 25 im/s : une seule lecture à 12,5 im/s (réglable 4 à 25) de la bande seule, le masque est comparé à chaque image ; précision ± 0,08 s, sans second décodage |
| R24 RapidOCR dans un environnement « ocr » | fait | **reconnaissance seule** sur des lignes découpées par le masque (25 ms par ligne au lieu de 1,5 s pour la détection complète). Repli `Windows.Media.Ocr` : **non fait** (non vérifiable ici, langue OCR anglaise rarement installée ; RapidOCR s'installe avec les autres moteurs) |
| R25 prétraitement | fait | partie centrale de l'image pour ignorer le décor sur les côtés ; l'agrandissement est fait par RapidOCR (hauteur 48 px) |
| R26 fusion des textes quasi identiques | fait | |
| R27 nettoyage OCR | fait, **sans dictionnaire anglais** | règles l/I/1, 0/O, ponctuation, apostrophes + glossaire (lettres confondables) ; relecture DeepSeek en option (page Contrôle) ; confiance < 80 % signalée |
| R28 panneaux, karaoké, crédits, logos écartés | fait | |
| R29 `<nom> (EN, OCR).srt` réutilisé | fait | retrouvé comme fichier voisin |
| R36 masquage à l'export (flou ou bandeau, seulement pendant les sous-titres) | fait | encodeurs : Media Foundation puis OpenH264 (libx264 seulement s'il est présent) |
| R30 glossaire avec prononciation, noms proposés | fait | « terme = rendu \| prononciation » |
| R31 traduction avec contexte | partiel | DeepSeek : contexte complet ; Opus-MT : phrases qui traversent plusieurs répliques déjà gérées (1.0) |
| R32 DeepSeek orienté doublage | déjà présent (1.0) | |
| Calage : `max_rate` 1,20, débordement 1,5 s | fait | |
| Personnes : extrait le plus propre, fusion | fait | « Fusionner avec… » sur la page Personnes ; séparation par « Attribuer à → Nouvelle personne » (page Doublage) |
| Compresseur léger sur la VF | fait | 2:1 au-dessus de -18 dBFS |
| R34 vue Contrôle | fait | page « Contrôle » |
| R35 réexport rapide | déjà présent | cache par réplique |

### Mesures (sandbox Linux, 4 cœurs, sans carte graphique)

- Chaîne réelle japonais + sous-titres anglais incrustés (25 s, Chatterbox multilingue pour la voix japonaise) :
  langue détectée « japonais », 6 sous-titres lus sur 6 (5 à l'identique, 1 à 99 %), temps à ± 0,07 s, 6 répliques
  doublées, **100 % de la parole couverte**, sous-titres d'origine floutés à l'export.
- Lecture OCR : 3 min de vidéo 1080p lues en 14 s, 47 sous-titres exacts sur 47 (soit environ 2 min pour 22 min).
- Tests automatisés : 83 tests, autotest 14 contrôles.
