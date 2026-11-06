#!/usr/bin/env python3
"""Yeni serilerin çizim testleri (ağ yok, ses yok; her kelime sabit 0,5 sn):

- olsaydin kalıbı (kart şablonu): hesap fişi (receipt) kartı; card_lines ayrıştırma, kart türü seçimi, satırların
  dış sesle basılması, güvenli alan; sayaç kartının Türkçe para ve oran değerleri,
- Nasıl üretiliyor? (uretim kalıbı, templates/uretim.json ile nasil çizicisi): AŞAMA işaretleri, bölüm planı,
  başlık yazıları, kraft zemin, yürüyen bandın kırpılmadan güvenli alanda kalması,
- birleşim: demo senaryolarının şablon yönlendirmesi ve pipeline.build'in çiziciye geçirdiği varyant ve fiş satırları,
- mevcut nasil ve kart videolarının kareleri bu değişiklikten önceki commit'tekiyle piksel piksel aynı.

    python -B tests/panel/test_seri_cizim.py
    python -B tests/panel/test_seri_cizim.py --kareler <kök> <senaryo.json> <kart|nasil>
        <kök>/shortgen ile senaryonun birkaç karesinin sha256'sını JSON yazar (piksel eşliği testi bunu iki kökte
        çalıştırır)

Piksel eşliğinin tabanı SERI_CIZIM_TABAN (varsayılan: bu dalın ayrıldığı commit); taban depoda yoksa test atlanır.
nasil ya da kart görünümü bilerek değiştiğinde taban o değişikliğin commit'ine çekilir.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
TABAN = os.environ.get("SERI_CIZIM_TABAN", "a0b3372")
ADIM_SN = 0.5                                  # kelime başına süre
DEMO = {"nasil": REPO / "demo/nasil/ornek_cay.json", "kart": REPO / "demo/kart/ornek_cin_seddi.json",
        "uretim": REPO / "demo/uretim/ornek_kalem.json", "olsaydin": REPO / "demo/olsaydin/ornek_piyango.json"}


def sahneler(data: dict, root: Path, render, Word, renderer: str, kart=None):
    """Senaryodan pipeline.build'in kurduğu sahneler (fotoğraf yok, depodaki hazır çizimler var, kelime zamanları
    sabit adımlı): (sahneler, kelimeler, meta)."""
    words, specs, t = [], [], 0.0
    for sc in data["scenes"]:
        ws = [Word(w, t + j * ADIM_SN, t + j * ADIM_SN + ADIM_SN * 0.8) for j, w in enumerate(sc["narration"].split())]
        t += len(ws) * ADIM_SN
        ill = (sc.get("illustration") or "").strip()
        sprite = root / ill[6:] if ill.startswith("local:") else None
        spec = render.SceneSpec(narration=sc["narration"], kicker=sc.get("kicker", ""), headline=list(sc["headline"]),
                                highlight_line=sc.get("highlight_line", 0), strike=[], theme="light",
                                image_mode="none", image=None, icon="none", sprite=sprite,
                                motion="still" if sprite else "none", drawn=True)
        spec.words = ws
        spec.start = ws[0].start if ws else t
        words += ws
        specs.append(spec)
    specs[0].start = 0.0
    for a, b in zip(specs, specs[1:]):
        b.start = max(b.start - 0.12, a.start + 0.5)
        a.end = b.start
    specs[-1].end = words[-1].end + 1.6
    meta = {"topic": data["topic"], "structure": data["structure"], "title": data.get("title", ""),
            "category": data.get("category", "")}
    for i, (spec, sc) in enumerate(zip(specs, data["scenes"])):
        if renderer == "kart":
            spec.card = {"type": sc.get("card", "auto"), "value": sc.get("card_value", ""),
                         "label": sc.get("card_label", ""), "myth": sc.get("card_myth", ""),
                         "fact": sc.get("card_fact", ""), "note": sc.get("card_note", ""),
                         "mascot": sc.get("mascot", "auto"), "lines": list(sc.get("card_lines") or [])}
            spec.card["type"] = kart.card_type(spec, i, len(specs))
        else:
            spec.card = {"step": sc.get("step", 0), "callouts": list(sc.get("callouts") or []),
                         "mascot": sc.get("mascot", "auto")}
    if renderer == "nasil":
        meta["sablon"] = json.loads((root / "templates" / f"{data['template']}.json").read_text(encoding="utf-8"))
    return specs, words, meta


def kare_anlari(specs) -> list[float]:
    """Kanca, açılış kesmesi, her sahnenin girişi ve ortası, kapanış."""
    ts = {0.0, 0.45, round(specs[-1].end - 0.2, 2)}
    for s in specs:
        ts.update({round(s.start + 0.15, 2), round((s.start + s.end) / 2, 2)})
    return sorted(ts)


def kareler(root: Path, senaryo: Path, renderer: str) -> dict:
    """<kök>/shortgen ile senaryonun kare özetleri {an: sha256}."""
    sys.path.insert(0, str(root))
    sys.dont_write_bytecode = True
    from shortgen import brand, render
    from shortgen.voice import Word
    data = json.loads(senaryo.read_text(encoding="utf-8"))
    if renderer == "kart":
        from shortgen import kart as M
        specs, words, meta = sahneler(data, root, render, Word, "kart", M)
        v = M.KartVideo(specs, words, meta, brand.load_config())
    else:
        from shortgen import nasil as M
        specs, words, meta = sahneler(data, root, render, Word, "nasil")
        v = M.NasilVideo(specs, words, meta, brand.load_config())
    return {f"{t:.2f}": hashlib.sha256(v.frame(t).tobytes()).hexdigest() for t in kare_anlari(specs)}


if __name__ == "__main__" and len(sys.argv) == 5 and sys.argv[1] == "--kareler":
    print(json.dumps(kareler(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve(), sys.argv[4])))
    sys.exit(0)

sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
from PIL import Image  # noqa: E402

from shortgen import kart as K, nasil as N, pipeline as _pipeline, render, script as S  # noqa: E402
from shortgen.voice import Word  # noqa: E402

# modül başında yüklenen shortgen modülleri: aynı süreçte koşan başka test dosyaları shortgen'i yeniden yükleyebilir
# (test_panel geçici kökten); Birlesim pipeline.build'in içeride içe aktardığı kart/nasil bu modüller olsun diye
# bunları geri koyar
_MODULLER = {m: mod for m, mod in sys.modules.items() if m == "shortgen" or m.startswith("shortgen.")}


def _shortgen_modulleri() -> dict:
    return {m: mod for m, mod in sys.modules.items() if m == "shortgen" or m.startswith("shortgen.")}


def _modulleri_koy(moduller: dict) -> None:
    for ad in _shortgen_modulleri():
        del sys.modules[ad]
    sys.modules.update(moduller)

BCFG = {"enabled": True, "handle": "@bilgimakasi", "intro_cut": True, "subtitle_handle": True}


def demo(ad: str) -> dict:
    return json.loads(DEMO[ad].read_text(encoding="utf-8"))


def sahne(card: dict | None = None, headline=("BAŞLIK",), narration="Kısa bir dış ses.", sprite=None, image=None):
    """card_type için en küçük sahne."""
    c = {"type": "auto", "value": "", "label": "", "myth": "", "fact": "", "note": "", "mascot": "auto"}
    c.update(card or {})
    return types.SimpleNamespace(card=c, headline=list(headline), narration=narration, sprite=sprite, image=image)


def yapay_video(kartlar: list[dict], anlatim: dict | None = None, yapi: str = "olsaydin"):
    """Kart verilerinden olsaydin videosu (her sahne bir dış ses cümlesi)."""
    words, specs, t = [], [], 0.0
    for i, c in enumerate(kartlar):
        m = (anlatim or {}).get(i) or "Bu sahnede birkaç kelimelik kısa bir dış ses var, hesap burada yapılır."
        ws = [Word(w, t + j * ADIM_SN, t + j * ADIM_SN + 0.4) for j, w in enumerate(m.split())]
        start, t = t, t + len(ws) * ADIM_SN + 0.3
        words += ws
        card = {"type": "auto", "value": "", "label": "", "myth": "", "fact": "", "note": "", "mascot": "auto",
                "lines": []}
        card.update(c)
        specs.append(types.SimpleNamespace(words=ws, start=start, end=t, kicker="", headline=["KUYUMCU", "OLSAYDIN"],
                                           highlight_line=1, sprite=None, image=None, narration=m, card=card))
    for i, s in enumerate(specs):
        s.card["type"] = K.card_type(s, i, len(specs))
    return K.KartVideo(specs, words, {"topic": "Kuyumcu olsaydın", "structure": yapi}, BCFG), specs


def alfa_kutusu(im: Image.Image):
    return im.getchannel("A").getbbox()


# ---------------------------------------------------------------- hesap fişi satırları
class FisSatirlari(unittest.TestCase):
    def test_kalem_ve_tutar(self):
        self.assertEqual(K.parse_receipt(["KİRA + DEPOZİTO|135.000 ₺", "VERGİ (%20)|-20 MİLYON ₺"]),
                         [("KİRA + DEPOZİTO", "135.000 ₺"), ("VERGİ (%20)", "-20 MİLYON ₺")])

    def test_turkce_buyuk_harf_ve_bosluklar(self):
        self.assertEqual(K.parse_receipt(["  altın   stok |  4,5 milyon ₺ ", "işçilik|5 bin ₺"]),
                         [("ALTIN STOK", "4,5 MİLYON ₺"), ("İŞÇİLİK", "5 BİN ₺")])

    def test_tutarsiz_ve_coklu_ayrac(self):
        self.assertEqual(K.parse_receipt(["SADECE KALEM", "KİRA|", "A|ara not|100 ₺|", "|90.000 ₺"]),
                         [("SADECE KALEM", ""), ("KİRA", ""), ("A", "100 ₺"), ("", "90.000 ₺")])

    def test_iki_nokta_yedegi(self):
        self.assertEqual(K.parse_receipt(["KİRA: 135.000 ₺", "VERGİ (%20): -20 MİLYON ₺"]),
                         [("KİRA", "135.000 ₺"), ("VERGİ (%20)", "-20 MİLYON ₺")])
        # saat ya da oran iki noktadan bölünmez; tutarsız iki nokta da bölünmez
        self.assertEqual(K.parse_receipt(["AÇILIŞ 10:30", "NOT: YOK"]), [("AÇILIŞ 10:30", ""), ("NOT: YOK", "")])

    def test_bos_satirlar_ve_sinir(self):
        self.assertEqual(K.parse_receipt(None), [])
        self.assertEqual(K.parse_receipt(["", "   ", "|", " | "]), [])
        uzun = [f"KALEM {i}|{i} ₺" for i in range(1, 8)]
        self.assertEqual(K.parse_receipt(uzun), [(f"KALEM {i}", f"{i} ₺") for i in range(1, 5)] + [("DİĞER", "18 ₺")])
        # 6. satır sessizce düşmez: görünen satırlar toplama eşit kalır
        alti = K.parse_receipt([f"{c}|10 ₺" for c in "ABCDEF"])
        self.assertEqual(alti, [("A", "10 ₺"), ("B", "10 ₺"), ("C", "10 ₺"), ("D", "10 ₺"), ("DİĞER", "20 ₺")])
        self.assertEqual(sum(S.tutar(a)[0] for _, a in alti), 60)
        self.assertEqual(len(K.parse_receipt(uzun[:5])), 5)

    def test_diger_toplami(self):
        self.assertEqual(K.receipt_sum(["-20 MİLYON ₺", "-3 MİLYON ₺"]), "-23 MİLYON ₺")
        self.assertEqual(K.receipt_sum(["4,5 MİLYON ₺", "1,2 MİLYON ₺"]), "5,7 MİLYON ₺")
        self.assertEqual(K.receipt_sum(["-270.000 ₺", "1 ₺"]), "-269.999 ₺")
        self.assertEqual(K.receipt_sum(["1 MİLYON ₺", "-250.000 ₺"]), "750.000 ₺")
        self.assertEqual(K.receipt_sum(["135.000 TL", ""]), "135.000 TL")      # tutarsız satır toplama girmez
        self.assertEqual(K.receipt_sum(["900.000 ₺", "%4"]), "")              # yüzde toplanmaz
        self.assertEqual(K.receipt_sum(["YOK", "10 ₺"]), "")
        self.assertEqual(K.receipt_sum(["", ""]), "")


# ---------------------------------------------------------------- kart türü
class KartTuru(unittest.TestCase):
    SATIRLAR = ["KİRA|135.000 ₺", "TAŞINMA|20.000 ₺"]

    def test_satirli_sahne_fis(self):
        self.assertEqual(K.card_type(sahne({"lines": self.SATIRLAR}), 1, 5), "receipt")
        self.assertEqual(K.card_type(sahne({"lines": self.SATIRLAR, "value": "155.000 ₺"}), 1, 5), "receipt")
        self.assertEqual(K.card_type(sahne({"type": "receipt", "lines": self.SATIRLAR}), 1, 5), "receipt")
        # kapakta da (çizim olsa bile açık seçim geçerli)
        self.assertEqual(K.card_type(sahne({"type": "receipt", "lines": self.SATIRLAR}, sprite=Path("x.png")), 0, 5),
                         "receipt")

    def test_satirsiz_sahne(self):
        self.assertEqual(K.card_type(sahne({"value": "450.000 ₺"}), 1, 5), "counter")
        self.assertEqual(K.card_type(sahne({"value": "450.000 ₺", "lines": []}), 1, 5), "counter")
        self.assertEqual(K.card_type(sahne({"value": "450.000 ₺", "lines": ["", " | "]}), 1, 5), "counter")
        # satırsız açık fiş seçimi veriyle desteklenmez: görsel yoksa yazı kartı
        self.assertEqual(K.card_type(sahne({"type": "receipt"}), 1, 5), "text")
        self.assertEqual(K.card_type(sahne({"type": "receipt"}, sprite=Path("x.png")), 1, 5), "drawing")

    def test_oncelik(self):
        self.assertEqual(K.card_type(sahne({"lines": self.SATIRLAR}), 4, 5), "cta")
        self.assertEqual(K.card_type(sahne({"lines": self.SATIRLAR}, headline=["AMA ASIL", "MESELE"]), 2, 5),
                         "interstitial")
        self.assertEqual(K.card_type(sahne({"type": "counter", "value": "5 ₺", "lines": self.SATIRLAR}), 1, 5),
                         "counter")

    def test_mevcut_demo_turleri_degismez(self):
        d = demo("kart")
        n = len(d["scenes"])
        for gorsel in (None, Path("cizim.png")):
            for i, sc in enumerate(d["scenes"]):
                c = {"type": sc.get("card", "auto"), "value": sc.get("card_value", ""),
                     "label": sc.get("card_label", ""), "myth": sc.get("card_myth", ""),
                     "fact": sc.get("card_fact", ""), "note": sc.get("card_note", "")}
                once = K.card_type(sahne(c, sc["headline"], sc["narration"], sprite=gorsel), i, n)
                sonra = K.card_type(sahne(dict(c, lines=[]), sc["headline"], sc["narration"], sprite=gorsel), i, n)
                self.assertEqual(once, sonra, (i, sc["headline"]))
                self.assertNotEqual(sonra, "receipt")

    def test_sahne_modeli(self):
        self.assertIn("receipt", S.Scene.model_fields["card"].annotation.__args__)
        sc = S.Scene.model_validate(demo("olsaydin")["scenes"][2])
        self.assertEqual(sc.card, "receipt")
        self.assertEqual(len(sc.card_lines), 5)
        bos = S.Scene.model_validate(demo("kart")["scenes"][3])
        self.assertEqual(bos.card_lines, [])


# ---------------------------------------------------------------- sayaç değerleri
class SayacDegerleri(unittest.TestCase):
    def test_turkce_degerler(self):
        self.assertEqual(K.parse_value("450.000 ₺"), ("", 450000.0, 0, True, " ₺"))
        self.assertEqual(K.parse_value("1,2 MİLYON ₺"), ("", 1.2, 1, False, " MİLYON ₺"))
        self.assertEqual(K.parse_value("%25"), ("%", 25.0, 0, False, ""))
        self.assertEqual(K.parse_value("18 AY"), ("", 18.0, 0, False, " AY"))
        self.assertIsNone(K.parse_value("1 / 90 MİLYON"))
        self.assertIsNone(K.parse_value("3:1"))
        self.assertEqual(K.fmt_value(450000, 0, True), "450.000")
        self.assertEqual(K.fmt_value(1.2, 1, False), "1,2")

    def test_sayac_karti(self):
        degerler = ["450.000 ₺", "1,2 MİLYON ₺", "%25", "18 AY", "1 / 90 MİLYON"]
        anlatim = {0: "Ayda ortalama 450.000 lira gelir.", 1: "Yılda 1,2 milyon lira eder.",
                   2: "Bunun yüzde 25'i vergi.", 3: "Yatırım 18 ayda geri döner.",
                   4: "Kazanma ihtimali 90 milyonda bir."}
        v, specs = yapay_video([{"value": d, "label": "ETİKET"} for d in degerler] + [{}], anlatim)
        self.assertEqual(v.types, ["counter"] * 5 + ["cta"])
        for i, d in enumerate(degerler):
            c = v.scene(i).card
            self.assertIsInstance(c, K.CounterCard)
            self.assertEqual(c.text_at(1.0), d)
            if i == 4:                  # oran sayılmaz: her an olduğu gibi
                self.assertEqual(c.text_at(0.3), d)
            # sayı söylendiği anda oturur
            sayi = re.findall(r"\d+", d)[-1] if i == 4 else re.sub(r"\D", "", d)
            w = next(w for w in specs[i].words if sayi in re.sub(r"\D", "", w.text))
            self.assertAlmostEqual(c.land, max(0.25, w.start - specs[i].start + 0.05), places=6)


# ---------------------------------------------------------------- hesap fişi kartı
class FisKarti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        specs, words, meta = sahneler(demo("olsaydin"), REPO, render, Word, "kart", K)
        cls.specs = specs
        cls.v = K.KartVideo(specs, words, meta, BCFG)
        anlatim = {1: "Önce vitrin ve kasa kurulur, sonra altın stok alınır, personel tutulur ve hesap büyür, "
                      "toplam 5.320.000 lira."}
        cls.zor, cls.zor_specs = yapay_video([
            {"type": "receipt", "lines": ["KİRA + DEPOZİTO|135.000 ₺", "TAŞINMA|20.000 ₺"], "value": "155.000 ₺",
             "note": "Tahmini · Kasım 2026"},
            {"lines": ["ÇOK UZUN BİR KALEM ADI: VİTRİN, KASA VE ALARM SİSTEMİ|1.250.000 ₺", "altın stok|4,5 MİLYON ₺",
                       "SADECE KALEM", "|90.000 ₺", "PERSONEL (3 KİŞİ)|-270.000 ₺", "ALTINCI|1 ₺"],
             "value": "123.456.789.000 ₺", "label": "İLK YATIRIM", "note": "Tahmini · Kasım 2026 · İstanbul"},
            {"lines": ["AYLIK CİRO|900.000 ₺", "KÂR MARJI|%4"]},
            {},
        ], anlatim)

    def fisler(self):
        for v, specs in ((self.v, self.specs), (self.zor, self.zor_specs)):
            for i, t in enumerate(v.types):
                if t == "receipt":
                    yield v, specs[i], v.scene(i)

    def test_demo_turleri(self):
        self.assertEqual(self.v.types, ["drawing", "counter", "receipt", "counter", "interstitial", "text", "cta"])
        self.assertEqual(self.zor.types, ["receipt", "receipt", "receipt", "cta"])

    def test_satirlar_dis_sesle_basilir(self):
        sc = self.v.scene(2)
        c = sc.card
        self.assertIsInstance(c, K.ReceiptCard)
        self.assertEqual([k for k, _ in c.rows], ["İKRAMİYE", "VERGİ (%20)", "EV", "ARABA", "AİLEYE PAY"])
        self.assertEqual((c.total, c.total_label), ("52 MİLYON ₺", "KALAN"))
        ev = c.events
        self.assertEqual(len(ev), len(c.rows) + 1)
        self.assertTrue(all(b > a for a, b in zip(ev, ev[1:])), ev)
        self.assertGreaterEqual(ev[0], c.T0 - 1e-9)
        self.assertLessEqual(ev[-1], sc.dur - c.HOLD - c.FEED + 1e-6)
        spec = self.specs[2]
        st = spec.start

        def an(kelime):
            return next(w.start for w in spec.words if K.tr_lower(w.text).startswith(kelime)) - st - 0.08

        # VERGİ, EV, ARABA, AİLEYE PAY ve toplam söylendikleri anda (bir önceki satırdan en az bir besleme sonra)
        for k, kelime in ((1, "vergi"), (2, "ev"), (3, "araba"), (4, "ailene"), (5, "52")):
            self.assertGreaterEqual(ev[k] + 1e-9, an(kelime), kelime)
            self.assertLess(ev[k] - an(kelime), 0.4, kelime)

    def test_kagit_beslenir_ve_damga_oturur(self):
        sc = self.v.scene(2)
        c = sc.card
        ls = [c.length(i * 0.05) for i in range(int(sc.dur / 0.05) + 1)]
        self.assertTrue(all(b >= a - 1e-9 for a, b in zip(ls, ls[1:])))
        self.assertAlmostEqual(ls[0], c.feed[0])
        self.assertAlmostEqual(ls[-1], c.L_full)
        self.assertIsNone(c.stamp_state(c.events[-1]))
        k, al = c.stamp_state(c.events[-1] + 1.0)
        self.assertAlmostEqual(k, 1.0, places=3)
        self.assertEqual(al, 1.0)
        self.assertEqual(c.mood(0.0, sc.dur), "normal")
        self.assertEqual(c.mood(c.events[-1] + 1.0, sc.dur), "surprised")

    def test_kapakta_basili(self):
        c = self.zor.scene(0).card
        self.assertTrue(c.instant)
        self.assertEqual(c.length(0.0), c.L_full)
        self.assertEqual(c.stamp_state(0.0), (1.0, 1.0))

    def test_uzun_kalem_ve_toplam_sigar(self):
        c = self.zor.scene(1).card
        self.assertGreaterEqual(c.fs, 40)                # telefonda okunur
        self.assertEqual(c.scale, 1.0)
        self.assertEqual(len(c.rows), 5)
        self.assertGreaterEqual(c.total_size, 44)
        for bases, lines, amount, _ in c.row_geo:          # kalem tutara binmez
            room = c.PW - 2 * c.PAD - (K.tw(amount, "mono", c.fs) + 48 if amount else 0)
            self.assertLessEqual(K.tw(lines[-1], "mono", c.fs), room + 1e-6, lines)
        self.assertEqual(self.zor.scene(2).card.total_label, "TOPLAM")

    @staticmethod
    def kart(lines, value="45.000 ₺", label="ELİNE KALAN", idx=2):
        spec = types.SimpleNamespace(words=[], start=0.0, end=8.0, headline=["ELİNE NE", "KALIR?"], narration="",
                                     image=None, sprite=None, card={"type": "receipt", "lines": lines, "value": value,
                                                                    "label": label, "note": "Tahmini · Kasım 2026"})
        return K.ReceiptCard({"spec": spec, "idx": idx, "dur": 8.0, "slug": "deneme", "handle": "@x",
                              "box": K.CARD0 if idx == 0 else K.CARD})

    KUYUMCU = ["AYLIK CİRO|1.200.000 ₺", "ALTIN ALIŞ MALİYETİ|-950.000 ₺", "DÜKKÂN KİRASI|-85.000 ₺",
               "ÇALIŞAN MAAŞLARI|-90.000 ₺", "VERGİ VE SİGORTA|-30.000 ₺"]

    def test_kalemler_kisaltilmaz(self):
        """İstemin sınırındaki (en fazla 22 karakter) kalemler 3-5 satırlık fişte '…' ile kesilmez: önce iki satıra
        sarılır ve yazı küçülür; ekrandaki yazı fişin alt başlığından (MIN_FS) küçük olmaz."""
        durumlar = [self.KUYUMCU[:n] for n in (3, 4, 5)] + [["KİRA + DEPOZİTO|-135.000 ₺"] * n for n in (3, 4, 5)]
        durumlar.append(["UÇAK BİLETİ (TEK YÖN)|-1.250.000 ₺", "VİZE VE RESMİ BELGELER|-385.000 ₺",
                         "KİRA + DEPOZİTO (2 AY)|-540.000 ₺", "İLK AY MARKET|-120.500 ₺", "ŞEHİR İÇİ ULAŞIM|-49.178 ₺"])
        for idx in (2, 0):
            for lines in durumlar[:6] if idx == 0 else durumlar:
                c = self.kart(lines, idx=idx)
                yazilar = [L for _, ls, _, _ in c.row_geo for L in ls]
                self.assertFalse([L for L in yazilar if L.endswith("…")], (idx, yazilar))
                self.assertEqual(" ".join(yazilar).split(), " ".join(k for k, _ in c.rows).split())
                self.assertGreaterEqual(c.fs * c.scale, c.MIN_FS - 1e-6, (idx, lines))
        c = self.kart(self.KUYUMCU)
        self.assertGreaterEqual(c.fs * c.scale, 36)                  # kart sahnesinde ölçek 0,97, ~37 px
        self.assertIn(["ALTIN ALIŞ", "MALİYETİ"], [ls for _, ls, _, _ in c.row_geo])
        # kısa kalemli fişin yerleşimi değişmez
        c = self.kart(["KİRA|135.000 ₺", "TAŞINMA|20.000 ₺"])
        self.assertEqual((c.fs, c.lh, c.scale), (44, 57, 1.0))

    def test_toplam_etiketi_damgaya_binmez(self):
        """Uzun toplam etiketi damganın altına girmez: damga 44 px'e kadar, sonra etiket 30 px'e kadar küçülür; yine
        sığmazsa etiket kendi satırında, damga altında sağa yaslı durur."""
        iw = K.ReceiptCard.PW - 2 * K.ReceiptCard.PAD
        for label in ("TOPLAM", "ELİNE KALAN", "AYLIK NET KAZANÇ", "YILLIK NET KAZANÇ", "İLK AY TOPLAM GİDER",
                      "BİR YILDA ELİNE KALAN NET PARA"):
            for total in ("45.000 ₺", "1.250.000 ₺", "-2.344.678 ₺", "52 MİLYON ₺", "64.000.000 ₺"):
                c = self.kart(["KİRA|-35.000 ₺", "MAAŞ|85.000 ₺"], value=total, label=label)
                lab = K.torn_label(c.total, c.total_size, K.OFF, K.RED, 1)
                stamp_l, stamp_t = c.total_c[0] - lab.w / 2, c.total_c[1] - lab.h / 2
                right = c.PAD + K.tw(c.total_label_text, "archivo", c.total_label_size)
                self.assertLessEqual(right, c.PAD + iw + 1e-6, (label, total))
                if c.total_stacked:                                  # etiket damganın üstünde
                    self.assertLess(c.total_base + 12, stamp_t, (label, total))
                else:                                                # etiket damganın solunda, arada boşluk
                    self.assertLess(right + 30, stamp_l, (label, total))
                    self.assertGreaterEqual(c.total_label_size, 30)
                self.assertEqual(c.total_label_text, label, "etiket kısaltılmaz")
        c = self.kart(["KİRA|-35.000 ₺", "MAAŞ|85.000 ₺"], value="420.000 ₺", label="TOPLAM")
        self.assertEqual((c.total_size, c.total_label_size, c.total_stacked), (76, 40, False))
        c = self.kart(["KİRA|-35.000 ₺", "MAAŞ|85.000 ₺"], value="-2.344.678 ₺", label="İLK AY TOPLAM GİDER")
        self.assertTrue(c.total_stacked)
        self.assertEqual(c.total_size, 76, "kendi satırında damga yeniden büyür")

    def test_guvenli_alan(self):
        rx0, ry0 = K.CARD_REGION[:2]
        for v, spec, sc in self.fisler():
            c = sc.card
            for lt in [0.0, 0.2] + [e + d for e in c.events if e >= 0 for d in (0.05, 0.15, 0.4)] + [sc.dur]:
                x0, y0, x1, y1 = alfa_kutusu(c.layer(lt, sc.dur))
                self.assertGreaterEqual(x0 + rx0, 0, (spec.narration, lt))
                self.assertLessEqual(x1 + rx0, K.SAFE[2], (spec.narration, lt))
                self.assertGreaterEqual(y0 + ry0, K.SAFE[1], (spec.narration, lt))
                self.assertLessEqual(y1 + ry0, K.CARD_FLOOR, (spec.narration, lt))
            for lt in (0.3, sc.dur - 0.05):                # karenin bütün içerik katmanları
                x0, y0, x1, y1 = alfa_kutusu(v.frame(spec.start + lt, debug_layers=True))
                self.assertLessEqual(x1, K.SAFE[2])
                self.assertGreaterEqual(y0, K.SAFE[1])
                self.assertLessEqual(y1, K.SAFE[3])

    def test_terminal_ve_seri_adi(self):
        self.assertEqual(self.v.logs[2], "hesap: kalan 52 milyon ₺")
        self.assertEqual(self.zor.logs[2], "hesap basılıyor")
        self.assertEqual({self.v.right_label(i) for i in range(self.v.n)}, {K.OLSAYDIN_ADI})
        u, _ = yapay_video([{}, {}], yapi="uretim")
        u.scenes[1].headline = ["AŞAMA 2", "PİŞİRİLİR"]
        self.assertEqual([u.right_label(0), u.right_label(1)], [K.STRUCT_RIGHT["uretim"], "AŞAMA 2"])
        self.assertEqual(K.STRUCT_RIGHT["uretim"], N.sablon_of("uretim")["seri_adi"])


# ---------------------------------------------------------------- Nasıl üretiliyor?
class UretimVaryanti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        specs, words, meta = sahneler(demo("uretim"), REPO, render, Word, "nasil")
        cls.specs, cls.meta = specs, meta
        cls.v = N.NasilVideo(specs, words, meta, BCFG)

    def test_asama_isaretleri(self):
        for s in ("AŞAMA 2", "aşama 2: karıştır", "2. AŞAMA", "ADIM 3", "3. adım"):
            self.assertIsNotNone(N.step_marker(s), s)
        for s in ("AŞAMALAR", "ÜRETİM AŞAMASI", "2 AŞAMADA"):
            self.assertIsNone(N.step_marker(s), s)
        self.assertEqual(N._as_adim("AŞAMA 2 KARIŞTIR"), "ADIM 2 KARIŞTIR")
        self.assertEqual(N._as_adim("2. aşama"), "ADIM 2")
        self.assertEqual(N._as_adim("KARIŞTIR"), "KARIŞTIR")
        self.assertEqual(N.step_title(["AŞAMA 1", "GRAFİT VE KİL", "KARIŞTIRILIR"]), ["GRAFİT VE KİL", "KARIŞTIRILIR"])
        self.assertEqual(N.step_title(["AŞAMA 1: KARIŞTIR"]), ["KARIŞTIR"])
        self.assertEqual(N.step_title(["aşama 2"]), [])

    def test_plan(self):
        segs = self.v.segs
        self.assertEqual([s.kind for s in segs], ["hook", "step", "step", "step", "step", "recap"])
        self.assertEqual([s.number for s in segs if s.kind == "step"], [1, 2, 3, 4])
        self.assertEqual(segs[1].title, ["GRAFİT VE KİL", "KARIŞTIRILIR"])
        self.assertEqual(segs[-1].title, ["KURŞUN KALEM"])

    def test_plan_basliktan(self):
        """step alanı olmadan başlıktaki AŞAMA işaretleri; başlıksız aşama kartı 'AŞAMA n' olur."""
        def sp(h):
            return types.SimpleNamespace(headline=h, highlight_line=0, card={}, sprite=None, image=None)
        specs = [sp(["NASIL", "ÜRETİLİYOR?"]), sp(["AŞAMA 1"]), sp(["2. AŞAMA", "PİŞİR"]), sp(["AŞAMA 3"]),
                 sp(["ÖZET"])]
        segs = N.plan(specs, "AŞAMA")
        self.assertEqual([s.kind for s in segs], ["hook", "step", "step", "step", "recap"])
        self.assertEqual([s.title for s in segs[1:4]], [["AŞAMA 1"], ["PİŞİR"], ["AŞAMA 3"]])
        self.assertEqual(N.plan(specs)[1].title, ["ADIM 1"])

    def test_varyant(self):
        v = N.varyant({"structure": "uretim"})
        self.assertEqual((v["adim_kelimesi"], v["zemin"], v["ilerleme"]), ("AŞAMA", "kraft", "bant"))
        self.assertEqual(N.varyant(self.meta), v)
        self.assertEqual(N.varyant({}), N.VARSAYILAN)
        self.assertEqual(N.varyant({"structure": "nasil"}), N.VARSAYILAN)
        self.assertEqual(N.varyant({"sablon": {"adim_kelimesi": " ", "zemin": 3}}), N.VARSAYILAN)
        self.assertEqual(N.sablon_of("olmayan"), {})
        u = json.loads((REPO / "templates/uretim.json").read_text(encoding="utf-8"))
        self.assertEqual((u["renderer"], u["yapi"]), ("nasil", "uretim"))
        self.assertTrue(set(N.VARSAYILAN) <= set(u), set(N.VARSAYILAN) - set(u))
        n = json.loads((REPO / "templates/nasil.json").read_text(encoding="utf-8"))
        self.assertEqual((n["renderer"], n["yapi"]), ("nasil", "nasil"))
        self.assertEqual(N.varyant({"sablon": n}), N.VARSAYILAN)

    def test_baslik_yazilari(self):
        v = N.NasilVideo(self.specs, self.v.words, self.meta, BCFG)
        orj_label, orj_text = N.paste_label, K.Pen.text
        for seg, etiket, yazilar in ((v.segs[0], "NASIL ÜRETİLİYOR?", ["4", " AŞAMA"]),
                                     (v.segs[2], "NASIL ÜRETİLİYOR?", ["AŞAMA ", "2", "/4"]),
                                     (v.segs[-1], "ÜRETİM HATTI", ["4/4", "KURŞUN KALEM"])):
            with mock.patch.object(N, "paste_label", side_effect=orj_label) as pl, \
                    mock.patch.object(K.Pen, "text", autospec=True, side_effect=orj_text) as pt:
                v.header(seg)
            self.assertEqual([c.args[1] for c in pl.call_args_list], [etiket])
            self.assertEqual([c.args[3] for c in pt.call_args_list], yazilar)
        with mock.patch.object(N, "label_img", side_effect=N.label_img) as li:
            v.recap_parts(v.segs[-1])
        self.assertEqual([c.args[0] for c in li.call_args_list], ["BİLİYOR MUYDUN?", "SENCE?", "KAYDET, BİRİNE GÖSTER!"])

    def test_kraft_zemin(self):
        bg = N.kraft_bg()
        self.assertEqual(bg.size, (K.W, K.H))
        im = self.v.frame(1.0).convert("RGB")
        x, y = 30, K.H - 120                                    # platform arayüzünün altında kalan boş zemin
        px = im.crop((x, y, x + 40, y + 40)).resize((1, 1), Image.BOX).getpixel((0, 0))
        self.assertTrue(all(abs(a - b) <= 20 for a, b in zip(px, N.KRAFT)), px)

    def test_bant_makasla_ayni_yone_kayar(self):
        """Bant deseni 6 fazda döner (24 px); Makas karede 15-29 px atlarken ham konum deseni geri, ileri ya da
        yerinde oynatırdı. Kayma hızı sınırlı: 30 fps'de her karede Makas'ın yönünde, en çok 2 faz; Makas dururken
        bant da durur. Kare yalnız t'ye bağlı (çizelge bir kez kurulur)."""
        v = N.NasilVideo(self.specs, self.v.words, self.meta, BCFG)
        ts = [i / N.FPS for i in range(int(v.segs[-1].end * N.FPS))]
        geri = list(reversed(ts[::7]))
        sonra = {t: v.belt_offset(t) for t in geri}                 # sırasız çağrı aynı sonucu verir
        xs = [v.scissors_at(t)[0] for t in ts]
        faz = [int(round(v.belt_offset(t) / (N.TREAD / 6))) % 6 for t in ts]
        hizli = 0
        for i in range(1, len(ts)):
            if xs[i] is None or xs[i - 1] is None:
                continue
            dx, d = xs[i] - xs[i - 1], (faz[i] - faz[i - 1]) % 6
            d = d - 6 if d > 3 else d
            self.assertLessEqual(abs(d), 2, ts[i])
            if abs(dx) >= 8:                                         # hızlı: desen Makas'ın yönünde 1-2 faz
                hizli += 1
                self.assertIn(d, (1, 2) if dx > 0 else (-1, -2), (ts[i], dx))
            elif abs(dx) < 1e-9:
                self.assertEqual(d, 0, ts[i])
            else:
                self.assertGreaterEqual(d * dx, 0, (ts[i], dx, d))
        self.assertGreater(hizli, 10)
        self.assertEqual({t: v.belt_offset(t) for t in geri}, sonra)

    def test_bant_kirpilmadan_guvenli_alanda(self):
        v = self.v
        yakalanan = []
        orj = K.put

        def put(img, layer, x, y, **kw):
            yakalanan.append((layer, x, y))
            return orj(img, layer, x, y, **kw)

        son = v.segs[-1].start
        anlar = [i * 0.1 for i in range(int(son / 0.1) + 1)]
        durumlar = set()
        for t in anlar:
            yakalanan.clear()
            img = Image.new("RGBA", (K.W, K.H), (0, 0, 0, 0))
            with mock.patch.object(K, "put", side_effect=put):
                v.progress(img, t)
            (lay, x, y), = yakalanan
            a = lay.getchannel("A")
            w, h = lay.size
            kenar = [a.crop((0, 0, w, 1)), a.crop((0, h - 1, w, h)), a.crop((0, 0, 1, h)), a.crop((w - 1, 0, w, h))]
            self.assertTrue(all(k.getbbox() is None for k in kenar), f"bant katmanın kenarında kırpıldı: t={t:.1f}")
            x0, y0, x1, y1 = alfa_kutusu(lay)
            self.assertLessEqual(x + x1, K.SAFE[2])
            self.assertGreaterEqual(y + y0, N.HEAD[1] + 100, t)     # başlık satırının etiketine binmez
            self.assertLessEqual(y + y1, N.HOOK_TOP, t)             # kanca içeriğinin üstünde biter
            durumlar.add(tuple(s for s, _ in v.node_states(t)))
        self.assertIn(("done", "cur", "up", "up"), durumlar)
        self.assertIn(("done", "done", "done", "cur"), durumlar)


# ---------------------------------------------------------------- birleşim (içerik + çizim)
class Birlesim(unittest.TestCase):
    """Demo senaryoları load_script ile açılır, şablon yönlendirmesi doğru çiziciyi seçer ve pipeline.build çiziciye
    şablon varyantını (uretim: AŞAMA) ve hesap fişi satırlarını (olsaydin: receipt) geçirir; çizim yapılmaz."""

    @classmethod
    def setUpClass(cls):
        # modül başında içe aktarılan pipeline ve modüller (mock.patch K ve N'ye uygulanır; build de bunları kullanır)
        cls._onceki = _shortgen_modulleri()
        _modulleri_koy(_MODULLER)
        cls.P = _pipeline

    @classmethod
    def tearDownClass(cls):
        _modulleri_koy(cls._onceki)

    def kur(self, ad: str, override: str | None = None):
        script = S.load_script(DEMO[ad])
        template = self.P.pick_template(script, override)
        cap = {}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(N, "render_nasil", lambda sc, w, o, m, mu, meta: cap.update(specs=sc, meta=meta)), \
                mock.patch.object(K, "render_kart", lambda sc, w, o, m, mu, meta: cap.update(specs=sc, meta=meta)):
            self.P.build(script, Path(tmp) / "b", use_voice=False, music=None, template=template)
            cap["metadata"] = json.loads((Path(tmp) / "b" / "metadata.json").read_text(encoding="utf-8"))
        return script, template, cap

    def test_uretim_asama_varyanti(self):
        for override in ("uretim",):  # --template uretim (eslesme.json yapi_sablon artık isemri'yi seçer)
            script, template, cap = self.kur("uretim", override)
            self.assertEqual((script.structure, template), ("uretim", "uretim"))
            self.assertEqual(self.P.sablon_renderer(template), "nasil")
            self.assertEqual(self.P.sablon_yapisi(template), "uretim")
            var = N.varyant(cap["meta"])
            self.assertEqual((var["adim_kelimesi"], var["zemin"], var["ilerleme"]), ("AŞAMA", "kraft", "bant"))
            self.assertEqual([s.card["step"] for s in cap["specs"]], [0, 1, 2, 3, 4, 0])
            self.assertEqual(cap["metadata"]["structure"], "uretim")
            self.assertIn("NasılÜretiliyor", cap["metadata"]["hashtags"])

    def test_olsaydin_hesap_fisi(self):
        script, template, cap = self.kur("olsaydin")
        self.assertEqual((script.structure, template), ("olsaydin", "kart"))
        self.assertEqual(S.fis_sorunlari(script), [])
        turler = [s.card["type"] for s in cap["specs"]]
        self.assertIn("receipt", turler)
        fis = cap["specs"][turler.index("receipt")].card
        self.assertEqual(len(K.parse_receipt(fis["lines"])), 5)
        self.assertEqual((fis["value"], fis["label"]), ("52 MİLYON ₺", "KALAN"))
        self.assertEqual(cap["meta"]["structure"], "olsaydin")
        aciklama = cap["metadata"]["description"]
        uyari = ("Rakamlar 2026 Türkiye verilerine dayanan yaklaşık hesaplardır; kişiye ve şehre göre değişir. "
                 "Yatırım tavsiyesi değildir.")
        if cap["metadata"].get("created", "").startswith("2026"):
            self.assertEqual(aciklama.count(uyari), 1)
            self.assertLess(aciklama.index(uyari), aciklama.index("#"))

    def test_gecici_seri_adi_tek_yerde(self):
        """olsaydin serisinin ekrandaki adı kalıp listesinden gelir (kart sağ etiketi ve format etiketi aynı)."""
        self.assertEqual(K.OLSAYDIN_ADI, S.STRUCTURES["olsaydin"][0])
        self.assertEqual(K.STRUCT_RIGHT["olsaydin"], S.STRUCTURES["olsaydin"][0])


# ---------------------------------------------------------------- piksel eşliği
class PikselEsligi(unittest.TestCase):
    def test_kart_satir_alani_etkisiz(self):
        """Kartta 'lines' alanının bulunması (boş liste) mevcut kart videosunu değiştirmez."""
        specs, words, meta = sahneler(demo("kart"), REPO, render, Word, "kart", K)
        a = K.KartVideo(specs, words, meta, BCFG)
        specs2, words2, meta2 = sahneler(demo("kart"), REPO, render, Word, "kart", K)
        for s in specs2:
            s.card.pop("lines")
        b = K.KartVideo(specs2, words2, meta2, BCFG)
        for t in kare_anlari(specs)[::3]:
            self.assertEqual(a.frame(t).tobytes(), b.frame(t).tobytes(), t)

    def test_onceki_commit_ile_ayni(self):
        """nasil ve kart demo videolarının kareleri SERI_CIZIM_TABAN commit'indeki çizicilerle aynı."""
        try:
            ok = subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{TABAN}^{{commit}}"],
                                capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if not ok:
            self.skipTest(f"taban commit yok: {TABAN}")
        with tempfile.TemporaryDirectory() as tmp:
            arsiv = subprocess.run(["git", "-C", str(REPO), "archive", TABAN, "shortgen", "templates", "brand.json",
                                    "demo/nasil", "demo/kart"], capture_output=True, timeout=120)
            if arsiv.returncode:
                self.skipTest(f"taban arşivi çıkarılamadı: {arsiv.stderr.decode(errors='replace')[:200]}")
            with tarfile.open(fileobj=io.BytesIO(arsiv.stdout)) as tf:
                tf.extractall(tmp, filter="data") if hasattr(tarfile, "data_filter") else tf.extractall(tmp)
            for renderer in ("nasil", "kart"):
                ozet = {}
                for kok in (Path(tmp), REPO):
                    r = subprocess.run([sys.executable, "-B", __file__, "--kareler", str(kok),
                                        str(kok / DEMO[renderer].relative_to(REPO)), renderer],
                                       capture_output=True, text=True, timeout=600)
                    self.assertEqual(r.returncode, 0, r.stderr[-2000:])
                    ozet[kok] = json.loads(r.stdout.strip().splitlines()[-1])
                once, simdi = ozet[Path(tmp)], ozet[REPO]
                self.assertEqual(sorted(once), sorted(simdi))
                farkli = [t for t in once if once[t] != simdi[t]]
                self.assertEqual(farkli, [], f"{renderer}: {len(farkli)}/{len(once)} kare farklı")


if __name__ == "__main__":
    unittest.main(verbosity=2)
