import defaultConfig from '../data/maintenance.json';
import { commissioningDate, num, prop, propMatch, text } from './props';
import type { El, Model } from './types';

export interface CheckItem {
  id: string;
  libelle: string;
}
export interface MesureDef {
  id: string;
  libelle: string;
  unite: string;
  min?: number;
  max?: number;
}
export interface MaintType {
  id: string;
  libelle: string;
  detection: { classes: string[]; predefinis?: string[]; motsCles?: string[] };
  periodiciteMois: number;
  etancheite?: boolean;
  reglementation: string;
  checklist: CheckItem[];
  mesures: MesureDef[];
}
export interface MaintConfig {
  version: number;
  fluides: Record<string, number>;
  types: MaintType[];
}

export const DEFAULT_MAINT: MaintConfig = defaultConfig as unknown as MaintConfig;

export interface Intervention {
  id: string;
  fileKey: string;
  gid: string;
  elementName: string;
  date: string;
  intervenant: string;
  type: 'preventive' | 'corrective';
  statut: 'en_cours' | 'terminee';
  checklist: Record<string, 'ok' | 'nok' | 'na' | ''>;
  mesures: Record<string, string>;
  observations: string;
  pieces: string;
  photo?: string;
  signature?: string;
  createdAt: number;
}

export type MaintStatus = 'en_cours' | 'retard' | 'a_prevoir' | 'a_jour' | 'inconnu';

export const STATUS_LABEL: Record<MaintStatus, string> = {
  en_cours: 'Intervention en cours',
  retard: 'En retard',
  a_prevoir: 'À prévoir (< 30 jours)',
  a_jour: 'À jour',
  inconnu: 'Date inconnue',
};

function kwMatch(hay: string, kw: string): boolean {
  const k = kw.toLowerCase();
  if (k.length <= 4) return new RegExp(`(^|[^a-zà-ÿ0-9])${k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-zà-ÿ0-9]|$)`, 'i').test(hay);
  return hay.includes(k);
}

export function maintTypeOf(e: El, cfg: MaintConfig = DEFAULT_MAINT): MaintType | null {
  const cls = e.cls.toLowerCase();
  const hay = `${e.name} ${e.objectType} ${e.typeName}`.toLowerCase();
  for (const t of cfg.types) {
    if (!t.detection.classes.some((c) => c.toLowerCase() === cls)) continue;
    const pre = t.detection.predefinis ?? [];
    const kws = t.detection.motsCles ?? [];
    const preOk = pre.length && pre.some((p) => p.toUpperCase() === e.predefined.toUpperCase());
    const kwOk = kws.length && kws.some((k) => kwMatch(hay, k));
    if (!pre.length && !kws.length) return t;
    if (preOk || kwOk) return t;
  }
  return null;
}

export function maintainable(m: Model, cfg: MaintConfig = DEFAULT_MAINT): { el: El; type: MaintType }[] {
  const out: { el: El; type: MaintType }[] = [];
  for (const e of m.elements) {
    const t = maintTypeOf(e, cfg);
    if (t) out.push({ el: e, type: t });
  }
  const order = (t: MaintType) => cfg.types.indexOf(t);
  return out.sort((a, b) => order(a.type) - order(b.type) || a.el.name.localeCompare(b.el.name, 'fr'));
}

// ------------------------------------------------------------ fluides frigorigènes
export interface FluidInfo {
  fluide: string;
  chargeKg: number;
  gwp: number | null;
  teqCO2: number | null;
  hermetique: boolean;
  periodiciteMois: number | null;
  texte: string;
}

export function fluidInfo(e: El, cfg: MaintConfig = DEFAULT_MAINT): FluidInfo | null {
  const fl = text(prop(e, 'Fluide frigorigène') ?? prop(e, 'Refrigerant') ?? prop(e, 'RefrigerantType'));
  const ch = num(prop(e, 'Charge en fluide (kg)') ?? propMatch(e, /charge.*(fluide|frigo)/i)?.value ?? prop(e, 'RefrigerantCharge'));
  if (!fl && ch === null) return null;
  const key = Object.keys(cfg.fluides).find((k) => k.toLowerCase() === fl.replace(/\s/g, '').toLowerCase());
  const gwp = num(prop(e, 'PRG du fluide (GWP)')) ?? (key ? cfg.fluides[key] : null);
  const herm = prop(e, 'Circuit hermétiquement scellé') === true;
  const teq = gwp !== null && ch !== null ? (ch * gwp) / 1000 : null;
  const p = leakCheckPeriod(teq, herm);
  return { fluide: fl || 'Non renseigné', chargeKg: ch ?? 0, gwp, teqCO2: teq, hermetique: herm, periodiciteMois: p.mois, texte: p.texte };
}

/** Périodicité du contrôle d'étanchéité (règlement UE 2024/573, art. 5). */
export function leakCheckPeriod(teq: number | null, hermetique: boolean): { mois: number | null; texte: string } {
  if (teq === null) return { mois: null, texte: 'Charge ou fluide inconnu : impossible de déterminer la périodicité.' };
  if (hermetique && teq < 10) return { mois: null, texte: 'Équipement hermétiquement scellé de moins de 10 t éq. CO2 : pas de contrôle périodique obligatoire.' };
  if (teq < 5) return { mois: null, texte: 'Moins de 5 t éq. CO2 : pas de contrôle d’étanchéité périodique obligatoire (contrôle recommandé à l’entretien).' };
  if (teq < 50) return { mois: 12, texte: 'Entre 5 et 50 t éq. CO2 : contrôle d’étanchéité tous les 12 mois (24 mois avec détection permanente de fuites).' };
  if (teq < 500) return { mois: 6, texte: 'Entre 50 et 500 t éq. CO2 : contrôle d’étanchéité tous les 6 mois (12 mois avec détection de fuites).' };
  return { mois: 3, texte: 'Au moins 500 t éq. CO2 : contrôle d’étanchéité tous les 3 mois, détection de fuites obligatoire.' };
}

export function effectivePeriod(e: El, t: MaintType, cfg: MaintConfig = DEFAULT_MAINT): number {
  if (t.etancheite) {
    const f = fluidInfo(e, cfg);
    if (f?.periodiciteMois) return Math.min(t.periodiciteMois, f.periodiciteMois);
  }
  return t.periodiciteMois;
}

// ------------------------------------------------------------ échéances
export function addMonths(iso: string, months: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1 + months, 1));
  const last = new Date(Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth() + 1, 0)).getUTCDate();
  dt.setUTCDate(Math.min(d, last));
  return dt.toISOString().slice(0, 10);
}

export interface StatusInfo {
  status: MaintStatus;
  reference: string | null;
  echeance: string | null;
  derniere: Intervention | null;
}

export function maintStatus(e: El, t: MaintType, interventions: Intervention[], todayIso: string, cfg: MaintConfig = DEFAULT_MAINT): StatusInfo {
  const list = interventions.filter((i) => i.gid === e.gid).sort((a, b) => b.date.localeCompare(a.date) || b.createdAt - a.createdAt);
  const derniere = list[0] ?? null;
  if (list.some((i) => i.statut === 'en_cours')) return { status: 'en_cours', reference: derniere?.date ?? null, echeance: null, derniere };
  const prev = list.find((i) => i.type === 'preventive' && i.statut === 'terminee');
  const ref = prev?.date ?? (commissioningDate(e) || null);
  if (!ref || !/^\d{4}-\d{2}-\d{2}/.test(ref)) return { status: 'inconnu', reference: null, echeance: null, derniere };
  const ech = addMonths(ref.slice(0, 10), effectivePeriod(e, t, cfg));
  let status: MaintStatus = 'a_jour';
  if (ech < todayIso) status = 'retard';
  else if (ech <= addDays(todayIso, 30)) status = 'a_prevoir';
  return { status, reference: ref.slice(0, 10), echeance: ech, derniere };
}

export function addDays(iso: string, n: number): string {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function validateConfig(x: any): string | null {
  if (!x || typeof x !== 'object' || !Array.isArray(x.types)) return 'Le fichier doit contenir une liste "types".';
  for (const t of x.types) {
    if (!t.id || !t.libelle || !t.detection || !Array.isArray(t.detection.classes)) return `Type incomplet : ${t.id ?? '?'} (id, libelle, detection.classes requis).`;
    if (!Array.isArray(t.checklist)) return `Type ${t.id} : "checklist" doit être une liste.`;
    if (typeof t.periodiciteMois !== 'number') return `Type ${t.id} : "periodiciteMois" doit être un nombre.`;
    t.mesures = Array.isArray(t.mesures) ? t.mesures : [];
  }
  if (!x.fluides) x.fluides = DEFAULT_MAINT.fluides;
  return null;
}
