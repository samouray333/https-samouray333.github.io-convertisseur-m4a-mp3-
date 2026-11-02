import { computeEnergie, DEFAULT_ACTIONS, ENERGIES, ENERGY_BY_ID, type EnergieInput, type EnergieResult, type EnergyType } from '../../core/energie';
import { computeBilan, DEFAULT_PARAMS } from '../../core/deperditions';
import { fmt, parseNum, slug } from '../../core/format';
import { kvGet, kvSet } from '../../store/db';
import type { Ctx, Page } from '../ctx';
import { debounce, el, esc } from '../dom';
import { icon } from '../icons';

export class EnergiePage implements Page {
  el = el('section');
  private inp!: EnergieInput;
  private res!: EnergieResult;
  private form: HTMLElement;
  private out: HTMLElement;
  private key = '';
  private save = debounce(() => kvSet(this.key, this.inp), 400);

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'page-inner' });
    inner.innerHTML = `
      <h1>${icon('bolt')} Bilan énergétique simple</h1>
      <p class="lead">Saisissez les consommations annuelles (factures) : ratio kWh/m².an et estimation des gains de quelques actions. Toutes les hypothèses sont affichées et modifiables.</p>`;
    const grid = el('div', { class: 'grid-2' });
    this.form = el('div');
    this.out = el('div');
    grid.append(this.form, this.out);
    inner.appendChild(grid);
    this.el.appendChild(inner);
  }

  modelChanged() {
    this.key = '';
  }

  async show() {
    const m = this.ctx.model;
    const key = `energie|${m ? m.fileKey : 'libre'}`;
    if (key !== this.key) {
      this.key = key;
      const surface = m ? Math.round(computeBilan(m, DEFAULT_PARAMS).surfaceChauffee * 10) / 10 : 100;
      const gas = m ? !!m.elements.find((e) => /ifcboiler/i.test(e.cls)) : true;
      const def: EnergieInput = {
        surface,
        consos: gas
          ? [{ type: 'gaz', quantite: 14000, partChauffage: 80 }, { type: 'electricite', quantite: 3200, partChauffage: 0 }]
          : [{ type: 'electricite', quantite: 7800, partChauffage: 55 }],
        prix: {},
        actions: { ...DEFAULT_ACTIONS, generateur: gas ? 'chaudiere' : 'aucun', rendementActuel: gas ? 0.85 : 1 },
      };
      this.inp = await kvGet<EnergieInput>(key, def);
      this.inp.actions = { ...DEFAULT_ACTIONS, ...this.inp.actions };
      this.renderForm();
    }
    this.compute();
  }

  private compute() {
    this.res = computeEnergie(this.inp);
    this.renderOut();
  }

  private renderForm() {
    const a = this.inp.actions;
    const f = this.form;
    f.innerHTML = `
      <div class="card"><h2>${icon('home')} Logement</h2>
        <label class="field">Surface chauffée (m²)${this.ctx.model ? ' : calculée depuis la maquette' : ''}<input type="text" inputmode="decimal" data-s="surface" value="${fmt(this.inp.surface, 1)}"></label>
      </div>
      <div class="card"><h2>${icon('flame')} Consommations annuelles</h2><div data-k="consos"></div>
        <button class="btn small" data-k="add">${icon('plus')} Ajouter une énergie</button></div>
      <div class="card"><h2>${icon('wrench')} Actions à étudier</h2>
        <label class="field">Remplacement du générateur<select data-a="generateur"><option value="aucun">Aucun</option><option value="chaudiere">Chaudière à condensation</option><option value="pac">Pompe à chaleur air/eau</option></select></label>
        <div class="grid" style="margin-top:8px">
          <label class="field">Rendement saisonnier actuel (%)<input type="text" inputmode="decimal" data-a="rendementActuel" data-pct="1" value="${fmt(a.rendementActuel * 100, 0)}"></label>
          <label class="field">Rendement chaudière neuve (%)<input type="text" inputmode="decimal" data-a="rendementChaudiere" data-pct="1" value="${fmt(a.rendementChaudiere * 100, 0)}"></label>
          <label class="field">SCOP de la PAC<input type="text" inputmode="decimal" data-a="scopPac" value="${fmt(a.scopPac, 1)}"></label>
        </div>
        ${(['isolationCombles', 'isolationMurs', 'fenetres', 'regulation'] as const)
          .map((k) => {
            const g = { isolationCombles: 'gainCombles', isolationMurs: 'gainMurs', fenetres: 'gainFenetres', regulation: 'gainRegulation' }[k] as 'gainCombles';
            const lab = { isolationCombles: 'Isolation des combles', isolationMurs: 'Isolation des murs', fenetres: 'Remplacement des fenêtres', regulation: 'Régulation (programmation, robinets thermostatiques)' }[k];
            return `<div class="check-row"><label class="inline lb"><input type="checkbox" data-a="${k}" ${a[k] ? 'checked' : ''}> ${lab}</label><label class="inline">gain <input type="text" class="num" inputmode="decimal" data-a="${g}" value="${fmt(a[g], 0)}" style="width:60px"> % du chauffage</label></div>`;
          })
          .join('')}
      </div>`;
    const consos = f.querySelector<HTMLElement>('[data-k=consos]')!;
    const drawConsos = () => {
      consos.innerHTML = '';
      this.inp.consos.forEach((c, i) => {
        const d = ENERGY_BY_ID[c.type];
        const row = el('div', { class: 'check-row' });
        row.innerHTML = `
          <select data-c="type">${ENERGIES.map((e) => `<option value="${e.id}" ${e.id === c.type ? 'selected' : ''}>${esc(e.label)}</option>`).join('')}</select>
          <label class="inline"><input type="text" class="num" inputmode="decimal" data-c="quantite" value="${fmt(c.quantite, 0)}" style="width:100px"> ${esc(d.unite)}/an</label>
          <label class="inline">dont chauffage <input type="text" class="num" inputmode="decimal" data-c="partChauffage" value="${fmt(c.partChauffage, 0)}" style="width:56px"> %</label>
          <label class="inline">prix <input type="text" class="num" inputmode="decimal" data-c="prix" value="${fmt(this.inp.prix[c.type] ?? d.prixKwh, 3)}" style="width:70px"> €/kWh</label>
          <button class="x-btn" title="Retirer">${icon('trash')}</button>`;
        row.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-c]').forEach((x) => {
          x.addEventListener(x.tagName === 'SELECT' ? 'change' : 'input', () => {
            const k = x.dataset.c!;
            if (k === 'type') {
              c.type = x.value as EnergyType;
              drawConsos();
            } else {
              const v = parseNum(x.value);
              if (v === null) return;
              if (k === 'prix') this.inp.prix[c.type] = v;
              else (c as any)[k] = v;
            }
            this.changed();
          });
        });
        row.querySelector<HTMLButtonElement>('.x-btn')!.onclick = () => {
          this.inp.consos.splice(i, 1);
          drawConsos();
          this.changed();
        };
        consos.appendChild(row);
      });
    };
    drawConsos();
    f.querySelector<HTMLButtonElement>('[data-k=add]')!.onclick = () => {
      this.inp.consos.push({ type: 'electricite', quantite: 0, partChauffage: 0 });
      drawConsos();
      this.changed();
    };
    f.querySelector<HTMLInputElement>('[data-s=surface]')!.oninput = (e) => {
      const v = parseNum((e.target as HTMLInputElement).value);
      if (v !== null && v > 0) {
        this.inp.surface = v;
        this.changed();
      }
    };
    const gen = f.querySelector<HTMLSelectElement>('[data-a=generateur]')!;
    gen.value = a.generateur;
    f.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-a]').forEach((x) => {
      x.addEventListener(x.tagName === 'SELECT' || (x as HTMLInputElement).type === 'checkbox' ? 'change' : 'input', () => {
        const k = x.dataset.a as keyof typeof a;
        if (x.tagName === 'SELECT') (a as any)[k] = x.value;
        else if ((x as HTMLInputElement).type === 'checkbox') (a as any)[k] = (x as HTMLInputElement).checked;
        else {
          const v = parseNum(x.value);
          if (v === null || v <= 0) return;
          (a as any)[k] = x.dataset.pct ? v / 100 : v;
        }
        this.changed();
      });
    });
  }

  private changed() {
    this.save();
    this.compute();
  }

  private renderOut() {
    const r = this.res;
    this.out.innerHTML = `
      <div class="kpis">
        <div class="kpi"><div class="l">Consommation totale</div><div class="v">${fmt(r.totalKwh, 0)} <small>kWh/an</small></div></div>
        <div class="kpi"><div class="l">Ratio</div><div class="v">${fmt(r.ratio, 0)} <small>kWh/m².an</small></div></div>
        <div class="kpi"><div class="l">Coût</div><div class="v">${fmt(r.cout, 0)} <small>€/an</small></div></div>
        <div class="kpi"><div class="l">Émissions</div><div class="v">${fmt(r.co2 / 1000, 2)} <small>t CO2/an</small></div></div>
      </div>
      <div class="card"><h2>${icon('thermo')} Situation actuelle</h2>
        <p>Chauffage : <b>${fmt(r.chauffageKwh, 0)} kWh/an</b> (${fmt(r.ratioChauffage, 0)} kWh/m².an). Niveau indicatif : <span class="pill ${r.ratio < 110 ? 'ok' : r.ratio < 180 ? 'warn' : 'err'}">${esc(r.classe)}</span></p>
        <p class="lead" style="font-size:12.5px">Énergie finale. Repères : &lt; 70 très performant, 70 à 110 performant, 110 à 180 moyen, 180 à 250 énergivore, &gt; 250 très énergivore. Ce n'est pas un DPE (énergie primaire et CO2).</p>
      </div>
      <div class="card"><h2>${icon('bolt')} Gains estimés</h2>
        ${r.gains.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Action (seule)</th><th class="n">kWh/an</th><th class="n">€/an</th><th class="n">kg CO2/an</th></tr></thead><tbody>${r.gains.map((g) => `<tr><td><b>${esc(g.action)}</b><br><small class="lead">${esc(g.hypothese)}</small></td><td class="n">${fmt(g.kwh, 0)}</td><td class="n">${fmt(g.euros, 0)}</td><td class="n">${fmt(g.co2, 0)}</td></tr>`).join('')}</tbody></table></div>
        <div class="formula">Toutes actions cumulées (appliquées successivement) : ${fmt(r.apres.kwh, 0)} kWh/an soit ${fmt(r.apres.ratio, 0)} kWh/m².an, ${fmt(r.apres.cout, 0)} €/an, ${fmt(r.apres.co2 / 1000, 2)} t CO2/an.<br>Économie totale : ${fmt(r.totalKwh - r.apres.kwh, 0)} kWh/an (${fmt(r.totalKwh ? (100 * (r.totalKwh - r.apres.kwh)) / r.totalKwh : 0, 0)} %), ${fmt(r.cout - r.apres.cout, 0)} €/an.</div>` : '<div class="empty">Cochez au moins une action.</div>'}
        <p class="lead" style="font-size:12.5px;margin-top:10px">Hypothèses : PCI fioul 10 kWh/L, propane 12,8 kWh/kg, bois 1 700 kWh/stère, granulés 4,8 kWh/kg. Facteurs CO2 (kg/kWh) : gaz 0,227, électricité 0,079, fioul 0,324, propane 0,272, bois 0,030. Prix modifiables dans la liste des consommations.</p>
        <div class="toolbar"><span class="spacer"></span><button class="btn primary" data-k="pdf">${icon('pdf')} Export PDF</button></div>
      </div>`;
    this.out.querySelector<HTMLButtonElement>('[data-k=pdf]')!.onclick = async () => {
      const { energiePdf } = await import('../../pdf/reports');
      const name = this.ctx.model ? slug(this.ctx.model.data.fileName.replace(/\.ifc$/i, '')) : 'saisie';
      await this.ctx.exportFile(`bilan_energetique_${name}.pdf`, await energiePdf(this.ctx.model, this.inp, this.res, this.ctx.settings), 'application/pdf', 'Bilan énergétique');
    };
  }
}
