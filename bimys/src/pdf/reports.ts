// Rapports PDF de chaque module.
import type { Finding } from '../core/coherence';
import { formatAnswer, type DefiResult } from '../core/defis';
import { VERDICT_LABEL, type Bilan, type DepParams } from '../core/deperditions';
import type { EnergieInput, EnergieResult } from '../core/energie';
import { ENERGY_BY_ID } from '../core/energie';
import { dateFr, fmt } from '../core/format';
import type { Intervention, MaintType, StatusInfo, FluidInfo } from '../core/maintenance';
import { STATUS_LABEL } from '../core/maintenance';
import type { MetreResult } from '../core/metre';
import type { NomRow } from '../core/nomenclature';
import type { El, Model } from '../core/types';
import type { Settings } from '../store/db';
import { Report } from './report';

const VERDICT_COLOR: Record<string, [number, number, number]> = {
  sous: [198, 40, 40],
  correct: [46, 125, 50],
  sur: [230, 120, 0],
  aucun: [198, 40, 40],
  non_chauffe: [120, 120, 120],
};

function src(m: Model): string {
  return `Maquette : ${m.data.fileName}${m.data.projectName ? ` (${m.data.projectName})` : ''}`;
}

export async function metrePdf(m: Model, r: MetreResult, s: Settings): Promise<Uint8Array> {
  const rep = await Report.create('Métré des réseaux', src(m), s);
  rep.para(`Longueurs issues de la maquette IFC (quantités Qto ou longueur d'axe des segments). Majoration pour chutes : ${fmt(r.chutesPct, 0)} %.`);
  if (r.tubes.length) {
    rep.h2('Tubes');
    rep.table(
      ['Système', 'Matériau', 'Diamètre', 'Tronçons', 'Longueur (m)', `Avec chutes (m)`],
      r.tubes.map((t) => [t.systeme, t.materiau, t.designation, String(t.nb), fmt(t.longueur, 2), fmt(t.longueurChutes, 2)]),
      { columnStyles: { 3: { halign: 'right' }, 4: { halign: 'right' }, 5: { halign: 'right', fontStyle: 'bold' } } },
    );
  }
  if (r.gaines.length) {
    rep.h2('Gaines de ventilation');
    rep.table(
      ['Système', 'Matériau', 'Section', 'Tronçons', 'Longueur (m)', 'Avec chutes (m)'],
      r.gaines.map((t) => [t.systeme, t.materiau, t.designation, String(t.nb), fmt(t.longueur, 2), fmt(t.longueurChutes, 2)]),
      { columnStyles: { 3: { halign: 'right' }, 4: { halign: 'right' }, 5: { halign: 'right', fontStyle: 'bold' } } },
    );
  }
  if (r.raccords.length) {
    rep.h2('Raccords');
    rep.table(['Système', 'Type', 'Diamètre', 'Quantité'], r.raccords.map((x) => [x.systeme, x.categorie, x.designation, String(x.nb)]), { columnStyles: { 3: { halign: 'right' } } });
  }
  if (r.accessoires.length) {
    rep.h2('Vannes et accessoires');
    rep.table(['Système', 'Type', 'Quantité'], r.accessoires.map((x) => [x.systeme, x.categorie, String(x.nb)]), { columnStyles: { 2: { halign: 'right' } } });
  }
  return rep.output();
}

export async function nomenclaturePdf(m: Model, rows: NomRow[], s: Settings): Promise<Uint8Array> {
  const rep = await Report.create('Nomenclature des équipements', src(m), s, true);
  let cat = '';
  const body: any[] = [];
  for (const r of rows) {
    if (r.categorie !== cat) {
      cat = r.categorie;
      const n = rows.filter((x) => x.categorie === cat).length;
      body.push([{ content: `${cat} (${n})`, colSpan: 6, styles: { fontStyle: 'bold', fillColor: [226, 236, 239], textColor: [15, 76, 92] } }]);
    }
    body.push([r.designation, r.localisation, [r.marque, r.modele].filter(Boolean).join(' '), r.puissance, r.systeme, r.caracteristiques]);
  }
  rep.table(['Désignation', 'Localisation', 'Marque / modèle', 'Puissance', 'Système', 'Caractéristiques'], body, {
    columnStyles: { 0: { cellWidth: 48 }, 1: { cellWidth: 38 }, 2: { cellWidth: 44 }, 3: { cellWidth: 18, halign: 'right' }, 4: { cellWidth: 32 } },
    styles: { fontSize: 7.8 },
  });
  return rep.output();
}

export async function deperditionsPdf(m: Model, b: Bilan, p: DepParams, s: Settings): Promise<Uint8Array> {
  const rep = await Report.create('Bilan des déperditions', src(m), s);
  rep.h2('Hypothèses');
  rep.kv([
    ['Méthode', p.method === 'parois' ? 'Par parois : Φ = Σ(U × S × b × ΔT) + ponts thermiques + 0,34 × Qv × ΔT' : `Volumique : Φ = G × V × ΔT (G = ${fmt(p.g, 2)} W/m³.K)`],
    ['Température extérieure de base', `${fmt(p.te, 0)} °C`],
    ['Ponts thermiques', p.method === 'parois' ? `+ ${fmt(p.pontsPct, 0)} % des déperditions par parois` : 'inclus dans G'],
    ['Puissance des émetteurs', p.correctionRegime ? `corrigée pour le régime ${fmt(p.tDepart, 0)}/${fmt(p.tRetour, 0)} °C (n = ${fmt(p.nExp, 2)})` : 'nominale (ΔT 50 K)'],
    ['Verdict', `correct si l'écart est entre ${fmt(p.seuilSous, 0)} % et + ${fmt(p.seuilSur, 0)} %`],
  ], 1);
  rep.h2('Synthèse par pièce');
  rep.table(
    ['Pièce', 'Niveau', 'Ti', 'ΔT', 'Φ parois', 'Φ ponts', 'Φ ventil.', 'Φ total', 'Émetteurs', 'Écart', 'Verdict'],
    b.rooms.map((r) => [
      r.input.name,
      r.input.storey,
      `${fmt(r.input.ti, 0)} °C`,
      `${fmt(r.dT, 0)} K`,
      p.method === 'parois' ? fmt(r.phiParois, 0) : '',
      p.method === 'parois' ? fmt(r.phiPonts, 0) : '',
      p.method === 'parois' ? fmt(r.phiVent, 0) : '',
      { content: fmt(r.phiTotal, 0), styles: { fontStyle: 'bold' } },
      fmt(r.pEmis, 0),
      r.ecartPct === null ? '' : `${r.ecartPct > 0 ? '+' : ''}${fmt(r.ecartPct, 1)} %`,
      { content: VERDICT_LABEL[r.verdict], styles: { textColor: VERDICT_COLOR[r.verdict], fontStyle: 'bold' } },
    ]),
    { styles: { fontSize: 7.8 }, columnStyles: { 4: { halign: 'right' }, 5: { halign: 'right' }, 6: { halign: 'right' }, 7: { halign: 'right' }, 8: { halign: 'right' }, 9: { halign: 'right' } } },
  );
  rep.para(`Total des pièces chauffées : ${fmt(b.totalPhi, 0)} W de déperditions pour ${fmt(b.totalEmis, 0)} W d'émetteurs installés. Surface chauffée ${fmt(b.surfaceChauffee, 2)} m², volume ${fmt(b.volumeChauffe, 1)} m³ (${fmt(b.surfaceChauffee ? b.totalPhi / b.surfaceChauffee : 0, 1)} W/m²). Puissances en watts.`);
  if (p.method === 'parois') {
    for (const r of b.rooms.filter((x) => x.input.parois.length)) {
      rep.h2(`${r.input.name} (${r.input.storey})`);
      rep.table(
        ['Paroi', 'Type', 'S (m²)', 'U (W/m².K)', 'b', 'U.S.b (W/K)', 'Φ (W)'],
        r.input.parois.map((w) => {
          const ok = w.area !== null && w.u !== null;
          const usb = ok ? w.u! * w.area! * w.tau : null;
          return [w.label, w.type, w.area === null ? 'à saisir' : fmt(w.area, 2), w.u === null ? 'à saisir' : fmt(w.u, 2), fmt(w.tau, 2), usb === null ? '' : fmt(usb, 2), usb === null ? '' : fmt(usb * r.dT, 0)];
        }),
        { styles: { fontSize: 7.8 }, columnStyles: { 2: { halign: 'right' }, 3: { halign: 'right' }, 4: { halign: 'right' }, 5: { halign: 'right' }, 6: { halign: 'right' } } },
      );
      rep.para(
        `Σ U.S.b = ${fmt(r.ubs, 2)} W/K ; Φ parois = ${fmt(r.ubs, 2)} × ${fmt(r.dT, 0)} = ${fmt(r.phiParois, 0)} W ; ponts thermiques ${fmt(r.phiPonts, 0)} W ; ventilation 0,34 × ${fmt(r.input.qv, 0)} × ${fmt(r.dT, 0)} = ${fmt(r.phiVent, 0)} W ; total ${fmt(r.phiTotal, 0)} W. ` +
          (r.emetteurs.length ? `Émetteurs : ${r.emetteurs.map((e) => `${e.name} ${fmt(e.pCorr, 0)} W`).join(', ')}. ` : 'Aucun émetteur. ') +
          `Verdict : ${VERDICT_LABEL[r.verdict]}${r.ecartPct !== null ? ` (${r.ecartPct > 0 ? '+' : ''}${fmt(r.ecartPct, 1)} %)` : ''}.`,
        8.5,
      );
    }
  }
  return rep.output();
}

export async function coherencePdf(m: Model, f: Finding[], s: Settings): Promise<Uint8Array> {
  const rep = await Report.create('Vérification de cohérence', src(m), s);
  if (!f.length) rep.para('Aucune anomalie détectée.');
  else rep.table(['Gravité', 'Règle', 'Constat'], f.map((x) => [x.severite.toUpperCase(), x.regle, x.message]), { columnStyles: { 0: { cellWidth: 20 }, 1: { cellWidth: 50 } } });
  return rep.output();
}

import { elementFacts } from '../core/facts';
export { elementFacts };

export async function interventionPdf(
  m: Model,
  e: El,
  t: MaintType,
  i: Intervention,
  st: StatusInfo,
  fluid: FluidInfo | null,
  s: Settings,
): Promise<Uint8Array> {
  const rep = await Report.create("Rapport d'intervention", `${e.name} : ${t.libelle}`, s);
  rep.h2('Équipement');
  const loc = [e.storeyId !== null ? m.storeyById.get(e.storeyId)?.name : '', e.spaceId !== null ? m.byId.get(e.spaceId)?.name : ''].filter(Boolean).join(' / ');
  rep.kv([['Désignation', e.name], ['Localisation', loc || 'Non localisé'], ['Maquette', m.data.fileName], ['GlobalId', e.gid], ...elementFacts(e).slice(0, 10)], 2);
  if (fluid) rep.para(`Fluide ${fluid.fluide}, charge ${fmt(fluid.chargeKg, 2)} kg, PRG ${fmt(fluid.gwp ?? 0, 0)} : ${fluid.teqCO2 !== null ? fmt(fluid.teqCO2, 2) : '?'} t éq. CO2. ${fluid.texte}`, 8.5);
  rep.h2('Intervention');
  rep.kv([
    ['Date', dateFr(i.date)],
    ['Intervenant', i.intervenant || ''],
    ['Type', i.type === 'preventive' ? 'Maintenance préventive' : 'Maintenance corrective'],
    ['Statut', i.statut === 'terminee' ? 'Terminée' : 'En cours'],
    ['Prochaine échéance', st.echeance ? dateFr(st.echeance) : ''],
    ['État', STATUS_LABEL[st.status]],
  ]);
  if (t.checklist.length) {
    rep.h2('Points de contrôle');
    const lab = { ok: 'Conforme', nok: 'Non conforme', na: 'Sans objet', '': 'Non vérifié' } as const;
    const col = { ok: [46, 125, 50], nok: [198, 40, 40], na: [120, 120, 120], '': [150, 150, 150] } as const;
    rep.table(
      ['Contrôle', 'Résultat'],
      t.checklist.map((c) => {
        const v = i.checklist[c.id] ?? '';
        return [c.libelle, { content: lab[v], styles: { textColor: col[v] as any, fontStyle: 'bold' } }];
      }),
      { columnStyles: { 1: { cellWidth: 32 } } },
    );
  }
  const mes = t.mesures.filter((x) => (i.mesures[x.id] ?? '').trim() !== '');
  if (mes.length) {
    rep.h2('Mesures relevées');
    rep.table(['Mesure', 'Valeur', 'Unité', 'Repère'], mes.map((x) => [x.libelle, i.mesures[x.id], x.unite, x.max !== undefined ? `≤ ${fmt(x.max, 0)}` : x.min !== undefined ? `≥ ${fmt(x.min, 0)}` : '']));
  }
  if (i.observations) {
    rep.h2('Observations');
    rep.para(i.observations);
  }
  if (i.pieces) {
    rep.h2('Pièces changées');
    rep.para(i.pieces);
  }
  if (i.photo) {
    rep.h2('Photo');
    const p = rep.doc.getImageProperties(i.photo);
    const w = Math.min(120, rep.inner);
    rep.image(i.photo, w, (w * p.height) / p.width);
  }
  rep.h2('Signature');
  if (i.signature) rep.image(i.signature, 60, 24);
  else rep.para('Non signé.');
  rep.para(`Réglementation : ${t.reglementation}`, 7.5, [110, 110, 110]);
  return rep.output();
}

export async function defiPdf(r: DefiResult, withCorrection: boolean, s: Settings): Promise<Uint8Array> {
  const rep = await Report.create('Résultat du défi', `${r.eleve}${r.classe ? ' (' + r.classe + ')' : ''} : ${r.fichier}`, s);
  rep.kv([['Élève', r.eleve], ['Classe', r.classe || ''], ['Date', dateFr(r.date)], ['Score', `${r.score} / ${r.questions.length}`], ['Maquette', r.fichier], ['Série n°', String(r.seed)]]);
  rep.table(
    withCorrection ? ['N°', 'Question', 'Réponse', 'Résultat', 'Corrigé'] : ['N°', 'Question', 'Réponse', 'Résultat'],
    r.questions.map((q, k) => {
      const row: any[] = [String(k + 1), q.texte, `${r.reponses[k] ?? ''}${q.unite && r.reponses[k] ? ' ' + q.unite : ''}`, { content: r.justes[k] ? 'Juste' : 'Faux', styles: { textColor: r.justes[k] ? [46, 125, 50] : [198, 40, 40], fontStyle: 'bold' } }];
      if (withCorrection) row.push(`${formatAnswer(q)}\n${q.explication}`);
      return row;
    }),
    { styles: { fontSize: 8 }, columnStyles: withCorrection ? { 0: { cellWidth: 8 }, 2: { cellWidth: 26 }, 3: { cellWidth: 15 }, 4: { cellWidth: 48 } } : { 0: { cellWidth: 8 }, 2: { cellWidth: 34 }, 3: { cellWidth: 18 } } },
  );
  const pct = r.questions.length ? (100 * r.score) / r.questions.length : 0;
  rep.para(`Note : ${fmt((20 * r.score) / Math.max(1, r.questions.length), 1)} / 20 (${fmt(pct, 0)} % de réussite).`, 11, [15, 76, 92]);
  return rep.output();
}

export async function energiePdf(m: Model | null, inp: EnergieInput, res: EnergieResult, s: Settings): Promise<Uint8Array> {
  const rep = await Report.create('Bilan énergétique simplifié', m ? src(m) : 'Saisie libre', s);
  rep.h2('Consommations annuelles');
  rep.table(
    ['Énergie', 'Quantité', 'kWh/an', 'Part chauffage', 'Prix (€/kWh)'],
    inp.consos.map((c) => {
      const d = ENERGY_BY_ID[c.type];
      return [d.label, `${fmt(c.quantite, 0)} ${d.unite}`, fmt(c.quantite * d.kwhParUnite, 0), `${fmt(c.partChauffage, 0)} %`, fmt(inp.prix[c.type] ?? d.prixKwh, 3)];
    }),
  );
  rep.kv([
    ['Surface', `${fmt(inp.surface, 1)} m²`],
    ['Consommation totale', `${fmt(res.totalKwh, 0)} kWh/an`],
    ['Ratio', `${fmt(res.ratio, 0)} kWh/m².an (${res.classe})`],
    ['Dont chauffage', `${fmt(res.chauffageKwh, 0)} kWh/an (${fmt(res.ratioChauffage, 0)} kWh/m².an)`],
    ['Coût estimé', `${fmt(res.cout, 0)} €/an`],
    ['Émissions', `${fmt(res.co2 / 1000, 2)} t CO2/an`],
  ]);
  rep.para("Ratio en énergie finale, à titre pédagogique : ce n'est pas un DPE (qui raisonne en énergie primaire et en émissions).", 8, [110, 110, 110]);
  if (res.gains.length) {
    rep.h2('Actions étudiées (gains estimés, action seule)');
    rep.table(['Action', 'Hypothèse', 'kWh/an', '€/an', 'kg CO2/an'], res.gains.map((g) => [g.action, g.hypothese, fmt(g.kwh, 0), fmt(g.euros, 0), fmt(g.co2, 0)]), { columnStyles: { 2: { halign: 'right' }, 3: { halign: 'right' }, 4: { halign: 'right' } } });
    rep.para(`Toutes actions cumulées : ${fmt(res.apres.kwh, 0)} kWh/an (${fmt(res.apres.ratio, 0)} kWh/m².an), ${fmt(res.apres.cout, 0)} €/an, ${fmt(res.apres.co2 / 1000, 2)} t CO2/an. Les gains ne s'additionnent pas : ils sont appliqués successivement.`);
  }
  return rep.output();
}
