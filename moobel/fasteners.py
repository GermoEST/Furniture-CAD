"""Mööblikinnituste tüübid ja nende aukude/riistvara arvutamine.

Kõik kinnitused paigutatakse nii: kasutaja klikib detaili A välispinnale
(kohas, kust kinnitus läheb läbi). Kinnituse telg d läheb pinnast sisse,
läbib A paksuse ja siseneb detaili B (tavaliselt B serva).
"""
import numpy as np
from . import geom

STEEL = "#8c9399"
DARK = "#3b3f44"
BRASS = "#c9a43b"
ZINC = "#b9bec4"
WOOD = "#c8a06a"

FASTENER_TYPES = {
    "ristmutter": dict(
        name="Mööblipolt + ristmutter (pikk vastasmutter)",
        short="mööblipolt M6 + ristmutter",
        joint="edge",
        help="Polt läheb läbi A, ristmutter (Ø10 silinder) pannakse B külje sisse risti poldiga.",
        params={"polt_d": 6.0, "polt_L": 70.0, "pea_d": 13.0, "mutri_d": 10.0}),
    "minifix": dict(
        name="Minifix 15 (veerandpöörde ekstsentrik)",
        short="Minifix 15 ekstsentrik + polt",
        joint="edge",
        help="Ekstsentrik Ø15 detaili B siseküljel, polt keeratakse A sisepinda. Väljast ei paista.",
        params={"kaugus": 24.0, "eks_d": 15.0, "eks_sugavus": 12.5, "polt_ava_d": 5.0,
                "polt_ava_sugavus": 11.0, "serva_ava_d": 8.0}),
    "konfirmaat": dict(
        name="Konfirmaat (euro-kruvi) 7×50",
        short="konfirmaat 7×50",
        joint="any",
        help="Läbiv ava Ø7 detailis A, juhtava Ø5 detailis B.",
        params={"d": 7.0, "L": 50.0, "juhtava_d": 5.0, "pea_d": 10.0}),
    "tuubel": dict(
        name="Puittüübel 8×35",
        short="tüübel 8×35",
        joint="any",
        help="Peidetud tüübel. A sisse 12 mm, ülejäänu B sisse.",
        params={"d": 8.0, "L": 35.0, "sugavus_A": 12.0}),
    "kruvi": dict(
        name="Puidukruvi 4×40",
        short="puidukruvi 4×40",
        joint="any",
        help="Läbiv ava A-s, eelpuuritud juhtava B-s.",
        params={"d": 4.0, "L": 40.0}),
    "jalapolt": dict(
        name="Jalapolt M8 + keermesmuhv (puitjalg)",
        short="jalapolt M8 + keermesmuhv",
        joint="any",
        help="Kahepoolne polt: puidukeere jala sisse, M8 keere plaati paigaldatud keermesmuhvi. "
             "Kliki jala alumisele pinnale.",
        params={"d": 8.0, "sugavus_jalg": 35.0, "jala_ava_d": 6.0, "muhv_d": 12.0, "muhv_L": 13.0}),
    "hing": dict(
        name="Peitehing 35 mm (kausshing)", short="peitehing 35 mm", joint="any",
        help="Lisatakse uste juures automaatselt.", params={"cup": 35.0}),
    "labipolt": dict(
        name="Läbiv mööblipolt + kuppelmutter",
        short="mööblipolt M6 + kuppelmutter",
        joint="face",
        help="Kahe pinnapidi kokku pandud detaili läbiv polt (nt jalg raami külge).",
        params={"d": 6.0, "pea_d": 13.0, "mutri_d": 12.0}),
}


def hw(origin, direction, diameter, length, color):
    return dict(origin=[float(x) for x in origin], direction=[float(x) for x in geom.unit(direction)],
                diameter=float(diameter), length=float(length), color=color)


class FastenerError(Exception):
    pass


def analyse_joint(project, part_a, P, n_out):
    """Leiab detaili B ja kinnituse telje. P = klikipunkt A pinnal, n_out = pinna välisnormaal.
    Tagastab dict või tõstab FastenerError."""
    d = -geom.unit(n_out)
    tA = None
    # A paksus telje suunas: kiir A sees
    ma = part_a.world_body_mesh()
    dist = [float(x) + 0.05 for x in geom.ray_hits(ma, P + d * 0.05, d) if x > 0.01]
    if dist:
        tA = dist[0]
    if tA is None:
        raise FastenerError("Ei leidnud detaili paksust selles kohas.")
    best = None
    for p in project.parts:
        if p.id == part_a.id:
            continue
        m = p.world_body_mesh()
        for t in geom.ray_hits(m, P - d * 0.5, d):
            t = float(t) - 0.5
            if t > -0.2 and (best is None or t < best[0]):
                best = (t, p, P + d * t)
    if best is None or best[0] > tA + 1.5:
        raise FastenerError("Selle koha taga pole teist detaili (B). Kliki kohale, kus "
                            "teine detail on vastu selle detaili sisepinda.")
    t, part_b, E = best
    zB = part_b.thickness_axis_world()
    cos = abs(float(np.dot(zB, d)))
    joint = "edge" if cos < 0.2 else ("face" if cos > 0.9 else "angled")
    return dict(d=d, tA=tA, part_b=part_b, E=np.asarray(E, float), zB=zB, joint=joint,
                tB=part_b.thickness if part_b.kind == "plate" else None)


def _b_face(part_b, Q, side):
    """Punkt B välispinnal (side=+1 -> lokaalne z=paksus, -1 -> z=0) ja suund B sisse."""
    ql = part_b.to_local_point(Q)
    ql[2] = part_b.thickness if side > 0 else 0.0
    world = part_b.R @ ql + np.asarray(part_b.position)
    dir_in = -side * part_b.thickness_axis_world()
    return world, dir_in


def _inner_side(project, part_b):
    lo, hi = part_b.world_bounds()
    c = (lo + hi) / 2
    to_center = project.centroid() - c
    zB = part_b.thickness_axis_world()
    s = float(np.dot(zB, to_center))
    return 1 if s >= 0 else -1


def build(project, ftype, params, part_a, P, n_out, flip_side=False):
    """Arvutab kinnituse augud ja riistvara. Tagastab dict:
    holes_a, holes_b (maailma koord. tuple: origin, dir, dia, depth, label), hardware (maailm), part_b."""
    spec = FASTENER_TYPES[ftype]
    pr = dict(spec["params"]); pr.update(params or {})
    J = analyse_joint(project, part_a, np.asarray(P, float), np.asarray(n_out, float))
    d, tA, B, E, joint = J["d"], J["tA"], J["part_b"], J["E"], J["joint"]
    warn = []
    if spec["joint"] == "edge" and joint != "edge":
        raise FastenerError(f"{spec['name']} vajab, et detaili B serv oleks vastu detaili A pinda.")
    if spec["joint"] == "face" and joint != "face":
        raise FastenerError(f"{spec['name']} on kahe pinnapidi kokku pandud plaadi jaoks.")
    if joint in ("edge",) and B.kind == "plate":
        # tsentreeri telg B paksuse keskele
        el = B.to_local_point(E)
        el[2] = B.thickness / 2
        E2 = B.R @ el + np.asarray(B.position)
        shift = E2 - E
        shift -= d * float(np.dot(shift, d))
        E = E + shift
        P = np.asarray(P, float) + shift
    P = np.asarray(P, float)
    side = _inner_side(project, B) * (-1 if flip_side else 1)
    tB = J["tB"] or 18.0
    ha, hb, hwr = [], [], []

    if ftype == "ristmutter":
        L = pr["polt_L"]
        bd = pr["polt_d"] + 1
        ha.append((P - d * 0.5, d, bd, tA + 1, "polt"))
        depthB = L - tA + 5
        hb.append((E, d, bd, depthB, "polt"))
        e = max(L - tA - 12, 12)
        nut_depth = tB - 3 if tB - 3 >= 8 else tB
        F, din = _b_face(B, E + d * e, side)
        hb.append((F, din, pr["mutri_d"], nut_depth, "ristmutter"))
        hwr.append(hw(P, -d, pr["pea_d"], 3, DARK))
        hwr.append(hw(P, d, pr["polt_d"], L, STEEL))
        hwr.append(hw(F + din * 0.3, din, pr["mutri_d"] - 0.4, nut_depth - 0.5, BRASS))
    elif ftype == "minifix":
        k = pr["kaugus"]
        if tA < pr["polt_ava_sugavus"] + 2:
            warn.append("Detail A on Minifixi poldi jaoks õhuke.")
        depthA = min(pr["polt_ava_sugavus"], tA - 2)
        ha.append((E, -d, pr["polt_ava_d"], depthA, "minifixi polt"))
        hb.append((E, d, pr["serva_ava_d"], k, "minifixi serva ava"))
        cam_depth = min(pr["eks_sugavus"], tB - 2)
        F, din = _b_face(B, E + d * k, side)
        hb.append((F, din, pr["eks_d"], cam_depth, "ekstsentrik"))
        hwr.append(hw(E - d * depthA, d, 6, depthA + k, STEEL))
        hwr.append(hw(F + din * 0.3, din, pr["eks_d"] - 0.4, cam_depth - 0.5, ZINC))
    elif ftype == "konfirmaat":
        L = pr["L"]
        ha.append((P - d * 0.5, d, pr["d"], tA + 1, "konfirmaat"))
        hb.append((E, d, pr["juhtava_d"], max(L - tA + 3, 10), "konfirmaadi juhtava"))
        hwr.append(hw(P - d * 0.2, d, pr["pea_d"], 2, DARK))
        hwr.append(hw(P, d, pr["d"], L, STEEL))
    elif ftype == "tuubel":
        L = pr["L"]
        da = min(pr["sugavus_A"], tA - 3)
        ha.append((E, -d, pr["d"], da + 1, "tüübel"))
        hb.append((E, d, pr["d"], L - da + 2, "tüübel"))
        hwr.append(hw(E - d * da, d, pr["d"] - 0.3, L, WOOD))
    elif ftype == "kruvi":
        L = pr["L"]
        ha.append((P - d * 0.5, d, pr["d"] + 0.5, tA + 1, "kruvi"))
        hb.append((E, d, max(pr["d"] * 0.6, 2.0), max(L - tA + 2, 5), "kruvi juhtava"))
        hwr.append(hw(P - d * 0.2, d, pr["d"] * 2, 1.5, DARK))
        hwr.append(hw(P, d, pr["d"], L, STEEL))
    elif ftype == "jalapolt":
        da = pr["sugavus_jalg"]
        ha.append((E, -d, pr["jala_ava_d"], da, "jalapolt"))
        hb.append((E, d, pr["muhv_d"], pr["muhv_L"], "keermesmuhv"))
        hwr.append(hw(E - d * da, d, pr["d"], da + pr["muhv_L"] - 1, STEEL))
        hwr.append(hw(E + d * 0.3, d, pr["muhv_d"] - 0.6, pr["muhv_L"] - 1, BRASS))
    elif ftype == "labipolt":
        tot = tA + tB
        ha.append((P - d * 0.5, d, pr["d"] + 1, tA + 1, "polt"))
        hb.append((E - d * 0.5, d, pr["d"] + 1, tB + 1, "polt"))
        L = round((tot + 10) / 5) * 5
        pr["L"] = L
        hwr.append(hw(P, -d, pr["pea_d"], 3, DARK))
        hwr.append(hw(P, d, pr["d"], L, STEEL))
        hwr.append(hw(P + d * tot, d, pr["mutri_d"], 8, DARK))
    else:
        raise FastenerError("Tundmatu kinnitus")
    if joint != "edge" and ftype != "labipolt" and J["tB"]:
        fixed = []
        for (o, dd, dia, depth, lab) in hb:
            if abs(float(np.dot(dd, d))) > 0.9 and depth > tB - 2:
                depth = tB - 2
                if "lühendatud" not in " ".join(warn):
                    warn.append("Ava B-s lühendatud (pinnapidi ühendus) – vali lühem kinnitus.")
            fixed.append((o, dd, dia, depth, lab))
        hb = fixed
    return dict(holes_a=ha, holes_b=hb, hardware=hwr, part_b=B, params=pr, warnings=warn,
                P=P, d=d)


def add_fastener(project, ftype, params, part_a, P, n_out, flip_side=False):
    from .model import Fastener, Hole
    res = build(project, ftype, params, part_a, P, n_out, flip_side)
    B = res["part_b"]
    f = Fastener(project.new_id(), ftype, res["params"], part_a.id, B.id)
    for (o, dd, dia, depth, lab) in res["holes_a"]:
        part_a.holes.append(Hole(part_a.to_local_point(o), part_a.to_local_dir(dd), dia, depth, f.id, lab))
    for (o, dd, dia, depth, lab) in res["holes_b"]:
        B.holes.append(Hole(B.to_local_point(o), B.to_local_dir(dd), dia, depth, f.id, lab))
    for h in res["hardware"]:
        f.hardware.append(dict(h, origin=part_a.to_local_point(h["origin"]).tolist(),
                               direction=part_a.to_local_dir(h["direction"]).tolist()))
    f.axis = [part_a.to_local_point(res["P"]).tolist(), part_a.to_local_dir(res["d"]).tolist()]
    project.fasteners.append(f)
    return f, res["warnings"]


def hardware_summary(project):
    out = {}
    for f in project.fasteners:
        spec = FASTENER_TYPES.get(f.ftype, {})
        key = spec.get("name", f.ftype)
        if f.ftype == "ristmutter":
            key = f"Mööblipolt M{f.params.get('polt_d', 6):g}×{f.params.get('polt_L', 70):g} + ristmutter Ø{f.params.get('mutri_d', 10):g}"
        elif f.ftype == "labipolt":
            key = f"Mööblipolt M{f.params.get('d', 6):g}×{f.params.get('L', 50):g} + kuppelmutter"
        elif f.ftype == "konfirmaat":
            key = f"Konfirmaat {f.params.get('d', 7):g}×{f.params.get('L', 50):g}"
        elif f.ftype == "tuubel":
            key = f"Puittüübel {f.params.get('d', 8):g}×{f.params.get('L', 35):g}"
        elif f.ftype == "hing":
            key = "Peitehing 35 mm + paigaldusplaat"
        elif f.ftype == "jalapolt":
            key = f"Jalapolt M{f.params.get('d', 8):g} + keermesmuhv M{f.params.get('d', 8):g}"
        elif f.ftype == "kruvi":
            key = f"Puidukruvi {f.params.get('d', 4):g}×{f.params.get('L', 40):g}"
        out[key] = out.get(key, 0) + 1
    # siinid, käepidemed ja detailide külge märgitud lisatarvikud
    slides = {}
    for p in project.parts:
        role = getattr(p, "role", None)
        if role == "slide":
            k = (p.slide or {}).get("name", "Sahtlisiin") if getattr(p, "slide", None) else "Sahtlisiin"
            slides[k] = slides.get(k, 0) + 1
        elif role == "handle" and getattr(p, "handle", None):
            from .handles import describe
            k = "Käepide: " + describe(p.handle)
            out[k] = out.get(k, 0) + 1
            ks = "Käepideme kruvi M4×25"
            out[ks] = out.get(ks, 0) + (1 if p.handle["style"] in ("nupp_umar", "nupp_kandiline") else 2)
        for nm, q in (getattr(p, "hw", None) or []):
            out[nm] = out.get(nm, 0) + q
    for k, n in slides.items():
        out[f"{k} (paar)"] = out.get(f"{k} (paar)", 0) + n // 2
    return out
