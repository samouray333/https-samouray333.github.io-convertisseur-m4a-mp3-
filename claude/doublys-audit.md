# Audit de Doublys 1.2.3

Date : 10 novembre 2026. Périmètre : `doublys-app/` (branche `claude/doublys-windows-app-0tping`, commit `fab968b`).

Méthode :

- relecture du code ;
- mesures automatiques : ruff avec règles étendues, couverture des tests ;
- résultats des tests réels déjà passés sous Windows (CI) et sous Linux.

Limites : pas d'essai manuel de l'interface sous Windows, et **aucun essai sur un vrai épisode** (toutes les
vidéos de test sont fabriquées).

---

## 1. Synthèse

| Domaine | Note | En bref |
|---|---|---|
| Fonctionnalités | 9/10 | Chaîne complète, OCR des sous-titres incrustés, couverture de la VF, contrôle, séries, file d'attente |
| Fiabilité du cœur | 8/10 | Tests réels verts sous Windows ; reprise après arrêt ; aucune réplique perdue en silence |
| Sécurité | 7/10 | Mise à jour vérifiée (SHA-256), clé chiffrée, modèles `.pth` chargés sans code ; quelques téléchargements sans empreinte |
| Robustesse réseau | 6/10 | Un réseau lent peut bloquer le chargement d'un modèle jusqu'à une heure |
| Maintenabilité | 6/10 | Code clair et commenté, mais deux fichiers énormes et beaucoup d'exceptions attrapées en bloc |
| Tests | 7/10 | 86 tests, 62 % du code couvert (cœur : 80 à 93 %) ; moteurs réels testés seulement dans la CI |
| Distribution | 6/10 | Installateur et portable propres, mais exécutable non signé (alerte Windows) |
| Qualité du doublage | à mesurer | Bonne sur les tests ; non vérifiée sur un vrai épisode |

**Verdict** : l'application est complète et sérieusement testée pour un projet de cette taille. Les risques
principaux ne sont pas des bogues connus : ce sont la **robustesse réseau au premier lancement**, la **place
disque** sur les longues vidéos, l'**absence de signature** et le fait que la qualité réelle n'a pas encore été
mesurée sur ton cas réel (Zyuranger).

---

## 2. Points forts

- **Architecture saine** :
  - l'interface (PySide6) est séparée de la chaîne (`core/`) ;
  - les moteurs d'IA tournent dans des processus et des environnements Python à part (uv) : un plantage de
    modèle ne fait pas tomber l'appli, et chaque moteur garde ses propres versions de bibliothèques.
- **Reprise et cache** :
  - chaque étape est relançable ;
  - dépendances entre étapes : changer de sous-titres ne refait pas la séparation ;
  - séparation et transcription reprises par blocs ;
  - voix mises en cache par réplique ;
  - les projets 1.x sont migrés.
- **Aucune perte silencieuse** :
  - 3 essais puis une voix de secours ;
  - voix d'origine remise là où il manque une VF ;
  - tout élément écarté est journalisé (`ecartes.json`) et visible dans la page Contrôle.
- **OCR** : lecture rapide puis relecture complète des cas douteux. 339 sous-titres exacts sur 339 sur 22 min en
  3,5 min sous Windows.
- **Sécurité de base correcte** :
  - installateur de mise à jour vérifié par SHA-256 et supprimé s'il ne correspond pas
    (`core/updates.py`) ;
  - clé DeepSeek chiffrée par DPAPI, avec avertissement si le chiffrement est impossible (`core/secrets.py`) ;
  - modèles RVC chargés avec `torch.load(weights_only=True)` (pas d'exécution de code caché,
    `worker/tts_worker.py:453`) ;
  - Python de base des moteurs vérifié par empreinte (`installer.py:377`) ;
  - aucun `shell=True` ni `eval`.
- **CI complète** :
  - tests Linux ;
  - autotest de l'exécutable Windows ;
  - installation et désinstallation silencieuses testées ;
  - tests réels des moteurs sur processeur (10 scénarios) ;
  - fichier `.sha256` publié avec chaque version.
- **Licences documentées** : FFmpeg en version LGPL, mises en garde XTTS (non commercial), Opus-MT (CC-BY) et
  voix clonées.

---

## 3. Problèmes trouvés, par gravité

### Élevé

| # | Problème | Où | Effet | Correction proposée |
|---|---|---|---|---|
| E1 | **Chargement d'un modèle bloqué par un réseau lent** : au chargement, les bibliothèques Hugging Face revérifient en ligne des modèles déjà téléchargés. Constaté pendant les tests : Chatterbox bloqué plus de 10 min sur « Fetching 6 files ». Le délai d'attente du chargement est d'une heure. | `core/engines/installer.py` (`worker_env`), `neural.py:428` (`timeout=3600`) | Doublage qui semble figé au premier lancement d'un moteur, avec une connexion mauvaise ou filtrée | Une fois les modèles présents, lancer les moteurs en mode hors ligne (`HF_HUB_OFFLINE=1`) ; sinon, délais réseau courts (`HF_HUB_ETAG_TIMEOUT`) et message clair |
| E2 | **Place disque sur une vidéo de 1 h 30** : environ 5 Go de fichiers de travail par projet (son d'origine, voix, fond, mixage en WAV 44,1 kHz, plus le cache des voix), jamais nettoyés après l'export | `travail/` de chaque projet ; seul « Vider le cache des voix » existe | Disque plein sur un portable après quelques épisodes | Proposer « Libérer l'espace » après l'export (garder le projet, supprimer les WAV recalculables), afficher la place prise, prévenir avant de lancer si le disque est presque plein |
| E3 | **Exécutable non signé** | `packaging/` | Alerte « Windows a protégé votre ordinateur » à chaque installation et mise à jour ; certains antivirus bloquent les exécutables PyInstaller non signés | Certificat de signature de code (payant) ou au moins signature dans la CI quand un certificat est disponible |

### Moyen

| # | Problème | Où | Correction proposée |
|---|---|---|---|
| M1 | Modèles Kokoro téléchargés sans vérification d'empreinte | `installer.py` (`SPECS["kokoro"].downloads`, `download()`) | Ajouter une empreinte SHA-256 attendue, comme pour le Python de base |
| M2 | Versions des moteurs incomplètement figées : `transformers>=4.46,<5`, `huggingface-hub`, `librosa`, `faiss-cpu` sans version, dépendances transitives libres ; modèles Hugging Face sans révision figée | `installer.py` (`SPECS`) | Fichier de contraintes par moteur (versions figées, testées dans la CI), révision fixe des modèles |
| M3 | 96 `except Exception`, dont 16 qui ne font rien (`pass`) ; une erreur réelle peut passer inaperçue | `app.py`, `player.py`, `main_window.py`, `qc.py:75`, `tts_worker.py`… | Journaliser au moins en `debug` (fait pour les endroits critiques en 1.2), restreindre le type d'exception attrapé |
| M4 | Reconnaissance des personnes fragile entre voix très proches : corrigée en 1.2.3 pour les répliques à deux voix, mais le seuil de regroupement reste fixe (0,62) | `core/speakers.py` | Seuil adapté automatiquement à la vidéo, ou proposition « ces deux personnes se ressemblent : les fusionner ? » |
| M5 | Traduction directe japonais vers français (Opus-MT ja-fr) de qualité moyenne quand il n'y a pas de sous-titres | `core/models.py` (`LANGUAGES`) | **Vérifié (1.2.4) : passer par l'anglais n'est pas meilleur** (12 phrases comparées : erreurs différentes, parfois pires, comme un sens inversé ou des noms déformés). Garder la traduction directe ; leviers réels : sous-titres anglais (OCR), glossaire, DeepSeek |
| M6 | Voix Microsoft (edge-tts) obtenues par un accès non officiel au service de lecture d'Edge | `core/engines/edge.py` | Le dire dans l'appli (conditions d'utilisation incertaines, usage commercial déconseillé) ; le mode par défaut (Kokoro + Chatterbox) n'en dépend pas |
| M7 | Deux fichiers très gros : `ui/pages/dubbing.py` (1 225 lignes), `core/pipeline.py` (1 068 lignes) ; fonctions longues (23 de plus de 50 instructions) | | Découper : pipeline en un module par étape, page Doublage en composants (tableau, barre d'étapes, choix du texte) |
| M8 | Couverture faible de certaines parties : dialogue de zone OCR (0 %), page Contrôle (58 %), personnes (61 %), processus moteur (14 % hors CI) | `tests/` | Tests d'interface pour la zone et les actions de la page Contrôle ; les tests réels de la CI couvrent le processus moteur |

### Faible

| # | Problème | Où |
|---|---|---|
| F1 | Interface en français seulement, sans réglage de taille de texte ni contraste élevé | `ui/` |
| F2 | Les répliques « non doublées » (générique) sont quand même traduites (calcul inutile) | `pipeline.step_translate` |
| F3 | Le texte OCR enregistré à côté de la vidéo (`(EN, OCR).srt`) est préféré automatiquement s'il existe, même s'il est ancien ; changer la zone suffit à relire | `core/subsources.py` (`rank`) |
| F4 | Le masque de flou s'appuie sur une longue expression FFmpeg (jusqu'à 400 plages) : ça fonctionne, mais c'est à surveiller sur des films très sous-titrés | `core/media.py` (`mask_filter`) |
| F5 | Avertissements d'outils sans conséquence aujourd'hui : SHA-1 pour des clés de cache (pas de sécurité en jeu), `zip()` sans `strict`, `assert` dans l'autotest | divers |

---

## 4. Mesures

| Mesure | Valeur |
|---|---|
| Code de l'application | 17 764 lignes Python, 69 fichiers |
| Tests | 86 tests automatiques (1 539 lignes), 15 contrôles d'autotest, 10 scénarios réels dans la CI |
| Couverture | 62 % au total ; `subsources` 93 %, `qc` 93 %, `align` 92 %, `mixer` 90 %, `speakers` 90 %, `pipeline` 85 %, `ocr` 80 %, `coverage` 74 % |
| Analyse statique (règles étendues) | Aucune erreur sur les règles de base (CI). Avec les règles étendues : surtout du style (imports locaux, nombres magiques), 67 exceptions attrapées en bloc, 16 `try/except/pass` |
| OCR (Windows, 1080p, décor chargé) | 22 min lues en 3,5 min, 339/339 sous-titres exacts |
| Doublage complet (processeur, 4 cœurs) | mesure 1.1 : 15 min de vidéo doublées en 35 min avec voix clonées (environ 2,3 fois la durée) ; une vidéo de 1 h 30 demande donc plusieurs heures |
| Disque | estimation : environ 5 Go de fichiers de travail pour 1 h 30 (WAV 44,1 kHz) |

---

## 5. Plan d'action conseillé

1. **Avant tout** : essai sur un vrai épisode de Zyuranger (extrait de 3 min, puis épisode entier) pour mesurer
   ce qui compte vraiment : sous-titres bien lus, répliques toutes doublées, voix crédibles.
2. **Rapide, fort effet (1 à 2 jours)** :
   - E1 (modèles en mode hors ligne) ;
   - E2 (libérer l'espace après l'export, avertissement de disque) ;
   - M1 (empreinte Kokoro) ;
   - M5 (japonais par l'anglais).
3. **Fiabilité dans la durée** :
   - M2 (versions figées des moteurs) ;
   - M3 (exceptions) ;
   - M7 (découpage des gros fichiers) ;
   - M8 (tests d'interface).
4. **Distribution** : E3 (signature) quand un certificat est disponible.

---

## 6. Corrections faites (1.2.4)

| # | État | Détail |
|---|---|---|
| E1 | **corrigé** | Moteurs chargés en mode hors ligne dès que leurs modèles sont dans le cache ; si un modèle manque (nouvelle langue, autre taille de Whisper), le moteur est relancé en ligne tout seul ; délais réseau courts. Vérifié avec les vrais moteurs : plus aucun blocage, chaîne japonais + sous-titres réussie |
| E2 | **corrigé** | Bouton « Libérer l'espace » (page Export) : supprime les gros fichiers recalculables, garde répliques, traductions et voix ; si on retravaille le projet, seuls l'extraction, la séparation et le mixage sont refaits. Avertissement avant de lancer si le disque est presque plein |
| M1 | **corrigé** | Modèles Kokoro vérifiés par SHA-256 ; un fichier abîmé est retéléchargé, un fichier qui ne correspond pas est refusé |
| M5 | **vérifié, pas de changement** | Voir le tableau : la traduction par l'anglais n'est pas meilleure |
