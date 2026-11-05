"""Konu sırası: panelden düzenlenen, otomatik üretimde gündem önerisinden önce kullanılan konular.

Dosya: state/konu_sirasi.json  {"konular": ["...", ...], "guncellendi": "<ISO>"}
- Panel (işle.yml -> telegram_bot.process_panel) listeyi kaydeder (en fazla 30 konu, her biri en fazla 300 karakter).
- Konusuz üretimde (pipeline.main) ilk konu alınır; senaryo yazıldıktan sonra listeden çıkarılır.
- state_sync aynı anda iki yerden değişen listeyi merge() ile birleştirir (ör. üretim ilk konuyu alırken panelden
  sıra değiştirildiyse ikisi de korunur).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "state" / "konu_sirasi.json"
MAX_ITEMS, MAX_LEN = 30, 300
TR = dt.timezone(dt.timedelta(hours=3))


def clean(items) -> list[str]:
    """Panelden gelen listeyi doğrular: boşluklar sadeleşir, boş ve tekrar eden konular atılır."""
    if not isinstance(items, list):
        raise ValueError("Konu sırası bir liste olmalı.")
    out: list[str] = []
    for x in items:
        if not isinstance(x, str):
            raise ValueError("Konular yazı olmalı.")
        t = " ".join(x.split())
        if not t:
            continue
        if len(t) > MAX_LEN:
            raise ValueError(f"Bir konu en fazla {MAX_LEN} karakter olabilir.")
        if t not in out:
            out.append(t)
    if len(out) > MAX_ITEMS:
        raise ValueError(f"Sırada en fazla {MAX_ITEMS} konu olabilir.")
    return out


def _items(text: str | None) -> list[str]:
    try:
        d = json.loads(text or "")
    except ValueError:
        return []
    items = d.get("konular") if isinstance(d, dict) else d
    return [x for x in items if isinstance(x, str)] if isinstance(items, list) else []


def load(path: Path | None = None) -> list[str]:
    p = path or FILE
    return _items(p.read_text(encoding="utf-8")) if p.exists() else []


def _dump(items: list[str]) -> str:
    return json.dumps({"konular": items, "guncellendi": dt.datetime.now(TR).isoformat(timespec="seconds")},
                      ensure_ascii=False, indent=2)


def save(items: list[str], path: Path | None = None) -> None:
    p = path or FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_dump(items), encoding="utf-8")


def peek(path: Path | None = None) -> str | None:
    items = load(path)
    return items[0] if items else None


def remove(topic: str, path: Path | None = None) -> bool:
    items = load(path)
    if topic not in items:
        return False
    items.remove(topic)
    save(items, path)
    return True


def merge(base: str | None, remote: str | None, local: str | None) -> str:
    """İki taraf da değiştirdiyse: yalnız konu çıkaran taraf (üretim) diğerinin listesinden o konuları siler;
    ikisi de düzenlediyse yerel sıra korunur, uzakta silinenler silinir, uzakta eklenenler sona eklenir."""
    b, r, l = _items(base), _items(remote), _items(local)
    gone_l, gone_r = set(b) - set(l), set(b) - set(r)
    if not set(l) - set(b) and [x for x in b if x in l] == l:  # yerel taraf yalnız çıkardı
        out = [x for x in r if x not in gone_l]
    elif not set(r) - set(b) and [x for x in b if x in r] == r:  # uzak taraf yalnız çıkardı
        out = [x for x in l if x not in gone_r]
    else:
        out = [x for x in l if x not in gone_r] + [x for x in r if x not in l and x not in b]
    return _dump(out[:MAX_ITEMS])
