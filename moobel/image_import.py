"""Pildist detaili tegemine: kontuuri tuvastus (OpenCV) ja Meshy AI pilt->3D."""
import base64
import json
import os
import time
import urllib.request

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except Exception:  # pragma: no cover
    cv2 = None
    HAS_CV2 = False


def load_image(path):
    data = np.fromfile(path, dtype=np.uint8)   # töötab ka täpitähtedega teedel (Windows)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Pilti ei õnnestunud avada")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        # läbipaistev taust -> valge
        alpha = img[:, :, 3:4].astype(float) / 255
        img = (img[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
    # suured pildid väiksemaks
    h, w = img.shape[:2]
    s = 1600 / max(h, w)
    if s < 1:
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return img


def make_mask(img, threshold=0, invert=False, grabcut=False, blur=5):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if blur > 1:
        gray = cv2.GaussianBlur(gray, (blur | 1, blur | 1), 0)
    if grabcut:
        h, w = img.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        rect = (int(w * 0.02), int(h * 0.02), int(w * 0.96), int(h * 0.96))
        bg, fg = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(img, mask, rect, bg, fg, 5, cv2.GC_INIT_WITH_RECT)
        th = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    elif threshold <= 0:
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, th = cv2.threshold(gray, int(threshold), 255, cv2.THRESH_BINARY_INV)
    if invert:
        th = 255 - th
    k = np.ones((5, 5), np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, k, iterations=2)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, k, iterations=1)
    return th


def extract_contours(mask, simplify_pct=0.5, keep_holes=True, min_hole_pct=0.3):
    """Tagastab (välimine kontuur Nx2, [sisemised kontuurid]) pikslites või (None, [])."""
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None, []
    hier = hier[0]
    outer_idx = [i for i in range(len(cnts)) if hier[i][3] == -1]
    if not outer_idx:
        return None, []
    oi = max(outer_idx, key=lambda i: cv2.contourArea(cnts[i]))
    area = cv2.contourArea(cnts[oi])

    def simp(c):
        eps = max(simplify_pct, 0.01) / 100.0 * cv2.arcLength(c, True)
        a = cv2.approxPolyDP(c, eps, True)
        return a.reshape(-1, 2).astype(float)

    outer = simp(cnts[oi])
    holes = []
    if keep_holes:
        for i in range(len(cnts)):
            if hier[i][3] == oi and cv2.contourArea(cnts[i]) > area * min_hole_pct / 100:
                h = simp(cnts[i])
                if len(h) >= 3:
                    holes.append(h)
    return outer, holes


def contours_to_mm(outer, holes, width_mm):
    """Pikslid -> mm, Y telg üles, vasak alumine nurk nullis."""
    xmin, xmax = outer[:, 0].min(), outer[:, 0].max()
    ymax = outer[:, 1].max()
    s = width_mm / max(xmax - xmin, 1e-6)

    def conv(c):
        return [[float((x - xmin) * s), float((ymax - y) * s)] for x, y in c]

    return conv(outer), [conv(h) for h in holes], s


# --------------------------------------------------------------------- Meshy AI
MESHY_BASE = "https://api.meshy.ai/openapi/v1/image-to-3d"


def _req(url, api_key, data=None, timeout=60):
    headers = {"Authorization": f"Bearer {api_key}"}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def meshy_image_to_3d(api_key, image_path, out_dir, progress=None, cancelled=None):
    """Saadab pildi Meshy teenusele ja laeb alla STL faili. Tagastab faili tee."""
    ext = os.path.splitext(image_path)[1].lower().strip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "png")
    with open(image_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    payload = {"image_url": f"data:image/{mime};base64,{b64}", "should_texture": False,
               "target_formats": ["stl", "glb"]}
    res = json.loads(_req(MESHY_BASE, api_key, payload))
    task = res.get("result")
    if not task:
        raise RuntimeError(f"Meshy vastus: {res}")
    t0 = time.time()
    while True:
        if cancelled and cancelled():
            raise RuntimeError("Katkestatud")
        st = json.loads(_req(f"{MESHY_BASE}/{task}", api_key))
        if progress:
            progress(int(st.get("progress", 0)), st.get("status", ""))
        if st.get("status") == "SUCCEEDED":
            urls = st.get("model_urls", {})
            url = urls.get("stl") or urls.get("glb") or urls.get("obj")
            if not url:
                raise RuntimeError("Meshy ei andnud mudeli faili")
            fmt = "stl" if urls.get("stl") == url else ("glb" if urls.get("glb") == url else "obj")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"meshy_{task}.{fmt}")
            with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as fh:
                fh.write(r.read())
            return path
        if st.get("status") in ("FAILED", "CANCELED"):
            raise RuntimeError(f"Meshy: {st.get('status')} {st.get('task_error')}")
        if time.time() - t0 > 900:
            raise RuntimeError("Meshy ei vastanud 15 minutiga")
        time.sleep(4)


def load_mesh_file(path, size_mm=None):
    """Laeb STL/OBJ/GLB faili üheks trimesh'iks, aseb nurga nulli ja skaleerib suurima mõõdu järgi."""
    import trimesh
    m = trimesh.load(path, force="mesh")
    if m is None or len(m.faces) == 0:
        raise ValueError("Failis pole 3D kujundit")
    m = m.copy()
    m.merge_vertices()
    # GLB on tavaliselt Y-üles -> keera Z-üles
    if path.lower().endswith((".glb", ".gltf")):
        from . import geom
        m.apply_transform(geom.make_transform(geom.rot_x(90), [0, 0, 0]))
    if size_mm:
        m.apply_scale(float(size_mm) / max(m.extents))
    m.apply_translation(-m.bounds[0])
    if len(m.faces) > 60000:
        try:
            m = m.simplify_quadric_decimation(face_count=60000)
        except Exception:
            pass
    return m
