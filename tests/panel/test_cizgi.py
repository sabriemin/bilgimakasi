#!/usr/bin/env python3
"""Çizgi Roman şablonu (templates/cizgi.json, shortgen/cizgi*.py; "Karar Senin" hikâye serisinin pilotu) testleri.
Ağ yok, ses yok (kelime süreleri voice.estimate ile, pipeline'ın --no-voice yolu gibi):

- senaryo modeli: Scene.cizgi isteğe bağlı (eski JSON yüklenir), doğrulama ve dil düzeltmesi tarifi korur, tarifsiz
  senaryoların istem metni değişmez,
- şablon kaydı: yalnız --template ile seçilir (eslesme.json değişmez), kalıp sabitlemez,
- pilot senaryo: 17 sahne, dış ses birebir, başlık, açıklama, kategori ve kalıp,
- karakterler ve mekânlar: her anahtar çizilir, çıktı belirlenimci,
- yerleşim: her sahnenin her anında içerik güvenli alanda; balon konuşanın başına, anlatıcı kutusu Makas'a binmez;
  uzun Türkçe kelimeler, 6 ve 18 sahne; son sahnenin parçaları üst üste binmez,
- uçtan uca: python -m shortgen.pipeline --script demo/cizgi/kuzey_1.json --no-voice --template cizgi (geçici
  kökte; depoya yazmaz).

    python -B tests/panel/test_cizgi.py
"""
from __future__ import annotations

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

import numpy as np  # noqa: E402

from shortgen import cizgi as C, cizgi_karakter as CK, cizgi_mekan as CM, cizgi_sabit as CZ  # noqa: E402
from shortgen import kart as K, pipeline as PL, render, script as S  # noqa: E402
from shortgen.voice import estimate  # noqa: E402

DEMO = REPO / "demo" / "cizgi" / "kuzey_1.json"
KART_DEMO = REPO / "demo" / "kart" / "ornek_cin_seddi.json"
BCFG = {"enabled": True, "handle": "@bilgimakasi", "intro_cut": True, "subtitle_handle": True,
        "watermark_switch_seconds": 7, "cut_transition_every": 4}
SAFE = K.SAFE
UZUN = "ÇEKOSLOVAKYALILAŞTIRAMADIKLARIMIZDANMIŞSINIZCASINA"
UZUN2 = "muvaffakiyetsizleştiricileştiriveremeyebileceklerimizdenmişsinizcesine"

ANLATIM = [
    "On beş yaşındaki Kuzey'in cebinde iki kulübün kartviziti var.",
    "Kuzey, Sinop'ta balıkçı Hasan Reis'in oğlu.",
    "Sabahları babasıyla ağ topluyor, akşamları Sinopspor'un gençlerinde top koşturuyor.",
    "Türkiye'nin en kuzey ucu İnceburun da Sinop'ta; Kuzey adını oradan alıyor.",
    "Bu yaz bölge turnuvasında altı maçta dokuz gol atıyor.",
    "Final maçında tribünde iki adam not alıyor.",
    "Biri Galatasaray'ın gözcüsü Selim Bey.",
    "Teklifi parlak: İstanbul'da altyapı, yatılı yer ve okul.",
    "Ama orada her yaş grubunda onun gibi onlarca yetenek var.",
    "Öbürü Samsunspor'un gözcüsü Orhan Bey.",
    "Sözü net: \"Bizde bir yıl içinde A takımla antrenmana çıkarsın.\"",
    "Samsun eve yakın; ama İstanbul'un kapısı ikinci kez çalmayabilir.",
    "Hasan Reis ağını katlıyor: \"Kararın neyse arkandayım oğlum.\"",
    "Annesi Nermin'in tek şartı var: okul yarım kalmayacak.",
    "Kuzey'in bilmediği bir şey var: Selim Bey aynı turnuvadan bir golcüye daha teklif yaptı.",
    "Selim Bey yarın sabah İstanbul'a dönüyor; cevap bu gece verilecek.",
    "Kuzey ne yapsın? A: İstanbul'a, Galatasaray'a gitsin. B: Samsunspor'da şansını denesin. Yorumlara A ya da B yaz.",
]


def sahneler(script: S.ShortScript):
    """pipeline.build'in kurgu modülü dalının kurduğu sahneler (kelime süreleri voice.estimate)."""
    specs = []
    for sc in script.scenes:
        specs.append(render.SceneSpec(
            narration=sc.narration, kicker=sc.kicker, headline=list(sc.headline), highlight_line=sc.highlight_line,
            strike=list(sc.strike), theme=sc.theme, image_mode="none", image=None, icon="none", sprite=None,
            motion="none", drawn=True))
    words = estimate(" ".join(sc.narration.strip() for sc in script.scenes))
    i = 0
    for spec, sc in zip(specs, script.scenes):
        c = len(sc.narration.split())
        spec.words = words[i:i + c]
        spec.start = spec.words[0].start if spec.words else (words[i - 1].end if i else 0.0)
        i += c
    specs[0].start = 0.0
    for a, b in zip(specs, specs[1:]):
        b.start = max(b.start - 0.12, a.start + 0.5)
        a.end = b.start
    specs[-1].end = words[-1].end + 0.35
    for spec, sc in zip(specs, script.scenes):
        spec.card = sc.model_dump()
    meta = {"topic": script.topic, "structure": script.structure, "title": script.title,
            "category": script.category, "sablon": {}, "script": script.model_dump()}
    return specs, words, meta


def video(script, yalniz_icerik=True):
    specs, words, meta = sahneler(script)
    return C.CizgiVideo(specs, words, meta, BCFG, yalniz_icerik=yalniz_icerik), specs


def demo() -> S.ShortScript:
    return S.load_script(DEMO)


def alfa_kutu(im) -> tuple | None:
    return im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()


def guvenli(test, im, ad):
    b = alfa_kutu(im)
    if b is None:
        return
    test.assertGreaterEqual(b[1], SAFE[1], f"{ad}: üst taşma {b}")
    test.assertLessEqual(b[2], SAFE[2], f"{ad}: sağ taşma {b}")
    test.assertLessEqual(b[3], SAFE[3], f"{ad}: alt taşma {b}")


def anlar(spec, n=5):
    d = spec.end - spec.start
    return [spec.start + d * f for f in (0.0, 0.08, 0.3, 0.6, 0.97)[:n]]


def kesisir(a, b, pay=0.0) -> bool:
    return not (a[2] <= b[0] + pay or b[2] <= a[0] + pay or a[3] <= b[1] + pay or b[3] <= a[1] + pay)


# ---------------------------------------------------------------- senaryo modeli
class Senaryo(unittest.TestCase):
    def test_eski_json_yuklenir(self):
        s = S.load_script(KART_DEMO)
        self.assertEqual({sc.cizgi for sc in s.scenes}, {None})
        sema = S.ShortScript.model_json_schema()["$defs"]
        self.assertNotIn("cizgi", sema["Scene"].get("required", []))
        self.assertEqual(sema["CizgiPanel"]["properties"]["mekan"]["enum"], list(CZ.MEKANLAR))
        self.assertEqual(sema["CizgiKarakter"]["properties"]["id"]["enum"], list(CZ.KARAKTERLER))
        # alan sınıfın sonunda ve şablon başlığının altında
        self.assertEqual(list(S.Scene.model_fields)[-1], "cizgi")
        kaynak = (REPO / "shortgen" / "script.py").read_text(encoding="utf-8")
        self.assertIn("    # --- cizgi şablonu ---\n    cizgi: CizgiSahne | None", kaynak)

    def test_pilot_senaryo(self):
        s = demo()
        self.assertEqual([sc.narration for sc in s.scenes], ANLATIM)
        self.assertEqual((s.title, s.category, s.structure), ("Karar Senin · 1. Bölüm: İki Kartvizit", "spor", "hikaye"))
        self.assertIn(s.structure, S.STRUCTURES)
        self.assertNotIn("secim", S.STRUCTURES)
        self.assertTrue(s.description.endswith("Kurgusal bir hikâyedir."))
        self.assertEqual(len(s.hashtags), 5)
        kelime = sum(len(sc.narration.split()) for sc in s.scenes)
        self.assertTrue(140 <= kelime <= 175, kelime)       # 60-80 sn (≈2,15 kelime/sn)
        for sc in s.scenes:
            self.assertIsNotNone(sc.cizgi)
            self.assertEqual((sc.illustration, sc.image_queries, sc.image_mode), ("", [], "none"), "ağ yok")
        c0 = s.scenes[0].cizgi
        self.assertEqual((c0.seri, c0.bolum), ("KARAR SENİN", 1))
        kartlar = [sc.cizgi.kart.tur if sc.cizgi.kart else "" for sc in s.scenes]
        self.assertEqual(kartlar.count("gercek"), 1, "bölümün tek gerçek bilgisi")
        self.assertEqual(kartlar[-1], "ab")
        ab = s.scenes[-1].cizgi.kart
        self.assertEqual((ab.a, ab.b), ("İSTANBUL'A, GALATASARAY'A", "SAMSUNSPOR'DA ŞANSINI DENESİN"))
        self.assertEqual(s.scenes[14].cizgi.kart.baslik, "SEN BİLİYORSUN, KUZEY BİLMİYOR")
        # balon metni dış sesteki tırnak içiyle aynı
        for sc in s.scenes:
            if sc.cizgi.balon:
                self.assertIn(f"\"{sc.cizgi.balon.metin}\"", sc.narration)
        # gerçek kişi yok: kadro kurgusal
        self.assertEqual(set(CZ.KARAKTERLER), {"kuzey", "hasan", "nermin", "selim", "orhan", "golge"})

    def test_istem_tarifsiz_senaryoda_degismez(self):
        k = S.load_script(KART_DEMO)
        self.assertNotIn("cizgi", S._senaryo_json(k))
        self.assertIn("\"cizgi\"", S._senaryo_json(demo()))

    def test_dil_duzeltmesi_tarifi_korur(self):
        s = demo()
        duz = s.model_copy(deep=True)
        for sc in duz.scenes:
            sc.cizgi = None
        duz.scenes[1].narration = "Kuzey, Sinop'ta balıkçı Hasan Reis'in oğludur."
        with mock.patch.object(S, "ask_claude", lambda *a, **k: S.Polished(notes=[], fixed=duz.model_copy(deep=True))):
            out = S.polish_script(s)
        self.assertEqual([x.cizgi for x in out.scenes], [x.cizgi for x in s.scenes])
        self.assertEqual(out.scenes[1].narration, "Kuzey, Sinop'ta balıkçı Hasan Reis'in oğludur.")

    def test_dogrulama_tarifi_geri_yukler(self):
        s = demo()
        yeni = s.model_copy(deep=True)
        for sc in yeni.scenes:
            sc.cizgi = None
        S.cizgi_geri_yukle(s, yeni)
        self.assertEqual([x.cizgi for x in yeni.scenes], [x.cizgi for x in s.scenes])
        # sahne çıkarıldıysa dış sesi benzeyen sahnenin tarifi
        yeni = s.model_copy(deep=True)
        del yeni.scenes[5]
        for sc in yeni.scenes:
            sc.cizgi = None
        S.cizgi_geri_yukle(s, yeni)
        self.assertEqual(yeni.scenes[5].cizgi, s.scenes[6].cizgi)
        self.assertEqual(yeni.scenes[-1].cizgi, s.scenes[-1].cizgi)
        # verify geçişi de korur
        rev = s.model_copy(deep=True)
        for sc in rev.scenes:
            sc.cizgi = None
        with mock.patch.object(S, "ask_claude", lambda *a, **k: S.Review(ok=True, problems=[], fixed=rev.model_copy(deep=True))):
            out = S.verify_script(s)
        self.assertEqual([x.cizgi for x in out.scenes], [x.cizgi for x in s.scenes])


# ---------------------------------------------------------------- şablon kaydı
class Sablon(unittest.TestCase):
    def test_yalniz_elle_secilir(self):
        t = json.loads((REPO / "templates" / "cizgi.json").read_text(encoding="utf-8"))
        self.assertEqual(t["renderer"], "cizgi")
        self.assertNotIn("yapi", t)
        self.assertIn("cizgi", t["istem"])
        self.assertNotIn("cizgi", (REPO / "templates" / "eslesme.json").read_text(encoding="utf-8"))
        self.assertIn("cizgi", PL.kendi_secimli())
        self.assertEqual(PL.sablon_yapisi("cizgi"), "")
        s = demo()
        self.assertEqual(PL.pick_template(s, "cizgi"), "cizgi")
        self.assertNotEqual(PL.pick_template(s), "cizgi")
        self.assertNotEqual(PL.pick_template(s.model_copy(update={"template": "cizgi"})), "cizgi")


# ---------------------------------------------------------------- karakterler ve mekânlar
class Cizimler(unittest.TestCase):
    def test_her_karakter_poz_ifade(self):
        for kid in CZ.KARAKTERLER:
            self.assertIn(kid, CK.KADRO)
            for poz in CZ.POZLAR:
                a = CK.figur_svg(kid, poz, "normal", "sag")
                self.assertEqual(a, CK.figur_svg(kid, poz, "normal", "sag"), "belirlenimci")
                if poz != "dur":
                    self.assertNotEqual(a, CK.figur_svg(kid, "dur", "normal", "sag"), (kid, poz))
            for ifade in CZ.IFADELER:
                self.assertTrue(CK.figur_svg(kid, "dur", ifade, "sol").startswith("<g transform"))
        for k in CZ.IFADELER:
            self.assertIn(k, CK.KASLAR)
        # solak: şut pozunda figür aynalanmaz (vuran bacak sol bacak kalır)
        self.assertEqual(CK.figur_svg("kuzey", "sut", "kararli", "sol"), CK.figur_svg("kuzey", "sut", "kararli", "sag"))
        im = K.svg_img(CK.figur_svg("kuzey", "sut", "kararli"), (-100, 0, 600, 1000), 300, 500)
        self.assertIsNotNone(alfa_kutu(im))

    def test_her_mekan_her_panelde(self):
        self.assertEqual(set(CM.MEKANLAR), set(CZ.MEKANLAR))
        for anahtar in CZ.MEKANLAR:
            for box in ((64, 346, 920, 760), (64, 346, 470, 1198), (64, 346, 920, 1198)):
                m = CM.mekan(anahtar, box, ["6 MAÇ · 9 GOL", UZUN], 3)
                self.assertTrue(m.arka.startswith("<"), anahtar)
                for x, y, t, f, s, c, an in m.yazi:
                    self.assertTrue(box[0] - 1 <= x <= box[2] + 1 and box[1] <= y <= box[3] + 1, (anahtar, t, x, y))
                    w = K.tw(t, f, s)
                    x0 = x - (w / 2 if an[0] == "m" else (w if an[0] == "r" else 0))
                    self.assertTrue(box[0] - 2 <= x0 and x0 + w <= box[2] + 2, (anahtar, t, box))

    def test_tirnak_ici(self):
        t = ["Sözü", "net:", "\"Bizde", "bir", "yıl.\"", "Sonra"]
        self.assertEqual(C.tirnak_ici(t), [False, False, True, True, True, False])
        self.assertEqual(C.tirnak_ici(["\"Tamam.\"", "dedi."]), [True, False])
        self.assertEqual(C.temiz("\"Bizde"), "Bizde")


# ---------------------------------------------------------------- yerleşim
class Yerlesim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v, cls.specs = video(demo())

    def test_her_sahne_guvenli_alanda(self):
        for i, spec in enumerate(self.specs):
            for t in anlar(spec):
                guvenli(self, self.v.frame(t), f"sahne {i + 1} t={t:.2f}")

    def test_panel_ve_kutular(self):
        v = self.v
        for i in range(len(self.specs)):
            S_ = v.hazirla(i)
            for lay, (x, y), _ in S_.paneller:
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + lay.width, SAFE[2] + 1, i)
            if S_.anlatici:
                for pi in range(len(S_.anlatici.pages)):
                    im, w, h = v.anlatici_katmani(S_, pi, 10 ** 6)
                    self.assertLessEqual(C.CAP[0] + w, C.CAP[2] + 1)
                    self.assertLessEqual(C.CAP[1] + h, SAFE[3] - 8, (i, pi))
                    # Makas'ın gövdesine binmez
                    self.assertLess(C.CAP[0] + w + 10, C.MASKOT[0] - 50)
            if S_.balon is not None:
                b = S_.balon.kutu
                self.assertGreaterEqual(b[0], C.X0)
                self.assertLessEqual(b[2], C.X1)
                self.assertGreaterEqual(b[1], C.PANEL_Y0 - 8)
                kon = S_.balon.b.uc
                self.assertIsNotNone(kon)
            kk = v.kart_katmani(S_)
            if kk:
                lay, y0 = kk
                bb = alfa_kutu(lay)
                self.assertLessEqual(y0 + bb[3], C.CAP[1] - 4, f"sahne {i + 1}: kart anlatıcı kutusuna biner")
                self.assertGreaterEqual(y0 + bb[1], C.KARTLI_Y1 - 4)

    def test_balon_konusanin_basina_binmez(self):
        v = self.v
        for i, sc in enumerate(demo().scenes):
            if not (sc.cizgi and sc.cizgi.balon):
                continue
            S_ = v.hazirla(i)
            pc = sc.cizgi.paneller[0].model_dump()
            box = C.ic_kutu(S_.polys[0])
            ys = C.yerlestir(pc["karakterler"], box, True)
            kon = next(y for y in ys if y.kid == sc.cizgi.balon.konusan)
            hx, htop, mouth, hw = kon.bas
            bas = (hx - hw, htop, hx + hw, mouth)
            self.assertFalse(kesisir(S_.balon.kutu, bas), f"sahne {i + 1}")
            # balondaki söz dış sesteki tırnak içi (büyük harf)
            self.assertEqual(" ".join(S_.balon.words), K.tr_upper(sc.cizgi.balon.metin))

    def test_son_sahne_parcalari(self):
        v = self.v
        S_ = v.hazirla(len(self.specs) - 1)
        P = v.ab_parcalar(S_)
        kartlar = []
        for h in ("a", "b"):
            im, x, y = P["kart_" + h]
            bb = alfa_kutu(im)
            kartlar.append((x + bb[0], y + bb[1], x + bb[2], y + bb[3]))
            self.assertLessEqual(x + bb[2], SAFE[2])
        self.assertFalse(kesisir(kartlar[0], kartlar[1]))
        cta, cx, cy = P["cta"]
        cb = alfa_kutu(cta)
        cta_box = (cx + cb[0], cy + cb[1], cx + cb[2], cy + cb[3])
        alt, ax, ay = P["alt"]
        ab_ = alfa_kutu(alt)
        alt_box = (ax + ab_[0], ay + ab_[1], ax + ab_[2], ay + ab_[3])
        self.assertLessEqual(alt_box[3], SAFE[3] - 8)
        self.assertFalse(kesisir(cta_box, alt_box, 2), (cta_box, alt_box))
        for k in kartlar:
            self.assertFalse(kesisir(k, cta_box, 6), (k, cta_box))
        self.assertGreaterEqual(P["sonraki_size"], 34, "sonraki bölüm satırı büyük")
        # oylama ve kurgu satırı ve çağrı son karede görünür
        son = v.frame(self.specs[-1].end - 0.05)
        guvenli(self, son, "son kare")

    def test_kapak_karesi_tam(self):
        """t=0 kapak: panel, anlatıcı kutusu ve üst bant görünür."""
        im = self.v.frame(0.0)
        a = np.asarray(im.getchannel("A"))
        self.assertGreater(a[C.PANEL_Y0 + 200, 400], 200, "panel")
        self.assertGreater(a[C.CAP[1] + 40, C.CAP[0] + 40], 200, "anlatıcı kutusu")
        self.assertGreater(a[C.HEAD_CY, 140], 200, "üst bant")
        self.assertGreater(a[C.HEAD_CY, 880], 200, "KURGU etiketi")


class UzunVeSayilar(unittest.TestCase):
    def senaryo(self, n: int) -> S.ShortScript:
        s = demo()
        sc = [x.model_copy(deep=True) for x in s.scenes]
        orta = sc[1:-1]
        govde = (orta * 3)[:max(1, n - 2)]
        s.scenes = [sc[0]] + [x.model_copy(deep=True) for x in govde] + [sc[-1]]
        return s

    def test_alti_ve_on_sekiz_sahne(self):
        for n in (6, 18):
            s = self.senaryo(n)
            self.assertEqual(len(s.scenes), n)
            v, specs = video(s)
            for i, spec in enumerate(specs):
                guvenli(self, v.frame(spec.start + (spec.end - spec.start) * 0.9), f"{n} sahne, {i + 1}")

    def test_uzun_turkce_kelimeler(self):
        s = demo()
        s.scenes = [s.scenes[i].model_copy(deep=True) for i in (0, 3, 10, 14, 16)]
        s.scenes[0].narration = f"{UZUN2} {UZUN2} Kuzey'in cebinde iki kartvizit var."
        s.scenes[0].cizgi.seri = "KARAR SENİN ÇEKOSLOVAKYALILAŞTIRAMADIKLARIMIZDAN"
        s.scenes[1].cizgi.kart.metin = f"{UZUN2} {UZUN2} İnceburun Sinop'tadır."
        s.scenes[1].cizgi.kart.kaynak = UZUN2
        s.scenes[1].cizgi.paneller[0].yazi = [UZUN]
        s.scenes[2].narration = f"Sözü net: \"{UZUN2} {UZUN2} çıkarsın.\""
        s.scenes[2].cizgi.balon.metin = f"{UZUN2} {UZUN2} çıkarsın."
        s.scenes[3].cizgi.kart.baslik = f"{UZUN}, {UZUN}"
        s.scenes[3].cizgi.paneller[0].yazi = [UZUN, UZUN]
        s.scenes[4].cizgi.kart.a = UZUN
        s.scenes[4].cizgi.kart.b = f"{UZUN} {UZUN}"
        s.scenes[4].cizgi.kart.baslik = f"{UZUN} NE YAPSIN?"
        v, specs = video(s)
        for i, spec in enumerate(specs):
            for t in anlar(spec):
                guvenli(self, v.frame(t), f"uzun, sahne {i + 1}")

    def test_tarifsiz_sahne(self):
        s = demo()
        s.scenes = [s.scenes[0].model_copy(deep=True), s.scenes[1].model_copy(update={"cizgi": None}, deep=True)]
        v, specs = video(s)
        guvenli(self, v.frame(specs[1].start + 0.5), "tarifsiz")


# ---------------------------------------------------------------- uçtan uca
class UctanUca(unittest.TestCase):
    def test_pipeline_sessiz(self):
        with tempfile.TemporaryDirectory() as tmp:
            kok = Path(tmp)
            shutil.copytree(REPO / "shortgen", kok / "shortgen", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(REPO / "templates", kok / "templates")
            shutil.copy2(REPO / "brand.json", kok / "brand.json")
            shutil.copytree(REPO / "demo" / "cizgi", kok / "demo" / "cizgi")
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            r = subprocess.run([sys.executable, "-B", "-m", "shortgen.pipeline", "--script",
                                str(kok / "demo/cizgi/kuzey_1.json"), "--no-voice", "--template", "cizgi",
                                "--out", str(kok / "out")], cwd=kok, env=env, capture_output=True, text=True,
                               timeout=2400)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
            self.assertIn("Şablon: cizgi", r.stdout)
            mp4 = next((kok / "out").glob("*/video.mp4"))
            pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height:format=duration", "-of", "json", str(mp4)],
                                capture_output=True, text=True, timeout=60)
            info = json.loads(pr.stdout)
            self.assertEqual((info["streams"][0]["width"], info["streams"][0]["height"]), (1080, 1920))
            sure = float(info["format"]["duration"])
            words = estimate(" ".join(ANLATIM))
            self.assertAlmostEqual(sure, words[-1].end + 0.35, delta=0.6)
            self.assertGreater(sure, 55)
            meta = json.loads(next((kok / "out").glob("*/metadata.json")).read_text(encoding="utf-8"))
            self.assertEqual(meta["template"], "cizgi")
            self.assertIn("Kurgusal bir hikâyedir.", meta["description"])
        self.assertFalse((REPO / "out").exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
