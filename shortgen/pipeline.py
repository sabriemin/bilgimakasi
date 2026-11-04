"""Uçtan uca: senaryo -> görsel -> ses -> kurgu -> yayın paketi."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path

from . import illustrate, images, render, voice
from .script import ShortScript, generate_script, load_script

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


def pick_template(script: ShortScript, override: str | None = None) -> str:
    cat = template_catalog()
    if override:
        if override not in cat:
            raise SystemExit(f"Şablon yok: {override}. Mevcut: {', '.join(cat)}")
        return override
    m = json.loads((ROOT / "templates" / "eslesme.json").read_text(encoding="utf-8"))
    if m.get("claude_secsin") and script.template in cat:
        return script.template
    t = m.get("kategoriler", {}).get(script.category.strip().lower(), m.get("varsayilan", "kolaj"))
    return t if t in cat else "kolaj"


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
    for i, sc in enumerate(script.scenes):
        desc = sc.illustration.strip() or (sc.anim_query.strip() if sc.motion != "none" else "")
        if desc and (sc.motion != "none" or i not in photos):
            want[i] = desc
    drawings = illustrate.draw_scenes(want, script.topic, out_dir / "cizimler") if use_drawings else {}

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
    render.render(specs, words, video, mp3, music, template=template)

    # 6) yayın paketi
    desc = "\n\n".join(filter(None, [
        script.description,
        " ".join("#" + h.lstrip("#").replace(" ", "") for h in script.hashtags),
    ]))
    meta = {
        "title": script.title, "description": desc, "hashtags": script.hashtags,
        "topic": script.topic, "category": script.category, "template": template,
        "credits": [images.credit_dict(c) for c in credits], "ai_voice": use_voice,
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
    if a.script:
        script = load_script(a.script)
    elif pending.exists() and not a.topic:
        # önceki çalışma ses/kurgu aşamasında düştüyse senaryoyu yeniden üretme (Claude bütçesi harcanmasın)
        print("Önceki çalışmadan kalan senaryo kullanılıyor.")
        script = load_script(pending)
    else:
        topic = a.topic
        if not topic and os.environ.get("AUTO_TREND", "1") != "0":
            try:  # konu verilmediyse gündemden en yüksek puanlı öneriyi seç
                from .trends import suggest
                s0 = suggest(3)[0]
                topic = f"{s0.topic} (kanca: {s0.hook}; gündem: {s0.trend})"
                print("Gündemden seçilen konu:", topic)
            except Exception as e:  # noqa: BLE001
                print("Gündem önerisi alınamadı, serbest konu seçilecek:", e)
        script = generate_script(history, topic, template_catalog() if m.get("claude_secsin") else None)
    template = pick_template(script, a.template)
    print(f"Şablon: {template}")
    music = a.music or (Path(os.environ["MUSIC_FILE"]) if os.environ.get("MUSIC_FILE") else None)
    out_dir = a.out / f"{dt.datetime.now():%Y-%m-%d_%H%M}_{slugify(script.topic)}"
    video = build(script, out_dir, use_voice=not a.no_voice, music=music, template=template)
    with history.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"date": str(dt.date.today()), "topic": script.topic, "dir": str(out_dir)},
                           ensure_ascii=False) + "\n")
    pending.unlink(missing_ok=True)
    print(f"Hazır: {video}")


if __name__ == "__main__":
    main()
