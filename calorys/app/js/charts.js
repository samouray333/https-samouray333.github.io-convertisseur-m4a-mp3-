/* Calorys : petits graphiques SVG sans dépendance. */
(function () {
  'use strict';
  const W = 640;

  function ring(pct, size, stroke, cls) {
    const r = (size - stroke) / 2, c = 2 * Math.PI * r;
    const p = Math.max(0, Math.min(1, pct));
    return `<svg class="ring ${cls || ''}" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">
      <circle class="ring-bg" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}" fill="none"/>
      <circle class="ring-fg" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}" fill="none"
        stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - p)}" stroke-linecap="round"
        transform="rotate(-90 ${size / 2} ${size / 2})"/></svg>`;
  }

  /* bars : [{label, value, title}], goal : ligne horizontale optionnelle. */
  function bars(data, goal, opts) {
    opts = opts || {};
    const H = 220, pad = { l: 44, r: 8, t: 12, b: 26 };
    const max = Math.max(goal || 0, ...data.map(d => d.value), 1) * 1.1;
    const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    const bw = iw / data.length;
    const y = v => pad.t + ih - (v / max) * ih;
    const ticks = niceTicks(max, 4);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${opts.label || ''}">`;
    for (const t of ticks) s += `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(t)}" y2="${y(t)}"/><text class="axis" x="${pad.l - 6}" y="${y(t) + 4}" text-anchor="end">${fmt(t)}</text>`;
    const every = Math.ceil(data.length / 10);
    data.forEach((d, i) => {
      const h = Math.max(0, ih - (y(d.value) - pad.t));
      const over = goal && d.value > goal * 1.05;
      const x = pad.l + i * bw + bw * 0.18;
      s += `<rect class="cbar ${over ? 'over' : ''} ${d.value ? '' : 'empty'}" x="${x}" y="${y(d.value)}" width="${bw * 0.64}" height="${h}" rx="${Math.min(6, bw * 0.2)}"><title>${d.title || d.value}</title></rect>`;
      if (i % every === 0) s += `<text class="axis" x="${pad.l + i * bw + bw / 2}" y="${H - 8}" text-anchor="middle">${d.label}</text>`;
    });
    if (goal) s += `<line class="goal" x1="${pad.l}" x2="${W - pad.r}" y1="${y(goal)}" y2="${y(goal)}"/><text class="goal-label" x="${W - pad.r}" y="${y(goal) - 5}" text-anchor="end">objectif ${fmt(goal)}</text>`;
    return s + '</svg>';
  }

  /* points : [{x: timestamp, y}], target : ligne cible optionnelle. */
  function line(points, target, opts) {
    opts = opts || {};
    const H = 220, pad = { l: 44, r: 12, t: 14, b: 26 };
    if (!points.length) return '';
    const trend = opts.trend || null;
    const ys = points.map(p => p.y).concat(target ? [target] : [], trend ? trend.map(p => p.y) : []);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    const span = Math.max(hi - lo, 2);
    lo -= span * 0.15; hi += span * 0.15;
    const x0 = points[0].x, x1 = points[points.length - 1].x === x0 ? x0 + 1 : points[points.length - 1].x;
    const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    const X = x => pad.l + (x - x0) / (x1 - x0) * iw;
    const Y = v => pad.t + ih - (v - lo) / (hi - lo) * ih;
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${opts.label || ''}">`;
    const step = (hi - lo) / 4;
    for (let i = 0; i <= 4; i++) { const v = lo + step * i; s += `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${pad.l - 6}" y="${Y(v) + 4}" text-anchor="end">${v.toFixed(1).replace('.', ',')}</text>`; }
    if (target) s += `<line class="goal" x1="${pad.l}" x2="${W - pad.r}" y1="${Y(target)}" y2="${Y(target)}"/><text class="goal-label" x="${W - pad.r}" y="${Y(target) - 5}" text-anchor="end">objectif ${String(target).replace('.', ',')}</text>`;
    const d = points.map((p, i) => (i ? 'L' : 'M') + X(p.x).toFixed(1) + ' ' + Y(p.y).toFixed(1)).join(' ');
    const area = d + ` L${X(points[points.length - 1].x).toFixed(1)} ${pad.t + ih} L${X(x0).toFixed(1)} ${pad.t + ih} Z`;
    if (trend && trend.length) {
      // Pesées brutes en points discrets, tendance lissée (moyenne mobile exponentielle) en trait plein.
      const td = trend.map((p, i) => (i ? 'L' : 'M') + X(p.x).toFixed(1) + ' ' + Y(p.y).toFixed(1)).join(' ');
      const ta = td + ` L${X(trend[trend.length - 1].x).toFixed(1)} ${pad.t + ih} L${X(trend[0].x).toFixed(1)} ${pad.t + ih} Z`;
      s += `<path class="area" d="${ta}"/><path class="raw" d="${d}"/><path class="line" d="${td}"/>`;
      points.forEach(p => { s += `<circle class="dot raw-dot" cx="${X(p.x)}" cy="${Y(p.y)}" r="3"><title>${p.title || p.y}</title></circle>`; });
    } else {
      s += `<path class="area" d="${area}"/><path class="line" d="${d}"/>`;
      points.forEach(p => { s += `<circle class="dot" cx="${X(p.x)}" cy="${Y(p.y)}" r="4"><title>${p.title || p.y}</title></circle>`; });
    }
    const lab = [points[0], points[Math.floor(points.length / 2)], points[points.length - 1]];
    const seen = new Set();
    lab.forEach(p => { if (seen.has(p.x)) return; seen.add(p.x); s += `<text class="axis" x="${X(p.x)}" y="${H - 8}" text-anchor="middle">${new Date(p.x).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}</text>`; });
    return s + '</svg>';
  }

  /* Anneau des macros : parts [{value, cls}]. */
  function donut(parts, size) {
    const total = parts.reduce((a, p) => a + p.value, 0) || 1;
    const r = size / 2 - 10, c = 2 * Math.PI * r;
    let off = 0, s = `<svg class="donut" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true"><circle class="ring-bg" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="16" fill="none"/>`;
    for (const p of parts) {
      const len = c * p.value / total;
      if (len > 0) s += `<circle class="${p.cls}" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="16" fill="none" stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-off}" transform="rotate(-90 ${size / 2} ${size / 2})"/>`;
      off += len;
    }
    return s + '</svg>';
  }

  function niceTicks(max, n) {
    const raw = max / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
    const out = [];
    for (let v = 0; v <= max; v += step) out.push(v);
    return out;
  }

  function fmt(v) { return Math.round(v).toLocaleString('fr-FR'); }

  window.Charts = { ring, bars, line, donut };
})();
