/** Nombre au format français (virgule décimale, espace pour les milliers). */
export function fmt(n: number | null | undefined, dec = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '';
  const s = Math.abs(n).toFixed(dec);
  const [i, d] = s.split('.');
  const ii = i.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return (n < 0 && Number(s) !== 0 ? '-' : '') + ii + (d ? ',' + d : '');
}

/** Lecture d'un nombre saisi (accepte la virgule). */
export function parseNum(s: string | number | null | undefined): number | null {
  if (s === null || s === undefined) return null;
  if (typeof s === 'number') return Number.isFinite(s) ? s : null;
  const t = s.trim().replace(/\s/g, '').replace(',', '.');
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function mm(m: number): string {
  const v = m * 1000;
  return Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : fmt(v, 1);
}

export function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function dateFr(iso: string): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

export function slug(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 60);
}
