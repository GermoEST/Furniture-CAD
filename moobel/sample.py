"""Näidisprojekt: lihtne kirjutuslaud (1200 × 600 × 750 mm)."""
import numpy as np
from .model import Project, Part, PALETTE
from . import geom
from .fasteners import add_fastener


def place_min(part, xmin, ymin, zmin):
    lo, _ = part.world_bounds()
    part.position = (np.asarray(part.position) + np.array([xmin, ymin, zmin]) - lo).tolist()


def plate(pr, name, w, h, t, color, R=None, r=0.0):
    p = Part(pr.new_id(), name)
    p.thickness = t
    p.set_rect(w, h, r)
    p.color = color
    if R is not None:
        p.R = R
    pr.add_part(p)
    return p


def desk():
    pr = Project()
    from .i18n import T as _tr
    pr.name = _tr("Kirjutuslaud")
    T = 18.0
    W, D, H = 1200.0, 600.0, 750.0
    top = plate(pr, "Lauaplaat", W, D, T, PALETTE[0], r=0)
    place_min(top, 0, 0, H - T)
    side_h = H - T
    # külg: kontuur (sügavus × kõrgus), paksus X suunas
    R_side = geom.rot_z(90) @ geom.rot_x(90)   # lokaalne X->Y, Y->Z, Z->X
    sl = plate(pr, "Külg vasak", D, side_h, T, PALETTE[1], R_side)
    place_min(sl, 40, 0, 0)
    sr = plate(pr, "Külg parem", D, side_h, T, PALETTE[1], R_side)
    place_min(sr, W - 40 - T, 0, 0)
    # tagapaneel (põlvekate) sügavus Y suunas
    back_w = (W - 80 - 2 * T)
    bk = plate(pr, "Tagapaneel", back_w, 350, T, PALETTE[2], geom.rot_x(90))
    place_min(bk, 40 + T, D - 60 - T, side_h - 350)
    pr.note_assembled(top.id, sl.id, sr.id, bk.id)

    # kinnitused: lauaplaat -> küljed minifixiga (klikk lauaplaadi pealispinnal)
    for side in (sl, sr):
        lo, hi = side.world_bounds()
        x = (lo[0] + hi[0]) / 2
        for y in (80, D - 80):
            add_fastener(pr, "minifix", {}, top, np.array([x, y, H]), np.array([0, 0, 1.0]))
    # küljed -> tagapaneel ristmutriga (klikk külje välispinnal)
    for side, nx in ((sl, -1.0), (sr, 1.0)):
        lo, hi = side.world_bounds()
        xo = lo[0] if nx < 0 else hi[0]
        blo, bhi = bk.world_bounds()
        y = (blo[1] + bhi[1]) / 2
        for z in (blo[2] + 70, bhi[2] - 70):
            add_fastener(pr, "ristmutter", {"polt_L": 70}, side, np.array([xo, y, z]),
                         np.array([nx, 0, 0]))
    # tüüblid lauaplaadi ja tagapaneeli vahel
    blo, bhi = bk.world_bounds()
    y = (blo[1] + bhi[1]) / 2
    for x in (300, 600, 900):
        add_fastener(pr, "tuubel", {}, top, np.array([x, y, H]), np.array([0, 0, 1.0]))
    pr.auto_steps()
    return pr
