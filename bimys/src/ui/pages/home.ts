import type { Ctx, Page } from '../ctx';
import { el, esc, toast } from '../dom';
import { icon } from '../icons';
import { getRecent, listRecents, removeRecent } from '../../store/db';
import { electron, isAndroid, isElectron } from '../../platform/platform';
import logoUrl from '../../assets/logo.svg?url';

export const SAMPLES = [
  { file: 'maison_chaudiere_gaz.ifc', title: 'Maison R+1 : chaudière gaz', desc: '110 m², radiateurs bitube cuivre et multicouche, ballon 150 L, VMC hygro B', icon: 'flame' },
  { file: 'maison_pac_air_eau.ifc', title: 'Maison R+1 : PAC air/eau', desc: 'Même maison, PAC monobloc R410A 2,4 kg, module hydraulique, ballon 200 L', icon: 'fan' },
];

export class HomePage implements Page {
  el = el('section', { class: 'home' });
  private recentBox: HTMLElement;

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'home-inner' });
    inner.innerHTML = `
      <div class="hero">
        <img src="${logoUrl}" alt="Logo Bimys">
        <div>
          <h1>Bimys</h1>
          <p>Maquettes BIM en génie thermique : réseaux, métrés, déperditions, maintenance. Bac Pro ICCER et MEE.</p>
          <button class="btn accent" data-act="open">${icon('open')} Ouvrir une maquette IFC</button>
        </div>
      </div>
      <div class="samples"></div>
      <div class="grid-2">
        <div class="card"><h2>${icon('refresh')} Fichiers récents</h2><div class="recents"></div></div>
        <div class="card"><h2>${icon('info')} Prise en main</h2>
          <p class="lead" style="margin-bottom:8px">Ouvrez un exemple puis l'onglet <b>Métré</b> : deux clics suffisent.</p>
          <div class="drop-hint">${isAndroid ? 'Astuce : depuis le gestionnaire de fichiers, « Ouvrir avec » Bimys sur un fichier .ifc.' : 'Glissez-déposez un fichier .ifc n\'importe où dans la fenêtre.'}</div>
          ${isAndroid ? '' : `<p class="lead" style="margin-top:10px">Raccourcis : <span class="kbd">Ctrl+O</span> ouvrir, <span class="kbd">F</span> cadrer, <span class="kbd">H</span> masquer, <span class="kbd">I</span> isoler, <span class="kbd">A</span> tout afficher, <span class="kbd">Échap</span> désélectionner.</p>`}
        </div>
      </div>`;
    this.el.appendChild(inner);
    inner.querySelector<HTMLButtonElement>('[data-act=open]')!.onclick = () => ctx.openFile();
    const s = inner.querySelector('.samples')!;
    for (const x of SAMPLES) {
      const b = el('button', { class: 'sample', 'data-sample': x.file }, `<div class="ico">${icon(x.icon)}</div><div><b>${esc(x.title)}</b><span>${esc(x.desc)}</span></div>`);
      b.onclick = () => ctx.openSample(x.file);
      s.appendChild(b);
    }
    this.recentBox = inner.querySelector('.recents')!;
  }

  async show() {
    const list = await listRecents().catch(() => []);
    this.recentBox.innerHTML = '';
    if (!list.length) {
      this.recentBox.innerHTML = '<div class="empty">Aucun fichier ouvert récemment.</div>';
      return;
    }
    const ul = el('ul', { class: 'recent-list' });
    for (const r of list) {
      const li = el('li');
      const d = new Date(r.date);
      li.innerHTML = `${icon('cube')}<span class="nm" title="${esc(r.path ?? r.name)}">${esc(r.name)}</span><small class="lead" style="margin:0">${(r.size / 1e6).toFixed(1).replace('.', ',')} Mo, ${d.toLocaleDateString('fr-FR')}</small>`;
      li.querySelector<HTMLElement>('.nm')!.onclick = async () => {
        const full = await getRecent(r.id);
        if (full?.blob) return this.ctx.loadBytes(full.name, await full.blob.arrayBuffer(), full.path);
        if (isElectron && full?.path) {
          try {
            return this.ctx.loadBytes(full.name, await electron()!.readFile(full.path), full.path);
          } catch {
            /* fichier déplacé */
          }
        }
        toast('Fichier introuvable : rouvrez-le avec le bouton Ouvrir.', { error: true });
      };
      const del = el('button', { class: 'x-btn', title: 'Retirer de la liste', 'aria-label': 'Retirer' }, icon('close'));
      del.onclick = async () => {
        await removeRecent(r.id);
        this.show();
      };
      li.appendChild(del);
      ul.appendChild(li);
    }
    this.recentBox.appendChild(ul);
  }
}
