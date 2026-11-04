"""Görsel bulma: yalnızca kamu malı / özgür lisanslı görseller (Wikimedia Commons)."""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

# Wikimedia kullanıcı ajanı politikası: araç adı + iletişim adresi (depo) olmalı, yoksa 429 dönebiliyor.
UA = {"User-Agent": "BilgiMakasiBot/1.0 (https://github.com/sabriemin/bilgimakasi) python-requests"}
_last = [0.0]


def _get(url: str, **kw) -> requests.Response:
    """Wikimedia'ya nazik istek: istekler arası bekleme, 429/5xx'te Retry-After'a uyarak tekrar dene."""
    for attempt in range(6):
        wait = 1.2 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        r = requests.get(url, headers=UA, **kw)
        _last[0] = time.time()
        if r.status_code not in (429, 500, 502, 503, 504):
            r.raise_for_status()
            return r
        try:
            ra = float(r.headers.get("Retry-After", ""))
        except ValueError:
            ra = 0
        time.sleep(min(60, max(ra, 5 * 2 ** attempt)))
    r.raise_for_status()
    return r
API = "https://commons.wikimedia.org/w/api.php"
ALLOWED = re.compile(r"^(public domain|pd\b|pd-|cc0|cc[- ]by(-sa)?[- ]?\d)", re.I)


@dataclass
class ImageCredit:
    file: str
    title: str
    author: str
    license: str
    page: str


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def find_cutout(query: str, cache_dir: Path) -> tuple[Path, ImageCredit] | None:
    """Önce şeffaf arka planlı PNG arar (animasyon için ideal), yoksa normal fotoğraf döner."""
    return find_image(query, cache_dir, prefer_png=True) or find_image(query, cache_dir)


def find_image(query: str, cache_dir: Path, exclude: set[str] | None = None,
               prefer_png: bool = False) -> tuple[Path, ImageCredit] | None:
    """Sorguya uyan, lisansı uygun ilk fotoğrafı indirir. Bulamazsa None."""
    if not query:
        return None
    exclude = exclude or set()
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filemime:image/png" if prefer_png else f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 15,
        "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1280,
    }
    r = _get(API, params=params, timeout=30)
    pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = _strip(meta.get("LicenseShortName", {}).get("value", ""))
        if not ALLOWED.match(lic) or "nc" in lic.lower() or "nd" in lic.lower():
            continue
        if info.get("mime") not in (("image/png",) if prefer_png else ("image/jpeg", "image/png")) \
                or info.get("width", 0) < 400:
            continue
        if p["title"] in exclude:
            continue
        url = info.get("thumburl") or info["url"]
        out = cache_dir / (hashlib.md5(url.encode()).hexdigest() + Path(url).suffix.lower())
        if not out.exists():
            img = _get(url, timeout=60)
            out.write_bytes(img.content)
        credit = ImageCredit(
            file=str(out), title=p["title"].removeprefix("File:"),
            author=_strip(meta.get("Artist", {}).get("value", "")) or "Bilinmiyor",
            license=lic, page=info.get("descriptionurl", ""),
        )
        return out, credit
    return None


def credits_text(credits: list[ImageCredit]) -> str:
    seen, lines = set(), []
    for c in credits:
        if c.page in seen:
            continue
        seen.add(c.page)
        lines.append(f"{c.title}, {c.author}, {c.license}, Wikimedia Commons")
    return "Görseller: " + " | ".join(lines) if lines else ""


def credit_dict(c: ImageCredit) -> dict:
    return asdict(c)
