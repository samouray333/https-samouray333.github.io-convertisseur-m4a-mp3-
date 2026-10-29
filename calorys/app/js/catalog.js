/* Calorys : catalogue hors ligne des produits de marque (Open Food Facts, France).
   Base SQLite + index FTS4, téléchargée une seule fois puis utilisée sans réseau.
   Android : SQLite natif via le pont Java. Windows et navigateur : sql.js (WebAssembly). */
(function () {
  'use strict';
  const M = window.CATALOG_MANIFEST || null;
  const native = window.CalorysNative && window.CalorysNative.catalogStatus ? window.CalorysNative : null;
  const isNeu = typeof window.NL_PORT !== 'undefined' && typeof window.Neutralino !== 'undefined';
  const REPO = 'samouray333/https-samouray333.github.io-convertisseur-m4a-mp3-';
  const SOURCES = [
    'https://raw.githubusercontent.com/' + REPO + '/main/calorys/catalog/',
    'https://raw.githubusercontent.com/' + REPO + '/claude/reverse-engineering-app-wsufv0/calorys/catalog/',
    'https://samouray333.github.io/https-samouray333.github.io-convertisseur-m4a-mp3-/calorys/catalog/'
  ];
  // Version web (GitHub Pages) : le catalogue est publié juste à côté de l'appli.
  if (!native && !isNeu && /^https?:$/.test(location.protocol)) SOURCES.unshift(new URL('../catalog/', location.href).href);
  const COLS = 'code, name, brand, kcal, p, c, f, su, sa, fi, sl, serving_g, serving, nutriscore, qty';

  let state = 'none';      // none | downloading | ready | error
  let progress = 0, message = '', outdated = false, sessionOnly = false;
  let db = null;           // sql.js
  let opening = null;
  const listeners = new Set();
  const emit = () => listeners.forEach(fn => { try { fn(status()); } catch (e) { /* ignore */ } });

  function status() {
    return { state, progress, message, outdated, sessionOnly, available: !!M, count: M ? M.count : 0, version: M ? M.version : '',
      sizeMb: M ? Math.round(M.gzSize / 1048576) : 0, dbMb: M ? Math.round(M.dbSize / 1048576) : 0 };
  }

  /* ---------- Requêtes ---------- */
  function norm(s) {
    return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/œ/g, 'oe').replace(/æ/g, 'ae')
      .replace(/[^a-z0-9]+/g, ' ').trim();
  }
  function matchExpr(q) {
    const toks = norm(q).split(' ').filter(t => t.length >= 1).slice(0, 6);
    if (!toks.length || (toks.length === 1 && toks[0].length < 2)) return '';
    return toks.map(t => t + '*').join(' ');
  }
  function toFood(r) {
    const n = v => (v == null ? null : Number(v));
    const per100 = { e: n(r.kcal), p: n(r.p), c: n(r.c), f: n(r.f), su: n(r.su), fi: n(r.fi), sa: n(r.sa), sl: n(r.sl),
      ca: null, fe: null, mg: null, po: null, vc: null, vd: null, b12: null };
    const portions = [];
    if (r.serving_g) portions.push({ l: 'portion' + (r.serving ? ' (' + r.serving + ')' : ''), g: n(r.serving_g) });
    return { key: 'o:' + r.code, barcode: r.code, name: r.name, brand: r.brand || '', per100, portions,
      nutriscore: r.nutriscore || '', qty: r.qty || '', src: 'off' };
  }

  async function search(q, limit) {
    if (state !== 'ready') return [];
    const m = matchExpr(q);
    if (!m) return [];
    limit = limit || 30;
    if (native) {
      try { return JSON.parse(native.catalogSearch(m, limit) || '[]').map(toFood); } catch (e) { return []; }
    }
    const d = await open();
    const st = d.prepare(`SELECT ${COLS} FROM fts JOIN food ON food.id = fts.docid WHERE fts MATCH ? ORDER BY fts.docid LIMIT ?`);
    st.bind([m, limit]);
    const out = [];
    while (st.step()) out.push(toFood(st.getAsObject()));
    st.free();
    return out;
  }

  async function byBarcode(code) {
    if (state !== 'ready' || !code) return null;
    if (native) {
      try { const r = native.catalogBarcode(String(code)); return r ? toFood(JSON.parse(r)) : null; } catch (e) { return null; }
    }
    const d = await open();
    const st = d.prepare(`SELECT ${COLS} FROM food WHERE code = ? LIMIT 1`);
    st.bind([String(code)]);
    const r = st.step() ? toFood(st.getAsObject()) : null;
    st.free();
    return r;
  }

  /* ---------- sql.js (Windows et navigateur) ---------- */
  let sqlPromise = null;
  function loadSql() {
    if (sqlPromise) return sqlPromise;
    sqlPromise = new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = 'js/vendor/sql-wasm.js';
      s.onload = () => window.initSqlJs({ locateFile: f => 'js/vendor/' + f }).then(res, rej);
      s.onerror = () => rej(new Error('sql.js indisponible'));
      document.head.appendChild(s);
    });
    return sqlPromise;
  }
  function open() {
    if (db) return Promise.resolve(db);
    if (!opening) opening = (async () => {
      const SQL = await loadSql();
      const bytes = await readStored();
      if (!bytes) throw new Error('catalogue absent');
      db = new SQL.Database(bytes);
      return db;
    })().catch(e => { opening = null; throw e; });
    return opening;
  }

  /* Stockage du fichier .db : %APPDATA%\Calorys\catalog.db (Windows), IndexedDB (navigateur). */
  async function neuPath() {
    const sep = window.NL_OS === 'Windows' ? '\\' : '/';
    return (await Neutralino.os.getPath('data')) + sep + 'Calorys' + sep + 'catalog.db';
  }
  function idb() {
    return new Promise((res, rej) => {
      const r = indexedDB.open('calorys-catalog', 1);
      r.onupgradeneeded = () => r.result.createObjectStore('files');
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    });
  }
  async function idbOp(mode, fn) {
    const d = await idb();
    return new Promise((res, rej) => {
      const tx = d.transaction('files', mode);
      const req = fn(tx.objectStore('files'));
      tx.oncomplete = () => res(req && req.result);
      tx.onerror = () => rej(tx.error || new Error('stockage refusé'));
      tx.onabort = () => rej(tx.error || new Error('espace de stockage insuffisant'));
    });
  }
  async function readStored() {
    if (isNeu) {
      try { return new Uint8Array(await Neutralino.filesystem.readBinaryFile(await neuPath())); } catch (e) { return null; }
    }
    const v = await idbOp('readonly', s => s.get('db'));
    return v ? new Uint8Array(v) : null;
  }
  async function writeStored(u8) {
    if (isNeu) { await Neutralino.filesystem.writeBinaryFile(await neuPath(), u8.buffer); return; }
    await idbOp('readwrite', s => s.put(u8.buffer, 'db'));
  }
  async function removeStored() {
    if (isNeu) { try { await Neutralino.filesystem.remove(await neuPath()); } catch (e) { /* absent */ } return; }
    await idbOp('readwrite', s => s.delete('db'));
  }

  async function sha256(buf) {
    const h = await crypto.subtle.digest('SHA-256', buf);
    return Array.from(new Uint8Array(h), b => b.toString(16).padStart(2, '0')).join('');
  }

  async function fetchPart(part, onBytes) {
    let lastErr = null;
    for (const base of SOURCES) {
      try {
        const r = await fetch(base + part.name, { cache: 'no-store' });
        if (!r.ok) { lastErr = new Error('HTTP ' + r.status); continue; }
        const reader = r.body.getReader();
        const buf = new Uint8Array(part.size);
        let off = 0;
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          if (off + value.length > buf.length) throw new Error('taille inattendue');
          buf.set(value, off); off += value.length; onBytes(value.length);
        }
        if (off !== part.size) throw new Error('fichier incomplet');
        if ((await sha256(buf)) !== part.sha256) throw new Error('empreinte invalide');
        return buf;
      } catch (e) { lastErr = e; }
    }
    throw lastErr || new Error('téléchargement impossible');
  }

  async function installJs() {
    let got = 0;
    const parts = [];
    for (const p of M.parts) {
      parts.push(await fetchPart(p, n => { got += n; progress = got / M.gzSize * 0.9; emit(); }));
    }
    message = 'Décompression…'; emit();
    const blob = new Blob(parts);
    const ds = blob.stream().pipeThrough(new DecompressionStream('gzip'));
    const u8 = new Uint8Array(await new Response(ds).arrayBuffer());
    if (u8.length !== M.dbSize || (await sha256(u8)) !== M.dbSha256) throw new Error('catalogue corrompu après décompression');
    message = 'Enregistrement…'; progress = 0.95; emit();
    const SQL = await loadSql();
    db = new SQL.Database(u8);
    try {
      if (!isNeu && navigator.storage && navigator.storage.persist) { try { await navigator.storage.persist(); } catch (e) { /* ignore */ } }
      await writeStored(u8);
      try { localStorage.setItem('calorys.catalog', M.version); } catch (e) { /* ignore */ }
    } catch (e) {
      // Navigateur sans assez d'espace : le catalogue reste utilisable pendant cette session.
      if (isNeu) throw e;
      sessionOnly = true;
    }
  }

  /* ---------- Installation ---------- */
  async function install() {
    if (!M || state === 'downloading') return;
    state = 'downloading'; progress = 0; message = 'Téléchargement…'; emit();
    try {
      if (native) {
        await new Promise((res, rej) => {
          window.__calorysCatalog = (st, pct, msg) => {
            progress = pct; message = msg || message;
            if (st === 'ready') res(); else if (st === 'error') rej(new Error(msg)); else emit();
          };
          native.catalogInstall(JSON.stringify(M), JSON.stringify(SOURCES));
        });
      } else {
        await installJs();
      }
      state = 'ready'; progress = 1; message = ''; emit();
    } catch (e) {
      state = 'error'; message = e.message || String(e); emit();
      throw e;
    }
  }

  async function remove() {
    if (native) native.catalogRemove();
    else { db = null; opening = null; await removeStored(); try { localStorage.removeItem('calorys.catalog'); } catch (e) { /* ignore */ } }
    state = 'none'; progress = 0; emit();
  }

  async function init() {
    if (!M) return;
    try {
      if (native) {
        const st = JSON.parse(native.catalogStatus() || '{}');
        if (st.ready) { state = 'ready'; outdated = st.version !== M.version; }
      } else {
        let flag = null;
        try { flag = localStorage.getItem('calorys.catalog'); } catch (e) { /* ignore */ }
        if (isNeu) { try { await Neutralino.filesystem.getStats(await neuPath()); state = 'ready'; } catch (e) { state = 'none'; } }
        else if (flag) state = 'ready';
      }
    } catch (e) { state = 'none'; }
    emit();
  }

  window.Catalog = { init, install, remove, search, byBarcode, status, onChange: fn => listeners.add(fn), matchExpr };
})();
