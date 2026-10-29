/* Calorys : application principale (journal, jeûne, analyse, profil). */
(function () {
  'use strict';
  const N = window.Nutrition, C = window.Charts, P = window.Platform;
  const APP_VERSION = '1.0.0';
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
    food: 'M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10M17 3c-2 2-3 5-3 8h3v10'
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
        goal: 'lose', pace: 0.5, split: { c: 50, p: 20, f: 30 }, kcalOverride: null, waterGoal: 2000, glass: 250,
        addExercise: true, stepsGoal: 8000 },
      days: {}, weights: [], foods: [], recipes: [], off: {}, favs: [], recents: [],
      fasting: { plan: '16:8', active: null, history: [] },
      settings: { theme: 'auto' }
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
    return out;
  }

  let S = defaults();
  const ui = { tab: 'journal', date: today(), statsRange: 7, ob: null, obStep: 0 };
  let saveTimer = null;
  function save() { clearTimeout(saveTimer); saveTimer = setTimeout(() => P.save(S), 250); }

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
  function goals() {
    const p = Object.assign({}, S.profile, { weight: currentWeight() });
    const g = N.computeGoal(p);
    const k = S.profile.kcalOverride || g.kcal;
    return Object.assign({ kcal: k, calc: g.kcal, bmr: g.bmr, tdee: g.tdee }, N.macroGoals(k, S.profile.split));
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

  /* ---------- Aliments ---------- */
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
    if (t === 'o:') return S.off[id] || null;
    if (t === 'r:') { const r = S.recipes.find(x => x.id === id); return r ? recipeFood(r) : null; }
    return null;
  }
  function extraFoods() {
    return S.foods.map(f => Object.assign({ key: 'u:' + f.id, src: 'custom' }, f))
      .concat(Object.values(S.off))
      .concat(S.recipes.map(recipeFood));
  }
  function foodSub(f) {
    const parts = [];
    if (f.brand) parts.push(f.brand);
    else if (f.src === 'ciqual') parts.push(f.group);
    else if (f.src === 'custom') parts.push('Mon aliment');
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
    const view = $('#view');
    document.body.classList.toggle('onboarding', !S.profile.onboarded);
    if (!S.profile.onboarded) { view.innerHTML = renderOnboarding(); return; }
    document.querySelectorAll('#tabbar [data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === ui.tab));
    const fn = { journal: renderJournal, fasting: renderFasting, stats: renderStats, profile: renderProfile }[ui.tab];
    view.innerHTML = fn();
    for (const s of sheets) if (s.opts.live) s.refresh();
  }

  /* ---------- Journal ---------- */
  function renderJournal() {
    const g = goals(), t = dayTotals(ui.date), d = dayGet(ui.date);
    const burned = S.profile.addExercise ? t.burned : 0;
    const left = g.kcal - t.eaten + burned;
    const pct = t.eaten / (g.kcal + burned || 1);
    const macro = (k, label, cls) => {
      const v = t.n[k], goal = g[k];
      return `<div class="macro ${cls}"><div class="macro-top"><span>${label}</span><span><b>${r0(v)}</b> / ${goal} g</span></div>
        <div class="bar"><i style="width:${Math.min(100, v / goal * 100)}%"></i></div></div>`;
    };
    let h = `<div class="topbar"><button class="icon-btn" data-act="day" data-n="-1" aria-label="Jour précédent">${icon('chevL')}</button>
      <label class="day-label"><span>${dayLabel(ui.date)}</span><input type="date" value="${ui.date}" data-act="pickDay" aria-label="Choisir une date"></label>
      <button class="icon-btn" data-act="day" data-n="1" aria-label="Jour suivant">${icon('chevR')}</button></div>`;
    h += `<section class="card summary">
      <div class="sum-side"><b>${kcal(t.eaten)}</b><span>mangées</span></div>
      <div class="sum-ring ${left < 0 ? 'over' : ''}">${C.ring(pct, 168, 14)}<div class="ring-center"><b>${kcal(Math.abs(left))}</b><span>${left < 0 ? 'en trop' : 'restantes'}</span></div></div>
      <div class="sum-side"><b>${kcal(t.burned)}</b><span>brûlées</span></div>
      <div class="macros">${macro('c', 'Glucides', 'carb')}${macro('p', 'Protéines', 'prot')}${macro('f', 'Lipides', 'fat')}</div>
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
    const glass = S.profile.glass, wg = S.profile.waterGoal;
    const nG = Math.max(1, Math.ceil(wg / glass)), filled = Math.floor(t.water / glass);
    let cups = '';
    for (let i = 0; i < Math.max(nG, filled + 1); i++) cups += `<button class="cup ${i < filled ? 'full' : ''}" data-act="cup" data-i="${i}" aria-label="Verre ${i + 1}">${icon('drop')}</button>`;
    h += `<section class="card water"><header class="meal-head"><span class="meal-ic water">${icon('drop')}</span>
      <div class="grow"><h3>Eau</h3><p class="muted">${fr(t.water / 1000, 2)} / ${fr(wg / 1000, 2)} L</p></div>
      <button class="icon-btn" data-act="water" data-n="-1" aria-label="Retirer un verre">${icon('minus')}</button>
      <button class="add-btn" data-act="water" data-n="1" aria-label="Ajouter un verre">${icon('plus')}</button></header>
      <div class="cups">${cups}</div></section>`;
    const w = currentWeight();
    h += `<section class="card"><header class="meal-head"><span class="meal-ic act">${icon('run')}</span>
      <div class="grow"><h3>Activités</h3><p class="muted">${kcal(t.burned)} kcal brûlées${S.profile.addExercise ? '' : ' (non ajoutées à l\'objectif)'}</p></div>
      <button class="add-btn" data-act="addActivity" aria-label="Ajouter une activité">${icon('plus')}</button></header>
      <ul class="entries">${(d.acts || []).map(a => `<li data-act="editActivity" data-id="${a.id}"><div class="grow"><b>${esc(a.name)}</b><span class="muted">${a.min ? a.min + ' min' : 'saisie manuelle'}</span></div><span class="kc">${kcal(a.kcal)}</span></li>`).join('')}
      <li class="steps"><div class="grow"><b>Pas</b><span class="muted">objectif ${S.profile.stepsGoal.toLocaleString('fr-FR')}${d.steps ? ' · ' + kcal(N.stepsKcal(d.steps, w)) + ' kcal' : ''}</span></div>
      <input class="steps-input" inputmode="numeric" data-act="steps" value="${d.steps || ''}" placeholder="0" aria-label="Nombre de pas"></li></ul></section>`;
    const lastW = S.weights.length ? S.weights[S.weights.length - 1] : null;
    h += `<section class="card"><header class="meal-head"><span class="meal-ic weight">${icon('scale')}</span>
      <div class="grow"><h3>Poids</h3><p class="muted">${lastW ? fr(lastW.kg) + ' kg le ' + pkey(lastW.date).toLocaleDateString('fr-FR') : 'Aucune pesée'} · objectif ${fr(S.profile.targetWeight)} kg</p></div>
      <button class="add-btn" data-act="addWeight" aria-label="Ajouter une pesée">${icon('plus')}</button></header></section>`;
    h += `<p class="foot muted">Nutriments : ${esc(N.source)}</p>`;
    return h;
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
    return `<li><button class="res" data-act="openFood" data-key="${esc(f.key)}"><b>${esc(f.name)}</b><span class="muted">${esc(foodSub(f))}</span></button>${plus}</li>`;
  }
  function renderResults(s) {
    const box = $('#results', s.el);
    if (!box) return;
    const q = (s.data.q || '').trim();
    let h = '';
    if (q) {
      const list = N.search(q, extraFoods(), boost);
      h += list.length ? `<ul class="res-list">${list.map(f => resultRow(f, s)).join('')}</ul>` : `<p class="empty">Aucun aliment trouvé dans la base hors ligne.</p>`;
      if (s.data.offRes) {
        h += `<h4 class="sec">Open Food Facts</h4>` + (s.data.offRes.length ? `<ul class="res-list">${s.data.offRes.map(f => resultRow(f, s)).join('')}</ul>` : '<p class="empty">Aucun produit trouvé en ligne.</p>');
      } else {
        h += `<button class="btn ghost wide" data-act="offSearch" ${s.data.offLoading ? 'disabled' : ''}>${icon('globe')}${s.data.offLoading ? 'Recherche en ligne…' : 'Chercher les produits de marque (Open Food Facts, en ligne)'}</button>`;
      }
    } else {
      const tabs = [['recent', 'Récents'], ['fav', 'Favoris'], ['mine', 'Mes aliments'], ['recipes', 'Recettes']];
      h += `<div class="tabs">${tabs.map(([id, l]) => `<button class="${s.data.tab === id ? 'on' : ''}" data-act="resTab" data-tab="${id}">${l}</button>`).join('')}</div>`;
      let list = [];
      if (s.data.tab === 'recent') list = S.recents.map(r => foodByKey(r.key)).filter(Boolean);
      if (s.data.tab === 'fav') list = S.favs.map(foodByKey).filter(Boolean);
      if (s.data.tab === 'mine') list = S.foods.map(f => foodByKey('u:' + f.id)).concat(Object.values(S.off));
      if (s.data.tab === 'recipes') list = S.recipes.map(recipeFood);
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
      return sheetHead(esc(food.name), esc(foodSub(food))) + `
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
  function openActivity(existing) {
    openSheet(s => {
      const q = N.norm(s.data.q || '');
      const list = N.ACTIVITIES.filter(a => !q || N.norm(a.name).includes(q));
      const w = currentWeight();
      const sel = s.data.sel;
      return sheetHead(existing ? 'Modifier l\'activité' : 'Ajouter une activité', 'Calcul selon ton poids (' + fr(w) + ' kg)') + `
        <div class="grid2"><label class="field"><span>Durée (min)</span><input id="acMin" inputmode="numeric" value="${s.data.min}"></label>
        <label class="field"><span>Ou calories (kcal)</span><input id="acK" inputmode="numeric" value="${s.data.k || ''}" placeholder="auto"></label></div>
        <div class="search">${icon('search')}<input id="acQ" placeholder="Rechercher une activité" value="${esc(s.data.q || '')}"></div>
        <ul class="res-list acts">${list.map(a => `<li><button class="res ${sel === a.name ? 'on' : ''}" data-act="pickAct" data-name="${esc(a.name)}"><b>${esc(a.name)}</b><span class="muted">${kcal(N.activityKcal(a.met, s.data.min || 0, w))} kcal</span></button></li>`).join('')}</ul>
        <div class="sheet-actions">${existing ? `<button class="btn ghost danger-text" data-act="delAct">${icon('trash')}Supprimer</button>` : ''}
        <button class="btn grow" data-act="saveAct" ${sel || s.data.k ? '' : 'disabled'}>${icon('check')}${sel ? esc(sel) : 'Choisis une activité'}</button></div>`;
    }, {
      data: { existing, q: '', min: existing ? existing.min : 30, sel: existing ? existing.name : null, k: existing && !existing.min ? existing.kcal : null },
      mount: s => {
        const m = $('#acMin', s.el), k = $('#acK', s.el), q = $('#acQ', s.el);
        m.addEventListener('change', () => { s.data.min = Math.round(num(m.value) || 0); s.data.k = null; s.refresh(); });
        k.addEventListener('change', () => { s.data.k = Math.round(num(k.value) || 0) || null; s.refresh(); });
        q.addEventListener('input', () => { s.data.q = q.value; const pos = q.selectionStart; s.refresh(); const q2 = $('#acQ', s.el); q2.focus(); q2.setSelectionRange(pos, pos); });
      }
    });
  }

  function openWeight() {
    const lastW = currentWeight();
    openSheet(() => sheetHead('Nouvelle pesée') + `<div class="form">
      <label class="field"><span>Poids (kg)</span><input id="wKg" inputmode="decimal" value="${fr(lastW)}" autofocus></label>
      <label class="field"><span>Date</span><input id="wDate" type="date" value="${ui.date > today() ? today() : ui.date}" max="${today()}"></label></div>
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
    const kp = aP * 4, kc = aC * 4, kf = aF * 9, kt = kp + kc + kf || 1;
    h += `<section class="card"><h3>Répartition des macronutriments</h3><div class="donut-row">${C.donut([{ value: kc, cls: 'd-carb' }, { value: kp, cls: 'd-prot' }, { value: kf, cls: 'd-fat' }], 150)}
      <ul class="legend">
        <li><i class="carb"></i>Glucides <b>${r0(aC)} g</b><span class="muted">${r0(kc / kt * 100)} % (objectif ${S.profile.split.c} %)</span></li>
        <li><i class="prot"></i>Protéines <b>${r0(aP)} g</b><span class="muted">${r0(kp / kt * 100)} % (objectif ${S.profile.split.p} %)</span></li>
        <li><i class="fat"></i>Lipides <b>${r0(aF)} g</b><span class="muted">${r0(kf / kt * 100)} % (objectif ${S.profile.split.f} %)</span></li></ul></div></section>`;
    const nutr = [['fi', 'Fibres', 30, 'min'], ['su', 'Sucres', 90, 'max'], ['sa', 'AG saturés', 20, 'max'], ['sl', 'Sel', 5, 'max']];
    h += `<section class="card"><h3>Qualité de l'alimentation</h3><p class="muted">Moyennes journalières comparées aux repères (ANSES, OMS)</p>
      ${nutr.map(([k, l, ref, kind]) => { const v = avg(x => x.n[k]); const bad = kind === 'min' ? v < ref : v > ref; return `<div class="macro ${bad && logged.length ? 'warn' : 'good'}"><div class="macro-top"><span>${l}</span><span><b>${fr(v)}</b> g · ${kind === 'min' ? 'au moins' : 'au plus'} ${ref} g</span></div><div class="bar"><i style="width:${Math.min(100, v / ref * 100)}%"></i></div></div>`; }).join('')}</section>`;
    const since = pkey(addDays(t, -(R - 1))).getTime();
    const ws = S.weights.filter(w => pkey(w.date).getTime() >= since);
    const cw = currentWeight(), b = N.bmi(cw, S.profile.height);
    const first = S.weights[0];
    h += `<section class="card"><header class="meal-head"><div class="grow"><h3>Poids</h3><p class="muted">${fr(cw)} kg · IMC ${fr(b)} (${N.bmiLabel(b)})${first ? ' · ' + (cw - first.kg > 0 ? '+' : '') + fr(cw - first.kg) + ' kg depuis le début' : ''}</p></div>
      <button class="add-btn" data-act="addWeight" aria-label="Ajouter une pesée">${icon('plus')}</button></header>
      ${ws.length >= 1 ? C.line(ws.map(w => ({ x: pkey(w.date).getTime(), y: w.kg, title: pkey(w.date).toLocaleDateString('fr-FR') + ' : ' + fr(w.kg) + ' kg' })), S.profile.targetWeight, { label: 'Évolution du poids' }) : '<p class="empty">Ajoute des pesées pour voir ta courbe.</p>'}
      ${S.weights.length ? `<details><summary>Toutes les pesées (${S.weights.length})</summary><ul class="entries">${S.weights.slice().reverse().map(w => `<li><div class="grow"><b>${fr(w.kg)} kg</b><span class="muted">${pkey(w.date).toLocaleDateString('fr-FR')}</span></div><button class="icon-btn" data-act="delWeight" data-date="${w.date}" aria-label="Supprimer">${icon('trash')}</button></li>`).join('')}</ul></details>` : ''}</section>`;
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
    const goalTxt = { lose: 'Perdre du poids', maintain: 'Maintenir mon poids', gain: 'Prendre du poids' }[p.goal];
    const lvl = ACTIVITY_LEVELS.find(a => a[0] === p.activity) || ACTIVITY_LEVELS[1];
    const row = (act, ic, label, val) => `<li><button data-act="${act}">${icon(ic)}<span class="grow">${label}</span>${val ? `<span class="muted">${val}</span>` : ''}${icon('chevR', 'chev')}</button></li>`;
    return `<div class="topbar"><h1>Profil</h1></div>
      <section class="card profile-card"><div class="avatar">${esc((p.name || 'C').charAt(0).toUpperCase())}</div>
        <div class="grow"><h3>${esc(p.name || 'Mon profil')}</h3><p class="muted">${p.sex === 'f' ? 'Femme' : 'Homme'} · ${p.age} ans · ${p.height} cm · ${fr(currentWeight())} kg</p></div>
        <button class="icon-btn" data-act="editProfile" aria-label="Modifier le profil">${icon('edit')}</button></section>
      <section class="card goals-card"><div><span class="muted">Objectif</span><b>${goalTxt}</b></div><div><span class="muted">Calories / jour</span><b>${kcal(g.kcal)} kcal</b></div>
        <div><span class="muted">G / P / L</span><b>${g.c} / ${g.p} / ${g.f} g</b></div><div><span class="muted">Dépense estimée</span><b>${kcal(g.tdee)} kcal</b></div></section>
      <ul class="menu card">
        ${row('editProfile', 'scale', 'Profil et objectif', goalTxt)}
        ${row('editGoals', 'sliders', 'Objectifs nutritionnels', kcal(g.kcal) + ' kcal')}
        ${row('manageFoods', 'food', 'Mes aliments et recettes', (S.foods.length + Object.keys(S.off).length) + ' / ' + S.recipes.length)}
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
        <div class="seg wide">${[['lose', 'Perdre'], ['maintain', 'Maintenir'], ['gain', 'Prendre']].map(([v, l]) => `<button class="${d.goal === v ? 'on' : ''}" data-act="pfSet" data-k="goal" data-v="${v}">${l}</button>`).join('')}</div>
        ${d.goal !== 'maintain' ? `<label class="field"><span>Rythme</span><select id="pf_pace">${[0.25, 0.5, 0.75, 1].map(v => `<option value="${v}" ${v === d.pace ? 'selected' : ''}>${fr(v, 2)} kg par semaine</option>`).join('')}</select></label>` : ''}
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
  }

  function openGoals() {
    const p = S.profile;
    openSheet(s => {
      const d = s.data;
      const g = N.computeGoal(Object.assign({}, p, { weight: currentWeight() }));
      const k = d.override ? d.kcal : g.kcal;
      const m = N.macroGoals(k, d.split);
      const sum = d.split.c + d.split.p + d.split.f;
      const sl = (key, label) => `<label class="slider"><span>${label}<b>${d.split[key]} % · ${m[key]} g</b></span><input type="range" min="5" max="75" step="5" value="${d.split[key]}" data-act="split" data-k="${key}"></label>`;
      return sheetHead('Objectifs nutritionnels', 'Calcul : Mifflin-St Jeor, métabolisme ' + kcal(g.bmr) + ' kcal, dépense ' + kcal(g.tdee) + ' kcal') + `<div class="form">
        <label class="switch"><input type="checkbox" id="gOverride" ${d.override ? 'checked' : ''}><span>Définir mon objectif calorique moi-même</span></label>
        <label class="field"><span>Calories par jour</span><input id="gK" inputmode="numeric" value="${r0(k)}" ${d.override ? '' : 'disabled'}></label>
        ${sl('c', 'Glucides')}${sl('p', 'Protéines')}${sl('f', 'Lipides')}
        <p class="${sum === 100 ? 'muted' : 'warn-text'}">Total : ${sum} %${sum === 100 ? '' : ' (doit faire 100 %)'}</p>
        <div class="grid2"><label class="field"><span>Objectif d'eau (ml)</span><input id="gW" inputmode="numeric" value="${d.water}"></label>
        <label class="field"><span>Taille d'un verre (ml)</span><input id="gG" inputmode="numeric" value="${d.glass}"></label></div>
        <label class="field"><span>Objectif de pas</span><input id="gS" inputmode="numeric" value="${d.steps}"></label>
        <label class="switch"><input type="checkbox" id="gEx" ${d.addEx ? 'checked' : ''}><span>Ajouter les calories des activités à mon objectif du jour</span></label>
      </div><div class="sheet-actions"><button class="btn grow" data-act="saveGoals" ${sum === 100 ? '' : 'disabled'}>${icon('check')}Enregistrer</button></div>`;
    }, {
      data: { override: !!p.kcalOverride, kcal: p.kcalOverride || goals().calc, split: Object.assign({}, p.split), water: p.waterGoal, glass: p.glass, steps: p.stepsGoal, addEx: p.addExercise },
      mount: s => {
        const keep = () => { const d = s.data; const g = id => $('#' + id, s.el);
          d.override = g('gOverride').checked; if (d.override) d.kcal = num(g('gK').value) || d.kcal;
          d.water = num(g('gW').value) || d.water; d.glass = num(g('gG').value) || d.glass; d.steps = num(g('gS').value) || d.steps; d.addEx = g('gEx').checked; };
        s.data.keep = keep;
        $('#gOverride', s.el).addEventListener('change', () => { keep(); s.refresh(); });
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
      <div class="choices">${[['lose', 'Perdre du poids'], ['maintain', 'Maintenir mon poids'], ['gain', 'Prendre du poids / du muscle']].map(([v, l]) => `<button class="choice ${o.goal === v ? 'on' : ''}" data-act="obSet" data-k="goal" data-v="${v}"><b>${l}</b></button>`).join('')}</div>
      ${o.goal !== 'maintain' ? `<div class="grid2"><label class="field"><span>Poids cible (kg)</span><input id="ob_targetWeight" inputmode="decimal" value="${fr(o.targetWeight)}"></label>
      <label class="field"><span>Rythme</span><select id="ob_pace">${[0.25, 0.5, 0.75, 1].map(v => `<option value="${v}" ${v === o.pace ? 'selected' : ''}>${fr(v, 2)} kg / semaine</option>`).join('')}</select></label></div>` : ''}` + nav();
    if (st === 4) {
      const g = N.computeGoal(o), m = N.macroGoals(g.kcal, o.split);
      const diff = Math.abs(o.weight - o.targetWeight);
      const weeks = o.goal === 'maintain' || !diff ? 0 : Math.ceil(diff / o.pace);
      const eta = weeks ? new Date(Date.now() + weeks * 7 * 86400000).toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' }) : '';
      body = `<h2>Ton plan${o.name ? ', ' + esc(o.name) : ''}</h2><div class="ob-plan"><div class="big"><b>${kcal(g.kcal)}</b><span>kcal par jour</span></div>
        <div class="grid3 plan-macros"><div class="carb"><b>${m.c} g</b><span>Glucides</span></div><div class="prot"><b>${m.p} g</b><span>Protéines</span></div><div class="fat"><b>${m.f} g</b><span>Lipides</span></div></div>
        <p class="muted">Métabolisme de base ${kcal(g.bmr)} kcal · dépense estimée ${kcal(g.tdee)} kcal${eta ? '<br>Objectif de ' + fr(o.targetWeight) + ' kg vers ' + eta : ''}</p></div>
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
      const g = lastGrams(f.key);
      logFood(f, g, s.data.meal);
      render(); renderResults(s);
      toast(f.name.split(',')[0] + ' ajouté (' + fr(g, 0) + ' g)', { label: 'Annuler', fn: () => undoLast(s.data.meal) });
    },
    offSearch: async () => {
      const s = topSheet();
      s.data.offLoading = true; renderResults(s);
      try { s.data.offRes = await N.offSearch(s.data.q); }
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
    saveAct: () => {
      const s = topSheet(), d = dayMut(ui.date);
      const a = N.ACTIVITIES.find(x => x.name === s.data.sel);
      const k = s.data.k || (a ? N.activityKcal(a.met, s.data.min, currentWeight()) : 0);
      if (!k) { toast('Indique une durée ou des calories.'); return; }
      const rec = { id: s.data.existing ? s.data.existing.id : uid(), name: s.data.sel || 'Activité', min: s.data.k ? 0 : s.data.min, kcal: k };
      const i = d.acts.findIndex(x => x.id === rec.id);
      if (i >= 0) d.acts[i] = rec; else d.acts.push(rec);
      save(); closeSheet(s); render();
    },
    delAct: () => { const s = topSheet(), d = dayMut(ui.date); d.acts = d.acts.filter(a => a.id !== s.data.existing.id); save(); closeSheet(s); render(); },
    addWeight: () => openWeight(),
    saveWeight: () => {
      const s = topSheet(), kg = num($('#wKg', s.el).value), date = $('#wDate', s.el).value || today();
      if (!(kg > 20 && kg < 400)) { toast('Poids invalide.'); return; }
      S.weights = S.weights.filter(w => w.date !== date).concat([{ date, kg }]).sort((a, b) => a.date < b.date ? -1 : 1);
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
    fastStart: () => { S.fasting.active = { start: Date.now(), plan: S.fasting.plan }; save(); render(); P.vibrate(20); },
    fastStop: async () => {
      const F = S.fasting, a = F.active, el = Date.now() - a.start, goalH = parseInt(a.plan, 10);
      if (el < goalH * 3600000 && !(await confirmBox('Arrêter le jeûne avant l\'objectif de ' + goalH + ' h ?', 'Arrêter'))) return;
      if (el > 10 * 60000) F.history.push({ start: a.start, end: Date.now(), plan: a.plan, goalH });
      F.active = null; save(); render();
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
      S.fasting.active.start = t; save(); closeSheet(s); render();
    },
    fastDel: el => { S.fasting.history.splice(+el.dataset.i, 1); save(); render(); },
    range: el => { ui.statsRange = +el.dataset.r; render(); },
    editProfile: () => openProfile(),
    pfSet: el => { const s = topSheet(); readProfileForm(s); s.data.p[el.dataset.k] = el.dataset.v; s.refresh(); },
    saveProfile: () => {
      const s = topSheet(); readProfileForm(s);
      S.profile = Object.assign(S.profile, s.data.p);
      save(); closeSheet(s); render(); toast('Profil mis à jour');
    },
    editGoals: () => openGoals(),
    saveGoals: () => {
      const s = topSheet(); s.data.keep();
      const d = s.data, p = S.profile;
      p.kcalOverride = d.override ? Math.round(d.kcal) : null;
      p.split = d.split; p.waterGoal = Math.round(d.water); p.glass = Math.round(d.glass); p.stepsGoal = Math.round(d.steps); p.addExercise = d.addEx;
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
      S.profile = Object.assign(S.profile, ui.ob, { onboarded: true });
      if (!S.weights.length) S.weights.push({ date: today(), kg: ui.ob.weight });
      ui.ob = null; save(); render();
    }
  };
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
    if (act === 'ingG') { const s = topSheet(); s.data.r.items[+el.dataset.i].g = num(el.value) || 0; s.refresh(); }
  });
  $('#fileInput').addEventListener('change', async e => { const f = e.target.files[0]; if (f) restoreFrom(await f.text()); });
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
    render();
    const sp = $('#splash');
    sp.classList.add('hide'); setTimeout(() => sp.remove(), 400);
    if ('serviceWorker' in navigator && P.kind === 'web' && location.protocol === 'https:') navigator.serviceWorker.register('sw.js').catch(() => {});
  }
  window.CalorysDebug = { get state() { return S; }, ui, render };
  boot();
})();
