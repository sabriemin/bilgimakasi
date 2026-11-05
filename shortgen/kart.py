"""Kart şablonu: "Göz" kartları + Kolaj'ın yırtık kâğıt etiketleri + maskot Makas.

Ekran düzeni (1080x1920). Platform arayüzü sağdaki düğmeleri (x > 935), üst çubuğu (y < 170) ve alttaki açıklamayı
(y > 1540) kapattığı için gölgeler dahil hiçbir öğe bu alanlara taşmaz (yalnız düz arka plan taşar):
  başlık      y≈200       "// 03 — çin seddi" ..................... ✂ EFSANE Mİ?
  kinetik     y 232-440   dış ses 1-4 kelimelik parçalar hâlinde yırtık etiketlerde (söylenen siyah, okunan kırmızı,
                          sıradaki gri). Bu şablonda alttaki altyazı kutusunun yerini tutar.
  kart        y 480-1120  sahnenin kartı: photo, drawing, counter, compare, quote, interstitial, cta (+ yedek: text)
  alt sıra    y 1296-1516 terminal (makas@bilgimakasi, kayıt satırları, kesik çizgi ilerleme) ve maskot Makas

Hız: arka plan + başlık sahne başına, kartın durağan hâli sahne başına, etiketler kelime/durum başına, maskot
ifade/ağız/göz kırpma başına, terminal durum başına önbelleğe alınır. Kare başına yalnız katmanlar birleştirilir.
Rastgelelik sahne/kelime numarasıyla tohumlanır; aynı sahnenin kareleri arasında hiçbir şey titremez.
"""
from __future__ import annotations

import bisect
import io
import math
import random
import re
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import render
from .voice import Word

W, H, FPS = render.W, render.H, render.FPS
FONT_DIR = render.FONT_DIR
SS = 2  # durağan katmanlar 2x çizilip küçültülür (kenar yumuşatma)

RED = (221, 32, 39)
YELLOW = (252, 213, 33)
INK = (20, 19, 19)
PAPER = (233, 231, 226)
OFF = (250, 249, 245)
WHITE = (255, 255, 255)
GREY = (150, 148, 145)
DGREY = (84, 82, 79)                       # açık zeminde ikincil mono yazı (soluk gri değil)
DOT = (218, 216, 211)
YEL_LIGHT = (253, 240, 176)
UPC_BG, UPC_FG = (207, 204, 198), (86, 84, 81)   # sıradaki kelimeler: dolu gri kâğıt
TERM_DIM = (78, 76, 74)
TERM_TXT = (200, 197, 192)

SAFE = (0, 170, 935, 1540)                 # içerik yalnız bu dikdörtgende (x0, y0, x1, y1)
SAFE_X = SAFE[2]                           # yerleşim hesapları için (SAFE kırpma içindir)
HEADER_Y = 202
HEADER_REGION = (0, 166, W, 224)
RULE_Y = 230
KIN = (72, 244, 920, 446)
CARD = (100, 480, 908, 1120)
CARD_SH = 12
CARD_REGION = (68, 440, 926, 1140)         # kart katmanının kapladığı alan (gölge, bant, çip taşmaları dahil)
CARD_FLOOR = 1138                          # kart bunun altına inmez: maskotun bıçak uçları ~1150'den başlar
CLIP_FLOOR = CARD_FLOOR                    # kart katmanlarının kırpıldığı alt sınır (CARD_FLOOR yerleşim içindir)
TERM = (60, 1296, 600, 1516)
MASCOT_XY, MASCOT_SCALE = (774, 1370), 0.86
WIPE = 0.42                                # ara kanca kırmızı silme süresi (sn)

FONTS = {"anton": "Anton-Regular.ttf", "archivo": "ArchivoBlack-Regular.ttf", "mono": "DMMono-Medium.ttf",
         "oswald": "Oswald-Bold.ttf", "courier": "CourierPrime-Bold.ttf"}
CARD_TYPES = ("photo", "drawing", "counter", "compare", "quote", "interstitial", "cta", "text")


# ---------------------------------------------------------------- küçük yardımcılar
_fonts: dict = {}


def fnt(name: str, px: float) -> ImageFont.FreeTypeFont:
    key = (name, max(1, int(round(px))))
    f = _fonts.get(key)
    if f is None:
        f = _fonts[key] = ImageFont.truetype(str(FONT_DIR / FONTS.get(name, name)), key[1])
    return f


def tw(s: str, font: str, size: float) -> float:
    """Yazının tasarım pikseli cinsinden genişliği."""
    return fnt(font, size * SS).getlength(s) / SS


def tbox(s: str, font: str, size: float, anchor: str = "ls") -> tuple:
    return tuple(v / SS for v in fnt(font, size * SS).getbbox(s, anchor=anchor))


def ink_box(s: str, font: str, size: float) -> tuple:
    """Yazının gerçek mürekkep kutusu (taban çizgisine göre, tasarım pikseli)."""
    f = fnt(font, size * SS)
    im = Image.new("L", (int(f.getlength(s)) + 4 * size * SS // 4 + 8, int(size * SS * 2.2)), 0)
    by = int(size * SS * 1.5)
    ImageDraw.Draw(im).text((4, by), s, font=f, fill=255, anchor="ls")
    b = im.getbbox() or (4, by, 4, by)
    return ((b[0] - 4) / SS, (b[1] - by) / SS, (b[2] - 4) / SS, (b[3] - by) / SS)


def fit(s: str, font: str, size: float, max_w: float) -> str:
    """Sığmayan yazıyı sondan kısaltıp '…' ekler."""
    if tw(s, font, size) <= max_w:
        return s
    while s and tw(s + "…", font, size) > max_w:
        s = s[:-1]
    return s.rstrip(" ·-—,") + "…"


def tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def slug(s: str, n: int = 40) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")
    return re.sub(r"[^a-z0-9]+", "-", s.translate(tr).lower()).strip("-")[:n].strip("-")


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out_cubic(x: float) -> float:
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out_back(x: float, k: float = 1.6) -> float:
    x = clamp(x)
    return 1 + (k + 1) * (x - 1) ** 3 + k * (x - 1) ** 2


def blend(c1, c2, k):
    return tuple(int(round(a + (b - a) * k)) for a, b in zip(c1, c2))


def put(img: Image.Image, layer: Image.Image | None, x: float, y: float, k: float = 1.0, alpha: float = 1.0,
        clip=SAFE, anchor=(0.5, 0.5)) -> None:
    """Katmanı (x, y) sol üst köşesine bindirir; k ile anchor noktasından ölçekler; güvenli alanın dışını kırpar."""
    if layer is None:
        return
    if abs(k - 1.0) > 1e-3:
        nw, nh = max(1, int(round(layer.width * k))), max(1, int(round(layer.height * k)))
        x, y = x + (layer.width - nw) * anchor[0], y + (layer.height - nh) * anchor[1]
        layer = layer.resize((nw, nh), Image.BILINEAR)
    if alpha < 0.999:
        layer = layer.copy()
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    x, y = int(round(x)), int(round(y))
    cx0, cy0, cx1, cy1 = clip
    l, t = max(0, cx0 - x), max(0, cy0 - y)
    r, b = min(layer.width, cx1 - x), min(layer.height, cy1 - y)
    if r <= l or b <= t:
        return
    if (l, t, r, b) != (0, 0, layer.width, layer.height):
        layer = layer.crop((l, t, r, b))
    img.alpha_composite(layer, (x + l, y + t))


# ---------------------------------------------------------------- 2x çizim katmanı
class Pen:
    """Tasarım koordinatlarıyla (1080x1920) çizer; katman yalnız verilen kutuyu SS kat çözünürlükte kaplar."""

    def __init__(self, x0, y0, x1, y1, ss: int = SS):
        self.x0, self.y0, self.s = int(x0), int(y0), ss
        self.w, self.h = int(math.ceil(x1)) - self.x0, int(math.ceil(y1)) - self.y0
        self.im = Image.new("RGBA", (self.w * ss, self.h * ss), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def p(self, x, y):
        return ((x - self.x0) * self.s, (y - self.y0) * self.s)

    def rr(self, box, r, fill=None, outline=None, width=0, corners=None):
        x0, y0, x1, y1 = box
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        a, b = self.p(x0, y0)
        c, d = self.p(x1, y1)
        self.d.rounded_rectangle([a, b, c - 1, d - 1], radius=r * self.s, fill=fill, outline=outline,
                                 width=int(round(width * self.s)) if outline else 0, corners=corners)

    def ell(self, cx, cy, r, fill=None, outline=None, width=0):
        a, b = self.p(cx - r, cy - r)
        c, d = self.p(cx + r, cy + r)
        self.d.ellipse([a, b, c, d], fill=fill, outline=outline, width=int(round(width * self.s)) if outline else 0)

    def line(self, pts, fill, width, joint="curve"):
        self.d.line([self.p(x, y) for x, y in pts], fill=fill, width=max(1, int(round(width * self.s))), joint=joint)

    def poly(self, pts, fill):
        self.d.polygon([self.p(x, y) for x, y in pts], fill=fill)

    def text(self, x, y, s, font, size, fill, anchor="ls"):
        self.d.text(self.p(x, y), s, font=fnt(font, size * self.s), fill=fill, anchor=anchor)

    def paste(self, im: Image.Image, x, y):
        """im zaten SS ölçeğinde; sol üst köşesi tasarım koordinatı (x, y)."""
        px, py = self.p(x, y)
        _comp(self.im, im, px, py)

    def svg(self, body, vb, x, y, w, rot=0.0):
        h = w * vb[3] / vb[2]
        im = svg_img(body, vb, w * self.s, h * self.s)
        if rot:
            im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
            px, py = self.p(x + w / 2, y + h / 2)
            _comp(self.im, im, px - im.width / 2, py - im.height / 2)
        else:
            self.paste(im, x, y)

    def done(self) -> Image.Image:
        return self.im.resize((self.w, self.h), Image.LANCZOS) if self.s != 1 else self.im


def _comp(dst: Image.Image, im: Image.Image, x, y):
    x, y = int(round(x)), int(round(y))
    l, t = max(0, -x), max(0, -y)
    r, b = min(im.width, dst.width - x), min(im.height, dst.height - y)
    if r <= l or b <= t:
        return
    dst.alpha_composite(im.crop((l, t, r, b)) if (l, t, r, b) != (0, 0, im.width, im.height) else im, (x + l, y + t))


def svg_img(body: str, vb, pw, ph) -> Image.Image:
    import cairosvg
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="{vb[0]:.2f} {vb[1]:.2f} {vb[2]:.2f} {vb[3]:.2f}" width="{vb[2]:.2f}" height="{vb[3]:.2f}">'
           f'{body}</svg>')
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=max(1, int(round(pw))),
                           output_height=max(1, int(round(ph))))
    return Image.open(io.BytesIO(png)).convert("RGBA")


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(c[:3])


def P(x, y) -> str:
    return f"{x:.2f},{y:.2f}"


# ---------------------------------------------------------------- küçük SVG simgeler
SCISSORS_VB = (0, 0, 124, 84)
ICON_VB = (0, 0, 100, 100)


def scissors_svg(open_deg=22, ring=RED, blade=INK, pivot=YELLOW, outline=INK) -> str:
    """Sağa bakan marka makası (viewBox 0 0 124 84)."""
    px_, py_ = 58, 42
    rings = [(20, 22), (20, 62)]
    a = math.radians(open_deg / 2)
    tips = [(px_ + 64 * math.cos(a), py_ + 64 * math.sin(a)), (px_ + 64 * math.cos(a), py_ - 64 * math.sin(a))]
    body = ""
    for (rx, ry), (tx, ty) in zip(rings, tips):
        body += (f'<line x1="{rx}" y1="{ry}" x2="{px_}" y2="{py_}" stroke="{_hex(blade)}" stroke-width="11" '
                 'stroke-linecap="round"/>')
        ux, uy = tx - px_, ty - py_
        n = math.hypot(ux, uy)
        nx, ny = -uy / n, ux / n
        body += (f'<path d="M{P(px_ + nx * 7, py_ + ny * 7)} L{P(tx, ty)} L{P(px_ - nx * 7, py_ - ny * 7)} Z" '
                 f'fill="{_hex(blade)}" stroke="{_hex(blade)}" stroke-width="3" stroke-linejoin="round"/>')
    for rx, ry in rings:
        if outline:
            body += f'<circle cx="{rx}" cy="{ry}" r="14" fill="none" stroke="{_hex(outline)}" stroke-width="13"/>'
        body += f'<circle cx="{rx}" cy="{ry}" r="14" fill="none" stroke="{_hex(ring)}" stroke-width="8"/>'
    body += f'<circle cx="{px_}" cy="{py_}" r="5" fill="{_hex(pivot)}"/>'
    return body


def check_svg(color=INK, w=15) -> str:
    return (f'<path d="M22 54 L42 73 L79 30" fill="none" stroke="{_hex(color)}" stroke-width="{w}" '
            'stroke-linecap="round" stroke-linejoin="round"/>')


def cross_svg(color=OFF, w=15) -> str:
    return (f'<path d="M28 28 L72 72 M72 28 L28 72" fill="none" stroke="{_hex(color)}" stroke-width="{w}" '
            'stroke-linecap="round"/>')


def arrow_svg(color=OFF, w=14, direction="right") -> str:
    d = "M18 50 L80 50 M56 26 L80 50 L56 74" if direction == "right" else "M50 14 L50 80 M24 56 L50 82 L76 56"
    return (f'<path d="{d}" fill="none" stroke="{_hex(color)}" stroke-width="{w}" stroke-linecap="round" '
            'stroke-linejoin="round"/>')


def mini_rings(pen: Pen, x, y, r=12, inner=YELLOW):
    """Pencere 'düğmeleri': iç içe geçmiş iki kırmızı makas halkası."""
    for i in range(2):
        cx = x + i * r * 1.7
        pen.ell(cx, y, r, fill=RED, outline=INK, width=3)
        pen.ell(cx, y, r * 0.48, fill=inner, outline=INK, width=3)


_sc_cache: dict = {}


def scissors_icon(w: float, open_deg: float, blade=INK, ring=RED, pivot=YELLOW, outline=INK, rot=0.0) -> Image.Image:
    """1x makas simgesi (önbellekli). rot: derece, saat yönünün tersine."""
    key = (round(w), round(open_deg), blade, ring, pivot, outline, round(rot, 1))
    im = _sc_cache.get(key)
    if im is None:
        h = w * SCISSORS_VB[3] / SCISSORS_VB[2]
        im = svg_img(scissors_svg(open_deg, ring, blade, pivot, outline), SCISSORS_VB, w * SS, h * SS)
        if rot:
            im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
        im = _sc_cache[key] = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
    return im


# ---------------------------------------------------------------- yırtık kâğıt (Kolaj)
def rot_pts(pts, cx, cy, deg):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca + (y - cy) * sa, cy - (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def add_shadow(im: Image.Image, dx, dy, blur, opacity, color=INK) -> Image.Image:
    a = im.getchannel("A")
    sh_a = a.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else a
    sh_a = sh_a.point(lambda v: int(v * opacity))
    sh = Image.new("RGBA", im.size, color + (0,))
    sh.putalpha(sh_a)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (int(dx), int(dy)))
    out.alpha_composite(im)
    return out


class Sprite:
    """Tasarım pikseliyle çizilen, SS çözünürlükte tutulan RGBA katman; döndürülüp küçültülür."""

    def __init__(self, w, h, margin=40):
        self.w, self.h, self.m = w, h, margin
        self.im = Image.new("RGBA", (int(round((w + 2 * margin) * SS)), int(round((h + 2 * margin) * SS))), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def p(self, x, y):
        return ((x + self.m) * SS, (y + self.m) * SS)

    def polygon(self, pts, fill):
        self.d.polygon([self.p(x, y) for x, y in pts], fill=fill)

    def line(self, pts, fill, width):
        self.d.line([self.p(x, y) for x, y in pts], fill=fill, width=max(1, int(round(width * SS))), joint="curve")

    def dot(self, x, y, r, fill):
        a, b = self.p(x - r, y - r)
        c, d = self.p(x + r, y + r)
        self.d.ellipse([a, b, c, d], fill=fill)

    def text(self, xy, s, font, size, fill, anchor="ls"):
        self.d.text(self.p(*xy), s, font=fnt(font, size * SS), fill=fill, anchor=anchor)

    def render_ss(self, rot=0.0, shadow=None) -> Image.Image:
        """SS ölçeğinde (2x) döndürülmüş görüntü; Pen.paste ile 2x katmana yapıştırmak için."""
        im = self.im.rotate(rot, resample=Image.BICUBIC, expand=True) if rot else self.im
        if shadow:
            dx, dy, blur, op = shadow
            im = add_shadow(im, dx * SS, dy * SS, blur * SS, op)
        return im

    def render(self, rot=0.0, shadow=None) -> Image.Image:
        im = self.im.rotate(rot, resample=Image.BICUBIC, expand=True) if rot else self.im
        im = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
        return add_shadow(im, *shadow) if shadow else im


def torn_pts(x, y, w, h, seed, jitter=3.0, step=5.0):
    """Elle yırtılmış kenarlı dikdörtgen (düşük frekanslı dalga + lif gürültüsü)."""
    rng = np.random.default_rng(seed)
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    pts = []
    for i in range(4):
        ax, ay = corners[i]
        bx, by = corners[(i + 1) % 4]
        L = math.hypot(bx - ax, by - ay)
        n = max(4, int(L / step))
        nx, ny = (by - ay) / L, -(bx - ax) / L
        raw = rng.normal(0, 1, n + 8)
        low = np.convolve(raw, np.ones(5) / 5, mode="same")[4:4 + n] * 1.9
        for k in range(n):
            t = k / n
            off = jitter * (0.8 * low[k] + 0.45 * rng.uniform(-1, 1))
            if rng.random() < 0.035:
                off -= jitter * rng.uniform(0.8, 1.6)
            pts.append((ax + (bx - ax) * t + nx * off, ay + (by - ay) * t + ny * off))
    return pts


def torn_paper(sp: Sprite, x, y, w, h, color, seed, jitter=None, rim=OFF, rim_w=2.4, alpha=255):
    """Yırtık kâğıt parçası; renkli kâğıtlarda yırtık kenarda açık renk lif şeridi görünür."""
    jitter = jitter if jitter is not None else max(1.6, min(w, h) * 0.022)
    step = max(3.5, jitter * 1.6)
    if rim is not None:
        sp.polygon(torn_pts(x - rim_w * 0.6, y - rim_w * 0.6, w + rim_w * 1.2, h + rim_w * 1.2, seed + 101, jitter, step),
                   rim + (alpha,))
    inset = rim_w * 0.4 if rim is not None else 0
    sp.polygon(torn_pts(x + inset, y + inset, w - 2 * inset, h - 2 * inset, seed, jitter, step), color + (alpha,))


def tape(sp: Sprite, cx, cy, w, h, rot, seed, color=YELLOW, alpha=200):
    """Yarı saydam bant, uçları tırtıklı (ayrı bir katmana çizilip bindirilmeli)."""
    rng = random.Random(seed)
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    pts = [(x0, y0), (x1, y0)]
    yy, k = y0, 0
    while yy < y1:
        pts.append((x1 + (2.6 if k % 2 else -2.6) + rng.uniform(-1, 1), yy))
        yy += h / 7
        k += 1
    pts += [(x1, y1), (x0, y1)]
    yy, k = y1, 0
    while yy > y0:
        pts.append((x0 + (2.6 if k % 2 else -2.6) + rng.uniform(-1, 1), yy))
        yy -= h / 7
        k += 1
    sp.polygon(rot_pts(pts, cx, cy, rot), color + (alpha,))
    for f in (0.3, 0.72):
        sp.line(rot_pts([(x0 + 4, y0 + h * f), (x1 - 4, y0 + h * f + rng.uniform(-1, 1))], cx, cy, rot),
                (255, 255, 255, 60), 1.2)


def torn_label(text, size, fg, bg, seed, font="anton", pad=0.16, rim=OFF) -> Sprite:
    """Yırtık kâğıt etiket üstünde kelime; kâğıt kelimenin kendi mürekkep kutusunu sarar (Türkçe şapka/çengel sığar)."""
    fS = fnt(font, size * SS)
    l, t, r, b = fS.getbbox(text, anchor="ls")
    cap = -fS.getbbox("H", anchor="ls")[1] / SS
    top, bot = max(cap, -t / SS), max(0.0, b / SS)
    padx, pady = size * 0.2, size * pad
    w, h = fS.getlength(text) / SS + 2 * padx, top + bot + 2 * pady
    sp = Sprite(w, h, margin=max(14, size * 0.18))
    torn_paper(sp, 0, 0, w, h, bg, seed, rim=rim)
    sp.text((padx, pady + top), text, font, size, fg)
    sp.base_y = pady + top
    return sp


# ---------------------------------------------------------------- arka plan, gren, başlık
_static: dict = {}


def paper_bg() -> Image.Image:
    """Kırık beyaz kâğıt + sessiz nokta ızgarası (bir kez çizilir)."""
    if "paper" not in _static:
        sp = 28
        tile = Image.new("RGB", (sp * 4, sp * 4), OFF)
        ImageDraw.Draw(tile).ellipse([sp * 2 - 4.6, sp * 2 - 4.6, sp * 2 + 4.6, sp * 2 + 4.6], fill=DOT)
        tile = tile.resize((sp, sp), Image.LANCZOS)
        bg = Image.new("RGB", (W, H), OFF)
        for y in range(0, H, sp):
            for x in range(0, W, sp):
                bg.paste(tile, (x, y))
        _static["paper"] = bg.convert("RGBA")
    return _static["paper"]


def red_bg() -> Image.Image:
    if "red" not in _static:
        _static["red"] = Image.new("RGBA", (W, H), RED + (255,))
    return _static["red"]


def grain_layers() -> tuple[Image.Image, Image.Image]:
    """Kolaj'daki hafif kâğıt greni: ekran sabiti, kareden kareye değişmez (titreme yok)."""
    if "grain" not in _static:
        rng = np.random.default_rng(5)
        n = rng.normal(0, 4.2, (H // 2, W // 2)).astype(np.float32)
        n = np.asarray(Image.fromarray(n).resize((W, H), Image.BILINEAR))
        pos = Image.fromarray(np.clip(n, 0, 255).astype(np.uint8)).convert("RGB")
        neg = Image.fromarray(np.clip(-n, 0, 255).astype(np.uint8)).convert("RGB")
        _static["grain"] = (pos, neg)
    return _static["grain"]


def finish(img: Image.Image) -> Image.Image:
    pos, neg = grain_layers()
    return ImageChops.subtract(ImageChops.add(img.convert("RGB"), pos), neg)


def header_layer(no: int, name: str, right: str, kind: str, dark: bool) -> Image.Image:
    """'// 03 — konu' solda; sağda yapıya uygun ilerleme etiketi ya da (ilk sahnede) seri etiketi rozeti."""
    pen = Pen(*HEADER_REGION)
    ink, acc = (OFF, YELLOW) if dark else (INK, RED)
    size, y, x1 = 28, HEADER_Y, 920
    # sağ taraf
    if kind == "pill":
        ps = 26
        lab = fit(right, "mono", ps, 520)
        pw = pill_width(right)
        pen.rr((x1 - pw + 4, y - 27 + 4, x1 + 4, y + 11 + 4), 19, fill=INK)
        pen.rr((x1 - pw, y - 27, x1, y + 11), 19, fill=YELLOW, outline=INK, width=3)
        pen.text(x1 - pw / 2, y, lab, "mono", ps, INK, anchor="ms")
        rx = x1 - pw
    elif kind == "count":                     # "BİLGİ 2/3"
        a, b = right.rsplit(" ", 1)
        wb = tw(b, "mono", size)
        pen.text(x1, y, b, "mono", size, acc, anchor="rs")
        pen.text(x1 - wb - tw(" ", "mono", size), y, a, "mono", size, ink, anchor="rs")
        rx = x1 - wb - tw(" " + a, "mono", size)
    else:
        lab = fit(right, "mono", size, 440)
        pen.text(x1, y, lab, "mono", size, ink, anchor="rs")
        rx = x1 - tw(lab, "mono", size)
    iw = 40
    pen.svg(scissors_svg(28, ring=YELLOW if dark else RED, blade=ink, pivot=RED if dark else YELLOW,
                         outline=None if dark else INK), SCISSORS_VB, rx - iw - 12, y - 24, iw)
    # sol taraf
    x = 72
    pen.text(x, y, "//", "mono", size, acc)
    x += tw("// ", "mono", size)
    pen.text(x, y, fit(f"{no:02d} — {name}", "mono", size, rx - iw - 40 - x), "mono", size, ink)
    return pen.done()


def rule_layer(dark: bool) -> Image.Image:
    """Başlığın altındaki 'buradan kesin' çizgisi (açılışta makas bunu keser)."""
    if ("rule", dark) in _static:
        return _static[("rule", dark)]
    pen = Pen(0, RULE_Y - 6, W, RULE_Y + 6)
    col = blend(RED, OFF, 0.55) if dark else (196, 194, 189)
    x = 72.0
    while x < 920:
        pen.rr((x, RULE_Y - 1.5, min(x + 14, 920), RULE_Y + 1.5), 1.5, fill=col)
        x += 24
    _static[("rule", dark)] = pen.done()
    return _static[("rule", dark)]


# ---------------------------------------------------------------- kinetik kelimeler
def _clean_word(s: str) -> str:
    s = s.strip().strip('"“”«»()[]')
    s = s.rstrip(".,;:…—-") or s
    return tr_upper(s)


class Kinetic:
    """Dış ses, sahne sınırını aşmayan 1-4 kelimelik parçalar hâlinde; her kelime yırtık bir kâğıtta."""
    X0, Y0, X1, Y1 = KIN
    MAXW = 800
    TILT = math.sin(math.radians(3.0))
    REGION = (40, 196, 935, 474)

    def __init__(self, words: list[Word], ranges: list[tuple[int, int]]):
        self.words = words
        self.text = [_clean_word(w.text) for w in words]
        self.chunks: list[list[int]] = []
        for a, b in ranges:
            for ch in render.chunk_words(words[a:b], max_words=4, max_chars=20):
                self.chunks.append([a + i for i in ch])
        self.chunk_of = {i: ci for ci, ch in enumerate(self.chunks) for i in ch}
        self._lay: dict = {}
        self._lab: dict = {}
        self._layer: dict = {}

    def layout(self, ci: int):
        """Parçanın en büyük boyutta en fazla 2 satıra yerleşimi: [(kelime, cx, cy, eğim)], boyut."""
        if ci in self._lay:
            return self._lay[ci]
        idx = self.chunks[ci]
        words = [self.text[i] for i in idx]
        gap = 14
        chosen = None
        for size in range(150, 34, -2):
            fS = fnt("anton", size * SS)
            padx, pady = size * 0.2, size * 0.16
            cap = -fS.getbbox("H", anchor="ls")[1] / SS
            ws, tops, bots = [], [], []
            for w in words:
                l, t, r, b = fS.getbbox(w, anchor="ls")
                ws.append(fS.getlength(w) / SS + 2 * padx)
                tops.append(max(cap, -t / SS) + pady)
                bots.append(max(0, b / SS) + pady)
            lines, cur, cw = [], [], 0.0
            for i, w in enumerate(ws):
                if cur and cw + gap + w > self.MAXW:
                    lines.append(cur)
                    cur, cw = [], 0.0
                cw = cw + (gap if cur else 0) + w
                cur.append(i)
            lines.append(cur)
            if len(lines) > 2 or any(sum(ws[i] for i in ln) + gap * (len(ln) - 1) > self.MAXW for ln in lines):
                continue
            heights = [max(tops[i] for i in ln) + max(bots[i] for i in ln) for ln in lines]
            overlap = size * 0.08
            total_h = sum(heights) - overlap * (len(lines) - 1)
            # eğik etiketin dikey taşması (en fazla 3°) + gölge: alan dışına, başlık çizgisine çıkmasın
            ex_top = max(ws[i] for i in lines[0]) * self.TILT / 2 + 4
            ex_bot = max(ws[i] for i in lines[-1]) * self.TILT / 2 + 12
            if total_h + ex_top + ex_bot <= self.Y1 - self.Y0:
                chosen = (size, lines, ws, tops, heights, overlap, total_h, ex_top, ex_bot)
                break
        if chosen is None:  # son çare: en küçük boyut, tek satır
            size = 36
            chosen = (size, [list(range(len(words)))], [tw(w, "anton", size) + 16 for w in words],
                      [size] * len(words), [size * 1.4], 0, size * 1.4, 0, 0)
        size, lines, ws, tops, heights, overlap, total_h, ex_top, ex_bot = chosen
        rng = random.Random(7000 + idx[0])
        cx0 = (self.X0 + self.X1) / 2
        y = self.Y0 + ex_top + (self.Y1 - self.Y0 - total_h - ex_top - ex_bot) / 2
        out = []
        for li, ln in enumerate(lines):
            base = y + max(tops[i] for i in ln)
            lw = sum(ws[i] for i in ln) + gap * (len(ln) - 1)
            x = cx0 - lw / 2
            for i in ln:
                gi = idx[i]
                sgn = -1 if gi % 2 else 1
                rot = sgn * rng.uniform(0.8, 2.0)
                out.append((gi, x + ws[i] / 2, base, rot, sgn))
                x += ws[i] + gap
            y += heights[li] - overlap
        self._lay[ci] = (out, size)
        return self._lay[ci]

    def label(self, gi: int, state: str, dark: bool, size: int, rot: float, sgn: int):
        key = (gi, state, dark, size)
        if key not in self._lab:
            if state == "said":
                fg, bg, rim = OFF, INK, OFF
            elif state == "cur":
                fg, bg, rim = (INK, YELLOW, OFF) if dark else (OFF, RED, OFF)
            else:
                fg, bg, rim = UPC_FG, UPC_BG, OFF
            lab = torn_label(self.text[gi], size, fg, bg, 900 + gi * 7, rim=rim)
            r = sgn * 3.0 if state == "cur" else rot
            im = lab.render(r, shadow=(4, 7, 4, 0.32 if state == "cur" else 0.24))
            self._lab[key] = (im, lab.base_y, lab.h)
        return self._lab[key]

    def layer(self, ci: int, cur: int, dark: bool):
        """(kalanların katmanı, şu anki kelimenin görüntüsü, merkezi). cur: parçadaki o anki kelimenin indeksi."""
        key = (ci, cur, dark)
        if key in self._layer:
            return self._layer[key]
        lay, size = self.layout(ci)
        rx0, ry0, rx1, ry1 = self.REGION
        rest = Image.new("RGBA", (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
        cur_im = cur_c = None
        for gi, cx, base, rot, sgn in lay:
            state = "said" if gi < cur else ("cur" if gi == cur else "up")
            im, base_y, h = self.label(gi, state, dark, size, rot, sgn)
            cy = base - base_y + h / 2
            if state == "cur":
                cur_im, cur_c = im, (cx, cy)
                continue
            _comp(rest, im, cx - im.width / 2 - rx0, cy - im.height / 2 - ry0)
        if len(self._layer) > 64:
            self._layer.clear()
        self._layer[key] = (rest, cur_im, cur_c)
        return self._layer[key]


# ---------------------------------------------------------------- kart kabuğu
def shell(pen: Pen, box, title: str, chip: str | None = None, bar=YELLOW, body=WHITE, r=24):
    """Pencere kart: sert mürekkep gölge, 4 px mürekkep çerçeve, makas halkalı sarı başlık çubuğu, mono başlık, çip."""
    x0, y0, x1, y1 = box
    bar_h = 68
    pen.rr((x0 + CARD_SH, y0 + CARD_SH, x1 + CARD_SH, y1 + CARD_SH), r, fill=INK)
    pen.rr(box, r, fill=body, outline=INK, width=4)
    pen.rr((x0, y0, x1, y0 + bar_h), r, fill=bar, outline=INK, width=4, corners=(True, True, False, False))
    mini_rings(pen, x0 + 34, y0 + bar_h / 2, inner=bar)
    tx, avail = x0 + 86, x1 - 24 - (x0 + 86)
    if chip:
        cw = tw(chip, "mono", 26) + 30
        cx1 = x1 - 18
        pen.rr((cx1 - cw, y0 + 15, cx1, y0 + bar_h - 15), 19, fill=INK)
        pen.text(cx1 - cw / 2, y0 + bar_h / 2 + 9, chip, "mono", 26, OFF, anchor="ms")
        avail = cx1 - cw - 18 - tx
    pen.text(tx, y0 + bar_h / 2 + 9, fit(title, "mono", 26, avail), "mono", 26, INK)
    return inner_of(box)


def inner_of(box):
    return (box[0] + 4, box[1] + 68, box[2] - 4, box[3] - 4)


def chip_label(pen: Pen, x, y, text, size=28, rot=2.0, max_w=640):
    """Sarı not çipi (kırmızı noktalı), hafif eğik; sol üst köşesi (x, y)."""
    text = fit(text, "mono", size, max_w - 62)
    cw, ch = tw(text, "mono", size) + 62, 58
    s = pen.s
    im = Image.new("RGBA", (int((cw + 20) * s), int((ch + 20) * s)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([6 * s, 6 * s, (cw + 6) * s, (ch + 6) * s], 10 * s, fill=INK)
    d.rounded_rectangle([0, 0, cw * s, ch * s], 10 * s, fill=YELLOW, outline=INK, width=4 * s)
    d.ellipse([16 * s, (ch / 2 - 6) * s, 28 * s, (ch / 2 + 6) * s], fill=RED)
    d.text((40 * s, (ch / 2 + 10) * s), text, font=fnt("mono", size * s), fill=INK, anchor="ls")
    im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    pen.paste(im, x, y)


def wrap(text: str, font: str, size: float, width: float) -> list[list[str]]:
    lines, cur, cw = [], [], 0.0
    sp = tw(" ", font, size)
    for w in text.split():
        ww = tw(w.strip("*"), font, size)
        if cur and cw + sp + ww > width:
            lines.append(cur)
            cur, cw = [], 0.0
        cw += (sp if cur else 0) + ww
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def fit_block(text: str, fonts: tuple, width: float, height: float, max_size: int, min_size: int, lh=1.16,
              max_lines: int = 4):
    """Metni kutuya sığdıran (font, boyut, satırlar). Uzun tek kelime sığmazsa daha dar fonta geçer."""
    for font in fonts:
        for size in range(max_size, min_size - 1, -2):
            lines = wrap(text, font, size, width)
            if len(lines) <= max_lines and len(lines) * size * lh <= height and all(
                    tw(" ".join(w.strip("*") for w in L), font, size) <= width for L in lines):
                return font, size, lines
    font = fonts[-1]
    size = min_size
    while size > 30 and any(tw(w, font, size) > width for w in text.split()):
        size -= 2
    return font, size, wrap(text, font, size, width)


# ---------------------------------------------------------------- kartlar
class Card:
    """Kart katmanı CARD_REGION'u kaplar. layer(lt, dur) o anın görüntüsünü verir (durağan kartlarda önbellek)."""
    still = True

    def __init__(self, ctx: dict):
        self.ctx = ctx
        self.spec = ctx["spec"]
        self.c = ctx["spec"].card or {}
        self.idx = ctx["idx"]
        self.hook = ctx["idx"] == 0     # kanca karesi: kart ilk karede tamamlanmış görünür
        self._static = None

    def pen(self) -> Pen:
        return Pen(*CARD_REGION)

    def static(self) -> Image.Image:
        raise NotImplementedError

    def layer(self, lt: float, dur: float) -> Image.Image | None:
        if self._static is None:
            self._static = self.static()
        return self._static

    def mood(self, lt: float, dur: float) -> str:
        return "normal"

    @property
    def topic_slug(self) -> str:
        return self.ctx["slug"]


def archival(im: Image.Image, seed: int) -> Image.Image:
    """Mürekkep → sıcak kâğıt duotone + film greni: arşiv baskısı gibi okunur."""
    g = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    g = ImageOps.colorize(g, black=INK, white=(241, 234, 219), mid=(140, 130, 112))
    a = np.asarray(g).astype(np.int16)
    a = a + np.random.default_rng(seed).normal(0, 8, a.shape[:2])[..., None].astype(np.int16)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def cover(im: Image.Image, w: int, h: int, focus=(0.5, 0.38)) -> Image.Image:
    s = max(w / im.width, h / im.height)
    nw, nh = int(math.ceil(im.width * s)), int(math.ceil(im.height * s))
    im = im.resize((nw, nh), Image.LANCZOS)
    left = int(clamp(focus[0] * nw - w / 2, 0, nw - w))
    top = int(clamp(focus[1] * nh - h / 2, 0, nh - h))
    return im.crop((left, top, left + w, top + h))


class PhotoCard(Card):
    """Arşiv duotone fotoğraf, bant, not çipi ve dosya adlı başlık çubuğu; fotoğraf sahne boyunca hafif yakınlaşır."""
    still = False

    def __init__(self, ctx):
        super().__init__(ctx)
        rx0, ry0 = CARD_REGION[:2]
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, CARD, f"{self.topic_slug} / arsiv_{self.idx + 1:02d}.jpg", tr_upper("arşiv"))
        self.pb = (int(ix0 + 20), int(iy0 + 20), int(ix1 - 20), int(iy1 - 20))
        self.base = pen.done()
        px0, py0, px1, py1 = self.pb
        pw, ph = px1 - px0, py1 - py0
        src = Image.open(self.spec.image).convert("RGB")
        self.src = archival(cover(src, int(pw * 1.1), int(ph * 1.1)), 31 + self.idx)
        self.size = (pw, ph)
        self.pos = (px0 - rx0, py0 - ry0)
        # üst katman: köşe yuvarlatma, çerçeve, bant, not çipi
        ov = self.pen()
        ov.rr((px0, py0, px1, py1), 0, fill=WHITE + (255,))
        ov.rr((px0, py0, px1, py1), 12, fill=(0, 0, 0, 0))
        ov.rr((px0, py0, px1, py1), 12, outline=INK, width=4)
        tl = Sprite(170, 44, 10)
        tape(tl, 85, 22, 170, 44, -3, 40 + self.idx, alpha=215)
        ov.paste(tl.im, (px0 + px1) / 2 - 95, py0 - 22 - 10)
        note = (self.c.get("note") or "").strip()
        if note:
            chip_label(ov, px0 + 22, py1 - 96, note, max_w=pw - 60)
        self.over = ov.done()
        self.zoom_end = 1.1

    def layer(self, lt, dur):
        p = clamp(lt / max(0.5, dur))
        z = lerp(1.0, self.zoom_end, ease_in_out(p) * 0.6 + p * 0.4)
        sw, sh = self.src.size
        cw, ch = sw / z, sh / z
        cx, cy = sw / 2, sh / 2 - (sh - ch) * 0.15
        ph = self.src.resize(self.size, Image.BILINEAR, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))
        img = self.base.copy()
        img.paste(ph, self.pos)
        img.alpha_composite(self.over)
        return img


class DrawingCard(Card):
    """illustrate.py çizimi (şeffaf PNG) beyaz kartta, hafif noktalı çizim kâğıdı ve sert açık gölge ile."""

    def static(self):
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, CARD, f"{self.topic_slug} / cizim_{self.idx + 1:02d}.png", tr_upper("çizim"))
        for y in range(int(iy0) + 26, int(iy1) - 16, 26):
            for x in range(int(ix0) + 26, int(ix1) - 16, 26):
                pen.ell(x, y, 2.0, fill=(234, 232, 227))
        note = (self.c.get("note") or "").strip()
        bottom = iy1 - (96 if note else 30)
        im = Image.open(self.spec.sprite).convert("RGBA")
        bb = im.getchannel("A").getbbox()
        if bb:
            im = im.crop(bb)
        bw, bh = (ix1 - ix0) - 90, bottom - iy0 - 40
        k = min(bw / im.width, bh / im.height)
        dw, dh = im.width * k, im.height * k
        im2 = im.resize((max(1, int(dw * SS)), max(1, int(dh * SS))), Image.LANCZOS)
        sh = Image.new("RGBA", im2.size, (226, 223, 216, 0))
        sh.putalpha(im2.getchannel("A"))
        dx, dy = (ix0 + ix1) / 2 - dw / 2, iy0 + 22 + (bottom - iy0 - 22 - dh) / 2
        pen.paste(sh, dx + 10, dy + 10)
        pen.paste(im2, dx, dy)
        if note:
            chip_label(pen, ix0 + 26, iy1 - 84, note, max_w=ix1 - ix0 - 60)
        return pen.done()


def parse_value(s: str):
    """'21.196' / '%90' / '1,5 milyon' -> (ön ek, değer, ondalık hane, binlik ayraç var mı, son ek)."""
    m = re.search(r"\d[\d.,]*", s or "")
    if not m:
        return None
    num = m.group(0).rstrip(".,")
    pre, suf = s[:m.start()], s[m.start() + len(num):]
    ip, dp = (num.split(",", 1) + [""])[:2] if "," in num else (num, "")
    grouped = "." in ip
    if grouped and not re.fullmatch(r"\d{1,3}(\.\d{3})+", ip):  # '3.5' gibi İngilizce ondalık: sayma yok
        return None
    try:
        v = float(ip.replace(".", "") + ("." + dp if dp else ""))
    except ValueError:
        return None
    return pre, v, len(dp), grouped, suf


def fmt_value(v: float, dec: int, grouped: bool) -> str:
    s = f"{v:,.{dec}f}" if grouped else f"{v:.{dec}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


class CounterCard(Card):
    """0'dan değere ~0,8 sn'de sayan büyük sayı + etiket + değere bağlı kesik çizgi zaman çizelgesi."""
    still = False
    COUNT = 0.8

    def __init__(self, ctx):
        super().__init__(ctx)
        raw = (self.c.get("value") or "").strip()
        self.parsed = parse_value(raw)
        self.raw = raw
        self.label = tr_upper((self.c.get("label") or "").strip())
        self.note = (self.c.get("note") or "").strip()
        pen = self.pen()
        ix0, iy0, ix1, iy1 = self.inner = shell(pen, CARD, f"sayaç / {slug(self.label or 'deger', 24) or 'deger'}.log",
                                                tr_upper("sayaç"))
        cx = (ix0 + ix1) / 2
        final = self.text_at(1.0)
        self.size = 250
        while self._num_w(final, self.size) > ix1 - ix0 - 90 and self.size > 120:
            self.size -= 6
        cap = -tbox("8", "anton", self.size)[1]
        self.base_y = iy0 + 42 + cap
        y = self.base_y + 100
        if self.label:
            ls = 48
            while tw(self.label, "archivo", ls) > ix1 - ix0 - 80 and ls > 30:
                ls -= 2
            pen.text(cx, y, self.label, "archivo", ls, INK, anchor="ms")
        if self.note:
            pen.text(cx, y + 56, fit(self.note, "mono", 28, ix1 - ix0 - 70), "mono", 28, DGREY, anchor="ms")
        # zaman çizelgesi: kesik çizgi, uçlarda 0 ve hedef değer
        self.ly = iy1 - 96
        self.lx0, self.lx1 = ix0 + 60, ix1 - 60
        x = self.lx0
        while x < self.lx1:
            pen.rr((x, self.ly - 3, min(x + 18, self.lx1), self.ly + 3), 3, fill=GREY)
            x += 30
        for k in range(1, 4):
            tx = lerp(self.lx0, self.lx1, k / 4)
            pen.rr((tx - 2, self.ly - 10, tx + 2, self.ly + 10), 2, fill=GREY)
        for xx, lab, anc in ((self.lx0, "0", "ls"), (self.lx1, final, "rs")):
            pen.ell(xx, self.ly, 9, fill=WHITE, outline=INK, width=4)
            pen.text(xx - (6 if anc == "ls" else -6), self.ly + 52, lab, "mono", 28, INK, anchor=anc)
        self.base = pen.done()
        self._fin = None

    def progress(self, lt: float) -> float:
        return 1.0 if (self.hook or self.parsed is None) else ease_out_cubic(lt / self.COUNT)

    def text_at(self, e: float) -> str:
        if self.parsed is None:
            return self.raw or "?"
        pre, v, dec, grouped, suf = self.parsed
        cur = v * e
        if dec == 0:
            cur = math.floor(cur + 1e-9) if e < 1 else v
        return pre + fmt_value(cur, dec, grouped) + suf

    def _num_w(self, s, size):
        dw = max(tw(d, "anton", size) for d in "0123456789")
        return sum(dw if ch.isdigit() else tw(ch, "anton", size) for ch in s)

    def _number(self, pen: Pen, s: str, cx, base, size):
        """Rakamlar sabit genişlikte yuvalarda: sayarken sayı titremez."""
        dw = max(tw(d, "anton", size) for d in "0123456789")
        total = self._num_w(s, size)
        x = cx - total / 2
        for ch in s:
            w = dw if ch.isdigit() else tw(ch, "anton", size)
            pen.text(x + w / 2, base, ch, "anton", size, INK, anchor="ms")
            x += w

    def draw_dynamic(self, lt) -> Image.Image:
        e = self.progress(lt)
        img = self.base.copy()
        ix0, iy0, ix1, iy1 = self.inner
        cx = (ix0 + ix1) / 2
        pen = Pen(ix0, iy0, ix1, iy1)
        land = clamp((lt - self.COUNT) / 0.2) if not self.hook else 1.0
        pop = 1 + 0.06 * math.sin(math.pi * land) if 0 < land < 1 else 1.0
        s = self.text_at(e)
        self._number(pen, s, cx, self.base_y, self.size * pop)
        uw = self._num_w(self.text_at(1.0), self.size) * e
        pen.rr((cx - uw / 2, self.base_y + 18, cx + uw / 2, self.base_y + 32), 7, fill=RED)
        hx = lerp(self.lx0, self.lx1, e)        # ilerleme = sayılan değer / hedef değer
        if hx > self.lx0 + 2:
            pen.rr((self.lx0, self.ly - 5, hx, self.ly + 5), 5, fill=RED)
        for k in range(1, 4):
            tx = lerp(self.lx0, self.lx1, k / 4)
            if tx <= hx:
                pen.rr((tx - 2, self.ly - 10, tx + 2, self.ly + 10), 2, fill=RED)
        moving = 0 < e < 1
        iw = 92
        pen.svg(scissors_svg(34 if (moving and int(lt * 20) % 2) else 18), SCISSORS_VB,
                hx - iw * 58 / 124, self.ly - iw * 84 / 124 / 2, iw)
        lay = pen.done()
        img.alpha_composite(lay, (int(ix0) - CARD_REGION[0], int(iy0) - CARD_REGION[1]))
        return img

    def layer(self, lt, dur):
        if self.progress(lt) >= 1 and (self.hook or lt >= self.COUNT + 0.2):
            if self._fin is None:
                self._fin = self.draw_dynamic(10.0)
            return self._fin
        return self.draw_dynamic(lt)

    def mood(self, lt, dur):
        return "surprised" if (self.hook or lt >= self.COUNT) else "normal"


def _rich(text: str) -> list[tuple[str, bool]]:
    out, emph = [], False
    for w in text.split():
        if w.startswith("*"):
            emph = True
        out.append((w.strip("*"), emph))
        if w.endswith("*"):
            emph = False
    return out


class CompareCard(Card):
    """EFSANE (çizilir) ve GERÇEK sütunları. İnanış çizilmeden önce okunur; çizik canlanır, sonra gerçek açılır."""
    still = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self.myth = (self.c.get("myth") or "").strip()
        self.fact = (self.c.get("fact") or "").strip()
        self.note = (self.c.get("note") or "").strip()
        dur = max(0.6, ctx["dur"])
        self.t_strike = min(0.65, 0.22 * dur)
        self.t_reveal = self.t_strike + 0.5
        ix0, iy0, ix1, iy1 = self.inner = inner_of(CARD)
        pad, gap = 22, 34
        foot = 56 if self.note else 0
        cw = (ix1 - ix0 - 2 * pad - gap) / 2
        self.cols = [(ix0 + pad, iy0 + pad, ix0 + pad + cw, iy1 - pad - foot),
                     (ix0 + pad + cw + gap, iy0 + pad, ix1 - pad, iy1 - pad - foot)]
        self.text_box = [(bx0 + 24, by0 + 98, bx1 - 22, by1 - 22) for bx0, by0, bx1, by1 in self.cols]
        tb = self.text_box[0]
        both = self.myth + " " + self.fact
        # iki sütun aynı yazı boyutunu kullanır (en az 48 px, kalın dar yüz)
        font, size, _ = fit_block(both, ("oswald", "anton"), tb[2] - tb[0], 10_000, 80, 48)
        for txt in (self.myth, self.fact):
            f2, s2, _ = fit_block(txt, (font, "anton"), tb[2] - tb[0], tb[3] - tb[1], size, 44, lh=1.12)
            if s2 < size or f2 != font:
                font, size = f2, s2
        self.font, self.fsize = font, size
        self.lines = [wrap(t, font, size, tb[2] - tb[0]) for t in (self.myth, self.fact)]
        self.pre = self._render(revealed=False)
        self.post = self._render(revealed=True)
        self.strike = self._strike_layer()
        self._fin = None

    def _col_text(self, pen: Pen, ci: int):
        font, size = self.font, self.fsize
        tx0, ty0, tx1, ty1 = self.text_box[ci]
        lh = size * 1.12
        lines = self.lines[ci]
        yb = ty0 + (ty1 - ty0 - len(lines) * lh) / 2 + size * 0.86
        out = []
        for L in lines:
            x = tx0
            for w, e in _rich(" ".join(L)):
                col = (78, 76, 73) if ci == 0 else (RED if e else INK)
                pen.text(x, yb, w, font, size, col)
                x += tw(w + " ", font, size)
            out.append((tx0, x - tw(" ", font, size), yb - size * 0.3))
            yb += lh
        return out

    def _render(self, revealed: bool) -> Image.Image:
        pen = self.pen()
        shell(pen, CARD, "efsane / gerçek", tr_upper("karşılaştır"))
        (a0, a1, a2, a3), (b0, b1, b2, b3) = self.cols
        pen.rr(self.cols[0], 16, fill=PAPER, outline=INK, width=3)
        pen.rr(self.cols[1], 16, fill=YEL_LIGHT if revealed else WHITE, outline=INK, width=3)
        for ci, (bx0, by0, bx1, by1) in enumerate(self.cols):
            ttl = tr_upper("efsane" if ci == 0 else "gerçek")
            tag_w = tw(ttl, "archivo", 30) + 36
            ty = by0 + 22
            if ci == 0:
                pen.rr((bx0 + 20, ty, bx0 + 20 + tag_w, ty + 54), 27, fill=WHITE, outline=INK, width=3)
                pen.text(bx0 + 20 + tag_w / 2, ty + 40, ttl, "archivo", 30, DGREY, anchor="ms")
            else:
                pen.rr((bx0 + 20, ty, bx0 + 20 + tag_w, ty + 54), 27, fill=INK)
                pen.text(bx0 + 20 + tag_w / 2, ty + 40, ttl, "archivo", 30, YELLOW, anchor="ms")
            bcx, bcy, br = bx1 - 46, ty + 27, 28
            if ci == 0 or revealed:
                pen.ell(bcx + 4, bcy + 4, br, fill=INK)
                pen.ell(bcx, bcy, br, fill=RED if ci == 0 else YELLOW, outline=INK, width=4)
                body = cross_svg(OFF, 16) if ci == 0 else check_svg(INK, 15)
                pen.svg(body, ICON_VB, bcx - br * 0.82, bcy - br * 0.82, br * 1.64)
            else:
                pen.ell(bcx, bcy, br, fill=WHITE, outline=INK, width=4)
                pen.text(bcx, bcy + 14, "?", "anton", 40, INK, anchor="ms")
        self.strike_rows = self._col_text(pen, 0)
        if revealed:
            self._col_text(pen, 1)
        else:
            tx0, ty0, tx1, ty1 = self.text_box[1]
            pen.text((tx0 + tx1) / 2, (ty0 + ty1) / 2 + 80, "?", "anton", 220, (222, 219, 213), anchor="ms")
        ix0, iy0, ix1, iy1 = self.inner
        mx, my = (a2 + b0) / 2, (a1 + a3) / 2 + 30
        pen.ell(mx + 4, my + 4, 27, fill=INK)
        pen.ell(mx, my, 27, fill=RED, outline=INK, width=4)
        pen.svg(arrow_svg(OFF, 16), ICON_VB, mx - 20, my - 20, 40)
        if self.note:
            pen.text((ix0 + ix1) / 2, iy1 - 26, fit(self.note, "mono", 26, ix1 - ix0 - 60), "mono", 26, DGREY,
                     anchor="ms")
        return pen.done()

    def _strike_layer(self) -> Image.Image:
        pen = self.pen()
        for li, (x0, x1, y) in enumerate(self.strike_rows):
            rng = random.Random(500 + self.idx * 31 + li)
            n, tilt = 14, rng.uniform(-4, 4)
            pts = []
            for i in range(n + 1):
                t = i / n
                pts.append((x0 - 8 + (x1 - x0 + 16) * t, y + tilt * (t - 0.5) * 2 + math.sin(t * 6 + li) * 1.5))
            pen.line(pts, RED, 7)
            pen.ell(*pts[0], 3.5, fill=RED)
            pen.ell(*pts[-1], 3.5, fill=RED)
        return pen.done()

    def layer(self, lt, dur):
        if self.hook or lt >= self.t_reveal + 0.35:
            if self._fin is None:
                self._fin = self.post.copy()
                self._fin.alpha_composite(self.strike)
            return self._fin
        rx0, ry0 = CARD_REGION[:2]
        img = self.pre.copy() if lt < self.t_reveal else self.post.copy()
        if lt >= self.t_reveal:  # gerçek sütunu soldan sağa açılır
            k = ease_out_cubic((lt - self.t_reveal) / 0.35)
            bx0, by0, bx1, by1 = (int(v) for v in self.cols[1])
            wv = int((bx1 - bx0 + 6) * k)
            if wv < bx1 - bx0 + 6:
                pre = self.pre.crop((bx0 - rx0 + wv, by0 - ry0 - 2, bx1 - rx0 + 6, by1 - ry0 + 6))
                img.paste(pre, (bx0 - rx0 + wv, by0 - ry0 - 2))
        for li, (x0, x1, y) in enumerate(self.strike_rows):  # satır satır çizilen kırmızı çizik
            k = ease_out_cubic((lt - self.t_strike - li * 0.1) / 0.3)
            if k <= 0:
                continue
            xe = int(x0 - 12 + (x1 - x0 + 24) * k) - rx0
            band = (int(x0 - 14) - rx0, int(y - 16) - ry0, xe, int(y + 16) - ry0)
            if band[2] > band[0]:
                img.alpha_composite(self.strike.crop(band), band[:2])
        return img

    def mood(self, lt, dur):
        return "thinking" if (not self.hook and lt < self.t_reveal) else "normal"


class QuoteCard(Card):
    """Daktiloyla yazılan alıntı + kaynak çipi."""
    still = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self.quote = (self.c.get("label") or self.spec.narration).strip().strip('"“”')
        self.src = (self.c.get("note") or "").strip()
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, CARD, f"alıntı / {slug(self.src.split('·')[0], 20) or 'kaynak'}.txt",
                                   tr_upper("alıntı"))
        qm = ink_box("“", "anton", 200)
        pen.text(ix0 + 40 - qm[0], iy0 + 30 - qm[1], "“", "anton", 200, RED)
        self.box = (ix0 + 64, iy0 + 30 + (qm[3] - qm[1]) + 18, ix1 - 46, iy1 - (108 if self.src else 50))
        bx0, by0, bx1, by1 = self.box
        self.font, self.fsize, self.lines = fit_block(self.quote, ("archivo",), bx1 - bx0, by1 - by0, 64, 40, lh=1.22,
                                                      max_lines=6)
        if self.src:
            s = fit("— " + self.src, "mono", 28, ix1 - ix0 - 110)
            cw = tw(s, "mono", 28) + 40
            pen.rr((ix0 + 40 + 5, iy1 - 96 + 5, ix0 + 40 + cw + 5, iy1 - 40 + 5), 28, fill=RED)
            pen.rr((ix0 + 40, iy1 - 96, ix0 + 40 + cw, iy1 - 40), 28, fill=INK)
            pen.text(ix0 + 60, iy1 - 58, s, "mono", 28, OFF)
        self.base = pen.done()
        self.n_total = len(" ".join(" ".join(L) for L in self.lines))
        dur = max(0.8, ctx["dur"])
        self.t0, self.cps = 0.12, self.n_total / max(0.6, min(1.5, 0.55 * dur))
        self._cache: dict = {}

    def _text(self, n: int, cursor: bool) -> Image.Image:
        key = (n, cursor)
        if key not in self._cache:
            bx0, by0, bx1, by1 = self.box
            pen = Pen(bx0 - 10, by0 - 10, bx1 + 30, by1 + 10)
            size, lh = self.fsize, self.fsize * 1.22
            yb = by0 + (by1 - by0 - len(self.lines) * lh) / 2 + size * 0.95
            left, x = n, bx0
            for L in self.lines:
                s = " ".join(L)
                part = s[:max(0, left)]
                pen.text(bx0, yb, part, self.font, size, INK)
                x = bx0 + tw(part, self.font, size)
                left -= len(s) + 1
                if left < 0:
                    break
                yb += lh
            if cursor:
                pen.rr((x + 6, yb - size * 0.78, x + 6 + size * 0.28, yb + 4), 2, fill=RED)
            if len(self._cache) > 160:
                self._cache.clear()
            self._cache[key] = pen.done()
        return self._cache[key]

    def layer(self, lt, dur):
        n = self.n_total if self.hook else int(clamp((lt - self.t0) * self.cps, 0, self.n_total))
        cursor = n < self.n_total or int(lt * 2.4) % 2 == 0
        img = self.base.copy()
        bx0, by0 = self.box[:2]
        img.alpha_composite(self._text(n, cursor), (int(bx0 - 10) - CARD_REGION[0], int(by0 - 10) - CARD_REGION[1]))
        return img


class InterstitialCard(Card):
    """Ara kanca: tam kırmızı ekran, görünür bantta yarım ton silme, bantlı yırtık mürekkep kart (sahne başlığı)."""
    still = False

    def __init__(self, ctx):
        super().__init__(ctx)
        lines = [tr_upper(x) for x in self.spec.headline if x.strip()] or ["AMA ASIL", "ŞAŞIRTICI", "OLAN"]
        hl = self.spec.highlight_line if 0 <= self.spec.highlight_line < len(lines) else len(lines) - 1
        sizes = [150 if i == hl else 118 for i in range(len(lines))]
        maxw = 640
        for i, ln in enumerate(lines):
            while tw(ln, "anton", sizes[i]) > maxw and sizes[i] > 50:
                sizes[i] -= 4
        while sum(-tbox("H", "anton", s)[1] + 30 for s in sizes) > 470:
            sizes = [s - 4 for s in sizes]
        w = int(max(tw(ln, "anton", s) for ln, s in zip(lines, sizes)) + 130)
        h = int(sum(-tbox("H", "anton", s)[1] for s in sizes) + 32 * (len(lines) - 1) + 150)
        sp = Sprite(w, h, 60)
        torn_paper(sp, 0, 0, w, h, INK, 81 + self.idx, jitter=4, rim=OFF, rim_w=3)
        y = 84
        for i, (ln, sz) in enumerate(zip(lines, sizes)):
            y += -tbox("H", "anton", sz)[1]
            sp.text((62, y), ln, "anton", sz, YELLOW if i == hl else OFF)
            y += 32
        tp = Sprite(w, h, 60)
        tape(tp, 64, -4, 150, 44, -22, 82 + self.idx, alpha=225)
        tape(tp, w - 58, h - 2, 150, 44, -16, 83 + self.idx, alpha=225)
        tab = tr_upper("// dur bir saniye")
        tabw = tw(tab, "mono", 26) + 34
        tp.d.rounded_rectangle([*tp.p(w - tabw - 40, -24), *tp.p(w - 40, 24)], radius=14 * SS, fill=YELLOW,
                               outline=INK, width=4 * SS)
        tp.text((w - 40 - tabw / 2, 9), tab, "mono", 26, INK, anchor="ms")
        sp.im.alpha_composite(tp.im)
        im = sp.render(-3.0, shadow=(10, 16, 12, 0.38))
        im = im.crop(im.getchannel("A").point(lambda v: 255 if v > 4 else 0).getbbox())
        rx0, ry0, rx1, ry1 = CARD_REGION
        bx0, by0, bx1, by1 = CARD[0] - 24, CARD[1] - 16, SAFE_X - 6, CARD_FLOOR - 4  # gölge ve bantlar dahil
        k = min(1.0, (bx1 - bx0) / im.width, (by1 - by0) / im.height)
        if k < 1:
            im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
        lay = Image.new("RGBA", (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
        cx, cy = (CARD[0] + CARD[2] + CARD_SH) / 2 - rx0, (by0 + by1) / 2 - ry0
        _comp(lay, im, cx - im.width / 2, cy - im.height / 2)
        self.sprite = lay
        self.appear = 0.0 if self.hook else WIPE * 0.55

    def layer(self, lt, dur):
        return self.sprite

    def scale(self, lt) -> float | None:
        """Kırmızı indikten sonra kart küçükten 'pat' diye oturur. Büyükten küçülmek (1.2→1) kartın üst kenarını
        kinetik yazının üstüne taşırdı; tepe değeri 1.006 ile sınırlı (üst kenar ≤ 4 px yükselir)."""
        if self.hook:
            return 1.0  # kanca: ilk karede tam boy
        if lt < self.appear:
            return None
        x = (lt - self.appear) / 0.3
        return 1.0 if x >= 1 else min(1.006, 0.84 + 0.16 * ease_out_back(x, 2.2))

    def mood(self, lt, dur):
        return "surprised"


class CtaCard(Card):
    """Son sahnenin soru kartı: soru, 'YORUMLARA YAZ' etiketi, kupon çizgisi ve kanal adı. Makas mutlu."""
    still = False

    def __init__(self, ctx):
        super().__init__(ctx)
        q = (self.c.get("label") or "").strip()
        if not q:
            sents = re.split(r"(?<=[.?!])\s+", self.spec.narration.strip())
            qs = [s for s in sents if s.endswith("?")]
            q = qs[0] if qs else (" ".join(self.spec.headline).strip() or "Sence?")
        self.q = q
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, CARD, "son / yorum.txt", tr_upper("soru"))
        cx = (ix0 + ix1) / 2
        qh = 222
        font, size, lines = fit_block(q, ("archivo",), ix1 - ix0 - 100, qh, 62, 38, lh=1.2, max_lines=3)
        lh = size * 1.2
        yb = iy0 + 30 + (qh - len(lines) * lh) / 2 + size * 0.92
        for L in lines:
            pen.text(cx, yb, " ".join(L), font, size, INK, anchor="ms")
            yb += lh
        # yorum etiketi (ayrı katman: hafifçe nabız atar)
        st = tr_upper("yorumlara yaz")
        ssz = 92
        while tw(st, "anton", ssz) + 150 > ix1 - ix0 - 120:
            ssz -= 4
        bw, bh = tw(st, "anton", ssz) + 150, ssz * 1.18
        sp = Pen(0, 0, bw + 30, bh + 30)
        sp.rr((10, 10, bw + 10, bh + 10), 14, fill=INK)
        sp.rr((0, 0, bw, bh), 14, fill=RED, outline=INK, width=4)
        cap = -tbox("H", "anton", ssz)[1]
        sp.text(36, bh / 2 + cap / 2, st, "anton", ssz, OFF)
        sp.svg(arrow_svg(OFF, 15, "down"), ICON_VB, bw - 100, bh / 2 - 38, 76)
        self.sticker = sp.done().rotate(2.0, resample=Image.BICUBIC, expand=True)
        self.sticker_c = (cx, iy0 + 330)
        # kupon çizgisi + kanal adı
        ly = iy0 + 448
        x = ix0 + 110
        while x < ix1 - 40:
            pen.rr((x, ly - 2, min(x + 16, ix1 - 40), ly + 2), 2, fill=GREY)
            x += 26
        pen.svg(scissors_svg(30), SCISSORS_VB, ix0 + 30, ly - 25, 72)
        pen.text(cx, ly + 70, self.ctx.get("handle", "@bilgimakasi"), "archivo", 44, INK, anchor="ms")
        self.base = pen.done()

    def layer(self, lt, dur):
        img = self.base.copy()
        k = 1.0 if lt < 0.4 else 1 + 0.035 * (0.5 - 0.5 * math.cos((lt - 0.4) * 2 * math.pi / 1.1))
        st = self.sticker
        if k != 1.0:
            st = st.resize((int(st.width * k), int(st.height * k)), Image.BILINEAR)
        cx, cy = self.sticker_c
        _comp(img, st, cx - st.width / 2 - CARD_REGION[0], cy - st.height / 2 - CARD_REGION[1])
        return img

    def mood(self, lt, dur):
        return "happy"


class TextCard(Card):
    """Yedek kart (fotoğraf/çizim/veri yoksa): başlık satırları kartın içinde yırtık etiketlerde."""

    def static(self):
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, CARD, "not / makas.txt", tr_upper("not"))
        lines = [tr_upper(x) for x in self.spec.headline if x.strip()] or [tr_upper(self.spec.narration[:30])]
        hl = self.spec.highlight_line
        note = (self.c.get("note") or "").strip()
        avail_h = iy1 - iy0 - (110 if note else 60)
        size = 150
        while size > 50 and (any(tw(ln, "anton", size) + size * 0.4 > ix1 - ix0 - 90 for ln in lines)
                             or len(lines) * size * 1.25 > avail_h):
            size -= 4
        labs = []
        for i, ln in enumerate(lines):
            fg, bg = (INK, YELLOW) if i == hl else ((OFF, INK) if i % 2 == 0 else (INK, PAPER))
            labs.append(torn_label(ln, size, fg, bg, 300 + self.idx * 11 + i))
        total = sum(lb.h for lb in labs) + 14 * (len(labs) - 1)
        y = iy0 + 30 + (avail_h - total) / 2
        cx = (ix0 + ix1) / 2
        for i, lb in enumerate(labs):
            im = lb.render_ss((-1.6 if i % 2 else 1.4), shadow=(4, 7, 4, 0.25))
            iw, ih = im.width / SS, im.height / SS
            pen.paste(im, cx - iw / 2 + (18 if i % 2 else -10), y + lb.h / 2 - ih / 2)
            y += lb.h + 14
        if note:
            pen.text(cx, iy1 - 40, fit(note, "mono", 28, ix1 - ix0 - 70), "mono", 28, DGREY, anchor="ms")
        return pen.done()


CARD_CLASSES = {"photo": PhotoCard, "drawing": DrawingCard, "counter": CounterCard, "compare": CompareCard,
                "quote": QuoteCard, "interstitial": InterstitialCard, "cta": CtaCard, "text": TextCard}


def card_type(spec, idx: int, n: int) -> str:
    """Sahnenin kart türü. Açık seçim (card) veriyle destekleniyorsa geçerli; 'auto' için: son sahne cta,
    'AMA ASIL…'/'ASIL…' başlık interstitial, card_value counter, card_myth+card_fact compare, alıntı quote,
    sonra fotoğraf, çizim, yoksa yazı kartı."""
    c = spec.card or {}
    has_photo, has_drawing = spec.image is not None, spec.sprite is not None
    data = {"counter": bool((c.get("value") or "").strip()),
            "compare": bool((c.get("myth") or "").strip() and (c.get("fact") or "").strip()),
            "quote": bool((c.get("label") or "").strip()), "photo": has_photo, "drawing": has_drawing,
            "cta": True, "interstitial": True, "text": True}
    want = c.get("type") or "auto"
    if want in data and data[want]:
        return want
    head = tr_upper(" ".join(spec.headline)).strip()
    if want == "auto":
        if idx == n - 1 and n > 1:
            return "cta"
        if head.startswith("AMA ASIL") or head.startswith("ASIL "):
            return "interstitial"
        if data["counter"]:
            return "counter"
        if data["compare"]:
            return "compare"
    if has_photo:
        return "photo"
    if has_drawing:
        return "drawing"
    return "text"


# ---------------------------------------------------------------- terminal
class Terminal:
    """Koyu terminal: makas@bilgimakasi:~/konu, son iki kayıt satırı, sahne/sahne sayısı kadar kesilmiş çizgi."""
    REGION = (52, 1288, 620, 1536)

    def __init__(self, handle: str, topic_slug: str, logs: list[str], n: int):
        self.handle, self.logs, self.n = handle, logs, n
        x0, y0, x1, y1 = TERM
        self.fs = 26
        head = "makas" + handle
        rest = fit(f":~/{topic_slug}", "mono", self.fs, x1 - x0 - 48 - tw(head, "mono", self.fs))
        self.title = (head, rest)
        self._static: dict = {}
        self._dyn: dict = {}

    def static(self, i: int, dark: bool) -> Image.Image:
        key = (i, dark)
        if key not in self._static:
            x0, y0, x1, y1 = TERM
            pen = Pen(*self.REGION)
            pen.rr((x0 + 10, y0 + 10, x1 + 10, y1 + 10), 20, fill=YELLOW if dark else RED)
            pen.rr(TERM, 20, fill=INK, outline=INK, width=4)
            fs = self.fs
            a, b = self.title
            pen.text(x0 + 24, y0 + 42, "makas", "mono", fs, OFF)
            pen.text(x0 + 24 + tw("makas", "mono", fs), y0 + 42, self.handle, "mono", fs, YELLOW)
            pen.text(x0 + 24 + tw(a, "mono", fs), y0 + 42, b, "mono", fs, TERM_TXT)
            pen.rr((x0 + 4, y0 + 60, x1 - 4, y0 + 62), 0, fill=(52, 50, 49))
            if i > 0:
                ly = y0 + 100
                pen.svg(check_svg(YELLOW, 17), ICON_VB, x0 + 20, ly - 25, 30)
                pen.text(x0 + 24 + 32, ly, fit(self.logs[i - 1], "mono", fs, x1 - x0 - 80), "mono", fs, OFF)
            by = y1 - 38
            bx0, bx1 = x0 + 28, x1 - 142
            x = bx0
            while x < bx1:
                pen.rr((x, by - 2.5, min(x + 10, bx1), by + 2.5), 2.5, fill=TERM_DIM)
                x += 18
            self._static[key] = pen.done()
        return self._static[key]

    def layer(self, i: int, lt: float, dark: bool, hook: bool) -> Image.Image:
        line = self.logs[i]
        n_ch = len(line) if hook else int(clamp((lt - 0.08) / 0.022, 0, len(line)))
        cur_on = n_ch < len(line) or int(lt * 2.2) % 2 == 0
        a, b = i / self.n, (i + 1) / self.n
        frac = b if hook else lerp(a, b, ease_out_cubic(lt / 0.45))
        x0, y0, x1, y1 = TERM
        bx0, bx1 = x0 + 28, x1 - 142
        hx = round(lerp(bx0, bx1, frac))
        key = (i, n_ch, cur_on, hx, dark)
        if key in self._dyn:
            return self._dyn[key]
        img = self.static(i, dark).copy()
        pen = Pen(*self.REGION)
        fs = self.fs
        ly = y0 + (138 if i > 0 else 100)
        pen.text(x0 + 24, ly, "$", "mono", fs, RED)
        shown = fit(line, "mono", fs, x1 - x0 - 90)[:n_ch]
        pen.text(x0 + 24 + 32, ly, shown, "mono", fs, OFF)
        if cur_on:
            cx = x0 + 24 + 32 + tw(shown, "mono", fs) + (6 if shown else 0)
            pen.rr((cx, ly - 22, cx + 13, ly + 4), 2, fill=YELLOW)
        by = y1 - 38
        full = frac >= 0.999
        if hx > bx0 + 1:
            pen.rr((bx0, by - 5, hx, by + 5), 5, fill=YELLOW if full else RED)
        pen.text(x1 - 24, by + 9, f"{i + 1:02d}/{self.n:02d}", "mono", fs, YELLOW if full else OFF, anchor="rs")
        img.alpha_composite(pen.done())
        sc = scissors_icon(50, 26, blade=OFF, outline=None)
        _comp(img, sc, hx - 50 * 58 / 124 - self.REGION[0], by - sc.height / 2 - self.REGION[1])
        if len(self._dyn) > 120:
            self._dyn.clear()
        self._dyn[key] = img
        return img


# ---------------------------------------------------------------- maskot Makas ("göz")
MASCOT_VB = (-220, -300, 440, 480)
MOODS = {
    "normal": dict(blades=(-17, 17), L=1.00, look=(-0.40, -0.32), pupil=16, mouth="smile"),
    "surprised": dict(blades=(-30, 30), L=1.05, look=(0, -0.05), pupil=10, mouth="o", eye_scale=1.06, fx="shock"),
    "happy": dict(blades=(-25, 25), L=1.02, look=(0, 0), pupil=16, mouth="grin", lids="happy", blush=True,
                  fx="sparkle"),
    "thinking": dict(blades=(4, 28), L=1.00, look=(0.55, -0.62), pupil=15, mouth="hmm", fx="dots"),
}
_HEAD = dict(x=-98, y=-30, w=196, h=188, r=64, teeth=7, tooth_h=12)
_EYES = [(-60, 30, 1.0), (59, 25, 0.88)]   # bilerek simetrik değil: sağ göz biraz küçük ve yukarıda
_PIVOT = (0, -70)
_BLADE_L = 164
_OUT, _DIECUT, _SHADOW = 6, 9, (5, 5)


def _rot(px_, py_, th, x, y):
    c_, s_ = math.cos(th), math.sin(th)
    return (px_ + x * c_ - y * s_, py_ + x * s_ + y * c_)


def _arm(ring, theta_deg, L, inner):
    """Bir makas kolu (halkadan pime sap + ince bıçak) ve bıçak ucu."""
    px_, py_ = _PIVOT
    rx, ry, rs = ring
    ux, uy = px_ - rx, py_ - ry
    n = math.hypot(ux, uy)
    ux, uy = ux / n, uy / n
    nx, ny = -uy, ux
    ax, ay = rx + ux * (58 * rs - 8), ry + uy * (58 * rs - 8)
    shank = (f"M{P(ax + nx * 9, ay + ny * 9)} L{P(px_ + nx * 11, py_ + ny * 11)} "
             f"L{P(px_ - nx * 11, py_ - ny * 11)} L{P(ax - nx * 9, ay - ny * 9)} Z")
    th = math.radians(theta_deg)
    p1 = _rot(px_, py_, th, inner * 9, 10)
    tip = _rot(px_, py_, th, inner * 1.2, -L)
    ctrl = _rot(px_, py_, th, -inner * 21, -L * 0.42)
    p3 = _rot(px_, py_, th, -inner * 11, 10)
    blade = f"M{P(*p1)} L{P(*tip)} Q{P(*ctrl)} {P(*p3)} Z"
    s0 = _rot(px_, py_, th, -inner * 6, -L * 0.2)
    s1 = _rot(px_, py_, th, -inner * 5, -L * 0.5)
    return shank, blade, f"M{P(*s0)} L{P(*s1)}", tip, th


def _head_d():
    x0, y0 = _HEAD["x"], _HEAD["y"]
    x1, y1 = x0 + _HEAD["w"], y0 + _HEAD["h"]
    r, n, th = _HEAD["r"], _HEAD["teeth"], _HEAD["tooth_h"]
    yb = y1 - th
    d = f"M{P(x0, y0 + r)} A{r} {r} 0 0 1 {P(x0 + r, y0)} L{P(x1 - r, y0)} A{r} {r} 0 0 1 {P(x1, y0 + r)} L{P(x1, yb)} "
    w_ = (x1 - x0) / n
    for i in range(n):
        xa = x1 - i * w_
        d += f"L{P(xa - w_ / 2, y1)} L{P(xa - w_, yb)} "
    return d + "Z"


def mascot_svg(mood: str = "normal", mouth: str = "rest", blink: bool = False) -> str:
    """Makas: dik duran marka makası. Kırmızı halkalar gözler, ince siyah bıçaklar konuşurken açılıp kapanan
    antenler, yüz zikzak kenarlı sarı bir kâğıt parçası. Düz çıkartma: mürekkep hat, beyaz kesim kenarı, sert gölge.
    Minion'a benzememesi için gözler farklı boyda, gövde hafif eğik ve uzun bıçağın ucunda bir perçem kıvrımı var."""
    E = dict(MOODS["normal"])
    E.update(MOODS.get(mood, {}))
    ink, yel, red, white = _hex(INK), _hex(YELLOW), _hex(RED), _hex(WHITE)
    db = {"open": 9, "closed": -8}.get(mouth, 0)
    thL, thR = E["blades"][0] - db, E["blades"][1] + db
    L = _BLADE_L * E["L"]
    lx, ly = E["look"]
    es = E.get("eye_scale", 1.0)
    armA = _arm(_EYES[0], thR, L, -1)
    armB = _arm(_EYES[1], thL, L * 0.9, +1)
    # perçem: uzun bıçağın ucunda küçük kıvrım
    tx, ty = armA[3]
    th = armA[4]
    c1 = _rot(tx, ty, th, 16, -8)
    c2 = _rot(tx, ty, th, 22, 8)
    c3 = _rot(tx, ty, th, 12, 12)
    curl = f"M{P(tx, ty)} C{P(*c1)} {P(*c2)} {P(*c3)}"
    head = f'<path d="{_head_d()}"'

    def silhouette(col, extra):
        sw = _OUT + extra
        st = f'fill="{col}" stroke="{col}" stroke-width="{sw}" stroke-linejoin="round"'
        g = f"{head} {st}/>"
        for arm in (armA, armB):
            g += f'<path d="{arm[0]}" {st}/><path d="{arm[1]}" {st}/>'
        g += f'<path d="{curl}" fill="none" stroke="{col}" stroke-width="{5 + extra}" stroke-linecap="round"/>'
        for ex, ey, rs in _EYES:
            g += f'<circle cx="{ex}" cy="{ey}" r="{58 * rs * es}" {st}/>'
        g += f'<circle cx="{_PIVOT[0]}" cy="{_PIVOT[1]}" r="13" {st}/>'
        return g

    out = '<g transform="rotate(-4 0 60)">'
    out += f'<g transform="translate({_SHADOW[0]} {_SHADOW[1]})">{silhouette(ink, 2 * _DIECUT)}</g>'
    out += silhouette(white, 2 * _DIECUT)
    out += f'{head} fill="{yel}" stroke="{ink}" stroke-width="{_OUT}" stroke-linejoin="round"/>'
    if E.get("blush") or mouth == "open":
        for sx in (-1, 1):
            out += f'<ellipse cx="{sx * 68}" cy="110" rx="15" ry="8" fill="{red}" opacity="0.45"/>'
    st = f'fill="{ink}" stroke="{ink}" stroke-width="{_OUT - 1}" stroke-linejoin="round"'
    for arm in (armA, armB):
        out += f'<path d="{arm[0]}" {st}/><path d="{arm[1]}" {st}/>'
        out += f'<path d="{arm[2]}" stroke="{white}" stroke-width="3" stroke-linecap="round" opacity="0.5" fill="none"/>'
    out += f'<path d="{curl}" fill="none" stroke="{ink}" stroke-width="5" stroke-linecap="round"/>'
    defs = "<defs>"
    for i, (ex, ey, rs) in enumerate(_EYES):
        defs += f'<clipPath id="sc{i}"><circle cx="{ex}" cy="{ey}" r="{43 * rs}"/></clipPath>'
    out += defs + "</defs>"
    lids = "closed" if (blink and E.get("lids") != "happy") else E.get("lids")
    for i, (ex, ey, rs) in enumerate(_EYES):
        R, Sr = 58 * rs, 43 * rs
        g = f'<g transform="translate({ex} {ey}) scale({es}) translate({-ex} {-ey})">'
        g += f'<circle cx="{ex}" cy="{ey}" r="{R}" fill="{red}" stroke="{ink}" stroke-width="{_OUT}"/>'
        a0, a1 = math.radians(200), math.radians(245)
        rm = (R + Sr) / 2
        g += (f'<path d="M{P(ex + rm * math.cos(a0), ey + rm * math.sin(a0))} A{rm} {rm} 0 0 1 '
              f'{P(ex + rm * math.cos(a1), ey + rm * math.sin(a1))}" stroke="{white}" stroke-width="5" '
              'stroke-linecap="round" fill="none" opacity="0.7"/>')
        g += f'<circle cx="{ex}" cy="{ey}" r="{Sr}" fill="{white}" stroke="{ink}" stroke-width="{_OUT}"/>'
        pr = E["pupil"] * (0.92 if i else 1.0)
        travel = Sr - pr - 7
        pxx, pyy = ex + lx * travel, ey + ly * travel
        inner = f'<circle cx="{pxx:.2f}" cy="{pyy:.2f}" r="{pr}" fill="{ink}"/>'
        inner += (f'<circle cx="{pxx - pr * 0.36:.2f}" cy="{pyy - pr * 0.40:.2f}" r="{max(3.5, pr * 0.30):.2f}" '
                  f'fill="{white}"/>')
        if lids == "closed":
            inner = (f'<rect x="{ex - 50}" y="{ey - 50}" width="100" height="100" fill="{yel}"/>'
                     f'<path d="M{P(ex - 25 * rs, ey + 2)} Q{P(ex, ey + 20 * rs)} {P(ex + 25 * rs, ey + 2)}" '
                     f'stroke="{ink}" stroke-width="7" fill="none" stroke-linecap="round"/>')
        elif lids == "happy":
            inner = (f'<rect x="{ex - 50}" y="{ey - 50}" width="100" height="100" fill="{yel}"/>'
                     f'<path d="M{P(ex - 22 * rs, ey + 11)} Q{P(ex, ey - 24 * rs)} {P(ex + 22 * rs, ey + 11)}" '
                     f'stroke="{ink}" stroke-width="8" fill="none" stroke-linecap="round"/>')
        g += f'<g clip-path="url(#sc{i})">{inner}</g>'
        g += f'<circle cx="{ex}" cy="{ey}" r="{Sr}" fill="none" stroke="{ink}" stroke-width="{_OUT}"/></g>'
        out += g
    out += f'<circle cx="{_PIVOT[0]}" cy="{_PIVOT[1]}" r="12" fill="{yel}" stroke="{ink}" stroke-width="5"/>'
    out += f'<circle cx="{_PIVOT[0] - 4}" cy="{_PIVOT[1] - 4}" r="3.2" fill="{white}"/>'
    mx, my = 4, 113
    m = {"open": "open", "closed": "closed"}.get(mouth, E["mouth"])
    ms = f'stroke="{ink}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"'
    if m == "smile":
        out += f'<path d="M{P(mx - 23, my - 7)} Q{P(mx + 2, my + 14)} {P(mx + 23, my - 9)}" {ms} fill="none"/>'
    elif m == "closed":
        out += f'<path d="M{P(mx - 17, my - 3)} Q{P(mx, my + 7)} {P(mx + 17, my - 4)}" {ms} fill="none"/>'
    elif m in ("open", "grin"):
        w2, hg = (24, 30) if m == "open" else (33, 32)
        d = (f"M{P(mx - w2, my - 10)} L{P(mx + w2, my - 10)} Q{P(mx + w2, my - 10 + hg * 1.25)} {P(mx, my - 10 + hg)} "
             f"Q{P(mx - w2, my - 10 + hg * 1.25)} {P(mx - w2, my - 10)} Z")
        out += (f'<defs><clipPath id="mclip"><path d="{d}"/></clipPath></defs><path d="{d}" fill="{ink}" {ms}/>'
                f'<g clip-path="url(#mclip)"><ellipse cx="{mx}" cy="{my - 10 + hg}" rx="{w2 * 0.62:.1f}" '
                f'ry="{hg * 0.42:.1f}" fill="{red}"/></g>')
    elif m == "o":
        out += f'<ellipse cx="{mx}" cy="{my + 2}" rx="14" ry="17" fill="{ink}" {ms}/>'
    elif m == "hmm":
        out += f'<path d="M{P(mx - 6, my + 2)} q9 -9 16 0 t16 -2" {ms} fill="none"/>'
    fx = E.get("fx")
    fs = f'stroke="{ink}" stroke-width="7" stroke-linecap="round" fill="none"'
    if fx == "shock":
        for sx in (-1, 1):
            for a, r0, r1 in ((-160, 132, 160), (-128, 140, 168), (-196, 128, 154)):
                aa = math.radians(a if sx < 0 else -180 - a)
                out += (f'<path d="M{P(r0 * math.cos(aa), 10 + r0 * math.sin(aa))} '
                        f'L{P(r1 * math.cos(aa), 10 + r1 * math.sin(aa))}" {fs}/>')
    elif fx == "dots":
        for dx, dy, r in ((112, -96, 8), (128, -132, 12), (142, -178, 17)):
            out += f'<circle cx="{dx}" cy="{dy}" r="{r}" fill="{white}" stroke="{ink}" stroke-width="5"/>'
    elif fx == "sparkle":
        for sx_, sy_, r in ((-150, -150, 20), (146, -118, 15), (-138, -38, 11)):
            d = (f"M{P(sx_, sy_ - r)} Q{P(sx_, sy_)} {P(sx_ + r, sy_)} Q{P(sx_, sy_)} {P(sx_, sy_ + r)} "
                 f"Q{P(sx_, sy_)} {P(sx_ - r, sy_)} Q{P(sx_, sy_)} {P(sx_, sy_ - r)} Z")
            out += f'<path d="{d}" fill="{yel}" stroke="{ink}" stroke-width="4" stroke-linejoin="round"/>'
    return out + "</g>"


class Mascot:
    """İfade/ağız/göz kırpma başına bir kez çizilen Makas görüntüleri."""

    def __init__(self, scale: float = MASCOT_SCALE):
        self.scale = scale
        self._c: dict = {}

    def sprite(self, mood: str, mouth: str, blink: bool) -> tuple[Image.Image, tuple[int, int]]:
        key = (mood, mouth, blink)
        if key not in self._c:
            vb = MASCOT_VB
            k = self.scale * SS
            im = svg_img(mascot_svg(mood, mouth, blink), vb, vb[2] * k, vb[3] * k)
            im = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
            off = (int(round(MASCOT_XY[0] + vb[0] * self.scale)), int(round(MASCOT_XY[1] + vb[1] * self.scale)))
            self._c[key] = (im, off)
        return self._c[key]


# ---------------------------------------------------------------- video
STRUCT_RIGHT = {"efsane": "EFSANE Mİ?", "neden": "NEDEN?"}


def short_name(topic: str, max_w: float) -> str:
    """Başlıktaki kısa konu adı: konunun sığan ilk kelimeleri (kelime ortasından kesmeden)."""
    words = tr_lower(re.sub(r"[\"“”'’?!.,:;]", "", topic or "")).split()
    out = ""
    for w in words:
        nxt = (out + " " + w).strip()
        if tw(nxt, "mono", 28) > max_w and out:
            break
        out = nxt
    return fit(out, "mono", 28, max_w) if out else "bilgi"


def pill_width(text: str) -> float:
    return tw(fit(text, "mono", 26, 520), "mono", 26) + 34


class KartScene:
    def __init__(self, video: "KartVideo", i: int):
        v = video
        self.i = i
        s = v.scenes[i]
        self.spec = s
        self.dur = max(0.1, s.end - s.start)
        self.type = v.types[i]
        self.dark = self.type == "interstitial"
        ctx = {"spec": s, "idx": i, "dur": self.dur, "slug": v.slug, "handle": v.handle}
        self.card = CARD_CLASSES[self.type](ctx)
        if i == 0:
            kind, right = "pill", (s.kicker.strip() or v.right_label(i))
        elif v.structure == "sayac":
            kind, right = "count", v.right_label(i)
        else:
            kind, right = "text", v.right_label(i)
        self.header = header_layer(i + 1, v.short, tr_upper(right) if kind != "count" else right, kind, self.dark)
        bg = red_bg() if self.dark else paper_bg()
        self.base = bg.copy()
        self.base.alpha_composite(self.header, HEADER_REGION[:2])
        if not (i == 0 and v.intro):
            self.base.alpha_composite(rule_layer(self.dark), (0, RULE_Y - 6))
        self.mascot_override = (s.card or {}).get("mascot", "auto")

    def mood(self, lt: float) -> str:
        if self.mascot_override in MOODS:
            return self.mascot_override
        return self.card.mood(lt, self.dur)


class KartVideo:
    def __init__(self, scenes, words: list[Word], meta: dict, bcfg: dict):
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        self.n = n = len(scenes)
        on = bcfg.get("enabled", False)
        self.intro = bool(on and bcfg.get("intro_cut", True))
        every = int(bcfg.get("cut_transition_every", 4) or 0) if on else 0
        self.cut_at = {i for i in range(1, n) if every and i % every == 0}
        self.handle = bcfg.get("handle") or "@bilgimakasi"
        self.structure = self.meta.get("structure", "")
        # kısa konu adı ilk sahnenin başlığına (seri etiketi rozetinin yanına) sığmalı
        kicker = (scenes[0].kicker or "").strip() if scenes else ""
        right_w = pill_width(tr_upper(kicker)) if kicker else 300
        name_w = 920 - right_w - 40 - 12 - 24 - (72 + tw("// 01 — ", "mono", 28))
        self.short = short_name(self.meta.get("short") or self.meta.get("topic") or "", name_w)
        self.slug = ""
        for part in slug(self.short, 60).split("-"):
            if len(self.slug) + len(part) + 1 > 15 and self.slug:
                break
            self.slug = (self.slug + "-" + part).strip("-")
        self.slug = self.slug or "bilgi"
        self.types = [card_type(s, i, n) for i, s in enumerate(scenes)]
        # kelime aralıkları (sahne sınırları korunur)
        ranges, a = [], 0
        for i, s in enumerate(scenes):
            b = min(len(words), a + len(s.words)) if i < n - 1 else len(words)
            ranges.append((a, b))
            a = b
        self.ranges = ranges
        self.kin = Kinetic(words, ranges)
        self.starts = [w.start for w in words]
        self.logs = [self._log(i) for i in range(n)]
        self.term = Terminal(self.handle, self.slug, self.logs, n)
        self.mascot = Mascot()
        self._sc: dict[int, KartScene] = {}
        self.scene_starts = [s.start for s in scenes]

    def right_label(self, i: int) -> str:
        if self.structure == "sayac":
            k = round(3 * i / max(1, self.n - 1))
            return f"{tr_upper('bilgi')} {k}/3"
        if self.structure in STRUCT_RIGHT:
            return STRUCT_RIGHT[self.structure]
        return (self.scenes[0].kicker or "").strip() or "BİLGİ MAKASI"

    def _log(self, i: int) -> str:
        s = self.scenes[i]
        c = s.card or {}
        if c.get("log"):
            return str(c["log"])
        t = self.types[i]
        if i == 0:
            return f"makas kes {self.slug}"
        if t == "counter":
            return tr_lower(f"{c.get('value', '')} {c.get('label', '')}".strip())
        if t == "compare":
            return "efsane kesildi"
        if t == "quote" and (c.get("note") or "").strip():
            return "alıntı: " + tr_lower(c["note"].split("·")[0].strip())
        if t == "interstitial":
            return "dur bir saniye…"
        if t == "cta":
            return "yorumlar açık"
        return tr_lower(" ".join(x.strip() for x in s.headline if x.strip())) or "kesiliyor"

    def scene(self, i: int) -> KartScene:
        sc = self._sc.get(i)
        if sc is None:
            sc = self._sc[i] = KartScene(self, i)
            for k in [k for k in self._sc if k < i - 1 or k > i + 1]:
                del self._sc[k]
        return sc

    def scene_at(self, t: float) -> int:
        return max(0, bisect.bisect_right(self.scene_starts, t) - 1)

    # ------------------------------------------------------------ katmanlar
    def _words(self, img: Image.Image, t: float, si: int, dark: bool) -> None:
        if not self.words:
            return
        a, b = self.ranges[si]
        cur = bisect.bisect_right(self.starts, t + 0.03) - 1
        if a < b and cur < a:
            cur = a  # sahne değişti ama ilk kelime birkaç kare sonra: yeni parçayı ilk kelimesi seçili göster
        cur = max(0, cur)
        if t > self.words[-1].end + 0.35:
            ci, hi = len(self.kin.chunks) - 1, len(self.words)
        else:
            ci, hi = self.kin.chunk_of.get(cur, 0), cur
        rest, cur_im, cur_c = self.kin.layer(ci, hi, dark)
        rx0, ry0 = Kinetic.REGION[:2]
        put(img, rest, rx0, ry0)
        if cur_im is not None:
            w = self.words[hi]
            k = 1.0
            x = (t - w.start) / 0.12
            if 0 <= x < 1:
                k = 1 + 0.12 * (1 - x) ** 2
            put(img, cur_im, cur_c[0] - cur_im.width / 2, cur_c[1] - cur_im.height / 2, k=k)

    def _talk(self, t: float) -> str:
        if not self.words:
            return "rest"
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0:
            return "rest"
        w = self.words[i]
        if t >= w.end:
            return "rest"
        letters = sum(ch.isalnum() for ch in w.text)
        n = max(1, round(letters / 2.6))
        ph = (t - w.start) / max(0.05, w.end - w.start) * n
        return "open" if (ph % 1.0) < 0.55 else "closed"

    def _mascot(self, img: Image.Image, t: float, sc: KartScene, lt: float) -> None:
        mood = sc.mood(lt)
        mouth = self._talk(t)
        blink = (t % 3.6) > 3.45 and mood not in ("happy", "surprised")
        im, (x, y) = self.mascot.sprite(mood, mouth, blink)
        bob = round(3 * math.sin(t * 2 * math.pi * 0.55))
        put(img, im, x, y + bob)

    def _wipe_mask(self, lt: float) -> Image.Image:
        """Kırmızı yukarıdan iner; ön kenarı küçülen yarım ton noktalara dağılır. Kenar görünür bantta (y 232→1540)
        hareket eder, bitince ekran düz kırmızıdır (terminal ve maskotun arkasında yarım ton kalmaz)."""
        band, sp = 300, 34
        p = ease_in_out(lt / WIPE)
        e = lerp(232, SAFE[3] + band, p)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rectangle([0, 0, W, int(e)], fill=255)
        bh = int(min(band, H - e)) + sp
        if bh > 0:
            dots = Image.new("L", (W * SS, bh * SS), 0)
            d = ImageDraw.Draw(dots)
            rmax, row, y = sp * 0.74, 0, 0.0
            while y < band:
                r = rmax * (1 - clamp(y / band)) ** 1.15
                if r > 0.6:
                    x = -sp + (sp / 2 if row % 2 else 0)
                    while x < W + sp:
                        d.ellipse([(x - r) * SS, (y - r + sp / 2) * SS, (x + r) * SS, (y + r + sp / 2) * SS], fill=255)
                        x += sp
                y += sp * 0.5
                row += 1
            dots = dots.resize((W, bh), Image.LANCZOS)
            mask.paste(ImageChops.lighter(mask.crop((0, int(e) - sp // 2, W, int(e) - sp // 2 + bh)), dots),
                       (0, int(e) - sp // 2))
        return mask

    def _cut(self, img: Image.Image, old: Image.Image, local: float, seed: int, length: float = 0.4) -> None:
        """Eski kart makasla ikiye kesilir, parçalar ayrılıp kaybolur; altta yeni kart durur."""
        p = clamp(local / length)
        rx0, ry0 = CARD_REGION[:2]
        lw, lh = old.size
        ang = math.radians(6 if seed % 2 else -6)
        cy = (CARD[1] + CARD[3]) / 2 - ry0
        yl, yr = cy - math.tan(ang) * lw / 2, cy + math.tan(ang) * lw / 2
        sx = lerp(CARD[0] - rx0 - 40, SAFE_X - 66 - rx0, ease_in_out(p / 0.5))
        d = 90 * clamp((p - 0.4) / 0.6) ** 1.5
        a = 1 - ease_in_out((p - 0.5) / 0.28)  # hayalet üst üste binme ≤ 3 kare
        mask = Image.new("L", old.size, 0)
        ImageDraw.Draw(mask).polygon([(0, 0), (lw, 0), (lw, yr), (0, yl)], fill=255)
        top = Image.new("RGBA", old.size, (0, 0, 0, 0))
        top.paste(old, (0, 0), mask)
        bot = Image.new("RGBA", old.size, (0, 0, 0, 0))
        bot.paste(old, (0, 0), ImageChops.invert(mask))
        # üst parça sola kayar (yukarı kalkması kinetik yazının altına girerdi), alt parça yerinde birkaç px düşer
        put(img, bot, rx0, ry0 + min(d, 5), alpha=a, clip=(0, SAFE[1], SAFE[2], CLIP_FLOOR))
        put(img, top, rx0 - d * 1.4, ry0 - min(d * 0.15, 12), alpha=a, clip=(0, SAFE[1], SAFE[2], CLIP_FLOOR))
        if p < 0.6:
            dd = ImageDraw.Draw(img)
            x = CARD[0] - 30
            while x < sx + rx0:
                xe = min(x + 22, sx + rx0)
                ya = ry0 + yl + (yr - yl) * ((x - rx0) / lw)
                yb = ry0 + yl + (yr - yl) * ((xe - rx0) / lw)
                dd.line([(x, ya), (xe, yb)], fill=INK, width=4)
                x += 34
            sc = scissors_icon(110, 34 if int(local * 30) % 2 else 14, rot=-math.degrees(ang))
            yy = ry0 + yl + (yr - yl) * (sx / lw)
            put(img, sc, rx0 + sx - sc.width * 0.45, yy - sc.height / 2)

    def _intro(self, img: Image.Image, t: float, dark: bool, dur: float = 0.8) -> None:
        """Açılış: makas başlığın altındaki kesik çizgiyi soldan sağa keser (t=0'da sol başta durur)."""
        p = clamp(t / dur)
        x = lerp(72, SAFE_X - 40, ease_in_out(p))
        rule = rule_layer(dark)
        if x > 72:
            put(img, rule.crop((0, 0, int(x), rule.height)), 0, RULE_Y - 6)
        if p < 1:
            sc = scissors_icon(64, 32 if int(t * 24) % 2 else 12)
            put(img, sc, x - 64 * 58 / 124, RULE_Y - sc.height / 2)

    # ------------------------------------------------------------ kare
    def frame(self, t: float, grain: bool = True, debug_layers: bool = False) -> Image.Image:
        si = self.scene_at(t)
        sc = self.scene(si)
        s = sc.spec
        lt = t - s.start
        if debug_layers:  # yalnız içerik katmanları (güvenli alan denetimi için)
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            img.alpha_composite(sc.header, HEADER_REGION[:2])
        elif sc.dark and si > 0 and lt < WIPE:
            img = paper_bg().copy()  # kırmızı, önceki kartın üstünden aşağı doğru iner
            prev = self.scene(si - 1)
            if not prev.dark:
                put(img, prev.card.layer(prev.dur, prev.dur), *CARD_REGION[:2], clip=(0, SAFE[1], SAFE[2], CLIP_FLOOR))
            img.paste(red_bg(), (0, 0), self._wipe_mask(lt))
            img.alpha_composite(sc.header, HEADER_REGION[:2])
            img.alpha_composite(rule_layer(True), (0, RULE_Y - 6))
        else:
            img = sc.base.copy()
        if si == 0 and self.intro:
            self._intro(img, t, sc.dark)
        # kart
        layer = sc.card.layer(lt, sc.dur)
        rx0, ry0 = CARD_REGION[:2]
        clip = (0, SAFE[1], SAFE[2], CLIP_FLOOR)
        if isinstance(sc.card, InterstitialCard):
            k = sc.card.scale(lt)
            if k is not None:  # alt kenar sabit kalır: büyüyen kart maskotun bıçaklarına inmez
                put(img, layer, rx0, ry0, k=k, clip=clip,
                    anchor=(0.5, (CARD_FLOOR - 4 - ry0) / layer.height))
        elif si == 0:  # kanca: kart ilk karede tam; ilk yarım saniyede küçük bir zıplama
            k = 1 + 0.022 * math.sin(math.pi * clamp(lt / 0.5)) if lt < 0.5 else 1.0
            put(img, layer, rx0, ry0, k=k, clip=clip)
        elif si in self.cut_at and lt < 0.4 and self.types[si - 1] != "interstitial":
            put(img, layer, rx0, ry0, clip=clip)
            prev = self.scene(si - 1)
            self._cut(img, prev.card.layer(prev.dur, prev.dur), lt, si)
        else:
            x = lt / 0.22  # yeni kart küçükten oturur (büyütmek gölgeyi x > 935'e taşırdı)
            k = 1.0 if x >= 1 else 0.94 + 0.06 * ease_out_back(x, 1.4)
            put(img, layer, rx0, ry0, k=k, clip=clip)
        self._words(img, t, si, sc.dark)
        put(img, self.term.layer(si, lt, sc.dark, si == 0), *Terminal.REGION[:2])
        self._mascot(img, t, sc, lt)
        if debug_layers:
            return img
        return finish(img) if grain else img.convert("RGB")


# ---------------------------------------------------------------- ana döngü
def render_kart(scenes: list[render.SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
                music: Path | None, meta: dict) -> Path:
    """Kart şablonuyla videoyu kurar: kareleri render.render gibi ffmpeg'e yazar, render.mux ile sesi ekler,
    brand.json'daki end_tail_seconds / outro_seconds ayarlarına uyar."""
    from .brand import Brand, load_config
    t_begin = time.perf_counter()
    bcfg = load_config()
    brand = Brand(bcfg, {})
    outro = bcfg.get("outro_seconds", 0.0) if brand.on else 0.0
    tail = bcfg.get("end_tail_seconds", 1.6)
    content_end = (words[-1].end if words else scenes[-1].end) + (0.7 if outro else tail)
    total = content_end + outro
    scenes[-1].end = content_end
    video = KartVideo(scenes, words, meta, bcfg)
    silent = out_mp4.with_suffix(".silent.mp4")
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "8M", "-bufsize", "16M",
        "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    n = int(total * FPS)
    for fi in range(n):
        t = fi / FPS
        if t >= content_end:
            img = brand.outro(t - content_end, outro).convert("RGB")
        else:
            img = video.frame(t)
        ff.stdin.write(img.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg video kodlaması başarısız")
    render.mux(silent, voice_mp3, music, out_mp4, total)
    silent.unlink(missing_ok=True)
    el = time.perf_counter() - t_begin
    print(f"Kart: {n} kare, {el:.1f} sn ({el / max(1, n) * 1000:.0f} ms/kare)")
    return out_mp4
