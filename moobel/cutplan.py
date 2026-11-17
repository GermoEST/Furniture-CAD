"""Lõikeplaan: detailide paigutamine täisplaatidele (MaxRects, parim lühikese külje sobivus)."""
import math

from . import prices as PR

KERF = 4.0          # saelõike laius mm
TRIM = 10.0         # plaadi servast äralõige mm


class Sheet:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.free = [(0.0, 0.0, W, H)]
        self.placed = []      # (x, y, w, h, part_id, nimi, pööratud)

    def _score(self, w, h):
        best = None
        for (fx, fy, fw, fh) in self.free:
            for rot, (ww, hh) in ((False, (w, h)), (True, (h, w))):
                if ww <= fw + 1e-6 and hh <= fh + 1e-6:
                    s = (min(fw - ww, fh - hh), max(fw - ww, fh - hh))
                    if best is None or s < best[0]:
                        best = (s, fx, fy, ww, hh, rot)
        return best

    def place(self, w, h, allow_rot=True):
        b = self._score(w, h) if allow_rot else None
        if not allow_rot:
            for (fx, fy, fw, fh) in self.free:
                if w <= fw + 1e-6 and h <= fh + 1e-6:
                    s = (min(fw - w, fh - h), max(fw - w, fh - h))
                    if b is None or s < b[0]:
                        b = (s, fx, fy, w, h, False)
        if b is None:
            return None
        _, x, y, ww, hh, rot = b
        self._split(x, y, ww + KERF, hh + KERF)
        return x, y, ww, hh, rot

    def _split(self, x, y, w, h):
        new = []
        for (fx, fy, fw, fh) in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                new.append((fx, fy, fw, fh))
                continue
            if x > fx:
                new.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                new.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                new.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                new.append((fx, y + h, fw, fy + fh - y - h))
        # eemalda teiste sees olevad
        out = []
        for i, a in enumerate(new):
            if a[2] <= 1 or a[3] <= 1:
                continue
            inside = False
            for j, b in enumerate(new):
                if i != j and a[0] >= b[0] - 1e-6 and a[1] >= b[1] - 1e-6 and \
                        a[0] + a[2] <= b[0] + b[2] + 1e-6 and a[1] + a[3] <= b[1] + b[3] + 1e-6 and \
                        (a != b or i > j):
                    inside = True
                    break
            if not inside:
                out.append(a)
        self.free = out

    def used_area(self):
        return sum(w * h for (_, _, w, h, *_r) in self.placed)


def plan(project, st=None, grain=False):
    """Tagastab {(materjal, paksus): dict(sheet=(L,W), sheets=[Sheet], too_big=[nimed], area)}."""
    st = st or PR.load()
    groups = {}
    for p in project.parts:
        if getattr(p, "role", None) in ("slide", "handle") or getattr(p, "leg", None) or p.kind != "plate":
            continue
        cL, cW, T = p.cut_dims()
        groups.setdefault((p.material, T), []).append((cL, cW, p.id, p.name))
    out = {}
    for (mat, T), lst in sorted(groups.items()):
        it = PR.item(st, f"{mat}|{T:g}")
        sh = it.get("sheet") or PR.SHEETS.get(mat, [2800, 2070])
        L, W = max(sh), min(sh)
        UW, UH = L - 2 * TRIM, W - 2 * TRIM
        lst.sort(key=lambda r: (max(r[0], r[1]), min(r[0], r[1])), reverse=True)
        sheets, too_big = [], []
        for (a, b, pid, name) in lst:
            ok = False
            for s in sheets:
                r = s.place(a, b, not grain)
                if r:
                    s.placed.append((*r[:4], pid, name, r[4]))
                    ok = True
                    break
            if not ok:
                s = Sheet(UW, UH)
                r = s.place(a, b, not grain)
                if r is None:
                    too_big.append(name)
                    continue
                s.placed.append((*r[:4], pid, name, r[4]))
                sheets.append(s)
        area = sum(a * b for a, b, *_ in lst) / 1e6
        out[(mat, T)] = dict(sheet=(L, W), sheets=sheets, too_big=too_big, area=area)
    return out


def sheet_counts(project, st=None):
    return {k: len(v["sheets"]) for k, v in plan(project, st).items()}


# ------------------------------------------------------------------ joonistamine
def draw_sheet(painter, rect, sheet_size, sheet, title, names_tr=lambda s: s):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QPen, QFont
    L, W = sheet_size
    x0, y0, rw, rh = rect.x(), rect.y(), rect.width(), rect.height()
    k = min((rw - 20) / L, (rh - 40) / W)
    ox, oy = x0 + 10, y0 + 30
    p = painter
    p.setFont(QFont("Segoe UI", 10, QFont.Bold))
    p.setPen(QColor("#222"))
    used = sheet.used_area() / ((L - 2 * TRIM) * (W - 2 * TRIM)) * 100
    p.drawText(QRectF(x0, y0, rw, 24), Qt.AlignLeft | Qt.AlignVCenter, f"{title}   ({used:.0f}%)")
    p.setPen(QPen(QColor("#555"), 1))
    p.setBrush(QColor("#efe9dc"))
    p.drawRect(QRectF(ox, oy, L * k, W * k))
    cols = ["#d9b98c", "#c6d7c0", "#c9d3e8", "#e8cfc9", "#e6dca8", "#d6c8e3"]
    f = QFont("Segoe UI"); f.setPixelSize(max(9, int(min(13, 60 * k * 4))))
    p.setFont(f)
    for i, (x, y, w, h, pid, name, rot) in enumerate(sheet.placed):
        r = QRectF(ox + (x + TRIM) * k, oy + (y + TRIM) * k, w * k, h * k)
        p.setBrush(QColor(cols[pid % len(cols)]))
        p.setPen(QPen(QColor("#333"), 1))
        p.drawRect(r)
        lab = f"{names_tr(name)}\n{max(w, h):g}×{min(w, h):g}"
        p.setPen(QColor("#111"))
        if r.width() > 40 and r.height() > 18:
            p.drawText(r.adjusted(2, 2, -2, -2), Qt.AlignCenter | Qt.TextWordWrap, lab)
    p.setPen(QColor("#666"))
    p.drawText(QRectF(ox, oy + W * k + 2, L * k, 16), Qt.AlignRight, f"{L:g} × {W:g} mm")
