"""Germo Mööbli disainer – käivitusfail. Topeltklikk käivitab (vajab Pythonit ja install.bat käivitamist)."""
import os
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def missing(name):
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk(); r.withdraw()
        messagebox.showerror("Mööbli disainer", f"Puudub vajalik moodul: {name}\n\nKäivita kõigepealt install.bat")
    except Exception:
        print("Puudub moodul:", name)
    sys.exit(1)


def run():
    try:
        from moobel import glboot
        glboot.setup()                      # OpenGL valik enne VTK laadimist
        from PySide6.QtWidgets import QApplication
    except ImportError as e:
        missing(e.name)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from moobel.logo import Splash, app_icon
    app.setWindowIcon(app_icon())
    splash = Splash()
    splash.show()
    splash.set(5, "Käivitan…")

    # rasked moodulid (VTK, pyvista) laetakse taustal, käivituskuva samal ajal liigub
    result = {}

    def load():
        try:
            import moobel.app as m
            result["m"] = m
        except BaseException as e:      # noqa
            result["e"] = e
            result["tb"] = traceback.format_exc()

    t = threading.Thread(target=load, daemon=True)
    t.start()
    t0 = time.time()
    stages = [(0.0, "Laen 3D mootorit (VTK)…"), (1.5, "Laen geomeetria tööriistu…"),
              (3.0, "Valmistan kinnitusi ja sahtleid…"), (5.0, "Peaaegu valmis…")]
    while t.is_alive() or time.time() - t0 < 1.6:
        el = time.time() - t0
        msg = [m for s, m in stages if el >= s][-1]
        prog = 8 + 77 * (1 - 2.71828 ** (-el / 2.5))
        splash.tick += 1
        splash.set(prog, msg)
        time.sleep(0.033)
    if "e" in result:
        splash.close()
        if isinstance(result["e"], ImportError):
            missing(result["e"].name)
        raise result["e"]
    result["m"].main(app, splash)


if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        raise
    except Exception:
        with open(os.path.join(ROOT, "viga.log"), "w", encoding="utf-8") as fh:
            traceback.print_exc(file=fh)
        raise
