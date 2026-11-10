"""Formes détaillées des équipements, menuiseries et appareils des maquettes Bimys.

Chaque fonction découpe l'encombrement d'origine (boîte ou cylindre) en plusieurs volumes
colorés : un radiateur a ses panneaux nervurés et sa grille, une chaudière sa ventouse et
son bandeau de commande, une unité extérieure ses ventilateurs, etc.
Les volumes restent à l'intérieur de l'encombrement d'origine : les cotes, les positions de
raccordement et les identifiants (GlobalId) ne changent pas.
"""
import math

DET = {
    "Det sombre": (0.16, 0.18, 0.20),
    "Det serpentin": (0.30, 0.33, 0.36),
    "Det gris": (0.55, 0.57, 0.60),
    "Det clair": (0.82, 0.84, 0.86),
    "Det blanc": (0.97, 0.97, 0.97),
    "Det laiton": (0.80, 0.62, 0.22),
    "Det inox": (0.74, 0.76, 0.79),
    "Det rouge": (0.80, 0.12, 0.10),
    "Menuiserie": (0.95, 0.95, 0.95),
}


class Boite:
    """Repère local : u = grande dimension horizontale, v = petite, z = hauteur."""

    def __init__(self, b, dims, base):
        self.b = b
        self.swap = dims[1] > dims[0]
        self.L = max(dims[0], dims[1])
        self.T = min(dims[0], dims[1])
        self.H = dims[2]
        self.base = base
        self.items = []

    def _st(self, st):
        st = st or self.base
        if st in DET:
            self.b.style(st, DET[st])
        return st

    def box(self, u, v, z, du, dv, dz, st=None):
        if min(du, dv, dz) <= 1e-4:
            return
        if self.swap:
            x, y, ex, ey = v, u, dv, du
        else:
            x, y, ex, ey = u, v, du, dv
        self.items.append((self.b.box_solid(ex, ey, dz, (x, y, z)), self._st(st)))

    def cyl(self, r, length, u, v, z, axis="z", st=None):
        if r <= 1e-4 or length <= 1e-4:
            return
        ax = {"z": (0, 0, 1), "u": (0, 1, 0) if self.swap else (1, 0, 0), "v": (1, 0, 0) if self.swap else (0, 1, 0)}[axis]
        o = (v, u, z) if self.swap else (u, v, z)
        self.items.append((self.b.cyl_solid(r, length, o, ax), self._st(st)))


class Rond:
    """Équipement cylindrique d'axe vertical : origine au centre de la base."""

    def __init__(self, b, r, h, base):
        self.b = b
        self.r = r
        self.h = h
        self.base = base
        self.items = []

    def _st(self, st):
        st = st or self.base
        if st in DET:
            self.b.style(st, DET[st])
        return st

    def disc(self, k, z0, z1, st=None):
        """cylindre de rayon k × r entre les hauteurs relatives z0 et z1"""
        if z1 - z0 <= 1e-4:
            return
        self.items.append((self.b.cyl_solid(self.r * k, (z1 - z0) * self.h, (0, 0, z0 * self.h)), self._st(st)))

    def box(self, x0, x1, y0, y1, z0, z1, st=None):
        r, h = self.r, self.h
        self.items.append((self.b.box_solid((x1 - x0) * r, (y1 - y0) * r, (z1 - z0) * h, (x0 * r, y0 * r, z0 * h)), self._st(st)))


# ---------------------------------------------------------------- émetteurs
def radiateur(s):
    L, T, H = s.L, s.T, s.H
    e = min(0.004, T * 0.08)  # profondeur des nervures
    pas = 0.04
    n = max(3, int((L - 0.03) / pas))
    u0 = (L - n * pas) / 2 + (pas - 0.022) / 2
    if T >= 0.05:
        tp = min(0.02, T * 0.22)
        s.box(0, e, 0, L, tp, H)
        s.box(0, T - e - tp, 0, L, tp, H)
        # ailettes entre les panneaux, grille supérieure et joues
        s.box(0.03, e + tp, 0.05, L - 0.06, T - 2 * (e + tp), H - 0.09, "Det serpentin")
        s.box(0.012, e + tp, H - 0.014, L - 0.024, T - 2 * (e + tp), 0.014, "Det gris")
        s.box(0, e, 0.02, 0.012, T - 2 * e, H - 0.02)
        s.box(L - 0.012, e, 0.02, 0.012, T - 2 * e, H - 0.02)
    else:
        s.box(0, e, 0, L, T - 2 * e, H)
    for i in range(n):
        u = u0 + i * pas
        s.box(u, 0, 0.03, 0.022, e, H - 0.06)
        s.box(u, T - e, 0.03, 0.022, e, H - 0.06)


def convecteur(s):
    L, T, H = s.L, s.T, s.H
    e = min(0.004, T * 0.08)
    s.box(0, e, 0, L, T - 2 * e, H)
    s.box(0.03, 0, H - 0.05, L - 0.06, T, 0.03, "Det sombre")
    s.box(0.03, 0, 0.02, L - 0.06, T, 0.02, "Det sombre")
    s.box(L - 0.10, 0, H * 0.45, 0.07, T, 0.05, "Det gris")


def seche_serviettes(s):
    L, T, H = s.L, s.T, s.H
    rv = min(0.018, T * 0.4, L * 0.06)
    rh = rv * 0.6
    for u in (rv, L - rv):
        s.cyl(rv, H, u, T / 2, 0, "z")
    z = 0.06
    k = 0
    while z < H - 0.04:
        s.cyl(rh, L - 2 * rv, rv, T / 2, z, "u")
        k += 1
        z += 0.045 if k % 6 else 0.13


# ---------------------------------------------------------------- générateurs
def chaudiere(s, ventouse=True):
    L, T, H = s.L, s.T, s.H
    e = min(0.008, T * 0.02)
    m = min(L, T)
    if H < 1.0:  # murale
        zb = 0.08 * H
        s.box(e, e, zb, L - 2 * e, T - 2 * e, 0.84 * H)
        s.box(0, 0, zb, L, T, 0.12 * H, "Det sombre")
        s.box(0, 0, zb + 0.125 * H, L, T, 0.008, "Det gris")
        n = 5 if ventouse else 4
        for i in range(n):
            s.cyl(min(0.012, m * 0.035), zb, L * (0.18 + 0.64 * i / (n - 1)), T / 2, 0, "z", "Det laiton")
        if ventouse:
            s.cyl(m * 0.13, 0.08 * H, L / 2, T / 2, 0.92 * H, "z", "Det clair")
            s.cyl(m * 0.08, 0.08 * H - 0.002, L / 2, T / 2, 0.92 * H + 0.002, "z", "Det sombre")
        else:
            s.box(e * 3, e * 3, 0.92 * H, L - 6 * e, T - 6 * e, 0.08 * H, "Det gris")
    else:  # au sol
        s.box(0, 0, 0, L, T, 0.05 * H, "Det sombre")
        s.box(e, e, 0.05 * H, L - 2 * e, T - 2 * e, 0.89 * H)
        s.box(0, 0, 0.70 * H, L, T, 0.09 * H, "Det sombre")
        s.box(0, 0, 0.795 * H, L, T, 0.008 * H, "Det gris")
        s.box(0, 0, 0.30 * H, L, T, 0.006 * H, "Det gris")
        s.box(3 * e, 3 * e, 0.94 * H, L - 6 * e, T - 6 * e, 0.025 * H, "Det gris")
        if ventouse:
            s.cyl(m * 0.14, 0.06 * H, L / 2, T / 2, 0.94 * H, "z", "Det clair")


def unite_exterieure(s):
    """Groupe à soufflage horizontal (PAC air/eau individuelle)."""
    L, T, H = s.L, s.T, s.H
    e = min(0.014, T * 0.04)
    zp = min(0.05, H * 0.07)
    for u in (0.10 * L, 0.90 * L - 0.08):
        s.box(u, 0, 0, 0.08, T, zp, "Det sombre")
    s.box(0, e, zp, L, T - 2 * e, H - zp)
    hc = H - zp
    nf = 2 if hc > 1.15 else 1
    r = min(0.60 * L, hc / nf) * 0.42
    for i in range(nf):
        zc = zp + hc * (i + 0.5) / nf
        uc = 0.37 * L
        for v0, sens in ((0.0, 1), (T - e, -1)):
            s.cyl(r, e * 0.7, uc, v0 + (0.3 * e if sens == 1 else 0), zc, "v", "Det sombre")
            s.cyl(r * 0.26, e, uc, v0, zc, "v", "Det gris")
    for v0 in (0.0, T - e * 0.5):
        s.box(0.735 * L, v0, zp + 0.03, 0.006, e * 0.5, hc - 0.06, "Det sombre")
        for k in range(5):
            s.box(0.78 * L, v0, zp + hc * (0.2 + 0.13 * k), 0.17 * L, e * 0.5, 0.012, "Det sombre")


def groupe_toiture(s, serpentin=1.0):
    """Groupe à soufflage vertical : DRV, groupe froid, rooftop."""
    L, T, H = s.L, s.T, s.H
    e = min(0.03, T * 0.02)
    s.box(0, 0, 0, L, T, 0.05 * H, "Det sombre")
    s.box(e, e, 0.05 * H, L - 2 * e, T - 2 * e, 0.91 * H)
    n = max(1, round(L * serpentin / T))
    lu = L * serpentin / n
    r = min(T, lu) * 0.40
    for i in range(n):
        uc = lu * (i + 0.5)
        s.cyl(r, 0.03 * H, uc, T / 2, 0.96 * H, "z", "Det sombre")
        s.cyl(r * 0.28, 0.04 * H, uc, T / 2, 0.96 * H, "z", "Det gris")
        for v0 in (0.0, T - e):
            s.box(lu * i + 0.06 * lu, v0, 0.34 * H, lu * 0.88, e, 0.56 * H, "Det serpentin")
    if serpentin < 1.0:  # partie traitement d'air : portes de visite
        u0 = L * serpentin
        nd = max(1, round((L - u0) / 0.9))
        ld = (L - u0) / nd
        for i in range(nd):
            for v0 in (0.0, T - e):
                s.box(u0 + ld * i + 0.04 * ld, v0, 0.12 * H, ld * 0.92, e, 0.78 * H, "Det clair")
                s.box(u0 + ld * (i + 0.82), v0, 0.48 * H, 0.03, e, 0.10 * H, "Det sombre")
    for v0 in (0.0, T - e):
        s.box(0.04 * L, v0, 0.10 * H, 0.92 * L, e, 0.012 * H, "Det gris")


def caisson(s):
    """Centrale de traitement d'air, VMC double flux, caisson d'extraction."""
    L, T, H = s.L, s.T, s.H
    e = max(0.004, min(0.02, T * 0.02))
    if L < 0.7:  # petit caisson de VMC individuelle
        s.box(e, e, 0, L - 2 * e, T - 2 * e, H * 0.9)
        s.box(0, 0, H * 0.30, L, T, H * 0.10, "Det sombre")
        s.cyl(min(L, T) * 0.30, H * 0.10, L / 2, T / 2, H * 0.9, "z", "Det sombre")
        return
    zb = 0.05 * H
    s.box(0, 0, 0, L, T, zb, "Det sombre")
    s.box(e, e, zb, L - 2 * e, T - 2 * e, H - zb - e)
    s.box(0, 0, H - e, L, T, e, "Det gris")
    n = max(2, round(L / 1.0))
    wp = min(0.05, L * 0.02)
    for i in range(n + 1):
        u = min(L - wp, max(0.0, L * i / n - wp / 2))
        for v0 in (0.0, T - e):
            s.box(u, v0, zb, wp, e, H - zb - e, "Det gris")
    for i in range(n):
        for v0 in (0.0, T - e):
            s.box(L * (i + 0.80) / n, v0, 0.46 * H, wp * 0.6, e, 0.10 * H, "Det sombre")
    for v0 in (0.0, T - e):
        s.box(0, v0, zb, L, e, 0.012 * H, "Det gris")


def ventilo(s):
    L, T, H = s.L, s.T, s.H
    e = min(0.006, H * 0.03)
    s.box(0, 0, e, L, T, H - e, "Det inox")
    s.box(0.24 * L, 0.06 * T, 0, 0.70 * L, 0.88 * T, e, "Det sombre")
    s.box(0, 0, e, 0.20 * L, T, H - e, "Det gris")
    s.box(0.20 * L, 0, e, 0.006, T, H - e, "Det sombre")


def cassette(s):
    L, T, H = s.L, s.T, s.H
    zf = min(0.04, H * 0.15)
    m = 0.05 * T
    s.box(m, m, zf, L - 2 * m, T - 2 * m, H - zf, "Det inox")
    s.box(0, 0, 0.006, L, T, zf - 0.006, "Det blanc")
    s.box(0.24 * L, 0.24 * T, 0, 0.52 * L, 0.52 * T, zf, "Det gris")
    b = 0.05
    s.box(0.14 * L, b * T, 0, 0.72 * L, 0.05 * T, 0.008, "Det sombre")
    s.box(0.14 * L, (1 - b - 0.05) * T, 0, 0.72 * L, 0.05 * T, 0.008, "Det sombre")
    s.box(b * L, 0.14 * T, 0, 0.05 * L, 0.72 * T, 0.008, "Det sombre")
    s.box((1 - b - 0.05) * L, 0.14 * T, 0, 0.05 * L, 0.72 * T, 0.008, "Det sombre")


# ---------------------------------------------------------------- sanitaires
def bac(s, rebord, fond, bonde_u, st):
    """cuve creuse : quatre rebords et un fond bas"""
    L, T, H = s.L, s.T, s.H
    s.box(0, 0, 0, L, rebord, H, st)
    s.box(0, T - rebord, 0, L, rebord, H, st)
    s.box(0, rebord, 0, rebord, T - 2 * rebord, H, st)
    s.box(L - rebord, rebord, 0, rebord, T - 2 * rebord, H, st)
    s.box(rebord, rebord, 0, L - 2 * rebord, T - 2 * rebord, fond * H, st)
    s.cyl(min(0.03, T * 0.06), 0.004, bonde_u * L, T / 2, fond * H, "z", "Det gris")


def evier(s):
    L, T, H = s.L, s.T, s.H
    r = 0.03
    uc = 0.56 * L if L > T * 1.2 else L
    st = "Det inox"
    s.box(0, 0, 0, uc, r, H, st)
    s.box(0, T - r, 0, uc, r, H, st)
    s.box(0, r, 0, r, T - 2 * r, H, st)
    if uc < L:
        s.box(uc - r, r, 0, r, T - 2 * r, H, st)
        s.box(uc, 0, 0.45 * H, L - uc, T, 0.45 * H, st)
        for k in range(5):
            s.box(uc + 0.03, T * (0.16 + 0.17 * k), 0.9 * H, L - uc - 0.06, 0.012, 0.1 * H, st)
    else:
        s.box(L - r, r, 0, r, T - 2 * r, H, st)
    s.box(r, r, 0, uc - 2 * r, T - 2 * r, 0.25 * H, st)
    s.cyl(0.028, 0.004, uc / 2, T / 2, 0.25 * H, "z", "Det sombre")


def wc(s):
    L, T, H = s.L, s.T, s.H
    r = T / 2
    def ovale(k, z0, z1, st):
        rr = r * k
        s.cyl(rr, z1 - z0, r, r, z0, "z", st)
        s.cyl(rr, z1 - z0, L - r, r, z0, "z", st)
        s.box(r, r - rr, z0, L - 2 * r, 2 * rr, z1 - z0, st)
    ovale(0.55, 0, 0.50 * H, "Det blanc")
    ovale(0.94, 0.50 * H, 0.90 * H, "Det blanc")
    ovale(1.0, 0.90 * H, 0.95 * H, "Det clair")
    ovale(0.90, 0.95 * H, H, "Det blanc")


# ---------------------------------------------------------------- divers
def boitier(s, ecran="Det sombre"):
    L, T, H = s.L, s.T, s.H
    e = T * 0.12
    s.box(0, e, 0, L, T - 2 * e, H, "Det blanc")
    s.box(0.2 * L, 0, 0.42 * H, 0.6 * L, T, 0.38 * H, ecran)


def compteur(s):
    L, T, H = s.L, s.T, s.H
    rb = min(T, H) * 0.24
    s.cyl(rb, L, 0, T / 2, rb, "u", "Det laiton")
    for u in (0.0, L - 0.012):
        s.cyl(min(rb * 1.5, T / 2), 0.012, u, T / 2, rb, "u", "Det laiton")
    rc = min(T / 2, L / 3.2)
    s.cyl(rc, H - rb - 0.012, L / 2, T / 2, rb, "z", "Det sombre")
    s.cyl(rc * 0.86, 0.012, L / 2, T / 2, H - 0.012, "z", "Det blanc")


def collecteur(s):
    L, T, H = s.L, s.T, s.H
    n = max(2, round(L / 0.07))
    if H >= 0.12:
        rb = min(T * 0.32, H * 0.14)
        for zc, st in ((0.72 * H, "Det rouge"), (0.28 * H, "Det inox")):
            s.cyl(rb, L, 0, T / 2, zc, "u", "Det laiton")
            for i in range(n):
                u = L * (i + 0.5) / n
                if zc > H / 2:
                    s.cyl(rb * 0.7, H - zc - rb * 0.5, u, T / 2, zc + rb * 0.5, "z", st)
                else:
                    s.cyl(rb * 0.55, zc - rb * 0.5, u, T / 2, 0, "z", st)
        for u in (0.10 * L, 0.90 * L - 0.012):
            s.box(u, T * 0.2, 0.06 * H, 0.012, T * 0.6, 0.88 * H, "Det gris")
    else:
        rb = min(T, H) * 0.36
        s.cyl(rb, L, 0, T / 2, H / 2, "u")
        for i in range(n):
            s.cyl(rb * 0.55, T / 2 - 0.002, L * (i + 0.5) / n, 0, H / 2, "v", "Det laiton")


def entree_air(s):
    L, T, H = s.L, s.T, s.H
    e = min(0.004, T * 0.1, H * 0.1)
    s.box(0, e, e, L, T - 2 * e, H - 2 * e, "Det blanc")
    s.box(0.08 * L, 0, 0.3 * H, 0.84 * L, T, 0.4 * H, "Det sombre")


# ---------------------------------------------------------------- aiguillage
def detail_boite(b, cls, predefined, name, dims, base):
    """Renvoie [(solide, style)] ou None pour garder la boîte d'origine."""
    n = name.lower()
    if min(dims) < 0.015 or n.startswith("plancher chauffant"):
        return None
    s = Boite(b, dims, base)
    if cls == "IfcSpaceHeater":
        if "sèche" in n or "seche" in n:
            seche_serviettes(s)
        elif predefined == "CONVECTOR":
            convecteur(s)
        else:
            radiateur(s)
    elif cls == "IfcBoiler":
        chaudiere(s, True)
    elif cls == "IfcChiller":
        groupe_toiture(s)
    elif cls == "IfcUnitaryEquipment":
        if "module hydraulique" in n:
            chaudiere(s, False)
        elif "rooftop" in n:
            groupe_toiture(s, 0.5)
        elif "drv" in n and "cassette" not in n:
            groupe_toiture(s)
        elif "cassette" in n:
            cassette(s)
        elif "ventilo" in n:
            ventilo(s)
        elif "pac" in n or "extérieure" in n:
            unite_exterieure(s)
        else:
            return None
    elif cls in ("IfcAirToAirHeatRecovery", "IfcFan"):
        caisson(s)
    elif cls == "IfcSanitaryTerminal":
        if predefined == "SINK":
            evier(s)
        elif predefined == "WASHHANDBASIN":
            bac(s, 0.04, 0.3, 0.5, "Det blanc")
        elif predefined == "BATH":
            bac(s, 0.06, 0.3, 0.85, "Det blanc")
        elif predefined == "SHOWER":
            bac(s, 0.04, 0.45, 0.5, "Det blanc")
        elif predefined == "WCSEAT":
            wc(s)
        else:
            return None
    elif cls == "IfcUnitaryControlElement":
        boitier(s)
    elif cls == "IfcSensor":
        boitier(s, "Det gris")
    elif cls == "IfcFlowMeter":
        compteur(s)
    elif cls == "IfcPipeFitting" and predefined == "JUNCTION":
        collecteur(s)
    elif cls == "IfcAirTerminal":
        entree_air(s)
    else:
        return None
    return s.items or None


def detail_cylindre(b, cls, predefined, name, r, h, base):
    n = name.lower()
    s = Rond(b, r, h, base)
    if cls == "IfcPump":
        s.disc(1.0, 0, 0.06, "Det gris")
        s.disc(0.80, 0.06, 0.44)
        s.disc(1.0, 0.44, 0.50, "Det gris")
        s.disc(0.72, 0.50, 0.92, "Det sombre")
        s.disc(0.50, 0.92, 1.0, "Det gris")
        s.box(0.45, 0.70, -0.3, 0.3, 0.56, 0.86, "Det gris")
    elif cls == "IfcTank" and predefined == "EXPANSION":
        s.disc(0.55, 0, 0.05)
        s.disc(0.86, 0.05, 0.13)
        s.disc(0.97, 0.13, 0.87)
        s.disc(1.0, 0.485, 0.515, "Det gris")
        s.disc(0.86, 0.87, 0.95)
        s.disc(0.55, 0.95, 1.0)
        s.disc(0.16, 0.0, 0.02, "Det laiton")
    elif cls == "IfcTank":
        thermo = "thermodynamique" in n
        s.disc(0.80, 0, 0.03, "Det sombre")
        s.disc(0.88, 0.03, 0.08)
        s.disc(0.98, 0.08, 0.70 if thermo else 0.93)
        s.disc(1.0, 0.16, 0.17, "Det gris")
        if thermo:
            s.disc(1.0, 0.70, 0.715, "Det sombre")
            s.disc(0.98, 0.715, 0.95, "Det gris")
            s.disc(0.70, 0.95, 1.0, "Det sombre")
        else:
            s.disc(1.0, 0.84, 0.85, "Det gris")
            s.disc(0.88, 0.93, 0.975)
            s.disc(0.60, 0.975, 1.0)
    elif cls == "IfcValve":
        if "thermostatique" in n:
            s.disc(0.62, 0, 0.40, "Det laiton")
            s.disc(0.80, 0.40, 0.47, "Det gris")
            s.disc(1.0, 0.47, 1.0, "Det blanc")
        elif predefined in ("PRESSURERELIEF", "SAFETYCUTOFF"):
            s.disc(0.70, 0, 0.55, "Det laiton")
            s.disc(1.0, 0.55, 0.92, "Det rouge")
            s.disc(0.55, 0.92, 1.0, "Det sombre")
        elif predefined == "PRESSUREREDUCING":
            s.disc(0.70, 0, 0.50, "Det laiton")
            s.disc(0.95, 0.50, 0.90, "Det laiton")
            s.disc(0.50, 0.90, 1.0, "Det sombre")
        elif predefined == "AIRRELEASE":
            s.disc(0.55, 0, 0.25, "Det laiton")
            s.disc(1.0, 0.25, 0.88, "Det laiton")
            s.disc(0.45, 0.88, 1.0, "Det sombre")
        elif "voies" in n:
            s.disc(0.65, 0, 0.45, "Det laiton")
            s.box(-0.66, 0.66, -0.66, 0.66, 0.45, 1.0, "Det gris")
        else:
            s.disc(0.65, 0, 0.55, "Det laiton")
            s.disc(0.28, 0.55, 0.80, "Det gris")
            s.box(-0.9, 0.9, -0.24, 0.24, 0.80, 1.0, "Det rouge")
    elif cls == "IfcFilter":
        s.disc(0.88, 0, 0.72, "Det sombre")
        s.disc(1.0, 0.72, 0.84, "Det laiton")
        s.disc(0.55, 0.84, 1.0, "Det laiton")
    elif cls == "IfcAirTerminal":
        if "toiture" in n:
            s.disc(0.60, 0, 0.70)
            s.disc(1.0, 0.70, 0.86, "Det sombre")
            s.disc(0.50, 0.86, 1.0, "Det sombre")
        else:
            s.disc(1.0, 0.5, 1.0, "Det blanc")
            s.disc(0.74, 0.2, 0.5, "Det gris")
            s.disc(0.52, 0.0, 0.2, "Det blanc")
    else:
        return None
    return s.items or None


def detail_menuiserie(b, kind, dims):
    """Fenêtre : dormant, vitrage et meneaux. Porte : huisserie, vantail et poignées."""
    b.style("Menuiserie", DET["Menuiserie"])
    s = Boite(b, dims, "Porte")
    L, T, H = s.L, s.T, s.H
    if kind == "W":
        w = min(0.055, L * 0.12, H * 0.12)
        tg = min(0.024, T * 0.4)
        s.box(0, 0, 0, w, T, H, "Menuiserie")
        s.box(L - w, 0, 0, w, T, H, "Menuiserie")
        s.box(w, 0, 0, L - 2 * w, T, w, "Menuiserie")
        s.box(w, 0, H - w, L - 2 * w, T, w, "Menuiserie")
        s.box(w, (T - tg) / 2, w, L - 2 * w, tg, H - 2 * w, "Vitrage")
        nm = 0 if L <= 1.25 else 1 if L <= 2.3 else max(2, round(L / 1.1) - 1)
        for i in range(nm):
            u = w + (L - 2 * w) * (i + 1) / (nm + 1) - w * 0.5
            s.box(u, T * 0.1, w, w, T * 0.8, H - 2 * w, "Menuiserie")
        if H > 1.9:  # porte-fenêtre : traverse basse
            s.box(w, T * 0.1, w, L - 2 * w, T * 0.8, 0.07, "Menuiserie")
    else:
        w = min(0.045, L * 0.08)
        s.box(0, 0, 0, w, T, H, "Menuiserie")
        s.box(L - w, 0, 0, w, T, H, "Menuiserie")
        s.box(w, 0, H - w, L - 2 * w, T, w, "Menuiserie")
        tv = min(0.04, T * 0.5)
        v0 = (T - tv) / 2
        s.box(w, v0, 0, L - 2 * w, tv, H - w, "Porte")
        zp = min(1.02, H * 0.5)
        if L > 1.35:  # deux vantaux
            s.box(L / 2 - 0.004, v0 - 0.002, 0, 0.008, tv + 0.004, H - w, "Det sombre")
            us = (L / 2 - 0.16, L / 2 + 0.05)
        else:
            us = (L - w - 0.16,)
        for u in us:
            s.box(u, 0, zp, 0.11, v0, 0.022, "Det gris")
            s.box(u, v0 + tv, zp, 0.11, T - v0 - tv, 0.022, "Det gris")
    return s.items
