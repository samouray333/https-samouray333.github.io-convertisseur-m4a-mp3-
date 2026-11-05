import { mm } from './format';
import { predefFr } from './ifcTypesFr';
import { num, prop, text } from './props';
import type { El, Model } from './types';

export interface Conditionnement {
  /** ex. « Barre de 4 m », « Couronne de 100 m » */
  libelle: string;
  longueur: number;
}

export interface LengthRow {
  systeme: string;
  lot: string;
  materiau: string;
  designation: string;
  nb: number;
  longueur: number;
  longueurChutes: number;
  /** éléments IFC comptés (pour les voir en 3D) */
  ids: number[];
  niveaux: string[];
  /** diamètre intérieur (m) pour les tubes */
  dInt: number | null;
  /** contenance en eau (L) pour les tubes */
  volumeL: number;
  /** surface développée (m²) pour les gaines : périmètre x longueur, chutes comprises */
  surfaceM2: number;
  conditionnement: Conditionnement;
  aCommander: number;
  /** estimation des colliers de fixation */
  colliers: number;
  entraxeColliers: number;
}

export interface CountRow {
  systeme: string;
  categorie: string;
  designation: string;
  nb: number;
  ids: number[];
}

export interface SystemSummary {
  systeme: string;
  lot: string;
  tubesM: number;
  gainesM: number;
  volumeL: number;
  surfaceM2: number;
  raccords: number;
  accessoires: number;
}

export interface MetreOptions {
  chutesPct?: number;
  /** limiter à un niveau (id IfcBuildingStorey) */
  storeyId?: number | null;
  /** limiter à un réseau (nom du système) */
  systeme?: string | null;
}

export interface MetreResult {
  tubes: LengthRow[];
  gaines: LengthRow[];
  raccords: CountRow[];
  accessoires: CountRow[];
  chutesPct: number;
  systemes: SystemSummary[];
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

/** Diamètres extérieur et intérieur (m) d'un tube, depuis les propriétés ou le profil. */
export function pipeDiameters(e: El): { outer: number | null; inner: number | null } {
  let outer = num(prop(e, 'OuterDiameter')) ?? num(prop(e, 'NominalDiameter'));
  let inner = num(prop(e, 'InnerDiameter'));
  if (!outer && e.profile?.kind === 'circle' && e.profile.d) outer = e.profile.d;
  if (!inner && outer && e.profile?.kind === 'circle' && e.profile.wall) inner = outer - 2 * e.profile.wall;
  return { outer, inner };
}

/** Périmètre (m) d'une gaine, ronde ou rectangulaire. */
export function ductPerimeter(e: El): number {
  const w = num(prop(e, 'NominalDiameterOrWidth')) ?? (e.profile?.kind === 'rect' ? e.profile.w ?? null : e.profile?.d ?? null);
  const h = num(prop(e, 'NominalHeight')) ?? (e.profile?.kind === 'rect' ? e.profile.h ?? null : null);
  const shape = text(prop(e, 'Shape')).toUpperCase();
  if (w && h && shape !== 'ROUND') return 2 * (w + h);
  return w ? Math.PI * w : 0;
}

/** Conditionnement usuel du commerce (hypothèses affichées dans l'appli). */
export function conditionnement(materiau: string, outerM: number | null, gaine: boolean, souple: boolean): Conditionnement {
  const mat = materiau.toLowerCase();
  const d = (outerM ?? 0) * 1000;
  if (gaine) {
    if (souple || /souple|flexible/.test(mat)) return { libelle: 'Rouleau de 10 m', longueur: 10 };
    if (/rectangul/.test(mat)) return { libelle: 'Tronçon de 1,5 m', longueur: 1.5 };
    return { libelle: 'Conduit de 3 m', longueur: 3 };
  }
  if (/frigo/.test(mat)) return { libelle: 'Couronne de 25 m', longueur: 25 };
  if (/cuivre|copper/.test(mat)) return d <= 22 ? { libelle: 'Barre de 4 m', longueur: 4 } : { libelle: 'Barre de 5 m', longueur: 5 };
  if (/multicouche|alu/.test(mat)) return d <= 20 ? { libelle: 'Couronne de 100 m', longueur: 100 } : { libelle: 'Barre de 5 m', longueur: 5 };
  if (/per|pe-x|pex|polyéthylène/.test(mat)) return d <= 20 ? { libelle: 'Couronne de 100 m', longueur: 100 } : { libelle: 'Couronne de 50 m', longueur: 50 };
  if (/acier|steel|inox/.test(mat)) return { libelle: 'Barre de 6 m', longueur: 6 };
  if (/pvc|pp|pehd/.test(mat)) return { libelle: 'Barre de 4 m', longueur: 4 };
  return { libelle: 'Au mètre', longueur: 1 };
}

/** Entraxe indicatif des colliers en pose horizontale (m). */
export function entraxeColliers(materiau: string, outerM: number | null, gaine: boolean): number {
  const mat = materiau.toLowerCase();
  const d = (outerM ?? 0) * 1000;
  if (gaine) return /souple/.test(mat) ? 1.0 : 1.5;
  if (/cuivre|copper/.test(mat)) return d <= 22 ? 1.25 : 1.8;
  if (/multicouche|alu/.test(mat)) return d <= 20 ? 1.0 : 1.5;
  if (/per|pe-x|pex/.test(mat)) return 0.8;
  if (/acier|steel/.test(mat)) return d <= 40 ? 2.5 : 3.0;
  return 1.5;
}

export function computeMetre(m: Model, opts: number | MetreOptions = 0): MetreResult {
  const o: MetreOptions = typeof opts === 'number' ? { chutesPct: opts } : opts;
  const chutesPct = o.chutesPct ?? 0;
  const k = 1 + chutesPct / 100;
  const tubes = new Map<string, LengthRow>();
  const gaines = new Map<string, LengthRow>();
  const raccords = new Map<string, CountRow>();
  const accessoires = new Map<string, CountRow>();
  const lotOf = (e: El) => (e.systemIds.length ? m.systemById.get(e.systemIds[0])?.lot ?? e.lot : e.lot);
  for (const e of m.elements) {
    if (o.storeyId != null && e.storeyId !== o.storeyId) continue;
    const sys = systemName(m, e);
    if (o.systeme && sys !== o.systeme) continue;
    const niveau = e.storeyId !== null ? m.storeyById.get(e.storeyId)?.name ?? '' : '';
    if (PIPE.test(e.cls) || DUCT.test(e.cls)) {
      const isPipe = PIPE.test(e.cls);
      const mat = materialName(e);
      const des = isPipe ? pipeDesignation(e) : ductDesignation(e);
      const key = `${sys}|${mat}|${des}`;
      const map = isPipe ? tubes : gaines;
      const dia = isPipe ? pipeDiameters(e) : { outer: num(prop(e, 'NominalDiameterOrWidth')), inner: null };
      let row = map.get(key);
      if (!row) {
        const souple = /FLEXIBLE/i.test(e.predefined);
        row = {
          systeme: sys, lot: lotOf(e), materiau: mat, designation: des, nb: 0, longueur: 0, longueurChutes: 0, ids: [], niveaux: [],
          dInt: isPipe ? dia.inner : null, volumeL: 0, surfaceM2: 0,
          conditionnement: conditionnement(mat, dia.outer, !isPipe, souple), aCommander: 0, colliers: 0, entraxeColliers: entraxeColliers(mat, dia.outer, !isPipe),
        };
        map.set(key, row);
      }
      const L = segmentLength(e);
      row.nb++;
      row.longueur += L;
      row.ids.push(e.id);
      if (niveau && !row.niveaux.includes(niveau)) row.niveaux.push(niveau);
      if (isPipe && dia.inner) row.volumeL += ((Math.PI * dia.inner * dia.inner) / 4) * L * 1000;
      if (!isPipe) row.surfaceM2 += ductPerimeter(e) * L;
      row.colliers += Math.ceil(L / row.entraxeColliers);
    } else if (PIPE_FIT.test(e.cls) || DUCT_FIT.test(e.cls)) {
      const cat = (DUCT_FIT.test(e.cls) ? 'Gaine : ' : '') + fittingCategory(e);
      const des = fittingSize(e);
      const key = `${sys}|${cat}|${des}`;
      const row = raccords.get(key) ?? { systeme: sys, categorie: cat, designation: des, nb: 0, ids: [] };
      row.nb++;
      row.ids.push(e.id);
      raccords.set(key, row);
    } else if (ACCESS.test(e.cls)) {
      const cat = accessoryCategory(e);
      const key = `${sys}|${cat}`;
      const row = accessoires.get(key) ?? { systeme: sys, categorie: cat, designation: '', nb: 0, ids: [] };
      row.nb++;
      row.ids.push(e.id);
      accessoires.set(key, row);
    }
  }
  for (const r of [...tubes.values(), ...gaines.values()]) {
    r.longueur = Math.round(r.longueur * 1000) / 1000;
    r.longueurChutes = Math.round(r.longueur * k * 100) / 100;
    r.volumeL = Math.round(r.volumeL * 100) / 100;
    r.surfaceM2 = Math.round(r.surfaceM2 * k * 100) / 100;
    r.aCommander = Math.ceil(r.longueurChutes / r.conditionnement.longueur - 1e-9);
  }
  const sum = new Map<string, SystemSummary>();
  const get = (sys: string, lot: string) => {
    if (!sum.has(sys)) sum.set(sys, { systeme: sys, lot, tubesM: 0, gainesM: 0, volumeL: 0, surfaceM2: 0, raccords: 0, accessoires: 0 });
    return sum.get(sys)!;
  };
  for (const r of tubes.values()) {
    const x = get(r.systeme, r.lot);
    x.tubesM += r.longueur;
    x.volumeL += r.volumeL;
  }
  for (const r of gaines.values()) {
    const x = get(r.systeme, r.lot);
    x.gainesM += r.longueur;
    x.surfaceM2 += r.surfaceM2;
  }
  for (const r of raccords.values()) get(r.systeme, 'autres').raccords += r.nb;
  for (const r of accessoires.values()) get(r.systeme, 'autres').accessoires += r.nb;
  return {
    tubes: sortRows([...tubes.values()], (r) => r.materiau + r.designation),
    gaines: sortRows([...gaines.values()], (r) => r.materiau + r.designation),
    raccords: sortRows([...raccords.values()], (r) => r.categorie + r.designation),
    accessoires: sortRows([...accessoires.values()], (r) => r.categorie),
    chutesPct,
    systemes: [...sum.values()].sort((a, b) => a.systeme.localeCompare(b.systeme, 'fr')),
  };
}

/** Longueur totale (m) pour un système, un matériau (sous-chaîne) et une désignation. */
export function totalLength(res: MetreResult, opts: { systeme?: RegExp; materiau?: RegExp; designation?: string }): number {
  return [...res.tubes, ...res.gaines]
    .filter((r) => (!opts.systeme || opts.systeme.test(r.systeme)) && (!opts.materiau || opts.materiau.test(r.materiau)) && (!opts.designation || r.designation === opts.designation))
    .reduce((s, r) => s + r.longueur, 0);
}
