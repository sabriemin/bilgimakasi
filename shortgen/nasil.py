"""Nasıl yapılır? şablonu ("Adım kartları"): sarı noktalı zemin, 1-2-3-4 ilerleme çubuğu, numaralı adım kartları,
kartı gösteren maskot Makas ve onun konuşma balonunda kelime kelime dış ses.

Ekran düzeni (1080x1920). Yazı yalnız x 72-920, y 236-1536 arasında; gölgeler dahil hiçbir öğe platform arayüzüne
(sağdaki düğmeler x > 935, üst çubuk y < 170, alttaki açıklama y > 1540) taşmaz:
  236-306   seri etiketi (siyah yırtık) + makas ...................... ADIM 2/4
  326-428   ilerleme: ✓ ── ② ✂- - - ③ - - - ④  (makas adım boyunca bir sonraki düğüme doğru keser)
  480-1290  adım kartı: kırmızı yırtık numara + başlık, kesik çizgi, çizim, en çok 2 küçük not; Makas sağ alt
            köşede kartı gösterir
  1340-1528 Makas'ın konuşma balonu: o an okunan dış ses (okunan sarı, söylenmiş kırık beyaz, sıradaki soluk). Kinetik
            altyazı yoktur: dış sesin her kelimesi balonda (özette NEDEN? kutusunda) yazılı, sessiz izleyen de okur.
Kanca (ilk sahne): seri etiketi + "4 ADIM", boş ilerleme çubuğu, büyük soru başlığı (vurgulu satır kırmızı yırtık
etikette), sonuç/sorun çizimi, düşünceli Makas ve balon. t=0 karesi kapaktır, tam görünür.
Özet (son sahne): adımların listesi (satırlar sırayla düşer, ✓ işaretleri patlar), dış sesin "neden"i NEDEN? kutusunda,
soru gelince kutu SENCE? olur; KAYDET, SONRA DENE! etiketi ve mutlu Makas. Sondaki "Yorumlara yaz." kutuya yazılmaz:
söylendiği anda kart şablonunun YORUMLARA YAZ çıkartması olarak belirir (aynı söz ekranda iki kez durmaz).
Geçişler: eski içerik kart şablonunun makas kesmesiyle (kart.card_cut) kesilir; ilerleme çubuğundaki makas bir sonraki
düğüme kadar keser ve düğüm kırmızı olur (son düğümde makas geri çekilip düğümün solunda durur); yeni kart sağdan
sekerek gelir (sağ kenarda yumuşakça belirir, x=935'te düz kesilmez), numarası damga gibi iner. Özet, eski kart
kesilip söndükten sonra gelir.

Senaryo eşlemesi (plan, script.adim_isaretleri / adim_gruplari ile normalize_nasil'in aynısı): sahnenin adımı
spec.card["step"] (Scene.step), yoksa başlığın ilk satırındaki "ADIM n" ya da "n. ADIM" ("AŞAMA n" / "n. AŞAMA" da
aynı; ilk ve son sahnede okunmaz). İlk adımdan önceki sahneler kanca, en son sahne özet; aynı adımın art arda sahneleri
ve adımsız ara sahneler (son adımdan sonrakiler dahil) o adımın kartıdır. Adım işareti hiç yoksa ilk sahne kanca, son
sahne özet, aradakiler birer adım olur.

Varyantlar (VARSAYILAN; şablon ayarından: templates/<ad>.json, renderer "nasil"): Nasıl yapılır? (nasil.json) yukarıdaki
gibidir. Nasıl üretiliyor? (uretim.json, "yapi": "uretim") aynı düzende "ADIM" yerine "AŞAMA" der ("4 AŞAMA",
"AŞAMA 2/4", ÜRETİM HATTI özeti) ve fabrika görünüşündedir: kraft karton zemin + silik teknik çizim ızgarası; ilerleme
çubuğu yürüyen banttır (y 306-440): numaralı aşama kutuları bandın üstünde durur (sıradaki kırık beyaz, şimdiki kırmızı,
biten mürekkep + sarı ✓), Makas bandın üstünde kutudan kutuya ilerler; bandın diş izleri ve makaraları Makas'la birlikte
kayar/döner, bandın işlenen kısmı kırmızıdır.
"""
from __future__ import annotations

import bisect
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import kart as K
from . import render
from .script import ADIM_RE, adim_gruplari, adim_isaretleri
from .voice import Word

# 'AŞAMA 2', 'AŞAMA 2:', '2. AŞAMA' (Nasıl üretiliyor?): 'ADIM n' ile aynı kural (script.ADIM_RE); '4 AŞAMA' aşama
# sayısıdır, işaret değil
ASAMA_RE = re.compile(r"^\s*(?:AŞAMA\s*(\d+)|(\d+)\s*\.\s*AŞAMA)\b[\s:.,\-–—]*")

# Şablon varyantı: Adım kartları renderer'ını kullanan her seri (templates/*.json, renderer "nasil") kelimelerini ve
# görünüşünü şablonundan alır; anahtar yoksa Nasıl yapılır? değeri geçerlidir (nasil.json bu anahtarları yazmaz).
VARSAYILAN = {
    "adim_kelimesi": "ADIM",              # kanca "4 ADIM", başlık "ADIM 2/4", başlıksız kart "ADIM 3"
    "seri_adi": "NASIL YAPILIR?",         # adım başlığındaki seri etiketi; kancada seri etiketi (kicker) yoksa o da
    "ozet_etiketi": "ÖZET",               # özet başlığındaki kırmızı etiket
    "ozet_adi": "ADIMLAR",                # özet sahnesinin başlığı yoksa
    "ozet_kutusu": "NEDEN?",              # özette dış ses kutusunun etiketi (soru gelince SENCE?)
    "kapanis": "KAYDET, SONRA DENE!",     # özetin kapanış etiketi (yorum çağrısı söylenmeden önce)
    "zemin": "sari",                      # sari: sarı noktalı | kraft: kraft karton + silik teknik çizim ızgarası
    "ilerleme": "dugum",                  # dugum: 1-2-3-4 düğümleri | bant: aşama kutularını taşıyan yürüyen bant
}

W, H, FPS, SS = K.W, K.H, K.FPS, K.SS
RED, YELLOW, INK, OFF, WHITE = K.RED, K.YELLOW, K.INK, K.OFF, K.WHITE
DOT = (238, 196, 16)                       # sarı zeminin sessiz noktaları
KRAFT = (224, 202, 163)                    # kraft karton zemin (uretim)
KRAFT_GRID, KRAFT_MAJOR = (212, 189, 148), (200, 175, 132)   # silik teknik çizim ızgarası: ince / her 5. çizgi
GHOST = (112, 109, 104)                    # balonda sıradaki kelimeler: mürekkep zeminde soluk ama okunur
RULE_GREY = (190, 187, 180)
X0, X1 = 72, 920                           # yazı alanı
SAFE = K.SAFE                              # (0, 170, 935, 1540)
CLIP = (0, SAFE[1], SAFE[2], SAFE[3])
HEAD = (0, 196, 935, 340)                  # başlık satırı katmanı
HEAD_CY = 272
PROG = (0, 306, 935, 448)                  # ilerleme çubuğu katmanı
PROG_CY = 376
NODE_X0, NODE_X1 = 140, 852
CONTENT = (0, 436, 935, 1320)              # sahne içeriği (kart, başlık, satırlar); kesme geçişi bunu keser
CARD = (72, 480, 920, 1290)
CARD_SH = 14
NUM_C = (CARD[0] + 96, CARD[1] + 112)      # numara etiketinin merkezi
BUBBLE = (72, 1340, 920, 1528)
TAIL_X = 800                               # balon kuyruğu Makas'a uzanır
HOOK_TOP = 452
MASCOT_VB = (-300, -320, 600, 520)         # gövde merkezi SVG'de (0, 60)
POSE = {"hook": (812, 1190, 0.66, None), "step": (826, 1228, 0.72, 212.0), "recap": (826, 1462, 0.56, None)}
MOOD = {"hook": "thinking", "step": "normal", "recap": "happy"}
CUT = K.CUT_LEN                            # makas kesmesi (kart şablonuyla aynı süre)
SLIDE0, SLIDE = 0.18, 0.42                 # yeni kart sağdan gelir (makas eski kartı kestikten sonra)
STAMP0, STAMP = 0.56, 0.16                 # numara damgası
NOTE0 = 0.86                               # küçük notlar patlar
RECAP0 = CUT + 0.03                        # özet satırları ve NEDEN? kutusu: eski kartın parçaları söndükten sonra
T_REACH, T_HOP = 0.30, 0.20                # ilerleme makası düğüme varır, düğümün üstünden atlar
CUT_SHARE = 0.62                           # makas bir adım boyunca aradaki çizginin bu kadarını keser
SC_W, SC_PIN = 84, 58 / 124                # ilerleme makası genişliği, pimin soldan oranı
FEATHER = 60                               # gelen kart sağ kırpma kenarında (x=935) bu kadar px'te yumuşakça belirir
# yürüyen bant (uretim): kutular bandın üstünde durur (tabanları BELT_Y0), Makas bandın üstünde ilerler
BELT_X0, BELT_X1 = 70, 906
BELT_Y0, BELT_Y1 = 394, 428                # bandın (dış mürekkep halka) üst ve alt kenarı
BELT_LEG = 440                             # ayakların alt ucu (PROG içinde; kanca başlığı 452'den başlar)
BELT_RUN = 7                               # bandın mürekkep kalınlığı (üst kol: diş izleri, işlenen kısım kırmızı)
BELT_COL = (198, 192, 181)                 # bandın içi (makaraların arkası)
TREAD = 24                                 # diş izleri aralığı: fazda 4 px kayar, makara çizgisi 15 derece döner
BELT_VMAX = 2 * TREAD / 6 * FPS            # bandın en yüksek hızı (px/sn): karede en çok 2 faz (desen 6 fazda döner)
BOX = {"up": (68, 60), "cur": (82, 72), "done": (68, 60)}   # aşama kutusu (genişlik, yükseklik)
BOX_POP = 0.5                              # kutunun durum değişimindeki büyümesi düğümünkinin yarısı (PROG'a sığar)
Q_RE = re.compile(r"\byorumlara\s+yaz", re.I)


def up(s: str) -> str:
    return K.tr_upper((s or "").strip())


def cap_h(font: str, size: float) -> float:
    return -K.tbox("H", font, size)[1]


def step_marker(line: str):
    """Başlık satırının başındaki adım işareti ('ADIM n', 'n. ADIM', 'AŞAMA n', 'n. AŞAMA'): re.Match ya da None."""
    u = up(line)
    return ADIM_RE.match(u) or ASAMA_RE.match(u)


def _as_adim(line: str) -> str:
    """'AŞAMA n ...' satırını 'ADIM n ...' yapar (script.adim_isaretleri ADIM işaretini okur); diğerleri aynen."""
    m = ASAMA_RE.match(up(line))
    if not m:
        return line
    return f"ADIM {m.group(1) or m.group(2)} {up(line)[m.end():]}".strip()


def step_marks(specs) -> list[int]:
    """Sahnelerin ham adım işaretleri: card['step'] (Scene.step), yoksa başlığın ilk satırındaki 'ADIM n' / 'n. ADIM'
    / 'AŞAMA n' / 'n. AŞAMA' (script.adim_isaretleri: ilk ve son sahnenin başlığı okunmaz); adımsız sahnede 0."""
    steps = []
    for spec in specs:
        try:
            steps.append(max(0, int((spec.card or {}).get("step") or 0)))
        except (TypeError, ValueError):
            steps.append(0)
    return adim_isaretleri(steps, [_as_adim((spec.headline or [""])[0]) for spec in specs])


def step_title(headline: list[str]) -> list[str]:
    """Adım başlığı: 'ADIM n' / 'AŞAMA n' satırı (ya da satır başındaki 'ADIM n:' öneki) çıkarılmış başlık satırları."""
    lines = [up(x) for x in headline if x and x.strip()]
    if lines:
        m = step_marker(lines[0])
        if m:
            rest = lines[0][m.end():].strip()
            lines = ([rest] if rest else []) + lines[1:]
    return lines


def sablon_of(yapi: str | None) -> dict:
    """Yapıya (anlatım kalıbı) ait Adım kartları şablonunun ayarı: templates/*.json içinde renderer 'nasil' ve 'yapi'
    alanı yapıya eşit olan (yapi yoksa 'nasil' sayılır); yoksa {}."""
    if not yapi:
        return {}
    for f in sorted(render.TEMPLATE_DIR.glob("*.json")):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(t, dict) and t.get("renderer") == "nasil" and (t.get("yapi") or "nasil") == yapi:
            return t
    return {}


def varyant(meta: dict | None) -> dict:
    """Videonun varyantı: VARSAYILAN, üstüne şablon ayarındaki anahtarlar. Şablon ayarı meta['sablon'] (pipeline.build
    verir), yoksa meta['structure']'a ait şablon (sablon_of)."""
    meta = meta or {}
    cfg = meta.get("sablon")
    if not isinstance(cfg, dict):
        cfg = sablon_of(meta.get("structure"))
    out = dict(VARSAYILAN)
    out.update({k: v for k, v in cfg.items() if k in VARSAYILAN and isinstance(v, str) and v.strip()})
    return out


# ---------------------------------------------------------------- senaryo -> bölümler
@dataclass
class Segment:
    kind: str                       # hook | step | recap
    scenes: list[int]
    number: int = 0                 # adım sırası (1'den), kanca ve özette 0
    title: list[str] = field(default_factory=list)
    hl: int = -1
    sprite: Path | None = None
    image: Path | None = None
    credit: dict = field(default_factory=dict)
    callouts: list[str] = field(default_factory=list)
    mascot: str = "auto"
    start: float = 0.0
    end: float = 0.0
    a: int = 0                      # kelime aralığı [a, b)
    b: int = 0


def plan(specs, word: str = "ADIM") -> list[Segment]:
    """Sahneleri kanca / adım / özet bölümlerine ayırır (modül açıklamasındaki kurallar). word: başlığı olmayan adım
    kartının adı ('ADIM 3' / 'AŞAMA 3')."""
    n = len(specs)
    raw = step_marks(specs)
    if not any(raw):   # adım işareti yok: ilk sahne kanca, son sahne özet, aradakiler birer adım
        raw = [0] + list(range(1, n - 1)) + [0] if n >= 3 else [0] + list(range(1, n))
    hook, steps, recap = adim_gruplari(raw)
    if not steps:
        return [Segment("hook", list(range(n)))] if n else []
    groups = (([("hook", hook)] if hook else []) + [("step", idx) for _, idx in steps]
              + ([("recap", recap)] if recap else []))
    segs, k = [], 0
    for kind, idx in groups:
        s0 = specs[idx[0]]
        seg = Segment(kind, idx)
        c = s0.card or {}
        if kind == "step":
            k += 1
            seg.number = k
            seg.title = step_title(s0.headline) or [f"{word} {k}"]
            seg.callouts = [up(x) for x in (c.get("callouts") or []) if str(x).strip()][:2]
        else:
            seg.title = [up(x) for x in s0.headline if x and x.strip()]
            seg.hl = s0.highlight_line if 0 <= s0.highlight_line < len(seg.title) else -1
        for i in idx:               # bölümün görseli: ilk çizim, yoksa ilk fotoğraf
            s = specs[i]
            if seg.sprite is None and s.sprite is not None:
                seg.sprite = s.sprite
            if seg.image is None and s.image is not None:
                seg.image, seg.credit = s.image, dict((s.card or {}).get("credit") or {})
        seg.mascot = c.get("mascot", "auto")
        segs.append(seg)
    return segs


# ---------------------------------------------------------------- küçük çizim yardımcıları
_static: dict = {}


def yellow_bg() -> Image.Image:
    """Vurgu sarısı + sessiz nokta ızgarası (kart şablonundaki noktalı kâğıdın sarı hâli; bir kez çizilir)."""
    if "bg" not in _static:
        sp = 28
        tile = Image.new("RGB", (sp * 4, sp * 4), YELLOW)
        ImageDraw.Draw(tile).ellipse([sp * 2 - 4.6, sp * 2 - 4.6, sp * 2 + 4.6, sp * 2 + 4.6], fill=DOT)
        tile = tile.resize((sp, sp), Image.LANCZOS)
        bg = Image.new("RGB", (W, H), YELLOW)
        for y in range(0, H, sp):
            for x in range(0, W, sp):
                bg.paste(tile, (x, y))
        _static["bg"] = bg.convert("RGBA")
    return _static["bg"]


def kraft_bg() -> Image.Image:
    """Kraft karton + silik teknik çizim ızgarası (28 px; her 5. çizgi biraz koyu) ve hafif lif dalgası (bir kez
    çizilir; kâğıt greni kare sonunda kart.finish ile eklenir)."""
    if "kraft" not in _static:
        sp = 28
        rng = np.random.default_rng(11)
        n = rng.normal(0, 1, (H // 16 + 1, W // 16 + 1)).astype(np.float32)
        low = np.asarray(Image.fromarray(n).resize((W, H), Image.BICUBIC)) * 3.0     # yumuşak lif dalgası (±3)
        base = np.empty((H, W, 3), np.float32)
        base[:] = KRAFT
        base += low[..., None]
        bg = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
        d = ImageDraw.Draw(bg)
        for k, x in enumerate(range(X0 % sp, W, sp)):
            d.line([(x, 0), (x, H)], fill=KRAFT_MAJOR if k % 5 == 0 else KRAFT_GRID, width=2 if k % 5 == 0 else 1)
        for k, y in enumerate(range(0, H, sp)):
            d.line([(0, y), (W, y)], fill=KRAFT_MAJOR if k % 5 == 0 else KRAFT_GRID, width=2 if k % 5 == 0 else 1)
        _static["kraft"] = bg.convert("RGBA")
    return _static["kraft"]


def label_w(text: str, size: float, font: str = "anton") -> float:
    return K.tw(text, font, size) + 2 * size * 0.2


def paste_label(pen: K.Pen, text, size, fg, bg, seed, cx, cy, rot=0.0, shadow=(6, 8, 0, 0.9), font="anton", rim=OFF):
    """Yırtık kâğıt etiketi merkezi (cx, cy) olacak şekilde 2x katmana yapıştırır; (w, h) döndürür."""
    lab = K.torn_label(text, size, fg, bg, seed, font=font, rim=rim)
    im = lab.render_ss(rot, shadow)
    pen.paste(im, cx - im.width / 2 / SS, cy - im.height / 2 / SS)
    return lab.w, lab.h


def label_img(text, size, fg, bg, seed, rot=0.0, shadow=(6, 8, 0, 0.9), rim=OFF) -> Image.Image:
    """Yırtık etiketin 1x görüntüsü (ayrı katman: damga, patlama)."""
    lab = K.torn_label(text, size, fg, bg, seed, rim=rim)
    return lab.render(rot, shadow)


def dashed(pen: K.Pen, x0, y, x1, col, dash=16, gap=10, w=3.0):
    x = x0
    while x < x1:
        pen.rr((x, y - w / 2, min(x + dash, x1), y + w / 2), w / 2, fill=col)
        x += dash + gap


def card_box(pen: K.Pen, box, fill=OFF, r=30, sh=CARD_SH, w=6):
    x0, y0, x1, y1 = box
    if sh:
        pen.rr((x0 + sh, y0 + sh, x1 + sh, y1 + sh), r, fill=INK)
    pen.rr(box, r, fill=fill, outline=INK, width=w)


_cols: dict = {}


def ink_cols(text: str, font: str, size: float):
    """Satırın sütun sütun mürekkep sınırları, taban çizgisine göre (tasarım pikseli; 2x sütunlar): (o, üst, alt).
    Sütun c kalemin x'inden (c - o) / SS uzakta; mürekkepsiz sütunda üst +inf, alt -inf."""
    key = (text, font, int(round(size * SS)))
    if key not in _cols:
        f = K.fnt(font, size * SS)
        l, t, r, b = f.getbbox(text, anchor="ls")
        o = max(0, -l) + 2
        base = -t + 2
        im = Image.new("L", (o + max(r, 1) + 2, base + max(b, 0) + 2), 0)
        ImageDraw.Draw(im).text((o, base), text, font=f, fill=255, anchor="ls")
        a = np.asarray(im) > 96
        has = a.any(axis=0)
        rows = np.arange(a.shape[0])[:, None]
        top = np.where(has, (np.where(a, rows, a.shape[0]).min(axis=0) - base) / SS, np.inf)
        bot = np.where(has, (np.where(a, rows, -1).max(axis=0) - base) / SS, -np.inf)
        if len(_cols) > 512:
            _cols.clear()
        _cols[key] = (o, top, bot)
    return _cols[key]


def line_pitch(lines: list[str], font: str, size: float, base: float) -> float:
    """Sola hizalı satırların taban çizgileri arası (tek ölçü, ritim bozulmasın): en az base; üst satırın inen
    işaretleri (Ş/Ç çengeli, virgül, noktalı virgül) alttaki satırın harflerine ve şapka/nokta işaretlerine sütun sütun
    en az 0,07 em uzak kalır (çapraz yakınlık da sayılır), üstüne binmez."""
    gap = size * 0.07
    g = max(1, int(round(gap * SS)))
    pitch = base
    for upper, lower in zip(lines, lines[1:]):
        o1, _, bot = ink_cols(upper, font, size)
        o2, top, _ = ink_cols(lower, font, size)
        lo = -max(o1, o2)
        n = max(len(bot) - o1, len(top) - o2) - lo
        B = np.full(n, -np.inf)
        B[-o1 - lo:-o1 - lo + len(bot)] = bot
        T = np.full(n, np.inf)
        T[-o2 - lo:-o2 - lo + len(top)] = top
        Bd = B.copy()
        for d in range(1, g + 1):
            Bd[d:] = np.maximum(Bd[d:], B[:-d])
            Bd[:-d] = np.maximum(Bd[:-d], B[d:])
        need = Bd - T
        need = need[np.isfinite(need)]
        if need.size:
            pitch = max(pitch, float(need.max()) + gap)
    return pitch


def title_pitch(lines: list[str], size: float) -> float:
    """Adım kartı başlığının satır aralığı (Anton): 1,12 büyük harf + 0,1 em, Türkçe çengeller sığacak kadar açılır."""
    return line_pitch(lines, "anton", size, cap_h("anton", size) * 1.12 + size * 0.1)


def row_pitch(lines: list[str], size: float) -> float:
    """Özet satırının (2 satıra kadar) satır aralığı: 1,22 büyük harf, Türkçe çengeller sığacak kadar açılır."""
    return line_pitch(lines, "anton", size, cap_h("anton", size) * 1.22)


def fit_lines(lines: list[str], font: str, width: float, max_size: int, min_size: int, max_lines: int,
              max_h: float, pitch=None) -> tuple[int, list[str]]:
    """En büyük boyut: verilen satır kırılımı sığıyorsa o, sığmıyorsa metin yeniden sarılır. Blok yüksekliği (ilk
    satırın büyük harfi + satır aralıkları) çizimdeki satır aralığıyla (pitch(satırlar, boyut)) ölçülür."""
    text = " ".join(lines)
    for size in range(max_size, min_size - 1, -2):
        for cand in (lines, [" ".join(L) for L in K.wrap(text, font, size, width)]):
            if not (cand and len(cand) <= max_lines and all(K.tw(L, font, size) <= width for L in cand)):
                continue
            lh = pitch(cand, size) if pitch else cap_h(font, size) * 1.12
            if cap_h(font, size) + (len(cand) - 1) * lh <= max_h:
                return size, cand
    size = min_size
    return size, [" ".join(L) for L in K.wrap(text, font, size, width)][:max_lines]


def feather_right(layer: Image.Image, x: float, strength: float = 1.0, edge: float = SAFE[2],
                  width: float = FEATHER) -> Image.Image:
    """Ekranda x'ten başlayan katmanın alfasını sağ kırpma kenarına (edge) doğru width px boyunca 0'a indirir: kayarak
    gelen kart görünmez bir duvardan düz kesilmiş gibi çıkmaz, kenarda yumuşakça belirir. strength 0..1: kart yerine
    yaklaşırken yumuşatma kalkar (yerinde duran kartın sağ kenarı tam görünür)."""
    x = int(round(x))
    if strength <= 0 or x + layer.width <= edge - width:
        return layer
    m = 1 - strength * (1 - np.clip((edge - (x + np.arange(layer.width))) / width, 0.0, 1.0))
    a = np.asarray(layer.getchannel("A"), dtype=np.float32) * m[None, :]
    out = layer.copy()
    out.putalpha(Image.fromarray(a.astype(np.uint8)))
    return out


def bump(x: float, peak: float = 1.2) -> float:
    """1 -> peak -> 1 vurgu ölçeği (x 0..1): görünür kalan öğe (ilerleme düğümü) durum değiştirirken."""
    return 1 + (peak - 1) * math.sin(math.pi * K.clamp(x))


def ease_pop(x: float, peak: float = 1.18) -> float:
    """0 -> peak -> 1 patlama ölçeği (x 0..1): yeni beliren öğe."""
    x = K.clamp(x)
    if x < 0.6:
        return peak * K.ease_out_cubic(x / 0.6)
    return K.lerp(peak, 1.0, K.ease_in_out((x - 0.6) / 0.4))


# ---------------------------------------------------------------- maskot: işaret eden Makas
def _hand(ex, ey, ang, fill, stroke, sw, extra=0.0) -> str:
    """İşaret parmağı uzatılmış eldivenli el (yerel +x parmak yönü). extra: kesim kenarı/gölge kalınlığı."""
    flip = -1 if math.cos(math.radians(ang)) < 0 else 1
    st = f'fill="{fill}" stroke="{stroke}" stroke-width="{sw + extra:.1f}" stroke-linejoin="round"'
    g = f'<g transform="translate({ex:.1f} {ey:.1f}) rotate({ang:.1f}) scale(1 {flip})">'
    g += f'<rect x="-30" y="-15" width="14" height="30" rx="5" {st}/>'            # manşet
    g += f'<rect x="4" y="-21" width="50" height="16" rx="8" {st}/>'             # işaret parmağı
    g += f'<rect x="-20" y="-20" width="40" height="38" rx="15" {st}/>'          # yumruk
    if not extra:
        g += (f'<path d="M-2 -3 Q8 -3 12 4 M-6 7 Q6 8 12 13" stroke="{stroke}" stroke-width="4" fill="none" '
              'stroke-linecap="round"/>')
    return g + "</g>"


def _arm(ang, L, ink, fill, sw, extra=0.0) -> str:
    """Kâğıt gövdenin sol kenarından çıkan hafif kıvrık kol ve el."""
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    x0, y0 = -90, 96
    ex, ey = x0 + ux * L, y0 + uy * L
    bend = 16 if ux < 0 else -16
    mx, my = x0 + ux * L * 0.5 - uy * bend, y0 + uy * L * 0.5 + ux * bend
    out = (f'<path d="M{K.P(x0, y0)} Q{K.P(mx, my)} {K.P(ex, ey)}" stroke="{ink}" stroke-width="{13 + extra:.1f}" '
           'stroke-linecap="round" fill="none"/>')
    return out + _hand(ex, ey, ang, fill if not extra else ink, ink, sw, extra)


def mascot_svg(mood: str, mouth: str, blink: bool, point: float | None = None, L: float = 100) -> str:
    """kart.mascot_svg + (point verilirse) o yöne (derece; 0 sağ, 180 sol, 212 sol-yukarı) uzanan işaret eden kol."""
    body = K.mascot_svg(mood, mouth, blink)
    if point is None:
        return body
    ink, white = K._hex(INK), K._hex(WHITE)
    arm = '<g transform="rotate(-6 0 60)">'
    arm += f'<g transform="translate(5 5)">{_arm(point, L, ink, ink, 5, extra=18)}</g>'
    arm += _arm(point, L, white, white, 5, extra=18) + _arm(point, L, ink, white, 5) + "</g>"
    return body + arm if 200 < point < 340 else arm + body


class Mascot:
    """İfade/ağız/göz kırpma/kol/ölçek başına bir kez çizilen Makas; gövde merkezine göre yerleşir."""

    def __init__(self):
        self._c: dict = {}

    def sprite(self, mood, mouth, blink, point, scale) -> Image.Image:
        key = (mood, mouth, blink, point, round(scale, 3))
        if key not in self._c:
            vb = MASCOT_VB
            k = scale * SS
            im = K.svg_img(mascot_svg(mood, mouth, blink, point), vb, vb[2] * k, vb[3] * k)
            self._c[key] = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
        return self._c[key]

    @staticmethod
    def origin(cx, cy, scale) -> tuple[float, float]:
        return cx + MASCOT_VB[0] * scale, cy + (MASCOT_VB[1] - 60) * scale


# ---------------------------------------------------------------- konuşma balonu: kelime kelime dış ses
class Speech:
    """Bir bölümün dış sesi, kutuya (en çok max_lines satır) sığan sayfalar hâlinde. Kelimeler sayfadaki yerlerinde
    durur: okunan sarı, söylenmiş kırık beyaz, sıradaki soluk; böylece sessiz izleyen de cümlenin tamamını okur.
    Sayfa önce cümle sonunda, sığmazsa yan cümlede, en son kelimede bölünür. breaks: yeni sayfanın başlaması
    gereken kelimeler (özette soru cümlesi)."""
    FONT = "courier"

    def __init__(self, words: list[Word], a: int, b: int, rect, sizes=(40, 38, 36, 34, 32), max_lines=3,
                 lh=1.25, breaks=()):
        self.words, self.a, self.b, self.rect = words, a, b, rect
        self.width = rect[2] - rect[0]
        self.max_lines, self.lh = max_lines, lh
        self.texts = {i: words[i].text for i in range(a, b)}
        breaks = set(breaks)
        chosen = None
        for size in sizes:
            pages, forced = self._pages(size, breaks)
            if not forced or size == sizes[-1]:
                chosen = (size, pages)
                break
        self.size, pages = chosen if chosen else (sizes[-1], [])
        self.pages = [(p[0], p[-1] + 1) for p in pages]
        self.page_starts = [p0 for p0, _ in self.pages]
        self.lines = {pi: self._balanced(list(range(p0, p1)), self.size) for pi, (p0, p1) in enumerate(self.pages)}
        self._img: dict = {}

    def _wrap(self, ids: list[int], size: float) -> list[list[int]]:
        lines, cur, cw = [], [], 0.0
        sp = K.tw(" ", self.FONT, size)
        for i in ids:
            ww = K.tw(self.texts[i], self.FONT, size)
            if cur and cw + sp + ww > self.width:
                lines.append(cur)
                cur, cw = [], 0.0
            cw += (sp if cur else 0) + ww
            cur.append(i)
        if cur:
            lines.append(cur)
        return lines

    def _balanced(self, ids: list[int], size: float) -> list[list[int]]:
        """Aynı satır sayısını koruyan en dar sarma: son satırda tek kelime kalmasın ('dök.' gibi)."""
        best = self._wrap(ids, size)
        full = self.width
        for w in range(int(full) - 8, int(full * 0.55), -8):
            self.width = w
            lines = self._wrap(ids, size)
            if len(lines) != len(best):
                break
            best = lines
        self.width = full
        return best

    def _fits(self, ids, size) -> bool:
        lines = self._wrap(ids, size)
        return len(lines) <= self.max_lines and all(
            K.tw(" ".join(self.texts[i] for i in L), self.FONT, size) <= self.width + 0.5 for L in lines)

    def _split(self, ids, ends) -> list[list[int]]:
        out, cur = [], []
        for i in ids:
            if cur and i in self._hard:
                out.append(cur)
                cur = []
            cur.append(i)
            if self.texts[i].rstrip('"“”»)’\'')[-1:] in ends:
                out.append(cur)
                cur = []
        if cur:
            out.append(cur)
        return out

    def _pages(self, size, breaks) -> tuple[list[list[int]], bool]:
        self._hard = breaks
        units, forced = [], False
        for sent in self._split(list(range(self.a, self.b)), ".?!…"):
            if self._fits(sent, size):
                units.append(sent)
                continue
            forced = True
            for clause in self._split(sent, ",;:—"):
                if self._fits(clause, size):
                    units.append(clause)
                    continue
                cur = []
                for i in clause:     # kelime kelime: kutuyu dolduran parçalar
                    if cur and not self._fits(cur + [i], size):
                        units.append(cur)
                        cur = []
                    cur.append(i)
                if cur:
                    units.append(cur)
        pages, cur = [], []
        for u in units:
            if cur and (u[0] in breaks or not self._fits(cur + u, size)):
                pages.append(cur)
                cur = []
            cur = cur + u
        if cur:
            pages.append(cur)
        return pages, forced

    def page_of(self, gi: int) -> int:
        return max(0, bisect.bisect_right(self.page_starts, gi) - 1)

    def image(self, pi: int, cur: int) -> Image.Image:
        """Sayfanın o anki görüntüsü (rect boyutunda, şeffaf zemin). cur: okunan kelime (b ise hepsi söylenmiş)."""
        key = (pi, cur)
        if key in self._img:
            return self._img[key]
        x0, y0, x1, y1 = self.rect
        pen = K.Pen(x0 - 4, y0 - 4, x1 + 4, y1 + 4)
        lines = self.lines.get(pi, [])
        size = self.size
        lh = size * self.lh
        cap = cap_h(self.FONT, size)
        base = (y0 + y1) / 2 - (len(lines) - 1) * lh / 2 + cap / 2
        sp = K.tw(" ", self.FONT, size)
        for li, L in enumerate(lines):
            x = x0
            for i in L:
                col = YELLOW if i == cur else (OFF if i < cur else GHOST)
                pen.text(x, base + li * lh, self.texts[i], self.FONT, size, col)
                x += K.tw(self.texts[i], self.FONT, size) + sp
        if len(self._img) > 96:
            self._img.clear()
        self._img[key] = pen.done()
        return self._img[key]

    def put(self, img: Image.Image, cur: int, dy: float = 0.0, alpha: float = 1.0) -> None:
        if not self.pages:
            return
        pi = self.page_of(min(cur, self.b - 1))
        K.put(img, self.image(pi, cur), self.rect[0] - 4, self.rect[1] - 4 + dy, alpha=alpha, clip=CLIP)

    def page_kind(self, cur: int, breaks) -> bool:
        """Okunan kelimenin sayfası bir kırılımdan (soru) başlıyor mu."""
        if not self.pages:
            return False
        p0 = self.pages[self.page_of(min(cur, self.b - 1))][0]
        return p0 in breaks


# ---------------------------------------------------------------- video
class NasilVideo:
    def __init__(self, scenes, words: list[Word], meta: dict, bcfg: dict):
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        on = bcfg.get("enabled", False)
        self.intro = bool(on and bcfg.get("intro_cut", True))
        self.handle = (bcfg.get("handle") or "") if on and bcfg.get("subtitle_handle", True) else ""
        self.var = varyant(self.meta)
        self.word = self.var["adim_kelimesi"]
        self.belt = self.var["ilerleme"] == "bant"
        self.segs = plan(scenes, self.word)
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
        self.node_x = ([NODE_X0 + k * (NODE_X1 - NODE_X0) / max(1, self.N - 1) for k in range(self.N)]
                       if self.N > 1 else [(NODE_X0 + NODE_X1) / 2] * self.N)
        self.starts = [w.start for w in words]
        self.kicker = up(scenes[0].kicker) if scenes and (scenes[0].kicker or "").strip() else self.var["seri_adi"]
        self.mascot = Mascot()
        self._layers: dict = {}
        self._speech: dict = {}
        self._nodes: dict = {}
        self._q_breaks: dict = {}
        self._belt_off: tuple[float, list[float]] | None = None

    # ------------------------------------------------------------ zaman
    def seg_at(self, t: float) -> int:
        return max(0, bisect.bisect_right(self.seg_starts, t) - 1)

    def cur_word(self, t: float, seg: Segment) -> int:
        """Bölümde okunan kelime (sahne değişti ama ilk kelime birkaç kare sonra: ilk kelime seçili görünür)."""
        if seg.a >= seg.b:
            return seg.b
        if seg is self.segs[-1] and t > self.words[seg.b - 1].end + 0.35:
            return seg.b
        cur = bisect.bisect_right(self.starts, t + 0.03) - 1
        return min(max(cur, seg.a), seg.b - 1)

    # ------------------------------------------------------------ başlık satırı
    def header(self, seg: Segment) -> Image.Image:
        key = ("head", seg.kind, seg.number)
        if key in self._layers:
            return self._layers[key]
        pen = K.Pen(*HEAD)
        cy = HEAD_CY
        size = 52
        base = cy + cap_h("anton", size) / 2
        if seg.kind == "recap":
            tag = self.var["ozet_etiketi"]
            lw = label_w(tag, 56)
            paste_label(pen, tag, 56, OFF, RED, 720, X0 + lw / 2 + 4, cy, rot=-2.5)
            right = f"{self.N}/{self.N}" if self.N else ""
            pen.text(X1, base, right, "anton", size, RED, anchor="rs")
            room = X1 - K.tw(right, "anton", size) - 30 - (X0 + lw + 30)
            name = " ".join(seg.title) or self.var["ozet_adi"]
            ts = size
            while ts > 34 and K.tw(name, "anton", ts) > room:
                ts -= 2
            pen.text(X0 + lw + 30, cy + cap_h("anton", ts) / 2, K.fit_words(name, "anton", ts, room), "anton", ts, INK)
        else:
            if seg.kind == "hook":
                parts = [(str(self.N), RED), (" " + self.word, INK)] if self.N else []
                text, ls = self.kicker, 46
            else:
                parts = [(self.word + " ", INK), (str(seg.number), RED), (f"/{self.N}", INK)]
                text, ls = self.var["seri_adi"], 40
            rw = sum(K.tw(p, "anton", size) for p, _ in parts)
            while ls > 30 and label_w(text, ls) > X1 - rw - 120 - X0:
                ls -= 2
            lw = label_w(text, ls)
            paste_label(pen, text, ls, OFF, INK, 701, X0 + lw / 2 + 4, cy, rot=-2.0, shadow=None)
            x = X1 - rw
            for p, col in parts:
                pen.text(x, base, p, "anton", size, col)
                x += K.tw(p, "anton", size)
            if seg.kind == "step":   # küçük makas etiketin sağında (kancada ilerleme makası açılışı yapar)
                pen.svg(K.scissors_svg(26), K.SCISSORS_VB, X0 + lw + 22, cy - 22, 60)
        self._layers[key] = pen.done()
        return self._layers[key]

    # ------------------------------------------------------------ ilerleme çubuğu
    def node(self, state: str, k: int) -> tuple[Image.Image, float]:
        key = (state, k)
        if key not in self._nodes:
            r = 52 if state == "cur" else 40
            pad = 14
            c = pad + r
            pen = K.Pen(0, 0, 2 * c + 8, 2 * c + 8)
            if state == "done":
                pen.ell(c + 5, c + 5, r, fill=INK)
                pen.ell(c, c, r, fill=INK, outline=INK, width=5)
                pen.svg(K.check_svg(YELLOW, 16), K.ICON_VB, c - 30, c - 30, 60)
            elif state == "cur":
                pen.ell(c + 7, c + 7, r, fill=INK)
                pen.ell(c, c, r, fill=RED, outline=INK, width=6)
                s = 64
                pen.text(c, c + cap_h("anton", s) / 2, str(k + 1), "anton", s, OFF, anchor="ms")
            else:
                pen.ell(c, c, r, fill=OFF, outline=INK, width=5)
                s = 46
                pen.text(c, c + cap_h("anton", s) / 2, str(k + 1), "anton", s, INK, anchor="ms")
            self._nodes[key] = (pen.done(), c)
        return self._nodes[key]

    def prog_base(self) -> Image.Image:
        if "prog" not in self._layers:
            pen = K.Pen(*PROG)
            for k in range(self.N - 1):
                dashed(pen, self.node_x[k] + 44, PROG_CY, self.node_x[k + 1] - 44, INK, dash=18, gap=12, w=6)
            self._layers["prog"] = pen.done()
        return self._layers["prog"]

    def last_park(self) -> float:
        """Son adımda makasın durduğu pim x'i: son düğümün (patlarken büyüyen kırmızı düğüm, r 52 x 1,25) solunda, onun
        üstüne binmeden; adımlar sıkışıksa önceki düğümün sağ kenarına kadar."""
        nx = self.node_x
        k = self.N - 1
        x = nx[k] - 52 * 1.25 - 6 - SC_W * (1 - SC_PIN)
        if k > 0:
            x = max(x, nx[k - 1] + 42 + SC_W * SC_PIN)
        return x

    def scissors_at(self, t: float) -> tuple[float | None, float, bool, float]:
        """İlerleme makasının pimi (x, y kayması, kesiyor mu, kesilen çizginin ucu). x None: makas yok (özet)."""
        nx = self.node_x
        park = nx[0] - 66
        if not self.steps or t < self.steps[0].start:
            return park, 0.0, False, park
        if self.segs[-1].kind == "recap" and t >= self.segs[-1].start:
            return None, 0.0, False, nx[-1]
        k = bisect.bisect_right([s.start for s in self.steps], t) - 1
        s = self.steps[k]
        lt = t - s.start
        if k == 0:
            prev = park
        else:
            prev = nx[k - 1] + 70 + (nx[k] - nx[k - 1] - 140) * CUT_SHARE
        left = nx[k] - 46
        if lt < T_REACH:                     # kalan çizgiyi düğüme kadar keser
            x = K.lerp(prev, left, K.ease_in_out(lt / T_REACH))
            return x, 0.0, True, x
        if k == self.N - 1:                  # son düğüm: kesilecek çizgi kalmadı; makas geri çekilip solda durur
            p = K.clamp((lt - T_REACH) / T_HOP)
            x = K.lerp(left, self.last_park(), K.ease_out_cubic(p))
            return x, -18 * math.sin(math.pi * p), False, nx[k]
        right = nx[k] + 70
        if lt < T_REACH + T_HOP:             # düğümün üstünden atlar
            p = (lt - T_REACH) / T_HOP
            x = K.lerp(left, right, K.ease_in_out(p))
            return x, -34 * math.sin(math.pi * p), False, max(x, nx[k])
        span = max(0.5, (s.end - s.start) - T_REACH - T_HOP)
        p = K.clamp((lt - T_REACH - T_HOP) / span)
        x = right + (nx[k + 1] - nx[k] - 140) * CUT_SHARE * p
        return x, 0.0, True, x

    def node_states(self, t: float) -> list[tuple[str, float]]:
        """Her düğüm için (durum, patlama ölçeği)."""
        out = []
        recap = self.segs[-1].start if self.segs and self.segs[-1].kind == "recap" else None
        for k, s in enumerate(self.steps):
            nxt = self.steps[k + 1].start if k + 1 < self.N else recap
            if nxt is not None and t >= nxt:
                out.append(("done", bump((t - nxt) / 0.28, 1.22)))
            elif t >= s.start + T_REACH:
                out.append(("cur", bump((t - s.start - T_REACH) / 0.3, 1.25)))
            else:
                out.append(("up", 1.0))
        return out

    def progress(self, img: Image.Image, t: float) -> None:
        if not self.N:
            return
        if self.belt:
            self.belt_progress(img, t)
            return
        lay = self.prog_base().copy()
        ox, oy = PROG[:2]
        x, dy, cutting, bar = self.scissors_at(t)
        nx = self.node_x
        bar = max(nx[0], bar)
        if bar > nx[0] + 1:
            ImageDraw.Draw(lay).rounded_rectangle([nx[0] - ox, PROG_CY - 6 - oy, bar - ox, PROG_CY + 6 - oy], 6,
                                                  fill=INK + (255,))
        for k, (state, sc) in enumerate(self.node_states(t)):
            im, c = self.node(state, k)
            if abs(sc - 1) > 0.01:
                im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
                c = c * sc
            K._comp(lay, im, nx[k] - c - ox, PROG_CY - c - oy)
        if x is not None:
            snip = cutting or (self.intro and t < 0.8)
            ang = (32 if int(t * 16) % 2 else 12) if snip else 26
            sc = K.scissors_icon(SC_W, ang)
            K._comp(lay, sc, x - SC_W * SC_PIN - ox, PROG_CY - sc.height / 2 + dy - oy)
        K.put(img, lay, ox, oy, clip=CLIP)

    # ------------------------------------------------------------ yürüyen bant (uretim)
    def belt_base(self, phase: int) -> Image.Image:
        """Bandın faz başına bir kez çizilen hâli: ayaklar, sert gölge, mürekkep halka, içte makaralar (çapraz çizgileri
        faz x 15° döner) ve üst koldaki açık diş izleri (faz x 4 px kayar)."""
        key = ("belt", phase)
        if key not in self._layers:
            pen = K.Pen(*PROG)
            x0, x1, y0, y1 = BELT_X0, BELT_X1, BELT_Y0, BELT_Y1
            r = (y1 - y0) / 2
            for lx in (x0 + 70, (x0 + x1) / 2, x1 - 70):              # ayaklar
                pen.poly([(lx - 12, y1 - 2), (lx + 12, y1 - 2), (lx + 18, BELT_LEG), (lx - 18, BELT_LEG)], INK)
            pen.rr((x0 + 6, y0 + 6, x1 + 6, y1 + 6), r, fill=INK)     # sert gölge
            pen.rr((x0, y0, x1, y1), r, fill=INK)
            pen.rr((x0 + BELT_RUN, y0 + BELT_RUN, x1 - BELT_RUN, y1 - BELT_RUN), r - BELT_RUN, fill=BELT_COL)
            cy, rr = (y0 + y1) / 2, r - BELT_RUN - 3
            ang = math.radians(phase * 15)
            n = 13
            for i in range(n):                                        # makaralar
                cx = x0 + r + (x1 - x0 - 2 * r) * i / (n - 1)
                pen.ell(cx, cy, rr, fill=OFF, outline=INK, width=3)
                for a in (ang, ang + math.pi / 2):
                    dx, dy = math.cos(a) * (rr - 2), math.sin(a) * (rr - 2)
                    pen.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], INK, 2.5)
                pen.ell(cx, cy, 2.6, fill=YELLOW)
            x = x0 + r + phase * TREAD / 6                            # diş izleri (üst kol)
            while x < x1 - r - 6:
                pen.rr((x, y0 + 2, x + 8, y0 + BELT_RUN - 2), 1.5, fill=(112, 109, 104))
                x += TREAD
            self._layers[key] = pen.done()
        return self._layers[key]

    def box(self, state: str, k: int) -> Image.Image:
        """Aşama kutusu (karton): sıradaki kırık beyaz + mürekkep numara, şimdiki kırmızı + kırık beyaz numara, biten
        mürekkep + sarı ✓; üstte sarı bant, sert gölge. Görüntünün alt ortası kutunun tabanıdır (gölge payı hariç)."""
        key = ("box", state, k)
        if key not in self._nodes:
            w, h = BOX[state]
            sh, pad = 6, 4
            pen = K.Pen(0, 0, w + sh + 2 * pad, h + sh + 2 * pad)
            bx = (pad, pad, pad + w, pad + h)
            fill, num = {"up": (OFF, INK), "cur": (RED, OFF), "done": (INK, None)}[state]
            pen.rr((bx[0] + sh, bx[1] + sh, bx[2] + sh, bx[3] + sh), 7, fill=INK)
            pen.rr(bx, 7, fill=fill, outline=INK, width=5 if state != "cur" else 6)
            flap = bx[1] + h * 0.24
            pen.line([(bx[0] + 4, flap), (bx[2] - 4, flap)], INK if state != "done" else (90, 88, 85), 3)
            tw_ = w * 0.26                                             # bant: kapak çizgisinden üste
            pen.rr((pad + w / 2 - tw_ / 2, bx[1] + 3, pad + w / 2 + tw_ / 2, flap + 2), 2, fill=YELLOW)
            cyb = flap + (bx[3] - flap) / 2
            if num is None:
                s = h * 0.62
                pen.svg(K.check_svg(YELLOW, 16), K.ICON_VB, pad + w / 2 - s / 2, cyb - s / 2, s)
            else:
                s = 50 if state == "cur" else 40
                pen.text(pad + w / 2, cyb + cap_h("anton", s) / 2, str(k + 1), "anton", s, num, anchor="ms")
            self._nodes[key] = pen.done()
        return self._nodes[key]

    def belt_offset(self, t: float) -> float:
        """Bandın kayması (px): Makas'ın pimini izler ama hızı BELT_VMAX ile sınırlıdır. Makas düğüme varırken ve
        üstünden atlarken karede 15-29 px gider; desen 24 px'te (6 fazda) döndüğü için ham konum diş izlerini ve makara
        çizgilerini geri, ileri ya da yerinde oynatırdı. Kayma videonun başından bir kez çizelgelenir (kare yalnız t'ye
        bağlı kalır); Makas yokken (özet) bant durur."""
        if self._belt_off is None:
            dt = 1 / (FPS * 4)
            end = max([self.segs[-1].end] + [w.end for w in self.words[-1:]]) + 2.0
            prev = self.scissors_at(0.0)[0]
            off, tab = prev if prev is not None else self.node_x[-1], []
            for i in range(int(end / dt) + 2):
                x = self.scissors_at(i * dt)[0]
                if x is not None and prev is not None:
                    off += K.clamp(x - prev, -BELT_VMAX * dt, BELT_VMAX * dt)
                prev = x if x is not None else prev
                tab.append(off)
            self._belt_off = (dt, tab)
        dt, tab = self._belt_off
        return tab[min(len(tab) - 1, max(0, int(round(t / dt))))]

    def belt_progress(self, img: Image.Image, t: float) -> None:
        """Yürüyen bant: kutular düğümlerin yerinde bandın üstünde, Makas (ilerleme makası) bandın üstünde kutudan
        kutuya ilerler; bant onunla birlikte, hızı sınırlı olarak kayar (belt_offset), işlenen kısmı (ilk kutudan
        Makas'a) kırmızıdır."""
        x, dy, cutting, bar = self.scissors_at(t)
        nx = self.node_x
        phase = int(round(self.belt_offset(t) / (TREAD / 6))) % 6
        lay = self.belt_base(phase).copy()
        ox, oy = PROG[:2]
        bar = max(nx[0], bar)
        if bar > nx[0] + 1:
            ImageDraw.Draw(lay).rounded_rectangle([nx[0] - ox, BELT_Y0 - oy, bar - ox, BELT_Y0 + BELT_RUN - oy], 3,
                                                  fill=RED + (255,))
        for k, (state, sc) in enumerate(self.node_states(t)):
            im = self.box(state, k)
            w, h = BOX[state]
            # tabanı bantta kalarak büyür; çerçevesi katmanın (PROG) üst kenarına değmez
            sc = min(1 + (sc - 1) * BOX_POP, (BELT_Y0 - PROG[1] - 4) / (4 + h))
            if abs(sc - 1) > 0.01:
                im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
            K._comp(lay, im, nx[k] - (4 + w / 2) * sc - ox, BELT_Y0 + 1 - (4 + h) * sc - oy)
        if x is not None:
            snip = cutting or (self.intro and t < 0.8)
            ang = (32 if int(t * 16) % 2 else 12) if snip else 26
            sc = K.scissors_icon(SC_W, ang)
            K._comp(lay, sc, x - SC_W * SC_PIN - ox, BELT_Y0 - sc.height + 4 + dy - oy)
        K.put(img, lay, ox, oy, clip=CLIP)

    # ------------------------------------------------------------ kanca
    def drawing(self, path: Path, w: float, h: float) -> Image.Image:
        """Çizimi (şeffaf PNG) saydam kenarlarından kırpıp w x h kutuya sığdırır (2x)."""
        key = ("draw", str(path), round(w), round(h))
        if key not in self._layers:
            im = Image.open(path).convert("RGBA")
            bb = im.getchannel("A").getbbox()
            if bb:
                im = im.crop(bb)
            k = min(w / im.width, h / im.height)
            self._layers[key] = im.resize((max(1, int(im.width * k * SS)), max(1, int(im.height * k * SS))),
                                          Image.LANCZOS)
        return self._layers[key]

    def photo(self, path: Path, w: float, h: float) -> Image.Image:
        """Fotoğraf (çizim yoksa): kutuyu dolduracak biçimde kırpılmış, yuvarlak köşeli (2x)."""
        src = Image.open(path).convert("RGB")
        im = K.cover(src, int(w * SS), int(h * SS)).convert("RGBA")
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], 18 * SS, fill=255)
        im.putalpha(mask)
        return im

    def hook_layout(self, seg: Segment):
        """Kanca başlığının boyutu ve satır ölçüleri; çizim kartı başlığın altında en az 300 px yer bulur."""
        lines = seg.title or [self.kicker]
        has_pic = seg.sprite is not None or seg.image is not None
        max_h = (CARD[3] - 300 - 44 if has_pic else CARD[3] - 40) - HOOK_TOP
        for size in range(156, 70, -4):
            hs = round(size * 0.86)
            rows = []
            for i, L in enumerate(lines):
                if i == seg.hl:
                    fS = K.fnt("anton", hs * SS)
                    l, tt, r, bb = fS.getbbox(L, anchor="ls")
                    top = max(cap_h("anton", hs), -tt / SS)
                    h = top + max(0.0, bb / SS) + 2 * hs * 0.16
                    rows.append(("label", L, hs, label_w(L, hs) + 24, h, top))
                else:
                    l, tt, r, bb = K.tbox(L, "anton", size)
                    rows.append(("text", L, size, K.tw(L, "anton", size), -tt + max(0.0, bb), -tt))
            gap = size * 0.2
            total = sum(r[4] for r in rows) + gap * (len(rows) - 1)
            if all(r[3] <= X1 - X0 for r in rows) and total <= max_h:
                return rows, gap, total
        return rows, gap, total

    def hook_content(self, seg: Segment) -> Image.Image:
        key = ("hook", seg.scenes[0])
        if key in self._layers:
            return self._layers[key]
        pen = K.Pen(*CONTENT)
        rows, gap, total = self.hook_layout(seg)
        y = HOOK_TOP
        for kind, L, size, w, h, top in rows:
            if kind == "label":
                paste_label(pen, L, size, OFF, RED, 703, X0 + (w - 24) / 2 + 4, y + h / 2, rot=1.5,
                            shadow=(9, 11, 0, 0.95))
            else:
                pen.text(X0, y + top, L, "anton", size, INK)
            y += h + gap
        if seg.sprite is not None or seg.image is not None:
            top = y - gap + 44
            pad = 26
            ih = CARD[3] - top - 2 * pad
            if seg.sprite is not None:
                x1 = 690                    # taslaktaki gibi: Makas kartın sağında durur
                card_box(pen, (X0, top, x1, CARD[3]))
                d = self.drawing(seg.sprite, x1 - X0 - 2 * pad, ih)
                pen.paste(d, (X0 + x1) / 2 - d.width / SS / 2, top + pad + (ih - d.height / SS) / 2)
            else:
                x1 = 690
                card_box(pen, (X0, top, x1, CARD[3]))
                pen.paste(self.photo(seg.image, x1 - X0 - 2 * pad, ih), X0 + pad, top + pad)
                pen.rr((X0 + pad, top + pad, x1 - pad, top + pad + ih), 18, outline=INK, width=4)
                self._chip(pen, seg, X0 + pad + 14, top + pad + ih - 74, x1 - X0 - 2 * pad - 30)
        self._layers[key] = pen.done()
        self._layers[("box", seg.scenes[0])] = (X0, HOOK_TOP, X1, CARD[3])
        return self._layers[key]

    def _chip(self, pen, seg, x, y, max_w):
        note = K.credit_chip(seg.credit)
        if note:
            K.chip_label(pen, x, y, note, max_w=max_w)

    # ------------------------------------------------------------ adım kartı
    def mascot_zone(self, seg: Segment) -> tuple[np.ndarray, int, int]:
        """Adım pozundaki Makas'ın gövdesi ve bıçakları (işaret eden kol hariç: kol çizimi gösterebilir), 8 px payla:
        (ekrandaki opak maske, sol üst x, y)."""
        cx, cy, sc, _ = POSE["step"]
        mood = seg.mascot if seg.mascot in K.MOODS else MOOD["step"]
        im = self.mascot.sprite(mood, "rest", False, None, sc)
        a = im.getchannel("A").point(lambda v: 255 if v > 60 else 0).filter(ImageFilter.MaxFilter(17))
        ox, oy = Mascot.origin(cx, cy, sc)
        return np.asarray(a) > 0, int(round(ox)), int(round(oy))

    def fit_drawing(self, seg: Segment, box) -> tuple[Image.Image, float, float]:
        """Çizimi kutuya sığdırır; Makas'ın gövdesi ya da bıçakları çizimin üstüne binecekse kutunun sağ kenarı (en çok
        %35) daraltılır: çizim biraz küçülüp sola kayar, ayrıntısı maskotun arkasında kalmaz."""
        ax0, ay0, ax1, ay1 = box
        zone, zx, zy = self.mascot_zone(seg)
        best = None
        for right in range(int(ax1), int(ax0 + (ax1 - ax0) * 0.65) - 1, -10):
            d = self.drawing(seg.sprite, right - ax0, ay1 - ay0)
            dw, dh = d.width / SS, d.height / SS
            dx, dy = (ax0 + right) / 2 - dw / 2, (ay0 + ay1) / 2 - dh / 2
            a = np.asarray(d.getchannel("A").resize((max(1, int(dw)), max(1, int(dh))))) > 140
            # çizimin maskot bölgesiyle kesişen kısmı
            x0, y0 = max(int(dx), zx), max(int(dy), zy)
            x1, y1 = min(int(dx) + a.shape[1], zx + zone.shape[1]), min(int(dy) + a.shape[0], zy + zone.shape[0])
            hit = 0
            if x1 > x0 and y1 > y0:
                hit = int((a[y0 - int(dy):y1 - int(dy), x0 - int(dx):x1 - int(dx)]
                           & zone[y0 - zy:y1 - zy, x0 - zx:x1 - zx]).sum())
            if best is None or hit < best[0]:
                best = (hit, d, dx, dy)
            if hit <= 40:
                break
        return best[1], best[2], best[3]

    def step_card(self, seg: Segment):
        """(kart katmanı, numara etiketi, [(not katmanı, sol üst)]) — kart katmanı CONTENT bölgesini kaplar."""
        key = ("step", seg.number)
        if key in self._layers:
            return self._layers[key]
        x0, y0, x1, y1 = CARD
        pen = K.Pen(*CONTENT)
        card_box(pen, CARD)
        # başlık: numaranın sağında, 1-3 satır
        hx0 = x0 + 222
        hw = x1 - 40 - hx0
        size, lines = fit_lines(seg.title, "anton", hw, 112, 54, 3, 196, pitch=title_pitch)
        capH = cap_h("anton", size)
        lh = title_pitch(lines, size)
        block = capH + (len(lines) - 1) * lh
        ty = y0 + 36 + (200 - block) / 2
        for k, L in enumerate(lines):
            pen.text(hx0, ty + capH + k * lh, L, "anton", size, INK)
        bottom = ty + capH + (len(lines) - 1) * lh + max(0.0, K.tbox(lines[-1], "anton", size)[3])
        # 'buradan kesin' çizgisi + küçük makas
        yc = max(bottom, y0 + 238) + 30
        dashed(pen, x0 + 96, yc, x1 - 36, RULE_GREY, dash=16, gap=10, w=4)
        pen.svg(K.scissors_svg(26, outline=INK), K.SCISSORS_VB, x0 + 28, yc - 22, 56)
        # çizim alanı (sağ alt köşede Makas durur)
        ax0, ay0, ax1, ay1 = x0 + 30, yc + 22, x1 - 150, y1 - 28
        mask = None
        if seg.sprite is not None:
            d, dx, dy = self.fit_drawing(seg, (ax0, ay0, ax1, ay1))
            dw, dh = d.width / SS, d.height / SS
            pen.paste(d, dx, dy)
            a = np.asarray(d.getchannel("A").resize((max(1, int(dw)), max(1, int(dh)))))
            pts = np.argwhere(a > 140)
            mask = (pts[:, 1] + dx, pts[:, 0] + dy) if len(pts) else None
        elif seg.image is not None:
            pen.paste(self.photo(seg.image, ax1 - ax0, ay1 - ay0), ax0, ay0)
            pen.rr((ax0, ay0, ax1, ay1), 18, outline=INK, width=4)
            self._chip(pen, seg, ax0 + 14, ay1 - 74, ax1 - ax0 - 30)
        else:                     # görsel yoksa büyük soluk numara
            s = 420
            pen.text((ax0 + ax1) / 2, (ay0 + ay1) / 2 + cap_h("anton", s) / 2, str(seg.number), "anton", s,
                     (232, 229, 221), anchor="ms")
        base = pen.done()
        # numara etiketi (damga) ve küçük notlar (patlar) ayrı katmanlar
        ns = 200
        while label_w(str(seg.number), ns) > 200 and ns > 120:
            ns -= 10
        num = label_img(str(seg.number), ns, OFF, RED, 900 + seg.number, rot=-4.0, shadow=(9, 11, 0, 0.95))
        callouts = []
        for ci, text in enumerate(seg.callouts):
            callouts.append(self._callout(ci, text, (ax0, ay0, x1 - 36, ay1), mask, seg.number))
        self._layers[key] = (base, num, [c for c in callouts if c])
        return self._layers[key]

    def _callout(self, ci, text, area, mask, seed):
        """Not etiketi: 0. not sağ üstte kırmızı, kısa bir çizgiyle çizimin en yakın noktasına bağlanır; 1. not sol
        üstte sarı (mürekkep kenarlı)."""
        ax0, ay0, ax1, ay1 = area
        size = 36 if ci == 0 else 32
        while size > 24 and label_w(text, size) > 380:
            size -= 2
        lw = label_w(text, size)
        pen = K.Pen(*CONTENT)
        if ci == 0:
            cx, cy = ax1 - lw / 2, ay0 + 48
            if mask is not None:
                sx, sy = cx - lw / 2 + 18, cy + size * 0.55
                d2 = (mask[0] - sx) ** 2 + (mask[1] - sy) ** 2
                j = int(np.argmin(d2))
                tx, ty = float(mask[0][j]), float(mask[1][j])
                if 30 ** 2 < d2[j] < 260 ** 2:
                    pen.line([(sx, sy), (tx, ty)], RED, 4)
                    pen.ell(tx, ty, 7, fill=RED)
            paste_label(pen, text, size, OFF, RED, 711 + seed, cx, cy, rot=-2, shadow=None)
        else:
            cx, cy = ax0 + 4 + lw / 2, ay0 + 30
            paste_label(pen, text, size, INK, YELLOW, 712 + seed, cx, cy, rot=-4, shadow=None, rim=INK)
        im = pen.done()
        bb = im.getchannel("A").getbbox()
        if not bb:
            return None
        return im.crop(bb), (CONTENT[0] + bb[0], CONTENT[1] + bb[1]), (cx, cy)

    def step_final(self, seg: Segment) -> Image.Image:
        """Adım kartının oturmuş hâli (kesme geçişinde kesilen katman)."""
        key = ("stepfin", seg.number)
        if key not in self._layers:
            base, num, callouts = self.step_card(seg)
            lay = base.copy()
            K._comp(lay, num, NUM_C[0] - num.width / 2 - CONTENT[0], NUM_C[1] - num.height / 2 - CONTENT[1])
            for im, (x, y), _ in callouts:
                K._comp(lay, im, x - CONTENT[0], y - CONTENT[1])
            self._layers[key] = lay
        return self._layers[key]

    def draw_step(self, img: Image.Image, seg: Segment, lt: float, enter: bool) -> None:
        base, num, callouts = self.step_card(seg)
        ox, oy = CONTENT[:2]
        if not enter:
            K.put(img, self.step_final(seg), ox, oy, clip=CLIP)
            return
        p = (lt - SLIDE0) / SLIDE
        if p <= 0:
            return
        dx = (1 - K.ease_out_back(p, 1.2)) * 960
        if dx > 0.5:                  # kart sağ kenardan girerken (x=935 kırpması) yumuşak belirir
            base = feather_right(base, ox + dx, strength=K.clamp(dx / 40))
        K.put(img, base, ox + dx, oy, clip=CLIP)
        ps = (lt - STAMP0) / STAMP
        if ps > 0:                 # numara: büyükten hızla iner, hafifçe ezilip oturur
            if ps < 1:
                k, al = K.lerp(1.8, 0.94, ps ** 2), min(1.0, ps * 3)
            else:
                k, al = K.lerp(0.94, 1.0, K.ease_out_cubic((ps - 1) * STAMP / 0.12)), 1.0
            K.put(img, num, NUM_C[0] - num.width / 2 + dx, NUM_C[1] - num.height / 2, k=k, alpha=al, clip=CLIP)
        for j, (im, (x, y), _) in enumerate(callouts):
            pc = (lt - NOTE0 - 0.2 * j) / 0.26
            if pc > 0:
                K.put(img, im, x + dx, y, k=ease_pop(pc, 1.14), clip=CLIP)

    # ------------------------------------------------------------ özet
    def recap_parts(self, seg: Segment):
        key = ("recap", seg.scenes[0])
        if key in self._layers:
            return self._layers[key]
        n = max(1, self.N)
        gap = 15 if n <= 4 else 12
        rh = min(122, (560 - gap * (n - 1)) / n)
        rows, y = [], 458
        for k, st in enumerate(self.steps):
            box = (X0, y, X1 - 10, y + rh)
            pen = K.Pen(X0 - 4, y - 4, X1 + 4, y + rh + 14)
            card_box(pen, box, r=22, sh=9, w=5)
            sq = rh - 36
            pen.rr((X0 + 18, y + 18, X0 + 18 + sq, y + rh - 18), 14, fill=RED, outline=INK, width=4)
            s = min(66, sq * 0.78)
            pen.text(X0 + 18 + sq / 2, y + rh / 2 + cap_h("anton", s) / 2, str(k + 1), "anton", s, OFF, anchor="ms")
            tx = X0 + 18 + sq + 22
            room = X1 - 10 - 124 - tx
            text = " ".join(st.title)
            size, lines = fit_lines([text], "anton", room, min(54, int(rh * 0.44)), 30, 2, rh - 30, pitch=row_pitch)
            capH = cap_h("anton", size)
            lh2 = row_pitch(lines, size)
            b0 = y + rh / 2 - (len(lines) - 1) * lh2 / 2 + capH / 2
            for li, L in enumerate(lines):
                pen.text(tx, b0 + li * lh2, K.fit_words(L, "anton", size, room), "anton", size, INK)
            cx = X1 - 10 - 62
            pen.ell(cx, y + rh / 2, min(38, rh * 0.32), fill=YELLOW, outline=INK, width=5)
            rows.append((pen.done(), (X0 - 4, y - 4), (cx, y + rh / 2)))
            y += rh + gap
        tick = K.svg_img(K.check_svg(INK, 15), K.ICON_VB, 56 * SS, 56 * SS).resize((56, 56), Image.LANCZOS)
        # NEDEN? kutusu
        nb = (X0, y + 26, X1 - 10, y + 26 + 232)
        # kanal sekmesi kutunun altından sarkar: tuval onu da kapsasın (yoksa ince bir şerit kalıyordu)
        pen = K.Pen(nb[0] - 2, nb[1] - 2, nb[2] + 2, nb[3] + 44)
        card_box(pen, nb, fill=INK, r=26, sh=0, w=5)
        if self.handle:
            self._handle_tab(pen, nb[0] + 30, nb[3] - 2, anchor="left_bottom")
        box_img = (pen.done(), (nb[0] - 2, nb[1] - 2))
        tags = {}                       # dış ses kutusunun etiketi: neden (NEDEN?) ve soru (SENCE?)
        for kind, tag, seed in (("neden", self.var["ozet_kutusu"], 721), ("soru", "SENCE?", 723)):
            tags[kind] = label_img(tag, 50, INK, YELLOW, seed, rot=-3, shadow=None, rim=INK)
        rect = (nb[0] + 40, nb[1] + 62, nb[2] - 40, nb[3] - 26)
        # kapanış: kaydet etiketi; "Yorumlara yaz" söylenince kart şablonunun yorum çıkartması
        save = label_img(self.var["kapanis"], 52, OFF, RED, 722, rot=-1.5, shadow=(6, 8, 0, 0.9))
        sticker = K.cta_sticker(up(K.CtaCard.BUTTON), 600, size=76)
        cta_y = nb[3] + (SAFE[3] - 24 - nb[3]) / 2
        out = dict(rows=rows, tick=tick, box=box_img, nb=nb, tags=tags, rect=rect, save=save, sticker=sticker,
                   cta_y=cta_y)
        self._layers[key] = out
        return out

    def recap_cta(self, seg: Segment) -> int | None:
        """Özetin sonundaki 'Yorumlara yaz' çağrısının ilk kelimesi (en çok 4 kelimelik kuyruk): bu kelimeler NEDEN?/SENCE?
        kutusuna yazılmaz, söylendikleri anda YORUMLARA YAZ çıkartması belirir. Çağrı yoksa ya da sonda değilse None."""
        key = ("cta", seg.scenes[0])
        if key not in self._q_breaks:
            out = None
            for i in range(max(seg.a, seg.b - 4), seg.b):
                if Q_RE.match(" ".join(self.words[j].text for j in range(i, seg.b))):
                    out = i
                    break
            self._q_breaks[key] = out
        return self._q_breaks[key]

    def recap_breaks(self, seg: Segment) -> set[int]:
        """Özette soru cümlesinin (ya da 'Yorumlara yaz' içeren cümlenin) ilk kelimesi: kutu SENCE? olur."""
        if seg.scenes[0] in self._q_breaks:
            return self._q_breaks[seg.scenes[0]]
        out, sent = set(), []
        for i in range(seg.a, seg.b):
            sent.append(i)
            t = self.words[i].text.rstrip('"“”»)’\'')
            if t[-1:] in ".?!…":
                text = " ".join(self.words[j].text for j in sent)
                if t.endswith("?") or Q_RE.search(text):
                    out.add(sent[0])
                    break
                sent = []
        self._q_breaks[seg.scenes[0]] = out
        return out

    def draw_recap(self, img: Image.Image, seg: Segment, lt: float, t: float) -> None:
        R = self.recap_parts(seg)
        for k, (im, (x, y), (cx, cy)) in enumerate(R["rows"]):
            p = (lt - RECAP0 - 0.13 * k) / 0.3
            if p <= 0:
                continue
            K.put(img, im, x, y - 60 * (1 - K.ease_out_back(p, 1.3)), alpha=min(1.0, p * 3), clip=CLIP)
            pt = (lt - RECAP0 - 0.13 * k - 0.24) / 0.26
            if pt > 0:
                tk = R["tick"]
                K.put(img, tk, cx - tk.width / 2, cy - tk.height / 2, k=ease_pop(pt, 1.3), clip=CLIP)
        pb = K.ease_out_cubic((lt - RECAP0) / 0.24)
        if pb <= 0:
            return
        dy = 40 * (1 - pb)
        pb = min(1.0, pb * 3)               # yarı saydam koyu kutu bulanık görünür: hızla tam opak olur
        box, (bx, by) = R["box"]
        K.put(img, box, bx, by + dy, alpha=pb, clip=CLIP)
        sp = self.speech(seg)
        breaks = self.recap_breaks(seg)
        cur = min(self.cur_word(t, seg), sp.b)    # çağrı kelimeleri okunurken kutudaki metnin hepsi söylenmiş
        q = sp.page_kind(cur, breaks)
        tag = R["tags"]["soru" if q else "neden"]
        nb = R["nb"]
        k = 1.0
        if q:
            qs = self.words[min(breaks)].start - 0.12 - seg.start
            k = ease_pop((lt - qs) / 0.25, 1.2) if lt - qs < 0.25 else 1.0
        K.put(img, tag, nb[0] + 40, nb[1] + 4 - tag.height / 2 + dy, k=k, alpha=pb, clip=CLIP)
        sp.put(img, cur, dy, alpha=pb)
        # kapanış: kaydet etiketi; yorum çağrısı söylenince (çağrı yoksa soru gelince) yorum çıkartması
        cy = R["cta_y"]
        cta = self.recap_cta(seg)
        if cta is not None:
            cs = self.words[cta].start - 0.08 - seg.start
        elif breaks:
            cs = self.words[min(breaks)].start - 0.12 - seg.start
        else:
            cs = None
        if cs is not None and lt >= cs:
            st = R["sticker"]
            kk = ease_pop((lt - cs) / 0.28, 1.15) * K.cta_pulse(lt - cs)
            K.put(img, st, X0 - 6, cy - st.height / 2, k=kk, clip=CLIP, anchor=(0.3, 0.5))
        else:
            ps = (lt - RECAP0 - 0.8) / 0.3
            if ps > 0:
                sv = R["save"]
                K.put(img, sv, X0, cy - sv.height / 2, k=ease_pop(ps, 1.12), clip=CLIP, anchor=(0.3, 0.5))

    # ------------------------------------------------------------ balon
    def speech(self, seg: Segment) -> Speech:
        key = seg.scenes[0]
        if key not in self._speech:
            if seg.kind == "recap":   # sondaki yorum çağrısı kutuya değil çıkartmaya yazılır
                R = self.recap_parts(seg)
                cta = self.recap_cta(seg)
                b = cta if cta is not None and cta > seg.a else seg.b
                self._speech[key] = Speech(self.words, seg.a, b, R["rect"], sizes=(38, 36, 34, 32),
                                           breaks={i for i in self.recap_breaks(seg) if i < b})
            else:
                x0, y0, x1, y1 = BUBBLE
                self._speech[key] = Speech(self.words, seg.a, seg.b, (x0 + 36, y0 + 20, x1 - 36, y1 - 20))
        return self._speech[key]

    def _handle_tab(self, pen: K.Pen, x, y, anchor="left_top"):
        """Kanal adı sekmesi: 'makas@bilgimakasi' (mono, kırık beyaz + sarı), mürekkep zeminde."""
        fs = 26
        a, b = "makas", self.handle
        w = K.tw(a + b, "mono", fs) + 32
        h = 40
        if anchor == "left_top":
            x0, y0 = x, y - h + 6
        elif anchor == "left_bottom":
            x0, y0 = x, y - 6
        else:
            x0, y0 = x - w, y - 6
        pen.rr((x0, y0, x0 + w, y0 + h), 12, fill=INK)
        pen.text(x0 + 16, y0 + 28, a, "mono", fs, OFF)
        pen.text(x0 + 16 + K.tw(a, "mono", fs), y0 + 28, b, "mono", fs, YELLOW)

    def bubble_base(self) -> Image.Image:
        if "bubble" not in self._layers:
            x0, y0, x1, y1 = BUBBLE
            pen = K.Pen(x0 - 4, y0 - 50, x1 + 10, y1 + 10)
            pen.rr((x0 + 8, y0 + 8, x1 + 8, y1 + 8), 26, fill=(0, 0, 0, 60))
            pen.rr(BUBBLE, 26, fill=INK)
            pen.poly([(TAIL_X - 34, y0 + 2), (TAIL_X + 14, y0 - 40), (TAIL_X + 10, y0 + 2)], INK)
            if self.handle:
                self._handle_tab(pen, x0 + 26, y0)
            self._layers["bubble"] = (pen.done(), (x0 - 4, y0 - 50))
        return self._layers["bubble"]

    def draw_bubble(self, img: Image.Image, seg: Segment, t: float, dy: float = 0.0, alpha: float = 1.0) -> None:
        im, (x, y) = self.bubble_base()
        K.put(img, im, x, y + dy, alpha=alpha, clip=CLIP)
        self.speech(seg).put(img, self.cur_word(t, seg), dy, alpha)

    # ------------------------------------------------------------ Makas
    def pose(self, seg: Segment) -> tuple[float, float, float, float | None]:
        return POSE[seg.kind]

    def draw_mascot(self, img: Image.Image, t: float, si: int, lt: float) -> None:
        seg = self.segs[si]
        cx, cy, sc, point = self.pose(seg)
        mood = seg.mascot if seg.mascot in K.MOODS else MOOD[seg.kind]
        hop = 0.0
        if si > 0:
            pcx, pcy, psc, _ = self.pose(self.segs[si - 1])
            p = K.clamp(lt / 0.4)
            if (pcx, pcy, psc) != (cx, cy, sc) and p < 1:   # yerleşim değişti: yeni yerine sıçrar
                e = K.ease_in_out(p)
                cx, cy, scl = K.lerp(pcx, cx, e), K.lerp(pcy, cy, e), K.lerp(psc, sc, e)
                hop = -60 * math.sin(math.pi * p)
                im = self.mascot.sprite(mood, "rest", False, point, sc)
                k = scl / sc
                ox, oy = Mascot.origin(cx, cy, scl)
                K.put(img, im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.BILINEAR),
                      ox, oy + hop, clip=CLIP)
                return
            if p < 1:                                        # yeni adım: küçük bir zıplama
                hop = -22 * math.sin(math.pi * K.clamp(lt / 0.32))
        mouth = K.talk_state(self.words, self.starts, t)
        blink = (t % 3.6) > 3.45 and mood not in ("happy", "surprised")
        im = self.mascot.sprite(mood, mouth, blink, point, sc)
        bob = round(3 * math.sin(t * 2 * math.pi * 0.55))
        ox, oy = Mascot.origin(cx, cy, sc)
        K.put(img, im, ox, oy + bob + hop, clip=CLIP)

    # ------------------------------------------------------------ kare
    def final_content(self, seg: Segment) -> tuple[Image.Image | None, tuple]:
        """Bölümün oturmuş içerik katmanı ve kesme çizgisinin dayandığı kutu."""
        if seg.kind == "hook":
            lay = self.hook_content(seg)
            return lay, self._layers[("box", seg.scenes[0])]
        if seg.kind == "step":
            return self.step_final(seg), CARD
        return None, CARD

    def frame(self, t: float, grain: bool = True) -> Image.Image:
        si = self.seg_at(t)
        seg = self.segs[si]
        lt = t - seg.start
        img = (kraft_bg() if self.var["zemin"] == "kraft" else yellow_bg()).copy()
        img.alpha_composite(self.header(seg), HEAD[:2])
        self.progress(img, t)
        ox, oy = CONTENT[:2]
        enter = si > 0
        if enter and lt < CUT:              # önceki bölümün içeriği makasla kesilir
            old, box = self.final_content(self.segs[si - 1])
            if old is not None:
                K.card_cut(img, old, lt, si, origin=CONTENT[:2], card=box, x_end=SAFE[2] - 66,
                           clip_top=(0, SAFE[1] + 250, SAFE[2], CONTENT[3]),
                           clips_bot=((0, SAFE[1] + 250, SAFE[2], CONTENT[3] + 12),))
        if seg.kind == "hook":
            lay = self.hook_content(seg)
            k = 1 + 0.02 * math.sin(math.pi * K.clamp(lt / 0.5)) if (si == 0 and lt < 0.5) else 1.0
            K.put(img, lay, ox, oy, k=k, clip=CLIP)
        elif seg.kind == "step":
            self.draw_step(img, seg, lt, enter)
        else:
            self.draw_recap(img, seg, lt, t)
        # balon: kanca ve adımlarda; özete geçerken aşağı kayıp kaybolur (dış ses NEDEN? kutusuna geçer)
        if seg.kind != "recap":
            self.draw_bubble(img, seg, t)
        elif lt < 0.12 and si > 0:         # balon hızla kaybolur (yarı saydam koyu kutu bulanık görünür)
            p = lt / 0.12
            self.draw_bubble(img, self.segs[si - 1], seg.start - 0.01, dy=30 * p, alpha=1 - p)
        self.draw_mascot(img, t, si, lt)
        return K.finish(img) if grain else img.convert("RGB")


# ---------------------------------------------------------------- ana giriş
def render_nasil(scenes: list[render.SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
                 music: Path | None, meta: dict) -> Path:
    """Nasıl yapılır? şablonuyla videoyu kurar. Kare döngüsü, ses, kuyruk ve marka kapanışı kart şablonuyla ortak
    (kart.render_frames)."""
    return K.render_frames(scenes, words, out_mp4, voice_mp3, music,
                           lambda bcfg: NasilVideo(scenes, words, meta, bcfg), "Nasıl")
