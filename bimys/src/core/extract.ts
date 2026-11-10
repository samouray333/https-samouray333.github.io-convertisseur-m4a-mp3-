// Extraction des données d'une maquette IFC avec web-ifc (utilisé par le worker et par les tests).
import * as W from 'web-ifc';
import type { IfcAPI } from 'web-ifc';
import { classifyLot, lotFromSystem } from './lots';
import type { BBox, El, GeoBucket, LotId, ModelData, Profile, PropSet, PropValue, SpaceBoundary, StoreyInfo, SystemInfo, TreeNode } from './types';
import { ifcFr } from './ifcTypesFr';

type Progress = (pct: number, label: string) => void;

const SPATIAL = new Set(['ifcsite', 'ifcbuilding', 'ifcbuildingstorey', 'ifcspace']);
const SKIP = new Set(['ifcopeningelement', 'ifcvirtualelement', 'ifcdistributionport', 'ifcannotation', 'ifcgrid', 'ifcopeningstandardcase']);
const SEGMENT = new Set(['ifcpipesegment', 'ifcductsegment', 'ifcflowsegment', 'ifccablesegment', 'ifccablecarriersegment']);

function v(x: any): any {
  if (x === null || x === undefined) return null;
  if (typeof x === 'object' && 'value' in x) return x.value;
  return x;
}

function ref(x: any): number | null {
  if (x === null || x === undefined) return null;
  if (typeof x === 'number') return x;
  if (typeof x === 'object' && x.type === 5) return x.value; // REF
  if (typeof x === 'object' && 'expressID' in x) return x.expressID;
  return null;
}

function str(x: any): string {
  const r = v(x);
  return r === null || r === undefined ? '' : String(r);
}

function lines(api: IfcAPI, m: number, type: number): number[] {
  const vec = api.GetLineIDsWithType(m, type);
  const out: number[] = new Array(vec.size());
  for (let i = 0; i < vec.size(); i++) out[i] = vec.get(i);
  return out;
}

function getLine(api: IfcAPI, m: number, id: number | null, flatten = false): any {
  if (id === null) return null;
  try {
    return api.GetLine(m, id, flatten);
  } catch {
    return null;
  }
}

function lengthScaleOf(api: IfcAPI, m: number): number {
  try {
    for (const id of lines(api, m, W.IFCUNITASSIGNMENT)) {
      const ua = getLine(api, m, id);
      for (const u of ua.Units ?? []) {
        const unit = getLine(api, m, ref(u));
        if (!unit || str(unit.UnitType) !== 'LENGTHUNIT') continue;
        if (unit.type === W.IFCSIUNIT) {
          const p = str(unit.Prefix);
          return p === 'MILLI' ? 0.001 : p === 'CENTI' ? 0.01 : p === 'DECI' ? 0.1 : p === 'KILO' ? 1000 : 1;
        }
        if (unit.type === W.IFCCONVERSIONBASEDUNIT) {
          const n = str(unit.Name).toLowerCase();
          if (n.includes('foot') || n.includes('feet')) return 0.3048;
          if (n.includes('inch')) return 0.0254;
          const mwu = getLine(api, m, ref(unit.ConversionFactor));
          const f = Number(v(mwu?.ValueComponent));
          if (f > 0) return f;
        }
      }
    }
  } catch {
    /* unités par défaut */
  }
  return 1;
}

function propValue(nv: any, scale: number): PropValue {
  if (nv === null || nv === undefined) return null;
  const raw = v(nv);
  const tn = typeof nv === 'object' && nv && 'name' in nv ? String(nv.name || '').toUpperCase() : '';
  if (raw === 'T' || raw === true) return true;
  if (raw === 'F' || raw === false) return false;
  if (raw === 'U') return null;
  if (typeof raw === 'number') {
    if (tn === 'IFCLENGTHMEASURE' || tn === 'IFCPOSITIVELENGTHMEASURE') return raw * scale;
    if (tn === 'IFCAREAMEASURE') return raw * scale * scale;
    if (tn === 'IFCVOLUMEMEASURE') return raw * scale * scale * scale;
    return raw;
  }
  if (raw === null || raw === undefined) return null;
  return String(raw);
}

function readProperties(api: IfcAPI, m: number, props: any[], scale: number, out: PropSet, prefix = ''): void {
  for (const pr of props ?? []) {
    const p = getLine(api, m, ref(pr));
    if (!p) continue;
    const name = prefix + str(p.Name);
    switch (p.type) {
      case W.IFCPROPERTYSINGLEVALUE:
        out[name] = propValue(p.NominalValue, scale);
        break;
      case W.IFCPROPERTYENUMERATEDVALUE:
        out[name] = (p.EnumerationValues ?? []).map((x: any) => str(x)).join(', ');
        break;
      case W.IFCPROPERTYBOUNDEDVALUE: {
        const lo = propValue(p.LowerBoundValue, scale);
        const hi = propValue(p.UpperBoundValue, scale);
        out[name] = `${lo ?? ''} à ${hi ?? ''}`;
        break;
      }
      case W.IFCPROPERTYLISTVALUE:
        out[name] = (p.ListValues ?? []).map((x: any) => str(x)).join(', ');
        break;
      case W.IFCCOMPLEXPROPERTY:
        readProperties(api, m, p.HasProperties, scale, out, name + ' / ');
        break;
      default:
        break;
    }
  }
}

function readPropertyDefinition(api: IfcAPI, m: number, defId: number | null, scale: number, el: { psets: Record<string, PropSet>; qtos: Record<string, Record<string, number>> }, override: boolean): void {
  const d = getLine(api, m, defId);
  if (!d) return;
  const name = str(d.Name) || 'Propriétés';
  if (d.type === W.IFCPROPERTYSET) {
    const ps: PropSet = el.psets[name] && !override ? el.psets[name] : {};
    const tmp: PropSet = {};
    readProperties(api, m, d.HasProperties, scale, tmp);
    el.psets[name] = override ? { ...(el.psets[name] ?? {}), ...tmp } : { ...tmp, ...ps };
  } else if (d.type === W.IFCELEMENTQUANTITY) {
    const q: Record<string, number> = el.qtos[name] ?? {};
    for (const qr of d.Quantities ?? []) {
      const qq = getLine(api, m, ref(qr));
      if (!qq) continue;
      const qn = str(qq.Name);
      let val: number | null = null;
      if (qq.type === W.IFCQUANTITYLENGTH) val = Number(v(qq.LengthValue)) * scale;
      else if (qq.type === W.IFCQUANTITYAREA) val = Number(v(qq.AreaValue)) * scale * scale;
      else if (qq.type === W.IFCQUANTITYVOLUME) val = Number(v(qq.VolumeValue)) * scale * scale * scale;
      else if (qq.type === W.IFCQUANTITYCOUNT) val = Number(v(qq.CountValue));
      else if (qq.type === W.IFCQUANTITYWEIGHT) val = Number(v(qq.WeightValue));
      else if (qq.type === W.IFCQUANTITYTIME) val = Number(v(qq.TimeValue));
      if (val !== null && Number.isFinite(val)) {
        if (override || !(qn in q)) q[qn] = val;
      }
    }
    el.qtos[name] = q;
  }
}

function materialNames(api: IfcAPI, m: number, id: number | null, depth = 0): string[] {
  const mat = getLine(api, m, id);
  if (!mat || depth > 4) return [];
  switch (mat.type) {
    case W.IFCMATERIAL:
      return [str(mat.Name)];
    case W.IFCMATERIALLIST:
      return (mat.Materials ?? []).flatMap((x: any) => materialNames(api, m, ref(x), depth + 1));
    case W.IFCMATERIALLAYERSETUSAGE:
      return materialNames(api, m, ref(mat.ForLayerSet), depth + 1);
    case W.IFCMATERIALLAYERSET:
      return (mat.MaterialLayers ?? []).flatMap((x: any) => materialNames(api, m, ref(x), depth + 1));
    case W.IFCMATERIALLAYER:
      return materialNames(api, m, ref(mat.Material), depth + 1);
    case W.IFCMATERIALPROFILESETUSAGE:
      return materialNames(api, m, ref(mat.ForProfileSet), depth + 1);
    case W.IFCMATERIALPROFILESET:
      return (mat.MaterialProfiles ?? []).flatMap((x: any) => materialNames(api, m, ref(x), depth + 1));
    case W.IFCMATERIALPROFILE:
      return materialNames(api, m, ref(mat.Material), depth + 1);
    case W.IFCMATERIALCONSTITUENTSET:
      return (mat.MaterialConstituents ?? []).flatMap((x: any) => materialNames(api, m, ref(x), depth + 1));
    case W.IFCMATERIALCONSTITUENT:
      return materialNames(api, m, ref(mat.Material), depth + 1);
    default:
      return mat.Name ? [str(mat.Name)] : [];
  }
}

/** Lit la profondeur d'extrusion et le profil d'un segment depuis sa représentation 'Body'. */
function segmentGeometry(api: IfcAPI, m: number, reprId: number | null, scale: number): { depth: number | null; profile: Profile | null } {
  const pds = getLine(api, m, reprId);
  if (!pds) return { depth: null, profile: null };
  const items: number[] = [];
  for (const r of pds.Representations ?? []) {
    const rep = getLine(api, m, ref(r));
    if (!rep) continue;
    const ident = str(rep.RepresentationIdentifier);
    if (ident && ident !== 'Body') continue;
    for (const it of rep.Items ?? []) items.push(ref(it)!);
  }
  let depth = 0;
  let profile: Profile | null = null;
  let found = false;
  const visit = (id: number, d = 0) => {
    const it = getLine(api, m, id);
    if (!it || d > 3) return;
    if (it.type === W.IFCEXTRUDEDAREASOLID) {
      found = true;
      depth += Number(v(it.Depth)) * scale;
      const pr = getLine(api, m, ref(it.SweptArea));
      if (pr && !profile) {
        if (pr.type === W.IFCCIRCLEHOLLOWPROFILEDEF) profile = { kind: 'circle', d: 2 * Number(v(pr.Radius)) * scale, wall: Number(v(pr.WallThickness)) * scale };
        else if (pr.type === W.IFCCIRCLEPROFILEDEF) profile = { kind: 'circle', d: 2 * Number(v(pr.Radius)) * scale };
        else if (pr.type === W.IFCRECTANGLEHOLLOWPROFILEDEF || pr.type === W.IFCRECTANGLEPROFILEDEF)
          profile = { kind: 'rect', w: Number(v(pr.XDim)) * scale, h: Number(v(pr.YDim)) * scale };
      }
    } else if (it.type === W.IFCMAPPEDITEM) {
      const src = getLine(api, m, ref(it.MappingSource));
      const rep = getLine(api, m, ref(src?.MappedRepresentation));
      for (const x of rep?.Items ?? []) visit(ref(x)!, d + 1);
    }
  };
  for (const id of items) visit(id);
  return { depth: found ? depth : null, profile };
}

// ------------------------------------------------------------ géométrie des limites d'espaces
type P3 = [number, number, number];

function curvePoints(api: IfcAPI, m: number, id: number | null, scale: number, depth = 0): P3[] {
  const c = getLine(api, m, id);
  if (!c || depth > 4) return [];
  const toP = (pid: any): P3 => {
    const p = getLine(api, m, ref(pid));
    const co = (p?.Coordinates ?? []).map((x: any) => Number(v(x)) * scale);
    return [co[0] ?? 0, co[1] ?? 0, co[2] ?? 0];
  };
  switch (c.type) {
    case W.IFCPOLYLINE:
      return (c.Points ?? []).map(toP);
    case W.IFCPOLYLOOP:
      return (c.Polygon ?? []).map(toP);
    case W.IFCINDEXEDPOLYCURVE: {
      const pl = getLine(api, m, ref(c.Points));
      const list = (pl?.CoordList ?? []).map((row: any[]) => row.map((x: any) => Number(v(x)) * scale));
      return list.map((r: number[]) => [r[0] ?? 0, r[1] ?? 0, r[2] ?? 0] as P3);
    }
    case W.IFCCOMPOSITECURVE: {
      const out: P3[] = [];
      for (const s of c.Segments ?? []) {
        const seg = getLine(api, m, ref(s));
        out.push(...curvePoints(api, m, ref(seg?.ParentCurve), scale, depth + 1));
      }
      return out;
    }
    default:
      return [];
  }
}

function polygonArea(pts: P3[]): number {
  if (pts.length < 3) return 0;
  // Newell : fonctionne en 2D (z = 0) comme en 3D
  let nx = 0, ny = 0, nz = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    nx += (a[1] - b[1]) * (a[2] + b[2]);
    ny += (a[2] - b[2]) * (a[0] + b[0]);
    nz += (a[0] - b[0]) * (a[1] + b[1]);
  }
  return 0.5 * Math.sqrt(nx * nx + ny * ny + nz * nz);
}

function polygonNormalZ(pts: P3[]): number {
  let nx = 0, ny = 0, nz = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    nx += (a[1] - b[1]) * (a[2] + b[2]);
    ny += (a[2] - b[2]) * (a[0] + b[0]);
    nz += (a[0] - b[0]) * (a[1] + b[1]);
  }
  const l = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
  return nz / l;
}

function boundaryGeometry(api: IfcAPI, m: number, connId: number | null, scale: number): { area: number; gross: number; normalZ: number } | null {
  const conn = getLine(api, m, connId);
  if (!conn) return null;
  const surf = getLine(api, m, ref(conn.SurfaceOnRelatingElement));
  if (!surf) return null;
  if (surf.type === W.IFCCURVEBOUNDEDPLANE || surf.type === W.IFCCURVEBOUNDEDSURFACE) {
    const outer = curvePoints(api, m, ref(surf.OuterBoundary), scale);
    const gross = polygonArea(outer);
    let inner = 0;
    for (const ib of surf.InnerBoundaries ?? []) inner += polygonArea(curvePoints(api, m, ref(ib), scale));
    let normalZ = 0;
    const basis = getLine(api, m, ref(surf.BasisSurface));
    const pos = getLine(api, m, ref(basis?.Position));
    const axis = getLine(api, m, ref(pos?.Axis));
    if (axis) {
      const d = (axis.DirectionRatios ?? []).map((x: any) => Number(v(x)));
      const l = Math.hypot(d[0] ?? 0, d[1] ?? 0, d[2] ?? 0) || 1;
      normalZ = (d[2] ?? 0) / l;
    } else if (basis && !axis && pos) {
      normalZ = 1;
    }
    return { area: Math.max(0, gross - inner), gross, normalZ };
  }
  if (surf.type === W.IFCFACESURFACE || surf.type === W.IFCFACE) {
    let gross = 0, inner = 0, nz = 0;
    for (const b of surf.Bounds ?? []) {
      const fb = getLine(api, m, ref(b));
      const pts = curvePoints(api, m, ref(fb?.Bound), scale);
      const a = polygonArea(pts);
      if (fb?.type === W.IFCFACEOUTERBOUND || gross === 0) {
        gross += a;
        nz = polygonNormalZ(pts);
      } else inner += a;
    }
    return { area: Math.max(0, gross - inner), gross, normalZ: nz };
  }
  return null;
}

// ------------------------------------------------------------ extraction des données
export function extractData(api: IfcAPI, m: number, fileName: string, progress: Progress = () => {}): ModelData {
  const scale = lengthScaleOf(api, m);
  const types = api.GetAllTypesOfModel(m) as Array<{ typeID: number; typeName: string }>;
  const elements: El[] = [];
  const byId = new Map<number, El>();
  const spatial = new Map<number, { cls: string; name: string; elevation: number; gid: string }>();
  let projectGid = '';
  let projectName = '';
  let projectId = -1;

  for (const pid of lines(api, m, W.IFCPROJECT)) {
    const p = getLine(api, m, pid);
    projectGid = str(p.GlobalId);
    projectName = str(p.LongName) || str(p.Name);
    projectId = pid;
  }

  let done = 0;
  for (const t of types) {
    const cls = api.GetNameFromTypeCode(t.typeID) || t.typeName;
    const lc = cls.toLowerCase();
    if (SKIP.has(lc)) continue;
    const isEl = SPATIAL.has(lc) || (api as any).IsIfcElement?.(t.typeID);
    if (!isEl) continue;
    for (const id of lines(api, m, t.typeID)) {
      const l = getLine(api, m, id);
      if (!l || !l.GlobalId) continue;
      if (lc !== 'ifcspace' && SPATIAL.has(lc)) {
        spatial.set(id, { cls, name: str(l.Name) || str(l.LongName) || ifcFr(cls), elevation: Number(v(l.Elevation) ?? 0) * scale, gid: str(l.GlobalId) });
        continue;
      }
      const e: El = {
        id,
        gid: str(l.GlobalId),
        cls,
        name: lc === 'ifcspace' ? str(l.LongName) || str(l.Name) : str(l.Name),
        objectType: str(l.ObjectType),
        desc: str(l.Description),
        predefined: str(l.PredefinedType),
        typeName: '',
        storeyId: null,
        spaceId: null,
        systemIds: [],
        psets: {},
        qtos: {},
        materials: [],
        lot: 'autres',
        bbox: null,
        length: null,
        profile: null,
        hasGeometry: !!l.Representation,
      };
      if (lc === 'ifcspace' && str(l.Name) && str(l.LongName) && str(l.Name) !== str(l.LongName)) e.desc = e.desc || `N° ${str(l.Name)}`;
      if (SEGMENT.has(lc)) {
        const g = segmentGeometry(api, m, ref(l.Representation), scale);
        e.length = g.depth;
        e.profile = g.profile;
      }
      elements.push(e);
      byId.set(id, e);
      if (lc === 'ifcspace') spatial.set(id, { cls, name: e.name, elevation: 0, gid: e.gid });
    }
    done++;
    progress(10 + Math.round((15 * done) / Math.max(1, types.length)), 'Lecture des objets');
  }

  // agrégations (arbre spatial et sous-éléments)
  const parent = new Map<number, number>();
  const children = new Map<number, number[]>();
  for (const id of lines(api, m, W.IFCRELAGGREGATES)) {
    const r = getLine(api, m, id);
    const p = ref(r.RelatingObject);
    if (p === null) continue;
    for (const c of r.RelatedObjects ?? []) {
      const cid = ref(c);
      if (cid === null) continue;
      parent.set(cid, p);
      if (!children.has(p)) children.set(p, []);
      children.get(p)!.push(cid);
    }
  }
  for (const id of lines(api, m, W.IFCRELNESTS)) {
    const r = getLine(api, m, id);
    const p = ref(r.RelatingObject);
    if (p === null || !byId.has(p)) continue;
    for (const c of r.RelatedObjects ?? []) {
      const cid = ref(c);
      if (cid !== null && byId.has(cid) && !parent.has(cid)) parent.set(cid, p);
    }
  }
  progress(28, 'Arborescence');

  // contenance spatiale
  const contained = new Map<number, number[]>();
  for (const id of lines(api, m, W.IFCRELCONTAINEDINSPATIALSTRUCTURE)) {
    const r = getLine(api, m, id);
    const s = ref(r.RelatingStructure);
    if (s === null) continue;
    for (const c of r.RelatedElements ?? []) {
      const cid = ref(c);
      if (cid === null) continue;
      if (!contained.has(s)) contained.set(s, []);
      contained.get(s)!.push(cid);
      const e = byId.get(cid);
      if (!e) continue;
      const sc = spatial.get(s)?.cls.toLowerCase();
      if (sc === 'ifcspace') e.spaceId = s;
      else if (sc === 'ifcbuildingstorey') e.storeyId = s;
    }
  }
  const storeyOf = (id: number): number | null => {
    let cur: number | undefined = id;
    for (let i = 0; i < 12 && cur !== undefined; i++) {
      const sp = spatial.get(cur);
      if (sp && sp.cls.toLowerCase() === 'ifcbuildingstorey') return cur;
      const e = byId.get(cur);
      if (e && e.storeyId !== null && cur !== id) return e.storeyId;
      if (e && e.spaceId !== null) {
        cur = e.spaceId;
        continue;
      }
      cur = parent.get(cur);
    }
    return null;
  };
  for (const e of elements) {
    if (e.cls.toLowerCase() === 'ifcspace') {
      e.storeyId = storeyOf(e.id);
      continue;
    }
    if (e.spaceId === null && e.storeyId === null) {
      // sous-élément : hérite du conteneur de son parent
      let p = parent.get(e.id);
      for (let i = 0; i < 6 && p !== undefined; i++) {
        const pe = byId.get(p);
        if (pe && (pe.spaceId !== null || pe.storeyId !== null)) {
          e.spaceId = pe.spaceId;
          e.storeyId = pe.storeyId;
          break;
        }
        p = parent.get(p);
      }
    }
    if (e.storeyId === null && e.spaceId !== null) e.storeyId = storeyOf(e.spaceId);
  }
  progress(32, 'Propriétés');

  // types
  const typeOf = new Map<number, number>();
  for (const id of lines(api, m, W.IFCRELDEFINESBYTYPE)) {
    const r = getLine(api, m, id);
    const t = ref(r.RelatingType);
    if (t === null) continue;
    const tl = getLine(api, m, t);
    for (const o of r.RelatedObjects ?? []) {
      const oid = ref(o);
      const e = oid !== null ? byId.get(oid) : undefined;
      if (!e) continue;
      typeOf.set(e.id, t);
      e.typeName = str(tl?.Name);
      if (!e.predefined || e.predefined === 'NOTDEFINED') {
        const tp = str(tl?.PredefinedType);
        if (tp) e.predefined = tp;
      }
      for (const ps of tl?.HasPropertySets ?? []) readPropertyDefinition(api, m, ref(ps), scale, e, false);
    }
  }
  // propriétés d'occurrence (prioritaires sur le type)
  const relProps = lines(api, m, W.IFCRELDEFINESBYPROPERTIES);
  relProps.forEach((id, i) => {
    const r = getLine(api, m, id);
    const def = ref(r.RelatingPropertyDefinition);
    for (const o of r.RelatedObjects ?? []) {
      const oid = ref(o);
      const e = oid !== null ? byId.get(oid) : undefined;
      if (e) readPropertyDefinition(api, m, def, scale, e, true);
    }
    if (i % 200 === 0) progress(32 + Math.round((10 * i) / Math.max(1, relProps.length)), 'Propriétés');
  });

  // matériaux (occurrence puis type)
  const matOf = new Map<number, string[]>();
  for (const id of lines(api, m, W.IFCRELASSOCIATESMATERIAL)) {
    const r = getLine(api, m, id);
    const names = materialNames(api, m, ref(r.RelatingMaterial)).filter(Boolean);
    for (const o of r.RelatedObjects ?? []) {
      const oid = ref(o);
      if (oid !== null) matOf.set(oid, names);
    }
  }
  for (const e of elements) {
    const own = matOf.get(e.id);
    const t = typeOf.get(e.id);
    e.materials = own && own.length ? own : t !== undefined ? matOf.get(t) ?? [] : [];
    e.materials = [...new Set(e.materials)];
  }

  // systèmes
  const systems: SystemInfo[] = [];
  const sysTypes = [W.IFCSYSTEM, W.IFCDISTRIBUTIONSYSTEM, (W as any).IFCBUILDINGSYSTEM, (W as any).IFCDISTRIBUTIONCIRCUIT].filter((x) => typeof x === 'number');
  const sysIds = new Set<number>();
  for (const t of sysTypes) for (const id of lines(api, m, t)) sysIds.add(id);
  const sysMap = new Map<number, SystemInfo>();
  for (const id of sysIds) {
    const s = getLine(api, m, id);
    const info: SystemInfo = {
      id,
      gid: str(s.GlobalId),
      name: str(s.Name) || str(s.LongName) || 'Système',
      predefined: str(s.PredefinedType),
      cls: api.GetNameFromTypeCode(s.type),
      lot: 'autres',
      members: [],
    };
    info.lot = lotFromSystem(info.predefined, info.name) ?? 'autres';
    sysMap.set(id, info);
    systems.push(info);
  }
  for (const id of lines(api, m, W.IFCRELASSIGNSTOGROUP)) {
    const r = getLine(api, m, id);
    const g = ref(r.RelatingGroup);
    const s = g !== null ? sysMap.get(g) : undefined;
    if (!s) continue;
    for (const o of r.RelatedObjects ?? []) {
      const oid = ref(o);
      const e = oid !== null ? byId.get(oid) : undefined;
      if (!e) continue;
      s.members.push(e.id);
      if (!e.systemIds.includes(s.id)) e.systemIds.push(s.id);
    }
  }
  progress(45, 'Classement par lot');

  for (const e of elements) {
    const lots = e.systemIds.map((id) => sysMap.get(id)!.lot) as LotId[];
    e.lot = classifyLot(e.cls, lots, `${e.name} ${e.objectType} ${e.typeName}`);
    // longueur : quantité IFC prioritaire
    if (SEGMENT.has(e.cls.toLowerCase())) {
      for (const [qn, q] of Object.entries(e.qtos)) {
        if (/segment|base/i.test(qn) && typeof q.Length === 'number' && q.Length > 0) {
          e.length = q.Length;
          break;
        }
      }
    }
  }

  // limites d'espaces
  const boundaries: SpaceBoundary[] = [];
  const sbTypes = [W.IFCRELSPACEBOUNDARY, (W as any).IFCRELSPACEBOUNDARY1STLEVEL, (W as any).IFCRELSPACEBOUNDARY2NDLEVEL].filter((x) => typeof x === 'number');
  for (const t of sbTypes) {
    for (const id of lines(api, m, t)) {
      const r = getLine(api, m, id);
      const sp = ref(r.RelatingSpace);
      if (sp === null || !byId.has(sp)) continue;
      const geom = boundaryGeometry(api, m, ref(r.ConnectionGeometry), scale);
      if (!geom || geom.area <= 0) continue;
      const ioe = str(r.InternalOrExternalBoundary);
      boundaries.push({
        spaceId: sp,
        elementId: ref(r.RelatedBuildingElement),
        area: geom.area,
        gross: geom.gross,
        external: ioe === 'EXTERNAL' || ioe === 'EXTERNAL_EARTH' || ioe === 'EXTERNAL_WATER' || ioe === 'EXTERNAL_FIRE',
        normalZ: geom.normalZ,
      });
    }
  }

  // niveaux
  const storeys: StoreyInfo[] = [];
  for (const [id, s] of spatial) if (s.cls.toLowerCase() === 'ifcbuildingstorey') storeys.push({ id, gid: s.gid, name: s.name, elevation: s.elevation });
  storeys.sort((a, b) => a.elevation - b.elevation);

  // arborescence : Projet > Bâtiment > Niveaux > Pièces > Éléments
  const buildNode = (id: number, depth: number): TreeNode => {
    const sp = spatial.get(id);
    const e = byId.get(id);
    const node: TreeNode = { id, cls: sp?.cls ?? e?.cls ?? 'IfcProject', name: sp?.name ?? e?.name ?? projectName, children: [] };
    if (depth > 8) return node;
    const kids = (children.get(id) ?? []).filter((c) => spatial.has(c) || byId.has(c));
    const spatialKids = kids.filter((c) => spatial.has(c));
    const sortedSpatial = spatialKids.sort((a, b) => (spatial.get(a)!.elevation - spatial.get(b)!.elevation) || spatial.get(a)!.name.localeCompare(spatial.get(b)!.name, 'fr'));
    for (const c of sortedSpatial) {
      const cls = spatial.get(c)!.cls.toLowerCase();
      if (cls === 'ifcsite') node.children.push(...buildNode(c, depth + 1).children);
      else node.children.push(buildNode(c, depth + 1));
    }
    const elems = [...(contained.get(id) ?? []), ...kids.filter((c) => !spatial.has(c) && byId.has(c))].filter((c, i, arr) => arr.indexOf(c) === i && byId.has(c));
    const isSpace = sp?.cls.toLowerCase() === 'ifcspace';
    const groups = new Map<string, TreeNode>();
    for (const c of elems) {
      const ce = byId.get(c)!;
      const sub: TreeNode = { id: c, cls: ce.cls, name: ce.name || ifcFr(ce.cls), children: [] };
      for (const cc of children.get(c) ?? []) {
        const cce = byId.get(cc);
        if (cce) sub.children.push({ id: cc, cls: cce.cls, name: cce.name || ifcFr(cce.cls), children: [] });
      }
      if (isSpace && elems.length < 25) {
        node.children.push(sub);
        continue;
      }
      const g = ifcFr(ce.cls);
      if (!groups.has(g)) groups.set(g, { id: -1, cls: 'group', name: g, children: [] });
      groups.get(g)!.children.push(sub);
    }
    for (const g of [...groups.values()].sort((a, b) => a.name.localeCompare(b.name, 'fr'))) {
      g.name = `${g.name} (${g.children.length})`;
      g.children.sort((a, b) => a.name.localeCompare(b.name, 'fr', { numeric: true }));
      node.children.push(g);
    }
    return node;
  };
  const tree = projectId >= 0 ? buildNode(projectId, 0) : null;
  if (tree) {
    tree.cls = 'IfcProject';
    tree.name = projectName || fileName;
  }

  return {
    fileName,
    schema: api.GetModelSchema(m),
    projectGid,
    projectName,
    lengthScale: scale,
    elements,
    systems,
    storeys,
    boundaries,
    tree,
  };
}

// ------------------------------------------------------------ géométrie
interface BucketBuild {
  key: string;
  lot: LotId;
  run: boolean;
  color: [number, number, number, number];
  pos: Float32Array[];
  nor: Float32Array[];
  idx: Uint32Array[];
  vcount: number;
  icount: number;
  ranges: number[];
}

/**
 * Parcourt la géométrie : calcule les boîtes englobantes (coordonnées IFC) et, si demandé,
 * fusionne les maillages par lot et par couleur (peu d'appels de rendu sur mobile).
 */
export function extractGeometry(api: IfcAPI, m: number, data: ModelData, buildBuffers: boolean, progress: Progress = () => {}): GeoBucket[] {
  const byId = new Map<number, El>();
  for (const e of data.elements) byId.set(e.id, e);
  const buckets = new Map<string, BucketBuild>();
  const total = Math.max(1, data.elements.filter((e) => e.hasGeometry).length);
  let n = 0;
  const skipClasses = new Set(['ifcopeningelement']);

  const onMesh = (mesh: any) => {
    const e = byId.get(mesh.expressID);
    n++;
    if (n % 50 === 0) progress(50 + Math.round((45 * n) / total), 'Géométrie 3D');
    if (!e || skipClasses.has(e.cls.toLowerCase())) return;
    const geoms = mesh.geometries;
    const bb: BBox = e.bbox ?? [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
    for (let i = 0; i < geoms.size(); i++) {
      const pg = geoms.get(i);
      const geo = api.GetGeometry(m, pg.geometryExpressID);
      const verts = api.GetVertexArray(geo.GetVertexData(), geo.GetVertexDataSize());
      const index = api.GetIndexArray(geo.GetIndexData(), geo.GetIndexDataSize());
      const t = pg.flatTransformation as number[];
      const nv = verts.length / 6;
      const pos = buildBuffers ? new Float32Array(nv * 3) : null;
      const nor = buildBuffers ? new Float32Array(nv * 3) : null;
      for (let k = 0; k < nv; k++) {
        const x = verts[k * 6], y = verts[k * 6 + 1], z = verts[k * 6 + 2];
        const px = t[0] * x + t[4] * y + t[8] * z + t[12];
        const py = t[1] * x + t[5] * y + t[9] * z + t[13];
        const pz = t[2] * x + t[6] * y + t[10] * z + t[14];
        // coordonnées three (y vers le haut) -> IFC (z vers le haut)
        const ix = px, iy = -pz, iz = py;
        if (ix < bb[0]) bb[0] = ix;
        if (iy < bb[1]) bb[1] = iy;
        if (iz < bb[2]) bb[2] = iz;
        if (ix > bb[3]) bb[3] = ix;
        if (iy > bb[4]) bb[4] = iy;
        if (iz > bb[5]) bb[5] = iz;
        if (pos && nor) {
          pos[k * 3] = px;
          pos[k * 3 + 1] = py;
          pos[k * 3 + 2] = pz;
          const a = verts[k * 6 + 3], b = verts[k * 6 + 4], c = verts[k * 6 + 5];
          nor[k * 3] = t[0] * a + t[4] * b + t[8] * c;
          nor[k * 3 + 1] = t[1] * a + t[5] * b + t[9] * c;
          nor[k * 3 + 2] = t[2] * a + t[6] * b + t[10] * c;
        }
      }
      if (buildBuffers && pos && nor) {
        const col = pg.color;
        const rgba: [number, number, number, number] = [round2(col.x), round2(col.y), round2(col.z), round2(col.w)];
        const run: boolean = /segment|fitting/i.test(e.cls) && e.predefined !== 'JUNCTION';
        const key: string = `${e.lot}|${run ? 'r' : 'e'}|${rgba.join(',')}`;
        let b = buckets.get(key);
        if (!b) {
          b = { key, lot: e.lot, run, color: rgba, pos: [], nor: [], idx: [], vcount: 0, icount: 0, ranges: [] };
          buckets.set(key, b);
        }
        const idx = new Uint32Array(index.length);
        for (let k = 0; k < index.length; k++) idx[k] = index[k] + b.vcount;
        const last = b.ranges.length - 3;
        if (last >= 0 && b.ranges[last] === e.id && b.ranges[last + 1] + b.ranges[last + 2] === b.icount) b.ranges[last + 2] += idx.length;
        else b.ranges.push(e.id, b.icount, idx.length);
        b.pos.push(pos);
        b.nor.push(nor);
        b.idx.push(idx);
        b.vcount += nv;
        b.icount += idx.length;
      }
      geo.delete?.();
    }
    if (bb[0] !== Infinity) e.bbox = bb;
  };
  api.StreamAllMeshes(m, onMesh);
  // web-ifc ignore les IfcSpace par défaut : on les charge à part (volumes des pièces, étiquettes en plan)
  try {
    api.StreamAllMeshesWithTypes(m, [W.IFCSPACE], onMesh);
  } catch {
    /* version de web-ifc sans cette fonction */
  }

  const out: GeoBucket[] = [];
  for (const b of buckets.values()) {
    out.push({
      key: b.key,
      lot: b.lot,
      run: b.run,
      color: b.color,
      positions: concatF(b.pos, b.vcount * 3),
      normals: concatF(b.nor, b.vcount * 3),
      indices: concatU(b.idx, b.icount),
      ranges: Int32Array.from(b.ranges),
    });
  }
  return out;
}

function round2(x: number): number {
  return Math.round(x * 100) / 100;
}

function concatF(parts: Float32Array[], len: number): Float32Array {
  const out = new Float32Array(len);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

function concatU(parts: Uint32Array[], len: number): Uint32Array {
  const out = new Uint32Array(len);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

/** Chargement complet (worker ou tests). */
export function loadIfc(api: IfcAPI, bytes: Uint8Array, fileName: string, buildBuffers: boolean, progress: Progress = () => {}): { data: ModelData; buckets: GeoBucket[] } {
  progress(2, 'Ouverture du fichier');
  const m = api.OpenModel(bytes, { COORDINATE_TO_ORIGIN: true, CIRCLE_SEGMENTS: 20 } as any);
  try {
    progress(10, 'Lecture des objets');
    const data = extractData(api, m, fileName, progress);
    progress(50, 'Géométrie 3D');
    const buckets = extractGeometry(api, m, data, buildBuffers, progress);
    try {
      data.coord = Array.from(api.GetCoordinationMatrix(m) as ArrayLike<number>);
    } catch {
      data.coord = [];
    }
    progress(98, 'Finalisation');
    return { data, buckets };
  } finally {
    api.CloseModel(m);
  }
}
