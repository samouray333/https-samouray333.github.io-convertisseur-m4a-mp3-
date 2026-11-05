#!/usr/bin/env python3
"""
Bimys : bibliothèque de maquettes IFC4 pédagogiques (bâtiments complets).

    python tools/batiments.py            # génère toutes les maquettes dans public/samples/

Moteur générique : pièces rectangulaires par niveau, enveloppe, cloisons et portes déduites des pièces,
fenêtres, limites d'espaces (déperditions), puis réseaux de chauffage, froid, ECS, EF et ventilation.
Les émetteurs sont dimensionnés à partir des déperditions calculées comme dans Bimys
(parois U x S x ΔT + 10 % de ponts thermiques + 0,34 x Qv x ΔT, Te = -10 °C), avec quelques
erreurs volontaires listées dans BATIMENTS (champ "erreurs") pour les exercices.
Script non embarqué dans l'application (IfcOpenShell est sous LGPL).
"""
import json
import math
import os
import re
import sys

import ifcopenshell
import ifcopenshell.guid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_maquette import Builder, DeterministicGuid, api  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_IFC = os.path.join(ROOT, "public", "samples")
SLAB = 0.20
TE = -10.0

CIRCULATION = re.compile(r"circulation|couloir|dégagement|degagement|palier|hall|entrée|entree|séjour|sejour|accueil|attente|open", re.I)
NO_WINDOW = re.compile(r"wc|sanitaire|salle d.eau|salle de bains|gaine|local|chaufferie|cellier|palier|circulation|couloir|dégagement|salle [0-9]|cabine|réserve|stérilisation|bloc|vestiaire|archives", re.I)


def default_ti(name):
    n = name.lower()
    if re.search(r"bain|sdb|salle d.eau|douche", n):
        return 22.0
    if re.search(r"séjour|salon|salle [àa] manger|living|bureau|pièce de vie", n):
        return 20.0
    return 19.0


def heated(name):
    return not re.search(r"cellier|garage|chaufferie|cave|local technique|combles|abri|local (vélos|poubelles|déchets|ménage)|gaine|parking|terrasse", name, re.I)


def manhattan(a, b, z, first="x"):
    """Trajet orthogonal de a vers b à l'altitude z."""
    (ax, ay), (bx, by) = a, b
    mid = (bx, ay) if first == "x" else (ax, by)
    pts = [(ax, ay, z), (mid[0], mid[1], z), (bx, by, z)]
    out = []
    for p in pts:
        if not out or max(abs(p[i] - out[-1][i]) for i in range(3)) > 1e-6:
            out.append(p)
    return out


class Bat(Builder):
    def __init__(self, key, name, long_name, desc, storeys, W, D, U, ext_t=0.30, mes="2019-09-15"):
        self.variant = key
        self.key = key
        ifcopenshell.guid.new = DeterministicGuid(key)
        f = self.f = api("project.create_file", None, version="IFC4")
        self.project = api("root.create_entity", f, ifc_class="IfcProject", name=name)
        self.project.LongName = long_name
        self.project.Description = desc
        api("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"}, area={"is_metric": True, "raw": "METERS"}, volume={"is_metric": True, "raw": "METERS"})
        self.ctx = api("context.add_context", f, context_type="Model")
        self.body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=self.ctx)
        self.site = api("root.create_entity", f, ifc_class="IfcSite", name="Terrain")
        self.site.Description = "Saône-et-Loire (71)"
        self.building = api("root.create_entity", f, ifc_class="IfcBuilding", name=name)
        api("aggregate.assign_object", f, products=[self.site], relating_object=self.project)
        api("aggregate.assign_object", f, products=[self.building], relating_object=self.site)
        for o in (self.site, self.building):
            o.ObjectPlacement = self.lp(None, (0, 0, 0))
        self.storeys, self.sinfo, self.order = {}, {}, []
        for skey, sname, elev, h in storeys:
            s = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name=sname)
            s.Elevation = elev
            s.ObjectPlacement = self.lp(self.building.ObjectPlacement, (0, 0, elev))
            api("aggregate.assign_object", f, products=[s], relating_object=self.building)
            self.storeys[skey] = s
            self.sinfo[skey] = {"name": sname, "elev": elev, "h": h}
            self.order.append(skey)
        self.W, self.D, self.t = W, D, ext_t
        self.X0, self.X1, self.Y0, self.Y1 = ext_t, W - ext_t, ext_t, D - ext_t
        self.U = U
        self.mes = mes
        self.styles, self.materials, self.types, self.systems, self.spaces = {}, {}, {}, {}, {}
        self.ext_walls, self.slabs = {}, {}
        self.expected = {"pipes": {}, "ducts": {}, "counts": {}, "rooms": {}}
        self.serial = 1000
        self.rooms = []  # dict(name, usage, skey, x0, x1, y0, y1, h)
        self.doors_ext = []  # (skey, side, pos, width, height, name)
        self.ext_openings = []
        self.openings_by_name = {}
        self.inlet_q = {}
        self.losses = {}
        self.circ = 0
        for n, c, tr in (("Mur", (0.86, 0.84, 0.80), 0), ("Cloison", (0.93, 0.92, 0.90), 0), ("Dalle", (0.72, 0.72, 0.72), 0), ("Vitrage", (0.55, 0.75, 0.90), 0.6),
                         ("Porte", (0.55, 0.38, 0.25), 0), ("Toiture", (0.45, 0.45, 0.47), 0), ("Espace", (0.6, 0.8, 0.6), 0.85), ("Cuivre", (0.80, 0.45, 0.20), 0),
                         ("Acier", (0.35, 0.35, 0.38), 0), ("Multicouche", (0.92, 0.92, 0.92), 0), ("Equipement", (0.95, 0.95, 0.97), 0), ("Radiateur", (0.98, 0.98, 0.98), 0),
                         ("Robinet", (0.80, 0.10, 0.10), 0), ("Circulateur", (0.10, 0.45, 0.25), 0), ("Vase", (0.85, 0.15, 0.15), 0), ("PAC", (0.85, 0.87, 0.88), 0),
                         ("PER EF", (0.15, 0.35, 0.85), 0), ("PER EC", (0.85, 0.15, 0.15), 0), ("Sanitaire", (0.97, 0.97, 0.97), 0), ("Ballon", (0.92, 0.92, 0.92), 0),
                         ("Galva", (0.70, 0.72, 0.75), 0), ("Souple", (0.80, 0.80, 0.70), 0), ("Bouche", (0.98, 0.98, 0.98), 0), ("VMC", (0.30, 0.55, 0.75), 0),
                         ("Froid", (0.10, 0.65, 0.75), 0), ("PCBT", (0.95, 0.60, 0.40), 0.75)):
            self.style(n, c, tr)

    # ------------------------------------------------------------ outils
    def hsp(self, skey):
        return self.sinfo[skey]["h"] - SLAB

    def room(self, skey, name, usage, x0, x1, y0, y1):
        r = {"name": name, "usage": usage, "skey": skey, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "h": self.hsp(skey), "windows": [], "doors": []}
        self.rooms.append(r)
        return r

    def R(self, name, skey=None):
        for r in self.rooms:
            if r["name"] == name and (skey is None or r["skey"] == skey):
                return r
        raise KeyError(name)

    def area(self, r):
        return (r["x1"] - r["x0"]) * (r["y1"] - r["y0"])

    def ext_sides(self, r):
        s = []
        e = 1e-6
        if abs(r["x0"] - self.X0) < e:
            s.append(("Ouest", r["y0"], r["y1"]))
        if abs(r["x1"] - self.X1) < e:
            s.append(("Est", r["y0"], r["y1"]))
        if abs(r["y0"] - self.Y0) < e:
            s.append(("Sud", r["x0"], r["x1"]))
        if abs(r["y1"] - self.Y1) < e:
            s.append(("Nord", r["x0"], r["x1"]))
        return s

    def door_ext(self, skey, side, pos, width=1.0, height=2.15, name="Porte d'entrée"):
        self.doors_ext.append((skey, side, pos, width, height, name))

    @property
    def occupied(self):
        return [k for k in self.order if any(r["skey"] == k for r in self.rooms)]

    # ------------------------------------------------------------ enveloppe, cloisons, ouvertures
    def build_envelope(self, window=(1.2, 0.9, 1.25), big_window_rooms=None):
        import generate_maquette as gm
        gm.U_WIN, gm.U_DOOR = self.U["fenetre"], self.U["porte"]
        f = self.f
        m_ext = self.material(self.U.get("mur_txt", "Béton 20 cm + isolant"), "Maçonnerie")
        m_int = self.material("Cloison plaque de plâtre 72/48", "Plâtre")
        m_slab = self.material("Béton armé", "Béton")
        m_win = self.material("Menuiserie PVC double vitrage", "Menuiserie")
        m_door = self.material("Porte acier isolée", "Menuiserie")
        occ = self.occupied
        t = self.t
        for skey in occ:
            h = self.sinfo[skey]["h"]
            sn = self.sinfo[skey]["name"]
            walls = {"Sud": ((0, 0), self.W, t), "Nord": ((0, self.Y1), self.W, t), "Ouest": ((0, self.Y0), t, self.Y1 - self.Y0), "Est": ((self.X1, self.Y0), t, self.Y1 - self.Y0)}
            self.ext_walls[skey] = {}
            for side, ((x, y), dx, dy) in walls.items():
                w = self.product("IfcWall", f"Mur extérieur {side} {sn}", skey, (x, y, 0), [self.box_solid(dx, dy, h)], "Mur", predefined="SOLIDWALL")
                api("material.assign_material", f, products=[w], material=m_ext)
                self.pset(w, "Pset_WallCommon", {"IsExternal": True, "ThermalTransmittance": self.U["mur"], "LoadBearing": True})
                self.qto(w, "Qto_WallBaseQuantities", {"Length": max(dx, dy), "Width": t, "Height": h})
                self.ext_walls[skey][side] = w
        # dalles
        low = occ[0]
        s = self.product("IfcSlab", "Plancher bas", low, (0, 0, -SLAB), [self.box_solid(self.W, self.D, SLAB)], "Dalle", predefined="BASESLAB")
        self.pset(s, "Pset_SlabCommon", {"IsExternal": True, "ThermalTransmittance": self.U["sol"]})
        api("material.assign_material", f, products=[s], material=m_slab)
        self.slabs["sol"] = s
        for skey in occ[:-1]:
            s = self.product("IfcSlab", f"Plancher haut {self.sinfo[skey]['name']}", skey, (self.X0, self.Y0, self.hsp(skey)), [self.box_solid(self.X1 - self.X0, self.Y1 - self.Y0, SLAB)], "Dalle", predefined="FLOOR")
            self.pset(s, "Pset_SlabCommon", {"IsExternal": False})
            api("material.assign_material", f, products=[s], material=m_slab)
        top = occ[-1]
        s = self.product("IfcSlab", "Toiture terrasse isolée", top, (0, 0, self.hsp(top)), [self.box_solid(self.W, self.D, SLAB)], "Toiture", predefined="ROOF")
        self.pset(s, "Pset_SlabCommon", {"IsExternal": True, "ThermalTransmittance": self.U["toit"]})
        api("material.assign_material", f, products=[s], material=m_slab)
        self.slabs["toit"] = s
        roof_key = self.order[-1] if self.order[-1] not in occ else None
        if roof_key:
            for side, ((x, y), dx, dy) in {"Sud": ((0, 0), self.W, 0.2), "Nord": ((0, self.D - 0.2), self.W, 0.2), "Ouest": ((0, 0.2), 0.2, self.D - 0.4), "Est": ((self.W - 0.2, 0.2), 0.2, self.D - 0.4)}.items():
                a = self.product("IfcWall", f"Acrotère {side}", roof_key, (x, y, 0), [self.box_solid(dx, dy, 0.6)], "Mur", predefined="PARAPET")
                self.pset(a, "Pset_WallCommon", {"IsExternal": True})
        # espaces
        for r in self.rooms:
            sp = api("root.create_entity", f, ifc_class="IfcSpace", name=r["name"], predefined_type="INTERNAL")
            sp.LongName = r["name"]
            sp.ObjectType = r["usage"]
            sp.ObjectPlacement = self.lp(self.storeys[r["skey"]].ObjectPlacement, (r["x0"], r["y0"], 0))
            sp.Representation = self.shape([self.box_solid(r["x1"] - r["x0"], r["y1"] - r["y0"], r["h"])])
            self.paint(sp, "Espace")
            api("aggregate.assign_object", f, products=[sp], relating_object=self.storeys[r["skey"]])
            a = round(self.area(r), 4)
            self.qto(sp, "Qto_SpaceBaseQuantities", {"Height": r["h"], "NetFloorArea": a, "GrossFloorArea": a, "NetVolume": round(a * r["h"], 3), "NetPerimeter": round(2 * (r["x1"] - r["x0"] + r["y1"] - r["y0"]), 3)})
            self.pset(sp, "Pset_SpaceCommon", {"Reference": r["usage"], "IsExternal": False})
            r["space"] = sp
            self.spaces[f"{r['skey']}|{r['name']}"] = sp
        # cloisons déduites des pièces
        self.partitions = {}
        for skey in occ:
            lines = {}
            for r in [x for x in self.rooms if x["skey"] == skey]:
                for orient, c, a, b in (("v", r["x0"], r["y0"], r["y1"]), ("v", r["x1"], r["y0"], r["y1"]), ("h", r["y0"], r["x0"], r["x1"]), ("h", r["y1"], r["x0"], r["x1"])):
                    if orient == "v" and (abs(c - self.X0) < 1e-6 or abs(c - self.X1) < 1e-6):
                        continue
                    if orient == "h" and (abs(c - self.Y0) < 1e-6 or abs(c - self.Y1) < 1e-6):
                        continue
                    lines.setdefault((orient, round(c, 3)), []).append((a, b))
            walls = []
            for (orient, c), segs in sorted(lines.items()):
                segs.sort()
                merged = []
                for a, b in segs:
                    if merged and a <= merged[-1][1] + 1e-6:
                        merged[-1][1] = max(merged[-1][1], b)
                    else:
                        merged.append([a, b])
                for a, b in merged:
                    if b - a < 0.2:
                        continue
                    if orient == "v":
                        origin, dims = (c - 0.05, a, 0), (0.10, b - a, self.hsp(skey))
                    else:
                        origin, dims = (a, c - 0.05, 0), (b - a, 0.10, self.hsp(skey))
                    w = self.product("IfcWall", f"Cloison {self.sinfo[skey]['name']} {len(walls) + 1}", skey, origin, [self.box_solid(*dims)], "Cloison", predefined="PARTITIONING")
                    api("material.assign_material", f, products=[w], material=m_int)
                    self.pset(w, "Pset_WallCommon", {"IsExternal": False})
                    walls.append((orient, c, a, b, w))
            self.partitions[skey] = walls
        # portes intérieures : chaque pièce s'ouvre sur une circulation voisine
        n = 0
        for r in self.rooms:
            if CIRCULATION.search(r["name"]) and not re.search(r"séjour|sejour", r["name"], re.I):
                continue
            best = None
            for o in self.rooms:
                if o is r or o["skey"] != r["skey"] or not CIRCULATION.search(o["name"]):
                    continue
                for orient, c, a1, b1, a2, b2 in (("v", r["x1"], r["y0"], r["y1"], o["y0"], o["y1"]) if abs(r["x1"] - o["x0"]) < 1e-6 else (None,) * 6,
                                                  ("v", r["x0"], r["y0"], r["y1"], o["y0"], o["y1"]) if abs(r["x0"] - o["x1"]) < 1e-6 else (None,) * 6,
                                                  ("h", r["y1"], r["x0"], r["x1"], o["x0"], o["x1"]) if abs(r["y1"] - o["y0"]) < 1e-6 else (None,) * 6,
                                                  ("h", r["y0"], r["x0"], r["x1"], o["x0"], o["x1"]) if abs(r["y0"] - o["y1"]) < 1e-6 else (None,) * 6):
                    if orient is None:
                        continue
                    lo, hi = max(a1, a2), min(b1, b2)
                    if hi - lo >= 1.1 and (best is None or hi - lo > best[3] - best[2]):
                        best = (orient, c, lo, hi)
            if not best:
                continue
            orient, c, lo, hi = best
            wall = next((w for (o2, c2, a, b, w) in self.partitions[r["skey"]] if o2 == orient and abs(c2 - c) < 1e-3 and a <= lo + 1e-6 and b >= hi - 1e-6), None)
            if wall is None:
                continue
            wd = 0.93 if re.search(r"chambre|salle|bloc", r["name"], re.I) else 0.83
            p = lo + 0.25 if hi - lo > 2.5 else (lo + hi) / 2 - wd / 2
            n += 1
            if orient == "v":
                o_or, o_d, f_or, f_d = (c - 0.1, p, 0), (0.2, wd, 2.04), (c - 0.02, p, 0), (0.04, wd, 2.04)
            else:
                o_or, o_d, f_or, f_d = (p, c - 0.1, 0), (wd, 0.2, 2.04), (p, c - 0.02, 0), (wd, 0.04, 2.04)
            self.make_opening(r["skey"], wall, o_or, o_d, f_or, f_d, "D", f"Porte {r['name']} ({self.sinfo[r['skey']]['name']}) {n}", wd, 2.04, m_win, m_door, external=False)
        # portes extérieures
        for (skey, side, pos, width, height, name) in self.doors_ext:
            room = self.room_at(skey, side, pos + width / 2)
            self.add_ext_opening(skey, side, pos, width, 0.0, height, "D", f"{name} ({self.sinfo[skey]['name']})", room, m_win, m_door)
        # fenêtres
        big = big_window_rooms or set()
        for r in self.rooms:
            if NO_WINDOW.search(r["name"]) and r["name"] not in big:
                continue
            for side, a, b in self.ext_sides(r):
                L = b - a
                if L < 1.2:
                    continue
                if r["name"] in big:
                    ww, sill, hh = min(L - 0.6, 2.4), 0.0, 2.2
                    nwin = max(1, int(L / 3.0))
                else:
                    ww, sill, hh = window
                    if re.search(r"salle d.eau|bain|wc", r["name"], re.I):
                        ww, sill, hh = 0.6, 1.3, 0.8
                    nwin = max(1, int(L / 3.6))
                for i in range(nwin):
                    pos = a + L * (i + 0.5) / nwin - ww / 2
                    if any(d[0] == r["skey"] and d[1] == side and not (pos + ww < d[2] - 0.2 or pos > d[2] + d[3] + 0.2) for d in self.doors_ext):
                        continue
                    self.add_ext_opening(r["skey"], side, pos, ww, sill, hh, "W", f"Fenêtre {r['name']} {side} {i + 1} ({self.sinfo[r['skey']]['name']})", r, m_win, m_door)

    def room_at(self, skey, side, pos):
        for r in self.rooms:
            if r["skey"] != skey:
                continue
            for s, a, b in self.ext_sides(r):
                if s == side and a <= pos <= b:
                    return r
        return None

    def add_ext_opening(self, skey, side, pos, width, sill, height, kind, name, room, m_win, m_door):
        wall = self.ext_walls[skey][side]
        t = self.t
        if side in ("Sud", "Nord"):
            y = 0.0 if side == "Sud" else self.Y1
            o_or, o_d, f_or, f_d = (pos, y - 0.05, sill), (width, t + 0.1, height), (pos, y + t / 2 - 0.04, sill), (width, 0.08, height)
        else:
            x = 0.0 if side == "Ouest" else self.X1
            o_or, o_d, f_or, f_d = (x - 0.05, pos, sill), (t + 0.1, width, height), (x + t / 2 - 0.04, pos, sill), (0.08, width, height)
        self.make_opening(skey, wall, o_or, o_d, f_or, f_d, kind, name, width, height, m_win, m_door, external=True)
        rec = (skey, side, pos, width, sill, height, kind, name, room["name"] if room else None)
        self.ext_openings.append(rec)
        if room is not None:
            (room["windows"] if kind == "W" else room["doors"]).append({"side": side, "pos": pos, "width": width, "sill": sill, "height": height, "name": name})

    # ------------------------------------------------------------ limites d'espaces et déperditions
    def build_boundaries(self):
        occ = self.occupied
        for r in self.rooms:
            sp, skey = r["space"], r["skey"]
            x0, x1, y0, y1, h = r["x0"], r["x1"], r["y0"], r["y1"], r["h"]
            ua = 0.0
            for side, a, b in self.ext_sides(r):
                wall = self.ext_walls[skey][side]
                inners = []
                for o in r["windows"] + r["doors"]:
                    if o["side"] != side:
                        continue
                    inners.append((o["pos"] - a, o["sill"], o["width"], o["height"]))
                    el = self.openings_by_name[o["name"]]
                    if side in ("Sud", "Nord"):
                        yy = self.Y0 if side == "Sud" else self.Y1
                        self.plane_boundary(sp, el, (o["pos"] - x0, yy - y0, o["sill"]), (0, -1 if side == "Sud" else 1, 0), (1, 0, 0), o["width"], o["height"])
                    else:
                        xx = self.X0 if side == "Ouest" else self.X1
                        self.plane_boundary(sp, el, (xx - x0, o["pos"] - y0, o["sill"]), (-1 if side == "Ouest" else 1, 0, 0), (0, 1, 0), o["width"], o["height"])
                    ua += (self.U["fenetre"] if o in r["windows"] else self.U["porte"]) * o["width"] * o["height"]
                L = b - a
                if side in ("Sud", "Nord"):
                    yy = self.Y0 if side == "Sud" else self.Y1
                    self.plane_boundary(sp, wall, (0, yy - y0, 0), (0, -1 if side == "Sud" else 1, 0), (1, 0, 0), L, h, inners)
                else:
                    xx = self.X0 if side == "Ouest" else self.X1
                    self.plane_boundary(sp, wall, (xx - x0, 0, 0), (-1 if side == "Ouest" else 1, 0, 0), (0, 1, 0), L, h, inners)
                ua += self.U["mur"] * (L * h - sum(i[2] * i[3] for i in inners))
            if skey == occ[0]:
                self.plane_boundary(sp, self.slabs["sol"], (0, 0, 0), (0, 0, -1), (1, 0, 0), x1 - x0, y1 - y0)
                ua += self.U["sol"] * self.area(r)
            if skey == occ[-1]:
                self.plane_boundary(sp, self.slabs["toit"], (0, 0, h), (0, 0, 1), (1, 0, 0), x1 - x0, y1 - y0)
                ua += self.U["toit"] * self.area(r)
            r["ua"] = ua

    def loss(self, r):
        """Déperditions (W) calculées comme dans Bimys (méthode par parois)."""
        dt = default_ti(r["name"]) - TE
        q = self.inlet_q.get(id(r), 0.0)
        return r["ua"] * dt * 1.10 + 0.34 * q * dt

    def size(self, r, step=50, factor=1.08, mini=0):
        target = self.loss(r) * factor
        if target < 700 and step > 25:
            step = 25
        p = max(mini, math.ceil(target / step) * step)
        if r["name"] in getattr(self, "undersized", set()):
            p = max(step, math.floor(self.loss(r) * 0.72 / step) * step)
        return p

    # ------------------------------------------------------------ équipements et réseaux génériques
    def eq(self, cls, name, skey, origin, dims, style, predefined=None, object_type=None, room=None, system=None, cyl=False, psets=None):
        container = room["space"] if room else None
        if cyl:
            p = self.cyl_equipment(cls, name, skey, origin, dims[0], dims[1], style, predefined=predefined, container=container, system=system)
        else:
            p = self.box_equipment(cls, name, skey, origin, dims, style, predefined=predefined, container=container, system=system)
        if object_type:
            p.ObjectType = object_type
            try:
                if not predefined:
                    p.PredefinedType = "USERDEFINED"
            except Exception:
                pass
        if psets:
            marque, modele, kw, extra = psets
            self.equipment_psets(p, marque, modele, kw, self.mes, extra, marque[:2].upper())
        return p

    def pipe(self, skey, pts, label, material, outer, wall, system, circuit, style, fittings=True):
        fam = "cuivre" if "Cuivre" in material else "acier" if "Acier" in material else "multicouche" if "Multicouche" in material else "PER"
        return self.run(skey, pts, "pipe", label, material, outer, wall, system, circuit, fam, style, fittings=fittings)

    def duct(self, skey, pts, dia, material, system, circuit, style="Galva"):
        fam = "galva" if "galva" in material.lower() else "souple"
        return self.run(skey, pts, "duct", f"Ø{dia}", material, dia, 0, system, circuit, fam, style)

    def rect_duct(self, skey, pts, w_mm, h_mm, system, circuit, material="Conduit galva rectangulaire"):
        """Gaine rectangulaire (profil IfcRectangleProfileDef, Pset forme RECTANGULAR)."""
        f = self.f
        label = f"{w_mm}x{h_mm}"
        key = ("rduct", label, material)
        if key not in self.types:
            t = api("root.create_entity", f, ifc_class="IfcDuctSegmentType", name=f"Gaine rectangulaire {label}", predefined_type="RIGIDSEGMENT")
            self.pset(t, "Pset_DuctSegmentTypeCommon", {"Shape": "RECTANGULAR", "NominalDiameterOrWidth": w_mm / 1000.0, "NominalHeight": h_mm / 1000.0, "Reference": label})
            api("material.assign_material", f, products=[t], material=self.material(material))
            self.types[key] = t
        t = self.types[key]
        segs = []
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            d = [b[k] - a[k] for k in range(3)]
            L = math.sqrt(sum(v * v for v in d))
            if L < 1e-6:
                continue
            u = [v / L for v in d]
            refx = (0, 0, 1) if abs(u[2]) < 0.9 else (1, 0, 0)
            prof = f.createIfcRectangleProfileDef("AREA", None, f.createIfcAxis2Placement2D(self.pt((0, 0)), None), w_mm / 1000.0, h_mm / 1000.0)
            solid = f.createIfcExtrudedAreaSolid(prof, self.ax3((0, 0, 0)), self.dirn((0, 0, 1)), L)
            seg = self.product("IfcDuctSegment", f"Gaine {label} {circuit}", skey, a, [solid], "Galva", z=tuple(u), x=refx)
            seg.PredefinedType = "RIGIDSEGMENT"
            api("type.assign_type", f, related_objects=[seg], relating_type=t)
            self.qto(seg, "Qto_DuctSegmentBaseQuantities", {"Length": round(L, 4)})
            segs.append(seg)
            if i > 0:
                pa = pts[i - 1]
                d0 = [a[k] - pa[k] for k in range(3)]
                n0 = math.sqrt(sum(v * v for v in d0)) or 1.0
                back = tuple(-v / n0 for v in d0)
                self.assign(system, [self.fitting(skey, a, "duct", "BEND", f"Coude {label}", max(w_mm, h_mm) / 2000.0, "Galva", label, dirs=[back, tuple(u)], rect=(w_mm / 1000.0, h_mm / 1000.0))])
        self.assign(system, segs)
        return segs

    def wall_point(self, r, prefer_window=True):
        """Position d'un émetteur : sous la première fenêtre, sinon au milieu du plus grand mur."""
        if prefer_window and r["windows"]:
            w = r["windows"][0]
            return w["side"], w["pos"] + w["width"] / 2
        best = None
        for side, a, b in (("Sud", r["x0"], r["x1"]), ("Nord", r["x0"], r["x1"]), ("Ouest", r["y0"], r["y1"]), ("Est", r["y0"], r["y1"])):
            if best is None or b - a > best[2] - best[1]:
                best = (side, a, b)
        return best[0], (best[1] + best[2]) / 2

    def radiator(self, r, power, system, name=None, trv=True, towel=False, electric=False):
        """Radiateur contre un mur, centré sous la fenêtre ; renvoie les points de raccordement départ et retour."""
        side, c = self.wall_point(r, not towel)
        L = max(0.4, min(2.0, round(power / (900.0 if not towel else 600.0), 1)))
        H = 1.2 if towel else 0.6
        skey = r["skey"]
        if side in ("Sud", "Nord"):
            y = r["y0"] + 0.05 if side == "Sud" else r["y1"] - 0.15
            a = max(r["x0"] + 0.1, min(r["x1"] - L - 0.1, c - L / 2))
            origin, dims, dpt, rpt = (a, y, 0.45), (L, 0.10, H), (a + L, y + 0.05), (a, y + 0.05)
        else:
            x = r["x0"] + 0.05 if side == "Ouest" else r["x1"] - 0.15
            a = max(r["y0"] + 0.1, min(r["y1"] - L - 0.1, c - L / 2))
            origin, dims, dpt, rpt = (x, a, 0.45), (0.10, L, H), (x + 0.05, a + L), (x + 0.05, a)
        nm = name or (f"Sèche-serviettes {r['name']}" if towel else f"{'Convecteur électrique' if electric else 'Radiateur'} {r['name']}")
        rad = self.eq("IfcSpaceHeater", nm, skey, origin, dims, "Radiateur", predefined="CONVECTOR" if electric else "RADIATOR", room=r, system=None if electric else system)
        rad.ObjectType = "Convecteur électrique" if electric else ("Radiateur sèche-serviettes" if towel else "Radiateur acier panneaux")
        self.pset(rad, "Pset_SpaceHeaterTypeCommon", {"OutputCapacity": float(power), "HeatTransferMedium": "AIR" if electric else "WATER", "EnergySource": "ELECTRICITY" if electric else "NOTKNOWN"})
        self.equipment_psets(rad, "Calorys" if not electric else "Thermelec", f"{'Convecteur' if electric else 'Type 21'} H{int(H * 1000)} L{int(L * 1000)}", power / 1000.0, self.mes, {"Puissance nominale à ΔT 50 K (W)": float(power)} if not electric else {"Alimentation": "230 V"}, "CA")
        if electric:
            return rad, None, None
        if trv:
            v = self.eq("IfcValve", f"Robinet thermostatique {nm.lower()}", skey, (dpt[0], dpt[1], 0.40), (0.022, 0.09), "Robinet", predefined="REGULATING", room=r, system=system, cyl=True)
            v.ObjectType = "Robinet thermostatique"
        ts = self.eq("IfcValve", f"Té de réglage {nm.lower()}", skey, (rpt[0], rpt[1], 0.40), (0.018, 0.06), "Robinet", predefined="REGULATING", room=r, system=system, cyl=True)
        ts.ObjectType = "Té de réglage"
        return rad, dpt, rpt

    def star(self, skey, coll, targets, label, material, outer, wall, system, style, z0=0.05, rise_to=0.45, first="x"):
        """Distribution en étoile (pieuvre) depuis un collecteur : un aller et un retour par émetteur."""
        for (dpt, rpt) in targets:
            z = z0 + 0.025 * (self.circ % 8)
            self.circ += 1
            for circ, p, zz in (("Départ", dpt, z), ("Retour", rpt, z + 0.0125)):
                pts = manhattan(coll, p, zz, first)
                pts.append((p[0], p[1], rise_to))
                self.pipe(skey, pts, label, material, outer, wall, system, circ, style)

    def sanitary(self, r, kind, pos, systems=("EF", "ECS")):
        names = {"SINK": "Évier", "WASHHANDBASIN": "Lavabo", "SHOWER": "Douche", "BATH": "Baignoire", "WCSEAT": "WC"}
        dims = {"SINK": (0.6, 0.6, 0.05), "WASHHANDBASIN": (0.5, 0.45, 0.1), "SHOWER": (0.9, 0.9, 0.08), "BATH": (1.7, 0.7, 0.55), "WCSEAT": (0.4, 0.55, 0.4)}
        z = 0.85 if kind in ("SINK", "WASHHANDBASIN") else 0.0
        s = self.eq("IfcSanitaryTerminal", f"{names[kind]} {r['name']}", r["skey"], (pos[0], pos[1], z), dims[kind], "Sanitaire", predefined=kind, room=r)
        for sy in systems:
            if sy in self.systems and not (kind == "WCSEAT" and sy == "ECS"):
                self.assign(sy, [s])
        return s

    def air_terminal(self, r, name, fonction, q, pos, system, kind="extraction", dia=125):
        z = r["h"] - 0.04
        b = self.eq("IfcAirTerminal", name, r["skey"], (pos[0], pos[1], z), (dia / 2000.0 + 0.04, 0.04), "Bouche", room=r, system=system, cyl=True)
        b.PredefinedType = "USERDEFINED"
        b.ObjectType = {"extraction": "Bouche d'extraction", "soufflage": "Diffuseur de soufflage", "insufflation": "Bouche d'insufflation", "reprise": "Grille de reprise"}[kind]
        self.pset(b, "Bimys_Equipement", {"Marque": "AéroFlux", "Modèle": f"{b.ObjectType} Ø{dia}", "Fonction": fonction, "Débit nominal (m³/h)": float(q)})
        return b

    def inlet(self, r, q, system):
        w = r["windows"][0] if r["windows"] else None
        if not w:
            return None
        side = w["side"]
        if side in ("Sud", "Nord"):
            y = self.Y0 + 0.12 if side == "Sud" else self.Y1 - 0.16
            o, d = (w["pos"] + 0.1, y, w["sill"] + w["height"] - 0.06), (0.4, 0.04, 0.04)
        else:
            x = self.X0 + 0.12 if side == "Ouest" else self.X1 - 0.16
            o, d = (x, w["pos"] + 0.1, w["sill"] + w["height"] - 0.06), (0.04, 0.4, 0.04)
        e = self.eq("IfcAirTerminal", f"Entrée d'air {r['name']} ({self.sinfo[r['skey']]['name']})", r["skey"], o, d, "Bouche", room=r, system=system)
        e.PredefinedType = "USERDEFINED"
        e.ObjectType = "Entrée d'air hygro"
        self.pset(e, "Bimys_Equipement", {"Marque": "AéroFlux", "Modèle": f"EA hygro {int(q)}", "Fonction": "Entrée d'air", "Débit nominal (m³/h)": float(q)})
        self.inlet_q[id(r)] = self.inlet_q.get(id(r), 0.0) + q
        return e

    def write_all(self, fname):
        os.makedirs(OUT_IFC, exist_ok=True)
        path = os.path.join(OUT_IFC, fname)
        self.f.write(path)
        n = len(self.f.by_type("IfcProduct"))
        print(f"OK {fname} : {n} objets, {os.path.getsize(path) // 1024} Ko")
        return path


# ====================================================================== 1. maison plain-pied PCBT
def maison_plain_pied():
    U = {"mur": 0.22, "fenetre": 1.1, "porte": 1.2, "sol": 0.25, "toit": 0.15, "mur_txt": "Brique 20 cm + doublage 140 mm"}
    b = Bat("plainpied", "Maison plain-pied PAC + plancher chauffant", "Maison plain-pied 118 m² : PAC air/eau, plancher chauffant, VMC double flux",
            "Maison RE 2020 : plancher chauffant basse température, VMC double flux, ballon thermodynamique", [("RDC", "RDC", 0.0, 2.7), ("COMBLES", "Combles", 2.7, 1.5)], 15.6, 9.6, U, mes="2022-11-04")
    X0, X1, Y0, Y1 = b.X0, b.X1, b.Y0, b.Y1
    b.room("RDC", "Séjour / cuisine", "Séjour", X0, 7.0, Y0, Y1)
    b.room("RDC", "Entrée", "Circulation", 7.0, 9.2, Y0, 4.0)
    b.room("RDC", "Dégagement", "Circulation", 7.0, X1, 4.0, 5.2)
    b.room("RDC", "Chambre 1", "Chambre", 9.2, 12.2, Y0, 4.0)
    b.room("RDC", "Chambre 2", "Chambre", 12.2, X1, Y0, 4.0)
    b.room("RDC", "Cellier / local technique", "Cellier", 7.0, 9.2, 5.2, Y1)
    b.room("RDC", "Salle de bains", "Salle de bains", 9.2, 11.6, 5.2, Y1)
    b.room("RDC", "WC / buanderie", "WC", 11.6, 12.8, 5.2, Y1)
    b.room("RDC", "Chambre 3", "Chambre", 12.8, X1, 5.2, Y1)
    b.door_ext("RDC", "Sud", 7.6, 1.0)
    b.undersized = {"Chambre 3"}
    b.build_envelope(big_window_rooms={"Séjour / cuisine"})
    b.build_boundaries()
    b.system("CH", "Chauffage plancher chauffant", "HEATING")
    b.system("ECS", "Eau chaude sanitaire", "DOMESTICHOTWATER")
    b.system("EF", "Eau froide", "DOMESTICCOLDWATER")
    b.system("VMC", "Ventilation double flux", "VENTILATION")
    cel = b.R("Cellier / local technique")
    pac = b.eq("IfcUnitaryEquipment", "PAC air/eau monobloc", "RDC", (7.4, Y1 + 0.9, 0.0), (1.0, 0.45, 0.9), "PAC", object_type="Pompe à chaleur air/eau", system="CH",
               psets=("AéroCalor", "Monobloc R32 6 kW", 6.0, {"Énergie": "Électricité", "COP à +7/35 °C": 4.9, "SCOP": 4.5, "Fluide frigorigène": "R32", "Charge en fluide (kg)": 1.3, "PRG du fluide (GWP)": 675.0, "Circuit hermétiquement scellé": True}))
    mod = b.eq("IfcUnitaryEquipment", "Module hydraulique PAC", "RDC", (7.2, Y1 - 0.5, 1.0), (0.45, 0.4, 0.7), "Equipement", object_type="Module hydraulique", room=cel, system="CH",
               psets=("AéroCalor", "Module MH-6", 2.0, {"Appoint électrique (kW)": 2.0}))
    b.pipe("RDC", [(7.7, Y1 + 0.9, 0.6), (7.7, Y1 - 0.1, 0.6), (7.35, Y1 - 0.1, 0.6), (7.35, Y1 - 0.1, 1.0)], "20x22", "Cuivre", 22, 1.0, "CH", "Liaison PAC aller", "Cuivre")
    b.pipe("RDC", [(8.0, Y1 + 0.9, 0.5), (8.0, Y1 - 0.05, 0.5), (7.5, Y1 - 0.05, 0.5), (7.5, Y1 - 0.05, 1.0)], "20x22", "Cuivre", 22, 1.0, "CH", "Liaison PAC retour", "Cuivre")
    for nm, cls, pre, z, x in (("Circulateur plancher chauffant", "IfcPump", "CIRCULATOR", 0.55, 7.9), ("Vase d'expansion 18 L", "IfcTank", "EXPANSION", 1.1, 8.4), ("Soupape de sécurité 3 bar", "IfcValve", "SAFETYCUTOFF", 0.95, 8.8)):
        e = b.eq(cls, nm, "RDC", (x, Y1 - 0.25, z), (0.07 if cls != "IfcTank" else 0.16, 0.15 if cls != "IfcTank" else 0.4), "Circulateur" if cls == "IfcPump" else "Vase" if cls == "IfcTank" else "Robinet", predefined=pre, room=cel, system="CH", cyl=True)
        b.equipment_psets(e, "HydroCal", nm, None, b.mes, {"Pression de gonflage (bar)": 1.0} if cls == "IfcTank" else {"Pression de tarage (bar)": 3.0} if cls == "IfcValve" else {"Puissance absorbée max (W)": 40.0}, "HC")
    # collecteur et boucles de plancher chauffant
    cx0, cy0 = 7.6, 5.35
    b.eq("IfcPipeFitting", "Collecteur plancher chauffant 8 départs", "RDC", (cx0 - 0.3, 5.25, 0.25), (0.7, 0.12, 0.25), "Multicouche", predefined="JUNCTION", room=cel, system="CH")
    b.pipe("RDC", [(7.35, Y1 - 0.5, 1.0), (7.35, cy0 + 0.1, 1.0), (7.35, cy0 + 0.1, 0.3)], "26x3", "Multicouche PER-Alu-PER", 26, 3.0, "CH", "Départ collecteur", "Multicouche")
    b.pipe("RDC", [(7.5, Y1 - 0.5, 0.9), (7.5, cy0 + 0.15, 0.9), (7.5, cy0 + 0.15, 0.3)], "26x3", "Multicouche PER-Alu-PER", 26, 3.0, "CH", "Retour collecteur", "Multicouche")
    step = 0.20
    k = 0
    for r in b.rooms:
        if not heated(r["name"]):
            continue
        p = b.size(r, step=10, factor=1.05)
        x0, x1, y0, y1 = r["x0"] + 0.15, r["x1"] - 0.15, r["y0"] + 0.15, r["y1"] - 0.15
        lane = 4.6 + 0.05 * k
        k += 1
        pts = [(cx0, cy0, 0.03), (cx0, lane, 0.03), (x0, lane, 0.03), (x0, y0, 0.03)]
        y = y0
        right = True
        while y + step <= y1 + 1e-6:
            pts.append((x1 if right else x0, y, 0.03))
            y = round(y + step, 3)
            pts.append((x1 if right else x0, y, 0.03))
            right = not right
        dedup = [pts[0]] + [q for i, q in enumerate(pts[1:]) if max(abs(q[j] - pts[i][j]) for j in range(3)) > 1e-6]
        b.pipe("RDC", dedup, "16x2", "Multicouche PER-Alu-PER", 16, 2.0, "CH", f"Boucle {r['name']} aller", "Multicouche", fittings=False)
        b.pipe("RDC", [(dedup[-1][0], y, 0.045), (r["x1"] - 0.06, y, 0.045), (r["x1"] - 0.06, lane + 0.02, 0.045), (cx0 + 0.1, lane + 0.02, 0.045), (cx0 + 0.1, cy0, 0.045)], "16x2", "Multicouche PER-Alu-PER", 16, 2.0, "CH", f"Boucle {r['name']} retour", "Multicouche", fittings=False)
        pc = b.eq("IfcSpaceHeater", f"Plancher chauffant {r['name']}", "RDC", (r["x0"] + 0.05, r["y0"] + 0.05, -0.02), (r["x1"] - r["x0"] - 0.1, r["y1"] - r["y0"] - 0.1, 0.02), "PCBT", room=r, system="CH")
        pc.PredefinedType = "USERDEFINED"
        pc.ObjectType = "Plancher chauffant basse température"
        b.pset(pc, "Pset_SpaceHeaterTypeCommon", {"OutputCapacity": float(p), "HeatTransferMedium": "WATER", "PlacementType": "FLOOR"})
        b.pset(pc, "Bimys_Equipement", {"Marque": "Calorys", "Modèle": "PCBT tube 16x2 pas 20 cm", "Puissance émise (W)": float(p), "Régime d'eau": "35/30 °C", "Pas de pose (cm)": 20.0})
        b.eq("IfcUnitaryControlElement", f"Thermostat {r['name']}", "RDC", (r["x0"] + 0.2, r["y0"] + 0.2, 1.5), (0.08, 0.03, 0.08), "Equipement", predefined="THERMOSTAT", room=r, system="CH")
    # ballon thermodynamique, EF, ECS
    bal = b.eq("IfcTank", "Ballon thermodynamique 200 L", "RDC", (8.6, 6.4, 0.0), (0.3, 1.75), "Ballon", predefined="STORAGE", room=cel, system="ECS", cyl=True,
               psets=("ThermaNova", "Thermo 200 air ambiant", 1.7, {"Capacité (L)": 200.0, "COP": 3.2, "Fluide frigorigène": "R134a", "Charge en fluide (kg)": 0.9, "PRG du fluide (GWP)": 1430.0, "Type d'anode": "Titane"}))
    b.eq("IfcValve", "Groupe de sécurité ECS 7 bar", "RDC", (8.6, 6.95, 0.3), (0.03, 0.12), "Robinet", predefined="PRESSURERELIEF", room=cel, system="ECS", cyl=True)
    b.eq("IfcPipeFitting", "Nourrice eau froide", "RDC", (7.2, 7.2, 0.02), (0.3, 0.1, 0.08), "PER EF", predefined="JUNCTION", room=cel, system="EF")
    b.pipe("RDC", [(7.3, Y1 + 0.3, 0.05), (7.3, 7.25, 0.05)], "20x1,9", "PER", 20, 1.9, "EF", "Arrivée", "PER EF")
    sdb, cuis, wc = b.R("Salle de bains"), b.R("Séjour / cuisine"), b.R("WC / buanderie")
    terms = [(b.sanitary(cuis, "SINK", (5.8, Y1 - 0.7)), (6.1, Y1 - 0.4)), (b.sanitary(sdb, "WASHHANDBASIN", (9.6, Y1 - 0.6)), (9.8, Y1 - 0.4)),
             (b.sanitary(sdb, "SHOWER", (10.6, Y1 - 1.0)), (11.0, Y1 - 0.5)), (b.sanitary(wc, "WCSEAT", (11.8, Y1 - 0.7)), (12.0, Y1 - 0.4))]
    for k, (term, p) in enumerate(terms):
        b.pipe("RDC", manhattan((7.3, 7.25), p, 0.06 + 0.02 * k, "y") + [(p[0], p[1], 0.6)], "16x1,5", "PER", 16, 1.5, "EF", "Distribution", "PER EF")
        if "WC" not in term.Name:
            b.pipe("RDC", manhattan((8.6, 6.7), (p[0] + 0.08, p[1]), 0.07 + 0.02 * k, "y") + [(p[0] + 0.08, p[1], 0.6)], "16x1,5", "PER", 16, 1.5, "ECS", "Distribution", "PER EC")
    # VMC double flux dans les combles
    cdf = b.eq("IfcAirToAirHeatRecovery", "VMC double flux haut rendement", "COMBLES", (7.4, 6.6, 0.25), (1.1, 0.6, 0.45), "VMC", predefined="FIXEDPLATECOUNTERFLOWEXCHANGER", system="VMC",
               psets=("AéroFlux", "DF Confort 300", 0.06, {"Rendement échangeur (%)": 90.0, "Débit maximal (m³/h)": 300.0, "Filtres": "ePM1 55 % soufflage, G4 reprise"}))
    hz = 0.5
    for r, q, kind in ((cuis, 45, "extraction"), (sdb, 30, "extraction"), (wc, 15, "extraction"), (b.R("Chambre 1"), 30, "insufflation"), (b.R("Chambre 2"), 30, "insufflation"), (b.R("Chambre 3"), 30, "insufflation"), (cuis, 45, "insufflation")):
        cx = (r["x0"] + r["x1"]) / 2 + (1.2 if (kind == "insufflation" and r is cuis) else 0)
        cy = (r["y0"] + r["y1"]) / 2
        if r is cuis and kind == "extraction":
            cx, cy = 6.2, Y1 - 0.8
        nm = f"Bouche d'{'extraction' if kind == 'extraction' else 'insufflation'} {r['name']}"
        b.air_terminal(r, nm, "Extraction" if kind == "extraction" else "Insufflation", q, (cx, cy), "VMC", kind=kind, dia=80 if q < 40 else 125)
        b.duct("RDC", [(cx, cy, r["h"]), (cx, cy, r["h"] + SLAB)], 80 if q < 40 else 125, "Gaine souple isolée", "VMC", "Piquage", "Souple")
        b.duct("COMBLES", manhattan((cx, cy), (7.95, 6.9 if kind == "extraction" else 7.0), hz, "y"), 80 if q < 40 else 125, "Gaine souple isolée", "VMC", "Extraction" if kind == "extraction" else "Insufflation", "Souple")
        hz += 0.06
    b.duct("COMBLES", [(7.4, 6.8, 0.5), (6.6, 6.8, 0.5), (6.6, 6.8, 1.4)], 160, "Conduit galva rigide", "VMC", "Rejet")
    b.duct("COMBLES", [(7.4, 7.0, 0.6), (6.2, 7.0, 0.6), (6.2, 7.0, 1.4)], 160, "Conduit galva rigide", "VMC", "Prise d'air neuf")
    return b


# ====================================================================== 2. immeuble collectif R+3
def immeuble():
    U = {"mur": 0.28, "fenetre": 1.3, "porte": 1.5, "sol": 0.30, "toit": 0.18, "mur_txt": "Béton 18 cm + ITE 140 mm"}
    H = 2.75
    st = [("RDC", "RDC", 0.0, H), ("R1", "R+1", H, H), ("R2", "R+2", 2 * H, H), ("R3", "R+3", 3 * H, H), ("TT", "Toiture terrasse", 4 * H, 1.5)]
    b = Bat("immeuble", "Résidence Les Tilleuls", "Immeuble collectif R+3 : 14 logements, chaufferie collective gaz", "Logements T3 de 78 m², chaufferie collective, colonnes montantes, comptage individuel, VMC collective hygro B",
            st, 30.6, 12.6, U, mes="2016-10-03")
    X0, X1, Y0, Y1 = b.X0, b.X1, b.Y0, b.Y1
    mid = (X0 + X1) / 2
    px0, px1 = mid - 2.0, mid + 2.0
    ym = (Y0 + Y1) / 2
    apts = []
    for skey in ("RDC", "R1", "R2", "R3"):
        sn = b.sinfo[skey]["name"]
        b.room(skey, f"Palier / escalier {sn}" if skey != "RDC" else "Hall d'entrée", "Circulation", px0, px1, Y0, Y1)
        for side_x in ("O", "E"):
            for side_y in ("S", "N"):
                if skey == "RDC" and side_x == "E" and side_y == "N":
                    b.room(skey, "Chaufferie", "Chaufferie", px1, px1 + 6.0, ym, Y1)
                    b.room(skey, "Local vélos", "Local", px1 + 6.0, X1, ym, Y1)
                    continue
                num = len(apts) + 1
                lg = f"Logement {num:02d}"
                # repère local : u depuis le pignon, v depuis la façade
                def rect(u0, u1, v0, v1, sx=side_x, sy=side_y):
                    if sx == "O":
                        x0, x1 = X0 + u0, X0 + u1
                    else:
                        x0, x1 = X1 - u1, X1 - u0
                    if sy == "S":
                        y0, y1 = Y0 + v0, Y0 + v1
                    else:
                        y0, y1 = Y1 - v1, Y1 - v0
                    return x0, x1, y0, y1
                U_ = px0 - X0
                V_ = ym - Y0
                rooms = {}
                for nm, usage, u0, u1, v0, v1 in (("Séjour", "Séjour", 0, 6.0, 0, V_), ("Chambre 1", "Chambre", 6.0, 9.2, 0, 3.4), ("Chambre 2", "Chambre", 9.2, U_, 0, 3.4),
                                                  ("Salle de bains", "Salle de bains", 6.0, 8.6, 3.4, V_), ("WC", "WC", 8.6, 9.8, 3.4, V_), ("Entrée", "Circulation", 9.8, U_, 3.4, V_)):
                    x0, x1, y0, y1 = rect(u0, u1, v0, v1)
                    rooms[nm] = b.room(skey, f"{lg} {nm}", usage, x0, x1, y0, y1)
                apts.append((skey, lg, rooms, side_x, side_y))
    b.door_ext("RDC", "Sud", mid - 0.8, 1.6, 2.2, "Porte du hall")
    b.door_ext("RDC", "Nord", px1 + 1.5, 1.0, 2.1, "Porte de la chaufferie")
    b.undersized = {"Logement 07 Chambre 2", "Logement 12 Séjour"}
    b.build_envelope()
    b.build_boundaries()
    for k, n, p in (("CH", "Chauffage collectif", "HEATING"), ("ECS", "Eau chaude sanitaire collective", "DOMESTICHOTWATER"), ("EF", "Eau froide", "DOMESTICCOLDWATER"), ("VMC", "VMC collective hygro B", "VENTILATION")):
        b.system(k, n, p)
    ch = b.R("Chaufferie")
    for i in range(2):
        bo = b.eq("IfcBoiler", f"Chaudière gaz condensation {i + 1}/2 (cascade)", "RDC", (ch["x0"] + 0.6 + i * 1.3, ch["y1"] - 0.9, 0.0), (0.9, 0.7, 1.6), "Equipement", predefined="WATER", room=ch, system="CH",
                  psets=("ThermaNova", "Condensa Pro 70", 70.0, {"Énergie": "Gaz naturel", "Rendement PCI 30 % (%)": 108.5, "Puissance chauffage (kW)": 70.0, "Montage": "Cascade 2 chaudières"}))
        b.pset(bo, "Pset_BoilerTypeCommon", {"EnergySource": "NATURALGAS"})
    for nm, cls, pre, pos, extra in (("Circulateur primaire chauffage", "IfcPump", "CIRCULATOR", (ch["x0"] + 3.4, ch["y1"] - 0.6), {"Puissance absorbée max (W)": 180.0}),
                                    ("Circulateur de bouclage ECS", "IfcPump", "CIRCULATOR", (ch["x0"] + 4.4, ch["y0"] + 0.8), {"Puissance absorbée max (W)": 60.0}),
                                    ("Vase d'expansion 100 L", "IfcTank", "EXPANSION", (ch["x0"] + 4.2, ch["y1"] - 0.6), {"Capacité (L)": 100.0, "Pression de gonflage (bar)": 1.5}),
                                    ("Soupape de sécurité chaufferie 4 bar", "IfcValve", "SAFETYCUTOFF", (ch["x0"] + 3.0, ch["y1"] - 0.4), {"Pression de tarage (bar)": 4.0}),
                                    ("Pot de décantation", "IfcFilter", "WATER", (ch["x0"] + 3.8, ch["y1"] - 1.2), {})):
        e = b.eq(cls, nm, "RDC", (pos[0], pos[1], 0.6 if cls != "IfcTank" else 0.0), (0.09 if cls != "IfcTank" else 0.3, 0.2 if cls != "IfcTank" else 0.9), "Circulateur" if cls == "IfcPump" else "Vase" if cls == "IfcTank" else "Robinet",
                 predefined=pre, room=ch, system="ECS" if "ECS" in nm else "CH", cyl=True)
        b.equipment_psets(e, "HydroCal", nm, None, b.mes, extra, "HC")
    bal = b.eq("IfcTank", "Préparateur ECS 750 L", "RDC", (ch["x0"] + 1.0, ch["y0"] + 0.9, 0.0), (0.45, 2.0), "Ballon", predefined="STORAGE", room=ch, system="ECS", cyl=True,
               psets=("ThermaNova", "Préparateur 750 L double serpentin", None, {"Capacité (L)": 750.0, "Type d'anode": "Magnésium", "Température de consigne (°C)": 60.0}))
    gs = b.eq("IfcValve", "Soupape de sécurité ECS 7 bar", "RDC", (ch["x0"] + 1.6, ch["y0"] + 0.5, 0.4), (0.03, 0.12), "Robinet", predefined="PRESSURERELIEF", room=ch, system="ECS", cyl=True)
    cg = b.eq("IfcFlowMeter", "Compteur général eau froide", "RDC", (ch["x0"] + 2.6, ch["y0"] + 0.4, 0.4), (0.25, 0.12, 0.15), "Equipement", predefined="WATERMETER", room=ch, system="EF")
    # colonnes montantes dans la gaine du palier
    gx, gy = px0 + 0.35, Y1 - 0.5
    top = b.order[-2]
    for circ, dx, mat, lab, outer, wall, sy, style in (("Départ", 0.0, "Acier noir", "DN40", 48.3, 3.2, "CH", "Acier"), ("Retour", 0.12, "Acier noir", "DN40", 48.3, 3.2, "CH", "Acier"),
                                                      ("Colonne EC", 0.24, "Cuivre", "26x28", 28, 1.0, "ECS", "PER EC"), ("Bouclage", 0.32, "Cuivre", "16x18", 18, 1.0, "ECS", "PER EC"), ("Colonne EF", 0.42, "Cuivre", "30x32", 32, 1.0, "EF", "PER EF")):
        x = gx + dx
        src = (ch["x0"] + 2.0 + dx, ch["y1"] - 0.3) if sy == "CH" else (ch["x0"] + 1.2 + dx, ch["y0"] + 0.4)
        b.pipe("RDC", manhattan(src, (x, gy), 2.45 - dx * 0.5, "y"), lab, mat, outer, wall, sy, circ, style)
        for skey in ("RDC", "R1", "R2", "R3"):
            b.pipe(skey, [(x, gy, 0.0 if skey != "RDC" else 2.45 - dx * 0.5), (x, gy, b.sinfo[skey]["h"])], lab, mat, outer, wall, sy, circ, style, fittings=False)
    # logements : module de comptage, collecteur, radiateurs en étoile ; ECS / EF ; VMC
    for (skey, lg, rooms, sx, sy) in apts:
        ent = rooms["Entrée"]
        cx = ent["x0"] + 0.4 if sx == "E" else ent["x1"] - 0.4
        cy = (ent["y0"] + ent["y1"]) / 2
        b.eq("IfcFlowMeter", f"Compteur d'énergie thermique {lg}", skey, (cx - 0.15, cy - 0.3, 1.1), (0.25, 0.1, 0.15), "Equipement", predefined="ENERGYMETER", room=ent, system="CH",
             psets=("HydroCal", "Compteur à ultrasons DN20", None, {"Télérelève": "Radio wM-Bus"}))
        b.eq("IfcFlowMeter", f"Compteur eau chaude {lg}", skey, (cx - 0.15, cy, 1.1), (0.15, 0.08, 0.1), "Equipement", predefined="WATERMETER", room=ent, system="ECS")
        b.eq("IfcFlowMeter", f"Compteur eau froide {lg}", skey, (cx - 0.15, cy + 0.2, 1.1), (0.15, 0.08, 0.1), "Equipement", predefined="WATERMETER", room=ent, system="EF")
        b.eq("IfcPipeFitting", f"Collecteur chauffage {lg}", skey, (cx - 0.2, cy - 0.6, 0.15), (0.4, 0.1, 0.15), "Multicouche", predefined="JUNCTION", room=ent, system="CH")
        b.pipe(skey, manhattan((gx, gy), (cx, cy - 0.55), 2.3, "y") + [(cx, cy - 0.55, 0.2)], "20x2", "Multicouche PER-Alu-PER", 20, 2.0, "CH", "Antenne départ", "Multicouche")
        b.pipe(skey, manhattan((gx + 0.12, gy), (cx + 0.1, cy - 0.55), 2.36, "y") + [(cx + 0.1, cy - 0.55, 0.2)], "20x2", "Multicouche PER-Alu-PER", 20, 2.0, "CH", "Antenne retour", "Multicouche")
        for nm, q in (("Chambre 1", 15), ("Chambre 2", 15), ("Séjour", 30)):
            b.inlet(rooms[nm], q, "VMC")
        targets = []
        for nm in ("Séjour", "Chambre 1", "Chambre 2", "Salle de bains", "Entrée"):
            r = rooms[nm]
            p = b.size(r)
            if b.loss(r) < 60:
                continue  # pièce intérieure : pas d'émetteur
            if nm == "Séjour":
                for k in range(2):
                    rr = dict(r)
                    rr["windows"] = r["windows"][k:k + 1] or r["windows"][:1]
                    rad, d, rt = b.radiator(rr, math.ceil(p / 2 / 25) * 25, "CH", name=f"Radiateur {r['name']} {k + 1}", trv=not (lg == "Logement 03" and k == 1))
                    targets.append((d, rt))
            else:
                rad, d, rt = b.radiator(r, p, "CH", towel=(nm == "Salle de bains"))
                targets.append((d, rt))
        b.star(skey, (cx, cy - 0.55), targets, "16x2", "Multicouche PER-Alu-PER", 16, 2.0, "CH", "Multicouche")
        # sanitaires
        sdb, wc, sej = rooms["Salle de bains"], rooms["WC"], rooms["Séjour"]
        kx = sej["x1"] - 0.8 if sx == "O" else sej["x0"] + 0.2
        ky = sej["y1"] - 0.7 if sy == "S" else sej["y0"] + 0.1
        items = [(b.sanitary(sej, "SINK", (kx, ky)), (kx + 0.3, ky + 0.3)), (b.sanitary(sdb, "WASHHANDBASIN", (sdb["x0"] + 0.3, sdb["y0"] + 0.4)), (sdb["x0"] + 0.5, sdb["y0"] + 0.6)),
                 (b.sanitary(sdb, "BATH", (sdb["x0"] + 0.4, sdb["y1"] - 0.8 if sy == "S" else sdb["y0"] + 0.1)), (sdb["x0"] + 0.6, (sdb["y0"] + sdb["y1"]) / 2)), (b.sanitary(wc, "WCSEAT", (wc["x0"] + 0.4, wc["y0"] + 0.4)), (wc["x0"] + 0.6, wc["y0"] + 0.8))]
        for k, (term, p) in enumerate(items):
            b.pipe(skey, manhattan((cx, cy + 0.2), p, 0.05 + 0.02 * k, "x") + [(p[0], p[1], 0.6)], "16x1,5", "PER", 16, 1.5, "EF", "Distribution", "PER EF")
            if term.PredefinedType != "WCSEAT":
                b.pipe(skey, manhattan((cx, cy), (p[0] + 0.08, p[1]), 0.06 + 0.02 * k, "x") + [(p[0] + 0.08, p[1], 0.6)], "16x1,5", "PER", 16, 1.5, "ECS", "Distribution", "PER EC")
        b.pipe(skey, manhattan((gx + 0.24, gy), (cx, cy), 2.2, "y") + [(cx, cy, 1.1)], "16x1,5", "PER", 16, 1.5, "ECS", "Antenne logement", "PER EC")
        b.pipe(skey, manhattan((gx + 0.42, gy), (cx, cy + 0.2), 2.16, "y") + [(cx, cy + 0.2, 1.1)], "16x1,5", "PER", 16, 1.5, "EF", "Antenne logement", "PER EF")
        # ventilation
        hz = sdb["h"] - 0.25
        for r, q, dia, pos in ((sej, 45, 125, (kx + 0.3, ky + 0.3)), (sdb, 30, 80, ((sdb["x0"] + sdb["x1"]) / 2, (sdb["y0"] + sdb["y1"]) / 2)), (wc, 15, 80, ((wc["x0"] + wc["x1"]) / 2, (wc["y0"] + wc["y1"]) / 2))):
            b.air_terminal(r, f"Bouche d'extraction {'cuisine' if r is sej else 'salle de bains' if r is sdb else 'WC'} {lg}", "Extraction", q, pos, "VMC", dia=dia)
            b.duct(skey, manhattan(pos, (px0 + 1.2, Y1 - 0.4), hz, "y"), dia, "Gaine souple isolée", "VMC", "Raccordement", "Souple")
            hz -= 0.12
    for skey in ("RDC", "R1", "R2", "R3"):
        b.duct(skey, [(px0 + 1.2, Y1 - 0.4, 0.0 if skey != "RDC" else 1.0), (px0 + 1.2, Y1 - 0.4, b.sinfo[skey]["h"])], 315, "Conduit galva rigide", "VMC", "Colonne collective")
    caisson = b.eq("IfcFan", "Caisson VMC collective hygro B", "TT", (px0 + 0.6, Y1 - 1.6, 0.0), (1.2, 0.9, 0.8), "VMC", object_type="Caisson VMC", system="VMC",
                   psets=("AéroFlux", "Collectif hygro 1800", 0.35, {"Débit maximal (m³/h)": 1800.0, "Type": "Simple flux hygroréglable B, basse consommation"}))
    b.duct("TT", [(px0 + 1.2, Y1 - 0.4, 0.0), (px0 + 1.2, Y1 - 0.4, 0.4), (px0 + 1.2, Y1 - 0.9, 0.4)], 315, "Conduit galva rigide", "VMC", "Aspiration caisson")
    return b


# ====================================================================== 3. clinique R+2 (ventilo-convecteurs 4 tubes, CTA)
def clinique():
    U = {"mur": 0.25, "fenetre": 1.2, "porte": 1.5, "sol": 0.28, "toit": 0.15, "mur_txt": "Béton 20 cm + ITE 160 mm"}
    H = 3.6
    st = [("RDC", "RDC", 0.0, H), ("R1", "R+1", H, H), ("R2", "R+2", 2 * H, H), ("TT", "Terrasse technique", 3 * H, 3.0)]
    b = Bat("clinique", "Clinique du Val", "Clinique R+2 : ventilo-convecteurs 4 tubes, groupe froid, CTA double flux", "Établissement de santé : chambres avec salle d'eau, bloc opératoire, eau glacée, chauffage, ECS bouclée",
            st, 48.6, 16.2, U, mes="2018-03-12")
    X0, X1, Y0, Y1 = b.X0, b.X1, b.Y0, b.Y1
    cy0, cy1 = 6.9, 9.3  # couloir central
    bay = 3.6
    nb = int((X1 - X0 - 4.0) / bay)
    gx = X0 + nb * bay  # zone technique / escalier à l'est
    for skey in ("RDC", "R1", "R2"):
        sn = b.sinfo[skey]["name"]
        b.room(skey, f"Couloir {sn}", "Circulation", X0, gx, cy0, cy1)
        b.room(skey, f"Escalier et gaine technique {sn}", "Circulation", gx, X1, Y0, Y1)
        for i in range(nb):
            x0, x1 = X0 + i * bay, X0 + (i + 1) * bay
            for side, (y0, y1) in (("S", (Y0, cy0)), ("N", (cy1, Y1))):
                num = f"{sn.replace('+', '')}{side}{i + 1:02d}"
                if skey == "RDC":
                    if side == "S" and i < 3:
                        if i == 0:
                            b.room(skey, "Hall d'accueil", "Circulation", X0, X0 + 3 * bay, Y0, cy0)
                        continue
                    if side == "N" and i >= nb - 4:
                        if i == nb - 4:
                            b.room(skey, "Local technique chaufferie", "Local technique", x0, gx, cy1, Y1)
                        continue
                    if side == "N" and i < 4:
                        if i == 0:
                            b.room(skey, "Bloc opératoire 1", "Bloc", X0, X0 + 2 * bay, cy1, Y1)
                        elif i == 2:
                            b.room(skey, "Bloc opératoire 2", "Bloc", X0 + 2 * bay, X0 + 4 * bay, cy1, Y1)
                        continue
                    nm = f"Consultation {num}" if side == "S" else f"Bureau médical {num}"
                    b.room(skey, nm, "Bureau", x0, x1, y0, y1)
                    continue
                # chambre + salle d'eau côté couloir
                if side == "S":
                    b.room(skey, f"Chambre {num}", "Chambre", x0, x1, y0, y1 - 2.2)
                    b.room(skey, f"Salle d'eau {num}", "Salle d'eau", x0, x0 + 2.0, y1 - 2.2, y1)
                    b.room(skey, f"Sas chambre {num}", "Circulation", x0 + 2.0, x1, y1 - 2.2, y1)
                else:
                    b.room(skey, f"Chambre {num}", "Chambre", x0, x1, y0 + 2.2, y1)
                    b.room(skey, f"Salle d'eau {num}", "Salle d'eau", x0, x0 + 2.0, y0, y0 + 2.2)
                    b.room(skey, f"Sas chambre {num}", "Circulation", x0 + 2.0, x1, y0, y0 + 2.2)
    b.door_ext("RDC", "Sud", X0 + 4.5, 2.0, 2.4, "Entrée principale")
    b.undersized = {"Chambre R1S04", "Chambre R2N07"}
    b.build_envelope(window=(1.4, 0.9, 1.6), big_window_rooms={"Hall d'accueil"})
    b.build_boundaries()
    for k, n, p in (("CH", "Chauffage (eau chaude 4 tubes)", "HEATING"), ("EG", "Eau glacée", "CHILLEDWATER"), ("ECS", "Eau chaude sanitaire bouclée", "DOMESTICHOTWATER"),
                    ("EF", "Eau froide", "DOMESTICCOLDWATER"), ("CTA", "Ventilation double flux (CTA)", "VENTILATION")):
        b.system(k, n, p)
    lt = b.R("Local technique chaufferie")
    for i in range(2):
        b.eq("IfcBoiler", f"Chaudière gaz condensation {i + 1}/2", "RDC", (lt["x0"] + 0.8 + i * 1.6, lt["y1"] - 1.2, 0.0), (1.1, 0.9, 1.8), "Equipement", predefined="WATER", room=lt, system="CH",
             psets=("ThermaNova", "Condensa Pro 150", 150.0, {"Énergie": "Gaz naturel", "Rendement PCI 30 % (%)": 108.0}))
    ecs = b.eq("IfcTank", "Préparateur ECS 1500 L", "RDC", (lt["x0"] + 4.6, lt["y0"] + 1.2, 0.0), (0.6, 2.3), "Ballon", predefined="STORAGE", room=lt, system="ECS", cyl=True,
               psets=("ThermaNova", "Préparateur 1500 L", None, {"Capacité (L)": 1500.0, "Température de consigne (°C)": 60.0, "Type d'anode": "Anode à courant imposé"}))
    for nm, cls, pre, pos, sy, extra in (("Circulateur primaire chauffage", "IfcPump", "CIRCULATOR", (lt["x0"] + 3.8, lt["y1"] - 0.5), "CH", {"Puissance absorbée max (W)": 450.0}),
                                        ("Pompe eau glacée", "IfcPump", "CIRCULATOR", (lt["x0"] + 6.0, lt["y1"] - 0.5), "EG", {"Puissance absorbée max (W)": 750.0}),
                                        ("Circulateur de bouclage ECS", "IfcPump", "CIRCULATOR", (lt["x0"] + 5.4, lt["y0"] + 0.5), "ECS", {"Puissance absorbée max (W)": 90.0}),
                                        ("Vase d'expansion chauffage 300 L", "IfcTank", "EXPANSION", (lt["x0"] + 7.0, lt["y1"] - 0.8), "CH", {"Capacité (L)": 300.0, "Pression de gonflage (bar)": 2.0}),
                                        ("Vase d'expansion eau glacée 200 L", "IfcTank", "EXPANSION", (lt["x0"] + 8.0, lt["y1"] - 0.8), "EG", {"Capacité (L)": 200.0, "Pression de gonflage (bar)": 2.0}),
                                        ("Soupape de sécurité chauffage 6 bar", "IfcValve", "SAFETYCUTOFF", (lt["x0"] + 3.2, lt["y1"] - 0.4), "CH", {"Pression de tarage (bar)": 6.0})):
        e = b.eq(cls, nm, "RDC", (pos[0], pos[1], 0.6 if cls != "IfcTank" else 0.0), (0.12 if cls != "IfcTank" else 0.35, 0.25 if cls != "IfcTank" else 1.1), "Circulateur" if cls == "IfcPump" else "Vase" if cls == "IfcTank" else "Robinet", predefined=pre, room=lt, system=sy, cyl=True)
        b.equipment_psets(e, "HydroCal", nm, None, b.mes, extra, "HC")
    gf = b.eq("IfcChiller", "Groupe froid à condensation par air", "TT", (X0 + 20.0, Y0 + 1.0, 0.0), (4.2, 2.2, 2.2), "PAC", predefined="AIRCOOLED", system="EG",
              psets=("AéroCalor", "Chiller AC-250 R32", 250.0, {"Puissance frigorifique (kW)": 250.0, "EER": 3.1, "SEER": 4.6, "Fluide frigorigène": "R32", "Charge en fluide (kg)": 38.0, "PRG du fluide (GWP)": 675.0}))
    cta = b.eq("IfcAirToAirHeatRecovery", "CTA double flux chambres et consultations", "TT", (X0 + 4.0, Y0 + 5.4, 0.0), (8.0, 2.0, 2.0), "VMC", predefined="ROTARYWHEEL", system="CTA",
               psets=("AéroFlux", "CTA DF 9000 roue", 9.0, {"Débit soufflage (m³/h)": 9000.0, "Rendement récupération (%)": 78.0, "Filtres": "F7 + F9 soufflage, F7 reprise", "Batteries": "Chaude 60 kW, froide 75 kW"}))
    ctab = b.eq("IfcAirToAirHeatRecovery", "CTA bloc opératoire (air neuf, surpression)", "TT", (X0 + 13.0, Y0 + 9.0, 0.0), (4.5, 1.6, 1.8), "VMC", predefined="FIXEDPLATECOUNTERFLOWEXCHANGER", system="CTA",
                psets=("AéroFlux", "CTA bloc ISO 7", 3.0, {"Débit soufflage (m³/h)": 3000.0, "Filtration terminale": "H14 (plafond soufflant)", "Taux de renouvellement (vol/h)": 15.0}))
    # colonnes dans la gaine technique (est)
    gt = b.R("Escalier et gaine technique RDC")
    rx, ry = gt["x0"] + 0.5, cy0 + 0.3
    nets = (("CH", "Départ", "Acier noir", "DN65", 76.1, 3.6, "Acier"), ("CH", "Retour", "Acier noir", "DN65", 76.1, 3.6, "Acier"), ("EG", "Départ", "Acier noir isolé", "DN80", 88.9, 4.0, "Froid"),
            ("EG", "Retour", "Acier noir isolé", "DN80", 88.9, 4.0, "Froid"), ("ECS", "Colonne", "Cuivre", "40x42", 42, 1.0, "PER EC"), ("ECS", "Bouclage", "Cuivre", "20x22", 22, 1.0, "PER EC"), ("EF", "Colonne", "Cuivre", "40x42", 42, 1.0, "PER EF"))
    for k, (sy, circ, mat, lab, outer, wall, style) in enumerate(nets):
        x = rx + 0.13 * k
        b.pipe("RDC", manhattan((lt["x0"] + 2.0 + 0.13 * k, lt["y1"] - 0.3), (x, ry), H - 0.5 - 0.05 * k, "y"), lab, mat, outer, wall, sy, circ, style)
        for skey in ("RDC", "R1", "R2"):
            b.pipe(skey, [(x, ry, 0.0 if skey != "RDC" else H - 0.5 - 0.05 * k), (x, ry, H)], lab, mat, outer, wall, sy, circ, style, fittings=False)
        # réseaux horizontaux dans le faux plafond du couloir
        for skey in ("RDC", "R1", "R2"):
            zz = H - SLAB - 0.35 - 0.05 * k
            b.pipe(skey, [(x, ry, zz), (x, cy0 + 0.25 + 0.12 * k, zz), (X0 + 0.4, cy0 + 0.25 + 0.12 * k, zz)], lab if outer < 60 else ("DN40" if outer > 80 else "DN32"), mat, 48.3 if outer > 80 else 42.4 if outer > 60 else outer, 3.2 if outer > 60 else wall, sy, circ, style)
    # gaines CTA : colonnes soufflage et reprise puis réseau en faux plafond du couloir
    for skey in ("RDC", "R1", "R2"):
        zz = H - SLAB - 0.15
        b.rect_duct(skey, [(gx + 1.8, cy1 - 0.4, 0.0 if skey != "RDC" else zz), (gx + 1.8, cy1 - 0.4, H)], 800, 500, "CTA", "Colonne soufflage")
        b.rect_duct(skey, [(gx + 2.8, cy1 - 0.4, 0.0 if skey != "RDC" else zz), (gx + 2.8, cy1 - 0.4, H)], 800, 500, "CTA", "Colonne reprise")
        b.rect_duct(skey, [(gx + 1.8, cy1 - 0.4, zz), (gx - 0.2, cy1 - 0.4, zz), (X0 + 1.0, cy1 - 0.4, zz)], 600, 300, "CTA", "Soufflage couloir")
        b.rect_duct(skey, [(gx + 2.8, cy1 - 0.4, zz - 0.35), (gx - 0.6, cy1 - 0.7, zz - 0.35), (X0 + 1.4, cy1 - 0.7, zz - 0.35)], 500, 250, "CTA", "Reprise couloir")
    b.rect_duct("TT", [(gx + 1.8, cy1 - 0.4, 0.0), (gx + 1.8, cy1 - 0.4, 1.0), (X0 + 12.0, cy1 - 0.4, 1.0), (X0 + 12.0, Y0 + 6.4, 1.0)], 800, 500, "CTA", "Soufflage CTA")
    b.rect_duct("TT", [(gx + 2.8, cy1 - 0.4, 0.0), (gx + 2.8, cy1 - 0.4, 1.6), (X0 + 12.0, cy1 - 0.4, 1.6), (X0 + 12.0, Y0 + 7.0, 1.6)], 800, 500, "CTA", "Reprise CTA")
    b.pipe("TT", [(rx + 0.26, ry, 0.0), (rx + 0.26, ry, 0.6), (X0 + 22.0, ry, 0.6), (X0 + 22.0, Y0 + 3.2, 0.6)], "DN80", "Acier noir isolé", 88.9, 4.0, "EG", "Départ groupe froid", "Froid")
    b.pipe("TT", [(rx + 0.39, ry, 0.0), (rx + 0.39, ry, 0.8), (X0 + 22.6, ry, 0.8), (X0 + 22.6, Y0 + 3.2, 0.8)], "DN80", "Acier noir isolé", 88.9, 4.0, "EG", "Retour groupe froid", "Froid")
    # terminaux par local
    for r in list(b.rooms):
        n = r["name"]
        zc = r["h"] - 0.35
        cxr, cyr = (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2
        if n.startswith("Chambre") or n.startswith("Consultation") or n.startswith("Bureau médical"):
            p = b.size(r)
            vc_y = r["y1"] - 0.6 if r["y1"] <= cy0 + 1e-6 or r["y1"] < cy1 else r["y0"] + 0.1
            vc = b.eq("IfcUnitaryEquipment", f"Ventilo-convecteur {n}", r["skey"], (r["x0"] + 0.4, vc_y, zc - 0.05), (1.0, 0.5, 0.3), "Equipement", object_type="Ventilo-convecteur 4 tubes gainable", room=r, system="CH",
                      psets=("AéroCalor", "VCG 4T", round(p / 1000.0, 2), {"Puissance calorifique (W)": float(p), "Puissance frigorifique (W)": float(round(max(1500, p * 2.5), -2)), "Régime chaud": "45/40 °C", "Régime froid": "7/12 °C"}))
            b.assign("EG", [vc])
            v1 = b.eq("IfcValve", f"Vanne 2 voies chaud {n}", r["skey"], (r["x0"] + 1.5, vc_y + 0.2, zc), (0.03, 0.08), "Robinet", predefined="REGULATING", room=r, system="CH", cyl=True)
            v1.ObjectType = "Vanne 2 voies motorisée"
            v2 = b.eq("IfcValve", f"Vanne 2 voies froid {n}", r["skey"], (r["x0"] + 1.6, vc_y + 0.3, zc), (0.03, 0.08), "Robinet", predefined="REGULATING", room=r, system="EG", cyl=True)
            v2.ObjectType = "Vanne 2 voies motorisée"
            yline = cy0 + 0.25 if vc_y < cy0 else cy0 + 0.25
            for k, (sy, circ, style) in enumerate((("CH", "Départ", "Multicouche"), ("CH", "Retour", "Multicouche"), ("EG", "Départ", "Froid"), ("EG", "Retour", "Froid"))):
                b.pipe(r["skey"], [(r["x0"] + 0.6 + 0.1 * k, yline + 0.12 * k, H - SLAB - 0.35 - 0.05 * k), (r["x0"] + 0.6 + 0.1 * k, vc_y + 0.25, H - SLAB - 0.35 - 0.05 * k), (r["x0"] + 0.6 + 0.1 * k, vc_y + 0.25, zc)],
                       "16x2", "Multicouche PER-Alu-PER", 16, 2.0, sy, circ, style)
            q = 60 if n.startswith("Chambre") else 90
            b.air_terminal(r, f"Diffuseur de soufflage {n}", "Soufflage", q, (cxr, cyr), "CTA", kind="soufflage", dia=160)
            b.duct(r["skey"], [(cxr, cyr, r["h"]), (cxr, cyr, H - SLAB - 0.15), (cxr, cy1 - 0.4, H - SLAB - 0.15)], 160, "Conduit galva rigide", "CTA", "Piquage soufflage")
            if not n.startswith("Chambre"):
                b.air_terminal(r, f"Grille de reprise {n}", "Reprise", q, (cxr + 0.8, cyr), "CTA", kind="reprise", dia=160)
        elif n.startswith("Salle d'eau"):
            b.air_terminal(r, f"Bouche d'extraction {n}", "Extraction", 60, (cxr, cyr), "CTA", dia=125)
            b.duct(r["skey"], [(cxr, cyr, r["h"]), (cxr, cyr, H - SLAB - 0.5), (cxr, cy1 - 0.7, H - SLAB - 0.5)], 125, "Conduit galva rigide", "CTA", "Piquage reprise")
            if b.loss(r) >= 60:
                b.radiator(r, b.size(r), None, electric=True, name=f"Sèche-serviettes électrique {n}")
            lav = b.sanitary(r, "WASHHANDBASIN", (r["x0"] + 0.2, r["y0"] + 0.3))
            dch = b.sanitary(r, "SHOWER", (r["x1"] - 1.0, r["y0"] + 0.2 if r["y1"] <= cy0 + 1e-6 else r["y1"] - 1.1))
            wcs = b.sanitary(r, "WCSEAT", (r["x0"] + 0.2, r["y1"] - 0.7 if r["y1"] <= cy0 + 1e-6 else r["y0"] + 0.1))
            for k, (sy, st_) in enumerate((("EF", "PER EF"), ("ECS", "PER EC"))):
                yline = cy0 + 0.25 + 0.12 * (5 + k)
                b.pipe(r["skey"], [(r["x0"] + 1.0 + 0.1 * k, yline, H - SLAB - 0.6 - 0.05 * k), (r["x0"] + 1.0 + 0.1 * k, (r["y0"] + r["y1"]) / 2, H - SLAB - 0.6 - 0.05 * k), (r["x0"] + 1.0 + 0.1 * k, (r["y0"] + r["y1"]) / 2, 0.6)],
                       "16x1,5", "PER", 16, 1.5, sy, "Distribution", st_)
        elif n.startswith("Bloc"):
            p = b.size(r)
            for j in range(2):
                b.air_terminal(r, f"Plafond soufflant {n} {j + 1}", "Soufflage", 900, (r["x0"] + 2.4 + j * 2.4, cyr), "CTA", kind="soufflage", dia=400)
            b.air_terminal(r, f"Grille de reprise basse {n}", "Reprise", 1500, (r["x0"] + 0.4, r["y1"] - 0.6), "CTA", kind="reprise", dia=250)
            rad, d, rt = b.radiator(r, p, "CH", name=f"Panneau rayonnant {n}", trv=False)
            b.pipe(r["skey"], manhattan((r["x0"] + 0.6, cy0 + 0.25), d, H - SLAB - 0.4) + [(d[0], d[1], 0.45)], "20x2", "Multicouche PER-Alu-PER", 20, 2.0, "CH", "Départ", "Multicouche")
            b.pipe(r["skey"], manhattan((r["x0"] + 0.7, cy0 + 0.37), rt, H - SLAB - 0.45) + [(rt[0], rt[1], 0.45)], "20x2", "Multicouche PER-Alu-PER", 20, 2.0, "CH", "Retour", "Multicouche")
        elif n.startswith("Hall"):
            p = b.size(r)
            for j in range(2):
                rr = dict(r)
                rr["windows"] = r["windows"][j:j + 1] or r["windows"][:1]
                rad, d, rt = b.radiator(rr, math.ceil(p / 2 / 25) * 25, "CH", name=f"Radiateur hall {j + 1}")
                b.pipe("RDC", manhattan((r["x0"] + 1.0 + j, cy0 + 0.25), d, H - SLAB - 0.4) + [(d[0], d[1], 0.45)], "16x2", "Multicouche PER-Alu-PER", 16, 2.0, "CH", "Départ", "Multicouche")
                b.pipe("RDC", manhattan((r["x0"] + 1.1 + j, cy0 + 0.37), rt, H - SLAB - 0.45) + [(rt[0], rt[1], 0.45)], "16x2", "Multicouche PER-Alu-PER", 16, 2.0, "CH", "Retour", "Multicouche")
    return b


# ====================================================================== 4. cinéma 3 salles (rooftops)
def cinema():
    U = {"mur": 0.30, "fenetre": 1.5, "porte": 2.0, "sol": 0.35, "toit": 0.20, "mur_txt": "Béton 25 cm + isolant 120 mm (acoustique)"}
    st = [("RDC", "RDC", 0.0, 7.0), ("TT", "Toiture", 7.0, 2.5)]
    b = Bat("cinema", "Cinéma Le Lumière", "Cinéma 3 salles : rooftops réversibles, grands volumes", "ERP type L : 3 salles de 120 à 220 places, hall, sanitaires publics, cabine de projection",
            st, 40.6, 30.6, U, mes="2015-06-20")
    X0, X1, Y0, Y1 = b.X0, b.X1, b.Y0, b.Y1
    b.room("RDC", "Hall / billetterie", "Circulation", X0, 18.0, Y0, 12.0)
    b.room("RDC", "Sanitaires hommes", "Sanitaires", 18.0, 22.0, Y0, 6.0)
    b.room("RDC", "Sanitaires femmes", "Sanitaires", 22.0, 26.0, Y0, 6.0)
    b.room("RDC", "Local technique", "Local technique", 26.0, X1, Y0, 6.0)
    b.room("RDC", "Circulation salles", "Circulation", 18.0, X1, 6.0, 12.0)
    b.room("RDC", "Salle 1", "Salle", X0, 14.0, 12.0, Y1)
    b.room("RDC", "Salle 2", "Salle", 14.0, 27.0, 12.0, Y1)
    b.room("RDC", "Salle 3", "Salle", 27.0, X1, 12.0, Y1)
    b.door_ext("RDC", "Sud", 6.0, 3.0, 2.4, "Entrée vitrée")
    b.door_ext("RDC", "Est", 8.0, 1.6, 2.2, "Issue de secours salles")
    b.build_envelope(window=(1.2, 1.0, 1.4), big_window_rooms={"Hall / billetterie"})
    b.build_boundaries()
    b.system("CVC", "Chauffage climatisation par rooftops", "AIRCONDITIONING")
    b.system("VMC", "Extraction sanitaires", "EXHAUST")
    b.system("ECS", "Eau chaude sanitaire", "DOMESTICHOTWATER")
    b.system("EF", "Eau froide", "DOMESTICCOLDWATER")
    places = {"Salle 1": 180, "Salle 2": 220, "Salle 3": 120}
    for k, r in enumerate([b.R("Salle 1"), b.R("Salle 2"), b.R("Salle 3"), b.R("Hall / billetterie")]):
        cx, cy = (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2
        p = math.ceil(b.loss(r) * 1.1 / 500.0) * 0.5
        if r["name"] == "Salle 3":
            p = math.floor(b.loss(r) * 0.65 / 500.0) * 0.5  # erreur volontaire : rooftop sous-dimensionné
        q = places.get(r["name"], 0) * 18 or 3000
        rt = b.eq("IfcUnitaryEquipment", f"Rooftop {r['name']}", "TT", (cx - 1.4, cy - 1.0, 0.0), (2.8, 2.0, 1.4), "PAC", object_type="Rooftop réversible", system="CVC",
                  psets=("AéroCalor", f"Rooftop RT-{int(p)}", p, {"Puissance calorifique (kW)": p, "Puissance frigorifique (kW)": round(p * 1.1, 0), "Débit d'air (m³/h)": float(q), "Air neuf (m³/h)": float(round(q * 0.55, -2)),
                                                                   "Fluide frigorigène": "R410A", "Charge en fluide (kg)": round(4 + p * 0.25, 1), "PRG du fluide (GWP)": 2088.0, "Pièce desservie": r["name"], "Récupération d'énergie": "Roue sur air extrait"}))
        w, h = (1000, 500) if q > 2500 else (800, 400)
        b.rect_duct("TT", [(cx - 0.4, cy, 0.4), (cx - 0.4, cy, 0.0)], w, h, "CVC", "Soufflage")
        b.rect_duct("TT", [(cx + 0.6, cy, 0.4), (cx + 0.6, cy, 0.0)], w, h, "CVC", "Reprise")
        zz = r["h"] - 0.5
        b.rect_duct("RDC", [(cx - 0.4, cy, r["h"] + SLAB), (cx - 0.4, cy, zz), (cx - 0.4, r["y0"] + 2.0, zz), (cx - 0.4, r["y1"] - 2.0, zz)], w, h, "CVC", "Soufflage")
        b.rect_duct("RDC", [(cx + 0.6, cy, r["h"] + SLAB), (cx + 0.6, cy, zz - 0.6)], w, h, "CVC", "Reprise")
        nd = 4 if r["name"].startswith("Salle") else 3
        for j in range(nd):
            yy = r["y0"] + 2.0 + j * (r["y1"] - r["y0"] - 4.0) / max(1, nd - 1)
            b.air_terminal(r, f"Diffuseur hélicoïdal {r['name']} {j + 1}", "Soufflage", q / nd, (cx - 0.4, yy), "CVC", kind="soufflage", dia=400)
        b.air_terminal(r, f"Grille de reprise {r['name']}", "Reprise", q, (cx + 0.6, cy), "CVC", kind="reprise", dia=500)
    lt = b.R("Local technique")
    ce = b.eq("IfcTank", "Chauffe-eau électrique 150 L", "RDC", (lt["x0"] + 1.0, lt["y0"] + 1.0, 0.0), (0.28, 1.4), "Ballon", predefined="STORAGE", room=lt, system="ECS", cyl=True,
              psets=("ThermaNova", "Stéatite 150 L", 2.2, {"Capacité (L)": 150.0, "Type d'anode": "Magnésium", "Température de consigne (°C)": 60.0}))
    b.eq("IfcValve", "Groupe de sécurité chauffe-eau", "RDC", (lt["x0"] + 1.4, lt["y0"] + 0.6, 0.3), (0.03, 0.12), "Robinet", predefined="PRESSURERELIEF", room=lt, system="ECS", cyl=True)
    caisson = b.eq("IfcFan", "Caisson d'extraction sanitaires", "TT", (21.0, 2.0, 0.0), (0.9, 0.7, 0.6), "VMC", object_type="Caisson VMC", system="VMC",
                   psets=("AéroFlux", "Caisson C4 1500", 0.25, {"Débit maximal (m³/h)": 1500.0}))
    for r in (b.R("Sanitaires hommes"), b.R("Sanitaires femmes")):
        for j in range(3):
            pos = (r["x0"] + 0.6 + j * 1.2, r["y1"] - 0.8)
            b.sanitary(r, "WCSEAT", pos, systems=("EF",))
            b.air_terminal(r, f"Bouche d'extraction {r['name']} {j + 1}", "Extraction", 30, (pos[0] + 0.2, pos[1] - 0.6), "VMC", dia=125)
            b.duct("RDC", [(pos[0] + 0.2, pos[1] - 0.6, r["h"] - 3.0), (pos[0] + 0.2, 1.0, r["h"] - 3.0), (21.4, 1.0, r["h"] - 3.0)], 125, "Conduit galva rigide", "VMC", "Extraction")
        for j in range(2):
            b.sanitary(r, "WASHHANDBASIN", (r["x0"] + 0.5 + j * 1.5, r["y0"] + 0.2))
        b.radiator(r, b.size(r), None, electric=True)
        b.pipe("RDC", manhattan((lt["x0"] + 1.0, lt["y0"] + 1.0), ((r["x0"] + r["x1"]) / 2, r["y0"] + 0.4), 0.1, "y") + [((r["x0"] + r["x1"]) / 2, r["y0"] + 0.4, 0.8)], "16x1,5", "PER", 16, 1.5, "EF", "Distribution", "PER EF")
        b.pipe("RDC", manhattan((lt["x0"] + 1.1, lt["y0"] + 1.2), ((r["x0"] + r["x1"]) / 2 + 0.1, r["y0"] + 0.4), 0.14, "y") + [((r["x0"] + r["x1"]) / 2 + 0.1, r["y0"] + 0.4, 0.8)], "16x1,5", "PER", 16, 1.5, "ECS", "Distribution", "PER EC")
    b.duct("RDC", [(21.4, 1.0, 4.0), (21.4, 1.0, 7.0)], 250, "Conduit galva rigide", "VMC", "Colonne extraction")
    b.duct("TT", [(21.4, 1.0, 0.0), (21.4, 1.0, 0.3), (21.4, 2.3, 0.3)], 250, "Conduit galva rigide", "VMC", "Aspiration caisson")
    b.pipe("RDC", [(lt["x0"] + 0.5, Y0 - 0.3, 0.1), (lt["x0"] + 0.5, lt["y0"] + 0.9, 0.1), (lt["x0"] + 1.0, lt["y0"] + 0.9, 0.1)], "26x3", "PER", 26, 3.0, "EF", "Arrivée", "PER EF")
    b.eq("IfcFlowMeter", "Compteur général eau froide", "RDC", (lt["x0"] + 0.4, lt["y0"] + 0.4, 0.3), (0.25, 0.12, 0.15), "Equipement", predefined="WATERMETER", room=lt, system="EF")
    return b


# ====================================================================== 5. immeuble de bureaux R+2 (VRV)
def bureaux():
    U = {"mur": 0.26, "fenetre": 1.4, "porte": 1.8, "sol": 0.30, "toit": 0.17, "mur_txt": "Béton 20 cm + ITE 140 mm"}
    H = 3.3
    st = [("RDC", "RDC", 0.0, H), ("R1", "R+1", H, H), ("R2", "R+2", 2 * H, H), ("TT", "Terrasse technique", 3 * H, 2.5)]
    b = Bat("bureaux", "Immeuble de bureaux Horizon", "Bureaux R+2 : DRV/VRV réversible, CTA d'air neuf", "Tertiaire : bureaux cloisonnés et open space, climatisation à débit de réfrigérant variable, CTA double flux",
            st, 36.6, 14.6, U, mes="2020-02-17")
    X0, X1, Y0, Y1 = b.X0, b.X1, b.Y0, b.Y1
    cy0, cy1 = 6.0, 8.0
    for skey in ("RDC", "R1", "R2"):
        sn = b.sinfo[skey]["name"]
        b.room(skey, f"Circulation {sn}", "Circulation", X0, 30.0, cy0, cy1)
        b.room(skey, f"Escalier et ascenseur {sn}", "Circulation", 30.0, X1, Y0, 9.0)
        b.room(skey, f"Sanitaires {sn}", "Sanitaires", 30.0, X1, 9.0, Y1)
        b.room(skey, f"Open space {sn}", "Bureau", X0, 15.0, Y0, cy0)
        for i in range(5):
            b.room(skey, f"Bureau {sn.replace('+', '')}-{i + 1}", "Bureau", 15.0 + i * 3.0, 18.0 + i * 3.0, Y0, cy0)
        b.room(skey, f"Salle de réunion {sn}", "Bureau", X0, 9.0, cy1, Y1)
        for i in range(7):
            b.room(skey, f"Bureau {sn.replace('+', '')}-{i + 6}", "Bureau", 9.0 + i * 3.0, 12.0 + i * 3.0, cy1, Y1)
    b.door_ext("RDC", "Est", 3.0, 1.8, 2.3, "Entrée")
    b.undersized = {"Bureau R1-9", "Salle de réunion R+2"}
    b.build_envelope(window=(1.6, 0.9, 1.6))
    b.build_boundaries()
    b.system("FRIGO", "DRV / VRV (fluide frigorigène)", "REFRIGERATION")
    b.system("CTA", "Air neuf double flux (CTA)", "VENTILATION")
    b.system("ECS", "Eau chaude sanitaire", "DOMESTICHOTWATER")
    b.system("EF", "Eau froide", "DOMESTICCOLDWATER")
    groups = {}
    for i, skey in enumerate(("RDC", "R1", "R2")):
        pass
    for g in range(2):
        u = b.eq("IfcUnitaryEquipment", f"Unité extérieure DRV {g + 1}/2", "TT", (6.0 + g * 9.0, Y0 + 1.0, 0.0), (2.6, 0.9, 1.8), "PAC", object_type="Unité extérieure DRV/VRV", system="FRIGO",
                 psets=("AéroCalor", "DRV-H 45 kW", 50.0, {"Puissance calorifique (kW)": 50.0, "Puissance frigorifique (kW)": 45.0, "SCOP": 4.1, "SEER": 6.9, "Fluide frigorigène": "R410A", "Charge en fluide (kg)": 18.5, "PRG du fluide (GWP)": 2088.0, "Récupération de chaleur": "Non (2 tubes réversible)"}))
        groups[g] = u
    cta = b.eq("IfcAirToAirHeatRecovery", "CTA d'air neuf double flux", "TT", (22.0, Y0 + 5.0, 0.0), (6.0, 1.6, 1.8), "VMC", predefined="ROTARYWHEEL", system="CTA",
               psets=("AéroFlux", "CTA AN 4500", 4.5, {"Débit air neuf (m³/h)": 4500.0, "Rendement récupération (%)": 80.0, "Filtres": "ePM1 70 % soufflage, ePM10 reprise"}))
    # colonnes dans le noyau
    nx, ny = 30.5, Y0 + 0.6
    for skey in ("RDC", "R1", "R2"):
        for k, (lab, outer) in enumerate((("26x28", 28), ("14x16", 16))):
            b.pipe(skey, [(nx + 0.15 * k, ny, 0.0), (nx + 0.15 * k, ny, H)], lab, "Cuivre frigorifique", outer, 1.0, "FRIGO", "Gaz" if k == 0 else "Liquide", "Cuivre", fittings=False)
        b.rect_duct(skey, [(nx + 1.5, ny + 0.3, 0.0 if skey != "RDC" else H - SLAB - 0.2), (nx + 1.5, ny + 0.3, H)], 600, 400, "CTA", "Colonne soufflage")
        b.rect_duct(skey, [(nx + 2.4, ny + 0.3, 0.0 if skey != "RDC" else H - SLAB - 0.2), (nx + 2.4, ny + 0.3, H)], 600, 400, "CTA", "Colonne reprise")
    b.pipe("TT", [(nx, ny, 0.0), (nx, ny, 0.5), (7.3, ny, 0.5), (7.3, Y0 + 1.4, 0.5)], "26x28", "Cuivre frigorifique", 28, 1.0, "FRIGO", "Gaz", "Cuivre")
    b.pipe("TT", [(nx + 0.15, ny, 0.0), (nx + 0.15, ny, 0.6), (16.3, ny + 0.1, 0.6), (16.3, Y0 + 1.4, 0.6)], "14x16", "Cuivre frigorifique", 16, 1.0, "FRIGO", "Liquide", "Cuivre")
    b.rect_duct("TT", [(nx + 1.5, ny + 0.3, 0.0), (nx + 1.5, ny + 0.3, 1.0), (nx + 1.5, Y0 + 5.6, 1.0), (28.0, Y0 + 5.6, 1.0)], 600, 400, "CTA", "Soufflage CTA")
    b.rect_duct("TT", [(nx + 2.4, ny + 0.3, 0.0), (nx + 2.4, ny + 0.3, 1.5), (nx + 2.4, Y0 + 6.2, 1.5), (28.0, Y0 + 6.2, 1.5)], 600, 400, "CTA", "Reprise CTA")
    for skey in ("RDC", "R1", "R2"):
        zz = H - SLAB - 0.25
        b.pipe(skey, [(nx, ny, zz), (nx, cy0 + 0.3, zz), (X0 + 0.5, cy0 + 0.3, zz)], "22x24", "Cuivre frigorifique", 24, 1.0, "FRIGO", "Gaz", "Cuivre")
        b.pipe(skey, [(nx + 0.15, ny, zz - 0.06), (nx + 0.15, cy0 + 0.45, zz - 0.06), (X0 + 0.5, cy0 + 0.45, zz - 0.06)], "12x14", "Cuivre frigorifique", 14, 1.0, "FRIGO", "Liquide", "Cuivre")
        b.rect_duct(skey, [(nx + 1.5, ny + 0.3, zz), (nx + 1.5, cy1 - 0.4, zz), (X0 + 1.0, cy1 - 0.4, zz)], 400, 250, "CTA", "Soufflage circulation")
        b.rect_duct(skey, [(nx + 2.4, ny + 0.3, zz - 0.35), (nx + 2.4, cy1 - 0.8, zz - 0.35), (X0 + 1.4, cy1 - 0.8, zz - 0.35)], 400, 250, "CTA", "Reprise circulation")
        for r in [x for x in b.rooms if x["skey"] == skey]:
            n = r["name"]
            cxr, cyr = (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2
            if n.startswith("Bureau") or n.startswith("Open") or n.startswith("Salle de réunion"):
                nbu = max(1, int(b.area(r) / 30))
                p = b.size(r)
                pu = math.ceil(p / nbu / 25) * 25
                for j in range(nbu):
                    ux = r["x0"] + (j + 0.5) * (r["x1"] - r["x0"]) / nbu
                    cs = b.eq("IfcUnitaryEquipment", f"Cassette DRV {n}{f' {j + 1}' if nbu > 1 else ''}", skey, (ux - 0.3, cyr - 0.3, r["h"] - 0.3), (0.6, 0.6, 0.3), "Equipement", object_type="Unité intérieure cassette DRV", room=r, system="FRIGO",
                                psets=("AéroCalor", "Cassette 600x600", round(pu / 1000.0, 1), {"Puissance calorifique (W)": float(pu), "Puissance frigorifique (W)": float(round(max(1700, pu * 2.2), -2)), "Détendeur électronique": True}))
                    for k, (lab, outer, zl) in enumerate((("10x12", 12, zz), ("6x8", 8, zz - 0.06))):
                        b.pipe(skey, [(ux + 0.05 * k, cy0 + 0.3 + 0.15 * k, zl), (ux + 0.05 * k, cyr, zl), (ux + 0.05 * k, cyr, r["h"] - 0.15)], lab, "Cuivre frigorifique", outer, 1.0, "FRIGO", "Gaz" if k == 0 else "Liquide", "Cuivre")
                    b.assign("FRIGO", [b.fitting(skey, (ux, cy0 + 0.3, zz), "pipe", "JUNCTION", "Raccord de dérivation (Refnet)", 0.016, "Cuivre", "22x24", dirs=[(1, 0, 0), (-1, 0, 0), (0, 1, 0)])])
                q = 25 * max(1, int(b.area(r) / 10))
                b.air_terminal(r, f"Diffuseur air neuf {n}", "Soufflage", q, (cxr + 1.0, cyr), "CTA", kind="soufflage", dia=160)
                b.duct(skey, [(cxr + 1.0, cyr, r["h"]), (cxr + 1.0, cyr, zz), (cxr + 1.0, cy1 - 0.4, zz)], 160, "Conduit galva rigide", "CTA", "Piquage soufflage")
                b.air_terminal(r, f"Grille de reprise {n}", "Reprise", q, (cxr - 1.0, cyr), "CTA", kind="reprise", dia=160)
            elif n.startswith("Sanitaires"):
                for j in range(3):
                    b.sanitary(r, "WCSEAT", (r["x0"] + 0.4 + j * 1.6, r["y1"] - 0.8), systems=("EF",))
                    b.air_terminal(r, f"Bouche d'extraction {n} {j + 1}", "Extraction", 30, (r["x0"] + 0.6 + j * 1.6, r["y1"] - 1.4), "CTA", dia=125)
                lav = b.sanitary(r, "WASHHANDBASIN", (r["x0"] + 0.4, r["y0"] + 0.3))
                ce = b.eq("IfcTank", f"Chauffe-eau électrique 30 L {skey}", skey, (r["x1"] - 0.6, r["y0"] + 0.4, 1.2), (0.2, 0.6), "Ballon", predefined="STORAGE", room=r, system="ECS", cyl=True,
                          psets=("ThermaNova", "Sous-évier 30 L", 1.2, {"Capacité (L)": 30.0, "Type d'anode": "Magnésium"}))
                b.pipe(skey, [(nx + 0.4, ny, 0.1), (nx + 0.4, r["y0"] + 0.4, 0.1), (r["x1"] - 0.6, r["y0"] + 0.4, 0.1), (r["x1"] - 0.6, r["y0"] + 0.4, 1.2)], "16x1,5", "PER", 16, 1.5, "EF", "Distribution", "PER EF")
                b.pipe(skey, [(r["x1"] - 0.5, r["y0"] + 0.4, 1.0), (r["x0"] + 0.6, r["y0"] + 0.4, 1.0), (r["x0"] + 0.6, r["y0"] + 0.4, 0.9)], "16x1,5", "PER", 16, 1.5, "ECS", "Distribution", "PER EC")
                b.radiator(r, b.size(r), None, electric=True)
        b.pipe(skey, [(nx + 0.4, ny, 0.0 if skey != "RDC" else 0.1), (nx + 0.4, ny, H if skey != "R2" else 0.1)], "26x3", "PER", 26, 3.0, "EF", "Colonne", "PER EF", fittings=False)
    return b


BATIMENTS = [
    ("maison_plain_pied_pcbt.ifc", maison_plain_pied, "Chambre 3 : plancher chauffant sous-dimensionné"),
    ("immeuble_collectif_r3.ifc", immeuble, "Logement 07 chambre 2 et Logement 12 séjour sous-dimensionnés ; Logement 03 : un radiateur sans robinet thermostatique"),
    ("clinique_r2.ifc", clinique, "Chambres R1S04 et R2N07 : ventilo-convecteurs sous-dimensionnés ; panneaux des blocs sans robinet thermostatique (régulation centrale)"),
    ("cinema_3_salles.ifc", cinema, "Salle 3 : rooftop sous-dimensionné"),
    ("bureaux_r2_drv.ifc", bureaux, "Bureau R1-9 et salle de réunion R+2 : cassettes sous-dimensionnées"),
]


def main():
    only = sys.argv[1:] or None
    for fname, fn, _ in BATIMENTS:
        if only and not any(o in fname for o in only):
            continue
        b = fn()
        b.write_all(fname)


if __name__ == "__main__":
    main()
