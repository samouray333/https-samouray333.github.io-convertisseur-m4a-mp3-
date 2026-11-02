import * as W from 'web-ifc';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { loadIfc } from '../src/core/extract';
import { Model } from '../src/core/types';

let api: W.IfcAPI | null = null;
const cache = new Map<string, Model>();

export async function loadSample(name: 'maison_chaudiere_gaz.ifc' | 'maison_pac_air_eau.ifc'): Promise<Model> {
  if (cache.has(name)) return cache.get(name)!;
  if (!api) {
    api = new W.IfcAPI();
    api.SetWasmPath(resolve(__dirname, '../node_modules/web-ifc') + '/', true);
    await api.Init();
  }
  const bytes = new Uint8Array(readFileSync(resolve(__dirname, '../public/samples', name)));
  const { data } = loadIfc(api, bytes, name, false);
  const m = new Model(data);
  cache.set(name, m);
  return m;
}
