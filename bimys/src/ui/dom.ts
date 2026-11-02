// Petites aides DOM : création d'éléments, notifications, fenêtres modales.
export function esc(s: unknown): string {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, any> = {}, html = ''): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else e.setAttribute(k, v === true ? '' : String(v));
  }
  if (html) e.innerHTML = html;
  return e;
}

export function qs<T extends HTMLElement = HTMLElement>(root: ParentNode, sel: string): T {
  return root.querySelector(sel) as T;
}

let toastHost: HTMLElement | null = null;

export interface ToastAction {
  label: string;
  run: () => void;
}

export function toast(msg: string, opts: { error?: boolean; actions?: ToastAction[]; ms?: number } = {}) {
  if (!toastHost) {
    toastHost = el('div', { class: 'toasts', role: 'status', 'aria-live': 'polite' });
    document.body.appendChild(toastHost);
  }
  const t = el('div', { class: 'toast' + (opts.error ? ' err' : '') });
  t.appendChild(el('div', { class: 'grow' }, esc(msg)));
  for (const a of opts.actions ?? []) {
    const b = el('button', {}, esc(a.label));
    b.onclick = () => {
      a.run();
      t.remove();
    };
    t.appendChild(b);
  }
  const x = el('button', { 'aria-label': 'Fermer' }, '✕');
  x.onclick = () => t.remove();
  t.appendChild(x);
  toastHost.appendChild(t);
  setTimeout(() => t.remove(), opts.ms ?? (opts.actions?.length ? 9000 : 4500));
}

export function modal(title: string, body: HTMLElement | string, buttons: { label: string; cls?: string; run?: () => boolean | void | Promise<boolean | void> }[]): Promise<number> {
  return new Promise((resolve) => {
    const bg = el('div', { class: 'modal-bg' });
    const m = el('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true' });
    m.appendChild(el('h3', {}, esc(title)));
    if (typeof body === 'string') m.appendChild(el('div', {}, body));
    else m.appendChild(body);
    const act = el('div', { class: 'actions' });
    buttons.forEach((b, i) => {
      const btn = el('button', { class: 'btn ' + (b.cls ?? '') }, esc(b.label));
      btn.onclick = async () => {
        const r = b.run ? await b.run() : undefined;
        if (r === false) return;
        bg.remove();
        resolve(i);
      };
      act.appendChild(btn);
    });
    m.appendChild(act);
    bg.appendChild(m);
    bg.addEventListener('click', (e) => {
      if (e.target === bg) {
        bg.remove();
        resolve(-1);
      }
    });
    document.body.appendChild(bg);
    (m.querySelector('input,select,textarea') as HTMLElement | null)?.focus();
  });
}

export async function confirmBox(title: string, text: string, ok = 'Confirmer'): Promise<boolean> {
  return (await modal(title, `<p>${esc(text)}</p>`, [{ label: 'Annuler' }, { label: ok, cls: 'primary' }])) === 1;
}

export async function promptBox(title: string, label: string, type = 'text', value = ''): Promise<string | null> {
  const wrap = el('div');
  const f = el('label', { class: 'field' }, esc(label));
  const input = el('input', { type, value });
  f.appendChild(input);
  wrap.appendChild(f);
  let out: string | null = null;
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') (wrap.closest('.modal')?.querySelector('.btn.primary') as HTMLButtonElement)?.click();
  });
  const r = await modal(title, wrap, [{ label: 'Annuler' }, { label: 'Valider', cls: 'primary', run: () => void (out = input.value) }]);
  return r === 1 ? out : null;
}

export class Loader {
  private root: HTMLElement;
  private bar: HTMLElement;
  private lbl: HTMLElement;
  constructor(title: string) {
    this.root = el('div', { class: 'loader' });
    const box = el('div', { class: 'loader-box' }, `<b>${esc(title)}</b><div class="lbl">Préparation…</div><div class="bar"><i></i></div>`);
    this.root.appendChild(box);
    this.bar = box.querySelector('i')!;
    this.lbl = box.querySelector('.lbl')!;
    document.body.appendChild(this.root);
  }
  set(pct: number, label: string) {
    this.bar.style.width = `${Math.max(2, Math.min(100, pct))}%`;
    this.lbl.textContent = `${label} (${Math.round(pct)} %)`;
  }
  close() {
    this.root.remove();
  }
}

export function num(input: HTMLInputElement): number | null {
  const t = input.value.trim().replace(/\s/g, '').replace(',', '.');
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function debounce<T extends (...a: any[]) => void>(fn: T, ms = 250): T {
  let t: any;
  return ((...a: any[]) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  }) as T;
}
