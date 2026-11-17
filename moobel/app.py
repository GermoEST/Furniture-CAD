"""Mööbli disainer – peaaken."""
import os
import sys
import tempfile
import traceback

import numpy as np
from PySide6.QtCore import Qt, QObject, QEvent, QSettings, QUrl, QTimer
from PySide6.QtGui import QAction, QKeySequence, QColor, QDesktopServices, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QListWidget, QListWidgetItem, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QFormLayout, QLineEdit, QComboBox, QPlainTextEdit, QLabel,
    QToolBar, QSlider, QCheckBox, QMessageBox, QFileDialog, QColorDialog, QGroupBox,
    QScrollArea, QProgressDialog, QInputDialog, QDoubleSpinBox, QGridLayout, QSizePolicy)

import pyvista as pv
from pyvistaqt import QtInteractor
from vtkmodules.vtkRenderingCore import vtkCellPicker

from . import geom, scene
from .model import Project, Part, PALETTE, MATERIALS
from .fasteners import FASTENER_TYPES, FastenerError, add_fastener
from . import dialogs as dlg
from .i18n import T, translate_tree, ShowTranslator, flag_icon, set_lang, lang

APP_NAME = "Mööbli disainer"
FILE_FILTER = "Mööbliprojekt (*.moobel);;JSON (*.json)"

ORIENT_R = [np.eye(3), geom.rot_x(90), geom.rot_z(90) @ geom.rot_x(90)]


class ClickFilter(QObject):
    """Püüab 3D vaates lühikesed klikid (ilma lohistamata), ei sega pööramist."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.press = None
        self._resending = False

    def _resend_with_shift(self, obj, ev):
        """Lukus vaates muudetakse vasak lohistamine nihutamiseks (Shift+vasak = pan)."""
        e2 = QMouseEvent(ev.type(), ev.position(), ev.globalPosition(), ev.button(), ev.buttons(),
                         ev.modifiers() | Qt.ShiftModifier)
        self._resending = True
        try:
            QApplication.sendEvent(obj, e2)
        finally:
            self._resending = False
        return True

    def eventFilter(self, obj, ev):
        if self._resending:
            return False
        t = ev.type()
        if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            self.press = ev.position().toPoint()
        elif t == QEvent.MouseButtonRelease and ev.button() == Qt.LeftButton and self.press is not None:
            p = ev.position().toPoint()
            if (p - self.press).manhattanLength() <= 4:
                QTimer.singleShot(0, lambda pp=p: self.win.on_click(pp, obj))
            self.press = None
        elif t == QEvent.KeyPress:
            if ev.key() == Qt.Key_Escape:
                self.win.set_mode("select")
                return True
            if self.win.key_nudge(ev):
                return True
            # ära lase VTK enda klahve (w, s, e, q, r ...) kasutada – need segaksid
            if not (ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
                return True
            return False
        if self.win.view_locked and t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                                          QEvent.MouseMove, QEvent.MouseButtonDblClick):
            left = ev.button() == Qt.LeftButton or bool(ev.buttons() & Qt.LeftButton)
            if left and not (ev.modifiers() & Qt.ShiftModifier):
                return self._resend_with_shift(obj, ev)
            # ctrl+parem vms pööramisvariandid keelatud
            if t == QEvent.MouseButtonPress and ev.modifiers() & Qt.ControlModifier:
                return True
        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Foral", "Moobel")
        self.project = Project()
        self.path = None
        self.dirty = False
        self.undo_stack, self.redo_stack = [], []
        self.selected = None
        self.mode = "select"
        self.mate_first = None
        self.part_actors = {}       # pid -> (main_actor, [all actors])
        self.fast_actors = []
        self.marker = None
        self.view_locked = False
        self.sel = set()            # lisaks valitud detailid (Ctrl+klikk)
        self.fparams = {k: {} for k in FASTENER_TYPES}
        self.work_dir = os.path.join(tempfile.gettempdir(), "moobel_tmp")
        os.makedirs(self.work_dir, exist_ok=True)

        self.resize(1500, 900)
        self._build_view()
        self._build_parts_dock()
        self._build_props_dock()
        self._build_toolbar()
        self._build_menu()
        sb = self.statusBar()
        _orig_show = sb.showMessage
        sb.showMessage = lambda msg, ms=0: _orig_show(T(msg), ms)
        self._build_lang_bar()
        self.statusBar().showMessage("Tere! Alusta: 'Plaat / latt', 'Mööblijalad' või 'Näidis: kirjutuslaud'.")
        self.update_title()
        self.refresh_all(reset_camera=True)
        translate_tree(self)

    # ================================================================== keel
    def _build_lang_bar(self):
        from PySide6.QtWidgets import QToolButton, QButtonGroup
        from PySide6.QtCore import QSize
        w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(4, 0, 8, 0); lay.setSpacing(2)
        lay.addWidget(QLabel("🌐"))
        self.lang_btns = {}
        grp = QButtonGroup(w); grp.setExclusive(True)
        for code, label in (("et", "EST"), ("en", "ENG")):
            b = QToolButton()
            b.setIcon(flag_icon(code, 30, 20)); b.setIconSize(QSize(30, 20))
            b.setText(label); b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setCheckable(True); b.setChecked(lang() == code)
            b.setToolTip({"et": "Eesti keel", "en": "English"}[code])
            b.setStyleSheet("QToolButton{padding:2px 6px;border:1px solid transparent;border-radius:4px}"
                            "QToolButton:checked{background:#dbe9f8;border:1px solid #0072CE;font-weight:bold}")
            b.clicked.connect(lambda _=False, c=code: self.switch_lang(c))
            grp.addButton(b)
            lay.addWidget(b)
            self.lang_btns[code] = b
        self._lang_grp = grp
        self._lang_w = w
        self.menuBar().setCornerWidget(w, Qt.TopRightCorner)

    def switch_lang(self, code):
        if code == lang():
            return
        self.plotter.setFocus()          # lõpeta pooleli tekstimuutmine vanas keeles
        QApplication.processEvents()
        set_lang(code)
        for c, b in self.lang_btns.items():
            b.setChecked(c == code)
        translate_tree(self)
        self.a_lock.setText(T("🔓 Vabasta vaade" if self.view_locked else "🔒 Lukusta vaade"))
        self.refresh_list(); self.load_props(); self.update_title()
        self.statusBar().showMessage("Keel: eesti" if code == "et" else "Language: English", 4000)

    # ================================================================== UI ehitus
    def _build_view(self):
        self.plotter = QtInteractor(self)
        self.plotter.set_background("#f7f8fa", top="#dfe5ec")
        self.plotter.add_axes(interactive=False, line_width=2, labels_off=False)
        self.plotter.enable_lightkit() if hasattr(self.plotter, "enable_lightkit") else None
        # "maastiku" stiil: Z-telg jääb alati üles, vaade ei kaldu imeliku nurga alla
        try:
            self.plotter.enable_terrain_style(mouse_wheel_zooms=True, shift_pans=True)
        except Exception:
            pass
        self.setCentralWidget(self.plotter)
        self.clicker = ClickFilter(self)
        self.plotter.installEventFilter(self.clicker)
        self.picker = vtkCellPicker()
        self.picker.SetTolerance(0.0005)

    def _build_parts_dock(self):
        dock = QDockWidget("Detailid", self)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        w = QWidget(); lay = QVBoxLayout(w)
        self.part_list = QListWidget()
        self.part_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.part_list.currentItemChanged.connect(self._list_selected)
        self.part_list.itemSelectionChanged.connect(self._list_multi)
        lay.addWidget(self.part_list)
        g = QGridLayout()
        btns = [("➕ Plaat / latt", self.add_plate), ("🦵 Mööblijalad…", self.add_legs),
                ("📦 3D fail…", self.add_mesh_file), ("⧉ Dubleeri", self.duplicate_part),
                ("⇋ Koopia teisele poole", self.mirror_copy), ("🗑 Kustuta", self.delete_part),
                ("🗄 Lisa sahtlid…", self.add_drawers), ("🚪 Lisa uksed…", self.add_doors),
                ("📚 Lisa riiulid…", self.add_shelves_ui), ("🧩 Mallid…", self.add_template)]
        for i, (t, fn) in enumerate(btns):
            b = QPushButton(t); b.clicked.connect(fn); g.addWidget(b, i // 2, i % 2)
        lay.addLayout(g)
        hint = QLabel("Mitu detaili: Ctrl + klikk (nimekirjas või 3D vaates)")
        hint.setStyleSheet("color:#666;font-size:11px")
        lay.addWidget(hint)
        dock.setWidget(w)
        dock.setMinimumWidth(240)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_props_dock(self):
        dock = QDockWidget("Omadused", self)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        w = QWidget(); v = QVBoxLayout(w)
        f = QFormLayout()
        self.p_name = QLineEdit(); self.p_name.editingFinished.connect(self.apply_props)
        self.p_mat = dlg.material_combo(); self.p_mat.currentTextChanged.connect(self.apply_props)
        self.p_color = QPushButton(); self.p_color.clicked.connect(self.pick_color)
        self.p_t = dlg.spin(18, 0.5, 500)
        self.p_w = dlg.spin(600)
        self.p_h = dlg.spin(400)
        self.p_r = dlg.spin(0, 0, 500)
        for s in (self.p_t, self.p_w, self.p_h, self.p_r):
            s.valueChanged.connect(self.apply_props)
        f.addRow("Nimi", self.p_name)
        f.addRow("Materjal", self.p_mat)
        f.addRow("Värv", self.p_color)
        f.addRow("Paksus", self.p_t)
        self.lbl_w = QLabel("Laius"); self.lbl_h = QLabel("Kõrgus"); self.lbl_r = QLabel("Nurga raadius")
        f.addRow(self.lbl_w, self.p_w)
        f.addRow(self.lbl_h, self.p_h)
        f.addRow(self.lbl_r, self.p_r)
        v.addLayout(f)

        gb = QGroupBox("Asukoht ja pööre")
        gf = QFormLayout(gb)
        self.p_pos = [dlg.spin(0, -100000, 100000, 1, 1) for _ in range(3)]
        self.p_rot = [dlg.spin(0, -360, 360, 2, 15, "°") for _ in range(3)]
        for s in self.p_pos + self.p_rot:
            s.valueChanged.connect(self.apply_transform)
        for lab, s in zip("XYZ", self.p_pos):
            gf.addRow(f"{lab}", s)
        for lab, s in zip("XYZ", self.p_rot):
            gf.addRow(f"Pööre {lab}", s)
        rr = QHBoxLayout()
        for ax in "XYZ":
            b = QPushButton(f"↻{ax} 90°")
            b.clicked.connect(lambda _=False, a=ax: self.rotate90(a))
            rr.addWidget(b)
        gf.addRow(rr)
        rr2 = QHBoxLayout()
        b = QPushButton("Põrandale"); b.clicked.connect(self.to_floor); rr2.addWidget(b)
        b = QPushButton("Nihuta…"); b.clicked.connect(self.nudge_dialog); rr2.addWidget(b)
        gf.addRow(rr2)
        v.addWidget(gb)

        gbE = QGroupBox("Servakant")
        ge = QGridLayout(gbE)
        self.e_cb = {}
        for n_, (k_, lab_) in enumerate((("L1", "Pikk serv 1"), ("L2", "Pikk serv 2"),
                                         ("W1", "Lühike serv 1"), ("W2", "Lühike serv 2"))):
            cb = QCheckBox(lab_); cb.toggled.connect(self.apply_edges)
            ge.addWidget(cb, n_ // 2, n_ % 2); self.e_cb[k_] = cb
        self.e_t = QComboBox(); self.e_t.addItems(["0.4", "0.8", "1", "2"]); self.e_t.setCurrentText("2")
        self.e_t.currentTextChanged.connect(self.apply_edges)
        ge.addWidget(QLabel("Paksus mm"), 2, 0); ge.addWidget(self.e_t, 2, 1)
        bA = QPushButton("Kõik servad"); bA.clicked.connect(lambda: self.set_all_edges(True)); ge.addWidget(bA, 3, 0)
        bN = QPushButton("Puudub"); bN.clicked.connect(lambda: self.set_all_edges(False)); ge.addWidget(bN, 3, 1)
        ge.addWidget(QLabel("Kehtib kõigile valitud detailidele"), 4, 0, 1, 2)
        v.addWidget(gbE)
        self.gb_edges = gbE
        fr = QHBoxLayout()
        fr.addWidget(QLabel("Pind"))
        from . import textures as TX
        self.p_finish = QComboBox()
        for k_, n_ in TX.FINISHES.items():
            self.p_finish.addItem(n_, k_)
        self.p_finish.currentIndexChanged.connect(self.apply_finish)
        fr.addWidget(self.p_finish, 1)
        v.addLayout(fr)
        self.p_info = QLabel(""); self.p_info.setWordWrap(True)
        v.addWidget(self.p_info)
        v.addWidget(QLabel("Kirjeldus"))
        self.p_desc = QPlainTextEdit(); self.p_desc.setMaximumHeight(90)
        self.p_desc.textChanged.connect(self._desc_changed)
        v.addWidget(self.p_desc)

        self.p_handle = dlg.HandleStyleWidget(self.change_handle)
        self.p_handle.setVisible(False)
        v.addWidget(self.p_handle)

        gb2 = QGroupBox("Kinnitused selles detailis")
        g2 = QVBoxLayout(gb2)
        self.p_fast = QListWidget(); self.p_fast.setMaximumHeight(160)
        self.p_fast.currentItemChanged.connect(lambda *_: self.highlight_fasteners())
        g2.addWidget(self.p_fast)
        b = QPushButton("Kustuta valitud kinnitus (ja selle augud)")
        b.clicked.connect(self.delete_fastener)
        g2.addWidget(b)
        v.addWidget(gb2)
        v.addStretch()
        sc.setWidget(w)
        dock.setWidget(sc)
        dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.props_widget = w
        self.load_props()

    def _act(self, text, fn, shortcut=None, tip=None, checkable=False):
        a = QAction(text, self)
        a.triggered.connect(fn)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.WindowShortcut)
        if tip:
            a.setToolTip(tip); a.setStatusTip(tip)
        a.setCheckable(checkable)
        return a

    def _key3d(self, action):
        """Ühe-klahvi otsetee töötab ainult siis, kui 3D vaade on aktiivne (et tekstikastides saaks kirjutada)."""
        action.setShortcutContext(Qt.WidgetShortcut)
        self.plotter.addAction(action)
        return action

    def _build_toolbar(self):
        tb = QToolBar("Tööriistad"); tb.setMovable(False)
        self.addToolBar(tb)
        self.a_mate = self._act("🧲 Liida pinnad", lambda: self.set_mode("mate1"), "M",
                                "Kliki paigal oleva detaili pinnale, siis liigutatava detaili pinnale. "
                                "Teine detail keeratakse ja lükatakse esimese vastu.", True)
        tb.addAction(self._key3d(self.a_mate))
        tb.addSeparator()
        tb.addWidget(QLabel(" Kinnitus: "))
        self.f_combo = QComboBox()
        for k, s in FASTENER_TYPES.items():
            if k == "hing":
                continue
            self.f_combo.addItem(s["name"], k)
        self.f_combo.setToolTip("\n".join(f"{s['name']}: {s['help']}" for s in FASTENER_TYPES.values()))
        tb.addWidget(self.f_combo)
        tb.addAction(self._act("⚙", self.fastener_settings, tip="Kinnituse mõõdud"))
        self.a_fast = self._act("🔩 Lisa kinnitus", lambda: self.set_mode("fastener"), "K",
                                "Kliki detaili välispinnale kohas, kust kinnitus sisse läheb. "
                                "Selle taga peab olema teine detail. Esc lõpetab.", True)
        tb.addAction(self._key3d(self.a_fast))
        self.flip_cb = QCheckBox("mutter/ekstsentrik teisele poole")
        tb.addWidget(self.flip_cb)
        tb.addSeparator()
        tb.addWidget(QLabel(" Lahti: "))
        self.explode = QSlider(Qt.Horizontal); self.explode.setRange(0, 100); self.explode.setFixedWidth(110)
        self.explode.valueChanged.connect(lambda *_: (self.rebuild_scene(), self.plotter.reset_camera(), self.plotter.render()))
        tb.addWidget(self.explode)
        self.cb_hw = QCheckBox("Kinnitused"); self.cb_hw.setChecked(True)
        self.cb_hw.toggled.connect(lambda *_: self.refresh_all())
        tb.addWidget(self.cb_hw)
        self.cb_xray = QCheckBox("Läbipaistev"); self.cb_xray.toggled.connect(lambda *_: self.refresh_all())
        tb.addWidget(self.cb_xray)
        tb.addSeparator()
        self.addToolBarBreak()
        tv = QToolBar("Vaade"); tv.setMovable(False)
        self.addToolBar(tv)
        tv.addWidget(QLabel(" Vaade: "))
        self.a_lock = self._key3d(self._act("🔒 Lukusta vaade", self.toggle_lock, "L",
                                            "Vaade ei pöördu: vasak hiir nihutab, ratas suumib.", True))
        tv.addAction(self.a_lock)
        self.a_ortho = self._key3d(self._act("📐 Ortho", self.toggle_ortho, "O",
                                             "Ilma perspektiivita vaade (nagu tehniline joonis).", True))
        tv.addAction(self.a_ortho)
        tv.addSeparator()
        self.view_acts = []
        for t, key, which in (("Iso", "0", "iso"), ("Eest", "1", "front"), ("Tagant", "2", "back"),
                              ("Paremalt", "3", "right"), ("Vasakult", "4", "left"), ("Pealt", "7", "top")):
            a = self._key3d(self._act(t, lambda _=False, w=which: self.view(w), key, f"{t} vaade (klahv {key})"))
            tv.addAction(a)
        tv.addAction(self._key3d(self._act("Sobita", lambda: (self.plotter.reset_camera(), self.plotter.render()), "F", "Sobita kõik vaatesse (F)")))
        tv.addSeparator()
        tv.addAction(self._act("⌨ Klahvid", self.show_keys))
        tv.addSeparator()
        tb.addSeparator()
        tv.addAction(self._act("📋 Nimekiri", self.show_cutlist))
        tv.addAction(self._act("🪜 Sammud", self.edit_steps))
        tv.addAction(self._act("📘 Monteerimisjuhend", self.make_manual))
        tv.addAction(self._act("💶 Maksumus", self.show_prices, tip="Materjalide ja tarvikute nimekiri hindadega – hinnad sisestad ise"))
        self.addToolBarBreak()
        tm = QToolBar("Valmistamine"); tm.setMovable(False)
        self.addToolBar(tm)
        tm.addWidget(QLabel(" Tööriistad: "))
        self.a_measure = self._key3d(self._act("📏 Mõõda", lambda: self.set_mode("measure" if self.mode != "measure" else "select"),
                                               "D", "Kliki kahte punkti – näitab kaugust. Esc lõpetab.", True))
        tm.addAction(self.a_measure)
        self.a_dims = self._act("📐 Üldmõõdud", lambda: (self.rebuild_scene(), self.plotter.render()),
                                tip="Näita mööbli laiust, sügavust ja kõrgust 3D vaates", checkable=True)
        tm.addAction(self.a_dims)
        tm.addSeparator()
        tm.addAction(self._act("✂ Lõikeplaan", self.show_cutplan, tip="Detailide paigutus täisplaatidele"))
        tm.addAction(self._act("🔩 Puurimisjoonised", self.show_drilling, tip="Iga detaili augud koos mõõtudega"))
        tm.addAction(self._act("⚠ Kontrolli", self.run_check, tip="Otsi kokkupõrkeid ja vigaseid auke"))
        tm.addAction(self._act("🖼 Esitlus", self.make_presentation, tip="Ilus pilt või PDF koos mõõtudega"))
        tm.addSeparator()
        tm.addAction(self._key3d(self._act("Vali grupp", self.select_group, "G",
                                           "Vali kõik sama grupi detailid (nt terve sahtel)")))
        tm.addAction(self._key3d(self._act("Vali kõik", self.select_all, "Ctrl+A")))

    def _build_menu(self):
        m = self.menuBar().addMenu("&Fail")
        m.addAction(self._act("Uus", self.new_project, "Ctrl+N"))
        m.addAction(self._act("Ava…", self.open_project, "Ctrl+O"))
        m.addAction(self._act("Salvesta", self.save_project, "Ctrl+S"))
        m.addAction(self._act("Salvesta nimega…", lambda: self.save_project(True), "Ctrl+Shift+S"))
        m.addSeparator()
        m.addAction(self._act("Näidis: kirjutuslaud", self.load_sample))
        m.addAction(self._act("Ekspordi STL (kogu mööbel)…", self.export_stl))
        m.addAction(self._act("Projekti nimi…", self.rename_project))
        m.addSeparator()
        m.addAction(self._act("Välju", self.close, "Ctrl+Q"))
        e = self.menuBar().addMenu("&Muuda")
        e.addAction(self._act("Võta tagasi", self.undo, "Ctrl+Z"))
        e.addAction(self._act("Tee uuesti", self.redo, "Ctrl+Y"))
        e.addSeparator()
        e.addAction(self._act("Dubleeri detail", self.duplicate_part, "Ctrl+D"))
        a_del = self._act("Kustuta detail", self.delete_part, "Del")
        a_del.setShortcutContext(Qt.WidgetShortcut)
        self.plotter.addAction(a_del); self.part_list.addAction(a_del)
        e.addAction(a_del)
        e.addAction(self._act("Tühista tööriist", lambda: self.set_mode("select"), "Esc"))
        h = self.menuBar().addMenu("&Abi")
        h.addAction(self._act("Kuidas kasutada", self.show_help, "F1"))
        h.addAction(self._act("Klahvid ja hiir", self.show_keys, "F2"))
        h.addAction(self._act("Graafika režiim (kui 3D vaade on must/tühi)…", self.gl_mode_dialog))

    # ================================================================== projekt / undo
    def push_undo(self):
        self.undo_stack.append(self.project.snapshot())
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.dirty = True
        self.update_title()

    def _restore(self, snap):
        sel = self.selected
        self.project = Project.from_dict(snap)
        self.selected = sel if self.project.part(sel) else None
        self.refresh_all()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.project.snapshot())
            self._restore(self.undo_stack.pop())
            self.statusBar().showMessage("Tagasi võetud", 2000)

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.project.snapshot())
            self._restore(self.redo_stack.pop())

    def update_title(self):
        n = os.path.basename(self.path) if self.path else "salvestamata"
        self.setWindowTitle(f"{T(APP_NAME)} – {self.project.name} ({T(n)}){' *' if self.dirty else ''}")

    def ask_save(self):
        if not self.dirty:
            return True
        r = QMessageBox.question(self, APP_NAME, "Salvestan muudatused?",
                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Yes:
            return self.save_project()
        return True

    def new_project(self):
        if not self.ask_save():
            return
        self.project = Project(); self.path = None; self.dirty = False
        self.undo_stack.clear(); self.selected = None
        self.refresh_all(reset_camera=True); self.update_title()

    def open_project(self, path=None):
        if not self.ask_save():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, T("Ava projekt"), self.settings.value("dir", ""), FILE_FILTER)
        if not path:
            return
        try:
            self.project = Project.load(path)
        except Exception as e:
            QMessageBox.warning(self, "Viga", f"Ei saanud avada:\n{e}")
            return
        self.settings.setValue("dir", os.path.dirname(path))
        self.path = path; self.dirty = False; self.undo_stack.clear(); self.selected = None
        self.refresh_all(reset_camera=True); self.update_title()

    def save_project(self, as_new=False):
        path = self.path
        if as_new or not path:
            path, _ = QFileDialog.getSaveFileName(self, T("Salvesta projekt"),
                                                  os.path.join(self.settings.value("dir", ""),
                                                               f"{self.project.name}.moobel"), FILE_FILTER)
            if not path:
                return False
        self.project.save(path)
        self.settings.setValue("dir", os.path.dirname(path))
        self.path = path; self.dirty = False; self.update_title()
        self.statusBar().showMessage(f"Salvestatud: {path}", 4000)
        return True

    def rename_project(self):
        t, ok = QInputDialog.getText(self, "Projekti nimi", "Nimi:", text=self.project.name)
        if ok and t:
            self.push_undo(); self.project.name = t; self.update_title()

    def load_sample(self):
        if not self.ask_save():
            return
        from .sample import desk
        self.project = desk(); self.path = None; self.dirty = True; self.undo_stack.clear()
        self.selected = None
        self.refresh_all(reset_camera=True); self.update_title()
        self.statusBar().showMessage("Näidislaud laaditud: 4 detaili, Minifixid, ristmutrid ja tüüblid.", 6000)

    def closeEvent(self, e):
        if self.ask_save():
            self.plotter.close()
            e.accept()
        else:
            e.ignore()

    # ================================================================== detailide lisamine
    def _free_spot(self, part):
        if len(self.project.parts) <= 1:
            lo, _ = part.world_bounds()
            part.position = (np.asarray(part.position) - lo).tolist()
            return
        others = [p for p in self.project.parts if p.id != part.id]
        his = max(p.world_bounds()[1][0] for p in others)
        lo, _ = part.world_bounds()
        part.position = (np.asarray(part.position) + np.array([his + 100 - lo[0], -lo[1], -lo[2]])).tolist()

    def _new_part(self, name, color=None):
        p = Part(self.project.new_id(), name)
        p.color = color or PALETTE[(len(self.project.parts)) % len(PALETTE)]
        return p

    def add_plate(self):
        d = dlg.PlateDialog(self)
        if not d.exec():
            return
        v = d.values()
        self.push_undo()
        last = None
        for i in range(v["qty"]):
            p = self._new_part(v["name"] if v["qty"] == 1 else f"{v['name']} {i + 1}")
            p.thickness = v["t"]; p.set_rect(v["w"], v["h"], v["r"])
            p.material = v["material"]; p.description = v["desc"]
            p.R = ORIENT_R[v["orient"]]
            self.project.add_part(p)
            self._free_spot(p)
            last = p
        self.selected = last.id
        self.refresh_all(reset_camera=len(self.project.parts) <= v["qty"])

    def add_legs(self):
        from . import legs as LG
        sel = self.project.part(self.selected)
        plate = sel if (sel is not None and sel.kind == "plate") else None
        d = dlg.LegDialog(self, plate)
        if not d.exec():
            return
        v = d.values()
        k, p = v["kind"], v["params"]
        self.push_undo()
        made = []
        is_frame = k == "metall_raam"
        n = 2 if (is_frame and v["place"] == "under") else (4 if v["place"] == "under" else v["qty"])
        base = "Raamjalg" if is_frame else "Jalg"
        mesh = None if is_frame else LG.leg_mesh(k, p)
        for i in range(n):
            part = self._new_part(f"{base} {i + 1}", v["color"])
            if is_frame:
                part.kind = "plate"; part.source = "leg"
                part.outline, part.inner = LG.frame_outline(p)
                part.thickness = float(p["a"])
                part.rect = [0, 0, 0]
                part.R = ORIENT_R[2]
            else:
                part.kind = "mesh"; part.source = "leg"
                part.mesh_v = np.round(mesh.vertices, 3).tolist()
                part.mesh_f = mesh.faces.tolist()
                part.thickness = float(min(mesh.extents))
            part.material = "Täispuit" if LG.LEG_TYPES[k]["wood"] else "Metall"
            part.description = LG.describe(k, p) + f", {v['color_name'].lower()}"
            part.leg = dict(kind=k, params=p)
            self.project.add_part(part)
            made.append(part)

        warns = []
        if v["place"] == "under" and plate is not None:
            from .sample import place_min
            lo, hi = plate.world_bounds()
            ins = v["inset"]
            H = float(p["H"])
            z0 = lo[2] - H
            if is_frame:
                a, W = float(p["a"]), float(p["W"])
                yc = (lo[1] + hi[1]) / 2 - W / 2
                for part, x in zip(made, (lo[0] + ins, hi[0] - ins - a)):
                    place_min(part, x, yc, z0)
            else:
                fx, fy = LG.footprint(k, p)
                xs = (lo[0] + ins, hi[0] - ins - fx)
                ys = (lo[1] + ins, hi[1] - ins - fy)
                for part, (x, y) in zip(made, [(xs[0], ys[0]), (xs[1], ys[0]), (xs[0], ys[1]), (xs[1], ys[1])]):
                    place_min(part, x, y, z0)
            names = ["vasak ees", "parem ees", "vasak taga", "parem taga"] if not is_frame else ["vasak", "parem"]
            for part, nm in zip(made, names):
                part.name = f"{base} {nm}"
                self.project.note_assembled(plate.id, part.id)
            if v["auto_fix"]:
                down = np.array([0, 0, -1.0])
                for part in made:
                    try:
                        if is_frame:
                            flo, fhi = part.world_bounds()
                            a = float(p["a"])
                            xc = (flo[0] + fhi[0]) / 2
                            for y in (flo[1] + 60, fhi[1] - 60):
                                add_fastener(self.project, "kruvi", {"d": 5, "L": a + 14}, part,
                                             np.array([xc, y, fhi[2] - a]), down)
                        elif LG.LEG_TYPES[k]["wood"]:
                            P = np.asarray(part.position) + part.R @ np.zeros(3)
                            lo2, hi2 = part.world_bounds()
                            P = np.array([(lo2[0] + hi2[0]) / 2, (lo2[1] + hi2[1]) / 2, lo2[2]])
                            add_fastener(self.project, "jalapolt", {}, part, P, down)
                        else:
                            for pt in LG.screw_points(k, p, v.get("screws", 4)):
                                P = part.R @ np.asarray(pt) + np.asarray(part.position)
                                add_fastener(self.project, "kruvi", {"d": 4, "L": 16}, part, P, down)
                    except FastenerError as e:
                        warns.append(f"{part.name}: {e}")
        else:
            for part in made:
                self._free_spot(part)
        self.selected = made[0].id
        self.refresh_all(reset_camera=True)
        msg = f"Lisatud {len(made)} jalga ({LG.LEG_TYPES[k]['name']})."
        if warns:
            QMessageBox.warning(self, "Jalad", msg + "\n\nMõned kinnitused jäid lisamata:\n" + "\n".join(warns[:6]))
        else:
            self.statusBar().showMessage(msg, 6000)

    def add_drawers(self):
        from . import drawers as D
        ids = self.selected_ids()
        if len(ids) != 2:
            QMessageBox.information(self, "Sahtlid",
                                    "Vali kaks küljeseina, mille vahele sahtlid tulevad:\n"
                                    "kliki esimesel, siis Ctrl + klikk teisel (nimekirjas või 3D vaates).")
            return
        A, B = (self.project.part(i) for i in ids)
        try:
            d = dlg.DrawerDialog(self.project, A, B, self)
        except D.DrawerError as e:
            QMessageBox.warning(self, "Sahtlid", str(e)); return
        if not d.exec():
            return
        before = self.project.snapshot()
        try:
            made, warns = D.build(self.project, A, B, d.options())
        except Exception as e:
            self.project = Project.from_dict(before)
            QMessageBox.warning(self, "Sahtlid", str(e)); return
        self.undo_stack.append(before); self.redo_stack.clear(); self.dirty = True; self.update_title()
        for p in made:
            self.project.note_assembled(p.id)
        self.sel = set()
        self.selected = made[0].id if made else None
        self.refresh_all()
        groups = sorted({p.group for p in made})
        msg = f"Lisatud: {', '.join(groups)} ({len(made)} detaili)."
        if warns:
            QMessageBox.information(self, "Sahtlid", msg + "\n\n" + "\n".join(warns))
        else:
            self.statusBar().showMessage(msg, 6000)

    def change_handle(self, new, all_handles):
        from . import drawers as D
        p = self.project.part(self.selected)
        if not p or not getattr(p, "handle", None):
            return
        targets = [q for q in self.project.parts if getattr(q, "handle", None)] if all_handles else [p]
        from . import handles as H
        cc_changed = new["cc"] != p.handle["cc"]
        self.push_undo()
        for q in targets:
            hd = dict(q.handle)
            hd["style"], hd["finish"] = new["style"], new["finish"]
            if q is p or cc_changed:
                hd["cc"] = new["cc"]
            if hd["cc"] > q.handle["front_w"] * 0.9:
                hd["cc"] = H.default_cc(q.handle["front_w"])
            D.set_handle_geometry(q, hd)
        self.refresh_all()
        self.statusBar().showMessage(f"Käepide muudetud ({len(targets)} tk).", 4000)

    def add_from_image(self):
        d = dlg.ImageImportDialog(self, self.work_dir)
        if not d.exec() or not d.result:
            return
        r = d.result
        try:
            if r["kind"] == "plate":
                p = self._new_part(r["name"])
                p.source = "image"
                p.outline, p.inner, p.thickness = r["outline"], r["inner"], r["thickness"]
                p.rect = [0, 0, 0]
                p.R = ORIENT_R[r["orient"]]
                p.body_mesh()
            else:
                p = self._mesh_part(r["path"], r["size"], r["name"])
                p.source = "ai"
            p.material = r["material"]; p.description = r["description"]
        except Exception as e:
            QMessageBox.warning(self, "Viga", f"Detaili ei saanud luua:\n{e}")
            return
        self.push_undo()
        self.project.add_part(p)
        self._free_spot(p)
        self.selected = p.id
        self.refresh_all(reset_camera=len(self.project.parts) == 1)

    def _mesh_part(self, path, size, name):
        from .image_import import load_mesh_file
        m = load_mesh_file(path, size)
        p = self._new_part(name)
        p.kind = "mesh"; p.source = "file"
        p.mesh_v = np.round(m.vertices, 3).tolist()
        p.mesh_f = m.faces.tolist()
        p.thickness = float(min(m.extents))
        return p

    def add_mesh_file(self):
        path, _ = QFileDialog.getOpenFileName(self, T("Ava 3D fail"), self.settings.value("dir", ""),
                                              "3D (*.stl *.obj *.glb *.gltf *.ply *.off)")
        if not path:
            return
        size, ok = QInputDialog.getDouble(self, "Suurus", "Suurim mõõt mm (0 = jäta failist):", 0, 0, 100000, 1)
        if not ok:
            return
        try:
            p = self._mesh_part(path, size or None, os.path.splitext(os.path.basename(path))[0])
        except Exception as e:
            QMessageBox.warning(self, "Viga", str(e)); return
        self.push_undo()
        self.project.add_part(p); self._free_spot(p); self.selected = p.id
        self.refresh_all(reset_camera=len(self.project.parts) == 1)

    def _copy_part(self, p, name):
        d = p.to_dict()
        q = Part.from_dict(d)
        q.id = self.project.new_id()
        q.name = name
        q.holes = []
        return q

    def duplicate_part(self):
        ps = [self.project.part(i) for i in self.selected_ids()]
        if not ps:
            return
        self.push_undo()
        los, his = zip(*[q.world_bounds() for q in ps])
        dx = np.max(his, axis=0)[0] - np.min(los, axis=0)[0] + 50
        new = []
        for p in ps:
            q = self._copy_part(p, p.name + " (koopia)")
            q.position = (np.asarray(q.position) + np.array([dx, 0, 0])).tolist()
            if getattr(q, "group", ""):
                q.group = q.group + " (koopia)"
            self.project.add_part(q)
            new.append(q.id)
        self.selected = new[-1]
        self.sel = set(new) if len(new) > 1 else set()
        self.refresh_all()

    def mirror_copy(self):
        """Peegelkoopia üle X-telje keskkoha (nt vasak külg -> parem külg)."""
        p = self.project.part(self.selected)
        if not p:
            return
        self.push_undo()
        q = self._copy_part(p, p.name + " (teine pool)")
        lo, hi = p.world_bounds()
        plo, phi = self.project.bounds()
        cx = (plo[0] + phi[0]) / 2
        newx = 2 * cx - hi[0]
        q.position = (np.asarray(q.position) + np.array([newx - lo[0], 0, 0])).tolist()
        self.project.add_part(q)
        self.selected = q.id
        self.refresh_all()

    def delete_part(self):
        ids = self.selected_ids()
        if not ids:
            return
        p = self.project.part(ids[0])
        q = (f"Kustutan detaili '{p.name}' (ja selle kinnitused)?" if len(ids) == 1
             else f"Kustutan {len(ids)} valitud detaili (ja nende kinnitused)?")
        if QMessageBox.question(self, "Kustuta", q) != QMessageBox.Yes:
            return
        self.push_undo()
        for i in ids:
            self.project.remove_part(i)
        self.selected = None
        self.sel = set()
        self.refresh_all()

    # ================================================================== omadused
    def _list_multi(self):
        ids = {it.data(Qt.UserRole) for it in self.part_list.selectedItems()}
        self.sel = ids if len(ids) > 1 else set()
        self.update_highlight()
        if len(ids) > 1:
            self.statusBar().showMessage(f"Valitud {len(ids)} detaili.", 3000)

    def selected_ids(self):
        ids = set(self.sel)
        if self.selected is not None:
            ids.add(self.selected)
        return [p.id for p in self.project.parts if p.id in ids]

    def _list_selected(self, cur, prev):
        if cur is None:
            return
        pid = cur.data(Qt.UserRole)
        if pid != self.selected:
            self.selected = pid
            self.load_props()
            self.update_highlight()

    def load_props(self):
        p = self.project.part(self.selected)
        self.props_widget.setEnabled(p is not None)
        widgets = [self.p_name, self.p_mat, self.p_t, self.p_w, self.p_h, self.p_r, self.p_desc] + self.p_pos + self.p_rot
        for w in widgets:
            w.blockSignals(True)
        try:
            if p is None:
                self.p_handle.setVisible(False)
                self.p_name.setText(""); self.p_info.setText("Vali detail nimekirjast või 3D vaates.")
                self.p_fast.clear()
                return
            self.p_name.setText(T(p.name))
            hd = getattr(p, "handle", None)
            self.p_handle.setVisible(bool(hd))
            if hd:
                self.p_handle.load(hd)
            self.p_mat.setCurrentText(T(p.material))
            self.p_color.setStyleSheet(f"background-color:{p.color};border:1px solid #777;min-height:20px")
            self.p_t.setValue(p.thickness)
            self.p_t.setEnabled(p.kind == "plate")
            is_rect = p.kind == "plate" and p.source == "rect"
            for w in (self.p_w, self.p_h, self.p_r, self.lbl_w, self.lbl_h, self.lbl_r):
                w.setVisible(is_rect)
            if is_rect:
                self.p_w.setValue(p.rect[0]); self.p_h.setValue(p.rect[1]); self.p_r.setValue(p.rect[2])
            for s, v in zip(self.p_pos, p.position):
                s.setValue(v)
            for s, v in zip(self.p_rot, geom.matrix_to_euler(p.R)):
                s.setValue(v)
            self.p_desc.setPlainText(T(p.description))
            for k_, cb in self.e_cb.items():
                cb.blockSignals(True); cb.setChecked(p.edge_t(k_) > 0); cb.blockSignals(False)
            ts_ = [p.edge_t(k_) for k_ in self.e_cb if p.edge_t(k_) > 0]
            if ts_:
                self.e_t.blockSignals(True); self.e_t.setCurrentText(f"{ts_[0]:g}"); self.e_t.blockSignals(False)
            self.gb_edges.setEnabled(p.kind == "plate")
            self.p_finish.blockSignals(True)
            self.p_finish.setCurrentIndex(max(0, self.p_finish.findData(getattr(p, "finish", "") or "")))
            self.p_finish.blockSignals(False)
            L, W, Tk = p.dims()
            lo, hi = p.world_bounds()
            _, ok = p.display_mesh()
            src = {"rect": "ristkülik", "image": "pildist kontuur", "ai": "AI 3D", "file": "3D fail"}.get(p.source, p.source)
            self.p_info.setText(
                f"<b>Mõõdud:</b> {L:g} × {W:g} × {Tk:g} mm"
                + (f" &nbsp; <b>Lõikemõõt:</b> {p.cut_dims()[0]:g} × {p.cut_dims()[1]:g}" if p.edge_code() else "")
                + f"<br><b>Allikas:</b> {src}<br>"
                f"<b>Ruumis:</b> X {lo[0]:.0f}…{hi[0]:.0f}, Y {lo[1]:.0f}…{hi[1]:.0f}, Z {lo[2]:.0f}…{hi[2]:.0f}<br>"
                f"<b>Auke:</b> {len(p.holes)}" + ("" if ok or not p.holes else " (näidatud tumedalt – kujund pole kinnine)"))
            self.p_fast.clear()
            for f in self.project.fasteners:
                if p.id in (f.a_id, f.b_id):
                    other = self.project.part(f.b_id if f.a_id == p.id else f.a_id)
                    it = QListWidgetItem(T(f"{FASTENER_TYPES[f.ftype]['short']} ↔ {other.name if other else '?'}"))
                    it.setData(Qt.UserRole, f.id)
                    self.p_fast.addItem(it)
        finally:
            if lang() == "en":
                self.p_info.setText(T(self.p_info.text()))
            for w in widgets:
                w.blockSignals(False)

    def apply_props(self, *a):
        p = self.project.part(self.selected)
        if not p:
            return
        nm = self.p_name.text() or T(p.name)
        mt = self.p_mat.currentText()
        new = dict(name=p.name if nm == T(p.name) else nm,
                   material=p.material if mt == T(p.material) else mt,
                   thickness=self.p_t.value())
        rect = [self.p_w.value(), self.p_h.value(), self.p_r.value()]
        geo_change = (p.kind == "plate" and (abs(new["thickness"] - p.thickness) > 1e-6 or
                      (p.source == "rect" and any(abs(a - b) > 1e-6 for a, b in zip(rect, p.rect)))))
        if new["name"] == p.name and new["material"] == p.material and not geo_change:
            return
        self.push_undo()
        p.name, p.material = new["name"], new["material"]
        if geo_change:
            p.thickness = new["thickness"]
            if p.source == "rect":
                p.set_rect(*rect)
        self.refresh_all(keep_props=not geo_change)

    def _desc_changed(self):
        p = self.project.part(self.selected)
        if p and T(p.description) != self.p_desc.toPlainText():
            p.description = self.p_desc.toPlainText()
            self.dirty = True; self.update_title()

    def apply_transform(self, *a):
        p = self.project.part(self.selected)
        if not p:
            return
        pos = [s.value() for s in self.p_pos]
        rot = [s.value() for s in self.p_rot]
        R = geom.euler_to_matrix(*rot)
        if np.allclose(pos, p.position, atol=1e-6) and np.allclose(R, p.R, atol=1e-6):
            return
        self.push_undo()
        p.position = pos
        p.R = R
        self.update_transforms()
        self.load_props()

    def pick_color(self):
        p = self.project.part(self.selected)
        if not p:
            return
        c = QColorDialog.getColor(QColor(p.color), self)
        if c.isValid():
            self.push_undo(); p.color = c.name(); self.refresh_all()

    def rotate90(self, ax):
        ps = [self.project.part(i) for i in self.selected_ids()]
        if not ps:
            return
        self.push_undo()
        los, his = zip(*[q.world_bounds() for q in ps])
        c = (np.min(los, axis=0) + np.max(his, axis=0)) / 2
        Rm = {"X": geom.rot_x, "Y": geom.rot_y, "Z": geom.rot_z}[ax](90)
        for p in ps:
            p.R = Rm @ p.R
            p.position = (Rm @ (np.asarray(p.position) - c) + c).tolist()
        self.update_transforms(); self.load_props()

    def to_floor(self):
        p = self.project.part(self.selected)
        if not p:
            return
        self.push_undo()
        lo, _ = p.world_bounds()
        p.position[2] -= lo[2]
        self.update_transforms(); self.load_props()

    def nudge_dialog(self):
        p = self.project.part(self.selected)
        if not p:
            return
        t, ok = QInputDialog.getText(self, "Nihuta", "Nihe X Y Z mm (nt: 0 0 -18):", text="0 0 0")
        if not ok:
            return
        try:
            v = [float(x.replace(",", ".")) for x in t.split()]
            v = (v + [0, 0, 0])[:3]
        except ValueError:
            return
        self.push_undo()
        p.position = (np.asarray(p.position) + v).tolist()
        self.update_transforms(); self.load_props()

    # ================================================================== 3D vaade
    def refresh_all(self, reset_camera=False, keep_props=False):
        self.refresh_list()
        self.rebuild_scene()
        if not keep_props:
            self.load_props()
        if reset_camera:
            self.view("iso")
        self.plotter.render()

    def refresh_list(self):
        self.part_list.blockSignals(True)
        self.part_list.clear()
        for p in self.project.parts:
            L, W, Tk = p.dims()
            it = QListWidgetItem(f"{T(p.name)}   ({L:g}×{W:g}×{Tk:g})")
            it.setData(Qt.UserRole, p.id)
            bg = QColor(p.color).lighter(130)
            it.setBackground(bg)
            it.setForeground(QColor("#ffffff") if bg.lightness() < 110 else QColor("#111"))
            self.part_list.addItem(it)
        sel = set(self.selected_ids())
        for k in range(self.part_list.count()):
            it = self.part_list.item(k)
            pid = it.data(Qt.UserRole)
            if pid == self.selected:
                self.part_list.setCurrentItem(it)
            it.setSelected(pid in sel)
        self.part_list.blockSignals(False)

    def _offsets(self):
        return scene.explode_offsets(self.project, self.explode.value() / 100.0 * 1.2)

    def rebuild_scene(self):
        pl = self.plotter
        for a in getattr(self, "_dim_actors", []):
            pl.remove_actor(a, render=False)
        self._dim_actors = []
        for pid, (a, actors) in self.part_actors.items():
            for x in actors:
                pl.remove_actor(x, render=False)
        for x in self.fast_actors:
            pl.remove_actor(x, render=False)
        self.part_actors, self.fast_actors = {}, []
        offs = self._offsets()
        xray = self.cb_xray.isChecked()
        for p in self.project.parts:
            try:
                a, actors = scene.add_part(pl, p, opacity=0.35 if xray and p.id != self.selected else 1.0,
                                           offset=offs.get(p.id))
            except Exception as e:  # vigane kujund
                print("Detaili joonistamine ebaõnnestus:", p.name, e)
                continue
            self.part_actors[p.id] = (a, actors)
        if self.cb_hw.isChecked() or xray:
            for f in self.project.fasteners:
                self.fast_actors += scene.add_fastener(pl, self.project, f, offset=offs.get(f.a_id))
        self.update_highlight(render=False)
        if getattr(self, "a_dims", None) is not None and self.a_dims.isChecked() and not self._offsets():
            self._dim_actors = self.add_overall_dims()

    def update_transforms(self):
        offs = self._offsets()
        if offs:
            self.rebuild_scene(); self.plotter.render(); return
        for p in self.project.parts:
            if p.id in self.part_actors:
                M = p.transform()
                for x in self.part_actors[p.id][1]:
                    x.user_matrix = M
        for x in self.fast_actors:
            pass
        # kinnitused liiguvad A detailiga: lihtsaim on uuesti joonistada
        for x in self.fast_actors:
            self.plotter.remove_actor(x, render=False)
        self.fast_actors = []
        if self.cb_hw.isChecked() or self.cb_xray.isChecked():
            for f in self.project.fasteners:
                self.fast_actors += scene.add_fastener(self.plotter, self.project, f)
        self.refresh_list()
        self.update_highlight(render=False)
        self.plotter.render()
        self.dirty = True; self.update_title()

    def update_highlight(self, render=True):
        selset = set(self.selected_ids())
        for pid, (a, actors) in self.part_actors.items():
            sel = pid in selset
            if len(actors) > 1:
                e = actors[1]
                e.prop.color = "#ff7f00" if sel else "#3a3a3a"
                e.prop.line_width = 3.5 if sel else 1.2
        self.highlight_fasteners(render=False)
        if render:
            self.plotter.render()

    def highlight_fasteners(self, render=True):
        it = self.p_fast.currentItem() if hasattr(self, "p_fast") else None
        fid = it.data(Qt.UserRole) if it else None
        for a in getattr(self, "_hl_actors", []):
            self.plotter.remove_actor(a, render=False)
        self._hl_actors = []
        if fid is not None and self.project.fastener(fid):
            self._hl_actors = scene.add_fastener(self.plotter, self.project, self.project.fastener(fid),
                                                 offset=self._offsets().get(self.project.fastener(fid).a_id),
                                                 highlight=True, name_prefix="hl")
        if render:
            self.plotter.render()

    def view(self, which):
        pl = self.plotter
        if not self.project.parts:
            pl.view_isometric(); return
        lo, hi = self.project.bounds(); c = (lo + hi) / 2
        L = float(np.linalg.norm(hi - lo)) or 1000
        if which == "iso":
            scene.set_iso_camera(pl, self.project)
        else:
            eye = {"front": (0, -2.5 * L, 0), "back": (0, 2.5 * L, 0), "right": (2.5 * L, 0, 0),
                   "left": (-2.5 * L, 0, 0), "top": (0, 0, 2.5 * L), "side": (2.5 * L, 0, 0)}[which]
            up = (0, 1, 0) if which == "top" else (0, 0, 1)
            pl.camera_position = [tuple(c + np.array(eye)), tuple(c), up]
            pl.reset_camera()
        names = {"iso": "Iso", "front": "Eest", "back": "Tagant", "right": "Paremalt", "left": "Vasakult",
                 "top": "Pealt", "side": "Küljelt"}
        self.statusBar().showMessage(f"Vaade: {T(names.get(which, which))}"
                                     + ("  (lukus – L vabastab)" if self.view_locked else "  (L = lukusta)"), 4000)
        pl.render()

    def toggle_lock(self, *a):
        self.view_locked = not self.view_locked
        self.a_lock.setChecked(self.view_locked)
        self.a_lock.setText(T("🔓 Vabasta vaade" if self.view_locked else "🔒 Lukusta vaade"))
        self.statusBar().showMessage(
            "Vaade LUKUS: vasak hiir nihutab, ratas suumib, pööramine keelatud. L = vabasta."
            if self.view_locked else "Vaade vaba: vasak hiir pöörab.", 5000)

    def toggle_ortho(self, *a):
        on = not bool(self.plotter.camera.parallel_projection)
        if on:
            self.plotter.enable_parallel_projection()
        else:
            self.plotter.disable_parallel_projection()
        self.a_ortho.setChecked(on)
        self.plotter.render()

    def key_nudge(self, ev):
        """Nooleklahvid liigutavad valitud detaili: 10 mm, Shift = 1 mm, Ctrl = 100 mm. PgUp/PgDn = Z."""
        k = ev.key()
        dirs = {Qt.Key_Left: (-1, 0, 0), Qt.Key_Right: (1, 0, 0), Qt.Key_Up: (0, 1, 0),
                Qt.Key_Down: (0, -1, 0), Qt.Key_PageUp: (0, 0, 1), Qt.Key_PageDown: (0, 0, -1)}
        if k not in dirs:
            return False
        ps = [self.project.part(i) for i in self.selected_ids()]
        if not ps:
            return True
        step = 1.0 if ev.modifiers() & Qt.ShiftModifier else (100.0 if ev.modifiers() & Qt.ControlModifier else 10.0)
        self.push_undo()
        for p in ps:
            p.position = (np.asarray(p.position) + np.asarray(dirs[k]) * step).tolist()
        self.update_transforms(); self.load_props()
        return True

    def show_keys(self):
        QMessageBox.information(self, T("Klahvid ja hiir"), KEYS_TEXT_EN if lang() == "en" else KEYS_TEXT)

    # ================================================================== klikid ja tööriistad
    def set_mode(self, mode):
        self.mode = mode
        self.a_mate.setChecked(mode in ("mate1", "mate2"))
        self.a_fast.setChecked(mode == "fastener")
        if hasattr(self, "a_measure"):
            self.a_measure.setChecked(mode == "measure")
            if mode != "measure":
                self._clear_measure()
        self._clear_marker()
        if mode != "select" and self.explode.value():
            self.explode.setValue(0)
        msg = {"select": "Valimine: kliki detailil. Hiire vasak = pööra, parem/ratas = suumi, keskmine = nihuta.",
               "mate1": "LIIDA 1/2: kliki pinnal, mille vastu teine detail tuleb (see detail jääb paigale). Esc = katkesta.",
               "mate2": "LIIDA 2/2: kliki liigutatava detaili pinnal, mis läheb esimese vastu.",
               "fastener": "KINNITUS: kliki detaili VÄLISPINNAL kohas, kust kinnitus läheb läbi teise detaili sisse. Esc = lõpeta.",
               "measure": "MÕÕTMINE: kliki kahte punkti detailide pinnal. Esc = lõpeta."}[mode]
        self.statusBar().showMessage(msg)
        if mode == "mate1":
            self.mate_first = None

    def _clear_marker(self):
        if self.marker is not None:
            self.plotter.remove_actor(self.marker, render=False)
            self.marker = None
        self.plotter.render()

    def pick(self, qpoint, widget):
        dpr = widget.devicePixelRatioF()
        x = qpoint.x() * dpr
        y = (widget.height() - qpoint.y() - 1) * dpr
        ren = self.plotter.renderer
        if not self.picker.Pick(x, y, 0, ren):
            return None
        act = self.picker.GetActor()
        pid = None
        for k, (a, actors) in self.part_actors.items():
            if a is act or (act is not None and a.GetAddressAsString("vtkObject") == act.GetAddressAsString("vtkObject")):
                pid = k; break
        if pid is None:
            return None
        part = self.project.part(pid)
        cid = self.picker.GetCellId()
        pos = np.array(self.picker.GetPickPosition())
        pos -= self._offsets().get(pid, 0)
        pvm = scene._pv_cache(part)[0]
        tri = pvm.faces.reshape(-1, 4)[cid, 1:]
        pts = pvm.points[tri]
        n_local = geom.unit(np.cross(pts[1] - pts[0], pts[2] - pts[0]))
        n = part.R @ n_local
        # pinnal olev punkt täpsemaks: projitseeri kolmnurga tasandile
        p0w = part.R @ pts[0] + np.asarray(part.position)
        pos = pos - n * float(np.dot(pos - p0w, n))
        return part, pos, n

    def on_click(self, qpoint, widget):
        try:
            hit = self.pick(qpoint, widget)
        except Exception:
            traceback.print_exc()
            return
        if self.mode == "select":
            ctrl = bool(QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
            if ctrl and hit:
                ids = set(self.selected_ids())
                pid = hit[0].id
                if pid in ids:
                    ids.discard(pid)
                    self.selected = next(iter(ids), None) if self.selected == pid else self.selected
                else:
                    ids.add(pid)
                    self.selected = pid
                self.sel = ids if len(ids) > 1 else set()
            else:
                self.sel = set()
                self.selected = hit[0].id if hit else None
            self.refresh_list(); self.load_props(); self.update_highlight()
            if hit:
                L, W, Tk = hit[0].dims()
                self.statusBar().showMessage(f"{hit[0].name}: {L:g} × {W:g} × {Tk:g} mm", 4000)
        elif self.mode == "mate1":
            if not hit:
                return
            self.mate_first = hit
            self._show_marker(hit[1], hit[2])
            self.set_mode_keep("mate2")
        elif self.mode == "mate2":
            if not hit or hit[0].id == self.mate_first[0].id:
                self.statusBar().showMessage("Vali TEISE detaili pind.", 3000)
                return
            self.do_mate(self.mate_first, hit)
            self.set_mode("select")
        elif self.mode == "fastener":
            if not hit:
                return
            self.do_fastener(hit)
        elif self.mode == "measure":
            if hit:
                self.measure_click(hit[1])

    def set_mode_keep(self, mode):
        self.mode = mode
        self.statusBar().showMessage("LIIDA 2/2: kliki liigutatava detaili pinnal, mis läheb esimese vastu. Esc = katkesta.")

    def _show_marker(self, pos, n):
        self._clear_marker()
        lo, hi = self.project.bounds()
        L = float(np.linalg.norm(hi - lo)) or 500
        arrow = pv.Arrow(start=pos, direction=n, scale=L * 0.08)
        self.marker = self.plotter.add_mesh(arrow, color="#e0312b", pickable=False, reset_camera=False)
        self.plotter.render()

    def do_mate(self, first, second):
        A, pA, nA = first
        B, pB, nB = second
        self.push_undo()
        R = geom.rotation_between(nB, -nA)
        B.R = R @ B.R
        B.position = (R @ (np.asarray(B.position) - pB) + pB).tolist()
        # B klikipunkt pärast pööret on endiselt pB; lükka see A klikipunkti
        B.position = (np.asarray(B.position) + (pA - pB)).tolist()
        # joonda servad (kui on lähedal)
        alo, ahi = A.world_bounds()
        blo, bhi = B.world_bounds()
        shift = np.zeros(3)
        for i in range(3):
            if abs(nA[i]) > 0.5:
                continue
            cands = [alo[i] - blo[i], ahi[i] - bhi[i], alo[i] - bhi[i], ahi[i] - blo[i]]
            best = min(cands, key=abs)
            if abs(best) <= 40:
                shift[i] = best
        B.position = (np.asarray(B.position) + shift).tolist()
        self.project.note_assembled(A.id, B.id)
        self.selected = B.id
        self._clear_marker()
        self.refresh_all()
        self.statusBar().showMessage(f"'{B.name}' liidetud detaili '{A.name}' külge. "
                                     "Täpsusta vajadusel asukohta paremalt paneelilt.", 6000)

    def fastener_settings(self):
        k = self.f_combo.currentData()
        d = dlg.FastenerParamsDialog(k, self.fparams.get(k), self)
        if d.exec():
            self.fparams[k] = d.values()

    def do_fastener(self, hit):
        part, pos, n = hit
        k = self.f_combo.currentData()
        before = self.project.snapshot()
        try:
            f, warns = add_fastener(self.project, k, self.fparams.get(k), part, pos, n,
                                    self.flip_cb.isChecked())
        except FastenerError as e:
            self.project = Project.from_dict(before)
            self.statusBar().showMessage(f"⚠ {e}", 8000)
            QApplication.beep()
            return
        except Exception as e:
            traceback.print_exc()
            self.project = Project.from_dict(before)
            QMessageBox.warning(self, "Viga", str(e)); return
        self.undo_stack.append(before); self.redo_stack.clear(); self.dirty = True; self.update_title()
        self.project.note_assembled(f.a_id, f.b_id)
        self.selected = part.id
        self.refresh_all()
        B = self.project.part(f.b_id)
        self.statusBar().showMessage(
            f"✔ {FASTENER_TYPES[k]['short']}: {part.name} → {B.name}. "
            + (" ".join(warns) + " " if warns else "") + "Kliki järgmist kohta või Esc.", 8000)

    def delete_fastener(self):
        it = self.p_fast.currentItem()
        if not it:
            return
        self.push_undo()
        self.project.remove_fastener(it.data(Qt.UserRole))
        self.refresh_all()

    # ================================================================== nimekiri, juhend, eksport
    # ---------------------------------------------------------------- servakant / pind
    def apply_edges(self, *a):
        ps = [self.project.part(i) for i in self.selected_ids()]
        ps = [p for p in ps if p and p.kind == "plate"]
        if not ps:
            return
        t = float(self.e_t.currentText())
        self.push_undo()
        for p in ps:
            p.edges = {k: (t if cb.isChecked() else 0) for k, cb in self.e_cb.items()}
            p.edges = {k: v for k, v in p.edges.items() if v}
        self.load_props()

    def set_all_edges(self, on):
        for cb in self.e_cb.values():
            cb.blockSignals(True); cb.setChecked(on); cb.blockSignals(False)
        self.apply_edges()

    def apply_finish(self, *a):
        ps = [self.project.part(i) for i in self.selected_ids()]
        if not ps:
            return
        self.push_undo()
        for p in ps:
            p.finish = self.p_finish.currentData() or ""
        self.refresh_all(keep_props=True)

    # ---------------------------------------------------------------- valik
    def select_group(self):
        p = self.project.part(self.selected)
        if not p:
            return
        g = getattr(p, "group", "")
        if not g:
            self.statusBar().showMessage("Sellel detailil pole gruppi.", 3000); return
        self.sel = {q.id for q in self.project.parts if getattr(q, "group", "") == g}
        self.refresh_list(); self.update_highlight()
        self.statusBar().showMessage(f"Valitud grupp '{g}': {len(self.sel)} detaili.", 4000)

    def select_all(self):
        if not self.project.parts:
            return
        self.sel = {p.id for p in self.project.parts}
        self.selected = self.project.parts[0].id
        self.refresh_list(); self.load_props(); self.update_highlight()

    # ---------------------------------------------------------------- mõõtmine
    def _clear_measure(self):
        for a in getattr(self, "_meas_actors", []):
            self.plotter.remove_actor(a, render=False)
        self._meas_actors, self._meas_pts = [], []
        self.plotter.render()

    def measure_click(self, pos):
        if not hasattr(self, "_meas_pts") or len(self._meas_pts) >= 2:
            self._clear_measure()
        self._meas_pts.append(np.asarray(pos, float))
        lo, hi = self.project.bounds()
        r = max(3.0, float(np.linalg.norm(hi - lo)) * 0.004)
        self._meas_actors.append(self.plotter.add_mesh(pv.Sphere(radius=r, center=pos), color="#e0312b",
                                                       pickable=False, reset_camera=False))
        if len(self._meas_pts) == 2:
            a, b = self._meas_pts
            d = b - a
            self._meas_actors.append(self.plotter.add_mesh(pv.Line(a, b), color="#e0312b", line_width=3,
                                                           pickable=False, reset_camera=False))
            txt = f"{np.linalg.norm(d):.1f} mm  (ΔX {abs(d[0]):.1f}, ΔY {abs(d[1]):.1f}, ΔZ {abs(d[2]):.1f})"
            self._meas_actors.append(self.plotter.add_point_labels(
                np.array([(a + b) / 2]), [txt], font_size=14, point_size=1, show_points=False,
                shape_color="#fff3c4", always_visible=True, reset_camera=False))
            self.statusBar().showMessage(f"Kaugus: {txt}", 15000)
        self.plotter.render()

    def add_overall_dims(self, force=False):
        if not self.project.parts:
            return []
        lo, hi = self.project.bounds()
        size = hi - lo
        off = max(40.0, float(np.linalg.norm(size)) * 0.04)
        pl = self.plotter
        acts = []
        segs = [((lo[0], lo[1] - off, lo[2]), (hi[0], lo[1] - off, lo[2]), f"{size[0]:.0f}"),
                ((hi[0] + off, lo[1], lo[2]), (hi[0] + off, hi[1], lo[2]), f"{size[1]:.0f}"),
                ((hi[0] + off, lo[1] - off, lo[2]), (hi[0] + off, lo[1] - off, hi[2]), f"{size[2]:.0f}")]
        for a, b, t in segs:
            acts.append(pl.add_mesh(pv.Line(a, b), color="#1f6fd1", line_width=2, pickable=False, reset_camera=False))
            for e in (a, b):
                acts.append(pl.add_mesh(pv.Sphere(radius=off * 0.08, center=e), color="#1f6fd1", pickable=False,
                                        reset_camera=False))
            acts.append(pl.add_point_labels(np.array([(np.array(a) + np.array(b)) / 2]), [t + " mm"], font_size=15,
                                            point_size=1, show_points=False, shape_color="#e3efff",
                                            always_visible=True, reset_camera=False))
        return acts

    # ---------------------------------------------------------------- uued aknad
    def _two_sides(self, what):
        ids = self.selected_ids()
        if len(ids) != 2:
            QMessageBox.information(self, T(what), T("Vali kaks küljeseina: kliki esimesel, siis Ctrl + klikk teisel."))
            return None
        return [self.project.part(i) for i in ids]

    def _run_builder(self, fn, *args):
        before = self.project.snapshot()
        try:
            made = fn(self.project, *args)
        except Exception as e:
            traceback.print_exc()
            self.project = Project.from_dict(before)
            QMessageBox.warning(self, T("Viga"), str(e)); return None
        self.undo_stack.append(before); self.redo_stack.clear(); self.dirty = True; self.update_title()
        self.sel = set()
        if made:
            self.selected = made[0].id
        self.refresh_all()
        return made

    def add_doors(self):
        from . import ui_extra as UX, drawers as D
        ab = self._two_sides("Uksed")
        if not ab:
            return
        try:
            d = UX.DoorDialog(self.project, *ab, parent=self)
        except D.DrawerError as e:
            QMessageBox.warning(self, T("Uksed"), str(e)); return
        if d.exec():
            from . import builders as BU
            made = self._run_builder(BU.add_doors, *ab, d.options())
            if made:
                self.statusBar().showMessage(f"Lisatud {sum(1 for p in made if p.name.endswith('uks'))} ust koos hingedega.", 6000)

    def add_shelves_ui(self):
        from . import ui_extra as UX, drawers as D
        ab = self._two_sides("Riiulid")
        if not ab:
            return
        try:
            d = UX.ShelfDialog(self.project, *ab, parent=self)
        except D.DrawerError as e:
            QMessageBox.warning(self, T("Riiulid"), str(e)); return
        if d.exec():
            from . import builders as BU
            self._run_builder(BU.add_shelves, *ab, d.options())

    def add_template(self):
        from . import ui_extra as UX, builders as BU
        d = UX.TemplateDialog(self)
        if not d.exec():
            return
        kind, o = d.options()
        o["x0"] = 0.0 if not self.project.parts else float(self.project.bounds()[1][0]) + 300
        made = self._run_builder(BU.build_template, kind, o)
        if made:
            self.view("iso")
            self.statusBar().showMessage(f"Mall loodud: {len(made)} detaili.", 6000)

    def show_cutplan(self):
        if not self.project.parts:
            return
        from .ui_extra import CutPlanDialog
        CutPlanDialog(self.project, self).exec()

    def show_drilling(self):
        if not self.project.parts:
            return
        from .drilling import DrillDialog
        DrillDialog(self.project, self).exec()

    def run_check(self):
        from .ui_extra import CheckDialog
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            d = CheckDialog(self.project, self, self)
        finally:
            QApplication.restoreOverrideCursor()
        d.exec()

    def make_presentation(self):
        if not self.project.parts:
            return
        from .ui_extra import PresentDialog
        d = PresentDialog(self, self)
        if d.exec():
            path = d.make()
            if path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def show_prices(self):
        if not self.project.parts:
            QMessageBox.information(self, T("Maksumus"), T("Projekt on tühi.")); return
        from .price_dialog import PriceDialog
        snap = self.project.snapshot()
        d = PriceDialog(self.project, self)
        d.exec()
        if d.changed:
            self.undo_stack.append(snap); self.redo_stack.clear()
            self.dirty = True; self.update_title()

    def show_cutlist(self):
        dlg.CutListDialog(self.project, self).exec()

    def edit_steps(self):
        snap = self.project.snapshot()
        d = dlg.StepsDialog(self.project, self)
        if d.exec():
            self.undo_stack.append(snap); self.dirty = True; self.update_title()

    def make_manual(self):
        if not self.project.parts:
            QMessageBox.information(self, "Juhend", "Projekt on tühi."); return
        covered = {pid for st in self.project.steps for pid in st.part_ids}
        if not self.project.steps or ({p.id for p in self.project.parts} - covered):
            self.project.auto_steps()
        r = QMessageBox.question(self, "Monteerimisjuhend",
                                 f"Sammud: {len(self.project.steps)}. Kas tahad enne samme vaadata/muuta?",
                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
        if r == QMessageBox.Cancel:
            return
        if r == QMessageBox.Yes:
            if not dlg.StepsDialog(self.project, self).exec():
                return
        base = os.path.dirname(self.path) if self.path else self.settings.value("dir", os.path.expanduser("~"))
        out = QFileDialog.getExistingDirectory(self, T("Kuhu juhend salvestada?"), base)
        if not out:
            return
        safe = "".join(c for c in self.project.name if c.isalnum() or c in " _-").strip() or "mobel"
        out_dir = os.path.join(out, f"{safe}_juhend")
        from . import manual
        manual.set_shared_plotter(self.plotter)
        cam = self.plotter.camera_position
        prog = QProgressDialog(T("Teen pilte…"), None, 0, 100, self)
        prog.setWindowModality(Qt.WindowModal); prog.setMinimumDuration(0); prog.setValue(0)

        def cb(v, msg):
            prog.setValue(v); prog.setLabelText(T(f"Teen pilte: {msg}")); QApplication.processEvents()
        try:
            html_path, imgs, text = manual.build_manual(self.project, out_dir, cb)
            pdf = os.path.join(out_dir, f"{safe}_monteerimisjuhend.pdf")
            manual.html_to_pdf(text, imgs, pdf)
            manual.export_csv(self.project, os.path.join(out_dir, f"{safe}_nimekiri.csv"))
        except Exception as e:
            traceback.print_exc()
            prog.close()
            self._restore_view(cam)
            QMessageBox.warning(self, "Viga", f"Juhendi tegemine ebaõnnestus:\n{e}")
            return
        prog.close()
        self._restore_view(cam)
        self.dirty = True; self.update_title()
        QDesktopServices.openUrl(QUrl.fromLocalFile(pdf))
        self.statusBar().showMessage(f"Juhend valmis: {out_dir}", 10000)

    def _restore_view(self, cam):
        self.part_actors, self.fast_actors, self._hl_actors = {}, [], []
        self.marker = None
        self.plotter.clear_actors()
        self.plotter.set_background("#f7f8fa", top="#dfe5ec")
        try:
            self.plotter.show_axes()
        except Exception:
            pass
        self.rebuild_scene()
        self.plotter.camera_position = cam
        self.plotter.render()

    def check_gl_runtime(self):
        """Kontrollib, millise OpenGL-i 3D vaade tegelikult sai. Kui alla 3.2, lülitab tarkvara peale."""
        try:
            from PySide6.QtGui import QOpenGLContext
            ctx = self.plotter.context()
            if ctx is None:
                gl_log("3D vaate kontekst puudub")
                return
            f = ctx.format()
            ver = (f.majorVersion(), f.minorVersion())
            renderer = ""
            try:
                self.plotter.makeCurrent()
                renderer = ctx.functions().glGetString(0x1F01) or ""
                renderer = renderer.decode() if isinstance(renderer, bytes) else str(renderer)
                self.plotter.doneCurrent()
            except Exception as e:
                renderer = f"? ({e})"
            sw = os.environ.get("QT_OPENGL") == "software"
            gl_log(f"3D vaade (Qt): OpenGL {ver[0]}.{ver[1]}, {renderer}, tarkvara={'jah' if sw else 'ei'}")
            try:
                caps = self.plotter.ren_win.ReportCapabilities() or ""
                gl_log("VTK näeb:\n" + "\n".join(caps.splitlines()[:6]))
            except Exception as e:
                gl_log(f"VTK capabilities viga: {e}")
            self.gl_info = f"OpenGL {ver[0]}.{ver[1]} – {renderer}"
            if ver < (3, 2) and not sw:
                self.settings.setValue("gl_mode", "sw")
                QMessageBox.information(
                    self, "Graafika",
                    f"Sinu videokaart annab ainult OpenGL {ver[0]}.{ver[1]} ({renderer}).\n"
                    "3D vaade vajab vähemalt 3.2.\n\nLülitan tarkvaralise joonistamise peale "
                    "ja käivitan programmi uuesti.")
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv)
                self.dirty = False
                QApplication.quit()
            elif ver < (3, 2) and sw:
                dll = _sw_dll()
                QMessageBox.warning(
                    self, "Graafika",
                    f"Ka tarkvaraline OpenGL ei tööta (OpenGL {ver[0]}.{ver[1]}).\n"
                    f"opengl32sw.dll: {'olemas' if os.path.exists(dll) else 'PUUDUB'}\n\n"
                    "Saada mulle fail graafika.txt.")
        except Exception as e:
            gl_log(f"kontroll ebaõnnestus: {e}")

    def gl_mode_dialog(self):
        cur = self.settings.value("gl_mode", "auto")
        QMessageBox.information(self, "Graafika", getattr(self, "gl_info", "teadmata"))
        items = ["auto (soovitatav)", "riistvara (videokaart)", "tarkvara (aeglasem, töötab alati)"]
        keys = ["auto", "hw", "sw"]
        it, ok = QInputDialog.getItem(self, "Graafika", f"3D joonistamise režiim (praegu: {cur}).\n"
                                      "Muudatus hakkab kehtima pärast programmi taaskäivitamist.",
                                      items, keys.index(cur) if cur in keys else 0, False)
        if ok:
            self.settings.setValue("gl_mode", keys[items.index(it)])
            self.settings.remove("gl_probe")
            QMessageBox.information(self, "Graafika", "Käivita programm uuesti.")

    def export_stl(self):
        if not self.project.parts:
            return
        p, _ = QFileDialog.getSaveFileName(self, T("Ekspordi STL"), f"{self.project.name}.stl", "STL (*.stl)")
        if not p:
            return
        import trimesh
        ms = []
        for part in self.project.parts:
            m, _ = part.display_mesh()
            m = m.copy(); m.apply_transform(part.transform()); ms.append(m)
        trimesh.util.concatenate(ms).export(p)
        self.statusBar().showMessage(f"Eksporditud: {p}", 5000)

    def show_help(self):
        QMessageBox.information(self, T("Kuidas kasutada"), HELP_TEXT_EN if lang() == "en" else HELP_TEXT)


HELP_TEXT = """<b>Mööbli disainer</b><br><br>
<b>1. Detailid</b><br>
• <i>Plaat / latt</i>: sisesta mõõdud, paksus ja asend.<br>
• <i>Mööblijalad</i>: puidust (kandiline, ümar, koonusjas) või metallist (ümar/kandiline toru kinnitusplaadiga,
  kirjutuslaua raamjalg). Vali enne lauaplaat – jalad pannakse selle nurkadesse ja kinnitused lisatakse ise.<br>
• <i>Lisa sahtlid</i>: vali kaks küljeseina (Ctrl + klikk), vajuta 'Lisa sahtlid'. Programm teeb siinid,
  sahtlikastid, põhjad, esipaneelid ja käepidemed. Saab teha ka klaviatuurisahtli.
  Käepideme stiili muutmiseks kliki käepidemel – omaduste paneelis on 10 stiili.<br>
• <i>3D fail</i>: STL/OBJ/GLB (nt internetist alla laaditud jalad, käepidemed).<br><br>
• <i>Lisa uksed / Lisa riiulid</i>: vali kaks küljeseina (Ctrl + klikk). Uksed tulevad koos peitehingede ja
  aukudega, riiulid koos 32 mm süsteemi aukudega.<br>
• <i>Mallid</i>: kapp, riiul, kummut, öökapp, voodiraam – annad mõõdud, programm ehitab kõik koos kinnitustega.<br>
• Paremal paneelil: <i>servakant</i> iga serva kohta ja <i>pind</i> (tamm, pähkel, kask, mänd, saar, valge läige, must matt, betoon).<br><br>
<b>2. Kokku panemine</b><br>
• <i>🧲 Liida pinnad</i> (M): kliki paigal oleva detaili pinnale, siis liigutatava detaili pinnale.
  Teine detail keeratakse ja lükatakse vastu, servad joondatakse automaatselt (kuni 40 mm).<br>
• Täpne asukoht/pööre: parem paneel. ↻90° nupud, 'Põrandale', 'Nihuta…'.<br><br>
<b>3. Kinnitused</b> (K)<br>
Vali tüüp ülaribalt (⚙ = mõõdud), vajuta 'Lisa kinnitus' ja kliki detaili <u>välispinnale</u> kohas,
kust kinnitus läheb läbi teise detaili sisse. Augud puuritakse mõlemasse detaili automaatselt.<br>
• Minifix ja ristmutter: teine detail peab olema servaga vastu. Ekstsentrik/mutter läheb mööbli sisemisele
  poolele (linnukesega teisele poole).<br>
• Läbipolt: kaks pinnapidi kokku pandud detaili.<br><br>
<b>4. Valmistamine</b><br>
• <i>Lõikeplaan</i>: detailide paigutus täisplaatidele (PDF). <i>Puurimisjoonised</i>: iga detaili augud koos mõõtudega.<br>
• <i>Kontrolli</i>: otsib kokkupõrkeid ja serva liiga lähedal olevaid auke. <i>Esitlus</i>: ilus pilt või PDF.<br>
• <i>Mõõda</i> (D): kliki kaht punkti. <i>Üldmõõdud</i>: laius × sügavus × kõrgus 3D vaates. G = vali grupp, Ctrl+A = kõik.<br><br>
<b>5. Juhend</b><br>
'Sammud' – monteerimise järjekord (automaatne liitmise järjekorra järgi). 'Monteerimisjuhend' teeb
PDF + HTML + CSV nimekirja koos piltidega.<br><br>
<b>Klahvid ja hiir:</b> vaata Abi → Klahvid ja hiir (F2).
"""

KEYS_TEXT = """<b>Hiir 3D vaates</b>
<table cellpadding=3>
<tr><td>Vasak lohistamine</td><td>pööra vaadet (Z jääb alati üles)</td></tr>
<tr><td>Shift + vasak / keskmine nupp</td><td>nihuta vaadet</td></tr>
<tr><td>Ratas / parem lohistamine</td><td>suumi</td></tr>
<tr><td>Vasak klikk</td><td>vali detail (tööriistaga: vali pind)</td></tr>
<tr><td>Ctrl + klikk</td><td>vali mitu detaili (nt kaks küljeseina sahtlite jaoks)</td></tr>
</table>
<p><b>Klahvid</b> (töötavad, kui 3D vaade on aktiivne – kliki enne vaatesse)</p>
<table cellpadding=3>
<tr><td><b>L</b></td><td>lukusta / vabasta vaade (lukus: vasak hiir nihutab, ei pööra)</td></tr>
<tr><td><b>O</b></td><td>ortograafiline vaade sisse/välja (ilma perspektiivita)</td></tr>
<tr><td><b>1</b></td><td>eestvaade</td></tr>
<tr><td><b>2</b></td><td>tagantvaade</td></tr>
<tr><td><b>3</b></td><td>paremalt</td></tr>
<tr><td><b>4</b></td><td>vasakult</td></tr>
<tr><td><b>7</b></td><td>pealtvaade</td></tr>
<tr><td><b>0</b></td><td>isomeetriline vaade</td></tr>
<tr><td><b>F</b></td><td>sobita kõik vaatesse</td></tr>
<tr><td><b>M</b></td><td>liida pinnad</td></tr>
<tr><td><b>K</b></td><td>lisa kinnitus</td></tr>
<tr><td><b>Esc</b></td><td>tööriist maha</td></tr>
<tr><td><b>Nooled</b></td><td>liiguta valitud detaili X/Y suunas 10 mm</td></tr>
<tr><td><b>PgUp / PgDn</b></td><td>liiguta valitud detaili üles/alla 10 mm</td></tr>
<tr><td>+ <b>Shift</b> / + <b>Ctrl</b></td><td>sama nihe 1 mm / 100 mm</td></tr>
<tr><td><b>Del</b></td><td>kustuta valitud detail</td></tr>
</table>
<p><b>Kõikjal</b></p>
<table cellpadding=3>
<tr><td>Ctrl+Z / Ctrl+Y</td><td>võta tagasi / tee uuesti</td></tr>
<tr><td>Ctrl+S, Ctrl+Shift+S</td><td>salvesta, salvesta nimega</td></tr>
<tr><td>Ctrl+O, Ctrl+N</td><td>ava, uus</td></tr>
<tr><td>Ctrl+D</td><td>dubleeri detail</td></tr>
<tr><td>F1 / F2</td><td>abi / see nimekiri</td></tr>
</table>
<p>Soovitus: eestvaate jaoks vajuta <b>1</b>, siis <b>O</b> ja <b>L</b> – saad ühtlase tehnilise eestvaate,
mis ei keera ära.</p>
"""


from .glboot import gl_log, _sw_dll, setup as _gl_setup  # noqa: E402


def main(app=None, splash=None):
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    use_sw, gl_ok, final = _gl_setup()
    if app is None:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
    if not gl_ok:
        if splash:
            splash.close()
        dll = _sw_dll()
        QMessageBox.critical(
            None, APP_NAME,
            "3D vaade ei saa selles arvutis OpenGL 3.2 tuge – ka tarkvaraline režiim ei töötanud.\n\n"
            f"Test: {final}\n"
            f"opengl32sw.dll: {'olemas' if os.path.exists(dll) else 'PUUDUB'}\n\n"
            "Saada fail graafika.txt (kaustas mööbel) Claudele.")
        settings = QSettings("Foral", "Moobel")
        settings.remove("gl_probe")
        settings.remove("gl_final")
        sys.exit(1)
    app.setApplicationName(APP_NAME)
    app._i18n = ShowTranslator()
    app._i18n.install(app)
    try:
        from .logo import app_icon
        app.setWindowIcon(app_icon())
    except Exception:
        pass
    if splash:
        splash.set(88, "Ehitan 3D vaadet…")
    w = MainWindow()
    if splash:
        splash.set(100, "Valmis")
    w.show()
    if splash:
        splash.finish(w)
    QTimer.singleShot(1200, w.check_gl_runtime)
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        w.open_project(sys.argv[1])
    sys.exit(app.exec())


HELP_TEXT_EN = """<b>Furniture Designer</b><br><br>
<b>1. Parts</b><br>
• <i>Panel / batten</i>: enter dimensions, thickness and orientation.<br>
• <i>Furniture legs</i>: wooden (square, round, tapered) or metal (round/square tube with mounting plate,
  desk frame leg). Select the tabletop first – legs are placed in its corners and fasteners are added automatically.<br>
• <i>Add drawers</i>: select two side panels (Ctrl + click) and press 'Add drawers'. The program makes the slides,
  drawer boxes, bottoms, front panels and handles. A keyboard tray is also available.
  To change the handle style, click a handle – the properties panel offers 10 styles.<br>
• <i>3D file</i>: STL/OBJ/GLB (e.g. legs or handles downloaded from the internet).<br><br>
• <i>Add doors / Add shelves</i>: select two side panels (Ctrl + click). Doors come with concealed hinges and holes,
  shelves with 32 mm system holes.<br>
• <i>Templates</i>: cabinet, shelf unit, chest of drawers, bedside table, bed frame – enter sizes, everything is built with fasteners.<br>
• Right panel: <i>edge banding</i> per edge and <i>surface</i> (oak, walnut, birch, pine, ash, white gloss, matt black, concrete).<br><br>
<b>2. Assembly</b><br>
• <i>🧲 Join faces</i> (M): click a face of the part that stays, then a face of the part to move.
  The second part is rotated and pushed against the first, edges are aligned automatically (up to 40 mm).<br>
• Exact position/rotation: right panel. ↻90° buttons, 'To floor', 'Move…'.<br><br>
<b>3. Fasteners</b> (K)<br>
Choose the type in the toolbar (⚙ = dimensions), press 'Add fastener' and click the <u>outer face</u> of a part
where the fastener goes through into the other part. Holes are drilled into both parts automatically.<br>
• Minifix and cross dowel: the other part must meet it with its edge. The cam/nut goes to the inner side of the
  furniture (tick the box to put it on the other side).<br>
• Through bolt: two parts joined face to face.<br><br>
<b>4. Making</b><br>
• <i>Cutting plan</i>: parts laid out on full sheets (PDF). <i>Drilling drawings</i>: holes of each part with dimensions.<br>
• <i>Check</i>: finds collisions and holes too close to edges. <i>Presentation</i>: nice image or PDF.<br>
• <i>Measure</i> (D): click two points. <i>Overall size</i>: W × D × H in 3D. G = select group, Ctrl+A = all.<br><br>
<b>5. Guide</b><br>
'Steps' – assembly order (automatic, by the order parts were joined). 'Assembly guide' creates
a PDF + HTML + CSV list with pictures.<br><br>
<b>Keys and mouse:</b> see Help → Keys and mouse (F2).
"""

KEYS_TEXT_EN = """<b>Mouse in the 3D view</b>
<table cellpadding=3>
<tr><td>Left drag</td><td>rotate the view (Z always stays up)</td></tr>
<tr><td>Shift + left / middle button</td><td>pan the view</td></tr>
<tr><td>Wheel / right drag</td><td>zoom</td></tr>
<tr><td>Left click</td><td>select a part (with a tool: select a face)</td></tr>
<tr><td>Ctrl + click</td><td>select several parts (e.g. two side panels for drawers)</td></tr>
</table>
<p><b>Keys</b> (work when the 3D view is active – click into it first)</p>
<table cellpadding=3>
<tr><td><b>L</b></td><td>lock / unlock the view (locked: left mouse pans, does not rotate)</td></tr>
<tr><td><b>O</b></td><td>orthographic view on/off (no perspective)</td></tr>
<tr><td><b>1</b></td><td>front view</td></tr>
<tr><td><b>2</b></td><td>back view</td></tr>
<tr><td><b>3</b></td><td>from the right</td></tr>
<tr><td><b>4</b></td><td>from the left</td></tr>
<tr><td><b>7</b></td><td>top view</td></tr>
<tr><td><b>0</b></td><td>isometric view</td></tr>
<tr><td><b>F</b></td><td>fit everything in view</td></tr>
<tr><td><b>M</b></td><td>join faces</td></tr>
<tr><td><b>K</b></td><td>add fastener</td></tr>
<tr><td><b>Esc</b></td><td>cancel tool</td></tr>
<tr><td><b>Arrows</b></td><td>move the selected part 10 mm in X/Y</td></tr>
<tr><td><b>PgUp / PgDn</b></td><td>move the selected part up/down 10 mm</td></tr>
<tr><td>+ <b>Shift</b> / + <b>Ctrl</b></td><td>same move 1 mm / 100 mm</td></tr>
<tr><td><b>Del</b></td><td>delete the selected part</td></tr>
</table>
<p><b>Everywhere</b></p>
<table cellpadding=3>
<tr><td>Ctrl+Z / Ctrl+Y</td><td>undo / redo</td></tr>
<tr><td>Ctrl+S, Ctrl+Shift+S</td><td>save, save as</td></tr>
<tr><td>Ctrl+O, Ctrl+N</td><td>open, new</td></tr>
<tr><td>Ctrl+D</td><td>duplicate part</td></tr>
<tr><td>F1 / F2</td><td>help / this list</td></tr>
</table>
<p>Tip: for a front view press <b>1</b>, then <b>O</b> and <b>L</b> – you get a steady technical front view
that does not twist away.</p>
"""
