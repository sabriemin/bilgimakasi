"""Çizgi Roman şablonunun çizim motoru: sayfa, tram (Ben-Day) noktaları, kalın kenarlı paneller, konuşma/düşünce/
bağırma balonları, ses efekti (SFX) yazıları, hız çizgileri, yırtık kâğıt etiketler ve yazı sığdırma.

Hepsi tasarım koordinatıyla (1080x1920) çalışır ve kart şablonunun Pen'i ile 2x çizilip küçültülür. Videoda panel
içerikleri ve balonlar sahne başına bir kez çizilip önbelleğe alınır; kare başına yalnız katmanlar birleştirilir
(bkz. cizgi.py).
"""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw

from . import kart as K

W, H, SS = K.W, K.H, K.SS
RED, YELLOW, INK, PAPER, OFF, WHITE, GREY = K.RED, K.YELLOW, K.INK, K.PAPER, K.OFF, K.WHITE, K.GREY
# serinin TEK ek rengi: baskı camgöbeği. Kırmızı + sarı + mürekkep + camgöbeği = dört renkli çizgi roman baskısı;
# B seçeneğinin, gece sahnelerinin ve sayfa köşelerindeki tram noktalarının rengi.
CYAN = (22, 150, 190)
CYAN_LT = (178, 222, 234)
CYAN_DK = (12, 98, 128)
NBSP = "\u00a0"


def up(s: str) -> str:
    return K.tr_upper(s or "")


def hx(c) -> str:
    return K._hex(c)


def tw(s, font, size) -> float:
    return K.tw(s, font, size)


def cap_h(font: str, size: float) -> float:
    return -K.tbox("H", font, size)[1]


def sar(text: str, font: str, size: float, width: float) -> list[str]:
    """Kelime kaydırma: '\n' satırı zorla böler; NBSP ile bağlı kelimeler ayrılmaz ("15.000 ₺")."""
    out = []
    sp = tw(" ", font, size)
    for para in text.split("\n"):
        cur, cw = [], 0.0
        for w in para.split(" "):
            if not w:
                continue
            ww = tw(w.replace(NBSP, " "), font, size)
            if cur and cw + sp + ww > width:
                out.append(" ".join(cur))
                cur, cw = [], 0.0
            cw += (sp if cur else 0) + ww
            cur.append(w)
        if cur:
            out.append(" ".join(cur))
    return [L.replace(NBSP, " ") for L in out]


def sigdir(text: str, font: str, width: float, max_size: int, min_size: int, max_lines: int) -> tuple[int, list[str]]:
    """En büyük boyutu seçer: satır sayısı max_lines'ı, her satır width'i aşmaz. Hiçbiri sığmazsa en küçük boyutta
    satırlar yine width'e sığar (uzun tek kelime harf harf bölünmez, ölçüsü küçülür: bkz. sigdir_kesin)."""
    for size in range(max_size, min_size - 1, -2):
        lines = sar(text, font, size, width)
        if len(lines) <= max_lines and all(tw(L, font, size) <= width for L in lines):
            return size, lines
    return sigdir_kesin(text, font, width, min_size, max_lines)


def sigdir_kesin(text: str, font: str, width: float, size: int, max_lines: int) -> tuple[int, list[str]]:
    """Sığmayan metin: boyut, en uzun satır width'e ve satır sayısı max_lines'a sığana kadar küçülür (en az 12 px)."""
    while size > 12:
        lines = sar(text, font, size, width)
        if len(lines) <= max_lines and all(tw(L, font, size) <= width for L in lines):
            break
        size -= 1
    return size, sar(text, font, size, width)


# ---------------------------------------------------------------- yırtık kâğıt etiketler
def etiket(pen: K.Pen, text, size, fg, bg, seed, cx, cy, rot=0.0, shadow=(6, 8, 0, 0.9), font="anton", rim=OFF):
    """Yırtık kâğıt etiketi merkezi (cx, cy) olacak şekilde yapıştırır; (w, h) döndürür."""
    lab = K.torn_label(text, size, fg, bg, seed, font=font, rim=rim)
    im = lab.render_ss(rot, shadow)
    pen.paste(im, cx - im.width / 2 / SS, cy - im.height / 2 / SS)
    return lab.w, lab.h


def etiket_olcu(text, size, font="anton") -> tuple[float, float]:
    """torn_label'ın kâğıt ölçüsü (w, h), çizmeden."""
    lab = K.torn_label(text, size, INK, OFF, 1, font=font)
    return lab.w, lab.h


def etiket_sol(pen, text, size, fg, bg, seed, x, cy, **kw):
    """Sol kenarı x olan etiket; genişliğini döndürür."""
    w, _ = etiket_olcu(text, size, kw.get("font", "anton"))
    etiket(pen, text, size, fg, bg, seed, x + w / 2, cy, **kw)
    return w


KENAR = 8            # panel mürekkep kenarı
GOLGE = (10, 12)     # panel sert gölgesi
BALON_SW = 6         # balon kenarı


# ---------------------------------------------------------------- tram (Ben-Day) noktaları
def tram(w: int, h: int, renk, aralik: float, aci: float, yogunluk, rmax: float | None = None,
         x0: float = 0, y0: float = 0) -> Image.Image:
    """Döndürülmüş ızgarada, yoğunluğa göre büyüyen noktalar (kenar yumuşatmalı RGBA).
    yogunluk: (X, Y) -> 0..1 dizisi döndüren fonksiyon (X, Y tasarım koordinatı)."""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    X, Y = xs + x0 + 0.5, ys + y0 + 0.5
    a = math.radians(aci)
    u = X * math.cos(a) + Y * math.sin(a)
    v = -X * math.sin(a) + Y * math.cos(a)
    cu = (np.floor(u / aralik) + 0.5) * aralik
    cv = (np.floor(v / aralik) + 0.5) * aralik
    d = np.hypot(u - cu, v - cv)
    # nokta merkezinin yoğunluğu (hücre içinde sabit kalsın diye merkezde örneklenir)
    cx = cu * math.cos(a) - cv * math.sin(a)
    cy = cu * math.sin(a) + cv * math.cos(a)
    rmax = rmax if rmax is not None else aralik * 0.5
    r = np.clip(yogunluk(cx, cy), 0, 1) * rmax
    alpha = np.clip(r - d + 0.5, 0, 1) * (r > 0.35)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = renk
    out[..., 3] = (alpha * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def sayfa(seed: int = 0, koyu: bool = False) -> Image.Image:
    """Çizgi roman sayfası: marka kâğıdı + iki köşede camgöbeği tram geçişi (seri imzası)."""
    bg = Image.new("RGBA", (W, H), (INK if koyu else PAPER) + (255,))

    def yog(X, Y):
        d1 = np.hypot(X - 0, Y - 120) / 900
        d2 = np.hypot(X - W, Y - H + 60) / 1000
        return np.maximum(1 - d1, 1 - d2) * 1.15 - 0.15

    col = (40, 52, 58) if koyu else blend(PAPER, CYAN, 0.55)
    bg.alpha_composite(tram(W, H, col, 26, 18, yog))
    return bg


def blend(c1, c2, k):
    return tuple(int(round(a + (b - a) * k)) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- çokgen yardımcıları
def iceri(poly, d):
    """Dışbükey çokgeni (saat yönünde, ekran koordinatı) d kadar içeri kaydırır."""
    n = len(poly)
    # yön: alan işaretine göre
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    sgn = 1 if area > 0 else -1
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        L = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / L * sgn, (x1 - x0) / L * sgn
        lines.append(((x0 + nx * d, y0 + ny * d), (x1 + nx * d, y1 + ny * d)))
    out = []
    for i in range(n):
        (a0, a1), (b0, b1) = lines[i - 1], lines[i]
        out.append(_kesis(a0, a1, b0, b1))
    return out


def _kesis(p1, p2, p3, p4):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return p2
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def kutu(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def kaydir(poly, dx, dy):
    return [(x + dx, y + dy) for x, y in poly]


# ---------------------------------------------------------------- panel
def panel(img: Image.Image, poly, ciz, kenar=KENAR, golge=GOLGE, zemin=OFF):
    """Panel: sert gölge + mürekkep kenar + içerik. ciz(pen) içeriği panelin kutusunu kaplayan bir Pen'e çizer
    (tasarım koordinatıyla); içerik iç çokgenle kırpılır. Panelin iç çokgenini döndürür."""
    x0, y0, x1, y1 = kutu(poly)
    x0, y0, x1, y1 = math.floor(x0) - 2, math.floor(y0) - 2, math.ceil(x1) + 2, math.ceil(y1) + 2
    # gölge + kenar (2x)
    pen = K.Pen(x0, y0, x1 + golge[0] + 2, y1 + golge[1] + 2)
    pen.poly(kaydir(poly, *golge), INK + (255,))
    pen.poly(poly, INK + (255,))
    ic = iceri(poly, kenar)
    pen.poly(ic, zemin + (255,))
    lay = pen.done()
    img.alpha_composite(lay, (x0, y0))
    # içerik
    cp = K.Pen(x0, y0, x1, y1)
    ciz(cp)
    con = cp.done()
    mp = K.Pen(x0, y0, x1, y1)
    mp.poly(ic, (255, 255, 255, 255))
    mask = mp.done().getchannel("A")
    a = Image.fromarray((np.asarray(con.getchannel("A"), dtype=np.float32) *
                         np.asarray(mask, dtype=np.float32) / 255).astype(np.uint8))
    con.putalpha(a)
    img.alpha_composite(con, (x0, y0))
    return ic


def tram_pen(pen: K.Pen, box, renk, aralik, aci, yogunluk, rmax=None):
    """Pen'e (2x) tram katmanı yapıştırır; box tasarım koordinatı."""
    bx0, by0, bx1, by1 = [int(round(v)) for v in box]
    s = pen.s
    t = tram((bx1 - bx0) * s, (by1 - by0) * s, renk, aralik * s, aci,
             lambda X, Y: yogunluk(X / s, Y / s), None if rmax is None else rmax * s, bx0 * s, by0 * s)
    pen.paste(t, bx0, by0)


# ---------------------------------------------------------------- SVG yardımcıları
def P(x, y):
    return f"{x:.1f},{y:.1f}"


def svg_tam(pen: K.Pen, body: str):
    """Tasarım koordinatlı SVG gövdesini pen'in kutusuna çizer (viewBox = pen kutusu)."""
    vb = (pen.x0, pen.y0, pen.w, pen.h)
    pen.svg(body, vb, pen.x0, pen.y0, pen.w)


def _yol_cift(paths_ink: list[str], paths_fill: list[str], fill, sw) -> str:
    """Kenarları kaynaşan şekiller: önce hepsi kalın mürekkeple, sonra hepsi dolguyla (kenarsız)."""
    ink = hx(INK)
    out = "".join(f'<path d="{d}" fill="{ink}" stroke="{ink}" stroke-width="{2 * sw}" stroke-linejoin="round"/>'
                  for d in paths_ink)
    out += "".join(f'<path d="{d}" fill="{hx(fill)}"/>' for d in paths_fill)
    return out


def _rrect_d(x0, y0, x1, y1, r):
    return (f"M{P(x0 + r, y0)} L{P(x1 - r, y0)} Q{P(x1, y0)} {P(x1, y0 + r)} L{P(x1, y1 - r)} "
            f"Q{P(x1, y1)} {P(x1 - r, y1)} L{P(x0 + r, y1)} Q{P(x0, y1)} {P(x0, y1 - r)} L{P(x0, y0 + r)} "
            f"Q{P(x0, y0)} {P(x0 + r, y0)} Z")


def _ell_d(cx, cy, rx, ry):
    return (f"M{P(cx - rx, cy)} A{rx:.1f} {ry:.1f} 0 1 0 {P(cx + rx, cy)} "
            f"A{rx:.1f} {ry:.1f} 0 1 0 {P(cx - rx, cy)} Z")


def _kuyruk_d(cx, cy, hw, uc, egri=0.0):
    """Balon gövdesinin merkezinden uca kuyruk (gövdenin içinden başlar, üstü dolguyla örtülür)."""
    tx, ty = uc
    dx, dy = tx - cx, ty - cy
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    a = (cx + nx * hw, cy + ny * hw)
    b = (cx - nx * hw, cy - ny * hw)
    mx, my = cx + dx * 0.6 + nx * egri, cy + dy * 0.6 + ny * egri
    return f"M{P(*a)} Q{P(mx, my)} {P(tx, ty)} Q{P(mx, my)} {P(*b)} Z"


# ---------------------------------------------------------------- balonlar
class Balon:
    """Konuşma balonu: yazı Anton, büyük harf, ortalı. tur: 'konus' (yuvarlak köşe), 'oval', 'bagir' (dikenli),
    'dusun' (bulut, kuyruğu küçük yuvarlaklar)."""

    def __init__(self, text, cx, cy, genislik, uc=None, tur="konus", size=52, min_size=42, satir=3, renk=WHITE,
                 yazi=INK, font="anton", seed=1, vurgu=None):
        self.text, self.cx, self.cy = up(text) if font == "anton" else text, cx, cy
        self.uc, self.tur, self.renk, self.yazi, self.font, self.seed = uc, tur, renk, yazi, font, seed
        self.size, self.lines = sigdir(self.text, font, genislik, size, min_size, satir)
        self.vurgu = [up(v) for v in (vurgu or [])]
        self.lh = self.size * 1.22      # Türkçe şapka ve noktalar (Ğ, İ, Ş) üst satırın harfine değmesin
        self.tw = max(tw(L, font, self.size) for L in self.lines)
        self.th = cap_h(font, self.size) + (len(self.lines) - 1) * self.lh
        padx, pady = (0.62, 0.62) if tur in ("oval", "bagir", "dusun") else (0.42, 0.40)
        self.w = self.tw + 2 * self.size * padx
        self.h = self.th + 2 * self.size * pady
        if tur in ("oval", "dusun"):
            self.w *= 1.16
            self.h *= 1.22
        if tur == "bagir":
            self.w *= 1.16
            self.h *= 1.26

    @property
    def box(self):
        return (self.cx - self.w / 2, self.cy - self.h / 2, self.cx + self.w / 2, self.cy + self.h / 2)

    def svg(self) -> str:
        cx, cy, w, h = self.cx, self.cy, self.w, self.h
        sw = BALON_SW
        if self.tur == "konus":
            body = _rrect_d(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, min(h / 2, 46))
        elif self.tur in ("oval",):
            body = _ell_d(cx, cy, w / 2, h / 2)
        elif self.tur == "bagir":
            rng = random.Random(self.seed)
            n = 22
            pts = []
            for i in range(2 * n):
                a = math.pi * 2 * i / (2 * n) + rng.uniform(-0.03, 0.03)
                k = 1.0 if i % 2 == 0 else 0.80 + rng.uniform(-0.03, 0.03)
                if i % 2 == 0:
                    k = 1.0 + rng.uniform(0.0, 0.14)
                pts.append((cx + math.cos(a) * w / 2 * k, cy + math.sin(a) * h / 2 * k))
            body = "M" + " L".join(P(*p) for p in pts) + " Z"
        else:   # dusun: bulut
            rng = random.Random(self.seed)
            n = 11
            body = ""
            for i in range(n):
                a = math.pi * 2 * i / n
                r = min(w, h) * 0.24 * rng.uniform(0.9, 1.1)
                bx = cx + math.cos(a) * (w / 2 - r * 0.62)
                by = cy + math.sin(a) * (h / 2 - r * 0.62)
                body += _ell_d(bx, by, r, r * 0.92) + " "
            body += _ell_d(cx, cy, w / 2 - min(w, h) * 0.12, h / 2 - min(w, h) * 0.12)
        ink_paths, fill_paths = [body], [body]
        extra = ""
        if self.uc is not None:
            if self.tur == "dusun":
                tx, ty = self.uc
                # buluttan uca doğru küçülen yuvarlaklar
                dx, dy = tx - cx, ty - cy
                L = math.hypot(dx, dy)
                ux, uy = dx / L, dy / L
                ex = cx + ux * (abs(w / 2 * ux) + abs(h / 2 * uy)) * 0.86
                ey = cy + uy * (abs(w / 2 * ux) + abs(h / 2 * uy)) * 0.86
                for k, rr in ((0.18, 20), (0.55, 14), (0.88, 9)):
                    px_, py_ = ex + (tx - ex) * k, ey + (ty - ey) * k
                    d = _ell_d(px_, py_, rr, rr * 0.9)
                    extra += (f'<path d="{d}" fill="{hx(self.renk)}" stroke="{hx(INK)}" stroke-width="{sw}"/>')
            else:
                hw = min(w, h) * (0.16 if self.tur != "bagir" else 0.2)
                k = _kuyruk_d(cx, cy, hw, self.uc, egri=hw * 0.6)
                ink_paths.append(k)
                fill_paths.append(k)
        out = f'<g transform="translate(5 6)">{_yol_cift(ink_paths, [], INK, sw)}</g>' if self.tur != "dusun" else ""
        out += _yol_cift(ink_paths, fill_paths, self.renk, sw)
        return out + extra

    def yazi_ciz(self, pen: K.Pen):
        ch = cap_h(self.font, self.size)
        y = self.cy - self.th / 2 + ch
        if self.tur == "bagir":
            y += self.size * 0.04
        for L in self.lines:
            if self.vurgu:
                self._vurgulu(pen, L, y)
            else:
                pen.text(self.cx, y, L, self.font, self.size, self.yazi, anchor="ms")
            y += self.lh

    def _vurgulu(self, pen, L, y):
        words = L.split(" ")
        sp = tw(" ", self.font, self.size)
        total = tw(L, self.font, self.size)
        x = self.cx - total / 2
        for wd in words:
            col = RED if any(v in wd for v in self.vurgu) else self.yazi
            pen.text(x, y, wd, self.font, self.size, col)
            x += tw(wd, self.font, self.size) + sp


def balonlar(pen: K.Pen, liste: list[Balon]):
    """Balonları (SVG) ve yazılarını pen'e çizer."""
    if not liste:
        return
    svg_tam(pen, "".join(b.svg() for b in liste))
    for b in liste:
        b.yazi_ciz(pen)


# ---------------------------------------------------------------- anlatıcı kutusu
def anlatici(pen: K.Pen, text, x, y, genislik, size=40, renk=YELLOW, yazi=INK, rot=0.0, seed=3, font="courier",
             satir=4, min_size=40, hizala="sol", ust_etiket=None):
    """Sarı yırtık kâğıt anlatıcı kutusu (çizgi romanın 'caption' kutusu + markanın yırtık kâğıdı).
    (x, y) sol üst köşe. Kutunun (w, h) boyutunu döndürür."""
    pad = size * 0.5
    size, lines = sigdir(text, font, genislik - 2 * pad, size, min_size, satir)
    lh = size * 1.22
    ch = cap_h(font, size)
    tw_ = max(tw(L, font, size) for L in lines)
    w = (tw_ + 2 * pad) if hizala == "sol" else genislik
    h = ch + (len(lines) - 1) * lh + 2 * pad + size * 0.18
    sp = K.Sprite(w, h, margin=24)
    K.torn_paper(sp, 0, 0, w, h, renk, seed, rim=OFF)
    yy = pad + ch
    for L in lines:
        if hizala == "sol":
            sp.text((pad, yy), L, font, size, yazi)
        else:
            sp.text((w / 2, yy), L, font, size, yazi, anchor="ms")
        yy += lh
    im = sp.render_ss(rot, (6, 8, 0, 0.9))
    pen.paste(im, x - (im.width / SS - w) / 2, y - (im.height / SS - h) / 2)
    return w, h


# ---------------------------------------------------------------- ses efekti (SFX)
def sfx(pen: K.Pen, text, cx, cy, size, renk=YELLOW, kenar=INK, kalinlik=None, rot=0.0, golge=True):
    """Kalın mürekkep kenarlı, eğik çizgi roman ses yazısı (Anton)."""
    text = up(text)
    s = pen.s
    f = K.fnt("anton", size * s)
    k = int(round((kalinlik or size * 0.09) * s))
    l, t, r, b = f.getbbox(text, anchor="mm", stroke_width=k)
    m = 20 * s
    im = Image.new("RGBA", (r - l + 2 * m, b - t + 2 * m), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    org = (-l + m, -t + m)
    if golge:
        d.text((org[0] + 6 * s, org[1] + 7 * s), text, font=f, fill=kenar, anchor="mm", stroke_width=k,
               stroke_fill=kenar)
    d.text(org, text, font=f, fill=renk, anchor="mm", stroke_width=k, stroke_fill=kenar)
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    pen.paste(im, cx - im.width / 2 / s, cy - im.height / 2 / s)


# ---------------------------------------------------------------- hız çizgileri
def hiz_cizgileri(pen: K.Pen, cx, cy, r0, r1, n=46, renk=INK, seed=4, kalin=(6, 16)):
    """Odak noktasına doğru incelen ışınsal çizgiler (şaşkınlık/vurgu panelleri)."""
    rng = random.Random(seed)
    body = ""
    for i in range(n):
        a = math.pi * 2 * i / n + rng.uniform(-0.04, 0.04)
        w = rng.uniform(*kalin)
        rr0 = r0 * rng.uniform(1.0, 1.35)
        tip = (cx + math.cos(a) * rr0, cy + math.sin(a) * rr0)
        nx, ny = -math.sin(a), math.cos(a)
        ox, oy = cx + math.cos(a) * r1, cy + math.sin(a) * r1
        body += (f'<path d="M{P(*tip)} L{P(ox + nx * w, oy + ny * w)} L{P(ox - nx * w, oy - ny * w)} Z" '
                 f'fill="{hx(renk)}"/>')
    svg_tam(pen, body)


# ---------------------------------------------------------------- yazı (kenarlı)
def kenarli_yazi(pen: K.Pen, x, y, text, font, size, renk, kenar=INK, k=None, anchor="ls"):
    s = pen.s
    f = K.fnt(font, size * s)
    kk = int(round((k or size * 0.08) * s))
    px, py = pen.p(x, y)
    pen.d.text((px, py), text, font=f, fill=renk, anchor=anchor, stroke_width=kk, stroke_fill=kenar)
