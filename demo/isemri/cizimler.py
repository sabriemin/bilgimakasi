"""İş Emri şablonunun örnek videosu (demo/isemri/kursun_kalem.json) için elle çizilmiş SVG çizimler.

Gerçek üretimde sahne çizimleri illustrate.py'den gelir; bu dosya yalnız örnek videonun çizimlerini PNG olarak yazar.
Makineler fabrika ekipmanı gibi okunur: çelik şase ve I-profil ayaklar, cıvatalı flanşlar, ray ve konveyör makaraları,
ikaz şeritli kaideler, borular, ibreli göstergeler (mutfak aleti ya da ev eşyası gibi değil).

    python demo/isemri/cizimler.py        # demo/isemri/*.png dosyalarını yeniden yazar
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cairosvg

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK.parents[1]))

from shortgen.isemri import (AHSAP, AHSAP_K, AHSAP_KK, CELIK, CELIK_A, CELIK_K, GRAFIT, GRAFIT_A, YESIL,  # noqa: E402
                             civata_svg, ikaz_svg, makine_p as _p, makine_poly as _poly)
from shortgen import kart as K  # noqa: E402

hx = K._hex
I = hx(K.INK)
RED, YELLOW, OFF, INK = K.RED, K.YELLOW, K.OFF, K.INK
TUGLA, TUGLA_K = (170, 72, 50), (128, 50, 36)
KOR = (240, 138, 28)


def yaz(ad: str, vb, govde: str, en: int = 1400) -> None:
    boy = int(round(en * vb[3] / vb[2]))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb[0]} {vb[1]} {vb[2]} {vb[3]}" '
           f'width="{vb[2]}" height="{vb[3]}">{govde}</svg>')
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(KOK / ad), output_width=en, output_height=boy)
    print("yazıldı:", KOK / ad)


# ---------------------------------------------------------------- kanca: kırık kurşun kalem
def kalem() -> str:
    y0, y1, yc = 90, 170, 130
    o = f'<ellipse cx="420" cy="196" rx="390" ry="9" fill="{I}" opacity="0.18"/>'
    core = 9
    o += _p(_poly([(370, yc - core), (404, yc - core), (398, yc - 2), (410, yc + 3), (402, yc + core),
                   (370, yc + core)]), GRAFIT, 5)
    o += _p(_poly([(470, yc - core), (436, yc - core), (444, yc - 3), (432, yc + 2), (440, yc + core),
                   (470, yc + core)]), GRAFIT, 5)
    o += _p(_poly([(22, yc), (78, yc - 15), (78, yc + 15)]), GRAFIT, 6)
    koni = (f"M78 {yc - 15} L184 {y0} Q172 {y0 + 13} 184 {y0 + 27} Q172 {yc} 184 {y1 - 27} Q172 {y1 - 13} 184 {y1} "
            f"L78 {yc + 15} Z")
    o += _p(koni, AHSAP, 6)
    kir_sol = [(380, y0), (372, y0 + 16), (386, y0 + 30), (376, y0 + 46), (390, y0 + 60), (378, y1)]
    o += _govde(184, kir_sol, y0, y1, sol=True)
    kir_sag = [(452, y0), (442, y0 + 18), (456, y0 + 34), (444, y0 + 50), (458, y0 + 66), (448, y1)]
    o += _govde(None, kir_sag, y0, y1, sol=False, x_son=690)
    o += _p(f"M690 {y0 - 4} L752 {y0 - 4} L752 {y1 + 4} L690 {y1 + 4} Z", CELIK_A, 6)
    for x in (704, 718, 738):
        o += f'<path d="M{x} {y0} L{x} {y1}" stroke="{I}" stroke-width="4"/>'
    o += _p(f"M752 {y0} L790 {y0} Q812 {y0} 812 {yc} Q812 {y1} 790 {y1} L752 {y1} Z", RED, 6)
    o += (f'<path d="M760 {y0 + 12} L790 {y0 + 12}" stroke="#ffffff" stroke-width="6" opacity="0.6" '
          'stroke-linecap="round"/>')
    return o


def _kx(kirik, y):
    for (xa, ya), (xb, yb) in zip(kirik, kirik[1:]):
        if ya <= y <= yb:
            return xa + (xb - xa) * (y - ya) / max(1e-6, yb - ya)
    return kirik[-1][0]


def _govde(x_bas, kirik, y0, y1, sol=True, x_son=None):
    """Altıgen kalem gövdesi yandan: açık üst yüz, sarı orta yüz, koyu alt yüz; bir ucu kırık."""
    acik, koyu = (254, 233, 120), (224, 178, 16)
    ya, yb = y0 + 22, y1 - 22
    xs = lambda y: _kx(kirik, y)  # noqa: E731
    if sol:
        dis = _poly([(x_bas, y0)] + list(kirik) + [(x_bas, y1)])
        bant = [((x_bas, y0), (xs(y0), y0), (xs(ya), ya), (x_bas, ya)),
                ((x_bas, yb), (xs(yb), yb), (xs(y1), y1), (x_bas, y1))]
        cz = [(x_bas, xs(ya)), (x_bas, xs(yb))]
    else:
        dis = _poly(list(kirik) + [(x_son, y1), (x_son, y0)])
        bant = [((xs(y0), y0), (x_son, y0), (x_son, ya), (xs(ya), ya)),
                ((xs(yb), yb), (x_son, yb), (x_son, y1), (xs(y1), y1))]
        cz = [(xs(ya), x_son), (xs(yb), x_son)]
    o = f'<path d="{dis}" fill="{hx(YELLOW)}"/>'
    o += f'<path d="{_poly(bant[0])}" fill="{hx(acik)}"/><path d="{_poly(bant[1])}" fill="{hx(koyu)}"/>'
    for (xa, xb), y in zip(cz, (ya, yb)):
        o += f'<path d="M{xa} {y} L{xb} {y}" stroke="{I}" stroke-width="3.5"/>'
    o += _p(dis, None, 6)
    x_a, x_b = (200, 330) if sol else (480, 660)
    o += (f'<path d="M{x_a} {y0 + 11} L{x_b} {y0 + 11}" stroke="#ffffff" stroke-width="5" opacity="0.7" '
          'stroke-linecap="round"/>')
    return o


# ---------------------------------------------------------------- ortak makine parçaları
def i_ayak(x, y_ust, y_alt, w=34) -> str:
    """I-profil çelik ayak + taban plakası (cıvatalı)."""
    o = _p(_poly([(x - w / 2, y_ust), (x + w / 2, y_ust), (x + w / 2, y_alt), (x - w / 2, y_alt)]), CELIK_K, 6)
    o += f'<path d="M{x} {y_ust + 6} L{x} {y_alt - 6}" stroke="{hx(CELIK)}" stroke-width="8"/>'
    o += _p(_poly([(x - w / 2 - 14, y_alt), (x + w / 2 + 14, y_alt), (x + w / 2 + 14, y_alt + 12),
                   (x - w / 2 - 14, y_alt + 12)]), CELIK, 5)
    return o


def zemin(x0, x1, y) -> str:
    return (f'<path d="M{x0} {y} L{x1} {y}" stroke="{I}" stroke-width="8" stroke-linecap="round"/>'
            f'<rect x="{x0 + 20}" y="{y + 6}" width="{x1 - x0 - 40}" height="10" fill="{I}" opacity="0.15"/>')


def konveyor(x0, x1, y, n=None, r=13) -> str:
    """Makaralı konveyör: üstte bant, altta makaralar, iki ayak."""
    o = i_ayak(x0 + 40, y + 20, y + 120, 26) + i_ayak(x1 - 40, y + 20, y + 120, 26)
    o += _p(_poly([(x0, y), (x1, y), (x1, y + 34), (x0, y + 34)]), CELIK_K, 6)
    n = n or max(3, int((x1 - x0) / 46))
    for k in range(n):
        cx = x0 + 22 + (x1 - x0 - 44) * k / max(1, n - 1)
        o += f'<circle cx="{cx:.1f}" cy="{y + 17}" r="{r}" fill="{hx(CELIK_A)}" stroke="{I}" stroke-width="4"/>'
        o += f'<circle cx="{cx:.1f}" cy="{y + 17}" r="3.5" fill="{I}"/>'
    o += f'<path d="M{x0} {y} L{x1} {y}" stroke="{I}" stroke-width="7" stroke-linecap="round"/>'
    return o


def gosterge_k(cx, cy, r, aci=-40) -> str:
    """Küçük ibreli manometre (makinenin üstünde)."""
    a = math.radians(aci - 90)
    o = f'<circle cx="{cx}" cy="{cy}" r="{r + 6}" fill="{hx(CELIK_K)}" stroke="{I}" stroke-width="5"/>'
    o += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{hx(OFF)}" stroke="{I}" stroke-width="4"/>'
    for k in range(7):
        b = math.radians(-225 + 45 * k)
        o += (f'<path d="M{cx + (r - 4) * math.cos(b):.1f} {cy + (r - 4) * math.sin(b):.1f} '
              f'L{cx + (r - 11) * math.cos(b):.1f} {cy + (r - 11) * math.sin(b):.1f}" stroke="{I}" stroke-width="3"/>')
    o += (f'<path d="M{cx} {cy} L{cx + (r - 8) * math.cos(a):.1f} {cy + (r - 8) * math.sin(a):.1f}" '
          f'stroke="{hx(RED)}" stroke-width="5" stroke-linecap="round"/>')
    o += f'<circle cx="{cx}" cy="{cy}" r="5" fill="{I}"/>'
    return o


def boru(pts, w=16, col=CELIK) -> str:
    d = "M" + " L".join(f"{x} {y}" for x, y in pts)
    return (f'<path d="{d}" fill="none" stroke="{I}" stroke-width="{w + 10}" stroke-linejoin="round" '
            f'stroke-linecap="round"/><path d="{d}" fill="none" stroke="{hx(col)}" stroke-width="{w}" '
            'stroke-linejoin="round" stroke-linecap="round"/>')


# ---------------------------------------------------------------- aşama 1: karıştırıcı + ekstrüzyon presi
def pres() -> str:
    o = zemin(20, 980, 470)
    # karıştırıcı kazan (solda, yüksek): çelik tank, üstte motor, gövdede gözetleme penceresi
    o += i_ayak(70, 300, 458, 26) + i_ayak(220, 300, 458, 26)
    o += _p("M40 150 L250 150 L250 300 Q250 330 220 340 L170 356 L120 356 L70 340 Q40 330 40 300 Z", CELIK, 7)
    o += _p("M30 136 L260 136 L260 158 L30 158 Z", CELIK_K, 6)
    for x in (46, 96, 146, 196, 244):
        o += civata_svg(x, 147, 6)
    o += _p("M104 80 L186 80 L186 136 L104 136 Z", CELIK_K, 6)   # motor
    for y in (90, 102, 114, 126):
        o += f'<path d="M110 {y} L180 {y}" stroke="{I}" stroke-width="3"/>'
    o += _p("M136 52 L154 52 L154 80 L136 80 Z", CELIK, 5)
    o += _p("M88 196 L202 196 L202 270 L88 270 Z", (60, 62, 66), 6)   # pencere: koyu karışım
    o += f'<path d="M96 236 Q120 222 146 236 T196 232 L196 262 L96 262 Z" fill="{hx(GRAFIT)}"/>'
    o += '<path d="M100 214 L134 204" stroke="#ffffff" stroke-width="5" opacity="0.5" stroke-linecap="round"/>'
    # kazandan prese boru
    o += boru([(145, 356), (145, 400), (300, 400), (300, 250), (340, 250)], 22)
    # ekstrüzyon presi: hidrolik silindir (kırmızı) + piston + namlu (flanşlı) + kalıp
    o += i_ayak(420, 318, 458) + i_ayak(700, 318, 458)
    o += _p("M330 300 L880 300 L880 318 L330 318 Z", CELIK_K, 6)            # şase kirişi
    o += _p("M340 196 L470 196 L470 296 L340 296 Z", RED, 7)                # hidrolik silindir
    o += _p("M340 196 L470 196 L470 214 L340 214 Z", (176, 22, 28), 5)
    for y in (210, 282):
        o += civata_svg(352, y, 6) + civata_svg(458, y, 6)
    o += _p("M470 230 L520 230 L520 262 L470 262 Z", CELIK_A, 5)            # piston kolu
    o += _p("M520 178 L800 178 L800 314 L520 314 Z", CELIK, 7)              # namlu
    for x in (520, 610, 700, 790):                                          # flanşlar
        o += _p(f"M{x - 8} 168 L{x + 14} 168 L{x + 14} 324 L{x - 8} 324 Z", CELIK_K, 5)
        for y in (182, 246, 310):
            o += civata_svg(x + 3, y, 5)
    o += _p("M560 130 L660 130 L640 178 L580 178 Z", CELIK_A, 6)            # besleme ağzı
    o += f'<path d="M574 142 L646 142" stroke="{hx(GRAFIT)}" stroke-width="12"/>'
    o += gosterge_k(745, 140, 26, 30) + f'<path d="M745 172 L745 178" stroke="{I}" stroke-width="7"/>'
    o += _p("M800 210 L846 222 L846 270 L800 282 Z", CELIK_K, 6)            # kalıp
    # çıkan grafit çubuklar konveyörün üstünde
    o += konveyor(830, 980, 300, n=4, r=11)
    for k, y in enumerate((232, 246, 260)):
        o += (f'<path d="M846 {y} L{960 + 6 * k} {y + 52 - k * 0}" stroke="{I}" stroke-width="12" '
              'stroke-linecap="round"/>')
        o += (f'<path d="M846 {y} L{960 + 6 * k} {y + 52}" stroke="{hx(GRAFIT_A)}" stroke-width="5" '
              'stroke-linecap="round"/>')
    # ikaz şeritli kaide
    o += ikaz_svg(330, 440, 560, 18, 14)
    return o


# ---------------------------------------------------------------- aşama 2: tünel fırın (tuğla, ray, vagon, baca)
def firin() -> str:
    o = zemin(10, 990, 470)
    # baca
    o += _p("M770 20 L830 20 L842 150 L758 150 Z", TUGLA, 7)
    for y in (48, 86, 124):
        o += _p(f"M{764 - (y - 20) * 0.08:.1f} {y} L{836 + (y - 20) * 0.08:.1f} {y} L{837 + (y - 20) * 0.08:.1f} "
                f"{y + 10} L{763 - (y - 20) * 0.08:.1f} {y + 10} Z", CELIK_K, 4)
    for k, x in enumerate((786, 808)):
        o += (f'<path d="M{x} {6 - 6 * k} q-10 -12 0 -24" stroke="{hx(CELIK_A)}" stroke-width="10" fill="none" '
              'stroke-linecap="round" opacity="0.9"/>')
    # fırın gövdesi: uzun, alçak tuğla blok; çelik bağlantı kuşakları
    o += _p("M160 150 L960 150 L960 440 L160 440 Z", TUGLA, 8)
    for r, y in enumerate(range(166, 432, 26)):     # tuğla dokusu
        o += f'<path d="M166 {y} L954 {y}" stroke="{hx(TUGLA_K)}" stroke-width="3"/>'
        for x in range(180 + (24 if r % 2 else 0), 950, 48):
            o += f'<path d="M{x} {y - 26 + 3} L{x} {y}" stroke="{hx(TUGLA_K)}" stroke-width="3"/>'
    o += _p("M146 132 L974 132 L974 158 L146 158 Z", CELIK_K, 6)            # üst kiriş
    for x in (160, 420, 680, 946):                                         # dikey çelik kuşaklar
        o += _p(f"M{x - 12} 150 L{x + 12} 150 L{x + 12} 440 L{x - 12} 440 Z", CELIK_K, 6)
        for y in (176, 300, 420):
            o += civata_svg(x, y, 5)
    # kemerli giriş: kızgın iç, raylar içeri girer
    o += f'<path d="M190 440 L190 300 Q190 214 290 214 Q390 214 390 300 L390 440 Z" fill="{I}"/>'
    o += (f'<defs><radialGradient id="kor" cx="50%" cy="65%" r="70%"><stop offset="0%" stop-color="{hx(YELLOW)}"/>'
          f'<stop offset="55%" stop-color="{hx(KOR)}"/><stop offset="100%" stop-color="{hx(RED)}"/></radialGradient>'
          '</defs>')
    o += '<path d="M204 436 L204 302 Q204 228 290 228 Q376 228 376 302 L376 436 Z" fill="url(#kor)"/>'
    # vagon girişte: çelik vagon, üstünde pota (uçları görünen çubuklar), tekerlekler rayda
    o += f'<path d="M20 452 L980 452" stroke="{I}" stroke-width="9" stroke-linecap="round"/>'
    for x in range(30, 980, 40):
        o += f'<rect x="{x}" y="456" width="22" height="8" fill="{I}"/>'
    o += _p("M40 360 L300 360 L300 420 L40 420 Z", CELIK, 7)
    o += _p("M40 360 L300 360 L300 376 L40 376 Z", CELIK_K, 5)
    for x in (80, 260):
        o += f'<circle cx="{x}" cy="434" r="20" fill="{hx(CELIK_K)}" stroke="{I}" stroke-width="6"/>'
        o += f'<circle cx="{x}" cy="434" r="6" fill="{hx(CELIK_A)}"/>'
    o += _p("M66 252 L274 252 L274 360 L66 360 Z", (214, 206, 192), 7)       # seramik pota
    for r in range(3):
        for c in range(7):
            cx, cy = 90 + c * 28 + (14 if r % 2 else 0), 276 + r * 30
            if cx > 262:
                continue
            o += f'<circle cx="{cx}" cy="{cy}" r="10" fill="{hx(GRAFIT)}" stroke="{I}" stroke-width="3"/>'
            o += f'<circle cx="{cx - 3}" cy="{cy - 3}" r="2.8" fill="{hx(GRAFIT_A)}"/>'
    # hareket oku: vagon fırına girer
    o += (f'<path d="M314 330 L364 330 M350 316 L366 330 L350 344" stroke="{hx(YELLOW)}" stroke-width="16" '
          'fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    o += (f'<path d="M314 330 L364 330 M350 316 L366 330 L350 344" stroke="{I}" stroke-width="5" fill="none" '
          'stroke-linecap="round" stroke-linejoin="round"/>')
    # gözetleme deliği ve brülör hattı
    for x in (520, 800):
        o += f'<circle cx="{x}" cy="300" r="22" fill="{I}"/><circle cx="{x}" cy="300" r="13" fill="url(#kor)"/>'
    o += boru([(470, 214), (560, 214), (560, 196), (900, 196)], 16, YELLOW)
    o += gosterge_k(640, 260, 32, 50)
    o += _p("M840 360 L920 360 L920 420 L840 420 Z", CELIK, 6)              # kumanda kutusu
    o += f'<circle cx="862" cy="382" r="9" fill="{hx(YESIL)}" stroke="{I}" stroke-width="3"/>'
    o += f'<circle cx="896" cy="382" r="9" fill="{hx(RED)}" stroke="{I}" stroke-width="3"/>'
    o += f'<path d="M852 404 L908 404" stroke="{I}" stroke-width="4"/>'
    return o


# ---------------------------------------------------------------- aşama 3: oluk açma (freze köprüsü + levha)
_FX0, _FX1, _FY, _DX, _DY, _T, _N, _R = 120, 640, 400, 150, -150, 56, 7, 16


def _oluk_x(i):
    return _FX0 + (i + 0.5) * (_FX1 - _FX0) / _N


def _cubuk(x, y):
    dx, dy, r = _DX, _DY, 12
    q = [(x - r, y), (x + r, y), (x + r + dx, y + dy), (x - r + dx, y + dy)]
    o = f'<path d="{_poly(q)}" fill="{hx(GRAFIT)}" stroke="{I}" stroke-width="4" stroke-linejoin="round"/>'
    o += (f'<path d="M{x - 4} {y - 6} L{x - 4 + dx} {y + dy - 6}" stroke="{hx(GRAFIT_A)}" stroke-width="4" '
          'stroke-linecap="round"/>')
    o += f'<circle cx="{x}" cy="{y}" r="{r}" fill="{hx(GRAFIT)}" stroke="{I}" stroke-width="4"/>'
    return o


def oluk() -> str:
    fx0, fx1, fy, dx, dy, t = _FX0, _FX1, _FY, _DX, _DY, _T
    o = zemin(20, 980, 540)
    # konveyör tablası
    o += _p(_poly([(fx0 - 70, fy + t + 6), (fx1 + 60, fy + t + 6), (fx1 + 60 + dx, fy + t + 6 + dy),
                   (fx0 - 70 + dx, fy + t + 6 + dy)]), CELIK, 6)
    o += _p(_poly([(fx0 - 70, fy + t + 6), (fx1 + 60, fy + t + 6), (fx1 + 60, fy + t + 40), (fx0 - 70, fy + t + 40)]),
            CELIK_K, 6)
    o += i_ayak(fx0 - 30, fy + t + 40, 528, 26) + i_ayak(fx1 + 20, fy + t + 40, 528, 26)
    o += ikaz_svg(fx0 - 70, fy + t + 40, fx1 - fx0 + 130, 14, 12)
    # levha: yan yüz, üst yüz, oluklar, ön yüz
    o += _p(_poly([(fx1, fy), (fx1 + dx, fy + dy), (fx1 + dx, fy + dy + t), (fx1, fy + t)]), AHSAP_KK, 7)
    o += _p(_poly([(fx0, fy), (fx1, fy), (fx1 + dx, fy + dy), (fx0 + dx, fy + dy)]), AHSAP, 7)
    for i in range(_N):
        x = _oluk_x(i)
        q = [(x - _R, fy), (x + _R, fy), (x + _R + dx, fy + dy), (x - _R + dx, fy + dy)]
        o += f'<path d="{_poly(q)}" fill="{hx(AHSAP_KK)}" stroke="{I}" stroke-width="3.5" stroke-linejoin="round"/>'
    d = f"M{fx0} {fy} "
    for i in range(_N):
        x = _oluk_x(i)
        d += f"L{x - _R} {fy} A{_R} {_R} 0 0 0 {x + _R} {fy} "
    d += f"L{fx1} {fy} L{fx1} {fy + t} L{fx0} {fy + t} Z"
    o += _p(d, AHSAP_K, 7)
    for k, yy in enumerate((fy + 26, fy + 42)):
        o += (f'<path d="M{fx0 + 14} {yy} Q{fx0 + 180} {yy - 7 + k * 8} {fx0 + 300} {yy} T{fx1 - 14} {yy - 2}" '
              f'stroke="{hx(AHSAP_KK)}" stroke-width="3" fill="none"/>')
    for i in range(5):
        o += _cubuk(_oluk_x(i), fy - 1)
    # freze köprüsü: iki kolon + kiriş + motorlu mil, ucunda dişli freze bıçakları (son oluklar)
    bx = _oluk_x(6) + dx * 0.5
    o += _p(_poly([(bx + 90, 60), (bx + 130, 60), (bx + 130, 330), (bx + 90, 330)]), CELIK_K, 7)   # arka kolon
    o += _p(_poly([(bx - 170, 40), (bx + 150, 40), (bx + 150, 100), (bx - 170, 100)]), YELLOW, 7)  # kiriş
    o += ikaz_svg(bx - 160, 84, 300, 12, 10)
    for x_ in (bx - 150, bx + 130):
        o += civata_svg(x_, 58, 6)
    o += _p(_poly([(bx - 60, 100), (bx + 20, 100), (bx + 20, 176), (bx - 60, 176)]), CELIK, 7)      # motor
    for y in (114, 128, 142, 156):
        o += f'<path d="M{bx - 52} {y} L{bx + 12} {y}" stroke="{I}" stroke-width="3"/>'
    o += _p(_poly([(bx - 30, 176), (bx - 10, 176), (bx - 10, 236), (bx - 30, 236)]), CELIK_A, 6)    # mil
    cx, cy = bx - 20, 250
    for k, (ox, oy) in enumerate(((0, 0), (-38, 30))):
        pts = []
        for j in range(14):
            a0 = 2 * math.pi * j / 14
            a1 = a0 + 2 * math.pi / 14 * 0.55
            pts += [(cx + ox + 46 * math.cos(a0), cy + oy + 46 * math.sin(a0) * 0.42),
                    (cx + ox + 58 * math.cos(a1), cy + oy + 58 * math.sin(a1) * 0.42)]
        o += _p(_poly(pts), CELIK_A, 5)
        o += _p(f"M{cx + ox - 14} {cy + oy} A14 6 0 1 0 {cx + ox + 14} {cy + oy} A14 6 0 1 0 {cx + ox - 14} "
                f"{cy + oy} Z", CELIK_K, 4)
    for ox, oy, r in ((-90, 40, 6), (-104, 22, 5), (52, 44, 6), (66, 26, 4), (-70, 62, 4)):     # talaş
        o += f'<circle cx="{cx + ox}" cy="{cy + oy}" r="{r}" fill="{hx(AHSAP)}" stroke="{I}" stroke-width="2.5"/>'
    o += _p(_poly([(bx - 150, 100), (bx - 120, 100), (bx - 120, 360), (bx - 150, 360)]), CELIK_K, 7)  # ön kolon
    o += gosterge_k(bx + 60, 140, 24, -20)
    return o


# ---------------------------------------------------------------- aşama 4: yapıştır, kes, boya (profil kesici + boya)
def kes_boya() -> str:
    o = zemin(10, 990, 480)
    o += konveyor(20, 980, 330, n=20, r=11)
    # giren sandviç levha (iki sedir levha, arada uçlar)
    o += _p(_poly([(40, 280), (230, 280), (230, 330), (40, 330)]), AHSAP, 6)
    o += f'<path d="M40 305 L230 305" stroke="{I}" stroke-width="4"/>'
    for x in range(56, 228, 26):
        o += f'<circle cx="{x}" cy="305" r="7" fill="{hx(GRAFIT)}" stroke="{I}" stroke-width="3"/>'
    # profil kesici: ağır döküm gövde, ikaz bandı, pencereden görünen üst/alt kesici tamburlar
    o += _p(_poly([(240, 120), (480, 120), (480, 330), (240, 330)]), CELIK, 8)
    o += _p(_poly([(228, 104), (492, 104), (492, 132), (228, 132)]), CELIK_K, 6)
    o += ikaz_svg(240, 300, 240, 14, 12)
    o += _p(_poly([(270, 160), (450, 160), (450, 290), (270, 290)]), (52, 54, 58), 6)          # pencere
    for cy in (198, 262):
        o += f'<circle cx="360" cy="{cy}" r="34" fill="{hx(CELIK_A)}" stroke="{I}" stroke-width="5"/>'
        for j in range(8):
            a = 2 * math.pi * j / 8
            o += (f'<path d="M{360 + 22 * math.cos(a):.1f} {cy + 22 * math.sin(a):.1f} '
                  f'L{360 + 38 * math.cos(a + 0.3):.1f} {cy + 38 * math.sin(a + 0.3):.1f}" stroke="{I}" '
                  'stroke-width="5" stroke-linecap="round"/>')
        o += f'<circle cx="360" cy="{cy}" r="8" fill="{I}"/>'
    o += '<path d="M286 172 L330 166" stroke="#ffffff" stroke-width="5" opacity="0.4" stroke-linecap="round"/>'
    for x in (252, 468):
        for y in (146, 316):
            o += civata_svg(x, y, 6)
    o += gosterge_k(420, 70, 26, 40) + f'<path d="M420 100 L420 104" stroke="{I}" stroke-width="8"/>'
    # çıkan altıgen kalemler: önce ham ahşap, boya kabininden sonra sarı
    for k, x in enumerate((500, 560, 620)):
        o += _altigen_kalem(x, 300, AHSAP)
    # boya kabini: üstte boya hattı ve püskürtme memeleri, sarı sis
    o += _p(_poly([(670, 90), (900, 90), (900, 116), (670, 116)]), CELIK_K, 6)
    o += boru([(690, 116), (690, 150)], 12, CELIK_A) + boru([(880, 116), (880, 150)], 12, CELIK_A)
    o += boru([(560, 60), (785, 60), (785, 90)], 14, YELLOW)
    for x in (730, 785, 840):
        o += _p(_poly([(x - 14, 116), (x + 14, 116), (x + 8, 150), (x - 8, 150)]), CELIK, 5)
        o += (f'<path d="M{x - 6} 154 L{x - 30} 268 L{x + 30} 268 L{x + 6} 154 Z" fill="{hx(YELLOW)}" '
              'opacity="0.55"/>')
        for j, (ox, oy) in enumerate(((-12, 190), (10, 214), (-20, 236), (18, 250), (0, 228))):
            o += f'<circle cx="{x + ox}" cy="{oy}" r="4" fill="{hx(YELLOW)}" stroke="{I}" stroke-width="1.5"/>'
    for x in (700, 760, 820, 880):
        o += _altigen_kalem(x, 300, YELLOW)
    o += f'<path d="M676 330 L676 168 M894 330 L894 168" stroke="{I}" stroke-width="5" stroke-dasharray="14 10"/>'
    return o


def _altigen_kalem(x, y, renk):
    """Konveyörde uçtan görünen altıgen kalem (ortada grafit)."""
    r = 24
    pts = [(x + r * math.cos(math.radians(60 * k + 30)), y + r * math.sin(math.radians(60 * k + 30)) * 0.98)
           for k in range(6)]
    o = _p(_poly(pts), renk, 5)
    o += f'<circle cx="{x}" cy="{y}" r="11" fill="{hx(AHSAP_K if renk != AHSAP else AHSAP_K)}" stroke="{I}" stroke-width="3"/>'
    o += f'<circle cx="{x}" cy="{y}" r="5" fill="{hx(GRAFIT)}"/>'
    return o


def main() -> None:
    yaz("kalem.png", (0, 40, 830, 180), kalem())
    yaz("asama1_pres.png", (0, 40, 1000, 450), pres())
    yaz("asama2_firin.png", (0, -30, 1000, 510), firin())
    yaz("asama3_oluk.png", (40, 20, 940, 530), oluk())
    yaz("asama4_kes_boya.png", (0, 40, 1000, 460), kes_boya())


if __name__ == "__main__":
    main()
