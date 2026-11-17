"""OpenGL valik ENNE VTK/Qt GUI importimist.

VTK vajab OpenGL 3.2. Vanadel arvutitel (nt Intel HD 2000, i3-2100) annab videokaart ainult 3.1.
Siis kasutatakse kaustas 'mesa' olevat Mesa llvmpipe tarkvaralist OpenGL-i (4.5).
Oluline: Mesa opengl32.dll laetakse protsessi ENNE VTK-d, et nii Qt kui VTK kasutaksid sama OpenGL-i.
"""
import os
import sys

_DONE = None
FROZEN = getattr(sys, "frozen", False)
# programmi kaust: .exe kõrval (PyInstaller) või lähtekoodi kaust
ROOT = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MESA_DIR = os.path.join(ROOT, "mesa")
MESA_DLL = os.path.join(MESA_DIR, "opengl32.dll")

_GL_PROBE = r"""
import sys, os
if os.environ.get("MOOBEL_MESA_DLL"):
    import ctypes
    os.add_dll_directory(os.path.dirname(os.environ["MOOBEL_MESA_DLL"]))
    ctypes.WinDLL(os.environ["MOOBEL_MESA_DLL"])
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication, QOpenGLContext, QSurfaceFormat, QOffscreenSurface
if os.environ.get("QT_OPENGL") == "software":
    QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)
app = QGuiApplication(sys.argv)
f = QSurfaceFormat()
f.setRenderableType(QSurfaceFormat.OpenGL)
f.setProfile(QSurfaceFormat.CoreProfile)
f.setVersion(3, 2)
c = QOpenGLContext(); c.setFormat(f)
ok = c.create()
s = QOffscreenSurface(); s.setFormat(c.format()); s.create()
ok = ok and c.makeCurrent(s)
fm = c.format()
r = ""
try:
    r = c.functions().glGetString(0x1F01)
    r = r.decode() if isinstance(r, bytes) else str(r)
except Exception:
    pass
_out = "GLPROBE %d %d %d %d %s" % (int(bool(ok)), fm.majorVersion(), fm.minorVersion(), int(c.isOpenGLES()), r)
if os.environ.get("MOOBEL_PROBE_OUT"):
    open(os.environ["MOOBEL_PROBE_OUT"], "w", encoding="utf-8").write(_out)
else:
    print(_out)
"""


def probe_main():
    """Käivitatakse .exe-s argumendiga --glprobe (seal pole python -c võimalust)."""
    exec(_GL_PROBE, {"__name__": "__probe__"})


def gl_log(text, mode="a"):
    import tempfile
    for d in (ROOT, tempfile.gettempdir()):
        try:
            with open(os.path.join(d, "graafika.txt"), mode, encoding="utf-8") as fh:
                fh.write(text + "\n")
            return
        except Exception:
            continue


def _sw_dll():
    try:
        import PySide6
        return os.path.join(os.path.dirname(PySide6.__file__), "opengl32sw.dll")
    except Exception:
        return "?"


def _run_probe():
    import subprocess
    try:
        import tempfile
        flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
        out = os.path.join(tempfile.gettempdir(), f"moobel_glprobe_{os.getpid()}.txt")
        env = dict(os.environ, MOOBEL_PROBE_OUT=out)
        cmd = [sys.executable, "--glprobe"] if FROZEN else [sys.executable, "-c", _GL_PROBE]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=flags, env=env)
        txt = ""
        if os.path.exists(out):
            with open(out, encoding="utf-8") as fh:
                txt = fh.read()
            os.remove(out)
        line = [l for l in txt.splitlines() if l.startswith("GLPROBE")]
        return line[0] if line else f"GLPROBE 0 0 0 0 (viga: {(r.stderr or '').strip()[-300:]})"
    except Exception as e:
        return f"GLPROBE 0 0 0 0 (viga: {e})"


def _parse(probe):
    parts = probe.split()
    try:
        return int(parts[1]), (int(parts[2]), int(parts[3]))
    except (IndexError, ValueError):
        return 0, (0, 0)


def setup():
    """Tagastab (use_sw, gl_ok, final_probe). Kutsu enne VTK/pyvista importimist."""
    global _DONE
    if _DONE is not None:
        return _DONE
    from PySide6.QtCore import QCoreApplication, QSettings, Qt
    from PySide6.QtGui import QSurfaceFormat
    settings = QSettings("Foral", "Moobel")
    mode = os.environ.get("MOOBEL_GL") or settings.value("gl_mode", "auto")
    use_sw = mode in ("sw", "software")
    info = f"režiim={mode}"
    if mode == "auto":
        probe = settings.value("gl_probe", "")
        if not probe:
            probe = _run_probe()
            settings.setValue("gl_probe", probe)
        ok, ver = _parse(probe)
        use_sw = not ok or ver < (3, 2)
        info += f", videokaardi test: {probe}"
    sw_info = ""
    if use_sw:
        os.environ["QT_OPENGL"] = "software"
        QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)
        if os.name == "nt" and os.path.exists(MESA_DLL):
            os.environ["QT_OPENGL_DLL"] = MESA_DLL
            os.environ["MOOBEL_MESA_DLL"] = MESA_DLL
            os.environ["PATH"] = MESA_DIR + os.pathsep + os.environ.get("PATH", "")
            os.environ["GALLIUM_DRIVER"] = "llvmpipe"
            try:
                import ctypes
                os.add_dll_directory(MESA_DIR)
                ctypes.WinDLL(MESA_DLL)     # nüüd seob ka VTK oma opengl32.dll selle Mesaga
                sw_info = f"Mesa eellaetud: {MESA_DLL}"
            except Exception as e:
                sw_info = f"Mesa eellaadimine ebaõnnestus: {e}"
        else:
            os.environ.setdefault("MESA_GL_VERSION_OVERRIDE", "3.3COMPAT")
            os.environ.setdefault("MESA_GLSL_VERSION_OVERRIDE", "330")
            sw_info = "Mesa kaust puudub – PySide6 opengl32sw.dll + versiooni ülekirjutus"
    else:
        QCoreApplication.setAttribute(Qt.AA_UseDesktopOpenGL)
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setVersion(3, 2)
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)
    sig = f"{mode}|{int(use_sw)}|{os.environ.get('MOOBEL_MESA_DLL', '')}"
    cached = settings.value("gl_final", "")
    if cached.startswith(sig + "|"):
        final = cached[len(sig) + 1:]
        ok_c, ver_c = _parse(final)
        if not (ok_c and ver_c >= (3, 2)):
            final = _run_probe()
    else:
        final = _run_probe()
    settings.setValue("gl_final", f"{sig}|{final}")
    dll = _sw_dll()
    vtk_loaded = "vtkmodules.vtkRenderingOpenGL2" in sys.modules
    gl_log(f"{info}\ntarkvaraline OpenGL: {'jah' if use_sw else 'ei'}\n"
           f"opengl32sw.dll: {'olemas' if os.path.exists(dll) else 'PUUDUB'}\n{sw_info}\n"
           f"VTK juba laetud enne seadistust: {'JAH (halb)' if vtk_loaded else 'ei'}\n"
           f"lõplik test: {final}\nPython: {sys.executable}", "w")
    print("[graafika]", info, "tarkvara" if use_sw else "riistvara", "|", sw_info, "|", final)
    ok, ver = _parse(final)
    _DONE = (use_sw, bool(ok) and ver >= (3, 2), final)
    return _DONE
