import { computeMetre, type CountRow, type LengthRow, type MetreResult } from '../../core/metre';
import { LOT_BY_ID } from '../../core/lots';
import type { LotId } from '../../core/types';
import { fmt, slug } from '../../core/format';
import { toCsv } from '../../core/csv';
import type { Ctx, Page } from '../ctx';
import { el, esc } from '../dom';
import { icon } from '../icons';

type Onglet = 'tubes' | 'gaines' | 'raccords' | 'commande';

export class MetrePage implements Page {
  el = el('section', { class: 'metre-page' });
  private res: MetreResult | null = null;
  private pct = 10;
  private storeyId: number | null = null;
  private systeme: string | null = null;
  private onglet: Onglet = 'tubes';
  private head: HTMLElement;
  private body: HTMLElement;
  private filters: HTMLElement;

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'page-inner' });
    inner.innerHTML = `
      <h1>${icon('ruler')} Métré des réseaux</h1>
      <p class="lead">Quantités issues de la maquette : longueurs par réseau, matériau et diamètre, conditionnement et quantités à commander, contenance en eau, surface de tôle des gaines, raccords et accessoires. Touchez ${icon('cube', 'inline-ico')} pour voir en 3D ce qui est compté.</p>`;
    this.filters = el('div', { class: 'toolbar metre-filters' });
    this.head = el('div');
    this.body = el('div');
    inner.append(this.filters, this.head, this.body);
    this.el.appendChild(inner);
  }

  modelChanged() {
    this.pct = this.ctx.settings.chutesPct;
    this.storeyId = null;
    this.systeme = null;
    this.res = null;
  }

  show() {
    if (!this.ctx.model) return;
    this.renderFilters();
    if (!this.res) this.compute();
  }

  private renderFilters() {
    const m = this.ctx.model!;
    const systems = [...new Set(m.data.systems.map((s) => s.name))].sort((a, b) => a.localeCompare(b, 'fr'));
    this.filters.innerHTML = `
      <label class="field inline-field">Niveau<select data-k="niv"><option value="">Tous les niveaux</option>${m.data.storeys.map((s) => `<option value="${s.id}" ${this.storeyId === s.id ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select></label>
      <label class="field inline-field">Réseau<select data-k="sys"><option value="">Tous les réseaux</option>${systems.map((s) => `<option ${this.systeme === s ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select></label>
      <label class="field inline-field">Chutes<span class="inline"><input type="number" class="num" min="0" max="100" step="1" data-k="pct" value="${this.pct}" style="width:70px"> %</span></label>
      <span class="spacer"></span>
      <button class="btn" data-k="csv">${icon('csv')} CSV</button>
      <button class="btn" data-k="pdfc">${icon('pdf')} Bon de commande</button>
      <button class="btn primary" data-k="pdf">${icon('pdf')} Métré PDF</button>`;
    const q = <T extends HTMLElement>(k: string) => this.filters.querySelector(`[data-k=${k}]`) as T;
    q<HTMLSelectElement>('niv').onchange = (e) => {
      const v = (e.target as HTMLSelectElement).value;
      this.storeyId = v ? Number(v) : null;
      this.compute();
    };
    q<HTMLSelectElement>('sys').onchange = (e) => {
      this.systeme = (e.target as HTMLSelectElement).value || null;
      this.compute();
    };
    q<HTMLInputElement>('pct').oninput = (e) => {
      this.pct = Math.max(0, Math.min(100, Number((e.target as HTMLInputElement).value.replace(',', '.')) || 0));
      this.compute();
    };
    q<HTMLButtonElement>('csv').onclick = () => this.csv();
    q<HTMLButtonElement>('pdf').onclick = () => this.pdf(false);
    q<HTMLButtonElement>('pdfc').onclick = () => this.pdf(true);
  }

  private compute() {
    const m = this.ctx.model;
    if (!m) return;
    this.res = computeMetre(m, { chutesPct: this.pct, storeyId: this.storeyId, systeme: this.systeme });
    this.render();
  }

  private lotColor(lot: string): string {
    return LOT_BY_ID[lot as LotId]?.color ?? '#8D99A6';
  }

  private render() {
    const r = this.res!;
    // indicateurs par réseau
    const cards = r.systemes
      .filter((s) => s.tubesM || s.gainesM)
      .map(
        (s) => `<button class="kpi kpi-sys" data-sys="${esc(s.systeme)}" style="--c:${this.lotColor(s.lot)}" title="Filtrer sur ce réseau">
          <div class="l">${esc(s.systeme)}</div>
          <div class="v">${s.tubesM ? `${fmt(s.tubesM, 1)} <small>m de tubes</small>` : `${fmt(s.gainesM, 1)} <small>m de gaines</small>`}</div>
          <div class="kpi-sub">${s.volumeL ? `Contenance ${fmt(s.volumeL, 1)} L` : s.surfaceM2 ? `Tôle ${fmt(s.surfaceM2, 1)} m²` : ''}${s.raccords ? ` · ${s.raccords} raccords` : ''}${s.accessoires ? ` · ${s.accessoires} accessoires` : ''}</div>
        </button>`,
      )
      .join('');
    // graphique des longueurs
    const lignes = [...r.tubes, ...r.gaines].sort((a, b) => b.longueur - a.longueur).slice(0, 14);
    const max = Math.max(1, ...lignes.map((l) => l.longueur));
    const chart = lignes.length
      ? `<div class="card"><h2>${icon('layers')} Répartition des longueurs</h2><div class="barchart">${lignes
          .map(
            (l) => `<div class="bar-row" title="${esc(l.systeme)}"><span class="bar-lbl">${esc(l.materiau)} <b>${esc(l.designation)}</b><em>${esc(l.systeme)}</em></span><span class="bar-track"><i style="width:${(100 * l.longueur) / max}%;background:${this.lotColor(l.lot)}"></i></span><span class="bar-val">${fmt(l.longueur, 1)} m</span></div>`,
          )
          .join('')}</div></div>`
      : '';
    const filtre = [this.storeyId !== null ? this.ctx.model!.storeyById.get(this.storeyId)?.name : '', this.systeme].filter(Boolean).join(' · ');
    this.head.innerHTML = `${filtre ? `<div class="filter-chip">${icon('search')} Filtre : ${esc(filtre)} <button class="x-btn" data-k="clear" title="Retirer le filtre">${icon('close')}</button></div>` : ''}
      <div class="kpis">${cards || '<div class="empty">Aucun tube ni gaine pour ce filtre.</div>'}</div>${chart}
      <div class="tabs-inline">${(
        [
          ['tubes', `Tubes (${r.tubes.length})`],
          ['gaines', `Gaines (${r.gaines.length})`],
          ['raccords', `Raccords et accessoires (${r.raccords.length + r.accessoires.length})`],
          ['commande', 'Bon de commande'],
        ] as [Onglet, string][]
      )
        .map(([k, l]) => `<button data-o="${k}" class="${this.onglet === k ? 'active' : ''}">${esc(l)}</button>`)
        .join('')}</div>`;
    this.head.querySelectorAll<HTMLButtonElement>('[data-sys]').forEach((b) => {
      b.onclick = () => {
        this.systeme = this.systeme === b.dataset.sys ? null : b.dataset.sys!;
        this.renderFilters();
        this.compute();
      };
    });
    this.head.querySelector<HTMLButtonElement>('[data-k=clear]')?.addEventListener('click', () => {
      this.systeme = null;
      this.storeyId = null;
      this.renderFilters();
      this.compute();
    });
    this.head.querySelectorAll<HTMLButtonElement>('[data-o]').forEach((b) => {
      b.onclick = () => {
        this.onglet = b.dataset.o as Onglet;
        this.render();
      };
    });
    this.body.innerHTML =
      this.onglet === 'tubes' ? this.tubesTable(r) : this.onglet === 'gaines' ? this.gainesTable(r) : this.onglet === 'raccords' ? this.countTables(r) : this.commandeTable(r);
    this.body.querySelectorAll<HTMLButtonElement>('[data-ids]').forEach((b) => {
      b.onclick = () => this.ctx.showElements(b.dataset.ids!.split(',').map(Number));
    });
  }

  private eye(ids: number[]): string {
    return `<button class="x-btn see3d" data-ids="${ids.join(',')}" title="Voir en 3D">${icon('cube')}</button>`;
  }

  private groupRows<T extends { systeme: string }>(rows: T[], line: (r: T) => string, sub: (rs: T[]) => string, cols: number, lot: (r: T) => string): string {
    let html = '';
    let sys = '';
    for (const row of rows) {
      if (row.systeme !== sys) {
        sys = row.systeme;
        const rs = rows.filter((x) => x.systeme === sys);
        html += `<tr class="group" style="--c:${this.lotColor(lot(row))}"><td colspan="${cols}"><span class="dot" style="background:${this.lotColor(lot(row))}"></span>${esc(sys)}</td>${sub(rs)}</tr>`;
      }
      html += line(row);
    }
    return html;
  }

  private tubesTable(r: MetreResult): string {
    if (!r.tubes.length) return '<div class="card empty">Aucun tube pour ce filtre.</div>';
    const tot = (rs: LengthRow[], f: (x: LengthRow) => number) => rs.reduce((s, x) => s + f(x), 0);
    const rows = this.groupRows(
      r.tubes,
      (t) => `<tr><td>${esc(t.materiau)}</td><td><b>${esc(t.designation)}</b></td><td class="n">${t.dInt ? fmt(t.dInt * 1000, 1) : ''}</td><td class="n">${t.nb}</td><td class="n">${fmt(t.longueur, 2)}</td><td class="n"><b>${fmt(t.longueurChutes, 2)}</b></td><td>${esc(t.conditionnement.libelle)}</td><td class="n"><b>${t.aCommander}</b></td><td class="n">${t.colliers}</td><td class="n">${fmt(t.volumeL, 2)}</td><td>${this.eye(t.ids)}</td></tr>`,
      (rs) => `<td class="n">${fmt(tot(rs, (x) => x.longueur), 2)}</td><td class="n">${fmt(tot(rs, (x) => x.longueurChutes), 2)}</td><td colspan="3"></td><td class="n">${fmt(tot(rs, (x) => x.volumeL), 1)}</td><td>${this.eye(rs.flatMap((x) => x.ids))}</td>`,
      4,
      (t) => t.lot,
    );
    return `<div class="card table-card"><div class="table-wrap"><table class="data metre-table"><thead><tr><th>Matériau</th><th>Diamètre</th><th class="n">Ø int. (mm)</th><th class="n">Tronçons</th><th class="n">Longueur (m)</th><th class="n">+ ${fmt(r.chutesPct, 0)} % chutes</th><th>Conditionnement</th><th class="n">À commander</th><th class="n">Colliers ≈</th><th class="n">Contenance (L)</th><th></th></tr></thead><tbody>${rows}</tbody>
      <tfoot><tr><td colspan="4">Total</td><td class="n">${fmt(tot(r.tubes, (x) => x.longueur), 2)}</td><td class="n">${fmt(tot(r.tubes, (x) => x.longueurChutes), 2)}</td><td colspan="2"></td><td class="n">${tot(r.tubes, (x) => x.colliers)}</td><td class="n">${fmt(tot(r.tubes, (x) => x.volumeL), 1)}</td><td></td></tr></tfoot></table></div>
      <p class="lead small">Contenance = π × Ø int² / 4 × longueur : volume d'eau des tubes, à ajouter à celui des émetteurs et du générateur pour dimensionner le vase d'expansion. Colliers estimés en pose horizontale (cuivre 1,25 m jusqu'au Ø 22, multicouche 1 m, PER 0,8 m, acier 2,5 à 3 m).</p></div>`;
  }

  private gainesTable(r: MetreResult): string {
    if (!r.gaines.length) return '<div class="card empty">Aucune gaine pour ce filtre.</div>';
    const tot = (rs: LengthRow[], f: (x: LengthRow) => number) => rs.reduce((s, x) => s + f(x), 0);
    const rows = this.groupRows(
      r.gaines,
      (t) => `<tr><td>${esc(t.materiau)}</td><td><b>${esc(t.designation)}</b></td><td class="n">${t.nb}</td><td class="n">${fmt(t.longueur, 2)}</td><td class="n"><b>${fmt(t.longueurChutes, 2)}</b></td><td class="n">${fmt(t.surfaceM2, 2)}</td><td>${esc(t.conditionnement.libelle)}</td><td class="n"><b>${t.aCommander}</b></td><td class="n">${t.colliers}</td><td>${this.eye(t.ids)}</td></tr>`,
      (rs) => `<td class="n">${fmt(tot(rs, (x) => x.longueur), 2)}</td><td class="n">${fmt(tot(rs, (x) => x.longueurChutes), 2)}</td><td class="n">${fmt(tot(rs, (x) => x.surfaceM2), 1)}</td><td colspan="3"></td><td>${this.eye(rs.flatMap((x) => x.ids))}</td>`,
      3,
      (t) => t.lot,
    );
    return `<div class="card table-card"><div class="table-wrap"><table class="data metre-table"><thead><tr><th>Matériau</th><th>Section</th><th class="n">Tronçons</th><th class="n">Longueur (m)</th><th class="n">+ ${fmt(r.chutesPct, 0)} % chutes</th><th class="n">Surface développée (m²)</th><th>Conditionnement</th><th class="n">À commander</th><th class="n">Supports ≈</th><th></th></tr></thead><tbody>${rows}</tbody>
      <tfoot><tr><td colspan="3">Total</td><td class="n">${fmt(tot(r.gaines, (x) => x.longueur), 2)}</td><td class="n">${fmt(tot(r.gaines, (x) => x.longueurChutes), 2)}</td><td class="n">${fmt(tot(r.gaines, (x) => x.surfaceM2), 1)}</td><td colspan="2"></td><td class="n">${tot(r.gaines, (x) => x.colliers)}</td><td></td></tr></tfoot></table></div>
      <p class="lead small">Surface développée = périmètre × longueur (chutes comprises) : quantité de tôle ou d'isolant pour les gaines. Gaine ronde : π × Ø ; rectangulaire : 2 × (largeur + hauteur).</p></div>`;
  }

  private countTables(r: MetreResult): string {
    const table = (title: string, rows: CountRow[], withDes: boolean) => {
      if (!rows.length) return '';
      let html = `<div class="card table-card"><h2>${title}</h2><div class="table-wrap"><table class="data"><thead><tr><th>Réseau</th><th>Type</th>${withDes ? '<th>Diamètre</th>' : ''}<th class="n">Quantité</th><th></th></tr></thead><tbody>`;
      for (const x of rows) html += `<tr><td>${esc(x.systeme)}</td><td>${esc(x.categorie)}</td>${withDes ? `<td>${esc(x.designation)}</td>` : ''}<td class="n"><b>${x.nb}</b></td><td>${this.eye(x.ids)}</td></tr>`;
      html += `</tbody><tfoot><tr><td colspan="${withDes ? 3 : 2}">Total</td><td class="n">${rows.reduce((s, x) => s + x.nb, 0)}</td><td></td></tr></tfoot></table></div></div>`;
      return html;
    };
    return `<div class="grid-2">${table(`${icon('layers')} Raccords`, r.raccords, true)}${table(`${icon('pump')} Vannes et accessoires`, r.accessoires, false)}</div>` || '<div class="card empty">Aucun raccord.</div>';
  }

  private commandeRows(r: MetreResult): { ref: string; cond: string; qte: number; unite: string; longueur: number }[] {
    const map = new Map<string, { ref: string; cond: string; qte: number; unite: string; longueur: number }>();
    for (const t of [...r.tubes, ...r.gaines]) {
      const isTube = r.tubes.includes(t);
      const ref = `${isTube ? 'Tube' : 'Gaine'} ${t.materiau.toLowerCase()} ${t.designation}`;
      const key = `${ref}|${t.conditionnement.libelle}`;
      const x = map.get(key) ?? { ref, cond: t.conditionnement.libelle, qte: 0, unite: '', longueur: 0 };
      x.longueur += t.longueurChutes;
      x.qte = Math.ceil(x.longueur / t.conditionnement.longueur - 1e-9);
      x.unite = /barre/i.test(t.conditionnement.libelle) ? 'barre(s)' : /couronne/i.test(t.conditionnement.libelle) ? 'couronne(s)' : /rouleau/i.test(t.conditionnement.libelle) ? 'rouleau(x)' : 'unité(s)';
      map.set(key, x);
    }
    return [...map.values()].sort((a, b) => a.ref.localeCompare(b.ref, 'fr', { numeric: true }));
  }

  private commandeTable(r: MetreResult): string {
    const rows = this.commandeRows(r);
    const fittings = new Map<string, number>();
    for (const x of [...r.raccords, ...r.accessoires]) fittings.set(`${x.categorie}${x.designation ? ' ' + x.designation : ''}`, (fittings.get(`${x.categorie}${x.designation ? ' ' + x.designation : ''}`) ?? 0) + x.nb);
    const colliers = new Map<string, number>();
    for (const t of r.tubes) colliers.set(`Collier ${t.materiau.toLowerCase()} ${t.designation}`, (colliers.get(`Collier ${t.materiau.toLowerCase()} ${t.designation}`) ?? 0) + t.colliers);
    return `<div class="card table-card"><h2>${icon('list')} Bon de commande (tous réseaux confondus)</h2><div class="table-wrap"><table class="data"><thead><tr><th>Article</th><th>Conditionnement</th><th class="n">Longueur nécessaire (m)</th><th class="n">Quantité</th></tr></thead><tbody>
      ${rows.map((x) => `<tr><td><b>${esc(x.ref)}</b></td><td>${esc(x.cond)}</td><td class="n">${fmt(x.longueur, 2)}</td><td class="n"><b>${x.qte}</b> ${esc(x.unite)}</td></tr>`).join('')}
      ${[...fittings].sort((a, b) => a[0].localeCompare(b[0], 'fr', { numeric: true })).map(([k, n]) => `<tr><td>${esc(k)}</td><td>À l'unité</td><td></td><td class="n"><b>${n}</b></td></tr>`).join('')}
      ${[...colliers].map(([k, n]) => `<tr><td>${esc(k)} (estimation)</td><td>À l'unité</td><td></td><td class="n"><b>${n}</b></td></tr>`).join('')}
      </tbody></table></div><p class="lead small">Chutes de ${fmt(r.chutesPct, 0)} % incluses. Conditionnements usuels : cuivre en barres de 4 m (5 m au-delà du Ø 22), multicouche et PER en couronnes de 100 m (barres de 5 m ou couronnes de 50 m au-delà du Ø 20), acier en barres de 6 m, gaines rigides en conduits de 3 m, gaines souples en rouleaux de 10 m, gaines rectangulaires en tronçons de 1,5 m.</p></div>`;
  }

  private name(ext: string, suffix = '') {
    return `metre${suffix}_${slug(this.ctx.model!.data.fileName.replace(/\.ifc$/i, ''))}.${ext}`;
  }

  private csv() {
    const r = this.res!;
    const rows: (string | number)[][] = [];
    for (const t of r.tubes) rows.push(['Tube', t.systeme, t.materiau, t.designation, t.dInt ? Math.round(t.dInt * 10000) / 10 : '', t.nb, t.longueur, t.longueurChutes, t.conditionnement.libelle, t.aCommander, t.colliers, t.volumeL, '', t.niveaux.join(', ')]);
    for (const t of r.gaines) rows.push(['Gaine', t.systeme, t.materiau, t.designation, '', t.nb, t.longueur, t.longueurChutes, t.conditionnement.libelle, t.aCommander, t.colliers, '', t.surfaceM2, t.niveaux.join(', ')]);
    for (const t of r.raccords) rows.push(['Raccord', t.systeme, t.categorie, t.designation, '', t.nb, '', '', 'Unité', t.nb, '', '', '', '']);
    for (const t of r.accessoires) rows.push(['Accessoire', t.systeme, t.categorie, '', '', t.nb, '', '', 'Unité', t.nb, '', '', '', '']);
    const csv = toCsv(
      ['Famille', 'Réseau', 'Matériau / type', 'Diamètre / section', 'Ø intérieur (mm)', 'Quantité ou tronçons', 'Longueur (m)', `Longueur avec ${r.chutesPct} % de chutes (m)`, 'Conditionnement', 'À commander', 'Colliers estimés', 'Contenance (L)', 'Surface développée (m²)', 'Niveaux'],
      rows,
    );
    void this.ctx.exportFile(this.name('csv'), csv, 'text/csv', 'Métré');
  }

  private async pdf(commande: boolean) {
    const { metrePdf } = await import('../../pdf/reports');
    const r = this.res!;
    const filtre = [this.storeyId !== null ? this.ctx.model!.storeyById.get(this.storeyId)?.name : '', this.systeme].filter(Boolean).join(' · ');
    const bytes = await metrePdf(this.ctx.model!, r, this.ctx.settings, { commande, filtre, lignesCommande: this.commandeRows(r) });
    await this.ctx.exportFile(this.name('pdf', commande ? '_bon_de_commande' : ''), bytes, 'application/pdf', commande ? 'Bon de commande' : 'Métré');
  }
}
