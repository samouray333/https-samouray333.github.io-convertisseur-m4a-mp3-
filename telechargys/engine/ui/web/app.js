'use strict';
/* Telechargys : interface (commune ordinateur / téléphone). */

// ---------- jeton et API ----------
const qs = new URLSearchParams(location.search);
if (qs.get('token')) { try { sessionStorage.setItem('ty-token', qs.get('token')); } catch (e) {} history.replaceState(null, '', location.pathname); }
let TOKEN = qs.get('token') || (() => { try { return sessionStorage.getItem('ty-token'); } catch (e) { return ''; } })() || '';

async function api(method, path, body) {
  const r = await fetch('/api/' + path, { method, headers: { 'X-Token': TOKEN, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  let j = null;
  try { j = await r.json(); } catch (e) {}
  if (!r.ok) { const e = new Error((j && j.error) || ('Erreur ' + r.status)); e.status = r.status; e.data = j; throw e; }
  return j;
}

// ---------- pont vers la coque (Electron / Android) ----------
const E = window.tyShell, A = window.TYAndroid;
const shell = {
  desktop: !!E, android: !!A,
  openFile(p) { if (E) E.openFile(p); else if (A) A.openFile(p); else toast('Fichier : ' + p); },
  showInFolder(p) { if (E) E.showInFolder(p); else if (A) A.openFolder(p); },
  share(p) { if (A) A.share(p); },
  async chooseFolder(cur) { return E ? E.chooseFolder(cur || '') : null; },
  openBrowser(u) { if (A) A.openBrowser(u || ''); },
  copy(t) { if (A && A.copy) A.copy(t); else if (E) E.copy(t); else navigator.clipboard && navigator.clipboard.writeText(t).catch(() => {}); toast('Copié dans le presse-papiers'); },
  apply(s) { if (E && E.applySettings) E.applySettings(s); if (A && A.applySettings) A.applySettings(JSON.stringify(s)); },
};

// ---------- utilitaires ----------
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const k in attrs || {}) {
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else if (k in e && k !== 'list') e[k] = v;
    else e.setAttribute(k, v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
const ICONS = {
  plus: 'M12 5v14M5 12h14', play: 'M7 4l13 8-13 8z', pause: 'M8 5v14M16 5v14', trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  playAll: 'M4 4l9 8-9 8zM13 4l9 8-9 8z', stop: 'M6 6h12v12H6z', batch: 'M4 6h16M4 12h16M4 18h10', clock: 'M12 7v5l3 2M12 3a9 9 0 100 18 9 9 0 000-18z',
  spider: 'M12 8a4 4 0 100 8 4 4 0 000-8zM4 4l5 5M20 4l-5 5M4 20l5-5M20 20l-5-5M2 12h6M16 12h6', gear: 'M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M15 4v4M9 10v4M17 16v4',
  search: 'M11 4a7 7 0 100 14 7 7 0 000-14zM16 16l5 5', menu: 'M4 6h16M4 12h16M4 18h16', download: 'M12 3v12M7 10l5 5 5-5M4 20h16',
  gauge: 'M12 13l4-5M4 17a9 9 0 1116 0', x: 'M6 6l12 12M18 6L6 18', folder: 'M3 6h6l2 2h10v11H3z', file: 'M6 3h8l4 4v14H6zM14 3v4h4',
  refresh: 'M4 12a8 8 0 0114-5l2-2v6h-6l2-2a5 5 0 10-1 7', link: 'M10 14a4 4 0 005 0l3-3a4 4 0 00-6-6l-1 1M14 10a4 4 0 00-5 0l-3 3a4 4 0 006 6l1-1',
  info: 'M12 8h.01M11 12h1v5h1M12 3a9 9 0 100 18 9 9 0 000-18z', up: 'M12 19V5M6 11l6-6 6 6', down: 'M12 5v14M6 13l6 6 6-6', share: 'M12 3v12M7 8l5-5 5 5M5 14v6h14v-6',
  globe: 'M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18', check: 'M5 12l5 5 9-10', copy: 'M9 9h11v11H9zM5 15V4h11', queue: 'M4 6h12M4 12h12M4 18h7M19 9v9M16 15l3 3 3-3',
};
function icon(n) { return `<svg class="ic" viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; }
function paintIcons(root) { $$('i[data-i]', root).forEach(i => { i.outerHTML = icon(i.dataset.i); }); }

function fmtSize(n) {
  if (n == null || n < 0) return '?';
  const u = ['o', 'Ko', 'Mo', 'Go', 'To']; let i = 0; let v = n;
  while (v >= 1024 && i < 4) { v /= 1024; i++; }
  return (i === 0 ? v : v.toFixed(v < 10 ? 2 : v < 100 ? 1 : 0)).toString().replace('.', ',') + ' ' + u[i];
}
const fmtSpeed = n => fmtSize(n) + '/s';
function fmtEta(s) {
  if (!isFinite(s) || s < 0) return '';
  s = Math.round(s);
  if (s < 60) return s + ' s';
  if (s < 3600) return Math.floor(s / 60) + ' min ' + (s % 60 ? (s % 60) + ' s' : '');
  if (s < 86400) return Math.floor(s / 3600) + ' h ' + Math.floor(s % 3600 / 60) + ' min';
  return Math.floor(s / 86400) + ' j ' + Math.floor(s % 86400 / 3600) + ' h';
}
function fmtDate(ms) {
  if (!ms) return '';
  const d = new Date(ms), n = new Date();
  const t = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  return d.toDateString() === n.toDateString() ? "Aujourd'hui " + t : d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit' }) + ' ' + t;
}
const STATUS = { queued: 'En attente', downloading: 'En cours', paused: 'En pause', completed: 'Terminé', error: 'Erreur', merging: 'Assemblage' };
const ext = n => { const m = /\.([a-z0-9]{1,5})$/i.exec(n || ''); return m ? m[1].toLowerCase() : ''; };
const isMobile = () => matchMedia('(max-width:860px)').matches;
const sep = () => (S.platform === 'windows' ? '\\' : '/');
const joinPath = (d, f) => d + (d.endsWith('/') || d.endsWith('\\') ? '' : sep()) + f;

function toast(msg, kind, title) {
  const t = h('div', { class: 'toast' + (kind === 'err' ? ' err' : '') }, title ? h('b', {}, title) : null, msg);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 6000 : 3500);
}
const fail = e => toast(e.message || String(e), 'err');
function toastAction(msg, label, fn, title) {
  const b = h('button', { class: 'btn small primary', style: 'margin-top:8px' }, label);
  const t = h('div', { class: 'toast' }, title ? h('b', {}, title) : null, h('div', {}, msg), b);
  b.onclick = () => { t.remove(); fn(); };
  $('#toasts').append(t);
  setTimeout(() => t.remove(), 9000);
}
// Android : propose le lien copié en revenant dans l'appli (comme la surveillance du presse-papiers d'IDM)
let lastClip = (() => { try { return localStorage.getItem('ty-clip') || ''; } catch (e) { return ''; } })();
function checkClipboard() {
  if (!A || document.hidden || !S.version) return;
  let t = ''; try { t = (A.getClipboard() || '').trim(); } catch (e) { return; }
  if (!t || t === lastClip || !/^(https?|ftp):\/\/\S+$/i.test(t)) return;
  lastClip = t; try { localStorage.setItem('ty-clip', t); } catch (e) {}
  if ([...S.dls.values()].some(d => d.url === t) || $('.modal')) return;
  let name = t; try { name = decodeURIComponent(new URL(t).pathname.split('/').pop()) || new URL(t).hostname; } catch (e) {}
  toastAction(name, 'Télécharger', () => openAdd({ url: t }), 'Lien copié détecté');
}
document.addEventListener('visibilitychange', () => setTimeout(checkClipboard, 400));

// ---------- état ----------
const S = { version: '', platform: '', settings: {}, categories: [], queues: [], dls: new Map() };
const V = { filter: 'all', search: '', sort: 'addedAt', dir: -1, sel: new Set(), last: null, hist: new Map(), rows: new Map() };

function pct(d) {
  if (d.status === 'completed') return 100;
  if (d.kind === 'hls' && d.hls && d.hls.total > 0) return Math.min(100, d.hls.done * 100 / d.hls.total);
  if (d.size > 0) return Math.min(100, d.downloaded * 100 / d.size);
  return -1;
}
function eta(d) {
  if (d.status !== 'downloading' || !d.speed) return NaN;
  if (d.kind === 'hls') { const p = pct(d); return p > 0 && d.elapsedMs ? (d.elapsedMs / 1000) * (100 - p) / p : NaN; }
  return d.size > 0 ? (d.size - d.downloaded) / d.speed : NaN;
}
function matches(d) {
  const f = V.filter;
  if (V.search && !(d.fileName + ' ' + d.url).toLowerCase().includes(V.search)) return false;
  if (f === 'all') return true;
  if (f === 'active') return d.status === 'downloading' || d.status === 'merging';
  if (f === 'waiting') return d.status === 'queued' || d.status === 'paused';
  if (f === 'done') return d.status === 'completed';
  if (f === 'error') return d.status === 'error';
  if (f.startsWith('c:')) return d.category === f.slice(2);
  if (f.startsWith('q:')) return d.queue === f.slice(2) && d.status !== 'completed';
  return true;
}
function sortVal(d) {
  switch (V.sort) {
    case 'fileName': return d.fileName.toLowerCase();
    case 'progress': return pct(d);
    case 'eta': { const e = eta(d); return isNaN(e) ? Infinity : e; }
    default: return d[V.sort];
  }
}
function visible() {
  const a = [...S.dls.values()].filter(matches);
  a.sort((x, y) => { const p = sortVal(x), q = sortVal(y); return (p < q ? -1 : p > q ? 1 : x.order - y.order) * V.dir; });
  return a;
}

// ---------- rendu : barre latérale ----------
function counts() {
  const c = { all: 0, active: 0, waiting: 0, done: 0, error: 0 };
  for (const d of S.dls.values()) {
    c.all++;
    if (d.status === 'downloading' || d.status === 'merging') c.active++;
    else if (d.status === 'queued' || d.status === 'paused') c.waiting++;
    else if (d.status === 'completed') c.done++;
    else if (d.status === 'error') c.error++;
    c['c:' + d.category] = (c['c:' + d.category] || 0) + 1;
    if (d.status !== 'completed') c['q:' + d.queue] = (c['q:' + d.queue] || 0) + 1;
  }
  return c;
}
let sideTimer = 0;
function renderSide() { clearTimeout(sideTimer); sideTimer = setTimeout(renderSideNow, 60); }
function renderSideNow() {
  const c = counts();
  const item = (id, label, ic, extra) => h('div', { class: 'nav' + (V.filter === id ? ' on' : ''), onclick: () => setFilter(id), html: icon(ic) }, h('span', {}, label), extra || (c[id] ? h('span', { class: 'n' }, c[id]) : null));
  const side = $('#side');
  side.replaceChildren(
    item('all', 'Tous', 'download'), item('active', 'En cours', 'play'), item('waiting', 'En attente', 'pause'), item('done', 'Terminés', 'check'), item('error', 'Erreurs', 'info'),
    h('h4', {}, 'Catégories', h('button', { title: 'Modifier les catégories', html: icon('gear'), onclick: () => openSettings('cats') })),
    ...S.categories.map(k => item('c:' + k.id, k.name, 'folder')),
    h('h4', {}, 'Files d\'attente', h('button', { title: 'Planificateur', html: icon('clock'), onclick: openQueues })),
    ...S.queues.map(q => item('q:' + q.id, q.name, 'queue', q.running ? h('span', { class: 'run', title: 'File en cours' }) : null)),
  );
  const chip = (id, label) => h('div', { class: 'chip' + (V.filter === id ? ' on' : ''), onclick: () => setFilter(id) }, label + (c[id] ? ' ' + c[id] : ''));
  $('#chips').replaceChildren(chip('all', 'Tous'), chip('active', 'En cours'), chip('waiting', 'En attente'), chip('done', 'Terminés'), chip('error', 'Erreurs'),
    ...S.categories.map(k => chip('c:' + k.id, k.name)), ...S.queues.filter(q => q.id !== 'main').map(q => chip('q:' + q.id, q.name)));
}
function setFilter(f) { V.filter = f; renderSideNow(); renderList(); }

// ---------- rendu : liste ----------
function makeRow(d) {
  const r = h('div', { class: 'row dl' });
  r.dataset.id = d.id;
  r.innerHTML = `<div class="name"><div class="ficon"></div><span></span></div><div class="size"></div>
    <div class="pcell"><div class="prog"><div class="bar"><i></i></div><b></b></div></div>
    <div class="spd"></div><div class="eta"></div><div class="stc"><span class="st"></span></div><div class="date"></div>
    <div class="sub"><span></span><span></span></div><div class="act"><button></button></div>`;
  r._q = {};
  for (const k of ['.ficon', '.name span', '.size', '.bar', '.bar i', '.prog b', '.spd', '.eta', '.st', '.date', '.sub span:first-child', '.sub span:last-child', '.act button']) r._q[k] = $(k, r);
  fillRow(r, d);
  return r;
}
function fillRow(r, d) {
  const q = r._q, p = pct(d), run = d.status === 'downloading';
  const e = ext(d.fileName);
  if (q['.ficon'].textContent !== e) { q['.ficon'].textContent = e; }
  q['.ficon'].className = 'ficon c-' + (['video', 'music', 'archive', 'program', 'document', 'image'].includes(d.category) ? d.category : 'other');
  if (q['.name span'].textContent !== d.fileName) { q['.name span'].textContent = d.fileName; r.title = d.fileName; }
  const size = d.size > 0 ? fmtSize(d.size) : (d.downloaded > 0 ? fmtSize(d.downloaded) : '?');
  q['.size'].textContent = size;
  q['.bar'].className = 'bar' + (d.status === 'paused' || d.status === 'queued' ? ' paused' : d.status === 'error' ? ' error' : '') + ((p < 0 && run) || d.status === 'merging' ? ' ind' : '');
  q['.bar i'].style.width = (p < 0 ? 0 : p) + '%';
  q['.prog b'].textContent = p < 0 ? '' : Math.floor(p) + ' %';
  q['.spd'].textContent = run ? fmtSpeed(d.speed) : '';
  q['.eta'].textContent = run ? fmtEta(eta(d)) : '';
  q['.st'].className = 'st ' + d.status;
  q['.st'].textContent = STATUS[d.status] || d.status;
  q['.st'].title = d.error || '';
  q['.date'].textContent = fmtDate(d.completedAt || d.addedAt);
  q['.sub span:first-child'].textContent = d.status === 'completed' ? size : d.status === 'error' ? (d.error || 'Erreur') : (d.size > 0 ? fmtSize(d.downloaded) + ' / ' + size : fmtSize(d.downloaded)) + (p >= 0 ? ' · ' + Math.floor(p) + ' %' : '');
  q['.sub span:last-child'].textContent = run ? fmtSpeed(d.speed) + (isNaN(eta(d)) ? '' : ' · ' + fmtEta(eta(d))) : STATUS[d.status];
  const ic = d.status === 'downloading' || d.status === 'merging' ? 'pause' : d.status === 'completed' ? 'file' : 'play';
  if (q['.act button'].dataset.ic !== ic) { q['.act button'].dataset.ic = ic; q['.act button'].innerHTML = icon(ic); }
  r.classList.toggle('sel', V.sel.has(d.id));
}
function renderList() {
  const list = $('#list'), vis = visible();
  const frag = document.createDocumentFragment();
  for (const d of vis) {
    let r = V.rows.get(d.id);
    if (!r) { r = makeRow(d); V.rows.set(d.id, r); } else fillRow(r, d);
    frag.append(r);
  }
  list.replaceChildren(frag);
  $('#empty').hidden = vis.length > 0;
  $$('#listHead>div').forEach(e => { e.className = e.dataset.sort === V.sort ? (V.dir > 0 ? 'asc' : 'desc') : ''; });
  for (const id of [...V.sel]) if (!S.dls.has(id)) V.sel.delete(id);
  updateTools();
  renderDetail();
}
let listTimer = 0;
function scheduleList() { clearTimeout(listTimer); listTimer = setTimeout(renderList, 80); }

function upsert(d) {
  const old = S.dls.get(d.id);
  S.dls.set(d.id, d);
  const r = V.rows.get(d.id);
  if (!old || old.status !== d.status || old.category !== d.category || old.queue !== d.queue || old.order !== d.order || !r || !r.isConnected) { scheduleList(); renderSide(); }
  else { fillRow(r, d); if (V.sel.has(d.id)) renderDetail(); }
}

function updateTools() {
  const sel = [...V.sel].map(id => S.dls.get(id)).filter(Boolean);
  const any = k => sel.some(k);
  $('[data-act=resume]').disabled = !any(d => ['paused', 'error', 'queued'].includes(d.status));
  $('[data-act=pause]').disabled = !any(d => ['downloading', 'merging', 'queued'].includes(d.status));
  $('[data-act=remove]').disabled = !sel.length;
}
function updateStatus() {
  let n = 0, sp = 0, w = 0;
  for (const d of S.dls.values()) { if (d.status === 'downloading' || d.status === 'merging') { n++; sp += d.speed || 0; } else if (d.status === 'queued') w++; }
  $('#stActive').textContent = n ? `${n} téléchargement${n > 1 ? 's' : ''} en cours` + (w ? ` · ${w} en attente` : '') : (w ? `${w} en attente` : 'Aucun téléchargement en cours');
  $('#stSpeed').textContent = fmtSpeed(sp);
  const on = S.settings.speedLimitOn && S.settings.speedLimit > 0;
  $('#limitBtn').classList.toggle('on', !!on);
  $('#limitTxt').textContent = on ? 'Limité à ' + fmtSpeed(S.settings.speedLimit) : 'Débit illimité';
  document.title = n ? `${fmtSpeed(sp)} · Telechargys` : 'Telechargys';
}

// ---------- sélection ----------
function select(id, ev) {
  if (ev && (ev.ctrlKey || ev.metaKey)) { V.sel.has(id) ? V.sel.delete(id) : V.sel.add(id); V.last = id; }
  else if (ev && ev.shiftKey && V.last) {
    const ids = visible().map(d => d.id); const a = ids.indexOf(V.last), b = ids.indexOf(id);
    V.sel = new Set(ids.slice(Math.min(a, b), Math.max(a, b) + 1));
  } else { V.sel = new Set([id]); V.last = id; }
  for (const [rid, r] of V.rows) r.classList.toggle('sel', V.sel.has(rid));
  updateTools(); renderDetail();
}
function clearSel() { V.sel.clear(); for (const r of V.rows.values()) r.classList.remove('sel'); updateTools(); renderDetail(); }

// ---------- panneau de détail ----------
function renderDetail() {
  const box = $('#detail');
  const d = V.sel.size === 1 ? S.dls.get([...V.sel][0]) : null;
  $('.scrim')?.remove();
  if (!d) { box.hidden = true; box._id = null; return; }
  if (isMobile()) document.body.append(h('div', { class: 'scrim', onclick: clearSel }));
  const path = joinPath(d.dir, d.fileName);
  const run = d.status === 'downloading' || d.status === 'merging';
  const B = (label, ic, fn, cls) => h('button', { class: 'btn small ' + (cls || ''), onclick: fn, html: icon(ic) }, label);
  const acts = [];
  if (d.status === 'completed') {
    acts.push(B('Ouvrir', 'file', () => shell.openFile(path), 'primary'));
    if (shell.desktop || shell.android) acts.push(B('Dossier', 'folder', () => shell.showInFolder(path)));
    if (shell.android) acts.push(B('Partager', 'share', () => shell.share(path)));
    acts.push(B('Retélécharger', 'refresh', () => act('restart', [d.id])));
  } else {
    if (run || d.status === 'queued') acts.push(B('Pause', 'pause', () => act('pause', [d.id])));
    if (!run) acts.push(B(d.downloaded > 0 ? 'Reprendre' : 'Démarrer', 'play', () => act('start', [d.id]), 'primary'));
    if (d.status === 'paused' || d.status === 'error') acts.push(B('Mettre en file', 'queue', () => act('queue', [d.id])));
    acts.push(B('Actualiser l\'adresse', 'link', () => openRefresh(d)));
  }
  acts.push(B('Propriétés', 'info', () => openProps(d)), B('Supprimer', 'trash', () => confirmRemove([d.id]), 'danger'));
  const p = pct(d);
  const kv = [
    ['État', (STATUS[d.status] || d.status) + (p >= 0 && d.status !== 'completed' ? ` · ${p.toFixed(1).replace('.', ',')} %` : '')],
    ['Taille', d.size > 0 ? `${fmtSize(d.downloaded)} sur ${fmtSize(d.size)}` : fmtSize(d.downloaded) + (d.status === 'completed' ? '' : ' (taille inconnue)')],
    run ? ['Vitesse', fmtSpeed(d.speed) + (isNaN(eta(d)) ? '' : ' · reste ' + fmtEta(eta(d)))] : null,
    run ? ['Connexions', String(d.conns || 0)] : null,
    d.kind === 'hls' && d.hls ? ['Flux vidéo', `${d.hls.done || 0} / ${d.hls.total || '?'} segments` + (d.hls.quality ? ' · ' + d.hls.quality : '')] : null,
    ['Reprise', d.probed ? (d.resumable ? 'Oui' : 'Non : le serveur ne permet pas la reprise') : 'Inconnue'],
    ['Adresse', d.url], ['Dossier', d.dir],
    d.checksum && d.checksum.actual ? [d.checksum.algo.toUpperCase(), d.checksum.actual + (d.checksum.ok === true ? '  ✓ conforme' : d.checksum.ok === false ? '  ✗ différent' : '')] : null,
    d.description ? ['Note', d.description] : null,
  ].filter(Boolean);
  box.hidden = false;
  box.replaceChildren(
    h('div', { class: 'dhead' }, h('h3', {}, d.fileName), h('div', { class: 'dacts' }, acts)),
    h('div', { class: 'dgrid' },
      h('div', {},
        h('dl', { class: 'kv' }, kv.map(([k, v]) => [h('dt', {}, k), h('dd', { title: v }, v)])),
        d.error ? h('div', { class: 'err' }, d.error) : null,
        d.kind !== 'hls' && d.status !== 'completed' ? [h('div', { class: 'cap' }, 'Segments et connexions'), h('canvas', { id: 'segc', height: 26 })] : null),
      run ? h('div', {}, h('div', { class: 'cap' }, 'Vitesse'), h('canvas', { id: 'spdc', height: 90 })) : null));
  box._id = d.id;
  drawDetail(d);
}
function cssv(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function drawDetail(d) {
  const sc = $('#segc');
  if (sc) {
    const w = sc.width = sc.clientWidth * devicePixelRatio, hh = sc.height = 26 * devicePixelRatio, c = sc.getContext('2d');
    c.clearRect(0, 0, w, hh);
    const segs = d.segs || (d.segments || []).map(s => [s.start, s.pos, s.end * 2]);
    if (d.size > 0 && segs.length) {
      for (const [st, pos, e2] of segs) {
        const end = Math.floor(e2 / 2), active = e2 % 2 === 1;
        const x0 = st / d.size * w, x1 = Math.min(pos, end + 1) / d.size * w;
        c.fillStyle = cssv('--accent'); c.fillRect(x0, 0, Math.max(0, x1 - x0), hh);
        if (active) { c.fillStyle = cssv('--warn'); c.fillRect(x1, 0, Math.max(2 * devicePixelRatio, 3), hh); }
        c.fillStyle = cssv('--panel'); c.fillRect(x0, 0, devicePixelRatio, hh);
      }
    } else if (d.size > 0) { c.fillStyle = cssv('--accent'); c.fillRect(0, 0, d.downloaded / d.size * w, hh); }
  }
  const gc = $('#spdc');
  if (gc) {
    const hist = V.hist.get(d.id) || [];
    const w = gc.width = gc.clientWidth * devicePixelRatio, hh = gc.height = 90 * devicePixelRatio, c = gc.getContext('2d');
    c.clearRect(0, 0, w, hh);
    const max = Math.max(1, ...hist) * 1.15, n = 120;
    c.beginPath(); c.moveTo(0, hh);
    hist.forEach((v, i) => c.lineTo((i + n - hist.length) / (n - 1) * w, hh - v / max * hh));
    c.lineTo(w, hh); c.closePath();
    c.fillStyle = cssv('--accent-soft'); c.fill();
    c.beginPath();
    hist.forEach((v, i) => { const x = (i + n - hist.length) / (n - 1) * w, y = hh - v / max * hh; i ? c.lineTo(x, y) : c.moveTo(x, y); });
    c.strokeStyle = cssv('--accent'); c.lineWidth = 2 * devicePixelRatio; c.stroke();
    c.fillStyle = cssv('--mute'); c.font = `${11 * devicePixelRatio}px system-ui`; c.fillText('max ' + fmtSpeed(Math.max(0, ...hist)), 6 * devicePixelRatio, 14 * devicePixelRatio);
  }
}

// ---------- actions ----------
async function act(action, ids, extra) {
  try {
    if (ids.length === 1 && ['restart', 'queue'].includes(action)) await api('POST', `downloads/${ids[0]}/${action}`, extra || {});
    else if (action === 'queue') for (const id of ids) await api('POST', `downloads/${id}/queue`, {});
    else await api('POST', 'actions', { action, ids, ...(extra || {}) });
  } catch (e) { fail(e); }
}
function selIds() { return [...V.sel]; }
function confirmRemove(ids) {
  if (!ids.length) return;
  const ds = ids.map(i => S.dls.get(i)).filter(Boolean);
  const done = ds.some(d => d.status === 'completed');
  const chk = h('input', { type: 'checkbox' });
  modal({
    title: ids.length > 1 ? `Supprimer ${ids.length} téléchargements ?` : 'Supprimer ce téléchargement ?',
    body: [h('p', {}, ids.length > 1 ? 'Ils seront retirés de la liste.' : ds[0] ? ds[0].fileName : ''),
      done ? h('label', { class: 'check' }, chk, 'Supprimer aussi les fichiers terminés du disque') : h('p', { class: 'hint' }, 'Les fichiers partiels seront effacés.')],
    ok: 'Supprimer', danger: true,
    onok: async () => { await act('remove', ids, { deleteFile: chk.checked }); V.sel.clear(); },
  });
}
const ACTIONS = {
  add: () => openAdd(), resume: () => act('start', selIds()), pause: () => act('pause', selIds()), remove: () => confirmRemove(selIds()),
  startAll: () => act('startAll', []), pauseAll: () => act('pauseAll', []), batch: () => openBatch(), grab: () => openGrab(), queues: () => openQueues(),
  settings: () => openSettings(), browser: () => shell.openBrowser(''), menu: ev => openMenu(ev),
};
function openMenu() {
  showCtx([
    ['Rechercher', 'search', () => { $('#top').classList.add('searching'); $('#search').focus(); }],
    ['Tout démarrer', 'playAll', ACTIONS.startAll], ['Tout arrêter', 'stop', ACTIONS.pauseAll], null,
    shell.android ? ['Navigateur intégré', 'globe', ACTIONS.browser] : null,
    ['Téléchargement par lot', 'batch', ACTIONS.batch], ['Aspirateur de site', 'spider', ACTIONS.grab], ['Files et planificateur', 'clock', ACTIONS.queues], null,
    ['Effacer les terminés de la liste', 'trash', () => act('removeCompleted', [])], ['Réglages', 'gear', ACTIONS.settings],
  ], innerWidth - 240, 50);
}
function showCtx(items, x, y) {
  const c = $('#ctx');
  c.replaceChildren(...items.filter(i => i !== undefined && i !== false).map(i => i === null ? h('hr') : h('button', { class: i[3] || '', html: icon(i[1]), onclick: () => { hideCtx(); i[2](); } }, i[0])));
  c.hidden = false;
  const r = c.getBoundingClientRect();
  c.style.left = Math.max(6, Math.min(x, innerWidth - r.width - 6)) + 'px';
  c.style.top = Math.max(6, Math.min(y, innerHeight - r.height - 6)) + 'px';
}
function hideCtx() { $('#ctx').hidden = true; }
function rowMenu(d, x, y) {
  const ids = selIds(), path = joinPath(d.dir, d.fileName), done = d.status === 'completed';
  showCtx([
    done ? ['Ouvrir', 'file', () => shell.openFile(path)] : null,
    done && (shell.desktop || shell.android) ? ['Ouvrir le dossier', 'folder', () => shell.showInFolder(path)] : false,
    done && shell.android ? ['Partager', 'share', () => shell.share(path)] : false,
    !done ? ['Reprendre', 'play', () => act('start', ids)] : false,
    !done ? ['Pause', 'pause', () => act('pause', ids)] : false,
    !done ? ['Mettre en file d\'attente', 'queue', () => act('queue', ids)] : false,
    null,
    ['Retélécharger', 'refresh', () => act('restart', [d.id])],
    !done ? ['Actualiser l\'adresse…', 'link', () => openRefresh(d)] : false,
    ['Copier l\'adresse', 'copy', () => shell.copy(ids.length > 1 ? ids.map(i => (S.dls.get(i) || {}).url).filter(Boolean).join('\n') : d.url)],
    ids.length > 1 ? ['Exporter ces adresses (.txt)', 'download', () => saveExport('export.txt?ids=' + ids.join(','), 'telechargys-adresses.txt')] : false,
    !done ? ['Monter dans la file', 'up', () => api('POST', `downloads/${d.id}/move`, { dir: -1 }).catch(fail)] : false,
    !done ? ['Descendre dans la file', 'down', () => api('POST', `downloads/${d.id}/move`, { dir: 1 }).catch(fail)] : false,
    ['Propriétés…', 'info', () => openProps(d)], null,
    ['Supprimer', 'trash', () => confirmRemove(ids), 'danger'],
  ].filter((v, i, a) => !(v === null && (i === 0 || a[i - 1] === null))), x, y);
}

// ---------- fenêtres ----------
function modal({ title, body, ok, onok, cancel, danger, wide, extra, onclose }) {
  const m = h('div', { class: 'modal' });
  const close = () => { m.remove(); onclose && onclose(); };
  const okBtn = ok ? h('button', { class: 'btn primary' + (danger ? ' dangerbg' : '') }, ok) : null;
  if (okBtn) okBtn.onclick = async () => {
    okBtn.disabled = true;
    try { const r = await onok(); if (r !== false) close(); } catch (e) { fail(e); }
    okBtn.disabled = false;
  };
  const d = h('div', { class: 'dlg' + (wide ? ' wide' : '') },
    h('header', {}, h('h2', {}, title), h('button', { class: 'x', html: icon('x'), onclick: close })),
    h('div', { class: 'c' }, body),
    h('footer', {}, extra || null, h('button', { class: 'btn', onclick: close }, cancel || (ok ? 'Annuler' : 'Fermer')), okBtn));
  m.append(d);
  m.addEventListener('mousedown', e => { if (e.target === m) close(); });
  m.addEventListener('keydown', e => { if (e.key === 'Escape') close(); if (e.key === 'Enter' && okBtn && e.target.tagName !== 'TEXTAREA' && !e.target.closest('.noenter')) { e.preventDefault(); okBtn.click(); } });
  $('#modals').append(m);
  setTimeout(() => { const f = $('[autofocus]', m) || $('input,textarea,select', m); f && !isMobile() && f.focus(); }, 30);
  m.close = close; m.okBtn = okBtn;
  return m;
}
const F = (label, el, hint) => h('div', { class: 'field' }, h('label', {}, label), el, hint ? h('div', { class: 'hint', style: 'margin:0' }, hint) : null);
const I = (attrs) => h('input', { class: 'in', ...attrs });
const Sel = (opts, val) => { const s = h('select', { class: 'in' }, opts.map(([v, t]) => h('option', { value: v }, t))); s.value = val; return s; };
function folderField(input) {
  if (!shell.desktop) return input;
  return h('div', { class: 'inbtn' }, input, h('button', { class: 'btn', type: 'button', html: icon('folder'), title: 'Choisir un dossier', onclick: async () => { const p = await shell.chooseFolder(input.value); if (p) { input.value = p; input.dispatchEvent(new Event('input')); } } }));
}
function limitField(bytes) {
  const n = I({ type: 'number', min: 0, step: 'any', placeholder: 'illimité', value: bytes > 0 ? +(bytes / 1024 >= 1024 ? (bytes / 1048576).toFixed(2) : (bytes / 1024).toFixed(0)) : '' });
  const u = Sel([['1024', 'Ko/s'], ['1048576', 'Mo/s']], bytes >= 1048576 ? '1048576' : '1024');
  const el = h('div', { class: 'inbtn' }, n, u);
  u.style.width = '96px'; u.style.flex = 'none';
  el.val = () => Math.round((parseFloat(n.value.replace(',', '.')) || 0) * +u.value);
  return el;
}

// ---------- évènements serveur ----------
function onEvent(ev) {
  const d = ev.data;
  switch (ev.type) {
    case 'download': upsert(d); updateStatus(); break;
    case 'progress':
      for (const p of d) {
        const x = S.dls.get(p.id); if (!x) continue;
        x.downloaded = p.downloaded; x.speed = p.speed; x.size = p.size; x.conns = p.conns; x.segs = p.segs; x.status = p.status; x.elapsedMs = (x.elapsedMs || 0) + 500;
        if (x.hls && p.hlsTotal) { x.hls.done = p.hlsDone; x.hls.total = p.hlsTotal; }
        let hst = V.hist.get(p.id); if (!hst) V.hist.set(p.id, hst = []);
        hst.push(p.speed); if (hst.length > 120) hst.shift();
        const r = V.rows.get(p.id); if (r && r.isConnected) fillRow(r, x);
        if ($('#detail')._id === p.id) { drawDetail(x); const dd = $$('#detail .kv dd'); if (dd[0]) { const pc = pct(x); dd[0].textContent = STATUS[x.status] + (pc >= 0 ? ` · ${pc.toFixed(1).replace('.', ',')} %` : ''); dd[1].textContent = x.size > 0 ? `${fmtSize(x.downloaded)} sur ${fmtSize(x.size)}` : fmtSize(x.downloaded); if (dd[2] && x.status === 'downloading') { dd[2].textContent = fmtSpeed(x.speed) + (isNaN(eta(x)) ? '' : ' · reste ' + fmtEta(eta(x))); if (dd[3]) dd[3].textContent = String(x.conns || 0); } } }
      }
      updateStatus(); break;
    case 'removed': S.dls.delete(d); V.rows.delete(d); V.sel.delete(d); V.hist.delete(d); scheduleList(); renderSide(); updateStatus(); break;
    case 'settings': S.settings = d; applyTheme(); updateStatus(); break;
    case 'categories': S.categories = d; renderSide(); break;
    case 'queues': S.queues = d; renderSide(); break;
    case 'notify':
      toast(d.body, d.kind === 'error' ? 'err' : '', d.title);
      if (d.kind === 'done' && S.settings.soundDone && !shell.android) beep();
      break;
    case 'queueDone': toast(`La file « ${d.name} » est terminée.`); break;
    case 'capture': openAdd(d); break;
    case 'captureBatch': openBatch((d.urls || []).join('\n'), d); break;
    case 'refreshed': {
      const fm = $$('.modal').find(x => x.dataset.refresh === d.id);
      if (fm) { delete fm.dataset.refresh; fm.close(); }
      toast('Nouvelle adresse récupérée, le téléchargement reprend.', '', 'Lien actualisé');
      break;
    }
    case 'pair': openPair(d); break;
    case 'pairEnd': $$('.modal').forEach(m => m.dataset.pair === d && m.remove()); break;
    case 'reload': load(); break;
  }
}
function beep() {
  try {
    const a = new AudioContext(), t = a.currentTime;
    [660, 880].forEach((f, i) => { const o = a.createOscillator(), g = a.createGain(); o.frequency.value = f; o.connect(g); g.connect(a.destination); g.gain.setValueAtTime(.12, t + i * .14); g.gain.exponentialRampToValueAtTime(.001, t + i * .14 + .25); o.start(t + i * .14); o.stop(t + i * .14 + .26); });
    setTimeout(() => a.close(), 900);
  } catch (e) {}
}
function openPair(p) {
  const m = modal({
    title: 'Autoriser l\'extension du navigateur ?',
    body: h('p', {}, `« ${p.name || 'Extension Telechargys'} » demande à envoyer des téléchargements à Telechargys. N'accepte que si tu viens d'installer l'extension.`),
    ok: 'Autoriser', onok: () => api('POST', 'pair/' + p.id, { approve: true }), cancel: 'Refuser',
    onclose: () => api('POST', 'pair/' + p.id, { approve: false }).catch(() => {}),
  });
  m.dataset.pair = p.id;
}
function applyTheme() {
  const t = S.settings.theme || 'auto';
  const sysDark = typeof window.tySystemDark === 'boolean' ? window.tySystemDark : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = t === 'auto' ? (sysDark ? 'dark' : 'light') : t;
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);

let es;
function connect() {
  if (es) es.close();
  es = new EventSource('/api/events?token=' + encodeURIComponent(TOKEN));
  es.onmessage = m => { try { onEvent(JSON.parse(m.data)); } catch (e) { console.error(e); } };
  es.onerror = () => { es.close(); setTimeout(() => load().catch(() => setTimeout(connect, 2000)), 1500); };
}
async function load() {
  const st = await api('GET', 'state');
  S.version = st.version; S.platform = st.platform; S.settings = st.settings; S.categories = st.categories; S.queues = st.queues;
  S.dls = new Map((st.downloads || []).map(d => [d.id, d]));
  V.rows.clear();
  document.body.classList.toggle('android', S.platform === 'android');
  applyTheme(); renderSideNow(); renderList(); updateStatus(); connect();
  setTimeout(checkClipboard, 800);
}

// ---------- interactions globales ----------
function initUI() {
  paintIcons(document);
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-act]');
    if (b && !b.disabled) ACTIONS[b.dataset.act](e);
    if (!e.target.closest('#ctx') && !e.target.closest('[data-act=menu]')) hideCtx();
  });
  const list = $('#list');
  list.addEventListener('click', e => {
    const r = e.target.closest('.dl');
    if (!r) { if (!isMobile()) clearSel(); return; }
    const d = S.dls.get(r.dataset.id);
    if (e.target.closest('.act')) {
      if (d.status === 'downloading' || d.status === 'merging') act('pause', [d.id]);
      else if (d.status === 'completed') shell.openFile(joinPath(d.dir, d.fileName));
      else act('start', [d.id]);
      return;
    }
    select(r.dataset.id, e);
  });
  list.addEventListener('dblclick', e => {
    const r = e.target.closest('.dl'); if (!r) return;
    const d = S.dls.get(r.dataset.id);
    d.status === 'completed' ? shell.openFile(joinPath(d.dir, d.fileName)) : openProps(d);
  });
  list.addEventListener('contextmenu', e => {
    const r = e.target.closest('.dl'); if (!r) return;
    e.preventDefault();
    if (!V.sel.has(r.dataset.id)) select(r.dataset.id);
    rowMenu(S.dls.get(r.dataset.id), e.clientX, e.clientY);
  });
  $('#listHead').addEventListener('click', e => {
    const k = e.target.dataset.sort; if (!k) return;
    if (V.sort === k) V.dir = -V.dir; else { V.sort = k; V.dir = k === 'fileName' ? 1 : -1; }
    renderList();
  });
  $('#search').addEventListener('input', e => { V.search = e.target.value.trim().toLowerCase(); renderList(); });
  $('#search').addEventListener('blur', e => { if (!e.target.value) $('#top').classList.remove('searching'); });
  $('#limitBtn').addEventListener('click', openLimit);
  document.addEventListener('keydown', e => {
    if (e.target.closest('input,textarea,select') || $('.modal')) return;
    if (e.key === 'Delete') confirmRemove(selIds());
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); openAdd(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); V.sel = new Set(visible().map(d => d.id)); renderList(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); $('#search').focus(); }
    else if (e.key === 'Escape') clearSel();
    else if (e.key === ' ' && V.sel.size) { e.preventDefault(); const d = S.dls.get(selIds()[0]); act(d.status === 'downloading' ? 'pause' : 'start', selIds()); }
  });
  document.addEventListener('paste', e => {
    if (e.target.closest('input,textarea') || $('.modal')) return;
    const t = (e.clipboardData.getData('text') || '').trim();
    if (/^(https?|ftp):\/\//i.test(t)) t.split(/\s+/).length > 1 ? openBatch(t) : openAdd({ url: t });
  });
  // glisser-déposer de liens
  let depth = 0;
  addEventListener('dragenter', e => { if ([...e.dataTransfer.types].some(t => t === 'text/uri-list' || t === 'text/plain')) { depth++; $('#drop').hidden = false; } });
  addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; $('#drop').hidden = true; } });
  addEventListener('dragover', e => e.preventDefault());
  addEventListener('drop', e => {
    e.preventDefault(); depth = 0; $('#drop').hidden = true;
    const t = (e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain') || '').split(/\r?\n/).filter(l => /^(https?|ftp):\/\//i.test(l.trim()));
    if (t.length === 1) openAdd({ url: t[0].trim() }); else if (t.length) openBatch(t.join('\n'));
  });
  addEventListener('resize', () => { const d = S.dls.get($('#detail')._id); if (d) drawDetail(d); });
}
// appelé par les coques (lien reçu, presse-papiers...)
window.tyAddUrl = (url, extra) => {
  const fm = $$('.modal').find(x => x.dataset.refresh); // fenêtre « Actualiser l'adresse » ouverte : ce lien la remplit
  if (fm) {
    const id = fm.dataset.refresh;
    api('POST', `downloads/${id}/refresh`, { url }).then(() => api('POST', `downloads/${id}/start`, {}))
      .then(() => { delete fm.dataset.refresh; fm.close(); toast('Le téléchargement reprend.', '', 'Lien actualisé'); }).catch(fail);
    return;
  }
  openAdd({ url, ...(extra || {}) });
};
window.tyAddUrls = list => (list.length === 1 ? window.tyAddUrl(list[0]) : openBatch(list.join('\n')));
// bouton Retour d'Android : ferme ce qui est ouvert, sinon laisse l'appli passer en arrière-plan
window.tyBack = () => {
  const ms = $$('.modal');
  if (ms.length) { ms[ms.length - 1].close(); return true; }
  if (!$('#ctx').hidden) { hideCtx(); return true; }
  if (V.sel.size) { clearSel(); return true; }
  if ($('#top').classList.contains('searching')) { $('#search').value = ''; V.search = ''; $('#top').classList.remove('searching'); renderList(); return true; }
  return false;
};
window.applyTheme = applyTheme;

initUI();
load().catch(e => { document.body.innerHTML = '<p style="padding:30px;font-size:16px">Connexion au moteur impossible : ' + e.message + '</p>'; });
