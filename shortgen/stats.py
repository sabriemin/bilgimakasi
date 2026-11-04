"""İstatistik raporu: platform bazlı, video bazlı ve toplam izlenme / takipçi / beğeni / yorum / kaydetme / paylaşım.

python -m shortgen.stats report   # raporu Telegram'a gönderir ve state/stats.json'a kaydeder
python -m shortgen.stats print    # yalnızca ekrana yazar

Her platform ayrı denenir; izin eksikse o platform raporda "izin gerekli" olarak görünür, diğerleri etkilenmez.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

from . import publish as P

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
VIDEOS = STATE / "videos.json"
SNAP = STATE / "stats.json"
TR = dt.timezone(dt.timedelta(hours=3))
KEYS = ("views", "likes", "comments", "saves", "shares")
LABEL = {"views": "👁", "likes": "❤️", "comments": "💬", "saves": "🔖", "shares": "↗️"}


def _published() -> list[dict]:
    try:
        v = json.loads(VIDEOS.read_text())
    except Exception:  # noqa: BLE001
        return []
    return [x for x in v if x.get("platforms")]


def _int(x) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ YouTube
def youtube(videos: list[dict]) -> dict:
    h = {"Authorization": f"Bearer {P._yt_token()}"}
    base = "https://www.googleapis.com/youtube/v3"
    out = {"account": {}, "videos": {}}
    ch = requests.get(f"{base}/channels", headers=h, params={"part": "statistics", "mine": "true"}, timeout=30)
    if ch.status_code == 403:
        raise PermissionError("YouTube okuma izni yok (anahtar yalnız yükleme izniyle alınmış)")
    ch.raise_for_status()
    st = (ch.json().get("items") or [{}])[0].get("statistics", {})
    out["account"] = {"followers": _int(st.get("subscriberCount")), "views": _int(st.get("viewCount")),
                      "videos": _int(st.get("videoCount"))}
    ids = {x["platforms"]["youtube"]["id"]: x for x in videos
           if x["platforms"].get("youtube", {}).get("status") == "ok"}
    for i in range(0, len(ids), 50):
        chunk = list(ids)[i:i + 50]
        r = requests.get(f"{base}/videos", headers=h, params={"part": "statistics", "id": ",".join(chunk)}, timeout=30)
        r.raise_for_status()
        for it in r.json().get("items", []):
            s = it["statistics"]
            out["videos"][ids[it["id"]]["tag"]] = {"views": _int(s.get("viewCount")), "likes": _int(s.get("likeCount")),
                                                  "comments": _int(s.get("commentCount"))}
    return out


# ------------------------------------------------------------------ Instagram
def instagram(videos: list[dict]) -> dict:
    uid, token = P._env("IG_USER_ID", "IG_ACCESS_TOKEN")
    g = f"{P._ig_base(token)}/{P.IG_VER}"
    out = {"account": {}, "videos": {}}
    me = requests.get(f"{g}/{uid}", params={"fields": "followers_count,media_count", "access_token": token}, timeout=30)
    me.raise_for_status()
    out["account"] = {"followers": _int(me.json().get("followers_count")), "videos": _int(me.json().get("media_count"))}
    missing = False
    for x in videos:
        p = x["platforms"].get("instagram", {})
        if p.get("status") != "ok" or not p.get("id"):
            continue
        row = {}
        r = requests.get(f"{g}/{p['id']}/insights", timeout=30, params={
            "metric": "views,likes,comments,saved,shares", "access_token": token})
        if r.ok:
            for m in r.json().get("data", []):
                val = (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value"))
                row[{"saved": "saves"}.get(m["name"], m["name"])] = _int(val)
        else:
            missing = True
            b = requests.get(f"{g}/{p['id']}", params={"fields": "like_count,comments_count", "access_token": token},
                             timeout=30)
            if b.ok:
                row = {"likes": _int(b.json().get("like_count")), "comments": _int(b.json().get("comments_count"))}
        out["videos"][x["tag"]] = row
    for k in KEYS:
        out["account"][k] = sum(v.get(k, 0) for v in out["videos"].values())
    if missing:
        out["note"] = "izlenme/kaydetme için Instagram içgörü izni gerekli"
    return out


# ------------------------------------------------------------------ TikTok
def tiktok(videos: list[dict]) -> dict:
    h = {"Authorization": f"Bearer {P._tt_token()}", "Content-Type": "application/json"}
    out = {"account": {}, "videos": {}, "list": []}
    u = requests.get(f"{P.TT}/user/info/", headers=h, timeout=30,
                     params={"fields": "follower_count,likes_count,video_count"}).json()
    if u.get("error", {}).get("code") not in (None, "ok"):
        raise PermissionError("TikTok istatistik izni yok (user.info.stats / video.list eklenmeli)")
    d = u.get("data", {}).get("user", {})
    out["account"] = {"followers": _int(d.get("follower_count")), "likes": _int(d.get("likes_count")),
                      "videos": _int(d.get("video_count"))}
    r = requests.post(f"{P.TT}/video/list/", headers=h, timeout=30, json={"max_count": 20},
                      params={"fields": "id,title,view_count,like_count,comment_count,share_count"}).json()
    if r.get("error", {}).get("code") not in (None, "ok"):
        out["note"] = "video listesi için TikTok video.list izni gerekli"
        return out
    for it in r.get("data", {}).get("videos", []):
        out["list"].append({"title": it.get("title", "")[:60], "views": _int(it.get("view_count")),
                            "likes": _int(it.get("like_count")), "comments": _int(it.get("comment_count")),
                            "shares": _int(it.get("share_count"))})
    for k in ("views", "comments", "shares"):
        out["account"][k] = sum(v.get(k, 0) for v in out["list"])
    return out


FETCH = {"youtube": youtube, "instagram": instagram, "tiktok": tiktok}
NAMES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}


def collect() -> dict:
    videos = _published()
    snap = {"time": dt.datetime.now(TR).isoformat(timespec="minutes"), "platforms": {}}
    for name, fn in FETCH.items():
        try:
            snap["platforms"][name] = fn(videos)
        except P.Skip:
            snap["platforms"][name] = {"error": "bağlı değil"}
        except PermissionError as e:
            snap["platforms"][name] = {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            snap["platforms"][name] = {"error": f"okunamadı ({str(e)[:120]})"}
    snap["titles"] = {x["tag"]: x.get("title", x["tag"]) for x in videos}
    return snap


def _n(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def _delta(cur: int, old) -> str:
    if old is None or cur == old:
        return ""
    return f" ({'+' if cur > old else ''}{_n(cur - old)})"


def render(snap: dict, prev: dict | None) -> str:
    prev = prev or {"platforms": {}}
    lines = [f"📊 Bilgi Makası raporu · {snap['time'][:16].replace('T', ' ')}"]
    total = {k: 0 for k in ("followers",) + KEYS}
    for name, d in snap["platforms"].items():
        lines.append("")
        if "error" in d:
            lines.append(f"▪️ {NAMES[name]}: {d['error']}")
            continue
        a, pa = d["account"], prev["platforms"].get(name, {}).get("account", {})
        parts = [f"👥 {_n(a.get('followers', 0))}{_delta(a.get('followers', 0), pa.get('followers'))}"]
        for k in KEYS:
            if k in a:
                parts.append(f"{LABEL[k]} {_n(a[k])}{_delta(a[k], pa.get(k))}")
                total[k] += a[k]
        total["followers"] += a.get("followers", 0)
        lines.append(f"▪️ {NAMES[name]}: " + "  ".join(parts))
        if d.get("note"):
            lines.append(f"   ({d['note']})")
    lines += ["", "Σ Toplam: " + "  ".join(
        [f"👥 {_n(total['followers'])}"] + [f"{LABEL[k]} {_n(total[k])}" for k in KEYS if total[k]])]
    # video bazlı
    rows = []
    for tag, title in snap.get("titles", {}).items():
        per = []
        for name in ("youtube", "instagram"):
            v = snap["platforms"].get(name, {}).get("videos", {}).get(tag)
            if v:
                per.append(f"{NAMES[name][:2]} " + " ".join(f"{LABEL[k]}{_n(v[k])}" for k in KEYS if k in v))
        if per:
            rows.append((sum(snap["platforms"].get(n, {}).get("videos", {}).get(tag, {}).get("views", 0)
                             for n in ("youtube", "instagram")), f"🎬 {title[:45]}\n   " + " | ".join(per)))
    tt = snap["platforms"].get("tiktok", {}).get("list") or []
    if rows or tt:
        lines += ["", "Videolar (en çok izlenen üstte):"]
        lines += [r for _, r in sorted(rows, reverse=True)[:10]]
        for v in sorted(tt, key=lambda v: -v["views"])[:5]:
            lines.append(f"🎵 TikTok · {v['title'][:40]}\n   " + " ".join(f"{LABEL[k]}{_n(v[k])}" for k in KEYS if k in v))
    return "\n".join(lines)[:4000]


def report(send: bool = True) -> str:
    try:
        prev = json.loads(SNAP.read_text())
    except Exception:  # noqa: BLE001
        prev = None
    snap = collect()
    text = render(snap, prev)
    if send:
        from .telegram_bot import api
        api("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text})
        SNAP.parent.mkdir(exist_ok=True)
        SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    return text


if __name__ == "__main__":
    from .pipeline import load_env
    load_env(ROOT / ".env")
    print(report(send=sys.argv[1:2] == ["report"]))
