"""Detailide ja kinnituste joonistamine pyvista plotterisse (nii ekraanil kui pildifailis)."""
import numpy as np
import trimesh

from . import geom

HOLE_COLOR = "#2b2b2b"


def _pv_cache(part):
    mesh, ok = part.display_mesh()
    key = ("pv", id(mesh))
    c = part._cache.get(key)
    if c is None:
        pvm = geom.to_pv(mesh)
        edges = pvm.extract_feature_edges(feature_angle=35, boundary_edges=True,
                                          non_manifold_edges=False, manifold_edges=False)
        hole_mesh = None
        if part.holes and not ok:
            cyl = [geom.cylinder_mesh(h.origin, h.direction, h.diameter, h.depth, 16) for h in part.holes]
            hole_mesh = geom.to_pv(trimesh.util.concatenate(cyl))
        c = (pvm, edges, hole_mesh)
        part._cache = {k: v for k, v in part._cache.items() if k[0] != "pv"}
        part._cache[key] = c
    return c


def add_part(plotter, part, color=None, opacity=1.0, offset=None, pickable=True, edges=True,
             name_prefix="part"):
    pvm, edge_mesh, hole_mesh = _pv_cache(part)
    M = part.transform()
    if offset is not None:
        M[:3, 3] += offset
    actors = []
    fin = getattr(part, "finish", "") or ""
    from . import textures as TX
    kw = {}
    spec = 0.15
    if color is None and fin in TX.WOOD or (color is None and fin == "betoon"):
        key = ("tex", id(pvm))
        tm = part._cache.get(key)
        if tm is None:
            tm = TX.apply_tcoords(pvm, part)
            part._cache[key] = tm
        pvm = tm
        kw["texture"] = TX.texture(fin)
        spec = 0.25
    elif color is None and fin in TX.SOLID:
        color, spec = TX.SOLID[fin]
    a = plotter.add_mesh(pvm, color=None if kw else (color or part.color), opacity=opacity, pickable=pickable,
                         smooth_shading=False, specular=spec, reset_camera=False,
                         name=f"{name_prefix}_{part.id}", **kw)
    a.user_matrix = M
    actors.append(a)
    if edges and edge_mesh is not None and edge_mesh.n_points:
        e = plotter.add_mesh(edge_mesh, color="#3a3a3a", line_width=1.2, pickable=False,
                             opacity=min(1.0, opacity + 0.2), reset_camera=False,
                             name=f"{name_prefix}_{part.id}_edges")
        e.user_matrix = M
        actors.append(e)
    if hole_mesh is not None:
        h = plotter.add_mesh(hole_mesh, color=HOLE_COLOR, pickable=False, reset_camera=False,
                             name=f"{name_prefix}_{part.id}_holes")
        h.user_matrix = M
        actors.append(h)
    return a, actors


def fastener_mesh(fastener):
    """Riistvara mesh'id värvide kaupa (A lokaalsetes koordinaatides)."""
    groups = {}
    for h in fastener.hardware:
        m = geom.cylinder_mesh(h["origin"], h["direction"], h["diameter"], h["length"], 18)
        groups.setdefault(h["color"], []).append(m)
    return {c: geom.to_pv(trimesh.util.concatenate(ms)) for c, ms in groups.items()}


def add_fastener(plotter, project, fastener, offset=None, highlight=False, name_prefix="fast"):
    A = project.part(fastener.a_id)
    if A is None:
        return []
    M = A.transform()
    if offset is not None:
        M[:3, 3] += offset
    out = []
    for i, (col, m) in enumerate(fastener_mesh(fastener).items()):
        a = plotter.add_mesh(m, color="#e0312b" if highlight else col, pickable=False,
                             specular=0.5, reset_camera=False,
                             name=f"{name_prefix}_{fastener.id}_{i}")
        a.user_matrix = M
        out.append(a)
    return out


def explode_offsets(project, factor):
    if factor <= 0 or not project.parts:
        return {}
    c = project.centroid()
    out = {}
    for p in project.parts:
        lo, hi = p.world_bounds()
        out[p.id] = ((lo + hi) / 2 - c) * factor
    return out


def set_iso_camera(plotter, project, zoom=1.0):
    lo, hi = project.bounds()
    c = (lo + hi) / 2
    L = float(np.linalg.norm(hi - lo)) or 500
    plotter.camera_position = [(c[0] - 0.9 * L, c[1] - 1.5 * L, c[2] + 0.9 * L), tuple(c), (0, 0, 1)]
    plotter.reset_camera()
    if zoom != 1.0:
        plotter.camera.zoom(zoom)
