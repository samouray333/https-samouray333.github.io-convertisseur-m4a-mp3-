#!/usr/bin/env python3
"""Filtre l'export CSV français d'Open Food Facts (lu sur l'entrée standard) :
garde les produits vendus en France avec des valeurs nutritionnelles plausibles.
Sortie : TSV compact (code, nom, marque, kcal, p, c, f, sucres, ags, fibres, sel,
portion_g, portion, nutriscore, quantité, popularité).

Source : https://openfoodfacts-ds.s3.eu-west-3.amazonaws.com/fr.openfoodfacts.org.products.csv.zst
Licence des données : ODbL (Open Food Facts).
Pays : produits marqués « France » ou à code-barres GS1 France (300-379).
Usage : zstd -dc fr.openfoodfacts.org.products.csv.zst | python3 filter_off.py | gzip > off-fr.tsv.gz
"""
import html
import sys

IMG_PREFIX = 'https://images.openfoodfacts.org/images/products/'


def image_path(code):
    # Dossier d'image d'Open Food Facts : code sur 13 chiffres découpé 3/3/3/reste.
    if len(code) <= 8:
        return code
    c = code.zfill(13)
    return '/'.join([c[0:3], c[3:6], c[6:9], c[9:]])


def image_ref(code, url):
    # "fr.4" quand l'URL suit le schéma standard, sinon le chemin complet après le préfixe.
    if not url.startswith(IMG_PREFIX) or not url.endswith('.200.jpg'):
        return ''
    rest = url[len(IMG_PREFIX):-len('.200.jpg')]
    folder, _, file = rest.rpartition('/')
    if folder == image_path(code) and file.startswith('front_'):
        return file[len('front_'):]
    return rest


def main():
    inp = sys.stdin.buffer
    header = inp.readline().decode('utf-8').rstrip('\n').split('\t')
    ix = {k: i for i, k in enumerate(header)}
    need = ['code', 'product_name', 'brands', 'countries_tags', 'energy-kcal_100g', 'energy_100g', 'proteins_100g',
            'carbohydrates_100g', 'fat_100g', 'sugars_100g', 'saturated-fat_100g', 'fiber_100g', 'salt_100g',
            'serving_quantity', 'serving_size', 'nutriscore_grade', 'quantity', 'unique_scans_n', 'image_small_url']
    I = [ix[k] for k in need]
    n = len(header)
    out = sys.stdout
    seen = set()
    total = kept = 0

    def fnum(s):
        if not s:
            return None
        try:
            v = float(s)
        except ValueError:
            return None
        return v if v == v else None

    def fmt(v):
        if v is None:
            return ''
        v = round(v, 2)
        return str(int(v)) if v == int(v) else str(v)

    for raw in inp:
        total += 1
        f = raw.decode('utf-8', 'replace').rstrip('\n').split('\t')
        if len(f) < n:
            continue
        code, name, brands, ctry, ekc, ekj, p, c, fat, su, sa, fi, sl, sq, ss, ns, qty, pop, img = (f[i] for i in I)
        code = code.strip()
        # Pays souvent incomplets dans OFF : on garde aussi les codes GS1 France (300-379).
        if 'en:france' not in ctry and not (len(code) == 13 and '300' <= code[:3] <= '379'):
            continue
        if not code.isdigit() or not (8 <= len(code) <= 14) or code in seen:
            continue
        name = ' '.join(html.unescape(name).replace("\\'", "'").split())[:120]
        if len(name) < 2:
            continue
        kcal = fnum(ekc)
        if kcal is None and fnum(ekj) is not None:
            kcal = fnum(ekj) / 4.184
        p, c, fat = fnum(p), fnum(c), fnum(fat)
        if kcal is None or p is None or c is None or fat is None:
            continue
        if not (0 <= kcal <= 950) or not all(0 <= v <= 100 for v in (p, c, fat)) or p + c + fat > 105:
            continue
        # Cohérence énergie / macros (tolérance large : fibres, polyols, alcool).
        est = 4 * p + 4 * c + 9 * fat
        if kcal > 30 and est > 0 and not (0.55 <= kcal / est <= 1.8):
            continue
        su, sa, fi, sl = fnum(su), fnum(sa), fnum(fi), fnum(sl)
        if su is not None and not (0 <= su <= 100): su = None
        if sa is not None and not (0 <= sa <= 100): sa = None
        if fi is not None and not (0 <= fi <= 100): fi = None
        if sl is not None and not (0 <= sl <= 100): sl = None
        sqv = fnum(sq)
        if sqv is not None and not (1 <= sqv <= 2000): sqv = None
        brand = ' '.join(html.unescape(brands.split(',')[0]).replace("\\'", "'").split())[:60]
        ns = ns.strip().lower()
        if ns not in ('a', 'b', 'c', 'd', 'e'): ns = ''
        popv = int(fnum(pop) or 0)
        img = image_ref(code, img.strip())
        seen.add(code)
        kept += 1
        out.write('\t'.join([code, name.replace('\t', ' '), brand, fmt(kcal), fmt(p), fmt(c), fmt(fat), fmt(su), fmt(sa),
                             fmt(fi), fmt(sl), fmt(sqv), ' '.join(ss.split())[:40] if sqv else '', ns,
                             ' '.join(qty.split())[:30], str(popv), img]) + '\n')
    print(f'{total} lignes lues, {kept} produits gardés', file=sys.stderr)

if __name__ == '__main__':
    main()
