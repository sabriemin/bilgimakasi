"""Konu sırası: panelden düzenlenen, otomatik üretimde gündem önerisinden önce kullanılan konular.

Dosya: state/konu_sirasi.json  {"konular": ["...", ...], "guncellendi": "<ISO>", "rid": "<son panel isteği>"}
- Panel (işle.yml -> telegram_bot.process_panel) listeyi kaydeder (en fazla 30 konu, her biri en fazla 300 karakter).
  Sayfanın yüklediği liste (taban) de gelir: kayıt save_merged ile üç yollu yapılır, sayfa açıkken üretimin sıradan
  aldığı konu eski sayfadan kaydedilince geri gelmez. "rid", panelin kaydın işlendiğini görmesi içindir.
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


def _rid(text: str | None) -> str | None:
    try:
        d = json.loads(text or "")
    except ValueError:
        return None
    r = d.get("rid") if isinstance(d, dict) else None
    return r if isinstance(r, str) and r else None


def _items(text: str | None) -> list[str]:
    try:
        d = json.loads(text or "")
    except ValueError:
        return []
    items = d.get("konular") if isinstance(d, dict) else d
    if not isinstance(items, list):
        return []
    return [" ".join(x.split()) for x in items if isinstance(x, str) and x.strip()]  # boş konu sırayı tıkamasın


def load(path: Path | None = None) -> list[str]:
    p = path or FILE
    return _items(p.read_text(encoding="utf-8")) if p.exists() else []


def _dump(items: list[str], rid: str | None = None) -> str:
    d = {"konular": items, "guncellendi": dt.datetime.now(TR).isoformat(timespec="seconds")}
    if rid:
        d["rid"] = rid
    return json.dumps(d, ensure_ascii=False, indent=2)


def save(items: list[str], path: Path | None = None, rid: str | None = None) -> None:
    """rid verilmezse (ör. üretim konu çıkarırken) dosyadaki son panel kaydının numarası korunur."""
    p = path or FILE
    if rid is None and p.exists():
        rid = _rid(p.read_text(encoding="utf-8"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_dump(items, rid), encoding="utf-8")


def save_merged(base: list[str], items: list[str], rid: str | None = None, path: Path | None = None) -> list[str]:
    """Panel kaydı: base = sayfanın yüklediği liste, items = kullanıcının yeni listesi, dosya = şimdiki hâl."""
    p = path or FILE
    cur = p.read_text(encoding="utf-8") if p.exists() else None
    out = _items(merge(_dump(base), cur, _dump(items)))
    save(out, p, rid=rid)
    return out


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
    rb, rr, rl = _rid(base), _rid(remote), _rid(local)
    return _dump(out[:MAX_ITEMS], rl if rl != rb else rr)
