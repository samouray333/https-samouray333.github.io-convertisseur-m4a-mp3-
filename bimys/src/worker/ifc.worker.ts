// Chargement IFC dans un Web Worker : l'interface reste fluide pendant la lecture.
import { IfcAPI } from 'web-ifc';
import { loadIfc } from '../core/extract';

let api: IfcAPI | null = null;

self.onmessage = async (ev: MessageEvent) => {
  const { type, bytes, fileName, wasmPath } = ev.data ?? {};
  if (type !== 'load') return;
  try {
    if (!api) {
      api = new IfcAPI();
      api.SetWasmPath(wasmPath, true);
      await api.Init(undefined, true);
    }
    const res = loadIfc(api, new Uint8Array(bytes), fileName, true, (pct, label) => (self as any).postMessage({ type: 'progress', pct, label }));
    const transfer = res.buckets.flatMap((b) => [b.positions.buffer, b.normals.buffer, b.indices.buffer, b.ranges.buffer]);
    (self as any).postMessage({ type: 'done', data: res.data, buckets: res.buckets }, transfer);
  } catch (e: any) {
    (self as any).postMessage({ type: 'error', message: String(e?.message ?? e) });
  }
};
