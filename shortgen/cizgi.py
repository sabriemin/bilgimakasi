"""Çizgi Roman şablonu ("Karar Senin" etkileşimli hikâye serisi): her sahne bir çizgi roman sayfası.

Sayfa: marka kâğıdı, iki köşede camgöbeği tram (Ben-Day) noktaları; kalın mürekkep kenarlı, sert gölgeli 1-3 panel;
her panelde kodla çizilen mekân ve aynı elle çizilmiş karakterler (cizgi_karakter.KADRO: görünüş sabit, yalnız poz ve
ifade değişir); tırnak içindeki söz konuşma balonunda, dış sesin geri kalanı sayfanın altındaki sarı anlatıcı kutusunda
kelime kelime belirir (ayrı altyazı yoktur). Bölümün tek gerçek bilgisi GERÇEK BİLGİ kartında, izleyicinin bildiği ama
karakterin bilmediği şey yırtık etiketlerde durur. Son sahnede ekran makasla kırmızı A ve camgöbeği B paneline kesilir;
seçenekler, büyük YORUMLARA A YA DA B YAZ çağrısı ve "Oylama 24 saat açık · Kurgusal hikâye" alt satırı gelir.

Ekran düzeni (1080x1920). Yazı ve önemli öğeler yalnız x 64-920, y 176-1532 arasında; gölgeler dahil hiçbir şey platform
arayüzüne (sağdaki düğmeler x > 935, üst çubuk y < 170, alttaki açıklama y > 1540) taşmaz:
  178-250   filigran (sol ve sağ arasında brand.json'daki sürede yer değiştirir)
  262-326   üst bant: KARAR SENİN + 1. BÖLÜM yırtık etiketleri; sağda her karede KURGU etiketi
  346-1200  paneller (GERÇEK BİLGİ ya da ipucu kartı olan sahnede paneller 912'de biter, kart altta)
  1226-1530 sarı anlatıcı kutusu (dış ses kelime kelime) ve sağında maskot Makas
Son sahne (ab): soru etiketi, A | B panelleri (makas oluktan keser), seçenek kartları, çağrı ve alt satır.

Senaryo eşlemesi: sahnenin tarifi Scene.cizgi (script.CizgiSahne; spec.card["cizgi"]). Tarifsiz sahne düz zeminli tek
panel olur. Seri adı ve bölüm numarası ilk sahnenin tarifinden gelir (boşsa KARAR SENİN, numarasız).
Geçişler: yeni sayfanın panelleri sırayla (sağdan sola değil, okuma sırasıyla) hafifçe yukarı kayarak gelir; her dört
sahnede bir eski sayfanın panelleri kart şablonunun makas kesmesiyle (kart.card_cut) kesilir. Hız: sayfa, paneller,
balonlar, anlatıcı kutusu ve kartlar sahne başına bir kez çizilir; kare başına yalnız katmanlar birleştirilir.
"""
from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import cizgi_karakter as CK
from . import cizgi_mekan as CM
from . import cizgi_motor as CZM
from . import cizgi_sabit as CZ
from . import kart as K
from .cizgi_motor import (CYAN, CYAN_DK, INK, OFF, PAPER, RED, SS, WHITE, YELLOW, Balon, blend, cap_h, etiket,
                          etiket_olcu, sar, sigdir, tw, up)
from .nasil import Mascot, ease_pop
from .render import SceneSpec
from .voice import Word

W, H, FPS = K.W, K.H, K.FPS
SAFE = K.SAFE                              # (0, 170, 935, 1540)
CLIP = (0, SAFE[1], SAFE[2], SAFE[3])
X0, X1 = 64, 920                           # panellerin ve yazının yatay sınırı (gölge 930'da biter)
HEAD_CY = 294                              # üst bant
PANEL_Y0, PANEL_Y1 = 346, 1198             # panel alanı
KARTLI_Y1 = 900                            # özel kartlı sahnede panellerin alt sınırı
KART_Y0, KART_Y1 = 930, 1200               # özel kartın alanı
CAP = (72, 1232, 748, 1528)                # anlatıcı kutusu (kâğıdın en geniş hâli)
CAP_FONT, CAP_SIZES, CAP_LINES = "courier", (40, 38, 36), 4
MASKOT = (848, 1430, 0.40)                 # gövde merkezi ve ölçek (anlatıcı kutusunun sağında)
WM_OLCEK = 0.6
GUTTER = 22
ENTRY = 0.22                               # panelin geliş süresi
STAGGER = 0.32                             # paneller arası gecikme
CUT_EVERY = 4                              # her kaç sahnede bir makas kesmesi
QUOTE = "\"“”«»"
# anlatıcı kutusunda sıradaki kelimeler: sarı kâğıtta soluk ama okunur (sessiz izleyen cümlenin tamamını görür,
# söylenen kelime mürekkep olur)
GHOST = (196, 160, 40)


# ---------------------------------------------------------------- tarif okuma (sözlük; pipeline Scene.model_dump verir)
def tarif(spec: SceneSpec) -> dict:
    c = (spec.card or {}).get("cizgi") or {}
    return c if isinstance(c, dict) else {}


def seri_bilgisi(specs) -> tuple[str, int]:
    c = tarif(specs[0]) if specs else {}
    seri = up((c.get("seri") or "").strip()) or CZ.SERI_ADI
    try:
        bolum = max(0, int(c.get("bolum") or 0))
    except (TypeError, ValueError):
        bolum = 0
    return seri, bolum


def kart_turu(spec: SceneSpec) -> str:
    k = tarif(spec).get("kart") or {}
    return (k.get("tur") or "") if isinstance(k, dict) else ""


# ---------------------------------------------------------------- panel düzenleri
def panel_polys(duzen: str, n: int, y0: float = PANEL_Y0, y1: float = PANEL_Y1) -> list[list[tuple]]:
    """Düzenin panel çokgenleri (saat yönünde, tasarım koordinatı). Oluklar hafif eğik (çizgi roman hareketi).
    Tarifteki panel sayısı düzenden azsa düzen küçülür (uc -> ust_alt -> tek)."""
    g = GUTTER
    if duzen == "uc" and n < 3:
        duzen = "ust_alt" if n == 2 else "tek"
    if duzen in ("ust_alt", "yan_yana") and n < 2:
        duzen = "tek"
    h = y1 - y0
    if duzen == "ust_alt":
        ym = y0 + h * 0.5
        return [[(X0, y0 + 4), (X1, y0), (X1, ym - g / 2 - 6), (X0, ym - g / 2 + 6)],
                [(X0, ym + g / 2 + 6), (X1, ym + g / 2 - 6), (X1, y1 - 4), (X0, y1)]]
    if duzen == "yan_yana":
        xm = (X0 + X1) / 2
        return [[(X0, y0), (xm - g / 2 + 8, y0), (xm - g / 2 - 8, y1), (X0, y1)],
                [(xm + g / 2 + 8, y0), (X1, y0), (X1, y1), (xm + g / 2 - 8, y1)]]
    if duzen == "uc":
        ym = y0 + h * 0.46
        xm = (X0 + X1) / 2
        return [[(X0, y0 + 4), (X1, y0), (X1, ym - g / 2 - 6), (X0, ym - g / 2 + 6)],
                [(X0, ym + g / 2 + 6), (xm - g / 2 + 8, ym + g / 2 + 2), (xm - g / 2 - 8, y1), (X0, y1)],
                [(xm + g / 2 + 8, ym + g / 2 + 2), (X1, ym + g / 2 - 6), (X1, y1), (xm + g / 2 - 8, y1)]]
    return [[(X0, y0 + 4), (X1, y0), (X1, y1 - 4), (X0, y1)]]


def ic_kutu(poly) -> tuple:
    """Çokgenin içine sığan eksen hizalı kutu (eğik olukların içi)."""
    ic = CZM.iceri(poly, CZM.KENAR)
    xs = sorted(p[0] for p in ic)
    ys = sorted(p[1] for p in ic)
    return (xs[1], ys[1], xs[2], ys[2])


# ---------------------------------------------------------------- karakter yerleşimi
@dataclass
class Yer:
    """Panele yerleşmiş bir karakter: VB'yi tasarım koordinatına çeviren ölçek ve köken."""
    kid: str
    s: float
    x: float          # VB x=-100'ün tasarım x'i
    y: float          # VB y=0'ın tasarım y'si
    yon: str
    svg: str

    def p(self, vx, vy):
        if self.yon == "sol":
            vx = 400 - vx
        return (self.x + (vx + 100) * self.s, self.y + vy * self.s)

    @property
    def bas(self) -> tuple:
        """(baş merkezi x, saç üstü y, ağız y, baş yarı genişliği) tasarım koordinatında."""
        cx, _ = self.p(200, 0)
        return (cx, self.y + (50 + CK.BAS_DY) * self.s, self.y + (250 + CK.BAS_DY) * self.s, 75 * self.s)


KONUM_X = {"sol": 0.27, "orta": 0.5, "sag": 0.73}


def yerlestir(karakterler: list, box, balonlu: bool) -> list[Yer]:
    """Paneldeki karakterler: bust belden yukarı (VB y=600 panelin altında), boy boydan (ayak panelin altına yakın).
    Balonlu panelde figürler küçülür, baş aşağı iner (balona yer kalır)."""
    x0, y0, x1, y1 = box
    pw, ph = x1 - x0, y1 - y0
    n = max(1, len(karakterler))
    out = []
    for i, k in enumerate(karakterler[:3]):
        kid = k.get("id") or "kuzey"
        konum = k.get("konum") or ("orta" if n == 1 else ("sol", "sag", "orta")[i])
        if n == 2 and konum == "orta":
            konum = ("sol", "sag")[i]
        cerceve = k.get("cerceve") or "bust"
        if (k.get("poz") or "") == "sut":
            cerceve = "boy"
        # bir figürün en çok genişliği (VB 400 birim; kollar kenarda kırpılabilir, yüz panelde kalır)
        en_cok = pw / n * (1.0 if n > 1 else 1.1)
        if cerceve == "boy":
            s = min(ph * 0.8 / (CK.BOY[1] - CK.BOY[0]), en_cok / 400)
            s *= 0.86 if balonlu else 1.0
            y = y1 - 12 - CK.BOY[1] * s
        else:
            s = min(ph * (0.80 if balonlu else 0.92) / (CK.BUST[1] - CK.BUST[0]), en_cok / 400)
            y = y1 + 6 - CK.BUST[1] * s
        cx = x0 + pw * KONUM_X.get(konum, 0.5)
        yon = "sag" if konum == "sol" else ("sol" if konum == "sag" else "sag")
        if (k.get("poz") or "") == "isaret" and konum == "orta":
            yon = "sag"
        svg = CK.figur_svg(kid, k.get("poz") or "dur", k.get("ifade") or "normal", yon)
        out.append(Yer(kid, s, cx - 300 * s, y, yon, svg))
    return out


# ---------------------------------------------------------------- balon (kelime kelime)
class SozBalonu:
    """Konuşma balonu: şekil bir kez, sözler okundukça. Kuyruk konuşanın ağzına doğru, baş kapanmaz."""

    def __init__(self, text: str, box, konusan: Yer | None, tur: str, seed: int, ust_sinir: float):
        x0, y0, x1, y1 = box
        pw = x1 - x0
        genislik = min(pw * 0.72, 560) - 60
        self.b = Balon(text, 0, 0, genislik, uc=None, tur=tur, size=50, min_size=38, satir=4, seed=seed)
        bw, bh = self.b.w, self.b.h
        if konusan is not None:
            hx_, htop, mouth, hw = konusan.bas
            sag_taraf = hx_ < (x0 + x1) / 2
            cx = hx_ + (bw / 2 + hw * 0.4 if sag_taraf else -(bw / 2 + hw * 0.4))
        else:
            cx = (x0 + x1) / 2
        cx = max(x0 + bw / 2 + 14, min(min(x1, X1) - bw / 2 - 14, cx))
        cy = max(ust_sinir + bh / 2, y0 + 18 + bh / 2)
        if konusan is not None:
            hx_, htop, mouth, hw = konusan.bas
            # balon başla yatayda çakışıyorsa başın üstünde kalır; yer yoksa yana kayar
            if abs(cx - hx_) < bw / 2 + hw and cy + bh / 2 > htop - 12:
                cy = max(ust_sinir + bh / 2, htop - 12 - bh / 2)
            # kuyruk konuşanın başının hemen üstünde biter (başa binmez)
            tip = (hx_ + (hw * 0.45 if cx > hx_ else -hw * 0.45), max(cy + bh / 2 + 18, htop - 14))
        else:
            tip = None
        self.b.cx, self.b.cy, self.b.uc = cx, cy, tip
        self.words = self.b.text.split()

    @property
    def kutu(self):
        return self.b.box

    def sekil(self, pen: K.Pen):
        CZM.svg_tam(pen, self.b.svg())

    def yazi(self, pen: K.Pen, n: int):
        """İlk n kelime (satırlar sabit; kalan kelimeler yazılmaz)."""
        b = self.b
        ch = cap_h(b.font, b.size)
        y = b.cy - b.th / 2 + ch
        sp = tw(" ", b.font, b.size)
        k = 0
        for L in b.lines:
            ws = L.split(" ")
            x = b.cx - tw(L, b.font, b.size) / 2
            for w in ws:
                if k < n:
                    pen.text(x, y, w, b.font, b.size, b.yazi)
                x += tw(w, b.font, b.size) + sp
                k += 1
            y += b.lh


# ---------------------------------------------------------------- dış ses: anlatıcı ve balon kelimeleri
def tirnak_ici(texts: list[str]) -> list[bool]:
    """Her kelimenin tırnak içinde olup olmadığı (tırnak işareti kelimeye bitişik yazılır)."""
    out, ic = [], False
    for t in texts:
        acar = bool(t) and t[0] in QUOTE
        if acar and not ic:
            ic = True
            kapar = len(t) > 1 and t.rstrip(".,!?;:…")[-1:] in QUOTE
            out.append(True)
            if kapar:
                ic = False
            continue
        out.append(ic)
        if ic and t.rstrip(".,!?;:…")[-1:] in QUOTE:
            ic = False
    return out


def temiz(t: str) -> str:
    return t.strip(QUOTE).replace("\"", "")


class Anlatici:
    """Sarı anlatıcı kutusunun sayfaları: kelimeler (genel indeks) satırlara ve en çok CAP_LINES satırlık sayfalara."""

    def __init__(self, idx: list[int], texts: dict[int, str], width: float):
        self.idx = idx
        self.texts = texts
        self.size, self.pages = CAP_SIZES[-1], []
        uzun = max((tw(texts[i], CAP_FONT, 1.0) for i in idx), default=0.0)   # 1 px'te en uzun kelime
        for size in CAP_SIZES:
            lines = self._satirlar(size, width)
            if len(lines) <= CAP_LINES and uzun * size <= width:
                self.size, self.pages = size, [lines]
                break
        else:
            # tek bir kelime bile sığmıyorsa (çok uzun Türkçe kelime) yazı küçülür, kutudan taşmaz
            if uzun * self.size > width:
                self.size = max(16, int(width / uzun))
            lines = self._satirlar(self.size, width)
            self.pages = self._bol(lines)
        self.page_first = [p[0][0] for p in self.pages if p and p[0]]

    def _satirlar(self, size, width):
        lines, cur, cw = [], [], 0.0
        sp = tw(" ", CAP_FONT, size)
        for i in self.idx:
            ww = tw(self.texts[i], CAP_FONT, size)
            if cur and cw + sp + ww > width:
                lines.append(cur)
                cur, cw = [], 0.0
            cw += (sp if cur else 0) + ww
            cur.append(i)
        if cur:
            lines.append(cur)
        return lines

    def _bol(self, lines):
        """Satırları sayfalara böler: sayfa mümkünse cümle sonunda biter."""
        pages, cur = [], []
        for L in lines:
            cur.append(L)
            son = self.texts[L[-1]][-1:] in ".?!:"
            if len(cur) == CAP_LINES or (son and len(cur) >= 2):
                pages.append(cur)
                cur = []
        if cur:
            pages.append(cur)
        return pages

    def sayfa_of(self, wi: int) -> int:
        return max(0, bisect.bisect_right(self.page_first, wi) - 1)


# ---------------------------------------------------------------- sahne
@dataclass
class Sahne:
    i: int
    start: float
    end: float
    a: int
    b: int
    c: dict
    tur: str
    polys: list = field(default_factory=list)
    paneller: list = field(default_factory=list)     # [(katman, (x, y), giriş zamanı)]
    balon: SozBalonu | None = None
    balon_idx: list = field(default_factory=list)    # balondaki kelimelerin genel indeksleri
    anlatici: Anlatici | None = None
    sesler: list = field(default_factory=list)       # [((katman, x, y), zaman)]
    ab: dict = field(default_factory=dict)           # son sahne: soru, a, b


class CizgiVideo:
    def __init__(self, scenes, words: list[Word], meta: dict, bcfg: dict, yalniz_icerik: bool = False):
        """yalniz_icerik: sayfa kâğıdı çizilmez, frame() gren eklemeden RGBA döner (testlerde güvenli alan denetimi)."""
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        self.yalniz_icerik = yalniz_icerik
        on = bcfg.get("enabled", False)
        self.brand_on = on
        self.intro = bool(on and bcfg.get("intro_cut", True))
        self.wm_every = float(bcfg.get("watermark_switch_seconds", 7) or 7)
        self.wm_alpha = float(bcfg.get("watermark_opacity", 0.85) or 0.85)
        self.cut_on = bool(on and int(bcfg.get("cut_transition_every", 4) or 0) > 0)
        self.n = n = len(scenes)
        self.starts = [w.start for w in words]
        self.seri, self.bolum = seri_bilgisi(scenes)
        ranges, a = [], 0
        for i, s in enumerate(scenes):
            b = min(len(words), a + len(s.words)) if i < n - 1 else len(words)
            ranges.append((a, b))
            a = b
        self.ranges = ranges
        self.sahneler = [Sahne(i, s.start, s.end, ranges[i][0], ranges[i][1], tarif(s), kart_turu(s))
                         for i, s in enumerate(scenes)]
        self.scene_starts = [s.start for s in scenes]
        self.mascot = Mascot()
        self._c: dict = {}
        self._hazir: set = set()

    # ------------------------------------------------------------ zaman
    def scene_at(self, t: float) -> int:
        return max(0, bisect.bisect_right(self.scene_starts, t) - 1)

    def visible(self, a: int, b: int, t: float) -> int:
        """[a, b) aralığında t anına kadar söylenmeye başlamış kelime sayısı."""
        return max(0, min(b, bisect.bisect_right(self.starts, t + 0.02, a, b)) - a)

    def word_time(self, a, b, pred) -> float | None:
        for i in range(a, b):
            if pred(self.words[i].text):
                return self.words[i].start
        return None

    # ------------------------------------------------------------ sabit katmanlar
    def sayfa(self) -> Image.Image:
        if "sayfa" not in self._c:
            if self.yalniz_icerik:   # kâğıt yok; üst bant içeriktir (güvenli alan denetimine girer)
                bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                bg.alpha_composite(self.ust_bant(), (0, 0))
                self._c["sayfa"] = bg
            else:
                bg = Image.new("RGBA", (W, H), PAPER + (255,))

                def yog(X, Y):
                    d1 = np.hypot(X - 0, Y - 150) / 820
                    d2 = np.hypot(X - W, Y - H + 40) / 900
                    return np.maximum(1 - d1, 1 - d2) * 1.15 - 0.2

                bg.alpha_composite(CZM.tram(W, H, blend(PAPER, CYAN, 0.55), 26, 18, yog))
                bg.alpha_composite(self.ust_bant(), (0, 0))
                self._c["sayfa"] = bg
        return self._c["sayfa"]

    def ust_bant(self) -> Image.Image:
        """KARAR SENİN + N. BÖLÜM (solda) ve KURGU (sağda) etiketleri."""
        if "bant" not in self._c:
            pen = K.Pen(0, 0, W, HEAD_CY + 60)
            k = CZ.KURGU_ETIKETI
            wk, _ = etiket_olcu(k, 36)
            t = f"{self.bolum}. BÖLÜM" if self.bolum else ""
            size = 50
            while size > 20:        # seri adı ve bölüm, KURGU etiketine kadar sığar
                w1 = etiket_olcu(self.seri, size)[0]
                w2 = etiket_olcu(t, size)[0] + 14 if t else 0
                if X0 + w1 + w2 <= X1 - wk - 34:
                    break
                size -= 2
            w1, _ = etiket_olcu(self.seri, size)
            etiket(pen, self.seri, size, OFF, INK, 21, X0 + w1 / 2, HEAD_CY, rot=-1.0, shadow=(5, 6, 0, 0.9))
            if t:
                w2, _ = etiket_olcu(t, size)
                etiket(pen, t, size, OFF, RED, 22, X0 + w1 + 14 + w2 / 2, HEAD_CY + 2, rot=1.5, shadow=(5, 6, 0, 0.9))
            etiket(pen, k, 36, INK, YELLOW, 23, X1 - 10 - wk / 2, HEAD_CY + 2, rot=2.0, shadow=(4, 5, 0, 0.9))
            self._c["bant"] = pen.done()
        return self._c["bant"]

    # ------------------------------------------------------------ panel çizimi
    def panel_katmani(self, poly, pc: dict, karakterler: list[Yer], seed: int, zemin=OFF) -> tuple:
        """Bir panelin katmanı (kenar, gölge, mekân, karakterler); (katman, (x, y)) döndürür."""
        x0, y0, x1, y1 = CZM.kutu(poly)
        bx0, by0 = int(math.floor(x0)) - 4, int(math.floor(y0)) - 4
        bx1, by1 = int(math.ceil(x1)) + CZM.GOLGE[0] + 6, int(math.ceil(y1)) + CZM.GOLGE[1] + 6
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        box = (x0, y0, x1, y1)
        m = CM.mekan(pc.get("mekan") or "bos", box, pc.get("yazi") or [], seed)

        def ciz(pen):
            CZM.svg_tam(pen, m.arka)
            for tb, renk, aralik, aci, yog in m.tram:
                CZM.tram_pen(pen, tb, renk, aralik, aci, yog)
            for y in karakterler:
                pen.svg(y.svg, (-100, 0, 600, 1000), y.x, y.y, 600 * y.s)
            if m.on:
                CZM.svg_tam(pen, m.on)
            for x, yy, t, f, s, c, an in m.yazi:
                pen.text(x, yy, t, f, s, c, anchor=an)

        CZM.panel(img, poly, ciz, zemin=zemin)
        return img.crop((bx0, by0, bx1, by1)), (bx0, by0), m

    def hazirla(self, si: int) -> Sahne:
        S = self.sahneler[si]
        if si in self._hazir:
            return S
        self._hazir.add(si)
        c = S.c
        texts = {i: self.words[i].text for i in range(S.a, S.b)}
        ic = tirnak_ici([texts[i] for i in range(S.a, S.b)])
        balon_idx = [S.a + k for k, v in enumerate(ic) if v]
        cap_idx = [S.a + k for k, v in enumerate(ic) if not v]
        bal = c.get("balon") if isinstance(c.get("balon"), dict) else None
        if not bal:              # balon yoksa tırnak içi de anlatıcı kutusuna yazılır
            cap_idx, balon_idx = list(range(S.a, S.b)), []
        S.balon_idx = balon_idx
        if S.tur != "ab":
            S.anlatici = Anlatici(cap_idx, {i: texts[i] for i in cap_idx}, CAP[2] - CAP[0] - 56) if cap_idx else None
        if S.tur == "ab":
            self.hazirla_ab(S)
            return S
        paneller = [p for p in (c.get("paneller") or []) if isinstance(p, dict)][:3] or [{"mekan": "bos"}]
        y1 = KARTLI_Y1 if S.tur in ("gercek", "ipucu") else PANEL_Y1
        S.polys = panel_polys(c.get("duzen") or "tek", len(paneller), PANEL_Y0, y1)
        paneller = paneller[:len(S.polys)]
        bp = int((bal or {}).get("panel") or 0) if bal else -1
        bp = min(max(bp, 0), len(S.polys) - 1) if bal else -1
        stag = min(STAGGER, max(0.12, (S.end - S.start) * 0.5 / max(1, len(S.polys))))
        yerler_bal = None
        for k, (poly, pc) in enumerate(zip(S.polys, paneller)):
            box = ic_kutu(poly)
            ys = yerlestir([x for x in (pc.get("karakterler") or []) if isinstance(x, dict)], box, k == bp)
            lay, xy, m = self.panel_katmani(poly, pc, ys, seed=si * 7 + k + 1)
            S.paneller.append((lay, xy, k * stag))
            if k == bp:
                yerler_bal = (ys, box)
            ses = (pc.get("ses") or "").strip()
            if ses:
                S.sesler.append((self.ses_katmani(ses, box, si + k, m.koyu), k * stag + 0.3))
        if bal is not None and yerler_bal is not None:
            ys, box = yerler_bal
            kon = next((y for y in ys if y.kid == bal.get("konusan")), ys[0] if ys else None)
            if balon_idx:
                text = " ".join(temiz(self.words[i].text) for i in balon_idx)
            else:
                text = (bal.get("metin") or "").strip()
            if text:
                S.balon = SozBalonu(text, box, kon, bal.get("tur") or "konus", si, PANEL_Y0 - 6)
        return S

    def ses_katmani(self, text: str, box, seed: int, koyu: bool):
        x0, y0, x1, y1 = box
        size = min(120, (x1 - x0) * 0.22)
        cx, cy = x1 - (x1 - x0) * 0.26, y0 + (y1 - y0) * 0.2
        while size > 40 and tw(up(text), "anton", size) + 60 > (x1 - x0) * 0.5:
            size -= 4
        pen = K.Pen(cx - 300, cy - 160, cx + 300, cy + 160)
        CZM.sfx(pen, text, cx, cy, size, renk=YELLOW, kalinlik=size * 0.09, rot=-8 + (seed % 3) * 5)
        lay = pen.done()
        return (lay, cx - 300, cy - 160)

    # ------------------------------------------------------------ özel kartlar
    def kart_katmani(self, S: Sahne) -> Image.Image | None:
        key = ("kart", S.i)
        if key in self._c:
            return self._c[key]
        k = S.c.get("kart") or {}
        pen = K.Pen(0, KART_Y0 - 40, SAFE[2], KART_Y1 + 30)
        if S.tur == "gercek":
            baslik = up((k.get("baslik") or "").strip()) or CZ.GERCEK_BASLIK
            metin = (k.get("metin") or "").strip()
            kaynak = (k.get("kaynak") or "").strip()
            x0, x1 = X0 + 6, X1 - 14
            yt = KART_Y0 + 34
            size, lines = sigdir(metin, "archivo", x1 - x0 - 64, 46, 30, 3)
            lh = size * 1.32       # Türkçe şapka/nokta üst satıra değmesin diye geniş satır aralığı
            ksz = 28
            ust = 58               # başlık etiketi kâğıdın üst kenarına biner: yazı onun altında başlar
            hh = ust + cap_h("archivo", size) + (len(lines) - 1) * lh + (ksz + 22 if kaynak else 8) + 26
            hh = min(hh, KART_Y1 - yt)
            sp = K.Sprite(x1 - x0, hh, margin=24)
            K.torn_paper(sp, 0, 0, x1 - x0, hh, OFF, 61, rim=None)
            y = ust + cap_h("archivo", size)
            for L in lines:
                sp.text((32, y), L, "archivo", size, INK)
                y += lh
            if kaynak:
                sp.text((32, y - lh + size * 0.4 + ksz + 18), kaynak, "courier", ksz, K.DGREY)
            im = sp.render_ss(-1.0, (8, 10, 0, 0.9))
            pen.paste(im, x0 - (im.width / SS - (x1 - x0)) / 2, yt - (im.height / SS - hh) / 2)
            wl, _ = etiket_olcu(baslik, 46)
            etiket(pen, baslik, 46, OFF, RED, 62, x0 + 10 + wl / 2, yt - 2, rot=-2.5, shadow=(5, 6, 0, 0.9))
        elif S.tur == "ipucu":
            baslik = up((k.get("baslik") or "").strip())
            parca = [p.strip() for p in re.split(r"(?<=,)\s+", baslik) if p.strip()] or [baslik]
            if len(parca) > 2:
                parca = [parca[0], " ".join(parca[1:])]
            renk = [(YELLOW, INK), (OFF, RED)]
            y = KART_Y0 + 40
            for j, p in enumerate(parca[:2]):
                size = 80
                while size > 40 and etiket_olcu(p, size)[0] > X1 - X0 - 40:
                    size -= 2
                w, hh = etiket_olcu(p, size)
                fg, bg = renk[j]
                etiket(pen, p, size, fg, bg, 71 + j, X0 + 8 + w / 2 + j * 24, y + hh / 2 - 30, rot=(-2.0, 1.5)[j],
                       shadow=(8, 10, 0, 0.9))
                y += hh + 16
        else:
            self._c[key] = None
            return None
        self._c[key] = (pen.done(), pen.y0)
        return self._c[key]

    # ------------------------------------------------------------ son sahne: A | B
    def hazirla_ab(self, S: Sahne) -> None:
        k = S.c.get("kart") or {}
        paneller = [p for p in (S.c.get("paneller") or []) if isinstance(p, dict)]
        pa = paneller[0] if paneller else {"mekan": "istanbul"}
        pb = paneller[1] if len(paneller) > 1 else {"mekan": "samsun"}
        y0, y1 = AB_Y0, AB_Y1
        xm = (X0 + X1) / 2
        g = GUTTER
        S.polys = [[(X0, y0), (xm - g / 2 + 6, y0), (xm - g / 2 - 6, y1), (X0, y1)],
                   [(xm + g / 2 + 6, y0), (X1, y0), (X1, y1), (xm + g / 2 - 6, y1)]]
        for j, (poly, pc) in enumerate(zip(S.polys, (pa, pb))):
            box = ic_kutu(poly)
            # büyük harfe yer: karakterler panelin alt ve iç tarafında
            ys = yerlestir([x for x in (pc.get("karakterler") or []) if isinstance(x, dict)],
                           (box[0] + 40, box[1] + 60, box[2], box[3]), False)
            lay, xy, _ = self.panel_katmani(poly, pc, ys, seed=90 + j)
            S.paneller.append((lay, xy, 0.0))
        S.ab = {"soru": up((k.get("baslik") or "").strip()), "a": up((k.get("a") or "").strip()),
                "b": up((k.get("b") or "").strip())}

    def ab_parcalar(self, S: Sahne) -> dict:
        key = ("ab", S.i)
        if key in self._c:
            return self._c[key]
        d = S.ab
        P: dict = {}
        # soru etiketi
        if d["soru"]:
            size = 72
            while size > 44 and etiket_olcu(d["soru"], size)[0] > X1 - X0 - 20:
                size -= 2
            pen = K.Pen(0, 330, SAFE[2], AB_Y0)
            w, h = etiket_olcu(d["soru"], size)
            etiket(pen, d["soru"], size, OFF, INK, 81, X0 + w / 2, (334 + AB_Y0) / 2 + 2, rot=-1.2,
                   shadow=(6, 8, 0, 0.9))
            P["soru"] = (pen.done(), 0, 330)
        # dev harfler
        for harf, x in (("A", X0 + 70), ("B", (X0 + X1) / 2 + 74)):
            pen = K.Pen(x - 120, AB_Y0 - 20, x + 120, AB_Y0 + 230)
            CZM.sfx(pen, harf, x, AB_Y0 + 104, 160, renk=YELLOW, kalinlik=12, rot=-6 if harf == "A" else 5)
            P[harf] = (pen.done(), x - 120, AB_Y0 - 20)
        # seçenek kartları: üç satıra kadar, geniş satır aralığı (harf noktaları üst satıra değmez)
        hmax = 0
        olc = {}
        for harf in ("a", "b"):
            gen = (X1 - X0) / 2 - 22
            size, lines = sigdir(d[harf], "anton", gen - 44, 50, 34, 3)
            lh = size * 1.24       # Türkçe noktalar (İ, Ş) üst satıra değmesin diye geniş satır aralığı
            h = cap_h("anton", size) + (len(lines) - 1) * lh + 48
            olc[harf] = (gen, size, lines, lh)
            hmax = max(hmax, h)
        for j, harf in enumerate(("a", "b")):
            gen, size, lines, lh = olc[harf]
            x = X0 + 4 if j == 0 else X1 - 12 - gen     # sağ kartın gölgesi 935'i geçmez
            sp = K.Sprite(gen, hmax, margin=24)
            K.torn_paper(sp, 0, 0, gen, hmax, OFF, 83 + j, rim=None)
            blok = cap_h("anton", size) + (len(lines) - 1) * lh
            yy = (hmax - blok) / 2 + cap_h("anton", size)
            for L in lines:
                sp.text((gen / 2, yy), L, "anton", size, INK, anchor="ms")
                yy += lh
            im = sp.render((-1.2, 1.0)[j], (6, 8, 0, 0.9))
            P["kart_" + harf] = (im, x + gen / 2 - im.width / 2, AB_Y1 + 20 + hmax / 2 - im.height / 2)
        P["kart_h"] = hmax
        # çağrı: YORUMLARA / [A] YA DA [B] YAZ.
        cs = 70
        cy0 = AB_Y1 + 20 + hmax + 26
        pen = K.Pen(0, cy0 - 10, SAFE[2], cy0 + 230)
        w1, h1 = etiket_olcu("YORUMLARA", cs)
        etiket(pen, "YORUMLARA", cs, OFF, INK, 91, X0 + w1 / 2, cy0 + h1 / 2 + 4, rot=-1.5, shadow=(8, 10, 0, 0.9))
        y2 = cy0 + h1 + 16
        self.cta_ab(pen, X0, y2, cs)
        P["cta"] = (pen.done(), 0, cy0 - 10)
        P["cta_y1"] = y2 + cs * 1.3
        P["cta_cy2"] = y2 + cs * 0.65
        # alt satırlar: sonraki bölüm (kâğıt şeridinde değil, kendi satırında, büyük) + oylama/kurgu notu
        t = CZ.AB_SONRAKI.format(sonraki=self.bolum + 1) if self.bolum else CZ.AB_SONRAKI_NUMARASIZ
        size = 40
        while size > 26 and tw(t, "courier", size) > X1 - X0 - 8:
            size -= 1
        P["sonraki_size"] = size
        yb = P["cta_y1"] + 22 + size
        asz = 30
        pen = K.Pen(0, yb - size - 10, SAFE[2], yb + 70)
        pen.text(X0 + 2, yb, t, "courier", size, INK)
        alt = CZ.AB_ALT
        aw = tw(alt, "courier", asz) + 36
        pen.rr((X0, yb + 18, X0 + aw, yb + 62), 6, fill=INK + (255,))
        pen.text(X0 + 18, yb + 50, alt, "courier", asz, OFF)
        P["alt"] = (pen.done(), 0, yb - size - 10)
        P["alt_y1"] = yb + 62
        self._c[key] = P
        return P

    def cta_ab(self, pen: K.Pen, x, y, size):
        """[A] YA DA [B] YAZ. : sarı yırtık etikette mürekkep yazı; A kırmızı yuvarlak rozette beyaz, B camgöbeği kare
        rozette mürekkep harf (rozetler kendi zeminiyle okunur; renk körü izleyici için biçimleri de farklı)."""
        parts = [("A", "rozA"), (" YA DA ", None), ("B", "rozB"), (" YAZ.", None)]
        r = size * 0.62
        widths = [(2 * r + 12) if k else tw(t, "anton", size) for t, k in parts]
        total = sum(widths)
        sp = K.Sprite(total + size * 0.5, size * 1.3, margin=26)
        K.torn_paper(sp, 0, 0, total + size * 0.5, size * 1.3, YELLOW, 93, rim=OFF)
        xx = size * 0.25
        base = size * 1.3 / 2 + cap_h("anton", size) / 2
        for (t, k), w in zip(parts, widths):
            if k:
                cx, cy = xx + w / 2, size * 0.65
                hb = cy + cap_h("anton", size * 0.8) / 2      # harf rozetin tam ortasında
                if k == "rozA":
                    sp.dot(cx, cy, r + 4, INK + (255,))
                    sp.dot(cx, cy, r, RED + (255,))
                    sp.text((cx, hb), "A", "anton", size * 0.8, WHITE, anchor="ms")
                else:
                    sp.polygon([(cx - r - 4, cy - r - 4), (cx + r + 4, cy - r - 4), (cx + r + 4, cy + r + 4),
                                (cx - r - 4, cy + r + 4)], INK + (255,))
                    sp.polygon([(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)], CYAN + (255,))
                    sp.text((cx, hb), "B", "anton", size * 0.8, INK, anchor="ms")
            else:
                sp.text((xx, base), t, "anton", size, INK)
            xx += w
        im = sp.render_ss(1.2, (8, 10, 0, 0.9))
        pen.paste(im, x - 26, y - 26)

    def draw_ab(self, img: Image.Image, S: Sahne, lt: float) -> None:
        P = self.ab_parcalar(S)
        dur = S.end - S.start
        ta = self.word_time(S.a, S.b, lambda w: w.strip().upper().startswith("A:"))
        tb = self.word_time(S.a, S.b, lambda w: w.strip().upper().startswith("B:"))
        tc = self.word_time(S.a, S.b, lambda w: w.strip().lower().startswith("yorumlara"))
        ta = (ta - S.start) if ta is not None else dur * 0.2
        tb = (tb - S.start) if tb is not None else max(ta + 0.6, dur * 0.5)
        tc = (tc - S.start) if tc is not None else max(tb + 0.6, dur * 0.78)
        if "soru" in P:
            im, x, y = P["soru"]
            k = ease_pop(lt / 0.25) if lt < 0.25 else 1.0
            K.put(img, im, x, y, k=k, clip=CLIP, anchor=(0.1, 0.5))
        # makas kesmesi: iki yarı birbirine yapışık başlar, makas oluk boyunca indikçe ayrılır
        cut = K.clamp(lt / AB_CUT)
        e = K.ease_in_out(cut)
        for j, (lay, (x, y), _) in enumerate(S.paneller):
            dx = (1 - e) * (GUTTER / 2 + 2) * (1 if j == 0 else -1)
            K.put(img, lay, x + dx, y, clip=CLIP)
        if cut < 1:
            xm = (X0 + X1) / 2
            yy = AB_Y0 - 10 + (AB_Y1 - AB_Y0 + 20) * e
            pen = K.Pen(xm - 40, AB_Y0 - 20, xm + 40, AB_Y1 + 20)
            y = AB_Y0 - 10
            while y < yy:
                pen.rr((xm - 3, y, xm + 3, min(y + 18, yy)), 2, fill=OFF + (255,))
                y += 30
            K.put(img, pen.done(), xm - 40, AB_Y0 - 20, clip=CLIP)
            sc = K.scissors_icon(120, 34 if int(lt * 24) % 2 else 10, blade=OFF, outline=INK, rot=-90)
            K.put(img, sc, xm - sc.width / 2, yy - sc.height * 0.42, clip=CLIP)
        for harf, t0 in (("A", ta), ("B", tb)):
            if lt >= t0:
                im, x, y = P[harf]
                k = ease_pop((lt - t0) / 0.3, 1.25) if lt - t0 < 0.3 else 1.0
                K.put(img, im, x, y, k=k, clip=CLIP)
                im, x, y = P["kart_" + harf.lower()]
                k2 = ease_pop((lt - t0) / 0.3) if lt - t0 < 0.3 else 1.0
                K.put(img, im, x, y, k=k2, clip=CLIP)
        if lt >= tc:
            im, x, y = P["cta"]
            k = ease_pop((lt - tc) / 0.3) if lt - tc < 0.3 else 1.0
            pul = K.cta_pulse(lt - tc) if hasattr(K, "cta_pulse") else 1.0
            K.put(img, im, x, y, k=k * pul, clip=CLIP, anchor=(0.1, 0.5))
        im, x, y = P["alt"]
        a = K.clamp((lt - tc) / 0.3)       # çağrıyla birlikte (çağrıdan önce altında boşluk kalmaz)
        if a > 0:
            K.put(img, im, x, y, alpha=a, clip=CLIP)

    # ------------------------------------------------------------ anlatıcı kutusu
    def anlatici_katmani(self, S: Sahne, pi: int, n: int):
        """Sayfa pi'nin kutusu: genel indeksi n'den küçük kelimeler söylenmiş (mürekkep), diğerleri soluk."""
        key = ("cap", S.i, pi, n)
        if key in self._c:
            return self._c[key]
        A = S.anlatici
        lines = A.pages[pi]
        size = A.size
        lh = size * 1.3
        pad = 28
        ch = cap_h(CAP_FONT, size)
        # kutunun ölçüsü sayfadaki bütün kelimelerle sabit: kelimeler belirdikçe kutu büyümez
        tws = [tw(" ".join(A.texts[i] for i in L), CAP_FONT, size) for L in lines]
        w = min(CAP[2] - CAP[0], max(tws) + 2 * pad + 6)
        h = ch + (len(lines) - 1) * lh + 2 * pad + 8
        base_key = ("capbox", S.i, pi)
        if base_key not in self._c:
            sp = K.Sprite(w, h, margin=24)
            K.torn_paper(sp, 0, 0, w, h, YELLOW, 30 + S.i * 3 + pi, rim=OFF)
            self._c[base_key] = sp
        sp0 = self._c[base_key]
        sp = K.Sprite(w, h, margin=24)
        sp.im = sp0.im.copy()
        from PIL import ImageDraw
        sp.d = ImageDraw.Draw(sp.im)
        y = pad + ch
        sp_w = tw(" ", CAP_FONT, size)
        son = None
        for L in lines:
            x = pad
            for i in L:
                if i < n:
                    son = (x, y, A.texts[i])
                sp.text((x, y), A.texts[i], CAP_FONT, size, INK if i < n else GHOST)
                x += tw(A.texts[i], CAP_FONT, size) + sp_w
            y += lh
        if son is not None:     # en son beliren kelimenin altı kırmızı çizgi (okunan yer)
            x, y, t = son
            sp.line([(x, y + 7), (x + tw(t, CAP_FONT, size), y + 7)], RED + (255,), 4)
        im = sp.render(-0.6, (6, 8, 0, 0.9))
        self._c[key] = (im, w, h)
        return self._c[key]

    def draw_anlatici(self, img: Image.Image, S: Sahne, t: float, lt: float) -> None:
        A = S.anlatici
        if A is None or not A.pages:
            return
        vis = [i for i in A.idx if self.words[i].start <= t + 0.02]
        cur = vis[-1] if vis else A.idx[0]
        pi = A.sayfa_of(cur)
        n = (cur + 1) if vis else -1
        im, w, h = self.anlatici_katmani(S, pi, n)
        k = ease_pop(lt / 0.2, 1.06) if (lt < 0.2 and S.i > 0) else 1.0     # kapakta (t=0) tam görünür
        K.put(img, im, CAP[0] - (im.width - w) / 2, CAP[1] - (im.height - h) / 2, k=k, clip=CLIP, anchor=(0.0, 0.0))

    # ------------------------------------------------------------ maskot, filigran, açılış
    def draw_mascot(self, img: Image.Image, t: float, S: Sahne, lt: float) -> None:
        cx, cy, sc = MASKOT
        if S.tur == "ab":
            cx, cy, sc = AB_MASKOT
            cy = self.ab_parcalar(S)["cta_cy2"]
        mood = {"ipucu": "surprised", "gercek": "surprised"}.get(S.tur, "normal")
        m = (self.scenes[S.i].card or {}).get("mascot", "auto")
        if S.tur == "ab":
            tc = self.word_time(S.a, S.b, lambda w: w.strip().lower().startswith("yorumlara"))
            mood = "happy" if (tc is not None and t >= tc) else "thinking"
        elif S.i == 0:
            mood = "thinking"
        if m in K.MOODS:
            mood = m
        mouth = K.talk_state(self.words, self.starts, t)
        blink = (t % 3.6) > 3.45 and mood not in ("happy", "surprised")
        im = self.mascot.sprite(mood, mouth, blink, None, sc)
        bob = round(3 * math.sin(t * 2 * math.pi * 0.55))
        hop = -18 * math.sin(math.pi * K.clamp(lt / 0.3)) if (S.i > 0 and lt < 0.3) else 0
        ox, oy = Mascot.origin(cx, cy, sc)
        K.put(img, im, ox, oy + bob + hop, clip=CLIP)

    def watermark(self, img: Image.Image, t: float) -> None:
        if not self.brand_on:
            return
        if "wm" not in self._c:
            wm = Image.open(Path(__file__).resolve().parent / "assets" / "brand" / "video_filigran.png").convert("RGBA")
            wm = wm.resize((int(wm.width * WM_OLCEK), int(wm.height * WM_OLCEK)), Image.LANCZOS)
            wm.putalpha(wm.getchannel("A").point(lambda v: int(v * self.wm_alpha)))
            ww, wh = wm.size
            self._c["wm"] = (wm, [(X0, 178), (SAFE[2] - 12 - ww, 178)])
        wm, spots = self._c["wm"]
        intro = 0.8 if self.intro else 0.0
        if t < intro:
            return
        tt = t - intro
        i = int(tt // self.wm_every)
        local = tt - i * self.wm_every
        alpha = min(1.0, local / 0.25, (self.wm_every - local) / 0.25) if i else min(1.0, (self.wm_every - local) / 0.25)
        if alpha <= 0:
            return
        x, y = spots[i % len(spots)]
        K.put(img, wm, x, y, alpha=alpha, clip=CLIP)

    def intro_cut(self, img: Image.Image, t: float, dur: float = 0.8) -> None:
        """Açılış: makas üst bandın altından keser (t=0'da sol başta durur); kesik çizgi sonra söner."""
        if not self.intro or t >= dur + 0.4:
            return
        p = K.clamp(t / dur)
        y = 334
        x = K.lerp(X0, SAFE[2] - 40, K.ease_in_out(p))
        fade = 1.0 if t < dur else 1 - (t - dur) / 0.4
        pen = K.Pen(0, y - 40, SAFE[2], y + 40)
        xx = X0
        while xx < x:
            pen.rr((xx, y - 2, min(xx + 16, x), y + 2), 2, fill=INK + (int(255 * fade),))
            xx += 26
        K.put(img, pen.done(), 0, y - 40, clip=CLIP)
        if p < 1:
            sc = K.scissors_icon(70, 32 if int(t * 24) % 2 else 12, blade=OFF, outline=INK)
            K.put(img, sc, x - 70 * 58 / 124, y - sc.height / 2, clip=CLIP)

    # ------------------------------------------------------------ geçiş
    def final_katman(self, S: Sahne) -> Image.Image:
        """Sahnenin panelleri ve kartı tek katmanda (makas kesmesi için), (0, PANEL_Y0 - 30) kökenli."""
        key = ("final", S.i)
        if key not in self._c:
            y0 = PANEL_Y0 - 30
            lay = Image.new("RGBA", (SAFE[2], KART_Y1 + 40 - y0), (0, 0, 0, 0))
            for im, (x, y), _ in S.paneller:
                K.put(lay, im, x, y - y0, clip=(0, 0, lay.width, lay.height))
            kk = self.kart_katmani(S)
            if kk:
                K.put(lay, kk[0], 0, kk[1] - y0, clip=(0, 0, lay.width, lay.height))
            self._c[key] = lay
        return self._c[key]

    def kes_mi(self, i: int) -> bool:
        return (self.cut_on and i > 0 and i % CUT_EVERY == 0 and self.sahneler[i].tur != "ab")

    # ------------------------------------------------------------ kare
    def frame(self, t: float, grain: bool = True) -> Image.Image:
        si = self.scene_at(t)
        S = self.hazirla(si)
        lt = t - S.start
        img = self.sayfa().copy()
        if S.tur == "ab":
            self.draw_ab(img, S, lt)
        else:
            kes = self.kes_mi(si)
            gecikme = K.CUT_SLICE * 0.9 if kes else 0.0
            for lay, (x, y), t0 in S.paneller:
                p = (lt - gecikme - t0) / ENTRY
                if si == 0 and t0 == 0:
                    p = 1.0                      # kapak karesi (t=0) tam görünür
                if p <= 0:
                    continue
                e = K.ease_out_cubic(K.clamp(p))
                K.put(img, lay, x, y + 26 * (1 - e), alpha=K.clamp(p * 1.6), clip=CLIP)
            for (lay, x, y), t0 in S.sesler:
                tt = lt - gecikme - t0
                if tt > 0:
                    k = ease_pop(tt / 0.3, 1.3) if tt < 0.3 else 1.0
                    K.put(img, lay, x, y, k=k, clip=CLIP)
            if S.balon is not None:
                self.draw_balon(img, S, t, lt)
            kk = self.kart_katmani(S)
            if kk:
                t0 = gecikme + 0.45
                if lt >= t0 or si == 0:
                    k = ease_pop((lt - t0) / 0.3, 1.12) if 0 <= lt - t0 < 0.3 else 1.0
                    K.put(img, kk[0], 0, kk[1], k=k, clip=CLIP, anchor=(0.3, 0.5))
            if kes and lt < K.CUT_LEN:
                old = self.final_katman(self.hazirla(si - 1))
                y0 = PANEL_Y0 - 30
                K.card_cut(img, old, lt, si, origin=(0, y0), card=(X0, PANEL_Y0, X1, PANEL_Y1), x_end=SAFE[2] - 66,
                           clip_top=(0, PANEL_Y0 - 24, SAFE[2], KART_Y1 + 30),
                           clips_bot=((0, PANEL_Y0 - 24, SAFE[2], KART_Y1 + 30),))
            self.draw_anlatici(img, S, t, lt)
        if si == 0:
            self.intro_cut(img, t)
        self.draw_mascot(img, t, S, lt)
        self.watermark(img, t)
        if self.yalniz_icerik:
            return img
        return K.finish(img) if grain else img.convert("RGB")

    def draw_balon(self, img: Image.Image, S: Sahne, t: float, lt: float) -> None:
        B = S.balon
        if S.balon_idx:
            t0 = self.words[S.balon_idx[0]].start
            n = sum(1 for i in S.balon_idx if self.words[i].start <= t + 0.02)
        else:
            t0 = S.start + 0.35
            n = len(B.words)
        if t < t0 - 0.05:
            return
        key = ("balon", S.i, n)
        if key not in self._c:
            x0, y0, x1, y1 = B.kutu
            tip = B.b.uc or (B.b.cx, B.b.cy)
            px0 = min(x0, tip[0]) - 30
            py0 = min(y0, tip[1]) - 30
            px1 = max(x1, tip[0]) + 30
            py1 = max(y1, tip[1]) + 30
            pen = K.Pen(px0, py0, px1, py1)
            B.sekil(pen)
            B.yazi(pen, n)
            self._c[key] = (pen.done(), pen.x0, pen.y0)
        im, x, y = self._c[key]
        k = ease_pop((t - t0 + 0.05) / 0.25, 1.1) if t - t0 + 0.05 < 0.25 else 1.0
        K.put(img, im, x, y, k=k, clip=CLIP)


# son sahnenin ölçüleri
AB_Y0, AB_Y1 = 456, 930
AB_CUT = 0.75
AB_MASKOT = (846, 1290, 0.40)               # y çağrının ikinci satırına göre


# ---------------------------------------------------------------- ana giriş
def render(scenes: list[SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
           music: Path | None, meta: dict) -> Path:
    """Çizgi Roman şablonuyla videoyu kurar (pipeline.build: shortgen/<renderer>.py render). Kare döngüsü, ses,
    kuyruk ve marka kapanışı kart şablonuyla ortak (kart.render_frames)."""
    return K.render_frames(scenes, words, out_mp4, voice_mp3, music,
                           lambda bcfg: CizgiVideo(scenes, words, meta, bcfg), "Cizgi")
