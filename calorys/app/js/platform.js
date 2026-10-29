/* Calorys : couche plateforme (Android, Windows via Neutralino, navigateur).
   Tout le reste de l'appli passe par Platform pour stocker et exporter. */
(function () {
  'use strict';
  const STORE_KEY = 'calorys.data.v1';
  const native = window.CalorysNative || null;
  const isNeu = typeof window.NL_PORT !== 'undefined' && typeof window.Neutralino !== 'undefined';
  const kind = native ? 'android' : isNeu ? 'windows' : 'web';

  let dataFile = null;      // Windows : %APPDATA%\Calorys\data.json
  let docsDir = null;       // Windows : Documents\Calorys
  let lastSaveDir = null;   // Windows : dernier dossier de "Enregistrer sous"
  let writeTimer = null;
  let pendingJson = null;

  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); return true; } catch (e) { return false; } }

  async function init() {
    if (kind !== 'windows') return;
    Neutralino.init();
    Neutralino.events.on('windowClose', async () => { await flush(); Neutralino.app.exit(); });
    const sep = window.NL_OS === 'Windows' ? '\\' : '/';
    const appData = await Neutralino.os.getPath('data');
    const docs = await Neutralino.os.getPath('documents');
    const dir = appData + sep + 'Calorys';
    docsDir = docs + sep + 'Calorys';
    for (const d of [dir, docsDir]) {
      try { await Neutralino.filesystem.createDirectory(d); } catch (e) { /* existe déjà */ }
    }
    dataFile = dir + sep + 'data.json';
    lastSaveDir = lsGet('calorys.lastSaveDir') || docsDir;
  }

  async function load() {
    if (kind === 'windows') {
      try { return JSON.parse(await Neutralino.filesystem.readFile(dataFile)); } catch (e) { /* premier lancement */ }
      const bak = lsGet(STORE_KEY);
      return bak ? JSON.parse(bak) : null;
    }
    const raw = lsGet(STORE_KEY);
    if (raw) { try { return JSON.parse(raw); } catch (e) { /* corrompu */ } }
    if (native && native.loadBackup) {
      // Filet de sécurité Android : copie miroir dans le stockage interne de l'appli.
      const b = native.loadBackup();
      if (b) { try { return JSON.parse(b); } catch (e) { /* ignore */ } }
    }
    return null;
  }

  function save(state) {
    const json = JSON.stringify(state);
    lsSet(STORE_KEY, json);
    if (kind === 'android' && native.saveBackup) {
      pendingJson = json;
      clearTimeout(writeTimer);
      writeTimer = setTimeout(() => { native.saveBackup(pendingJson); pendingJson = null; }, 800);
    }
    if (kind === 'windows') {
      pendingJson = json;
      clearTimeout(writeTimer);
      writeTimer = setTimeout(flush, 500);
    }
  }

  async function flush() {
    if (pendingJson == null) return;
    const json = pendingJson; pendingJson = null;
    if (kind === 'android') { native.saveBackup(json); return; }
    if (kind === 'windows') {
      const tmp = dataFile + '.tmp';
      await Neutralino.filesystem.writeFile(tmp, json);
      try { await Neutralino.filesystem.remove(dataFile); } catch (e) { /* absent */ }
      await Neutralino.filesystem.move(tmp, dataFile);
    }
  }

  /* Enregistre un fichier texte. Renvoie un libellé lisible de l'emplacement, ou null si annulé. */
  async function exportFile(name, mime, text) {
    if (kind === 'android') {
      const res = native.saveFile(name, mime, text);
      if (res && res.startsWith('ERR:')) throw new Error(res.slice(4));
      return res;
    }
    if (kind === 'windows') {
      const sep = window.NL_OS === 'Windows' ? '\\' : '/';
      const path = await Neutralino.os.showSaveDialog('Enregistrer sous', {
        defaultPath: (lastSaveDir || docsDir) + sep + name,
        filters: [{ name: name.endsWith('.csv') ? 'Fichier CSV' : 'Sauvegarde JSON', extensions: [name.split('.').pop()] }]
      });
      if (!path) return null;
      await Neutralino.filesystem.writeFile(path, (name.endsWith('.csv') ? '﻿' : '') + text);
      lastSaveDir = path.slice(0, Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/')));
      lsSet('calorys.lastSaveDir', lastSaveDir);
      return path;
    }
    const blob = new Blob([(name.endsWith('.csv') ? '﻿' : '') + text], { type: mime });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    return 'Téléchargements/' + name;
  }

  function canShare() { return kind === 'android' || (kind === 'web' && !!navigator.share); }

  async function shareFile(name, mime, text) {
    if (kind === 'android') { native.shareFile(name, mime, text); return; }
    const file = new File([text], name, { type: mime });
    if (navigator.canShare && navigator.canShare({ files: [file] })) await navigator.share({ files: [file], title: name });
    else await navigator.share({ title: name, text });
  }

  async function openFolder() {
    if (kind === 'windows') await Neutralino.os.open(docsDir);
  }

  function setBars(dark, color) {
    if (native && native.setBars) native.setBars(!!dark, color);
  }

  function vibrate(ms) {
    if (native && native.vibrate) native.vibrate(ms || 15);
    else if (navigator.vibrate) navigator.vibrate(ms || 15);
  }

  window.Platform = { kind, init, load, save, flush, exportFile, canShare, shareFile, openFolder, setBars, vibrate,
    get docsDir() { return docsDir; } };
})();
