/* Calorys : synchronisation entre appareils, sans serveur ni compte.
   - Chaque élément (aliment noté, séance, pesée, recette…) est daté automatiquement quand il change,
     les suppressions laissent une trace : la fusion garde la version la plus récente de chaque élément.
   - Transport : le téléphone sert d'hôte sur le Wi-Fi local, l'autre appareil s'y connecte.
   - Les données voyagent chiffrées (AES-256-GCM, clé dérivée du code affiché sur l'hôte). */
(function () {
  'use strict';
  const PORT = 8787;
  const TOMB_DAYS = 180;
  const ALPHA = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
  let prev = null; // empreintes des éléments au dernier enregistrement

  /* ---------- Éléments synchronisés ---------- */
  function explode(S) {
    const r = new Map();
    for (const [d, day] of Object.entries(S.days || {})) {
      for (const [m, list] of Object.entries(day.meals || {})) for (const e of list || []) r.set('e:' + e.id, { d, m, e });
      for (const a of day.acts || []) r.set('a:' + a.id, { d, a });
      if (day.water) r.set('dw:' + d, day.water);
      if (day.steps) r.set('ds:' + d, day.steps);
    }
    for (const w of S.weights || []) r.set('w:' + w.date, w);
    for (const f of S.foods || []) r.set('f:' + f.id, f);
    for (const x of S.recipes || []) r.set('r:' + x.id, x);
    for (const [code, f] of Object.entries(S.off || {})) r.set('o:' + code, f);
    for (const x of S.shopping || []) r.set('sh:' + x.id, x);
    for (const x of (S.fasting || {}).history || []) r.set('fh:' + x.start, x);
    r.set('fa', { active: S.fasting.active, plan: S.fasting.plan });
    r.set('p', S.profile);
    r.set('sg', { game: S.settings.game, geminiKey: S.settings.geminiKey });
    r.set('fav', S.favs || []);
    r.set('rc', S.recents || []);
    r.set('frc', S.favRecipes || []);
    return r;
  }
  const hashes = recs => { const h = new Map(); for (const [k, v] of recs) h.set(k, JSON.stringify(v)); return h; };

  function meta(S) {
    if (!S.sync) S.sync = {};
    const m = S.sync;
    if (!m.device) m.device = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    if (!m.t) m.t = {};
    if (!m.tomb) m.tomb = {};
    if (!m.peers) m.peers = {};
    return m;
  }

  /* À l'ouverture : point de départ, les éléments sans date reçoivent une date ancienne. */
  function init(S) {
    const m = meta(S);
    prev = hashes(explode(S));
    for (const k of prev.keys()) if (!m.t[k]) m.t[k] = 1;
  }

  /* À chaque enregistrement : date les éléments modifiés, garde trace des suppressions. */
  function stamp(S) {
    const m = meta(S);
    if (!prev) { init(S); return; }
    const now = Date.now();
    const cur = hashes(explode(S));
    for (const [k, h] of cur) if (prev.get(k) !== h) { m.t[k] = now; delete m.tomb[k]; }
    for (const k of prev.keys()) if (!cur.has(k)) { m.tomb[k] = now; delete m.t[k]; }
    prev = cur;
  }

  /* ---------- Fusion ---------- */
  function payload(S) {
    const m = meta(S);
    return { device: m.device, records: Object.fromEntries(explode(S)), t: m.t, tomb: m.tomb };
  }

  /* Version la plus récente de chaque élément ; à date égale, l'élément l'emporte sur sa suppression. */
  function merge(a, b) {
    const keys = new Set([...Object.keys(a.records), ...Object.keys(b.records), ...Object.keys(a.tomb), ...Object.keys(b.tomb)]);
    const out = { records: {}, t: {}, tomb: {} };
    const limit = Date.now() - TOMB_DAYS * 86400000;
    for (const k of keys) {
      const c = [];
      if (k in a.records) c.push({ v: a.records[k], t: a.t[k] || 1 });
      if (k in b.records) c.push({ v: b.records[k], t: b.t[k] || 1 });
      if (k in a.tomb) c.push({ del: true, t: a.tomb[k] });
      if (k in b.tomb) c.push({ del: true, t: b.tomb[k] });
      c.sort((x, y) => y.t - x.t || (x.del ? 1 : 0) - (y.del ? 1 : 0));
      const w = c[0];
      if (w.del) { if (w.t > limit) out.tomb[k] = w.t; }
      else { out.records[k] = w.v; out.t[k] = w.t; }
    }
    return out;
  }

  /* Reconstruit l'état à partir des éléments fusionnés (les réglages propres à l'appareil restent). */
  function implode(S, merged, MEALS) {
    const R = merged.records;
    const days = {};
    const day = d => days[d] || (days[d] = { meals: Object.fromEntries(MEALS.map(x => [x, []])), water: 0, acts: [], steps: 0 });
    const entries = [], acts = [];
    const out = { weights: [], foods: [], recipes: [], off: {}, shopping: [], history: [] };
    for (const [k, v] of Object.entries(R)) {
      const t = k.slice(0, k.indexOf(':') + 1) || k;
      if (t === 'e:') entries.push(v);
      else if (t === 'a:') acts.push(v);
      else if (t === 'dw:') day(k.slice(3)).water = v;
      else if (t === 'ds:') day(k.slice(3)).steps = v;
      else if (t === 'w:') out.weights.push(v);
      else if (t === 'f:') out.foods.push(v);
      else if (t === 'r:') out.recipes.push(v);
      else if (t === 'o:') out.off[k.slice(2)] = v;
      else if (t === 'sh:') out.shopping.push(v);
      else if (t === 'fh:') out.history.push(v);
    }
    entries.sort((x, y) => (x.e.id < y.e.id ? -1 : 1));
    for (const x of entries) { const dd = day(x.d); (dd.meals[x.m] || (dd.meals[x.m] = [])).push(x.e); }
    acts.sort((x, y) => (x.a.id < y.a.id ? -1 : 1));
    for (const x of acts) day(x.d).acts.push(x.a);
    S.days = days;
    S.weights = out.weights.sort((a, b) => (a.date < b.date ? -1 : 1));
    S.foods = out.foods; S.recipes = out.recipes; S.off = out.off; S.shopping = out.shopping;
    S.fasting.history = out.history.sort((a, b) => a.start - b.start);
    if (R.fa) { S.fasting.active = R.fa.active; S.fasting.plan = R.fa.plan; }
    if (R.p) S.profile = R.p;
    if (R.sg) { S.settings.game = R.sg.game; S.settings.geminiKey = R.sg.geminiKey; }
    if (R.fav) S.favs = R.fav;
    if (R.rc) S.recents = R.rc;
    if (R.frc) S.favRecipes = R.frc;
    const m = meta(S);
    m.t = merged.t; m.tomb = merged.tomb;
    prev = hashes(explode(S));
    return S;
  }

  /* Nombre d'éléments qui diffèrent entre deux jeux (pour le résumé affiché). */
  function diffCount(from, to) {
    let n = 0;
    const keys = new Set([...Object.keys(from.records), ...Object.keys(to.records)]);
    for (const k of keys) if (JSON.stringify(from.records[k]) !== JSON.stringify(to.records[k])) n++;
    return n;
  }

  /* ---------- Chiffrement ---------- */
  const b64 = u8 => { let s = ''; for (let i = 0; i < u8.length; i += 32768) s += String.fromCharCode.apply(null, u8.subarray(i, i + 32768)); return btoa(s); };
  const unb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const normCode = c => String(c || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  async function keyFor(code, salt) {
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode('calorys-sync:' + normCode(code)), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: 150000, hash: 'SHA-256' }, base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  }
  async function gz(u8, dir) {
    const S = dir ? new CompressionStream('gzip') : new DecompressionStream('gzip');
    return new Uint8Array(await new Response(new Blob([u8]).stream().pipeThrough(S)).arrayBuffer());
  }
  async function seal(code, obj) {
    const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
    const data = await gz(new TextEncoder().encode(JSON.stringify(obj)), true);
    const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await keyFor(code, salt), data));
    return JSON.stringify({ v: 1, salt: b64(salt), iv: b64(iv), data: b64(ct) });
  }
  async function open(code, text) {
    const o = JSON.parse(text);
    let pt;
    try { pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(o.iv) }, await keyFor(code, unb64(o.salt)), unb64(o.data)); }
    catch (e) { throw new Error('Code incorrect.'); }
    return JSON.parse(new TextDecoder().decode(await gz(new Uint8Array(pt), false)));
  }
  function newCode() {
    const r = crypto.getRandomValues(new Uint8Array(8));
    const s = Array.from(r, x => ALPHA[x % ALPHA.length]).join('');
    return s.slice(0, 4) + '-' + s.slice(4);
  }

  /* ---------- Client (PC ou téléphone qui se connecte à l'hôte) ---------- */
  function baseUrl(addr) {
    let a = String(addr || '').trim().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
    if (!a) throw new Error('Indique l\'adresse affichée sur le téléphone.');
    if (!/:\d+$/.test(a)) a += ':' + PORT;
    return 'http://' + a;
  }
  async function http(url, opts) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), (opts && opts.timeout) || 20000);
    try { return await fetch(url, Object.assign({ signal: ctl.signal, cache: 'no-store' }, opts || {})); }
    catch (e) { throw new Error('Téléphone injoignable. Vérifie que les deux appareils sont sur le même Wi-Fi et que l\'écran de synchronisation est ouvert sur le téléphone.'); }
    finally { clearTimeout(timer); }
  }
  /* mode : 'merge' (fusion) ou 'replace' (prendre les données de l'hôte). */
  async function connect(S, addr, code, mode, MEALS, deviceName) {
    const base = baseUrl(addr);
    const r = await http(base + '/calorys/state');
    if (r.status === 503) throw new Error('Le téléphone prépare ses données, réessaie dans quelques secondes.');
    if (!r.ok) throw new Error('Réponse inattendue du téléphone (' + r.status + ').');
    const remote = await open(code, await r.text());
    stamp(S);
    const local = payload(S);
    const merged = mode === 'replace' ? { records: remote.records, t: remote.t, tomb: remote.tomb } : merge(local, remote);
    const received = diffCount(local, merged), sent = diffCount(remote, merged);
    const body = await seal(code, { device: meta(S).device, name: deviceName, records: merged.records, t: merged.t, tomb: merged.tomb });
    const r2 = await http(base + '/calorys/state', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body, timeout: 60000 });
    const res = await r2.json().catch(() => ({}));
    if (!r2.ok || !res.ok) throw new Error(res.error || 'Le téléphone n\'a pas pu enregistrer les données.');
    implode(S, merged, MEALS);
    meta(S).peers[remote.device] = { name: remote.name || 'Téléphone', at: Date.now() };
    return { received, sent, peer: remote.name || 'Téléphone' };
  }

  /* ---------- Hôte (téléphone Android) ---------- */
  const host = { code: null, on: false };
  async function hostStart(S, deviceName, onEvent) {
    const nat = window.CalorysNative;
    if (!nat || !nat.syncStart) throw new Error('Seule l\'appli Android peut servir d\'hôte.');
    host.code = newCode();
    host.on = true;
    host.onEvent = onEvent;
    host.S = S; host.name = deviceName;
    const info = JSON.parse(nat.syncStart(PORT) || '{}');
    if (info.error) { host.on = false; throw new Error(info.error); }
    await hostOffer();
    return { code: host.code, ips: info.ips || [], port: info.port || PORT };
  }
  async function hostOffer() {
    if (!host.on) return;
    stamp(host.S);
    const p = payload(host.S);
    p.name = host.name;
    window.CalorysNative.syncOffer(await seal(host.code, p));
  }
  function hostStop() {
    host.on = false;
    if (window.CalorysNative && window.CalorysNative.syncStop) window.CalorysNative.syncStop();
  }
  /* Appelé par Java quand l'autre appareil envoie l'état fusionné. */
  window.__calorysSyncReceive = async function (text) {
    const nat = window.CalorysNative;
    try {
      if (!host.on) throw new Error('synchronisation fermée');
      const m = await open(host.code, text);
      const before = payload(host.S);
      if (host.onEvent) host.onEvent('apply', { records: m.records, t: m.t, tomb: m.tomb }, m);
      const n = diffCount(before, m);
      meta(host.S).peers[m.device] = { name: m.name || 'Appareil', at: Date.now() };
      nat.syncResult(JSON.stringify({ ok: true, changed: n }));
      if (host.onEvent) host.onEvent('done', { changed: n, peer: m.name || 'Appareil' });
      await hostOffer();
    } catch (e) {
      nat.syncResult(JSON.stringify({ ok: false, error: e.message }));
      if (host.onEvent) host.onEvent('error', { message: e.message });
    }
  };

  window.Sync = { PORT, init, stamp, merge, payload, implode, connect, hostStart, hostStop, hostOffer, newCode, seal, open, explode,
    get hosting() { return host.on; } };
})();
