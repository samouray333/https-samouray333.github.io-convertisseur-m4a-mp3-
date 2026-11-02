// Pont sécurisé entre l'interface et Windows (contextIsolation).
const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('bimysNative', {
  saveFile: (name, data, filters) => ipcRenderer.invoke('save-file', name, data, filters),
  openIfcDialog: () => ipcRenderer.invoke('open-ifc'),
  readFile: (p) => ipcRenderer.invoke('read-file', p),
  getPathForFile: (f) => webUtils.getPathForFile(f),
  addRecent: (p) => ipcRenderer.send('add-recent', p),
  onOpenFile: (cb) => ipcRenderer.on('open-file', (_e, f) => cb(f)),
  onMenu: (cb) => ipcRenderer.on('menu', (_e, cmd) => cb(cmd)),
  getInitialFile: () => ipcRenderer.invoke('initial-file'),
  documentsDir: () => ipcRenderer.invoke('documents-dir'),
  showItem: (p) => ipcRenderer.send('show-item', p),
  setSoftwareRendering: (on) => ipcRenderer.send('software-rendering', on),
  setModelOpen: (open) => ipcRenderer.send('model-open', open),
  info: () => ipcRenderer.invoke('info'),
  log: (level, msg) => ipcRenderer.send('log', level, String(msg)),
  version: '',
});
