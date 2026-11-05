"""Ya Sen Olsaydın? şablonu ("Ajanda"): açık bir ajanda sayfası, tükenmez kalemle elle yazılan gün akışı ya da hesap
ve para konularında altta büyük sarı bir masa hesap makinesi.

Dünya: krem ajanda kâğıdı, açık mavi satır çizgileri, solda basılı saat sütunu, üstte bugünün basılı tarihi (gün,
ay, hafta günü, hafta ve yılın günü), sağ kenarda kırmızı kurdele (yalnız arka plan; düğme sütununun altında kalır).
Serinin tek ek rengi TÜKENMEZ MAVİSİ: el yazısı, kalem işaretleri, sayfa çizgileri. Marka kimliği korunur:
kırmızı/sarı/mürekkep/kâğıt, Anton + Courier Prime Bold, yırtık etiketler, sert gölgeler, kâğıt greni, Makas,
hareketli filigran.

Ekran düzeni (1080x1920). Yazı yalnız x 72-920, y 236-1536 arasında; gölgeler dahil hiçbir öğe platform arayüzüne
(sağdaki düğmeler x > 935, üst çubuk y < 170, alttaki açıklama y > 1540) taşmaz (filigran 120-228'de):
  236-326   basılı tarih satırı: büyük kırmızı gün, ay yıl / hafta günü, sağda HAFTA · GÜN; altında çift çizgi
  336-404   seri etiketi (siyah yırtık "YA SEN OLSAYDIN?") ........ DURAK 2/4 ☑ ◯ ☐ ☐ (elle çizilmiş kutular)
  440-618   sahnenin başlığı (Anton); SEN / SANA / SENİN kelimesi mavi tükenmezle halkalanır (serinin imzası),
            vurgulu satırın altından sarı fosforlu kalem geçer. Sağda Makas (x 720-920) başlığı ve sayfayı gösterir.
  632-728   dış ses: Courier, okunan kelimenin altından fosforlu kalem geçer (sessiz izleyen de okur)
  760-1528  sayfa: gün akışında saat çizgileri; her durak kendi saatinin çizgisine elle yazılır ("07:30" kırmızı,
            olay mavi), önceki duraklar sayfada kalır ve tiklenir (gün dolar). Sahnenin çizimi ya da fotoğrafı sağda
            bantlı bir polaroid olur (fotoğrafta künye çipi polaroidin alt boşluğunda). İçeriden bilgi ya da alıntı
            sayfaya yapıştırılmış sarı yapışkan nottur ("İÇERİDEN"; dış ses notun üstüne kelime kelime yazılır).
  1096-1532 yalnız para konularında: sarı masa hesap makinesi "MAKAS-12"; LCD yürüyen toplamı gösterir (sayaç
            sahnesinde card_value tuşlanır, fiş sahnesinde her satır eklenir, sonda = ile toplam). Para yoksa makine
            çizilmez, sayfa günü yazar.
Son sahne: "SEN OLSAN NE YAPARDIN?" (SEN halkalı), boş, elle çizilmiş bir liste, sayfada duran bir tükenmez kalem ve
"Yorumlara yaz" söylenince patlayan YORUMLARA YAZ ↓ etiketi.

Senaryo eşlemesi (pipeline.build spec.card'a sahnenin bütün alanlarını koyar): ilk sahne kanca, son sahne cta;
kicker'ı saat olan ("07:30", "7.30") sahneler gün akışının durakları, card counter / receipt sahneleri hesap
durakları (kart.card_type ile aynı kural), interstitial / quote sahneleri içeriden notu; diğer sahneler gün akışında
önceki durağın devamıdır (başlığı durağın altına küçük not olarak yazılır).

Hız: sayfa, tarih ve hesap makinesi gövdesi video başına; başlık, el yazısı satırları, polaroid ve notlar sahne
başına; kalem işaretleri ilerleme adımı başına önbelleğe alınır. Kare başına yalnız katmanlar birleştirilir.
Rastgelelik metin ve sahne numarasıyla tohumlanır: aynı videonun kareleri her çalıştırmada aynıdır.
"""
from __future__ import annotations

import bisect
import datetime as dt
import math
import random
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from . import kart as K
from . import nasil as N
from .render import SceneSpec
from .script import STRUCTURES, para_var, tutar
from .voice import Word

W, H, FPS, SS = K.W, K.H, K.FPS, K.SS
RED, YELLOW, INK, OFF, WHITE, DGREY = K.RED, K.YELLOW, K.INK, K.OFF, K.WHITE, K.DGREY

# ---------------------------------------------------------------- serinin rengi ve sayfa tonları
MAVI = (27, 64, 158)                 # tükenmez kalem mavisi: serinin tek ek rengi
MAVI_CIZGI = (190, 204, 232)         # ajanda çizgileri (aynı mavinin açığı)
MAVI_SOLUK = (128, 150, 196)         # basılı saat sütunu
SAYFA = (248, 245, 236)              # ajanda kâğıdı (marka kâğıdının sıcak açığı)
SONUK = (150, 146, 138)              # dış seste sıradaki kelimeler
FOSFOR = (253, 226, 74)              # fosforlu kalem (vurgu sarısının kâğıtta biraz açılmış hâli)
LCD_BG, LCD_GHOST, LCD_INK = (201, 205, 190), (189, 193, 178), (30, 32, 29)
POLAROID = (252, 251, 247)

# ---------------------------------------------------------------- yerleşim
X0, X1 = 72, 920                     # yazı alanı
SAFE = K.SAFE                        # (0, 170, 935, 1540)
CLIP = (0, SAFE[1], SAFE[2], SAFE[3])
TARIH_BASE, TARIH_CIZGI = 298, 316   # basılı tarih satırının taban çizgisi ve altındaki çift çizgi
SIRA_CY = 370                        # seri etiketi + DURAK satırının ortası
BAS_Y0, BAS_Y1 = 440, 618            # başlık bloğu (ilk satırın büyük harf üstü .. son satırın altı)
BAS_X1 = 700                         # başlık ve dış ses sağda Makas'a yer bırakır
ANLATI = (X0, 632, BAS_X1, 728)      # dış ses kutusu
ICERIK_Y0 = 780                      # sayfanın ilk içerik çizgisi (gün akışında ilk durağın saati)
ICERIK_Y1 = 1528                     # içeriğin alt sınırı (para yokken)
CIZGI_UST = 404                      # sayfa çizgilerinin başladığı yer
MAKAS_XY, MAKAS_OLCEK = (834, 552), 0.5
POINT = 212.0                        # Makas'ın kolu: sol-yukarı (başlığı gösterir)
CALC_W, CALC_H = 838, 410            # hesap makinesi (yerel; eğik ve gölgeli hâli x ≤ 935)
CALC_X, CALC_Y, CALC_ROT = X0, 1098, -1.4
CALC_TOP = CALC_Y - 14               # makinenin (eğim dahil) en üst noktası: içerik bunun üstünde biter
LCD_BOX = (44, 96, CALC_W - 44, 262)
TUSLAR = ("AC", "÷", "×", "−", "+", "=")
SEN_RE = re.compile(r"^(SEN|SANA|SENİ|SENİN|SENDE|SENDEN|SENCE|SENİNLE|SENİNKİ|SENİNKİNİ)\W*$")
SAAT_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)(?!\d)")
YORUM_RE = re.compile(r"\byorumlara\s+yaz", re.I)
SORU_RE = re.compile(r"^sen$", re.I)
AYLAR = ("OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK")
GUNLER = ("PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR")
SERI_ADI = STRUCTURES["olsaydin"][0]  # "YA SEN OLSAYDIN?" (kalıp listesinden: ad değişirse burası da değişir)
CTA_BASLIK = ["SEN OLSAN", "NE YAPARDIN?"]
CUT = K.CUT_LEN                      # makas kesmesi (kart şablonuyla aynı süre)
YENI0 = K.CUT_SLICE + K.CUT_SPLIT     # yeni başlığın belirdiği an: makas eskisini kesip parçalar ayrılınca


def up(s: str) -> str:
    return K.tr_upper((s or "").strip())


def cap_h(font: str, size: float) -> float:
    return N.cap_h(font, size)


def tohum(*parts) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode("utf-8"))


def cumle(s: str) -> str:
    """BÜYÜK HARF başlığı ajanda yazısına çevirir: 'İLK ARIZA' -> 'İlk arıza' (Türkçe i/ı korunur)."""
    s = re.sub(r"\s+", " ", (s or "").strip())
    if not s:
        return ""
    low = K.tr_lower(s)
    return K.tr_upper(low[0]) + low[1:]


def turkce_tarih(gun: dt.date) -> tuple[str, str, str, str]:
    """('05', 'KASIM 2026', 'PERŞEMBE', 'HAFTA 45 · GÜN 309')"""
    return (f"{gun.day:02d}", f"{AYLAR[gun.month - 1]} {gun.year}", GUNLER[gun.weekday()],
            f"HAFTA {gun.isocalendar()[1]} · GÜN {gun.timetuple().tm_yday}")


def saat_of(kicker: str) -> tuple[str, int] | None:
    """kicker'daki saat: ('07:30', 450 dakika) ya da None."""
    m = SAAT_RE.search(kicker or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{mi:02d}", h * 60 + mi


# ---------------------------------------------------------------- tükenmez kalem: el yazısı ve işaretler
_GLYPH: dict = {}


def _glyph(ch: str, face: str, px: int):
    """Tek harfin maske görüntüsü (SS ölçeğinde), taban çizgisi ve mürekkep sınırları (önbellekli)."""
    key = (ch, face, px)
    if key not in _GLYPH:
        f = K.fnt(face, px)
        pad = int(px * 0.5)
        w = int(f.getlength(ch)) + 2 * pad
        h = int(px * 1.9)
        by = int(px * 1.3)
        im = Image.new("L", (max(1, w), h), 0)
        ImageDraw.Draw(im).text((pad, by), ch, font=f, fill=255, anchor="ls")
        bb = im.getbbox()
        il, ir = (bb[0], bb[2]) if bb else (pad, pad + int(f.getlength(ch)))
        _GLYPH[key] = (im, by, il, ir)
    return _GLYPH[key]


class Yazi:
    """Tükenmez kalemle elle yazılmış tek satır: Courier Prime Bold harfleri tek tek, sağa yatık, hafif dönük ve oynak
    taban çizgisiyle (₺ IBM Plex Mono'dan). Görüntü bir kez çizilir; yazılış animasyonu soldan sağa açılır
    (reveal). Konum: (x, taban çizgisi), anchor 'l' / 'r' / 'm'."""
    SLANT, GAP = 0.16, 0.07

    def __init__(self, text: str, size: float, col=MAVI, seed=0):
        self.text, self.size, self.col = text, size, col
        rng = random.Random(f"{text}|{seed}|{size}")
        plan, cur = [], 0.0
        faz = rng.uniform(0, 6.28)
        self.char_x: list[tuple[float, float]] = []      # her karakterin (sol, sağ) yerel x'i (kelime eşlemesi için)
        for i, ch in enumerate(text):
            if ch == " ":
                a = cur
                cur += size * 0.36 + rng.uniform(-1, 1)
                self.char_x.append((a, cur))
                continue
            face = "plex" if ch == K.TL else "courier"
            px = max(8, int(round(size * SS * (1 + rng.uniform(-0.05, 0.05)))))
            im, by, il, ir = _glyph(ch, face, px)
            ink_w = (ir - il) / SS
            dy = math.sin(i * 0.55 + faz) * size * 0.035 + rng.uniform(-1, 1) * size * 0.02
            rot = rng.gauss(0, 2.2)
            plan.append((cur, im, by, il, dy, rot))
            self.char_x.append((cur, cur + ink_w))
            cur += ink_w + size * self.GAP + rng.uniform(-0.6, 0.6)
        self.w = max(1.0, cur - size * self.GAP)
        pad = size * 0.6
        self.ox, self.oy = pad, size * 1.25                # yerel (0, taban) noktasının görüntüdeki yeri
        cw, ch_ = int(math.ceil((self.w + 2 * pad) * SS)), int(math.ceil(size * 1.9 * SS))
        mask = Image.new("L", (cw, ch_), 0)
        for cx, im, by, il, dy, rot in plan:
            g = im.transform(im.size, Image.AFFINE, (1, self.SLANT, -self.SLANT * by, 0, 1, 0), resample=Image.BICUBIC)
            if rot:
                g = g.rotate(rot, resample=Image.BICUBIC, center=(il, by))
            px_, py_ = (self.ox + cx) * SS, (self.oy + dy) * SS
            mask.paste(255, (int(round(px_ - il)), int(round(py_ - by))), g)
        mask = mask.resize((max(1, cw // SS), max(1, ch_ // SS)), Image.LANCZOS)
        a = np.asarray(mask, dtype=np.float32)
        # tükenmez: mürekkep yer yer biraz açık (kalem kâğıda eşit basmaz)
        n = np.random.default_rng(seed + 7).normal(0, 1, (a.shape[0] // 12 + 1, a.shape[1] // 12 + 1))
        n = np.asarray(Image.fromarray(n.astype(np.float32)).resize((a.shape[1], a.shape[0]), Image.BICUBIC))
        a = a * np.clip(0.93 + 0.06 * n, 0.78, 1.0)
        self.im = Image.new("RGBA", (a.shape[1], a.shape[0]), col + (0,))
        self.im.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))

    def left(self, x: float, anchor: str = "l") -> float:
        return {"l": x, "r": x - self.w, "m": x - self.w / 2}[anchor]

    def put(self, img: Image.Image, x: float, y: float, anchor: str = "l", reveal: float | None = None,
            clip=CLIP, alpha: float = 1.0) -> None:
        """reveal: yerel x (soldan) — o x'e kadar yazılmış kısım; None tamamı."""
        x0 = self.left(x, anchor) - self.ox
        im = self.im
        if reveal is not None:
            cw = int(round(self.ox + reveal))
            if cw <= 0:
                return
            if cw < im.width:
                im = im.crop((0, 0, cw, im.height))
        K.put(img, im, x0, y - self.oy, alpha=alpha, clip=clip)

    def ink_box(self, x: float, y: float, anchor: str = "l") -> tuple[float, float, float, float]:
        x0 = self.left(x, anchor)
        return x0, y - self.size * 0.78, x0 + self.w, y + self.size * 0.26


def _gurultu(n, seed, amp, yumusak=5):
    rng = np.random.default_rng(seed)
    raw = rng.normal(0, 1, n + 2 * yumusak)
    return np.convolve(raw, np.ones(yumusak) / yumusak, mode="same")[yumusak:yumusak + n] * amp


def el_cizgi(x0, y0, x1, y1, seed, amp=1.4, n=36):
    """İki nokta arasında hafif titrek kalem çizgisi."""
    nz = _gurultu(n, seed, amp)
    L = math.hypot(x1 - x0, y1 - y0) or 1
    nx, ny = -(y1 - y0) / L, (x1 - x0) / L
    pts = []
    for i in range(n):
        t = i / (n - 1)
        bow = math.sin(t * math.pi) * amp * 1.1
        pts.append((x0 + (x1 - x0) * t + nx * (nz[i] + bow), y0 + (y1 - y0) * t + ny * (nz[i] + bow)))
    return pts


def el_daire(cx, cy, rx, ry, seed, tur=1.14, rot=-4.0, amp=0.03):
    """Bir kelimenin etrafına elle çekilmiş halka: başı ile sonu üst üste biner, biraz kayar."""
    rng = random.Random(seed)
    n = 90
    a0 = math.radians(rng.uniform(150, 200))
    nz = _gurultu(n, seed, amp)
    th = math.radians(rot)
    pts = []
    for i in range(n):
        t = i / (n - 1)
        a = a0 + t * tur * 2 * math.pi
        k = 1 + nz[i] + 0.05 * t
        x, y = rx * k * math.cos(a), ry * k * math.sin(a)
        pts.append((cx + x * math.cos(th) - y * math.sin(th), cy + x * math.sin(th) + y * math.cos(th)))
    return pts


def el_tik(x, y, s, seed):
    """Sol alt köşesi yaklaşık (x, y) olan onay işareti."""
    rng = random.Random(seed)
    return [(x, y - s * 0.45), (x + s * 0.32, y + rng.uniform(-2, 2)), (x + s * 0.95, y - s * 0.95)]


def el_kutu(cx, cy, s, seed):
    rng = random.Random(seed)
    h = s / 2

    def j():
        return rng.uniform(-2.0, 2.0)
    return [(cx - h + j(), cy - h + j()), (cx + h + j(), cy - h + j()), (cx + h + j(), cy + h + j()),
            (cx - h + j(), cy + h + j()), (cx - h + j(), cy - h + j() - 4)]


def el_ok(x0, y0, x1, y1, seed, bukum=0.25, uc=24):
    """Kavisli kalem oku ve iki çizgilik ucu: [gövde, uç1, uç2]."""
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    L = math.hypot(x1 - x0, y1 - y0) or 1
    nx, ny = -(y1 - y0) / L, (x1 - x0) / L
    cx, cy = mx + nx * L * bukum, my + ny * L * bukum
    nz = _gurultu(30, seed, 1.0)
    govde = []
    for i in range(30):
        t = i / 29
        x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1
        y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1
        govde.append((x + nz[i], y + nz[i] * 0.6))
    a = math.atan2(y1 - govde[-4][1], x1 - govde[-4][0])
    return [govde, [(x1, y1), (x1 - uc * math.cos(a - 0.5), y1 - uc * math.sin(a - 0.5))],
            [(x1, y1), (x1 - uc * math.cos(a + 0.5), y1 - uc * math.sin(a + 0.5))]]


class Iz:
    """Kalem işareti (bir ya da birkaç çizgi): ilerleme p (0..1) kadarı çizilir; 20 adımda önbelleğe alınır."""
    STEPS = 20

    def __init__(self, strokes: list[list[tuple[float, float]]], width: float, col=MAVI, alpha=236):
        self.strokes = [s for s in strokes if len(s) >= 2]
        self.width, self.col, self.alpha = width, col, alpha
        pts = [p for s in self.strokes for p in s] or [(0, 0)]
        m = width + 4
        self.box = (min(x for x, _ in pts) - m, min(y for _, y in pts) - m, max(x for x, _ in pts) + m,
                    max(y for _, y in pts) + m)
        self.lens = [sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(s, s[1:])) for s in self.strokes]
        self.total = sum(self.lens) or 1.0
        self._c: dict = {}

    def layer(self, p: float) -> Image.Image | None:
        k = int(round(K.clamp(p) * self.STEPS))
        if k <= 0:
            return None
        if k not in self._c:
            pen = K.Pen(*self.box)
            left = self.total * k / self.STEPS
            col = self.col + (self.alpha,)
            for s, L in zip(self.strokes, self.lens):
                if left <= 0:
                    break
                pts, acc = [s[0]], 0.0
                for a, b in zip(s, s[1:]):
                    d = math.hypot(b[0] - a[0], b[1] - a[1])
                    if acc + d >= left:
                        f = (left - acc) / d if d else 1.0
                        pts.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
                        break
                    pts.append(b)
                    acc += d
                left -= L
                pen.line(pts, col, self.width)
                for x, y in (pts[0], pts[-1]):
                    pen.ell(x, y, self.width / 2, fill=col)
            self._c[k] = pen.done()
        return self._c[k]

    def put(self, img: Image.Image, p: float = 1.0, clip=CLIP, alpha: float = 1.0) -> None:
        lay = self.layer(p)
        if lay is not None:
            K.put(img, lay, self.box[0], self.box[1], clip=clip, alpha=alpha)


def fosfor(x0, y0, x1, y1, seed) -> tuple[Image.Image, tuple[float, float]]:
    """Fosforlu kalem şeridi (uçları eğik, kenarları titrek): (1x görüntü, sol üst)."""
    rng = random.Random(seed)
    pen = K.Pen(x0 - 14, y0 - 8, x1 + 14, y1 + 8)
    n = 22
    top = [(x0 + (x1 - x0) * i / n, y0 + rng.uniform(-2.2, 2.2)) for i in range(n + 1)]
    bot = [(x1 - (x1 - x0) * i / n, y1 + rng.uniform(-2.2, 2.2)) for i in range(n + 1)]
    top[0] = (x0 + 7, y0)
    bot[-1] = (x0 - 5, y1)
    pen.poly(top + bot, FOSFOR + (226,))
    return pen.done(), (x0 - 14, y0 - 8)


def kalem_svg(cap=MAVI) -> str:
    """Genel bir tükenmez kalem (kendi çizimimiz; viewBox 0 -14 600 76): uç solda (6, 30)."""
    ink, off, c = K._hex(INK), K._hex(OFF), K._hex(cap)
    yol = "M440 6 L440 -2 Q440 -10 452 -10 L580 -10 Q590 -10 586 0"
    return (f'<path d="M6 30 L64 18 L64 42 Z" fill="{K._hex((190, 186, 176))}" stroke="{ink}" stroke-width="5" '
            'stroke-linejoin="round"/>'
            f'<circle cx="8" cy="30" r="4" fill="{ink}"/>'
            f'<rect x="60" y="12" width="360" height="36" rx="8" fill="{off}" stroke="{ink}" stroke-width="5"/>'
            f'<rect x="70" y="20" width="340" height="7" rx="3" fill="{K._hex((226, 222, 212))}"/>'
            f'<rect x="400" y="6" width="190" height="48" rx="14" fill="{c}" stroke="{ink}" stroke-width="5"/>'
            f'<path d="{yol}" fill="none" stroke="{ink}" stroke-width="12" stroke-linecap="round"/>'
            f'<path d="{yol}" fill="none" stroke="{c}" stroke-width="5" stroke-linecap="round"/>')


KALEM_VB = (0, -14, 600, 76)
_kalem: dict = {}


def kalem(w: float, rot: float) -> tuple[Image.Image, tuple[float, float]]:
    """Tükenmez kalemin 1x görüntüsü ve ucunun görüntüdeki yeri (rot: derece, saat yönünün tersine)."""
    key = (round(w), round(rot, 1))
    if key not in _kalem:
        vb = KALEM_VB
        h = w * vb[3] / vb[2]
        im = K.svg_img(kalem_svg(), vb, w * SS, h * SS)
        im = K.add_shadow(im, 5 * SS, 7 * SS, 0, 0.28)
        tip = ((6 - vb[0]) / vb[2] * w * SS, (30 - vb[1]) / vb[3] * h * SS)
        cx, cy = im.width / 2, im.height / 2
        r = im.rotate(rot, resample=Image.BICUBIC, expand=True)
        a = math.radians(rot)
        dx, dy = tip[0] - cx, tip[1] - cy
        tx = r.width / 2 + dx * math.cos(a) + dy * math.sin(a)
        ty = r.height / 2 - dx * math.sin(a) + dy * math.cos(a)
        r = r.resize((max(1, r.width // SS), max(1, r.height // SS)), Image.LANCZOS)
        _kalem[key] = (r, (tx / SS, ty / SS))
    return _kalem[key]


def kalem_ucu(img: Image.Image, x: float, y: float, clip=CLIP) -> None:
    """Yazan kalem: ucu (x, y)'de, gövdesi sağ aşağıya uzanır (sağ elle yazılmış gibi, yazılanı örtmez). Sağ kenarda
    ya da altta güvenli alandan taşacaksa gövde sola ve/veya yukarı döner (aynalanır)."""
    im, (tx, ty) = kalem(210, -34)
    w, h = im.size
    for sol, ust in ((False, False), (True, False), (False, True), (True, True)):
        ox = x - (w - tx if sol else tx)
        oy = y - (h - ty if ust else ty)
        if ox >= clip[0] and ox + w <= clip[2] and oy >= clip[1] and oy + h <= clip[3]:
            break
    key = ("ayna", sol, ust)
    if key not in _kalem:
        lay = ImageOps.mirror(im) if sol else im
        _kalem[key] = ImageOps.flip(lay) if ust else lay
    K.put(img, _kalem[key], ox, oy, clip=clip)


def yorum_etiketi(size: float, seed: int, rot: float = 1.8) -> Image.Image:
    """Sarı yırtık kâğıtta 'YORUMLARA YAZ' ve kalın aşağı ok (Anton'un ↓ işareti ince kaldığı için çizilir); mürekkep
    kenarlı, sert gölgeli 1x görüntü."""
    text = "YORUMLARA YAZ"
    cap = cap_h("anton", size)
    padx, pady = size * 0.22, size * 0.22
    aw = size * 0.86
    w = K.tw(text, "anton", size) + 2 * padx + aw * 0.86
    h = cap + 2 * pady
    sp = K.Sprite(w, h, margin=max(14, size * 0.18))
    K.torn_paper(sp, 0, 0, w, h, YELLOW, seed, rim=INK)
    sp.text((padx, pady + cap), text, "anton", size, INK)
    ok = K.svg_img(K.arrow_svg(INK, 17, "down"), K.ICON_VB, aw * SS, aw * SS)
    sp.im.alpha_composite(ok, (int((w - padx * 0.55 - aw * 0.9 + sp.m) * SS), int((h / 2 - aw * 0.5 + sp.m) * SS)))
    return sp.render(rot, shadow=(6, 8, 0, 0.9))


# ---------------------------------------------------------------- 7 bölmeli LCD
_SEG = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
        "8": "abcdefg", "9": "abcdfg", "-": "g", " ": ""}


def _segment_polys(dw, dh, t):
    g = t * 0.22

    def hx(xa, xb, y):
        return [(xa + g, y), (xa + g + t / 2, y - t / 2), (xb - g - t / 2, y - t / 2), (xb - g, y),
                (xb - g - t / 2, y + t / 2), (xa + g + t / 2, y + t / 2)]

    def vx(x, ya, yb):
        return [(x, ya + g), (x + t / 2, ya + g + t / 2), (x + t / 2, yb - g - t / 2), (x, yb - g),
                (x - t / 2, yb - g - t / 2), (x - t / 2, ya + g + t / 2)]
    L, R, T, M, B = t / 2, dw - t / 2, t / 2, dh / 2, dh - t / 2
    return {"a": hx(L, R, T), "g": hx(L, R, M), "d": hx(L, R, B),
            "f": vx(L, T, M), "b": vx(R, T, M), "e": vx(L, M, B), "c": vx(R, M, B)}


def lcd_hucreleri(metin: str) -> list[list]:
    """'1.200.000' -> [[ch, nokta, virgül], ...]: '.' ve ',' önceki hücrenin noktası (virgül kuyruklu)."""
    out: list[list] = []
    for ch in metin:
        if ch in ".," and out:
            out[-1][1 if ch == "." else 2] = True
        else:
            out.append([ch, False, False])
    return out


def lcd_rakamlar(pen: K.Pen, x0, y0, x1, metin: str, dh: float, n_hucre: int, egim=0.09):
    """Sağa yaslı 7 bölmeli rakamlar; boş hücrelerde soluk '8' hayaletleri. '/' çapraz bölme olarak çizilir."""
    hucre = lcd_hucreleri(metin)[-n_hucre:]
    hucre = [[" ", False, False]] * max(0, n_hucre - len(hucre)) + hucre
    pitch = (x1 - x0) / n_hucre
    dw = pitch * 0.72
    t = dh * 0.12
    polys = _segment_polys(dw, dh, t)

    def tr(px, py, ox):
        return (ox + px + egim * (dh - py), y0 + py)
    for i, (ch, dp, vg) in enumerate(hucre):
        ox = x0 + i * pitch + pitch * 0.08
        for pts in polys.values():
            pen.poly([tr(px, py, ox) for px, py in pts], LCD_GHOST)
        r = t * 0.75
        dx, dy = tr(dw + pitch * 0.13, dh - r, ox)
        pen.ell(dx, dy, r, fill=LCD_GHOST)
        if ch == "/":
            pts = [(dw * 0.05, dh - t * 0.2), (dw * 0.05 + t * 1.1, dh - t * 0.2), (dw * 0.95, t * 0.2),
                   (dw * 0.95 - t * 1.1, t * 0.2)]
            pen.poly([tr(px, py, ox) for px, py in pts], LCD_INK)
        else:
            for s in _SEG.get(ch, ""):
                pen.poly([tr(px, py, ox) for px, py in polys[s]], LCD_INK)
        if dp or vg:
            pen.ell(dx, dy, r, fill=LCD_INK)
        if vg:
            pen.poly([(dx + r * 0.2, dy), (dx - r * 1.3, dy + r * 2.6), (dx - r * 0.1, dy + r * 2.4)], LCD_INK)


def _fmt(v: float, dec: int) -> str:
    return K.fmt_value(v, dec, True)


def lcd_degeri(deger: str) -> tuple[str, str]:
    """Kart değerini LCD'ye çevirir: ('1.200.000', '₺'), ('25', '%'), ('1/90.000.000', ''), ('18', 'AY').
    Okunamazsa ('', '')."""
    s = up(deger)
    if not s:
        return "", ""
    birim = K.TL if (K.TL in s or re.search(r"\bTL\b", s)) else ("%" if "%" in s else "")
    m = re.search(r"(\d[\d.,]*)\s*/\s*(\d[\d.,]*)\s*(MİLYAR|MİLYON|BİN)?", s)
    if m:                                               # oran: '1 / 90 MİLYON' -> 1/90.000.000
        b = tutar(m.group(2) + (" " + m.group(3) if m.group(3) else ""))
        bv = _fmt(b[0], 0) if b and b[0] == int(b[0]) else m.group(2)
        return f"{m.group(1)}/{bv}", ""
    t = tutar(s)
    if t is None:
        return "", ""
    v = t[0]
    dec = 0 if abs(v - round(v)) < 1e-6 else (1 if abs(v * 10 - round(v * 10)) < 1e-6 else 2)
    txt = _fmt(abs(v), dec)
    if v < 0:
        txt = "-" + txt
    if not birim:
        kalan = re.sub(r"[\d.,\s%-]|MİLYAR|MİLYON|BİN", " ", s).split()
        birim = kalan[0][:4] if kalan else ""
    return txt, birim


def lcd_sigar(metin: str, n: int = 12) -> bool:
    return len(lcd_hucreleri(metin)) <= n


# ---------------------------------------------------------------- senaryo -> sahne planı
@dataclass
class Sahne:
    i: int
    tur: str                        # kanca | durak | sayac | fis | iceriden | cta | serbest
    kart: str = "auto"              # kart.card_type sonucu
    saat: str = ""                  # '07:30' (gün akışı durağı)
    dakika: int = -1
    durak: int = 0                  # durak sırası (1'den); durak olmayan sahnede o ana kadarki son durak
    baslik: list[str] = field(default_factory=list)
    hl: int = -1
    resim: Path | None = None       # çizim (sprite) ya da fotoğraf
    foto: bool = False
    kunye: dict = field(default_factory=dict)
    deger: str = ""
    etiket: str = ""
    notu: str = ""
    satirlar: list[tuple[str, str]] = field(default_factory=list)
    alinti: str = ""
    maskot: str = "auto"
    start: float = 0.0
    end: float = 0.0
    a: int = 0                      # kelime aralığı [a, b)
    b: int = 0


def _kart_spec(spec) -> SimpleNamespace:
    """kart.card_type'ın okuduğu biçim (pipeline.build'in kart şablonuna verdiği card sözlüğü)."""
    c = spec.card or {}
    return SimpleNamespace(card={"type": c.get("card", "auto"), "value": c.get("card_value", ""),
                                 "label": c.get("card_label", ""), "myth": c.get("card_myth", ""),
                                 "fact": c.get("card_fact", ""), "lines": list(c.get("card_lines") or [])},
                           image=spec.image, sprite=spec.sprite, headline=spec.headline, narration=spec.narration)


def plan(specs) -> list[Sahne]:
    n = len(specs)
    out: list[Sahne] = []
    for i, spec in enumerate(specs):
        c = spec.card or {}
        kt = K.card_type(_kart_spec(spec), i, n)
        s = Sahne(i, "serbest", kt)
        s.baslik = [up(x) for x in spec.headline if x and x.strip()]
        s.hl = spec.highlight_line if 0 <= spec.highlight_line < len(s.baslik) else -1
        if spec.sprite is not None:
            s.resim = spec.sprite
        elif spec.image is not None:
            s.resim, s.foto, s.kunye = spec.image, True, dict(c.get("credit") or {})
        s.deger, s.etiket = up(c.get("card_value", "")), up(c.get("card_label", ""))
        s.notu = (c.get("card_note") or "").strip()
        s.satirlar = K.parse_receipt(c.get("card_lines"))
        s.maskot = c.get("mascot", "auto")
        st = saat_of(spec.kicker) if i > 0 else None
        if st:
            s.saat, s.dakika = st
        if i == 0:
            s.tur = "kanca"
        elif kt == "cta":
            s.tur = "cta"
        elif kt == "receipt":
            s.tur = "fis"
        elif kt == "counter":
            s.tur = "sayac"
        elif kt in ("interstitial", "quote"):
            s.tur = "iceriden"
            s.alinti = (c.get("card_label") or "").strip().strip('"“”') if kt == "quote" else ""
        elif st:
            s.tur = "durak"
        out.append(s)
    k = 0
    for s in out:
        if s.tur in ("durak", "sayac", "fis"):
            k += 1
        s.durak = k
    return out


# ---------------------------------------------------------------- dış ses (fosforlu kalemle okunan kelime)
class Anlati(N.Speech):
    """nasil.Speech'in sayfa bölme kuralları; kâğıt üstünde: söylenmiş mürekkep, okunan fosforlu kalem üstünde
    mürekkep, sıradaki soluk."""

    def image(self, pi: int, cur: int) -> Image.Image:
        key = (pi, cur)
        if key in self._img:
            return self._img[key]
        x0, y0, x1, y1 = self.rect
        pen = K.Pen(x0 - 4, y0 - 4, x1 + 4, y1 + 4)
        lines = self.lines.get(pi, [])
        size = self.size
        lh = size * self.lh
        cap = cap_h(self.FONT, size)
        base = y0 + cap + 2
        sp = K.tw(" ", self.FONT, size)
        for li, L in enumerate(lines):
            x = x0
            for i in L:
                ww = K.tw(self.texts[i], self.FONT, size)
                if i == cur:
                    yb = base + li * lh
                    pen.rr((x - 5, yb - cap - 7, x + ww + 5, yb + size * 0.24), 5, fill=FOSFOR + (235,))
                x += ww + sp
            x = x0
            for i in L:
                col = INK if i <= cur else SONUK
                pen.text(x, base + li * lh, self.texts[i], self.FONT, size, col)
                x += K.tw(self.texts[i], self.FONT, size) + sp
        if len(self._img) > 96:
            self._img.clear()
        self._img[key] = pen.done()
        return self._img[key]


# ---------------------------------------------------------------- hesap makinesi
class HesapMakinesi:
    """Sarı masa hesap makinesi 'MAKAS-12': isim plakası ve güneş paneli, LCD (üst satırda kalem ya da işlem, büyük 7
    bölmeli rakamlar, sağda birim), bir sıra işlem tuşu (basılan tuş sarı). Durum başına bir kez çizilir, eğilir."""

    def __init__(self):
        self._body: dict = {}
        self._c: dict = {}

    def body(self, basili: str | None) -> Image.Image:
        if basili not in self._body:
            pen = K.Pen(-20, -20, CALC_W + 20, CALC_H + 20)
            pen.rr((0, 0, CALC_W, CALC_H), 46, fill=INK)
            pen.rr((7, 7, CALC_W - 7, CALC_H - 7), 40, fill=YELLOW)
            pen.rr((48, 11, CALC_W - 48, 20), 4, fill=(255, 234, 128))
            pen.svg(K.scissors_svg(26, RED, INK, YELLOW, INK), K.SCISSORS_VB, 40, 30, 62)
            pen.text(116, 74, "MAKAS-12", "anton", 44, INK)
            pen.text(116 + K.tw("MAKAS-12", "anton", 44) + 14, 72, "12 HANE", "courier", 24, INK)
            sx0, sx1 = 560, LCD_BOX[2]
            pen.rr((sx0, 30, sx1, 78), 8, fill=INK)
            for i in range(4):
                a = sx0 + 6 + i * (sx1 - sx0 - 12) / 4
                pen.rr((a + 3, 36, a + (sx1 - sx0 - 12) / 4 - 3, 72), 3, fill=(62, 58, 52))
            lx0, ly0, lx1, ly1 = LCD_BOX
            pen.rr((lx0 - 18, ly0 - 16, lx1 + 18, ly1 + 18), 22, fill=INK)
            pen.rr(LCD_BOX, 10, fill=LCD_BG)
            pen.rr((lx0, ly0, lx1, ly0 + 9), 6, fill=(178, 182, 168))
            kx0, kx1, ky0, kh, gap = 44, LCD_BOX[2], 300, 82, 16
            kw = (kx1 - kx0 - gap * 5) / 6
            for c, t in enumerate(TUSLAR):
                x = kx0 + c * (kw + gap)
                down = basili == t
                dy = 5 if down else 0
                fill, fg = (RED, OFF) if t == "AC" else ((OFF, INK) if t == "=" else (INK, OFF))
                if down:
                    fill, fg = YELLOW, INK
                pen.rr((x + 2, ky0 + 9, x + kw + 2, ky0 + kh + 9), 20, fill=INK)
                pen.rr((x, ky0 + dy, x + kw, ky0 + kh + dy), 20, fill=INK)
                pen.rr((x + 5, ky0 + 5 + dy, x + kw - 5, ky0 + kh - 5 + dy), 16, fill=fill)
                cx, cy = x + kw / 2, ky0 + kh / 2 + dy
                if t == "AC":
                    pen.text(cx, cy + cap_h("anton", 46) / 2, t, "anton", 46, fg, anchor="ms")
                else:
                    _sembol(pen, t, cx, cy, 23, fg)
            self._body[basili] = pen.done()
        return self._body[basili]

    def layer(self, ust: str, deger: str, birim: str, basili: str | None, rozet: str) -> Image.Image:
        """Makinenin o durumdaki eğik görüntüsü (sert gölge dahil); sol üst köşesi CALC_ORIGIN."""
        key = (ust, deger, birim, basili, rozet)
        if key in self._c:
            return self._c[key]
        im = self.body(basili).copy()
        pen = K.Pen(-20, -20, CALC_W + 20, CALC_H + 20)
        lx0, ly0, lx1, ly1 = LCD_BOX
        rx = lx1 - 18
        if rozet:
            rw = K.tw(rozet, "courier", 24) + 18
            pen.rr((rx - rw, ly0 + 16, rx, ly0 + 50), 5, outline=LCD_INK, width=3)
            pen.text(rx - rw / 2, ly0 + 41, rozet, "courier", 24, LCD_INK, anchor="ms")
            rx -= rw + 14
        if ust:
            size = 28
            room = rx - (lx0 + 20)
            while size > 22 and K.tw(ust, "courier", size) > room:
                size -= 1
            pen.text(lx0 + 20, ly0 + 42, K.fit_words(ust, "courier", size, room), "courier", size, LCD_INK)
        bw = 0.0
        if birim:
            bf, bs = ("plex", 66) if birim == K.TL else ("anton", 52)
            bw = K.tw(birim, bf, bs) + 16
            pen.text(lx1 - 18, ly1 - 22, birim, bf, bs, LCD_INK, anchor="rs")
        lcd_rakamlar(pen, lx0 + 12, ly0 + 60, lx1 - 18 - bw, deger or "0", 92, 12 if not birim else 11)
        im.alpha_composite(pen.done())
        big = im.resize((im.width * SS, im.height * SS), Image.LANCZOS)
        big = big.rotate(CALC_ROT, resample=Image.BICUBIC, expand=True)
        big = K.add_shadow(big, 10 * SS, 12 * SS, 0, 0.92)
        out = big.resize((big.width // SS, big.height // SS), Image.LANCZOS)
        if len(self._c) > 80:
            self._c.clear()
        self._c[key] = out
        return out

    @staticmethod
    def origin(lay: Image.Image) -> tuple[float, float]:
        """Eğik görüntünün sol üst köşesi: döndürülmemiş kutunun merkezi aynı yerde kalır."""
        cx, cy = CALC_X - 20 + (CALC_W + 40) / 2, CALC_Y - 20 + (CALC_H + 40) / 2
        return cx - (lay.width - 10) / 2, cy - (lay.height - 12) / 2


def _sembol(pen: K.Pen, t, cx, cy, r, col):
    """İşlem tuşlarının simgeleri (Anton'daki matematik işaretleri küçük kaldığı için çizilir)."""
    k = r * 0.26
    if t in ("−", "+", "÷"):
        pen.rr((cx - r, cy - k / 2 - 1, cx + r, cy + k / 2 + 1), k / 2, fill=col)
    if t == "+":
        pen.rr((cx - k / 2 - 1, cy - r, cx + k / 2 + 1, cy + r), k / 2, fill=col)
    if t == "÷":
        for sy in (-1, 1):
            pen.ell(cx, cy + sy * r * 0.62, k * 0.75, fill=col)
    if t == "=":
        for sy in (-1, 1):
            pen.rr((cx - r, cy + sy * r * 0.34 - k / 2, cx + r, cy + sy * r * 0.34 + k / 2), k / 2, fill=col)
    if t == "×":
        a = r * 0.74
        for sx in (-1, 1):
            pts = [(cx - a, cy - sx * a), (cx + a, cy + sx * a)]
            pen.line(pts, col, k + 1)
            for px, py in pts:
                pen.ell(px, py, (k + 1) / 2, fill=col)


# ---------------------------------------------------------------- sayfadaki öğeler
class Oge:
    """Sayfaya konan bir öğe. gorunur(si): o sahnede görünür mü; kes: görünmez olduğu sınırda makasla kesilir
    (yoksa kendi çıkışı vardır: cikis sn). z: çizim sırası."""
    z = 10
    kes = True
    cikis = 0.0

    def __init__(self, sahneler):
        self.sahneler = set(sahneler)

    def gorunur(self, si: int) -> bool:
        return si in self.sahneler

    def draw(self, v: "AjandaVideo", img: Image.Image, t: float) -> None:
        raise NotImplementedError

    def exit(self, v: "AjandaVideo", img: Image.Image, t: float, p: float) -> None:
        """Çıkış (p 0..1): öntanımlı yok."""


class YaziOge(Oge):
    """Elle yazılan satır: t0'dan itibaren dur sn'de soldan sağa yazılır (kalem ucu yazıyı izler). kelime: sözle eşli
    yazma için (karakter indeksi -> açılma anı) listesi; verilirse dur yok sayılır."""

    def __init__(self, sahneler, yazi: Yazi, x, y, anchor="l", t0=0.0, dur=0.6, z=10, anlik=False, kelime=None):
        super().__init__(sahneler)
        self.yazi, self.x, self.y, self.anchor = yazi, x, y, anchor
        self.t0, self.dur, self.z, self.anlik, self.kelime = t0, max(0.05, dur), z, anlik, kelime

    def reveal(self, t: float) -> float | None:
        """Yazılmış kısmın yerel x'i; None: tamamı."""
        if self.anlik:
            return None
        w = self.yazi.w
        if self.kelime:
            cx = self.yazi.char_x
            out = 0.0
            for (ca, cb), (ta, tb) in zip(cx, self.kelime):
                if t <= ta:
                    break
                out = ca + (cb - ca) * K.clamp((t - ta) / max(0.02, tb - ta))
                if t < tb:
                    break
            return None if out >= w - 0.5 else out
        p = (t - self.t0) / self.dur
        return None if p >= 1 else w * K.clamp(p)

    def bitti(self, t: float) -> bool:
        return self.reveal(t) is None

    def draw(self, v, img, t):
        r = self.reveal(t)
        if r is not None and r <= 0:
            return
        self.yazi.put(img, self.x, self.y, self.anchor, reveal=r)
        if r is not None:
            v.kalem_ucu = (self.yazi.left(self.x, self.anchor) + r, self.y - self.yazi.size * 0.1)


class IzOge(Oge):
    def __init__(self, sahneler, iz: Iz, t0=0.0, dur=0.3, z=12, anlik=False):
        super().__init__(sahneler)
        self.iz, self.t0, self.dur, self.z, self.anlik = iz, t0, max(0.05, dur), z, anlik

    def draw(self, v, img, t):
        p = 1.0 if self.anlik else (t - self.t0) / self.dur
        if p > 0:
            self.iz.put(img, p)


class FosforOge(Oge):
    """Fosforlu kalem şeridi: soldan sağa geçer."""
    z = 5

    def __init__(self, sahneler, x0, y0, x1, y1, seed, t0=0.0, dur=0.3, anlik=False):
        super().__init__(sahneler)
        self.im, self.o = fosfor(x0, y0, x1, y1, seed)
        self.t0, self.dur, self.anlik = t0, max(0.05, dur), anlik

    def draw(self, v, img, t):
        p = 1.0 if self.anlik else K.ease_in_out((t - self.t0) / self.dur)
        if p <= 0:
            return
        im = self.im
        if p < 1:
            im = im.crop((0, 0, max(1, int(im.width * p)), im.height))
        K.put(img, im, *self.o)


class ResimOge(Oge):
    """Bantlı polaroid: t0'da hafifçe büyükten iner; sahne bitince kalkıp söner."""
    z = 8
    kes = False
    cikis = 0.22

    def __init__(self, sahneler, im: Image.Image, cx, cy, t0=0.0, anlik=False):
        super().__init__(sahneler)
        self.im, self.cx, self.cy, self.t0, self.anlik = im, cx, cy, t0, anlik
        # büyükten inerken güvenli alana taşmasın: sağ ya da alt kenara yakınsa o kenar sabit kalır
        sag, alt = cx + im.width / 2, cy + im.height / 2
        self.anchor = (1.0 if sag > SAFE[2] - 50 else 0.5, 1.0 if alt > SAFE[3] - 50 else 0.5)

    def draw(self, v, img, t):
        p = 1.0 if self.anlik else (t - self.t0) / 0.28
        if p <= 0:
            return
        k = 1.0 if p >= 1 else K.lerp(1.1, 1.0, K.ease_out_cubic(p))
        a = min(1.0, p * 3)
        K.put(img, self.im, self.cx - self.im.width / 2, self.cy - self.im.height / 2, k=k, alpha=a,
              anchor=self.anchor)

    def exit(self, v, img, t, p):
        """Kalkıp sola yukarı kayar ve söner."""
        K.put(img, self.im, self.cx - self.im.width / 2 - 36 * p, self.cy - self.im.height / 2 - 28 * p,
              alpha=1 - p)


class NotOge(Oge):
    """Sarı yapışkan not ('İÇERİDEN'): sayfaya yapışır, yazısı sözle birlikte elle yazılır, sahne bitince kalkar."""
    z = 30
    kes = False
    cikis = 0.24

    def __init__(self, sahneler, govde: Image.Image, o, satirlar: list[YaziOge], izler: list[IzOge], t0):
        super().__init__(sahneler)
        self.govde, self.o, self.satirlar, self.izler, self.t0 = govde, o, satirlar, izler, t0

    def draw(self, v, img, t):
        p = (t - self.t0) / 0.24
        if p <= 0:
            return
        if p < 1:                                   # yapışır: biraz büyükten iner
            k = K.lerp(1.05, 1.0, K.ease_out_cubic(p))
            K.put(img, self.govde, *self.o, k=k, alpha=min(1.0, p * 3))
            return
        K.put(img, self.govde, *self.o)
        for s in self.satirlar:
            s.draw(v, img, t)
        for s in self.izler:
            s.draw(v, img, t)

    def exit(self, v, img, t, p):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay.alpha_composite(self.govde, (int(self.o[0]), int(self.o[1])))
        for s in self.satirlar:
            s.yazi.put(lay, s.x, s.y, s.anchor)
        for s in self.izler:
            s.iz.put(lay, 1.0)
        bb = lay.getbbox()
        if not bb:
            return
        lay = lay.crop(bb)
        K.put(img, lay, bb[0] - 50 * p, bb[1] - 40 * p, k=1 + 0.03 * p, alpha=1 - p)   # sola yukarı kalkar


class EtiketOge(Oge):
    """Yırtık etiket ya da çıkartma: t0'da patlar."""
    z = 40

    def __init__(self, sahneler, im: Image.Image, x, y, t0, nabiz=False):
        super().__init__(sahneler)
        self.im, self.x, self.y, self.t0, self.nabiz = im, x, y, t0, nabiz

    def draw(self, v, img, t):
        p = (t - self.t0) / 0.28
        if p <= 0:
            return
        k = N.ease_pop(p, 1.14) * (K.cta_pulse(t - self.t0) if self.nabiz else 1.0)
        K.put(img, self.im, self.x, self.y, k=k, anchor=(0.2, 0.5))


class ResimSabit(Oge):
    """Sahnede duran görüntü (ör. sayfadaki kalem): t0'da hafifçe kayarak gelir."""
    z = 35

    def __init__(self, sahneler, im, x, y, t0, dx=-40):
        super().__init__(sahneler)
        self.im, self.x, self.y, self.t0, self.dx = im, x, y, t0, dx

    def draw(self, v, img, t):
        p = (t - self.t0) / 0.35
        if p <= 0:
            return
        e = K.ease_out_cubic(p)
        K.put(img, self.im, self.x + self.dx * (1 - e), self.y - self.dx * 0.5 * (1 - e), alpha=min(1.0, p * 2.5))


class BaslikOge(Oge):
    """Sahnenin Anton başlığı: vurgulu satırın altından fosforlu kalem geçer, SEN / SANA / SENİN kelimesi mavi
    tükenmezle halkalanır. Kancada (kapak) her şey ilk karede tamdır; diğer sahnelerde başlık makas eskisini keserken
    belirir, sonra fosfor ve halka çizilir."""
    z = 50

    def __init__(self, s: Sahne, lines: list[str], hook: bool, vurgu: str | None = None):
        super().__init__([s.i])
        self.s, self.hook = s, hook
        if vurgu is None:
            vurgu = s.baslik[s.hl] if 0 <= s.hl < len(s.baslik) else ""
        width = BAS_X1 - X0
        zone = BAS_Y1 - BAS_Y0
        en_buyuk = 124 if hook else 112
        while True:   # son satırın çengelleri (Ç, Ş, Ğ...) de dış sesin üstünde kalmalı
            size, out = N.fit_lines(lines or [SERI_ADI], "anton", width, en_buyuk, 52, 3, zone, pitch=N.title_pitch)
            while size > 30 and any(K.tw(L, "anton", size) > width for L in out):   # bölünmeyen uzun kelime
                size -= 2
            cap = cap_h("anton", size)
            lh = N.title_pitch(out, size) if len(out) > 1 else cap
            alt = max(0.0, K.tbox(out[-1], "anton", size)[3])
            block = cap + (len(out) - 1) * lh + alt
            if block <= zone or size <= 30:
                break
            en_buyuk = size - 2
        lines = out
        self.size, self.lines = size, lines
        top = BAS_Y0 + max(0.0, (zone - block) / 2)
        self.bases = [top + cap + k * lh for k in range(len(lines))]
        self.region = (0, BAS_Y0 - 60, SAFE[2], BAS_Y1 + 48)
        pen = K.Pen(*self.region)
        for L, b in zip(lines, self.bases):
            pen.text(X0, b, L, "anton", size, INK)
        self.text = pen.done()
        self.fosfor = None
        for L, b in zip(lines, self.bases):          # vurgulu satır yeniden sarıldıysa da metninin altından geçer
            k = L.find(vurgu) if vurgu else -1
            if k >= 0:
                x0 = X0 + (K.tw(L[:k].rstrip(), "anton", size) + K.tw(" ", "anton", size) if k else 0.0)
                self.fosfor = fosfor(x0 - 10, b - cap * 0.6, x0 + K.tw(vurgu, "anton", size) + 12, b + size * 0.07,
                                     tohum("fosfor", s.i))
                break
        self.halka = None
        for L, b in zip(lines, self.bases):
            kel = L.split(" ")
            for k, w in enumerate(kel):
                if SEN_RE.match(w):
                    core = re.sub(r"\W+$", "", w)
                    a = X0 + K.tw(" ".join(kel[:k]) + (" " if k else ""), "anton", size)
                    bx = a + K.tw(core, "anton", size)
                    cx, cy = (a + bx) / 2, b - cap / 2
                    rx = (bx - a) / 2 + min(30.0, max(18.0, size * 0.18))
                    self.halka = Iz([el_daire(cx, cy, rx, cap / 2 + max(12.0, size * 0.11), tohum("halka", s.i))],
                                    max(4.5, size * 0.05), MAVI)
                    break
            if self.halka:
                break

    def zaman(self, t: float) -> tuple[float, float, float]:
        """(başlığın görünürlüğü, fosfor ilerlemesi, halka ilerlemesi)."""
        if self.hook:
            return 1.0, 1.0, 1.0
        lt = t - self.s.start
        return (K.clamp((lt - YENI0) / 0.1), K.ease_in_out((lt - YENI0 - 0.1) / 0.3), (lt - YENI0 - 0.2) / 0.5)

    def draw(self, v, img, t):
        pa, pf, ph = self.zaman(t)
        if pa <= 0:
            return
        if self.fosfor is not None and pf > 0:
            im, o = self.fosfor
            if pf < 1:
                im = im.crop((0, 0, max(1, int(im.width * pf)), im.height))
            K.put(img, im, *o)
        k = 1.0 if pa >= 1 else K.lerp(1.05, 1.0, K.ease_out_cubic(pa))
        K.put(img, self.text, *self.region[:2], k=k, alpha=min(1.0, pa * 1.6), anchor=(0.07, 0.5))
        if self.halka is not None and ph > 0:
            self.halka.put(img, ph)


# ---------------------------------------------------------------- video
class AjandaVideo:
    def __init__(self, scenes, words: list[Word], meta: dict, bcfg: dict):
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        on = bool(bcfg.get("enabled", False))
        self.intro = bool(on and bcfg.get("intro_cut", True))
        self.brand = None
        if on:
            from .brand import Brand
            self.brand = Brand(bcfg, {})
        self.p = plan(scenes)
        n = len(scenes)
        ranges, a = [], 0
        for i, s in enumerate(scenes):
            b = min(len(words), a + len(s.words)) if i < n - 1 else len(words)
            ranges.append((a, b))
            a = b
        for s, (a, b), spec in zip(self.p, ranges, scenes):
            s.a, s.b, s.start, s.end = a, b, spec.start, spec.end
        self.starts = [w.start for w in words]
        self.scene_starts = [s.start for s in self.p]
        self.N = max([s.durak for s in self.p] + [0])
        self.gun = sum(1 for s in self.p if s.tur == "durak") >= 2
        senaryo = self.meta.get("script") or {}
        ns = SimpleNamespace(scenes=[SimpleNamespace(**sc) for sc in (senaryo.get("scenes") or [])]
                             or [SimpleNamespace(**{**(sp.card or {}), "narration": sp.narration}) for sp in scenes])
        self.para = bool(para_var(ns)) or any(s.tur in ("sayac", "fis") for s in self.p)
        self.gorunum = [self._gorunum(s) for s in self.p]
        tarih = self.meta.get("tarih")
        if isinstance(tarih, str):
            tarih = dt.date.fromisoformat(tarih)
        self.tarih = turkce_tarih(tarih or dt.date.today())
        k0 = up(scenes[0].kicker) if scenes else ""
        self.seri = k0 if k0.startswith(SERI_ADI) else SERI_ADI
        self.alt = CALC_TOP - 8 if self.para else ICERIK_Y1
        self._cizgiler()
        self.hm = HesapMakinesi() if self.para else None
        self.mascot = N.Mascot()
        self._speech: dict = {}
        self._cut: dict = {}
        self._layers: dict = {}
        self.olay: dict[int, float] = {}            # sahnenin ana anı (sayı oturdu, toplam basıldı)
        self.sessiz: dict[int, int] = {}            # dış sesin yazılmadığı ilk kelime (notta, cta'da soru)
        self.ogeler: list[Oge] = []
        self.lcd: list[tuple] = []
        self._kur()
        self.ogeler.sort(key=lambda o: o.z)
        self.lcd.sort(key=lambda e: e[0])
        self.lcd_t = [e[0] for e in self.lcd]
        self.kalem_ucu = None

    # ------------------------------------------------------------ plan yardımcıları
    def _gorunum(self, s: Sahne) -> str:
        if s.tur == "cta":
            return "cta"
        if s.tur in ("sayac", "fis"):
            return "hesap"
        return "gun" if self.gun else "hesap"

    def _cizgiler(self) -> None:
        """Sayfanın çizgileri (y) ve basılı saatleri. Gün akışında ilk durağın saati ICERIK_Y0 çizgisindedir; çizgi
        aralığı durakların saatleri ve devam notları içerik alanına sığacak kadar daralır (en az 50 px; sığmazsa çizgi
        başına 2-3 saat). Para konusunda çizgiler 56 px, saatler (süs) ilk içerik çizgisinden makineye kadar 09, 10, ..."""
        if self.gun:
            dk = [s.dakika for s in self.p if s.tur == "durak"]
            h0, h1 = min(dk) // 60, max(dk) // 60
            son = max(s.i for s in self.p if s.tur == "durak")
            ek = 1 + sum(1 for s in self.p[son + 1:] if s.tur == "serbest" and self.gorunum[s.i] == "gun")
            avail = self.alt - ICERIK_Y0 - 12
            step = 1
            while True:
                need = (h1 - h0) // step + 1 + ek
                sp = min(66.0, avail / max(1, need - 1))
                if sp >= 50 or step >= 3:
                    break
                step += 1
            self.h0, self.step, self.sp = h0, step, sp
        else:
            self.h0, self.step, self.sp = 0, 1, 56.0
        y = ICERIK_Y0
        while y - self.sp >= CIZGI_UST:
            y -= self.sp
        k = -round((ICERIK_Y0 - y) / self.sp)
        self.cizgi = []                                 # (y, basılı saat)
        while y < H:
            h = self.h0 + k * self.step
            self.cizgi.append((y, f"{h:02d}" if self.gun and k >= 0 and h <= 23 else ""))
            y += self.sp
            k += 1
        if not self.gun:
            first = next((j for j, (yy, _) in enumerate(self.cizgi) if yy >= ICERIK_Y0 - 0.5), 0)
            self.cizgi = [(yy, f"{9 + j - first:02d}" if j >= first and yy <= self.alt + 0.5 else "")
                          for j, (yy, _) in enumerate(self.cizgi)]
        self.icerik = [yy for yy, _ in self.cizgi if ICERIK_Y0 - 0.5 <= yy <= self.alt]

    def satir(self, dakika: int) -> int:
        return max(0, (dakika // 60 - self.h0) // self.step)

    def kelime_ani(self, s: Sahne, hedef: list[str], rakam: str = "", sonra: int = -1) -> tuple[float, int] | None:
        """Sahnenin dış sesinde hedef kelimelerden biri (ilk 4 harf) ya da rakam geçtiği an (mutlak, 0,08 sn önce)
        ve kelimenin indeksi; sonra: bu indeksten sonraki kelimeler."""
        kok = {K._bare(x)[:4] for x in hedef if len(K._bare(x)) >= 2 and K._bare(x) not in K.RECEIPT_STOP}
        dig = re.sub(r"\D", "", rakam)
        for wi in range(max(s.a, sonra + 1), s.b):
            w = self.words[wi]
            if K._bare(w.text)[:4] in kok or (len(dig) >= 2 and dig in re.sub(r"\D", "", w.text)):
                return w.start - 0.08, wi
        return None

    # ------------------------------------------------------------ sayfa
    def sayfa(self) -> Image.Image:
        """Ajanda sayfası (video başına): krem kâğıt, çizgiler, basılı saat sütunu, cilt gölgesi, sayfa kenarları ve
        kurdele; basılı tarih satırı (çift çizgi hariç: açılışta makas onu keser)."""
        if "sayfa" in self._layers:
            return self._layers["sayfa"]
        img = Image.new("RGBA", (W, H), SAYFA + (255,))
        pen = K.Pen(0, 0, W, H)
        for y, lab in self.cizgi:
            pen.rr((70, y - 1, 1052, y + 1), 1, fill=MAVI_CIZGI)
            if lab and y <= SAFE[3] - 10:              # alttaki açıklama bandına basılı saat düşmez
                pen.text(38, y - 12, lab, "courier", 26, MAVI_SOLUK, anchor="ms")
        top = self.cizgi[0][0] - 40 if self.cizgi else CIZGI_UST
        pen.rr((66, top, 68, H), 1, fill=MAVI_CIZGI)
        img.alpha_composite(pen.done())
        g = np.zeros((H, W), np.float32)
        xs = np.arange(W, dtype=np.float32)
        g += np.clip(1 - xs / 26, 0, 1)[None, :] ** 1.6 * 0.26
        g += np.clip((xs - (W - 30)) / 30, 0, 1)[None, :] ** 2 * 0.10
        dark = Image.new("RGBA", (W, H), INK + (0,))
        dark.putalpha(Image.fromarray((g * 255).astype(np.uint8)))
        img.alpha_composite(dark)
        pen = K.Pen(1040, 0, W, H)
        for x in (1056, 1063, 1070, 1077):
            pen.rr((x, 0, x + 1.6, H), 0.8, fill=(206, 202, 192))
        img.alpha_composite(pen.done(), (1040, 0))
        rp = K.Pen(900, 0, W, 900)                     # kurdele: düğme sütununun üstünde, yalnız süs
        x0, x1, yb = 954, 996, 808
        pts = [(x0, -10), (x1, -10), (x1 + 4, yb), ((x0 + x1) / 2 + 2, yb - 30), (x0 + 4, yb)]
        rp.poly([(x + 7, y + 8) for x, y in pts], INK + (200,))
        rp.poly(pts, RED)
        rp.poly([(x0 + 6, -10), (x0 + 12, -10), (x0 + 15, yb - 8), (x0 + 9, yb - 4)], (236, 84, 80))
        rp.poly([(x1 - 9, -10), (x1 - 4, -10), (x1, yb - 4), (x1 - 5, yb - 8)], (176, 22, 30))
        img.alpha_composite(rp.done(), (900, 0))
        pen = K.Pen(0, 230, SAFE[2], TARIH_CIZGI)
        gun, ay_yil, gun_adi, sag = self.tarih
        pen.text(X0, TARIH_BASE, gun, "anton", 74, RED)
        gx = X0 + K.tw(gun, "anton", 74) + 16
        pen.text(gx, TARIH_BASE - 34, ay_yil, "courier", 28, INK)
        pen.text(gx, TARIH_BASE, gun_adi, "courier", 28, DGREY)
        pen.text(X1, TARIH_BASE, sag, "courier", 26, DGREY, anchor="rs")
        img.alpha_composite(pen.done(), (0, 230))
        self._layers["sayfa"] = img
        return img

    def cift_cizgi(self) -> Image.Image:
        if "cizgi" not in self._layers:
            pen = K.Pen(0, TARIH_CIZGI - 6, SAFE[2], TARIH_CIZGI + 14)
            pen.rr((X0, TARIH_CIZGI - 2, X1, TARIH_CIZGI + 2), 1, fill=INK)
            pen.rr((X0, TARIH_CIZGI + 7, X1, TARIH_CIZGI + 8.4), 0.7, fill=INK)
            self._layers["cizgi"] = pen.done()
        return self._layers["cizgi"]

    def taban(self, kanca: bool) -> Image.Image:
        """Sayfa + seri etiketi (kancada büyük, kicker'daki sayıyla; diğer sahnelerde küçük)."""
        key = ("taban", kanca)
        if key in self._layers:
            return self._layers[key]
        img = self.sayfa().copy()
        pen = K.Pen(0, SIRA_CY - 60, SAFE[2], SIRA_CY + 60)
        if kanca:
            size = 44
            while size > 40 and N.label_w(self.seri, size) > X1 - X0 - 40:
                size -= 2
            N.paste_label(pen, self.seri, size, OFF, INK, 11, X0 + N.label_w(self.seri, size) / 2 + 2, SIRA_CY + 2,
                          rot=-1.5)
        else:
            N.paste_label(pen, SERI_ADI, 40, OFF, INK, 11, X0 + N.label_w(SERI_ADI, 40) / 2 + 2, SIRA_CY, rot=-1.5)
        img.alpha_composite(pen.done(), (0, SIRA_CY - 60))
        self._layers[key] = img
        return img

    # ------------------------------------------------------------ DURAK ilerlemesi
    def ilerleme_kutulari(self) -> tuple[float, float, float]:
        n = self.N
        s, gap = (34, 14) if n <= 5 else (28, 10)
        return X1 - 6 - (n * s + (n - 1) * gap), s, gap

    def ilerleme(self, img: Image.Image, si: int, t: float) -> None:
        """Sağda 'DURAK k/N' ve elle çizilmiş kutular: geçilen duraklar mavi tikli, şimdiki kırmızı halkalı; sonda
        TAMAM. Kancada (kapak) yok."""
        if not self.N or si == 0:
            return
        s = self.p[si]
        lt = t - s.start
        bitti = s.tur == "cta"
        k = self.N if bitti else s.durak
        if k <= 0:
            return
        key = ("ilerleme", k, bitti)
        if key not in self._layers:
            kx0, bs, gap = self.ilerleme_kutulari()
            pen = K.Pen(0, SIRA_CY - 50, SAFE[2], SIRA_CY + 50)
            size = 44
            base = SIRA_CY + cap_h("anton", size) / 2
            tx = kx0 - 22
            if bitti:
                pen.text(tx, base, "TAMAM", "anton", size, INK, anchor="rs")
            else:
                sag = f"/{self.N}"
                w_sag = K.tw(sag, "anton", size)
                pen.text(tx, base, sag, "anton", size, INK, anchor="rs")
                pen.text(tx - w_sag, base, str(k), "anton", size, RED, anchor="rs")
                pen.text(tx - w_sag - K.tw(str(k), "anton", size) - 10, base, "DURAK", "anton", size, INK,
                         anchor="rs")
            cx = [kx0 + bs / 2 + j * (bs + gap) for j in range(self.N)]
            kutular = [Iz([el_kutu(x, SIRA_CY, bs, 300 + j)], 3.4) for j, x in enumerate(cx)]
            tikler = [Iz([el_tik(x - bs * 0.32, SIRA_CY + bs * 0.18, bs * 0.95, 400 + j)], 5.0)
                      for j, x in enumerate(cx)]
            halka = [Iz([el_daire(x, SIRA_CY, bs * 0.8, bs * 0.76, 500 + j, tur=1.1)], 4.0, RED)
                     for j, x in enumerate(cx)]
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            lay.alpha_composite(pen.done(), (0, SIRA_CY - 50))
            for iz in kutular:
                iz.put(lay)
            last = self.N if bitti else k - 1
            for j in range(last - 1):              # önceki tikler (sonuncusu bu sahnede çizilir)
                tikler[j].put(lay)
            bb = lay.getbbox()
            self._layers[key] = (lay.crop(bb), bb[:2], tikler, halka)
        lay, o, tikler, halka = self._layers[key]
        K.put(img, lay, *o)
        last = self.N if bitti else k - 1
        onceki = self.p[si - 1]
        yeni = bitti or (s.tur in ("durak", "sayac", "fis") and onceki.durak != s.durak)
        if last >= 1:
            tikler[last - 1].put(img, (lt - 0.2) / 0.25 if yeni else 1.0)
        if not bitti:
            halka[k - 1].put(img, (lt - 0.35) / 0.4 if yeni else 1.0)

    # ------------------------------------------------------------ öğeleri kur
    def _kur(self) -> None:
        for s in self.p:
            if s.tur == "cta":
                self.ogeler.append(BaslikOge(s, CTA_BASLIK, False, CTA_BASLIK[-1]))
            else:
                self.ogeler.append(BaslikOge(s, s.baslik, s.i == 0))
        self.lcd.append((0.0, "", "0", "", None, ""))
        self.resim_yeri: dict[int, tuple[float, float, float, float]] = {}
        if self.gun:
            self._gun_kur()
        for s in self.p:
            g = self.gorunum[s.i]
            if s.tur == "iceriden":
                self._not_kur(s)
            elif s.tur == "cta":
                self._cta_kur(s)
            elif g == "hesap":
                self._hesap_kur(s)
            if s.resim is not None and s.tur not in ("iceriden", "cta"):
                self._polaroid_kur(s)

    def _gorunur_gun(self, i0: int, i1: int | None = None) -> list[int]:
        """i0'dan (i1 hariç) gün akışı görünümündeki sahneler."""
        return [j for j in range(i0, len(self.p) if i1 is None else i1) if self.gorunum[j] == "gun"]

    def _yazi_sigdir(self, metin: str, room: float, sizes, col=MAVI, seed=0) -> Yazi:
        for size in sizes:
            y = Yazi(metin, size, col, seed)
            if y.w <= room:
                return y
        size = sizes[-1]
        while len(metin) > 2:
            metin = metin[:-1].rstrip(" ,.;:-–")
            y = Yazi(metin + "…", size, col, seed)
            if y.w <= room:
                return y
        return Yazi(metin, size, col, seed)

    def _gun_kur(self) -> None:
        """Gün akışı: her durak kendi saatinin çizgisine ('07:30' kırmızı + olay mavi), devam sahnesinin başlığı
        durağın altına küçük not olarak yazılır. Önceki durak bir sonraki durak başlayınca tiklenir; şimdiki durağın
        altından fosforlu kalem geçer."""
        def sag(s: Sahne) -> float:                     # kendi polaroidi olan sahnenin yazısı polaroide değmez
            return 590.0 if s.resim is not None else X1 - 40.0
        duraklar = [s for s in self.p if s.tur == "durak" and self.gorunum[s.i] == "gun"]
        son_satir, son_durak = -1, None
        self.giris: dict[int, tuple[int, float]] = {}     # sahne -> (satır, taban y)
        L = len(self.icerik)
        for s in self.p:
            if self.gorunum[s.i] != "gun" or s.i == 0:
                continue
            nxt = next((d for d in duraklar if d.i > s.i), None)
            lim = min(L, self.satir(nxt.dakika) if nxt else L)
            gor = self._gorunur_gun(s.i)
            ani = self.kelime_ani(s, " ".join(s.baslik).split())
            t0 = s.start + 0.3 if ani is None else K.clamp(ani[0], s.start + 0.3, max(s.start + 0.3, s.end - 1.4))
            if s.tur == "durak":
                k = min(L - 1, max(self.satir(s.dakika), son_satir + 1))
                y = self.icerik[k] - 9
                saat = Yazi(s.saat, 38, RED, tohum("saat", s.i))
                x_txt = 92 + saat.w + 18
                metin = cumle(" ".join(s.baslik))
                room = sag(s) - x_txt
                satirlar = [self._yazi_sigdir(metin, 10 ** 6, (50,), seed=tohum("giris", s.i))]
                if satirlar[0].w > room:
                    tek = self._yazi_sigdir(metin, room, (48, 46, 44, 42, 40), seed=tohum("giris", s.i))
                    kel = metin.split()
                    iki = None
                    if k + 1 < lim and len(kel) > 1 and not tek.text.endswith(metin):
                        best = None
                        for j in range(1, len(kel)):
                            a, b = " ".join(kel[:j]), " ".join(kel[j:])
                            ya, yb = Yazi(a, 44, MAVI, tohum("giris", s.i)), Yazi(b, 44, MAVI, tohum("giris2", s.i))
                            if ya.w <= room and yb.w <= room and (best is None or abs(ya.w - yb.w) < best[0]):
                                best = (abs(ya.w - yb.w), [ya, yb])
                        iki = best[1] if best else None
                    satirlar = iki or [tek]
                dur = K.clamp(len(metin) * 0.045, 0.5, 1.3)
                self.ogeler.append(YaziOge(gor, saat, 92, y, t0=t0, dur=0.28))
                t = t0 + 0.32
                for j, yz in enumerate(satirlar):
                    yy = self.icerik[k + j] - 9
                    d = dur * yz.w / max(1.0, sum(z.w for z in satirlar))
                    self.ogeler.append(YaziOge(gor, yz, x_txt, yy, t0=t, dur=d))
                    t += d
                son = satirlar[-1]
                yson = self.icerik[k + len(satirlar) - 1] - 9
                bitis = t
                # şimdiki durağın fosforu (sonraki durak başlayınca kalkar) ve tiki (sonraki durakta çizilir)
                fosfor_gor = self._gorunur_gun(s.i, nxt.i if nxt else None)
                for j, yz in enumerate(satirlar):
                    yy = self.icerik[k + j] - 9
                    self.ogeler.append(FosforOge(fosfor_gor, x_txt - 8, yy - yz.size * 0.52, x_txt + yz.w + 8,
                                                 yy + yz.size * 0.12, tohum("gf", s.i, j), t0=bitis + 0.05, dur=0.3))
                if nxt:
                    tx = x_txt + son.w + 16
                    self.ogeler.append(IzOge(self._gorunur_gun(nxt.i), Iz([el_tik(tx, yson - 4, 30, tohum("t", s.i))],
                                                                          5.0), t0=nxt.start + 0.25, dur=0.25))
                self.giris[s.i] = (k, yson)
                son_satir, son_durak = k + len(satirlar) - 1, s
            elif s.tur == "serbest" and son_durak is not None:
                k = son_satir + 1
                if k >= lim:
                    continue
                y = self.icerik[k] - 9
                metin = "– " + cumle(" ".join(s.baslik))
                x = 150
                yz = self._yazi_sigdir(metin, sag(s) - x, (38, 36, 34, 32, 30), seed=tohum("not", s.i))
                self.ogeler.append(YaziOge(gor, yz, x, y, t0=t0, dur=K.clamp(len(metin) * 0.045, 0.5, 1.2)))
                self.giris[s.i] = (k, y)
                son_satir = k

    # ------------------------------------------------------------ polaroid
    def polaroid(self, s: Sahne, w: float) -> Image.Image:
        """Bantlı polaroid (1x, eğik, sert gölgeli): çizim açık kâğıt zeminde, fotoğraf kırpılmış; alt boşlukta çizimde
        saat ya da başlık (el yazısı), fotoğrafta künye çipi."""
        pad, alt = 15, 62
        iw = w - 2 * pad
        h = pad + iw + alt
        m = 40
        pen = K.Pen(-m, -m, w + m, h + m)
        pen.rr((0, 0, w, h), 6, fill=POLAROID, outline=INK, width=4)
        if s.foto:
            src = Image.open(s.resim).convert("RGB")
            im = K.cover(src, int(iw * SS), int(iw * SS)).convert("RGBA")
            pen.paste(im, pad, pad)
            pen.rr((pad, pad, pad + iw, pad + iw), 2, outline=INK, width=3)
            note = K.credit_chip(s.kunye)
            if note:
                K.chip_label(pen, pad + 2, pad + iw + 8, note, size=22, rot=0.0, max_w=iw)
        else:
            pen.rr((pad, pad, pad + iw, pad + iw), 2, fill=(241, 236, 222))
            src = Image.open(s.resim).convert("RGBA")
            bb = src.getchannel("A").getbbox()
            if bb:
                src = src.crop(bb)
            q = (iw - 28) / max(src.width, src.height)
            d = src.resize((max(1, int(src.width * q * SS)), max(1, int(src.height * q * SS))), Image.LANCZOS)
            pen.paste(d, pad + iw / 2 - d.width / SS / 2, pad + iw / 2 - d.height / SS / 2)
            pen.rr((pad, pad, pad + iw, pad + iw), 2, outline=INK, width=3)
        im = pen.done()
        if not s.foto and s.saat:
            cap = s.saat
            yz = self._yazi_sigdir(cap, iw - 20, (34, 32, 30, 28), seed=tohum("pol", s.i))
            yz.put(im, m + w / 2, m + pad + iw + alt * 0.62, "m", clip=(0, 0, im.width, im.height))
        sp = K.Sprite(w + 2 * m, h + 2 * m, margin=0)
        sp.im.paste(im.resize((im.width * SS, im.height * SS), Image.LANCZOS), (0, 0))
        tape = K.Sprite(w + 2 * m, h + 2 * m, margin=0)
        K.tape(tape, m + w / 2, m + 2, 150, 40, -4 if s.i % 2 else 3, tohum("bant", s.i), alpha=205)
        sp.im.alpha_composite(tape.im)
        rot = 2.6 if s.i % 2 else -2.2
        out = sp.render(rot, shadow=(8, 10, 0, 0.9))
        bb = out.getchannel("A").getbbox()
        return out.crop(bb) if bb else out

    def _polaroid_kur(self, s: Sahne) -> None:
        """Polaroidin yeri: gün akışının kancasında sayfanın ortasında büyük; gün akışında durağın satırının sağında;
        hesapta sağ sütunda (yüksekliğe göre küçülür, makineye inmez)."""
        g = self.gorunum[s.i]
        if g == "gun" and s.i == 0:
            w = 470
            top = ICERIK_Y0 + 10
            cx = (X0 + X1) / 2 + 30
        elif g == "gun":
            w = 300
            k, y = self.giris.get(s.i, (None, None))
            if y is None:
                y = self.icerik[0]
            top = y - 22
            cx = X1 - w / 2 - 14
        else:
            yer = (X1 - 330, ICERIK_Y0 - 64, X1, self.alt)
            if s.i == 0:                                    # kanca: sayfada başka yazı yok, ortada
                yer = (X0 + 160, ICERIK_Y0 - 64, X1 - 160, self.alt)
            x0, y0, x1, y1 = self.resim_yeri.get(s.i, yer)
            w = min(330.0, x1 - x0, (y1 - y0) - 47 - 34)
            top = y0
            cx = (x0 + x1) / 2
        im = self.polaroid(s, w)
        hh = im.height
        top = K.clamp(top, ICERIK_Y0 - 70, self.alt + 10 - hh)
        anlik = s.i == 0
        self.ogeler.append(ResimOge([s.i], im, cx, top + hh / 2, t0=s.start + 0.22, anlik=anlik))

    # ------------------------------------------------------------ para: hesap satırları ve makine
    def _lcd_yaz(self, t_bitis: float, ust: str, deger: str, birim: str, tus: str | None, rozet: str,
                 hizli: bool = False) -> None:
        """LCD'de değerin tuşlanması: rakamlar soldan birer birer girer (t_bitis'te tamam), sonra tuş basılır."""
        txt = deger
        tam = re.sub(r"[^\d]", "", txt.split(",")[0].split("/")[0])
        if "/" in txt or not tam or hizli:
            self.lcd.append((t_bitis, ust, txt, birim, tus, rozet))
            return
        neg = txt.startswith("-")
        n = len(tam)
        for k in range(1, n + 1):
            ara = _fmt(int(tam[:k]), 0)
            self.lcd.append((t_bitis - (n - k) * 0.055 - 0.06, ust, ("-" if neg else "") + ara, birim, None, rozet))
        self.lcd.append((t_bitis, ust, txt, birim, tus, rozet))

    def lcd_at(self, t: float) -> tuple:
        j = max(0, bisect.bisect_right(self.lcd_t, t) - 1)
        e = self.lcd[j]
        tus = e[4] if (t - e[0]) < 0.2 else None
        return e[1], e[2], e[3], tus, e[5]

    def _rozet(self, s: Sahne) -> str:
        metin = s.notu + " " + " ".join(w.text for w in self.words[s.a:s.b])
        return "TAHMİNİ" if re.search(r"tahmin|yaklaşık|ortalama", metin, re.I) else ""

    @staticmethod
    def el_tutar(s: str) -> str:
        """'20 MİLYON ₺' -> '20 milyon ₺' (el yazısında birimler küçük harf)."""
        return re.sub(r"[A-ZÇĞİÖŞÜ]{2,}", lambda m: K.tr_lower(m.group(0)), s.strip()).replace("−", "-")

    def _ozet(self, s: Sahne) -> list[tuple[str, str]]:
        """Önceki para duraklarının özeti: (etiket, tutar)."""
        out = []
        for q in self.p[:s.i]:
            if q.tur == "sayac" or (q.tur == "kanca" and q.deger):
                out.append((cumle(q.etiket or " ".join(q.baslik)), self.el_tutar(q.deger)))
            elif q.tur == "fis" and q.deger:
                out.append((cumle(q.etiket or "Toplam"), self.el_tutar(q.deger)))
        return out

    def _satir_oge(self, gor, y, sol: str, sag: str, x_r: float, t0: float, size: float, seed, sag_renk=MAVI,
                   anlik=False, sag_t0=None, sol_x=92, nokta=True, hizli=False,
                   sure: float | None = None) -> tuple[Yazi, Yazi, float]:
        """'Kalem ........ tutar' satırı: kalem solda, tutar sağa yaslı, arada seyrek noktalar. sure: satırın en çok
        bu kadar sn'de yazılması (sıradaki satır başlamadan biter). (sol, sağ, bitiş)."""
        a = self._yazi_sigdir(sol, max(60.0, x_r - sol_x - 60 - Yazi(sag, size, sag_renk, seed).w), (size, size - 2,
                              size - 4, size - 6), seed=seed) if sol else None
        b = Yazi(sag, size + 2, sag_renk, seed + 1) if sag else None
        da = (0.16 if hizli else K.clamp(len(sol) * 0.04, 0.3, 0.8)) if sol else 0.0
        db = (0.12 if hizli else K.clamp(len(sag) * 0.045, 0.3, 0.7)) if sag else 0.0
        if sure is not None and da + db + 0.1 > sure:
            f = max(0.05, sure - 0.1) / max(1e-6, da + db)
            da, db = da * f, db * f
        if a:
            self.ogeler.append(YaziOge(gor, a, sol_x, y, t0=t0, dur=da, anlik=anlik))
        tb = (t0 + da + 0.1) if sag_t0 is None else max(sag_t0, t0 + da + 0.05)
        if a and b and nokta:
            x, pts = sol_x + a.w + 20, []
            while x < x_r - b.w - 18:
                pts.append([(x, y - 2), (x + 1.6, y - 2.4)])
                x += 22
            if pts:
                self.ogeler.append(IzOge(gor, Iz(pts, 4.2), t0=t0 + da, dur=max(0.05, tb - t0 - da), anlik=anlik))
        if b:
            self.ogeler.append(YaziOge(gor, b, x_r, y, "r", t0=tb, dur=db, anlik=anlik))
        return a, b, tb + db

    def _hesap_kur(self, s: Sahne) -> None:
        """Para görünümü: önceki durakların özeti (yazılmış, tikli) ve sahnenin hesabı: sayaçta '+ etiket' ve çift
        çizgili tutar, fişte satırlar, çizgi ve '= toplam'. LCD tuşlanır."""
        gor = [s.i]
        lines = self.icerik
        L = len(lines)
        x_r = X1 - 14
        if s.resim is not None:
            x_r = 590
            self.resim_yeri[s.i] = (610, lines[0] - 60, X1, self.alt)
        rozet = self._rozet(s)
        anlik = s.i == 0
        blok: list = []
        if s.tur == "sayac" or (s.tur == "kanca" and s.deger):
            blok = ["etiket", "deger"] + (["not"] if s.notu else [])
        elif s.tur == "fis":
            blok = ["satir"] * len(s.satirlar) + ["toplam"] + (["not"] if s.notu else [])
        need = len([b for b in blok if b != "not"])
        if len(blok) > L:                               # not sığmıyorsa yazılmaz (LCD rozeti 'TAHMİNİ' der)
            blok = [b for b in blok if b != "not"]
        ozet = self._ozet(s)
        bos = L - len(blok) - (1 if blok and ozet else 0)
        ozet = ozet[-bos:] if bos > 0 else []
        k = 0
        for lab, val in ozet:                           # özet: makas eski hesabı kesince hızla yeniden yazılır, tikli
            y = lines[k] - 9
            t_oz = s.start + CUT * 0.8 + 0.08 * k
            a, b, bit = self._satir_oge(gor, y, lab, val, x_r - 44, t_oz, 36, tohum("oz", s.i, k), hizli=True)
            self.ogeler.append(IzOge(gor, Iz([el_tik(x_r - 30, y - 4, 26, tohum("ozt", s.i, k))], 4.4), t0=bit,
                                     dur=0.12))
            k += 1
        if ozet and blok:
            k += 1 if (L - k) > need else 0
        lab = s.etiket or " ".join(s.baslik)
        if s.tur == "sayac" or (s.tur == "kanca" and s.deger):
            ani = self.kelime_ani(s, lab.split())
            t_lab = s.start + 0.3 if ani is None else K.clamp(ani[0], s.start + 0.3, s.end - 1.6)
            v = self.kelime_ani(s, [], rakam=s.deger)
            t_land = K.clamp(v[0] if v else t_lab + 1.0, t_lab + 0.6, max(t_lab + 0.6, s.end - 0.9))
            y = lines[k] - 9
            a = self._yazi_sigdir("+ " + cumle(lab), x_r - 92, (42, 40, 38, 36), seed=tohum("et", s.i))
            self.ogeler.append(YaziOge(gor, a, 92, y, t0=t_lab, dur=K.clamp(len(lab) * 0.045, 0.4, 0.9), anlik=anlik))
            y2 = lines[min(L - 1, k + 1)] - 9
            b = self._yazi_sigdir(self.el_tutar(s.deger), x_r - 120, (60, 56, 52, 48), seed=tohum("dg", s.i))
            self.ogeler.append(YaziOge(gor, b, x_r, y2, "r", t0=t_land - 0.1, dur=K.clamp(len(s.deger) * 0.05, 0.35,
                                                                                             0.7), anlik=anlik))
            bx0 = x_r - b.w
            iz = Iz([el_cizgi(bx0 - 12, y2 + 12, x_r + 6, y2 + 9, tohum("c1", s.i)),
                     el_cizgi(bx0 - 6, y2 + 23, x_r + 2, y2 + 20, tohum("c2", s.i))], 4.4)
            self.ogeler.append(IzOge(gor, iz, t0=t_land + 0.55, dur=0.3, anlik=anlik))
            if "not" in blok and k + 2 < L:
                n = self._yazi_sigdir("*" + s.notu, x_r - 96, (32, 30, 28), col=RED, seed=tohum("nt", s.i))
                self.ogeler.append(YaziOge(gor, n, 96, lines[k + 2] - 12, t0=t_land + 0.9, dur=0.6, anlik=anlik))
            dg, br = lcd_degeri(s.deger)
            if dg and lcd_sigar(dg, 12 if not br else 11):
                self._lcd_yaz(0.0 if anlik else t_land + 0.1, up(lab), dg, br, "=", rozet, hizli=anlik)
            self.olay[s.i] = t_land
        elif s.tur == "fis":
            satirlar = s.satirlar
            n = len(satirlar)
            # satırlar sırayla yazılır (biri bitmeden öteki başlamaz); kalem dış seste geçiyorsa o an başlar
            t0 = s.start + max(0.3, CUT)
            t_end = max(t0 + 0.6 * n, s.end - 1.5)       # toplamdan önce satırların bittiği an
            d = min(1.25, (t_end - t0) / max(1, n))       # satır başına yazma süresi
            times, prev, used = [], t0, -1
            for j, (kalem, tutar_) in enumerate(satirlar):
                latest = t_end - (n - j) * d
                ani = self.kelime_ani(s, kalem.split(), rakam=tutar_, sonra=used)
                t = prev
                if ani and prev <= ani[0] <= latest:
                    t, used = ani
                times.append(max(prev, min(t, latest)))
                prev = times[-1] + d
            toplam_ani = self.kelime_ani(s, [], rakam=s.deger, sonra=used)
            t_tot = max(prev + 0.25, toplam_ani[0] if toplam_ani else prev + 0.4)
            t_tot = min(t_tot, max(prev + 0.25, s.end - 0.7))
            acc, birim = 0.0, ""
            for j, ((kalem, tutar_), t) in enumerate(zip(satirlar, times)):
                y = lines[k + j] - 9
                neg = tutar_.strip()[:1] in "-−–"
                _, _, bit = self._satir_oge(gor, y, cumle(kalem), self.el_tutar(tutar_), x_r, t, 38,
                                            tohum("fs", s.i, j), sag_renk=RED if neg else MAVI, sure=d - 0.06)
                tv = tutar(tutar_)
                if tv is not None:
                    acc += tv[0]
                    _, br = lcd_degeri(tutar_)
                    birim = birim or br
                    dg, _ = lcd_degeri(tutar_.lstrip("-−– "))
                    if dg and lcd_sigar(dg):
                        self._lcd_yaz(bit, up(kalem), dg, birim, "−" if neg else "+", rozet)
                        dd = 0 if abs(acc - round(acc)) < 1e-6 else 2
                        self.lcd.append((bit + 0.2, "ARA TOPLAM", ("-" if acc < 0 else "") + _fmt(abs(acc), dd), birim,
                                         "−" if neg else "+", rozet))
            yl = lines[k + n - 1] - 9
            self.ogeler.append(IzOge(gor, Iz([el_cizgi(88, yl + 16, x_r + 6, yl + 13, tohum("fc", s.i))], 4.2),
                                     t0=max(prev - 0.05, t_tot - 0.35), dur=0.25))
            yt = lines[min(L - 1, k + n)] - 9
            etiket = "= " + cumle(s.etiket or "Toplam")
            a, b, bit = self._satir_oge(gor, yt, etiket, self.el_tutar(s.deger), x_r, t_tot - 0.1, 40,
                                        tohum("ft", s.i), sag_t0=t_tot)
            if b is not None:
                bx0 = x_r - b.w
                iz = Iz([el_cizgi(bx0 - 12, yt + 12, x_r + 6, yt + 9, tohum("d1", s.i)),
                         el_cizgi(bx0 - 6, yt + 23, x_r + 2, yt + 20, tohum("d2", s.i))], 4.4)
                self.ogeler.append(IzOge(gor, iz, t0=bit + 0.05, dur=0.3))
            if "not" in blok and k + n + 1 < L:
                nt = self._yazi_sigdir("*" + s.notu, x_r - 96, (30, 28), col=RED, seed=tohum("fn", s.i))
                self.ogeler.append(YaziOge(gor, nt, 96, lines[k + n + 1] - 12, t0=bit + 0.4, dur=0.6))
            dg, br = lcd_degeri(s.deger)
            if dg and lcd_sigar(dg, 12 if not br else 11):
                self.lcd.append((t_tot, up(s.etiket or "TOPLAM"), dg, br or birim, "=", rozet))
            self.olay[s.i] = t_tot

    # ------------------------------------------------------------ içeriden: yapışkan not
    def _not_kur(self, s: Sahne) -> None:
        """Sarı yapışkan not: köşesinde kırmızı 'İÇERİDEN' etiketi; metin alıntı ya da sahnenin dış sesidir (dış ses
        kelime kelime söylenirken nota yazılır ve o sahnede alttaki dış ses satırı gizlenir; nota sığmazsa sahnenin
        başlığı yazılır, dış ses altta kalır). Son satırın altına kırmızı kalem çizgisi."""
        gun = self.gorunum[s.i] == "gun"
        nx0 = X0 + 22
        nw = (X1 - 40) - nx0
        iw = nw - 74
        if gun:
            dolu = [y for j, (k, y) in self.giris.items() if j < s.i]
            top = ICERIK_Y0 - 30
        else:
            dolu, top = [], self.icerik[0] - 64
        max_h = self.alt - 6 - top
        kelimeler = [w.text for w in self.words[s.a:s.b]]
        soz = not s.alinti and 0 < len(kelimeler) <= 26
        metin = s.alinti or (" ".join(kelimeler) if soz else cumle(" ".join(s.baslik)))
        ust_pay = 66                                     # etiketin altı: ilk satırın büyük harf üstü
        sec = None
        for size in (46, 44, 42, 40, 38, 36, 34, 32):
            lh = size * 1.4
            lines, cur = [], []
            for w in metin.split():
                cand = cur + [w]
                if cur and Yazi(" ".join(cand), size, MAVI, 0).w > iw:
                    lines.append(cur)
                    cur = [w]
                else:
                    cur = cand
            if cur:
                lines.append(cur)
            nh = ust_pay + size * 0.74 + (len(lines) - 1) * lh + 40
            if nh <= max_h:
                sec = (size, lh, lines, nh)
                break
        if sec is None:
            soz = False
            metin = cumle(" ".join(s.baslik))
            size = 40
            sec = (size, size * 1.4, [metin.split()], ust_pay + size * 0.74 + 40)
        size, lh, lines, nh = sec
        if gun and dolu:                                 # mümkünse son yazılan satırın altına yapışır
            top = K.clamp(max(dolu) + 74, top, self.alt - 6 - nh)
        if soz:
            self.sessiz[s.i] = s.a
        # not gövdesi (sayfa koordinatlarında)
        m = 46
        x0, y0, x1, y1 = nx0, top, nx0 + nw, top + nh
        pen = K.Pen(x0 - m, y0 - m, x1 + m, y1 + m)
        curl = 46
        body = [(x0, y0), (x1, y0), (x1, y1 - curl), (x1 - curl * 0.9, y1 - curl * 0.15), (x1 - curl, y1), (x0, y1)]
        pen.poly([(x + 8, y + 10) for x, y in body], INK + (235,))
        pen.poly(body, INK)
        inner = [(x0 + 4, y0 + 4), (x1 - 4, y0 + 4), (x1 - 4, y1 - curl - 1), (x1 - curl * 0.9 - 1, y1 - curl * 0.15 - 3),
                 (x1 - curl - 1, y1 - 4), (x0 + 4, y1 - 4)]
        pen.poly(inner, YELLOW)
        pen.rr((x0 + 4, y0 + 4, x1 - 4, y0 + 30), 0, fill=tuple(int(c * 0.955) for c in YELLOW))
        pen.poly([(x1 - curl * 0.98, y1 - curl * 0.2), (x1 - 6, y1 - curl - 2), (x1 - curl * 0.55, y1 - curl * 0.5)],
                 tuple(int(c * 0.8) for c in YELLOW))
        lw = N.label_w("İÇERİDEN", 42)
        N.paste_label(pen, "İÇERİDEN", 42, OFF, RED, tohum("ic", s.i), x0 + 26 + lw / 2, y0 + 4, rot=-3.0,
                      shadow=(5, 6, 0, 0.9))
        if s.alinti and s.notu:
            kaynak = K.fit("— " + s.notu, "courier", 28, nw - lw - 90)
            pen.text(x1 - 30, y0 + 52, kaynak, "courier", 28, DGREY, anchor="rs")
        govde = pen.done()
        # satırlar (sözle eşli ya da sırayla yazılır)
        satirlar: list[YaziOge] = []
        wi = s.a
        y = y0 + ust_pay + size * 0.74
        t = s.start + 0.42
        for li, L in enumerate(lines):
            yz = Yazi(" ".join(L), size, MAVI, tohum("nt", s.i, li))
            zaman = None
            if soz:
                zaman = []
                for j, w in enumerate(L):
                    wd = self.words[wi] if wi < len(self.words) else None
                    ta, tb = (wd.start - 0.04, max(wd.start + 0.08, wd.end - 0.04)) if wd else (s.end, s.end + 0.1)
                    if j:
                        zaman.append((ta - 0.02, ta))      # boşluk
                    zaman += [(ta + (tb - ta) * c / max(1, len(w)), ta + (tb - ta) * (c + 1) / max(1, len(w)))
                              for c in range(len(w))]
                    wi += 1
                satirlar.append(YaziOge([s.i], yz, x0 + 36, y, kelime=zaman))
            else:
                d = K.clamp(len(yz.text) * 0.035, 0.3, 0.9)
                satirlar.append(YaziOge([s.i], yz, x0 + 36, y, t0=t, dur=d))
                t += d
            y += lh
        son = satirlar[-1]
        bitis = (self.words[s.b - 1].end if soz and s.b > s.a else t) + 0.1
        yl = son.y + size * 0.3
        cizgi = IzOge([s.i], Iz([el_cizgi(x0 + 30, yl + 2, x0 + 40 + son.yazi.w, yl - 2, tohum("nc", s.i), amp=1.2)],
                                5.0, RED), t0=bitis, dur=0.3)
        self.ogeler.append(NotOge([s.i], govde, (x0 - m, y0 - m), satirlar, [cizgi], s.start + 0.12))
        self.olay[s.i] = s.start + 0.12

    # ------------------------------------------------------------ son sahne
    def _cta_kur(self, s: Sahne) -> None:
        """'Senin listen:' ve boş, elle çizilmiş üç satır; sayfada duran bir tükenmez kalem; 'Yorumlara yaz'
        söylenince YORUMLARA YAZ ↓ etiketi. Soru söylenmeye başlayınca dış ses satırı gizlenir (başlık sorudur)."""
        gor = [s.i]
        lines = self.icerik
        L = len(lines)
        t0 = s.start + 0.45
        genis = not self.para and L >= 8                # gün akışının sayfası: liste iki satırda bir, büyük
        adim = 2 if genis else 1
        ts, ns, ks, cx1, kw = (56, 52, 38, 660, 380) if genis else (46, 42, 30, 540, 330)
        y = lines[0] - 9
        self.ogeler.append(YaziOge(gor, Yazi("Senin listen:", ts, MAVI, tohum("cta", s.i)), 92, y, t0=t0, dur=0.55))
        t = t0 + 0.6
        son_y = y
        for j in range(3):
            yy = lines[min(L - 1, (1 + j) * adim)] - 9
            kutu = Iz([el_kutu(96 + ks / 2, yy - ks / 2, ks, tohum("ck", j))], 3.8)
            self.ogeler.append(IzOge(gor, kutu, t0=t, dur=0.18))
            nx = 96 + ks + 14
            self.ogeler.append(YaziOge(gor, Yazi(f"{j + 1}.", ns, MAVI, tohum("cn", j)), nx, yy, t0=t + 0.16,
                                       dur=0.15))
            x1 = cx1 - 50 * (j % 2)
            self.ogeler.append(IzOge(gor, Iz([el_cizgi(nx + ns * 1.3, yy + 2, x1, yy, tohum("cc", j), amp=1.0)],
                                             3.6), t0=t + 0.3, dur=0.22))
            t += 0.42
            son_y = yy
        im, _ = kalem(kw, 16)
        ky = lines[min(L - 1, 2 * adim)] - im.height / 2 - (40 if genis else 20)
        self.ogeler.append(ResimSabit(gor, im, X1 - 10 - im.width, ky, t0=t))
        # 'Yorumlara yaz' söylendiği an (yoksa sahnenin %60'ı)
        t_y = None
        for wi in range(s.a, s.b - 1):
            if YORUM_RE.search(self.words[wi].text + " " + self.words[wi + 1].text):
                t_y = self.words[wi].start - 0.08
                break
        if t_y is None:
            t_y = s.start + 0.6 * (s.end - s.start)
        for wi in range(s.a, s.b - 1):
            if K._bare(self.words[wi].text) == "sen" and K._bare(self.words[wi + 1].text).startswith("olsa"):
                self.sessiz[s.i] = wi
                break
        im = yorum_etiketi(94 if genis else 62, tohum("yy", s.i))
        alt = self.alt - 10
        yb = min(son_y + (130 if genis else 56), alt - im.height)
        self.ogeler.append(EtiketOge(gor, im, X0 - 2, yb, t_y, nabiz=True))
        self.olay[s.i] = t_y

    # ------------------------------------------------------------ dış ses
    def anlati(self, img: Image.Image, si: int, t: float) -> None:
        s = self.p[si]
        b = self.sessiz.get(si, s.b)
        if b <= s.a:
            return
        if si not in self._speech:
            self._speech[si] = Anlati(self.words, s.a, b, ANLATI, sizes=(36, 34, 32), max_lines=2, lh=1.34)
        sp = self._speech[si]
        if not sp.pages:
            return
        cur = bisect.bisect_right(self.starts, t + 0.03) - 1
        if cur >= b and si in self.sessiz:
            return
        if si == len(self.p) - 1 and t > self.words[s.b - 1].end + 0.35:
            cur = b
        cur = min(max(cur, s.a), b)
        sp.put(img, cur)

    # ------------------------------------------------------------ Makas
    def makas(self, img: Image.Image, si: int, t: float, lt: float) -> None:
        s = self.p[si]
        olay = self.olay.get(si)
        if s.maskot in K.MOODS:
            mood = s.maskot
        elif s.tur == "kanca":
            mood = "surprised"
        elif s.tur == "cta":
            mood = "happy"
        elif s.tur == "iceriden":
            mood = "thinking"
        elif s.tur in ("sayac", "fis"):
            mood = "surprised" if (olay is not None and t >= olay + 0.3) else "thinking"
        else:
            mood = "normal"
        point = POINT if mood in ("normal", "thinking") else None
        mouth = K.talk_state(self.words, self.starts, t)
        blink = (t % 3.6) > 3.45 and mood not in ("happy", "surprised")
        im = self.mascot.sprite(mood, mouth, blink, point, MAKAS_OLCEK)
        bob = round(3 * math.sin(t * 2 * math.pi * 0.55))
        hop = -18 * math.sin(math.pi * K.clamp(lt / 0.3)) if si > 0 and lt < 0.3 else 0.0
        ox, oy = N.Mascot.origin(*MAKAS_XY, MAKAS_OLCEK)
        K.put(img, im, ox, oy + bob + hop)

    # ------------------------------------------------------------ kesme
    def kesik(self, si: int) -> tuple[Image.Image, tuple, tuple]:
        """si sahnesine geçerken makasın kestiği eski katman: önceki sahnenin başlığı ve bu sahnede görünmeyecek
        (kesilen) içeriği, son hâliyle. (katman, köken, kesme kutusu)"""
        if si in self._cut:
            return self._cut[si]
        t = self.p[si].start - 1e-3
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        icerik = False
        for o in self.ogeler:
            if o.kes and o.gorunur(si - 1) and not o.gorunur(si):
                o.draw(self, lay, t)
                icerik = icerik or not isinstance(o, BaslikOge)
        self.kalem_ucu = None
        y0, y1 = 236, int(self.alt + 12)
        out = (lay.crop((0, y0, SAFE[2], y1)), (0, y0),
               (X0, BAS_Y0, X1, self.alt) if icerik else (X0, BAS_Y0, BAS_X1, BAS_Y1))
        self._cut = {si: out}
        return out

    # ------------------------------------------------------------ kare
    def scene_at(self, t: float) -> int:
        return max(0, bisect.bisect_right(self.scene_starts, t) - 1)

    def frame(self, t: float, grain: bool = True) -> Image.Image:
        si = self.scene_at(t)
        s = self.p[si]
        lt = t - s.start
        img = self.taban(si == 0).copy()
        rule = self.cift_cizgi()
        oy = TARIH_CIZGI - 6
        if self.intro and t < 0.8:                     # açılış: makas basılı çift çizgiyi soldan sağa keser
            x = K.lerp(X0, X1, K.ease_in_out(t / 0.8))
            if x > X0:
                K.put(img, rule.crop((0, 0, int(x), rule.height)), 0, oy)
            sc = K.scissors_icon(64, 32 if int(t * 24) % 2 else 12)
            K.put(img, sc, x - 64 * 58 / 124, TARIH_CIZGI + 3 - sc.height / 2)
        else:
            K.put(img, rule, 0, oy)
        self.ilerleme(img, si, t)
        self.kalem_ucu = None
        for o in self.ogeler:
            if o.gorunur(si):
                o.draw(self, img, t)
            elif o.cikis and si > 0 and o.gorunur(si - 1) and lt < o.cikis:
                o.exit(self, img, t, lt / o.cikis)
        if si > 0 and lt < CUT:
            old, origin, box = self.kesik(si)
            bot = int(self.alt + 12)
            K.card_cut(img, old, lt, si, origin=origin, card=box, x_end=SAFE[2] - 66,
                       clip_top=(0, 236, SAFE[2], bot), clips_bot=((0, 236, SAFE[2], bot),))
        self.anlati(img, si, t)
        if self.hm is not None:
            ust, deger, birim, tus, rozet = self.lcd_at(t)
            lay = self.hm.layer(ust, deger, birim, tus, rozet)
            K.put(img, lay, *HesapMakinesi.origin(lay))
        if self.kalem_ucu is not None:
            kalem_ucu(img, *self.kalem_ucu)
        self.makas(img, si, t, lt)
        if self.brand is not None and self.brand.on:
            self.brand.watermark(img, t, 0.8 if self.intro else 0.0)
        return K.finish(img) if grain else img.convert("RGB")


# ---------------------------------------------------------------- ana giriş
def render(scenes: list[SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
           music: Path | None, meta: dict) -> Path:
    """Ajanda şablonuyla videoyu kurar. Kare döngüsü, ses, kuyruk ve marka kapanışı kart şablonuyla ortak
    (kart.render_frames)."""
    return K.render_frames(scenes, words, out_mp4, voice_mp3, music,
                           lambda bcfg: AjandaVideo(scenes, words, meta, bcfg), "Ajanda")
