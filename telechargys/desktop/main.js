// Telechargys : application de bureau (fenêtre, zone de notification, intégration Windows).
const { app, BrowserWindow, Tray, Menu, ipcMain, shell, dialog, clipboard, Notification, nativeImage } = require('electron');
const { spawn, execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const isWin = process.platform === 'win32';
const asset = f => path.join(__dirname, 'assets', f);
let win, tray, engine, base = '', token = '', settings = {}, quitting = false, lastClip = '', clipTimer;

if (!app.requestSingleInstanceLock()) { app.quit(); return; }
app.setAppUserModelId('com.qmtech.telechargys');

const urlsIn = argv => argv.filter(a => /^(https?|ftp):\/\//i.test(a));

function api(method, p, body) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? null : JSON.stringify(body);
    const req = http.request(base + '/api/' + p, { method, headers: { 'X-Token': token, 'Content-Type': 'application/json' } }, res => {
      let s = ''; res.on('data', c => { s += c; }); res.on('end', () => { try { resolve(JSON.parse(s)); } catch (e) { resolve(null); } });
    });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

function startEngine() {
  return new Promise((resolve, reject) => {
    const name = isWin ? 'telechargys-engine.exe' : 'telechargys-engine';
    const bin = app.isPackaged ? path.join(process.resourcesPath, 'engine', name) : path.join(__dirname, 'engine-bin', isWin ? 'win' : 'linux', name);
    const data = process.env.TY_DATA || path.join(app.getPath('userData'), 'moteur');
    const dl = process.env.TY_DOWNLOADS || path.join(app.getPath('downloads'), 'Telechargys');
    engine = spawn(bin, ['-data', data, '-downloads', dl], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    let out = '', done = false;
    engine.stdout.on('data', c => {
      out += c;
      if (!done && out.includes('\n')) {
        done = true;
        try { const j = JSON.parse(out.split('\n')[0]); base = 'http://127.0.0.1:' + j.port; token = j.token; resolve(); } catch (e) { reject(e); }
      }
    });
    engine.stderr.on('data', c => console.error('[moteur]', String(c)));
    engine.on('error', reject);
    engine.on('exit', code => { if (!quitting) { dialog.showErrorBox('Telechargys', 'Le moteur de téléchargement s\'est arrêté (code ' + code + ').'); app.exit(1); } });
  });
}

function showWin() {
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show(); win.focus();
}

function createWindow() {
  win = new BrowserWindow({
    width: 1200, height: 760, minWidth: 420, minHeight: 480, show: false, icon: asset('icon.png'), backgroundColor: '#f3f5f7', title: 'Telechargys',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  win.loadURL(base + '/?token=' + token);
  win.webContents.on('did-finish-load', () => setTimeout(() => { uiReady = true; pendingUrls.splice(0).forEach(addUrl); }, 900));
  win.once('ready-to-show', () => { if (!process.argv.includes('--hidden')) win.show(); });
  win.on('close', e => { if (!quitting && settings.minimizeToTray) { e.preventDefault(); win.hide(); } });
  win.on('closed', () => { win = null; });
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith(base)) { e.preventDefault(); shell.openExternal(url); } });
}

let uiReady = false; const pendingUrls = [];
function addUrl(u) { if (!uiReady) { pendingUrls.push(u); return; } api('POST', 'capture', { url: u }).catch(() => {}); }

function buildMenu() {
  const tpl = [
    { label: 'Fichier', submenu: [
      { label: 'Nouveau téléchargement…', accelerator: 'CmdOrCtrl+N', click: () => { showWin(); win.webContents.executeJavaScript('openAdd()'); } },
      { label: 'Ouvrir le dossier des téléchargements', click: () => shell.openPath(settings.downloadDir || app.getPath('downloads')) },
      { type: 'separator' },
      { label: 'Quitter', accelerator: 'CmdOrCtrl+Q', click: quit },
    ] },
    { label: 'Téléchargements', submenu: [
      { label: 'Tout démarrer', click: () => api('POST', 'actions', { action: 'startAll' }) },
      { label: 'Tout arrêter', click: () => api('POST', 'actions', { action: 'pauseAll' }) },
    ] },
    { label: 'Affichage', submenu: [{ role: 'reload', label: 'Actualiser' }, { role: 'zoomIn', label: 'Zoom avant' }, { role: 'zoomOut', label: 'Zoom arrière' }, { role: 'resetZoom', label: 'Taille normale' }, { role: 'togglefullscreen', label: 'Plein écran' }] },
    { label: 'Aide', submenu: [
      { label: 'Installer l\'extension pour navigateur…', click: extensionHelp },
      { label: 'À propos de Telechargys', click: () => dialog.showMessageBox(win, { type: 'info', title: 'À propos', message: 'Telechargys ' + app.getVersion(), detail: 'Gestionnaire de téléchargements accéléré.\n© QMTech', icon: nativeImage.createFromPath(asset('icon.png')) }) },
    ] },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(tpl));
}

function extensionHelp() {
  const dir = app.isPackaged ? path.join(process.resourcesPath, 'extension') : path.join(__dirname, '..', 'extension');
  dialog.showMessageBox(win, {
    type: 'info', title: 'Extension pour navigateur', buttons: ['Ouvrir le dossier de l\'extension', 'Fermer'], defaultId: 0, cancelId: 1,
    message: 'Capter les téléchargements de Chrome, Edge, Brave ou Opera',
    detail: '1. Dans le navigateur, ouvre la page chrome://extensions (ou edge://extensions).\n2. Active le « Mode développeur » (en haut à droite).\n3. Clique sur « Charger l\'extension non empaquetée ».\n4. Choisis ce dossier :\n' + dir + '\n5. Accepte la demande d\'autorisation qui apparaît dans Telechargys.\n\nFirefox : page about:debugging, « Ce Firefox », « Charger un module temporaire », puis le fichier manifest.json du sous-dossier firefox.',
  }).then(r => { if (r.response === 0) shell.openPath(dir); });
}

function buildTray() {
  tray = new Tray(nativeImage.createFromPath(asset('tray.png')));
  tray.setToolTip('Telechargys');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Ouvrir Telechargys', click: showWin },
    { label: 'Nouveau téléchargement…', click: () => { showWin(); win.webContents.executeJavaScript('openAdd()'); } },
    { type: 'separator' },
    { label: 'Tout démarrer', click: () => api('POST', 'actions', { action: 'startAll' }) },
    { label: 'Tout arrêter', click: () => api('POST', 'actions', { action: 'pauseAll' }) },
    { type: 'separator' },
    { label: 'Quitter', click: quit },
  ]));
  tray.on('click', showWin);
}

function fmtSpeed(n) { const u = ['o', 'Ko', 'Mo', 'Go']; let i = 0; while (n >= 1024 && i < 3) { n /= 1024; i++; } return (i ? n.toFixed(1).replace('.', ',') : n) + ' ' + u[i] + '/s'; }

function applySettings(s) {
  settings = s || settings;
  if (app.isPackaged && isWin) app.setLoginItemSettings({ openAtLogin: !!settings.startWithSystem, args: ['--hidden'] });
  clearInterval(clipTimer);
  if (settings.clipboardWatch) {
    lastClip = clipboard.readText();
    clipTimer = setInterval(() => {
      const t = clipboard.readText().trim();
      if (t === lastClip) return;
      lastClip = t;
      if (!/^(https?|ftp):\/\/\S+$/i.test(t) || t.length > 2000) return;
      let ext = '';
      try { ext = (/\.([a-z0-9]{1,5})$/i.exec(new URL(t).pathname) || [])[1] || ''; } catch (e) { return; }
      if ((settings.captureExts || []).includes(ext.toLowerCase())) { addUrl(t); }
    }, 1200);
  }
}

function postAction(a) {
  if (!a) return;
  if (a === 'exit') return quit();
  const labels = { shutdown: 'éteindre l\'ordinateur', sleep: 'mettre l\'ordinateur en veille', hibernate: 'mettre l\'ordinateur en veille prolongée' };
  showWin();
  let cancelled = false;
  const ctrl = new AbortController();
  const t = setTimeout(() => {
    if (cancelled) return;
    ctrl.abort();
    if (!isWin) return;
    if (a === 'shutdown') execFile('shutdown', ['/s', '/t', '5']);
    else if (a === 'hibernate') execFile('shutdown', ['/h']);
    else if (a === 'sleep') execFile('rundll32.exe', ['powrprof.dll,SetSuspendState', '0,1,0']);
  }, 30000);
  dialog.showMessageBox(win, { type: 'warning', title: 'File terminée', message: 'La file est terminée : Telechargys va ' + labels[a] + ' dans 30 secondes.', buttons: ['Annuler'], signal: ctrl.signal })
    .then(() => { cancelled = true; clearTimeout(t); }).catch(() => {});
}

// flux d'évènements du moteur (notifications, capture, fin de file)
function listen() {
  const req = http.get(base + '/api/events?token=' + token, res => {
    let buf = '';
    res.on('data', c => {
      buf += c;
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 2);
        if (!line.startsWith('data: ')) continue;
        let ev; try { ev = JSON.parse(line.slice(6)); } catch (e) { continue; }
        onEvent(ev);
      }
    });
    res.on('end', () => { if (!quitting) setTimeout(listen, 1500); });
  });
  req.on('error', () => { if (!quitting) setTimeout(listen, 1500); });
}
// fenêtres de progression et de fin (comme IDM)
const progWins = new Map(), lastStatus = new Map();
function miniWin(id, view, w, hgt) {
  const bw = new BrowserWindow({
    width: w, height: hgt, resizable: view !== 'done', minimizable: true, maximizable: false, show: false, icon: asset('icon.png'),
    autoHideMenuBar: true, backgroundColor: '#ffffff', title: 'Telechargys',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  bw.setMenu(null);
  console.log('[fenêtre]', view, id);
  bw.loadURL(`${base}/progress.html?view=${view}&id=${id}&token=${token}`);
  bw.once('ready-to-show', () => bw.showInactive ? bw.show() : bw.show());
  bw.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  return bw;
}
function onDownload(d) {
  const prev = lastStatus.get(d.id);
  lastStatus.set(d.id, d.status);
  const pw = progWins.get(d.id);
  if (d.status === 'downloading' && prev !== 'downloading' && prev !== 'merging' && !d.viaQueue && settings.showProgressWin && !pw && progWins.size < 6 && prev !== undefined) {
    const bw = miniWin(d.id, 'progress', 520, 500);
    progWins.set(d.id, bw);
    bw.on('closed', () => progWins.delete(d.id));
  }
  if (d.status === 'completed' && prev && prev !== 'completed') {
    if (pw && !pw.isDestroyed()) pw.close();
    if (settings.showDoneWin && !d.viaQueue) miniWin(d.id, 'done', 520, 340);
  }
}
function onEvent(ev) {
  const d = ev.data;
  if (ev.type === 'download') return onDownload(d);
  if (ev.type === 'removed') { const pw = progWins.get(d); if (pw && !pw.isDestroyed()) pw.close(); lastStatus.delete(d); return; }
  if (ev.type === 'notify' && d.kind === 'done' && settings.showDoneWin) return;
  if (ev.type === 'notify' && settings.notifyDone && Notification.isSupported() && !(win && win.isFocused())) {
    const n = new Notification({ title: d.title, body: d.body, icon: asset('icon.png') });
    n.on('click', () => { if (d.kind === 'done' && d.path) shell.showItemInFolder(d.path); else showWin(); });
    n.show();
  } else if (ev.type === 'capture' || ev.type === 'pair') showWin();
  else if (ev.type === 'queueDone') postAction(d.postAction);
  else if (ev.type === 'settings') applySettings(d);
}

function pollSummary() {
  setInterval(async () => {
    try {
      const s = await api('GET', 'summary');
      if (win) win.setProgressBar(s.active ? (s.percent >= 0 ? s.percent / 100 : 2) : -1);
      if (tray) tray.setToolTip(s.active ? `Telechargys : ${s.active} en cours, ${fmtSpeed(s.speed)}` : 'Telechargys');
    } catch (e) {}
  }, 1500);
}

function quit() {
  if (quitting) return;
  quitting = true;
  clearInterval(clipTimer);
  const end = () => app.exit(0);
  if (engine && engine.exitCode === null) {
    engine.once('exit', end);
    try { engine.stdin.write('quit\n'); } catch (e) {}
    setTimeout(() => { try { engine.kill(); } catch (e) {} end(); }, 5000);
  } else end();
}

ipcMain.handle('openFile', async (e, p) => { const err = await shell.openPath(p); if (err) dialog.showErrorBox('Telechargys', 'Impossible d\'ouvrir le fichier :\n' + p); });
ipcMain.handle('showInFolder', (e, p) => { fs.existsSync(p) ? shell.showItemInFolder(p) : shell.openPath(path.dirname(p)); });
ipcMain.handle('chooseFolder', async (e, cur) => {
  const r = await dialog.showOpenDialog(win, { title: 'Choisir un dossier', defaultPath: cur || undefined, properties: ['openDirectory', 'createDirectory'] });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.handle('readClipboard', () => clipboard.readText());
ipcMain.handle('copy', (e, t) => { clipboard.writeText(String(t)); lastClip = String(t).trim(); });
ipcMain.handle('applySettings', (e, s) => applySettings(s));
ipcMain.handle('resizeProgress', (e, big) => { const w = BrowserWindow.fromWebContents(e.sender); if (w) w.setSize(w.getSize()[0], big ? 500 : 360); });

app.on('second-instance', (e, argv) => { showWin(); urlsIn(argv).forEach(addUrl); });
app.on('window-all-closed', () => {});
app.on('before-quit', e => { if (!quitting) { e.preventDefault(); quit(); } });

app.whenReady().then(async () => {
  try { await startEngine(); } catch (e) { dialog.showErrorBox('Telechargys', 'Impossible de démarrer le moteur de téléchargement.\n' + e.message); app.exit(1); return; }
  const st = await api('GET', 'state');
  for (const d of st.downloads || []) lastStatus.set(d.id, d.status);
  createWindow(); buildMenu(); buildTray(); applySettings(st.settings); listen(); pollSummary();
  urlsIn(process.argv).forEach(addUrl);
  if (process.env.TY_SHOT) setTimeout(async () => { const img = await win.webContents.capturePage(); fs.writeFileSync(process.env.TY_SHOT, img.toPNG()); quit(); }, 4000);
});
