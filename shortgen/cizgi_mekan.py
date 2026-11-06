"""Çizgi Roman şablonunun mekânları: panel arka planları, kodla çizilen SVG (fotoğraf ya da başka bir kaynağın görseli
yok). Her mekân panelin kutusuna (tasarım koordinatı) göre oransal çizilir; geniş, dikey ve kare panellerde çalışır.

Bir mekân dört katman verir:
  arka   arka plan SVG'si (karakterlerin arkasında)
  tram   tram (Ben-Day) noktalı gölgeler: (kutu, renk, aralık, açı, yoğunluk fonksiyonu)
  on     ön plan SVG'si (karakterlerin önünde: masa, korkuluk, tezgâh)
  yazi   mekândaki yazılar (tabela, skor, defter, bilet): (x, y, metin, yazı yüzü, boyut, renk, hiza)
Mekândaki yazılar CizgiPanel.yazi'dan gelir; yazı yoksa mekânın varsayılan yazısı (ör. yol tabelası) kullanılmaz,
tabela boş kalır. Kulüp arması, logo ya da gerçek kişi çizilmez (renkler ve adlar yalnız yazı olarak).

Gece/akşam mekânları koyu, gündüz mekânları açık zeminlidir: üstlerine binen balon ve kutular her zaman kendi
kâğıtlarıyla okunur.
"""
from __future__ import annotations

import math
import random

from . import cizgi_sabit as CZ
from .cizgi_motor import CYAN, CYAN_DK, CYAN_LT, INK, OFF, PAPER, RED, WHITE, YELLOW, blend, hx

ink = hx(INK)
LACI = (24, 36, 70)           # gece göğü
LACI_2 = (36, 54, 98)
AHSAP, AHSAP_G = (176, 124, 78), (138, 92, 54)
YESIL, YESIL_2 = (74, 150, 82), (60, 128, 68)
GRI, GRI_2 = (196, 194, 188), (160, 158, 152)
TURUNCU = (236, 120, 40)


class M:
    """Bir mekânın çizim katmanları (bkz. modül açıklaması)."""

    def __init__(self):
        self.arka, self.on = "", ""
        self.tram: list = []
        self.yazi: list = []
        self.koyu = False          # koyu zemin (gece): ses efekti ve karakter gölgesi açık tonla


def P(x, y):
    return f"{x:.1f},{y:.1f}"


def poly(pts, fill, sw=4.0, op=1.0):
    s = f' stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round"' if sw else ""
    o = f' fill-opacity="{op}"' if op < 1 else ""
    return f'<path d="M{" L".join(P(*p) for p in pts)} Z" fill="{hx(fill)}"{o}{s}/>'


def rect(x0, y0, x1, y1, fill, sw=4.0, rx=0.0):
    s = f' stroke="{ink}" stroke-width="{sw}"' if sw else ""
    return (f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{max(0, x1 - x0):.1f}" height="{max(0, y1 - y0):.1f}" '
            f'rx="{rx:.1f}" fill="{hx(fill)}"{s}/>')


def circ(cx, cy, r, fill, sw=4.0):
    s = f' stroke="{ink}" stroke-width="{sw}"' if sw else ""
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{hx(fill)}"{s}/>'


def line(pts, color=INK, w=4.0, cap="round", dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="M{" L".join(P(*p) for p in pts)}" fill="none" stroke="{hx(color)}" stroke-width="{w}" '
            f'stroke-linecap="{cap}" stroke-linejoin="round"{d}/>')


class Kutu:
    """Panel kutusunda oransal koordinat: k(fx, fy) -> (x, y)."""

    def __init__(self, b):
        self.x0, self.y0, self.x1, self.y1 = b
        self.w, self.h = self.x1 - self.x0, self.y1 - self.y0

    def __call__(self, fx, fy):
        return (self.x0 + fx * self.w, self.y0 + fy * self.h)

    def x(self, f):
        return self.x0 + f * self.w

    def y(self, f):
        return self.y0 + f * self.h

    @property
    def s(self):      # ölçek: kısa kenar
        return min(self.w, self.h)


def _sabit(_x, _y, v=0.6):
    return v + 0 * _x


def _dikey(k: Kutu, a, b):
    """Yukarıdan aşağı a -> b yoğunluk."""
    return lambda X, Y: a + (b - a) * (Y - k.y0) / max(1, k.h)


def _yildizlar(k: Kutu, y_alt, n, seed):
    rng = random.Random(seed)
    out = ""
    for _ in range(n):
        x, y = rng.uniform(k.x0, k.x1), rng.uniform(k.y0, y_alt)
        r = rng.uniform(1.8, 3.6)
        out += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{hx(OFF)}" opacity="{rng.uniform(.5, .95):.2f}"/>'
    return out


def _tekne(cx, base_y, L, yon=1, kabin=True):
    """Mavi-beyaz balıkçı teknesi (yan görünüş): beyaz gövde, mavi bordür ve su hattı, kabin, direk."""
    h = L * 0.22
    x0, x1 = cx - L / 2, cx + L / 2
    if yon < 0:
        x0, x1 = x1, x0
    pts = [(x0, base_y - h), (x1 + 0.06 * L * yon, base_y - h * 1.25), (x1 - 0.06 * L * yon, base_y),
           (x0 + 0.08 * L * yon, base_y)]
    out = poly(pts, OFF, 5)
    # mavi bordür ve su hattı şeridi
    out += poly([(x0, base_y - h), (x1 + 0.06 * L * yon, base_y - h * 1.25), (x1 + 0.03 * L * yon, base_y - h * 0.95),
                 (x0 + 0.01 * L * yon, base_y - h * 0.78)], CYAN, 4)
    out += poly([(x0 + 0.06 * L * yon, base_y - h * 0.22), (x1 - 0.04 * L * yon, base_y - h * 0.22),
                 (x1 - 0.06 * L * yon, base_y), (x0 + 0.08 * L * yon, base_y)], (30, 70, 140), 4)
    if kabin:
        kx0, kx1 = cx - 0.12 * L * yon, cx + 0.12 * L * yon
        a, b = min(kx0, kx1), max(kx0, kx1)
        out += rect(a, base_y - h * 2.3, b, base_y - h * 0.95, OFF, 5)
        out += rect(a + 0.03 * L, base_y - h * 2.0, b - 0.03 * L, base_y - h * 1.5, CYAN_LT, 4)
        out += rect(a - 0.01 * L, base_y - h * 2.45, b + 0.01 * L, base_y - h * 2.25, CYAN, 4)
        mx = cx - 0.3 * L * yon
        out += line([(mx, base_y - h), (mx, base_y - h * 3.6)], INK, 6)
        out += line([(mx, base_y - h * 3.4), (cx, base_y - h * 2.45)], INK, 3)
    return out


def _dalgalar(k: Kutu, y0, y1, renk, n=5, seed=1):
    rng = random.Random(seed)
    out = ""
    for i in range(n):
        y = y0 + (y1 - y0) * (i + 0.5) / n
        x = k.x0 + rng.uniform(0.02, 0.4) * k.w
        L = rng.uniform(0.12, 0.3) * k.w
        out += line([(x, y), (x + L, y)], renk, 4)
    return out


def _saat(cx, cy, r, hh, mm):
    out = circ(cx, cy, r, OFF, 6)
    for i in range(12):
        a = math.radians(i * 30)
        r0, r1 = r * 0.72, r * 0.86
        out += line([(cx + r0 * math.sin(a), cy - r0 * math.cos(a)), (cx + r1 * math.sin(a), cy - r1 * math.cos(a))],
                    INK, 5 if i % 3 == 0 else 3)
    am = math.radians(mm * 6)
    ah = math.radians((hh % 12) * 30 + mm * 0.5)
    out += line([(cx, cy), (cx + r * 0.5 * math.sin(ah), cy - r * 0.5 * math.cos(ah))], INK, 8)
    out += line([(cx, cy), (cx + r * 0.74 * math.sin(am), cy - r * 0.74 * math.cos(am))], RED, 5)
    out += circ(cx, cy, r * 0.07, INK, 0)
    return out


def _yazi(m: M, x, y, text, font, size, color, anchor="ms"):
    m.yazi.append((x, y, text, font, size, color, anchor))


def _sigan(text, font, size, w):
    from .cizgi_motor import tw
    while size > 8 and tw(text, font, size) > w:
        size -= 1
    return size


# ---------------------------------------------------------------- mekânlar
def bos(k: Kutu, yazi, seed):
    m = M()
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, CYAN_LT, 0)
    m.tram.append(((k.x0, k.y0, k.x1, k.y1), blend(CYAN_LT, CYAN, .7), 18, 30,
                   lambda X, Y: 0.25 + 0.5 * (Y - k.y0) / max(1, k.h)))
    return m


def iskele_gece(k: Kutu, yazi, seed):
    m = M()
    m.koyu = True
    deniz = k.y(0.52)
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, LACI, 0)
    m.arka += _yildizlar(k, deniz - 20, 26, seed)
    ax, ay, ar = k.x(0.78), k.y(0.2), k.s * 0.11
    m.arka += f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="{ar * 1.6:.1f}" fill="{hx(LACI_2)}"/>'
    m.arka += circ(ax, ay, ar, OFF, 5)
    m.arka += circ(ax - ar * 0.3, ay - ar * 0.2, ar * 0.18, PAPER, 0) + circ(ax + ar * 0.3, ay + ar * 0.3, ar * 0.12, PAPER, 0)
    # uzakta Sinop kıyısı: tepe silueti ve küçük ışıklar
    m.arka += poly([(k.x0, deniz), (k.x0, deniz - k.h * 0.06), (k.x(0.2), deniz - k.h * 0.1), (k.x(0.38), deniz - k.h * 0.05),
                    (k.x(0.5), deniz - k.h * 0.03), (k.x(0.5), deniz)], (18, 26, 52), 0)
    for i in range(7):
        m.arka += circ(k.x(0.04 + i * 0.065), deniz - k.h * (0.02 + 0.015 * (i % 3)), 2.6, YELLOW, 0)
    m.arka += rect(k.x0, deniz, k.x1, k.y1, (16, 60, 92), 0)
    # ayın denizdeki yansıması
    for i in range(6):
        y = deniz + (i + 1) * k.h * 0.05
        w = k.w * (0.05 + 0.025 * i)
        m.arka += line([(ax - w / 2, y), (ax + w / 2, y)], blend(OFF, CYAN, .3), 5)
    # iskele: perspektifli ahşap tahtalar (alttan ortaya)
    yb, yt = k.y1 + 4, deniz + k.h * 0.06
    m.arka += poly([(k.x(-0.05), yb), (k.x(0.62), yb), (k.x(0.36), yt), (k.x(0.2), yt)], AHSAP_G, 5)
    for i in range(1, 9):
        t = (i / 9) ** 1.6
        y = yt + (yb - yt) * t
        xl = k.x(0.2) + (k.x(-0.05) - k.x(0.2)) * t
        xr = k.x(0.36) + (k.x(0.62) - k.x(0.36)) * t
        m.arka += line([(xl, y), (xr, y)], INK, 3)
    # iskele babası ve fener direği
    bx = k.x(0.56)
    m.arka += rect(bx - 12, yb - k.h * 0.22, bx + 12, yb, (60, 58, 56), 4)
    lx = k.x(0.1)
    m.arka += line([(lx, k.y(0.12)), (lx, k.y1)], INK, 9)
    m.arka += poly([(lx - 16, k.y(0.12)), (lx + 16, k.y(0.12)), (lx + 10, k.y(0.2)), (lx - 10, k.y(0.2))], YELLOW, 4)
    m.tram.append(((k.x0, k.y0, k.x1, deniz), (52, 74, 128), 16, 20, _dikey(k, 0.15, 0.55)))
    m.tram.append(((k.x0, deniz, k.x1, k.y1), (10, 40, 66), 14, 70, _dikey(k, 0.2, 0.8)))
    return m


def liman(k: Kutu, yazi, seed):
    m = M()
    ufuk = k.y(0.42)
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, CYAN_LT, 0)
    m.arka += circ(k.x(0.86), k.y(0.12), k.s * 0.07, YELLOW, 4)
    # Sinop yarımadasının tepeleri ve kale duvarı
    m.arka += poly([(k.x0, ufuk), (k.x0, ufuk - k.h * 0.1), (k.x(0.16), ufuk - k.h * 0.16), (k.x(0.36), ufuk - k.h * 0.08),
                    (k.x(0.5), ufuk - k.h * 0.12), (k.x(0.7), ufuk - k.h * 0.05), (k.x(0.7), ufuk)], YESIL_2, 4)
    dx0, dx1 = k.x(0.04), k.x(0.42)
    m.arka += rect(dx0, ufuk - k.h * 0.07, dx1, ufuk, (214, 200, 168), 4)
    n = 7
    for i in range(n):
        x = dx0 + (dx1 - dx0) * (i + 0.25) / n
        m.arka += rect(x, ufuk - k.h * 0.1, x + (dx1 - dx0) / n * 0.5, ufuk - k.h * 0.07, (214, 200, 168), 4)
    m.arka += rect(k.x0, ufuk, k.x1, k.y1, CYAN, 0)
    m.arka += _dalgalar(k, ufuk + 10, k.y(0.7), blend(CYAN, OFF, .45), 5, seed)
    # dalgakıran ve kırmızı fener
    m.arka += poly([(k.x(0.55), ufuk + 8), (k.x1 + 4, ufuk + 8), (k.x1 + 4, ufuk + k.h * 0.06), (k.x(0.53), ufuk + k.h * 0.06)],
                   GRI, 4)
    fx = k.x(0.93)
    m.arka += poly([(fx - 14, ufuk + 8), (fx + 14, ufuk + 8), (fx + 9, ufuk - k.h * 0.14), (fx - 9, ufuk - k.h * 0.14)], RED, 4)
    m.arka += rect(fx - 12, ufuk - k.h * 0.18, fx + 12, ufuk - k.h * 0.14, YELLOW, 4)
    # martılar
    for gx, gy in ((0.6, 0.12), (0.68, 0.18), (0.52, 0.2)):
        x, y = k(gx, gy)
        m.arka += line([(x - 16, y - 6), (x, y + 2), (x + 16, y - 6)], INK, 4)
    # mavi-beyaz balıkçı teknesi
    m.arka += _tekne(k.x(0.68), k.y(0.68), k.w * 0.5, yon=1)
    # iskele kenarı (ön)
    m.on = rect(k.x0 - 4, k.y(0.95), k.x1 + 4, k.y1 + 4, AHSAP, 5)
    m.tram.append(((k.x0, ufuk, k.x1, k.y1), blend(CYAN, INK, .25), 14, 60, _dikey(k, 0.05, 0.6)))
    return m


def tekne_sabah(k: Kutu, yazi, seed):
    m = M()
    ufuk = k.y(0.5)
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, (253, 230, 150), 0)
    sx, sr = k.x(0.66), k.s * 0.2
    m.arka += f'<path d="M{P(sx - sr, ufuk)} A{sr:.1f},{sr:.1f} 0 0 1 {P(sx + sr, ufuk)} Z" fill="{hx(YELLOW)}" stroke="{ink}" stroke-width="5"/>'
    for i in range(9):
        a = math.radians(180 + i * 22.5)
        m.arka += line([(sx + math.cos(a) * sr * 1.2, ufuk + math.sin(a) * sr * 1.2),
                        (sx + math.cos(a) * sr * 1.55, ufuk + math.sin(a) * sr * 1.55)], (236, 150, 40), 6)
    m.arka += rect(k.x0, ufuk, k.x1, k.y1, CYAN, 0)
    m.arka += line([(k.x0, ufuk), (k.x1, ufuk)], INK, 4)
    for i in range(4):
        y = ufuk + 14 + i * 16
        m.arka += line([(sx - sr * (0.8 - i * 0.15), y), (sx + sr * (0.8 - i * 0.15), y)], YELLOW, 5)
    # güverte korkuluğu ve ağ yığını (ön)
    m.on = poly([(k.x0 - 4, k.y(0.84)), (k.x1 + 4, k.y(0.8)), (k.x1 + 4, k.y1 + 4), (k.x0 - 4, k.y1 + 4)], AHSAP, 5)
    m.on += line([(k.x0, k.y(0.9)), (k.x1, k.y(0.87))], AHSAP_G, 4)
    m.tram.append(((k.x0, k.y0, k.x1, ufuk), (240, 170, 60), 18, 30, _dikey(k, 0.6, 0.0)))
    return m


def saha_aksam(k: Kutu, yazi, seed):
    m = M()
    m.koyu = True
    ufuk = k.y(0.5)
    m.arka = rect(k.x0, k.y0, k.x1, ufuk, LACI, 0)
    m.arka += rect(k.x0, k.y(0.38), k.x1, ufuk, (150, 60, 70), 0)
    # projektör direği ve ışık konisi
    px = k.x(0.84)
    m.arka += f'<path d="M{P(px, k.y(0.12))} L{P(k.x(0.2), k.y1)} L{P(k.x1, k.y1)} Z" fill="{hx(YELLOW)}" opacity="0.22"/>'
    m.arka += line([(px, k.y(0.12)), (px, ufuk)], INK, 8)
    m.arka += rect(px - 34, k.y(0.06), px + 34, k.y(0.13), OFF, 4)
    for i in range(3):
        for j in range(2):
            m.arka += circ(px - 22 + i * 22, k.y(0.08) + j * k.h * 0.03, 6, YELLOW, 2)
    m.arka += rect(k.x0, ufuk, k.x1, k.y1, YESIL, 0)
    for i in range(0, 6, 2):
        y0 = ufuk + (k.y1 - ufuk) * (i / 6)
        m.arka += rect(k.x0, y0, k.x1, y0 + (k.y1 - ufuk) / 6, YESIL_2, 0)
    m.arka += line([(k.x0, ufuk), (k.x1, ufuk)], INK, 4)
    m.arka += line([(k.x0, ufuk + 26), (k.x1, ufuk + 26)], OFF, 5)
    # küçük kale
    gx = k.x(0.1)
    m.arka += line([(gx, ufuk + 22), (gx, ufuk - k.h * 0.09), (gx + k.w * 0.22, ufuk - k.h * 0.09), (gx + k.w * 0.22, ufuk + 22)],
                   OFF, 7)
    m.arka += _yildizlar(k, k.y(0.3), 10, seed)
    m.tram.append(((k.x0, k.y0, k.x1, ufuk), (52, 74, 128), 16, 20, _dikey(k, 0.4, 0.0)))
    return m


def harita_fener(k: Kutu, yazi, seed):
    m = M()
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, CYAN, 0)
    # Karadeniz kıyısı: Sinop yarımadası ve İnceburun burnu (sadeleştirilmiş, kendi çizimimiz)
    kara = [(0.0, 0.62), (0.12, 0.6), (0.24, 0.56), (0.34, 0.5), (0.4, 0.42), (0.43, 0.3), (0.47, 0.28),
            (0.5, 0.36), (0.55, 0.42), (0.6, 0.44), (0.66, 0.4), (0.7, 0.44), (0.76, 0.48), (0.86, 0.54),
            (1.0, 0.58), (1.0, 1.0), (0.0, 1.0)]
    m.arka += poly([k(x, y) for x, y in kara], (232, 222, 190), 5)
    m.arka += poly([k(0.0, 0.8), k(0.3, 0.74), k(0.6, 0.82), k(1.0, 0.76), k(1.0, 1.0), k(0.0, 1.0)], (218, 206, 168), 0)
    # enlem çizgisi 42°K
    m.arka += line([k(0.0, 0.28), k(1.0, 0.28)], OFF, 3, dash="12 10")
    _yazi(m, k.x(0.98), k.y(0.28) - 10, "42° K", "courier", max(22, k.s * 0.06), OFF, "rs")
    # kırmızı iğne: İnceburun
    ix, iy = k(0.45, 0.29)
    m.arka += f'<path d="M{P(ix, iy)} L{P(ix - 16, iy - 34)} A18,18 0 1 1 {P(ix + 16, iy - 34)} Z" fill="{hx(RED)}" stroke="{ink}" stroke-width="5"/>'
    m.arka += circ(ix, iy - 46, 7, OFF, 3)
    # deniz adı mavide okunsun: kırık beyaz, mürekkep kontur (sekiz yöne kaydırılmış mürekkep kopyalar)
    ks = max(30, k.s * 0.09)
    kc = max(2.5, ks * 0.05)
    for a in range(8):
        _yazi(m, k.x(0.5) + kc * math.cos(a * math.pi / 4), k.y(0.16) + kc * math.sin(a * math.pi / 4), "KARADENİZ",
              "anton", ks, INK)
    _yazi(m, k.x(0.5), k.y(0.16), "KARADENİZ", "anton", ks, OFF)
    _yazi(m, k.x(0.55), k.y(0.6), "SİNOP", "anton", max(28, k.s * 0.08), INK)
    # İnceburun: iğnenin sağında, enlem çizgisinin üstünde, kâğıt çip üstünde
    from .cizgi_motor import tw
    isz = max(22, k.s * 0.055)
    lx, ly = ix + 36, k.y(0.28) - 16
    lw = tw("İnceburun", "courier", isz)
    m.arka += rect(lx - 9, ly - isz * 1.08, lx + lw + 9, ly + isz * 0.34, OFF, 3, rx=4)
    _yazi(m, lx, ly, "İnceburun", "courier", isz, INK, "ls")
    # fener (sağda): beyaz kule, ışık hüzmesi
    fx, fy = k.x(0.84), k.y(0.92)
    fh = k.h * 0.42
    m.arka += f'<path d="M{P(fx, fy - fh)} L{P(k.x0, fy - fh - k.h * 0.18)} L{P(k.x0, fy - fh + k.h * 0.1)} Z" fill="{hx(YELLOW)}" opacity="0.35"/>'
    m.arka += poly([(fx - 26, fy), (fx + 26, fy), (fx + 16, fy - fh), (fx - 16, fy - fh)], OFF, 5)
    m.arka += rect(fx - 22, fy - fh - 30, fx + 22, fy - fh, YELLOW, 5)
    m.arka += poly([(fx - 28, fy - fh - 30), (fx + 28, fy - fh - 30), (fx, fy - fh - 58)], RED, 5)
    m.arka += rect(fx - 10, fy - 40, fx + 10, fy, INK, 0)
    m.tram.append(((k.x0, k.y0, k.x1, k.y1), CYAN_DK, 14, 45, lambda X, Y: 0.35 + 0 * X))
    return m


def saha_gol(k: Kutu, yazi, seed):
    m = M()
    m.koyu = True
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, LACI, 0)
    zemin = k.y(0.8)
    m.arka += rect(k.x0, zemin, k.x1, k.y1, YESIL, 0)
    m.arka += line([(k.x0, zemin), (k.x1, zemin)], INK, 4)
    # kale ve file (sağda)
    gx0, gx1, gy = k.x(0.42), k.x(0.98), k.y(0.36)
    fil = ""
    for i in range(16):
        x = gx0 + (gx1 - gx0) * i / 15
        fil += f"M{P(x, gy)} L{P(x - 10, zemin)} "
    for j in range(9):
        y = gy + (zemin - gy) * j / 8
        fil += f"M{P(gx0 - 10 * j / 8, y)} L{P(gx1 - 10 * j / 8, y)} "
    m.arka += rect(gx0, gy, gx1, zemin, (40, 54, 94), 0)
    m.arka += f'<path d="{fil}" stroke="{hx(OFF)}" stroke-width="2.5" opacity="0.7"/>'
    m.arka += line([(gx0, zemin), (gx0, gy), (gx1, gy), (gx1, zemin)], OFF, 12)
    m.arka += line([(gx0, zemin), (gx0, gy), (gx1, gy), (gx1, zemin)], INK, 3)
    # skor tabelası (üst sol): yazı panel verisinden
    tx0, ty0, tx1, ty1 = k.x(0.04), k.y(0.05), k.x(0.56), k.y(0.2)
    for xx in (tx0 + 40, tx1 - 40):     # tabela tavandan asılı (direği figürün arkasından geçmez)
        m.arka += line([(xx, k.y0), (xx, ty0)], INK, 6)
    m.arka += rect(tx0, ty0, tx1, ty1, INK, 6, rx=8)
    m.arka += rect(tx0 + 12, ty0 + 12, tx1 - 12, ty1 - 12, (36, 34, 32), 0, rx=4)
    t = (yazi[0] if yazi else "").strip()
    if t:
        size = _sigan(t, "anton", (ty1 - ty0) * 0.62, tx1 - tx0 - 44)
        _yazi(m, (tx0 + tx1) / 2, (ty0 + ty1) / 2 + size * 0.36, t, "anton", size, YELLOW)
    m.tram.append(((k.x0, k.y0, k.x1, zemin), (52, 74, 128), 16, 20, _dikey(k, 0.1, 0.5)))
    return m


def tribun(k: Kutu, yazi, seed):
    m = M()
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, (240, 170, 90), 0)
    m.arka += rect(k.x0, k.y0, k.x1, k.y(0.18), (210, 110, 70), 0)
    n = 6
    for i in range(n):
        y0 = k.y(0.18 + i * 0.82 / n)
        y1 = k.y(0.18 + (i + 1) * 0.82 / n)
        m.arka += rect(k.x0 - 4, y0, k.x1 + 4, y1, GRI if i % 2 else GRI_2, 4)
        rng = random.Random(seed * 10 + i)
        for j in range(12):   # boş oturak çizgileri
            x = k.x0 + (j + 0.5) * k.w / 12 + rng.uniform(-4, 4)
            m.arka += rect(x - 16, y0 + 6, x + 16, y0 + 18, (150, 60, 60) if (i + j) % 3 else (120, 118, 114), 2, rx=4)
    # korkuluk (ön)
    m.on = line([(k.x0, k.y(0.86)), (k.x1, k.y(0.86))], INK, 10)
    m.on += line([(k.x0, k.y(0.86)), (k.x1, k.y(0.86))], OFF, 4)
    for i in range(7):
        x = k.x0 + (i + 0.5) * k.w / 7
        m.on += line([(x, k.y(0.86)), (x, k.y1)], INK, 8)
    m.tram.append(((k.x0, k.y0, k.x1, k.y1), (110, 60, 50), 16, 20, _dikey(k, 0.45, 0.1)))
    return m


def brosur(k: Kutu, yazi, seed):
    m = M()
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, AHSAP, 0)
    for i in range(6):
        y = k.y(0.1 + i * 0.17)
        m.arka += line([(k.x0, y), (k.x1, y + 8)], AHSAP_G, 3)
    # üç kanatlı broşür (hafif açılı)
    bx0, by0, bx1, by1 = k.x(0.05), k.y(0.12), k.x(0.95), k.y(0.9)
    w = (bx1 - bx0) / 3
    adlar = list(yazi[:3]) + [""] * (3 - len(yazi[:3]))
    for i in range(3):
        dy = 10 if i == 1 else 0
        x0, x1 = bx0 + i * w, bx0 + (i + 1) * w
        m.arka += f'<g transform="translate(8 10)">{rect(x0, by0 + dy, x1, by1 + dy, INK, 0)}</g>'
        m.arka += rect(x0, by0 + dy, x1, by1 + dy, OFF, 5)
        # resim alanı
        px0, py0, px1, py1 = x0 + 14, by0 + dy + 14, x1 - 14, by0 + dy + (by1 - by0) * 0.62
        renk = (CYAN_LT, (253, 236, 170), (40, 54, 94))[i]
        m.arka += rect(px0, py0, px1, py1, renk, 4)
        cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
        pw, ph = px1 - px0, py1 - py0
        if i == 0:     # yatakhane: ranza (yastık, kırmızı battaniye, merdiven)
            for yy in (cy - ph * 0.26, cy + ph * 0.16):
                m.arka += rect(cx - pw * 0.4, yy, cx + pw * 0.4, yy + ph * 0.12, AHSAP, 4)
                m.arka += rect(cx - pw * 0.36, yy - ph * 0.07, cx + pw * 0.36, yy + ph * 0.02, RED, 4, rx=8)
                m.arka += rect(cx - pw * 0.34, yy - ph * 0.12, cx - pw * 0.12, yy - ph * 0.03, OFF, 4, rx=10)
            m.arka += line([(cx - pw * 0.42, cy - ph * 0.42), (cx - pw * 0.42, cy + ph * 0.44)], INK, 7)
            m.arka += line([(cx + pw * 0.42, cy - ph * 0.42), (cx + pw * 0.42, cy + ph * 0.44)], INK, 7)
            for yy in (0.0, 0.08):
                m.arka += line([(cx + pw * 0.3, cy + ph * (0.02 + yy)), (cx + pw * 0.42, cy + ph * (0.02 + yy))], INK, 4)
        elif i == 1:   # okul binası
            m.arka += rect(cx - pw * 0.36, cy - ph * 0.1, cx + pw * 0.36, cy + ph * 0.4, (232, 200, 150), 4)
            m.arka += poly([(cx - pw * 0.42, cy - ph * 0.1), (cx, cy - ph * 0.38), (cx + pw * 0.42, cy - ph * 0.1)], RED, 4)
            for r in range(2):
                for c in range(3):
                    m.arka += rect(cx - pw * 0.28 + c * pw * 0.2, cy + r * ph * 0.16, cx - pw * 0.18 + c * pw * 0.2,
                                   cy + ph * 0.1 + r * ph * 0.16, CYAN_LT, 3)
            m.arka += line([(cx + pw * 0.3, cy - ph * 0.4), (cx + pw * 0.3, cy - ph * 0.12)], INK, 4)
            m.arka += rect(cx + pw * 0.3, cy - ph * 0.4, cx + pw * 0.42, cy - ph * 0.32, RED, 2)
        else:          # ışıl ışıl saha
            m.arka += rect(px0, cy + ph * 0.05, px1, py1, YESIL, 4)
            m.arka += line([(cx, cy + ph * 0.05), (cx, py1)], OFF, 3)
            m.arka += f'<circle cx="{cx:.1f}" cy="{cy + ph * 0.28:.1f}" r="{pw * 0.12:.1f}" fill="none" stroke="{hx(OFF)}" stroke-width="3"/>'
            for xx in (px0 + pw * 0.14, px1 - pw * 0.14):
                m.arka += line([(xx, py0 + ph * 0.12), (xx, cy + ph * 0.05)], OFF, 4)
                m.arka += rect(xx - 16, py0 + ph * 0.06, xx + 16, py0 + ph * 0.14, YELLOW, 3)
                for kk in range(5):
                    a = math.radians(40 + kk * 25)
                    m.arka += line([(xx + 20 * math.cos(a), py0 + ph * 0.1 + 20 * math.sin(a)),
                                    (xx + 34 * math.cos(a), py0 + ph * 0.1 + 34 * math.sin(a))], YELLOW, 3)
        # kanadın yazısı ve satırlar
        t = (adlar[i] or "").strip()
        if t:
            size = _sigan(t, "anton", min(44, (by1 - by0) * 0.08), w - 36)
            _yazi(m, (x0 + x1) / 2, py1 + size + 16, t, "anton", size, INK)
        for j in range(3):
            yy = by1 + dy - (by1 - by0) * (0.17 - j * 0.045)
            m.arka += line([(x0 + 22, yy), (x1 - 22 - (j % 2) * 30, yy)], GRI_2, 4)
    return m


def soyunma(k: Kutu, yazi, seed):
    m = M()
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, (212, 230, 232), 0)
    for i in range(1, 12):      # fayans
        m.arka += line([(k.x0, k.y0 + i * k.h / 12), (k.x1, k.y0 + i * k.h / 12)], (190, 210, 214), 2)
    # iki sıra askıda aynı forma (numaralar farklı, renkler aynı: kalabalık izlenimi)
    nos = [7, 9, 10, 11, 17, 19, 21, 23, 77, 99, 14, 18]
    sira = 1
    per = 6 if k.w > k.h else 4
    i = 0
    for r in range(sira):
        y = k.y(0.1 + r * 0.32)
        m.arka += line([(k.x0, y), (k.x1, y)], (120, 118, 114), 6)
        for c in range(per):
            cx = k.x0 + (c + 0.5) * k.w / per
            fw, fh = k.w / per * 0.78, k.h * 0.26
            m.arka += line([(cx, y), (cx, y + 14)], INK, 4)
            sh = [(cx - fw * 0.5, y + 22 + fh * 0.18), (cx - fw * 0.3, y + 16), (cx - fw * 0.12, y + 16),
                  (cx, y + 28), (cx + fw * 0.12, y + 16), (cx + fw * 0.3, y + 16), (cx + fw * 0.5, y + 22 + fh * 0.18),
                  (cx + fw * 0.38, y + 22 + fh * 0.32), (cx + fw * 0.3, y + 22 + fh * 0.26), (cx + fw * 0.3, y + 16 + fh),
                  (cx - fw * 0.3, y + 16 + fh), (cx - fw * 0.3, y + 22 + fh * 0.26), (cx - fw * 0.38, y + 22 + fh * 0.32)]
            m.arka += poly(sh, OFF, 4)
            _yazi(m, cx, y + 16 + fh * 0.78, str(nos[i % len(nos)]), "anton", fh * 0.42, (120, 118, 114))
            i += 1
    # bankta yan yana oturan, aynı formalı çocuklar (aynı karakter çizimi, yalnız yerleri farklı)
    from .cizgi_karakter import figur_svg
    by = k.y(0.84)
    nk = 5 if k.w > k.h else 3
    fw = k.w / nk
    sc = fw * 1.25 / 400
    figs = ""
    for c in range(nk):
        cx = k.x0 + (c + 0.5) * fw
        figs += (f'<g transform="translate({cx - 200 * sc:.1f} {by - 560 * sc:.1f}) scale({sc:.4f})">'
                 f'{figur_svg("oyuncu", "dur", ("normal", "gulumse", "kararli")[c % 3], "sag" if c % 2 else "sol")}</g>')
    m.on = figs + rect(k.x0 - 4, by, k.x1 + 4, by + k.h * 0.05, AHSAP, 5)
    m.on += rect(k.x0 - 4, by + k.h * 0.05, k.x1 + 4, k.y1 + 4, (150, 160, 166), 0)
    return m


def yol_tabelasi(k: Kutu, yazi, seed):
    m = M()
    ufuk = k.y(0.55)
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, CYAN_LT, 0)
    m.arka += rect(k.x0, ufuk - k.h * 0.06, k.x(0.55), ufuk, CYAN, 0)            # solda deniz
    m.arka += poly([(k.x(0.5), ufuk), (k.x(0.62), ufuk - k.h * 0.12), (k.x(0.82), ufuk - k.h * 0.18), (k.x1, ufuk - k.h * 0.1),
                    (k.x1, ufuk)], YESIL_2, 4)
    m.arka += rect(k.x0, ufuk, k.x1, k.y1, (210, 196, 150), 0)
    # yol: ortadan ufka uzanan
    m.arka += poly([(k.x(0.1), k.y1 + 4), (k.x(0.9), k.y1 + 4), (k.x(0.53), ufuk), (k.x(0.47), ufuk)], (90, 88, 86), 4)
    for i in range(5):
        t0, t1 = (i / 5) ** 1.5, ((i + 0.5) / 5) ** 1.5
        m.arka += poly([(k.x(0.5) - 3 - 8 * t0, ufuk + (k.y1 - ufuk) * t0), (k.x(0.5) + 3 + 8 * t0, ufuk + (k.y1 - ufuk) * t0),
                        (k.x(0.5) + 3 + 8 * t1, ufuk + (k.y1 - ufuk) * t1), (k.x(0.5) - 3 - 8 * t1, ufuk + (k.y1 - ufuk) * t1)],
                       OFF, 0)
    # direk ve iki ok tabela: sol yazi[0] sola, sağ yazi[1] sağa
    px = k.x(0.5)
    m.arka += line([(px, k.y(0.12)), (px, k.y(0.75))], (120, 118, 114), 14)
    m.arka += line([(px, k.y(0.12)), (px, k.y(0.75))], INK, 4)
    sol = (yazi[0] if len(yazi) > 0 else "").strip()
    sag = (yazi[1] if len(yazi) > 1 else "").strip()
    hh = k.h * 0.14
    for j, (t, yon) in enumerate(((sol, -1), (sag, 1))):
        y0 = k.y(0.14) + j * (hh + 18)
        L = k.w * 0.44
        if yon < 0:
            pts = [(px + 14, y0), (px - L + hh / 2, y0), (px - L, y0 + hh / 2), (px - L + hh / 2, y0 + hh), (px + 14, y0 + hh)]
        else:
            pts = [(px - 14, y0), (px + L - hh / 2, y0), (px + L, y0 + hh / 2), (px + L - hh / 2, y0 + hh), (px - 14, y0 + hh)]
        m.arka += f'<g transform="translate(6 8)">{poly(pts, INK, 0)}</g>' + poly(pts, (30, 82, 160), 5)
        m.arka += poly(pts, (30, 82, 160), 0)
        inner = [(x + (6 if x < px else -6) * 0, y) for x, y in pts]
        m.arka += f'<path d="M{" L".join(P(*p) for p in inner)} Z" fill="none" stroke="{hx(OFF)}" stroke-width="3" transform="translate(0 0)"/>'
        if t:
            size = _sigan(t, "anton", hh * 0.6, L - hh * 0.9 - 20)
            cx = px + yon * (L / 2 - hh * 0.15)
            _yazi(m, cx, y0 + hh / 2 + size * 0.36, t, "anton", size, OFF)
    return m


def mutfak(k: Kutu, yazi, seed):
    m = M()
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, (250, 236, 190), 0)
    for i in range(0, 14):        # fayans şeridi
        x = k.x0 + i * k.w / 13
        m.arka += line([(x, k.y(0.42)), (x, k.y(0.66))], (226, 206, 150), 3)
    # pencere
    wx0, wy0, wx1, wy1 = k.x(0.62), k.y(0.08), k.x(0.94), k.y(0.36)
    m.arka += rect(wx0, wy0, wx1, wy1, CYAN_LT, 6)
    m.arka += line([((wx0 + wx1) / 2, wy0), ((wx0 + wx1) / 2, wy1)], INK, 5)
    m.arka += line([(wx0, (wy0 + wy1) / 2), (wx1, (wy0 + wy1) / 2)], INK, 5)
    # raf ve kavanozlar
    m.arka += rect(k.x(0.04), k.y(0.24), k.x(0.42), k.y(0.27), AHSAP, 4)
    for i, c in enumerate((RED, YELLOW, CYAN)):
        x = k.x(0.08 + i * 0.12)
        m.arka += rect(x, k.y(0.14), x + k.w * 0.07, k.y(0.24), c, 4, rx=6)
    # masa (ön): kareli örtü ve okul çantası
    ty = k.y(0.72)
    on = rect(k.x0 - 4, ty, k.x1 + 4, k.y1 + 4, OFF, 5)
    for i in range(0, 16, 2):
        x = k.x0 + i * k.w / 15
        on += rect(x, ty, x + k.w / 15, k.y1 + 4, (232, 120, 110), 0)
    on += line([(k.x0, ty), (k.x1, ty)], INK, 5)
    cx, cw, ch = k.x(0.72), k.w * 0.24, k.h * 0.3
    on += rect(cx - cw / 2, ty - ch * 0.82, cx + cw / 2, ty + ch * 0.18, RED, 6, rx=22)
    on += rect(cx - cw * 0.36, ty - ch * 0.3, cx + cw * 0.36, ty + ch * 0.08, (176, 22, 30), 5, rx=12)
    on += f'<path d="M{P(cx - cw * 0.25, ty - ch * 0.82)} C{P(cx - cw * 0.25, ty - ch * 1.12)} {P(cx + cw * 0.25, ty - ch * 1.12)} {P(cx + cw * 0.25, ty - ch * 0.82)}" fill="none" stroke="{ink}" stroke-width="12"/>'
    on += line([(cx - cw * 0.3, ty - ch * 0.12), (cx + cw * 0.3, ty - ch * 0.12)], YELLOW, 5)
    # çay bardağı
    gx = k.x(0.2)
    on += poly([(gx - 18, ty - 50), (gx + 18, ty - 50), (gx + 12, ty - 4), (gx - 12, ty - 4)], (200, 80, 40), 4)
    on += rect(gx - 26, ty - 6, gx + 26, ty + 2, OFF, 3, rx=3)
    m.on = on
    return m


def telefon_defter(k: Kutu, yazi, seed):
    m = M()
    m.koyu = True
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, (52, 50, 62), 0)
    # duvarda perde ve abajur ışığı
    m.arka += f'<circle cx="{k.x(0.15):.1f}" cy="{k.y(0.3):.1f}" r="{k.s * 0.4:.1f}" fill="{hx(YELLOW)}" opacity="0.18"/>'
    m.arka += poly([(k.x(0.1), k.y(0.18)), (k.x(0.22), k.y(0.18)), (k.x(0.26), k.y(0.32)), (k.x(0.06), k.y(0.32))], YELLOW, 5)
    m.arka += line([(k.x(0.16), k.y(0.32)), (k.x(0.16), k.y(0.6))], INK, 7)
    ty = k.y(0.6)
    m.arka += rect(k.x0 - 4, ty, k.x1 + 4, k.y1 + 4, AHSAP_G, 5)
    # açık defter: iki isim (yazi), ikincisi kırmızıyla daire içinde
    dx0, dy0, dx1, dy1 = k.x(0.42), k.y(0.5), k.x(0.97), k.y(0.97)
    m.on = f'<g transform="rotate(-4 {(dx0 + dx1) / 2:.1f} {(dy0 + dy1) / 2:.1f})">'
    m.on += rect(dx0, dy0, dx1, dy1, OFF, 5)
    m.on += line([((dx0 + dx1) / 2, dy0), ((dx0 + dx1) / 2, dy1)], GRI_2, 4)
    for j in range(5):
        y = dy0 + (dy1 - dy0) * (0.2 + j * 0.16)
        m.on += line([(dx0 + 14, y), (dx1 - 14, y)], (190, 205, 220), 3)
    m.on += "</g>"
    names = [t.strip() for t in yazi[:3] if t.strip()]
    from .cizgi_motor import tw
    for j, t in enumerate(names):
        size = _sigan(t, "anton", min(64, (dy1 - dy0) * 0.24), (dx1 - dx0) - 70)
        x = dx0 + 34
        y = dy0 + (dy1 - dy0) * (0.36 + j * 0.34)
        _yazi(m, x, y, t, "anton", size, INK if j == 0 else (30, 60, 150), "ls")
        if j == 1:             # ikinci isim kırmızıyla daire içinde
            ww = tw(t, "anton", size)
            m.on += (f'<ellipse cx="{x + ww / 2:.1f}" cy="{y - size * 0.36:.1f}" rx="{ww / 2 + 22:.1f}" '
                     f'ry="{size * 0.72:.1f}" fill="none" stroke="{hx(RED)}" stroke-width="6" '
                     f'transform="rotate(-4 {x + ww / 2:.1f} {y:.1f})"/>')
    return m


def saat_bilet(k: Kutu, yazi, seed):
    m = M()
    m.koyu = True
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, LACI, 0)
    hh, mm = 23, 40
    if yazi and ":" in yazi[0]:
        try:
            hh, mm = (int(v) for v in yazi[0].strip().split(":")[:2])
        except ValueError:
            pass
    r = k.s * 0.24
    cx, cy = k.x(0.5), k.y(0.36)
    m.arka += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 1.35:.1f}" fill="{hx(LACI_2)}"/>'
    m.arka += _saat(cx, cy, r, hh, mm)
    ty = k.y(0.74)
    m.arka += rect(k.x0 - 4, ty, k.x1 + 4, k.y1 + 4, AHSAP_G, 5)
    # otobüs bileti (ön)
    bx0, by0, bx1, by1 = k.x(0.2), k.y(0.79), k.x(0.8), k.y(0.95)
    m.on = f'<g transform="rotate(-3 {(bx0 + bx1) / 2:.1f} {(by0 + by1) / 2:.1f})">'
    m.on += f'<g transform="translate(6 8)">{rect(bx0, by0, bx1, by1, INK, 0, rx=6)}</g>'
    m.on += rect(bx0, by0, bx1, by1, OFF, 5, rx=6)
    m.on += rect(bx0, by0, bx0 + (bx1 - bx0) * 0.18, by1, RED, 5, rx=6)
    m.on += line([(bx0 + (bx1 - bx0) * 0.78, by0 + 6), (bx0 + (bx1 - bx0) * 0.78, by1 - 6)], INK, 3, dash="6 6")
    m.on += "</g>"
    t = (yazi[1] if len(yazi) > 1 else "").strip()
    if t:
        size = _sigan(t, "anton", (by1 - by0) * 0.42, (bx1 - bx0) * 0.58)
        _yazi(m, bx0 + (bx1 - bx0) * 0.48, (by0 + by1) / 2 + size * 0.36, t, "anton", size, INK)
    m.tram.append(((k.x0, k.y0, k.x1, ty), (52, 74, 128), 16, 20, _dikey(k, 0.15, 0.45)))
    return m


def istanbul(k: Kutu, yazi, seed):
    """A paneli: kırmızı zemin, İstanbul silueti (Galata Kulesi, kubbeler, köprü), koyu kırmızı."""
    m = M()
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, RED, 0)
    sil = (150, 18, 26)
    gy = k.y(0.62)
    out = ""
    # köprü
    out += line([(k.x0, gy - k.h * 0.02), (k.x1, gy - k.h * 0.02)], sil, 8)
    for x in (0.3, 0.75):
        out += line([(k.x(x), gy), (k.x(x), gy - k.h * 0.16)], sil, 10)
    out += f'<path d="M{P(k.x0, gy - k.h * 0.1)} Q{P(k.x(0.52), gy + k.h * 0.06)} {P(k.x1, gy - k.h * 0.1)}" fill="none" stroke="{hx(sil)}" stroke-width="5"/>'
    # kubbeler ve kule
    for cx, r in ((0.18, 0.08), (0.36, 0.06)):
        out += f'<path d="M{P(k.x(cx) - k.w * r, gy)} A{k.w * r:.1f},{k.w * r:.1f} 0 0 1 {P(k.x(cx) + k.w * r, gy)} Z" fill="{hx(sil)}"/>'
        out += line([(k.x(cx) + k.w * r * 1.3, gy), (k.x(cx) + k.w * r * 1.3, gy - k.h * 0.18)], sil, 6)
    tx = k.x(0.62)
    out += poly([(tx - 18, gy), (tx + 18, gy), (tx + 14, gy - k.h * 0.2), (tx - 14, gy - k.h * 0.2)], sil, 0)
    out += poly([(tx - 18, gy - k.h * 0.2), (tx + 18, gy - k.h * 0.2), (tx, gy - k.h * 0.28)], sil, 0)
    m.arka += out + rect(k.x0, gy, k.x1, k.y1, (186, 24, 32), 0)
    m.tram.append(((k.x0, k.y0, k.x1, k.y1), (176, 20, 28), 16, 30, _dikey(k, 0.1, 0.6)))
    return m


def samsun(k: Kutu, yazi, seed):
    """B paneli: camgöbeği zemin, Karadeniz kıyısı, stadyum ışıkları ve vapur silueti."""
    m = M()
    m.arka = rect(k.x0, k.y0, k.x1, k.y1, CYAN, 0)
    sil = CYAN_DK
    gy = k.y(0.62)
    out = ""
    # stadyum kasesi ve projektörler
    out += f'<path d="M{P(k.x(0.08), gy)} L{P(k.x(0.14), gy - k.h * 0.1)} Q{P(k.x(0.4), gy - k.h * 0.16)} {P(k.x(0.66), gy - k.h * 0.1)} L{P(k.x(0.72), gy)} Z" fill="{hx(sil)}"/>'
    for x in (0.12, 0.68):
        out += line([(k.x(x), gy - k.h * 0.1), (k.x(x), gy - k.h * 0.26)], sil, 6)
        out += rect(k.x(x) - 16, gy - k.h * 0.29, k.x(x) + 16, gy - k.h * 0.25, YELLOW, 3)
    # vapur
    vx = k.x(0.84)
    out += poly([(vx - k.w * 0.14, gy - k.h * 0.04), (vx + k.w * 0.14, gy - k.h * 0.04), (vx + k.w * 0.11, gy),
                 (vx - k.w * 0.12, gy)], sil, 0)
    out += rect(vx - k.w * 0.03, gy - k.h * 0.1, vx + k.w * 0.01, gy - k.h * 0.04, sil, 0)
    m.arka += out + rect(k.x0, gy, k.x1, k.y1, (18, 128, 166), 0)
    m.arka += _dalgalar(k, gy + 10, k.y(0.75), blend(CYAN, OFF, .4), 3, seed)
    m.tram.append(((k.x0, k.y0, k.x1, k.y1), CYAN_DK, 16, 30, _dikey(k, 0.1, 0.6)))
    return m


MEKANLAR = {"bos": bos, "iskele_gece": iskele_gece, "liman": liman, "tekne_sabah": tekne_sabah,
            "saha_aksam": saha_aksam, "harita_fener": harita_fener, "saha_gol": saha_gol, "tribun": tribun,
            "brosur": brosur, "soyunma": soyunma, "yol_tabelasi": yol_tabelasi, "mutfak": mutfak,
            "telefon_defter": telefon_defter, "saat_bilet": saat_bilet, "istanbul": istanbul, "samsun": samsun}
assert set(MEKANLAR) == set(CZ.MEKANLAR), "her mekân anahtarının çizimi olmalı"


def mekan(anahtar: str, box, yazi=(), seed: int = 1) -> M:
    """Mekânın katmanları; bilinmeyen anahtar 'bos'."""
    return MEKANLAR.get(anahtar, bos)(Kutu(box), [str(t) for t in (yazi or [])], seed)
