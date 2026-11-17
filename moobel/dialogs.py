"""Dialoogid: plaat, pildist import, kinnituse seaded, sammud, nimekiri."""
import os
import tempfile

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QSettings
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDialogButtonBox,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QCheckBox, QTabWidget, QWidget,
    QPlainTextEdit, QFileDialog, QMessageBox, QProgressBar, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QApplication, QGroupBox, QSplitter)

from .model import MATERIALS
from .fasteners import FASTENER_TYPES
from . import image_import as imp
from .i18n import T

ORIENTATIONS = ["Lamav (horisontaalne)", "Püstine, eest vaadates (nt tagasein)",
                "Püstine, küljelt vaadates (nt külg)"]


def spin(val, lo=0.0, hi=10000.0, dec=1, step=1.0, suffix=" mm"):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def material_combo(current=None):
    c = QComboBox()
    c.setEditable(True)
    c.addItems(MATERIALS)
    if current:
        c.setCurrentText(current)
    return c


# ====================================================================== plaat
class PlateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Uus plaat / latt")
        f = QFormLayout(self)
        self.name = QLineEdit("Plaat")
        self.w = spin(600)
        self.h = spin(400)
        self.t = spin(18, 0.5, 500, 1, 1)
        self.r = spin(0, 0, 500)
        self.mat = material_combo()
        self.orient = QComboBox(); self.orient.addItems(ORIENTATIONS)
        self.qty = QSpinBox(); self.qty.setRange(1, 50)
        self.desc = QLineEdit()
        f.addRow("Nimi", self.name)
        f.addRow("Laius (pikkus)", self.w)
        f.addRow("Kõrgus (laius)", self.h)
        f.addRow("Paksus", self.t)
        f.addRow("Nurga raadius", self.r)
        f.addRow("Materjal", self.mat)
        f.addRow("Asend", self.orient)
        f.addRow("Kogus", self.qty)
        f.addRow("Kirjeldus", self.desc)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self):
        return dict(name=self.name.text() or "Plaat", w=self.w.value(), h=self.h.value(),
                    t=self.t.value(), r=self.r.value(), material=self.mat.currentText(),
                    orient=self.orient.currentIndex(), qty=self.qty.value(),
                    desc=self.desc.text())


# ====================================================================== pildist
def cv_to_qimage(img):
    import cv2
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class MeshyWorker(QThread):
    progress = Signal(int, str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, key, path, out_dir):
        super().__init__()
        self.key, self.path, self.out_dir = key, path, out_dir
        self._stop = False

    def run(self):
        try:
            p = imp.meshy_image_to_3d(self.key, self.path, self.out_dir,
                                      progress=lambda v, s: self.progress.emit(v, s),
                                      cancelled=lambda: self._stop)
            self.done.emit(p)
        except Exception as e:  # noqa
            self.failed.emit(str(e))


class ImageImportDialog(QDialog):
    """Tulemus: self.result = dict(kind='plate', outline, inner, ...) või dict(kind='mesh', path, ...)."""

    def __init__(self, parent=None, work_dir=None):
        super().__init__(parent)
        self.setWindowTitle("Detail pildist")
        self.resize(1100, 720)
        self.work_dir = work_dir or tempfile.gettempdir()
        self.img = None
        self.img_path = None
        self.outer = None
        self.holes = []
        self.result = None
        self.worker = None
        self.settings = QSettings("Foral", "Moobel")

        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        row = QHBoxLayout()
        b_open = QPushButton("Ava pilt…"); b_open.clicked.connect(self.open_image)
        b_paste = QPushButton("Kleebi lõikelaualt"); b_paste.clicked.connect(self.paste_image)
        row.addWidget(b_open); row.addWidget(b_paste); row.addStretch()
        left.addLayout(row)
        self.preview = QLabel("Ava pilt (nt toote foto internetist või joonis).\n"
                              "Parim tulemus: detail heledal ühtlasel taustal, otse eest pildistatud.")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(640, 560)
        self.preview.setStyleSheet("background:#f4f4f4;border:1px solid #ccc")
        left.addWidget(self.preview, 1)
        self.info = QLabel("")
        left.addWidget(self.info)
        lay.addLayout(left, 3)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 2)

        # ---- kontuur
        t1 = QWidget(); f = QFormLayout(t1)
        self.thr = QSlider(Qt.Horizontal); self.thr.setRange(0, 254); self.thr.setValue(0)
        self.thr_lbl = QLabel("automaatne")
        self.inv = QCheckBox("Pööra ümber (detail on heledam kui taust)")
        self.grab = QCheckBox("Eemalda taust nutikalt (GrabCut, aeglasem)")
        self.simp = QSlider(Qt.Horizontal); self.simp.setRange(1, 300); self.simp.setValue(40)
        self.simp_lbl = QLabel("")
        self.keep_holes = QCheckBox("Võta ka sisemised augud"); self.keep_holes.setChecked(True)
        self.width_mm = spin(600)
        self.thick = spin(18, 0.5, 500)
        self.name = QLineEdit("Detail pildist")
        self.mat = material_combo()
        self.orient = QComboBox(); self.orient.addItems(ORIENTATIONS)
        self.desc = QPlainTextEdit(); self.desc.setPlaceholderText(
            "Kirjelda, millega on tegu (nt 'laua külg, alumine serv kaarjas')")
        self.desc.setMaximumHeight(80)
        thr_row = QHBoxLayout(); thr_row.addWidget(self.thr); thr_row.addWidget(self.thr_lbl)
        simp_row = QHBoxLayout(); simp_row.addWidget(self.simp); simp_row.addWidget(self.simp_lbl)
        f.addRow("Lävi", thr_row)
        f.addRow("", self.inv)
        f.addRow("", self.grab)
        f.addRow("Lihtsustus", simp_row)
        f.addRow("", self.keep_holes)
        f.addRow("Tegelik laius", self.width_mm)
        f.addRow("Paksus", self.thick)
        f.addRow("Nimi", self.name)
        f.addRow("Materjal", self.mat)
        f.addRow("Asend", self.orient)
        f.addRow("Kirjeldus", self.desc)
        self.size_lbl = QLabel("")
        f.addRow("Mõõdud", self.size_lbl)
        b_ok = QPushButton("Loo plaat sellest kontuurist")
        b_ok.setStyleSheet("font-weight:bold;padding:6px")
        b_ok.clicked.connect(self.accept_plate)
        f.addRow(b_ok)
        self.tabs.addTab(t1, "Kontuur → plaat")
        for w in (self.thr, self.simp):
            w.valueChanged.connect(self.update_contour)
        for w in (self.inv, self.grab, self.keep_holes):
            w.toggled.connect(self.update_contour)
        self.width_mm.valueChanged.connect(self.update_size)

        # ---- AI
        t2 = QWidget(); g = QFormLayout(t2)
        g.addRow(QLabel("Tehisintellekt (Meshy.ai) teeb pildist täieliku 3D kujundi.\n"
                        "Vajab internetti ja Meshy API võtit (meshy.ai → API).\n"
                        "Sobib keerulistele detailidele (jalad, nupud, kujuga osad).\n"
                        "Mõõtmed ei ole täpsed – anna suurim mõõt ise."), )
        self.key = QLineEdit(self.settings.value("meshy_key", ""))
        self.key.setEchoMode(QLineEdit.Password)
        self.ai_size = spin(400)
        self.ai_name = QLineEdit("AI detail")
        self.ai_mat = material_combo()
        self.ai_desc = QPlainTextEdit(); self.ai_desc.setMaximumHeight(80)
        g.addRow("API võti", self.key)
        g.addRow("Suurim mõõt", self.ai_size)
        g.addRow("Nimi", self.ai_name)
        g.addRow("Materjal", self.ai_mat)
        g.addRow("Kirjeldus", self.ai_desc)
        self.ai_prog = QProgressBar(); self.ai_prog.setValue(0)
        self.ai_status = QLabel("")
        self.ai_btn = QPushButton("Saada AI-le ja loo 3D detail")
        self.ai_btn.clicked.connect(self.start_ai)
        g.addRow(self.ai_btn)
        g.addRow(self.ai_prog)
        g.addRow(self.ai_status)
        self.tabs.addTab(t2, "AI → 3D kujund")

        if not imp.HAS_CV2:
            self.info.setText("OpenCV puudub: käivita install.bat")

    # ------------------------------------------------------------ pilt
    def open_image(self):
        d = self.settings.value("img_dir", "")
        p, _ = QFileDialog.getOpenFileName(self, "Ava pilt", d, "Pildid (*.png *.jpg *.jpeg *.webp *.bmp)")
        if p:
            self.settings.setValue("img_dir", os.path.dirname(p))
            self.set_image(p)

    def paste_image(self):
        im = QApplication.clipboard().image()
        if im.isNull():
            QMessageBox.information(self, "Lõikelaud", "Lõikelaual pole pilti. (Brauseris: parem klikk pildil → Kopeeri pilt)")
            return
        p = os.path.join(self.work_dir, "kleebitud_pilt.png")
        im.save(p)
        self.set_image(p)

    def set_image(self, path):
        try:
            self.img = imp.load_image(path)
        except Exception as e:
            QMessageBox.warning(self, "Viga", str(e))
            return
        self.img_path = path
        base = os.path.splitext(os.path.basename(path))[0]
        if self.name.text() == "Detail pildist":
            self.name.setText(base[:40])
        self.update_contour()

    def update_contour(self):
        if self.img is None:
            return
        self.thr_lbl.setText("automaatne" if self.thr.value() == 0 else str(self.thr.value()))
        self.simp_lbl.setText(f"{self.simp.value() / 100:.2f} %")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            mask = imp.make_mask(self.img, self.thr.value(), self.inv.isChecked(), self.grab.isChecked())
            self.outer, self.holes = imp.extract_contours(mask, self.simp.value() / 100,
                                                          self.keep_holes.isChecked())
        finally:
            QApplication.restoreOverrideCursor()
        self.draw_preview()
        self.update_size()

    def draw_preview(self):
        qi = cv_to_qimage(self.img)
        pm = QPixmap.fromImage(qi)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        if self.outer is not None:
            pen = QPen(QColor("#e0312b")); pen.setWidth(max(2, qi.width() // 300))
            p.setPen(pen)
            p.setBrush(QColor(224, 49, 43, 40))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in self.outer]))
            pen.setColor(QColor("#1f6fd1")); p.setPen(pen); p.setBrush(QColor(31, 111, 209, 60))
            for h in self.holes:
                p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in h]))
            p.setBrush(QColor("#e0312b"))
            r = max(3, qi.width() // 250)
            for x, y in self.outer:
                p.drawEllipse(QPointF(x, y), r, r)
        p.end()
        self.preview.setPixmap(pm.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if self.outer is None:
            self.info.setText("Kontuuri ei leitud – muuda läve või pööra ümber.")
        else:
            self.info.setText(f"Kontuuris {len(self.outer)} punkti, sisemisi auke {len(self.holes)}. "
                              "Punane = detail, sinine = augud.")

    def update_size(self):
        if self.outer is None:
            return
        o = np.asarray(self.outer)
        wpx = o[:, 0].max() - o[:, 0].min()
        hpx = o[:, 1].max() - o[:, 1].min()
        h_mm = self.width_mm.value() * hpx / max(wpx, 1)
        self.size_lbl.setText(f"{self.width_mm.value():.0f} × {h_mm:.0f} × {self.thick.value():g} mm")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.img is not None:
            self.draw_preview()

    def accept_plate(self):
        if self.outer is None or len(self.outer) < 3:
            QMessageBox.warning(self, "Kontuur", "Kontuur puudub.")
            return
        outline, inner, _ = imp.contours_to_mm(np.asarray(self.outer), [np.asarray(h) for h in self.holes],
                                               self.width_mm.value())
        self.result = dict(kind="plate", outline=outline, inner=inner, thickness=self.thick.value(),
                           name=self.name.text(), material=self.mat.currentText(),
                           orient=self.orient.currentIndex(),
                           description=self.desc.toPlainText())
        self.accept()

    # ------------------------------------------------------------ AI
    def start_ai(self):
        if not self.img_path:
            QMessageBox.warning(self, "AI", "Ava kõigepealt pilt.")
            return
        key = self.key.text().strip()
        if not key:
            QMessageBox.warning(self, "AI", "Sisesta Meshy API võti.")
            return
        self.settings.setValue("meshy_key", key)
        self.ai_btn.setEnabled(False)
        self.ai_status.setText("Saadan pilti…")
        self.worker = MeshyWorker(key, self.img_path, self.work_dir)
        self.worker.progress.connect(lambda v, s: (self.ai_prog.setValue(v), self.ai_status.setText(s)))
        self.worker.done.connect(self.ai_done)
        self.worker.failed.connect(self.ai_failed)
        self.worker.start()

    def ai_done(self, path):
        self.result = dict(kind="mesh", path=path, size=self.ai_size.value(), name=self.ai_name.text(),
                           material=self.ai_mat.currentText(), description=self.ai_desc.toPlainText())
        self.accept()

    def ai_failed(self, msg):
        self.ai_btn.setEnabled(True)
        self.ai_status.setText("Viga")
        QMessageBox.warning(self, "AI viga", msg)

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.worker._stop = True
            self.worker.wait(5000)
        super().reject()


# ====================================================================== kinnituse seaded
PARAM_NAMES = {
    "polt_d": "Poldi läbimõõt", "polt_L": "Poldi pikkus", "pea_d": "Pea läbimõõt",
    "mutri_d": "Mutri läbimõõt", "kaugus": "Ekstsentriku kaugus servast", "eks_d": "Ekstsentriku Ø",
    "eks_sugavus": "Ekstsentriku ava sügavus", "polt_ava_d": "Poldi ava Ø (vastasdetailis)",
    "polt_ava_sugavus": "Poldi ava sügavus", "serva_ava_d": "Serva ava Ø", "d": "Läbimõõt",
    "L": "Pikkus", "juhtava_d": "Juhtava Ø", "sugavus_A": "Sügavus esimeses detailis",
    "sugavus_jalg": "Ava sügavus jalas", "jala_ava_d": "Ava Ø jalas", "muhv_d": "Keermesmuhvi ava Ø",
    "muhv_L": "Keermesmuhvi ava sügavus",
}


class FastenerParamsDialog(QDialog):
    def __init__(self, ftype, current, parent=None):
        super().__init__(parent)
        spec = FASTENER_TYPES[ftype]
        self.setWindowTitle(spec["name"])
        f = QFormLayout(self)
        lbl = QLabel(spec["help"]); lbl.setWordWrap(True)
        f.addRow(lbl)
        self.fields = {}
        vals = dict(spec["params"]); vals.update(current or {})
        for k, v in spec["params"].items():
            s = spin(float(vals[k]), 0.5, 500, 1, 0.5)
            self.fields[k] = s
            f.addRow(PARAM_NAMES.get(k, k), s)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            lambda: [self.fields[k].setValue(v) for k, v in spec["params"].items()])
        f.addRow(bb)

    def values(self):
        return {k: s.value() for k, s in self.fields.items()}


# ====================================================================== sammud
class StepsDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        from .model import Step
        self.Step = Step
        self.project = project
        self.steps = [Step.from_dict(s.to_dict()) for s in project.steps] or []
        self.setWindowTitle("Monteerimise sammud")
        self.resize(900, 560)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self.show_step)
        left.addWidget(self.lst)
        row = QHBoxLayout()
        for txt, fn in (("Automaatne", self.auto), ("▲", self.up), ("▼", self.down),
                        ("Lisa", self.add), ("Ühenda eelmisega", self.merge), ("Kustuta", self.delete)):
            b = QPushButton(txt); b.clicked.connect(fn); row.addWidget(b)
        left.addLayout(row)
        lay.addLayout(left, 1)
        right = QFormLayout()
        self.title = QLineEdit(); self.title.editingFinished.connect(self.save_current)
        self.note = QPlainTextEdit(); self.note.textChanged.connect(self.save_current)
        self.parts = QListWidget(); self.parts.itemChanged.connect(self.save_current)
        self.fast_lbl = QLabel()
        right.addRow("Pealkiri", self.title)
        right.addRow("Märkus", self.note)
        right.addRow("Uued detailid selles sammus", self.parts)
        right.addRow("Kinnitused", self.fast_lbl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        right.addRow(bb)
        lay.addLayout(right, 1)
        self._loading = False
        if not self.steps:
            self.auto()
        else:
            self.reload()

    def reload(self, row=0):
        self.lst.clear()
        for i, s in enumerate(self.steps):
            self.lst.addItem(f"{i + 1}. {T(s.title)}")
        if self.steps:
            self.lst.setCurrentRow(min(row, len(self.steps) - 1))

    def show_step(self, i):
        if i < 0 or i >= len(self.steps):
            return
        self._loading = True
        s = self.steps[i]
        self.title.setText(T(s.title))
        self.note.setPlainText(s.note)
        self.parts.clear()
        for p in self.project.parts:
            it = QListWidgetItem(p.name)
            it.setData(Qt.UserRole, p.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if p.id in s.part_ids else Qt.Unchecked)
            self.parts.addItem(it)
        self.fast_lbl.setText(f"{len(s.fastener_ids)} tk")
        self._loading = False

    def save_current(self, *a):
        if self._loading:
            return
        i = self.lst.currentRow()
        if i < 0:
            return
        s = self.steps[i]
        s.title = self.title.text()
        s.note = self.note.toPlainText()
        s.part_ids = [self.parts.item(k).data(Qt.UserRole) for k in range(self.parts.count())
                      if self.parts.item(k).checkState() == Qt.Checked]
        self.lst.item(i).setText(f"{i + 1}. {T(s.title)}")

    def auto(self):
        self.steps = [self.Step.from_dict(s.to_dict()) for s in self.project.auto_steps()]
        self.reload()

    def up(self):
        i = self.lst.currentRow()
        if i > 0:
            self.steps[i - 1], self.steps[i] = self.steps[i], self.steps[i - 1]
            self.reload(i - 1)

    def down(self):
        i = self.lst.currentRow()
        if 0 <= i < len(self.steps) - 1:
            self.steps[i + 1], self.steps[i] = self.steps[i], self.steps[i + 1]
            self.reload(i + 1)

    def add(self):
        self.steps.insert(self.lst.currentRow() + 1, self.Step("Uus samm"))
        self.reload(self.lst.currentRow() + 1)

    def merge(self):
        i = self.lst.currentRow()
        if i > 0:
            a, b = self.steps[i - 1], self.steps[i]
            a.part_ids += [x for x in b.part_ids if x not in a.part_ids]
            a.fastener_ids += b.fastener_ids
            a.note = (a.note + "\n" + b.note).strip()
            del self.steps[i]
            self.reload(i - 1)

    def delete(self):
        i = self.lst.currentRow()
        if i >= 0:
            del self.steps[i]
            self.reload(i)

    def accept(self):
        self.project.steps = self.steps
        super().accept()


# ====================================================================== nimekiri
class CutListDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        from .manual import cut_list
        from .fasteners import hardware_summary
        self.project = project
        self.setWindowTitle("Detailide ja kinnituste nimekiri")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        rows = cut_list(project)
        t = QTableWidget(len(rows), 9)
        t.setHorizontalHeaderLabels(["Detail", "Kogus", "Materjal", "Pikkus", "Laius", "Paksus", "Lõikemõõt",
                                     "Servakant", "Auke"])
        total_area = 0.0
        for i, r in enumerate(rows):
            L, W, Tk = r["dims"]
            vals = [", ".join(r["names"]), r["qty"], r["material"], L, W, Tk,
                    f"{r['cut'][0]:g} × {r['cut'][1]:g}", r["edges"], r["holes"]]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(f"{v:g}" if isinstance(v, float) else T(str(v))))
            if r["kind"] == "plate":
                total_area += L * W * r["qty"] / 1e6
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(QLabel("<b>Detailid</b>"))
        lay.addWidget(t)
        hs = hardware_summary(project)
        t2 = QTableWidget(len(hs), 2)
        t2.setHorizontalHeaderLabels(["Kinnitus", "Kogus"])
        for i, (k, n) in enumerate(hs.items()):
            t2.setItem(i, 0, QTableWidgetItem(T(k))); t2.setItem(i, 1, QTableWidgetItem(str(n)))
        t2.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(QLabel("<b>Kinnitused</b>"))
        lay.addWidget(t2)
        lay.addWidget(QLabel(f"Plaatide kogupindala: {total_area:.2f} m²"))
        row = QHBoxLayout()
        b = QPushButton("Salvesta CSV (Excel)…"); b.clicked.connect(self.save_csv)
        row.addWidget(b); row.addStretch()
        c = QPushButton("Sulge"); c.clicked.connect(self.accept); row.addWidget(c)
        lay.addLayout(row)

    def save_csv(self):
        from .manual import export_csv
        p, _ = QFileDialog.getSaveFileName(self, "Salvesta nimekiri", f"{self.project.name}_nimekiri.csv",
                                           "CSV (*.csv)")
        if p:
            export_csv(self.project, p)


# ====================================================================== mööblijalad
class LegDialog(QDialog):
    def __init__(self, parent=None, plate=None):
        """plate = valitud plaat (Part) või None."""
        super().__init__(parent)
        from . import legs as L
        self.L = L
        self.plate = plate
        self.setWindowTitle("Mööblijalad")
        self.resize(760, 560)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        f = QFormLayout()
        self.kind = QComboBox()
        for k, v in L.LEG_TYPES.items():
            self.kind.addItem(v["name"], k)
        self.kind.currentIndexChanged.connect(self._rebuild_params)
        f.addRow("Jala tüüp", self.kind)
        self.color = QComboBox()
        f.addRow("Värv / puit", self.color)
        left.addLayout(f)
        self.pbox = QGroupBox("Mõõdud")
        self.pform = QFormLayout(self.pbox)
        left.addWidget(self.pbox)

        g = QGroupBox("Paigutus")
        gf = QFormLayout(g)
        self.place = QComboBox()
        if plate is not None:
            self.place.addItem(f"Valitud plaadi '{plate.name}' alla nurkadesse", "under")
        self.place.addItem("Lisa eraldi (paigutan ise)", "free")
        self.inset = spin(40, 0, 1000)
        self.qty = QSpinBox(); self.qty.setRange(1, 20); self.qty.setValue(4)
        self.auto_fix = QCheckBox("Lisa kinnitused automaatselt (kruvid / jalapoldid)")
        self.auto_fix.setChecked(True)
        gf.addRow("Kuhu", self.place)
        gf.addRow("Kaugus plaadi servast", self.inset)
        gf.addRow("Kogus (eraldi lisamisel)", self.qty)
        gf.addRow(self.auto_fix)
        self.screws = QSpinBox(); self.screws.setRange(1, 12); self.screws.setValue(4)
        self.screws.setToolTip("Mitu kruvi läheb ühe jala kinnitusplaadist (metalljalad)")
        gf.addRow("Kruvisid jala kohta", self.screws)
        self.place.currentIndexChanged.connect(self._update_enabled)
        left.addWidget(g)
        left.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        left.addWidget(bb)
        lay.addLayout(left, 3)
        self.preview = QLabel()
        self.preview.setMinimumSize(260, 440)
        self.preview.setStyleSheet("background:#f4f4f4;border:1px solid #ccc")
        lay.addWidget(self.preview, 2)
        self.fields = {}
        self._rebuild_params()
        self._update_enabled()

    def _default_H(self):
        if self.plate is not None:
            lo, _ = self.plate.world_bounds()
            if lo[2] > 50:
                return round(float(lo[2]), 1)
        return 720.0

    def _rebuild_params(self, *a):
        k = self.kind.currentData()
        spec = self.L.LEG_TYPES[k]
        while self.pform.rowCount():
            self.pform.removeRow(0)
        self.fields = {}
        for name, val in spec["params"].items():
            if name == "H":
                val = self._default_H()
            if name == "W" and self.plate is not None:
                lo, hi = self.plate.world_bounds()
                val = max(100.0, float(hi[1] - lo[1]) - 2 * self.inset.value())
            s = spin(float(val), 1, 5000)
            s.valueChanged.connect(self._draw)
            self.fields[name] = s
            self.pform.addRow(self.L.PARAM_NAMES.get(name, name), s)
        cols = self.L.WOOD_COLORS if spec["wood"] else self.L.METAL_COLORS
        cur = self.color.currentText()
        self.color.blockSignals(True)
        self.color.clear()
        for n, c in cols.items():
            self.color.addItem(n, c)
        if cur in cols:
            self.color.setCurrentText(cur)
        self.color.blockSignals(False)
        self.qty.setValue(2 if k == "metall_raam" else 4)
        if hasattr(self, "screws"):
            three = k == "metall_umar_3laba"
            self.screws.setValue(6 if three else 4)
            self.screws.setEnabled(k in ("metall_umar", "metall_kandiline"))
        self._draw()

    def _update_enabled(self, *a):
        under = self.place.currentData() == "under"
        self.inset.setEnabled(under)
        self.qty.setEnabled(not under)
        self.auto_fix.setEnabled(under)

    def params(self):
        return {k: s.value() for k, s in self.fields.items()}

    def _draw(self, *a):
        k = self.kind.currentData()
        p = self.params()
        w, h = 260, 440
        pm = QPixmap(w, h); pm.fill(QColor("#f4f4f4"))
        qp = QPainter(pm); qp.setRenderHint(QPainter.Antialiasing)
        H = p.get("H", 720)
        if k == "metall_raam":
            W = p.get("W", 560)
            sc = min((w - 40) / W, (h - 60) / H)
        else:
            top = p.get("plaat", p.get("a", p.get("d", 60)))
            sc = min((w - 40) / max(top * 3, 1), (h - 60) / H)
        ox, oy = w / 2, h - 30
        qp.setPen(QPen(QColor("#333"), 1.5))
        qp.setBrush(QColor(self.color.currentData() or "#999"))

        def poly(pts):
            qp.drawPolygon(QPolygonF([QPointF(ox + x * sc, oy - y * sc) for x, y in pts]))
        if k == "metall_raam":
            W, a = p["W"], p["a"]
            poly([(-W / 2, 0), (W / 2, 0), (W / 2, H), (-W / 2, H)])
            qp.setBrush(QColor("#f4f4f4"))
            poly([(-W / 2 + a, a), (W / 2 - a, a), (W / 2 - a, H - a), (-W / 2 + a, H - a)])
        elif k in ("metall_umar", "metall_kandiline", "metall_umar_3laba"):
            s = p.get("d", p.get("a")); t = p["plaat_t"]; pl = p["plaat"]
            poly([(-s / 2, 0), (s / 2, 0), (s / 2, H - t), (-s / 2, H - t)])
            poly([(-pl / 2, H - t), (pl / 2, H - t), (pl / 2, H), (-pl / 2, H)])
        else:
            top = p.get("a", p.get("d"))
            bot = p.get("a_all", p.get("d_all", top))
            poly([(-bot / 2, 0), (bot / 2, 0), (top / 2, H), (-top / 2, H)])
        qp.setPen(QColor("#555"))
        qp.drawText(8, 18, T(f"Kõrgus {H:g} mm"))
        qp.drawLine(10, int(oy), w - 10, int(oy))
        qp.end()
        self.preview.setPixmap(pm)

    def values(self):
        k = self.kind.currentData()
        return dict(kind=k, params=self.params(), color=self.color.currentData(),
                    color_name=self.color.currentText(), place=self.place.currentData(),
                    inset=self.inset.value(), qty=self.qty.value(),
                    auto_fix=self.auto_fix.isChecked() and self.place.currentData() == "under",
                    screws=self.screws.value())


# ====================================================================== sahtlid
class DrawerDialog(QDialog):
    def __init__(self, project, A, B, parent=None):
        super().__init__(parent)
        from . import drawers as D
        from . import handles as H
        self.D, self.H = D, H
        self.project, self.A, self.B = project, A, B
        self.info = D.analyse(A, B)
        inf = self.info
        self.setWindowTitle("Lisa sahtlid")
        self.resize(620, 720)
        v = QVBoxLayout(self)
        top = QLabel(f"Ava '{inf['lo_side'].name}' ja '{inf['hi_side'].name}' vahel: laius <b>{inf['W']:.0f} mm</b>, "
                     f"sügavus {inf['D']:.0f} mm, kõrgus {inf['z0']:.0f}…{inf['z1']:.0f} mm")
        top.setWordWrap(True)
        v.addWidget(top)
        f = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItem("Sahtlid", "sahtlid")
        self.kind.addItem("Klaviatuurisahtel (siinidega)", "klaviatuur")
        f.addRow("Tüüp", self.kind)
        self.count = QSpinBox(); self.count.setRange(1, 10); self.count.setValue(3)
        f.addRow("Sahtlite arv", self.count)
        zb_default = inf["z0"] + (100 if inf["z0"] < 5 else 0)
        self.zb = spin(round(zb_default, 1), -5000, 10000)
        self.zt = spin(round(inf["z1"], 1), -5000, 10000)
        f.addRow("Ava alumine serv (Z)", self.zb)
        f.addRow("Ava ülemine serv (Z)", self.zt)
        self.front_side = QComboBox()
        jn = "XYZ"[inf["j"]]
        self.front_side.addItem(f"{jn} väiksem pool (−{jn})", "min")
        self.front_side.addItem(f"{jn} suurem pool (+{jn})", "max")
        f.addRow("Mööbli esikülg", self.front_side)
        self.slide = QComboBox()
        for k, s in D.SLIDES.items():
            self.slide.addItem(f"{s['name']} (vahe {s['clr']:g} mm/pool)", k)
        f.addRow("Siinid", self.slide)
        self.L = QComboBox()
        self.L.addItem("Automaatne (pikim, mis mahub)", 0)
        for Ln in D.SLIDE_LENGTHS:
            self.L.addItem(f"{Ln} mm", Ln)
        f.addRow("Siini pikkus", self.L)
        v.addLayout(f)

        self.g_box = QGroupBox("Sahtlikast")
        gf = QFormLayout(self.g_box)
        self.box_mat = QComboBox()
        for k, (m, t, c) in D.BOX_MATS.items():
            self.box_mat.addItem(f"{m} {t:g} mm", k)
        self.bottom = QComboBox()
        for k, (m, t, c) in D.BOTTOMS.items():
            self.bottom.addItem(f"{m} {t:g} mm", k)
        self.bottom.setCurrentIndex(1)
        self.wide = QComboBox()
        self.wide.addItem("Paksem põhi (vineer 12 mm) + tugiliist", "molemad")
        self.wide.addItem("Paksem põhi (vineer 12 mm)", "paks")
        self.wide.addItem("Tavaline põhi + keskmine tugiliist", "liist")
        gf.addRow("Küljed, esi- ja tagaosa", self.box_mat)
        gf.addRow("Põhi (kuni 600 mm)", self.bottom)
        gf.addRow("Üle 600 mm laiad", self.wide)
        v.addWidget(self.g_box)

        self.g_front = QGroupBox("Esipaneel ja käepide")
        ff = QFormLayout(self.g_front)
        self.front_mode = QComboBox()
        self.front_mode.addItem("Sisse (ava sisse, esiservaga tasa)", "sisse")
        self.front_mode.addItem("Peale (katab külgseinte servad)", "peale")
        self.front_t = spin(18, 6, 40)
        self.gap = spin(3, 1, 10, 1, 0.5)
        self.front_mat = material_combo("MDF")
        self.front_color = QPushButton(); self._fc = "#f2f0eb"
        self.front_color.setStyleSheet(f"background-color:{self._fc};border:1px solid #777;min-height:20px")
        self.front_color.clicked.connect(self._pick_color)
        self.handle = QComboBox()
        for k, n in H.STYLES.items():
            self.handle.addItem(n, k)
        self.handle.addItem("Puudub (vajutusavaja)", "puudub")
        self.finish = QComboBox()
        for k in H.FINISHES:
            self.finish.addItem(k, k)
        self.handle.currentIndexChanged.connect(
            lambda: self.finish.setCurrentIndex(max(0, self.finish.findData(
                H.default_finish(self.handle.currentData() or "")))))
        ff.addRow("Paigaldus", self.front_mode)
        ff.addRow("Paksus", self.front_t)
        ff.addRow("Vahe paneelide vahel", self.gap)
        ff.addRow("Materjal", self.front_mat)
        ff.addRow("Värv", self.front_color)
        ff.addRow("Käepide", self.handle)
        ff.addRow("Käepideme viimistlus", self.finish)
        v.addWidget(self.g_front)

        self.g_kb = QGroupBox("Klaviatuurisahtel")
        kf = QFormLayout(self.g_kb)
        self.kb_w = spin(min(700.0, inf["W"] - 26), 200, 3000)
        self.kb_top = spin(round(inf["z1"] - 60, 1), -5000, 10000)
        self.kb_handle = QCheckBox("Lisa käepide esiliistule")
        kf.addRow("Alusplaadi laius", self.kb_w)
        kf.addRow("Alusplaadi pealmine pind (Z)", self.kb_top)
        kf.addRow(self.kb_handle)
        v.addWidget(self.g_kb)

        self.info_lbl = QLabel(); self.info_lbl.setWordWrap(True)
        self.info_lbl.setStyleSheet("background:#f6f3e8;border:1px solid #d8cfae;padding:6px")
        v.addWidget(self.info_lbl)
        v.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        self.ok_btn = bb.button(QDialogButtonBox.Ok)
        v.addWidget(bb)
        for w in (self.kind, self.front_side, self.slide, self.L, self.box_mat, self.bottom, self.wide,
                  self.front_mode, self.handle):
            w.currentIndexChanged.connect(self.update_info)
        for w in (self.count, self.zb, self.zt, self.front_t, self.gap, self.kb_w, self.kb_top):
            w.valueChanged.connect(self.update_info)
        self.handle.setCurrentIndex(0)
        self.finish.setCurrentIndex(max(0, self.finish.findData("Must")))
        self.update_info()

    def _pick_color(self):
        c = QColorDialog_get(self._fc, self)
        if c:
            self._fc = c
            self.front_color.setStyleSheet(f"background-color:{c};border:1px solid #777;min-height:20px")

    def options(self):
        return dict(kind=self.kind.currentData(), count=self.count.value(), z_bottom=self.zb.value(),
                    z_top=self.zt.value(), front_side=self.front_side.currentData(),
                    slide=self.slide.currentData(), L=self.L.currentData() or None,
                    box_mat=self.box_mat.currentData(), bottom=self.bottom.currentData(),
                    wide_mode=self.wide.currentData(), front_mode=self.front_mode.currentData(),
                    front_t=self.front_t.value(), gap=self.gap.value(), front_color=self._fc,
                    front_mat=self.front_mat.currentText(), handle=self.handle.currentData(),
                    finish=self.finish.currentData(), kb_width=self.kb_w.value(), kb_top=self.kb_top.value(),
                    kb_handle=self.kb_handle.isChecked())

    def update_info(self, *a):
        kb = self.kind.currentData() == "klaviatuur"
        self.g_box.setVisible(not kb)
        self.g_front.setVisible(True)
        self.g_kb.setVisible(kb)
        for w in (self.count, self.zb, self.zt):
            w.setEnabled(not kb)
        try:
            P = self.D.plan(self.info, self.options(), self.project)
        except self.D.DrawerError as e:
            self.info_lbl.setText(T(f"<b style='color:#b00'>⚠ {e}</b>"))
            self.ok_btn.setEnabled(False)
            return
        self.ok_btn.setEnabled(True)
        if kb:
            t = (f"Alus {P['Wt']:.0f} × {P['L']:g} mm, siinid {P['L']:g} mm"
                 + (f", siini aluslatid {P['spacer']:.0f} mm paksused (täidavad vahe küljeseinteni)"
                    if P['spacer'] > 1 else ""))
        else:
            t = (f"<b>{P['n']} sahtlit</b>: esipaneel {P['hf']:.0f} mm kõrge; kast {P['Wb']:.0f} × {P['L']:g} × "
                 f"{P['hb']:.0f} mm (L×S×K); siinid {P['L']:g} mm; põhi {P['tb']:g} mm")
            if P["wide"]:
                t += ("<br><b>Lai sahtel (&gt;600 mm):</b> " + ("paksem põhi " if P["thick"] else "")
                      + ("+ keskmine tugiliist" if P["support"] else "") + " – kasuta 45 kg siine")
        if P.get("D_free", 0) < self.info["D"] - 1:
            t += f"<br>Vaba sügavus piiratud teise detailiga: {P['D_free']:.0f} mm"
        self.info_lbl.setText(T(t))


def QColorDialog_get(cur, parent):
    from PySide6.QtWidgets import QColorDialog
    c = QColorDialog.getColor(QColor(cur), parent)
    return c.name() if c.isValid() else None


class HandleStyleWidget(QGroupBox):
    """Omaduste paneelis: käepideme stiili, tsentrite vahe ja viimistluse valik."""

    def __init__(self, on_change, parent=None):
        super().__init__("Käepide", parent)
        from . import handles as H
        self.H = H
        f = QFormLayout(self)
        self.style = QComboBox()
        for k, n in H.STYLES.items():
            self.style.addItem(n, k)
        self.cc = QComboBox()
        for c in H.CC_SIZES:
            self.cc.addItem(f"{c} mm", c)
        self.finish = QComboBox()
        for k in H.FINISHES:
            self.finish.addItem(k, k)
        self.all = QCheckBox("Muuda kõiki käepidemeid")
        f.addRow("Stiil", self.style)
        f.addRow("Kinnitusavade vahe", self.cc)
        f.addRow("Viimistlus", self.finish)
        f.addRow(self.all)
        self._on_change = on_change
        for w in (self.style, self.cc, self.finish):
            w.currentIndexChanged.connect(self._changed)
        self._loading = False

    def load(self, hd):
        self._loading = True
        self.style.setCurrentIndex(max(0, self.style.findData(hd["style"])))
        i = self.cc.findData(int(hd["cc"]))
        self.cc.setCurrentIndex(i if i >= 0 else 0)
        self.finish.setCurrentIndex(max(0, self.finish.findData(hd["finish"])))
        self.cc.setEnabled(hd["style"] not in self.H.KNOBS + ("profiil",))
        self._loading = False

    def _changed(self, *a):
        if self._loading:
            return
        st = self.style.currentData()
        self.cc.setEnabled(st not in self.H.KNOBS + ("profiil",))
        self._on_change(dict(style=st, cc=self.cc.currentData(), finish=self.finish.currentData()),
                        self.all.isChecked())
