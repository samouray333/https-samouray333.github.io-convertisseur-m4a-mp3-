import { computeMetre, type MetreResult } from '../../core/metre';
import { fmt, slug } from '../../core/format';
import { toCsv } from '../../core/csv';
import type { Ctx, Page } from '../ctx';
import { el, esc } from '../dom';
import { icon } from '../icons';

export class MetrePage implements Page {
  el = el('section');
  private res: MetreResult | null = null;
  private pct = 10;
  private body: HTMLElement;

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'page-inner' });
    inner.innerHTML = `
      <h1>${icon('ruler')} Métré des réseaux</h1>
      <p class="lead">Longueurs de tubes par système, matériau et diamètre ; gaines par section ; comptage des raccords, vannes et accessoires.</p>
      <div class="toolbar">
        <label class="inline">Chutes + <input type="number" class="num" min="0" max="100" step="1" data-k="pct" style="width:70px"> %</label>
        <span class="spacer"></span>
        <button class="btn" data-k="csv">${icon('csv')} Export CSV</button>
        <button class="btn primary" data-k="pdf">${icon('pdf')} Export PDF</button>
      </div>`;
    this.body = el('div');
    inner.appendChild(this.body);
    this.el.appendChild(inner);
    const pct = inner.querySelector<HTMLInputElement>('[data-k=pct]')!;
    pct.oninput = () => {
      this.pct = Math.max(0, Math.min(100, Number(pct.value.replace(',', '.')) || 0));
      this.compute();
    };
    inner.querySelector<HTMLButtonElement>('[data-k=csv]')!.onclick = () => this.csv();
    inner.querySelector<HTMLButtonElement>('[data-k=pdf]')!.onclick = () => this.pdf();
    this.pctInput = pct;
  }
  private pctInput: HTMLInputElement;

  modelChanged() {
    this.pct = this.ctx.settings.chutesPct;
    this.pctInput.value = String(this.pct);
    this.res = null;
  }

  show() {
    if (!this.res) this.compute();
  }

  private compute() {
    const m = this.ctx.model;
    if (!m) return;
    this.res = computeMetre(m, this.pct);
    this.render();
  }

  private render() {
    const r = this.res!;
    const totals = (rows: { longueur: number; longueurChutes: number }[]) => [rows.reduce((s, x) => s + x.longueur, 0), rows.reduce((s, x) => s + x.longueurChutes, 0)];
    const lenTable = (title: string, ico: string, rows: MetreResult['tubes'], col: string) => {
      if (!rows.length) return `<div class="card"><h2>${icon(ico)} ${title}</h2><div class="empty">Aucun élément.</div></div>`;
      let html = `<div class="card"><h2>${icon(ico)} ${title}</h2><div class="table-wrap"><table class="data"><thead><tr><th>Système</th><th>Matériau</th><th>${col}</th><th class="n">Tronçons</th><th class="n">Longueur</th><th class="n">Avec chutes (+${fmt(r.chutesPct, 0)} %)</th></tr></thead><tbody>`;
      let sys = '';
      for (const t of rows) {
        if (t.systeme !== sys) {
          sys = t.systeme;
          const sub = rows.filter((x) => x.systeme === sys);
          const [a, b] = totals(sub);
          html += `<tr class="group"><td colspan="4">${esc(sys)}</td><td class="n">${fmt(a, 2)} m</td><td class="n">${fmt(b, 2)} m</td></tr>`;
        }
        html += `<tr><td></td><td>${esc(t.materiau)}</td><td><b>${esc(t.designation)}</b></td><td class="n">${t.nb}</td><td class="n">${fmt(t.longueur, 2)} m</td><td class="n"><b>${fmt(t.longueurChutes, 2)} m</b></td></tr>`;
      }
      const [a, b] = totals(rows);
      html += `</tbody><tfoot><tr><td colspan="4">Total</td><td class="n">${fmt(a, 2)} m</td><td class="n">${fmt(b, 2)} m</td></tr></tfoot></table></div></div>`;
      return html;
    };
    const cntTable = (title: string, ico: string, rows: MetreResult['raccords'], withDes: boolean) => {
      if (!rows.length) return '';
      let html = `<div class="card"><h2>${icon(ico)} ${title}</h2><div class="table-wrap"><table class="data"><thead><tr><th>Système</th><th>Type</th>${withDes ? '<th>Diamètre</th>' : ''}<th class="n">Quantité</th></tr></thead><tbody>`;
      for (const x of rows) html += `<tr><td>${esc(x.systeme)}</td><td>${esc(x.categorie)}</td>${withDes ? `<td>${esc(x.designation)}</td>` : ''}<td class="n"><b>${x.nb}</b></td></tr>`;
      html += `</tbody><tfoot><tr><td colspan="${withDes ? 3 : 2}">Total</td><td class="n">${rows.reduce((s, x) => s + x.nb, 0)}</td></tr></tfoot></table></div></div>`;
      return html;
    };
    this.body.innerHTML =
      lenTable('Tubes', 'flame', r.tubes, 'Diamètre') +
      lenTable('Gaines de ventilation', 'fan', r.gaines, 'Section') +
      `<div class="grid-2">${cntTable('Raccords', 'layers', r.raccords, true)}${cntTable('Vannes et accessoires', 'pump', r.accessoires, false)}</div>`;
  }

  private name(ext: string) {
    return `metre_${slug(this.ctx.model!.data.fileName.replace(/\.ifc$/i, ''))}.${ext}`;
  }

  private csv() {
    const r = this.res!;
    const rows: (string | number)[][] = [];
    for (const t of r.tubes) rows.push(['Tube', t.systeme, t.materiau, t.designation, t.nb, t.longueur, t.longueurChutes]);
    for (const t of r.gaines) rows.push(['Gaine', t.systeme, t.materiau, t.designation, t.nb, t.longueur, t.longueurChutes]);
    for (const t of r.raccords) rows.push(['Raccord', t.systeme, t.categorie, t.designation, t.nb, '', '']);
    for (const t of r.accessoires) rows.push(['Accessoire', t.systeme, t.categorie, '', t.nb, '', '']);
    const csv = toCsv(['Famille', 'Système', 'Matériau / type', 'Diamètre / section', 'Quantité', 'Longueur (m)', `Longueur avec ${r.chutesPct} % de chutes (m)`], rows);
    void this.ctx.exportFile(this.name('csv'), csv, 'text/csv', 'Métré');
  }

  private async pdf() {
    const { metrePdf } = await import('../../pdf/reports');
    const bytes = await metrePdf(this.ctx.model!, this.res!, this.ctx.settings);
    await this.ctx.exportFile(this.name('pdf'), bytes, 'application/pdf', 'Métré');
  }
}
