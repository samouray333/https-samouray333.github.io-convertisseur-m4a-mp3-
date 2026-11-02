// Vue 3D three.js : géométrie fusionnée par lot/couleur, sélection, masquage, coupes, mesure.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
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
  mat: THREE.MeshLambertMaterial;
  /** index courant (éléments visibles) : débuts et ids, pour retrouver l'élément touché */
  visStarts: Int32Array;
  visIds: Int32Array;
  bvhDirty: boolean;
}

export type ViewName = 'dessus' | 'face' | 'iso' | 'droite';

export interface ViewerEvents {
  onSelect?: (id: number | null) => void;
  onMeasure?: (d: number | null) => void;
}

const SEL_COLOR = 0x22d3ee;

export class Viewer {
  readonly container: HTMLElement;
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly controls: OrbitControls;
  private buckets: BucketRT[] = [];
  private elementRanges = new Map<number, { b: BucketRT; start: number; count: number }[]>();
  private hidden = new Set<number>();
  private isolated: Set<number> | null = null;
  private lotVisible: Record<string, boolean> = {};
  private colorMode: 'lot' | 'ifc' = 'lot';
  private archiTransparent = false;
  private selected: number | null = null;
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
  measuring = false;
  events: ViewerEvents = {};
  private disposed = false;
  private ro: ResizeObserver;
  private lowPower: boolean;

  constructor(container: HTMLElement) {
    this.container = container;
    this.lowPower = matchMedia('(pointer: coarse)').matches;
    this.renderer = new THREE.WebGLRenderer({ antialias: !this.lowPower, alpha: false, powerPreference: 'default', preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.lowPower ? 1.75 : 2));
    this.renderer.localClippingEnabled = false;
    this.renderer.domElement.className = 'viewer-canvas';
    container.appendChild(this.renderer.domElement);
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.05, 5000);
    this.camera.position.set(15, 12, 15);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.screenSpacePanning = true;
    this.controls.addEventListener('change', () => this.requestRender());
    const hemi = new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6);
    const dir = new THREE.DirectionalLight(0xffffff, 1.4);
    dir.position.set(10, 20, 8);
    const dir2 = new THREE.DirectionalLight(0xffffff, 0.5);
    dir2.position.set(-10, 6, -12);
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
        this.renderer.render(this.scene, this.camera);
        this.updateMeasureLabel();
      }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  setBackground(color: string) {
    this.scene.background = new THREE.Color(color);
    this.requestRender();
  }

  requestRender() {
    this.needsRender = true;
  }

  resize() {
    const w = this.container.clientWidth || 1;
    const h = this.container.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
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
    }
    this.buckets = [];
    this.elementRanges.clear();
    this.hidden.clear();
    this.isolated = null;
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
      const mat = new THREE.MeshLambertMaterial({ side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(geom, mat);
      mesh.matrixAutoUpdate = false;
      const rt: BucketRT = { data, mesh, geom, mat, visStarts: new Int32Array(0), visIds: new Int32Array(0), bvhDirty: true };
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
    this.camera.near = Math.max(0.01, size / 2000);
    this.camera.far = size * 20 + 100;
    this.camera.updateProjectionMatrix();
    for (const b of this.buckets) this.rebuildIndex(b);
    this.applyMaterials();
    this.setView('iso');
  }

  get bounds(): THREE.Box3 {
    return this.modelBox.clone();
  }

  // ------------------------------------------------------------ apparence
  setLotVisible(lot: LotId, v: boolean) {
    this.lotVisible[lot] = v;
    for (const b of this.buckets) if (b.data.lot === lot) b.mesh.visible = v;
    this.requestRender();
  }

  setLotVisibility(map: Record<string, boolean>) {
    this.lotVisible = { ...map };
    for (const b of this.buckets) b.mesh.visible = map[b.data.lot] !== false;
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
      if (useLot) mat.color.set(LOT_BY_ID[lot].color);
      else mat.color.setRGB(r, g, bl, THREE.SRGBColorSpace);
      let opacity = a;
      if (lot === 'espaces') opacity = Math.min(a, 0.18);
      if (lot === 'archi' && this.archiTransparent) opacity = Math.min(a, 0.18);
      mat.transparent = opacity < 0.99;
      mat.opacity = opacity;
      mat.depthWrite = opacity >= 0.99;
      mat.polygonOffset = lot === 'archi';
      mat.polygonOffsetFactor = 1;
      mat.polygonOffsetUnits = 1;
      b.mesh.renderOrder = mat.transparent ? 2 : lot === 'archi' ? 0 : 1;
      mat.needsUpdate = true;
      b.mesh.visible = this.lotVisible[lot] !== undefined ? this.lotVisible[lot] : LOT_BY_ID[lot]?.visible !== false;
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
    for (const b of this.buckets) this.rebuildIndex(b);
    this.requestRender();
  }

  hide(ids: number[]) {
    for (const id of ids) this.hidden.add(id);
    if (this.selected !== null && ids.includes(this.selected)) this.select(null);
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

  select(id: number | null, notify = false) {
    this.selected = id;
    this.clearSelectionMesh();
    if (id !== null) {
      const g = this.subsetGeometry([id]);
      if (g) {
        const m = new THREE.MeshLambertMaterial({ color: SEL_COLOR, emissive: SEL_COLOR, emissiveIntensity: 0.45, side: THREE.DoubleSide, depthTest: true, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, transparent: true, opacity: 0.92 });
        this.selMesh = new THREE.Mesh(g, m);
        this.selMesh.renderOrder = 5;
        this.scene.add(this.selMesh);
      }
    }
    if (notify) this.events.onSelect?.(id);
    this.requestRender();
  }

  get selection(): number | null {
    return this.selected;
  }

  // ------------------------------------------------------------ repères (maintenance)
  clearMarkers() {
    for (const c of [...this.markers.children]) {
      const m = c as THREE.Mesh;
      m.geometry?.dispose();
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
      const mat = new THREE.MeshLambertMaterial({ color: it.color, emissive: it.color, emissiveIntensity: 0.55, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
      const mesh = new THREE.Mesh(g, mat);
      mesh.renderOrder = 4;
      this.markers.add(mesh);
      // halo sphérique pour repérer les petits équipements de loin
      const bs = g.boundingSphere!;
      const halo = new THREE.Mesh(new THREE.SphereGeometry(Math.max(bs.radius * 1.3, 0.18), 16, 12), new THREE.MeshBasicMaterial({ color: it.color, transparent: true, opacity: 0.22, depthWrite: false }));
      halo.position.copy(bs.center);
      halo.renderOrder = 6;
      this.markers.add(halo);
    }
    this.requestRender();
  }

  setMarkersVisible(v: boolean) {
    this.markers.visible = v;
    this.requestRender();
  }

  // ------------------------------------------------------------ caméra
  fitBox(box: THREE.Box3, keepDirection = true) {
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.length() / 2, 0.3);
    const fov = (this.camera.fov * Math.PI) / 180;
    const fit = Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * this.camera.aspect));
    const dist = (radius / Math.sin(fit / 2)) * 1.05;
    const dir = keepDirection ? this.camera.position.clone().sub(this.controls.target).normalize() : new THREE.Vector3(1, 0.8, 1).normalize();
    if (!Number.isFinite(dir.x) || dir.lengthSq() === 0) dir.set(1, 0.8, 1).normalize();
    this.controls.target.copy(center);
    this.camera.position.copy(center).addScaledVector(dir, dist);
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.requestRender();
  }

  fit() {
    if (this.selected !== null) {
      const g = this.subsetGeometry([this.selected]);
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
    return box.isEmpty() ? this.modelBox.clone() : box;
  }

  setView(v: ViewName) {
    const box = this.visibleBox();
    const c = box.getCenter(new THREE.Vector3());
    const dirs: Record<ViewName, THREE.Vector3> = {
      dessus: new THREE.Vector3(0, 1, 0.0001),
      face: new THREE.Vector3(0, 0.05, 1),
      droite: new THREE.Vector3(1, 0.05, 0),
      iso: new THREE.Vector3(1, 0.9, 1),
    };
    this.controls.target.copy(c);
    this.camera.position.copy(c).add(dirs[v].normalize());
    this.camera.up.set(0, 1, 0);
    this.fitBox(box, true);
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

  // ------------------------------------------------------------ interaction
  private installPointer() {
    const el = this.renderer.domElement;
    let down: { x: number; y: number; t: number } | null = null;
    el.addEventListener('pointerdown', (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
    });
    el.addEventListener('pointerup', (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const dt = performance.now() - down.t;
      down = null;
      if (moved > 6 || dt > 600) return;
      const hit = this.pick(e.clientX, e.clientY);
      if (this.measuring) {
        if (hit) this.addMeasurePoint(hit.point);
        return;
      }
      this.select(hit ? hit.id : null, true);
    });
  }

  pick(cx: number, cy: number): { id: number; point: THREE.Vector3 } | null {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((cx - rect.left) / rect.width) * 2 - 1, -((cy - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    (this.raycaster as any).firstHitOnly = false;
    const meshes = this.buckets.filter((b) => b.mesh.visible && b.data.lot !== 'espaces' && b.visIds.length);
    for (const b of meshes) {
      if (b.bvhDirty) {
        (b.geom as any).computeBoundsTree({ indirect: true });
        b.bvhDirty = false;
      }
    }
    const hits = this.raycaster.intersectObjects(meshes.map((b) => b.mesh), false);
    const planes = this.renderer.clippingPlanes;
    for (const h of hits) {
      if (planes.some((p) => p.distanceToPoint(h.point) < -1e-4)) continue;
      const b = meshes.find((x) => x.mesh === h.object);
      if (!b || h.faceIndex === undefined || h.faceIndex === null) continue;
      if (b.mat.transparent && b.mat.opacity < 0.3 && b.data.lot === 'archi') continue;
      const idxPos = h.faceIndex * 3;
      // recherche dichotomique de l'élément dont la plage contient idxPos
      let lo = 0, hi = b.visStarts.length - 1, f = -1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (b.visStarts[mid] <= idxPos) {
          f = mid;
          lo = mid + 1;
        } else hi = mid - 1;
      }
      if (f >= 0) return { id: b.visIds[f], point: h.point.clone() };
    }
    return null;
  }

  // ------------------------------------------------------------ mesure
  setMeasuring(on: boolean) {
    this.measuring = on;
    this.clearMeasure();
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
      this.measureLabel.textContent = `${d.toFixed(3).replace('.', ',')} m` + (dz > 0.005 ? `  (ΔZ ${dz.toFixed(2).replace('.', ',')} m)` : '');
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
    this.renderer.render(this.scene, this.camera);
    return this.renderer.domElement.toDataURL('image/png');
  }
}
