#!/usr/bin/env python3
"""Bir Kitap Bir Dakika (kitap kalıbı) içerik ve seri testleri (ağ yok, Claude çağrısı yok):

- kamu malı sınırı (FSEK: Y yılında yazarı Y-71 ya da önce ölmüş kitap; 2026'da 1955 evet, 1956 hayır; ölüm yılı 0 hayır),
- normalize_kitap: telif koruması (ilk cümle, giris dahil sayfalardaki alıntılar; ilk cümle sağ sayfada tekrar
  edilmez), bölüm sırası, vurgu onarımı,
  'KANCA' kelimesi, kapanış cümlesi, sayfa uzunluğu, kapak/afiş araması; diğer kalıplara dokunmaması,
- üretim akışı (sahte Claude): yönergeler, web araması, doğrulayıcı ve editörün kitap alanlarını koruması, alıntı
  kalan senaryoda üretimin durması, diğer kalıpların doğrulama/editör isteminin değişmemesi,
- seri bağlantıları: FORCED_ONLY, trends (SERILER, SERI_IKON, SERI_KALIP, öneri yönergesi), publish (seri etiketi),
  eslesme.json, iş akışı açıklamaları,
- demo/kitap/ornek_donusum.json varsa şemaya ve kurallara uyması (çizici dalında gelir; yoksa atlanır).

    python -B tests/panel/test_kitap_icerik.py
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ORNEK = REPO / "demo" / "kitap" / "ornek_donusum.json"


def sahne(bolum, narration, sayfa="", vurgu="", **kw):
    return {"narration": narration, "kicker": "", "headline": kw.pop("headline", ["DÖNÜŞÜM"]), "highlight_line": -1,
            "strike": [], "theme": "paper", "image_mode": "none", "icon": "none", "kitap_bolum": bolum,
            "sayfa_metni": sayfa, "vurgu": vurgu, **kw}


ILK = "Gregor Samsa bir sabah huzursuz düşlerden uyandığında, kendini yatağında devasa bir böceğe dönüşmüş buldu."
# kitabın gerçek ilk cümlesi (özgün dilde; yalnız denetim içindir, ekrana yazılmaz)
KAYNAK = ("Als Gregor Samsa eines Morgens aus unruhigen Träumen erwachte, fand er sich in seinem Bett zu einem "
          "ungeheueren Ungeziefer verwandelt.")
# giris bölümünün sağ sayfası: kitabı tanıtan cümle (ilk cümle ya da künye sol sayfaya kendiliğinden basılır)
GIRIS = "1915'te yayımlanan bu uzun öykü, edebiyatın en ünlü açılışlarından biriyle başlar."
DONUSUM = {
    "topic": "Franz Kafka, Dönüşüm: bir sabah böceğe dönüşen pazarlamacı",
    "category": "dil ve kültür", "template": "kitap", "structure": "kitap",
    "title": "Dönüşüm: Kafka kapakta böcek istemedi",
    "description": "Kafka'nın Dönüşüm'ü bir sabah böceğe dönüşen bir adamı anlatır. Sen okudun mu?",
    "hashtags": ["dönüşümkafka", "kafka", "dönüşüm", "klasik", "bilgimakasi"],
    "sources": ["https://tr.wikipedia.org/wiki/Dönüşüm_(roman)"], "search_phrase": "Dönüşüm Kafka",
    "kitap": {"baslik": "Dönüşüm", "yazar": "Franz Kafka", "yil": 1915, "tur": "uzun öykü", "ozgun_dil": "Almanca",
              "yazar_olum": 1924, "ilk_cumle": ILK, "amblem": "kapi", "kapak_rengi": "lacivert",
              "ozgun_baslik": "Die Verwandlung", "kaynak_ilk_cumle": KAYNAK},
    "scenes": [
        sahne("giris", "Bir sabah uyanıyorsun ve dev bir böceğe dönüşmüşsün. Franz Kafka'nın Dönüşüm adlı kitabı tam "
                       "olarak böyle başlar.", GIRIS,
              "en ünlü açılışlarından"),
        sahne("konu", "Gregor Samsa bir pazarlamacıdır ve ailesinin bütün yükünü o taşır. Böcek olmuştur ama ilk "
                      "derdi trene yetişememek, işe geç kalmaktır.",
              "Ailesini geçindiren Gregor, böceğe dönüştüğü sabah bile işe geç kalmayı dert eder.", "işe geç kalmayı"),
        sahne("konu", "Kapının ardında ise annesi, babası, kız kardeşi Grete ve sabırsız şefi ondan bir açıklama "
                      "bekliyordur; kapı ise içeriden kilitlidir."),
        sahne("fikir", "Kitabın asıl sorusu şudur: İşe yaramadığımız gün, sevdiklerimiz bizi hâlâ sever mi? Kafka bu "
                       "soruyu bir ailenin sofrasında sorar.",
              "İşe yaramadığımız gün, sevdiklerimiz bizi hâlâ sever mi?", "hâlâ sever mi"),
        sahne("bilgi", "Üstelik Kafka, 1915'teki ilk baskı hazırlanırken yayıncısına mektup yazıp kapağa böceğin asla "
                       "çizilmemesini istemişti.",
              "Kafka, 1915'te yayıncısından kapağa böceğin asla çizilmemesini istedi.", "böceğin asla çizilmemesini",
              mascot="surprised"),
        sahne("bilgi", "Bu yüzden ilk baskının kapağında böcek yoktur; yalnızca elleriyle yüzünü kapatmış bir adam ve "
                       "aralık bir kapı görünür. Çizimi ressam Ottomar Starke yapmıştır."),
        sahne("soru", "Gregor'un yerinde olsan ilk kimi çağırırdın?", "Sen olsan ilk kimi çağırırdın?",
              "ilk kimi çağırırdın?"),
        sahne("soru", "Sence ailesi haksız mıydı? Okudun mu? Yorumlara yaz."),
    ],
}


class KitapIcerik(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO))
        # depodaki modüller taze yüklenir; sonra önceki modüller geri konur (aynı süreçte koşan diğer test dosyaları
        # kendi içe aktardıkları modüllerle sürer)
        cls._eski = {m: mod for m, mod in sys.modules.items() if m == "shortgen" or m.startswith("shortgen.")}
        for ad in cls._eski:
            del sys.modules[ad]
        import shortgen.pipeline as pl
        import shortgen.publish as P
        import shortgen.script as sc
        import shortgen.trends as tr
        cls.pl, cls.P, cls.sc, cls.tr = pl, P, sc, tr
        cls.demo = sc.load_script(REPO / "demo" / "demo_script.json")

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(REPO))
        for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
            del sys.modules[ad]
        sys.modules.update(cls._eski)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kitap_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.h = self.tmp / "history.jsonl"
        self.h.write_text("", encoding="utf-8")

    def yama(self, nesne, ad, deger):
        eski = getattr(nesne, ad)
        setattr(nesne, ad, deger)
        self.addCleanup(setattr, nesne, ad, eski)

    def senaryo(self, **kitap):
        s = self.sc.ShortScript.model_validate(json.loads(json.dumps(DONUSUM)))
        if kitap:
            s.kitap = s.kitap.model_copy(update=kitap)
        return s

    # ------------------------------------------------------------ kamu malı sınırı
    def test_kamu_mali_siniri(self):
        km = self.sc.kamu_mali
        self.assertTrue(km(1955, 2026), "2026'da 1955'te ölen yazarın kitabı kamu malı")
        self.assertFalse(km(1956, 2026), "1956'da ölenin koruması 2026 sonunda biter")
        self.assertTrue(km(1956, 2027))
        self.assertTrue(km(1924, 2026))
        for olum in (0, None, -5, 2030, "yok"):
            self.assertFalse(km(olum, 2026), olum)
        self.assertEqual(self.sc.KAMU_MALI_FARK, 71)

    def test_kamu_mali_kitapta_ilk_cumle_sayfasi(self):
        """İlk cümle sol sayfaya (kitap.ilk_cumle) basılır; giris sayfa_metni sağ sayfanın tanıtım cümlesidir."""
        for olum in (1924, 1955):
            s = self.sc.normalize_kitap(self.senaryo(yazar_olum=olum), year=2026)
            self.assertEqual(s.kitap.ilk_cumle, ILK, olum)
            self.assertEqual((s.scenes[0].sayfa_metni, s.scenes[0].vurgu), (GIRIS, "en ünlü açılışlarından"))
            self.assertEqual(self.sc.kitap_alintilari(s, 2026), [])
        # tırnaklı yazılmış ilk cümle tırnaksız saklanır; giris sayfasına ilk cümle yazılmışsa sağ sayfada tekrar
        # edilmez (sayfa boşalır, çizici dış sesten kısa parça yazar)
        for sayfa in (ILK, f"“{ILK}”", "Kitap şöyle başlar: " + ILK, ILK.split(",")[0]):
            s = self.senaryo(ilk_cumle=f"“{ILK}”")
            s.scenes[0].sayfa_metni = sayfa
            s = self.sc.normalize_kitap(s, year=2026)
            self.assertEqual((s.kitap.ilk_cumle, s.scenes[0].sayfa_metni, s.scenes[0].vurgu), (ILK, "", ""), sayfa)
        s = self.senaryo()
        s.scenes[0].sayfa_metni = "Bir sabah böceğe dönüşen bir adam."
        self.assertEqual(self.sc.normalize_kitap(s, year=2026).scenes[0].sayfa_metni,
                         "Bir sabah böceğe dönüşen bir adam.")

    def test_telifli_kitapta_alinti_yok(self):
        sc = self.sc
        for olum in (1956, 0, 2010):  # 0: yaşıyor ya da bilinmiyor -> kamu malı sayılmaz
            s = self.senaryo(yazar_olum=olum)
            s.scenes[1].sayfa_metni = "Gregor şöyle düşünür: “Bu yorucu meslek beni bitirecek” ve yine de işe gitmek ister."
            s.scenes[3].sayfa_metni = "Kitap şöyle der: " + ILK
            s = sc.normalize_kitap(s, year=2026)
            self.assertEqual(s.kitap.ilk_cumle, "", olum)
            self.assertEqual((s.scenes[0].sayfa_metni, s.scenes[0].vurgu), (GIRIS, "en ünlü açılışlarından"),
                             "alıntısız tanıtım cümlesi kalır (sol sayfa künyedir)")
            self.assertNotIn("“", s.scenes[1].sayfa_metni)
            self.assertNotIn("Bu yorucu meslek", s.scenes[1].sayfa_metni)
            self.assertEqual(s.scenes[1].sayfa_metni, "", "alıntı cümlesi bütünüyle çıkar (yarım cümle kalmaz)")
            self.assertEqual(s.scenes[3].sayfa_metni, "", "kitabın ilk cümlesini içeren sayfa boşalır")
            self.assertEqual(s.scenes[3].vurgu, "")
        # alıntının kaldığı tek parça (3 kelimeden az) sayfa boşalır
        s = self.senaryo(yazar_olum=0)
        s.scenes[1].sayfa_metni = "“Bu yorucu meslek beni bitirecek” dedi."
        self.assertEqual(sc.normalize_kitap(s, year=2026).scenes[1].sayfa_metni, "")
        # giris sayfası da aynı kurala uyar: ilk cümle ya da tırnaklı alıntı sağ sayfaya yazılmaz
        for sayfa, beklenen in ((ILK, ""), ("Kitap şöyle başlar: " + ILK, ""),
                                ("Kafka şöyle yazar: “Bu yorucu meslek beni bitirecek” ve öykü başlar.", ""),
                                ("Bu öykü 1915'te çıktı. Kafka şöyle yazar: “Bu yorucu meslek beni bitirecek” ve öykü "
                                 "başlar. Gregor bir pazarlamacıdır.", "Bu öykü 1915'te çıktı. Gregor bir pazarlamacıdır."),
                                ("Kafka şöyle yazar: “Bu yorucu meslek beni bitirecek.” Gregor yine de işe gider.",
                                 "Gregor yine de işe gider.")):
            s = self.senaryo(yazar_olum=0)
            s.scenes[0].sayfa_metni, s.scenes[0].vurgu = sayfa, ""
            s = sc.normalize_kitap(s, year=2026)
            self.assertEqual((s.kitap.ilk_cumle, s.scenes[0].sayfa_metni), ("", beklenen), sayfa)
            self.assertEqual(sc.kitap_alintilari(s, 2026), [])

    def test_kitap_alintilari(self):
        sc = self.sc
        s = self.senaryo(yazar_olum=0)
        s.scenes[0].sayfa_metni = ILK  # sağ sayfaya yazılmış ilk cümle
        s.scenes[2].narration = 'Gregor kendi kendine "Bu yorucu meslek beni bitirecek" diye düşünür.'
        s.title = "«Ben bir böceğe dönüştüm» diyen adam"
        bulunan = sc.kitap_alintilari(s, 2026)
        self.assertEqual(bulunan, ['3. sahnenin dış sesi: "Bu yorucu meslek beni bitirecek"',
                                   "1. sahnenin sayfa metni: kitabın ilk cümlesi",  # normalleştirmeden önce
                                   "başlık: «Ben bir böceğe dönüştüm»"])
        self.assertEqual(sc.kitap_alintilari(sc.normalize_kitap(s, 2026), 2026), [
            '3. sahnenin dış sesi: "Bu yorucu meslek beni bitirecek"', "başlık: «Ben bir böceğe dönüştüm»"],
            "normalleştirme sayfaları temizler; dış ses ve başlık yazarın işidir")
        # ilk cümle (kamu malı olmayan kitapta) tırnaksız da alıntıdır
        s = self.senaryo(yazar_olum=0)
        s.scenes[0].narration = ILK
        self.assertIn("1. sahnenin dış sesi: kitabın ilk cümlesi", sc.kitap_alintilari(s, 2026))
        # kitabın adı, kısa ifadeler ve kesme işareti alıntı sayılmaz; kamu malı kitapta liste boş
        s = self.senaryo(yazar_olum=0, baslik="Bir Ömür Nasıl Yaşanır")
        s.scenes[1].narration = "Kitabın adı “Bir Ömür Nasıl Yaşanır” olarak çevrildi; Kafka'nın 'böcek' sözü ünlüdür."
        s.kitap.ilk_cumle = ""
        self.assertEqual(sc.kitap_alintilari(s, 2026), [])
        s = self.senaryo()
        s.scenes[2].narration = 'Gregor "Bu yorucu meslek beni bitirecek" diye düşünür.'
        self.assertEqual(sc.kitap_alintilari(s, 2026), [], "kamu malı kitapta alıntı serbest")
        self.assertEqual(sc.kitap_alintilari(self.demo, 2026), [], "diğer kalıplar")

    def test_eser_adlari_alinti_sayilmaz(self):
        """Tırnaklı eser adları (özgün ad, film ya da başka eser, 'Ad: alt başlık', şapka ve ek farkı) üretimi durdurmaz;
        tırnaklı cümle ya da söz aktarımı durdurur; cümle olmayan parçanın yalnız tırnağı kalkar."""
        sc = self.sc
        s = self.senaryo(yazar_olum=2016, baslik="Bülbülü Öldürmek", ozgun_baslik="To Kill a Mockingbird",
                         ilk_cumle="", kaynak_ilk_cumle="When he was nearly thirteen, my brother Jem got his arm badly "
                                                         "broken at the elbow.")
        for metin in ("Romanın özgün adı “To Kill a Mockingbird” idi.",
                      "Harper Lee'nin “Go Set a Watchman” adlı ikinci romanı 2015'te çıktı.",
                      "Kitap “Bülbülü Öldürmek: Bir Amerikan Klasiği” adıyla yeniden basıldı.",
                      "“Bülbülü Öldürmek”in filmi 1962'de çekildi.",
                      "Hemingway'in “The Old Man and the Sea” adlı kitabı da o yıl ödül aldı.",
                      "Film 'To Kill a Mockingbird' adıyla vizyona girdi."):
            s.scenes[4].narration = metin
            self.assertEqual(sc.kitap_alintilari(s, 2026), [], metin)
        s.scenes[4].narration = "Kitap “Bulbulu Oldurmek” değil, “Bülbülü Öldürmek” diye yazılır."
        self.assertEqual(sc._alintilar(s.scenes[4].narration, ("Bülbülü Öldürmek",)), [])
        self.assertEqual(sc._alintilar("Roman “Saatleri Ayarlama Enstitüsü”dür.", ("Saatleri Âyarlama Enstitüsü",)), [])
        # cümle ya da söz aktarımı durdurur
        for metin, beklenen in (("Atticus der ki: “Birini anlamak için onun yerine geçmelisin”.", "“Birini"),
                                ("Scout “Bu kasabada herkes birbirini tanır.” diye anlatır.", "“Bu kasabada")):
            s.scenes[4].narration = metin
            bulunan = sc.kitap_alintilari(s, 2026)
            self.assertEqual(len(bulunan), 1, metin)
            self.assertIn(beklenen, bulunan[0])
        # cümle olmayan parça: tırnağı kalkar, doğrulayıcıya bildirilir, üretim durmaz
        s.scenes[4].narration = "Kitap “küçük bir kasabanın sessiz önyargıları” üzerine kuruludur."
        self.assertEqual(sc.kitap_alintilari(s, 2026), [])
        self.assertIn("kamu malı olmayan kitapta alıntı (çıkar, dolaylı anlat): 5. sahnenin dış sesi: "
                      "“küçük bir kasabanın sessiz önyargıları”", sc.kitap_sorunlari(s, 2026))
        sc.normalize_kitap(s, 2026)
        self.assertEqual(s.scenes[4].narration, "Kitap küçük bir kasabanın sessiz önyargıları üzerine kuruludur.")

    def test_tek_tirnakli_alinti_ve_kaynak_ilk_cumle(self):
        """Düz tek tırnaklı alıntı da yakalanır (ek ayıran kesme işareti tırnak sayılmaz); kamu malı olmayan kitapta
        ilk_cumle boş olsa da kaynak_ilk_cumle (kitabın gerçek ilk cümlesi) dış seste, sayfada, başlıkta ve açıklamada
        aranır."""
        sc = self.sc
        cumle = "Ben şimdi bir ölüyüm, bir kuyunun dibinde bir cesedim."
        s = self.senaryo(yazar_olum=0, baslik="Benim Adım Kırmızı", ilk_cumle="", kaynak_ilk_cumle=cumle)
        s.scenes[1].narration = f"Roman '{cumle}' cümlesiyle açılır."
        s.scenes[1].sayfa_metni = f"Roman '{cumle}' cümlesiyle açılır. Bir nakkaş kaybolur."
        s.title = f"'{cumle}'"
        s.description = f"Pamuk'un romanı '{cumle}' diye başlar."
        bulunan = sc.kitap_alintilari(s, 2026)
        for yer in ("2. sahnenin dış sesi: '", "2. sahnenin sayfa metni: '", "başlık: '", "açıklama: '"):
            self.assertTrue(any(b.startswith(yer) for b in bulunan), (yer, bulunan))
        sc.normalize_kitap(s, 2026)
        self.assertEqual(s.scenes[1].sayfa_metni, "Bir nakkaş kaybolur.", "alıntı cümlesi sayfadan bütünüyle çıkar")
        # kesme işaretli ekler tırnak değildir
        self.assertEqual(sc._alintilar("Kafka'nın 'böcek' sözü ve Brod'un Kafka'yı kurtarışı Dönüşüm'ü yaşattı."), [])
        # tırnaksız kaynak ilk cümle (tamamı ya da ilk 8 kelimesi) da durdurur
        for metin in (cumle, "Ben şimdi bir ölüyüm, bir kuyunun dibinde bir... diye başlar."):
            t = self.senaryo(yazar_olum=0, baslik="Benim Adım Kırmızı", ilk_cumle="", kaynak_ilk_cumle=cumle)
            t.scenes[0].narration = metin
            self.assertIn("1. sahnenin dış sesi: kitabın ilk cümlesi", sc.kitap_alintilari(t, 2026), metin)
        t = self.senaryo(yazar_olum=0, ilk_cumle="", kaynak_ilk_cumle=cumle)
        t.scenes[0].sayfa_metni = cumle
        self.assertEqual(sc.normalize_kitap(t, 2026).scenes[0].sayfa_metni, "")
        self.assertEqual(sc.kitap_alintilari(self.senaryo(kaynak_ilk_cumle=cumle), 2026), [], "kamu malı kitap")

    def test_telif_durunca_hata_turu_ve_not(self):
        """Telif durdurması KitapTelifHatasi'dır (RuntimeError); pipeline.main kısa notu Telegram için yazar."""
        sc, pl = self.sc, self.pl
        s = self.senaryo(yazar_olum=0)
        s.scenes[2].narration = 'Gregor "Bu yorucu meslek beni bitirecek" diye düşünür.'
        with self.assertRaises(sc.KitapTelifHatasi) as hata:
            self.uret(s, structure="kitap")
        self.assertIsInstance(hata.exception, RuntimeError)
        self.assertEqual(hata.exception.konu, s.topic)
        self.yama(pl, "TELIF_DURDU", self.tmp / "out" / "telif_durdu.txt")
        pl._telif_durdu_yaz(hata.exception)
        not_ = (self.tmp / "out" / "telif_durdu.txt").read_text(encoding="utf-8")
        self.assertIn("telif kuralı yüzünden durdu", not_)
        self.assertIn("Bu yorucu meslek", not_)
        y = (REPO / ".github" / "workflows" / "uret.yml").read_text(encoding="utf-8")
        self.assertIn("python -m shortgen.telegram_bot durdu output/telif_durdu.txt", y)
        self.assertLess(y.index("telegram_bot durdu"), y.index("Hata olursa senaryoyu"))
        tg = (REPO / "shortgen" / "telegram_bot.py").read_text(encoding="utf-8")
        self.assertIn('sys.argv[1] == "durdu"', tg)
        # eser adı geçen senaryo üretimi durdurmaz
        s = self.senaryo(yazar_olum=0, ozgun_baslik="Die Verwandlung")
        s.scenes[4].narration = "Kitabın özgün adı “Die Verwandlung” idi; Kafka kapağa böcek çizilmesini istemedi."
        out, _, _ = self.uret(s, structure="kitap")
        self.assertIn("“Die Verwandlung”", out.scenes[4].narration)

    def test_kaptan_kanca_silinmez(self):
        """Yalnız 'KANCA' etiketi silinir; cümle içindeki gerçek kelime (Peter Pan'daki Kaptan Kanca) kalır."""
        sc = self.sc
        s = self.senaryo(baslik="Peter Pan", yazar="J. M. Barrie", yazar_olum=1937, ilk_cumle="")
        sayfa = "Wendy ve kardeşleri, Kaptan Kanca'nın korsanlarıyla dolu bir adaya uçar."
        s.scenes[1].sayfa_metni, s.scenes[1].vurgu = sayfa, "Kaptan Kanca'nın korsanlarıyla"
        s.scenes[1].headline, s.scenes[1].kicker = ["KAPTAN KANCA", "VE KORSANLAR"], "KAPTAN KANCA"
        s.scenes[0].headline, s.scenes[0].highlight_line = ["KANCA", "PETER PAN"], 1
        s = sc.normalize_kitap(s, year=2026)
        self.assertEqual((s.scenes[1].sayfa_metni, s.scenes[1].vurgu), (sayfa, "Kaptan Kanca'nın korsanlarıyla"))
        self.assertEqual((s.scenes[1].headline, s.scenes[1].kicker), (["KAPTAN KANCA", "VE KORSANLAR"], "KAPTAN KANCA"))
        self.assertEqual((s.scenes[0].headline, s.scenes[0].highlight_line), (["PETER PAN"], 0))
        self.assertEqual(sc._kancasiz("KANCA - Peter Pan"), "Peter Pan")

    # ------------------------------------------------------------ bölüm düzeni
    def test_bolum_sirasi_onarilir(self):
        kb = self.sc.kitap_bolumleri
        dogru = ["giris", "konu", "konu", "fikir", "bilgi", "soru"]
        self.assertEqual(kb(dogru), dogru)
        self.assertEqual(kb(["giris", "konu", "fikir", "bilgi", "soru"]), ["giris", "konu", "fikir", "bilgi", "soru"])
        self.assertEqual(kb(["giris", "giris", "konu", "konu", "fikir", "fikir", "bilgi", "soru"]),
                         ["giris", "giris", "konu", "konu", "fikir", "fikir", "bilgi", "soru"])
        # hiç bölüm yazılmamışsa varsayılan plan (fazla sahneler önce konu, sonra bilgi); yazılmamış tek tük sahne
        # önceki bölümün devamı
        self.assertEqual(kb([""] * 5), ["giris", "konu", "fikir", "bilgi", "soru"])
        self.assertEqual(kb([""] * 7), ["giris", "konu", "konu", "fikir", "bilgi", "bilgi", "soru"])
        self.assertEqual(kb(["giris", "", "konu", "", "fikir", "bilgi", "soru"]),
                         ["giris", "giris", "konu", "konu", "fikir", "bilgi", "soru"])
        self.assertEqual(kb(["giris", "konu", "", "fikir", "", "soru"]), ["giris", "konu", "konu", "fikir", "bilgi", "soru"],
                         "devam sığmazsa sonraki bölüm: bilgi atlanamaz")
        # geri dönen sıra: en az değişiklikle düzelir
        self.assertEqual(kb(["giris", "konu", "fikir", "konu", "bilgi", "soru"]),
                         ["giris", "konu", "fikir", "fikir", "bilgi", "soru"])
        # son sahne her zaman soru, ilk sahne giris
        self.assertEqual(kb(["konu", "konu", "fikir", "bilgi", "bilgi", "fikir"]),
                         ["giris", "konu", "fikir", "bilgi", "bilgi", "soru"])
        # bölüm başına en çok 2 sahne
        out = kb(["giris", "konu", "konu", "konu", "fikir", "bilgi", "soru"])
        self.assertEqual(out, ["giris", "konu", "konu", "fikir", "fikir", "bilgi", "soru"])
        for raw in ([""] * 6, ["soru"] * 8, ["bilgi", "giris", "x", "soru", "konu", "fikir"], ["fikir"] * 10):
            out = kb(raw)
            sira = [self.sc.KITAP_BOLUMLERI.index(b) for b in out]
            self.assertEqual(sira, sorted(sira), raw)
            self.assertEqual(set(out), set(self.sc.KITAP_BOLUMLERI), raw)
            self.assertTrue(all(1 <= out.count(b) <= 2 for b in self.sc.KITAP_BOLUMLERI), (raw, out))
        # 5'ten az sahnede ara bölümler düşer, 10'dan çok sahnede bölüm başına daha çok sahne olur
        self.assertEqual(kb(["", "", "", ""]), ["giris", "konu", "fikir", "soru"])
        self.assertEqual(kb(["giris", "bilgi", "soru"]), ["giris", "bilgi", "soru"])
        uzun = kb([""] * 12)
        self.assertEqual((uzun[0], uzun[-1], len(uzun)), ("giris", "soru", 12))
        self.assertLessEqual(max(uzun.count(b) for b in uzun), 3)
        self.assertEqual(kb([]), [])

    def test_normalize_bolum_ve_sayfa(self):
        s = self.senaryo()
        s.scenes[2].kitap_bolum = ""      # yazılmamış: konunun devamı
        s.scenes[3].kitap_bolum = "x"     # tanınmayan değer şemadan geçmez; elle konulsa da düzelir
        s.scenes[1].sayfa_metni, s.scenes[2].sayfa_metni = "", "Gregor işe geç kalmayı dert eder."
        s.scenes[1].vurgu, s.scenes[2].vurgu = "", "işe geç kalmayı"
        s = self.sc.normalize_kitap(s, year=2026)
        self.assertEqual([x.kitap_bolum for x in s.scenes],
                         ["giris", "konu", "konu", "fikir", "bilgi", "bilgi", "soru", "soru"])
        self.assertEqual((s.scenes[1].sayfa_metni, s.scenes[1].vurgu),
                         ("Gregor işe geç kalmayı dert eder.", "işe geç kalmayı"), "bölümün sayfası ilk sahnesinde")
        self.assertEqual((s.scenes[2].sayfa_metni, s.scenes[2].vurgu), ("", ""))

    # ------------------------------------------------------------ vurgu, KANCA, kapanış, sayfa uzunluğu
    def test_vurgu_harfi_harfine(self):
        sc = self.sc
        sayfa = "İşe yaramadığımız gün, sevdiklerimiz bizi hâlâ sever mi?"
        self.assertEqual(sc._vurgu_onar(sayfa, "hâlâ sever mi"), "hâlâ sever mi")
        self.assertEqual(sc._vurgu_onar(sayfa, "İŞE YARAMADIĞIMIZ GÜN"), "İşe yaramadığımız gün", "Türkçe büyük harf")
        self.assertEqual(sc._vurgu_onar(sayfa, "gün sevdiklerimiz"), "gün, sevdiklerimiz", "noktalama farkı")
        self.assertEqual(sc._vurgu_onar(sayfa, "“hâlâ sever mi?”"), "hâlâ sever mi?", "tırnak gider, soru işareti kalır")
        self.assertEqual(sc._vurgu_onar(sayfa, "hâlâ sever mi!"), "hâlâ sever mi", "sayfada olmayan noktalama gider")
        self.assertEqual(sc._vurgu_onar(sayfa, "bizi sever"), "", "geçmiyorsa boş")
        self.assertEqual(sc._vurgu_onar("", "hâlâ"), "")
        s = self.senaryo()
        s.scenes[3].vurgu = "HÂLÂ SEVER Mİ"
        s.scenes[4].vurgu = "kapakta böcek yok"
        s = sc.normalize_kitap(s, year=2026)
        self.assertEqual(s.scenes[3].vurgu, "hâlâ sever mi")
        self.assertEqual(s.scenes[4].vurgu, "")
        for x in s.scenes:
            self.assertTrue(x.vurgu == "" or x.vurgu in x.sayfa_metni, x.vurgu)

    def test_kanca_ekranda_gorunmez(self):
        s = self.senaryo()
        s.scenes[0].narration = "Kanca: " + s.scenes[0].narration
        s.scenes[0].headline, s.scenes[0].highlight_line = ["KANCA", "DÖNÜŞÜM", "KAFKA"], 2
        s.scenes[0].kicker = "KANCA"
        s.scenes[1].sayfa_metni = "KANCA: " + s.scenes[1].sayfa_metni
        s.scenes[1].vurgu = "KANCA: işe geç kalmayı"
        s = self.sc.normalize_kitap(s, year=2026)
        self.assertEqual(s.scenes[0].narration, DONUSUM["scenes"][0]["narration"])
        self.assertEqual((s.scenes[0].headline, s.scenes[0].highlight_line), (["DÖNÜŞÜM", "KAFKA"], 1))
        self.assertEqual(s.scenes[0].kicker, "")
        self.assertEqual(s.scenes[1].sayfa_metni, DONUSUM["scenes"][1]["sayfa_metni"])
        self.assertEqual(s.scenes[1].vurgu, "işe geç kalmayı")
        for x in s.scenes:
            for metin in [x.sayfa_metni, x.vurgu, x.kicker, *x.headline]:
                self.assertNotRegex(metin.upper(), r"\bKANCA\b")

    def test_kapanis_sorusu(self):
        sc = self.sc
        for son, beklenen in (("Sence ailesi haksız mıydı? Yorumlara yaz.", "Sence ailesi haksız mıydı? " + sc.KITAP_KAPANIS),
                              ("Sence ailesi haksız mıydı?", "Sence ailesi haksız mıydı? " + sc.KITAP_KAPANIS),
                              ("Okudun mu? Yorumlara yaz.", "Okudun mu? Yorumlara yaz."),
                              ("Sen okudun mu? Yorumlara yaz!", "Sen okudun mu? Yorumlara yaz!"),
                              ("Okudun mu?", sc.KITAP_KAPANIS)):
            s = self.senaryo()
            s.scenes[-1].narration = son
            self.assertEqual(sc.normalize_kitap(s, year=2026).scenes[-1].narration, beklenen, son)
        s = self.senaryo()
        s.scenes[-2].sayfa_metni, s.scenes[-2].vurgu = "", ""  # soru bölümünün sayfası ilk sahnesinde
        self.assertEqual(sc.normalize_kitap(s, year=2026).scenes[-2].sayfa_metni, sc.KITAP_KAPANIS)

    def test_sayfa_en_cok_22_kelime(self):
        sc = self.sc
        uzun = " ".join(f"kelime{i}" for i in range(30))
        self.assertEqual(sc._sayfa_kirp(uzun), " ".join(f"kelime{i}" for i in range(22)) + "…")
        cumleli = "Bir iki üç dört beş altı yedi sekiz dokuz on. " + uzun
        self.assertEqual(sc._sayfa_kirp(cumleli), "Bir iki üç dört beş altı yedi sekiz dokuz on.", "tam cümlede kesilir")
        s = self.senaryo(ilk_cumle=" ".join(["uzun"] * 30) + ".")
        s = sc.normalize_kitap(s, year=2026)
        self.assertLessEqual(len(s.kitap.ilk_cumle.split()), sc.KITAP_SAYFA_KELIME)
        self.assertTrue(s.kitap.ilk_cumle.endswith("…"))
        self.assertEqual(s.scenes[0].sayfa_metni, GIRIS, "ilk cümle sol sayfada; sağ sayfa tanıtım cümlesi")

    def test_kapak_ve_afis_aranmaz(self):
        s = self.senaryo()
        s.scenes[4].image_mode = "framed"
        s.scenes[4].image_queries = ["Die Verwandlung first edition cover", "Franz Kafka portrait 1923",
                                     "Dönüşüm kitap kapağı", "Metamorphosis film poster"]
        s.scenes[1].image_mode, s.scenes[1].image_queries = "full", ["Die Verwandlung 1915 book jacket"]
        s = self.sc.normalize_kitap(s, year=2026)
        self.assertEqual((s.scenes[4].image_mode, s.scenes[4].image_queries), ("framed", ["Franz Kafka portrait 1923"]))
        self.assertEqual((s.scenes[1].image_mode, s.scenes[1].image_queries), ("none", []))

    def test_diger_kaliplara_dokunmaz(self):
        sc = self.sc
        for k in ("hikaye", "efsane", "nasil", "olsaydin"):
            d = self.demo.model_copy(update={"structure": k}, deep=True)
            d.scenes[0].narration = "KANCA: “Bu cümle tırnak içinde bir alıntıdır” dedi."
            once = d.model_dump()
            self.assertEqual(sc.normalize_kitap(d, year=2026).model_dump(), once, k)
            self.assertEqual(sc.kitap_sorunlari(d), [], k)
        # eski senaryolar yeni alanlar olmadan yüklenir (varsayılanlar)
        self.assertIsNone(self.demo.kitap)
        self.assertEqual({(x.kitap_bolum, x.sayfa_metni, x.vurgu) for x in self.demo.scenes}, {("", "", "")})

    def test_kitap_sorunlari(self):
        sc = self.sc
        self.assertEqual(sc.kitap_sorunlari(sc.normalize_kitap(self.senaryo(), year=2026), 2026), [])
        kisa = self.senaryo()
        kisa.scenes[2].narration = "Kapı kapalıdır."
        kisa.scenes[4].narration = "Kafka kapakta böcek istemedi."
        self.assertEqual(sc.kitap_sorunlari(kisa, 2026), ["toplam dış ses 99 kelime (125-140 olmalı, en çok 145)"])
        uzun = self.senaryo()
        uzun.scenes[2].narration += (" Ama kapı kilitli, anahtar içeride ve Gregor'un küçük bacakları kilidi çevirmeye "
                                     "yetmiyor. Dışarıdan sesler yükseliyor, şef sabırsızlanıyor ve annesi ağlamaya "
                                     "başlıyor.")
        self.assertEqual(sc.kitap_sorunlari(uzun, 2026), ["toplam dış ses 147 kelime (125-140 olmalı, en çok 145)"],
                         "1 dakikayı aşan senaryo")
        self.assertIn("kitap.kaynak_ilk_cumle boş", sc.kitap_sorunlari(self.senaryo(kaynak_ilk_cumle=""), 2026)[0])
        s = self.senaryo(yazar_olum=0)
        s.kitap = None
        s.scenes[3].kitap_bolum = "giris"
        s.scenes[4].vurgu = "yok böyle bir şey"
        s.scenes[-1].narration = "Sence?"
        sorun = sc.kitap_sorunlari(s, 2026)
        self.assertEqual(sorun[0], "kitap alanı (künye, amblem, kapak rengi) boş")
        self.assertTrue(any(x.startswith("kitap_bolum sırası bozuk (giris, konu, konu, giris") for x in sorun), sorun)
        self.assertIn("5. sahnenin vurgusu sayfa_metni içinde harfi harfine geçmiyor: yok böyle bir şey", sorun)
        self.assertIn(f"son cümle '{sc.KITAP_KAPANIS}' değil", sorun)
        s = self.senaryo(yazar_olum=1990)
        s.scenes[0].sayfa_metni = ILK
        self.assertIn("kitap kamu malı değil (yazar_olum 1990; 2026 yılında yazarı 1955 ya da önce ölmüş olmalı): "
                      "ilk_cumle boş olmalı", sc.kitap_sorunlari(s, 2026))
        self.assertTrue(any(x.startswith("kamu malı olmayan kitapta alıntı") for x in sc.kitap_sorunlari(s, 2026)))

    # ------------------------------------------------------------ yönergeler ve üretim akışı
    def test_kalip_kurallari_kitap(self):
        sc = self.sc
        self.assertEqual(sc.kalip_kurallari("kitap", False), "\n" + sc.KITAP_RULES)
        self.assertEqual(sc.kalip_kurallari("kitap", True), "\n" + sc.KITAP_RULES)
        k = sc.KITAP_RULES
        for parca in ("giris → konu → fikir → bilgi → soru", "her bölüm 1-3 sahne", "Sahne sayısı 8-12",
                      "en fazla 22 kelime", "HARFİ HARFİNE", "125-140 kelime, 145'yi GEÇMESİN", "55-62 saniye", "SÜRPRİZ YOK",
                      "kaynak_ilk_cumle (HER kitapta", "ozgun_baslik",
                      "yayınevi kapakları, yayınevi görselleri ve yayımlanmış çeviriler KULLANILMAZ",
                      f"yazarı {sc.YIL - 71} ya da daha önce ölmüşse", "KENDİ kısa", "İLK CÜMLE (alıntı yoksa KÜNYE)",
                      "HİÇBİR\n  alıntı yoktur", "Okudun mu? Yorumlara yaz.", "kitap kapağı, baskı, film afişi",
                      "yazar_olum (ölüm yılı; yaşıyorsa ya da emin değilsen 0)", sc.KITAP_YASAK):
            self.assertIn(parca, k)
        for a in sc.KITAP_AMBLEMLER + sc.KITAP_RENKLERI:
            self.assertIn(a, k)
        self.assertEqual(sc.KITAP_AMBLEMLER, ["kapi", "anahtar", "goz", "kalp", "gemi", "saat", "mektup", "tac", "kus",
                                              "agac", "dalga", "yildiz", "kilic", "maske", "ev", "ay"])
        self.assertEqual(sc.KITAP_RENKLERI, ["kirmizi", "sari", "lacivert", "yesil", "siyah"])
        sema = sc.ShortScript.model_json_schema()["$defs"]
        self.assertEqual(sema["KitapBilgi"]["properties"]["amblem"]["enum"], sc.KITAP_AMBLEMLER)
        self.assertEqual(sema["Scene"]["properties"]["kitap_bolum"]["enum"], ["", *sc.KITAP_BOLUMLERI])
        self.assertEqual(sc.STRUCTURES["kitap"][0], "BİR KİTAP BİR DAKİKA")
        self.assertIn("Okudun mu? Yorumlara yaz.", sc.STRUCTURES["kitap"][1])
        self.assertIn(sc.KITAP_YASAK, sc.STRUCTURES["kitap"][1])
        for k2 in ("hikaye", "efsane", "sayac", "neden", "nasil", "uretim", "olsaydin"):
            self.assertNotIn(sc.KITAP_RULES, sc.kalip_kurallari(k2, True), k2)

    def test_yalniz_elle_secilir(self):
        sc = self.sc
        self.assertIn("kitap", sc.FORCED_ONLY)
        for son in ([], ["kitap"], ["hikaye", "hikaye", "kitap"], ["efsane", "neden", "sayac"]):
            self.h.write_text("".join(json.dumps({"topic": f"t{i}", "structure": k}) + "\n" for i, k in enumerate(son)),
                              encoding="utf-8")
            self.assertNotIn("kitap", sc.allowed_structures(self.h), son)
        self.assertNotIn("- kitap:", sc.structure_ask(sc.allowed_structures(self.h)))
        self.assertNotIn("kitap", self.tr.OTOMATIK_SERILER)

    def uret(self, donen, editor=None, dogrulayici=None, **kw):
        """generate_script'i sahte Claude ile çalıştırır; (çıktı, [(şema, sistem, istem, web)], günlük)."""
        sc, cagri = self.sc, []

        def ask(prompt, schema, system, web=False):
            cagri.append((schema.__name__, system, prompt, web))
            s = donen.model_copy(deep=True)
            if schema is sc.ShortScript:
                return s
            if schema is sc.Review:
                return sc.Review(ok=True, problems=[], fixed=dogrulayici(s) if dogrulayici else s)
            return sc.Polished(notes=[], fixed=editor(s) if editor else s)
        self.yama(sc, "ask_claude", ask)
        with contextlib.redirect_stdout(io.StringIO()) as gunluk:
            out = sc.generate_script(self.h, kw.pop("konu", "Dönüşüm"), **kw)
        return out, cagri, gunluk.getvalue()

    def test_uretim_istemleri(self):
        sc = self.sc
        out, cagri, gunluk = self.uret(self.senaryo(), structure="kitap", kart=True)
        self.assertEqual([(c[0], c[3]) for c in cagri], [("ShortScript", True), ("Review", True), ("Polished", False)],
                         "kitap web aramasıyla araştırılarak yazılır")
        for c in cagri[:2]:
            self.assertIn(sc.KITAP_RULES, c[1])
            self.assertNotIn(sc.KART_RULES, c[1], "kart alanları kitap videosunda istenmez")
        self.assertIn("- kitap: " + sc.STRUCTURES["kitap"][1], cagri[0][2])
        self.assertIn("ANLATIM KALIBI (SABİT)", cagri[0][2])
        self.assertIn("yazarın ölüm yılı (kamu malı kararı buna bağlı)", cagri[0][2])
        for parca in ("yazar_olum; yaşıyorsa 0", f"yazar {sc.YIL - 71} ya da daha önce ölmemişse", "125-140 kelime",
                      "ilk perdeden sonraki dönüşleri", sc.KITAP_YASAK, '"kitap_bolum": "giris"', '"sayfa_metni"'):
            self.assertIn(parca, cagri[1][2])
        self.assertNotIn("Kitap kurallarında bulunan sorunlar", cagri[1][2], "kurallara uyan senaryo")
        self.assertIn(sc.EDITOR_KITAP, cagri[2][1])
        self.assertIn('"amblem": "kapi"', cagri[2][2], "editör kitap alanını görür")
        self.assertEqual(out.structure, "kitap")
        self.assertEqual(out.kitap.ilk_cumle, ILK)
        self.assertEqual([x.kitap_bolum for x in out.scenes],
                         ["giris", "konu", "konu", "fikir", "bilgi", "bilgi", "soru", "soru"])
        self.assertNotIn("UYARI kitap", gunluk)
        # kural dışı senaryo: sorunlar doğrulayıcıya gider, düzelmezse günlükte görünür
        kisa = self.senaryo()
        kisa.scenes[2].narration = "Kapı kapalıdır."
        kisa.scenes[4].narration = "Kafka kapakta böcek istemedi."
        kisa.scenes[2].kitap_bolum = "soru"
        _, cagri, gunluk = self.uret(kisa, structure="kitap")
        self.assertIn("Kitap kurallarında bulunan sorunlar (düzelt): toplam dış ses 99 kelime (125-140 olmalı, en çok 145); "
                      "kitap_bolum sırası bozuk (giris, konu, soru, fikir, bilgi, bilgi, soru, soru)", cagri[1][2])
        self.assertIn("UYARI kitap: toplam dış ses 99 kelime (125-140 olmalı, en çok 145)", gunluk)
        self.assertNotIn("UYARI kitap: kitap_bolum", gunluk, "bölüm sırası kodda düzelir")

    def test_dogrulayici_ve_editor_kitap_alanlarini_korur(self):
        sc = self.sc

        def dogrulayici(s):  # kitap alanını ve bölümleri düşürür
            s.kitap = None
            for x in s.scenes:
                x.kitap_bolum, x.sayfa_metni, x.vurgu = "", "", ""
            return s

        def editor(s):  # sayfaları, künyeyi ve bir sayıyı değiştirir
            s.kitap.baslik, s.kitap.amblem = "Değişim", "ay"
            s.scenes[1].sayfa_metni, s.scenes[1].vurgu = "Başka sayfa.", "Başka"
            s.scenes[4].narration = s.scenes[4].narration.replace("1915", "1916")
            s.scenes[3].narration = "Kitabın asıl sorusu: İşe yaramadığımız gün bizi kim sever?"
            return s
        out, _, gunluk = self.uret(self.senaryo(), structure="kitap", editor=editor, dogrulayici=dogrulayici)
        self.assertEqual((out.kitap.baslik, out.kitap.amblem), ("Dönüşüm", "kapi"))
        self.assertEqual([x.kitap_bolum for x in out.scenes], [x["kitap_bolum"] for x in DONUSUM["scenes"]])
        self.assertEqual(out.scenes[1].sayfa_metni, DONUSUM["scenes"][1]["sayfa_metni"])
        self.assertIn("1915", out.scenes[4].narration, "editör yılları değiştiremez")
        self.assertIn("5. sahnenin sayılarını değiştirdi", gunluk)
        self.assertEqual(out.scenes[3].narration, "Kitabın asıl sorusu: İşe yaramadığımız gün bizi kim sever?",
                         "sayısız dil düzeltmesi geçer")

    def test_alinti_kalirsa_uretim_durur(self):
        s = self.senaryo(yazar_olum=0)
        s.scenes[2].narration = 'Gregor "Bu yorucu meslek beni bitirecek" diye düşünür.'
        with self.assertRaises(RuntimeError) as hata:
            self.uret(s, structure="kitap")
        self.assertIn("kamu malı olmayan bir kitaptan alıntı", str(hata.exception))
        self.assertIn("Bu yorucu meslek", str(hata.exception))
        # doğrulayıcı alıntıyı çıkarırsa üretim sürer; ilk cümle boşalır (sol sayfa künye), tanıtım cümlesi kalır
        temiz = lambda x: x.model_copy(update={"scenes": [y.model_copy(update={"narration": y.narration.replace(  # noqa: E731
            '"Bu yorucu meslek beni bitirecek" diye', "mesleğinin onu bitireceğini")}) for y in x.scenes]}, deep=True)
        out, cagri, _ = self.uret(s, structure="kitap", dogrulayici=temiz, editor=temiz)  # sahte editör girdiyi görmez
        self.assertIn("kamu malı olmayan kitapta alıntı (çıkar, dolaylı anlat)", cagri[1][2])
        self.assertEqual((out.kitap.ilk_cumle, out.scenes[0].sayfa_metni), ("", GIRIS))
        self.assertEqual(self.sc.kitap_alintilari(out), [])

    def test_taslagin_ilk_cumlesi_dis_seste_kalirsa_uretim_durur(self):
        """Taslak kitabı kamu malı sanıp ilk cümlesini yazdı ve okudu; doğrulayıcı ölüm yılını düzeltti (kamu malı değil)
        ama dış sesi bıraktı: ilk cümle normalleştirmede silinse de dış seste aranır, üretim durur."""
        taslak = self.senaryo(yazar_olum=1924)
        taslak.scenes[0].narration = ILK + " Franz Kafka'nın Dönüşüm'ü böyle başlar."

        def dogrulayici(s):
            s.kitap.yazar_olum = 0
            return s
        with self.assertRaises(RuntimeError) as hata:
            self.uret(taslak, structure="kitap", dogrulayici=dogrulayici)
        self.assertIn("1. sahnenin dış sesi: kitabın ilk cümlesi", str(hata.exception))
        # yalnız baştan 8 kelimesi okunsa da alıntıdır
        taslak.scenes[0].narration = " ".join(ILK.split()[:8]) + " ve sonra her şey değişir. Kafka'nın Dönüşüm'ü."
        with self.assertRaises(RuntimeError):
            self.uret(taslak, structure="kitap", dogrulayici=dogrulayici)

    def test_kitap_telif(self):
        sc = self.sc
        s = self.senaryo(yazar_olum=0)
        s.scenes[2].narration = ILK
        self.assertEqual(sc.kitap_telif(s, 2026), ["3. sahnenin dış sesi: kitabın ilk cümlesi"])
        self.assertEqual(s.kitap.ilk_cumle, "", "ilk cümle yine de silinir")
        temiz = self.senaryo(yazar_olum=0)
        self.assertEqual(sc.kitap_telif(temiz, 2026), [])
        self.assertEqual(sc.kitap_telif(self.senaryo(), 2026), [], "kamu malı kitap")

    def test_diger_kaliplarin_istemi_degismez(self):
        """Doğrulayıcı ve editöre giden senaryo metninde kitap alanları yalnız kitap kalıbında yazılır."""
        sc = self.sc
        for k in ("hikaye", "efsane", "olsaydin"):
            d = self.demo.model_copy(update={"structure": k}, deep=True)
            metin = sc._senaryo_json(d)
            for alan in ('"kitap"', '"kitap_bolum"', '"sayfa_metni"', '"vurgu"'):
                self.assertNotIn(alan, metin, k)
            beklenen = json.loads(d.model_dump_json())
            beklenen.pop("kitap")
            beklenen.pop("belgesel")  # Mini Belgesel alanları yalnız belgesel kalıbında yazılır
            for x in beklenen["scenes"]:
                for alan in ("kitap_bolum", "sayfa_metni", "vurgu"):
                    x.pop(alan)
                x.pop("cizgi")  # Çizgi Roman tarifi yalnız dolu olduğunda yazılır
                x.pop("belgesel")
            self.assertEqual(json.loads(metin), beklenen, k)
            _, cagri, _ = self.uret(d, konu="muz", structure=k)
            for c in cagri:
                self.assertNotIn(sc.KITAP_RULES, c[1], k)
                self.assertNotIn(sc.EDITOR_KITAP, c[1], k)
                self.assertNotIn('"sayfa_metni"', c[2], k)

    # ------------------------------------------------------------ seri bağlantıları
    def test_trends_kitap_serisi(self):
        tr, sc = self.tr, self.sc
        self.assertEqual(list(tr.SERILER)[-2:], ["kitap", "belgesel"])
        self.assertEqual(tr.SERILER["kitap"], "Bir Kitap Bir Dakika")
        self.assertEqual(tr.SERI_IKON["kitap"], "📖")
        self.assertEqual(len(set(tr.SERI_IKON.values())), len(tr.SERI_IKON), "her serinin simgesi ayrı")
        self.assertEqual(tr.SERI_KALIP["kitap"], "kitap")
        self.assertEqual(tr.kalip_of({"seri": "kitap"}), "kitap")
        self.assertEqual(tr.Suggestion.model_json_schema()["properties"]["seri"]["enum"], list(tr.SERILER))
        self.assertIn("SEKİZ SERİDE", tr.SYSTEM)
        self.assertNotIn("ALTI SERİDE", tr.SYSTEM)
        for parca in ("- kitap (Bir Kitap Bir Dakika):", "yıl dönümü", "uyarlaması", "edebiyat ödülü",
                      "okul okuma listeleri", "en az biri Türk edebiyatından", f"yazarı {sc.YIL - 71}", "kamu malıdır",
                      "videoda alıntı olmaz", "Kafka yayıncısından kapağa böceğin çizilmemesini istedi", sc.KITAP_YASAK,
                      "sonunu\n  ya da büyük sürprizini"):
            self.assertIn(parca, tr.SYSTEM)
        # /oneri: sekiz seri, kitap ve Mini Belgesel üçüncü mesajda
        ortak = dict(hook="kanca", trend="neden", scope="TR", category="dil ve kültür", score=5)
        items = [dict(topic=f"{s} {i}", seri=s, **ortak) for s in tr.SERILER for i in range(3)]
        msj = tr.mesajlar(items)
        self.assertEqual(len(msj), 3)
        self.assertTrue(msj[2][0].startswith("🗂 Bugünün konu önerileri (3/3)\n\n📖 Bir Kitap Bir Dakika\n19. "))
        d = tr.damga(items)
        self.assertEqual(msj[2][1][0], [("🎬 19", f"tp:{d}:18"), ("🎬 20", f"tp:{d}:19"), ("🎬 21", f"tp:{d}:20")])
        self.assertIn("\n🎞 Mini Belgesel\n22. ", msj[2][0])

    def test_seri_etiketi_ve_aciklama(self):
        P, pl = self.P, self.pl
        self.assertEqual(P.SERIES_TAGS["kitap"], "BirKitapBirDakika")
        self.assertEqual(set(P.SERIES_TAGS), set(self.tr.SERI_KALIP.values()))
        s = self.senaryo()
        meta = pl.yayin_paketi(s, "kitap", [], True)
        self.assertEqual(meta["hashtags"], ["dönüşümkafka", "kafka", "dönüşüm", "BirKitapBirDakika", "bilgimakasi"])
        self.assertEqual(meta["description"], DONUSUM["description"] +
                         "\n\n#dönüşümkafka #kafka #dönüşüm #BirKitapBirDakika #bilgimakasi")
        self.assertEqual(P.apply_series_tag(meta), meta)
        self.assertEqual(P.apply_disclaimer(meta), meta, "kitap videosunda uyarı satırı yok")
        for metin in (P.youtube_description(meta), P.instagram_caption(meta), P.tiktok_caption(meta)):
            self.assertEqual(metin.count("#BirKitapBirDakika"), 1)
            self.assertNotIn("yapay zekâ", metin)
        # görsel kullanıldıysa tek satırlık atıf etiketlerden sonra
        kredi = pl.images.ImageCredit(file="f", title="t", author="John Doe", license="CC BY-SA 4.0", page="p")
        self.assertTrue(pl.yayin_paketi(s, "kitap", [kredi], True)["description"].endswith(
            "#BirKitapBirDakika #bilgimakasi\n\n📷 John Doe (CC BY-SA 4.0)"))

    def test_eslesme_ve_is_akislari(self):
        m = json.loads((REPO / "templates" / "eslesme.json").read_text(encoding="utf-8"))
        self.assertEqual(m["yapi_sablon"]["kitap"], "kitap")
        self.assertIn("'kitap' (Bir Kitap Bir Dakika)", m["yapi_sablon"]["_aciklama"])
        if not (REPO / "templates" / "kitap.json").exists():  # çizici dalı gelmeden: kitap senaryosu kategoriye düşer
            self.assertNotEqual(self.pl.pick_template(self.senaryo()), "kitap")
        for ad, alanlar in (("uret.yml", ("template", "kalip")), ("ornek.yml", ("sablon", "kalip"))):
            y = (REPO / ".github" / "workflows" / ad).read_text(encoding="utf-8")
            for alan in alanlar:
                aciklama = re.search(rf"\n      {alan}:\n        description: (.+)\n", y).group(1)
                self.assertIn("kitap", aciklama, (ad, alan))

    def test_ornek_senaryo_semaya_uyar(self):
        """Çizicinin demo senaryosu (demo/kitap/ornek_donusum.json, çizici dalında) veri sözleşmesine uyar."""
        if not ORNEK.exists():
            self.skipTest("demo/kitap/ornek_donusum.json bu dalda yok (çizici dalında gelir)")
        sc = self.sc
        s = sc.load_script(ORNEK)
        self.assertEqual(s.structure, "kitap")
        self.assertIsNotNone(s.kitap)
        self.assertIn(s.kitap.amblem, sc.KITAP_AMBLEMLER)
        self.assertIn(s.kitap.kapak_rengi, sc.KITAP_RENKLERI)
        raw = [x.kitap_bolum for x in s.scenes]
        self.assertEqual(raw, sc.kitap_bolumleri(raw), "bölüm sırası")
        for x in s.scenes:
            self.assertTrue(x.vurgu == "" or x.vurgu in x.sayfa_metni, x.vurgu)
            self.assertLessEqual(len(x.sayfa_metni.split()), sc.KITAP_SAYFA_KELIME)
        if not sc.kamu_mali(s.kitap.yazar_olum, 2026):
            self.assertEqual(s.kitap.ilk_cumle, "")
        self.assertEqual(sc.kitap_alintilari(s, 2026), [])
        self.assertTrue(sc._duz(s.scenes[-1].narration).endswith(sc._duz(sc.KITAP_KAPANIS)))
        n = sc.normalize_kitap(s.model_copy(deep=True), year=2026)
        self.assertEqual([x.kitap_bolum for x in n.scenes], raw)
        self.assertEqual(n.model_dump(), s.model_dump(), "kurallara uyan demo normalleştirmede hiç değişmez")
        self.assertEqual(sc.kitap_sorunlari(s, 2026), [])
        # sağ sayfalarda ilk cümle tekrar edilmez (sol sayfada basılı)
        self.assertNotIn(sc._duz(s.kitap.ilk_cumle), sc._duz(" ".join(x.sayfa_metni for x in s.scenes)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
