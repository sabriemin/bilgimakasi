"""Haftalık yayın takvimi: her serinin sabit günü ve saati (Sabri 5 Kasım 2026'da onayladı, haftada 20 video; Kelimenin Kökeni ve yeni saatler 6 Kasım 2026: hafta içi 12:00/17:00/21:00, hafta sonu 11:30/15:30/20:30).

Onayda '🎯' seçilirse video kendi serisinin bir sonraki boş saatine konur ve üç platformda aynı anda paylaşılır.
Saatler Türkiye saatidir.

Tek kaynak state/yayin_plani.json'dur (panel de oradan okur). Dosya yoksa ya da bozuksa aşağıdaki sabitler kullanılır."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

PLAN = Path(__file__).resolve().parent.parent / "state" / "yayin_plani.json"

TR = dt.timezone(dt.timedelta(hours=3))

SERI_ADI = {"genel": "Genel", "nasil": "Nasıl yapılır?", "uretim": "Nasıl Üretiliyor?", "olsaydin": "Ya Sen Olsaydın?",
            "efsane": "Efsane mi, gerçek mi?", "kitap": "Bir Kitap Bir Dakika", "belgesel": "Mini Belgesel",
            "koken": "Kelimenin Kökeni"}

# Pazartesi = 0
HAFTA: dict[int, list[tuple[str, str]]] = {
    0: [("12:00", "nasil"), ("17:00", "genel"), ("21:00", "belgesel")],
    1: [("12:00", "efsane"), ("17:00", "genel"), ("21:00", "kitap")],
    2: [("12:00", "uretim"), ("17:00", "genel"), ("21:00", "belgesel")],
    3: [("12:00", "koken"), ("17:00", "genel"), ("21:00", "olsaydin")],
    4: [("12:00", "nasil"), ("17:00", "genel"), ("21:00", "belgesel")],
    5: [("11:30", "efsane"), ("15:30", "olsaydin")],
    6: [("11:30", "koken"), ("15:30", "uretim"), ("20:30", "kitap")],
}

# Kullanılmayacak saatler (TR, "YYYY-AA-GG SS:DD"): 10 Kasım akşamı Atatürk'ü anma günü
KAPALI = {"2026-11-10 17:00"}

_SABLON_SERI = {"nasil": "nasil", "uretim": "uretim", "isemri": "uretim", "ajanda": "olsaydin", "dosya": "efsane",
                "kitap": "kitap", "belgesel": "belgesel"}

# Serinin ilk yayın günü (bu günden önceki saatleri kullanılmaz): Karar Senin 16 Kasım'da başlıyor
BASLANGIC: dict[str, dt.date] = {}

_GUN = {"pazartesi": 0, "salı": 1, "çarşamba": 2, "perşembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}


def _saat(x: object) -> str:
    h, m = map(int, str(x).split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(x)
    return f"{h:02d}:{m:02d}"


def plan_oku(yol: Path = PLAN) -> dict | None:
    """state/yayin_plani.json'u okur ve doğrular: {hafta, kapali, seri_adi, sablon_seri, baslangic}; yoksa None."""
    try:
        d = json.loads(yol.read_text(encoding="utf-8"))
        hafta: dict[int, list[tuple[str, str]]] = {i: [] for i in range(7)}
        for g in d["hafta"]:
            i = _GUN[str(g["gun"]).lower()]
            hafta[i] = sorted((_saat(x["saat"]), str(x["seri"])) for x in g["slotlar"])
        kapali = set()
        for x in d.get("istisnalar") or []:
            gun, hm = str(x["zaman"]).split()
            kapali.add(f"{dt.date.fromisoformat(gun):%Y-%m-%d} {_saat(hm)}")
        seriler = d.get("seriler") or []
        seri_adi = {str(x["key"]): str(x["ad"]) for x in seriler if x.get("key") and x.get("ad")}
        baslangic = {str(x["key"]): dt.date.fromisoformat(x["baslangic"]) for x in seriler if x.get("baslangic")}
        sablon_seri = {str(k): str(v) for k, v in (d.get("sablon_seri") or {}).items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not any(hafta.values()):
        return None
    return {"hafta": hafta, "kapali": kapali, "seri_adi": seri_adi, "sablon_seri": sablon_seri, "baslangic": baslangic}


_P = plan_oku()
if _P:
    HAFTA = _P["hafta"]
    KAPALI = _P["kapali"]
    SERI_ADI = {**SERI_ADI, **_P["seri_adi"]}
    _SABLON_SERI = _P["sablon_seri"] or _SABLON_SERI
    BASLANGIC = _P["baslangic"]


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
            if s != seri or f"{day:%Y-%m-%d} {hm}" in KAPALI or day < BASLANGIC.get(s, day):
                continue
            h, m = map(int, hm.split(":"))
            t = dt.datetime.combine(day, dt.time(h, m), TR)
            if t <= now + dt.timedelta(minutes=15):
                continue
            if all(abs(t - b) >= bosluk for b in dolu):
                return t
    return None
