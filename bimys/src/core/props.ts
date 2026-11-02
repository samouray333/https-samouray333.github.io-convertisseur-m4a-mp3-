import type { BBox, El, PropValue } from './types';

/** Recherche une propriété par nom (exact puis insensible à la casse) dans tous les Psets. */
export function prop(e: El, name: string, psetName?: string): PropValue {
  const sets = psetName ? [e.psets[psetName]].filter(Boolean) : Object.values(e.psets);
  for (const ps of sets) if (ps && name in ps && ps[name] !== null && ps[name] !== '') return ps[name];
  const ln = name.toLowerCase();
  for (const ps of sets) for (const [k, v] of Object.entries(ps ?? {})) if (k.toLowerCase() === ln && v !== null && v !== '') return v;
  return null;
}

export function propMatch(e: El, re: RegExp): { key: string; value: PropValue } | null {
  for (const ps of Object.values(e.psets)) for (const [k, v] of Object.entries(ps)) if (re.test(k) && v !== null && v !== '') return { key: k, value: v };
  return null;
}

export function num(x: PropValue): number | null {
  if (typeof x === 'number' && Number.isFinite(x)) return x;
  if (typeof x === 'string') {
    const n = Number(x.replace(',', '.').replace(/[^\d.+-eE]/g, ''));
    return Number.isFinite(n) && x.trim() !== '' ? n : null;
  }
  return null;
}

export function text(x: PropValue): string {
  if (x === null || x === undefined) return '';
  if (typeof x === 'boolean') return x ? 'Oui' : 'Non';
  return String(x);
}

/** Puissance nominale d'un émetteur ou d'un générateur, en watts. */
export function powerW(e: El): number | null {
  const oc = num(prop(e, 'OutputCapacity'));
  if (oc !== null && oc > 0) return oc;
  const w = propMatch(e, /puissance.*\(w\)/i);
  if (w && num(w.value) !== null) return num(w.value)!;
  const kw = propMatch(e, /puissance.*\(kw\)/i);
  if (kw && num(kw.value) !== null) return num(kw.value)! * 1000;
  for (const k of ['NominalPower', 'NominalOutput', 'HeatingCapacity', 'Puissance']) {
    const v = num(prop(e, k));
    if (v !== null && v > 0) return v < 100 ? v * 1000 : v;
  }
  return null;
}

export function brand(e: El): string {
  return text(prop(e, 'Marque') ?? prop(e, 'Manufacturer') ?? prop(e, 'Fabricant'));
}

export function model(e: El): string {
  return text(prop(e, 'Modèle') ?? prop(e, 'ModelLabel') ?? prop(e, 'ModelReference') ?? prop(e, 'Modele'));
}

export function serial(e: El): string {
  return text(prop(e, 'Numéro de série') ?? prop(e, 'SerialNumber'));
}

export function commissioningDate(e: El): string {
  return text(prop(e, 'Date de mise en service') ?? prop(e, 'InstallationDate') ?? prop(e, 'AcquisitionDate'));
}

export function label(e: El): string {
  return e.name || e.objectType || e.typeName || e.cls;
}

export function bboxCenter(b: BBox): [number, number, number] {
  return [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
}

/** Distance entre deux boîtes (0 si elles se touchent). */
export function bboxDistance(a: BBox, b: BBox): number {
  const dx = Math.max(0, a[0] - b[3], b[0] - a[3]);
  const dy = Math.max(0, a[1] - b[4], b[1] - a[4]);
  const dz = Math.max(0, a[2] - b[5], b[2] - a[5]);
  return Math.hypot(dx, dy, dz);
}

export function pointInBBox(p: [number, number, number], b: BBox, tol = 0.01): boolean {
  return p[0] >= b[0] - tol && p[0] <= b[3] + tol && p[1] >= b[1] - tol && p[1] <= b[4] + tol && p[2] >= b[2] - tol && p[2] <= b[5] + tol;
}

export function isThermostaticValve(e: El): boolean {
  return /ifcvalve/i.test(e.cls) && /thermosta/i.test(`${e.name} ${e.objectType} ${e.typeName}`);
}

export function isExtractTerminal(e: El): boolean {
  if (!/ifcairterminal/i.test(e.cls)) return false;
  const s = `${e.name} ${e.objectType} ${e.typeName} ${text(prop(e, 'Fonction'))}`.toLowerCase();
  if (/entr[ée]e d.air|soufflage|insufflation|supply/.test(s)) return false;
  return /extract|bouche|reprise|exhaust/.test(s);
}

export function isAirInlet(e: El): boolean {
  if (!/ifcairterminal/i.test(e.cls)) return false;
  return /entr[ée]e d.air|air inlet/i.test(`${e.name} ${e.objectType} ${e.typeName} ${text(prop(e, 'Fonction'))}`);
}

export function airFlow(e: El): number | null {
  const q = propMatch(e, /d[ée]bit nominal/i) ?? propMatch(e, /d[ée]bit/i);
  if (q) return num(q.value);
  const f = num(prop(e, 'AirFlowRate') ?? prop(e, 'NominalAirFlowRate'));
  return f !== null ? f * 3600 : null; // m³/s -> m³/h
}
