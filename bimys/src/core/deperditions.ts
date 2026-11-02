// Déperditions par pièce : méthode par parois et méthode volumique (G x V x ΔT),
// comparaison avec la puissance des émetteurs présents.
import { airFlow, bboxCenter, isAirInlet, num, pointInBBox, powerW, prop } from './props';
import type { El, Model } from './types';

export type ParoiType = 'Mur' | 'Fenêtre' | 'Porte' | 'Plancher bas' | 'Plafond' | 'Toiture' | 'Autre';
export const PAROI_TYPES: ParoiType[] = ['Mur', 'Fenêtre', 'Porte', 'Plancher bas', 'Plafond', 'Toiture', 'Autre'];

export interface Paroi {
  id: string;
  label: string;
  type: ParoiType;
  area: number | null;
  u: number | null;
  /** coefficient de réduction de température b (1 pour l'extérieur) */
  tau: number;
  source: 'maquette' | 'saisie';
}

export interface RoomInput {
  spaceGid: string;
  name: string;
  storey: string;
  area: number;
  volume: number;
  heated: boolean;
  ti: number;
  /** débit d'air neuf entrant dans la pièce (m³/h) */
  qv: number;
  parois: Paroi[];
}

export interface DepParams {
  te: number;
  method: 'parois' | 'volumique';
  /** coefficient volumique G (W/m³.K) pour la méthode volumique */
  g: number;
  /** majoration forfaitaire pour ponts thermiques (% des déperditions par parois) */
  pontsPct: number;
  correctionRegime: boolean;
  tDepart: number;
  tRetour: number;
  nExp: number;
  /** écart (%) en dessous duquel l'émetteur est sous-dimensionné */
  seuilSous: number;
  /** écart (%) au-dessus duquel l'émetteur est surdimensionné */
  seuilSur: number;
}

export const DEFAULT_PARAMS: DepParams = {
  te: -10,
  method: 'parois',
  g: 0.75,
  pontsPct: 10,
  correctionRegime: false,
  tDepart: 70,
  tRetour: 50,
  nExp: 1.3,
  seuilSous: -5,
  seuilSur: 30,
};

export type Verdict = 'sous' | 'correct' | 'sur' | 'aucun' | 'non_chauffe';

export const VERDICT_LABEL: Record<Verdict, string> = {
  sous: 'Sous-dimensionné',
  correct: 'Correct',
  sur: 'Surdimensionné',
  aucun: 'Aucun émetteur',
  non_chauffe: 'Non chauffée',
};

export interface EmitterInfo {
  id: number;
  gid: string;
  name: string;
  pNom: number;
  pCorr: number;
}

export interface RoomResult {
  input: RoomInput;
  dT: number;
  /** Σ U.S.b par paroi (W/K) */
  ubs: number;
  phiParois: number;
  phiPonts: number;
  phiVent: number;
  phiTotal: number;
  emetteurs: EmitterInfo[];
  pEmis: number;
  ecartPct: number | null;
  verdict: Verdict;
  manquants: number;
}

export function defaultTi(name: string): number {
  const n = name.toLowerCase();
  if (/bain|sdb|salle d.eau|douche/.test(n)) return 22;
  if (/s[ée]jour|salon|salle [àa] manger|living|bureau|pi[èe]ce de vie/.test(n)) return 20;
  return 19;
}

export function defaultHeated(name: string): boolean {
  return !/cellier|garage|chaufferie|cave|local technique|combles|buanderie non|abri/i.test(name);
}

export function paroiType(e: El | undefined, normalZ: number): ParoiType {
  if (!e) return normalZ < -0.5 ? 'Plancher bas' : normalZ > 0.5 ? 'Plafond' : 'Autre';
  const c = e.cls.toLowerCase();
  if (c.startsWith('ifcwall') || c === 'ifccurtainwall') return 'Mur';
  if (c === 'ifcwindow') return 'Fenêtre';
  if (c === 'ifcdoor') return 'Porte';
  if (c === 'ifcroof') return 'Toiture';
  if (c === 'ifcslab' || c === 'ifccovering') {
    if (/ROOF/i.test(e.predefined)) return 'Toiture';
    if (/BASESLAB/i.test(e.predefined) || normalZ < -0.5) return 'Plancher bas';
    if (normalZ > 0.5) return 'Plafond';
    return 'Plancher bas';
  }
  return 'Autre';
}

export function uValue(e: El | undefined): number | null {
  if (!e) return null;
  const u = num(prop(e, 'ThermalTransmittance'));
  if (u !== null && u > 0) return u;
  const m = Object.values(e.psets).flatMap((ps) => Object.entries(ps)).find(([k]) => /^U\b|coefficient u|transmission thermique/i.test(k));
  return m ? num(m[1]) : null;
}

export function spaceArea(e: El): number {
  for (const q of Object.values(e.qtos)) {
    if (typeof q.NetFloorArea === 'number') return q.NetFloorArea;
    if (typeof q.GrossFloorArea === 'number') return q.GrossFloorArea;
  }
  const a = num(prop(e, 'NetFloorArea') ?? prop(e, 'Surface'));
  if (a) return a;
  if (e.bbox) return (e.bbox[3] - e.bbox[0]) * (e.bbox[4] - e.bbox[1]);
  return 0;
}

export function spaceHeight(e: El): number {
  for (const q of Object.values(e.qtos)) {
    if (typeof q.Height === 'number') return q.Height;
    if (typeof q.FinishCeilingHeight === 'number') return q.FinishCeilingHeight;
  }
  if (e.bbox) return e.bbox[5] - e.bbox[2];
  return 2.5;
}

export function spaceVolume(e: El): number {
  for (const q of Object.values(e.qtos)) {
    if (typeof q.NetVolume === 'number') return q.NetVolume;
    if (typeof q.GrossVolume === 'number') return q.GrossVolume;
  }
  return spaceArea(e) * spaceHeight(e);
}

/** Éléments situés dans une pièce : rattachés à l'IfcSpace ou dont le centre est dans le volume de la pièce. */
export function elementsInSpace(m: Model, space: El, filter: (e: El) => boolean): El[] {
  return m.elements.filter((e) => {
    if (!filter(e)) return false;
    if (e.spaceId === space.id) return true;
    if (e.spaceId !== null || !e.bbox || !space.bbox) return false;
    return pointInBBox(bboxCenter(e.bbox), space.bbox, 0.05);
  });
}

export function emittersOf(m: Model, space: El): El[] {
  return elementsInSpace(m, space, (e) => /^ifcspaceheater$/i.test(e.cls));
}

/** Pré-remplit la saisie d'une pièce à partir de la maquette. */
export function roomInputFromModel(m: Model, space: El): RoomInput {
  const parois: Paroi[] = [];
  let i = 0;
  for (const b of m.data.boundaries) {
    if (b.spaceId !== space.id || !b.external) continue;
    const el = b.elementId !== null ? m.byId.get(b.elementId) : undefined;
    const type = paroiType(el, b.normalZ);
    parois.push({
      id: `b${i++}`,
      label: el?.name || type,
      type,
      area: Math.round(b.area * 1000) / 1000,
      u: uValue(el),
      tau: 1,
      source: 'maquette',
    });
  }
  const order = (t: ParoiType) => PAROI_TYPES.indexOf(t);
  parois.sort((a, b) => order(a.type) - order(b.type) || a.label.localeCompare(b.label, 'fr'));
  const inlets = elementsInSpace(m, space, isAirInlet);
  const qv = inlets.reduce((s, e) => s + (airFlow(e) ?? 0), 0);
  const name = space.name || 'Pièce';
  return {
    spaceGid: space.gid,
    name,
    storey: space.storeyId !== null ? m.storeyById.get(space.storeyId)?.name ?? '' : '',
    area: Math.round(spaceArea(space) * 1000) / 1000,
    volume: Math.round(spaceVolume(space) * 1000) / 1000,
    heated: defaultHeated(name),
    ti: defaultTi(name),
    qv,
    parois,
  };
}

export function regimeFactor(p: DepParams, ti: number): number {
  if (!p.correctionRegime) return 1;
  const tm = (p.tDepart + p.tRetour) / 2;
  const dt = tm - ti;
  if (dt <= 0) return 0;
  return Math.pow(dt / 50, p.nExp);
}

export function computeRoom(input: RoomInput, p: DepParams, emitters: { id: number; gid: string; name: string; pNom: number }[]): RoomResult {
  const dT = input.ti - p.te;
  let ubs = 0;
  let manquants = 0;
  for (const w of input.parois) {
    if (w.area === null || w.u === null) {
      manquants++;
      continue;
    }
    ubs += w.u * w.area * (w.tau ?? 1);
  }
  let phiParois = 0, phiPonts = 0, phiVent = 0, phiTotal = 0;
  if (p.method === 'parois') {
    phiParois = ubs * dT;
    phiPonts = (phiParois * p.pontsPct) / 100;
    phiVent = 0.34 * input.qv * dT;
    phiTotal = phiParois + phiPonts + phiVent;
  } else {
    phiTotal = p.g * input.volume * dT;
  }
  const f = regimeFactor(p, input.ti);
  const em: EmitterInfo[] = emitters.map((e) => ({ ...e, pCorr: e.pNom * f }));
  const pEmis = em.reduce((s, e) => s + e.pCorr, 0);
  let verdict: Verdict;
  let ecartPct: number | null = null;
  if (!input.heated) verdict = 'non_chauffe';
  else if (!em.length) {
    verdict = 'aucun';
    ecartPct = phiTotal > 0 ? -100 : null;
  } else {
    ecartPct = phiTotal > 0 ? ((pEmis - phiTotal) / phiTotal) * 100 : null;
    if (ecartPct === null) verdict = 'correct';
    else if (ecartPct < p.seuilSous) verdict = 'sous';
    else if (ecartPct > p.seuilSur) verdict = 'sur';
    else verdict = 'correct';
  }
  return { input, dT, ubs, phiParois, phiPonts, phiVent, phiTotal, emetteurs: em, pEmis, ecartPct, verdict, manquants };
}

export function emitterInfos(m: Model, space: El): { id: number; gid: string; name: string; pNom: number }[] {
  return emittersOf(m, space).map((e) => ({ id: e.id, gid: e.gid, name: e.name || 'Émetteur', pNom: powerW(e) ?? 0 }));
}

export interface Bilan {
  rooms: RoomResult[];
  totalPhi: number;
  totalEmis: number;
  surfaceChauffee: number;
  volumeChauffe: number;
}

/** Calcul complet ; `overrides` contient les saisies de l'élève par GlobalId de pièce. */
export function computeBilan(m: Model, p: DepParams, overrides: Record<string, RoomInput> = {}): Bilan {
  const rooms: RoomResult[] = [];
  for (const sp of m.spaces()) {
    const input = overrides[sp.gid] ?? roomInputFromModel(m, sp);
    rooms.push(computeRoom(input, p, emitterInfos(m, sp)));
  }
  rooms.sort((a, b) => a.input.storey.localeCompare(b.input.storey, 'fr') || a.input.name.localeCompare(b.input.name, 'fr', { numeric: true }));
  const heated = rooms.filter((r) => r.input.heated);
  return {
    rooms,
    totalPhi: heated.reduce((s, r) => s + r.phiTotal, 0),
    totalEmis: heated.reduce((s, r) => s + r.pEmis, 0),
    surfaceChauffee: heated.reduce((s, r) => s + r.input.area, 0),
    volumeChauffe: heated.reduce((s, r) => s + r.input.volume, 0),
  };
}
