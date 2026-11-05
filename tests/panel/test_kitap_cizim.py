#!/usr/bin/env python3
"""Bir Kitap Bir Dakika (kitap şablonu, shortgen/kitap.py) çizim testleri (ağ yok, ses yok; her kelime sabit 0,4 sn):

- telif: kamu malı sınırı (FSEK, ölümden sonra 70 yıl), kamu malı olmayan ya da ölüm yılı bilinmeyen eserde ilk cümle
  sayfası yerine KÜNYE sayfası (alıntı hiç çizilmez), kamu malı eserde alıntının en az 40 px olması,
- plan: bölüm işaretleri (varsayılanlar, geri gitmeme, ilk sahne giriş, son sahne soru), aynı bölümdeki sahnelerin
  aynı sayfa çiftinde kalması, sayfa metni boşsa dış sesten kısa parça,
- sağ sayfa metni: 40-46 px, sütuna sığan dengeli satırlar (tek kelimelik satır yok), fosforlu kalemin vurguyu satır
  satır sarması ve yalnız vurgu söylendikten sonra çizilmesi,
- zaman çizelgesi: evrelerin sırası, kapağın ilk cümleden önce açılması, kelimelerin dış sesle yazılması, OKUDUN MU?
  etiketinin söylendiği anda belirmesi, her bölümün her anında kare çizilmesi,
- yerleşim: yazı kutularının güvenli alanda kalması (x <= 935, y 240-1540), sayfa çevrilirken sekme sırasının hiç
  örtülmemesi, kütüphane kartının yalnız kanca ve son karede olması, seri etiketinin sığması,
- amblemler ve kapak renkleri: 16 amblemin hepsi çizilir, bilinmeyen anahtar monogram olur, kapak yazısı okunur,
- birleşim: kitap şablonu Claude'a önerilmez, kitap kalıbı kitap şablonuna gider, pipeline.build çiziciye bölüm, sayfa
  metni, vurgu ve künyeyi geçirir; diğer şablonların dosyaları ve çizicileri bu daldan önceki commit'tekiyle aynı.

    python -B tests/panel/test_kitap_cizim.py

Diğer şablonların karşılaştırma tabanı KITAP_CIZIM_TABAN (varsayılan: bu dalın ayrıldığı commit); taban depoda yoksa
o test atlanır.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402

from shortgen import kitap as KT, pipeline as P, render, script as S  # noqa: E402
from shortgen.voice import Word  # noqa: E402

DEMO = REPO / "demo/kitap/ornek_donusum.json"
TABAN = os.environ.get("KITAP_CIZIM_TABAN", "35bcd8d")
ADIM = 0.4                                      # kelime başına süre
BCFG = {"enabled": True, "handle": "@bilgimakasi", "intro_cut": True}
SAFE_X, SAFE_Y0, SAFE_Y1 = 935, 240, 1540


def demo() -> dict:
    return json.loads(DEMO.read_text(encoding="utf-8"))


def kur(data: dict | None = None, kitap: dict | None = None, yil: int | None = 2026, adim: float = ADIM,
        sablon: dict | None = None):
    """Senaryodan pipeline.build'in kurduğu sahneler ve video: (sahneler, kelimeler, meta, KitapVideo)."""
    data = data or demo()
    words, specs, t = [], [], 0.0
    for sc in data["scenes"]:
        ws = [Word(w, t + j * adim, t + j * adim + adim * 0.8) for j, w in enumerate(sc["narration"].split())]
        t += len(ws) * adim + 0.15
        spec = render.SceneSpec(narration=sc["narration"], kicker=sc.get("kicker", ""),
                                headline=list(sc.get("headline") or []), highlight_line=sc.get("highlight_line", -1),
                                strike=[], theme="paper", image_mode="none", image=None, icon="none", sprite=None,
                                motion="none", drawn=True)
        spec.words = ws
        spec.start = ws[0].start
        spec.card = {"bolum": sc.get("kitap_bolum", ""), "sayfa": sc.get("sayfa_metni", ""),
                     "vurgu": sc.get("vurgu", ""), "mascot": sc.get("mascot", "auto")}
        words += ws
        specs.append(spec)
    specs[0].start = 0.0
    for a, b in zip(specs, specs[1:]):
        b.start = max(b.start - 0.12, a.start + 0.5)
        a.end = b.start
    specs[-1].end = words[-1].end + 0.35
    meta = {"topic": data["topic"], "title": data.get("title", ""), "structure": "kitap",
            "category": data.get("category", ""), "kitap": copy.deepcopy(kitap if kitap is not None else data["kitap"]),
            "sablon": sablon if sablon is not None else
            json.loads((REPO / "templates" / "kitap.json").read_text(encoding="utf-8"))}
    return specs, words, meta, KT.KitapVideo(specs, words, meta, BCFG, yil=yil)


def anlar(v: KT.KitapVideo, words, n: int = 36) -> list[float]:
    """Her evreden kareler: eşit aralıklı anlar + her geçişin içi + son."""
    end = words[-1].end + 0.3
    ts = {round(end * k / n, 2) for k in range(n)}
    for g in v.gecis:
        ts.update({round(g + d, 2) for d in (0.1, 0.3, 0.45, 0.6, 0.95)})
    ts.update({0.0, round(end, 2)})
    return sorted(ts)


def kutu_ici(box) -> bool:
    x0, y0, x1, y1 = box
    return x0 >= 0 and x1 <= SAFE_X and y0 >= SAFE_Y0 and y1 <= SAFE_Y1


# ---------------------------------------------------------------- telif
class Telif(unittest.TestCase):
    def test_kamu_mali_siniri(self):
        """2026'da en geç 1955'te ölmüş yazarın eseri kamu malıdır; ölüm yılı 0 (yaşıyor / bilinmiyor) değildir."""
        self.assertTrue(KT.kamu_mali(1955, 2026))
        self.assertFalse(KT.kamu_mali(1956, 2026))
        self.assertTrue(KT.kamu_mali(1924, 2026))
        self.assertTrue(KT.kamu_mali("1924", 2026))
        self.assertFalse(KT.kamu_mali(0, 2026))
        self.assertFalse(KT.kamu_mali(-3, 2026))
        self.assertFalse(KT.kamu_mali("bilinmiyor", 2026))
        self.assertTrue(KT.kamu_mali(1956, 2027))

    def test_kamu_mali_olmayan_eserde_kunye(self):
        """İlk cümle verilmiş olsa da yazar sınırdan sonra öldüyse ya da ölüm yılı yoksa alıntı hiç çizilmez."""
        kb = dict(demo()["kitap"], baslik="Kürk Mantolu Madonna", yazar="Sabahattin Ali", yil=1943, tur="roman",
                  ozgun_dil="Türkçe", amblem="kalp", kapak_rengi="lacivert",
                  ilk_cumle="Bu, korunan bir eserden alınmış gibi duran bir deneme cümlesidir.")
        for olum in (1948, 0):
            with self.subTest(olum=olum):
                specs, words, meta, v = kur(kitap=dict(kb, yazar_olum=olum), yil=2015)
                self.assertEqual(v.kb["ilk_cumle"], "")
                self.assertFalse(v.alinti)
                self.assertEqual(v.sekme_adlari[0], KT.KUNYE)
                self.assertEqual(v._sol_tur(v.bolumler[0]), "kunye")
                with mock.patch.object(KT.KitapVideo, "_sol_alinti", side_effect=AssertionError("alıntı çizildi")):
                    for t in (0.0, v.t_ac + 0.5, v.gecis[1] - 0.4, v.gecis[1] + 0.5):
                        v.frame(t, grain=False)

    def test_kamu_mali_eserde_ilk_cumle(self):
        specs, words, meta, v = kur()
        self.assertTrue(v.alinti)
        self.assertEqual(v.sekme_adlari[0], "İLK CÜMLE")
        self.assertEqual(v._sol_tur(v.bolumler[0]), "alinti")
        v.frame(v.gecis[1] - 0.5, grain=False)
        self.assertGreaterEqual(v.alinti_px, 40, "ilk cümle en az 40 px")
        self.assertNotIn("KANCA", " ".join(v.sekme_adlari))

    def test_cok_uzun_ilk_cumle_kucuk_yazilmaz(self):
        kb = dict(demo()["kitap"], ilk_cumle=" ".join(["uzun"] * 120))
        specs, words, meta, v = kur(kitap=kb)
        v.sol_sayfa(0)
        self.assertEqual(v.alinti_px, 40)

    def test_kitap_bilgisi_savunmaci(self):
        """Künye eksik, alanlar yanlış türde ya da model nesnesi olarak gelse de çizilir."""
        kb = KT.kitap_bilgisi({"topic": "Bir Konu"})
        self.assertEqual((kb["baslik"], kb["kapak_rengi"], kb["ilk_cumle"]), ("Bir Konu", "kirmizi", ""))
        model = types.SimpleNamespace(baslik="Dönüşüm", yazar="Franz Kafka", yil="1915", tur="uzun öykü",
                                      ozgun_dil="Almanca", yazar_olum=1924, ilk_cumle="Bir  cümle.", amblem="kapi",
                                      kapak_rengi="mor")
        kb = KT.kitap_bilgisi({"kitap": model}, yil=2026)
        self.assertEqual((kb["yil"], kb["kapak_rengi"], kb["ilk_cumle"]), (1915, "kirmizi", "Bir cümle."))
        dump = types.SimpleNamespace(model_dump=lambda: {"baslik": "X", "yazar_olum": 1990, "ilk_cumle": "Y."})
        self.assertEqual(KT.kitap_bilgisi({"kitap": dump}, yil=2026)["ilk_cumle"], "")
        data = demo()
        specs, words, meta, v = kur(data, kitap={})
        v.frame(0.0, grain=False)
        v.frame(v.gecis[1] + 1.0, grain=False)


# ---------------------------------------------------------------- plan
class Plan(unittest.TestCase):
    def isaret(self, bolumler: list[str]) -> list[str]:
        specs = [types.SimpleNamespace(card={"bolum": b}) for b in bolumler]
        return KT.bolum_isaretleri(specs)

    def test_varsayilan_bolumler(self):
        self.assertEqual(self.isaret([""]), ["giris"])
        self.assertEqual(self.isaret(["", ""]), ["giris", "soru"])
        self.assertEqual(self.isaret([""] * 3), ["giris", "konu", "soru"])
        self.assertEqual(self.isaret([""] * 5), ["giris", "konu", "fikir", "bilgi", "soru"])
        self.assertEqual(self.isaret([""] * 6), ["giris", "konu", "konu", "fikir", "bilgi", "soru"])

    def test_isaretler(self):
        self.assertEqual(self.isaret(["giris", "fikir", "konu", "soru"]), ["giris", "fikir", "fikir", "soru"],
                         "bölüm geri gitmez")
        self.assertEqual(self.isaret(["giris", "xyz", "KONU", ""]), ["giris", "giris", "konu", "soru"],
                         "tanınmayan işaret öncekini sürdürür, son sahne soru")
        self.assertEqual(self.isaret(["konu", "konu", "bilgi", "soru"]), ["giris", "konu", "bilgi", "soru"],
                         "ilk sahne her zaman giriş")

    def test_ayni_bolum_ayni_sayfa_cifti(self):
        specs, words, meta, v = kur()
        self.assertEqual([b.ad for b in v.bolumler], list(KT.BOLUMLER))
        self.assertEqual(v.bolumler[0].sahneler, [0, 1])
        self.assertEqual(len(v.bolumler[0].paragraflar), 1, "ilk cümle sahnesinin sayfa metni yok")
        self.assertEqual(v.sekme_adlari, ["İLK CÜMLE", "KONU", "FİKİR", "BİLGİ", "SORU"])

    def test_eksik_bolumun_sekmesi_yok(self):
        data = demo()
        data["scenes"] = [sc for sc in data["scenes"] if sc["kitap_bolum"] != "fikir"]
        specs, words, meta, v = kur(data)
        self.assertEqual(v.sekme_adlari, ["İLK CÜMLE", "KONU", "BİLGİ", "SORU"])
        v.frame(v.gecis[2] + 0.5, grain=False)
        v.frame(v.gecis[-1] + 3.0, grain=False)

    def test_sayfa_metni_yoksa_dis_sesten(self):
        data = demo()
        for sc in data["scenes"]:
            sc["sayfa_metni"] = ""
            sc["vurgu"] = ""
        specs, words, meta, v = kur(data)
        for b in v.bolumler[:-1]:
            metin = " ".join(p.metin for p in b.paragraflar)
            self.assertTrue(metin, b.ad)
            self.assertLessEqual(len(metin.split()), 24, b.ad)
            self.assertNotIn("Yorumlara", metin)
        self.assertNotIn("Okudun", v.blurb)
        self.assertNotIn("Yorumlara", v.blurb)
        v.frame(v.gecis[2] + 1.0, grain=False)


# ---------------------------------------------------------------- sağ sayfa metni
class SayfaMetni(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs, cls.words, cls.meta, cls.v = kur()

    def test_sutun_ve_boyut(self):
        """Sütun 400 px'ten geniş; yazı 40-46 px; satırlar sığar, kısa tek kelimelik satır yok; her sayfada 3+ kelimelik
        satır var, satır başına ortalama 2,4+ kelime (Türkçe uzun kelimelerle; Courier'de 1-2 idi)."""
        self.assertGreaterEqual(KT.TX1 - KT.TX0, 400)
        toplam_kelime = toplam_satir = 0
        for i, sm in self.v._metin.items():
            with self.subTest(bolum=self.v.bolumler[i].ad):
                self.assertTrue(40 <= sm.size <= 46, sm.size)
                satirlar: dict = {}
                for j in sm.jetonlar:
                    satirlar.setdefault((j.para, j.line), []).append(j)
                    self.assertLessEqual(j.x + j.w, sm.width + 0.5)
                for js in satirlar.values():
                    if len(js) == 1:
                        self.assertGreater(js[0].w, sm.width * 0.62, f"tek kelimelik satır: {js[0].text}")
                self.assertGreaterEqual(max(len(js) for js in satirlar.values()), 3)
                self.assertLessEqual(sm.n_lines * sm.lh, sm.height + 0.5)
                toplam_kelime += len(sm.jetonlar)
                toplam_satir += len(satirlar)
        self.assertGreaterEqual(toplam_kelime / toplam_satir, 2.4)

    def test_tasan_metin_gruplanir(self):
        """Bölüm metni 40 px'te de sığmazsa sahne sahne gruplanır; yazı küçülmez, sayfadan taşmaz."""
        uzun = "Bu cümle sayfaya sığmayacak kadar uzun bir bölüm metninin parçasıdır ve birkaç kez yinelenir."
        paras = [KT.Paragraf(uzun, "", k, 0, 0) for k in range(5)]
        sm = KT.SayfaMetni(paras, [], reveal=1.0)
        self.assertEqual(sm.size, 40)
        self.assertGreater(len(sm.gruplar), 1)
        self.assertLessEqual(sm.n_lines * sm.lh, sm.height + 0.5)
        n, _, grup = sm.durum(1e9)
        self.assertEqual((n, grup), (len(sm.jetonlar), len(sm.gruplar) - 1))

    def test_dengeli_sarma(self):
        ws = [100, 30, 40, 200, 50, 60, 70, 30, 80]
        for M in (250, 300, 420):
            rows = KT.dengeli(ws, 10, M)
            self.assertEqual([k for i, j in rows for k in range(i, j)], list(range(len(ws))))
            for i, j in rows:
                self.assertLessEqual(sum(ws[i:j]) + 10 * (j - i - 1), M)
        self.assertEqual(KT.dengeli([], 10, 100), [])

    def test_vurgu_satirlari_sarar(self):
        """Fosforlu kalem tam olarak vurguyu kaplar; birden çok satıra yayılabilir."""
        for i, sm in self.v._metin.items():
            for pi, p in enumerate(sm.paras):
                if not p.vurgu:
                    continue
                with self.subTest(vurgu=p.vurgu):
                    js = [j for j in sm.jetonlar if j.para == pi and j.hl]
                    self.assertTrue(js)
                    parca = []
                    for j in js:
                        for a, b in j.hl:
                            k0 = next(k for k in range(len(j.text) + 1)
                                      if abs(KT.tw(j.text[:k], sm.font, sm.size) - (a - j.x)) < 0.6)
                            k1 = next(k for k in range(len(j.text) + 1)
                                      if abs(KT.tw(j.text[:k], sm.font, sm.size) - (b - j.x)) < 0.6)
                            parca.append(j.text[k0:k1])
                    self.assertEqual(" ".join(parca), p.vurgu.rstrip(".,;:!?"))
        giris = self.v._metin[0]
        self.assertGreater(len({j.line for j in giris.jetonlar if j.hl}), 1, "demo vurgusu iki satıra yayılır")

    def test_kalem_vurgu_soylendikten_sonra(self):
        v = self.v
        i = 2                                           # fikir
        sm = v._metin[i]
        t_kalem = sm.hl_t[0]
        son_vurgu = max(j.t for j in sm.jetonlar if j.hl)
        self.assertGreater(t_kalem, son_vurgu)

        def sari(t):
            a = np.asarray(v.sag_sayfa(i, t, duz=True).convert("RGB")).astype(int)
            return int(((a[..., 0] > 225) & (a[..., 1] > 180) & (a[..., 1] < 235) & (a[..., 2] < 130)).sum())
        self.assertEqual(sari(t_kalem - 0.05), 0)
        self.assertGreater(sari(t_kalem + KT.KALEM + 0.05), 500)


# ---------------------------------------------------------------- zaman çizelgesi
class Zaman(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs, cls.words, cls.meta, cls.v = kur()

    def test_evre_sirasi(self):
        v, words = self.v, self.words
        sira = {"kapak": 0, "acilis": 1, "sayfa": 2, "cevir": 2, "kapan": 3, "son": 4}
        onceki, onceki_bolum = -1, 0
        end = words[-1].end + 0.35
        t = 0.0
        while t < end:
            ev, i, lt = v.evre(t)
            self.assertGreaterEqual(sira[ev], onceki, f"t={t:.2f} {ev}")
            self.assertGreaterEqual(i, onceki_bolum)
            onceki, onceki_bolum = sira[ev], i
            t += 1 / 30
        self.assertEqual(v.evre(0.0)[0], "kapak")
        self.assertEqual(v.evre(end - 0.01)[0], "son")

    def test_kapak_ilk_cumleden_once_acilir(self):
        v, words = self.v, self.words
        ilk = next(w for w in words if w.text == "Gregor")
        self.assertGreaterEqual(v.t_ac, 1.0, "kanca en az 1 sn görünür")
        self.assertLessEqual(v.t_ac + KT.ACILIS_ORT + KT.ACILIS_DON, ilk.start + 0.35)
        self.assertGreaterEqual(v.t_ac, ilk.start - 1.6)

    def test_kelimeler_dis_sesle_yazilir(self):
        v = self.v
        for i, sm in v._metin.items():
            with self.subTest(bolum=v.bolumler[i].ad):
                ts = [j.t for j in sm.jetonlar]
                self.assertEqual(ts, sorted(ts))
                self.assertGreaterEqual(ts[0], v._reveal(i) - 1e-6, "sayfa açılmadan yazı yok")
                bitis = v.gecis[i + 1] if i + 1 < len(v.gecis) else self.words[-1].end
                self.assertLessEqual(ts[-1], bitis, "bölüm bitmeden sayfa tamamlanır")
                n0 = -1
                for k in range(40):
                    t = v.gecis[i] + (bitis - v.gecis[i]) * k / 39
                    n = sm.durum(t)[0]
                    self.assertGreaterEqual(n, n0)
                    n0 = n
        sm = v._metin[2]                               # fikir: "İnsan ..." söylendiği anda yazılır
        insan = next(w for w in self.words if w.text == "İnsan")
        self.assertAlmostEqual(sm.jetonlar[0].t, insan.start, delta=0.05)

    def test_okudun_mu_soylendiginde(self):
        v = self.v
        okudun = next(w for w in self.words if w.text == "Okudun")
        yorum = next(w for w in self.words if w.text == "Yorumlara")

        def var(t, ad):
            v.frame(t, grain=False)
            return any(n == ad for n, _ in v.kutular)
        self.assertFalse(var(okudun.start - 0.2, "okudun mu"))
        self.assertTrue(var(okudun.start + 0.1, "okudun mu"))
        self.assertFalse(var(yorum.start - 0.2, "yorumlara yaz"))
        self.assertTrue(var(yorum.start + 0.1, "yorumlara yaz"))

    def test_her_anda_kare(self):
        v = self.v
        for t in anlar(v, self.words):
            with self.subTest(t=t):
                im = v.frame(t)
                self.assertEqual((im.size, im.mode), ((1080, 1920), "RGB"))


# ---------------------------------------------------------------- yerleşim
class Yerlesim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs, cls.words, cls.meta, cls.v = kur()

    def test_guvenli_alan(self):
        v = self.v
        for t in anlar(v, self.words):
            v.frame(t, grain=False)
            self.assertTrue(v.kutular, t)
            for ad, box in v.kutular:
                self.assertTrue(kutu_ici(box), f"t={t:.2f} {ad} {box}")

    def test_kunyeli_video_guvenli_alanda(self):
        kb = dict(demo()["kitap"], baslik="Saatleri Ayarlama Enstitüsü", yazar="Ahmet Hamdi Tanpınar", yil=1961,
                  tur="roman", ozgun_dil="Türkçe", yazar_olum=1962, amblem="saat", kapak_rengi="yesil")
        specs, words, meta, v = kur(kitap=kb)
        for t in (0.0, v.t_ac + 0.8, v.gecis[1] - 0.3, v.gecis[-1] + 3.5, words[-1].end):
            v.frame(t, grain=False)
            for ad, box in v.kutular:
                self.assertTrue(kutu_ici(box), f"t={t:.2f} {ad} {box}")

    def test_uzun_kanca_ve_iki_sahne(self):
        """Üç satırlık uzun kanca, uzun başlık ve yalnız iki sahne (giriş + soru) de güvenli alanda çizilir."""
        data = demo()
        data["scenes"] = [dict(data["scenes"][0], headline=["İLK CÜMLESİYLE", "EDEBİYATI DEĞİŞTİREN", "UZUN ÖYKÜ"]),
                          data["scenes"][-1]]
        kb = dict(demo()["kitap"], baslik="Saatleri Ayarlama Enstitüsü Üzerine Uzun Bir Başlık")
        specs, words, meta, v = kur(data, kitap=kb)
        self.assertEqual([b.ad for b in v.bolumler], ["giris", "soru"])
        for t in anlar(v, words, 16):
            v.frame(t, grain=False)
            for ad, box in v.kutular:
                self.assertTrue(kutu_ici(box), f"t={t:.2f} {ad} {box}")

    def test_sekmeler_cevirmede_ortulmez(self):
        """Çevrilen sayfa (kapak açılışı, sayfa çevirme, kapanış) sekme sırasının üstüne hiç çıkmaz: yaprak çizilmeden
        alınan karede sekme şeridi piksel piksel aynı; bütün sekmeler kayıtlı."""
        v = self.v
        anlar_ = [v.t_ac + KT.ACILIS_ORT + KT.ACILIS_DON * f for f in (0.2, 0.5, 0.8)]
        for g in v.gecis[1:-1]:
            anlar_ += [g + KT.CEVIR * f for f in (0.15, 0.35, 0.5, 0.65, 0.9)]
        anlar_ += [v.t_kapan + KT.KAPAN * f for f in (0.3, 0.6)]
        y0, y1 = 428, KT.TOP - 4
        for t in anlar_:
            with self.subTest(t=round(t, 2), evre=v.evre(t)[0]):
                a = np.asarray(v.frame(t, grain=False))[y0:y1, 20:914]
                ev = v.evre(t)[0]
                if ev == "cevir":
                    sekme = [n for n, _ in v.kutular if n.startswith("sekme")]
                    self.assertEqual(len(sekme), len(v.sekme_adlari))
                with mock.patch.object(KT, "cevir", lambda *a, **k: None):
                    b = np.asarray(v.frame(t, grain=False))[y0:y1, 20:914]
                self.assertTrue(np.array_equal(a, b))

    def test_manset_ve_sekme_dik_konumdan_sonra(self):
        v = self.v
        g = v.gecis[2]                                   # konu -> fikir
        once = g + KT.CEVIR * 0.2
        sonra = g + KT.CEVIR * 0.8
        v.frame(once, grain=False)
        self.assertTrue(any(n.startswith("manşet NE ANLATIYOR") for n, _ in v.kutular))
        v.frame(sonra, grain=False)
        self.assertTrue(any(n.startswith("manşet ANA FİKİR") for n, _ in v.kutular))

    def test_kutuphane_karti_yalniz_kanca_ve_sonda(self):
        v = self.v
        for t in anlar(v, self.words):
            v.frame(t, grain=False)
            kart = any(n == "kütüphane kartı" for n, _ in v.kutular)
            ev = v.evre(t)[0]
            if ev in ("acilis", "sayfa", "cevir", "kapan"):
                self.assertFalse(kart, f"t={t:.2f} {ev}")
            if ev == "kapak" or (ev == "son" and t > v.t_son + 0.4):
                self.assertTrue(kart, f"t={t:.2f} {ev}")

    def test_seri_etiketi(self):
        sablon = json.loads((REPO / "templates" / "kitap.json").read_text(encoding="utf-8"))
        self.assertEqual(sablon["seri_adi"], KT.SERI_ADI)
        self.assertEqual(KT.varyant({})["seri_adi"], KT.SERI_ADI)
        uzun = dict(sablon, seri_adi="Bir Kitap Bir Dakika Özel Sezon")
        specs, words, meta, v = kur(sablon=uzun)
        self.assertEqual(v.seri, "BİR KİTAP BİR DAKİKA ÖZEL SEZON")
        for k in (70, 60):
            _, boxes = v.seri_katmani(k)
            self.assertTrue(boxes)
            for ad, b in boxes:
                self.assertLessEqual(b[2], SAFE_X, ad)
        v.frame(0.0, grain=False)
        self.assertTrue(any(n.startswith("seri BİR KİTAP") for n, _ in v.kutular))


# ---------------------------------------------------------------- amblemler, kapaklar
def kontrast(a, b) -> float:
    def lum(c):
        ch = [x / 255 for x in c[:3]]
        ch = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class AmblemKapak(unittest.TestCase):
    def test_on_alti_amblem(self):
        self.assertEqual(len(KT.AMBLEMLER), 16)
        ozet = set()
        for k in KT.AMBLEMLER:
            with self.subTest(amblem=k):
                self.assertIsNotNone(KT.amblem_svg(k))
                im = KT.amblem_img(k, 160)
                self.assertEqual(im.size, (160, 160))
                a = np.asarray(im.convert("RGBA")).astype(int)
                op = a[..., 3] > 200
                renkler = 0
                for c in (KT.RED, KT.YELLOW, KT.YESIL):
                    yakin = (np.abs(a[..., :3] - np.array(c)).sum(axis=2) < 40) & op
                    renkler += int(yakin.sum() > 150)
                self.assertGreaterEqual(renkler, 1, "marka renginde dolgu")
                ozet.add(hashlib.sha256(im.tobytes()).hexdigest())
        self.assertEqual(len(ozet), 16)

    def test_bilinmeyen_amblem_monogram(self):
        self.assertIsNone(KT.amblem_svg("ejderha"))
        a = KT.amblem_img("ejderha", 160, "Suç ve Ceza")
        b = KT.amblem_img("", 160, "Moby Dick")
        self.assertEqual(a.size, (160, 160))
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_kapak_renkleri_okunur(self):
        self.assertEqual(set(KT.KAPAKLAR), {"kirmizi", "sari", "lacivert", "yesil", "siyah"})
        for ad, c in KT.KAPAKLAR.items():
            with self.subTest(renk=ad):
                self.assertGreaterEqual(kontrast(c["yazi"], c["zemin"]), 4.5)
                self.assertGreaterEqual(kontrast(c["vurgu"], c["zemin"]), 3.0)

    def test_her_renk_ve_amblemle_kapak(self):
        kb = dict(KT.kitap_bilgisi({"kitap": demo()["kitap"]}, yil=2026))
        for i, ad in enumerate(KT.KAPAKLAR):
            for k in KT.AMBLEMLER[i::5]:
                with self.subTest(renk=ad, amblem=k):
                    on = KT.kapak_on(dict(kb, kapak_rengi=ad, amblem=k), KT.SERI_ADI)
                    arka = KT.kapak_arka(dict(kb, kapak_rengi=ad, amblem=k), "Sence ailesi ona haksızlık mı etti?")
                    self.assertEqual(on.size, (KT.PW, KT.PH))
                    self.assertEqual(arka.size, (KT.PW, KT.PH))
                    zemin = np.asarray(on.convert("RGB"))[KT.PH - 12, KT.PW // 2]
                    self.assertLess(np.abs(zemin.astype(int) - np.array(KT.KAPAKLAR[ad]["zemin"])).sum(), 30)

    def test_uzun_baslik_sigar(self):
        for baslik in ("Saatleri Ayarlama Enstitüsü", "Yüzyıllık Yalnızlık", "Ölü Canlar", "A"):
            size, lines = KT._baslik_satirlari(baslik, KT.PW - 36 - 48 - 30, 150, 60)
            self.assertLessEqual(len(lines), 3)
            for L in lines:
                self.assertLessEqual(KT.tw(L, "anton", size), KT.PW - 36 - 48 - 30 + 0.5)

    def test_her_kapak_rengiyle_video(self):
        for ad in KT.KAPAKLAR:
            with self.subTest(renk=ad):
                specs, words, meta, v = kur(kitap=dict(demo()["kitap"], kapak_rengi=ad))
                for t in (0.0, v.gecis[1] + 0.5, words[-1].end):
                    v.frame(t, grain=False)
                    for n, box in v.kutular:
                        self.assertTrue(kutu_ici(box), f"{ad} t={t:.2f} {n} {box}")


# ---------------------------------------------------------------- hız
class Hiz(unittest.TestCase):
    def test_kare_suresi(self):
        """Önbellek ısındıktan sonra sayfa ve çevirme kareleri hızlı (hedef ~0,1 sn; makine farkı için gevşek sınır)."""
        specs, words, meta, v = kur()
        g = v.gecis[2]
        for t in (g - 1.0, g + 0.2, g + 0.6):
            v.frame(t)
        ts = [g - 1.0 + k / 30 for k in range(30)] + [g + k / 30 for k in range(24)]
        t0 = time.perf_counter()
        for t in ts:
            v.frame(t).tobytes()
        ort = (time.perf_counter() - t0) / len(ts)
        self.assertLess(ort, 0.35, f"{ort * 1000:.0f} ms/kare")


# ---------------------------------------------------------------- birleşim
def kitap_senaryosu():
    """Demo senaryo ShortScript olarak. Modelde kitap alanları henüz yoksa (içerik dalı birleşmeden) testin alt
    sınıfı kullanılır: alanlar yine pipeline.build'e aynı adlarla ulaşır."""
    try:
        return S.load_script(DEMO)
    except Exception:  # noqa: BLE001
        pass

    class KScene(S.Scene):
        kitap_bolum: str = ""
        sayfa_metni: str = ""
        vurgu: str = ""

    class KScript(S.ShortScript):
        scenes: list[KScene]
        structure: str = "kitap"
        kitap: dict | None = None

    return KScript.model_validate(demo())


class Birlesim(unittest.TestCase):
    def test_sablon_yonlendirme(self):
        self.assertEqual(P.sablon_renderer("kitap"), "kitap")
        self.assertEqual(P.sablon_yapisi("kitap"), "kitap")
        self.assertIn("kitap", P.kendi_secimli(), "Claude'un şablon listesine girmez")
        self.assertEqual(P.yapi_sablonu("kitap"), "kitap")
        self.assertEqual(P.yapi_sablonu("hikaye"), "")
        self.assertEqual(P.yapi_sablonu(""), "")
        script = kitap_senaryosu()
        self.assertEqual(P.pick_template(script), "kitap")
        self.assertEqual(P.pick_template(script, "kitap"), "kitap")
        diger = script.model_copy(update={"structure": "hikaye", "template": "kitap"})
        self.assertNotEqual(P.pick_template(diger), "kitap", "Claude önerse de kitap şablonu seçilmez")

    def test_build_kitap_cizicisine_gecirir(self):
        script = kitap_senaryosu()
        cap = {}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(KT, "render_kitap", lambda sc, w, o, m, mu, meta: cap.update(specs=sc, meta=meta)), \
                mock.patch.object(P.images, "find_any", side_effect=AssertionError("fotoğraf aranmaz")):
            P.build(script, Path(tmp) / "b", use_voice=False, music=None, template="kitap")
            cap["metadata"] = json.loads((Path(tmp) / "b" / "metadata.json").read_text(encoding="utf-8"))
        specs, meta = cap["specs"], cap["meta"]
        self.assertEqual([s.card["bolum"] for s in specs], ["giris", "giris", "konu", "fikir", "bilgi", "soru"])
        self.assertEqual(specs[2].card["vurgu"], "Ailesi ona nasıl bakacak?")
        self.assertIn(specs[2].card["vurgu"], specs[2].card["sayfa"])
        self.assertEqual(specs[0].card["mascot"], "surprised")
        self.assertEqual(meta["kitap"]["baslik"], "Dönüşüm")
        self.assertEqual(meta["kitap"]["yazar_olum"], 1924)
        self.assertEqual((meta["sablon"]["renderer"], meta["sablon"]["seri_adi"]), ("kitap", KT.SERI_ADI))
        self.assertEqual(cap["metadata"]["template"], "kitap")
        # çizici, build'in verdiği sahnelerle kurulur
        v = KT.KitapVideo(specs, [w for s in specs for w in s.words], meta, BCFG)
        self.assertEqual([b.ad for b in v.bolumler], list(KT.BOLUMLER))

    def test_diger_sablonlar_degismedi(self):
        """Diğer şablon dosyaları ve çizicileri (kart, nasil, render, brand) tabandakiyle aynı."""
        try:
            ok = subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{TABAN}^{{commit}}"],
                                capture_output=True).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if not ok:
            self.skipTest(f"taban commit yok: {TABAN}")
        ls = subprocess.run(["git", "-C", str(REPO), "ls-tree", "--name-only", TABAN, "templates/"],
                            capture_output=True, text=True, check=True).stdout.split()
        dosyalar = [f for f in ls if f.endswith(".json") and f != "templates/kitap.json"]
        dosyalar += ["shortgen/kart.py", "shortgen/nasil.py", "shortgen/render.py", "shortgen/brand.py"]
        self.assertIn("templates/nasil.json", dosyalar)
        for f in dosyalar:
            with self.subTest(dosya=f):
                eski = subprocess.run(["git", "-C", str(REPO), "show", f"{TABAN}:{f}"], capture_output=True,
                                      check=True).stdout
                self.assertEqual((REPO / f).read_bytes(), eski)


if __name__ == "__main__":
    unittest.main(verbosity=2)
