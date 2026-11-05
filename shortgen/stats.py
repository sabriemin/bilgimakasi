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
HIST = STATE / "stats_gecmis.jsonl"
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
    base = "https://www.googleapis.com/youtube/v3"
    out = {"account": {}, "videos": {}}
    key = os.environ.get("YT_API_KEY", "").strip()
    h, auth = {"Authorization": f"Bearer {P._yt_token()}"}, {}
    ch = requests.get(f"{base}/channels", headers=h, params={"part": "statistics", "mine": "true"}, timeout=30)
    if ch.status_code == 403:
        if not key:
            raise PermissionError("YouTube okuma izni yok: YT_API_KEY eklenmeli")
        # herkese açık istatistikler API anahtarıyla okunur
        h, auth = {}, {"key": key}
        cid = os.environ.get("YT_CHANNEL_ID", "").strip()
        if not cid:
            first = next((x["platforms"]["youtube"]["id"] for x in videos
                          if x["platforms"].get("youtube", {}).get("status") == "ok"), None)
            r = requests.get(f"{base}/videos", params={"part": "snippet", "id": first, **auth}, timeout=30)
            r.raise_for_status()
            cid = r.json()["items"][0]["snippet"]["channelId"]
        ch = requests.get(f"{base}/channels", params={"part": "statistics", "id": cid, **auth}, timeout=30)
    ch.raise_for_status()
    st = (ch.json().get("items") or [{}])[0].get("statistics", {})
    out["account"] = {"followers": _int(st.get("subscriberCount")), "views": _int(st.get("viewCount")),
                      "videos": _int(st.get("videoCount"))}
    ids = {x["platforms"]["youtube"]["id"]: x for x in videos
           if x["platforms"].get("youtube", {}).get("status") == "ok"}
    for i in range(0, len(ids), 50):
        chunk = list(ids)[i:i + 50]
        r = requests.get(f"{base}/videos", headers=h, params={"part": "statistics", "id": ",".join(chunk), **auth}, timeout=30)
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
            missing = (r.json().get("error", {}).get("message") or r.text)[:150]
            b = requests.get(f"{g}/{p['id']}", params={"fields": "like_count,comments_count", "access_token": token},
                             timeout=30)
            if b.ok:
                row = {"likes": _int(b.json().get("like_count")), "comments": _int(b.json().get("comments_count"))}
        out["videos"][x["tag"]] = row
    for k in KEYS:
        if any(k in v for v in out["videos"].values()):
            out["account"][k] = sum(v.get(k, 0) for v in out["videos"].values())
    if missing:
        print("Instagram içgörü hatası:", P._redact(missing))
        out["note"] = "izlenme ve kaydetme için Instagram içgörü izni gerekli"
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
            snap["platforms"][name] = {"error": P._redact(e)}
        except Exception as e:  # noqa: BLE001  # ağ hatası metni adresi (Instagram anahtarıyla) içerebilir
            snap["platforms"][name] = {"error": f"okunamadı ({P._redact(e)[:120]})"}
    snap["titles"] = {x["tag"]: x.get("title", x["tag"]) for x in videos}
    return snap


def _n(x: int) -> str:
    return f"{x:,}".replace(",", ".")


# Telegram'da tablo <pre> (eş genişlikli yazı) içinde gönderilir. Telefonda satır kaymasın diye bir satır en çok W
# karakter olur (küçük ekranlı telefonda ~30 karakter sığar); uzun video adları kısaltılır. Tablo içinde emoji
# kullanılmaz (genişliği yazı tipine göre değişir, sütunlar kayar).
W = 30
AY = ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")
ROWS = (("followers", "Takipçi"), ("views", "İzlenme"), ("likes", "Beğeni"), ("comments", "Yorum"),
        ("saves", "Kaydetme"), ("shares", "Paylaşım"))
COL = {"youtube": "YouTube", "instagram": "Insta", "tiktok": "TikTok"}
WORD = {"followers": "takipçi", "views": "izlenme", "likes": "beğeni", "comments": "yorum", "saves": "kaydetme",
        "shares": "paylaşım"}


def _when(iso: str, ref: str | None = None) -> str:
    """'2026-11-05T07:19+03:00' -> '5 Kas 07:19'; ref ile aynı günse yalnız saat."""
    try:
        t = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso or "")[:16].replace("T", " ")
    if ref and str(ref)[:10] == str(iso)[:10]:
        return f"{t:%H:%M}"
    return f"{t.day} {AY[t.month - 1]} {t:%H:%M}"


def _plain(title) -> str:
    """Tablo hücresi için ad: NFC'ye çevrilir; emoji, birleşen işaretler ve görünmez/denetim karakterleri çıkar (eş genişlikli
    yazıda sütunları kaydırırlar), boşluklar teke iner."""
    import unicodedata as u
    t = u.normalize("NFC", str(title or ""))
    t = "".join(c for c in t if (ord(c) < 0x2000 or 0x2010 <= ord(c) <= 0x2027) and not u.combining(c)
                and u.category(c) not in ("Cf", "Cc", "Cs", "Co"))
    return " ".join(t.split())


def _cut(t: str, w: int) -> str:
    return t if len(t) <= w else t[:max(1, w - 1)].rstrip() + "…"


def _k(x: int) -> str:
    """Kısa sayı (tablo W'ye sığmazsa), en çok 5 karakter: 9.999 / 12B / 124B / 1,2Mn / 12Mn / 999Mn."""
    a, sign = abs(x), "-" if x < 0 else ""
    if a < 10_000:
        return sign + _n(a)
    for div, unit in ((1_000_000, "Mn"), (1_000, "B")):
        if a >= div * 0.9995:  # 999.999 -> 1Mn (1000B değil)
            v = a / div
            txt = f"{v:.1f}".replace(".", ",") if v < 9.95 else f"{v:.0f}"
            return sign + txt.removesuffix(",0") + unit
    return sign + _n(a)


def _fmt(v, short: bool, signed: bool = False) -> str:
    """Hücre: sayıysa biçimlenir (signed: +/− işaretli), değilse olduğu gibi."""
    if not isinstance(v, int) or isinstance(v, bool):
        return str(v)
    txt = _k(v) if short else _n(abs(v) if signed else v)
    if signed:
        txt = txt.lstrip("-")
        return ("+" if v > 0 else "−" if v < 0 else "") + txt
    return txt


def _table(head: list[str], rows: list[list], title: bool = False, signed: bool = False, label_w: int = 0) -> str:
    """İlk sütun sola, diğerleri sağa yaslı eş genişlikli tablo; satırlar en çok W karakter. Sığmazsa sayılar kısaltılır
    (12,3B), title=True ise ilk sütun (video adı) daraltılıp '…' ile kesilir."""
    import html
    for short in (False, True):
        cells = [list(head)] + [[r[0]] + [_fmt(c, short, signed) for c in r[1:]] for r in rows]
        ws = [max(len(c) for c in col) for col in zip(*cells)]
        ws[0] = max(ws[0], label_w)  # platform tabloları alt alta aynı hizada dursun
        rest = sum(w + 1 for w in ws[1:])
        if title:
            ws[0] = max(6, min(ws[0], W - rest))
        if ws[0] + rest <= W:
            break
    out = [" ".join([_cut(r[0], ws[0]).ljust(ws[0])] + [c.rjust(w) for c, w in zip(r[1:], ws[1:])]).rstrip()
           for r in cells]
    return "<pre>" + html.escape("\n".join(out), quote=False) + "</pre>"


def render(snap: dict, prev: dict | None) -> str:
    """Telegram raporu (HTML): platform tablosu (satırlar ölçü, sütunlar platform), toplam, platform platform son
    rapordan beri değişim, en çok izlenen videolar tablosu ve TikTok tablosu."""
    import html
    prev = prev or {"platforms": {}}
    plats = snap.get("platforms") or {}
    lines = [f"📊 <b>Bilgi Makası raporu</b> · {_when(snap.get('time', ''))}"]
    ok = [n for n in ("youtube", "instagram", "tiktok") if isinstance(plats.get(n), dict) and "error" not in plats[n]]
    notes = [f"⚠️ {NAMES[n]}: {html.escape(str(plats[n]['error']))}" for n in ("youtube", "instagram", "tiktok")
             if isinstance(plats.get(n), dict) and "error" in plats[n]]
    notes += [f"ℹ️ {NAMES[n]}: {html.escape(str(plats[n]['note']))}" for n in ok if plats[n].get("note")]
    acc = {n: plats[n].get("account") or {} for n in ok}

    def num(d, k):
        v = d.get(k)
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    body = [[label] + [num(acc[n], k) if num(acc[n], k) is not None else "–" for n in ok]
            for k, label in ROWS if any(num(acc[n], k) is not None for n in ok)]
    if body:
        lines += ["", _table([""] + [COL[n] for n in ok], body, label_w=max(len(label) for _, label in ROWS))]
        if len(ok) > 1:
            tot = [f"{_n(sum(num(acc[n], k) or 0 for n in ok))} {WORD[k]}"
                   for k in ("followers", "views", "likes") if any(num(acc[n], k) is not None for n in ok)]
            lines.append("<b>Toplam:</b> " + ", ".join(tot))
    # son rapordan beri, platform platform: yalnız iki ölçümde de okunabilen değerler karşılaştırılır
    pp = prev.get("platforms") or {}
    if pp and ok:
        pacc = {n: ((pp.get(n) or {}).get("account") or {}) if isinstance(pp.get(n), dict) and "error" not in pp[n]
                else {} for n in ok}
        diff = {(n, k): num(acc[n], k) - num(pacc[n], k) for n in ok for k, _ in ROWS
                if num(acc[n], k) is not None and num(pacc[n], k) is not None}
        since = _when(prev.get("time", ""), snap.get("time")) if prev.get("time") else ""
        head = f"<b>Son rapordan{f' ({since})' if since else ''} beri</b>"
        rows = [[label] + [diff.get((n, k), "–") for n in ok] for k, label in ROWS
                if any(diff.get((n, k)) for n in ok)]
        if rows:
            views = sum(v for (n, k), v in diff.items() if k == "views")
            lines += ["", head + (f" (toplam {'+' if views > 0 else '−' if views < 0 else ''}{_n(abs(views))} izlenme)"
                                  if any(k == "views" for _, k in diff) else ""),
                      _table([""] + [COL[n] for n in ok], rows, signed=True, label_w=max(len(label) for _, label in ROWS))]
        elif diff:
            lines.append(head + ": değişiklik yok")
    # video bazlı: YouTube ve Instagram aynı videoyu kayıttan eşleştirir; TikTok listesi ayrı (taslaktan elle paylaşıldı)
    rows = []
    for tag, title in (snap.get("titles") or {}).items():
        yt = ((plats.get("youtube") or {}).get("videos") or {}).get(tag)
        ig = ((plats.get("instagram") or {}).get("videos") or {}).get(tag)
        if not (yt or ig):
            continue
        views = _int((yt or {}).get("views")) + _int((ig or {}).get("views"))
        likes = _int((yt or {}).get("likes")) + _int((ig or {}).get("likes"))
        rows.append((views, [_plain(title) or tag, _int(yt["views"]) if yt and "views" in yt else "–",
                             _int(ig["views"]) if ig and "views" in ig else "–", likes]))
    if rows:
        top = [r for _, r in sorted(rows, key=lambda x: -x[0])[:10]]
        lines += ["", "<b>Videolar</b> (izlenme; beğeni iki platformun toplamı)",
                  _table(["Video", "YT", "Insta", "Beğeni"], top, title=True)]
    tt = ((plats.get("tiktok") or {}).get("list") or []) if "tiktok" in ok else []
    if tt:
        top = [[_plain(v.get("title")) or "(adsız)", _int(v.get("views")), _int(v.get("likes"))]
               for v in sorted(tt, key=lambda v: -_int(v.get("views")))[:5]]
        lines += ["", _table(["TikTok", "İzlenme", "Beğeni"], top, title=True)]
    if notes:
        lines += [""] + notes
    lines += ["", "Grafikler ve ayrıntı: /panel"]
    return "\n".join(lines)


def plain(text: str) -> str:
    """HTML raporun düz yazı hâli (etiketler çıkar, &amp; gibi kaçışlar geri döner)."""
    import html
    import re
    return html.unescape(re.sub(r"</?(b|pre)>", "", text))


def report(send: bool = True) -> str:
    try:
        prev = json.loads(SNAP.read_text())
    except Exception:  # noqa: BLE001
        prev = None
    snap = collect()
    text = render(snap, prev)
    if send:
        from .telegram_bot import api
        chat = os.environ["TELEGRAM_CHAT_ID"]
        try:
            api("sendMessage", data={"chat_id": chat, "text": text, "parse_mode": "HTML"})
        except RuntimeError as e:  # biçim reddedilirse rapor kaybolmasın: aynı metin düz yazı olarak gider
            print("Biçimli rapor gönderilemedi, düz metin deneniyor:", P._redact(e)[:200])
            api("sendMessage", data={"chat_id": chat, "text": plain(text)})
        SNAP.parent.mkdir(exist_ok=True)
        SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
        with HIST.open("a", encoding="utf-8") as f:  # panel grafikleri için kısa geçmiş (state_sync satır birleştirir)
            f.write(json.dumps(history_line(snap), ensure_ascii=False, separators=(",", ":")) + "\n")
    return text


def history_line(snap: dict, days: int = 7) -> dict:
    """Bir ölçümün kısa özeti: platform hesap toplamları + son `days` günün videolarının [izlenme, beğeni] değerleri.
    Hata veren platform yazılmaz (grafikte boşluk olur, sıfır görünmez)."""
    since = (dt.datetime.now(TR) - dt.timedelta(days=days)).strftime("%Y%m%d")
    acc, vids = {}, {}
    for name, d in (snap.get("platforms") or {}).items():
        if not isinstance(d, dict) or "error" in d:
            continue
        acc[name] = {k: v for k, v in (d.get("account") or {}).items() if isinstance(v, int)}
        for tag, v in (d.get("videos") or {}).items():
            if (tag.split("-") + ["", ""])[1] >= since:  # short-YYYYMMDD-HHMM(SS)
                vids.setdefault(tag, {})[name] = [_int(v.get("views")), _int(v.get("likes"))]
    return {"time": snap.get("time"), "hesap": acc, "video": vids}


if __name__ == "__main__":
    from .pipeline import load_env
    load_env(ROOT / ".env")
    out = report(send=sys.argv[1:2] == ["report"])
    print(out if sys.argv[1:2] == ["report"] else plain(out))
