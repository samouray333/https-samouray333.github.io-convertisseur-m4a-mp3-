/* Calorys : moteur métier, porté de Nutravyn (domain/*.dart).
   Calculs énergétiques, moteur adaptatif, mode sèche, séances, gamification.
   Aucune décision métier dans l'interface : tout passe par ce module. */
(function () {
  'use strict';
  const KCAL_PER_KG = 7700;
  const DAY = 86400000;

  /* ---------- Calculs énergétiques (nutrition_calculator.dart) ---------- */
  const PRESETS = {
    balanced: { label: 'Équilibré', p: 0.30, c: 0.40, f: 0.30 },
    cut: { label: 'Sèche (protéines hautes)', p: 0.40, c: 0.30, f: 0.30 },
    bulk: { label: 'Prise de masse', p: 0.28, c: 0.47, f: 0.25 },
    lowCarb: { label: 'Low-carb', p: 0.35, c: 0.20, f: 0.45 },
    keto: { label: 'Cétogène', p: 0.30, c: 0.07, f: 0.63 }
  };

  function bmr(sex, w, h, age) {
    const base = 10 * w + 6.25 * h - 5 * age;
    return sex === 'f' ? base - 161 : base + 5;
  }
  const tdee = (sex, w, h, age, factor) => bmr(sex, w, h, age) * factor;
  const floorKcal = (sex, b) => Math.max(sex === 'f' ? 1200 : 1500, b);
  const maxWeeklyLossKg = w => w * 0.01;

  /* En perte, maintien et prise : la cible demandée sort telle quelle.
     En sèche (date de pesée) : déficit plafonné à 25 % et plancher métabolique. */
  function dailyTarget(expenditure, goal, rate, sex, b) {
    const delta = rate * KCAL_PER_KG / 7;
    let t;
    if (goal === 'cut') t = Math.max(expenditure - delta, expenditure * 0.75, floorKcal(sex, b));
    else if (goal === 'lose') t = expenditure - delta;
    else if (goal === 'gain') t = expenditure + delta;
    else t = expenditure;
    return Math.round(Math.max(0, t));
  }

  /* Ce qu'il faut savoir sur la cible obtenue : informatif, jamais bloquant. */
  function describe(target, expenditure, b, rate, w) {
    const deficit = expenditure <= 0 ? 0 : (expenditure - target) / expenditure;
    const maxRate = maxWeeklyLossKg(w);
    const belowBmr = target < b;
    const aggressive = deficit > 0.25 || rate > maxRate;
    let note = null;
    if (belowBmr) note = `Cible sous ton métabolisme de base (${Math.round(deficit * 100)} % de déficit).`;
    else if (aggressive && deficit > 0) note = `Déficit de ${Math.round(deficit * 100)} %, au-dessus du rythme conventionnel de ${maxRate.toFixed(2).replace('.', ',')} kg/sem.`;
    return { deficit, belowBmr, aggressive, note, maxRate };
  }

  /* Macros d'un preset (ou d'une répartition perso {p,c,f} en fractions).
     proteinFloorKg : plancher protéique en g/kg (1,8 en mode sèche). */
  function macros(kcal, split, w, proteinFloorKg) {
    let p = kcal * split.p / 4;
    if (w && proteinFloorKg) p = Math.max(p, w * proteinFloorKg);
    const rest = Math.max(0, kcal - p * 4);
    const ratio = split.c + split.f || 1;
    return { kcal, p: Math.round(p), c: Math.round(rest * (split.c / ratio) / 4), f: Math.round(rest * (split.f / ratio) / 9) };
  }

  /* Eau conseillée : 35 ml/kg + 500 ml par heure d'entraînement. */
  const waterGoalMl = (w, trainingMin) => Math.round((w * 35 + trainingMin / 60 * 500) / 50) * 50;

  /* ---------- Moteur adaptatif (adaptive_engine.dart) ---------- */
  const ALPHA = 0.25, MIN_DAYS = 10;

  /* Moyenne mobile exponentielle des pesées (ordre chronologique). */
  function smooth(weights) {
    if (!weights.length) return [];
    const sorted = weights.slice().sort((a, b) => (a.date < b.date ? -1 : 1));
    let ema = sorted[0].kg;
    return sorted.map(w => { ema = ALPHA * w.kg + (1 - ALPHA) * ema; return { date: w.date, kg: ema }; });
  }

  /* dépense réelle = kcal moyennes ingérées + (Δ poids lissé × 7700 / jours).
     intake : {date: kcal} sur la fenêtre ; weights : pesées de la même fenêtre. */
  function adaptive(p, intake, weights, currentW, theoretical, b) {
    const trend = smooth(weights);
    const vals = Object.values(intake).filter(v => v > 0);
    const logged = vals.length;
    let measured = null, weekly = 0, reliable = false;
    if (trend.length >= 3 && logged >= MIN_DAYS) {
      const first = trend[0], last = trend[trend.length - 1];
      const days = Math.round((Date.parse(last.date) - Date.parse(first.date)) / DAY);
      if (days >= MIN_DAYS) {
        const dKg = last.kg - first.kg;
        weekly = dKg / days * 7;
        const avg = vals.reduce((a, v) => a + v, 0) / logged;
        measured = avg - dKg * KCAL_PER_KG / days;
        // Une mesure absurde (sous-déclaration massive, pesées rares) est écartée.
        reliable = measured > b * 0.9 && measured < theoretical * 1.6;
      }
    }
    return { measured, reliable, weekly, logged, weighIns: weights.length,
      verdict: verdict(p, weekly, reliable, logged, weights.length, currentW, measured, theoretical) };
  }

  function verdict(p, weekly, reliable, logged, nW, w, measured, theoretical) {
    const f2 = v => Math.abs(v).toFixed(2).replace('.', ',');
    if (!reliable) {
      const needDays = Math.max(0, 14 - logged), needW = Math.max(0, 4 - nW);
      const parts = [];
      if (needDays) parts.push(`${needDays} jour(s) de journal`);
      if (needW) parts.push(`${needW} pesée(s)`);
      return parts.length
        ? `Encore ${parts.join(' et ')} pour calibrer ta dépense réelle. En attendant : estimation théorique.`
        : 'Mesure encore incohérente (journal incomplet ou pesées trop espacées) : estimation théorique conservée.';
    }
    const diff = Math.round(measured - theoretical);
    const calib = Math.abs(diff) < 60 ? 'La formule tombait juste.'
      : diff > 0 ? `Tu brûles ${Math.abs(diff)} kcal de plus que la formule le disait.`
        : `Tu brûles ${Math.abs(diff)} kcal de moins que la formule le disait.`;
    const maxRate = maxWeeklyLossKg(w);
    if (p.goal === 'lose' || p.goal === 'cut') {
      if (weekly > 0.1) return `${calib} Le poids monte alors que tu vises une perte : cible réajustée à la baisse.`;
      if (weekly > -0.1) return `${calib} Plateau réel (hors bruit hydrique) : la cible descend d'un cran.`;
      if (Math.abs(weekly) > maxRate * 1.3) return `${calib} Tu descends à ${f2(weekly)} kg/sem, au-delà du repère de ${f2(maxRate)} kg/sem. Surveille la force à l'entraînement.`;
      return `${calib} Trajectoire propre : ${f2(weekly)} kg/sem. On ne touche à rien.`;
    }
    return `${calib} Variation : ${weekly >= 0 ? '+' : '-'}${f2(weekly)} kg/sem.`;
  }

  /* ---------- Mode sèche / pesée officielle (cut_planner.dart) ---------- */
  function cutPlan(p, currentKg, expenditure, b) {
    const f2 = v => v.toFixed(2).replace('.', ','), f1 = v => v.toFixed(1).replace('.', ',');
    const days = Math.max(0, Math.ceil((Date.parse(p.weighIn) - Date.now()) / DAY));
    const toLose = currentKg - p.targetWeight;
    const weeks = Math.max(days / 7, 0.1);
    const required = toLose / weeks;
    const safe = maxWeeklyLossKg(currentKg);
    if (toLose <= 0) {
      return { days, toLose: 0, required: 0, safe, target: Math.round(expenditure), status: 'done',
        message: 'Tu es dans la catégorie. Objectif : y rester sans creuser.', notes: ['Maintien calorique jusqu\'à la pesée.'] };
    }
    const applied = Math.min(required, safe);
    const target = dailyTarget(expenditure, 'cut', applied, p.sex, b);
    let status, message;
    if (required <= safe * 0.75) { status = 'ontrack'; message = `Trajectoire confortable : ${f2(required)} kg/sem sur ${days} jours.`; }
    else if (required <= safe) { status = 'tight'; message = `Ça passe mais c'est serré : ${f2(required)} kg/sem. Zéro écart, pesée le matin à jeun.`; }
    else {
      status = 'unrealistic';
      const reach = currentKg - safe * weeks;
      message = `Pas atteignable proprement. Au rythme sain maximum (${f2(safe)} kg/sem) tu seras à ${f1(reach)} kg le jour J, soit ${f1(reach - p.targetWeight)} kg au-dessus.`;
    }
    const notes = [`Protéines à ${Math.round(currentKg * 2)} g/j minimum pour garder le muscle.`,
      'Pesée quotidienne le matin, à jeun, après WC : seule la courbe lissée compte.'];
    if (days > 14) notes.push(`Semaines 1 à ${Math.floor((days - 7) / 7)} : déficit plein. Dernière semaine : déficit réduit et glucides remontés la veille pour garder du jus.`);
    if (status === 'unrealistic') notes.push('Options réelles : monter de catégorie, décaler la date, ou accepter l\'écart. Descendre plus vite se paie sur la performance le jour J.');
    notes.push('Coupe hydrique : à voir avec ton staff, pas planifiée par l\'appli.');
    return { days, toLose, required, safe, target, status, message, notes };
  }

  /* ---------- Séances (activity_calculator.dart) ---------- */
  const SESSIONS = [
    { id: 'sparring', name: 'Sparring', met: 10.3, sweat: 18 },
    { id: 'technique', name: 'Technique / pao', met: 7.8, sweat: 5 },
    { id: 'grappling', name: 'Grappling / sol', met: 10.0, sweat: 18 },
    { id: 'bag', name: 'Sac / shadow', met: 7.0, sweat: 14 },
    { id: 'strength', name: 'Renforcement', met: 6.0, sweat: 10 },
    { id: 'cardio', name: 'Cardio / course', met: 9.8, sweat: 14 },
    { id: 'cycling', name: 'Vélo', met: 8.0, sweat: 10 },
    { id: 'mobility', name: 'Mobilité / étirements', met: 2.8, sweat: 5 }
  ];
  /* kcal = MET × 3,5 × poids / 200 × minutes, ajusté par l'intensité perçue (RPE 1 à 10). */
  function sessionKcal(met, minutes, w, rpe) {
    const f = Math.min(1.35, Math.max(0.5, 0.7 + (Math.min(10, Math.max(1, rpe)) - 5) * 0.06));
    return Math.round(met * f * 3.5 * w / 200 * minutes);
  }
  const sweatMl = (base, minutes, rpe) => Math.round(base * minutes * (0.8 + rpe / 20));

  /* ---------- Gamification (gamification.dart) ---------- */
  const BELTS = [
    { id: 'white', label: 'Blanche', xp: 0, color: '#ede7ff' },
    { id: 'yellow', label: 'Jaune', xp: 600, color: '#ffd84b' },
    { id: 'orange', label: 'Orange', xp: 1600, color: '#ff8a3d' },
    { id: 'green', label: 'Verte', xp: 3200, color: '#4ae39b' },
    { id: 'blue', label: 'Bleue', xp: 5600, color: '#2ed9e6' },
    { id: 'brown', label: 'Marron', xp: 9000, color: '#a9614b' },
    { id: 'black', label: 'Noire', xp: 14000, color: '#3a3346' },
    { id: 'dan2', label: 'Noire 2e dan', xp: 22000, color: '#ff3d6e' }
  ];
  const XP = { logMeal: 10, completeDay: 40, hitCalories: 30, hitProtein: 25, logWeight: 15, hitWater: 20,
    logTraining: 20, finishFast: 30, photoScan: 5 };
  const XP_LABELS = { logMeal: 'Repas noté', completeDay: 'Journée complète', hitCalories: 'Cible calorique tenue',
    hitProtein: 'Protéines atteintes', logWeight: 'Pesée', hitWater: 'Hydratation OK', logTraining: 'Séance notée',
    finishFast: 'Jeûne terminé', photoScan: 'Repas scanné', quest: 'Défi de la semaine' };
  const BADGES = [
    { code: 'first_blood', label: 'Premier round', hint: 'Ton premier repas noté.' },
    { code: 'week_1', label: 'Semaine pleine', hint: '7 jours notés d\'affilée.' },
    { code: 'month_1', label: 'Camp d\'entraînement', hint: '30 jours notés d\'affilée.' },
    { code: 'protein_king', label: 'Machine à protéines', hint: 'Protéines tenues 14 jours.' },
    { code: 'scale_honest', label: 'Face à la balance', hint: '20 pesées enregistrées.' },
    { code: 'first_kg', label: 'Premier kilo', hint: '1 kg perdu sur la courbe lissée.' },
    { code: 'five_kg', label: 'Cinq kilos', hint: '5 kg perdus sur la courbe lissée.' },
    { code: 'weight_made', label: 'Poids fait', hint: 'Catégorie atteinte le jour de la pesée.' },
    { code: 'comeback', label: 'Retour au coin', hint: 'Repris le journal après une coupure.' }
  ];
  const beltFor = xp => BELTS.reduce((cur, b) => (xp >= b.xp ? b : cur), BELTS[0]);

  /* Les XP se recalculent à partir de l'historique : une suppression ou une
     correction ne laisse pas de points fantômes, et casser une série ne coûte rien.
     days : [{date, meals, kcal, protein, water, trainings, weighed, fastsDone, photos}] triés. */
  function game(days, goalsFor, weightsCount, trendLossKg, cutDone) {
    let xp = 0, streak = 0, best = 0, prev = null, comeback = false, proteinDays = 0;
    const log = [];
    const byWeek = {};
    const now = new Date();
    const todayKey = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
    for (const d of days) {
      const active = d.meals > 0;
      const gap = prev ? Math.round((Date.parse(d.date) - Date.parse(prev)) / DAY) : 0;
      if (active) {
        if (!prev || gap > 1) { if (prev && gap > 3) comeback = true; streak = 1; } else streak += 1;
        prev = d.date; best = Math.max(best, streak);
      }
      const mult = Math.min(1.5, 1 + Math.max(0, streak - 1) * 0.02);
      const g = goalsFor(d.date);
      const past = d.date < todayKey;
      const gains = [];
      if (active) gains.push(['logMeal', XP.logMeal * Math.min(4, d.meals)]);
      if (d.meals >= 3) gains.push(['completeDay', XP.completeDay]);
      if (past && active && Math.abs(d.kcal - g.kcal) <= g.kcal * 0.1) gains.push(['hitCalories', XP.hitCalories]);
      const protOk = active && d.protein >= g.p * 0.95;
      if (protOk) { gains.push(['hitProtein', XP.hitProtein]); proteinDays++; }
      if (d.water >= g.water) gains.push(['hitWater', XP.hitWater]);
      if (d.trainings) gains.push(['logTraining', XP.logTraining]);
      if (d.weighed) gains.push(['logWeight', XP.logWeight]);
      if (d.fastsDone) gains.push(['finishFast', XP.finishFast * d.fastsDone]);
      if (d.photos) gains.push(['photoScan', XP.photoScan * Math.min(4, d.photos)]);
      let dayXp = 0;
      for (const [k, v] of gains) dayXp += Math.round(v * mult);
      xp += dayXp;
      if (dayXp) log.push({ date: d.date, xp: dayXp, gains });
      const wk = weekKey(d.date);
      const w = byWeek[wk] || (byWeek[wk] = { days: 0, sessions: 0, weighIns: 0, protein: 0 });
      if (active) w.days++;
      w.sessions += d.trainings;
      if (d.weighed) w.weighIns++;
      if (protOk) w.protein++;
    }
    for (const wk of Object.keys(byWeek)) for (const q of quests(byWeek[wk])) if (q.done) xp += q.reward;
    const lastActive = prev;
    if (lastActive && Math.round((Date.parse(todayKey) - Date.parse(lastActive)) / DAY) > 1) streak = 0;
    const badges = new Set();
    if (days.some(d => d.meals)) badges.add('first_blood');
    if (best >= 7) badges.add('week_1');
    if (best >= 30) badges.add('month_1');
    if (proteinDays >= 14) badges.add('protein_king');
    if (weightsCount >= 20) badges.add('scale_honest');
    if (trendLossKg >= 1) badges.add('first_kg');
    if (trendLossKg >= 5) badges.add('five_kg');
    if (cutDone) badges.add('weight_made');
    if (comeback) badges.add('comeback');
    const belt = beltFor(xp);
    const next = BELTS[BELTS.indexOf(belt) + 1] || null;
    const progress = next ? (xp - belt.xp) / (next.xp - belt.xp) : 1;
    const curWeek = byWeek[weekKey(todayKey)] || { days: 0, sessions: 0, weighIns: 0, protein: 0 };
    return { xp, belt, next, progress, toNext: next ? next.xp - xp : 0, streak, best, badges,
      multiplier: Math.min(1.5, 1 + Math.max(0, streak - 1) * 0.02), quests: quests(curWeek), log };
  }

  /* Défis de la semaine (lundi à dimanche) : régularité, jamais privation. */
  function quests(w) {
    return [
      { code: 'log6', label: '6 journées notées', target: 6, progress: w.days, reward: 120 },
      { code: 'train4', label: '4 séances', target: 4, progress: w.sessions, reward: 100 },
      { code: 'weigh4', label: '4 pesées du matin', target: 4, progress: w.weighIns, reward: 80 },
      { code: 'protein5', label: '5 jours protéines tenues', target: 5, progress: w.protein, reward: 110 }
    ].map(q => Object.assign(q, { done: q.progress >= q.target, ratio: Math.min(1, q.progress / q.target) }));
  }

  function weekKey(date) {
    const d = new Date(date + 'T12:00:00');
    const day = (d.getDay() + 6) % 7;
    d.setDate(d.getDate() - day);
    return d.toISOString().slice(0, 10);
  }

  window.Engine = { KCAL_PER_KG, PRESETS, bmr, tdee, floorKcal, maxWeeklyLossKg, dailyTarget, describe, macros,
    waterGoalMl, smooth, adaptive, cutPlan, SESSIONS, sessionKcal, sweatMl, BELTS, XP, XP_LABELS, BADGES, beltFor,
    game, quests, weekKey };
})();
