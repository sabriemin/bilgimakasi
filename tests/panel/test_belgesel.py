"""Mini Belgesel (belgesel kalıbı ve şablonu) testleri (ağ yok, Claude çağrısı yok, ses yok):
- yazar kuralları doğrulayıcısı (script.belgesel_sorunlari) ve normalize_belgesel,
- iki bölüme ayırma (script.belgesel_bolumleri, pipeline.belgesel_hazirla): başlık/açıklama 'Bölüm n/2', seri_id,
- kurgu (shortgen/belgesel.py) duman testi: iki görünüm, iki bölüm; her karede 'BÖLÜM n /2' etiketi, 'DEVAMI BÖLÜM
  2'DE', 'BÖLÜM 1'DE...' ve 'ŞİMDİ' yazıları, yazıların güvenli alanda kalması, metadata'da seri alanları,
- iki bölümlü onay akışı (telegram_bot): 1. bölüm onaylanınca 2. bölüm sıradaki belgesel saatine zamanlanır, red ve
  iptal 2. bölüme geçer, 2. bölümün kendi 'en iyi' saati 1. bölümden sonradır.

    python3 tests/panel/test_belgesel.py
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from shortgen import script as S  # noqa: E402
from shortgen import takvim  # noqa: E402

KEDI = REPO / "demo" / "belgesel" / "kedi_yasam_dongusu.json"
KAN = REPO / "demo" / "belgesel" / "kanin_temizlenmesi.json"
SAFE = (0, 170, 935, 1540)


def yukle(p: Path) -> S.ShortScript:
    return S.load_script(p)


# ---------------------------------------------------------------- yazar kuralları
class Kurallar(unittest.TestCase):
    def test_ornekler_kurallara_uyar(self):
        for p, gor in ((KEDI, "cizgi"), (KAN, "hat")):
            s = yukle(p)
            self.assertEqual(s.structure, "belgesel")
            self.assertEqual(s.belgesel.gorunum, gor)
            self.assertEqual(S.belgesel_sorunlari(s), [], p.name)
            g = S.belgesel_bolum_sahneleri(s)
            for no in (1, 2):
                kelime = sum(len(sc.narration.split()) for sc in g[no])
                self.assertTrue(S.BELGESEL_KELIME[0] <= kelime <= S.BELGESEL_KELIME_UST, (p.name, no, kelime))

    def test_kalip_kayitli(self):
        self.assertIn("belgesel", S.STRUCTURES)
        self.assertIn("belgesel", S.FORCED_ONLY)
        self.assertEqual(S.kalip_kurallari("belgesel", False), "\n" + S.BELGESEL_RULES)
        for parca in ("Devamı Bölüm 2'de.", "Bölüm 1'de", "Yorumlara yaz.", "kanca"):
            self.assertIn(parca, S.BELGESEL_RULES)
        # belgesel alanları yalnız belgesel kalıbında şemada
        self.assertNotIn("Belgesel", json.dumps(S.sema_json(S.ShortScript)))
        with S._belgesel_semasi(True):
            self.assertIn("BelgeselBilgi", json.dumps(S.sema_json(S.ShortScript)))

    def test_dogrulayici_hatalari_yakalar(self):
        s = yukle(KEDI)
        g = S.belgesel_bolum_sahneleri(s)
        son1, ilk2, son2 = g[1][-1], g[2][0], g[2][-1]

        s1 = s.model_copy(deep=True)
        S.belgesel_bolum_sahneleri(s1)[1][-1].narration = "Genç kedi artık sınırlarını tanıyor."
        self.assertTrue(any("Bölüm 1'in son cümlesi" in x for x in S.belgesel_sorunlari(s1)))

        s2 = s.model_copy(deep=True)
        S.belgesel_bolum_sahneleri(s2)[2][0].narration = "Şimdi sırada yetişkinlik var."
        self.assertTrue(any("Bölüm 2'nin ilk cümlesi" in x for x in S.belgesel_sorunlari(s2)))

        s3 = s.model_copy(deep=True)  # bir evrenin durak sahnesi silinirse
        s3.scenes = [sc for sc in s3.scenes if not (sc.belgesel.tur == "durak" and sc.belgesel.durak == 4)]
        self.assertTrue(any("'durak' sahnesi yok" in x for x in S.belgesel_sorunlari(s3)))

        s4 = s.model_copy(deep=True)  # bölüm başına kelime üst sınırı
        S.belgesel_bolum_sahneleri(s4)[1][1].narration += " " + " ".join(["kedi"] * 40)
        self.assertTrue(any("kelime" in x for x in S.belgesel_sorunlari(s4)))

        s5 = s.model_copy(deep=True)
        s5.belgesel.duraklar = s5.belgesel.duraklar[:3]
        self.assertTrue(any("evre/durak var" in x for x in S.belgesel_sorunlari(s5)))
        self.assertIsNotNone(son1 and ilk2 and son2)

    def test_normalize_devam_cumlesini_ekler(self):
        s = yukle(KEDI)
        son = S.belgesel_bolum_sahneleri(s)[1][-1]
        son.narration = son.narration.replace(" Devamı Bölüm 2'de.", "")
        son.belgesel.tur = "durak"
        S.normalize_belgesel(s)
        son = S.belgesel_bolum_sahneleri(s)[1][-1]
        self.assertTrue(son.narration.endswith("Devamı Bölüm 2'de."))
        self.assertEqual(son.belgesel.tur, "devam")
        self.assertEqual(S.belgesel_sorunlari(s), [])


# ---------------------------------------------------------------- iki bölüm
class IkiBolum(unittest.TestCase):
    def test_ayirma_baslik_aciklama(self):
        from shortgen import pipeline as PL
        s = yukle(KAN)
        parcalar = PL.belgesel_hazirla(s, dt.datetime(2026, 11, 6, 12, 0))
        self.assertEqual([p.series_part for p in parcalar], [1, 2])
        sid = {p.belgesel.seri_id for p in parcalar}
        self.assertEqual(len(sid), 1)
        self.assertTrue(next(iter(sid)).startswith("202611061200-"))
        for p in parcalar:
            no = p.series_part
            self.assertTrue(p.title.endswith(f" | Bölüm {no}/2"), p.title)
            self.assertLessEqual(len(p.title), 70)
            self.assertTrue(p.description.startswith(f"Mini Belgesel · Bölüm {no}/2"))
            self.assertEqual({sc.belgesel.bolum for sc in p.scenes}, {no})
        self.assertIn("devamı bir sonraki videoda", parcalar[0].description)
        self.assertEqual(len(parcalar[0].scenes) + len(parcalar[1].scenes), len(s.scenes))
        # ilk sahnenin format etiketi iki bölümde aynı
        self.assertEqual(parcalar[0].scenes[0].kicker, parcalar[1].scenes[0].kicker)
        # ayrılmış tek bölüm yeniden ayrılmaz (yeniden çizim)
        self.assertEqual(len(S.belgesel_bolumleri(parcalar[1])), 1)
        # başlık eki iki kez eklenmez, uzun başlık kısalır
        self.assertEqual(S.bolum_basligi("Kan | Bölüm 1/2", 2), "Kan | Bölüm 2/2")
        uzun = S.bolum_basligi("Çok " * 30, 1)
        self.assertLessEqual(len(uzun), 70)
        self.assertTrue(uzun.endswith("… | Bölüm 1/2"))

    def test_yayin_paketi_seri_alanlari(self):
        from shortgen import pipeline as PL
        parcalar = PL.belgesel_hazirla(yukle(KEDI))
        for p in parcalar:
            m = PL.yayin_paketi(p, "belgesel", [], True)
            self.assertEqual((m["bolum"], m["bolum_sayisi"]), (p.series_part, 2))
            self.assertEqual(m["seri_id"], p.belgesel.seri_id)
            self.assertEqual(m["structure"], "belgesel")

    def test_seri_etiketi_ve_eslesme(self):
        from shortgen import publish as P
        from shortgen import trends as tr
        self.assertEqual(P.SERIES_TAGS["belgesel"], "MiniBelgesel")
        m = json.loads((REPO / "templates" / "eslesme.json").read_text(encoding="utf-8"))
        self.assertEqual(m["yapi_sablon"]["belgesel"], "belgesel")
        sab = json.loads((REPO / "templates" / "belgesel.json").read_text(encoding="utf-8"))
        self.assertEqual((sab["renderer"], sab["yapi"]), ("belgesel", "belgesel"))
        self.assertEqual(tr.SERI_KALIP["belgesel"], "belgesel")
        self.assertEqual(tr.seri_tahmini("belgesel: Somonun göçü"), ("belgesel", "Somonun göçü"))
        self.assertEqual(tr.seri_tahmini("Mini belgesel: Somonun göçü"), ("belgesel", "Somonun göçü"))
        self.assertEqual(tr.seri_adi("belgesel"), "Mini Belgesel")
        for alan in ("doğa", "hayvan", "insan", "vücut"):
            self.assertIn(alan, tr.SYSTEM[tr.SYSTEM.index("- belgesel (Mini Belgesel)"):])
        self.assertEqual(takvim.seri_of({"structure": "belgesel", "template": "belgesel"}), "belgesel")


# ---------------------------------------------------------------- kurgu duman testi
class Kurgu(unittest.TestCase):
    """Her senaryonun iki bölümü pipeline.build ile kurulur (ses yok, görsel araması yok: yer tutucu çizim); video
    kodlanmaz, birkaç kare çizilir ve küçültülerek denetlenir."""

    @classmethod
    def setUpClass(cls):
        from shortgen import images, illustrate, kart as K, pipeline as PL
        cls.tmp = Path(tempfile.mkdtemp(prefix="belgesel-test-"))
        cls.sonuc = {}
        kayit = []

        def ornekle(scenes, words, out_mp4, voice_mp3, music, make_video, name, son_bekleme=None):
            from shortgen.brand import load_config
            v = make_video(load_config())
            for i, s in enumerate(scenes):
                tur = v.sahneler[i].tur
                if tur not in ("kanca", "devam", "ozet", "kapanis") and i != 1:
                    continue
                end = s.end if i < len(scenes) - 1 else words[-1].end + 1.0
                t = end - 0.05 if tur in ("devam", "ozet") else s.start + min(2.6, (end - s.start) * 0.7)
                im = v.frame(t)
                kayit.append((out_mp4.parent.name, tur, im.convert("RGB").resize((270, 480)), list(v.kutular),
                              v.koyu, v.bolum))
            out_mp4.write_bytes(b"")
            return out_mp4

        with mock.patch.object(images, "find_any", lambda *a, **k: None), \
                mock.patch.object(illustrate, "draw_scenes", lambda *a, **k: {}), \
                mock.patch.object(K, "render_frames", ornekle), mock.patch("builtins.print"):
            for ad, p in (("kedi", KEDI), ("kan", KAN)):
                for parca in PL.belgesel_hazirla(yukle(p)):
                    d = cls.tmp / f"{ad}-b{parca.series_part}"
                    PL.build(parca, d, use_voice=False, music=None, template="belgesel", use_drawings=False)
                    cls.sonuc[d.name] = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        cls.kareler = kayit

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_metadata(self):
        self.assertEqual(set(self.sonuc), {"kedi-b1", "kedi-b2", "kan-b1", "kan-b2"})
        for ad, m in self.sonuc.items():
            no = int(ad[-1])
            self.assertEqual((m["bolum"], m["bolum_sayisi"], m["template"]), (no, 2, "belgesel"))
            self.assertTrue(m["title"].endswith(f"Bölüm {no}/2"))
        self.assertEqual(self.sonuc["kedi-b1"]["seri_id"], self.sonuc["kedi-b2"]["seri_id"])
        self.assertNotEqual(self.sonuc["kedi-b1"]["seri_id"], self.sonuc["kan-b1"]["seri_id"])

    def test_gorunumler_ve_turler(self):
        koyu = {d: k for d, _, _, _, k, _ in self.kareler}
        self.assertEqual((koyu["kedi-b1"], koyu["kan-b1"]), (False, True), "kedi: Yaşam Çizgisi, kan: Kan Hattı")
        turler = {(d, t) for d, t, *_ in self.kareler}
        for g in ("kedi", "kan"):
            self.assertLessEqual({(f"{g}-b1", "kanca"), (f"{g}-b1", "devam"), (f"{g}-b2", "ozet"),
                                  (f"{g}-b2", "kapanis")}, turler)

    def test_bolum_etiketi_her_karede(self):
        """Sol üstteki 'BÖLÜM n /2' etiketi: Yaşam Çizgisi'nde kırmızı yırtık etiket, Kan Hattı'nda bilet (1. bölüm
        sarı, 2. bölüm açık renk)."""
        for d, tur, im, _, koyu, bolum in self.kareler:
            px = list(im.crop((18, 60, 82, 82)).convert("RGB").tobytes())
            px = [tuple(px[i:i + 3]) for i in range(0, len(px), 3)]  # 1080x1920'de x 72-330, y 240-330 (küçültülmüş)
            if not koyu:
                renk = lambda p: p[0] > 170 and p[1] < 90 and p[2] < 90  # noqa: E731 kırmızı
            elif bolum == 1:
                renk = lambda p: p[0] > 200 and p[1] > 170 and p[2] < 90  # noqa: E731 sarı
            else:
                renk = lambda p: min(p) > 200  # noqa: E731 açık
            oran = sum(1 for p in px if renk(p)) / len(px)
            self.assertGreater(oran, 0.25, (d, tur, oran))

    def test_bolum_yazilari(self):
        adlar = {(d, t): " | ".join(k for k, _ in kt) for d, t, _, kt, _, _ in self.kareler}
        self.assertIn("DEVAMI", adlar[("kedi-b1", "devam")])
        self.assertIn("BÖLÜM 2'DE", adlar[("kedi-b1", "devam")])
        self.assertIn("DEVAMI BÖLÜM 2'DE", adlar[("kan-b1", "devam")])
        self.assertIn("pano", adlar[("kan-b1", "devam")], "SONRAKİ DURAK panosu")
        for g in ("kedi", "kan"):
            self.assertIn("BÖLÜM 1'DE...", adlar[(f"{g}-b2", "ozet")])
            self.assertIn("şimdi", adlar[(f"{g}-b2", "ozet")])
            self.assertIn("not 2", adlar[(f"{g}-b2", "ozet")], "2-3 maddelik özet")

    def test_guvenli_alan(self):
        x0s, y0s, x1s, y1s = SAFE
        for d, tur, _, kt, _, _ in self.kareler:
            for ad, (x0, y0, x1, y1) in kt:
                self.assertTrue(x0 >= x0s and y0 >= y0s and x1 <= x1s + 0.5 and y1 <= y1s + 0.5,
                                f"{d} {tur}: {ad} {(round(x0), round(y0), round(x1), round(y1))}")


# ---------------------------------------------------------------- iki bölümlü onay
class Onay(unittest.TestCase):
    def setUp(self):
        from shortgen import telegram_bot as tb
        self.tb = tb
        self.tmp = Path(tempfile.mkdtemp(prefix="belgesel-onay-"))
        self.cagri = []
        self.p = [mock.patch.object(tb, "VIDEOS", self.tmp / "videos.json"),
                  mock.patch.object(tb, "api", lambda m, **k: self.cagri.append((m, k)) or {"message_id": 99}),
                  mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "1"})]
        for x in self.p:
            x.start()
        kayit = lambda tag, no, mid: {"tag": tag, "title": f"Kan | Bölüm {no}/2", "topic": "kan",  # noqa: E731
                                      "category": "insan vücudu", "template": "belgesel", "structure": "belgesel",
                                      "created": "2026-11-06T10:00:00+03:00", "status": "onay_bekliyor",
                                      "telegram_message_id": mid, "platforms": {}, "seri_id": "s1", "bolum": no,
                                      "bolum_sayisi": 2}
        tb.save(tb.VIDEOS, [kayit("short-1", 1, 11), kayit("short-2", 2, 12)])

    def tearDown(self):
        for x in self.p:
            x.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def v(self, tag):
        return self.tb._find(self.tb.load(self.tb.VIDEOS, []), tag)

    @staticmethod
    def belgesel_saati(t: dt.datetime) -> bool:
        t = t.astimezone(takvim.TR)
        return any(s == "belgesel" and hm == f"{t:%H:%M}" for hm, s in takvim.HAFTA.get(t.weekday(), []))

    def test_bolum1_onayi_bolum2yi_zamanlar(self):
        not_ = self.tb._approve("short-1", "best", "1", 11)
        v1, v2 = self.v("short-1"), self.v("short-2")
        self.assertEqual((v1["status"], v2["status"]), ("zamanlandi", "zamanlandi"))
        t1, t2 = (dt.datetime.fromisoformat(v["publish_at"]) for v in (v1, v2))
        self.assertGreater(t2, t1)
        self.assertTrue(self.belgesel_saati(t1) and self.belgesel_saati(t2), (t1, t2))
        # arada başka belgesel saati boş kalmaz: 2. bölüm 1. bölümden sonraki ilk belgesel saatinde
        self.assertEqual(t2, takvim.sonraki_saat("belgesel", [t1], t1))
        self.assertEqual(set(v2["schedule"].values()), {v2["publish_at"]})
        self.assertTrue(v2["otomatik_bolum"])
        self.assertIn("Bölüm 2/2 de otomatik zamanlandı", not_)
        # 2. bölümün mesajındaki düğme 'iptal' oldu
        dugme = [k for m, k in self.cagri if m == "editMessageReplyMarkup" and k["data"]["message_id"] == 12]
        self.assertIn("cancel:short-2", dugme[-1]["data"]["reply_markup"])

    def test_bolum1_iptali_bolum2yi_geri_alir(self):
        self.tb._approve("short-1", "best", "1", 11)
        not_ = self.tb._cancel("short-1", "1", self.v("short-1"))
        self.assertIn("2. bölüm de yeniden onay bekliyor", not_)
        self.assertEqual((self.v("short-1")["status"], self.v("short-2")["status"]), ("onay_bekliyor", "onay_bekliyor"))
        self.assertIsNone(self.v("short-2")["publish_at"])

    def test_elle_zamanlanan_bolum2_iptalde_kalir(self):
        self.tb._approve("short-2", "y19", "1", 12)
        self.tb._approve("short-1", "best", "1", 11)
        self.tb._cancel("short-1", "1", self.v("short-1"))
        self.assertEqual(self.v("short-2")["status"], "zamanlandi")

    def test_bolum1_reddi_bolum2yi_reddeder(self):
        not_ = self.tb._reject("short-1", "1", self.v("short-1"))
        self.assertIn("2. bölüm de reddedildi", not_)
        self.assertEqual(self.v("short-2")["status"], "reddedildi")

    def test_bolum2_kendi_saati_bolum1den_sonra(self):
        self.tb._approve("short-1", "now", "1", 11)  # 1. bölüm hemen: 2. bölüm sıradaki belgesel saati
        self.assertEqual(self.v("short-2")["status"], "zamanlandi")
        self.tb._cancel("short-2", "1", self.v("short-2"))
        uzak = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=9)).isoformat(timespec="seconds")
        self.tb._update("short-1", publish_at=uzak, schedule={p: uzak for p in self.tb.BEST_TIMES})
        t2 = self.tb._seri_saati("short-2")
        self.assertGreater(t2, dt.datetime.fromisoformat(uzak))
        self.assertTrue(self.belgesel_saati(t2))

    def test_panel_onayi_da_zamanlar(self):
        t = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).replace(second=0, microsecond=0)
        iso = t.isoformat()
        not_ = self.tb._schedule("short-1", {"schedule": {p: iso for p in self.tb.PLATFORM_NAMES}},
                                 self.v("short-1"), "1")
        self.assertIn("Bölüm 2/2", not_)
        t2 = dt.datetime.fromisoformat(self.v("short-2")["publish_at"])
        self.assertGreater(t2, t)

    def test_notify_seri_alanlarini_kaydeder(self):
        d = self.tmp / "out"
        d.mkdir()
        (d / "video.mp4").write_bytes(b"0")
        (d / "metadata.json").write_text(json.dumps({
            "title": "Kan | Bölüm 1/2", "topic": "kan", "category": "insan vücudu", "template": "belgesel",
            "structure": "belgesel", "created": "2026-11-06T10:00:00", "description": "Mini Belgesel · Bölüm 1/2",
            "hashtags": [], "seri_id": "s9", "bolum": 1, "bolum_sayisi": 2}), encoding="utf-8")
        with mock.patch("builtins.print"):
            self.tb.notify(d, "short-9")
        v = self.v("short-9")
        self.assertEqual((v["seri_id"], v["bolum"], v["bolum_sayisi"]), ("s9", 1, 2))


if __name__ == "__main__":
    unittest.main()
