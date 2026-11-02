import { computeNomenclature, NOM_CATEGORIES, type NomRow } from '../../core/nomenclature';
import { slug } from '../../core/format';
import { toCsv } from '../../core/csv';
import type { Ctx, Page } from '../ctx';
import { el, esc } from '../dom';
import { icon } from '../icons';

export class NomenclaturePage implements Page {
  el = el('section');
  private rows: NomRow[] | null = null;
  private body: HTMLElement;
  private filter = '';

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'page-inner' });
    inner.innerHTML = `
      <h1>${icon('list')} Nomenclature des équipements</h1>
      <p class="lead">Générateurs, émetteurs, circulateurs, vases, soupapes, ventilation, régulation et sanitaires, avec leurs caractéristiques. Touchez une ligne pour voir l'équipement en 3D.</p>
      <div class="toolbar">
        <select data-k="cat"><option value="">Toutes les catégories</option>${NOM_CATEGORIES.map((c) => `<option>${esc(c)}</option>`).join('')}</select>
        <span class="spacer"></span>
        <button class="btn" data-k="csv">${icon('csv')} Export CSV</button>
        <button class="btn primary" data-k="pdf">${icon('pdf')} Export PDF</button>
      </div>`;
    this.body = el('div');
    inner.appendChild(this.body);
    this.el.appendChild(inner);
    const cat = inner.querySelector<HTMLSelectElement>('[data-k=cat]')!;
    cat.onchange = () => {
      this.filter = cat.value;
      this.render();
    };
    inner.querySelector<HTMLButtonElement>('[data-k=csv]')!.onclick = () => this.csv();
    inner.querySelector<HTMLButtonElement>('[data-k=pdf]')!.onclick = () => this.pdf();
  }

  modelChanged() {
    this.rows = null;
  }

  show() {
    if (!this.rows && this.ctx.model) {
      this.rows = computeNomenclature(this.ctx.model);
      this.render();
    }
  }

  private get shown(): NomRow[] {
    return (this.rows ?? []).filter((r) => !this.filter || r.categorie === this.filter);
  }

  private render() {
    const rows = this.shown;
    if (!rows.length) {
      this.body.innerHTML = '<div class="card empty">Aucun équipement dans cette catégorie.</div>';
      return;
    }
    const counts: Record<string, number> = {};
    for (const r of this.rows ?? []) counts[r.categorie] = (counts[r.categorie] ?? 0) + 1;
    let html = `<div class="kpis">${Object.entries(counts).slice(0, 6).map(([k, v]) => `<div class="kpi"><div class="l">${esc(k)}</div><div class="v">${v}</div></div>`).join('')}</div>`;
    html += `<div class="table-wrap card" style="padding:0"><table class="data"><thead><tr><th>Désignation</th><th>Localisation</th><th>Marque / modèle</th><th class="n">Puissance</th><th>Caractéristiques</th></tr></thead><tbody>`;
    let cat = '';
    for (const r of rows) {
      if (r.categorie !== cat) {
        cat = r.categorie;
        html += `<tr class="group"><td colspan="5">${esc(cat)} (${counts[cat]})</td></tr>`;
      }
      html += `<tr class="clickable" data-id="${r.id}"><td><b>${esc(r.designation)}</b><br><small class="lead">${esc(r.systeme)}</small></td><td>${esc(r.localisation)}</td><td>${esc([r.marque, r.modele].filter(Boolean).join(' '))}</td><td class="n">${esc(r.puissance)}</td><td style="font-size:13px">${esc(r.caracteristiques)}</td></tr>`;
    }
    html += '</tbody></table></div>';
    this.body.innerHTML = html;
    this.body.querySelectorAll<HTMLElement>('tr[data-id]').forEach((tr) => (tr.onclick = () => this.ctx.showElement(Number(tr.dataset.id))));
  }

  private name(ext: string) {
    return `nomenclature_${slug(this.ctx.model!.data.fileName.replace(/\.ifc$/i, ''))}.${ext}`;
  }

  private csv() {
    const rows = this.shown.map((r) => [r.categorie, r.designation, r.localisation, r.systeme, r.marque, r.modele, r.puissance, r.caracteristiques, r.gid]);
    void this.ctx.exportFile(this.name('csv'), toCsv(['Catégorie', 'Désignation', 'Localisation', 'Système', 'Marque', 'Modèle', 'Puissance', 'Caractéristiques', 'GlobalId'], rows), 'text/csv', 'Nomenclature');
  }

  private async pdf() {
    const { nomenclaturePdf } = await import('../../pdf/reports');
    await this.ctx.exportFile(this.name('pdf'), await nomenclaturePdf(this.ctx.model!, this.shown, this.ctx.settings), 'application/pdf', 'Nomenclature');
  }
}
