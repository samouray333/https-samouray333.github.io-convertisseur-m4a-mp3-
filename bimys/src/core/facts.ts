import { fmt } from './format';
import { propFr, valueFr } from './ifcPropsFr';
import type { El, PropValue } from './types';

export function propText(v: PropValue): string {
  if (v === null) return '';
  if (typeof v === 'boolean') return v ? 'Oui' : 'Non';
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return fmt(v, 0);
    // zéros inutiles retirés seulement après la virgule (10,500 -> 10,5 ; 200 reste 200)
    return fmt(v, 3).replace(/(,\d*?)0+$/, '$1').replace(/,$/, '');
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v.split('-').reverse().join('/');
  return /^[A-Z_]+$/.test(v) ? valueFr(v) : v;
}

/** Caractéristiques d'un équipement (noms de propriétés traduits), sans doublons. */
export function elementFacts(e: El): [string, string][] {
  const out: [string, string][] = [];
  const seen = new Set<string>();
  const sets = ['Bimys_Equipement', ...Object.keys(e.psets).filter((k) => k !== 'Bimys_Equipement')];
  for (const s of sets) {
    for (const [k, v] of Object.entries(e.psets[s] ?? {})) {
      if (seen.has(k) || v === null || v === '') continue;
      if (/^(Manufacturer|ModelLabel|SerialNumber)$/.test(k) && s !== 'Bimys_Equipement') continue;
      seen.add(k);
      out.push([propFr(k), propText(v)]);
    }
  }
  return out;
}
