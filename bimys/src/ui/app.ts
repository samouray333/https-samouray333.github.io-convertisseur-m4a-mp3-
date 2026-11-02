// Coque de l'application : en-tête, navigation, chargement des maquettes, raccourcis.
import { Model, type GeoBucket, type ModelData } from '../core/types';
import { DEFAULT_MAINT, type MaintConfig } from '../core/maintenance';
import { addRecent, getMaintOverride, getSettings, saveSettings as dbSaveSettings, type Settings } from '../store/db';
import { canShare, electron, initialFile, isElectron, onExternalFile, pickIfc, saveFile, shareFile } from '../platform/platform';
import { Viewer } from '../viewer/viewer';
import type { Ctx, Page, PageId } from './ctx';
import { el, esc, Loader, toast } from './dom';
import { icon } from './icons';
import { HomePage } from './pages/home';
import { ViewerPage } from './pages/viewerPage';
import { MetrePage } from './pages/metre';
import { NomenclaturePage } from './pages/nomenclature';
import { DeperditionsPage } from './pages/deperditions';
import { CoherencePage } from './pages/coherence';
import { MaintenancePage } from './pages/maintenance';
import { EnergiePage } from './pages/energie';
import { DefisPage } from './pages/defis';
import { SettingsPage } from './pages/settings';
import logoUrl from '../assets/logo.svg?url';

const TABS: { id: PageId; label: string; icon: string; needModel: boolean }[] = [
  { id: 'viewer', label: 'Vue 3D', icon: 'cube', needModel: true },
  { id: 'metre', label: 'Métré', icon: 'ruler', needModel: true },
  { id: 'nomenclature', label: 'Équipements', icon: 'list', needModel: true },
  { id: 'deperditions', label: 'Déperditions', icon: 'thermo', needModel: true },
  { id: 'coherence', label: 'Cohérence', icon: 'check', needModel: true },
  { id: 'maintenance', label: 'Maintenance', icon: 'wrench', needModel: true },
  { id: 'energie', label: 'Énergie', icon: 'bolt', needModel: false },
  { id: 'defis', label: 'Défis', icon: 'trophy', needModel: true },
];

export const VERSION = __APP_VERSION__;

export class App implements Ctx {
  model: Model | null = null;
  settings!: Settings;
  maint: MaintConfig = DEFAULT_MAINT;
  viewer: Viewer | null = null;
  version = VERSION;
  buckets: GeoBucket[] = [];
  private pages = new Map<PageId, Page>();
  private current: PageId = 'home';
  private main!: HTMLElement;
  private tabs = new Map<PageId, HTMLButtonElement>();
  private fileLabel!: HTMLElement;
  private worker: Worker | null = null;
  private loading = false;

  async start(root: HTMLElement) {
    this.settings = await getSettings();
    const ov = await getMaintOverride();
    if (ov) this.maint = ov;
    this.applyTheme();
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => this.applyTheme());
    root.innerHTML = '';
    const header = el('header', { class: 'top' });
    const brand = el('div', { class: 'brand', title: 'Accueil' }, `<img src="${logoUrl}" alt=""><div>Bimys<small>QMTech</small></div>`);
    brand.onclick = () => this.go('home');
    header.appendChild(brand);
    this.fileLabel = el('div', { class: 'file-name' });
    header.appendChild(this.fileLabel);
    const nav = el('nav', { class: 'tabs', 'aria-label': 'Modules' });
    for (const t of TABS) {
      const b = el('button', { class: 'tab', 'data-page': t.id }, `${icon(t.icon)}<span>${esc(t.label)}</span>`) as HTMLButtonElement;
      b.onclick = () => this.go(t.id);
      this.tabs.set(t.id, b);
      nav.appendChild(b);
    }
    header.appendChild(nav);
    const actions = el('div', { class: 'top-actions' });
    const open = el('button', { class: 'icon-btn primary', title: 'Ouvrir une maquette IFC (Ctrl+O)' }, `${icon('open')}<span class="lbl">Ouvrir</span>`);
    open.onclick = () => this.openFile();
    const set = el('button', { class: 'icon-btn', title: 'Paramètres', 'aria-label': 'Paramètres' }, icon('gear'));
    set.onclick = () => this.go('settings');
    actions.append(open, set);
    header.appendChild(actions);
    root.appendChild(header);
    this.main = el('main');
    root.appendChild(this.main);
    root.appendChild(el('div', { class: 'drop-overlay' }, 'Déposez la maquette IFC ici'));

    const add = (id: PageId, p: Page) => {
      p.el.classList.add('page');
      p.el.hidden = true;
      this.pages.set(id, p);
      this.main.appendChild(p.el);
    };
    add('home', new HomePage(this));
    const vp = new ViewerPage(this);
    add('viewer', vp);
    add('metre', new MetrePage(this));
    add('nomenclature', new NomenclaturePage(this));
    add('deperditions', new DeperditionsPage(this));
    add('coherence', new CoherencePage(this));
    add('maintenance', new MaintenancePage(this));
    add('energie', new EnergiePage(this));
    add('defis', new DefisPage(this));
    add('settings', new SettingsPage(this));
    this.updateTabs();
    this.go('home');
    this.installShortcuts();
    this.installDragDrop();
    onExternalFile((f) => this.loadBytes(f.name, f.data, f.path));
    const init = await initialFile().catch(() => null);
    if (init) await this.loadBytes(init.name, init.data, init.path);
    (window as any).bimysApp = this;
  }

  applyTheme() {
    const t = this.settings.theme;
    const dark = t === 'sombre' || (t === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'sombre' : 'clair';
    this.viewer?.setBackground(getComputedStyle(document.documentElement).getPropertyValue('--viewer-bg').trim());
  }

  private updateTabs() {
    for (const t of TABS) this.tabs.get(t.id)!.disabled = t.needModel && !this.model;
    this.fileLabel.textContent = this.model ? this.model.data.fileName : '';
  }

  go(page: PageId) {
    const t = TABS.find((x) => x.id === page);
    if (t?.needModel && !this.model) page = 'home';
    const prev = this.pages.get(this.current);
    if (prev && this.current !== page) {
      prev.hide?.();
      prev.el.hidden = true;
    }
    this.current = page;
    for (const [id, b] of this.tabs) b.classList.toggle('active', id === page);
    const p = this.pages.get(page)!;
    p.el.hidden = false;
    p.show?.();
    if (page === 'viewer') this.viewer?.resize();
  }

  get currentPage(): PageId {
    return this.current;
  }

  setViewer(v: Viewer) {
    this.viewer = v;
  }

  async openFile() {
    const f = await pickIfc();
    if (f) await this.loadBytes(f.name, f.data, f.path);
  }

  async openSample(name: string) {
    const url = new URL(`samples/${name}`, document.baseURI).href;
    const r = await fetch(url);
    if (!r.ok) {
      toast(`Exemple introuvable : ${name}`, { error: true });
      return;
    }
    await this.loadBytes(name, await r.arrayBuffer(), undefined, false);
  }

  private getWorker(): Worker {
    if (!this.worker) this.worker = new Worker(new URL('../worker/ifc.worker.ts', import.meta.url), { type: 'module' });
    return this.worker;
  }

  async loadBytes(name: string, data: ArrayBuffer, path?: string, remember = true) {
    if (this.loading) return;
    if (!/\.ifc$/i.test(name) && !new TextDecoder().decode(new Uint8Array(data.slice(0, 20))).startsWith('ISO-10303-21')) {
      toast(`« ${name} » n'est pas un fichier IFC (format STEP ISO-10303-21 attendu).`, { error: true });
      return;
    }
    this.loading = true;
    const loader = new Loader(`Ouverture de ${name}`);
    const size = data.byteLength;
    const copy = remember ? data.slice(0) : null;
    try {
      const w = this.getWorker();
      const res = await new Promise<{ data: ModelData; buckets: GeoBucket[] }>((resolve, reject) => {
        w.onmessage = (ev) => {
          const m = ev.data;
          if (m.type === 'progress') loader.set(m.pct, m.label);
          else if (m.type === 'done') resolve({ data: m.data, buckets: m.buckets });
          else if (m.type === 'error') reject(new Error(m.message));
        };
        w.onerror = (e) => reject(new Error(e.message || 'Erreur du module de lecture IFC'));
        w.postMessage({ type: 'load', bytes: data, fileName: name, wasmPath: new URL('wasm/', document.baseURI).href }, [data]);
      });
      loader.set(99, 'Affichage 3D');
      this.model = new Model(res.data);
      this.buckets = res.buckets;
      this.updateTabs();
      // la vue 3D est affichée avant le chargement pour que le cadrage tienne compte de la taille réelle
      this.go('viewer');
      for (const p of this.pages.values()) p.modelChanged?.();
      await this.refreshMarkers();
      if (copy) {
        await addRecent({ id: `${Date.now()}`, name, size, date: Date.now(), path, blob: size < 80e6 ? new Blob([copy]) : undefined }).catch(() => {});
        if (path && isElectron) electron()?.addRecent(path);
      }
      const n = res.data.elements.length;
      toast(`${name} : ${n} objets chargés (${res.data.schema}).`);
    } catch (e: any) {
      console.error(e);
      toast(`Impossible d'ouvrir ${name} : ${e?.message ?? e}`, { error: true, ms: 9000 });
      this.worker?.terminate();
      this.worker = null;
    } finally {
      loader.close();
      this.loading = false;
    }
  }

  showElement(id: number, isolate = false) {
    this.go('viewer');
    const vp = this.pages.get('viewer') as ViewerPage;
    vp.selectElement(id, true, isolate);
  }

  async exportFile(name: string, data: Uint8Array | string, mime: string, title = name) {
    try {
      const res = await saveFile(name, data, mime);
      if (!res.ok) {
        toast(res.message);
        return;
      }
      const actions = [];
      if (canShare() && res.uri) actions.push({ label: 'Partager', run: () => void shareFile(res, title) });
      if (isElectron && res.path) actions.push({ label: 'Afficher', run: () => electron()!.showItem(res.path!) });
      toast(res.message, { actions });
    } catch (e: any) {
      toast(`Échec de l'enregistrement : ${e?.message ?? e}`, { error: true });
    }
  }

  async saveSettings(s: Settings) {
    this.settings = s;
    await dbSaveSettings(s);
    this.applyTheme();
  }

  setMaint(c: MaintConfig) {
    this.maint = c;
    (this.pages.get('maintenance') as MaintenancePage).modelChanged();
    void this.refreshMarkers();
  }

  async refreshMarkers() {
    const mp = this.pages.get('maintenance') as MaintenancePage | undefined;
    if (mp && this.model) await mp.updateMarkers();
  }

  private installShortcuts() {
    window.addEventListener('keydown', (e) => {
      const t = e.target as HTMLElement;
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'o') {
        e.preventDefault();
        void this.openFile();
        return;
      }
      if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
      const vp = this.pages.get('viewer') as ViewerPage;
      if (e.key === 'Escape') {
        document.querySelector('.modal-bg')?.remove();
        if (this.current === 'viewer') vp.escape();
        return;
      }
      if (this.current !== 'viewer' || !this.model) return;
      const k = e.key.toLowerCase();
      if (k === 'f') vp.fit();
      else if (k === 'h') vp.hideSelection();
      else if (k === 'i') vp.isolateSelection();
      else if (k === 'a') vp.showAll();
      else return;
      e.preventDefault();
    });
  }

  private installDragDrop() {
    let depth = 0;
    window.addEventListener('dragenter', (e) => {
      if (!e.dataTransfer?.types.includes('Files')) return;
      depth++;
      document.body.classList.add('dragging');
    });
    window.addEventListener('dragleave', () => {
      depth = Math.max(0, depth - 1);
      if (!depth) document.body.classList.remove('dragging');
    });
    window.addEventListener('dragover', (e) => e.preventDefault());
    window.addEventListener('drop', async (e) => {
      e.preventDefault();
      depth = 0;
      document.body.classList.remove('dragging');
      const f = e.dataTransfer?.files?.[0];
      if (!f) return;
      let path: string | undefined;
      try {
        path = electron()?.getPathForFile(f) || undefined;
      } catch {
        path = undefined;
      }
      await this.loadBytes(f.name, await f.arrayBuffer(), path);
    });
  }
}
