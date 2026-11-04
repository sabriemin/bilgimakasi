"""Sahne çizimleri: Claude, her sahne için marka renklerinde düz (flat) bir SVG illüstrasyon çizer.

Fotoğraftan kesilmiş nesneler yerine kullanılır: anlamı tam tutar (ör. 'kahverengi melas dalgası'),
telif sorunu yoktur ve tüm videolarda tutarlı bir çizgi stili sağlar.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from .script import ask_claude

STYLE = """Sen bir editoryal illüstratörsün. Kısa video sahneleri için tek nesneli/tek sahneli, düz (flat) vektör çizimler yaparsın.
Kurallar:
- Çıktı geçerli, bağımsız bir SVG olsun: <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800">. Arka plan ŞEFFAF (arka plan dikdörtgeni yok).
- Stil: kesilmiş kâğıt kolaj hissi veren düz çizim; kalın siyah dış hatlar (stroke-width 8-12, stroke-linejoin round),
  az detay, net siluet, birkaç düz renk alanı ve basit gölge şekilleri. Gradyan, filtre, metin, <image>, dış bağlantı, font YOK.
- Palet: verilen marka renkleri. Konu gerçekten gerektiriyorsa (ör. melas için koyu kahverengi, deniz için mavi, bitki için yeşil)
  en fazla 2 ek doğal renk kullan; doygunluğu düşük tut.
- Çizim konuyu kelimesi kelimesine değil, anlamıyla göstersin (ör. 'melas dalgası' = koyu kahverengi, yapışkan, damlalı bir dalga;
  deniz dalgası değil). Tarihî döneme uygun nesneler çiz.
- Nesne viewBox'ı büyük ölçüde doldursun ama kenarlardan 30 birim boşluk kalsın. Gerçekçi insan yüzü çizme; insan gerekiyorsa basit siluet.
- Her SVG en fazla yaklaşık 6000 karakter olsun."""


class Drawing(BaseModel):
    scene: int = Field(description="Sahne numarası (0'dan başlar)")
    svg: str = Field(description="Tam SVG belgesi")


class Drawings(BaseModel):
    items: List[Drawing]


def _palette() -> str:
    from . import render
    hexs = lambda c: "#%02x%02x%02x" % tuple(c[:3])  # noqa: E731
    return (f"kırmızı {hexs(render.RED)}, sarı {hexs(render.YELLOW)}, siyah {hexs(render.BLACK)}, "
            f"krem {hexs(render.PAPER)}, beyaz {hexs(render.WHITE)}")


def _clean(svg: str) -> str:
    svg = svg.strip()
    svg = re.sub(r"^```(?:svg|xml)?\s*|\s*```$", "", svg)
    # güvenlik: dışarıdan kaynak çekebilecek öğeleri sil
    svg = re.sub(r"<(script|image|foreignObject)\b.*?(</\1>|/>)", "", svg, flags=re.S | re.I)
    svg = re.sub(r'\s(xlink:)?href="(?!#)[^"]*"', "", svg)
    return svg


def rasterize(svg: str, out: Path, size: int = 900) -> Path | None:
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(out), output_width=size, output_height=size)
    except Exception as e:  # noqa: BLE001
        print(f"Çizim işlenemedi ({out.name}): {e}")
        return None
    from PIL import Image
    im = Image.open(out)
    if im.mode != "RGBA" or im.getchannel("A").getbbox() is None:
        return None
    return out


def draw_scenes(requests: dict[int, str], topic: str, out_dir: Path) -> dict[int, Path]:
    """requests: {sahne_no: çizim tarifi}. Tek Claude çağrısıyla hepsini çizer; PNG yollarını döndürür."""
    if not requests:
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(f"- Sahne {i}: {d}" for i, d in sorted(requests.items()))
    prompt = (f"Video konusu: {topic}\nMarka renkleri: {_palette()}\n\n"
              f"Aşağıdaki her sahne için bir SVG çiz ve 'items' listesinde sahne numarasıyla döndür:\n{lines}")
    try:
        res = ask_claude(prompt, Drawings, STYLE)
    except Exception as e:  # noqa: BLE001
        print(f"Çizimler alınamadı: {e}")
        return {}
    out: dict[int, Path] = {}
    for it in res.items:
        if it.scene not in requests:
            continue
        svg = _clean(it.svg)
        (out_dir / f"sahne_{it.scene:02d}.svg").write_text(svg, encoding="utf-8")
        png = rasterize(svg, out_dir / f"sahne_{it.scene:02d}_{hashlib.md5(svg.encode()).hexdigest()[:6]}.png")
        if png:
            out[it.scene] = png
    print(f"Çizim: {len(out)}/{len(requests)} sahne")
    return out
