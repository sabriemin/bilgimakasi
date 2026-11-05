#!/usr/bin/env python3
"""İş Emri şablonunun (Nasıl Üretiliyor?, shortgen/isemri.py) testleri. Ağ yok, ses yok, Claude çağrısı yok.

- üretim hızı: counter kartından (card_value + card_label dönemi), kart yoksa dış sesten; bulunamazsa sayaç çizilmez,
- sahne planı (nasil.plan ile aynı): kanca, aşamalar, devam sahneleri, ölçek; iş emrindeki aşama durumları ve tikler,
  ONAY kutusuna TAMAM, "Yorumlara yaz" ile KAPANDI mührü,
- yerleşim değişmezleri: karenin bütün katmanları (gölgeler dahil) güvenli alanda (x ≤ 935, y 170-1540; dışarıda
  zemin aynen kalır), iş emri, makine bölgesi ve Makas birbirine binmez, dış ses satırları kâğıda sığar; uzun Türkçe
  kelimeler; 6-10 sahnelik senaryolar; fotoğraf (künye çipi) ve görselsiz aşama (genel sanayi presi),
- belirlenimcilik, şablonun yalnız --template isemri ile seçilmesi (eslesme.json değişmez),
- uçtan uca: geçici bir kökte python -m shortgen.pipeline --script demo/isemri/kursun_kalem.json --no-voice
  --template isemri (depodaki history.jsonl'e dokunulmaz).

    python -B tests/panel/test_isemri.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from shortgen import isemri as I, kart as K, pipeline as P, render  # noqa: E402
from shortgen.script import ShortScript, load_script  # noqa: E402
from shortgen.voice import Word  # noqa: E402

ADIM_SN = 0.42
DEMO = REPO / "demo/isemri/kursun_kalem.json"
FOTO = REPO / "demo/eileen_collins_nasa.jpg"
BCFG = {"enabled": False}


def video(data: dict, bcfg: dict | None = None):
    """Senaryodan pipeline.build'in isemri çizicisine verdiği sahneler (sabit adımlı kelime zamanları) ve video."""
    script = ShortScript.model_validate(data)
    words, specs, t = [], [], 0.0
    for sc, raw in zip(script.scenes, data["scenes"]):
        ws = [Word(w, t + j * ADIM_SN, t + j * ADIM_SN + ADIM_SN * 0.8) for j, w in enumerate(sc.narration.split())]
        t += len(ws) * ADIM_SN + 0.2
        ill = sc.illustration.strip()
        sprite = REPO / ill[6:] if ill.startswith("local:") else None
        image = REPO / raw["image"] if raw.get("image") else None
        spec = render.SceneSpec(narration=sc.narration, kicker=sc.kicker, headline=list(sc.headline),
                                highlight_line=sc.highlight_line, strike=[], theme=sc.theme, image_mode="none",
                                image=image, icon="none", sprite=sprite, drawn=True)
        spec.words = ws
        spec.start = ws[0].start if ws else t
        spec.card = sc.model_dump()
        if image is not None:
            spec.card["credit"] = dict(raw.get("credit") or {})
        words += ws
        specs.append(spec)
    specs[0].start = 0.0
    for a, b in zip(specs, specs[1:]):
        b.start = max(b.start - 0.12, a.start + 0.5)
        a.end = b.start
    specs[-1].end = words[-1].end + 0.35
    meta = {"topic": script.topic, "structure": script.structure, "title": script.title,
            "category": script.category, "sablon": {}, "script": script.model_dump()}
    return I.IsEmriVideo(specs, words, meta, bcfg or BCFG), specs, words


def demo() -> dict:
    return json.loads(DEMO.read_text(encoding="utf-8"))


def sahne(narration: str, headline, **kw) -> dict:
    d = {"narration": narration, "kicker": "", "headline": list(headline), "highlight_line": 0, "strike": [],
         "theme": "paper", "image_mode": "none", "image_queries": [], "icon": "none", "illustration": "",
         "motion": "none"}
    d.update(kw)
    return d


def senaryo(scenes: list[dict], konu="Deneme nasıl üretiliyor") -> dict:
    return {"topic": konu, "category": "icatlar", "template": "isemri", "title": konu, "description": "Deneme.",
            "hashtags": ["deneme", "bilgimakasi"], "scenes": scenes, "sources": ["deneme"],
            "search_phrase": "deneme", "structure": "uretim", "series_part": 0, "next_part_brief": ""}


CIZIMLER = ["asama1_pres.png", "asama2_firin.png", "asama3_oluk.png", "asama4_kes_boya.png"]


def uretim_senaryosu(asama: int = 4, devam: int = 0, uzun: bool = False, foto: bool = False, olcek: bool = True,
                     gorselsiz: bool = False) -> dict:
    """asama kadar aşama (devam kadarı bir devam sahnesiyle), kanca ve ölçek sahnesi."""
    sc = [sahne("Bu ürünün içinde sandığın şey yok. Peki nasıl üretiliyor?",
                ["ÇAY BARDAĞI", "NASIL", "ÜRETİLİYOR?"], highlight_line=2,
                illustration="" if gorselsiz else "local:demo/isemri/kalem.png")]
    for k in range(asama):
        bas = (["AŞAMA %d" % (k + 1), "ÇEKOSLOVAKYALILAŞTIRAMADIKLARIMIZDAN"] if uzun and k == 1
               else ["AŞAMA %d" % (k + 1), "MALZEME", "İŞLENİR"])
        kw = {"step": k + 1, "callouts": ["≈1.450°C", "MÜHENDİSLİKLEŞTİREMEDİKLERİMİZDEN"] if uzun else ["72 SAAT"]}
        if not gorselsiz:
            kw["illustration"] = "local:demo/isemri/" + CIZIMLER[k % 4]
        if foto and k == 2:
            kw.update(illustration="", image="demo/eileen_collins_nasa.jpg",
                      credit={"author": "NASA", "license": "Public domain", "source": "wikimedia"})
        sc.append(sahne("Ardından malzeme yüksek ısıda işlenir ve kalıba dökülür.", bas, **kw))
        if k < devam:
            sc.append(sahne("Bu işlem birkaç kez tekrarlanır.", ["TEKRAR"]))
    son = sahne("Türkiye'de günde yaklaşık 2 milyon çay bardağı üretiliyor. Sence evinde kaç tane var? Yorumlara yaz.",
                ["ÇAY BARDAĞI"])
    if olcek:
        son.update(card="counter", card_value="2 MİLYON", card_label="ÇAY BARDAĞI / GÜN", card_note="tahmini")
    sc.append(son)
    return senaryo(sc, "Çay bardağı nasıl üretiliyor")


def anlar(v, adim: float = 0.5) -> list[float]:
    son = v.segs[-1].end + 0.5
    ts = [round(i * adim, 3) for i in range(int(son / adim))]
    for s in v.segs:   # geçişlerin kritik anları: kesme, kayan içerik, damga, notlar, tik
        ts += [s.start + x for x in (0.05, 0.2, 0.36, 0.55, 0.9, 1.3)]
    return sorted(set(round(x, 3) for x in ts))


class Hiz(unittest.TestCase):
    def test_demo_sayaci(self):
        v, _, _ = video(demo())
        h = v.hiz
        self.assertAlmostEqual(h["hiz"], 14e9 / (365.25 * 86400), places=3)
        self.assertEqual((h["isim"], h["sayi"], h["donem"], h["yer"]), ("KALEM", "≈14 MİLYAR", "YILDA", "DÜNYADA"))
        self.assertEqual(v.sayac_degeri(0.0), 0)
        self.assertEqual(v.sayac_degeri(10.6), int(h["hiz"] * 10))
        degerler = [v.sayac_degeri(t / 4) for t in range(160)]
        self.assertEqual(degerler, sorted(degerler), "sayaç geri gitmez")
        self.assertEqual(len(set(v.sayac_degeri(t + 0.1) for t in range(10))), 10, "her saniye artar")

    def test_gunluk_ve_isim(self):
        h = I.uretim_hizi([{"card": "counter", "card_value": "2 MİLYON", "card_label": "ÇAY BARDAĞI / GÜN",
                            "narration": "Türkiye'de günde yaklaşık 2 milyon çay bardağı üretiliyor."}])
        self.assertEqual((h["isim"], h["sayi"], h["donem"], h["yer"]), ("ÇAY BARDAĞI", "≈2 MİLYON", "GÜNDE", "TÜRKİYE'DE"))
        self.assertAlmostEqual(h["hiz"], 2e6 / 86400, places=6)
        self.assertEqual(I._isim("YILDA ÜRETİLEN ÇAY BARDAĞI"), "ÇAY BARDAĞI")
        self.assertEqual(I._isim("KALEM / YIL"), "KALEM")
        h = I.uretim_hizi([{"card": "counter", "card_value": "14.000.000.000", "card_label": "KALEM",
                            "narration": "Her yıl 14 milyar kalem üretilir."}])
        self.assertAlmostEqual(h["hiz"], 14e9 / (365.25 * 86400), places=3)
        self.assertEqual(h["sayi"], "14.000.000.000")

    def test_karti_yoksa_dis_sesten(self):
        d = demo()
        for k in ("card", "card_value", "card_label", "card_note"):
            d["scenes"][-1].pop(k)
        v, _, _ = video(d)
        self.assertAlmostEqual(v.hiz["hiz"], 14e9 / (365.25 * 86400), places=3)
        self.assertEqual((v.hiz["isim"], v.hiz["sayi"]), ("KALEM", "≈14 MİLYAR"))

    def test_sayi_yoksa_sayac_yok(self):
        d = uretim_senaryosu(olcek=False)
        d["scenes"][-1]["narration"] = "Bu bardaklar çok dayanıklı. Sence evinde kaç tane var? Yorumlara yaz."
        v, _, _ = video(d)
        self.assertIsNone(v.hiz)
        im = np.asarray(v.frame(5.0, grain=False), dtype=np.int16)
        zemin = np.asarray(I.sac_zemin().convert("RGB"), dtype=np.int16)
        self.assertLess(np.abs(im[236:330, 600:935] - zemin[236:330, 600:935]).max(), 8, "sayaç çizilmez")
        self.assertEqual(v.sayac_degeri(9.0), 0)

    def test_kucuk_hiz_gizlenir(self):
        self.assertIsNotNone(I.uretim_hizi([{"card": "counter", "card_value": "3", "card_label": "GEMİ / YIL"}]))
        d = uretim_senaryosu()
        d["scenes"][-1].update(card_value="40", card_label="GEMİ / YIL")
        v, _, _ = video(d)
        self.assertIsNone(v.hiz, "video boyunca kıpırdamayan sayaç gösterilmez")


class Plan(unittest.TestCase):
    def test_demo_plani(self):
        v, specs, _ = video(demo())
        self.assertEqual([s.kind for s in v.segs], ["hook", "step", "step", "step", "step", "recap"])
        self.assertEqual(v.N, 4)
        self.assertEqual([" ".join(s.title) for s in v.steps],
                         ["GRAFİT VE KİL KARIŞTIRILIR", "UÇLAR FIRINDA PİŞİRİLİR", "UÇLAR OLUĞA YERLEŞTİRİLİR",
                          "YAPIŞTIRILIR, KESİLİR, BOYANIR"])
        self.assertEqual(v.urun, "KURŞUN KALEM")
        self.assertEqual(v.kicker, "NASIL ÜRETİLİYOR?")
        self.assertTrue(len(v.no) == 4 and v.no.isdigit())

    def test_demo_dogru_bilgiler(self):
        d = demo()
        metin = " ".join(s["narration"] for s in d["scenes"])
        self.assertIn("kurşun yok", metin)
        self.assertIn("bin derecelik", metin)
        self.assertIn("sedir", metin)
        self.assertIn("yaklaşık 14 milyar", metin)
        self.assertIn("tahmin", metin, "dünya üretimi kesin değil, tahmin olarak söylenir")
        self.assertLessEqual(len(metin.split()), 78)
        self.assertNotIn("TEST", json.dumps(d, ensure_ascii=False).upper().replace("TESTİ", ""))
        load_script(DEMO)          # şema geçerli

    def test_durumlar_ve_tikler(self):
        v, _, _ = video(demo())
        st = v.steps
        self.assertEqual(v.durumlar(0.5), ["sira"] * 4)
        self.assertEqual(v.durumlar(st[0].start + 0.1), ["simdi", "sira", "sira", "sira"])
        self.assertEqual(v.durumlar(st[2].start + 0.1), ["bitti", "bitti", "simdi", "sira"])
        recap = v.segs[-1]
        self.assertEqual(v.durumlar(recap.start + 0.01), ["bitti"] * 4)
        cta = v.recap_cta(recap)
        self.assertIsNotNone(cta)
        self.assertEqual(" ".join(w.text for w in v.words[cta:recap.b]), "Yorumlara yaz.")
        self.assertAlmostEqual(v.kapanis_ani(), v.words[cta].start - 0.08)
        # yorum çağrısı kâğıda yazılmaz; soru kendi sayfasından başlar
        sp = v.speech(recap)
        self.assertEqual(sp.b, cta)
        ilk = {v.words[p0].text for p0, _ in sp.pages}
        self.assertIn("Sence", ilk)

    def test_cagrisiz_kapanis(self):
        d = demo()
        d["scenes"][-1]["narration"] = "Dünyada yılda yaklaşık 14 milyar kalem üretildiği tahmin ediliyor."
        v, _, _ = video(d)
        recap = v.segs[-1]
        self.assertIsNone(v.recap_cta(recap))
        self.assertAlmostEqual(v.kapanis_ani(), v.words[recap.b - 1].end + 0.2)

    def test_devam_sahneleri(self):
        v, _, _ = video(uretim_senaryosu(asama=4, devam=3))
        self.assertEqual(v.N, 4)
        self.assertEqual([len(s.scenes) for s in v.steps], [2, 2, 2, 1])


class Yerlesim(unittest.TestCase):
    """Her önemli anda: güvenli alanın dışında zemin aynen kalır; öğeler birbirine binmez."""

    def kontrol(self, v, ts=None):
        zemin = np.asarray(I.sac_zemin().convert("RGB"), dtype=np.int16)
        disari = np.ones(zemin.shape[:2], bool)
        disari[K.SAFE[1]:K.SAFE[3], :K.SAFE[2]] = False
        for t in ts or anlar(v):
            im = np.asarray(v.frame(t, grain=False), dtype=np.int16)
            fark = np.abs(im - zemin).max(axis=2) > 6
            ys, xs = np.nonzero(fark & disari)
            self.assertEqual(len(xs), 0, f"t={t}: güvenli alan dışında {len(xs)} px (x {xs.min() if len(xs) else 0}-"
                                         f"{xs.max() if len(xs) else 0}, y {ys.min() if len(ys) else 0}-"
                                         f"{ys.max() if len(ys) else 0})")
        o = v.olcu
        self.assertGreaterEqual(v.bolge_y1 - I.BOLGE_Y0, 300, "makine bölgesi yeterince büyük")
        self.assertLess(v.bolge_y1 + 12, o["y0"], "makine bölgesinin gölgesi iş emrine binmez")
        # Makas: güvenli alanda, kâğıdın dış ses satırlarına binmez (yalnız eli kâğıdın tırtıl şeridine uzanır)
        cx, cy, sc = I.MAKAS
        for mood in ("normal", "thinking", "happy", "surprised"):
            sp = v.makas.sprite(mood, "open", False, I.MAKAS_KOL[0], I.MAKAS_KOL[1], sc)
            ox, oy = I.Makas.origin(cx, cy, sc)
            a = np.asarray(sp.getchannel("A")) > 20
            ys, xs = np.nonzero(a)
            self.assertLessEqual(ox + xs.max(), K.SAFE[2], mood)
            self.assertLessEqual(oy + ys.max(), K.SAFE[3], mood)
            self.assertGreaterEqual(ox + xs.min(), o["anlati"][2], f"{mood}: Makas dış sese binmez")
            self.assertGreaterEqual(oy + ys.min(), v.bolge_y1 + 12, f"{mood}: Makas makine bölgesine binmez")
        # dış ses satırları kâğıda sığar
        for seg in v.segs:
            sp = v.speech(seg)
            for pi, lines in sp.lines.items():
                self.assertLessEqual(len(lines), I.ANLATI_SATIR)
                for L in lines:
                    w = K.tw(" ".join(sp.texts[i] for i in L), "courier", sp.size)
                    self.assertLessEqual(w, sp.width + 0.5, " ".join(sp.texts[i] for i in L))
        # aşama satırları ONAY kutusunun altından başlar, kâğıdın içinde kalır
        for k in range(v.N):
            bx, cyy, room = v.satir_yeri(k)
            self.assertGreater(cyy - o["rh"] / 2, o["onay"][3])
            self.assertLess(cyy + o["rh"] / 2, o["ayrac2"] + 1)
            im, (x, y) = v.satir(k, "simdi")
            bb = im.getchannel("A").getbbox()
            self.assertLessEqual(x + bb[2], o["kx1"], f"{k}. aşama satırı taşmaz")

    def test_demo(self):
        v, _, _ = video(demo())
        self.kontrol(v)

    def test_marka_acikken(self):
        v, _, _ = video(demo(), {"enabled": True, "intro_cut": True, "watermark_switch_seconds": 7,
                                 "watermark_opacity": 0.85})
        im = v.frame(0.3, grain=False)          # açılış makası ve kesik çizgi güvenli alanda
        self.assertEqual(im.size, (1080, 1920))

    def test_alti_sahne(self):
        v, specs, _ = video(uretim_senaryosu(asama=4))
        self.assertEqual(len(specs), 6)
        self.kontrol(v)

    def test_on_sahne_bes_asama(self):
        v, specs, _ = video(uretim_senaryosu(asama=5, devam=3))
        self.assertEqual((len(specs), v.N), (10, 5))
        self.kontrol(v)

    def test_sekiz_asama_iki_sutun(self):
        v, specs, _ = video(uretim_senaryosu(asama=8))
        self.assertEqual((len(specs), v.N, v.olcu["sut"]), (10, 8, 2))
        self.kontrol(v, [s.start + 1.0 for s in v.segs] + [v.segs[-1].end])

    def test_uzun_turkce_kelimeler(self):
        d = uretim_senaryosu(uzun=True)
        d["scenes"][-1]["headline"] = ["MÜHENDİSLİKLEŞTİREMEDİKLERİMİZDEN"]
        d["scenes"][-1]["card_label"] = "ÇEKOSLOVAKYALILAŞTIRAMADIKLARIMIZDAN / YIL"
        v, _, _ = video(d)
        self.kontrol(v, [s.start + 1.2 for s in v.segs] + [v.segs[-1].end])

    def test_fotograf_ve_gorselsiz(self):
        v, _, _ = video(uretim_senaryosu(foto=True))
        self.kontrol(v, [s.start + 1.2 for s in v.segs])
        v, _, _ = video(uretim_senaryosu(gorselsiz=True))
        self.kontrol(v, [s.start + 1.2 for s in v.segs])


class Zamanlama(unittest.TestCase):
    def test_tik_onay_kapandi_cizilir(self):
        v, _, _ = video(demo())
        recap = v.segs[-1]
        o = v.olcu
        x0, y0, x1, y1 = (int(c) for c in o["onay"])

        def onay(t):
            return np.asarray(v.frame(t, grain=False), dtype=np.int16)[y0 + 8:y1 - 4, x0 + 8:x1 - 8]

        bos, dolu = onay(recap.start - 0.2), onay(recap.start + I.ONAY0 + 0.4)
        self.assertGreater(np.abs(bos - dolu).max(), 60, "ONAY kutusuna TAMAM basılır")
        yesil = (np.abs(dolu - np.array(I.YESIL)).sum(axis=2) < 90).sum()
        self.assertGreater(yesil, 200)
        ka = v.kapanis_ani()
        once, sonra = (np.asarray(v.frame(t, grain=False), dtype=np.int16) for t in (ka - 0.1, ka + 0.4))
        bolge = (slice(int(o["liste_y0"]), int(o["ayrac2"])), slice(int(o["kx0"]), int(o["kx1"])))
        yesil = (np.abs(sonra[bolge] - np.array(I.YESIL)).sum(axis=2) < 90).sum()
        self.assertGreater(yesil, 8000, "KAPANDI mührü aşama listesinin üstüne iner")
        self.assertGreater(np.abs(once[bolge] - sonra[bolge]).max(), 100)

    def test_belirlenimci(self):
        a = video(demo())[0].frame(12.3)
        b = video(demo())[0].frame(12.3)
        self.assertEqual(hashlib.md5(a.tobytes()).hexdigest(), hashlib.md5(b.tobytes()).hexdigest())


class Secim(unittest.TestCase):
    def test_yalniz_elle_secilir(self):
        cfg = json.loads((REPO / "templates/isemri.json").read_text(encoding="utf-8"))
        self.assertEqual((cfg["renderer"], cfg["yapi"]), ("isemri", "uretim"))
        self.assertIn("counter", cfg["istem"])
        self.assertIn("isemri", P.kendi_secimli())
        self.assertEqual(P.sablon_yapisi("isemri"), "uretim")
        self.assertTrue(P.adim_kartli("isemri"))
        self.assertTrue(P.adim_kartli("uretim") and P.adim_kartli("nasil"))
        self.assertFalse(P.adim_kartli("kart") or P.adim_kartli("ajanda") or P.adim_kartli(None))
        m = json.loads((REPO / "templates/eslesme.json").read_text(encoding="utf-8"))
        self.assertNotIn("isemri", json.dumps(m))
        self.assertEqual(m["yapi_sablon"]["uretim"], "uretim")
        s = load_script(DEMO)
        self.assertEqual(P.pick_template(s.model_copy(update={"template": ""})), "uretim")
        self.assertEqual(P.pick_template(s, "isemri"), "isemri")
        uretim = json.loads((REPO / "templates/uretim.json").read_text(encoding="utf-8"))
        self.assertEqual(uretim["renderer"], "nasil", "uretim şablonu onaya kadar aynen kalır")

    def test_uctan_uca(self):
        """Geçici kökte pipeline: video, metadata, history.jsonl yalnız geçici kökte."""
        gecmis = REPO / "history.jsonl"
        once = gecmis.read_bytes() if gecmis.exists() else None
        with tempfile.TemporaryDirectory() as tmp:
            kok = Path(tmp) / "kok"
            shutil.copytree(REPO / "shortgen", kok / "shortgen", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(REPO / "templates", kok / "templates")
            shutil.copytree(REPO / "demo/isemri", kok / "demo/isemri")
            shutil.copy(REPO / "brand.json", kok / "brand.json")
            env = dict(os.environ, SERIES_LABEL="0", AUTO_TREND="0", PYTHONDONTWRITEBYTECODE="1")
            for k in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY"):
                env.pop(k, None)
            r = subprocess.run([sys.executable, "-B", "-m", "shortgen.pipeline", "--script",
                                "demo/isemri/kursun_kalem.json", "--no-voice", "--template", "isemri", "--out",
                                str(Path(tmp) / "out")], cwd=kok, env=env, capture_output=True, text=True,
                               timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            self.assertIn("Şablon: isemri", r.stdout)
            mp4 = list((Path(tmp) / "out").glob("*/video.mp4"))
            self.assertEqual(len(mp4), 1)
            meta = json.loads((mp4[0].parent / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["template"], "isemri")
            sure = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                         "default=nw=1:nk=1", str(mp4[0])], capture_output=True,
                                        text=True).stdout.strip())
            self.assertTrue(20.0 <= sure <= 60.0, sure)
            kare = Path(tmp) / "kare.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(min(12.0, sure / 2)), "-i", str(mp4[0]),
                            "-frames:v", "1", str(kare)], check=True)
            im = Image.open(kare).convert("RGB")
            self.assertEqual(im.size, (1080, 1920))
            self.assertGreater(len(set(im.resize((108, 192)).getdata())), 50, "boş kare değil")
            self.assertTrue((kok / "history.jsonl").exists())
        self.assertEqual(gecmis.read_bytes() if gecmis.exists() else None, once, "depodaki history.jsonl değişmez")


if __name__ == "__main__":
    unittest.main(verbosity=2)
