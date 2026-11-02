import { LOTS, LOT_BY_ID } from '../../core/lots';
import { ifcFr, predefFr } from '../../core/ifcTypesFr';
import { fmt, slug, today } from '../../core/format';
import { ductDesignation, pipeDesignation, segmentLength } from '../../core/metre';
import type { El, LotId, PropValue, TreeNode } from '../../core/types';
import { maintTypeOf } from '../../core/maintenance';
import { kvGet, kvSet } from '../../store/db';
import { isElectron, electron } from '../../platform/platform';
import { Viewer, type CameraState, type ViewName } from '../../viewer/viewer';
import type { App } from '../app';
import type { Page } from '../ctx';
import { confirmBox, el, esc, promptBox, toast } from '../dom';
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

/** Point de vue enregistré : caméra, coupes, lots visibles, isolement, transparence. */
export interface Viewpoint {
  id: string;
  name: string;
  date: string;
  thumb: string;
  camera: CameraState;
  cut: { levelIdx: number; levelH: number; free: { axis: 'x' | 'y' | 'z'; t: number; flip: boolean } | null };
  lots: Record<string, boolean>;
  ghost: boolean;
  visibility: { hidden: number[]; isolated: number[] | null };
}

type LeftTab = 'tree' | 'lots' | 'views';

export class ViewerPage implements Page {
  el = el('section', { class: 'viewer-page' });
  private viewer: Viewer | null = null;
  private left: HTMLElement;
  private right: HTMLElement;
  private leftBody: HTMLElement;
  private rightBody: HTMLElement;
  private rightTitle: HTMLElement;
  private leftTab: LeftTab = 'tree';
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
  private search = '';
  private status: HTMLElement;
  private tooltip: HTMLElement;
  private ctxMenu: HTMLElement | null = null;
  private measure: number | null = null;
  private planMode = false;
  private viewpoints: Viewpoint[] = [];
  private labels: HTMLElement;

  constructor(private app: App) {
    const host = el('div', { class: 'viewer-host' });
    this.el.appendChild(host);
    try {
      this.viewer = new Viewer(host);
      app.setViewer(this.viewer);
      this.viewer.hoverEnabled = matchMedia('(pointer: fine)').matches;
      this.viewer.events.onSelect = (id, additive) => this.onSelect(id, false, additive);
      this.viewer.events.onMeasure = (d) => {
        this.measure = d;
        this.updateStatus();
      };
      this.viewer.events.onContextMenu = (id, x, y) => this.openContextMenu(id, x, y);
      this.viewer.events.onHover = (id, x, y) => this.showTooltip(id, x, y);
      this.viewer.events.onCamera = () => {
        this.updateStatus();
        this.positionLabels();
      };
      const cubeHost = el('div', { class: 'navcube-host' });
      this.el.appendChild(cubeHost);
      this.viewer.attachNavCube(cubeHost);
    } catch (e) {
      console.error('WebGL indisponible', e);
      host.innerHTML = '';
      host.appendChild(this.noWebGlBox());
    }

    // panneau gauche
    this.left = el('div', { class: 'panel left' });
    const lh = el('div', { class: 'panel-head' });
    const seg = el('div', { class: 'seg' }, `<button data-t="tree" class="active">Arborescence</button><button data-t="lots">Lots</button><button data-t="views">Vues</button>`);
    seg.querySelectorAll('button').forEach((b) => (b.onclick = () => this.setLeftTab(b.dataset.t as LeftTab)));
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
    const lt = el('button', { class: 'panel-toggle left', title: 'Arborescence, lots et vues', 'aria-label': 'Arborescence, lots et vues' }, icon('tree'));
    lt.onclick = () => this.togglePanel('left');
    const rt = el('button', { class: 'panel-toggle right', title: 'Propriétés', 'aria-label': 'Propriétés' }, icon('info'));
    rt.onclick = () => this.togglePanel('right');
    this.status = el('div', { class: 'statusbar', role: 'status' });
    this.tooltip = el('div', { class: 'hover-tip', hidden: true });
    this.labels = el('div', { class: 'room-labels', hidden: true });
    this.el.append(this.labels, lt, rt, this.left, this.right, this.status, this.tooltip);
    if (innerWidth < 820) this.left.classList.add('collapsed');
    if (this.viewer) this.buildToolbar();
    this.syncToggles();
    for (const l of LOTS) this.lotState[l.id] = l.visible;
    document.addEventListener('pointerdown', (e) => {
      if (this.ctxMenu && !this.ctxMenu.contains(e.target as Node)) this.closeContextMenu();
    });
  }

  get has3d(): boolean {
    return !!this.viewer;
  }

  private noWebGlBox(): HTMLElement {
    const box = el('div', { class: 'nowebgl' });
    box.innerHTML = `<div class="card"><h2>${icon('alert')} Affichage 3D indisponible</h2>
      <p>La carte graphique ou son pilote ne permet pas l'affichage 3D (WebGL). Les autres modules (métré, équipements, déperditions, maintenance, défis) fonctionnent normalement, ainsi que l'arborescence et les propriétés.</p>
      ${isElectron ? `<p>Bimys peut utiliser un rendu 3D logiciel, plus lent mais compatible avec tous les PC.</p><button class="btn primary" data-a="soft">${icon('refresh')} Relancer avec le rendu 3D logiciel</button>` : '<p>Essayez de mettre à jour le pilote graphique ou d’activer l’accélération matérielle du navigateur.</p>'}</div>`;
    const b = box.querySelector<HTMLButtonElement>('[data-a=soft]');
    if (b) b.onclick = () => electron()?.setSoftwareRendering(true);
    return box;
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
    this.el.classList.toggle('left-open', !this.left.classList.contains('collapsed'));
    this.el.classList.toggle('right-open', !this.right.classList.contains('collapsed'));
  }

  private setLeftTab(t: LeftTab) {
    this.leftTab = t;
    this.left.querySelectorAll('.seg button').forEach((b) => b.classList.toggle('active', (b as HTMLElement).dataset.t === t));
    this.togglePanel('left', true);
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
    btn('iso', 'iso', 'Iso', 'Vue isométrique', () => this.setView('iso'));
    btn('dessus', 'top', 'Dessus', 'Vue de dessus', () => this.setView('dessus'));
    btn('face', 'front', 'Face', 'Vue de face (sud)', () => this.setView('face'));
    btn('fit', 'frame', 'Cadrer', 'Cadrer (F)', () => this.fit());
    btn('ortho', 'ortho', 'Ortho', 'Vue orthographique / perspective (O)', () => this.toggleProjection());
    btn('plan', 'plan', 'Plan 2D', 'Plan 2D du niveau (P)', () => this.togglePlan());
    sep();
    btn('cut', 'scissors', 'Coupe', 'Plans de coupe', () => this.togglePopover());
    btn('measure', 'tape', 'Mesure', 'Mesurer une distance, aimantée sur les sommets (M)', () => this.toggleMeasure());
    sep();
    btn('isolate', 'isolate', 'Isoler', 'Isoler la sélection (I)', () => this.isolateSelection());
    btn('hide', 'eyeOff', 'Masquer', 'Masquer la sélection (H)', () => this.hideSelection());
    btn('all', 'showAll', 'Tout', 'Tout afficher (A)', () => this.showAll());
    sep();
    btn('ghost', 'ghost', 'Archi', 'Architecture en transparence (T)', () => this.setGhost(!this.archiGhost));
    btn('colors', 'palette', 'Couleurs', 'Couleurs par lot ou couleurs IFC', () => {
      const s = { ...this.app.settings, couleurs: this.app.settings.couleurs === 'lot' ? ('ifc' as const) : ('lot' as const) };
      void this.app.saveSettings(s);
      this.viewer?.setColorMode(s.couleurs);
      this.tb.colors.classList.toggle('on', s.couleurs === 'lot');
      this.renderLeft();
    });
    btn('markers', 'marker', 'Repères', 'Repères maintenance (en retard / en cours)', () => {
      this.markersOn = !this.markersOn;
      this.viewer?.setMarkersVisible(this.markersOn);
      this.tb.markers.classList.toggle('on', this.markersOn);
    });
    btn('shot', 'camera', 'Capture', 'Capture d’écran PNG (Ctrl+Maj+S)', () => void this.screenshot());
    this.el.appendChild(bar);
  }

  setView(v: ViewName) {
    if (this.planMode && v !== 'dessus') this.exitPlan();
    this.viewer?.setView(v);
  }

  toggleProjection() {
    if (!this.viewer) return;
    this.viewer.setProjection(this.viewer.projection === 'perspective' ? 'orthographic' : 'perspective');
    this.tb.ortho.classList.toggle('on', this.viewer.projection === 'orthographic');
  }

  /** Plan 2D : vue de dessus orthographique avec coupe à 1,30 m au-dessus du niveau. */
  togglePlan() {
    const m = this.app.model;
    if (!this.viewer || !m) return;
    if (this.planMode) return this.exitPlan();
    if (!m.data.storeys.length) return toast('Aucun niveau dans cette maquette.', { error: true });
    if (this.levelIdx < 0) this.levelIdx = 0;
    this.levelH = 1.3;
    this.planMode = true;
    this.applyCut('level');
    this.viewer.setProjection('orthographic');
    this.viewer.setView('dessus');
    this.viewer.setArchiTransparent(false);
    this.viewer.setPlanStyle(true, (ids) => {
      let w = 0;
      for (const id of ids) if (/^ifcwall/i.test(m.byId.get(id)?.cls ?? '')) w++;
      return w > ids.length / 2;
    });
    this.buildLabels();
    this.tb.plan.classList.add('on');
    this.tb.ortho.classList.add('on');
    this.tb.cut.classList.add('on');
    toast(`Plan 2D : ${m.data.storeys[this.levelIdx].name}. Changez de niveau dans « Coupe » ou avec Page préc. / Page suiv.`);
    this.updateStatus();
  }

  private exitPlan() {
    if (!this.viewer) return;
    this.planMode = false;
    this.levelIdx = -1;
    this.viewer.setPlanStyle(false);
    this.viewer.setArchiTransparent(this.archiGhost);
    this.labels.hidden = true;
    this.applyCut('level');
    this.viewer.setProjection('perspective');
    this.viewer.setView('iso');
    this.tb.plan.classList.remove('on');
    this.tb.ortho.classList.remove('on');
    this.tb.cut.classList.toggle('on', !!this.free);
    this.updateStatus();
  }

  /** niveau suivant / précédent en mode plan ou coupe */
  stepLevel(d: number) {
    const m = this.app.model;
    if (!m || this.levelIdx < 0) return;
    this.levelIdx = Math.max(0, Math.min(m.data.storeys.length - 1, this.levelIdx + d));
    this.applyCut('level');
    if (this.planMode) this.buildLabels();
    if (this.pop) (this.pop.querySelector('[data-k=level]') as HTMLSelectElement).value = String(this.levelIdx);
    this.updateStatus();
  }

  private applyCut(changed: string) {
    const m = this.app.model;
    if (!this.viewer || !m) return;
    if (this.levelIdx >= 0 && m.data.storeys[this.levelIdx]) {
      const y = m.data.storeys[this.levelIdx].elevation + m.yOffset;
      this.viewer.setLevelCut({ bottom: y - 0.25, top: y + this.levelH });
      if (changed === 'level') {
        const b = this.viewer.bounds;
        b.min.y = Math.max(b.min.y, y - 0.25);
        b.max.y = Math.min(b.max.y, y + this.levelH);
        this.viewer.fitBox(b);
      }
    } else this.viewer.setLevelCut(null);
    this.viewer.setFreeCut(this.free);
    this.tb.cut?.classList.toggle('on', this.levelIdx >= 0 || !!this.free);
  }

  /** étiquettes des pièces du niveau affiché en plan : nom et surface */
  private buildLabels() {
    const m = this.app.model;
    this.labels.innerHTML = '';
    if (!m || !this.planMode || this.levelIdx < 0) return;
    const st = m.data.storeys[this.levelIdx];
    const spaces = m.spaces().filter((x) => x.storeyId === st.id && x.bbox);
    // préfixe commun (ex. « Logement 02 ») affiché en petit pour alléger l'étiquette
    const pref = new Map<string, number>();
    for (const sp of spaces) {
      const w = sp.name.split(/\s+/);
      if (w.length >= 3) pref.set(w.slice(0, 2).join(' '), (pref.get(w.slice(0, 2).join(' ')) ?? 0) + 1);
    }
    for (const sp of spaces.sort((a, b) => this.areaOf(b) - this.areaOf(a))) {
      const a = this.areaOf(sp);
      const w = sp.name.split(/\s+/);
      const p2 = w.slice(0, 2).join(' ');
      const short = w.length >= 3 && (pref.get(p2) ?? 0) >= 3;
      const title = short ? w.slice(2).join(' ') : sp.name;
      const d = el('div', { class: 'room-label', 'data-id': sp.id, title: sp.name }, `<b>${esc(title)}</b><span>${short ? esc(p2) + ' · ' : ''}${a ? `${fmt(a, 2)} m²` : ''}</span>`);
      d.onclick = () => this.selectElement(sp.id, false);
      this.labels.appendChild(d);
    }
    this.labels.hidden = false;
    this.positionLabels();
    requestAnimationFrame(() => this.positionLabels());
  }

  private areaOf(sp: El): number {
    return Object.values(sp.qtos).find((q) => typeof q.NetFloorArea === 'number')?.NetFloorArea ?? 0;
  }

  /** place les étiquettes et masque celles qui se chevauchent (les grandes pièces d'abord) */
  private positionLabels() {
    const m = this.app.model;
    if (!m || !this.viewer || this.labels.hidden) return;
    const placed: DOMRect[] = [];
    for (const d of Array.from(this.labels.children) as HTMLElement[]) {
      const b = m.byId.get(Number(d.dataset.id))?.bbox;
      if (!b) continue;
      const p = this.viewer.projectIfc((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, b[2]);
      if (!p) {
        d.hidden = true;
        continue;
      }
      d.hidden = false;
      d.style.left = `${p.x}px`;
      d.style.top = `${p.y}px`;
      const r = d.getBoundingClientRect();
      // une étiquette plus large que la pièce à l'écran ou qui en chevauche une autre est masquée
      const q1 = this.viewer.projectIfc(b[0], b[1], b[2]);
      const q2 = this.viewer.projectIfc(b[3], b[4], b[2]);
      const roomW = q1 && q2 ? Math.abs(q2.x - q1.x) : Infinity;
      const overlap = placed.some((o) => !(r.right < o.left + 2 || r.left > o.right - 2 || r.bottom < o.top + 2 || r.top > o.bottom - 2));
      if (overlap || r.width > roomW * 1.15) d.hidden = true;
      else placed.push(r);
    }
  }

  private togglePopover() {
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
    const apply = (k = '') => {
      this.levelIdx = Number(q('level').value);
      this.levelH = Number(q('h').value);
      q('hv').textContent = `${fmt(this.levelH, 1)} m`;
      const ax = q('axis').value as '' | 'x' | 'y' | 'z';
      this.free = ax ? { axis: ax, t: Number(q('t').value), flip: this.free?.flip ?? false } : null;
      this.applyCut(k);
      this.updateStatus();
    };
    ['level', 'h', 'axis', 't'].forEach((k) => q(k).addEventListener('input', () => apply(k)));
    q('flip').onclick = () => {
      if (this.free) this.free.flip = !this.free.flip;
      apply();
    };
    q('reset').onclick = () => {
      q('level').value = '-1';
      q('axis').value = '';
      if (this.planMode) this.exitPlan();
      apply();
    };
    q('close').onclick = () => this.togglePopover();
    this.el.appendChild(p);
    this.pop = p;
    this.tb.cut.classList.add('on');
  }

  toggleMeasure() {
    if (!this.viewer) return;
    const on = !this.viewer.measuring;
    this.viewer.setMeasuring(on);
    this.tb.measure.classList.toggle('on', on);
    if (on) toast('Mesure : cliquez deux points. Le curseur s’aimante sur les sommets proches.');
  }

  escape() {
    if (this.ctxMenu) this.closeContextMenu();
    else if (this.viewer?.measuring) this.toggleMeasure();
    else if (this.pop) this.togglePopover();
    else this.selectElement(null, false);
  }

  fit() {
    this.viewer?.fit();
  }

  setGhost(on: boolean) {
    this.archiGhost = on;
    this.viewer?.setArchiTransparent(on);
    this.tb.ghost?.classList.toggle('on', on);
  }

  hideSelection() {
    const ids = this.viewer?.selectionIds ?? [];
    if (ids.length) this.viewer!.hide(ids);
    this.onSelect(this.viewer?.selection ?? null, true);
    this.updateStatus();
  }

  isolateSelection() {
    if (!this.viewer) return;
    const sel = this.viewer.selectionIds;
    if (!sel.length) return toast('Sélectionnez d’abord un ou plusieurs objets (Ctrl+clic pour en ajouter).');
    const ids = sel.flatMap((id) => this.withChildren(id));
    this.viewer.isolate(ids);
    this.viewer.fitIds(ids);
    this.updateStatus();
  }

  showAll() {
    this.viewer?.showAll();
    this.updateStatus();
  }

  /** éléments d'un nœud spatial (niveau, pièce) pour isoler un ensemble */
  private withChildren(id: number): number[] {
    const m = this.app.model!;
    const e = m.byId.get(id);
    if (e?.cls.toLowerCase() === 'ifcspace') return [id, ...m.elements.filter((x) => x.spaceId === id).map((x) => x.id)];
    if (m.storeyById.has(id)) return m.elements.filter((x) => x.storeyId === id).map((x) => x.id);
    return [id];
  }

  async screenshot() {
    const m = this.app.model;
    if (!this.viewer || !m) return;
    const src = this.viewer.screenshot();
    // cartouche : nom du fichier, établissement, date
    const img = new Image();
    await new Promise((r) => {
      img.onload = r;
      img.src = src;
    });
    const c = document.createElement('canvas');
    c.width = img.width;
    c.height = img.height + 56;
    const g = c.getContext('2d')!;
    g.drawImage(img, 0, 0);
    g.fillStyle = '#0f4c5c';
    g.fillRect(0, img.height, c.width, 56);
    g.fillStyle = '#f28c28';
    g.fillRect(0, img.height, c.width, 4);
    g.fillStyle = '#ffffff';
    g.font = 'bold 20px Segoe UI, Arial, sans-serif';
    g.fillText(`${m.data.projectName || m.data.fileName}`, 16, img.height + 34);
    g.font = '15px Segoe UI, Arial, sans-serif';
    const right = `${this.app.settings.etablissement}  ·  ${today().split('-').reverse().join('/')}  ·  Bimys`;
    g.fillText(right, c.width - g.measureText(right).width - 16, img.height + 34);
    const bytes = Uint8Array.from(atob(c.toDataURL('image/png').split(',')[1]), (ch) => ch.charCodeAt(0));
    await this.app.exportFile(`capture_${slug(m.data.fileName.replace(/\.ifc$/i, ''))}_${today()}.png`, bytes, 'image/png', 'Capture 3D');
  }

  // ------------------------------------------------------------ cycle de vie
  async modelChanged() {
    const m = this.app.model;
    this.treeRows.clear();
    this.treeParents.clear();
    this.expanded.clear();
    this.search = '';
    if (this.pop) {
      this.pop.remove();
      this.pop = null;
    }
    this.levelIdx = -1;
    this.free = null;
    this.planMode = false;
    this.labels.hidden = true;
    this.viewer?.setPlanStyle(false);
    this.closeContextMenu();
    if (this.viewer) {
      this.viewer.setLevelCut(null);
      this.viewer.setFreeCut(null);
      this.viewer.setMeasuring(false);
      this.viewer.setProjection('perspective');
      for (const k of ['cut', 'measure', 'plan', 'ortho']) this.tb[k]?.classList.remove('on');
    }
    if (!m || !this.app.buckets.length) return;
    for (const l of LOTS) this.lotState[l.id] = l.visible;
    if (this.viewer) {
      this.viewer.setColorMode(this.app.settings.couleurs);
      this.viewer.setArchiTransparent(this.archiGhost);
      this.viewer.load(this.app.buckets);
      this.viewer.setLotVisibility(this.lotState);
      this.tb.colors.classList.toggle('on', this.app.settings.couleurs === 'lot');
      this.tb.markers.classList.toggle('on', this.markersOn);
    }
    this.app.buckets = [];
    const walk = (n: TreeNode, path: TreeNode[]) => {
      if (n.id >= 0) this.treeParents.set(n.id, path);
      for (const c of n.children) walk(c, [...path, n]);
    };
    if (m.data.tree) {
      walk(m.data.tree, []);
      this.expanded.add(m.data.tree);
      for (const b of m.data.tree.children) this.expanded.add(b);
    }
    this.viewpoints = await kvGet<Viewpoint[]>(`vues|${m.fileKey}`, []);
    this.renderLeft();
    this.onSelect(null, false);
    this.updateStatus();
  }

  show() {
    this.viewer?.resize();
  }

  // ------------------------------------------------------------ barre d'état et info-bulle
  updateStatus() {
    const m = this.app.model;
    if (!m) {
      this.status.textContent = '';
      return;
    }
    const v = this.viewer;
    const parts: string[] = [`${m.elements.length} objets`];
    if (v) {
      const sel = v.selectionIds;
      if (sel.length === 1) parts.push(`Sélection : ${m.byId.get(sel[0])?.name || ifcFr(m.byId.get(sel[0])?.cls ?? '')}`);
      else if (sel.length > 1) parts.push(`${sel.length} objets sélectionnés`);
      if (v.isIsolating) parts.push('Affichage filtré');
      parts.push(v.projection === 'orthographic' ? 'Orthographique' : 'Perspective');
      if (this.planMode && this.levelIdx >= 0) parts.push(`Plan ${m.data.storeys[this.levelIdx]?.name ?? ''}`);
      else if (this.levelIdx >= 0) parts.push(`Coupe ${m.data.storeys[this.levelIdx]?.name ?? ''}`);
      if (this.measure !== null) parts.push(`Mesure ${fmt(this.measure, 3)} m`);
    } else parts.push('3D indisponible');
    this.status.innerHTML = parts.map((p) => `<span>${esc(p)}</span>`).join('');
  }

  private showTooltip(id: number | null, x: number, y: number) {
    const e = id !== null ? this.app.model?.byId.get(id) : undefined;
    if (!e || this.ctxMenu) {
      this.tooltip.hidden = true;
      return;
    }
    const r = this.el.getBoundingClientRect();
    this.tooltip.innerHTML = `<b>${esc(e.name || ifcFr(e.cls))}</b><span>${esc(ifcFr(e.cls))}${e.systemIds.length ? ' · ' + esc(this.app.model!.systemNames(e)[0]) : ''}</span>`;
    this.tooltip.style.left = `${x - r.left + 14}px`;
    this.tooltip.style.top = `${y - r.top + 14}px`;
    this.tooltip.hidden = false;
  }

  // ------------------------------------------------------------ menu contextuel
  private openContextMenu(id: number | null, x: number, y: number) {
    this.closeContextMenu();
    this.tooltip.hidden = true;
    const m = this.app.model;
    if (!m || !this.viewer) return;
    if (id !== null && !this.viewer.selectionIds.includes(id)) this.selectElement(id, false);
    const e = id !== null ? m.byId.get(id) : undefined;
    const menu = el('div', { class: 'ctxmenu', role: 'menu' });
    const item = (ic: string, label: string, run: () => void, kbd = '', disabled = false) => {
      const b = el('button', { role: 'menuitem', disabled }, `${icon(ic)}<span>${esc(label)}</span>${kbd ? `<span class="kbd">${esc(kbd)}</span>` : ''}`);
      b.onclick = () => {
        this.closeContextMenu();
        run();
      };
      menu.appendChild(b);
    };
    const sepr = () => menu.appendChild(el('div', { class: 'ctxsep' }));
    if (e) {
      menu.appendChild(el('div', { class: 'ctxhead' }, `${esc(e.name || ifcFr(e.cls))}<small>${esc(ifcFr(e.cls))}</small>`));
      item('frame', 'Cadrer', () => this.fit(), 'F');
      item('isolate', 'Isoler', () => this.isolateSelection(), 'I');
      item('eyeOff', 'Masquer', () => this.hideSelection(), 'H');
      item('layers', `Masquer tous les « ${ifcFr(e.cls)} »`, () => {
        this.viewer!.hide(m.elements.filter((x) => x.cls === e.cls).map((x) => x.id));
        this.updateStatus();
      });
      item('isolate', `Isoler le lot ${LOT_BY_ID[e.lot].label}`, () => this.isolateLot(e.lot));
      if (e.systemIds.length) {
        const sid = e.systemIds[0];
        item('isolate', `Isoler le réseau « ${m.systemById.get(sid)?.name} »`, () => {
          const ids = m.systemById.get(sid)!.members;
          this.viewer!.isolate(ids);
          this.viewer!.fitIds(ids);
          this.updateStatus();
        });
      }
      sepr();
      item('info', 'Propriétés', () => this.togglePanel('right', true));
      if (maintTypeOf(e, this.app.maint)) item('wrench', 'Fiche maintenance', () => this.openMaintenance(e));
      item('list', 'Copier le GlobalId', () => {
        void navigator.clipboard?.writeText(e.gid).then(() => toast(`GlobalId copié : ${e.gid}`));
      });
      sepr();
    }
    item('showAll', 'Tout afficher', () => this.showAll(), 'A');
    item('ghost', this.archiGhost ? 'Architecture opaque' : 'Architecture en transparence', () => this.setGhost(!this.archiGhost), 'T');
    item('camera', 'Capture d’écran', () => void this.screenshot());
    const r = this.el.getBoundingClientRect();
    menu.style.left = `${Math.min(x - r.left, r.width - 270)}px`;
    menu.style.top = `${Math.min(y - r.top, r.height - 40 - menu.childElementCount * 34)}px`;
    this.el.appendChild(menu);
    this.ctxMenu = menu;
  }

  private closeContextMenu() {
    this.ctxMenu?.remove();
    this.ctxMenu = null;
  }

  private openMaintenance(e: El) {
    this.app.go('maintenance');
    document.dispatchEvent(new CustomEvent('bimys:maint', { detail: e.gid }));
  }

  // ------------------------------------------------------------ panneau gauche
  private renderLeft() {
    const m = this.app.model;
    this.leftBody.innerHTML = '';
    if (!m) return;
    if (this.leftTab === 'lots') return this.renderLots();
    if (this.leftTab === 'views') return this.renderViews();
    this.treeRows.clear();
    const sb = el('div', { class: 'searchbox' });
    sb.innerHTML = `${icon('search')}<input type="search" placeholder="Rechercher : nom, type, GlobalId…" value="${esc(this.search)}" aria-label="Rechercher un objet">`;
    const input = sb.querySelector('input')!;
    const results = el('div');
    input.oninput = () => {
      this.search = input.value;
      this.renderSearch(results);
    };
    this.leftBody.append(sb, results);
    this.renderSearch(results);
  }

  focusSearch() {
    this.setLeftTab('tree');
    this.leftBody.querySelector<HTMLInputElement>('.searchbox input')?.focus();
  }

  private renderSearch(host: HTMLElement) {
    const m = this.app.model!;
    host.innerHTML = '';
    const q = this.search.trim().toLowerCase();
    if (!q) {
      const root = el('div', { class: 'tree' });
      const ul = el('ul');
      if (m.data.tree) ul.appendChild(this.treeItem(m.data.tree));
      root.appendChild(ul);
      host.appendChild(root);
      const sel = this.viewer?.selectionIds ?? [];
      for (const id of sel) this.treeRows.get(id)?.classList.add('sel');
      return;
    }
    const words = q.split(/\s+/);
    const found = m.elements.filter((e) => {
      const hay = `${e.name} ${ifcFr(e.cls)} ${e.cls} ${e.objectType} ${e.typeName} ${e.gid} ${m.systemNames(e).join(' ')}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    });
    const head = el('div', { class: 'search-head' }, `<span>${found.length} résultat${found.length > 1 ? 's' : ''}</span>`);
    if (found.length && this.viewer) {
      const iso = el('button', { class: 'btn small' }, `${icon('isolate')} Isoler`);
      iso.onclick = () => {
        const ids = found.map((e) => e.id);
        this.viewer!.isolate(ids);
        this.viewer!.setSelection(ids.filter((id) => this.viewer!.hasGeometry(id)));
        this.viewer!.fitIds(ids);
        this.updateStatus();
      };
      head.appendChild(iso);
    }
    host.appendChild(head);
    const list = el('div', { class: 'tree' });
    for (const e of found.slice(0, 300)) {
      const row = el('div', { class: 'tnode' }, `<span class="dot" style="background:${LOT_BY_ID[e.lot].color}"></span><span class="lbl">${esc(e.name || ifcFr(e.cls))}</span><span class="typ">${esc(ifcFr(e.cls))}</span>`);
      row.onclick = (ev) => this.selectElement(e.id, !ev.ctrlKey, false, ev.ctrlKey || ev.metaKey);
      this.treeRows.set(e.id, row);
      list.appendChild(row);
    }
    if (found.length > 300) list.appendChild(el('div', { class: 'lead', style: { padding: '6px' } }, 'Affinez la recherche pour voir les autres résultats.'));
    host.appendChild(list);
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
    row.onclick = (ev) => {
      if (n.id < 0) return toggle();
      this.selectElement(n.id, false, false, ev.ctrlKey || ev.metaKey);
      if (has && !this.expanded.has(n) && !ev.ctrlKey) toggle();
    };
    row.ondblclick = () => {
      if (n.id >= 0) {
        this.selectElement(n.id, false);
        const ids = this.withChildren(n.id);
        this.viewer?.fitIds(ids.length ? ids : [n.id]);
      }
    };
    if (n.id >= 0) {
      row.oncontextmenu = (ev) => {
        ev.preventDefault();
        this.openContextMenu(n.id, ev.clientX, ev.clientY);
      };
      this.treeRows.set(n.id, row);
    }
    li.appendChild(row);
    if (has) {
      if (open) fill();
      else childUl.hidden = true;
      li.appendChild(childUl);
    }
    return li;
  }

  private revealInTree(id: number) {
    if (this.search) return;
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
        this.viewer?.setLotVisible(l.id, this.lotState[l.id]);
      };
      const iso = el('button', { class: 'x-btn', title: `Isoler le lot ${l.label}` }, icon('isolate'));
      iso.onclick = () => this.isolateLot(l.id);
      row.append(iso, sw);
      wrap.appendChild(row);
    }
    const sysTitle = el('h4', { class: 'panel-sub' }, 'Réseaux (IfcSystem)');
    wrap.appendChild(sysTitle);
    for (const s of m.data.systems) {
      const row = el('div', { class: 'lot-row' }, `<span class="sw" style="background:${LOT_BY_ID[s.lot].color}"></span><span class="nm">${esc(s.name)}</span><span class="cnt">${s.members.length}</span>`);
      const iso = el('button', { class: 'x-btn', title: `Isoler le réseau ${s.name}` }, icon('isolate'));
      iso.onclick = () => {
        this.viewer?.isolate(s.members);
        this.viewer?.fitIds(s.members);
        this.updateStatus();
      };
      row.appendChild(iso);
      wrap.appendChild(row);
    }
    const acts = el('div', { class: 'toolbar', style: { marginTop: '10px' } });
    const all = el('button', { class: 'btn small' }, `${icon('showAll')} Tout afficher`);
    all.onclick = () => {
      for (const l of LOTS) this.lotState[l.id] = l.id !== 'espaces';
      this.viewer?.setLotVisibility(this.lotState);
      this.viewer?.showAll();
      this.renderLeft();
      this.updateStatus();
    };
    const ghost = el('label', { class: 'inline' }, `<input type="checkbox" ${this.archiGhost ? 'checked' : ''}> Architecture en transparence`);
    ghost.querySelector('input')!.onchange = (ev) => this.setGhost((ev.target as HTMLInputElement).checked);
    acts.append(all, ghost);
    wrap.appendChild(acts);
    wrap.appendChild(el('p', { class: 'lead', style: { fontSize: '12.5px' } }, "Le lot d'un objet vient de son système IFC (IfcSystem), sinon de sa classe. Les équipements (générateurs, circulateurs, ballons, vases, caisson VMC) forment un lot à part pour les repérer facilement."));
    this.leftBody.appendChild(wrap);
  }

  private isolateLot(lot: LotId) {
    for (const l of LOTS) this.lotState[l.id] = l.id === lot || (l.id === 'archi' && this.archiGhost);
    this.viewer?.setLotVisibility(this.lotState);
    this.renderLeft();
    this.viewer?.fit();
  }

  // ------------------------------------------------------------ points de vue
  private renderViews() {
    const wrap = el('div');
    const add = el('button', { class: 'btn primary small', disabled: !this.viewer }, `${icon('plus')} Enregistrer la vue actuelle`);
    add.onclick = () => void this.saveViewpoint();
    wrap.appendChild(add);
    wrap.appendChild(el('p', { class: 'lead', style: { fontSize: '12.5px', margin: '8px 0' } }, 'Une vue mémorise la caméra, les coupes, les lots affichés, les objets isolés et la transparence. Pratique pour préparer un cours.'));
    if (!this.viewpoints.length) wrap.appendChild(el('div', { class: 'empty' }, 'Aucune vue enregistrée pour cette maquette.'));
    for (const vp of this.viewpoints) {
      const row = el('div', { class: 'vp-item' });
      row.innerHTML = `<img src="${vp.thumb}" alt=""><div class="vp-nm"><b>${esc(vp.name)}</b><small>${esc(vp.date.split('-').reverse().join('/'))}</small></div>`;
      const del = el('button', { class: 'x-btn', title: 'Supprimer la vue' }, icon('trash'));
      del.onclick = async (ev) => {
        ev.stopPropagation();
        if (!(await confirmBox('Supprimer la vue', `Supprimer « ${vp.name} » ?`, 'Supprimer'))) return;
        this.viewpoints = this.viewpoints.filter((x) => x.id !== vp.id);
        await kvSet(`vues|${this.app.model!.fileKey}`, this.viewpoints);
        this.renderLeft();
      };
      row.appendChild(del);
      row.onclick = () => this.restoreViewpoint(vp);
      wrap.appendChild(row);
    }
    this.leftBody.appendChild(wrap);
  }

  private async saveViewpoint() {
    const m = this.app.model;
    if (!this.viewer || !m) return;
    const name = await promptBox('Enregistrer la vue', 'Nom de la vue', 'text', `Vue ${this.viewpoints.length + 1}`);
    if (!name) return;
    const full = this.viewer.screenshot();
    const img = new Image();
    await new Promise((r) => {
      img.onload = r;
      img.src = full;
    });
    const c = document.createElement('canvas');
    c.width = 160;
    c.height = Math.round((160 * img.height) / img.width);
    c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height);
    const vp: Viewpoint = {
      id: `${Date.now()}`,
      name,
      date: today(),
      thumb: c.toDataURL('image/jpeg', 0.7),
      camera: this.viewer.getCameraState(),
      cut: { levelIdx: this.levelIdx, levelH: this.levelH, free: this.free },
      lots: { ...this.lotState },
      ghost: this.archiGhost,
      visibility: this.viewer.visibilityState,
    };
    this.viewpoints.push(vp);
    await kvSet(`vues|${m.fileKey}`, this.viewpoints);
    this.renderLeft();
    toast(`Vue « ${name} » enregistrée.`);
  }

  private restoreViewpoint(vp: Viewpoint) {
    if (!this.viewer) return;
    this.lotState = { ...vp.lots };
    this.viewer.setLotVisibility(this.lotState);
    this.setGhost(vp.ghost);
    this.viewer.setVisibilityState(vp.visibility);
    this.levelIdx = vp.cut.levelIdx;
    this.levelH = vp.cut.levelH;
    this.free = vp.cut.free;
    this.applyCut('');
    this.viewer.setCameraState(vp.camera);
    this.tb.ortho.classList.toggle('on', vp.camera.projection === 'orthographic');
    this.updateStatus();
  }

  // ------------------------------------------------------------ sélection et propriétés
  selectElement(id: number | null, fit: boolean, isolate = false, additive = false) {
    this.viewer?.select(id, false, additive);
    const e = id !== null ? this.app.model?.byId.get(id) : undefined;
    if (fit && e && e.lot !== 'archi' && !this.archiGhost) this.setGhost(true);
    this.onSelect(this.viewer ? this.viewer.selection : id, true, additive);
    if (id !== null && isolate) this.viewer?.isolate(this.withChildren(id));
    if (id !== null && fit && this.viewer) {
      if (this.viewer.hasGeometry(id)) this.viewer.fit();
      else this.viewer.fitIds(this.withChildren(id));
    }
  }

  private onSelect(id: number | null, fromUi: boolean, _additive = false) {
    for (const r of this.treeRows.values()) r.classList.remove('sel');
    const sel = this.viewer ? this.viewer.selectionIds : id !== null ? [id] : [];
    for (const s of sel) this.treeRows.get(s)?.classList.add('sel');
    this.updateStatus();
    if (id === null) {
      this.renderProps(null);
      return;
    }
    if (!fromUi) this.revealInTree(id);
    this.renderProps(id);
    if (innerWidth >= 820 || !fromUi) this.togglePanel('right', true);
  }

  private renderProps(id: number | null) {
    const m = this.app.model;
    this.rightBody.innerHTML = '';
    if (!m || id === null) {
      this.rightTitle.textContent = 'Propriétés';
      this.rightBody.innerHTML = `<div class="empty">Touchez un objet dans la vue 3D ou dans l'arborescence.<br><small>Ctrl+clic pour sélectionner plusieurs objets, clic droit pour le menu.</small></div>`;
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
          this.viewer?.isolate(ids);
          this.viewer?.fitIds(ids);
        };
        this.rightBody.appendChild(b);
      }
      return;
    }
    const nsel = this.viewer?.selectionIds.length ?? 1;
    this.rightTitle.textContent = nsel > 1 ? `${nsel} objets sélectionnés` : ifcFr(e.cls);
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
    if (maintTypeOf(e, this.app.maint)) mk('wrench', 'Maintenance', () => this.openMaintenance(e));
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
      if (inside.length) this.rightBody.appendChild(this.psetBox(`Contenu de la pièce (${inside.length})`, inside.map((x) => [ifcFr(x.cls), x.name]), false));
    }
    const copy = el('button', { class: 'btn small', style: { marginTop: '4px' } }, `${icon('list')} Copier les propriétés`);
    copy.onclick = () => {
      const lines = [`${e.name}\t${e.cls}\t${e.gid}`, ...general.map(([k, v]) => `${k}\t${v}`)];
      for (const [ps, props] of Object.entries(e.psets)) for (const [k, v] of Object.entries(props)) lines.push(`${ps} / ${k}\t${pv(v)}`);
      void navigator.clipboard?.writeText(lines.join('\n')).then(() => toast('Propriétés copiées (collables dans un tableur).'));
    };
    this.rightBody.appendChild(copy);
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
