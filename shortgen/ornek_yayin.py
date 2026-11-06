"""Örnek videoyu yayına alma (ornek_yayinla.yml): ornek.yml'in iş çıktısındaki ("ornek-video") hazır videolar yeniden
çizilmeden normal üretim gibi kayda alınır: GitHub Release, videos.json (onay_bekliyor), geçmiş, Telegram onay mesajı.

İş çıktısının düzeni: tek videoda dosyalar kökte; Mini Belgesel'de her bölüm kendi klasöründe (…-b1/, …-b2/).
Bir çalışma tek bir yayın birimidir: Mini Belgesel'in iki bölümü birlikte (seri_id ve bölüm numarasıyla) alınır ki
1. bölüm onaylanınca 2. bölüm kendiliğinden zamanlansın.

    python -m shortgen.ornek_yayin hazirla <kök> <run_id>   # plan.tsv: etiket, klasör, yeni mi (1/0)
    python -m shortgen.ornek_yayin kaydet <kök> <run_id>    # yeni bölümler: Telegram onay mesajı + kayıt + geçmiş
    python -m shortgen.ornek_yayin onizleme <kök> <alindi|zaten|geri> [mesaj_no]   # örnek mesajlarının düğmesi
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import telegram_bot as tb

ROOT = Path(__file__).resolve().parent.parent
DOSYALAR = ("video.mp4", "metadata.json", "script.json")  # uret.yml'in Release'e koyduğu dosyalar
PLAN = "plan.tsv"
ONIZLEME = "telegram.json"  # ornek.yml: örnek mesajının numarası (düğmesi yayına alınınca değişir)


def dugme(run_id: str) -> list:
    """Örnek mesajının düğmesi (callback: oy:<run_id>; bir çalışmanın tüm bölümleri birlikte alınır)."""
    return [[("📥 Yayına al", f"oy:{run_id}")]]


def klasorler(kok: Path) -> list[Path]:
    """İş çıktısındaki video klasörleri, bölüm sırasıyla. Eksik dosya ya da birbirine bağlı olmayan klasörler varsa durur."""
    kok = Path(kok)
    if (kok / "metadata.json").exists():
        dirs = [kok]
    else:
        dirs = [d for d in sorted(kok.iterdir()) if d.is_dir() and (d / "metadata.json").exists()]
    if not dirs:
        raise SystemExit("İş çıktısında video bulunamadı (metadata.json yok).")
    for d in dirs:
        eksik = [f for f in DOSYALAR if not (d / f).is_file()]
        if eksik:
            raise SystemExit(f"{d.name}: eksik dosya {', '.join(eksik)}")
    metas = [_meta(d) for d in dirs]
    if len(dirs) > 1:
        sid = {m.get("seri_id") for m in metas}
        bolumler = sorted(m.get("bolum") or 0 for m in metas)
        if len(sid) != 1 or None in sid or bolumler != list(range(1, len(dirs) + 1)):
            raise SystemExit("Birden çok video var ama tek bir serinin bölümleri değil; yayına alınmadı.")
    return [d for _, d in sorted(zip(metas, dirs), key=lambda x: (x[0].get("bolum") or 0, x[1].name))]


def _meta(d: Path) -> dict:
    return json.loads((d / "metadata.json").read_text(encoding="utf-8"))


def _ayni(v: dict, m: dict) -> bool:
    """Kayıt bu örnek videonun mu (üretim anı ve konu aynı; bölümlü seride bölüm de)."""
    return v.get("created") == m["created"] and v.get("topic") == m["topic"] and v.get("bolum") == m.get("bolum")


def plan(dirs: list[Path], videos: list[dict]) -> list[tuple[str, Path, bool]]:
    """(etiket, klasör, yeni mi). Etiket örneğin üretim anından gelir (short-YYYYMMDD-HHMMSS): aynı örnek her denemede
    aynı etiketi alır, yarım kalan iş yeniden çalışabilir. Bölümler bir saniye arayla, başka videonun etiketiyle
    çakışmadan sıralanır (uret.yml'deki gibi). Daha önce kayda alınmış bölüm kendi kayıtlı etiketini korur."""
    out: list[tuple[str, Path, bool]] = []
    son: dt.datetime | None = None
    for d in dirs:
        m = _meta(d)
        kayit = next((v for v in videos if _ayni(v, m)), None)
        if kayit:
            out.append((kayit["tag"], d, False))
            son = max(son, _an(kayit["tag"])) if son else _an(kayit["tag"])
            continue
        t = dt.datetime.fromisoformat(m["created"]).replace(tzinfo=None, microsecond=0)
        if son and t <= son:
            t = son + dt.timedelta(seconds=1)
        dolu = {v["tag"] for v in videos} | {x[0] for x in out}
        while _etiket(t) in dolu:
            t += dt.timedelta(seconds=1)
        out.append((_etiket(t), d, True))
        son = t
    return out


def _etiket(t: dt.datetime) -> str:
    return f"short-{t:%Y%m%d-%H%M%S}"


def _an(tag: str) -> dt.datetime:
    try:
        return dt.datetime.strptime(tag, "short-%Y%m%d-%H%M%S")
    except ValueError:
        return dt.datetime.min


def plan_oku(kok: Path) -> list[tuple[str, Path, bool]]:
    satirlar = (Path(kok) / PLAN).read_text(encoding="utf-8").splitlines()
    return [(t, Path(d), y == "1") for t, d, y in (s.split("\t") for s in satirlar if s.strip())]


def hazirla(kok: Path, run_id: str) -> list[tuple[str, Path, bool]]:
    p = plan(klasorler(kok), tb.load(tb.VIDEOS, []))
    (Path(kok) / PLAN).write_text("".join(f"{t}\t{d}\t{int(y)}\n" for t, d, y in p), encoding="utf-8")
    for t, d, y in p:
        m = _meta(d)
        print(f"{t} {'yeni' if y else 'zaten kayıtlı'} | {m['title']} | şablon: {m.get('template')}"
              + (f" | bölüm {m.get('bolum')}/{m.get('bolum_sayisi')}" if m.get("bolum") else ""))
    env = os.environ.get("GITHUB_ENV")
    if env:
        with open(env, "a", encoding="utf-8") as f:
            f.write(f"TAG={p[0][0]}\nYENI={sum(y for _, _, y in p)}\n")
    return p


def kaydet(kok: Path, run_id: str) -> list[str]:
    """Yeni bölümleri sırayla Telegram'a onay mesajıyla gönderir (telegram_bot.notify: videos.json kaydı, seri_id ve
    bölüm dahil) ve geçmişe yazar. Her bölüm kendi kaydını hemen yazar: yarıda kalan iş tekrarlanınca kalan bölümden
    sürer. Gönderilen etiketleri döndürür."""
    yeni = []
    for tag, d, y in plan_oku(kok):
        if not y or tb._find(tb.load(tb.VIDEOS, []), tag):
            continue
        tb.notify(d, tag)
        m = _meta(d)
        with (ROOT / "history.jsonl").open("a", encoding="utf-8") as f:  # konu tekrar seçilmesin, format sayısı doğru
            f.write(json.dumps({"date": str(dt.date.today()), "topic": m["topic"], "dir": f"ornek:{run_id}",
                                "structure": m.get("structure"), "search_phrase": m.get("search_phrase"),
                                "series_part": m.get("series_part")}, ensure_ascii=False) + "\n")
        yeni.append(tag)
    return yeni


def _mesajlar(kok: Path) -> list[int]:
    out = []
    for d in klasorler_sessiz(kok):
        try:
            mid = json.loads((d / ONIZLEME).read_text(encoding="utf-8")).get("message_id")
        except (OSError, ValueError):
            continue
        if isinstance(mid, int):
            out.append(mid)
    return out


def klasorler_sessiz(kok: Path) -> list[Path]:
    """İş çıktısı indirilemediyse ya da bozuksa boş liste (hata bildiriminde kullanılır)."""
    try:
        return klasorler(kok)
    except (SystemExit, OSError, ValueError):
        return []


def onizleme(kok: Path, durum: str, run_id: str = "", mesaj: str = "") -> None:
    """Örnek mesajlarının düğmesi. alindi/zaten: düğme kalkar ve ilk örnek mesajına kısa not yazılır. geri: iş yarım
    kaldı, '📥 Yayına al' düğmesi geri konur (tekrar denenebilsin). mesaj: basılan mesajın numarası (iş çıktısı
    indirilemese de o mesajın düğmesi geri konur)."""
    chat = os.environ["TELEGRAM_CHAT_ID"]
    mids = _mesajlar(kok)
    if mesaj.isdigit() and int(mesaj) not in mids:
        mids.append(int(mesaj))
    kb = tb._kb([] if durum in ("alindi", "zaten") else dugme(run_id))
    for mid in mids:
        try:
            tb.api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": kb})
        except Exception as e:  # noqa: BLE001
            print("Örnek mesajının düğmesi değiştirilemedi:", tb._redact_safe(e))
    if durum == "geri":
        return
    p = plan_oku(kok) if (Path(kok) / PLAN).exists() else []
    etiketler = ", ".join(t for t, _, _ in p)
    metin = (f"📥 Yayına alındı ({etiketler}). Onay mesajı aşağıda; ✅ Onayla ile paylaşım saatini seç."
             if durum == "alindi" else f"ℹ️ Bu örnek zaten yayına alınmış ({etiketler}). Onay mesajı daha önce gönderildi.")
    data = {"chat_id": chat, "text": metin}
    if mids:
        data["reply_to_message_id"] = mids[0]
        data["allow_sending_without_reply"] = "true"
    tb.api("sendMessage", data=data)


if __name__ == "__main__":
    cmd, kok = sys.argv[1], Path(sys.argv[2])
    if cmd == "hazirla":
        hazirla(kok, sys.argv[3])
    elif cmd == "kaydet":
        print("Gönderilen:", ", ".join(kaydet(kok, sys.argv[3])) or "yok")
    elif cmd == "onizleme":
        onizleme(kok, sys.argv[3], os.environ.get("RUN_ID", ""), sys.argv[4] if len(sys.argv) > 4 else "")
    else:
        raise SystemExit(f"bilinmeyen komut: {cmd}")
