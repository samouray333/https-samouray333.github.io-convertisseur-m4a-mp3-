import {
  effectivePeriod,
  fluidInfo,
  maintainable,
  maintStatus,
  STATUS_LABEL,
  type Intervention,
  type MaintStatus,
  type MaintType,
} from '../../core/maintenance';
import { dateFr, fmt, slug, today } from '../../core/format';
import type { El } from '../../core/types';
import { elementFacts } from '../../core/facts';
import { deleteIntervention, listInterventions, saveIntervention } from '../../store/db';
import type { Ctx, Page } from '../ctx';
import { confirmBox, el, esc, toast } from '../dom';
import { icon } from '../icons';
import { resizeImage, SignaturePad } from '../signature';

const SCLS: Record<MaintStatus, string> = { en_cours: 'warn', retard: 'err', a_prevoir: 'info', a_jour: 'ok', inconnu: 'mute' };
export const MARKER_COLORS: Partial<Record<MaintStatus, string>> = { retard: '#e53935', en_cours: '#fb8c00' };

export class MaintenancePage implements Page {
  el = el('section');
  private items: { el: El; type: MaintType }[] = [];
  private interventions: Intervention[] = [];
  private selGid: string | null = null;
  private listBox: HTMLElement;
  private detail: HTMLElement;
  private editing: Intervention | null = null;
  private loadedKey = '';

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'page-inner' });
    inner.innerHTML = `
      <h1>${icon('wrench')} Maintenance et carnet d'interventions</h1>
      <p class="lead">Fiches équipements, check-lists d'entretien (fichier maintenance.json éditable), carnet daté et rapport PDF signé. Les équipements en retard ou avec une intervention en cours apparaissent en couleur dans la vue 3D.</p>`;
    const grid = el('div', { class: 'maint' });
    this.listBox = el('div', { class: 'eq-list' });
    this.detail = el('div');
    grid.append(this.listBox, this.detail);
    inner.appendChild(grid);
    this.el.appendChild(inner);
    document.addEventListener('bimys:maint', (e) => {
      this.selGid = (e as CustomEvent).detail;
      this.editing = null;
      void this.refresh();
    });
  }

  modelChanged() {
    this.items = this.ctx.model ? maintainable(this.ctx.model, this.ctx.maint) : [];
    this.selGid = null;
    this.editing = null;
    this.loadedKey = '';
  }

  async show() {
    await this.refresh();
  }

  private async loadInterventions() {
    const m = this.ctx.model;
    if (!m) return;
    this.interventions = await listInterventions(m.fileKey).catch(() => []);
    this.loadedKey = m.fileKey;
  }

  async updateMarkers() {
    const m = this.ctx.model;
    if (!m) return;
    if (!this.items.length) this.items = maintainable(m, this.ctx.maint);
    await this.loadInterventions();
    const t = today();
    const marks: { id: number; color: string }[] = [];
    for (const it of this.items) {
      const st = maintStatus(it.el, it.type, this.interventions, t, this.ctx.maint).status;
      const c = MARKER_COLORS[st];
      if (c) marks.push({ id: it.el.id, color: c });
    }
    this.ctx.viewer?.setMarkers(marks);
  }

  private async refresh() {
    if (!this.ctx.model) return;
    if (!this.items.length) this.items = maintainable(this.ctx.model, this.ctx.maint);
    await this.loadInterventions();
    if (!this.selGid && this.items.length) this.selGid = this.items[0].el.gid;
    this.renderList();
    this.renderDetail();
  }

  private renderList() {
    const t = today();
    this.listBox.innerHTML = '';
    if (!this.items.length) {
      this.listBox.innerHTML = '<div class="card empty">Aucun équipement à entretenir reconnu dans cette maquette.</div>';
      return;
    }
    const counts: Partial<Record<MaintStatus, number>> = {};
    for (const it of this.items) {
      const st = maintStatus(it.el, it.type, this.interventions, t, this.ctx.maint);
      counts[st.status] = (counts[st.status] ?? 0) + 1;
      const b = el('button', { class: 'eq-item' + (it.el.gid === this.selGid ? ' sel' : '') });
      b.innerHTML = `<div class="nm"><b>${esc(it.el.name || it.type.libelle)}</b><span>${esc(it.type.libelle)}${st.echeance ? ` · échéance ${dateFr(st.echeance)}` : ''}</span></div><span class="pill ${SCLS[st.status]}">${esc(STATUS_LABEL[st.status].replace(' (< 30 jours)', ''))}</span>`;
      b.onclick = () => {
        this.selGid = it.el.gid;
        this.editing = null;
        this.renderList();
        this.renderDetail();
        if (innerWidth < 900) this.detail.scrollIntoView({ behavior: 'smooth' });
      };
      this.listBox.appendChild(b);
    }
    const sum = el('div', { class: 'lead', style: { fontSize: '13px', margin: '4px 2px' } }, `${counts.retard ?? 0} en retard, ${counts.en_cours ?? 0} en cours, ${counts.a_prevoir ?? 0} à prévoir, ${counts.a_jour ?? 0} à jour.`);
    this.listBox.prepend(sum);
  }

  private get selected(): { el: El; type: MaintType } | undefined {
    return this.items.find((x) => x.el.gid === this.selGid);
  }

  private renderDetail() {
    const it = this.selected;
    this.detail.innerHTML = '';
    if (!it) return;
    if (this.editing) return this.renderForm(it);
    const m = this.ctx.model!;
    const st = maintStatus(it.el, it.type, this.interventions, today(), this.ctx.maint);
    const fl = it.type.etancheite ? fluidInfo(it.el, this.ctx.maint) : null;
    const loc = [it.el.storeyId !== null ? m.storeyById.get(it.el.storeyId)?.name : '', it.el.spaceId !== null ? m.byId.get(it.el.spaceId)?.name : ''].filter(Boolean).join(' / ');
    const card = el('div', { class: 'card' });
    card.innerHTML = `
      <h2>${icon('info')} ${esc(it.el.name)}</h2>
      <div class="toolbar">
        <span class="pill ${SCLS[st.status]}">${esc(STATUS_LABEL[st.status])}</span>
        <span class="lead" style="margin:0">${esc(it.type.libelle)} · périodicité ${effectivePeriod(it.el, it.type, this.ctx.maint)} mois${st.reference ? ` · référence ${dateFr(st.reference)}` : ''}${st.echeance ? ` · prochaine échéance <b>${dateFr(st.echeance)}</b>` : ''}</span>
        <span class="spacer"></span>
        <button class="btn" data-a="see">${icon('cube')} Voir en 3D</button>
        <button class="btn accent" data-a="new">${icon('plus')} Nouvelle intervention</button>
      </div>
      ${fl ? `<div class="formula">Fluide <b>${esc(fl.fluide)}</b>, charge ${fmt(fl.chargeKg, 2)} kg, PRG ${fmt(fl.gwp ?? 0, 0)} → <b>${fl.teqCO2 !== null ? fmt(fl.teqCO2, 2) : '?'} t éq. CO2</b> (charge × PRG / 1000).<br>${esc(fl.texte)}</div>` : ''}
      <h3>Caractéristiques (maquette)</h3>
      <div class="table-wrap"><table class="data"><tbody>${[['Localisation', loc || 'Non localisé'], ...elementFacts(it.el)].map(([k, v]) => `<tr><td style="width:45%">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</tbody></table></div>
      <h3>Check-list d'entretien</h3>
      <ol style="margin:0 0 6px 18px;padding:0">${it.type.checklist.map((c) => `<li style="margin:3px 0">${esc(c.libelle)}</li>`).join('')}</ol>
      <p class="lead" style="font-size:12.5px">${esc(it.type.reglementation)}</p>`;
    card.querySelector<HTMLButtonElement>('[data-a=see]')!.onclick = () => this.ctx.showElement(it.el.id);
    card.querySelector<HTMLButtonElement>('[data-a=new]')!.onclick = () => this.newIntervention(it);
    this.detail.appendChild(card);

    const hist = el('div', { class: 'card' });
    const list = this.interventions.filter((i) => i.gid === it.el.gid).sort((a, b) => b.date.localeCompare(a.date) || b.createdAt - a.createdAt);
    hist.innerHTML = `<h2>${icon('list')} Carnet d'interventions (${list.length})</h2>`;
    if (!list.length) hist.innerHTML += '<div class="empty">Aucune intervention enregistrée pour cet équipement.</div>';
    for (const i of list) {
      const nok = Object.values(i.checklist).filter((v) => v === 'nok').length;
      const row = el('div', { class: 'hist-item' });
      row.innerHTML = `<div class="d"><b>${dateFr(i.date)}</b> · ${i.type === 'preventive' ? 'Préventive' : 'Corrective'} · ${esc(i.intervenant || 'intervenant non renseigné')}<br><small class="lead">${esc((i.observations || '').slice(0, 120))}${nok ? ` · ${nok} non-conformité(s)` : ''}</small></div>
        <span class="pill ${i.statut === 'en_cours' ? 'warn' : 'ok'}">${i.statut === 'en_cours' ? 'En cours' : 'Terminée'}</span>
        <button class="btn small" data-a="edit">${icon('sign')} Ouvrir</button>
        <button class="btn small" data-a="pdf">${icon('pdf')} Rapport</button>
        <button class="x-btn" data-a="del" title="Supprimer">${icon('trash')}</button>`;
      row.querySelector<HTMLButtonElement>('[data-a=edit]')!.onclick = () => {
        this.editing = structuredClone(i);
        this.renderDetail();
      };
      row.querySelector<HTMLButtonElement>('[data-a=pdf]')!.onclick = () => this.pdf(it, i);
      row.querySelector<HTMLButtonElement>('[data-a=del]')!.onclick = async () => {
        if (!(await confirmBox('Supprimer', `Supprimer l'intervention du ${dateFr(i.date)} ?`, 'Supprimer'))) return;
        await deleteIntervention(i.id);
        await this.afterChange();
      };
      hist.appendChild(row);
    }
    this.detail.appendChild(hist);
  }

  private newIntervention(it: { el: El; type: MaintType }) {
    const m = this.ctx.model!;
    this.editing = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      fileKey: m.fileKey,
      gid: it.el.gid,
      elementName: it.el.name,
      date: today(),
      intervenant: this.ctx.settings.intervenant,
      type: 'preventive',
      statut: 'en_cours',
      checklist: Object.fromEntries(it.type.checklist.map((c) => [c.id, ''])),
      mesures: {},
      observations: '',
      pieces: '',
      createdAt: Date.now(),
    };
    this.renderDetail();
  }

  private renderForm(it: { el: El; type: MaintType }) {
    const i = this.editing!;
    const card = el('div', { class: 'card' });
    card.innerHTML = `
      <h2>${icon('sign')} Intervention : ${esc(it.el.name)}</h2>
      <div class="grid">
        <label class="field">Date<input type="date" data-f="date" value="${esc(i.date)}"></label>
        <label class="field">Intervenant<input type="text" data-f="intervenant" value="${esc(i.intervenant)}" placeholder="Nom, classe"></label>
        <label class="field">Type<select data-f="type"><option value="preventive">Préventive</option><option value="corrective">Corrective</option></select></label>
        <label class="field">Statut<select data-f="statut"><option value="en_cours">En cours</option><option value="terminee">Terminée</option></select></label>
      </div>
      <h3>Points de contrôle</h3><div data-k="checks"></div>
      ${it.type.mesures.length ? '<h3>Mesures relevées</h3><div class="grid" data-k="mes"></div>' : ''}
      <h3>Observations</h3><textarea data-f="observations" placeholder="Constats, réglages effectués, conseils donnés à l'usager…">${esc(i.observations)}</textarea>
      <h3>Pièces changées</h3><textarea data-f="pieces" style="min-height:50px" placeholder="Référence, quantité">${esc(i.pieces)}</textarea>
      <h3>Photo (optionnelle)</h3>
      <div class="toolbar"><label class="btn">${icon('camera')} Prendre / choisir une photo<input type="file" accept="image/*" capture="environment" data-k="photo" hidden></label><button class="btn small danger" data-k="nophoto" ${i.photo ? '' : 'hidden'}>Retirer</button></div>
      <img class="photo-prev" data-k="prev" ${i.photo ? `src="${i.photo}"` : 'hidden'} alt="Photo de l'intervention">
      <h3>Signature</h3><div data-k="sig"></div>
      <div class="toolbar" style="margin-top:6px"><button class="btn small" data-k="clearsig">Effacer la signature</button></div>
      <div class="toolbar" style="margin-top:14px"><button class="btn" data-k="cancel">Annuler</button><span class="spacer"></span><button class="btn" data-k="savepdf">${icon('pdf')} Enregistrer + rapport PDF</button><button class="btn primary" data-k="save">${icon('save')} Enregistrer</button></div>`;
    const q = <T extends HTMLElement>(s: string) => card.querySelector(s) as T;
    q<HTMLSelectElement>('[data-f=type]').value = i.type;
    q<HTMLSelectElement>('[data-f=statut]').value = i.statut;
    const checks = q<HTMLElement>('[data-k=checks]');
    for (const c of it.type.checklist) {
      const row = el('div', { class: 'check-row' });
      row.innerHTML = `<div class="lb">${esc(c.libelle)}</div><div class="tri"><button data-v="ok" class="ok">Conforme</button><button data-v="nok" class="nok">Non conforme</button><button data-v="na" class="na">S.O.</button></div>`;
      const paint = () => row.querySelectorAll<HTMLButtonElement>('button').forEach((b) => b.classList.toggle('on', i.checklist[c.id] === b.dataset.v));
      row.querySelectorAll<HTMLButtonElement>('button').forEach((b) => {
        b.onclick = () => {
          i.checklist[c.id] = i.checklist[c.id] === b.dataset.v ? '' : (b.dataset.v as any);
          paint();
        };
      });
      paint();
      checks.appendChild(row);
    }
    const all = el('button', { class: 'btn small', style: { marginTop: '6px' } }, 'Tout conforme');
    all.onclick = () => {
      for (const c of it.type.checklist) i.checklist[c.id] = 'ok';
      checks.querySelectorAll('.check-row').forEach((r) => r.querySelectorAll<HTMLButtonElement>('button').forEach((b) => b.classList.toggle('on', b.dataset.v === 'ok')));
    };
    checks.appendChild(all);
    const mes = card.querySelector<HTMLElement>('[data-k=mes]');
    for (const d of it.type.mesures) {
      const f = el('label', { class: 'field' }, `${esc(d.libelle)} (${esc(d.unite)})${d.max !== undefined ? ` ≤ ${d.max}` : ''}`);
      const input = el('input', { type: 'text', inputmode: 'decimal', value: i.mesures[d.id] ?? '' });
      input.oninput = () => {
        i.mesures[d.id] = input.value;
        const v = Number(input.value.replace(',', '.'));
        input.classList.toggle('missing', d.max !== undefined && Number.isFinite(v) && v > d.max);
      };
      f.appendChild(input);
      mes?.appendChild(f);
    }
    const pad = new SignaturePad(i.signature);
    q('[data-k=sig]').appendChild(pad.canvas);
    q<HTMLButtonElement>('[data-k=clearsig]').onclick = () => pad.clear();
    const photo = q<HTMLInputElement>('[data-k=photo]');
    photo.onchange = async () => {
      const f = photo.files?.[0];
      if (!f) return;
      try {
        i.photo = await resizeImage(f);
        const img = q<HTMLImageElement>('[data-k=prev]');
        img.src = i.photo;
        img.hidden = false;
        q('[data-k=nophoto]').hidden = false;
      } catch (e: any) {
        toast(e.message, { error: true });
      }
    };
    q<HTMLButtonElement>('[data-k=nophoto]').onclick = () => {
      i.photo = undefined;
      q('[data-k=prev]').hidden = true;
      q('[data-k=nophoto]').hidden = true;
    };
    const collect = () => {
      i.date = q<HTMLInputElement>('[data-f=date]').value || today();
      i.intervenant = q<HTMLInputElement>('[data-f=intervenant]').value.trim();
      i.type = q<HTMLSelectElement>('[data-f=type]').value as any;
      i.statut = q<HTMLSelectElement>('[data-f=statut]').value as any;
      i.observations = q<HTMLTextAreaElement>('[data-f=observations]').value;
      i.pieces = q<HTMLTextAreaElement>('[data-f=pieces]').value;
      i.signature = pad.toDataURL();
    };
    const save = async (withPdf: boolean) => {
      collect();
      await saveIntervention(i);
      if (i.intervenant && i.intervenant !== this.ctx.settings.intervenant) await this.ctx.saveSettings({ ...this.ctx.settings, intervenant: i.intervenant });
      const saved = i;
      this.editing = null;
      await this.afterChange();
      toast('Intervention enregistrée.');
      if (withPdf) await this.pdf(it, saved);
    };
    q<HTMLButtonElement>('[data-k=save]').onclick = () => save(false);
    q<HTMLButtonElement>('[data-k=savepdf]').onclick = () => save(true);
    q<HTMLButtonElement>('[data-k=cancel]').onclick = () => {
      this.editing = null;
      this.renderDetail();
    };
    this.detail.appendChild(card);
  }

  private async afterChange() {
    await this.loadInterventions();
    this.renderList();
    this.renderDetail();
    await this.updateMarkers();
  }

  private async pdf(it: { el: El; type: MaintType }, i: Intervention) {
    const { interventionPdf } = await import('../../pdf/reports');
    const others = this.interventions.filter((x) => x.id !== i.id);
    const st = maintStatus(it.el, it.type, [...others, i], today(), this.ctx.maint);
    const bytes = await interventionPdf(this.ctx.model!, it.el, it.type, i, st, it.type.etancheite ? fluidInfo(it.el, this.ctx.maint) : null, this.ctx.settings);
    await this.ctx.exportFile(`intervention_${slug(it.el.name)}_${i.date}.pdf`, bytes, 'application/pdf', "Rapport d'intervention");
  }
}
