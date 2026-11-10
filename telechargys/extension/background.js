// Telechargys : extension navigateur (capture des téléchargements, menu contextuel, détection des vidéos).
const api = typeof browser !== 'undefined' ? browser : chrome;
const PORTS = Array.from({ length: 10 }, (_, i) => 47615 + i);
let conn = null;      // { port, token }
let appSettings = null;
let media = {};       // tabId -> [{url, type, size, title}]
const SKIP_HOSTS = /(^|\.)(youtube\.com|googlevideo\.com|youtu\.be|netflix\.com|nflxvideo\.net|primevideo\.com|disneyplus\.com)$/i;

async function store(k, v) { if (v === undefined) return (await api.storage.local.get(k))[k]; await api.storage.local.set({ [k]: v }); }

async function findPort() {
  for (const p of PORTS) {
    try {
      const r = await fetch(`http://127.0.0.1:${p}/api/ping`, { signal: AbortSignal.timeout(700) });
      const j = await r.json();
      if (j.app === 'telechargys') return p;
    } catch (e) {}
  }
  return 0;
}

// connect : trouve l'application et, si besoin, demande l'autorisation (association).
async function connect(allowPair) {
  const port = await findPort();
  if (!port) { conn = null; return null; }
  let token = await store('token');
  if (token) {
    const r = await fetch(`http://127.0.0.1:${port}/api/state`, { headers: { 'X-Token': token } }).catch(() => null);
    if (r && r.ok) { appSettings = (await r.json()).settings; conn = { port, token }; return conn; }
    token = null;
  }
  if (!allowPair) { conn = null; return null; }
  const name = (/Edg\//.test(navigator.userAgent) ? 'Edge' : /Firefox\//.test(navigator.userAgent) ? 'Firefox' : 'Chrome');
  const r = await fetch(`http://127.0.0.1:${port}/api/pair`, { method: 'POST', body: JSON.stringify({ name: 'Extension ' + name }) }).catch(() => null);
  if (!r || !r.ok) { conn = null; return null; }
  token = (await r.json()).token;
  await store('token', token);
  return connect(false);
}

async function call(path, body) {
  if (!conn && !(await connect(false))) throw new Error('Telechargys n\'est pas lancé ou pas encore autorisé');
  const r = await fetch(`http://127.0.0.1:${conn.port}/api/${path}`, { method: 'POST', headers: { 'X-Token': conn.token }, body: JSON.stringify(body) });
  if (r.status === 401) { conn = null; await store('token', ''); throw new Error('Autorisation perdue : rouvre l\'extension pour la redonner'); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'Erreur ' + r.status);
  return r.json();
}

async function cookiesFor(url) {
  try { return (await api.cookies.getAll({ url })).map(c => c.name + '=' + c.value).join('; '); } catch (e) { return ''; }
}

async function send(url, referer, fileName) {
  return call('capture', { url, referer: referer || '', cookies: await cookiesFor(url), userAgent: navigator.userAgent, fileName: fileName || '' });
}

function extOf(u) { try { return (/\.([a-z0-9]{1,5})$/i.exec(new URL(u).pathname) || [])[1].toLowerCase(); } catch (e) { return ''; } }

// ----- capture des téléchargements du navigateur -----
api.downloads.onCreated.addListener(async item => {
  try {
    if (item.state && item.state !== 'in_progress') return;
    if ((await store('enabled')) === false) return;
    const url = item.finalUrl || item.url;
    if (!/^https?:\/\//i.test(url)) return; // blob:, data: : laissés au navigateur
    if (!conn && !(await connect(false))) return;
    const exts = (appSettings && appSettings.captureExts) || [];
    const e = extOf(url) || extOf(item.filename || '');
    if (!exts.includes(e)) return;
    const min = ((appSettings && appSettings.captureMinKB) || 0) * 1024;
    if (min && item.fileSize > 0 && item.fileSize < min) return;
    await send(url, item.referrer, '');
    // l'application a bien reçu le lien : on annule la copie du navigateur
    await api.downloads.cancel(item.id).catch(() => {});
    await api.downloads.erase({ id: item.id }).catch(() => {});
  } catch (e) { /* en cas de souci, le navigateur continue son téléchargement normalement */ }
});

// ----- menu contextuel -----
function buildMenus() {
  api.contextMenus.removeAll(() => {
    api.contextMenus.create({ id: 'ty-link', title: 'Télécharger avec Telechargys', contexts: ['link', 'image', 'video', 'audio'] });
    api.contextMenus.create({ id: 'ty-all', title: 'Télécharger tous les fichiers liés de cette page', contexts: ['page'] });
  });
}
api.runtime.onInstalled.addListener(() => { buildMenus(); connect(true); });
api.runtime.onStartup.addListener(() => { buildMenus(); connect(false); });

function notify(tabId, text, bad) {
  api.action.setBadgeBackgroundColor({ color: bad ? '#d64545' : '#0e9f6e' });
  api.action.setBadgeText({ text: bad ? '!' : '✓', tabId });
  api.action.setTitle({ title: text, tabId });
  setTimeout(() => refreshBadge(tabId), 2500);
}

api.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (info.menuItemId === 'ty-link') {
      const url = info.linkUrl || info.srcUrl;
      if (!/^https?:\/\//i.test(url || '')) throw new Error('Lien non téléchargeable');
      await send(url, info.pageUrl);
      notify(tab.id, 'Envoyé à Telechargys');
    } else if (info.menuItemId === 'ty-all') {
      if (!conn) await connect(false);
      const exts = (appSettings && appSettings.captureExts) || [];
      const [{ result }] = await api.scripting.executeScript({ target: { tabId: tab.id }, func: () => [...new Set([...document.querySelectorAll('a[href],img[src],video[src],audio[src],source[src]')].map(e => e.href || e.src))] });
      const urls = (result || []).filter(u => /^https?:\/\//i.test(u) && exts.includes(((/\.([a-z0-9]{1,5})$/i.exec(new URL(u).pathname) || [])[1] || '').toLowerCase()));
      if (!urls.length) throw new Error('Aucun fichier reconnu sur cette page');
      const cookies = await cookiesFor(tab.url);
      await call('downloads', { items: urls.map(u => ({ url: u, referer: tab.url, cookies, userAgent: navigator.userAgent })) });
      notify(tab.id, urls.length + ' fichiers ajoutés à la file de Telechargys');
    }
  } catch (e) { notify(tab && tab.id, e.message, true); }
});

// ----- détection des vidéos et musiques des pages -----
const MEDIA_EXT = ['mp4', 'webm', 'mkv', 'mov', 'm4v', 'flv', 'mp3', 'm4a', 'ogg', 'opus', 'flac', 'wav', 'aac', 'm3u8'];
function refreshBadge(tabId) {
  const n = (media[tabId] || []).length;
  api.action.setBadgeBackgroundColor({ color: '#0e9f6e' });
  api.action.setBadgeText({ text: n ? String(n) : '', tabId }).catch(() => {});
  api.action.setTitle({ title: n ? `Telechargys : ${n} média${n > 1 ? 's' : ''} détecté${n > 1 ? 's' : ''}` : 'Telechargys', tabId }).catch(() => {});
}
api.webRequest.onResponseStarted.addListener(d => {
  if (d.tabId < 0 || d.statusCode >= 400) return;
  let host = '';
  try { const u = new URL(d.url); host = u.hostname; if (host === '127.0.0.1' && PORTS.includes(+u.port)) return; } catch (e) { return; }
  if (SKIP_HOSTS.test(host)) return;
  const hdr = n => { const h = (d.responseHeaders || []).find(x => x.name.toLowerCase() === n); return h ? h.value : ''; };
  const ct = hdr('content-type').toLowerCase().split(';')[0].trim();
  const e = extOf(d.url);
  const hls = e === 'm3u8' || ct.includes('mpegurl');
  const isMedia = hls || ct.startsWith('video/') || ct.startsWith('audio/') || (MEDIA_EXT.includes(e) && d.type === 'media');
  if (!isMedia || e === 'ts' || e === 'm4s' || ct === 'video/mp2t') return; // morceaux de flux ignorés
  let size = parseInt(hdr('content-length'), 10) || 0;
  const cr = /\/(\d+)$/.exec(hdr('content-range')); if (cr) size = parseInt(cr[1], 10);
  if (!hls && size > 0 && size < 300 * 1024) return;
  const list = media[d.tabId] = media[d.tabId] || [];
  const known = list.find(m => m.url === d.url);
  if (known) { if (size > known.size) known.size = size; return; }
  list.unshift({ url: d.url, type: hls ? 'HLS' : (e || ct.split('/')[1] || 'média').toUpperCase(), size, referer: d.initiator || d.documentUrl || '' });
  if (list.length > 25) list.pop();
  refreshBadge(d.tabId);
}, { urls: ['http://*/*', 'https://*/*'] }, ['responseHeaders']);
api.tabs.onRemoved.addListener(id => { delete media[id]; });
api.tabs.onUpdated.addListener((id, ch) => { if (ch.url) { media[id] = []; refreshBadge(id); } });

// ----- messages de la fenêtre de l'extension -----
api.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.type === 'status') {
      const c = await connect(false);
      const port = c ? c.port : await findPort();
      return { connected: !!c, running: !!port, enabled: (await store('enabled')) !== false, media: media[msg.tabId] || [] };
    }
    if (msg.type === 'pair') return { connected: !!(await connect(true)) };
    if (msg.type === 'enable') { await store('enabled', msg.value); return {}; }
    if (msg.type === 'send') { await send(msg.url, msg.referer, msg.fileName); return { ok: true }; }
    return {};
  })().then(reply, e => reply({ error: e.message }));
  return true;
});
