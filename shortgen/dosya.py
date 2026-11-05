"""Dava Dosyası şablonu ("Efsane mi, Gerçek mi?" serisi, efsane kalıbı): koyu masada manila bir dava dosyası.

İnanış dosyanın kapağındaki İDDİA fişine yazılır; deliller dosyanın içine sahne sahne eklenir (tanık ifadesi, delil
torbasında fotoğraf, şerit metreli ölçüm, iğneli çizim); sonda dosya kapanır, kırmızı lastik damga "HÜKÜM: EFSANE"
(GERÇEK / KISMEN DOĞRU) diye fişin üstüne iner ve dosya kısa bir an sarsılır; son soru SENCE? ve YORUMLARA YAZ olur.
Dış ses dosyanın altındaki daktilo TUTANAK şeridine kelime kelime yazılır: ayrı altyazı yoktur.

Ekran düzeni (1080x1920). Yazı yalnız x 72-920, y 176-1536 arasında; gölgeler dahil hiçbir içerik platform arayüzüne
(sağdaki düğmeler x > 935, üst çubuk y < 170, alttaki açıklama y > 1540) taşmaz. Masa ve dosyanın kenarları taşabilir:
  184-262   masa: filigran (sekmenin solunda/sağında, brand.json'daki sürede yer değiştirir) · sekme "DOSYA NO. 04"
  286-440   kapak: seri etiketi, KONU / TARİH · iç sayfa: DELİL 2/4 ve numaralı delil işaretleri
  380-1250  sayfanın belgesi: İDDİA fişi, iddia kaydı, tanık ifadesi, ölçüm, delil torbası, iğneli çizim; hükümde
            damgalı fiş ve GERÇEK şeridi
  1100-1330 Makas (belgeyi gösterir); kapakta delil işaretleri sırası
  1340-1528 TUTANAK: dış ses daktiloyla yazılır (okunan kelime sarı, sonda kırmızı imleç; en çok iki satır, eski satır
            yukarı kayar); kenarında makas@bilgimakasi sekmesi
Dosya kartonu manila/zeytin tonludur: Nasıl üretiliyor? şablonunun (uretim) kraft zemininden ayrı okunur.

Senaryo eşlemesi (plan): ilk sahne kapaktır (İDDİA fişi). Kart alanları kart şablonundakiyle aynıdır (kart.card_type):
compare sahnesi iddia kaydı sayfasıdır (card_myth İDDİA fişindeki inanış, card_fact BULGU satırı), interstitial ara
sayfadır (YENİ BULGU), quote tanık ifadesi (card_label alıntı, card_note 'Kim · nerede · yıl'), counter ölçüm (şerit
metre değere kadar açılır), photo delil torbası (künye çipi korunur), drawing iğneli çizimdir. Sahnenin delil numarası
Scene.delil'dir (aynı numaralı devam sahnesi yeni belge getirmezse aynı sayfada kalır); numara hiç yoksa kendi belgesi
olan her sahne yeni delildir, ama cümlenin ortasından başlayan sahne önceki delilin ikinci belgesidir. Son delilden
sonraki sahneler (en çok son üç) hükümdür. Hüküm ShortScript.hukum'dur; boşsa compare kartı varsa EFSANE, yoksa
tarafsız "DOSYA KAPANDI" damgası basılır. Dosya numarası ilk sahnenin seri etiketinden ('EFSANE Mİ, GERÇEK Mİ? #4'),
yoksa 01.

Geçişler: kapaktan içeri geçerken kapak soldaki menteşesinin üstüne kapanarak (yatayda daralarak) açılır; iç sayfalar
arasında eski belge kart şablonunun makas kesmesiyle (kart.card_cut) kesilir, yeni belge masaya bırakılır gibi oturur;
hükümde kapak geri kapanır ve damga iner. Hız: masa, dosya, sayfaların durağan hâli, tutanak satırları ve maskot
önbelleğe alınır; kare başına yalnız katmanlar birleştirilir.
"""
from __future__ import annotations

import bisect
import datetime as dt
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import kart as K
from .render import SceneSpec
from .nasil import Mascot, bump, ease_pop
from .script import STRUCTURES
from .voice import Word

W, H, FPS, SS = K.W, K.H, K.FPS, K.SS
RED, YELLOW, INK, OFF, WHITE, DGREY = K.RED, K.YELLOW, K.INK, K.OFF, K.WHITE, K.DGREY
X0, X1 = 72, 920                           # yazı alanı
SAFE = K.SAFE                              # (0, 170, 935, 1540)
CLIP = (0, SAFE[1], SAFE[2], SAFE[3])

# ---------------------------------------------------------------- renkler: manila/zeytin karton, kırık beyaz fişler
MANILA = (206, 187, 122)                   # kapak
MANILA_IC = (224, 210, 154)                # dosyanın içi (biraz daha açık)
MANILA_DK = (140, 122, 66)                 # kenar, baskı, kesik çizgiler
LIF = ((128, 110, 56, 96), (242, 232, 192, 120))  # karton lifleri (koyu, açık)
FIS = (252, 250, 243)                      # fiş, tutanak, belge kâğıdı
CIZGI = (214, 209, 199)                    # soluk satır çizgileri, tutanak delikleri
DESK = INK

# ---------------------------------------------------------------- ölçüler
DOSYA = (40, 256, 1060, 1660)              # dosya gövdesi (sağ ve alt kenarı platform arayüzünün altında kalır)
SEKME = (392, 190, 648, 262)               # dosya sekmesi
FOLD = (30, 180, W, 1690)                  # kapak katmanının kutusu (kapanırken bu kutu daralır)
TUTANAK = (72, 1362, 920, 1528)
SHADOW = (9, 11)                           # sert gölge (marka: kalın mürekkep hat + sert gölge)
CONTENT = (0, 372, 935, 1352)              # iç sayfanın içerik katmanı (manşet + belge); kesme geçişi bunu keser
TOP = (0, 270, 935, 400)                   # iç sayfanın üst sırası (DELİL n/N + delil işaretleri)
MANSET_Y = 396                             # iç sayfada manşetin üst kenarı
DOC_Y1 = 1150                              # belgenin alt sınırı: altında sağda Makas, solda delil etiketi
STRIP_Y1 = 1128                            # hükümde GERÇEK şeridinin alt sınırı (altında SENCE? sırası ve Makas)
MASKOT_X0 = 724                            # Makas'ın (iç sayfa duruşu) sol ucu: alt sıradaki öğeler bunun solunda
WM_OLCEK = 0.6
MAX_DELIL = 6
FLIP = 0.36                                # kapağın açılması / kapanması (sn)
ENTRY0 = 0.12                              # iç sayfalar arası: yeni içerik makas kesmesi başlarken gelir
STAMP_FALL = 0.2                           # damganın inişi (sn)
SHAKE = 0.36                               # damga çarpınca sarsıntı (sn)
TYPE = 0.14                                # daktilo: kelimenin harfleri bu sürede yazılır
SCROLL = 0.16                              # tutanakta satır kayması
TUT_SIZE = 44                              # tutanak yazısı (Courier Prime Bold)
SERIT_UST = 38                             # hüküm şeridinde yazının üst boşluğu (etiket yazıya değmesin)
POSE = {"kapak": (836, 1262, 0.44, 228.0), "ic": (846, 1262, 0.44, 205.0), "ara": (846, 1262, 0.44, None)}
MOOD = {"kapak": "surprised", "ozet": "thinking", "delil": "normal", "ara": "surprised"}
Q_RE = re.compile(r"\byorumlara\s+yaz", re.I)
SORU_EKI = re.compile(r"\s+(?:mi|mı|mu|mü)(?:dir|dır|dur|dür|ydi|ydı|ydu|ydü)?\s*[?!.…]*\s*$", re.I)
HUKUMLER = ("EFSANE", "GERÇEK", "KISMEN DOĞRU")
KANIT = ("quote", "counter", "receipt", "photo", "drawing")   # kendi belgesi olan kart türleri
BELGE = {"quote": "ifade", "counter": "olcum", "receipt": "olcum", "photo": "torba", "drawing": "cizim"}


def up(s: str) -> str:
    return K.tr_upper((s or "").strip())


def cap_h(font: str, size: float) -> float:
    return -K.tbox("H", font, size)[1]


def label_w(text: str, size: float, font: str = "anton") -> float:
    return K.tw(text, font, size) + 2 * size * 0.2


def _int(v) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def cumle_bitti(text: str) -> bool:
    return (text or "").rstrip(" \"”’'»)").endswith((".", "!", "?", "…"))


def duz(s: str) -> str:
    """Karşılaştırma için kelime: Türkçe büyük harf, noktalama yok."""
    return re.sub(r"[^\wÇĞİÖŞÜÂÎÛ]", "", up(s))


# ---------------------------------------------------------------- senaryo -> sayfalar
def kart_verisi(c: dict) -> dict:
    """spec.card (Scene alanlarının hepsi; pipeline.build verir) -> kart.card_type'ın okuduğu kart verisi."""
    if "card" not in c and "type" in c:          # kart biçiminde verilmişse olduğu gibi
        return c
    return {"type": c.get("card") or "auto", "value": c.get("card_value") or "", "label": c.get("card_label") or "",
            "myth": c.get("card_myth") or "", "fact": c.get("card_fact") or "", "note": c.get("card_note") or "",
            "mascot": c.get("mascot") or "auto", "lines": list(c.get("card_lines") or [])}


def sahne_turu(spec, i: int, n: int) -> str:
    """Sahnenin kart türü, kart şablonunun kuralıyla (kart.card_type)."""
    ns = SimpleNamespace(card=kart_verisi(spec.card or {}), image=spec.image, sprite=spec.sprite,
                         headline=list(spec.headline or []), narration=spec.narration or "")
    return K.card_type(ns, i, n)


@dataclass
class Sayfa:
    kind: str                       # kapak | ozet | delil | ara | hukum
    scenes: list[int]
    belge: str = ""                 # ifade | olcum | torba | cizim | not | kayit
    no: int = 0                     # delil numarası; delil olmayan sayfada o ana kadarki son numara
    start: float = 0.0
    end: float = 0.0
    a: int = 0                      # kelime aralığı [a, b)
    b: int = 0
    extra: dict = field(default_factory=dict)


def plan(specs) -> list[Sayfa]:
    """Sahneleri kapak / iddia kaydı / delil / ara / hüküm sayfalarına ayırır (modül açıklamasındaki kurallar)."""
    n = len(specs)
    if not n:
        return []
    if n == 1:
        return [Sayfa("kapak", [0])]
    turler = [sahne_turu(s, i, n) for i, s in enumerate(specs)]
    nolar = [_int((s.card or {}).get("delil")) for s in specs]
    acik = any(nolar[1:])
    if acik:
        v = max(i for i in range(1, n) if nolar[i] > 0) + 1
    else:
        v = n - 1
        while v - 1 >= 1 and turler[v - 1] in ("text", "compare", "cta"):
            v -= 1
    v = min(max(v, 1, n - 3), n - 1)       # hüküm en çok son üç sahne, en az son sahne
    pages = [Sayfa("kapak", [0])]
    son = 0
    for i in range(1, v):
        t, cur = turler[i], pages[-1]
        if t == "compare":
            pages.append(Sayfa("ozet", [i], "kayit", son))
            continue
        if t == "interstitial":
            pages.append(Sayfa("ara", [i], "", son))
            continue
        if acik:
            d = nolar[i]
            if d <= 0 or (cur.kind == "delil" and d == cur.extra.get("ham") and t not in KANIT):
                cur.scenes.append(i)        # numarasız ya da aynı delilin belgesiz devamı: sayfa sürer
                continue
            no = d
        else:
            if t not in KANIT:
                cur.scenes.append(i)
                continue
            if cur.kind == "delil" and not cumle_bitti(specs[i - 1].narration):
                no = cur.extra["ham"]       # cümlenin devamı: aynı delilin yeni belgesi
            else:
                no = son + 1
        son = max(son, no)
        pages.append(Sayfa("delil", [i], BELGE.get(t, "not"), no, extra={"ham": no}))
    if not any(p.kind == "delil" for p in pages) and len(pages[0].scenes) > 1:
        # hiç delil yok (eski senaryo): kapaktan sonraki sahneler birer yazılı delil olur
        rest, pages[0].scenes = pages[0].scenes[1:], [0]
        for k, i in enumerate(rest):
            pages.insert(1 + k, Sayfa("delil", [i], "not", k + 1, extra={"ham": k + 1}))
    # numaralar görünüş sırasıyla 1, 2, 3...; en çok MAX_DELIL (fazlası son numaranın yeni belgesi olur)
    sira: dict[int, int] = {}
    last = 0
    for p in pages:
        if p.kind == "delil":
            ham = p.extra.get("ham", p.no)
            if ham not in sira:
                sira[ham] = min(len(sira) + 1, MAX_DELIL)
            p.no = last = sira[ham]
        elif p.kind in ("ozet", "ara"):
            p.no = last
    pages.append(Sayfa("hukum", list(range(v, n)), "", last))
    return pages


def iddia_metni(specs, meta: dict) -> str:
    """İDDİA fişinin metni: compare kartının inanışı (card_myth), yoksa soru biçimindeki konunun soru eki atılmış hâli
    ('Çin Seddi uzaydan görünür mü' -> 'Çin Seddi uzaydan görünür'), yoksa kapak başlığı."""
    for s in specs:
        myth = ((s.card or {}).get("card_myth") or (s.card or {}).get("myth") or "").replace("*", "").strip()
        if myth:
            return myth.rstrip(".!")
    topic = (meta.get("topic") or "").strip()
    if topic and SORU_EKI.search(topic):
        return SORU_EKI.sub("", topic).strip()
    if specs:
        return " ".join(x.strip() for x in specs[0].headline if x.strip())
    return topic


def hukum_of(specs, meta: dict) -> str:
    """Hüküm: senaryodaki hukum alanı, boşsa compare kartı (inanış + doğrusu) varsa EFSANE, yoksa ''."""
    h = up(str((meta.get("script") or {}).get("hukum") or meta.get("hukum") or ""))
    if h in HUKUMLER:
        return h
    n = len(specs)
    if any(sahne_turu(s, i, n) == "compare" for i, s in enumerate(specs)):
        return "EFSANE"
    return ""


def seri_bilgisi(kicker: str) -> tuple[list[str], int]:
    """İlk sahnenin seri etiketinden ('EFSANE Mİ, GERÇEK Mİ? #4') kapaktaki etiket parçaları ve dosya numarası."""
    k = up(kicker)
    m = re.search(r"#\s*(\d+)", k)
    no = int(m.group(1)) if m else 1
    name = re.sub(r"\s*#\s*\d+\s*", " ", k).strip() or STRUCTURES["efsane"][0]
    parts = [p.strip() for p in re.split(r"(?<=,)\s+", name) if p.strip()]
    return parts[:2] if len(parts) > 1 else [name], max(1, no)


# ---------------------------------------------------------------- küçük çizimler
def lif(img: Image.Image, box, seed: int, n: int):
    """Karton lifleri: ayrı saydam katmana çizilip bindirilir (RGBA'ya doğrudan çizgi saydamlığı ezerdi)."""
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    r = random.Random(seed)
    x0, y0, x1, y1 = box
    for _ in range(n):
        x, y = r.uniform(x0, x1), r.uniform(y0, y1)
        a = r.uniform(0, math.pi)
        L = r.uniform(4, 15)
        d.line([(x, y), (x + math.cos(a) * L, y + math.sin(a) * L)], fill=LIF[0] if r.random() < 0.55 else LIF[1],
               width=1)
    img.alpha_composite(lay)


def blend_dk(k: float):
    """Karton ile koyu kenar arası (baskı rengi): k=1 karton, k=0 koyu kenar."""
    return K.blend(MANILA_DK, MANILA, k)


ATAC_D = "M15 44 L15 98 A7 7 0 0 0 29 98 L29 20 A11 11 0 0 0 7 20 L7 106 A15 15 0 0 0 37 106 L37 52"
ATAC_VB = (0, 0, 44, 130)


def atac_svg() -> str:
    """Dikey ataş."""
    return (f'<path d="{ATAC_D}" fill="none" stroke="{K._hex(INK)}" stroke-width="8" stroke-linecap="round" '
            'stroke-linejoin="round"/>'
            f'<path d="{ATAC_D}" fill="none" stroke="#c9cbcd" stroke-width="4.2" stroke-linecap="round" '
            'stroke-linejoin="round"/>'
            f'<path d="{ATAC_D}" fill="none" stroke="#ffffff" stroke-width="1.3" stroke-linecap="round" '
            'opacity="0.8" stroke-dasharray="18 26"/>')


def atac(pen: K.Pen, x, y, w=40, rot=0.0):
    pen.svg(atac_svg(), ATAC_VB, x, y, w, rot=rot)


PIN_VB = (0, 0, 60, 74)


def raptiye_svg() -> str:
    """Kırmızı raptiye (yukarıdan, hafif yandan): başlık, parlama, gölge ve iğne."""
    ink, red = K._hex(INK), K._hex(RED)
    return (f'<ellipse cx="36" cy="64" rx="14" ry="5" fill="{ink}" opacity="0.35"/>'
            f'<path d="M30 40 L34 66" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
            f'<ellipse cx="30" cy="40" rx="15" ry="7" fill="{red}" stroke="{ink}" stroke-width="4"/>'
            f'<path d="M22 38 L24 22 L36 22 L38 38 Z" fill="{red}" stroke="{ink}" stroke-width="4" '
            'stroke-linejoin="round"/>'
            f'<ellipse cx="30" cy="20" rx="20" ry="11" fill="{red}" stroke="{ink}" stroke-width="4"/>'
            '<ellipse cx="24" cy="17" rx="7" ry="3.5" fill="#ffffff" opacity="0.7"/>')


def raptiye(pen: K.Pen, cx, cy, w=52):
    """Raptiyenin iğne ucu (cx, cy) noktasına batar."""
    k = w / PIN_VB[2]
    pen.svg(raptiye_svg(), PIN_VB, cx - 34 * k, cy - 66 * k, w)


def isaret_svg(durum: str) -> str:
    """Olay yeri delil işareti (önden çadır kart). durum: 'bitti' | 'simdi' | 'sirada'."""
    ink = K._hex(INK)
    if durum == "sirada":
        body, band, st = K._hex(MANILA_IC), K._hex(MANILA), K._hex(MANILA_DK)
    else:
        body, band, st = K._hex(YELLOW), "#e6bd12", ink
    dash = ' stroke-dasharray="9 7"' if durum == "sirada" else ""
    out = ""
    if durum != "sirada":
        out += f'<path d="M20 24 L84 24 L96 106 L8 106 Z" transform="translate(6 6)" fill="{ink}"/>'
    out += (f'<path d="M20 24 L84 24 L96 106 L8 106 Z" fill="{body}" stroke="{st}" stroke-width="5" '
            f'stroke-linejoin="round"{dash}/>')
    out += (f'<path d="M20 24 L84 24 L86 40 L18 40 Z" fill="{band}" stroke="{st}" stroke-width="4" '
            'stroke-linejoin="round"/>')
    return out


ISARET_VB = (0, 14, 108, 100)


def isaret(pen: K.Pen, x, y, w, no: int, durum: str):
    """Delil işareti; sol üst köşesi (x, y). Numara Anton ile Pen'den basılır (cairosvg yazı tipini bulamayabilir)."""
    pen.svg(isaret_svg(durum), ISARET_VB, x, y, w)
    k = w / ISARET_VB[2]
    col = INK if durum != "sirada" else MANILA_DK
    pen.text(x + 52 * k, y + (96 - 14) * k, str(no), "anton", 52 * k, col, anchor="ms")
    if durum == "bitti":
        pen.svg(K.check_svg(RED, 16), K.ICON_VB, x + w * 0.52, y - w * 0.22, w * 0.62)


def isaret_img(no: int, durum: str, w: float) -> Image.Image:
    """Tek delil işareti katmanı (1x); sol üst köşe görüntünün (pad, pad) noktası."""
    pad = 24
    pen = K.Pen(0, 0, w + 2 * pad, w + 2 * pad)
    isaret(pen, pad, pad, w, no, durum)
    return pen.done()


def asili_etiket(text, size=40, rot=-8.0, ip=56, col=YELLOW) -> Image.Image:
    """Delil etiketi (SS): delikli, köşesi kesik karton; kırmızı ipi yukarı uzanır."""
    w = K.tw(text, "anton", size) + 64
    h = cap_h("anton", size) + 40
    sp = K.Sprite(w + ip, h + ip, margin=20)
    ox, oy = ip * 0.2, ip
    c = 16
    pts = [(ox + c, oy), (ox + w, oy), (ox + w, oy + h), (ox + c, oy + h), (ox, oy + h - c), (ox, oy + c)]
    sp.polygon([(px + 5, py + 6) for px, py in pts], INK + (255,))
    sp.polygon(pts, col + (255,))
    sp.line(pts + [pts[0]], INK + (255,), 4)
    ex, ey = ox + 22, oy + h / 2
    sp.dot(ex, ey, 10, INK + (255,))
    sp.dot(ex, ey, 6, OFF + (255,))
    sp.line([(ex, ey), (ex - 6, oy - ip * 0.5), (ex + 10, 0)], RED + (255,), 4)
    sp.text((ox + 42, oy + h / 2 + cap_h("anton", size) / 2), text, "anton", size, INK)
    return sp.render_ss(rot)


def kagit(w, h, renk=FIS, cizgili=False, kenar=True, margin=30) -> K.Sprite:
    """Mürekkep kenarlı belge kâğıdı + sert gölge (SS). İsteğe bağlı soluk satır çizgileri."""
    sp = K.Sprite(w, h, margin=margin)
    d = sp.d

    def box(x0, y0, x1, y1, **kw):
        a, b = sp.p(x0, y0)
        c, e = sp.p(x1, y1)
        d.rounded_rectangle([a, b, c, e], radius=6 * SS, **kw)

    box(SHADOW[0], SHADOW[1], w + SHADOW[0], h + SHADOW[1], fill=INK + (255,))
    box(0, 0, w, h, fill=renk + (255,), outline=INK + (255,) if kenar else None, width=int(5 * SS) if kenar else 0)
    if cizgili:
        y = 70
        while y < h - 20:
            sp.line([(14, y), (w - 14, y)], CIZGI + (255,), 2)
            y += 58
    return sp


def yapistir(pen: K.Pen, sp: K.Sprite, cx, cy, rot):
    im = sp.render_ss(rot)
    pen.paste(im, cx - im.width / 2 / SS, cy - im.height / 2 / SS)


def kirmizi_cizik(pen_or_sp, x0, x1, y, seed, w=12):
    """Kırmızı keçeli kalemle iki kez üstünü çizme (hafif dalgalı)."""
    r = random.Random(seed)
    for k, dy in enumerate((-6, 8)):
        pts = []
        n = 14
        for i in range(n + 1):
            u = i / n
            pts.append((x0 - 10 + (x1 - x0 + 20) * u, y + dy + r.uniform(-2.5, 2.5) - k * 10 * (u - 0.5)))
        pen_or_sp.line(pts, RED + (235,), w)


def satir_araliklari(lines, font, size, gap):
    """Satırların taban çizgileri arası: üstteki satırın kuyruğu (Ç, Ş) + alttakinin şapkası (İ, Ö, Ü) + gap."""
    out = []
    for a, b in zip(lines, lines[1:]):
        desc = max(0.0, K.tbox(a, font, size)[3])
        asc = max(cap_h(font, size), -K.tbox(b, font, size)[1])
        out.append(desc + asc + gap)
    return out


def sar_genislik(words: list[str], font: str, size: float, widths) -> list[str] | None:
    """Kelimeleri satır satır sarar; i. satırın genişliği widths(i). Tek kelime bile sığmazsa None."""
    lines, cur = [], []
    sp = K.tw(" ", font, size)
    cw = 0.0
    for w in words:
        ww = K.tw(w, font, size)
        lim = widths(len(lines))
        if cur and cw + sp + ww > lim:
            lines.append(cur)
            cur, cw = [], 0.0
            lim = widths(len(lines))
        if ww > lim:
            return None
        cw = cw + (sp if cur else 0) + ww
        cur.append(w)
    if cur:
        lines.append(cur)
    return [" ".join(L) for L in lines]


def kucult_sar(words: list[str], font: str, size: float, width: float, min_size: float = 16):
    """Her kelime width'e sığana kadar küçültüp sarar (uzun Türkçe kelime taşmaz): (boyut, satırlar)."""
    while size > min_size and any(K.tw(w, font, size) > width for w in words):
        size -= 2
    return size, sar_genislik(words, font, size, lambda i: width) or [" ".join(words)]


def ortala_ve_sigdir(text, font, width, max_size, min_size, max_lines) -> tuple[int, list[str]]:
    """En büyük boyut: satır sayısı max_lines'ı, her satır width'i aşmaz (uzun Türkçe kelime de sığar)."""
    words = text.split()
    for size in range(max_size, min_size - 1, -2):
        lines = sar_genislik(words, font, size, lambda i: width)
        if lines and len(lines) <= max_lines:
            return size, lines
    return kucult_sar(words, font, min_size, width)


# ---------------------------------------------------------------- damga
def damga(ust: str, alt: str, size_alt=190, rot=-9.0, seed=4, col=RED) -> Image.Image:
    """Kırmızı lastik damga (SS, döndürülmüş): çift çerçeve, üstte HÜKÜM, altta EFSANE/GERÇEK; mürekkebi yer yer
    eksik."""
    S = SS
    size_ust = max(40, min(66, size_alt * 0.36))
    wa = K.tw(alt, "anton", size_alt)
    wu = K.tw(ust, "anton", size_ust)
    bw = max(wa, wu + 120) + 96
    capa, capu = cap_h("anton", size_alt), cap_h("anton", size_ust)
    ascu = max(capu, -K.tbox(ust, "anton", size_ust)[1])
    asca = max(capa, -K.tbox(alt, "anton", size_alt)[1])
    desca = max(0.0, K.tbox(alt, "anton", size_alt)[3])
    bh = 36 + ascu + 30 + asca + desca + 40
    m = 30
    im = Image.new("RGBA", (int((bw + 2 * m) * S), int((bh + 2 * m) * S)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = col + (255,)
    d.rounded_rectangle([m * S, m * S, (m + bw) * S, (m + bh) * S], radius=18 * S, outline=c, width=int(13 * S))
    d.rounded_rectangle([(m + 20) * S, (m + 20) * S, (m + bw - 20) * S, (m + bh - 20) * S], radius=8 * S, outline=c,
                        width=int(5 * S))
    yu = m + 36 + ascu
    d.text(((m + bw / 2) * S, yu * S), ust, font=K.fnt("anton", size_ust * S), fill=c, anchor="ms")
    for sgn in (-1, 1):                    # HÜKÜM'ün iki yanında kısa çizgiler
        xa = m + bw / 2 + sgn * (wu / 2 + 18)
        xb = m + bw / 2 + sgn * (bw / 2 - 44)
        d.line([(xa * S, (yu - capu / 2) * S), (xb * S, (yu - capu / 2) * S)], fill=c, width=int(6 * S))
    ya = yu + 30 + asca
    d.text(((m + bw / 2) * S, ya * S), alt, font=K.fnt("anton", size_alt * S), fill=c, anchor="ms")
    # mürekkep: ince benekler + geniş soluk bölgeler (sabit tohum: kareden kareye titremez)
    rng = np.random.default_rng(seed)
    hh, ww = im.height, im.width
    fine = rng.random((hh // 5, ww // 5)).astype(np.float32)
    fine = np.asarray(Image.fromarray(fine).resize((ww, hh), Image.BILINEAR))
    lowf = rng.normal(0, 1, (max(2, hh // 120), max(2, ww // 120))).astype(np.float32)
    lowf = np.asarray(Image.fromarray(lowf).resize((ww, hh), Image.BICUBIC))
    lowf = (lowf - lowf.min()) / (np.ptp(lowf) + 1e-6)
    a = np.asarray(im.getchannel("A")).astype(np.float32) / 255
    keep = (fine > 0.07 + 0.16 * (1 - lowf)).astype(np.float32)
    a = a * keep * (0.84 + 0.16 * lowf)
    im.putalpha(Image.fromarray(np.clip(a * 255 * 0.97, 0, 255).astype(np.uint8)))
    im = im.filter(ImageFilter.GaussianBlur(0.6 * S))
    return im.rotate(rot, resample=Image.BICUBIC, expand=True)


def carp(img: Image.Image, stamp: Image.Image, x: int, y: int, alpha: float = 1.0) -> None:
    """Damgayı (1x) çarpma karışımıyla basar: altındaki yazı görünür kalır. img RGBA, yerinde değişir; kırpar."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img.width, x + stamp.width), min(img.height, y + stamp.height)
    if x1 <= x0 or y1 <= y0:
        return
    st = stamp.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    reg = img.crop((x0, y0, x1, y1))
    a = np.asarray(st.getchannel("A"), np.float32)[..., None] / 255 * alpha
    lc = np.asarray(st.convert("RGB"), np.float32)
    bc = np.asarray(reg.convert("RGB"), np.float32)
    out = bc * (1 - a + a * lc / 255)
    res = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")
    res.putalpha(reg.getchannel("A"))
    img.paste(res, (x0, y0))


# ---------------------------------------------------------------- belge parçaları (SS sprite'lar)
def iddia_karti(lines, size, w=816, strike=(), head_h=100, alt_bosluk=40, narrow=None):
    """İDDİA fişi: kırmızı çerçeveli İDDİA başlığı + 'yaygın inanış', kırmızı fiş çizgisi, Anton iddia satırları,
    isteğe bağlı kırmızı çizik (strike: (satır, ilk kelime, son kelime) üçlüleri). Döndürür: (sprite, bilgi)."""
    pad = 46
    gaps = satir_araliklari(lines, "anton", size, size * 0.10)
    top0 = max(cap_h("anton", size), -K.tbox(lines[0], "anton", size)[1])
    h = pad + head_h + top0 + sum(gaps) + max(0.0, K.tbox(lines[-1], "anton", size)[3]) + alt_bosluk
    sp = kagit(w, h)
    sp.line([(14, pad + head_h - 16), (w - 14, pad + head_h - 16)], RED + (230,), 3)
    hs = 56 if head_h >= 96 else 50
    hw = K.tw("İDDİA", "anton", hs)
    bx0, by0 = pad, pad - 8
    bh = cap_h("anton", hs) + 2 * 13 + 13
    sp.line([(bx0, by0), (bx0 + hw + 36, by0), (bx0 + hw + 36, by0 + bh), (bx0, by0 + bh), (bx0, by0 - 2)],
            RED + (255,), 5)
    sp.text((bx0 + 18, by0 + bh - 13), "İDDİA", "anton", hs, RED)
    sp.text((w - pad, by0 + bh - 18), "yaygın inanış", "courier", 30, DGREY, anchor="rs")
    info = {"lines": [], "w": w, "h": h, "pad": pad}
    y = pad + head_h + top0
    for i, L in enumerate(lines):
        sp.text((pad, y), L, "anton", size, INK)
        info["lines"].append((pad, y - cap_h("anton", size), pad + K.tw(L, "anton", size), y))
        if i < len(gaps):
            y += gaps[i]
    for li, a, b in strike:
        words = lines[li].split()
        x0 = pad + (K.tw(" ".join(words[:a]) + " ", "anton", size) if a else 0)
        x1 = pad + K.tw(" ".join(words[:b + 1]), "anton", size)
        base = info["lines"][li][3]
        kirmizi_cizik(sp, x0, x1, base - cap_h("anton", size) * 0.48, 5 + li, w=max(8, size * 0.1))
    return sp, info


def ekran_noktasi(info, cx, cy, rot, px, py):
    """Fiş içindeki (px, py) noktasının ekran koordinatı (fiş (cx, cy) merkezli, rot derece döndürülmüş)."""
    w, h = info["w"], info["h"]
    a = math.radians(rot)
    dx, dy = px - w / 2, py - h / 2
    return cx + dx * math.cos(a) + dy * math.sin(a), cy - dx * math.sin(a) + dy * math.cos(a)


def gorsel_ac(path: Path | None) -> Image.Image | None:
    if path is None:
        return None
    try:
        return Image.open(path).convert("RGBA")
    except (OSError, ValueError):
        return None


def cizim_kirp(im: Image.Image) -> Image.Image:
    bb = im.getchannel("A").getbbox()
    return im.crop(bb) if bb else im


def polaroit(cizim: Image.Image, foto: bool, w: float, rot=5.0, seed=12) -> Image.Image:
    """Bantlı küçük fotoğraf kartı (alt kenarı geniş): mürekkep kenar + sert gölge, içinde çizim ya da fotoğraf (SS)."""
    S = SS
    pad, alt = 16, 46
    iw = w - 2 * pad
    ih = iw * 0.86
    h = pad + ih + alt
    m = 34
    im = Image.new("RGBA", (int((w + 2 * m) * S), int((h + 2 * m) * S)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([(m + SHADOW[0]) * S, (m + SHADOW[1]) * S, (m + w + SHADOW[0]) * S, (m + h + SHADOW[1]) * S],
                fill=INK + (255,))
    d.rectangle([m * S, m * S, (m + w) * S, (m + h) * S], fill=FIS + (255,), outline=INK + (255,), width=int(4 * S))
    box = [(m + pad) * S, (m + pad) * S, (m + pad + iw) * S, (m + pad + ih) * S]
    if foto:
        ph = K.cover(cizim.convert("RGB"), int(iw * S), int(ih * S)).convert("RGBA")
        im.alpha_composite(ph, (int(box[0]), int(box[1])))
        d.rectangle(box, outline=INK + (255,), width=int(3 * S))
    else:
        d.rectangle(box, fill=WHITE + (255,), outline=INK + (255,), width=int(3 * S))
        cz = cizim_kirp(cizim)
        k = min((iw - 16) * S / cz.width, (ih - 16) * S / cz.height)
        cz = cz.resize((max(1, int(cz.width * k)), max(1, int(cz.height * k))), Image.LANCZOS)
        im.alpha_composite(cz, (int((m + pad + iw / 2) * S - cz.width / 2), int((m + pad + ih / 2) * S - cz.height / 2)))
    sp = K.Sprite(w, 40, margin=0)       # bant: fotoğrafın üst kenarına
    sp.im = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sp.d = ImageDraw.Draw(sp.im)
    sp.m = m
    K.tape(sp, w * 0.5, 2, w * 0.42, 38, 3, seed, color=(252, 226, 120), alpha=185)
    im.alpha_composite(sp.im)
    return im.rotate(rot, resample=Image.BICUBIC, expand=True)


def manset_olc(lines: list[str], hl: int, max_w: float, max_h: float, sizes=(112, 104, 96, 88, 80, 72, 64, 58, 52),
               gap=12, tek=False):
    """Manşet: her satır bir yırtık etiket; sığarsa (tek değilse) iki satır yan yana. Döndürür (boyut, sıralar), sıra:
    [(satır, i)]."""
    lines = [L for L in lines if L]
    for size in sizes:
        rows, cur, cw = [], [], 0.0
        ok = True
        for i, L in enumerate(lines):
            lw = label_w(L, size)
            if lw > max_w:
                ok = False
                break
            if cur and (tek or cw + gap + lw > max_w):
                rows.append(cur)
                cur, cw = [], 0.0
            cw = cw + (gap if cur else 0) + lw
            cur.append((L, i))
        if not ok:
            continue
        if cur:
            rows.append(cur)
        rh = max_satir_h(lines, size)
        if len(rows) * rh + (len(rows) - 1) * gap <= max_h:
            return size, rows
    size = sizes[-1]
    while size > 18 and any(label_w(L, size) > max_w for L in lines):
        size -= 2
    return size, [[(L, i)] for i, L in enumerate(lines)]


def max_satir_h(lines, size) -> float:
    """Yırtık etiketin yüksekliği (en uzun şapka/kuyruk payıyla)."""
    out = 0.0
    for L in lines or ["H"]:
        l, t, r, b = K.tbox(L, "anton", size)
        out = max(out, max(cap_h("anton", size), -t) + max(0.0, b) + 2 * size * 0.16)
    return out


# ---------------------------------------------------------------- video
class DosyaVideo:
    def __init__(self, scenes, words: list[Word], meta: dict, bcfg: dict, yalniz_icerik: bool = False):
        """yalniz_icerik: masa ve dosya kartonu çizilmez, frame() gren eklemeden RGBA döner (testlerde güvenli alan
        denetimi için: saydam olmayan her piksel içeriktir)."""
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        self.yalniz_icerik = yalniz_icerik
        on = bcfg.get("enabled", False)
        self.brand_on = on
        self.intro = bool(on and bcfg.get("intro_cut", True))
        self.handle = (bcfg.get("handle") or "") if on and bcfg.get("subtitle_handle", True) else ""
        self.wm_every = float(bcfg.get("watermark_switch_seconds", 7) or 7)
        self.wm_alpha = float(bcfg.get("watermark_opacity", 0.85) or 0.85)
        n = len(scenes)
        self.n = n
        ranges, a = [], 0
        for i, s in enumerate(scenes):
            b = min(len(words), a + len(s.words)) if i < n - 1 else len(words)
            ranges.append((a, b))
            a = b
        self.ranges = ranges
        self.pages = plan(scenes)
        for pg in self.pages:
            pg.start, pg.end = scenes[pg.scenes[0]].start, scenes[pg.scenes[-1]].end
            pg.a, pg.b = ranges[pg.scenes[0]][0], ranges[pg.scenes[-1]][1]
        self.page_starts = [p.start for p in self.pages]
        self.N = max([p.no for p in self.pages] + [0])
        self.starts = [w.start for w in words]
        self.seri, self.dosya_no = seri_bilgisi(scenes[0].kicker if scenes else "")
        self.iddia = iddia_metni(scenes, self.meta)
        self.hukum = hukum_of(scenes, self.meta)
        self.tarih = self.meta.get("tarih") or dt.date.today().strftime("%d.%m.%Y")
        self.mascot = Mascot()
        self._c: dict = {}
        self._dyn: dict = {}

    # ------------------------------------------------------------ zaman
    def page_at(self, t: float) -> int:
        return max(0, bisect.bisect_right(self.page_starts, t) - 1)

    def scene_at(self, t: float) -> int:
        return max(0, bisect.bisect_right([s.start for s in self.scenes], t) - 1)

    def cur_word(self, t: float) -> int:
        return bisect.bisect_right(self.starts, t + 0.03) - 1

    def word_time(self, a: int, b: int, pred) -> float | None:
        for i in range(a, b):
            if pred(self.words[i].text):
                return self.words[i].start
        return None

    # ------------------------------------------------------------ zemin: masa + dosya
    def desk(self) -> Image.Image:
        if self.yalniz_icerik:
            return self._c.setdefault("bos", Image.new("RGBA", (W, H), (0, 0, 0, 0)))
        if "desk" not in self._c:
            rng = np.random.default_rng(3)
            low = rng.normal(0, 1, (H // 60, W // 60)).astype(np.float32)
            low = np.asarray(Image.fromarray(low).resize((W, H), Image.BICUBIC))
            yy = np.linspace(-1, 1, H)[:, None]
            xx = np.linspace(-1, 1, W)[None, :]
            vig = (xx ** 2 + yy ** 2) * 5            # kenarlara doğru biraz koyulaşır
            desk = np.zeros((H, W, 3), np.float32) + np.array(DESK, np.float32) + (low * 3 - vig)[..., None]
            self._c["desk"] = Image.fromarray(np.clip(desk, 0, 255).astype(np.uint8)).convert("RGBA")
        return self._c["desk"]

    def folder(self, acik: bool) -> Image.Image:
        """Dosya katmanı (tam kare, masası şeffaf). acik=False: kapak (arkasında koyu arka kapak, kenarda baskı
        çerçevesi); acik=True: içi (daha açık karton, üstte kapağın katlandığı iki çizgi). Sekmede dosya numarası."""
        key = ("folder", acik)
        if key in self._c:
            return self._c[key]
        if self.yalniz_icerik:
            self._c[key] = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            return self._c[key]
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        x0, y0, x1, y1 = DOSYA
        sx0, sy0, sx1, sy1 = SEKME
        body = MANILA_IC if acik else MANILA
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rounded_rectangle([x0 + 12, y0 + 16, x1 + 12, y1 + 16], 18, fill=(0, 0, 0, 150))
        sd.rounded_rectangle([sx0 + 12, sy0 + 16, sx1 + 12, y0 + 40], 16, fill=(0, 0, 0, 150))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
        pen = K.Pen(0, 0, W, H)
        if not acik:   # arka kapak: biraz kaymış koyu karton (dosyanın kalınlığı) ve içinden taşan kâğıt kenarları
            pen.rr((x0 - 10, y0 - 8, x1 - 4, y1 + 12), 18, fill=MANILA_DK)
            pen.rr((x0 + 30, y0 - 4, x1 - 40, y1 + 6), 6, fill=(236, 232, 220))
            pen.rr((x0 + 60, y0 - 1, x1 - 70, y1 + 3), 6, fill=(246, 243, 233))
        pen.rr((sx0, sy0, sx1, y0 + 30), 16, fill=body, outline=MANILA_DK, width=3)
        pen.rr((x0, y0, x1, y1), 18, fill=body, outline=MANILA_DK, width=3)
        pen.rr((sx0 + 3, y0 - 4, sx1 - 3, y0 + 8), 2, fill=body)
        img.alpha_composite(pen.done())
        # karton dokusu: düşük frekanslı lekeler + lifler (yalnız dosyanın üstünde)
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], 17, fill=255)
        md.rounded_rectangle([sx0 + 2, sy0 + 2, sx1 - 2, y0 + 30], 15, fill=255)
        rng = np.random.default_rng(11 if acik else 7)
        lowk = rng.normal(0, 1, (H // 36, W // 36)).astype(np.float32)
        lowk = np.asarray(Image.fromarray(lowk).resize((W, H), Image.BICUBIC))
        tex = np.asarray(img.convert("RGB"), np.float32) + lowk[..., None] * 5
        tex_im = Image.fromarray(np.clip(tex, 0, 255).astype(np.uint8)).convert("RGBA")
        lif(tex_im, (x0, sy0, x1, y1), 11 if acik else 7, 1500)
        img.paste(tex_im, (0, 0), mask)
        pen = K.Pen(0, 0, W, H)
        if acik:
            for yy in (270, 282):
                pen.rr((x0 + 20, yy - 1, x1 - 20, yy + 1), 1, fill=blend_dk(0.45))
        else:
            pen.rr((x0 + 22, y0 + 22, x1 - 22, y1 - 22), 12, outline=blend_dk(0.55), width=2)
        no = f"DOSYA NO. {self.dosya_no:02d}"
        size = 40
        while label_w(no, size) > sx1 - sx0 - 20 and size > 26:
            size -= 2
        pen.text((sx0 + sx1) / 2, sy0 + 50, no, "anton", size, INK, anchor="ms")
        img.alpha_composite(pen.done())
        self._c[key] = img
        return img

    def bg(self, acik: bool) -> Image.Image:
        key = ("bg", acik)
        if key not in self._c:
            im = self.desk().copy()
            im.alpha_composite(self.folder(acik))
            self._c[key] = im
        return self._c[key]

    # ------------------------------------------------------------ kapak
    def kapak_parts(self, pg: Sayfa) -> dict:
        """Kapak: seri etiketi, KONU / TARİH, İDDİA fişi (kancanın görseli polaroit, hükümse yanlış kelime kırmızı
        kalemle çizilir), kancanın vurgulu satırı fişin altına yırtık etiket olarak yapışır, delil işaretleri sırası."""
        key = ("kapak", pg.scenes[0])
        if key in self._c:
            return self._c[key]
        pen = K.Pen(0, 0, W, H)
        # seri etiketi
        s, x = 62, X0 + 6
        for k, part in enumerate(self.seri):
            while label_w(part, s) > X1 - X0 - 20 and s > 40:
                s -= 2
        for k, part in enumerate(self.seri):
            lab = K.torn_label(part, s, OFF, (INK, RED)[k % 2], 71 + k)
            im = lab.render_ss((-2.0, 1.6)[k % 2], (6, 8, 0, 0.9))
            cy = 324 + 4 * k
            if x + lab.w > X1 and k:   # ikinci parça sığmazsa alta
                x, cy = X0 + 6, 324 + lab.h + 8
            pen.paste(im, x + lab.w / 2 - im.width / 2 / SS, cy - im.height / 2 / SS)
            x += lab.w + 10
        # KONU / TARİH
        konu = (self.meta.get("topic") or "").strip()
        if konu and SORU_EKI.search(konu) and not konu.endswith("?"):
            konu += "?"
        konu = konu[:1].upper() + konu[1:] if konu else ""
        yb = 432
        fs = 30
        tarih = f"TARİH: {self.tarih}"
        while fs > 24 and K.tw("KONU: " + konu, "courier", fs) + 40 + K.tw(tarih, "courier", fs) > X1 - X0:
            fs -= 2
        show_t = K.tw("KONU: " + konu, "courier", fs) + 40 + K.tw(tarih, "courier", fs) <= X1 - X0
        room = X1 - X0 - 8 - (K.tw(tarih, "courier", fs) + 40 if show_t else 0)
        kt = K.fit_words("KONU: " + konu, "courier", fs, room) if konu else "KONU: —"
        pen.text(X0 + 8, yb, kt, "courier", fs, INK)
        kx = X0 + 8 + K.tw("KONU: ", "courier", fs)
        x = kx
        while x < X0 + 8 + K.tw(kt, "courier", fs):
            pen.rr((x, yb + 9, x + 6, yb + 11), 1, fill=MANILA_DK)
            x += 12
        if show_t:
            pen.text(X1 - 4, yb, tarih, "courier", fs, INK, anchor="rs")
        base = pen.done()
        # İDDİA fişi
        lay = self.iddia_layout(top=462, bottom=1226, hook=True)
        out = {"base": base, **lay}
        self._c[key] = out
        return out

    def strike_words(self, lines: list[str]) -> list[tuple[int, int, int]]:
        """Hüküm EFSANE'yse kancanın başlığında geçmeyen 1-2 iddia kelimesi çizilir (yoksa son kelime)."""
        if self.hukum != "EFSANE":
            return []
        head = {duz(w) for L in self.scenes[0].headline for w in L.split()}
        pos = [(li, wi, w) for li, L in enumerate(lines) for wi, w in enumerate(L.split())]
        diff = [(li, wi) for li, wi, w in pos if duz(w) not in head]
        pick = diff if 0 < len(diff) <= 2 else [(pos[-1][0], pos[-1][1])]
        out: list[tuple[int, int, int]] = []
        for li, wi in pick:
            if out and out[-1][0] == li and out[-1][2] == wi - 1:
                out[-1] = (li, out[-1][1], wi)
            else:
                out.append((li, wi, wi))
        return out

    def hook_label(self) -> str:
        """Kancanın vurgulu satırı (yoksa son satırı): iddia fişinin altına yapışan yırtık etiket."""
        sc = self.scenes[0]
        lines = [up(x) for x in sc.headline if x and x.strip()]
        if not lines:
            return ""
        hl = sc.highlight_line if 0 <= sc.highlight_line < len(lines) else len(lines) - 1
        lab = lines[hl]
        if duz(lab) and duz(lab) in duz(up(self.iddia)).split() and self.hukum != "GERÇEK":
            return ""
        return lab

    def iddia_layout(self, top: float, bottom: float, hook: bool) -> dict:
        """İDDİA fişinin kapaktaki yerleşimi: satırlar en büyük boyda; kancanın görseli sağ üstte polaroit; hüküm
        etiketi son satırın altına fişin alt kenarından taşarak yapışır. Hepsi bottom'un üstünde biter."""
        sc = self.scenes[0]
        text = up(self.iddia).replace("*", "")
        words = text.split()
        pic = gorsel_ac(sc.sprite) if sc.sprite is not None else None
        foto = False
        if pic is None and sc.image is not None:
            pic, foto = gorsel_ac(sc.image), True
        label = self.hook_label() if hook else ""
        cw, pad, head_h = 816, 46, 100
        inner = cw - 2 * pad
        pw = 280 if pic is not None else 0
        ph = (pw - 32) * 0.86 + 16 + 46 if pic is not None else 0
        best = None
        for size in range(132, 55, -4):
            pitch0 = cap_h("anton", size) * 1.14 + size * 0.1
            narrow_until = head_h + 20 + ph       # fiş içinde polaroitin alt kenarı (yaklaşık)

            def widths(i, size=size, pitch0=pitch0, narrow_until=narrow_until):
                top_i = pad + head_h + i * pitch0
                return inner - pw - 26 if (pw and top_i < narrow_until) else inner
            lines = sar_genislik(words, "anton", size, widths)
            if not lines or len(lines) > 4:
                continue
            ls = 0
            lab = None
            if label:
                ls = min(116, int(size * 0.92))
                while label_w(label, ls) > 640 and ls > 30:
                    ls -= 4
                lab = K.torn_label(label, ls, OFF if self.hukum != "GERÇEK" else INK,
                                   RED if self.hukum != "GERÇEK" else YELLOW, 81)
            gaps = satir_araliklari(lines, "anton", size, size * 0.10)
            top0 = max(cap_h("anton", size), -K.tbox(lines[0], "anton", size)[1])
            text_h = pad + head_h + top0 + sum(gaps) + max(0.0, K.tbox(lines[-1], "anton", size)[3])
            text_h = max(text_h, pad + head_h + ph - 10) if pw else text_h
            if lab is not None:
                lab_top = text_h + 20
                card_h = lab_top + lab.h * 0.5
                total = lab_top + lab.h + 14
            else:
                card_h = text_h + 44
                total = card_h + SHADOW[1] + 6
            if top + total <= bottom:
                best = (size, lines, lab, card_h, text_h)
                break
        if best is None:
            size, lines = kucult_sar(words, "anton", 56, inner - pw - 26 if pw else inner)   # polaroidin solunda
            gaps = satir_araliklari(lines, "anton", size, size * 0.10)
            top0 = max(cap_h("anton", size), -K.tbox(lines[0], "anton", size)[1])
            th = pad + head_h + top0 + sum(gaps) + max(0.0, K.tbox(lines[-1], "anton", size)[3])
            th = max(th, pad + head_h + ph - 10) if pw else th
            best = (size, lines, None, th + 44, th)
        size, lines, lab, card_h, text_h = best
        strike = self.strike_words(lines) if hook else []
        alt = card_h - text_h
        sp, info = iddia_karti(lines, size, w=cw, strike=strike, head_h=head_h, alt_bosluk=alt)
        cx, rot = 492, -1.2
        cy = top + info["h"] / 2
        pen = K.Pen(0, 0, W, H)
        yapistir(pen, sp, cx, cy, rot)
        atac(pen, 470, top - 26, 40, rot=-3)
        if pic is not None:
            pim = polaroit(pic, foto, pw, rot=5)
            px = cx + cw / 2 - pad - pw / 2 + 6
            py = top + pad + head_h + ph / 2 + 16
            pen.paste(pim, px - pim.width / 2 / SS, py - pim.height / 2 / SS)
            if foto:
                note = K.credit_chip(dict((sc.card or {}).get("credit") or {}))
                if note:
                    K.chip_label(pen, px - pw / 2 - 10, py + ph / 2 - 30, note, size=24, max_w=pw + 40)
        layer = pen.done()
        out = {"card": layer, "size": size, "lines": lines, "info": info, "cx": cx, "cy": cy, "rot": rot}
        if lab is not None:
            li = strike[-1][0] if strike else len(lines) - 1
            _, taban = ekran_noktasi(info, cx, cy, rot, 300, info["lines"][li][3])
            if li < len(lines) - 1:
                _, taban = ekran_noktasi(info, cx, cy, rot, 300, info["lines"][-1][3])
            im = lab.render(-4.0, (7, 9, 0, 1.0))
            lx = min(X1 - 10 - im.width, max(X0 - 6, cx - im.width / 2 + 40))
            out["label"] = (im, lx, taban + 20 + K.tbox("H", "anton", 1)[3] - 8)
        return out

    def tags_row(self) -> Image.Image | None:
        """Kapakta: boş delil işaretleri + 'N delil · 1 hüküm'."""
        if "tagsrow" in self._c:
            return self._c["tagsrow"]
        if not self.N:
            self._c["tagsrow"] = None
            return None
        pen = K.Pen(0, 1200, 935, 1340)
        w = 64 if self.N <= 5 else 54
        step = w + 16
        yr = 1250
        for i in range(self.N):
            isaret(pen, X0 + 8 + i * step, yr, w, i + 1, "sirada")
        txt = f"{self.N} delil · 1 hüküm"
        pen.text(X0 + 8 + self.N * step + 10, yr + 52 * w / 64, txt, "courier", 30, INK)
        self._c["tagsrow"] = pen.done()
        return self._c["tagsrow"]

    def kapak_layer(self, pg: Sayfa, with_label=True) -> Image.Image:
        """Kapağın tam katmanı (masası şeffaf): dosya + içerik; kapak açılırken daralan katman."""
        key = ("kapak_kat", pg.scenes[0], with_label)
        if key not in self._c:
            P = self.kapak_parts(pg)
            im = self.folder(False).copy()
            im.alpha_composite(P["base"])
            im.alpha_composite(P["card"])
            tr = self.tags_row()
            if tr is not None:
                im.alpha_composite(tr, (0, 1200))
            if with_label and "label" in P:
                lab, lx, ly = P["label"]
                K._comp(im, lab, lx, ly)
            self._c[key] = im
        return self._c[key]

    def draw_kapak(self, img: Image.Image, pg: Sayfa, t: float, lt: float) -> None:
        P = self.kapak_parts(pg)
        img.alpha_composite(self.kapak_layer(pg, with_label=False))
        if "label" in P:
            lab, lx, ly = P["label"]
            k = 1.0
            ts = self._label_time(pg)
            if ts is not None and 0 <= t - ts < 0.3:
                k = bump((t - ts) / 0.3, 1.1)
            elif lt < 0.5 and pg is self.pages[0]:
                k = 1 + 0.03 * math.sin(math.pi * K.clamp(lt / 0.5))
            K.put(img, lab, lx, ly, k=k, clip=CLIP)

    def _label_time(self, pg: Sayfa) -> float | None:
        if "lt" not in pg.extra:
            lab = self.hook_label()
            first = duz(lab.split()[0]) if lab else ""
            a, b = self.ranges[0]
            pg.extra["lt"] = self.word_time(a, b, lambda w: bool(first) and duz(w).startswith(first[:max(3, len(first) - 2)]))
        return pg.extra["lt"]

    # ------------------------------------------------------------ iç sayfa: üst sıra
    def top_row(self, pg: Sayfa):
        """İç sayfanın üst sırası: solda DELİL n/N (iddia kaydında İDDİA KAYDI, arada YENİ BULGU), sağda delil
        işaretleri. Döndürür: (şimdiki işaret hariç katman, şimdiki işaret, sol üst)."""
        key = ("top", pg.kind, pg.no)
        if key in self._c:
            return self._c[key]
        pen = K.Pen(*TOP)
        yb = 366
        if pg.kind == "delil":
            a = f"DELİL {pg.no}"
            pen.text(X0 + 8, yb, a, "anton", 56, INK)
            pen.text(X0 + 8 + K.tw(a, "anton", 56), yb, f"/{self.N}", "anton", 56, RED)
        else:
            txt, col = ("İDDİA KAYDI", INK) if pg.kind == "ozet" else ("YENİ BULGU", RED)
            pen.text(X0 + 8, yb, txt, "anton", 56, col)
        cur_img, cur_xy = None, None
        if self.N:
            n = self.N
            w = 66 if n <= 5 else 56
            gap = 14 if n <= 5 else 10
            total = n * w + (n - 1) * gap
            x = X1 - 6 - total
            for i in range(1, n + 1):
                if pg.kind == "delil" and i == pg.no:
                    ww = w * 1.18
                    cur_img = isaret_img(i, "simdi", ww)
                    cur_xy = (x - (ww - w) / 2 - 24, 296 - (ww - w) - 24)
                else:
                    durum = "bitti" if i <= pg.no and not (pg.kind == "delil" and i == pg.no) else "sirada"
                    if pg.kind == "delil" and i < pg.no:
                        durum = "bitti"
                    isaret(pen, x, 296, w, i, durum)
                x += w + gap
        out = (pen.done(), cur_img, cur_xy)
        self._c[key] = out
        return out

    def draw_top(self, img: Image.Image, pg: Sayfa, lt: float) -> None:
        base, cur, xy = self.top_row(pg)
        K.put(img, base, TOP[0], TOP[1], clip=CLIP)
        if cur is not None:
            k = bump(lt / 0.32, 1.22) if lt < 0.32 else 1.0
            K.put(img, cur, xy[0], xy[1], k=k, clip=CLIP)

    # ------------------------------------------------------------ iç sayfa: manşet ve belgeler
    def scene_title(self, i: int) -> tuple[list[str], int]:
        """Sahnenin başlık satırları (boşlar atılır) ve vurgulu satırın bu listedeki sırası (yoksa -1)."""
        s = self.scenes[i]
        lines, hl = [], -1
        for k, x in enumerate(s.headline):
            if x and x.strip():
                if k == s.highlight_line:
                    hl = len(lines)
                lines.append(up(x))
        return lines, hl

    def manset(self, lines, hl, top, max_h, seed, center=False, sizes=None, tek=False):
        """Manşet etiketleri (1x görüntüler ve ekran konumları) ve alt kenar."""
        size, rows = manset_olc(lines, hl, X1 - X0 - 10, max_h, tek=tek, **({"sizes": sizes} if sizes else {}))
        labs = []
        y = top
        rh = max_satir_h(lines, size)
        for r, row in enumerate(rows):
            ims = []
            for L, i in row:
                bg = RED if i == hl else INK
                lab = K.torn_label(L, size, OFF, bg, seed + i)
                ims.append((lab, lab.render((-1.6, 1.3, -0.8, 1.0)[(i + r) % 4], (6, 8, 0, 0.9))))
            tot = sum(l.w for l, _ in ims) + 12 * (len(ims) - 1)
            x = X0 + 2 if not center else (X0 + X1) / 2 - tot / 2
            for lab, im in ims:
                cx, cy = x + lab.w / 2, y + rh / 2
                labs.append((im, cx - im.width / 2, cy - im.height / 2))
                x += lab.w + 12
            y += rh + 12
        return labs, y - 12

    def page_parts(self, pg: Sayfa, si: int) -> dict:
        """Bir iç sayfa sahnesinin parçaları: manşet etiketleri, belge (1x katman ve konum), asılı delil etiketi, son
        hâlin CONTENT katmanı ve kesme kutusu. si: sayfanın belgesini getiren sahne."""
        key = ("page", si)
        if key in self._c:
            return self._c[key]
        spec = self.scenes[si]
        c = spec.card or {}
        lines, hl = self.scene_title(si)
        out: dict = {"labels": [], "doc": None, "tag": None, "dyn": None}
        if pg.kind == "ara" or (pg.kind == "delil" and pg.belge == "not"):
            if not lines:
                lines = [K.fit_words(up(spec.narration).rstrip(".,!?…"), "anton", 100, X1 - X0 - 60)]
            labs, bot = self.manset(lines, hl, 0, 600, 640 + si, center=True, tek=True,
                                    sizes=(140, 132, 124, 116, 108, 100, 92, 84, 76, 68, 60, 52))
            h = bot
            y0 = (MANSET_Y + DOC_Y1) / 2 - h / 2 - 10
            out["labels"] = [(im, x, y + y0) for im, x, y in labs]
            out["box"] = (X0, y0, X1, y0 + h)
            self.delil_etiketi(out, pg, X0 + 10, y0 + h + 40)
        else:
            labs, bot = self.manset(lines, hl, MANSET_Y, 250, 90 + si * 7) if lines else ([], MANSET_Y - 26)
            out["labels"] = labs
            top = bot + 34
            builder = {"ifade": self.doc_ifade, "olcum": self.doc_olcum, "torba": self.doc_torba,
                       "cizim": self.doc_cizim, "kayit": self.doc_kayit}.get(pg.belge if si == pg.scenes[0]
                                                                            else self.belge_of(si), self.doc_kayit)
            builder(out, pg, spec, c, top)
        # son hâl: CONTENT katmanı
        lay = Image.new("RGBA", (CONTENT[2] - CONTENT[0], CONTENT[3] - CONTENT[1]), (0, 0, 0, 0))
        if out["doc"] is not None:
            im, x, y = out["doc"]
            K._comp(lay, im, x - CONTENT[0], y - CONTENT[1])
        if out.get("dyn") is not None:
            im, x, y = out["dyn"](1e9)
            K._comp(lay, im, x - CONTENT[0], y - CONTENT[1])
        for im, x, y in out["labels"]:
            K._comp(lay, im, x - CONTENT[0], y - CONTENT[1])
        for part in ("tag", "chip"):
            if out.get(part) is not None:
                im, x, y = out[part]
                K._comp(lay, im, x - CONTENT[0], y - CONTENT[1])
        out["final"] = lay
        self._c[key] = out
        return out

    def belge_of(self, si: int) -> str:
        return BELGE.get(sahne_turu(self.scenes[si], si, self.n), "")

    def _sprite_img(self, sp: K.Sprite, rot: float) -> Image.Image:
        im = sp.render_ss(rot)
        return im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)

    def _place(self, out, im: Image.Image, cx, top_y, shadow_pad=0):
        """Belge görüntüsünü (1x) yatayda cx merkezli, üst kenarı top_y olacak biçimde yerleştirir."""
        x, y = cx - im.width / 2, top_y - 30          # 30: kâğıt sprite kenar payı (üst kenar = top_y)
        out["doc"] = (im, x, y)
        out["box"] = (x + 30, y + 30, x + im.width - 30, y + im.height - 30)
        return x, y

    def delil_etiketi(self, out, pg, x, y, rot=-7.0):
        """Belgenin alt kenarından ipiyle sarkan sarı DELİL n etiketi; tutanağın üstünde biter."""
        if pg.kind != "delil" or not pg.no:
            return
        tag = asili_etiket(f"DELİL {pg.no}", 40, rot=rot, ip=50)
        tag = tag.resize((tag.width // SS, tag.height // SS), Image.LANCZOS)
        y = min(y, TUTANAK[1] - 30 - tag.height)
        out["tag"] = (tag, x, y)

    def doc_ifade(self, out, pg, spec, c, top):
        """Tanık ifadesi: daktiloyla yazılmış alıntı, mavi imza ve isim; ataş ve asılı delil etiketi."""
        alinti = (c.get("card_label") or c.get("label") or "").strip().strip('"“”')
        note = (c.get("card_note") or c.get("note") or "").strip()
        parts = [p.strip() for p in note.split("·") if p.strip()]
        kim = parts[0] if parts else ""
        ayrinti = " · ".join(parts[1:])
        w, pad = 760, 44
        avail = DOC_Y1 - top
        for maxq, maxl in ((60, 4), (54, 4), (48, 5), (42, 5), (36, 6)):
            qs, qlines = ortala_ve_sigdir(f"“{alinti}”", "courier", w - 2 * pad, maxq, max(28, maxq - 12), maxl)
            lh = qs * 1.26
            q0 = pad + 58 + 30 + cap_h("courier", qs)
            yb = q0 + (len(qlines) - 1) * lh + (78 if kim else 30)
            h = yb + (76 if kim else 0)
            if h + 40 <= avail:
                break
        sp = kagit(w, h)
        sp.text((pad, pad + 32), "TANIK İFADESİ", "anton", 40, INK)
        if ayrinti:
            aw = w - 2 * pad - K.tw("TANIK İFADESİ", "anton", 40) - 30
            sp.text((w - pad, pad + 30), K.fit_words(ayrinti, "courier", 28, aw), "courier", 28, DGREY, anchor="rs")
        sp.line([(pad, pad + 52), (w - pad, pad + 52)], INK + (255,), 3)
        y = q0
        for L in qlines:
            sp.text((pad, y), L, "courier", qs, INK)
            y += lh
        if kim:
            # mavi tükenmez imza: halkalı el yazısı + alt çizgi kuyruğu
            sx = w - pad - 300
            pts = []
            for i in range(140):
                u = i / 139
                pts.append((sx + 210 * u + 11 * math.cos(2 * math.pi * 6 * u),
                            yb - 24 - 15 * math.sin(2 * math.pi * 6 * u) * (1 - 0.45 * u) - 8 * u))
            pts += [(sx + 226, yb - 30), (sx + 150, yb - 6), (sx + 30, yb - 2)]
            sp.line(pts, (38, 58, 132, 255), 3.6)
            sp.line([(sx - 10, yb + 2), (w - pad, yb + 2)], INK + (255,), 2)
            kw = K.fit_words("— " + kim, "courier", 32, w - 2 * pad)
            sp.text((w - pad, yb + 44), kw, "courier", 32, INK, anchor="rs")
        im = self._sprite_img(sp, 1.2)
        x, y = self._place(out, im, 470, top + 20 + max(0, (avail - 40 - h) * 0.3))
        ust = 70                                   # ataşın kâğıdın üstünden taşan kısmı
        pen = K.Pen(x, y - ust, x + im.width, y + 90)
        atac(pen, x + 300, y - 40, 40, rot=4)
        big = Image.new("RGBA", (im.width, im.height + ust), (0, 0, 0, 0))
        big.alpha_composite(im, (0, ust))
        big.alpha_composite(pen.done())
        out["doc"] = (big, x, y - ust)
        self.delil_etiketi(out, pg, x + 40, y + im.height - 44)

    def doc_olcum(self, out, pg, spec, c, top):
        """Ölçüm tutanağı: büyük sayı 0'dan değere sayar, bu arada sarı şerit metre makarasından değere kadar açılır;
        birim ve kaynak notu. Sayı dış seste söylendiği anda oturur."""
        raw = (c.get("card_value") or c.get("value") or "").strip()
        unit = up(c.get("card_label") or c.get("label") or "")
        note = (c.get("card_note") or c.get("note") or "").strip()
        parsed = K.parse_value(raw)
        w, pad = 780, 44
        avail = DOC_Y1 - top - 20 - 22             # 20: üst boşluk, 22: gölge ve eğiklik payı
        size = 200
        dw = lambda s, z: sum(max(K.tw(d, "anton", z) for d in "0123456789") if ch.isdigit() else K.tw(ch, "anton", z)
                              for ch in s)
        final = raw or "?"
        while (dw(final, size) > w - 2 * pad - 20 or cap_h("anton", size) + 330 > avail) and size > 60:
            size -= 6
        us = 58
        while unit and K.tw(unit, "anton", us) > w - 2 * pad and us > 24:
            us -= 2
        unit = K.fit_words(unit, "anton", us, w - 2 * pad) if unit else unit
        capn = cap_h("anton", size)
        hdr = pad + 52
        nb = hdr + 40 + capn                    # sayının tabanı
        ub = nb + (26 + cap_h("anton", us) if unit else 0)
        tape_y = ub + 60                        # şeridin ortası
        h = tape_y + 64
        sp = kagit(w, h)
        sp.text((pad, pad + 32), "ÖLÇÜM", "anton", 40, INK)
        if note:
            nw = w - 2 * pad - K.tw("ÖLÇÜM", "anton", 40) - 30
            sp.text((w - pad, pad + 30), K.fit_words(note, "courier", 28, nw), "courier", 28, DGREY, anchor="rs")
        sp.line([(pad, pad + 52), (w - pad, pad + 52)], INK + (255,), 3)
        if unit:
            sp.text((w / 2, ub), unit, "anton", us, INK, anchor="ms")
        # makara (şeridin kutusu): solda
        cx0, cy0 = pad + 40, tape_y
        sp.dot(cx0 + 5, cy0 + 6, 44, INK + (255,))
        sp.dot(cx0, cy0, 44, RED + (255,))
        sp.d.ellipse([*sp.p(cx0 - 44, cy0 - 44), *sp.p(cx0 + 44, cy0 + 44)], outline=INK + (255,), width=int(5 * SS))
        sp.dot(cx0, cy0, 16, OFF + (255,))
        sp.d.ellipse([*sp.p(cx0 - 16, cy0 - 16), *sp.p(cx0 + 16, cy0 + 16)], outline=INK + (255,), width=int(4 * SS))
        im = self._sprite_img(sp, -1.0)
        x, y = self._place(out, im, 470, top + 20 + max(0, (avail - h) * 0.3))
        self.delil_etiketi(out, pg, x + 40, y + im.height - 44)
        m = 30
        rot = -1.0
        tx0, tx1 = pad + 84, w - pad - 10       # şeridin başı ve en uzak ucu (kâğıt içinde)
        land = None
        digits = re.sub(r"\D", "", raw)
        if digits:
            for wd in spec.words:
                if digits in re.sub(r"\D", "", wd.text):
                    land = max(0.6, wd.start - pg.start + 0.05)
                    break
        if land is None:
            land = 1.2
        out["count"] = (max(0.5, land - 0.8), land)
        cache: dict = {}

        def dyn(lt: float):
            c0, c1 = out["count"]
            e = 1.0 if parsed is None else K.ease_out_cubic((lt - c0) / max(0.05, c1 - c0))
            key = round(e, 3) if e < 1 else 1.0
            if key in cache:
                return cache[key]
            spd = K.Sprite(w, h, margin=m)
            # sayı (rakamlar sabit genişlikte: sayarken titremez)
            if parsed is None:
                s = raw or "?"
            else:
                pre, v, dec, grouped, suf = parsed
                cur = v * e
                if dec == 0:
                    cur = math.floor(cur + 1e-9) if e < 1 else v
                s = pre + K.fmt_value(cur, dec, grouped) + suf
            dwid = max(K.tw(d, "anton", size) for d in "0123456789")
            tot = dw(s, size)
            xx = w / 2 - tot / 2
            for ch in s:
                cw = dwid if ch.isdigit() else K.tw(ch, "anton", size)
                spd.text((xx + cw / 2, nb), ch, "anton", size, INK, anchor="ms")
                xx += cw
            # şerit metre
            hx = tx0 + (tx1 - tx0) * e
            hw = 26
            if hx > tx0 + 4:
                spd.polygon([(tx0 + 5, tape_y - hw + 6), (hx + 5, tape_y - hw + 6), (hx + 5, tape_y + hw + 6),
                             (tx0 + 5, tape_y + hw + 6)], INK + (255,))
                spd.polygon([(tx0, tape_y - hw), (hx, tape_y - hw), (hx, tape_y + hw), (tx0, tape_y + hw)],
                            YELLOW + (255,))
                spd.line([(tx0, tape_y - hw), (hx, tape_y - hw), (hx, tape_y + hw), (tx0, tape_y + hw)],
                         INK + (255,), 4)
                k, tt = 0, tx0 + 10
                while tt < hx - 6:
                    ln = 22 if k % 10 == 0 else 15 if k % 5 == 0 else 9
                    spd.line([(tt, tape_y - hw), (tt, tape_y - hw + ln)], INK + (255,), 3 if k % 10 == 0 else 2)
                    tt += 9
                    k += 1
                # uç: metal kanca
                spd.polygon([(hx, tape_y - hw - 8), (hx + 14, tape_y - hw - 8), (hx + 14, tape_y + hw + 2),
                             (hx, tape_y + hw + 2)], (178, 176, 170, 255))
                spd.line([(hx, tape_y - hw - 8), (hx + 14, tape_y - hw - 8), (hx + 14, tape_y + hw + 2),
                          (hx, tape_y + hw + 2), (hx, tape_y - hw - 8)], INK + (255,), 4)
            # makaranın ağzı şeridin üstünde
            spd.dot(pad + 40, tape_y, 16, OFF + (255,))
            spd.d.ellipse([*spd.p(pad + 24, tape_y - 16), *spd.p(pad + 56, tape_y + 16)], outline=INK + (255,),
                          width=int(4 * SS))
            res = (self._sprite_img(spd, rot), x, y)
            if len(cache) > 64:
                cache.clear()
            cache[key] = res
            return res
        out["dyn"] = dyn

    def doc_torba(self, out, pg, spec, c, top):
        """Delil torbası: şeffaf plastik (ısıl yapışma kenarı, parlama), üstte kırmızı DELİL bandı ve yazı alanı,
        altında kilit şeridi; içinde fotoğraf. Fotoğrafın künyesi sarı çipte."""
        ph = gorsel_ac(spec.image) or gorsel_ac(spec.sprite)
        note = (c.get("card_note") or c.get("note") or "").strip()
        konu = note or K.tr_lower(" ".join(x.strip() for x in spec.headline if x.strip()))
        avail = DOC_Y1 - top
        w = 640
        h = int(min(700, max(380, avail - 40)))
        S = SS
        m = 30
        im = Image.new("RGBA", (int((w + 2 * m) * S), int((h + 2 * m) * S)), (0, 0, 0, 0))

        def R(x0, y0, x1, y1):
            return [(m + x0) * S, (m + y0) * S, (m + x1) * S, (m + y1) * S]

        seal, band_h = 16, 84
        d = ImageDraw.Draw(im)
        d.rounded_rectangle(R(SHADOW[0], SHADOW[1], w + SHADOW[0], h + SHADOW[1]), 12 * S, fill=INK + (255,))
        d.rounded_rectangle(R(0, 0, w, h), 12 * S, fill=K.blend(MANILA_IC, WHITE, 0.35) + (255,))
        ky = seal + band_h + 40
        cw, chh = w - 2 * seal - 44, h - ky - seal - 22
        if ph is not None:
            if spec.image is not None and ph is not None and gorsel_ac(spec.image) is not None:
                card = K.cover(ph.convert("RGB"), int(cw * S), int(chh * S)).convert("RGBA")
            else:
                card = Image.new("RGBA", (int(cw * S), int(chh * S)), FIS + (255,))
                cz = cizim_kirp(ph)
                k = min((cw - 60) * S / cz.width, (chh - 40) * S / cz.height)
                cz = cz.resize((max(1, int(cz.width * k)), max(1, int(cz.height * k))), Image.LANCZOS)
                card.alpha_composite(cz, ((card.width - cz.width) // 2, (card.height - cz.height) // 2))
            ImageDraw.Draw(card).rectangle([0, 0, card.width - 1, card.height - 1], outline=INK + (255,),
                                           width=int(4 * S))
            card = card.rotate(1.4, resample=Image.BICUBIC, expand=True)
            im.alpha_composite(card, (int((m + (w - cw) / 2) * S - (card.width - cw * S) / 2),
                                      int((m + ky) * S - (card.height - chh * S) / 2)))
        film = Image.new("RGBA", im.size, (0, 0, 0, 0))
        fd = ImageDraw.Draw(film)
        fd.rounded_rectangle(R(0, 0, w, h), 12 * S, fill=(255, 255, 255, 30))
        for ax, ay, bx, by, wd, al in [(w * 0.70, 0, w * 0.14, h, 58, 46), (w * 0.88, 0, w * 0.34, h, 18, 70),
                                       (w * 1.05, h * 0.25, w * 0.70, h, 34, 36), (w * 0.10, 0, -w * 0.2, h * 0.5, 22, 44)]:
            fd.line([((m + ax) * S, (m + ay) * S), ((m + bx) * S, (m + by) * S)], fill=(255, 255, 255, al),
                    width=int(wd * S))
        fd.rounded_rectangle(R(0, 0, w, h), 12 * S, outline=(255, 255, 255, 120), width=int(seal * S))
        fd.rounded_rectangle(R(seal, seal, w - seal, h - seal), 4 * S, outline=(150, 140, 120, 150), width=int(2 * S))
        clip = Image.new("L", im.size, 0)
        ImageDraw.Draw(clip).rounded_rectangle(R(0, 0, w, h), 12 * S, fill=255)
        film.putalpha(Image.fromarray(np.minimum(np.asarray(film.getchannel("A")), np.asarray(clip))))
        im.alpha_composite(film)
        d = ImageDraw.Draw(im)
        bx0, by0, bx1, by1 = seal + 6, seal + 6, w - seal - 6, seal + 6 + band_h
        d.rectangle(R(bx0, by0, bx1, by1), fill=RED + (255,))
        lab = f"DELİL {pg.no}"
        K.draw_text(d, ((m + bx0 + 24) * S, (m + by0 + 64) * S), lab, "anton", 52 * S, OFF + (255,), anchor="ls")
        kx = bx0 + 24 + K.tw(lab, "anton", 52) + 26
        d.rectangle(R(kx, by0 + 16, bx1 - 16, by1 - 16), fill=FIS + (255,))
        # konu önce küçülerek sığdırılır (22 px'e kadar), yine sığmazsa kelime sınırında kısaltılır
        kw, ks = bx1 - 16 - kx - 28, 30
        while ks > 22 and K.tw("konu: " + konu, "courier", ks) > kw:
            ks -= 2
        kt = K.fit_words("konu: " + konu, "courier", ks, kw)
        K.draw_text(d, ((m + kx + 16) * S, (m + by0 + band_h / 2 + ks / 3) * S), kt, "courier", ks * S, INK + (255,),
                    anchor="ls")
        zy = by1 + 16
        d.line([((m + seal) * S, (m + zy) * S), ((m + w - seal) * S, (m + zy) * S)], fill=(120, 116, 108, 255),
               width=int(3 * S))
        d.line([((m + seal) * S, (m + zy + 9) * S), ((m + w - seal) * S, (m + zy + 9) * S)], fill=(160, 156, 148, 255),
               width=int(3 * S))
        xx = seal + 6
        while xx < w - seal - 6:
            d.line([((m + xx) * S, (m + zy) * S), ((m + xx) * S, (m + zy + 9) * S)], fill=(140, 136, 128, 255),
                   width=int(2 * S))
            xx += 9
        d.rounded_rectangle(R(0, 0, w, h), 12 * S, outline=INK + (255,), width=int(4 * S))
        im = im.rotate(-2.0, resample=Image.BICUBIC, expand=True)
        im = im.resize((im.width // S, im.height // S), Image.LANCZOS)
        x, y = self._place(out, im, 84 + w / 2 + 10, top - 10)
        credit = K.credit_chip(dict(c.get("credit") or {}))
        if credit and spec.image is not None:
            pen = K.Pen(0, 0, 700, 90)
            K.chip_label(pen, 6, 6, credit, size=26, rot=2.0, max_w=560)
            chip = pen.done()
            bb = chip.getchannel("A").getbbox()
            chip = chip.crop(bb) if bb else chip
            out["chip"] = (chip, x + 40, y + im.height - 64)

    def doc_cizim(self, out, pg, spec, c, top):
        """İğneli çizim: beyaz çizim kâğıdı, üst ortada kırmızı raptiye; not (card_note) sarı çipte."""
        pic = gorsel_ac(spec.sprite) or gorsel_ac(spec.image)
        note = (c.get("card_note") or c.get("note") or "").strip()
        top += 30                                  # raptiyenin başı manşete değmesin
        avail = DOC_Y1 - top
        w = 620
        h = int(min(640, max(340, avail - (70 if note else 30))))
        sp = kagit(w, h, renk=WHITE)
        if pic is not None:
            if spec.sprite is None and spec.image is not None:
                ph = K.cover(pic.convert("RGB"), int((w - 60) * SS), int((h - 60) * SS)).convert("RGBA")
                sp.im.alpha_composite(ph, (int((sp.m + 30) * SS), int((sp.m + 30) * SS)))
            else:
                cz = cizim_kirp(pic)
                k = min((w - 70) * SS / cz.width, (h - 70) * SS / cz.height)
                cz = cz.resize((max(1, int(cz.width * k)), max(1, int(cz.height * k))), Image.LANCZOS)
                sp.im.alpha_composite(cz, (int((sp.m + w / 2) * SS - cz.width / 2),
                                           int((sp.m + h / 2 + 8) * SS - cz.height / 2)))
        im = self._sprite_img(sp, -1.6)
        x, y = self._place(out, im, 84 + w / 2 + 6, top + max(0, (avail - h - (70 if note else 30)) * 0.3))
        pen = K.Pen(x, y, x + im.width, y + 80)
        raptiye(pen, x + im.width / 2, y + 52, 54)
        pin = pen.done()
        big = im.copy()
        big.alpha_composite(pin, (0, 0))
        out["doc"] = (big, x, y)
        if note:
            pen = K.Pen(0, 0, 760, 90)
            K.chip_label(pen, 6, 6, note, size=28, rot=-1.5, max_w=620)
            chip = pen.done()
            bb = chip.getchannel("A").getbbox()
            chip = chip.crop(bb) if bb else chip
            out["chip"] = (chip, x + 24, y + im.height - 58)
        tag = asili_etiket(f"DELİL {pg.no}", 40, rot=8, ip=46)
        tag = tag.resize((tag.width // SS, tag.height // SS), Image.LANCZOS)
        out["tag"] = (tag, min(X1 - tag.width + 10, x + im.width - 30), y + 60)

    def doc_kayit(self, out, pg, spec, c, top):
        """İddia kaydı (compare): kırmızı İDDİA kutusunun altında inanış, kesik çizginin altında BULGU kutusu ve
        doğrusu (yıldızlı kelime kırmızı), en altta kaynak notu. BULGU sahnenin ortasında yazılır; hüküm EFSANE'yse
        aynı anda inanışın yanlış kelimesi kırmızı kalemle çizilir."""
        myth = up((c.get("card_myth") or c.get("myth") or self.iddia).replace("*", "").strip())
        fact = (c.get("card_fact") or c.get("fact") or "").strip()
        note = (c.get("card_note") or c.get("note") or "").strip()
        w, pad = 780, 44
        inner = w - 2 * pad
        rich = K._rich(up(fact)) if fact else []
        emph = {t for t, e in rich if e}
        avail = DOC_Y1 - top - SHADOW[1]
        for big in (88, 80, 72, 64, 56, 48):
            ms, mlines = ortala_ve_sigdir(myth, "anton", inner, big, max(40, big - 16), 2)
            fs, flines = (ortala_ve_sigdir(" ".join(t for t, _ in rich), "anton", inner, big, max(40, big - 16), 2)
                          if rich else (0, []))
            y = pad + 40                                   # İDDİA kutusunun tabanı
            yb_m = []
            gm = satir_araliklari(mlines, "anton", ms, ms * 0.12)
            y += 8 + 28 + max(cap_h("anton", ms), -K.tbox(mlines[0], "anton", ms)[1])
            for i in range(len(mlines)):
                yb_m.append(y)
                if i < len(gm):
                    y += gm[i]
            y += max(0.0, K.tbox(mlines[-1], "anton", ms)[3])
            div = y + 30
            yb_f = []
            if fs:
                yb2 = div + 30 + 40
                y = yb2 + 8 + 28 + max(cap_h("anton", fs), -K.tbox(flines[0], "anton", fs)[1])
                gf = satir_araliklari(flines, "anton", fs, fs * 0.12)
                for i in range(len(flines)):
                    yb_f.append(y)
                    if i < len(gf):
                        y += gf[i]
                y += max(0.0, K.tbox(flines[-1], "anton", fs)[3])
            note_y = y + 50 if note else y
            h = note_y + (28 if note else 36)
            if h <= avail:
                break

        def kutu(sp_, x, yb, text, col):
            tw_ = K.tw(text, "anton", 34)
            sp_.line([(x, yb - 40), (x + tw_ + 24, yb - 40), (x + tw_ + 24, yb + 8), (x, yb + 8), (x, yb - 42)],
                     col + (255,), 4)
            sp_.text((x + 12, yb), text, "anton", 34, col)

        sp = kagit(w, h)
        kutu(sp, pad, pad + 40, "İDDİA", RED)
        sp.text((w - pad, pad + 34), "yaygın inanış", "courier", 28, DGREY, anchor="rs")
        for L, yb in zip(mlines, yb_m):
            sp.text((pad, yb), L, "anton", ms, INK)
        xx = pad
        while xx < w - pad:                                # kesik ayırıcı
            sp.line([(xx, div), (min(xx + 14, w - pad), div)], CIZGI + (255,), 3)
            xx += 24
        x, yy = self._place(out, self._sprite_img(sp, 0.8), 470, top + max(0.0, (avail - h) * 0.22))
        if not fs:
            return
        spf = kagit(w, h)
        spf.im = sp.im.copy()
        spf.d = ImageDraw.Draw(spf.im)
        kutu(spf, pad, div + 30 + 40, "BULGU", INK)
        for L, yb in zip(flines, yb_f):
            xx = pad
            for wd in L.split():
                spf.text((xx, yb), wd, "anton", fs, RED if wd in emph else INK)
                xx += K.tw(wd + " ", "anton", fs)
        if note:
            spf.text((pad, note_y), K.fit_words(note, "courier", 28, inner), "courier", 28, DGREY)
        for li, a_, b_ in self.strike_words(mlines):
            words = mlines[li].split()
            x0 = pad + (K.tw(" ".join(words[:a_]) + " ", "anton", ms) if a_ else 0)
            x1 = pad + K.tw(" ".join(words[:b_ + 1]), "anton", ms)
            kirmizi_cizik(spf, x0, x1, yb_m[li] - cap_h("anton", ms) * 0.48, 15 + li, w=max(8, ms * 0.1))
        out["doc_before"] = out["doc"]
        out["doc"] = (self._sprite_img(spf, 0.8), x, yy)
        dur = max(0.1, self.scenes[pg.scenes[-1]].end - self.scenes[pg.scenes[0]].start)
        out["reveal"] = min(1.6, dur * 0.45)

    # ------------------------------------------------------------ iç sayfa çizimi
    def draw_content(self, img: Image.Image, pg: Sayfa, lt: float, entry: float, si: int) -> None:
        """Sayfanın içeriği; entry: girişin başladığı an (sayfa başından). Giriş: manşet etiketleri sırayla patlar,
        belge masaya bırakılır gibi oturur, delil etiketi ve çip sonra gelir."""
        P = self.page_parts(pg, si)
        e = lt - entry
        settled = e > 0.75 and P.get("dyn") is None and ("reveal" not in P or lt > P["reveal"] + 0.3)
        if settled:
            K.put(img, P["final"], CONTENT[0], CONTENT[1], clip=CLIP)
            return
        # belge
        if P["doc"] is not None or P.get("dyn") is not None:
            p = (e - 0.08) / 0.28
            if p > 0:
                k = K.lerp(1.07, 1.0, K.ease_out_cubic(p)) if p < 1 else 1.0
                al = min(1.0, p * 2.5)
                dy = -26 * (1 - K.ease_out_cubic(p)) if p < 1 else 0.0
                doc = P["doc"]
                if "reveal" in P and lt < P["reveal"]:
                    doc = P["doc_before"]
                elif "reveal" in P and lt - P["reveal"] < 0.25:     # BULGU yazılınca fiş hafifçe zıplar
                    k *= bump((lt - P["reveal"]) / 0.25, 1.025)
                if doc is not None:
                    im, x, y = doc
                    K.put(img, im, x, y + dy, k=k, alpha=al, clip=CLIP)
                if P.get("dyn") is not None:
                    im, x, y = P["dyn"](lt)
                    K.put(img, im, x, y + dy, k=k, alpha=al, clip=CLIP)
        for j, (im, x, y) in enumerate(P["labels"]):
            pl = (e - 0.07 * j) / 0.24
            if pl > 0:
                K.put(img, im, x, y, k=ease_pop(pl, 1.1), clip=CLIP)
        for part, t0 in (("chip", 0.42), ("tag", 0.5)):
            if P.get(part) is not None:
                pc = (e - t0) / 0.26
                if pc > 0:
                    im, x, y = P[part]
                    K.put(img, im, x, y, k=ease_pop(pc, 1.12), clip=CLIP)

    def page_scene(self, pg: Sayfa, t: float) -> int:
        """Sayfanın o an gösterdiği belgenin sahnesi: sayfanın ilk sahnesi, ya da kendi belgesi olan sonraki sahne."""
        out = pg.scenes[0]
        for i in pg.scenes[1:]:
            if self.scenes[i].start <= t and self.belge_of(i) and pg.kind == "delil":
                out = i
        return out

    def final_content(self, pg: Sayfa) -> tuple[Image.Image, tuple]:
        si = self.page_scene(pg, pg.end - 0.01)
        P = self.page_parts(pg, si)
        return P["final"], P.get("box", (X0, 500, X1, 1100))

    # ------------------------------------------------------------ hüküm
    def hukum_parts(self, pg: Sayfa) -> dict:
        """Hüküm: kapak geri kapanır; İDDİA fişi üstte, damga son satırın altına iner; altında GERÇEK şeridi (sonuç
        sahnesinin başlığı, yoksa compare kartının doğrusu); soru gelince tutanağa SENCE? yapışır, 'Yorumlara yaz'
        söylenince YORUMLARA YAZ çıkartması belirir. Damga, şerit ve SENCE? satırı tutanağın üstüne sığana kadar
        küçülür."""
        key = ("hukum", pg.scenes[0])
        if key in self._c:
            return self._c[key]
        n = self.n
        # sonuç sahnesi: son sahneden (soru) önceki son sahne (cta kartı değilse)
        sonuc_i = None
        for i in pg.scenes:
            if i != n - 1 and sahne_turu(self.scenes[i], i, n) != "cta":
                sonuc_i = i
        strip_words: list[tuple[str, bool]] = []
        if sonuc_i is not None:
            lines, hl = self.scene_title(sonuc_i)
            for li, L in enumerate(lines):
                strip_words += [(w, li == hl) for w in L.split()]
        if not strip_words:
            for s in self.scenes:
                f = ((s.card or {}).get("card_fact") or (s.card or {}).get("fact") or "").strip()
                if f:
                    strip_words = [(up(t), e) for t, e in K._rich(f)]
                    break
        stamp_alt = self.hukum or "KAPANDI"
        stamp_ust = "HÜKÜM" if self.hukum else "DOSYA"
        # alt sıra: tutanağın sol üst köşesinde SENCE? sekmesi, yanında YORUMLARA YAZ çıkartması (Makas'a değmez)
        lab_sence = K.torn_label("SENCE?", 64, OFF, RED, 57)
        sence_top = TUTANAK[1] + 24 - lab_sence.h
        sx = X0 + 6 + lab_sence.w + 20
        sticker = K.cta_sticker(up(K.CtaCard.BUTTON), MASKOT_X0 - sx - 20, size=60)   # 20: 2° eğiklik payı
        top = 282
        text = up(self.iddia).replace("*", "")
        cw, pad, head_h = 816, 46, 88
        inner = cw - 2 * pad
        best = None
        damgalar: dict = {}

        def serit(room, en_az=36):
            """GERÇEK şeridinin en büyük yazısı (en çok iki satır, en az en_az px) room yüksekliğine sığacak biçimde;
            sığmazsa None."""
            if not strip_words:
                return 0, [], 0.0
            for g in (g for g in (84, 78, 72, 66, 60, 54, 48, 42, 36) if g >= en_az):
                gs_, gl_ = ortala_ve_sigdir(" ".join(w for w, _ in strip_words), "anton", inner - 10, g, g, 2)
                if not gl_ or len(gl_) > 2 or any(K.tw(L, "anton", gs_) > inner - 10 for L in gl_):
                    continue
                gp = satir_araliklari(gl_, "anton", gs_, gs_ * 0.10)
                ga = max(cap_h("anton", gs_), -K.tbox(gl_[0], "anton", gs_)[1])
                gh_ = SERIT_UST + ga + sum(gp) + max(0.0, K.tbox(gl_[-1], "anton", gs_)[3]) + 26
                if gh_ + SHADOW[1] + 7 <= room:      # 7: 0,8° eğik şeridin taşan köşesi
                    return gs_, gl_, gh_
            return None

        claims = []
        for csize in (100, 92, 84, 76, 68, 60):
            cl = sar_genislik(text.split(), "anton", csize, lambda i: inner)
            if cl and len(cl) <= 3:
                claims.append((csize, cl, iddia_karti(cl, csize, w=cw, head_h=head_h, alt_bosluk=0)[1]))

        def dene(csize, cl, info0, size_alt, en_az=36):
            if K.tw(stamp_alt, "anton", size_alt) > 600:
                return None
            if size_alt not in damgalar:
                damgalar[size_alt] = damga(stamp_ust, stamp_alt, size_alt=size_alt, rot=7)
            st = damgalar[size_alt]
            bb = st.getbbox()
            ust_kenar, alt_kenar = (st.height / 2 - bb[1]) / SS, (bb[3] - st.height / 2) / SS
            off = ust_kenar - 34                      # damganın üst çerçevesi son satırın alt kısmını keser
            alt = max(30.0, off + alt_kenar + 26 - (info0["h"] - info0["lines"][-1][3]))
            bot = top + info0["h"] + alt
            gy = bot + 34
            sr = serit(STRIP_Y1 - gy, en_az)
            if sr is None or bot + SHADOW[1] > STRIP_Y1:
                return None
            return (csize, cl, st, off, alt, *sr, gy)

        # önce büyük damga (hükmün kahramanı), okunur iddia (>= 76 px) ve okunur şerit (>= 54 px); sonra şerit
        # küçülebilir; en son iddia önce, damga küçülerek
        sira = [(c, z, 54) for z in range(184, 119, -8) for c in claims if c[0] >= 76]
        sira += [(c, z, 36) for z in range(184, 135, -8) for c in claims if c[0] >= 76]
        sira += [(c, z, 36) for c in claims for z in range(184, 103, -8)]
        for (csize, cl, info0), size_alt, en_az in sira:
            best = dene(csize, cl, info0, size_alt, en_az)
            if best:
                break
        if best is None:
            st = damga(stamp_ust, stamp_alt, size_alt=104, rot=7)
            bb = st.getbbox()
            ust_kenar, alt_kenar = (st.height / 2 - bb[1]) / SS, (bb[3] - st.height / 2) / SS
            csize = 60
            while True:
                csize, cl = kucult_sar(text.split(), "anton", csize, inner)
                info0 = iddia_karti(cl, csize, w=cw, head_h=head_h, alt_bosluk=0)[1]
                off = ust_kenar - 34
                alt = max(30.0, off + alt_kenar + 26 - (info0["h"] - info0["lines"][-1][3]))
                if top + info0["h"] + alt + SHADOW[1] <= STRIP_Y1 or csize <= 24:
                    break
                csize -= 6
            best = (csize, cl, st, off, alt, 54, [], 0, 0)
        csize, cl, st, off, alt, gs, gl, gh, gy = best
        sp, info = iddia_karti(cl, csize, w=cw, head_h=head_h, alt_bosluk=alt)
        cx, rot = 492, -1.2
        cy = top + info["h"] / 2
        pen = K.Pen(0, 0, W, H)
        yapistir(pen, sp, cx, cy, rot)
        atac(pen, 470, top - 26, 40, rot=-3)
        card = pen.done()
        _, taban = ekran_noktasi(info, cx, cy, rot, 300, info["lines"][-1][3])
        stamp = st.resize((st.width // SS, st.height // SS), Image.LANCZOS)
        scx = min(X1 - 10 - stamp.width / 2 + 40, 600)
        out = {"card": card, "stamp": stamp, "stamp_c": (scx, taban + off), "sence": lab_sence,
               "sence_top": sence_top, "strip": None}
        if gl:
            emph = {w for w, e in strip_words if e}
            sp2 = kagit(cw, gh)
            gasc = max(cap_h("anton", gs), -K.tbox(gl[0], "anton", gs)[1])
            gpitch = satir_araliklari(gl, "anton", gs, gs * 0.10)
            yb = SERIT_UST + gasc
            for li, L in enumerate(gl):
                xx = 44
                for wd in L.split():
                    sp2.text((xx, yb), wd, "anton", gs, RED if wd in emph else INK)
                    xx += K.tw(wd + " ", "anton", gs)
                if li < len(gpitch):
                    yb += gpitch[li]
            pen = K.Pen(0, gy - 60, W, gy + gh + 60)
            yapistir(pen, sp2, 492, gy + gh / 2, 0.8)
            tag = "SONUÇ" if self.hukum == "GERÇEK" else "GERÇEK"
            lab = K.torn_label(tag, 46, OFF, INK, 55)
            im = lab.render_ss(-3, (6, 8, 0, 0.9))
            pen.paste(im, X0 + 26 + lab.w / 2 - im.width / 2 / SS, gy - 8 - im.height / 2 / SS)
            out["strip"] = (pen.done(), 0, gy - 60)
            out["strip_box"] = (X0, gy, X1, gy + gh)
        out["sticker"] = sticker
        out["sticker_xy"] = (sx, TUTANAK[1] - 12 - sticker.height)   # tutanağın sekmesine değmez
        # zamanlar: damga, şerit, soru, yorum çağrısı
        ps = pg.start
        land = FLIP + 0.12 + STAMP_FALL
        out["land"] = land
        sonuc_t = (self.scenes[sonuc_i].start - ps) if sonuc_i is not None else land + 0.5
        out["strip_t"] = max(land + 0.45, sonuc_t)
        q = self.question_start(pg)
        out["q_t"] = None if q is None else self.words[q].start - 0.1 - ps
        cta = self.cta_start(pg)
        if cta is not None:
            out["cta_t"] = self.words[cta].start - 0.08 - ps
        else:
            out["cta_t"] = out["q_t"]
        self._c[key] = out
        return out

    def question_start(self, pg: Sayfa) -> int | None:
        """Hükümdeki soru cümlesinin (ya da 'Yorumlara yaz' içeren cümlenin) ilk kelimesi; yoksa son sahnenin ilk
        kelimesi."""
        if "q" in pg.extra:
            return pg.extra["q"]
        out, sent = None, []
        for i in range(pg.a, pg.b):
            sent.append(i)
            t = self.words[i].text.rstrip('"“”»)’\'')
            if t[-1:] in ".?!…":
                text = " ".join(self.words[j].text for j in sent)
                if t.endswith("?") or Q_RE.search(text):
                    out = sent[0]
                    break
                sent = []
        if out is None and pg.scenes:
            a, b = self.ranges[pg.scenes[-1]]
            out = a if a < b and pg.scenes[-1] == self.n - 1 and len(pg.scenes) > 1 else None
        pg.extra["q"] = out
        return out

    def cta_start(self, pg: Sayfa) -> int | None:
        """Sondaki 'Yorumlara yaz' çağrısının ilk kelimesi (en çok 4 kelimelik kuyruk): tutanağa yazılmaz, söylendiği
        anda YORUMLARA YAZ çıkartması belirir."""
        if "cta" in pg.extra:
            return pg.extra["cta"]
        out = None
        for i in range(max(pg.a, pg.b - 4), pg.b):
            if Q_RE.match(" ".join(self.words[j].text for j in range(i, pg.b))):
                out = i
                break
        pg.extra["cta"] = out
        return out

    def hukum_layer(self, pg: Sayfa) -> Image.Image:
        """Hükmün damgasız kapak katmanı (masası şeffaf): kapanırken genişleyen katman."""
        key = ("hukum_kat", pg.scenes[0])
        if key not in self._c:
            P = self.hukum_parts(pg)
            im = self.folder(False).copy()
            im.alpha_composite(P["card"])
            self._c[key] = im
        return self._c[key]

    def hukum_stamped(self, pg: Sayfa) -> Image.Image:
        key = ("hukum_damga", pg.scenes[0])
        if key not in self._c:
            P = self.hukum_parts(pg)
            im = self.hukum_layer(pg).copy()
            st = P["stamp"]
            carp(im, st, int(P["stamp_c"][0] - st.width / 2), int(P["stamp_c"][1] - st.height / 2))
            self._c[key] = im
        return self._c[key]

    def draw_hukum(self, img: Image.Image, pg: Sayfa, lt: float) -> None:
        P = self.hukum_parts(pg)
        land = P["land"]
        dx = dy = 0
        if land <= lt < land + SHAKE:
            p = (lt - land) / SHAKE
            amp = 11 * (1 - p) ** 1.6
            dx = int(round(amp * math.sin(p * 2 * math.pi * 3.2)))
            dy = int(round(0.6 * amp * math.cos(p * 2 * math.pi * 2.6)))
        if lt >= land:
            lay = self.hukum_stamped(pg)
        else:
            lay = self.hukum_layer(pg)
        if dx or dy:
            K._comp(img, lay, dx, dy)
        else:
            img.alpha_composite(lay)
        if land - STAMP_FALL <= lt < land:          # damga iner: büyükten hızla, saydamdan opağa
            p = (lt - (land - STAMP_FALL)) / STAMP_FALL
            k = K.lerp(2.1, 1.0, p ** 2)
            st = P["stamp"]
            sw, sh = max(1, int(st.width * k)), max(1, int(st.height * k))
            im = st.resize((sw, sh), Image.BILINEAR)
            a = 0.25 + 0.75 * p
            # inerken gölgesi: koyu, bulanık
            shd = Image.new("RGBA", im.size, (0, 0, 0, 0))
            shd.putalpha(im.getchannel("A").point(lambda v: int(v * 0.35 * p)))
            cx, cy = P["stamp_c"]
            K.put(img, shd, cx - sw / 2 + 14 * k, cy - sh / 2 + 18 * k, clip=CLIP)
            K.put(img, im, cx - sw / 2, cy - sh / 2, alpha=a, clip=CLIP)
        if P["strip"] is not None and lt >= P["strip_t"]:
            im, x, y = P["strip"]
            p = (lt - P["strip_t"]) / 0.32
            off = 0.0 if p >= 1 else 90 * (1 - K.ease_out_back(p, 1.3))
            al = min(1.0, max(0.0, p) * 3)
            K.put(img, im, x + dx, y + off + dy, alpha=al, clip=(0, SAFE[1], SAFE[2], TUTANAK[1] - 2))

    def draw_cta(self, img: Image.Image, pg: Sayfa, lt: float) -> None:
        P = self.hukum_parts(pg)
        ct = P.get("cta_t")
        if ct is not None and lt >= ct:
            st = P["sticker"]
            kk = ease_pop((lt - ct) / 0.28, 1.15) * K.cta_pulse(lt - ct)
            x, y = P["sticker_xy"]
            K.put(img, st, x, y, k=kk, clip=CLIP, anchor=(0.7, 0.5))

    # ------------------------------------------------------------ geçiş: kapak açılır / kapanır
    def flip(self, img: Image.Image, layer: Image.Image, f: float) -> None:
        """Kapak katmanı soldaki menteşesinin üstüne döner: f=1 kapalı (tam), f=0 açık (görünmez). Döndükçe koyulaşır,
        kenarında ince gölge."""
        if f <= 0.01:
            return
        x0, y0, x1, y1 = FOLD
        crop = layer.crop(FOLD)
        nw = max(1, int(round(crop.width * f)))
        im = crop.resize((nw, crop.height), Image.BILINEAR)
        dark = 0.62 + 0.38 * f
        if dark < 0.999:
            r, g, b, a = im.split()
            r, g, b = (ch.point(lambda v, d=dark: int(v * d)) for ch in (r, g, b))
            im = Image.merge("RGBA", (r, g, b, a))
        if not self.yalniz_icerik:   # kapağın kenar gölgesi (dosyanın parçası; içerik denetiminde çizilmez)
            sh = Image.new("RGBA", (40, crop.height), (0, 0, 0, 0))
            grad = np.linspace(110 * (1 - f) + 20, 0, 40).astype(np.uint8)
            sh.putalpha(Image.fromarray(np.tile(grad, (crop.height, 1))))
            img.alpha_composite(sh, (x0 + nw, y0))
        img.alpha_composite(im, (x0, y0))

    # ------------------------------------------------------------ tutanak
    def tutanak_base(self, sekme: bool) -> Image.Image:
        key = ("tut", sekme)
        if key in self._c:
            return self._c[key]
        x0, y0, x1, y1 = TUTANAK
        pen = K.Pen(x0 - 4, y0 - 26, x1 + SHADOW[0] + 4, y1 + SHADOW[1] + 4)
        pen.rr((x0 + SHADOW[0], y0 + SHADOW[1], x1 + SHADOW[0], y1 + SHADOW[1]), 10, fill=INK)
        pen.rr((x0, y0, x1, y1), 10, fill=FIS, outline=INK, width=5)
        for yy in range(int(y0) + 26, int(y1) - 12, 34):     # sürekli form kâğıdının delikleri
            pen.ell(x0 + 22, yy, 6.5, fill=CIZGI, outline=(190, 186, 176), width=1.5)
            pen.ell(x1 - 22, yy, 6.5, fill=CIZGI, outline=(190, 186, 176), width=1.5)
        if self.handle:
            a, b = "makas", self.handle
            fs = 26
            tw_ = K.tw(a + b, "courier", fs) + 32
            hx1 = x1 - 20
            pen.rr((hx1 - tw_, y0 - 22, hx1, y0 + 18), 10, fill=INK)
            pen.text(hx1 - tw_ + 16, y0 + 6, a, "courier", fs, OFF)
            pen.text(hx1 - tw_ + 16 + K.tw(a, "courier", fs), y0 + 6, b, "courier", fs, YELLOW)
        if sekme:
            lw = K.tw("TUTANAK", "anton", 30) + 28
            pen.rr((x0 + 20, y0 - 22, x0 + 20 + lw, y0 + 18), 8, fill=RED)
            pen.text(x0 + 34, y0 + 10, "TUTANAK", "anton", 30, OFF)
        out = (pen.done(), (x0 - 4, y0 - 26))
        self._c[key] = out
        return out

    def tut_lines(self, si: int, b: int):
        """Sahnenin dış sesinin tutanak satırları (sabit yerleşim: yazılınca kelimeler kaymaz). b: yazılacak son
        kelime + 1 (yorum çağrısı yazılmaz)."""
        key = ("tutl", si, b)
        if key in self._c:
            return self._c[key]
        a = self.ranges[si][0]
        ids = list(range(a, b))
        x0, _, x1, _ = TUTANAK
        width = (x1 - 48) - (x0 + 48) - 30
        size = TUT_SIZE
        while size > 16 and any(K.tw(self.words[i].text, "courier", size) > width for i in ids):
            size -= 2
        sp = K.tw(" ", "courier", size)
        lines, cur, cw = [], [], 0.0
        for i in ids:
            ww = K.tw(self.words[i].text, "courier", size)
            if cur and cw + sp + ww > width:
                lines.append(cur)
                cur, cw = [], 0.0
            cw = cw + (sp if cur else 0) + ww
            cur.append(i)
        if cur:
            lines.append(cur)
        out = (size, lines)
        self._c[key] = out
        return out

    def draw_tutanak(self, img: Image.Image, t: float, pg: Sayfa, sence: bool) -> None:
        base, (bx, by) = self.tutanak_base(not sence)
        K.put(img, base, bx, by, clip=CLIP)
        si = self.scene_at(t)
        a, b = self.ranges[si]
        if pg.kind == "hukum":
            cta = self.cta_start(pg)
            if cta is not None and a <= cta < b:
                b = cta
        if a >= b:
            return
        cur = self.cur_word(t)
        if t > self.words[-1].end + 0.35 if self.words else True:
            cur = b - 1
        if cur < a:
            return
        cur = min(cur, b - 1)
        size, lines = self.tut_lines(si, b)
        w = self.words[cur]
        chars = len(w.text)
        if t - w.start < TYPE and not (t > w.end):
            chars = max(1, int(math.ceil(len(w.text) * K.clamp((t - w.start) / TYPE))))
        li = next((k for k, L in enumerate(lines) if cur in L), 0)
        first = max(0, li - 1)
        scroll = 0.0
        if li >= 2:
            t_line = self.words[lines[li][0]].start
            p = (t - t_line) / SCROLL
            if p < 1:
                scroll = (1 - K.ease_out_cubic(max(0.0, p)))
                first = li - 2
        key = ("tutx", si, cur, chars, first, round(scroll, 2), b)
        lay = self._dyn.get(key)
        if lay is None:
            x0, y0, x1, y1 = TUTANAK
            pen = K.Pen(x0 + 8, y0 + 6, x1 - 8, y1 - 6)
            lh = size * 1.3
            capc = cap_h("courier", size)
            base0 = y0 + 30 + capc + 8 + (TUT_SIZE - size) * 0.6
            sp = K.tw(" ", "courier", size)
            for k in range(first, min(len(lines), first + 3)):
                by_ = base0 + (k - first) * lh - (lh * (1 - scroll) if (li >= 2 and first == li - 2) else 0)
                if by_ < y0 + 10 or by_ > y1 - 8:
                    continue
                xx = x0 + 48
                for i in lines[k]:
                    if i > cur:
                        break
                    text = self.words[i].text if i < cur else self.words[i].text[:chars]
                    ww = K.tw(self.words[i].text, "courier", size)
                    if i == cur:   # sarı vurgu yazılan harflerle uzar
                        tw_ = K.tw(text, "courier", size)
                        pen.rr((xx - 6, by_ - capc - 10, xx + tw_ + 6, by_ + 12), 4, fill=YELLOW)
                    pen.text(xx, by_, text, "courier", size, INK)
                    if i == cur:
                        cx = xx + K.tw(text, "courier", size) + 8
                        pen.rr((cx, by_ - capc - 4, cx + size * 0.5, by_ + 6), 2, fill=RED)
                    xx += ww + sp
            lay = pen.done()
            if len(self._dyn) > 160:
                self._dyn.clear()
            self._dyn[key] = lay
        # satırlar kâğıdın içinde kırpılır (kayan satır kenardan taşmaz)
        K.put(img, lay, TUTANAK[0] + 8, TUTANAK[1] + 6, clip=(TUTANAK[0] + 8, TUTANAK[1] + 8, TUTANAK[2] - 8,
                                                               TUTANAK[3] - 8))

    # ------------------------------------------------------------ Makas
    def pose(self, pg: Sayfa, lt: float):
        if pg.kind == "kapak":
            return POSE["kapak"]
        if pg.kind == "hukum":
            return POSE["ara"]
        if pg.kind == "ara":
            return POSE["ara"]
        return POSE["ic"]

    def mood(self, pg: Sayfa, lt: float, si: int) -> str:
        m = (self.scenes[si].card or {}).get("mascot", "auto")
        if m in K.MOODS:
            return m
        if pg.kind == "hukum":
            P = self.hukum_parts(pg)
            if lt < P["land"]:
                return "thinking"
            return "surprised" if lt < P["land"] + 0.5 else "happy"
        if pg.kind == "delil" and pg.belge == "olcum":
            P = self.page_parts(pg, pg.scenes[0])
            return "surprised" if lt >= P["count"][1] else "normal"
        return MOOD.get(pg.kind, "normal")

    def draw_mascot(self, img: Image.Image, t: float, pi: int, lt: float) -> None:
        pg = self.pages[pi]
        si = self.scene_at(t)
        cx, cy, sc, point = self.pose(pg, lt)
        mood = self.mood(pg, lt, si)
        hop = 0.0
        if pi > 0:
            pcx, pcy, psc, _ = self.pose(self.pages[pi - 1], 99.0)
            p = K.clamp(lt / 0.4)
            if (pcx, pcy, psc) != (cx, cy, sc) and p < 1:
                e = K.ease_in_out(p)
                cx, cy, scl = K.lerp(pcx, cx, e), K.lerp(pcy, cy, e), K.lerp(psc, sc, e)
                hop = -60 * math.sin(math.pi * p)
                im = self.mascot.sprite(mood, "rest", False, None, sc)
                k = scl / sc
                ox, oy = Mascot.origin(cx, cy, scl)
                K.put(img, im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.BILINEAR),
                      ox, oy + hop, clip=CLIP)
                return
            if p < 1:
                hop = -22 * math.sin(math.pi * K.clamp(lt / 0.32))
        if pg.kind == "hukum":
            P = self.hukum_parts(pg)
            if P["land"] <= lt < P["land"] + 0.3:
                hop = -40 * math.sin(math.pi * (lt - P["land"]) / 0.3)
        mouth = K.talk_state(self.words, self.starts, t)
        blink = (t % 3.6) > 3.45 and mood not in ("happy", "surprised")
        im = self.mascot.sprite(mood, mouth, blink, point, sc)
        bob = round(3 * math.sin(t * 2 * math.pi * 0.55))
        ox, oy = Mascot.origin(cx, cy, sc)
        K.put(img, im, ox, oy + bob + hop, clip=CLIP)

    # ------------------------------------------------------------ marka: filigran ve açılış kesmesi
    def watermark(self, img: Image.Image, t: float) -> None:
        if not self.brand_on:
            return
        if "wm" not in self._c:
            wm = Image.open(Path(__file__).resolve().parent / "assets" / "brand" / "video_filigran.png").convert("RGBA")
            wm = wm.resize((int(wm.width * WM_OLCEK), int(wm.height * WM_OLCEK)), Image.LANCZOS)
            wm.putalpha(wm.getchannel("A").point(lambda v: int(v * self.wm_alpha)))
            ww, wh = wm.size
            sy = SEKME[1] + (SEKME[3] - SEKME[1]) / 2 - wh / 2 - 6
            self._c["wm"] = (wm, [(X0, sy), (min(SAFE[2] - 8, X1 + 8) - ww, sy)])
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
        """Açılış: makas dosyanın üst kenarı boyunca keser (t=0'da sol başta durur); kesik çizgi sonra söner."""
        if not self.intro or t >= dur + 0.4:
            return
        p = K.clamp(t / dur)
        y = DOSYA[1] - 2
        x = K.lerp(X0, SAFE[2] - 40, K.ease_in_out(p))
        fade = 1.0 if t < dur else 1 - (t - dur) / 0.4
        pen = K.Pen(0, y - 40, SAFE[2], y + 40)
        xx = X0
        while xx < x:
            pen.rr((xx, y - 2, min(xx + 16, x), y + 2), 2, fill=OFF + (int(255 * fade),))
            xx += 26
        lay = pen.done()
        K.put(img, lay, 0, y - 40, clip=CLIP)
        if p < 1:
            sc = K.scissors_icon(70, 32 if int(t * 24) % 2 else 12, blade=OFF, outline=INK)
            K.put(img, sc, x - 70 * 58 / 124, y - sc.height / 2, clip=CLIP)

    def kes(self, img: Image.Image, old: Image.Image, box, local: float, seed: int) -> None:
        """İç sayfalar arası geçiş: eski içerik (CONTENT katmanı) kart şablonunun makas kesmesiyle ikiye ayrılır;
        parçalar üst sıranın altında ve tutanağın üstünde kırpılır."""
        K.card_cut(img, old, local, seed, origin=CONTENT[:2], card=box, x_end=SAFE[2] - 66,
                   clip_top=(0, TOP[3] - 4, SAFE[2], CONTENT[3]),
                   clips_bot=((0, TOP[3] - 4, SAFE[2], CONTENT[3] + 12),))

    # ------------------------------------------------------------ kare
    def frame(self, t: float, grain: bool = True) -> Image.Image:
        pi = self.page_at(t)
        pg = self.pages[pi]
        lt = t - pg.start
        prev = self.pages[pi - 1] if pi else None
        sence = False
        if pg.kind == "kapak":
            img = self.bg(False).copy()
            self.draw_kapak(img, pg, t, lt)
        elif pg.kind == "hukum":
            if prev is not None and prev.kind not in ("kapak",) and lt < FLIP:
                img = self.bg(True).copy()
                self.draw_inside_final(img, prev)
                self.flip(img, self.hukum_layer(pg), K.ease_in_out(lt / FLIP))
            else:
                img = self.desk().copy()
                self.draw_hukum(img, pg, lt)
            P = self.hukum_parts(pg)
            sence = P["q_t"] is not None and lt >= P["q_t"]
        else:
            img = self.bg(True).copy()
            self.draw_top(img, pg, lt)
            si = self.page_scene(pg, t)
            entry = 0.0
            if prev is not None and prev.kind == "kapak":
                entry = FLIP * 0.55
                self.draw_content(img, pg, lt, entry, si)
                self.flip(img, self.kapak_layer(prev), 1 - K.ease_in_out(lt / FLIP))
            else:
                if si != pg.scenes[0]:
                    # aynı delilin numarasız ek belgesi: önceki belge makasla kesilir, yenisi bırakılır
                    s0 = self.scenes[si].start - pg.start
                    psi = max(i for i in pg.scenes if i < si and (i == pg.scenes[0] or self.belge_of(i)))
                    if lt - s0 < K.CUT_LEN:
                        P0 = self.page_parts(pg, psi)
                        self.kes(img, P0["final"], P0.get("box", (X0, 500, X1, 1100)), lt - s0, si)
                    self.draw_content(img, pg, lt, s0 + ENTRY0, si)
                else:
                    if prev is not None and lt < K.CUT_LEN:
                        old, box = self.final_content(prev)
                        self.kes(img, old, box, lt, pi)
                    self.draw_content(img, pg, lt, ENTRY0, si)
        if pi == 0:
            self.intro_cut(img, t)
        self.draw_tutanak(img, t, pg, sence)
        if pg.kind == "hukum" and sence:
            P = self.hukum_parts(pg)
            lab = P["sence"]
            k = 1.0
            if lt - P["q_t"] < 0.25:
                k = ease_pop((lt - P["q_t"]) / 0.25, 1.2)
            im = self._c.setdefault(("sence_im",), lab.render(-3, (6, 8, 0, 0.9)))
            K.put(img, im, X0 + 6 + lab.w / 2 - im.width / 2, P["sence_top"] + lab.h / 2 - im.height / 2, k=k,
                  clip=CLIP)
        if pg.kind == "hukum":
            self.draw_cta(img, pg, lt)
        self.draw_mascot(img, t, pi, lt)
        self.watermark(img, t)
        if self.yalniz_icerik:
            return img
        return K.finish(img) if grain else img.convert("RGB")

    def draw_inside_final(self, img: Image.Image, pg: Sayfa) -> None:
        """İç sayfanın son hâli (kapak kapanırken altında kalır)."""
        self.draw_top(img, pg, 99.0)
        old, _ = self.final_content(pg)
        K.put(img, old, CONTENT[0], CONTENT[1], clip=CLIP)


# ---------------------------------------------------------------- ana giriş
def render(scenes: list[SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
           music: Path | None, meta: dict) -> Path:
    """Dava Dosyası şablonuyla videoyu kurar (pipeline.build: shortgen/<renderer>.py render). Kare döngüsü, ses,
    kuyruk ve marka kapanışı kart şablonuyla ortak (kart.render_frames)."""
    return K.render_frames(scenes, words, out_mp4, voice_mp3, music,
                           lambda bcfg: DosyaVideo(scenes, words, meta, bcfg), "Dosya")
