import { LOTS, LOT_BY_ID } from '../../core/lots';
import { ifcFr, predefFr } from '../../core/ifcTypesFr';
import { fmt } from '../../core/format';
import { ductDesignation, pipeDesignation, segmentLength } from '../../core/metre';
import type { El, LotId, PropValue, TreeNode } from '../../core/types';
import { maintTypeOf } from '../../core/maintenance';
import { Viewer, type ViewName } from '../../viewer/viewer';
import type { App } from '../app';
import type { Page } from '../ctx';
import { el, esc } from '../dom';
import { icon } from '../icons';

function pv(v: PropValue): string {
  if (v === null) return '';
  if (typeof v === 'boolean') return v ? 'Oui' : 'Non';
  if (typeof v === 'number') {
    const a = Math.abs(v);
    return fmt(v, Number.isInteger(v) ? 0 : a < 0.1 ? 4 : a < 10 ? 3 : 2).replace(/(,\d*?)0+$/, '$1').replace(/,$/, '');
  }
  return String(v);
}

export class ViewerPage implements Page {
  el = el('section', { class: 'viewer-page' });
  private viewer: Viewer;
  private left: HTMLElement;
  private right: HTMLElement;
  private leftBody: HTMLElement;
  private rightBody: HTMLElement;
  private rightTitle: HTMLElement;
  private leftTab: 'tree' | 'lots' = 'tree';
  private lotState: Record<string, boolean> = {};
  private archiGhost = false;
  private treeRows = new Map<number, HTMLElement>();
  private treeParents = new Map<number, TreeNode[]>();
  private expanded = new Set<TreeNode>();
  private tb: Record<string, HTMLButtonElement> = {};
  private pop: HTMLElement | null = null;
  private levelIdx = -1;
  private levelH = 1.3;
  private free: { axis: 'x' | 'y' | 'z'; t: number; flip: boolean } | null = null;
  private markersOn = true;

  constructor(private app: App) {
    const host = el('div', { class: 'viewer-host' });
    this.el.appendChild(host);
    this.viewer = new Viewer(host);
    app.setViewer(this.viewer);
    this.viewer.events.onSelect = (id) => this.onSelect(id, false);

    // panneau gauche
    this.left = el('div', { class: 'panel left' });
    const lh = el('div', { class: 'panel-head' });
    const seg = el('div', { class: 'seg' }, `<button data-t="tree" class="active">Arborescence</button><button data-t="lots">Lots</button>`);
    seg.querySelectorAll('button').forEach((b) => (b.onclick = () => this.setLeftTab(b.dataset.t as any)));
    const lclose = el('button', { class: 'x-btn', title: 'Replier', 'aria-label': 'Replier' }, icon('close'));
    lclose.onclick = () => this.togglePanel('left', false);
    lh.append(seg, lclose);
    this.leftBody = el('div', { class: 'panel-body' });
    this.left.append(lh, this.leftBody);
    // panneau droit
    this.right = el('div', { class: 'panel right collapsed' });
    const rh = el('div', { class: 'panel-head' });
    this.rightTitle = el('h3', {}, 'Propriétés');
    const rclose = el('button', { class: 'x-btn', title: 'Replier', 'aria-label': 'Replier' }, icon('close'));
    rclose.onclick = () => this.togglePanel('right', false);
    rh.append(this.rightTitle, rclose);
    this.rightBody = el('div', { class: 'panel-body' });
    this.right.append(rh, this.rightBody);
    const lt = el('button', { class: 'panel-toggle left', title: 'Arborescence et lots', 'aria-label': 'Arborescence et lots' }, icon('tree'));
    lt.onclick = () => this.togglePanel('left');
    const rt = el('button', { class: 'panel-toggle right', title: 'Propriétés', 'aria-label': 'Propriétés' }, icon('info'));
    rt.onclick = () => this.togglePanel('right');
    this.el.append(lt, rt, this.left, this.right);
    if (innerWidth < 820) this.left.classList.add('collapsed');
    this.buildToolbar();
    this.syncToggles();
    for (const l of LOTS) this.lotState[l.id] = l.visible;
  }

  private togglePanel(side: 'left' | 'right', open?: boolean) {
    const p = side === 'left' ? this.left : this.right;
    const willOpen = open ?? p.classList.contains('collapsed');
    p.classList.toggle('collapsed', !willOpen);
    if (willOpen && innerWidth < 820) (side === 'left' ? this.right : this.left).classList.add('collapsed');
    this.syncToggles();
  }

  private syncToggles() {
    this.el.querySelector<HTMLElement>('.panel-toggle.left')!.hidden = !this.left.classList.contains('collapsed');
    this.el.querySelector<HTMLElement>('.panel-toggle.right')!.hidden = !this.right.classList.contains('collapsed');
  }

  private setLeftTab(t: 'tree' | 'lots') {
    this.leftTab = t;
    this.left.querySelectorAll('.seg button').forEach((b) => b.classList.toggle('active', (b as HTMLElement).dataset.t === t));
    this.renderLeft();
  }

  // ------------------------------------------------------------ barre d'outils
  private buildToolbar() {
    const bar = el('div', { class: 'vtoolbar', role: 'toolbar' });
    const btn = (id: string, ic: string, label: string, title: string, run: () => void) => {
      const b = el('button', { class: 'vt', title, 'data-tool': id }, `${icon(ic)}<span>${esc(label)}</span>`) as HTMLButtonElement;
      b.onclick = run;
      this.tb[id] = b;
      bar.appendChild(b);
      return b;
    };
    const sep = () => bar.appendChild(el('div', { class: 'vsep' }));
    btn('iso', 'iso', 'Iso', 'Vue isométrique', () => this.viewer.setView('iso'));
    btn('dessus', 'top', 'Dessus', 'Vue de dessus', () => this.viewer.setView('dessus'));
    btn('face', 'front', 'Face', 'Vue de face', () => this.viewer.setView('face'));
    btn('fit', 'frame', 'Cadrer', 'Cadrer (F)', () => this.fit());
    sep();
    btn('cut', 'scissors', 'Coupe', 'Plans de coupe', () => this.togglePopover('cut'));
    btn('measure', 'tape', 'Mesure', 'Mesurer une distance entre deux points', () => this.toggleMeasure());
    sep();
    btn('isolate', 'isolate', 'Isoler', 'Isoler la sélection (I)', () => this.isolateSelection());
    btn('hide', 'eyeOff', 'Masquer', 'Masquer la sélection (H)', () => this.hideSelection());
    btn('all', 'showAll', 'Tout', 'Tout afficher (A)', () => this.showAll());
    sep();
    btn('ghost', 'ghost', 'Archi', 'Architecture en transparence', () => this.setGhost(!this.archiGhost));
    btn('colors', 'palette', 'Couleurs', 'Couleurs par lot ou couleurs IFC', () => {
      const s = { ...this.app.settings, couleurs: this.app.settings.couleurs === 'lot' ? ('ifc' as const) : ('lot' as const) };
      void this.app.saveSettings(s);
      this.viewer.setColorMode(s.couleurs);
      this.tb.colors.classList.toggle('on', s.couleurs === 'lot');
      this.renderLeft();
    });
    btn('markers', 'marker', 'Repères', 'Repères maintenance (en retard / en cours)', () => {
      this.markersOn = !this.markersOn;
      this.viewer.setMarkersVisible(this.markersOn);
      this.tb.markers.classList.toggle('on', this.markersOn);
    });
    this.el.appendChild(bar);
  }

  private togglePopover(kind: 'cut') {
    if (this.pop) {
      this.pop.remove();
      this.pop = null;
      this.tb.cut.classList.toggle('on', this.levelIdx >= 0 || !!this.free);
      return;
    }
    const m = this.app.model;
    if (!m) return;
    const p = el('div', { class: 'popover' });
    const storeys = m.data.storeys;
    p.innerHTML = `
      <h4>Coupe horizontale par niveau</h4>
      <div class="row"><select data-k="level"><option value="-1">Aucune</option>${storeys.map((s, i) => `<option value="${i}">${esc(s.name)} (${fmt(s.elevation, 2)} m)</option>`).join('')}</select>
      <label class="inline">Hauteur <input type="range" min="0.3" max="3" step="0.1" data-k="h"> <span data-k="hv"></span></label></div>
      <h4>Plan de coupe libre</h4>
      <div class="row"><select data-k="axis"><option value="">Aucun</option><option value="x">Axe X (est/ouest)</option><option value="z">Axe Y (nord/sud)</option><option value="y">Axe Z (vertical)</option></select>
      <button class="btn small" data-k="flip">Inverser</button></div>
      <div class="row"><input type="range" min="0" max="1" step="0.005" data-k="t"></div>
      <div class="row"><button class="btn small" data-k="reset">Supprimer les coupes</button><span class="spacer"></span><button class="btn small primary" data-k="close">Fermer</button></div>`;
    const q = (k: string) => p.querySelector(`[data-k=${k}]`) as HTMLInputElement;
    q('level').value = String(this.levelIdx);
    q('h').value = String(this.levelH);
    q('hv').textContent = `${fmt(this.levelH, 1)} m`;
    q('axis').value = this.free?.axis ?? '';
    q('t').value = String(this.free?.t ?? 0.5);
    const apply = () => {
      this.levelIdx = Number(q('level').value);
      this.levelH = Number(q('h').value);
      q('hv').textContent = `${fmt(this.levelH, 1)} m`;
      if (this.levelIdx >= 0) {
        const s = storeys[this.levelIdx];
        const y = s.elevation + m.yOffset;
        this.viewer.setLevelCut({ bottom: y - 0.25, top: y + this.levelH });
      } else this.viewer.setLevelCut(null);
      const ax = q('axis').value as '' | 'x' | 'y' | 'z';
      this.free = ax ? { axis: ax, t: Number(q('t').value), flip: this.free?.flip ?? false } : null;
      this.viewer.setFreeCut(this.free);
      this.tb.cut.classList.toggle('on', this.levelIdx >= 0 || !!this.free);
    };
    ['level', 'h', 'axis', 't'].forEach((k) => q(k).addEventListener('input', apply));
    q('flip').onclick = () => {
      if (this.free) this.free.flip = !this.free.flip;
      apply();
    };
    q('reset').onclick = () => {
      q('level').value = '-1';
      q('axis').value = '';
      apply();
    };
    q('close').onclick = () => this.togglePopover(kind);
    this.el.appendChild(p);
    this.pop = p;
    this.tb.cut.classList.add('on');
  }

  private toggleMeasure() {
    const on = !this.viewer.measuring;
    this.viewer.setMeasuring(on);
    this.tb.measure.classList.toggle('on', on);
  }

  escape() {
    if (this.viewer.measuring) this.toggleMeasure();
    else if (this.pop) this.togglePopover('cut');
    else this.selectElement(null, false);
  }

  fit() {
    this.viewer.fit();
  }

  hideSelection() {
    const id = this.viewer.selection;
    if (id !== null) this.viewer.hide([id]);
  }

  isolateSelection() {
    const id = this.viewer.selection;
    if (id === null) return;
    const ids = this.withChildren(id);
    this.viewer.isolate(ids);
    this.viewer.fitIds(ids);
  }

  showAll() {
    this.viewer.showAll();
  }

  /** éléments d'un nœud spatial (niveau, pièce) pour isoler un ensemble */
  private withChildren(id: number): number[] {
    const m = this.app.model!;
    const e = m.byId.get(id);
    if (e?.cls.toLowerCase() === 'ifcspace') return [id, ...m.elements.filter((x) => x.spaceId === id).map((x) => x.id)];
    if (m.storeyById.has(id)) return m.elements.filter((x) => x.storeyId === id).map((x) => x.id);
    return [id];
  }

  // ------------------------------------------------------------ cycle de vie
  modelChanged() {
    const m = this.app.model;
    this.treeRows.clear();
    this.treeParents.clear();
    this.expanded.clear();
    if (this.pop) {
      this.pop.remove();
      this.pop = null;
    }
    this.levelIdx = -1;
    this.free = null;
    this.viewer.setLevelCut(null);
    this.viewer.setFreeCut(null);
    this.viewer.setMeasuring(false);
    for (const k of ['cut', 'measure']) this.tb[k]?.classList.remove('on');
    if (!m || !this.app.buckets.length) return;
    for (const l of LOTS) this.lotState[l.id] = l.visible;
    this.viewer.setColorMode(this.app.settings.couleurs);
    this.viewer.setArchiTransparent(this.archiGhost);
    this.viewer.load(this.app.buckets);
    this.app.buckets = [];
    this.viewer.setLotVisibility(this.lotState);
    this.tb.colors.classList.toggle('on', this.app.settings.couleurs === 'lot');
    this.tb.markers.classList.toggle('on', this.markersOn);
    // index des parents pour synchroniser l'arbre
    const walk = (n: TreeNode, path: TreeNode[]) => {
      if (n.id >= 0) this.treeParents.set(n.id, path);
      for (const c of n.children) walk(c, [...path, n]);
    };
    if (m.data.tree) {
      walk(m.data.tree, []);
      this.expanded.add(m.data.tree);
      for (const b of m.data.tree.children) {
        this.expanded.add(b);
      }
    }
    this.renderLeft();
    this.onSelect(null, false);
  }

  show() {
    this.viewer.resize();
  }

  // ------------------------------------------------------------ panneau gauche
  private renderLeft() {
    const m = this.app.model;
    this.leftBody.innerHTML = '';
    if (!m) return;
    if (this.leftTab === 'lots') return this.renderLots();
    this.treeRows.clear();
    const root = el('div', { class: 'tree' });
    const ul = el('ul');
    if (m.data.tree) ul.appendChild(this.treeItem(m.data.tree));
    root.appendChild(ul);
    this.leftBody.appendChild(root);
    const sel = this.viewer.selection;
    if (sel !== null) this.treeRows.get(sel)?.classList.add('sel');
  }

  private treeItem(n: TreeNode): HTMLElement {
    const m = this.app.model!;
    const li = el('li');
    const row = el('div', { class: 'tnode', role: 'treeitem' });
    const has = n.children.length > 0;
    const open = this.expanded.has(n);
    const e = n.id >= 0 ? m.byId.get(n.id) : undefined;
    const dot = e ? `<span class="dot" style="background:${LOT_BY_ID[e.lot].color}"></span>` : '';
    const typ = n.cls === 'group' ? '' : `<span class="typ">${esc(ifcFr(n.cls))}</span>`;
    row.innerHTML = `<span class="car ${open ? 'open' : ''}">${has ? icon('chevronR') : ''}</span>${dot}<span class="lbl">${esc(n.name || ifcFr(n.cls))}</span>${typ}`;
    const car = row.querySelector('.car') as HTMLElement;
    const childUl = el('ul');
    const fill = () => {
      childUl.innerHTML = '';
      for (const c of n.children) childUl.appendChild(this.treeItem(c));
    };
    const toggle = () => {
      if (!has) return;
      if (this.expanded.has(n)) {
        this.expanded.delete(n);
        childUl.hidden = true;
        car.classList.remove('open');
      } else {
        this.expanded.add(n);
        if (!childUl.childElementCount) fill();
        childUl.hidden = false;
        car.classList.add('open');
      }
    };
    car.onclick = (ev) => {
      ev.stopPropagation();
      toggle();
    };
    row.onclick = () => {
      if (n.id < 0) return toggle();
      this.selectElement(n.id, false);
      if (has && !this.expanded.has(n)) toggle();
    };
    row.ondblclick = () => {
      if (n.id >= 0) {
        this.selectElement(n.id, false);
        const ids = this.withChildren(n.id);
        this.viewer.fitIds(ids.length ? ids : [n.id]);
      }
    };
    if (n.id >= 0) this.treeRows.set(n.id, row);
    li.appendChild(row);
    if (has) {
      if (open) fill();
      else childUl.hidden = true;
      li.appendChild(childUl);
    }
    return li;
  }

  private revealInTree(id: number) {
    const path = this.treeParents.get(id);
    if (!path) return;
    let changed = false;
    for (const p of path) if (!this.expanded.has(p)) {
      this.expanded.add(p);
      changed = true;
    }
    if (changed && this.leftTab === 'tree') this.renderLeft();
    const row = this.treeRows.get(id);
    if (row) {
      // défilement du seul panneau (scrollIntoView ferait défiler toute la page 3D)
      const body = this.leftBody;
      const top = row.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop;
      if (top < body.scrollTop || top > body.scrollTop + body.clientHeight - 30) body.scrollTop = top - body.clientHeight / 3;
    }
  }

  private renderLots() {
    const m = this.app.model!;
    const counts: Record<string, number> = {};
    for (const e of m.elements) counts[e.lot] = (counts[e.lot] ?? 0) + 1;
    const wrap = el('div');
    for (const l of LOTS) {
      if (!counts[l.id]) continue;
      const row = el('div', { class: 'lot-row' });
      const col = this.app.settings.couleurs === 'lot' || l.id === 'archi' ? l.color : '#999';
      row.innerHTML = `<span class="sw" style="background:${col}"></span><span class="nm">${esc(l.label)}</span><span class="cnt">${counts[l.id]}</span>`;
      const sw = el('label', { class: 'switch', title: 'Afficher / masquer' }, `<input type="checkbox" ${this.lotState[l.id] ? 'checked' : ''}><span></span>`);
      sw.querySelector('input')!.onchange = (ev) => {
        this.lotState[l.id] = (ev.target as HTMLInputElement).checked;
        this.viewer.setLotVisible(l.id, this.lotState[l.id]);
      };
      const iso = el('button', { class: 'x-btn', title: `Isoler le lot ${l.label}` }, icon('isolate'));
      iso.onclick = () => this.isolateLot(l.id);
      row.append(iso, sw);
      wrap.appendChild(row);
    }
    const acts = el('div', { class: 'toolbar', style: { marginTop: '10px' } });
    const all = el('button', { class: 'btn small' }, `${icon('showAll')} Tout afficher`);
    all.onclick = () => {
      for (const l of LOTS) this.lotState[l.id] = l.id !== 'espaces';
      this.viewer.setLotVisibility(this.lotState);
      this.viewer.showAll();
      this.renderLeft();
    };
    const ghost = el('label', { class: 'inline' }, `<input type="checkbox" ${this.archiGhost ? 'checked' : ''}> Architecture en transparence`);
    ghost.querySelector('input')!.onchange = (ev) => {
      this.archiGhost = (ev.target as HTMLInputElement).checked;
      this.viewer.setArchiTransparent(this.archiGhost);
      this.tb.ghost.classList.toggle('on', this.archiGhost);
    };
    acts.append(all, ghost);
    wrap.appendChild(acts);
    wrap.appendChild(el('p', { class: 'lead', style: { fontSize: '12.5px' } }, "Le lot d'un objet vient de son système IFC (IfcSystem), sinon de sa classe. Les équipements (générateurs, circulateurs, ballons, vases, caisson VMC) forment un lot à part pour les repérer facilement."));
    this.leftBody.appendChild(wrap);
  }

  private isolateLot(lot: LotId) {
    for (const l of LOTS) this.lotState[l.id] = l.id === lot || (l.id === 'archi' && this.archiGhost);
    this.viewer.setLotVisibility(this.lotState);
    this.renderLeft();
    this.viewer.fit();
  }

  // ------------------------------------------------------------ sélection et propriétés
  setGhost(on: boolean) {
    this.archiGhost = on;
    this.viewer.setArchiTransparent(on);
    this.tb.ghost?.classList.toggle('on', on);
  }

  selectElement(id: number | null, fit: boolean, isolate = false) {
    this.viewer.select(id);
    // un équipement est souvent caché par les murs ou les dalles : passage en transparence
    const e = id !== null ? this.app.model?.byId.get(id) : undefined;
    if (fit && e && e.lot !== 'archi' && !this.archiGhost) this.setGhost(true);
    this.onSelect(id, true);
    if (id !== null && isolate) this.viewer.isolate(this.withChildren(id));
    if (id !== null && fit) {
      if (this.viewer.hasGeometry(id)) this.viewer.fit();
      else this.viewer.fitIds(this.withChildren(id));
    }
  }

  private onSelect(id: number | null, fromUi: boolean) {
    for (const r of this.treeRows.values()) r.classList.remove('sel');
    if (id === null) {
      this.renderProps(null);
      return;
    }
    if (!fromUi) this.revealInTree(id);
    this.treeRows.get(id)?.classList.add('sel');
    this.renderProps(id);
    if (innerWidth >= 820 || !fromUi) this.togglePanel('right', true);
  }

  private renderProps(id: number | null) {
    const m = this.app.model;
    this.rightBody.innerHTML = '';
    if (!m || id === null) {
      this.rightTitle.textContent = 'Propriétés';
      this.rightBody.innerHTML = `<div class="empty">Touchez un objet dans la vue 3D ou dans l'arborescence.</div>`;
      return;
    }
    const e = m.byId.get(id);
    if (!e) {
      const st = m.storeyById.get(id);
      this.rightTitle.textContent = st ? 'Niveau' : 'Propriétés';
      this.rightBody.innerHTML = st
        ? `<div class="prop-head"><div class="t">Niveau</div><div class="n">${esc(st.name)}</div><div class="g">${esc(st.gid)}</div></div><p>Altitude : ${fmt(st.elevation, 2)} m</p><p>${m.elements.filter((x) => x.storeyId === id).length} objets.</p>`
        : '';
      if (st) {
        const b = el('button', { class: 'btn small' }, `${icon('isolate')} Isoler le niveau`);
        b.onclick = () => {
          const ids = this.withChildren(id);
          this.viewer.isolate(ids);
          this.viewer.fitIds(ids);
        };
        this.rightBody.appendChild(b);
      }
      return;
    }
    this.rightTitle.textContent = ifcFr(e.cls);
    const head = el('div', { class: 'prop-head' }, `<div class="t">${esc(ifcFr(e.cls))}</div><div class="n">${esc(e.name || '(sans nom)')}</div><div class="g">${esc(e.cls)} · ${esc(e.gid)}</div>`);
    this.rightBody.appendChild(head);
    const acts = el('div', { class: 'toolbar' });
    const mk = (ic: string, lbl: string, run: () => void) => {
      const b = el('button', { class: 'btn small' }, `${icon(ic)} ${esc(lbl)}`);
      b.onclick = run;
      acts.appendChild(b);
    };
    mk('frame', 'Cadrer', () => this.selectElement(id, true));
    mk('isolate', 'Isoler', () => this.isolateSelection());
    mk('eyeOff', 'Masquer', () => this.hideSelection());
    if (maintTypeOf(e, this.app.maint)) mk('wrench', 'Maintenance', () => {
      this.app.go('maintenance');
      document.dispatchEvent(new CustomEvent('bimys:maint', { detail: e.gid }));
    });
    this.rightBody.appendChild(acts);
    const general: [string, string][] = [
      ['Type (français)', ifcFr(e.cls)],
      ['Classe IFC', e.cls],
      ['Type prédéfini', [predefFr(e.predefined), e.predefined && e.predefined !== 'NOTDEFINED' ? `(${e.predefined})` : ''].filter(Boolean).join(' ')],
      ["Type d'objet", e.objectType],
      ['Type associé', e.typeName],
      ['Description', e.desc],
      ['Lot', LOT_BY_ID[e.lot].label],
      ['Système(s)', m.systemNames(e).join(', ') || (e.cls === 'IfcSpace' ? '' : 'Aucun')],
      ['Niveau', e.storeyId !== null ? m.storeyById.get(e.storeyId)?.name ?? '' : ''],
      ['Pièce', e.spaceId !== null ? m.byId.get(e.spaceId)?.name ?? '' : ''],
      ['Matériau(x)', e.materials.join(', ')],
    ];
    if (/segment/i.test(e.cls)) {
      general.push(['Longueur', `${fmt(segmentLength(e), 3)} m`]);
      general.push([/duct/i.test(e.cls) ? 'Section' : 'Diamètre', /duct/i.test(e.cls) ? ductDesignation(e) : pipeDesignation(e)]);
    }
    if (e.bbox) general.push(['Encombrement (x, y, z)', `${fmt(e.bbox[3] - e.bbox[0], 2)} × ${fmt(e.bbox[4] - e.bbox[1], 2)} × ${fmt(e.bbox[5] - e.bbox[2], 2)} m`]);
    this.rightBody.appendChild(this.psetBox('Informations générales', general.filter(([, v]) => v), true));
    const psetNames = Object.keys(e.psets).sort((a, b) => (a === 'Bimys_Equipement' ? -1 : b === 'Bimys_Equipement' ? 1 : a.localeCompare(b)));
    for (const name of psetNames) {
      const rows = Object.entries(e.psets[name]).map(([k, v]) => [k, pv(v)] as [string, string]);
      this.rightBody.appendChild(this.psetBox(name === 'Bimys_Equipement' ? 'Caractéristiques (Bimys_Equipement)' : name, rows, name === 'Bimys_Equipement' || psetNames.length <= 2));
    }
    for (const [name, q] of Object.entries(e.qtos)) {
      const rows = Object.entries(q).map(([k, v]) => [k, `${pv(v)} ${unitOf(k)}`.trim()] as [string, string]);
      this.rightBody.appendChild(this.psetBox(`Quantités : ${name}`, rows, true));
    }
    if (e.cls === 'IfcSpace') {
      const inside = m.elements.filter((x) => x.spaceId === e.id);
      if (inside.length) {
        const box = this.psetBox(`Contenu de la pièce (${inside.length})`, inside.map((x) => [ifcFr(x.cls), x.name]), false);
        this.rightBody.appendChild(box);
      }
    }
  }

  private psetBox(title: string, rows: [string, string][], open: boolean): HTMLElement {
    const d = el('details', { class: 'pset' });
    if (open) d.open = true;
    d.innerHTML = `<summary>${esc(title)}</summary><table>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>`;
    return d;
  }
}

function unitOf(k: string): string {
  if (/area/i.test(k)) return 'm²';
  if (/volume/i.test(k)) return 'm³';
  if (/length|height|width|perimeter|depth|thickness/i.test(k)) return 'm';
  return '';
}

export type { El, ViewName };
