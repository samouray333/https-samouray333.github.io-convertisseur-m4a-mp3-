#!/usr/bin/env python3
"""Regroupe les programmes de calorys/programmes/*.json dans app/data/programmes.js (programmes fournis)."""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ['jeune-16-8-sans-petit-dejeuner', 'reequilibrage-3-repas', 'jeune-18-6', 'jeune-5-2', 'seche-sports-de-combat']
progs = {}
for f in glob.glob(os.path.join(HERE, '..', 'programmes', '*.json')):
    p = json.load(open(f, encoding='utf-8'))
    progs[p['id']] = p
out = [progs[i] for i in ORDER if i in progs] + [p for i, p in sorted(progs.items()) if i not in ORDER]
with open(os.path.join(HERE, '..', 'app', 'data', 'programmes.js'), 'w', encoding='utf-8') as fh:
    fh.write('window.CALORYS_PROGRAMMES=')
    json.dump(out, fh, ensure_ascii=False, separators=(',', ':'))
    fh.write(';\n')
print(len(out), 'programmes')
