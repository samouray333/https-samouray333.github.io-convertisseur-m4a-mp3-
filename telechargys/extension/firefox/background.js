// Telechargys : extension navigateur (capture des téléchargements, menu contextuel, détection des vidéos).
const api = typeof browser !== 'undefined' ? browser : chrome;
const PORTS = Array.from({ length: 10 }, (_, i) => 47615 + i);
let conn = null;      // { port, token }
let appSettings = null;
let media = {};       // tabId -> [{url, type, size, title}]
let altAt = 0;        // dernier clic avec Alt (= laisser le navigateur télécharger)
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

function excluded(u) {
  const list = (appSettings && appSettings.captureExclude) || [];
  if (!u || !list.length) return false;
  let host = ''; try { host = new URL(u).hostname.toLowerCase(); } catch (e) { return false; }
  return list.some(x => host === x || host.endsWith('.' + x));
}

function extOf(u) { try { return (/\.([a-z0-9]{1,5})$/i.exec(new URL(u).pathname) || [])[1].toLowerCase(); } catch (e) { return ''; } }

// ----- capture des téléchargements du navigateur -----
api.downloads.onCreated.addListener(async item => {
  try {
    if (item.state && item.state !== 'in_progress') return;
    if ((await store('enabled')) === false) return;
    if (Date.now() - altAt < 4000) return; // Alt + clic : le navigateur garde la main
    const url = item.finalUrl || item.url;
    if (!/^https?:\/\//i.test(url)) return; // blob:, data: : laissés au navigateur
    if (!conn && !(await connect(false))) return;
    const exts = (appSettings && appSettings.captureExts) || [];
    if (excluded(item.referrer) || excluded(url)) return;
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
    api.contextMenus.create({ id: 'ty-sel', title: 'Télécharger les liens sélectionnés avec Telechargys', contexts: ['selection'] });
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

const onMenu = async (info, tab) => {
  try {
    if (info.menuItemId === 'ty-link') {
      const url = info.linkUrl || info.srcUrl;
      if (!/^https?:\/\//i.test(url || '')) throw new Error('Lien non téléchargeable');
      await send(url, info.pageUrl);
      notify(tab.id, 'Envoyé à Telechargys');
    } else if (info.menuItemId === 'ty-all' || info.menuItemId === 'ty-sel') {
      if (!conn) await connect(false);
      const sel = info.menuItemId === 'ty-sel';
      const exts = (appSettings && appSettings.captureExts) || [];
      const results = await api.scripting.executeScript({ target: { tabId: tab.id, frameIds: [info.frameId || 0] }, args: [sel], func: onlySel => {
        const s = getSelection();
        const els = [...document.querySelectorAll('a[href],img[src],video[src],audio[src],source[src]')]
          .filter(e => !onlySel || (s && s.rangeCount && s.containsNode(e, true)));
        const urls = els.map(e => e.href || e.src);
        if (onlySel && s) for (const m of String(s).matchAll(/(https?|ftp):\/\/[^\s<>"']+/gi)) urls.push(m[0]); // adresses écrites en clair
        return [...new Set(urls)];
      } });
      const all = (results[0] && results[0].result) || [];
      // sélection : tous les liens (l'utilisateur a choisi) ; page entière : seulement les fichiers reconnus
      const urls = all.filter(u => /^(https?|ftp):\/\//i.test(u) && (sel || exts.includes(extOf(u))));
      if (!urls.length) throw new Error(sel ? 'Aucun lien dans la sélection' : 'Aucun fichier reconnu sur cette page');
      await call('capture', { url: urls[0], urls, referer: tab.url, cookies: await cookiesFor(tab.url), userAgent: navigator.userAgent });
      notify(tab.id, urls.length + ' lien' + (urls.length > 1 ? 's' : '') + ' envoyé' + (urls.length > 1 ? 's' : '') + ' à Telechargys');
    }
  } catch (e) { notify(tab && tab.id, e.message, true); }
};
api.contextMenus.onClicked.addListener(onMenu);
globalThis.__tyMenu = onMenu; // utilisé par les tests automatiques

// ----- détection des vidéos et musiques des pages -----
const MEDIA_EXT = ['mp4', 'webm', 'mkv', 'mov', 'm4v', 'flv', 'mp3', 'm4a', 'ogg', 'opus', 'flac', 'wav', 'aac', 'm3u8', 'mpd'];
function refreshBadge(tabId) {
  const n = (media[tabId] || []).length;
  api.action.setBadgeBackgroundColor({ color: '#0e9f6e' });
  api.action.setBadgeText({ text: n ? String(n) : '', tabId }).catch(() => {});
  api.action.setTitle({ title: n ? `Telechargys : ${n} média${n > 1 ? 's' : ''} détecté${n > 1 ? 's' : ''}` : 'Telechargys', tabId }).catch(() => {});
}
api.webRequest.onResponseStarted.addListener(d => {
  if (d.tabId < 0) return;
  if (d.type === 'main_frame') { media[d.tabId] = []; refreshBadge(d.tabId); return; } // nouvelle page
  if (d.statusCode >= 400) return;
  let host = '';
  try { const u = new URL(d.url); host = u.hostname; if (host === '127.0.0.1' && PORTS.includes(+u.port)) return; } catch (e) { return; }
  if (SKIP_HOSTS.test(host)) return;
  const hdr = n => { const h = (d.responseHeaders || []).find(x => x.name.toLowerCase() === n); return h ? h.value : ''; };
  const ct = hdr('content-type').toLowerCase().split(';')[0].trim();
  const e = extOf(d.url);
  const hls = e === 'm3u8' || ct.includes('mpegurl');
  const dash = e === 'mpd' || ct.includes('dash+xml');
  const isMedia = hls || dash || ct.startsWith('video/') || ct.startsWith('audio/') || (MEDIA_EXT.includes(e) && d.type === 'media');
  if (!isMedia || e === 'ts' || e === 'm4s' || ct === 'video/mp2t') return; // morceaux de flux ignorés
  let size = parseInt(hdr('content-length'), 10) || 0;
  const cr = /\/(\d+)$/.exec(hdr('content-range')); if (cr) size = parseInt(cr[1], 10);
  if (!hls && !dash && size > 0 && size < 300 * 1024) return;
  const list = media[d.tabId] = media[d.tabId] || [];
  const known = list.find(m => m.url === d.url);
  if (known) { if (size > known.size) known.size = size; return; }
  list.unshift({ url: d.url, type: hls ? 'HLS' : dash ? 'DASH' : (e || ct.split('/')[1] || 'média').toUpperCase(), size, referer: d.initiator || d.documentUrl || '' });
  if (list.length > 25) list.pop();
  refreshBadge(d.tabId);
}, { urls: ['http://*/*', 'https://*/*'] }, ['responseHeaders']);
api.tabs.onRemoved.addListener(id => { delete media[id]; });

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
    if (msg.type === 'altClick') { altAt = Date.now(); return {}; }
    if (msg.type === 'videoButtonEnabled') {
      if (!conn) await connect(false);
      let host = ''; try { host = new URL(sender.tab.url).hostname; } catch (e) {}
      return { enabled: !!conn && (appSettings ? appSettings.videoButton !== false : true) && !SKIP_HOSTS.test(host) && (await store('enabled')) !== false };
    }
    if (msg.type === 'videoButton') return videoButton(msg, sender.tab);
    return {};
  })().then(reply, e => reply({ error: e.message }));
  return true;
});

// bouton « Télécharger cette vidéo » : la source directe si elle existe, sinon le flux (HLS / DASH) repéré sur la page
async function videoButton(msg, tab) {
  const clean = (msg.title || tab.title || 'video').replace(/[<>:"/\\|?*]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 90) || 'video';
  const list = media[tab.id] || [];
  let url = '', name = '';
  const direct = /^https?:\/\//i.test(msg.src || '') ? msg.src : '';
  const stream = list.find(m => m.type === 'HLS' || m.type === 'DASH');
  if (direct && !/\.(m3u8|mpd)(\?|$)/i.test(direct)) { url = direct; name = clean + '.' + (extOf(direct) || 'mp4'); }
  else if (stream) { url = stream.url; name = clean + '.mp4'; }
  else if (direct) { url = direct; name = clean + '.mp4'; }
  else if (list.length) { url = list[0].url; name = clean + '.' + (extOf(list[0].url) || 'mp4'); }
  if (!url) throw new Error('Vidéo pas encore repérée : lance la lecture quelques secondes puis réessaie');
  await send(url, msg.pageUrl || tab.url, name);
  return { ok: true };
}
