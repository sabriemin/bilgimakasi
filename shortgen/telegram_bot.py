"""Telegram onay botu.

notify <klasör> <etiket>: Yeni videoyu Onayla / Reddet düğmeleriyle Telegram'a gönderir.
poll: Düğme basışlarını ve komutları okur, state/videos.json dosyasını günceller.

Komutlar: /durum (bekleyenler), /uret [konu] (hemen yeni video üret).
Yalnızca TELEGRAM_CHAT_ID'deki kişiden gelen mesajlar işlenir.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
VIDEOS = STATE / "videos.json"
OFFSET = STATE / "telegram_offset.json"


def api(method: str, **kw):
    r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}", timeout=120, **kw)
    r.raise_for_status()
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


def _set_status(tag: str, status: str) -> dict | None:
    videos = load(VIDEOS, [])
    for v in videos:
        if v["tag"] == tag:
            v["status"] = status
            v["decided"] = dt.datetime.now().isoformat(timespec="seconds")
            save(VIDEOS, videos)
            return v
    return None


def _dispatch(topic: str) -> bool:
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return False
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/uret.yml/dispatches",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      json={"ref": os.environ.get("GITHUB_REF_NAME", "main"), "inputs": {"topic": topic}}, timeout=30)
    return r.status_code == 204


def poll() -> list[str]:
    """Yeni olayları işler; onaylanan etiketleri döndürür (yükleme adımı için)."""
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    off = load(OFFSET, {"offset": 0})
    approved = []
    for u in api("getUpdates", data={"offset": off["offset"], "timeout": 0}):
        off["offset"] = u["update_id"] + 1
        if cq := u.get("callback_query"):
            if str(cq["from"]["id"]) != chat:
                continue
            action, tag = cq["data"].split(":", 1)
            v = _set_status(tag, "onaylandi" if action == "ok" else "reddedildi")
            note = "✅ Onaylandı, yüklemeye alındı." if action == "ok" else "❌ Reddedildi."
            api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": note})
            if v:
                api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": v["telegram_message_id"],
                                                    "reply_markup": json.dumps({"inline_keyboard": []})})
                api("sendMessage", data={"chat_id": chat, "text": f"{note}\n{v['title']}",
                                         "reply_to_message_id": v["telegram_message_id"]})
            if action == "ok":
                approved.append(tag)
        elif (m := u.get("message")) and str(m["chat"]["id"]) == chat:
            text = (m.get("text") or "").strip()
            if text.startswith("/durum"):
                vs = load(VIDEOS, [])
                bekleyen = [v for v in vs if v["status"] == "onay_bekliyor"]
                lines = [f"Toplam video: {len(vs)}", f"Onay bekleyen: {len(bekleyen)}"]
                lines += [f"• {v['title']}" for v in bekleyen[-10:]]
                api("sendMessage", data={"chat_id": chat, "text": "\n".join(lines)})
            elif text.startswith("/uret"):
                topic = text[5:].strip()
                ok = _dispatch(topic)
                api("sendMessage", data={"chat_id": chat, "text": "Üretim başlatıldı, birkaç dakika içinde gelir." if ok
                                         else "Üretim başlatılamadı."})
            elif text.startswith("/start"):
                api("sendMessage", data={"chat_id": chat, "text": "Merhaba! Yeni videolar buraya gelecek.\n"
                                         "/durum: bekleyen videolar\n/uret [konu]: hemen yeni video üret"})
    save(OFFSET, off)
    return approved


if __name__ == "__main__":
    from .pipeline import load_env
    load_env(ROOT / ".env")
    if sys.argv[1] == "notify":
        notify(Path(sys.argv[2]), sys.argv[3])
    elif sys.argv[1] == "poll":
        for t in poll():
            print(t)
