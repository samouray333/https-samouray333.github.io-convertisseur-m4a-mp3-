#!/usr/bin/env python3
"""Construit le catalogue hors ligne Calorys (SQLite + index plein texte FTS4)
à partir du TSV produit par filter_off.py, puis le découpe en morceaux gzip
de moins de 45 Mo pour l'hébergement (dépôt GitHub / GitHub Pages).

Usage : python3 build_catalog.py off-fr.tsv.gz sortie/  [AAAA-MM-JJ]
Données : Open Food Facts, licence ODbL.
"""
import gzip
import hashlib
import json
import os
import sqlite3
import sys
import unicodedata

PART = 45 * 1024 * 1024


def norm(s):
    s = unicodedata.normalize('NFD', s.lower())
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    s = s.replace('œ', 'oe').replace('æ', 'ae')
    return ' '.join(''.join(ch if ch.isalnum() else ' ' for ch in s).split())


def num(v):
    return float(v) if v != '' else None


def main():
    src, out = sys.argv[1], sys.argv[2]
    date = sys.argv[3] if len(sys.argv) > 3 else ''
    os.makedirs(out, exist_ok=True)
    rows = []
    with gzip.open(src, 'rt', encoding='utf-8') as fh:
        for line in fh:
            f = line.rstrip('\n').split('\t')
            if len(f) != 16:
                continue
            rows.append(f)
    rows.sort(key=lambda f: -int(f[15] or 0))
    db_path = os.path.join(out, 'catalog.db')
    if os.path.exists(db_path):
        os.remove(db_path)
    db = sqlite3.connect(db_path)
    db.executescript('''
      PRAGMA page_size = 4096;
      CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
      CREATE TABLE food (id INTEGER PRIMARY KEY, code TEXT NOT NULL, name TEXT NOT NULL, brand TEXT,
        kcal REAL, p REAL, c REAL, f REAL, su REAL, sa REAL, fi REAL, sl REAL,
        serving_g REAL, serving TEXT, nutriscore TEXT, qty TEXT);
      CREATE VIRTUAL TABLE fts USING fts4(content="", s);
    ''')
    cur = db.cursor()
    for i, f in enumerate(rows, 1):
        code, name, brand = f[0], f[1], f[2]
        cur.execute('INSERT INTO food VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (i, code, name, brand or None, num(f[3]), num(f[4]), num(f[5]), num(f[6]), num(f[7]), num(f[8]),
                     num(f[9]), num(f[10]), num(f[11]), f[12] or None, f[13] or None, f[14] or None))
        cur.execute('INSERT INTO fts(docid, s) VALUES (?, ?)', (i, norm(name + ' ' + brand)))
    db.execute('CREATE INDEX ix_code ON food(code)')
    db.execute("INSERT INTO fts(fts) VALUES('optimize')")
    meta = {'source': 'Open Food Facts (ODbL), export France', 'date': date, 'count': str(len(rows)), 'schema': '1'}
    db.executemany('INSERT INTO meta VALUES (?,?)', meta.items())
    db.commit()
    db.execute('VACUUM')
    db.close()

    raw = open(db_path, 'rb').read()
    db_sha = hashlib.sha256(raw).hexdigest()
    gz = gzip.compress(raw, 9)
    parts = []
    for n, off in enumerate(range(0, len(gz), PART)):
        chunk = gz[off:off + PART]
        name = f'catalog-{date or "v"}.db.gz.{n:02d}'
        open(os.path.join(out, name), 'wb').write(chunk)
        parts.append({'name': name, 'size': len(chunk), 'sha256': hashlib.sha256(chunk).hexdigest()})
    manifest = {'version': date, 'count': len(rows), 'dbSize': len(raw), 'dbSha256': db_sha,
                'gzSize': len(gz), 'parts': parts, 'source': meta['source']}
    json.dump(manifest, open(os.path.join(out, 'catalog.json'), 'w'), indent=1)
    print(json.dumps(manifest, indent=1))


if __name__ == '__main__':
    main()
