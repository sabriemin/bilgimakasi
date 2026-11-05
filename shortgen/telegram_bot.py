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
import math
import re
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


def _err_text(e: BaseException, n: int = 200) -> str:
    """Sohbete yazılacak hata metni. Ağ hatalarının metni tam adresi (Telegram'da bot anahtarı, Instagram'da
    access_token) içerir: onlar için sabit bir cümle + iş bağlantısı gider, ayrıntı yalnız (maskelenmiş) günlüğe yazılır."""
    from requests.exceptions import RequestException
    from .publish import _redact
    print("Hata ayrıntısı:", _redact(f"{type(e).__name__}: {e}")[:1000])
    if isinstance(e, RequestException):
        run = os.environ.get("GITHUB_RUN_ID")
        url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}"
               f"/actions/runs/{run}") if run and os.environ.get("GITHUB_REPOSITORY") else ""
        return "Telegram veya GitHub'a bağlanılamadı; birazdan tekrar dene." + (f"\nAyrıntı: {url}" if url else "")
    return _redact(e)[:n]


def _cut16(text: str, n: int = 4096) -> str:
    """Telegram metin sınırı UTF-16 birimiyle sayılır (emoji 2 birim)."""
    if len(text.encode("utf-16-le")) // 2 <= n:
        return text
    while len(text.encode("utf-16-le")) // 2 > n - 1:
        text = text[:-max(1, (len(text.encode("utf-16-le")) // 2 - n + 1) // 2)]
    return text + "…"


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _video_caption(title, template) -> str:
    """Video mesajının kısa başlığı (HTML): yalnız başlık ve şablon; açıklama ayrı mesajda gelir.
    Kaçışlı: "<" ya da "&" içeren başlık Telegram'ın HTML ayrıştırmasını bozup videoyu düşürmesin. Kesme kaçıştan
    önce yapılır: kaçışlı metni kesmek &amp; gibi bir varlığı bölüp HTML'i bozabilir (1024 sınırı içinde kalır)."""
    import html
    title, tpl = str(title or "")[:300], str(template or "-")[:40]
    while True:
        cap = f"🎬 <b>{html.escape(title)}</b>\nŞablon: {html.escape(tpl)}"
        if len(cap) <= 1000 or len(title) <= 1:
            return cap
        title = title.rstrip("…")[:-max(1, (len(cap) - 1000) // 5 + 1)] + "…"


def _send_desc(chat: str, text: str) -> int:
    """Açıklama mesajı: başlıksız, yanıt olmayan düz metin (uzun basıp kopyalanır, TikTok taslağına yapıştırılır)."""
    msg = api("sendMessage", data={"chat_id": chat, "text": _cut16(text, 4096), "disable_web_page_preview": "true"})
    return msg["message_id"]


def notify(out_dir: Path, tag: str) -> None:
    from .publish import apply_series_tag, tiktok_caption
    meta = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    chat = os.environ["TELEGRAM_CHAT_ID"]
    kb = {"inline_keyboard": [[
        {"text": "✅ Onayla", "callback_data": f"ok:{tag}"},
        {"text": "❌ Reddet", "callback_data": f"no:{tag}"},
    ]]}
    with (out_dir / "video.mp4").open("rb") as f:
        msg = api("sendVideo", data={"chat_id": chat, "caption": _video_caption(meta["title"], meta.get("template")),
                                     "parse_mode": "HTML", "supports_streaming": "true",
                                     "reply_markup": json.dumps(kb)}, files={"video": f})
    # Açıklama ayrı mesaj (videoya yanıt değil): TikTok'a gidecek açıklamanın aynısı, bir daha gönderilmez.
    # Gönderilemezse video yine kayda geçer: onay akışı bozulmasın.
    desc_id = None
    try:
        desc_id = _send_desc(chat, tiktok_caption(apply_series_tag(meta)))
    except Exception as e:  # noqa: BLE001
        print("Açıklama mesajı gönderilemedi:", _redact_safe(e))
    videos = load(VIDEOS, [])
    videos.append({"tag": tag, "title": meta["title"], "topic": meta["topic"], "category": meta["category"],
                   "template": meta.get("template"), "created": meta["created"], "status": "onay_bekliyor",
                   "telegram_message_id": msg["message_id"],
                   **({"aciklama_message_id": desc_id} if desc_id else {}), "platforms": {}})
    save(VIDEOS, videos)


def preview(out_dir: Path, label: str = "") -> None:
    """Yalnız göz atmak için örnek video (ornek.yml): onay düğmesi yok, kayda (videos.json) geçmez, paylaşılmaz."""
    import html
    meta = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    # kesme kaçıştan ÖNCE: kaçışlı metni kesmek &amp; varlığını ya da </b> etiketini bölebilir (1024 sınırı içinde kalır)
    caption = (f"🧪 <b>Örnek video, paylaşılmayacak</b>\n{html.escape(label[:300])}\n\n"
               f"<b>{html.escape(str(meta['title'])[:200])}</b>\nŞablon: {html.escape(str(meta.get('template', '-'))[:40])}")
    with (out_dir / "video.mp4").open("rb") as f:
        api("sendVideo", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": caption,
                               "parse_mode": "HTML", "supports_streaming": "true"}, files={"video": f})


def _find(videos: list, tag: str) -> dict | None:
    return next((v for v in videos if v["tag"] == tag), None)


def _origin_record(tag: str) -> dict | None:
    """Videonun uzak depodaki (origin/main) en güncel kaydı; alınamazsa None. Yerel durumu değiştirmez."""
    import subprocess
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, check=True, timeout=60,
                       capture_output=True)
        remote = json.loads(subprocess.run(["git", "show", "origin/main:state/videos.json"], cwd=ROOT,
                                           capture_output=True, text=True, check=True).stdout)
    except Exception as e:  # noqa: BLE001
        print("Uzak kayıt alınamadı:", _redact_safe(e))
        return None
    return _find(remote, tag)


def _refresh_videos() -> None:
    """Dinleme işi başladıktan sonra üretilen videoları uzak depodan alır (yerel değişikliklere dokunmaz)."""
    import subprocess
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, check=True, timeout=60)
        remote = json.loads(subprocess.run(["git", "show", "origin/main:state/videos.json"], cwd=ROOT,
                                           capture_output=True, text=True, check=True).stdout)
    except Exception as e:  # noqa: BLE001
        print("Uzak durum alınamadı:", _redact_safe(e))
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
# Ek saatler: varsayılan olarak yok; otomatik seçim (🎯) yalnız asıl en iyi saatleri kullanır, o günün asıl saatleri
# doluysa ertesi günün asıl saatine geçer. EXTRA_TIMES ortam değişkeniyle (JSON) ek saat tanımlanırsa asıl saatlerden
# sonra o günün ek saati denenir. İstenen her saat panelin Takvim sekmesinden elle seçilebilir.
EXTRA_TIMES = json.loads(os.environ.get("EXTRA_TIMES") or json.dumps({
    "youtube": [],
    "instagram": [],
    "tiktok": [],
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
    """Her platform için en az 15 dk sonraki, başka bir videoya ayrılmamış ilk en iyi saati (UTC ISO) döndürür.
    Aynı platformda iki paylaşım arasında en az MIN_GAP olur; bugünün en iyi saatleri doluysa sonraki günün en iyi
    saatine geçer (14 gün ileriye kadar bakar)."""
    now = now or dt.datetime.now(TR)
    busy = {} if ignore_busy else _busy(exclude)
    out = {}
    for p, times in BEST_TIMES.items():
        chosen = None
        for d in range(0, 14):
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


def _is_prime(p: str, iso: str) -> bool:
    """Saat, platformun en iyi saatlerinden (prime time) biri mi (TR saatiyle)."""
    return f"{dt.datetime.fromisoformat(iso).astimezone(TR):%H:%M}" in BEST_TIMES.get(p, [])


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


PANEL_HINT = "Saatleri değiştirmek için panelde Takvim: /panel"


def _sched_lines(sched: dict[str, str]) -> str:
    """Platform saatleri, saate göre sıralı; en iyi saatler (prime time) ⭐ ile (ör. "• YouTube: 6 Kasım Cuma 18:00 ⭐")."""
    return "\n".join(f"• {PLATFORM_NAMES[p]}: {_fmt(t)}" + (" ⭐" if _is_prime(p, t) else "")
                     for p, t in sorted(sched.items(), key=lambda x: x[1]))


def _plan_text(sched: dict[str, str]) -> str:
    """Bir videonun platform saatleri ve panelde değiştirme notu (saat yoksa boş)."""
    return f"{_sched_lines(sched)}\n{PANEL_HINT}" if sched else ""


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
    from .trends import uretim_konusu
    return uretim_konusu(it)


def _produce_suggestion(it: dict) -> bool:
    """Öneriden üretim: serinin kalıbı (trends.SERI_KALIP: Efsane mi, gerçek mi? -> efsane, Nasıl yapılır? -> nasil,
    Nasıl üretiliyor? -> uretim, Ya sen olsaydın? -> olsaydin, Bir Kitap Bir Dakika -> kitap) üretimde sabitlenir."""
    from .trends import kalip_of
    return _dispatch(_suggestion_topic(it), kalip=kalip_of(it))


def _approve(tag: str, code: str, chat: str, mid: int) -> str:
    """Onay (kod: best|now|b12|b19|y12|y19): saati hesaplar ve kaydeder, video mesajının düğmesini 'iptal' yapar.
    Telegram'a yazılacak notu döndürür."""
    if code == "best":
        sched = _best_schedule(exclude=tag)
        iso = min(sched.values())
        note = "✅ Onaylandı. Her platform kendi en iyi saatinde paylaşılacak:\n" + _plan_text(sched)
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
    first = (v.get("duzenleme") or {}).get("ilk_baslik") or v.get("title", "")  # panelde başlık değişmiş olabilir
    if "(1. Bölüm)" in first and seri_file.exists():  # 1. bölüm reddedilirse 2. bölüm üretilmesin
        seri = json.loads(seri_file.read_text(encoding="utf-8"))
        if seri.get("bekleyen", {}).get("title") == first:
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
    if action == "tp":  # öneriden üretim: tp:<liste damgası>:<sıra> ("_": damgasız eski mesaj)
        from .trends import damga, load_saved
        items = load_saved()
        i = int(arg) if arg.isdigit() else -1
        if not 0 <= i < len(items):
            api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": "Öneri bulunamadı."})
            return
        if tag != "_" and tag != damga(items):  # kayıtlı liste bu mesajınki değil: aynı numara başka konu olabilir
            api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": ""})  # açıklama tek mesajda
            api("sendMessage", data={"chat_id": chat, "text": "⚠️ Bu mesajın öneri listesi kayıtlı listeyle aynı değil "
                                     "(liste yenilenmiş ya da yenisi henüz kaydediliyor). Bir dakika sonra tekrar dene "
                                     "ya da panelin Konular sekmesinden seç."})
            return
        it = items[i]
        ok = _produce_suggestion(it)
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
    if action in ("ok", "at", "no") and v.get("status") != "onay_bekliyor":
        # eski bir düğme (ör. iki işlem aynı anda yürüdü): karar verilmiş videoyu yeniden onaylatma/reddettirme
        st = v.get("status", "?")
        _restore_kb(tag, chat)
        api("answerCallbackQuery", data={"callback_query_id": cq["id"],
                                         "text": f"Bu video artık onay beklemiyor ({DURUM_ADI.get(st, st)})."[:190]})
        return
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
            note = ("Bu paylaşım zaten iptal edilmiş; video onay bekliyor." if v.get("status") == "onay_bekliyor"
                    else "Bu video zaten paylaşıldı veya paylaşılıyor.")
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
    {"command": "oneri", "description": "Yedi seriden 21 konu önerisi (butonla üret)"},
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
        print("Klavye geri konamadı:", _redact_safe(e))


def _kb_rows(tag: str, status: str) -> list:
    """Videonun durumuna uygun düğmeler."""
    return {"onay_bekliyor": [[("✅ Onayla", f"ok:{tag}"), ("❌ Reddet", f"no:{tag}")]],
            "zamanlandi": [[("🚫 Paylaşımı iptal et", f"cancel:{tag}")]],
            "hata": [[("🔁 Hatalıları tekrar dene", f"rt:{tag}")]],
            "kismen": [[("🔁 Hatalıları tekrar dene", f"rt:{tag}")]]}.get(status, [])


def _restore_kb(tag: str, chat: str, status: str | None = None) -> None:
    """Webhook modunda kapı düğmeyi '⏳ İşleniyor' yaptı; hata olursa videonun durumuna uygun düğmeleri geri koy."""
    v = _find(load(VIDEOS, []), tag)
    if not v or not v.get("telegram_message_id"):
        return
    rows = _kb_rows(tag, status or v["status"])
    try:
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": v["telegram_message_id"],
                                            "reply_markup": _kb(rows)})
    except Exception as e:  # noqa: BLE001
        print("Düğmeler geri konamadı:", _redact_safe(e))


def refresh_kb(update: dict, chat: str) -> None:
    """Durum kaydedildikten (state_sync) SONRA çağrılır. Aynı anda yürüyen başka bir işin kararı (ör. Telegram'dan
    red, panelden düzenleme) birleşmiş olabilir: video mesajının düğmelerini birleşmiş duruma göre yeniden koyar.
    Onay bekleyen videoda saat seçimi gibi geçici düğmelere dokunmaz (yalnız panel düzenlemesinden sonra koyar)."""
    p = update.get("panel") if isinstance(update.get("panel"), dict) else {}
    tag = str(p.get("tag") or "")
    data = str((update.get("callback_query") or {}).get("data") or "")
    if not tag and data.count(":") and not data.startswith(("cm:", "tp:")):
        tag = data.split(":")[1]
    v = _find(load(VIDEOS, []), tag) if tag else None
    if not v or (v.get("status") == "onay_bekliyor" and p.get("action") != "edit"):
        return
    _restore_kb(tag, chat)


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
                print("Düğme işlenemedi.")
                note = _err_text(e)
                if os.environ.get("TG_WEBHOOK") == "1":
                    tag = cq["data"].partition(":")[2].partition(":")[0]
                    if _find(load(VIDEOS, []), tag):
                        _restore_kb(tag, chat)
                    else:
                        _put_back(cq, chat)
                    api("sendMessage", data={"chat_id": chat, "text": f"⚠️ Düğme işlenemedi: {note}"})
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
            from .trends import seri_tahmini
            kalip, topic = seri_tahmini(re.sub(r"^/uret(@\w+)?", "", text))
            ok = _dispatch(topic, kalip=kalip)
            api("sendMessage", data={"chat_id": chat, "text": ("Üretim başlatıldı" + _seri_notu(kalip)
                                     + ", birkaç dakika içinde gelir.") if ok else "Üretim başlatılamadı."})
        elif text.startswith("/oneri"):
            ok = _dispatch("", "oneri.yml")
            api("sendMessage", data={"chat_id": chat, "text": "🔎 Gündem taranıyor, öneriler 2-3 dakikada gelir."
                                     if ok else "Öneri başlatılamadı."})
        elif text.startswith("/rapor"):
            try:
                from . import stats
                stats.report()
            except Exception as e:  # noqa: BLE001
                api("sendMessage", data={"chat_id": chat, "text": f"Rapor hazırlanamadı: {_err_text(e)}"})
        elif text.startswith("/saatler"):
            lines = ["Platformların en iyi paylaşım saatleri (Türkiye, ⭐ prime time):"]
            lines += [f"• {PLATFORM_NAMES[p]}: {', '.join(t)}" + (f" (ek saat: {', '.join(EXTRA_TIMES[p])})"
                      if EXTRA_TIMES.get(p) else "") for p, t in BEST_TIMES.items()]
            if any(EXTRA_TIMES.get(p) for p in BEST_TIMES):
                lines += ["Ek saat, günün kalan (en az 15 dk sonraki) asıl saatleri başka videolara ayrıldıysa kullanılır."]
            lines += ["", "Onaylarken '🎯 Her platform en iyi saatinde' seçersen her biri kendi boş en iyi saatinde "
                      "paylaşılır; o günün en iyi saatleri doluysa ertesi güne geçer.", PANEL_HINT]
            api("sendMessage", data={"chat_id": chat, "text": "\n".join(lines)})
        elif text.startswith("/start") or text.startswith("/yardim"):
            api("sendMessage", data={"chat_id": chat, "text": "Merhaba! Yeni videolar buraya onaya gelir.\n\n"
                                     "/oneri: 7 seriden 21 konu önerisi (butonla üret)\n"
                                     "/uret [konu]: hemen yeni video üret (konu isteğe bağlı; 'Kuyumcu olsaydın', "
                                     "'Çay nasıl demlenir?' gibi konularda seri kendiliğinden seçilir, başına "
                                     "'genel:' yazarsan serbest kalır)\n"
                                     "/durum: bekleyen ve zamanlanan videolar\n"
                                     "/rapor: izlenme, takipçi, beğeni, kaydetme raporu\n"
                                     "/saatler: platformların en iyi paylaşım saatleri\n"
                                     "/panel: yönetim paneline giriş bağlantısı\n"
                                     "/yardim: bu liste"})
        elif re.match(r"/panel(@\w+)?(\s|$)", text):  # giriş bağlantısını Cloudflare kapısı verir (PANEL_SECRET orada)
            api("sendMessage", data={"chat_id": chat, "text": "Panel bağlantısını 7/24 kapı verir; kapı kapalı ya da "
                                     "henüz panelli sürüme güncellenmemiş. GitHub'da 'Telegram kapısını kur' işini "
                                     "çalıştırıp /panel yaz."})


# ---- Panel: Cloudflare kapısı (/panel) -> işle.yml -> {"panel": {...}} ----
SLOT_CODES = ("best", "now", "b12", "b19", "y12", "y19")
DURUM_ADI = {"onay_bekliyor": "onay bekliyor", "zamanlandi": "zamanlandı", "yayinlaniyor": "paylaşılıyor",
             "yayinlandi": "paylaşıldı", "kismen": "kısmen paylaşıldı", "hata": "paylaşılamadı",
             "baglanti_yok": "bağlantı yok", "reddedildi": "reddedildi", "iptal": "iptal"}
# video işlemleri yalnız bu durumlarda yapılır: çift basış veya eski sayfadan gelen istek hiçbir şeyi değiştirmez
PANEL_VIDEO_ACTIONS = {"approve": ("onay_bekliyor",), "reject": ("onay_bekliyor",), "cancel": ("zamanlandi",),
                       "retry": ("hata", "kismen", "baglanti_yok"), "edit": ("onay_bekliyor", "zamanlandi"),
                       "schedule": ("onay_bekliyor", "zamanlandi")}
_TAIL = ("#", "📷", "🎙", "Görseller:", "Kaynaklar:", "Bu videoda yapay zekâ")


def _is_tail(par: str) -> bool:
    """Açıklamanın sonundaki etiket (#...) ve görsel atfı (📷 ...) paragrafları."""
    lines = [ln.strip() for ln in par.splitlines() if ln.strip()]
    return bool(lines) and all(ln.startswith(_TAIL) for ln in lines)


# Paylaşım işi publish_at'te başlar ve durumu ancak yüklemeden sonra kaydeder: bu kadar dakika kala metin değiştirilmez.
EDIT_GUARD_MIN = 10


def _split_tag_lines(desc: str) -> str:
    """Metnin hemen altına boş satır bırakmadan yazılmış #etiket satırlarını ayrı paragraf yapar."""
    import re
    pars = re.split(r"\n\s*\n", desc.strip())
    lines = pars[-1].splitlines()
    k = len(lines)
    while k > 0 and lines[k - 1].split() and all(re.fullmatch(r"#\w*[^\W\d_]\w*", w) for w in lines[k - 1].split()):
        k -= 1
    if 0 < k < len(lines):
        pars[-1:] = ["\n".join(lines[:k]).rstrip(), "\n".join(ln.strip() for ln in lines[k:])]
    return "\n\n".join(pars)


def _apply_edit(meta: dict, ed: dict | None) -> dict:
    """Panelde düzenlenen başlık/açıklamayı paylaşım paketine uygular. Orijinal açıklamanın görsel atfı (📷, lisans)
    HER ZAMAN sona eklenir; kullanıcının metni yalnız etiket (#) satırının yerine geçebilir: kendi # satırını yazdıysa
    orijinal etiket satırı eklenmez. (Kullanıcının "📷 ..." / "Kaynaklar: ..." satırı atfın yerine geçmez.)"""
    if not isinstance(ed, dict):
        return meta
    import re
    meta = dict(meta)
    if ed.get("title"):
        meta["title"] = ed["title"]
    desc = _split_tag_lines(ed.get("description") or "") if (ed.get("description") or "").strip() else ""
    if desc:
        pars = [x.strip() for x in re.split(r"\n\s*\n", desc) if x.strip()]
        own_tags = any(_is_tail(x) and any(ln.strip().startswith("#") for ln in x.splitlines()) for x in pars)
        keep = []
        for x in re.split(r"\n\s*\n", meta.get("description") or ""):
            x = x.strip()
            if not _is_tail(x) or x in pars:  # bilgi metni değişti; aynen yazılmış ek paragraf iki kez eklenmez
                continue
            lines = [ln.strip() for ln in x.splitlines() if ln.strip() and not (own_tags and ln.strip().startswith("#"))]
            if lines:
                keep.append("\n".join(lines))
        meta["description"] = "\n\n".join([desc] + keep)
        if own_tags:  # kendi etiketleri Instagram, TikTok ve YouTube etiket alanında da kullanılır
            tags = [re.sub(r"\W", "", t) for x in pars if _is_tail(x) for ln in x.splitlines()
                    if ln.strip().startswith("#") for t in re.findall(r"#[^\s#]+", ln)]
            tags = list(dict.fromkeys(t for t in tags if t))
            if tags:
                meta["hashtags"] = tags
    return meta


def _check_edit(p: dict) -> tuple[str, str]:
    """Kapının (panel.js metinAl / aciklamaDenetle) denetiminin aynısı: buraya bozuk istek gelse de kayda geçmez."""
    import re
    title = " ".join(str(p.get("title") or "").split())
    desc = "\n".join(ln.rstrip() for ln in str(p.get("description") or "").replace("\r\n", "\n").split("\n")).strip()
    if not 1 <= len(title) <= 100:
        raise ValueError("başlık 1-100 karakter olmalı")
    if not 1 <= len(desc) <= 2000:
        raise ValueError("açıklama 1-2000 karakter olmalı")
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f]", title + desc):
        raise ValueError("metin geçersiz karakter içeriyor")
    if len(desc.encode("utf-8")) > 4000:  # YouTube sınırı 5000 bayt; sona atıf ve etiketler de eklenir
        raise ValueError("açıklama çok uzun (emoji ve özel karakterler daha çok yer kaplar), biraz kısalt")
    for par in re.split(r"\n\s*\n", desc):
        if _is_tail(par) and not all(ln.strip().startswith("#") for ln in par.splitlines() if ln.strip()):
            raise ValueError("görsel atfı ve kaynak satırları sona kendiliğinden eklenir; bu satırları açıklamadan çıkar")
    return title, desc


def _edit_caption(v: dict, chat: str) -> None:
    """Video mesajındaki başlığı günceller; düğmeler videonun durumuna göre aynı kalır."""
    try:
        api("editMessageCaption", data={"chat_id": chat, "message_id": v["telegram_message_id"],
                                        "caption": _video_caption(v["title"], v.get("template")),
                                        "parse_mode": "HTML", "reply_markup": _kb(_kb_rows(v["tag"], v["status"]))})
    except Exception as e:  # noqa: BLE001
        if "not modified" not in str(e):  # başlık ve düğmeler aynıysa Telegram hata verir: mesaj zaten güncel
            print("Video mesajının başlığı güncellenemedi:", _redact_safe(e))


def _release_meta(tag: str) -> dict:
    """Videonun GitHub Release'indeki yalnız metadata.json dosyası (video indirilmez). İşle.yml'in hafif ortamında
    çalışır: gh yerine GitHub API + requests."""
    from urllib.parse import quote
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not (repo and token):
        raise RuntimeError("GITHUB_REPOSITORY ya da GITHUB_TOKEN tanımlı değil")
    auth = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/tags/{quote(tag, safe='')}",
                     headers={**auth, "Accept": "application/vnd.github+json"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub Release okunamadı ({r.status_code})")
    asset = next((a for a in r.json().get("assets") or [] if isinstance(a, dict) and a.get("name") == "metadata.json"),
                 None)
    # anahtar yalnız bu deponun release dosyası adresine gider (dosya alanına yönlendirmede requests onu göndermez)
    if not asset or not str(asset.get("url") or "").startswith(f"https://api.github.com/repos/{repo}/releases/assets/"):
        raise RuntimeError("GitHub Release'te metadata.json yok")
    r = requests.get(asset["url"], headers={**auth, "Accept": "application/octet-stream"}, timeout=60)
    if r.status_code != 200 or len(r.content) > 1_000_000:
        raise RuntimeError(f"metadata.json indirilemedi ({r.status_code})")
    return json.loads(r.content.decode("utf-8"))


def _write_desc(tag: str, v: dict, chat: str, text: str) -> int | None:
    """Açıklama mesajını verilen metne getirir: varsa yerinde düzenler; yoksa (eski video, notify'da gönderilemedi) ya da
    düzenlenemezse yenisini gönderip numarasını kaydeder. Güncel mesajın numarasını, yazılamazsa None döndürür."""
    mid = v.get("aciklama_message_id")
    try:
        if mid:
            try:
                api("editMessageText", data={"chat_id": chat, "message_id": mid,
                                             "text": _cut16(text, 4096), "disable_web_page_preview": "true"})
                return mid
            except Exception as e:  # noqa: BLE001
                if "not modified" in str(e):  # metin aynı: Telegram hata verir ama mesaj zaten güncel
                    return mid
                print("Açıklama mesajı düzenlenemedi, yenisi gönderiliyor:", _redact_safe(e))
        mid = _send_desc(chat, text)
        _update(tag, aciklama_message_id=mid)
        return mid
    except Exception as e:  # noqa: BLE001
        print("Açıklama mesajı güncellenemedi:", _redact_safe(e))
        return None


def _refresh_desc(tag: str, v: dict, chat: str) -> bool:
    """Panel düzenlemesinden sonra açıklama mesajını TikTok'a gidecek yeni açıklamayla günceller (_write_desc).
    metadata.json alınamazsa mesaja dokunulmaz: görsel atfı ve etiketleri eksik bir metin yazılmaz; TikTok taslağı
    gönderilirken publish_due mesajı TikTok'a giden metinle yeniler. Hata düzenlemeyi düşürmez: False döner."""
    try:
        from .publish import apply_series_tag, tiktok_caption
        text = tiktok_caption(_apply_edit(apply_series_tag(_release_meta(tag)), v.get("duzenleme") or {}))
    except Exception as e:  # noqa: BLE001
        print("metadata.json alınamadı; açıklama mesajı şimdi güncellenmedi:", _redact_safe(e))
        return False
    return _write_desc(tag, v, chat, text) is not None


# ---- Panel takvimi: platform başına elle seçilen saatler (action "schedule") ----
SCHEDULE_MAX = dt.timedelta(days=30)
# kapı (panel.js) şimdi+2 dk denetler; iş 30-60 sn geç başlayabildiği için 3 dk öncesine kadarki saat kabul edilir
SCHEDULE_LATE = dt.timedelta(minutes=3)


def _check_schedule(p: dict, approve: bool, done: set[str] = frozenset()) -> dict[str, str]:
    """Kapının (panel.js saatleriAl) denetiminin aynısı: {platform: ISO}, yalnız bilinen platformlar, saat dilimli
    geçerli ISO, dakikaya yuvarlanır, en çok 30 gün sonrası. Geçmişte kalan (en çok 3 dk) saat şimdiye çekilir.
    Onayda paylaşılmamış her platformun saati verilmeli (done: paylaşılmışlar; kalanları iptal edilip yeniden onay
    bekleyen videoda olur), paylaşılmış platformun saati verilemez. UTC ISO döndürür."""
    s = p.get("schedule")
    if not isinstance(s, dict) or not s:
        raise ValueError("platform saatleri eksik")
    if set(s) - set(PLATFORM_NAMES):
        raise ValueError("bilinmeyen platform")
    if approve:
        shared = [PLATFORM_NAMES[k] for k in PLATFORM_NAMES if k in s and k in done]
        if shared:
            raise ValueError(f"{', '.join(shared)} zaten paylaşıldı")
        missing = [PLATFORM_NAMES[k] for k in PLATFORM_NAMES if k not in s and k not in done]
        if missing:
            raise ValueError("onay için üç platformun da saati seçilmeli" if not done
                             else f"onay için {', '.join(missing)} saati de seçilmeli")
    now = dt.datetime.now(dt.timezone.utc)
    out = {}
    for k, iso in s.items():
        try:
            t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            t = None
        if t is None or t.tzinfo is None:
            raise ValueError(f"{PLATFORM_NAMES[k]} saati geçersiz")
        t = (t + dt.timedelta(seconds=30)).replace(second=0, microsecond=0)
        if t < now - SCHEDULE_LATE:
            raise ValueError(f"{PLATFORM_NAMES[k]} saati geçmişte kaldı, yeni bir saat seç")
        if t > now + SCHEDULE_MAX:
            raise ValueError(f"{PLATFORM_NAMES[k]} saati en çok 30 gün sonrası olabilir")
        out[k] = max(t, now).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    return out


def _schedule(tag: str, p: dict, v: dict, chat: str) -> str:
    """Panel takviminden gelen saatler. Onay bekleyen video tam bu saatlerle onaylanır; zamanlanmış videoda yalnız
    verilen (henüz paylaşılmamış) platformların saati değişir, verilmeyenler kendi saatinde kalır.
    Telegram'a yazılacak notu döndürür (ℹ️ ile başlayan not: değişiklik yapılmadı)."""
    if v["status"] == "onay_bekliyor":
        new = _check_schedule(p, approve=True, done=_done(v))  # paylaşılmış platform (kısmen paylaşılıp iptal) yeniden paylaşılmaz
        _update(tag, status="zamanlandi", schedule=new, publish_at=min(new.values()),
                decided=dt.datetime.now(TR).isoformat(timespec="seconds"))
        _restore_kb(tag, chat, "zamanlandi")
        return "✅ Onaylandı, takvimdeki saatlerde paylaşılacak:\n" + _sched_lines(new)
    # bu işin kopyası birkaç saniye eski olabilir: paylaşılan platformlar ve saatler için uzaktaki en güncel kayda bakılır
    fresh = _origin_record(tag) or v
    st, due = fresh.get("status", "?"), _due_at(fresh)
    if st != "zamanlandi":
        _restore_kb(tag, chat, st)
        return f"ℹ️ Saatler değiştirilmedi: video şu an '{DURUM_ADI.get(st, st)}' durumunda."
    if due and due <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=EDIT_GUARD_MIN):
        _restore_kb(tag, chat, st)
        return ("ℹ️ Saatler değiştirilmedi: bir paylaşım şu an sürüyor ya da 10 dakika içinde başlayacak. "
                "Paylaşım bittikten sonra kalan platformların saatini yeniden ayarlayabilirsin.")
    new = _check_schedule(p, approve=False)
    done = _done(v) | _done(fresh)
    shared = [PLATFORM_NAMES[x] for x in PLATFORM_NAMES if x in new and x in done]
    if shared:
        _restore_kb(tag, chat, st)
        return f"ℹ️ Saatler değiştirilmedi: {', '.join(shared)} zaten paylaşıldı."
    old = _sched_of(fresh)
    if all(old.get(k) and dt.datetime.fromisoformat(old[k]) == dt.datetime.fromisoformat(t) for k, t in new.items()):
        _restore_kb(tag, chat, st)
        return "ℹ️ Saatler zaten böyle, değişiklik yapılmadı."
    # paylaşılmış platformlar kayıtlı saatinde kalır. Saati geçip paylaşılamamış platform eskisi gibi (eski) publish_at'te
    # denenir: o saat kayda yazılır ki başka bir platform öne alınınca o da öne çekilmesin, mesaj ve panel aynı saati göstersin.
    pend = {k: t for k, t in {**_pending_sched(fresh), **new}.items() if k not in done}
    _update(tag, status="zamanlandi", schedule={**old, **pend}, publish_at=min(pend.values()))
    _restore_kb(tag, chat, "zamanlandi")
    return "🗓 Paylaşım saatleri değişti:\n" + _sched_lines(pend)


def process_panel(p: dict, chat: str) -> None:
    """Panelden gelen işlem. Telegram düğmeleriyle aynı yardımcıları (_approve, _reject, _cancel, _retry, _dispatch,
    stats.report) kullanır; sonucu sohbete "🖥 Panelden:" diye yazar ki Telegram konuşması asıl kayıt olarak kalsın."""
    action, tag = str(p.get("action") or ""), str(p.get("tag") or "")
    print("Panel işlemi:", action, tag, p.get("rid", ""))
    v = _find(load(VIDEOS, []), tag) if tag else None
    mid = (v or {}).get("telegram_message_id")

    def say(text: str) -> None:
        data = {"chat_id": chat, "text": _cut16("🖥 Panelden: " + text, 4000)}
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
            elif action == "schedule":
                say(f"{_schedule(tag, p, v, chat)}\n{v['title']}")
            elif action == "reject":
                say(f"{_reject(tag, chat, v)}\n{v['title']}")
            elif action == "cancel":
                say(f"{_cancel(tag, chat, v)}\n{v['title']}")
            elif action == "retry":
                note = _retry(tag)
                api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb([])})
                say(f"🔁 {note}\n{v['title']}")
            elif action == "edit":
                # bu işin kopyası birkaç saniye eski olabilir: karar ve saat için uzaktaki en güncel kayda bakılır
                fresh = _origin_record(tag) or v
                if fresh.get("status") not in PANEL_VIDEO_ACTIONS["edit"]:
                    _restore_kb(tag, chat, fresh.get("status"))
                    st = fresh.get("status", "?")
                    say(f"ℹ️ İşlem yapılmadı: video şu an '{DURUM_ADI.get(st, st)}' durumunda.\n{v['title']}")
                    return
                pa = fresh.get("publish_at")
                if fresh.get("status") == "zamanlandi" and pa and dt.datetime.fromisoformat(pa) <= \
                        dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=EDIT_GUARD_MIN):
                    _restore_kb(tag, chat, fresh.get("status"))
                    say("ℹ️ Düzenleme yapılmadı: bir paylaşım şu an sürüyor ya da 10 dakika içinde başlayacak. Paylaşılmayan "
                        f"platform kalırsa paylaşım bittikten sonra yeniden düzenleyebilirsin.\n{v['title']}")
                    return
                title, desc = _check_edit(p)
                first = (v.get("duzenleme") or {}).get("ilk_baslik") or v["title"]  # seri bağı (seri.json) için
                v = _update(tag, title=title, duzenleme={"title": title, "description": desc, "ilk_baslik": first,
                                                         "at": dt.datetime.now(TR).isoformat(timespec="seconds")})
                _edit_caption({**v, "status": fresh.get("status", v.get("status"))}, chat)
                # metin tekrar yazılmaz: açıklama mesajı yerinde güncellenir (TikTok'a oradan kopyalanır)
                desc_ok = _refresh_desc(tag, {**v, "aciklama_message_id": v.get("aciklama_message_id")
                                              or fresh.get("aciklama_message_id")}, chat)
                done = [PLATFORM_NAMES[x] for x in PLATFORM_NAMES if x in _done(v) | _done(fresh)]
                old_note = f"\n(Zaten paylaşılan {', '.join(done)} paylaşımında eski metin kalır.)" if done else ""
                say(f"✏️ Başlık ve açıklama güncellendi; paylaşımda yeni metin kullanılacak.{old_note}"
                    + ("" if desc_ok or "tiktok" in _done(v) | _done(fresh)
                       else "\n⚠️ Açıklama mesajı şimdi güncellenemedi; TikTok taslağı gönderilirken yenilenecek."))
        elif action == "produce_suggestion":
            from .trends import load_saved
            items, i = load_saved(), p.get("index")
            if type(i) is not int or not 0 <= i < len(items) or (p.get("topic") and items[i].get("topic") != p["topic"]):
                say("⚠️ Öneri bulunamadı; öneri listesi değişmiş olabilir. Paneli yenileyip tekrar seç.")
                return
            ok = _produce_suggestion(items[i])
            say(f"🎬 Üretim başladı: {items[i]['topic']}\nYaklaşık 15 dakikada gelir." if ok
                else "⚠️ Üretim başlatılamadı.")
        elif action == "produce_topic":
            topic = " ".join(str(p.get("topic") or "").split())
            if len(topic) > 300:
                raise ValueError("konu en fazla 300 karakter olabilir")
            from .trends import seri_tahmini
            kalip, topic = seri_tahmini(topic)
            ok = _dispatch(topic, kalip=kalip)
            say(("🎬 Üretim başladı: " + (topic or "konu sıradan veya gündemden seçilecek") + _seri_notu(kalip)
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
            rid = str(p.get("rid") or "")[:64] or None
            if isinstance(p.get("queue_base"), list):
                # sayfa listeyi yüklediğinden beri üretim sıradan konu aldıysa o konu geri gelmez (üç yollu birleştirme)
                items = konu_sirasi.save_merged(konu_sirasi.clean(p["queue_base"]), items, rid=rid)
            else:
                konu_sirasi.save(items, rid=rid)
            say(f"📋 Konu sırası kaydedildi ({len(items)} konu)." + (f"\nSıradaki: {items[0]}" if items else ""))
        else:
            say(f"⚠️ Bilinmeyen panel işlemi: {action[:40]}")
    except Exception as e:  # noqa: BLE001
        print("Panel işlemi yapılamadı.")
        note = _err_text(e)
        if v:
            _restore_kb(tag, chat)
        say(f"⚠️ İşlem yapılamadı: {note}")


def poll(wait: int = 0) -> int:
    """Yeni düğme basışlarını ve komutları işler. wait>0 ise o kadar saniye yeni olay bekler (long polling)."""
    global _menu_set
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    if not _menu_set:  # "/" yazınca açılan komut menüsü
        try:
            api("setMyCommands", data={"commands": json.dumps(COMMANDS, ensure_ascii=False)})
        except Exception as e:  # noqa: BLE001
            print("Komut menüsü ayarlanamadı:", _redact_safe(e))
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


def _due_at(v: dict) -> dt.datetime | None:
    """Paylaşım işinin zamanlanmış bir videoda bir şey paylaşacağı an (worker.js paylasimAni ile aynı kural).
    publish_due yalnız publish_at gelince ve saati gelmiş, paylaşılmamış platform varken yükler: an, publish_at ile
    bekleyen en erken platform saatinin geç olanıdır. (Saati geçip paylaşılamamış platform publish_at'te yeniden
    denenir; bekleyen bütün platformlardan erken kalmış bir publish_at ise kendi başına bir şey paylaşmaz.)"""
    if v.get("status") != "zamanlandi":
        return None
    pend = [dt.datetime.fromisoformat(t) for k, t in (v.get("schedule") or {}).items() if t and k not in _done(v)]
    cands = [x for x in (dt.datetime.fromisoformat(v["publish_at"]) if v.get("publish_at") else None,
                         min(pend) if pend else None) if x]
    return max(cands) if cands else None


def _next_due() -> dt.datetime | None:
    """Zamanlanmış videolardaki en yakın paylaşım anı (platform bazlı saatler dahil)."""
    times = [t for v in load(VIDEOS, []) if (t := _due_at(v))]
    return min(times) if times else None


def _due_times(since: dt.datetime, until: dt.datetime) -> list[dt.datetime]:
    """[since, until] içindeki paylaşım anları, sıralı ve tekil (worker.js paylasimAnlari ile aynı)."""
    return sorted({t for v in load(VIDEOS, []) if (t := _due_at(v)) and since <= t <= until})


# Seçilen saatte tam zamanında paylaşım: kapının dakikalık zamanlayıcısı (worker.js scheduled) ve işle.yml'in
# dispatch-if-due adımı, saati yaklaşan paylaşım için onay.yml'i o anı hedefleyerek başlatır. İş, paylaşımdan en çok
# birkaç dakika önce başlatılır (kurulum ~1 dk) ki Actions dakikası beklemeye harcanmasın.
DUE_WINDOW = dt.timedelta(minutes=3)  # worker.js ONCE_MS
DUE_STALE = dt.timedelta(hours=3)  # bundan eski bekleyen saat için iş başlatılmaz (takılı bir kayıt döngü yapmasın)
RUN_DEDUPE = dt.timedelta(minutes=30)
NOT_STARTED = ("queued", "pending", "waiting", "requested")  # state grubunda sırasını bekleyen (başlamamış) iş


def _due_inputs(due: dt.datetime, now: dt.datetime) -> dict[str, str]:
    """onay.yml girdileri: dakika = paylaşıma kalan dakika + 2 (en çok 15), hedef = paylaşım anı (UTC, "…THH:MMZ")."""
    left = max(0, math.ceil((due - now).total_seconds() / 60))
    return {"dakika": str(min(15, left + 2)), "hedef": due.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}


def _onay_runs() -> list[dict] | None:
    """onay.yml'in son 20 işi (iş adı hedefi içerir); öğrenilemezse None."""
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return None
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/actions/workflows/onay.yml/runs",
                         params={"per_page": 20}, timeout=30,
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            print("Paylaşım işleri listelenemedi:", r.status_code)
            return None
        runs = r.json().get("workflow_runs")
        return runs if isinstance(runs, list) else None
    except Exception as e:  # noqa: BLE001
        print("Paylaşım işleri listelenemedi:", _redact_safe(e))
        return None


def _due_covered(runs: list[dict], due: dt.datetime, now: dt.datetime) -> bool:
    """Bu paylaşım anını üstlenmiş iş var mı (worker.js isVar ile aynı): aynı hedefle kuyrukta bekleyen/çalışan ya da son
    30 dakikada başlatılmış, iptal edilmemiş iş (state grubunda yenisi gelince bekleyen iş çalışmadan iptal olur).
    Saati gelmiş paylaşımı henüz başlamamış herhangi bir iş de üstlenir: başlayınca saati gelenlerin hepsini paylaşır;
    yenisi başlatılırsa o işi iptal eder ve iki hedef birbirini iptal edip durur."""
    hedef = _due_inputs(due, now)["hedef"]
    for run in runs:
        if due <= now and run.get("status") in NOT_STARTED:
            return True
        if hedef not in f"{run.get('display_title') or ''} {run.get('name') or ''}":
            continue
        try:
            created = dt.datetime.fromisoformat(str(run.get("created_at") or "").replace("Z", "+00:00"))
        except ValueError:
            created = now  # tarihi okunamayan iş yeni sayılır
        if run.get("status") != "completed" or (run.get("conclusion") != "cancelled" and created >= now - RUN_DEDUPE):
            return True
    return False


def dispatch_if_due() -> bool:
    """Durum kaydedildikten SONRA çağrılır: 3 dakika içinde paylaşılacak bir şey varsa tek sıra hâlinde çalışan
    onay.yml'i (state grubu) o anı hedefleyerek başlatır. Anlara sırayla bakılır: üstlenen işi olan atlanır, ilk
    üstlenilmemiş an için iş başlatılır (saati geçmiş bir kaydın işi, ör. hata almış ya da hâlâ yükleyen iş, sonraki
    videonun paylaşımını bekletmesin). Kapının zamanlayıcısı da aynı hedefle başlatır. 3 saatten eski takılı kayıt
    sayılmaz. İş listesi alınamazsa ilk an için başlatılır (bu adım her kayıttan sonra bir kez çalışır, döngü yapmaz)."""
    now = dt.datetime.now(dt.timezone.utc)
    dues = _due_times(now - DUE_STALE, now + DUE_WINDOW)
    if not dues:
        return False
    runs = _onay_runs()
    for due in dues:
        if runs is not None and _due_covered(runs, due, now):
            continue
        inputs = _due_inputs(due, now)
        ok = _dispatch("", "onay.yml", inputs=inputs)
        print("Paylaşım işi başlatıldı:", ok, inputs["hedef"], "dakika:", inputs["dakika"])
        return ok
    print("Bu saatler için paylaşım işi zaten var:", ", ".join(_due_inputs(d, now)["hedef"] for d in dues))
    return False


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
            # en çok dakikada bir yeniden bakılır: bu arada panel takviminden öne alınan bir saat kaçmasın
            wait = min(wait, 60)
            time.sleep(max(5, min(wait, end - now + 1)))
    while time.time() < end:
        try:
            poll(wait=int(max(1, min(50, end - time.time()))))
            publish_due()
        except Exception as e:  # noqa: BLE001
            print("Dinleme hatası:", _redact_safe(e))
            time.sleep(5)


def publish_due() -> None:
    """Saati gelen videoları paylaşır. Daha önce başarılı olan platformlara tekrar yüklemez."""
    from .publish import apply_series_tag, fetch_release, publish
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
                res = publish(video, _apply_edit(apply_series_tag(meta), v.get("duzenleme")), todo)
        except Exception as e:  # noqa: BLE001
            from .publish import _redact
            res = {p: {"status": "hata", "error": _redact(f"video indirilemedi: {e}")[:600]} for p in todo}
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
        # TikTok taslağı: açıklama mesajı TikTok'a giden metne getirilir (eski videoda ya da notify'da gönderilemediyse
        # şimdi gönderilir, düzenlemede yazılamadıysa yenilenir) ve sonuç ona yanıt olur: alıntıya dokununca o mesaj açılır
        tt = res.get("tiktok") or {}
        desc_mid = None
        if tt.get("status") == "ok" and tt.get("draft"):
            desc_mid = _write_desc(tag, v, chat, tt["caption"]) if tt.get("caption") else v.get("aciklama_message_id")
        lines = []
        for p, r in platforms.items():
            if p not in todo:
                continue  # yalnız bu turda paylaşılanları yaz
            name = PLATFORM_NAMES[p]
            if r["status"] == "ok":  # açıklama tekrar yazılmaz: taslağa açıklama mesajından kopyalanır
                done_text = (("taslak gönderildi. Açıklamayı yanıtlanan mesajdan kopyala." if desc_mid
                              else "taslak gönderildi.") if r.get("draft") else r.get("url") or "paylaşıldı")
                lines.append(f"✅ {name}: {done_text}" + (f"\n   ⚠️ {r['note']}" if r.get("note") else "")
                             # açıklama mesajı yazılamadıysa açıklama yalnız burada gelir (taslağa yapıştırılacak)
                             + (f"\n\n{r['caption']}\n" if r.get("draft") and not desc_mid and r.get("caption") else ""))
            elif r["status"] == "hata":
                lines.append(f"❌ {name}: {_redact_safe(r.get('error'))[:300]}")
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
        reply = ({"reply_to_message_id": desc_mid, "allow_sending_without_reply": "true"} if desc_mid
                 else {"reply_to_message_id": v["telegram_message_id"]})
        api("sendMessage", data={"chat_id": chat, "text": f"{head}\n{v['title']}\n\n" + "\n".join(lines),
                                 **reply, "disable_web_page_preview": "true"})


def _redact_safe(text) -> str:
    """Günlüğe yazılan hata metni (ağ hataları adreste anahtar taşır)."""
    from .publish import _redact
    return _redact(text or "")


def _seri_notu(kalip: str) -> str:
    """Elle yazılan konudan seri tahmin edildiyse yanıta eklenen not (serbest kalıpta boş)."""
    from .trends import seri_adi
    ad = seri_adi(kalip)
    return f" ({ad} serisi; genel video için konunun başına 'genel:' yaz)" if ad else ""


def _dispatch(topic: str, workflow: str = "uret.yml", kalip: str = "", inputs: dict | None = None) -> bool:
    """kalip: üretimde sabitlenecek anlatım kalıbı (script.STRUCTURES); boşsa uret.yml'e hiç gönderilmez.
    inputs: iş akışı girdileri (verilirse topic/kalip yerine bunlar gönderilir, ör. onay.yml dakika/hedef)."""
    if kalip:
        from .script import STRUCTURES
        if kalip not in STRUCTURES:
            raise ValueError("geçersiz anlatım kalıbı")
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return False
    if inputs is None:
        inputs = {"topic": topic} if workflow == "uret.yml" else {}
        if kalip and workflow == "uret.yml":
            inputs["kalip"] = kalip
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
        note = ""
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
        if v.get("status") == "zamanlandi":
            shared = []  # paylaşılmış platformlar da görünsün (saatleri artık planda değil)
            for p in PLATFORM_NAMES:
                if p in _done(v):
                    at = (v.get("platforms") or {})[p].get("at")
                    shared.append(f"✅ {PLATFORM_NAMES[p]}: paylaşıldı" + (f" ({_fmt(at)})" if at else ""))
            body = "\n".join(shared + [_plan_text(_pending_sched(v))]).strip() \
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
    elif sys.argv[1] == "refresh-kb":  # işle.yml: durum kaydedildikten sonra düğmeleri birleşmiş duruma göre koy
        try:
            refresh_kb(json.loads(os.environ.get("UPDATE") or "{}"), str(os.environ["TELEGRAM_CHAT_ID"]))
        except Exception as e:  # noqa: BLE001  (düğme tazeleme hatası işi düşürmesin)
            print("Düğmeler tazelenemedi:", _redact_safe(e))
    elif sys.argv[1] == "dispatch-if-due":
        dispatch_if_due()
    elif sys.argv[1] == "duzelt":  # düzeltme sonrası: videonun mesajına güncel planı yanıt olarak yazar
        duzelt(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "", " ".join(sys.argv[4:]))
    elif sys.argv[1] == "notify":
        notify(Path(sys.argv[2]), sys.argv[3])
    elif sys.argv[1] == "durdu":  # uret.yml: üretim telif kuralı yüzünden durdu (pipeline'ın yazdığı kısa not)
        _durdu = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
        api("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": _cut16("⛔ " + _durdu, 4096)})
    elif sys.argv[1] == "preview":  # ornek.yml: yalnız göz atmak için, onaysız ve kayıtsız
        preview(Path(sys.argv[2]), " ".join(sys.argv[3:]))
    elif sys.argv[1] == "poll":
        poll()
    elif sys.argv[1] == "listen":
        listen(float(sys.argv[2]))
    elif sys.argv[1] == "publish-due":
        publish_due()
