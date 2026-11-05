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
from .script import STRUCTURES, tutar
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
# kapak sahnesi (sahne 0): kart biraz aşağıda başlar, kinetik bant o kadar uzar. Kapak cümlesi (6 kelimeye kadar, iki
# satır) böylece ~76 px'in üstünde okunur; kartın, seri etiketinin ve açılış zıplamasının üstünde kalır.
CARD0 = (100, 540, 908, 1120)
KIN0 = (72, 238, 920, 500)
CARD_SH = 12
CARD_REGION = (68, 440, 926, 1140)         # kart katmanının kapladığı alan (gölge, bant, çip taşmaları dahil)
CARD_FLOOR = 1138                          # kart bunun altına inmez: maskotun bıçak uçları ~1150'den başlar
CLIP_FLOOR = CARD_FLOOR                    # kart katmanlarının kırpıldığı alt sınır (CARD_FLOOR yerleşim içindir)
TERM = (60, 1296, 600, 1516)
MASCOT_XY, MASCOT_SCALE = (774, 1370), 0.86
WIPE = 0.42                                # ara kanca kırmızı silme süresi (sn)
WIPE_Y0, WIPE_Y1 = 232, SAFE[3]            # silmenin düz kırmızı kenarı başlık çizgisinden güvenli bandın altına iner
CUT_EVERY = 3                              # makas kesme geçişi her kaç sahnede bir (brand.json kart_kesme_her)
CUT_SLICE, CUT_SPLIT, CUT_FADE = 0.2, 0.15, 2 / FPS   # kesme: makas geçer, parçalar ayrılır, ≤ 2 karede söner
CUT_LEN = CUT_SLICE + CUT_SPLIT + CUT_FADE

FONTS = {"anton": "Anton-Regular.ttf", "archivo": "ArchivoBlack-Regular.ttf", "mono": "DMMono-Medium.ttf",
         "oswald": "Oswald-Bold.ttf", "courier": "CourierPrime-Bold.ttf", "plex": "IBMPlexMono-SemiBold.ttf"}
CARD_TYPES = ("photo", "drawing", "counter", "compare", "quote", "interstitial", "cta", "receipt", "text")
TL = "₺"
# ₺ işareti olmayan yazı yüzleri: işaret yedek yüzle çizilir (DM Mono / Courier yerine aynı genişlikte IBM Plex Mono)
TL_YEDEK = {"mono": "plex", "courier": "plex", "archivo": "oswald"}


# ---------------------------------------------------------------- küçük yardımcılar
_fonts: dict = {}


def fnt(name: str, px: float) -> ImageFont.FreeTypeFont:
    key = (name, max(1, int(round(px))))
    f = _fonts.get(key)
    if f is None:
        f = _fonts[key] = ImageFont.truetype(str(FONT_DIR / FONTS.get(name, name)), key[1])
    return f


def runs(s: str, font: str) -> list[tuple[str, str]]:
    """Yazıyı (parça, yüz) dizisine böler: ₺ işareti olmayan yüzde işaret TL_YEDEK yüzüyle çizilir."""
    alt = TL_YEDEK.get(font)
    if not alt or TL not in s:
        return [(s, font)]
    out = []
    for i, part in enumerate(s.split(TL)):
        if i:
            out.append((TL, alt))
        if part:
            out.append((part, font))
    return out


def draw_text(d: ImageDraw.ImageDraw, xy, s: str, font: str, px: float, fill, anchor: str = "ls") -> None:
    """ImageDraw.text (px: çizim pikseli boyutu); ₺ işareti olmayan yüzde işaret yedek yüzle çizilir: yatay hiza
    korunur, parçalar aynı dikey hizaya (çoğunlukla taban çizgisi) oturur."""
    rs = runs(s, font)
    if len(rs) == 1 and rs[0][1] == font:
        d.text(xy, s, font=fnt(font, px), fill=fill, anchor=anchor)
        return
    total = sum(fnt(f, px).getlength(p) for p, f in rs)
    x, y = xy
    x -= {"m": total / 2, "r": total}.get(anchor[0], 0.0)
    va = anchor[1] if len(anchor) > 1 else "s"
    for p, f in rs:
        d.text((x, y), p, font=fnt(f, px), fill=fill, anchor="l" + va)
        x += fnt(f, px).getlength(p)


def tw(s: str, font: str, size: float) -> float:
    """Yazının tasarım pikseli cinsinden genişliği."""
    if TL in s and font in TL_YEDEK:
        return sum(fnt(f, size * SS).getlength(p) for p, f in runs(s, font)) / SS
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


def fit_words(s: str, font: str, size: float, max_w: float) -> str:
    """fit gibi, ama kelime sınırında keser ('21.196 kilometre…'); kısa çizgi ve eğik çizgi de sınırdır
    ('makas kes japon…'). İlk kelime bile sığmazsa harf harf kısaltır."""
    if tw(s, font, size) <= max_w:
        return s
    cuts = [m.start() for m in re.finditer(r"(?<=\S)[\s/-]", s)]
    for c in reversed(cuts):
        cand = s[:c].rstrip(" ·-—,:;/") + "…"
        if tw(cand, font, size) <= max_w:
            return cand
    return fit(s, font, size, max_w)


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


def wipe_edge(lt: float) -> float:
    """Ara kanca silmesinin düz kırmızı kenarı (y): başlık çizgisinden güvenli bandın altına (1540) iner."""
    return lerp(WIPE_Y0, WIPE_Y1, ease_in_out(lt / WIPE))


def wipe_time(y: float) -> float:
    """Silme kenarının y'ye ulaştığı an (sn)."""
    lo, hi = 0.0, WIPE
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if wipe_edge(mid) < y else (lo, mid)
    return hi


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
        draw_text(self.d, self.p(x, y), s, font, size * self.s, fill, anchor)

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
        draw_text(self.d, self.p(*xy), s, font, size * SS, fill, anchor)

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


HEADER_SIZE = 32
HEADER_ICON = 44


def header_layer(no: int, name: str, right: str, kind: str, dark: bool) -> Image.Image:
    """'// 03 — konu' solda; sağda makas simgesi + yapıya uygun ilerleme etiketi. Seri etiketi ilk sahnede kartın
    üstünde büyük bir yırtık etikettir (cover_layer)."""
    pen = Pen(*HEADER_REGION)
    ink, acc = (OFF, YELLOW) if dark else (INK, RED)
    size, y, x1 = HEADER_SIZE, HEADER_Y, 920
    # sağ taraf
    if kind == "count":                       # "BİLGİ 2/3"
        a, b = right.rsplit(" ", 1)
        wb = tw(b, "mono", size)
        pen.text(x1, y, b, "mono", size, acc, anchor="rs")
        pen.text(x1 - wb - tw(" ", "mono", size), y, a, "mono", size, ink, anchor="rs")
        rx = x1 - wb - tw(" " + a, "mono", size)
    else:
        lab = fit(right, "mono", size, 440)
        pen.text(x1, y, lab, "mono", size, ink, anchor="rs")
        rx = x1 - tw(lab, "mono", size)
    iw = HEADER_ICON
    pen.svg(scissors_svg(28, ring=YELLOW if dark else RED, blade=ink, pivot=RED if dark else YELLOW,
                         outline=None if dark else INK), SCISSORS_VB, rx - iw - 12, y - 27, iw)
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


# Kendinden önceki kelimeye yaslanan ekler/edatlar: parça bunlardan hemen önce bitmez ("UZUNLUK | DEĞİL" olmaz).
CLITICS = {"değil", "değildi", "değildir", "değiller", "mi", "mı", "mu", "mü", "midir", "mıdır", "mudur", "müdür",
           "miydi", "mıydı", "muydu", "müydü", "misin", "mısın", "musun", "müsün", "gibi", "kadar", "ile", "da", "de",
           "bile", "ki"}
# Sonrakini niteleyen kelimeler: parça bunlarla bitmesin ("ÇIPLAK | GÖZLE" gibi kopukluklar için hafif ceza).
MODIFIERS = {"bir", "bu", "şu", "o", "tek", "çok", "en", "daha", "her", "hiç", "ilk", "son", "tam", "yalnızca",
             "sadece", "birkaç", "bazı", "hangi", "asıl", "çıplak", "kaç", "hem", "ne"}
_PUNCT_END = ".?!,;:…"


def _bare(s: str) -> str:
    return tr_lower(s.strip().strip('"“”«»()[]').rstrip(".,;:!?…—-"))


def _split_clause(toks: list[str]) -> list[int]:
    """Bir yan cümleyi (noktalama içermeyen kelime dizisi) dengeli parçalara böler; parça boyları döner.
    Parça sayısı ceil(n/4) (uzun kelimelerde biraz fazla); boylar dengeli (6 -> 3+3, 5 -> 3+2), parça bir edattan
    hemen önce ya da niteleyen bir kelimeyle bitmez, tek kelimelik parça (yan cümle tek kelime değilse) olmaz."""
    n = len(toks)
    bare = [_bare(t) for t in toks]
    chars = sum(len(t) for t in bare) + n - 1
    k = min(n, max(math.ceil(n / 4), math.ceil(chars / 28)))
    if k <= 1:
        return [n]
    mean = n / k

    def part_cost(pos, sz):
        end = pos + sz
        cost = (sz - mean) ** 2 + (8 if sz == 1 else 0)
        cost += max(0, sum(len(t) for t in bare[pos:end]) + sz - 1 - 24) * 0.3
        if end < n:
            if bare[end] in CLITICS:
                cost += 100
            if bare[end - 1] in MODIFIERS or bare[end - 1].isdigit():
                cost += 3
            if len(bare[end]) > 3 and bare[end].endswith(("sı", "si", "su", "sü", "ları", "leri")):
                cost += 4     # tamlamanın ikinci kelimesi ("insan | yapısı") başa düşmesin
        return cost

    memo: dict = {}

    def best(pos, parts):     # (maliyet, boylar): words[pos:] tam 'parts' parçaya; eşitlikte büyük ilk parça (3+2)
        if (pos, parts) in memo:
            return memo[(pos, parts)]
        left = n - pos
        if parts == 1:
            r = (part_cost(pos, left), [left]) if 1 <= left <= 4 else (float("inf"), [])
        else:
            r = (float("inf"), [])
            for sz in range(min(4, left - parts + 1), 0, -1):
                c, rest = best(pos + sz, parts - 1)
                c += part_cost(pos, sz)
                if c < r[0] - 1e-9:
                    r = (c, [sz] + rest)
        memo[(pos, parts)] = r
        return r

    cost, sizes = best(0, k)
    return sizes if sizes else [n]


def kart_phrases(words: list[Word], whole_first: int = 0) -> list[list[int]]:
    """Kart şablonunun kinetik parçaları (sahne içi kelime indeksleri). Önce noktalamada bölünür, sonra her yan
    cümle _split_clause ile. whole_first > 0 ise ilk cümle en fazla bu kadar kelimeyse tek parça kalır (kapak)."""
    out: list[list[int]] = []
    clauses, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        if w.text.rstrip('"“”»)')[-1:] in _PUNCT_END:
            clauses.append(cur)
            cur = []
    if cur:
        clauses.append(cur)
    start = 0
    if whole_first:
        sent = []
        for i, w in enumerate(words):
            sent.append(i)
            if w.text.rstrip('"“”»)')[-1:] in ".?!…":
                break
        if len(sent) <= whole_first:
            out.append(sent)
            start = len(sent)
            clauses = [[i for i in c if i >= start] for c in clauses]
            clauses = [c for c in clauses if c]
    for c in clauses:
        pos = 0
        for sz in _split_clause([words[i].text for i in c]):
            out.append(c[pos:pos + sz])
            pos += sz
    return out


class Kinetic:
    """Dış ses, sahne sınırını aşmayan 1-4 kelimelik (kapakta en çok 6) parçalar hâlinde; her kelime yırtık kâğıtta.
    Kapak sahnesinin parçaları daha uzun bantta (KIN0) durur; kapak cümlesinin etiketleri biraz daha sıkı (iç boşluk
    0,09, eğim en çok 2°) ve ilk kelime t=0'da zıplamaz, böylece altı kelimelik kapak cümlesi büyük (~76 px) okunur.
    Kapak sahnesinde okunan kelime %12 yerine %6 (kapak cümlesinde %4) zıplar."""
    X0, Y0, X1, Y1 = KIN
    MAXW = 800
    TILT = math.sin(math.radians(3.0))
    REGION = (40, 196, 935, 500)
    PAD, COVER_PAD = 0.16, 0.09
    CUR_ROT, COVER_ROT = 3.0, 2.0

    def __init__(self, words: list[Word], ranges: list[tuple[int, int]]):
        self.words = words
        self.text = [_clean_word(w.text) for w in words]
        self.chunks: list[list[int]] = []
        self.first: set[int] = set()     # kapak sahnesinin parçaları (uzun bant)
        for si, (a, b) in enumerate(ranges):
            for ch in kart_phrases(words[a:b], whole_first=6 if si == 0 else 0):
                if si == 0:
                    self.first.add(len(self.chunks))
                self.chunks.append([a + i for i in ch])
        self.chunk_of = {i: ci for ci, ch in enumerate(self.chunks) for i in ch}
        self._lay: dict = {}
        self._lab: dict = {}
        self._layer: dict = {}

    def cover(self, ci: int) -> bool:
        """Kapak cümlesi: videonun ilk parçası."""
        return ci == 0 and ci in self.first

    def pop(self, ci: int) -> float:
        """Okunan kelimenin başlangıçtaki büyüme oranı (kapak sahnesinde daha az: uzun bantta etiketler büyük)."""
        return (0.04 if self.cover(ci) else 0.06) if ci in self.first else 0.12

    def layout(self, ci: int):
        """Parçanın en büyük boyutta en fazla 2 satıra yerleşimi: [(kelime, cx, cy, eğim)], boyut."""
        if ci in self._lay:
            return self._lay[ci]
        idx = self.chunks[ci]
        words = [self.text[i] for i in idx]
        gap = 14
        chosen = None
        is_cover = self.cover(ci)
        # kapak sahnesi alta doğru uzun bantta; üstte yalnız sıkı kapak cümlesi (az zıplar) başlık çizgisine yaklaşır
        y_top, y_bot = KIN0[1] if is_cover else self.Y0, KIN0[3] if ci in self.first else self.Y1
        pad = self.COVER_PAD if is_cover else self.PAD
        pop = self.pop(ci) if ci in self.first else 0.0
        tilt = math.sin(math.radians(self.COVER_ROT if is_cover else self.CUR_ROT))
        for size in range(150, 34, -2):
            fS = fnt("anton", size * SS)
            padx, pady = size * 0.2, size * pad
            cap = -fS.getbbox("H", anchor="ls")[1] / SS
            ws, tops, bots = [], [], []
            for w in words:
                l, t, r, b = fS.getbbox(w, anchor="ls")
                ws.append(fS.getlength(w) / SS + 2 * padx)
                tops.append(max(cap, -t / SS) + pady)
                bots.append(max(0, b / SS) + pady)
            def lw(ln):
                return sum(ws[i] for i in ln) + gap * (len(ln) - 1)
            options = [[list(range(len(words)))]]
            if lw(options[0][0]) > self.MAXW:   # iki satır: en geniş satırı en dar yapan bölme (dengeli satırlar)
                if len(words) < 2:
                    continue
                options = sorted(([list(range(j)), list(range(j, len(words)))] for j in range(1, len(words))),
                                 key=lambda L: (max(lw(x) for x in L), lw(L[1]) - lw(L[0])))
                if not is_cover:   # kapak cümlesinde sığan her bölme denenir (en dengelisi önce)
                    options = options[:1]
            overlap = size * (0.05 if is_cover else 0.08)
            for lines in options:
                if any(lw(ln) > self.MAXW for ln in lines):
                    continue
                heights = [max(tops[i] for i in ln) + max(bots[i] for i in ln) for ln in lines]
                total_h = sum(heights) - overlap * (len(lines) - 1)
                # eğik etiketin dikey taşması (en fazla 3°, kapakta 2°) + gölge: alan dışına, başlık çizgisine çıkmasın;
                # kapak sahnesinde okunan kelimenin zıplaması da hesaba katılır
                ex_top = max(ws[i] for i in lines[0]) * tilt / 2 + 4 + pop * heights[0] / 2
                ex_bot = max(ws[i] for i in lines[-1]) * tilt / 2 + 12 + pop * heights[-1] / 2
                if total_h + ex_top + ex_bot <= y_bot - y_top:
                    chosen = (size, lines, ws, tops, heights, overlap, total_h, ex_top, ex_bot)
                    break
            if chosen:
                break
        if chosen is None:  # son çare: en küçük boyut, tek satır
            size = 36
            chosen = (size, [list(range(len(words)))], [tw(w, "anton", size) + 16 for w in words],
                      [size] * len(words), [size * 1.4], 0, size * 1.4, 0, 0)
        size, lines, ws, tops, heights, overlap, total_h, ex_top, ex_bot = chosen
        rng = random.Random(7000 + idx[0])
        cx0 = (self.X0 + self.X1) / 2
        y = y_top + ex_top + (y_bot - y_top - total_h - ex_top - ex_bot) / 2
        lo, hi = (0.6, 1.4) if is_cover else (0.8, 2.0)
        out = []
        for li, ln in enumerate(lines):
            base = y + max(tops[i] for i in ln)
            lw = sum(ws[i] for i in ln) + gap * (len(ln) - 1)
            x = cx0 - lw / 2
            for i in ln:
                gi = idx[i]
                sgn = -1 if gi % 2 else 1
                rot = sgn * rng.uniform(lo, hi)
                out.append((gi, x + ws[i] / 2, base, rot, sgn))
                x += ws[i] + gap
            y += heights[li] - overlap
        self._lay[ci] = (out, size, (pad, self.COVER_ROT if is_cover else self.CUR_ROT))
        return self._lay[ci]

    def label(self, gi: int, state: str, dark: bool, size: int, rot: float, sgn: int, style=(PAD, CUR_ROT)):
        """style: (iç boşluk oranı, okunan kelimenin eğimi)."""
        key = (gi, state, dark, size, style)
        if key not in self._lab:
            if state == "said":
                fg, bg, rim = OFF, INK, OFF
            elif state == "cur":
                fg, bg, rim = (INK, YELLOW, OFF) if dark else (OFF, RED, OFF)
            else:
                fg, bg, rim = UPC_FG, UPC_BG, OFF
            lab = torn_label(self.text[gi], size, fg, bg, 900 + gi * 7, pad=style[0], rim=rim)
            r = sgn * style[1] if state == "cur" else rot
            im = lab.render(r, shadow=(4, 7, 4, 0.32 if state == "cur" else 0.24))
            self._lab[key] = (im, lab.base_y, lab.h)
        return self._lab[key]

    def layer(self, ci: int, cur: int, dark: bool):
        """(kalanların katmanı, şu anki kelimenin görüntüsü, merkezi). cur: parçadaki o anki kelimenin indeksi."""
        key = (ci, cur, dark)
        if key in self._layer:
            return self._layer[key]
        lay, size, style = self.layout(ci)
        rx0, ry0, rx1, ry1 = self.REGION
        rest = Image.new("RGBA", (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
        cur_im = cur_c = None
        for gi, cx, base, rot, sgn in lay:
            state = "said" if gi < cur else ("cur" if gi == cur else "up")
            im, base_y, h = self.label(gi, state, dark, size, rot, sgn, style)
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
    draw_text(d, (40 * s, (ch / 2 + 10) * s), text, "mono", size * s, INK)
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
        self.area = ctx.get("box") or CARD   # kartın kutusu: kapak sahnesinde CARD0 (biraz aşağıda başlar)
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
    def has_chip(self) -> bool:
        """Kartın altında not çipi var mı (kapak damgası çipin üstüne yerleşir)."""
        return bool((self.c.get("note") or "").strip())

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


_UNKNOWN_AUTHORS = {"bilinmiyor", "unknown", "unknown author", "anonymous", "anonim", "untitled", "n/a", "-"}
# Wikimedia'nın yer tutucu yazar adları (ör. "Unknown photographer", "Self-photographed", "Own work"): kaynak adı yazılır
_UNKNOWN_AUTHOR_RE = re.compile(r"^(unknown|anonymous|anonim|bilinmeyen|self[- ]?photographed|own work|kendi eseri)\b", re.I)
_OPENVERSE_SOURCES = {"flickr": "Flickr", "wikimedia": "Wikimedia"}


def credit_chip(cr: dict, max_len: int = 32) -> str:
    """Fotoğraf künyesinden (images.credit_dict: author, license, source) en çok max_len karakterlik çip yazısı:
    "NASA · kamu malı", "Wikimedia · CC BY-SA 4.0". Yalnız künyedeki bilgiyi kısaltır, kaynak uydurmaz; yazar
    bilinmiyorsa ya da sığmıyorsa kaynağın kısa adı yazılır."""
    if not cr:
        return ""
    lic = re.sub(r"\s+", " ", str(cr.get("license") or "")).strip()
    low = lic.lower()
    if re.match(r"(public domain|pd\b|pd-|pdm\b|cc pdm|kamu)", low):
        lic = "kamu malı"
    elif low.startswith("cc0"):
        lic = "CC0"
    src = str(cr.get("source") or "").strip()
    if src.lower().startswith("openverse"):
        src = _OPENVERSE_SOURCES.get(src.split("/", 1)[-1].strip().lower(), "Openverse")
    elif "wikimedia" in src.lower():
        src = "Wikimedia"
    author = re.sub(r"\s+", " ", str(cr.get("author") or "")).strip()
    names = []
    if author and author.lower() not in _UNKNOWN_AUTHORS and not _UNKNOWN_AUTHOR_RE.match(author):
        first = re.split(r"\s*[,;/|(]\s*|\s+-\s+", author)[0].strip()
        # "John Smith (talk)", "A, B": ilk ad; düz addaysa önce tam ad denenir
        names += [first] if re.search(r"[(,;]", author) else [author, first]
    names.append(src)
    for who in names:
        if not who:
            continue
        text = f"{who} · {lic}" if lic else who
        if len(text) <= max_len:
            return text
    return lic if len(lic) <= max_len else ""


class PhotoCard(Card):
    """Arşiv duotone fotoğraf, bant, not çipi ve dosya adlı başlık çubuğu; fotoğraf sahne boyunca hafif yakınlaşır."""
    still = False

    def __init__(self, ctx):
        super().__init__(ctx)
        rx0, ry0 = CARD_REGION[:2]
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, self.area, f"{self.topic_slug} / arsiv_{self.idx + 1:02d}.jpg",
                                   tr_upper("arşiv"))
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
        # not yoksa fotoğrafın kendi künyesinden kısa çip ("NASA · kamu malı"); künye yoksa çip de yok
        self.chip = note = (self.c.get("note") or "").strip() or credit_chip(self.c.get("credit") or {})
        if note:
            chip_label(ov, px0 + 22, py1 - 96, note, max_w=pw - 60)
        self.over = ov.done()
        self.zoom_end = 1.1

    @property
    def has_chip(self) -> bool:
        return bool(self.chip)

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
        ix0, iy0, ix1, iy1 = shell(pen, self.area, f"{self.topic_slug} / cizim_{self.idx + 1:02d}.png",
                                   tr_upper("çizim"))
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
    """'21.196' / '%90' / '1,5 milyon' / '450.000 ₺' -> (ön ek, değer, ondalık hane, binlik ayraç var mı, son ek).
    Oran ya da olasılık ('1 / 90 MİLYON', '3:1') sayılmaz: None (sayaç değeri sayarak değil, olduğu gibi gösterir)."""
    if re.search(r"\d\s*[/:]\s*\d", s or ""):
        return None
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
    """0'dan değere ~0,8 sn'de sayan büyük sayı + etiket + değere bağlı kesik çizgi zaman çizelgesi. Sayı, dış seste
    söylendiği anda oturur (land); o ana kadar 0 ve boş çizelge görünür, sayma land'den 0,8 sn önce başlar."""
    still = False
    COUNT = 0.8

    def __init__(self, ctx):
        super().__init__(ctx)
        raw = (self.c.get("value") or "").strip()
        self.parsed = parse_value(raw)
        self.raw = raw
        self.land, self.count_start = self.COUNT, 0.0
        digits = re.sub(r"\D", "", raw)
        # sayı söylendiği anda oturur; sayılmayan oranda tam rakam dizisi geçmiyorsa ('1 / 90 MİLYON' -> '90
        # milyonda bir') en uzun rakam grubu aranır
        groups = ([digits] + (sorted(re.findall(r"\d+", raw), key=len, reverse=True)[:1] if self.parsed is None else [])
                  if digits else [])
        for g in groups:
            w = next((w for w in self.spec.words if g in re.sub(r"\D", "", w.text)), None)
            if w is not None:
                self.land = max(0.25, w.start - self.spec.start + 0.05)
                self.count_start = max(0.0, self.land - self.COUNT)
                break
        self._zero = None
        self.label = tr_upper((self.c.get("label") or "").strip())
        self.note = (self.c.get("note") or "").strip()
        pen = self.pen()
        ix0, iy0, ix1, iy1 = self.inner = shell(pen, self.area,
                                                f"sayaç / {slug(self.label or 'deger', 24) or 'deger'}.log",
                                                tr_upper("sayaç"))
        cx = (ix0 + ix1) / 2
        final = self.text_at(1.0)
        self.size = 250
        # sayı hem genişliğe hem yüksekliğe sığar: etiket ve not, zaman çizelgesinin (iy1 - 96) en az 44 px üstünde
        # kalır (kapak sahnesinin kısa kartında sayı biraz küçülür)
        room = iy1 - 96 - iy0 - 42 - 100 - (56 if self.note else 0) - 44
        while (self._num_w(final, self.size) > ix1 - ix0 - 90 or -tbox("8", "anton", self.size)[1] > room) \
                and self.size > 120:
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
        if self.hook or self.parsed is None:
            return 1.0
        return ease_out_cubic((lt - self.count_start) / max(0.05, self.land - self.count_start))

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
        land = clamp((lt - self.land) / 0.2) if not self.hook else 1.0
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
        if self.progress(lt) >= 1 and (self.hook or lt >= self.land + 0.2):
            if self._fin is None:
                self._fin = self.draw_dynamic(self.land + 10.0)
            return self._fin
        if lt <= self.count_start:
            if self._zero is None:
                self._zero = self.draw_dynamic(self.count_start)
            return self._zero
        return self.draw_dynamic(lt)

    def mood(self, lt, dur):
        return "surprised" if (self.hook or lt >= self.land) else "normal"


def parse_receipt(lines, limit: int = 5) -> list[tuple[str, str]]:
    """Hesap fişi satırları (Scene.card_lines): 'KALEM|TUTAR' -> (KALEM, TUTAR), Türkçe büyük harf, fazla boşluklar
    teke iner. Tutar yoksa '' ('KİRA', 'KİRA|'); birden çok '|' varsa kalem ilk parça, tutar son dolu parça; '|' hiç
    yoksa 'KİRA: 135.000 ₺' gibi son iki noktadan ayrılır. Boş satırlar atlanır. limit'ten (5) fazla satır varsa ilk
    limit - 1 satır kalır, kalanlar tutarlarının toplamıyla tek 'DİĞER' satırında birleşir: görünen satırlar yine
    toplama (card_value) eşit kalır."""
    out = []
    for raw in lines or []:
        text = re.sub(r"\s+", " ", str(raw or "")).strip()
        if "|" in text:
            parts = [p.strip() for p in text.split("|")]
            label, amount = parts[0], next((p for p in reversed(parts[1:]) if p), "")
        else:
            m = re.match(r"^(.*[^\d\s])\s*:\s*([^:]*\d[^:]*)$", text)    # '10:30' gibi saat bölünmez
            label, amount = (m.group(1), m.group(2).strip()) if m else (text, "")
        if not label and not amount:
            continue
        out.append((tr_upper(label), tr_upper(amount)))
    if len(out) > limit:
        out = out[:limit - 1] + [("DİĞER", receipt_sum([a for _, a in out[limit - 1:]]))]
    return out


def receipt_sum(amounts: list[str]) -> str:
    """Fiş tutarlarının toplamı, tutarların yazılışıyla: hepsi aynı büyüklük birimindeyse o birimle ('-20 MİLYON ₺' +
    '-3 MİLYON ₺' -> '-23 MİLYON ₺'), değilse binlik ayraçlı tam sayı ('-270.000 ₺' + '1 ₺' -> '-269.999 ₺').
    Tutarsız satır toplama girmez; okunamayan ya da yüzde tutar varsa (toplanamaz) ''."""
    vals = [a for a in amounts if a]
    parsed = [tutar(a) if "%" not in a else None for a in vals]
    if not vals or any(p is None for p in parsed):
        return ""
    total = sum(p[0] for p in parsed)
    units = {m.group(0) if (m := re.search(r"MİLYAR|MİLYON|BİN", a)) else "" for a in vals}
    unit = units.pop() if len(units) == 1 else ""
    n = abs(total) / {"BİN": 1e3, "MİLYON": 1e6, "MİLYAR": 1e9}.get(unit, 1.0)
    dec = next((d for d in (0, 1, 2) if abs(n * 10 ** d - round(n * 10 ** d)) < 1e-6), 2)
    cur = next((c for c in ("₺", "TL") if any(c in a for a in vals)), "")
    return ("-" if total < 0 else "") + fmt_value(round(n, dec), dec, True) + "".join(f" {x}" for x in (unit, cur) if x)


# hesap fişi satırını dış sese bağlarken sayılmayan kelimeler (bağlaç, edat, niteleyen)
RECEIPT_STOP = CLITICS | MODIFIERS | {"ve", "ya", "veya", "için", "+", "-", "&"}


class ReceiptCard(Card):
    """Hesap fişi (olsaydin kalıbı): kırık beyaz termal kâğıt, zikzak yırtık üst/alt kenar, hafif eğik, sert mürekkep
    gölge, üstte sarı bant. Satırlar ('KALEM ........ TUTAR', mono 44-32 px, uzun kalem iki satıra sarılır, eksi
    tutarlar kırmızı) dış ses ilerledikçe birer birer basılır: kâğıt aşağı doğru beslenir, alt yırtık kenar yeni
    satırın altına iner (satırın kalemi ya da tutarı söylenince; söylenmiyorsa sahneye eşit yayılır). Son satırdan
    sonra çift çizginin altına toplam basılır, tutar kırmızı yırtık etikette damga gibi iner ve Makas şaşırır;
    card_note fişin altında küçük. Kapak sahnesinde fiş ilk karede tam basılı."""
    still = False
    PW = 700                       # kâğıt genişliği
    PAD = 34                       # kâğıt iç kenar boşluğu (yan)
    ROT = -1.6                     # eğim (derece)
    TOOTH, TEETH = 12, 26          # zikzak kenar: diş yüksekliği, yaklaşık diş genişliği
    M = 34                         # çizim payı (bant, diş, gölge)
    SHADOW = (10, 10)
    PAPER_COL = (253, 251, 245)
    FEED = 0.24                    # bir satırlık kâğıt besleme süresi (sn)
    HOLD = 1.2                     # toplam, sahne bitmeden en az bu kadar ekranda
    T0 = 0.3                       # ilk satırın en erken basıldığı an

    def __init__(self, ctx):
        super().__init__(ctx)
        self.rows = parse_receipt(self.c.get("lines")) or [("", "")]
        self.total = tr_upper((self.c.get("value") or "").strip())
        self.total_label = tr_upper((self.c.get("label") or "").strip()) or "TOPLAM"
        self.note = (self.c.get("note") or "").strip()
        x0, y0, x1, y1 = self.area
        # görünen kâğıdın (bant, dişler, gölge dahil) üst sınırı: kapakta seri etiketi kartın üst kenarında durur,
        # diğer sahnelerde kayan başlığın (KIN) hemen altı
        top = y0 + 86 if self.hook else KIN[3] + 12
        avail = CARD_FLOOR - 4 - top
        self._fit_rows(avail)
        self.scale = min(1.0, avail / self.full_h())   # sığmayan fiş bütünüyle küçülür
        self._content = self._draw_content()
        self._paper: dict = {}
        vx0, vy0, vx1, vy1 = self.paper(self.L_full).getchannel("A").getbbox()
        if vy1 - vy0 > avail:                          # tahmin tutmadıysa ölçülen yüksekliğe göre küçülür
            self.scale *= avail / (vy1 - vy0)
            self._paper.clear()
            vx0, vy0, vx1, vy1 = self.paper(self.L_full).getchannel("A").getbbox()
        # tam basılmış fişin görünen kutusu: kapakta üstten, diğer sahnelerde boşlukta ortalı
        cy = top + ((vy1 - vy0) if self.hook else avail) / 2
        self.pos = ((x0 + x1) / 2 - (vx0 + vx1) / 2, cy - (vy0 + vy1) / 2)
        self.stamp = self._stamp()
        self._fin = None
        self.timing(max(0.6, ctx["dur"]))

    # ------------------------------------------------------------ yerleşim (kâğıdın yerel koordinatları, y aşağı)
    # kalem satırlarının yerleşimleri (mono yazı boyu, satır aralığı katsayısı): sığmayan kalem iki satıra sarılır
    WRAPPED = ((44, 1.3), (42, 1.3), (40, 1.3), (38, 1.15), (36, 1.12), (34, 1.12), (32, 1.12))
    MIN_FS = 26                    # fiş küçülünce kalem yazısının ekrandaki en küçük boyu (fişin alt başlığı kadar)

    def _fit_rows(self, avail: float) -> None:
        """Kalem satırlarının yerleşimi: önce kalemler kısaltılmadan (gerekirse iki satıra sarılarak) 44'ten 36 px'e
        küçülen yazıyla, fiş küçülmeden sığan ilk yerleşim; yoksa fişin bütünüyle küçüleceği sarılı yerleşimlerden
        kalem yazısını ekranda en büyük gösteren (32 px'e kadar). O da MIN_FS'in altında kalırsa (çok satırlı uzun
        kalemler kapakta) son çare kalemler tek satırda kelime sınırında kısaltılır."""
        for fs, lhk in self.WRAPPED[:5]:
            self._layout(fs, True, lhk)
            if self.full_h() <= avail:
                return
        best = None
        for fs, lhk in self.WRAPPED:
            self._layout(fs, True, lhk)
            shown = fs * min(1.0, avail / self.full_h())
            if best is None or shown > best[0] + 1e-6:
                best = (shown, fs, lhk)
        if best[0] >= self.MIN_FS:
            self._layout(best[1], True, best[2])
        else:
            self._layout(40, False, 1.18)

    def _layout(self, fs: int, wrap_ok: bool, lhk: float) -> None:
        self.fs, self.lh = fs, round(fs * lhk)
        iw = self.PW - 2 * self.PAD
        cap_m = -tbox("H", "mono", fs)[1]
        self.head_base = 24 - tbox("H", "archivo", 40)[1]
        self.sub_base = self.head_base + 38
        self.rule_y = self.sub_base + 20
        y = self.rule_y + 22
        self.row_geo = []                          # (satır taban çizgileri, kalem satırları, tutar, alt)
        for label, amount in self.rows:
            aw = tw(amount, "mono", fs) if amount else 0.0
            room = iw - (aw + 48 if amount else 0)
            lines = [label]
            if tw(label, "mono", fs) > room:
                lines = self._wrap_label(label, iw, room, fs) if wrap_ok else [fit_words(label, "mono", fs, room)]
            bases = [y + cap_m + j * self.lh for j in range(len(lines))]
            bottom = bases[-1] + fs * 0.3
            self.row_geo.append((bases, lines, amount, bottom))
            y = bottom + 10
        self.feed = [self.rule_y + 10] + [g[3] + 12 for g in self.row_geo]
        y += 10
        self.rule2 = y if self.total else None
        self.total_stacked = False
        if self.total:
            y += 30
            lsz, ts, label = 40, 76, self.total_label

            def spare() -> float:                  # etiketle damga arasında 42 px'ten artan yer (< 0: sığmıyor)
                return iw - tw(label, "archivo", lsz) - 36 - (tw(self.total, "anton", ts) + 0.4 * ts)
            while ts > 44 and spare() < 0:          # önce damga küçülür,
                ts -= 4
            while lsz > 30 and spare() < 0:         # en küçüğünde etiket de küçülür
                lsz -= 2
            self.total_stacked = spare() < 0
            if self.total_stacked:                 # yine sığmıyorsa etiket kendi satırında, damga altında sağa yaslı
                lsz, ts = 40, 76
                while lsz > 30 and tw(label, "archivo", lsz) > iw:
                    lsz -= 2
                label = fit_words(label, "archivo", lsz, iw)
                while ts > 44 and tw(self.total, "anton", ts) + 0.4 * ts > iw - 36:
                    ts -= 4
            self.total_size, self.total_label_size, self.total_label_text = ts, lsz, label
            lab = torn_label(self.total, ts, OFF, RED, 4500 + self.idx)
            self.total_h = lab.h
            cap = -tbox("H", "archivo", lsz)[1]
            if self.total_stacked:
                self.total_base = y + cap
                y = self.total_base + 24           # Ç, Ş çengelleri ve damganın yırtık kenarı birbirine değmez
            else:
                self.total_base = y + lab.h / 2 + cap / 2
            self.total_c = (self.PW - self.PAD - lab.w / 2 + 6, y + lab.h / 2)
            y += lab.h + 26                        # etiketin eğimi ve gölgesi nota binmesin
        if self.note:
            self.note_base = y - tbox("H", "mono", 28)[1]
            y = self.note_base + 12
        self.L_full = y + 20
        self.feed.append(self.L_full)

    def _wrap_label(self, label: str, iw: float, room: float, fs: int) -> list[str]:
        """Uzun kalem iki satıra: ilk satır tam genişlik, ikinci satır tutarın soluna sığar (en dengeli bölme);
        hiçbir bölme sığmazsa tek satır '…' ile kısalır."""
        words = label.split()
        best = None
        for j in range(1, len(words)):
            a, b = " ".join(words[:j]), " ".join(words[j:])
            wa, wb = tw(a, "mono", fs), tw(b, "mono", fs)
            if wa <= iw and wb <= room and (best is None or abs(wa - wb) < best[0]):
                best = (abs(wa - wb), [a, b])
        if best:
            return best[1]
        if len(words) > 1:          # ilk kelime ilk satırda, kalanı tutarın solunda ('…' ile kısalabilir)
            return [fit_words(words[0], "mono", fs, iw), fit_words(" ".join(words[1:]), "mono", fs, room)]
        return [fit_words(label, "mono", fs, room)]

    def full_h(self) -> float:
        """Tam basılmış fişin ekranda görünen yüksekliğinin tahmini (eğim, dişler, bant ve gölge dahil; çizim payı
        hariç). Yerleşim ölçülen yükseklikle düzeltilir."""
        return self.rot_size()[1] - 2 * self.M + 38

    def rot_size(self) -> tuple[float, float]:
        w, h = self.PW + 2 * self.M, self.L_full + self.TOOTH + 2 * self.M
        a = math.radians(abs(self.ROT))
        return w * math.cos(a) + h * math.sin(a), w * math.sin(a) + h * math.cos(a)

    def _poly(self, L: float, dx=0.0, dy=0.0) -> list[tuple[float, float]]:
        """Kâğıdın zikzak kenarlı dış çizgisi: üst kenar y=0, alt kenar L (dişler dışarı)."""
        n = max(2, round(self.PW / self.TEETH))
        tw_ = self.PW / n
        pts = [(i * tw_ / 2 + dx, (-self.TOOTH if i % 2 else 0) + dy) for i in range(2 * n + 1)]
        pts += [(self.PW - i * tw_ / 2 + dx, L + (self.TOOTH if i % 2 else 0) + dy) for i in range(2 * n + 1)]
        return pts

    def _sprite(self) -> Sprite:
        return Sprite(self.PW, self.L_full + self.TOOTH, margin=self.M)

    def _draw_content(self) -> Image.Image:
        sp = self._sprite()
        cx = self.PW / 2
        iw = self.PW - 2 * self.PAD
        x0, x1 = self.PAD, self.PW - self.PAD
        head = "HESAP FİŞİ"
        hw = tw(head, "archivo", 40)
        sp.text((cx + 26, self.head_base), head, "archivo", 40, INK, anchor="ms")
        sc = svg_img(scissors_svg(26), SCISSORS_VB, 60 * SS, 60 * 84 / 124 * SS)
        px_, py_ = sp.p(cx + 26 - hw / 2 - 74, self.head_base - 36)
        _comp(sp.im, sc, px_, py_)
        sub = fit(f"// {self.topic_slug} · {self.idx + 1:02d}", "mono", 26, iw)
        sp.text((cx, self.sub_base), sub, "mono", 26, INK, anchor="ms")
        x = x0
        while x < x1:
            sp.line([(x, self.rule_y), (min(x + 14, x1), self.rule_y)], INK, 3)
            x += 24
        fs = self.fs
        for bases, lines, amount, _ in self.row_geo:
            for b, L in zip(bases, lines):
                if L:
                    sp.text((x0, b), L, "mono", fs, INK)
            if amount:
                col = RED if amount[:1] in "-−" else INK
                sp.text((x1, bases[-1]), amount, "mono", fs, col, anchor="rs")
                lx0 = x0 + (tw(lines[-1], "mono", fs) + 14 if lines[-1] else 0)
                lx1 = x1 - tw(amount, "mono", fs) - 14
                d = lx0 + 6
                while d <= lx1 - 2:
                    sp.dot(d, bases[-1] - fs * 0.1, 2.6, GREY)
                    d += 13
        if self.rule2 is not None:
            for yy in (self.rule2, self.rule2 + 10):
                sp.line([(x0, yy), (x1, yy)], INK, 3.5)
            sp.text((x0, self.total_base), self.total_label_text, "archivo", self.total_label_size, INK)
        if self.note:
            sp.text((cx, self.note_base), fit(self.note, "mono", 28, iw), "mono", 28, DGREY, anchor="ms")
        return sp.im

    def _stamp(self) -> tuple[Image.Image, tuple[float, float]] | None:
        """Toplam tutarın kırmızı yırtık etiketi (1x) ve fişin döndürülmüş görüntüsündeki merkezi."""
        if not self.total:
            return None
        lab = torn_label(self.total, self.total_size, OFF, RED, 4500 + self.idx)
        im = lab.render(self.ROT + 3.0, shadow=(6, 8, 0, 0.9))
        if self.scale < 1:
            im = im.resize((max(1, int(im.width * self.scale)), max(1, int(im.height * self.scale))), Image.LANCZOS)
        return im, self.to_screen(*self.total_c)

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        """Kâğıdın yerel noktası -> ekran (fişin eğimi, konumu ve ölçeğiyle)."""
        w, h = self.PW + 2 * self.M, self.L_full + self.TOOTH + 2 * self.M
        rw, rh = self.rot_size()
        dx, dy = x + self.M - w / 2, y + self.M - h / 2
        a = math.radians(self.ROT)
        rx, ry = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
        return self.pos[0] + (rw / 2 + rx) * self.scale, self.pos[1] + (rh / 2 + ry) * self.scale

    def paper(self, L: float) -> Image.Image:
        """Alt kenarı L'de olan fişin 1x görüntüsü (sabit boyut: üst kenar her durumda aynı yerde)."""
        key = int(round(L))
        if key in self._paper:
            return self._paper[key]
        sp = self._sprite()
        sx, sy = self.SHADOW
        sp.polygon(self._poly(key, sx, sy), INK + (255,))
        sp.polygon(self._poly(key), self.PAPER_COL + (255,))
        mask = Image.new("L", sp.im.size, 0)
        ImageDraw.Draw(mask).polygon([sp.p(x, y) for x, y in self._poly(key - 4)], fill=255)
        content = self._content.copy()
        content.putalpha(ImageChops.multiply(content.getchannel("A"), mask))
        sp.im.alpha_composite(content)
        pts = self._poly(key)
        sp.line(pts + [pts[0]], INK, 4)
        tape(sp, self.PW / 2, -4, 180, 46, -3, 4600 + self.idx, alpha=215)
        im = sp.im.rotate(self.ROT, resample=Image.BICUBIC, expand=True)
        rw, rh = self.rot_size()
        im = im.resize((max(1, int(round(rw * self.scale))), max(1, int(round(rh * self.scale)))), Image.LANCZOS)
        if len(self._paper) > 48:
            self._paper.clear()
        self._paper[key] = im
        return im

    # ------------------------------------------------------------ zamanlama
    def timing(self, dur: float) -> None:
        """Olay anları (sahne başına göre): her satır ve toplam/not. Satır, kalemi ya da tutarı dış seste geçtiğinde
        basılır; geçmiyorsa satırlar sahneye eşit yayılır. Toplam söylendiği anda (yoksa son satırdan 0,7 sn sonra)
        basılır ama en az HOLD sn ekranda kalır. Sahne çok kısaysa fiş baştan basılı durur."""
        n = len(self.rows)
        ev = n + 1
        self.instant = self.hook or dur < 1.2
        if self.instant:
            self.events = [-1.0] * ev
            return
        words = self.spec.words or []
        st = self.spec.start
        t_end = max(self.T0 + 0.1, dur - self.HOLD - self.FEED)
        gap = min(0.35, (t_end - self.T0) / max(1, n))
        times, prev = [], self.T0 - gap
        used = -1
        for k, (label, amount) in enumerate(self.rows):
            latest = t_end - (n - k) * gap
            lo = prev + gap
            stems = {_bare(x)[:4] for x in label.split() if len(_bare(x)) >= 2 and _bare(x) not in RECEIPT_STOP}
            dig = re.sub(r"\D", "", amount)
            t = None
            # kalem ya da tutar söylenmeye başlayınca (en erken bir önceki satırdan gap sonra)
            for wi, w in enumerate(words):
                lt = w.start - st - 0.08
                if wi <= used or lt > latest:
                    continue
                if _bare(w.text)[:4] in stems or (len(dig) >= 2 and dig in re.sub(r"\D", "", w.text)):
                    t, used = lt, wi
                    break
            if t is None:
                span = (t_end - 0.5 - self.T0) / max(1, n - 1) if n > 1 else 0.0
                t = min(max(lo, self.T0 + k * span), latest)
            times.append(max(lo, t))
            prev = times[-1]
        t_tot = None
        dig = re.sub(r"\D", "", self.total)
        if len(dig) >= 2:
            w = next((w for w in words if dig in re.sub(r"\D", "", w.text)), None)
            if w is not None:
                t_tot = w.start - st - 0.08
        lo = prev + self.FEED + 0.15
        if t_tot is None:
            t_tot = prev + (0.7 if self.total else 0.4)
        times.append(min(max(lo, t_tot), max(lo, t_end)))
        self.events = times

    def length(self, lt: float) -> float:
        """Kâğıdın o anki uzunluğu (alt kenar): son olayın beslemesi ease_out ile ilerler."""
        if self.instant:
            return self.L_full
        j = bisect.bisect_right(self.events, lt) - 1
        if j < 0:
            return self.feed[0]
        p = ease_out_cubic((lt - self.events[j]) / self.FEED)
        return lerp(self.feed[j], self.feed[j + 1], p)

    def stamp_state(self, lt: float) -> tuple[float, float] | None:
        """Toplam damgasının (ölçek, saydamlık): büyükten iner, hafifçe ezilip oturur (Nasıl yapılır? numarası gibi)."""
        if self.stamp is None:
            return None
        if self.instant:
            return 1.0, 1.0
        ps = (lt - self.events[-1] - self.FEED * 0.7) / 0.16
        if ps <= 0:
            return None
        if ps < 1:
            return lerp(1.8, 0.94, ps ** 2), min(1.0, ps * 3)
        return lerp(0.94, 1.0, ease_out_cubic((ps - 1) * 0.16 / 0.12)), 1.0

    def _compose(self, L: float, st) -> Image.Image:
        rx0, ry0, rx1, ry1 = CARD_REGION
        img = Image.new("RGBA", (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
        _comp(img, self.paper(L), self.pos[0] - rx0, self.pos[1] - ry0)
        if st is not None:
            k, al = st
            im, (cx, cy) = self.stamp
            if abs(k - 1) > 1e-3:
                im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.BILINEAR)
            if al < 0.999:
                im = im.copy()
                im.putalpha(im.getchannel("A").point(lambda v: int(v * al)))
            _comp(img, im, cx - im.width / 2 - rx0, cy - im.height / 2 - ry0)
        return img

    def layer(self, lt, dur):
        settled = self.FEED if self.stamp is None else max(self.FEED, self.FEED * 0.7 + 0.16 + 0.12)
        if self.instant or lt >= self.events[-1] + settled:
            if self._fin is None:
                self._fin = self._compose(self.L_full, (1.0, 1.0) if self.stamp is not None else None)
            return self._fin
        return self._compose(self.length(lt), self.stamp_state(lt))

    def mood(self, lt, dur):
        if self.instant or lt >= self.events[-1] + self.FEED * 0.7:
            return "surprised"
        return "thinking" if lt >= self.T0 else "normal"


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
    """EFSANE (çizilir) ve GERÇEK sütunları. İnanış çizilmeden önce okunur; çizik canlanır, sonra gerçek açılır.
    Zamanlama: tamamen açılmış hâl sahnenin sonunda en az HOLD sn ekranda kalır; inanış çizilmeden önce
    READ sn okunur. Sahne ikisine yetmiyorsa önce çizik öne alınır, sonra çizik/açılış animasyonu sıkıştırılır (en çok
    0,45 kat), en son okuma süresi kısalır; çok kısa sahnede (< ~1,9 sn) kart baştan açılmış durur."""
    still = False
    HOLD, READ = 1.25, 1.4
    STRIKE, STAGGER, GAP, REVEAL = 0.3, 0.1, 0.5, 0.35   # çizik satırı, satırlar arası, çizikten açılışa, açılış (sn)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.myth = (self.c.get("myth") or "").strip()
        self.fact = (self.c.get("fact") or "").strip()
        self.note = (self.c.get("note") or "").strip()
        ix0, iy0, ix1, iy1 = self.inner = inner_of(self.area)
        pad, gap = 22, 34
        foot = 56 if self.note else 0
        cw = (ix1 - ix0 - 2 * pad - gap) / 2
        self.cols = [(ix0 + pad, iy0 + pad, ix0 + pad + cw, iy1 - pad - foot),
                     (ix0 + pad + cw + gap, iy0 + pad, ix1 - pad, iy1 - pad - foot)]
        self.text_box = [(bx0 + 24, by0 + 98, bx1 - 22, by1 - 22) for bx0, by0, bx1, by1 in self.cols]
        tb = self.text_box[0]
        bw, bh = tb[2] - tb[0], tb[3] - tb[1]
        # her sütun kendi kutusuna ayrı sığdırılır; ikisi de küçüğünü ve aynı yüzü kullanır (en az 48 px, kalın dar yüz)
        font, size = "anton", 44
        for f in ("oswald", "anton"):
            sm, sf = self._fit_col(self.myth, f, bw, bh), self._fit_col(self.fact, f, bw, bh)
            if sm and sf and min(sm, sf) >= 48:
                font, size = f, min(sm, sf)
                break
        else:
            sm, sf = self._fit_col(self.myth, "anton", bw, bh, 44), self._fit_col(self.fact, "anton", bw, bh, 44)
            size = min(sm or 44, sf or 44)
        self.font, self.fsize = font, size
        self.lines = [wrap(t, font, size, bw) for t in (self.myth, self.fact)]
        self.pre = self._render(revealed=False)
        self.post = self._render(revealed=True)
        self.strike = self._strike_layer()
        self._fin = None
        self.timing(max(0.6, ctx["dur"]))

    def timing(self, dur: float) -> None:
        """Çizik inanışı anlatan cümle bitmek üzereyken gelir, ama tam açılmış hâl en az HOLD sn kalacak kadar erken."""
        n = max(1, len(self.strike_rows))

        def span(k):  # çizik başından her şeyin oturmasına kadar geçen süre (k: animasyon ölçeği)
            return k * max(self.STRIKE + self.STAGGER * (n - 1), self.GAP + self.REVEAL)

        latest = dur - self.HOLD
        k = clamp((latest - self.READ) / span(1.0), 0.45, 1.0)
        t = min(max(self.READ, self._myth_end() - 0.2), latest - span(k))
        self.instant = t < 0.3          # sahne çok kısa: animasyonsuz, baştan açılmış
        self.t_strike = t
        self.t_reveal = t + self.GAP * k
        self.strike_len, self.stagger, self.reveal_len = self.STRIKE * k, self.STAGGER * k, self.REVEAL * k
        self.t_full = t + span(k)

    LH = 1.12

    def _myth_end(self) -> float:
        """İnanışı anlatan cümlenin son kelimesinin bitişi (sahne başına göre). Cümle, card_myth ile en çok kelime kökü
        paylaşan cümledir; hiçbiri paylaşmıyorsa ilk cümle."""
        ws = self.spec.words or []
        if not ws:
            return 0.65
        sents, cur = [], []
        for w in ws:
            cur.append(w)
            if w.text.rstrip('"“”»)')[-1:] in ".?!…":
                sents.append(cur)
                cur = []
        if cur:
            sents.append(cur)
        stems = {_bare(x)[:4] for x in self.myth.replace("*", "").split() if len(_bare(x)) >= 3}
        score = [sum(_bare(w.text)[:4] in stems for w in sn) for sn in sents]
        best = sents[score.index(max(score))] if max(score) > 0 else sents[0]
        return best[-1].end - self.spec.start

    @staticmethod
    def _block_h(lines, font, size, lh):
        if not lines:
            return 0.0, 0.0
        f = fnt(font, size * SS)
        top = -f.getbbox(" ".join(w.strip("*") for w in lines[0]), anchor="ls")[1] / SS
        bot = max(0.0, f.getbbox(" ".join(w.strip("*") for w in lines[-1]), anchor="ls")[3] / SS)
        return top, (len(lines) - 1) * size * lh + top + bot

    def _fit_col(self, text, font, w, h, min_size=48, max_size=84, max_lines=4):
        """Metnin sütun kutusuna gerçek mürekkep yüksekliğiyle sığdığı en büyük boyut (yoksa None)."""
        for size in range(max_size, min_size - 1, -2):
            lines = wrap(text, font, size, w)
            if len(lines) > max_lines or any(tw(" ".join(x.strip("*") for x in L), font, size) > w for L in lines):
                continue
            if self._block_h(lines, font, size, self.LH)[1] <= h:
                return size
        return None

    def _col_text(self, pen: Pen, ci: int):
        font, size = self.font, self.fsize
        tx0, ty0, tx1, ty1 = self.text_box[ci]
        lh = size * self.LH
        lines = self.lines[ci]
        top, bh = self._block_h(lines, font, size, self.LH)
        yb = ty0 + (ty1 - ty0 - bh) / 2 + top
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
        shell(pen, self.area, "efsane / gerçek", tr_upper("karşılaştır"))
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
        if self.hook or self.instant or lt >= self.t_full:
            if self._fin is None:
                self._fin = self.post.copy()
                self._fin.alpha_composite(self.strike)
            return self._fin
        rx0, ry0 = CARD_REGION[:2]
        img = self.pre.copy() if lt < self.t_reveal else self.post.copy()
        if lt >= self.t_reveal:  # gerçek sütunu soldan sağa açılır
            k = ease_out_cubic((lt - self.t_reveal) / self.reveal_len)
            bx0, by0, bx1, by1 = (int(v) for v in self.cols[1])
            wv = int((bx1 - bx0 + 6) * k)
            if wv < bx1 - bx0 + 6:
                pre = self.pre.crop((bx0 - rx0 + wv, by0 - ry0 - 2, bx1 - rx0 + 6, by1 - ry0 + 6))
                img.paste(pre, (bx0 - rx0 + wv, by0 - ry0 - 2))
        for li, (x0, x1, y) in enumerate(self.strike_rows):  # satır satır çizilen kırmızı çizik
            k = ease_out_cubic((lt - self.t_strike - li * self.stagger) / self.strike_len)
            if k <= 0:
                continue
            xe = int(x0 - 12 + (x1 - x0 + 24) * k) - rx0
            band = (int(x0 - 14) - rx0, int(y - 16) - ry0, xe, int(y + 16) - ry0)
            if band[2] > band[0]:
                img.alpha_composite(self.strike.crop(band), band[:2])
        return img

    def mood(self, lt, dur):
        return "thinking" if (not self.hook and not self.instant and lt < self.t_reveal) else "normal"


class QuoteCard(Card):
    """Daktiloyla yazılan alıntı + kaynak çipi."""
    still = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self.quote = (self.c.get("label") or self.spec.narration).strip().strip('"“”')
        self.src = (self.c.get("note") or "").strip()
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, self.area, f"alıntı / {slug(self.src.split('·')[0], 20) or 'kaynak'}.txt",
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
    """Ara kanca: tam kırmızı ekran, görünür bantta yarım ton silme, bantlı yırtık kırık beyaz kart (Göz kartlarındaki
    gibi mürekkep yazı, vurgulu satır kırmızı yırtık etikette) ve "// DUR BİR SANİYE" sekmesi (sahne başlığı)."""
    still = False

    def __init__(self, ctx):
        super().__init__(ctx)
        lines = [tr_upper(x) for x in self.spec.headline if x.strip()] or ["AMA ASIL", "ŞAŞIRTICI", "OLAN"]
        hl = self.spec.highlight_line if 0 <= self.spec.highlight_line < len(lines) else len(lines) - 1
        sizes = [140 if i == hl else 118 for i in range(len(lines))]
        maxw = 620
        for i, ln in enumerate(lines):
            while tw(ln, "anton", sizes[i]) * (1.4 if i == hl else 1.0) > maxw and sizes[i] > 50:
                sizes[i] -= 4
        while sum(-tbox("H", "anton", s)[1] + 34 for s in sizes) > 470:
            sizes = [s - 4 for s in sizes]
        pad_x, pad_top, pad_bot, gap = 62, 78, 62, 30
        rows = []                                           # (tür, nesne, genişlik, yükseklik, üst)
        for i, (ln, sz) in enumerate(zip(lines, sizes)):
            if i == hl:
                lab = torn_label(ln, sz, OFF, RED, 85 + self.idx, rim=OFF)
                rows.append(("lab", lab, lab.w, lab.h, 0.0))
            else:
                l, t, r, b = tbox(ln, "anton", sz)
                rows.append(("txt", (ln, sz), tw(ln, "anton", sz), -t + max(0.0, b), -t))
        w = int(max(r[2] for r in rows) + 2 * pad_x)
        h = int(pad_top + sum(r[3] for r in rows) + gap * (len(rows) - 1) + pad_bot)
        sp = Sprite(w, h, 60)
        torn_paper(sp, 0, 0, w, h, OFF, 81 + self.idx, jitter=4, rim=WHITE, rim_w=3)
        y = pad_top
        for kind, obj, rw, rh, top in rows:
            if kind == "txt":
                sp.text((pad_x, y + top), obj[0], "anton", obj[1], INK)
            else:
                im = obj.render_ss(2.0, shadow=(4, 6, 0, 0.9))
                cx, cy = sp.p(pad_x - 8 + rw / 2, y + rh / 2)
                _comp(sp.im, im, cx - im.width / 2, cy - im.height / 2)
            y += rh + gap
        tp = Sprite(w, h, 60)
        tape(tp, 64, -4, 150, 44, -22, 82 + self.idx, alpha=225)
        tape(tp, w - 58, h - 2, 150, 44, -16, 83 + self.idx, alpha=225)
        tab = tr_upper("// dur bir saniye")
        tabw = tw(tab, "mono", 26) + 34
        tp.d.rounded_rectangle([*tp.p(w - tabw - 40, -24), *tp.p(w - 40, 24)], radius=14 * SS, fill=YELLOW,
                               outline=INK, width=4 * SS)
        tp.text((w - 40 - tabw / 2, 9), tab, "mono", 26, INK, anchor="ms")
        im = sp.render(-3.0, shadow=(12, 16, 0, 0.95))     # sert mürekkep gölge (Göz kartları)
        im.alpha_composite(tp.render(-3.0))
        im = im.crop(im.getchannel("A").point(lambda v: 255 if v > 4 else 0).getbbox())
        rx0, ry0, rx1, ry1 = CARD_REGION
        box = self.area
        bx0, by0, bx1, by1 = box[0] - 24, box[1] - 16, SAFE_X - 6, CARD_FLOOR - 4  # gölge ve bantlar dahil
        k = min(1.0, (bx1 - bx0) / im.width, (by1 - by0) / im.height)
        if k < 1:
            im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
        lay = Image.new("RGBA", (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
        cx, cy = (box[0] + box[2] + CARD_SH) / 2 - rx0, (by0 + by1) / 2 - ry0
        _comp(lay, im, cx - im.width / 2, cy - im.height / 2)
        self.sprite = lay
        # kart, kırmızı önceki kartı tamamen örttükten sonra (kenar kart tabanının ~22 px altındayken) gelir
        self.appear = 0.0 if self.hook else wipe_time(CLIP_FLOOR + 22)

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


def cta_sticker(text: str, max_w: float, size: int = 92) -> Image.Image:
    """'YORUMLARA YAZ ↓' çıkartması: kırmızı, mürekkep çerçeveli ve gölgeli, 2° eğik (1x RGBA; nasil.py de kullanır)."""
    ssz = size
    while tw(text, "anton", ssz) + 150 > max_w:
        ssz -= 4
    bw, bh = tw(text, "anton", ssz) + 150, ssz * 1.18
    sp = Pen(0, 0, bw + 30, bh + 30)
    sp.rr((10, 10, bw + 10, bh + 10), 14, fill=INK)
    sp.rr((0, 0, bw, bh), 14, fill=RED, outline=INK, width=4)
    cap = -tbox("H", "anton", ssz)[1]
    sp.text(36, bh / 2 + cap / 2, text, "anton", ssz, OFF)
    sp.svg(arrow_svg(OFF, 15, "down"), ICON_VB, bw - 100, bh / 2 - 38, 76)
    return sp.done().rotate(2.0, resample=Image.BICUBIC, expand=True)


def cta_pulse(lt: float) -> float:
    """Yorum çıkartmasının nabzı (ölçek): 0,4 sn durur, sonra 1,1 sn'lik dönemle %3,5 büyüyüp küçülür."""
    return 1.0 if lt < 0.4 else 1 + 0.035 * (0.5 - 0.5 * math.cos((lt - 0.4) * 2 * math.pi / 1.1))


class CtaCard(Card):
    """Son sahnenin soru kartı: soru, 'YORUMLARA YAZ' etiketi, kupon çizgisi ve kanal adı. Makas mutlu."""
    still = False
    BUTTON = "yorumlara yaz"
    GENERIC_Q = "Sen ne düşünüyorsun?"

    @classmethod
    def question(cls, label: str, narration: str, headline: list[str]) -> str:
        """Kartın soru satırı: card_label, yoksa dış sesteki ilk soru cümlesi, yoksa başlık. Düğmedeki 'YORUMLARA YAZ'
        sözünü içeren aday atlanır (aynı söz iki kez yazılmasın); hiçbiri kalmazsa genel bir soru."""
        phrase = re.compile(r"\byorumlara\s+yaz(ın|in)?\b[\s:,;.!—–-]*", re.I)

        def clean(s: str) -> str:
            s = (s or "").strip()
            t = phrase.sub("", s).strip(" :,;.!—–-")
            if t == s:
                return s
            # "Yorumlara yaz: sence hangisi doğru?" -> "Sence hangisi doğru?"; soru kalmadıysa aday düşer
            return tr_upper(t[:1]) + t[1:] if t.endswith("?") and len(t) > 3 else ""

        sents = re.split(r"(?<=[.?!])\s+", (narration or "").strip())
        cands = [label] + [s for s in sents if s.endswith("?")] + [" ".join(headline)]
        return next((c for c in map(clean, cands) if c), cls.GENERIC_Q)

    def __init__(self, ctx):
        super().__init__(ctx)
        q = self.q = self.question(self.c.get("label") or "", self.spec.narration, self.spec.headline)
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, self.area, "son / yorum.txt", tr_upper("soru"))
        cx = (ix0 + ix1) / 2
        qh = 222
        font, size, lines = fit_block(q, ("archivo",), ix1 - ix0 - 100, qh, 62, 38, lh=1.2, max_lines=3)
        lh = size * 1.2
        yb = iy0 + 30 + (qh - len(lines) * lh) / 2 + size * 0.92
        for L in lines:
            pen.text(cx, yb, " ".join(L), font, size, INK, anchor="ms")
            yb += lh
        # yorum etiketi (ayrı katman: hafifçe nabız atar)
        self.sticker = cta_sticker(tr_upper(self.BUTTON), ix1 - ix0 - 120)
        self.sticker_c = (cx, iy0 + 330)
        # kupon çizgisi + kanal adı
        ly = iy0 + 448
        x = ix0 + 110
        while x < ix1 - 40:
            pen.rr((x, ly - 2, min(x + 16, ix1 - 40), ly + 2), 2, fill=GREY)
            x += 26
        pen.svg(scissors_svg(30), SCISSORS_VB, ix0 + 30, ly - 25, 72)
        handle = self.ctx.get("handle") or ""   # marka kapalıysa kanal adı yazılmaz
        if handle:
            pen.text(cx, ly + 70, handle, "archivo", 44, INK, anchor="ms")
        self.base = pen.done()

    def layer(self, lt, dur):
        img = self.base.copy()
        k = cta_pulse(lt)
        st = self.sticker
        if k != 1.0:
            st = st.resize((int(st.width * k), int(st.height * k)), Image.BILINEAR)
        cx, cy = self.sticker_c
        _comp(img, st, cx - st.width / 2 - CARD_REGION[0], cy - st.height / 2 - CARD_REGION[1])
        return img

    def mood(self, lt, dur):
        return "happy"


class TextCard(Card):
    """Yedek kart (fotoğraf/çizim/veri yoksa): başlık satırları kartın içinde yırtık etiketlerde. Boyut, gerçek etiket
    ölçüleriyle (Türkçe şapka/çengel, iç boşluk, eğim, gölge) seçilir; etiketler başlık çubuğuna, çerçeveye ve nota
    taşmaz. label_box: etiket katmanının kart üzerindeki gerçek kutusu (denetim için)."""
    GAP, ROT = 14, 1.6
    SHADOW = (4, 7, 4, 0.25)

    def _labels(self, lines, size, hl):
        labs = []
        for i, ln in enumerate(lines):
            fg, bg = (INK, YELLOW) if i == hl else ((OFF, INK) if i % 2 == 0 else (INK, PAPER))
            labs.append(torn_label(ln, size, fg, bg, 300 + self.idx * 11 + i))
        return labs

    def static(self):
        pen = self.pen()
        ix0, iy0, ix1, iy1 = shell(pen, self.area, "not / makas.txt", tr_upper("not"))
        lines = [tr_upper(x) for x in self.spec.headline if x.strip()] or [tr_upper(self.spec.narration[:30])]
        hl = self.spec.highlight_line
        note = (self.c.get("note") or "").strip()
        top, bottom = iy0 + 24, iy1 - (96 if note else 24)     # etiketlerin (gölge dahil) sığacağı bant
        avail_h, maxw = bottom - top, ix1 - ix0 - 48
        sn = math.sin(math.radians(self.ROT))
        dx = (18, -10)                                         # tek/çift satırların yatay kaydırması
        size = 150
        while True:
            labs = self._labels(lines, size, hl)
            # eğik etiketin dikey payı (w·sinθ: yarısı üstte, yarısı altta) + yırtık kenar/lif şeridi + gölge
            total = sum(lb.h for lb in labs) + self.GAP * (len(labs) - 1)
            ext = (labs[0].w * sn / 2 + 6) + (labs[-1].w * sn / 2 + 6 + self.SHADOW[1] + self.SHADOW[2])
            widest = max(lb.w + lb.h * sn + 2 * abs(dx[i % 2]) + 12 for i, lb in enumerate(labs))
            if (total + ext <= avail_h and widest <= maxw) or size <= 44:
                break
            size -= 4
        y = max(top + labs[0].w * sn / 2 + 6, top + labs[0].w * sn / 2 + 6 + (avail_h - total - ext) / 2)
        y = min(y, bottom - total - (ext - labs[0].w * sn / 2 - 6))   # son etiketin altı (gölge dahil) bandı aşmasın
        cx = (ix0 + ix1) / 2
        lay = Pen(*CARD_REGION)
        for i, lb in enumerate(labs):
            im = lb.render_ss((-self.ROT if i % 2 else self.ROT * 0.9), shadow=self.SHADOW)
            iw, ih = im.width / SS, im.height / SS
            lay.paste(im, cx - iw / 2 + dx[i % 2], y + lb.h / 2 - ih / 2)
            y += lb.h + self.GAP
        lab_im = lay.done()
        bb = lab_im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        rx0, ry0 = CARD_REGION[:2]
        self.label_box = (bb[0] + rx0, bb[1] + ry0, bb[2] + rx0, bb[3] + ry0) if bb else None
        self.label_limits = (ix0, iy0, ix1, bottom)
        if note:
            pen.text(cx, iy1 - 40, fit(note, "mono", 28, ix1 - ix0 - 70), "mono", 28, DGREY, anchor="ms")
        img = pen.done()
        img.alpha_composite(lab_im)
        return img


CARD_CLASSES = {"photo": PhotoCard, "drawing": DrawingCard, "counter": CounterCard, "compare": CompareCard,
                "quote": QuoteCard, "interstitial": InterstitialCard, "cta": CtaCard, "receipt": ReceiptCard,
                "text": TextCard}


def series_cliff(narration: str) -> bool:
    """Serinin 1. bölümünün son sahnesi ("Devamı ikinci bölümde."): bu bölümde yorum çağrısı yoktur (script.py
    SERİ KURALI), son sahne yorum kartı olmaz."""
    return bool(re.search(r"\bdevamı\s+(ikinci|2\.)\s+bölüm", tr_lower(narration or "")))


def card_type(spec, idx: int, n: int) -> str:
    """Sahnenin kart türü. Açık seçim (card) veriyle destekleniyorsa geçerli; 'auto' için: son sahne cta,
    'AMA ASIL…'/'ASIL…' başlık interstitial, card_lines (hesap fişi satırları) receipt, card_value counter,
    card_myth+card_fact compare, sonra fotoğraf, çizim, yoksa yazı kartı. quote yalnız açıkça istenince (card_label
    sayaç etiketi de olabildiği için)."""
    c = spec.card or {}
    has_photo, has_drawing = spec.image is not None, spec.sprite is not None
    data = {"receipt": bool(parse_receipt(c.get("lines"))), "counter": bool((c.get("value") or "").strip()),
            "compare": bool((c.get("myth") or "").strip() and (c.get("fact") or "").strip()),
            "quote": bool((c.get("label") or "").strip()), "photo": has_photo, "drawing": has_drawing,
            "cta": True, "interstitial": True, "text": True}
    want = c.get("type") or "auto"
    if want in data and data[want]:
        return want
    head = tr_upper(" ".join(spec.headline)).strip()
    if want == "auto":
        if idx == n - 1 and n > 1 and not series_cliff(spec.narration):
            return "cta"
        if head.startswith("AMA ASIL") or head.startswith("ASIL "):
            return "interstitial"
        if data["receipt"]:
            return "receipt"
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
    """Koyu terminal: makas@bilgimakasi:~/konu, son iki kayıt satırı (32 px, sığmayan satır kelime sınırında '…' ile
    kesilir), sahne/sahne sayısı kadar kesilmiş çizgi."""
    REGION = (52, 1288, 620, 1536)
    FS, TITLE_FS = 32, 28            # telefonda (390 px) ~11,5 px: okunur; başlık sığsın diye 28
    LY1, LY2 = 108, 152              # kayıt satırlarının taban çizgileri (TERM üstüne göre)

    def __init__(self, handle: str, topic_slug: str, logs: list[str], n: int):
        self.handle, self.logs, self.n = handle, logs, n
        x0, y0, x1, y1 = TERM
        head = "makas" + handle          # kullanıcı adı yoksa "makas:~/konu"
        rest = fit(f":~/{topic_slug}", "mono", self.TITLE_FS, x1 - x0 - 48 - tw(head, "mono", self.TITLE_FS))
        self.title = (head, rest)
        self.prompt_w = tw("$ ", "mono", self.FS)
        self._static: dict = {}
        self._dyn: dict = {}

    def static(self, i: int, dark: bool) -> Image.Image:
        key = (i, dark)
        if key not in self._static:
            x0, y0, x1, y1 = TERM
            pen = Pen(*self.REGION)
            pen.rr((x0 + 10, y0 + 10, x1 + 10, y1 + 10), 20, fill=YELLOW if dark else RED)
            pen.rr(TERM, 20, fill=INK, outline=INK, width=4)
            fs, tf = self.FS, self.TITLE_FS
            a, b = self.title
            pen.text(x0 + 24, y0 + 42, "makas", "mono", tf, OFF)
            if self.handle:
                pen.text(x0 + 24 + tw("makas", "mono", tf), y0 + 42, self.handle, "mono", tf, YELLOW)
            pen.text(x0 + 24 + tw(a, "mono", tf), y0 + 42, b, "mono", tf, TERM_TXT)
            pen.rr((x0 + 4, y0 + 60, x1 - 4, y0 + 62), 0, fill=(52, 50, 49))
            if i > 0:
                ly = y0 + self.LY1
                pen.svg(check_svg(YELLOW, 17), ICON_VB, x0 + 18, ly - 29, 34)
                pen.text(x0 + 24 + self.prompt_w, ly,
                         fit_words(self.logs[i - 1], "mono", fs, x1 - x0 - 48 - self.prompt_w), "mono", fs, OFF)
            by = y1 - 30
            bx0, bx1 = x0 + 28, x1 - 142
            x = bx0
            while x < bx1:
                pen.rr((x, by - 2.5, min(x + 10, bx1), by + 2.5), 2.5, fill=TERM_DIM)
                x += 18
            self._static[key] = pen.done()
        return self._static[key]

    def layer(self, i: int, lt: float, dark: bool, hook: bool) -> Image.Image:
        x0, y0, x1, y1 = TERM
        fs = self.FS
        line = fit_words(self.logs[i], "mono", fs, x1 - x0 - 48 - self.prompt_w - 22)
        n_ch = len(line) if hook else int(clamp((lt - 0.08) / 0.022, 0, len(line)))
        cur_on = n_ch < len(line) or int(lt * 2.2) % 2 == 0
        a, b = i / self.n, (i + 1) / self.n
        frac = b if hook else lerp(a, b, ease_out_cubic(lt / 0.45))
        bx0, bx1 = x0 + 28, x1 - 142
        hx = round(lerp(bx0, bx1, frac))
        full = frac >= 0.999
        key = (i, n_ch, cur_on, hx, full, dark)   # full anahtarda: sarı/kırmızı çubuk önbellekte karışmasın
        if key in self._dyn:
            return self._dyn[key]
        img = self.static(i, dark).copy()
        pen = Pen(*self.REGION)
        ly = y0 + (self.LY2 if i > 0 else self.LY1)
        pen.text(x0 + 24, ly, "$", "mono", fs, RED)
        shown = line[:n_ch]
        pen.text(x0 + 24 + self.prompt_w, ly, shown, "mono", fs, OFF)
        if cur_on:
            cx = x0 + 24 + self.prompt_w + tw(shown, "mono", fs) + (6 if shown else 0)
            pen.rr((cx, ly - 25, cx + 15, ly + 5), 2, fill=YELLOW)
        by = y1 - 30
        if hx > bx0 + 1:
            pen.rr((bx0, by - 5, hx, by + 5), 5, fill=YELLOW if full else RED)
        pen.text(x1 - 24, by + 10, f"{i + 1:02d}/{self.n:02d}", "mono", 28, YELLOW if full else OFF, anchor="rs")
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
_HEAD = dict(x=-98, y=-30, w=196, h=188, r=16, teeth=7, tooth_h=12)   # köşeli kâğıt parçası, üst kenar yırtık
_EYES = [(-60, 30, 1.0), (60, 19, 0.80)]   # bilerek simetrik değil: sağ göz belirgin küçük ve 11 px yukarıda
_RING_TIP = 1.36                           # halkalar pime bakan damla biçimli makas sapları (sivri uç sapa bağlanır)
_TILT = -6
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
    rng = random.Random(23)                 # yırtık üst kenar: sabit tohum, her karede aynı
    d = f"M{P(x0, y0 + r)} A{r} {r} 0 0 1 {P(x0 + r, y0)} "
    x = x0 + r + 9
    while x < x1 - r - 4:
        d += f"L{P(x, y0 + rng.uniform(-3.8, 3.2))} "
        x += rng.uniform(7, 12)
    d += f"L{P(x1 - r, y0)} A{r} {r} 0 0 1 {P(x1, y0 + r)} L{P(x1, yb)} "
    w_ = (x1 - x0) / n
    for i in range(n):
        xa = x1 - i * w_
        d += f"L{P(xa - w_ / 2, y1)} L{P(xa - w_, yb)} "
    return d + "Z"


def _ring_d(ex, ey, R) -> str:
    """Damla biçimli makas sapı: (ex, ey) merkezli R yarıçaplı halka, sivri ucu pime bakar."""
    ux, uy = _PIVOT[0] - ex, _PIVOT[1] - ey
    n = math.hypot(ux, uy)
    ux, uy = ux / n, uy / n
    tip = (ex + ux * R * _RING_TIP, ey + uy * R * _RING_TIP)
    phi = math.acos(1 / _RING_TIP)
    base = math.atan2(uy, ux)
    p1 = (ex + R * math.cos(base + phi), ey + R * math.sin(base + phi))
    p2 = (ex + R * math.cos(base - phi), ey + R * math.sin(base - phi))
    return f"M{P(*p1)} A{R:.2f} {R:.2f} 0 1 1 {P(*p2)} L{P(*tip)} Z"


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
            g += f'<path d="{_ring_d(ex, ey, 58 * rs * es)}" {st}/>'
        g += f'<circle cx="{_PIVOT[0]}" cy="{_PIVOT[1]}" r="13" {st}/>'
        return g

    out = f'<g transform="rotate({_TILT} 0 60)">'
    out += f'<g transform="translate({_SHADOW[0]} {_SHADOW[1]})">{silhouette(ink, 2 * _DIECUT)}</g>'
    out += silhouette(white, 2 * _DIECUT)
    out += f'{head} fill="{yel}" stroke="{ink}" stroke-width="{_OUT}" stroke-linejoin="round"/>'
    if E.get("blush"):                     # yanak yalnız ifadeye bağlı (hece hece yanıp sönmesin)
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
        g += f'<path d="{_ring_d(ex, ey, R)}" fill="{red}" stroke="{ink}" stroke-width="{_OUT}" stroke-linejoin="round"/>'
        a0, a1 = math.radians(200), math.radians(245)
        rm = (R + Sr) / 2
        g += (f'<path d="M{P(ex + rm * math.cos(a0), ey + rm * math.sin(a0))} A{rm} {rm} 0 0 1 '
              f'{P(ex + rm * math.cos(a1), ey + rm * math.sin(a1))}" stroke="{white}" stroke-width="5" '
              'stroke-linecap="round" fill="none" opacity="0.7"/>')
        g += f'<circle cx="{ex}" cy="{ey}" r="{Sr}" fill="{white}" stroke="{ink}" stroke-width="{_OUT}"/>'
        pr = E["pupil"] * (0.88 if i else 1.0)
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
    if mouth in ("open", "closed"):         # konuşurken ağız ifadeyi korur (şaşkın 'o', düşünceli 'hmm')
        m = {"surprised": {"open": "o_big", "closed": "o_small"},
             "thinking": {"open": "oval", "closed": "hmm"}}.get(mood, {}).get(mouth, mouth)
    else:
        m = E["mouth"]
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
    elif m in ("o", "o_big", "o_small"):
        rx, ry = {"o": (14, 17), "o_big": (17, 22), "o_small": (10, 12)}[m]
        out += f'<ellipse cx="{mx}" cy="{my + 2}" rx="{rx}" ry="{ry}" fill="{ink}" {ms}/>'
    elif m == "oval":
        out += (f'<ellipse cx="{mx + 9}" cy="{my + 1}" rx="10" ry="13" fill="{ink}" {ms} '
                f'transform="rotate(14 {mx + 9} {my + 1})"/>')
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


def talk_state(words: list[Word], starts: list[float], t: float) -> str:
    """Makas'ın ağzı: o an okunan kelimenin hecesine göre 'open'/'closed', sessizlikte 'rest' (nasil.py de kullanır)."""
    if not words:
        return "rest"
    i = bisect.bisect_right(starts, t) - 1
    if i < 0:
        return "rest"
    w = words[i]
    if t >= w.end:
        return "rest"
    letters = sum(ch.isalnum() for ch in w.text)
    n = max(1, round(letters / 2.6))
    ph = (t - w.start) / max(0.05, w.end - w.start) * n
    return "open" if (ph % 1.0) < 0.55 else "closed"


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
# "olsaydin" serisinin adı geçici (sahibi seçiyor): ekrandaki adı kalıp listesinden (script.STRUCTURES) gelir;
# ilk sahnenin format etiketi (pipeline.series_label) de aynı yerden okur
OLSAYDIN_ADI = STRUCTURES["olsaydin"][0]
STRUCT_RIGHT = {"efsane": "EFSANE Mİ?", "neden": "NEDEN?", "nasil": "NASIL?", "uretim": "NASIL ÜRETİLİYOR?",
                "olsaydin": OLSAYDIN_ADI}


def short_name(topic: str, max_w: float) -> str:
    """Başlıktaki kısa konu adı: konunun sığan ilk kelimeleri (kelime ortasından kesmeden)."""
    words = tr_lower(re.sub(r"[\"“”'’?!.,:;]", "", topic or "")).split()
    out = ""
    for w in words:
        nxt = (out + " " + w).strip()
        if tw(nxt, "mono", HEADER_SIZE) > max_w and out:
            break
        out = nxt
    return fit(out, "mono", HEADER_SIZE, max_w) if out else "bilgi"


def cover_layer(kicker: str, stamp: str, note: bool = False, box=CARD0) -> Image.Image | None:
    """Kapak (sahne 0) kartının üstü: seri etiketi kartın üst kenarına yapışmış büyük sarı yırtık etiket (Anton, en az
    44 px) ve fotoğraflı/çizimli kartta başlığın vurgulu satırı kırmızı yırtık damga. Kapak karesi tek başına okunur."""
    if not kicker and not stamp:
        return None
    rx0, ry0, rx1, ry1 = CARD_REGION
    lay = Image.new("RGBA", (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
    if stamp:
        size = 128
        while tw(stamp, "anton", size) + size * 0.4 > 660 and size > 64:
            size -= 4
        lab = torn_label(stamp, size, OFF, RED, 4242, rim=OFF)
        im = lab.render(4.0, shadow=(7, 10, 0, 0.92))
        cx, cy = (box[0] + box[2]) / 2 + 24, box[3] - (240 if note else 150)   # not çipinin üstünde
        _comp(lay, im, cx - im.width / 2 - rx0, cy - im.height / 2 - ry0)
    if kicker:
        size = 52
        while tw(kicker, "anton", size) + size * 0.4 > 620 and size > 44:
            size -= 2
        lab = torn_label(kicker, size, INK, YELLOW, 4343, rim=OFF)
        im = lab.render(2.5, shadow=(5, 7, 0, 0.92))
        cx, cy = box[0] + 14 + lab.w / 2, box[1] + 34   # üst kenar ≈ kart üstü - 25 (kapakta ≈ 515): kinetik yazının,
        # vuruşunun ve açılış zıplamasının (ilk 0,5 sn, en çok 7 px yukarı) altında
        _comp(lay, im, cx - im.width / 2 - rx0, cy - im.height / 2 - ry0)
    return lay


def card_cut(img: Image.Image, old: Image.Image, local: float, seed: int, origin=None, card=CARD,
             x_end: float = SAFE_X - 66, clip_top=None, clips_bot=None) -> None:
    """Makas kesme geçişi: eski kart makasla ikiye kesilir (CUT_SLICE), parçalar tam opak ayrılır (CUT_SPLIT: üst
    parça sola-yukarı ~70 px kayıp 3° döner, alt parça menteşeli gibi düşer: sol ucu ~35 px, maskotun üstündeki sağ ucu
    ≤ 6 px, böylece bıçak uçlarına inmez), sonra en çok 2 karede söner; altta yeni kart durur. Ayrılmadan sönen
    parçalar çift pozlama gibi okunuyordu. Varsayılanlar kart şablonunun yerleşimidir; nasil.py kendi kart kutusunu,
    katman kökenini (origin) ve kırpma kutularını verir."""
    rx0, ry0 = origin if origin is not None else CARD_REGION[:2]
    lw, lh = old.size
    ang = math.radians(6 if seed % 2 else -6)
    cy = (card[1] + card[3]) / 2 - ry0
    yl, yr = cy - math.tan(ang) * lw / 2, cy + math.tan(ang) * lw / 2
    p_cut = clamp(local / CUT_SLICE)
    sx = lerp(card[0] - rx0 - 40, x_end - rx0, ease_in_out(p_cut))
    e = ease_out_cubic((local - CUT_SLICE) / CUT_SPLIT) + 0.25 * clamp((local - CUT_SLICE - CUT_SPLIT) / CUT_FADE)
    a = 1 - clamp((local - CUT_SLICE - CUT_SPLIT) / CUT_FADE)
    if a <= 0:
        return
    mask = Image.new("L", old.size, 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (lw, 0), (lw, yr), (0, yl)], fill=255)
    top = Image.new("RGBA", old.size, (0, 0, 0, 0))
    top.paste(old, (0, 0), mask)
    bot = Image.new("RGBA", old.size, (0, 0, 0, 0))
    bot.paste(old, (0, 0), ImageChops.invert(mask))
    clip = clip_top if clip_top is not None else (0, SAFE[1], SAFE[2], CLIP_FLOOR)
    bx, by = rx0, ry0 + 20 * e
    tx, ty = rx0 - 60 * e, ry0 - 36 * e
    if e > 0.01:
        r = bot.rotate(2.3 * e, resample=Image.BICUBIC, expand=True)    # sağ uç yukarıda kalır
        bx, by = bx - (r.width - lw) / 2, by - (r.height - lh) / 2
        bot = r
        r = top.rotate(-3.0 * e, resample=Image.BICUBIC, expand=True)   # sol uç kalkar
        tx, ty = tx - (r.width - lw) / 2, ty - (r.height - lh) / 2
        top = r
    # kartta: düşen sol uç terminalin üstüne kadar inebilir; maskot bandında (x ≥ 600) bıçak uçlarının (y ≥ 1154)
    # üstünde kalır
    for cb in (clips_bot if clips_bot is not None else
               ((0, SAFE[1], 600, TERM[1] - 16), (600, SAFE[1], SAFE[2], CLIP_FLOOR + 14))):
        put(img, bot, bx, by, alpha=a, clip=cb)
    put(img, top, tx, ty, alpha=a, clip=clip)
    if p_cut < 1:
        dd = ImageDraw.Draw(img)
        x = card[0] - 30
        while x < sx + rx0:
            xe = min(x + 22, sx + rx0)
            ya = ry0 + yl + (yr - yl) * ((x - rx0) / lw)
            yb = ry0 + yl + (yr - yl) * ((xe - rx0) / lw)
            dd.line([(x, ya), (xe, yb)], fill=INK, width=4)
            x += 34
        sc = scissors_icon(110, 34 if int(local * 30) % 2 else 14, rot=-math.degrees(ang))
        yy = ry0 + yl + (yr - yl) * (sx / lw)
        put(img, sc, rx0 + sx - sc.width * 0.45, yy - sc.height / 2)


class KartScene:
    def __init__(self, video: "KartVideo", i: int):
        v = video
        self.i = i
        s = v.scenes[i]
        self.spec = s
        self.dur = max(0.1, s.end - s.start)
        self.type = v.types[i]
        self.dark = self.type == "interstitial"
        # kapak sahnesinin kartı biraz aşağıda (CARD0): üstündeki uzun kinetik bantla (KIN0) çakışmaz
        ctx = {"spec": s, "idx": i, "dur": self.dur, "slug": v.slug, "handle": v.handle,
               "box": CARD0 if i == 0 else CARD}
        self.card = CARD_CLASSES[self.type](ctx)
        self.cover = None
        if i == 0 and not self.dark:
            lines = [tr_upper(x.strip()) for x in s.headline if x.strip()]
            hl = s.highlight_line if 0 <= s.highlight_line < len(lines) else len(lines) - 1
            stamp = lines[hl] if (lines and self.type in ("photo", "drawing")) else ""
            self.cover = cover_layer(tr_upper((s.kicker or "").strip()), stamp, self.card.has_chip, self.card.area)
        self._cov_src = self._cov = None
        kind = "count" if v.structure == "sayac" else "text"
        right = v.right_label(i)
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

    def card_layer(self, lt: float) -> Image.Image | None:
        """Kartın o anki katmanı; kapakta seri etiketi ve damga üstünde (aynı kart görüntüsü için önbellekli)."""
        lay = self.card.layer(lt, self.dur)
        if self.cover is None or lay is None:
            return lay
        if lay is not self._cov_src:
            self._cov_src = lay
            self._cov = lay.copy()
            self._cov.alpha_composite(self.cover)
        return self._cov


class KartVideo:
    def __init__(self, scenes, words: list[Word], meta: dict, bcfg: dict):
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        self.n = n = len(scenes)
        on = bcfg.get("enabled", False)
        self.intro = bool(on and bcfg.get("intro_cut", True))
        # kullanıcı adı render.render'daki gibi brand.json'a uyar (marka kapalıysa ya da subtitle_handle false ise yok)
        self.handle = (bcfg.get("handle") or "") if on and bcfg.get("subtitle_handle", True) else ""
        self.structure = self.meta.get("structure", "")
        # kısa konu adı her sahnenin başlığına (sağdaki etiketin yanına) sığmalı
        right_w = max(tw(tr_upper(self.right_label(i)), "mono", HEADER_SIZE) for i in range(n)) if n else 200
        name_w = 920 - min(440, right_w) - HEADER_ICON - 12 - 40 - (72 + tw("// 01 — ", "mono", HEADER_SIZE))
        self.short = short_name(self.meta.get("short") or self.meta.get("topic") or "", name_w)
        self.slug = ""
        for part in slug(self.short, 60).split("-"):
            if len(self.slug) + len(part) + 1 > 15 and self.slug:
                break
            self.slug = (self.slug + "-" + part).strip("-")
        self.slug = self.slug or "bilgi"
        self.types = [card_type(s, i, n) for i, s in enumerate(scenes)]
        # makas kesme geçişi: brand.json cut_transition_every > 0 iken (0 her şablonda kapatır) kart şablonunda
        # kart_kesme_her sahnede bir (varsayılan 3: kart sahneleri kısa olduğundan diğer şablonlardaki 4 yerine 3).
        # Ara kanca ya da ara kancadan hemen sonraki sahneye düşerse bir sonraki uygun sahneye kayar.
        self.cut_at: set[int] = set()
        every = int(bcfg.get("kart_kesme_her", CUT_EVERY) or 0)
        if on and int(bcfg.get("cut_transition_every", 4) or 0) > 0 and every > 0:
            ok = [i > 0 and "interstitial" not in (self.types[i], self.types[i - 1]) for i in range(n)]
            i = every
            while i < n:
                while i < n and not ok[i]:
                    i += 1
                if i < n:
                    self.cut_at.add(i)
                i += every
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
        if self.structure in ("nasil", "uretim"):  # adım/aşama sahnesinde numara (headline 'ADIM 2' / 'AŞAMA 2')
            m = re.match(r"(?:ADIM|AŞAMA) \d+", tr_upper(" ".join((self.scenes[i].headline or [""])[:1])).strip())
            if m:
                return m.group(0)
        if self.structure in STRUCT_RIGHT:
            return STRUCT_RIGHT[self.structure]
        kicker = (self.scenes[0].kicker or "").strip()
        return kicker if (kicker and i > 0) else "BİLGİ MAKASI"  # ilk sahnede seri etiketi kartın üstünde

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
        if t == "receipt":
            total = (c.get("value") or "").strip()
            if not total:
                return "hesap basılıyor"
            return tr_lower(f"hesap: {(c.get('label') or 'toplam').strip()} {total}")
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
            if 0 <= x < 1 and hi > 0:   # ilk kelime zıplamaz: t=0 kapak karesidir, değişen bir şey yok
                k = 1 + self.kin.pop(ci) * (1 - x) ** 2
            put(img, cur_im, cur_c[0] - cur_im.width / 2, cur_c[1] - cur_im.height / 2, k=k)

    def _talk(self, t: float) -> str:
        return talk_state(self.words, self.starts, t)

    def _mascot(self, img: Image.Image, t: float, sc: KartScene, lt: float) -> None:
        mood = sc.mood(lt)
        mouth = self._talk(t)
        blink = (t % 3.6) > 3.45 and mood not in ("happy", "surprised")
        im, (x, y) = self.mascot.sprite(mood, mouth, blink)
        bob = round(3 * math.sin(t * 2 * math.pi * 0.55))
        put(img, im, x, y + bob)

    def _wipe_mask(self, lt: float) -> Image.Image:
        """Kırmızı yukarıdan iner; ön kenarı küçülen yarım ton noktalara dağılır. Kenar ve noktalar yalnız görünür
        bantta (y 232→1540) hareket eder: başta üstü (y < 232) dolu başlar, platform arayüzünün altına (y > 1540) hiç
        inmez; son silme karesinde ekran tamamen düz kırmızıdır (terminal ve maskotun arkasında yarım ton
        kalmaz)."""
        band, sp = 300, 34
        e = wipe_edge(lt)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rectangle([0, 0, W, int(e)], fill=255)
        bh = int(min(band + sp, WIPE_Y1 - (int(e) - sp // 2)))
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

    def _cut(self, img: Image.Image, old: Image.Image, local: float, seed: int) -> None:
        card_cut(img, old, local, seed)

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
        elif sc.dark and si > 0 and lt < WIPE - 1 / FPS:   # son silme karesi (ve sonrası) düz kırmızı taban
            img = paper_bg().copy()  # kırmızı, önceki kartın üstünden aşağı doğru iner
            prev = self.scene(si - 1)
            if not prev.dark:
                put(img, prev.card_layer(prev.dur), *CARD_REGION[:2], clip=(0, SAFE[1], SAFE[2], CLIP_FLOOR))
            img.paste(red_bg(), (0, 0), self._wipe_mask(lt))
            img.alpha_composite(sc.header, HEADER_REGION[:2])
            img.alpha_composite(rule_layer(True), (0, RULE_Y - 6))
        else:
            img = sc.base.copy()
        if si == 0 and self.intro:
            self._intro(img, t, sc.dark)
        # kart
        layer = sc.card_layer(lt)
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
        elif si in self.cut_at and lt < CUT_LEN and self.types[si - 1] != "interstitial":
            put(img, layer, rx0, ry0, clip=clip)
            prev = self.scene(si - 1)
            self._cut(img, prev.card_layer(prev.dur), lt, si)
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
    return render_frames(scenes, words, out_mp4, voice_mp3, music,
                         lambda bcfg: KartVideo(scenes, words, meta, bcfg), "Kart")


def render_frames(scenes: list[render.SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
                  music: Path | None, make_video, name: str) -> Path:
    """Kart ve nasil şablonlarının ortak kare döngüsü: make_video(bcfg) .frame(t) veren nesneyi kurar; içerik son
    sözden sonra brand.json'daki end_tail_seconds kadar (kapanış kartı açıksa 0,7 sn) sürer, ardından marka kapanış
    kartı (outro_seconds) gelir. Kareler ffmpeg'e yazılır, ses render.mux ile eklenir."""
    from .brand import Brand, load_config
    t_begin = time.perf_counter()
    bcfg = load_config()
    brand = Brand(bcfg, {})
    outro = bcfg.get("outro_seconds", 0.0) if brand.on else 0.0
    tail = bcfg.get("end_tail_seconds", 1.6)
    content_end = (words[-1].end if words else scenes[-1].end) + (0.7 if outro else tail)
    total = content_end + outro
    scenes[-1].end = content_end
    video = make_video(bcfg)
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
    print(f"{name}: {n} kare, {el:.1f} sn ({el / max(1, n) * 1000:.0f} ms/kare)")
    return out_mp4
