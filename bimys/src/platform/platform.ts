// Abstraction des plateformes : Windows (Electron), Android (Capacitor) et navigateur.
import { Capacitor, registerPlugin } from '@capacitor/core';
import { Directory, Filesystem } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';

export interface NativeBridge {
  saveFile(name: string, data: ArrayBuffer, filters?: { name: string; extensions: string[] }[]): Promise<string | null>;
  openIfcDialog(): Promise<{ path: string; name: string; data: ArrayBuffer } | null>;
  readFile(path: string): Promise<ArrayBuffer>;
  getPathForFile(f: File): string;
  addRecent(path: string): void;
  onOpenFile(cb: (f: { path: string; name: string; data: ArrayBuffer }) => void): void;
  getInitialFile(): Promise<{ path: string; name: string; data: ArrayBuffer } | null>;
  documentsDir(): Promise<string>;
  showItem(path: string): void;
  version: string;
}

interface IntentPlugin {
  getPendingFile(): Promise<{ path?: string; name?: string }>;
  addListener(ev: 'fileOpened', cb: (d: { path: string; name: string }) => void): Promise<{ remove: () => void }>;
}

const native: NativeBridge | undefined = (window as any).bimysNative;
export const isElectron = !!native;
export const isAndroid = Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android';
export const platformName = isElectron ? 'Windows' : isAndroid ? 'Android' : 'Navigateur';
const Intent = isAndroid ? registerPlugin<IntentPlugin>('BimysIntent') : null;

export function electron(): NativeBridge | undefined {
  return native;
}

function toBase64(buf: Uint8Array): string {
  let s = '';
  const chunk = 0x8000;
  for (let i = 0; i < buf.length; i += chunk) s += String.fromCharCode(...buf.subarray(i, i + chunk));
  return btoa(s);
}

async function toBytes(data: Blob | Uint8Array | string): Promise<Uint8Array> {
  if (typeof data === 'string') return new TextEncoder().encode(data);
  if (data instanceof Uint8Array) return data;
  return new Uint8Array(await data.arrayBuffer());
}

export interface SaveResult {
  ok: boolean;
  path?: string;
  uri?: string;
  message: string;
}

const FILTERS: Record<string, { name: string; extensions: string[] }> = {
  pdf: { name: 'Document PDF', extensions: ['pdf'] },
  csv: { name: 'Tableur CSV', extensions: ['csv'] },
  json: { name: 'Sauvegarde JSON', extensions: ['json'] },
  png: { name: 'Image PNG', extensions: ['png'] },
};

/**
 * Enregistre un export :
 * Windows : boîte « Enregistrer sous » (Documents\Bimys par défaut, dernier dossier mémorisé) ;
 * Android : Documents/Bimys puis proposition de partage ;
 * navigateur : téléchargement.
 */
export async function saveFile(name: string, data: Blob | Uint8Array | string, mime: string): Promise<SaveResult> {
  const bytes = await toBytes(data);
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  if (native) {
    const path = await native.saveFile(name, bytes.slice().buffer, FILTERS[ext] ? [FILTERS[ext]] : undefined);
    return path ? { ok: true, path, message: `Enregistré : ${path}` } : { ok: false, message: 'Enregistrement annulé.' };
  }
  if (isAndroid) {
    const b64 = toBase64(bytes);
    try {
      const r = await Filesystem.writeFile({ path: `Bimys/${name}`, data: b64, directory: Directory.Documents, recursive: true });
      return { ok: true, uri: r.uri, path: `Documents/Bimys/${name}`, message: `Enregistré dans Documents/Bimys/${name}` };
    } catch {
      const r = await Filesystem.writeFile({ path: `Bimys/${name}`, data: b64, directory: Directory.Data, recursive: true });
      return { ok: true, uri: r.uri, path: `Bimys/${name}`, message: `Enregistré dans le stockage de l'application (${name}). Utilisez Partager pour l'envoyer.` };
    }
  }
  const blob = new Blob([bytes.slice().buffer], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return { ok: true, message: `Téléchargé : ${name}` };
}

export async function shareFile(res: SaveResult, title: string): Promise<void> {
  if (!isAndroid || !res.uri) return;
  await Share.share({ title, dialogTitle: 'Partager le fichier', files: [res.uri] });
}

export function canShare(): boolean {
  return isAndroid;
}

/** Ouvre le sélecteur de fichier IFC. */
export async function pickIfc(): Promise<{ name: string; data: ArrayBuffer; path?: string } | null> {
  if (native) return native.openIfcDialog();
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = isAndroid ? '*/*' : '.ifc,.IFC';
    input.style.display = 'none';
    document.body.appendChild(input);
    input.onchange = async () => {
      const f = input.files?.[0];
      input.remove();
      if (!f) return resolve(null);
      resolve({ name: f.name, data: await f.arrayBuffer() });
    };
    input.addEventListener('cancel', () => {
      input.remove();
      resolve(null);
    });
    input.click();
  });
}

/** Fichier reçu par « Ouvrir avec » (Android) ou passé en argument (Windows). */
export async function initialFile(): Promise<{ name: string; data: ArrayBuffer; path?: string } | null> {
  if (native) return native.getInitialFile();
  if (Intent) {
    try {
      const p = await Intent.getPendingFile();
      if (p.path) return readAndroidFile(p.path, p.name ?? 'maquette.ifc');
    } catch {
      /* rien en attente */
    }
  }
  return null;
}

async function readAndroidFile(path: string, name: string): Promise<{ name: string; data: ArrayBuffer; path: string }> {
  const url = Capacitor.convertFileSrc(path.startsWith('file://') ? path : 'file://' + path);
  const r = await fetch(url);
  return { name, data: await r.arrayBuffer(), path };
}

export function onExternalFile(cb: (f: { name: string; data: ArrayBuffer; path?: string }) => void): void {
  if (native) native.onOpenFile(cb);
  if (Intent) Intent.addListener('fileOpened', async (d) => cb(await readAndroidFile(d.path, d.name)));
}

export function exportsLocation(): string {
  if (isElectron) return 'Documents\\Bimys (modifiable dans la boîte « Enregistrer sous »)';
  if (isAndroid) return 'Documents/Bimys';
  return 'dossier de téléchargement du navigateur';
}
