/* Calorys : base d'aliments, recherche, portions, calculs nutritionnels. */
(function () {
  'use strict';
  const DB = window.CIQUAL;
  const NKEYS = DB.keys; // e p c f su fi sa sl ca fe mg po vc vd b12

  const NUTRIENTS = {
    e: { label: 'Énergie', unit: 'kcal' },
    p: { label: 'Protéines', unit: 'g' },
    c: { label: 'Glucides', unit: 'g' },
    su: { label: 'dont sucres', unit: 'g', sub: true },
    f: { label: 'Lipides', unit: 'g' },
    sa: { label: 'dont AG saturés', unit: 'g', sub: true },
    fi: { label: 'Fibres', unit: 'g' },
    sl: { label: 'Sel', unit: 'g' },
    ca: { label: 'Calcium', unit: 'mg' },
    fe: { label: 'Fer', unit: 'mg' },
    mg: { label: 'Magnésium', unit: 'mg' },
    po: { label: 'Potassium', unit: 'mg' },
    vc: { label: 'Vitamine C', unit: 'mg' },
    vd: { label: 'Vitamine D', unit: 'µg' },
    b12: { label: 'Vitamine B12', unit: 'µg' }
  };

  // Apports de référence adulte (règlement UE 1169/2011, annexe XIII) pour les % affichés.
  const RDA = { fi: 30, sl: 6, su: 90, sa: 20, ca: 800, fe: 14, mg: 375, po: 2000, vc: 80, vd: 5, b12: 2.5 };

  function norm(s) {
    return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/œ/g, 'oe').replace(/æ/g, 'ae').replace(/[^a-z0-9]+/g, ' ').trim();
  }

  const ciqual = new Map();
  const index = [];
  for (const row of DB.foods) {
    const per100 = {};
    NKEYS.forEach((k, i) => { per100[k] = row[3 + i]; });
    const food = { key: 'c:' + row[0], name: row[1], group: DB.groups[row[2]], per100, src: 'ciqual' };
    ciqual.set(food.key, food);
    index.push({ food, n: norm(row[1]), first: norm(row[1].split(',')[0]) });
  }

  /* Portions usuelles déduites du nom (la table Ciqual n'en fournit pas). */
  const PORTION_RULES = [
    [/^(oeuf|œuf)/, [['œuf moyen', 50], ['2 œufs', 100]]],
    [/^pain|baguette|^biscotte/, [['tranche', 30], ['1/4 de baguette', 60]]],
    [/^biscotte/, [['biscotte', 8]]],
    [/yaourt|yogourt|fromage blanc|skyr/, [['pot', 125]]],
    [/petit suisse/, [['pot', 60]]],
    [/^pomme,|^pomme /, [['pomme moyenne', 150]]],
    [/^banane/, [['banane moyenne', 120]]],
    [/^orange|^pamplemousse/, [['fruit moyen', 150]]],
    [/^kiwi/, [['kiwi', 75]]],
    [/^poire/, [['poire moyenne', 160]]],
    [/^clementine|^mandarine/, [['fruit', 60]]],
    [/^abricot|^prune/, [['fruit', 40]]],
    [/^peche|^nectarine/, [['fruit moyen', 130]]],
    [/^fraise|^framboise|^myrtille|^cerise/, [['bol', 125]]],
    [/^tomate/, [['tomate moyenne', 120]]],
    [/^carotte/, [['carotte moyenne', 80]]],
    [/^avocat/, [['1/2 avocat', 80]]],
    [/^vin |^vin,|champagne/, [['verre (12,5 cl)', 125]]],
    [/^biere/, [['demi (25 cl)', 250], ['canette (33 cl)', 330]]],
    [/^lait|^jus|^boisson|^soda|^cola|^eau|nectar|limonade|sirop/, [['verre (20 cl)', 200], ['canette (33 cl)', 330]]],
    [/^cafe|^the |^the,|^infusion|^chocolat chaud/, [['tasse', 150]]],
    [/^beurre|margarine/, [['noisette', 10], ['c. à soupe', 15]]],
    [/^huile/, [['c. à café', 5], ['c. à soupe', 10]]],
    [/^sucre/, [['morceau', 5], ['c. à café', 5]]],
    [/^miel|^confiture|pate a tartiner|^sirop/, [['c. à café', 10], ['c. à soupe', 20]]],
    [/^fromage|camembert|comte|emmental|roquefort|brie|chevre|mozzarella|gruyere|raclette/, [['portion', 30]]],
    [/^riz|^pates|^semoule|^quinoa|^boulgour|^lentille|^pois chiche|^haricot/, [['assiette', 200], ['accompagnement', 150]]],
    [/^pomme de terre|^frites|puree/, [['portion', 200]]],
    [/steak|filet|escalope|cote|blanc de poulet|cuisse|roti|pave|saumon|cabillaud|thon/, [['portion', 120]]],
    [/^jambon/, [['tranche', 45]]],
    [/^saucisse|merguez/, [['saucisse', 60]]],
    [/pizza|quiche|tarte/, [['part', 120]]],
    [/^croissant|pain au chocolat|brioche|viennoiserie/, [['pièce', 60]]],
    [/^cereales|muesli|flocons/, [['bol', 40]]],
    [/^chocolat/, [['carré', 5], ['barre (4 carrés)', 20]]],
    [/^biscuit|cookie|gateau sec/, [['biscuit', 10]]],
    [/^gateau|^cake|^brownie|^muffin/, [['part', 80]]],
    [/^glace|sorbet|creme glacee/, [['boule', 50]]],
    [/^soupe|^veloute|^potage/, [['bol', 250]]],
    [/^salade|crudites/, [['assiette', 150]]],
    [/^noix|^amande|^noisette|^cacahuete|^pistache|^cajou/, [['poignée', 30]]],
    [/^compote/, [['pot', 100]]],
    [/sandwich|burger|kebab|wrap/, [['pièce', 200]]]
  ];

  function portionsFor(food) {
    if (food.portions && food.portions.length) return food.portions;
    const n = norm(food.name);
    const out = [];
    for (const [re, list] of PORTION_RULES) {
      if (re.test(n)) { for (const [l, g] of list) if (!out.some(o => o.l === l)) out.push({ l, g }); }
      if (out.length >= 3) break;
    }
    return out;
  }

  /* Recherche insensible aux accents dans la table Ciqual + aliments perso.
     boost(key) renvoie un bonus (récents, favoris). */
  function search(query, extra, boost) {
    const q = norm(query);
    if (!q) return [];
    // Pluriels simples : "pommes" -> "pomme", "noix" reste "noix".
    const toks = q.split(' ').map(t => (t.length > 3 && /[sx]$/.test(t) && !/(ix|oux|us)$/.test(t) ? t.slice(0, -1) : t));
    const res = [];
    let best = 0;
    const consider = (food, n, first) => {
      let score = 0, hit = 0;
      for (const t of toks) {
        const at = n.indexOf(t);
        if (at < 0) { score -= 40; continue; }
        hit++;
        if (at === 0) score += 60;
        else if (n[at - 1] === ' ') score += 25;
        else score += 5;
      }
      if (!hit || (toks.length > 1 && hit < Math.ceil(toks.length / 2))) return;
      best = Math.max(best, hit);
      if (first === q) score += 80;
      else if (first.startsWith(toks[0])) score += 30;
      if (/\bcru|nature|entier|moyen\b/.test(n)) score += 6;
      if (/prelevee a|martinique|guadeloupe|reunion|guyane|mayotte/.test(n)) score -= 25;
      score -= n.length * 0.35;
      score += boost ? boost(food.key) : 0;
      if (food.src !== 'ciqual') score += 20;
      res.push({ food, score, hit });
    };
    for (const f of extra) { const n = norm(f.name + ' ' + (f.brand || '')); consider(f, n, norm(f.name.split(',')[0])); }
    for (const it of index) consider(it.food, it.n, it.first);
    // Si des aliments contiennent tous les mots, on n'affiche qu'eux.
    const kept = res.filter(r => r.hit === best);
    kept.sort((a, b) => b.score - a.score);
    return kept.slice(0, 80).map(r => r.food);
  }

  /* Nutriments pour une quantité en grammes. */
  function forGrams(per100, grams) {
    const out = {};
    for (const k of NKEYS) {
      const v = per100[k];
      out[k] = v == null ? null : Math.round(v * grams) / 100;
    }
    return out;
  }

  function sumNutrients(list) {
    const out = {};
    for (const k of NKEYS) out[k] = 0;
    for (const n of list) for (const k of NKEYS) if (n && n[k] != null) out[k] += n[k];
    return out;
  }

  /* Objectif calorique : Mifflin-St Jeor x niveau d'activité, ajusté selon l'objectif. */
  function computeGoal(p) {
    const age = p.age || 30, w = p.weight || 70, h = p.height || 170;
    const bmr = 10 * w + 6.25 * h - 5 * age + (p.sex === 'f' ? -161 : 5);
    const tdee = bmr * (p.activity || 1.375);
    const delta = (p.pace || 0.5) * 7700 / 7;
    let goal = tdee;
    if (p.goal === 'lose') goal = tdee - delta;
    if (p.goal === 'gain') goal = tdee + delta;
    const floor = p.sex === 'f' ? 1200 : 1500;
    return { bmr: Math.round(bmr), tdee: Math.round(tdee), kcal: Math.round(Math.max(goal, Math.min(floor, tdee)) / 10) * 10 };
  }

  function macroGoals(kcal, split) {
    return {
      c: Math.round(kcal * split.c / 100 / 4),
      p: Math.round(kcal * split.p / 100 / 4),
      f: Math.round(kcal * split.f / 100 / 9)
    };
  }

  function bmi(weight, height) { return height ? weight / Math.pow(height / 100, 2) : 0; }

  function bmiLabel(v) {
    if (!v) return '';
    if (v < 18.5) return 'Insuffisance pondérale';
    if (v < 25) return 'Corpulence normale';
    if (v < 30) return 'Surpoids';
    return 'Obésité';
  }

  /* Activités : MET d'après le Compendium of Physical Activities (Ainsworth et al.). */
  const ACTIVITIES = [
    ['Marche tranquille', 3.0], ['Marche rapide', 4.3], ['Randonnée', 6.0], ['Course à pied (8 km/h)', 8.3],
    ['Course à pied (10 km/h)', 9.8], ['Course à pied (12 km/h)', 11.8], ['Vélo balade', 4.0], ['Vélo sportif', 8.0],
    ['Vélo d\'appartement', 6.8], ['Natation', 7.0], ['Musculation', 5.0], ['Musculation intense', 6.0],
    ['Boxe (sac, pattes d\'ours)', 7.8], ['Boxe (sparring)', 12.8], ['Arts martiaux / MMA', 10.3], ['Corde à sauter', 11.8],
    ['HIIT / CrossFit', 8.0], ['Fitness / aérobic', 7.3], ['Yoga', 2.5], ['Pilates', 3.0], ['Étirements', 2.3],
    ['Football', 7.0], ['Basket-ball', 6.5], ['Tennis', 7.3], ['Badminton', 5.5], ['Rugby', 8.3], ['Handball', 8.0],
    ['Danse', 5.0], ['Escalade', 8.0], ['Rameur', 7.0], ['Elliptique', 5.0], ['Ski', 7.0], ['Jardinage', 3.8],
    ['Ménage', 3.3], ['Bricolage', 3.5], ['Montée d\'escaliers', 8.8]
  ].map(([name, met]) => ({ name, met }));

  function activityKcal(met, minutes, weight) { return Math.round(met * (weight || 70) * minutes / 60); }
  function stepsKcal(steps, weight) { return Math.round(steps * 0.00057 * (weight || 70)); }

  /* Open Food Facts (en ligne, optionnel). Données ODbL. */
  const OFF_FIELDS = 'code,product_name,product_name_fr,brands,nutriments,serving_quantity,serving_size,quantity,image_small_url,nutriscore_grade';
  const IMG_HOST = 'https://images.openfoodfacts.org/images/products/';
  /* Dossier d'image d'Open Food Facts : code sur 13 chiffres découpé 3/3/3/reste. */
  function imgFolder(code) {
    if (code.length <= 8) return code;
    const c = code.padStart(13, '0');
    return c.slice(0, 3) + '/' + c.slice(3, 6) + '/' + c.slice(6, 9) + '/' + c.slice(9);
  }
  /* URL de la photo d'un produit (100, 200 ou 400 px). */
  function productImage(food, size) {
    if (!food || !food.img || !food.barcode) return null;
    const rel = food.img.includes('/') ? food.img : imgFolder(food.barcode) + '/front_' + food.img;
    const sz = '.' + (size || 200) + '.jpg';
    return { src: IMG_HOST + rel + sz };
  }
  function imgRefFromUrl(code, url) {
    if (!url || url.indexOf(IMG_HOST) !== 0 || !/\.(100|200|400)\.jpg$/.test(url)) return '';
    const rest = url.slice(IMG_HOST.length).replace(/\.(100|200|400)\.jpg$/, '');
    const i = rest.lastIndexOf('/'), folder = rest.slice(0, i), file = rest.slice(i + 1);
    return folder === imgFolder(code) && file.indexOf('front_') === 0 ? file.slice(6) : rest;
  }
  function fromOff(p, code) {
    const n = p.nutriments || {};
    const g = k => (n[k] == null || n[k] === '' ? null : Number(n[k]));
    let e = g('energy-kcal_100g');
    if (e == null && g('energy_100g') != null) e = Math.round(g('energy_100g') / 4.184);
    const per100 = { e, p: g('proteins_100g'), c: g('carbohydrates_100g'), f: g('fat_100g'), su: g('sugars_100g'),
      fi: g('fiber_100g'), sa: g('saturated-fat_100g'), sl: g('salt_100g'), ca: null, fe: null, mg: null, po: null,
      vc: null, vd: null, b12: null };
    const name = (p.product_name_fr || p.product_name || '').trim();
    if (!name || per100.e == null) return null;
    const portions = [];
    const sq = Number(p.serving_quantity);
    if (sq > 0) portions.push({ l: 'portion' + (p.serving_size ? ' (' + p.serving_size + ')' : ''), g: sq });
    const bc = String(code || p.code);
    const ns = String(p.nutriscore_grade || '').toLowerCase();
    return { key: 'o:' + bc, name, brand: (p.brands || '').split(',')[0].trim(), barcode: bc,
      per100, portions, src: 'off', img: imgRefFromUrl(bc, p.image_small_url), nutriscore: /^[a-e]$/.test(ns) ? ns : '' };
  }

  async function offByBarcode(code) {
    const r = await fetch('https://world.openfoodfacts.org/api/v2/product/' + encodeURIComponent(code) + '.json?fields=' + OFF_FIELDS);
    if (r.status === 404) return null;
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    return j.status === 1 && j.product ? fromOff(j.product, code) : null;
  }

  async function offSearch(q) {
    const url = 'https://world.openfoodfacts.org/cgi/search.pl?search_simple=1&json=1&page_size=25&lc=fr&cc=fr&fields=' +
      OFF_FIELDS + '&search_terms=' + encodeURIComponent(q);
    const r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    return (j.products || []).map(p => fromOff(p, p.code)).filter(Boolean);
  }

  window.Nutrition = { NKEYS, NUTRIENTS, RDA, ACTIVITIES, ciqual, norm, search, portionsFor, forGrams, sumNutrients,
    computeGoal, macroGoals, bmi, bmiLabel, activityKcal, stepsKcal, offByBarcode, offSearch, productImage, source: DB.source };
})();
