# Catalogue hors ligne Calorys

Base SQLite (index plein texte FTS4) des produits alimentaires vendus en France, tirée de l'export
officiel d'Open Food Facts (`fr.openfoodfacts.org.products.csv.zst`, bucket S3 `openfoodfacts-ds`).

- Produits : 892 632 (export du 28/10/2026), valeurs nutritionnelles complètes et cohérentes.
- Fichiers : `catalog-AAAA-MM-JJ.db.gz.NN` (morceaux gzip à recoller dans l'ordre), `catalog.json` (tailles et SHA-256).
- Construction : `tools/filter_off.py` puis `tools/build_catalog.py` (voir le README principal).

Licence : Open Database License (ODbL) 1.0, © contributeurs d'Open Food Facts. Le contenu des fiches est
sous licence Database Contents. Ce catalogue dérivé est redistribué sous la même licence ODbL.
https://world.openfoodfacts.org/data
