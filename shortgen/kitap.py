"""Bir Kitap Bir Dakika şablonu ("Açılan kitap"): kütüphane rafının önünde kendi çizdiğimiz bez ciltli kitap açılır,
her bölüm bir sayfa çiftidir, bölüm değişince sayfa çevrilir, sonda kitap kapanır ve arka kapakta soru durur.

Telif kuralları (kodda da uygulanır):
  - Yayınevi kapağı, yayınevi çizimi ya da yayımlanmış çeviri kullanılmaz. Kapak kodla çizilir: başlık, yazar, kod
    çizimi amblem (AMBLEMLER, bilinmeyen anahtarda baş harf monogramı) ve kapak rengi (KAPAKLAR).
  - İlk cümle sayfası yalnız kamu malı eserde basılır: Türkiye'de (FSEK) koruma yazarın ölümünü izleyen yıldan başlayarak
    70 yıl sürer; Y yılında yazar en geç Y-71'de ölmüşse eser kamu malıdır (kamu_mali). Alıntı kendi kısa çevirimizdir.
    ilk_cumle boşsa ya da yazar bu sınırdan sonra öldüyse (ya da ölüm yılı bilinmiyorsa) ilk sayfa KÜNYE sayfasıdır.

Giriş: pipeline.build kurgu modüllerinin ortak girişini (render) çağırır; render sahnenin bütün alanlarını (kitap_bolum,
sayfa_metni, vurgu, mascot) ve meta['script']['kitap']'ı aşağıdaki sözleşmeye çevirip render_kitap'a verir.

Senaryo eşlemesi (veri sözleşmesi; alanlar getattr/dict ile okunur, demo JSON'u da çalışır):
  meta["kitap"]: baslik, yazar, yil, tur, ozgun_dil, yazar_olum, ilk_cumle, amblem, kapak_rengi
  spec.card: {"bolum": giris|konu|fikir|bilgi|soru, "sayfa": sağ sayfanın metni, "vurgu": sayfa metninin fosforlu
  kalemle işaretlenen parçası, "mascot": Makas'ın ifadesi}. Art arda aynı bölümdeki sahneler aynı sayfa çiftinde kalır;
  bölüm geri gidemez (geri giden sahne o anki bölümde kalır); ilk sahne her zaman giriş, son sahne soru (kitap kapanır).
  Hiç bölüm yazılmamışsa aradakiler sırayla konu / fikir / bilgi olur. Sekmeler videodaki bölümlerdir.
  Sağ sayfa metni dar yüzle (Oswald) 46-40 px, dengeli satırlarla yazılır (sütun 403 px: Türkçe uzun kelimelerle
  satırda 2-4 kelime); ilk cümle Playfair Display ile en az 40 px; küçük etiketler Courier, yırtık etiketler Anton.

Ekran düzeni (1080x1920). Yazı ve ana öğeler x <= 935 ve y 240-1540 içinde (y 120-228 filigranın yeri):
  kanca (kapak)  245-335 seri etiketi (BİR KİTAP + BİR DAKİKA, #04) · 360-650 kanca başlığı · altta kapalı kitabın ön
                 kapağı, sağda kütüphane kartı (künye), sağ altta kitap yığınının üstünde Makas
  sayfa çifti    245-410 yırtık manşet · 418-500 sekmeler (İLK CÜMLE / KONU / FİKİR / BİLGİ / SORU; bitenler kırmızı ✓,
                 o anki sarı) · 500-1270 açık kitap: sol sayfa tipografik (ilk cümle, künye, büyük yıl ya da sayı, öne
                 çıkan alıntı; sahnenin çizimi varsa çizim), sağ sayfada sayfa metni dış sesle daktilo gibi yazılır,
                 vurgu fosforlu kalemle çizilir · Makas sağ altta
  son            seri etiketi · kapalı kitabın arka kapağı: soru (soru bölümünün sayfa metni), OKUDUN MU? ve
                 Yorumlara yaz. söylendikleri anda belirir · kütüphane kartı (OKUNDU MU? damgası) · mutlu Makas
Zaman çizelgesi: t=0 kapak karesidir (tam görünür); markanın makas açılışı ve filigranı (brand.json) üstüne gelir.
Kanca cümlesinden sonra (ilk cümle okunacaksa ondan hemen önce) kanca katmanı makasla kesilir, kitap yerine kayar ve
kapak açılır. Bölüm değişince sayfa çevrilir; manşet ve sekmeler sayfa dik konumu geçince (90°) değişir, çevrilen sayfa
sekme sırasının üstüne hiç çıkmaz. Soru bölümünde kitap kapanır (sağ yarı sola kapanır, arka kapak üstte kalır) ve
ortaya gelir.

Hız: raf zemini, kitap gövdesi, sayfalar, kapaklar, sekmeler, manşetler ve Makas önbellekte; sağ sayfa yalnız yazılan
kelime sayısı ya da fosforlu kalem değişince yeniden çizilir. Kare başına katmanlar birleştirilir (≈ 0,1 sn/kare).
"""
from __future__ import annotations

import bisect
import datetime as dt
import itertools
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import kart as K
from . import render as R  # ortak sahne tipi (render adı bu modülün ortak girişidir)
from .voice import Word

W, H, FPS, SS = K.W, K.H, K.FPS, K.SS
RED, YELLOW, INK, PAPER, OFF, WHITE = K.RED, K.YELLOW, K.INK, K.PAPER, K.OFF, K.WHITE
GREY, DGREY = K.GREY, K.DGREY
blend, tw = K.blend, K.tw

# ---------------------------------------------------------------- seri sabitleri
SERI_ADI = "BİR KİTAP BİR DAKİKA"          # şablonda "seri_adi" yoksa (templates/kitap.json yazar)
YESIL = (30, 107, 82)                      # serinin tek ek rengi: kütüphane yeşili (kurdele, raf, amblem)
DUVAR = blend(YESIL, INK, 0.62)            # raf duvarı
SAYFA = (251, 248, 240)                    # kitap sayfası
SAYFA_KENAR = PAPER                        # sayfa yığınının kenarı
CIZGI = (214, 210, 200)                    # sayfa başlığının altındaki ince çizgi
MARKER = (252, 213, 33, 220)               # fosforlu kalem
GOVDE = "oswald"                           # sağ sayfa metni: dar yüz (yarım sayfa sütununa satırda 3-4 kelime sığar)
ALINTI = "PlayfairDisplay-Black.ttf"       # ilk cümle ve öne çıkan alıntı (kitap sayfası tadında)
SAFE = K.SAFE                              # (0, 170, 935, 1540)
CLIP = (0, SAFE[1], SAFE[2], SAFE[3])

BOLUMLER = ("giris", "konu", "fikir", "bilgi", "soru")
SEKMELER = {"giris": "İLK CÜMLE", "konu": "KONU", "fikir": "FİKİR", "bilgi": "BİLGİ", "soru": "SORU"}
KUNYE = "KÜNYE"                            # alıntısız (kamu malı olmayan) kitapta ilk sekme ve sayfa
BASLIKLAR = {"konu": "NE ANLATIYOR?", "fikir": "ANA FİKİR", "bilgi": "BİLİYOR MUYDUN?", "soru": "OKUDUN MU?"}
MANSET_RENK = {"giris": (OFF, RED), "konu": (OFF, INK), "fikir": (OFF, RED), "bilgi": (INK, YELLOW),
               "soru": (INK, YELLOW)}       # (yazı, kâğıt)
MOOD = {"giris": "surprised", "konu": "normal", "fikir": "thinking", "bilgi": "surprised", "soru": "happy"}
AMBLEMLER = ("kapi", "anahtar", "goz", "kalp", "gemi", "saat", "mektup", "tac", "kus", "agac", "dalga", "yildiz",
             "kilic", "maske", "ev", "ay")
# kapak rengi: zemin, başlık/yazar yazısı, vurgu (çerçeve, tür satırı), başlığın sert gölgesi
KAPAKLAR = {
    "kirmizi": dict(zemin=RED, yazi=OFF, vurgu=YELLOW, golge=INK),
    "sari": dict(zemin=YELLOW, yazi=INK, vurgu=RED, golge=OFF),
    "lacivert": dict(zemin=(36, 52, 104), yazi=OFF, vurgu=YELLOW, golge=INK),
    "yesil": dict(zemin=(26, 122, 88), yazi=OFF, vurgu=YELLOW, golge=INK),
    "siyah": dict(zemin=(36, 35, 34), yazi=OFF, vurgu=YELLOW, golge=RED),
}
CTA_RE = re.compile(r"\b(okudun\s+mu|yorumlara\s+yaz)\w*[.?!]*", re.I)

# ---------------------------------------------------------------- geometri
PW, PH = 447, 720                          # bir sayfa
GX = 467                                   # cilt sırtı
TOP = 500                                  # sayfaların üst kenarı
X_SOL, X_SAG = GX - PW, GX + PW            # 20, 914
BOARD = 12                                 # cildin sayfalardan taşan payı (sağda 926)
CUKUR = 12                                 # sırtta sayfaların çukurlaşması
STACK = 4                                  # sayfa yığınında bir yaprağın kalınlığı
BOT = TOP + PH
REGION = (0, 380, 940, 1420)               # kitap katmanlarının tuvali
TX0, TX1 = 26, PW - 18                     # sağ sayfa metin sütunu (sayfa koordinatı, 403 px)
TY0, TY1 = 112, PH - 66
MASKOT = (792, 1366, 0.54)                 # Makas gövde merkezi ve ölçeği (bütün karelerde aynı yer)
YIGIN_Y = MASKOT[1] + 132 * MASKOT[2]      # kitap yığınının üstü
MASCOT_VB = K.MASCOT_VB
# kanca (kapak) karesi
KANCA_Y0 = 368
KAPAK_K = 0.98                             # kapaktaki kapalı kitabın ölçeği
KART_KANCA = (590, 930)                    # kütüphane kartının x aralığı (kanca)
# son kare
SON_K = 1.12
SON_CX = 452
# süreler (sn)
ACILIS_GEC, ACILIS_KAY = 0.12, 0.40        # makas kancayı kesmeye başladıktan sonra kitap yerine kayar
ACILIS_ORT, ACILIS_DON = 0.44, 0.62        # kapak bu anda (açılışın başından) açılmaya başlar
CEVIR = 0.78                               # sayfa çevirme
KAPAN, SON_KAY = 0.78, 0.42                # kitap kapanır, ortaya kayar
YAZ_HIZ = 0.045                            # dış ses önden gittiyse sayfa kelimeleri bu aralıkla yazılır
KALEM = 0.38                               # fosforlu kalemin vurguyu çizmesi


def up(s: str) -> str:
    return K.tr_upper((s or "").strip())


def low(s: str) -> str:
    return K.tr_lower((s or "").strip())


def cap_h(font: str, size: float) -> float:
    return -K.tbox("H", font, size)[1]


def _al(obj, key: str, default=None):
    """Pydantic modeli ya da sözlükten alan okur (sözleşme alanı modelde yoksa da çalışır)."""
    if obj is None:
        return default
    v = obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    return default if v is None else v


def _int(v, default: int = 0) -> int:
    try:
        return int(str(v).strip()[:6])
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- telif: kamu malı denetimi
def kamu_mali(yazar_olum: int, yil: int | None = None) -> bool:
    """FSEK: koruma ölümü izleyen yıldan başlayarak 70 yıl; Y yılında ölüm yılı <= Y-71 ise eser kamu malıdır.
    Ölüm yılı 0 (yaşıyor ya da bilinmiyor) kamu malı sayılmaz."""
    yil = yil or dt.date.today().year
    return 0 < _int(yazar_olum) <= yil - 71


def kitap_bilgisi(meta: dict | None, yil: int | None = None) -> dict:
    """meta['kitap'] (KitapBilgi modeli ya da sözlük) -> düz sözlük. Kamu malı olmayan eserin ilk cümlesi silinir:
    o zaman ilk sayfa KÜNYE sayfasıdır."""
    meta = meta or {}
    raw = meta.get("kitap")
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    out = {
        "baslik": str(_al(raw, "baslik", "") or "").strip() or str(meta.get("topic") or "").strip() or "Kitap",
        "yazar": str(_al(raw, "yazar", "") or "").strip(),
        "yil": _int(_al(raw, "yil", 0)),
        "tur": str(_al(raw, "tur", "") or "").strip(),
        "ozgun_dil": str(_al(raw, "ozgun_dil", "") or "").strip(),
        "yazar_olum": _int(_al(raw, "yazar_olum", 0)),
        "ilk_cumle": " ".join(str(_al(raw, "ilk_cumle", "") or "").split()),
        "amblem": str(_al(raw, "amblem", "") or "").strip(),
        "kapak_rengi": str(_al(raw, "kapak_rengi", "") or "").strip(),
    }
    if not kamu_mali(out["yazar_olum"], yil):
        out["ilk_cumle"] = ""
    if out["kapak_rengi"] not in KAPAKLAR:
        out["kapak_rengi"] = "kirmizi"
    return out


def varyant(meta: dict | None) -> dict:
    """Şablon ayarı (meta['sablon'], templates/kitap.json): seri adı ve bölüm manşetleri; yoksa varsayılanlar."""
    cfg = (meta or {}).get("sablon")
    cfg = cfg if isinstance(cfg, dict) else {}
    seri = cfg.get("seri_adi")
    bas = dict(BASLIKLAR)
    if isinstance(cfg.get("basliklar"), dict):
        bas.update({k: up(v) for k, v in cfg["basliklar"].items() if k in BASLIKLAR and isinstance(v, str) and v.strip()})
    return {"seri_adi": up(seri) if isinstance(seri, str) and seri.strip() else SERI_ADI, "basliklar": bas}


# ---------------------------------------------------------------- senaryo -> bölümler
def bolum_isaretleri(specs) -> list[str]:
    """Her sahnenin bölümü (modül açıklamasındaki kurallar)."""
    n = len(specs)
    raw = []
    for s in specs:
        b = str(_al(s.card or {}, "bolum", "") or "").strip().lower()
        raw.append(b if b in BOLUMLER else "")
    if not any(raw):
        if n == 1:
            return ["giris"]
        mid = ["konu", "fikir", "bilgi"]
        k = n - 2
        orta = [mid[min(2, int(i * 3 / max(1, k)))] if k >= 3 else mid[[0, 2][i] if k == 2 else 0] for i in range(k)]
        return ["giris"] + orta + ["soru"]
    out, cur = [], 0
    for i, b in enumerate(raw):
        if i > 0 and b and BOLUMLER.index(b) > cur:   # ilk sahne her zaman giriştir (kapak ilk sayfaya açılır)
            cur = BOLUMLER.index(b)
        out.append(BOLUMLER[cur])
    if n >= 2 and "soru" not in out:
        out[-1] = "soru"           # kitap her zaman kapanır: son sahne sorudur
    return out


@dataclass
class Paragraf:
    metin: str
    vurgu: str
    sahne: int
    a: int                          # sahnenin dış ses kelime aralığı [a, b)
    b: int


@dataclass
class Bolum:
    ad: str
    sahneler: list[int]
    no: int = 0                     # sayfa çiftinin sırası (0: giriş)
    start: float = 0.0
    end: float = 0.0
    a: int = 0
    b: int = 0
    paragraflar: list[Paragraf] = field(default_factory=list)
    sprite: Path | None = None
    mascot: str = "auto"
    headline: list[str] = field(default_factory=list)
    hl: int = -1


def _kirp_metin(text: str, n: int = 24) -> str:
    """Sayfa metni boşsa dış sesten: en çok n kelime, cümle sonunda kesilir; yorum çağrısı alınmaz."""
    text = CTA_RE.sub("", text or "").strip()
    ws = text.split()
    if len(ws) <= n:
        return " ".join(ws)
    out = []
    for w in ws:
        out.append(w)
        if len(out) >= n:
            break
    cut = max((i for i, w in enumerate(out) if w[-1:] in ".?!"), default=len(out) - 1)
    return " ".join(out[:cut + 1])


def plan(specs, words: list[Word]) -> list[Bolum]:
    marks = bolum_isaretleri(specs)
    n = len(specs)
    ranges, a = [], 0
    for i, s in enumerate(specs):
        b = min(len(words), a + len(s.words)) if i < n - 1 else len(words)
        ranges.append((a, b))
        a = b
    out: list[Bolum] = []
    for i, (s, m) in enumerate(zip(specs, marks)):
        if not out or out[-1].ad != m:
            out.append(Bolum(m, [], no=len(out)))
        bl = out[-1]
        bl.sahneler.append(i)
        c = s.card or {}
        metin = " ".join(str(_al(c, "sayfa", "") or "").split())
        if metin:
            bl.paragraflar.append(Paragraf(metin, " ".join(str(_al(c, "vurgu", "") or "").split()), i, *ranges[i]))
        if bl.sprite is None and s.sprite is not None:
            bl.sprite = s.sprite
        if len(bl.sahneler) == 1:
            bl.mascot = str(_al(c, "mascot", "auto") or "auto")
            bl.headline = [up(x) for x in (s.headline or []) if x and x.strip()]
            bl.hl = s.highlight_line if 0 <= s.highlight_line < len(bl.headline) else -1
    for bl in out:
        s0, s1 = specs[bl.sahneler[0]], specs[bl.sahneler[-1]]
        bl.start, bl.end = s0.start, s1.end
        bl.a, bl.b = ranges[bl.sahneler[0]][0], ranges[bl.sahneler[-1]][1]
        if not bl.paragraflar and bl.ad != "soru":   # sayfa metni yoksa dış sesten kısa bir parça
            nar = " ".join(specs[i].narration for i in bl.sahneler)
            if _kirp_metin(nar):
                bl.paragraflar.append(Paragraf(_kirp_metin(nar), "", bl.sahneler[0], bl.a, bl.b))
    return out


# ---------------------------------------------------------------- sayfa metni: dengeli sarma ve zamanlama
def _norm(w: str) -> str:
    return re.sub(r"[^\wçğıöşü]", "", low(w).replace("'", "").replace("’", ""))


def dengeli(widths: list[float], sp: float, M: float) -> list[tuple[int, int]]:
    """Satır sayısını artırmadan en dengeli sarma (tek kelimelik satır yok; gerekirse bir satır fazla). Satırlar
    (i, j) kelime aralıkları."""
    n = len(widths)
    if not n:
        return []

    def lw(i, j):
        return sum(widths[i:j]) + sp * (j - i - 1)

    greedy, i = 0, 0
    while i < n:
        j = i + 1
        while j < n and lw(i, j + 1) <= M:
            j += 1
        greedy += 1
        i = j
    best = None
    for L in (greedy, greedy + 1):
        if L > n:
            continue
        INF = float("inf")
        dp = [[INF] * (n + 1) for _ in range(L + 1)]
        bk = [[-1] * (n + 1) for _ in range(L + 1)]
        dp[0][0] = 0.0
        for k in range(1, L + 1):
            for j in range(1, n + 1):
                for i in range(j - 1, -1, -1):
                    w = lw(i, j)
                    if w > M and j - i > 1:
                        break
                    if dp[k - 1][i] == INF:
                        continue
                    c = ((M - min(w, M)) / M) ** 2 * 100
                    if j - i == 1 and n >= 3 and not (w > M * 0.62):
                        c += 1000              # tek kelimelik satır (kelime tek başına uzun değilse)
                    if dp[k - 1][i] + c < dp[k][j]:
                        dp[k][j], bk[k][j] = dp[k - 1][i] + c, i
        if dp[L][n] == INF:
            continue
        cost = dp[L][n] + (L - greedy) * 400
        if best is None or cost < best[0]:
            lines, j = [], n
            for k in range(L, 0, -1):
                i = bk[k][j]
                lines.append((i, j))
                j = i
            best = (cost, lines[::-1])
    return best[1] if best else [(0, n)]


@dataclass
class Jeton:
    text: str
    para: int
    line: int
    x: float
    w: float
    grup: int = 0                   # sayfa grubu (bölümün metni tek sayfaya sığmazsa sahne sahne gruplanır)
    t: float = 0.0                  # sayfada belirdiği an
    hl: list = field(default_factory=list)   # fosforlu kalemin x aralıkları [(x0, x1)]


class SayfaMetni:
    """Sağ sayfanın metni: paragraflar (bölümün sahneleri), sütuna sığan en büyük boyut (46-40 px; tek kelimelik satır
    bırakmayan ilk boyut), dengeli satırlar, kelimelerin dış sese göre belirme anları ve vurgunun fosforlu kalem
    aralıkları. Paragraflar 40 px'te de sayfaya sığmazsa gruplara bölünür: yeni grubun ilk kelimesi yazılınca sayfa
    temizlenir ve grup baştan yazılır (yazı hiçbir zaman küçülmez ya da sayfadan taşmaz)."""
    SIZES = (46, 44, 42, 40)
    LH = 1.2

    def __init__(self, paras: list[Paragraf], words: list[Word], reveal: float, width: float = TX1 - TX0,
                 height: float = TY1 - TY0, font: str = GOVDE):
        self.font, self.width, self.height = font, width, height
        self.paras = paras
        self.size, self.lines, self.gruplar = self._fit()
        self.lh = self.size * self.LH
        self.jetonlar: list[Jeton] = []
        self._layout()
        self._timing(words, reveal)
        self.hl_t = self._hl_times()

    def _wrap(self, text: str, size: float) -> list[list[str]]:
        toks = text.split()
        ws = [tw(t, self.font, size) for t in toks]
        return [toks[i:j] for i, j in dengeli(ws, tw(" ", self.font, size), self.width)]

    def _fit(self):
        adaylar = []
        for size in self.SIZES:
            lines = [self._wrap(p.metin, size) for p in self.paras]
            nl = sum(len(x) for x in lines)
            h = nl * size * self.LH + max(0, len(lines) - 1) * size * 0.5
            tek = [L for p in lines for L in p if len(L) == 1 and len(p) > 1]
            kisa_tek = sum(1 for L in tek if tw(L[0], self.font, size) < self.width * 0.62)
            wide = all(tw(" ".join(L), self.font, size) <= self.width + 0.5 for p in lines for L in p)
            if h <= self.height and wide:
                adaylar.append(((kisa_tek, len(tek), -size), size, lines))
        if adaylar:     # önce kısa tek kelimelik satır, sonra her tek kelimelik satır en az; eşitse en büyük boyut
            _, size, lines = min(adaylar, key=lambda a: a[0])
            return size, lines, [list(range(len(self.paras)))]
        # sığmıyor: en küçük boyutta paragraflar sırayla gruplara; tek başına sığmayan paragrafın fazla satırı atılır
        size = self.SIZES[-1]
        lh = size * self.LH
        maxl = max(1, int(self.height // lh))
        lines = [self._wrap(p.metin, size)[:maxl] for p in self.paras]
        gruplar, cur, h = [], [], 0.0
        for pi, L in enumerate(lines):
            ph = len(L) * lh + (size * 0.5 if cur else 0)
            if cur and h + ph > self.height:
                gruplar.append(cur)
                cur, h, ph = [], 0.0, len(L) * lh
            cur.append(pi)
            h += ph
        gruplar.append(cur)
        return size, lines, gruplar

    def _layout(self):
        sp = tw(" ", self.font, self.size)
        grup_of = {pi: g for g, ps in enumerate(self.gruplar) for pi in ps}
        li, self.n_lines = 0, 0
        for pi, (p, lines) in enumerate(zip(self.paras, self.lines)):
            if pi and grup_of[pi] != grup_of[pi - 1]:
                li = 0                                      # yeni grup: sayfanın başından
            vs = low(p.metin).find(low(p.vurgu)) if p.vurgu else -1
            ve = vs + len(p.vurgu) if vs >= 0 else -1
            pos = 0
            for L in lines:
                x = 0.0
                for tok in L:
                    k = p.metin.find(tok, pos)
                    k = pos if k < 0 else k
                    pos = k + len(tok)
                    w = tw(tok, self.font, self.size)
                    j = Jeton(tok, pi, li, x, w, grup_of[pi])
                    if vs >= 0 and k < ve and k + len(tok) > vs:    # vurgu bu kelimeyle kesişiyor
                        a0, a1 = max(0, vs - k), min(len(tok), ve - k)
                        tail = tok[a0:a1].rstrip(".,;:!?…\"”’)") if a1 == len(tok) else tok[a0:a1]
                        j.hl.append((x + tw(tok[:a0], self.font, self.size),
                                     x + tw(tok[:a0] + tail, self.font, self.size)))
                    self.jetonlar.append(j)
                    x += w + sp
                li += 1
            self.n_lines = max(self.n_lines, li)
            li += 0.5                                       # paragraf arası yarım satır

    def _timing(self, words: list[Word], reveal: float):
        """Kelimeler dış sesteki karşılıklarıyla belirir (eşleşmeyenler araya oranla); sayfa açılmadan söylenenler
        açılışta hızla yazılır. Paragrafın son kelimesi sahnesinin son sözünde yazılmış olur."""
        for pi, p in enumerate(self.paras):
            js = [j for j in self.jetonlar if j.para == pi]
            nar = list(range(p.a, min(p.b, len(words))))
            times: list[float | None] = [None] * len(js)
            ptr = 0
            for k, j in enumerate(js):
                nj = _norm(j.text)
                if not nj:
                    continue
                for q in range(ptr, min(len(nar), ptr + 8)):
                    nw = _norm(words[nar[q]].text)
                    if nw and (nw == nj or (len(nj) >= 4 and len(nw) >= 4 and (nw.startswith(nj[:4])
                                                                                 and nj.startswith(nw[:4])))):
                        times[k] = words[nar[q]].start
                        ptr = q + 1
                        break
            if nar:
                t0, t1 = words[nar[0]].start, words[nar[-1]].start
            else:
                t0 = t1 = reveal
            known = [(k, tt) for k, tt in enumerate(times) if tt is not None]
            for k in range(len(js)):
                if times[k] is not None:
                    continue
                prev = max(((kk, tt) for kk, tt in known if kk < k), default=None, key=lambda x: x[0])
                nxt = min(((kk, tt) for kk, tt in known if kk > k), default=None, key=lambda x: x[0])
                if prev and nxt:
                    times[k] = prev[1] + (nxt[1] - prev[1]) * (k - prev[0]) / (nxt[0] - prev[0])
                elif prev:
                    times[k] = prev[1] + (t1 - prev[1]) * (k - prev[0]) / max(1, len(js) - 1 - prev[0])
                elif nxt:
                    times[k] = t0 + (nxt[1] - t0) * k / max(1, nxt[0])
                else:
                    times[k] = t0 + (t1 - t0) * k / max(1, len(js) - 1)
            last = -1e9
            for k, j in enumerate(js):
                tt = max(float(times[k]), reveal + YAZ_HIZ * k if times[k] < reveal else float(times[k]))
                tt = max(tt, last + 0.02)
                j.t = tt
                last = tt

    def _hl_times(self) -> dict:
        """Paragraf başına fosforlu kalemin başladığı an: vurgunun son kelimesi belirdikten hemen sonra."""
        out = {}
        for pi in range(len(self.paras)):
            ts = [j.t for j in self.jetonlar if j.para == pi and j.hl]
            if ts:
                out[pi] = max(ts) + 0.08
        return out

    def durum(self, t: float) -> tuple[int, tuple, int]:
        """(yazılmış kelime sayısı, paragraf başına fosforlu kalem adımı 0-8, görünen grup): sayfa görüntüsünün
        önbellek anahtarı."""
        n = bisect.bisect_right([j.t for j in self.jetonlar], t)
        steps = []
        for pi, t0 in sorted(self.hl_t.items()):
            steps.append(max(0, min(8, int((t - t0) / KALEM * 8) + 1)) if t >= t0 else 0)
        return n, tuple(steps), (self.jetonlar[n - 1].grup if n else 0)

    def ciz(self, pen: K.Pen, x0: float, y0: float, n: int, steps: tuple, grup: int = 0, renk=INK) -> None:
        cap = cap_h(self.font, self.size)
        rng = random.Random(7)
        # 1) fosforlu kalem (yazının altında); satır satır, adım adım soldan sağa
        for (pi, _), st in zip(sorted(self.hl_t.items()), steps):
            if not st or pi not in self.gruplar[grup]:
                continue
            runs: dict = {}
            for j in self.jetonlar:
                if j.para == pi and j.hl:
                    for a, b in j.hl:
                        r = runs.setdefault(j.line, [a, b])
                        r[0], r[1] = min(r[0], a), max(r[1], b)
            total = sum(b - a for a, b in runs.values())
            left = total * st / 8
            for line in sorted(runs):
                a, b = runs[line]
                if left <= 0:
                    break
                bb = min(b, a + left)
                left -= b - a
                base = y0 + cap + line * self.lh
                xa, xb = x0 + a - self.size * 0.12, x0 + bb + self.size * 0.12
                top, bot = base - cap - self.size * 0.14, base + self.size * 0.16
                jj = lambda: rng.uniform(-2.0, 2.0)  # noqa: E731
                pen.poly([(xa + jj(), top + jj()), (xb + jj(), top - 2 + jj()), (xb + jj(), bot + jj()),
                          (xa + jj(), bot + 2 + jj())], MARKER)
        # 2) yazı
        for j in self.jetonlar[:n]:
            if j.grup != grup:
                continue
            pen.text(x0 + j.x, y0 + cap + j.line * self.lh, j.text, self.font, self.size, renk)

    def imlec(self, n: int) -> tuple[float, float, float] | None:
        """Daktilo imlecinin yeri (x, taban, boy) sayfa metni koordinatında: son yazılan kelimenin sağı."""
        if not self.jetonlar or n >= len(self.jetonlar):
            return None
        if n == 0:
            j = self.jetonlar[0]
            return j.x, cap_h(self.font, self.size) + j.line * self.lh, self.size
        j = self.jetonlar[n - 1]
        return j.x + j.w + 6, cap_h(self.font, self.size) + j.line * self.lh, self.size

    def kutu(self) -> tuple[float, float, float, float]:
        """Metnin sayfa metni koordinatındaki kutusu."""
        if not self.jetonlar:
            return (0, 0, 0, 0)
        x1 = max(j.x + j.w for j in self.jetonlar)
        return (0, 0, x1, self.n_lines * self.lh)


# ---------------------------------------------------------------- küçük yardımcılar
_cache: dict = {}


def etiket(text: str, size: float, fg, bg, seed: int, rot: float = 0.0, font: str = "anton",
           shadow=(6, 8, 0, 0.9)) -> tuple[Image.Image, float, float]:
    """Yırtık kâğıt etiket (1x RGBA, önbellekli) ve etiketin kendi genişliği/yüksekliği."""
    key = ("etiket", text, round(size, 1), fg, bg, seed, round(rot, 2), font, shadow)
    if key not in _cache:
        lab = K.torn_label(text, size, fg, bg, seed, font=font)
        _cache[key] = (lab.render(rot, shadow), lab.w, lab.h)
    return _cache[key]


def etiket_gen(text: str, size: float, font: str = "anton") -> float:
    return tw(text, font, size) + 0.4 * size


def etiket_boy(text: str, size: float, font: str = "anton") -> float:
    """Yırtık etiketin yüksekliği (çizmeden: mürekkep kutusu + iç pay, torn_label ile aynı hesap)."""
    fS = K.fnt(font, size)
    t, b = fS.getbbox(text, anchor="ls")[1], fS.getbbox(text, anchor="ls")[3]
    return max(cap_h(font, size), -t) + max(0.0, b) + 2 * size * 0.16


def svg_im(body: str, vb, w: float) -> Image.Image:
    h = w * vb[3] / vb[2]
    im = K.svg_img(body, vb, w * SS, h * SS)
    return im.resize((max(1, round(w)), max(1, round(h))), Image.LANCZOS)


def ortala(base: Image.Image, im: Image.Image, cx: float, cy: float, clip=None) -> tuple:
    x, y = cx - im.width / 2, cy - im.height / 2
    if clip:
        K.put(base, im, x, y, clip=clip)
    else:
        K._comp(base, im, x, y)
    return (round(x), round(y), round(x) + im.width, round(y) + im.height)


def alfa(im: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return im


def _ease(x: float) -> float:
    return K.ease_in_out(K.clamp(x))


# ---------------------------------------------------------------- zemin: geri itilmiş kütüphane rafı
def raf_zemini() -> Image.Image:
    """Koyu yeşil duvar önünde sessiz kitap sırtları: kırmızı sırt ve beyaz etiket yok, kontrast %40 düşük,
    hafif bulanık ve koyu (kahraman kitap ve etiketler öne çıksın). Makas'ın kitap yığını da zemine çizilir."""
    if "raf" in _cache:
        return _cache["raf"]
    S = 2
    im = Image.new("RGBA", (W * S, H * S), DUVAR + (255,))
    d = ImageDraw.Draw(im)
    rng = random.Random(1915)
    renkler = [blend(YESIL, INK, 0.25), blend(YESIL, INK, 0.5), (92, 86, 52), (58, 66, 60), INK,
               blend(YESIL, OFF, 0.12), (70, 92, 84), (104, 96, 60)]
    for ry in (300, 700, 1100, 1500, 1900):
        x = -20
        while x < W + 20:
            if rng.random() < 0.06:
                x += rng.randint(50, 90)
                continue
            bw, bh = rng.randint(34, 74), rng.randint(230, 330)
            col = rng.choice(renkler)
            lean = rng.random() < 0.08
            pts = [(x, ry), (x + bw, ry), (x + bw, ry - bh), (x, ry - bh)]
            if lean:
                a = math.radians(rng.choice([-9, 9]))
                c0 = x if a > 0 else x + bw
                pts = [(c0 + (px - c0) * math.cos(a) - (py - ry) * math.sin(a),
                        ry + (px - c0) * math.sin(a) + (py - ry) * math.cos(a)) for px, py in pts]
            d.polygon([(px * S, py * S) for px, py in pts], fill=col, outline=INK, width=4 * S)
            if not lean:
                band = blend(col, (150, 140, 90), 0.45)
                for yy in (ry - bh + 22, ry - 34):
                    d.rectangle([(x + 6) * S, yy * S, (x + bw - 6) * S, (yy + 5) * S], fill=band)
            x += bw + (0 if rng.random() < 0.7 else rng.randint(2, 8))
        d.rectangle([-10 * S, ry * S, (W + 10) * S, (ry + 30) * S], fill=INK)
        d.rectangle([-10 * S, (ry + 4) * S, (W + 10) * S, (ry + 9) * S], fill=blend(YESIL, INK, 0.3))
    im = im.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2.2))
    arr = np.asarray(im, dtype=np.float32)[..., :3]
    duvar = np.array(DUVAR, np.float32)
    arr = duvar + (arr - duvar) * 0.6                     # kontrast %40 düşük
    g = arr.mean(axis=2, keepdims=True)
    arr = g + (arr - g) * 0.7                             # doygunluk düşük
    arr *= 0.86                                           # koyu
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W * 0.45) / (W * 0.75)) ** 2 + ((yy - H * 0.47) / (H * 0.62)) ** 2)
    arr *= (1 - np.clip((r - 0.62) * 0.6, 0, 0.34))[..., None]
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    out.alpha_composite(kitap_yigini(), (0, 0))
    _cache["raf"] = out
    return out


def kitap_yigini() -> Image.Image:
    """Makas'ın oturduğu üç kitaplık yığın (tam kare boyutunda katman)."""
    cx = MASKOT[0]
    pen = K.Pen(0, 0, W, H)
    y = YIGIN_Y
    for i, (c, bw, band) in enumerate([(INK, 214, YELLOW), (YELLOW, 196, INK), (YESIL, 206, OFF)]):
        bh = 30
        x0 = cx - bw / 2 + (i - 1) * 8
        pen.rr((x0 + 6, y + 7, x0 + bw + 6, y + bh + 7), 5, fill=INK)
        pen.rr((x0, y, x0 + bw, y + bh), 5, fill=c, outline=INK, width=4)
        pen.rr((x0 + bw - 26, y + 5, x0 + bw - 6, y + bh - 5), 2, fill=SAYFA, outline=INK, width=2)
        pen.rr((x0 + 16, y + bh / 2 - 3, x0 + 70, y + bh / 2 + 3), 2, fill=band)
        y += bh
    return pen.done()


# ---------------------------------------------------------------- amblemler (kalın mürekkep, marka renkleri)
def _st(fill, sw=8, extra=""):
    return (f'fill="{K._hex(fill) if fill else "none"}" stroke="{K._hex(INK)}" stroke-width="{sw}" '
            f'stroke-linejoin="round" stroke-linecap="round" {extra}')


def _ln(pts, sw=8, col=INK):
    d = " ".join(("M" if i == 0 else "L") + f"{x:.1f} {y:.1f}" for i, (x, y) in enumerate(pts))
    return f'<path d="{d}" fill="none" stroke="{K._hex(col)}" stroke-width="{sw}" stroke-linecap="round" ' \
           'stroke-linejoin="round"/>'


AMBLEM_VB = (0, 0, 300, 300)


def amblem_svg(key: str) -> str | None:
    """Kapak amblemi (viewBox 0 0 300 300): kırık beyaz rozet + basit kalın çizim (rozetin içine kırpılır).
    Bilinmeyen anahtar None."""
    s = ""
    if key == "kapi":            # karanlık odaya aralanmış kapı
        s += f'<path d="M112 236 L216 236 L262 270 L150 270 Z" fill="{K._hex(YELLOW)}"/>'
        s += _ln([(40, 236), (260, 236)], 8)
        s += f'<rect x="112" y="62" width="104" height="174" {_st(INK)}/>'
        s += f'<path d="M112 62 L70 44 L70 256 L112 236 Z" {_st(OFF)}/>'
        s += f'<circle cx="84" cy="152" r="8" {_st(YELLOW, 5)}/>'
    elif key == "anahtar":
        s += f'<circle cx="96" cy="150" r="48" {_st(YELLOW)}/><circle cx="96" cy="150" r="18" {_st(OFF, 7)}/>'
        s += f'<rect x="140" y="138" width="124" height="24" rx="6" {_st(YELLOW)}/>'
        s += f'<rect x="206" y="160" width="20" height="38" {_st(YELLOW, 7)}/>'
        s += f'<rect x="238" y="160" width="20" height="28" {_st(YELLOW, 7)}/>'
    elif key == "goz":
        s += f'<path d="M36 150 Q150 46 264 150 Q150 254 36 150 Z" {_st(OFF)}/>'
        s += f'<circle cx="150" cy="150" r="52" {_st(RED)}/><circle cx="150" cy="150" r="22" {_st(INK, 6)}/>'
        s += f'<circle cx="166" cy="134" r="9" fill="{K._hex(OFF)}"/>'
        for a, b in (((86, 104), (72, 80)), ((150, 86), (150, 58)), ((214, 104), (228, 80))):
            s += _ln([a, b], 8)
    elif key == "kalp":
        s += (f'<path d="M150 250 C60 188 38 132 70 96 C100 64 140 78 150 112 C160 78 200 64 230 96 C262 132 240 188 '
              f'150 250 Z" {_st(RED)}/>')
        s += f'<path d="M90 122 Q96 102 114 98" fill="none" stroke="{K._hex(OFF)}" stroke-width="9" ' \
             'stroke-linecap="round"/>'
    elif key == "gemi":
        s += (f'<path d="M36 236 Q66 220 96 236 T156 236 T216 236 T276 236" fill="none" stroke="{K._hex(INK)}" '
              'stroke-width="8" stroke-linecap="round"/>')
        s += f'<path d="M58 192 L242 192 L214 230 L88 230 Z" {_st(RED)}/>'
        s += _ln([(150, 192), (150, 52)], 8)
        s += f'<path d="M158 64 L158 178 L236 178 Z" {_st(OFF, 7)}/>'
        s += f'<path d="M142 84 L142 178 L84 178 Z" {_st(YELLOW, 7)}/>'
        s += f'<path d="M150 52 L182 62 L150 74 Z" {_st(RED, 6)}/>'
    elif key == "saat":
        s += f'<circle cx="150" cy="150" r="98" {_st(YELLOW)}/>'
        for k in range(12):
            a = math.radians(k * 30)
            r0 = 74 if k % 3 else 64
            s += _ln([(150 + r0 * math.sin(a), 150 - r0 * math.cos(a)), (150 + 86 * math.sin(a), 150 - 86 * math.cos(a))],
                     8 if k % 3 == 0 else 5)
        s += _ln([(150, 150), (150, 92)], 11) + _ln([(150, 150), (198, 168)], 9)
        s += f'<circle cx="150" cy="150" r="11" {_st(RED, 5)}/>'
    elif key == "mektup":
        s += f'<rect x="50" y="90" width="200" height="132" rx="8" {_st(YELLOW)}/>'
        s += _ln([(50, 96), (150, 168), (250, 96)], 8) + _ln([(56, 216), (124, 158)], 6) + _ln([(244, 216), (176, 158)], 6)
        s += f'<circle cx="150" cy="170" r="24" {_st(RED, 7)}/>'
    elif key == "tac":
        s += f'<path d="M64 204 L52 100 L106 146 L150 72 L194 146 L248 100 L236 204 Z" {_st(YELLOW)}/>'
        s += f'<rect x="60" y="200" width="180" height="36" rx="5" {_st(RED)}/>'
        for x, y in ((52, 100), (150, 72), (248, 100)):
            s += f'<circle cx="{x}" cy="{y}" r="13" {_st(RED, 6)}/>'
        for x in (100, 150, 200):
            s += f'<circle cx="{x}" cy="218" r="8" fill="{K._hex(OFF)}"/>'
    elif key == "kus":
        s += f'<path d="M66 172 L28 146 L38 194 Z" {_st(INK, 7)}/>'
        s += f'<ellipse cx="138" cy="172" rx="80" ry="52" {_st(RED)}/>'
        s += f'<circle cx="208" cy="124" r="38" {_st(RED)}/>'
        s += f'<path d="M240 114 L278 128 L240 140 Z" {_st(YELLOW, 6)}/>'
        s += f'<circle cx="216" cy="116" r="8" fill="{K._hex(INK)}"/>'
        s += f'<path d="M96 166 Q138 118 184 160 Q138 192 96 166 Z" {_st(OFF, 7)}/>'
        s += _ln([(120, 222), (112, 250)], 7) + _ln([(156, 222), (160, 250)], 7)
    elif key == "agac":
        s += _ln([(56, 252), (244, 252)], 8)
        s += f'<path d="M134 252 L138 170 L162 170 L166 252 Z" {_st(INK, 6)}/>'
        s += f'<circle cx="102" cy="150" r="48" {_st(YESIL)}/><circle cx="198" cy="150" r="48" {_st(YESIL)}/>'
        s += f'<circle cx="150" cy="108" r="64" {_st(YESIL)}/>'
        for x, y in ((118, 96), (176, 128), (96, 160), (204, 166), (150, 150)):
            s += f'<circle cx="{x}" cy="{y}" r="10" {_st(RED, 5)}/>'
    elif key == "dalga":
        s += f'<circle cx="150" cy="92" r="36" {_st(YELLOW, 8)}/>'            # güneş, önünde dalgalı deniz
        s += f'<path d="M-10 168 Q28 128 66 168 T142 168 T218 168 T294 168 T370 168 L370 320 L-10 320 Z" {_st(INK, 8)}/>'
        for y, dx in ((214, 0), (258, 34)):
            s += (f'<path d="M{-20 + dx} {y} Q{12 + dx} {y - 22} {44 + dx} {y} T{108 + dx} {y} T{172 + dx} {y} '
                  f'T{236 + dx} {y} T{300 + dx} {y}" fill="none" stroke="{K._hex(OFF)}" stroke-width="9" '
                  'stroke-linecap="round"/>')
        s += f'<path d="M110 150 L132 150 L128 160 L114 160 Z" {_st(RED, 5)}/>'      # uzakta küçük kayık
    elif key == "yildiz":
        pts = []
        for k in range(10):
            r = 112 if k % 2 == 0 else 46
            a = math.radians(-90 + k * 36)
            pts.append((150 + r * math.cos(a), 156 + r * math.sin(a)))
        s += f'<path d="M{" L".join(f"{x:.1f} {y:.1f}" for x, y in pts)} Z" {_st(YELLOW)}/>'
        for x, y, r in ((62, 76, 12), (240, 238, 10)):
            s += f'<circle cx="{x}" cy="{y}" r="{r}" {_st(RED, 5)}/>'
    elif key == "kilic":
        g = '<g transform="rotate(45 150 150)">'
        g += f'<path d="M138 214 L138 64 L150 30 L162 64 L162 214 Z" {_st(OFF)}/>'
        g += _ln([(150, 60), (150, 200)], 4, GREY)
        g += f'<rect x="96" y="210" width="108" height="22" rx="8" {_st(YELLOW)}/>'
        g += f'<rect x="138" y="230" width="24" height="44" rx="6" {_st(INK, 6)}/>'
        g += f'<circle cx="150" cy="280" r="14" {_st(RED, 6)}/></g>'
        s += g
    elif key == "maske":
        s += f'<path d="M66 78 Q150 48 234 78 L226 168 Q208 248 150 256 Q92 248 74 168 Z" {_st(YELLOW)}/>'
        s += f'<path d="M92 128 Q116 104 140 128 Q116 142 92 128 Z" {_st(INK, 6)}/>'
        s += f'<path d="M160 128 Q184 104 208 128 Q184 142 160 128 Z" {_st(INK, 6)}/>'
        s += f'<path d="M104 180 Q150 226 196 180 Q150 200 104 180 Z" {_st(RED, 7)}/>'
    elif key == "ev":
        s += _ln([(48, 246), (252, 246)], 8)
        s += f'<rect x="186" y="80" width="26" height="54" {_st(RED, 7)}/>'
        s += f'<rect x="80" y="140" width="140" height="106" {_st(YELLOW)}/>'
        s += f'<path d="M60 150 L150 68 L240 150 Z" {_st(RED)}/>'
        s += f'<rect x="132" y="186" width="38" height="60" {_st(INK, 6)}/>'
        s += f'<rect x="92" y="164" width="30" height="30" {_st(OFF, 6)}/>'
        s += _ln([(107, 164), (107, 194)], 4) + _ln([(92, 179), (122, 179)], 4)
    elif key == "ay":
        s += f'<path d="M188 58 A100 100 0 1 0 226 226 A80 80 0 1 1 188 58 Z" {_st(YELLOW)}/>'
        for x, y, r in ((214, 110, 13), (236, 168, 9), (196, 196, 7)):
            s += f'<circle cx="{x}" cy="{y}" r="{r}" {_st(RED, 5)}/>'
    else:
        return None
    return (f'<defs><clipPath id="amb"><circle cx="150" cy="150" r="134"/></clipPath></defs>'
            f'<circle cx="150" cy="150" r="138" fill="{K._hex(OFF)}"/><g clip-path="url(#amb)">{s}</g>'
            f'<circle cx="150" cy="150" r="138" fill="none" stroke="{K._hex(INK)}" stroke-width="9"/>')


def amblem_img(key: str, size: float, baslik: str = "") -> Image.Image:
    """Amblem görüntüsü (size x size, 1x). Bilinmeyen anahtar: başlığın baş harf(ler)i monogramı."""
    ck = ("amblem", key, round(size), baslik)
    if ck in _cache:
        return _cache[ck]
    body = amblem_svg(key)
    if body is not None:
        im = svg_im(body, AMBLEM_VB, size)
    else:
        pen = K.Pen(0, 0, 300, 300, ss=max(1, round(SS * size / 300 + 0.5)))
        pen.ell(150, 150, 138, fill=OFF, outline=INK, width=9)
        pen.ell(150, 150, 112, outline=RED, width=5)
        harf = "".join(w[0] for w in up(baslik).split()[:2] if w[:1].isalnum()) or "?"
        fs = 170 if len(harf) == 1 else 128
        pen.text(150, 150 + cap_h("anton", fs) / 2, harf, "anton", fs, INK, anchor="ms")
        im = pen.im.resize((max(1, round(size)), max(1, round(size))), Image.LANCZOS)
    _cache[ck] = im
    return im


# ---------------------------------------------------------------- kapaklar
def _yazi_sigdir(text: str, font: str, width: float, mx: int, mn: int) -> int:
    size = mx
    while size > mn and tw(text, font, size) > width:
        size -= 1
    return size


def _baslik_satirlari(baslik: str, width: float, mx: int = 150, mn: int = 64) -> tuple[int, list[str]]:
    """Kapak başlığı: tek satıra sığmazsa 2-4 dengeli satır; az satır ve büyük boyut tercih edilir. mn altına ancak
    hiçbir bölünme sığmazsa inilir (başlık kısaltılmaz; tek kelime sütundan genişse o kelime kısalır)."""
    words = up(baslik).split() or ["?"]
    if len(words) > 20:                                 # akla yatmayacak kadar uzun başlık: sonu üç nokta
        words = words[:20]
        words[-1] += "…"
    best, yedek = None, None
    for n in range(1, min(4, len(words)) + 1):
        for cuts in itertools.combinations(range(1, len(words)), n - 1):
            sinir = (0,) + cuts + (len(words),)
            c = [" ".join(words[a:b]) for a, b in zip(sinir, sinir[1:])]
            w100 = max(tw(x, "anton", 100) for x in c)
            size = min(mx, int(width * 100 / w100))
            while size > 20 and max(tw(x, "anton", size) for x in c) > width:
                size -= 1
            score = size * (1.0, 0.86, 0.74, 0.64)[n - 1]
            if size >= mn and (best is None or score > best[0]):
                best = (score, size, c)
            if yedek is None or size > yedek[1]:
                yedek = (score, size, c)
        if best and n == 1:
            break
    if best is None:
        size = max(28, yedek[1])
        return size, [K.fit(x, "anton", size, width) for x in yedek[2]]
    return best[1], best[2]


def kapak_on(kb: dict, seri: str, k: float = 1.0) -> Image.Image:
    """Ön kapak (PW x PH x k): bez cilt rengi, sırt şeridi, çerçeve, yazar, başlık, tür · yıl, amblem, makas + seri adı.
    Kenarında çizgi yok: cildin üstüne biner, kapak açılırken dönen yaprak da budur."""
    key = ("on", tuple(sorted(kb.items())), seri, round(k, 3))
    if key in _cache:
        return _cache[key]
    c = KAPAKLAR[kb["kapak_rengi"]]
    pen = K.Pen(0, 0, PW, PH, ss=3)
    pen.rr((0, 0, PW, PH), 0, fill=c["zemin"])
    sirt = 36
    pen.rr((0, 0, sirt, PH), 0, fill=blend(c["zemin"], INK, 0.22))
    pen.line([(sirt, 0), (sirt, PH)], blend(c["zemin"], INK, 0.5), 4)
    pen.line([(sirt + 7, 0), (sirt + 7, PH)], blend(c["zemin"], OFF, 0.3), 2)
    m = 24
    pen.rr((sirt + m - 6, m, PW - m, PH - m), 6, outline=c["vurgu"], width=3)
    cx = (sirt + PW) / 2
    inner = PW - sirt - 2 * m - 30
    y = 98
    if kb["yazar"]:
        fs = _yazi_sigdir(up(kb["yazar"]), "courier", inner, 32, 20)
        pen.text(cx, y, up(kb["yazar"]), "courier", fs, c["yazi"], anchor="ms")
    size, lines = _baslik_satirlari(kb["baslik"], inner, 150, 60)
    y += 26
    for L in lines:
        y += size * 1.0
        pen.text(cx + 5, y + 6, L, "anton", size, c["golge"], anchor="ms")
        pen.text(cx, y, L, "anton", size, c["yazi"], anchor="ms")
        y += size * 0.06
    alt = " · ".join(x for x in (low(kb["tur"]), str(kb["yil"]) if kb["yil"] else "") if x)
    if alt:
        fs = _yazi_sigdir(alt, "courier", inner, 26, 18)
        pen.text(cx, y + 46, alt, "courier", fs, c["vurgu"], anchor="ms")
        y += 46
    # amblem: kalan alanın ortasında
    ky = PH - m - 24
    am_top, am_bot = y + 30, ky - 50
    am = max(80, min(inner - 10, am_bot - am_top, 250))
    pen.paste(amblem_img(kb["amblem"], am * 3, kb["baslik"]), cx - am / 2, (am_top + am_bot) / 2 - am / 2)
    # künye: makas + seri adı
    fs = _yazi_sigdir(seri, "courier", inner - 52, 22, 16)
    lab_w = tw(seri, "courier", fs)
    sw_ = 40
    sx = cx - (sw_ + 8 + lab_w) / 2
    pen.svg(K.scissors_svg(26, ring=c["vurgu"], blade=c["yazi"], pivot=c["vurgu"], outline=None), K.SCISSORS_VB,
            sx, ky - 22, sw_)
    pen.text(sx + sw_ + 8, ky, seri, "courier", fs, c["yazi"])
    im = pen.im.resize((max(1, round(PW * k)), max(1, round(PH * k))), Image.LANCZOS)
    _cache[key] = im
    return im


def kapak_arka(kb: dict, blurb: str, k: float = 1.0) -> Image.Image:
    """Arka kapak (PW x PH x k): üstte yazar · başlık, soru bölümünün metni (arka kapak yazısı), altta barkod ve kanal.
    OKUDUN MU? ve Yorumlara yaz. ayrı katmandır (söylendiklerinde belirir)."""
    key = ("arka", tuple(sorted(kb.items())), blurb, round(k, 3))
    if key in _cache:
        return _cache[key]
    c = KAPAKLAR[kb["kapak_rengi"]]
    pen = K.Pen(0, 0, PW, PH, ss=3)
    pen.rr((0, 0, PW, PH), 0, fill=c["zemin"])
    sirt = 36
    pen.rr((PW - sirt, 0, PW, PH), 0, fill=blend(c["zemin"], INK, 0.22))
    pen.line([(PW - sirt, 0), (PW - sirt, PH)], blend(c["zemin"], INK, 0.5), 4)
    m = 24
    pen.rr((m, m, PW - sirt - m + 6, PH - m), 6, outline=c["vurgu"], width=3)
    cx = (PW - sirt) / 2
    inner = PW - sirt - 2 * m - 34
    ust = up(" · ".join(x for x in (kb["yazar"], kb["baslik"]) if x))
    fs = _yazi_sigdir(ust, "courier", inner, 22, 15)
    pen.text(cx, 78, K.fit(ust, "courier", fs, inner), "courier", fs, c["vurgu"], anchor="ms")
    pen.rr((cx - 56, 94, cx + 56, 97), 1, fill=c["vurgu"])
    if blurb:       # soru: y 118-340 arası (altında OKUDUN MU? etiketi durur), dengeli satırlar, en büyük boyut
        toks = blurb.split()
        for size in range(56, 29, -2):
            ws = [tw(x, GOVDE, size) for x in toks]
            rows = dengeli(ws, tw(" ", GOVDE, size), inner)
            if len(rows) * size * 1.18 <= 222 and all(tw(" ".join(toks[i:j]), GOVDE, size) <= inner for i, j in rows):
                break
        lines = [" ".join(toks[i:j]) for i, j in rows][:5]
        y = 118 + (222 - len(lines) * size * 1.18) / 2
        for L in lines:
            pen.text(cx, y + cap_h(GOVDE, size), L, GOVDE, size, c["yazi"], anchor="ms")
            y += size * 1.18
    # barkod + kanal
    bw, bh = 220, 96
    bx0, by0 = cx - bw / 2, PH - m - 30 - bh
    pen.rr((bx0, by0, bx0 + bw, by0 + bh), 6, fill=OFF, outline=INK, width=4)
    rng = random.Random(7)
    x = bx0 + 18
    while x < bx0 + bw - 20:
        wbar = rng.choice([3, 3, 5, 7])
        pen.rr((x, by0 + 12, x + wbar, by0 + 58), 0, fill=INK)
        x += wbar + rng.choice([3, 4, 6])
    pen.text(cx, by0 + 84, "@bilgimakasi", "courier", 22, INK, anchor="ms")
    im = pen.im.resize((max(1, round(PW * k)), max(1, round(PH * k))), Image.LANCZOS)
    _cache[key] = im
    return im


# ---------------------------------------------------------------- sayfa bükümü ve sırt gölgesi (numpy, önbellekli)
def _bukum_haritasi(w: int, h: int, taraf: str):
    key = ("bukum", w, h, taraf)
    if key not in _cache:
        x = np.arange(w, dtype=np.float32)
        d = (w - 1 - x) if taraf == "sol" else x
        off = CUKUR * (1 - d / w) ** 3
        _cache[key] = off
    return _cache[key]


def bukum(im: Image.Image, taraf: str) -> Image.Image:
    """Sayfayı sırta doğru hafifçe aşağı büker (üst ve alt kenar martı kanadı) ve sırta yakın kenarı koyulaştırır.
    Çıktı CUKUR+2 px daha yüksektir."""
    arr = np.asarray(im, dtype=np.float32)
    h, w = arr.shape[:2]
    off = _bukum_haritasi(w, h, taraf)
    d = (w - 1 - np.arange(w, dtype=np.float32)) if taraf == "sol" else np.arange(w, dtype=np.float32)
    shade = 1 - 0.20 * np.clip(1 - d / 70, 0, 1) ** 1.6
    arr = arr.copy()
    arr[..., :3] *= shade[None, :, None]
    Ho = h + CUKUR + 2
    yy = np.arange(Ho, dtype=np.float32)[:, None] - off[None, :]   # kaynak satır (kesirli)
    y0 = np.floor(yy).astype(np.int32)
    f = (yy - y0)[..., None]
    xs = np.broadcast_to(np.arange(w)[None, :], (Ho, w))
    v0 = (y0 >= 0) & (y0 < h)
    v1 = (y0 + 1 >= 0) & (y0 + 1 < h)
    a = np.where(v0[..., None], arr[np.clip(y0, 0, h - 1), xs], 0)
    b = np.where(v1[..., None], arr[np.clip(y0 + 1, 0, h - 1), xs], 0)
    out = a * (1 - f) + b * f
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def kenar_noktalari(taraf: str, top: float = TOP, x0: float = None) -> list[tuple[float, float]]:
    """Bükülmüş sayfanın dış çizgisi (üst kenar soldan sağa, alt kenar sağdan sola)."""
    x0 = (X_SOL if taraf == "sol" else GX) if x0 is None else x0
    pts_t, pts_b = [], []
    for i in range(0, PW + 1, 6):
        d = (PW - i) if taraf == "sol" else i
        off = CUKUR * (1 - d / PW) ** 3
        pts_t.append((x0 + i, top + off))
        pts_b.append((x0 + i, top + PH + off))
    return pts_t + pts_b[::-1]


# ---------------------------------------------------------------- sayfa çevirme (sütun sütun perspektif)
def cevir(lay: Image.Image, origin, on: Image.Image, arka: Image.Image, theta: float, top: float = TOP,
          gx: float = GX, kivrim: float = 30.0, D: float = 4200.0, golge: bool = True) -> None:
    """Sırt (gx) etrafında dönen yaprağı lay (origin'de duran bölge katmanı) üstüne çizer. theta 0: sağda düz, 180:
    solda düz. Yaprağın üst kenarı sayfanın üst kenarında sabittir (perspektif yalnız aşağı büyütür): çevrilen sayfa
    sekme sırasının üstüne hiç çıkmaz. Ön yüz cos(phi) > 0 iken, arka yüz (aynalanmış sırayla) sonra görünür."""
    ox, oy = origin
    on_a = np.asarray(on.convert("RGBA"))
    arka_a = np.asarray(arka.convert("RGBA"))
    Hp, Wp = on_a.shape[0], on_a.shape[1]
    r = np.arange(Wp + 1, dtype=np.float32)
    phi = np.radians(np.clip(theta + kivrim * math.sin(math.radians(theta)) * (r / Wp) ** 2, 0, 180))
    xs = np.concatenate([[0], np.cumsum(np.cos(phi[:-1]))])
    zs = np.concatenate([[0], np.cumsum(np.sin(phi[:-1]))])
    s = D / (D - zs)
    cx = W / 2
    X = cx + (gx + xs - cx) * s
    out = np.asarray(lay).copy()
    LH_, LW_ = out.shape[:2]
    if golge:   # yaprağın sert gölgesi (yarı saydam mürekkep), yalnız kitabın üstüne
        sh = Image.new("L", (LW_, LH_), 0)
        sd = ImageDraw.Draw(sh)
        k = 18 * math.sin(math.radians(theta))
        poly = [(X[i] + k - ox, top + 14 - oy) for i in range(0, Wp + 1, 6)]
        poly += [(X[i] + k - ox, top + Hp * s[i] + 8 - oy) for i in range(Wp, -1, -6)]
        sd.polygon(poly, fill=int(255 * 0.28))
        sa = (np.asarray(sh, dtype=np.float32) / 255)[..., None] * (out[..., 3:4] > 0)
        out[..., :3] = (out[..., :3] * (1 - sa) + np.array(INK, np.float32) * sa).astype(np.uint8)
    order = np.argsort(zs[:-1], kind="stable")
    cosp = np.cos(phi)
    for i in order:
        xa, xb = X[i] - ox, X[i + 1] - ox
        lo, hi = int(math.floor(min(xa, xb))), int(math.ceil(max(xa, xb)))
        if hi <= lo:
            hi = lo + 1
        lo, hi = max(lo, 0), min(hi, LW_)
        if hi <= lo:
            continue
        front = cosp[i] > 0
        src = on_a[:, i] if front else arka_a[:, Wp - 1 - i]
        h = Hp * s[i]
        y0 = top - oy
        ys0, ys1 = max(0, int(y0)), min(LH_, int(math.ceil(y0 + h)))
        if ys1 <= ys0:
            continue
        idx = np.clip(((np.arange(ys0, ys1) - y0) / s[i]).astype(np.int32), 0, Hp - 1)
        col = src[idx].astype(np.float32)
        lum = (0.80 + 0.20 * abs(cosp[i])) if front else (0.88 + 0.12 * abs(cosp[i]))
        a = col[:, 3:4] / 255
        dst = out[ys0:ys1, lo:hi].astype(np.float32)
        dst[..., :3] = dst[..., :3] * (1 - a[:, None]) + (col[:, None, :3] * lum) * a[:, None]
        dst[..., 3:4] = np.maximum(dst[..., 3:4], col[:, None, 3:4])
        out[ys0:ys1, lo:hi] = dst.astype(np.uint8)
    res = Image.fromarray(out, "RGBA")
    d = ImageDraw.Draw(res)
    tp = [(X[i] - ox, top - oy) for i in range(0, Wp + 1, 3)] + [(X[Wp] - ox, top - oy)]
    bp = [(X[i] - ox, top + Hp * s[i] - oy) for i in range(0, Wp + 1, 3)] + [(X[Wp] - ox, top + Hp * s[Wp] - oy)]
    d.line(tp, fill=INK, width=5, joint="curve")
    d.line(bp, fill=INK, width=5, joint="curve")
    d.line([tp[-1], bp[-1]], fill=INK, width=5)
    lay.paste(res, (0, 0))


# ---------------------------------------------------------------- video
class KitapVideo:
    def __init__(self, scenes, words: list[Word], meta: dict, bcfg: dict, yil: int | None = None):
        from .brand import Brand
        self.scenes, self.words, self.meta = scenes, words, meta or {}
        self.kb = kitap_bilgisi(self.meta, yil)
        self.var = varyant(self.meta)
        self.seri = self.var["seri_adi"]
        self.renk = KAPAKLAR[self.kb["kapak_rengi"]]
        on = bool(bcfg.get("enabled", False))
        self.brand = Brand(bcfg, {}) if on else None
        self.intro = bool(on and bcfg.get("intro_cut", True))
        self.starts = [w.start for w in words]
        m = re.search(r"#\s*(\d+)", (scenes[0].kicker or "") if scenes else "")
        self.no = int(m.group(1)) if m else 0
        self.alinti = bool(self.kb["ilk_cumle"])
        self.bolumler = plan(scenes, words)
        # sekmeler videodaki bölümlerdir (bölüm atlanmışsa sekmesi de yok): İLK CÜMLE (ya da KÜNYE) / KONU / ...
        self.sekme_adlari = [KUNYE if (b.ad == "giris" and not self.alinti) else SEKMELER[b.ad] for b in self.bolumler]
        self._c: dict = {}                              # bu videonun katman önbelleği (içerik videoya özgü)
        self._mascots: dict = {}
        self._metin: dict = {}
        self._sag: dict = {}
        self.kutular: list[tuple[str, tuple]] = []      # son karedeki yazı kutuları (güvenli alan denetimi)
        self._zaman()

    # ------------------------------------------------------------ zaman çizelgesi
    def _kelime_ani(self, pattern, a: int, b: int) -> float | None:
        for i in range(a, min(b, len(self.words))):
            if re.match(pattern, low(" ".join(w.text for w in self.words[i:i + 2]))):
                return self.words[i].start
        return None

    def _zaman(self):
        bl = self.bolumler
        g = bl[0]
        end0 = bl[1].start if len(bl) > 1 else (self.words[-1].end + 1.0 if self.words else g.end)
        # kapak açılışı: ilk cümle okunacaksa hemen öncesinde, değilse kanca cümlesinin sonunda
        want = None
        if self.alinti:
            ilk = [_norm(x) for x in self.kb["ilk_cumle"].split()[:3]]
            for i in range(g.a, min(g.b, len(self.words)) - 2):
                if [_norm(self.words[i + q].text) for q in range(3)] == ilk:
                    want = self.words[i].start - (ACILIS_ORT + ACILIS_DON * 0.55)
                    break
        if want is None:
            for i in range(g.a, min(g.b, len(self.words))):
                if self.words[i].text.rstrip('"”’)')[-1:] in ".?!:":
                    want = self.words[i].end + 0.1
                    break
        if want is None:
            want = g.start + 1.6
        acilis_son = ACILIS_ORT + ACILIS_DON
        self.t_ac = max(1.0, min(want, end0 - acilis_son - 0.3))
        prev = self.t_ac + acilis_son
        self.gecis: list[float] = [self.t_ac]   # bölüm i'nin geçişinin başladığı an (giriş: kapak açılışı)
        for b in bl[1:]:
            t0 = max(b.start, prev + 0.05)
            self.gecis.append(t0)
            prev = t0 + (KAPAN + SON_KAY if b.ad == "soru" else CEVIR)
        self.soru = len(bl) - 1 if len(bl) > 1 and bl[-1].ad == "soru" else None
        # sayfa metinleri (sağ sayfanın açıldığı an: geçişin yarısı)
        for i, b in enumerate(bl):
            reveal = self.gecis[i] + (ACILIS_ORT + ACILIS_DON * 0.6 if i == 0 else CEVIR * 0.6)
            if b.ad != "soru":
                self._metin[i] = SayfaMetni(b.paragraflar, self.words, reveal)
        if self.soru is not None:
            sb = bl[self.soru]
            self.t_kapan = self.gecis[self.soru]
            self.t_son = self.t_kapan + KAPAN + SON_KAY
            self.t_okudun = self._kelime_ani(r"okudun\b", sb.a, sb.b)
            self.t_yorum = self._kelime_ani(r"yorumlara\b", sb.a, sb.b)
            if self.t_okudun is None:
                self.t_okudun = self.t_son + 0.3
            if self.t_yorum is None:
                self.t_yorum = max(self.t_okudun + 0.6, self.t_son + 0.9)
            self.t_okudun = max(self.t_okudun - 0.08, self.t_son + 0.05)
            self.t_yorum = max(self.t_yorum - 0.08, self.t_okudun + 0.25)
            # arka kapak yazısı: soru sayfasının metni; yalnız "Okudun mu? Yorumlara yaz." ise (içerik kalıbı boş soru
            # sayfasına bunu yazar) soru dış sesten gelir. OKUDUN MU? ve Yorumlara yaz. ayrı katmandır, burada yazılmaz.
            blurb = _kirp_metin(" ".join(p.metin for p in sb.paragraflar), 18)
            if not blurb:
                blurb = _kirp_metin(" ".join(self.scenes[i].narration for i in sb.sahneler), 18)
            self.blurb = blurb

    def bolum_at(self, t: float) -> int:
        return max(0, bisect.bisect_right(self.gecis, t) - 1) if t >= self.gecis[0] else 0

    def evre(self, t: float) -> tuple[str, int, float]:
        """(evre, bölüm, yerel zaman): kapak | acilis | sayfa | cevir | kapan | son."""
        if t < self.t_ac:
            return "kapak", 0, t
        i = self.bolum_at(t)
        lt = t - self.gecis[i]
        if i == 0:
            return ("acilis", 0, lt) if lt < ACILIS_ORT + ACILIS_DON else ("sayfa", 0, lt)
        if i == self.soru:
            return ("kapan", i, lt) if lt < KAPAN + SON_KAY else ("son", i, lt)
        return ("cevir", i, lt) if lt < CEVIR else ("sayfa", i, lt)

    # ------------------------------------------------------------ yazı kutuları
    def kayit(self, ad: str, box) -> None:
        self.kutular.append((ad, tuple(round(float(v), 1) for v in box)))

    # ------------------------------------------------------------ seri etiketi, kanca, manşet
    def seri_katmani(self, size: float = 70) -> tuple[Image.Image, list]:
        """BİR KİTAP (siyah) + BİR DAKİKA (kırmızı) yırtık etiketleri ve bölüm numarası; tek satıra sığmazsa küçülür."""
        key = ("seri", self.seri, size, self.no)
        if key in self._c:
            return self._c[key]
        ws = self.seri.split()
        k = max(1, len(ws) // 2)
        a, b = " ".join(ws[:k]), " ".join(ws[k:])
        no = f"#{self.no:02d}" if self.no else ""
        while size > 40:
            wa, wb = etiket_gen(a, size), etiket_gen(b, size) if b else 0
            wn = etiket_gen(no, size * 0.6) + 24 if no else 0
            if 64 + wa + 18 + wb + wn <= 920:
                break
            size -= 2
        pen_w, pen_h = W, 200
        lay = Image.new("RGBA", (pen_w, pen_h), (0, 0, 0, 0))
        boxes = []
        cy = 100
        x = 64
        for i, (txt, bg) in enumerate(((a, INK), (b, RED))):
            if not txt:
                continue
            im, lw, lh = etiket(txt, size, OFF, bg, 11 + i, -2.0 + 1.2 * i)
            ortala(lay, im, x + lw / 2, cy + size * 0.03 * i)
            boxes.append((f"seri {txt}", (x, cy - lh / 2, x + lw, cy + lh / 2)))
            x += lw + 18
        if no:
            im, lw, lh = etiket(no, size * 0.6, INK, YELLOW, 21, 4)
            x += 10
            ortala(lay, im, x + lw / 2, cy - 4)
            boxes.append(("bölüm no", (x, cy - 4 - lh / 2, x + lw, cy - 4 + lh / 2)))
        self._c[key] = (lay, boxes)
        return self._c[key]

    def kanca_katmani(self) -> tuple[Image.Image, list, tuple]:
        """Kanca karesinin üst katmanı (kesilecek olan): seri etiketi, kanca başlığı, kütüphane kartı. Bölge CLIP."""
        key = ("kanca",)
        if key in self._c:
            return self._c[key]
        y0 = SAFE[1]
        lay = Image.new("RGBA", (SAFE[2], SAFE[3] - SAFE[1]), (0, 0, 0, 0))
        boxes = []
        seri, sb = self.seri_katmani(70)
        K._comp(lay, seri, 0, 292 - 100 - y0)
        boxes += [(n, (b[0], b[1] + 192, b[2], b[3] + 192)) for n, b in sb]
        g = self.bolumler[0]
        lines = g.headline or [up(self.kb["baslik"])]
        lines = lines[:3]
        hl = g.hl if g.hl >= 0 else len(lines) - 1
        size = 112
        while size > 64:
            hs = [etiket_boy(L, self._sigan(L, size, 840)) for L in lines]
            if sum(hs) + 12 * (len(lines) - 1) <= 290 and all(etiket_gen(L, self._sigan(L, size, 840)) <= 850
                                                                for L in lines):
                break
            size -= 4
        y = KANCA_Y0
        for i, L in enumerate(lines):
            s = self._sigan(L, size, 840)
            fg, bg = (OFF, RED) if i == hl else (INK, OFF)
            im, lw, lh = etiket(L, s, fg, bg, 31 + i, -1.6 if i % 2 == 0 else 1.4)
            lx = 70 + (56 if i % 2 else 0)
            lx = min(lx, 920 - lw)
            ortala(lay, im, lx + lw / 2, y + lh / 2 - y0)
            boxes.append((f"kanca {L}", (lx, y, lx + lw, y + lh)))
            y += lh + 12
        self.kanca_alt = y
        kart, kbox = self.kutuphane_karti(KART_KANCA[1] - KART_KANCA[0], damga=None)
        kcx = (KART_KANCA[0] + KART_KANCA[1]) / 2
        kcy = max(y + 160, 930)
        ortala(lay, kart, kcx, kcy - y0)
        boxes.append(("kütüphane kartı", (kcx - kbox[0] / 2, kcy - kbox[1] / 2, kcx + kbox[0] / 2, kcy + kbox[1] / 2)))
        self._c[key] = (lay, boxes, (60, KANCA_Y0, 900, y))
        return self._c[key]

    @staticmethod
    def _sigan(text: str, size: float, max_w: float) -> float:
        while size > 56 and etiket_gen(text, size) > max_w:
            size -= 2
        return size

    def manset(self, i: int) -> tuple[Image.Image, list]:
        """Bölümün yırtık manşeti (tek satır, y 245-410); konu bölümünde 'spoiler yok' rozeti."""
        key = ("manset", i)
        if key in self._c:
            return self._c[key]
        b = self.bolumler[i]
        if b.ad == "giris":
            text = " ".join(b.headline) if b.headline else (SEKMELER["giris"] if self.alinti else KUNYE)
        else:
            text = self.var["basliklar"].get(b.ad, up(b.ad))
        size = 104
        while size > 64 and etiket_gen(text, size) > 850:
            size -= 2
        if etiket_gen(text, size) > 850:
            text = SEKMELER["giris"] if b.ad == "giris" and self.alinti else (
                KUNYE if b.ad == "giris" else self.var["basliklar"].get(b.ad, up(b.ad)))
            size = 96
            while size > 56 and etiket_gen(text, size) > 850:
                size -= 2
        fg, bg = MANSET_RENK.get(b.ad, (OFF, INK))
        lay = Image.new("RGBA", (SAFE[2], 200), (0, 0, 0, 0))
        im, lw, lh = etiket(text, size, fg, bg, 40 + i, 1.2 if i % 2 else -1.4)
        cy = 330 - 230
        ortala(lay, im, 70 + lw / 2, cy)
        boxes = [(f"manşet {text}", (70, 330 - lh / 2, 70 + lw, 330 + lh / 2))]
        if b.ad == "konu" and 70 + lw + 20 < 690:
            r, rw, rh = etiket("spoiler yok", 30, INK, YELLOW, 61, -5, font="courier")
            rx = min(905 - rw / 2, 70 + lw + 30 + rw / 2)
            ortala(lay, r, rx, 274 - 230)
            boxes.append(("rozet", (rx - rw / 2, 274 - rh / 2, rx + rw / 2, 274 + rh / 2)))
        self._c[key] = (lay, boxes)
        return self._c[key]

    # ------------------------------------------------------------ kütüphane kartı
    def kutuphane_karti(self, cw: float, damga: str | None = None, rot: float = 3.0):
        """Kütüphane ödünç kartı (künye); satırlar kartın içinde payla, uzun değer küçülür ya da kısalır. Görüntü ve
        (genişlik, yükseklik)."""
        key = ("kart", cw, damga, rot)
        if key in self._c:
            return self._c[key]
        kb = self.kb
        rows = [("Eser", kb["baslik"]), ("Yazar", kb["yazar"])]
        if not damga:
            rows.append(("Yıl", " · ".join(x for x in (str(kb["yil"]) if kb["yil"] else "", low(kb["tur"])) if x)))
        rows = [(a, b) for a, b in rows if b]
        pad, head, step = 22, 52, 48
        lab_w = max(tw(a + ":", "courier", 24) for a, _ in rows) + 14 if rows else 0
        room = cw - 2 * pad - lab_w
        satirlar = []                                   # (etiket, değer satırları, boyut)
        for a, bval in rows:
            fs = 26
            while fs > 20 and tw(bval, "courier", fs) > room:
                fs -= 1
            if tw(bval, "courier", fs) <= room:
                satirlar.append((a, [bval], fs))
            else:                                       # iki satır (ikincisi sığmazsa kısalır)
                fs = 22
                parca = [" ".join(x) for x in K.wrap(bval, "courier", fs, room)]
                ikinci = " ".join(parca[1:])
                satirlar.append((a, [K.fit(parca[0], "courier", fs, room), K.fit(ikinci, "courier", fs, room)], fs))
        ch = head + 16 + sum(step + 28 * (len(v) - 1) for _, v, _ in satirlar) + (70 if damga else 6) + pad
        sp = K.Sprite(cw, ch, margin=40)
        sp.polygon([(0, 0), (cw, 0), (cw, ch), (0, ch)], OFF + (255,))
        sp.polygon([(0, 0), (cw, 0), (cw, head), (0, head)], INK + (255,))
        no = f"No {self.no:03d}" if self.no else ""
        hs = 24
        while hs > 16 and tw("KÜTÜPHANE KARTI", "courier", hs) + (tw(no, "courier", hs) + 16 if no else 0) > cw - 2 * pad:
            hs -= 1
        sp.text((pad, head / 2 + cap_h("courier", hs) / 2), "KÜTÜPHANE KARTI", "courier", hs, OFF)
        if no:
            sp.text((cw - pad, head / 2 + cap_h("courier", hs) / 2), no, "courier", hs, YELLOW, anchor="rs")
        y = head + 16
        for a, vals, fs in satirlar:
            base = y + step / 2 + 9
            sp.text((pad, base), a + ":", "courier", 24, DGREY)
            for q, v in enumerate(vals):
                sp.text((pad + lab_w, base + 28 * q), v, "courier", fs, INK)
            y += step + 28 * (len(vals) - 1)
            sp.line([(pad - 6, y), (cw - pad + 6, y)], (205, 201, 192, 255), 2)
        sp.line([(0, 0), (cw, 0), (cw, ch), (0, ch), (0, 0)], INK + (255,), 4)
        if damga:
            fs = 36
            sw_, sh_ = tw(damga, "anton", fs) + 34, 54
            st = K.Sprite(sw_, sh_, margin=20)
            col = RED + (235,)
            st.line([(0, 0), (sw_, 0), (sw_, sh_), (0, sh_), (0, 0)], col, 6)
            st.line([(7, 7), (sw_ - 7, 7), (sw_ - 7, sh_ - 7), (7, sh_ - 7), (7, 7)], col, 2)
            st.text((sw_ / 2, sh_ / 2 + cap_h("anton", fs) / 2), damga, "anton", fs, col, anchor="ms")
            sti = st.render_ss(-2.5)
            scx, scy = cw - pad - sw_ / 2 - 4, ch - pad - sh_ / 2 - 2
            sp.im.alpha_composite(sti, (int((scx + 40) * SS - sti.width / 2), int((scy + 40) * SS - sti.height / 2)))
        im = sp.render(rot, (8, 10, 0, 0.9))
        self._c[key] = (im, (cw, ch))
        return self._c[key]

    # ------------------------------------------------------------ sekmeler
    def sekmeler(self, aktif: int, kisa: str | None = None) -> Image.Image:
        """Sekme sırası (REGION katmanı). kisa None: açık kitabın üstünde yazılı sekmeler; 'sag'/'sol': kapalı kitabın
        (sağ ya da sol yarıda) numaralı dar sekmeleri. Bitenler kırmızı + ✓, o anki sarı ve uzun, sıradakiler kâğıt."""
        key = ("sekme", aktif, kisa)
        if key in self._c:
            return self._c[key]
        pen = K.Pen(*REGION)
        n = len(self.sekme_adlari)
        alt = TOP + 4
        if kisa is None:
            x0, x1 = X_SOL + 22, X_SAG - 22
        elif kisa == "sag":
            x0, x1 = GX + 34, X_SAG - 6
        else:
            x0, x1 = X_SOL + 6, GX - 34
        fs = 24
        tick = 24
        if kisa is None:
            nat = [tw(ad, "courier", fs) + tick + 34 for ad in self.sekme_adlari]
            extra = (x1 - x0 - sum(nat) - 10 * (n - 1)) / n
            ws = [w + extra for w in nat]
            gap = 10
        else:
            ws = [(x1 - x0 - 8 * (n - 1)) / n] * n
            gap = 8
        x = x0
        boxes = []
        for i, ad in enumerate(self.sekme_adlari):
            dur = "bitti" if i < aktif else ("aktif" if i == aktif else "sonra")
            sw_ = ws[i]
            h = 62 + (18 if dur == "aktif" else 0)
            bg, fg = {"bitti": (RED, OFF), "aktif": (YELLOW, INK), "sonra": (PAPER, DGREY)}[dur]
            top = alt - h
            pen.rr((x + 5, top + 6, x + sw_ + 5, alt + 40), 9, fill=INK)
            pen.rr((x, top, x + sw_, alt + 40), 9, fill=bg, outline=INK, width=4)
            ty = top + 40
            if kisa:
                if dur == "bitti":
                    pen.svg(K.check_svg(OFF, 18), K.ICON_VB, x + sw_ / 2 - 16, top + 9, 32)
                else:
                    pen.text(x + sw_ / 2, top + 42, str(i + 1), "anton", 32, fg, anchor="ms")
            elif dur == "bitti":
                wl = tick + 4 + tw(ad, "courier", fs)
                lx = x + (sw_ - wl) / 2
                pen.svg(K.check_svg(OFF, 18), K.ICON_VB, lx - 2, top + 15, tick + 4)
                pen.text(lx + tick + 4, ty, ad, "courier", fs, fg)
                boxes.append((f"sekme {ad}", (x, top, x + sw_ + 5, alt)))
            else:
                pen.text(x + sw_ / 2, ty, ad, "courier", fs, fg, anchor="ms")
                boxes.append((f"sekme {ad}", (x, top, x + sw_ + 5, alt)))
            x += sw_ + gap
        im = pen.done()
        im.kutular = boxes  # type: ignore[attr-defined]
        self._c[key] = im
        return im

    # ------------------------------------------------------------ açık kitabın parçaları
    def kurdele(self) -> Image.Image:
        """Sırttan inen yeşil kitap ayracı (REGION katmanı)."""
        if "kurdele" in self._c:
            return self._c["kurdele"]
        pen = K.Pen(*REGION)
        x, y0, y1, w = GX + 2, TOP - 6, BOT + 96, 30
        pts = [(x + 14 * max(0, (t - 0.72) / 0.28) ** 2, y0 + (y1 - y0) * t) for t in np.linspace(0, 1, 25)]
        left = [(px - w / 2, py) for px, py in pts]
        right = [(px + w / 2, py) for px, py in pts]
        tip = pts[-1]
        poly = left + [(tip[0] - w / 2, tip[1] + 8), (tip[0], tip[1] - w * 0.55), (tip[0] + w / 2, tip[1] + 8)] + right[::-1]
        pen.poly([(px + 6, py + 7) for px, py in poly], INK + (230,))
        pen.poly(poly, YESIL)
        pen.line(poly + [poly[0]], INK, 4)
        pen.line([(px - w / 2 + 7, py) for px, py in pts[1:-2]], blend(YESIL, OFF, 0.35), 2.5)
        self._c["kurdele"] = pen.done()
        return self._c["kurdele"]

    def cilt(self, yarim: str = "tam") -> Image.Image:
        """Cilt kartonu + sert gölge (REGION katmanı). yarim: tam | sag | sol."""
        key = ("cilt", yarim, self.kb["kapak_rengi"])
        if key in self._c:
            return self._c[key]
        pen = K.Pen(*REGION)
        x0 = X_SOL - BOARD if yarim in ("tam", "sol") else GX - 4
        x1 = X_SAG + BOARD if yarim in ("tam", "sag") else GX + 4
        y0, y1 = TOP - 8, BOT + CUKUR + 6 + STACK * 5 + 10
        pen.rr((x0 + 10, y0 + 12, x1 + 10, y1 + 12), 16, fill=INK)
        pen.rr((x0, y0, x1, y1), 16, fill=self.renk["zemin"], outline=INK, width=6)
        self._c[key] = pen.done()
        return self._c[key]

    def yigin(self, nL: int, nR: int) -> Image.Image:
        """Sayfa yığınları (sırttan uzaklaştıkça kalın) + yaprak çizgileri (REGION katmanı)."""
        key = ("yigin", nL, nR)
        if key in self._c:
            return self._c[key]
        pen = K.Pen(*REGION)
        for side, n in (("sol", nL), ("sag", nR)):
            for k in range(n, 0, -1):
                dy = STACK * k
                if side == "sol":
                    pen.rr((X_SOL - 2 + k, TOP + dy, GX, BOT + CUKUR + dy), 4, fill=SAYFA_KENAR, outline=INK, width=2.5)
                else:
                    pen.rr((GX, TOP + dy, X_SAG + 2 - k, BOT + CUKUR + dy), 4, fill=SAYFA_KENAR, outline=INK, width=2.5)
        self._c[key] = pen.done()
        return self._c[key]

    def kenarlar(self, sol: bool = True, sag: bool = True) -> Image.Image:
        """Bükülmüş sayfaların mürekkep kenarı ve sırt çizgisi (REGION katmanı)."""
        key = ("kenar", sol, sag)
        if key in self._c:
            return self._c[key]
        pen = K.Pen(*REGION)
        for taraf, on in (("sol", sol), ("sag", sag)):
            if on:
                poly = kenar_noktalari(taraf)
                pen.line(poly + [poly[0]], INK, 5)
        if sol and sag:
            pen.line([(GX, TOP + CUKUR), (GX, BOT + CUKUR)], blend(INK, SAYFA, 0.35), 3)
        self._c[key] = pen.done()
        return self._c[key]

    def _ilerleme(self, i: float) -> tuple[int, int]:
        n = max(1, len(self.bolumler) - 1)
        p = K.clamp(i / n)
        return 1 + round(4 * p), 1 + round(4 * (1 - p))

    # ------------------------------------------------------------ sayfalar
    def _sayfa_bos(self, taraf: str, no: int) -> K.Pen:
        pen = K.Pen(0, 0, PW, PH)
        pen.rr((0, 0, PW, PH), 0, fill=SAYFA)
        if taraf == "sol":
            head = f"{self.seri}" + (f" · {self.no:02d}" if self.no else "")
            fs = _yazi_sigdir(head, "courier", PW - 76, 22, 16)
            pen.text(36, 56, head, "courier", fs, DGREY)
            pen.rr((36, 70, PW - 34, 72.5), 1, fill=CIZGI)
            pen.text(36, PH - 30, str(2 * no + 1), "courier", 22, DGREY)
        else:
            head = up(self.kb["baslik"])
            fs = _yazi_sigdir(head, "courier", PW - 76, 22, 16)
            pen.text(PW - 30, 56, K.fit(head, "courier", fs, PW - 76), "courier", fs, DGREY, anchor="rs")
            pen.rr((TX0, 70, PW - 30, 72.5), 1, fill=CIZGI)
            pen.text(PW - 30, PH - 30, str(2 * no + 2), "courier", 22, DGREY, anchor="rs")
        return pen

    def sol_sayfa(self, i: int, duz: bool = False) -> Image.Image:
        """Bölümün sol sayfası (bükülmüş; duz True: çevrilen yaprağın arka yüzü için düz). Tipografik: giriş ilk
        cümle ya da künye; konu büyük yıl; fikir öne çıkan alıntı (vurgu); bilgi büyük sayı ya da tarih, yoksa
        alıntı. Bölümde çizim (sprite) varsa çizim. Hiçbiri yoksa amblem."""
        key = ("sol", i, duz)
        if key in self._c:
            return self._c[key]
        b = self.bolumler[i]
        pen = self._sayfa_bos("sol", b.no)
        boxes = []
        tur = self._sol_tur(b)
        L, R = 36, PW - 40               # sırt tarafında kurdele ve gölge payı
        if tur == "cizim":
            try:
                sp = Image.open(b.sprite).convert("RGBA")
                bb = sp.getchannel("A").getbbox()
                if bb:
                    sp = sp.crop(bb)
                k = min((R - L) / sp.width, 470 / sp.height)
                sp = sp.resize((max(1, int(sp.width * k * SS)), max(1, int(sp.height * k * SS))), Image.LANCZOS)
                pen.paste(sp, (L + R) / 2 - sp.width / SS / 2, 110 + (500 - sp.height / SS) / 2)
            except (OSError, ValueError):
                tur = "amblem"
        if tur == "alinti":
            boxes += self._sol_alinti(pen, L, R)
        elif tur == "kunye":
            boxes += self._sol_kunye(pen, L, R)
        elif tur == "yil":
            boxes += self._sol_buyuk(pen, L, R, str(self.kb["yil"]), "İLK YAYIN",
                                     [x for x in (low(self.kb["tur"]), f"{self.kb['ozgun_dil']} aslından"
                                                  if self.kb["ozgun_dil"] else "") if x])
        elif tur.startswith("sayi:"):
            ust, alt = tur[5:].split("|", 1)
            boxes += self._sol_buyuk(pen, L, R, ust, "NOT ET", [alt] if alt else [], ikinci=bool(alt))
        elif tur == "vurgu":
            boxes += self._sol_vurgu(pen, L, R, b)
        elif tur == "amblem":
            am = 300
            pen.paste(amblem_img(self.kb["amblem"], am * SS, self.kb["baslik"]), (L + R) / 2 - am / 2, 190)
            lab = self.var["basliklar"].get(b.ad, "") if b.ad != "giris" else ""
            if lab:
                pen.text((L + R) / 2, 560, lab, "courier", 26, RED, anchor="ms")
        im = pen.done()
        im = im if duz else bukum(im, "sol")
        im.kutular = boxes  # type: ignore[attr-defined]
        self._c[key] = im
        return im

    def _sol_tur(self, b: Bolum) -> str:
        if b.ad == "giris":
            return "alinti" if self.alinti else "kunye"
        if b.sprite is not None and Path(b.sprite).is_file():
            return "cizim"
        if b.ad == "konu":
            return "yil" if self.kb["yil"] else "amblem"
        text = " ".join(p.metin for p in b.paragraflar)
        if b.ad == "bilgi":
            m = re.search(r"\b(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|"
                          r"Aralık)\s+(\d{3,4})\b", text)
            if m:
                return f"sayi:{m.group(1)} {up(m.group(2))}|{m.group(3)}"
            m = re.search(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d{1,4})(?:[.,]\d+)?(?![\d])", text)
            if m:
                return f"sayi:{m.group(0)}|"
        if any(p.vurgu and low(p.vurgu) in low(p.metin) for p in b.paragraflar):
            return "vurgu"
        return "amblem"

    def _sol_alinti(self, pen: K.Pen, L: float, R: float) -> list:
        """İlk cümle sayfası: kendi çevirimiz, en az 40 px, sayfanın tamamı."""
        q = self.kb["ilk_cumle"]
        pen.text(L, 118, "İLK CÜMLE", "courier", 26, RED)
        pen.rr((L, 128, L + 64, 132), 1, fill=RED)
        width = R - L
        area = (150, PH - 120)
        chosen = None
        for size in (52, 50, 48, 46, 44, 42, 40):
            lines = [" ".join(x) for x in K.wrap("“" + q + "”", ALINTI, size, width)]
            if len(lines) * size * 1.2 <= area[1] - area[0] and all(tw(x, ALINTI, size) <= width for x in lines):
                chosen = (size, lines)
                break
        if chosen is None:          # çok uzun cümle: 40 px'te sayfaya sığan kadarı, sonu üç nokta
            size = 40
            lines = [" ".join(x) for x in K.wrap("“" + q + "”", ALINTI, size, width)]
            maxl = int((area[1] - area[0]) / (size * 1.2))
            lines = lines[:maxl]
            lines[-1] = K.fit(lines[-1].rstrip("”") + "…”", ALINTI, size, width)
            chosen = (size, lines)
        size, lines = chosen
        self.alinti_px = size
        lh = size * 1.2
        y = area[0] + cap_h(ALINTI, size) + 8
        for Lx in lines:
            pen.text(L, y, Lx, ALINTI, size, INK)
            y += lh
        kim = " · ".join(x for x in (self.kb["yazar"], self.kb["baslik"] + (f" ({self.kb['yil']})" if self.kb["yil"]
                                                                              else "")) if x)
        fs = _yazi_sigdir("— " + kim, "courier", width, 22, 15)
        yy = min(PH - 82, y + 14)
        pen.text(L, yy, "— " + kim, "courier", fs, DGREY)
        pen.text(L, yy + 30, "çeviri: Bilgi Makası", "courier", 20, DGREY)
        return [("ilk cümle", (L, area[0], R, y)), ("çeviri notu", (L, yy - 22, R, yy + 34))]

    def _sol_kunye(self, pen: K.Pen, L: float, R: float) -> list:
        """Künye sayfası (alıntısız kitap): başlık, yazar ve satırlar."""
        kb = self.kb
        pen.text(L, 118, KUNYE, "courier", 26, RED)
        pen.rr((L, 128, L + 64, 132), 1, fill=RED)
        rows = [("Yıl", str(kb["yil"]) if kb["yil"] else ""), ("Tür", low(kb["tur"])), ("Özgün dil", kb["ozgun_dil"])]
        rows = [(a, b) for a, b in rows if b]
        alt_h = (58 if kb["yazar"] else 0) + 34 + 52 * len(rows) + 16
        bos = PH - 76 - 160 - alt_h                       # başlığa kalan yükseklik
        for mx in range(96, 39, -4):
            size, lines = _baslik_satirlari(kb["baslik"], R - L, mx, 40)
            if len(lines) * size * 1.08 <= bos:
                break
        y = 160 + max(0.0, (bos - len(lines) * size * 1.08) / 2)    # künye bloğu sayfada ortalanır
        for Lx in lines:
            y += size
            pen.text(L, y, Lx, "anton", size, INK)
            y += size * 0.08
        if kb["yazar"]:
            fs = _yazi_sigdir(kb["yazar"], GOVDE, R - L, 40, 26)
            y += 58
            pen.text(L, y, kb["yazar"], GOVDE, fs, RED)
        y += 34
        lab_w = max((tw(a + ":", "courier", 24) for a, _ in rows), default=0) + 14
        for a, bval in rows:
            y += 52
            fs = _yazi_sigdir(bval, "courier", R - L - lab_w, 28, 18)
            pen.text(L, y, a + ":", "courier", 24, DGREY)
            pen.text(L + lab_w, y, K.fit(bval, "courier", fs, R - L - lab_w), "courier", fs, INK)
            pen.line([(L, y + 14), (R, y + 14)], CIZGI, 2)
        am = 120
        if y + 40 + am < PH - 70:
            pen.paste(amblem_img(kb["amblem"], am * SS, kb["baslik"]), R - am, PH - 70 - am)
        return [("künye", (L, 100, R, y + 16))]

    def _sol_buyuk(self, pen: K.Pen, L: float, R: float, buyuk: str, etiket_: str, altlar: list[str],
                   ikinci: bool = False) -> list:
        """Büyük yıl / sayı / tarih sayfası. ikinci: altlar[0] ikinci büyük satır (tarihte yıl)."""
        pen.text(L, 118, etiket_, "courier", 26, RED)
        pen.rr((L, 128, L + 64, 132), 1, fill=RED)
        size = 190
        while size > 70 and tw(buyuk, "anton", size) > R - L:
            size -= 4
        y = 170 + size
        pen.text(L, y, buyuk, "anton", size, INK)
        if ikinci and altlar:
            s2 = min(size * 0.72, 150)
            while s2 > 50 and tw(altlar[0], "anton", s2) > R - L:
                s2 -= 4
            y += s2 + 14
            pen.text(L, y, altlar[0], "anton", s2, RED)
            altlar = altlar[1:]
        pen.rr((L, y + 30, L + 120, y + 37), 2, fill=YELLOW)
        y += 40
        for a in altlar:
            fs = _yazi_sigdir(a, GOVDE, R - L, 38, 24)
            y += 58
            pen.text(L, y, a, GOVDE, fs, DGREY)
        am = 110
        if y + 40 + am < PH - 70:
            pen.paste(amblem_img(self.kb["amblem"], am * SS, self.kb["baslik"]), R - am, PH - 70 - am)
        return [("büyük sayı", (L, 100, R, y + 10))]

    def _sol_vurgu(self, pen: K.Pen, L: float, R: float, b: Bolum) -> list:
        """Öne çıkan alıntı: sayfa metninin vurgusu büyük yazıyla, kırmızı tırnak."""
        v = next(p.vurgu for p in b.paragraflar if p.vurgu and low(p.vurgu) in low(p.metin))
        pen.text(L - 4, 300, "“", ALINTI, 240, RED)
        width = R - L
        chosen = None
        for size in (64, 60, 56, 52, 48, 44, 40):
            lines = [" ".join(x) for x in K.wrap(v, ALINTI, size, width)]
            if len(lines) * size * 1.18 <= 330 and all(tw(x, ALINTI, size) <= width for x in lines):
                chosen = (size, lines)
                break
        size, lines = chosen or (40, [" ".join(x) for x in K.wrap(v, ALINTI, 40, width)][:7])
        y = 300 + cap_h(ALINTI, size)
        for Lx in lines:
            pen.text(L, y, Lx, ALINTI, size, INK)
            y += size * 1.18
        lab = "— " + low(self.var["basliklar"].get(b.ad, b.ad))
        pen.text(L, y + 26, lab, "courier", 24, DGREY)
        return [("öne çıkan alıntı", (L, 160, R, y + 34))]

    def sag_bos(self, i: int) -> Image.Image:
        """Sağ sayfanın yazısız hâli (SS ölçeğinde Pen görüntüsü)."""
        key = ("sagbos", i)
        if key not in self._c:
            self._c[key] = self._sayfa_bos("sag", self.bolumler[i].no).im
        return self._c[key]

    def sag_sayfa(self, i: int, t: float, duz: bool = False) -> Image.Image:
        """Sağ sayfa: o ana kadar yazılmış kelimeler ve fosforlu kalem (durum başına önbellekli)."""
        sm = self._metin.get(i)
        d = sm.durum(t) if sm else (0, (), 0)
        key = (i, d, duz)
        if key in self._sag:
            return self._sag[key]
        pen = K.Pen(0, 0, PW, PH)
        pen.im.paste(self.sag_bos(i), (0, 0))
        if sm:
            sm.ciz(pen, TX0, TY0, *d)
        im = pen.done()
        im = im if duz else bukum(im, "sag")
        if len(self._sag) > 64:
            self._sag.clear()
        self._sag[key] = im
        return im

    # ------------------------------------------------------------ katman birleştirme
    def _acik_kitap(self, lay: Image.Image, sol_i: int | None, sag_i: int | None, t: float, aktif: int,
                    ilerleme: float, sekme: str | None = "tam", cilt: str = "tam") -> None:
        """Açık kitabı REGION katmanına çizer: cilt, sekmeler, yığınlar, sayfalar, kenarlar ve kurdele.
        sol_i / sag_i None: o yarı yok (kapak açılırken sol, kapanırken sağ)."""
        ox, oy = REGION[:2]
        lay.alpha_composite(self.cilt(cilt))
        if sekme == "tam":
            lay.alpha_composite(self.sekmeler(aktif))
        elif sekme in ("sag", "sol"):
            lay.alpha_composite(self.sekmeler(aktif, sekme))
        nL, nR = self._ilerleme(ilerleme)
        lay.alpha_composite(self.yigin(nL if sol_i is not None else 0, nR if sag_i is not None else 0))
        if sol_i is not None:
            K._comp(lay, self.sol_sayfa(sol_i), X_SOL - ox, TOP - oy)
        if sag_i is not None:
            K._comp(lay, self.sag_sayfa(sag_i, t), GX - ox, TOP - oy)
            sm = self._metin.get(sag_i)
            if sm:
                im = sm.imlec(sm.durum(t)[0])
                if im and t >= self._reveal(sag_i) and int(t * 4) % 2 == 0:
                    x, base, size = im
                    xx, yy = GX + TX0 + x - ox, TOP + TY0 + base - oy
                    ImageDraw.Draw(lay).rectangle([xx, yy - size * 0.72, xx + size * 0.32, yy + 2], fill=RED)
        lay.alpha_composite(self.kenarlar(sol_i is not None, sag_i is not None))
        if sol_i is not None and sag_i is not None:
            lay.alpha_composite(self.kurdele())

    def _reveal(self, i: int) -> float:
        return self.gecis[i] + (ACILIS_ORT + ACILIS_DON * 0.6 if i == 0 else CEVIR * 0.6)

    def kapali_kitap(self, yuz: str, aktif: int, k: float = 1.0) -> tuple[Image.Image, tuple[float, float]]:
        """Kapalı kitap (döndürülmeden): dar sekmeler, sayfa bloğu (önde sağda ve altta, arkada solda ve altta), cilt,
        kapak. Döner: görüntü ve kapak resminin (PW x PH) görüntüdeki sol üst köşesi."""
        key = ("kapali", yuz, aktif, round(k, 3), getattr(self, "blurb", ""))
        if key in self._c:
            return self._c[key]
        kal = 22
        pad_t, pad = 100, 26
        cw, ch = PW + BOARD, PH + 16
        Wc, Hc = (cw + kal + 2 * pad) * k, (ch + kal + pad_t + pad) * k
        pen = K.Pen(0, 0, Wc / k, Hc / k, ss=max(2, round(SS * k + 0.4)))
        on = yuz == "on"
        bx, by = (pad, pad_t) if on else (pad + kal, pad_t)     # cilt kutusu
        # sekmeler (cildin arkasında)
        n = len(self.sekme_adlari)
        sx0, sx1 = (bx + 40, bx + cw - 12) if on else (bx + 12, bx + cw - 40)
        sw_ = (sx1 - sx0 - 8 * (n - 1)) / n
        for i in range(n):
            dur = "bitti" if i < aktif else ("aktif" if i == aktif else "sonra")
            h = 60 + (16 if dur == "aktif" else 0)
            bg, fg = {"bitti": (RED, OFF), "aktif": (YELLOW, INK), "sonra": (PAPER, DGREY)}[dur]
            x = sx0 + i * (sw_ + 8)
            top = by + 8 - h
            pen.rr((x + 5, top + 6, x + sw_ + 5, by + 40), 9, fill=INK)
            pen.rr((x, top, x + sw_, by + 40), 9, fill=bg, outline=INK, width=4)
            if dur == "bitti":
                pen.svg(K.check_svg(OFF, 18), K.ICON_VB, x + sw_ / 2 - 16, top + 8, 32)
            else:
                pen.text(x + sw_ / 2, top + 42, str(i + 1), "anton", 32, fg, anchor="ms")
        # sayfa bloğu
        for q in range(4, 0, -1):
            o = kal * q / 4
            fill = SAYFA_KENAR if q % 2 else SAYFA
            if on:
                pen.rr((bx + 10, by + 6 + o * 0.5, bx + cw + o, by + ch + o * 0.6), 8, fill=fill, outline=INK, width=3)
            else:
                pen.rr((bx - o, by + 6 + o * 0.5, bx + cw - 10, by + ch + o * 0.6), 8, fill=fill, outline=INK, width=3)
        pen.rr((bx, by, bx + cw, by + ch), 14, fill=self.renk["zemin"], outline=INK, width=6)
        im = pen.im.resize((max(1, round(Wc)), max(1, round(Hc))), Image.LANCZOS)
        art = kapak_on(self.kb, self.seri, k) if on else kapak_arka(self.kb, getattr(self, "blurb", ""), k)
        ax, ay = (bx if on else bx + BOARD) * k, (by + 8) * k
        K._comp(im, art, ax, ay)
        # kapak resminin dış çizgisi (cilt çizgisinin içinde kalır)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([round(bx * k), round(by * k), round((bx + cw) * k) - 1, round((by + ch) * k) - 1],
                            radius=round(14 * k), outline=INK, width=max(3, round(6 * k)))
        self._c[key] = (im, (ax, ay))
        return self._c[key]

    def _kitap_pozu(self, yuz: str, aktif: int, k: float, ax: float, ay: float, rot: float, img: Image.Image,
                    kgoruntu: float | None = None, golge: bool = True) -> tuple:
        """Kapalı kitabı, kapak resminin sol üstü (ax, ay) olacak biçimde k ölçeği ve rot (derece) ile çizer."""
        kg = kgoruntu or k
        im, (cx_, cy_) = self.kapali_kitap(yuz, aktif, kg)
        if abs(k - kg) > 1e-3:
            f = k / kg
            im = im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.BILINEAR)
            cx_, cy_ = cx_ * f, cy_ * f
        # kapak resminin merkezi etrafında döndür
        pcx, pcy = cx_ + PW * k / 2, cy_ + PH * k / 2
        if abs(rot) > 0.05:
            w0, h0 = im.size
            im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
            dx, dy = (im.width - w0) / 2, (im.height - h0) / 2
            a = math.radians(rot)
            vx, vy = pcx - w0 / 2, pcy - h0 / 2
            rx, ry = vx * math.cos(a) + vy * math.sin(a), -vx * math.sin(a) + vy * math.cos(a)
            pcx, pcy = rx + w0 / 2 + dx, ry + h0 / 2 + dy
        x, y = ax + PW * k / 2 - pcx, ay + PH * k / 2 - pcy
        if golge:
            a = im.getchannel("A").point(lambda v: int(v * 0.9))
            sh = Image.new("RGBA", im.size, INK + (0,))
            sh.putalpha(a)
            K.put(img, sh, x + 12 * k, y + 14 * k, clip=CLIP)
        K.put(img, im, x, y, clip=CLIP)      # sağa kayarken sayfa bloğu x 935'i geçmesin
        return (x, y, x + im.width, y + im.height)

    # ------------------------------------------------------------ pozlar
    def kanca_pozu(self) -> tuple[float, float, float, float]:
        """Kanca karesindeki kapalı kitabın (ön kapak) kapak resmi sol üstü, ölçeği ve açısı."""
        if not hasattr(self, "_kpoz"):
            self.kanca_katmani()
            k = KAPAK_K
            top = max(self.kanca_alt + 92, 700)
            if top + PH * k + 40 > 1500:
                k = (1500 - 40 - top) / PH
            self._kpoz = (96, top, k, -2.5)
        return self._kpoz

    def son_pozu(self) -> tuple[float, float, float, float]:
        k = SON_K
        return (SON_CX - PW * k / 2, 452 + 8 * k, k, 2.0)

    # ------------------------------------------------------------ Makas
    def maskot(self, img: Image.Image, t: float, mood: str) -> None:
        cx, cy, sc = MASKOT
        mouth = K.talk_state(self.words, self.starts, t)
        blink = (t % 3.6) > 3.45 and mood not in ("happy", "surprised")
        key = (mood, mouth, blink)
        if key not in self._mascots:
            vb = MASCOT_VB
            k = sc * SS
            im = K.svg_img(K.mascot_svg(mood, mouth, blink), vb, vb[2] * k, vb[3] * k)
            self._mascots[key] = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
        im = self._mascots[key]
        bob = round(3 * math.sin(t * 2 * math.pi * 0.55))
        K.put(img, im, cx + MASCOT_VB[0] * sc, cy + (MASCOT_VB[1] - 60) * sc + bob, clip=CLIP)
        self.kayit("Makas", (cx - 125, cy - 200, cx + 125, YIGIN_Y + 98))

    def _mood(self, i: int, son: bool = False) -> str:
        b = self.bolumler[i]
        if son:
            return "happy"
        return b.mascot if b.mascot in K.MOODS else MOOD.get(b.ad, "normal")

    # ------------------------------------------------------------ kare
    def frame(self, t: float, grain: bool = True) -> Image.Image:
        self.kutular = []
        img = raf_zemini().copy()
        ev, i, lt = self.evre(t)
        getattr(self, "_kare_" + ev)(img, t, i, lt)
        if self.brand is not None:
            self.brand.watermark(img, t, 0.8 if self.intro else 0.0)
            if self.intro:
                self.brand.intro(img, t)
        return K.finish(img) if grain else img.convert("RGB")

    def _manset_koy(self, img: Image.Image, i: int, k: float = 1.0, alpha: float = 1.0) -> None:
        lay, boxes = self.manset(i)
        K.put(img, alfa(lay, alpha), 0, 230, k=k, clip=CLIP, anchor=(0.1, 0.5))
        for n, b in boxes:
            self.kayit(n, b)

    def _sekme_kutulari(self, aktif: int) -> None:
        for n, b in getattr(self.sekmeler(aktif), "kutular", []):
            self.kayit(n, b)

    def _sayfa_kutulari(self, i: int) -> None:
        ox = X_SOL
        for n, b in getattr(self.sol_sayfa(i), "kutular", []):
            self.kayit(n, (b[0] + ox, b[1] + TOP, b[2] + ox, b[3] + TOP))
        sm = self._metin.get(i)
        if sm and sm.jetonlar:
            x0, y0, x1, y1 = sm.kutu()
            self.kayit("sağ sayfa metni", (GX + TX0 + x0, TOP + TY0 + y0, GX + TX0 + x1, TOP + TY0 + y1))

    # kanca: kapalı kitap, seri etiketi, kanca başlığı, kütüphane kartı
    def _kare_kapak(self, img: Image.Image, t: float, i: int, lt: float) -> None:
        ax, ay, k, rot = self.kanca_pozu()
        self._kitap_pozu("on", 0, k, ax, ay, rot, img)
        lay, boxes, _ = self.kanca_katmani()
        kk = 1 + 0.02 * math.sin(math.pi * K.clamp(t / 0.5)) if 0 < t < 0.5 else 1.0
        K.put(img, lay, 0, SAFE[1], k=kk, clip=CLIP, anchor=(0.1, 0.2))
        for n, b in boxes:
            self.kayit(n, b)
        self.kayit("kapalı kitap", (ax, ay - 70, ax + (PW + BOARD + 22) * k, ay + PH * k + 26))
        self.maskot(img, t, self._mood(0))

    # açılış: kanca katmanı makasla kesilir, kitap yerine kayar, kapak açılır
    def _kare_acilis(self, img: Image.Image, t: float, i: int, lt: float) -> None:
        ax0, ay0, k0, r0 = self.kanca_pozu()
        p_kay = _ease((lt - ACILIS_GEC) / ACILIS_KAY)
        lay_kanca, _, hbox = self.kanca_katmani()
        ld = lt - ACILIS_ORT
        if ld < 0:      # kayma: kitap açık kitabın sağ yarısına
            ax, ay = K.lerp(ax0, GX, p_kay), K.lerp(ay0, TOP, p_kay)
            self._kitap_pozu("on", 0, K.lerp(k0, 1.0, p_kay), ax, ay, K.lerp(r0, 0.0, p_kay), img, kgoruntu=1.0)
            self.kayit("kapalı kitap", (ax, ay - 70, min(SAFE[2], ax + (PW + BOARD + 22)), ay + PH + 26))
        else:           # kapak açılır (ön yüz kapak, arka yüz giriş bölümünün sol sayfası)
            th = 180 * _ease(ld / ACILIS_DON)
            ox, oy = REGION[:2]
            lay = Image.new("RGBA", (REGION[2] - ox, REGION[3] - oy), (0, 0, 0, 0))
            if th < 90:
                self._acik_kitap(lay, None, 0, t, 0, 0.0, sekme="sag", cilt="sag")
            else:       # sol yarıya kapağın iç yüzü (sol sayfa) iner; sol cilt payı yaprak yatınca görünür
                self._acik_kitap(lay, None, 0, t, 0, 0.0, sekme="tam", cilt="tam" if th > 165 else "sag")
                self._sekme_kutulari(0)
            cevir(lay, (ox, oy), kapak_on(self.kb, self.seri, 1.0), self.sol_sayfa(0, duz=True), th, kivrim=0.0)
            img.alpha_composite(lay, (ox, oy))
            if th >= 90:
                pm = K.clamp((th - 90) / 60)
                self._manset_koy(img, 0, k=K.lerp(1.12, 1.0, K.ease_out_cubic(pm)), alpha=min(1.0, pm * 2.5))
        # kanca katmanı makasla kesilir (kart şablonunun kesmesi)
        if lt < K.CUT_LEN:
            K.card_cut(img, lay_kanca, lt, 1, origin=(0, SAFE[1]), card=hbox, x_end=SAFE[2] - 66,
                       clip_top=CLIP, clips_bot=(CLIP,))
        self.maskot(img, t, self._mood(0))

    def _kare_sayfa(self, img: Image.Image, t: float, i: int, lt: float) -> None:
        ox, oy = REGION[:2]
        lay = Image.new("RGBA", (REGION[2] - ox, REGION[3] - oy), (0, 0, 0, 0))
        self._acik_kitap(lay, i, i, t, i, i)
        img.alpha_composite(lay, (ox, oy))
        self._manset_koy(img, i)
        self._sekme_kutulari(i)
        self._sayfa_kutulari(i)
        self.maskot(img, t, self._mood(i))

    def _kare_cevir(self, img: Image.Image, t: float, i: int, lt: float) -> None:
        """Bölüm i-1'den i'ye: alttaki kitapta eski sol sayfa ve yeni sağ sayfa; dönen yaprağın ön yüzü eski sağ sayfa,
        arka yüzü yeni sol sayfa. Manşet ve sekmeler yaprak dik konumu geçince değişir."""
        ox, oy = REGION[:2]
        th = 180 * _ease(lt / CEVIR)
        cur = i if th >= 90 else i - 1
        lay = Image.new("RGBA", (REGION[2] - ox, REGION[3] - oy), (0, 0, 0, 0))
        self._acik_kitap(lay, i - 1, i, t, cur, i - 0.5)
        on = self.sag_sayfa(i - 1, self.gecis[i] - 0.001 if lt < CEVIR else t, duz=True)
        cevir(lay, (ox, oy), on, self.sol_sayfa(i, duz=True), th)
        img.alpha_composite(lay, (ox, oy))
        if th >= 90:
            pm = K.clamp((th - 90) / 60)
            self._manset_koy(img, i, k=K.lerp(1.12, 1.0, K.ease_out_cubic(pm)), alpha=min(1.0, pm * 2.5))
        else:
            self._manset_koy(img, i - 1, alpha=1.0 - K.clamp((th - 60) / 30))
        self._sekme_kutulari(cur)
        self.maskot(img, t, self._mood(cur))

    def _kare_kapan(self, img: Image.Image, t: float, i: int, lt: float) -> None:
        """Kitap kapanır: sağ yarı (son sağ sayfa + arka kapak) sola kapanır, arka kapak üstte kalır; sonra kitap
        ortaya kayar ve büyür."""
        ox, oy = REGION[:2]
        prev = i - 1
        if lt < KAPAN:
            th = 180 * _ease(lt / KAPAN)
            lay = Image.new("RGBA", (REGION[2] - ox, REGION[3] - oy), (0, 0, 0, 0))
            cur = i if th >= 90 else prev
            self._acik_kitap(lay, prev, None, t, cur, prev, sekme="tam" if th < 90 else "sol", cilt="sol")
            on = self.sag_sayfa(prev, self.gecis[i] - 0.001, duz=True)
            cevir(lay, (ox, oy), on, kapak_arka(self.kb, self.blurb, 1.0), th, kivrim=0.0)
            img.alpha_composite(lay, (ox, oy))
            if th < 90:
                self._manset_koy(img, prev, alpha=1.0 - K.clamp((th - 60) / 30))
                self._sekme_kutulari(cur)
            else:
                self._seri_koy(img, alpha=K.clamp((th - 120) / 50))
        else:
            p = _ease((lt - KAPAN) / SON_KAY)
            ax1, ay1, k1, r1 = self.son_pozu()
            ax = K.lerp(X_SOL, ax1, p)
            ay = K.lerp(TOP, ay1, p)
            self._seri_koy(img)
            self._kitap_pozu("arka", len(self.bolumler) - 1, K.lerp(1.0, k1, p), ax, ay, K.lerp(0.0, r1, p), img,
                             kgoruntu=k1)
        self.maskot(img, t, self._mood(i, son=True))

    def _seri_koy(self, img: Image.Image, alpha: float = 1.0) -> None:
        lay, boxes = self.seri_katmani(60)
        K.put(img, alfa(lay, alpha), 0, 292 - 100, clip=CLIP)
        for n, b in boxes:
            self.kayit(n, (b[0], b[1] + 192, b[2], b[3] + 192))

    def _kare_son(self, img: Image.Image, t: float, i: int, lt: float) -> None:
        """Son: arka kapakta soru; OKUDUN MU? ve Yorumlara yaz. söylendikleri anda; kütüphane kartı OKUNDU MU?
        damgasıyla soldan gelir; mutlu Makas."""
        ax, ay, k, rot = self.son_pozu()
        self._seri_koy(img)
        self._kitap_pozu("arka", len(self.bolumler) - 1, k, ax, ay, rot, img)
        self.kayit("arka kapak", (ax, ay - 76 * k, ax + (PW + BOARD) * k, ay + PH * k))
        cx = ax + (PW - 36) * k / 2
        if self.blurb:
            self.kayit("arka kapak yazısı", (ax + 24 * k, ay + 120 * k, ax + (PW - 60) * k, ay + 330 * k))
        qy = ay + PH * k * 0.60
        if t >= self.t_okudun:
            q, qw, qh = etiket("OKUDUN MU?", 112, INK, YELLOW, 91, -3)
            pk = K.clamp((t - self.t_okudun) / 0.28)
            kk = 1 + 0.25 * (1 - K.ease_out_back(pk, 1.6)) if pk < 1 else 1.0
            qcx = min(cx - 6, 920 - qw / 2)
            K.put(img, q, qcx - q.width / 2, qy - q.height / 2, k=kk, clip=CLIP)
            self.kayit("okudun mu", (qcx - qw / 2, qy - qh / 2, qcx + qw / 2, qy + qh / 2))
        if t >= self.t_yorum:
            a, aw, ah = etiket("Yorumlara yaz.", 46, OFF, INK, 92, 2, font="courier")
            pk = K.clamp((t - self.t_yorum) / 0.24)
            kk = (1 + 0.2 * (1 - K.ease_out_back(pk, 1.5))) * K.cta_pulse(t - self.t_yorum)
            ycy = qy + 112
            K.put(img, a, cx + 10 - a.width / 2, ycy - a.height / 2, k=kk, clip=CLIP)
            self.kayit("yorumlara yaz", (cx + 10 - aw / 2, ycy - ah / 2, cx + 10 + aw / 2, ycy + ah / 2))
        # kütüphane kartı: OKUNDU MU? damgası
        kart, (kw, kh) = self.kutuphane_karti(470, damga="OKUNDU MU?", rot=-1.4)
        pc = _ease((t - self.t_son) / 0.35)
        kcx, kcy = 74 + kw / 2, 1520 - kh / 2
        K.put(img, kart, kcx - kart.width / 2 - 520 * (1 - pc), kcy - kart.height / 2, clip=CLIP)
        if pc >= 1:
            self.kayit("kütüphane kartı", (kcx - kw / 2, kcy - kh / 2, kcx + kw / 2, kcy + kh / 2))
        self.maskot(img, t, self._mood(i, son=True))


# ---------------------------------------------------------------- ana giriş
def render_kitap(scenes: list[R.SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
                 music: Path | None, meta: dict) -> Path:
    """Bir Kitap Bir Dakika şablonuyla videoyu kurar. Kare döngüsü, ses, kuyruk ve marka kapanışı kart şablonuyla
    ortak (kart.render_frames)."""
    return K.render_frames(scenes, words, out_mp4, voice_mp3, music,
                           lambda bcfg: KitapVideo(scenes, words, meta, bcfg), "Kitap")


def sozlesme_karti(card) -> dict:
    """pipeline'ın ortak girişinden gelen sahne kartını (sahnenin bütün alanları: kitap_bolum, sayfa_metni, vurgu,
    mascot, ...) bu çizicinin sözleşmesine çevirir: {"bolum", "sayfa", "vurgu", "mascot"} (+ "credit"). Zaten sözleşme
    biçimindeyse aynen döner."""
    c = card if isinstance(card, dict) else {}
    if "bolum" in c or "sayfa" in c:
        return dict(c)
    out = {"bolum": str(c.get("kitap_bolum") or ""), "sayfa": str(c.get("sayfa_metni") or ""),
           "vurgu": str(c.get("vurgu") or ""), "mascot": str(c.get("mascot") or "auto")}
    if c.get("credit"):
        out["credit"] = c["credit"]
    return out


def render(scenes: list[R.SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
           music: Path | None, meta: dict) -> Path:
    """Şablon kurgu modüllerinin ortak girişi (pipeline.build: shortgen/<renderer>.py render). Sahne kartları ve
    meta['kitap'] (senaryonun kitap alanı, meta['script'] içinden) sözleşmeye çevrilir, video render_kitap ile kurulur."""
    for s in scenes:
        s.card = sozlesme_karti(s.card)
    meta = dict(meta or {})
    if meta.get("kitap") is None:
        meta["kitap"] = (meta.get("script") or {}).get("kitap")
    return render_kitap(scenes, words, out_mp4, voice_mp3, music, meta)
