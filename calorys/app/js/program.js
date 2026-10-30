/* Calorys : programmes importables (fichiers « calorys-programme »).
   Un programme décrit la fenêtre de jeûne, les repas, la répartition des calories, le planning
   d'eau, les notifications et les conseils ; l'appli se règle dessus. Voir calorys/programmes/. */
(function () {
  'use strict';
  const MEALS = ['breakfast', 'lunch', 'dinner', 'snack'];
  const PRESETS = ['balanced', 'cut', 'bulk', 'lowCarb', 'keto'];
  const DAY = 86400000;
  const isTime = t => typeof t === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(t);
  const str = (v, max) => String(v == null ? '' : v).replace(/[\u0000-\u001f]/g, ' ').trim().slice(0, max || 200);
  const toMin = t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; };
  const days = v => (Array.isArray(v) ? v.map(Number).filter(d => d >= 1 && d <= 7) : []);

  /* Vérifie et nettoie un programme. Renvoie { ok, errors, prog }. */
  function validate(raw) {
    const errors = [];
    let o = raw;
    if (typeof raw === 'string') { try { o = JSON.parse(raw); } catch (e) { return { ok: false, errors: ['Fichier illisible (JSON invalide).'] }; } }
    if (!o || typeof o !== 'object' || o.format !== 'calorys-programme') return { ok: false, errors: ['Ce fichier n\'est pas un programme Calorys (champ "format" attendu : "calorys-programme").'] };
    const p = { format: 'calorys-programme', version: 1 };
    p.id = str(o.id || o.name, 60).toLowerCase().replace(/[^a-z0-9-]+/g, '-') || 'programme';
    p.name = str(o.name, 80);
    if (!p.name) errors.push('Le programme n\'a pas de nom ("name").');
    p.author = str(o.author, 60);
    p.description = str(o.description, 600);
    p.durationDays = Math.max(0, Math.min(730, Math.round(Number(o.durationDays) || 0)));
    if (o.goal) {
      const t = ['lose', 'maintain', 'gain'].includes(o.goal.type) ? o.goal.type : null;
      if (t) p.goal = { type: t, pace: Math.max(0, Math.min(1, Number(o.goal.pace) || 0.5)) };
    }
    if (o.macros) {
      if (PRESETS.includes(o.macros.preset)) p.macros = { preset: o.macros.preset };
      else if (['p', 'c', 'f'].every(k => Number(o.macros[k]) >= 0)) {
        const m = { p: Math.round(o.macros.p), c: Math.round(o.macros.c), f: Math.round(o.macros.f) };
        if (m.p + m.c + m.f === 100) p.macros = { custom: m }; else errors.push('Les macros doivent faire 100 % (p + c + f).');
      }
    }
    if (o.fasting) {
      const f = o.fasting;
      if (!isTime(f.eatStart) || !isTime(f.eatEnd)) errors.push('Jeûne : "eatStart" et "eatEnd" doivent être au format HH:MM.');
      else {
        let win = toMin(f.eatEnd) - toMin(f.eatStart);
        if (win <= 0) win += 1440;
        const fastH = Math.round((1440 - win) / 60);
        p.fasting = { eatStart: f.eatStart, eatEnd: f.eatEnd, plan: fastH + ':' + (24 - fastH), autoStart: f.autoStart !== false };
      }
    }
    if (o.meals) {
      const sh = {};
      let tot = 0;
      for (const m of MEALS) { const v = Math.max(0, Number(o.meals[m]) || 0); sh[m] = v; tot += v; }
      if (tot <= 0) errors.push('Repas : au moins un repas doit avoir une part (> 0).');
      else { for (const m of MEALS) sh[m] = Math.round(sh[m] / tot * 1000) / 1000; p.meals = sh; }
    }
    if (o.water) {
      const w = { goal: o.water.goalMl === 'auto' || o.water.goalMl == null ? 'auto' : Math.max(500, Math.min(8000, Math.round(Number(o.water.goalMl) || 2000))), schedule: [] };
      for (const s of (o.water.schedule || []).slice(0, 24)) {
        if (!isTime(s.at)) { errors.push('Eau : heure invalide "' + str(s.at, 10) + '".'); continue; }
        w.schedule.push({ at: s.at, ml: Math.max(50, Math.min(1500, Math.round(Number(s.ml) || 250))), text: str(s.text, 120) });
      }
      w.schedule.sort((a, b) => toMin(a.at) - toMin(b.at));
      p.water = w;
    }
    p.reminders = [];
    for (const r of (o.reminders || []).slice(0, 40)) {
      if (!isTime(r.at)) { errors.push('Rappel : heure invalide "' + str(r.at, 10) + '".'); continue; }
      const title = str(r.title, 60);
      if (!title) { errors.push('Rappel de ' + r.at + ' sans titre.'); continue; }
      const d = days(r.days);
      p.reminders.push({ at: r.at, title, text: str(r.text, 160), days: d.length && d.length < 7 ? d : null });
    }
    p.dayOverrides = [];
    for (const d of (o.dayOverrides || []).slice(0, 7)) {
      const dd = days(d.days);
      if (!dd.length) continue;
      p.dayOverrides.push({ days: dd, kcal: d.kcal ? Math.max(400, Math.min(6000, Math.round(Number(d.kcal)))) : null, note: str(d.note, 120) });
    }
    p.tips = (o.tips || []).slice(0, 120).map(t => str(t, 240)).filter(Boolean);
    p.rules = (o.rules || []).slice(0, 20).map(t => str(t, 160)).filter(Boolean);
    if (!p.fasting && !p.meals && !p.water && !p.reminders.length && !p.macros && !p.goal && !p.dayOverrides.length) errors.push('Le programme ne règle rien (ni jeûne, ni repas, ni eau, ni rappels).');
    return { ok: !errors.length, errors, prog: p };
  }

  /* Jour ISO (1 = lundi … 7 = dimanche). */
  const isoDay = d => ((d.getDay() + 6) % 7) + 1;
  const at = (base, hm) => { const d = new Date(base); const [h, m] = hm.split(':').map(Number); d.setHours(h, m, 0, 0); return d; };

  /* État de la fenêtre de repas à l'instant t. */
  function eatWindow(p, now) {
    if (!p || !p.fasting) return null;
    now = now || new Date();
    const f = p.fasting;
    let start = at(now, f.eatStart), end = at(now, f.eatEnd);
    if (end <= start) { // fenêtre qui passe minuit
      if (now < end) start = new Date(start.getTime() - DAY); else end = new Date(end.getTime() + DAY);
    }
    const open = now >= start && now < end;
    let next;
    if (open) next = end;
    else next = now < start ? start : new Date(start.getTime() + DAY);
    const lastEnd = now >= end ? end : new Date(end.getTime() - DAY);
    return { open, start, end, next, lastEnd };
  }

  function dayIndex(state, now) {
    if (!state) return 0;
    const s = new Date(state.start + 'T00:00:00'), n = now || new Date();
    return Math.floor((new Date(n.getFullYear(), n.getMonth(), n.getDate()) - s) / DAY) + 1;
  }

  function override(p, date) {
    if (!p || !p.dayOverrides) return null;
    const d = isoDay(date || new Date());
    return p.dayOverrides.find(o => o.days.includes(d)) || null;
  }

  function tipOf(p, n) { return p && p.tips && p.tips.length ? p.tips[(Math.max(1, n) - 1) % p.tips.length] : ''; }

  /* Notifications du programme : [{id, at, title, text, days}] (ids 100 et plus). */
  function notifications(p) {
    if (!p) return [];
    const out = [];
    let id = 100;
    for (const r of p.reminders) out.push({ id: id++, at: r.at, title: r.title, text: r.text || '', days: r.days });
    if (p.water) for (const w of p.water.schedule) out.push({ id: id++, at: w.at, title: 'Hydratation : ' + w.ml + ' ml', text: w.text || 'Un verre d\'eau, comme prévu dans ton programme.' });
    return out;
  }

  /* Ce que l'application de ce programme va changer (affiché avant confirmation). */
  function summary(p) {
    const L = [];
    const MEAL_FR = { breakfast: 'petit-déjeuner', lunch: 'déjeuner', dinner: 'dîner', snack: 'collations' };
    if (p.fasting) L.push(`Jeûne ${p.fasting.plan} : repas de ${p.fasting.eatStart} à ${p.fasting.eatEnd}${p.fasting.autoStart ? ', minuteur de jeûne automatique' : ''}`);
    if (p.meals) {
      const off = MEALS.filter(m => !p.meals[m]).map(m => MEAL_FR[m]);
      L.push('Répartition : ' + MEALS.filter(m => p.meals[m]).map(m => MEAL_FR[m] + ' ' + Math.round(p.meals[m] * 100) + ' %').join(', ') + (off.length ? ' (sans ' + off.join(', ') + ')' : ''));
    }
    if (p.goal) L.push('Objectif : ' + { lose: 'perdre', maintain: 'maintenir', gain: 'prendre' }[p.goal.type] + (p.goal.type !== 'maintain' ? ' ' + String(p.goal.pace).replace('.', ',') + ' kg/semaine' : ''));
    if (p.macros) L.push('Macros : ' + (p.macros.preset ? { balanced: 'équilibré', cut: 'sèche', bulk: 'prise de masse', lowCarb: 'low-carb', keto: 'cétogène' }[p.macros.preset] : 'P ' + p.macros.custom.p + ' / G ' + p.macros.custom.c + ' / L ' + p.macros.custom.f + ' %'));
    for (const o of p.dayOverrides) L.push((o.kcal ? o.kcal + ' kcal' : 'Jour spécial') + ' le ' + o.days.map(d => ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'][d - 1]).join(' et ') + (o.note ? ' (' + o.note + ')' : ''));
    if (p.water) L.push('Eau : ' + (p.water.goal === 'auto' ? 'objectif automatique' : (p.water.goal / 1000).toString().replace('.', ',') + ' L par jour') + (p.water.schedule.length ? ', ' + p.water.schedule.length + ' rappels programmés' : ''));
    if (p.reminders.length) L.push(p.reminders.length + ' notification(s) : ' + p.reminders.slice(0, 4).map(r => r.at + ' ' + r.title).join(' · ') + (p.reminders.length > 4 ? '…' : ''));
    if (p.durationDays) L.push('Durée : ' + p.durationDays + ' jours');
    return L;
  }

  /* Modèle commenté à exporter pour créer son propre programme. */
  function template() {
    return {
      format: 'calorys-programme', version: 1, id: 'mon-programme', name: 'Mon programme', author: 'Moi',
      description: 'Décris ici ton programme.', durationDays: 28,
      goal: { type: 'lose', pace: 0.5 },
      macros: { preset: 'balanced' },
      fasting: { eatStart: '12:00', eatEnd: '20:00', autoStart: true },
      meals: { breakfast: 0, lunch: 0.45, dinner: 0.4, snack: 0.15 },
      water: { goalMl: 'auto', schedule: [{ at: '08:00', ml: 500, text: 'Grand verre d\'eau au réveil' }] },
      reminders: [{ at: '12:00', title: 'Fenêtre de repas ouverte', text: 'Tu peux manger.' }, { at: '07:30', title: 'Pesée', text: 'Pesée hebdomadaire.', days: [1] }],
      dayOverrides: [],
      rules: ['Une règle par ligne'],
      tips: ['Un conseil par jour, affiché dans le journal']
    };
  }

  window.Program = { validate, eatWindow, dayIndex, override, tipOf, notifications, summary, template, isoDay, toMin };
})();
