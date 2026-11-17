"""Maksumuse aken: programm täidab nimetused ja kogused, kasutaja sisestab ühikuhinnad (KM-ga)."""
import csv
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QPushButton,
    QComboBox, QCheckBox, QSpinBox, QMessageBox, QFileDialog, QDialogButtonBox, QApplication)

from . import prices as PR
from .i18n import T

COLS = ["Rühm", "Nimetus", "Selgitus", "Kogus", "Ühik", "Plaadi mõõt", "Ühikuhind (KM-ga)", "Summa"]
C_QTY, C_SHEET, C_PRICE = 3, 5, 6
OVR = QColor("#ffd9a8")
MISSING = QColor("#fff2b3")
EDIT = QColor("#eef6ff")


def _fmt(x):
    return f"{x:,.2f}".replace(",", " ").replace(".", ",")


def _num(txt):
    t = txt.replace(" ", "").replace(",", ".")
    t = re.sub(r"[^0-9.\-]", "", t)
    return float(t) if t not in ("", ".", "-") else 0.0


class PriceDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.st = PR.load()
        self.setWindowTitle("Maksumus")
        self.resize(1100, 680)
        v = QVBoxLayout(self)
        top = QLabel("Programm on täitnud vajalikud materjalid ja kogused. Kirjuta sinise taustaga lahtrisse "
                     "ühikuhind koos käibemaksuga – summa arvutatakse ise. Hinnad jäävad meelde ka "
                     "järgmisteks projektideks. Kollased read on veel ilma hinnata.")
        top.setWordWrap(True)
        v.addWidget(top)
        row = QHBoxLayout()
        row.addWidget(QLabel("Valuuta"))
        self.cur = QComboBox(); self.cur.setEditable(True)
        self.cur.addItems(["€", "$", "£", "kr", "zł", "CHF"])
        self.cur.setCurrentText(self.st.get("currency", "€"))
        self.cur.setFixedWidth(70)
        row.addWidget(self.cur)
        row.addWidget(QLabel("   Jääkide varu"))
        self.waste = QSpinBox(); self.waste.setRange(0, 100); self.waste.setSuffix(" %")
        self.waste.setValue(int(self.st.get("waste", 15)))
        row.addWidget(self.waste)
        row.addWidget(QLabel("   Plaadid:"))
        self.mode = QComboBox()
        self.mode.addItem("täisplaatidena (nii nagu poest ostad)", True)
        self.mode.addItem("ainult kulunud osa järgi", False)
        self.mode.setCurrentIndex(0 if self.st.get("whole", True) else 1)
        row.addWidget(self.mode)
        self.edging = QCheckBox("Arvesta servakanti"); self.edging.setChecked(bool(self.st.get("edging", True)))
        row.addWidget(self.edging)
        row.addStretch()
        v.addLayout(row)

        self.tbl = QTableWidget(0, len(COLS))
        self.tbl.setHorizontalHeaderLabels(COLS)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.itemChanged.connect(self._edited)
        v.addWidget(self.tbl, 1)
        self.total_lbl = QLabel()
        self.total_lbl.setStyleSheet("font-size:15px;padding:8px;background:#f6f3e8;border:1px solid #d8cfae")
        v.addWidget(self.total_lbl)
        self.warn_lbl = QLabel(); self.warn_lbl.setWordWrap(True); self.warn_lbl.setStyleSheet("color:#a33")
        v.addWidget(self.warn_lbl)
        r2 = QHBoxLayout()
        b = QPushButton("Salvesta CSV (Excel)…"); b.clicked.connect(self.save_csv); r2.addWidget(b)
        b = QPushButton("Kopeeri tekstina"); b.clicked.connect(self.copy_text); r2.addWidget(b)
        b = QPushButton("Tühjenda kõik hinnad"); b.clicked.connect(self.clear_prices); r2.addWidget(b)
        b = QPushButton("➕ Lisa oma rida"); b.clicked.connect(self.add_row); r2.addWidget(b)
        b = QPushButton("➖ Eemalda oma rida"); b.clicked.connect(self.del_row); r2.addWidget(b)
        b = QPushButton("↺ Taasta arvutatud kogused"); b.clicked.connect(self.reset_qty); r2.addWidget(b)
        r2.addStretch()
        v.addLayout(r2)
        note = QLabel("Plaadi ühikuhind on terve plaadi hind. Plaadi mõõtu saab muuta (nt 2800×2070) – selle "
                      "järgi arvutatakse, mitu plaati on vaja. Kogust saab käsitsi muuta (oranž ✎) – see jääb "
                      "selle projekti juurde; tühi lahter taastab programmi arvutuse.")
        note.setWordWrap(True); note.setStyleSheet("color:#666")
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        v.addWidget(bb)

        self.waste.valueChanged.connect(self._opts)
        self.mode.currentIndexChanged.connect(self._opts)
        self.edging.toggled.connect(self._opts)
        self.cur.currentTextChanged.connect(self._opts)
        self._loading = False
        self.changed = False
        self.refresh()

    # ---------------------------------------------------------- oma read / kogused
    def add_row(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, T("Lisa oma rida"), T("Nimetus (nt Liim, Õli, Transport):"))
        if not ok or not name.strip():
            return
        unit, ok = QInputDialog.getItem(self, T("Lisa oma rida"), T("Ühik:"), ["tk", "paar", "pakk", "m", "l", "kg", "h"], 0, True)
        if not ok:
            return
        self.project.extra_rows.append(dict(name=name.strip(), unit=unit.strip() or "tk", qty=1))
        self.changed = True
        self.refresh()

    def del_row(self):
        r = self.tbl.currentRow()
        it = self.tbl.item(r, 0) if r >= 0 else None
        ex = it.data(Qt.UserRole + 1) if it else None
        if ex is None:
            QMessageBox.information(self, T("Maksumus"), T("Vali tabelist enda lisatud rida."))
            return
        del self.project.extra_rows[ex]
        self.changed = True
        self.refresh()

    def reset_qty(self):
        if self.project.qty_override:
            self.project.qty_override.clear()
            self.changed = True
            self.refresh()

    # ---------------------------------------------------------- tabel
    def _opts(self, *a):
        self.st["waste"] = self.waste.value()
        self.st["whole"] = bool(self.mode.currentData())
        self.st["edging"] = self.edging.isChecked()
        self.st["currency"] = self.cur.currentText().strip() or "€"
        self.refresh()
        self._save()

    def refresh(self):
        self.res = r = PR.calculate(self.project, self.st)
        cur = self.st.get("currency", "€")
        self._loading = True
        self.tbl.setRowCount(len(r["rows"]))
        grp = {"plaat": T("Plaadid"), "tarvik": T("Tarvikud"), "oma": T("Lisatud")}
        for i, x in enumerate(r["rows"]):
            qty = x["qty"]
            qtxt = f"{qty:g}" if isinstance(qty, (int, float)) else str(qty)
            if x.get("overridden"):
                qtxt += " ✎"
            sheet = "×".join(f"{s:g}" for s in x["sheet"]) if x.get("sheet") else ""
            price = f"{x['unit_price']:.2f}".replace(".", ",") if x["unit_price"] else ""
            vals = [grp[x["group"]], T(x["name"]), T(x["info"]), qtxt, T(x["unit"]), sheet, price,
                    f"{_fmt(x['total'])} {cur}" if x["unit_price"] else "—"]
            for j, val in enumerate(vals):
                c = QTableWidgetItem(val)
                c.setData(Qt.UserRole, x["key"])
                editable = j in (C_PRICE, C_QTY) or (j == C_SHEET and x.get("sheet")) or \
                    (j == 1 and x["group"] == "oma")
                c.setData(Qt.UserRole + 1, x.get("extra"))
                if not editable:
                    c.setFlags(c.flags() & ~Qt.ItemIsEditable)
                if j in (3, 6, 7):
                    c.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == C_QTY and x.get("overridden"):
                    c.setBackground(OVR)
                    c.setToolTip(T(f"Muudetud käsitsi. Programmi arvutus: {x['calc_qty']:g}. "
                                   f"Tühjenda lahter, et taastada.") )
                elif j == C_QTY:
                    c.setBackground(EDIT)
                elif editable:
                    c.setBackground(EDIT if x["unit_price"] or j in (C_SHEET, 1) else MISSING)
                elif not x["unit_price"]:
                    c.setBackground(MISSING)
                self.tbl.setItem(i, j, c)
        self.tbl.resizeColumnsToContents()
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl.setColumnWidth(C_PRICE, max(self.tbl.columnWidth(C_PRICE), 130))
        self._loading = False
        miss = T(f" &nbsp;&nbsp; <span style='color:#a60'>Hind puudub {r['missing']} real</span>") if r["missing"] else ""
        self.total_lbl.setText(T(f"Plaadid: <b>{_fmt(r['panels'])} {cur}</b> &nbsp;&nbsp; Tarvikud: <b>{_fmt(r['hardware'])} {cur}</b>"
                                 f" &nbsp;&nbsp; <span style='font-size:18px'>KOKKU: <b>{_fmt(r['total'])} {cur}</b></span>") + miss)
        self.warn_lbl.setText("<br>".join("⚠ " + T(w) for w in r["warnings"]))

    def _edited(self, cell):
        if self._loading:
            return
        key = cell.data(Qt.UserRole)
        extra = cell.data(Qt.UserRole + 1)
        it = PR.item(self.st, key)
        txt = cell.text().replace("✎", "").strip()
        if cell.column() == C_QTY:
            if extra is not None:
                self.project.extra_rows[extra]["qty"] = _num(txt) if txt else 0
            elif txt == "":
                self.project.qty_override.pop(key, None)
            else:
                q = _num(txt)
                calc = next((r["calc_qty"] for r in self.res["rows"] if r["key"] == key), None)
                if calc is not None and abs(q - calc) < 1e-9:
                    self.project.qty_override.pop(key, None)
                else:
                    self.project.qty_override[key] = q
            self.changed = True
        elif cell.column() == 1 and extra is not None:
            old = "oma|" + self.project.extra_rows[extra]["name"]
            self.project.extra_rows[extra]["name"] = txt or T("Muu")
            if old in self.st["items"]:
                self.st["items"]["oma|" + self.project.extra_rows[extra]["name"]] = self.st["items"].pop(old)
            self.changed = True
        elif cell.column() == C_PRICE:
            try:
                it["price"] = _num(txt) if txt else 0.0
            except ValueError:
                QMessageBox.warning(self, T("Viga"), T("Vigane number."))
        elif cell.column() == C_SHEET:
            try:
                nums = [_num(x) for x in re.split(r"[x×*X]", txt) if x.strip()]
                if len(nums) >= 2 and nums[0] > 0 and nums[1] > 0:
                    it["sheet"] = nums[:2]
            except ValueError:
                pass
        self._save()
        row, col = cell.row(), cell.column()
        self.refresh()
        nxt = min(row + 1, self.tbl.rowCount() - 1)
        self.tbl.setCurrentCell(nxt, col)

    def _save(self):
        try:
            PR.save(self.st)
        except Exception:
            pass

    def clear_prices(self):
        if QMessageBox.question(self, T("Maksumus"), T("Kustutan kõik sisestatud hinnad?")) != QMessageBox.Yes:
            return
        for it in self.st["items"].values():
            it.pop("price", None)
        self._save()
        self.refresh()

    # ---------------------------------------------------------- eksport
    def save_csv(self):
        p, _ = QFileDialog.getSaveFileName(self, T("Salvesta maksumus"), f"{self.project.name}_maksumus.csv",
                                           "CSV (*.csv)")
        if not p:
            return
        cur = self.st.get("currency", "€")
        r = self.res
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow([T(x) for x in ["Rühm", "Nimetus", "Selgitus", "Kogus", "Ühik", "Ühikuhind (KM-ga)", "Summa"]]
                       + [cur])
            for x in r["rows"]:
                w.writerow([T("Plaadid") if x["group"] == "plaat" else T("Tarvikud"), T(x["name"]), T(x["info"]),
                            f"{x['qty']:g}".replace(".", ","), T(x["unit"]),
                            f"{x['unit_price']:.2f}".replace(".", ","), f"{x['total']:.2f}".replace(".", ",")])
            w.writerow([])
            for lab, val in (("Plaadid", r["panels"]), ("Tarvikud", r["hardware"]), ("KOKKU", r["total"])):
                w.writerow([T(lab), "", "", "", "", "", f"{val:.2f}".replace(".", ",")])

    def copy_text(self):
        cur = self.st.get("currency", "€")
        lines = [f"{self.project.name} – {T('maksumus')}"]
        for x in self.res["rows"]:
            lines.append(f"{T(x['name'])}: {x['qty']:g} {T(x['unit'])} × {_fmt(x['unit_price'])} {cur} = "
                         f"{_fmt(x['total'])} {cur}")
        lines.append(f"{T('KOKKU')}: {_fmt(self.res['total'])} {cur}")
        QApplication.clipboard().setText("\n".join(lines))
