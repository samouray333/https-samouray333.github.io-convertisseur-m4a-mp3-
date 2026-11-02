// Mode Défis : questions générées automatiquement à partir de la maquette ouverte.
import { checkCoherence, RULES } from './coherence';
import { computeBilan, DEFAULT_PARAMS, VERDICT_LABEL, type DepParams } from './deperditions';
import { fmt, parseNum } from './format';
import { computeMetre } from './metre';
import { fluidInfo } from './maintenance';
import { airFlow, isExtractTerminal, num, powerW, prop } from './props';
import type { Model } from './types';

export interface Question {
  id: string;
  texte: string;
  type: 'nombre' | 'choix';
  unite?: string;
  choix?: string[];
  reponse: number | string;
  /** tolérance absolue et/ou relative (%) pour les valeurs numériques */
  tolAbs?: number;
  tolPct?: number;
  explication: string;
}

export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(r: () => number, arr: T[]): T {
  return arr[Math.floor(r() * arr.length)];
}

function shuffle<T>(r: () => number, arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function tolerance(q: Question): number {
  if (q.type !== 'nombre' || typeof q.reponse !== 'number') return 0;
  return Math.max(q.tolAbs ?? 0, (Math.abs(q.reponse) * (q.tolPct ?? 0)) / 100);
}

export function checkAnswer(q: Question, answer: string): boolean {
  if (q.type === 'choix') return answer.trim().toLowerCase() === String(q.reponse).trim().toLowerCase();
  const v = parseNum(answer);
  if (v === null || typeof q.reponse !== 'number') return false;
  return Math.abs(v - q.reponse) <= tolerance(q) + 1e-9;
}

export function formatAnswer(q: Question): string {
  if (q.type === 'choix') return String(q.reponse);
  const r = q.reponse as number;
  const dec = Number.isInteger(r) ? 0 : Math.abs(r) < 10 ? 2 : 1;
  const t = tolerance(q);
  return `${fmt(r, dec)}${q.unite ? ' ' + q.unite : ''}${t > 0 ? ` (tolérance ± ${fmt(t, t < 1 ? 2 : 1)})` : ''}`;
}

export function generateQuestions(m: Model, seed: number, count = 10, params: DepParams = DEFAULT_PARAMS): Question[] {
  const r = rng(seed);
  const metre = computeMetre(m, 0);
  const bilan = computeBilan(m, params);
  const all: Question[] = [];
  const must: string[] = [];

  // 1. longueurs de tubes
  const tubes = metre.tubes.filter((t) => t.longueur > 0.5 && t.systeme !== 'Sans système');
  for (const t of shuffle(r, tubes).slice(0, 3)) {
    const id = `long_${t.systeme}_${t.materiau}_${t.designation}`;
    all.push({
      id,
      texte: `Longueur totale de tube ${/^[A-Z][a-zé]/.test(t.materiau) ? t.materiau.toLowerCase() : t.materiau} ${t.designation} sur le réseau « ${t.systeme} » (sans chutes) ?`,
      type: 'nombre',
      unite: 'm',
      reponse: Math.round(t.longueur * 100) / 100,
      tolPct: 5,
      tolAbs: 0.2,
      explication: `Somme des ${t.nb} tronçons de ${t.designation} du métré (onglet Métré).`,
    });
    if (!must.length) must.push(id);
  }
  // 2. bouches d'extraction
  const bouches = m.elements.filter(isExtractTerminal);
  if (bouches.length) {
    all.push({ id: 'nb_bouches', texte: "Combien de bouches d'extraction compte la maquette ?", type: 'nombre', reponse: bouches.length, explication: `Bouches : ${bouches.map((b) => b.name).join(', ')}.` });
    must.push('nb_bouches');
    const q = bouches.reduce((s, b) => s + (airFlow(b) ?? 0), 0);
    if (q > 0) all.push({ id: 'qv_extrait', texte: "Débit total d'extraction de la VMC (débits nominaux des bouches) ?", type: 'nombre', unite: 'm³/h', reponse: q, tolPct: 2, explication: 'Somme des débits nominaux des bouches d’extraction.' });
  }
  // 3. dimensionnement d'un émetteur
  const withEm = bilan.rooms.filter((x) => x.input.heated && x.emetteurs.length && x.ecartPct !== null && x.manquants === 0);
  if (withEm.length) {
    const off = withEm.filter((x) => x.verdict !== 'correct');
    const room = off.length && r() < 0.7 ? pick(r, off) : pick(r, withEm);
    const em = room.emetteurs.map((e) => e.name).join(' + ');
    const id = `dim_${room.input.spaceGid}`;
    all.push({
      id,
      texte: `${room.emetteurs.length > 1 ? 'Les émetteurs' : "L'émetteur"} de la pièce « ${room.input.name} » (${em}) ${room.emetteurs.length > 1 ? 'sont-ils' : 'est-il'} bien dimensionné${room.emetteurs.length > 1 ? 's' : ''} ? Hypothèses : Te = ${fmt(params.te, 0)} °C, Ti = ${fmt(room.input.ti, 0)} °C, méthode par parois, ponts thermiques + ${fmt(params.pontsPct, 0)} %, ventilation 0,34 × Qv × ΔT, puissance nominale des émetteurs. Correct si l'écart est entre ${fmt(params.seuilSous, 0)} % et + ${fmt(params.seuilSur, 0)} %.`,
      type: 'choix',
      choix: [VERDICT_LABEL.sous, VERDICT_LABEL.correct, VERDICT_LABEL.sur],
      reponse: VERDICT_LABEL[room.verdict],
      explication: `Déperditions ${fmt(room.phiTotal, 0)} W, émetteurs ${fmt(room.pEmis, 0)} W, écart ${fmt(room.ecartPct!, 1)} %.`,
    });
    must.push(id);
    const other = pick(r, bilan.rooms.filter((x) => x.input.heated && x.manquants === 0 && x.input.spaceGid !== room.input.spaceGid) || []);
    if (other)
      all.push({
        id: `phi_${other.input.spaceGid}`,
        texte: `Déperditions totales de la pièce « ${other.input.name} » (Te = ${fmt(params.te, 0)} °C, Ti = ${fmt(other.input.ti, 0)} °C, ponts thermiques + ${fmt(params.pontsPct, 0)} %, Qv = ${fmt(other.input.qv, 0)} m³/h) ?`,
        type: 'nombre',
        unite: 'W',
        reponse: Math.round(other.phiTotal),
        tolPct: 10,
        explication: `Φ parois ${fmt(other.phiParois, 0)} W + ponts ${fmt(other.phiPonts, 0)} W + ventilation ${fmt(other.phiVent, 0)} W.`,
      });
  }
  // 4. nombre d'émetteurs
  const rads = m.ofClass('IfcSpaceHeater');
  if (rads.length) all.push({ id: 'nb_emetteurs', texte: 'Combien d’émetteurs (radiateurs et sèche-serviettes) compte l’installation ?', type: 'nombre', reponse: rads.length, explication: 'Comptage des IfcSpaceHeater (onglet Nomenclature).' });
  // 5. puissance du générateur
  const gen = m.elements.find((e) => /ifcboiler/i.test(e.cls)) ?? m.elements.find((e) => /ifcunitaryequipment/i.test(e.cls) && /pompe|pac/i.test(`${e.name} ${e.objectType}`));
  const gp = gen ? powerW(gen) : null;
  if (gen && gp) all.push({ id: 'p_gen', texte: `Puissance nominale du générateur « ${gen.name} » ?`, type: 'nombre', unite: 'kW', reponse: gp / 1000, tolPct: 2, explication: 'Lue dans les propriétés de l’équipement.' });
  // 6. surface d'une pièce
  const sp = pick(r, bilan.rooms);
  if (sp) all.push({ id: `surf_${sp.input.spaceGid}`, texte: `Surface habitable de la pièce « ${sp.input.name} » ?`, type: 'nombre', unite: 'm²', reponse: Math.round(sp.input.area * 100) / 100, tolPct: 2, explication: 'Quantité NetFloorArea de l’IfcSpace.' });
  if (bilan.surfaceChauffee > 0) all.push({ id: 'surf_ch', texte: 'Surface totale des pièces chauffées ?', type: 'nombre', unite: 'm²', reponse: Math.round(bilan.surfaceChauffee * 100) / 100, tolPct: 3, explication: 'Somme des surfaces des pièces chauffées (cellier exclu).' });
  // 7. matériau du réseau ECS
  const mats = [...new Set(metre.tubes.map((t) => t.materiau))];
  const ecs = metre.tubes.find((t) => /eau chaude|ecs/i.test(t.systeme));
  if (ecs && mats.length >= 2) all.push({ id: 'mat_ecs', texte: 'Quel matériau est utilisé pour le réseau d’eau chaude sanitaire ?', type: 'choix', choix: mats, reponse: ecs.materiau, explication: `Réseau ${ecs.systeme} : ${ecs.materiau}.` });
  // 8. émetteur sans robinet thermostatique
  const trv = checkCoherence(m).filter((f) => f.regle === RULES.trv);
  if (trv.length === 1 && rads.length >= 3) {
    const bad = m.byId.get(trv[0].elementIds[0])!;
    const choix = shuffle(r, [bad.name, ...shuffle(r, rads.filter((x) => x.id !== bad.id)).slice(0, 3).map((x) => x.name)]);
    all.push({ id: 'sans_trv', texte: 'Quel émetteur n’est pas équipé de robinet thermostatique ?', type: 'choix', choix, reponse: bad.name, explication: 'Onglet Cohérence ou recherche des robinets à proximité de chaque émetteur.' });
  }
  // 9. vase d'expansion
  const vase = m.elements.find((e) => /ifctank/i.test(e.cls) && /EXPANSION/i.test(e.predefined));
  const pg = vase ? num(prop(vase, 'Pression de gonflage (bar)')) ?? (num(prop(vase, 'ChargePressure')) ?? 0) / 100000 : null;
  if (vase && pg) all.push({ id: 'vase', texte: `Pression de gonflage prescrite du vase d’expansion « ${vase.name} » ?`, type: 'nombre', unite: 'bar', reponse: pg, tolAbs: 0.05, explication: 'Propriété du vase d’expansion (fiche équipement).' });
  // 10. PAC : tonnes équivalent CO2
  const pac = m.elements.find((e) => fluidInfo(e)?.teqCO2);
  const fi = pac ? fluidInfo(pac) : null;
  if (pac && fi?.teqCO2) {
    all.push({ id: 'teq', texte: `Charge de la PAC en tonnes équivalent CO2 (fluide ${fi.fluide}, ${fmt(fi.chargeKg, 2)} kg, PRG ${fmt(fi.gwp ?? 0, 0)}) ?`, type: 'nombre', unite: 't éq. CO2', reponse: Math.round(fi.teqCO2 * 100) / 100, tolPct: 2, explication: 'Charge (kg) × PRG / 1000.' });
    all.push({ id: 'etanch', texte: 'Un contrôle d’étanchéité périodique est-il obligatoire pour cette PAC ?', type: 'choix', choix: ['Oui', 'Non'], reponse: fi.periodiciteMois ? 'Oui' : 'Non', explication: fi.texte });
  }
  // 11. coudes chauffage
  const coudes = metre.raccords.filter((x) => /chauffage/i.test(x.systeme) && /coude/i.test(x.categorie)).reduce((s, x) => s + x.nb, 0);
  if (coudes > 0) all.push({ id: 'coudes', texte: 'Combien de coudes compte le réseau de chauffage ?', type: 'nombre', reponse: coudes, explication: 'Comptage des raccords de type coude (onglet Métré).' });

  const chosen = all.filter((q) => must.includes(q.id));
  const rest = shuffle(r, all.filter((q) => !must.includes(q.id)));
  return [...chosen, ...rest].slice(0, Math.max(1, count));
}

export interface DefiResult {
  eleve: string;
  classe: string;
  date: string;
  seed: number;
  fichier: string;
  questions: Question[];
  reponses: string[];
  justes: boolean[];
  score: number;
}

export function scoreDefi(questions: Question[], reponses: string[]): { justes: boolean[]; score: number } {
  const justes = questions.map((q, i) => checkAnswer(q, reponses[i] ?? ''));
  return { justes, score: justes.filter(Boolean).length };
}
