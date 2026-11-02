// Bimys : processus principal Electron (Windows).
const { app, BrowserWindow, dialog, ipcMain, Menu, net, protocol, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const DIST = path.join(__dirname, '..', 'dist');
const CONFIG = () => path.join(app.getPath('userData'), 'bimys-config.json');
let win = null;
let pendingFile = null;

protocol.registerSchemesAsPrivileged([{ scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } }]);

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG(), 'utf8'));
  } catch {
    return {};
  }
}
function writeConfig(c) {
  try {
    fs.mkdirSync(path.dirname(CONFIG()), { recursive: true });
    fs.writeFileSync(CONFIG(), JSON.stringify(c, null, 2));
  } catch {
    /* ignoré */
  }
}
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

function createWindow() {
  win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'Bimys',
    icon: path.join(__dirname, '..', 'build', 'icon.png'),
    backgroundColor: '#0f4c5c',
    show: false,
    autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  win.once('ready-to-show', () => win.show());
  win.loadURL('app://bimys/index.html');
  // aucune navigation externe : l'application est 100 % locale
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('app://')) e.preventDefault();
  });
  win.webContents.on('before-input-event', (e, input) => {
    if (input.type === 'keyDown' && input.key === 'F11') win.setFullScreen(!win.isFullScreen());
    if (input.type === 'keyDown' && input.key === 'F12' && input.control && input.shift) win.webContents.toggleDevTools();
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
      if (f) win.webContents.send('open-file', fileMsg(f));
    }
  });
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    protocol.handle('app', (req) => {
      const u = new URL(req.url);
      let p = decodeURIComponent(u.pathname);
      if (p === '/' || !p) p = '/index.html';
      const file = path.normalize(path.join(DIST, p));
      if (!file.startsWith(DIST)) return new Response('Interdit', { status: 403 });
      return net.fetch(pathToFileURL(file).toString());
    });
    createWindow();
  });
  app.on('window-all-closed', () => app.quit());
}

ipcMain.handle('save-file', async (_e, name, data, filters) => {
  const cfg = readConfig();
  const dir = cfg.lastDir && fs.existsSync(cfg.lastDir) ? cfg.lastDir : docsDir();
  const r = await dialog.showSaveDialog(win, { title: 'Enregistrer sous', defaultPath: path.join(dir, name), filters: filters || [] });
  if (r.canceled || !r.filePath) return null;
  fs.writeFileSync(r.filePath, Buffer.from(data));
  writeConfig({ ...cfg, lastDir: path.dirname(r.filePath) });
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
  writeConfig({ ...cfg, lastOpenDir: path.dirname(r.filePaths[0]) });
  return fileMsg(r.filePaths[0]);
});

ipcMain.handle('read-file', async (_e, p) => fileMsg(p).data);
ipcMain.handle('initial-file', async () => {
  const f = pendingFile;
  pendingFile = null;
  return f ? fileMsg(f) : null;
});
ipcMain.handle('documents-dir', async () => docsDir());
ipcMain.on('add-recent', (_e, p) => {
  try {
    app.addRecentDocument(p);
  } catch {
    /* ignoré */
  }
});
ipcMain.on('show-item', (_e, p) => shell.showItemInFolder(p));
