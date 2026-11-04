"""Gündem konuları: Türkiye ve dünyada şu an popüler olan konulardan short fikri önerir.

Claude web aramasıyla güncel gündemi (Google Trends TR, haber manşetleri, sosyal medya gündemi,
YouTube'da yükselen konular) tarar ve her birini kanalın tarzına uygun bir "az bilinen bilgi" açısına çevirir.

    python -m shortgen.trends notify   # 5 öneriyi Telegram'a butonlarla gönderir
    python -m shortgen.trends best     # en iyi öneriyi yazdırır (otomatik üretim için)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field

from .script import CATEGORIES, _history, ask_claude

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "oneriler.json"

SYSTEM = """Sen Türkçe bilgi/merak kanalı "Bilgi Makası" için gündem editörüsün. Görevin, BUGÜN Türkiye'de ve
dünyada çok konuşulan, aranan konuları bulmak ve her birini 40-50 saniyelik bir "bunu biliyor muydun?" short'una
dönüştürecek şaşırtıcı, doğrulanabilir bir açı önermek.
Kurallar:
- Web araması yap: Google Trends Türkiye günlük aramaları, Türkiye ve dünya haber manşetleri, X/Twitter Türkiye
  gündemi, YouTube'da yükselen konular, yaklaşan önemli günler/yıl dönümleri, vizyondaki film/dizi/oyunlar, spor olayları.
- Konunun kendisini haber gibi anlatma; ona bağlı az bilinen bir bilgi, tarihçe, bilim veya ilginç bağlantı bul.
  Ör. gündem 'Dünya Kupası elemeleri' ise açı: 'Bir maçta kalecinin attığı 3 golün hikâyesi'.
- Siyasi kutuplaştırıcı, trajik (ölüm, afet, suç mağdurları), sağlık iddiası ve magazin dedikodusu konularını ÖNERME.
- Doğrulanabilir olmalı; güvenilir kaynakta geçmeli.
- Daha önce işlenen konuları tekrar etme.
- Çeşitlilik: en az 2 öneri Türkiye gündeminden, en az 2'si küresel gündemden olsun."""


class Suggestion(BaseModel):
    topic: str = Field(description="Video konusu, tek cümle, üretim için yeterince net (ör. 'Halley kuyruklu yıldızının 1910'da yarattığı panik')")
    hook: str = Field(description="Videonun açılış kancası, en fazla 12 kelime, merak uyandıran")
    trend: str = Field(description="Bağlı olduğu gündem ve neden şu an popüler, en fazla 15 kelime")
    scope: Literal["TR", "Global"]
    category: str = Field(description=f"Şunlardan biri: {', '.join(CATEGORIES)}")
    score: int = Field(description="Tahmini izlenme potansiyeli 1-10 (gündem sıcaklığı x merak x görsel zenginlik)")


class Suggestions(BaseModel):
    items: List[Suggestion]


def suggest(n: int = 5) -> list[Suggestion]:
    used = _history(ROOT / "history.jsonl")[-150:]
    today = dt.date.today().strftime("%d %B %Y")
    prompt = (f"Bugünün tarihi: {today}. Gündemi araştır ve {n} short konusu öner, en yüksek puanlı önce gelsin.")
    if used:
        prompt += "\nDaha önce işlenen konular (tekrar etme):\n- " + "\n- ".join(used)
    res = ask_claude(prompt, Suggestions, SYSTEM, web=True)
    items = sorted(res.items, key=lambda s: -s.score)[:n]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"date": str(dt.date.today()), "items": [s.model_dump() for s in items]},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def load_saved() -> list[dict]:
    """Son önerileri okur. Dinleme oturumu öneriden önce başlamış olabileceği için önce GitHub'daki güncel kopyaya bakar."""
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if repo and token:
        try:
            import requests
            r = requests.get(f"https://api.github.com/repos/{repo}/contents/state/oneriler.json",
                             headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"},
                             timeout=20)
            if r.ok:
                return r.json().get("items", [])
        except Exception:  # noqa: BLE001
            pass
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8")).get("items", [])
    return []


def notify() -> None:
    from .telegram_bot import _kb, api
    items = suggest()
    chat = os.environ["TELEGRAM_CHAT_ID"]
    lines = ["🔥 Gündemden konu önerileri:"]
    for i, s in enumerate(items, 1):
        flag = "🇹🇷" if s.scope == "TR" else "🌍"
        lines.append(f"\n{i}. {flag} {s.topic}\n   🎣 {s.hook}\n   📈 {s.trend} (puan {s.score}/10)")
    lines.append("\nÜretmek istediğin konunun numarasına bas.")
    rows = [[(f"🎬 {i}", f"tp:_:{i - 1}") for i in range(1, len(items) + 1)]]
    api("sendMessage", data={"chat_id": chat, "text": "\n".join(lines), "reply_markup": _kb(rows),
                             "disable_web_page_preview": "true"})


if __name__ == "__main__":
    from .pipeline import load_env
    load_env(ROOT / ".env")
    if sys.argv[1] == "notify":
        notify()
    elif sys.argv[1] == "best":
        s = suggest(3)[0]
        print(f"{s.topic} (kanca: {s.hook}; gündem: {s.trend})")
