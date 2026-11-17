"""Lisaaknad: uksed, riiulid, mallid, lõikeplaan, kontroll, esitlus."""
import numpy as np
from PySide6.QtCore import Qt, QRectF, QMarginsF
from PySide6.QtGui import QPainter, QColor, QFont, QImage, QPixmap, QPdfWriter, QPageSize, QPageLayout
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, QCheckBox, QDialogButtonBox, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QScrollArea, QWidget, QLineEdit,
    QColorDialog)

from .i18n import T
from . import drawers as DR, builders as BU, handles as H
from .dialogs import spin, material_combo


def _color_btn(initial):
    b = QPushButton()
    b._c = initial

    def setc(c):
        b._c = c
        b.setStyleSheet(f"background-color:{c};border:1px solid #777;min-height:20px")

    def pick():
        c = QColorDialog.getColor(QColor(b._c), b)
        if c.isValid():
            setc(c.name())
    setc(initial)
    b.clicked.connect(pick)
    return b


def _handle_combo(with_none=True):
    c = QComboBox()
    for k, n in H.STYLES.items():
        c.addItem(n, k)
    if with_none:
        c.addItem("Puudub (vajutusavaja)", "puudub")
    return c


def _finish_combo():
    c = QComboBox()
    for k in H.FINISHES:
        c.addItem(k, k)
    return c


def _front_combo(info):
    c = QComboBox()
    jn = "XYZ"[info["j"]]
    c.addItem(f"{jn} väiksem pool (−{jn})", "min")
    c.addItem(f"{jn} suurem pool (+{jn})", "max")
    return c


# ====================================================================== uksed
class DoorDialog(QDialog):
    def __init__(self, project, A, B, parent=None):
        super().__init__(parent)
        self.info = inf = DR.analyse(A, B)
        self.setWindowTitle("Lisa uksed")
        f = QFormLayout(self)
        f.addRow(QLabel(f"Ava '{inf['lo_side'].name}' ja '{inf['hi_side'].name}' vahel: laius <b>{inf['W']:.0f} mm</b>, "
                        f"sügavus {inf['D']:.0f} mm, kõrgus {inf['z0']:.0f}…{inf['z1']:.0f} mm"))
        self.count = QComboBox(); self.count.addItem("1 uks", 1); self.count.addItem("2 ust (paariuks)", 2)
        if inf["W"] > 600:
            self.count.setCurrentIndex(1)
        self.zb = spin(round(inf["z0"], 1), -5000, 10000)
        self.zt = spin(round(inf["z1"], 1), -5000, 10000)
        self.mode = QComboBox(); self.mode.addItem("Peale (katab korpuse servad)", "peale")
        self.mode.addItem("Sisse (korpuse sisse, tasa)", "sisse")
        self.front = _front_combo(inf)
        self.hinge = QComboBox(); self.hinge.addItem("Vasakul", "vasak"); self.hinge.addItem("Paremal", "parem")
        self.glass = QCheckBox("Klaasuks (5 mm klaas, klaasihinged)")
        self.mat = material_combo("MDF")
        self.color = _color_btn("#f2f0eb")
        self.handle = _handle_combo()
        self.finish = _finish_combo()
        for lab, w in (("Uste arv", self.count), ("Ava alumine serv (Z)", self.zb), ("Ava ülemine serv (Z)", self.zt),
                       ("Paigaldus", self.mode), ("Mööbli esikülg", self.front), ("Hinged (1 uks)", self.hinge),
                       ("", self.glass), ("Materjal", self.mat), ("Värv", self.color), ("Käepide", self.handle),
                       ("Käepideme viimistlus", self.finish)):
            f.addRow(lab, w)
        f.addRow(QLabel("Hingede arv valitakse ukse kõrguse järgi (2–5). Kausi ava Ø35 × 12 mm, "
                        "paigaldusplaadi augud 37 mm esiservast."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)

    def options(self):
        return dict(count=self.count.currentData(), z_bottom=self.zb.value(), z_top=self.zt.value(),
                    mode=self.mode.currentData(), front_side=self.front.currentData(),
                    hinge_side=self.hinge.currentData(), glass=self.glass.isChecked(), t=18,
                    material=self.mat.currentText(), color=self.color._c, handle=self.handle.currentData(),
                    finish=self.finish.currentData())


# ====================================================================== riiulid
class ShelfDialog(QDialog):
    def __init__(self, project, A, B, parent=None):
        super().__init__(parent)
        self.info = inf = DR.analyse(A, B)
        self.setWindowTitle("Lisa riiulid")
        f = QFormLayout(self)
        f.addRow(QLabel(f"Laius {inf['W']:.0f} mm, sügavus {inf['D']:.0f} mm"))
        self.count = QSpinBox(); self.count.setRange(1, 20); self.count.setValue(3)
        self.zb = spin(round(inf["z0"], 1), -5000, 10000)
        self.zt = spin(round(inf["z1"], 1), -5000, 10000)
        self.front = _front_combo(inf)
        self.t = spin(18, 6, 60)
        self.setback = spin(20, 0, 300)
        self.holes = QCheckBox("Puuri 32 mm süsteemi augud (reguleeritavad riiulid)"); self.holes.setChecked(True)
        self.mat = material_combo()
        self.color = _color_btn("#d9b98c")
        for lab, w in (("Riiulite arv", self.count), ("Ala alumine serv (Z)", self.zb), ("Ala ülemine serv (Z)", self.zt),
                       ("Mööbli esikülg", self.front), ("Paksus", self.t), ("Tagasi esiservast", self.setback),
                       ("", self.holes), ("Materjal", self.mat), ("Värv", self.color)):
            f.addRow(lab, w)
        f.addRow(QLabel("Augud Ø5 × 10 mm, 37 mm esi- ja tagaservast, iga 32 mm järel. Iga riiul: 4 riiulikandurit."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)

    def options(self):
        return dict(count=self.count.value(), z_bottom=self.zb.value(), z_top=self.zt.value(),
                    front_side=self.front.currentData(), t=self.t.value(), setback=self.setback.value(),
                    holes=self.holes.isChecked(), material=self.mat.currentText(), color=self.color._c)


# ====================================================================== mallid
class TemplateDialog(QDialog):
    LABELS = dict(W="Laius", D="Sügavus", H="Kõrgus", t="Plaadi paksus", shelves="Riiuleid", doors="Uksi",
                  drawers="Sahtleid", plinth="Sokli kõrgus")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mallid")
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.kind = QComboBox()
        for k, n in BU.TEMPLATES.items():
            self.kind.addItem(n, k)
        f.addRow("Mööbel", self.kind)
        v.addLayout(f)
        self.form = QFormLayout()
        v.addLayout(self.form)
        self.ft = QComboBox()
        for k, n in (("konfirmaat", "Konfirmaat (euro-kruvi) 7×50"), ("minifix", "Minifix 15 (veerandpöörde ekstsentrik)"),
                     ("tuubel", "Puittüübel 8×35"), ("ristmutter", "Mööblipolt + ristmutter (pikk vastasmutter)")):
            self.ft.addItem(n, k)
        self.color = _color_btn("#d9b98c")
        self.fcolor = _color_btn("#f2f0eb")
        self.handle = _handle_combo()
        f2 = QFormLayout()
        f2.addRow("Korpuse kinnitus", self.ft)
        f2.addRow("Korpuse värv", self.color)
        f2.addRow("Uste/esipaneelide värv", self.fcolor)
        f2.addRow("Käepide", self.handle)
        self.back = QCheckBox("Tagasein (HDF)"); f2.addRow("", self.back)
        v.addLayout(f2)
        v.addWidget(QLabel("Pärast loomist saad iga detaili, kinnitust ja mõõtu muuta nagu tavaliselt."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.fields = {}
        self.kind.currentIndexChanged.connect(self.rebuild)
        self.rebuild()

    def rebuild(self, *a):
        k = self.kind.currentData()
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = {}
        d = BU.TPL_DEFAULTS[k]
        for name in ("W", "D", "H", "t", "plinth", "shelves", "doors", "drawers"):
            if k == "voodi" and name in ("plinth", "shelves", "doors", "drawers"):
                continue
            if name in ("shelves", "doors", "drawers"):
                w = QSpinBox(); w.setRange(0, 12 if name != "doors" else 2); w.setValue(int(d[name]))
            else:
                w = spin(float(d[name]), 0, 5000)
            lab = self.LABELS[name]
            if k == "voodi":
                lab = {"W": "Madratsi laius", "D": "Madratsi pikkus", "H": "Raami kõrgus"}.get(name, lab)
            self.form.addRow(lab, w)
            self.fields[name] = w
        self.back.setChecked(bool(d.get("back", True)))
        self.back.setEnabled(k != "voodi")

    def options(self):
        o = {k: (w.value()) for k, w in self.fields.items()}
        o.update(back=self.back.isChecked(), ftype=self.ft.currentData(), color=self.color._c,
                 front_color=self.fcolor._c, handle=self.handle.currentData(), finish="Must")
        return self.kind.currentData(), o


# ====================================================================== lõikeplaan
class CutPlanDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        from . import cutplan as CP, prices as PR
        self.CP, self.project = CP, project
        self.st = PR.load()
        self.setWindowTitle("Lõikeplaan")
        self.resize(1200, 800)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        self.grain = QCheckBox("Arvesta süüsuunda (ära pööra detaile)")
        self.grain.toggled.connect(self.refresh)
        row.addWidget(self.grain)
        row.addWidget(QLabel(f"   Saelõige {CP.KERF:g} mm, servast äralõige {CP.TRIM:g} mm. Plaadi mõõdu saad muuta aknas 'Maksumus'."))
        row.addStretch()
        b = QPushButton("💾 Salvesta PDF"); b.clicked.connect(self.save_pdf); row.addWidget(b)
        v.addLayout(row)
        self.summary = QLabel(); self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        self.inner = QWidget(); self.vl = QVBoxLayout(self.inner)
        sc.setWidget(self.inner)
        v.addWidget(sc, 1)
        self.refresh()

    def _pages(self):
        out = []
        for (mat, Tk), g in self.plan.items():
            for i, s in enumerate(g["sheets"]):
                out.append((f"{T(mat)} {Tk:g} mm – {T('plaat')} {i + 1}/{len(g['sheets'])}", g["sheet"], s))
        return out

    def refresh(self, *a):
        self.plan = self.CP.plan(self.project, self.st, self.grain.isChecked())
        while self.vl.count():
            w = self.vl.takeAt(0).widget()
            if w:
                w.deleteLater()
        lines = []
        for (mat, Tk), g in self.plan.items():
            used = sum(sh.used_area() for sh in g["sheets"]) / 1e6
            tot = len(g["sheets"]) * g["sheet"][0] * g["sheet"][1] / 1e6
            lines.append(f"<b>{T(mat)} {Tk:g} mm</b>: {len(g['sheets'])} × {g['sheet'][0]:g}×{g['sheet'][1]:g} – "
                         f"{T('kasutus')} {used / max(tot, 1e-9) * 100:.0f}%"
                         + (f" <span style='color:#b00'>⚠ {T('ei mahu')}: {', '.join(T(n) for n in g['too_big'])}</span>"
                            if g["too_big"] else ""))
        self.summary.setText("<br>".join(lines) or T("Plaate pole."))
        for title, size, s in self._pages():
            img = QImage(1100, int(1100 * size[1] / size[0]) + 70, QImage.Format_RGB32)
            img.fill(QColor("white"))
            p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
            self.CP.draw_sheet(p, QRectF(0, 0, img.width(), img.height()), size, s, title, T)
            p.end()
            lab = QLabel(); lab.setPixmap(QPixmap.fromImage(img))
            self.vl.addWidget(lab)
        self.vl.addStretch()

    def save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, T("Salvesta PDF"), f"{self.project.name}_loikeplaan.pdf", "PDF (*.pdf)")
        if not path:
            return
        pw = QPdfWriter(path)
        pw.setPageSize(QPageSize(QPageSize.A4)); pw.setPageOrientation(QPageLayout.Landscape)
        pw.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Millimeter); pw.setResolution(150)
        p = QPainter(pw)
        r = pw.pageLayout().paintRectPixels(150)
        for i, (title, size, s) in enumerate(self._pages()):
            if i:
                pw.newPage()
            self.CP.draw_sheet(p, QRectF(0, 0, r.width(), r.height()), size, s, f"{self.project.name} – {title}", T)
        p.end()
        QMessageBox.information(self, T("Lõikeplaan"), T("Salvestatud: ") + path)


# ====================================================================== kontroll
def check_project(project):
    """Tagastab [(tekst, [detailide id])]."""
    import trimesh
    from shapely.geometry import Point
    from . import geom
    issues = []
    parts = [p for p in project.parts if getattr(p, "role", None) != "handle"]
    bounds = {p.id: p.world_bounds() for p in parts}
    mans = {}

    def man(p):
        if p.id not in mans:
            m = p.world_body_mesh()
            try:
                mans[p.id] = geom._to_manifold(m)
            except Exception:
                mans[p.id] = None
        return mans[p.id]
    for i, a in enumerate(parts):
        alo, ahi = bounds[a.id]
        for b in parts[i + 1:]:
            blo, bhi = bounds[b.id]
            ov = np.minimum(ahi, bhi) - np.maximum(alo, blo)
            if (ov <= 0.5).any():
                continue
            ma, mb = man(a), man(b)
            vol = None
            if ma is not None and mb is not None:
                try:
                    vol = (ma ^ mb).volume()
                except Exception:
                    vol = None
            if vol is None:
                vol = float(np.prod(ov))
            if vol > 200:
                issues.append((f"Detailid lähevad üksteise sisse: '{a.name}' ja '{b.name}' (~{vol / 1000:.1f} cm³)",
                               [a.id, b.id]))
    for p in project.parts:
        if p.kind != "plate" or not p.holes:
            continue
        poly = geom.make_polygon(p.outline, p.inner)
        for h in p.holes:
            o, d = np.asarray(h.origin), np.asarray(h.direction)
            if abs(d[2]) > 0.9:
                dist = poly.exterior.distance(Point(o[0], o[1]))
                if not poly.contains(Point(o[0], o[1])):
                    issues.append((f"'{p.name}': ava ({h.label}) on plaadist väljas", [p.id]))
                elif dist < h.diameter / 2 + 3:
                    issues.append((f"'{p.name}': ava ({h.label} Ø{h.diameter:g}) on serva lähedal ({dist:.1f} mm)",
                                   [p.id]))
                if p.thickness - 1.0 < h.depth < p.thickness - 0.05:
                    issues.append((f"'{p.name}': ava ({h.label}) jätab põhja alla 1 mm – võib läbi minna", [p.id]))
            else:
                end = o + d * h.depth
                if not poly.buffer(-h.diameter / 2 + 0.5).contains(Point(end[0], end[1])):
                    issues.append((f"'{p.name}': servaauk ({h.label}) väljub plaadist", [p.id]))
                zc = o[2]
                if zc - h.diameter / 2 < 1.5 or zc + h.diameter / 2 > p.thickness - 1.5:
                    issues.append((f"'{p.name}': servaauk ({h.label} Ø{h.diameter:g}) on plaadi pinna lähedal",
                                   [p.id]))
    return issues


class CheckDialog(QDialog):
    def __init__(self, project, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.setWindowTitle("Kontroll")
        self.resize(760, 460)
        v = QVBoxLayout(self)
        issues = check_project(project)
        if not issues:
            v.addWidget(QLabel("✔ Probleeme ei leitud: detailid ei lähe üksteise sisse ja augud on korras."))
        else:
            v.addWidget(QLabel(f"⚠ Leitud {len(issues)} kohta. Topeltklikk valib detailid 3D vaates."))
        self.lst = QListWidget()
        for txt, ids in issues:
            it = QListWidgetItem(T(txt)); it.setData(Qt.UserRole, ids)
            self.lst.addItem(it)
        self.lst.itemDoubleClicked.connect(self.pick)
        v.addWidget(self.lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        v.addWidget(bb)

    def pick(self, it):
        ids = it.data(Qt.UserRole)
        self.win.selected = ids[0]
        self.win.sel = set(ids) if len(ids) > 1 else set()
        self.win.refresh_list(); self.win.load_props(); self.win.update_highlight()


# ====================================================================== esitlus
class PresentDialog(QDialog):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.setWindowTitle("Esitluspilt")
        f = QFormLayout(self)
        self.title = QLineEdit(win.project.name)
        self.sub = QLineEdit("")
        self.view = QComboBox()
        for k, n in (("current", "Praegune vaade"), ("iso", "Isomeetriline"), ("front", "Eest"), ("top", "Pealt")):
            self.view.addItem(n, k)
        self.dims = QCheckBox("Näita üldmõõte"); self.dims.setChecked(True)
        self.legend = QCheckBox("Lisa materjalide kokkuvõte"); self.legend.setChecked(True)
        self.fmt = QComboBox(); self.fmt.addItem("PNG pilt", "png"); self.fmt.addItem("PDF (A4)", "pdf")
        for lab, w in (("Pealkiri", self.title), ("Alapealkiri", self.sub), ("Vaade", self.view), ("", self.dims),
                       ("", self.legend), ("Fail", self.fmt)):
            f.addRow(lab, w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)

    def make(self):
        w = self.win
        ext = self.fmt.currentData()
        path, _ = QFileDialog.getSaveFileName(w, T("Salvesta esitlus"), f"{w.project.name}.{ext}",
                                              "PNG (*.png)" if ext == "png" else "PDF (*.pdf)")
        if not path:
            return None
        import os, tempfile
        cam = w.plotter.camera_position
        tmp = os.path.join(tempfile.gettempdir(), "moobel_esitlus.png")
        pl = w.plotter
        old_sel, old_multi = w.selected, set(w.sel)
        w.selected, w.sel = None, set()
        w.update_highlight(render=False)
        try:
            if self.view.currentData() != "current":
                w.view(self.view.currentData())
            pl.set_background("white")
            try:
                pl.hide_axes()
            except Exception:
                pass
            dim_actors = w.add_overall_dims(force=True) if self.dims.isChecked() else []
            if self.view.currentData() != "current":
                pl.reset_camera(); pl.camera.zoom(1.15)
            pl.render()
            pl.screenshot(tmp)
            for a in dim_actors:
                pl.remove_actor(a, render=False)
        finally:
            w.selected, w.sel = old_sel, old_multi
            w._restore_view(cam)
        shot = QImage(tmp)
        lo, hi = w.project.bounds()
        size = hi - lo
        lines = [f"{T('Üldmõõdud')}: {size[0]:.0f} × {size[1]:.0f} × {size[2]:.0f} mm"]
        if self.legend.isChecked():
            mats = {}
            for p in w.project.parts:
                if getattr(p, "role", None) in ("slide", "handle"):
                    continue
                key = f"{T(p.material)} {p.dims()[2]:g} mm"
                mats[key] = mats.get(key, 0) + 1
            lines.append(", ".join(f"{k} ({n})" for k, n in mats.items()))
        from .logo import logo_pixmap
        logo = logo_pixmap(600, 200, False).toImage()

        def compose(p, Wd, Hd):
            p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.fillRect(QRectF(0, 0, Wd, Hd), QColor("white"))
            head = Hd * 0.12
            ft = QFont("Segoe UI"); ft.setPixelSize(int(head * 0.42)); ft.setBold(True); p.setFont(ft)
            p.setPen(QColor("#111"))
            p.drawText(QRectF(Wd * 0.04, Hd * 0.02, Wd * 0.7, head * 0.6), Qt.AlignLeft | Qt.AlignVCenter, self.title.text())
            fs = QFont("Segoe UI"); fs.setPixelSize(int(head * 0.2)); p.setFont(fs); p.setPen(QColor("#555"))
            p.drawText(QRectF(Wd * 0.04, Hd * 0.02 + head * 0.6, Wd * 0.7, head * 0.35), Qt.AlignLeft | Qt.AlignVCenter,
                       self.sub.text())
            lw = Wd * 0.2
            p.drawImage(QRectF(Wd * 0.96 - lw, Hd * 0.025, lw, lw / 3), logo)
            foot = Hd * 0.1
            area = QRectF(Wd * 0.03, Hd * 0.02 + head, Wd * 0.94, Hd - head - foot - Hd * 0.03)
            s = min(area.width() / shot.width(), area.height() / shot.height())
            tw, th = shot.width() * s, shot.height() * s
            p.drawImage(QRectF(area.x() + (area.width() - tw) / 2, area.y() + (area.height() - th) / 2, tw, th), shot)
            p.setPen(QColor("#ddd")); p.drawLine(int(Wd * 0.04), int(Hd - foot), int(Wd * 0.96), int(Hd - foot))
            fs.setPixelSize(int(foot * 0.22)); p.setFont(fs); p.setPen(QColor("#333"))
            p.drawText(QRectF(Wd * 0.04, Hd - foot + 4, Wd * 0.92, foot - 8), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
                       "\n".join(lines))
        if ext == "png":
            img = QImage(3000, 2000, QImage.Format_RGB32)
            p = QPainter(img); compose(p, img.width(), img.height()); p.end()
            img.save(path)
        else:
            pw = QPdfWriter(path)
            pw.setPageSize(QPageSize(QPageSize.A4)); pw.setPageOrientation(QPageLayout.Landscape)
            pw.setPageMargins(QMarginsF(8, 8, 8, 8), QPageLayout.Millimeter); pw.setResolution(200)
            p = QPainter(pw)
            r = pw.pageLayout().paintRectPixels(200)
            compose(p, r.width(), r.height()); p.end()
        return path
