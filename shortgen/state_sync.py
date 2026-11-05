"""Durum dosyalarını (state/, history.jsonl) çakışmasız kaydeder.

Üretim ve onay oturumu aynı anda çalışabildiği için ikisi de state/videos.json'a yazabilir.
Bu komut uzak dalı alır, dosyaları içerik düzeyinde birleştirir ve yalnız durum dosyalarını iter:

    python -m shortgen.state_sync "commit mesajı"
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATHS = ["state", "history.jsonl"]


def _git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check).stdout


def _show(rev: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _keep_published(local: dict, remote: dict) -> dict:
    """Yerel kayıt kazansa bile uzakta paylaşılmış (ok) platformlar kaybolmaz: aynı video bir platforma iki kez
    yüklenmesin (ör. düzeltme işi paylaşım sürerken eski kaydı yeniden yazarsa)."""
    rp, lp = remote.get("platforms") or {}, local.get("platforms") or {}
    keep = [p for p, r in rp.items() if (r or {}).get("status") == "ok" and (lp.get(p) or {}).get("status") != "ok"]
    if not keep:
        return local
    out = {**local, "platforms": {**lp, **{p: rp[p] for p in keep}}}
    rs, ls = remote.get("schedule"), local.get("schedule")
    if isinstance(rs, dict) and isinstance(ls, dict):
        out["schedule"] = {**ls, **{p: rs[p] for p in keep if p in rs}}
    # saat planı yoksa (tekrar dene, sabit saatli onay) paylaşım işi ok olmayan her platformu bekleyen sayar
    sched = out.get("schedule") or dict.fromkeys(("youtube", "instagram", "tiktok"))
    pending = [p for p in sched if (out["platforms"].get(p) or {}).get("status") != "ok"]
    if out.get("status") in ("zamanlandi", "onay_bekliyor") and not pending \
            and remote.get("status") in ("yayinlandi", "kismen", "hata"):
        out["status"] = remote["status"]  # uzakta paylaşım bitmiş, yerelde bekleyen platform kalmadı
        if remote.get("published"):
            out["published"] = remote["published"]
    return out


def _decision(v: dict) -> dict:
    """Kaydın paylaşım kararıyla ilgili kısmı: panel metin düzenlemesi (başlık/açıklama) bir paylaşım kararı değildir."""
    return {k: x for k, x in v.items() if k not in ("duzenleme", "title")}


def _keep_edit(local: dict, remote: dict, base: dict | None) -> dict:
    """Panelde yapılan başlık/açıklama düzenlemesi (duzenleme), bu çalışma onu değiştirmediyse kaybolmaz
    (ör. paylaşım işi düzenleme sürerken kaydını yeniden yazarsa kalan platformlar yine düzenlenmiş metni kullanır)."""
    base = base or {}
    if remote.get("duzenleme") == base.get("duzenleme") or local.get("duzenleme") != base.get("duzenleme"):
        return local
    out = {**local, "duzenleme": remote.get("duzenleme")}
    if local.get("title") == base.get("title") and "title" in remote:
        out["title"] = remote["title"]
    return out


def _merge(path: str, base: str | None, remote: str | None, local: str | None) -> str | None:
    if local == base:  # bu çalışmada değişmedi: uzaktakini al
        return remote
    if remote is None or remote == base:
        return local
    if local is None:
        return remote
    if path.endswith("videos.json"):
        r, l = json.loads(remote), json.loads(local)
        b = {v["tag"]: v for v in json.loads(base)} if base else {}
        out = {v["tag"]: v for v in r}
        for v in l:  # bu çalışmada değişen kayıtlar kazanır (uzakta paylaşılmış platformlar korunarak)
            if v["tag"] not in out:
                out[v["tag"]] = v
            elif v != b.get(v["tag"]):
                rv, bv = out[v["tag"]], b.get(v["tag"]) or {}
                # platforms alanını yalnız paylaşım işi yazar. Uzak kayıt değişmiş ama platforms'u aynıysa bu bir
                # kullanıcı kararıdır (iptal, ret, yeniden onay, tekrar dene, düzeltme). Bu çalışma paylaşım yaptıysa
                # kullanıcının kararı geçerli olur, bu çalışmada yapılmış paylaşımlar (ok) yine korunur.
                # Panel düzenlemesi (duzenleme/başlık) hangi taraf kazanırsa kazansın kaybolmaz (_keep_edit).
                if _decision(rv) != _decision(bv) and rv.get("platforms") == bv.get("platforms") \
                        and v.get("platforms") != bv.get("platforms"):
                    out[v["tag"]] = _keep_published(_keep_edit(rv, v, bv), v)
                else:
                    out[v["tag"]] = _keep_published(_keep_edit(v, rv, bv), rv)
        order = [v["tag"] for v in r] + [v["tag"] for v in l if v["tag"] not in {x["tag"] for x in r}]
        return json.dumps([out[t] for t in order], ensure_ascii=False, indent=2)
    if path.endswith("yorumlar.json"):
        r, l = json.loads(remote), json.loads(local)
        b = json.loads(base) if base else {"seen": [], "pending": {}}
        seen = list(dict.fromkeys(r.get("seen", []) + l.get("seen", [])))
        pend = {**r.get("pending", {}), **l.get("pending", {})}
        for k in b.get("pending", {}):  # iki taraftan birinde işlenip silinen taslak silinmiş kalır
            if k not in r.get("pending", {}) or k not in l.get("pending", {}):
                pend.pop(k, None)
        return json.dumps({"seen": seen, "pending": pend}, ensure_ascii=False, indent=1)
    if path.endswith("konu_sirasi.json"):  # üretim ilk konuyu alırken panelden sıra değişmiş olabilir
        from .konu_sirasi import merge
        return merge(base, remote, local)
    if path.endswith("telegram_offset.json"):
        return local if json.loads(local).get("offset", 0) >= json.loads(remote).get("offset", 0) else remote
    if path.endswith(".jsonl"):
        seen, lines = set(), []
        for ln in remote.splitlines() + local.splitlines():
            if ln.strip() and ln not in seen:
                seen.add(ln)
                lines.append(ln)
        return "\n".join(lines) + "\n"
    return local


def _tracked(rev: str) -> set[str]:
    out = set()
    for p in PATHS:
        out |= set(_git("ls-tree", "-r", "--name-only", rev, "--", p, check=False).split())
    return out


def sync(message: str) -> None:
    # Bu çalışmanın değişikliklerini BİR KEZ yakala: itme reddedilip tekrar denenirse taban ve yerel içerik
    # değişmemeli (yoksa ikinci denemede yerel == taban görünür ve değişiklikler sessizce kaybolur).
    base_rev = _git("rev-parse", "HEAD").strip()
    snap: dict[str, str | None] = {}
    files = _tracked(base_rev)
    for p in PATHS:
        for f in (ROOT / p).rglob("*") if (ROOT / p).is_dir() else [ROOT / p]:
            if f.is_file():
                files.add(str(f.relative_to(ROOT)))
    for f in files:
        lp = ROOT / f
        snap[f] = lp.read_text(encoding="utf-8") if lp.exists() else None
    for attempt in range(6):
        _git("fetch", "-q", "origin", "main")
        merged = {}
        for f in sorted(files | _tracked("origin/main")):
            merged[f] = _merge(f, _show(base_rev, f), _show("origin/main", f), snap.get(f))
        _git("reset", "-q", "--mixed", "origin/main")
        for f, content in merged.items():
            lp = ROOT / f
            if content is None:
                lp.unlink(missing_ok=True)
            else:
                lp.parent.mkdir(parents=True, exist_ok=True)
                lp.write_text(content, encoding="utf-8")
        _git("add", "-A", "--", *PATHS)
        if not _git("diff", "--cached", "--name-only"):
            print("Kaydedilecek değişiklik yok.")
            return
        _git("commit", "-q", "-m", message)
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT).returncode == 0:
            print("Durum kaydedildi.")
            return
        time.sleep(3 * (attempt + 1))
    raise SystemExit("Durum kaydedilemedi")


def refresh() -> None:
    """Yerel durumu uzak depodaki en güncel hâline getirir. Önce sync() çağrılmış olmalı (yerel değişiklik kalmamalı)."""
    _git("fetch", "-q", "origin", "main")
    _git("reset", "-q", "--hard", "origin/main")


if __name__ == "__main__":
    sync(sys.argv[1] if len(sys.argv) > 1 else "Durum güncellendi")
