"""Onaylanan videoyu YouTube Shorts, Instagram Reels ve TikTok'a yükler.

Kullanım:
    python -m shortgen.publish <etiket>          # GitHub Release'teki videoyu indirip tüm bağlı platformlara yükler
    python -m shortgen.publish check youtube     # bağlantıyı dener, yükleme yapmaz (youtube/instagram/tiktok)

Her platform yalnızca anahtarları tanımlıysa denenir; tanımlı olmayan platform atlanır.
Gerekli GitHub Secrets (kurulum: docs/PAYLASIM_KURULUM.md):
    YouTube:   YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
    Instagram: IG_USER_ID, IG_ACCESS_TOKEN
    TikTok:    TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
İsteğe bağlı: GH_SECRETS_PAT (Instagram ve TikTok anahtarlarını süresi dolmadan kendiliğinden yeniler).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent


class Skip(Exception):
    """Platform bağlı değil."""


def _env(*names: str) -> list[str]:
    vals = [os.environ.get(n, "").strip() for n in names]
    if not all(vals):
        raise Skip("anahtarlar tanımlı değil")
    return vals


def _rotate_secret(name: str, value: str) -> bool:
    """Yenilenen anahtarı GitHub Secrets'a geri yazar (GH_SECRETS_PAT varsa). Değer hiçbir yere yazdırılmaz."""
    pat, repo = os.environ.get("GH_SECRETS_PAT"), os.environ.get("GITHUB_REPOSITORY")
    if not (pat and repo and value):
        return False
    r = subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value, text=True, check=False,
                       env={**os.environ, "GH_TOKEN": pat}, capture_output=True)
    if r.returncode:
        print(f"{name} GitHub'a kaydedilemedi: {r.stderr.strip()[:200]}")
    return r.returncode == 0


def _hashtags(meta: dict, limit: int) -> list[str]:
    tags = ["#" + re.sub(r"\s+", "", h.lstrip("#")) for h in meta.get("hashtags", [])]
    return [t for t in tags if len(t) > 1][:limit]


# ------------------------------------------------------------------ YouTube
def _yt_token() -> str:
    cid, secret, refresh = _env("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": secret, "refresh_token": refresh, "grant_type": "refresh_token"},
        timeout=30)
    if not r.ok:
        raise RuntimeError(f"YouTube oturumu yenilenemedi: {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def youtube(video: Path, meta: dict) -> dict:
    token = _yt_token()
    title = meta["title"].replace("<", "").replace(">", "")
    if "#shorts" not in title.lower() and len(title) <= 92:
        title += " #Shorts"
    desc = meta["description"].replace("<", "").replace(">", "")[:4900]
    body = {
        "snippet": {"title": title[:100], "description": desc, "categoryId": "27",  # Eğitim
                    "tags": [h.lstrip("#") for h in meta.get("hashtags", [])][:15],
                    "defaultLanguage": "tr", "defaultAudioLanguage": "tr"},
        "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"), "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(meta.get("ai_voice"))},
    }
    size = video.stat().st_size
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        data=json.dumps(body), timeout=60)
    if not init.ok:
        raise RuntimeError(f"YouTube yükleme başlatılamadı: {init.status_code} {init.text[:400]}")
    with video.open("rb") as f:
        up = requests.put(init.headers["Location"], data=f,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4",
                                   "Content-Length": str(size)}, timeout=900)
    if not up.ok:
        raise RuntimeError(f"YouTube yükleme hatası: {up.status_code} {up.text[:400]}")
    vid = up.json()["id"]
    status = up.json().get("status", {}).get("privacyStatus", "")
    res = {"id": vid, "url": f"https://youtube.com/shorts/{vid}"}
    if status and status != body["status"]["privacyStatus"]:
        # Google denetiminden geçmemiş uygulamaların videoları zorla "private" olur
        res["note"] = f"YouTube videoyu '{status}' yaptı (uygulama denetimi bekleniyor olabilir)"
    return res


# ------------------------------------------------------------------ Instagram (Instagram ile giriş API'si)
IG_GRAPH = "https://graph.instagram.com"
IG_VER = os.environ.get("IG_API_VERSION", "v23.0")


def _ig_base(token: str) -> str:
    """Instagram girişli anahtar (IG...) graph.instagram.com, Birleşik/Facebook girişli (EAA...) graph.facebook.com kullanır."""
    return "https://graph.facebook.com" if token.startswith("EAA") else IG_GRAPH


def instagram(video: Path, meta: dict) -> dict:
    (token,) = _env("IG_ACCESS_TOKEN")
    user = os.environ.get("IG_USER_ID", "").strip() or "me"  # numara verilmezse anahtarın sahibi kullanılır
    G = _ig_base(token)
    if G == IG_GRAPH:
        # 60 günlük anahtarı her paylaşımda tazele (24 saatten eski olmalı; olmazsa sorun değil)
        rr = requests.get(f"{IG_GRAPH}/refresh_access_token",
                          params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
        if rr.ok and rr.json().get("access_token"):
            token = rr.json()["access_token"]
            _rotate_secret("IG_ACCESS_TOKEN", token)

    caption = meta["title"] + "\n\n" + meta["description"]
    tags = _hashtags(meta, 30)
    caption = re.sub(r"(#\w+\s*)+$", "", caption).strip()  # açıklamanın sonundaki etiketleri tekrar etme
    caption = (caption[:2150 - len(" ".join(tags))] + "\n\n" + " ".join(tags)).strip()

    c = requests.post(f"{G}/{IG_VER}/{user}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true",
        "access_token": token}, timeout=60)
    if not c.ok:
        raise RuntimeError(f"Instagram kapsayıcı oluşturulamadı: {c.status_code} {c.text[:400]}")
    cid = c.json()["id"]
    size = video.stat().st_size
    up_url = c.json().get("uri") or f"https://rupload.facebook.com/ig-api-upload/{IG_VER}/{cid}"
    with video.open("rb") as f:
        up = requests.post(up_url, data=f,
                           headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                           timeout=900)
    if not up.ok:
        raise RuntimeError(f"Instagram yükleme hatası: {up.status_code} {up.text[:400]}")
    for _ in range(60):  # işlenmesini bekle (en fazla ~10 dk)
        s = requests.get(f"{G}/{IG_VER}/{cid}", params={"fields": "status_code,status",
                                                               "access_token": token}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram videoyu işleyemedi: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram işleme zaman aşımı")
    p = requests.post(f"{G}/{IG_VER}/{user}/media_publish",
                      data={"creation_id": cid, "access_token": token}, timeout=60)
    if not p.ok:
        raise RuntimeError(f"Instagram yayınlama hatası: {p.status_code} {p.text[:400]}")
    mid = p.json()["id"]
    link = requests.get(f"{G}/{IG_VER}/{mid}", params={"fields": "permalink", "access_token": token},
                        timeout=30).json().get("permalink", "")
    return {"id": mid, "url": link}


# ------------------------------------------------------------------ TikTok (Content Posting API, doğrudan paylaşım)
TT = "https://open.tiktokapis.com/v2"
TT_REDIRECT = os.environ.get("TIKTOK_REDIRECT_URI", "https://sabriemin.github.io/tiktok/")


def _tt_token() -> str:
    key, secret, refresh = _env("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
    r = requests.post(f"{TT}/oauth/token/", data={
        "client_key": key, "client_secret": secret, "grant_type": "refresh_token", "refresh_token": refresh},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    d = r.json()
    if not r.ok or "access_token" not in d:
        raise RuntimeError(f"TikTok oturumu yenilenemedi: {r.status_code} {str(d)[:300]}")
    if d.get("refresh_token") and d["refresh_token"] != refresh:
        _rotate_secret("TIKTOK_REFRESH_TOKEN", d["refresh_token"])
    return d["access_token"]


def tiktok(video: Path, meta: dict) -> dict:
    token = _tt_token()
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    info = requests.post(f"{TT}/post/publish/creator_info/query/", headers=h, timeout=30).json()
    opts = info.get("data", {}).get("privacy_level_options", [])
    want = os.environ.get("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE")
    privacy = want if want in opts else ("SELF_ONLY" if "SELF_ONLY" in opts else (opts or ["SELF_ONLY"])[0])
    title = (meta["title"] + " " + " ".join(_hashtags(meta, 8)))[:2200]
    size = video.stat().st_size
    if size <= 64 * 1024 * 1024:
        chunk, count = size, 1
    else:
        chunk = 10 * 1024 * 1024
        count = size // chunk
    def _init(priv: str):
        return requests.post(f"{TT}/post/publish/video/init/", headers=h, json={
            "post_info": {"title": title, "privacy_level": priv, "disable_comment": False, "disable_duet": False,
                          "disable_stitch": False, "is_aigc": bool(meta.get("ai_voice"))},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                            "total_chunk_count": count}}, timeout=60)
    init = _init(privacy)
    d = init.json()
    draft = False
    # incelemeden geçmemiş uygulamalar doğrudan paylaşamaz: videoyu TikTok gelen kutusuna taslak olarak gönder
    if "unaudited" in str(d.get("error", {}).get("code", "")):
        draft = True
        init = requests.post(f"{TT}/post/publish/inbox/video/init/", headers=h, json={
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                            "total_chunk_count": count}}, timeout=60)
        d = init.json()
    if not init.ok or d.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok yükleme başlatılamadı: {init.status_code} {str(d)[:400]}")
    pid, url = d["data"]["publish_id"], d["data"]["upload_url"]
    with video.open("rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1  # son parça kalanı da alır
            part = f.read(end - start + 1)
            u = requests.put(url, data=part, timeout=900, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            if u.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok parça yükleme hatası: {u.status_code} {u.text[:300]}")
    draft_note = ("Uygulama TikTok incelemesinden geçene kadar video taslak olarak gönderilir: "
                  "TikTok'taki bildirime dokunup açıklamayı yapıştır ve Paylaş de")
    for _ in range(60):
        s = requests.post(f"{TT}/post/publish/status/fetch/", headers=h, json={"publish_id": pid},
                          timeout=30).json().get("data", {})
        st = s.get("status")
        if draft and st == "SEND_TO_USER_INBOX":
            return {"id": pid, "draft": True, "note": draft_note}
        if st == "PUBLISH_COMPLETE":
            ids = s.get("publicaly_available_post_id") or s.get("publicly_available_post_id") or []
            res = {"id": str(ids[0]) if ids else pid, "privacy": privacy}
            if ids:
                res["url"] = f"https://www.tiktok.com/@{os.environ.get('TIKTOK_HANDLE', 'bilgimakasi')}/video/{ids[0]}"
            if privacy == "SELF_ONLY":
                res["note"] = "Video 'yalnızca ben' olarak paylaşıldı"
            return res
        if st == "FAILED":
            raise RuntimeError(f"TikTok paylaşımı başarısız: {s.get('fail_reason')}")
        time.sleep(10)
    return {"id": pid, "note": draft_note if draft else "TikTok hâlâ işliyor, birkaç dakika içinde profilde görünür"}


PLATFORMS = {"youtube": youtube, "instagram": instagram, "tiktok": tiktok}


def publish(video: Path, meta: dict, only: list[str] | None = None) -> dict:
    """Her platformu ayrı dener; birinin hatası diğerlerini durdurmaz."""
    out = {}
    for name, fn in PLATFORMS.items():
        if only and name not in only:
            continue
        try:
            out[name] = {"status": "ok", **fn(video, meta)}
        except Skip as e:
            out[name] = {"status": "atlandi", "note": str(e)}
        except Exception as e:  # noqa: BLE001
            out[name] = {"status": "hata", "error": str(e)[:600]}
        print(name, json.dumps(out[name], ensure_ascii=False))
    return out


def fetch_release(tag: str, dest: Path) -> tuple[Path, dict]:
    subprocess.run(["gh", "release", "download", tag, "--pattern", "video.mp4", "--pattern", "metadata.json",
                    "--dir", str(dest), "--clobber"], check=True)
    return dest / "video.mp4", json.loads((dest / "metadata.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    env = ROOT / ".env"  # yerel çalıştırma için (Actions'ta anahtarlar ortam değişkeninden gelir)
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
    if sys.argv[1] == "tiktok-login-url":
        from urllib.parse import urlencode
        url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
            "client_key": os.environ["TIKTOK_CLIENT_KEY"].strip(), "response_type": "code",
            "scope": "user.info.basic,video.publish,video.upload",
            "redirect_uri": TT_REDIRECT, "state": "bilgimakasi"})
        # Actions günlükleri secret değerlerini maskelediği için link Telegram'dan gönderilir
        r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage", data={
            "chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "text": "TikTok bağlantısı: aşağıdaki linke tıkla, @bilgimakasi ile giriş yapıp izin ver. "
                    "Açılan sayfadaki kodu GitHub Secrets'a TIKTOK_AUTH_CODE adıyla ekle.\n\n" + url,
            "disable_web_page_preview": "true"}, timeout=30)
        print("Telegram:", r.status_code)
        sys.exit(0 if r.ok else 1)
    if sys.argv[1] == "tiktok-exchange":
        key, secret, code = _env("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_AUTH_CODE")
        if not os.environ.get("GH_SECRETS_PAT"):
            sys.exit("HATA: GH_SECRETS_PAT tanımlı değil; anahtar GitHub'a kaydedilemez")
        from urllib.parse import unquote
        r = requests.post(f"{TT}/oauth/token/", data={
            "client_key": key, "client_secret": secret, "code": unquote(code), "grant_type": "authorization_code",
            "redirect_uri": TT_REDIRECT}, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        d = r.json()
        if not r.ok or "refresh_token" not in d:
            sys.exit(f"HATA: TikTok kodu anahtara çevrilemedi: {r.status_code} "
                     f"{ {k: v for k, v in d.items() if 'token' not in k} }")
        if not _rotate_secret("TIKTOK_REFRESH_TOKEN", d["refresh_token"]):
            sys.exit("HATA: anahtar alındı ama GitHub'a kaydedilemedi (GH_SECRETS_PAT izinlerini kontrol et)")
        print("TikTok anahtarı kaydedildi. İzinler:", d.get("scope"))
        sys.exit(0)
    if sys.argv[1] == "ig-upload-test":
        # paylaşım yapmadan Instagram yüklemesini dener ve ayrıntıları yazar
        (token,) = _env("IG_ACCESS_TOKEN")
        user = os.environ.get("IG_USER_ID", "").strip() or "me"
        G = _ig_base(token)
        with tempfile.TemporaryDirectory() as d:
            v, m = fetch_release(sys.argv[2], Path(d))
            size = v.stat().st_size
            data = v.read_bytes()
            for ver, mode in (("v26.0", "bytes"), ("v26.0", "bytes-ct"), ("v23.0", "bytes")):
                c = requests.post(f"{G}/{ver}/{user}/media", data={
                    "media_type": "REELS", "upload_type": "resumable", "caption": "test",
                    "access_token": token}, timeout=60)
                print(f"[{ver} {mode}] kapsayıcı:", c.status_code, c.text[:200])
                if not c.ok:
                    continue
                cid = c.json()["id"]
                hdr = {"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}
                if mode == "bytes-ct":
                    hdr["Content-Type"] = "application/octet-stream"
                up = requests.post(c.json().get("uri") or f"https://rupload.facebook.com/ig-api-upload/{ver}/{cid}",
                                   data=data, headers=hdr, timeout=900)
                print(f"[{ver} {mode}] yükleme:", up.status_code, up.text[:300])
                time.sleep(10)
                st = requests.get(f"{G}/{ver}/{cid}", params={"fields": "status_code,status",
                                                               "access_token": token}, timeout=30)
                print(f"[{ver} {mode}] durum:", st.text[:300])
            pe = requests.get(f"{G}/v26.0/{user}", params={"fields": "username,account_type",
                                                          "access_token": token}, timeout=30)
            print("hesap:", pe.text[:300])
        sys.exit(0)
    if sys.argv[1] == "check":
        name = sys.argv[2]
        try:
            for n in {"youtube": ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"],
                      "instagram": ["IG_ACCESS_TOKEN"],
                      "tiktok": ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"]}[name]:
                if not os.environ.get(n):
                    raise Skip(f"{n} GitHub Secrets'ta tanımlı değil")
        except Skip as e:
            sys.exit(f"HATA: {e}")
        if name == "youtube":
            cid, sec, ref = (os.environ[k].strip() for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))
            # sırları göstermeden biçim kontrolü
            print(f"Client ID: {cid[:16]}... ({len(cid)} karakter, doğru bitiş: {cid.endswith('.apps.googleusercontent.com')})")
            print(f"Client secret: {sec[:7]}... ({len(sec)} karakter)")
            print(f"Refresh token: {ref[:4]}... ({len(ref)} karakter)")
            tok = _yt_token()
            ch = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"},
                              headers={"Authorization": f"Bearer {tok}"}, timeout=30)
            # youtube.upload kapsamı kanal okumaya izin vermeyebilir; oturumun yenilenmesi yeterli kanıt
            title = ch.json().get("items", [{}])[0].get("snippet", {}).get("title") if ch.ok else None
            print("YouTube bağlantısı çalışıyor." + (f" Kanal: {title}" if title else ""))
        elif name == "instagram":
            (token,) = _env("IG_ACCESS_TOKEN")
            user = os.environ.get("IG_USER_ID", "").strip() or "me"
            G = _ig_base(token)
            print("Kullanılan adres:", G)
            r = requests.get(f"{G}/{IG_VER}/{user}", params={"fields": "id,username", "access_token": token}, timeout=30)
            if not r.ok:
                sys.exit(f"HATA: Instagram {r.status_code}: {r.text[:400]}")
            me = r.json()
            if not me.get("username"):
                sys.exit(f"HATA: hesap bilgisi gelmedi: {str(me)[:300]}")
            print("Instagram bağlantısı çalışıyor:", me.get("username"), me.get("id"))
            if G != IG_GRAPH:
                d = requests.get(f"{G}/{IG_VER}/debug_token", params={"input_token": token, "access_token": token},
                                 timeout=30)
                if d.ok:
                    dd = d.json().get("data", {})
                    exp = dd.get("expires_at")
                    print("Anahtar süresi:", "süresiz" if not exp else time.strftime("%Y-%m-%d", time.gmtime(exp)),
                          "| izinler:", ", ".join(dd.get("scopes", [])))
        elif name == "tiktok":
            h = {"Authorization": f"Bearer {_tt_token()}"}
            r = requests.post(f"{TT}/post/publish/creator_info/query/", headers=h, timeout=30)
            print("TikTok:", r.status_code, r.json().get("data", {}).get("creator_username"),
                  r.json().get("data", {}).get("privacy_level_options"))
    else:
        with tempfile.TemporaryDirectory() as d:
            v, m = fetch_release(sys.argv[1], Path(d))
            print(json.dumps(publish(v, m), ensure_ascii=False))
