#!/usr/bin/env python3
"""Génère app/data/foods.js à partir de la table Ciqual 2025 (ANSES).

Source : table de composition nutritionnelle Ciqual 2025, ANSES,
Licence Ouverte / Open Licence Etalab 2.0 (réutilisation commerciale autorisée
avec mention de la source). Copie du fichier CIQUAL2025_FR_2025_11_03.csv
compressée dans tools/.

Usage : python3 tools/build_foods.py
"""
import csv
import gzip
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "CIQUAL2025_FR_2025_11_03.csv.gz")
OUT = os.path.join(HERE, "..", "app", "data", "foods.js")

# Colonnes Ciqual -> clé courte. Ordre = ordre des valeurs dans foods.js.
COLUMNS = [
    ("e", 10),    # Energie kcal (règlement UE 1169/2011)
    ("p", 14),    # Protéines (facteur de Jones)
    ("c", 16),    # Glucides
    ("f", 17),    # Lipides
    ("su", 18),   # Sucres
    ("fi", 26),   # Fibres
    ("sa", 31),   # AG saturés
    ("sl", 49),   # Sel
    ("ca", 50),   # Calcium mg
    ("fe", 53),   # Fer mg
    ("mg", 55),   # Magnésium mg
    ("po", 58),   # Potassium mg
    ("vc", 72),   # Vitamine C mg
    ("vd", 65),   # Vitamine D µg
    ("b12", 82),  # Vitamine B12 µg
]


def parse(v):
    v = v.strip()
    if v in ("", "-"):
        return None
    if v == "traces":
        return 0
    if v.startswith("<"):
        # Valeur inférieure à un seuil : on prend la moitié du seuil.
        return round(float(v[1:].strip().replace(",", ".")) / 2, 3)
    return float(v.replace(",", "."))


def num(x):
    if x is None:
        return None
    x = round(x, 2)
    return int(x) if x == int(x) else x


def main():
    rows = csv.reader(gzip.open(SRC, "rt", encoding="utf-8"), delimiter="\t")
    next(rows)
    groups, foods = [], []
    for r in rows:
        name = r[7].strip()
        if not name:
            continue
        grp = r[3].strip() or "divers"
        if grp not in groups:
            groups.append(grp)
        vals = [parse(r[i]) for _, i in COLUMNS]
        if vals[0] is None:
            p, c, f, fi = (v or 0 for v in (vals[1], vals[2], vals[3], vals[5]))
            if vals[1] is None and vals[2] is None and vals[3] is None:
                continue
            vals[0] = 4 * p + 4 * c + 9 * f + 2 * fi
        foods.append([int(r[6]), name, groups.index(grp)] + [num(v) for v in vals])
    foods.sort(key=lambda x: x[1].lower())
    payload = {
        "source": "Table Ciqual 2025, ANSES (Licence Ouverte Etalab 2.0)",
        "keys": [k for k, _ in COLUMNS],
        "groups": groups,
        "foods": foods,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("window.CIQUAL=")
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")
    print(f"{len(foods)} aliments, {len(groups)} groupes -> {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
