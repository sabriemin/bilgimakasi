"""Ya Sen Olsaydın? şablonu ("Ajanda", 2. sürüm): resim önde, ajanda çerçevede.

Sabri'nin ilk sürüme itirazı: hesap makinesi fikri yerinde ama ekranı yiyordu; video Tesla'yı anlatıyor ama ne Tesla'nın
resmi ne fuar ne de kablosuz enerji kulesi görünüyordu. Bu sürümde her sahnenin resmi (fotoğraf ya da çizim) ekranın
büyük kısmını kaplar ve sürekli hareket eder; ajanda kimliği üst şerit, tarih damgası ve tükenmez notlarıyla korunur;
hesap makinesi yalnız para sahnelerinde köşeden gelen küçük bir yardımcıdır.

Ekran düzeni (1080x1920). Yazı yalnız x ≤ 935, y 170-1540 arasında; gölgeler dahil hiçbir yazı öğesi platform
arayüzüne taşmaz. Yalnız sahnenin baskısı (resim katmanı) yatayda kenara kadar uzanabilir (filigran 120-228'de):
  238-318   ajanda şeridi: solda seri etiketi; kancada "YA SEN OLSAYDIN? #1" ve sağda basılı tarih ("BİR ÖMÜR · YIL
            YIL", "BİR AYIN HESABI", "BİR İŞ GÜNÜ · SAAT SAAT"), diğer sahnelerde sağda DURAK k/N ve elle çizilmiş
            kutular (geçilen duraklar tikli). Altında basılı çift çizgi (açılışta makas keser).
  340-1500  sahnenin baskısı: beyaz kenarlı, köşelerinden bantlı, neredeyse tam genişlikte bir baskı (iç alan
            984x1132, karenin %59'u). Fotoğrafta yavaş Ken Burns (yakınlaşma + kayma); çizimde kâğıt zemin ile çizim
            ayrı hızlarda kayar (paralaks). Resim yoksa sayfa boş kalmaz: sahnenin tema renginde büyük yıl / saat /
            sayı afişi (o da yoksa soru işareti ya da makas). Sahneler arası geçiş sırayla kayma, bant çevirme ve
            makas kesmesidir.
  baskının üstünde:
    sol üst    kicker'daki yıl ya da saat kırmızı lastik damga olarak iner ve tükenmez mavisiyle halkalanır (ajandada
               günü daire içine almak); yıl / saat değilse kicker beyaz kâğıda tükenmezle yazılıp bantlanır
    para       büyük sayı resmin üstünde sayarak yükselir ve card_label damgasıyla oturur; fişte satırlar dar bir kâğıt
               şeridine yazılır; küçük sarı hesap makinesi "MAKAS-12" sağ üst köşeden kayarak gelir, yürüyen toplamı
               gösterir, sahne bitince geri çekilir (sonraki sahne de paraysa yerinde kalır)
    içeriden   sarı yapışkan not; dış ses söylendikçe nota tükenmezle yazılır
    son sahne  "Senin listen:" kâğıdı, sayfada duran tükenmez kalem, "Yorumlara yaz" söylenince YORUMLARA YAZ ↓
  ~1030-1386 başlık (Anton) yırtık kâğıt etiketlerde, sol altta (x ≤ 700); vurgulu satır sarı kâğıtta, SEN / SANA /
            SENİN tükenmez mavisiyle halkalanır (serinin imzası). Sağında Makas başlığı gösterir.
  1402-1530 dış ses şeridi: kâğıt üstünde Courier, okunan kelimenin altından fosforlu kalem geçer.

Senaryo eşlemesi (pipeline.build spec.card'a sahnenin bütün alanlarını, spec.image'a fotoğrafı, spec.sprite'a
çizimi koyar): fotoğraf varsa o, yoksa çizim, ikisi de yoksa afiş. İlk sahne kanca, son sahne cta; card counter /
receipt sahneleri hesap durakları (kart.card_type ile aynı kural), interstitial / quote sahneleri içeriden notu;
kicker'ı saat ("07:30") ya da yıl ("1884") olan sahneler zaman çizgisinin durakları, diğerleri önceki durağın devamı.

Hız: sayfa, şerit, baskı çerçevesi, damgalar ve etiketler video ya da sahne başına bir kez çizilir; kare başına yalnız
Ken Burns penceresi (kutulu yeniden örnekleme) ve katmanlar birleştirilir. Rastgelelik metin ve sahne numarasıyla
tohumlanır: aynı videonun kareleri her çalıştırmada aynıdır.
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
from PIL import Image, ImageDraw, ImageFilter, ImageOps

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
MAVI_SOLUK = (128, 150, 196)
SAYFA = (248, 245, 236)              # ajanda kâğıdı (marka kâğıdının sıcak açığı)
SONUK = (150, 146, 138)              # dış seste sıradaki kelimeler
FOSFOR = (253, 226, 74)              # fosforlu kalem
LCD_BG, LCD_GHOST, LCD_INK = (201, 205, 190), (189, 193, 178), (30, 32, 29)
POLAROID = (252, 251, 247)           # baskının beyaz kenarı
KAGIT_ZEMIN = {"yellow": (252, 232, 150), "red": (246, 205, 196)}   # çizim zemini (diğer temalarda krem)
KREM = (241, 236, 222)

# ---------------------------------------------------------------- yerleşim
X0, X1 = 72, 920                     # yazı alanı
SAFE = K.SAFE                        # (0, 170, 935, 1540)
CLIP = (0, SAFE[1], SAFE[2], SAFE[3])
BASKI_CLIP = (0, SAFE[1], W, SAFE[3])  # baskı (resim) katmanı: yatayda kenara uzanabilir, dikeyde güvenli bantta
SIRA_CY = 279                        # ajanda şeridinin ortası (seri etiketi, DURAK)
TARIH_CIZGI = 326                    # şeridin altındaki basılı çift çizgi
MAKINE_CLIP = (0, TARIH_CIZGI + 14, SAFE[2], SAFE[3])   # makine şeridin altından çıkar: üstü çizginin altında kalır
BASKI = (34, 340, 1046, 1500)        # baskının dış kenarı (beyaz kenar dahil)
KENAR = 14
FOTO = (BASKI[0] + KENAR, BASKI[1] + KENAR, BASKI[2] - KENAR, BASKI[3] - KENAR)   # resmin göründüğü iç alan
KB = 1.16                            # Ken Burns payı: kaynak, iç alandan bu kadar büyük hazırlanır
BAS_X1 = 700                         # başlık etiketleri en çok buraya kadar (sağında Makas)
BAS_Y1 = 1386                        # son başlık etiketinin alt kenarı
BAS_YMIN = 1020                      # başlık bloğunun en üst sınırı
SERIT = (52, 1400, 920, 1522)        # dış ses şeridi (kâğıt; gölgesiyle 1540'ın üstünde biter)
ANLATI = (X0 + 8, 1414, 900, 1514)   # dış ses metni
UST0 = FOTO[1] + 22                  # baskı üstü öğelerin en üst sınırı (damga, makine)
DAMGA_X = 70
MAKAS_XY, MAKAS_OLCEK = (834, 1296), 0.5
MAKAS_UST = MAKAS_XY[1] - 186        # Makas'ın (kolu dahil) üst sınırı: sağdaki notlar bunun üstünde biter
POINT = 212.0                        # Makas'ın kolu: sol-yukarı (başlığı gösterir)
CALC_W, CALC_H = 838, 410            # hesap makinesi tasarım ölçüsü (küçültülmeden önce)
CALC_OLCEK = 0.44                    # ekranda: ~370x180, karenin ~%3,5'i
CALC_X1, CALC_Y = 928, UST0 - 4      # makinenin (gölge dahil) sağ kenarı ve üst kenarı
CALC_ROT = -3.0
CALC_GIRIS = 0.32                    # köşeden kayarak gelme / geri çekilme süresi
LCD_BOX = (44, 96, CALC_W - 44, 262)
TUSLAR = ("AC", "÷", "×", "−", "+", "=")
SEN_RE = re.compile(r"^(SEN|SANA|SENİ|SENİN|SENDE|SENDEN|SENCE|SENİNLE|SENİNKİ|SENİNKİNİ)\W*$")
SAAT_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)(?!\d)")
YIL_RE = re.compile(r"(?<![\d.,])(1[0-9]\d\d|20\d\d)(?![\d.,]?\d)")
SAYI_RE = re.compile(r"(?<![\w])(%?\d[\d.,]*\d|%?\d)")
YORUM_RE = re.compile(r"\byorumlara\s+yaz", re.I)
AYLAR = ("OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK")
GUNLER = ("PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR")
SERI_ADI = STRUCTURES["olsaydin"][0]  # "YA SEN OLSAYDIN?" (kalıp listesinden: ad değişirse burası da değişir)
CTA_BASLIK = ["SEN OLSAN", "NE YAPARDIN?"]
GECIS = 0.40                         # kayma ve bant çevirme geçişi
CUT = K.CUT_LEN                      # makas kesmesi (kart şablonuyla aynı süre)
YENI0 = 0.30                         # yeni başlığın belirmeye başladığı an
OGE0 = 0.46                          # baskı üstü öğelerin en erken belirdiği an (baskı yerine oturunca)
PARA_TURLERI = ("sayac", "fis")


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


def tarihsiz_baslik(tur) -> tuple[str, str, str, str]:
    """meta'da yayın tarihi yoksa kancadaki basılı tarih: somut gün yok. tur: 'para' (ya da True), 'yil', 'gun'
    (ya da False). ('BİR', 'AYIN', 'HESABI', '')"""
    tur = {True: "para", False: "gun"}.get(tur, tur)
    return {"para": ("BİR", "AYIN", "HESABI", ""), "yil": ("BİR", "ÖMÜR", "YIL YIL", "")}.get(
        tur, ("BİR", "İŞ GÜNÜ", "SAAT SAAT", ""))


def saat_of(kicker: str) -> tuple[str, int] | None:
    """kicker'daki saat: ('07:30', 450 dakika) ya da None."""
    m = SAAT_RE.search(kicker or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{mi:02d}", h * 60 + mi


def yil_of(metin: str) -> str:
    """Metindeki ilk yıl ('1884'te' -> '1884'); '1.200.000' gibi tutarlar yıl sayılmaz."""
    m = YIL_RE.search(metin or "")
    return m.group(1) if m else ""


def damga_of(kicker: str) -> str:
    """kicker'ın damgası: saat ('07:30') ya da yıl ('1884'); başka bir şeyse ''."""
    st = saat_of(kicker)
    return st[0] if st else yil_of(kicker)


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
    m = re.search(r"(\d[\d.,]*)\s*[-–]\s*(\d[\d.,]*)\s*(MİLYAR|MİLYON|BİN)?", s)
    if m:                                               # aralık: '55-65 BİN' -> 55.000-65.000 (çarpan ikisine de)
        ek = " " + m.group(3) if m.group(3) else ""
        a, b = tutar(m.group(1) + ek), tutar(m.group(2) + ek)
        if a and b:
            return f"{_fmt(a[0], 0)}-{_fmt(b[0], 0)}", birim
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



def sayac_metni(deger: str, f: float) -> str:
    """Büyük sayının sayarken görünen hâli: '276.000 $' f=0,5 -> '138.000 $'. Oran ya da aralık sayılmaz (tamamı)."""
    s = up(deger)
    if f >= 1 or "/" in s or re.search(r"\d\s*[-–]\s*\d", s):
        return s
    m = re.search(r"\d[\d.]*(?:,\d+)?", s)
    if not m:
        return s
    tok = m.group(0)
    tam, _, ondalik = tok.partition(",")
    try:
        v = float(tam.replace(".", "") + ("." + ondalik if ondalik else ""))
    except ValueError:
        return s
    dec = len(ondalik)
    ara = K.fmt_value(v * K.clamp(f), dec, "." in tam or v >= 10000)
    return s[:m.start()] + ara + s[m.end():]


# ---------------------------------------------------------------- senaryo -> sahne planı
@dataclass
class Sahne:
    i: int
    tur: str                        # kanca | durak | sayac | fis | iceriden | cta | serbest
    kart: str = "auto"              # kart.card_type sonucu
    saat: str = ""                  # '07:30' (gün akışı durağı)
    dakika: int = -1
    damga: str = ""                 # kicker'daki saat ya da yıl ('07:30', '1884')
    kicker: str = ""                # damga değilse kicker'ın kendisi (ör. 'WESTINGHOUSE ANLAŞMASI')
    durak: int = 0                  # durak sırası (1'den); durak olmayan sahnede o ana kadarki son durak
    baslik: list[str] = field(default_factory=list)
    hl: int = -1
    resim: Path | None = None       # fotoğraf (varsa) ya da çizim (sprite)
    foto: bool = False
    kunye: dict = field(default_factory=dict)
    tema: str = "paper"
    anlatim: str = ""
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

    @property
    def para(self) -> bool:
        return self.tur in PARA_TURLERI or (self.tur == "kanca" and bool(self.deger))


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
    onceki = ""
    for i, spec in enumerate(specs):
        c = spec.card or {}
        kt = K.card_type(_kart_spec(spec), i, n)
        s = Sahne(i, "serbest", kt)
        s.baslik = [up(x) for x in spec.headline if x and x.strip()]
        s.hl = spec.highlight_line if 0 <= spec.highlight_line < len(s.baslik) else -1
        if spec.image is not None:              # fotoğraf önce gelir: Tesla'nın kendi resmi çizimden değerlidir
            s.resim, s.foto, s.kunye = spec.image, True, dict(c.get("credit") or {})
        elif spec.sprite is not None:
            s.resim = spec.sprite
        s.tema = (getattr(spec, "theme", "") or c.get("theme") or "paper").strip().lower()
        s.anlatim = spec.narration or ""
        s.deger, s.etiket = up(c.get("card_value", "")), up(c.get("card_label", ""))
        s.notu = (c.get("card_note") or "").strip()
        s.satirlar = K.parse_receipt(c.get("card_lines"))
        s.maskot = c.get("mascot", "auto")
        if i > 0:
            s.damga = damga_of(spec.kicker)
            k = up(spec.kicker)
            if not s.damga and k and not k.startswith(SERI_ADI):
                s.kicker = k
            st = saat_of(spec.kicker)
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
        elif s.damga and s.damga != onceki:     # aynı yılın / saatin ikinci sahnesi durağın devamıdır
            s.tur = "durak"
        if s.damga:
            onceki = s.damga
        out.append(s)
    k = 0
    for s in out:
        if s.tur in ("durak", "sayac", "fis"):
            k += 1
        s.durak = k
    return out


# ---------------------------------------------------------------- dış ses (fosforlu kalemle okunan kelime)
class Anlati(N.Speech):
    """nasil.Speech'in sayfa bölme kuralları; kâğıt şerit üstünde: söylenmiş mürekkep, okunan fosforlu kalem üstünde
    mürekkep, sıradaki soluk. Son sayfada tek başına 1-3 kelime kalmasın ('lira.', '78 bin lira.' gibi): yetim
    kalırsa daha küçük puntolar (30'a dek) denenir; şerit iki satırlıktır."""
    YETIM = 3
    YEDEK = (30,)

    def __init__(self, words, a, b, rect, sizes=(36, 34, 32), max_lines=2, lh=1.34, breaks=()):
        super().__init__(words, a, b, rect, sizes=sizes, max_lines=max_lines, lh=lh, breaks=breaks)
        if not self._yetim():
            return
        for size in [z for z in tuple(sizes) + self.YEDEK if z <= self.size]:
            pages, _ = self._pages(size, set(breaks))
            if len(pages) == 1 or len(pages[-1]) > self.YETIM:
                self._kur(size, pages)
                return

    def _yetim(self) -> bool:
        return len(self.pages) >= 2 and self.pages[-1][1] - self.pages[-1][0] <= self.YETIM

    def _kur(self, size, pages) -> None:
        self.size = size
        self.pages = [(p[0], p[-1] + 1) for p in pages]
        self.page_starts = [p0 for p0, _ in self.pages]
        self.lines = {pi: self._balanced(list(range(p0, p1)), size) for pi, (p0, p1) in enumerate(self.pages)}
        self._img = {}

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
        # iki satırlık şeritte tek satır dikeyde ortalanır
        base = y0 + cap + 2 + (lh / 2 if len(lines) == 1 else 0)
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


# ---------------------------------------------------------------- hesap makinesi (küçük, ikincil)
class HesapMakinesi:
    """Sarı masa hesap makinesi 'MAKAS-12': isim plakası ve güneş paneli, LCD (üst satırda kalem ya da işlem, büyük 7
    bölmeli rakamlar, sağda birim), bir sıra işlem tuşu (basılan tuş sarı). Tasarım ölçüsünde (838x410) çizilir, eğilir
    ve CALC_OLCEK'e küçültülür: ekranda yalnız yürüyen toplamı gösteren küçük bir yardımcıdır."""

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
        """Makinenin o durumdaki eğik, küçültülmüş görüntüsü (sert gölge dahil)."""
        key = (ust, deger, birim, basili, rozet)
        if key in self._c:
            return self._c[key]
        im = self.body(basili).copy()
        pen = K.Pen(-20, -20, CALC_W + 20, CALC_H + 20)
        lx0, ly0, lx1, ly1 = LCD_BOX
        rx = lx1 - 18
        if rozet:
            rw = K.tw(rozet, "courier", 26) + 18
            pen.rr((rx - rw, ly0 + 14, rx, ly0 + 50), 5, outline=LCD_INK, width=3)
            pen.text(rx - rw / 2, ly0 + 42, rozet, "courier", 26, LCD_INK, anchor="ms")
            rx -= rw + 14
        if ust:
            size = 32
            room = rx - (lx0 + 20)
            while size > 24 and K.tw(ust, "courier", size) > room:
                size -= 1
            pen.text(lx0 + 20, ly0 + 44, K.fit_words(ust, "courier", size, room), "courier", size, LCD_INK)
        bw = 0.0
        if birim:
            bf, bs = ("plex", 66) if birim == K.TL else ("anton", 56)
            bw = K.tw(birim, bf, bs) + 16
            pen.text(lx1 - 18, ly1 - 22, birim, bf, bs, LCD_INK, anchor="rs")
        lcd_rakamlar(pen, lx0 + 12, ly0 + 60, lx1 - 18 - bw, deger or "0", 92, 12 if not birim else 11)
        im.alpha_composite(pen.done())
        k = CALC_OLCEK
        big = im.resize((int(im.width * k * SS), int(im.height * k * SS)), Image.LANCZOS)
        big = big.rotate(CALC_ROT, resample=Image.BICUBIC, expand=True)
        big = K.add_shadow(big, 7 * SS, 9 * SS, 0, 0.9)
        out = big.resize((big.width // SS, big.height // SS), Image.LANCZOS)
        if len(self._c) > 80:
            self._c.clear()
        self._c[key] = out
        return out


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


# ---------------------------------------------------------------- damga, kâğıt parçası, etiket
def _asindir(a: np.ndarray, seed: int, oran: float = 0.10) -> np.ndarray:
    """Lastik damga aşınması: düşük frekanslı mürekkep dalgası + ince boşluklar (alfa dizisi 0..1)."""
    rng = np.random.default_rng(seed)
    h, w = a.shape
    blot = rng.normal(0, 1, (h // 16 + 2, w // 16 + 2)).astype(np.float32)
    blot = np.asarray(Image.fromarray(blot).resize((w, h), Image.BICUBIC))
    keep = np.clip(0.86 + 0.22 * blot, 0.35, 1.0) * (rng.random((h, w)) > oran)
    return a * keep


def damga_goruntusu(metin: str, size: float, seed: int, rot: float = -6.0, renk=RED, cerceve: bool = True,
                    hale: bool = True) -> Image.Image:
    """Kırmızı lastik damga (çift çerçeveli, aşınmış); resim üstünde okunsun diye ince kâğıt rengi hale. 1x RGBA."""
    cap = cap_h("anton", size)
    padx, pady = size * 0.24, size * 0.22
    bw, bh = K.tw(metin, "anton", size) + 2 * padx, cap + 2 * pady
    m = 26
    pen = K.Pen(-m, -m, bw + m, bh + m)
    beyaz = (255, 255, 255, 255)
    if cerceve:
        lw = max(5.0, size * 0.065)
        pen.rr((0, 0, bw, bh), size * 0.12, outline=beyaz, width=lw)
        ins = lw + size * 0.05
        pen.rr((ins, ins, bw - ins, bh - ins), size * 0.07, outline=beyaz, width=max(2.5, lw * 0.42))
    pen.text(bw / 2, pady + cap, metin, "anton", size, beyaz, anchor="ms")
    maske = pen.done().getchannel("A")
    a = _asindir(np.asarray(maske, np.float32) / 255.0, seed)
    out = Image.new("RGBA", maske.size, OFF + (0,))
    if hale:
        h = maske.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(1.2))
        out.putalpha(h.point(lambda v: int(v * 0.82)))
    ink = Image.new("RGBA", maske.size, renk + (0,))
    ink.putalpha(Image.fromarray(np.clip(a * 242, 0, 255).astype(np.uint8)))
    out.alpha_composite(ink)
    out = out.rotate(rot, resample=Image.BICUBIC, expand=True)
    bb = out.getchannel("A").getbbox()
    return out.crop(bb) if bb else out


def kagit_yazi(metin: str, size: float, seed: int, rot: float = -2.5, renk=MAVI, bant: bool = True,
               max_w: float = 600) -> Image.Image:
    """Beyaz kâğıt parçasına tükenmezle yazılmış not (üstünde sarı bant), sert gölgeli. 1x RGBA."""
    yz = None
    for z in range(int(size), 27, -2):
        yz = Yazi(metin, z, renk, seed)
        if yz.w <= max_w - 2 * z * 0.55:
            break
    while yz.w > max_w - 2 * yz.size * 0.55 and len(metin) > 3:     # yine sığmazsa kelime sınırında kısalır
        metin = metin.rsplit(" ", 1)[0] if " " in metin.strip() else metin[:-2]
        yz = Yazi(metin.rstrip(" ,.;:-–") + "…", yz.size, renk, seed)
    padx, pady = yz.size * 0.55, yz.size * 0.42
    w, h = yz.w + 2 * padx, yz.size * 1.04 + 2 * pady
    sp = K.Sprite(w, h, margin=30)
    K.torn_paper(sp, 0, 0, w, h, POLAROID, seed, rim=None)
    im = sp.render(0)
    yz.put(im, 30 + padx, 30 + pady + yz.size * 0.80, clip=(0, 0, im.width, im.height))
    if bant:
        tp = K.Sprite(w, h, margin=30)
        K.tape(tp, w / 2 + random.Random(seed).uniform(-20, 20), 2, min(150, w * 0.45), 36, 4 if seed % 2 else -5,
               seed, alpha=200)
        im.alpha_composite(tp.render(0))
    im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    im = K.add_shadow(im, 6, 8, 0, 0.85)
    bb = im.getchannel("A").getbbox()
    return im.crop(bb) if bb else im


# ---------------------------------------------------------------- sahnedeki öğeler
class Oge:
    """Sahneye konan bir öğe. gorunur(si): o sahnede görünür mü. baski: baskının üstündedir (geçişte baskıyla
    birlikte kayar / kesilir). kutu: son hâlinin ekrandaki kutusu (yerleşim denetimi). z: çizim sırası."""
    z = 10
    baski = True
    kutu: tuple | None = None
    yazi_mi = True                   # metin taşıyan öğe (güvenli alan ve binmeme denetimi)

    def __init__(self, sahneler):
        self.sahneler = set(sahneler)

    def gorunur(self, si: int) -> bool:
        return si in self.sahneler

    def draw(self, v: "AjandaVideo", img: Image.Image, t: float) -> None:
        raise NotImplementedError


class YaziOge(Oge):
    """Elle yazılan satır: t0'dan itibaren dur sn'de soldan sağa yazılır (kalem ucu yazıyı izler). kelime: sözle eşli
    yazma için (karakter indeksi -> açılma anı) listesi; verilirse dur yok sayılır."""

    def __init__(self, sahneler, yazi: Yazi, x, y, anchor="l", t0=0.0, dur=0.6, z=10, anlik=False, kelime=None):
        super().__init__(sahneler)
        self.yazi, self.x, self.y, self.anchor = yazi, x, y, anchor
        self.t0, self.dur, self.z, self.anlik, self.kelime = t0, max(0.05, dur), z, anlik, kelime
        self.kutu = yazi.ink_box(x, y, anchor)

    def reveal(self, t: float) -> float | None:
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
    yazi_mi = False

    def __init__(self, sahneler, iz: Iz, t0=0.0, dur=0.3, z=12, anlik=False):
        super().__init__(sahneler)
        self.iz, self.t0, self.dur, self.z, self.anlik = iz, t0, max(0.05, dur), z, anlik

    def draw(self, v, img, t):
        p = 1.0 if self.anlik else (t - self.t0) / self.dur
        if p > 0:
            self.iz.put(img, p)


class DamgaOge(Oge):
    """Yıl / saat damgası: büyükten çarparak iner (0,16 sn), sonra tükenmez mavisiyle halkalanır."""
    z = 20

    def __init__(self, sahneler, im, x, y, t0, anlik=False, halka: Iz | None = None):
        super().__init__(sahneler)
        self.im, self.x, self.y, self.t0, self.anlik, self.halka = im, x, y, t0, anlik, halka
        self.kutu = (x, y, x + im.width, y + im.height)

    def draw(self, v, img, t):
        p = 1.0 if self.anlik else (t - self.t0) / 0.16
        if p <= 0:
            return
        k = 1.0 if p >= 1 else K.lerp(1.3, 1.0, K.clamp(p) ** 2)
        K.put(img, self.im, self.x, self.y, k=k, alpha=min(1.0, 0.35 + p), anchor=(0.15, 0.3))
        if self.halka is not None:
            self.halka.put(img, 1.0 if self.anlik else (t - self.t0 - 0.32) / 0.45)


class KagitOge(Oge):
    """Bantlı kâğıt parçası ya da yırtık etiket: t0'da hafif büyükten yapışır."""
    z = 22

    def __init__(self, sahneler, im, x, y, t0, anlik=False, z=22, nabiz=False, yazi_mi=True):
        super().__init__(sahneler)
        self.im, self.x, self.y, self.t0, self.anlik, self.z, self.nabiz = im, x, y, t0, anlik, z, nabiz
        self.yazi_mi = yazi_mi
        self.kutu = (x, y, x + im.width, y + im.height)

    def draw(self, v, img, t):
        p = 1.0 if self.anlik else (t - self.t0) / 0.24
        if p <= 0:
            return
        k = N.ease_pop(p, 1.1) * (K.cta_pulse(t - self.t0) if self.nabiz else 1.0)
        K.put(img, self.im, self.x, self.y, k=k, alpha=min(1.0, p * 3))


class SayiOge(Oge):
    """Para durağının büyük sayısı: sarı yırtık kâğıtta sayarak yükselir, oturduğu an kırmızı etiket damgası iner."""
    z = 30

    def __init__(self, sahneler, deger: str, etiket: str, cx: float, alt: float, maxw: float, t_land: float,
                 seed: int, anlik=False, sayim=0.75):
        super().__init__(sahneler)
        self.deger, self.t_land, self.anlik, self.sayim = deger, t_land, anlik, sayim
        size = 196.0
        while size > 70 and K.tw(deger, "anton", size) + size * 0.5 > maxw:
            size -= 4
        self.size = size
        cap = cap_h("anton", size)
        padx, pady = size * 0.25, size * 0.17
        w, h = K.tw(deger, "anton", size) + 2 * padx, cap + 2 * pady
        sp = K.Sprite(w, h, margin=24)
        K.torn_paper(sp, 0, 0, w, h, YELLOW, seed, rim=INK, rim_w=4)
        self.kagit = sp.render(-2.0, shadow=(9, 11, 0, 0.9))
        self.x, self.y = cx - self.kagit.width / 2, alt - self.kagit.height
        self.tx, self.ty = cx, self.y + self.kagit.height / 2 + cap / 2 - 4
        self._yazi: dict = {}
        self.damga = None
        if etiket:
            self.damga = damga_goruntusu(etiket, max(40.0, min(58.0, size * 0.3)), seed + 3, rot=7.0)
            dx = min(self.x + self.kagit.width - self.damga.width * 0.72, SAFE[2] - 6 - self.damga.width)
            self.dxy = (dx, self.y - self.damga.height * 0.45)
        x0, y0 = self.x, self.y
        x1, y1 = self.x + self.kagit.width, self.y + self.kagit.height
        if self.damga is not None:
            x0, y0 = min(x0, self.dxy[0]), min(y0, self.dxy[1])
            x1 = max(x1, self.dxy[0] + self.damga.width)
        self.kutu = (x0, y0, x1, y1)

    def yazi(self, metin: str) -> Image.Image:
        if metin not in self._yazi:
            pad = 30
            w = K.tw(metin, "anton", self.size) + 2 * pad
            pen = K.Pen(self.tx - w / 2, self.ty - self.size, self.tx + w / 2, self.ty + self.size * 0.3)
            pen.text(self.tx, self.ty, metin, "anton", self.size, INK, anchor="ms")
            self._yazi[metin] = (pen.done(), (self.tx - w / 2, self.ty - self.size))
        return self._yazi[metin]

    def draw(self, v, img, t):
        t0 = self.t_land - self.sayim
        p = 1.0 if self.anlik else (t - t0 + 0.12) / 0.2
        if p <= 0:
            return
        k = N.ease_pop(p, 1.08)
        K.put(img, self.kagit, self.x, self.y, k=k, alpha=min(1.0, p * 3))
        if p < 0.35:
            return
        f = 1.0 if self.anlik else K.ease_out_cubic((t - t0) / self.sayim)
        lay, o = self.yazi(sayac_metni(self.deger, f))
        oturdu = self.anlik or t >= self.t_land
        kk = 1.0 if self.anlik else (1.0 + 0.1 * (1 - K.clamp((t - self.t_land) / 0.18)) if oturdu else 1.0)
        K.put(img, lay, *o, k=kk)
        if self.damga is not None and oturdu:
            q = 1.0 if self.anlik else (t - self.t_land - 0.08) / 0.14
            if q > 0:
                K.put(img, self.damga, *self.dxy, k=1.0 if q >= 1 else K.lerp(1.4, 1.0, q * q),
                      alpha=min(1.0, 0.3 + q), anchor=(1.0, 0.6))


class FisOge(Oge):
    """Dar fiş şeridi: başlık, satırlar sırayla daktiloyla basılır (soldan açılır), altında çift çizgi. Fiş kâğıdı
    alttan kayarak gelir."""
    z = 26

    def __init__(self, sahneler, kagit: Image.Image, o, satirlar: list, t0: float, anlik=False):
        super().__init__(sahneler)
        self.kagit, self.o, self.satirlar, self.t0, self.anlik = kagit, o, satirlar, t0, anlik
        self.kutu = (o[0], o[1], o[0] + kagit.width, o[1] + kagit.height)

    def draw(self, v, img, t):
        p = 1.0 if self.anlik else (t - self.t0) / 0.26
        if p <= 0:
            return
        e = K.ease_out_cubic(p)
        im = self.kagit.copy()
        for lay, (lx, ly), ta, tb in self.satirlar:
            q = 1.0 if self.anlik else K.clamp((t - ta) / max(0.05, tb - ta))
            if q <= 0:
                continue
            if q < 1:
                lay = lay.crop((0, 0, max(1, int(lay.width * q)), lay.height))
            im.alpha_composite(lay, (int(lx), int(ly)))
        K.put(img, im, self.o[0], self.o[1] + 70 * (1 - e), alpha=min(1.0, p * 2.5))


class NotOge(Oge):
    """Sarı yapışkan not ('İÇERİDEN'): yapışır, yazısı sözle birlikte elle yazılır."""
    z = 30

    def __init__(self, sahneler, govde: Image.Image, o, satirlar: list[YaziOge], izler: list[IzOge], t0):
        super().__init__(sahneler)
        self.govde, self.o, self.satirlar, self.izler, self.t0 = govde, o, satirlar, izler, t0
        bb = govde.getchannel("A").getbbox() or (0, 0, govde.width, govde.height)
        self.kutu = (o[0] + bb[0], o[1] + bb[1], o[0] + bb[2], o[1] + bb[3])

    def draw(self, v, img, t):
        p = (t - self.t0) / 0.24
        if p <= 0:
            return
        if p < 1:
            K.put(img, self.govde, *self.o, k=K.lerp(1.06, 1.0, K.ease_out_cubic(p)), alpha=min(1.0, p * 3))
            return
        K.put(img, self.govde, *self.o)
        for s in self.satirlar:
            s.draw(v, img, t)
        for s in self.izler:
            s.draw(v, img, t)


class ResimSabit(Oge):
    """Sahnede duran görüntü (ör. kâğıttaki kalem): t0'da hafifçe kayarak gelir."""
    z = 35
    yazi_mi = False

    def __init__(self, sahneler, im, x, y, t0, dx=-40):
        super().__init__(sahneler)
        self.im, self.x, self.y, self.t0, self.dx = im, x, y, t0, dx
        self.kutu = (x, y, x + im.width, y + im.height)

    def draw(self, v, img, t):
        p = (t - self.t0) / 0.35
        if p <= 0:
            return
        e = K.ease_out_cubic(p)
        K.put(img, self.im, self.x + self.dx * (1 - e), self.y - self.dx * 0.5 * (1 - e), alpha=min(1.0, p * 2.5))


# ---------------------------------------------------------------- başlık: yırtık kâğıt etiketler
class Baslik:
    """Sahnenin Anton başlığı: her satır ayrı yırtık kâğıt etiket (vurgulu satır sarı), sol altta üst üste; SEN /
    SANA / SENİN kelimesi mavi tükenmezle halkalanır. Kancada (kapak) ilk karede tamdır; diğer sahnelerde etiketler
    YENI0'dan itibaren sırayla yapışır, sahne değişince aşağı kayıp söner."""
    ARA = -10                         # etiketler arası (eksi: hafif üst üste biner)

    def __init__(self, s: Sahne, lines: list[str], hook: bool, vurgu: str | None = None):
        self.s, self.hook = s, hook
        if vurgu is None:
            vurgu = s.baslik[s.hl] if 0 <= s.hl < len(s.baslik) else ""
        lines = lines or [SERI_ADI]
        size, self.lines = self._sigdir(lines, 120 if hook else 106)
        while True:                                   # tahmin kısa kaldıysa gerçek etiketlerle küçültülür
            self._kur(size, vurgu)
            sigar = (self.top >= BAS_YMIN and max(b[2] for b in self.kutular) <= BAS_X1
                     and min(b[0] for b in self.kutular) >= X0 - 14)
            if sigar or size <= 30:
                break
            size -= 3
        self.size = size

    def _kur(self, size: float, vurgu: str) -> None:
        s = self.s
        self.size = size
        self.etiketler = []                           # (görüntü, x, y, metin)
        self.kutular = []
        planned = []
        for k, L in enumerate(self.lines):
            vur = bool(vurgu) and L == vurgu
            fg, bg = (INK, YELLOW) if vur else (INK, OFF)
            lab = K.torn_label(L, size, fg, bg, tohum("bl", s.i, k), rim=INK)
            planned.append((L, lab, vur))
        if vurgu and not any(v for _, _, v in planned):   # vurgu yeniden sarıldıysa içeren ilk satır
            for j, (L, lab, _) in enumerate(planned):
                if any(w in L.split() for w in vurgu.split()):
                    planned[j] = (L, K.torn_label(L, size, INK, YELLOW, tohum("bl", s.i, j), rim=INK), True)
                    break
        ims = []
        for k, (L, lab, vur) in enumerate(planned):
            rot = (-1.4, 1.1, -0.8)[k % 3]
            im = lab.render(rot, shadow=(7, 9, 0, 0.9))
            ims.append((im, lab, rot, L))
        y = BAS_Y1                                  # alttan yukarı: mürekkep (kâğıt + gölge) kutusuna göre
        pos = []
        for k in range(len(ims) - 1, -1, -1):
            im = ims[k][0]
            bb = im.getchannel("A").getbbox() or (0, 0, im.width, im.height)
            pos.append((k, y - bb[3]))
            y = y - bb[3] + bb[1] - self.ARA
        pos.sort()
        self.halka = None
        for (k, yy), (im, lab, rot, L) in zip(pos, ims):
            x = X0 - lab.m + (22 if k % 2 else 0) - 4
            self.etiketler.append((im, x, yy, L))
            bb = im.getchannel("A").getbbox()
            self.kutular.append((x + bb[0], yy + bb[1], x + bb[2], yy + bb[3]))
            if self.halka is None:
                self.halka = self._halka(L, lab, rot, im, x, yy)
        self.top = min(b[1] for b in self.kutular)

    @staticmethod
    def etiket_h(L: str, size: float) -> float:
        """Etiketin ekrandaki yüksekliği (yırtık kâğıt: Türkçe şapka ve çengeller dahil, eğim ve sert gölge payıyla)."""
        l, t, r, b = K.tbox(L, "anton", size)
        cap = cap_h("anton", size)
        h = max(cap, -t) + max(0.0, b) + 2 * size * 0.16
        w = K.tw(L, "anton", size) + 2 * size * 0.2
        return h + w * 0.025 + 12

    @staticmethod
    def _sigdir(lines: list[str], en_buyuk: int) -> tuple[float, list[str]]:
        """En büyük boyut: önce verilen satır kırılımı, sığmazsa kelimeler 1-3 satıra yeniden dağıtılır."""
        words = " ".join(lines).split()

        def sar(n):
            if n == 1:
                return [" ".join(words)]
            best = None
            for cuts in _bolmeler(len(words), n):
                parts = [" ".join(words[a:b]) for a, b in cuts]
                m = max(K.tw(p, "anton", 100) for p in parts)
                if best is None or m < best[0]:
                    best = (m, parts)
            return best[1] if best else [" ".join(words)]
        boy = BAS_Y1 - BAS_YMIN

        def en_iyi(c) -> float:
            if len(c) > 3:
                return 0.0
            size = float(en_buyuk)
            while size >= 30:
                gen = max(K.tw(L, "anton", size) + 2 * size * 0.2 for L in c) + 22
                yuk = sum(Baslik.etiket_h(L, size) for L in c) + (len(c) - 1) * Baslik.ARA
                if gen <= BAS_X1 - X0 and yuk <= boy:
                    return size
                size -= 2
            return 0.0
        # senaryonun satır kırılımı (vurgulu satır) korunur; yalnız çok küçülecekse kelimeler yeniden dağıtılır
        s0 = en_iyi(lines)
        adaylar = sorted(((en_iyi(c), -len(c), c) for c in (sar(n) for n in (1, 2, 3) if n <= len(words))),
                         key=lambda a: (a[0], a[1]), reverse=True)
        if s0 and (s0 >= 72 or not adaylar or s0 >= 0.82 * adaylar[0][0]):
            return s0, lines
        if adaylar and adaylar[0][0]:
            return adaylar[0][0], adaylar[0][2]
        return 30.0, lines

    def _halka(self, L, lab, rot, im, x, yy) -> Iz | None:
        kel = L.split(" ")
        for k, w in enumerate(kel):
            if not SEN_RE.match(w):
                continue
            size = self.size
            core = re.sub(r"\W+$", "", w)
            padx = size * 0.2
            a = padx + K.tw(" ".join(kel[:k]) + (" " if k else ""), "anton", size)
            b = a + K.tw(core, "anton", size)
            cap = cap_h("anton", size)
            cx, cy = lab.m + (a + b) / 2, lab.m + lab.base_y - cap / 2
            # etiket görüntüsü merkezine göre döndürülmüştür
            w0, h0 = lab.w + 2 * lab.m, lab.h + 2 * lab.m
            dx, dy = cx - w0 / 2, cy - h0 / 2
            th = math.radians(rot)
            rx_, ry_ = dx * math.cos(th) + dy * math.sin(th), -dx * math.sin(th) + dy * math.cos(th)
            gx, gy = x + im.width / 2 + rx_, yy + im.height / 2 + ry_
            rx = (b - a) / 2 + min(30.0, max(18.0, size * 0.18))
            return Iz([el_daire(gx, gy, rx, cap / 2 + max(12.0, size * 0.12), tohum("halka", self.s.i))],
                      max(5.0, size * 0.055), MAVI)
        return None

    def draw(self, img, t, cikis: float | None = None):
        """cikis: sahne değişirken (0..1) etiketler aşağı kayıp söner."""
        lt = t - self.s.start
        n = len(self.etiketler)
        for k, (im, x, y, _) in enumerate(self.etiketler):
            if cikis is not None:
                e = K.clamp(cikis)
                K.put(img, im, x, y + 46 * e * e, alpha=1 - e)
                continue
            p = 1.0 if self.hook else (lt - YENI0 - 0.07 * k) / 0.22
            if p <= 0:
                continue
            K.put(img, im, x, y, k=N.ease_pop(p, 1.12), alpha=min(1.0, p * 3), anchor=(0.1, 0.5))
        if self.halka is not None and cikis is None:
            ph = 1.0 if self.hook else (lt - YENI0 - 0.07 * n - 0.15) / 0.45
            if ph > 0:
                self.halka.put(img, ph)


def _bolmeler(n: int, parca: int):
    """n kelimeyi parca satıra bölen (başlangıç, bitiş) dizileri."""
    if parca == 1:
        yield [(0, n)]
        return
    for i in range(1, n - parca + 2):
        for rest in _bolmeler(n - i, parca - 1):
            yield [(0, i)] + [(a + i, b + i) for a, b in rest]


# ---------------------------------------------------------------- sahnenin baskısı (resim)
class Baski:
    """Sahnenin büyük baskısı: fotoğraf (Ken Burns), çizim (kâğıt zemin + ayrı kayan çizim: paralaks) ya da resim
    yoksa tema renginde büyük yıl / saat / sayı afişi. Beyaz kenarlı, bantlı çerçeve sahne başına bir kez çizilir."""
    M = 34                                            # çerçeve katmanının gölge / bant payı

    def __init__(self, v: "AjandaVideo", s: Sahne):
        self.v, self.s = v, s
        self.cw, self.ch = FOTO[2] - FOTO[0], FOTO[3] - FOTO[1]
        rng = random.Random(tohum("kb", s.i))
        self.yakin = s.i % 2 == 0                     # sırayla yakınlaş / uzaklaş
        self.pan = (rng.choice((-1, 1)) * rng.uniform(0.45, 0.9), rng.uniform(-0.5, 0.35))
        self.tur = "foto" if s.foto else ("cizim" if s.resim is not None else "afis")
        self.afis = None
        self._src = None
        self._cizim = None
        self._cerceve = None
        self._ust = None

    # ------------------------------------------------------------ hazırlık
    def hazirla(self) -> None:
        if self._src is not None:
            return
        sw, sh = int(round(self.cw * KB)), int(round(self.ch * KB))
        if self.tur == "foto":
            try:
                src = Image.open(self.s.resim).convert("RGB")
            except Exception:  # noqa: BLE001
                self.tur = "afis"
                return self.hazirla()
            src = K.cover(src, sw, sh, focus=(0.5, 0.34))
            sicak = Image.new("RGB", src.size, (238, 226, 204))
            self._src = Image.blend(src, sicak, 0.07)
        elif self.tur == "cizim":
            zw, zh = int(self.cw * 1.05), int(self.ch * 1.05)
            self._src = self.v.zemin(self.s.tema, zw, zh, tohum("z", self.s.i))
            try:
                sp = Image.open(self.s.resim).convert("RGBA")
            except Exception:  # noqa: BLE001
                self.tur = "afis"
                self._src = None
                return self.hazirla()
            bb = sp.getchannel("A").getbbox()
            if bb:
                sp = sp.crop(bb)
            q = min(self.cw * 0.86 / sp.width, self.ch * 0.66 / sp.height) * 1.08
            sp = sp.resize((max(1, int(sp.width * q)), max(1, int(sp.height * q))), Image.LANCZOS)
            self._cizim = K.add_shadow(sp, 12, 14, 0, 0.22)
        else:
            self._src = self.v.afis(self.s, sw, sh)

    def cerceve(self) -> tuple[Image.Image, Image.Image]:
        """(alt katman: gölge + beyaz kenar, üst katman: bantlar + künye çipi); sol üst köşeleri BASKI - M."""
        if self._cerceve is None:
            m = self.M
            bw, bh = BASKI[2] - BASKI[0], BASKI[3] - BASKI[1]
            pen = K.Pen(-m, -m, bw + m, bh + m)
            pen.rr((12, 14, bw + 12, bh + 14), 6, fill=INK + (225,))
            pen.rr((0, 0, bw, bh), 6, fill=POLAROID, outline=INK, width=4)
            pen.rr((KENAR - 2, KENAR - 2, bw - KENAR + 2, bh - KENAR + 2), 2, fill=INK)
            self._cerceve = pen.done()
            ust = K.Sprite(bw, bh, margin=m)
            rng = random.Random(tohum("bant", self.s.i))
            K.tape(ust, 70 + rng.uniform(-10, 10), 6, 190, 46, -33 + rng.uniform(-4, 4), tohum("b1", self.s.i),
                   alpha=200)
            K.tape(ust, bw - 70 + rng.uniform(-10, 10), 6, 190, 46, 31 + rng.uniform(-4, 4), tohum("b2", self.s.i),
                   alpha=200)
            im = ust.render(0)
            not_ = K.credit_chip(self.s.kunye) if self.s.foto else ""
            if not_:
                pen = K.Pen(-m, -m, bw + m, bh + m)
                tw = K.tw(K.fit(not_, "mono", 22, 380), "mono", 22) + 62
                K.chip_label(pen, bw - KENAR - 14 - tw, bh - KENAR - 230, not_, size=22, rot=0.0, max_w=440)
                im.alpha_composite(pen.done())
            self._ust = im
        return self._cerceve, self._ust

    # ------------------------------------------------------------ kare
    def icerik(self, p: float) -> Image.Image:
        """İç alanın (984x1132) p anındaki görüntüsü (RGB): Ken Burns penceresi, çizimde paralaks."""
        self.hazirla()
        e = K.lerp(p, K.ease_in_out(p), 0.5)
        if self.tur == "cizim":
            zw, zh = self._src.size
            ox = (zw - self.cw) / 2 * (1 + self.pan[0] * (2 * e - 1) * 0.8)
            oy = (zh - self.ch) / 2 * (1 - 0.6 * (2 * e - 1))
            out = self._src.resize((self.cw, self.ch), Image.BILINEAR,
                                   box=(ox, oy, ox + self.cw, oy + self.ch)).convert("RGBA")
            k = K.lerp(0.93, 1.0, e) if self.yakin else K.lerp(1.0, 0.94, e)
            sp = self._cizim
            nw, nh = max(1, int(sp.width * k)), max(1, int(sp.height * k))
            sp = sp.resize((nw, nh), Image.BILINEAR)
            cx = self.cw / 2 - self.pan[0] * 26 * (2 * e - 1)
            cy = self.ch * 0.38 + 8 * math.sin(p * math.pi * 1.4 + self.s.i)
            out.alpha_composite(sp, (int(round(cx - nw / 2)), int(round(cy - nh / 2))))
            return out.convert("RGB")
        sw, sh = self._src.size
        z = K.lerp(KB, 1.015, e) if self.yakin else K.lerp(1.015, KB, e)
        if self.tur == "afis":
            z = K.lerp(KB, 1.06, e) if self.yakin else K.lerp(1.06, KB, e)
        ww, wh = min(sw, self.cw * z), min(sh, self.ch * z)
        rx, ry = (sw - ww) / 2, (sh - wh) / 2
        cx = sw / 2 + self.pan[0] * rx * (2 * e - 1)
        cy = sh / 2 + self.pan[1] * ry * (2 * e - 1)
        if self.tur == "foto":
            cy = min(cy, sh / 2)                      # yüzler genelde üstte: pencere aşağı kaymaz
        box = (cx - ww / 2, cy - wh / 2, cx + ww / 2, cy + wh / 2)
        return self._src.resize((self.cw, self.ch), Image.BILINEAR, box=box)

    def ciz(self, img: Image.Image, p: float) -> None:
        alt, ust = self.cerceve()
        o = (BASKI[0] - self.M, BASKI[1] - self.M)
        K.put(img, alt, *o, clip=BASKI_CLIP)
        img.paste(self.icerik(p), (FOTO[0], FOTO[1]))
        K.put(img, ust, *o, clip=BASKI_CLIP)

    def katman(self, p: float) -> Image.Image:
        """Geçişlerde döndürülüp kaydırılan tek parça (çerçeve + resim + bantlar); sol üst köşesi BASKI - M."""
        alt, ust = self.cerceve()
        out = alt.copy()
        out.paste(self.icerik(p), (self.M + KENAR, self.M + KENAR))
        out.alpha_composite(ust)
        return out

    def birak(self) -> None:
        """Bellek: sahne geçtikten sonra büyük kaynaklar bırakılır (gerekirse yeniden hazırlanır)."""
        self._src = None
        self._cizim = None


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
        self.gun = sum(1 for s in self.p if s.tur == "durak" and s.saat) >= 2
        self.yillik = any(s.tur == "durak" and s.damga and not s.saat for s in self.p)
        senaryo = self.meta.get("script") or {}
        ns = SimpleNamespace(scenes=[SimpleNamespace(**sc) for sc in (senaryo.get("scenes") or [])]
                             or [SimpleNamespace(**{**(sp.card or {}), "narration": sp.narration}) for sp in scenes])
        self.para = bool(para_var(ns)) or any(s.para for s in self.p)
        tarih = self.meta.get("tarih")
        if isinstance(tarih, str):
            tarih = dt.date.fromisoformat(tarih)
        # Video yayından günler önce çizilir; yayın günü bilinmeden somut tarih basılmaz
        self.tarih = turkce_tarih(tarih) if tarih else tarihsiz_baslik(
            "yil" if self.yillik else ("para" if self.para and not self.gun else "gun"))
        k0 = up(scenes[0].kicker) if scenes else ""
        self.seri = k0 if k0.startswith(SERI_ADI) else SERI_ADI
        self.hm = HesapMakinesi() if any(s.para for s in self.p) else None
        self.mascot = N.Mascot()
        self._speech: dict = {}
        self._layers: dict = {}
        self._eski: dict = {}
        self.seri_sag: dict[bool, float] = {}
        self.olay: dict[int, float] = {}            # sahnenin ana anı (sayı oturdu, toplam basıldı)
        self.sessiz: dict[int, int] = {}            # dış sesin şeritte yazılmadığı ilk kelime (notta, cta'da soru)
        self.ogeler: list[Oge] = []
        self.lcd: list[tuple] = []
        self.baskilar = [Baski(self, s) for s in self.p]
        self.basliklar: dict[int, Baslik] = {}
        self._kur()
        self.ogeler.sort(key=lambda o: o.z)
        self.lcd.sort(key=lambda e: e[0])
        self.lcd_t = [e[0] for e in self.lcd]
        self.makine_ara = self._makine_araliklari()
        self.kalem_ucu = None

    # ------------------------------------------------------------ yardımcılar
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

    def sayi_ani(self, s: Sahne, deger: str, sonra: int = -1) -> tuple[float, int] | None:
        """Değerin dış seste söylendiği an: '80.000 ₺' için '80' (ardından 'bin'), '276.000' için '276' de sayılır."""
        dig = re.sub(r"\D", "", deger.split(",")[0])
        if not dig:
            return None
        for wi in range(max(s.a, sonra + 1), s.b):
            w = re.sub(r"\D", "", self.words[wi].text)
            if w and (w == dig or (dig.startswith(w) and not dig[len(w):].strip("0") and len(dig) - len(w) >= 3)):
                return self.words[wi].start - 0.08, wi
        return None

    def resim_kutusu(self, si: int) -> tuple | None:
        """Sahnenin fotoğrafının ya da çiziminin göründüğü alan (resim yoksa None; afiş de aynı alanı kaplar)."""
        return FOTO if self.p[si].resim is not None else None

    def gecis_turu(self, si: int) -> str:
        return ("kayma", "bant", "kesme")[(si - 1) % 3]

    def gecis_suresi(self, si: int) -> float:
        return CUT if self.gecis_turu(si) == "kesme" else GECIS

    def ilerleme_p(self, si: int, t: float) -> float:
        s = self.p[si]
        return K.clamp((t - s.start) / max(0.5, s.end - s.start))

    def _tema_renk(self, tema: str) -> tuple:
        bg = {"black": INK, "yellow": YELLOW, "red": RED}.get(tema, (244, 238, 224))
        fg = {INK: YELLOW, YELLOW: INK, RED: OFF}.get(bg, RED)
        golge = {INK: RED, YELLOW: RED, RED: INK}.get(bg, INK)
        kalem = OFF if bg in (INK, RED) else MAVI
        return bg, fg, golge, kalem

    # ------------------------------------------------------------ baskı zeminleri
    def zemin(self, tema: str, w: int, h: int, seed: int) -> Image.Image:
        """Çizimin kâğıt zemini: tema renginde açık kâğıt, ajanda kareli çizgileri ve kırmızı kenar çizgisi."""
        key = ("zemin", tema, w, h)
        if key not in self._layers:
            base = KAGIT_ZEMIN.get(tema, KREM)
            im = Image.new("RGB", (w, h), base)
            d = ImageDraw.Draw(im)
            ac = K.blend(base, MAVI, 0.13)
            for y in range(40, h, 52):
                d.line([(0, y), (w, y)], fill=ac, width=2)
            d.line([(96, 0), (96, h)], fill=K.blend(base, RED, 0.45), width=3)
            g = np.asarray(im, np.float32)
            yy, xx = np.mgrid[0:h, 0:w]
            r = np.hypot((xx - w / 2) / (w * 0.7), (yy - h * 0.42) / (h * 0.7))
            g *= np.clip(1.04 - 0.16 * r ** 2, 0.82, 1.03)[..., None]
            g += np.random.default_rng(seed).normal(0, 2.4, g.shape[:2])[..., None]
            self._layers[key] = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8))
        return self._layers[key]

    def afis_metni(self, s: Sahne) -> tuple[str, str]:
        """Resimsiz sahnenin afişi: ('1884', 'damga'), ('?', 'soru'), ('$', 'birim'), ('', 'makas'), ..."""
        if s.para:
            _, br = lcd_degeri(s.deger)
            return (br, "birim") if br else ("", "bos")
        if s.tur == "cta":
            return "?", "soru"
        if s.damga:
            return s.damga, "damga"
        y = yil_of(s.anlatim)
        if y:
            return y, "sayi"
        m = SAYI_RE.search(s.anlatim)
        if m and len(m.group(1)) >= 2:
            return m.group(1).rstrip(".,"), "sayi"
        return "", "makas"

    def afis(self, s: Sahne, sw: int, sh: int) -> Image.Image:
        """Resim yoksa baskının kendisi: tema renginde kareli kâğıt üstünde dev yıl / saat / sayı (sert gölgeli,
        tükenmezle altı çizili); para sahnesinde birimin soluk dev işareti; hiçbiri yoksa makas."""
        bg, fg, golge, kalem_ = self._tema_renk(s.tema)
        metin, tur = self.afis_metni(s)
        pen = K.Pen(0, 0, sw, sh)
        pen.rr((0, 0, sw, sh), 0, fill=bg)
        cizgi = K.blend(bg, fg, 0.10)
        for y in range(46, sh, 56):
            pen.rr((0, y - 1, sw, y + 1), 0, fill=cizgi)
        pen.rr((118, 0, 121, sh), 0, fill=K.blend(bg, OFF if bg == RED else RED, 0.4))
        cx = sw * {"soru": 0.70, "makas": 0.30 if s.tur == "iceriden" else 0.5}.get(tur, 0.5)
        cy = sh * 0.40
        if tur == "birim" and metin:
            font = "plex" if metin == K.TL else "anton"
            size = sh * 0.62
            while size > 80 and K.tw(metin, font, size) > sw * 0.7:
                size -= 10
            pen.text(sw * 0.62, sh * 0.62, metin, font, size, K.blend(bg, fg, 0.13), anchor="ms")
        elif tur in ("damga", "sayi", "soru") and metin:
            size = sh * 0.5
            while size > 60 and (K.tw(metin, "anton", size) > sw * 0.78 or cap_h("anton", size) > sh * 0.34):
                size -= 6
            cap = cap_h("anton", size)
            base = cy + cap / 2
            off = size * 0.045
            pen.text(cx + off, base + off, metin, "anton", size, golge, anchor="ms")
            pen.text(cx, base, metin, "anton", size, fg, anchor="ms")
            w = K.tw(metin, "anton", size)
            seed = tohum("afis", s.i)
            for j, dy in enumerate((size * 0.12, size * 0.2)):
                pts = el_cizgi(cx - w / 2 - 20 + j * 30, base + dy, cx + w / 2 + 30 - j * 40, base + dy - 6,
                               seed + j, amp=3.0)
                pen.line(pts, kalem_ + (235,), 11 - j * 3)
        elif tur == "makas":
            ink = OFF if bg in (INK, RED) else INK
            sc = K.scissors_icon(sw * 0.56, 26, blade=ink, ring=YELLOW if bg == RED else RED, pivot=YELLOW
                                 if bg != YELLOW else OFF, outline=ink, rot=-14)
            x = 60
            y0 = cy + 120
            while x < sw - 60:
                pen.rr((x, y0 - 3 - (x - 60) * 0.25, x + 34, y0 + 3 - (x - 60) * 0.25), 3, fill=K.blend(bg, ink, 0.55))
                x += 58
            big = sc.resize((sc.width * SS, sc.height * SS), Image.LANCZOS)
            pen.paste(big, cx - sc.width / 2, cy - sc.height / 2)
        im = pen.done().convert("RGB")
        g = np.asarray(im, np.float32)
        g += np.random.default_rng(tohum("afisgren", s.i)).normal(0, 3.0, g.shape[:2])[..., None]
        return Image.fromarray(np.clip(g, 0, 255).astype(np.uint8))

    # ------------------------------------------------------------ sayfa ve ajanda şeridi
    def sayfa(self) -> Image.Image:
        """Ajanda sayfası (video başına): krem kâğıt, kenarlarda görünen çizgiler, cilt gölgesi, sayfa kenarları ve
        kurdele; baskı bunun üstüne konur."""
        if "sayfa" in self._layers:
            return self._layers["sayfa"]
        img = Image.new("RGBA", (W, H), SAYFA + (255,))
        pen = K.Pen(0, 0, W, H)
        for y in range(TARIH_CIZGI + 40, H, 56):
            pen.rr((0, y - 1, W, y + 1), 1, fill=MAVI_CIZGI)
        pen.rr((22, TARIH_CIZGI + 12, 24, H), 1, fill=K.blend(SAYFA, RED, 0.45))
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
        x0, x1, yb = 954, 996, 520
        pts = [(x0, -10), (x1, -10), (x1 + 4, yb), ((x0 + x1) / 2 + 2, yb - 30), (x0 + 4, yb)]
        rp.poly([(x + 7, y + 8) for x, y in pts], INK + (200,))
        rp.poly(pts, RED)
        rp.poly([(x0 + 6, -10), (x0 + 12, -10), (x0 + 15, yb - 8), (x0 + 9, yb - 4)], (236, 84, 80))
        rp.poly([(x1 - 9, -10), (x1 - 4, -10), (x1, yb - 4), (x1 - 5, yb - 8)], (176, 22, 30))
        img.alpha_composite(rp.done(), (900, 0))
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
        """Sayfa + ajanda şeridi: seri etiketi (kancada büyük, kicker'daki sayıyla; sağda basılı tarih)."""
        key = ("taban", kanca)
        if key in self._layers:
            return self._layers[key]
        img = self.sayfa().copy()
        pen = K.Pen(0, SIRA_CY - 60, SAFE[2], SIRA_CY + 60)
        metin, size = (self.seri, 44) if kanca else (SERI_ADI, 40)
        sinir = X0 + (X1 - X0) * 0.5
        if kanca:                                    # basılı tarih sağda; seri etiketi soldaki boşluğa sığar
            gun, ay_yil, gun_adi, sag = self.tarih
            base = SIRA_CY + 26
            x_r = X1
            if sag:
                pen.text(x_r, base, sag, "courier", 24, DGREY, anchor="rs")
                x_r -= K.tw(sag, "courier", 24) + 18
            w2 = max(K.tw(ay_yil, "courier", 28), K.tw(gun_adi, "courier", 28))
            pen.text(x_r - w2, base - 32, ay_yil, "courier", 28, INK)
            pen.text(x_r - w2, base, gun_adi, "courier", 28, DGREY)
            pen.text(x_r - w2 - 14, base, gun, "anton", 70, RED, anchor="rs")
            sinir = x_r - w2 - 14 - K.tw(gun, "anton", 70) - 28
        while size > 30 and X0 + N.label_w(metin, size) > sinir:
            size -= 2
        N.paste_label(pen, metin, size, OFF, INK, 11, X0 + N.label_w(metin, size) / 2 + 2, SIRA_CY + 2, rot=-1.5)
        self.seri_sag[kanca] = X0 + N.label_w(metin, size) + 10
        img.alpha_composite(pen.done(), (0, SIRA_CY - 60))
        self._layers[key] = img
        return img

    # ------------------------------------------------------------ DURAK ilerlemesi
    def ilerleme_kutulari(self) -> tuple[float, float, float]:
        n = self.N
        s, gap = (34, 14) if n <= 5 else ((28, 10) if n <= 7 else (24, 8))
        return X1 - 6 - (n * s + (n - 1) * gap), s, gap

    def ilerleme(self, img: Image.Image, si: int, t: float) -> None:
        """Şeridin sağında 'DURAK k/N' ve elle çizilmiş kutular: geçilen duraklar mavi tikli, şimdiki kırmızı
        halkalı; sonda TAMAM. Kancada (kapak) yok."""
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
            self.taban(False)
            kx0, bs, gap = self.ilerleme_kutulari()
            pen = K.Pen(0, SIRA_CY - 50, SAFE[2], SIRA_CY + 50)
            size = 44
            base = SIRA_CY + cap_h("anton", size) / 2
            tx = kx0 - 20
            if bitti:
                pen.text(tx, base, "TAMAM", "anton", size, INK, anchor="rs")
            else:
                sag = f"/{self.N}"
                w_sag = K.tw(sag, "anton", size)
                pen.text(tx, base, sag, "anton", size, INK, anchor="rs")
                pen.text(tx - w_sag, base, str(k), "anton", size, RED, anchor="rs")
                x_durak = tx - w_sag - K.tw(str(k), "anton", size) - 10
                if x_durak - K.tw("DURAK", "anton", size) > self.seri_sag[False] + 12:
                    pen.text(x_durak, base, "DURAK", "anton", size, INK, anchor="rs")
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
            for j in range(last - 1):
                tikler[j].put(lay)
            bb = lay.getbbox()
            self._layers[key] = (lay.crop(bb), bb[:2], tikler, halka)
        lay, o, tikler, halka = self._layers[key]
        K.put(img, lay, *o)
        last = self.N if bitti else k - 1
        onceki = self.p[si - 1]
        yeni = bitti or (s.tur in ("durak", "sayac", "fis") and onceki.durak != s.durak)
        if last >= 1:
            tikler[last - 1].put(img, (lt - YENI0 - 0.02) / 0.25 if yeni else 1.0)
        if not bitti:
            halka[k - 1].put(img, (lt - YENI0 - 0.15) / 0.4 if yeni else 1.0)

    # ------------------------------------------------------------ öğeleri kur
    def _kur(self) -> None:
        for s in self.p:
            if s.tur == "cta":
                self.basliklar[s.i] = Baslik(s, CTA_BASLIK, False, CTA_BASLIK[-1])
            else:
                self.basliklar[s.i] = Baslik(s, s.baslik, s.i == 0)
        self.lcd.append((0.0, "", "0", "", None, ""))
        for s in self.p:
            anlik = s.i == 0
            t_on = 0.0 if anlik else s.start + OGE0
            ust_alt = UST0 - 16
            afis_metin, _ = self.afis_metni(s)
            ayni = self.baskilar[s.i].tur == "afis" and afis_metin == s.damga
            if s.damga and not ayni:
                im = damga_goruntusu(s.damga, 132 if len(s.damga) <= 4 else 112, tohum("dm", s.i),
                                     rot=-7.0 if s.i % 2 else -4.5)
                x, y = DAMGA_X, UST0
                halka = Iz([el_daire(x + im.width / 2, y + im.height / 2, im.width * 0.6, im.height * 0.62,
                                     tohum("dh", s.i), tur=1.1, rot=-6)], 6.0, MAVI)
                self.ogeler.append(DamgaOge([s.i], im, x, y, t_on, anlik=anlik, halka=halka))
                ust_alt = y + im.height + 20
            elif s.kicker:
                # para sahnesinde sağ üstte makine durur: kâğıt onun soluna sığar
                im = kagit_yazi(cumle(s.kicker), 44, tohum("kk", s.i), max_w=430 if s.para else 620)
                self.ogeler.append(KagitOge([s.i], im, DAMGA_X - 10, UST0, t_on, anlik=anlik))
                ust_alt = UST0 + im.height
            if s.para:
                self._hesap_kur(s, ust_alt, t_on, anlik)
            elif s.tur == "iceriden":
                self._not_kur(s, ust_alt)
            elif s.tur == "cta":
                self._cta_kur(s, ust_alt)

    def alt_sinir(self, s: Sahne, sag: bool = True) -> float:
        """Baskı üstü öğelerin alt sınırı: başlığın üstü (sağa uzanan öğede Makas'ın üstü de)."""
        top = self.basliklar[s.i].top
        return min(top, MAKAS_UST) - 26 if sag else top - 26

    # ------------------------------------------------------------ para: büyük sayı, fiş ve makine
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

    def _hesap_kur(self, s: Sahne, ust_alt: float, t_on: float, anlik: bool) -> None:
        """Para durağı: büyük sayı (sayarak yükselir, damgayla oturur), fişte dar kâğıt şeridi; LCD tuşlanır."""
        gor = [s.i]
        rozet = self._rozet(s)
        alt = self.alt_sinir(s)
        lab = s.etiket or " ".join(s.baslik)
        if s.tur == "fis":
            self._fis_kur(s, ust_alt, alt, t_on, rozet)
            return
        ani = self.kelime_ani(s, lab.split())
        t_lab = t_on if ani is None else K.clamp(ani[0], t_on, max(t_on, s.end - 1.6))
        v = self.sayi_ani(s, s.deger)
        t_land = K.clamp(v[0] + 0.15 if v else t_lab + 1.0, t_on + 0.9, max(t_on + 0.9, s.end - 0.3))
        if anlik:
            t_land = 0.0
        sayim = K.clamp(t_land - t_on - 0.15, 0.6, 1.4)
        sayi = SayiOge(gor, s.deger, s.etiket, 470, alt, 800, t_land, tohum("sy", s.i), anlik=anlik, sayim=sayim)
        self.ogeler.append(sayi)
        if s.notu:
            im = kagit_yazi("*" + s.notu, 36, tohum("nt", s.i), rot=2.0, max_w=520)
            y = sayi.kutu[1] - im.height - 6
            if y >= ust_alt:
                self.ogeler.append(KagitOge(gor, im, X1 - 6 - im.width, y, t_land + 0.45, anlik=anlik, z=24))
        dg, br = lcd_degeri(s.deger)
        if dg and lcd_sigar(dg, 12 if not br else 11):
            self._lcd_yaz(t_land + 0.05, up(lab), dg, br, "=", rozet, hizli=anlik)
        self.olay[s.i] = t_land

    def _fis_kur(self, s: Sahne, ust_alt: float, alt: float, t_on: float, rozet: str) -> None:
        """Fiş: satırlar dar kâğıt şeridine sırayla basılır (kalem dış seste geçiyorsa o an), toplam büyük sayı olarak
        fişin altına oturur. Makine her satırda ara toplamı gösterir."""
        gor = [s.i]
        satirlar = s.satirlar
        n = len(satirlar)
        t0 = t_on + 0.25
        t_end = max(t0 + 0.6 * n, s.end - 1.5)
        d = min(1.1, (t_end - t0) / max(1, n))
        times, prev, used = [], t0, -1
        for j, (kalem_, tutar_) in enumerate(satirlar):
            latest = t_end - (n - j) * d
            ani = self.kelime_ani(s, kalem_.split(), rakam=tutar_, sonra=used)
            t = prev
            if ani and prev <= ani[0] <= latest:
                t, used = ani
            times.append(max(prev, min(t, latest)))
            prev = times[-1] + d
        toplam_ani = self.sayi_ani(s, s.deger, sonra=used)
        t_tot = max(prev + 0.15, toplam_ani[0] + 0.25 if toplam_ani else prev + 0.4)
        t_tot = min(t_tot, max(prev + 0.15, s.end - 0.6))
        # toplam: büyük sayı, fişin altında
        sayi = SayiOge(gor, s.deger, s.etiket or "TOPLAM", 500, alt, 760, t_tot, tohum("fsy", s.i), sayim=0.6)
        self.ogeler.append(sayi)
        # fiş kâğıdı: başlık + satırlar + çift çizgi
        fw = 450
        x0 = X0 + 4
        top = max(ust_alt + 28, UST0 + 20)             # kutunun kenar payı (m) kâğıda binmesin
        bottom = sayi.kutu[1] + 64                      # toplamın kâğıdı fişin alt ucuna biraz biner
        size, lh = 26, 50
        while True:
            need = 30 + 50 + n * lh + 34 + 24
            if need <= bottom - top or lh <= 34:
                break
            lh -= 2
            size = min(size, lh * 0.6)
        fh = min(bottom - top, 30 + 50 + n * lh + 34 + 24)
        m = 20
        pen = K.Pen(-m, -m, fw + m, fh + m)
        dis = 14
        ust_kenar = [(x * fw / 24, (dis * 0.5 if x % 2 else 0)) for x in range(25)]
        alt_kenar = [(fw - x * fw / 24, fh - (dis * 0.5 if x % 2 else 0)) for x in range(25)]
        pen.poly([(x + 8, y + 10) for x, y in ust_kenar + alt_kenar], INK + (215,))
        pen.poly(ust_kenar + alt_kenar, POLAROID)
        baslik = K.fit(s.etiket or "HESAP", "courier", 28, fw - 60)
        pen.text(fw / 2, 30 + 30, baslik, "courier", 28, INK, anchor="ms")
        x = 26
        while x < fw - 26:
            pen.rr((x, 30 + 46, x + 10, 30 + 48), 1, fill=DGREY)
            x += 18
        kagit = pen.done()
        katmanlar = []
        acc, birim = 0.0, ""
        for j, ((kalem_, tutar_), t) in enumerate(zip(satirlar, times)):
            yb = 30 + 50 + (j + 1) * lh - lh * 0.3
            lp = K.Pen(-m, yb - lh, fw + m, yb + 14)
            neg = tutar_.strip()[:1] in "-−–"
            sag = tutar_.replace("−", "-")
            sw = K.tw(sag, "courier", size)
            oda = fw - 60 - sw - 30
            zs = size - 2
            while zs > 19 and K.tw(kalem_, "courier", zs) > oda:
                zs -= 1
            sol = K.fit(kalem_, "courier", zs, oda)
            lp.text(24, yb, sol, "courier", zs, INK)
            lp.text(fw - 24, yb, sag, "courier", size, RED if neg else INK, anchor="rs")
            xx = 24 + K.tw(sol, "courier", zs) + 12
            while xx < fw - 24 - sw - 12:
                lp.ell(xx, yb - 4, 1.8, fill=DGREY)
                xx += 14
            lay = lp.done()
            katmanlar.append((lay, (0, yb - lh + m), t, t + min(d - 0.08, 0.55)))
            tv = tutar(tutar_)
            if tv is not None:
                acc += tv[0]
                _, br = lcd_degeri(tutar_)
                birim = birim or br
                dg, _ = lcd_degeri(tutar_.lstrip("-−– "))
                if dg and lcd_sigar(dg):
                    bit = t + min(d - 0.08, 0.55)
                    self._lcd_yaz(bit, up(kalem_), dg, birim, "−" if neg else "+", rozet)
                    dd = 0 if abs(acc - round(acc)) < 1e-6 else 2
                    self.lcd.append((bit + 0.2, "ARA TOPLAM", ("-" if acc < 0 else "") + _fmt(abs(acc), dd), birim,
                                     "−" if neg else "+", rozet))
        yl = 30 + 50 + n * lh + 10
        lp = K.Pen(-m, yl - 6, fw + m, yl + 16)
        lp.rr((20, yl, fw - 20, yl + 3), 1, fill=INK)
        lp.rr((20, yl + 8, fw - 20, yl + 10), 1, fill=INK)
        katmanlar.append((lp.done(), (0, yl - 6 + m), t_tot - 0.3, t_tot - 0.1))
        self.ogeler.append(FisOge(gor, kagit, (x0 - m, top - m), katmanlar, t_on))
        dg, br = lcd_degeri(s.deger)
        if dg and lcd_sigar(dg, 12 if not br else 11):
            self.lcd.append((t_tot, up(s.etiket or "TOPLAM"), dg, br or birim, "=", rozet))
        self.olay[s.i] = t_tot

    def _makine_araliklari(self) -> list[tuple[float, float, bool, bool]]:
        """Hesap makinesinin ekranda olduğu aralıklar: (giriş, çıkış, kayarak gelir mi, kayarak gider mi). Yalnız para
        sahnelerinde; arka arkaya para sahnelerinde yerinde kalır."""
        out = []
        for s in self.p:
            if not s.para:
                continue
            onceki = s.i > 0 and self.p[s.i - 1].para
            sonraki = s.i + 1 < len(self.p) and self.p[s.i + 1].para
            t_in = s.start if onceki else (0.0 if s.i == 0 else s.start + OGE0 - 0.1)
            t_out = s.end if sonraki else max(t_in + CALC_GIRIS + 0.3, s.end - 0.06)
            out.append((t_in, t_out, not onceki and s.i > 0, not sonraki))
        return out

    def makine_durumu(self, t: float) -> float | None:
        """Makine görünmüyorsa None; görünüyorsa yerine oturma oranı (0: köşede, 1: yerinde)."""
        for t_in, t_out, gir, cik in self.makine_ara:
            if t_in <= t < t_out:
                e = 1.0
                if gir:
                    e = min(e, K.ease_out_cubic((t - t_in) / CALC_GIRIS))
                if cik:
                    e = min(e, K.ease_in_out((t_out - t) / CALC_GIRIS))
                return e
        return None

    def makine(self, img: Image.Image, t: float) -> tuple | None:
        e = self.makine_durumu(t)
        if e is None or e <= 0.001:
            return None
        lay = self.hm.layer(*self.lcd_at(t))
        si = self.scene_at(t)
        y = CALC_Y + (64 if self.p[si].foto else 0)
        x = CALC_X1 - lay.width
        dy = -(y + lay.height - MAKINE_CLIP[1] + 6) * (1 - e)      # şeridin altından aşağı kayarak çıkar
        K.put(img, lay, x, y + dy, clip=MAKINE_CLIP)
        return (x, y + dy, x + lay.width, y + dy + lay.height)

    # ------------------------------------------------------------ içeriden: yapışkan not
    def _not_kur(self, s: Sahne, ust_alt: float) -> None:
        """Sarı yapışkan not sağda, başlığın üstünde: köşesinde kırmızı 'İÇERİDEN' etiketi; metin alıntı ya da
        sahnenin dış sesidir (dış ses kelime kelime söylenirken nota yazılır ve şeritte gizlenir; nota sığmazsa
        sahnenin başlığı yazılır, dış ses şeritte kalır). Son satırın altına kırmızı kalem çizgisi."""
        nw = 500
        nx0 = X1 - 20 - nw
        iw = nw - 74
        y_alt = self.alt_sinir(s)
        max_h = y_alt - max(ust_alt, UST0)
        kelimeler = [w.text for w in self.words[s.a:s.b]]
        soz = not s.alinti and 0 < len(kelimeler) <= 26
        metin = s.alinti or (" ".join(kelimeler) if soz else cumle(" ".join(s.baslik)))
        ust_pay = 66
        sec = None
        for size in (42, 40, 38, 36, 34, 32, 30):
            lh = size * 1.36
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
            size = 36
            sec = (size, size * 1.36, [metin.split()], ust_pay + size * 0.74 + 40)
        size, lh, lines, nh = sec
        top = y_alt - nh
        if soz:
            self.sessiz[s.i] = s.a
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
            kaynak = K.fit("— " + s.notu, "courier", 26, nw - lw - 90)
            pen.text(x1 - 26, y0 + 52, kaynak, "courier", 26, DGREY, anchor="rs")
        govde = pen.done()
        satirlar: list[YaziOge] = []
        wi = s.a
        y = y0 + ust_pay + size * 0.74
        t = s.start + OGE0 + 0.2
        for li, L in enumerate(lines):
            yz = Yazi(" ".join(L), size, MAVI, tohum("nt", s.i, li))
            if soz:
                zaman = []
                for j, w in enumerate(L):
                    wd = self.words[wi] if wi < len(self.words) else None
                    ta, tb = (wd.start - 0.04, max(wd.start + 0.08, wd.end - 0.04)) if wd else (s.end, s.end + 0.1)
                    ta = max(ta, s.start + OGE0)
                    tb = max(tb, ta + 0.05)
                    if j:
                        zaman.append((ta - 0.02, ta))
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
        not_ = NotOge([s.i], govde, (x0 - m, y0 - m), satirlar, [cizgi], s.start + OGE0)
        self.ogeler.append(not_)
        self.olay[s.i] = s.start + OGE0

    # ------------------------------------------------------------ son sahne
    def _cta_kur(self, s: Sahne, ust_alt: float) -> None:
        """'Senin listen:' kâğıdı (boş, elle çizilmiş üç satır), üstünde duran tükenmez kalem; 'Yorumlara yaz'
        söylenince YORUMLARA YAZ ↓ etiketi. Soru söylenmeye başlayınca şeritteki dış ses gizlenir (başlık sorudur)."""
        gor = [s.i]
        t0 = s.start + OGE0
        etiket = yorum_etiketi(76, tohum("yy", s.i))
        alt = self.alt_sinir(s, sag=False)
        kw, kh = 560, 400
        top = K.clamp(alt - kh - 26 - etiket.height, max(ust_alt, UST0) + 10, 10 ** 6)
        kh = min(kh, alt - 26 - etiket.height - top)
        x0 = X0 + 6
        sp = K.Sprite(kw, kh, margin=30)
        K.torn_paper(sp, 0, 0, kw, kh, POLAROID, tohum("ck", s.i), rim=None)
        kagit = sp.render(0)
        tp = K.Sprite(kw, kh, margin=30)
        K.tape(tp, kw / 2, 4, 170, 40, -3, tohum("ct", s.i), alpha=205)
        kagit.alpha_composite(tp.render(0))
        kagit = K.add_shadow(kagit, 8, 10, 0, 0.85)
        self.ogeler.append(KagitOge(gor, kagit, x0 - 30, top - 30, t0, z=22, yazi_mi=False))
        adim = (kh - 120) / 3
        y = top + 74
        self.ogeler.append(YaziOge(gor, Yazi("Senin listen:", 52, MAVI, tohum("cta", s.i)), x0 + 34, y, t0=t0 + 0.2,
                                   dur=0.55, z=24))
        t = t0 + 0.8
        ks = 38
        for j in range(3):
            yy = top + 120 + adim * (j + 0.7)
            self.ogeler.append(IzOge(gor, Iz([el_kutu(x0 + 40 + ks / 2, yy - ks / 2, ks, tohum("ck", j))], 3.8),
                                     t0=t, dur=0.18, z=24))
            nx = x0 + 40 + ks + 14
            self.ogeler.append(YaziOge(gor, Yazi(f"{j + 1}.", 46, MAVI, tohum("cn", j)), nx, yy, t0=t + 0.16,
                                       dur=0.15, z=24))
            x1 = x0 + kw - 50 - 50 * (j % 2)
            self.ogeler.append(IzOge(gor, Iz([el_cizgi(nx + 62, yy + 2, x1, yy, tohum("cc", j), amp=1.0)], 3.6),
                                     t0=t + 0.3, dur=0.22, z=24))
            t += 0.42
        im, _ = kalem(380, 8)
        self.ogeler.append(ResimSabit(gor, im, x0 + kw - im.width - 10, top + kh - im.height * 0.55, t0=t))
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
        self.ogeler.append(KagitOge(gor, etiket, X0 - 6, alt - etiket.height, t_y, z=40, nabiz=True))
        self.olay[s.i] = t_y

    # ------------------------------------------------------------ dış ses
    def serit(self) -> Image.Image:
        if "serit" not in self._layers:
            x0, y0, x1, y1 = SERIT
            sp = K.Sprite(x1 - x0, y1 - y0, margin=20)
            K.torn_paper(sp, 0, 0, x1 - x0, y1 - y0, POLAROID, 77, rim=INK, rim_w=3)
            self._layers["serit"] = sp.render(0, shadow=(6, 8, 0, 0.85))
        return self._layers["serit"]

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
        K.put(img, self.serit(), SERIT[0] - 20, SERIT[1] - 20)
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
        elif s.tur in PARA_TURLERI:
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

    # ------------------------------------------------------------ geçiş
    def eski_katman(self, si: int) -> tuple[Image.Image, tuple]:
        """si sahnesine geçerken eski sahnenin baskısı, son hâliyle ve üstündeki öğelerle tek parça (katman, köken)."""
        if si in self._eski:
            return self._eski[si]
        j = si - 1
        t = self.p[si].start - 1e-3
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        b = self.baskilar[j]
        K.put(lay, b.katman(self.ilerleme_p(j, t)), BASKI[0] - Baski.M, BASKI[1] - Baski.M, clip=BASKI_CLIP)
        for o in self.ogeler:
            if o.baski and o.gorunur(j):
                o.draw(self, lay, t)
        self.kalem_ucu = None
        bb = lay.getbbox() or (0, 0, W, H)
        self._eski = {si: (lay.crop(bb), bb[:2])}
        return self._eski[si]

    def baski_ciz(self, img: Image.Image, si: int, t: float, lt: float) -> str | None:
        """Baskıyı çizer; geçiş sürüyorsa eski baskıyla birlikte. Makas kesmesi sürüyorsa 'kesme' döner (eski parçalar
        öğelerden sonra, en üstte kesilir)."""
        b = self.baskilar[si]
        p = self.ilerleme_p(si, t)
        if si == 0 or lt >= self.gecis_suresi(si):
            b.ciz(img, p)
            return None
        tur = self.gecis_turu(si)
        eski, eo = self.eski_katman(si)
        if tur == "kesme":
            b.ciz(img, p)
            return "kesme"
        q = K.clamp(lt / GECIS)
        o = (BASKI[0] - Baski.M, BASKI[1] - Baski.M)
        if tur == "kayma":                          # eski sola kayıp döner, yeni sağdan dönerek gelir
            e = K.ease_in_out(q)
            r = eski.rotate(5 * e, resample=Image.BILINEAR, expand=True) if e > 0.01 else eski
            K.put(img, r, eo[0] - 1180 * e - (r.width - eski.width) / 2, eo[1] + 40 * e - (r.height - eski.height) / 2,
                  clip=BASKI_CLIP)
            yeni = b.katman(p)
            r = yeni.rotate(-4 * (1 - e), resample=Image.BILINEAR, expand=True) if e < 0.99 else yeni
            K.put(img, r, o[0] + 1180 * (1 - e) - (r.width - yeni.width) / 2, o[1] - (r.height - yeni.height) / 2,
                  clip=BASKI_CLIP)
        else:                                       # bant: yeni baskı üst bandından menteşeli, aşağı açılır
            K.put(img, eski, *eo, clip=BASKI_CLIP)
            e = K.ease_out_back(q, 1.2) if q < 1 else 1.0
            yeni = b.katman(p)
            h = max(2, int(yeni.height * K.clamp(e, 0.02, 1.08)))
            r = yeni.resize((yeni.width, h), Image.BILINEAR)
            if e < 1:
                golge = Image.new("RGBA", r.size, INK + (0,))
                golge.putalpha(r.getchannel("A").point(lambda v: int(v * 0.35 * (1 - K.clamp(e)))))
                r = r.copy()
                r.alpha_composite(golge)
            K.put(img, r, *o, clip=BASKI_CLIP)
        return None

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
        gecis = si > 0 and lt < YENI0                  # eski başlık çekilip yenisi gelene dek eski sahnenin durumu
        self.ilerleme(img, si - 1 if gecis else si, s.start - 1e-3 if gecis else t)
        self.kalem_ucu = None
        kesme = self.baski_ciz(img, si, t, lt)
        for o in self.ogeler:
            if o.baski and o.gorunur(si):
                o.draw(self, img, t)
        if kesme:
            eski, eo = self.eski_katman(si)
            K.card_cut(img, eski, lt, si, origin=eo, card=BASKI, x_end=SAFE[2] - 66, clip_top=BASKI_CLIP,
                       clips_bot=(BASKI_CLIP,))
        if gecis and lt < 0.2:
            self.basliklar[si - 1].draw(img, t, cikis=lt / 0.2)
        self.basliklar[si].draw(img, t)
        if gecis:
            self.anlati(img, si - 1, s.start - 1e-3)
        else:
            self.anlati(img, si, t)
        if self.hm is not None:
            self.makine(img, t)
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
