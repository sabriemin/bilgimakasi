"""Nasıl Üretiliyor? için "İş Emri" şablonu: fabrika zemini, canlı üretim sayacı, aşama levhası, makine bölgesi ve
ekranın altında baretli Makas'ın sunduğu İŞ EMRİ kâğıdı.

Dünya: koyu baklavalı çelik sac zemin, üst ve alt kenarda sarı-siyah ikaz bandı (arka plan; platform arayüzünün altında
kalabilir, yazı yoktur). Serinin tek ek rengi TAMAM YEŞİLİ (biten aşamanın tiki, ONAY ve KAPANDI mühürleri). Marka
kimliği korunur: kırmızı/sarı/mürekkep/kâğıt, Anton + Courier Prime Bold, yırtık etiketler, sert gölgeler, gren,
Makas (bu seride beyaz iş baretiyle), hareketli filigran.

Ekran düzeni (1080x1920). Yazı yalnız x 72-920, y 236-1528 arasında; gölgeler dahil hiçbir öğe platform arayüzüne
(sağdaki düğmeler x > 935, üst çubuk y < 170, alttaki açıklama y > 1540) taşmaz (filigran 120-228'de):
  236-330   seri etiketi (siyah yırtık "NASIL ÜRETİLİYOR?") ....... SEN İZLERKEN ÜRETİLEN [0][0].[8][8][8] KALEM
            Sayaç senaryodaki üretim sayısından (son sahnenin counter kartı: card_value '14 MİLYAR', card_label
            'KALEM / YIL'; kart yoksa dış sesteki 'yılda ... milyar kalem') saniyedeki üretimi hesaplar ve her saniye
            artar (tamburlar döner). Sayı bulunamazsa sayaç çizilmez.
  356-540   aşama levhası: sarı boyalı çelik levhada "AŞAMA / 2/4" + sağında aşamanın başlığı (kırık beyaz Anton)
  566-...   makine bölgesi: dört yanı ikaz bantlı alan; aşamanın çizimi (ya da fotoğrafı, künye çipiyle) ve en çok 2
            yırtık not etiketi (üst köşelerde; çizim dar kalıyorsa boş köşelere, değilse üstte ayrılan şeride).
            Görsel yoksa koddan çizilen genel bir sanayi presi durur.
  ...-1528  İŞ EMRİ (x 72-700): sürekli form kâğıdı, "İŞ EMRİ No. 0427" başlık şeridi, ÜRÜN satırı, sağ üstte ONAY
            kutusu, aşama listesi (biten aşamaya yeşil tik çizilir, süren aşama sarı fosforlu ve kırmızı ▶), dış ses
            satırları (okunan kelime sarı fosforlu, söylenmiş mürekkep, sıradaki soluk). Kâğıdın yüksekliği aşama
            sayısına göre ayarlanır; makine bölgesi kalan yeri alır.
  1150-1530 Makas (x 642-932, eli dahil): baretli, büyük; kâğıdın sağında durur ve kolunu uzatıp dış sesi kâğıtta gösterir,
            konuşurken bıçakları açılıp kapanır.
Kanca (ilk sahne): levha yerine büyük soru başlığı (vurgulu satır kırmızı yırtık etikette), bölgede ürünün çizimi;
kâğıttaki bütün kutular boş.
Ölçek (son sahne): sarı levhada "ÜRETİM / HIZI" (aşama numarası yok), yanında saniyedeki üretim ("DÜNYADA HER SANİYE"
/ "≈444 KALEM", sarı); bölgede rakamlı ibreli gösterge (ibre saniyedeki üretime oturur ve titrer, altında "≈444" çipi)
ve TEK büyük sayı (yıllık ya da günlük üretim, ör. "≈14 MİLYAR" + "KALEM" etiketi). Soru cümlesi söylenmeye
başlayınca levha ve hız satırının yerine soru büyük başlık olarak gelir (ilk satır kırık beyaz, ikincisi kırmızı yırtık
etikette: "SENCE BİR KALEM" / "KAÇ KİLOMETRE YAZAR?"). Son aşamanın tiki atılınca ONAY kutusuna TAMAM mührü basılır;
"Yorumlara yaz" söylenince bölgenin sağ alt köşesinde (göstergeye ve sayıya binmeden) YORUMLARA YAZ çıkartması belirir
ve ONAY kutusundaki TAMAM, KAPANDI mührüne döner (çağrı yoksa dış ses bitince).
Geçişler: levha ve makine bölgesi kart şablonunun makas kesmesiyle kesilir (kart.card_cut), yenisi sağdan sekerek
gelir; sayaç, iş emri ve Makas yerinde kalır.

Senaryo eşlemesi Adım kartlarınınkiyle aynıdır (nasil.plan: Scene.step ya da başlıktaki 'AŞAMA n'; ilk adımdan önceki
sahneler kanca, son sahne ölçek, aynı aşamanın art arda sahneleri ve adımsız ara sahneler o aşamanın devamı).
Hız: zemin, başlık satırı, levha + bölge, kâğıdın durumları, dış ses sayfaları, Makas ve sayaç tamburları önbellekte;
kare başına yalnız katmanlar birleştirilir. Aynı videonun kareleri her çalıştırmada aynıdır.
"""
from __future__ import annotations

import bisect
import math
import re
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import kart as K
from . import nasil as N
from .render import SceneSpec
from .script import tutar
from .voice import Word

W, H, FPS, SS = K.W, K.H, K.FPS, K.SS
RED, YELLOW, INK, PAPER, OFF, WHITE, DGREY = K.RED, K.YELLOW, K.INK, K.PAPER, K.OFF, K.WHITE, K.DGREY

# ---------------------------------------------------------------- renkler
YESIL = (0, 150, 90)                 # serinin tek ek rengi: TAMAM yeşili (tik, ONAY ve KAPANDI mühürleri)
SAC = (48, 50, 53)                   # baklavalı sac zemin
SAC_A, SAC_K, SAC_KABARTI = (70, 73, 77), (30, 31, 33), (57, 59, 63)
CELIK, CELIK_A, CELIK_K = (150, 153, 158), (184, 187, 192), (110, 113, 118)   # makine çizimleri
METAL = (168, 171, 176)              # cıvata, gösterge çerçevesi
FORM = (247, 244, 235)               # sürekli form kâğıdı
FORM_BANT = (231, 241, 232)          # sürekli formun soluk yeşil bantları
SOLUK = (150, 147, 140)              # kâğıtta sıradaki kelimeler ve aşamalar
FOSFOR = (253, 226, 74)              # fosforlu kalem
AHSAP, AHSAP_K, AHSAP_KK = (226, 178, 118), (198, 146, 88), (168, 118, 66)
GRAFIT, GRAFIT_A = (58, 59, 63), (120, 123, 130)
BOLGE_IC = (226, 224, 218)           # makine bölgesinin açık gri boyalı sacı

# ---------------------------------------------------------------- yerleşim
X0, X1 = 72, 920
SAFE = K.SAFE                        # (0, 170, 935, 1540)
CLIP = (0, SAFE[1], SAFE[2], SAFE[3])
UST = (0, 230, 935, 336)             # seri etiketi + sayaç satırı katmanı
UST_CY = 286
KES_Y = 342                          # açılışta makasın kestiği çizgi
ICERIK_Y0 = 346                      # levha/başlık + makine bölgesi katmanının üstü (kesme geçişi bunu keser)
LEVHA = (X0, 360, X0 + 232, 540)
BOLGE_Y0 = 566
BOLGE_BOSLUK = 28                    # makine bölgesi ile iş emri arası
FIS_X0, FIS_X1, FIS_Y1 = 72, 700, 1528
DELIK = 36                           # tırtıl şeridi genişliği
ONAY_W = 150
SATIR = 46                           # aşama satırı
LISTE_EN_FAZLA = 5                   # tek sütunda en çok bu kadar aşama; fazlası iki sütun
ANLATI_SATIR, ANLATI_LH = 4, 1.18    # dış ses: en çok 4 satır
ANLATI_BOY = (36, 34, 32, 30)
MAKAS_VB = (-300, -330, 600, 540)    # gövde merkezi SVG'de (0, 60)
MAKAS = (806, 1426, 0.85)            # gövde merkezi ve ölçek: kâğıdın sağında
MAKAS_KOL = (196.0, 40)              # kâğıda uzanan kolun yönü (derece) ve boyu
RUH = {"hook": "thinking", "step": "normal", "recap": "happy"}
CUT = K.CUT_LEN
SLIDE0, SLIDE = 0.18, 0.42           # yeni içerik sağdan gelir
STAMP0, STAMP = 0.56, 0.16           # levhadaki numara damgası
NOTE0 = 0.86                         # not etiketleri patlar
TIK = 0.38                           # tikin çizilme süresi
ONAY0 = 0.55                         # ölçek sahnesinde TAMAM mührü (son tikten sonra)
SAYAC_DONME = 0.32                   # sayaç tamburlarının dönme süresi (her saniyenin başında)
Q_RE = re.compile(r"\byorumlara\s+yaz", re.I)
DONEMLER = (("SANİYE", 1.0), ("DAKİKA", 60.0), ("SAAT", 3600.0), ("GÜN", 86400.0), ("HAFTA", 7 * 86400.0),
            ("AY", 30.44 * 86400.0), ("YIL", 365.25 * 86400.0))
DONEM_EKI = {"SANİYE": "SANİYEDE", "DAKİKA": "DAKİKADA", "SAAT": "SAATTE", "GÜN": "GÜNDE", "HAFTA": "HAFTADA",
             "AY": "AYDA", "YIL": "YILDA"}
_DONEM_RE = re.compile(r"\b(SANİYE|DAKİKA|SAAT|GÜN|HAFTA|AY|YIL)(?:DA|DE|TA|TE|LIK|LİK|LUK|LÜK)?\b")
_ANLATI_RE = re.compile(r"\b(saniyede|dakikada|saatte|günde|haftada|ayda|yılda|her\s+(?:saniye|dakika|saat|gün|hafta|"
                        r"ay|yıl)|yıllık|günlük|aylık)\b[^.?!]*?(\d[\d.,]*)\s*(milyar|milyon|bin)?\s+([a-zçğıöşü]+)",
                        re.I)
_SAYAC_DISI = {"ADET", "TANE", "ÜRETİLEN", "ÜRETİLİR", "ÜRETİLİYOR", "DÜNYADA", "TÜRKİYE'DE", "YAKLAŞIK", "HER",
               "TAHMİNİ", "TOPLAM", "/", "·", "-"}


def up(s: str) -> str:
    return K.tr_upper((s or "").strip())


def cap_h(font: str, size: float) -> float:
    return -K.tbox("H", font, size)[1]


# ---------------------------------------------------------------- üretim hızı (sayaç ve ölçek)
def _donem(metin: str) -> tuple[str, float] | None:
    m = _DONEM_RE.search(up(metin))
    if not m:
        return None
    return next((ad, sn) for ad, sn in DONEMLER if ad == m.group(1))


def _isim(etiket: str) -> str:
    """'KALEM / YIL' -> 'KALEM'; 'YILDA ÜRETİLEN ÇAY BARDAĞI' -> 'ÇAY BARDAĞI'."""
    s = _DONEM_RE.sub(" ", up(etiket))
    s = re.sub(r"[/·|,:;()\-–—]+", " ", s)
    return " ".join(w for w in s.split() if w not in _SAYAC_DISI and not re.fullmatch(r"[\d.,%≈~]+", w))


def uretim_hizi(cards: list[dict]) -> dict | None:
    """Senaryodan üretim hızı: önce counter kartı (sondan başa; card_value '14 MİLYAR', card_label 'KALEM / YIL'),
    yoksa dış sesteki 'yılda yaklaşık 14 milyar kalem' kalıbı. Dönmüş sözlük: hiz (adet/sn), isim ('KALEM'), sayi
    (ekrandaki büyük sayı, ör. '≈14 MİLYAR'), donem ('YILDA'), yer ('DÜNYADA' / 'TÜRKİYE'DE' / ''). Bulunamazsa None."""
    for c in reversed(cards):
        if (c.get("card") or "") != "counter":
            continue
        deger = str(c.get("card_value") or "")
        t = tutar(deger)
        if not t or t[0] <= 0:
            continue
        metin = " ".join(str(c.get(k) or "") for k in ("card_label", "card_note", "narration"))
        ad, sn = _donem(" ".join(str(c.get(k) or "") for k in ("card_label", "card_note"))) or _donem(metin) \
            or ("YIL", 365.25 * 86400.0)
        isim = _isim(str(c.get("card_label") or ""))
        if not isim:
            m = _ANLATI_RE.search(str(c.get("narration") or ""))
            isim = up(m.group(4)) if m else "ADET"
        yaklasik = bool(re.search(r"yaklaşık|civarı|kadar|tahmin|~|≈", metin + deger, re.I))
        sayi = re.sub(r"^[≈~]\s*", "", up(deger)).replace("₺", "").strip()
        return _hiz_sozlugu(t[0], sn, isim, ("≈" if yaklasik else "") + sayi, DONEM_EKI[ad], metin)
    for c in reversed(cards):
        m = _ANLATI_RE.search(str(c.get("narration") or ""))
        if not m:
            continue
        kat = (m.group(3) or "").lower()
        t = tutar(m.group(2) + (" " + up(kat) if kat else ""))
        if not t or t[0] <= 0:
            continue
        ad, sn = _donem(m.group(1)) or ("YIL", 365.25 * 86400.0)
        yaklasik = bool(re.search(r"yaklaşık|civarı|kadar", c.get("narration") or "", re.I))
        sayi = (m.group(2).rstrip(".,") + (" " + up(kat) if kat else ""))
        return _hiz_sozlugu(t[0], sn, up(m.group(4)), ("≈" if yaklasik else "") + sayi, DONEM_EKI[ad],
                            str(c.get("narration") or ""))
    return None


def _hiz_sozlugu(deger, sn, isim, sayi, donem, metin) -> dict:
    u = up(metin)
    yer = "DÜNYADA" if "DÜNYA" in u else ("TÜRKİYE'DE" if "TÜRKİYE" in u else "")
    return {"hiz": deger / sn, "isim": isim, "sayi": sayi, "donem": donem, "yer": yer}


def binlik(n: int, hane: int = 0) -> str:
    s = str(int(n)).rjust(hane, "0") if hane else str(int(n))
    out = ""
    for i, c in enumerate(reversed(s)):
        if i and i % 3 == 0:
            out = "." + out
        out = c + out
    return out


# ---------------------------------------------------------------- çizim yardımcıları (SVG: demo çizimleri de kullanır)
hx = K._hex


def makine_p(d, fill, sw=7, stroke=None, extra="") -> str:
    """Mürekkep hatlı düz SVG yolu (makine çizimleri)."""
    st = hx(stroke) if stroke is not None else hx(INK)
    f = "none" if fill is None else hx(fill)
    return (f'<path d="{d}" fill="{f}" stroke="{st}" stroke-width="{sw}" stroke-linejoin="round" '
            f'stroke-linecap="round" {extra}/>')


def makine_poly(pts) -> str:
    return "M" + " L".join(K.P(x, y) for x, y in pts) + " Z"


def civata_svg(cx, cy, r=6.0) -> str:
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{hx(METAL)}" stroke="{hx(INK)}" stroke-width="2.6"/>'
            f'<path d="M{cx - r * 0.55:.1f} {cy + r * 0.3:.1f} L{cx + r * 0.55:.1f} {cy - r * 0.3:.1f}" '
            f'stroke="{hx(INK)}" stroke-width="2.4"/>')


def ikaz_svg(x, y, w, h, serit=12) -> str:
    """Sarı-siyah eğik ikaz şeridi (SVG; kırpma yolu ile dikdörtgende)."""
    cid = f"ik{int(x)}_{int(y)}_{int(w)}"
    o = (f'<defs><clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath></defs>'
         f'<g clip-path="url(#{cid})"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{hx(YELLOW)}"/>')
    xx = x - h - 2 * serit
    while xx < x + w + 2 * serit:
        o += f'<path d="M{xx} {y} L{xx + serit} {y} L{xx + serit + h} {y + h} L{xx + h} {y + h} Z" fill="{hx(INK)}"/>'
        xx += 2 * serit
    return o + f'</g><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{hx(INK)}" stroke-width="4"/>'


MAKINE_VB = (0, 0, 900, 520)


def makine_svg() -> str:
    """Görseli olmayan aşamanın genel çizimi: hidrolik sanayi presi (I-profil kolonlar, kırmızı silindir, kalıp
    tablası, konveyör, ikaz şeritli kaide, manometre). Mutfak aleti gibi değil, fabrika ekipmanı gibi okunur."""
    p, q = makine_p, makine_poly
    o = f'<path d="M20 500 L880 500" stroke="{hx(INK)}" stroke-width="8" stroke-linecap="round"/>'
    o += p(q([(250, 440), (650, 440), (650, 492), (250, 492)]), CELIK_K, 7)                 # kaide
    o += ikaz_svg(262, 452, 376, 26, 14)
    for x in (290, 570):                                                                    # kolonlar
        o += p(q([(x, 60), (x + 40, 60), (x + 40, 440), (x, 440)]), CELIK, 7)
        o += f'<path d="M{x + 20} 70 L{x + 20} 430" stroke="{hx(CELIK_K)}" stroke-width="10"/>'
    o += p(q([(250, 40), (650, 40), (650, 120), (250, 120)]), YELLOW, 8)                     # üst kiriş
    for x in (272, 628):
        for y in (62, 98):
            o += civata_svg(x, y, 7)
    o += p(q([(400, 120), (500, 120), (500, 220), (400, 220)]), RED, 7)                      # hidrolik silindir
    o += p(q([(436, 220), (464, 220), (464, 262), (436, 262)]), CELIK_A, 6)                  # piston kolu
    o += p(q([(340, 262), (560, 262), (560, 300), (340, 300)]), CELIK_K, 7)                  # üst kalıp
    o += p(q([(340, 370), (560, 370), (560, 440), (340, 440)]), CELIK_K, 7)                  # alt kalıp tablası
    o += p(q([(370, 340), (530, 340), (530, 370), (370, 370)]), YELLOW, 6)                   # iş parçası
    for x in (330, 570):
        o += f'<path d="M{x} 316 l0 40" stroke="{hx(RED)}" stroke-width="6" stroke-linecap="round"/>'
    o += p(q([(130, 380), (250, 380), (250, 400), (130, 400)]), CELIK_K, 6)                  # giriş konveyörü
    o += p(q([(650, 380), (790, 380), (790, 400), (650, 400)]), CELIK_K, 6)                  # çıkış konveyörü
    for x in range(146, 250, 30):
        o += f'<circle cx="{x}" cy="410" r="10" fill="{hx(CELIK_A)}" stroke="{hx(INK)}" stroke-width="4"/>'
    for x in range(666, 790, 30):
        o += f'<circle cx="{x}" cy="410" r="10" fill="{hx(CELIK_A)}" stroke="{hx(INK)}" stroke-width="4"/>'
    for x in (150, 230, 670, 770):
        o += p(q([(x - 8, 418), (x + 8, 418), (x + 10, 492), (x - 10, 492)]), CELIK_K, 5)
    o += p(q([(680, 340), (740, 340), (740, 380), (680, 380)]), YELLOW, 6)                   # çıkan parça
    o += p(q([(690, 150), (820, 150), (820, 300), (690, 300)]), CELIK, 7)                    # kumanda dolabı
    o += f'<circle cx="720" cy="182" r="12" fill="{hx(YESIL)}" stroke="{hx(INK)}" stroke-width="4"/>'
    o += f'<circle cx="760" cy="182" r="12" fill="{hx(RED)}" stroke="{hx(INK)}" stroke-width="4"/>'
    for y in (222, 246, 270):
        o += f'<path d="M708 {y} L802 {y}" stroke="{hx(INK)}" stroke-width="5" stroke-linecap="round"/>'
    o += p("M650 200 L690 200", None, 14) + p("M650 200 L690 200", None, 6, stroke=CELIK_A)
    cx, cy, r = 160, 230, 46                                                                # manometre
    o += f'<path d="M{cx} {cy + r} L{cx} 380" stroke="{hx(INK)}" stroke-width="10"/>'
    o += f'<circle cx="{cx}" cy="{cy}" r="{r + 8}" fill="{hx(CELIK_K)}" stroke="{hx(INK)}" stroke-width="6"/>'
    o += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{hx(OFF)}" stroke="{hx(INK)}" stroke-width="4"/>'
    for k in range(7):
        b = math.radians(-225 + 45 * k)
        o += (f'<path d="M{cx + (r - 5) * math.cos(b):.1f} {cy + (r - 5) * math.sin(b):.1f} '
              f'L{cx + (r - 14) * math.cos(b):.1f} {cy + (r - 14) * math.sin(b):.1f}" stroke="{hx(INK)}" '
              'stroke-width="4"/>')
    o += (f'<path d="M{cx} {cy} L{cx + 34 * math.cos(math.radians(-30)):.1f} '
          f'{cy + 34 * math.sin(math.radians(-30)):.1f}" stroke="{hx(RED)}" stroke-width="7" stroke-linecap="round"/>')
    o += f'<circle cx="{cx}" cy="{cy}" r="7" fill="{hx(INK)}"/>'
    return o


# ---------------------------------------------------------------- zemin: baklavalı sac
_static: dict = {}


def ikaz_img(w: float, h: float, serit: float = 34, seed: int = 0, asinma: float = 1.0) -> Image.Image:
    """Sarı-siyah eğik ikaz şeridi (SS ölçeğinde RGBA), hafif aşınmış."""
    S = SS
    pw, ph = int(round(w * S)), int(round(h * S))
    im = Image.new("RGBA", (pw, ph), YELLOW + (255,))
    d = ImageDraw.Draw(im)
    p = serit * 2 * S
    x = -ph - p
    while x < pw + p:
        d.polygon([(x, 0), (x + serit * S, 0), (x + serit * S + ph, ph), (x + ph, ph)], fill=INK + (255,))
        x += p
    if asinma > 0:
        rng = np.random.default_rng(seed)
        for _ in range(int(pw * ph / (S * S) / 900 * asinma)):
            cx, cy = rng.uniform(0, pw), rng.uniform(0, ph)
            L = rng.uniform(4, 22) * S
            a = rng.uniform(-0.4, 0.4)
            d.line([(cx, cy), (cx + L * math.cos(a), cy + L * math.sin(a))],
                   fill=(92, 90, 84, int(rng.uniform(70, 150))), width=max(1, int(rng.uniform(0.8, 2.2) * S)))
    return im


def sac_zemin() -> Image.Image:
    """Koyu baklavalı sac + üst/alt kenarda ikaz bandı (bir kez çizilir)."""
    if "zemin" in _static:
        return _static["zemin"]
    S, T = 2, 36
    tile = Image.new("RGBA", (2 * T * S, 2 * T * S), SAC + (255,))
    d = ImageDraw.Draw(tile)

    def kabarti(cx, cy, ang):
        L, w = 22, 6.5
        ux, uy = math.cos(math.radians(ang)) * L / 2, math.sin(math.radians(ang)) * L / 2
        for off, col in ((1.6, SAC_K), (-1.1, SAC_A), (0.0, SAC_KABARTI)):
            a = ((cx - ux + off) * S, (cy - uy + off) * S)
            b = ((cx + ux + off) * S, (cy + uy + off) * S)
            d.line([a, b], fill=col, width=int(w * S))
            for q in (a, b):
                d.ellipse([q[0] - w * S / 2, q[1] - w * S / 2, q[0] + w * S / 2, q[1] + w * S / 2], fill=col)

    for i in range(2):
        for j in range(2):
            kabarti(T / 2 + i * T, T / 2 + j * T, 45 if (i + j) % 2 == 0 else -45)
    tile = tile.resize((2 * T, 2 * T), Image.LANCZOS)
    img = Image.new("RGBA", (W, H), SAC + (255,))
    for y in range(0, H, 2 * T):
        for x in range(0, W, 2 * T):
            img.alpha_composite(tile, (x, y))
    rng = np.random.default_rng(11)          # geniş ölçekli ışık farkı ve kenar kararması
    n = rng.normal(0, 1, (H // 160 + 2, W // 160 + 2)).astype(np.float32)
    n = np.asarray(Image.fromarray(n).resize((W, H), Image.BICUBIC))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = ((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.45) / (H * 0.6)) ** 2
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    arr += (n * 6 - np.clip(vig, 0, 2) * 14)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    pen = K.Pen(0, 0, W, H)
    for y0, y1, seed in ((0, 54, 1), (H - 54, H, 2)):
        pen.paste(ikaz_img(W, y1 - y0, 40, seed, 0.6), 0, y0)
        yy_ = y1 if y0 == 0 else y0
        pen.line([(0, yy_), (W, yy_)], INK, 6)
    img.alpha_composite(pen.done())
    _static["zemin"] = img
    return img


# ---------------------------------------------------------------- etiket, cıvata, levha, bölge
def etiket(pen: K.Pen, text, size, fg, bg, seed, cx, cy, rot=0.0, shadow=(6, 8, 0, 0.9), rim=OFF):
    """Yırtık kâğıt etiketi merkezi (cx, cy) olacak şekilde yapıştırır; (w, h) döndürür."""
    return N.paste_label(pen, text, size, fg, bg, seed, cx, cy, rot=rot, shadow=shadow, rim=rim)


def civata(pen: K.Pen, cx, cy, r=8.0, ang=-30):
    pen.ell(cx + 1.8, cy + 2.2, r, fill=INK)
    pen.ell(cx, cy, r, fill=METAL, outline=INK, width=2.6)
    a = math.radians(ang)
    dx, dy = math.cos(a) * r * 0.62, math.sin(a) * r * 0.62
    pen.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], INK, 2.6)


def halka_maske(w, h, b, r_dis=10, r_ic=4) -> Image.Image:
    S = SS
    m = Image.new("L", (int(w * S), int(h * S)), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], r_dis * S, fill=255)
    d.rounded_rectangle([b * S, b * S, (w - b) * S - 1, (h - b) * S - 1], r_ic * S, fill=0)
    return m


BANT = 22


def bolge(pen: K.Pen, box, seed=3, ic=BOLGE_IC):
    """Makine bölgesi: ikaz bantlı çerçeve (yer işaret bandı gibi), içi açık gri boyalı sac; köşelerde cıvata."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pen.rr((x0 + 12, y0 + 12, x1 + 12, y1 + 12), 12, fill=INK)
    pen.rr((x0 - 5, y0 - 5, x1 + 5, y1 + 5), 14, fill=INK)
    band = ikaz_img(w, h, 26, seed, 0.8)
    band.putalpha(halka_maske(w, h, BANT, 10, 4))
    pen.paste(band, x0, y0)
    pen.rr((x0 + BANT, y0 + BANT, x1 - BANT, y1 - BANT), 4, fill=INK)
    pen.rr((x0 + BANT + 5, y0 + BANT + 5, x1 - BANT - 5, y1 - BANT - 5), 2, fill=ic)
    k = BANT + 20
    for cx, cy in ((x0 + k, y0 + k), (x1 - k, y0 + k), (x0 + k, y1 - k), (x1 - k, y1 - k)):
        civata(pen, cx, cy, 7)


def plaka(pen: K.Pen, box, renk=YELLOW, golge=10):
    """Boyalı çelik levha: mürekkep kenar, sert gölge, köşe cıvataları."""
    x0, y0, x1, y1 = box
    pen.rr((x0 + golge, y0 + golge, x1 + golge, y1 + golge), 10, fill=INK)
    pen.rr((x0, y0, x1, y1), 10, fill=renk, outline=INK, width=6)
    pen.line([(x0 + 10, y0 + 9), (x1 - 10, y0 + 9)], K.blend(renk, WHITE, 0.45), 3)
    for cx, cy in ((x0 + 20, y0 + 22), (x1 - 20, y0 + 22), (x0 + 20, y1 - 20), (x1 - 20, y1 - 20)):
        civata(pen, cx, cy, 7)


# ---------------------------------------------------------------- mekanik sayaç tamburu
_tambur: dict = {}


def tambur(cw, ch, d0: str, d1: str, roll: float, size, bg) -> Image.Image:
    """Tek tambur (1x): d0 yukarı kayarken d1 alttan gelir (roll 0..1); üst ve alt kenarda silindir gölgesi."""
    key = (cw, ch, d0, d1, round(roll * 12), size, bg)
    if key in _tambur:
        return _tambur[key]
    roll = round(roll * 12) / 12
    p = K.Pen(0, 0, cw, ch)
    p.rr((0, 0, cw, ch), 6, fill=bg)
    base = ch / 2 + cap_h("anton", size) / 2
    if d0 == d1 or roll <= 0:
        p.text(cw / 2, base, d0, "anton", size, OFF, anchor="ms")
    else:
        p.text(cw / 2, base - roll * ch, d0, "anton", size, OFF, anchor="ms")
        p.text(cw / 2, base + (1 - roll) * ch, d1, "anton", size, OFF, anchor="ms")
    im = p.done()
    a = np.asarray(im.getchannel("A"), dtype=np.float32)
    yy = np.linspace(-1, 1, im.height)[:, None]
    g = np.clip(np.abs(yy) ** 3 * 190, 0, 190) * (a > 0)
    sh = Image.new("RGBA", im.size, INK + (0,))
    sh.putalpha(Image.fromarray(np.broadcast_to(g, a.shape).astype(np.uint8)))
    out = im.copy()
    out.alpha_composite(sh)
    clip = Image.new("L", im.size, 0)
    ImageDraw.Draw(clip).rounded_rectangle([0, 0, im.width - 1, im.height - 1], 6, fill=255)
    out.putalpha(Image.fromarray(np.minimum(np.asarray(out.getchannel("A")), np.asarray(clip))))
    if len(_tambur) > 600:
        _tambur.clear()
    _tambur[key] = out
    return out


# ---------------------------------------------------------------- lastik mühür, tik
def muhur_img(satirlar: list[str], size: float, col, rot: float = -8, seed: int = 0, alpha: float = 0.92,
              dolu: bool = False):
    """Lastik mühür (1x RGBA): çift çerçeve, Anton yazı, mürekkep boşlukları. dolu: mürekkep blok, yazı kâğıt rengi
    (altındaki yazıların üstüne basıldığında da okunur)."""
    pad = size * 0.38
    ws = [K.tw(t, "anton", size) for t in satirlar]
    capH = cap_h("anton", size)
    ust = max(capH, -K.tbox(" ".join(satirlar), "anton", size)[1])
    lh = capH + size * 0.3
    w = max(ws) + 2 * pad + 16
    h = (len(satirlar) - 1) * lh + ust + 2 * pad + 12
    m = 24
    pen = K.Pen(0, 0, w + 2 * m, h + 2 * m)
    if dolu:
        pen.rr((m + 6, m + 8, m + w + 6, m + h + 8), 12, fill=INK + (150,))
        pen.rr((m, m, m + w, m + h), 12, fill=tuple(col) + (255,))
        pen.rr((m + 9, m + 9, m + w - 9, m + h - 9), 8, outline=FORM + (255,), width=3)
    else:
        for inset, lw in ((0, 7), (11, 3)):
            pen.rr((m + inset, m + inset, m + w - inset, m + h - inset), 10, outline=tuple(col) + (255,), width=lw)
    for j, t in enumerate(satirlar):
        pen.text(m + w / 2, m + pad + 6 + ust + j * lh, t, "anton", size, (FORM if dolu else tuple(col)) + (255,),
                 anchor="ms")
    im = pen.done()
    rng = np.random.default_rng(seed)
    a = np.asarray(im.getchannel("A"), dtype=np.float32)
    kucuk = rng.normal(0, 1, (max(2, im.height // 5), max(2, im.width // 5))).astype(np.float32)
    n1 = np.asarray(Image.fromarray(kucuk).resize(im.size, Image.BICUBIC))
    keep = np.clip(n1 * 1.6 + 1.3, 0, 1) * (rng.random(a.shape) > 0.07)
    a = a * ((0.82 + 0.18 * keep) if dolu else (0.5 + 0.5 * keep)) * alpha
    im.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
    return im.rotate(rot, resample=Image.BICUBIC, expand=True) if rot else im


def tik_svg(col, w=16) -> str:
    return (f'<path d="M14 52 Q26 60 38 78 Q58 34 92 6" fill="none" stroke="{hx(col)}" stroke-width="{w}" '
            'stroke-linecap="round" stroke-linejoin="round"/>')


_tik: dict = {}


def tik_img(s: float, k: float) -> Image.Image:
    """Keçeli kalemle atılmış yeşil tik (1x; mürekkep gölgeli); k: çizim ilerlemesi (0-1)."""
    k = round(min(1.0, max(0.0, k)) * 10) / 10
    key = (round(s), k)
    if key not in _tik:
        L = 150
        st = "" if k >= 1 else f' stroke-dasharray="{L * k:.1f} {L}"'
        g = (tik_svg(INK, 24).replace("/>", f'{st} transform="translate(3 4)"/>')
             + tik_svg(YESIL, 15).replace("/>", f"{st}/>"))
        im = K.svg_img(g, (0, 0, 104, 104), s * SS, s * SS)
        _tik[key] = im.resize((max(1, int(s)), max(1, int(s))), Image.LANCZOS)
    return _tik[key]


# ---------------------------------------------------------------- ibreli gösterge (rakamsız)
def _ac(v, vmax):
    return math.radians(135 + 270 * v / vmax)


def kadran_svg(R, bolgeler, yazi="ÜRETİM HIZI") -> str:
    """Göstergenin sabit kısmı (ibresiz): çelik çerçeve, kadran, renkli bölgeler, çentikler."""
    o = f'<circle cx="8" cy="10" r="{R + 22}" fill="{hx(INK)}"/>'
    o += f'<circle cx="0" cy="0" r="{R + 22}" fill="{hx(METAL)}" stroke="{hx(INK)}" stroke-width="6"/>'
    for a in range(0, 360, 45):
        rr = R + 11
        o += civata_svg(rr * math.cos(math.radians(a + 22.5)), rr * math.sin(math.radians(a + 22.5)), 4.5)
    o += f'<circle cx="0" cy="0" r="{R}" fill="{hx(OFF)}" stroke="{hx(INK)}" stroke-width="6"/>'
    rz = R - 24

    def yay(v0, v1, r, col, sw):
        a0, a1 = _ac(v0, 100), _ac(v1, 100)
        big = 1 if (a1 - a0) > math.pi else 0
        return (f'<path d="M{K.P(r * math.cos(a0), r * math.sin(a0))} A{r} {r} 0 {big} 1 '
                f'{K.P(r * math.cos(a1), r * math.sin(a1))}" stroke="{hx(col)}" stroke-width="{sw}" fill="none"/>')

    for v0, v1, col in bolgeler:
        o += yay(v0, v1, rz, col, 22)
    v = 0
    while v <= 100 + 1e-6:
        a = _ac(v, 100)
        maj = v % 20 == 0
        r0, r1 = R - 8, R - (42 if maj else 28)
        o += (f'<path d="M{K.P(r0 * math.cos(a), r0 * math.sin(a))} L{K.P(r1 * math.cos(a), r1 * math.sin(a))}" '
              f'stroke="{hx(INK)}" stroke-width="{6 if maj else 3}" stroke-linecap="round"/>')
        v += 5
    return o


def ibre_svg(R, v) -> str:
    a = _ac(v, 100)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    tip = (ux * R * 0.84, uy * R * 0.84)
    tail = (-ux * R * 0.2, -uy * R * 0.2)
    bw = max(9, R * 0.07)
    d = (f"M{K.P(*tip)} L{K.P(nx * bw, ny * bw)} L{K.P(tail[0] + nx * bw * 0.6, tail[1] + ny * bw * 0.6)} "
         f"L{K.P(tail[0] - nx * bw * 0.6, tail[1] - ny * bw * 0.6)} L{K.P(-nx * bw, -ny * bw)} Z")
    o = f'<path d="{d}" transform="translate(4 6)" fill="{hx(INK)}" opacity="0.35"/>'
    o += f'<path d="{d}" fill="{hx(RED)}" stroke="{hx(INK)}" stroke-width="4" stroke-linejoin="round"/>'
    o += f'<circle cx="0" cy="0" r="{R * 0.13:.1f}" fill="{hx(INK)}"/>'
    o += f'<circle cx="0" cy="0" r="{R * 0.055:.1f}" fill="{hx(METAL)}"/>'
    o += (f'<path d="M{K.P(-R * 0.78, -R * 0.2)} A{R * 0.8} {R * 0.8} 0 0 1 {K.P(-R * 0.2, -R * 0.78)} '
          f'L{K.P(-R * 0.26, -R * 0.66)} A{R * 0.68} {R * 0.68} 0 0 0 {K.P(-R * 0.66, -R * 0.26)} Z" '
          'fill="#ffffff" opacity="0.45"/>')
    return o


# ---------------------------------------------------------------- Makas (baretli, işaret eden kol)
def baret_svg() -> str:
    """Beyaz iş bareti: bıçaklar baretin tepesinden çıkar, siper gözlerin hemen üstünde (Makas'ın eğikliğiyle)."""
    ink, white, off = hx(INK), hx(WHITE), hx((238, 236, 230))
    kubbe = "M-84 -40 C-86 -104 -46 -134 0 -134 C46 -134 86 -104 84 -40 Z"
    siper = "M-108 -46 Q0 -60 108 -46 L110 -32 Q0 -44 -110 -32 Z"
    sirt = "M-13 -132 L13 -132 L16 -44 L-16 -44 Z"

    def sil(col, extra):
        st = f'fill="{col}" stroke="{col}" stroke-width="{6 + extra}" stroke-linejoin="round"'
        return f'<path d="{kubbe}" {st}/><path d="{siper}" {st}/>'

    o = '<g transform="rotate(-6 0 60)">'
    o += f'<g transform="translate(5 5)">{sil(ink, 18)}</g>' + sil(white, 18)
    st = f'stroke="{ink}" stroke-width="6" stroke-linejoin="round"'
    o += f'<path d="{kubbe}" fill="{white}" {st}/>'
    o += f'<path d="{sirt}" fill="{off}" stroke="{ink}" stroke-width="4" stroke-linejoin="round"/>'
    o += ('<path d="M-66 -64 Q-64 -96 -40 -116" stroke="#ffffff" stroke-width="8" fill="none" '
          'stroke-linecap="round" opacity="0.9"/>')
    o += f'<path d="{siper}" fill="{white}" {st}/>'
    o += f'<path d="M-96 -40 Q0 -52 96 -40" stroke="{hx(YELLOW)}" stroke-width="5" fill="none"/>'
    return o + "</g>"


def makas_svg(mood: str, mouth: str, blink: bool, point: float | None, L: float) -> str:
    """kart.mascot_svg + baret + (point verilirse) o yöne uzanan işaret eden kol (nasil.mascot_svg'nin kolu)."""
    body = K.mascot_svg(mood, mouth, blink) + baret_svg()
    if point is None:
        return body
    ink, white = hx(INK), hx(WHITE)
    arm = '<g transform="rotate(-6 0 60)">'
    arm += f'<g transform="translate(5 5)">{N._arm(point, L, ink, ink, 5, extra=18)}</g>'
    arm += N._arm(point, L, white, white, 5, extra=18) + N._arm(point, L, ink, white, 5) + "</g>"
    return body + arm


class Makas:
    """İfade/ağız/göz kırpma başına bir kez çizilen baretli Makas (1x)."""

    def __init__(self):
        self._c: dict = {}

    def sprite(self, mood, mouth, blink, point, L, scale) -> Image.Image:
        key = (mood, mouth, blink, point, L, round(scale, 3))
        if key not in self._c:
            vb = MAKAS_VB
            im = K.svg_img(makas_svg(mood, mouth, blink, point, L), vb, vb[2] * scale * SS, vb[3] * scale * SS)
            self._c[key] = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
        return self._c[key]

    @staticmethod
    def origin(cx, cy, scale) -> tuple[float, float]:
        return cx + MAKAS_VB[0] * scale, cy + (MAKAS_VB[1] - 60) * scale


# ---------------------------------------------------------------- iş emri kâğıdının ölçüleri
def fis_olcu(n: int) -> dict:
    """Aşama sayısına göre iş emrinin ölçüleri (tasarım pikseli): kâğıdın üstü, başlık şeridi, ONAY kutusu, liste
    satırları (1 ya da 2 sütun), dış ses dikdörtgeni."""
    sut = 1 if n <= LISTE_EN_FAZLA else 2
    satir = max(1, math.ceil(n / sut))
    rh = SATIR if satir <= LISTE_EN_FAZLA else max(34, SATIR * LISTE_EN_FAZLA / satir)
    anlati_h = ANLATI_SATIR * ANLATI_BOY[0] * ANLATI_LH + 20
    h = 136 + satir * rh + 18 + anlati_h + 14
    y0 = FIS_Y1 - h
    kx0, kx1 = FIS_X0 + DELIK, FIS_X1 - DELIK
    liste_y0 = y0 + 140
    ayrac2 = liste_y0 + satir * rh + 8
    return {
        "y0": y0, "kx0": kx0, "kx1": kx1, "serit": (kx0 + 4, y0 + 14, kx1 - ONAY_W - 14, y0 + 74),
        "urun_y": y0 + 114, "onay": (kx1 - ONAY_W, y0 + 26, kx1 - 4, y0 + 122), "ayrac1": y0 + 132,
        "liste_y0": liste_y0, "rh": rh, "sut": sut, "satir": satir, "ayrac2": ayrac2,
        "anlati": (kx0 + 14, ayrac2 + 10, kx1 - 28, FIS_Y1 - 14),
    }


class FisAnlati(N.Speech):
    """İş emrine daktiloyla yazılmış dış ses: okunan kelimenin altından sarı fosforlu kalem geçer, söylenmiş
    kelimeler mürekkep, sıradakiler soluk (sessiz izleyen de cümlenin tamamını okur)."""

    def image(self, pi: int, cur: int) -> Image.Image:
        key = (pi, cur)
        if key in self._img:
            return self._img[key]
        x0, y0, x1, y1 = self.rect
        pen = K.Pen(x0 - 8, y0 - 4, x1 + 8, y1 + 4)
        lines = self.lines.get(pi, [])
        size = self.size
        lh = size * self.lh
        cap = cap_h(self.FONT, size)
        base = (y0 + y1) / 2 - (len(lines) - 1) * lh / 2 + cap / 2
        sp = K.tw(" ", self.FONT, size)
        for li, L in enumerate(lines):
            x = x0
            for i in L:
                ww = K.tw(self.texts[i], self.FONT, size)
                if i == cur:
                    pen.rr((x - 5, base + li * lh - size * 0.78, x + ww + 5, base + li * lh + size * 0.22), 4,
                           fill=FOSFOR)
                col = INK if i <= cur else SOLUK
                pen.text(x, base + li * lh, self.texts[i], self.FONT, size, col)
                x += ww + sp
        if len(self._img) > 96:
            self._img.clear()
        self._img[key] = pen.done()
        return self._img[key]

    def put(self, img: Image.Image, cur: int, dy: float = 0.0, alpha: float = 1.0) -> None:
        if not self.pages:
            return
        pi = self.page_of(min(cur, self.b - 1))
        K.put(img, self.image(pi, cur), self.rect[0] - 8, self.rect[1] - 4 + dy, alpha=alpha, clip=CLIP)


# ---------------------------------------------------------------- video
class IsEmriVideo:
    def __init__(self, scenes: list[SceneSpec], words: list[Word], meta: dict, bcfg: dict):
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        on = bool(bcfg.get("enabled", False))
        self.intro = bool(on and bcfg.get("intro_cut", True))
        self.brand = None
        if on:
            from .brand import Brand
            self.brand = Brand(bcfg, {})
        self.segs = N.plan(scenes, "AŞAMA")
        ranges, a = [], 0
        n = len(scenes)
        for i, s in enumerate(scenes):
            b = min(len(words), a + len(s.words)) if i < n - 1 else len(words)
            ranges.append((a, b))
            a = b
        for seg in self.segs:
            seg.start, seg.end = scenes[seg.scenes[0]].start, scenes[seg.scenes[-1]].end
            seg.a, seg.b = ranges[seg.scenes[0]][0], ranges[seg.scenes[-1]][1]
        self.seg_starts = [s.start for s in self.segs]
        self.steps = [s for s in self.segs if s.kind == "step"]
        self.N = len(self.steps)
        self.starts = [w.start for w in words]
        self.kicker = up(scenes[0].kicker) if scenes and (scenes[0].kicker or "").strip() else "NASIL ÜRETİLİYOR?"
        recap = self.segs[-1] if self.segs and self.segs[-1].kind == "recap" else None
        topic = str(self.meta.get("topic") or "")
        self.urun = (" ".join(recap.title) if recap and recap.title else up(re.sub(
            r"\s+(nasıl|nasil)\b.*$", "", topic, flags=re.I))) or "ÜRÜN"
        self.no = f"{zlib.crc32((topic or self.urun).encode('utf-8')) % 9000 + 1000:04d}"
        self.hiz = uretim_hizi([dict(s.card or {}, narration=s.narration) for s in scenes])
        self.son = max([self.segs[-1].end if self.segs else 0.0] + [w.end for w in words[-1:]]) + 2.5
        if self.hiz:
            enbuyuk = self.hiz["hiz"] * self.son
            self.hiz["hane"] = max(3, len(str(int(enbuyuk))))
            if enbuyuk < 3:            # video boyunca sayaç kıpırdamazdı: gösterme
                self.hiz = None
        self.olcu = fis_olcu(max(1, self.N))
        self.bolge_y1 = self.olcu["y0"] - BOLGE_BOSLUK
        self.icerik = (0, ICERIK_Y0, SAFE[2], self.bolge_y1 + 20)
        self.makas = Makas()
        self._lay: dict = {}
        self._speech: dict = {}
        self._q: dict = {}

    # ------------------------------------------------------------ zaman
    def seg_at(self, t: float) -> int:
        return max(0, bisect.bisect_right(self.seg_starts, t) - 1)

    def cur_word(self, t: float, seg) -> int:
        if seg.a >= seg.b:
            return seg.b
        if seg is self.segs[-1] and t > self.words[seg.b - 1].end + 0.35:
            return seg.b
        cur = bisect.bisect_right(self.starts, t + 0.03) - 1
        return min(max(cur, seg.a), seg.b - 1)

    def bitis(self, k: int) -> float | None:
        """k. aşamanın bittiği an: sonraki aşamanın (ya da ölçeğin) başı; yoksa None."""
        if k + 1 < self.N:
            return self.steps[k + 1].start
        recap = self.segs[-1] if self.segs and self.segs[-1].kind == "recap" else None
        return recap.start if recap else None

    def kapanis_ani(self) -> float | None:
        """KAPANDI mührünün anı: 'Yorumlara yaz' söylenince, yoksa dış ses bitince (ölçek sahnesi varsa)."""
        recap = self.segs[-1] if self.segs and self.segs[-1].kind == "recap" else None
        if recap is None:
            return None
        cta = self.recap_cta(recap)
        if cta is not None:
            return self.words[cta].start - 0.08
        return (self.words[recap.b - 1].end + 0.2) if recap.b > recap.a else recap.start + 1.0

    # ------------------------------------------------------------ üst satır: seri etiketi + sayaç
    def ust(self) -> tuple[Image.Image, float]:
        """Seri etiketi katmanı ve etiketin sağ kenarı."""
        if "ust" not in self._lay:
            pen = K.Pen(*UST)
            ls = 44
            sayac_w = self.sayac_genislik(40, 54, 42)[0] if self.hiz else 0
            room = X1 - X0 - (sayac_w + 40 if self.hiz else 0)
            while ls > 30 and N.label_w(self.kicker, ls) > room:
                ls -= 2
            lw = N.label_w(self.kicker, ls)
            etiket(pen, self.kicker, ls, YELLOW, INK, 41, X0 + lw / 2 + 2, UST_CY, rot=1.2, shadow=(5, 6, 0, 0.9))
            self._lay["ust"] = (pen.done(), X0 + lw + 6)
        return self._lay["ust"]

    def sayac_degeri(self, t: float) -> int:
        """Sayacın t anında gösterdiği (dönmesi biten) sayı: her saniyenin başında saniyedeki üretim kadar artar."""
        return int(self.hiz["hiz"] * int(t)) if self.hiz else 0

    def sayac_metni(self, v: float) -> str:
        return binlik(int(v), self.hiz["hane"])

    def sayac_genislik(self, cw, ch, size) -> tuple[float, float]:
        metin = self.sayac_metni(0)
        dot_w = cw * 0.34
        tot = sum(dot_w if c == "." else cw + 4 for c in metin) - 4
        return tot + 24 + 18 + K.tw(self.hiz["isim"], "anton", 34), tot

    def sayac_olcu(self) -> tuple[float, float, float, str]:
        """(tambur genişliği, yüksekliği, rakam boyu, isim) — etiketin sağına sığacak biçimde."""
        if "sayac_olcu" not in self._lay:
            cw, ch, size = 40, 54, 42
            isim = self.hiz["isim"]
            sol = X0 + N.label_w(self.kicker, 30) + 30
            while cw > 26 and self.sayac_genislik(cw, ch, size)[0] > X1 - sol:
                cw, ch, size = cw - 2, ch - 2.6, size - 2
            tot = self.sayac_genislik(cw, ch, size)[1]
            isim = K.fit_words(isim, "anton", 34, max(80, X1 - sol - tot - 30))
            self._lay["sayac_olcu"] = (cw, ch, size, isim)
        return self._lay["sayac_olcu"]

    def sayac(self, img: Image.Image, t: float) -> None:
        if not self.hiz:
            return
        cw, ch, size, isim = self.sayac_olcu()
        sn = int(t)
        p = K.ease_in_out(K.clamp((t - sn) / SAYAC_DONME)) if sn > 0 else 1.0
        eski = self.sayac_metni(self.hiz["hiz"] * max(0, sn - 1))
        yeni = self.sayac_metni(self.hiz["hiz"] * sn)
        if len(eski) != len(yeni):
            eski = yeni
        key = ("sayac", yeni, eski, round(p * 12))
        lay = self._lay.get(key)
        if lay is None:
            pen = K.Pen(560, 230, SAFE[2], 336)
            iw = K.tw(isim, "anton", 34)
            y = UST_CY - ch / 2 + 10
            dot_w = cw * 0.34
            tot = sum(dot_w if c == "." else cw + 4 for c in yeni) - 4
            x = X1 - iw - 18 - tot
            pen.text(X1, y + ch / 2 + cap_h("anton", 34) / 2, isim, "anton", 34, OFF, anchor="rs")
            pen.rr((x - 10, y - 8, x + tot + 10, y + ch + 8), 10, fill=INK)
            pen.text(x - 2, y - 16, "SEN İZLERKEN ÜRETİLEN", "courier", 24, YELLOW)
            son = max(i for i, c in enumerate(yeni) if c.isdigit())
            parcalar = []
            for i, (c0, c1) in enumerate(zip(eski, yeni)):
                if c1 == ".":
                    pen.ell(x + dot_w / 2, y + ch - 10, 4.2, fill=OFF)
                    x += dot_w
                    continue
                parcalar.append((x, c0, c1, i == son))
                x += cw + 4
            lay = pen.done()
            for x_, c0, c1, last in parcalar:
                im = tambur(int(cw), int(ch), c0, c1, p, size, RED if last else (40, 39, 39))
                K._comp(lay, im, x_ - 560, y - 230)
            if len([k for k in self._lay if isinstance(k, tuple) and k[0] == "sayac"]) > 40:
                for k in [k for k in self._lay if isinstance(k, tuple) and k[0] == "sayac"]:
                    del self._lay[k]
            self._lay[key] = lay
        K.put(img, lay, 560, 230, clip=CLIP)

    # ------------------------------------------------------------ levha ve başlık
    def levha(self, pen: K.Pen, seg) -> None:
        """Sarı levha: üstte "AŞAMA", altında büyük aşama numarası ve "/4" (ölçekte "4/4", bölü yeşil)."""
        bx0, by0, bx1, by1 = LEVHA
        plaka(pen, LEVHA, YELLOW)
        cx = (bx0 + bx1) / 2
        ks = 34
        kb = by0 + 26 + cap_h("anton", ks)                  # "AŞAMA" tabanı (Ş çengeli altta kalır)
        pen.text(cx, kb, "ÜRETİM" if seg.kind == "recap" else "AŞAMA", "anton", ks, INK, anchor="ms")
        if seg.kind == "recap":    # ölçek: aşama numarası yok (beşinci aşama sanılmasın), levhada ÜRETİM HIZI
            hs = 96
            while hs > 40 and K.tw("HIZI", "anton", hs) > bx1 - bx0 - 44:
                hs -= 4
            pen.text(cx, by1 - 24, "HIZI", "anton", min(hs, by1 - 24 - kb - ks * 0.22 - 14), INK, anchor="ms")
            return
        num = str(seg.number if seg.kind == "step" else self.N)
        n = f"/{self.N}"
        alt = by1 - 24
        ust = kb + ks * 0.22 + 8                            # çengelin altı + boşluk
        ns = 140
        while ns > 40 and (cap_h("anton", ns) > alt - ust
                           or K.tw(num, "anton", ns) + 8 + K.tw(n, "anton", ns * 0.45) > bx1 - bx0 - 44):
            ns -= 4
        ss = ns * 0.45
        nw, sw = K.tw(num, "anton", ns), K.tw(n, "anton", ss)
        x = cx - (nw + 8 + sw) / 2
        pen.text(x, alt, num, "anton", ns, INK)
        pen.text(x + nw + 8, alt, n, "anton", ss, RED if seg.kind == "step" else YESIL)

    def baslik(self, pen: K.Pen, lines: list[str], renkler: tuple | None = None) -> None:
        """Levhanın sağında başlık: kırık beyaz Anton (renkler verilirse satır satır ve satır kırılımı korunur), 1-3
        satır, levhanın yüksekliğinde ortalı."""
        bx0, by0, bx1, by1 = LEVHA
        tx = bx1 + 34
        size = 0
        if renkler:
            for sz in range(100, 35, -2):
                if (all(K.tw(L, "anton", sz) <= X1 - tx for L in lines)
                        and cap_h("anton", sz) + (len(lines) - 1) * N.title_pitch(lines, sz) <= by1 - by0):
                    size = sz
                    break
        if not size:
            size, lines = N.fit_lines(lines, "anton", X1 - tx, 100, 36, 3, by1 - by0, pitch=N.title_pitch)
        capH = cap_h("anton", size)
        lh = N.title_pitch(lines, size)
        block = capH + (len(lines) - 1) * lh
        top = (by0 + by1) / 2 - block / 2
        for k, L in enumerate(lines):
            renk = renkler[min(k, len(renkler) - 1)] if renkler else OFF
            pen.text(tx, top + capH + k * lh, K.fit_words(L, "anton", size, X1 - tx), "anton", size, renk)

    def kanca_basligi(self, pen: K.Pen, seg) -> float:
        """Kancanın büyük soru başlığı (vurgulu satır kırmızı yırtık etikette); bloğun alt kenarını döndürür."""
        max_h = min(380, self.bolge_y1 - 240 - LEVHA[1])     # makine bölgesine en az 240 px kalır
        return self.buyuk_baslik(pen, seg.title or [self.kicker], seg.hl, max_h)

    def buyuk_baslik(self, pen: K.Pen, lines: list[str], hl: int, max_h: float, en_kucuk: int = 60) -> float:
        """Büyük başlık (kanca ve ölçekteki soru): satırlar kırık beyaz Anton, hl. satır kırmızı yırtık etikette;
        bloğun alt kenarını döndürür."""
        for size in range(124, en_kucuk, -4):
            hs = round(size * 0.86)
            rows = []
            for i, L in enumerate(lines):
                if i == hl:
                    fS = K.fnt("anton", hs * SS)
                    l, tt, r, bb = fS.getbbox(L, anchor="ls")
                    top = max(cap_h("anton", hs), -tt / SS)
                    rows.append(("label", L, hs, N.label_w(L, hs) + 24, top + max(0.0, bb / SS) + 2 * hs * 0.16, top))
                else:
                    l, tt, r, bb = K.tbox(L, "anton", size)
                    rows.append(("text", L, size, K.tw(L, "anton", size), -tt + max(0.0, bb), -tt))
            gap = size * 0.18
            total = sum(r[4] for r in rows) + gap * (len(rows) - 1)
            if all(r[3] <= X1 - X0 for r in rows) and total <= max_h:
                break
        y = LEVHA[1] - 4
        for kind, L, size, w, h, top in rows:
            if kind == "label":
                etiket(pen, L, size, OFF, RED, 703, X0 + (w - 24) / 2 + 4, y + h / 2, rot=-1.5,
                       shadow=(9, 11, 0, 0.95))
            else:
                pen.text(X0, y + top, L, "anton", size, OFF)
            y += h + gap
        return y - gap

    # ------------------------------------------------------------ makine bölgesi
    def cizim(self, path: Path, w: float, h: float) -> Image.Image:
        """Çizimi (şeffaf PNG) saydam kenarlarından kırpıp w x h kutuya sığdırır (2x)."""
        key = ("cizim", str(path), round(w), round(h))
        if key not in self._lay:
            im = Image.open(path).convert("RGBA")
            bb = im.getchannel("A").getbbox()
            if bb:
                im = im.crop(bb)
            k = min(w / im.width, h / im.height)
            self._lay[key] = im.resize((max(1, int(im.width * k * SS)), max(1, int(im.height * k * SS))),
                                       Image.LANCZOS)
        return self._lay[key]

    def gorsel(self, pen: K.Pen, seg, area) -> None:
        """Bölümün görselini alana koyar: çizim, yoksa fotoğraf (künye çipiyle), yoksa genel sanayi presi."""
        ax0, ay0, ax1, ay1 = area
        if seg.sprite is not None:
            d = self.cizim(seg.sprite, ax1 - ax0, ay1 - ay0)
        elif seg.image is not None:
            src = Image.open(seg.image).convert("RGB")
            im = K.cover(src, int((ax1 - ax0) * SS), int((ay1 - ay0) * SS)).convert("RGBA")
            mask = Image.new("L", im.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], 14 * SS, fill=255)
            im.putalpha(mask)
            pen.paste(im, ax0, ay0)
            pen.rr((ax0, ay0, ax1, ay1), 14, outline=INK, width=4)
            note = K.credit_chip(seg.credit)
            if note:
                K.chip_label(pen, ax0 + 14, ay1 - 70, note, max_w=ax1 - ax0 - 30)
            return
        else:
            vb = MAKINE_VB
            k = min((ax1 - ax0) / vb[2], (ay1 - ay0) / vb[3])
            d = K.svg_img(makine_svg(), vb, vb[2] * k * SS, vb[3] * k * SS)
        dw, dh = d.width / SS, d.height / SS
        dx, dy = (ax0 + ax1) / 2 - dw / 2, (ay0 + ay1) / 2 - dh / 2
        pen.paste(d, dx, dy)

    def not_etiketi(self, ci: int, text: str, area, seed: int):
        """Not etiketi (yırtık, çizime yapıştırılmış): 0. not sağ üstte kırmızı, 1. not sol üstte sarı. Çizime çizgiyle
        bağlanmaz: en yakın nokta çoğu zaman yanlış parçayı (ör. köprüyü) gösteriyordu."""
        ax0, ay0, ax1, ay1 = area
        size = self.not_boyu(text, area)
        lw = N.label_w(text, size)
        pen = K.Pen(*self.icerik)
        if ci == 0:
            cx, cy, renk, yazi, rim, rot = ax1 - lw / 2 - 4, ay0 + 28, RED, OFF, OFF, -2.0
        else:
            cx, cy, renk, yazi, rim, rot = ax0 + lw / 2 + 4, ay0 + 28, YELLOW, INK, INK, 1.5
        etiket(pen, text, size, yazi, renk, 711 + seed + ci, cx, cy, rot=rot, shadow=(5, 6, 0, 0.9), rim=rim)
        im = pen.done()
        bb = im.getchannel("A").getbbox()
        if not bb:
            return None
        return im.crop(bb), (self.icerik[0] + bb[0], self.icerik[1] + bb[1])

    @staticmethod
    def not_boyu(text: str, area) -> int:
        size = 40
        while size > 26 and N.label_w(text, size) > (area[2] - area[0]) * 0.46:
            size -= 2
        return size

    def gorsel_alani(self, seg, ic) -> tuple:
        """Görselin alanı: notlar varsa ve tam boy çizim notların köşelerine uzanıyorsa üstte not şeridi ayrılır;
        çizim dar kalıyorsa (yüksekliğe sığan geniş olmayan çizim) notlar boş köşelere oturur, çizim küçülmez."""
        callouts = seg.callouts[:2] if seg.kind == "step" else []
        tam = (ic[0] + 8, ic[1], ic[2] - 8, ic[3])
        if not callouts:
            return tam
        genis = max(N.label_w(c, self.not_boyu(c, ic)) for c in callouts) + 16
        if seg.sprite is not None:
            im = Image.open(seg.sprite)
            bb = im.getchannel("A").getbbox() if im.mode in ("RGBA", "LA") else None
            w, h = (bb[2] - bb[0], bb[3] - bb[1]) if bb else im.size
            k = min((tam[2] - tam[0]) / w, (tam[3] - tam[1]) / h)
            dw = w * k
            serbest = ((tam[2] - tam[0]) - dw) / 2
            if serbest >= genis:
                return tam
        return (ic[0] + 8, ic[1] + 64, ic[2] - 8, ic[3])

    def icerik_katmani(self, seg):
        """(levha + başlık + makine bölgesi katmanı, [not katmanları], bölge kutusu) — bölüm başına bir kez."""
        key = ("icerik", seg.scenes[0])
        if key in self._lay:
            return self._lay[key]
        pen = K.Pen(*self.icerik)
        notlar = []
        if seg.kind == "hook":
            y = self.kanca_basligi(pen, seg)
            zb = (X0, max(BOLGE_Y0, y + 34), X1, self.bolge_y1)
        else:
            if seg.kind != "recap":   # ölçekte levha ve başlık ayrı katmanda (soru gelince değişir: ust_katman)
                self.levha(pen, seg)
                self.baslik(pen, seg.title or [self.urun])
            zb = (X0, BOLGE_Y0, X1, self.bolge_y1)
        bolge(pen, zb, seed=4 + seg.number)
        ic = (zb[0] + BANT + 18, zb[1] + BANT + 14, zb[2] - BANT - 18, zb[3] - BANT - 14)
        if seg.kind == "recap":
            self.olcek(pen, ic, zb)
        else:
            callouts = seg.callouts if seg.kind == "step" else []
            self.gorsel(pen, seg, self.gorsel_alani(seg, ic))
            for ci, text in enumerate(callouts[:2]):
                c = self.not_etiketi(ci, text, ic, seg.number)
                if c:
                    notlar.append(c)
        out = (pen.done(), notlar, zb)
        self._lay[key] = out
        return out

    # ------------------------------------------------------------ ölçek: gösterge + tek büyük sayı
    def gosterge_yeri(self, ic) -> tuple[float, float, float]:
        ix0, iy0, ix1, iy1 = ic
        R = min(150.0, (iy1 - iy0) / 2 - 30, (ix1 - ix0) * 0.22)
        return ix0 + R + 30, (iy0 + iy1) / 2, R

    def anlik_hiz(self) -> dict | None:
        """Göstergenin değeri: saniyedeki üretim (1'den azsa dakikadaki, saatteki ya da gündeki). Dönmüş sözlük: deger,
        donem ('SANİYE'), metin ('≈444'), vmax (kadranın en büyük rakamı), adim (rakamlar arası). Hız yoksa None."""
        if not self.hiz:
            return None
        if "anlik" not in self._q:
            hiz, ad = self.hiz["hiz"], "SANİYE"
            for ad, sn in DONEMLER[:4]:
                if hiz * sn >= 1:
                    hiz *= sn
                    break
            else:
                hiz *= DONEMLER[3][1]
            metin = binlik(round(hiz)) if hiz >= 10 else f"{hiz:.1f}".replace(".", ",").replace(",0", "")
            yaklasik = "≈" if (self.hiz["sayi"].startswith("≈") or abs(hiz - round(hiz)) > 1e-6) else ""
            # kadran: 5 eşit aralık, ibre değerin %70-85'ine oturur (sarı bölge)
            hedef = hiz * 1.2 / 5
            us = 10 ** math.floor(math.log10(hedef)) if hedef > 0 else 1
            adim = next((m * us for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10) if m * us >= hedef), 10 * us)
            self._q["anlik"] = {"deger": hiz, "donem": ad, "metin": yaklasik + metin, "vmax": adim * 5, "adim": adim}
        return self._q["anlik"]

    def olcek(self, pen: K.Pen, ic, zb) -> None:
        gx, gy, R = self.gosterge_yeri(ic)
        m = 34
        vb = (-R - m, -R - m, 2 * (R + m), 2 * (R + m))
        pen.svg(kadran_svg(R, [(0, 55, (205, 225, 210)), (55, 80, YELLOW), (80, 100, RED)]), vb, gx - R - m,
                gy - R - m, 2 * (R + m))
        ah = self.anlik_hiz()
        if ah:
            # kadran rakamları (0 ... vmax) ve ibrenin altında saniyedeki üretim çipi
            rs = max(16, R * 0.15)
            for k in range(6):
                v = k * 20
                a = _ac(v, 100)
                r = R - 60 - (8 if k in (0, 5) else 0)     # alttaki iki rakam çipe değmesin
                deger = ah["adim"] * k
                t = binlik(round(deger)) if deger >= 10 or deger == int(deger) else f"{deger:.1f}".replace(".", ",")
                pen.text(gx + r * math.cos(a), gy + r * math.sin(a) + cap_h("anton", rs) / 2, t, "anton", rs, INK,
                         anchor="ms")
            cs = max(20, R * 0.2)
            cw = K.tw(ah["metin"], "anton", cs) + 22
            cy0 = gy + R * 0.5
            pen.rr((gx - cw / 2, cy0, gx + cw / 2, cy0 + cs * 1.2), 8, fill=INK)
            pen.text(gx, cy0 + cs * 0.6 + cap_h("anton", cs) / 2, ah["metin"], "anton", cs, OFF, anchor="ms")
        else:
            pen.text(gx, gy + R * 0.46, "ÜRETİM HIZI", "courier", max(16, R * 0.13), DGREY, anchor="ms")
        rx = gx + R + 56
        room = ic[2] - rx
        if self.hiz:
            ust = " · ".join(x for x in (self.hiz["yer"], self.hiz["donem"]) if x)
            sayi, isim = self.hiz["sayi"], self.hiz["isim"]
        else:
            ust, sayi, isim = "ÜRETİM", self.urun, "TAMAMLANDI"
        # yorum çıkartması bölgenin sağ alt köşesine gelir: sayı bloğu onun üstünde kalır
        alt = ic[3]
        if self.recap_cta(self.segs[-1]) is not None:
            st = self.cta_cikartmasi(zb)
            alt = min(alt, self.cta_merkezi(zb)[1] - st.height / 2 - 6)
        for olc in (1.0, 0.9, 0.8, 0.7, 0.6):
            us = int(46 * olc)
            while us > 24 and K.tw(ust, "anton", us) > room:
                us -= 2
            ss = int(128 * olc)
            while ss > 40 and K.tw(sayi, "anton", ss) > room:
                ss -= 4
            isz = int(58 * olc)
            while isz > 26 and N.label_w(isim, isz) > room:
                isz -= 2
            h_ust, h_sayi = cap_h("anton", us), cap_h("anton", ss)
            h_isim = cap_h("anton", isz) * 1.5
            ara1, ara2 = 22 * olc, 30 * olc
            blok = h_ust + ara1 + h_sayi + ara2 + h_isim
            if blok <= alt - ic[1] - 8:
                break
        sayi = K.fit_words(sayi, "anton", ss, room)
        y = max(ic[1] + 4, min(gy - blok / 2, alt - blok - 4))
        pen.text(rx, y + h_ust, ust, "anton", us, INK)
        y += h_ust + ara1
        pen.text(rx, y + h_sayi, sayi, "anton", ss, INK)
        y += h_sayi + ara2
        etiket(pen, isim, isz, INK, YELLOW, 51, rx + N.label_w(isim, isz) / 2, y + h_isim / 2, rot=-1.5,
               shadow=(5, 6, 0, 0.9), rim=INK)

    def soru_metni(self, seg) -> tuple[int, list[str]] | None:
        """Ölçek sahnesindeki soru cümlesi: (ilk kelimesinin indeksi, iki satır BÜYÜK HARF). Soru yoksa None."""
        key = ("soru_metni", seg.scenes[0])
        if key not in self._q:
            out = None
            ilk = next(iter(self.soru_kirilimi(seg)), None)
            if ilk is not None:
                ws = []
                for i in range(ilk, seg.b):
                    ws.append(self.words[i].text.strip('"“”«»'))
                    if self.words[i].text.rstrip('"“”»)’\'').endswith("?"):
                        break
                ws = [up(w) for w in ws if w]
                if len(ws) > 1:   # en geniş satırı en kısa yapan kırılım (ikinci satır etikette, biraz daha geniş)
                    k = min(range(1, len(ws)), key=lambda j: max(K.tw(" ".join(ws[:j]), "anton", 100),
                                                                 N.label_w(" ".join(ws[j:]), 86) + 24))
                    out = (ilk, [" ".join(ws[:k]), " ".join(ws[k:])])
                elif ws:
                    out = (ilk, ws)
            self._q[key] = out
        return self._q[key]

    def ust_katman(self, seg, soru: bool) -> Image.Image:
        """Ölçekte levhanın satırı: ÜRETİM HIZI levhası + saniyedeki üretim; soru söylenince sorunun büyük başlığı."""
        key = ("ust_katman", seg.scenes[0], soru)
        if key not in self._lay:
            pen = K.Pen(*self.icerik)
            sm = self.soru_metni(seg) if soru else None
            if sm:
                lines = sm[1]
                self.buyuk_baslik(pen, lines, len(lines) - 1, BOLGE_Y0 - 18 - (LEVHA[1] - 4), en_kucuk=36)
            else:
                self.levha(pen, seg)
                ah = self.anlik_hiz()
                if ah:
                    yer = self.hiz["yer"]
                    self.baslik(pen, [f"{yer} HER {ah['donem']}".strip(), f"{ah['metin']} {self.hiz['isim']}"],
                                renkler=(OFF, YELLOW))
                else:
                    self.baslik(pen, seg.title or [self.urun])
            self._lay[key] = pen.done()
        return self._lay[key]

    def cta_cikartmasi(self, zb) -> Image.Image:
        """YORUMLARA YAZ çıkartması: göstergenin sağındaki sütuna sığacak boyda."""
        if "cta" not in self._lay:
            ic = (zb[0] + BANT + 18, zb[1] + BANT + 14, zb[2] - BANT - 18, zb[3] - BANT - 14)
            gx, gy, R = self.gosterge_yeri(ic)
            self._lay["cta"] = K.cta_sticker(up(K.CtaCard.BUTTON), X1 - (gx + R + 62), size=60)
        return self._lay["cta"]

    def cta_merkezi(self, zb) -> tuple[float, float]:
        st = self.cta_cikartmasi(zb)
        return X1 + 4 - st.width / 2, zb[3] - 6

    def ibre(self, img: Image.Image, seg, lt: float) -> None:
        _, _, zb = self.icerik_katmani(seg)
        ic = (zb[0] + BANT + 18, zb[1] + BANT + 14, zb[2] - BANT - 18, zb[3] - BANT - 14)
        gx, gy, R = self.gosterge_yeri(ic)
        p = (lt - SLIDE0 - SLIDE) / 1.3
        ah = self.anlik_hiz()
        hedef = min(96.0, 100.0 * ah["deger"] / ah["vmax"]) if ah else 86.0
        if p <= 0:
            v = 0.0
        elif p < 1:
            v = hedef * K.ease_out_back(p, 1.25)
        else:
            v = hedef + 1.6 * math.sin(lt * 9.0) + 0.8 * math.sin(lt * 23.0)
        v = max(0.0, min(99.0, v))
        key = ("ibre", round(v * 2) / 2, round(R))
        im = self._lay.get(key)
        if im is None:
            m = 34
            vb = (-R - m, -R - m, 2 * (R + m), 2 * (R + m))
            s = K.svg_img(ibre_svg(R, round(v * 2) / 2), vb, vb[2] * SS, vb[3] * SS)
            im = s.resize((int(vb[2]), int(vb[3])), Image.LANCZOS)
            self._lay[key] = im
        K.put(img, im, gx - R - 34, gy - R - 34, clip=CLIP)

    # ------------------------------------------------------------ iş emri
    def fis_taban(self) -> Image.Image:
        """İş emrinin değişmeyen kısmı: kâğıt, tırtıl delikleri, bantlar, başlık şeridi, ÜRÜN, ONAY kutusu, ayraçlar."""
        if "fis" in self._lay:
            return self._lay["fis"]
        o = self.olcu
        y0, kx0, kx1 = o["y0"], o["kx0"], o["kx1"]
        pen = K.Pen(FIS_X0 - 4, y0 - 4, FIS_X1 + 16, FIS_Y1 + 12)
        pen.rr((FIS_X0 + 10, y0 + 12, FIS_X1 + 10, FIS_Y1 + 10), 8, fill=INK)
        pen.rr((FIS_X0, y0, FIS_X1, FIS_Y1), 8, fill=FORM, outline=INK, width=5)
        y, k = o["ayrac1"] + 6, 0
        while y < FIS_Y1 - 6:
            if k % 2 == 0:
                pen.rr((kx0, y, kx1, min(y + 54, FIS_Y1 - 6)), 0, fill=FORM_BANT)
            y += 54
            k += 1
        for xx in (kx0, kx1):
            yy = y0 + 8
            while yy < FIS_Y1 - 8:
                pen.line([(xx, yy), (xx, min(yy + 6, FIS_Y1 - 8))], (196, 192, 182), 2)
                yy += 11
        for xx in (FIS_X0 + 18, FIS_X1 - 18):
            yy = y0 + 22
            while yy < FIS_Y1 - 12:
                pen.ell(xx, yy, 7, fill=(38, 39, 41))
                yy += 31
        # başlık şeridi: düz Anton (şablon köprüsü yok: "İŞ EMRİ" her harfiyle okunur)
        sx0, sy0, sx1, sy1 = o["serit"]
        pen.rr((sx0, sy0, sx1, sy1), 4, fill=INK)
        hs = 44
        base = (sy0 + sy1) / 2 + cap_h("anton", hs) / 2 + 2
        pen.text(sx0 + 18, base, "İŞ EMRİ", "anton", hs, YELLOW)
        no = f"No. {self.no}"
        pen.text(sx1 - 16, base - 3, no, "courier", 30, OFF, anchor="rs")
        # ürün satırı
        lab = "ÜRÜN:"
        pen.text(sx0 + 4, o["urun_y"], lab, "courier", 26, DGREY)
        ux = sx0 + 4 + K.tw(lab, "courier", 26) + 12
        us = 34
        room = sx1 - ux
        while us > 24 and K.tw(self.urun, "anton", us) > room:
            us -= 2
        pen.text(ux, o["urun_y"] + 2, K.fit_words(self.urun, "anton", us, room), "anton", us, INK)
        # ONAY kutusu
        ox0, oy0, ox1, oy1 = o["onay"]
        pen.rr((ox0, oy0, ox1, oy1), 4, fill=FORM, outline=INK, width=3)
        lw_ = K.tw("ONAY", "courier", 24)
        pen.rr((ox0 + 12, oy0 - 12, ox0 + 24 + lw_, oy0 + 6), 0, fill=FORM)
        pen.text(ox0 + 18, oy0 + 6, "ONAY", "courier", 24, DGREY)
        for yy in (o["ayrac1"], o["ayrac2"]):
            x = kx0 + 10
            while x < kx1 - 10:
                pen.line([(x, yy), (min(x + 12, kx1 - 10), yy)], (150, 146, 138), 2)
                x += 20
        self._lay["fis"] = pen.done()
        return self._lay["fis"]

    def satir_yeri(self, k: int) -> tuple[float, float, float]:
        """k. aşama satırının kutu x'i, satırın ortası ve yazı genişliği."""
        o = self.olcu
        r, c = (k, 0) if o["sut"] == 1 else divmod(k, 2)
        colw = (o["kx1"] - o["kx0"] - 20) / o["sut"]
        bx = o["kx0"] + 12 + c * colw
        cy = o["liste_y0"] + r * o["rh"] + o["rh"] / 2
        return bx, cy, colw - 50

    def satir(self, k: int, durum: str) -> tuple[Image.Image, tuple[float, float]]:
        """Aşama satırı (kutu + '2 · UÇLAR PİŞİRİLİR'): sira soluk, simdi sarı fosforlu ve kırmızı ▶, bitti mürekkep."""
        key = ("satir", k, durum)
        if key in self._lay:
            return self._lay[key]
        bx, cy, room = self.satir_yeri(k)
        rh = self.olcu["rh"]
        bs = min(34, rh - 12)
        pen = K.Pen(bx - 4, cy - rh / 2, bx + room + 50, cy + rh / 2)
        lab = f"{k + 1} · " + " ".join(self.steps[k].title)
        lx = bx + bs + 12
        ls = 34 if rh >= 44 else 28
        while ls > 24 and K.tw(lab, "anton", ls) > room - (lx - bx) + 40:
            ls -= 2
        lab = K.fit_words(lab, "anton", ls, room - (lx - bx) + 40)
        if durum == "simdi":
            pen.rr((lx - 6, cy - rh / 2 + 5, lx + K.tw(lab, "anton", ls) + 8, cy + rh / 2 - 5), 3, fill=FOSFOR)
        pen.rr((bx, cy - bs / 2, bx + bs, cy + bs / 2), 4, fill=OFF, outline=(SOLUK if durum == "sira" else INK),
               width=3.5)
        if durum == "simdi":
            pen.poly([(bx + 9, cy - 9), (bx + 9, cy + 9), (bx + 25, cy)], RED)
        pen.text(lx, cy + cap_h("anton", ls) / 2, lab, "anton", ls, INK if durum != "sira" else SOLUK)
        out = (pen.done(), (bx - 4, cy - rh / 2))
        self._lay[key] = out
        return out

    def durumlar(self, t: float) -> list[str]:
        """Her aşamanın iş emrindeki durumu: sira (henüz gelmedi), simdi (anlatılıyor), bitti (tik atıldı)."""
        out = []
        for k, st in enumerate(self.steps):
            son = self.bitis(k)
            out.append("bitti" if son is not None and t >= son else ("simdi" if st.start <= t else "sira"))
        return out

    def fis(self, img: Image.Image, t: float, si: int) -> None:
        K.put(img, self.fis_taban(), FIS_X0 - 4, self.olcu["y0"] - 4, clip=CLIP)
        seg = self.segs[si]
        bs = min(34, self.olcu["rh"] - 12)
        for k, durum in enumerate(self.durumlar(t)):
            son = self.bitis(k)
            im, (x, y) = self.satir(k, durum)
            K.put(img, im, x, y, clip=CLIP)
            if durum == "bitti":
                bx, cy, _ = self.satir_yeri(k)
                s = bs * 1.5
                K.put(img, tik_img(s, (t - son) / TIK), bx - bs * 0.22, cy - bs / 2 - s * 0.42, clip=CLIP)
        recap = self.segs[-1] if self.segs[-1].kind == "recap" else None
        ka = self.kapanis_ani()
        if recap is not None and t >= recap.start + ONAY0 and (ka is None or t < ka):
            ox0, oy0, ox1, oy1 = self.olcu["onay"]
            im = self._lay.get("tamam")
            if im is None:
                im = self._lay["tamam"] = muhur_img(["TAMAM"], 34, YESIL, rot=-9, seed=5)
            ps = (t - recap.start - ONAY0) / 0.16
            k = K.lerp(1.7, 1.0, K.ease_out_cubic(ps)) if ps < 1 else 1.0
            K.put(img, im, (ox0 + ox1) / 2 - im.width / 2, (oy0 + oy1) / 2 + 4 - im.height / 2, k=k,
                  alpha=min(1.0, ps * 3), clip=CLIP)
        self.speech(seg).put(img, self.cur_word(t, seg) if not self.cta_okunuyor(seg, t) else self.speech(seg).b)
        if ka is not None and t >= ka:     # ONAY kutusundaki TAMAM, KAPANDI mührüne döner (listeye binmez)
            ox0, oy0, ox1, oy1 = self.olcu["onay"]
            im = self._lay.get("kapandi")
            if im is None:
                ms = 34
                while ms > 18 and K.tw("KAPANDI", "anton", ms) + ms * 0.76 + 16 > ox1 - ox0 - 6:
                    ms -= 2
                im = self._lay["kapandi"] = muhur_img(["KAPANDI"], ms, YESIL, rot=-9, seed=9, alpha=1.0,
                                                          dolu=True)
            cx, cy = (ox0 + ox1) / 2, (oy0 + oy1) / 2 + 4
            ps = (t - ka) / 0.18
            k = K.lerp(1.9, 1.0, K.ease_out_cubic(ps)) if ps < 1 else 1.0
            K.put(img, im, cx - im.width / 2, cy - im.height / 2, k=k, alpha=min(1.0, ps * 3), clip=CLIP)

    # ------------------------------------------------------------ dış ses
    def recap_cta(self, seg) -> int | None:
        """Sondaki 'Yorumlara yaz' çağrısının ilk kelimesi (en çok 4 kelimelik kuyruk); yoksa None."""
        key = ("cta", seg.scenes[0])
        if key not in self._q:
            out = None
            for i in range(max(seg.a, seg.b - 4), seg.b):
                if Q_RE.match(" ".join(self.words[j].text for j in range(i, seg.b))):
                    out = i
                    break
            self._q[key] = out
        return self._q[key]

    def soru_kirilimi(self, seg) -> set[int]:
        """Ölçek sahnesinde soru cümlesinin ilk kelimesi: soru kâğıtta yeni sayfadan başlar."""
        key = ("soru", seg.scenes[0])
        if key not in self._q:
            out, sent = set(), []
            for i in range(seg.a, seg.b):
                sent.append(i)
                t = self.words[i].text.rstrip('"“”»)’\'')
                if t[-1:] in ".?!…":
                    if t.endswith("?"):
                        out.add(sent[0])
                        break
                    sent = []
            self._q[key] = out
        return self._q[key]

    def cta_okunuyor(self, seg, t: float) -> bool:
        if seg.kind != "recap":
            return False
        cta = self.recap_cta(seg)
        return cta is not None and t >= self.words[cta].start - 0.08

    def speech(self, seg) -> FisAnlati:
        key = seg.scenes[0]
        if key not in self._speech:
            b = seg.b
            breaks = set()
            if seg.kind == "recap":     # sondaki yorum çağrısı kâğıda değil çıkartmaya yazılır
                cta = self.recap_cta(seg)
                b = cta if cta is not None and cta > seg.a else seg.b
                breaks = {i for i in self.soru_kirilimi(seg) if i < b}
            self._speech[key] = FisAnlati(self.words, seg.a, b, self.olcu["anlati"], sizes=ANLATI_BOY,
                                          max_lines=ANLATI_SATIR, lh=ANLATI_LH, breaks=breaks)
        return self._speech[key]

    # ------------------------------------------------------------ Makas
    def draw_makas(self, img: Image.Image, t: float, si: int, lt: float) -> None:
        seg = self.segs[si]
        cx, cy, sc = MAKAS
        mood = seg.mascot if seg.mascot in K.MOODS else RUH[seg.kind]
        ka = self.kapanis_ani()
        if ka is not None and t >= ka:
            mood = "happy"
        mouth = K.talk_state(self.words, self.starts, t)
        blink = (t % 3.6) > 3.45 and mood not in ("happy", "surprised")
        hop = -18 * math.sin(math.pi * K.clamp(lt / 0.32)) if si > 0 and lt < 0.32 else 0.0
        bob = round(3 * math.sin(t * 2 * math.pi * 0.55))
        point, L = MAKAS_KOL
        im = self.makas.sprite(mood, mouth, blink, point, L, sc)
        ox, oy = Makas.origin(cx, cy, sc)
        K.put(img, im, ox, oy + bob + hop, clip=CLIP)

    # ------------------------------------------------------------ içerik (levha + bölge) ve geçişler
    def draw_icerik(self, img: Image.Image, seg, si: int, lt: float) -> None:
        base, notlar, _ = self.icerik_katmani(seg)
        ox, oy = self.icerik[:2]
        enter = si > 0
        clip = (0, self.icerik[1], SAFE[2], self.icerik[3])
        if not enter:
            k = 1 + 0.02 * math.sin(math.pi * K.clamp(lt / 0.5)) if lt < 0.5 else 1.0
            K.put(img, base, ox, oy, k=k, clip=clip)
            if seg.kind == "recap":
                self.ust_ciz(img, seg, lt, 0.0, clip)
            for im, (x, y) in notlar:
                K.put(img, im, x, y, clip=clip)
            return
        p = (lt - SLIDE0) / SLIDE
        if p <= 0:
            return
        dx = (1 - K.ease_out_back(p, 1.2)) * 960
        lay = N.feather_right(base, ox + dx, strength=K.clamp(dx / 40)) if dx > 0.5 else base
        K.put(img, lay, ox + dx, oy, clip=clip)
        if seg.kind == "recap":
            self.ust_ciz(img, seg, lt, dx, clip)
            self.ibre(img, seg, lt)
        for j, (im, (x, y)) in enumerate(notlar):
            pc = (lt - NOTE0 - 0.2 * j) / 0.26
            if pc > 0:
                K.put(img, im, x + dx, y, k=N.ease_pop(pc, 1.14), clip=clip)

    def ust_ciz(self, img: Image.Image, seg, lt: float, dx: float, clip) -> None:
        """Ölçekte levha satırı: soru söylenene kadar ÜRETİM HIZI levhası, sonra sorunun büyük başlığı (patlayarak)."""
        ox, oy = self.icerik[:2]
        sm = self.soru_metni(seg)
        ts = (self.words[sm[0]].start - 0.06 - seg.start) if sm else None
        if ts is None or lt < ts:
            lay = self.ust_katman(seg, False)
            if dx > 0.5:
                lay = N.feather_right(lay, ox + dx, strength=K.clamp(dx / 40))
            K.put(img, lay, ox + dx, oy, clip=clip)
            return
        k = N.ease_pop((lt - ts) / 0.28, 1.08) if lt - ts < 0.28 else 1.0
        K.put(img, self.ust_katman(seg, True), ox + dx, oy, k=k, clip=clip, anchor=(0.1, 0.12))

    def cta(self, img: Image.Image, seg, t: float) -> None:
        """'Yorumlara yaz' söylenince makine bölgesinin sağ alt köşesinde (sayı bloğunun altında, göstergeye binmeden)
        YORUMLARA YAZ çıkartması."""
        if seg.kind != "recap":
            return
        cta = self.recap_cta(seg)
        if cta is None:
            return
        cs = self.words[cta].start - 0.08
        if t < cs:
            return
        _, _, zb = self.icerik_katmani(seg)
        st = self.cta_cikartmasi(zb)
        cx, cy = self.cta_merkezi(zb)
        kk = N.ease_pop((t - cs) / 0.28, 1.15) * K.cta_pulse(t - cs)
        K.put(img, st, cx - st.width / 2, cy - st.height / 2, k=kk, clip=CLIP, anchor=(0.7, 0.5))

    def kesme_cizgisi(self, img: Image.Image, t: float) -> None:
        """Açılış: makas, sayaç satırının altındaki kesik çizgiyi soldan sağa keser; sonra çizgi yerinde kalır."""
        if "cizgi" not in self._lay:
            pen = K.Pen(X0 - 4, KES_Y - 6, X1 + 4, KES_Y + 6)
            N.dashed(pen, X0, KES_Y, X1, (112, 114, 118), dash=16, gap=10, w=3)
            self._lay["cizgi"] = pen.done()
        lay = self._lay["cizgi"]
        if self.intro and t < 0.8:
            x = K.lerp(X0, X1, K.ease_in_out(t / 0.8))
            if x > X0:
                K.put(img, lay.crop((0, 0, int(x - X0 + 4), lay.height)), X0 - 4, KES_Y - 6)
            sc = K.scissors_icon(64, 32 if int(t * 24) % 2 else 12)
            K.put(img, sc, x - 64 * 58 / 124, KES_Y - sc.height / 2)
        else:
            K.put(img, lay, X0 - 4, KES_Y - 6)

    def frame(self, t: float, grain: bool = True) -> Image.Image:
        si = self.seg_at(t)
        seg = self.segs[si]
        lt = t - seg.start
        img = sac_zemin().copy()
        lay, _ = self.ust()
        K.put(img, lay, UST[0], UST[1], clip=CLIP)
        self.sayac(img, t)
        self.kesme_cizgisi(img, t)
        if si > 0 and lt < CUT:              # önceki bölümün levhası ve bölgesi makasla kesilir
            old_seg = self.segs[si - 1]
            old, notlar, zb = self.icerik_katmani(old_seg)
            if notlar:
                old = old.copy()
                for im, (x, y) in notlar:
                    K._comp(old, im, x - self.icerik[0], y - self.icerik[1])
            alt = (0, ICERIK_Y0, SAFE[2], self.icerik[3])
            K.card_cut(img, old, lt, si, origin=self.icerik[:2], card=(zb[0], LEVHA[1], zb[2], zb[3]),
                       x_end=SAFE[2] - 66, clip_top=alt, clips_bot=(alt,))
        self.draw_icerik(img, seg, si, lt)
        if seg.kind == "recap" and si == 0:
            self.ibre(img, seg, lt + SLIDE0 + SLIDE + 1.3)
        self.fis(img, t, si)
        self.cta(img, seg, t)
        self.draw_makas(img, t, si, lt)
        if self.brand is not None and self.brand.on:
            self.brand.watermark(img, t, 0.8 if self.intro else 0.0)
        return K.finish(img) if grain else img.convert("RGB")


# ---------------------------------------------------------------- ana giriş
def render(scenes: list[SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
           music: Path | None, meta: dict) -> Path:
    """İş Emri şablonuyla videoyu kurar. Kare döngüsü, ses, kuyruk ve marka kapanışı kart şablonuyla ortak
    (kart.render_frames)."""
    return K.render_frames(scenes, words, out_mp4, voice_mp3, music,
                           lambda bcfg: IsEmriVideo(scenes, words, meta, bcfg), "İş Emri")
