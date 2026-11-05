"""Uçtan uca: senaryo -> görsel -> ses -> kurgu -> yayın paketi."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path

from . import illustrate, images, render, voice
from .script import STRUCTURES, ShortScript, generate_script, load_script, para_var

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


# Kendi kurgu modülü olan şablonlar Claude'a önerilmez, yalnız kendi kuralıyla seçilir (kart: kart_uygun; renderer'ı
# olan diğerleri: yapi_sablon ya da --template). Yeni bir şablon (ör. uretim) "renderer" yazınca kendiliğinden bu gruba
# girer. kart ve nasil dışındaki kurgu modülleri shortgen/<renderer>.py içinde render(...) sunar (bkz. build).
KENDI_RENDERER = ("kart", "nasil")


def _sablon(name: str | None) -> dict:
    if not name or name not in template_catalog():
        return {}
    return json.loads((ROOT / "templates" / f"{name}.json").read_text(encoding="utf-8"))


def sablon_renderer(name: str | None) -> str:
    """Şablonun kurgu modülü ('kart', 'nasil', ...; render.render ile çizilenler ''). Bilinmeyen şablon adı ''."""
    return _sablon(name).get("renderer", "") or ""


def sablon_yapisi(name: str | None) -> str:
    """Şablonun zorunlu anlatım kalıbı: kurgu modülü olan şablondaki "yapi" (nasil.json -> nasil, uretim.json -> uretim;
    renderer nasil olup yazılmamışsa nasil). Kalıba bağlı olmayan şablonlarda ''."""
    t = _sablon(name)
    if not t.get("renderer"):
        return ""
    return t.get("yapi") or ("nasil" if t.get("renderer") == "nasil" else "")


def kendi_secimli() -> set[str]:
    """Claude'un şablon listesine girmeyen şablonlar: kendi kurgu modülü olanlar (kart, nasil, ...)."""
    return {k for k in template_catalog() if sablon_renderer(k)}


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
    by_structure = (m.get("yapi_sablon") or {}).get(script.structure)
    if by_structure in cat:  # yapıya bağlı şablon (ör. uretim -> uretim, olsaydin -> kart) kategori eşleşmesinden önce
        return by_structure
    kart = m.get("kart") or {}
    if "kart" in cat and kart_uygun(script, kart):
        return "kart"
    if m.get("claude_secsin") and script.template in cat and script.template not in kendi_secimli():
        return script.template  # kart yalnız kart_uygun ile, nasil/uretim yalnız yapi_sablon ya da --template ile seçilir
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

    tcfg = render.apply_template(template)  # çizim paleti şablon renklerinden gelsin
    renderer = tcfg.get("renderer", "")      # kart / nasil kendi kurgu modülünü kullanır, diğerleri render.render
    # 1) fotoğraflar (birden çok sorgu, Wikimedia + Openverse, alaka kontrolü)
    credits, used = [], set()
    photos: dict[int, Path] = {}
    photo_credit: dict[int, images.ImageCredit] = {}
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
            photo_credit[i] = cr
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
    if renderer == "kart":
        from . import kart
        for i, (spec, sc) in enumerate(zip(specs, script.scenes)):
            spec.card = {"type": sc.card, "value": sc.card_value, "label": sc.card_label, "myth": sc.card_myth,
                         "fact": sc.card_fact, "note": sc.card_note, "mascot": sc.mascot, "lines": list(sc.card_lines)}
            if spec.image is not None and i in photo_credit:  # not yoksa fotoğraf kartının çipi künyeden yazılır
                cd = images.credit_dict(photo_credit[i])
                spec.card["credit"] = {k: cd.get(k, "") for k in ("author", "license", "source")}
            spec.card["type"] = kart.card_type(spec, i, len(specs))
        kart.render_kart(specs, words, video, mp3, music, {"topic": script.topic, "structure": script.structure,
                                                           "title": script.title, "category": script.category})
    elif renderer == "nasil":
        from . import nasil
        for i, (spec, sc) in enumerate(zip(specs, script.scenes)):  # adım numarası, notlar, maskot (nasil.plan okur)
            spec.card = {"step": sc.step, "callouts": list(sc.callouts), "mascot": sc.mascot}
            if spec.image is not None and i in photo_credit:  # çizim yoksa kullanılan fotoğrafın çipi künyeden
                cd = images.credit_dict(photo_credit[i])
                spec.card["credit"] = {k: cd.get(k, "") for k in ("author", "license", "source")}
        # şablonun varyantı (adım kelimesi, zemin, ilerleme çubuğu; ör. uretim.json: AŞAMA, kraft zemin, yürüyen bant)
        nasil.render_nasil(specs, words, video, mp3, music, {"topic": script.topic, "structure": script.structure,
                                                             "title": script.title, "category": script.category,
                                                             "sablon": tcfg})
    elif renderer:
        # diğer kurgu modülleri (shortgen/<renderer>.py): sahnenin bütün alanları spec.card'da, senaryo meta'da gelir
        import importlib
        mod = importlib.import_module(f".{renderer}", __package__)
        for i, (spec, sc) in enumerate(zip(specs, script.scenes)):
            spec.card = sc.model_dump()
            if spec.image is not None and i in photo_credit:
                cd = images.credit_dict(photo_credit[i])
                spec.card["credit"] = {k: cd.get(k, "") for k in ("author", "license", "source")}
        mod.render(specs, words, video, mp3, music, {"topic": script.topic, "structure": script.structure,
                                                      "title": script.title, "category": script.category,
                                                      "sablon": tcfg, "script": script.model_dump()})
    else:
        render.render(specs, words, video, mp3, music, template=template)

    # 6) yayın paketi
    meta = yayin_paketi(script, template, credits, use_voice)
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return video


def yayin_paketi(script: ShortScript, template: str, credits: list, ai_voice: bool) -> dict:
    """metadata.json: başlık, açıklama (bilgi metni, uyarı satırı, etiketler, görsel atfı) ve kayıt alanları."""
    desc = "\n\n".join(filter(None, [
        script.description,
        " ".join("#" + t for t in (re.sub(r"\W", "", h) for h in script.hashtags) if t),
        images.credits_text(credits),
    ]))
    meta = {
        "title": script.title, "description": desc, "hashtags": script.hashtags,
        "topic": script.topic, "category": script.category, "template": template,
        "credits": [images.credit_dict(c) for c in credits], "ai_voice": ai_voice,
        "series_part": script.series_part, "structure": script.structure, "search_phrase": script.search_phrase,
        "status": "onay_bekliyor", "created": dt.datetime.now().isoformat(timespec="seconds"),
    }
    if script.alkollu:  # alkollü tarif (script.ALKOLLU_ICECEK açıkken): açıklamaya yaş uyarısı
        meta["alkollu"] = True
    if script.structure == "olsaydin" and not para_var(script):
        meta["rakamsiz"] = True  # parasız gün akışı: 'rakamlar yaklaşık, yatırım tavsiyesi değildir' satırı eklenmez
    from .publish import apply_disclaimer, apply_series_tag
    meta = apply_series_tag(meta)  # "Efsane mi, gerçek mi?" gibi format serilerinin etiketi
    return apply_disclaimer(meta)  # Ya sen olsaydın? rakam uyarısı / alkollü tarifin yaş uyarısı


def main() -> None:
    ap = argparse.ArgumentParser(description="Short video üretici")
    ap.add_argument("--topic", help="İsteğe bağlı konu önerisi")
    ap.add_argument("--script", type=Path, help="Hazır script.json ile üret (Claude çağrısı yapılmaz)")
    ap.add_argument("--no-voice", action="store_true", help="ElevenLabs olmadan sessiz deneme")
    ap.add_argument("--music", type=Path, help="Telifsiz müzik dosyası (mp3)")
    ap.add_argument("--template", help="Şablonu elle seç (templates/ klasöründeki ad)")
    ap.add_argument("--structure", choices=list(STRUCTURES),
                    help="Anlatım kalıbını sabitle (öneri serisinden üretim, ör. efsane, nasil, uretim, olsaydin)")
    ap.add_argument("--out", type=Path, default=ROOT / "output")
    a = ap.parse_args()
    load_env(ROOT / ".env")
    yapi = sablon_yapisi((a.template or "").strip())
    if yapi:
        # Adım kartları şablonu (nasil, uretim) adım düzenli senaryo ister: yeni senaryo şablonun kalıbıyla ("yapi")
        # yazılır; başka kalıp verilirse Claude'a gitmeden durur (her sahne bir adım olur, 8-10 adımlık çubuk sığmaz)
        if a.structure and a.structure != yapi:
            raise SystemExit(f"{a.template.strip()} şablonu yalnız {yapi} kalıbıyla kullanılır "
                             f"(verilen kalıp: {a.structure}).")
        if yapi not in STRUCTURES:
            raise SystemExit(f"{a.template.strip()} şablonunun kalıbı tanınmıyor: {yapi}")
        a.structure = yapi

    history = ROOT / "history.jsonl"
    m = json.loads((ROOT / "templates" / "eslesme.json").read_text(encoding="utf-8"))
    pending = ROOT / "state" / "bekleyen_senaryo.json"
    seri_file = ROOT / "state" / "seri.json"
    seri = json.loads(seri_file.read_text(encoding="utf-8")) if seri_file.exists() else {}
    open_part = seri.get("bekleyen")
    # 2. bölüm, 1. bölümden en az 12 saat sonra gelen ilk konusuz üretimde çekilir
    part2_due = bool(open_part) and dt.datetime.now() >= dt.datetime.fromisoformat(open_part["created"]) + dt.timedelta(hours=12)
    # kart alanlarının yönergesi yalnız kart seçilebilecekse istenir (kapalıyken üretim yönergesi aynen kalır)
    kart_on = (a.template or "").strip() == "kart" or bool((m.get("kart") or {}).get("acik"))
    if a.script:
        script = load_script(a.script)
    elif pending.exists() and not a.topic:
        # önceki çalışma ses/kurgu aşamasında düştüyse senaryoyu yeniden üretme (Claude bütçesi harcanmasın)
        print("Önceki çalışmadan kalan senaryo kullanılıyor.")
        script = load_script(pending)
    elif part2_due and not a.topic:
        print("Serinin 2. bölümü üretiliyor:", open_part["title"])
        script = generate_script(history, None, None, series_prev=open_part, kart=kart_on,
                                 adim_kartlari=sablon_renderer(open_part.get("template")) == "nasil")
    else:
        from . import konu_sirasi
        queued = None if a.topic else konu_sirasi.peek()  # panelden sıraya konan konu gündemden önce gelir
        if queued:
            print("Konu sırasından alınan konu:", queued)
        topic = a.topic or queued
        if queued and not a.structure and not a.template:
            # panelde sıraya yazılan konunun serisi (ör. "Kuyumcu olsaydın" -> olsaydin; "genel:" öneki serbest)
            from .trends import seri_tahmini
            kalip, topic = seri_tahmini(queued)
            a.structure = kalip or None
        if not topic and os.environ.get("AUTO_TREND", "1") != "0":
            try:  # konu verilmediyse önerilerin en yüksek puanlısını seç (nasil, uretim, olsaydin otomatik seçilmez)
                from . import trends
                s0 = trends.best()
                topic = trends.uretim_konusu(s0)
                a.structure = a.structure or trends.kalip_of(s0) or None  # efsane önerisi efsane kalıbıyla
                print("Gündemden seçilen konu:", topic)
            except Exception as e:  # noqa: BLE001
                print("Gündem önerisi alınamadı, serbest konu seçilecek:", e)
        if a.structure:
            print("Sabit anlatım kalıbı:", a.structure)
        # seri formatı (sabit kalıp) videoları tek bölümlük: iki bölümlük seri yalnız serbest kalıpta
        allow = os.environ.get("SERIES", "1") != "0" and not open_part and not a.structure
        kendi = kendi_secimli()
        catalog = {k: v for k, v in template_catalog().items() if k not in kendi}  # Claude'a önerilmez
        # yapıya bağlı şablon senaryodan önce bilinir: elle seçilen ya da yapi_sablon (ör. nasil -> kart / nasil,
        # uretim -> uretim, olsaydin -> kart)
        hedef = a.template or (m.get("yapi_sablon") or {}).get(a.structure or "")
        script = generate_script(history, topic, catalog if m.get("claude_secsin") else None, allow_series=allow,
                                 # yapıya bağlı kart yönergesi yalnız şablon elle seçilmediyse (--template nasil kartsız)
                                 kart=kart_on or (not a.template and hedef == "kart"),
                                 structure=a.structure,
                                 # Adım kartları düzeni (NASIL_RULES / URETIM_RULES) yalnız video renderer'ı nasil
                                 # olan şablonla (nasil, uretim) çizilecekse istenir
                                 adim_kartlari=sablon_renderer(hedef) == "nasil",
                                 # şablonun kendi ek yönergesi (templates/<ad>.json "istem"), ör. ek sahne alanları
                                 sablon_kurali=str(_sablon(hedef).get("istem") or ""))
        if queued and konu_sirasi.remove(queued):  # senaryo yazıldı: konu sıradan çıkar (state_sync kaydeder)
            print("Konu sırasından çıkarıldı:", queued)
    if script.scenes and os.environ.get("SERIES_LABEL", "1") != "0":
        script.scenes[0].kicker = series_label(script, history)
        print("Format etiketi:", script.scenes[0].kicker)
    if script.series_part == 2 and open_part and open_part.get("template") and not a.template:
        a.template = open_part["template"]
    template = pick_template(script, a.template)
    print(f"Şablon: {template}")
    yapi = sablon_yapisi(template)
    if yapi and script.structure != yapi:  # ör. hazır senaryo başka kalıpta
        raise SystemExit(f"{template} şablonu yalnız {yapi} kalıbındaki senaryoyla kullanılır "
                         f"(senaryo: {script.structure}).")
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
