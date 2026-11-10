// Types partagés entre le worker, l'interface et les tests.

export type PropValue = string | number | boolean | null;
export type PropSet = Record<string, PropValue>;

export type LotId =
  | 'archi'
  | 'espaces'
  | 'chauffage'
  | 'ecs'
  | 'ef'
  | 'ventilation'
  | 'froid'
  | 'equipements'
  | 'electrique'
  | 'autres';

/** Boîte englobante en coordonnées IFC (x est, y nord, z haut), en mètres. */
export type BBox = [number, number, number, number, number, number];

export interface Profile {
  kind: 'circle' | 'rect';
  /** diamètre extérieur (m) pour un profil circulaire */
  d?: number;
  /** épaisseur de paroi (m) si profil creux */
  wall?: number;
  w?: number;
  h?: number;
}

export interface El {
  id: number;
  gid: string;
  cls: string;
  name: string;
  objectType: string;
  desc: string;
  predefined: string;
  typeName: string;
  storeyId: number | null;
  spaceId: number | null;
  systemIds: number[];
  psets: Record<string, PropSet>;
  qtos: Record<string, Record<string, number>>;
  materials: string[];
  lot: LotId;
  bbox: BBox | null;
  /** longueur d'axe pour les segments (m) : quantité IFC ou profondeur d'extrusion */
  length: number | null;
  profile: Profile | null;
  hasGeometry: boolean;
}

export interface SystemInfo {
  id: number;
  gid: string;
  name: string;
  predefined: string;
  cls: string;
  lot: LotId;
  members: number[];
}

export interface StoreyInfo {
  id: number;
  gid: string;
  name: string;
  elevation: number;
}

export interface SpaceBoundary {
  spaceId: number;
  elementId: number | null;
  /** surface nette (contour extérieur moins contours intérieurs), m² */
  area: number;
  /** surface brute du contour extérieur, m² */
  gross: number;
  external: boolean;
  /** composante z de la normale du plan (orientation IFC), 0 si inconnue */
  normalZ: number;
}

export interface TreeNode {
  id: number;
  cls: string;
  name: string;
  children: TreeNode[];
}

export interface ModelData {
  fileName: string;
  schema: string;
  projectGid: string;
  projectName: string;
  lengthScale: number;
  elements: El[];
  systems: SystemInfo[];
  storeys: StoreyInfo[];
  boundaries: SpaceBoundary[];
  tree: TreeNode | null;
  /** matrice de coordination appliquée par web-ifc (repère three, y vers le haut) */
  coord?: number[];
}

/** Index pratique construit côté interface. */
export class Model {
  readonly data: ModelData;
  readonly byId = new Map<number, El>();
  readonly byGid = new Map<string, El>();
  readonly systemById = new Map<number, SystemInfo>();
  readonly storeyById = new Map<number, StoreyInfo>();

  constructor(data: ModelData) {
    this.data = data;
    for (const e of data.elements) {
      this.byId.set(e.id, e);
      this.byGid.set(e.gid, e);
    }
    for (const s of data.systems) this.systemById.set(s.id, s);
    for (const s of data.storeys) this.storeyById.set(s.id, s);
  }

  get elements(): El[] {
    return this.data.elements;
  }

  ofClass(...cls: string[]): El[] {
    const set = new Set(cls.map((c) => c.toLowerCase()));
    return this.data.elements.filter((e) => set.has(e.cls.toLowerCase()));
  }

  spaces(): El[] {
    return this.ofClass('IfcSpace');
  }

  systemNames(e: El): string[] {
    return e.systemIds.map((id) => this.systemById.get(id)?.name ?? '').filter(Boolean);
  }

  /** Décalage vertical (repère three) entre l'altitude IFC et la géométrie affichée. */
  get yOffset(): number {
    const c = this.data.coord;
    return c && c.length === 16 ? c[13] : 0;
  }

  /** Clé de rattachement des données locales (interventions, saisies). */
  get fileKey(): string {
    return this.data.projectGid || this.data.fileName;
  }
}

/** Géométrie fusionnée transmise par le worker. */
export interface GeoBucket {
  key: string;
  lot: LotId;
  /** tronçons et raccords de réseaux (couleur franche du lot) ; sinon équipements et bâti */
  run?: boolean;
  color: [number, number, number, number];
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
  /** pour chaque élément : id, début (indice), nombre d'indices */
  ranges: Int32Array;
}
