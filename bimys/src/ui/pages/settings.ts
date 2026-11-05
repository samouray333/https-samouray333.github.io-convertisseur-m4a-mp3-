import { DEFAULT_MAINT, validateConfig } from '../../core/maintenance';
import { parseNum, today } from '../../core/format';
import { exportBackup, importBackup, setMaintOverride, type Settings } from '../../store/db';
import { exportsLocation, platformName } from '../../platform/platform';
import type { Ctx, Page } from '../ctx';
import { el, esc, modal, promptBox, toast } from '../dom';
import { icon } from '../icons';

const LICENCES = [
  ['three.js', 'MIT'],
  ['web-ifc (That Open Company)', 'MPL-2.0'],
  ['three-mesh-bvh', 'MIT'],
  ['jsPDF', 'MIT'],
  ['jspdf-autotable', 'MIT'],
  ['idb', 'ISC'],
  ['Capacitor (core, Filesystem, Share, Splash Screen)', 'MIT'],
  ['Electron', 'MIT (Chromium : BSD et licences tierces)'],
  ['Police DejaVu Sans (sous-ensemble)', 'Licence Bitstream Vera / domaine public'],
];

function pickFile(accept: string): Promise<File | null> {
  return new Promise((resolve) => {
    const i = document.createElement('input');
    i.type = 'file';
    i.accept = accept;
    i.onchange = () => resolve(i.files?.[0] ?? null);
    i.click();
  });
}

function resizeLogo(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const k = Math.min(1, 480 / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/png'));
    };
    img.onerror = () => reject(new Error('Image illisible'));
    img.src = url;
  });
}

export class SettingsPage implements Page {
  el = el('section');
  private inner = el('div', { class: 'page-inner' });

  constructor(private ctx: Ctx) {
    this.el.appendChild(this.inner);
  }

  show() {
    this.render();
  }

  private render() {
    const s = this.ctx.settings;
    this.inner.innerHTML = `
      <h1>${icon('gear')} Paramètres</h1>
      <p class="lead">Réglages enregistrés sur cet appareil. Exports enregistrés dans : <b>${esc(exportsLocation())}</b>.</p>
      <div class="card"><h2>${icon('home')} Établissement (en-tête des rapports PDF)</h2>
        <div class="grid">
          <label class="field">Nom de l'établissement<input type="text" data-s="etablissement" value="${esc(s.etablissement)}"></label>
          <label class="field">Adresse / section<input type="text" data-s="adresse" value="${esc(s.adresse)}" placeholder="ex. Section ICCER, 71000 Mâcon"></label>
          <label class="field">Intervenant par défaut<input type="text" data-s="intervenant" value="${esc(s.intervenant)}"></label>
        </div>
        <div class="toolbar" style="margin-top:10px">${s.logo ? `<img src="${s.logo}" alt="Logo" style="height:48px;border-radius:6px;border:1px solid var(--border)">` : '<span class="lead" style="margin:0">Aucun logo.</span>'}
          <button class="btn" data-a="logo">${icon('upload')} Choisir un logo</button>${s.logo ? `<button class="btn danger" data-a="nologo">Retirer</button>` : ''}</div>
      </div>
      <div class="card"><h2>${icon('thermo')} Calculs</h2>
        <div class="grid">
          <label class="field">Température extérieure de base (°C)<input type="text" inputmode="decimal" data-n="te" value="${s.te}"></label>
          <label class="field">Ponts thermiques par défaut (%)<input type="text" inputmode="decimal" data-n="pontsPct" value="${s.pontsPct}"></label>
          <label class="field">Seuil sous-dimensionné (%)<input type="text" inputmode="decimal" data-n="seuilSous" value="${s.seuilSous}"></label>
          <label class="field">Seuil surdimensionné (%)<input type="text" inputmode="decimal" data-n="seuilSur" value="${s.seuilSur}"></label>
          <label class="field">Chutes par défaut du métré (%)<input type="text" inputmode="decimal" data-n="chutesPct" value="${s.chutesPct}"></label>
          <label class="field">Questions par défi<input type="text" inputmode="numeric" data-n="nbQuestions" value="${s.nbQuestions}"></label>
        </div>
        <p class="lead" style="font-size:12.5px;margin-top:8px">Saône-et-Loire (zone H1c) : −10 °C jusqu'à 200 m d'altitude, −11 °C de 201 à 400 m, −12 °C de 401 à 600 m (NF EN 12831, annexe nationale).</p>
      </div>
      <div class="card"><h2>${icon('palette')} Affichage</h2>
        <div class="grid">
          <label class="field">Thème<select data-s="theme"><option value="auto">Automatique (système)</option><option value="clair">Clair</option><option value="sombre">Sombre</option></select></label>
          <label class="field">Couleurs 3D<select data-s="couleurs"><option value="lot">Par lot (code couleur)</option><option value="ifc">Couleurs du fichier IFC</option></select></label>
          <label class="field">Qualité graphique<select data-s="qualite"><option value="auto">Automatique (selon l'appareil)</option><option value="haute">Haute (ombrage d'ambiance, éclairage réaliste)</option><option value="standard">Standard (plus rapide, tablettes et vieux PC)</option></select></label>
          <label class="field">Arêtes des objets<select data-b="aretes"><option value="1">Affichées</option><option value="0">Masquées</option></select></label>
          <label class="field">Grille au sol<select data-b="grille"><option value="1">Affichée</option><option value="0">Masquée</option></select></label>
        </div>
      </div>
      <div class="card"><h2>${icon('lock')} Mode prof</h2>
        <p class="lead">Le code protège l'affichage des corrigés des défis. Code actuel requis pour le modifier (code initial : 1234).</p>
        <button class="btn" data-a="code">${icon('lock')} Changer le code prof</button>
      </div>
      <div class="card"><h2>${icon('wrench')} Check-lists de maintenance</h2>
        <p class="lead">Les check-lists viennent du fichier <b>src/data/maintenance.json</b> (modifiable puis reconstruire l'appli), ou d'un fichier importé ici sans reconstruire. Version active : <b>${this.ctx.maint === DEFAULT_MAINT ? 'fichier intégré' : 'fichier importé'}</b> (${this.ctx.maint.types.length} types d'équipements).</p>
        <div class="toolbar"><button class="btn" data-a="mexp">${icon('download')} Exporter le JSON actif</button><button class="btn" data-a="mimp">${icon('upload')} Importer un JSON</button>${this.ctx.maint === DEFAULT_MAINT ? '' : `<button class="btn danger" data-a="mreset">Revenir au fichier intégré</button>`}</div>
      </div>
      <div class="card"><h2>${icon('save')} Sauvegarde et restauration</h2>
        <p class="lead">Toutes les données locales : réglages, interventions (avec photos et signatures), saisies de déperditions, bilans énergétiques, résultats des défis.</p>
        <div class="toolbar"><button class="btn primary" data-a="bexp">${icon('download')} Sauvegarder (JSON)</button><button class="btn" data-a="bimp">${icon('upload')} Restaurer…</button></div>
      </div>
      <div class="card"><h2>${icon('info')} À propos</h2>
        <p><b>Bimys ${esc(this.ctx.version)}</b> (QMTech) : ${esc(platformName)}. Application 100 % hors ligne, aucune donnée envoyée.</p>
        <div class="table-wrap"><table class="data"><thead><tr><th>Composant</th><th>Licence</th></tr></thead><tbody>${LICENCES.map(([a, b]) => `<tr><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')}</tbody></table></div>
      </div>`;
    const q = <T extends HTMLElement>(sel: string) => this.inner.querySelector(sel) as T;
    q<HTMLSelectElement>('[data-s=theme]').value = s.theme;
    q<HTMLSelectElement>('[data-s=couleurs]').value = s.couleurs;
    q<HTMLSelectElement>('[data-s=qualite]').value = s.qualite;
    q<HTMLSelectElement>('[data-b=aretes]').value = s.aretes ? '1' : '0';
    q<HTMLSelectElement>('[data-b=grille]').value = s.grille ? '1' : '0';
    this.inner.querySelectorAll<HTMLSelectElement>('[data-b]').forEach((x) => {
      x.addEventListener('change', async () => {
        await save({ [x.dataset.b!]: x.value === '1' } as any);
        this.ctx.applyGraphics();
      });
    });
    const save = (patch: Partial<Settings>) => this.ctx.saveSettings({ ...this.ctx.settings, ...patch });
    this.inner.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-s]').forEach((x) => {
      x.addEventListener('change', async () => {
        await save({ [x.dataset.s!]: x.value } as any);
        if (x.dataset.s === 'couleurs') this.ctx.viewer?.setColorMode(x.value as any);
        if (x.dataset.s === 'qualite') this.ctx.applyGraphics();
      });
    });
    this.inner.querySelectorAll<HTMLInputElement>('[data-n]').forEach((x) => {
      x.addEventListener('change', () => {
        const v = parseNum(x.value);
        if (v === null) {
          toast('Valeur numérique attendue.', { error: true });
          return;
        }
        void save({ [x.dataset.n!]: v } as any);
        toast('Réglage enregistré.');
      });
    });
    q<HTMLButtonElement>('[data-a=logo]').onclick = async () => {
      const f = await pickFile('image/*');
      if (!f) return;
      await save({ logo: await resizeLogo(f) });
      this.render();
    };
    const nl = this.inner.querySelector<HTMLButtonElement>('[data-a=nologo]');
    if (nl)
      nl.onclick = async () => {
        await save({ logo: '' });
        this.render();
      };
    q<HTMLButtonElement>('[data-a=code]').onclick = async () => {
      const cur = await promptBox('Changer le code prof', 'Code actuel', 'password');
      if (cur === null) return;
      if (cur !== this.ctx.settings.codeProf) return toast('Code actuel incorrect.', { error: true });
      const n1 = await promptBox('Changer le code prof', 'Nouveau code (4 caractères minimum)', 'password');
      if (!n1 || n1.length < 4) return toast('Code trop court.', { error: true });
      await save({ codeProf: n1 });
      toast('Code prof modifié.');
    };
    q<HTMLButtonElement>('[data-a=mexp]').onclick = () => void this.ctx.exportFile('maintenance.json', JSON.stringify(this.ctx.maint, null, 2), 'application/json', 'Check-lists');
    q<HTMLButtonElement>('[data-a=mimp]').onclick = async () => {
      const f = await pickFile('.json,application/json');
      if (!f) return;
      try {
        const cfg = JSON.parse(await f.text());
        const err = validateConfig(cfg);
        if (err) return toast(err, { error: true, ms: 8000 });
        await setMaintOverride(cfg);
        this.ctx.setMaint(cfg);
        toast(`Check-lists importées (${cfg.types.length} types).`);
        this.render();
      } catch (e: any) {
        toast(`JSON invalide : ${e.message}`, { error: true });
      }
    };
    const mr = this.inner.querySelector<HTMLButtonElement>('[data-a=mreset]');
    if (mr)
      mr.onclick = async () => {
        await setMaintOverride(null);
        this.ctx.setMaint(DEFAULT_MAINT);
        this.render();
      };
    q<HTMLButtonElement>('[data-a=bexp]').onclick = async () => {
      const b = await exportBackup(this.ctx.version);
      await this.ctx.exportFile(`sauvegarde_bimys_${today()}.json`, JSON.stringify(b), 'application/json', 'Sauvegarde Bimys');
    };
    q<HTMLButtonElement>('[data-a=bimp]').onclick = async () => {
      const f = await pickFile('.json,application/json');
      if (!f) return;
      let data: any;
      try {
        data = JSON.parse(await f.text());
      } catch {
        return toast('Fichier JSON illisible.', { error: true });
      }
      const choice = await modal('Restaurer une sauvegarde', `<p>Sauvegarde du ${esc(String(data?.date ?? '').slice(0, 10))}. Fusionner avec les données actuelles, ou tout remplacer ?</p>`, [{ label: 'Annuler' }, { label: 'Fusionner' }, { label: 'Remplacer', cls: 'primary' }]);
      if (choice < 1) return;
      try {
        const r = await importBackup(data, choice === 2);
        toast(`Restauration terminée : ${r.interventions} intervention(s), ${r.rooms} pièce(s). Redémarrage…`);
        setTimeout(() => location.reload(), 1200);
      } catch (e: any) {
        toast(e.message, { error: true });
      }
    };
  }
}
