"""Nesne animasyonları: kesilmiş (arka planı silinmiş) bir nesneyi sahnede hareket ettirir.

Her hareket, sahnenin ilerleme oranı p (0..1) ve sahne içi süre lt (saniye) ile durumsuz hesaplanır,
böylece iz/duman gibi parçacıklar da geçmiş konumlardan yeniden çizilebilir.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

W, H = 1080, 1920

MOTIONS = ["fly_up", "fly_right", "fly_left", "drop_in", "zoom_in", "float", "spin", "shake", "orbit", "pulse", "rise", "still"]


def ease_in_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ease_out_back(x: float) -> float:
    x = min(1.0, max(0.0, x))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def bounce_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    n, d = 7.5625, 2.75
    if x < 1 / d:
        return n * x * x
    if x < 2 / d:
        x -= 1.5 / d
        return n * x * x + 0.75
    if x < 2.5 / d:
        x -= 2.25 / d
        return n * x * x + 0.9375
    x -= 2.625 / d
    return n * x * x + 0.984375


def pose(motion: str, p: float, lt: float, cy: float = 1000) -> tuple[float, float, float, float]:
    """(x, y, ölçek, açı) döndürür. x, y nesnenin merkezi."""
    cx = W / 2
    if motion == "fly_up":
        e = ease_in_out(p) ** 1.3
        return cx + 40 * math.sin(lt * 2), H + 450 - e * (H + 1000), 0.85 + 0.25 * e, 0
    if motion == "fly_right":
        e = ease_in_out(p)
        return -400 + e * (W + 800), cy + 30 * math.sin(lt * 3), 1.0, -4 + 3 * math.sin(lt * 2)
    if motion == "fly_left":
        e = ease_in_out(p)
        return W + 400 - e * (W + 800), cy + 30 * math.sin(lt * 3), 1.0, 4 + 3 * math.sin(lt * 2)
    if motion == "drop_in":
        return cx, -500 + bounce_out(p * 1.6) * (cy + 500), 1.0, 0
    if motion == "zoom_in":
        return cx, cy, 0.2 + 0.95 * ease_out_back(p * 1.8), 0
    if motion == "float":
        return cx, cy + 35 * math.sin(lt * 2.2), 1.0, 4 * math.sin(lt * 1.6)
    if motion == "spin":
        return cx, cy, 0.9 + 0.1 * ease_out_back(p * 2), -lt * 70
    if motion == "shake":
        k = max(0.0, 1 - p * 1.5)
        return cx + k * 28 * math.sin(lt * 55), cy + k * 18 * math.cos(lt * 47), 1.0, k * 5 * math.sin(lt * 40)
    if motion == "orbit":
        a = lt * 1.8
        return cx + 300 * math.cos(a), cy + 120 * math.sin(a), 0.75 + 0.15 * math.sin(a), 0
    if motion == "rise":  # aşağıdan yükselip yerine oturur (sel, dalga, bina)
        e = 1 - (1 - min(1.0, p * 1.8)) ** 3
        return cx + 12 * math.sin(lt * 1.5), cy + (1 - e) * 900, 1.0, 2 * math.sin(lt * 1.2)
    if motion == "still":  # çizim sahnesi: hafif içeri girip çok az salınır
        e = ease_out_back(min(1.0, p * 4))
        return cx, cy + 8 * math.sin(lt * 1.6), 0.85 + 0.15 * e, 1.2 * math.sin(lt * 1.1)
    if motion == "pulse":
        beat = abs(math.sin(lt * math.pi * 1.4)) ** 6
        return cx, cy, 1.0 + 0.12 * beat, 0
    return cx, cy, 1.0, 0


def prepare_sprite(path: Path, target_w: int = 560, max_h: int = 780) -> Image.Image:
    """Şeffaf PNG ise olduğu gibi; değilse rembg ile arka planı siler; o da yoksa çerçeveli fotoğraf yapar."""
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 250:
        im = im.convert("RGBA")
    else:
        try:
            from rembg import remove  # isteğe bağlı bağımlılık
            im = remove(im.convert("RGB"))
        except Exception:
            src = im.convert("RGB")
            src.thumbnail((target_w - 32, target_w - 32))
            fr = Image.new("RGBA", (src.width + 32, src.height + 32), (250, 249, 245, 255))
            fr.paste(src, (16, 16))
            im = fr
    bbox = im.getchannel("A").getbbox()
    if bbox:
        im = im.crop(bbox)
    s = min(target_w / im.width, max_h / im.height) if im.width >= im.height else min(max_h / im.height, 900 / im.width)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    # hafif gölge, kolaja oturması için
    sh = Image.new("RGBA", (im.width + 40, im.height + 40), (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: v * 0.45)
    sh.paste(Image.new("RGBA", im.size, (0, 0, 0, 255)), (26, 30), a)
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    sh.alpha_composite(im, (14, 14))
    return sh


def prepare_drawing(path: Path, max_w: int = 820, max_h: int = 720, border: int = 14) -> Image.Image:
    """Çizimi kâğıttan kesilmiş çıkartma gibi hazırlar: beyaz kenar + hafif gölge (koyu zeminde de okunur)."""
    im = Image.open(path).convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if bbox:
        im = im.crop(bbox)
    s = min(max_w / im.width, max_h / im.height)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    pad = border + 30
    a = Image.new("L", (im.width + 2 * pad, im.height + 2 * pad), 0)
    a.paste(im.getchannel("A"), (pad, pad))
    edge = a.filter(ImageFilter.MaxFilter(border * 2 + 1)).filter(ImageFilter.GaussianBlur(1.2))
    out = Image.new("RGBA", a.size, (0, 0, 0, 0))
    shadow = edge.point(lambda v: int(v * 0.4)).filter(ImageFilter.GaussianBlur(9))
    out.paste((0, 0, 0, 255), (10, 14), shadow)
    out = Image.composite(Image.new("RGBA", a.size, (250, 249, 245, 255)), out, edge)
    out.alpha_composite(im, (pad, pad))
    return out


class Animator:
    def __init__(self, sprite: Image.Image, motion: str, trail_color=(255, 255, 255), cy: float = 1000,
                 trail: bool = True):
        self.sprite, self.motion, self.trail_color, self.cy = sprite, motion, trail_color, cy
        self.trail = trail
        self._rot_cache: dict = {}

    def _transformed(self, scale: float, angle: float) -> Image.Image:
        key = (round(scale, 2), round(angle))
        if key not in self._rot_cache:
            if len(self._rot_cache) > 300:
                self._rot_cache.clear()
            im = self.sprite
            if abs(scale - 1) > 0.005:
                im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
            if key[1]:
                im = im.rotate(key[1], resample=Image.BICUBIC, expand=True)
            self._rot_cache[key] = im
        return self._rot_cache[key]

    def draw(self, img: Image.Image, p: float, lt: float, dur: float) -> None:
        if self.trail and self.motion in ("fly_up", "fly_right", "fly_left"):
            self._trail(img, p, lt, dur)
        x, y, s, a = pose(self.motion, p, lt, self.cy)
        im = self._transformed(s, a)
        img.alpha_composite(im, (int(x - im.width / 2), int(y - im.height / 2))) if (
            -im.width < x < W + im.width and -im.height < y < H + im.height) else None

    def _trail(self, img: Image.Image, p: float, lt: float, dur: float) -> None:
        """Geçmiş konumlardan duman/iz parçacıkları (durumsuz)."""
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for k in range(1, 26):
            dt = k * 0.035
            if lt - dt < 0:
                break
            pp = max(0.0, p - dt / dur)
            x, y, s, _ = pose(self.motion, pp, lt - dt, self.cy)
            rnd = random.Random(int((lt - dt) * 1000))
            if self.motion == "fly_up":
                ox, oy = rnd.uniform(-40, 40) * (1 + k * 0.08), self.sprite.height * s * 0.45 + k * 6
            else:
                sign = -1 if self.motion == "fly_right" else 1
                ox, oy = sign * self.sprite.width * s * 0.45 + sign * k * 4, rnd.uniform(-25, 25)
            r = 10 + k * 3.2
            alpha = int(200 * (1 - k / 26))
            c = self.trail_color
            d.ellipse([x + ox - r, y + oy - r, x + ox + r, y + oy + r], fill=(c[0], c[1], c[2], alpha))
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(6)))


def stars(img: Image.Image, lt: float, seed: int, color=(255, 255, 255)) -> None:
    """Gece şablonu için titreşen yıldızlar."""
    d = ImageDraw.Draw(img)
    r = random.Random(seed)
    for _ in range(90):
        x, y, ph, sz = r.uniform(0, W), r.uniform(0, H), r.uniform(0, 6.28), r.choice([1.5, 2, 2.5, 3.5])
        a = int(120 + 120 * math.sin(lt * 2.5 + ph))
        d.ellipse([x - sz, y - sz, x + sz, y + sz], fill=(color[0], color[1], color[2], max(0, a)))


def demo_shuttle(path: Path) -> Path:
    """Ağ yokken denemek için basit, çizilmiş bir uzay mekiği (gerçek üretimde fotoğraftan kesilir)."""
    im = Image.new("RGBA", (420, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([150, 120, 270, 820], radius=60, fill=(214, 120, 40))       # yakıt tankı
    d.polygon([(150, 180), (210, 20), (270, 180)], fill=(214, 120, 40))
    for x in (95, 275):                                                             # yan roketler
        d.rounded_rectangle([x, 240, x + 50, 840], radius=22, fill=(240, 240, 236))
        d.polygon([(x, 260), (x + 25, 170), (x + 50, 260)], fill=(240, 240, 236))
    d.polygon([(160, 360), (210, 300), (260, 360), (260, 800), (160, 800)], fill=(250, 250, 248))  # mekik
    d.polygon([(160, 620), (60, 800), (160, 800)], fill=(250, 250, 248))
    d.polygon([(260, 620), (360, 800), (260, 800)], fill=(250, 250, 248))
    d.polygon([(195, 330), (210, 312), (225, 330)], fill=(30, 30, 30))
    for x in (120, 210, 300):                                                       # alev
        d.polygon([(x - 22, 840), (x, 900), (x + 22, 840)], fill=(255, 190, 60))
    im.save(path)
    return path
