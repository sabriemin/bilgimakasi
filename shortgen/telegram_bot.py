"""Telegram onay botu.

notify <klasör> <etiket>: Yeni videoyu Onayla / Reddet düğmeleriyle Telegram'a gönderir.
poll: Düğme basışlarını ve komutları okur, state/videos.json dosyasını günceller.
publish-due: Paylaşım saati gelen onaylı videoları platformlara yükler ve sonucu Telegram'a yazar.

Akış: Onayla -> saat seç (Şimdi / bugün 19:00 / yarın 12:00 / yarın 19:00) -> o saatte otomatik paylaşım.
Komutlar: /durum (bekleyen ve zamanlananlar), /uret [konu] (hemen yeni video üret).
Yalnızca TELEGRAM_CHAT_ID'deki kişiden gelen mesajlar işlenir.
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TR = dt.timezone(dt.timedelta(hours=3))  # Türkiye saati (yaz saati uygulaması yok)
PLATFORM_NAMES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}
STATE = ROOT / "state"
VIDEOS = STATE / "videos.json"
OFFSET = STATE / "telegram_offset.json"


_QUIET = {"Ne zaman paylaşılsın?", "Üretim başladı", ""}


def api(method: str, **kw):
    if method == "answerCallbackQuery" and os.environ.get("TG_WEBHOOK") == "1":
        # düğmeye anında "⏳ Alındı" cevabını Cloudflare kapısı verdi; buradaki bilgi notunu mesaj olarak gönder
        text = (kw.get("data") or {}).get("text", "")
        if text not in _QUIET:
            return api("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text})
        return None
    r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}", timeout=120, **kw)
    if not r.ok:
        desc = r.json().get("description", "") if r.headers.get("content-type", "").startswith("application/json") else ""
        # önemsiz hatalar: eski düğme sorgusu, değişmeyen klavye
        if method in ("answerCallbackQuery", "editMessageReplyMarkup") and (
                "query is too old" in desc or "not modified" in desc or "query ID is invalid" in desc):
            print(f"Telegram {method} atlandı: {desc}")
            return None
        raise RuntimeError(f"Telegram {method} hatası {r.status_code}: {desc}")
    return r.json()["result"]


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def notify(out_dir: Path, tag: str) -> None:
    meta = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    chat = os.environ["TELEGRAM_CHAT_ID"]
    caption = f"🎬 <b>{meta['title']}</b>\n\nKonu: {meta['topic']}\nŞablon: {meta.get('template', '-')}"
    kb = {"inline_keyboard": [[
        {"text": "✅ Onayla", "callback_data": f"ok:{tag}"},
        {"text": "❌ Reddet", "callback_data": f"no:{tag}"},
    ]]}
    with (out_dir / "video.mp4").open("rb") as f:
        msg = api("sendVideo", data={"chat_id": chat, "caption": caption, "parse_mode": "HTML",
                                     "supports_streaming": "true", "reply_markup": json.dumps(kb)},
                  files={"video": f})
    api("sendMessage", data={"chat_id": chat, "text": meta["description"][:4000],
                             "reply_to_message_id": msg["message_id"]})
    videos = load(VIDEOS, [])
    videos.append({"tag": tag, "title": meta["title"], "topic": meta["topic"], "category": meta["category"],
                   "template": meta.get("template"), "created": meta["created"], "status": "onay_bekliyor",
                   "telegram_message_id": msg["message_id"], "platforms": {}})
    save(VIDEOS, videos)


def _find(videos: list, tag: str) -> dict | None:
    return next((v for v in videos if v["tag"] == tag), None)


def _refresh_videos() -> None:
    """Dinleme işi başladıktan sonra üretilen videoları uzak depodan alır (yerel değişikliklere dokunmaz)."""
    import subprocess
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, check=True, timeout=60)
        remote = json.loads(subprocess.run(["git", "show", "origin/main:state/videos.json"], cwd=ROOT,
                                           capture_output=True, text=True, check=True).stdout)
    except Exception as e:  # noqa: BLE001
        print("Uzak durum alınamadı:", e)
        return
    videos = load(VIDEOS, [])
    have = {v["tag"] for v in videos}
    new = [v for v in remote if v["tag"] not in have]
    if new:
        save(VIDEOS, videos + new)
        print("Uzaktan eklenen videolar:", [v["tag"] for v in new])


def _update(tag: str, **fields) -> dict | None:
    videos = load(VIDEOS, [])
    v = _find(videos, tag)
    if v:
        v.update(fields)
        save(VIDEOS, videos)
    return v


# Türkiye'deki kitle için platform başına önerilen paylaşım saatleri (TR saati).
# BEST_TIMES ortam değişkeniyle (JSON) değiştirilebilir, ör. {"youtube": ["18:00"], ...}
BEST_TIMES = json.loads(os.environ.get("BEST_TIMES") or json.dumps({
    "youtube": ["18:00", "21:00"],
    "instagram": ["12:30", "20:00"],
    "tiktok": ["19:30", "22:00"],
}))
# Ek saatler: o günün kalan (en az 15 dk sonraki) asıl saatleri başka videolara ayrılmışsa kullanılır
# (ör. aynı güne 3. video ya da günün ilk asıl saati geçtikten sonra gelen 2. video).
# EXTRA_TIMES ile değiştirilebilir.
EXTRA_TIMES = json.loads(os.environ.get("EXTRA_TIMES") or json.dumps({
    "youtube": ["15:00"],
    "instagram": ["17:00"],
    "tiktok": ["17:00"],
}))
ICONS = {"youtube": "▶️", "instagram": "📸", "tiktok": "🎵"}


MIN_GAP = dt.timedelta(hours=float(os.environ.get("MIN_GAP_HOURS", "2")))


def _busy(exclude: str | None = None) -> dict[str, list[dt.datetime]]:
    """Platform bazında dolu saatler: zamanlanmış videolar + son 24 saatte paylaşılanlar."""
    busy: dict[str, list[dt.datetime]] = {p: [] for p in BEST_TIMES}
    for v in load(VIDEOS, []):
        if v.get("tag") == exclude:
            continue
        if v.get("status") == "zamanlandi":
            sched = v.get("schedule") or {p: v.get("publish_at") for p in BEST_TIMES}
            for p, t in sched.items():
                if t and p in busy:
                    busy[p].append(dt.datetime.fromisoformat(t))
        for p, r in (v.get("platforms") or {}).items():  # paylaşılanlar: platformun kendi paylaşım anı
            t = r.get("at") or v.get("published")
            if r.get("status") == "ok" and p in busy and t:
                busy[p].append(dt.datetime.fromisoformat(t))
    return busy


def _best_schedule(now: dt.datetime | None = None, exclude: str | None = None,
                   ignore_busy: bool = False) -> dict[str, str]:
    """Her platform için en az 15 dk sonraki, başka bir videoya ayrılmamış ilk önerilen saati (UTC ISO) döndürür.
    Aynı platformda iki paylaşım arasında en az MIN_GAP olur; bugünün saatleri doluysa sonraki günlere geçer."""
    now = now or dt.datetime.now(TR)
    busy = {} if ignore_busy else _busy(exclude)
    out = {}
    for p, times in BEST_TIMES.items():
        chosen = None
        for d in range(0, 7):
            for hm in sorted(times) + sorted(EXTRA_TIMES.get(p, [])):  # önce asıl saatler, sonra ek saat
                h, m = map(int, hm.split(":"))
                t = dt.datetime.combine(now.date() + dt.timedelta(days=d), dt.time(h, m), TR)
                if t <= now + dt.timedelta(minutes=15):
                    continue
                if all(abs(t - b) >= MIN_GAP for b in busy.get(p, [])):
                    chosen = t
                    break
            if chosen:
                break
        out[p] = (chosen or now + dt.timedelta(minutes=20)).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    return out


def _slots(now: dt.datetime | None = None, all_: bool = False) -> list[tuple[str, str, dt.datetime]]:
    """Saat seçenekleri: (kod, düğme yazısı, UTC zamanı). Geçmişte kalan saatler gösterilmez (all_=True hariç)."""
    now = now or dt.datetime.now(TR)
    today, tomorrow = now.date(), now.date() + dt.timedelta(days=1)
    out = [("best", "🎯 Her platform en iyi saatinde", now), ("now", "⚡ Şimdi", now)]
    for code, label, day, hour in (("b12", "Bugün 12:00", today, 12), ("b19", "Bugün 19:00", today, 19),
                                   ("y12", "Yarın 12:00", tomorrow, 12), ("y19", "Yarın 19:00", tomorrow, 19)):
        t = dt.datetime.combine(day, dt.time(hour), TR)
        if all_ or t > now + dt.timedelta(minutes=15):
            out.append((code, "🕒 " + label, t))
    return out


AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
GUNLER = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


def _fmt(iso: str) -> str:
    """Tarih her zaman açık yazılır (ör. "6 Kasım Cuma 12:30"): gece yarısı "bugün/yarın" karışıklığı olmasın."""
    t = dt.datetime.fromisoformat(iso).astimezone(TR)
    return f"{t.day} {AYLAR[t.month - 1]} {GUNLER[t.weekday()]} {t:%H:%M}"


def _is_extra(p: str, iso: str) -> bool:
    return f"{dt.datetime.fromisoformat(iso).astimezone(TR):%H:%M}" in EXTRA_TIMES.get(p, [])


def _sched_of(v: dict) -> dict[str, str]:
    return v.get("schedule") or ({p: v["publish_at"] for p in BEST_TIMES} if v.get("publish_at") else {})


def _done(v: dict) -> set[str]:
    return {p for p, r in (v.get("platforms") or {}).items() if r.get("status") == "ok"}


def _pending_sched(v: dict) -> dict[str, str]:
    """Henüz paylaşılmamış platformların saatleri (plan mesajlarında yalnız bunlar gösterilir).
    Saati geçmiş ama paylaşılamamış bir platform paylaşım işinin bir sonraki turunda (publish_at) yeniden denenir:
    planda o saatle gösterilir."""
    pa = v.get("publish_at")
    pa_t = dt.datetime.fromisoformat(pa) if pa else None
    return {p: (pa if pa_t and dt.datetime.fromisoformat(t) < pa_t else t)
            for p, t in _sched_of(v).items() if p not in _done(v)}


def _plan_text(tag: str, sched: dict[str, str], explain: bool = True) -> str:
    """Bir videonun platform saatleri. explain: plan az önce hesaplandıysa, asıl en iyi saatler başka videolara
    ayrıldığı için kaydığını ve hangi videolara ayrıldığını da yazar."""
    lines = [f"• {PLATFORM_NAMES[p]}: {_fmt(t)}" + (" (günün ek saati)" if _is_extra(p, t) else "")
             for p, t in sorted(sched.items(), key=lambda x: x[1])]
    free = _best_schedule(exclude=tag, ignore_busy=True) if explain and sched else {}
    if explain and sched and any(sched[p] != free.get(p) for p in sched):
        lo = dt.datetime.fromisoformat(min(free.values())).astimezone(TR).date()
        hi = dt.datetime.fromisoformat(max(sched.values())).astimezone(TR).date()
        others = [v["title"] for v in load(VIDEOS, []) if v.get("status") == "zamanlandi" and v.get("tag") != tag
                  and any(lo <= dt.datetime.fromisoformat(t).astimezone(TR).date() <= hi
                          for t in _pending_sched(v).values())]
        if others:
            lines.append("\nAsıl en iyi saatler şu videolara ayrılmıştı, aynı saate iki video konmadı:\n"
                         + "\n".join(f"  - {t[:60]}" for t in others))
    return "\n".join(lines)


def plan_all() -> str:
    """Zamanlanmış tüm videoların gün gün paylaşım planı (hangi video, hangi platformda, ne zaman)."""
    rows = []
    for v in load(VIDEOS, []):
        if v.get("status") == "zamanlandi":
            for p, t in _pending_sched(v).items():
                rows.append((dt.datetime.fromisoformat(t).astimezone(TR), p, v["title"]))
    if not rows:
        return "Zamanlanmış video yok."
    lines, day = [], None
    for t, p, title in sorted(rows):
        if t.date() != day:
            day = t.date()
            lines.append(f"\n📅 {t.day} {AYLAR[t.month - 1]} {GUNLER[t.weekday()]}")
        short = title if len(title) <= 42 else title[:42].rsplit(" ", 1)[0] + "…"
        lines.append(f"{t:%H:%M} {ICONS.get(p, '')} {PLATFORM_NAMES[p]}: {short}")
    return "\n".join(lines).strip()


def _kb(rows: list[list[tuple[str, str]]]) -> str:
    return json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in rows]})


# ---- Düğmeler ve panel için ortak işlemler (Telegram düğmesi ve panel aynı kodu kullanır) ----
def _suggestion_topic(it: dict) -> str:
    return f"{it['topic']} (kanca: {it['hook']}; gündem: {it['trend']})"


def _approve(tag: str, code: str, chat: str, mid: int) -> str:
    """Onay (kod: best|now|b12|b19|y12|y19): saati hesaplar ve kaydeder, video mesajının düğmesini 'iptal' yapar.
    Telegram'a yazılacak notu döndürür."""
    if code == "best":
        sched = _best_schedule(exclude=tag)
        iso = min(sched.values())
        note = "✅ Onaylandı. Her platform kendi en iyi saatinde paylaşılacak:\n" + _plan_text(tag, sched)
    else:
        # düğme gösterildikten sonra saat 15 dk sınırına girmiş olabilir: seçilen saati yine de kullan
        when = next((t for c, _, t in _slots(all_=True) if c == code), dt.datetime.now(TR))
        if when < dt.datetime.now(TR):
            when = dt.datetime.now(TR)
        iso = when.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
        sched = None
        note = "✅ Onaylandı. " + ("Birkaç dakika içinde paylaşılacak." if code == "now"
                                   else f"Paylaşım zamanı: {_fmt(iso)}")
    _update(tag, status="zamanlandi", publish_at=iso, schedule=sched,
            decided=dt.datetime.now(TR).isoformat(timespec="seconds"))
    api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb(
        [[("🚫 Paylaşımı iptal et", f"cancel:{tag}")]])})
    return note


def _cancel(tag: str, chat: str, v: dict) -> str | None:
    """Zamanlanmış paylaşımı (kalan platformları) iptal eder; video yeniden onay bekler. Zamanlanmış değilse None."""
    if v["status"] != "zamanlandi":
        return None
    _update(tag, status="onay_bekliyor", publish_at=None, schedule=None)
    api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": v["telegram_message_id"], "reply_markup": _kb(
        [[("✅ Onayla", f"ok:{tag}"), ("❌ Reddet", f"no:{tag}")]])})
    return "Paylaşım iptal edildi, video yeniden onay bekliyor."


def _reject(tag: str, chat: str, v: dict) -> str:
    _update(tag, status="reddedildi", decided=dt.datetime.now(TR).isoformat(timespec="seconds"))
    api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": v["telegram_message_id"],
                                        "reply_markup": _kb([])})
    note = "❌ Reddedildi."
    seri_file = STATE / "seri.json"
    if "(1. Bölüm)" in v.get("title", "") and seri_file.exists():  # 1. bölüm reddedilirse 2. bölüm üretilmesin
        seri = json.loads(seri_file.read_text(encoding="utf-8"))
        if seri.get("bekleyen", {}).get("title") == v["title"]:
            seri.pop("bekleyen")
            seri_file.write_text(json.dumps(seri, ensure_ascii=False, indent=2), encoding="utf-8")
            note += " Serinin 2. bölümü de iptal edildi."
    return note


def _retry(tag: str) -> str:
    """Hatalı platformları hemen yeniden dener (publish_due paylaşılmış platformlara tekrar yüklemez)."""
    _update(tag, status="zamanlandi", schedule=None,
            publish_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    return "Hatalı platformlar birkaç dakika içinde yeniden denenecek."


def _handle_callback(cq: dict, chat: str) -> None:
    action, _, rest = cq["data"].partition(":")
    tag, _, arg = rest.partition(":")
    if action == "cm":  # yorum cevabı: cm:ok:<anahtar> / cm:no:<anahtar>
        from . import comments
        note = comments.handle(tag, arg, chat, cq["message"]["message_id"])
        if note.startswith(("✅", "Gönderilemedi")):
            api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": ""})
            api("sendMessage", data={"chat_id": chat, "text": note, "reply_to_message_id": cq["message"]["message_id"]})
        else:
            api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": note[:190]})
        return
    if action == "tp":  # gündem önerisinden üretim
        from .trends import load_saved
        items = load_saved()
        i = int(arg) if arg.isdigit() else -1
        if not 0 <= i < len(items):
            api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": "Öneri bulunamadı."})
            return
        it = items[i]
        ok = _dispatch(_suggestion_topic(it))
        api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": "Üretim başladı" if ok else "Başlatılamadı"})
        api("sendMessage", data={"chat_id": chat, "text": (f"🎬 Üretim başladı: {it['topic']}\nYaklaşık 15 dakikada gelir."
                                                          if ok else "Üretim başlatılamadı.")})
        return
    videos = load(VIDEOS, [])
    v = _find(videos, tag)
    tries = 6 if os.environ.get("TG_WEBHOOK") == "1" else 1
    for i in range(tries):  # yeni video henüz depoya yazılmamış olabilir (üretim işi birkaç saniye sonra iter)
        if v:
            break
        if i:
            import time
            time.sleep(15)
        _refresh_videos()
        videos = load(VIDEOS, [])
        v = _find(videos, tag)
    if not v:
        _put_back(cq, chat)
        api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": "Video bulunamadı."})
        return
    mid = v["telegram_message_id"]
    note = ""
    if action == "ok":  # onay: saat seçeneklerini göster
        sl = _slots()
        rows = [[(lbl, f"at:{tag}:{code}") for code, lbl, _ in sl[i:i + 2]] for i in range(0, len(sl), 2)]
        rows.append([("↩️ Geri", f"back:{tag}")])
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb(rows)})
        note = "Ne zaman paylaşılsın?"
    elif action == "back":
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb(
            [[("✅ Onayla", f"ok:{tag}"), ("❌ Reddet", f"no:{tag}")]])})
    elif action == "at":
        note = _approve(tag, arg, chat, mid)
        api("sendMessage", data={"chat_id": chat, "text": f"{note}\n{v['title']}", "reply_to_message_id": mid})
    elif action == "cancel":
        note = _cancel(tag, chat, v)
        if note is None:
            note = "Bu video zaten paylaşıldı veya paylaşılıyor."
            if os.environ.get("TG_WEBHOOK") == "1":
                _restore_kb(tag, chat)
    elif action == "no":
        note = _reject(tag, chat, v)
        api("sendMessage", data={"chat_id": chat, "text": f"{note}\n{v['title']}", "reply_to_message_id": mid})
    elif action == "rt":  # hatalı platformları yeniden dene
        note = _retry(tag)
        if os.environ.get("TG_WEBHOOK") == "1":
            api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": cq["message"]["message_id"],
                                                "reply_markup": _kb([])})
    # "at" ve "no" notu zaten mesaj olarak gönderildi: baloncukta tekrar gösterme
    api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": "" if action in ("at", "no") else note[:190]})


COMMANDS = [
    {"command": "oneri", "description": "Türkiye ve dünya gündeminden 5 konu önerisi"},
    {"command": "uret", "description": "Hemen yeni video üret (ör. /uret kara delikler)"},
    {"command": "durum", "description": "Bekleyen ve zamanlanan videolar"},
    {"command": "rapor", "description": "İzlenme, takipçi, beğeni, kaydetme raporu"},
    {"command": "saatler", "description": "Platformların en iyi paylaşım saatleri"},
    {"command": "panel", "description": "Yönetim paneline giriş bağlantısı"},
    {"command": "yardim", "description": "Komut listesi"},
]
_menu_set = False


def _put_back(cq: dict, chat: str) -> None:
    """Webhook modunda kapı düğmeyi '⏳ İşleniyor' yaptı; işlem yapılamadıysa basılan klavyeyi aynen geri koy."""
    if os.environ.get("TG_WEBHOOK") != "1":
        return
    try:
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": cq["message"]["message_id"],
                                            "reply_markup": json.dumps(cq["message"].get("reply_markup")
                                                                       or {"inline_keyboard": []})})
    except Exception as e:  # noqa: BLE001
        print("Klavye geri konamadı:", e)


def _kb_rows(tag: str, status: str) -> list:
    """Videonun durumuna uygun düğmeler."""
    return {"onay_bekliyor": [[("✅ Onayla", f"ok:{tag}"), ("❌ Reddet", f"no:{tag}")]],
            "zamanlandi": [[("🚫 Paylaşımı iptal et", f"cancel:{tag}")]],
            "hata": [[("🔁 Hatalıları tekrar dene", f"rt:{tag}")]],
            "kismen": [[("🔁 Hatalıları tekrar dene", f"rt:{tag}")]]}.get(status, [])


def _restore_kb(tag: str, chat: str) -> None:
    """Webhook modunda kapı düğmeyi '⏳ İşleniyor' yaptı; hata olursa videonun durumuna uygun düğmeleri geri koy."""
    v = _find(load(VIDEOS, []), tag)
    if not v or not v.get("telegram_message_id"):
        return
    rows = _kb_rows(tag, v["status"])
    try:
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": v["telegram_message_id"],
                                            "reply_markup": _kb(rows)})
    except Exception as e:  # noqa: BLE001
        print("Düğmeler geri konamadı:", e)


_wh: list = []


def _webhook_mode() -> bool:
    """Bot Cloudflare kapısına bağlıysa (webhook) getUpdates kullanılamaz; olaylar işle.yml ile tek tek gelir."""
    if not _wh:
        try:
            _wh.append(bool(api("getWebhookInfo").get("url")))
        except Exception:  # noqa: BLE001
            _wh.append(False)
    return _wh[0]


def process_update(u: dict, chat: str) -> None:
    """Tek bir Telegram olayını (düğme veya mesaj) işler. Hem dinleme (getUpdates) hem webhook yolu bunu kullanır.
    {"panel": {...}} olayı Telegram'dan değil, panelden gelir (Cloudflare kapısı işle.yml'e iletir)."""
    if isinstance(u.get("panel"), dict):
        process_panel(u["panel"], chat)
        return
    if cq := u.get("callback_query"):
        if str(cq["from"]["id"]) == chat:
            try:
                _handle_callback(cq, chat)
            except Exception as e:  # noqa: BLE001
                print("Düğme işlenemedi:", e)
                if os.environ.get("TG_WEBHOOK") == "1":
                    tag = cq["data"].partition(":")[2].partition(":")[0]
                    if _find(load(VIDEOS, []), tag):
                        _restore_kb(tag, chat)
                    else:
                        _put_back(cq, chat)
                    api("sendMessage", data={"chat_id": chat, "text": f"⚠️ Düğme işlenemedi: {str(e)[:200]}"})
    elif (m := u.get("message")) and str(m["chat"]["id"]) == chat:
        text = (m.get("text") or "").strip()
        rep = (m.get("reply_to_message") or {}).get("message_id")
        if rep and text and not text.startswith("/"):
            from . import comments
            key = comments.by_message(rep)
            if key:  # taslak yerine Sabri'nin kendi yazdığı cevap
                api("sendMessage", data={"chat_id": chat, "text": comments.handle("ok", key, chat, rep, custom=text),
                                         "reply_to_message_id": m["message_id"]})
                return
        if text.startswith("/durum"):
            vs = load(VIDEOS, [])
            bekleyen = [v for v in vs if v["status"] == "onay_bekliyor"]
            plan = [v for v in vs if v["status"] == "zamanlandi"]
            lines = [f"Toplam video: {len(vs)}", f"Onay bekleyen: {len(bekleyen)}"]
            lines += [f"• {v['title']}" for v in bekleyen[-10:]]
            if plan:
                lines += ["", f"Zamanlanan: {len(plan)}", plan_all()]
            api("sendMessage", data={"chat_id": chat, "text": "\n".join(lines)})
        elif text.startswith("/uret"):
            topic = text[5:].strip()
            ok = _dispatch(topic)
            api("sendMessage", data={"chat_id": chat, "text": "Üretim başlatıldı, birkaç dakika içinde gelir." if ok
                                     else "Üretim başlatılamadı."})
        elif text.startswith("/oneri"):
            ok = _dispatch("", "oneri.yml")
            api("sendMessage", data={"chat_id": chat, "text": "🔎 Gündem taranıyor, öneriler 2-3 dakikada gelir."
                                     if ok else "Öneri başlatılamadı."})
        elif text.startswith("/rapor"):
            try:
                from . import stats
                stats.report()
            except Exception as e:  # noqa: BLE001
                api("sendMessage", data={"chat_id": chat, "text": f"Rapor hazırlanamadı: {str(e)[:200]}"})
        elif text.startswith("/saatler"):
            lines = ["Platformların en iyi paylaşım saatleri (Türkiye):"]
            lines += [f"• {PLATFORM_NAMES[p]}: {', '.join(t)}" + (f" (ek saat: {', '.join(EXTRA_TIMES[p])})"
                      if EXTRA_TIMES.get(p) else "") for p, t in BEST_TIMES.items()]
            lines += ["Ek saat, günün kalan (en az 15 dk sonraki) asıl saatleri başka videolara ayrıldıysa kullanılır."]
            lines += ["", "Onaylarken '🎯 Her platform en iyi saatinde' seçersen her biri kendi saatinde paylaşılır."]
            api("sendMessage", data={"chat_id": chat, "text": "\n".join(lines)})
        elif text.startswith("/start") or text.startswith("/yardim"):
            api("sendMessage", data={"chat_id": chat, "text": "Merhaba! Yeni videolar buraya onaya gelir.\n\n"
                                     "/oneri: gündemden 5 konu önerisi (butonla üret)\n"
                                     "/uret [konu]: hemen yeni video üret (konu isteğe bağlı)\n"
                                     "/durum: bekleyen ve zamanlanan videolar\n"
                                     "/rapor: izlenme, takipçi, beğeni, kaydetme raporu\n"
                                     "/saatler: platformların en iyi paylaşım saatleri\n"
                                     "/panel: yönetim paneline giriş bağlantısı\n"
                                     "/yardim: bu liste"})
        elif text.startswith("/panel"):  # giriş bağlantısını Cloudflare kapısı verir (PANEL_SECRET orada)
            api("sendMessage", data={"chat_id": chat, "text": "Panel bağlantısını 7/24 kapı verir; kapı şu an kapalı "
                                     "görünüyor. GitHub'da 'Telegram kapısını kur' işini çalıştırıp /panel yaz."})


# ---- Panel: Cloudflare kapısı (/panel) -> işle.yml -> {"panel": {...}} ----
SLOT_CODES = ("best", "now", "b12", "b19", "y12", "y19")
DURUM_ADI = {"onay_bekliyor": "onay bekliyor", "zamanlandi": "zamanlandı", "yayinlaniyor": "paylaşılıyor",
             "yayinlandi": "paylaşıldı", "kismen": "kısmen paylaşıldı", "hata": "paylaşılamadı",
             "baglanti_yok": "bağlantı yok", "reddedildi": "reddedildi", "iptal": "iptal"}
# video işlemleri yalnız bu durumlarda yapılır: çift basış veya eski sayfadan gelen istek hiçbir şeyi değiştirmez
PANEL_VIDEO_ACTIONS = {"approve": ("onay_bekliyor",), "reject": ("onay_bekliyor",), "cancel": ("zamanlandi",),
                       "retry": ("hata", "kismen", "baglanti_yok"), "edit": ("onay_bekliyor", "zamanlandi")}
_TAIL = ("#", "📷", "🎙", "Görseller:", "Kaynaklar:", "Bu videoda yapay zekâ")


def _is_tail(par: str) -> bool:
    """Açıklamanın sonundaki etiket (#...) ve görsel atfı (📷 ...) paragrafları."""
    lines = [ln.strip() for ln in par.splitlines() if ln.strip()]
    return bool(lines) and all(ln.startswith(_TAIL) for ln in lines)


def _apply_edit(meta: dict, ed: dict | None) -> dict:
    """Panelde düzenlenen başlık/açıklamayı paylaşım paketine uygular. Yeni açıklamada etiket satırı veya görsel
    atfı yoksa orijinaldekiler sona eklenir (yalnız bilgi metni düzenlendiyse etiketler ve lisans atfı korunur)."""
    if not isinstance(ed, dict):
        return meta
    import re
    meta = dict(meta)
    if ed.get("title"):
        meta["title"] = ed["title"]
    desc = (ed.get("description") or "").strip()
    if desc:
        new = [x.strip() for x in re.split(r"\n\s*\n", desc) if _is_tail(x)]
        old = [x.strip() for x in re.split(r"\n\s*\n", meta.get("description") or "") if _is_tail(x)]
        tags, credit = any(x.startswith("#") for x in new), any(not x.startswith("#") for x in new)
        keep = [x for x in old if not (tags if x.startswith("#") else credit)]
        meta["description"] = "\n\n".join([desc] + keep)
    return meta


def _check_edit(p: dict) -> tuple[str, str]:
    title = " ".join(str(p.get("title") or "").split())
    desc = "\n".join(ln.rstrip() for ln in str(p.get("description") or "").replace("\r\n", "\n").split("\n")).strip()
    if not 1 <= len(title) <= 100:
        raise ValueError("başlık 1-100 karakter olmalı")
    if not 1 <= len(desc) <= 2000:
        raise ValueError("açıklama 1-2000 karakter olmalı")
    return title, desc


def _edit_caption(v: dict, chat: str) -> None:
    """Video mesajındaki başlığı günceller; düğmeler videonun durumuna göre aynı kalır."""
    import html
    cap = (f"🎬 <b>{html.escape(v['title'])}</b>\n\nKonu: {html.escape(v.get('topic') or '-')}"
           f"\nŞablon: {html.escape(v.get('template') or '-')}")
    try:
        api("editMessageCaption", data={"chat_id": chat, "message_id": v["telegram_message_id"], "caption": cap[:1000],
                                        "parse_mode": "HTML", "reply_markup": _kb(_kb_rows(v["tag"], v["status"]))})
    except Exception as e:  # noqa: BLE001
        print("Video mesajının başlığı güncellenemedi:", e)


def process_panel(p: dict, chat: str) -> None:
    """Panelden gelen işlem. Telegram düğmeleriyle aynı yardımcıları (_approve, _reject, _cancel, _retry, _dispatch,
    stats.report) kullanır; sonucu sohbete "🖥 Panelden:" diye yazar ki Telegram konuşması asıl kayıt olarak kalsın."""
    action, tag = str(p.get("action") or ""), str(p.get("tag") or "")
    print("Panel işlemi:", action, tag, p.get("rid", ""))
    v = _find(load(VIDEOS, []), tag) if tag else None
    mid = (v or {}).get("telegram_message_id")

    def say(text: str) -> None:
        data = {"chat_id": chat, "text": ("🖥 Panelden: " + text)[:4000]}
        if mid:
            data.update(reply_to_message_id=mid, allow_sending_without_reply="true")
        api("sendMessage", data=data)

    try:
        if action in PANEL_VIDEO_ACTIONS:
            if not v:
                say(f"⚠️ Video bulunamadı: {tag[:40]}")
                return
            if v.get("status") not in PANEL_VIDEO_ACTIONS[action]:
                _restore_kb(tag, chat)  # kapı düğmeyi '⏳ İşleniyor' yapmıştı
                st = v.get("status", "?")
                say(f"ℹ️ İşlem yapılmadı: video şu an '{DURUM_ADI.get(st, st)}' durumunda.\n{v['title']}")
                return
            if action == "approve":
                if p.get("code") not in SLOT_CODES:
                    raise ValueError("geçersiz saat seçimi")
                say(f"{_approve(tag, p['code'], chat, mid)}\n{v['title']}")
            elif action == "reject":
                say(f"{_reject(tag, chat, v)}\n{v['title']}")
            elif action == "cancel":
                say(f"{_cancel(tag, chat, v)}\n{v['title']}")
            elif action == "retry":
                note = _retry(tag)
                api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb([])})
                say(f"🔁 {note}\n{v['title']}")
            elif action == "edit":
                title, desc = _check_edit(p)
                v = _update(tag, title=title, duzenleme={"title": title, "description": desc,
                                                         "at": dt.datetime.now(TR).isoformat(timespec="seconds")})
                _edit_caption(v, chat)
                say(f"✏️ Başlık ve açıklama düzenlendi; paylaşımda bu metin kullanılacak.\n\n{title}\n\n{desc}")
        elif action == "produce_suggestion":
            from .trends import load_saved
            items, i = load_saved(), p.get("index")
            if type(i) is not int or not 0 <= i < len(items) or (p.get("topic") and items[i].get("topic") != p["topic"]):
                say("⚠️ Öneri bulunamadı; öneri listesi değişmiş olabilir. Paneli yenileyip tekrar seç.")
                return
            ok = _dispatch(_suggestion_topic(items[i]))
            say(f"🎬 Üretim başladı: {items[i]['topic']}\nYaklaşık 15 dakikada gelir." if ok
                else "⚠️ Üretim başlatılamadı.")
        elif action == "produce_topic":
            topic = " ".join(str(p.get("topic") or "").split())
            if len(topic) > 300:
                raise ValueError("konu en fazla 300 karakter olabilir")
            ok = _dispatch(topic)
            say(("🎬 Üretim başladı: " + (topic or "konu sıradan veya gündemden seçilecek")
                 + "\nYaklaşık 15 dakikada gelir.") if ok else "⚠️ Üretim başlatılamadı.")
        elif action == "refresh_suggestions":
            ok = _dispatch("", "oneri.yml")
            say("🔎 Gündem taranıyor, öneriler 2-3 dakikada gelir." if ok else "⚠️ Öneri başlatılamadı.")
        elif action == "report":
            from . import stats
            say("📊 Rapor istendi, hazırlanıyor.")
            stats.report()
        elif action == "queue_set":
            from . import konu_sirasi
            items = konu_sirasi.clean(p.get("queue"))
            konu_sirasi.save(items)
            say(f"📋 Konu sırası kaydedildi ({len(items)} konu)." + (f"\nSıradaki: {items[0]}" if items else ""))
        else:
            say(f"⚠️ Bilinmeyen panel işlemi: {action[:40]}")
    except Exception as e:  # noqa: BLE001
        print("Panel işlemi yapılamadı:", e)
        if v:
            _restore_kb(tag, chat)
        say(f"⚠️ İşlem yapılamadı: {str(e)[:200]}")


def poll(wait: int = 0) -> int:
    """Yeni düğme basışlarını ve komutları işler. wait>0 ise o kadar saniye yeni olay bekler (long polling)."""
    global _menu_set
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    if not _menu_set:  # "/" yazınca açılan komut menüsü
        try:
            api("setMyCommands", data={"commands": json.dumps(COMMANDS, ensure_ascii=False)})
        except Exception as e:  # noqa: BLE001
            print("Komut menüsü ayarlanamadı:", e)
        _menu_set = True
    if _webhook_mode():
        return 0
    off = load(OFFSET, {"offset": 0})
    updates = api("getUpdates", data={"offset": off["offset"], "timeout": wait}) or []
    for u in updates:
        off["offset"] = u["update_id"] + 1
        save(OFFSET, off)  # bir olay hata verse bile tekrar tekrar işlenmesin
        process_update(u, chat)
    save(OFFSET, off)
    return len(updates)


def _next_due() -> dt.datetime | None:
    """Zamanlanmış videolardaki en yakın paylaşım anı (platform bazlı saatler dahil)."""
    times = []
    for v in load(VIDEOS, []):
        if v["status"] != "zamanlandi":
            continue
        done = {k for k, r in (v.get("platforms") or {}).items() if r.get("status") == "ok"}
        sched = {k: t for k, t in (v.get("schedule") or {}).items() if k not in done}
        times += [dt.datetime.fromisoformat(t) for t in (sched.values() if sched else [v["publish_at"]]) if t]
    return min(times) if times else None


def _window_poll_until(start: float, end: float) -> float:
    """Pencere (start..end, unix zamanı) içinde yeni onaylara bakılacak son an. Bir saat (ör. 12:30) saatinden 15 dk
    öncesine kadar verilebilir; o son anda işlenen bir onayın depoya yazılması da birkaç saniye sürebildiği için
    3 dk pay bırakılır (saat - 12 dk). Saat artık verilmediğinden fazladan bakmanın zararı yok."""
    s, e = dt.datetime.fromtimestamp(start, TR), dt.datetime.fromtimestamp(end, TR)
    times = {hm for p in BEST_TIMES for hm in BEST_TIMES[p] + EXTRA_TIMES.get(p, [])} | {"12:00", "19:00"}
    cands = []
    for day in {s.date(), e.date()}:
        for hm in times:
            h, m = map(int, hm.split(":"))
            t = dt.datetime.combine(day, dt.time(h, m), TR)
            if s < t <= e:
                cands.append((t - dt.timedelta(minutes=12)).timestamp())
    return max(cands, default=0.0)


def listen(minutes: float) -> None:
    """Belirtilen süre boyunca düğmelere anında yanıt verir ve saati gelenleri hemen paylaşır.
    Webhook modunda düğmeleri Cloudflare kapısı karşılar; burada yalnız pencere içindeki paylaşımlar beklenir."""
    import time
    end = time.time() + minutes * 60
    if _webhook_mode():
        # Düğmeleri kapı + işle.yml karşılar. Burada (state grubunda, tek başına) yalnız pencere içindeki
        # paylaşımlar yapılır; her paylaşımdan önce en güncel durum alınır (iptal edilenler paylaşılmasın).
        from . import state_sync
        # Pencerenin içindeki bir saat (ör. 12:30), saatinden 15 dk öncesine kadar yeni onaylara verilebilir.
        # O ana kadar dakikada bir yeni onay var mı bakılır; sonra yalnız saati gelen beklenir.
        poll_until = _window_poll_until(time.time(), end)
        while True:
            state_sync.sync("Zamanlanmış paylaşımlar")
            state_sync.refresh()
            publish_due()
            state_sync.sync("Zamanlanmış paylaşımlar")
            state_sync.refresh()
            nxt, now = _next_due(), time.time()
            if now > end:
                return
            if nxt and nxt.timestamp() <= end:
                wait = nxt.timestamp() - now + 5
            elif now < poll_until:
                wait = 60
            else:
                return
            if now < poll_until:
                wait = min(wait, 60)
            time.sleep(max(5, min(wait, end - now + 1)))
    while time.time() < end:
        try:
            poll(wait=int(max(1, min(50, end - time.time()))))
            publish_due()
        except Exception as e:  # noqa: BLE001
            print("Dinleme hatası:", e)
            time.sleep(5)


def publish_due() -> None:
    """Saati gelen videoları paylaşır. Daha önce başarılı olan platformlara tekrar yüklemez."""
    from .publish import fetch_release, publish
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    now = dt.datetime.now(dt.timezone.utc)
    due = [v for v in load(VIDEOS, []) if v["status"] == "zamanlandi" and v.get("publish_at")
           and dt.datetime.fromisoformat(v["publish_at"]) <= now]
    for v in due:
        tag = v["tag"]
        done = {k for k, r in (v.get("platforms") or {}).items() if r.get("status") == "ok"}
        sched = v.get("schedule") or {}
        todo = [p for p in PLATFORM_NAMES if p not in done
                and (p not in sched or dt.datetime.fromisoformat(sched[p]) <= now)]
        later = {p: t for p, t in sched.items() if p not in done and p not in todo}
        if not todo:
            continue
        _update(tag, status="yayinlaniyor")
        try:
            with tempfile.TemporaryDirectory() as d:
                video, meta = fetch_release(tag, Path(d))
                res = publish(video, _apply_edit(meta, v.get("duzenleme")), todo)
        except Exception as e:  # noqa: BLE001
            res = {p: {"status": "hata", "error": f"video indirilemedi: {e}"[:600]} for p in todo}
        stamp = dt.datetime.now(TR).isoformat(timespec="seconds")
        for r in res.values():
            if r.get("status") == "ok":
                r.setdefault("at", stamp)
        platforms = {**(v.get("platforms") or {}), **res}
        failed = [p for p, r in platforms.items() if r.get("status") == "hata"]
        ok = [p for p, r in platforms.items() if r.get("status") == "ok"]
        status = "kismen" if failed and ok else "hata" if failed else "yayinlandi" if ok else "baglanti_yok"
        if later:  # diğer platformların saati henüz gelmedi
            _update(tag, status="zamanlandi", platforms=platforms, publish_at=min(later.values()))
        else:
            _update(tag, status=status, platforms=platforms,
                    published=dt.datetime.now(TR).isoformat(timespec="seconds"))
        lines = []
        for p, r in platforms.items():
            if p not in todo:
                continue  # yalnız bu turda paylaşılanları yaz
            name = PLATFORM_NAMES[p]
            if r["status"] == "ok":
                lines.append(f"✅ {name}: {r.get('url') or ('taslak olarak gönderildi' if r.get('draft') else 'paylaşıldı')}" + (f"\n   ⚠️ {r['note']}" if r.get("note") else "")
                             + (f"\n\n{r['caption']}\n" if r.get("caption") else ""))
            elif r["status"] == "hata":
                lines.append(f"❌ {name}: {r['error'][:300]}")
            else:
                lines.append(f"➖ {name}: bağlı değil")
        head = {"yayinlandi": "📢 Paylaşıldı", "kismen": "⚠️ Kısmen paylaşıldı", "hata": "❌ Paylaşılamadı",
                "baglanti_yok": "➖ Hiçbir platform bağlı değil, paylaşım yapılmadı"}[status]
        if later:
            lines += [f"🕒 {PLATFORM_NAMES[p]}: {_fmt(t)}" for p, t in sorted(later.items(), key=lambda x: x[1])]
            head = "📢 Paylaşım sürüyor" if ok else head
        kb = (_kb([[("🚫 Kalanları iptal et", f"cancel:{tag}")]]) if later
              else _kb([[("🔁 Hatalıları tekrar dene", f"rt:{tag}")]]) if failed else _kb([]))
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": v["telegram_message_id"], "reply_markup": kb})
        api("sendMessage", data={"chat_id": chat, "text": f"{head}\n{v['title']}\n\n" + "\n".join(lines),
                                 "reply_to_message_id": v["telegram_message_id"], "disable_web_page_preview": "true"})


def _dispatch(topic: str, workflow: str = "uret.yml") -> bool:
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return False
    inputs = {"topic": topic} if workflow == "uret.yml" else {}
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      json={"ref": os.environ.get("GITHUB_REF_NAME", "main"), "inputs": inputs}, timeout=30)
    return r.status_code == 204


def duzelt(tag: str, islem: str = "", neden: str = "") -> None:
    """Bir düzeltmeden sonra Telegram'a güncel paylaşım planını yazar.
    tag bir video ise mesaj o videonun mesajına yanıt olarak gider; tag "hepsi" ise yalnız genel plan gönderilir.
    islem="yeniden": o videonun en iyi saatlerini şimdiki kurallara göre yeniden hesaplar ve kaydeder."""
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    head = "🔁 Düzeltme" + (f": {neden}" if neden else "")
    data = {"chat_id": chat}
    if tag != "hepsi":
        v = _find(load(VIDEOS, []), tag)
        if not v:
            raise SystemExit(f"Video bulunamadı: {tag}")
        fresh, note = False, ""
        if islem == "yeniden" and v.get("status") == "zamanlandi" and v.get("schedule"):
            done = _done(v)  # paylaşılmış platformların gerçek saati korunur, yalnız bekleyenler yeniden planlanır
            soon = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=40)
            nxt = v.get("publish_at")  # paylaşım işinin videoya bir sonraki dokunacağı an
            if _pending_sched(v) and nxt and dt.datetime.fromisoformat(nxt) <= soon:
                # o platformu şu an bir paylaşım işi yüklüyor olabilir: saatlerle oynanmaz
                note = "⚠️ Paylaşım saati 40 dakikadan yakın olduğu için saatler yeniden hesaplanmadı."
            else:
                new = _best_schedule(exclude=tag)
                sched = {**{p: t for p, t in new.items() if p not in done},
                         **{p: v["schedule"][p] for p in done if p in v["schedule"]}}
                pend = [t for p, t in sched.items() if p not in done]
                if pend:
                    v = _update(tag, schedule=sched, publish_at=min(pend))
                    fresh = True
        if v.get("status") == "zamanlandi":
            shared = []  # paylaşılmış platformlar da görünsün (saatleri artık planda değil)
            for p in PLATFORM_NAMES:
                if p in _done(v):
                    at = (v.get("platforms") or {})[p].get("at")
                    shared.append(f"✅ {PLATFORM_NAMES[p]}: paylaşıldı" + (f" ({_fmt(at)})" if at else ""))
            body = "\n".join(shared + [_plan_text(tag, _pending_sched(v), explain=fresh)]).strip() \
                or ("Tüm platformlarda paylaşıldı." if len(_done(v)) == len(PLATFORM_NAMES)
                    else "Bu video için kayıtlı paylaşım saati yok.")
        else:
            body = "Durum: " + v.get("status", "?")
        if note:
            body += "\n" + note
        head += f"\n{v['title']}\n{body}"
        data["reply_to_message_id"] = v["telegram_message_id"]
    head += "\n\n🗓 Güncel paylaşım planı (Türkiye saati):\n" + plan_all()
    api("sendMessage", data={**data, "text": head[:4000]})


if __name__ == "__main__":
    try:
        from .pipeline import load_env
        load_env(ROOT / ".env")
    except ImportError:  # hafif ortam (işle.yml yalnız requests + pydantic kurar)
        pass
    if sys.argv[1] == "handle-update":  # Cloudflare kapısından gelen tek olay (UPDATE ortam değişkeninde)
        # Paylaşım burada yapılmaz (aynı anda iki iş aynı videoyu yüklemesin); bkz. dispatch-if-due.
        process_update(json.loads(os.environ["UPDATE"]), str(os.environ["TELEGRAM_CHAT_ID"]))
    elif sys.argv[1] == "dispatch-if-due":
        # Durum kaydedildikten SONRA çağrılır: şimdi paylaşılacak bir şey varsa tek sıra hâlinde çalışan
        # onay.yml'i (state grubu) başlatır.
        nxt = _next_due()
        if nxt and nxt <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2):
            print("Paylaşım işi başlatıldı:", _dispatch("", "onay.yml"))
    elif sys.argv[1] == "duzelt":  # düzeltme sonrası: videonun mesajına güncel planı yanıt olarak yazar
        duzelt(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "", " ".join(sys.argv[4:]))
    elif sys.argv[1] == "notify":
        notify(Path(sys.argv[2]), sys.argv[3])
    elif sys.argv[1] == "poll":
        poll()
    elif sys.argv[1] == "listen":
        listen(float(sys.argv[2]))
    elif sys.argv[1] == "publish-due":
        publish_due()
