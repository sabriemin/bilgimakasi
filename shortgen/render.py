"""Kolaj / fanzin tarzı dikey video kurgusu (Pillow ile kare kare + FFmpeg)."""
from __future__ import annotations

import math
import random
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .voice import Word

W, H, FPS = 1080, 1920, 30
FONT_DIR = Path(__file__).parent / "assets" / "fonts"
HEAD_FONT = str(FONT_DIR / "Anton-Regular.ttf")
MONO_BOLD = str(FONT_DIR / "CourierPrime-Bold.ttf")

RED = (221, 32, 39)
YELLOW = (252, 213, 33)
BLACK = (20, 19, 19)
PAPER = (233, 231, 226)
WHITE = (250, 249, 245)
GREY = (150, 148, 145)

THEME_BG = {"red": RED, "yellow": YELLOW, "black": BLACK, "paper": PAPER}
SUB_SIZE, SUB_Y, HEAD_SCALE, GRAIN_ON = 52, 1500, 1.0, True
LABEL_STYLE, ROT_MAX, TEXT_ENTRY, SUB_BOX, STARS, CASE = "box", 1.8, "pop", "torn", False, "upper"
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def apply_template(name: str) -> dict:
    """templates/<name>.json dosyasındaki renk, font ve ölçüleri etkinleştirir.
    Tema adları sabittir: red = vurgu rengi, yellow = ikincil vurgu, black = koyu, paper = açık."""
    import json
    global RED, YELLOW, BLACK, PAPER, WHITE, GREY, THEME_BG, HEAD_FONT, MONO_BOLD
    global SUB_SIZE, SUB_Y, HEAD_SCALE, GRAIN_ON, LABEL_STYLE, ROT_MAX, TEXT_ENTRY, SUB_BOX, STARS, CASE
    t = json.loads((TEMPLATE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    c = t["colors"]
    RED, YELLOW, BLACK = tuple(c["accent"]), tuple(c["highlight"]), tuple(c["dark"])
    PAPER, WHITE, GREY = tuple(c["light"]), tuple(c["box"]), tuple(c["muted"])
    THEME_BG = {"red": RED, "yellow": YELLOW, "black": BLACK, "paper": PAPER}
    HEAD_FONT = str(FONT_DIR / t["fonts"]["headline"])
    MONO_BOLD = str(FONT_DIR / t["fonts"]["subtitle"])
    SUB_SIZE = t.get("subtitle_size", 52)
    SUB_Y = t.get("subtitle_y", 1500)
    HEAD_SCALE = t.get("headline_scale", 1.0)
    GRAIN_ON = t.get("grain", True)
    LABEL_STYLE = t.get("label_style", "box")      # box | plain
    ROT_MAX = t.get("rotation", 1.8)                # etiketlerin en fazla eğimi (derece)
    TEXT_ENTRY = t.get("text_entry", "pop")         # pop | slide | wipe | drop
    SUB_BOX = t.get("subtitle_box", "torn")         # torn | pill | plain
    STARS = t.get("stars", False)
    CASE = t.get("case", "upper")                   # upper | asis
    _font_cache.clear()
    _sub_cache.clear()
    return t


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return _font_cache.setdefault((path, size), ImageFont.truetype(path, size))


_font_cache: dict = {}


def tr_upper(s: str) -> str:
    if CASE != "upper":
        return s
    return s.replace("i", "İ").replace("ı", "I").upper()


# ---------------------------------------------------------------- dokular
_rng = np.random.default_rng(7)
_GRAIN = (_rng.normal(0, 1, (H, W)) * 9).astype(np.int16)


def _vignette(strength: float, h: int = H, w: int = W) -> np.ndarray:
    y, x = np.ogrid[:h, :w]
    d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    return np.clip(1 - strength * np.clip(d - 0.35, 0, None) ** 1.6, 0, 1)[..., None]


_VIG = {"paper": _vignette(0.55), "red": _vignette(0.45), "yellow": _vignette(0.45), "black": _vignette(0.3)}


def texture(img: Image.Image, theme: str) -> Image.Image:
    if not GRAIN_ON:
        return img
    a = np.asarray(img).astype(np.int16)
    h, w = a.shape[:2]
    if (h, w) == (H, W):
        grain, vig = _GRAIN, _VIG.get(theme, _VIG["red"])
    else:
        grain = np.tile(_GRAIN, (h // H + 1, w // W + 1))[:h, :w]
        vig = _vignette(0.45, h, w)
    a = a + grain[..., None]
    a = (a * vig).clip(0, 255).astype(np.uint8)
    return Image.fromarray(a)


def background(theme: str) -> Image.Image:
    img = Image.new("RGB", (W, H), THEME_BG[theme])
    if theme == "paper":  # hafif kâğıt lifleri
        d = ImageDraw.Draw(img)
        r = random.Random(3)
        dark_bg = sum(PAPER) < 380
        line_col = tuple(min(255, int(v * 1.08) + 3) if dark_bg else int(v * 0.955) for v in PAPER)
        for _ in range(140):
            y = r.randint(0, H)
            d.line([(0, y), (W, y + r.randint(-4, 4))], fill=line_col, width=1)
    return texture(img, theme)


def tone(photo: Image.Image, theme: str) -> Image.Image:
    g = ImageOps.autocontrast(photo.convert("L"), cutoff=1)
    if theme in ("red", "yellow"):
        c = RED if theme == "red" else YELLOW
        dark = tuple(int(v * 0.12) for v in c)
        light = tuple(min(255, int(v * 0.6 + 110)) for v in c)
        return ImageOps.colorize(g, black=dark, white=light, mid=c)
    g = ImageOps.autocontrast(g, cutoff=2)
    return Image.merge("RGB", (g, g, g))


def cover(img: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / img.width, h / img.height)
    img = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
    l, t = (img.width - w) // 2, (img.height - h) // 3
    return img.crop((l, t, l + w, t + h))


# ---------------------------------------------------------------- etiketler
def label(text: str, font: ImageFont.FreeTypeFont, fg, bg, pad=(26, 14), shadow="accent", rot=0.0,
          strike=False) -> Image.Image:
    l, t, r, b = font.getbbox(text)
    tw, th = r - l, b - t
    bw, bh = tw + pad[0] * 2, th + pad[1] * 2
    off = max(6, bh // 14)
    if shadow == "accent":
        shadow = RED
    im = Image.new("RGBA", (bw + off + 4, bh + off + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shadow:
        d.rectangle([off, off, off + bw, off + bh], fill=shadow)
    d.rectangle([0, 0, bw, bh], fill=bg)
    d.text((pad[0] - l, pad[1] - t), text, font=font, fill=fg)
    if strike:
        y = bh // 2
        d.line([(-4, y + 6), (bw + 4, y - 6)], fill=RED, width=max(8, bh // 7))
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    return im


def fit_font(lines: list[str], max_w: int, start: int, minimum: int = 70) -> ImageFont.FreeTypeFont:
    size = start
    while size > minimum:
        f = _font(HEAD_FONT, size)
        if all(f.getbbox(s)[2] - f.getbbox(s)[0] + 52 <= max_w for s in lines):
            return f
        size -= 6
    return _font(HEAD_FONT, minimum)


def torn_box(w: int, h: int, seed: int) -> Image.Image:
    if SUB_BOX in ("pill", "plain"):
        im = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        rad = h // 2 if SUB_BOX == "pill" else 4
        ImageDraw.Draw(sh).rounded_rectangle([8, 10, w + 8, h + 8], radius=rad, fill=(0, 0, 0, 90))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
        ImageDraw.Draw(im).rounded_rectangle([6, 6, w + 6, h + 6], radius=rad, fill=WHITE)
        return im
    r = random.Random(seed)
    im = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
    pts = []
    for x in range(0, w + 1, 14):
        pts.append((x + 6, 6 + r.uniform(0, 7)))
    for x in range(w, -1, -14):
        pts.append((x + 6, h + 6 - r.uniform(0, 7)))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon([(x + 7, y + 8) for x, y in pts], fill=(0, 0, 0, 110))
    sh = sh.filter(ImageFilter.GaussianBlur(4))
    im.alpha_composite(sh)
    ImageDraw.Draw(im).polygon(pts, fill=WHITE)
    return im


# ---------------------------------------------------------------- ikonlar
def icon(kind: str, theme: str) -> tuple[Image.Image, tuple[int, int]] | None:
    if kind == "question":
        f = _font(HEAD_FONT, 620)
        im = Image.new("RGBA", (520, 760), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((40, -40), "?", font=f, fill=WHITE if theme != "paper" else RED)
        d.text((20, -60), "?", font=f, fill=BLACK)
        return im.rotate(-8, expand=True, resample=Image.BICUBIC), (560, 640)
    if kind == "arrow":
        im = Image.new("RGBA", (420, 120), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.line([(10, 60), (380, 60)], fill=WHITE, width=10)
        d.polygon([(410, 60), (350, 20), (350, 100)], fill=WHITE)
        return im, (120, 1060)
    if kind == "door":
        im = Image.new("RGBA", (300, 440), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([10, 10, 290, 430], fill=WHITE, outline=BLACK, width=10)
        d.rectangle([60, 60, 240, 200], outline=BLACK, width=8)
        d.ellipse([235, 230, 260, 255], fill=BLACK)
        return im, (600, 860)
    if kind == "letter":
        im = Image.new("RGBA", (680, 640), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([20, 20, 680, 640], fill=BLACK if theme == "red" else RED)
        d.rectangle([0, 0, 660, 620], fill=WHITE)
        for y in range(120, 590, 50):
            d.line([(46, y), (614, y)], fill=(200, 205, 215), width=2)
        return im.rotate(1.5, expand=True, resample=Image.BICUBIC), (200, 700)
    if kind == "record":
        im = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([0, 0, 299, 299], fill=BLACK)
        for r_ in range(140, 70, -12):
            d.ellipse([150 - r_, 150 - r_, 150 + r_, 150 + r_], outline=(55, 55, 55), width=2)
        d.ellipse([95, 95, 205, 205], fill=RED)
        d.ellipse([143, 143, 157, 157], fill=BLACK)
        return im, (720, 330)
    return None


# ---------------------------------------------------------------- sahne
@dataclass
class SceneSpec:
    narration: str
    kicker: str
    headline: list[str]
    highlight_line: int
    strike: list[str]
    theme: str
    image_mode: str
    image: Path | None
    icon: str
    sprite: Path | None = None
    motion: str = "none"
    trail: bool = True
    drawn: bool = False  # sprite bir çizim mi (fotoğraf kesiti değil)
    start: float = 0.0
    end: float = 0.0
    words: list[Word] = field(default_factory=list)


class SceneRenderer:
    def __init__(self, s: SceneSpec, idx: int):
        self.s, self.idx = s, idx
        r = random.Random(idx * 7919)
        theme = s.theme
        self.base = background(theme)
        self.photo = None
        if s.image is not None and s.image_mode == "full":
            src = tone(Image.open(s.image).convert("RGB"), theme)
            self.photo = texture(cover(src, int(W * 1.12), int(H * 1.12)), theme)
            self.pan = (r.uniform(-1, 1), r.uniform(-1, 1))
        elif s.image is not None and s.image_mode == "framed":
            src = tone(Image.open(s.image).convert("RGB"), "paper" if theme == "paper" else theme)
            src.thumbnail((800, 760), Image.LANCZOS)
            fr = Image.new("RGBA", (src.width + 32, src.height + 32), WHITE + (255,))
            fr.paste(src, (16, 16))
            shadow = Image.new("RGBA", (fr.width + 60, fr.height + 60), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rectangle([30, 36, fr.width + 30, fr.height + 36], fill=(0, 0, 0, 130))
            shadow = shadow.filter(ImageFilter.GaussianBlur(12))
            shadow.alpha_composite(fr, (24, 24))
            fr = shadow.rotate(r.uniform(-3, 3), expand=True, resample=Image.BICUBIC)
            self.base.paste(fr, ((W - fr.width) // 2, 620 + (700 - fr.height) // 2), fr)
        ic = icon(s.icon, theme)
        if ic:
            self.base.paste(ic[0], ic[1], ic[0])
        self.anim = None
        if s.sprite is not None and s.motion != "none":
            from .anim import Animator, prepare_drawing, prepare_sprite
            trail = (235, 235, 235) if theme != "paper" or sum(PAPER) < 380 else (120, 120, 120)
            spr = prepare_drawing(s.sprite) if s.drawn else prepare_sprite(s.sprite)
            self.anim = Animator(spr, s.motion, trail, cy=1060, trail=s.trail)

        # başlık satırları
        lines = [tr_upper(x) for x in s.headline if x.strip()]
        drawing = self.anim is not None and s.drawn and s.image_mode == "none"
        big = len(lines) == 1 and len(lines[0]) <= 6 and s.image_mode == "none" and not drawing
        size = 330 if big else (140 if drawing else (190 if s.image_mode == "none" else 160))
        font = fit_font(lines, 960, int(size * HEAD_SCALE))
        self.labels = []
        y = {"full": 1000, "framed": 300}.get(s.image_mode, 300 if drawing else 380)
        if s.image_mode == "full":
            y = 1330 - sum(font.getbbox(x)[3] + 40 for x in lines)
        x0 = 54
        if s.kicker.strip():
            k = label(tr_upper(s.kicker), _font(MONO_BOLD, 34),
                      fg=BLACK if theme == "black" else WHITE,
                      bg=WHITE if theme == "black" else BLACK, pad=(16, 10), shadow=None,
                      rot=r.uniform(-1, 1) * ROT_MAX * 0.7)
            self.labels.append((k, (x0, y - k.height - 12), 0.0))
        for i, line in enumerate(lines):
            if i == s.highlight_line:
                fg, bg = BLACK, YELLOW
            elif theme == "black" and not big:
                fg, bg = BLACK, WHITE
            elif big:
                fg, bg = YELLOW if theme == "black" else BLACK, None
            else:
                fg, bg = WHITE if theme != "paper" or i % 2 == 0 else BLACK, BLACK if theme != "paper" or i % 2 == 0 else WHITE
            if bg is None:
                im = self._bare(line, font, fg)
            elif LABEL_STYLE == "plain":
                dark_bg = sum(THEME_BG[theme]) < 380
                col = (YELLOW if dark_bg else RED) if i == s.highlight_line else (WHITE if dark_bg else BLACK)
                if theme in ("red", "yellow") and i == s.highlight_line:
                    col = WHITE if sum(THEME_BG[theme]) < 500 else BLACK
                im = self._plain(line, font, col, r.uniform(-1, 1) * ROT_MAX)
            else:
                im = label(line, font, fg, bg, rot=r.uniform(-1, 1) * ROT_MAX)
            x = x0 + (r.randint(0, 60) if i else 0)
            x = min(x, W - im.width - 20)
            self.labels.append((im, (max(10, x), y), 0.08 + i * 0.16))
            y += im.height + 10
        sf = _font(HEAD_FONT, 70)
        for j, line in enumerate(s.strike):
            im = label(tr_upper(line), sf, BLACK, WHITE, pad=(18, 8), shadow=BLACK, rot=r.uniform(-2, 2), strike=True)
            self.labels.append((im, (x0 + 30, y + 30), 0.5 + j * 0.35))
            y += im.height + 18
        if self.anim is not None and s.drawn and s.image_mode == "none" and \
                self.anim.motion in ("still", "float", "pulse", "zoom_in", "spin", "shake", "rise", "drop_in"):
            # çizimi başlığın altına, altyazının üstüne sığdır
            top, bottom = y + 10, SUB_Y - 60
            spr = self.anim.sprite
            room = max(560, bottom - top)
            if spr.height > room:
                k = room / spr.height
                self.anim.sprite = spr.resize((int(spr.width * k), int(spr.height * k)), Image.LANCZOS)
            self.anim.cy = top + max(room, self.anim.sprite.height) / 2

    @staticmethod
    def _plain(text: str, font, fg, rot: float) -> Image.Image:
        l, t, r_, b = font.getbbox(text)
        im = Image.new("RGBA", (r_ - l + 30, b - t + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((6 - l, 6 - t), text, font=font, fill=fg)
        d.rectangle([6, b - t + 18, r_ - l + 6, b - t + 26], fill=fg if fg != WHITE else YELLOW)
        return im.rotate(rot, resample=Image.BICUBIC, expand=True) if abs(rot) > 0.05 else im

    @staticmethod
    def _bare(text: str, font, fg) -> Image.Image:
        l, t, r_, b = font.getbbox(text)
        im = Image.new("RGBA", (r_ - l + 30, b - t + 30), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((14 - l, 16 - t), text, font=font, fill=RED)
        d.text((4 - l, 6 - t), text, font=font, fill=fg)
        return im

    def frame(self, t: float) -> Image.Image:
        dur = max(0.1, self.s.end - self.s.start)
        p = min(1.0, (t - self.s.start) / dur)
        if self.photo is not None:
            z = 1.0 + 0.08 * p
            cw, ch = int(W * 1.12 / z), int(H * 1.12 / z)
            mx, my = (self.photo.width - cw) / 2, (self.photo.height - ch) / 2
            cx = mx + self.pan[0] * mx * p
            cy = my + self.pan[1] * my * p
            img = self.photo.crop((int(cx), int(cy), int(cx) + cw, int(cy) + ch)).resize((W, H), Image.BILINEAR)
        else:
            img = self.base.copy()
        img = img.convert("RGBA") if img.mode != "RGBA" else img
        lt = t - self.s.start
        if STARS and self.photo is None and sum(THEME_BG[self.s.theme]) < 380:
            from .anim import stars
            stars(img, lt, self.idx)
        if self.anim is not None:
            self.anim.draw(img, p, lt, dur)
        for im, (x, y), delay in self.labels:
            a = (lt - delay) / (0.14 if TEXT_ENTRY == "pop" else 0.22)
            if a <= 0:
                continue
            if a >= 1:
                img.alpha_composite(im, (x, y))
            elif TEXT_ENTRY == "slide":
                e = 1 - (1 - a) ** 3
                img.alpha_composite(im, (int(x - 160 * (1 - e)), y)) if x - 160 * (1 - e) >= 0 else \
                    img.alpha_composite(im.crop((int(160 * (1 - e) - x), 0, im.width, im.height)), (0, y))
            elif TEXT_ENTRY == "wipe":
                wv = max(1, int(im.width * (1 - (1 - a) ** 2)))
                img.alpha_composite(im.crop((0, 0, wv, im.height)), (x, y))
            elif TEXT_ENTRY == "drop":
                e = 1 - (1 - a) ** 3
                yy = int(y - 90 * (1 - e))
                if yy >= 0:
                    img.alpha_composite(im, (x, yy))
            else:
                sc = 1.25 - 0.25 * a
                w2, h2 = int(im.width * sc), int(im.height * sc)
                im2 = im.resize((w2, h2), Image.BILINEAR)
                img.alpha_composite(im2, (max(0, x - (w2 - im.width) // 2), max(0, y - (h2 - im.height) // 2)))
        return img


# ---------------------------------------------------------------- altyazı
def chunk_words(words: list[Word], max_words: int = 5, max_chars: int = 28) -> list[list[int]]:
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        n_chars = sum(len(words[j].text) + 1 for j in cur)
        if len(cur) >= max_words or n_chars >= max_chars or w.text[-1] in ".?!,;:":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


_sub_cache: dict = {}
SUB_HANDLE = ""  # altyazı kutusundaki kullanıcı adı (marka)


def subtitle(words: list[Word], chunk: list[int], current: int, seed: int) -> Image.Image:
    key = (tuple(chunk), current)
    if key in _sub_cache:
        return _sub_cache[key]
    f = _font(MONO_BOLD, SUB_SIZE)
    toks = [words[i].text for i in chunk]
    space = f.getlength(" ")
    widths = [f.getlength(t) for t in toks]
    # en fazla 2 satır
    lines, cur, cw = [], [], 0
    for k, wdt in enumerate(widths):
        if cur and cw + space + wdt > 820:
            lines.append(cur)
            cur, cw = [], 0
        cw += (space if cur else 0) + wdt
        cur.append(k)
    lines.append(cur)
    lh = int(SUB_SIZE * 1.3)
    bw = int(max(sum(widths[k] for k in ln) + space * (len(ln) - 1) for ln in lines)) + 64
    bh = lh * len(lines) + 40 + (22 if SUB_HANDLE else 0)
    if SUB_HANDLE:
        bw = max(bw, 300)
    im = torn_box(bw, bh, seed)
    d = ImageDraw.Draw(im)
    if SUB_HANDLE:
        hf = _font(MONO_BOLD, 22)
        hw = hf.getlength(SUB_HANDLE)
        d.text((6 + bw - hw - 16, 6 + bh - 30), SUB_HANDLE, font=hf, fill=GREY)
    for li, ln in enumerate(lines):
        lw = sum(widths[k] for k in ln) + space * (len(ln) - 1)
        x = 6 + (bw - lw) / 2
        y = 6 + 20 + li * lh
        for k in ln:
            gi = chunk[k]
            col = BLACK if gi <= current else GREY
            d.text((x, y), toks[k], font=f, fill=col)
            if gi == current:
                d.line([(x, y + SUB_SIZE + 6), (x + widths[k], y + SUB_SIZE + 6)], fill=RED, width=6)
            x += widths[k] + space
    _sub_cache[key] = im
    return im


# ---------------------------------------------------------------- ana döngü
def render(scenes: list[SceneSpec], words: list[Word], out_mp4: Path, voice_mp3: Path | None,
           music: Path | None = None, tail: float = 1.6, template: str = "kolaj") -> Path:
    global SUB_HANDLE
    apply_template(template)
    from .brand import Brand, load_config
    bcfg = load_config()
    brand = Brand(bcfg, {})
    SUB_HANDLE = bcfg.get("handle", "") if brand.on and bcfg.get("subtitle_handle", True) else ""
    _sub_cache.clear()
    outro = bcfg.get("outro_seconds", 2.4) if brand.on else 0.0
    content_end = (words[-1].end if words else scenes[-1].end) + (0.7 if outro else tail)
    total = content_end + outro
    scenes[-1].end = content_end
    every = bcfg.get("cut_transition_every", 4) if brand.on else 0
    cut_at = [sc.start for i, sc in enumerate(scenes) if every and i and i % every == 0]
    chunks = chunk_words(words)
    chunk_of = {i: ci for ci, ch in enumerate(chunks) for i in ch}
    silent = out_mp4.with_suffix(".silent.mp4")
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "8M", "-bufsize", "16M",
        "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    renderers: dict[int, SceneRenderer] = {}
    n = int(total * FPS)
    si = 0
    for fi in range(n):
        t = fi / FPS
        while si + 1 < len(scenes) and t >= scenes[si + 1].start:
            renderers.pop(si, None)
            si += 1
        if t >= content_end:  # kapanış kartı
            img = brand.outro(t - content_end, outro)
            ff.stdin.write(img.convert("RGB").tobytes())
            continue
        if si not in renderers:
            renderers[si] = SceneRenderer(scenes[si], si)
        img = renderers[si].frame(t)
        if brand.on:
            brand.watermark(img, t, 0.8 if bcfg.get("intro_cut", True) else 0.0)
            brand.intro(img, t)
            for k, ct in enumerate(cut_at):
                if ct - 0.02 <= t < ct + 0.32:
                    img = brand.cut(img, t - ct, k)
        # aktif kelime
        cur = None
        for i, w in enumerate(words):
            if w.start <= t + 0.03:
                cur = i
            else:
                break
        if cur is not None and t <= words[-1].end + 0.6:
            ch = chunks[chunk_of[cur]]
            sub = subtitle(words, ch, cur, chunk_of[cur])
            img.alpha_composite(sub, ((W - sub.width) // 2, SUB_Y - sub.height // 2))
        ff.stdin.write(img.convert("RGB").tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg video kodlaması başarısız")
    mux(silent, voice_mp3, music, out_mp4, total)
    silent.unlink(missing_ok=True)
    return out_mp4


def mux(video: Path, voice: Path | None, music: Path | None, out: Path, total: float) -> None:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video)]
    if voice and music:
        cmd += ["-i", str(voice), "-stream_loop", "-1", "-i", str(music), "-filter_complex",
                "[1:a]asplit=2[v1][v2];[2:a]volume=0.22[m];"
                "[m][v1]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=400[duck];"
                "[v2][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]",
                "-map", "0:v", "-map", "[a]"]
    elif voice:
        cmd += ["-i", str(voice), "-filter_complex", "[1:a]loudnorm=I=-14:TP=-1.5[a]", "-map", "0:v", "-map", "[a]"]
    elif music:
        cmd += ["-stream_loop", "-1", "-i", str(music), "-filter_complex", "[1:a]volume=0.3[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-t", f"{total:.2f}",
            "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
