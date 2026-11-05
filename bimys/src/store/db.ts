// Stockage local (IndexedDB) : réglages, interventions, saisies de déperditions, fichiers récents.
import { openDB, type IDBPDatabase } from 'idb';
import type { RoomInput } from '../core/deperditions';
import type { Intervention, MaintConfig } from '../core/maintenance';
import type { DefiResult } from '../core/defis';

export interface Settings {
  etablissement: string;
  adresse: string;
  logo: string;
  te: number;
  theme: 'auto' | 'clair' | 'sombre';
  codeProf: string;
  intervenant: string;
  chutesPct: number;
  pontsPct: number;
  seuilSous: number;
  seuilSur: number;
  couleurs: 'lot' | 'ifc';
  nbQuestions: number;
  qualite: 'auto' | 'haute' | 'standard';
  aretes: boolean;
  grille: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  etablissement: 'Lycée professionnel',
  adresse: '',
  logo: '',
  te: -10,
  theme: 'auto',
  codeProf: '1234',
  intervenant: '',
  chutesPct: 10,
  pontsPct: 10,
  seuilSous: -5,
  seuilSur: 30,
  couleurs: 'lot',
  nbQuestions: 10,
  qualite: 'auto',
  aretes: true,
  grille: true,
};

export interface RecentFile {
  id: string;
  name: string;
  size: number;
  date: number;
  path?: string;
  blob?: Blob;
}

const DB_NAME = 'bimys';
let dbp: Promise<IDBPDatabase> | null = null;

function db(): Promise<IDBPDatabase> {
  if (!dbp)
    dbp = openDB(DB_NAME, 1, {
      upgrade(d) {
        d.createObjectStore('kv');
        const it = d.createObjectStore('interventions', { keyPath: 'id' });
        it.createIndex('fileKey', 'fileKey');
        d.createObjectStore('rooms');
        d.createObjectStore('recents', { keyPath: 'id' });
        d.createObjectStore('defis', { keyPath: 'id', autoIncrement: true });
      },
    });
  return dbp;
}

export async function kvGet<T>(key: string, def: T): Promise<T> {
  try {
    const v = await (await db()).get('kv', key);
    return v === undefined ? def : (v as T);
  } catch {
    return def;
  }
}

export async function kvSet(key: string, v: unknown): Promise<void> {
  await (await db()).put('kv', v, key);
}

export async function getSettings(): Promise<Settings> {
  return { ...DEFAULT_SETTINGS, ...(await kvGet<Partial<Settings>>('settings', {})) };
}

export async function saveSettings(s: Settings): Promise<void> {
  await kvSet('settings', s);
}

export async function getMaintOverride(): Promise<MaintConfig | null> {
  return kvGet<MaintConfig | null>('maintenance', null);
}

export async function setMaintOverride(c: MaintConfig | null): Promise<void> {
  if (c === null) await (await db()).delete('kv', 'maintenance');
  else await kvSet('maintenance', c);
}

// interventions
export async function listInterventions(fileKey: string): Promise<Intervention[]> {
  return (await db()).getAllFromIndex('interventions', 'fileKey', fileKey);
}

export async function saveIntervention(i: Intervention): Promise<void> {
  await (await db()).put('interventions', i);
}

export async function deleteIntervention(id: string): Promise<void> {
  await (await db()).delete('interventions', id);
}

// saisies de déperditions
export async function getRooms(fileKey: string): Promise<Record<string, RoomInput>> {
  const d = await db();
  const out: Record<string, RoomInput> = {};
  let cur = await d.transaction('rooms').store.openCursor(IDBKeyRange.bound(fileKey + '|', fileKey + '|￿'));
  while (cur) {
    const v = cur.value as RoomInput;
    out[v.spaceGid] = v;
    cur = await cur.continue();
  }
  return out;
}

export async function saveRoom(fileKey: string, r: RoomInput): Promise<void> {
  await (await db()).put('rooms', r, `${fileKey}|${r.spaceGid}`);
}

export async function deleteRoom(fileKey: string, gid: string): Promise<void> {
  await (await db()).delete('rooms', `${fileKey}|${gid}`);
}

export async function clearRooms(fileKey: string): Promise<void> {
  await (await db()).delete('rooms', IDBKeyRange.bound(fileKey + '|', fileKey + '|￿'));
}

// fichiers récents
export async function listRecents(): Promise<RecentFile[]> {
  const all = (await (await db()).getAll('recents')) as RecentFile[];
  return all.sort((a, b) => b.date - a.date);
}

export async function addRecent(r: RecentFile): Promise<void> {
  const d = await db();
  const all = (await d.getAll('recents')) as RecentFile[];
  for (const x of all) if (x.name === r.name && x.size === r.size) await d.delete('recents', x.id);
  await d.put('recents', r);
  const sorted = [...all.filter((x) => !(x.name === r.name && x.size === r.size)), r].sort((a, b) => b.date - a.date);
  for (const x of sorted.slice(6)) await d.delete('recents', x.id);
}

export async function getRecent(id: string): Promise<RecentFile | undefined> {
  return (await db()).get('recents', id);
}

export async function removeRecent(id: string): Promise<void> {
  await (await db()).delete('recents', id);
}

// résultats des défis
export async function saveDefi(r: DefiResult): Promise<void> {
  await (await db()).add('defis', r);
}

export async function listDefis(): Promise<(DefiResult & { id: number })[]> {
  return (await db()).getAll('defis');
}

export async function clearDefis(): Promise<void> {
  await (await db()).clear('defis');
}

// ------------------------------------------------------------ sauvegarde / restauration
export interface Backup {
  app: 'Bimys';
  version: string;
  date: string;
  kv: Record<string, unknown>;
  interventions: Intervention[];
  rooms: Record<string, RoomInput>;
  defis: DefiResult[];
}

export async function exportBackup(version: string): Promise<Backup> {
  const d = await db();
  const kv: Record<string, unknown> = {};
  const keys = await d.getAllKeys('kv');
  for (const k of keys) kv[String(k)] = await d.get('kv', k);
  const rooms: Record<string, RoomInput> = {};
  const rk = await d.getAllKeys('rooms');
  for (const k of rk) rooms[String(k)] = await d.get('rooms', k);
  const defis = ((await d.getAll('defis')) as (DefiResult & { id?: number })[]).map(({ id: _id, ...r }) => r as DefiResult);
  return { app: 'Bimys', version, date: new Date().toISOString(), kv, interventions: await d.getAll('interventions'), rooms, defis };
}

export async function importBackup(b: Backup, replace: boolean): Promise<{ interventions: number; rooms: number }> {
  if (!b || b.app !== 'Bimys') throw new Error("Ce fichier n'est pas une sauvegarde Bimys.");
  const d = await db();
  const tx = d.transaction(['kv', 'interventions', 'rooms', 'defis'], 'readwrite');
  if (replace) {
    await tx.objectStore('kv').clear();
    await tx.objectStore('interventions').clear();
    await tx.objectStore('rooms').clear();
    await tx.objectStore('defis').clear();
  }
  for (const [k, v] of Object.entries(b.kv ?? {})) await tx.objectStore('kv').put(v, k);
  for (const i of b.interventions ?? []) await tx.objectStore('interventions').put(i);
  for (const [k, v] of Object.entries(b.rooms ?? {})) await tx.objectStore('rooms').put(v, k);
  for (const r of b.defis ?? []) await tx.objectStore('defis').add(r);
  await tx.done;
  return { interventions: (b.interventions ?? []).length, rooms: Object.keys(b.rooms ?? {}).length };
}
