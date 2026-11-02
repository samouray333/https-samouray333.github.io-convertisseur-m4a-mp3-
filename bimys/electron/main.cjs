// Bimys : processus principal Electron (Windows).
const { app, BrowserWindow, dialog, ipcMain, Menu, net, protocol, screen, shell, nativeImage } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const DIST = path.join(__dirname, '..', 'dist');
// dossier de données isolé pour les tests automatiques
if (process.env.BIMYS_USER_DATA) app.setPath('userData', process.env.BIMYS_USER_DATA);
const ICON = path.join(__dirname, '..', 'build', 'icon.png');
const CONFIG = () => path.join(app.getPath('userData'), 'bimys-config.json');
const LOG_DIR = () => path.join(app.getPath('userData'), 'logs');
const LOG_FILE = () => path.join(LOG_DIR(), 'bimys.log');
let win = null;
let pendingFile = null;
let modelOpen = false;

// ------------------------------------------------------------ configuration et journal
function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG(), 'utf8'));
  } catch {
    return {};
  }
}
function writeConfig(patch) {
  try {
    const c = { ...readConfig(), ...patch };
    fs.mkdirSync(path.dirname(CONFIG()), { recursive: true });
    fs.writeFileSync(CONFIG(), JSON.stringify(c, null, 2));
    return c;
  } catch {
    return readConfig();
  }
}
function log(level, msg) {
  try {
    fs.mkdirSync(LOG_DIR(), { recursive: true });
    const f = LOG_FILE();
    if (fs.existsSync(f) && fs.statSync(f).size > 1024 * 1024) fs.renameSync(f, f.replace(/\.log$/, '.1.log'));
    fs.appendFileSync(f, `${new Date().toISOString()} [${level}] ${String(msg).slice(0, 4000)}\n`);
  } catch {
    /* journal indisponible */
  }
}
process.on('uncaughtException', (e) => log('fatal', e.stack || e));
process.on('unhandledRejection', (e) => log('error', (e && e.stack) || e));

// ------------------------------------------------------------ rendu 3D : bascule logicielle si la carte graphique est refusée
const cfg0 = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(app.getPath('userData'), 'bimys-config.json'), 'utf8'));
  } catch {
    return {};
  }
})();
const SOFTWARE = !!cfg0.softwareRendering || process.argv.includes('--rendu-logiciel');
if (SOFTWARE) {
  app.commandLine.appendSwitch('use-angle', 'swiftshader');
  app.commandLine.appendSwitch('enable-unsafe-swiftshader');
  app.commandLine.appendSwitch('ignore-gpu-blocklist');
}

// textes internes de Chromium (sélecteur de date, messages de formulaire) toujours en français
app.commandLine.appendSwitch('lang', 'fr-FR');

protocol.registerSchemesAsPrivileged([{ scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } }]);

function docsDir() {
  const d = path.join(app.getPath('documents'), 'Bimys');
  fs.mkdirSync(d, { recursive: true });
  return d;
}
function ifcFromArgs(argv) {
  return argv.slice(1).find((a) => /\.ifc$/i.test(a) && fs.existsSync(a)) || null;
}
function fileMsg(p) {
  const buf = fs.readFileSync(p);
  return { path: p, name: path.basename(p), data: buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) };
}
function send(cmd) {
  if (win) win.webContents.send('menu', cmd);
}

// ------------------------------------------------------------ fichiers récents
function recentList() {
  return (readConfig().recent || []).filter((p) => fs.existsSync(p)).slice(0, 10);
}
function addRecent(p) {
  const list = [p, ...recentList().filter((x) => x.toLowerCase() !== p.toLowerCase())].slice(0, 10);
  writeConfig({ recent: list });
  try {
    app.addRecentDocument(p);
  } catch {
    /* ignoré */
  }
  buildMenu();
}
function openPath(p) {
  try {
    win.webContents.send('open-file', fileMsg(p));
  } catch (e) {
    dialog.showErrorBox('Bimys', `Impossible d'ouvrir ${p} :\n${e.message}`);
  }
}

// ------------------------------------------------------------ menus
function buildMenu() {
  const recent = recentList();
  const m = !modelOpen;
  const template = [
    {
      label: '&Fichier',
      submenu: [
        { label: 'Ouvrir une maquette IFC…', accelerator: 'CmdOrCtrl+O', registerAccelerator: false, click: () => send('open') },
        {
          label: 'Fichiers récents',
          submenu: recent.length
            ? [...recent.map((p, i) => ({ label: `&${i + 1}  ${path.basename(p)}`, toolTip: p, click: () => openPath(p) })), { type: 'separator' }, { label: 'Vider la liste', click: () => { writeConfig({ recent: [] }); try { app.clearRecentDocuments(); } catch { /* */ } buildMenu(); } }]
            : [{ label: '(aucun)', enabled: false }],
        },
        {
          label: 'Ouvrir un exemple',
          submenu: [
            { label: 'Maison R+1 : chaudière gaz', click: () => send('sample:maison_chaudiere_gaz.ifc') },
            { label: 'Maison R+1 : PAC air/eau', click: () => send('sample:maison_pac_air_eau.ifc') },
            { label: 'Maison plain-pied : plancher chauffant, double flux', click: () => send('sample:maison_plain_pied_pcbt.ifc') },
            { type: 'separator' },
            { label: 'Immeuble R+3 : chaufferie collective', click: () => send('sample:immeuble_collectif_r3.ifc') },
            { label: 'Bureaux R+2 : DRV / VRV', click: () => send('sample:bureaux_r2_drv.ifc') },
            { type: 'separator' },
            { label: 'Clinique R+2 : ventilo-convecteurs, groupe froid, CTA', click: () => send('sample:clinique_r2.ifc') },
            { label: 'Cinéma 3 salles : rooftops', click: () => send('sample:cinema_3_salles.ifc') },
          ],
        },
        { label: 'Fermer la maquette', enabled: !m, click: () => send('close') },
        { type: 'separator' },
        { label: 'Capture d’écran de la vue 3D…', accelerator: 'CmdOrCtrl+Shift+S', registerAccelerator: false, enabled: !m, click: () => send('screenshot') },
        { label: 'Ouvrir le dossier des exports', click: () => shell.openPath(readConfig().lastDir && fs.existsSync(readConfig().lastDir) ? readConfig().lastDir : docsDir()) },
        { type: 'separator' },
        { label: 'Paramètres', accelerator: 'CmdOrCtrl+,', click: () => send('page:settings') },
        { type: 'separator' },
        { label: 'Quitter', accelerator: 'Alt+F4', role: 'quit' },
      ],
    },
    {
      label: '&Affichage',
      submenu: [
        { label: 'Vue isométrique', accelerator: '1', registerAccelerator: false, enabled: !m, click: () => send('view:iso') },
        { label: 'Vue de dessus', accelerator: '2', registerAccelerator: false, enabled: !m, click: () => send('view:dessus') },
        { label: 'Vue de face (sud)', accelerator: '3', registerAccelerator: false, enabled: !m, click: () => send('view:face') },
        { label: 'Vue de droite (est)', accelerator: '4', registerAccelerator: false, enabled: !m, click: () => send('view:droite') },
        { label: 'Plan 2D du niveau', accelerator: 'P', registerAccelerator: false, enabled: !m, click: () => send('view:plan') },
        { label: 'Orthographique / perspective', accelerator: 'O', registerAccelerator: false, enabled: !m, click: () => send('view:ortho') },
        { type: 'separator' },
        { label: 'Cadrer', accelerator: 'F', registerAccelerator: false, enabled: !m, click: () => send('view:fit') },
        { label: 'Tout afficher', accelerator: 'A', registerAccelerator: false, enabled: !m, click: () => send('view:all') },
        { label: 'Architecture en transparence', accelerator: 'T', registerAccelerator: false, enabled: !m, click: () => send('view:ghost') },
        { label: 'Rechercher un objet…', accelerator: 'CmdOrCtrl+F', registerAccelerator: false, enabled: !m, click: () => send('search') },
        { type: 'separator' },
        {
          label: 'Thème',
          submenu: [
            { label: 'Automatique', click: () => send('theme:auto') },
            { label: 'Clair', click: () => send('theme:clair') },
            { label: 'Sombre', click: () => send('theme:sombre') },
          ],
        },
        { label: 'Zoom de l’interface +', accelerator: 'CmdOrCtrl+=', role: 'zoomIn' },
        { label: 'Zoom de l’interface −', accelerator: 'CmdOrCtrl+-', role: 'zoomOut' },
        { label: 'Zoom de l’interface 100 %', accelerator: 'CmdOrCtrl+0', role: 'resetZoom' },
        { label: 'Plein écran', accelerator: 'F11', role: 'togglefullscreen' },
        { type: 'separator' },
        { label: 'Rendu 3D logiciel (compatibilité)', type: 'checkbox', checked: SOFTWARE, click: (it) => setSoftware(it.checked) },
      ],
    },
    {
      label: '&Modules',
      submenu: [
        ['viewer', 'Vue 3D', 'CmdOrCtrl+1'],
        ['metre', 'Métré', 'CmdOrCtrl+2'],
        ['nomenclature', 'Équipements', 'CmdOrCtrl+3'],
        ['deperditions', 'Déperditions', 'CmdOrCtrl+4'],
        ['coherence', 'Cohérence', 'CmdOrCtrl+5'],
        ['maintenance', 'Maintenance', 'CmdOrCtrl+6'],
        ['energie', 'Énergie', 'CmdOrCtrl+7'],
        ['defis', 'Défis', 'CmdOrCtrl+8'],
      ].map(([id, label, acc]) => ({ label, accelerator: acc, registerAccelerator: false, enabled: id === 'energie' || !m, click: () => send(`page:${id}`) })),
    },
    {
      label: '&Aide',
      submenu: [
        { label: 'Raccourcis clavier', accelerator: 'F1', registerAccelerator: false, click: () => send('shortcuts') },
        { label: 'Ouvrir le journal d’erreurs', click: () => { log('info', 'Ouverture du journal'); shell.openPath(LOG_FILE()); } },
        { label: 'Outils de développement', accelerator: 'CmdOrCtrl+Shift+I', click: () => win && win.webContents.toggleDevTools() },
        { type: 'separator' },
        { label: 'À propos de Bimys', click: about },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function about() {
  dialog.showMessageBox(win, {
    type: 'info',
    title: 'À propos de Bimys',
    icon: nativeImage.createFromPath(ICON),
    message: `Bimys ${app.getVersion()}`,
    detail:
      'Visionneuse BIM pédagogique en génie thermique (Bac Pro ICCER et MEE).\n© 2026 QMTech. Application 100 % hors ligne.\n\n' +
      `Electron ${process.versions.electron}, Chromium ${process.versions.chrome}\nRendu 3D : ${SOFTWARE ? 'logiciel (compatibilité)' : 'matériel'}\n\n` +
      'Composants : three.js (MIT), web-ifc (MPL-2.0), jsPDF (MIT), Electron (MIT).',
    buttons: ['OK'],
  });
}

function setSoftware(on) {
  writeConfig({ softwareRendering: !!on });
  log('info', `Rendu logiciel : ${on}`);
  const r = dialog.showMessageBoxSync(win, { type: 'question', title: 'Bimys', message: 'Redémarrer Bimys maintenant pour appliquer le mode de rendu 3D ?', buttons: ['Redémarrer', 'Plus tard'], defaultId: 0 });
  if (r === 0) {
    app.relaunch();
    app.exit(0);
  }
}

// ------------------------------------------------------------ fenêtre (taille et position mémorisées)
function windowBounds() {
  const b = readConfig().window;
  if (!b || !b.width) return { width: 1400, height: 900 };
  const area = screen.getDisplayMatching(b).workArea;
  const visible = b.x < area.x + area.width - 100 && b.x + b.width > area.x + 100 && b.y >= area.y - 20 && b.y < area.y + area.height - 100;
  return visible ? b : { width: Math.min(b.width, area.width), height: Math.min(b.height, area.height) };
}

function createWindow() {
  const b = windowBounds();
  win = new BrowserWindow({
    ...b,
    minWidth: 900,
    minHeight: 600,
    title: 'Bimys',
    icon: ICON,
    backgroundColor: '#0f4c5c',
    show: false,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  if (readConfig().maximized) win.maximize();
  win.once('ready-to-show', () => win.show());
  const save = () => {
    if (!win || win.isMinimized()) return;
    writeConfig({ maximized: win.isMaximized(), ...(win.isMaximized() || win.isFullScreen() ? {} : { window: win.getBounds() }) });
  };
  win.on('close', save);
  win.on('resize', () => !win.isMaximized() && writeConfig({ window: win.getBounds() }));
  win.loadURL('app://bimys/index.html');
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('app://')) e.preventDefault();
  });
  win.webContents.on('render-process-gone', (_e, d) => {
    log('fatal', `Processus d'affichage arrêté : ${d.reason} (${d.exitCode})`);
    const r = dialog.showMessageBoxSync({ type: 'error', title: 'Bimys', message: 'L’affichage de Bimys s’est arrêté de façon inattendue.', detail: `Raison : ${d.reason}. Vos données enregistrées sont conservées.`, buttons: ['Relancer', 'Quitter'] });
    if (r === 0) win.reload();
    else app.quit();
  });
  win.webContents.on('console-message', (e) => {
    const level = e.level ?? e.params?.level;
    if (level === 'error' || level === 3) log('renderer', e.message ?? e.params?.message);
  });
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  pendingFile = ifcFromArgs(process.argv);
  app.on('second-instance', (_e, argv) => {
    const f = ifcFromArgs(argv);
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
      if (f) openPath(f);
    }
  });
  app.whenReady().then(() => {
    log('info', `Démarrage Bimys ${app.getVersion()} (Electron ${process.versions.electron}, rendu ${SOFTWARE ? 'logiciel' : 'matériel'})`);
    protocol.handle('app', (req) => {
      const u = new URL(req.url);
      let p = decodeURIComponent(u.pathname);
      if (p === '/' || !p) p = '/index.html';
      const file = path.normalize(path.join(DIST, p));
      if (!file.startsWith(DIST)) return new Response('Interdit', { status: 403 });
      return net.fetch(pathToFileURL(file).toString());
    });
    buildMenu();
    createWindow();
  });
  app.on('window-all-closed', () => app.quit());
}

// ------------------------------------------------------------ échanges avec l'interface
ipcMain.handle('save-file', async (_e, name, data, filters) => {
  const cfg = readConfig();
  const dir = cfg.lastDir && fs.existsSync(cfg.lastDir) ? cfg.lastDir : docsDir();
  const r = await dialog.showSaveDialog(win, { title: 'Enregistrer sous', defaultPath: path.join(dir, name), filters: filters || [] });
  if (r.canceled || !r.filePath) return null;
  fs.writeFileSync(r.filePath, Buffer.from(data));
  writeConfig({ lastDir: path.dirname(r.filePath) });
  log('info', `Export : ${r.filePath}`);
  return r.filePath;
});

ipcMain.handle('open-ifc', async () => {
  const cfg = readConfig();
  const r = await dialog.showOpenDialog(win, {
    title: 'Ouvrir une maquette IFC',
    defaultPath: cfg.lastOpenDir && fs.existsSync(cfg.lastOpenDir) ? cfg.lastOpenDir : app.getPath('documents'),
    filters: [{ name: 'Maquette IFC', extensions: ['ifc'] }, { name: 'Tous les fichiers', extensions: ['*'] }],
    properties: ['openFile'],
  });
  if (r.canceled || !r.filePaths[0]) return null;
  writeConfig({ lastOpenDir: path.dirname(r.filePaths[0]) });
  return fileMsg(r.filePaths[0]);
});

ipcMain.handle('read-file', async (_e, p) => fileMsg(p).data);
ipcMain.handle('initial-file', async () => {
  const f = pendingFile;
  pendingFile = null;
  return f ? fileMsg(f) : null;
});
ipcMain.handle('documents-dir', async () => docsDir());
ipcMain.handle('info', async () => ({ version: app.getVersion(), electron: process.versions.electron, chrome: process.versions.chrome, software: SOFTWARE, logFile: LOG_FILE() }));
ipcMain.on('add-recent', (_e, p) => addRecent(p));
ipcMain.on('show-item', (_e, p) => shell.showItemInFolder(p));
ipcMain.on('software-rendering', (_e, on) => setSoftware(on));
ipcMain.on('model-open', (_e, open) => {
  modelOpen = !!open;
  buildMenu();
});
ipcMain.on('log', (_e, level, msg) => log(level, msg));
