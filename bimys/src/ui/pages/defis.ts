import { formatAnswer, generateQuestions, scoreDefi, type DefiResult, type Question } from '../../core/defis';
import { DEFAULT_PARAMS } from '../../core/deperditions';
import { dateFr, fmt, slug, today } from '../../core/format';
import { toCsv } from '../../core/csv';
import { clearDefis, listDefis, saveDefi } from '../../store/db';
import type { Ctx, Page } from '../ctx';
import { confirmBox, el, esc, promptBox, toast } from '../dom';
import { icon } from '../icons';

export class DefisPage implements Page {
  el = el('section');
  private body: HTMLElement;
  private prof = false;
  private questions: Question[] = [];
  private answers: string[] = [];
  private result: DefiResult | null = null;
  private eleve = '';
  private classe = '';
  private seed = 0;
  private profBtn: HTMLButtonElement;

  constructor(private ctx: Ctx) {
    const inner = el('div', { class: 'page-inner' });
    inner.innerHTML = `<h1>${icon('trophy')} Défis</h1><p class="lead">Questions générées automatiquement à partir de la maquette ouverte, corrigées avec tolérance sur les valeurs numériques.</p>`;
    const tb = el('div', { class: 'toolbar' });
    this.profBtn = el('button', { class: 'btn' }, `${icon('lock')} Mode prof`) as HTMLButtonElement;
    this.profBtn.onclick = () => this.toggleProf();
    tb.append(el('span', { class: 'spacer' }), this.profBtn);
    this.body = el('div');
    inner.append(tb, this.body);
    this.el.appendChild(inner);
  }

  modelChanged() {
    this.questions = [];
    this.result = null;
  }

  show() {
    if (!this.questions.length) this.renderStart();
  }

  private async toggleProf() {
    if (this.prof) {
      this.prof = false;
    } else {
      const code = await promptBox('Mode prof', 'Code enseignant', 'password');
      if (code === null) return;
      if (code !== this.ctx.settings.codeProf) {
        toast('Code incorrect.', { error: true });
        return;
      }
      this.prof = true;
    }
    this.profBtn.innerHTML = `${icon(this.prof ? 'unlock' : 'lock')} ${this.prof ? 'Quitter le mode prof' : 'Mode prof'}`;
    this.profBtn.classList.toggle('accent', this.prof);
    if (this.questions.length) this.renderQuestions();
    else this.renderStart();
  }

  private renderStart() {
    this.seed = this.seed || Math.floor(1000 + Math.random() * 9000);
    const s = this.ctx.settings;
    const card = el('div', { class: 'card' });
    card.innerHTML = `
      <h2>${icon('trophy')} Nouveau défi</h2>
      <div class="grid">
        <label class="field">Nom et prénom de l'élève<input type="text" data-k="eleve" value="${esc(this.eleve)}" placeholder="Obligatoire"></label>
        <label class="field">Classe<input type="text" data-k="classe" value="${esc(this.classe)}" placeholder="ex. 1re ICCER"></label>
        <label class="field">Nombre de questions<input type="number" min="3" max="20" data-k="n" value="${s.nbQuestions}"></label>
        <label class="field">N° de série (même série = mêmes questions)<input type="number" data-k="seed" value="${this.seed}"></label>
      </div>
      <div class="toolbar" style="margin-top:12px"><span class="spacer"></span><button class="btn accent" data-k="go">${icon('trophy')} Commencer</button></div>`;
    card.querySelector<HTMLButtonElement>('[data-k=go]')!.onclick = () => {
      const q = (k: string) => card.querySelector<HTMLInputElement>(`[data-k=${k}]`)!.value.trim();
      this.eleve = q('eleve');
      this.classe = q('classe');
      if (!this.eleve) {
        toast("Indiquez le nom de l'élève.", { error: true });
        return;
      }
      this.seed = Number(q('seed')) || this.seed;
      const n = Math.max(3, Math.min(20, Number(q('n')) || 10));
      const params = { ...DEFAULT_PARAMS, te: s.te, pontsPct: s.pontsPct, seuilSous: s.seuilSous, seuilSur: s.seuilSur };
      this.questions = generateQuestions(this.ctx.model!, this.seed, n, params);
      this.answers = this.questions.map(() => '');
      this.result = null;
      this.renderQuestions();
    };
    this.body.innerHTML = '';
    this.body.appendChild(card);
    if (this.prof) void this.renderResults();
  }

  private renderQuestions() {
    this.body.innerHTML = '';
    const head = el('div', { class: 'card' });
    head.innerHTML = `<div class="toolbar" style="margin:0"><div><b>${esc(this.eleve)}</b>${this.classe ? ` (${esc(this.classe)})` : ''} · série n° ${this.seed} · ${this.questions.length} questions</div><span class="spacer"></span>${this.result ? `<span class="score">${this.result.score} / ${this.questions.length}</span>` : ''}</div>`;
    this.body.appendChild(head);
    this.questions.forEach((q, i) => {
      const done = !!this.result;
      const ok = this.result?.justes[i];
      const box = el('div', { class: 'q' + (done ? (ok ? ' ok' : ' ko') : '') });
      box.innerHTML = `<div><span class="qn">${i + 1}.</span>${esc(q.texte)}</div>`;
      const ans = el('div', { class: 'ans' });
      if (q.type === 'choix') {
        for (const c of q.choix ?? []) {
          const l = el('label', { class: 'inline', style: { marginRight: '12px' } }, `<input type="radio" name="q${i}" value="${esc(c)}" ${this.answers[i] === c ? 'checked' : ''} ${done ? 'disabled' : ''}> ${esc(c)}`);
          l.querySelector('input')!.onchange = () => (this.answers[i] = c);
          ans.appendChild(l);
        }
      } else {
        const input = el('input', { type: 'text', inputmode: 'decimal', value: this.answers[i], placeholder: 'Votre réponse', disabled: done, style: { width: '160px' } });
        input.oninput = () => (this.answers[i] = input.value);
        ans.appendChild(input);
        if (q.unite) ans.appendChild(el('span', {}, esc(q.unite)));
      }
      if (done) ans.appendChild(el('span', { class: `pill ${ok ? 'ok' : 'err'}` }, ok ? 'Juste' : 'Faux'));
      box.appendChild(ans);
      if (this.prof) box.appendChild(el('div', { class: 'corr' }, `<b>Corrigé :</b> ${esc(formatAnswer(q))}<br>${esc(q.explication)}`));
      this.body.appendChild(box);
    });
    const tb = el('div', { class: 'toolbar' });
    if (!this.result) {
      const v = el('button', { class: 'btn primary' }, `${icon('check')} Valider mes réponses`);
      v.onclick = async () => {
        const empty = this.answers.filter((a) => !a.trim()).length;
        if (empty && !(await confirmBox('Valider', `${empty} question(s) sans réponse. Valider quand même ?`, 'Valider'))) return;
        const { justes, score } = scoreDefi(this.questions, this.answers);
        this.result = { eleve: this.eleve, classe: this.classe, date: today(), seed: this.seed, fichier: this.ctx.model!.data.fileName, questions: this.questions, reponses: [...this.answers], justes, score };
        await saveDefi(this.result).catch(() => {});
        this.renderQuestions();
        toast(`Score : ${score} / ${this.questions.length}`);
      };
      tb.append(el('span', { class: 'spacer' }), v);
    } else {
      const again = el('button', { class: 'btn' }, `${icon('refresh')} Nouveau défi`);
      again.onclick = () => {
        this.questions = [];
        this.result = null;
        this.seed = 0;
        this.renderStart();
      };
      const pdf = el('button', { class: 'btn primary' }, `${icon('pdf')} Export PDF du résultat`);
      pdf.onclick = () => this.pdf(this.result!, false);
      tb.append(again, el('span', { class: 'spacer' }), pdf);
      if (this.prof) {
        const pc = el('button', { class: 'btn accent' }, `${icon('pdf')} PDF avec corrigé`);
        pc.onclick = () => this.pdf(this.result!, true);
        tb.appendChild(pc);
      }
    }
    this.body.appendChild(tb);
  }

  private async pdf(r: DefiResult, corr: boolean) {
    const { defiPdf } = await import('../../pdf/reports');
    await this.ctx.exportFile(`defi_${slug(r.eleve)}_${r.date}${corr ? '_corrige' : ''}.pdf`, await defiPdf(r, corr, this.ctx.settings), 'application/pdf', 'Résultat du défi');
  }

  private async renderResults() {
    const list = await listDefis().catch(() => []);
    const card = el('div', { class: 'card' });
    card.innerHTML = `<h2>${icon('list')} Résultats enregistrés sur cet appareil (${list.length})</h2>`;
    if (!list.length) card.innerHTML += '<div class="empty">Aucun résultat.</div>';
    else {
      card.innerHTML += `<div class="table-wrap"><table class="data"><thead><tr><th>Date</th><th>Élève</th><th>Classe</th><th>Maquette</th><th class="n">Série</th><th class="n">Score</th><th></th></tr></thead><tbody>${list
        .sort((a, b) => b.id - a.id)
        .map((r) => `<tr><td>${dateFr(r.date)}</td><td>${esc(r.eleve)}</td><td>${esc(r.classe)}</td><td>${esc(r.fichier)}</td><td class="n">${r.seed}</td><td class="n"><b>${r.score} / ${r.questions.length}</b> (${fmt((20 * r.score) / r.questions.length, 1)}/20)</td><td><button class="btn small" data-id="${r.id}">${icon('pdf')}</button></td></tr>`)
        .join('')}</tbody></table></div>`;
      const tb = el('div', { class: 'toolbar', style: { marginTop: '10px' } });
      const csv = el('button', { class: 'btn' }, `${icon('csv')} Export CSV`);
      csv.onclick = () => void this.ctx.exportFile(`resultats_defis_${today()}.csv`, toCsv(['Date', 'Élève', 'Classe', 'Maquette', 'Série', 'Score', 'Questions', 'Note /20'], list.map((r) => [r.date, r.eleve, r.classe, r.fichier, r.seed, r.score, r.questions.length, (20 * r.score) / r.questions.length])), 'text/csv', 'Résultats');
      const clr = el('button', { class: 'btn danger' }, `${icon('trash')} Effacer`);
      clr.onclick = async () => {
        if (!(await confirmBox('Effacer', 'Effacer tous les résultats enregistrés sur cet appareil ?', 'Effacer'))) return;
        await clearDefis();
        this.renderStart();
      };
      tb.append(csv, el('span', { class: 'spacer' }), clr);
      card.appendChild(tb);
    }
    card.querySelectorAll<HTMLButtonElement>('[data-id]').forEach((b) => {
      b.onclick = () => {
        const r = list.find((x) => x.id === Number(b.dataset.id));
        if (r) void this.pdf(r, true);
      };
    });
    this.body.appendChild(card);
  }
}
