"""YouTube'a yeniden yükleme: sahibinin Studio'dan sildiği videoyu yalnız YouTube için yeniden sıraya koyar.

Eski YouTube kaydı ``youtube_onceki`` listesine taşınır, video ``zamanlandi`` olur ve takvimde yalnız YouTube'un
saati değişir; diğer platformlar zaten paylaşıldığı için (``_done``) yeniden yüklenmez.
Kullanım (youtube_tekrar.yml): TAG="t1,t2" ZAMAN="iso1,iso2" python -m shortgen.youtube_tekrar
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ETIKET = re.compile(r"short-\d{8}-\d{4,6}")


def isaretle(vids: list[dict], tag: str, zaman: dt.datetime) -> dict:
    v = next((x for x in vids if x.get("tag") == tag), None)
    if not v:
        raise ValueError(f"Video bulunamadı: {tag}")
    if v.get("status") == "yayinlaniyor":
        raise ValueError(f"{tag} şu an paylaşılıyor; bitince yeniden dene")
    platforms = v.setdefault("platforms", {})
    eksik = [k for k, r in platforms.items() if k != "youtube" and (r or {}).get("status") != "ok"]
    if eksik:  # paylaşım işi onları da yeniden denerdi; bu iş yalnız YouTube içindir
        raise ValueError(f"{tag}: {', '.join(eksik)} paylaşılmamış; önce onu düzelt")
    eski = platforms.pop("youtube", None)
    if eski:
        v.setdefault("youtube_onceki", []).append(eski)
    iso = zaman.isoformat(timespec="seconds")
    sched = {k: t for k, t in (v.get("schedule") or {}).items() if k != "youtube"}
    sched["youtube"] = iso
    v["schedule"] = sched
    v["status"] = "zamanlandi"
    v["publish_at"] = iso
    return v


def main() -> None:
    tags = [t.strip() for t in (os.environ.get("TAG") or "").split(",") if t.strip()]
    zamanlar = [z.strip() for z in (os.environ.get("ZAMAN") or "").split(",") if z.strip()]
    if not tags or any(not ETIKET.fullmatch(t) for t in tags):
        sys.exit(f"::error::Geçersiz etiket: {os.environ.get('TAG')!r}")
    if zamanlar and len(zamanlar) not in (1, len(tags)):
        sys.exit("::error::Zaman sayısı etiket sayısıyla aynı (ya da tek) olmalı")
    now = dt.datetime.now(dt.timezone.utc)
    p = ROOT / "state" / "videos.json"
    vids = json.loads(p.read_text(encoding="utf-8"))
    for i, tag in enumerate(tags):
        z = zamanlar[i] if len(zamanlar) == len(tags) else (zamanlar[0] if zamanlar else "")
        try:
            when = dt.datetime.fromisoformat(z) if z else now
            if when.tzinfo is None:
                raise ValueError("saat dilimi yok")
        except ValueError as e:
            sys.exit(f"::error::Geçersiz zaman {z!r}: {e}")
        try:
            v = isaretle(vids, tag, max(when, now))
        except ValueError as e:
            sys.exit(f"::error::{e}")
        print("YouTube'a yeniden yüklenecek:", tag, v["publish_at"], "|", v.get("title"))
    p.write_text(json.dumps(vids, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
