import { checkCoherence, RULES, type Finding } from '../../core/coherence';
import { slug } from '../../core/format';
import type { Ctx, Page } from '../ctx';
import { el, esc } from '../dom';
import { icon } from '../icons';

const SEV: Record<string, [string, string]> = { erreur: ['err', 'Erreur'], alerte: ['warn', 'Alerte'], info: ['info', 'Info'] };

export class CoherencePage implements Page {
  el = el('section');
  private findings: Finding[] | null = null;
  private body: HTMLElement;

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'page-inner' });
    inner.innerHTML = `
      <h1>${icon('check')} Vérification de cohérence</h1>
      <p class="lead">Contrôles automatiques simples sur la maquette : robinets thermostatiques, extraction dans les pièces humides, rattachement des éléments aux systèmes.</p>
      <div class="toolbar"><span class="spacer"></span><button class="btn primary" data-k="pdf">${icon('pdf')} Export PDF</button></div>`;
    this.body = el('div');
    inner.appendChild(this.body);
    this.el.appendChild(inner);
    inner.querySelector<HTMLButtonElement>('[data-k=pdf]')!.onclick = async () => {
      const { coherencePdf } = await import('../../pdf/reports');
      await ctx.exportFile(`coherence_${slug(ctx.model!.data.fileName.replace(/\.ifc$/i, ''))}.pdf`, await coherencePdf(ctx.model!, this.findings ?? [], ctx.settings), 'application/pdf', 'Cohérence');
    };
  }

  modelChanged() {
    this.findings = null;
  }

  show() {
    if (!this.ctx.model) return;
    if (!this.findings) this.findings = checkCoherence(this.ctx.model);
    let html = '';
    for (const rule of Object.values(RULES)) {
      const list = this.findings.filter((f) => f.regle === rule);
      html += `<div class="card"><h2>${list.length ? icon('alert') : icon('check')} ${esc(rule)} <span class="pill ${list.length ? (list.some((f) => f.severite === 'erreur') ? 'err' : list[0].severite === 'info' ? 'info' : 'warn') : 'ok'}">${list.length ? list.length + ' constat' + (list.length > 1 ? 's' : '') : 'Conforme'}</span></h2>`;
      if (!list.length) html += '<div class="lead" style="margin:0">Aucun problème détecté.</div>';
      for (const f of list) {
        const [cls, lab] = SEV[f.severite];
        html += `<div class="hist-item"><span class="pill ${cls}">${lab}</span><div class="d">${esc(f.message)}</div><button class="btn small" data-ids="${f.elementIds.join(',')}">${icon('cube')} Voir en 3D</button></div>`;
      }
      html += '</div>';
    }
    this.body.innerHTML = html;
    this.body.querySelectorAll<HTMLButtonElement>('[data-ids]').forEach((b) => {
      b.onclick = () => {
        const ids = b.dataset.ids!.split(',').map(Number);
        this.ctx.showElement(ids[0], false);
        if (ids.length > 1) this.ctx.viewer?.fitIds(ids);
      };
    });
  }
}
