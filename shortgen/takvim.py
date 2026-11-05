"""Haftalık yayın takvimi: her serinin sabit günü ve saati (Sabri 5 Kasım 2026'da onayladı, haftada 18 video).

Onayda '🎯' seçilirse video kendi serisinin bir sonraki boş saatine konur ve üç platformda aynı anda paylaşılır.
Saatler Türkiye saatidir."""
from __future__ import annotations

import datetime as dt

TR = dt.timezone(dt.timedelta(hours=3))

SERI_ADI = {"genel": "Genel", "nasil": "Nasıl yapılır?", "uretim": "Nasıl Üretiliyor?", "olsaydin": "Ya Sen Olsaydın?",
            "efsane": "Efsane mi, gerçek mi?", "kitap": "Bir Kitap Bir Dakika", "karar": "Karar Senin"}

# Pazartesi = 0
HAFTA: dict[int, list[tuple[str, str]]] = {
    0: [("11:30", "nasil"), ("18:00", "genel"), ("21:00", "karar")],
    1: [("13:00", "efsane"), ("18:00", "genel"), ("22:00", "kitap")],
    2: [("16:30", "uretim"), ("18:00", "genel"), ("21:00", "karar")],
    3: [("18:00", "genel"), ("19:30", "olsaydin")],
    4: [("11:30", "nasil"), ("18:00", "genel"), ("21:00", "karar")],
    5: [("13:00", "efsane"), ("19:30", "olsaydin")],
    6: [("16:30", "uretim"), ("22:00", "kitap")],
}

# Kullanılmayacak saatler (TR, "YYYY-AA-GG SS:DD"): 10 Kasım akşamı Atatürk'ü anma günü
KAPALI = {"2026-11-10 18:00"}

_SABLON_SERI = {"nasil": "nasil", "uretim": "uretim", "isemri": "uretim", "ajanda": "olsaydin", "dosya": "efsane",
                "kitap": "kitap", "cizgi": "karar"}


def seri_of(v: dict) -> str:
    """Videonun serisi: önce anlatım kalıbı (structure), yoksa şablon; ikisi de seri değilse 'genel'."""
    s = v.get("structure")
    if s in HAFTA_SERILER:
        return s
    return _SABLON_SERI.get(str(v.get("template") or ""), "genel")


HAFTA_SERILER = {s for g in HAFTA.values() for _, s in g}


def sonraki_saat(seri: str, dolu: list[dt.datetime], now: dt.datetime | None = None,
                 bosluk: dt.timedelta = dt.timedelta(minutes=30), gun: int = 28) -> dt.datetime | None:
    """Serinin en az 15 dk sonraki, başka bir videoya ayrılmamış ilk takvim saati (TR saat dilimli) ya da None."""
    now = (now or dt.datetime.now(TR)).astimezone(TR)
    for d in range(gun):
        day = now.date() + dt.timedelta(days=d)
        for hm, s in HAFTA.get(day.weekday(), []):
            if s != seri or f"{day:%Y-%m-%d} {hm}" in KAPALI:
                continue
            h, m = map(int, hm.split(":"))
            t = dt.datetime.combine(day, dt.time(h, m), TR)
            if t <= now + dt.timedelta(minutes=15):
                continue
            if all(abs(t - b) >= bosluk for b in dolu):
                return t
    return None
