#!/usr/bin/env python3
"""Ajanda şablonunun (Ya Sen Olsaydın?, shortgen/ajanda.py) testleri. Ağ yok, ses yok, Claude çağrısı yok.

- tarih, saat ve sahne planı (kanca, gün akışı durakları, devam notu, sayaç, fiş, içeriden notu, son sahne),
- yerleşim değişmezleri: karenin bütün içerik katmanları (gölgeler dahil) güvenli alanda (x ≤ 935, y 170-1540),
  elle yazılan satırlar birbirine, başlık Makas'a, polaroid yazılara binmez; uzun Türkçe kelimeler taşmaz;
  6-10 sahnelik senaryolar; fotoğraf (künye çipi) ve alıntı,
- hesap makinesinin yürüyen toplamı, içeriden notunun ve son sahnenin dış sesle eşlenmesi, belirlenimcilik,
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
    """Karelerdeki bütün katman bindirmeleri (kırpılmadan önceki alfa kutusu, ölçek dahil): [(an, kutu)]."""
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
                kayit.append((simdi[0], (ox + bb[0] * kx, oy + bb[1] * kx, ox + bb[2] * kx, oy + bb[3] * kx)))
        return asil(img, layer, x, y, k=k, alpha=alpha, clip=clip, anchor=anchor)

    with mock.patch.object(K, "put", put):
        for t in ts:
            simdi[0] = t
            v.frame(t, grain=False)
    return kayit


def kesisir(a, b, pay=1.0) -> bool:
    return a[0] < b[2] - pay and b[0] < a[2] - pay and a[1] < b[3] - pay and b[1] < a[3] - pay


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
        """meta'da yayın tarihi yoksa sayfaya somut gün basılmaz (çizim günü yayın günü değildir): gün akışında
        'BİR İŞ GÜNÜ · SAAT SAAT', para gününde 'BİR AYIN HESABI'."""
        for ad, beklenen in (("elektrikci", ("BİR", "İŞ GÜNÜ", "SAAT SAAT", "")),
                             ("kuyumcu", ("BİR", "AYIN", "HESABI", ""))):
            v, specs, words = video(demo(ad))
            meta = dict(v.meta)
            meta.pop("tarih")
            v2 = A.AjandaVideo(specs, words, meta, BCFG)
            self.assertEqual(v2.tarih, beklenen)
            metin = " ".join(v2.tarih)
            for gun in A.GUNLER:
                self.assertNotIn(gun, metin)

    def test_saat(self):
        self.assertEqual(A.saat_of("07:30"), ("07:30", 450))
        self.assertEqual(A.saat_of("7.05"), ("07:05", 425))
        self.assertEqual(A.saat_of("SAAT 17:30"), ("17:30", 1050))
        self.assertIsNone(A.saat_of(""))
        self.assertIsNone(A.saat_of("%25"))
        self.assertIsNone(A.saat_of("1.200.000"))

    def test_cumle(self):
        self.assertEqual(A.cumle("İLK ARIZA"), "İlk arıza")
        self.assertEqual(A.cumle("ŞANTİYEDE  PANO"), "Şantiyede pano")
        self.assertEqual(A.cumle("IŞIK"), "Işık")

    def test_elektrikci_plani(self):
        v, _, _ = video(demo("elektrikci"))
        self.assertEqual([s.tur for s in v.p], ["kanca", "durak", "durak", "serbest", "durak", "iceriden", "durak",
                                                "cta"])
        self.assertEqual([s.saat for s in v.p if s.tur == "durak"], ["07:30", "09:00", "13:00", "17:30"])
        self.assertEqual(v.N, 4)
        self.assertTrue(v.gun)
        self.assertFalse(v.para)
        self.assertIsNone(v.hm, "para yokken hesap makinesi çizilmez")

    def test_kuyumcu_plani(self):
        v, _, _ = video(demo("kuyumcu"))
        self.assertEqual([s.tur for s in v.p], ["kanca", "sayac", "sayac", "fis", "iceriden", "cta"])
        self.assertEqual(v.N, 3)
        self.assertFalse(v.gun)
        self.assertTrue(v.para)
        self.assertIsNotNone(v.hm)

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
        x0s, y0s, x1s, y1s = K.SAFE[0], K.SAFE[1], K.SAFE[2], K.SAFE[3]
        for t, (x0, y0, x1, y1) in kayitli_kareler(v, ts or anlar(v)):
            # makas kesmesinde (kart.card_cut) eski başlığın üst parçası sola kayıp ekranın sol kenarından çıkabilir;
            # solda platform arayüzü yok, sağ / üst / alt sınırlar her karede geçerli
            kesme = any(s.i > 0 and s.start <= t < s.start + A.CUT for s in v.p)
            self.assertGreaterEqual(x0, (x0s - 40) if kesme else (x0s - 0.5), (t, (x0, y0, x1, y1)))
            self.assertLessEqual(x1, x1s + 0.5, (t, (x0, y0, x1, y1)))
            self.assertGreaterEqual(y0, y0s - 0.5, (t, (x0, y0, x1, y1)))
            self.assertLessEqual(y1, y1s + 0.5, (t, (x0, y0, x1, y1)))

    def binmez(self, v):
        """Her sahnenin sonunda: elle yazılan satırlar birbirine, polaroide ve Makas'a binmez; başlık Makas'a binmez."""
        makas = (A.MAKAS_XY[0] - 120, A.MAKAS_XY[1] - 150, A.MAKAS_XY[0] + 80, A.MAKAS_XY[1] + 70)
        for s in v.p:
            t = s.end - 0.03
            yazilar = [o.yazi.ink_box(o.x, o.y, o.anchor) for o in v.ogeler
                       if isinstance(o, A.YaziOge) and o.gorunur(s.i)]
            resimler = [(o.cx - o.im.width / 2, o.cy - o.im.height / 2, o.cx + o.im.width / 2, o.cy + o.im.height / 2)
                        for o in v.ogeler if isinstance(o, A.ResimOge) and o.gorunur(s.i)]
            for i, a in enumerate(yazilar):
                self.assertLessEqual(a[2], A.X1 + 2, (s.i, a))
                self.assertGreaterEqual(a[0], A.X0 - 10, (s.i, a))
                self.assertGreaterEqual(a[1], A.ICERIK_Y0 - 80, (s.i, a))
                self.assertLessEqual(a[3], v.alt + 14, (s.i, a))
                for b in yazilar[i + 1:]:
                    self.assertFalse(kesisir(a, b, 3), (s.i, a, b))
                for r in resimler:
                    self.assertFalse(kesisir(a, r, 3), (s.i, "polaroid", a, r))
                self.assertFalse(kesisir(a, makas), (s.i, "Makas", a))
            for o in v.ogeler:
                if isinstance(o, A.BaslikOge) and o.gorunur(s.i):
                    bb = o.text.getchannel("A").getbbox()
                    self.assertLessEqual(o.region[0] + bb[2], A.BAS_X1 + 4, (s.i, o.lines))
                    self.assertGreaterEqual(o.region[1] + bb[1], A.SIRA_CY + 30, (s.i, o.lines))
                    self.assertLessEqual(o.region[1] + bb[3], A.ANLATI[1] - 4, (s.i, o.lines))
            v.frame(t, grain=False)

    def test_elektrikci(self):
        v, _, _ = video(demo("elektrikci"))
        self.guvenli(v)
        self.binmez(v)

    def test_kuyumcu(self):
        v, _, _ = video(demo("kuyumcu"))
        self.guvenli(v)
        self.binmez(v)

    def test_on_sahnelik_gun(self):
        data = gun_senaryosu(durak=5, devam=2)
        self.assertEqual(len(data["scenes"]), 10)
        v, _, _ = video(data, bcfg={"enabled": True, "intro_cut": True})
        self.assertEqual(v.N, 5)
        self.assertEqual(sum(1 for s in v.p if s.tur == "durak"), 5)
        self.guvenli(v, anlar(v, 0.5))
        self.binmez(v)
        foto = [o for o in v.ogeler if isinstance(o, A.ResimOge) and v.p[min(o.sahneler)].foto]
        self.assertEqual(len(foto), 1, "fotoğraf polaroid olur")

    def test_alti_sahnelik_gun(self):
        data = gun_senaryosu(durak=3, devam=0)
        self.assertEqual(len(data["scenes"]), 6)
        v, _, _ = video(data)
        self.guvenli(v, anlar(v, 0.5))
        self.binmez(v)

    def test_uzun_turkce_kelimeler(self):
        for data in (gun_senaryosu(durak=4, devam=2, uzun=True), para_senaryosu(uzun=True)):
            v, _, _ = video(data)
            self.guvenli(v, anlar(v, 0.5))
            self.binmez(v)
            for o in v.ogeler:
                if isinstance(o, A.BaslikOge):
                    self.assertTrue(all(K.tw(L, "anton", o.size) <= A.BAS_X1 - A.X0 for L in o.lines), o.lines)

    def test_para_ve_alinti(self):
        v, _, _ = video(para_senaryosu())
        self.assertEqual([s.tur for s in v.p], ["kanca", "sayac", "sayac", "fis", "iceriden", "cta"])
        self.assertEqual(v.p[4].alinti, "Kahvenin maliyeti fiyatının beşte biridir.")
        self.assertNotIn(4, v.sessiz, "alıntı notta yazılır, dış ses altta kalır")
        self.guvenli(v, anlar(v, 0.5))
        self.binmez(v)

    def test_gun_akisinda_para(self):
        """Gün akışında bir sayaç sahnesi: makine çizilir, durak satırları makinenin üstünde kalır."""
        data = gun_senaryosu(durak=4, devam=1)
        data["scenes"].insert(4, sahne("Günün sonunda eline yaklaşık 3 bin lira kalır.", ["ELİNE", "KALAN"],
                                       card="counter", card_value="3.000 ₺", card_label="GÜNLÜK"))
        v, _, _ = video(data)
        self.assertTrue(v.gun and v.para)
        self.assertLessEqual(max(v.icerik), A.CALC_TOP)
        self.guvenli(v, anlar(v, 0.5))
        self.binmez(v)


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

    def test_icerden_notu_sozle_yazilir(self):
        v, _, _ = video(demo("elektrikci"))
        s = v.p[5]
        self.assertEqual(v.sessiz.get(5), s.a, "notta yazılan dış ses alttaki satırda tekrar edilmez")
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
        etiket = next(o for o in v.ogeler if isinstance(o, A.EtiketOge))
        self.assertAlmostEqual(etiket.t0, v.words[yorum].start - 0.08)
        baslik = next(o for o in v.ogeler if isinstance(o, A.BaslikOge) and o.gorunur(s.i))
        self.assertEqual(baslik.lines, A.CTA_BASLIK)
        self.assertIsNotNone(baslik.halka, "SEN mavi tükenmezle halkalanır")

    def test_duraklar_saat_satirinda(self):
        v, _, _ = video(demo("elektrikci"))
        for s in v.p:
            if s.tur == "durak":
                k, y = v.giris[s.i]
                self.assertEqual(k, v.satir(s.dakika), s.saat)
                self.assertEqual(v.cizgi[[yy for yy, _ in v.cizgi].index(v.icerik[k])][1], s.saat[:2])

    def test_belirlenimci(self):
        a, _, _ = video(demo("kuyumcu"), bcfg={"enabled": True, "intro_cut": True})
        b, _, _ = video(demo("kuyumcu"), bcfg={"enabled": True, "intro_cut": True})
        for t in (0.3, 7.0, 16.0, 24.0):
            self.assertEqual(hashlib.sha256(a.frame(t).tobytes()).hexdigest(),
                             hashlib.sha256(b.frame(t).tobytes()).hexdigest(), t)


# ---------------------------------------------------------------- şablon seçimi ve uçtan uca
class Inceleme(unittest.TestCase):
    def test_son_sayfada_yetim_kelime_kalmaz(self):
        """Dış ses satırının son sayfası tek başına 1-3 kelime olmaz ('lira.', 'eder.'); sayfa en çok iki satır."""
        metinler = [sc["narration"] for ad in DEMO for sc in demo(ad)["scenes"]] + [
            "Çarşıda küçük bir dükkânın kirası ayda yaklaşık 80 bin lira.",
            "Güvenlik, sigorta, elektrik ve muhasebe de eklenince ayda 200 bin lira eder.",
            "İki çalışanın işverene maliyeti, asgari ücretle bile ayda 78 bin lira."]
        for m in metinler:
            m = m.split(" Sen olsan")[0]         # son sahnede soru dış ses satırına yazılmaz (başlık sorudur)
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
        """Makas eski başlığı kesip atana dek (YENI0) dış ses ve DURAK sırası eski sahnenindir."""
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

    def test_para_sayfasi_saatsiz(self):
        """Para gününde (gider defteri) basılı saat sütunu yok; gün akışında var."""
        v, _, _ = video(demo("kuyumcu"))
        self.assertFalse(v.saatli)
        v2, _, _ = video(demo("elektrikci"))
        self.assertTrue(v2.saatli)

    def test_sablon_istemi(self):
        t = json.loads((REPO / "templates" / "ajanda.json").read_text(encoding="utf-8"))
        for k in ("07:30", "interstitial", "quote", "illustration"):
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
