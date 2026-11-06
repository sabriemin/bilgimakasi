"""Mini Belgesel: iki bölümlük belgeselin kurgu modülü, iki görünüm.

Bir üretim iki video verir (pipeline.belgesel_hazirla): bu modül her seferinde TEK bölümü çizer. Bölüm numarası
senaryonun series_part alanından (ya da sahnelerin belgesel.bolum alanından) gelir. Bütün karelerde "BÖLÜM n /2"
etiketi durur; Bölüm 1'in son sahnesi DEVAMI BÖLÜM 2'DE (sıradaki evrelerin/durağın merakıyla), Bölüm 2'nin ilk sahnesi
BÖLÜM 1'DE... özeti ve ŞİMDİ: <evre> geçişidir.

Görünüm (gorunum): şablon dosyasında (templates/belgesel.json "gorunum") "cizgi" ya da "hat" yazılıysa o; değilse
senaryonun belgesel.gorunum alanı (yazar konuya göre seçer); ikisi de yoksa cizgi.

YAŞAM ÇİZGİSİ (cizgi): çizelge kâğıdı zemin; üst sırada BÖLÜM etiketi, seri adı, evre sayacı. Altında 4-6 evrelik
yatay zaman çizgisi (üstte ölçek, altta evre adları ve BÖLÜM 1 | BÖLÜM 2 ayraçları). Sahne evreyi değiştirince kırmızı
dolgu ilerler ve dolgunun ucunda Makas'ın makası kesik çizgiyi keserek yürür. Bölüm 1 sonunda makas çizgiyi iki bölüm
arasından keser; Bölüm 2 açılışında ilk yarı "izlendi" (mürekkep) çizilir. Sahne alanında büyük fotoğraf (künye çipi,
köşede evre etiketi), başlık etiketi ve açıklama ya da sayı / karşılaştırma şeması.

KAN HATTI (hat): koyu noktalı zemin; bilet biçimli BÖLÜM n /2 etiketi, durak sayacı; durak tabelası (B1 kırmızı / B2
sarı hat rozeti, durak adı, sonraki durak). Solda büyük fotoğraf (ya da sayı/karşılaştırma paneli), sağda vücut silueti
üstünde mini hat haritası ve dikey durak şeridi; tren (damla) duraklar arasında yürür. Duraklar senaryodan gelir (hat
güzergâhı siluetin içinde sabit bir yol, duraklar bu yola eşit aralıkla dizilir): kan ve organlar koda yazılı değildir.
Bölüm 1 bir kalkış panosuyla (SONRAKİ DURAK, KALKIŞ BÖLÜM 2) biter.

Ekran: 1080x1920; yazı ve ana öğeler x <= 935, y 170-1540 (K.SAFE); filigran y 120-228'de, üst sıra y >= 240.
Fotoğraf yoksa (açık lisanslı görsel bulunamadı) sahnenin çizimi (illustrate), o da yoksa kodla çizilen yer tutucu
kullanılır. Aynı videonun kareleri her çalıştırmada aynıdır.
"""
from __future__ import annotations

import bisect
import math
import random
import re
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import kart as K
from .render import SceneSpec
from .voice import Word

W, H, FPS, SS = K.W, K.H, K.FPS, K.SS
RED, YELLOW, INK, OFF, DGREY = K.RED, K.YELLOW, K.INK, K.OFF, K.DGREY
blend, tw = K.blend, K.tw
PAPER = (248, 245, 236)                     # marka kâğıdı #F8F5EC
LINE = (205, 199, 186)                      # cizgi: gelecek evrenin soluk çizgisi
SOLUK = (150, 144, 134)
SOFT = (176, 173, 168)                      # hat: koyu zeminde ikincil yazı
BODY = blend(INK, OFF, 0.07)
BODY_LINE = blend(INK, OFF, 0.22)
PANEL = blend(INK, OFF, 0.04)
DIM = 0.32                                  # hat: gidilmemiş hattın opaklığı
SAFE = K.SAFE                               # (0, 170, 935, 1540)
X1 = 920                                    # yazıların sağ sınırı
SERI = "MİNİ BELGESEL"
GORUNUMLER = ("cizgi", "hat")
GIRIS = 0.38                                # sahne içeriğinin giriş süresi (sn)
ILERLE = 0.9                                # zaman çizgisi / tren ilerleme süresi (sn)
MOOD = {"kanca": "surprised", "durak": "normal", "sayi": "surprised", "karsilastirma": "thinking",
        "devam": "thinking", "ozet": "happy", "kapanis": "happy"}
CTA = "YORUMLARA YAZ"


def up(s: str) -> str:
    return K.tr_upper(str(s or ""))


def _seed(*parts) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode("utf-8")) & 0xFFFF


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _sayi(s: str) -> float | None:
    m = re.search(r"\d+(?:[.,]\d+)*", str(s or ""))
    if not m:
        return None
    t = m.group(0)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t.replace(".", "").replace(",", ".") if "," in t else t)
    except ValueError:
        return None


# ---------------------------------------------------------------- küçük çizim yardımcıları
def etiket_im(text, size, fg, bg, seed, rot=0.0, font="anton", shadow=(6, 8, 0, 0.9)) -> Image.Image:
    lab = K.torn_label(text, size, fg, bg, seed, font=font)
    im = lab.render(rot, shadow)
    im.lab_w, im.lab_h = lab.w, lab.h  # type: ignore[attr-defined]
    return im


def etiket_boyu(text: str, max_w: float, size: int, en_kucuk: int, font: str = "anton") -> int:
    """Etiket max_w'ye sığana kadar küçülür (yırtık kâğıdın payı dahil)."""
    while size > en_kucuk and tw(text, font, size) * 1.0 + size * 0.4 > max_w:
        size -= 2
    return size


def yapistir(base: Image.Image, im: Image.Image, cx: float, cy: float, clip=SAFE) -> tuple:
    x, y = cx - im.width / 2, cy - im.height / 2
    K.put(base, im, x, y, clip=clip)
    return (x, y, x + im.width, y + im.height)


def etiket(base, text, size, fg, bg, seed, x, y_top, rot=0.0, font="anton", sag=False, max_w=None,
           en_kucuk=40, shadow=(6, 8, 0, 0.9), kutular=None) -> tuple:
    """Yırtık etiket; sol (sag=True ise sağ) kenarı x, üst kenarı y_top. max_w verilirse sığana kadar küçülür.
    Kâğıdın kutusunu döndürür."""
    if max_w:
        size = etiket_boyu(text, max_w, size, en_kucuk, font)
    im = etiket_im(text, size, fg, bg, seed, rot, font, shadow)
    w, h = im.lab_w, im.lab_h
    cx = x + w / 2 if not sag else x - w / 2
    cy = y_top + h / 2
    yapistir(base, im, cx + shadow[0] / 2, cy + shadow[1] / 2)
    box = (cx - w / 2 - 3, cy - h / 2 - 3, cx + w / 2 + 3 + shadow[0], cy + h / 2 + 3 + shadow[1])
    if kutular is not None:
        kutular.append((f"etiket {text}", box))
    return box


def satirlar(text: str, font: str, size: float, width: float) -> list[str]:
    return [" ".join(L) for L in K.wrap(text, font, size, width)]


def metin_sigdir(text: str, font: str, width: float, max_h: float, size: int, en_kucuk: int,
                 lh: float = 1.28) -> tuple[int, list[str]]:
    """Metin width genişliğe ve max_h yüksekliğe sığana kadar küçülür; en küçükte de sığmazsa satırlar kesilir (…)."""
    while True:
        ls = satirlar(text, font, size, width)
        if size * 0.8 + (len(ls) - 1) * size * lh + size * 0.3 <= max_h or size <= en_kucuk:
            break
        size -= 2
    n = max(1, int((max_h - size * 1.1) // (size * lh)) + 1)
    if len(ls) > n:
        ls = ls[:n]
        ls[-1] = K.fit(ls[-1] + " …", font, size, width)
    return size, ls


def sert_golge(im: Image.Image, dx=10, dy=12, op=0.9, renk=INK) -> Image.Image:
    pad = max(abs(dx), abs(dy)) + 2
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: int(v * op))
    sh = Image.new("RGBA", im.size, renk + (0,))
    sh.putalpha(a)
    out.alpha_composite(sh, (pad + dx, pad + dy))
    out.alpha_composite(im, (pad, pad))
    return out


def yuvarlat(im: Image.Image, r: int) -> Image.Image:
    m = Image.new("L", (im.width * 2, im.height * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, m.width - 1, m.height - 1], r * 2, fill=255)
    out = im.convert("RGBA")
    out.putalpha(m.resize(im.size, Image.LANCZOS))
    return out


def kunye_cipi(base: Image.Image, x: float, y_alt: float, text: str, koyu=True) -> tuple:
    """Fotoğraf köşesindeki künye çipi: kamera simgesi + 'Wikimedia · CC BY-SA 4.0' (images.credit_chip)."""
    size, h = 24, 44
    fg, bg = (OFF, INK) if koyu else (INK, OFF)
    w = tw(text, "courier", size) + 64
    x0, y0 = x, y_alt - h
    pen = K.Pen(x0 - 2, y0 - 2, x0 + w + 2, y0 + h + 2)
    pen.rr((x0, y0, x0 + w, y0 + h), 8, fill=bg + (235,))
    cx, cy = x0 + 26, y0 + h / 2 + 1
    pen.rr((cx - 13, cy - 8, cx + 13, cy + 10), 3, fill=fg)
    pen.rr((cx - 6, cy - 12, cx + 4, cy - 6), 2, fill=fg)
    pen.ell(cx, cy + 1, 6, fill=bg)
    pen.ell(cx, cy + 1, 3, fill=fg)
    pen.text(x0 + 48, y0 + h / 2 + 8, text, "courier", size, fg)
    base.alpha_composite(pen.done(), (int(x0 - 2), int(y0 - 2)))
    return (x0, y0, x0 + w, y0 + h)


def bilgi_yaz(base: Image.Image, x, y, text: str, width: float, max_h: float, renk=INK, size=36,
              en_kucuk=26, kutular=None) -> float:
    """Courier açıklama bloğu; alt kenarı döndürür."""
    if not text.strip():
        return y
    size, ls = metin_sigdir(text, "courier", width, max_h, size, en_kucuk)
    pen = K.Pen(0, 0, W, H)
    lh = size * 1.28
    for i, s in enumerate(ls):
        pen.text(x, y + size * 0.8 + i * lh, s, "courier", size, renk)
    base.alpha_composite(pen.done())
    yb = y + size * 0.8 + (len(ls) - 1) * lh + size * 0.3
    if kutular is not None:
        kutular.append((f"metin {text[:16]}", (x, y, x + max(tw(s, "courier", size) for s in ls), yb)))
    return yb


# ---------------------------------------------------------------- görseller
def foto_yukle(spec: SceneSpec) -> Image.Image | None:
    """Sahnenin fotoğrafı (images.find_any) ya da çizimi (illustrate; şeffaf PNG) RGBA; yoksa None."""
    for p, cizim in ((spec.image, False), (spec.sprite, True)):
        if p is None:
            continue
        try:
            im = Image.open(p)
            im.load()
        except Exception:  # noqa: BLE001
            continue
        im = im.convert("RGBA")
        im.cizim = cizim  # type: ignore[attr-defined]
        return im
    return None


def kapla(src: Image.Image, w: int, h: int, zoom: float = 1.0, koyu: bool = False) -> Image.Image:
    """Fotoğrafı kutuya kırpar (cover; zoom > 1 hafif yakınlaştırma). Çizim (şeffaf) zemine ortalanır."""
    if getattr(src, "cizim", False):
        bg = Image.new("RGBA", (w, h), (blend(INK, OFF, 0.12) if koyu else (236, 230, 216)) + (255,))
        s = min(w * 0.86 / src.width, h * 0.86 / src.height) * zoom
        im = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))), Image.LANCZOS)
        bg.alpha_composite(im, (int((w - im.width) / 2), int((h - im.height) / 2)))
        return bg
    s = max(w / src.width, h / src.height) * zoom
    nw, nh = max(w, int(math.ceil(src.width * s))), max(h, int(math.ceil(src.height * s)))
    im = src.resize((nw, nh), Image.BILINEAR)
    left, top = (nw - w) // 2, int(max(0, min(nh - h, nh * 0.42 - h / 2)))
    return im.crop((left, top, left + w, top + h))


def yer_tutucu(w: int, h: int, ad: str, koyu: bool, renk=RED, seed: int = 1) -> Image.Image:
    """Görsel bulunamazsa kodla çizilen yer tutucu: cizgide yumuşak kâğıt ışığı + büyük evre adı, hatta mikroskop
    hücrelerini andıran diskler + durak adı. Kendi çizimimizdir (lisans sorunu yok)."""
    rng = random.Random(seed)
    if koyu:
        im = Image.new("RGB", (w, h), blend(INK, renk, 0.35))
        d = ImageDraw.Draw(im)
        for y in range(h):
            d.line([(0, y), (w, y)], fill=blend(blend(INK, renk, 0.45), INK, y / h * 0.8))
        im = im.convert("RGBA")
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        for _ in range(22):
            r = rng.uniform(w * 0.05, w * 0.15)
            x, y = rng.uniform(-r, w + r), rng.uniform(-r, h + r)
            c = blend(renk, OFF, rng.uniform(0.0, 0.35))
            dd.ellipse([x - r, y - r * 0.9, x + r, y + r * 0.9], fill=c + (rng.randint(110, 200),))
            dd.ellipse([x - r * 0.45, y - r * 0.4, x + r * 0.45, y + r * 0.4], fill=blend(c, INK, 0.35) + (160,))
        im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(3)))
        fg = OFF
    else:
        im = Image.new("RGB", (w, h), (226, 214, 194))
        d = ImageDraw.Draw(im)
        for y in range(h):
            d.line([(0, y), (w, y)], fill=blend((232, 222, 204), (184, 168, 146), (y / h) ** 1.4))
        im = im.convert("RGBA")
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        for _ in range(12):
            r = rng.uniform(w * 0.03, w * 0.09)
            x, y = rng.uniform(0, w), rng.uniform(0, h * 0.6)
            dd.ellipse([x - r, y - r, x + r, y + r], fill=(255, 244, 220, rng.randint(50, 100)))
        im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(w * 0.02)))
        fg = INK
    pen = K.Pen(0, 0, w, h)
    ad = up(ad) or "?"
    size = etiket_boyu(ad, w * 0.8, int(h * 0.3), 30)
    pen.text(w / 2, h / 2 + size * 0.35, ad, "anton", size, fg + (70,), anchor="ms")
    im.alpha_composite(pen.done())
    return im


def karart(im: Image.Image, k: float = 0.5) -> Image.Image:
    out = im.copy()
    veil = Image.new("RGBA", im.size, INK + (int(255 * k),))
    out.alpha_composite(veil)
    a = im.getchannel("A")
    out.putalpha(a)
    return out


def gri(im: Image.Image) -> Image.Image:
    g = ImageOps.grayscale(im.convert("RGB")).convert("RGBA")
    g.putalpha(im.getchannel("A"))
    return g


# ---------------------------------------------------------------- Makas
class Makas:
    """Konuşurken ağzı açılıp kapanan Makas (kart.mascot_svg); görüntüler ölçek/ifade/ağız başına bir kez çizilir."""

    def __init__(self):
        self._c: dict = {}

    def ciz(self, img: Image.Image, cx: float, cy: float, k: float, mood: str, mouth: str, blink: bool) -> None:
        key = (round(k, 3), mood, mouth, blink)
        if key not in self._c:
            vb = K.MASCOT_VB
            im = K.svg_img(K.mascot_svg(mood, mouth, blink), vb, vb[2] * k * SS, vb[3] * k * SS)
            self._c[key] = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
        im = self._c[key]
        vb = K.MASCOT_VB
        K.put(img, im, cx + vb[0] * k, cy + (vb[1] - 60) * k)

    @staticmethod
    def kutu(cx, cy, k) -> tuple:
        return (cx - 160 * k, cy - 330 * k, cx + 160 * k, cy + 125 * k)


# ---------------------------------------------------------------- senaryo okuma
def _bb(meta: dict) -> dict:
    sc = (meta or {}).get("script") or {}
    bb = sc.get("belgesel") or (meta or {}).get("belgesel") or {}
    return dict(bb) if isinstance(bb, dict) else {}


def gorunum_sec(meta: dict) -> str:
    """Şablondaki 'gorunum' (cizgi | hat) önce; yoksa senaryonun belgesel.gorunum alanı; yoksa cizgi."""
    s = str(((meta or {}).get("sablon") or {}).get("gorunum") or "").strip()
    if s in GORUNUMLER:
        return s
    g = str(_bb(meta).get("gorunum") or "").strip()
    return g if g in GORUNUMLER else "cizgi"


class Sahne:
    """Çizicinin bir sahne için okuduğu her şey (sahnenin belgesel alanı + görsel + künye)."""

    def __init__(self, spec: SceneSpec, i: int, n: int, n_durak: int, bolum: int, b1_son: int):
        c = spec.card if isinstance(spec.card, dict) else {}
        b = c.get("belgesel") or {}
        self.spec, self.i = spec, i
        varsayilan = ("kanca" if bolum == 1 else "ozet") if i == 0 else (
            ("devam" if bolum == 1 else "kapanis") if i == n - 1 else "durak")
        self.tur = str(b.get("tur") or varsayilan)
        if self.tur not in MOOD:
            self.tur = varsayilan
        aralik = (0, b1_son) if bolum == 1 else (b1_son + 1, n_durak - 1)
        d = b.get("durak")
        if not isinstance(d, int):
            d = aralik[0] + round((aralik[1] - aralik[0]) * i / max(1, n - 1))
        self.durak = min(max(0, d), max(0, n_durak - 1))
        self.baslik = up(str(b.get("baslik") or ""))
        self.metin = " ".join(str(b.get("metin") or "").split())
        self.foto_etiketi = up(str(b.get("foto_etiketi") or ""))
        self.sayi = up(str(b.get("sayi") or ""))
        self.sayi_etiketi = up(str(b.get("sayi_etiketi") or ""))
        self.kalemler = [" ".join(str(x).split()) for x in (b.get("kalemler") or []) if str(x).strip()]
        mascot = str(c.get("mascot") or "auto")
        self.mood = mascot if mascot in ("normal", "surprised", "thinking", "happy") else MOOD[self.tur]
        self.credit = K.credit_chip(c.get("credit") or {}) if c.get("credit") else ""
        self.start, self.end = spec.start, spec.end
        self.words = spec.words
        if not self.metin and self.tur in ("durak", "sayi", "karsilastirma", "kanca"):
            ilk = re.split(r"(?<=[.!?])\s+", spec.narration.strip())[0] if spec.narration.strip() else ""
            self.metin = ilk if len(ilk.split()) <= 16 else " ".join(ilk.split()[:15]) + "…"

    def kelime_ani(self, pattern: str) -> float | None:
        for w in self.words:
            if re.match(pattern, K.tr_lower(w.text.strip("\"'“”‘’(«"))):
                return w.start
        return None


# ---------------------------------------------------------------- video
class BelgeselVideo:
    def __init__(self, scenes: list[SceneSpec], words: list[Word], meta: dict, bcfg: dict):
        from .brand import Brand
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        bb = _bb(self.meta)
        self.gorunum = gorunum_sec(self.meta)
        self.koyu = self.gorunum == "hat"
        duraklar = bb.get("duraklar") or []
        self.duraklar = [(up(str(d.get("ad") or "")) if isinstance(d, dict) else up(str(d)),
                          str(d.get("ust") or "") if isinstance(d, dict) else "") for d in duraklar]
        if len(self.duraklar) < 2:  # alan yoksa sahne sayısından türet (bozuk senaryo da çizilsin)
            self.duraklar = [(f"EVRE {i + 1}", "") for i in range(4)]
        self.n = len(self.duraklar)
        self.b1_son = min(max(0, int(bb.get("bolum1_son") or (self.n // 2 - 1))), self.n - 2)
        sp = int(((self.meta.get("script") or {}).get("series_part")) or 0)
        if sp not in (1, 2):
            bols = [((s.card or {}).get("belgesel") or {}).get("bolum") for s in scenes]
            sp = 2 if bols and all(x == 2 for x in bols) else 1
        self.bolum = sp
        self.baslik = [up(x) for x in (bb.get("baslik") or []) if str(x).strip()][:2] or \
            [up(w) for w in (scenes[0].headline if scenes else [])][:2] or [up(self.meta.get("topic", ""))]
        self.alt = str(bb.get("alt_baslik") or (self.meta.get("topic") or ""))[:30]
        self.sahneler = [Sahne(s, i, len(scenes), self.n, self.bolum, self.b1_son) for i, s in enumerate(scenes)]
        self.starts = [s.start for s in scenes]
        self.wstarts = [w.start for w in words]
        on = bool(bcfg.get("enabled", False))
        self.brand = Brand(bcfg, {}) if on else None
        self.intro = bool(on and bcfg.get("intro_cut", True))
        self.makas = Makas()
        self._c: dict = {}
        self._foto: dict = {}
        self.kutular: list[tuple[str, tuple]] = []      # son çizilen içerik katmanlarının yazı kutuları (denetim)
        self._ilerleme_plani()

    # ------------------------------------------------------------ zaman
    def seg_at(self, t: float) -> int:
        return max(0, min(len(self.scenes) - 1, bisect.bisect_right(self.starts, t) - 1))

    def _ilerleme_plani(self):
        """Her sahnenin başında ve sonunda dolgunun / trenin konumu (durak birimi)."""
        prev = 0.0 if self.bolum == 1 else float(self.b1_son)
        self.ilerleme: list[tuple[float, float, float]] = []   # (başlangıç konumu, hedef, ilerlemenin başladığı an)
        for s in self.sahneler:
            hedef = float(s.durak)
            if s.tur == "kanca":
                hedef = 0.0
            elif s.tur == "ozet":
                hedef = float(max(s.durak, self.b1_son + 1))
            elif s.tur == "devam":
                hedef = float(self.b1_son)
            elif s.tur == "kapanis":
                hedef = float(self.n - 1)
            t0 = s.start + 0.15
            if s.tur == "ozet":
                an = s.kelime_ani(r"şimdi")
                t0 = an if an is not None else s.start + (s.end - s.start) * 0.6
            self.ilerleme.append((prev, hedef, t0))
            prev = hedef

    def konum(self, si: int, t: float) -> float:
        a, b, t0 = self.ilerleme[si]
        if b == a:
            return b
        return a + (b - a) * _ease((t - t0) / ILERLE)

    def kesik_ani(self, s: Sahne) -> float:
        an = s.kelime_ani(r"devam")
        return an if an is not None else s.start + (s.end - s.start) * 0.55

    # ------------------------------------------------------------ zemin
    def zemin(self) -> Image.Image:
        if "zemin" not in self._c:
            if self.koyu:
                im = Image.new("RGBA", (W, H), INK + (255,))
                d = ImageDraw.Draw(im)
                c = blend(INK, OFF, 0.07)
                for y in range(0, H, 36):
                    for x in range(0, W, 36):
                        d.ellipse([x - 1.6, y - 1.6, x + 1.6, y + 1.6], fill=c)
            else:
                im = Image.new("RGBA", (W, H), PAPER + (255,))
                d = ImageDraw.Draw(im)
                c1, c2 = blend(PAPER, INK, 0.035), blend(PAPER, INK, 0.07)
                for x in range(0, W, 27):
                    d.line([(x, 0), (x, H)], fill=c2 if (x // 27) % 5 == 0 else c1, width=1)
                for y in range(0, H, 27):
                    d.line([(0, y), (W, y)], fill=c2 if (y // 27) % 5 == 0 else c1, width=1)
            self._c["zemin"] = im
        return self._c["zemin"]

    # ------------------------------------------------------------ üst sıra (her karede: BÖLÜM n /2)
    def ust_sira(self, sayac: str | None) -> Image.Image:
        key = ("ust", sayac)
        if key not in self._c:
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            if self.koyu:
                b = self.bilet(img, 72, 240)
                fg, fg2 = OFF, SOFT
                ust, alt = 274, 304
            else:
                b = etiket(img, f"BÖLÜM {self.bolum}", 54, OFF, RED, 10 + self.bolum, 70, 246, rot=-1.5)
                pen = K.Pen(0, 0, W, H)
                pen.text(b[2] + 26, 294, "/2", "anton", 44, INK)
                img.alpha_composite(pen.done())
                b = (b[0], b[1], b[2] + 26 + tw("/2", "anton", 44), b[3])
                fg, fg2 = INK, DGREY
                ust, alt = 277, 305
            pen = K.Pen(0, 0, W, H)
            x = b[2] + 24
            sag = X1
            if sayac:
                sw = tw(sayac, "courier", 28) + 30
                pen.rr((X1 - sw, 256, X1, 302), 23, fill=OFF if self.koyu else INK)
                pen.text(X1 - sw / 2, 288, sayac, "courier", 28, INK if self.koyu else YELLOW, anchor="ms")
                sag = X1 - sw - 16
            alt_yazi = K.fit(self.alt, "courier", 24, max(60, sag - x))
            seri = K.fit(SERI, "courier", 26, max(60, sag - x))
            pen.text(x, ust, seri, "courier", 26, fg)
            pen.text(x, alt, alt_yazi, "courier", 24, fg2)
            img.alpha_composite(pen.done())
            self._c[key] = img
        return self._c[key]

    def bilet(self, img, x, y) -> tuple:
        """KAN HATTI'nın bölüm etiketi: metro bileti (yan çentikli, delikli çizgili): B1 rozeti, BÖLÜM 1, /2."""
        bolum = self.bolum
        bw, bh = 330, 74
        sp = K.Sprite(bw, bh, margin=24)
        col = YELLOW if bolum == 1 else OFF
        sp.polygon([(0, 0), (bw, 0), (bw, bh), (0, bh)], col + (255,))
        sp.d.ellipse([*sp.p(-11, bh / 2 - 11), *sp.p(11, bh / 2 + 11)], fill=(0, 0, 0, 0))
        sp.d.ellipse([*sp.p(bw - 11, bh / 2 - 11), *sp.p(bw + 11, bh / 2 + 11)], fill=(0, 0, 0, 0))
        rc = RED if bolum == 1 else YELLOW
        sp.dot(46, bh / 2, 25, INK + (255,))
        sp.dot(46, bh / 2, 21, rc + (255,))
        sp.text((46, bh / 2 + 10), f"B{bolum}", "anton", 28, OFF if bolum == 1 else INK, anchor="ms")
        sp.text((86, bh / 2 + 17), f"BÖLÜM {bolum}", "anton", 48, INK)
        yy = 4
        while yy < bh - 4:
            sp.line([(268, yy), (268, yy + 6)], INK + (255,), 2.5)
            yy += 12
        sp.text((296, bh / 2 + 15), "/2", "anton", 40, INK, anchor="ms")
        im = sp.render(-2.0 if bolum == 1 else 1.5, (6, 8, 0, 0.9))
        yapistir(img, im, x + bw / 2 + 3, y + bh / 2 + 4)
        return (x, y, x + bw, y + bh)

    def sayac(self, s: Sahne) -> str | None:
        if s.tur == "kanca":
            return None
        return f"{'DURAK' if self.koyu else 'EVRE'} {s.durak + 1}/{self.n}"

    # ============================================================ YAŞAM ÇİZGİSİ
    TL_Y = 432
    NX0, NX1 = 118, 872

    def nx(self, i: float) -> float:
        return self.NX0 + (self.NX1 - self.NX0) * i / max(1, self.n - 1)

    def cut_x(self) -> float:
        return (self.nx(self.b1_son) + self.nx(self.b1_son + 1)) / 2

    def zaman_cizgisi(self, aktif: float, kesik: bool, ozet: bool) -> Image.Image:
        key = ("tl", round(aktif, 2), kesik, ozet)
        if key in self._c:
            return self._c[key]
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pen = K.Pen(0, 0, W, H)
        y, xa, cx = self.TL_Y, self.nx(aktif), self.cut_x()
        aralik = (self.NX1 - self.NX0) / max(1, self.n - 1)
        ad_boy = 32
        for ad, _ in self.duraklar:
            ad_boy = min(ad_boy, etiket_boyu(ad, aralik - 6, 32, 20))
        for i, (_, ust) in enumerate(self.duraklar):
            pen.line([(self.nx(i), y - 30), (self.nx(i), y - 20)], INK, 3)
            if ust:
                pen.text(self.nx(i), y - 40, K.fit(ust, "courier", 24, aralik - 8), "courier", 24, DGREY, anchor="ms")
        for k in range(26):
            x = self.NX0 + (self.NX1 - self.NX0) * k / 25
            pen.line([(x, y - 22), (x, y - 16)], SOLUK, 2)
        x = self.NX0
        while x < self.NX1:
            e = min(x + 14, self.NX1)
            if not (kesik and cx - 16 < x < cx + 16):
                pen.line([(x, y), (e, y)], LINE, 8)
            x += 24
        if ozet:
            pen.line([(self.NX0, y), (min(xa, self.nx(self.b1_son)), y)], INK, 12)
            if xa > self.nx(self.b1_son):
                pen.line([(self.nx(self.b1_son), y), (xa, y)], RED, 12)
        elif aktif > 0:
            end = min(xa, cx - 18) if kesik else xa
            pen.line([(self.NX0, y), (end, y)], RED, 12)
        for i, (ad, _) in enumerate(self.duraklar):
            x = self.nx(i)
            gecti = i < aktif - 0.01
            simdi = abs(i - aktif) < 0.01
            b2 = i > self.b1_son
            if simdi:
                pen.ell(x + 4, y + 5, 26, fill=INK)
                pen.ell(x, y, 26, fill=YELLOW, outline=INK, width=6)
                pen.ell(x, y, 9, fill=INK)
            elif gecti:
                col = INK if (ozet and i <= self.b1_son) else RED
                pen.ell(x, y, 19, fill=col, outline=INK, width=5)
                pen.svg(K.check_svg(OFF, 18), K.ICON_VB, x - 12, y - 12, 24)
            else:
                pen.ell(x, y, 17, fill=PAPER, outline=SOLUK if (kesik and b2) else INK, width=5)
            col = RED if simdi else (INK if gecti else (SOLUK if (kesik and b2) else DGREY))
            pen.text(x, y + 66, ad, "anton", ad_boy, col, anchor="ms")
        for b, (i0, i1) in enumerate(((0, self.b1_son), (self.b1_son + 1, self.n - 1)), start=1):
            x0, x1 = max(self.nx(i0) - 46, 72), min(self.nx(i1) + 46, 918)
            on = b == self.bolum
            col = RED if on else SOLUK
            yb = y + 88
            pen.line([(x0, yb - 8), (x0, yb), (x1, yb), (x1, yb - 8)], col, 4, joint=None)
            lab = f"BÖLÜM {b}"
            lw = tw(lab, "courier", 24) + 22
            c = (x0 + x1) / 2
            pen.rr((c - lw / 2, yb - 4, c + lw / 2, yb + 30), 6, fill=col if on else PAPER, outline=col, width=3)
            pen.text(c, yb + 21, lab, "courier", 24, OFF if on else col, anchor="ms")
        img.alpha_composite(pen.done())
        if len(self._c) > 400:
            for k in [k for k in self._c if isinstance(k, tuple) and k[0] == "tl"][:200]:
                del self._c[k]
        self._c[key] = img
        return img

    def makas_ucta(self, img: Image.Image, x: float, t: float, kesiyor: bool) -> None:
        """Dolgunun ucunda yürüyen makas (bıçakları açılıp kapanır); kesiyorsa dik durur."""
        acik = 34 if int(t * 14) % 2 else 10
        if kesiyor:
            sc = K.scissors_icon(96, acik, blade=INK, ring=RED, pivot=YELLOW, outline=INK, rot=-90)
            yapistir(img, sc, x, self.TL_Y + 4)
        else:
            sc = K.scissors_icon(74, acik, blade=INK, ring=RED, pivot=YELLOW, outline=INK)
            yapistir(img, sc, x + 6, self.TL_Y)

    def foto(self, s: Sahne, w: int, h: int, zoom: float) -> Image.Image:
        key = (s.i, w, h)
        if key not in self._foto:
            src = foto_yukle(s.spec)
            ad = self.duraklar[s.durak][0]
            self._foto[key] = src if src is not None else None
            if src is None:
                renk = RED if s.durak <= self.b1_son else YELLOW
                self._foto[key] = yer_tutucu(int(w * 1.06), int(h * 1.06), ad, self.koyu, renk, seed=s.i + 3)
                self._foto[key].cizim = False  # type: ignore[attr-defined]
        return kapla(self._foto[key], w, h, zoom, self.koyu)

    def cerceve(self, img: Image.Image, box) -> None:
        x0, y0, x1, y1 = box
        pen = K.Pen(x0 - 10, y0 - 10, x1 + 22, y1 + 22)
        if self.koyu:
            pen.rr((x0 + 10, y0 + 12, x1 + 10, y1 + 12), 14, fill=(0, 0, 0))
            pen.rr((x0 - 5, y0 - 5, x1 + 5, y1 + 5), 16, fill=OFF)
        else:
            pen.rr((x0 + 12, y0 + 14, x1 + 12, y1 + 14), 10, fill=INK)
            pen.rr((x0 - 6, y0 - 6, x1 + 6, y1 + 6), 12, fill=INK)
        img.alpha_composite(pen.done(), (int(x0 - 10), int(y0 - 10)))

    # ------------------------------------------------------------ içerik katmanları (sahne başına bir kez)
    def icerik(self, si: int) -> dict:
        """{'alt': çerçeve/gölge katmanı, 'foto': (kutu) ya da None, 'ust': yazı ve etiket katmanı, 'makas': (cx, cy,
        k), 'kutular': [...], 'cta': (cx, cy) ya da None}"""
        key = ("icerik", si)
        if key not in self._c:
            s = self.sahneler[si]
            alt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ust = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = {"alt": alt, "ust": ust, "foto": None, "makas": (818, 1420, 0.42), "kutular": [], "cta": None}
            (self.hat_icerik if self.koyu else self.cizgi_icerik)(s, d)
            self._c[key] = d
        return self._c[key]

    def cizgi_icerik(self, s: Sahne, d: dict) -> None:
        alt, ust, kt = d["alt"], d["ust"], d["kutular"]
        tur = s.tur
        if tur == "kanca":
            b1 = etiket(ust, self.baslik[0], 118, INK, OFF, 31, 66, 584, rot=-1.4, max_w=850, en_kucuk=60, kutular=kt)
            b2 = b1
            if len(self.baslik) > 1:
                b2 = etiket(ust, self.baslik[1], 150, OFF, RED, 32, 110, b1[3] + 4, rot=1.6, max_w=800, en_kucuk=70,
                            kutular=kt)
            fb = (84, b2[3] + 46, 600, 1500)
            if fb[3] - fb[1] < 360:
                fb = (84, b2[3] + 46, 600, b2[3] + 46 + 360)
            self.cerceve(alt, fb)
            d["foto"] = fb
            self._foto_ustu(ust, s, fb, kt)
            bilgi_yaz(ust, 632, fb[1] + 40, s.metin, 286, max(120, 1500 - 420 - fb[1] - 40), INK, 38, 26, kt)
            d["makas"] = (784, 1390, 0.5)
        elif tur == "durak":
            fb = (84, 590, 916, 1150)
            self.cerceve(alt, fb)
            d["foto"] = fb
            self._foto_ustu(ust, s, fb, kt)
            y = 1196
            if s.baslik:
                b = etiket(ust, s.baslik, 92, YELLOW, INK, 41 + s.i, 70, y, rot=-1.2, max_w=840, en_kucuk=54, kutular=kt)
                y = b[3] + 18
            bilgi_yaz(ust, 76, y, s.metin, 640, 1530 - y, INK, 36, 26, kt)
            d["makas"] = (818, 1420, 0.42)
        elif tur in ("sayi", "karsilastirma"):
            y = 596
            if s.baslik:
                b = etiket(ust, s.baslik, 96, OFF, INK, 51 + s.i, 70, y, rot=-1.2, max_w=840, en_kucuk=54, kutular=kt)
                y = b[3] + 40
            if tur == "sayi":
                y = self.sayi_karti(alt, ust, s, (84, y, 916, min(y + 520, 1240)), kt) + 34
            else:
                y = self.cubuklar(ust, s, (84, y, 916, min(y + 520, 1240)), kt) + 34
            bilgi_yaz(ust, 76, y, s.metin, 640, 1530 - y, INK, 34, 26, kt)
            d["makas"] = (818, 1430, 0.40)
        elif tur == "devam":
            b1 = etiket(ust, "DEVAMI", 120, INK, OFF, 61, 70, 596, rot=-1.5, kutular=kt)
            b2 = etiket(ust, "BÖLÜM 2'DE", 150, OFF, RED, 62, 120, b1[3] + 2, rot=1.4, kutular=kt)
            fb = (84, b2[3] + 58, 560, 1500)
            self.cerceve(alt, fb)
            d["foto"] = fb
            d["foto_karart"] = True
            etiket(ust, "?", 110, INK, YELLOW, 66, fb[2] + 10, fb[1] - 40, rot=6, sag=True, kutular=kt)
            x, yy = 600, fb[1] + 40
            pen = K.Pen(0, 0, W, H)
            pen.text(x, yy + 30, "SIRADA:", "anton", 44, RED)
            sira = s.kalemler or [a for a, _ in self.duraklar[self.b1_son + 1:]]
            yb = yy + 62
            ust.alpha_composite(pen.done())
            for k_, kal in enumerate(sira[:3]):
                yb = bilgi_yaz(ust, x, yb, kal + ("," if k_ < len(sira[:3]) - 1 else "."), X1 - x, 110, INK, 36, 24,
                               kt) + 12
            d["makas"] = (805, 1452, 0.42)
        elif tur == "ozet":
            b = etiket(ust, "BÖLÜM 1'DE...", 100, OFF, INK, 71, 70, 596, rot=-1.3, kutular=kt)
            y = self.notlar(ust, s, b[3] + 40, 72, X1, kt, koyu=False)
            self.simdi(ust, s, max(y + 30, 1170), kt)
            d["makas"] = (820, 1438, 0.38)
        else:  # kapanis
            y = 596
            for k_, satir in enumerate(self._soru_satirlari(s.baslik or "SEN NE DÜŞÜNÜYORSUN?")):
                b = etiket(ust, satir, 100 if k_ == 0 else 110, OFF if k_ == 0 else INK, INK if k_ == 0 else YELLOW,
                           81 + k_, 70 + 30 * k_, y, rot=(-1.4, 1.2)[k_ % 2], max_w=840 - 30 * k_, en_kucuk=56,
                           kutular=kt)
                y = b[3] + 6
            fb = None
            if foto_yukle(s.spec) is not None:
                fb = (84, y + 40, 560, min(y + 40 + 420, 1210))
                self.cerceve(alt, fb)
                d["foto"] = fb
                self._foto_ustu(ust, s, fb, kt, etiket_yok=True)
                y = fb[3] + 14
            bilgi_yaz(ust, 76, y + 30, s.metin, 640, max(60, 1300 - y - 30), INK, 34, 26, kt)
            d["cta"] = (420, 1430)
            d["makas"] = (812, 1400, 0.44)

    def _soru_satirlari(self, soru: str) -> list[str]:
        k = soru.split()
        if tw(soru, "anton", 100) + 40 <= 840 or len(k) < 2:
            return [soru]
        en_iyi = min(range(1, len(k)), key=lambda i: abs(tw(" ".join(k[:i]), "anton", 100) -
                                                       tw(" ".join(k[i:]), "anton", 100)))
        return [" ".join(k[:en_iyi]), " ".join(k[en_iyi:])]

    def _foto_ustu(self, ust: Image.Image, s: Sahne, fb, kt, etiket_yok=False) -> None:
        x0, y0, x1, y1 = fb
        if s.credit:
            kt.append(("künye", kunye_cipi(ust, x0 + 14, y1 - 14, s.credit)))
        if s.foto_etiketi and not etiket_yok:
            if self.koyu:
                etiket(ust, s.foto_etiketi, 40, INK, YELLOW, 31 + s.i, x1 - 12, y0 - 24, rot=3, sag=True,
                       max_w=x1 - x0 - 40, en_kucuk=28, kutular=kt)
            else:
                etiket(ust, s.foto_etiketi, 46, INK, YELLOW, 70 + s.i, x1 - 12, y0 - 26, rot=3, sag=True,
                       max_w=x1 - x0 - 40, en_kucuk=30, kutular=kt)

    def sayi_karti(self, alt, ust, s: Sahne, box, kt) -> float:
        x0, y0, x1, y1 = box
        h = min(y1 - y0, 420)
        y1 = y0 + h
        pen = K.Pen(0, 0, W, H)
        if self.koyu:
            pen.rr((x0, y0, x1, y1), 16, fill=PANEL, outline=BODY_LINE, width=3)
            fg, fg2 = YELLOW, OFF
        else:
            pen.rr((x0 + 12, y0 + 14, x1 + 12, y1 + 14), 16, fill=INK)
            pen.rr((x0, y0, x1, y1), 16, fill=OFF, outline=INK, width=5)
            fg, fg2 = RED, INK
        sayi = s.sayi or "?"
        size = 260
        while size > 80 and tw(sayi, "anton", size) > (x1 - x0) - 70:
            size -= 6
        pen.text((x0 + x1) / 2, y0 + 40 + size * 0.86, sayi, "anton", size, fg, anchor="ms")
        if s.sayi_etiketi:
            es = etiket_boyu(s.sayi_etiketi, x1 - x0 - 60, 48, 28)
            pen.text((x0 + x1) / 2, y1 - 40, s.sayi_etiketi, "anton", es, fg2, anchor="ms")
        ust.alpha_composite(pen.done())
        kt.append(("sayı kartı", (x0, y0, x1 + 12, y1 + 14)))
        return y1 + 14

    def cubuklar(self, ust, s: Sahne, box, kt) -> float:
        """karsilastirma: iki değerin yatay çubukları (uzunluk değerle orantılı)."""
        x0, y0, x1, y1 = box
        satir = []
        for k in s.kalemler[:2]:
            a, _, v = k.partition("|")
            satir.append((up(a.strip()), v.strip(), _sayi(v) or 0.0))
        if not satir:
            satir = [(s.sayi_etiketi or "?", s.sayi or "", 1.0)]
        mx = max(v for _, _, v in satir) or 1.0
        pen = K.Pen(0, 0, W, H)
        renkler = (RED, YELLOW)
        y = y0
        boy_max = 56
        # çubuk kalınlığı kutuya göre: iki satır kutuyu doldurur (100–150 px)
        bh = max(100.0, min(150.0, (y1 - y0) / len(satir) - boy_max - 58))
        for i, (ad, deger, v) in enumerate(satir):
            boy = etiket_boyu(ad, x1 - x0, boy_max, 26)
            pen.text(x0, y + boy, ad, "anton", boy, OFF if self.koyu else INK)
            yb = y + boy + 18
            bw = max(40.0, (x1 - x0 - 10) * (v / mx))
            if not self.koyu:
                pen.rr((x0 + 8, yb + 10, x0 + bw + 8, yb + bh + 10), 10, fill=INK)
            pen.rr((x0, yb, x0 + bw, yb + bh), 10, fill=renkler[i % 2], outline=INK if not self.koyu else None,
                   width=4 if not self.koyu else 0)
            ds = etiket_boyu(deger, max(80, bw - 30), int(bh * 0.66), 34)
            if tw(deger, "anton", ds) + 40 <= bw:
                pen.text(x0 + 20, yb + bh / 2 + ds * 0.36, deger, "anton", ds, OFF if i % 2 == 0 else INK)
            else:
                ds = 72 if bw < x1 - x0 - 200 else 48
                pen.text(x0 + bw + 18, yb + bh / 2 + ds * 0.36, deger, "anton", ds, OFF if self.koyu else INK)
            y = yb + bh + 40
        ust.alpha_composite(pen.done())
        kt.append(("çubuklar", (x0, y0, x1 + 8, y - 40 + 10)))
        return y - 30

    def notlar(self, ust, s: Sahne, y0: float, x0: float, x1: float, kt, koyu: bool) -> float:
        """BÖLÜM 1'DE... maddeleri: numaralı, tikli not kartları."""
        kalem = s.kalemler[:3] or [a for a, _ in self.duraklar[:self.b1_son + 1]][:3]
        y = y0
        for i, k_ in enumerate(kalem):
            size, ls = metin_sigdir(k_, "courier", x1 - x0 - 140, 100, 32, 24)
            h = max(110, size * 0.8 + (len(ls) - 1) * size * 1.28 + size * 0.3 + 44)
            pen = K.Pen(0, 0, W, H)
            pen.rr((x0 + 8, y + 10, x1 + 8, y + h + 10), 12, fill=(0, 0, 0) if koyu else INK)
            pen.rr((x0, y, x1, y + h), 12, fill=OFF, outline=None if koyu else INK, width=0 if koyu else 4)
            pen.ell(x0 + 44, y + 50, 26, fill=RED)
            pen.text(x0 + 44, y + 63, str(i + 1), "anton", 34, OFF, anchor="ms")
            for j, sat in enumerate(ls):
                pen.text(x0 + 88, y + 22 + size * 0.8 + j * size * 1.28, sat, "courier", size, INK)
            pen.svg(K.check_svg(RED, 16), K.ICON_VB, x1 - 58, y + h - 52, 40)
            ust.alpha_composite(pen.done())
            kt.append((f"not {i + 1}", (x0, y, x1 + 8, y + h + 10)))
            y += h + 26
        return y

    def simdi(self, ust, s: Sahne, y: float, kt) -> float:
        ad = self.duraklar[max(s.durak, self.b1_son + 1)][0]
        pen = K.Pen(0, 0, W, H)
        pen.text(76, y + 44, "ŞİMDİ:", "anton", 52, YELLOW if self.koyu else RED)
        ust.alpha_composite(pen.done())
        kt.append(("şimdi", (76, y, 76 + tw("ŞİMDİ:", "anton", 52), y + 56)))
        if self.koyu:
            return self.tabela(ust, ad, 2, self.sonraki(max(s.durak, self.b1_son + 1)), y + 70, kt)
        b = etiket(ust, ad, 104, YELLOW, INK, 90, 76, y + 70, rot=-1.4, max_w=840, en_kucuk=56, kutular=kt)
        return b[3]

    # ============================================================ KAN HATTI
    VB = (0, 0, 300, 420)
    ROTA = [(186, 150), (120, 150), (86, 184), (86, 262), (118, 294), (184, 294), (212, 322), (212, 360), (184, 388),
            (120, 388)]
    SILUET = [(132, 92), (168, 92), (171, 116), (232, 130), (254, 150), (276, 330), (248, 337), (224, 186), (214, 330),
              (220, 420), (80, 420), (86, 330), (76, 186), (52, 337), (24, 330), (46, 150), (68, 130), (129, 116)]

    def _rota_uzunluk(self) -> list[float]:
        if "rota" not in self._c:
            acc = [0.0]
            for a, b in zip(self.ROTA, self.ROTA[1:]):
                acc.append(acc[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
            self._c["rota"] = acc
        return self._c["rota"]

    def rota_noktasi(self, f: float) -> tuple[float, float]:
        """Rotanın f oranındaki noktası (0..1)."""
        acc = self._rota_uzunluk()
        L = acc[-1] * min(1.0, max(0.0, f))
        i = max(0, min(len(acc) - 2, bisect.bisect_right(acc, L) - 1))
        a, b = self.ROTA[i], self.ROTA[i + 1]
        s = acc[i + 1] - acc[i]
        k = (L - acc[i]) / s if s else 0
        return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)

    def rota_parca(self, f0: float, f1: float) -> list[tuple[float, float]]:
        acc = self._rota_uzunluk()
        L0, L1 = acc[-1] * f0, acc[-1] * f1
        pts = [self.rota_noktasi(f0)]
        for i, L in enumerate(acc):
            if L0 < L < L1:
                pts.append(self.ROTA[i])
        pts.append(self.rota_noktasi(f1))
        return pts

    def durak_f(self, i: float) -> float:
        return i / max(1, self.n - 1)

    def harita(self, img, box, ilerleme: float, etiketler=True, tam=False, ozet=False, olcek_yazi=1.0, kt=None):
        x0, y0, x1, y1 = box
        s = min((x1 - x0) / self.VB[2], (y1 - y0) / self.VB[3])
        ox = x0 + ((x1 - x0) - self.VB[2] * s) / 2
        oy = y0 + ((y1 - y0) - self.VB[3] * s) / 2

        def P(p):
            return (ox + p[0] * s, oy + p[1] * s)

        pen = K.Pen(0, 0, W, H)
        pts = [P(p) for p in self.SILUET]
        pen.poly(pts, BODY)
        pen.line(pts + [pts[0]], BODY_LINE, max(2, 1.4 * s))
        hx_, hy_ = P((150, 54))
        pen.ell(hx_, hy_, 38 * s, fill=BODY, outline=BODY_LINE, width=max(2, 1.4 * s))
        lw = max(6, 9 * s)
        for i in range(self.n - 1):
            renk = RED if i < self.b1_son else YELLOW
            seg = [P(p) for p in self.rota_parca(self.durak_f(i), self.durak_f(i + 1))]
            pen.line(seg, renk if tam else blend(INK, renk, DIM), lw)
            if ilerleme > i and not tam:
                f = min(1.0, ilerleme - i)
                pen.line([P(p) for p in self.rota_parca(self.durak_f(i), self.durak_f(i + f))], renk, lw)
        cx_m = (x0 + x1) / 2
        for i, (ad, _) in enumerate(self.duraklar):
            cx, cy = P(self.rota_noktasi(self.durak_f(i)))
            r = max(9, 11 * s)
            gecti = i < ilerleme - 0.01
            simdi = abs(i - ilerleme) < 0.01
            aktarma = i == self.b1_son
            if aktarma:
                pen.rr((cx - r * 1.5, cy - r * 1.1, cx + r * 1.5, cy + r * 1.1), r * 1.1, fill=OFF, outline=INK,
                       width=max(3, r * 0.35))
            else:
                pen.ell(cx, cy, r, fill=OFF, outline=INK, width=max(3, r * 0.35))
            if simdi and not tam:
                pen.ell(cx, cy, r * 1.9, fill=None, outline=YELLOW, width=max(3, r * 0.4))
            if gecti and etiketler and not tam:
                pen.svg(K.check_svg(RED if i <= self.b1_son else INK, 22), K.ICON_VB, cx - r * 0.8, cy - r * 0.8,
                        r * 1.6)
            if etiketler:
                b = 1 if i <= self.b1_son else 2
                fs = 32 * olcek_yazi
                col = OFF if (b == self.bolum or gecti or ozet or tam) else blend(INK, OFF, 0.5)
                if simdi and not tam:
                    col = YELLOW
                sag = cx >= cx_m - 4 * s
                ux = cx + r * 1.9 + 6 if sag else cx - r * 1.9 - 6
                yer = (x1 - ux) if sag else (ux - max(0, x0 - 30))
                fs = etiket_boyu(ad, yer + fs * 0.4, int(fs), 18)
                pen.text(ux, cy + fs * 0.36, ad, "anton", fs, col, anchor="ls" if sag else "rs")
                if kt is not None:
                    bw_ = tw(ad, "anton", fs)
                    kt.append((f"durak {ad}", (ux if sag else ux - bw_, cy - fs * 0.64, ux + bw_ if sag else ux,
                                               cy + fs * 0.4)))
        img.alpha_composite(pen.done())
        if not tam or ilerleme > 0:
            pen = K.Pen(0, 0, W, H)
            tx, ty = P(self.rota_noktasi(self.durak_f(ilerleme)))
            self.damla(pen, tx, ty + 4, max(9, 13 * s))
            img.alpha_composite(pen.done())
        return (ox, oy, ox + self.VB[2] * s, oy + self.VB[3] * s)

    @staticmethod
    def damla(pen, x, y, r, renk=RED, kenar=OFF):
        """Tren: damla (sivri ucu yukarı)."""
        tip = (x, y - r * 2.0)
        poly = [tip] + [(x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a))) for a in range(-30, 211, 6)]
        c = (x, y - r * 0.4)
        k = 1 + 5 / r
        pen.poly([(c[0] + (px - c[0]) * k, c[1] + (py - c[1]) * k) for px, py in poly], kenar)
        pen.poly(poly, renk)
        pen.ell(x - r * 0.35, y - r * 0.15, r * 0.22, fill=blend(renk, OFF, 0.6))

    def sonraki(self, i: int) -> str | None:
        return self.duraklar[i + 1][0] if i + 1 < self.n else None

    def tabela(self, img, ad: str, bolum: int, sonraki: str | None, y=340, kt=None, sag_yazi: str | None = None) -> float:
        x0, x1, h = 72, X1, 128
        pen = K.Pen(0, 0, W, H)
        pen.rr((x0 + 10, y + 12, x1 + 10, y + h + 12), 14, fill=(0, 0, 0))
        pen.rr((x0, y, x1, y + h), 14, fill=OFF)
        rc = RED if bolum == 1 else YELLOW
        pen.rr((x0, y + h - 16, x1, y + h), 6, fill=rc, corners=(False, False, True, True))
        pen.ell(x0 + 62, y + 56, 40, fill=INK)
        pen.ell(x0 + 62, y + 56, 34, fill=rc)
        pen.text(x0 + 62, y + 70, f"B{bolum}", "anton", 38, OFF if bolum == 1 else INK, anchor="ms")
        sag_w = 0.0
        if sonraki:
            ss = etiket_boyu(f"{sonraki} →", 250, 36, 24)
            sag_w = max(tw("sonraki", "courier", 24), tw(f"{sonraki} →", "anton", ss))
            pen.text(x1 - 24, y + 46, "sonraki", "courier", 24, (90, 88, 85), anchor="rs")
            pen.text(x1 - 24, y + 92, f"{sonraki} →", "anton", ss, INK, anchor="rs")
        elif sag_yazi:
            sag_w = tw(sag_yazi, "anton", 36)
            pen.text(x1 - 24, y + 92, sag_yazi, "anton", 36, INK, anchor="rs")
        yer = x1 - 24 - sag_w - 24 - (x0 + 124)
        size = 78
        while tw(ad, "anton", size) > yer and size > 40:
            size -= 2
        pen.text(x0 + 124, y + 64 + size * 0.36, ad, "anton", size, INK)
        img.alpha_composite(pen.done())
        if kt is not None:
            kt.append(("tabela", (x0, y, x1 + 10, y + h + 12)))
        return y + h + 12

    def serit(self, img, x, y0, y1, ilerleme: float):
        """Dikey durak şeridi; geçilen duraklar dolu, tren konumunda damla."""
        pen = K.Pen(0, 0, W, H)
        ys = [y0 + (y1 - y0) * i / max(1, self.n - 1) for i in range(self.n)]
        for i in range(self.n - 1):
            renk = RED if i < self.b1_son else YELLOW
            pen.line([(x, ys[i]), (x, ys[i + 1])], blend(INK, renk, DIM), 12)
            if ilerleme > i:
                f = min(1, ilerleme - i)
                pen.line([(x, ys[i]), (x, ys[i] + (ys[i + 1] - ys[i]) * f)], renk, 12)
        boy = 30
        for ad, _ in self.duraklar:
            boy = min(boy, etiket_boyu(ad, X1 - (x + 32) - 6, 30, 18))
        for i, (ad, _) in enumerate(self.duraklar):
            b = 1 if i <= self.b1_son else 2
            gecti = i < ilerleme - 0.01
            simdi = abs(i - ilerleme) < 0.01
            pen.ell(x, ys[i], 14, fill=(RED if b == 1 else YELLOW) if gecti else OFF, outline=OFF if gecti else INK,
                    width=4)
            if simdi:
                pen.ell(x, ys[i], 22, outline=YELLOW, width=5)
            col = YELLOW if simdi else (OFF if (gecti or b == self.bolum) else blend(INK, OFF, 0.45))
            pen.text(x + 32, ys[i] + boy * 0.36, ad, "anton", boy, col)
        i = min(int(ilerleme), self.n - 2)
        ty = ys[i] + (ys[i + 1] - ys[i]) * (ilerleme - i) if ilerleme < self.n - 1 else ys[-1]
        if abs(ilerleme - round(ilerleme)) > 0.01:
            self.damla(pen, x, ty + 8, 13)
        img.alpha_composite(pen.done())

    def sag_sutun(self, ilerleme: float) -> Image.Image:
        key = ("sutun", round(ilerleme, 2))
        if key not in self._c:
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            x0, x1, y0, y1 = 664, X1, 500, 1190
            pen = K.Pen(0, 0, W, H)
            pen.rr((x0, y0, x1, y1), 16, fill=PANEL, outline=BODY_LINE, width=3)
            pen.text(x0 + 20, y0 + 40, "HAT HARİTASI", "courier", 22, SOFT)
            img.alpha_composite(pen.done())
            self.harita(img, (x0 + 10, y0 + 54, x1 - 10, y0 + 340), ilerleme, etiketler=False)
            self.serit(img, x0 + 34, y0 + 392, y1 - 40, ilerleme)
            if len([k for k in self._c if isinstance(k, tuple) and k[0] == "sutun"]) > 200:
                for k in [k for k in self._c if isinstance(k, tuple) and k[0] == "sutun"][:100]:
                    del self._c[k]
            self._c[key] = img
        return self._c[key]

    def hat_icerik(self, s: Sahne, d: dict) -> None:
        alt, ust, kt = d["alt"], d["ust"], d["kutular"]
        tur = s.tur
        bol = 1 if s.durak <= self.b1_son else 2
        if tur == "kanca":
            b1 = etiket(ust, self.baslik[0], 118, INK, OFF, 21, 70, 352, rot=-1.5, max_w=850, en_kucuk=60, kutular=kt)
            b2 = b1
            if len(self.baslik) > 1:
                b2 = etiket(ust, self.baslik[1], 112, OFF, RED, 22, 70, b1[3] + 2, rot=1.2, max_w=850, en_kucuk=60,
                            kutular=kt)
            yb = bilgi_yaz(ust, 76, b2[3] + 22, s.metin, 840, 110, OFF, 34, 24, kt)
            self.harita(ust, (40, yb + 30, 680, 1530), 0, tam=True, olcek_yazi=1.0, kt=kt)
            pen = K.Pen(0, 0, W, H)
            lx, ly = 690, 1120
            for k_, (renk, ad) in enumerate(((RED, "BÖLÜM 1"), (YELLOW, "BÖLÜM 2"))):
                yy = ly + k_ * 50
                pen.line([(lx, yy), (lx + 46, yy)], renk, 12)
                pen.text(lx + 60, yy + 9, ad, "courier", 26, OFF)
            ust.alpha_composite(pen.done())
            d["makas"] = (800, 1400, 0.42)
        elif tur in ("durak", "sayi", "karsilastirma"):
            self.tabela(ust, self.duraklar[s.durak][0], bol, self.sonraki(s.durak), 340, kt,
                        sag_yazi="SON DURAK" if s.durak == self.n - 1 else None)
            d["sutun"] = True
            if tur == "durak":
                fb = (72, 500, 640, 1190)
                self.cerceve(alt, fb)
                d["foto"] = fb
                self._foto_ustu(ust, s, fb, kt)
            else:
                pen = K.Pen(0, 0, W, H)
                pen.rr((72, 500, 640, 1190), 16, fill=PANEL, outline=BODY_LINE, width=3)
                pen.text(96, 544, "NE KADAR?" if tur == "sayi" else "KARŞILAŞTIR", "courier", 26, SOFT)
                ust.alpha_composite(pen.done())
                if tur == "sayi":
                    self.sayi_karti(alt, ust, s, (92, 600, 620, 1170), kt)
                else:
                    self.cubuklar(ust, s, (100, 600, 612, 1170), kt)
            y = 1220
            if s.baslik:
                b = etiket(ust, s.baslik, 64, INK, YELLOW, 41 + s.i, 70, y, rot=-1.2, max_w=640, en_kucuk=40,
                           kutular=kt)
                y = b[3] + 14
            bilgi_yaz(ust, 76, y, s.metin, 640, 1530 - y, OFF, 34, 24, kt)
            d["makas"] = (818, 1430, 0.40)
        elif tur == "devam":
            b = etiket(ust, "DEVAMI BÖLÜM 2'DE", 92, INK, YELLOW, 41, 70, 352, rot=-1.4, kutular=kt)
            y0 = b[3] + 40
            x0, x1 = 72, X1
            pen = K.Pen(0, 0, W, H)
            pen.rr((x0 + 10, y0 + 12, x1 + 10, y0 + 352), 18, fill=(0, 0, 0))
            pen.rr((x0, y0, x1, y0 + 340), 18, fill=(34, 33, 32), outline=OFF, width=4)
            pen.text(x0 + 30, y0 + 52, "SONRAKİ DURAK", "courier", 28, SOFT)
            pen.text(x1 - 30, y0 + 52, "HAT B2", "courier", 28, YELLOW, anchor="rs")
            ad = self.duraklar[min(self.n - 1, self.b1_son + 1)][0]
            n_ch = max(1, len(ad.replace(" ", "")) + 0.5 * ad.count(" "))
            tile = min(84, (x1 - x0 - 60) / n_ch - 6)
            self.flap(pen, ad, x0 + 30, y0 + 76, tile * 1.12, tile)
            pen.text(x0 + 30, y0 + 262, "KALKIŞ", "courier", 28, SOFT)
            self.flap(pen, "BÖLÜM 2", x0 + 170, y0 + 214, 56, 50)
            ust.alpha_composite(pen.done())
            kt.append(("pano", (x0, y0, x1 + 10, y0 + 352)))
            self.harita(ust, (40, y0 + 380, 560, 1530), self.b1_son + 0.45, olcek_yazi=0.9, kt=kt)
            yy = y0 + 420
            if foto_yukle(s.spec) is not None:
                fb = (600, yy, X1 - 10, yy + 200)
                self.cerceve(alt, fb)
                d["foto"] = fb
                d["foto_karart"] = True
                yy = fb[3] + 30
            sira = s.metin or " ".join(s.kalemler)
            bilgi_yaz(ust, 600, yy, sira, X1 - 600, max(120, 1390 - yy), OFF, 28, 22, kt)
            d["makas"] = (830, 1470, 0.32)
        elif tur == "ozet":
            b = etiket(ust, "BÖLÜM 1'DE...", 96, OFF, RED, 51, 70, 352, rot=-1.3, kutular=kt)
            y0 = b[3] + 30
            self.harita(ust, (20, y0, 490, 1240), float(self.b1_son), ozet=True, olcek_yazi=0.82, kt=kt)
            self.notlar(ust, s, y0 + 40, 500, X1, kt, koyu=True)
            self.simdi(ust, s, 1250, kt)
            d["makas"] = (810, 470, 0.34)
        else:  # kapanis
            y = 352
            for k_, satir in enumerate(self._soru_satirlari(s.baslik or "SEN NE DÜŞÜNÜYORSUN?")):
                b = etiket(ust, satir, 96, INK if k_ == 0 else OFF, YELLOW if k_ == 0 else RED, 81 + k_, 70, y,
                           rot=(-1.4, 1.2)[k_ % 2], max_w=850, en_kucuk=56, kutular=kt)
                y = b[3] + 4
            yb = bilgi_yaz(ust, 76, y + 20, s.metin, 840, 120, OFF, 34, 24, kt)
            self.harita(ust, (40, yb + 20, 640, 1330), float(self.n - 1), tam=True, olcek_yazi=0.95, kt=kt)
            d["cta"] = (420, 1440)
            d["makas"] = (810, 1250, 0.40)

    @staticmethod
    def flap(pen, text, x, y, size_h, tile_w):
        size = size_h / 1.25
        for ch in text:
            if ch == " ":
                x += tile_w * 0.5
                continue
            pen.rr((x, y, x + tile_w, y + size * 1.25), 6, fill=(18, 18, 18))
            pen.text(x + tile_w / 2, y + size * 1.05, ch, "anton", size, YELLOW, anchor="ms")
            pen.line([(x, y + size * 0.62), (x + tile_w, y + size * 0.62)], (34, 33, 32), 3)
            x += tile_w + 6
        return x

    # ------------------------------------------------------------ kare
    def frame(self, t: float) -> Image.Image:
        si = self.seg_at(t)
        s = self.sahneler[si]
        lt = t - s.start
        img = self.zemin().copy()
        img.alpha_composite(self.ust_sira(self.sayac(s)))
        p = self.konum(si, t)
        # ilerleme göstergesi (hat görünümünde harita içeriğin parçası)
        if not self.koyu:
            kesik = s.tur == "devam" and t >= self.kesik_ani(s) + 0.5
            img.alpha_composite(self.zaman_cizgisi(p, kesik, s.tur == "ozet"))
        d = self.icerik(si)
        giris = _ease(lt / GIRIS) if si > 0 else 1.0
        dy = (1 - giris) * 46
        if d.get("sutun"):
            img.alpha_composite(self.sag_sutun(p))
        K.put(img, d["alt"], 0, dy, alpha=giris)
        if d["foto"] is not None:
            x0, y0, x1, y1 = d["foto"]
            w, h = int(x1 - x0), int(y1 - y0)
            dur = max(1.0, s.end - s.start)
            ph = self.foto(s, w, h, 1.0 + 0.06 * min(1.0, lt / dur))
            if d.get("foto_karart"):
                ph = karart(gri(ph), 0.45)
            K.put(img, yuvarlat(ph, 10 if self.koyu else 8), x0, y0 + dy, alpha=giris)
        K.put(img, d["ust"], 0, dy, alpha=giris)
        # makas: dolgunun ucunda (cizgi) / bölüm sonunda çizgiyi keser
        if not self.koyu:
            a, b, t0 = self.ilerleme[si]
            if s.tur == "devam":
                tk = self.kesik_ani(s)
                if t >= tk - 0.6:
                    k = _ease((t - (tk - 0.6)) / 0.6)
                    x = self.nx(self.b1_son) + (self.cut_x() - self.nx(self.b1_son)) * k
                    self.makas_ucta(img, x, t, kesiyor=k >= 1)
            elif b != a and t0 <= t < t0 + ILERLE + 0.15 and s.tur != "kanca":
                self.makas_ucta(img, self.nx(p), t, kesiyor=False)
        # Makas
        cx, cy, k = d["makas"]
        talk = K.talk_state(self.words, self.wstarts, t)
        blink = (t % 3.7) < 0.12
        self.makas.ciz(img, cx, cy + dy * 0.3, k, s.mood, talk, blink)
        # yorum çağrısı
        if d["cta"] is not None:
            an = s.kelime_ani(r"yorum")
            if an is not None and t >= an - 0.1:
                if "cta" not in self._c:
                    self._c["cta"] = K.cta_sticker(CTA, 620, 84)
                st = self._c["cta"]
                kk = K.cta_pulse(t - an)
                K.put(img, st, d["cta"][0] - st.width / 2, d["cta"][1] - st.height / 2, k=kk)
        if self.brand is not None:
            self.brand.watermark(img, t, 0.8 if self.intro else 0.0)
            if self.intro:
                self.brand.intro(img, t)
        self.kutular = list(d["kutular"])
        return K.finish(img)


# ---------------------------------------------------------------- giriş
def render_belgesel(scenes: list[SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
                    music: Path | None, meta: dict) -> Path:
    son = float(((meta or {}).get("sablon") or {}).get("son_bekleme") or 1.2)
    return K.render_frames(scenes, words, out_mp4, voice_mp3, music,
                           lambda bcfg: BelgeselVideo(scenes, words, meta, bcfg), "Belgesel", son_bekleme=son)


def render(scenes: list[SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
           music: Path | None, meta: dict) -> Path:
    """Şablon kurgu modüllerinin ortak girişi (pipeline.build: shortgen/<renderer>.py render): spec.card sahnenin
    bütün alanlarını (belgesel dahil), meta['script'] senaryoyu (belgesel bilgisi, series_part) taşır."""
    return render_belgesel(scenes, words, out_mp4, voice_mp3, music, meta)
