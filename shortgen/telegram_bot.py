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


def api(method: str, **kw):
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


def _update(tag: str, **fields) -> dict | None:
    videos = load(VIDEOS, [])
    v = _find(videos, tag)
    if v:
        v.update(fields)
        save(VIDEOS, videos)
    return v


def _slots(now: dt.datetime | None = None) -> list[tuple[str, str, dt.datetime]]:
    """Saat seçenekleri: (kod, düğme yazısı, UTC zamanı). Geçmişte kalan saatler gösterilmez."""
    now = now or dt.datetime.now(TR)
    today, tomorrow = now.date(), now.date() + dt.timedelta(days=1)
    out = [("now", "⚡ Şimdi", now)]
    for code, label, day, hour in (("b12", "Bugün 12:00", today, 12), ("b19", "Bugün 19:00", today, 19),
                                   ("y12", "Yarın 12:00", tomorrow, 12), ("y19", "Yarın 19:00", tomorrow, 19)):
        t = dt.datetime.combine(day, dt.time(hour), TR)
        if t > now + dt.timedelta(minutes=15):
            out.append((code, "🕒 " + label, t))
    return out


def _fmt(iso: str) -> str:
    t = dt.datetime.fromisoformat(iso).astimezone(TR)
    day = "bugün" if t.date() == dt.datetime.now(TR).date() else t.strftime("%d.%m")
    return f"{day} {t:%H:%M}"


def _kb(rows: list[list[tuple[str, str]]]) -> str:
    return json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in rows]})


def _handle_callback(cq: dict, chat: str) -> None:
    action, _, rest = cq["data"].partition(":")
    tag, _, arg = rest.partition(":")
    videos = load(VIDEOS, [])
    v = _find(videos, tag)
    if not v:
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
        when = next((t for code, _, t in _slots() if code == arg), dt.datetime.now(TR))
        iso = when.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
        _update(tag, status="zamanlandi", publish_at=iso, decided=dt.datetime.now(TR).isoformat(timespec="seconds"))
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb(
            [[("🚫 Paylaşımı iptal et", f"cancel:{tag}")]])})
        note = "✅ Onaylandı. " + ("Birkaç dakika içinde paylaşılacak." if arg == "now"
                                   else f"Paylaşım zamanı: {_fmt(iso)}")
        api("sendMessage", data={"chat_id": chat, "text": f"{note}\n{v['title']}", "reply_to_message_id": mid})
    elif action == "cancel":
        if v["status"] == "zamanlandi":
            _update(tag, status="onay_bekliyor", publish_at=None)
            api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb(
                [[("✅ Onayla", f"ok:{tag}"), ("❌ Reddet", f"no:{tag}")]])})
            note = "Paylaşım iptal edildi, video yeniden onay bekliyor."
        else:
            note = "Bu video zaten paylaşıldı veya paylaşılıyor."
    elif action == "no":
        _update(tag, status="reddedildi", decided=dt.datetime.now(TR).isoformat(timespec="seconds"))
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb([])})
        note = "❌ Reddedildi."
        api("sendMessage", data={"chat_id": chat, "text": f"{note}\n{v['title']}", "reply_to_message_id": mid})
    elif action == "rt":  # hatalı platformları yeniden dene
        _update(tag, status="zamanlandi", publish_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        note = "Hatalı platformlar birkaç dakika içinde yeniden denenecek."
    api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": note[:190]})


def poll(wait: int = 0) -> int:
    """Yeni düğme basışlarını ve komutları işler. wait>0 ise o kadar saniye yeni olay bekler (long polling)."""
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    off = load(OFFSET, {"offset": 0})
    updates = api("getUpdates", data={"offset": off["offset"], "timeout": wait}) or []
    for u in updates:
        off["offset"] = u["update_id"] + 1
        save(OFFSET, off)  # bir olay hata verse bile tekrar tekrar işlenmesin
        if cq := u.get("callback_query"):
            if str(cq["from"]["id"]) == chat:
                try:
                    _handle_callback(cq, chat)
                except Exception as e:  # noqa: BLE001
                    print("Düğme işlenemedi:", e)
        elif (m := u.get("message")) and str(m["chat"]["id"]) == chat:
            text = (m.get("text") or "").strip()
            if text.startswith("/durum"):
                vs = load(VIDEOS, [])
                bekleyen = [v for v in vs if v["status"] == "onay_bekliyor"]
                plan = [v for v in vs if v["status"] == "zamanlandi"]
                lines = [f"Toplam video: {len(vs)}", f"Onay bekleyen: {len(bekleyen)}"]
                lines += [f"• {v['title']}" for v in bekleyen[-10:]]
                if plan:
                    lines += ["", f"Zamanlanan: {len(plan)}"]
                    lines += [f"• {_fmt(v['publish_at'])}: {v['title']}" for v in plan]
                api("sendMessage", data={"chat_id": chat, "text": "\n".join(lines)})
            elif text.startswith("/uret"):
                topic = text[5:].strip()
                ok = _dispatch(topic)
                api("sendMessage", data={"chat_id": chat, "text": "Üretim başlatıldı, birkaç dakika içinde gelir." if ok
                                         else "Üretim başlatılamadı."})
            elif text.startswith("/start"):
                api("sendMessage", data={"chat_id": chat, "text": "Merhaba! Yeni videolar buraya gelecek.\n"
                                         "/durum: bekleyen ve zamanlanan videolar\n/uret [konu]: hemen yeni video üret"})
    save(OFFSET, off)
    return len(updates)


def listen(minutes: float) -> None:
    """Belirtilen süre boyunca düğmelere anında yanıt verir ve saati gelenleri hemen paylaşır."""
    import time
    end = time.time() + minutes * 60
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
        _update(tag, status="yayinlaniyor")
        done = {k for k, r in (v.get("platforms") or {}).items() if r.get("status") == "ok"}
        todo = [p for p in PLATFORM_NAMES if p not in done]
        try:
            with tempfile.TemporaryDirectory() as d:
                video, meta = fetch_release(tag, Path(d))
                res = publish(video, meta, todo)
        except Exception as e:  # noqa: BLE001
            res = {p: {"status": "hata", "error": f"video indirilemedi: {e}"[:600]} for p in todo}
        platforms = {**(v.get("platforms") or {}), **res}
        failed = [p for p, r in platforms.items() if r.get("status") == "hata"]
        ok = [p for p, r in platforms.items() if r.get("status") == "ok"]
        status = "kismen" if failed and ok else "hata" if failed else "yayinlandi" if ok else "baglanti_yok"
        _update(tag, status=status, platforms=platforms,
                published=dt.datetime.now(TR).isoformat(timespec="seconds"))
        lines = []
        for p, r in platforms.items():
            name = PLATFORM_NAMES[p]
            if r["status"] == "ok":
                lines.append(f"✅ {name}: {r.get('url') or 'paylaşıldı'}" + (f"\n   ⚠️ {r['note']}" if r.get("note") else ""))
            elif r["status"] == "hata":
                lines.append(f"❌ {name}: {r['error'][:300]}")
            else:
                lines.append(f"➖ {name}: bağlı değil")
        head = {"yayinlandi": "📢 Paylaşıldı", "kismen": "⚠️ Kısmen paylaşıldı", "hata": "❌ Paylaşılamadı",
                "baglanti_yok": "➖ Hiçbir platform bağlı değil, paylaşım yapılmadı"}[status]
        kb = _kb([[("🔁 Hatalıları tekrar dene", f"rt:{tag}")]]) if failed else _kb([])
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": v["telegram_message_id"], "reply_markup": kb})
        api("sendMessage", data={"chat_id": chat, "text": f"{head}\n{v['title']}\n\n" + "\n".join(lines),
                                 "reply_to_message_id": v["telegram_message_id"], "disable_web_page_preview": "true"})


def _dispatch(topic: str) -> bool:
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return False
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/uret.yml/dispatches",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      json={"ref": os.environ.get("GITHUB_REF_NAME", "main"), "inputs": {"topic": topic}}, timeout=30)
    return r.status_code == 204


if __name__ == "__main__":
    from .pipeline import load_env
    load_env(ROOT / ".env")
    if sys.argv[1] == "notify":
        notify(Path(sys.argv[2]), sys.argv[3])
    elif sys.argv[1] == "poll":
        poll()
    elif sys.argv[1] == "listen":
        listen(float(sys.argv[2]))
    elif sys.argv[1] == "publish-due":
        publish_due()
