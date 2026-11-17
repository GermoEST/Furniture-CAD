"""Automaatsed konstruktsioonid: kinnituste jaotamine liitekohta, uksed + hinged, riiulid + 32 mm augud,
ning valmis mallid (kapp, riiul, kummut, öökapp, voodiraam)."""
import numpy as np

from . import geom
from .model import Part, Hole, Fastener, PALETTE
from .fasteners import add_fastener, FastenerError, hw as _hw, STEEL, ZINC
from . import drawers as DR

E = np.eye(3)


# ====================================================================== abi
def box(pr, name, mins, maxs, thin, color, material="Puitlaastplaat (LMDP)", group="", role=None):
    """Telgedega joondatud plaat maailma koordinaatides."""
    return DR._plate(pr, name, mins, maxs, thin, color, material, group, role)


def _axis(part):
    n = part.thickness_axis_world()
    i = int(np.argmax(np.abs(n)))
    return i


def auto_join(pr, A, B, ftype, n=None, params=None, edge_margin=60.0):
    """Jaotab kinnitused liitekohta: B serv on vastu A pinda. Tagastab lisatud kinnituste arvu."""
    ia = _axis(A)
    alo, ahi = A.world_bounds()
    blo, bhi = B.world_bounds()
    if abs(blo[ia] - ahi[ia]) < 0.6:
        outer, n_out = alo[ia], -1.0          # B on A "suuremal" poolel -> klikk A väiksemal pinnal
    elif abs(bhi[ia] - alo[ia]) < 0.6:
        outer, n_out = ahi[ia], 1.0
    else:
        return 0
    others = [k for k in range(3) if k != ia]
    ib = _axis(B)
    if ib == ia:
        return 0
    il = [k for k in others if k != ib][0]
    lo = max(alo[il], blo[il])
    hi = min(ahi[il], bhi[il])
    ln = hi - lo
    if ln < 40:
        return 0
    if n is None:
        n = 2 if ln <= 450 else (3 if ln <= 900 else 4)
    m = min(edge_margin, ln / 4)
    zs = [lo + m] if n == 1 else list(np.linspace(lo + m, hi - m, n))
    cb = (max(alo[ib], blo[ib]) + min(ahi[ib], bhi[ib])) / 2
    cnt = 0
    for v in zs:
        P = np.zeros(3)
        P[ia] = outer
        P[il] = v
        P[ib] = cb
        nv = np.zeros(3); nv[ia] = n_out
        try:
            add_fastener(pr, ftype, params or {}, A, P, nv)
            cnt += 1
        except FastenerError:
            pass
    pr.note_assembled(A.id, B.id)
    return cnt


# ====================================================================== uksed
def hinge_count(h):
    return 2 if h <= 900 else (3 if h <= 1600 else (4 if h <= 2000 else 5))


def add_doors(pr, A, B, o):
    """o: count(1/2), z_bottom, z_top, mode('peale'/'sisse'), front_side('min'/'max'), hinge_side('vasak'/'parem'),
    t, glass(bool), color, material, handle, finish"""
    info = DR.analyse(A, B)
    i, j = info["i"], info["j"]
    front_min = o["front_side"] == "min"
    jf = info["j0"] if front_min else info["j1"]
    s_in = 1.0 if front_min else -1.0
    out = np.zeros(3); out[j] = -s_in
    t = 5.0 if o.get("glass") else float(o.get("t", 18))
    gap = 2.0
    i0, i1 = info["i0"], info["i1"]
    ts = info["t_side"]
    if o["mode"] == "peale":
        a0, a1 = i0 - ts + gap, i1 + ts - gap
        ja, jb = jf - s_in * t - s_in * 2, jf - s_in * 2        # 2 mm vahe korpuse ees
        za, zb = o["z_bottom"] - ts + gap, o["z_top"] + ts - gap
    else:
        a0, a1 = i0 + gap, i1 - gap
        ja, jb = jf, jf + s_in * t
        za, zb = o["z_bottom"] + gap, o["z_top"] - gap
    n = int(o.get("count", 1))
    used = {getattr(p, "group", "") for p in pr.parts}
    k = 1
    while f"Uks {k}" in used:
        k += 1
    made = []
    widths = [(a0, a1)] if n == 1 else [(a0, (a0 + a1) / 2 - 1.5), ((a0 + a1) / 2 + 1.5, a1)]
    for di, (da, db) in enumerate(widths):
        g = f"Uks {k + di}"
        hinge_left = (o.get("hinge_side", "vasak") == "vasak") if n == 1 else (di == 0)
        mins = np.zeros(3); maxs = np.zeros(3)
        mins[i], maxs[i] = da, db
        mins[j], maxs[j] = min(ja, jb), max(ja, jb)
        mins[2], maxs[2] = za, zb
        mat = "Klaas" if o.get("glass") else o.get("material", "MDF")
        col = "#bfdde3" if o.get("glass") else o.get("color", "#f2f0eb")
        door = box(pr, f"{g} – uks", mins, maxs, j, col, mat, g)
        door.pull = out.tolist()
        door.edges = {} if o.get("glass") else {"L1": 1.0, "L2": 1.0, "W1": 1.0, "W2": 1.0}
        made.append(door)
        side = info["lo_side"] if hinge_left else info["hi_side"]
        edge_i = da if hinge_left else db
        sgn = 1.0 if hinge_left else -1.0           # hinge -> ukse sisse
        h = zb - za
        nh = hinge_count(h)
        zs = np.linspace(za + 100, zb - 100, nh) if h > 260 else [za + h / 2]
        inner_j = max(ja, jb) if s_in > 0 else min(ja, jb)   # ukse sisepind (korpuse poole)
        for zc in zs:
            f = Fastener(pr.new_id(), "hing", {"cup": 35.0}, door.id, side.id)
            cup = np.zeros(3); cup[i] = edge_i + sgn * 22.5; cup[j] = inner_j; cup[2] = zc
            din = np.zeros(3); din[j] = -s_in            # ukse sisepinnast ukse sisse (välja suunas)
            if not o.get("glass"):
                door.holes.append(Hole(door.to_local_point(cup), door.to_local_dir(din), 35.0, 12.0, f.id, "hing"))
            # paigaldusplaat küljeseinale: 2 ava 37 mm esiservast
            plate_i = info["i0"] if hinge_left else info["i1"]
            dside = np.zeros(3); dside[i] = -1.0 if hinge_left else 1.0
            for dz in (-16.0, 16.0):
                hp = np.zeros(3); hp[i] = plate_i; hp[j] = jf + s_in * 37.0; hp[2] = zc + dz
                side.holes.append(Hole(side.to_local_point(hp), side.to_local_dir(dside), 5.0, 12.0, f.id,
                                       "hinge plate"))
            # riistvara (ukse koordinaatides): kauss + hõlm
            f.hardware.append(dict(_hw(cup - din * 0.5, din, 34.0, 12.0, ZINC),
                                   origin=door.to_local_point(cup - din * 0.5).tolist(),
                                   direction=door.to_local_dir(din).tolist()))
            arm_o = cup.copy(); arm_o[i] = edge_i - sgn * 6
            f.hardware.append(dict(_hw(arm_o, -din, 10, 14, STEEL), origin=door.to_local_point(arm_o).tolist(),
                                   direction=door.to_local_dir(-din).tolist()))
            f.axis = [door.to_local_point(cup).tolist(), door.to_local_dir(din).tolist()]
            pr.fasteners.append(f)
            pr.note_assembled(side.id, door.id)
        door.hw = [["Peitehinge kruvid 4×16", 4 * nh]]
        # käepide (püstine) vastasservas
        if o.get("handle", "puudub") != "puudub":
            hi_ = db - 45 if hinge_left else da + 45
            face = min(ja, jb) if s_in > 0 else max(ja, jb)
            hz = (za + zb) / 2 if h < 900 else min(zb - 150, za + 1050)
            hp = DR._add_handle(pr, made, o["handle"], o.get("finish", "Must"), out, j, i, hi_, face, hz,
                                min(h, 400), 120, g)
            if hp is not None:
                hp.R = geom.axis_angle(out, 90) @ hp.R
        for q in made:
            if q.group == g:
                q.pull = out.tolist()
    return made


# ====================================================================== riiulid
def add_shelves(pr, A, B, o):
    """o: count, z_bottom, z_top, front_side, t, setback, holes(bool), color, material"""
    info = DR.analyse(A, B)
    i, j = info["i"], info["j"]
    front_min = o["front_side"] == "min"
    jf = info["j0"] if front_min else info["j1"]
    s_in = 1.0 if front_min else -1.0
    t = float(o.get("t", 18))
    zb, zt = o["z_bottom"], o["z_top"]
    n = int(o["count"])
    D = info["D"]
    setback = float(o.get("setback", 20))
    depth = D - setback - 5
    made = []
    used = {getattr(p, "group", "") for p in pr.parts}
    gname = "Riiulid"
    k = 2
    while gname in used:
        gname = f"Riiulid {k}"; k += 1
    # 32 mm aukude read
    z_first = zb + 64
    rows_z = list(np.arange(z_first, zt - 48, 32.0))
    for q in range(n):
        target = zb + (q + 1) * (zt - zb) / (n + 1)
        if rows_z and o.get("holes", True):
            hz = min(rows_z, key=lambda z: abs(z - (target - t / 2 - 4)))
            zbot = hz + 4           # riiulikandur ~4 mm
        else:
            zbot = target - t / 2
        mins = np.zeros(3); maxs = np.zeros(3)
        mins[i], maxs[i] = info["i0"] + 1, info["i1"] - 1
        ja, jb = jf + s_in * setback, jf + s_in * (setback + depth)
        mins[j], maxs[j] = min(ja, jb), max(ja, jb)
        mins[2], maxs[2] = zbot, zbot + t
        sh = box(pr, f"Riiul {q + 1}", mins, maxs, 2, o.get("color", "#d9b98c"),
                 o.get("material", "Puitlaastplaat (LMDP)"), gname)
        sh.edges = {"L1": 1.0}
        sh.hw = [["Riiulikandur Ø5", 4]]
        made.append(sh)
        pr.note_assembled(sh.id)
    if o.get("holes", True) and rows_z:
        for side, x, dx in ((info["lo_side"], info["i0"], -1.0), (info["hi_side"], info["i1"], 1.0)):
            for jj in (jf + s_in * 37.0, jf + s_in * (D - 37.0)):
                for z in rows_z:
                    p = np.zeros(3); p[i] = x; p[j] = jj; p[2] = z
                    d = np.zeros(3); d[i] = dx
                    side.holes.append(Hole(side.to_local_point(p), side.to_local_dir(d), 5.0, 10.0, None,
                                           "32 mm"))
    return made


# ====================================================================== mallid
TEMPLATES = {
    "kapp": "Kapp (korpus, uksed, riiulid)",
    "riiul": "Riiul (avatud)",
    "kummut": "Kummut (sahtlid)",
    "okapp": "Öökapp",
    "voodi": "Voodiraam",
}

TPL_DEFAULTS = {
    "kapp": dict(W=800, D=560, H=2000, t=18, shelves=4, doors=2, drawers=0, plinth=80, back=True),
    "riiul": dict(W=800, D=300, H=1800, t=18, shelves=5, doors=0, drawers=0, plinth=0, back=True),
    "kummut": dict(W=800, D=450, H=850, t=18, shelves=0, doors=0, drawers=4, plinth=60, back=True),
    "okapp": dict(W=450, D=400, H=550, t=18, shelves=0, doors=0, drawers=2, plinth=0, back=True),
    "voodi": dict(W=1600, D=2000, H=400, t=25, shelves=0, doors=0, drawers=0, plinth=0, back=False),
}


def build_template(pr, kind, o):
    """Ehitab malli. o: W, D, H, t, shelves, doors, drawers, plinth, back, ftype, color, front_color, x0"""
    x0 = float(o.get("x0", 0.0))
    W, D, H, t = (float(o[k]) for k in ("W", "D", "H", "t"))
    col = o.get("color", PALETTE[0])
    fcol = o.get("front_color", "#f2f0eb")
    ft = o.get("ftype", "konfirmaat")
    made_before = {p.id for p in pr.parts}
    if kind == "voodi":
        return _bed(pr, o, x0)
    pl = float(o.get("plinth", 0))
    # küljed
    sl = box(pr, "Külg vasak", [x0, 0, 0], [x0 + t, D, H], 0, col)
    sr = box(pr, "Külg parem", [x0 + W - t, 0, 0], [x0 + W, D, H], 0, col)
    top = box(pr, "Pealne", [x0 + t, 0, H - t], [x0 + W - t, D, H], 2, col)
    bot = box(pr, "Põhi", [x0 + t, 0, pl], [x0 + W - t, D, pl + t], 2, col)
    for q in (sl, sr, top, bot):
        q.edges = {"L1": 1.0}
    pr.note_assembled(sl.id, bot.id, sr.id, top.id)
    for side in (sl, sr):
        for hb in (top, bot):
            auto_join(pr, side, hb, ft)
    if pl > 0:
        kick = box(pr, "Sokkel", [x0 + t, 30, 0], [x0 + W - t, 30 + t, pl], 1, col)
        auto_join(pr, sl, kick, "tuubel", 2)
        auto_join(pr, sr, kick, ft, 2)
    if o.get("back", True):
        bk = box(pr, "Tagasein", [x0, D, 0 if pl == 0 else pl], [x0 + W, D + 3, H], 1, "#e7e2d6", "HDF (kõvapapp)")
        n_nails = int((2 * (W + H - pl)) / 100)
        bk.hw = [["Klamber/nael 1,2×25 (tagasein)", n_nails]]
        pr.note_assembled(bk.id)
    zb, zt = pl + t, H - t
    if int(o.get("drawers", 0)) > 0:
        DR.build(pr, sl, sr, dict(kind="sahtlid", count=int(o["drawers"]), z_bottom=zb, z_top=zt, front_side="min",
                                  slide="kuul", L=None, box_mat="vineer12", bottom="vineer4", wide_mode="molemad",
                                  front_mode="sisse", front_t=18, gap=3, front_color=fcol, front_mat="MDF",
                                  handle=o.get("handle", "u_umar"), finish=o.get("finish", "Must"),
                                  kb_width=700, kb_top=zt, kb_handle=False))
    if int(o.get("shelves", 0)) > 0:
        add_shelves(pr, sl, sr, dict(count=int(o["shelves"]), z_bottom=zb, z_top=zt, front_side="min",
                                     t=t, setback=20 if int(o.get("doors", 0)) == 0 else 25, holes=True, color=col))
    if int(o.get("doors", 0)) > 0:
        add_doors(pr, sl, sr, dict(count=int(o["doors"]), z_bottom=zb - t, z_top=zt + t, mode="peale",
                                   front_side="min", hinge_side="vasak", t=18, glass=False, color=fcol,
                                   material="MDF", handle=o.get("handle", "u_umar"), finish=o.get("finish", "Must")))
    return [p for p in pr.parts if p.id not in made_before]


def _bed(pr, o, x0):
    """Voodiraam: madratsi mõõt W × D, külgpuud, otsad, keskpuu, liistud ja 6 jalga."""
    from . import legs as LG
    W, L, H = float(o["W"]), float(o["D"]), float(o["H"])
    t = float(o.get("t", 25))
    col = o.get("color", "#c49a6c")
    rail_h = 200.0
    z0 = H - rail_h
    made_before = {p.id for p in pr.parts}
    head_h = max(H + 500, 900)
    head = box(pr, "Peaots", [x0, 0, 0], [x0 + W + 2 * t, t, head_h], 1, col, "Liimpuit")
    foot = box(pr, "Jalutsiots", [x0, L + t, 0], [x0 + W + 2 * t, L + 2 * t, H], 1, col, "Liimpuit")
    r1 = box(pr, "Külgpuu vasak", [x0, t, z0], [x0 + t, L + t, H], 0, col, "Liimpuit")
    r2 = box(pr, "Külgpuu parem", [x0 + W + t, t, z0], [x0 + W + 2 * t, L + t, H], 0, col, "Liimpuit")
    pr.note_assembled(head.id, r1.id, r2.id, foot.id)
    for a in (head, foot):
        for b in (r1, r2):
            auto_join(pr, a, b, "ristmutter", 2, {"polt_L": 110})
    # liistude kandurid ja keskpuu
    lat_t, lat_h = 18.0, 70.0
    zl = H - 60 - lat_t
    c1 = box(pr, "Liistukandur vasak", [x0 + t, t, zl - 40], [x0 + t + 30, L + t, zl], 0, "#e3c48f", "Täispuit")
    c2 = box(pr, "Liistukandur parem", [x0 + W + t - 30, t, zl - 40], [x0 + W + t, L + t, zl], 0, "#e3c48f", "Täispuit")
    cm = box(pr, "Keskpuu", [x0 + t + W / 2 - 22, t, zl - 120], [x0 + t + W / 2 + 22, L + t, zl], 0, "#e3c48f", "Täispuit")
    for c in (c1, c2):
        c.hw = [["Puidukruvi 5×60 (liistukandur)", int(L // 300) + 1]]
    pr.note_assembled(c1.id, c2.id, cm.id)
    cm.hw = [["Keskpuu kinnitusnurk", 2]]
    n = int(L // 100)
    step = L / n
    slats = []
    for k in range(n):
        y = t + k * step + (step - lat_h) / 2
        s = box(pr, f"Liist {k + 1}", [x0 + t + 2, y, zl], [x0 + W + t - 2, y + lat_h, zl + lat_t], 2,
                "#ecd9b0", "Täispuit", "Voodiliistud")
        slats.append(s)
    slats[0].hw = [["Puidukruvi 4×30 (liistud)", 3 * n]]
    for s in slats:
        pr.note_assembled(s.id)
    # keskpuu tugijalad
    p = dict(LG.LEG_TYPES["puit_kandiline"]["params"]); p["H"] = zl - 120; p["a"] = 44
    m = LG.leg_mesh("puit_kandiline", p)
    for k, y in enumerate((t + L / 3, t + 2 * L / 3)):
        leg = Part(pr.new_id(), f"Keskpuu tugijalg {k + 1}")
        leg.kind, leg.source = "mesh", "leg"
        leg.mesh_v = np.round(m.vertices, 3).tolist(); leg.mesh_f = m.faces.tolist()
        leg.thickness = 44.0
        leg.material, leg.color = "Täispuit", "#e3c48f"
        leg.leg = dict(kind="puit_kandiline", params=p)
        leg.description = "Puit – kandiline sirge, 44×44"
        pr.add_part(leg)
        from .sample import place_min
        place_min(leg, x0 + t + W / 2 - 22, y - 22, 0)
        pr.note_assembled(leg.id)
    return [q for q in pr.parts if q.id not in made_before]
