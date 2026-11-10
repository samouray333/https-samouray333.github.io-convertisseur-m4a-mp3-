// Vue 3D three.js : géométrie fusionnée par lot/couleur, sélection multiple, masquage, coupes,
// mesure aimantée, caméra perspective ou orthographique, cube de navigation.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CSS3DObject, CSS3DRenderer } from 'three/examples/jsm/renderers/CSS3DRenderer.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/examples/jsm/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { acceleratedRaycast, computeBoundsTree, disposeBoundsTree } from 'three-mesh-bvh';
import { LOT_BY_ID } from '../core/lots';
import type { GeoBucket, LotId } from '../core/types';

(THREE.BufferGeometry.prototype as any).computeBoundsTree = computeBoundsTree;
(THREE.BufferGeometry.prototype as any).disposeBoundsTree = disposeBoundsTree;
THREE.Mesh.prototype.raycast = acceleratedRaycast;

interface BucketRT {
  data: GeoBucket;
  mesh: THREE.Mesh;
  geom: THREE.BufferGeometry;
  mat: THREE.MeshLambertMaterial | THREE.MeshStandardMaterial;
  /** arêtes de l'élément (lignes), avec leurs plages par élément */
  edges: { lines: THREE.LineSegments; ranges: Int32Array } | null;
  /** index courant (éléments visibles) : débuts et ids, pour retrouver l'élément touché */
  visStarts: Int32Array;
  visIds: Int32Array;
  bvhDirty: boolean;
}

export type ViewName = 'dessus' | 'dessous' | 'face' | 'nord' | 'droite' | 'ouest' | 'iso';
export type Projection = 'perspective' | 'orthographic';

/** Directions de vue dans le repère three (y vers le haut, z vers le sud). */
export const VIEW_DIRS: Record<ViewName, [number, number, number]> = {
  dessus: [0, 1, 0.0001],
  dessous: [0, -1, 0.0001],
  face: [0, 0.05, 1],
  nord: [0, 0.05, -1],
  droite: [1, 0.05, 0],
  ouest: [-1, 0.05, 0],
  iso: [1, 0.9, 1],
};

export type Quality = 'haute' | 'standard';

const PIPE_LOTS = new Set(['chauffage', 'ecs', 'ef', 'froid']);
const EDGE_LOTS = new Set(['archi', 'equipements', 'autres']);

export interface CameraState {
  position: [number, number, number];
  target: [number, number, number];
  projection: Projection;
  zoom: number;
}

export interface ViewerEvents {
  onSelect?: (id: number | null, additive: boolean) => void;
  onMeasure?: (d: number | null) => void;
  onContextMenu?: (id: number | null, x: number, y: number) => void;
  onHover?: (id: number | null, x: number, y: number) => void;
  onCamera?: () => void;
}

const SEL_COLOR = 0x22d3ee;
const TMP_COLOR = new THREE.Color();
/** seau composé de tronçons (tubes, gaines) et non d'équipements : marqué par le worker */
const data_isRun = (d: GeoBucket) => d.run === true;

export class Viewer {
  readonly container: HTMLElement;
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly persp: THREE.PerspectiveCamera;
  readonly ortho: THREE.OrthographicCamera;
  camera: THREE.PerspectiveCamera | THREE.OrthographicCamera;
  readonly controls: OrbitControls;
  private buckets: BucketRT[] = [];
  private elementRanges = new Map<number, { b: BucketRT; start: number; count: number }[]>();
  private hidden = new Set<number>();
  private isolated: Set<number> | null = null;
  private lotVisible: Record<string, boolean> = {};
  private colorMode: 'lot' | 'ifc' = 'lot';
  private archiTransparent = false;
  private selectedSet = new Set<number>();
  private primary: number | null = null;
  private selMesh: THREE.Mesh | null = null;
  private markers = new THREE.Group();
  private measureGroup = new THREE.Group();
  private measurePts: THREE.Vector3[] = [];
  private measureLabel: HTMLDivElement;
  private needsRender = true;
  private raycaster = new THREE.Raycaster();
  private modelBox = new THREE.Box3();
  private planeLevelTop = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
  private planeLevelBottom = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private planeFree = new THREE.Plane(new THREE.Vector3(1, 0, 0), 0);
  private levelCut: { bottom: number; top: number } | null = null;
  private freeCut: { axis: 'x' | 'y' | 'z'; t: number; flip: boolean } | null = null;
  private freeHelper: THREE.Mesh | null = null;
  private snapMarker: THREE.Mesh | null = null;
  measuring = false;
  hoverEnabled = false;
  events: ViewerEvents = {};
  private disposed = false;
  private ro: ResizeObserver;
  private lowPower: boolean;
  // cube de navigation
  quality: Quality;
  private composer: EffectComposer | null = null;
  private renderPass: RenderPass | null = null;
  private gtao: GTAOPass | null = null;
  private envMap: THREE.Texture | null = null;
  private lights: { hemi: THREE.HemisphereLight; dir: THREE.DirectionalLight; dir2: THREE.DirectionalLight } | null = null;
  private edgesOn = true;
  private edgeColor = new THREE.Color(0x2b3a40);
  private grid: THREE.Group | null = null;
  private gridOn = true;
  private ground: THREE.Mesh | null = null;
  private shadowsOn = true;
  private shadowDirty = true;
  private planStyleOn = false;
  private cubeRenderer: CSS3DRenderer | null = null;
  private cubeScene = new THREE.Scene();
  private cubeCamera = new THREE.PerspectiveCamera(50, 1, 1, 1000);

  constructor(container: HTMLElement) {
    this.container = container;
    this.lowPower = matchMedia('(pointer: coarse)').matches;
    this.quality = this.lowPower ? 'standard' : 'haute';
    // lève une exception si WebGL est indisponible : l'appelant affiche un repli
    this.renderer = new THREE.WebGLRenderer({ antialias: !this.lowPower, alpha: false, powerPreference: 'default', preserveDrawingBuffer: true, failIfMajorPerformanceCaveat: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.lowPower ? 1.75 : 2));
    this.renderer.localClippingEnabled = false;
    this.renderer.toneMapping = THREE.NeutralToneMapping;
    this.renderer.toneMappingExposure = 1.0;
    this.renderer.domElement.className = 'viewer-canvas';
    container.appendChild(this.renderer.domElement);
    this.persp = new THREE.PerspectiveCamera(45, 1, 0.05, 5000);
    this.persp.position.set(15, 12, 15);
    this.ortho = new THREE.OrthographicCamera(-10, 10, 10, -10, -5000, 5000);
    this.camera = this.persp;
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.screenSpacePanning = true;
    this.controls.zoomToCursor = true;
    this.controls.addEventListener('change', () => {
      this.requestRender(false);
      this.events.onCamera?.();
    });
    const hemi = new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6);
    const dir = new THREE.DirectionalLight(0xfff4e2, 1.4);
    dir.position.set(10, 20, 8);
    dir.shadow.mapSize.set(2048, 2048);
    dir.shadow.bias = -0.0004;
    dir.shadow.normalBias = 0.03;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.shadowMap.autoUpdate = false;
    this.scene.add(dir.target);
    const dir2 = new THREE.DirectionalLight(0xffffff, 0.5);
    dir2.position.set(-10, 6, -12);
    this.lights = { hemi, dir, dir2 };
    this.scene.add(hemi, dir, dir2, this.markers, this.measureGroup);
    this.measureLabel = document.createElement('div');
    this.measureLabel.className = 'measure-label';
    this.measureLabel.hidden = true;
    container.appendChild(this.measureLabel);
    this.setBackground(getComputedStyle(document.documentElement).getPropertyValue('--viewer-bg').trim() || '#e9eef0');
    this.renderer.domElement.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      console.warn('Contexte WebGL perdu');
    });
    this.renderer.domElement.addEventListener('webglcontextrestored', () => this.requestRender());
    this.installPointer();
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(container);
    this.resize();
    const loop = () => {
      if (this.disposed) return;
      if (this.needsRender && this.container.offsetParent !== null) {
        this.needsRender = false;
        this.renderFrame();
        this.updateMeasureLabel();
        this.renderCube();
      }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
    this.applyQuality();
  }

  // ------------------------------------------------------------ qualité de rendu
  /** Haute (PC) : matériaux physiques, éclairage d'environnement, occlusion ambiante. Standard (téléphone) : léger. */
  autoQuality(): Quality {
    return this.lowPower ? 'standard' : 'haute';
  }

  setQuality(q: Quality) {
    if (q === this.quality && (q === 'standard' || this.composer)) return;
    this.quality = q;
    this.applyQuality();
    for (const b of this.buckets) {
      const old = b.mat;
      b.mat = this.makeMaterial(b.data);
      if (!this.planMats.has(b)) b.mesh.material = b.mat;
      else this.planMats.set(b, b.mat);
      old.dispose();
    }
    this.applyMaterials();
  }

  private applyQuality() {
    const high = this.quality === 'haute';
    if (high && !this.envMap) {
      const pm = new THREE.PMREMGenerator(this.renderer);
      this.envMap = pm.fromScene(new RoomEnvironment(), 0.04).texture;
      pm.dispose();
    }
    this.scene.environment = high ? this.envMap : null;
    (this.scene as any).environmentIntensity = 0.55;
    if (this.lights) {
      this.lights.hemi.intensity = high ? 0.75 : 2.3;
      this.lights.dir.intensity = high ? 2.1 : 1.7;
      this.lights.dir2.intensity = high ? 0.3 : 0.9;
    }
    if (high && !this.composer) {
      const w = this.container.clientWidth || 1;
      const h = this.container.clientHeight || 1;
      const pr = this.renderer.getPixelRatio();
      const rt = new THREE.WebGLRenderTarget(w * pr, h * pr, { type: THREE.HalfFloatType, samples: 4 });
      this.composer = new EffectComposer(this.renderer, rt);
      this.renderPass = new RenderPass(this.scene, this.camera);
      this.gtao = new GTAOPass(this.scene, this.camera, w, h);
      this.gtao.blendIntensity = 0.85;
      this.composer.addPass(this.renderPass);
      this.composer.addPass(this.gtao);
      this.composer.addPass(new OutputPass());
      this.composer.setPixelRatio(this.renderer.getPixelRatio());
      this.composer.setSize(w, h);
    }
    this.requestRender();
  }

  private makeMaterial(d: GeoBucket): THREE.MeshLambertMaterial | THREE.MeshStandardMaterial {
    if (this.quality === 'standard') return new THREE.MeshLambertMaterial({ side: THREE.DoubleSide });
    const glass = d.lot === 'archi' && d.color[3] < 0.99;
    if (glass) return new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, roughness: 0.05, metalness: 0.0, envMapIntensity: 2.2 });
    if (d.run) return new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, roughness: 0.4, metalness: 0.3 });
    if (d.lot === 'archi' || d.lot === 'espaces') return new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, roughness: 0.86, metalness: 0.0 });
    // équipements : tôle laquée, laiton et inox un peu plus brillants
    const [r, g, b] = d.color;
    const metal = Math.abs(r - g) > 0.12 || (Math.abs(r - b) < 0.06 && r > 0.6 && r < 0.9);
    return new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, roughness: metal ? 0.38 : 0.55, metalness: metal ? 0.45 : 0.08 });
  }

  /** l'occlusion ambiante est coupée en transparence et en plan (rendu plus lisible) */
  private renderFrame() {
    const sh = this.quality === 'haute' && this.shadowsOn && !this.planStyleOn;
    if (this.renderer.shadowMap.enabled !== sh) {
      this.renderer.shadowMap.enabled = sh;
      this.shadowDirty = true;
      for (const b of this.buckets) b.mat.needsUpdate = true;
    }
    if (this.lights) this.lights.dir.castShadow = sh;
    if (this.ground) this.ground.visible = sh && this.camera.position.y > this.ground.position.y;
    if (sh && this.shadowDirty) this.renderer.shadowMap.needsUpdate = true;
    this.shadowDirty = false;
    const useAO = this.quality === 'haute' && this.composer && !this.archiTransparent && !this.planStyleOn;
    if (useAO && this.composer && this.renderPass && this.gtao) {
      this.renderPass.camera = this.camera;
      this.gtao.camera = this.camera;
      (this.gtao as any).gtaoMaterial && ((this.gtao as any).gtaoMaterial.needsUpdate = false);
      this.composer.render();
    } else {
      this.renderer.render(this.scene, this.camera);
    }
  }

  setEdges(on: boolean) {
    this.edgesOn = on;
    for (const b of this.buckets) if (b.edges) b.edges.lines.visible = on && b.mesh.visible;
    this.requestRender();
  }

  get edgesVisible(): boolean {
    return this.edgesOn;
  }

  /** fond dégradé (plus clair en haut) ; la couleur des arêtes suit le thème */
  setBackground(color: string) {
    const base = new THREE.Color(color);
    const hsl = { h: 0, s: 0, l: 0 };
    base.getHSL(hsl);
    const dark = hsl.l < 0.4;
    const top = base.clone().offsetHSL(0, -0.02, dark ? 0.06 : 0.07);
    const bottom = base.clone().offsetHSL(0, 0.0, dark ? -0.04 : -0.05);
    const c = document.createElement('canvas');
    c.width = 4;
    c.height = 256;
    const g = c.getContext('2d')!;
    const grad = g.createLinearGradient(0, 0, 0, 256);
    grad.addColorStop(0, `#${top.getHexString()}`);
    grad.addColorStop(1, `#${bottom.getHexString()}`);
    g.fillStyle = grad;
    g.fillRect(0, 0, 4, 256);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    (this.scene.background as THREE.Texture | null)?.dispose?.();
    this.scene.background = tex;
    this.edgeColor.set(dark ? 0xc8d6db : 0x24343a);
    for (const b of this.buckets) if (b.edges) (b.edges.lines.material as THREE.LineBasicMaterial).color.copy(this.edgeColor);
    if (this.grid) this.buildGrid();
    this.requestRender();
  }

  /** grille au sol discrète sous la maquette */
  private buildGrid() {
    if (this.grid) {
      this.scene.remove(this.grid);
      this.grid.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        (m.material as THREE.Material)?.dispose?.();
      });
    }
    const size = this.modelBox.getSize(new THREE.Vector3());
    const c = this.modelBox.getCenter(new THREE.Vector3());
    const ext = Math.ceil(Math.max(size.x, size.z) * 1.8 + 6);
    const step = ext > 120 ? 5 : ext > 50 ? 2 : 1;
    const dark = this.edgeColor.r > 0.5;
    const grid = new THREE.GridHelper(ext, Math.round(ext / step), dark ? 0x5a6e75 : 0x9fb0b6, dark ? 0x34444a : 0xc9d4d8);
    const gm = grid.material as THREE.LineBasicMaterial;
    gm.transparent = true;
    gm.opacity = 0.55;
    gm.depthWrite = false;
    const group = new THREE.Group();
    group.add(grid);
    group.position.set(Math.round(c.x), this.modelBox.min.y - 0.02, Math.round(c.z));
    group.renderOrder = -1;
    group.visible = this.gridOn;
    this.grid = group;
    this.scene.add(group);
    // sol invisible qui reçoit l'ombre portée du bâtiment
    if (this.ground) {
      this.scene.remove(this.ground);
      this.ground.geometry.dispose();
      (this.ground.material as THREE.Material).dispose();
    }
    const gr = new THREE.Mesh(new THREE.PlaneGeometry(ext * 3, ext * 3), new THREE.ShadowMaterial({ opacity: dark ? 0.35 : 0.22, depthWrite: false }));
    gr.rotation.x = -Math.PI / 2;
    gr.position.set(c.x, this.modelBox.min.y - 0.03, c.z);
    gr.receiveShadow = true;
    gr.renderOrder = -2;
    this.ground = gr;
    this.scene.add(gr);
    // soleil : cadrage de la carte d'ombres sur la maquette
    if (this.lights) {
      const d = this.lights.dir;
      const rad = Math.max(4, size.length() / 2) * 1.15;
      d.target.position.copy(c);
      d.position.copy(c).add(new THREE.Vector3(-0.38, 0.8, 0.46).normalize().multiplyScalar(rad * 2));
      const cam = d.shadow.camera;
      cam.left = cam.bottom = -rad;
      cam.right = cam.top = rad;
      cam.near = rad * 0.2;
      cam.far = rad * 4;
      cam.updateProjectionMatrix();
      const big = rad > 30;
      if (d.shadow.mapSize.x !== (big ? 4096 : 2048)) {
        d.shadow.mapSize.set(big ? 4096 : 2048, big ? 4096 : 2048);
        d.shadow.map?.dispose();
        d.shadow.map = null as any;
      }
      d.shadow.normalBias = Math.max(0.02, rad / 600);
    }
  }

  setShadows(v: boolean) {
    this.shadowsOn = v;
    this.requestRender();
  }

  setGridVisible(v: boolean) {
    this.gridOn = v;
    if (this.grid) this.grid.visible = v;
    this.requestRender();
  }

  /** `shadows` = false quand seule la caméra a bougé : la carte d'ombres est conservée */
  requestRender(shadows = true) {
    if (shadows) this.shadowDirty = true;
    this.needsRender = true;
  }

  resize() {
    const w = this.container.clientWidth || 1;
    const h = this.container.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.composer?.setSize(w, h);
    this.persp.aspect = w / h;
    this.persp.updateProjectionMatrix();
    this.updateOrthoFrustum();
    this.requestRender();
  }

  dispose() {
    this.disposed = true;
    this.ro.disconnect();
    this.clear();
    this.renderer.dispose();
  }

  clear() {
    for (const b of this.buckets) {
      this.scene.remove(b.mesh);
      (b.geom as any).disposeBoundsTree?.();
      b.geom.dispose();
      b.mat.dispose();
      if (b.edges) {
        this.scene.remove(b.edges.lines);
        b.edges.lines.geometry.dispose();
        (b.edges.lines.material as THREE.Material).dispose();
      }
    }
    this.edgeJob++;
    this.buckets = [];
    this.elementRanges.clear();
    this.hidden.clear();
    this.isolated = null;
    this.selectedSet.clear();
    this.primary = null;
    this.clearSelectionMesh();
    this.clearMarkers();
    this.clearMeasure();
    this.requestRender();
  }

  // ------------------------------------------------------------ chargement
  load(buckets: GeoBucket[]) {
    this.clear();
    this.modelBox.makeEmpty();
    for (const data of buckets) {
      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.BufferAttribute(data.positions, 3));
      geom.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3));
      geom.setIndex(new THREE.BufferAttribute(data.indices.slice(), 1));
      geom.computeBoundingBox();
      geom.computeBoundingSphere();
      const mat = this.makeMaterial(data);
      const mesh = new THREE.Mesh(geom, mat);
      mesh.matrixAutoUpdate = false;
      const rt: BucketRT = { data, mesh, geom, mat, edges: null, visStarts: new Int32Array(0), visIds: new Int32Array(0), bvhDirty: true };
      for (let i = 0; i < data.ranges.length; i += 3) {
        const id = data.ranges[i];
        if (!this.elementRanges.has(id)) this.elementRanges.set(id, []);
        this.elementRanges.get(id)!.push({ b: rt, start: data.ranges[i + 1], count: data.ranges[i + 2] });
      }
      if (data.lot !== 'espaces' && geom.boundingBox) this.modelBox.union(geom.boundingBox);
      this.buckets.push(rt);
      this.scene.add(mesh);
    }
    if (this.modelBox.isEmpty()) this.modelBox.set(new THREE.Vector3(-5, -5, -5), new THREE.Vector3(5, 5, 5));
    const size = this.modelBox.getSize(new THREE.Vector3()).length();
    this.persp.near = Math.max(0.01, size / 2000);
    this.persp.far = size * 20 + 100;
    this.persp.updateProjectionMatrix();
    this.ortho.near = -size * 20 - 100;
    this.ortho.far = size * 20 + 100;
    for (const b of this.buckets) this.rebuildIndex(b);
    this.applyMaterials();
    this.buildGrid();
    if (this.gtao) {
      const r = Math.max(0.25, Math.min(1.2, size / 40));
      this.gtao.updateGtaoMaterial({ radius: r, distanceExponent: 1.5, thickness: 1.0, scale: 1.0, samples: 16 });
      this.gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 6, rings: 2, samples: 16 });
    }
    this.setView('iso');
    // les arêtes sont calculées juste après le premier affichage pour ne pas retarder l'ouverture
    const job = ++this.edgeJob;
    setTimeout(() => {
      if (job === this.edgeJob) this.buildEdges();
    }, 30);
  }

  private edgeJob = 0;

  /** arêtes vives (angle > 30°) des murs, dalles, menuiseries et équipements, par élément */
  private buildEdges() {
    const tmp = new THREE.BufferGeometry();
    for (const b of this.buckets) {
      if ((!EDGE_LOTS.has(b.data.lot) && b.data.run !== false) || b.data.lot === 'espaces' || b.data.indices.length > 1_800_000) continue;
      const P = b.data.positions, I = b.data.indices, r = b.data.ranges;
      const chunks: Float32Array[] = [];
      const ranges: number[] = [];
      let nv = 0;
      for (let i = 0; i < r.length; i += 3) {
        const start = r[i + 1], count = r[i + 2];
        const pos = new Float32Array(count * 3);
        for (let k = 0; k < count; k++) {
          const v = I[start + k] * 3;
          pos[k * 3] = P[v];
          pos[k * 3 + 1] = P[v + 1];
          pos[k * 3 + 2] = P[v + 2];
        }
        tmp.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        const eg = new THREE.EdgesGeometry(tmp, 30);
        const ep = eg.getAttribute('position').array as Float32Array;
        eg.dispose();
        if (!ep.length) continue;
        ranges.push(r[i], nv, ep.length / 3);
        chunks.push(ep);
        nv += ep.length / 3;
      }
      if (!nv) continue;
      const all = new Float32Array(nv * 3);
      let o = 0;
      for (const c of chunks) {
        all.set(c, o);
        o += c.length;
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(all, 3));
      const mat = new THREE.LineBasicMaterial({ color: this.edgeColor, transparent: true, opacity: b.data.lot === 'archi' ? 0.42 : 0.3, depthWrite: false });
      const lines = new THREE.LineSegments(g, mat);
      lines.matrixAutoUpdate = false;
      lines.renderOrder = 3;
      b.edges = { lines, ranges: Int32Array.from(ranges) };
      this.rebuildEdgeIndex(b);
      lines.visible = this.edgesOn && b.mesh.visible;
      this.scene.add(lines);
    }
    tmp.dispose();
    this.requestRender();
  }

  private rebuildEdgeIndex(b: BucketRT) {
    if (!b.edges) return;
    const r = b.edges.ranges;
    let total = 0;
    for (let i = 0; i < r.length; i += 3) if (this.isVisible(r[i])) total += r[i + 2];
    const idx = new Uint32Array(total);
    let o = 0;
    for (let i = 0; i < r.length; i += 3) {
      if (!this.isVisible(r[i])) continue;
      for (let k = 0; k < r[i + 2]; k++) idx[o++] = r[i + 1] + k;
    }
    b.edges.lines.geometry.setIndex(new THREE.BufferAttribute(idx, 1));
  }

  get bounds(): THREE.Box3 {
    return this.modelBox.clone();
  }

  get elementCount(): number {
    return this.elementRanges.size;
  }

  // ------------------------------------------------------------ apparence
  setLotVisible(lot: LotId, v: boolean) {
    this.lotVisible[lot] = v;
    for (const b of this.buckets) if (b.data.lot === lot) {
      b.mesh.visible = v;
      if (b.edges) b.edges.lines.visible = v && this.edgesOn;
    }
    this.requestRender();
  }

  setLotVisibility(map: Record<string, boolean>) {
    this.lotVisible = { ...map };
    for (const b of this.buckets) {
      b.mesh.visible = map[b.data.lot] !== false;
      if (b.edges) b.edges.lines.visible = b.mesh.visible && this.edgesOn;
    }
    this.requestRender();
  }

  setColorMode(m: 'lot' | 'ifc') {
    this.colorMode = m;
    this.applyMaterials();
  }

  setArchiTransparent(t: boolean) {
    this.archiTransparent = t;
    this.applyMaterials();
  }

  private applyMaterials() {
    for (const b of this.buckets) {
      const lot = b.data.lot;
      const [r, g, bl, a] = b.data.color;
      const mat = b.mat;
      const useLot = this.colorMode === 'lot' && lot !== 'archi' && lot !== 'autres';
      mat.color.setRGB(r, g, bl, THREE.SRGBColorSpace);
      // tuyaux et gaines : couleur franche du lot ; équipements : teinte du lot qui garde le détail des pièces
      if (useLot) {
        if (data_isRun(b.data)) mat.color.set(LOT_BY_ID[lot].color);
        else mat.color.lerp(TMP_COLOR.set(LOT_BY_ID[lot].color), 0.22);
      }
      let opacity = a;
      if (lot === 'espaces') opacity = Math.min(a, 0.18);
      if (lot === 'archi' && this.archiTransparent) opacity = Math.min(a, 0.18);
      mat.transparent = opacity < 0.99;
      mat.opacity = opacity;
      mat.depthWrite = opacity >= 0.99;
      // décalage de profondeur : les arêtes restent nettes sans scintillement
      mat.polygonOffset = !mat.transparent;
      mat.polygonOffsetFactor = lot === 'archi' ? 1.5 : 1;
      mat.polygonOffsetUnits = 1;
      b.mesh.renderOrder = mat.transparent ? 2 : lot === 'archi' ? 0 : 1;
      b.mesh.castShadow = !mat.transparent;
      b.mesh.receiveShadow = !mat.transparent;
      mat.needsUpdate = true;
      b.mesh.visible = this.lotVisible[lot] !== undefined ? this.lotVisible[lot] : LOT_BY_ID[lot]?.visible !== false;
      if (b.edges) {
        b.edges.lines.visible = b.mesh.visible && this.edgesOn;
        (b.edges.lines.material as THREE.LineBasicMaterial).opacity = lot === 'archi' ? (this.archiTransparent ? 0.28 : 0.42) : 0.3;
      }
    }
    this.requestRender();
  }

  // ------------------------------------------------------------ visibilité par élément
  private isVisible(id: number): boolean {
    if (this.hidden.has(id)) return false;
    if (this.isolated && !this.isolated.has(id)) return false;
    return true;
  }

  private rebuildIndex(b: BucketRT) {
    const r = b.data.ranges;
    let total = 0;
    let n = 0;
    for (let i = 0; i < r.length; i += 3) if (this.isVisible(r[i])) {
      total += r[i + 2];
      n++;
    }
    const idx = new Uint32Array(total);
    const starts = new Int32Array(n);
    const ids = new Int32Array(n);
    let o = 0, k = 0;
    const src = b.data.indices;
    for (let i = 0; i < r.length; i += 3) {
      if (!this.isVisible(r[i])) continue;
      starts[k] = o;
      ids[k] = r[i];
      k++;
      idx.set(src.subarray(r[i + 1], r[i + 1] + r[i + 2]), o);
      o += r[i + 2];
    }
    (b.geom as any).disposeBoundsTree?.();
    b.geom.setIndex(new THREE.BufferAttribute(idx, 1));
    b.visStarts = starts;
    b.visIds = ids;
    b.bvhDirty = true;
  }

  private refreshVisibility() {
    for (const b of this.buckets) {
      this.rebuildIndex(b);
      this.rebuildEdgeIndex(b);
    }
    this.requestRender();
  }

  hide(ids: number[]) {
    for (const id of ids) this.hidden.add(id);
    const remaining = [...this.selectedSet].filter((id) => !ids.includes(id));
    if (remaining.length !== this.selectedSet.size) this.setSelection(remaining);
    this.refreshVisibility();
  }

  isolate(ids: number[]) {
    this.isolated = new Set(ids);
    this.hidden.clear();
    this.refreshVisibility();
  }

  showAll() {
    this.hidden.clear();
    this.isolated = null;
    this.refreshVisibility();
  }

  get isIsolating(): boolean {
    return this.isolated !== null || this.hidden.size > 0;
  }

  get visibilityState(): { hidden: number[]; isolated: number[] | null } {
    return { hidden: [...this.hidden], isolated: this.isolated ? [...this.isolated] : null };
  }

  setVisibilityState(s: { hidden: number[]; isolated: number[] | null }) {
    this.hidden = new Set(s.hidden);
    this.isolated = s.isolated ? new Set(s.isolated) : null;
    this.refreshVisibility();
  }

  hasGeometry(id: number): boolean {
    return this.elementRanges.has(id);
  }

  // ------------------------------------------------------------ sélection
  private subsetGeometry(ids: number[]): THREE.BufferGeometry | null {
    const parts: { b: BucketRT; start: number; count: number }[] = [];
    for (const id of ids) parts.push(...(this.elementRanges.get(id) ?? []));
    if (!parts.length) return null;
    const total = parts.reduce((s, p) => s + p.count, 0);
    const pos = new Float32Array(total * 3);
    const nor = new Float32Array(total * 3);
    let o = 0;
    for (const p of parts) {
      const P = p.b.data.positions, N = p.b.data.normals, I = p.b.data.indices;
      for (let i = p.start; i < p.start + p.count; i++) {
        const v = I[i] * 3;
        pos[o] = P[v]; pos[o + 1] = P[v + 1]; pos[o + 2] = P[v + 2];
        nor[o] = N[v]; nor[o + 1] = N[v + 1]; nor[o + 2] = N[v + 2];
        o += 3;
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    g.computeBoundingBox();
    g.computeBoundingSphere();
    return g;
  }

  private clearSelectionMesh() {
    if (this.selMesh) {
      this.scene.remove(this.selMesh);
      this.selMesh.geometry.dispose();
      (this.selMesh.material as THREE.Material).dispose();
      this.selMesh = null;
    }
  }

  private redrawSelection() {
    this.clearSelectionMesh();
    if (this.selectedSet.size) {
      const g = this.subsetGeometry([...this.selectedSet]);
      if (g) {
        const m = new THREE.MeshLambertMaterial({ color: SEL_COLOR, emissive: SEL_COLOR, emissiveIntensity: 0.35, side: THREE.DoubleSide, depthTest: true, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, transparent: true, opacity: 0.6, depthWrite: false });
        this.selMesh = new THREE.Mesh(g, m);
        this.selMesh.renderOrder = 5;
        this.scene.add(this.selMesh);
      }
    }
    this.requestRender();
  }

  /** Sélection simple ; `additive` ajoute ou retire l'élément de la sélection (Ctrl+clic). */
  select(id: number | null, notify = false, additive = false) {
    if (additive && id !== null) {
      if (this.selectedSet.has(id)) {
        this.selectedSet.delete(id);
        this.primary = this.selectedSet.size ? [...this.selectedSet][this.selectedSet.size - 1] : null;
      } else {
        this.selectedSet.add(id);
        this.primary = id;
      }
    } else {
      this.selectedSet = new Set(id === null ? [] : [id]);
      this.primary = id;
    }
    this.redrawSelection();
    if (notify) this.events.onSelect?.(this.primary, additive);
  }

  setSelection(ids: number[]) {
    this.selectedSet = new Set(ids);
    this.primary = ids.length ? ids[ids.length - 1] : null;
    this.redrawSelection();
  }

  /** élément principal de la sélection */
  get selection(): number | null {
    return this.primary;
  }

  get selectionIds(): number[] {
    return [...this.selectedSet];
  }

  // ------------------------------------------------------------ repères (maintenance)
  clearMarkers() {
    for (const c of [...this.markers.children]) {
      const m = c as THREE.Mesh;
      if (!(c as any).isSprite) m.geometry?.dispose();
      (m.material as THREE.Material)?.dispose();
      this.markers.remove(c);
    }
    this.requestRender();
  }

  setMarkers(items: { id: number; color: string }[]) {
    this.clearMarkers();
    for (const it of items) {
      const g = this.subsetGeometry([it.id]);
      if (!g) continue;
      // teinte légère (le détail de l'équipement reste lisible) et pastille au-dessus, visible de loin
      const mat = new THREE.MeshBasicMaterial({ color: it.color, transparent: true, opacity: 0.14, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
      const mesh = new THREE.Mesh(g, mat);
      mesh.renderOrder = 4;
      this.markers.add(mesh);
      const bb = g.boundingBox!;
      const pin = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.pinTexture(it.color), sizeAttenuation: false, depthTest: false, transparent: true }));
      pin.scale.setScalar(0.034);
      pin.center.set(0.5, 0);
      pin.position.set((bb.min.x + bb.max.x) / 2, bb.max.y + 0.03, (bb.min.z + bb.max.z) / 2);
      pin.renderOrder = 7;
      this.markers.add(pin);
    }
    this.requestRender();
  }

  private pinTextures = new Map<string, THREE.Texture>();

  /** pastille en goutte avec point d'exclamation */
  private pinTexture(color: string): THREE.Texture {
    let t = this.pinTextures.get(color);
    if (t) return t;
    const c = document.createElement('canvas');
    c.width = c.height = 96;
    const g = c.getContext('2d')!;
    g.beginPath();
    g.arc(48, 38, 30, Math.PI * 0.86, Math.PI * 0.14);
    g.lineTo(48, 94);
    g.closePath();
    g.fillStyle = color;
    g.fill();
    g.lineWidth = 5;
    g.strokeStyle = '#ffffff';
    g.stroke();
    g.fillStyle = '#ffffff';
    g.fillRect(44, 18, 8, 26);
    g.beginPath();
    g.arc(48, 54, 5, 0, Math.PI * 2);
    g.fill();
    t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    this.pinTextures.set(color, t);
    return t;
  }

  setMarkersVisible(v: boolean) {
    this.markers.visible = v;
    this.requestRender();
  }

  // ------------------------------------------------------------ caméras
  get projection(): Projection {
    return this.camera === this.ortho ? 'orthographic' : 'perspective';
  }

  private updateOrthoFrustum() {
    const w = this.container.clientWidth || 1;
    const h = this.container.clientHeight || 1;
    const dist = this.persp.position.distanceTo(this.controls?.target ?? new THREE.Vector3());
    const halfH = Math.max(0.5, Math.tan(THREE.MathUtils.degToRad(this.persp.fov / 2)) * dist);
    this.ortho.top = halfH;
    this.ortho.bottom = -halfH;
    this.ortho.left = -halfH * (w / h);
    this.ortho.right = halfH * (w / h);
    this.ortho.updateProjectionMatrix();
  }

  /** Bascule perspective / orthographique en conservant le cadrage. */
  setProjection(p: Projection) {
    if (p === this.projection) return;
    const target = this.controls.target.clone();
    if (p === 'orthographic') {
      this.persp.updateMatrixWorld();
      this.ortho.position.copy(this.persp.position);
      this.ortho.quaternion.copy(this.persp.quaternion);
      this.ortho.up.copy(this.persp.up);
      this.ortho.zoom = 1;
      this.updateOrthoFrustum();
      this.camera = this.ortho;
    } else {
      // distance équivalente au zoom orthographique
      const halfH = (this.ortho.top - this.ortho.bottom) / 2 / this.ortho.zoom;
      const dist = halfH / Math.tan(THREE.MathUtils.degToRad(this.persp.fov / 2));
      const dir = this.ortho.position.clone().sub(target).normalize();
      this.persp.position.copy(target).addScaledVector(dir, dist);
      this.persp.up.copy(this.ortho.up);
      this.camera = this.persp;
    }
    this.controls.object = this.camera;
    this.controls.target.copy(target);
    this.camera.lookAt(target);
    this.controls.update();
    this.requestRender();
    this.events.onCamera?.();
  }

  getCameraState(): CameraState {
    return {
      position: this.camera.position.toArray() as [number, number, number],
      target: this.controls.target.toArray() as [number, number, number],
      projection: this.projection,
      zoom: this.camera === this.ortho ? this.ortho.zoom : 1,
    };
  }

  setCameraState(s: CameraState) {
    if (this.projection !== s.projection) this.setProjection(s.projection);
    this.camera.position.fromArray(s.position);
    this.controls.target.fromArray(s.target);
    if (this.camera === this.ortho) {
      this.updateOrthoFrustum();
      this.ortho.zoom = s.zoom || 1;
      this.ortho.updateProjectionMatrix();
    }
    this.camera.lookAt(this.controls.target);
    this.controls.update();
    this.requestRender();
  }

  fitBox(box: THREE.Box3, keepDirection = true) {
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.length() / 2, 0.3);
    const fov = (this.persp.fov * Math.PI) / 180;
    const fit = Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * this.persp.aspect));
    const dist = (radius / Math.sin(fit / 2)) * 1.05;
    const dir = keepDirection ? this.camera.position.clone().sub(this.controls.target).normalize() : new THREE.Vector3(1, 0.8, 1).normalize();
    if (!Number.isFinite(dir.x) || dir.lengthSq() === 0) dir.set(1, 0.8, 1).normalize();
    this.controls.target.copy(center);
    this.persp.position.copy(center).addScaledVector(dir, dist);
    this.persp.lookAt(center);
    if (this.camera === this.ortho) {
      this.ortho.position.copy(center).addScaledVector(dir, dist);
      this.ortho.up.copy(this.persp.up);
      this.ortho.zoom = 1;
      this.updateOrthoFrustum();
      this.ortho.lookAt(center);
    }
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.requestRender();
  }

  fit() {
    if (this.selectedSet.size) {
      const g = this.subsetGeometry([...this.selectedSet]);
      if (g?.boundingBox) {
        const b = g.boundingBox.clone();
        g.dispose();
        this.fitBox(b.expandByScalar(0.25));
        return;
      }
    }
    this.fitBox(this.visibleBox());
  }

  fitIds(ids: number[]) {
    const g = this.subsetGeometry(ids);
    if (g?.boundingBox) {
      this.fitBox(g.boundingBox.clone().expandByScalar(0.4));
      g.dispose();
    }
  }

  private visibleBox(): THREE.Box3 {
    const box = new THREE.Box3();
    for (const b of this.buckets) {
      if (!b.mesh.visible || b.data.lot === 'espaces') continue;
      const P = b.data.positions;
      const I = b.geom.index!.array as Uint32Array;
      if (I.length === b.data.indices.length) {
        if (b.geom.boundingBox) box.union(b.geom.boundingBox);
        continue;
      }
      const v = new THREE.Vector3();
      for (let i = 0; i < I.length; i += 3) {
        const k = I[i] * 3;
        v.set(P[k], P[k + 1], P[k + 2]);
        box.expandByPoint(v);
      }
    }
    if (this.levelCut && !box.isEmpty()) {
      box.min.y = Math.max(box.min.y, this.levelCut.bottom);
      box.max.y = Math.min(box.max.y, this.levelCut.top);
    }
    return box.isEmpty() ? this.modelBox.clone() : box;
  }

  setView(v: ViewName) {
    this.setViewDir(new THREE.Vector3(...VIEW_DIRS[v]));
  }

  setViewDir(d: THREE.Vector3) {
    const box = this.visibleBox();
    const c = box.getCenter(new THREE.Vector3());
    this.controls.target.copy(c);
    this.camera.position.copy(c).add(d.clone().normalize());
    this.persp.position.copy(this.camera.position);
    this.camera.up.set(0, 1, 0);
    this.persp.up.set(0, 1, 0);
    this.fitBox(box, true);
    this.events.onCamera?.();
  }

  // ------------------------------------------------------------ style « plan » (murs coupés en noir)
  private planMats = new Map<BucketRT, THREE.Material>();

  /** En plan, les murs coupés apparaissent en aplat sombre (poché) ; `isWall` reçoit les ids d'un groupe. */
  setPlanStyle(on: boolean, isWall: (ids: Int32Array) => boolean = () => false) {
    for (const [b, m] of this.planMats) {
      (b.mesh.material as THREE.Material).dispose();
      b.mesh.material = m;
    }
    this.planMats.clear();
    this.planStyleOn = on;
    if (on) {
      for (const b of this.buckets) {
        if (b.data.lot !== 'archi') continue;
        const ids = new Int32Array(b.data.ranges.length / 3);
        for (let i = 0; i < ids.length; i++) ids[i] = b.data.ranges[i * 3];
        if (!isWall(ids)) continue;
        this.planMats.set(b, b.mesh.material as THREE.Material);
        b.mesh.material = new THREE.MeshBasicMaterial({ color: 0x2f3437, side: THREE.DoubleSide });
      }
    }
    this.requestRender();
  }

  /** Coordonnées écran (dans le conteneur) d'un point du repère IFC, ou null s'il est hors champ. */
  projectIfc(x: number, y: number, z: number): { x: number; y: number } | null {
    this.camera.updateMatrixWorld();
    const v = new THREE.Vector3(x, z, -y).project(this.camera);
    if (v.z < -1 || v.z > 1) return null;
    return { x: ((v.x + 1) / 2) * this.container.clientWidth, y: ((1 - v.y) / 2) * this.container.clientHeight };
  }

  // ------------------------------------------------------------ cube de navigation
  /** Cube cliquable (faces Dessus, Nord, Sud, Est, Ouest, Dessous) synchronisé avec la caméra. */
  attachNavCube(host: HTMLElement) {
    this.cubeRenderer = new CSS3DRenderer();
    this.cubeRenderer.setSize(96, 96);
    this.cubeRenderer.domElement.className = 'navcube';
    host.appendChild(this.cubeRenderer.domElement);
    const s = 60;
    const faces: { label: string; view: ViewName; pos: [number, number, number]; rot: [number, number, number] }[] = [
      { label: 'Dessus', view: 'dessus', pos: [0, s / 2, 0], rot: [-Math.PI / 2, 0, 0] },
      { label: 'Dessous', view: 'dessous', pos: [0, -s / 2, 0], rot: [Math.PI / 2, 0, 0] },
      { label: 'Sud', view: 'face', pos: [0, 0, s / 2], rot: [0, 0, 0] },
      { label: 'Nord', view: 'nord', pos: [0, 0, -s / 2], rot: [0, Math.PI, 0] },
      { label: 'Est', view: 'droite', pos: [s / 2, 0, 0], rot: [0, Math.PI / 2, 0] },
      { label: 'Ouest', view: 'ouest', pos: [-s / 2, 0, 0], rot: [0, -Math.PI / 2, 0] },
    ];
    for (const f of faces) {
      const d = document.createElement('div');
      d.className = 'navcube-face';
      d.textContent = f.label;
      d.title = `Vue ${f.label.toLowerCase()}`;
      d.style.width = d.style.height = `${s}px`;
      d.addEventListener('click', (e) => {
        e.stopPropagation();
        this.setView(f.view);
      });
      const o = new CSS3DObject(d);
      o.position.set(...f.pos);
      o.rotation.set(...f.rot);
      this.cubeScene.add(o);
    }
    this.renderCube();
  }

  private renderCube() {
    if (!this.cubeRenderer) return;
    const dir = this.camera.position.clone().sub(this.controls.target).normalize();
    this.cubeCamera.position.copy(dir.multiplyScalar(150));
    this.cubeCamera.up.copy(this.camera.up);
    this.cubeCamera.lookAt(0, 0, 0);
    this.cubeRenderer.render(this.cubeScene, this.cubeCamera);
  }

  // ------------------------------------------------------------ coupes
  private applyClipping() {
    const planes: THREE.Plane[] = [];
    if (this.levelCut) {
      this.planeLevelTop.set(new THREE.Vector3(0, -1, 0), this.levelCut.top);
      this.planeLevelBottom.set(new THREE.Vector3(0, 1, 0), -this.levelCut.bottom);
      planes.push(this.planeLevelTop, this.planeLevelBottom);
    }
    if (this.freeCut) {
      const n = new THREE.Vector3(this.freeCut.axis === 'x' ? 1 : 0, this.freeCut.axis === 'y' ? 1 : 0, this.freeCut.axis === 'z' ? 1 : 0);
      const min = this.modelBox.min, max = this.modelBox.max;
      const a = this.freeCut.axis;
      const pos = min[a] + (max[a] - min[a]) * this.freeCut.t;
      if (this.freeCut.flip) this.planeFree.set(n, -pos);
      else this.planeFree.set(n.clone().negate(), pos);
      planes.push(this.planeFree);
      this.updateFreeHelper(pos);
    } else if (this.freeHelper) {
      this.scene.remove(this.freeHelper);
      this.freeHelper.geometry.dispose();
      this.freeHelper = null;
    }
    this.renderer.clippingPlanes = planes;
    this.requestRender();
  }

  private updateFreeHelper(pos: number) {
    if (!this.freeCut) return;
    const size = this.modelBox.getSize(new THREE.Vector3());
    const c = this.modelBox.getCenter(new THREE.Vector3());
    if (this.freeHelper) {
      this.scene.remove(this.freeHelper);
      this.freeHelper.geometry.dispose();
    }
    const a = this.freeCut.axis;
    const w = a === 'x' ? size.z : size.x;
    const h = a === 'y' ? size.z : size.y;
    const g = new THREE.PlaneGeometry(w * 1.1, h * 1.1);
    const m = new THREE.MeshBasicMaterial({ color: 0xf28c28, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false });
    const mesh = new THREE.Mesh(g, m);
    mesh.position.copy(c);
    if (a === 'x') {
      mesh.rotation.y = Math.PI / 2;
      mesh.position.x = pos;
    } else if (a === 'y') {
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.y = pos;
    } else mesh.position.z = pos;
    this.freeHelper = mesh;
    this.scene.add(mesh);
  }

  /** Coupe horizontale : conserve la tranche [bas, haut] (hauteurs three, y vers le haut). */
  setLevelCut(cut: { bottom: number; top: number } | null) {
    this.levelCut = cut;
    this.applyClipping();
  }

  setFreeCut(cut: { axis: 'x' | 'y' | 'z'; t: number; flip: boolean } | null) {
    this.freeCut = cut;
    this.applyClipping();
  }

  get cutState(): { level: { bottom: number; top: number } | null; free: { axis: 'x' | 'y' | 'z'; t: number; flip: boolean } | null } {
    return { level: this.levelCut, free: this.freeCut };
  }

  // ------------------------------------------------------------ interaction
  private installPointer() {
    const el = this.renderer.domElement;
    let down: { x: number; y: number; t: number; button: number } | null = null;
    let hoverPending = false;
    let lastMove: PointerEvent | null = null;
    el.addEventListener('pointerdown', (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now(), button: e.button };
    });
    el.addEventListener('pointerup', (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const dt = performance.now() - down.t;
      const btn = down.button;
      down = null;
      if (moved > 6 || dt > 600 || btn !== 0) return;
      if (this.measuring) {
        const p = this.pickPoint(e.clientX, e.clientY);
        if (p) this.addMeasurePoint(p);
        return;
      }
      const hit = this.pick(e.clientX, e.clientY);
      const additive = e.ctrlKey || e.metaKey || e.shiftKey;
      if (!hit && additive) return;
      this.select(hit ? hit.id : null, true, additive);
    });
    el.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const hit = this.pick(e.clientX, e.clientY);
      this.events.onContextMenu?.(hit ? hit.id : null, e.clientX, e.clientY);
    });
    el.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse' || e.buttons) return;
      lastMove = e;
      if (hoverPending) return;
      hoverPending = true;
      requestAnimationFrame(() => {
        hoverPending = false;
        const ev = lastMove!;
        if (this.measuring) {
          this.updateSnapMarker(this.pickPoint(ev.clientX, ev.clientY));
          return;
        }
        if (!this.hoverEnabled) return;
        const hit = this.pick(ev.clientX, ev.clientY);
        el.style.cursor = hit ? 'pointer' : '';
        this.events.onHover?.(hit ? hit.id : null, ev.clientX, ev.clientY);
      });
    });
    el.addEventListener('pointerleave', () => this.events.onHover?.(null, 0, 0));
  }

  private raycast(cx: number, cy: number): { b: BucketRT; h: THREE.Intersection }[] {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((cx - rect.left) / rect.width) * 2 - 1, -((cy - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const meshes = this.buckets.filter((b) => b.mesh.visible && b.data.lot !== 'espaces' && b.visIds.length);
    for (const b of meshes) {
      if (b.bvhDirty) {
        (b.geom as any).computeBoundsTree({ indirect: true });
        b.bvhDirty = false;
      }
    }
    const hits = this.raycaster.intersectObjects(meshes.map((b) => b.mesh), false);
    const planes = this.renderer.clippingPlanes;
    const out: { b: BucketRT; h: THREE.Intersection }[] = [];
    for (const h of hits) {
      if (planes.some((p) => p.distanceToPoint(h.point) < -1e-4)) continue;
      const b = meshes.find((x) => x.mesh === h.object);
      if (!b || h.faceIndex === undefined || h.faceIndex === null) continue;
      if (b.mat.transparent && b.mat.opacity < 0.3 && b.data.lot === 'archi') continue;
      out.push({ b, h });
      break;
    }
    return out;
  }

  pick(cx: number, cy: number): { id: number; point: THREE.Vector3 } | null {
    const r = this.raycast(cx, cy)[0];
    if (!r) return null;
    const idxPos = r.h.faceIndex! * 3;
    let lo = 0, hi = r.b.visStarts.length - 1, f = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (r.b.visStarts[mid] <= idxPos) {
        f = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    return f >= 0 ? { id: r.b.visIds[f], point: r.h.point.clone() } : null;
  }

  /** Point de mesure : aimanté sur le sommet le plus proche du triangle touché (à moins de 14 px). */
  pickPoint(cx: number, cy: number): THREE.Vector3 | null {
    const r = this.raycast(cx, cy)[0];
    if (!r || !r.h.face) return null;
    const P = r.b.data.positions;
    const rect = this.renderer.domElement.getBoundingClientRect();
    let best: THREE.Vector3 | null = null;
    let bd = 14;
    for (const vi of [r.h.face.a, r.h.face.b, r.h.face.c]) {
      const v = new THREE.Vector3(P[vi * 3], P[vi * 3 + 1], P[vi * 3 + 2]);
      const s = v.clone().project(this.camera);
      const d = Math.hypot(((s.x + 1) / 2) * rect.width + rect.left - cx, ((1 - s.y) / 2) * rect.height + rect.top - cy);
      if (d < bd) {
        bd = d;
        best = v;
      }
    }
    return best ?? r.h.point.clone();
  }

  private updateSnapMarker(p: THREE.Vector3 | null) {
    if (!p) {
      if (this.snapMarker) this.snapMarker.visible = false;
      this.requestRender();
      return;
    }
    if (!this.snapMarker) {
      const r = Math.max(this.modelBox.getSize(new THREE.Vector3()).length() / 500, 0.015);
      this.snapMarker = new THREE.Mesh(new THREE.SphereGeometry(r, 10, 8), new THREE.MeshBasicMaterial({ color: 0x22d3ee, depthTest: false, transparent: true, opacity: 0.9 }));
      this.snapMarker.renderOrder = 11;
      this.scene.add(this.snapMarker);
    }
    this.snapMarker.visible = true;
    this.snapMarker.position.copy(p);
    this.requestRender();
  }

  // ------------------------------------------------------------ mesure
  setMeasuring(on: boolean) {
    this.measuring = on;
    this.clearMeasure();
    if (!on) this.updateSnapMarker(null);
    this.renderer.domElement.style.cursor = on ? 'crosshair' : '';
  }

  clearMeasure() {
    for (const c of [...this.measureGroup.children]) {
      const m = c as THREE.Mesh;
      m.geometry?.dispose();
      (m.material as THREE.Material)?.dispose();
      this.measureGroup.remove(c);
    }
    this.measurePts = [];
    this.measureLabel.hidden = true;
    this.events.onMeasure?.(null);
    this.requestRender();
  }

  private addMeasurePoint(p: THREE.Vector3) {
    if (this.measurePts.length >= 2) this.clearMeasure();
    this.measurePts.push(p);
    const r = Math.max(this.modelBox.getSize(new THREE.Vector3()).length() / 400, 0.02);
    const dot = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 8), new THREE.MeshBasicMaterial({ color: 0xf28c28, depthTest: false }));
    dot.position.copy(p);
    dot.renderOrder = 10;
    this.measureGroup.add(dot);
    if (this.measurePts.length === 2) {
      const g = new THREE.BufferGeometry().setFromPoints(this.measurePts);
      const line = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xf28c28, depthTest: false, linewidth: 2 }));
      line.renderOrder = 10;
      this.measureGroup.add(line);
      const d = this.measurePts[0].distanceTo(this.measurePts[1]);
      const dz = Math.abs(this.measurePts[0].y - this.measurePts[1].y);
      const dxy = Math.hypot(this.measurePts[0].x - this.measurePts[1].x, this.measurePts[0].z - this.measurePts[1].z);
      this.measureLabel.textContent = `${d.toFixed(3).replace('.', ',')} m` + (dz > 0.005 && dxy > 0.005 ? `  (horiz. ${dxy.toFixed(2).replace('.', ',')} m, ΔZ ${dz.toFixed(2).replace('.', ',')} m)` : '');
      this.measureLabel.hidden = false;
      this.events.onMeasure?.(d);
    }
    this.requestRender();
  }

  private updateMeasureLabel() {
    if (this.measurePts.length !== 2 || this.measureLabel.hidden) return;
    const mid = this.measurePts[0].clone().add(this.measurePts[1]).multiplyScalar(0.5).project(this.camera);
    const w = this.container.clientWidth, h = this.container.clientHeight;
    this.measureLabel.style.left = `${((mid.x + 1) / 2) * w}px`;
    this.measureLabel.style.top = `${((1 - mid.y) / 2) * h}px`;
  }

  screenshot(): string {
    this.renderFrame();
    return this.renderer.domElement.toDataURL('image/png');
  }
}
