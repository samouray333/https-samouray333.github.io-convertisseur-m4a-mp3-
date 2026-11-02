import { fmt } from './format';
import { ifcFr } from './ifcTypesFr';
import { brand, commissioningDate, isAirInlet, isExtractTerminal, model, powerW, prop, propMatch, text, airFlow, num } from './props';
import { systemName } from './metre';
import type { El, Model } from './types';

export interface NomRow {
  id: number;
  gid: string;
  categorie: string;
  designation: string;
  localisation: string;
  systeme: string;
  marque: string;
  modele: string;
  puissance: string;
  caracteristiques: string;
}

export const NOM_CATEGORIES = [
  'Générateurs',
  'Émetteurs',
  'Circulateurs',
  "Vases d'expansion",
  'Ballons / stockage',
  'Soupapes et sécurités',
  'Ventilation : caissons',
  'Ventilation : bouches et entrées d’air',
  'Régulation',
  'Appareils sanitaires',
];

export function nomCategory(e: El): string | null {
  const c = e.cls.toLowerCase();
  if (['ifcboiler', 'ifcchiller', 'ifcunitaryequipment', 'ifcheatexchanger', 'ifcburner', 'ifcsolardevice', 'ifcairtoairheatrecovery', 'ifccompressor'].includes(c)) return 'Générateurs';
  if (c === 'ifcspaceheater' || c === 'ifccoil') return 'Émetteurs';
  if (c === 'ifcpump') return 'Circulateurs';
  if (c === 'ifctank') return /EXPANSION/i.test(e.predefined) || /vase/i.test(e.name) ? "Vases d'expansion" : 'Ballons / stockage';
  if (c === 'ifcvalve' && (/SAFETYCUTOFF|PRESSURERELIEF/i.test(e.predefined) || /soupape|groupe de s[ée]curit/i.test(e.name))) return 'Soupapes et sécurités';
  if (c === 'ifcfan') return 'Ventilation : caissons';
  if (c === 'ifcairterminal') return 'Ventilation : bouches et entrées d’air';
  if (['ifcunitarycontrolelement', 'ifccontroller', 'ifcsensor', 'ifcactuator'].includes(c)) return 'Régulation';
  if (c === 'ifcsanitaryterminal') return 'Appareils sanitaires';
  return null;
}

const SKIP_KEYS = /^(Marque|Modèle|Manufacturer|ModelLabel|SerialNumber|Numéro de série|Reference|Status|Date de mise en service)$/i;

function characteristics(e: El): string {
  const parts: string[] = [];
  const add = (label: string, v: string) => v && parts.push(`${label} ${v}`);
  const c = e.cls.toLowerCase();
  if (c === 'ifcairterminal') {
    const q = airFlow(e);
    add(isExtractTerminal(e) ? 'Extraction' : isAirInlet(e) ? "Entrée d'air" : 'Terminal', q !== null ? `${fmt(q, 0)} m³/h` : '');
  }
  const custom = e.psets['Bimys_Equipement'] ?? {};
  for (const [k, v] of Object.entries(custom)) {
    if (SKIP_KEYS.test(k) || /puissance nominale/i.test(k) || /d[ée]bit nominal|fonction/i.test(k)) continue;
    if (parts.length >= 6) break;
    parts.push(`${k} : ${typeof v === 'number' ? fmt(v, Number.isInteger(v) ? 0 : 2) : text(v)}`);
  }
  if (!parts.length) {
    for (const ps of Object.values(e.psets)) {
      for (const [k, v] of Object.entries(ps)) {
        if (SKIP_KEYS.test(k) || v === null || v === '') continue;
        parts.push(`${k} : ${typeof v === 'number' ? fmt(v, 2) : text(v)}`);
        if (parts.length >= 4) break;
      }
      if (parts.length >= 4) break;
    }
  }
  return parts.join(' ; ');
}

export function location(m: Model, e: El): string {
  const sp = e.spaceId !== null ? m.byId.get(e.spaceId)?.name : '';
  const st = e.storeyId !== null ? m.storeyById.get(e.storeyId)?.name : '';
  return [st, sp].filter(Boolean).join(' / ') || 'Non localisé';
}

export function computeNomenclature(m: Model): NomRow[] {
  const rows: NomRow[] = [];
  for (const e of m.elements) {
    const cat = nomCategory(e);
    if (!cat) continue;
    const p = powerW(e);
    rows.push({
      id: e.id,
      gid: e.gid,
      categorie: cat,
      designation: e.name || ifcFr(e.cls),
      localisation: location(m, e),
      systeme: systemName(m, e),
      marque: brand(e),
      modele: model(e),
      puissance: p !== null ? (p >= 1000 ? `${fmt(p / 1000, 1)} kW` : `${fmt(p, 0)} W`) : '',
      caracteristiques: characteristics(e),
    });
  }
  const order = (c: string) => NOM_CATEGORIES.indexOf(c);
  return rows.sort((a, b) => order(a.categorie) - order(b.categorie) || a.designation.localeCompare(b.designation, 'fr', { numeric: true }));
}

export function countBy(rows: NomRow[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of rows) out[r.categorie] = (out[r.categorie] ?? 0) + 1;
  return out;
}

export { commissioningDate, propMatch, num, prop };
