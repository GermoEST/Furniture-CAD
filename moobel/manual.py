"""Detailide nimekiri ja monteerimisjuhend (pildid + HTML + PDF)."""
import csv
import html
import os

import numpy as np
import pyvista as pv

from . import scene, geom
from .fasteners import FASTENER_TYPES, hardware_summary

OLD_COLOR = "#d9d9d9"


# ------------------------------------------------------------------ nimekiri
def cut_list(project):
    """Rühmitab ühesuguse materjali ja mõõtudega detailid."""
    rows = {}
    for p in project.parts:
        if getattr(p, "role", None) in ("slide", "handle"):
            continue
        dims = tuple(p.dims())
        ec = p.edge_code() if hasattr(p, "edge_code") else ""
        key = (p.material, dims, p.kind, len(p.holes), ec)
        r = rows.setdefault(key, dict(names=[], material=p.material, dims=dims, kind=p.kind,
                                      cut=tuple(p.cut_dims()) if hasattr(p, "cut_dims") else dims, edges=ec,
                                      holes=len(p.holes), qty=0, desc=p.description, ids=[]))
        r["names"].append(p.name)
        r["ids"].append(p.id)
        r["qty"] += 1
    return list(rows.values())


def export_csv(project, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        from .i18n import T
        w.writerow([T(x) for x in ["Detail", "Kogus", "Materjal", "Pikkus mm", "Laius mm", "Paksus mm",
                                   "Lõikepikkus mm", "Lõikelaius mm", "Servakant", "Auke", "Märkus"]])
        for r in cut_list(project):
            L, W, Tk = r["dims"]
            cL, cW, _ = r["cut"]
            w.writerow([T(", ".join(r["names"])), r["qty"], T(r["material"]),
                        str(L).replace(".", ","), str(W).replace(".", ","), str(Tk).replace(".", ","),
                        str(cL).replace(".", ","), str(cW).replace(".", ","), r["edges"],
                        r["holes"], r["desc"]])
        w.writerow([])
        w.writerow([T("Kinnitus"), T("Kogus")])
        for k, n in hardware_summary(project).items():
            w.writerow([T(k), n])


# ------------------------------------------------------------------ pildid
_SHARED = None   # kui määratud, kasutatakse programmi enda 3D vaadet (töötab ka tarkvaralise OpenGL-iga)


def set_shared_plotter(pl):
    global _SHARED
    _SHARED = pl


def _done(pl):
    if pl is not _SHARED:
        pl.close()


def _plotter(size):
    if _SHARED is not None:
        pl = _SHARED
        pl.clear_actors()
        pl.set_background("white")
        try:
            pl.hide_axes()
        except Exception:
            pass
        return pl
    pl = pv.Plotter(off_screen=True, window_size=list(size), lighting="three lights")
    pl.set_background("white")
    pl.enable_anti_aliasing("ssaa") if hasattr(pl, "enable_anti_aliasing") else None
    return pl


def render_overview(project, path, size=(1100, 760), labels=True, explode=0.0):
    pl = _plotter(size)
    offs = scene.explode_offsets(project, explode)
    for p in project.parts:
        scene.add_part(pl, p, offset=offs.get(p.id), pickable=False)
    if labels and project.parts:
        pts, names = [], []
        for p in project.parts:
            lo, hi = p.world_bounds()
            pts.append((lo + hi) / 2 + offs.get(p.id, 0))
            from .i18n import T
            names.append(T(p.name))
        pl.add_point_labels(np.array(pts), names, font_size=14, point_size=1, shape_opacity=0.75,
                            always_visible=True, show_points=False)
    scene.set_iso_camera(pl, project, 1.05)
    pl.screenshot(path)
    _done(pl)


def render_part(part, path, size=(420, 300)):
    pl = _plotter(size)
    scene.add_part(pl, part, pickable=False)
    lo, hi = part.world_bounds()
    c = (lo + hi) / 2
    L = float(np.linalg.norm(hi - lo)) or 100
    # vaata detaili suurima pinna poolt (paksuse telje suunast, veidi viltu)
    n = part.thickness_axis_world() if part.kind == "plate" else np.array([0, -1, 0.6])
    side = geom.unit(np.cross(n, [0, 0, 1]) if abs(n[2]) < 0.9 else np.cross(n, [1, 0, 0]))
    eye = c + geom.unit(n * 1.0 + side * 0.35 + np.array([0, 0, 0.25])) * L * 1.6
    up = [0, 0, 1] if abs(n[2]) < 0.9 else [0, 1, 0]
    pl.camera_position = [tuple(eye), tuple(c), tuple(up)]
    pl.reset_camera()
    pl.screenshot(path)
    _done(pl)


def _step_move(project, step, placed):
    """Vektor, kui palju uut detaili juhendi pildil eemale nihutada (näitab, kuhu see läheb)."""
    vecs = []
    for fid in step.fastener_ids:
        f = project.fastener(fid)
        if not f or not f.axis:
            continue
        A = project.part(f.a_id)
        d = A.R @ np.asarray(f.axis[1])
        if f.b_id in step.part_ids and f.a_id in placed:
            vecs.append(d)
        elif f.a_id in step.part_ids and f.b_id in placed:
            vecs.append(-d)
    if not vecs:
        return None
    v = np.mean(vecs, axis=0)
    if np.linalg.norm(v) < 1e-6:
        return None
    lo, hi = project.bounds()
    dist = max(80.0, 0.12 * float(np.linalg.norm(hi - lo)))
    return geom.unit(v) * dist


def _group_pull(project, step):
    """Sahtli sammul: tõmba sahtel (v.a siinid) välja käepideme suunas."""
    groups = {getattr(project.part(pid), "group", "") for pid in step.part_ids}
    if len(groups) != 1 or not next(iter(groups)):
        return None
    for pid in step.part_ids:
        p = project.part(pid)
        if getattr(p, "pull", None) or getattr(p, "role", None) == "handle":
            out = np.asarray(p.pull, float) if getattr(p, "pull", None) else p.R @ np.array([0, 1.0, 0])
            depth = max((q.world_bounds()[1] - q.world_bounds()[0]).max() for q in
                        (project.part(x) for x in step.part_ids) if getattr(q, "role", None) == "slide") \
                if any(getattr(project.part(x), "role", None) == "slide" for x in step.part_ids) else 300
            return geom.unit(out) * min(0.65 * depth, 400)
    return None


def render_step(project, step, placed, path, size=(1000, 700)):
    pl = _plotter(size)
    pull = _group_pull(project, step)
    move = None if pull is not None else _step_move(project, step, placed)
    new = set(step.part_ids)

    def off_for(p):
        if pull is not None:
            return None if getattr(p, "role", None) == "slide" else pull
        return move
    for p in project.parts:
        if p.id in placed and p.id not in new:
            scene.add_part(pl, p, color=OLD_COLOR, pickable=False)
    for p in project.parts:
        if p.id in new:
            scene.add_part(pl, p, opacity=0.75 if step.fastener_ids else 1.0,
                           offset=off_for(p), pickable=False)
    for fid in step.fastener_ids:
        f = project.fastener(fid)
        if f is None:
            continue
        off = move if (move is not None and f.a_id in new) else None
        scene.add_fastener(pl, project, f, offset=off)
    arrow_v = pull if pull is not None else move
    labels, pts = [], []
    group = getattr(project.part(step.part_ids[0]), "group", "") if step.part_ids else ""
    if group:
        los, his = zip(*[project.part(pid).world_bounds() for pid in new])
        c = (np.min(los, axis=0) + np.max(his, axis=0)) / 2
        if arrow_v is not None:
            L = float(np.linalg.norm(arrow_v))
            pl.add_mesh(pv.Arrow(start=c + arrow_v, direction=-arrow_v, scale=L * 0.9, tip_length=0.3,
                                 tip_radius=0.12, shaft_radius=0.04), color="#e0312b", pickable=False)
        pts.append(c + (arrow_v if arrow_v is not None else 0))
        from .i18n import T
        labels.append(T(group))
    else:
        for pid in new:
            p = project.part(pid)
            lo, hi = p.world_bounds()
            c = (lo + hi) / 2
            if move is not None:
                L = float(np.linalg.norm(move))
                pl.add_mesh(pv.Arrow(start=c + move, direction=-move, scale=L * 0.9, tip_length=0.3,
                                     tip_radius=0.12, shaft_radius=0.04), color="#e0312b", pickable=False)
            pts.append(c + (move if move is not None else 0))
            from .i18n import T
            labels.append(T(p.name))
    if pts:
        pl.add_point_labels(np.array(pts), labels, font_size=16, point_size=1, show_points=False,
                            shape_color="#fff3c4", always_visible=True)
    scene.set_iso_camera(pl, project, 1.0)
    pl.screenshot(path)
    _done(pl)


# ------------------------------------------------------------------ juhend
def build_manual(project, out_dir, progress=None):
    """Teeb pildid ja HTML-i. Tagastab (html_tee, pildid dict, html_tekst)."""
    os.makedirs(out_dir, exist_ok=True)
    covered = {pid for st in project.steps for pid in st.part_ids}
    if not project.steps or ({p.id for p in project.parts} - covered):
        project.auto_steps()
    imgs = {}
    total = 2 + len(project.parts) + len(project.steps)
    k = 0

    def tick(msg):
        nonlocal k
        k += 1
        if progress:
            progress(int(k * 100 / total), msg)

    try:
        from .logo import logo_pixmap
        lp = os.path.join(out_dir, "logo.png")
        logo_pixmap(900, 300, False).save(lp)
        imgs["logo.png"] = lp
    except Exception:
        pass
    p_over = os.path.join(out_dir, "ylevaade.png")
    render_overview(project, p_over)
    imgs["ylevaade.png"] = p_over
    tick("ülevaade")
    p_expl = os.path.join(out_dir, "lahti.png")
    render_overview(project, p_expl, labels=True, explode=0.6)
    imgs["lahti.png"] = p_expl
    tick("lahtivõetud vaade")
    for p in project.parts:
        if getattr(p, "role", None) in ("slide", "handle"):
            continue
        fn = f"detail_{p.id}.png"
        render_part(p, os.path.join(out_dir, fn))
        imgs[fn] = os.path.join(out_dir, fn)
        tick(p.name)
    placed = set()
    for i, s in enumerate(project.steps):
        fn = f"samm_{i + 1}.png"
        render_step(project, s, placed, os.path.join(out_dir, fn))
        imgs[fn] = os.path.join(out_dir, fn)
        placed.update(s.part_ids)
        tick(f"samm {i + 1}")

    E = html.escape
    h = []
    h.append(f"<html><head><meta charset='utf-8'><title>{E(project.name)} – monteerimisjuhend</title>"
             "<style>body{font-family:Segoe UI,Arial,sans-serif;color:#222;max-width:900px;margin:auto}"
             "h1{font-size:26pt;margin-bottom:4px}h2{font-size:16pt;border-bottom:2px solid #333;"
             "padding-bottom:3px;margin-top:18px}table{border-collapse:collapse;width:100%}"
             "td,th{border:1px solid #999;padding:4px 6px;font-size:10pt}th{background:#eee}"
             ".note{font-size:11pt}.hw{font-size:11pt;font-weight:bold}</style></head><body>")
    if "logo.png" in imgs:
        h.append("<p align='right'><img src='logo.png' width='210'></p>")
    h.append(f"<h1>{E(project.name)}</h1><p>Monteerimisjuhend</p>")
    h.append("<p><img src='ylevaade.png' width='650'></p>")
    h.append("<h2>Detailid</h2><table><tr><th>#</th><th>Detail</th><th>Kogus</th><th>Materjal</th>"
             "<th>Mõõdud (mm)</th><th>Lõikemõõt</th><th>Servakant</th><th>Auke</th></tr>")
    for i, r in enumerate(cut_list(project), 1):
        L, W, Tk = r["dims"]
        h.append(f"<tr><td>{i}</td><td>{E(', '.join(r['names']))}</td><td>{r['qty']}</td>"
                 f"<td>{E(r['material'])}</td><td>{L:g} × {W:g} × {Tk:g}</td>"
                 f"<td>{r['cut'][0]:g} × {r['cut'][1]:g}</td><td>{E(r['edges'])}</td><td>{r['holes']}</td></tr>")
    h.append("</table>")
    hs = hardware_summary(project)
    if hs:
        h.append("<h2>Kinnitused</h2><table><tr><th>Kinnitus</th><th>Kogus</th></tr>")
        for kname, n in hs.items():
            h.append(f"<tr><td>{E(kname)}</td><td>{n}</td></tr>")
        h.append("</table>")
    h.append("<div style='page-break-before:always'></div><h2>Detailide ülevaade</h2><table>")
    plist = [p for p in project.parts if getattr(p, "role", None) not in ("slide", "handle")]
    for i in range(0, len(plist), 2):
        h.append("<tr>")
        for p in plist[i:i + 2]:
            L, W, Tk = p.dims()
            h.append(f"<td align='center'><img src='detail_{p.id}.png' width='300'><br><b>{E(p.name)}</b>"
                     f"<br>{L:g} × {W:g} × {Tk:g} mm, {len(p.holes)} auku"
                     + (f"<br><i>{E(p.description)}</i>" if p.description else "") + "</td>")
        h.append("</tr>")
    h.append("</table>")
    h.append("<p><img src='lahti.png' width='600'></p>")
    for i, s in enumerate(project.steps):
        h.append(f"<div style='page-break-before:always'></div><h2>Samm {i + 1}: {E(s.title)}</h2>")
        if s.note:
            h.append(f"<p class='note'>{E(s.note)}</p>")
        cnt = {}
        for fid in s.fastener_ids:
            f = project.fastener(fid)
            if f:
                nm = FASTENER_TYPES.get(f.ftype, {}).get("short", f.ftype)
                cnt[nm] = cnt.get(nm, 0) + 1
        if cnt:
            h.append("<p class='hw'>" + " &nbsp; ".join(f"{n}× {E(k2)}" for k2, n in cnt.items()) + "</p>")
        h.append(f"<p><img src='samm_{i + 1}.png' width='650'></p>")
    h.append("<p><br>Valmis!</p></body></html>")
    from .i18n import T
    text = T("\n".join(h))
    path = os.path.join(out_dir, "juhend.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path, imgs, text


def html_to_pdf(html_text, images, pdf_path):
    """Teeb HTML-ist PDF faili Qt abil (vajab töötavat QApplication'it)."""
    from PySide6.QtGui import QTextDocument, QPdfWriter, QPageSize, QImage, QPageLayout
    from PySide6.QtCore import QUrl, QMarginsF
    doc = QTextDocument()
    for name, p in images.items():
        doc.addResource(QTextDocument.ImageResource, QUrl(name), QImage(p))
    doc.setHtml(html_text)
    w = QPdfWriter(pdf_path)
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
    w.setResolution(96)
    doc.setPageSize(w.pageLayout().paintRectPixels(96).size().toSizeF())
    doc.print_(w)
    return pdf_path
