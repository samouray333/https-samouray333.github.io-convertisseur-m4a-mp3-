# Programmes Calorys

Un programme est un fichier `.json` que Calorys importe (Profil > Programmes > Importer un fichier). L'appli se règle dessus : fenêtre de jeûne et minuteur automatique, repas supprimés, répartition des calories, objectifs, planning d'eau, notifications, règles et conseil du jour. Quand on arrête le programme, les réglages d'avant reviennent.

Les fichiers de ce dossier sont fournis dans l'appli et servent d'exemples. Le bouton « Modèle à remplir » exporte un modèle vierge.

## Format

```json
{
  "format": "calorys-programme",
  "version": 1,
  "id": "mon-programme",
  "name": "Mon programme",
  "author": "Moi",
  "description": "Texte affiché avant de démarrer.",
  "durationDays": 56,
  "goal": { "type": "lose", "pace": 0.5 },
  "macros": { "preset": "balanced" },
  "fasting": { "eatStart": "12:00", "eatEnd": "20:00", "autoStart": true },
  "meals": { "breakfast": 0, "lunch": 0.45, "dinner": 0.4, "snack": 0.15 },
  "water": { "goalMl": "auto", "schedule": [ { "at": "07:30", "ml": 500, "text": "Au réveil" } ] },
  "reminders": [ { "at": "12:00", "title": "Fenêtre ouverte", "text": "Bon appétit", "days": [1, 2, 3, 4, 5] } ],
  "dayOverrides": [ { "days": [1, 4], "kcal": 600, "note": "jour réduit" } ],
  "rules": [ "Une règle par ligne" ],
  "tips": [ "Un conseil par jour" ]
}
```

| Champ | Rôle |
|---|---|
| `format` | obligatoire, toujours `"calorys-programme"` |
| `name` | obligatoire |
| `durationDays` | durée en jours (0 = sans fin) |
| `goal` | `type` : `lose`, `maintain` ou `gain` ; `pace` : kg par semaine (0 à 1) |
| `macros` | `preset` : `balanced`, `cut`, `bulk`, `lowCarb`, `keto` ; ou `{ "p": 30, "c": 40, "f": 30 }` (total 100) |
| `fasting` | heures de début et de fin de la fenêtre de repas (HH:MM) ; `autoStart` lance et arrête le minuteur de jeûne tout seul |
| `meals` | part de chaque repas (`breakfast`, `lunch`, `dinner`, `snack`) ; 0 = repas supprimé ; les parts sont ramenées à 100 % |
| `water` | `goalMl` : nombre ou `"auto"` (35 ml/kg + séances) ; `schedule` : heures et quantités, chacune devient une notification et un créneau à cocher |
| `reminders` | notifications : heure, titre, texte ; `days` facultatif (1 = lundi … 7 = dimanche) |
| `dayOverrides` | jours spéciaux : objectif calorique fixe ces jours-là (ex. 5:2) |
| `rules`, `tips` | affichés dans l'appli (un conseil différent chaque jour) |

Limites : 40 notifications, 24 créneaux d'eau, objectif des jours spéciaux entre 400 et 6 000 kcal. Un fichier invalide est refusé avec la liste des erreurs.

Pour régénérer la liste des programmes fournis : `python3 tools/build_programmes.py`.
