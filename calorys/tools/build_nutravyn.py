#!/usr/bin/env python3
"""Génère app/data/nutravyn.js à partir de tools/nutravyn-seed.json
(catalogue de base et recettes de l'appli Nutravyn, QMTech)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
seed = json.load(open(os.path.join(HERE, 'nutravyn-seed.json'), encoding='utf-8'))
cats = []
foods = []
for f in seed['foods']:
    if f['category'] not in cats:
        cats.append(f['category'])
    foods.append([f['id'], f['name'], cats.index(f['category']), f['kcal'], f['protein'], f['carbs'], f['fat']])
recipes = []
for r in seed['recipes']:
    ps = r['per_serving']
    recipes.append({'id': r['id'], 'name': r['name'], 'servings': r['servings'], 'minutes': r.get('minutes', 0),
                    'tags': r.get('tags', []), 'steps': r.get('steps', []),
                    'items': [[i['food_id'], i['grams']] for i in r['ingredients']],
                    'per': [ps['kcal'], ps['protein'], ps['carbs'], ps['fat']]})
out = os.path.join(HERE, '..', 'app', 'data', 'nutravyn.js')
with open(out, 'w', encoding='utf-8') as fh:
    fh.write('window.NUTRAVYN=')
    json.dump({'cats': cats, 'foods': foods, 'recipes': recipes}, fh, ensure_ascii=False, separators=(',', ':'))
    fh.write(';\n')
print(len(foods), 'aliments,', len(recipes), 'recettes ->', os.path.relpath(out))
