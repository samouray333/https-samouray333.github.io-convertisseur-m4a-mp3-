import { mm } from './format';
import { predefFr } from './ifcTypesFr';
import { num, prop, text } from './props';
import type { El, Model } from './types';

export interface LengthRow {
  systeme: string;
  materiau: string;
  designation: string;
  nb: number;
  longueur: number;
  longueurChutes: number;
}

export interface CountRow {
  systeme: string;
  categorie: string;
  designation: string;
  nb: number;
}

export interface MetreResult {
  tubes: LengthRow[];
  gaines: LengthRow[];
  raccords: CountRow[];
  accessoires: CountRow[];
  chutesPct: number;
}

const PIPE = /^(ifcpipesegment|ifcflowsegment)$/i;
const DUCT = /^ifcductsegment$/i;
const PIPE_FIT = /^(ifcpipefitting|ifcflowfitting)$/i;
const DUCT_FIT = /^ifcductfitting$/i;
const ACCESS = /^(ifcvalve|ifcfilter|ifcflowmeter|ifcdamper|ifcductsilencer|ifcflowcontroller)$/i;

export function systemName(m: Model, e: El): string {
  const n = m.systemNames(e);
  return n.length ? n[0] : 'Sans système';
}

export function materialName(e: El): string {
  if (e.materials.length) return e.materials[0];
  const p = text(prop(e, 'Matériau') ?? prop(e, 'Material'));
  return p || 'Non renseigné';
}

/** Désignation d'un tube : intérieur x extérieur pour le cuivre / acier, extérieur x épaisseur pour PER et multicouche. */
export function pipeDesignation(e: El): string {
  let outer = num(prop(e, 'OuterDiameter')) ?? num(prop(e, 'NominalDiameter'));
  let inner = num(prop(e, 'InnerDiameter'));
  if (!outer && e.profile?.kind === 'circle' && e.profile.d) outer = e.profile.d;
  if (!inner && outer && e.profile?.kind === 'circle' && e.profile.wall) inner = outer - 2 * e.profile.wall;
  const mat = materialName(e).toLowerCase();
  if (outer && inner && inner < outer) {
    if (/cuivre|copper|acier|steel|inox/.test(mat)) return `${mm(inner)}x${mm(outer)}`;
    return `${mm(outer)}x${mm((outer - inner) / 2)}`;
  }
  if (outer) return `Ø${mm(outer)}`;
  const d = text(prop(e, 'Désignation') ?? prop(e, 'Reference') ?? prop(e, 'Size'));
  return d || 'Diamètre non renseigné';
}

export function ductDesignation(e: El): string {
  const w = num(prop(e, 'NominalDiameterOrWidth'));
  const h = num(prop(e, 'NominalHeight'));
  const shape = text(prop(e, 'Shape')).toUpperCase();
  if (w && h && shape !== 'ROUND') return `${mm(w)}x${mm(h)}`;
  if (w) return `Ø${mm(w)}`;
  if (e.profile?.kind === 'circle' && e.profile.d) return `Ø${mm(e.profile.d)}`;
  if (e.profile?.kind === 'rect' && e.profile.w && e.profile.h) return `${mm(e.profile.w)}x${mm(e.profile.h)}`;
  const d = text(prop(e, 'Désignation') ?? prop(e, 'Reference'));
  return d || 'Section non renseignée';
}

export function segmentLength(e: El): number {
  if (e.length && e.length > 0) return e.length;
  if (e.bbox) return Math.max(e.bbox[3] - e.bbox[0], e.bbox[4] - e.bbox[1], e.bbox[5] - e.bbox[2]);
  return 0;
}

function fittingCategory(e: El): string {
  const n = `${e.name} ${e.objectType}`.toLowerCase();
  if (/collecteur|nourrice|pieuvre|manifold/.test(n)) return 'Collecteur / nourrice';
  if (/coude|bend|elbow/.test(n)) return 'Coude';
  if (/\bt[ée]\b|tee/.test(n)) return 'Té';
  const p = predefFr(e.predefined);
  return p || e.objectType || 'Raccord';
}

function fittingSize(e: El): string {
  const d = text(prop(e, 'Désignation') ?? prop(e, 'Size') ?? prop(e, 'NominalDiameter'));
  if (/^\d/.test(d) || /^Ø/.test(d)) return d;
  return '';
}

export function accessoryCategory(e: El): string {
  if (e.objectType && !/^(USERDEFINED|NOTDEFINED)$/i.test(e.objectType) && e.objectType.toUpperCase() !== e.objectType) return e.objectType;
  const n = e.name.toLowerCase();
  if (/thermostat/.test(n)) return 'Robinet thermostatique';
  if (/t[ée] de r[ée]glage/.test(n)) return 'Té de réglage';
  if (/purgeur/.test(n)) return 'Purgeur';
  if (/groupe de s[ée]curit[ée]/.test(n)) return 'Groupe de sécurité';
  if (/soupape/.test(n)) return 'Soupape de sécurité';
  if (/r[ée]ducteur/.test(n)) return 'Réducteur de pression';
  if (/vanne d.isolement|robinet d.arr[êe]t/.test(n)) return "Vanne d'isolement / arrêt";
  if (/filtre/.test(n)) return 'Filtre';
  if (/robinet/.test(n)) return 'Robinet';
  return predefFr(e.predefined) || e.cls.replace(/^Ifc/, '');
}

function sortRows<T extends { systeme: string }>(rows: T[], key: (r: T) => string): T[] {
  return rows.sort((a, b) => a.systeme.localeCompare(b.systeme, 'fr') || key(a).localeCompare(key(b), 'fr', { numeric: true }));
}

export function computeMetre(m: Model, chutesPct = 0): MetreResult {
  const k = 1 + chutesPct / 100;
  const tubes = new Map<string, LengthRow>();
  const gaines = new Map<string, LengthRow>();
  const raccords = new Map<string, CountRow>();
  const accessoires = new Map<string, CountRow>();
  for (const e of m.elements) {
    const sys = systemName(m, e);
    if (PIPE.test(e.cls) || DUCT.test(e.cls)) {
      const isPipe = PIPE.test(e.cls);
      const mat = materialName(e);
      const des = isPipe ? pipeDesignation(e) : ductDesignation(e);
      const key = `${sys}|${mat}|${des}`;
      const map = isPipe ? tubes : gaines;
      const row = map.get(key) ?? { systeme: sys, materiau: mat, designation: des, nb: 0, longueur: 0, longueurChutes: 0 };
      row.nb++;
      row.longueur += segmentLength(e);
      map.set(key, row);
    } else if (PIPE_FIT.test(e.cls) || DUCT_FIT.test(e.cls)) {
      const cat = (DUCT_FIT.test(e.cls) ? 'Gaine : ' : '') + fittingCategory(e);
      const des = fittingSize(e);
      const key = `${sys}|${cat}|${des}`;
      const row = raccords.get(key) ?? { systeme: sys, categorie: cat, designation: des, nb: 0 };
      row.nb++;
      raccords.set(key, row);
    } else if (ACCESS.test(e.cls)) {
      const cat = accessoryCategory(e);
      const key = `${sys}|${cat}`;
      const row = accessoires.get(key) ?? { systeme: sys, categorie: cat, designation: '', nb: 0 };
      row.nb++;
      accessoires.set(key, row);
    }
  }
  for (const r of [...tubes.values(), ...gaines.values()]) {
    r.longueur = Math.round(r.longueur * 1000) / 1000;
    r.longueurChutes = Math.round(r.longueur * k * 100) / 100;
  }
  return {
    tubes: sortRows([...tubes.values()], (r) => r.materiau + r.designation),
    gaines: sortRows([...gaines.values()], (r) => r.materiau + r.designation),
    raccords: sortRows([...raccords.values()], (r) => r.categorie + r.designation),
    accessoires: sortRows([...accessoires.values()], (r) => r.categorie),
    chutesPct,
  };
}

/** Longueur totale (m) pour un système, un matériau (sous-chaîne) et une désignation. */
export function totalLength(res: MetreResult, opts: { systeme?: RegExp; materiau?: RegExp; designation?: string }): number {
  return [...res.tubes, ...res.gaines]
    .filter((r) => (!opts.systeme || opts.systeme.test(r.systeme)) && (!opts.materiau || opts.materiau.test(r.materiau)) && (!opts.designation || r.designation === opts.designation))
    .reduce((s, r) => s + r.longueur, 0);
}
