// Pont sécurisé entre l'interface et l'application de bureau.
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('tyShell', {
  openFile: p => ipcRenderer.invoke('openFile', p),
  showInFolder: p => ipcRenderer.invoke('showInFolder', p),
  chooseFolder: cur => ipcRenderer.invoke('chooseFolder', cur),
  readClipboard: () => ipcRenderer.invoke('readClipboard'),
  copy: t => ipcRenderer.invoke('copy', t),
  applySettings: s => ipcRenderer.invoke('applySettings', s),
});
