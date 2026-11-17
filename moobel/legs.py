"""Mööblijalad: puidust ja metallist jalgade geomeetria (lokaalne: põhi z=0, keskel x=y=0)."""
import numpy as np
import trimesh

from . import geom

try:
    import manifold3d as mf
except Exception:  # pragma: no cover
    mf = None

METAL_COLORS = {"Must": "#2e3236", "Valge": "#e9eaec", "Kroom / hõbe": "#b9c0c7", "Antratsiit": "#4a4f55"}
WOOD_COLORS = {"Tamm": "#c9a06a", "Pöök": "#dcb48a", "Pähkel": "#7a5434", "Mänd": "#e3c48f",
               "Must": "#2e3236", "Valge": "#ecebe7"}

LEG_TYPES = {
    "puit_kandiline": dict(name="Puit – kandiline sirge", wood=True,
                           params=dict(H=720, a=60)),
    "puit_kandiline_koonus": dict(name="Puit – kandiline koonusjas", wood=True,
                                  params=dict(H=720, a=60, a_all=35)),
    "puit_umar": dict(name="Puit – ümar sirge", wood=True, params=dict(H=720, d=50)),
    "puit_umar_koonus": dict(name="Puit – ümar koonusjas (skandi)", wood=True,
                             params=dict(H=720, d=50, d_all=28)),
    "metall_umar": dict(name="Metall – ümar toru + kinnitusplaat", wood=False,
                        params=dict(H=720, d=60, plaat=90, plaat_t=6)),
    "metall_kandiline": dict(name="Metall – kandiline toru + kinnitusplaat", wood=False,
                             params=dict(H=720, a=60, plaat=90, plaat_t=6)),
    "metall_umar_3laba": dict(name="Metall – ümar toru + 3-labaline plaat (6 kruvi)", wood=False,
                              params=dict(H=710, d=60, plaat=130, plaat_t=3)),
    "metall_raam": dict(name="Metall – kandiline raamjalg (kirjutuslaua U-jalg)", wood=False,
                        params=dict(H=720, a=40, W=560)),
}

PARAM_NAMES = dict(H="Kõrgus", a="Külg (ülal)", a_all="Külg all", d="Läbimõõt (ülal)",
                   d_all="Läbimõõt all", plaat="Kinnitusplaat (külg)", plaat_t="Plaadi paksus",
                   W="Raami laius (sügavus)")


def _m(m):
    o = m.to_mesh()
    return trimesh.Trimesh(np.asarray(o.vert_properties)[:, :3], np.asarray(o.tri_verts), process=True)


def _cyl(h, r1, r2, z0=0.0):
    return mf.Manifold.cylinder(float(h), float(r1), float(r2), 64, False).translate([0, 0, z0])


def _box(sx, sy, h, z0=0.0):
    return mf.Manifold.cube([float(sx), float(sy), float(h)], False).translate([-sx / 2, -sy / 2, z0])


def _frustum_sq(h, a_bot, a_top):
    pts = []
    for (a, z) in ((a_bot, 0.0), (a_top, h)):
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts.append([sx * a / 2, sy * a / 2, z])
    return mf.Manifold.hull_points(np.asarray(pts, float))


def leg_mesh(kind, p):
    """Tagastab trimesh (kind != metall_raam)."""
    H = float(p["H"])
    if kind == "puit_kandiline":
        m = _box(p["a"], p["a"], H)
    elif kind == "puit_kandiline_koonus":
        m = _frustum_sq(H, p["a_all"], p["a"])
    elif kind == "puit_umar":
        m = _cyl(H, p["d"] / 2, p["d"] / 2)
    elif kind == "puit_umar_koonus":
        m = _cyl(H, p["d_all"] / 2, p["d"] / 2)
    elif kind in ("metall_umar", "metall_kandiline"):
        t = float(p["plaat_t"])
        body = _cyl(H - t, p["d"] / 2, p["d"] / 2) if kind == "metall_umar" else _box(p["a"], p["a"], H - t)
        foot = (_cyl(4, p["d"] / 2 - 1, p["d"] / 2 - 1) if kind == "metall_umar"
                else _box(p["a"] - 2, p["a"] - 2, 4))
        plate = _box(p["plaat"], p["plaat"], t, H - t)
        m = body + plate + foot
    elif kind == "metall_umar_3laba":
        t = float(p["plaat_t"])
        r = float(p["d"]) / 2
        body = _cyl(H - t - 8 - 14, r, r, 14)
        collar = _cyl(8, r, r + 6, H - t - 8)          # koonusjas üleminek plaadi alla
        foot = _cyl(14, r - 3, r - 3, 0) + _cyl(2.5, r + 0.5, r + 0.5, 12)   # reguleeritav jalg + rõngas
        plate = _lobe_plate(float(p["plaat"]), r, t).translate([0, 0, H - t])
        m = body + collar + foot + plate
    else:
        raise ValueError(kind)
    return _m(m)


def _lobe_geom(D, r_tube):
    """3-labalise plaadi kontuur (shapely) ja aukude kohad."""
    import math
    from shapely.geometry import Point
    from shapely.ops import unary_union
    R = D / 2
    lobe_r = max(11.0, R * 0.25)
    rc = R - lobe_r
    core = Point(0, 0).buffer(r_tube + 6, quad_segs=24)
    parts = [core]
    holes = []
    for i in range(3):
        a = math.radians(90 + 120 * i)
        cx, cy = rc * math.cos(a), rc * math.sin(a)
        from shapely.geometry import LineString
        parts.append(LineString([(0, 0), (cx, cy)]).buffer(lobe_r, quad_segs=16))
        # kaks auku labal, puutuja suunas
        tx, ty = -math.sin(a), math.cos(a)
        off = lobe_r * 0.5
        for sgn in (-1, 1):
            holes.append((cx + sgn * off * tx, cy + sgn * off * ty))
    shape = unary_union(parts).buffer(5, quad_segs=8).buffer(-5, quad_segs=8)
    return shape, holes


def _lobe_plate(D, r_tube, t):
    import trimesh as _tm
    shape, _ = _lobe_geom(D, r_tube)
    pm = _tm.creation.extrude_polygon(shape, t)
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(pm.vertices, np.float32),
                               tri_verts=np.asarray(pm.faces, np.uint32)))


def frame_outline(p):
    """Raamjala kontuur (laius W × kõrgus H) ja sisemine ava; paksus = toru külg a."""
    W, H, a = float(p["W"]), float(p["H"]), float(p["a"])
    outer = geom.rect_outline(W, H)
    inner = [[a, a], [W - a, a], [W - a, H - a], [a, H - a]]
    return outer, [inner]


def footprint(kind, p):
    """Jala ülemise osa mõõt X×Y (paigutamiseks)."""
    if kind == "metall_raam":
        return float(p["a"]), float(p["W"])
    if kind in ("metall_umar", "metall_kandiline", "metall_umar_3laba"):
        return float(p["plaat"]), float(p["plaat"])
    s = float(p.get("a", p.get("d", 50)))
    return s, s


def screw_points(kind, p, n=4):
    """Kinnituspunktid (lokaalne x, y, z – kinnituse alumine pind) jala ülaosas."""
    import math
    H = float(p["H"])
    if kind == "metall_umar_3laba":
        _, holes = _lobe_geom(float(p["plaat"]), float(p["d"]) / 2)
        z = H - float(p["plaat_t"])
        return [(x, y, z) for x, y in holes]
    if kind in ("metall_umar", "metall_kandiline"):
        e = float(p["plaat"]) / 2 - 12
        z = H - float(p["plaat_t"])
        if n == 4:
            return [(sx * e, sy * e, z) for sx in (-1, 1) for sy in (-1, 1)]
        # muu arv: ringjoonel (toru ümber), ühtlaselt
        r = max(e, float(p.get("d", p.get("a", 50))) / 2 + 8)
        r = min(r, float(p["plaat"]) / 2 - 7)
        return [(r * math.cos(2 * math.pi * i / n + math.pi / n), r * math.sin(2 * math.pi * i / n + math.pi / n), z)
                for i in range(int(n))]
    if kind == "metall_raam":
        return None   # arvutatakse raami järgi
    return [(0.0, 0.0, 0.0)]   # puitjalg: jalapolt alt keskelt


def describe(kind, p):
    t = LEG_TYPES[kind]["name"]
    if kind == "metall_raam":
        return f"{t}, {p['W']:g}×{p['H']:g} mm, toru {p['a']:g}×{p['a']:g}"
    if "d" in p:
        s = f"Ø{p['d']:g}" + (f"→Ø{p['d_all']:g}" if "d_all" in p else "")
    else:
        s = f"{p['a']:g}×{p['a']:g}" + (f"→{p['a_all']:g}" if "a_all" in p else "")
    return f"{t}, {s}, kõrgus {p['H']:g} mm"
