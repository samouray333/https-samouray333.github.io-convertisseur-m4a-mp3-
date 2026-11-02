import {
  computeRoom,
  DEFAULT_PARAMS,
  emitterInfos,
  PAROI_TYPES,
  roomInputFromModel,
  VERDICT_LABEL,
  type Bilan,
  type DepParams,
  type Paroi,
  type RoomInput,
  type RoomResult,
} from '../../core/deperditions';
import { fmt, parseNum, slug } from '../../core/format';
import type { El } from '../../core/types';
import { clearRooms, deleteRoom, getRooms, kvGet, kvSet, saveRoom } from '../../store/db';
import type { Ctx, Page } from '../ctx';
import { confirmBox, debounce, el, esc, toast } from '../dom';
import { icon } from '../icons';

const VCLS: Record<string, string> = { sous: 'err', correct: 'ok', sur: 'warn', aucun: 'err', non_chauffe: 'mute', negligeable: 'mute' };

export class DeperditionsPage implements Page {
  el = el('section');
  private params: DepParams = { ...DEFAULT_PARAMS };
  private inputs = new Map<string, RoomInput>();
  private modified = new Set<string>();
  private spaces: El[] = [];
  private open = new Set<string>();
  private paramBox: HTMLElement;
  private kpis: HTMLElement;
  private list: HTMLElement;
  private loaded = false;
  private saveParams = debounce(() => this.ctx.model && kvSet(`dep|${this.ctx.model.fileKey}`, this.params), 400);

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'page-inner' });
    inner.innerHTML = `
      <h1>${icon('thermo')} Déperditions par pièce</h1>
      <p class="lead">Parois pré-remplies depuis la maquette (limites d'espaces, coefficients U). Complétez ou corrigez les valeurs : le verdict sur les émetteurs se met à jour immédiatement.</p>`;
    this.paramBox = el('div', { class: 'card' });
    this.kpis = el('div', { class: 'kpis' });
    const tb = el('div', { class: 'toolbar' });
    tb.innerHTML = `<button class="btn" data-k="expand">${icon('list')} Tout déplier</button><button class="btn" data-k="reset">${icon('refresh')} Réinitialiser les saisies</button><span class="spacer"></span><button class="btn primary" data-k="pdf">${icon('pdf')} Export PDF du bilan</button>`;
    this.list = el('div', { class: 'room-list' });
    inner.append(this.paramBox, this.kpis, tb, this.list);
    this.el.appendChild(inner);
    tb.querySelector<HTMLButtonElement>('[data-k=pdf]')!.onclick = () => this.pdf();
    tb.querySelector<HTMLButtonElement>('[data-k=reset]')!.onclick = () => this.resetAll();
    tb.querySelector<HTMLButtonElement>('[data-k=expand]')!.onclick = () => {
      if (this.open.size === this.spaces.length) this.open.clear();
      else this.spaces.forEach((s) => this.open.add(s.gid));
      this.renderRooms();
    };
  }

  modelChanged() {
    this.loaded = false;
  }

  async show() {
    if (!this.ctx.model) return;
    if (!this.loaded) await this.load();
  }

  private async load() {
    const m = this.ctx.model!;
    const s = this.ctx.settings;
    this.params = { ...DEFAULT_PARAMS, te: s.te, pontsPct: s.pontsPct, seuilSous: s.seuilSous, seuilSur: s.seuilSur, ...(await kvGet<Partial<DepParams>>(`dep|${m.fileKey}`, {})) };
    const saved = await getRooms(m.fileKey);
    this.spaces = m.spaces().sort((a, b) => {
      const sa = a.storeyId !== null ? m.storeyById.get(a.storeyId)?.elevation ?? 0 : 0;
      const sb = b.storeyId !== null ? m.storeyById.get(b.storeyId)?.elevation ?? 0 : 0;
      return sa - sb || a.name.localeCompare(b.name, 'fr', { numeric: true });
    });
    this.inputs.clear();
    this.modified.clear();
    for (const sp of this.spaces) {
      if (saved[sp.gid]) {
        this.inputs.set(sp.gid, saved[sp.gid]);
        this.modified.add(sp.gid);
      } else this.inputs.set(sp.gid, roomInputFromModel(m, sp));
    }
    this.loaded = true;
    this.renderParams();
    this.renderRooms();
  }

  private results(): RoomResult[] {
    const m = this.ctx.model!;
    return this.spaces.map((sp) => computeRoom(this.inputs.get(sp.gid)!, this.params, emitterInfos(m, sp)));
  }

  private bilan(): Bilan {
    const rooms = this.results();
    const heated = rooms.filter((r) => r.input.heated);
    return {
      rooms,
      totalPhi: heated.reduce((s, r) => s + r.phiTotal, 0),
      totalEmis: heated.reduce((s, r) => s + r.pEmis, 0),
      surfaceChauffee: heated.reduce((s, r) => s + r.input.area, 0),
      volumeChauffe: heated.reduce((s, r) => s + r.input.volume, 0),
    };
  }

  // ------------------------------------------------------------ paramètres
  private renderParams() {
    const p = this.params;
    this.paramBox.innerHTML = `
      <h2>${icon('gear')} Hypothèses de calcul</h2>
      <div class="grid">
        <label class="field">Température extérieure de base (°C)<input type="text" inputmode="decimal" data-k="te" value="${fmt(p.te, 1).replace(/,0$/, '')}"></label>
        <label class="field">Méthode<select data-k="method"><option value="parois">Par parois (U × S × ΔT)</option><option value="volumique">Volumique (G × V × ΔT)</option></select></label>
        <label class="field" data-show="parois">Ponts thermiques forfaitaires (+ % parois)<input type="text" inputmode="decimal" data-k="pontsPct" value="${fmt(p.pontsPct, 1).replace(/,0$/, '')}"></label>
        <label class="field" data-show="volumique">Coefficient G (W/m³.K)<input type="text" inputmode="decimal" data-k="g" value="${fmt(p.g, 2)}"></label>
        <label class="field">Seuil sous-dimensionné (%)<input type="text" inputmode="decimal" data-k="seuilSous" value="${fmt(p.seuilSous, 0)}"></label>
        <label class="field">Seuil surdimensionné (%)<input type="text" inputmode="decimal" data-k="seuilSur" value="${fmt(p.seuilSur, 0)}"></label>
      </div>
      <div class="toolbar" style="margin:12px 0 0">
        <label class="inline"><input type="checkbox" data-k="correctionRegime" ${p.correctionRegime ? 'checked' : ''}> Corriger la puissance des émetteurs selon le régime d'eau</label>
        <label class="inline" data-show="regime">Départ <input type="text" class="num" inputmode="decimal" data-k="tDepart" value="${fmt(p.tDepart, 0)}" style="width:60px"> °C</label>
        <label class="inline" data-show="regime">Retour <input type="text" class="num" inputmode="decimal" data-k="tRetour" value="${fmt(p.tRetour, 0)}" style="width:60px"> °C</label>
        <label class="inline" data-show="regime">n <input type="text" class="num" inputmode="decimal" data-k="nExp" value="${fmt(p.nExp, 2)}" style="width:60px"></label>
      </div>
      <div class="formula" data-k="formula"></div>`;
    const sel = this.paramBox.querySelector<HTMLSelectElement>('[data-k=method]')!;
    sel.value = p.method;
    const sync = () => {
      this.paramBox.querySelectorAll<HTMLElement>('[data-show]').forEach((x) => {
        const k = x.dataset.show!;
        x.hidden = k === 'regime' ? !this.params.correctionRegime : k !== this.params.method;
      });
      const f = this.paramBox.querySelector<HTMLElement>('[data-k=formula]')!;
      f.innerHTML =
        this.params.method === 'parois'
          ? `Φ = Σ(U × S × b × ΔT) × (1 + ${fmt(this.params.pontsPct, 0)} %) + 0,34 × Qv × ΔT &nbsp;avec ΔT = Ti − (${fmt(this.params.te, 1).replace(/,0$/, '')} °C)`
          : `Φ = G × V × ΔT = ${fmt(this.params.g, 2)} × V × (Ti − (${fmt(this.params.te, 1).replace(/,0$/, '')} °C))`;
      if (this.params.correctionRegime) {
        const tm = (this.params.tDepart + this.params.tRetour) / 2;
        f.innerHTML += `<br>P réelle = P nominale × ((Tm − Ti) / 50)<sup>n</sup>, Tm = ${fmt(tm, 1)} °C (pour Ti = 20 °C : × ${fmt(Math.pow(Math.max(0, tm - 20) / 50, this.params.nExp), 3)})`;
      }
    };
    this.paramBox.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-k]').forEach((inp) => {
      const k = inp.dataset.k as keyof DepParams;
      if (!k || k === ('formula' as any)) return;
      inp.addEventListener(inp.tagName === 'SELECT' || (inp as HTMLInputElement).type === 'checkbox' ? 'change' : 'input', () => {
        if (k === 'method') this.params.method = (inp as HTMLSelectElement).value as any;
        else if (k === 'correctionRegime') this.params.correctionRegime = (inp as HTMLInputElement).checked;
        else {
          const v = parseNum(inp.value);
          if (v === null) return;
          (this.params as any)[k] = v;
        }
        sync();
        this.saveParams();
        this.renderRooms();
      });
    });
    sync();
  }

  // ------------------------------------------------------------ pièces
  private renderRooms() {
    const b = this.bilan();
    this.kpis.innerHTML = `
      <div class="kpi"><div class="l">Déperditions (pièces chauffées)</div><div class="v">${fmt(b.totalPhi, 0)} <small>W</small></div></div>
      <div class="kpi"><div class="l">Émetteurs installés</div><div class="v">${fmt(b.totalEmis, 0)} <small>W</small></div></div>
      <div class="kpi"><div class="l">Surface chauffée</div><div class="v">${fmt(b.surfaceChauffee, 1)} <small>m²</small></div></div>
      <div class="kpi"><div class="l">Ratio</div><div class="v">${fmt(b.surfaceChauffee ? b.totalPhi / b.surfaceChauffee : 0, 1)} <small>W/m²</small></div></div>`;
    this.list.innerHTML = '';
    for (const r of b.rooms) this.list.appendChild(this.roomCard(r));
  }

  private roomCard(r: RoomResult): HTMLElement {
    const gid = r.input.spaceGid;
    const card = el('div', { class: 'room', 'data-gid': gid });
    const head = el('div', { class: 'room-head' });
    const ratio = r.phiTotal > 0 ? Math.min(1.6, r.pEmis / r.phiTotal) : 0;
    const gcol = r.verdict === 'correct' ? 'var(--ok)' : r.verdict === 'sur' ? 'var(--warn)' : r.verdict === 'non_chauffe' || r.verdict === 'negligeable' ? 'var(--muted)' : 'var(--err)';
    head.innerHTML = `
      <span class="car" style="display:inline-flex;transform:rotate(${this.open.has(gid) ? 90 : 0}deg);transition:.15s">${icon('chevronR')}</span>
      <div class="nm">${esc(r.input.name)}<small>${esc(r.input.storey)}${this.modified.has(gid) ? ' · modifiée' : ''}${r.manquants ? ` · <span style="color:var(--err)">${r.manquants} valeur(s) à saisir</span>` : ''}</small></div>
      <div class="val">Φ <b>${fmt(r.phiTotal, 0)} W</b></div>
      <div class="val">Émetteurs <b>${fmt(r.pEmis, 0)} W</b></div>
      <div class="gauge" title="Puissance installée / déperditions"><i style="width:${(ratio / 1.6) * 100}%;background:${gcol}"></i><i style="left:${(1 / 1.6) * 100}%;width:2px;background:var(--text);opacity:.5"></i></div>
      <span class="pill ${VCLS[r.verdict]}">${VERDICT_LABEL[r.verdict]}${r.ecartPct !== null && r.verdict !== 'non_chauffe' ? ` ${r.ecartPct > 0 ? '+' : ''}${fmt(r.ecartPct, 0)} %` : ''}</span>`;
    head.onclick = () => {
      if (this.open.has(gid)) this.open.delete(gid);
      else this.open.add(gid);
      this.renderRooms();
    };
    card.appendChild(head);
    if (this.open.has(gid)) card.appendChild(this.roomBody(r));
    return card;
  }

  private persist(gid: string) {
    const inp = this.inputs.get(gid)!;
    this.modified.add(gid);
    void saveRoom(this.ctx.model!.fileKey, inp);
  }

  private roomBody(r: RoomResult): HTMLElement {
    const gid = r.input.spaceGid;
    const inp = this.inputs.get(gid)!;
    const body = el('div', { class: 'room-body' });
    const top = el('div', { class: 'toolbar' });
    top.innerHTML = `
      <label class="inline"><input type="checkbox" data-f="heated" ${inp.heated ? 'checked' : ''}> Pièce chauffée</label>
      <label class="inline">Ti <input type="text" class="num" inputmode="decimal" data-f="ti" value="${fmt(inp.ti, 1).replace(/,0$/, '')}" style="width:62px"> °C</label>
      <label class="inline">Qv air neuf <input type="text" class="num" inputmode="decimal" data-f="qv" value="${fmt(inp.qv, 1).replace(/,0$/, '')}" style="width:70px"> m³/h</label>
      <label class="inline">S <input type="text" class="num" inputmode="decimal" data-f="area" value="${fmt(inp.area, 2)}" style="width:76px"> m²</label>
      <label class="inline">V <input type="text" class="num" inputmode="decimal" data-f="volume" value="${fmt(inp.volume, 2)}" style="width:80px"> m³</label>
      <span class="spacer"></span>
      ${this.modified.has(gid) ? `<button class="btn small" data-a="revert">${icon('refresh')} Valeurs de la maquette</button>` : ''}
      <button class="btn small" data-a="see">${icon('cube')} Voir en 3D</button>`;
    body.appendChild(top);
    const recompute = () => {
      this.persist(gid);
      this.refreshHead(gid);
    };
    top.querySelectorAll<HTMLInputElement>('[data-f]').forEach((x) => {
      const f = x.dataset.f as 'heated' | 'ti' | 'qv' | 'area' | 'volume';
      x.addEventListener(x.type === 'checkbox' ? 'change' : 'input', () => {
        if (f === 'heated') inp.heated = x.checked;
        else {
          const v = parseNum(x.value);
          x.classList.toggle('missing', v === null);
          if (v === null) return;
          inp[f] = v;
        }
        recompute();
      });
    });
    top.querySelector<HTMLButtonElement>('[data-a=see]')!.onclick = () => {
      const sp = this.spaces.find((s) => s.gid === gid);
      if (sp) this.ctx.showElement(sp.id, true);
    };
    const rv = top.querySelector<HTMLButtonElement>('[data-a=revert]');
    if (rv)
      rv.onclick = async () => {
        const sp = this.spaces.find((s) => s.gid === gid)!;
        this.inputs.set(gid, roomInputFromModel(this.ctx.model!, sp));
        this.modified.delete(gid);
        await deleteRoom(this.ctx.model!.fileKey, gid);
        this.renderRooms();
      };

    if (this.params.method === 'parois') {
      const wrap = el('div', { class: 'table-wrap' });
      const t = el('table', { class: 'data' });
      t.innerHTML = `<thead><tr><th>Paroi</th><th>Type</th><th class="n">S (m²)</th><th class="n">U (W/m².K)</th><th class="n">b</th><th class="n">U.S.b</th><th class="n">Φ (W)</th><th></th></tr></thead>`;
      const tb = el('tbody');
      inp.parois.forEach((w, i) => tb.appendChild(this.paroiRow(gid, w, i, r.dT)));
      t.appendChild(tb);
      wrap.appendChild(t);
      body.appendChild(wrap);
      const add = el('button', { class: 'btn small', style: { marginTop: '8px' } }, `${icon('plus')} Ajouter une paroi`);
      add.onclick = () => {
        inp.parois.push({ id: `s${Date.now()}`, label: 'Nouvelle paroi', type: 'Mur', area: null, u: null, tau: 1, source: 'saisie' });
        this.persist(gid);
        this.renderRooms();
      };
      body.appendChild(add);
      if (!inp.parois.length) body.appendChild(el('p', { class: 'lead' }, "La maquette ne fournit pas les parois de cette pièce : ajoutez-les (surface et coefficient U)."));
    }
    body.appendChild(el('div', { class: 'formula', 'data-formula': gid }, this.formula(r)));
    const em = el('div', { style: { marginTop: '10px' } });
    em.innerHTML = r.emetteurs.length
      ? `<b>Émetteurs dans la pièce :</b> ${r.emetteurs.map((e) => `<a href="#" data-eid="${e.id}">${esc(e.name)}</a> (${fmt(e.pNom, 0)} W nominal${this.params.correctionRegime ? `, ${fmt(e.pCorr, 0)} W au régime` : ''})`).join(', ')}`
      : '<b>Aucun émetteur</b> dans cette pièce.';
    em.querySelectorAll<HTMLAnchorElement>('[data-eid]').forEach((a) => {
      a.onclick = (ev) => {
        ev.preventDefault();
        this.ctx.showElement(Number(a.dataset.eid));
      };
    });
    body.appendChild(em);
    return body;
  }

  private paroiRow(gid: string, w: Paroi, i: number, dT: number): HTMLTableRowElement {
    const inp = this.inputs.get(gid)!;
    const tr = el('tr');
    const usb = w.area !== null && w.u !== null ? w.u * w.area * w.tau : null;
    tr.innerHTML = `
      <td><input type="text" data-p="label" value="${esc(w.label)}" style="width:100%;min-width:130px"></td>
      <td><select data-p="type">${PAROI_TYPES.map((t) => `<option ${t === w.type ? 'selected' : ''}>${t}</option>`).join('')}</select></td>
      <td class="n"><input type="text" inputmode="decimal" class="num ${w.area === null ? 'missing' : ''}" data-p="area" value="${w.area === null ? '' : fmt(w.area, 2)}" placeholder="à saisir"></td>
      <td class="n"><input type="text" inputmode="decimal" class="num ${w.u === null ? 'missing' : ''}" data-p="u" value="${w.u === null ? '' : fmt(w.u, 2)}" placeholder="à saisir"></td>
      <td class="n"><input type="text" inputmode="decimal" class="num" data-p="tau" value="${fmt(w.tau, 2)}" style="width:62px"></td>
      <td class="n" data-o="usb">${usb === null ? '' : fmt(usb, 2)}</td>
      <td class="n" data-o="phi">${usb === null ? '' : fmt(usb * dT, 0)}</td>
      <td><button class="x-btn" title="Supprimer la paroi" aria-label="Supprimer">${icon('trash')}</button></td>`;
    tr.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-p]').forEach((x) => {
      const k = x.dataset.p as keyof Paroi;
      x.addEventListener(x.tagName === 'SELECT' ? 'change' : 'input', () => {
        if (k === 'label') w.label = x.value;
        else if (k === 'type') w.type = x.value as any;
        else {
          const v = parseNum(x.value);
          x.classList.toggle('missing', v === null && k !== 'tau');
          if (k === 'tau') {
            if (v === null) return;
            w.tau = v;
          } else (w as any)[k] = v;
        }
        w.source = 'saisie';
        this.persist(gid);
        const res = this.refreshHead(gid);
        const u2 = w.area !== null && w.u !== null ? w.u * w.area * w.tau : null;
        tr.querySelector('[data-o=usb]')!.textContent = u2 === null ? '' : fmt(u2, 2);
        tr.querySelector('[data-o=phi]')!.textContent = u2 === null || !res ? '' : fmt(u2 * res.dT, 0);
      });
    });
    tr.querySelector<HTMLButtonElement>('.x-btn')!.onclick = () => {
      inp.parois.splice(i, 1);
      this.persist(gid);
      this.renderRooms();
    };
    return tr;
  }

  /** met à jour l'en-tête et la formule d'une pièce sans reconstruire les champs (garde le focus) */
  private refreshHead(gid: string): RoomResult | null {
    const sp = this.spaces.find((s) => s.gid === gid);
    if (!sp) return null;
    const r = computeRoom(this.inputs.get(gid)!, this.params, emitterInfos(this.ctx.model!, sp));
    const card = this.list.querySelector<HTMLElement>(`.room[data-gid="${CSS.escape(gid)}"]`);
    if (card) {
      const fresh = this.roomCard(r);
      card.replaceChild(fresh.querySelector('.room-head')!, card.querySelector('.room-head')!);
      const f = card.querySelector<HTMLElement>('[data-formula]');
      if (f) f.innerHTML = this.formula(r);
    }
    const b = this.bilan();
    const v = this.kpis.querySelectorAll('.kpi .v');
    if (v.length === 4) {
      v[0].innerHTML = `${fmt(b.totalPhi, 0)} <small>W</small>`;
      v[1].innerHTML = `${fmt(b.totalEmis, 0)} <small>W</small>`;
      v[2].innerHTML = `${fmt(b.surfaceChauffee, 1)} <small>m²</small>`;
      v[3].innerHTML = `${fmt(b.surfaceChauffee ? b.totalPhi / b.surfaceChauffee : 0, 1)} <small>W/m²</small>`;
    }
    return r;
  }

  private formula(r: RoomResult): string {
    const p = this.params;
    if (!r.input.heated) return 'Pièce non chauffée : déperditions indicatives, pas de verdict.' + (p.method === 'parois' ? ` Φ = ${fmt(r.phiTotal, 0)} W.` : '');
    let s = `ΔT = ${fmt(r.input.ti, 1).replace(/,0$/, '')} − (${fmt(p.te, 1).replace(/,0$/, '')}) = ${fmt(r.dT, 1).replace(/,0$/, '')} K<br>`;
    if (p.method === 'parois') {
      s += `Φ parois = Σ U.S.b × ΔT = ${fmt(r.ubs, 3)} × ${fmt(r.dT, 1).replace(/,0$/, '')} = ${fmt(r.phiParois, 1)} W<br>`;
      s += `Φ ponts thermiques = ${fmt(p.pontsPct, 0)} % × ${fmt(r.phiParois, 1)} = ${fmt(r.phiPonts, 1)} W<br>`;
      s += `Φ ventilation = 0,34 × ${fmt(r.input.qv, 1).replace(/,0$/, '')} × ${fmt(r.dT, 1).replace(/,0$/, '')} = ${fmt(r.phiVent, 1)} W<br>`;
    } else {
      s += `Φ = G × V × ΔT = ${fmt(p.g, 2)} × ${fmt(r.input.volume, 2)} × ${fmt(r.dT, 1).replace(/,0$/, '')}<br>`;
    }
    s += `<b>Φ total = ${fmt(r.phiTotal, 1)} W</b> ; émetteurs ${fmt(r.pEmis, 0)} W`;
    if (r.ecartPct !== null) s += ` ; écart (P − Φ) / Φ = <b>${r.ecartPct > 0 ? '+' : ''}${fmt(r.ecartPct, 1)} %</b> → ${VERDICT_LABEL[r.verdict]}`;
    if (r.manquants) s += `<br><span style="color:var(--err)">${r.manquants} paroi(s) incomplète(s) non comptée(s).</span>`;
    return s;
  }

  private async resetAll() {
    if (!(await confirmBox('Réinitialiser', 'Effacer toutes les saisies de cette maquette et revenir aux valeurs du fichier IFC ?', 'Réinitialiser'))) return;
    await clearRooms(this.ctx.model!.fileKey);
    this.loaded = false;
    await this.load();
    toast('Saisies réinitialisées.');
  }

  private async pdf() {
    const { deperditionsPdf } = await import('../../pdf/reports');
    const bytes = await deperditionsPdf(this.ctx.model!, this.bilan(), this.params, this.ctx.settings);
    await this.ctx.exportFile(`deperditions_${slug(this.ctx.model!.data.fileName.replace(/\.ifc$/i, ''))}.pdf`, bytes, 'application/pdf', 'Bilan des déperditions');
  }
}
