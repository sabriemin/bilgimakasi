"""Görsel bulma: yalnızca kamu malı / özgür lisanslı görseller (Wikimedia Commons)."""
from __future__ import annotations

import hashlib
import os
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
# Kamu malı / CC0 + CC BY / BY-SA (CC BY için açıklamaya tek satır görsel kaynağı yazılır).
# ALLOW_CC_BY=0 verilirse yalnız atıf gerektirmeyen görseller kullanılır.
ALLOWED = re.compile(r"^(public domain|pd\b|pd-|cc0)" + (r"|^cc[- ]by(-sa)?[- ]?\d" if os.environ.get("ALLOW_CC_BY", "1") == "1" else ""), re.I)


@dataclass
class ImageCredit:
    file: str
    title: str
    author: str
    license: str
    page: str
    source: str = "Wikimedia Commons"


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


GENERIC = {"photo", "photograph", "photography", "historic", "historical", "image", "picture", "old", "vintage",
           "black", "white", "the", "and", "with", "from", "for", "view", "early", "century"}


def _tokens(text: str) -> set[str]:
    text = re.sub(r"(?<=[a-z])(?=[A-Z])|[_%-]", " ", text)  # BostonMolassesDisaster -> Boston Molasses Disaster
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in GENERIC}


def relevant(query: str, text: str) -> bool:
    """Görselin başlığı/açıklaması/kategorileri sorgudaki anlamlı kelimelerin en az %60'ını içermeli."""
    q = _tokens(query)
    if not q:
        return True
    hit = len(q & _tokens(text))
    return hit >= max(1, -(-len(q) * 6 // 10))


def find_any(queries: list[str], cache_dir: Path, exclude: set[str] | None = None) -> tuple[Path, ImageCredit] | None:
    """Sorguları sırayla dener: önce Wikimedia, sonra Openverse. Konuyla eşleşmeyen sonuçları reddeder."""
    for q in [q for q in queries if q.strip()]:
        for fn in (find_image, find_openverse):
            try:
                found = fn(q, cache_dir, exclude)
            except Exception as e:  # noqa: BLE001
                print(f"Görsel aranamadı ({q}, {fn.__name__}): {e}")
                found = None
            if found:
                return found
    return None


def find_openverse(query: str, cache_dir: Path, exclude: set[str] | None = None) -> tuple[Path, ImageCredit] | None:
    """Openverse (Flickr, müzeler vb.): yalnızca CC0, kamu malı, CC BY, CC BY-SA."""
    exclude = exclude or set()
    r = _get("https://api.openverse.org/v1/images/", timeout=30, params={
        "q": query, "license": "cc0,pdm,by,by-sa" if os.environ.get("ALLOW_CC_BY", "1") == "1" else "cc0,pdm", "page_size": 20, "mature": "false"})
    for it in r.json().get("results", []):
        if (it.get("width") or 0) < 600 or it.get("filetype") not in (None, "jpg", "jpeg", "png"):
            continue
        if (it.get("foreign_landing_url") or it["url"]) in exclude:
            continue
        text = " ".join([it.get("title") or ""] + [t.get("name", "") for t in it.get("tags") or []])
        if not relevant(query, text):
            continue
        url = it["url"]
        out = cache_dir / (hashlib.md5(url.encode()).hexdigest() + ".jpg")
        if not out.exists():
            try:
                out.write_bytes(_get(url, timeout=60).content)
            except Exception:  # noqa: BLE001
                continue
        lic = {"cc0": "CC0", "pdm": "Public domain"}.get(it["license"], f"CC {it['license'].upper()} {it.get('license_version', '')}".strip())
        return out, ImageCredit(file=str(out), title=it.get("title") or "Untitled",
                                author=it.get("creator") or "Bilinmiyor", license=lic,
                                page=it.get("foreign_landing_url") or "", source=f"Openverse/{it.get('source', '')}")
    return None


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
        "gsrsearch": f"{query} filemime:image/png" if prefer_png else f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 25,
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
        if p["title"] in exclude or info.get("descriptionurl") in exclude:
            continue
        text = " ".join([p["title"], _strip(meta.get("ImageDescription", {}).get("value", "")),
                         meta.get("Categories", {}).get("value", "").replace("|", " ")])
        if not relevant(query, text):
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
    """Tek satırlık kısa görsel atfı. Kamu malı/CC0 görseller atıf gerektirmediği için yazılmaz."""
    seen, parts = set(), []
    for c in credits:
        lic = (c.license or "").lower()
        if c.page in seen or any(k in lic for k in ("public domain", "pd", "cc0", "kamu")):
            continue
        seen.add(c.page)
        parts.append(f"{(c.author or 'bilinmiyor')[:40]} ({c.license})")
    return "📷 " + ", ".join(parts) if parts else ""


def credit_dict(c: ImageCredit) -> dict:
    return asdict(c)
