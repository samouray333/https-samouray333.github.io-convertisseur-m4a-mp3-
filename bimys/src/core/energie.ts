// Bilan énergétique simplifié et estimation de gains (hypothèses affichées et modifiables).

export type EnergyType = 'gaz' | 'electricite' | 'fioul' | 'bois' | 'granules' | 'propane';

export interface EnergyDef {
  id: EnergyType;
  label: string;
  unite: string;
  /** kWh par unité saisie */
  kwhParUnite: number;
  prixKwh: number;
  co2Kwh: number;
}

export const ENERGIES: EnergyDef[] = [
  { id: 'gaz', label: 'Gaz naturel', unite: 'kWh', kwhParUnite: 1, prixKwh: 0.12, co2Kwh: 0.227 },
  { id: 'electricite', label: 'Électricité', unite: 'kWh', kwhParUnite: 1, prixKwh: 0.25, co2Kwh: 0.079 },
  { id: 'fioul', label: 'Fioul domestique', unite: 'L', kwhParUnite: 10, prixKwh: 0.12, co2Kwh: 0.324 },
  { id: 'propane', label: 'Propane', unite: 'kg', kwhParUnite: 12.8, prixKwh: 0.18, co2Kwh: 0.272 },
  { id: 'bois', label: 'Bois bûches', unite: 'stère', kwhParUnite: 1700, prixKwh: 0.07, co2Kwh: 0.03 },
  { id: 'granules', label: 'Granulés de bois', unite: 'kg', kwhParUnite: 4.8, prixKwh: 0.09, co2Kwh: 0.03 },
];

export const ENERGY_BY_ID = Object.fromEntries(ENERGIES.map((e) => [e.id, e])) as Record<EnergyType, EnergyDef>;

export interface Conso {
  type: EnergyType;
  quantite: number;
  /** part de cette énergie utilisée pour le chauffage (%) */
  partChauffage: number;
}

export interface Actions {
  generateur: 'aucun' | 'chaudiere' | 'pac';
  rendementActuel: number;
  rendementChaudiere: number;
  scopPac: number;
  isolationCombles: boolean;
  gainCombles: number;
  isolationMurs: boolean;
  gainMurs: number;
  fenetres: boolean;
  gainFenetres: number;
  regulation: boolean;
  gainRegulation: number;
}

export interface EnergieInput {
  surface: number;
  consos: Conso[];
  prix: Partial<Record<EnergyType, number>>;
  actions: Actions;
}

export const DEFAULT_ACTIONS: Actions = {
  generateur: 'chaudiere',
  rendementActuel: 0.75,
  rendementChaudiere: 0.97,
  scopPac: 3.5,
  isolationCombles: true,
  gainCombles: 25,
  isolationMurs: false,
  gainMurs: 20,
  fenetres: false,
  gainFenetres: 10,
  regulation: true,
  gainRegulation: 12,
};

export interface ActionGain {
  action: string;
  hypothese: string;
  kwh: number;
  euros: number;
  co2: number;
}

export interface EnergieResult {
  totalKwh: number;
  chauffageKwh: number;
  ratio: number;
  ratioChauffage: number;
  cout: number;
  co2: number;
  classe: string;
  gains: ActionGain[];
  apres: { kwh: number; cout: number; co2: number; ratio: number };
}

export function ratioClass(r: number): string {
  if (r < 70) return 'Très performant';
  if (r < 110) return 'Performant';
  if (r < 180) return 'Moyen';
  if (r < 250) return 'Énergivore';
  return 'Très énergivore';
}

export function computeEnergie(inp: EnergieInput): EnergieResult {
  const price = (t: EnergyType) => inp.prix[t] ?? ENERGY_BY_ID[t].prixKwh;
  let total = 0, chauffage = 0, cout = 0, co2 = 0;
  let chauffEnergy: EnergyType = 'gaz';
  let maxCh = -1;
  for (const c of inp.consos) {
    const d = ENERGY_BY_ID[c.type];
    const kwh = c.quantite * d.kwhParUnite;
    total += kwh;
    const ch = (kwh * c.partChauffage) / 100;
    chauffage += ch;
    cout += kwh * price(c.type);
    co2 += kwh * d.co2Kwh;
    if (ch > maxCh) {
      maxCh = ch;
      chauffEnergy = c.type;
    }
  }
  const s = inp.surface > 0 ? inp.surface : 1;
  const a = inp.actions;
  const gains: ActionGain[] = [];
  const pE = price(chauffEnergy);
  const cE = ENERGY_BY_ID[chauffEnergy].co2Kwh;
  const env: { on: boolean; g: number; label: string }[] = [
    { on: a.isolationCombles, g: a.gainCombles, label: 'Isolation des combles' },
    { on: a.isolationMurs, g: a.gainMurs, label: 'Isolation des murs' },
    { on: a.fenetres, g: a.gainFenetres, label: 'Remplacement des fenêtres' },
    { on: a.regulation, g: a.gainRegulation, label: 'Régulation (programmation, robinets thermostatiques)' },
  ];
  for (const x of env) {
    if (!x.on) continue;
    const k = (chauffage * x.g) / 100;
    gains.push({ action: x.label, hypothese: `−${x.g} % sur la consommation de chauffage`, kwh: k, euros: k * pE, co2: k * cE });
  }
  // besoin utile après actions sur l'enveloppe et la régulation
  const factor = env.filter((x) => x.on).reduce((f, x) => f * (1 - x.g / 100), 1);
  const utile = chauffage * a.rendementActuel * factor;
  let apresChauffKwh = chauffage * factor;
  let apresCout = cout - chauffage * pE + apresChauffKwh * pE;
  let apresCo2 = co2 - chauffage * cE + apresChauffKwh * cE;
  if (a.generateur === 'chaudiere') {
    const alone = chauffage - (chauffage * a.rendementActuel) / a.rendementChaudiere;
    gains.push({
      action: 'Remplacement par une chaudière à condensation',
      hypothese: `Rendement saisonnier ${Math.round(a.rendementActuel * 100)} % → ${Math.round(a.rendementChaudiere * 100)} %`,
      kwh: alone,
      euros: alone * pE,
      co2: alone * cE,
    });
    const newKwh = utile / a.rendementChaudiere;
    apresCout += (newKwh - apresChauffKwh) * pE;
    apresCo2 += (newKwh - apresChauffKwh) * cE;
    apresChauffKwh = newKwh;
  } else if (a.generateur === 'pac') {
    const elec = (chauffage * a.rendementActuel) / a.scopPac;
    const pEl = price('electricite');
    const cEl = ENERGY_BY_ID.electricite.co2Kwh;
    gains.push({
      action: 'Remplacement par une PAC air/eau',
      hypothese: `Rendement actuel ${Math.round(a.rendementActuel * 100)} %, SCOP ${a.scopPac.toString().replace('.', ',')} (énergie : électricité)`,
      kwh: chauffage - elec,
      euros: chauffage * pE - elec * pEl,
      co2: chauffage * cE - elec * cEl,
    });
    const newElec = utile / a.scopPac;
    apresCout += newElec * pEl - apresChauffKwh * pE;
    apresCo2 += newElec * cEl - apresChauffKwh * cE;
    apresChauffKwh = newElec;
  }
  const apresTotal = total - chauffage + apresChauffKwh;
  return {
    totalKwh: total,
    chauffageKwh: chauffage,
    ratio: total / s,
    ratioChauffage: chauffage / s,
    cout,
    co2,
    classe: ratioClass(total / s),
    gains,
    apres: { kwh: apresTotal, cout: apresCout, co2: apresCo2, ratio: apresTotal / s },
  };
}
