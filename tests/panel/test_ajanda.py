#!/usr/bin/env python3
"""Ajanda şablonunun (Ya Sen Olsaydın?, shortgen/ajanda.py, 2. sürüm: resim önde) testleri. Ağ yok, ses yok, Claude
çağrısı yok.

- tarih, saat / yıl damgası ve sahne planı (kanca, durak, devam, sayaç, fiş, içeriden notu, son sahne); fotoğraf
  çizimden önce gelir,
- yerleşim değişmezleri: resmi olan her sahnede resim alanı karenin en az %55'i; resmi olmayan sahne boş kalmaz
  (afiş); hesap makinesi yalnız para sahnelerinde ve karenin %25'inden küçük; yazı katmanları (gölgeler dahil) güvenli
  alanda (x ≤ 935, y 170-1540), yalnız resim katmanı yatayda kenara uzanabilir; başlık etiketleri, notlar, fiş ve
  büyük sayı birbirine ve Makas'a binmez; uzun Türkçe kelimeler taşmaz; 6-10 sahnelik senaryolar,
- hesap makinesinin yürüyen toplamı, büyük sayının sayması, içeriden notunun ve son sahnenin dış sesle eşlenmesi,
  belirlenimcilik,
- görsel seçimi: harita, şema, logo ve arma, sorgu istemedikçe reddedilir,
- pipeline.build çizimi (spec.sprite) ve kart alanlarını (spec.card) ajandaya verir,
- şablon yalnız --template ajanda ile seçilir (eslesme.json değişmez),
- uçtan uca: geçici bir kökte python -m shortgen.pipeline --script demo/ajanda/kuyumcu.json --no-voice
  --template ajanda (depodaki history.jsonl'e dokunulmaz).

    python -B tests/panel/test_ajanda.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True

from PIL import Image  # noqa: E402

from shortgen import ajanda as A, kart as K, pipeline as P, render  # noqa: E402
from shortgen.script import ShortScript, load_script  # noqa: E402
from shortgen.voice import Word  # noqa: E402

ADIM_SN = 0.42                                 # kelime başına süre
DEMO = {"elektrikci": REPO / "demo/ajanda/elektrikci.json", "kuyumcu": REPO / "demo/ajanda/kuyumcu.json"}
TARIH = "2026-11-05"
BCFG = {"enabled": False}
FOTO = REPO / "demo/eileen_collins_nasa.jpg"


def video(data: dict, tarih: str = TARIH, bcfg: dict | None = None):
    """Senaryodan pipeline.build'in ajanda çizicisine verdiği sahneler (fotoğraf yalnız 'image' alanıyla, depodaki
    hazır çizimler, kelime zamanları sabit adımlı) ve video."""
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
            "category": script.category, "sablon": {}, "script": script.model_dump(), "tarih": tarih}
    return A.AjandaVideo(specs, words, meta, bcfg or BCFG), specs, words


def demo(ad: str) -> dict:
    return json.loads(DEMO[ad].read_text(encoding="utf-8"))


def sahne(narration: str, headline, **kw) -> dict:
    d = {"narration": narration, "kicker": "", "headline": list(headline), "highlight_line": 0, "strike": [],
         "theme": "paper", "image_mode": "none", "image_queries": [], "icon": "none", "illustration": "",
         "motion": "none"}
    d.update(kw)
    return d


def senaryo(scenes: list[dict], konu="Deneme olsaydın") -> dict:
    return {"topic": konu, "category": "ekonomi ve markalar", "template": "ajanda", "title": konu,
            "description": "Deneme.", "hashtags": ["deneme", "bilgimakasi"], "scenes": scenes, "sources": ["deneme"],
            "search_phrase": "deneme", "structure": "olsaydin", "series_part": 0, "next_part_brief": ""}


def gun_senaryosu(durak: int = 5, devam: int = 2, uzun: bool = False) -> dict:
    """durak kadar saatli durak, devam kadar devam notu, bir içeriden notu, bir fotoğraf ve son sahne."""
    saatler = ["06:45", "08:15", "10:30", "12:00", "14:30", "16:00", "18:45", "21:30"][:durak]
    sc = [sahne("Sen fırıncı olsaydın, günün gece üçte başlardı.", ["SEN FIRINCI", "OLSAYDIN"], highlight_line=1,
                illustration="local:demo/ajanda/olcu_aleti.png")]
    for k, saat in enumerate(saatler):
        bas = ["ÇEKOSLOVAKYALILAŞTIRAMADIKLARIMIZDAN"] if (uzun and k == 1) else [f"{k + 1}. İŞ", "BAŞLAR"]
        kw = {"kicker": saat}
        if k == 2:
            kw.update(image="demo/eileen_collins_nasa.jpg",
                      credit={"author": "NASA", "license": "Public domain", "source": "wikimedia"})
        if k == 3:
            kw.update(illustration="local:demo/ajanda/sigorta_panosu.png")
        sc.append(sahne(f"Saat {saat} olunca bu işe geçersin, iş uzun sürer ve dikkat ister.", bas, **kw))
        if k < devam:
            sc.append(sahne("Sonra kısa bir ara verip aletleri toparlarsın.",
                            ["MÜHENDİSLİKLEŞTİREMEDİKLERİMİZDEN"] if uzun else ["KISA BİR", "ARA"]))
    sc.insert(3, sahne("İçeriden bir bilgi: hamur gece mayalanır, sabah fırına girer.", ["GECE", "MAYASI"],
                       card="interstitial"))
    sc.append(sahne("Sen olsan ne yapardın? Yorumlara yaz.", ["SEN OLSAN?"], card="cta"))
    return senaryo(sc, "Fırıncı olsaydın günün nasıl geçerdi")


def para_senaryosu(uzun: bool = False) -> dict:
    sc = [sahne("Sen kafe açsaydın, ilk ay büyük bir masraf seni beklerdi.", ["SEN KAFE", "AÇSAYDIN"],
                highlight_line=1),
          sahne("Kira ve depozito yaklaşık 135 bin lira tutar.", ["KİRA VE", "DEPOZİTO"], card="counter",
                card_value="135.000 ₺", card_label="KİRA + DEPOZİTO", card_note="tahmini, Ankara",
                illustration="local:demo/ajanda/dukkan.png"),
          sahne("Kahve makinesi ikinci el yaklaşık 2,4 milyon lira değil, 240 bin lira.", ["KAHVE", "MAKİNESİ"],
                card="counter", card_value="240.000 ₺", card_label="KAHVE MAKİNESİ"),
          sahne("Hepsi eklenince ilk ay yaklaşık 470 bin lira eder, indirim de düşülür.", ["İLK AY", "TOPLAM"],
                card="receipt", card_value="470.000 ₺", card_label="İLK AY",
                card_note="Tahmini · Kasım 2026",
                card_lines=["KİRA + DEPOZİTO|135.000 ₺", "KAHVE MAKİNESİ|240.000 ₺",
                            ("DEKORASYONVEELEKTRİKTESİSATI|110.000 ₺" if uzun else "DEKORASYON|110.000 ₺"),
                            "İLK STOK|30.000 ₺", "AÇILIŞ İNDİRİMİ|-45.000 ₺"]),
          sahne("Bu sektörde bir fincan kahvenin maliyeti fiyatının yaklaşık beşte biridir.", ["FİNCAN", "MALİYETİ"],
                card="quote", card_label="Kahvenin maliyeti fiyatının beşte biridir.", card_note="Kafeci, Ankara"),
          sahne("Sen olsan ne yapardın? Yorumlara yaz.", ["SEN OLSAN?"], card="cta")]
    return senaryo(sc, "Kafe açsaydın ilk ay kaç lira harcardın")


def anlar(v, adim: float = 0.25) -> list[float]:
    son = v.p[-1].end
    ts = [round(i * adim, 3) for i in range(int(son / adim))]
    for s in v.p:
        ts += [s.start + d for d in (0.02, 0.1, 0.2, 0.3, 0.45)] + [s.end - 0.03]
    return sorted(t for t in set(ts) if 0 <= t < son)


def kayitli_kareler(v, ts):
    """Karelerdeki bütün katman bindirmeleri (kırpılmadan önceki alfa kutusu, ölçek dahil): [(an, kutu, kırpma)]."""
    asil = K.put
    kayit: list = []
    simdi = [0.0]

    def put(img, layer, x, y, k=1.0, alpha=1.0, clip=K.SAFE, anchor=(0.5, 0.5)):
        if layer is not None and img.size == (K.W, K.H):
            bb = layer.getchannel("A").getbbox()
            if bb:
                kx = 1.0 if abs(k - 1.0) <= 1e-3 else k
                nw, nh = layer.width * kx, layer.height * kx
                ox, oy = x + (layer.width - nw) * anchor[0], y + (layer.height - nh) * anchor[1]
                kayit.append((simdi[0], (ox + bb[0] * kx, oy + bb[1] * kx, ox + bb[2] * kx, oy + bb[3] * kx), clip))
        return asil(img, layer, x, y, k=k, alpha=alpha, clip=clip, anchor=anchor)

    with mock.patch.object(K, "put", put):
        for t in ts:
            simdi[0] = t
            v.frame(t, grain=False)
    return kayit


def kesisir(a, b, pay=1.0) -> bool:
    return a[0] < b[2] - pay and b[0] < a[2] - pay and a[1] < b[3] - pay and b[1] < a[3] - pay


def tesla_senaryosu() -> dict:
    """Sabri'nin beğenmediği gerçek örneğin (short-20261106-004840) senaryosu, yerel resimlerle: kancada fotoğraf ve
    çizim birlikte (fotoğraf önce gelir), yıllı kicker'lar, sayaç ve fiş, fotoğraflı içeriden notu, yazı kicker'ı."""
    portre = {"image": "demo/eileen_collins_nasa.jpg",
              "credit": {"author": "The Nikola Tesla Museum", "license": "CC BY-SA 4.0", "source": "Wikimedia"}}
    sc = [sahne("Nikola Tesla olsaydın, New York'a cebinde dört sentle inerdin.",
                ["TESLA OLSAYDIN", "CEBİNDE", "DÖRT SENTLE"], highlight_line=2, kicker="YA SEN OLSAYDIN? #1",
                illustration="local:demo/ajanda/bilezikler.png", **portre),
          sahne("1884'te Edison'ın yanında altı ay dayanırdın;", ["EDISON'IN YANINDA", "ALTI AY"], highlight_line=1,
                kicker="1884"),
          sahne("sonra günde iki dolara hendek kazardın.", ["GÜNDE", "İKİ DOLARA", "HENDEK"], highlight_line=1,
                kicker="1886", card="counter", card_value="2 $", card_label="GÜNLÜK ÜCRET",
                card_note="1886 · New York", illustration="local:demo/ajanda/dukkan.png", theme="yellow"),
          sahne("1888'de Westinghouse senin alternatif akım patentlerini alırdı;",
                ["WESTINGHOUSE", "PATENTLERİNİ", "ALIRDI"], highlight_line=1, kicker="1888",
                illustration="local:demo/ajanda/sigorta_panosu.png"),
          sahne("anlaşma sana toplamda 276 bin dolar kazandırırdı.", ["TOPLAMDA", "276 BİN DOLAR"], highlight_line=1,
                kicker="WESTINGHOUSE ANLAŞMASI", card="receipt", card_value="276.000 $", card_label="TOPLAM",
                card_note="Westinghouse · 1888-1897", theme="black",
                card_lines=["NAKİT VE HİSSE · 1888|60.000 $", "TOPLU ÖDEME · 1897|216.000 $"]),
          sahne("1893'te Chicago Dünya Fuarı'nı senin sistemin aydınlatırdı.",
                ["CHICAGO DÜNYA FUARI'NI", "SENİN SİSTEMİN", "AYDINLATIRDI"], highlight_line=2, kicker="1893",
                card="interstitial", image="demo/eileen_collins_nasa.jpg",
                credit={"author": "Graham, C.", "license": "Public domain", "source": "Wikimedia"}),
          sahne("Kablosuz enerji kulen ise para kesilince yarım kalırdı.", ["KABLOSUZ ENERJİ", "KULEN", "YARIM KALIRDI"],
                highlight_line=2, kicker="1901", theme="red"),
          sahne("1943'te bir otel odasında yalnız ölürdün;", ["OTEL ODASINDA", "YALNIZ"], highlight_line=1,
                kicker="1943", illustration="local:demo/ajanda/yanik_priz.png"),
          sahne("en yakın dostların güvercinler olurdu.", ["EN YAKIN DOSTLARIN", "GÜVERCİNLER"], highlight_line=1,
                kicker="1943", theme="yellow"),
          sahne("Sen olsan ne yapardın? Yorumlara yaz.", ["SEN OLSAN", "NE YAPARDIN?"], card="cta", theme="red")]
    return senaryo(sc, "Nikola Tesla olsaydın: hayatının dönüm noktaları")


def yazi_kutulari(v, si):
    """Sahnenin son hâlinde metin taşıyan baskı üstü öğelerin kutuları: [(öğe türü, kutu)]."""
    return [(type(o).__name__, o.kutu) for o in v.ogeler
            if o.gorunur(si) and o.kutu is not None and o.yazi_mi and not isinstance(o, (A.YaziOge, A.IzOge))]


MAKAS_KUTU = (A.MAKAS_XY[0] - 112, A.MAKAS_UST, A.MAKAS_XY[0] + 96, A.MAKAS_XY[1] + 64)


# ---------------------------------------------------------------- yardımcılar ve plan
class Plan(unittest.TestCase):
    def test_lcd_aralik_carpani(self):
        # '55-65 BİN' LCD'de 55 olarak çıkıyordu (Sabri, elektrikçi örneği)
        self.assertEqual(A.lcd_degeri("55-65 BİN ₺"), ("55.000-65.000", K.TL))
        self.assertEqual(A.lcd_degeri("55–65 bin TL"), ("55.000-65.000", K.TL))
        self.assertEqual(A.lcd_degeri("55 BİN ₺"), ("55.000", K.TL))
        self.assertEqual(A.lcd_degeri("-1.200 ₺"), ("-1.200", K.TL))

    def test_turkce_tarih(self):
        self.assertEqual(A.turkce_tarih(dt.date(2026, 11, 5)), ("05", "KASIM 2026", "PERŞEMBE", "HAFTA 45 · GÜN 309"))
        self.assertEqual(A.turkce_tarih(dt.date(2026, 2, 1))[1:3], ("ŞUBAT 2026", "PAZAR"))
        self.assertEqual(A.turkce_tarih(dt.date(2026, 8, 31))[1:3], ("AĞUSTOS 2026", "PAZARTESİ"))

    def test_tarihsiz_baslik(self):
        """meta'da yayın tarihi yoksa kancaya somut gün basılmaz (çizim günü yayın günü değildir): gün akışında
        'BİR İŞ GÜNÜ · SAAT SAAT', para gününde 'BİR AYIN HESABI', yıllı hayat hikâyesinde 'BİR ÖMÜR · YIL YIL'."""
        for data, beklenen in ((demo("elektrikci"), ("BİR", "İŞ GÜNÜ", "SAAT SAAT", "")),
                               (demo("kuyumcu"), ("BİR", "AYIN", "HESABI", "")),
                               (tesla_senaryosu(), ("BİR", "ÖMÜR", "YIL YIL", ""))):
            v, specs, words = video(data)
            meta = dict(v.meta)
            meta.pop("tarih")
            v2 = A.AjandaVideo(specs, words, meta, BCFG)
            self.assertEqual(v2.tarih, beklenen)
            for gun in A.GUNLER:
                self.assertNotIn(gun, " ".join(v2.tarih))

    def test_saat_ve_yil(self):
        self.assertEqual(A.saat_of("07:30"), ("07:30", 450))
        self.assertEqual(A.saat_of("7.05"), ("07:05", 425))
        self.assertEqual(A.saat_of("SAAT 17:30"), ("17:30", 1050))
        self.assertIsNone(A.saat_of(""))
        self.assertIsNone(A.saat_of("%25"))
        self.assertIsNone(A.saat_of("1.200.000"))
        self.assertEqual(A.damga_of("1884"), "1884")
        self.assertEqual(A.damga_of("07:30"), "07:30")
        self.assertEqual(A.damga_of("1888-1897"), "1888")
        for k in ("WESTINGHOUSE ANLAŞMASI", "1.200.000", "276.000 $", "12000", "YA SEN OLSAYDIN? #1", ""):
            self.assertEqual(A.damga_of(k), "", k)
        self.assertEqual(A.yil_of("1884'te Edison'ın yanında"), "1884")

    def test_cumle(self):
        self.assertEqual(A.cumle("İLK ARIZA"), "İlk arıza")
        self.assertEqual(A.cumle("ŞANTİYEDE  PANO"), "Şantiyede pano")
        self.assertEqual(A.cumle("IŞIK"), "Işık")

    def test_sayac_metni(self):
        self.assertEqual(A.sayac_metni("276.000 $", 0.5), "138.000 $")
        self.assertEqual(A.sayac_metni("276.000 $", 1.0), "276.000 $")
        self.assertEqual(A.sayac_metni("2 $", 0.0), "0 $")
        self.assertEqual(A.sayac_metni("1,2 MİLYON ₺", 0.5), "0,6 MİLYON ₺")
        self.assertEqual(A.sayac_metni("55-65 BİN ₺", 0.3), "55-65 BİN ₺", "aralık sayılmaz")

    def test_elektrikci_plani(self):
        v, _, _ = video(demo("elektrikci"))
        self.assertEqual([s.tur for s in v.p], ["kanca", "durak", "durak", "serbest", "durak", "iceriden", "durak",
                                                "cta"])
        self.assertEqual([s.saat for s in v.p if s.tur == "durak"], ["07:30", "09:00", "13:00", "17:30"])
        self.assertEqual(v.N, 4)
        self.assertTrue(v.gun)
        self.assertFalse(v.para)
        self.assertIsNone(v.hm, "para yokken hesap makinesi yok")

    def test_kuyumcu_plani(self):
        v, _, _ = video(demo("kuyumcu"))
        self.assertEqual([s.tur for s in v.p], ["kanca", "sayac", "sayac", "fis", "iceriden", "cta"])
        self.assertEqual(v.N, 3)
        self.assertFalse(v.gun)
        self.assertTrue(v.para)
        self.assertIsNotNone(v.hm)

    def test_tesla_plani(self):
        """Yıllı kicker'lar zaman çizgisinin durakları; aynı yılın ikinci sahnesi devam; fotoğraf çizimden önce gelir
        (ilk sürümde kancada Tesla'nın fotoğrafı yerine çizim çıkıyordu)."""
        v, _, _ = video(tesla_senaryosu())
        self.assertEqual([s.tur for s in v.p], ["kanca", "durak", "sayac", "durak", "fis", "iceriden", "durak", "durak",
                                                "serbest", "cta"])
        self.assertEqual([s.damga for s in v.p], ["", "1884", "1886", "1888", "", "1893", "1901", "1943", "1943", ""])
        self.assertEqual(v.p[4].kicker, "WESTINGHOUSE ANLAŞMASI")
        self.assertEqual(v.N, 6)
        self.assertTrue(v.p[0].foto)
        self.assertEqual(v.p[0].resim, REPO / "demo/eileen_collins_nasa.jpg")
        self.assertEqual(v.baskilar[0].tur, "foto")
        self.assertEqual(v.baskilar[5].tur, "foto", "fuarın fotoğrafı içeriden notunun altında büyük görünür")
        self.assertEqual(v.baskilar[1].tur, "afis")
        damgalar = {min(o.sahneler) for o in v.ogeler if isinstance(o, A.DamgaOge)}
        self.assertEqual(damgalar, {2, 3, 5, 7}, "yıl damgası resmin üstüne; afiş yılı zaten gösteriyorsa yok")

    def test_demo_senaryolari(self):
        """Demo senaryoları yüklenir, 6-10 sahne, hazır çizimler depoda (Claude çağrısı yok), ekranda TEST yok."""
        from shortgen.script import fis_sorunlari, para_var
        for ad, yol in DEMO.items():
            s = load_script(yol)
            self.assertTrue(6 <= len(s.scenes) <= 10, ad)
            self.assertEqual(s.structure, "olsaydin")
            self.assertEqual(fis_sorunlari(s), [], ad)
            for sc in s.scenes:
                ill = sc.illustration.strip()
                self.assertTrue(ill == "" or (ill.startswith("local:demo/ajanda/") and (REPO / ill[6:]).is_file()),
                                ill)
                metin = " ".join([sc.narration, sc.kicker, *sc.headline, sc.card_label, sc.card_note, *sc.card_lines])
                self.assertNotIn("TEST", metin.upper())
        self.assertFalse(para_var(load_script(DEMO["elektrikci"])), "elektrikçi demosu parasız")
        self.assertTrue(para_var(load_script(DEMO["kuyumcu"])))


# ---------------------------------------------------------------- yerleşim değişmezleri
class Yerlesim(unittest.TestCase):
    def guvenli(self, v, ts=None):
        """Yazı ve süs katmanları (gölgeler dahil) güvenli alanda; yalnız resim katmanı (BASKI_CLIP ile konan baskı ve
        geçişteki parçaları) yatayda kenara uzanabilir, o da dikeyde güvenli bantta kalır."""
        x0s, y0s, x1s, y1s = K.SAFE
        for t, (x0, y0, x1, y1), clip in kayitli_kareler(v, ts or anlar(v)):
            kutu = (t, (x0, y0, x1, y1))
            if clip == A.BASKI_CLIP:
                self.assertGreaterEqual(max(y0, clip[1]), y0s - 0.5, kutu)
                continue
            if clip == A.MAKINE_CLIP:                   # makine şeridin altından çıkar: üstü çizginin altında gizli
                y0 = max(y0, clip[1])
            # makas kesmesinde (kart.card_cut) parçalar sola kayıp ekranın sol kenarından çıkabilir; solda arayüz yok
            kesme = any(s.i > 0 and s.start <= t < s.start + A.CUT for s in v.p)
            self.assertGreaterEqual(x0, (x0s - 60) if kesme else (x0s - 0.5), kutu)
            self.assertLessEqual(x1, x1s + 0.5, kutu)
            self.assertGreaterEqual(y0, y0s - 0.5, kutu)
            self.assertLessEqual(y1, y1s + 0.5, kutu)

    def resim_buyuk(self, v):
        """Resmi olan her sahnede resim alanı karenin en az %55'i (tam genişliğe yakın); resmi olmayan sahnede aynı
        alanı boş olmayan bir afiş kaplar."""
        for s in v.p:
            b = v.baskilar[s.i]
            kutu = v.resim_kutusu(s.i)
            if s.resim is not None:
                self.assertIsNotNone(kutu, s.i)
                self.assertGreaterEqual((kutu[3] - kutu[1]) / K.H, 0.55, s.i)
                self.assertGreaterEqual((kutu[2] - kutu[0]) / K.W, 0.85, s.i)
                self.assertIn(b.tur, ("foto", "cizim"))
            else:
                self.assertEqual(b.tur, "afis", s.i)
            im = b.icerik(0.5)
            self.assertEqual(im.size, (A.FOTO[2] - A.FOTO[0], A.FOTO[3] - A.FOTO[1]))
            self.assertGreaterEqual(im.size[1] / K.H, 0.55)
            renk = len(set(im.resize((96, 110)).getdata()))
            self.assertGreater(renk, 40, (s.i, b.tur, "baskı boş kalmaz"))

    def binmez(self, v):
        """Her sahnenin son hâlinde: başlık etiketleri başlık alanında (x ≤ BAS_X1) ve Makas'a binmez; baskı üstü
        öğeler (damga, kâğıt notu, büyük sayı, fiş, yapışkan not, liste) başlığa, Makas'a, dış ses şeridine ve
        birbirine binmez; hepsi baskının üst sınırının altında."""
        for s in v.p:
            bas = v.basliklar[s.i]
            for b in bas.kutular:
                self.assertLessEqual(b[2], A.BAS_X1 + 4, (s.i, bas.lines))
                self.assertGreaterEqual(b[0], A.X0 - 16, (s.i, bas.lines))
                self.assertGreaterEqual(b[1], A.BAS_YMIN - 4, (s.i, bas.lines))
                self.assertLessEqual(b[3], A.SERIT[1] + 4, (s.i, bas.lines))
                self.assertFalse(kesisir(b, MAKAS_KUTU), (s.i, "Makas", bas.lines))
            for L in bas.lines:
                self.assertLessEqual(K.tw(L, "anton", bas.size) + 0.4 * bas.size, A.BAS_X1 - A.X0 + 0.5, L)
            ogeler = yazi_kutulari(v, s.i)
            for k, (ad, a) in enumerate(ogeler):
                self.assertGreaterEqual(a[1], A.FOTO[1], (s.i, ad, a))
                self.assertLessEqual(a[2], K.SAFE[2] + 0.5, (s.i, ad, a))
                for b in bas.kutular:
                    self.assertFalse(kesisir(a, b, 3), (s.i, ad, "başlık", a, b))
                self.assertFalse(kesisir(a, MAKAS_KUTU, 3), (s.i, ad, "Makas", a))
                self.assertFalse(kesisir(a, A.SERIT, 3), (s.i, ad, "şerit", a))
                for ad2, b in ogeler[k + 1:]:
                    izin = {ad, ad2} in ({"FisOge", "SayiOge"},)       # toplamın kâğıdı fişin alt ucuna biner
                    if not izin:
                        self.assertFalse(kesisir(a, b, 3), (s.i, ad, ad2, a, b))
            for o in v.ogeler:
                if isinstance(o, A.YaziOge) and o.gorunur(s.i):
                    a = o.kutu
                    self.assertLessEqual(a[2], A.X1 + 2, (s.i, o.yazi.text, a))
                    self.assertGreaterEqual(a[0], A.X0 - 10, (s.i, o.yazi.text, a))
            v.frame(s.end - 0.03, grain=False)

    def makine_kucuk_ve_parada(self, v, ts=None):
        """Hesap makinesi yalnız para sahnelerinde görünür, karenin %25'inden küçüktür ve her para sahnesinin ana
        anında (sayı oturunca) ekrandadır."""
        gorunen = set()
        for t in ts or anlar(v, 0.5):
            e = v.makine_durumu(t)
            if e is None:
                continue
            si = v.scene_at(t)
            self.assertTrue(v.p[si].para, (t, si, v.p[si].tur))
            gorunen.add(si)
        for s in v.p:
            if s.para:
                self.assertIsNotNone(v.makine_durumu(v.olay[s.i] + 0.05), s.i)
                img = Image.new("RGBA", (K.W, K.H))
                kutu = v.makine(img, v.olay[s.i] + 0.05)
                alan = (kutu[2] - kutu[0]) * (kutu[3] - kutu[1])
                self.assertLess(alan, 0.25 * K.W * K.H)
                self.assertLess(alan, 0.06 * K.W * K.H, "ikincil: ilk sürümün tam genişlik makinesi değil")
                self.assertLessEqual(kutu[2], K.SAFE[2])
                self.assertGreaterEqual(kutu[1], A.FOTO[1])
        if v.hm is None:
            self.assertFalse(gorunen)

    def hepsi(self, v, adim=0.5):
        self.resim_buyuk(v)
        self.guvenli(v, anlar(v, adim))
        self.binmez(v)
        self.makine_kucuk_ve_parada(v)

    def test_elektrikci(self):
        v, _, _ = video(demo("elektrikci"))
        self.hepsi(v, 0.25)

    def test_kuyumcu(self):
        v, _, _ = video(demo("kuyumcu"))
        self.hepsi(v, 0.25)

    def test_tesla(self):
        v, _, _ = video(tesla_senaryosu(), bcfg={"enabled": True, "intro_cut": True})
        self.hepsi(v)
        foto = [s.i for s in v.p if s.foto]
        self.assertEqual(foto, [0, 5])

    def test_on_sahnelik_gun(self):
        data = gun_senaryosu(durak=5, devam=2)
        self.assertEqual(len(data["scenes"]), 10)
        v, _, _ = video(data, bcfg={"enabled": True, "intro_cut": True})
        self.assertEqual(v.N, 5)
        self.assertEqual(sum(1 for s in v.p if s.tur == "durak"), 5)
        self.hepsi(v)

    def test_alti_sahnelik_gun(self):
        data = gun_senaryosu(durak=3, devam=0)
        self.assertEqual(len(data["scenes"]), 6)
        v, _, _ = video(data)
        self.hepsi(v)

    def test_uzun_turkce_kelimeler(self):
        for data in (gun_senaryosu(durak=4, devam=2, uzun=True), para_senaryosu(uzun=True)):
            v, _, _ = video(data)
            self.hepsi(v)

    def test_para_ve_alinti(self):
        v, _, _ = video(para_senaryosu())
        self.assertEqual([s.tur for s in v.p], ["kanca", "sayac", "sayac", "fis", "iceriden", "cta"])
        self.assertEqual(v.p[4].alinti, "Kahvenin maliyeti fiyatının beşte biridir.")
        self.assertNotIn(4, v.sessiz, "alıntı notta yazılır, dış ses şeritte kalır")
        self.hepsi(v)

    def test_gun_akisinda_para(self):
        """Gün akışında bir sayaç sahnesi: makine yalnız o sahnede gelir ve gider."""
        data = gun_senaryosu(durak=4, devam=1)
        data["scenes"].insert(4, sahne("Günün sonunda eline yaklaşık 3 bin lira kalır.", ["ELİNE", "KALAN"],
                                       card="counter", card_value="3.000 ₺", card_label="GÜNLÜK"))
        v, _, _ = video(data)
        self.assertTrue(v.gun and v.para)
        self.assertEqual(len(v.makine_ara), 1)
        t_in, t_out, gir, cik = v.makine_ara[0]
        self.assertTrue(gir and cik)
        self.assertGreaterEqual(t_in, v.p[4].start)
        self.assertLessEqual(t_out, v.p[4].end)
        self.hepsi(v)


# ---------------------------------------------------------------- dış sesle eşleme ve hesap
class Zamanlama(unittest.TestCase):
    def test_hesap_makinesi_yuruyen_toplam(self):
        v, _, _ = video(demo("kuyumcu"))
        fis = v.p[3]
        ara = [e[2] for e in v.lcd if e[1] == "ARA TOPLAM"]
        self.assertEqual(ara, ["80.000", "158.000", "183.000", "200.000"])
        ust, deger, birim, tus, rozet = v.lcd_at(fis.end - 0.05)
        self.assertEqual((ust, deger, birim), ("AYLIK GİDER", "200.000", "₺"))
        self.assertEqual(rozet, "TAHMİNİ")
        self.assertEqual(v.lcd_at(0.1)[1], "0")
        kira = v.p[1]
        self.assertEqual(v.lcd_at(kira.end - 0.05)[:3], ("AYLIK KİRA", "80.000", "₺"))
        self.assertTrue(all(a <= b for a, b in zip(v.lcd_t, v.lcd_t[1:])))

    def test_makine_gelir_gider(self):
        """Kuyumcuda üç para sahnesi arka arkaya: makine bir kez köşeden gelir, fiş bitince geri çekilir; içeriden
        notunda ve son sahnede yok."""
        v, _, _ = video(demo("kuyumcu"))
        self.assertEqual([(g, c) for _, _, g, c in v.makine_ara], [(True, False), (False, False), (False, True)])
        s1, s3 = v.p[1], v.p[3]
        self.assertIsNone(v.makine_durumu(s1.start + 0.1), "geçiş sürerken gelmez")
        self.assertLess(v.makine_durumu(s1.start + A.OGE0 + 0.05), 1.0, "köşeden kayarak gelir")
        self.assertEqual(v.makine_durumu(s1.end - 0.01), 1.0)
        self.assertLess(v.makine_durumu(s3.end - 0.1), 1.0, "geri çekilir")
        self.assertIsNone(v.makine_durumu(v.p[4].start + 1.0))

    def test_buyuk_sayi_sayar_ve_oturur(self):
        v, _, _ = video(demo("kuyumcu"))
        s = v.p[1]
        sayi = next(o for o in v.ogeler if isinstance(o, A.SayiOge) and o.gorunur(1))
        self.assertEqual(sayi.deger, "80.000 ₺")
        self.assertAlmostEqual(sayi.t_land, v.olay[1])
        kira = next(i for i in range(s.a, s.b) if v.words[i].text == "80")
        self.assertGreaterEqual(sayi.t_land, v.words[kira].start, "sayı söylenince oturur")
        self.assertGreaterEqual(sayi.t_land - sayi.sayim, s.start + A.OGE0 - 0.01)
        cagri = []
        with mock.patch.object(A.SayiOge, "yazi", lambda self, m: cagri.append(m) or (Image.new("RGBA", (4, 4)),
                                                                                       (0, 0))):
            for t in (sayi.t_land - sayi.sayim * 0.5, sayi.t_land + 0.3):
                sayi.draw(v, Image.new("RGBA", (K.W, K.H)), t)
        self.assertNotEqual(cagri[0], "80.000 ₺")
        self.assertEqual(cagri[-1], "80.000 ₺")

    def test_icerden_notu_sozle_yazilir(self):
        v, _, _ = video(demo("elektrikci"))
        s = v.p[5]
        self.assertEqual(v.sessiz.get(5), s.a, "notta yazılan dış ses şeritte tekrar edilmez")
        notu = next(o for o in v.ogeler if isinstance(o, A.NotOge))
        ilk, son = notu.satirlar[0], notu.satirlar[-1]
        self.assertEqual(ilk.reveal(v.words[s.a].start - 0.2), 0.0)
        self.assertIsNone(son.reveal(v.words[s.b - 1].end + 0.05))
        metin = " ".join(o.yazi.text for o in notu.satirlar)
        self.assertEqual(metin, " ".join(w.text for w in v.words[s.a:s.b]))

    def test_son_sahne(self):
        v, _, _ = video(demo("elektrikci"))
        s = v.p[-1]
        sen = next(i for i in range(s.a, s.b) if v.words[i].text == "Sen")
        self.assertEqual(v.sessiz.get(s.i), sen)
        yorum = next(i for i in range(s.a, s.b) if v.words[i].text == "Yorumlara")
        etiket = next(o for o in v.ogeler if isinstance(o, A.KagitOge) and o.nabiz)
        self.assertAlmostEqual(etiket.t0, v.words[yorum].start - 0.08)
        baslik = v.basliklar[s.i]
        self.assertEqual(baslik.lines, A.CTA_BASLIK)
        self.assertIsNotNone(baslik.halka, "SEN mavi tükenmezle halkalanır")

    def test_damga_sahnede(self):
        """Her saatli durağın saati ya damga (resmin üstünde) ya da afişin kendisidir."""
        v, _, _ = video(demo("elektrikci"))
        damgali = {min(o.sahneler) for o in v.ogeler if isinstance(o, A.DamgaOge)}
        for s in v.p:
            if s.tur == "durak":
                self.assertTrue(s.i in damgali or v.afis_metni(s) == (s.saat, "damga"), s.saat)

    def test_gecisler(self):
        """Sahne geçişleri sırayla kayma, bant çevirme ve makas kesmesi; eski baskı geçiş boyunca görünür."""
        v, _, _ = video(demo("elektrikci"))
        self.assertEqual([v.gecis_turu(i) for i in range(1, 7)], ["kayma", "bant", "kesme"] * 2)
        for si in (1, 2, 3):
            s = v.p[si]
            with mock.patch.object(A.AjandaVideo, "eski_katman", wraps=v.eski_katman) as eski:
                v.frame(s.start + 0.1, grain=False)
                self.assertTrue(eski.called, si)
                eski.reset_mock()
                v.frame(s.start + A.CUT + 0.1, grain=False)
                self.assertFalse(eski.called, si)

    def test_belirlenimci(self):
        a, _, _ = video(demo("kuyumcu"), bcfg={"enabled": True, "intro_cut": True})
        b, _, _ = video(demo("kuyumcu"), bcfg={"enabled": True, "intro_cut": True})
        for t in (0.3, 7.0, 16.0, 24.0):
            self.assertEqual(hashlib.sha256(a.frame(t).tobytes()).hexdigest(),
                             hashlib.sha256(b.frame(t).tobytes()).hexdigest(), t)

    def test_hareket(self):
        """Resim durmaz: aynı sahnenin iki anında baskının içeriği farklı (Ken Burns / paralaks)."""
        v, _, _ = video(tesla_senaryosu())
        for si in (0, 1, 7):
            b = v.baskilar[si]
            self.assertNotEqual(b.icerik(0.1).tobytes(), b.icerik(0.9).tobytes(), (si, b.tur))


# ---------------------------------------------------------------- görsel seçimi ve pipeline
class Gorsel(unittest.TestCase):
    def test_istenmeyen(self):
        from shortgen import images as I
        self.assertEqual(I.istenmeyen("Wardenclyffe Tower Shoreham", "File:Wardenclyffe Tower; Shoreham Map.JPG"),
                         "harita")
        self.assertEqual(I.istenmeyen("Westinghouse", "File:Westinghouse logo.png"), "logo")
        self.assertEqual(I.istenmeyen("Ankara", "File:Coat of arms of Ankara.png"), "arma")
        self.assertEqual(I.istenmeyen("induction motor", "File:Induction motor diagram.png"), "şema")
        for q, t in (("Chicago 1893 map", "File:Map of the World's Columbian Exposition.jpg"),
                     ("Westinghouse logo", "File:Westinghouse logo.png"),
                     ("Wardenclyffe Tower 1904", "File:Wardenclyffe Tower 1904.jpg Tesla Wardenclyffe Shoreham"),
                     ("Hotel New Yorker", "File:New Yorker Hotel.jpg Photographs by Ermell Buildings in Manhattan"),
                     ("Nikola Tesla", "File:Tesla Mapping Kit.jpg")):
            self.assertEqual(I.istenmeyen(q, t), "", (q, t))

    def test_find_image_haritayi_atlar(self):
        """Wikimedia aramasında harita ilk sırada gelse de lisansı uygun fotoğraf seçilir; lisans kuralı aynen kalır
        (CC BY-NC fotoğraf yine reddedilir)."""
        from shortgen import images as I

        def sayfa(i, baslik, lisans, aciklama=""):
            return {"index": i, "title": "File:" + baslik, "imageinfo": [{
                "url": f"https://upload.example/{i}.jpg", "thumburl": f"https://upload.example/{i}.jpg",
                "descriptionurl": f"https://commons.example/{i}", "mime": "image/jpeg", "width": 1200,
                "extmetadata": {"LicenseShortName": {"value": lisans}, "ImageDescription": {"value": aciklama},
                                "Artist": {"value": "Yazar"}, "Categories": {"value": "Wardenclyffe Tower"}}}]}
        cevap = {"query": {"pages": {
            "1": sayfa(1, "Wardenclyffe Tower; Shoreham Map.JPG", "CC BY-SA 4.0"),
            "2": sayfa(2, "Wardenclyffe Tower NC.jpg", "CC BY-NC 2.0"),
            "3": sayfa(3, "Wardenclyffe Tower 1904.jpg", "Public domain")}}}

        class Cevap:
            def __init__(self, veri=None):
                self.veri, self.content = veri, b"\xff\xd8resim"

            def json(self):
                return self.veri

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(I, "_get", side_effect=lambda url, **kw: Cevap(cevap if url == I.API else None)):
            yol, kunye = I.find_image("Wardenclyffe Tower Shoreham", Path(tmp))
            self.assertEqual(kunye.title, "Wardenclyffe Tower 1904.jpg")
            self.assertEqual(kunye.license, "Public domain")
            self.assertTrue(yol.exists())

    def test_pipeline_cizimi_verir(self):
        """pipeline.build bu şablonda fotoğrafı olmayan sahnenin çizimini spec.sprite'a, sahnenin bütün alanlarını
        spec.card'a, fotoğrafın künyesini card['credit']'e koyar (ajanda büyük çizer)."""
        data = tesla_senaryosu()
        for sc in data["scenes"]:
            sc.pop("image", None)
            sc.pop("credit", None)
        data["scenes"][0].update(image_queries=["local:demo/eileen_collins_nasa.jpg"], image_mode="full")
        data["scenes"][3].update(image_queries=["Tesla induction motor 1888"], image_mode="framed")
        data["scenes"][3]["illustration"] = "an old patent drawing of an electric motor"
        script = ShortScript.model_validate(data)
        cizim = REPO / "demo/ajanda/dukkan.png"
        yakalanan = {}

        def ciz(istek, konu, klasor):
            yakalanan["istek"] = dict(istek)
            return {i: cizim for i in istek}

        def bul(sorgular, cache, used):
            return None

        def kur(specs, words, video_, mp3, music, meta):
            yakalanan["specs"] = specs
            return video_
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(P.images, "find_any", side_effect=bul), \
                mock.patch.object(P.illustrate, "draw_scenes", side_effect=ciz), \
                mock.patch.object(A, "render", side_effect=kur):
            P.build(script, Path(tmp) / "out", use_voice=False, music=None, template="ajanda")
        specs = yakalanan["specs"]
        self.assertEqual(specs[0].image, REPO / "demo/eileen_collins_nasa.jpg")
        self.assertIn(3, yakalanan["istek"], "fotoğrafı bulunamayan sahnenin çizimi istenir")
        self.assertEqual(specs[3].sprite, cizim)
        self.assertIsNone(specs[3].image)
        self.assertEqual(specs[2].card["card_value"], "2 $")
        v = A.AjandaVideo(specs, [w for sp in specs for w in sp.words], {"script": script.model_dump()}, BCFG)
        self.assertEqual(v.baskilar[3].tur, "cizim")
        self.assertEqual(v.resim_kutusu(3), A.FOTO)


# ---------------------------------------------------------------- şablon seçimi ve uçtan uca
class Inceleme(unittest.TestCase):
    def test_son_sayfada_yetim_kelime_kalmaz(self):
        """Dış ses şeridinin son sayfası tek başına 1-3 kelime olmaz ('lira.', 'eder.'); sayfa en çok iki satır."""
        metinler = [sc["narration"] for ad in DEMO for sc in demo(ad)["scenes"]] + [
            sc["narration"] for sc in tesla_senaryosu()["scenes"]] + [
            "Çarşıda küçük bir dükkânın kirası ayda yaklaşık 80 bin lira.",
            "Güvenlik, sigorta, elektrik ve muhasebe de eklenince ayda 200 bin lira eder.",
            "İki çalışanın işverene maliyeti, asgari ücretle bile ayda 78 bin lira."]
        for m in metinler:
            m = m.split(" Sen olsan")[0]
            if m.startswith("Sen olsan"):
                continue
            ws = [Word(w, i, i + 0.5) for i, w in enumerate(m.split())]
            sp = A.Anlati(ws, 0, len(ws), A.ANLATI)
            if len(sp.pages) > 1:
                self.assertGreater(sp.pages[-1][1] - sp.pages[-1][0], A.Anlati.YETIM, m)
            for lines in sp.lines.values():
                self.assertLessEqual(len(lines), 2, m)
                for L in lines:
                    self.assertLessEqual(K.tw(" ".join(ws[i].text for i in L), "courier", sp.size),
                                         A.ANLATI[2] - A.ANLATI[0] + 0.5, m)

    def test_kesmede_eski_sahnenin_durumu(self):
        """Yeni başlık gelene dek (YENI0) dış ses ve DURAK sırası eski sahnenindir."""
        v, specs, words = video(demo("elektrikci"))
        cagri = []
        with mock.patch.object(A.AjandaVideo, "anlati", lambda self, img, si, t: cagri.append(("a", si))), \
                mock.patch.object(A.AjandaVideo, "ilerleme", lambda self, img, si, t: cagri.append(("i", si))):
            for si in range(2, len(v.p)):
                s0 = v.p[si].start
                cagri.clear()
                v.frame(s0 + A.YENI0 * 0.5, grain=False)
                self.assertEqual(sorted(cagri), [("a", si - 1), ("i", si - 1)])
                cagri.clear()
                v.frame(s0 + A.YENI0 + 0.02, grain=False)
                self.assertEqual(sorted(cagri), [("a", si), ("i", si)])

    def test_sablon_istemi(self):
        t = json.loads((REPO / "templates" / "ajanda.json").read_text(encoding="utf-8"))
        for k in ("07:30", "1884", "interstitial", "quote", "illustration", "image_queries", "portrait", "Harita"):
            self.assertIn(k, t["istem"])
        from shortgen import script as S
        self.assertIn("kart ya da ajanda şablonuyla", S.OLSAYDIN_RULES)


class Secim(unittest.TestCase):
    def test_yalniz_elle_secilir(self):
        t = json.loads((REPO / "templates/ajanda.json").read_text(encoding="utf-8"))
        self.assertEqual((t["renderer"], t["yapi"]), ("ajanda", "olsaydin"))
        self.assertEqual(P.sablon_renderer("ajanda"), "ajanda")
        self.assertEqual(P.sablon_yapisi("ajanda"), "olsaydin")
        self.assertIn("ajanda", P.kendi_secimli(), "Claude'un şablon listesine girmez")
        m = json.loads((REPO / "templates/eslesme.json").read_text(encoding="utf-8"))
        self.assertEqual(m["yapi_sablon"]["olsaydin"], "kart", "otomatik seçim değişmez")
        s = load_script(DEMO["kuyumcu"])
        self.assertEqual(P.pick_template(s), "kart")
        self.assertEqual(P.pick_template(s, "ajanda"), "ajanda")

    def test_uctan_uca(self):
        """Geçici kökte pipeline: video, metadata (rakamlar yaklaşık uyarısı), history.jsonl yalnız geçici kökte."""
        gecmis = REPO / "history.jsonl"
        once = gecmis.read_bytes() if gecmis.exists() else None
        with tempfile.TemporaryDirectory() as tmp:
            kok = Path(tmp) / "kok"
            shutil.copytree(REPO / "shortgen", kok / "shortgen", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(REPO / "templates", kok / "templates")
            shutil.copytree(REPO / "demo/ajanda", kok / "demo/ajanda")
            shutil.copy(REPO / "brand.json", kok / "brand.json")
            env = dict(os.environ, SERIES_LABEL="0", AUTO_TREND="0", PYTHONDONTWRITEBYTECODE="1")
            for k in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY"):
                env.pop(k, None)
            r = subprocess.run([sys.executable, "-B", "-m", "shortgen.pipeline", "--script",
                                "demo/ajanda/kuyumcu.json", "--no-voice", "--template", "ajanda", "--out",
                                str(Path(tmp) / "out")], cwd=kok, env=env, capture_output=True, text=True,
                               timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            self.assertIn("Şablon: ajanda", r.stdout)
            mp4 = list((Path(tmp) / "out").glob("*/video.mp4"))
            self.assertEqual(len(mp4), 1)
            meta = json.loads((mp4[0].parent / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["template"], "ajanda")
            self.assertNotIn("rakamsiz", meta)
            sure = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                         "default=nw=1:nk=1", str(mp4[0])], capture_output=True,
                                        text=True).stdout.strip())
            self.assertTrue(30.0 <= sure <= 35.5, sure)
            kare = Path(tmp) / "kare.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "20", "-i", str(mp4[0]), "-frames:v", "1",
                            str(kare)], check=True)
            im = Image.open(kare).convert("RGB")
            self.assertEqual(im.size, (1080, 1920))
            self.assertGreater(len(set(im.resize((108, 192)).getdata())), 50, "boş kare değil")
            self.assertTrue((kok / "history.jsonl").exists())
        self.assertEqual(gecmis.read_bytes() if gecmis.exists() else None, once, "depodaki history.jsonl değişmez")


if __name__ == "__main__":
    unittest.main(verbosity=2)
