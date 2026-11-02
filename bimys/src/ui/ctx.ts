import type { Model } from '../core/types';
import type { MaintConfig } from '../core/maintenance';
import type { Settings } from '../store/db';
import type { Viewer } from '../viewer/viewer';

export type PageId = 'home' | 'viewer' | 'metre' | 'nomenclature' | 'deperditions' | 'coherence' | 'maintenance' | 'energie' | 'defis' | 'settings';

export interface Ctx {
  model: Model | null;
  settings: Settings;
  maint: MaintConfig;
  viewer: Viewer | null;
  version: string;
  go(page: PageId): void;
  openFile(): Promise<void>;
  openSample(name: string): Promise<void>;
  loadBytes(name: string, data: ArrayBuffer, path?: string): Promise<void>;
  /** sélectionne un élément dans la vue 3D (et l'arborescence) */
  showElement(id: number, isolate?: boolean): void;
  exportFile(name: string, data: Uint8Array | string, mime: string, title?: string): Promise<void>;
  saveSettings(s: Settings): Promise<void>;
  setMaint(c: MaintConfig): void;
  refreshMarkers(): Promise<void>;
}

export interface Page {
  el: HTMLElement;
  /** appelé à chaque affichage */
  show?(): void;
  /** appelé quand une nouvelle maquette est chargée */
  modelChanged?(): void;
  hide?(): void;
}
