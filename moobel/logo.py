"""Germo Mööbel – logo ja käivituskuva (joonistatud QPainteriga, vektorina).

Märk: isomeetriline kuup kolmest plaadist (mööbliplaadid) Eesti lipu värvides –
sinine, must ja valge – ning sinisel küljel puuritud ava (mööblikinnituse auk).
"""
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QPainter, QColor, QPolygonF, QPixmap, QFont, QLinearGradient, QPen,
                           QRadialGradient, QIcon, QPainterPath)
from PySide6.QtWidgets import QSplashScreen, QApplication

BLUE = QColor("#0072CE")      # Eesti lipu sinine
BLACK = QColor("#111418")
WHITE = QColor("#F4F6F8")
VERSION = "1.0"


def _iso(cx, cy, s):
    """Kuubi tipud: keskpunkt (cx, cy), serv s."""
    h = s * math.sqrt(3) / 2
    top = QPointF(cx, cy - s)
    rt = QPointF(cx + h, cy - s / 2)
    rb = QPointF(cx + h, cy + s / 2)
    bot = QPointF(cx, cy + s)
    lb = QPointF(cx - h, cy + s / 2)
    lt = QPointF(cx - h, cy - s / 2)
    c = QPointF(cx, cy)
    return top, rt, rb, bot, lb, lt, c


def _shrink(poly, k):
    """Tõmbab hulknurga keskpunkti poole (plaatide vahele jääb vuuk)."""
    cx = sum(p.x() for p in poly) / len(poly)
    cy = sum(p.y() for p in poly) / len(poly)
    return QPolygonF([QPointF(cx + (p.x() - cx) * k, cy + (p.y() - cy) * k) for p in poly])


def draw_mark(p, cx, cy, s, dark_bg=True):
    """Joonistab logomärgi (kuubi) keskpunktiga (cx, cy) ja servaga s."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    top, rt, rb, bot, lb, lt, c = _iso(cx, cy, s)
    faces = [
        ([top, rt, c, lt], WHITE),     # pealmine – valge
        ([lt, c, bot, lb], BLUE),      # vasak – sinine
        ([c, rt, rb, bot], BLACK if not dark_bg else QColor("#1b2027")),   # parem – must
    ]
    for k, (pts, col) in enumerate(faces):
        poly = _shrink(pts, 0.93)
        if k == 2 and dark_bg:
            p.setPen(QPen(QColor(255, 255, 255, 110), max(1.0, s * 0.02)))   # must külg tumedal taustal
        elif k == 0 and not dark_bg:
            p.setPen(QPen(QColor("#111418"), max(1.0, s * 0.02)))           # valge külg heledal taustal
        else:
            p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon(poly)
    # plaadi paksus pealmisel plaadil (servajoon)
    p.setPen(QPen(QColor(0, 0, 0, 60), max(1.0, s * 0.018)))
    a = _shrink([top, rt, c, lt], 0.93)
    p.drawLine(QPointF((a[3].x() + a[2].x()) / 2, (a[3].y() + a[2].y()) / 2 + s * 0.06),
               QPointF((a[2].x() + a[1].x()) / 2, (a[2].y() + a[1].y()) / 2 + s * 0.06))
    # puuritud ava sinisel küljel (ellips isomeetrias)
    hc = QPointF((lt.x() + c.x() + bot.x() + lb.x()) / 4, (lt.y() + c.y() + bot.y() + lb.y()) / 4)
    p.translate(hc)
    p.rotate(-30)
    r = s * 0.17
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#00427a"))
    p.drawEllipse(QPointF(0, 0), r * 0.62, r)
    p.setBrush(QColor("#9fc9ef"))
    p.drawEllipse(QPointF(0, -r * 0.12), r * 0.30, r * 0.5)
    p.restore()


def draw_wordmark(p, x, y, size, color=WHITE, sub_color=BLUE):
    p.save()
    p.setRenderHint(QPainter.TextAntialiasing)
    f = QFont("Segoe UI", -1, QFont.Black)
    f.setPixelSize(int(size))
    f.setLetterSpacing(QFont.AbsoluteSpacing, size * 0.12)
    p.setFont(f)
    p.setPen(color)
    p.drawText(QPointF(x, y), "GERMO")
    f2 = QFont("Segoe UI", -1, QFont.DemiBold)
    f2.setPixelSize(int(size * 0.34))
    f2.setLetterSpacing(QFont.AbsoluteSpacing, size * 0.09)
    p.setFont(f2)
    p.setPen(sub_color)
    from .i18n import T
    p.drawText(QPointF(x + size * 0.04, y + size * 0.52), T("MÖÖBLI DISAINER"))
    p.restore()


def flag_bar(p, x, y, w, h):
    for i, col in enumerate((BLUE, BLACK, WHITE)):
        p.fillRect(QRectF(x, y + i * h / 3, w, h / 3 + 0.5), col)


def logo_pixmap(w=900, h=300, dark=False):
    """Logo PNG (läbipaistev taust)."""
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = h * 0.36
    draw_mark(p, h * 0.5, h * 0.5, s, dark_bg=dark)
    draw_wordmark(p, h * 0.98, h * 0.55, h * 0.30, WHITE if dark else BLACK, BLUE)
    p.end()
    return pm


def app_icon():
    icon = QIcon()
    for n in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(n, n)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        draw_mark(p, n / 2, n / 2, n * 0.47, dark_bg=False)
        p.end()
        icon.addPixmap(pm)
    return icon


class Splash(QSplashScreen):
    W, H = 720, 420

    def __init__(self):
        pm = QPixmap(self.W, self.H)
        pm.fill(Qt.transparent)
        super().__init__(pm, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.progress = 0
        self.msg = "Käivitan…"
        self.tick = 0

    def set(self, progress=None, msg=None):
        if progress is not None:
            self.progress = progress
        if msg is not None:
            from .i18n import T
            self.msg = T(msg)
        self.repaint()
        QApplication.processEvents()

    def animate(self):
        self.tick += 1
        self.repaint()

    def drawContents(self, p):
        W, H = self.W, self.H
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), 18, 18)
        g = QLinearGradient(0, 0, W, H)
        g.setColorAt(0, QColor("#0a1626"))
        g.setColorAt(1, QColor("#10345c"))
        p.fillPath(path, g)
        rg = QRadialGradient(QPointF(W * 0.25, H * 0.42), W * 0.45)
        rg.setColorAt(0, QColor(0, 114, 206, 70))
        rg.setColorAt(1, QColor(0, 114, 206, 0))
        p.fillPath(path, rg)
        # õrn joonestusruudustik
        p.save()
        p.setClipPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        for x in range(0, W, 24):
            p.drawLine(x, 0, x, H)
        for y in range(0, H, 24):
            p.drawLine(0, y, W, y)
        p.restore()

        # märk + kerge "hõljumine"
        bob = math.sin(self.tick / 6.0) * 3
        draw_mark(p, 175, 180 + bob, 92, dark_bg=True)
        draw_wordmark(p, 300, 190, 76, WHITE, QColor("#3d9be9"))
        flag_bar(p, 304, 250, 48, 16)
        f = QFont("Segoe UI"); f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 150))
        from .i18n import T
        p.drawText(QPointF(362, 263), T("Valmistatud Eestis"))

        # edenemisriba
        bx, by, bw, bh = 48, H - 66, W - 96, 6
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 3, 3)
        gb = QLinearGradient(bx, 0, bx + bw, 0)
        gb.setColorAt(0, QColor("#0072CE"))
        gb.setColorAt(1, QColor("#5fb4ff"))
        p.setBrush(gb)
        p.drawRoundedRect(QRectF(bx, by, max(bh, bw * self.progress / 100.0), bh), 3, 3)
        # liikuv helk
        sx = bx + (self.tick * 9) % int(bw)
        hg = QLinearGradient(sx - 40, 0, sx + 40, 0)
        hg.setColorAt(0, QColor(255, 255, 255, 0))
        hg.setColorAt(0.5, QColor(255, 255, 255, 70))
        hg.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hg)
        p.drawRoundedRect(QRectF(bx, by, bw * self.progress / 100.0, bh), 3, 3)

        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 190))
        dots = "." * (1 + (self.tick // 8) % 3)
        p.drawText(QPointF(bx, by - 12), self.msg.rstrip("…").rstrip(".") + dots)
        p.setPen(QColor(255, 255, 255, 110))
        p.drawText(QRectF(bx, by - 26, bw, 20), Qt.AlignRight, f"v{VERSION}")
        p.drawText(QRectF(bx, by + 14, bw, 20), Qt.AlignLeft, "© Germo")
