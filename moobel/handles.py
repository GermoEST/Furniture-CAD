"""Käepidemed: 10 stiili.

Lokaalne koordinaatsüsteem: X = piki esipaneeli laiust, Y = esipaneelist välja (y=0 on paneeli pind),
Z = üles. Nullpunkt = käepideme keskkoht paneeli pinnal.
"""
import math

import numpy as np
import trimesh

from . import geom

try:
    import manifold3d as mf
except Exception:  # pragma: no cover
    mf = None

STYLES = {
    "u_umar": "U-sang, ümar",
    "u_kandiline": "U-sang, kandiline",
    "t_latt": "T-latt (üleulatuv toru)",
    "kaar": "Kaarkäepide",
    "d_lame": "D-sang, lame lattmetall",
    "nupp_umar": "Nupp, ümar",
    "nupp_kandiline": "Nupp, kandiline",
    "profiil": "Profiilkäepide ülaservas (alumiinium)",
    "nahk": "Nahkrihm",
    "kauss": "Süvistatud kausskäepide",
}

FINISHES = {"Must": "#1f2226", "Kroom": "#d5dade", "Harjatud teras": "#a9afb5", "Messing": "#c9a43b",
            "Antratsiit": "#4a4f55", "Valge": "#f1f1f1", "Nahk pruun": "#7b4a2a", "Nahk must": "#2a2522"}

CC_SIZES = [64, 96, 128, 160, 192, 224, 256, 320, 448]

KNOBS = ("nupp_umar", "nupp_kandiline", "kauss")


def default_cc(front_w):
    ok = [c for c in CC_SIZES if c <= front_w * 0.45]
    return ok[-1] if ok else CC_SIZES[0]


def default_finish(style):
    return "Nahk pruun" if style == "nahk" else ("Harjatud teras" if style == "profiil" else "Must")


# ----------------------------------------------------------------- abifunktsioonid
def _cyl_between(p0, p1, r, seg=24):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    v = p1 - p0
    h = float(np.linalg.norm(v))
    c = mf.Manifold.cylinder(h, float(r), -1.0, seg, False)
    R = geom.rotation_between([0, 0, 1], v / h)
    return c.transform(np.hstack([R, p0.reshape(3, 1)]))


def _box(x0, x1, y0, y1, z0, z1):
    return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0], False).translate([x0, y0, z0])


def _sphere(p, r):
    return mf.Manifold.sphere(float(r), 20).translate(list(map(float, p)))


def _chain(points, r):
    parts = []
    for a, b in zip(points[:-1], points[1:]):
        parts.append(mf.Manifold.hull_points(np.vstack([
            np.asarray(_sphere(a, r).to_mesh().vert_properties)[:, :3],
            np.asarray(_sphere(b, r).to_mesh().vert_properties)[:, :3]])))
    return mf.Manifold.batch_boolean(parts, mf.OpType.Add)


def _union(ms):
    return mf.Manifold.batch_boolean(ms, mf.OpType.Add) if len(ms) > 1 else ms[0]


def _to_tri(m):
    o = m.to_mesh()
    return trimesh.Trimesh(np.asarray(o.vert_properties)[:, :3], np.asarray(o.tri_verts), process=True)


# ----------------------------------------------------------------- stiilid
def handle_mesh(style, cc=128, front_w=400, front_h=150):
    cc = float(cc)
    h2 = cc / 2
    if style == "u_umar":
        m = _union([_cyl_between([-h2, 0, 0], [-h2, 30, 0], 5), _cyl_between([h2, 0, 0], [h2, 30, 0], 5),
                    _cyl_between([-h2, 30, 0], [h2, 30, 0], 5), _sphere([-h2, 30, 0], 5), _sphere([h2, 30, 0], 5)])
    elif style == "u_kandiline":
        m = _union([_box(-h2 - 5, -h2 + 5, 0, 35, -5, 5), _box(h2 - 5, h2 + 5, 0, 35, -5, 5),
                    _box(-h2 - 5, h2 + 5, 25, 35, -5, 5)])
    elif style == "t_latt":
        m = _union([_cyl_between([-h2, 0, 0], [-h2, 30, 0], 4.5), _cyl_between([h2, 0, 0], [h2, 30, 0], 4.5),
                    _cyl_between([-h2 - 35, 30, 0], [h2 + 35, 30, 0], 6)])
    elif style == "kaar":
        n = 18
        pts = [[x, 3 + 26 * math.cos(math.pi * x / (cc + 12)), 0] for x in np.linspace(-h2, h2, n)]
        m = _union([_chain(pts, 5), _cyl_between([-h2, 0, 0], [-h2, 4, 0], 6), _cyl_between([h2, 0, 0], [h2, 4, 0], 6)])
    elif style == "d_lame":
        m = _union([_box(-h2 - 4, -h2 + 4, 0, 30, -4, 4), _box(h2 - 4, h2 + 4, 0, 30, -4, 4),
                    _box(-h2 - 12, h2 + 12, 28, 33, -10, 10)])
    elif style == "nupp_umar":
        m = _union([_cyl_between([0, 0, 0], [0, 22, 0], 7), _cyl_between([0, 18, 0], [0, 30, 0], 16),
                    _cyl_between([0, 30, 0], [0, 32, 0], 14)])
    elif style == "nupp_kandiline":
        m = _union([_box(-7, 7, 0, 20, -7, 7), _box(-15, 15, 18, 32, -15, 15)])
    elif style == "profiil":
        L = max(front_w - 4, 50)
        top = front_h / 2
        m = _union([_box(-L / 2, L / 2, 0, 2, top - 40, top), _box(-L / 2, L / 2, 0, 22, top - 2, top + 2),
                    _box(-L / 2, L / 2, 20, 22, top - 14, top)])
    elif style == "nahk":
        n = 16
        cl = []
        for x in np.linspace(-h2, h2, n):
            y = 2 + 32 * math.cos(math.pi * x / (cc + 6))
            cl.append(_box(x - 2, x + 2, y - 1.5, y + 1.5, -12.5, 12.5))
        loops = [mf.Manifold.hull_points(np.vstack([np.asarray(a.to_mesh().vert_properties)[:, :3],
                                                    np.asarray(b.to_mesh().vert_properties)[:, :3]]))
                 for a, b in zip(cl[:-1], cl[1:])]
        m = _union(loops + [_cyl_between([-h2, 0, 0], [-h2, 4, 0], 5), _cyl_between([h2, 0, 0], [h2, 4, 0], 5)])
    elif style == "kauss":
        w = max(min(cc, 120), 70)
        disc = mf.Manifold.cylinder(2.0, 1.0, -1.0, 48, False)
        disc = disc.transform(np.hstack([geom.rotation_between([0, 0, 1], [0, 1, 0]), np.zeros((3, 1))]))
        m = disc.scale([w / 2, 1.0, 20.0])
    else:
        raise ValueError(style)
    return _to_tri(m)


def describe(h):
    s = STYLES.get(h["style"], h["style"])
    if h["style"] in KNOBS:
        return f"{s} ({h['finish'].lower()})"
    if h["style"] == "profiil":
        return f"{s}, {h['front_w'] - 4:g} mm ({h['finish'].lower()})"
    return f"{s} CC {h['cc']:g} mm ({h['finish'].lower()})"
