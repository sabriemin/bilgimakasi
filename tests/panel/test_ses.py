#!/usr/bin/env python3
"""Çok sesli seslendirme (shortgen/voice.py, pipeline.seslendir) testleri. Ağ yok: ElevenLabs isteği sahte yanıtla
taklit edilir (ses dosyası ffmpeg ile üretilen kısa bir ton, kelime zamanları karakter başına sabit süre); anahtar
sahte bir değerdir.

- parçalama: anlatıcı ve karakter parçaları (balondaki tırnak içi söz), kelimeler ve sıraları korunur,
- ses ataması: her parça kendi ses kimliğiyle istenir; haritada olmayan konuşan anlatıcıda kalır,
- zaman kaydırma: birleşen kelime zamanları parçaların uç uca eklenmiş süresine göre kayar, tırnaklar korunur,
- geri dönüş: karakter sesi reddedilirse parça anlatıcıyla seslendirilir; anahtar/kredi hatası yükselir,
- tek sesli şablonlar: istek, gövde ve tempo eskisiyle aynı (voice.synthesize(metin, mp3)),
- sahne araları: ses ve kelime zamanları birlikte kayar; sessiz denemede yalnız zamanlar.

    python -B tests/panel/test_ses.py
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True

from shortgen import pipeline as PL, script as S, voice as V  # noqa: E402

DEMO = REPO / "demo" / "cizgi" / "kuzey_1.json"
KART_DEMO = REPO / "demo" / "kart" / "ornek_cin_seddi.json"
CIZGI = json.loads((REPO / "templates" / "cizgi.json").read_text(encoding="utf-8"))
ANLATICI = "anlaticiSesKimligi01"
ORTAM = {"ELEVENLABS_API_KEY": "sahte-anahtar", "ELEVENLABS_VOICE_ID": ANLATICI, "ELEVENLABS_MODEL": "eleven_v3"}
HARF = 0.05          # sahte hizalamada karakter başına süre
BAS = 0.2            # sahte sesin başındaki sessizlik

_ton: dict = {}


def ton(sure: float) -> bytes:
    """sure saniyelik tek kanallı mp3 (ElevenLabs çıktısı gibi 44.1 kHz)."""
    k = round(sure, 2)
    if k not in _ton:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "t.mp3"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={k}",
                            "-ac", "1", "-ar", "44100", "-b:a", "128k", str(f)], check=True)
            _ton[k] = f.read_bytes()
    return _ton[k]


class Yanit:
    def __init__(self, kod: int, veri: dict | None = None):
        self.status_code, self.ok, self._veri = kod, 200 <= kod < 300, veri or {}
        self.text = "" if self.ok else json.dumps({"detail": {"status": "voice_not_found"}})

    def json(self):
        return self._veri


class SahteEleven:
    """requests.post yerine: istekleri kaydeder; ret: {ses kimliği: HTTP kodu} reddedilen sesler."""

    def __init__(self, ret: dict | None = None):
        self.cagrilar: list[dict] = []
        self.ret = ret or {}

    def __call__(self, url, params=None, headers=None, json=None, timeout=None):  # noqa: A002
        ses = url.split("/text-to-speech/")[1].split("/")[0]
        self.cagrilar.append({"url": url, "params": params, "headers": headers, "json": json, "ses": ses})
        if ses in self.ret:
            return Yanit(self.ret[ses])
        text = json["text"]
        chars = list(text)
        starts = [BAS + i * HARF for i in range(len(chars))]
        return Yanit(200, {"audio_base64": base64.b64encode(ton(BAS + len(chars) * HARF + 0.15)).decode(),
                           "alignment": {"characters": chars, "character_start_times_seconds": starts,
                                         "character_end_times_seconds": [s + HARF for s in starts]}})

    def sesler(self) -> list[str]:
        return [c["ses"] for c in self.cagrilar]


def sure(mp3: Path) -> float:
    return V._duration(mp3)


def demo() -> S.ShortScript:
    return S.load_script(DEMO)


# ---------------------------------------------------------------- parçalama
class Parcalama(unittest.TestCase):
    def test_demo_parcalari(self):
        s = demo()
        parcalar = V.parcala(PL.ses_sahneleri(s), CIZGI["sesler"])
        tum = " ".join(sc.narration.strip() for sc in s.scenes)
        self.assertEqual(" ".join(p.text for p in parcalar).split(), tum.split(), "kelimeler ve sıraları korunur")
        konusanlar = [p.konusan for p in parcalar if p.konusan]
        balonlar = [sc.cizgi.balon.konusan for sc in s.scenes if sc.cizgi and sc.cizgi.balon]
        self.assertEqual(konusanlar, balonlar)
        self.assertEqual(len(parcalar), 2 * len(balonlar) + 1, "anlatıcı ve balon parçaları sırayla")
        for p in parcalar:
            if p.konusan:
                sc = next(x for x in s.scenes if x.cizgi and x.cizgi.balon and x.cizgi.balon.konusan == p.konusan)
                self.assertEqual(V._sade(p.text.strip(V.TIRNAK)), V._sade(sc.cizgi.balon.metin))
                self.assertTrue(p.text.startswith("\"") and p.text.rstrip(".!?").endswith("\""), p.text)
        # maliyet aynı mertebede: karakter seslerine giden kelimeler dış sesin küçük bir bölümü
        karakter = sum(p.kelime for p in parcalar if p.konusan)
        self.assertLess(karakter, len(tum.split()) * 0.3)

    def test_haritada_olmayan_konusan_anlaticida(self):
        sahneler = [("Gölge fısıldıyor: \"Seni izliyoruz.\"", "golge", "Seni izliyoruz."),
                    ("Kuzey gülüyor.", "", "")]
        p = V.parcala(sahneler, CIZGI["sesler"])
        self.assertEqual([(x.text, x.konusan) for x in p],
                         [("Gölge fısıldıyor: \"Seni izliyoruz.\" Kuzey gülüyor.", "")])
        self.assertEqual(V.parcala(sahneler, {}), p, "ses haritası boşsa tek anlatıcı parçası")

    def test_tirnaksiz_balon_metni_bulunur(self):
        t = "Hasan Reis ağını katlıyor: Kararın neyse arkandayım oğlum. Sonra susuyor.".split()
        self.assertEqual(V.soz_kelimeleri(t, "Kararın neyse arkandayım oğlum."),
                         [False] * 4 + [True] * 4 + [False] * 2)
        self.assertEqual(V.soz_kelimeleri(t, "Bambaşka bir söz."), [False] * len(t))
        self.assertEqual(V.soz_kelimeleri(["\"Tamam.\"", "dedi."]), [True, False])

    def test_ses_haritasi(self):
        """Haritadaki her kimlik bir Çizgi Roman karakteri, her ses kimliği ElevenLabs biçiminde (20 harf/rakam) ve
        birbirinden farklı; anlatıcının sesi haritada yok (ortam değişkeninden gelir)."""
        from shortgen import cizgi_sabit as CZ
        sesler = CIZGI["sesler"]
        self.assertLessEqual(set(sesler), set(CZ.KARAKTERLER))
        for k in ("hasan", "nermin", "selim", "orhan", "kuzey"):
            self.assertIn(k, sesler)
        for v in sesler.values():
            self.assertRegex(v, r"^[A-Za-z0-9]{20}$")
        self.assertEqual(len(set(sesler.values())), len(sesler))
        self.assertNotIn("BPOQsosga3cXhsJivIRc", sesler.values(), "anlatıcı (Gürkan) karakter sesi değil")
        # pilotun bütün balonları bir sese bağlı
        for sc in demo().scenes:
            if sc.cizgi and sc.cizgi.balon:
                self.assertIn(sc.cizgi.balon.konusan, sesler)


# ---------------------------------------------------------------- çok sesli seslendirme
class CokSes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, ORTAM)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def parcalar(self):
        return [V.Parca("Babası Hasan Reis ağını katlıyor:"), V.Parca("\"Kararın neyse arkandayım oğlum.\"", "hasan"),
                V.Parca("Annesi Nermin'in tek şartı var:"), V.Parca("\"Okul yarım kalmayacak.\"", "nermin")]

    def test_ses_atamasi_ve_zamanlar(self):
        sahte = SahteEleven()
        mp3 = self.dir / "voice.mp3"
        sesler = {"hasan": "hasanSesKimligi00001", "nermin": "nerminSesKimligi0001"}
        with mock.patch.object(V.requests, "post", sahte), mock.patch("builtins.print"):
            words = V.synthesize_parcali(self.parcalar(), mp3, sesler, tempo=1.0)
        self.assertEqual(sahte.sesler(), [ANLATICI, sesler["hasan"], ANLATICI, sesler["nermin"]])
        self.assertEqual([c["json"]["text"] for c in sahte.cagrilar], [p.text for p in self.parcalar()])
        tokens = " ".join(p.text for p in self.parcalar()).split()
        self.assertEqual([w.text for w in words], tokens, "tırnaklar kelimede kalır (kurgu balona yazar)")
        for a, b in zip(words, words[1:]):
            self.assertLessEqual(a.start, b.start)
            self.assertLessEqual(a.end, b.start + 1e-6)
        # her parçanın ilk kelimesi önceki parçaların toplam süresinden sonra başlar (baştaki sessizlik kırpılmış)
        sureler = []
        for p in self.parcalar():
            n = len(p.text)
            sureler.append(BAS + n * HARF + 0.15 - (BAS - 0.05))
        bas, k = 0.0, 0
        for p, d in zip(self.parcalar(), sureler):
            self.assertAlmostEqual(words[k].start, bas + 0.05, delta=0.08, msg=p.text)
            k += p.kelime
            bas += d
        self.assertAlmostEqual(sure(mp3), bas, delta=0.15)
        self.assertFalse((self.dir / "voice_parcalar").exists(), "ara dosyalar silinir")

    def test_karakter_sesi_reddedilirse_anlaticiya_doner(self):
        sesler = {"hasan": "yanlisSesKimligi0001", "nermin": "nerminSesKimligi0001"}
        sahte = SahteEleven(ret={"yanlisSesKimligi0001": 404})
        with mock.patch.object(V.requests, "post", sahte), mock.patch("builtins.print") as yaz:
            words = V.synthesize_parcali(self.parcalar(), self.dir / "voice.mp3", sesler, tempo=1.0)
        sirasi = sahte.sesler()
        i = sirasi.index("yanlisSesKimligi0001")
        # reddedilen parça hemen ardından aynı metinle anlatıcının sesiyle istenir (v3 gövdesi, sonra yedek gövdeler)
        geri = next(c for c in sahte.cagrilar[i + 1:] if c["ses"] != "yanlisSesKimligi0001")
        self.assertEqual((geri["ses"], geri["json"]["text"]), (ANLATICI, "\"Kararın neyse arkandayım oğlum.\""))
        self.assertEqual(sahte.cagrilar[-2]["json"]["text"], "Annesi Nermin'in tek şartı var:")
        self.assertEqual(sirasi[-1], "nerminSesKimligi0001")
        self.assertEqual(len(words), sum(p.kelime for p in self.parcalar()))
        log = " ".join(str(c) for c in yaz.call_args_list)
        self.assertIn("hasan için karakter sesi kullanılamadı", log)
        self.assertNotIn("sahte-anahtar", log, "anahtar günlüğe yazılmaz")

    def test_anahtar_hatasi_yukselir(self):
        sahte = SahteEleven(ret={"hasanSesKimligi00001": 401})
        with mock.patch.object(V.requests, "post", sahte), mock.patch("builtins.print"), \
                self.assertRaises(V.SesHatasi):
            V.synthesize_parcali(self.parcalar(), self.dir / "voice.mp3", {"hasan": "hasanSesKimligi00001"}, 1.0)
        self.assertNotIn(ANLATICI, sahte.sesler()[1:], "kredi/anahtar hatasında anlatıcıyla yeniden denenmez")

    def test_yalniz_anlatici_tek_istek(self):
        sahte = SahteEleven()
        with mock.patch.object(V.requests, "post", sahte), mock.patch("builtins.print"):
            V.synthesize_parcali([V.Parca("Kuzey gülüyor. Herkes susuyor.")], self.dir / "voice.mp3", {"a": "b"})
        self.assertEqual(sahte.sesler(), [ANLATICI])


# ---------------------------------------------------------------- tek sesli şablonlar eskisi gibi
class TekSes(unittest.TestCase):
    def test_istek_govdesi_ve_tempo_degismez(self):
        """voice.synthesize(metin, mp3): tek istek, anlatıcının sesi, v3 gövdesi ve VOICE_TEMPO (1.08) eskisi gibi."""
        sahte = SahteEleven()
        komutlar = []
        gercek = subprocess.run

        def run(cmd, *a, **k):
            komutlar.append(cmd)
            return gercek(cmd, *a, **k)

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, ORTAM), \
                mock.patch.object(V.requests, "post", sahte), mock.patch("subprocess.run", run), \
                mock.patch("builtins.print"):
            os.environ.pop("VOICE_TEMPO", None)
            words = V.synthesize("Kuzey gülüyor.", Path(tmp) / "voice.mp3")
        self.assertEqual(len(sahte.cagrilar), 1)
        c = sahte.cagrilar[0]
        self.assertEqual(c["url"], f"https://api.elevenlabs.io/v1/text-to-speech/{ANLATICI}/with-timestamps")
        self.assertEqual(c["params"], {"output_format": "mp3_44100_128"})
        self.assertEqual(c["headers"], {"xi-api-key": "sahte-anahtar", "Content-Type": "application/json"})
        self.assertEqual(c["json"], {"text": "Kuzey gülüyor.", "model_id": "eleven_v3", "language_code": "tr",
                                     "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}})
        tempo = [x for x in komutlar if "-filter:a" in x]
        self.assertEqual(len(tempo), 1)
        self.assertEqual(tempo[0][tempo[0].index("-filter:a") + 1], "atempo=1.08")
        self.assertEqual([w.text for w in words], ["Kuzey", "gülüyor."])

    def test_ses_ayari_olmayan_sablon(self):
        """Ses ayarı olmayan şablonlarda pipeline.seslendir yalnız voice.synthesize(metin, mp3) çağırır (ek argüman
        yok), parçalama ve sahne arası yok."""
        for ad in ("kart", "kolaj", "nasil", "kitap", "isemri"):
            t = json.loads((REPO / "templates" / f"{ad}.json").read_text(encoding="utf-8"))
            self.assertFalse({"sesler", "ses_tempo", "sahne_arasi"} & set(t), ad)
        s = S.load_script(KART_DEMO)
        metin = " ".join(sc.narration.strip() for sc in s.scenes)
        cagri = []

        def synth(*a, **k):
            cagri.append((a, k))
            return V.estimate(metin)

        mp3 = Path("/yok/voice.mp3")
        t = json.loads((REPO / "templates" / "kart.json").read_text(encoding="utf-8"))
        with mock.patch.object(V, "synthesize", synth), \
                mock.patch.object(V, "synthesize_parcali", side_effect=AssertionError("çok sesli yol")), \
                mock.patch.object(V, "duraklat", side_effect=AssertionError("sahne arası")):
            words, out = PL.seslendir(s, t, mp3, True)
        self.assertEqual(cagri, [((metin, mp3), {})])
        self.assertEqual(out, mp3)
        self.assertEqual(words, V.estimate(metin))
        # sessiz deneme de eskisi gibi (voice.estimate)
        words, out = PL.seslendir(s, t, mp3, False)
        self.assertIsNone(out)
        self.assertEqual(words, V.estimate(metin))


# ---------------------------------------------------------------- Çizgi Roman: çok ses, tempo, sahne araları
class Cizgi(unittest.TestCase):
    def test_cizgi_ayarlari(self):
        self.assertLess(CIZGI["ses_tempo"], V.VARSAYILAN_TEMPO, "anlatıcı biraz daha yavaş")
        self.assertGreaterEqual(CIZGI["ses_tempo"], 1.0)
        self.assertTrue(0.2 <= CIZGI["sahne_arasi"] <= 0.6)

    def test_seslendir_cok_sesli(self):
        s = demo()
        alinan = {}

        def parcali(parcalar, mp3, sesler, tempo=None):
            alinan.update(parcalar=parcalar, tempo=tempo, sesler=sesler)
            return V.estimate(" ".join(p.text for p in parcalar))

        with mock.patch.object(V, "synthesize_parcali", parcali), \
                mock.patch.object(V, "synthesize", side_effect=AssertionError("tek sesli yol")), \
                mock.patch.object(V, "duraklat", lambda w, mp3, sinir, sure: (alinan.update(sinir=sinir, ara=sure), w)[1]):
            PL.seslendir(s, CIZGI, Path("/yok/voice.mp3"), True)
        self.assertEqual(alinan["tempo"], CIZGI["ses_tempo"])
        self.assertEqual(alinan["sesler"], CIZGI["sesler"])
        self.assertEqual(len([p for p in alinan["parcalar"] if p.konusan]), 7)
        self.assertEqual(alinan["ara"], CIZGI["sahne_arasi"])
        sayilar = [len(sc.narration.split()) for sc in s.scenes]
        self.assertEqual(alinan["sinir"], [sum(sayilar[:i]) for i in range(1, len(sayilar))])

    def test_sessiz_deneme_araliklarla(self):
        s = demo()
        words, mp3 = PL.seslendir(s, CIZGI, Path("/yok/voice.mp3"), False)
        self.assertIsNone(mp3)
        sayilar = [len(sc.narration.split()) for sc in s.scenes]
        self.assertEqual(len(words), sum(sayilar))
        k = 0
        for c in sayilar[:-1]:
            k += c
            self.assertGreaterEqual(words[k].start - words[k - 1].end, CIZGI["sahne_arasi"])
        # daha yavaş anlatıcı ve aralarla bölüm ≈ 85-95 sn (son bekleyiş dahil)
        toplam = words[-1].end + max(0.35, CIZGI["son_bekleme"])
        self.assertTrue(85 <= toplam <= 95, toplam)

    def test_duraklat_ses_ve_zaman(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp3 = Path(tmp) / "voice.mp3"
            mp3.write_bytes(ton(3.0))
            w = [V.Word("a", 0.2, 0.6), V.Word("b", 0.8, 1.2), V.Word("c", 1.6, 2.0), V.Word("d", 2.2, 2.6)]
            with mock.patch("builtins.print"):
                out = V.duraklat(w, mp3, [2, 3], 0.5)
            self.assertEqual([(x.start, x.end) for x in out], [(0.2, 0.6), (0.8, 1.2), (2.1, 2.5), (3.2, 3.6)])
            self.assertAlmostEqual(sure(mp3), 4.0, delta=0.08)
        self.assertEqual(V.duraklat(w, None, [], 0.5), w)
        self.assertEqual(V.duraklat(w, None, [2], 0.0), w)

    def test_tahmin(self):
        m = "Kuzey ne yapsın? A: İstanbul. B: Samsun."
        self.assertEqual(V.tahmin(m), V.estimate(m))
        self.assertGreater(V.tahmin(m, 1.0)[-1].end, V.tahmin(m, 1.08)[-1].end)


if __name__ == "__main__":
    unittest.main(verbosity=1)
