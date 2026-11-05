#!/usr/bin/env python3
"""
Bimys : génération des maquettes IFC4 pédagogiques (maison R+1 ~110 m²).

Usage :
    pip install ifcopenshell
    python tools/generate_maquette.py            # génère les deux variantes
Sorties :
    public/samples/maison_chaudiere_gaz.ifc
    public/samples/maison_pac_air_eau.ifc
    tools/out/expected_<variante>.json  (valeurs de contrôle pour les tests)

Ce script n'est PAS embarqué dans l'application (IfcOpenShell est sous LGPL,
il ne sert qu'à produire les fichiers d'exemple).

Repère : x vers l'est, y vers le nord, z vers le haut, unités en mètres.
Emprise extérieure 9,40 x 7,00 m, murs extérieurs 0,30 m, cloisons 0,10 m.
Hauteur sous plafond 2,50 m, plancher 0,20 m, hauteur d'étage 2,70 m.
"""
import json
import math
import os
import sys

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_IFC = os.path.join(ROOT, "public", "samples")
OUT_JSON = os.path.join(HERE, "out")

HSP = 2.50
SLAB = 0.20
FLOOR_H = 2.70
EXT_T = 0.30
X0, X1, Y0, Y1 = 0.30, 9.10, 0.30, 6.70  # faces intérieures des murs extérieurs

U_WALL, U_WIN, U_DOOR, U_FLOOR, U_CEIL = 0.36, 1.4, 1.8, 0.40, 0.20


class DeterministicGuid:
    """GlobalId reproductibles : régénérer la maquette ne casse pas les données
    (interventions, saisies) liées aux GlobalId dans l'application."""

    def __init__(self, seed):
        self.seed = seed
        self.n = 0

    def __call__(self):
        import uuid
        self.n += 1
        return ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL, f"bimys/{self.seed}/{self.n}").hex)


def api(_usecase, _f, **kw):
    return ifcopenshell.api.run(_usecase, _f, **kw)


class Builder:
    def __init__(self, variant):
        self.variant = variant
        ifcopenshell.guid.new = DeterministicGuid(variant)
        self.f = api("project.create_file", None, version="IFC4")
        f = self.f
        self.project = api("root.create_entity", f, ifc_class="IfcProject", name="Maison pédagogique Bimys")
        self.project.Description = "Maison individuelle R+1, maquette pédagogique Bac Pro ICCER / MEE"
        api("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"}, area={"is_metric": True, "raw": "METERS"}, volume={"is_metric": True, "raw": "METERS"})
        self.ctx = api("context.add_context", f, context_type="Model")
        self.body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=self.ctx)
        self.site = api("root.create_entity", f, ifc_class="IfcSite", name="Terrain")
        self.site.Description = "Saône-et-Loire (71)"
        self.building = api("root.create_entity", f, ifc_class="IfcBuilding", name="Maison R+1")
        api("aggregate.assign_object", f, products=[self.site], relating_object=self.project)
        api("aggregate.assign_object", f, products=[self.building], relating_object=self.site)
        for o in (self.site, self.building):
            o.ObjectPlacement = self.lp(None, (0, 0, 0))
        self.storeys = {}
        for key, name, elev in (("RDC", "RDC", 0.0), ("R1", "R+1", FLOOR_H), ("COMBLES", "Combles", 2 * FLOOR_H)):
            s = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name=name)
            s.Elevation = elev
            s.ObjectPlacement = self.lp(self.building.ObjectPlacement, (0, 0, elev))
            api("aggregate.assign_object", f, products=[s], relating_object=self.building)
            self.storeys[key] = s
        self.styles = {}
        self.materials = {}
        self.types = {}
        self.systems = {}
        self.spaces = {}
        self.ext_walls = {}
        self.slabs = {}
        self.expected = {"pipes": {}, "ducts": {}, "counts": {}, "rooms": {}}
        self.serial = 1000

    # ------------------------------------------------------------ géométrie
    def pt(self, p):
        return self.f.createIfcCartesianPoint([float(v) for v in p])

    def dirn(self, d):
        return self.f.createIfcDirection([float(v) for v in d])

    def ax3(self, origin, z=(0, 0, 1), x=(1, 0, 0)):
        return self.f.createIfcAxis2Placement3D(self.pt(origin), self.dirn(z), self.dirn(x))

    def lp(self, rel, origin, z=(0, 0, 1), x=(1, 0, 0)):
        return self.f.createIfcLocalPlacement(rel, self.ax3(origin, z, x))

    def shape(self, items, kind="SweptSolid"):
        rep = self.f.createIfcShapeRepresentation(self.body, "Body", kind, items)
        return self.f.createIfcProductDefinitionShape(None, None, [rep])

    def box_solid(self, dx, dy, dz, origin=(0, 0, 0)):
        prof = self.f.createIfcRectangleProfileDef("AREA", None, self.f.createIfcAxis2Placement2D(self.pt((dx / 2, dy / 2)), None), dx, dy)
        return self.f.createIfcExtrudedAreaSolid(prof, self.ax3(origin), self.dirn((0, 0, 1)), dz)

    def cyl_solid(self, r, length, origin=(0, 0, 0), axis=(0, 0, 1), hollow=None):
        if hollow:
            prof = self.f.createIfcCircleHollowProfileDef("AREA", None, None, r, hollow)
        else:
            prof = self.f.createIfcCircleProfileDef("AREA", None, None, r)
        refx = (1, 0, 0) if abs(axis[0]) < 0.9 else (0, 0, 1)
        return self.f.createIfcExtrudedAreaSolid(prof, self.ax3(origin, axis, refx), self.dirn((0, 0, 1)), length)

    def style(self, name, rgb, transparency=0.0):
        if name not in self.styles:
            col = self.f.createIfcColourRgb(None, *rgb)
            rend = self.f.createIfcSurfaceStyleRendering(col, transparency, None, None, None, None, None, None, "NOTDEFINED")
            self.styles[name] = self.f.createIfcSurfaceStyle(name, "BOTH", [rend])
        return self.styles[name]

    def paint(self, product, style_name):
        st = self.styles[style_name]
        for rep in product.Representation.Representations:
            for it in rep.Items:
                self.f.createIfcStyledItem(it, [st], None)

    def material(self, name, category=None):
        if name not in self.materials:
            m = api("material.add_material", self.f, name=name)
            if category:
                m.Category = category
            self.materials[name] = m
        return self.materials[name]

    # ------------------------------------------------------------ produits
    def product(self, ifc_class, name, storey, origin, solids, style=None, container=None, predefined=None, object_type=None, z=(0, 0, 1), x=(1, 0, 0), desc=None):
        st = self.storeys[storey]
        p = api("root.create_entity", self.f, ifc_class=ifc_class, name=name, predefined_type=predefined)
        if object_type:
            p.ObjectType = object_type
            if predefined is None and hasattr(p, "PredefinedType"):
                try:
                    p.PredefinedType = "USERDEFINED"
                except Exception:
                    pass
        if desc:
            p.Description = desc
        p.ObjectPlacement = self.lp(st.ObjectPlacement, origin, z, x)
        p.Representation = self.shape(solids)
        if style:
            self.paint(p, style)
        api("spatial.assign_container", self.f, products=[p], relating_structure=container or st)
        return p

    def pset(self, product, name, props):
        ps = api("pset.add_pset", self.f, product=product, name=name)
        api("pset.edit_pset", self.f, pset=ps, properties=props)
        return ps

    def qto(self, product, name, props):
        q = api("pset.add_qto", self.f, product=product, name=name)
        api("pset.edit_qto", self.f, qto=q, properties=props)
        return q

    def system(self, key, name, predefined):
        if key not in self.systems:
            s = api("system.add_system", self.f, ifc_class="IfcDistributionSystem")
            s.Name = name
            s.PredefinedType = predefined
            self.systems[key] = s
            self.f.createIfcRelServicesBuildings(ifcopenshell.guid.new(), None, None, None, s, [self.building])
        return self.systems[key]

    def assign(self, key, products):
        if key is None:
            return
        api("system.assign_system", self.f, products=list(products), system=self.systems[key])

    def next_serial(self, prefix):
        self.serial += 7
        return f"{prefix}-{2026 - 5}{self.serial:05d}"

    def equipment_psets(self, p, marque, modele, puissance_kw, mes, extra=None, serial_prefix="SN"):
        props = {"Marque": marque, "Modèle": modele, "Date de mise en service": mes, "Numéro de série": self.next_serial(serial_prefix)}
        if puissance_kw is not None:
            props["Puissance nominale (kW)"] = float(puissance_kw)
        if extra:
            props.update(extra)
        self.pset(p, "Bimys_Equipement", props)
        self.pset(p, "Pset_ManufacturerTypeInformation", {"Manufacturer": marque, "ModelLabel": modele})
        self.pset(p, "Pset_ManufacturerOccurrence", {"SerialNumber": props["Numéro de série"]})

    # ------------------------------------------------------------ architecture
    def build_architecture(self):
        f = self.f
        self.style("Mur", (0.86, 0.84, 0.80))
        self.style("Cloison", (0.93, 0.92, 0.90))
        self.style("Dalle", (0.72, 0.72, 0.72))
        self.style("Vitrage", (0.55, 0.75, 0.90), 0.6)
        self.style("Menuiserie", (0.95, 0.95, 0.95))
        self.style("Porte", (0.55, 0.38, 0.25))
        self.style("Toiture", (0.62, 0.30, 0.22))
        self.style("Espace", (0.6, 0.8, 0.6), 0.85)
        m_ext = self.material("Parpaing 20 cm + PSE 100 mm + plâtre", "Maçonnerie")
        m_int = self.material("Cloison plaque de plâtre 72/48", "Plâtre")
        m_slab = self.material("Béton armé", "Béton")

        for skey in ("RDC", "R1"):
            st = self.storeys[skey]
            walls = {
                "Sud": ((0, 0), 9.4, EXT_T),
                "Nord": ((0, Y1), 9.4, EXT_T),
                "Ouest": ((0, Y0), EXT_T, Y1 - Y0),
                "Est": ((X1, Y0), EXT_T, Y1 - Y0),
            }
            self.ext_walls[skey] = {}
            for side, ((x, y), dx, dy) in walls.items():
                w = self.product("IfcWall", f"Mur extérieur {side} {st.Name}", skey, (x, y, 0), [self.box_solid(dx, dy, FLOOR_H)], "Mur", predefined="SOLIDWALL")
                api("material.assign_material", f, products=[w], material=m_ext)
                length = max(dx, dy)
                self.pset(w, "Pset_WallCommon", {"IsExternal": True, "ThermalTransmittance": U_WALL, "LoadBearing": True, "Reference": "Mur ext. isolé ITI"})
                self.qto(w, "Qto_WallBaseQuantities", {"Length": length, "Width": EXT_T, "Height": FLOOR_H, "GrossSideArea": round(length * FLOOR_H, 3)})
                self.ext_walls[skey][side] = w

        partitions = {
            "RDC": [((5.30, Y0), 0.10, Y1 - Y0), ((5.40, 3.60), X1 - 5.40, 0.10), ((7.40, Y0), 0.10, 3.60 - Y0), ((7.50, 2.30), X1 - 7.50, 0.10)],
            "R1": [((4.00, Y0), 0.10, Y1 - Y0), ((X0, 3.50), 4.00 - X0, 0.10), ((5.90, Y0), 0.10, Y1 - Y0), ((6.00, 3.50), X1 - 6.00, 0.10)],
        }
        self.partitions = {}
        for skey, lst in partitions.items():
            self.partitions[skey] = []
            for i, ((x, y), dx, dy) in enumerate(lst):
                w = self.product("IfcWall", f"Cloison {i + 1} {self.storeys[skey].Name}", skey, (x, y, 0), [self.box_solid(dx, dy, HSP)], "Cloison", predefined="PARTITIONING")
                api("material.assign_material", f, products=[w], material=m_int)
                self.pset(w, "Pset_WallCommon", {"IsExternal": False, "LoadBearing": False})
                self.qto(w, "Qto_WallBaseQuantities", {"Length": max(dx, dy), "Width": 0.10, "Height": HSP})
                self.partitions[skey].append(w)

        # dalles
        s = self.product("IfcSlab", "Dallage sur terre-plein", "RDC", (0, 0, -SLAB), [self.box_solid(9.4, 7.0, SLAB)], "Dalle", predefined="BASESLAB")
        self.pset(s, "Pset_SlabCommon", {"IsExternal": True, "ThermalTransmittance": U_FLOOR, "Reference": "Dallage isolé sous chape"})
        api("material.assign_material", f, products=[s], material=m_slab)
        self.slabs["sol"] = s
        s = self.product("IfcSlab", "Plancher intermédiaire", "RDC", (X0, Y0, HSP), [self.box_solid(X1 - X0, Y1 - Y0, SLAB)], "Dalle", predefined="FLOOR")
        self.pset(s, "Pset_SlabCommon", {"IsExternal": False})
        api("material.assign_material", f, products=[s], material=m_slab)
        s = self.product("IfcSlab", "Plancher haut sous combles perdus", "R1", (X0, Y0, HSP), [self.box_solid(X1 - X0, Y1 - Y0, SLAB)], "Dalle", predefined="FLOOR")
        self.pset(s, "Pset_SlabCommon", {"IsExternal": True, "ThermalTransmittance": U_CEIL, "Reference": "Laine soufflée 300 mm"})
        api("material.assign_material", f, products=[s], material=m_slab)
        self.slabs["plafond"] = s

        # toiture deux pans (faîtage est-ouest)
        pitch = math.radians(35)
        half = 3.5 + 0.4
        slope_len = half / math.cos(pitch)
        roof_mat = self.material("Tuiles terre cuite sur charpente bois", "Couverture")
        for side, sign in (("Sud", 1), ("Nord", -1)):
            ydir = (0, sign * math.cos(pitch), math.sin(pitch))
            normal = (0, -sign * math.sin(pitch), math.cos(pitch))
            y_start = -0.4 if sign == 1 else 3.5
            prof = f.createIfcRectangleProfileDef("AREA", None, f.createIfcAxis2Placement2D(self.pt((9.8 / 2, slope_len / 2)), None), 9.8, slope_len)
            solid = f.createIfcExtrudedAreaSolid(prof, self.ax3((0, 0, 0)), self.dirn((0, 0, 1)), 0.15)
            r = self.product("IfcSlab", f"Pan de toiture {side}", "COMBLES", (-0.2, y_start, -0.25 if sign == 1 else -0.25 + half * math.tan(pitch)), [solid], "Toiture", predefined="ROOF", z=normal, x=(1, 0, 0))
            # orienter le repère local : x global, y = pente
            r.ObjectPlacement.RelativePlacement.Axis = self.dirn(normal)
            api("material.assign_material", f, products=[r], material=roof_mat)

        self.build_spaces()
        self.build_openings()

    def build_spaces(self):
        rooms = {
            "RDC": [
                ("Séjour", "Séjour", 0.30, 5.30, 0.30, 6.70),
                ("Cuisine", "Cuisine", 5.40, 9.10, 3.70, 6.70),
                ("Entrée", "Entrée", 5.40, 7.40, 0.30, 3.60),
                ("WC", "WC", 7.50, 9.10, 2.40, 3.60),
                ("Cellier / chaufferie", "Cellier", 7.50, 9.10, 0.30, 2.30),
            ],
            "R1": [
                ("Chambre 1", "Chambre", 0.30, 4.00, 3.60, 6.70),
                ("Chambre 2", "Chambre", 0.30, 4.00, 0.30, 3.50),
                ("Chambre 3", "Chambre", 6.00, 9.10, 3.60, 6.70),
                ("Salle de bains", "Salle de bains", 6.00, 9.10, 0.30, 3.50),
                ("Dégagement", "Circulation", 4.10, 5.90, 0.30, 6.70),
            ],
        }
        self.room_rects = {}
        for skey, lst in rooms.items():
            for name, usage, x0, x1, y0, y1 in lst:
                sp = api("root.create_entity", self.f, ifc_class="IfcSpace", name=name, predefined_type="INTERNAL")
                sp.LongName = name
                sp.ObjectType = usage
                sp.ObjectPlacement = self.lp(self.storeys[skey].ObjectPlacement, (x0, y0, 0))
                sp.Representation = self.shape([self.box_solid(x1 - x0, y1 - y0, HSP)])
                self.paint(sp, "Espace")
                api("aggregate.assign_object", self.f, products=[sp], relating_object=self.storeys[skey])
                a = round((x1 - x0) * (y1 - y0), 4)
                self.qto(sp, "Qto_SpaceBaseQuantities", {"Height": HSP, "NetFloorArea": a, "GrossFloorArea": a, "NetVolume": round(a * HSP, 4), "GrossVolume": round(a * HSP, 4), "NetPerimeter": round(2 * ((x1 - x0) + (y1 - y0)), 3)})
                self.pset(sp, "Pset_SpaceCommon", {"Reference": usage, "IsExternal": False})
                self.spaces[name] = sp
                self.room_rects[name] = (skey, x0, x1, y0, y1)

    # ouvertures : (étage, façade, position début, largeur, allège, hauteur, type, nom, pièce)
    def build_openings(self):
        f = self.f
        m_win = self.material("PVC double vitrage 4/16/4 argon", "Menuiserie")
        m_door = self.material("Porte acier isolée", "Menuiserie")
        ext = [
            ("RDC", "Sud", 1.70, 2.40, 0.00, 2.15, "W", "Porte-fenêtre séjour", "Séjour"),
            ("RDC", "Ouest", 2.90, 1.20, 0.90, 1.25, "W", "Fenêtre séjour ouest", "Séjour"),
            ("RDC", "Nord", 2.05, 1.20, 0.90, 1.25, "W", "Fenêtre séjour nord", "Séjour"),
            ("RDC", "Nord", 6.75, 1.00, 0.90, 1.25, "W", "Fenêtre cuisine nord", "Cuisine"),
            ("RDC", "Est", 4.70, 1.00, 1.10, 1.00, "W", "Fenêtre cuisine est", "Cuisine"),
            ("RDC", "Sud", 6.45, 0.90, 0.00, 2.15, "D", "Porte d'entrée", "Entrée"),
            ("RDC", "Est", 2.70, 0.50, 1.40, 0.60, "W", "Fenêtre WC", "WC"),
            ("RDC", "Sud", 8.00, 0.80, 0.00, 2.00, "D", "Porte de service cellier", "Cellier / chaufferie"),
            ("R1", "Nord", 1.55, 1.20, 0.90, 1.25, "W", "Fenêtre chambre 1", "Chambre 1"),
            ("R1", "Sud", 1.55, 1.20, 0.90, 1.25, "W", "Fenêtre chambre 2", "Chambre 2"),
            ("R1", "Nord", 7.05, 1.00, 0.90, 1.25, "W", "Fenêtre chambre 3", "Chambre 3"),
            ("R1", "Est", 1.60, 0.60, 1.30, 0.80, "W", "Fenêtre salle de bains", "Salle de bains"),
            ("R1", "Sud", 4.60, 0.80, 1.00, 1.00, "W", "Fenêtre dégagement", "Dégagement"),
        ]
        self.ext_openings = []
        for skey, side, pos, width, sill, height, kind, name, room in ext:
            wall = self.ext_walls[skey][side]
            if side in ("Sud", "Nord"):
                y = 0.0 if side == "Sud" else Y1
                o_origin, o_dims = (pos, y - 0.05, sill), (width, EXT_T + 0.1, height)
                fr_origin, fr_dims = (pos, y + 0.10, sill), (width, 0.08, height)
            else:
                x = 0.0 if side == "Ouest" else X1
                o_origin, o_dims = (x - 0.05, pos, sill), (EXT_T + 0.1, width, height)
                fr_origin, fr_dims = (x + 0.10, pos, sill), (0.08, width, height)
            self.make_opening(skey, wall, o_origin, o_dims, fr_origin, fr_dims, kind, name, width, height, m_win, m_door, external=True)
            self.ext_openings.append((skey, side, pos, width, sill, height, kind, name, room))

        interior = [
            ("RDC", 0, (5.25, 1.50), (0.2, 0.83), "Porte séjour / entrée"),
            ("RDC", 2, (7.35, 1.00), (0.2, 0.83), "Porte entrée / cellier"),
            ("RDC", 2, (7.35, 2.65), (0.2, 0.73), "Porte WC"),
            ("RDC", 1, (5.60, 3.55), (0.83, 0.2), "Porte cuisine"),
            ("R1", 0, (3.95, 4.50), (0.2, 0.83), "Porte chambre 1"),
            ("R1", 0, (3.95, 2.20), (0.2, 0.83), "Porte chambre 2"),
            ("R1", 2, (5.85, 4.50), (0.2, 0.83), "Porte chambre 3"),
            ("R1", 2, (5.85, 2.20), (0.2, 0.83), "Porte salle de bains"),
        ]
        for skey, wi, (x, y), (dx, dy), name in interior:
            wall = self.partitions[skey][wi]
            fr = (x + 0.05, y, 0) if dx < dy else (x, y + 0.05, 0)
            frd = (0.04, dy, 2.04) if dx < dy else (dx, 0.04, 2.04)
            self.make_opening(skey, wall, (x, y, 0), (dx, dy, 2.04), fr, frd, "D", name, max(dx, dy), 2.04, m_win, m_door, external=False)

    def make_opening(self, skey, wall, o_origin, o_dims, fr_origin, fr_dims, kind, name, width, height, m_win, m_door, external):
        f = self.f
        op = api("root.create_entity", f, ifc_class="IfcOpeningElement", name=f"Réservation {name}")
        op.ObjectPlacement = self.lp(self.storeys[skey].ObjectPlacement, o_origin)
        op.Representation = self.shape([self.box_solid(*o_dims)])
        f.createIfcRelVoidsElement(ifcopenshell.guid.new(), None, None, None, wall, op)
        cls = "IfcWindow" if kind == "W" else "IfcDoor"
        el = self.product(cls, name, skey, fr_origin, [self.box_solid(*fr_dims)], "Vitrage" if kind == "W" else "Porte")
        el.OverallWidth = width
        el.OverallHeight = height
        if kind == "W":
            el.PredefinedType = "WINDOW"
            api("material.assign_material", f, products=[el], material=m_win)
            self.pset(el, "Pset_WindowCommon", {"IsExternal": True, "ThermalTransmittance": U_WIN, "Reference": "Uw 1,4"})
        else:
            el.PredefinedType = "DOOR"
            api("material.assign_material", f, products=[el], material=m_door)
            if external:
                self.pset(el, "Pset_DoorCommon", {"IsExternal": True, "ThermalTransmittance": U_DOOR, "Reference": "Ud 1,8"})
            else:
                self.pset(el, "Pset_DoorCommon", {"IsExternal": False})
        self.qto(el, "Qto_WindowBaseQuantities" if kind == "W" else "Qto_DoorBaseQuantities", {"Width": width, "Height": height, "Area": round(width * height, 4)})
        f.createIfcRelFillsElement(ifcopenshell.guid.new(), None, None, None, op, el)
        if not hasattr(self, "openings_by_name"):
            self.openings_by_name = {}
        self.openings_by_name[name] = el
        return el

    # ------------------------------------------------------------ limites d'espaces
    def plane_boundary(self, space, element, origin, zdir, xdir, w, h, inners=()):
        f = self.f
        plane = f.createIfcPlane(self.ax3(origin, zdir, xdir))
        outer = f.createIfcPolyline([self.pt(p) for p in ((0, 0), (w, 0), (w, h), (0, h), (0, 0))])
        inner_curves = []
        for (u, v, iw, ih) in inners:
            inner_curves.append(f.createIfcPolyline([self.pt(p) for p in ((u, v), (u + iw, v), (u + iw, v + ih), (u, v + ih), (u, v))]))
        cbp = f.createIfcCurveBoundedPlane(plane, outer, inner_curves)
        geom = f.createIfcConnectionSurfaceGeometry(cbp, None)
        f.createIfcRelSpaceBoundary(ifcopenshell.guid.new(), None, "1stLevel", None, space, element, geom, "PHYSICAL", "EXTERNAL")

    def build_space_boundaries(self):
        """Limites d'espaces extérieures : murs (avec ouvertures en contours intérieurs),
        fenêtres et portes, plancher bas (RDC) et plafond (R+1)."""
        rooms_out = {}
        for name, (skey, x0, x1, y0, y1) in self.room_rects.items():
            sp = self.spaces[name]
            room = {"storey": skey, "walls": [], "windows": [], "doors": [], "floor": 0.0, "ceiling": 0.0}
            sides = []
            if abs(x0 - X0) < 1e-6:
                sides.append(("Ouest", y0, y1))
            if abs(x1 - X1) < 1e-6:
                sides.append(("Est", y0, y1))
            if abs(y0 - Y0) < 1e-6:
                sides.append(("Sud", x0, x1))
            if abs(y1 - Y1) < 1e-6:
                sides.append(("Nord", x0, x1))
            for side, a, b in sides:
                wall = self.ext_walls[skey][side]
                inners = []
                for (s2, side2, pos, width, sill, height, kind, oname, room_name) in self.ext_openings:
                    if s2 == skey and side2 == side and room_name == name:
                        u = pos - a
                        inners.append((u, sill, width, height))
                        el = self.openings_by_name[oname]
                        if side in ("Sud", "Nord"):
                            yy = Y0 if side == "Sud" else Y1
                            self.plane_boundary(sp, el, (pos - x0, yy - y0, sill), (0, -1 if side == "Sud" else 1, 0), (1, 0, 0), width, height)
                        else:
                            xx = X0 if side == "Ouest" else X1
                            self.plane_boundary(sp, el, (xx - x0, pos - y0, sill), (-1 if side == "Ouest" else 1, 0, 0), (0, 1, 0), width, height)
                        (room["windows"] if kind == "W" else room["doors"]).append({"name": oname, "area": round(width * height, 4)})
                L = b - a
                if side in ("Sud", "Nord"):
                    yy = Y0 if side == "Sud" else Y1
                    self.plane_boundary(sp, wall, (0, yy - y0, 0), (0, -1 if side == "Sud" else 1, 0), (1, 0, 0), L, HSP, inners)
                else:
                    xx = X0 if side == "Ouest" else X1
                    self.plane_boundary(sp, wall, (xx - x0, 0, 0), (-1 if side == "Ouest" else 1, 0, 0), (0, 1, 0), L, HSP, inners)
                gross = L * HSP
                net = gross - sum(i[2] * i[3] for i in inners)
                room["walls"].append({"side": side, "gross": round(gross, 4), "net": round(net, 4)})
            area = (x1 - x0) * (y1 - y0)
            if skey == "RDC":
                self.plane_boundary(sp, self.slabs["sol"], (0, 0, 0), (0, 0, -1), (1, 0, 0), x1 - x0, y1 - y0)
                room["floor"] = round(area, 4)
            else:
                self.plane_boundary(sp, self.slabs["plafond"], (0, 0, HSP), (0, 0, 1), (1, 0, 0), x1 - x0, y1 - y0)
                room["ceiling"] = round(area, 4)
            room["area"] = round(area, 4)
            room["volume"] = round(area * HSP, 4)
            rooms_out[name] = room
        self.expected["rooms"] = rooms_out

    # ------------------------------------------------------------ réseaux
    def seg_type(self, kind, label, material, outer_mm, wall_mm, family):
        key = (kind, label, material)
        if key in self.types:
            return self.types[key]
        f = self.f
        if kind == "pipe":
            t = api("root.create_entity", f, ifc_class="IfcPipeSegmentType", name=f"Tube {family} {label}", predefined_type="RIGIDSEGMENT" if "Cuivre" in material else "FLEXIBLESEGMENT")
            self.pset(t, "Pset_PipeSegmentTypeCommon", {"NominalDiameter": outer_mm / 1000.0, "OuterDiameter": outer_mm / 1000.0, "InnerDiameter": (outer_mm - 2 * wall_mm) / 1000.0, "Reference": label})
        else:
            t = api("root.create_entity", f, ifc_class="IfcDuctSegmentType", name=f"Gaine {family} {label}", predefined_type="RIGIDSEGMENT" if "galva" in material.lower() else "FLEXIBLESEGMENT")
            self.pset(t, "Pset_DuctSegmentTypeCommon", {"Shape": "ROUND", "NominalDiameterOrWidth": outer_mm / 1000.0, "Reference": label})
        api("material.assign_material", f, products=[t], material=self.material(material))
        self.pset(t, "Bimys_Reseau", {"Désignation": label, "Matériau": material})
        self.types[key] = t
        return t

    def run(self, storey, pts, kind, label, material, outer_mm, wall_mm, system, circuit, family, style, fittings=True, start_fitting=None):
        """Crée les segments d'une polyligne + coudes aux changements de direction."""
        f = self.f
        t = self.seg_type(kind, label, material, outer_mm, wall_mm, family)
        r = outer_mm / 2000.0
        segs, fits = [], []
        total = 0.0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            d = [b[k] - a[k] for k in range(3)]
            L = math.sqrt(sum(v * v for v in d))
            if L < 1e-6:
                continue
            u = [v / L for v in d]
            cls = "IfcPipeSegment" if kind == "pipe" else "IfcDuctSegment"
            hollow = wall_mm / 1000.0 if kind == "pipe" else None
            refx = (1, 0, 0) if abs(u[0]) < 0.9 else (0, 0, 1)
            seg = self.product(cls, f"{'Tube' if kind == 'pipe' else 'Gaine'} {label} {circuit}", storey, a, [self.cyl_solid(r, L, hollow=hollow)], style, z=tuple(u), x=refx)
            seg.PredefinedType = t.PredefinedType
            api("type.assign_type", f, related_objects=[seg], relating_type=t)
            self.qto(seg, "Qto_PipeSegmentBaseQuantities" if kind == "pipe" else "Qto_DuctSegmentBaseQuantities", {"Length": round(L, 4)})
            self.pset(seg, "Bimys_Reseau", {"Circuit": circuit, "Désignation": label})
            segs.append(seg)
            total += L
            if fittings and 0 < i:
                prev = pts[i - 1]
                d0 = [a[k] - prev[k] for k in range(3)]
                cross = (d0[1] * d[2] - d0[2] * d[1], d0[2] * d[0] - d0[0] * d[2], d0[0] * d[1] - d0[1] * d[0])
                if sum(abs(c) for c in cross) > 1e-9:
                    n0 = math.sqrt(sum(c * c for c in d0))
                    back = tuple(-c / n0 for c in d0)
                    fits.append(self.fitting(storey, a, kind, "BEND", f"Coude {label}", r * 1.18, style, label, dirs=[back, tuple(u)]))
        sk = (system, material, label, kind)
        self.expected["pipes" if kind == "pipe" else "ducts"].setdefault("|".join(sk[:3]), 0.0)
        self.expected["pipes" if kind == "pipe" else "ducts"]["|".join(sk[:3])] += total
        self.assign(system, segs + fits)
        return segs, fits

    def fitting(self, storey, p, kind, predefined, name, r, style, label, dirs=None, rect=None):
        """Raccord à sertir ou à emboîter : un manchon par branche, orienté selon les tubes raccordés.
        Coude : dirs = [vers le tronçon amont, vers le tronçon aval] ; té : 3 directions (défaut : x, -x, z)."""
        cls = "IfcPipeFitting" if kind == "pipe" else "IfcDuctFitting"
        dirs = dirs or [(1, 0, 0), (-1, 0, 0), (0, 0, 1)]
        solids = []
        for d in dirs:
            L = math.sqrt(sum(c * c for c in d)) or 1.0
            u = tuple(c / L for c in d)
            if rect:
                w, h = rect
                ln = max(w, h) * 0.6
                refx = (0, 0, 1) if abs(u[2]) < 0.9 else (1, 0, 0)
                prof = self.f.createIfcRectangleProfileDef("AREA", None, self.f.createIfcAxis2Placement2D(self.pt((0, 0)), None), w * 1.08, h * 1.08)
                start = tuple(-u[i] * h * 0.54 for i in range(3))
                solids.append(self.f.createIfcExtrudedAreaSolid(prof, self.ax3(start, u, refx), self.dirn((0, 0, 1)), ln + h * 0.54))
            else:
                ln = max(2.4 * r, 0.025)
                start = tuple(-u[i] * r for i in range(3))
                solids.append(self.cyl_solid(r, ln + r, origin=start, axis=u))
        fit = self.product(cls, name, storey, (p[0], p[1], p[2]), solids, style, predefined=predefined)
        self.pset(fit, "Bimys_Reseau", {"Désignation": label})
        self.count(cls + ":" + predefined)
        return fit

    def count(self, key, n=1):
        self.expected["counts"][key] = self.expected["counts"].get(key, 0) + n

    def box_equipment(self, cls, name, storey, origin, dims, style, predefined=None, object_type=None, container=None, system=None):
        p = self.product(cls, name, storey, origin, [self.box_solid(*dims)], style, container=container, predefined=predefined, object_type=object_type)
        self.count(cls)
        if system:
            self.assign(system, [p])
        return p

    def cyl_equipment(self, cls, name, storey, origin, r, h, style, predefined=None, object_type=None, container=None, system=None):
        p = self.product(cls, name, storey, origin, [self.cyl_solid(r, h)], style, container=container, predefined=predefined, object_type=object_type)
        self.count(cls)
        if system:
            self.assign(system, [p])
        return p

    # ------------------------------------------------------------ chauffage
    def build_heating(self):
        f = self.f
        self.style("Cuivre", (0.80, 0.45, 0.20))
        self.style("Multicouche", (0.92, 0.92, 0.92))
        self.style("Equipement", (0.95, 0.95, 0.97))
        self.style("Radiateur", (0.98, 0.98, 0.98))
        self.style("Robinet", (0.80, 0.10, 0.10))
        self.style("Circulateur", (0.10, 0.45, 0.25))
        self.style("Vase", (0.85, 0.15, 0.15))
        self.style("PAC", (0.85, 0.87, 0.88))
        self.system("CH", "Chauffage", "HEATING")
        cell = self.spaces["Cellier / chaufferie"]
        gas = self.variant == "gaz"

        if gas:
            gen = self.box_equipment("IfcBoiler", "Chaudière gaz à condensation", "RDC", (8.55, 0.70, 1.00), (0.40, 0.45, 0.75), "Equipement", predefined="WATER", container=cell, system="CH")
            self.equipment_psets(gen, "ThermaNova", "Condensa Duo 25 C", 24.0, "2017-10-12", {
                "Énergie": "Gaz naturel", "Puissance chauffage (kW)": 24.0, "Puissance ECS (kW)": 28.0,
                "Rendement PCI 30 % (%)": 108.0, "Type d'évacuation": "Ventouse concentrique 60/100 (type C13)",
                "Pression de service (bar)": 1.5,
            }, "TN")
            self.pset(gen, "Pset_BoilerTypeCommon", {"EnergySource": "NATURALGAS", "WaterStorageCapacity": 0.0})
            dep_start = (8.75, 1.00, 1.00)
        else:
            gen = self.box_equipment("IfcUnitaryEquipment", "PAC air/eau monobloc (unité extérieure)", "RDC", (9.60, 0.60, 0.30), (0.45, 1.10, 0.85), "PAC", object_type="Pompe à chaleur air/eau", container=None, system="CH")
            self.equipment_psets(gen, "AéroCalor", "Monobloc AW 8 kW", 8.0, "2018-09-20", {
                "Énergie": "Électricité", "Puissance calorifique à +7/35 °C (kW)": 8.0, "COP à +7/35 °C": 4.4,
                "Puissance calorifique à -7/55 °C (kW)": 6.1, "SCOP": 3.9,
                "Fluide frigorigène": "R410A", "Charge en fluide (kg)": 2.4, "PRG du fluide (GWP)": 2088.0,
                "Circuit hermétiquement scellé": False, "Alimentation électrique": "230 V mono",
            }, "AC")
            mod = self.box_equipment("IfcUnitaryEquipment", "Module hydraulique PAC", "RDC", (8.55, 0.70, 1.00), (0.40, 0.45, 0.75), "Equipement", object_type="Module hydraulique", container=cell, system="CH")
            self.equipment_psets(mod, "AéroCalor", "Module hydro MH-8 avec appoint 3 kW", 3.0, "2018-09-20", {"Appoint électrique (kW)": 3.0}, "AC")
            # liaisons hydrauliques PAC <-> module (cuivre 20x22 isolé)
            self.run("RDC", [(9.60, 1.00, 0.55), (9.00, 1.00, 0.55), (8.75, 1.00, 0.55), (8.75, 1.00, 1.00)], "pipe", "20x22", "Cuivre", 22, 1.0, "CH", "Liaison PAC aller", "cuivre", "Cuivre")
            self.run("RDC", [(9.60, 1.20, 0.65), (8.95, 1.20, 0.65), (8.95, 1.20, 1.00)], "pipe", "20x22", "Cuivre", 22, 1.0, "CH", "Liaison PAC retour", "cuivre", "Cuivre")
            dep_start = (8.75, 1.00, 1.00)

        # accessoires chaufferie
        pump = self.cyl_equipment("IfcPump", "Circulateur chauffage", "RDC", (8.75, 1.00, 0.55), 0.06, 0.13, "Circulateur", predefined="CIRCULATOR", container=cell, system="CH")
        self.equipment_psets(pump, "HydroCal", "Eco 25-60 classe A", 0.045, "2017-10-12" if gas else "2018-09-20", {"Puissance absorbée max (W)": 45.0, "Hauteur manométrique max (m)": 6.0, "Indice EEI": 0.20}, "HC")
        vase = self.cyl_equipment("IfcTank", "Vase d'expansion chauffage 12 L", "RDC", (8.20, 0.55, 1.10), 0.14, 0.40, "Vase", predefined="EXPANSION", container=cell, system="CH")
        self.equipment_psets(vase, "HydroCal", "VX 12 L", None, "2017-10-12" if gas else "2018-09-20", {"Capacité (L)": 12.0, "Pression de gonflage (bar)": 1.0, "Pression maximale (bar)": 3.0}, "VX")
        self.pset(vase, "Pset_TankTypeExpansion", {"ChargePressure": 100000.0})
        soup = self.cyl_equipment("IfcValve", "Soupape de sécurité chauffage 3 bar", "RDC", (8.95, 0.80, 0.95), 0.025, 0.08, "Robinet", predefined="SAFETYCUTOFF", container=cell, system="CH")
        self.equipment_psets(soup, "HydroCal", "SS 1/2\" 3 bar", None, "2017-10-12" if gas else "2018-09-20", {"Pression de tarage (bar)": 3.0}, "SS")
        filt = self.cyl_equipment("IfcFilter", "Filtre désembouage magnétique", "RDC", (8.95, 1.00, 0.35), 0.05, 0.20, "Equipement", predefined="WATER", container=cell, system="CH")
        self.equipment_psets(filt, "HydroCal", "MagFilter 3/4\"", None, "2017-10-12" if gas else "2018-09-20", {}, "MF")
        purge = self.cyl_equipment("IfcValve", "Purgeur d'air automatique", "RDC", (8.75, 1.00, 1.80), 0.02, 0.06, "Robinet", predefined="AIRRELEASE", container=cell, system=None)
        for nm, x in (("Vanne d'isolement départ chauffage", 8.75), ("Vanne d'isolement retour chauffage", 8.95)):
            self.cyl_equipment("IfcValve", nm, "RDC", (x, 1.10, 0.80), 0.02, 0.06, "Robinet", predefined="ISOLATING", container=cell, system="CH")
        th = self.box_equipment("IfcUnitaryControlElement", "Thermostat d'ambiance programmable", "RDC", (5.20, 3.0, 1.50), (0.10, 0.03, 0.12), "Equipement", predefined="THERMOSTAT", container=self.spaces["Séjour"], system="CH")
        self.equipment_psets(th, "ThermaNova", "ThermoProg Radio", None, "2017-10-12" if gas else "2018-09-20", {"Consigne confort (°C)": 20.0, "Consigne réduit (°C)": 17.0}, "TP")
        so = self.box_equipment("IfcSensor", "Sonde extérieure", "RDC", (4.0, 7.0, 2.0), (0.08, 0.04, 0.10), "Equipement", predefined="TEMPERATURESENSOR", system="CH")
        self.equipment_psets(so, "ThermaNova", "SE-10", None, "2017-10-12" if gas else "2018-09-20", {}, "SE")

        # radiateurs : (nom, pièce, étage, façade, a, b, puissance W, hauteur, TRV)
        rads = [
            ("Radiateur entrée", "Entrée", "RDC", "Sud", 5.60, 6.20, 500, 0.6, True),
            ("Radiateur séjour 1", "Séjour", "RDC", "Ouest", 3.00, 4.00, 900, 0.6, True),
            ("Radiateur séjour 2", "Séjour", "RDC", "Nord", 2.15, 3.15, 800, 0.6, False),
            ("Radiateur cuisine", "Cuisine", "RDC", "Nord", 6.85, 7.65, 450, 0.6, True),
            ("Radiateur chambre 1", "Chambre 1", "R1", "Nord", 1.80, 2.50, 500, 0.6, True),
            ("Radiateur chambre 2", "Chambre 2", "R1", "Sud", 1.90, 2.40, 350, 0.6, True),
            ("Radiateur chambre 3", "Chambre 3", "R1", "Nord", 7.25, 7.85, 450, 0.6, True),
            ("Sèche-serviettes salle de bains", "Salle de bains", "R1", "Est", 2.60, 3.10, 300, 1.2, True),
            ("Radiateur dégagement", "Dégagement", "R1", "Sud", 4.75, 5.25, 250, 0.6, True),
        ]
        self.rad_info = {}
        for name, room, sk, side, a, b, pw, h, trv in rads:
            L = b - a
            if side in ("Sud", "Nord"):
                y = Y0 + 0.05 if side == "Sud" else Y1 - 0.15
                origin, dims = (a, y, 0.45), (L, 0.10, h)
                dpt, rpt = (b, y + 0.05), (a, y + 0.05)
            else:
                x = X0 + 0.05 if side == "Ouest" else X1 - 0.15
                origin, dims = (x, a, 0.45), (0.10, L, h)
                dpt, rpt = (x + 0.05, b), (x + 0.05, a)
            ot = "Radiateur sèche-serviettes" if "Sèche" in name else "Radiateur acier panneaux"
            rad = self.box_equipment("IfcSpaceHeater", name, sk, origin, dims, "Radiateur", predefined="RADIATOR", object_type=None, container=self.spaces[room], system="CH")
            rad.ObjectType = ot
            self.pset(rad, "Pset_SpaceHeaterTypeCommon", {"OutputCapacity": float(pw), "HeatTransferMedium": "WATER", "PlacementType": "WALL", "NumberOfPanels": 1 if pw < 500 else 2})
            self.equipment_psets(rad, "Calorys", f"{'Séchoir' if 'Sèche' in name else 'Type 21'} H{int(h * 1000)} L{int(round(L * 1000))}", pw / 1000.0, "2017-10-12" if gas else "2018-09-20", {
                "Puissance nominale à ΔT 50 K (W)": float(pw), "Exposant n": 1.3, "Régime nominal": "75/65/20 °C",
            }, "CA")
            if trv:
                v = self.cyl_equipment("IfcValve", f"Robinet thermostatique {name.lower().replace('radiateur ', '').replace('sèche-serviettes ', 'sèche-serviettes ')}", sk, (dpt[0], dpt[1], 0.40), 0.022, 0.09, "Robinet", predefined="REGULATING", object_type=None, container=self.spaces[room], system="CH")
                v.ObjectType = "Robinet thermostatique"
                self.pset(v, "Bimys_Equipement", {"Marque": "Calorys", "Modèle": "Tête thermostatique T30", "Plage de réglage": "* à 5 (8 à 28 °C)"})
            else:
                v = self.cyl_equipment("IfcValve", f"Robinet manuel {name.lower().replace('radiateur ', '')}", sk, (dpt[0], dpt[1], 0.40), 0.02, 0.07, "Robinet", predefined="REGULATING", container=self.spaces[room], system="CH")
                v.ObjectType = "Robinet manuel"
            ts = self.cyl_equipment("IfcValve", f"Té de réglage {name.lower().replace('radiateur ', '')}", sk, (rpt[0], rpt[1], 0.40), 0.018, 0.06, "Robinet", predefined="REGULATING", container=self.spaces[room], system="CH")
            ts.ObjectType = "Té de réglage"
            self.rad_info[name] = (sk, dpt, rpt)

        # ---- distribution RDC (cuivre)
        dz = 0.06
        z = 0.15
        D = [(dep_start[0], dep_start[1], 1.00), (8.75, 1.00, z), (8.75, 0.40, z)]
        # 16x18 : chaudière -> té entrée (6.20) -> té colonne (4.60)
        self.run("RDC", D + [(6.20, 0.40, z)], "pipe", "16x18", "Cuivre", 18, 1.0, "CH", "Départ", "cuivre", "Cuivre")
        self.run("RDC", [(6.20, 0.40, z), (4.60, 0.40, z)], "pipe", "16x18", "Cuivre", 18, 1.0, "CH", "Départ", "cuivre", "Cuivre", fittings=False)
        R = [(8.95, 1.00, 1.00), (8.95, 1.00, z + dz), (8.95, 0.40 + 0.0, z + dz)]
        self.run("RDC", R + [(5.60, 0.40, z + dz)], "pipe", "16x18", "Cuivre", 18, 1.0, "CH", "Retour", "cuivre", "Cuivre")
        self.run("RDC", [(5.60, 0.40, z + dz), (4.60, 0.40, z + dz)], "pipe", "16x18", "Cuivre", 18, 1.0, "CH", "Retour", "cuivre", "Cuivre", fittings=False)
        for p in ((6.20, 0.40, z), (4.60, 0.40, z), (5.60, 0.40, z + dz), (4.60, 0.40, z + dz)):
            self.assign("CH", [self.fitting("RDC", p, "pipe", "JUNCTION", "Té cuivre 16x18", 0.012, "Cuivre", "16x18")])
        # 14x16 : boucle séjour / cuisine
        dep = [(4.60, 0.40, z), (0.40, 0.40, z), (0.40, 4.00, z)]
        self.run("RDC", dep, "pipe", "14x16", "Cuivre", 16, 1.0, "CH", "Départ", "cuivre", "Cuivre")
        self.run("RDC", [(0.40, 4.00, z), (0.40, 6.60, z), (3.15, 6.60, z)], "pipe", "14x16", "Cuivre", 16, 1.0, "CH", "Départ", "cuivre", "Cuivre")
        self.run("RDC", [(3.15, 6.60, z), (7.65, 6.60, z)], "pipe", "14x16", "Cuivre", 16, 1.0, "CH", "Départ", "cuivre", "Cuivre", fittings=False)
        ret = [(4.60, 0.40, z + dz), (0.40, 0.40, z + dz), (0.40, 3.00, z + dz)]
        self.run("RDC", ret, "pipe", "14x16", "Cuivre", 16, 1.0, "CH", "Retour", "cuivre", "Cuivre")
        self.run("RDC", [(0.40, 3.00, z + dz), (0.40, 6.60, z + dz), (2.15, 6.60, z + dz)], "pipe", "14x16", "Cuivre", 16, 1.0, "CH", "Retour", "cuivre", "Cuivre")
        self.run("RDC", [(2.15, 6.60, z + dz), (6.85, 6.60, z + dz)], "pipe", "14x16", "Cuivre", 16, 1.0, "CH", "Retour", "cuivre", "Cuivre", fittings=False)
        for p in ((0.40, 4.00, z), (3.15, 6.60, z), (0.40, 3.00, z + dz), (2.15, 6.60, z + dz)):
            self.assign("CH", [self.fitting("RDC", p, "pipe", "JUNCTION", "Té cuivre 14x16", 0.010, "Cuivre", "14x16")])
        # piquages radiateurs RDC en 12x14 (remontées verticales)
        for name in ("Radiateur entrée", "Radiateur séjour 1", "Radiateur séjour 2", "Radiateur cuisine"):
            sk, dpt, rpt = self.rad_info[name]
            # le collecteur est à 0,10 m du mur, les piquages remontent à l'aplomb des raccords
            dp = self.snap_to_line(dpt)
            rp = self.snap_to_line(rpt)
            self.run("RDC", [(dp[0], dp[1], z), (dp[0], dp[1], 0.45)], "pipe", "12x14", "Cuivre", 14, 1.0, "CH", "Départ", "cuivre", "Cuivre")
            self.run("RDC", [(rp[0], rp[1], z + dz), (rp[0], rp[1], 0.45)], "pipe", "12x14", "Cuivre", 14, 1.0, "CH", "Retour", "cuivre", "Cuivre")
        # colonne montante multicouche 20
        self.run("RDC", [(4.60, 0.40, z), (4.60, 0.40, FLOOR_H + z)], "pipe", "20x2", "Multicouche PER-Alu-PER", 20, 2.0, "CH", "Départ", "multicouche", "Multicouche")
        self.run("RDC", [(4.60, 0.40, z + dz), (4.60, 0.40, FLOOR_H + z + dz)], "pipe", "20x2", "Multicouche PER-Alu-PER", 20, 2.0, "CH", "Retour", "multicouche", "Multicouche")
        col = self.box_equipment("IfcPipeFitting", "Collecteur chauffage R+1 (5 départs)", "R1", (4.45, 0.35, 0.10), (0.30, 0.12, 0.15), "Multicouche", predefined="JUNCTION", container=self.spaces["Dégagement"], system="CH")
        # étoile R+1 en multicouche 16x2 (chaque circuit à sa propre altitude)
        circuits = [
            ("Radiateur dégagement", [(4.60, 0.40)], 0),
            ("Radiateur chambre 2", [(4.60, 0.40)], 1),
            ("Radiateur chambre 1", [(4.60, 0.40), (4.20, 0.40), (4.20, 6.60)], 2),
            ("Radiateur chambre 3", [(4.60, 0.40), (5.80, 0.40), (5.80, 6.60)], 3),
            ("Sèche-serviettes salle de bains", [(4.60, 0.40), (5.80, 0.40), (5.80, 0.35), (9.00, 0.35)], 4),
        ]
        for name, path, k in circuits:
            sk, dpt, rpt = self.rad_info[name]
            zz = 0.05 + 0.025 * k
            for circ, end, zc in (("Départ", dpt, zz), ("Retour", rpt, zz + 0.0125)):
                end2 = self.snap_to_line(end)
                pts = [(x, y, zc) for (x, y) in path]
                last = pts[-1]
                if abs(last[0] - end2[0]) > 1e-6 and abs(last[1] - end2[1]) > 1e-6:
                    # aller d'abord le long de la dernière direction
                    if len(pts) >= 2 and abs(pts[-2][0] - last[0]) < 1e-6:
                        pts.append((last[0], end2[1], zc))
                    else:
                        pts.append((end2[0], last[1], zc))
                pts.append((end2[0], end2[1], zc))
                pts.append((end2[0], end2[1], 0.45))
                self.run("R1", pts, "pipe", "16x2", "Multicouche PER-Alu-PER", 16, 2.0, "CH", circ, "multicouche", "Multicouche")

        # circuit primaire ballon (chaudière -> ballon) en cuivre 16x18
        self.run("RDC", [(8.65, 1.15, 1.00), (8.65, 1.90, 1.00), (8.15, 1.90, 1.00)], "pipe", "16x18", "Cuivre", 18, 1.0, "CH", "Primaire ECS aller", "cuivre", "Cuivre")
        self.run("RDC", [(8.70, 1.15, 0.80), (8.70, 1.95, 0.80), (8.15, 1.95, 0.80)], "pipe", "16x18", "Cuivre", 18, 1.0, "CH", "Primaire ECS retour", "cuivre", "Cuivre")

    def snap_to_line(self, p):
        """Projette un point de raccord sur la ligne de distribution à 0,10 m du mur."""
        x, y = p
        if abs(y - (Y0 + 0.10)) < 0.11:
            return (x, 0.40)
        if abs(y - (Y1 - 0.10)) < 0.11:
            return (x, 6.60)
        if abs(x - (X0 + 0.10)) < 0.11:
            return (0.40, y)
        if abs(x - (X1 - 0.10)) < 0.11:
            return (9.00, y)
        return p

    # ------------------------------------------------------------ sanitaire
    def build_plumbing(self):
        self.style("PER EF", (0.15, 0.35, 0.85))
        self.style("PER EC", (0.85, 0.15, 0.15))
        self.style("Sanitaire", (0.97, 0.97, 0.97))
        self.style("Ballon", (0.92, 0.92, 0.92))
        self.system("ECS", "Eau chaude sanitaire", "DOMESTICHOTWATER")
        self.system("EF", "Eau froide", "DOMESTICCOLDWATER")
        cell = self.spaces["Cellier / chaufferie"]
        gas = self.variant == "gaz"
        cap = 150 if gas else 200
        bal = self.cyl_equipment("IfcTank", f"Ballon ECS {cap} L", "RDC", (7.85, 1.85, 0.0), 0.28, 1.20 if gas else 1.45, "Ballon", predefined="STORAGE", container=cell, system="ECS")
        self.equipment_psets(bal, "ThermaNova", f"Préparateur {cap} L serpentin" if gas else f"Ballon {cap} L émaillé pour PAC", None, "2017-10-12" if gas else "2018-09-20", {
            "Capacité (L)": float(cap), "Type d'anode": "Magnésium", "Température de consigne (°C)": 55.0, "Appoint électrique (kW)": 0.0 if gas else 1.8,
        }, "BE")
        self.pset(bal, "Pset_TankTypeCommon", {"NominalCapacity": cap / 1000.0, "StorageType": "POTABLEWATER"})
        gs = self.cyl_equipment("IfcValve", "Groupe de sécurité ECS 7 bar", "RDC", (8.10, 1.60, 0.30), 0.03, 0.12, "Robinet", predefined="PRESSURERELIEF", container=cell, system="ECS")
        self.equipment_psets(gs, "HydroCal", "GS 3/4\" 7 bar", None, "2017-10-12" if gas else "2018-09-20", {"Pression de tarage (bar)": 7.0}, "GS")
        rag = self.cyl_equipment("IfcValve", "Robinet d'arrêt général", "RDC", (8.30, 0.45, 0.30), 0.025, 0.08, "Robinet", predefined="ISOLATING", container=cell, system="EF")
        red = self.cyl_equipment("IfcValve", "Réducteur de pression 3 bar", "RDC", (8.30, 0.80, 0.30), 0.03, 0.10, "Robinet", predefined="PRESSUREREDUCING", container=cell, system="EF")
        self.equipment_psets(red, "HydroCal", "RP 3/4\"", None, "2017-10-12" if gas else "2018-09-20", {"Pression aval réglée (bar)": 3.0}, "RP")
        n_ef = self.box_equipment("IfcPipeFitting", "Nourrice eau froide 6 départs", "RDC", (8.15, 1.45, 0.02), (0.30, 0.10, 0.08), "PER EF", predefined="JUNCTION", container=cell, system="EF")
        n_ec = self.box_equipment("IfcPipeFitting", "Nourrice eau chaude 3 départs", "RDC", (7.70, 2.12, 0.02), (0.30, 0.10, 0.08), "PER EC", predefined="JUNCTION", container=cell, system="ECS")

        # terminaux
        ev = self.box_equipment("IfcSanitaryTerminal", "Évier cuisine", "RDC", (8.50, 4.80, 0.85), (0.60, 0.80, 0.05), "Sanitaire", predefined="SINK", container=self.spaces["Cuisine"])
        wc = self.box_equipment("IfcSanitaryTerminal", "WC suspendu RDC", "RDC", (8.55, 2.80, 0.0), (0.55, 0.40, 0.40), "Sanitaire", predefined="WCSEAT", container=self.spaces["WC"])
        la = self.box_equipment("IfcSanitaryTerminal", "Lavabo salle de bains", "R1", (6.00, 2.25, 0.80), (0.45, 0.60, 0.10), "Sanitaire", predefined="WASHHANDBASIN", container=self.spaces["Salle de bains"])
        ba = self.box_equipment("IfcSanitaryTerminal", "Baignoire", "R1", (6.00, 0.30, 0.0), (1.70, 0.70, 0.55), "Sanitaire", predefined="BATH", container=self.spaces["Salle de bains"])
        ll = self.cyl_equipment("IfcValve", "Robinet machine à laver", "RDC", (8.30, 2.20, 0.90), 0.02, 0.06, "Robinet", predefined="FAUCET", container=cell)
        self.assign("EF", [ev, wc, la, ba, ll])
        self.assign("ECS", [ev, la, ba])
        self.terminals = [ev, wc, la, ba]

        # EF : arrivée PER 20, étoile PER 16
        self.run("RDC", [(8.30, 0.0, 0.05), (8.30, 1.45, 0.05)], "pipe", "20x1,9", "PER", 20, 1.9, "EF", "Arrivée", "PER", "PER EF")
        ef = [
            [(8.30, 1.50, 0.03), (7.85, 1.50, 0.03), (7.85, 1.50, 0.25)],  # ballon
            [(8.40, 1.50, 0.055), (8.40, 2.20, 0.055), (8.40, 2.20, 0.90)],  # lave-linge
            [(8.30, 1.50, 0.08), (9.00, 1.50, 0.08), (9.00, 3.00, 0.08), (9.00, 3.00, 0.20)],  # WC
            [(8.30, 1.50, 0.105), (9.00, 1.50, 0.105), (9.00, 5.20, 0.105), (9.00, 5.20, 0.60)],  # évier
        ]
        for pts in ef:
            self.run("RDC", pts, "pipe", "16x1,5", "PER", 16, 1.5, "EF", "Distribution", "PER", "PER EF")
        # montée vers la salle de bains (gaine technique dans le cellier)
        self.run("RDC", [(8.30, 1.50, 0.13), (9.00, 1.50, 0.13), (9.00, 2.00, 0.13), (9.00, 2.00, FLOOR_H + 0.05)], "pipe", "16x1,5", "PER", 16, 1.5, "EF", "Colonne SdB", "PER", "PER EF")
        self.run("R1", [(9.00, 2.00, 0.05), (9.00, 3.40, 0.05), (6.25, 3.40, 0.05), (6.25, 2.55, 0.05), (6.25, 2.55, 0.60)], "pipe", "16x1,5", "PER", 16, 1.5, "EF", "Lavabo", "PER", "PER EF")
        self.run("R1", [(9.00, 2.00, 0.075), (9.00, 0.40, 0.075), (6.20, 0.40, 0.075), (6.20, 0.65, 0.075), (6.20, 0.65, 0.60)], "pipe", "16x1,5", "PER", 16, 1.5, "EF", "Baignoire", "PER", "PER EF")
        self.assign("EF", [self.fitting("R1", (9.00, 2.00, 0.06), "pipe", "JUNCTION", "Té PER 16x1,5", 0.012, "PER EF", "16x1,5")])
        # EC
        top = 1.20 if gas else 1.45
        self.run("RDC", [(7.85, 1.85, top), (7.85, 2.15, top), (7.85, 2.15, 0.06)], "pipe", "20x1,9", "PER", 20, 1.9, "ECS", "Sortie ballon", "PER", "PER EC")
        ec = [
            [(7.95, 2.15, 0.035), (8.85, 2.15, 0.035), (8.85, 5.30, 0.035), (8.85, 5.30, 0.60)],  # évier
        ]
        for pts in ec:
            self.run("RDC", pts, "pipe", "16x1,5", "PER", 16, 1.5, "ECS", "Distribution", "PER", "PER EC")
        self.run("RDC", [(7.95, 2.15, 0.06), (8.92, 2.15, 0.06), (8.92, 2.15, FLOOR_H + 0.10)], "pipe", "16x1,5", "PER", 16, 1.5, "ECS", "Colonne SdB", "PER", "PER EC")
        self.run("R1", [(8.92, 2.15, 0.10), (8.92, 3.35, 0.10), (6.30, 3.35, 0.10), (6.30, 2.55, 0.10), (6.30, 2.55, 0.60)], "pipe", "16x1,5", "PER", 16, 1.5, "ECS", "Lavabo", "PER", "PER EC")
        self.run("R1", [(8.92, 2.15, 0.125), (8.92, 0.45, 0.125), (6.25, 0.45, 0.125), (6.25, 0.70, 0.125), (6.25, 0.70, 0.60)], "pipe", "16x1,5", "PER", 16, 1.5, "ECS", "Baignoire", "PER", "PER EC")
        self.assign("ECS", [self.fitting("R1", (8.92, 2.15, 0.11), "pipe", "JUNCTION", "Té PER 16x1,5", 0.012, "PER EC", "16x1,5")])

    # ------------------------------------------------------------ ventilation
    def build_ventilation(self):
        self.style("Galva", (0.70, 0.72, 0.75))
        self.style("Souple", (0.80, 0.80, 0.70))
        self.style("Bouche", (0.98, 0.98, 0.98))
        self.style("VMC", (0.30, 0.55, 0.75))
        self.system("VMC", "Ventilation VMC simple flux", "VENTILATION")
        combles = self.storeys["COMBLES"]
        gas = self.variant == "gaz"
        mes = "2017-10-12" if gas else "2018-09-20"
        caisson = self.box_equipment("IfcFan", "Caisson VMC simple flux hygro B", "COMBLES", (7.20, 3.20, 0.25), (0.45, 0.45, 0.25), "VMC", object_type="Caisson VMC", system="VMC")
        caisson.PredefinedType = "CENTRIFUGALFORWARDCURVED"
        self.equipment_psets(caisson, "AéroFlux", "Hygro B Basse conso T3-T7", 0.025, mes, {
            "Type": "Simple flux hygroréglable type B", "Puissance absorbée (W-Th-C)": 25.0, "Débit maximal (m³/h)": 210.0,
        }, "AF")
        # bouches d'extraction (plafond)
        bouches = [
            ("Bouche d'extraction cuisine", "Cuisine", "RDC", (8.40, 6.10), 45.0, 135.0, "125"),
            ("Bouche d'extraction WC", "WC", "RDC", (8.20, 3.20), 15.0, 30.0, "80"),
            ("Bouche d'extraction salle de bains", "Salle de bains", "R1", (8.40, 1.00), 30.0, 45.0, "80"),
        ]
        for name, room, sk, (x, y), q, qmax, dia in bouches:
            b = self.cyl_equipment("IfcAirTerminal", name, sk, (x, y, HSP - 0.04), 0.08 if dia == "125" else 0.06, 0.04, "Bouche", container=self.spaces[room], system="VMC")
            b.PredefinedType = "USERDEFINED"
            b.ObjectType = "Bouche d'extraction hygro"
            self.pset(b, "Bimys_Equipement", {"Marque": "AéroFlux", "Modèle": f"BEH {dia}", "Fonction": "Extraction", "Débit nominal (m³/h)": q, "Débit de pointe (m³/h)": qmax})
        # gaines vers combles
        top = 0.40
        self.run("RDC", [(8.40, 6.10, HSP), (8.40, 6.10, FLOOR_H + HSP + SLAB)], "duct", "Ø125", "Gaine souple isolée", 125, 0, "VMC", "Cuisine", "souple", "Souple")
        self.run("COMBLES", [(8.40, 6.10, 0.0), (8.40, 6.10, top), (7.42, 6.10, top), (7.42, 3.65, top)], "duct", "Ø125", "Gaine souple isolée", 125, 0, "VMC", "Cuisine", "souple", "Souple")
        self.run("RDC", [(8.20, 3.20, HSP), (8.20, 3.20, FLOOR_H + HSP + SLAB)], "duct", "Ø80", "Gaine souple isolée", 80, 0, "VMC", "WC", "souple", "Souple")
        self.run("COMBLES", [(8.20, 3.20, 0.0), (8.20, 3.20, top), (7.65, 3.20, top), (7.65, 3.40, top)], "duct", "Ø80", "Gaine souple isolée", 80, 0, "VMC", "WC", "souple", "Souple")
        self.run("R1", [(8.40, 1.00, HSP), (8.40, 1.00, HSP + SLAB)], "duct", "Ø80", "Gaine souple isolée", 80, 0, "VMC", "Salle de bains", "souple", "Souple")
        self.run("COMBLES", [(8.40, 1.00, 0.0), (8.40, 1.00, top), (7.42, 1.00, top), (7.42, 3.20, top)], "duct", "Ø80", "Gaine souple isolée", 80, 0, "VMC", "Salle de bains", "souple", "Souple")
        self.run("COMBLES", [(7.20, 3.42, top), (6.40, 3.42, top), (6.40, 3.42, 2.40)], "duct", "Ø125", "Conduit galva rigide", 125, 0, "VMC", "Rejet", "galva", "Galva")
        s = self.cyl_equipment("IfcAirTerminal", "Sortie de toiture VMC", "COMBLES", (6.40, 3.42, 2.40), 0.10, 0.35, "Toiture", system="VMC")
        s.PredefinedType = "USERDEFINED"
        s.ObjectType = "Chapeau de toiture"
        # entrées d'air sur menuiseries
        inlets = [
            ("Entrée d'air séjour ouest", "Séjour", "RDC", (0.42, 3.10, 2.12), 30.0),
            ("Entrée d'air séjour nord", "Séjour", "RDC", (2.25, 6.58, 2.12), 15.0),
            ("Entrée d'air chambre 1", "Chambre 1", "R1", (1.75, 6.58, 2.12), 15.0),
            ("Entrée d'air chambre 2", "Chambre 2", "R1", (1.75, 0.42, 2.12), 15.0),
            ("Entrée d'air chambre 3", "Chambre 3", "R1", (7.25, 6.58, 2.12), 15.0),
        ]
        for name, room, sk, (x, y, zz), q in inlets:
            e = self.box_equipment("IfcAirTerminal", name, sk, (x, y - 0.02, zz), (0.40, 0.04, 0.04) if y > 1 or y < 0.5 else (0.04, 0.40, 0.04), "Bouche", container=self.spaces[room], system="VMC")
            e.PredefinedType = "USERDEFINED"
            e.ObjectType = "Entrée d'air hygro"
            self.pset(e, "Bimys_Equipement", {"Marque": "AéroFlux", "Modèle": f"EA hygro {int(q)}", "Fonction": "Entrée d'air", "Débit nominal (m³/h)": q})
        self.expected["ventilation"] = {"bouches_extraction": 3, "entrees_air": 5, "qv_extraction": 90.0, "qv_entrees": 90.0}

    def write(self, path):
        self.f.write(path)


def main():
    os.makedirs(OUT_IFC, exist_ok=True)
    os.makedirs(OUT_JSON, exist_ok=True)
    for variant, fname in (("gaz", "maison_chaudiere_gaz.ifc"), ("pac", "maison_pac_air_eau.ifc")):
        b = Builder(variant)
        b.build_architecture()
        b.build_space_boundaries()
        b.build_heating()
        b.build_plumbing()
        b.build_ventilation()
        b.project.LongName = "Maison R+1 : chaudière gaz à condensation" if variant == "gaz" else "Maison R+1 : pompe à chaleur air/eau"
        path = os.path.join(OUT_IFC, fname)
        b.write(path)
        exp = b.expected
        exp["pipes"] = {k: round(v, 4) for k, v in sorted(exp["pipes"].items())}
        exp["ducts"] = {k: round(v, 4) for k, v in sorted(exp["ducts"].items())}
        with open(os.path.join(OUT_JSON, f"expected_{variant}.json"), "w", encoding="utf-8") as fh:
            json.dump(exp, fh, ensure_ascii=False, indent=2)
        print(f"OK {path} ({os.path.getsize(path) // 1024} Ko)")


if __name__ == "__main__":
    sys.exit(main())
