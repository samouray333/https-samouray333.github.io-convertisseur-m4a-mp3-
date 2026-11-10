'use strict';
/* Telechargys : fenêtre de progression et fenêtre « Téléchargement terminé » (ordinateur). */
const q = new URLSearchParams(location.search);
const TOKEN = q.get('token'), ID = q.get('id'), VIEW = q.get('view') || 'progress';
const E = window.tyShell;
const $ = s => document.querySelector(s);
let d = null, details = true, hist = [];

async function api(method, path, body) {
  const r = await fetch('/api/' + path, { method, headers: { 'X-Token': TOKEN, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => null);
  if (!r.ok) throw new Error((j && j.error) || 'Erreur ' + r.status);
  return j;
}
function fmtSize(n) { if (n == null || n < 0) return '?'; const u = ['o', 'Ko', 'Mo', 'Go', 'To']; let i = 0, v = n; while (v >= 1024 && i < 4) { v /= 1024; i++; } return (i ? v.toFixed(v < 10 ? 2 : v < 100 ? 1 : 0) : v).toString().replace('.', ',') + ' ' + u[i]; }
function fmtEta(s) { if (!isFinite(s) || s < 0) return '—'; s = Math.round(s); if (s < 60) return s + ' s'; if (s < 3600) return Math.floor(s / 60) + ' min ' + (s % 60) + ' s'; return Math.floor(s / 3600) + ' h ' + Math.floor(s % 3600 / 60) + ' min'; }
const ext = n => ((/\.([a-z0-9]{1,5})$/i.exec(n || '') || [])[1] || '').toLowerCase();
const sep = p => (p.includes('\\') ? '\\' : '/');
const full = () => d.dir + (d.dir.endsWith(sep(d.dir)) ? '' : sep(d.dir)) + d.fileName;
function pct() {
  if (d.status === 'completed') return 100;
  if (d.kind === 'hls' && d.hls && d.hls.total) return d.hls.done * 100 / d.hls.total;
  return d.size > 0 ? d.downloaded * 100 / d.size : -1;
}
function eta() {
  if (d.status !== 'downloading' || !d.speed) return NaN;
  const p = pct();
  if (d.kind === 'hls') return p > 0 && d.elapsedMs ? d.elapsedMs / 1000 * (100 - p) / p : NaN;
  return d.size > 0 ? (d.size - d.downloaded) / d.speed : NaN;
}
const STATUS = { queued: 'En attente', downloading: 'Téléchargement en cours', paused: 'En pause', completed: 'Terminé', error: 'Erreur', merging: 'Assemblage de la vidéo…' };
const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function h(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; }
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function render() {
  const pw = $('#pw');
  if (VIEW === 'done') {
    document.title = 'Téléchargement terminé';
    pw.innerHTML = `
      <h1><span class="okicon"><svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></svg></span><span>Téléchargement terminé</span></h1>
      <dl class="kv"><dt>Fichier</dt><dd title="${esc(d.fileName)}">${esc(d.fileName)}</dd><dt>Taille</dt><dd>${fmtSize(d.size)}</dd><dt>Adresse</dt><dd title="${esc(d.url)}">${esc(d.url)}</dd></dl>
      <div class="path">${esc(full())}</div>
      <label class="check"><input type="checkbox" id="never"> Ne plus afficher cette fenêtre</label>
      <div class="btns"><button class="btn primary" id="open">Ouvrir</button><button class="btn" id="folder">Ouvrir le dossier</button><button class="btn" id="close">Fermer</button></div>`;
    const close = async () => { if ($('#never').checked) await api('PUT', 'settings', { showDoneWin: false }).catch(() => {}); window.close(); };
    $('#open').onclick = () => { E && E.openFile(full()); close(); };
    $('#folder').onclick = () => { E && E.showInFolder(full()); close(); };
    $('#close').onclick = close;
    addEventListener('keydown', e => { if (e.key === 'Escape') close(); if (e.key === 'Enter') $('#open').click(); });
    return;
  }
  pw.innerHTML = `
    <h1><span class="ficon"></span><span id="name"></span></h1>
    <div class="big"><div class="bar" id="bar"><i></i></div><b id="pct"></b></div>
    <dl class="kv" id="kv"></dl>
    <div id="det"><div class="cap">Connexions et segments</div><canvas id="seg"></canvas><div class="cap">Vitesse</div><canvas id="spd" style="height:44px"></canvas></div>
    <div class="err" id="err"></div>
    <div class="btns"><button class="btn small lft" id="toggle">Masquer les détails</button><button class="btn" id="pp"></button><button class="btn" id="cancel">Fermer</button></div>`;
  $('#toggle').onclick = () => { details = !details; $('#det').hidden = !details; $('#toggle').textContent = details ? 'Masquer les détails' : 'Afficher les détails'; E && E.resizeProgress && E.resizeProgress(details); };
  $('#pp').onclick = async () => {
    try {
      if (d.status === 'downloading' || d.status === 'queued' || d.status === 'merging') await api('POST', `downloads/${ID}/pause`, {});
      else await api('POST', `downloads/${ID}/start`, {});
    } catch (e) { $('#err').textContent = e.message; }
  };
  $('#cancel').onclick = () => window.close();
  addEventListener('keydown', e => { if (e.key === 'Escape') window.close(); });
  update();
}
function update() {
  if (VIEW === 'done' || !$('#bar')) return;
  const p = pct(), run = d.status === 'downloading';
  const ic = $('.ficon'); ic.textContent = ext(d.fileName); ic.className = 'ficon c-' + (['video', 'music', 'archive', 'program', 'document', 'image'].includes(d.category) ? d.category : 'other');
  $('#name').textContent = d.fileName; $('#name').title = d.fileName;
  document.title = (p >= 0 ? Math.floor(p) + ' % · ' : '') + d.fileName;
  $('#bar').className = 'bar' + (d.status === 'paused' ? ' paused' : d.status === 'error' ? ' error' : '') + ((p < 0 && run) || d.status === 'merging' ? ' ind' : '');
  $('#bar i').style.width = (p < 0 ? 0 : p) + '%';
  $('#pct').textContent = p < 0 ? '' : p.toFixed(1).replace('.', ',') + ' %';
  const rows = [
    ['État', STATUS[d.status] || d.status],
    ['Taille', d.size > 0 ? fmtSize(d.size) : (d.kind === 'hls' ? 'flux vidéo' : 'inconnue')],
    ['Téléchargé', fmtSize(d.downloaded) + (d.kind === 'hls' && d.hls && d.hls.total ? ` · ${d.hls.done}/${d.hls.total} segments` : '')],
    ['Vitesse', run ? fmtSize(d.speed) + '/s' : '—'],
    ['Temps restant', run ? fmtEta(eta()) : '—'],
    ['Reprise', d.probed ? (d.resumable ? 'Oui' : 'Non') : '…'],
    ['Adresse', d.url],
  ];
  $('#kv').innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd title="${esc(v)}">${esc(v)}</dd>`).join('');
  $('#pp').textContent = d.status === 'downloading' || d.status === 'queued' || d.status === 'merging' ? 'Pause' : (d.status === 'error' ? 'Réessayer' : 'Reprendre');
  $('#pp').className = 'btn' + (d.status === 'paused' || d.status === 'error' ? ' primary' : '');
  $('#err').textContent = d.status === 'error' ? d.error : '';
  draw();
}
function draw() {
  const sc = $('#seg'); if (!sc || !details) return;
  const dpr = devicePixelRatio, w = sc.width = sc.clientWidth * dpr, hh = sc.height = 22 * dpr, c = sc.getContext('2d');
  c.clearRect(0, 0, w, hh);
  const segs = d.segs || (d.segments || []).map(s => [s.start, s.pos, s.end * 2]);
  if (d.kind === 'hls' && d.hls && d.hls.total) { c.fillStyle = cssv('--accent'); c.fillRect(0, 0, d.hls.done / d.hls.total * w, hh); }
  else if (d.size > 0) for (const [st, pos, e2] of segs) {
    const end = Math.floor(e2 / 2), x0 = st / d.size * w, x1 = Math.min(pos, end + 1) / d.size * w;
    c.fillStyle = cssv('--accent'); c.fillRect(x0, 0, Math.max(0, x1 - x0), hh);
    if (e2 % 2) { c.fillStyle = cssv('--warn'); c.fillRect(x1, 0, 3 * dpr, hh); }
    c.fillStyle = cssv('--panel'); c.fillRect(x0, 0, dpr, hh);
  }
  const gc = $('#spd'), gw = gc.width = gc.clientWidth * dpr, gh = gc.height = 44 * dpr, g = gc.getContext('2d');
  g.clearRect(0, 0, gw, gh);
  const max = Math.max(1, ...hist) * 1.15, n = 120;
  g.beginPath(); hist.forEach((v, i) => { const x = (i + n - hist.length) / (n - 1) * gw, y = gh - v / max * gh; i ? g.lineTo(x, y) : g.moveTo(x, y); });
  g.strokeStyle = cssv('--accent'); g.lineWidth = 2 * dpr; g.stroke();
}

async function start() {
  const theme = (await api('GET', 'state').catch(() => ({ settings: {} }))).settings.theme || 'auto';
  document.documentElement.dataset.theme = theme === 'auto' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme;
  const st = await api('GET', 'state');
  d = st.downloads.find(x => x.id === ID);
  if (!d) { window.close(); return; }
  render();
  if (VIEW === 'done') return;
  const es = new EventSource('/api/events?token=' + encodeURIComponent(TOKEN));
  es.onmessage = m => {
    const ev = JSON.parse(m.data);
    if (ev.type === 'download' && ev.data.id === ID) { d = ev.data; update(); }
    else if (ev.type === 'removed' && ev.data === ID) window.close();
    else if (ev.type === 'progress') for (const p of ev.data) if (p.id === ID) {
      Object.assign(d, { downloaded: p.downloaded, speed: p.speed, size: p.size, segs: p.segs, status: p.status, elapsedMs: (d.elapsedMs || 0) + 500 });
      if (d.hls && p.hlsTotal) { d.hls.done = p.hlsDone; d.hls.total = p.hlsTotal; }
      hist.push(p.speed); if (hist.length > 120) hist.shift();
      update();
    }
  };
}
start();
