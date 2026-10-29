/* Calorys : application principale (journal, jeûne, recettes, analyse, profil).
   Le moteur métier (objectifs, moteur adaptatif, sèche, séances, gamification) vient de Nutravyn : js/engine.js. */
(function () {
  'use strict';
  const N = window.Nutrition, C = window.Charts, P = window.Platform, E = window.Engine, CAT = window.Catalog;
  const NV = window.NUTRAVYN || { cats: [], foods: [], recipes: [] };
  const APP_VERSION = '1.1.0';
  const $ = (s, r) => (r || document).querySelector(s);

  /* ---------- Icônes ---------- */
  const IC = {
    plus: 'M12 5v14M5 12h14', minus: 'M5 12h14', chevL: 'M15 18l-6-6 6-6', chevR: 'M9 6l6 6-6 6',
    close: 'M6 6l12 12M18 6L6 18', check: 'M5 12l5 5 9-10',
    search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM16.5 16.5L21 21',
    star: 'M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z',
    trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
    barcode: 'M4 5v14M7 5v14M10 5v10M13 5v14M16 5v10M20 5v14M10 18v1M16 18v1',
    flame: 'M12 3c3 4 6 6 6 11a6 6 0 0 1-12 0c0-3 2-5 3-7 1 2 2 3 3 3 0-3-1-5 0-7z',
    drop: 'M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11z',
    scale: 'M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8 10a4 4 0 0 1 8 0M12 10l1.5-2',
    edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
    breakfast: 'M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM16 10h2a2 2 0 0 1 0 4h-2M8 3v3M12 3v3',
    lunch: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2',
    dinner: 'M20 14A8 8 0 1 1 10 4a6 6 0 0 0 10 10z',
    snack: 'M12 7c-2-2-7-2-7 4 0 5 3 9 5 9 1 0 1.5-.5 2-.5s1 .5 2 .5c2 0 5-4 5-9 0-6-5-6-7-4zM12 7c0-2 1-4 3-4',
    run: 'M14 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM6 21l4-7 3 3v4M6 12l3-4 4 1 2 3h3M10 14l-1-4',
    clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
    copy: 'M9 9h11v11H9zM5 15V4h11', camera: 'M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z',
    bolt: 'M13 2L4 14h7l-1 8 9-12h-7z', recipe: 'M6 3h12v18H6zM9 7h6M9 11h6M9 15h4',
    download: 'M12 4v11M7 10l5 5 5-5M5 20h14', upload: 'M12 16V5M7 10l5-5 5 5M5 20h14',
    share: 'M18 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM6 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM8.6 13.5l6.8 4M15.4 6.5l-6.8 4',
    globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18',
    sliders: 'M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M15 4v4M9 10v4M17 16v4',
    info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5v.5', folder: 'M3 6h6l2 2h10v11H3z',
    food: 'M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10M17 3c-2 2-3 5-3 8h3v10',
    belt: 'M3 10h18v4H3zM10 10l-3 9M14 10l3 9M10 10h4v4h-4z', trophy: 'M8 4h8v5a4 4 0 0 1-8 0zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8 21h8M9 17h6',
    report: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7M9 8h2', bell: 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0',
    sparkle: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z',
    cart: 'M3 4h2l2.4 11h10.2L20 8H6.2M9 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM17 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2z',
    target: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2z',
    box: 'M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10', key: 'M15 4a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM11.5 12.5L3 21M6 18l2 2M8 16l2 2',
    timer: 'M12 5a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 9v4l2 2M10 2h4'
  };
  const icon = (n, cls) => `<svg class="ic ${cls || ''}" viewBox="0 0 24 24" aria-hidden="true"><path d="${IC[n]}"/></svg>`;

  const MEALS = [
    { id: 'breakfast', label: 'Petit-déjeuner', share: 0.25 },
    { id: 'lunch', label: 'Déjeuner', share: 0.35 },
    { id: 'dinner', label: 'Dîner', share: 0.3 },
    { id: 'snack', label: 'Collations', share: 0.1 }
  ];
  const mealLabel = id => (MEALS.find(m => m.id === id) || MEALS[3]).label;

  const ACTIVITY_LEVELS = [
    [1.2, 'Sédentaire', 'Travail assis, peu ou pas de sport'],
    [1.375, 'Peu actif', 'Sport léger 1 à 3 fois par semaine'],
    [1.55, 'Actif', 'Sport modéré 3 à 5 fois par semaine'],
    [1.725, 'Très actif', 'Sport intense 6 à 7 fois par semaine'],
    [1.9, 'Extrêmement actif', 'Travail physique et entraînement quotidien']
  ];
  const FAST_PLANS = ['12:12', '14:10', '16:8', '18:6', '20:4', '23:1'];
  const FAST_STAGES = [
    [0, 'Digestion', 'Le corps utilise l\'énergie du dernier repas.'],
    [4, 'Baisse de la glycémie', 'Le taux de sucre sanguin redescend et se stabilise.'],
    [12, 'Mobilisation des graisses', 'Les réserves de glycogène diminuent, les graisses prennent le relais.'],
    [16, 'Cétose légère', 'Production de corps cétoniques, en général à partir de 16 h.'],
    [24, 'Jeûne prolongé', 'Au-delà de 24 h, demande l\'avis d\'un professionnel de santé.']
  ];

  /* ---------- Outils ---------- */
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = v => { const n = parseFloat(String(v == null ? '' : v).replace(',', '.').replace(/\s/g, '')); return isFinite(n) ? n : null; };
  const r0 = v => Math.round(v || 0);
  const fr = (v, d) => (v == null ? '–' : Number(v).toLocaleString('fr-FR', { maximumFractionDigits: d == null ? 1 : d, minimumFractionDigits: 0 }));
  const kcal = v => r0(v).toLocaleString('fr-FR');
  const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const pad2 = n => String(n).padStart(2, '0');
  const dkey = d => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  const pkey = k => { const [y, m, d] = k.split('-').map(Number); return new Date(y, m - 1, d); };
  const addDays = (k, n) => { const d = pkey(k); d.setDate(d.getDate() + n); return dkey(d); };
  const today = () => dkey(new Date());
  function dayLabel(k) {
    const t = today();
    if (k === t) return 'Aujourd\'hui';
    if (k === addDays(t, -1)) return 'Hier';
    if (k === addDays(t, 1)) return 'Demain';
    const s = pkey(k).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  function defaultMeal() {
    const h = new Date().getHours();
    return h < 10 ? 'breakfast' : h < 15 ? 'lunch' : h < 18 ? 'snack' : 'dinner';
  }
  function dur(ms) {
    const m = Math.max(0, Math.floor(ms / 60000));
    return Math.floor(m / 60) + ' h ' + pad2(m % 60);
  }

  /* ---------- État ---------- */
  function defaults() {
    return {
      v: 1,
      profile: { onboarded: false, name: '', sex: 'm', age: 30, height: 175, weight: 75, targetWeight: 70, activity: 1.375,
        goal: 'lose', pace: 0.5, weighIn: '', preset: 'balanced', split: { c: 50, p: 20, f: 30 }, kcalOverride: null,
        adaptive: true, exercisePct: 50, waterAuto: true, waterGoal: 2000, glass: 250, stepsGoal: 8000 },
      days: {}, weights: [], foods: [], recipes: [], off: {}, favs: [], recents: [],
      fasting: { plan: '16:8', active: null, history: [] },
      shopping: [], favRecipes: [],
      settings: { theme: 'auto', game: true, geminiKey: '', seenBelt: 'white', seenBadges: [],
        reminders: { on: false, meals: true, breakfast: '08:00', lunch: '12:30', dinner: '19:30', water: true, weigh: false, weighAt: '07:30', fastEnd: true } }
    };
  }
  function migrate(s) {
    const d = defaults();
    if (!s || typeof s !== 'object') return d;
    const out = Object.assign(d, s);
    out.profile = Object.assign(defaults().profile, s.profile || {});
    out.profile.split = Object.assign({ c: 50, p: 20, f: 30 }, (s.profile || {}).split || {});
    out.fasting = Object.assign(defaults().fasting, s.fasting || {});
    out.settings = Object.assign(defaults().settings, s.settings || {});
    out.settings.reminders = Object.assign(defaults().settings.reminders, (s.settings || {}).reminders || {});
    // v1.0 -> v1.1 : "ajouter les calories des activités" (tout ou rien) devient un pourcentage (50 % conseillé).
    const sp = (s.profile || {});
    if (sp.exercisePct == null && sp.addExercise === false) out.profile.exercisePct = 0;
    if (sp.waterAuto == null && sp.waterGoal && sp.waterGoal !== 2000) out.profile.waterAuto = false;
    if (sp.preset == null && sp.split && (sp.split.c !== 50 || sp.split.p !== 20 || sp.split.f !== 30)) out.profile.preset = 'custom';
    delete out.profile.addExercise;
    return out;
  }

  let S = defaults();
  const ui = { tab: 'journal', date: today(), statsRange: 7, ob: null, obStep: 0 };
  let saveTimer = null;
  function save() { goalsMemo = null; gameMemo = null; clearTimeout(saveTimer); saveTimer = setTimeout(() => P.save(S), 250); }

  function emptyDay() { return { meals: { breakfast: [], lunch: [], dinner: [], snack: [] }, water: 0, acts: [], steps: 0 }; }
  function dayGet(k) { return S.days[k] || emptyDay(); }
  function dayMut(k) {
    if (!S.days[k]) S.days[k] = emptyDay();
    const d = S.days[k];
    for (const m of MEALS) if (!d.meals[m.id]) d.meals[m.id] = [];
    return d;
  }

  function currentWeight() {
    if (!S.weights.length) return S.profile.weight;
    return S.weights[S.weights.length - 1].kg;
  }
  /* Répartition des macros : preset Nutravyn ou répartition personnalisée. */
  function splitOf(p) {
    if (p.preset && p.preset !== 'custom' && E.PRESETS[p.preset]) return E.PRESETS[p.preset];
    return { p: p.split.p / 100, c: p.split.c / 100, f: p.split.f / 100 };
  }
  function intakeWindow(days) {
    const intake = {}, t = today();
    for (let i = 1; i <= days; i++) {
      const k = addDays(t, -i), tt = dayTotals(k);
      if (tt.count) intake[k] = tt.eaten;
    }
    return intake;
  }
  /* Objectif du jour : formule (Mifflin-St Jeor) ou dépense réelle mesurée (moteur adaptatif),
     puis cible selon l'objectif, bornée seulement en mode sèche. Mémorisé pendant un rendu. */
  let goalsMemo = null;
  function goals() {
    if (goalsMemo) return goalsMemo;
    const p = S.profile, w = currentWeight();
    const b = E.bmr(p.sex, w, p.height, p.age), theo = E.tdee(p.sex, w, p.height, p.age, p.activity);
    const since = addDays(today(), -28);
    const ad = E.adaptive(p, intakeWindow(28), S.weights.filter(x => x.date >= since), w, theo, b);
    const expenditure = p.adaptive && ad.reliable ? ad.measured : theo;
    const cut = p.goal === 'cut' && p.weighIn ? E.cutPlan(p, w, expenditure, b) : null;
    const rate = p.goal === 'maintain' ? 0 : p.pace;
    const calc = cut ? cut.target : E.dailyTarget(expenditure, p.goal, rate, p.sex, b);
    const k = p.kcalOverride || calc;
    const m = E.macros(k, splitOf(p), w, p.goal === 'cut' ? 1.8 : 0);
    const trainMin = (dayGet(ui.date).acts || []).filter(a => a.session).reduce((a, x) => a + (x.min || 0), 0);
    const water = p.waterAuto ? E.waterGoalMl(w, trainMin) : p.waterGoal;
    const info = E.describe(k, expenditure, b, cut ? Math.min(cut.required, cut.safe) : rate, w);
    goalsMemo = { kcal: k, calc, bmr: Math.round(b), tdee: Math.round(theo), expenditure: Math.round(expenditure),
      p: m.p, c: m.c, f: m.f, water, adaptive: ad, cut, info: p.kcalOverride ? Object.assign({}, info, { note: null }) : info };
    return goalsMemo;
  }

  function dayTotals(k) {
    const d = dayGet(k);
    const all = [];
    for (const m of MEALS) for (const e of d.meals[m.id] || []) all.push(e.n);
    const n = N.sumNutrients(all);
    const w = currentWeight();
    const actK = (d.acts || []).reduce((a, x) => a + x.kcal, 0) + (d.steps ? N.stepsKcal(d.steps, w) : 0);
    return { n, eaten: n.e, burned: actK, count: all.length, water: d.water || 0 };
  }
  /* Calories d'activité rendues à l'objectif : 50 % par défaut (les estimations de dépense sont généreuses). */
  const credited = t => Math.round(t.burned * (S.profile.exercisePct || 0) / 100);

  /* ---------- Aliments ---------- */
  /* Aliments courants de Nutravyn (noms usuels, valeurs pour 100 g) et ses 72 recettes. */
  const BASE = new Map();
  for (const [id, name, cat, e, pr, c, f] of NV.foods) {
    const per100 = {}; for (const k of N.NKEYS) per100[k] = null;
    Object.assign(per100, { e, p: pr, c, f });
    BASE.set('n:' + id, { key: 'n:' + id, name, group: NV.cats[cat], per100, src: 'base' });
  }
  const BASE_LIST = Array.from(BASE.values());
  function nvRecipeFood(r) {
    const tg = r.items.reduce((a, [, g]) => a + g, 0) || 1;
    const tot = N.sumNutrients(r.items.map(([id, g]) => { const f = BASE.get('n:' + id); return f ? N.forGrams(f.per100, g) : null; }));
    const per100 = {}; for (const k of N.NKEYS) per100[k] = tot[k] ? Math.round(tot[k] * 100 / tg * 100) / 100 : (k === 'e' || k === 'p' || k === 'c' || k === 'f' ? 0 : null);
    return { key: 'nr:' + r.id, name: r.name, brand: 'Recette Calorys', per100, src: 'nvrecipe', nv: r,
      portions: [{ l: 'portion (1/' + r.servings + ')', g: Math.round(tg / r.servings) }] };
  }
  const NV_RECIPES = new Map(NV.recipes.map(r => [r.id, r]));
  const NV_RECIPE_FOODS = NV.recipes.map(nvRecipeFood);
  const tempFoods = new Map(); // résultats catalogue / en ligne affichés, avant mise en cache
  function recipeFood(r) {
    const tg = r.items.reduce((a, i) => a + i.g, 0) || 1;
    const tot = N.sumNutrients(r.items.map(i => N.forGrams(i.per100, i.g)));
    const per100 = {};
    for (const k of N.NKEYS) per100[k] = Math.round(tot[k] * 100 / tg * 100) / 100;
    return { key: 'r:' + r.id, name: r.name, brand: 'Recette', per100, src: 'recipe',
      portions: [{ l: 'portion (1/' + r.servings + ')', g: Math.round(tg / r.servings) }], recipe: r };
  }
  function foodByKey(key) {
    if (!key) return null;
    const t = key.slice(0, 2), id = key.slice(2);
    if (t === 'c:') return N.ciqual.get(key) || null;
    if (t === 'u:') { const f = S.foods.find(x => x.id === id); return f ? Object.assign({ key, src: 'custom' }, f) : null; }
    if (t === 'o:') return S.off[id] || tempFoods.get(key) || null;
    if (t === 'r:') { const r = S.recipes.find(x => x.id === id); return r ? recipeFood(r) : null; }
    if (t === 'n:') return BASE.get(key) || null;
    if (key.startsWith('nr:')) { const r = NV_RECIPES.get(+key.slice(3)); return r ? nvRecipeFood(r) : null; }
    return tempFoods.get(key) || null;
  }
  function extraFoods() {
    return S.foods.map(f => Object.assign({ key: 'u:' + f.id, src: 'custom' }, f))
      .concat(Object.values(S.off))
      .concat(S.recipes.map(recipeFood))
      .concat(BASE_LIST)
      .concat(NV_RECIPE_FOODS);
  }
  function foodSub(f) {
    const parts = [];
    if (f.brand) parts.push(f.brand);
    else if (f.src === 'ciqual') parts.push(f.group);
    else if (f.src === 'custom') parts.push('Mon aliment');
    else if (f.src === 'base') parts.push('Aliment courant');
    if (f.per100 && f.per100.e != null) parts.push(kcal(f.per100.e) + ' kcal / 100 g');
    return parts.join(' · ');
  }
  function lastGrams(key) {
    const r = S.recents.find(x => x.key === key);
    if (r) return r.g;
    const f = foodByKey(key);
    const p = f ? N.portionsFor(f) : [];
    return p.length ? p[0].g : 100;
  }
  function pushRecent(key, g) {
    S.recents = [{ key, g, t: Date.now() }].concat(S.recents.filter(x => x.key !== key)).slice(0, 60);
  }
  function boost(key) {
    let b = 0;
    if (S.favs.includes(key)) b += 90;
    const i = S.recents.findIndex(x => x.key === key);
    if (i >= 0) b += 70 - i;
    return b;
  }
  function makeEntry(food, grams, extra) {
    return Object.assign({ id: uid(), key: food.key, name: food.name, brand: food.brand || '', g: grams,
      n: N.forGrams(food.per100, grams) }, extra || {});
  }
  function logFood(food, grams, meal, day) {
    const d = dayMut(day || ui.date);
    d.meals[meal].push(makeEntry(food, grams));
    pushRecent(food.key, grams);
    save();
    P.vibrate(12);
  }

  /* ---------- Gamification (Nutravyn) : recalculée depuis l'historique ---------- */
  let gameMemo = null;
  function game() {
    if (gameMemo) return gameMemo;
    const keys = Object.keys(S.days).sort();
    const fasts = {};
    for (const f of S.fasting.history) if (f.end - f.start >= f.goalH * 3600000) { const k = dkey(new Date(f.end)); fasts[k] = (fasts[k] || 0) + 1; }
    const weighed = new Set(S.weights.map(w => w.date));
    const all = new Set(keys.concat(Object.keys(fasts), Array.from(weighed)));
    const g = goals();
    const days = Array.from(all).sort().map(k => {
      const d = dayGet(k), t = dayTotals(k);
      const meals = MEALS.filter(m => (d.meals[m.id] || []).length).length;
      const photos = MEALS.reduce((a, m) => a + (d.meals[m.id] || []).filter(e => e.ai).length, 0);
      return { date: k, meals, kcal: t.eaten, protein: t.n.p, water: t.water, trainings: (d.acts || []).length,
        weighed: weighed.has(k), fastsDone: fasts[k] || 0, photos };
    });
    const trend = E.smooth(S.weights);
    const loss = trend.length ? Math.max(0, trend[0].kg - Math.min(...trend.map(x => x.kg))) : 0;
    const p = S.profile;
    const cutDone = p.goal === 'cut' && p.weighIn && p.weighIn <= today() && S.weights.some(w => w.date === p.weighIn && w.kg <= p.targetWeight);
    gameMemo = E.game(days, () => ({ kcal: g.kcal, p: g.p, water: g.water }), S.weights.length, loss, cutDone);
    return gameMemo;
  }
  /* Félicitations quand une ceinture ou un badge vient d'être gagné. */
  function celebrate() {
    if (!S.settings.game || !S.profile.onboarded) return;
    const gm = game(), st = S.settings;
    const newBadges = Array.from(gm.badges).filter(b => !st.seenBadges.includes(b));
    const beltIdx = E.BELTS.findIndex(b => b.id === gm.belt.id), seenIdx = E.BELTS.findIndex(b => b.id === st.seenBelt);
    if (beltIdx > seenIdx) {
      st.seenBelt = gm.belt.id; save();
      setTimeout(() => toast('Nouvelle ceinture : ' + gm.belt.label + ' !', { label: 'Voir', fn: openProgress }), 400);
    } else if (beltIdx < seenIdx) { st.seenBelt = gm.belt.id; save(); }
    if (newBadges.length) {
      st.seenBadges = st.seenBadges.concat(newBadges); save();
      const b = E.BADGES.find(x => x.code === newBadges[0]);
      if (beltIdx <= seenIdx && b) setTimeout(() => toast('Badge débloqué : ' + b.label, { label: 'Voir', fn: openProgress }), 400);
    }
  }

  /* ---------- Feuilles (fenêtres modales) ---------- */
  const sheets = [];
  function openSheet(render, opts) {
    opts = opts || {};
    const wrap = document.createElement('div');
    wrap.className = 'sheet-wrap' + (opts.full ? ' full' : '');
    wrap.innerHTML = '<div class="backdrop"></div><section class="sheet" role="dialog" aria-modal="true"></section>';
    const sheet = { wrap, el: wrap.querySelector('.sheet'), render, opts, data: opts.data || {} };
    sheet.refresh = () => { sheet.el.innerHTML = sheet.render(sheet); if (opts.mount) opts.mount(sheet); };
    wrap.querySelector('.backdrop').addEventListener('click', () => closeSheet(sheet));
    $('#sheets').appendChild(wrap);
    sheets.push(sheet);
    sheet.refresh();
    requestAnimationFrame(() => wrap.classList.add('open'));
    const f = sheet.el.querySelector('[autofocus]');
    if (f && !matchMedia('(pointer: coarse)').matches) setTimeout(() => f.focus(), 60);
    return sheet;
  }
  function closeSheet(sheet) {
    sheet = sheet || sheets[sheets.length - 1];
    if (!sheet) return;
    const i = sheets.indexOf(sheet);
    if (i >= 0) sheets.splice(i, 1);
    if (sheet.opts.onClose) sheet.opts.onClose(sheet);
    sheet.wrap.classList.remove('open');
    setTimeout(() => sheet.wrap.remove(), 220);
  }
  function topSheet() { return sheets[sheets.length - 1]; }
  const sheetHead = (title, sub) => `<header class="sheet-head"><div><h2>${title}</h2>${sub ? `<p class="muted">${sub}</p>` : ''}</div>
    <button class="icon-btn" data-act="close" aria-label="Fermer">${icon('close')}</button></header>`;

  function confirmBox(msg, ok, danger) {
    return new Promise(res => {
      let done = false;
      const s = openSheet(() => `<div class="confirm"><p>${msg}</p><div class="row gap">
        <button class="btn ghost grow" data-act="cfNo">Annuler</button>
        <button class="btn grow ${danger ? 'danger' : ''}" data-act="cfYes">${ok || 'Confirmer'}</button></div></div>`,
      { onClose: () => { if (!done) res(false); } });
      s.data.resolve = v => { done = true; res(v); closeSheet(s); };
    });
  }

  let toastTimer = null;
  function toast(msg, action) {
    const t = $('#toast');
    t.innerHTML = `<span>${esc(msg)}</span>` + (action ? `<button data-act="toastAction">${esc(action.label)}</button>` : '');
    t._action = action ? action.fn : null;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), action ? 5000 : 2600);
  }

  /* ---------- Rendu principal ---------- */
  function render() {
    goalsMemo = null; gameMemo = null;
    const view = $('#view');
    document.body.classList.toggle('onboarding', !S.profile.onboarded);
    if (!S.profile.onboarded) { view.innerHTML = renderOnboarding(); return; }
    document.querySelectorAll('#tabbar [data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === ui.tab));
    const fn = { journal: renderJournal, fasting: renderFasting, recipes: renderRecipes, stats: renderStats, profile: renderProfile }[ui.tab];
    view.innerHTML = fn();
    celebrate();
    for (const s of sheets) if (s.opts.live) s.refresh();
  }

  /* ---------- Journal ---------- */
  function renderJournal() {
    const g = goals(), t = dayTotals(ui.date), d = dayGet(ui.date);
    const burned = credited(t);
    const left = g.kcal - t.eaten + burned;
    const pct = t.eaten / (g.kcal + burned || 1);
    const macro = (k, label, cls) => {
      const v = t.n[k], goal = g[k];
      return `<div class="macro ${cls}"><div class="macro-top"><span>${label}</span><span><b>${r0(v)}</b> / ${goal} g</span></div>
        <div class="bar"><i style="width:${Math.min(100, v / goal * 100)}%"></i></div></div>`;
    };
    let h = `<div class="topbar"><button class="icon-btn" data-act="day" data-n="-1" aria-label="Jour précédent">${icon('chevL')}</button>
      <label class="day-label"><span>${dayLabel(ui.date)}</span><input type="date" value="${ui.date}" data-act="pickDay" aria-label="Choisir une date"></label>
      <button class="icon-btn" data-act="day" data-n="1" aria-label="Jour suivant">${icon('chevR')}</button>
      <button class="icon-btn" data-act="report" aria-label="Rapport du jour" title="Rapport du jour">${icon('report')}</button></div>`;
    if (S.settings.game) {
      const gm = game();
      h += `<button class="belt-bar" data-act="progress" style="--belt:${gm.belt.color}">
        <span class="belt-chip">${icon('belt')}</span>
        <span class="grow"><b>Ceinture ${gm.belt.label.toLowerCase()}</b><span class="muted">${gm.next ? kcal(gm.toNext) + ' XP avant la ' + gm.next.label.toLowerCase() : 'Grade maximum atteint'}</span>
        <i class="belt-prog"><i style="width:${Math.round(gm.progress * 100)}%"></i></i></span>
        <span class="streak">${icon('flame')}<b>${gm.streak}</b></span></button>`;
    }
    if (g.cut) h += cutCard(g);
    h += `<section class="card summary">
      <div class="sum-side"><b>${kcal(t.eaten)}</b><span>mangées</span></div>
      <div class="sum-ring ${left < 0 ? 'over' : ''}">${C.ring(pct, 168, 14)}<div class="ring-center"><b>${kcal(Math.abs(left))}</b><span>${left < 0 ? 'en trop' : 'restantes'}</span></div></div>
      <div class="sum-side"><b>${kcal(t.burned)}</b><span>brûlées${t.burned && S.profile.exercisePct < 100 ? ` (${S.profile.exercisePct} % rendues)` : ''}</span></div>
      <div class="macros">${macro('c', 'Glucides', 'carb')}${macro('p', 'Protéines', 'prot')}${macro('f', 'Lipides', 'fat')}</div>
      ${g.info.note ? `<p class="target-note">${icon('info')}<span>${esc(g.info.note)}</span></p>` : ''}
    </section>`;
    for (const m of MEALS) {
      const list = d.meals[m.id] || [];
      const mk = list.reduce((a, e) => a + (e.n.e || 0), 0);
      const yest = (dayGet(addDays(ui.date, -1)).meals[m.id] || []).length;
      h += `<section class="card meal"><header class="meal-head">
        <span class="meal-ic ${m.id}">${icon(m.id)}</span>
        <div class="grow"><h3>${m.label}</h3><p class="muted">${kcal(mk)} / ${kcal(g.kcal * m.share)} kcal</p></div>
        ${!list.length && yest ? `<button class="chip" data-act="copyMeal" data-meal="${m.id}" title="Reprendre le repas de la veille">${icon('copy')}Comme hier</button>` : ''}
        <button class="add-btn" data-act="addFood" data-meal="${m.id}" aria-label="Ajouter au ${m.label}">${icon('plus')}</button></header>`;
      if (list.length) {
        h += '<ul class="entries">' + list.map(e => `<li data-act="editEntry" data-meal="${m.id}" data-id="${e.id}">
          <div class="grow"><b>${esc(e.name)}</b><span class="muted">${entryQty(e)}${e.brand ? ' · ' + esc(e.brand) : ''}</span></div>
          <span class="kc">${kcal(e.n.e)}</span></li>`).join('') + '</ul>';
      }
      h += '</section>';
    }
    const glass = S.profile.glass, wg = g.water;
    const nG = Math.max(1, Math.ceil(wg / glass)), filled = Math.floor(t.water / glass);
    let cups = '';
    for (let i = 0; i < Math.max(nG, filled + 1); i++) cups += `<button class="cup ${i < filled ? 'full' : ''}" data-act="cup" data-i="${i}" aria-label="Verre ${i + 1}">${icon('drop')}</button>`;
    h += `<section class="card water"><header class="meal-head"><span class="meal-ic water">${icon('drop')}</span>
      <div class="grow"><h3>Eau</h3><p class="muted">${fr(t.water / 1000, 2)} / ${fr(wg / 1000, 2)} L${S.profile.waterAuto ? ' · objectif auto' : ''}</p></div>
      <button class="icon-btn" data-act="water" data-n="-1" aria-label="Retirer un verre">${icon('minus')}</button>
      <button class="add-btn" data-act="water" data-n="1" aria-label="Ajouter un verre">${icon('plus')}</button></header>
      <div class="cups">${cups}</div></section>`;
    const w = currentWeight();
    h += `<section class="card"><header class="meal-head"><span class="meal-ic act">${icon('run')}</span>
      <div class="grow"><h3>Séances et activités</h3><p class="muted">${kcal(t.burned)} kcal brûlées · ${kcal(burned)} rendues à l'objectif</p></div>
      <button class="add-btn" data-act="addActivity" aria-label="Ajouter une activité">${icon('plus')}</button></header>
      <ul class="entries">${(d.acts || []).map(a => `<li data-act="editActivity" data-id="${a.id}"><div class="grow"><b>${esc(a.name)}</b><span class="muted">${a.min ? a.min + ' min' : 'saisie manuelle'}${a.rpe ? ' · RPE ' + a.rpe + '/10' : ''}${a.sweat ? ' · ≈ ' + fr(a.sweat / 1000, 1) + ' L de sueur' : ''}</span></div><span class="kc">${kcal(a.kcal)}</span></li>`).join('')}
      <li class="steps"><div class="grow"><b>Pas</b><span class="muted">objectif ${S.profile.stepsGoal.toLocaleString('fr-FR')}${d.steps ? ' · ' + kcal(N.stepsKcal(d.steps, w)) + ' kcal' : ''}</span></div>
      <input class="steps-input" inputmode="numeric" data-act="steps" value="${d.steps || ''}" placeholder="0" aria-label="Nombre de pas"></li></ul></section>`;
    const lastW = S.weights.length ? S.weights[S.weights.length - 1] : null;
    h += `<section class="card"><header class="meal-head"><span class="meal-ic weight">${icon('scale')}</span>
      <div class="grow"><h3>Poids</h3><p class="muted">${lastW ? fr(lastW.kg) + ' kg le ' + pkey(lastW.date).toLocaleDateString('fr-FR') : 'Aucune pesée'}${S.weights.length > 2 ? ' · tendance ' + fr(E.smooth(S.weights).pop().kg) + ' kg' : ''} · objectif ${fr(S.profile.targetWeight)} kg</p></div>
      <button class="add-btn" data-act="addWeight" aria-label="Ajouter une pesée">${icon('plus')}</button></header></section>`;
    h += `<p class="foot muted">Nutriments : ${esc(N.source)}</p>`;
    return h;
  }
  function cutCard(g) {
    const c = g.cut, p = S.profile;
    const cls = { ontrack: 'ok', tight: 'warn', unrealistic: 'bad', done: 'ok' }[c.status];
    return `<button class="card cut-card ${cls}" data-act="cutInfo"><div class="cut-days"><b>J-${c.days}</b><span>pesée</span></div>
      <div class="grow"><b>${c.toLose > 0 ? fr(c.toLose) + ' kg à perdre pour ' + fr(p.targetWeight) + ' kg' : 'Dans la catégorie'}</b>
      <span class="muted">${esc(c.message)}</span></div>${icon('chevR', 'chev')}</button>`;
  }
  function entryQty(e) {
    if (e.key === 'q') return 'ajout rapide';
    if (e.pl) return fr(e.pc) + ' × ' + esc(e.pl) + ' (' + fr(e.g, 0) + ' g)';
    return fr(e.g, 0) + ' g';
  }

  /* ---------- Ajout d'aliments ---------- */
  function openAddFood(meal, opts) {
    opts = opts || {};
    const mode = opts.pick ? 'pick' : 'log';
    return openSheet(s => {
      const q = s.data.q || '';
      let h = `<header class="sheet-head search-head">
        <div class="grow">${mode === 'log' ? `<select class="meal-select" data-act="setMeal" aria-label="Repas">${MEALS.map(m => `<option value="${m.id}" ${m.id === s.data.meal ? 'selected' : ''}>${m.label}</option>`).join('')}</select>` : '<h2>Ajouter un ingrédient</h2>'}</div>
        <button class="icon-btn" data-act="close" aria-label="Fermer">${icon('close')}</button></header>
        <div class="search">${icon('search')}<input type="search" id="foodQ" placeholder="Rechercher un aliment…" value="${esc(q)}" autofocus autocomplete="off" aria-label="Rechercher un aliment"></div>
        <div class="quick-actions">
          <button class="qa" data-act="scan">${icon('barcode')}<span>Scanner</span></button>
          ${mode === 'log' ? `<button class="qa" data-act="photoAi">${icon('sparkle')}<span>Photo IA</span></button>` : ''}
          ${mode === 'log' ? `<button class="qa" data-act="quickAdd">${icon('bolt')}<span>Ajout rapide</span></button>` : ''}
          <button class="qa" data-act="newFood">${icon('edit')}<span>Créer un aliment</span></button>
          ${mode === 'log' ? `<button class="qa" data-act="newRecipe">${icon('recipe')}<span>Recette</span></button>` : ''}
        </div><div class="results" id="results"></div>`;
      return h;
    }, {
      full: true,
      data: { meal: meal || defaultMeal(), q: '', tab: 'recent', mode, pick: opts.pick },
      mount: s => {
        const inp = $('#foodQ', s.el);
        inp.addEventListener('input', () => { s.data.q = inp.value; s.data.offRes = null; renderResults(s); });
        inp.addEventListener('keydown', e => {
          if (e.key === 'Enter') { const first = $('.results [data-act="openFood"]', s.el); if (first) first.click(); }
        });
        renderResults(s);
      }
    });
  }
  function resultRow(f, s) {
    const plus = s.data.mode === 'log' ? `<button class="add-btn sm" data-act="quickLog" data-key="${esc(f.key)}" aria-label="Ajouter directement">${icon('plus')}</button>` : '';
    const ns = f.nutriscore ? `<i class="ns ns-${f.nutriscore}" title="Nutri-Score ${f.nutriscore.toUpperCase()}">${f.nutriscore.toUpperCase()}</i>` : '';
    return `<li><button class="res" data-act="openFood" data-key="${esc(f.key)}"><b>${esc(f.name)}</b><span class="muted">${ns}${esc(foodSub(f))}</span></button>${plus}</li>`;
  }
  /* Bloc "produits de marque" : catalogue hors ligne s'il est installé, sinon invitation à l'installer. */
  function catalogBlock(s, q) {
    const st = CAT.status();
    if (st.state === 'ready') {
      if (s.data.catQ !== q) {
        s.data.catQ = q; s.data.catRes = null;
        CAT.search(q, 30).then(list => {
          if (s.data.catQ !== q) return;
          list.forEach(f => tempFoods.set(f.key, f));
          s.data.catRes = list; renderResults(s);
        }).catch(() => { s.data.catRes = []; renderResults(s); });
      }
      if (!s.data.catRes) return `<h4 class="sec">Produits de marque</h4><p class="empty">Recherche dans ${st.count.toLocaleString('fr-FR')} produits…</p>`;
      return `<h4 class="sec">Produits de marque (${st.count.toLocaleString('fr-FR')} hors ligne)</h4>` +
        (s.data.catRes.length ? `<ul class="res-list">${s.data.catRes.map(f => resultRow(f, s)).join('')}</ul>` : '<p class="empty">Aucun produit de marque trouvé.</p>');
    }
    if (st.state === 'downloading') return `<p class="cat-hint">${icon('box')}<span>Installation du catalogue : ${Math.round(st.progress * 100)} %</span></p>`;
    if (!st.available) return '';
    return `<button class="cat-hint" data-act="catalog">${icon('box')}<span><b>Installer le catalogue de ${st.count.toLocaleString('fr-FR')} produits de marque</b><br>Recherche et scan sans connexion (${st.sizeMb} Mo à télécharger une fois)</span></button>`;
  }
  function renderResults(s) {
    const box = $('#results', s.el);
    if (!box) return;
    const q = (s.data.q || '').trim();
    let h = '';
    if (q) {
      const list = N.search(q, extraFoods(), boost).slice(0, 40);
      h += list.length ? `<ul class="res-list">${list.map(f => resultRow(f, s)).join('')}</ul>` : `<p class="empty">Aucun aliment générique trouvé.</p>`;
      h += catalogBlock(s, q);
      if (s.data.offRes) {
        h += `<h4 class="sec">Open Food Facts</h4>` + (s.data.offRes.length ? `<ul class="res-list">${s.data.offRes.map(f => resultRow(f, s)).join('')}</ul>` : '<p class="empty">Aucun produit trouvé en ligne.</p>');
      } else {
        h += `<button class="btn ghost wide" data-act="offSearch" ${s.data.offLoading ? 'disabled' : ''}>${icon('globe')}${s.data.offLoading ? 'Recherche en ligne…' : CAT.status().state === 'ready' ? 'Produit introuvable ? Chercher en ligne (Open Food Facts)' : 'Chercher les produits de marque (Open Food Facts, en ligne)'}</button>`;
      }
    } else {
      const tabs = [['recent', 'Récents'], ['fav', 'Favoris'], ['mine', 'Mes aliments'], ['recipes', 'Recettes']];
      h += `<div class="tabs">${tabs.map(([id, l]) => `<button class="${s.data.tab === id ? 'on' : ''}" data-act="resTab" data-tab="${id}">${l}</button>`).join('')}</div>`;
      let list = [];
      if (s.data.tab === 'recent') list = S.recents.map(r => foodByKey(r.key)).filter(Boolean);
      if (s.data.tab === 'fav') list = S.favs.map(foodByKey).filter(Boolean);
      if (s.data.tab === 'mine') list = S.foods.map(f => foodByKey('u:' + f.id)).concat(Object.values(S.off));
      if (s.data.tab === 'recipes') list = S.recipes.map(recipeFood).concat(S.favRecipes.map(id => foodByKey('nr:' + id)).filter(Boolean), NV_RECIPE_FOODS.filter(f => !S.favRecipes.includes(f.nv.id)));
      const empty = { recent: 'Les aliments que tu ajoutes apparaîtront ici.', fav: 'Touche l\'étoile d\'un aliment pour l\'ajouter aux favoris.',
        mine: 'Crée tes propres aliments ou scanne un code-barres.', recipes: 'Crée une recette pour l\'ajouter en une fois.' }[s.data.tab];
      h += list.length ? `<ul class="res-list">${list.map(f => resultRow(f, s)).join('')}</ul>` : `<p class="empty">${empty}</p>`;
    }
    box.innerHTML = h;
  }

  function openFood(food, opts) {
    opts = opts || {};
    const portions = N.portionsFor(food);
    const entry = opts.entry;
    let unit = 'g', count = opts.grams || lastGrams(food.key);
    if (entry && entry.pl) { const i = portions.findIndex(p => p.l === entry.pl); if (i >= 0) { unit = String(i); count = entry.pc; } }
    else if (entry) count = entry.g;
    else if (!opts.grams) {
      const r = S.recents.find(x => x.key === food.key);
      if (!r && portions.length) { unit = '0'; count = 1; }
    }
    return openSheet(s => {
      const grams = gramsOf(s);
      const n = N.forGrams(food.per100, grams);
      const fav = S.favs.includes(food.key);
      const rows = ['p', 'c', 'su', 'f', 'sa', 'fi', 'sl', 'ca', 'fe', 'mg', 'po', 'vc', 'vd', 'b12']
        .filter(k => food.per100[k] != null)
        .map(k => `<tr class="${N.NUTRIENTS[k].sub ? 'sub' : ''}"><td>${N.NUTRIENTS[k].label}</td><td>${fr(n[k], 2)} ${N.NUTRIENTS[k].unit}</td><td class="muted">${N.RDA[k] ? r0(n[k] / N.RDA[k] * 100) + ' %' : ''}</td></tr>`).join('');
      const tot = (n.p || 0) * 4 + (n.c || 0) * 4 + (n.f || 0) * 9 || 1;
      return sheetHead(esc(food.name), (food.nutriscore ? `<i class="ns ns-${food.nutriscore}">Nutri-Score ${food.nutriscore.toUpperCase()}</i> ` : '') + esc(foodSub(food)) + (food.qty ? ' · ' + esc(food.qty) : '')) + `
        <div class="food-hero">
          <div class="food-kcal"><b>${kcal(n.e)}</b><span>kcal</span></div>
          <div class="food-macros">
            <div class="fm carb"><b>${fr(n.c)} g</b><span>Glucides</span><i style="width:${(n.c || 0) * 400 / tot}%"></i></div>
            <div class="fm prot"><b>${fr(n.p)} g</b><span>Protéines</span><i style="width:${(n.p || 0) * 400 / tot}%"></i></div>
            <div class="fm fat"><b>${fr(n.f)} g</b><span>Lipides</span><i style="width:${(n.f || 0) * 900 / tot}%"></i></div>
          </div>
          <button class="icon-btn star ${fav ? 'on' : ''}" data-act="fav" aria-label="Favori">${icon('star')}</button>
        </div>
        <div class="qty">
          <input id="qtyN" inputmode="decimal" value="${fr(s.data.count, 2)}" aria-label="Quantité">
          <select id="qtyU" aria-label="Unité">
            <option value="g" ${s.data.unit === 'g' ? 'selected' : ''}>g / ml</option>
            ${portions.map((p, i) => `<option value="${i}" ${s.data.unit === String(i) ? 'selected' : ''}>${esc(p.l)} (${fr(p.g, 0)} g)</option>`).join('')}
          </select>
        </div>
        <div class="presets">${[50, 100, 150, 200, 250].map(v => `<button class="chip" data-act="preset" data-g="${v}">${v} g</button>`).join('')}</div>
        ${opts.mode === 'pick' ? '' : `<label class="field"><span>Repas</span><select id="mealSel">${MEALS.map(m => `<option value="${m.id}" ${m.id === s.data.meal ? 'selected' : ''}>${m.label}</option>`).join('')}</select></label>`}
        <table class="nutri"><thead><tr><th>Pour ${fr(grams, 0)} g</th><th></th><th class="muted">AR*</th></tr></thead><tbody>${rows}</tbody></table>
        <p class="muted small">*Apports de référence d'un adulte (8 400 kJ / 2 000 kcal). ${food.src === 'off' ? 'Données Open Food Facts (ODbL).' : food.src === 'ciqual' ? 'Données Ciqual, ANSES.' : ''}</p>
        <div class="sheet-actions">
          ${entry ? `<button class="btn ghost danger-text" data-act="delEntry">${icon('trash')}Supprimer</button>` : ''}
          ${food.src === 'custom' ? `<button class="btn ghost" data-act="editCustom">${icon('edit')}Modifier</button>` : ''}
          <button class="btn grow" data-act="confirmFood">${icon('check')}${entry ? 'Enregistrer' : opts.mode === 'pick' ? 'Ajouter à la recette' : 'Ajouter'}</button>
        </div>`;
    }, {
      data: { food, unit, count, meal: opts.meal || defaultMeal(), opts },
      mount: s => {
        const inp = $('#qtyN', s.el), sel = $('#qtyU', s.el), ms = $('#mealSel', s.el);
        const upd = () => { s.data.count = num(inp.value) || 0; s.data.unit = sel.value; const pos = inp.selectionStart; s.refresh(); const i2 = $('#qtyN', s.el); i2.focus(); try { i2.setSelectionRange(pos, pos); } catch (e) { /* ignore */ } };
        inp.addEventListener('input', upd);
        inp.addEventListener('keydown', e => { if (e.key === 'Enter') $('[data-act="confirmFood"]', s.el).click(); });
        sel.addEventListener('change', () => { s.data.unit = sel.value; s.data.count = sel.value === 'g' ? r0(gramsOfPortion(s, s.data.prevUnit)) : 1; s.data.prevUnit = sel.value; s.refresh(); });
        s.data.prevUnit = s.data.unit;
        if (ms) ms.addEventListener('change', () => { s.data.meal = ms.value; });
        inp.addEventListener('focus', () => inp.select());
      }
    });
    function gramsOfPortion(s, u) {
      if (u == null || u === 'g') return s.data.count;
      return (portions[+u] ? portions[+u].g : 100) * s.data.count;
    }
    function gramsOf(s) {
      return s.data.unit === 'g' ? s.data.count : (portions[+s.data.unit] ? portions[+s.data.unit].g : 100) * s.data.count;
    }
  }
  function sheetFoodGrams(s) {
    const food = s.data.food;
    const portions = N.portionsFor(food);
    if (s.data.unit === 'g') return { g: s.data.count };
    const p = portions[+s.data.unit];
    return { g: Math.round(p.g * s.data.count * 10) / 10, pl: p.l, pc: s.data.count };
  }

  function openQuickAdd(meal) {
    openSheet(() => sheetHead('Ajout rapide', mealLabel(meal)) + `
      <div class="form">
        <label class="field"><span>Nom (facultatif)</span><input id="qaName" placeholder="Ex. Repas au restaurant"></label>
        <label class="field"><span>Calories (kcal)</span><input id="qaK" inputmode="decimal" autofocus></label>
        <div class="grid3">
          <label class="field"><span>Glucides (g)</span><input id="qaC" inputmode="decimal"></label>
          <label class="field"><span>Protéines (g)</span><input id="qaP" inputmode="decimal"></label>
          <label class="field"><span>Lipides (g)</span><input id="qaF" inputmode="decimal"></label>
        </div></div>
      <div class="sheet-actions"><button class="btn grow" data-act="saveQuick">${icon('check')}Ajouter</button></div>`, { data: { meal } });
  }

  /* Aliment personnalisé */
  function openCustomFood(existing, prefill, after) {
    const f = existing || Object.assign({ name: '', brand: '', barcode: '', per100: {}, portions: [] }, prefill || {});
    const v = k => (f.per100 && f.per100[k] != null ? fr(f.per100[k], 2) : '');
    const fld = (id, label, k) => `<label class="field"><span>${label}</span><input id="cf_${k}" inputmode="decimal" value="${v(k)}"></label>`;
    const p0 = (f.portions || [])[0] || {};
    openSheet(() => sheetHead(existing ? 'Modifier l\'aliment' : 'Créer un aliment', 'Valeurs pour 100 g ou 100 ml (voir l\'étiquette)') + `
      <div class="form">
        <label class="field"><span>Nom *</span><input id="cf_name" value="${esc(f.name)}" autofocus></label>
        <div class="grid2"><label class="field"><span>Marque</span><input id="cf_brand" value="${esc(f.brand || '')}"></label>
        <label class="field"><span>Code-barres</span><input id="cf_barcode" inputmode="numeric" value="${esc(f.barcode || '')}"></label></div>
        <div class="grid2">${fld(0, 'Énergie (kcal) *', 'e')}${fld(0, 'Protéines (g)', 'p')}${fld(0, 'Glucides (g)', 'c')}${fld(0, 'dont sucres (g)', 'su')}
        ${fld(0, 'Lipides (g)', 'f')}${fld(0, 'dont AG saturés (g)', 'sa')}${fld(0, 'Fibres (g)', 'fi')}${fld(0, 'Sel (g)', 'sl')}</div>
        <div class="grid2"><label class="field"><span>Portion (nom)</span><input id="cf_pl" value="${esc(p0.l || '')}" placeholder="Ex. barre, pot, part"></label>
        <label class="field"><span>Portion (g)</span><input id="cf_pg" inputmode="decimal" value="${p0.g ? fr(p0.g) : ''}"></label></div>
      </div>
      <div class="sheet-actions">${existing ? `<button class="btn ghost danger-text" data-act="delCustom">${icon('trash')}Supprimer</button>` : ''}
      <button class="btn grow" data-act="saveCustom">${icon('check')}Enregistrer</button></div>`, { data: { existing, after } });
  }
  function readCustom(s) {
    const g = id => { const el = $('#cf_' + id, s.el); return el ? el.value.trim() : ''; };
    const name = g('name');
    const per100 = {};
    for (const k of N.NKEYS) per100[k] = null;
    for (const k of ['e', 'p', 'c', 'su', 'f', 'sa', 'fi', 'sl']) per100[k] = num(g(k));
    if (per100.e == null && (per100.p != null || per100.c != null || per100.f != null)) {
      per100.e = Math.round((per100.p || 0) * 4 + (per100.c || 0) * 4 + (per100.f || 0) * 9 + (per100.fi || 0) * 2);
    }
    if (!name) { toast('Donne un nom à l\'aliment.'); return null; }
    if (per100.e == null) { toast('Indique au moins les calories pour 100 g.'); return null; }
    const pg = num(g('pg'));
    return { name, brand: g('brand'), barcode: g('barcode').replace(/\D/g, ''), per100,
      portions: pg ? [{ l: g('pl') || 'portion', g: pg }] : [] };
  }

  /* Recettes */
  function openRecipe(existing) {
    const r = existing ? JSON.parse(JSON.stringify(existing)) : { id: uid(), name: '', servings: 2, items: [] };
    openSheet(s => {
      const rr = s.data.r;
      const food = rr.items.length ? recipeFood(rr) : null;
      const per = food ? N.forGrams(food.per100, food.portions[0].g) : null;
      return sheetHead(existing ? 'Modifier la recette' : 'Nouvelle recette') + `
        <div class="form"><label class="field"><span>Nom *</span><input id="rcName" value="${esc(rr.name)}" placeholder="Ex. Bolognaise maison"></label>
        <label class="field"><span>Nombre de portions</span><input id="rcServ" inputmode="numeric" value="${rr.servings}"></label></div>
        <h4 class="sec">Ingrédients</h4>
        <ul class="entries ing">${rr.items.map((it, i) => `<li><div class="grow"><b>${esc(it.name)}</b><span class="muted">${kcal(N.forGrams(it.per100, it.g).e)} kcal</span></div>
          <input class="g-input" inputmode="decimal" data-act="ingG" data-i="${i}" value="${fr(it.g, 1)}" aria-label="Grammes"><span class="muted">g</span>
          <button class="icon-btn" data-act="ingDel" data-i="${i}" aria-label="Retirer">${icon('trash')}</button></li>`).join('') || '<li class="empty">Aucun ingrédient pour l\'instant.</li>'}</ul>
        <button class="btn ghost wide" data-act="ingAdd">${icon('plus')}Ajouter un ingrédient</button>
        ${per ? `<p class="recipe-total">Par portion : <b>${kcal(per.e)} kcal</b> · G ${fr(per.c)} g · P ${fr(per.p)} g · L ${fr(per.f)} g</p>` : ''}
        <div class="sheet-actions">${existing ? `<button class="btn ghost danger-text" data-act="delRecipe">${icon('trash')}Supprimer</button>` : ''}
        <button class="btn grow" data-act="saveRecipe">${icon('check')}Enregistrer</button></div>`;
    }, {
      data: { r, existing },
      mount: s => {
        const n = $('#rcName', s.el), sv = $('#rcServ', s.el);
        n.addEventListener('input', () => { s.data.r.name = n.value; });
        sv.addEventListener('change', () => { s.data.r.servings = Math.max(1, Math.round(num(sv.value) || 1)); s.refresh(); });
      }
    });
  }

  /* Scanner de code-barres */
  let zxingLoading = null;
  function loadZxing() {
    if (window.ZXing) return Promise.resolve();
    if (!zxingLoading) zxingLoading = new Promise((res, rej) => {
      const sc = document.createElement('script'); sc.src = 'js/vendor/zxing.min.js';
      sc.onload = res; sc.onerror = () => rej(new Error('ZXing indisponible')); document.head.appendChild(sc);
    });
    return zxingLoading;
  }
  function openScanner(meal, opts) {
    const s = openSheet(() => sheetHead('Scanner un code-barres', 'Vise le code-barres du produit') + `
      <div class="scan-box"><video id="scanVideo" playsinline muted></video><div class="scan-frame"></div><p class="scan-msg" id="scanMsg">Démarrage de la caméra…</p></div>
      <div class="row gap"><input id="scanCode" class="grow" inputmode="numeric" placeholder="Ou saisis le code (EAN)" aria-label="Code-barres">
      <button class="btn" data-act="scanManual">${icon('search')}</button></div>
      <button class="btn ghost wide" data-act="scanPhoto">${icon('camera')}Prendre une photo du code-barres</button>`,
    { data: { meal, opts }, onClose: sh => stopScan(sh) });
    startScan(s);
  }
  async function startScan(s) {
    const msg = t => { const m = $('#scanMsg', s.el); if (m) m.textContent = t; };
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('nocam');
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      if (!sheets.includes(s)) { stream.getTracks().forEach(t => t.stop()); return; }
      s.data.stream = stream;
      const v = $('#scanVideo', s.el);
      v.srcObject = stream; await v.play();
      msg('Recherche du code-barres…');
      const formats = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'];
      let detector = null;
      if ('BarcodeDetector' in window) {
        try { const sup = await BarcodeDetector.getSupportedFormats(); if (sup.includes('ean_13')) detector = new BarcodeDetector({ formats: formats.filter(f => sup.includes(f)) }); } catch (e) { detector = null; }
      }
      if (detector) {
        const tick = async () => {
          if (!sheets.includes(s) || s.data.found) return;
          try { const r = await detector.detect(v); if (r.length) return onCode(s, r[0].rawValue); } catch (e) { /* image pas prête */ }
          s.data.timer = setTimeout(tick, 180);
        };
        tick();
      } else {
        await loadZxing();
        const hints = new Map();
        hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8, ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.UPC_E, ZXing.BarcodeFormat.CODE_128]);
        const reader = new ZXing.BrowserMultiFormatReader(hints, 200);
        s.data.reader = reader;
        reader.decodeFromVideoElementContinuously(v, res => { if (res && !s.data.found) onCode(s, res.getText()); });
      }
    } catch (e) {
      msg(e && e.name === 'NotAllowedError' ? 'Accès à la caméra refusé. Autorise-le dans les réglages, ou prends une photo.' : 'Caméra indisponible. Saisis le code ou prends une photo.');
    }
  }
  function stopScan(s) {
    clearTimeout(s.data.timer);
    if (s.data.reader) try { s.data.reader.reset(); } catch (e) { /* ignore */ }
    if (s.data.stream) s.data.stream.getTracks().forEach(t => t.stop());
  }
  async function decodePhoto(file, s) {
    const msg = $('#scanMsg', s.el);
    if (msg) msg.textContent = 'Analyse de la photo…';
    const url = URL.createObjectURL(file);
    try {
      if ('BarcodeDetector' in window) {
        const img = await createImageBitmap(file);
        const r = await new BarcodeDetector().detect(img);
        if (r.length) return onCode(s, r[0].rawValue);
      }
      await loadZxing();
      const reader = new ZXing.BrowserMultiFormatReader();
      const res = await reader.decodeFromImageUrl(url);
      onCode(s, res.getText());
    } catch (e) {
      if (msg) msg.textContent = 'Aucun code-barres lisible sur la photo. Réessaie plus près et bien éclairé.';
    } finally { URL.revokeObjectURL(url); }
  }
  async function onCode(s, code) {
    code = String(code).replace(/\D/g, '');
    if (!code || s.data.found) return;
    s.data.found = true;
    P.vibrate(40);
    stopScan(s);
    const { meal, opts } = s.data;
    const msg = $('#scanMsg', s.el);
    if (msg) msg.textContent = 'Code ' + code + ' : recherche du produit…';
    let food = null;
    const mine = S.foods.find(f => f.barcode === code);
    if (mine) food = foodByKey('u:' + mine.id);
    else if (S.off[code]) food = S.off[code];
    else if ((food = await CAT.byBarcode(code))) { S.off[code] = food; save(); }
    else {
      try {
        food = await N.offByBarcode(code);
        if (food) { S.off[code] = food; save(); }
      } catch (e) {
        closeSheet(s);
        toast('Pas de connexion : impossible de chercher ce produit en ligne.');
        openCustomFood(null, { barcode: code });
        return;
      }
    }
    closeSheet(s);
    if (food) openFood(food, { meal, mode: opts && opts.pick ? 'pick' : 'log', pick: opts && opts.pick });
    else { toast('Produit inconnu : crée-le en recopiant l\'étiquette.'); openCustomFood(null, { barcode: code }); }
  }

  /* Activités */
  /* Séances (types de combat Nutravyn, avec RPE) et activités du quotidien (MET). */
  function openActivity(existing) {
    const isSession = existing ? !!existing.session : true;
    openSheet(s => {
      const d = s.data, w = currentWeight();
      const tabs = `<div class="seg wide"><button class="${d.mode === 'session' ? 'on' : ''}" data-act="actMode" data-m="session">Séance</button><button class="${d.mode === 'other' ? 'on' : ''}" data-act="actMode" data-m="other">Autre activité</button></div>`;
      let body;
      if (d.mode === 'session') {
        const sess = E.SESSIONS.find(x => x.name === d.sel);
        const k = sess ? E.sessionKcal(sess.met, d.min || 0, w, d.rpe) : 0;
        const sw = sess ? E.sweatMl(sess.sweat, d.min || 0, d.rpe) : 0;
        body = `<div class="chips-grid">${E.SESSIONS.map(x => `<button class="choice sm ${d.sel === x.name ? 'on' : ''}" data-act="pickAct" data-name="${esc(x.name)}"><b>${esc(x.name)}</b></button>`).join('')}</div>
          <label class="field"><span>Durée (min)</span><input id="acMin" inputmode="numeric" value="${d.min}"></label>
          <label class="slider"><span>Intensité perçue (RPE)<b>${d.rpe}/10 · ${['', 'très facile', 'très facile', 'facile', 'modérée', 'modérée', 'soutenue', 'difficile', 'très difficile', 'extrême', 'maximale'][d.rpe]}</b></span>
          <input type="range" min="1" max="10" step="1" value="${d.rpe}" id="acRpe"></label>
          ${sess ? `<p class="recipe-total">${kcal(k)} kcal brûlées · ≈ ${fr(sw / 1000, 2)} L de sueur : bois-en autant en plus.</p>` : ''}`;
      } else {
        const q = N.norm(d.q || '');
        const list = N.ACTIVITIES.filter(a => !q || N.norm(a.name).includes(q));
        body = `<div class="grid2"><label class="field"><span>Durée (min)</span><input id="acMin" inputmode="numeric" value="${d.min}"></label>
          <label class="field"><span>Ou calories (kcal)</span><input id="acK" inputmode="numeric" value="${d.k || ''}" placeholder="auto"></label></div>
          <div class="search">${icon('search')}<input id="acQ" placeholder="Rechercher une activité" value="${esc(d.q || '')}"></div>
          <ul class="res-list acts">${list.map(a => `<li><button class="res ${d.sel === a.name ? 'on' : ''}" data-act="pickAct" data-name="${esc(a.name)}"><b>${esc(a.name)}</b><span class="muted">${kcal(N.activityKcal(a.met, d.min || 0, w))} kcal</span></button></li>`).join('')}</ul>`;
      }
      return sheetHead(existing ? 'Modifier l\'activité' : 'Ajouter une séance ou activité', 'Calcul selon ton poids (' + fr(w) + ' kg)') + tabs + body + `
        <div class="sheet-actions">${existing ? `<button class="btn ghost danger-text" data-act="delAct">${icon('trash')}Supprimer</button>` : ''}
        <button class="btn grow" data-act="saveAct" ${d.sel || d.k ? '' : 'disabled'}>${icon('check')}${d.sel ? esc(d.sel) : 'Choisis une activité'}</button></div>`;
    }, {
      data: { existing, mode: isSession ? 'session' : 'other', q: '', min: existing ? existing.min || 60 : 60, rpe: existing && existing.rpe ? existing.rpe : 7,
        sel: existing ? existing.name : null, k: existing && !existing.min ? existing.kcal : null },
      mount: s => {
        const m = $('#acMin', s.el), k = $('#acK', s.el), q = $('#acQ', s.el), r = $('#acRpe', s.el);
        if (m) m.addEventListener('change', () => { s.data.min = Math.round(num(m.value) || 0); s.data.k = null; s.refresh(); });
        if (k) k.addEventListener('change', () => { s.data.k = Math.round(num(k.value) || 0) || null; s.refresh(); });
        if (r) r.addEventListener('input', () => { s.data.rpe = +r.value; s.refresh(); });
        if (q) q.addEventListener('input', () => { s.data.q = q.value; const pos = q.selectionStart; s.refresh(); const q2 = $('#acQ', s.el); q2.focus(); q2.setSelectionRange(pos, pos); });
      }
    });
  }

  function lastWaist() { for (let i = S.weights.length - 1; i >= 0; i--) if (S.weights[i].waist) return S.weights[i].waist; return null; }
  function openWeight() {
    const lastW = currentWeight();
    openSheet(() => sheetHead('Nouvelle pesée') + `<div class="form">
      <label class="field"><span>Poids (kg)</span><input id="wKg" inputmode="decimal" value="${fr(lastW)}" autofocus></label>
      <label class="field"><span>Tour de taille (cm, facultatif)</span><input id="wWaist" inputmode="decimal" placeholder="${lastWaist() ? fr(lastWaist()) : 'au niveau du nombril'}"></label>
      <label class="field"><span>Date</span><input id="wDate" type="date" value="${ui.date > today() ? today() : ui.date}" max="${today()}"></label>
      <p class="muted small">Pèse-toi le matin, à jeun, après être passé aux toilettes. La courbe lissée gomme les variations d'eau.</p></div>
      <div class="sheet-actions"><button class="btn grow" data-act="saveWeight">${icon('check')}Enregistrer</button></div>`);
  }

  /* ---------- Jeûne ---------- */
  function renderFasting() {
    const F = S.fasting;
    const goalH = parseInt((F.active ? F.active.plan : F.plan), 10);
    let h = '<div class="topbar"><h1>Jeûne intermittent</h1></div>';
    if (F.active) {
      const el = Date.now() - F.active.start, pct = el / (goalH * 3600000);
      const stage = FAST_STAGES.filter(s => el / 3600000 >= s[0]).pop();
      const end = new Date(F.active.start + goalH * 3600000);
      h += `<section class="card fast"><div class="fast-ring ${pct >= 1 ? 'done' : ''}">${C.ring(pct, 230, 16)}
        <div class="ring-center"><span>${pct >= 1 ? 'Objectif atteint' : 'Temps écoulé'}</span><b id="fastEl">${dur(el)}</b>
        <span id="fastLeft">${pct >= 1 ? '+' + dur(el - goalH * 3600000) : 'encore ' + dur(goalH * 3600000 - el)}</span></div></div>
        <div class="fast-times"><div><span class="muted">Début</span><b>${new Date(F.active.start).toLocaleString('fr-FR', { weekday: 'short', hour: '2-digit', minute: '2-digit' })}</b><button class="link" data-act="fastEdit">modifier</button></div>
        <div><span class="muted">Fin prévue</span><b>${end.toLocaleString('fr-FR', { weekday: 'short', hour: '2-digit', minute: '2-digit' })}</b></div></div>
        <div class="stage"><b>${stage[1]}</b><p class="muted">${stage[2]}</p></div>
        <button class="btn wide ${pct >= 1 ? '' : 'ghost'}" data-act="fastStop">${pct >= 1 ? 'Terminer le jeûne' : 'Arrêter maintenant'}</button></section>`;
    } else {
      const last = F.history[F.history.length - 1];
      h += `<section class="card fast"><p class="muted center">Choisis ton rythme</p>
        <div class="plans">${FAST_PLANS.map(p => `<button class="plan ${p === F.plan ? 'on' : ''}" data-act="fastPlan" data-plan="${p}"><b>${p}</b><span>${parseInt(p, 10)} h de jeûne</span></button>`).join('')}</div>
        <div class="fast-ring idle">${C.ring(0, 230, 16)}<div class="ring-center"><span>Prêt</span><b>${parseInt(F.plan, 10)} h</b><span>${last ? 'dernier repas il y a ' + dur(Date.now() - last.end) : 'de jeûne'}</span></div></div>
        <button class="btn wide" data-act="fastStart">${icon('clock')}Commencer le jeûne</button></section>`;
    }
    const hist = F.history.slice(-14).reverse();
    const ok = F.history.filter(x => x.end - x.start >= x.goalH * 3600000).length;
    h += `<section class="card"><h3>Historique</h3><p class="muted">${F.history.length} jeûne(s), ${ok} objectif(s) atteint(s)</p>
      <ul class="entries">${hist.map((x, i) => { const d = x.end - x.start, okk = d >= x.goalH * 3600000; return `<li><div class="grow"><b>${new Date(x.start).toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })}</b><span class="muted">${x.plan} · ${new Date(x.start).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })} → ${new Date(x.end).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span></div><span class="kc ${okk ? 'ok' : ''}">${dur(d)}</span><button class="icon-btn" data-act="fastDel" data-i="${F.history.length - 1 - i}" aria-label="Supprimer">${icon('trash')}</button></li>`; }).join('') || '<li class="empty">Aucun jeûne terminé pour l\'instant.</li>'}</ul></section>
      <p class="foot muted">Le jeûne intermittent ne convient pas à tout le monde (grossesse, diabète, troubles alimentaires…). Demande conseil à un médecin en cas de doute.</p>`;
    return h;
  }
  setInterval(() => {
    if (ui.tab === 'fasting' && S.fasting.active && !document.hidden && S.profile.onboarded) {
      const el = $('#fastEl');
      if (el) { const prev = el.textContent; const n = dur(Date.now() - S.fasting.active.start); if (prev !== n) render(); }
    }
  }, 5000);

  /* ---------- Analyse ---------- */
  function renderStats() {
    const R = ui.statsRange, g = goals(), t = today();
    const keys = [];
    for (let i = R - 1; i >= 0; i--) keys.push(addDays(t, -i));
    const tots = keys.map(k => ({ k, t: dayTotals(k) }));
    const logged = tots.filter(x => x.t.count > 0);
    const avg = f => logged.length ? logged.reduce((a, x) => a + f(x.t), 0) / logged.length : 0;
    const aK = avg(x => x.eaten), aP = avg(x => x.n.p), aC = avg(x => x.n.c), aF = avg(x => x.n.f);
    const fmtLabel = k => { const d = pkey(k); return R <= 7 ? d.toLocaleDateString('fr-FR', { weekday: 'short' }).slice(0, 3) : d.getDate() + '/' + (d.getMonth() + 1); };
    const data = tots.map(x => ({ label: fmtLabel(x.k), value: x.t.eaten, title: dayLabel(x.k) + ' : ' + kcal(x.t.eaten) + ' kcal' }));
    let h = `<div class="topbar"><h1>Analyse</h1><div class="seg">${[7, 30, 90].map(r => `<button class="${R === r ? 'on' : ''}" data-act="range" data-r="${r}">${r} j</button>`).join('')}</div></div>`;
    h += `<section class="card"><h3>Calories</h3><p class="muted">Moyenne ${kcal(aK)} kcal / jour sur ${logged.length} jour(s) renseigné(s)</p>${C.bars(data, g.kcal, { label: 'Calories par jour' })}</section>`;
    const ad = g.adaptive;
    h += `<section class="card adaptive"><header class="meal-head"><span class="meal-ic act">${icon('target')}</span><div class="grow"><h3>Dépense réelle</h3>
      <p class="muted">${ad.reliable ? 'Mesurée sur ton journal et tes pesées (28 j)' : 'En calibrage'}</p></div></header>
      <div class="stats-grid three"><div><span class="muted">Formule</span><b>${kcal(g.tdee)}</b></div>
      <div><span class="muted">Mesurée</span><b>${ad.reliable ? kcal(ad.measured) : '–'}</b></div>
      <div><span class="muted">Retenue</span><b>${kcal(g.expenditure)}</b></div></div>
      <p class="verdict">${esc(ad.verdict)}</p>
      ${!S.profile.adaptive ? '<p class="muted small">Ajustement automatique désactivé dans Objectifs nutritionnels.</p>' : ''}</section>`;
    const kp = aP * 4, kc = aC * 4, kf = aF * 9, kt = kp + kc + kf || 1;
    h += `<section class="card"><h3>Répartition des macronutriments</h3><div class="donut-row">${C.donut([{ value: kc, cls: 'd-carb' }, { value: kp, cls: 'd-prot' }, { value: kf, cls: 'd-fat' }], 150)}
      <ul class="legend">
        <li><i class="carb"></i>Glucides <b>${r0(aC)} g</b><span class="muted">${r0(kc / kt * 100)} % (objectif ${Math.round(splitOf(S.profile).c * 100)} %)</span></li>
        <li><i class="prot"></i>Protéines <b>${r0(aP)} g</b><span class="muted">${r0(kp / kt * 100)} % (objectif ${Math.round(splitOf(S.profile).p * 100)} %)</span></li>
        <li><i class="fat"></i>Lipides <b>${r0(aF)} g</b><span class="muted">${r0(kf / kt * 100)} % (objectif ${Math.round(splitOf(S.profile).f * 100)} %)</span></li></ul></div></section>`;
    const nutr = [['fi', 'Fibres', 30, 'min'], ['su', 'Sucres', 90, 'max'], ['sa', 'AG saturés', 20, 'max'], ['sl', 'Sel', 5, 'max']];
    h += `<section class="card"><h3>Qualité de l'alimentation</h3><p class="muted">Moyennes journalières comparées aux repères (ANSES, OMS)</p>
      ${nutr.map(([k, l, ref, kind]) => { const v = avg(x => x.n[k]); const bad = kind === 'min' ? v < ref : v > ref; return `<div class="macro ${bad && logged.length ? 'warn' : 'good'}"><div class="macro-top"><span>${l}</span><span><b>${fr(v)}</b> g · ${kind === 'min' ? 'au moins' : 'au plus'} ${ref} g</span></div><div class="bar"><i style="width:${Math.min(100, v / ref * 100)}%"></i></div></div>`; }).join('')}</section>`;
    const since = pkey(addDays(t, -(R - 1))).getTime();
    const ws = S.weights.filter(w => pkey(w.date).getTime() >= since);
    const cw = currentWeight(), b = N.bmi(cw, S.profile.height);
    const first = S.weights[0];
    const trendAll = E.smooth(S.weights);
    const trendWin = trendAll.filter(x => pkey(x.date).getTime() >= since);
    const tNow = trendAll.length ? trendAll[trendAll.length - 1].kg : cw;
    const waist = lastWaist();
    h += `<section class="card"><header class="meal-head"><div class="grow"><h3>Poids</h3><p class="muted">${fr(cw)} kg (tendance ${fr(tNow)} kg) · IMC ${fr(b)} (${N.bmiLabel(b)})${first ? ' · ' + (tNow - first.kg > 0 ? '+' : '') + fr(tNow - first.kg) + ' kg depuis le début' : ''}${waist ? ' · taille ' + fr(waist) + ' cm' : ''}</p></div>
      <button class="add-btn" data-act="addWeight" aria-label="Ajouter une pesée">${icon('plus')}</button></header>
      ${ws.length >= 1 ? C.line(ws.map(w => ({ x: pkey(w.date).getTime(), y: w.kg, title: pkey(w.date).toLocaleDateString('fr-FR') + ' : ' + fr(w.kg) + ' kg' })), S.profile.targetWeight,
        { label: 'Évolution du poids', trend: ws.length >= 3 ? trendWin.map(x => ({ x: pkey(x.date).getTime(), y: x.kg })) : null }) : '<p class="empty">Ajoute des pesées pour voir ta courbe.</p>'}
      ${ws.length >= 3 ? '<p class="legend-line"><i class="lg-raw"></i>pesées <i class="lg-trend"></i>tendance lissée</p>' : ''}
      ${S.weights.length ? `<details><summary>Toutes les pesées (${S.weights.length})</summary><ul class="entries">${S.weights.slice().reverse().map(w => `<li><div class="grow"><b>${fr(w.kg)} kg</b><span class="muted">${pkey(w.date).toLocaleDateString('fr-FR')}${w.waist ? ' · taille ' + fr(w.waist) + ' cm' : ''}</span></div><button class="icon-btn" data-act="delWeight" data-date="${w.date}" aria-label="Supprimer">${icon('trash')}</button></li>`).join('')}</ul></details>` : ''}</section>`;
    const aW = avg(x => x.water);
    const fasts = S.fasting.history.filter(x => x.end >= since);
    h += `<section class="card stats-grid">
      <div><span class="muted">Eau / jour</span><b>${fr(aW / 1000, 2)} L</b></div>
      <div><span class="muted">Jours renseignés</span><b>${logged.length} / ${R}</b></div>
      <div><span class="muted">Dans l'objectif (±10 %)</span><b>${logged.filter(x => Math.abs(x.t.eaten - g.kcal) <= g.kcal * 0.1).length}</b></div>
      <div><span class="muted">Jeûnes terminés</span><b>${fasts.length}</b></div></section>`;
    return h;
  }

  /* ---------- Profil ---------- */
  function renderProfile() {
    const p = S.profile, g = goals();
    const goalTxt = { lose: 'Perdre du poids', maintain: 'Maintenir mon poids', gain: 'Prendre du poids', cut: 'Faire le poids' }[p.goal];
    const lvl = ACTIVITY_LEVELS.find(a => a[0] === p.activity) || ACTIVITY_LEVELS[1];
    const row = (act, ic, label, val) => `<li><button data-act="${act}">${icon(ic)}<span class="grow">${label}</span>${val ? `<span class="muted">${val}</span>` : ''}${icon('chevR', 'chev')}</button></li>`;
    return `<div class="topbar"><h1>Profil</h1></div>
      <section class="card profile-card"><div class="avatar">${esc((p.name || 'C').charAt(0).toUpperCase())}</div>
        <div class="grow"><h3>${esc(p.name || 'Mon profil')}</h3><p class="muted">${p.sex === 'f' ? 'Femme' : 'Homme'} · ${p.age} ans · ${p.height} cm · ${fr(currentWeight())} kg</p></div>
        <button class="icon-btn" data-act="editProfile" aria-label="Modifier le profil">${icon('edit')}</button></section>
      <section class="card goals-card"><div><span class="muted">Objectif</span><b>${goalTxt}</b></div><div><span class="muted">Calories / jour</span><b>${kcal(g.kcal)} kcal</b></div>
        <div><span class="muted">G / P / L</span><b>${g.c} / ${g.p} / ${g.f} g</b></div><div><span class="muted">${g.adaptive.reliable && S.profile.adaptive ? 'Dépense mesurée' : 'Dépense estimée'}</span><b>${kcal(g.expenditure)} kcal</b></div></section>
      <ul class="menu card">
        ${row('editProfile', 'scale', 'Profil et objectif', goalTxt)}
        ${row('editGoals', 'sliders', 'Objectifs nutritionnels', kcal(g.kcal) + ' kcal')}
        ${row('manageFoods', 'food', 'Mes aliments et recettes', (S.foods.length + Object.keys(S.off).length) + ' / ' + S.recipes.length)}
        ${row('catalog', 'box', 'Catalogue produits hors ligne', { ready: 'installé', downloading: Math.round(CAT.status().progress * 100) + ' %', error: 'erreur', none: 'non installé' }[CAT.status().state])}
        ${row('gemini', 'sparkle', 'Analyse photo (Gemini)', S.settings.geminiKey ? 'activée' : 'à configurer')}
        ${row('reminders', 'bell', 'Rappels', S.settings.reminders.on ? 'activés' : 'désactivés')}
        ${row('progress', 'belt', 'Ma progression', S.settings.game ? 'ceinture ' + game().belt.label.toLowerCase() : 'désactivée')}
        <li><label class="menu-select">${icon('trophy')}<span class="grow">Gamification (ceintures, défis)</span><input type="checkbox" class="toggle" data-act="gameToggleIn" ${S.settings.game ? 'checked' : ''}></label></li>
        <li><label class="menu-select">${icon('info')}<span class="grow">Thème</span><select data-act="theme">
          ${[['auto', 'Automatique'], ['light', 'Clair'], ['dark', 'Sombre']].map(([v, l]) => `<option value="${v}" ${S.settings.theme === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label></li>
      </ul>
      <h4 class="sec">Données</h4>
      <ul class="menu card">
        ${row('exportCsv', 'download', 'Exporter le journal (CSV)')}
        ${row('exportWeights', 'download', 'Exporter les pesées (CSV)')}
        ${row('backup', 'upload', 'Sauvegarder mes données (JSON)')}
        ${P.canShare() ? row('shareBackup', 'share', 'Partager une sauvegarde') : ''}
        ${row('restore', 'download', 'Restaurer une sauvegarde')}
        ${P.kind === 'windows' ? row('openFolder', 'folder', 'Ouvrir le dossier Calorys') : ''}
        ${row('reset', 'trash', 'Tout effacer')}
      </ul>
      ${row('about', 'info', 'À propos et licences', 'v' + APP_VERSION).replace('<li>', '<ul class="menu card"><li>').replace('</li>', '</li></ul>')}
      <p class="foot muted">Calorys ${APP_VERSION} · QMTech · Tes données restent sur cet appareil.</p>`;
  }

  function openProfile() {
    const p = S.profile;
    openSheet(s => {
      const d = s.data.p;
      return sheetHead('Profil et objectif') + `<div class="form">
        <label class="field"><span>Prénom</span><input id="pf_name" value="${esc(d.name)}"></label>
        <div class="seg wide">${[['m', 'Homme'], ['f', 'Femme']].map(([v, l]) => `<button class="${d.sex === v ? 'on' : ''}" data-act="pfSet" data-k="sex" data-v="${v}">${l}</button>`).join('')}</div>
        <div class="grid3"><label class="field"><span>Âge</span><input id="pf_age" inputmode="numeric" value="${d.age}"></label>
        <label class="field"><span>Taille (cm)</span><input id="pf_height" inputmode="numeric" value="${d.height}"></label>
        <label class="field"><span>Poids cible (kg)</span><input id="pf_targetWeight" inputmode="decimal" value="${fr(d.targetWeight)}"></label></div>
        <label class="field"><span>Niveau d'activité</span><select id="pf_activity">${ACTIVITY_LEVELS.map(a => `<option value="${a[0]}" ${a[0] === d.activity ? 'selected' : ''}>${a[1]} : ${a[2]}</option>`).join('')}</select></label>
        <div class="seg wide goals4">${[['lose', 'Perdre'], ['maintain', 'Maintenir'], ['gain', 'Prendre'], ['cut', 'Faire le poids']].map(([v, l]) => `<button class="${d.goal === v ? 'on' : ''}" data-act="pfSet" data-k="goal" data-v="${v}">${l}</button>`).join('')}</div>
        ${d.goal === 'lose' || d.goal === 'gain' ? `<label class="field"><span>Rythme</span><select id="pf_pace">${[0.25, 0.5, 0.75, 1].map(v => `<option value="${v}" ${v === d.pace ? 'selected' : ''}>${fr(v, 2)} kg par semaine</option>`).join('')}</select></label>` : ''}
        ${d.goal === 'cut' ? `<label class="field"><span>Date de la pesée officielle</span><input id="pf_weighIn" type="date" min="${addDays(today(), 1)}" value="${d.weighIn || addDays(today(), 42)}"></label>
        <p class="muted small">Mode sèche : déficit plafonné à 25 %, plancher au métabolisme de base, protéines au moins 1,8 g/kg. Aucune coupe hydrique n'est planifiée par l'appli.</p>` : ''}
      </div><div class="sheet-actions"><button class="btn grow" data-act="saveProfile">${icon('check')}Enregistrer</button></div>`;
    }, { data: { p: JSON.parse(JSON.stringify(p)) } });
  }
  function readProfileForm(s) {
    const d = s.data.p;
    const v = id => { const el = $('#pf_' + id, s.el); return el ? el.value : null; };
    if (v('name') != null) d.name = v('name').trim();
    d.age = Math.round(num(v('age')) || d.age);
    d.height = Math.round(num(v('height')) || d.height);
    d.targetWeight = num(v('targetWeight')) || d.targetWeight;
    if (v('activity')) d.activity = Number(v('activity'));
    if (v('pace')) d.pace = Number(v('pace'));
    if (v('weighIn') != null) d.weighIn = v('weighIn');
  }

  function openGoals() {
    const p = S.profile;
    openSheet(s => {
      const d = s.data, w = currentWeight();
      const base = goals();
      const k = d.override ? d.kcal : base.calc;
      const split = d.preset === 'custom' ? { p: d.split.p / 100, c: d.split.c / 100, f: d.split.f / 100 } : E.PRESETS[d.preset];
      const m = E.macros(k, split, w, p.goal === 'cut' ? 1.8 : 0);
      const sum = d.split.c + d.split.p + d.split.f;
      const sl = (key, label) => `<label class="slider"><span>${label}<b>${d.split[key]} % · ${m[key]} g</b></span><input type="range" min="5" max="75" step="5" value="${d.split[key]}" data-act="split" data-k="${key}"></label>`;
      const ok = d.preset !== 'custom' || sum === 100;
      return sheetHead('Objectifs nutritionnels', 'Métabolisme ' + kcal(base.bmr) + ' kcal · dépense formule ' + kcal(base.tdee) + ' kcal' + (base.adaptive.reliable ? ' · mesurée ' + kcal(base.adaptive.measured) + ' kcal' : '')) + `<div class="form">
        <label class="switch"><input type="checkbox" id="gAd" ${d.adaptive ? 'checked' : ''}><span>Ajuster l'objectif selon ma dépense réelle (journal + pesées, après 2 semaines)</span></label>
        <label class="switch"><input type="checkbox" id="gOverride" ${d.override ? 'checked' : ''}><span>Définir mon objectif calorique moi-même</span></label>
        <label class="field"><span>Calories par jour</span><input id="gK" inputmode="numeric" value="${r0(k)}" ${d.override ? '' : 'disabled'}></label>
        <label class="field"><span>Répartition des macros</span><select id="gPreset">${Object.entries(E.PRESETS).map(([id, x]) => `<option value="${id}" ${d.preset === id ? 'selected' : ''}>${x.label} (P ${Math.round(x.p * 100)} / G ${Math.round(x.c * 100)} / L ${Math.round(x.f * 100)} %)</option>`).join('')}
          <option value="custom" ${d.preset === 'custom' ? 'selected' : ''}>Personnalisée</option></select></label>
        ${d.preset === 'custom' ? sl('c', 'Glucides') + sl('p', 'Protéines') + sl('f', 'Lipides') + `<p class="${sum === 100 ? 'muted' : 'warn-text'}">Total : ${sum} %${sum === 100 ? '' : ' (doit faire 100 %)'}</p>` : ''}
        <p class="recipe-total">Par jour : <b>${kcal(k)} kcal</b> · G ${m.c} g · P ${m.p} g · L ${m.f} g${p.goal === 'cut' ? '<br><span class="muted small">Mode sèche : protéines au moins 1,8 g/kg.</span>' : ''}</p>
        <label class="field"><span>Calories des séances rendues à l'objectif</span><select id="gEx">${[[0, 'Aucune'], [50, '50 % (conseillé)'], [75, '75 %'], [100, '100 %']].map(([v, l]) => `<option value="${v}" ${+d.exPct === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
        <p class="muted small">Les estimations de dépense sont généreuses : « manger sa séance » est la première cause de plateau.</p>
        <label class="switch"><input type="checkbox" id="gWA" ${d.waterAuto ? 'checked' : ''}><span>Objectif d'eau automatique (35 ml/kg + 500 ml par heure de séance) : ${fr(E.waterGoalMl(w, 0) / 1000, 2)} L les jours sans séance</span></label>
        <div class="grid2">${d.waterAuto ? '' : `<label class="field"><span>Objectif d'eau (ml)</span><input id="gW" inputmode="numeric" value="${d.water}"></label>`}
        <label class="field"><span>Taille d'un verre (ml)</span><input id="gG" inputmode="numeric" value="${d.glass}"></label></div>
        <label class="field"><span>Objectif de pas</span><input id="gS" inputmode="numeric" value="${d.steps}"></label>
      </div><div class="sheet-actions"><button class="btn grow" data-act="saveGoals" ${ok ? '' : 'disabled'}>${icon('check')}Enregistrer</button></div>`;
    }, {
      data: { override: !!p.kcalOverride, kcal: p.kcalOverride || goals().calc, preset: p.preset || 'balanced', split: Object.assign({}, p.split),
        adaptive: p.adaptive !== false, exPct: p.exercisePct, waterAuto: p.waterAuto, water: p.waterGoal, glass: p.glass, steps: p.stepsGoal },
      mount: s => {
        const keep = () => { const d = s.data; const g = id => $('#' + id, s.el);
          d.override = g('gOverride').checked; if (d.override) d.kcal = num(g('gK').value) || d.kcal;
          d.adaptive = g('gAd').checked; d.preset = g('gPreset').value; d.exPct = +g('gEx').value; d.waterAuto = g('gWA').checked;
          if (g('gW')) d.water = num(g('gW').value) || d.water;
          d.glass = num(g('gG').value) || d.glass; d.steps = num(g('gS').value) || d.steps; };
        s.data.keep = keep;
        ['gOverride', 'gAd', 'gPreset', 'gWA', 'gEx'].forEach(id => $('#' + id, s.el).addEventListener('change', () => { keep(); s.refresh(); }));
        s.el.querySelectorAll('input[type=range]').forEach(r => r.addEventListener('input', () => { keep(); s.data.split[r.dataset.k] = Number(r.value); s.refresh(); }));
      }
    });
  }

  function openManageFoods() {
    openSheet(() => sheetHead('Mes aliments et recettes') + `
      <h4 class="sec">Recettes</h4><ul class="entries">${S.recipes.map(r => { const f = recipeFood(r); return `<li data-act="editRecipe" data-id="${r.id}"><div class="grow"><b>${esc(r.name)}</b><span class="muted">${r.items.length} ingrédient(s) · ${r.servings} portion(s)</span></div><span class="kc">${kcal(N.forGrams(f.per100, f.portions[0].g).e)}</span></li>`; }).join('') || '<li class="empty">Aucune recette.</li>'}</ul>
      <button class="btn ghost wide" data-act="newRecipe">${icon('plus')}Nouvelle recette</button>
      <h4 class="sec">Mes aliments</h4><ul class="entries">${S.foods.map(f => `<li data-act="editCustomId" data-id="${f.id}"><div class="grow"><b>${esc(f.name)}</b><span class="muted">${esc(f.brand || '')} ${f.barcode ? '· ' + f.barcode : ''}</span></div><span class="kc">${kcal(f.per100.e)}</span></li>`).join('') || '<li class="empty">Aucun aliment personnel.</li>'}</ul>
      <button class="btn ghost wide" data-act="newFood">${icon('plus')}Créer un aliment</button>
      ${Object.keys(S.off).length ? `<h4 class="sec">Produits scannés (Open Food Facts)</h4><ul class="entries">${Object.values(S.off).map(f => `<li><div class="grow"><b>${esc(f.name)}</b><span class="muted">${esc(f.brand || '')} · ${f.barcode}</span></div><button class="icon-btn" data-act="delOff" data-code="${f.barcode}" aria-label="Supprimer">${icon('trash')}</button></li>`).join('')}</ul>` : ''}`,
    { live: true });
  }

  function openAbout() {
    openSheet(() => sheetHead('À propos de Calorys', 'Version ' + APP_VERSION + ' · QMTech') + `<div class="prose">
      <p>Calorys est un compteur de calories et un journal alimentaire qui fonctionne entièrement hors ligne. Tes données restent sur ton appareil : pas de compte, pas de serveur, pas de publicité.</p>
      <h4>Sources et licences</h4>
      <ul><li><b>Table Ciqual 2025</b> : ANSES, composition nutritionnelle de ${N.ciqual.size.toLocaleString('fr-FR')} aliments. Licence Ouverte / Open Licence Etalab 2.0.</li>
      <li><b>Open Food Facts</b> (recherche en ligne et codes-barres, facultatif) : base collaborative sous licence ODbL, contenus sous licence Database Contents. openfoodfacts.org</li>
      <li><b>ZXing</b> (lecture des codes-barres) : licence Apache 2.0.</li>
      <li><b>Dépense des activités</b> : valeurs MET du Compendium of Physical Activities.</li>
      ${P.kind === 'windows' ? '<li><b>Neutralinojs</b> : licence MIT.</li>' : ''}</ul>
      <h4>Calculs</h4><p>Métabolisme de base : équation de Mifflin-St Jeor. Objectif : dépense journalière ajustée de 7 700 kcal par kg visé, sans descendre sous 1 200 kcal (femme) ou 1 500 kcal (homme).</p>
      <p class="muted">Calorys ne remplace pas l'avis d'un médecin ou d'un diététicien.</p>
      ${P.kind === 'windows' ? `<h4>Raccourcis clavier</h4><p>← / → : jour précédent / suivant · N ou Ctrl+F : ajouter un aliment · T : aujourd'hui · Ctrl+S : sauvegarde · Échap : fermer.<br>Tu peux aussi glisser un fichier de sauvegarde .json dans la fenêtre pour le restaurer.</p>` : ''}
      </div>`);
  }

  /* ---------- Accueil (onboarding) ---------- */
  function renderOnboarding() {
    const o = ui.ob || (ui.ob = JSON.parse(JSON.stringify(defaults().profile)));
    const st = ui.obStep;
    const steps = 5;
    const dots = `<div class="ob-dots">${Array.from({ length: steps }, (_, i) => `<i class="${i <= st ? 'on' : ''}"></i>`).join('')}</div>`;
    const nav = (next, label) => `<div class="ob-nav">${st ? '<button class="btn ghost" data-act="obBack">Retour</button>' : ''}<button class="btn grow" data-act="${next || 'obNext'}">${label || 'Continuer'}</button></div>`;
    let body = '';
    if (st === 0) body = `<div class="ob-hero"><img src="img/icon.svg" alt=""><h1>Bienvenue sur Calorys</h1><p>Compte tes calories, suis tes repas, ton eau, ton poids et ton jeûne. Tout reste sur ton appareil, même sans connexion.</p></div>
      <label class="field"><span>Ton prénom (facultatif)</span><input id="ob_name" value="${esc(o.name)}"></label>` + nav(null, 'Commencer');
    if (st === 1) body = `<h2>Parle-nous de toi</h2><p class="muted">Pour calculer tes besoins énergétiques.</p>
      <div class="seg wide">${[['m', 'Homme'], ['f', 'Femme']].map(([v, l]) => `<button class="${o.sex === v ? 'on' : ''}" data-act="obSet" data-k="sex" data-v="${v}">${l}</button>`).join('')}</div>
      <div class="grid3"><label class="field"><span>Âge</span><input id="ob_age" inputmode="numeric" value="${o.age}"></label>
      <label class="field"><span>Taille (cm)</span><input id="ob_height" inputmode="numeric" value="${o.height}"></label>
      <label class="field"><span>Poids (kg)</span><input id="ob_weight" inputmode="decimal" value="${fr(o.weight)}"></label></div>` + nav();
    if (st === 2) body = `<h2>Ton niveau d'activité</h2><p class="muted">En dehors des activités que tu ajouteras au journal.</p>
      <div class="choices">${ACTIVITY_LEVELS.map(a => `<button class="choice ${o.activity === a[0] ? 'on' : ''}" data-act="obSet" data-k="activity" data-v="${a[0]}"><b>${a[1]}</b><span>${a[2]}</span></button>`).join('')}</div>` + nav();
    if (st === 3) body = `<h2>Ton objectif</h2>
      <div class="choices">${[['lose', 'Perdre du poids', ''], ['maintain', 'Maintenir mon poids', ''], ['gain', 'Prendre du poids / du muscle', ''], ['cut', 'Faire le poids', 'Atteindre une catégorie pour une pesée officielle (compétition)']].map(([v, l, h]) => `<button class="choice ${o.goal === v ? 'on' : ''}" data-act="obSet" data-k="goal" data-v="${v}"><b>${l}</b>${h ? `<span>${h}</span>` : ''}</button>`).join('')}</div>
      ${o.goal !== 'maintain' ? `<div class="grid2"><label class="field"><span>${o.goal === 'cut' ? 'Poids de la catégorie (kg)' : 'Poids cible (kg)'}</span><input id="ob_targetWeight" inputmode="decimal" value="${fr(o.targetWeight)}"></label>
      ${o.goal === 'cut' ? `<label class="field"><span>Date de la pesée</span><input id="ob_weighIn" type="date" min="${addDays(today(), 1)}" value="${o.weighIn || addDays(today(), 42)}"></label>`
        : `<label class="field"><span>Rythme</span><select id="ob_pace">${[0.25, 0.5, 0.75, 1].map(v => `<option value="${v}" ${v === o.pace ? 'selected' : ''}>${fr(v, 2)} kg / semaine</option>`).join('')}</select></label>`}</div>` : ''}` + nav();
    if (st === 4) {
      const b = E.bmr(o.sex, o.weight, o.height, o.age), theo = E.tdee(o.sex, o.weight, o.height, o.age, o.activity);
      const cut = o.goal === 'cut' && o.weighIn ? E.cutPlan(o, o.weight, theo, b) : null;
      const target = cut ? cut.target : E.dailyTarget(theo, o.goal, o.goal === 'maintain' ? 0 : o.pace, o.sex, b);
      const preset = presetFor(o.goal);
      const m = E.macros(target, E.PRESETS[preset], o.weight, o.goal === 'cut' ? 1.8 : 0);
      const info = E.describe(target, theo, b, cut ? Math.min(cut.required, cut.safe) : o.pace, o.weight);
      const g = { kcal: target, bmr: Math.round(b), tdee: Math.round(theo) };
      const diff = Math.abs(o.weight - o.targetWeight);
      const weeks = o.goal === 'maintain' || o.goal === 'cut' || !diff ? 0 : Math.ceil(diff / o.pace);
      const eta = weeks ? new Date(Date.now() + weeks * 7 * 86400000).toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' }) : '';
      body = `<h2>Ton plan${o.name ? ', ' + esc(o.name) : ''}</h2><div class="ob-plan"><div class="big"><b>${kcal(g.kcal)}</b><span>kcal par jour</span></div>
        <div class="grid3 plan-macros"><div class="carb"><b>${m.c} g</b><span>Glucides</span></div><div class="prot"><b>${m.p} g</b><span>Protéines</span></div><div class="fat"><b>${m.f} g</b><span>Lipides</span></div></div>
        <p class="muted">Métabolisme de base ${kcal(g.bmr)} kcal · dépense estimée ${kcal(g.tdee)} kcal${eta ? '<br>Objectif de ' + fr(o.targetWeight) + ' kg vers ' + eta : ''}
        <br>Répartition : ${E.PRESETS[preset].label}</p>
        ${cut ? `<p class="target-note">${icon('target')}<span>${esc(cut.message)}</span></p>` : info.note ? `<p class="target-note">${icon('info')}<span>${esc(info.note)}</span></p>` : ''}
        <p class="muted small">L'objectif se recale ensuite sur ta dépense réelle, mesurée à partir de ton journal et de tes pesées.</p></div>
        <p class="muted small">Tu pourras tout ajuster plus tard dans Profil.</p>` + nav('obDone', 'C\'est parti');
    }
    return `<div class="ob">${dots}${body}</div>`;
  }
  function readOb() {
    const o = ui.ob;
    const v = id => { const el = $('#ob_' + id); return el ? el.value : null; };
    if (v('name') != null) o.name = v('name').trim();
    if (v('age') != null) o.age = Math.min(110, Math.max(12, Math.round(num(v('age')) || o.age)));
    if (v('height') != null) o.height = Math.min(250, Math.max(100, Math.round(num(v('height')) || o.height)));
    if (v('weight') != null) o.weight = Math.min(350, Math.max(30, num(v('weight')) || o.weight));
    if (v('targetWeight') != null) o.targetWeight = num(v('targetWeight')) || o.targetWeight;
    if (v('pace') != null) o.pace = Number(v('pace'));
    if (v('weighIn') != null) o.weighIn = v('weighIn');
  }
  const presetFor = goal => (goal === 'cut' ? 'cut' : goal === 'gain' ? 'bulk' : 'balanced');

  /* ---------- Recettes (bibliothèque Nutravyn + recettes perso) ---------- */
  const RECIPE_TAGS = [['all', 'Toutes'], ['fav', 'Favorites'], ['mine', 'Mes recettes'], ['petit-dej', 'Petit-déj'], ['proteine', 'Protéinées'],
    ['rapide', 'Rapides'], ['seche', 'Sèche'], ['prise de masse', 'Prise de masse'], ['healthy', 'Healthy'], ['low-carb', 'Low-carb'],
    ['vegetarien', 'Végétarien'], ['batch', 'Batch cooking'], ['plaisir', 'Plaisir'], ['dessert', 'Desserts'], ['collation', 'Collations']];
  function renderRecipes() {
    const q = N.norm(ui.rq || ''), tag = ui.rtag || 'all';
    let list = [];
    if (tag === 'mine') list = S.recipes.map(r => ({ mine: true, r, f: recipeFood(r) }));
    else {
      list = NV.recipes.filter(r => tag === 'all' || (tag === 'fav' ? S.favRecipes.includes(r.id) : r.tags.includes(tag))).map(r => ({ r, f: foodByKey('nr:' + r.id) }));
      if (tag === 'all') list = S.recipes.map(r => ({ mine: true, r, f: recipeFood(r) })).concat(list);
    }
    if (q) list = list.filter(x => N.norm(x.r.name).includes(q) || (x.r.tags || []).some(t => N.norm(t).includes(q)));
    const shop = S.shopping.filter(i => !i.done).length;
    let h = `<div class="topbar"><h1>Recettes</h1><button class="chip" data-act="shopping">${icon('cart')}Courses${shop ? ' (' + shop + ')' : ''}</button></div>
      <div class="search">${icon('search')}<input id="rcQ" type="search" placeholder="Rechercher une recette" value="${esc(ui.rq || '')}" aria-label="Rechercher une recette"></div>
      <div class="tabs wrap">${RECIPE_TAGS.map(([id, l]) => `<button class="${tag === id ? 'on' : ''}" data-act="rtag" data-tag="${esc(id)}">${l}</button>`).join('')}</div>`;
    h += list.length ? `<div class="recipe-grid">${list.map(({ r, f, mine }) => {
      const per = f.per100 && f.portions[0] ? N.forGrams(f.per100, f.portions[0].g) : { e: 0, p: 0 };
      const fav = !mine && S.favRecipes.includes(r.id);
      return `<button class="card recipe-card" data-act="${mine ? 'editRecipe' : 'nvRecipe'}" data-id="${r.id}">
        <span class="rc-top"><b>${esc(r.name)}</b>${fav ? icon('star', 'fav-on') : ''}</span>
        <span class="rc-stats"><span><b>${kcal(per.e)}</b> kcal</span><span><b>${r0(per.p)} g</b> prot.</span>${r.minutes ? `<span>${icon('timer')}${r.minutes} min</span>` : ''}</span>
        <span class="rc-tags">${mine ? '<i>Ma recette</i>' : (r.tags || []).slice(0, 3).map(t => `<i>${esc(t)}</i>`).join('')}</span></button>`;
    }).join('')}</div>` : '<p class="empty">Aucune recette ne correspond.</p>';
    h += `<button class="btn ghost wide" data-act="newRecipe">${icon('plus')}Créer ma recette</button>`;
    return h;
  }
  function openNvRecipe(id, meal) {
    const r = NV_RECIPES.get(+id);
    if (!r) return;
    openSheet(s => {
      const k = s.data.servings / r.servings;
      const f = foodByKey('nr:' + r.id), portion = f.portions[0].g;
      const per = N.forGrams(f.per100, portion);
      const fav = S.favRecipes.includes(r.id);
      return sheetHead(esc(r.name), (r.minutes ? r.minutes + ' min · ' : '') + r.servings + ' portion(s) · ' + (r.tags || []).join(', ')) + `
        <div class="food-hero"><div class="food-kcal"><b>${kcal(per.e)}</b><span>kcal / portion</span></div>
          <div class="food-macros"><div class="fm carb"><b>${fr(per.c)} g</b><span>Glucides</span></div><div class="fm prot"><b>${fr(per.p)} g</b><span>Protéines</span></div><div class="fm fat"><b>${fr(per.f)} g</b><span>Lipides</span></div></div>
          <button class="icon-btn star ${fav ? 'on' : ''}" data-act="nvFav" aria-label="Favori">${icon('star')}</button></div>
        <div class="row gap servings"><span class="grow"><b>Ingrédients</b></span><button class="icon-btn" data-act="nvServ" data-n="-1" aria-label="Moins">${icon('minus')}</button>
          <b>${s.data.servings} portion(s)</b><button class="icon-btn" data-act="nvServ" data-n="1" aria-label="Plus">${icon('plus')}</button></div>
        <ul class="entries ing">${r.items.map(([fid, g]) => { const bf = BASE.get('n:' + fid); return `<li><div class="grow"><b>${esc(bf ? bf.name : 'Ingrédient')}</b></div><span class="kc">${fr(g * k, 0)} g</span></li>`; }).join('')}</ul>
        ${r.steps.length ? `<h4 class="sec">Préparation</h4><ol class="steps">${r.steps.map(t => `<li>${esc(t)}</li>`).join('')}</ol>` : ''}
        <label class="field"><span>Ajouter au journal</span><select id="nvMeal">${MEALS.map(m => `<option value="${m.id}" ${m.id === s.data.meal ? 'selected' : ''}>${m.label}</option>`).join('')}</select></label>
        <div class="sheet-actions"><button class="btn ghost" data-act="nvShop">${icon('cart')}Courses</button><button class="btn ghost" data-act="nvCopy" title="Copier dans mes recettes pour la modifier">${icon('copy')}Copier</button>
        <button class="btn grow" data-act="nvLog">${icon('plus')}1 portion</button></div>`;
    }, { data: { r, servings: r.servings, meal: meal || defaultMeal() }, mount: s => { $('#nvMeal', s.el).addEventListener('change', e => { s.data.meal = e.target.value; }); } });
  }
  function addToShopping(items, source) {
    for (const [name, g] of items) {
      const ex = S.shopping.find(i => !i.done && N.norm(i.name) === N.norm(name));
      if (ex) { ex.g += g; if (!ex.from.includes(source)) ex.from.push(source); }
      else S.shopping.push({ id: uid(), name, g, done: false, from: [source] });
    }
    save();
  }
  function openShopping() {
    openSheet(() => {
      const todo = S.shopping.filter(i => !i.done), done = S.shopping.filter(i => i.done);
      const row = i => `<li class="shop ${i.done ? 'done' : ''}" data-act="shopToggle" data-id="${i.id}"><span class="check">${i.done ? icon('check') : ''}</span>
        <div class="grow"><b>${esc(i.name)}</b><span class="muted">${i.from.map(esc).join(', ')}</span></div><span class="kc">${i.g ? fr(i.g, 0) + ' g' : ''}</span></li>`;
      return sheetHead('Liste de courses', todo.length + ' article(s) à acheter') + `
        <div class="row gap"><input id="shopNew" class="grow field-input" placeholder="Ajouter un article"><button class="btn" data-act="shopAdd">${icon('plus')}</button></div>
        <ul class="entries">${todo.map(row).join('') || '<li class="empty">Ajoute des recettes ou des articles à ta liste.</li>'}</ul>
        ${done.length ? `<h4 class="sec">Dans le panier</h4><ul class="entries">${done.map(row).join('')}</ul>` : ''}
        <div class="sheet-actions">${done.length ? `<button class="btn ghost" data-act="shopClear">${icon('trash')}Retirer cochés</button>` : ''}
        <button class="btn grow" data-act="shopShare" ${todo.length ? '' : 'disabled'}>${icon('share')}${P.canShare() ? 'Partager' : 'Copier'} la liste</button></div>`;
    }, { live: true, mount: s => { const i = $('#shopNew', s.el); i.addEventListener('keydown', e => { if (e.key === 'Enter') A.shopAdd(); }); } });
  }

  /* ---------- Progression (ceintures, badges, défis) ---------- */
  function openProgress() {
    openSheet(() => {
      const gm = game();
      return sheetHead('Ma progression', kcal(gm.xp) + ' XP · série de ' + gm.streak + ' jour(s) · record ' + gm.best) + `
        <div class="belt-hero" style="--belt:${gm.belt.color}"><span class="belt-big">${icon('belt')}</span><div><b>Ceinture ${gm.belt.label.toLowerCase()}</b>
          <span class="muted">${gm.next ? kcal(gm.toNext) + ' XP avant la ceinture ' + gm.next.label.toLowerCase() : 'Grade maximum : respect.'}</span>
          <i class="belt-prog"><i style="width:${Math.round(gm.progress * 100)}%"></i></i>
          <span class="muted small">Bonus de série × ${gm.multiplier.toFixed(2).replace('.', ',')} (plafonné à × 1,5). Casser une série ne fait perdre aucun XP.</span></div></div>
        <h4 class="sec">Défis de la semaine</h4>
        <ul class="entries">${gm.quests.map(q => `<li><div class="grow"><b>${q.label}</b><i class="belt-prog q"><i style="width:${Math.round(q.ratio * 100)}%"></i></i></div><span class="kc ${q.done ? 'ok' : ''}">${q.done ? icon('check') : q.progress + '/' + q.target}</span><span class="muted small">+${q.reward}</span></li>`).join('')}</ul>
        <h4 class="sec">Badges (${gm.badges.size}/${E.BADGES.length})</h4>
        <div class="badges">${E.BADGES.map(b => `<div class="badge ${gm.badges.has(b.code) ? 'on' : ''}">${icon('trophy')}<b>${b.label}</b><span>${b.hint}</span></div>`).join('')}</div>
        <h4 class="sec">Grades</h4>
        <div class="belts">${E.BELTS.map(b => `<span class="belt-step ${gm.xp >= b.xp ? 'on' : ''}" style="--belt:${b.color}"><i></i>${b.label}<small>${kcal(b.xp)}</small></span>`).join('')}</div>
        <h4 class="sec">Barème</h4>
        <p class="muted small">${Object.entries(E.XP).map(([k, v]) => E.XP_LABELS[k] + ' +' + v).join(' · ')}. Seuls les comportements sont récompensés, jamais un déficit plus creux que prévu.</p>`;
    });
  }

  /* ---------- Catalogue hors ligne ---------- */
  function openCatalog() {
    openSheet(() => {
      const st = CAT.status();
      return sheetHead('Catalogue produits hors ligne', st.count.toLocaleString('fr-FR') + ' produits vendus en France · Open Food Facts') + `<div class="prose">
        <p>Le catalogue permet de chercher un produit de marque et de scanner un code-barres <b>sans connexion</b> : en avion, au sous-sol d'un gymnase, partout.</p>
        <ul><li>Téléchargement unique : <b>${st.sizeMb} Mo</b> (Wi-Fi conseillé), ${P.kind === 'android' ? st.dbMb : st.sizeMb} Mo une fois installé.</li>
        <li>Version des données : ${st.version ? pkey(st.version).toLocaleDateString('fr-FR') : '–'}. Chaque morceau est vérifié (empreinte SHA-256).</li>
        <li>Données Open Food Facts, licence ODbL. Les produits sortis après cette date restent trouvables en ligne.</li></ul>
        ${st.state === 'downloading' ? `<div class="dl"><i style="width:${Math.round(st.progress * 100)}%"></i></div><p class="muted">${esc(st.message)} ${Math.round(st.progress * 100)} %</p>` : ''}
        ${st.state === 'error' ? `<p class="warn-text">Échec : ${esc(st.message)}</p>` : ''}
        ${st.state === 'ready' ? `<p class="ok-text">${icon('check')} Installé${st.outdated ? ' (une version plus récente est disponible)' : ''}.</p>` : ''}
        ${st.sessionOnly ? '<p class="warn-text">Ce navigateur n\'a pas assez d\'espace pour le garder : il sera téléchargé à nouveau à la prochaine ouverture. L\'appli Android ou Windows le conserve.</p>' : ''}
      </div><div class="sheet-actions">
        ${st.state === 'ready' ? `<button class="btn ghost danger-text" data-act="catRemove">${icon('trash')}Supprimer</button>` : ''}
        ${st.state !== 'ready' || st.outdated ? `<button class="btn grow" data-act="catInstall" ${st.state === 'downloading' ? 'disabled' : ''}>${icon('download')}${st.state === 'downloading' ? 'Installation…' : st.outdated ? 'Mettre à jour' : 'Installer (' + st.sizeMb + ' Mo)'}</button>` : ''}
      </div>`;
    }, { live: true, onClose: () => setTimeout(render, 0) });
  }

  /* ---------- Analyse photo (Gemini, en ligne, facultative) ---------- */
  const GEMINI_MODELS = ['gemini-3.1-flash-lite', 'gemini-2.5-flash-lite', 'gemini-flash-lite-latest'];
  const GEMINI_PROMPT = `Tu es un nutritionniste qui estime le contenu d'une assiette à partir d'une photo.
Règles:
- Identifie chaque aliment distinct visible, séparément (pas "assiette composée"). Noms en français.
- Estime la masse en grammes avec les repères visibles (assiette ~26 cm, couverts, verre, main) et précise dans "note" le repère utilisé.
- Donne les valeurs POUR LA PORTION ESTIMÉE, pas pour 100 g.
- Les sauces, huiles de cuisson et matières grasses visibles comptent comme des aliments à part entière.
- confidence: 0.9 si l'aliment et la portion sont évidents, 0.5 si la portion est incertaine, 0.3 si l'aliment lui-même est ambigu.
- Si la photo ne contient pas de nourriture, renvoie une liste foods vide.
- Ne surestime pas : en cas de doute sur la portion, donne la fourchette basse et signale-le dans "note".`;
  const GEMINI_SCHEMA = { type: 'OBJECT', properties: { meal_guess: { type: 'STRING' }, foods: { type: 'ARRAY', items: { type: 'OBJECT',
    properties: { name: { type: 'STRING' }, grams: { type: 'NUMBER' }, kcal: { type: 'NUMBER' }, protein_g: { type: 'NUMBER' }, carbs_g: { type: 'NUMBER' },
      fat_g: { type: 'NUMBER' }, confidence: { type: 'NUMBER' }, note: { type: 'STRING' } },
    required: ['name', 'grams', 'kcal', 'protein_g', 'carbs_g', 'fat_g', 'confidence'] } } }, required: ['foods'] };
  async function geminiPost(body) {
    const key = S.settings.geminiKey;
    for (const model of GEMINI_MODELS) {
      const r = await fetch('https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent?key=' + encodeURIComponent(key),
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (r.status !== 404) return r;
    }
    return null;
  }
  async function googleMsg(r) { try { const j = await r.json(); return (j.error && j.error.message) || ''; } catch (e) { return ''; } }
  async function geminiAnalyze(b64, mime, hint) {
    let r;
    try {
      r = await geminiPost({ system_instruction: { parts: [{ text: GEMINI_PROMPT }] },
        contents: [{ role: 'user', parts: [{ text: hint ? 'Analyse ce repas. Indice de l\'utilisateur : ' + hint : 'Analyse ce repas.' }, { inline_data: { mime_type: mime, data: b64 } }] }],
        generationConfig: { temperature: 0.2, responseMimeType: 'application/json', responseSchema: GEMINI_SCHEMA } });
    } catch (e) { throw new Error('Pas de réseau. Saisis le repas à la main, tu pourras rescanner plus tard.'); }
    if (!r) throw new Error('Aucun modèle Gemini disponible actuellement. Saisis le repas à la main.');
    if (r.status === 429) throw new Error('Quota Gemini atteint pour aujourd\'hui. Saisie manuelle en attendant.');
    if (r.status === 400 || r.status === 403) throw new Error('Clé API refusée (' + r.status + '). ' + (await googleMsg(r)) + ' Vérifie-la dans Profil.');
    if (r.status >= 500) throw new Error('Gemini indisponible. Réessaie dans un moment.');
    if (!r.ok) throw new Error('Analyse échouée (' + r.status + '). ' + (await googleMsg(r)));
    let root;
    try { root = await r.json(); } catch (e) { throw new Error('Réponse de Gemini illisible.'); }
    const c = (root.candidates || [])[0];
    if (!c) throw new Error(root.promptFeedback && root.promptFeedback.blockReason ? 'Photo refusée par Gemini (' + root.promptFeedback.blockReason + '). Recadre sur l\'assiette seule.' : 'Aucun aliment reconnu sur cette photo.');
    let text = ((c.content || {}).parts || [{}])[0].text || '';
    text = text.trim().replace(/^```[a-zA-Z]*\n?/, '').replace(/```$/, '').trim();
    let payload;
    try { payload = JSON.parse(text); } catch (e) { throw new Error('Réponse de Gemini illisible. Réessaie, ou saisis le repas à la main.'); }
    const foods = (payload.foods || []).map(f => ({ name: String(f.name || 'Aliment').trim(), grams: +f.grams || 0, kcal: +f.kcal || 0, p: +f.protein_g || 0,
      c: +f.carbs_g || 0, f: +f.fat_g || 0, conf: Math.max(0, Math.min(1, +f.confidence || 0)), note: f.note || '' })).filter(f => f.kcal > 0 && f.grams > 0);
    if (!foods.length) throw new Error('Pas de nourriture détectée. Recadre l\'assiette de trois quarts, avec un couvert visible pour l\'échelle.');
    return { foods, guess: payload.meal_guess || '' };
  }
  function shrinkImage(file) {
    return new Promise((res, rej) => {
      const url = URL.createObjectURL(file), img = new Image();
      img.onload = () => {
        const max = 1280, k = Math.min(1, max / Math.max(img.width, img.height));
        const cv = document.createElement('canvas'); cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k);
        cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
        URL.revokeObjectURL(url);
        res(cv.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = () => { URL.revokeObjectURL(url); rej(new Error('Image illisible.')); };
      img.src = url;
    });
  }
  function openGeminiKey(after) {
    openSheet(() => sheetHead('Analyse photo des repas', 'Avec Gemini (Google), en ligne') + `<div class="prose">
      <p>Prends ton assiette en photo : chaque aliment est reconnu avec sa portion estimée, puis tu corriges avant d'ajouter.</p>
      <ul><li>Il faut une clé API gratuite Google AI Studio : <b>aistudio.google.com/apikey</b>. Elle reste enregistrée uniquement sur cet appareil.</li>
      <li>Palier gratuit : environ 1 000 analyses par jour, largement assez.</li>
      <li>Vie privée : sur le palier gratuit, Google peut utiliser tes photos pour améliorer ses modèles. Le reste de Calorys ne fait aucun envoi.</li></ul></div>
      <label class="field"><span>Clé API Gemini</span><input id="gemKey" value="${esc(S.settings.geminiKey)}" placeholder="AIza…" autocomplete="off" spellcheck="false"></label>
      <div class="sheet-actions">${S.settings.geminiKey ? `<button class="btn ghost danger-text" data-act="gemDel">${icon('trash')}Effacer</button>` : ''}
      <button class="btn ghost" data-act="gemTest">Tester</button><button class="btn grow" data-act="gemSave">${icon('check')}Enregistrer</button></div>`, { data: { after } });
  }
  function openPhotoReview(res, meal, dataUrl) {
    openSheet(s => {
      const d = s.data;
      const tot = d.items.reduce((a, x) => a + x.kcal * x.k, 0);
      return sheetHead('Repas détecté', (d.guess ? esc(d.guess) + ' · ' : '') + kcal(tot) + ' kcal · vérifie les portions') + `
        <img class="photo-prev" src="${d.img}" alt="">
        <ul class="entries ing">${d.items.map((x, i) => `<li><div class="grow"><b>${esc(x.name)}</b><span class="muted">${kcal(x.kcal * x.k)} kcal · P ${fr(x.p * x.k)} G ${fr(x.c * x.k)} L ${fr(x.f * x.k)}
          · <i class="conf c${x.conf >= 0.8 ? 3 : x.conf >= 0.5 ? 2 : 1}">${x.conf >= 0.8 ? 'sûr' : x.conf >= 0.5 ? 'portion incertaine' : 'à vérifier'}</i>${x.note ? ' · ' + esc(x.note) : ''}</span></div>
          <input class="g-input" inputmode="decimal" data-act="aiG" data-i="${i}" value="${fr(x.grams * x.k, 0)}" aria-label="Grammes"><span class="muted">g</span>
          <button class="icon-btn" data-act="aiDel" data-i="${i}" aria-label="Retirer">${icon('trash')}</button></li>`).join('')}</ul>
        <div class="row gap"><input id="aiHint" class="grow field-input" placeholder="Précision (ex. : riz complet, sans sauce)" value="${esc(d.hint || '')}"><button class="btn ghost" data-act="aiRetry">Réanalyser</button></div>
        <label class="field"><span>Repas</span><select id="aiMeal">${MEALS.map(m => `<option value="${m.id}" ${m.id === d.meal ? 'selected' : ''}>${m.label}</option>`).join('')}</select></label>
        <div class="sheet-actions"><button class="btn grow" data-act="aiAdd" ${d.items.length ? '' : 'disabled'}>${icon('check')}Ajouter ${d.items.length} aliment(s)</button></div>`;
    }, { data: { items: res.foods.map(x => Object.assign({ k: 1 }, x)), guess: res.guess, meal, img: dataUrl },
      mount: s => { $('#aiMeal', s.el).addEventListener('change', e => { s.data.meal = e.target.value; }); } });
  }
  async function runPhoto(file, meal, hint, sheet) {
    let dataUrl;
    try { dataUrl = await shrinkImage(file); } catch (e) { toast(e.message); return; }
    ui.lastPhoto = { file, meal };
    const wait = sheet || openSheet(() => sheetHead('Analyse en cours…', 'Gemini identifie les aliments') + `<img class="photo-prev" src="${dataUrl}" alt=""><div class="dl busy"><i></i></div>`);
    try {
      const res = await geminiAnalyze(dataUrl.split(',')[1], 'image/jpeg', hint);
      closeSheet(wait);
      openPhotoReview(res, meal, dataUrl);
    } catch (e) { closeSheet(wait); toast(e.message); }
  }

  /* ---------- Rapport du jour (imprimable / PDF) ---------- */
  function reportHtml(k) {
    const g = goals(), t = dayTotals(k), d = dayGet(k), w = S.weights.find(x => x.date === k);
    const row = (l, v) => `<div><span>${l}</span><b>${v}</b></div>`;
    let h = `<div class="report"><header><div><b>CALORYS</b><span>Rapport journalier</span></div><div class="r-date">${dayLabel(k)}<br>${pkey(k).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}</div></header>
      <div class="r-grid">${row('Calories', kcal(t.eaten) + ' / ' + kcal(g.kcal) + ' kcal')}${row('Brûlées', kcal(t.burned) + ' kcal')}${row('Eau', fr(t.water / 1000, 2) + ' L')}${w ? row('Poids', fr(w.kg) + ' kg') : ''}</div>
      <div class="r-grid">${row('Protéines', r0(t.n.p) + ' / ' + g.p + ' g')}${row('Glucides', r0(t.n.c) + ' / ' + g.c + ' g')}${row('Lipides', r0(t.n.f) + ' / ' + g.f + ' g')}${row('Fibres', fr(t.n.fi) + ' g')}</div>
      <h3>Journal alimentaire</h3>`;
    let any = false;
    for (const m of MEALS) {
      const list = d.meals[m.id] || [];
      if (!list.length) continue;
      any = true;
      h += `<h4>${m.label} <span>${kcal(list.reduce((a, e) => a + (e.n.e || 0), 0))} kcal</span></h4><table>${list.map(e => `<tr><td>${esc(e.name)}</td><td>${entryQty(e)}</td><td>P${r0(e.n.p)} G${r0(e.n.c)} L${r0(e.n.f)}</td><td>${kcal(e.n.e)} kcal</td></tr>`).join('')}</table>`;
    }
    if (!any) h += '<p>Rien de noté ce jour-là.</p>';
    h += '<h3>Sport</h3>' + ((d.acts || []).length ? `<table>${d.acts.map(a => `<tr><td>${esc(a.name)}</td><td>${a.min ? a.min + ' min' : ''}</td><td>${a.rpe ? 'RPE ' + a.rpe + '/10' : ''}</td><td>${kcal(a.kcal)} kcal</td></tr>`).join('')}</table>` : '<p>Aucune séance notée.</p>');
    const fasts = S.fasting.history.filter(f => dkey(new Date(f.end)) === k);
    if (fasts.length) h += '<h3>Jeûne</h3>' + fasts.map(f => `<p>${f.plan} : ${dur(f.end - f.start)}${f.end - f.start >= f.goalH * 3600000 ? ' (objectif atteint)' : ''}</p>`).join('');
    h += `<footer>${esc(S.profile.name || 'Calorys')} · généré le ${new Date().toLocaleString('fr-FR')}</footer></div>`;
    return h;
  }
  function openReport() {
    openSheet(() => sheetHead('Rapport du jour', dayLabel(ui.date)) + reportHtml(ui.date) + `
      <div class="sheet-actions"><button class="btn grow" data-act="printReport">${icon('download')}Imprimer / enregistrer en PDF</button></div>`, { full: true });
  }

  /* ---------- Rappels ---------- */
  function remindersPlan() {
    const r = S.settings.reminders, out = [];
    if (!r.on) return out;
    if (r.meals) {
      out.push({ id: 1, at: r.breakfast, title: 'Petit-déjeuner', text: 'Pense à noter ton petit-déjeuner dans Calorys.' });
      out.push({ id: 2, at: r.lunch, title: 'Déjeuner', text: 'Un déjeuner à noter ?' });
      out.push({ id: 3, at: r.dinner, title: 'Dîner', text: 'Note ton dîner pour boucler la journée.' });
    }
    if (r.water) ['10:30', '15:00', '17:30'].forEach((at, i) => out.push({ id: 10 + i, at, title: 'Hydratation', text: 'Un grand verre d\'eau ? Ton objectif t\'attend.' }));
    if (r.weigh) out.push({ id: 20, at: r.weighAt, title: 'Pesée du matin', text: 'À jeun, après les toilettes : seule la courbe lissée compte.' });
    return out;
  }
  function syncReminders() {
    const r = S.settings.reminders, F = S.fasting;
    const fastEnd = r.on && r.fastEnd && F.active ? F.active.start + parseInt(F.active.plan, 10) * 3600000 : 0;
    if (window.CalorysNative && window.CalorysNative.setReminders) {
      try { window.CalorysNative.setReminders(JSON.stringify({ daily: remindersPlan(), fastEnd })); } catch (e) { /* ignore */ }
    }
  }
  /* Windows et navigateur : rappels envoyés tant que l'appli est ouverte. */
  let lastTick = '';
  setInterval(() => {
    if (window.CalorysNative || !S.settings.reminders.on) return;
    const now = new Date(), hm = pad2(now.getHours()) + ':' + pad2(now.getMinutes()), stamp = today() + ' ' + hm;
    if (stamp === lastTick) return;
    lastTick = stamp;
    const due = remindersPlan().filter(x => x.at === hm);
    const F = S.fasting;
    if (S.settings.reminders.fastEnd && F.active) {
      const end = F.active.start + parseInt(F.active.plan, 10) * 3600000;
      if (Math.abs(Date.now() - end) < 30000) due.push({ title: 'Jeûne terminé', text: 'Objectif de ' + F.active.plan + ' atteint, bravo !' });
    }
    for (const x of due) notify(x.title, x.text);
  }, 20000);
  function notify(title, text) {
    if (P.kind === 'windows') { try { Neutralino.os.showNotification(title, text); } catch (e) { /* ignore */ } return; }
    if ('Notification' in window && Notification.permission === 'granted') { try { new Notification(title, { body: text, icon: 'img/icon-192.png' }); } catch (e) { /* ignore */ } }
  }
  function openReminders() {
    openSheet(s => {
      const r = s.data.r;
      const t = (id, v) => `<input type="time" id="${id}" value="${v}">`;
      return sheetHead('Rappels', P.kind === 'android' ? 'Notifications du téléphone' : 'Notifications tant que Calorys est ouvert') + `<div class="form">
        <label class="switch"><input type="checkbox" id="rOn" ${r.on ? 'checked' : ''}><span>Activer les rappels</span></label>
        <label class="switch"><input type="checkbox" id="rMeals" ${r.meals ? 'checked' : ''}><span>Repas</span></label>
        <div class="grid3"><label class="field"><span>Petit-déj</span>${t('rB', r.breakfast)}</label><label class="field"><span>Déjeuner</span>${t('rL', r.lunch)}</label><label class="field"><span>Dîner</span>${t('rD', r.dinner)}</label></div>
        <label class="switch"><input type="checkbox" id="rWater" ${r.water ? 'checked' : ''}><span>Eau (10 h 30, 15 h, 17 h 30)</span></label>
        <label class="switch"><input type="checkbox" id="rWeigh" ${r.weigh ? 'checked' : ''}><span>Pesée du matin</span></label>
        <label class="field"><span>Heure de la pesée</span>${t('rW', r.weighAt)}</label>
        <label class="switch"><input type="checkbox" id="rFast" ${r.fastEnd ? 'checked' : ''}><span>Fin du jeûne en cours</span></label>
      </div><div class="sheet-actions"><button class="btn grow" data-act="saveReminders">${icon('check')}Enregistrer</button></div>`;
    }, { data: { r: Object.assign({}, S.settings.reminders) } });
  }

  /* ---------- Export / sauvegarde ---------- */
  const csvNum = v => (v == null ? '' : String(Math.round(v * 100) / 100).replace('.', ','));
  const csvTxt = v => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
  function journalCsv() {
    const lines = ['Date;Repas;Aliment;Marque;Quantité (g);Énergie (kcal);Protéines (g);Glucides (g);dont sucres (g);Lipides (g);dont AG saturés (g);Fibres (g);Sel (g)'];
    for (const k of Object.keys(S.days).sort()) {
      const d = S.days[k];
      for (const m of MEALS) for (const e of d.meals[m.id] || []) {
        const n = e.n;
        lines.push([k, csvTxt(m.label), csvTxt(e.name), csvTxt(e.brand), csvNum(e.key === 'q' ? null : e.g), csvNum(n.e), csvNum(n.p), csvNum(n.c), csvNum(n.su), csvNum(n.f), csvNum(n.sa), csvNum(n.fi), csvNum(n.sl)].join(';'));
      }
      for (const a of d.acts || []) lines.push([k, csvTxt('Activité'), csvTxt(a.name), '', '', csvNum(-a.kcal), '', '', '', '', '', '', ''].join(';'));
    }
    return lines.join('\r\n');
  }
  function weightsCsv() {
    return ['Date;Poids (kg);IMC'].concat(S.weights.map(w => [w.date, csvNum(w.kg), csvNum(N.bmi(w.kg, S.profile.height))].join(';'))).join('\r\n');
  }
  const backupJson = () => JSON.stringify(Object.assign({ app: 'Calorys', appVersion: APP_VERSION, exportedAt: new Date().toISOString() }, S), null, 1);
  const stamp = () => today();
  async function doExport(name, mime, text) {
    try {
      const where = await P.exportFile(name, mime, text);
      if (where) {
        if (P.kind === 'android') toast('Enregistré dans ' + where, { label: 'Partager', fn: () => P.shareFile(name, mime, text) });
        else toast('Enregistré : ' + where);
      }
    } catch (e) { toast('Échec de l\'enregistrement : ' + e.message); }
  }
  async function restoreFrom(text) {
    let data;
    try { data = JSON.parse(text); } catch (e) { toast('Fichier invalide (JSON illisible).'); return; }
    if (!data || typeof data !== 'object' || !data.profile || !data.days) { toast('Ce fichier n\'est pas une sauvegarde Calorys.'); return; }
    const n = Object.keys(data.days).length;
    if (!(await confirmBox(`Restaurer cette sauvegarde (${n} jour(s) de journal${data.exportedAt ? ', du ' + new Date(data.exportedAt).toLocaleDateString('fr-FR') : ''}) ? Les données actuelles seront remplacées.`, 'Restaurer', true))) return;
    delete data.app; delete data.appVersion; delete data.exportedAt;
    S = migrate(data);
    P.save(S); await P.flush();
    applyTheme(); render(); toast('Sauvegarde restaurée.');
  }

  /* ---------- Thème ---------- */
  function applyTheme() {
    const t = S.settings.theme;
    const dark = t === 'dark' || (t === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = t === 'auto' ? '' : t;
    if (t === 'auto') delete document.documentElement.dataset.theme;
    P.setBars(dark, dark ? '#111814' : '#f4f7f5');
  }
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);

  /* ---------- Actions ---------- */
  const A = {
    close: () => closeSheet(),
    cfYes: () => topSheet().data.resolve(true),
    cfNo: () => topSheet().data.resolve(false),
    toastAction: () => { const t = $('#toast'); t.classList.remove('show'); if (t._action) t._action(); },
    day: el => { ui.date = addDays(ui.date, +el.dataset.n); render(); },
    addFood: el => openAddFood(el.dataset.meal),
    copyMeal: el => {
      const m = el.dataset.meal, src = dayGet(addDays(ui.date, -1)).meals[m] || [];
      const d = dayMut(ui.date);
      d.meals[m] = d.meals[m].concat(src.map(e => Object.assign({}, e, { id: uid() })));
      save(); render(); toast(src.length + ' aliment(s) repris d\'hier.');
    },
    setMeal: () => {},
    resTab: el => { const s = topSheet(); s.data.tab = el.dataset.tab; renderResults(s); },
    openFood: el => {
      const s = topSheet(), f = foodByKey(el.dataset.key) || (s.data.offRes || []).find(x => x.key === el.dataset.key);
      if (!f) return;
      openFood(f, { meal: s.data.meal, mode: s.data.mode, pick: s.data.pick });
    },
    quickLog: el => {
      const s = topSheet();
      let f = foodByKey(el.dataset.key);
      if (!f) { f = (s.data.offRes || []).find(x => x.key === el.dataset.key); if (f) { S.off[f.barcode] = f; } }
      if (!f) return;
      if (f.src === 'off') S.off[f.barcode] = f;
      const g = lastGrams(f.key);
      logFood(f, g, s.data.meal);
      render(); renderResults(s);
      toast(f.name.split(',')[0] + ' ajouté (' + fr(g, 0) + ' g)', { label: 'Annuler', fn: () => undoLast(s.data.meal) });
    },
    offSearch: async () => {
      const s = topSheet();
      s.data.offLoading = true; renderResults(s);
      try { s.data.offRes = await N.offSearch(s.data.q); s.data.offRes.forEach(f => tempFoods.set(f.key, f)); }
      catch (e) { toast('Recherche en ligne impossible (pas de connexion ?).'); s.data.offRes = null; }
      s.data.offLoading = false; renderResults(s);
    },
    fav: () => {
      const s = topSheet(), k = s.data.food.key;
      if (S.favs.includes(k)) S.favs = S.favs.filter(x => x !== k);
      else { S.favs.unshift(k); if (k.startsWith('o:')) S.off[s.data.food.barcode] = s.data.food; }
      save(); s.refresh();
    },
    preset: el => { const s = topSheet(); s.data.unit = 'g'; s.data.count = +el.dataset.g; s.refresh(); },
    confirmFood: () => {
      const s = topSheet(), { food, opts } = s.data;
      const q = sheetFoodGrams(s);
      if (!(q.g > 0)) { toast('Indique une quantité.'); return; }
      if (food.src === 'off') S.off[food.barcode] = food;
      if (opts.mode === 'pick' || opts.pick) {
        closeSheet(s);
        const add = sheets.find(x => x.data.pick);
        if (add) closeSheet(add);
        opts.pick(food, q.g);
        return;
      }
      if (opts.entry) {
        const d = dayMut(opts.day || ui.date);
        const fromMeal = opts.meal, toMeal = s.data.meal;
        const list = d.meals[fromMeal], i = list.findIndex(e => e.id === opts.entry.id);
        const ne = makeEntry(food, q.g, { id: opts.entry.id, pl: q.pl, pc: q.pc });
        if (fromMeal === toMeal) list[i] = ne; else { list.splice(i, 1); d.meals[toMeal].push(ne); }
        pushRecent(food.key, q.g);
        save(); closeSheet(s); render();
        return;
      }
      const d = dayMut(ui.date);
      d.meals[s.data.meal].push(makeEntry(food, q.g, { pl: q.pl, pc: q.pc }));
      pushRecent(food.key, q.g);
      save(); P.vibrate(12);
      closeSheet(s); render();
      toast(food.name.split(',')[0] + ' ajouté au ' + mealLabel(s.data.meal).toLowerCase(), { label: 'Annuler', fn: () => undoLast(s.data.meal) });
    },
    editEntry: el => {
      const d = dayGet(ui.date), e = (d.meals[el.dataset.meal] || []).find(x => x.id === el.dataset.id);
      if (!e) return;
      if (e.key === 'q') return openEditQuick(el.dataset.meal, e);
      const f = foodByKey(e.key) || { key: e.key, name: e.name, brand: e.brand, src: 'snapshot', per100: Object.fromEntries(N.NKEYS.map(k => [k, e.n[k] == null ? null : e.n[k] * 100 / e.g])) };
      openFood(f, { meal: el.dataset.meal, entry: e, day: ui.date });
    },
    delEntry: () => {
      const s = topSheet(), { opts } = s.data;
      const d = dayMut(opts.day || ui.date), list = d.meals[opts.meal], i = list.findIndex(e => e.id === opts.entry.id);
      const removed = list.splice(i, 1)[0];
      save(); closeSheet(s); render();
      toast('Aliment supprimé', { label: 'Annuler', fn: () => { list.splice(i, 0, removed); save(); render(); } });
    },
    quickAdd: () => openQuickAdd(topSheet().data.meal),
    saveQuick: () => {
      const s = topSheet(), g = id => num($('#' + id, s.el).value);
      const e = g('qaK');
      if (!(e > 0)) { toast('Indique les calories.'); return; }
      const n = {}; for (const k of N.NKEYS) n[k] = null;
      Object.assign(n, { e, c: g('qaC'), p: g('qaP'), f: g('qaF') });
      const entry = { id: s.data.entry ? s.data.entry.id : uid(), key: 'q', name: $('#qaName', s.el).value.trim() || 'Ajout rapide', brand: '', g: 0, n };
      const d = dayMut(ui.date), list = d.meals[s.data.meal];
      if (s.data.entry) list[list.findIndex(x => x.id === entry.id)] = entry; else list.push(entry);
      save();
      sheets.slice().forEach(x => closeSheet(x));
      render(); toast('Ajouté : ' + kcal(e) + ' kcal');
    },
    delQuick: () => {
      const s = topSheet(), list = dayMut(ui.date).meals[s.data.meal];
      list.splice(list.findIndex(x => x.id === s.data.entry.id), 1);
      save(); closeSheet(s); render();
    },
    newFood: () => {
      const s = topSheet();
      openCustomFood(null, null, s && s.data.mode ? f => openFood(f, { meal: s.data.meal, mode: s.data.mode, pick: s.data.pick }) : null);
    },
    editCustom: () => { const s = topSheet(); const f = S.foods.find(x => 'u:' + x.id === s.data.food.key); closeSheet(s); openCustomFood(f); },
    editCustomId: el => openCustomFood(S.foods.find(x => x.id === el.dataset.id)),
    saveCustom: () => {
      const s = topSheet(), v = readCustom(s);
      if (!v) return;
      let f = s.data.existing;
      if (f) Object.assign(f, v); else { f = Object.assign({ id: uid() }, v); S.foods.push(f); }
      if (v.barcode && S.off[v.barcode]) delete S.off[v.barcode];
      save(); closeSheet(s); render();
      toast('Aliment enregistré');
      if (s.data.after) s.data.after(foodByKey('u:' + f.id));
      else { const add = sheets.find(x => x.data.mode); if (add) renderResults(add); }
    },
    delCustom: async () => {
      const s = topSheet();
      if (!(await confirmBox('Supprimer cet aliment ? Les entrées déjà enregistrées dans le journal sont conservées.', 'Supprimer', true))) return;
      S.foods = S.foods.filter(x => x !== s.data.existing);
      S.favs = S.favs.filter(k => k !== 'u:' + s.data.existing.id);
      S.recents = S.recents.filter(r => r.key !== 'u:' + s.data.existing.id);
      save(); closeSheet(s); render();
    },
    delOff: el => { delete S.off[el.dataset.code]; S.favs = S.favs.filter(k => k !== 'o:' + el.dataset.code); save(); render(); },
    newRecipe: () => openRecipe(null),
    editRecipe: el => openRecipe(S.recipes.find(r => r.id === el.dataset.id)),
    ingAdd: () => {
      const rs = topSheet();
      openAddFood(null, { pick: (food, g) => { rs.data.r.items.push({ key: food.key, name: food.name, g, per100: food.per100 }); rs.refresh(); } });
    },
    ingDel: el => { const s = topSheet(); s.data.r.items.splice(+el.dataset.i, 1); s.refresh(); },
    saveRecipe: () => {
      const s = topSheet(), r = s.data.r;
      r.name = $('#rcName', s.el).value.trim();
      r.servings = Math.max(1, Math.round(num($('#rcServ', s.el).value) || 1));
      if (!r.name) { toast('Donne un nom à la recette.'); return; }
      if (!r.items.length) { toast('Ajoute au moins un ingrédient.'); return; }
      const i = S.recipes.findIndex(x => x.id === r.id);
      if (i >= 0) S.recipes[i] = r; else S.recipes.push(r);
      save(); closeSheet(s); render(); toast('Recette enregistrée');
      const add = sheets.find(x => x.data.mode === 'log');
      if (add) { add.data.tab = 'recipes'; add.data.q = ''; add.refresh(); }
    },
    delRecipe: async () => {
      const s = topSheet();
      if (!(await confirmBox('Supprimer cette recette ?', 'Supprimer', true))) return;
      S.recipes = S.recipes.filter(r => r.id !== s.data.r.id);
      save(); closeSheet(s); render();
    },
    scan: () => { const s = topSheet(); openScanner(s.data.meal, { pick: s.data.pick }); },
    scanManual: () => { const s = topSheet(); const v = $('#scanCode', s.el).value; if (v.replace(/\D/g, '').length >= 6) onCode(s, v); else toast('Code-barres trop court.'); },
    scanPhoto: () => { const inp = $('#photoInput'); inp.value = ''; inp.click(); },
    cup: el => {
      const i = +el.dataset.i, glass = S.profile.glass, d = dayMut(ui.date);
      const filled = Math.floor(d.water / glass);
      d.water = (i + 1 === filled ? i : i + 1) * glass;
      save(); render(); P.vibrate(8);
    },
    water: el => { const d = dayMut(ui.date); d.water = Math.max(0, d.water + (+el.dataset.n) * S.profile.glass); save(); render(); P.vibrate(8); },
    addActivity: () => openActivity(null),
    editActivity: el => openActivity((dayGet(ui.date).acts || []).find(a => a.id === el.dataset.id)),
    pickAct: el => { const s = topSheet(); s.data.sel = el.dataset.name; s.data.k = null; s.refresh(); },
    actMode: el => { const s = topSheet(); s.data.mode = el.dataset.m; s.data.sel = null; s.data.k = null; s.refresh(); },
    saveAct: () => {
      const s = topSheet(), d = dayMut(ui.date), w = currentWeight();
      let rec;
      if (s.data.mode === 'session') {
        const x = E.SESSIONS.find(y => y.name === s.data.sel);
        if (!x || !(s.data.min > 0)) { toast('Indique la durée de la séance.'); return; }
        rec = { id: s.data.existing ? s.data.existing.id : uid(), name: x.name, session: true, min: s.data.min, rpe: s.data.rpe,
          kcal: E.sessionKcal(x.met, s.data.min, w, s.data.rpe), sweat: E.sweatMl(x.sweat, s.data.min, s.data.rpe) };
      } else {
        const a = N.ACTIVITIES.find(x => x.name === s.data.sel);
        const k = s.data.k || (a ? N.activityKcal(a.met, s.data.min, w) : 0);
        if (!k) { toast('Indique une durée ou des calories.'); return; }
        rec = { id: s.data.existing ? s.data.existing.id : uid(), name: s.data.sel || 'Activité', min: s.data.k ? 0 : s.data.min, kcal: k };
      }
      const i = d.acts.findIndex(x => x.id === rec.id);
      if (i >= 0) d.acts[i] = rec; else d.acts.push(rec);
      save(); closeSheet(s); render();
    },
    delAct: () => { const s = topSheet(), d = dayMut(ui.date); d.acts = d.acts.filter(a => a.id !== s.data.existing.id); save(); closeSheet(s); render(); },
    addWeight: () => openWeight(),
    saveWeight: () => {
      const s = topSheet(), kg = num($('#wKg', s.el).value), date = $('#wDate', s.el).value || today();
      if (!(kg > 20 && kg < 400)) { toast('Poids invalide.'); return; }
      const waist = num($('#wWaist', s.el).value);
      const rec = { date, kg };
      if (waist > 30 && waist < 250) rec.waist = waist;
      S.weights = S.weights.filter(w => w.date !== date).concat([rec]).sort((a, b) => a.date < b.date ? -1 : 1);
      save(); closeSheet(s); render();
      const diff = S.weights.length > 1 ? kg - S.weights[S.weights.length - 2].kg : 0;
      toast('Pesée enregistrée' + (diff ? ' (' + (diff > 0 ? '+' : '') + fr(diff) + ' kg)' : ''));
    },
    delWeight: el => {
      const w = S.weights.find(x => x.date === el.dataset.date);
      S.weights = S.weights.filter(x => x !== w); save(); render();
      toast('Pesée supprimée', { label: 'Annuler', fn: () => { S.weights.push(w); S.weights.sort((a, b) => a.date < b.date ? -1 : 1); save(); render(); } });
    },
    fastPlan: el => { S.fasting.plan = el.dataset.plan; save(); render(); },
    fastStart: () => { S.fasting.active = { start: Date.now(), plan: S.fasting.plan }; save(); render(); syncReminders(); P.vibrate(20); },
    fastStop: async () => {
      const F = S.fasting, a = F.active, el = Date.now() - a.start, goalH = parseInt(a.plan, 10);
      if (el < goalH * 3600000 && !(await confirmBox('Arrêter le jeûne avant l\'objectif de ' + goalH + ' h ?', 'Arrêter'))) return;
      if (el > 10 * 60000) F.history.push({ start: a.start, end: Date.now(), plan: a.plan, goalH });
      F.active = null; save(); render(); syncReminders();
      toast(el >= goalH * 3600000 ? 'Bravo, objectif de jeûne atteint !' : 'Jeûne arrêté après ' + dur(el));
    },
    fastEdit: () => {
      const st = new Date(S.fasting.active.start);
      const v = st.getFullYear() + '-' + pad2(st.getMonth() + 1) + '-' + pad2(st.getDate()) + 'T' + pad2(st.getHours()) + ':' + pad2(st.getMinutes());
      openSheet(() => sheetHead('Début du jeûne') + `<label class="field"><span>Date et heure</span><input id="fsT" type="datetime-local" value="${v}"></label>
        <div class="sheet-actions"><button class="btn grow" data-act="fastEditSave">${icon('check')}Enregistrer</button></div>`);
    },
    fastEditSave: () => {
      const s = topSheet(), t = new Date($('#fsT', s.el).value).getTime();
      if (!t || t > Date.now()) { toast('Date invalide.'); return; }
      S.fasting.active.start = t; save(); closeSheet(s); render(); syncReminders();
    },
    fastDel: el => { S.fasting.history.splice(+el.dataset.i, 1); save(); render(); },
    range: el => { ui.statsRange = +el.dataset.r; render(); },
    editProfile: () => openProfile(),
    pfSet: el => { const s = topSheet(); readProfileForm(s); s.data.p[el.dataset.k] = el.dataset.v; s.refresh(); },
    saveProfile: () => {
      const s = topSheet(); readProfileForm(s);
      const oldGoal = S.profile.goal, np = s.data.p;
      if (np.goal !== oldGoal && S.profile.preset === presetFor(oldGoal)) np.preset = presetFor(np.goal);
      if (np.goal === 'cut' && !np.weighIn) np.weighIn = addDays(today(), 42);
      S.profile = Object.assign(S.profile, np);
      save(); closeSheet(s); render(); toast('Profil mis à jour');
    },
    editGoals: () => openGoals(),
    saveGoals: () => {
      const s = topSheet(); s.data.keep();
      const d = s.data, p = S.profile;
      p.kcalOverride = d.override ? Math.round(d.kcal) : null;
      p.adaptive = d.adaptive; p.preset = d.preset; p.split = d.split; p.exercisePct = d.exPct; p.waterAuto = d.waterAuto;
      p.waterGoal = Math.round(d.water); p.glass = Math.round(d.glass); p.stepsGoal = Math.round(d.steps);
      save(); closeSheet(s); render(); toast('Objectifs enregistrés');
    },
    manageFoods: () => openManageFoods(),
    about: () => openAbout(),
    exportCsv: () => doExport('calorys-journal-' + stamp() + '.csv', 'text/csv', journalCsv()),
    exportWeights: () => doExport('calorys-poids-' + stamp() + '.csv', 'text/csv', weightsCsv()),
    backup: () => doExport('calorys-sauvegarde-' + stamp() + '.json', 'application/json', backupJson()),
    shareBackup: () => P.shareFile('calorys-sauvegarde-' + stamp() + '.json', 'application/json', backupJson()).catch(() => {}),
    restore: () => { const i = $('#fileInput'); i.value = ''; i.click(); },
    openFolder: () => P.openFolder(),
    reset: async () => {
      if (!(await confirmBox('Effacer définitivement toutes tes données (journal, poids, aliments, recettes) ? Pense à faire une sauvegarde avant.', 'Tout effacer', true))) return;
      S = defaults(); ui.ob = null; ui.obStep = 0; ui.tab = 'journal';
      P.save(S); await P.flush(); render();
    },
    obNext: () => { readOb(); ui.obStep++; render(); window.scrollTo(0, 0); },
    obBack: () => { readOb(); ui.obStep--; render(); },
    obSet: el => { readOb(); const v = el.dataset.v; ui.ob[el.dataset.k] = isNaN(+v) ? v : +v; render(); },
    obDone: () => {
      readOb();
      S.profile = Object.assign(S.profile, ui.ob, { onboarded: true, preset: presetFor(ui.ob.goal) });
      if (!S.weights.length) S.weights.push({ date: today(), kg: ui.ob.weight });
      ui.ob = null; save(); render();
    }
  };
  Object.assign(A, {
    progress: () => openProgress(),
    cutInfo: () => {
      const g = goals(), c = g.cut;
      openSheet(() => sheetHead('Pesée officielle', 'J-' + c.days + ' · le ' + pkey(S.profile.weighIn).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })) + `
        <div class="stats-grid"><div><span class="muted">À perdre</span><b>${fr(Math.max(0, c.toLose))} kg</b></div><div><span class="muted">Rythme nécessaire</span><b>${fr(c.required, 2)} kg/sem</b></div>
        <div><span class="muted">Rythme sain max</span><b>${fr(c.safe, 2)} kg/sem</b></div><div><span class="muted">Cible du jour</span><b>${kcal(g.kcal)} kcal</b></div></div>
        <p class="verdict">${esc(c.message)}</p><ul class="notes">${c.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>
        <div class="sheet-actions"><button class="btn ghost grow" data-act="editProfile">${icon('edit')}Modifier la date ou la catégorie</button></div>`);
    },
    report: () => openReport(),
    printReport: () => {
      document.body.classList.add('printing');
      const done = () => setTimeout(() => document.body.classList.remove('printing'), 500);
      if (window.CalorysNative && window.CalorysNative.printPage) { window.CalorysNative.printPage('Calorys-rapport-' + ui.date); setTimeout(() => document.body.classList.remove('printing'), 4000); }
      else { window.print(); done(); }
    },
    rtag: el => { ui.rtag = el.dataset.tag; render(); },
    nvRecipe: el => openNvRecipe(el.dataset.id),
    nvServ: el => { const s = topSheet(); s.data.servings = Math.max(1, s.data.servings + (+el.dataset.n)); s.refresh(); },
    nvFav: () => {
      const s = topSheet(), id = s.data.r.id;
      S.favRecipes = S.favRecipes.includes(id) ? S.favRecipes.filter(x => x !== id) : [id].concat(S.favRecipes);
      save(); s.refresh(); render();
    },
    nvLog: () => {
      const s = topSheet(), f = foodByKey('nr:' + s.data.r.id), p = f.portions[0];
      const d = dayMut(ui.date);
      d.meals[s.data.meal].push(makeEntry(f, p.g, { pl: p.l, pc: 1 }));
      pushRecent(f.key, p.g); save(); P.vibrate(12);
      closeSheet(s); render();
      toast(s.data.r.name + ' ajouté au ' + mealLabel(s.data.meal).toLowerCase(), { label: 'Annuler', fn: () => undoLast(s.data.meal) });
    },
    nvShop: () => {
      const s = topSheet(), r = s.data.r, k = s.data.servings / r.servings;
      addToShopping(r.items.map(([fid, g]) => [(BASE.get('n:' + fid) || { name: 'Ingrédient' }).name, Math.round(g * k)]), r.name);
      toast(r.items.length + ' ingrédient(s) ajouté(s) à la liste de courses', { label: 'Voir', fn: openShopping });
    },
    nvCopy: () => {
      const s = topSheet(), r = s.data.r;
      const copy = { id: uid(), name: r.name, servings: r.servings, items: r.items.map(([fid, g]) => { const bf = BASE.get('n:' + fid); return bf ? { key: bf.key, name: bf.name, g, per100: bf.per100 } : null; }).filter(Boolean) };
      closeSheet(s); openRecipe(null); const rs = topSheet(); rs.data.r = copy; rs.data.existing = null; rs.refresh();
    },
    shopping: () => openShopping(),
    shopToggle: el => { const i = S.shopping.find(x => x.id === el.dataset.id); if (i) { i.done = !i.done; save(); topSheet().refresh(); render(); } },
    shopAdd: () => {
      const s = topSheet(), inp = $('#shopNew', s.el), v = inp.value.trim();
      if (!v) return;
      S.shopping.push({ id: uid(), name: v, g: 0, done: false, from: ['ajout manuel'] }); save(); s.refresh(); render();
      const n = $('#shopNew', topSheet().el); if (n) n.focus();
    },
    shopClear: () => { S.shopping = S.shopping.filter(i => !i.done); save(); topSheet().refresh(); render(); },
    shopShare: async () => {
      const txt = 'Liste de courses Calorys\n' + S.shopping.filter(i => !i.done).map(i => '- ' + i.name + (i.g ? ' (' + fr(i.g, 0) + ' g)' : '')).join('\n');
      if (P.canShare()) { try { await P.shareFile('liste-de-courses.txt', 'text/plain', txt); } catch (e) { /* annulé */ } }
      else { try { await navigator.clipboard.writeText(txt); toast('Liste copiée'); } catch (e) { toast('Copie impossible'); } }
    },
    catalog: () => openCatalog(),
    catInstall: () => { CAT.install().then(() => toast('Catalogue installé : ' + CAT.status().count.toLocaleString('fr-FR') + ' produits hors ligne')).catch(e => toast('Échec de l\'installation : ' + e.message)); },
    catRemove: async () => {
      if (!(await confirmBox('Supprimer le catalogue hors ligne ? Tu pourras le réinstaller plus tard.', 'Supprimer', true))) return;
      await CAT.remove(); toast('Catalogue supprimé');
    },
    photoAi: () => {
      const s = topSheet(), meal = s && s.data.meal ? s.data.meal : defaultMeal();
      if (!S.settings.geminiKey) { openGeminiKey(() => A.photoAi()); return; }
      ui.photoMeal = meal;
      const inp = $('#aiPhotoInput'); inp.value = ''; inp.click();
    },
    gemini: () => openGeminiKey(),
    gemSave: () => {
      const s = topSheet(); S.settings.geminiKey = $('#gemKey', s.el).value.trim(); save(); closeSheet(s); render();
      toast(S.settings.geminiKey ? 'Clé enregistrée' : 'Clé effacée');
      if (S.settings.geminiKey && s.data.after) s.data.after();
    },
    gemDel: () => { const s = topSheet(); S.settings.geminiKey = ''; save(); closeSheet(s); render(); toast('Clé effacée'); },
    gemTest: async () => {
      const s = topSheet(), key = $('#gemKey', s.el).value.trim();
      if (!key) { toast('Colle d\'abord ta clé.'); return; }
      const old = S.settings.geminiKey; S.settings.geminiKey = key;
      try {
        const r = await geminiPost({ contents: [{ role: 'user', parts: [{ text: 'Réponds uniquement le mot OK.' }] }] });
        if (!r) toast('Aucun modèle Gemini disponible actuellement.');
        else if (r.ok) toast('Clé valide : l\'analyse photo est prête.');
        else toast('Clé refusée (' + r.status + '). ' + (await googleMsg(r)));
      } catch (e) { toast('Pas de réseau.'); }
      S.settings.geminiKey = old;
    },
    aiDel: el => { const s = topSheet(); s.data.items.splice(+el.dataset.i, 1); s.refresh(); },
    aiRetry: () => {
      const s = topSheet(); const hint = $('#aiHint', s.el).value.trim();
      if (!ui.lastPhoto) return;
      closeSheet(s); runPhoto(ui.lastPhoto.file, s.data.meal, hint);
    },
    aiAdd: () => {
      const s = topSheet(), d = dayMut(ui.date);
      for (const x of s.data.items) {
        const n = {}; for (const k of N.NKEYS) n[k] = null;
        Object.assign(n, { e: Math.round(x.kcal * x.k), p: Math.round(x.p * x.k * 10) / 10, c: Math.round(x.c * x.k * 10) / 10, f: Math.round(x.f * x.k * 10) / 10 });
        d.meals[s.data.meal].push({ id: uid(), key: 'ai', name: x.name, brand: 'Photo IA', g: Math.round(x.grams * x.k), n, ai: true });
      }
      save(); P.vibrate(15);
      sheets.slice().forEach(x => closeSheet(x)); render();
      toast(s.data.items.length + ' aliment(s) ajouté(s) au ' + mealLabel(s.data.meal).toLowerCase());
    },
    reminders: () => openReminders(),
    saveReminders: async () => {
      const s = topSheet(), g = id => $('#' + id, s.el);
      const r = { on: g('rOn').checked, meals: g('rMeals').checked, breakfast: g('rB').value || '08:00', lunch: g('rL').value || '12:30', dinner: g('rD').value || '19:30',
        water: g('rWater').checked, weigh: g('rWeigh').checked, weighAt: g('rW').value || '07:30', fastEnd: g('rFast').checked };
      S.settings.reminders = r; save(); closeSheet(s);
      if (r.on && P.kind === 'web' && 'Notification' in window && Notification.permission === 'default') { try { await Notification.requestPermission(); } catch (e) { /* ignore */ } }
      syncReminders(); render(); toast(r.on ? 'Rappels activés' : 'Rappels désactivés');
    },
    gameToggle: () => { S.settings.game = !S.settings.game; save(); render(); }
  });
  function undoLast(meal) {
    const d = dayMut(ui.date);
    d.meals[meal].pop(); save(); render();
  }
  function openEditQuick(meal, e) {
    openSheet(() => sheetHead('Ajout rapide', mealLabel(meal)) + `<div class="form">
      <label class="field"><span>Nom</span><input id="qaName" value="${esc(e.name)}"></label>
      <label class="field"><span>Calories (kcal)</span><input id="qaK" inputmode="decimal" value="${r0(e.n.e)}"></label>
      <div class="grid3"><label class="field"><span>Glucides (g)</span><input id="qaC" inputmode="decimal" value="${e.n.c == null ? '' : fr(e.n.c)}"></label>
      <label class="field"><span>Protéines (g)</span><input id="qaP" inputmode="decimal" value="${e.n.p == null ? '' : fr(e.n.p)}"></label>
      <label class="field"><span>Lipides (g)</span><input id="qaF" inputmode="decimal" value="${e.n.f == null ? '' : fr(e.n.f)}"></label></div></div>
      <div class="sheet-actions"><button class="btn ghost danger-text" data-act="delQuick">${icon('trash')}Supprimer</button><button class="btn grow" data-act="saveQuick">${icon('check')}Enregistrer</button></div>`,
    { data: { meal, entry: e } });
  }

  /* ---------- Événements ---------- */
  document.addEventListener('click', e => {
    const tab = e.target.closest('#tabbar [data-tab]');
    if (tab) { ui.tab = tab.dataset.tab; render(); $('#view').scrollTop = 0; window.scrollTo(0, 0); return; }
    const el = e.target.closest('[data-act]');
    if (!el || el.tagName === 'SELECT' || (el.tagName === 'INPUT' && el.type !== 'button')) return;
    const fn = A[el.dataset.act];
    if (fn) { e.preventDefault(); fn(el, e); }
  });
  document.addEventListener('change', e => {
    const el = e.target;
    const act = el.dataset && el.dataset.act;
    if (act === 'pickDay' && el.value) { ui.date = el.value; render(); }
    if (act === 'setMeal') topSheet().data.meal = el.value;
    if (act === 'theme') { S.settings.theme = el.value; save(); applyTheme(); }
    if (act === 'steps') { const d = dayMut(ui.date); d.steps = Math.max(0, Math.round(num(el.value) || 0)); save(); render(); }
    if (act === 'gameToggleIn') { S.settings.game = el.checked; save(); render(); }
    if (act === 'aiG') { const s = topSheet(), x = s.data.items[+el.dataset.i]; const g = num(el.value); if (g > 0) { x.k = g / x.grams; s.refresh(); } }
    if (act === 'ingG') { const s = topSheet(); s.data.r.items[+el.dataset.i].g = num(el.value) || 0; s.refresh(); }
  });
  $('#fileInput').addEventListener('change', async e => { const f = e.target.files[0]; if (f) restoreFrom(await f.text()); });
  $('#aiPhotoInput').addEventListener('change', e => { const f = e.target.files[0]; if (f) runPhoto(f, ui.photoMeal || defaultMeal()); });
  document.addEventListener('input', e => {
    if (e.target.id !== 'rcQ') return;
    ui.rq = e.target.value; const pos = e.target.selectionStart; render();
    const q = $('#rcQ'); if (q) { q.focus(); try { q.setSelectionRange(pos, pos); } catch (er) { /* ignore */ } }
  });
  $('#photoInput').addEventListener('change', e => { const f = e.target.files[0]; const s = sheets.find(x => x.el.querySelector('#scanVideo')); if (f && s) decodePhoto(f, s); });

  document.addEventListener('keydown', e => {
    const typing = /INPUT|SELECT|TEXTAREA/.test((document.activeElement || {}).tagName || '');
    if (e.key === 'Escape') { if (sheets.length) { closeSheet(); e.preventDefault(); } return; }
    if (!S.profile.onboarded) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); A.backup(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); if (!sheets.length) openAddFood(defaultMeal()); else { const q = $('#foodQ'); if (q) q.focus(); } return; }
    if (typing || sheets.length || e.ctrlKey || e.metaKey || e.altKey) return;
    if (ui.tab === 'journal' && e.key === 'ArrowLeft') { ui.date = addDays(ui.date, -1); render(); }
    else if (ui.tab === 'journal' && e.key === 'ArrowRight') { ui.date = addDays(ui.date, 1); render(); }
    else if (e.key === 'n' || e.key === '+') { e.preventDefault(); ui.tab = 'journal'; render(); openAddFood(defaultMeal()); }
    else if (e.key === 't') { ui.date = today(); ui.tab = 'journal'; render(); }
  });
  document.addEventListener('dragover', e => { e.preventDefault(); });
  document.addEventListener('drop', async e => {
    e.preventDefault();
    const f = e.dataTransfer && e.dataTransfer.files[0];
    if (f && /\.json$/i.test(f.name)) restoreFrom(await f.text());
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) P.flush();
    else if (ui.date !== today() && S.profile.onboarded && !sheets.length && ui._lastToday && ui._lastToday !== today()) { ui.date = today(); render(); }
    ui._lastToday = today();
  });
  window.addEventListener('pagehide', () => P.flush());

  /* Bouton retour Android : renvoie true si l'appli a géré l'action. */
  window.calorysBack = function () {
    if (sheets.length) { closeSheet(); return true; }
    if (S.profile.onboarded && ui.tab !== 'journal') { ui.tab = 'journal'; render(); return true; }
    if (!S.profile.onboarded && ui.obStep > 0) { A.obBack(); return true; }
    return false;
  };

  /* ---------- Démarrage ---------- */
  async function boot() {
    try { await P.init(); } catch (e) { console.error(e); }
    try { S = migrate(await P.load()); } catch (e) { console.error(e); S = defaults(); }
    ui._lastToday = today();
    applyTheme();
    CAT.onChange(() => {
      for (const sh of sheets) { if (sh.opts.live) sh.refresh(); else if ($('#results', sh.el)) { sh.data.catQ = null; renderResults(sh); } }
      if (ui.tab === 'profile' && !sheets.length) render();
    });
    try { await CAT.init(); } catch (e) { console.error(e); }
    render();
    syncReminders();
    const sp = $('#splash');
    sp.classList.add('hide'); setTimeout(() => sp.remove(), 400);
    if ('serviceWorker' in navigator && P.kind === 'web' && location.protocol === 'https:') navigator.serviceWorker.register('sw.js').catch(() => {});
  }
  window.CalorysDebug = { get state() { return S; }, ui, render };
  boot();
})();
