"""Yorum cevapları: yeni yorumları toplar, Claude ile cevap taslağı yazar, Telegram'a onaya gönderir.

python -m shortgen.comments check    # yeni yorumları topla, taslak yaz, Telegram'a gönder
python -m shortgen.comments izin     # okuma/cevaplama izinlerini dener (hiçbir şey göndermez)

Onaylanan taslak telegram_bot içindeki cm:ok düğmesiyle send_reply() üzerinden gönderilir.
Telegram'da taslak mesajına yanıt olarak yazılan metin, taslağın yerine gönderilir.
TikTok yorum API'si sunmadığı için yalnızca YouTube ve Instagram.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import List

import requests
from pydantic import BaseModel, Field

from . import publish as P

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
FILE = STATE / "yorumlar.json"
YT = "https://www.googleapis.com/youtube/v3"
MAX_NEW = int(os.environ.get("COMMENT_MAX", "15"))


def load() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"seen": [], "pending": {}}


def save(d: dict) -> None:
    d["seen"] = d["seen"][-3000:]
    FILE.parent.mkdir(exist_ok=True)
    FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _videos() -> list[dict]:
    try:
        v = json.loads((STATE / "videos.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return [x for x in v if x.get("platforms")]


# ------------------------------------------------------------------ toplama
def _yt_comments(videos: list[dict]) -> list[dict]:
    key = os.environ.get("YT_API_KEY", "").strip()
    out = []
    for x in videos:
        p = x["platforms"].get("youtube", {})
        if p.get("status") != "ok":
            continue
        r = requests.get(f"{YT}/commentThreads", timeout=30, params={
            "part": "snippet", "videoId": p["id"], "maxResults": 50, "order": "time", "key": key})
        if not r.ok:
            print("YouTube yorumları okunamadı:", r.status_code, r.text[:200])
            continue
        for it in r.json().get("items", []):
            sn = it["snippet"]
            top = sn["topLevelComment"]["snippet"]
            if top.get("authorChannelId", {}).get("value") == os.environ.get("YT_CHANNEL_ID"):
                continue
            out.append({"id": f"yt:{it['id']}", "platform": "youtube", "parent": it["id"], "tag": x["tag"],
                        "video": x["title"], "author": top.get("authorDisplayName", ""),
                        "text": top.get("textOriginal", "")[:500]})
    return out


def _ig_comments(videos: list[dict]) -> list[dict]:
    uid, token = P._env("IG_USER_ID", "IG_ACCESS_TOKEN")
    g = f"{P._ig_base(token)}/{P.IG_VER}"
    me = requests.get(f"{g}/{uid}", params={"fields": "username", "access_token": token}, timeout=30).json()
    out = []
    for x in videos:
        p = x["platforms"].get("instagram", {})
        if p.get("status") != "ok":
            continue
        r = requests.get(f"{g}/{p['id']}/comments", timeout=30, params={
            "fields": "id,text,username,replies{username}", "limit": 50, "access_token": token})
        if not r.ok:
            print("Instagram yorumları okunamadı:", r.status_code, r.text[:200])
            continue
        for c in r.json().get("data", []):
            if c.get("username") == me.get("username"):
                continue
            if any(rp.get("username") == me.get("username") for rp in (c.get("replies") or {}).get("data", [])):
                continue  # zaten cevaplamışız
            out.append({"id": f"ig:{c['id']}", "platform": "instagram", "parent": c["id"], "tag": x["tag"],
                        "video": x["title"], "author": c.get("username", ""), "text": (c.get("text") or "")[:500]})
    return out


# ------------------------------------------------------------------ taslak
class Draft(BaseModel):
    id: str
    reply: str = Field(description="Cevap metni. Boş bırakılırsa bu yoruma cevap önerilmez.")


class Drafts(BaseModel):
    drafts: List[Draft]


SYSTEM = """Sen "Bilgi Makası" (@bilgimakasi) adlı Türkçe bilgi kanalının yorum cevaplarını yazıyorsun.
Kanalın sloganı: "Kesip biçilmiş bilgi." Ton: samimi, kısa, bilgili, saygılı; resmî değil ama laubali de değil.
Kurallar:
- Her cevap 1-2 kısa cümle (en fazla ~200 karakter). Yorumcuya adıyla hitap etme, @ kullanma.
- Soruya cevap veriyorsa doğru ve kısa cevap ver; emin olmadığın bilgiyi uydurma.
- Mümkünse konuşmayı sürdüren küçük bir soru ya da ek ilginç bilgi ekle (etkileşim artsın).
- Beğeni/takip dilenme, link, reklam, etiket yok. En fazla 1 emoji.
- Hakaret, spam, siyaset/din tartışması, anlamsız veya yalnızca emoji olan yorumlara reply boş bırak.
- Eleştiriye savunmaya geçmeden, teşekkür ederek ve düzeltme gerekiyorsa kabul ederek cevap ver.
- Yorum hangi dildeyse o dilde cevap ver."""


def draft(comments: list[dict]) -> dict[str, str]:
    from .script import ask_claude
    if not comments:
        return {}
    payload = [{"id": c["id"], "video": c["video"], "yorum": c["text"]} for c in comments]
    res = ask_claude("Bu yorumlara cevap taslağı yaz:\n" + json.dumps(payload, ensure_ascii=False, indent=1),
                     Drafts, SYSTEM)
    return {d.id: d.reply.strip() for d in res.drafts if d.reply.strip()}


# ------------------------------------------------------------------ gönderme
def send_reply(item: dict, text: str) -> str:
    if item["platform"] == "youtube":
        r = requests.post(f"{YT}/comments", params={"part": "snippet"}, timeout=30,
                          headers={"Authorization": f"Bearer {P._yt_token()}"},
                          json={"snippet": {"parentId": item["parent"], "textOriginal": text}})
        if r.status_code == 403:
            raise PermissionError("YouTube cevap izni yok: YouTube girişi 'youtube.force-ssl' izniyle yenilenmeli")
        r.raise_for_status()
        return r.json().get("id", "")
    uid, token = P._env("IG_USER_ID", "IG_ACCESS_TOKEN")
    g = f"{P._ig_base(token)}/{P.IG_VER}"
    r = requests.post(f"{g}/{item['parent']}/replies", data={"message": text, "access_token": token}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Instagram cevabı gönderilemedi: {r.text[:200]}")
    return r.json().get("id", "")


# ------------------------------------------------------------------ akış
def check() -> int:
    from .telegram_bot import api, _kb
    st = load()
    seen = set(st["seen"])
    videos = _videos()
    found = []
    for fn in (_yt_comments, _ig_comments):
        try:
            found += fn(videos)
        except P.Skip:
            pass
        except Exception as e:  # noqa: BLE001
            print(f"{fn.__name__} hatası:", e)
    new = [c for c in found if c["id"] not in seen][:MAX_NEW]
    if not new:
        print("Yeni yorum yok.")
        return 0
    drafts = draft(new)
    chat = os.environ["TELEGRAM_CHAT_ID"]
    sent = 0
    for c in new:
        st["seen"].append(c["id"])
        reply = drafts.get(c["id"])
        if not reply:
            continue
        icon = {"youtube": "▶️ YouTube", "instagram": "📸 Instagram"}[c["platform"]]
        text = (f"💬 {icon} · {c['video'][:50]}\n{c['author']}: {c['text']}\n\n"
                f"✍️ Taslak cevap:\n{reply}\n\n(Değiştirmek için bu mesaja yanıt olarak kendi cevabını yaz.)")
        key = str(len(st["seen"]))  # kısa düğme anahtarı
        m = api("sendMessage", data={"chat_id": chat, "text": text, "reply_markup": _kb(
            [[("✅ Gönder", f"cm:ok:{key}"), ("❌ Geç", f"cm:no:{key}")]])})
        st["pending"][key] = {**c, "reply": reply, "message_id": m["message_id"],
                              "created": dt.datetime.now().isoformat(timespec="seconds")}
        sent += 1
    save(st)
    print(f"{len(new)} yeni yorum, {sent} taslak gönderildi.")
    return sent


def handle(action: str, key: str, chat: str, mid: int, custom: str | None = None) -> str:
    """Telegram düğmesi / yanıtı: taslağı gönder veya geç."""
    from .telegram_bot import api, _kb
    st = load()
    item = st["pending"].get(key)
    if not item:
        return "Bu yorum zaten işlenmiş."
    if action == "no":
        st["pending"].pop(key)
        save(st)
        api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb([])})
        return "Geçildi."
    text = (custom or item["reply"]).strip()
    try:
        send_reply(item, text)
    except Exception as e:  # noqa: BLE001
        return f"Gönderilemedi: {str(e)[:200]}"
    st["pending"].pop(key)
    save(st)
    api("editMessageReplyMarkup", data={"chat_id": chat, "message_id": mid, "reply_markup": _kb([])})
    return "✅ Cevap gönderildi: " + text[:100]


def by_message(mid: int) -> str | None:
    for k, v in load()["pending"].items():
        if v.get("message_id") == mid:
            return k
    return None


def izin() -> None:
    videos = _videos()
    try:
        print("YouTube okuma:", len(_yt_comments(videos)), "yorum")
    except Exception as e:  # noqa: BLE001
        print("YouTube okuma hatası:", e)
    try:
        tok = P._yt_token()
        sc = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": tok}, timeout=30).json()
        print("YouTube izinleri:", sc.get("scope"))
    except Exception as e:  # noqa: BLE001
        print("YouTube izin sorgusu hatası:", e)
    try:
        print("Instagram okuma:", len(_ig_comments(videos)), "yorum")
    except Exception as e:  # noqa: BLE001
        print("Instagram okuma hatası:", e)


if __name__ == "__main__":
    from .pipeline import load_env
    load_env(ROOT / ".env")
    {"check": check, "izin": izin}[sys.argv[1]]()
