"""Geomeetria abifunktsioonid: pöörded, plaadi mesh, aukude lõikamine."""
import math
import numpy as np
import trimesh
from shapely.geometry import Polygon, MultiPolygon, box

try:
    import manifold3d as mf
    HAS_MANIFOLD = True
except Exception:  # pragma: no cover
    mf = None
    HAS_MANIFOLD = False


# ---------------------------------------------------------------- pöörded
def rot_x(deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], float)


def rot_y(deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], float)


def rot_z(deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], float)


def euler_to_matrix(rx, ry, rz):
    """Pööre: kõigepealt X, siis Y, siis Z (maailma telgede ümber)."""
    return rot_z(rz) @ rot_y(ry) @ rot_x(rx)


def matrix_to_euler(R):
    R = np.asarray(R, float)
    sy = max(-1.0, min(1.0, -R[2, 0]))
    ry = math.asin(sy)
    if abs(math.cos(ry)) > 1e-6:
        rx = math.atan2(R[2, 1], R[2, 2])
        rz = math.atan2(R[1, 0], R[0, 0])
    else:
        rx = math.atan2(-R[1, 2], R[1, 1])
        rz = 0.0
    out = []
    for v in (rx, ry, rz):
        d = math.degrees(v)
        if abs(d) < 1e-7:
            d = 0.0
        out.append(round(d, 3))
    return out


def axis_angle(axis, deg):
    axis = np.asarray(axis, float)
    n = np.linalg.norm(axis)
    if n < 1e-12:
        return np.eye(3)
    x, y, z = axis / n
    a = math.radians(deg); c, s = math.cos(a), math.sin(a); C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def rotation_between(a, b):
    """Väikseim pööre, mis viib ühikvektori a vektoriks b."""
    a, b = unit(a), unit(b)
    c = float(np.dot(a, b))
    if c > 1 - 1e-9:
        return np.eye(3)
    if c < -1 + 1e-9:
        # 180 kraadi ümber a-ga risti oleva telje
        helper = np.eye(3)[int(np.argmin(np.abs(a)))]
        ax = unit(np.cross(a, helper))
        return axis_angle(ax, 180)
    ax = np.cross(a, b)
    ang = math.degrees(math.atan2(np.linalg.norm(ax), c))
    return axis_angle(ax, ang)


def clean_rotation(R):
    """Ümardab peaaegu täisarvulised elemendid (90° pöörded jäävad puhtaks)."""
    R = np.asarray(R, float).copy()
    R[np.abs(R) < 1e-9] = 0.0
    for v in (1.0, -1.0):
        R[np.abs(R - v) < 1e-9] = v
    u, _, vt = np.linalg.svd(R)
    return u @ vt


def make_transform(R, t):
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = t
    return M


def apply_point(M, p):
    p = np.asarray(p, float)
    return (M[:3, :3] @ p) + M[:3, 3]


def apply_dir(M, d):
    return M[:3, :3] @ np.asarray(d, float)


# ---------------------------------------------------------------- 2D kujud
def rect_outline(w, h, r=0.0):
    if r and r > 0:
        r = min(r, w / 2 - 0.01, h / 2 - 0.01)
        poly = box(r, r, w - r, h - r).buffer(r, quad_segs=8)
    else:
        poly = box(0, 0, w, h)
    return [list(map(float, c)) for c in list(poly.exterior.coords)[:-1]]


def make_polygon(outline, inner=None):
    holes = [h for h in (inner or []) if len(h) >= 3]
    poly = Polygon(outline, holes)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly


def plate_mesh(outline, inner, thickness):
    poly = make_polygon(outline, inner)
    m = trimesh.creation.extrude_polygon(poly, float(thickness))
    m.merge_vertices()
    return m


# ---------------------------------------------------------------- augud
def _frame_from_dir(d):
    """Pöördemaatriks, mis viib Z-telje suunda d."""
    return rotation_between([0, 0, 1], d)


def cylinder_mesh(origin, direction, diameter, length, sections=20):
    d = unit(direction)
    cyl = trimesh.creation.cylinder(radius=diameter / 2.0, height=length, sections=sections)
    cyl.apply_translation([0, 0, length / 2.0])
    M = make_transform(_frame_from_dir(d), origin)
    cyl.apply_transform(M)
    return cyl


def _to_manifold(mesh):
    m = mf.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                tri_verts=np.asarray(mesh.faces, np.uint32))
    return mf.Manifold(m)


def subtract_holes(mesh, holes):
    """holes: list of (origin, direction, diameter, depth). Tagastab (mesh, ok)."""
    if not holes:
        return mesh, True
    if not HAS_MANIFOLD:
        return mesh, False
    try:
        body = _to_manifold(mesh)
        if body.is_empty():
            return mesh, False
        cutters = []
        for (o, d, dia, depth) in holes:
            d = unit(d)
            o = np.asarray(o, float) - d * 0.3
            c = mf.Manifold.cylinder(float(depth) + 0.6, float(dia) / 2.0, -1.0, 24, False)
            R = _frame_from_dir(d)
            m34 = np.hstack([R, o.reshape(3, 1)])
            cutters.append(c.transform(m34))
        cut = mf.Manifold.batch_boolean(cutters, mf.OpType.Add) if len(cutters) > 1 else cutters[0]
        res = body - cut
        out = res.to_mesh()
        v = np.asarray(out.vert_properties)[:, :3]
        f = np.asarray(out.tri_verts)
        if len(f) == 0:
            return mesh, False
        return trimesh.Trimesh(v, f, process=False), True
    except Exception:
        return mesh, False


def ray_hits(mesh, origin, direction):
    """Kõik kiire ja meshi lõikumiskaugused (Möller–Trumbore, ainult numpy)."""
    o = np.asarray(origin, float)
    d = unit(direction)
    tri = np.asarray(mesh.triangles, float)
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    s = o - v0
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    m = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 1e-9)
    return np.sort(t[m])


def to_pv(mesh):
    import pyvista as pv
    f = np.asarray(mesh.faces, np.int64)
    faces = np.hstack([np.full((len(f), 1), 3, np.int64), f]).ravel()
    return pv.PolyData(np.asarray(mesh.vertices, float), faces)
