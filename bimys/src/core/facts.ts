import { fmt } from './format';
import type { El, PropValue } from './types';

function propText(v: PropValue): string {
  if (v === null) return '';
  if (typeof v === 'boolean') return v ? 'Oui' : 'Non';
  if (typeof v === 'number') return fmt(v, Number.isInteger(v) ? 0 : 3).replace(/,?0+$/, '') || '0';
  return String(v);
}

export function elementFacts(e: El): [string, string][] {
  const out: [string, string][] = [];
  const seen = new Set<string>();
  const sets = ['Bimys_Equipement', ...Object.keys(e.psets).filter((k) => k !== 'Bimys_Equipement')];
  for (const s of sets) {
    for (const [k, v] of Object.entries(e.psets[s] ?? {})) {
      if (seen.has(k) || v === null || v === '') continue;
      if (/^(Manufacturer|ModelLabel|SerialNumber)$/.test(k) && s !== 'Bimys_Equipement') continue;
      seen.add(k);
      out.push([k, propText(v)]);
    }
  }
  return out;
}

