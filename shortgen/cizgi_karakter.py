"""Çizgi Roman şablonunun karakterleri: parametrik, kodla çizilen figürler (SVG). Claude çizim yapmaz; görünüş
kimlikten gelir ve sabittir (KADRO), sahneye göre yalnız poz, ifade ve bakış yönü değişir. Böylece aynı karakter her
panelde, her bölümde aynı görünür.

Çizim dili konsept 1'in kahramanından (elle çizilmiş çizgi roman) gelir: kalın mürekkep kenar (INK), düz renk dolgu, tek
gölge tonu, yuvarlak kalın uçlu çizgiler. Yüzler karikatürdür (nokta göz, kalın kaş, kıvrık ağız), gerçek kişiye
benzetilmez.

Koordinat: viewBox VB = (0, 0, 400, 1000). Yüz merkezi (200, 190), omuzlar y≈350, kalça y≈640, ayak tabanı y≈985.
  bust  y 30-600 arası gösterilir (belden yukarı yakın plan)
  boy   y 20-995 arası (boydan)
Kimlik, poz ve ifade anahtarları cizgi_sabit.py'dedir; buradaki tablolar her anahtarı karşılar (testler denetler).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import cizgi_sabit as CZ
from .cizgi_motor import CYAN, INK, OFF, RED, WHITE, YELLOW, hx

VB = (0, 0, 400, 1000)
BUST = (30, 600)          # bust çerçevesinin VB'deki dikey aralığı
BOY = (20, 995)
BAS_DY = 44               # baş, boyun kısa görünsün diye çizim koordinatından bu kadar aşağıda durur
SW = 6                    # ana mürekkep kenar kalınlığı (VB birimi)
ink, off, white = hx(INK), hx(OFF), hx(WHITE)


# ---------------------------------------------------------------- görünüm (enum parametreler)
@dataclass(frozen=True)
class Gorunum:
    """Bir karakterin sabit görünüşü. Renkler (r, g, b); şekiller anahtar adıdır."""
    ten: tuple                    # ten rengi
    ten_g: tuple                  # tenin gölge tonu
    sac: str                      # dalgali | kisa | topuz | yok (bere/şapka altında kısa)
    sac_renk: tuple
    sac_parlak: tuple             # saçtaki parlaklık çizgileri (okunur biçim için)
    ust: str                      # esofman | kazak | hirka | ceket | palto
    ust_renk: tuple
    ust_g: tuple                  # giysinin gölge tonu
    ust_ikinci: tuple = (250, 249, 245)   # şerit/yaka/gömlek rengi
    alt_renk: tuple = (34, 40, 58)        # pantolon
    ayakkabi: tuple = (20, 19, 19)
    sakal: str = ""               # "" | kirli (kır, kısa) | biyik
    sakal_renk: tuple = (150, 148, 145)
    gozluk: bool = False
    bere: str = ""                # "" | orgu (örgü bere) | kasket (siperli şapka)
    bere_renk: tuple = (34, 48, 86)
    bere_ikinci: tuple = (250, 249, 245)
    atki: tuple = ()              # atkı şerit renkleri (iki renk) ya da boş
    yas: str = "yetiskin"         # genc | yetiskin | olgun (kırışıklık çizgileri)
    golge: bool = False           # yüzü gölgede (kimliği belli olmayan gözcü)


LACIVERT = (32, 46, 84)
LACIVERT_G = (22, 32, 60)
KADRO: dict[str, Gorunum] = {
    # Kuzey: kısa koyu kahve dalgalı saç (siyah değil; açık kahve parlaklıklarla dalgalar telefonda okunur), açık
    # zeytin ten, lacivert antrenman üstü (fermuar + beyaz biye; kulüp forması yok)
    "kuzey": Gorunum(ten=(224, 182, 140), ten_g=(196, 150, 110), sac="dalgali", sac_renk=(74, 46, 30),
                     sac_parlak=(150, 100, 66), ust="esofman", ust_renk=LACIVERT, ust_g=LACIVERT_G,
                     ust_ikinci=(250, 249, 245), alt_renk=(26, 32, 52), yas="genc"),
    # Hasan Reis: kır kirli sakal, lacivert örgü bere, kalın lacivert kazak (balıkçı yakalı)
    "hasan": Gorunum(ten=(206, 152, 112), ten_g=(176, 122, 86), sac="kisa", sac_renk=(120, 118, 114),
                     sac_parlak=(176, 174, 170), ust="kazak", ust_renk=(40, 56, 100), ust_g=(28, 40, 74),
                     alt_renk=(52, 50, 48), sakal="kirli", sakal_renk=(146, 144, 140), bere="orgu",
                     bere_renk=(30, 42, 78), yas="olgun"),
    # Nermin: topuz koyu saç, hardal hırka (beyaz bluz üstüne)
    "nermin": Gorunum(ten=(230, 188, 152), ten_g=(204, 158, 122), sac="topuz", sac_renk=(52, 36, 30),
                      sac_parlak=(122, 88, 70), ust="hirka", ust_renk=(214, 160, 40), ust_g=(176, 126, 24),
                      ust_ikinci=(250, 249, 245), alt_renk=(70, 62, 58), yas="yetiskin"),
    # Selim Bey: gözlük, gri ceket, sarı-kırmızı atkı (arma yok), kırlaşan kısa saç
    "selim": Gorunum(ten=(232, 194, 160), ten_g=(206, 162, 128), sac="kisa", sac_renk=(92, 88, 84),
                     sac_parlak=(170, 166, 160), ust="ceket", ust_renk=(128, 130, 134), ust_g=(96, 98, 102),
                     ust_ikinci=(250, 249, 245), alt_renk=(70, 72, 78), gozluk=True,
                     atki=((252, 196, 20), (204, 26, 36)), yas="olgun"),
    # Orhan Bey: kırmızı-beyaz eşofman üstü (kollarda beyaz şerit), kırmızı kasket, bıyık
    "orhan": Gorunum(ten=(212, 160, 120), ten_g=(182, 130, 92), sac="kisa", sac_renk=(40, 34, 30),
                     sac_parlak=(110, 96, 86), ust="esofman", ust_renk=(206, 30, 38), ust_g=(160, 20, 28),
                     ust_ikinci=(250, 249, 245), alt_renk=(30, 30, 34), sakal="biyik", sakal_renk=(40, 34, 30),
                     bere="kasket", bere_renk=(206, 30, 38), bere_ikinci=(250, 249, 245), yas="yetiskin"),
    # gölgedeki not alan adam: koyu palto, kasket, yüz gölgede
    "golge": Gorunum(ten=(90, 86, 84), ten_g=(60, 58, 56), sac="kisa", sac_renk=(30, 28, 28),
                     sac_parlak=(70, 68, 66), ust="palto", ust_renk=(64, 66, 72), ust_g=(44, 46, 52),
                     alt_renk=(40, 40, 44), bere="kasket", bere_renk=(46, 46, 50), bere_ikinci=(46, 46, 50),
                     golge=True),
    # soyunma odasındaki aynı formalı çocuklar (yalnız mekân çiziminde; senaryoda kullanılmaz)
    "oyuncu": Gorunum(ten=(222, 180, 140), ten_g=(194, 148, 108), sac="kisa", sac_renk=(48, 34, 26),
                      sac_parlak=(110, 80, 60), ust="esofman", ust_renk=(250, 249, 245), ust_g=(214, 212, 206),
                      ust_ikinci=(150, 148, 145), alt_renk=(250, 249, 245), yas="genc"),
}


def _st(fill, sw=SW, extra=""):
    return f'fill="{fill}" stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round" {extra}'


def _circ(cx, cy, r):
    return f"M{cx - r:.1f},{cy:.1f} a{r},{r} 0 1 0 {2 * r},0 a{r},{r} 0 1 0 {-2 * r},0 Z"


# ---------------------------------------------------------------- el
def _el(cx, cy, rot=0.0, s=1.0, ten=(224, 182, 140), bas=True):
    """Yumruk (basit çizgi roman eli): avuç + parmak boğumları + başparmak."""
    g = f'<g transform="translate({cx:.1f} {cy:.1f}) rotate({rot:.1f}) scale({s})">'
    g += (f'<path d="M-26,-8 C-28,-28 -8,-32 6,-30 C24,-28 30,-16 28,0 C26,20 12,28 -4,28 C-20,28 -26,12 -26,-8 Z" '
          f'{_st(hx(ten), 5)}/>')
    for yy in (-14, -3, 8):
        g += f'<path d="M12,{yy} q10,2 14,7" fill="none" stroke="{ink}" stroke-width="3.5" stroke-linecap="round"/>'
    if bas:
        g += f'<path d="M-21,-6 C-35,-14 -33,-30 -19,-30 C-10,-30 -7,-21 -9,-12" {_st(hx(ten), 5)}/>'
    return g + "</g>"


def _isaret_eli(cx, cy, rot, ten):
    """Uzatılmış işaret parmaklı el (yerel +x yönünü gösterir)."""
    t = hx(ten)
    g = f'<g transform="translate({cx:.1f} {cy:.1f}) rotate({rot:.1f})">'
    g += f'<rect x="2" y="-18" width="52" height="15" rx="7.5" {_st(t, 5)}/>'
    g += f'<path d="M-22,-16 C-6,-24 14,-20 18,-4 C20,12 8,24 -8,22 C-22,20 -28,6 -22,-16 Z" {_st(t, 5)}/>'
    g += f'<path d="M0,4 q10,0 14,6 M-4,13 q8,2 12,6" fill="none" stroke="{ink}" stroke-width="3.5" stroke-linecap="round"/>'
    return g + "</g>"


# ---------------------------------------------------------------- baş
KASLAR = {
    "normal": ("M148,146 Q166,140 186,144", "M214,144 Q234,140 252,146"),
    "gulumse": ("M146,146 Q166,136 186,144", "M214,144 Q234,136 254,146"),
    "mutlu": ("M146,140 Q166,128 186,138", "M214,138 Q234,128 254,140"),
    "saskin": ("M146,126 Q166,112 186,122", "M214,122 Q234,112 254,126"),
    "endiseli": ("M146,150 Q168,146 188,132", "M212,132 Q232,146 254,150"),
    "dusunceli": ("M146,148 Q166,144 186,148", "M214,140 Q236,128 256,136"),
    "kararli": ("M146,134 Q168,138 190,150", "M210,150 Q232,138 254,134"),
}


def _agiz(ifade, ust_dudak_renk="#b84a3a"):
    ms = f'stroke="{ink}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"'
    red = hx(RED)
    if ifade == "normal":
        return f'<path d="M184,250 Q200,254 216,249" fill="none" {ms}/>'
    if ifade == "gulumse":
        return f'<path d="M178,244 Q200,262 224,242" fill="none" {ms}/>'
    if ifade == "mutlu":
        d = "M170,238 Q200,246 230,238 Q226,276 200,278 Q174,276 170,238 Z"
        return (f'<path d="{d}" fill="{ink}" {ms}/>'
                f'<path d="M176,246 Q200,264 224,246 Q216,272 200,272 Q184,272 176,246 Z" fill="{red}"/>'
                f'<path d="M172,240 Q200,248 228,240 L226,248 Q200,256 174,248 Z" fill="{white}"/>')
    if ifade == "saskin":
        return (f'<ellipse cx="200" cy="254" rx="13" ry="18" fill="{ink}" {ms}/>'
                f'<ellipse cx="200" cy="262" rx="7" ry="6" fill="{red}"/>')
    if ifade == "endiseli":
        return f'<path d="M178,254 q8,-8 15,0 t15,0 t15,0" fill="none" {ms}/>'
    if ifade == "dusunceli":
        return f'<path d="M184,252 Q202,250 218,240" fill="none" {ms}/>'
    if ifade == "kararli":
        return (f'<path d="M180,248 Q202,256 224,244" fill="none" {ms}/>'
                f'<path d="M224,244 l6,-4" fill="none" {ms}/>')
    return ""


def _gozler(ifade, bx, by):
    out = ""
    for gx in (166, 234):
        cx, cy = gx + bx * 8, 189 + by * 6
        if ifade == "mutlu":
            out += (f'<path d="M{gx - 13},194 Q{gx},176 {gx + 13},194" fill="none" stroke="{ink}" '
                    'stroke-width="7" stroke-linecap="round"/>')
            continue
        if ifade == "saskin":
            out += f'<ellipse cx="{gx}" cy="189" rx="15" ry="17" fill="{white}" stroke="{ink}" stroke-width="4"/>'
            out += f'<circle cx="{gx + bx * 4:.1f}" cy="{189 + by * 4:.1f}" r="5.5" fill="{ink}"/>'
            continue
        out += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8.5" fill="{ink}"/>'
        out += f'<circle cx="{cx - 3:.1f}" cy="{cy - 3.4:.1f}" r="2.8" fill="{white}"/>'
        if ifade == "endiseli":
            out += (f'<path d="M{gx - 12},202 Q{gx},207 {gx + 12},202" fill="none" stroke="{ink}" '
                    'stroke-width="3.5" stroke-linecap="round"/>')
    return out


def _sac_arka(g: Gorunum) -> str:
    """Başın arkasında kalan saç parçaları (topuz)."""
    if g.sac != "topuz":
        return ""
    c, p = hx(g.sac_renk), hx(g.sac_parlak)
    out = f'<path d="{_circ(200, 58, 44)}" {_st(c, 6)}/>'
    out += f'<path d="M172,46 Q196,24 226,40" fill="none" stroke="{p}" stroke-width="6" stroke-linecap="round"/>'
    out += f'<path d="M178,70 Q200,82 222,70" fill="none" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
    return out


def _sac_on(g: Gorunum) -> str:
    """Başın üstündeki ve alnındaki saç. Dalgalı saç: dört büyük dalga lobu + açık kahve parlaklık yayları (telefonda
    siyah bir leke gibi değil, saç gibi okunur)."""
    c, p = hx(g.sac_renk), hx(g.sac_parlak)
    if g.sac == "dalgali":
        # kafatasını saran taban + alına düşen dalgalı perçem (lobların alt kenarı yay)
        d = ("M128,170 C116,120 126,74 168,58 C196,46 236,48 258,66 C284,86 288,124 276,168 "
             "C272,140 266,124 258,114 C252,128 236,132 226,118 C216,132 196,134 188,118 "
             "C176,132 156,130 150,116 C142,128 136,148 128,170 Z")
        out = f'<path d="{d}" {_st(c, 6)}/>'
        # tepedeki dalga kıvrımları (koyu çizgi) ve parlaklıklar
        for d2 in ("M150,92 Q166,74 188,82", "M196,74 Q220,60 244,76", "M234,100 Q252,92 266,108",
                   "M160,108 Q172,98 186,104"):
            out += f'<path d="{d2}" fill="none" stroke="{p}" stroke-width="7" stroke-linecap="round"/>'
        for d2 in ("M146,112 Q154,100 168,100", "M206,100 Q222,90 238,100", "M178,92 Q190,86 200,92"):
            out += f'<path d="{d2}" fill="none" stroke="{ink}" stroke-width="3.5" stroke-linecap="round"/>'
        # şakaklarda kısa favori
        out += f'<path d="M130,160 L138,186 L146,168 Z" fill="{c}"/>'
        out += f'<path d="M270,160 L262,186 L254,168 Z" fill="{c}"/>'
        return out
    if g.sac == "topuz":
        d = ("M130,176 C118,120 140,82 200,80 C260,82 282,120 270,176 C262,146 248,124 222,116 "
             "C206,128 176,128 160,118 C146,128 136,148 130,176 Z")
        out = f'<path d="{d}" {_st(c, 6)}/>'
        out += f'<path d="M200,84 Q196,104 186,120" fill="none" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
        for d2 in ("M156,104 Q176,90 194,94", "M214,94 Q236,92 254,110"):
            out += f'<path d="{d2}" fill="none" stroke="{p}" stroke-width="6" stroke-linecap="round"/>'
        return out
    # kısa saç (bere/şapka altında yalnız ense ve şakaklar görünür)
    if g.bere:
        out = f'<path d="M132,170 C130,150 132,138 138,128 L150,128 L148,176 Z" {_st(c, 5)}/>'
        out += f'<path d="M268,170 C270,150 268,138 262,128 L250,128 L252,176 Z" {_st(c, 5)}/>'
        return out
    d = ("M130,168 C120,118 140,84 200,82 C260,84 280,118 270,168 C266,146 258,128 246,120 "
         "C228,128 176,128 156,120 C142,128 134,146 130,168 Z")
    out = f'<path d="{d}" {_st(c, 6)}/>'
    for d2 in ("M156,104 Q180,92 204,96", "M218,96 Q240,98 254,112"):
        out += f'<path d="{d2}" fill="none" stroke="{p}" stroke-width="6" stroke-linecap="round"/>'
    if g.yas == "olgun":   # şakaklarda kır
        out += f'<path d="M134,150 L140,172 M266,150 L260,172" stroke="{p}" stroke-width="6" stroke-linecap="round"/>'
    return out


def _bere(g: Gorunum) -> str:
    if g.bere == "orgu":
        c = hx(g.bere_renk)
        d = "M122,130 C118,74 156,40 200,40 C244,40 282,74 278,130 Z"
        out = f'<path d="{d}" {_st(c, 6)}/>'
        out += f'<path d="M118,112 L282,112 L284,142 L116,142 Z" {_st(c, 6)}/>'    # katlanmış kenar
        for x in range(132, 276, 16):                                             # örgü fitilleri
            out += f'<path d="M{x},118 L{x},136" stroke="{ink}" stroke-width="3" stroke-linecap="round" opacity="0.55"/>'
        for d2 in ("M150,108 Q156,80 176,66", "M200,112 L200,56", "M250,108 Q244,80 224,66"):
            out += f'<path d="{d2}" fill="none" stroke="{ink}" stroke-width="3" stroke-linecap="round" opacity="0.5"/>'
        return out
    if g.bere == "kasket":
        c, c2 = hx(g.bere_renk), hx(g.bere_ikinci)
        out = f'<path d="M124,140 C120,82 160,54 202,54 C246,54 280,84 276,140 Z" {_st(c, 6)}/>'
        out += f'<path d="M168,62 C184,56 216,56 232,62 L226,132 L174,132 Z" fill="{c2}" stroke="{ink}" stroke-width="4"/>'
        out += f'<path d="M118,130 C150,120 252,120 290,130 C300,136 302,144 290,148 C250,140 150,140 116,146 Z" {_st(c, 6)}/>'
        out += f'<circle cx="200" cy="58" r="7" fill="{c}" stroke="{ink}" stroke-width="4"/>'
        return out
    return ""


def _sakal(g: Gorunum) -> str:
    if g.sakal == "kirli":
        c = hx(g.sakal_renk)
        d = "M138,206 C142,252 170,280 200,281 C230,280 258,252 262,206 C254,236 236,250 200,252 C164,250 146,236 138,206 Z"
        out = f'<path d="{d}" fill="{c}" opacity="0.85"/>'
        out += f'<path d="M172,232 Q200,222 228,232 Q214,240 200,236 Q186,240 172,232 Z" fill="{c}"/>'   # bıyık
        # kirli sakal noktaları
        for x, y in ((150, 230), (160, 246), (176, 260), (224, 260), (240, 246), (250, 230), (192, 270), (208, 270),
                     (166, 238), (234, 238)):
            out += f'<circle cx="{x}" cy="{y}" r="2.6" fill="{ink}" opacity="0.45"/>'
        return out
    if g.sakal == "biyik":
        c = hx(g.sakal_renk)
        return (f'<path d="M168,236 Q184,222 200,230 Q216,222 232,236 Q218,242 200,238 Q182,242 168,236 Z" '
                f'{_st(c, 3)}/>')
    return ""


def _gozluk() -> str:
    out = ""
    for gx in (166, 234):
        out += (f'<rect x="{gx - 27}" y="170" width="54" height="40" rx="12" fill="{white}" fill-opacity="0.2" '
                f'stroke="{ink}" stroke-width="6"/>')
        out += (f'<path d="M{gx - 18},178 L{gx - 6},178" stroke="{white}" stroke-width="4" stroke-linecap="round" '
                'opacity="0.85"/>')
    out += f'<path d="M193,186 Q200,180 207,186" fill="none" stroke="{ink}" stroke-width="5" stroke-linecap="round"/>'
    out += f'<path d="M139,184 L126,180 M261,184 L274,180" stroke="{ink}" stroke-width="5" stroke-linecap="round"/>'
    return out


def _bas(g: Gorunum, ifade: str, bx: float, by: float, egim: float) -> str:
    ten, ten_g = hx(g.ten), hx(g.ten_g)
    out = f'<g transform="translate(0 {BAS_DY}) rotate({egim:.1f} 200 300)">'
    out += _sac_arka(g)
    for ex in (134, 266):                                       # kulaklar
        out += f'<ellipse cx="{ex}" cy="194" rx="15" ry="22" {_st(ten)}/>'
        sx = 1 if ex > 200 else -1
        out += (f'<path d="M{ex - 5 * sx},184 q{8 * sx},4 {4 * sx},16" fill="none" stroke="{ink}" stroke-width="3.5" '
                'stroke-linecap="round"/>')
    yuz = "M134,150 C134,92 266,92 266,150 L265,196 C262,248 234,278 200,278 C166,278 138,248 135,196 Z"
    out += f'<path d="{yuz}" fill="{ten}"/>'
    out += (f'<path d="M244,112 C262,132 266,160 264,196 C261,240 238,268 206,276 C236,252 252,216 251,182 '
            f'C250,152 248,130 244,112 Z" fill="{ten_g}"/>')
    out += _sakal(g) if g.sakal == "kirli" else ""
    out += f'<path d="{yuz}" fill="none" stroke="{ink}" stroke-width="{SW}" stroke-linejoin="round"/>'
    out += _sac_on(g)
    out += _bere(g)
    if g.golge:
        # yüz gölgede: şapkanın altı koyu, yalnız çene çizgisi ve not defterine bakan gözlerin parıltısı
        out += f'<path d="{yuz}" fill="{ink}" opacity="0.82"/>'
        out += f'<path d="M150,190 L182,186 M218,186 L250,190" stroke="{hx((150, 148, 145))}" stroke-width="5" stroke-linecap="round"/>'
        return out + "</g>"
    kL, kR = KASLAR.get(ifade, KASLAR["normal"])
    kas = hx(g.sac_renk) if g.sac_renk[0] > 100 else ink
    if g.bere:           # bere/şapka siperinin altında kalmasın
        kL, kR = (re.sub(r",(\d+)", lambda m: "," + str(int(m.group(1)) + 10), x) for x in (kL, kR))
    for k in (kL, kR):   # ten renkli hale: kaş saçın üstüne binse de okunur
        out += f'<path d="{k}" fill="none" stroke="{ten}" stroke-width="17" stroke-linecap="round"/>'
    for k in (kL, kR):
        out += f'<path d="{k}" fill="none" stroke="{kas}" stroke-width="10" stroke-linecap="round"/>'
        if kas != ink:
            out += f'<path d="{k}" fill="none" stroke="{ink}" stroke-width="3" stroke-linecap="round" opacity="0.5"/>'
    out += _gozler(ifade, bx, by)
    if g.gozluk:
        out += _gozluk()
    if g.yas == "olgun":    # göz kenarı ve alın çizgileri
        for d in ("M130,192 l-6,-4 M130,200 l-6,2", "M270,192 l6,-4 M270,200 l6,2", "M178,118 Q200,112 222,118"):
            out += f'<path d="{d}" fill="none" stroke="{ink}" stroke-width="3" stroke-linecap="round" opacity="0.55"/>'
    # burun
    out += (f'<path d="M203,200 Q190,224 200,229 Q206,231 211,227" fill="none" stroke="{ink}" stroke-width="5" '
            'stroke-linecap="round" stroke-linejoin="round"/>')
    if g.sakal == "biyik":
        out += _sakal(g)
    out += _agiz(ifade)
    if g.sakal == "kirli":
        out += f'<path d="M172,232 Q200,222 228,232 Q214,240 200,236 Q186,240 172,232 Z" {_st(hx(g.sakal_renk), 3)}/>'
    if ifade == "mutlu":
        for cx in (148, 252):
            out += f'<ellipse cx="{cx}" cy="230" rx="15" ry="8" fill="{hx(RED)}" opacity="0.35"/>'
    if g.yas == "genc" and ifade not in ("mutlu",):   # çil yok; yanakta hafif sıcaklık
        for cx in (150, 250):
            out += f'<ellipse cx="{cx}" cy="230" rx="13" ry="6" fill="{hx(RED)}" opacity="0.14"/>'
    if ifade in ("saskin", "endiseli"):               # ter damlası
        x, y = 290, 130
        out += (f'<path d="M{x},{y - 22} C{x + 12},{y - 4} {x + 12},{y + 10} {x},{y + 10} C{x - 12},{y + 10} '
                f'{x - 12},{y - 4} {x},{y - 22} Z" fill="{hx(CYAN)}" stroke="{ink}" stroke-width="4"/>')
    return out + "</g>"


# ---------------------------------------------------------------- gövde ve giysiler
GOVDE = "M62,650 L58,476 C52,404 96,354 200,344 C304,354 348,404 342,476 L338,650 Z"
OMUZ_L, OMUZ_R = (96, 392), (304, 392)


def _govde(g: Gorunum) -> str:
    u, ug, u2 = hx(g.ust_renk), hx(g.ust_g), hx(g.ust_ikinci)
    ten, ten_g = hx(g.ten), hx(g.ten_g)
    out = ""
    # boyun
    out += f'<path d="M176,270 L176,360 L224,360 L224,270 Z" {_st(ten)}/>'
    out += f'<path d="M178,300 Q200,326 222,300 L222,336 L178,336 Z" fill="{ten_g}"/>'
    if g.ust == "hirka":     # bluz (V yakanın içinde)
        out += f'<path d="M150,350 L250,350 L238,470 L162,470 Z" {_st(u2)}/>'
        out += f'<path d="M176,348 L200,372 L224,348" fill="none" stroke="{ink}" stroke-width="5" stroke-linejoin="round"/>'
    out += f'<path d="{GOVDE}" fill="{u}"/>'
    out += f'<path d="M290,368 C330,392 344,430 340,476 L336,650 L300,650 C304,560 306,440 290,368 Z" fill="{ug}"/>'
    if g.ust == "esofman":
        # fermuar, dik yaka, omuzdan inen beyaz biye
        out += f'<path d="M200,350 L200,650" stroke="{ink}" stroke-width="5"/>'
        out += f'<path d="M200,360 L200,650" stroke="{u2}" stroke-width="2" stroke-dasharray="6 6"/>'
        out += (f'<path d="M150,346 C160,330 240,330 250,346 L238,372 C224,362 176,362 162,372 Z" {_st(u, 5)}/>')
        out += f'<path d="M200,350 L200,368" stroke="{ink}" stroke-width="5"/>'
        out += f'<rect x="194" y="368" width="12" height="20" rx="3" fill="{hx((200, 200, 204))}" stroke="{ink}" stroke-width="3"/>'
        for x0, x1 in ((112, 72), (288, 328)):
            out += f'<path d="M{x0 + (8 if x0 < 200 else -8)},360 C{x0},380 {x1 + (10 if x1 < 200 else -10)},420 {x1},470" fill="none" stroke="{u2}" stroke-width="7" stroke-linecap="round"/>'
    elif g.ust == "kazak":
        # balıkçı yaka (rulo) ve örgü desenleri
        out += f'<path d="M150,330 C150,310 250,310 250,330 L252,370 C230,384 170,384 148,370 Z" {_st(u, 6)}/>'
        for x in range(160, 246, 14):
            out += f'<path d="M{x},336 L{x},372" stroke="{ug}" stroke-width="4" stroke-linecap="round"/>'
        for x in (130, 200, 270):     # örgü (saç örgüsü deseni)
            for y in range(410, 650, 34):
                out += (f'<path d="M{x - 12},{y} q12,14 24,0 M{x - 12},{y + 17} q12,14 24,0" fill="none" '
                        f'stroke="{ug}" stroke-width="4" stroke-linecap="round"/>')
    elif g.ust == "hirka":
        out += f'<path d="M150,350 L200,470 L250,350 L238,350 L200,440 L162,350 Z" fill="{hx(g.ust_ikinci)}"/>'
        out += f'<path d="M162,350 L200,446 L238,350" fill="none" stroke="{ink}" stroke-width="5" stroke-linejoin="round"/>'
        out += f'<path d="M200,446 L200,650" stroke="{ink}" stroke-width="5"/>'
        for y in (488, 548, 608):
            out += f'<circle cx="212" cy="{y}" r="7" fill="{hx(OFF)}" stroke="{ink}" stroke-width="3.5"/>'
        for x in (100, 300):      # örgü dokusu
            for y in range(430, 640, 40):
                out += (f'<path d="M{x - 10},{y} l10,12 l10,-12" fill="none" stroke="{ug}" stroke-width="4" '
                        'stroke-linecap="round" stroke-linejoin="round"/>')
    elif g.ust in ("ceket", "palto"):
        # gömlek, yakalar, düğmeler
        out += f'<path d="M160,350 L240,350 L226,520 L174,520 Z" fill="{u2}" stroke="{ink}" stroke-width="5"/>'
        if g.ust == "ceket":
            out += f'<path d="M190,360 L210,360 L214,470 L200,490 L186,470 Z" {_st(hx((60, 64, 80)), 4)}/>'  # kravat
        out += f'<path d="M156,348 L196,470 L188,650 L62,650 L58,476 C54,410 96,362 156,348 Z" {_st(u, 6)}/>'
        out += f'<path d="M244,348 L204,470 L212,650 L338,650 L342,476 C346,410 304,362 244,348 Z" {_st(u, 6)}/>'
        out += f'<path d="M156,348 L170,420 L148,408 L196,470" fill="none" stroke="{ink}" stroke-width="5" stroke-linejoin="round"/>'
        out += f'<path d="M244,348 L230,420 L252,408 L204,470" fill="none" stroke="{ink}" stroke-width="5" stroke-linejoin="round"/>'
        out += f'<path d="M300,368 C330,392 344,430 340,476 L336,650 L304,650 C306,560 310,440 300,368 Z" fill="{ug}"/>'
        for y in (530, 590):
            out += f'<circle cx="182" cy="{y}" r="7" fill="{ug}" stroke="{ink}" stroke-width="3.5"/>'
    out += f'<path d="{GOVDE}" fill="none" stroke="{ink}" stroke-width="{SW}" stroke-linejoin="round"/>'
    if g.atki:
        a1, a2 = hx(g.atki[0]), hx(g.atki[1])
        atki = ("M140,322 C166,356 234,356 260,322 C270,334 272,352 264,364 C236,392 164,392 136,364 "
                "C128,352 130,334 140,322 Z")
        out += f'<path d="{atki}" {_st(a1)}/>'
        out += f'<path d="M150,348 C176,368 224,368 250,348" fill="none" stroke="{a2}" stroke-width="12"/>'
        kuyruk = "M214,366 L252,520 L216,530 L194,374 Z"
        out += f'<path d="{kuyruk}" {_st(a1)}/>'
        for t in (0.35, 0.62):    # kırmızı şeritler
            x0, y0 = 214 + (252 - 214) * t, 366 + (520 - 366) * t
            x1, y1 = 194 + (216 - 194) * t, 374 + (530 - 374) * t
            out += f'<path d="M{x0:.1f},{y0:.1f} L{x1:.1f},{y1:.1f}" stroke="{a2}" stroke-width="16"/>'
        out += f'<path d="{kuyruk}" fill="none" stroke="{ink}" stroke-width="5" stroke-linejoin="round"/>'
        for i in range(5):
            out += f'<path d="M{218 + i * 8:.1f},{528 - i * 2.4:.1f} l2,14" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
    return out


def _bacaklar(g: Gorunum, sut: bool) -> str:
    """Pantolon ve ayakkabılar (boydan çerçevede görünür). sut: sol bacak (izleyicinin sağı) topa vurur."""
    a, sh = hx(g.alt_renk), hx(g.ayakkabi)
    out = ""
    if not sut:
        for x0 in (110, 206):
            out += f'<path d="M{x0},640 L{x0 + 84},640 L{x0 + 80},955 L{x0 + 6},955 Z" {_st(a)}/>'
            out += f'<path d="M{x0 - 6},950 C{x0 - 6},934 {x0 + 86},934 {x0 + 92},952 L{x0 + 92},982 L{x0 - 8},982 Z" {_st(sh, 5)}/>'
        out += f'<path d="M200,660 L200,940" stroke="{ink}" stroke-width="4"/>'
        return out
    # destek bacağı (izleyicinin solu) düz, vuran bacak öne-yukarı uzanır
    out += f'<path d="M112,632 L196,640 L170,950 L96,948 Z" {_st(a)}/>'
    out += f'<path d="M86,944 C86,928 170,928 176,946 L176,976 L82,976 Z" {_st(sh, 5)}/>'
    out += f'<path d="M84,970 L178,970" stroke="{white}" stroke-width="4"/>'
    leg = "M206,636 L292,628 L380,790 L320,826 Z"
    out += f'<path d="{leg}" {_st(a)}/>'
    out += (f'<g transform="rotate(-28 352 812)"><path d="M300,796 C300,780 392,778 400,800 L400,830 L296,830 Z" '
            f'{_st(sh, 5)}/><path d="M298,824 L400,824" stroke="{white}" stroke-width="4"/></g>')
    return out


# ---------------------------------------------------------------- kollar (pozlar)
def _kol(g: Gorunum, pts, w=46) -> str:
    """Omuzdan dirseğe, dirsekten bileğe kol: önce kalın mürekkep, sonra giysi rengi (iki geçişli çizgi)."""
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    out = (f'<path d="{d}" fill="none" stroke="{ink}" stroke-width="{w + 2 * SW}" stroke-linecap="round" '
           'stroke-linejoin="round"/>')
    out += (f'<path d="{d}" fill="none" stroke="{hx(g.ust_renk)}" stroke-width="{w}" stroke-linecap="round" '
            'stroke-linejoin="round"/>')
    if g.ust == "esofman":    # kolda beyaz şerit (biye)
        out += (f'<path d="{d}" fill="none" stroke="{hx(g.ust_ikinci)}" stroke-width="6" stroke-linecap="round" '
                'stroke-linejoin="round" transform="translate(0 -12)" opacity="0.95"/>')
    return out


def _kartvizit(x, y, rot, renk1, renk2):
    g = f'<g transform="translate({x} {y}) rotate({rot})">'
    g += f'<rect x="-46" y="-30" width="92" height="60" rx="6" fill="{off}" stroke="{ink}" stroke-width="5"/>'
    g += f'<rect x="-46" y="-30" width="92" height="18" fill="{hx(renk1)}" stroke="{ink}" stroke-width="5"/>'
    g += f'<rect x="-40" y="-26" width="24" height="10" fill="{hx(renk2)}"/>'
    for yy in (0, 12):
        g += f'<path d="M-34,{yy} L{30 if yy == 0 else 14},{yy}" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
    return g + "</g>"


def _defter(x, y, rot, s=1.0):
    g = f'<g transform="translate({x} {y}) rotate({rot}) scale({s})">'
    g += f'<rect x="-50" y="-64" width="100" height="128" rx="6" fill="{hx((60, 64, 80))}" stroke="{ink}" stroke-width="5"/>'
    g += f'<rect x="-42" y="-56" width="86" height="114" rx="3" fill="{off}" stroke="{ink}" stroke-width="3"/>'
    for yy in range(-38, 50, 16):
        g += f'<path d="M-32,{yy} L32,{yy}" stroke="{hx((150, 170, 190))}" stroke-width="3"/>'
    for yy in (-38, -22, -6):
        g += f'<path d="M-30,{yy - 4} q14,-6 22,0 t22,0" fill="none" stroke="{ink}" stroke-width="3" stroke-linecap="round"/>'
    return g + "</g>"


def _top(cx, cy, r):
    out = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{white}" stroke="{ink}" stroke-width="5"/>'
    pent = []
    for i in range(5):
        a = math.radians(-90 + i * 72)
        pent.append(f"{cx + math.cos(a) * r * 0.36:.1f},{cy + math.sin(a) * r * 0.36:.1f}")
    out += f'<path d="M{" L".join(pent)} Z" fill="{ink}"/>'
    for i in range(5):
        a = math.radians(-90 + i * 72)
        x0, y0 = cx + math.cos(a) * r * 0.36, cy + math.sin(a) * r * 0.36
        x1, y1 = cx + math.cos(a) * r * 0.95, cy + math.sin(a) * r * 0.95
        out += f'<path d="M{x0:.1f},{y0:.1f} L{x1:.1f},{y1:.1f}" stroke="{ink}" stroke-width="4"/>'
    return out


def _telefon(x, y, rot):
    g = f'<g transform="translate({x} {y}) rotate({rot})">'
    g += f'<rect x="-18" y="-40" width="36" height="80" rx="8" fill="{ink}" stroke="{ink}" stroke-width="4"/>'
    g += f'<rect x="-12" y="-32" width="24" height="56" rx="3" fill="{hx(CYAN)}"/>'
    return g + "</g>"


def _ag(g: Gorunum):
    """İki elle tutulan balık ağı: göğüs hizasında sarkan ağ gözleri ve turuncu mantar şamandıralar."""
    out = ""
    net = "M86,520 C120,500 280,500 318,520 L330,650 L74,650 Z"
    mesh = ""
    for k in range(-6, 14):
        x = 74 + k * 26
        mesh += f"M{x},520 L{x + 130},650 M{x + 130},520 L{x},650 "
    out += (f'<clipPath id="agk"><path d="{net}"/></clipPath><g clip-path="url(#agk)">'
            f'<path d="{mesh}" stroke="{hx((60, 72, 70))}" stroke-width="4"/></g>')
    out += f'<path d="M86,520 C120,500 280,500 318,520" fill="none" stroke="{hx((214, 196, 150))}" stroke-width="10" stroke-linecap="round"/>'
    out += f'<path d="M86,520 C120,500 280,500 318,520" fill="none" stroke="{ink}" stroke-width="3" stroke-dasharray="10 10"/>'
    for x in (140, 200, 260):
        out += f'<ellipse cx="{x}" cy="{510 if x == 200 else 512}" rx="16" ry="11" fill="{hx((236, 120, 40))}" stroke="{ink}" stroke-width="4"/>'
    return out


def _kollar(g: Gorunum, poz: str) -> tuple[str, str]:
    """(arkada kalan, önde kalan) SVG: kollar, eller ve eldeki nesneler."""
    t = g.ten
    L, R = OMUZ_L, OMUZ_R
    if poz == "dur":
        return "", (_kol(g, [L, (72, 500), (80, 600)]) + _kol(g, [R, (328, 500), (320, 600)])
                    + _el(80, 618, 90, ten=t) + _el(320, 618, 90, ten=t))
    if poz == "kartvizit":
        out = _kol(g, [L, (70, 500), (84, 600)]) + _el(84, 618, 90, ten=t)
        out += _kol(g, [R, (318, 500), (246, 444)])
        out += _kartvizit(222, 392, -14, (252, 196, 20), (204, 26, 36))
        out += _kartvizit(262, 380, 12, (206, 30, 38), (250, 249, 245))
        out += _el(240, 448, 160, ten=t)
        return "", out
    if poz == "ag":
        out = _kol(g, [L, (84, 470), (118, 512)]) + _kol(g, [R, (316, 470), (282, 512)])
        out += _ag(g)
        out += _el(122, 514, 20, ten=t) + _el(278, 514, 160, ten=t)
        return "", out
    if poz == "top":
        out = _kol(g, [L, (80, 480), (140, 520)]) + _kol(g, [R, (320, 480), (260, 520)])
        out += _top(200, 500, 62)
        out += _el(146, 520, 20, ten=t) + _el(254, 520, 160, ten=t)
        return "", out
    if poz == "sut":
        return "", (_kol(g, [L, (30, 440), (-6, 520)]) + _el(-10, 532, 120, ten=t)
                     + _kol(g, [R, (360, 360), (392, 300)]) + _el(392, 286, -70, ten=t))
    if poz == "sevinc":
        return "", (_kol(g, [L, (52, 300), (40, 200)]) + _el(40, 182, -90, ten=t)
                    + _kol(g, [R, (348, 300), (360, 200)]) + _el(360, 182, -90, ten=t))
    if poz == "not":
        out = _kol(g, [L, (74, 500), (150, 486)])
        out += _defter(186, 470, -8)
        out += _el(150, 494, 0, ten=t)
        out += _kol(g, [R, (330, 500), (236, 468)])
        out += (f'<path d="M226,440 L196,476" stroke="{ink}" stroke-width="12" stroke-linecap="round"/>'
                f'<path d="M226,440 L198,474" stroke="{hx(YELLOW)}" stroke-width="6" stroke-linecap="round"/>')
        out += _el(236, 466, 200, s=0.9, ten=t)
        return "", out
    if poz == "telefon":
        out = _kol(g, [L, (72, 500), (80, 600)]) + _el(80, 618, 90, ten=t)
        out += _kol(g, [R, (338, 440), (290, 316)])
        out += _telefon(274, 256, 18)
        out += _el(288, 306, -100, ten=t)
        return "", out
    if poz == "isaret":
        out = _kol(g, [L, (72, 500), (80, 600)]) + _el(80, 618, 90, ten=t)
        out += _kol(g, [R, (372, 400), (430, 380)])
        out += _isaret_eli(436, 384, -12, t)
        return "", out
    if poz == "cene":
        out = _kol(g, [L, (72, 500), (80, 600)]) + _el(80, 618, 90, ten=t)
        out += _kol(g, [R, (300, 530), (232, 346)]) + _el(228, 334, -80, s=1.05, ten=t)
        return "", out
    if poz == "kollar":
        out = _kol(g, [L, (84, 480), (250, 470)]) + _kol(g, [R, (316, 470), (150, 466)])
        out += _el(262, 466, 0, ten=t) + _el(140, 462, 180, ten=t)
        return "", out
    return "", ""


# ---------------------------------------------------------------- dış arayüz
YONLER = ("sol", "sag")


def figur_svg(kid: str, poz: str = "dur", ifade: str = "normal", yon: str = "sag") -> str:
    """Karakterin SVG gövdesi (viewBox VB). yon: karakterin baktığı taraf (sag: izleyicinin sağına). Aynı girdi her
    zaman aynı çıktıyı verir. Bilinmeyen poz/ifade varsayılana döner."""
    g = KADRO.get(kid) or KADRO["kuzey"]
    poz = poz if poz in CZ.POZLAR else "dur"
    ifade = ifade if ifade in CZ.IFADELER else "normal"
    if poz == "sut":
        yon = "sag"       # solak: vuran bacak karakterin sol bacağıdır, aynalanırsa sağ ayak olurdu
    bx = 0.6              # sola bakan figür aşağıda aynalanır: göz bebekleri de onunla döner
    by = 0.5 if poz in ("not", "ag", "kartvizit", "top") else (-0.4 if poz == "sevinc" else 0.0)
    egim = {"cene": -6.0, "dusunceli": 4.0}.get(poz, 0.0)
    if poz == "sut":
        egim = -8.0
    arka, on = _kollar(g, poz)
    body = arka + _bacaklar(g, poz == "sut") + _govde(g) + _bas(g, ifade, bx, by, egim) + on
    if poz == "sut":
        body += _top(394, 742, 40)
        for k, (x0, y0) in enumerate(((330, 700), (318, 738), (330, 776))):
            body += f'<path d="M{x0},{y0} l-46,{(k - 1) * 8}" stroke="{ink}" stroke-width="6" stroke-linecap="round"/>'
    # karakter sağa bakarken saçın/kolların asimetrisi doğal görünsün diye figür sola bakınca aynalanır
    if yon == "sol":
        body = f'<g transform="translate(400 0) scale(-1 1)">{body}</g>'
    return body


def gorunum_metni(kid: str) -> str:
    """Yazara (istem) giden tek görünüm metni (cizgi_sabit.KARAKTERLER)."""
    return CZ.KARAKTERLER.get(kid, "")
