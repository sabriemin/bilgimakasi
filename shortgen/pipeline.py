"""Uçtan uca: senaryo -> görsel -> ses -> kurgu -> yayın paketi."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path

from . import illustrate, images, render, voice
from .script import STRUCTURES, ShortScript, generate_script, load_script

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def slugify(s: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"[^a-z0-9]+", "-", s.translate(tr).lower()).strip("-")[:50]


def template_catalog() -> dict[str, str]:
    out = {}
    for f in sorted((ROOT / "templates").glob("*.json")):
        if f.stem != "eslesme":
            out[f.stem] = json.loads(f.read_text(encoding="utf-8")).get("description", "")
    return out


def kart_uygun(script: ShortScript, kart: dict) -> bool:
    """Kart şablonu yalnız eslesme.json'da açıksa ve yapı ya da kategori listedeyse seçilir. Tarih kategorilerinin
    hikâye anlatımları her zaman kolaj şablonunda kalır."""
    cat = script.category.strip().lower()
    if not kart.get("acik") or (cat in ("tarih", "az bilinen insan hikâyeleri") and script.structure == "hikaye"):
        return False
    return script.structure in kart.get("yapilar", []) or cat in kart.get("kategoriler", [])


def pick_template(script: ShortScript, override: str | None = None) -> str:
    cat = template_catalog()
    if override:
        if override not in cat:
            raise SystemExit(f"Şablon yok: {override}. Mevcut: {', '.join(cat)}")
        return override
    m = json.loads((ROOT / "templates" / "eslesme.json").read_text(encoding="utf-8"))
    kart = m.get("kart") or {}
    if "kart" in cat and kart_uygun(script, kart):
        return "kart"
    if m.get("claude_secsin") and script.template in cat and script.template != "kart":
        return script.template  # kart yalnız kart_uygun ile seçilir (yapı/kategori kuralları)
    t = m.get("kategoriler", {}).get(script.category.strip().lower(), m.get("varsayilan", "kolaj"))
    return t if t in cat else "kolaj"


def series_label(script: ShortScript, history: Path) -> str:
    """İlk sahnenin üstündeki format etiketi: 'EFSANE Mİ, GERÇEK Mİ? #4'. Tanıdık format izleyiciye takip sebebi verir."""
    if script.series_part == 2:
        return "2. BÖLÜM"
    try:
        vids = json.loads((ROOT / "state" / "videos.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        vids = []
    rejected = {v.get("topic") for v in vids if v.get("status") == "reddedildi"}
    seen = {script.topic}  # aynı konunun yeniden üretimi iki kez sayılmaz
    if history.exists():
        for line in history.read_text(encoding="utf-8").splitlines():
            try:
                h = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(h, dict):
                continue
            if h.get("structure") == script.structure and h.get("series_part") != 2 and h.get("topic") not in rejected:
                seen.add(h.get("topic"))
    return f"{STRUCTURES.get(script.structure, STRUCTURES['hikaye'])[0]} #{len(seen)}"


def build(script: ShortScript, out_dir: Path, use_voice: bool, music: Path | None,
          template: str = "kolaj", use_drawings: bool = True) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    cache = ROOT / "cache" / "images"
    cache.mkdir(parents=True, exist_ok=True)

    render.apply_template(template)  # çizim paleti şablon renklerinden gelsin
    # 1) fotoğraflar (birden çok sorgu, Wikimedia + Openverse, alaka kontrolü)
    credits, used = [], set()
    photos: dict[int, Path] = {}
    for i, sc in enumerate(script.scenes):
        queries = sc.image_queries or ([sc.image_query] if sc.image_query else [])
        if sc.image_mode == "none" or not queries:
            continue
        if queries[0].startswith("local:"):
            photos[i] = ROOT / queries[0][6:]
            continue
        found = images.find_any(queries, cache, used)
        if found:
            photos[i], cr = found
            used.update({"File:" + cr.title, cr.page})
            credits.append(cr)
        else:
            print(f"Sahne {i}: uygun fotoğraf bulunamadı ({queries})")

    # 2) çizimler: animasyonlu sahneler + fotoğrafı bulunamayan veya fotoğrafsız sahneler
    want: dict[int, str] = {}
    local: dict[int, Path] = {}
    for i, sc in enumerate(script.scenes):
        desc = sc.illustration.strip() or (sc.anim_query.strip() if sc.motion != "none" else "")
        if desc and (sc.motion != "none" or i not in photos):
            path = (ROOT / desc[6:]).resolve() if desc.startswith("local:") else None
            if path and path.is_relative_to(ROOT.resolve()) and path.is_file():
                local[i] = path  # deneme senaryoları: depodaki hazır çizim dosyası (Claude çağrısı yok)
            elif path:
                print(f"Sahne {i}: yerel çizim kullanılamadı (depo dışında ya da yok): {desc}")
            else:
                want[i] = desc
    drawings = illustrate.draw_scenes(want, script.topic, out_dir / "cizimler") if use_drawings else {}
    drawings.update(local)

    specs: list[render.SceneSpec] = []
    for i, sc in enumerate(script.scenes):
        img = photos.get(i)
        sprite = drawings.get(i)
        motion = sc.motion if sc.motion != "none" else "still"
        if sprite and img and sc.image_mode == "full" and sc.motion == "none":
            sprite = None  # tam ekran fotoğraf varken hareketsiz çizim üst üste binmesin
        specs.append(render.SceneSpec(
            narration=sc.narration, kicker=sc.kicker, headline=sc.headline,
            highlight_line=sc.highlight_line, strike=sc.strike, theme=sc.theme,
            image_mode=sc.image_mode if img else "none", image=img, icon=sc.icon if not sprite else "none",
            sprite=sprite, motion=motion if sprite else "none", trail=sc.trail, drawn=True))

    # 3) ses ve kelime zamanları
    text = " ".join(sc.narration.strip() for sc in script.scenes)
    mp3 = out_dir / "voice.mp3"
    if use_voice:
        words = voice.synthesize(text, mp3)
    else:
        words, mp3 = voice.estimate(text), None

    # 4) kelimeleri sahnelere dağıt
    counts = [len(sc.narration.split()) for sc in script.scenes]
    if sum(counts) != len(words):  # hizalama farklı bölündüyse oranla
        scale = len(words) / max(1, sum(counts))
        counts = [max(1, round(c * scale)) for c in counts]
        counts[-1] = max(1, len(words) - sum(counts[:-1]))
    i = 0
    for spec, c in zip(specs, counts):
        spec.words = words[i:i + c]
        spec.start = spec.words[0].start if spec.words else (words[i - 1].end if i else 0.0)
        i += c
    specs[0].start = 0.0
    for a, b in zip(specs, specs[1:]):
        b.start = max(b.start - 0.12, a.start + 0.5)  # görsel, sözden bir tık önce değişsin
        a.end = b.start

    # 5) kurgu
    video = out_dir / "video.mp4"
    if template == "kart":
        from . import kart
        for i, (spec, sc) in enumerate(zip(specs, script.scenes)):
            spec.card = {"type": sc.card, "value": sc.card_value, "label": sc.card_label, "myth": sc.card_myth,
                         "fact": sc.card_fact, "note": sc.card_note, "mascot": sc.mascot}
            spec.card["type"] = kart.card_type(spec, i, len(specs))
        kart.render_kart(specs, words, video, mp3, music, {"topic": script.topic, "structure": script.structure,
                                                           "title": script.title, "category": script.category})
    else:
        render.render(specs, words, video, mp3, music, template=template)

    # 6) yayın paketi
    desc = "\n\n".join(filter(None, [
        script.description,
        " ".join("#" + t for t in (re.sub(r"\W", "", h) for h in script.hashtags) if t),
        images.credits_text(credits),
    ]))
    meta = {
        "title": script.title, "description": desc, "hashtags": script.hashtags,
        "topic": script.topic, "category": script.category, "template": template,
        "credits": [images.credit_dict(c) for c in credits], "ai_voice": use_voice,
        "series_part": script.series_part, "structure": script.structure, "search_phrase": script.search_phrase,
        "status": "onay_bekliyor", "created": dt.datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return video


def main() -> None:
    ap = argparse.ArgumentParser(description="Short video üretici")
    ap.add_argument("--topic", help="İsteğe bağlı konu önerisi")
    ap.add_argument("--script", type=Path, help="Hazır script.json ile üret (Claude çağrısı yapılmaz)")
    ap.add_argument("--no-voice", action="store_true", help="ElevenLabs olmadan sessiz deneme")
    ap.add_argument("--music", type=Path, help="Telifsiz müzik dosyası (mp3)")
    ap.add_argument("--template", help="Şablonu elle seç (templates/ klasöründeki ad)")
    ap.add_argument("--out", type=Path, default=ROOT / "output")
    a = ap.parse_args()
    load_env(ROOT / ".env")

    history = ROOT / "history.jsonl"
    m = json.loads((ROOT / "templates" / "eslesme.json").read_text(encoding="utf-8"))
    pending = ROOT / "state" / "bekleyen_senaryo.json"
    seri_file = ROOT / "state" / "seri.json"
    seri = json.loads(seri_file.read_text(encoding="utf-8")) if seri_file.exists() else {}
    open_part = seri.get("bekleyen")
    # 2. bölüm, 1. bölümden en az 12 saat sonra gelen ilk konusuz üretimde çekilir
    part2_due = bool(open_part) and dt.datetime.now() >= dt.datetime.fromisoformat(open_part["created"]) + dt.timedelta(hours=12)
    if a.script:
        script = load_script(a.script)
    elif pending.exists() and not a.topic:
        # önceki çalışma ses/kurgu aşamasında düştüyse senaryoyu yeniden üretme (Claude bütçesi harcanmasın)
        print("Önceki çalışmadan kalan senaryo kullanılıyor.")
        script = load_script(pending)
    elif part2_due and not a.topic:
        print("Serinin 2. bölümü üretiliyor:", open_part["title"])
        script = generate_script(history, None, None, series_prev=open_part)
    else:
        from . import konu_sirasi
        queued = None if a.topic else konu_sirasi.peek()  # panelden sıraya konan konu gündemden önce gelir
        if queued:
            print("Konu sırasından alınan konu:", queued)
        topic = a.topic or queued
        if not topic and os.environ.get("AUTO_TREND", "1") != "0":
            try:  # konu verilmediyse gündemden en yüksek puanlı öneriyi seç
                from .trends import suggest
                s0 = suggest(3)[0]
                topic = f"{s0.topic} (kanca: {s0.hook}; gündem: {s0.trend})"
                print("Gündemden seçilen konu:", topic)
            except Exception as e:  # noqa: BLE001
                print("Gündem önerisi alınamadı, serbest konu seçilecek:", e)
        allow = os.environ.get("SERIES", "1") != "0" and not open_part
        catalog = {k: v for k, v in template_catalog().items() if k != "kart"}  # kart Claude'a önerilmez
        script = generate_script(history, topic, catalog if m.get("claude_secsin") else None, allow_series=allow)
        if queued and konu_sirasi.remove(queued):  # senaryo yazıldı: konu sıradan çıkar (state_sync kaydeder)
            print("Konu sırasından çıkarıldı:", queued)
    if script.scenes and os.environ.get("SERIES_LABEL", "1") != "0":
        script.scenes[0].kicker = series_label(script, history)
        print("Format etiketi:", script.scenes[0].kicker)
    if script.series_part == 2 and open_part and open_part.get("template") and not a.template:
        a.template = open_part["template"]
    template = pick_template(script, a.template)
    print(f"Şablon: {template}")
    music = a.music or (Path(os.environ["MUSIC_FILE"]) if os.environ.get("MUSIC_FILE") else None)
    out_dir = a.out / f"{dt.datetime.now():%Y-%m-%d_%H%M}_{slugify(script.topic)}"
    video = build(script, out_dir, use_voice=not a.no_voice, music=music, template=template)
    with history.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"date": str(dt.date.today()), "topic": script.topic, "dir": str(out_dir),
                            "structure": script.structure, "search_phrase": script.search_phrase,
                            "series_part": script.series_part},
                           ensure_ascii=False) + "\n")
    pending.unlink(missing_ok=True)
    if script.series_part == 1 and script.next_part_brief:
        seri["bekleyen"] = {"title": script.title, "topic": script.topic, "brief": script.next_part_brief,
                            "narration": " ".join(sc.narration for sc in script.scenes),
                            "category": script.category, "template": template, "structure": script.structure,
                            "created": dt.datetime.now().isoformat(timespec="seconds")}
    elif script.series_part == 2:
        seri.pop("bekleyen", None)
        seri.setdefault("biten", []).append(script.title)
    if script.series_part:
        seri_file.parent.mkdir(exist_ok=True)
        seri_file.write_text(json.dumps(seri, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hazır: {video}")


if __name__ == "__main__":
    main()
