"""Pinnaviimistlused: protseduursed puidu- ja betoonitekstuurid (ilma pildifailideta)."""
import numpy as np

FINISHES = {
    "": "Ühtlane värv",
    "tamm": "Tamm", "pahkel": "Pähkel", "kask": "Kask", "mand": "Mänd", "saar": "Saar",
    "valge_laige": "Valge läige", "must_matt": "Must matt", "betoon": "Betoon",
}
WOOD = {"tamm": ((196, 160, 110), (150, 110, 65)), "pahkel": ((120, 82, 52), (70, 45, 28)),
        "kask": ((232, 210, 170), (200, 170, 125)), "mand": ((228, 196, 140), (190, 140, 80)),
        "saar": ((215, 195, 160), (165, 140, 105))}
SOLID = {"valge_laige": ("#f4f4f2", 0.9), "must_matt": ("#1c1d1f", 0.0)}
_cache = {}


def _noise(n, scale, rng):
    small = rng.random((max(2, n // scale), max(2, n // scale)))
    from numpy import kron
    big = kron(small, np.ones((scale, scale)))[:n, :n]
    # pehmendus
    for _ in range(2):
        big = (big + np.roll(big, 1, 0) + np.roll(big, -1, 0) + np.roll(big, 1, 1) + np.roll(big, -1, 1)) / 5
    return big


def texture(name):
    import pyvista as pv
    if name in _cache:
        return _cache[name]
    n = 512
    rng = np.random.default_rng(abs(hash(name)) % 2 ** 32)
    y, x = np.mgrid[0:n, 0:n] / n
    if name in WOOD:
        light, dark = (np.array(c, float) for c in WOOD[name])
        warp = _noise(n, 32, rng) * 6 + _noise(n, 8, rng) * 1.5
        rings = np.sin((y * 18 + warp) * np.pi)          # süü kulgeb piki x-telge
        fine = _noise(n, 2, rng)
        t = np.clip(0.5 + 0.35 * rings + 0.25 * (fine - 0.5), 0, 1)[..., None]
        img = light * (1 - t) + dark * t
    else:   # betoon
        base = np.array([150, 150, 148], float)
        v = _noise(n, 16, rng) * 30 + _noise(n, 2, rng) * 25 - 25
        img = base + v[..., None]
        spots = rng.random((n, n)) > 0.996
        img[spots] *= 0.6
    tex = pv.Texture(np.clip(img, 0, 255).astype(np.uint8))
    tex.repeat = True
    tex.interpolate = True
    _cache[name] = tex
    return tex


def apply_tcoords(pvm, part):
    """Tekstuurikoordinaadid detaili lokaalse XY järgi (süü piki pikemat külge, kordus 700 mm)."""
    pts = np.asarray(pvm.points)
    if len(pts) == 0:
        return pvm
    ext = pts.max(axis=0) - pts.min(axis=0)
    ax = np.argsort(ext)[::-1]           # pikim, keskmine
    u = (pts[:, ax[0]] - pts[:, ax[0]].min()) / 700.0
    v = (pts[:, ax[1]] - pts[:, ax[1]].min()) / 700.0 + (pts[:, ax[2]] - pts[:, ax[2]].min()) / 700.0
    pvm = pvm.copy()
    pvm.active_texture_coordinates = np.column_stack([u, v]).astype(np.float32)
    return pvm
