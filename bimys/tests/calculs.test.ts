// Tests des calculs sur la maquette exemple. Les valeurs attendues sont recalculées à la main
// à partir du plan (tools/generate_maquette.py) : voir le détail en commentaire.
import { describe, expect, it } from 'vitest';
import { loadSample } from './helpers';
import { computeMetre, totalLength } from '../src/core/metre';
import { computeBilan, computeRoom, DEFAULT_PARAMS, regimeFactor, type DepParams } from '../src/core/deperditions';
import { checkCoherence, RULES } from '../src/core/coherence';
import { computeNomenclature, countBy } from '../src/core/nomenclature';
import { addMonths, fluidInfo, leakCheckPeriod, maintainable, maintStatus, type Intervention } from '../src/core/maintenance';
import { checkAnswer, generateQuestions, scoreDefi, type Question } from '../src/core/defis';
import { computeEnergie, DEFAULT_ACTIONS } from '../src/core/energie';
import { toCsv } from '../src/core/csv';
import { fmt, parseNum } from '../src/core/format';
import { isExtractTerminal } from '../src/core/props';

const GAZ = 'maison_chaudiere_gaz.ifc';
const PAC = 'maison_pac_air_eau.ifc';

describe('lecture de la maquette', () => {
  it('ouvre les deux variantes avec niveaux, pièces et systèmes', async () => {
    for (const f of [GAZ, PAC] as const) {
      const m = await loadSample(f);
      expect(m.data.schema).toBe('IFC4');
      expect(m.data.storeys.map((s) => s.name)).toEqual(['RDC', 'R+1', 'Combles']);
      expect(m.spaces()).toHaveLength(10);
      expect(m.data.systems.map((s) => s.name).sort()).toEqual(['Chauffage', 'Eau chaude sanitaire', 'Eau froide', 'Ventilation VMC simple flux']);
      // surface habitable : 54,82 m² au RDC + 54,36 m² à l'étage = 109,18 m²
      const s = m.spaces().reduce((a, e) => a + (e.qtos.Qto_SpaceBaseQuantities?.NetFloorArea ?? 0), 0);
      expect(s).toBeCloseTo(109.18, 2);
    }
  });
});

describe('métré', () => {
  it('longueurs de cuivre vérifiées à la main', async () => {
    const r = computeMetre(await loadSample(GAZ), 0);
    // 14x16 départ : 4,20 + 3,60 + 2,60 + 2,75 + 4,50 = 17,65 m ; retour : 4,20 + 2,60 + 3,60 + 1,75 + 4,70 = 16,85 m
    expect(totalLength(r, { systeme: /chauffage/i, materiau: /cuivre/i, designation: '14x16' })).toBeCloseTo(34.5, 3);
    // 16x18 : départ 0,85 + 0,60 + 2,55 + 1,60 = 5,60 ; retour 0,79 + 0,60 + 3,35 + 1,00 = 5,74 ;
    // primaire ECS aller 0,75 + 0,50 = 1,25 ; retour 0,80 + 0,55 = 1,35 ; total 13,94 m
    expect(totalLength(r, { systeme: /chauffage/i, designation: '16x18' })).toBeCloseTo(13.94, 3);
    // 12x14 : 4 radiateurs × (0,30 départ + 0,24 retour) = 2,16 m
    expect(totalLength(r, { designation: '12x14' })).toBeCloseTo(2.16, 3);
    // colonne multicouche 20 : 2 × 2,70 m
    expect(totalLength(r, { designation: '20x2' })).toBeCloseTo(5.4, 3);
  });

  it('applique le pourcentage de chutes', async () => {
    const r = computeMetre(await loadSample(GAZ), 10);
    const row = r.tubes.find((t) => t.designation === '14x16')!;
    expect(row.longueurChutes).toBeCloseTo(37.95, 2);
    expect(row.nb).toBe(10);
  });

  it('compte raccords et accessoires', async () => {
    const r = computeMetre(await loadSample(GAZ), 0);
    const n = (sys: RegExp, cat: RegExp) => [...r.raccords, ...r.accessoires].filter((x) => sys.test(x.systeme) && cat.test(x.categorie)).reduce((s, x) => s + x.nb, 0);
    expect(n(/chauffage/i, /thermostatique/i)).toBe(8);
    expect(n(/chauffage/i, /té de réglage/i)).toBe(9);
    expect(n(/chauffage/i, /^té \/ jonction/i)).toBe(8); // 4 tés 16x18 + 4 tés 14x16
    expect(n(/sans système/i, /purgeur/i)).toBe(1);
    expect(r.gaines.map((g) => g.designation).sort()).toEqual(['Ø125', 'Ø125', 'Ø80']);
  });
});

describe('nomenclature', () => {
  it('liste les équipements par catégorie', async () => {
    const c = countBy(computeNomenclature(await loadSample(GAZ)));
    expect(c['Générateurs']).toBe(1);
    expect(c['Émetteurs']).toBe(9);
    expect(c['Circulateurs']).toBe(1);
    expect(c["Vases d'expansion"]).toBe(1);
    expect(c['Soupapes et sécurités']).toBe(2);
    const p = countBy(computeNomenclature(await loadSample(PAC)));
    expect(p['Générateurs']).toBe(2); // PAC + module hydraulique
  });
});

describe('déperditions', () => {
  const P: DepParams = { ...DEFAULT_PARAMS };
  const room = async (name: string) => (await computeBilan(await loadSample(GAZ), P)).rooms.find((r) => r.input.name === name)!;

  it('séjour : calcul par parois vérifié à la main', async () => {
    // murs nets (16,0 − 1,5) + (12,5 − 5,16) + (12,5 − 1,5) = 32,84 m² × 0,36 = 11,8224 W/K
    // vitrages 8,16 m² × 1,4 = 11,424 W/K ; dallage 32 m² × 0,40 = 12,8 W/K ; Σ = 36,0464 W/K
    // Φ parois = 36,0464 × 30 = 1 081,39 W ; ponts + 10 % = 108,14 W ; ventilation 0,34 × 45 × 30 = 459 W
    const r = await room('Séjour');
    expect(r.ubs).toBeCloseTo(36.0464, 3);
    expect(r.phiParois).toBeCloseTo(1081.392, 2);
    expect(r.phiVent).toBeCloseTo(459, 6);
    expect(r.phiTotal).toBeCloseTo(1648.53, 1);
    expect(r.pEmis).toBe(1700);
    expect(r.verdict).toBe('correct');
  });

  it('chambre 2 sous-dimensionnée, entrée surdimensionnée, WC sans émetteur', async () => {
    // chambre 2 : murs 15,75 × 0,36 + fenêtre 1,5 × 1,4 + plafond 11,84 × 0,2 = 10,138 W/K
    // Φ = 10,138 × 29 × 1,1 + 0,34 × 15 × 29 = 323,40 + 147,90 = 471,30 W ; radiateur 350 W → −25,7 %
    const c2 = await room('Chambre 2');
    expect(c2.phiTotal).toBeCloseTo(471.3, 1);
    expect(c2.ecartPct).toBeCloseTo(-25.74, 1);
    expect(c2.verdict).toBe('sous');
    // entrée : 3,065 × 0,36 + 1,935 × 1,8 + 6,6 × 0,4 = 7,2264 W/K → 230,52 W ; 500 W → +116,9 %
    const en = await room('Entrée');
    expect(en.phiTotal).toBeCloseTo(230.52, 1);
    expect(en.verdict).toBe('sur');
    const wc = await room('WC');
    expect(wc.verdict).toBe('aucun');
    expect((await room('Cellier / chaufferie')).verdict).toBe('non_chauffe');
    expect((await room('Salle de bains')).dT).toBe(32); // 22 °C
  });

  it('méthode volumique G × V × ΔT', async () => {
    const m = await loadSample(GAZ);
    const b = computeBilan(m, { ...P, method: 'volumique', g: 0.75 });
    const s = b.rooms.find((r) => r.input.name === 'Séjour')!;
    expect(s.phiTotal).toBeCloseTo(0.75 * 80 * 30, 6); // 1 800 W
  });

  it('correction de la puissance selon le régime d’eau', () => {
    // 70/50 °C, Ti 20 °C : ((60 − 20) / 50)^1,3 = 0,8^1,3 = 0,7482
    expect(regimeFactor({ ...P, correctionRegime: true }, 20)).toBeCloseTo(Math.pow(0.8, 1.3), 6);
    const r = computeRoom(
      { spaceGid: 'x', name: 'Test', storey: '', area: 10, volume: 25, heated: true, ti: 20, qv: 0, parois: [{ id: 'a', label: 'Mur', type: 'Mur', area: 10, u: 1, tau: 1, source: 'saisie' }] },
      { ...P, pontsPct: 0, correctionRegime: true },
      [{ id: 1, gid: 'r', name: 'Rad', pNom: 400 }],
    );
    expect(r.phiTotal).toBeCloseTo(300, 6);
    expect(r.pEmis).toBeCloseTo(400 * Math.pow(0.8, 1.3), 6);
  });

  it('paroi incomplète non comptée et signalée', () => {
    const r = computeRoom(
      { spaceGid: 'x', name: 'T', storey: '', area: 10, volume: 25, heated: true, ti: 19, qv: 0, parois: [{ id: 'a', label: 'Mur', type: 'Mur', area: 10, u: null, tau: 1, source: 'saisie' }] },
      P,
      [],
    );
    expect(r.manquants).toBe(1);
    expect(r.phiParois).toBe(0);
  });
});

describe('cohérence', () => {
  it('détecte les anomalies volontaires de la maquette', async () => {
    const f = checkCoherence(await loadSample(GAZ));
    const trv = f.filter((x) => x.regle === RULES.trv);
    expect(trv).toHaveLength(1);
    expect(trv[0].message).toContain('Radiateur séjour 2');
    expect(f.filter((x) => x.regle === RULES.humide)).toHaveLength(0);
    const sys = f.filter((x) => x.regle === RULES.systeme);
    expect(sys).toHaveLength(1);
    expect(sys[0].message).toContain('Purgeur');
  });
});

describe('maintenance', () => {
  it('PAC R410A 2,4 kg : 5,01 t éq. CO2, contrôle d’étanchéité annuel', async () => {
    const m = await loadSample(PAC);
    const pac = m.elements.find((e) => e.name.startsWith('PAC air/eau'))!;
    const fi = fluidInfo(pac)!;
    expect(fi.teqCO2).toBeCloseTo(5.0112, 4);
    expect(fi.periodiciteMois).toBe(12);
    expect(leakCheckPeriod(4.9, false).mois).toBeNull();
    expect(leakCheckPeriod(8, true).mois).toBeNull();
    expect(leakCheckPeriod(60, false).mois).toBe(6);
  });

  it('reconnaît les équipements et calcule les échéances', async () => {
    const m = await loadSample(GAZ);
    const items = maintainable(m);
    expect(items.map((x) => x.type.id).sort()).toEqual(['ballon_ecs', 'chaudiere_gaz', 'circulateur', 'filtre', 'soupape', 'vase_expansion', 'vmc']);
    const ch = items.find((x) => x.type.id === 'chaudiere_gaz')!;
    expect(maintStatus(ch.el, ch.type, [], '2026-11-02').status).toBe('retard');
    const iv: Intervention = { id: '1', fileKey: m.fileKey, gid: ch.el.gid, elementName: '', date: '2026-10-01', intervenant: '', type: 'preventive', statut: 'terminee', checklist: {}, mesures: {}, observations: '', pieces: '', createdAt: 1 };
    const st = maintStatus(ch.el, ch.type, [iv], '2026-11-02');
    expect(st.status).toBe('a_jour');
    expect(st.echeance).toBe('2027-10-01');
    expect(maintStatus(ch.el, ch.type, [{ ...iv, id: '2', statut: 'en_cours' }], '2026-11-02').status).toBe('en_cours');
    expect(addMonths('2024-01-31', 1)).toBe('2024-02-29');
  });
});

describe('défis', () => {
  it('questions reproductibles et corrigées automatiquement', async () => {
    const m = await loadSample(GAZ);
    const q1 = generateQuestions(m, 42, 10);
    const q2 = generateQuestions(m, 42, 10);
    expect(q1.map((q) => q.id)).toEqual(q2.map((q) => q.id));
    expect(q1).toHaveLength(10);
    // les trois questions phares sont toujours présentes
    expect(q1.some((q) => q.id.startsWith('long_'))).toBe(true);
    expect(q1.some((q) => q.id === 'nb_bouches' && q.reponse === 3)).toBe(true);
    expect(q1.some((q) => q.id.startsWith('dim_'))).toBe(true);
    // la bonne réponse est acceptée pour chaque question
    const answers = q1.map((q) => (typeof q.reponse === 'number' ? fmt(q.reponse, 3) : q.reponse));
    expect(scoreDefi(q1, answers).score).toBe(10);
    expect(m.elements.filter(isExtractTerminal)).toHaveLength(3);
  });

  it('tolérance sur les valeurs numériques', () => {
    const q: Question = { id: 'x', texte: '', type: 'nombre', reponse: 34.5, tolPct: 5, tolAbs: 0.2, explication: '' };
    expect(checkAnswer(q, '34,5')).toBe(true);
    expect(checkAnswer(q, '36,2')).toBe(true); // + 4,9 %
    expect(checkAnswer(q, '36,3')).toBe(false); // + 5,2 %
    expect(checkAnswer(q, 'abc')).toBe(false);
    const c: Question = { id: 'y', texte: '', type: 'choix', choix: ['Oui', 'Non'], reponse: 'Oui', explication: '' };
    expect(checkAnswer(c, 'oui')).toBe(true);
    expect(checkAnswer(c, 'Non')).toBe(false);
  });
});

describe('bilan énergétique', () => {
  it('ratio et gain du remplacement de chaudière', () => {
    const r = computeEnergie({
      surface: 100,
      consos: [{ type: 'gaz', quantite: 15000, partChauffage: 80 }],
      prix: { gaz: 0.1 },
      actions: { ...DEFAULT_ACTIONS, generateur: 'chaudiere', rendementActuel: 0.75, rendementChaudiere: 0.95, isolationCombles: false, regulation: false },
    });
    expect(r.ratio).toBe(150);
    expect(r.chauffageKwh).toBe(12000);
    // gain = 12 000 − 12 000 × 0,75 / 0,95 = 2 526,3 kWh, soit 252,63 €
    expect(r.gains[0].kwh).toBeCloseTo(2526.32, 1);
    expect(r.gains[0].euros).toBeCloseTo(252.63, 1);
    expect(r.apres.kwh).toBeCloseTo(15000 - 2526.32, 1);
  });
});

describe('formats', () => {
  it('CSV pour Excel français et nombres', () => {
    const csv = toCsv(['A', 'B'], [['x;y', 1.5]]);
    expect(csv.startsWith('﻿')).toBe(true);
    expect(csv).toContain('"x;y";1,5');
    expect(fmt(1648.53, 1)).toBe('1 648,5');
    expect(parseNum('12,5')).toBe(12.5);
  });
});

describe('bibliothèque de bâtiments', () => {
  const cas: { f: string; erreurs: string[]; lots: string[]; maint: string[] }[] = [
    { f: 'maison_plain_pied_pcbt.ifc', erreurs: ['Chambre 3'], lots: ['chauffage', 'ventilation', 'ecs', 'ef'], maint: ['pac', 'vmc', 'ballon_ecs'] },
    { f: 'immeuble_collectif_r3.ifc', erreurs: ['Logement 07 Chambre 2', 'Logement 12 Séjour'], lots: ['chauffage', 'ventilation', 'ecs', 'ef'], maint: ['chaudiere_gaz', 'compteur_energie'] },
    { f: 'clinique_r2.ifc', erreurs: ['Chambre R1S04', 'Chambre R2N07'], lots: ['chauffage', 'froid', 'ventilation', 'ecs', 'ef'], maint: ['groupe_froid', 'cta', 'ventilo'] },
    { f: 'cinema_3_salles.ifc', erreurs: ['Salle 3'], lots: ['ventilation', 'ecs', 'ef'], maint: ['rooftop'] },
    { f: 'bureaux_r2_drv.ifc', erreurs: ['Bureau R1-9', 'Salle de réunion R+2'], lots: ['froid', 'ventilation'], maint: ['drv', 'ventilo', 'cta'] },
  ];
  for (const c of cas) {
    it(`${c.f} : ouverture, déperditions, erreurs volontaires, maintenance`, async () => {
      const m = await loadSample(c.f);
      expect(m.data.boundaries.length).toBeGreaterThan(30);
      for (const l of c.lots) expect(m.elements.some((e) => e.lot === l)).toBe(true);
      const b = computeBilan(m, DEFAULT_PARAMS);
      const sous = b.rooms.filter((r) => r.verdict === 'sous').map((r) => r.input.name).sort();
      expect(sous).toEqual([...c.erreurs].sort());
      // hors erreurs volontaires, aucun émetteur manquant dans une pièce déperditive
      expect(b.rooms.filter((r) => r.verdict === 'aucun').map((r) => r.input.name)).toEqual([]);
      const ids = new Set(maintainable(m).map((x) => x.type.id));
      for (const t of c.maint) expect(ids.has(t)).toBe(true);
      expect(generateQuestions(m, 3, 10)).toHaveLength(10);
    });
  }
  it('fluides : groupe froid R32 38 kg et DRV R410A 18,5 kg', async () => {
    const gf = (await loadSample('clinique_r2.ifc')).elements.find((e) => e.cls === 'IfcChiller')!;
    expect(fluidInfo(gf)!.teqCO2).toBeCloseTo(25.65, 2); // 38 × 675 / 1000
    expect(fluidInfo(gf)!.periodiciteMois).toBe(12);
    const drv = (await loadSample('bureaux_r2_drv.ifc')).elements.find((e) => /unité extérieure drv 1/i.test(e.name))!;
    expect(fluidInfo(drv)!.teqCO2).toBeCloseTo(38.63, 2); // 18,5 × 2088 / 1000
  });
});

describe('métré : quantités de commande, contenance, filtres', () => {
  it('contenance, conditionnement et quantité à commander vérifiés à la main', async () => {
    const r = computeMetre(await loadSample(GAZ), 10);
    const c = r.tubes.find((t) => t.designation === '14x16')!;
    // contenance = π × 0,014² / 4 × 34,5 m × 1000 = 5,31 L
    expect(c.volumeL).toBeCloseTo(5.31, 2);
    // 34,5 m + 10 % = 37,95 m en barres de 4 m : 10 barres
    expect(c.conditionnement.libelle).toBe('Barre de 4 m');
    expect(c.aCommander).toBe(10);
    const mc = r.tubes.find((t) => t.designation === '16x2')!;
    expect(mc.conditionnement.libelle).toBe('Couronne de 100 m');
    expect(mc.dInt).toBeCloseTo(0.012, 6);
    expect(c.ids).toHaveLength(10);
    // gaine souple Ø80 : surface développée = π × 0,08 × longueur × 1,1
    const g = r.gaines.find((x) => x.designation === 'Ø80')!;
    expect(g.surfaceM2).toBeCloseTo(Math.PI * 0.08 * g.longueur * 1.1, 1);
    const ch = r.systemes.find((x) => x.systeme === 'Chauffage')!;
    expect(ch.volumeL).toBeGreaterThan(10);
  });
  it('filtre par niveau et par réseau', async () => {
    const m = await loadSample(GAZ);
    const r1 = m.data.storeys.find((s) => s.name === 'R+1')!;
    const r = computeMetre(m, { chutesPct: 0, storeyId: r1.id });
    expect(r.tubes.some((t) => t.designation === '14x16')).toBe(false); // boucle 14x16 au RDC uniquement
    expect(r.tubes.some((t) => t.designation === '16x2')).toBe(true);
    const v = computeMetre(m, { systeme: 'Ventilation VMC simple flux' });
    expect(v.tubes).toHaveLength(0);
    expect(v.gaines.length).toBe(3);
  });
});
