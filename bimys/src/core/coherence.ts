import { elementsInSpace, emittersOf, defaultHeated } from './deperditions';
import { ifcFr } from './ifcTypesFr';
import { MEP_CLASSES } from './lots';
import { bboxDistance, isExtractTerminal, isThermostaticValve } from './props';
import type { El, Model } from './types';

export type Severity = 'erreur' | 'alerte' | 'info';

export interface Finding {
  regle: string;
  severite: Severity;
  message: string;
  elementIds: number[];
}

export const RULES = {
  trv: 'Émetteurs sans robinet thermostatique',
  humide: "Pièces humides sans bouche d'extraction",
  systeme: 'Éléments de réseau sans système associé',
  chauffee: 'Pièces chauffées sans émetteur',
};

export function isWetRoom(name: string): boolean {
  return /cuisine|bain|sdb|salle d.eau|douche|\bwc\b|toilette|sanitaire|buanderie|lingerie/i.test(name);
}

/**
 * Un robinet thermostatique est associé à l'émetteur le plus proche (à moins de 1 m),
 * ou à l'émetteur dans lequel il est imbriqué. Un émetteur sans robinet associé est signalé.
 */
export function trvAssignments(m: Model, maxDist = 1.0): Map<number, number> {
  const rads = m.ofClass('IfcSpaceHeater');
  const out = new Map<number, number>();
  for (const v of m.elements.filter(isThermostaticValve)) {
    let best: El | null = null;
    let bd = Infinity;
    for (const r of rads) {
      const d = r.bbox && v.bbox ? bboxDistance(r.bbox, v.bbox) : v.spaceId !== null && v.spaceId === r.spaceId ? maxDist : Infinity;
      if (d < bd) {
        bd = d;
        best = r;
      }
    }
    if (best && bd <= maxDist) out.set(v.id, best.id);
  }
  return out;
}

export function hasThermostaticValve(m: Model, rad: El, assign = trvAssignments(m)): boolean {
  if (/thermosta/i.test(`${rad.objectType} ${rad.desc} ${rad.typeName}`)) return true;
  for (const r of assign.values()) if (r === rad.id) return true;
  return false;
}

export function checkCoherence(m: Model): Finding[] {
  const out: Finding[] = [];
  // 1. émetteurs sans robinet thermostatique
  const assign = trvAssignments(m);
  for (const r of m.ofClass('IfcSpaceHeater')) {
    if (!hasThermostaticValve(m, r, assign)) {
      const sp = r.spaceId !== null ? m.byId.get(r.spaceId)?.name : '';
      out.push({
        regle: RULES.trv,
        severite: 'alerte',
        message: `${r.name || 'Émetteur'}${sp ? ` (${sp})` : ''} : aucun robinet thermostatique détecté à proximité. Exigé sur les émetteurs des pièces principales (sauf pièce du thermostat d'ambiance).`,
        elementIds: [r.id],
      });
    }
  }
  // 2. pièces humides sans bouche d'extraction
  for (const sp of m.spaces()) {
    if (!isWetRoom(sp.name)) continue;
    const b = elementsInSpace(m, sp, isExtractTerminal);
    if (!b.length) out.push({ regle: RULES.humide, severite: 'erreur', message: `${sp.name} : pièce humide sans bouche d'extraction (arrêté du 24 mars 1982).`, elementIds: [sp.id] });
  }
  // 3. éléments sans système
  const orphans = m.elements.filter((e) => MEP_CLASSES.has(e.cls.toLowerCase()) && e.systemIds.length === 0);
  const byClass = new Map<string, El[]>();
  for (const e of orphans) {
    const k = ifcFr(e.cls);
    if (!byClass.has(k)) byClass.set(k, []);
    byClass.get(k)!.push(e);
  }
  for (const [k, list] of byClass) {
    out.push({
      regle: RULES.systeme,
      severite: 'alerte',
      message: list.length === 1 ? `${list[0].name || k} n'est rattaché à aucun système (IfcSystem).` : `${list.length} éléments « ${k} » ne sont rattachés à aucun système.`,
      elementIds: list.map((e) => e.id),
    });
  }
  // 4. pièces chauffées sans émetteur (information)
  for (const sp of m.spaces()) {
    if (!defaultHeated(sp.name)) continue;
    if (!emittersOf(m, sp).length) out.push({ regle: RULES.chauffee, severite: 'info', message: `${sp.name} : aucun émetteur (chauffage par transfert d'air ou oubli ?).`, elementIds: [sp.id] });
  }
  return out;
}
