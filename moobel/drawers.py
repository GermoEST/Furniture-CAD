"""Sahtlid ja klaviatuurisahtel kahe küljeseina vahele.

Teljed: i = külgseinte vahe (horisontaalne), j = sügavus (horisontaalne, sahtel liigub piki j), z = üles.
Kõik detailid on telgedega joondatud ristkülikplaadid.
"""
import numpy as np

from . import geom
from . import handles as H
from .model import Part

SLIDE_LENGTHS = [250, 300, 350, 400, 450, 500, 550, 600, 650]
SLIDES = {
    "kuul": dict(name="Kuullaagersiin", clr=12.7, h=45.0),
    "rull": dict(name="Rullsiin", clr=12.5, h=35.0),
}
BOX_MATS = {
    "vineer12": ("Vineer", 12.0, "#e2c99c"),
    "vineer15": ("Vineer", 15.0, "#e2c99c"),
    "lmdp16": ("Puitlaastplaat (LMDP)", 16.0, "#efeee9"),
}
BOTTOMS = {
    "hdf3": ("HDF (kõvapapp)", 3.0, "#cfc2ad"),
    "vineer4": ("Vineer", 4.0, "#e7d2a8"),
    "papp3": ("Papp / kõvapapp", 3.0, "#c9b593"),
}
WIDE_LIMIT = 600.0
SLIDE_COLOR = "#aeb5bc"


class DrawerError(Exception):
    pass


def _axis_of(part):
    n = part.thickness_axis_world()
    i = int(np.argmax(np.abs(n)))
    if abs(n[i]) < 0.99:
        raise DrawerError(f"'{part.name}' ei ole telgedega joondatud (pööra 90° kaupa).")
    return i


def analyse(A, B):
    """Leiab kahe küljeseina vahelise ava."""
    if A.kind != "plate" or B.kind != "plate":
        raise DrawerError("Vali kaks plaati (küljeseina).")
    ia, ib = _axis_of(A), _axis_of(B)
    if ia != ib:
        raise DrawerError("Valitud plaadid ei ole paralleelsed.")
    if ia == 2:
        raise DrawerError("Valitud plaadid on lamavad – vali kaks püstist küljeseina.")
    i = ia
    j = 1 - i if i in (0, 1) else 0
    alo, ahi = A.world_bounds()
    blo, bhi = B.world_bounds()
    if ahi[i] <= blo[i]:
        lo_side, hi_side = A, B
    elif bhi[i] <= alo[i]:
        lo_side, hi_side = B, A
    else:
        raise DrawerError("Plaadid kattuvad – nende vahel pole ava.")
    llo, lhi = lo_side.world_bounds()
    hlo, hhi = hi_side.world_bounds()
    i0, i1 = lhi[i], hlo[i]
    j0, j1 = max(llo[j], hlo[j]), min(lhi[j], hhi[j])
    z0, z1 = max(llo[2], hlo[2]), min(lhi[2], hhi[2])
    if j1 - j0 < 200 or z1 - z0 < 80:
        raise DrawerError("Küljeseinte ühine osa on sahtlite jaoks liiga väike.")
    return dict(i=i, j=j, i0=float(i0), i1=float(i1), j0=float(j0), j1=float(j1), z0=float(z0), z1=float(z1),
                W=float(i1 - i0), D=float(j1 - j0), t_side=float(min(lo_side.thickness, hi_side.thickness)),
                lo_side=lo_side, hi_side=hi_side)


def axis_name(ax, positive):
    return ("+" if positive else "−") + "XYZ"[ax]


def _plate(pr, name, mins, maxs, thin, color, material, group, role=None):
    mins, maxs = np.asarray(mins, float), np.asarray(maxs, float)
    size = maxs - mins
    others = [a for a in range(3) if a != thin]
    E = np.eye(3)
    R = np.column_stack([E[others[0]], E[others[1]], E[thin]])
    if np.linalg.det(R) < 0:
        R[:, 0] = -R[:, 0]
    p = Part(pr.new_id(), name)
    p.thickness = float(size[thin])
    p.set_rect(float(size[others[0]]), float(size[others[1]]), 0)
    p.R = R
    lo, _ = p.world_bounds()
    p.position = (np.asarray(p.position) + mins - lo).tolist()
    p.color, p.material, p.group = color, material, group
    p.role = role
    pr.add_part(p)
    return p


def slide_length(avail):
    ok = [L for L in SLIDE_LENGTHS if L <= avail]
    return ok[-1] if ok else None


def free_depth(pr, info, zb, zt, front_min, ignore=()):
    """Kui sügavale saab sahtel minna, enne kui jääb ette mõni muu detail (nt tagasein)."""
    i, j = info["i"], info["j"]
    jf = info["j0"] if front_min else info["j1"]
    best = info["D"]
    skip = {info["lo_side"].id, info["hi_side"].id} | set(ignore)
    for p in pr.parts:
        if p.id in skip:
            continue
        lo, hi = p.world_bounds()
        if hi[i] <= info["i0"] + 1 or lo[i] >= info["i1"] - 1:
            continue
        if hi[2] <= zb + 1 or lo[2] >= zt - 1:
            continue
        if hi[j] <= info["j0"] + 1 or lo[j] >= info["j1"] - 1:
            continue
        d = (lo[j] - jf) if front_min else (jf - hi[j])
        if d > 50:
            best = min(best, d)
    return float(best)


def plan(info, o, pr=None):
    """Arvutab mõõdud ilma detaile loomata (dialoogi infoks). Tagastab dict või tõstab DrawerError."""
    sl = SLIDES[o["slide"]]
    clr = sl["clr"]
    tf = o["front_t"]
    inset = o["front_mode"] == "sisse"
    D = info["D"]
    if pr is not None:
        if o["kind"] == "klaviatuur":
            D = free_depth(pr, info, o["kb_top"] - 70, o["kb_top"], o["front_side"] == "min")
        else:
            D = free_depth(pr, info, o["z_bottom"], o["z_top"], o["front_side"] == "min")
    avail = D - (tf if inset else 0) - 10
    L = o["L"] if o.get("L") else slide_length(avail)
    if not L or L > avail + 0.1:
        raise DrawerError(f"Vaba sügavust on {D:.0f} mm – liiga vähe (lühim siin 250 mm).")
    zb, zt = o["z_bottom"], o["z_top"]
    if zt - zb < 80:
        raise DrawerError("Ava kõrgus on liiga väike.")
    Wc = info["W"]
    out = dict(L=L, clr=clr, Wc=Wc, D_free=D)
    if o["kind"] == "klaviatuur":
        Wt = min(o["kb_width"], Wc - 2 * clr)
        out.update(Wt=Wt, spacer=(Wc - Wt) / 2 - clr)
        return out
    n = o["count"]
    gap = o["gap"]
    hf = (zt - zb - (n + 1) * gap) / n
    if hf < 70:
        raise DrawerError("Sahtleid on selle kõrguse jaoks liiga palju.")
    Wb = Wc - 2 * clr
    wide = (Wb - 2 * BOX_MATS[o["box_mat"]][1]) > WIDE_LIMIT
    support = wide and o["wide_mode"] in ("liist", "molemad")
    thick = wide and o["wide_mode"] in ("paks", "molemad")
    tb = 12.0 if thick else BOTTOMS[o["bottom"]][1]
    hb = int((hf - 35 - (20 if support else 0)) // 5 * 5)
    hb = max(50, min(hb, 300))
    out.update(n=n, hf=hf, Wb=Wb, hb=hb, tb=tb, wide=wide, support=support, thick=thick)
    return out


def build(pr, A, B, o):
    """Loob sahtlid. Tagastab (detailide list, hoiatused)."""
    info = analyse(A, B)
    P = plan(info, o, pr)
    i, j = info["i"], info["j"]
    front_min = o["front_side"] == "min"
    jf = info["j0"] if front_min else info["j1"]
    s_in = 1.0 if front_min else -1.0          # sügavuse suund esiservast sisse
    out_dir = np.zeros(3); out_dir[j] = -s_in   # esipaneelist välja
    tf = o["front_t"]
    inset = o["front_mode"] == "sisse"
    i0, i1 = info["i0"], info["i1"]
    L, clr = P["L"], P["clr"]
    sl = SLIDES[o["slide"]]
    made, warns = [], []

    def box(ia, ib, ja, jb, za, zb_, thin, name, color, mat, group, role=None):
        mins = np.zeros(3); maxs = np.zeros(3)
        mins[i], maxs[i] = min(ia, ib), max(ia, ib)
        mins[j], maxs[j] = min(ja, jb), max(ja, jb)
        mins[2], maxs[2] = min(za, zb_), max(za, zb_)
        p = _plate(pr, name, mins, maxs, thin, color, mat, group, role)
        made.append(p)
        return p

    def jr(a, b):
        """Vahemik sügavuses esiservast a..b mm sissepoole."""
        return jf + s_in * a, jf + s_in * b

    def add_slides(group, za, h):
        for side, (a, b) in (("V", (i0, i0 + clr)), ("P", (i1 - clr, i1))):
            s = box(a, b, *jr(box_j0, box_j0 + L), za, za + h, i, f"{group} – siin {side}", SLIDE_COLOR,
                    "Metall", group, "slide")
            s.slide = dict(name=f"{sl['name']} {L:g} mm", L=L)

    box_j0 = (tf if inset else 0) + 2
    fin = o["finish"]

    if o["kind"] == "klaviatuur":
        g = "Klaviatuurisahtel"
        used = {getattr(p, "group", "") for p in pr.parts}
        k2 = 2
        while g in used:
            g = f"Klaviatuurisahtel {k2}"; k2 += 1
        Wt, sp = P["Wt"], P["spacer"]
        ttop = o["kb_top"]
        tt = 18.0
        ci = (i0 + i1) / 2
        a0, a1 = ci - Wt / 2, ci + Wt / 2
        box(a0, a1, *jr(box_j0, box_j0 + L), ttop - tt, ttop, 2, f"{g} – alus", "#d9b98c",
            "Puitlaastplaat (LMDP)", g)
        rail_h = 45.0
        for nm, (ra, rb) in (("V", (a0, a0 + 18)), ("P", (a1 - 18, a1))):
            box(ra, rb, *jr(box_j0, box_j0 + L), ttop - tt - rail_h, ttop - tt, i, f"{g} – küljeliist {nm}",
                "#d9b98c", "Täispuit", g)
        lip_out = 0.0 if inset else 0.0
        box(a0, a1, *jr(box_j0 - 18 - lip_out, box_j0), ttop - tt - rail_h, ttop + 15, j,
            f"{g} – esiliist", "#c49a6c", "Täispuit", g)
        if sp > 1:
            for nm, (ra, rb) in (("V", (i0, i0 + sp)), ("P", (i1 - sp, i1))):
                box(ra, rb, *jr(box_j0, box_j0 + L), ttop - tt - rail_h, ttop - tt, i,
                    f"{g} – siini aluslatt {nm}", "#e3c48f", "Täispuit", g)
        # siinid aluslati ja küljeliistu vahel
        za = ttop - tt - rail_h + (rail_h - sl["h"]) / 2
        for side, (a, b) in (("V", (a0 - clr, a0)), ("P", (a1, a1 + clr))):
            s = box(a, b, *jr(box_j0, box_j0 + L), za, za + sl["h"], i, f"{g} – siin {side}", SLIDE_COLOR,
                    "Metall", g, "slide")
            s.slide = dict(name=f"{sl['name']} {L:g} mm", L=L)
        made[0].hw = [["Puidukruvi 4×16 (siinid)", 12], ["Puidukruvi 4×40", 6]]
        if sp > 1:
            made[0].hw.append(["Puidukruvi 4×30 (aluslatid)", 8])
        for q in made:
            q.pull = out_dir.tolist()
        if o["kb_handle"]:
            _add_handle(pr, made, o["handle"], fin, out_dir, j, i, (i0 + i1) / 2,
                        jr(box_j0 - 18, box_j0 - 18)[0], ttop - (rail_h + tt) / 2 + 7, Wt, rail_h + tt + 15, g)
        return made, warns

    n, hf, gap = P["n"], P["hf"], o["gap"]
    Wb, hb, tb = P["Wb"], P["hb"], P["tb"]
    bm, bt, bc = BOX_MATS[o["box_mat"]]
    if P["thick"]:
        botm, botc = "Vineer", "#e7d2a8"
    else:
        botm, _, botc = BOTTOMS[o["bottom"]]
    ts = bt
    if inset:
        fa, fb = i0 + 2, i1 - 2
        fj = jr(0, tf)
    else:
        ov = info["t_side"] - 2
        fa, fb = i0 - ov, i1 + ov
        fj = jr(-tf, 0)
    zt = o["z_top"]
    used = {getattr(p, "group", "") for p in pr.parts}
    start = 0
    while f"Sahtel {start + 1}" in used:
        start += 1
    for k in range(n):
        g = f"Sahtel {start + k + 1}"
        f_top = zt - gap - k * (hf + gap)
        f_bot = f_top - hf
        front = box(fa, fb, *fj, f_bot, f_top, j, f"{g} – esipaneel", o["front_color"], o["front_mat"], g)
        base = f_bot + 8 + (20 if P["support"] else 0)
        bi0, bi1 = i0 + clr, i1 - clr
        # põhi (kasti alla)
        box(bi0, bi1, *jr(box_j0, box_j0 + L), base, base + tb, 2, f"{g} – põhi", botc, botm, g)
        sz0, sz1 = base + tb, base + tb + hb - tb
        box(bi0, bi0 + ts, *jr(box_j0, box_j0 + L), sz0, sz1, i, f"{g} – külg V", bc, bm, g)
        box(bi1 - ts, bi1, *jr(box_j0, box_j0 + L), sz0, sz1, i, f"{g} – külg P", bc, bm, g)
        box(bi0 + ts, bi1 - ts, *jr(box_j0, box_j0 + ts), sz0, sz1, j, f"{g} – kasti esiosa", bc, bm, g)
        box(bi0 + ts, bi1 - ts, *jr(box_j0 + L - ts, box_j0 + L), sz0, sz1, j, f"{g} – tagaosa", bc, bm, g)
        if P["support"]:
            ci = (bi0 + bi1) / 2
            box(ci - 20, ci + 20, *jr(box_j0 + ts, box_j0 + L - ts), base - 20, base, i,
                f"{g} – põhja tugiliist", "#e3c48f", "Täispuit", g)
        sh = sl["h"] if hb - tb >= sl["h"] else hb - tb
        add_slides(g, sz0 + max(0.0, (hb - tb - sh) / 2), sh)
        nails = int(2 * (L + Wb) / 100) + 4
        front.hw = [["Puidukruvi 3,5×30 (kast)", 8], ["Klamber/nael 1,2×25 (põhi)", nails],
                    ["Puidukruvi 4×25 (esipaneel)", 4], ["Puidukruvi 4×16 (siinid)", 12]]
        if P["support"]:
            front.hw.append(["Puidukruvi 3,5×20 (tugiliist)", 4])
        hz = (f_bot + f_top) / 2
        if hf > 250 and o["handle"] not in ("profiil",):
            hz = f_top - 70
        out_face = fj[0] if s_in > 0 else fj[1]
        out_face = min(fj) if out_dir[j] < 0 else max(fj)
        _add_handle(pr, made, o["handle"], fin, out_dir, j, i, (fa + fb) / 2, out_face, hz, fb - fa, hf, g)
    for q in made:
        q.pull = out_dir.tolist()
    if P["wide"]:
        warns.append(f"Kasti sisemõõt on üle {WIDE_LIMIT:.0f} mm – "
                     + ("lisatud paksem põhi" if P["thick"] else "")
                     + (" ja " if P["thick"] and P["support"] else "")
                     + ("lisatud põhja tugiliist" if P["support"] else "") + ". Kasuta tugevamaid (45 kg) siine.")
    return made, warns


def _add_handle(pr, made, style, finish, out_dir, j, i, ci, face_j, cz, front_w, front_h, group):
    if style == "puudub":
        return None
    cc = H.default_cc(front_w)
    hd = dict(style=style, cc=cc, finish=finish, front_w=float(front_w), front_h=float(front_h))
    p = Part(pr.new_id(), f"{group} – käepide")
    set_handle_geometry(p, hd)
    ez = np.array([0, 0, 1.0])
    ey = np.asarray(out_dir, float)
    ex = np.cross(ey, ez)
    R = np.column_stack([ex, ey, ez])
    if np.linalg.det(R) < 0:
        R[:, 0] = -R[:, 0]
    p.R = R
    pos = np.zeros(3)
    pos[i] = ci
    pos[j] = face_j
    pos[2] = cz
    p.position = pos.tolist()
    p.material = "Metall"
    p.role = "handle"
    p.group = group
    pr.add_part(p)
    made.append(p)
    return p


def set_handle_geometry(part, hd):
    m = H.handle_mesh(hd["style"], hd["cc"], hd["front_w"], hd["front_h"])
    part.kind = "mesh"
    part.source = "handle"
    part.mesh_v = np.round(m.vertices, 3).tolist()
    part.mesh_f = m.faces.tolist()
    part.thickness = float(min(m.extents))
    part.handle = dict(hd)
    part.color = H.FINISHES.get(hd["finish"], "#1f2226")
    part.description = H.describe(hd)
    part._cache = {}
