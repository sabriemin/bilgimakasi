"""Bilgi Makası marka öğeleri: hareketli filigran, makas kesme geçişleri, açılış ve kapanış kartı.

Amaç hem marka tanınırlığı hem de videonun başkaları tarafından kırpılıp yeniden yüklenmesini zorlaştırmak:
filigran köşeler arasında yer değiştirir, kullanıcı adı altyazı kutusunun içindedir (altyazıyı kırpmadan silinemez),
kapanış kartı da videonun sonunda kanal adını gösterir.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(__file__).resolve().parent / "assets"
W, H = 1080, 1920

RED, YEL, BLK = (221, 32, 39), (252, 213, 33), (20, 19, 19)
PAPER, WHITE = (233, 231, 226), (250, 249, 245)


def load_config() -> dict:
    p = ROOT / "brand.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"enabled": False}


def scissors(size: int, blade=BLK, handle=RED, pin=YEL, open_deg: float = 44, rot: float = 0.0) -> Image.Image:
    """Marka kitindeki makas simgesi (marka/uret_kit.py ile aynı çizim)."""
    S = size * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    px, py = S * 0.5, S * 0.45
    L, R = S * 0.42, S * 0.17
    rr, rw = S * 0.105, S * 0.04
    for sgn in (-1, 1):
        a = math.radians(sgn * open_deg / 2)
        ux, uy = math.sin(a), -math.cos(a)
        nx, ny = -uy, ux
        tip = (px + ux * L, py + uy * L)
        base = (px - ux * (R + rr * 0.3), py - uy * (R + rr * 0.3))
        ring = (px - ux * (R + rr * 0.95), py - uy * (R + rr * 0.95))
        wB, wS = S * 0.05, S * 0.034
        poly = [tip, (px + nx * wB * sgn, py + ny * wB * sgn), (base[0] + nx * wS, base[1] + ny * wS),
                (base[0] - nx * wS, base[1] - ny * wS), (px - nx * wB * 0.3 * sgn, py - ny * wB * 0.3 * sgn)]
        d.polygon(poly, fill=blade)
        cx, cy = ring
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=handle, width=int(rw))
    r = S * 0.028
    d.ellipse((px - r, py - r, px + r, py + r), fill=pin, outline=blade, width=int(S * 0.008))
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    im = im.crop(im.getbbox())
    k = (S * 0.96) / max(im.size)
    im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c.alpha_composite(im, ((S - im.width) // 2, (S - im.height) // 2))
    return c.resize((size, size), Image.LANCZOS)


def _dashed(d: ImageDraw.ImageDraw, p0, p1, color, width: int, dash: int = 30, gap: int = 18) -> None:
    L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    if L < 1:
        return
    ux, uy = (p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L
    t = 0.0
    while t < L:
        e = min(t + dash, L)
        d.line((p0[0] + ux * t, p0[1] + uy * t, p0[0] + ux * e, p0[1] + uy * e), fill=color, width=width)
        t = e + gap


class Brand:
    def __init__(self, cfg: dict, fonts: dict):
        self.cfg = cfg
        self.on = cfg.get("enabled", False)
        if not self.on:
            return
        wm = Image.open(ASSETS / "brand" / "video_filigran.png").convert("RGBA")
        wm = wm.resize((int(wm.width * 0.9), int(wm.height * 0.9)), Image.LANCZOS)
        a = wm.getchannel("A").point(lambda v: int(v * cfg.get("watermark_opacity", 0.85)))
        wm.putalpha(a)
        self.wm = wm
        self.spots = [(36, 120), (W - wm.width - 36, 120)]
        self.switch = cfg.get("watermark_switch_seconds", 7)
        self.sc_cache: dict = {}
        self.fonts = fonts
        self.logo_dark = Image.open(ASSETS / "brand" / "logo_koyu_zemin.png").convert("RGBA")
        self.logo_light = Image.open(ASSETS / "brand" / "logo_acik_zemin.png").convert("RGBA")

    # ------------------------------------------------------------ filigran
    def watermark(self, img: Image.Image, t: float, intro_end: float) -> None:
        if t < intro_end:
            return
        tt = t - intro_end
        i = int(tt // self.switch)
        local = tt - i * self.switch
        fade = 0.25
        x, y = self.spots[i % len(self.spots)]
        alpha = min(1.0, local / fade, (self.switch - local) / fade)
        if alpha <= 0:
            return
        im = self.wm
        if alpha < 1:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
        img.alpha_composite(im, (x, y))

    def _sc(self, size: int, rot: float, open_deg: float) -> Image.Image:
        key = (size, round(rot), round(open_deg))
        if key not in self.sc_cache:
            self.sc_cache[key] = scissors(size, blade=WHITE, rot=rot, open_deg=open_deg)
        return self.sc_cache[key]

    # ------------------------------------------------------------ açılış: makas ekranı keser
    def intro(self, img: Image.Image, t: float, dur: float = 0.8) -> None:
        if not self.cfg.get("intro_cut", True) or t >= dur:
            return
        p = t / dur
        y = 210
        d = ImageDraw.Draw(img)
        x = -150 + p * (W + 300)
        _dashed(d, (0, y), (max(0, x), y), (250, 249, 245), 6)
        _dashed(d, (0, y + 3), (max(0, x), y + 3), (20, 19, 19), 2)
        sc = self._sc(150, -90, 30 + 20 * abs(math.sin(t * 22)))
        img.alpha_composite(sc, (int(x - sc.width / 2), int(y - sc.height / 2)))
        # filigran, makasın arkasından düşerek yerine oturur
        if p > 0.45:
            k = min(1.0, (p - 0.45) / 0.45)
            e = 1 - (1 - k) ** 3
            x0, y0 = self.spots[0]
            img.alpha_composite(self.wm, (x0, int(y0 - 120 * (1 - e))))

    # ------------------------------------------------------------ sahne geçişi: makas kesimi
    def cut(self, img: Image.Image, local: float, seed: int, length: float = 0.32) -> Image.Image:
        """local: geçiş başlangıcından beri geçen süre (0..length)."""
        p = max(0.0, min(1.0, local / length))
        ang = math.radians(-8 if seed % 2 else 8)
        cy = H * (0.42 + 0.1 * (seed % 3))
        shift = int(70 * (1 - p) ** 2)
        if shift > 0:
            # ekranı kesik boyunca ikiye ayır, parçaları ters yönlere kaydır
            mask = Image.new("L", (W, H), 0)
            md = ImageDraw.Draw(mask)
            y0, y1 = cy - math.tan(ang) * W / 2, cy + math.tan(ang) * W / 2
            md.polygon([(0, 0), (W, 0), (W, y1), (0, y0)], fill=255)
            top = Image.new("RGBA", (W, H), (0, 0, 0, 255))
            top.paste(img, (-shift, -shift // 3))
            bottom = Image.new("RGBA", (W, H), (0, 0, 0, 255))
            bottom.paste(img, (shift, shift // 3))
            bottom.paste(top, (0, 0), mask)
            img = bottom
        d = ImageDraw.Draw(img)
        x = -150 + p * (W + 300)
        y0 = cy - math.tan(ang) * W / 2
        yx = y0 + math.tan(ang) * x
        _dashed(d, (0, y0), (max(1, x), yx), (250, 249, 245), 6)
        sc = self._sc(140, -90 - math.degrees(ang), 30 + 20 * abs(math.sin(local * 30)))
        img.alpha_composite(sc, (int(x - sc.width / 2), int(yx - sc.height / 2)))
        return img

    # ------------------------------------------------------------ kapanış kartı
    def outro(self, local: float, dur: float) -> Image.Image:
        from .render import background, label, _font, HEAD_FONT, MONO_BOLD
        img = background("paper").convert("RGBA")
        logo = self.logo_light
        s = min(1.0, local / 0.22)
        sc = 0.85 + 0.15 * (1 - (1 - s) ** 3) if s < 1 else 1.0
        lw = int(900 * sc)
        lg = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
        img.alpha_composite(lg, ((W - lg.width) // 2, 520 - lg.height // 2))
        if local > 0.25:
            h = label(self.cfg.get("handle", "@bilgimakasi"), _font(MONO_BOLD, 64), WHITE, BLK, pad=(28, 16),
                      shadow="accent", rot=-1.5)
            img.alpha_composite(h, ((W - h.width) // 2, 860))
        if local > 0.5:
            pulse = 1 + 0.05 * abs(math.sin((local - 0.5) * 5))
            f = label(self.cfg.get("follow_text", "TAKİP ET"), _font(HEAD_FONT, int(150 * pulse)), BLK, YEL,
                      rot=2.0)
            img.alpha_composite(f, ((W - f.width) // 2, 1080))
        if local > 0.7:
            sl = label(self.cfg.get("slogan", ""), _font(MONO_BOLD, 44), BLK, WHITE, pad=(20, 12), shadow=None)
            img.alpha_composite(sl, ((W - sl.width) // 2, 1380))
        if local < 0.35:  # makas kartı açar
            img = self.cut(img, local, 1, 0.35)
        return img
