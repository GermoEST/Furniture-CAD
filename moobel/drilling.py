"""Puurimisjoonised: iga plaadi kontuur, augud ja aukude tabel (PNG / PDF)."""
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF, QMarginsF
from PySide6.QtGui import (QPainter, QPen, QColor, QFont, QPolygonF, QImage, QPdfWriter, QPageSize,
                           QPageLayout)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
                               QPushButton, QFileDialog, QMessageBox, QCheckBox)

from .i18n import T


def hole_table(part):
    """[(nr, x, y, Ø, sügavus, koht)] lokaalsetes koordinaatides (nullpunkt = vasak alumine nurk)."""
    o = np.asarray(part.outline)
    x0, y0 = o[:, 0].min(), o[:, 1].min()
    rows = []
    for i, h in enumerate(part.holes, 1):
        ox, oy, oz = h.origin
        dx, dy, dz = h.direction
        if abs(dz) > 0.9:
            where = T("pealt") if dz < 0 else T("alt")
            if dz < 0 and oz < part.thickness - 0.5 or dz > 0 and oz > 0.5:
                where += " *"
            through = h.depth >= part.thickness - 0.2
            depth = T("läbi") if through else f"{h.depth:.0f}"
            rows.append((i, ox - x0, oy - y0, h.diameter, depth, where, "face", h))
        else:
            # servaauk: alguspunkt servas, suund sissepoole
            rows.append((i, ox - x0, oy - y0, h.diameter, f"{h.depth:.0f}", T("serv") + f" (z={oz:.0f})", "edge", h))
    return rows, (x0, y0)


def _table_rows(rows):
    """Üksikud augud eraldi; 32 mm süsteemi augud kokku võetuna veergude kaupa."""
    out, sys = [], {}
    for r in rows:
        nr, x, y, d, depth, where, kind, h = r
        if h.label == "32 mm":
            key = (round(x, 1), d, depth, where)
            sys.setdefault(key, []).append(y)
        else:
            out.append((str(nr), f"{x:.1f}", f"{y:.1f}", f"{d:g}", str(depth), where))
    for (x, d, depth, where), ys in sys.items():
        ys = sorted(ys)
        out.append(("32", f"{x:.1f}", f"{ys[0]:.0f}…{ys[-1]:.0f}", f"{d:g}", str(depth),
                    where + " – " + T(f"{len(ys)} tk, samm 32")))
    return out


def draw_part(p, rect, part, project_name=""):
    """Joonistab ühe detaili puurimisjoonise: vasakul joonis, paremal aukude tabel."""
    o = np.asarray(part.outline)
    x0, y0 = o[:, 0].min(), o[:, 1].min()
    Lx, Ly = o[:, 0].max() - x0, o[:, 1].max() - y0
    rows, _ = hole_table(part)
    trows = _table_rows(rows)
    X, Y, RW, RH = rect.x(), rect.y(), rect.width(), rect.height()
    p.setRenderHint(QPainter.Antialiasing)
    p.fillRect(rect, QColor("#ffffff"))
    p.setPen(QColor("#111"))
    f = QFont("Segoe UI"); f.setPixelSize(int(RH * 0.03)); f.setBold(True); p.setFont(f)
    L, W, Tk = part.dims()
    head = f"{T(part.name)}   {L:g} × {W:g} × {Tk:g} mm   {T(part.material)}"
    if part.edge_code():
        head += f"   {T('Servakant')}: {part.edge_code()}"
    p.drawText(QRectF(X + 10, Y + 6, RW - 20, RH * 0.06), Qt.AlignLeft | Qt.AlignVCenter, head)
    rot = Ly > Lx * 1.15                     # pikk külg alati horisontaalselt
    DW, DH = (Ly, Lx) if rot else (Lx, Ly)
    table_w = RW * 0.36 if trows else 0
    area = QRectF(X + 60, Y + RH * 0.09 + 10, RW - table_w - 110, RH * 0.91 - 90)
    k = min(area.width() / max(DW, 1), area.height() / max(DH, 1))
    ox = area.x() + (area.width() - DW * k) / 2
    oy = area.y() + (area.height() - DH * k) / 2 + DH * k

    def T_(x, y):
        u, v = x - x0, y - y0
        if rot:
            u, v = v, Lx - u
        return QPointF(ox + u * k, oy - v * k)
    p.setPen(QPen(QColor("#222"), 2)); p.setBrush(QColor("#f3ead8"))
    p.drawPolygon(QPolygonF([T_(x, y) for x, y in part.outline]))
    p.setBrush(QColor("#ffffff"))
    for inn in part.inner or []:
        p.drawPolygon(QPolygonF([T_(x, y) for x, y in inn]))
    if len(part.outline) == 4:
        long_x = Lx >= Ly
        segs = {"L1": ((0, 0), (Lx, 0)) if long_x else ((0, 0), (0, Ly)),
                "L2": ((0, Ly), (Lx, Ly)) if long_x else ((Lx, 0), (Lx, Ly)),
                "W1": ((0, 0), (0, Ly)) if long_x else ((0, 0), (Lx, 0)),
                "W2": ((Lx, 0), (Lx, Ly)) if long_x else ((0, Ly), (Lx, Ly))}
        p.setPen(QPen(QColor("#1f6fd1"), 5))
        for key, (a, b) in segs.items():
            if part.edge_t(key) > 0:
                p.drawLine(T_(a[0] + x0, a[1] + y0), T_(b[0] + x0, b[1] + y0))
    # mõõdud
    p.setPen(QPen(QColor("#666"), 1))
    f2 = QFont("Segoe UI"); f2.setPixelSize(int(RH * 0.024)); p.setFont(f2)
    bl = QPointF(ox, oy); br = QPointF(ox + DW * k, oy); tl = QPointF(ox, oy - DH * k)
    p.drawLine(QPointF(bl.x(), bl.y() + 16), QPointF(br.x(), br.y() + 16))
    p.drawText(QRectF(bl.x(), bl.y() + 18, br.x() - bl.x(), 22), Qt.AlignCenter, f"{DW:g}")
    p.drawLine(QPointF(bl.x() - 16, bl.y()), QPointF(tl.x() - 16, tl.y()))
    p.save(); p.translate(tl.x() - 22, (bl.y() + tl.y()) / 2); p.rotate(-90)
    p.drawText(QRectF(-80, -20, 160, 20), Qt.AlignCenter, f"{DH:g}"); p.restore()
    zero = T_(x0, y0)
    p.setPen(QPen(QColor("#b00020"), 1)); p.drawText(QPointF(zero.x() - 16, zero.y() + 16), "0")
    # augud
    fs = QFont("Segoe UI"); fs.setPixelSize(int(RH * 0.022)); fs.setBold(True)
    for (nr, x, y, d, depth, where, kind, h) in rows:
        c = T_(x + x0, y + y0)
        if kind == "face":
            r = max(2.5, d / 2 * k)
            p.setPen(QPen(QColor("#b00020"), 1.5))
            p.setBrush(QColor(176, 0, 32, 45) if where.startswith(T("alt")) else QColor(176, 0, 32, 110))
            p.drawEllipse(c, r, r)
        else:
            dx, dy = h.direction[0], h.direction[1]
            if rot:
                dx, dy = dy, -dx
            n = np.hypot(dx, dy) or 1
            e = QPointF(c.x() + dx / n * h.depth * k, c.y() - dy / n * h.depth * k)
            pen = QPen(QColor("#0b6e4f"), max(1.5, d * k)); pen.setStyle(Qt.DashLine)
            p.setPen(pen); p.drawLine(c, e)
        if h.label != "32 mm":
            p.setPen(QColor("#111")); p.setFont(fs)
            p.drawText(QPointF(c.x() + 6, c.y() - 6), str(nr))
    # tabel paremal
    if trows:
        tx = X + RW - table_w - 10
        ty = Y + RH * 0.09 + 10
        f3 = QFont("Segoe UI"); f3.setPixelSize(int(min(15, RH * 0.021))); p.setFont(f3)
        lh = f3.pixelSize() * 1.45
        cols = ["#", "X", "Y", "Ø", T("Sügavus"), T("Koht")]
        cw = [0.07, 0.13, 0.17, 0.08, 0.13, 0.42]
        xs = [tx]
        for w_ in cw[:-1]:
            xs.append(xs[-1] + table_w * w_)
        f3.setBold(True); p.setFont(f3); p.setPen(QColor("#333"))
        for c_, t in zip(xs, cols):
            p.drawText(QPointF(c_, ty + lh), t)
        p.drawLine(QPointF(tx, ty + lh * 1.3), QPointF(tx + table_w, ty + lh * 1.3))
        f3.setBold(False); p.setFont(f3)
        maxrows = int((RH * 0.85 - 40) / lh) - 2
        for i, row in enumerate(trows[:maxrows]):
            yy = ty + lh * (i + 2.3)
            for j, (c_, t) in enumerate(zip(xs, row)):
                if j == 5:
                    p.drawText(QRectF(c_, yy - lh + 3, table_w * cw[5] + 10, lh), Qt.AlignLeft | Qt.AlignVCenter, t)
                else:
                    p.drawText(QPointF(c_, yy), t)
        if len(trows) > maxrows:
            p.drawText(QPointF(tx, ty + lh * (maxrows + 2.3)), T(f"... ja veel {len(trows) - maxrows} rida"))
    p.setPen(QColor("#888"))
    f4 = QFont("Segoe UI"); f4.setPixelSize(int(RH * 0.017)); p.setFont(f4)
    p.drawText(QRectF(X + 10, Y + RH - 24, RW - 20, 22), Qt.AlignLeft | Qt.AlignVCenter,
               T("X/Y nullpunkt = vasak alumine nurk (punane 0), vaade pealt. Tume ring = auk pealt, hele = alt. "
                 "Roheline kriipsjoon = servaauk.") + f"   {project_name}")


def render_image(part, w=1400, h=1000, project_name=""):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    draw_part(p, QRectF(0, 0, w, h), part, project_name)
    p.end()
    return img


def export_pdf(parts, path, project_name=""):
    pw = QPdfWriter(path)
    pw.setPageSize(QPageSize(QPageSize.A4))
    pw.setPageOrientation(QPageLayout.Landscape)
    pw.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Millimeter)
    pw.setResolution(150)
    p = QPainter(pw)
    r = pw.pageLayout().paintRectPixels(150)
    for i, part in enumerate(parts):
        if i:
            pw.newPage()
        draw_part(p, QRectF(0, 0, r.width(), r.height()), part, project_name)
    p.end()


class DrillDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Puurimisjoonised")
        self.resize(1250, 780)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.only = QCheckBox("Ainult aukudega detailid"); self.only.setChecked(True)
        self.only.toggled.connect(self.fill)
        left.addWidget(self.only)
        self.lst = QListWidget(); self.lst.currentRowChanged.connect(self.show)
        left.addWidget(self.lst, 1)
        b = QPushButton("💾 Salvesta PDF (kõik nimekirjas)"); b.clicked.connect(self.save_pdf); left.addWidget(b)
        b = QPushButton("🖼 Salvesta pilt (valitud)"); b.clicked.connect(self.save_png); left.addWidget(b)
        lay.addLayout(left, 1)
        self.view = QLabel(); self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("background:#ddd")
        lay.addWidget(self.view, 4)
        self.fill()

    def parts(self):
        ps = [p for p in self.project.parts if p.kind == "plate" and getattr(p, "role", None) not in ("slide",)]
        if self.only.isChecked():
            ps = [p for p in ps if p.holes]
        return ps

    def fill(self, *a):
        self.lst.clear()
        for p in self.parts():
            it = QListWidgetItem(f"{T(p.name)}  ({len(p.holes)})")
            it.setData(Qt.UserRole, p.id)
            self.lst.addItem(it)
        if self.lst.count():
            self.lst.setCurrentRow(0)

    def show(self, row):
        if row < 0:
            return
        part = self.project.part(self.lst.item(row).data(Qt.UserRole))
        img = render_image(part, 1400, 1000, self.project.name)
        from PySide6.QtGui import QPixmap
        self.view.setPixmap(QPixmap.fromImage(img).scaled(self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.show(self.lst.currentRow())

    def save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, T("Salvesta PDF"), f"{self.project.name}_puurimine.pdf", "PDF (*.pdf)")
        if path:
            export_pdf(self.parts(), path, self.project.name)
            QMessageBox.information(self, T("Puurimisjoonised"), T("Salvestatud: ") + path)

    def save_png(self):
        r = self.lst.currentRow()
        if r < 0:
            return
        part = self.project.part(self.lst.item(r).data(Qt.UserRole))
        path, _ = QFileDialog.getSaveFileName(self, T("Salvesta pilt"), f"{part.name}.png", "PNG (*.png)")
        if path:
            render_image(part, 2000, 1430, self.project.name).save(path)
