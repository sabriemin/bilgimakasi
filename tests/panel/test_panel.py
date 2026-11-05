#!/usr/bin/env python3
"""Panelin Python tarafı testleri (gerçek Telegram/GitHub çağrısı yok; durum geçici klasörde).

    python -B tests/panel/test_panel.py              # tüm testler
    python -B tests/panel/test_panel.py --dugme <kök>  # düğme senaryolarını <kök>/shortgen ile çalıştırıp JSON yazar

fixtures/buttons_golden.json panelden ÖNCEKİ telegram_bot.py ile üretildi: Telegram düğmelerinin davranışı
(giden Telegram/GitHub çağrıları ve durum değişiklikleri) yeniden düzenlemeden sonra da aynı olmalı.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import io
import json
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures"
UTC = _dt.timezone.utc
TRZ = _dt.timezone(_dt.timedelta(hours=3))
SIMDI = _dt.datetime(2026, 11, 4, 21, 45, tzinfo=UTC)  # 5 Kasım 00:45 TR
CHAT = "424242"


class FakeDateTime(_dt.datetime):
    simdi = SIMDI

    @classmethod
    def now(cls, tz=None):
        t = cls.simdi
        return t.astimezone(tz) if tz else t.replace(tzinfo=None)


FAKE_DT = types.SimpleNamespace(datetime=FakeDateTime, timezone=_dt.timezone, timedelta=_dt.timedelta,
                                time=_dt.time, date=_dt.date)


class Yanit:
    def __init__(self, status=200, data=None):
        self.status_code, self._d = status, data if data is not None else {"ok": True, "result": {"message_id": 900}}
        self.ok = status < 400
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(self._d)

    def json(self):
        return self._d


class SahteRequests:
    """telegram_bot.requests yerine: Telegram ve GitHub dispatch çağrılarını kaydeder."""

    def __init__(self):
        self.cagrilar: list[dict] = []
        self.dispatch_durum = 204

    def post(self, url, timeout=None, data=None, json=None, headers=None, files=None, **kw):  # noqa: A002
        if "api.telegram.org" in url:
            d = dict(data or {})
            for k in ("reply_markup", "commands"):
                if isinstance(d.get(k), str):
                    d[k] = __import__("json").loads(d[k])
            self.cagrilar.append({"tg": url.rsplit("/", 1)[1], "data": d})
            return Yanit()
        m = re.search(r"/actions/workflows/([\w.]+)/dispatches$", url)
        if m:
            self.cagrilar.append({"gh": m.group(1), "json": json})
            return Yanit(self.dispatch_durum, {})
        raise AssertionError("beklenmeyen istek: " + url)

    def get(self, url, **kw):
        raise AssertionError("beklenmeyen GET: " + url)


ONERILER = json.loads((FIX / "state" / "oneriler.json").read_text(encoding="utf-8"))["items"]


def kok_hazirla(kaynak: Path) -> Path:
    """Geçici proje kökü: shortgen paketi + şablonlar + fikstür durumu."""
    root = Path(tempfile.mkdtemp(prefix="panel_test_"))
    shutil.copytree(kaynak / "shortgen", root / "shortgen", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "templates", root / "templates")
    (root / "demo").mkdir()
    shutil.copy(REPO / "demo" / "demo_script.json", root / "demo" / "demo_script.json")
    durum_sifirla(root)
    return root


def durum_sifirla(root: Path) -> None:
    st = root / "state"
    if st.exists():
        shutil.rmtree(st)
    shutil.copytree(FIX / "state", st)
    (root / "history.jsonl").write_text("", encoding="utf-8")


def kur(root: Path):
    """root/shortgen'i içe aktarır ve dış dünyayı taklit eder."""
    os.environ.update(TELEGRAM_BOT_TOKEN="123:TEST", TELEGRAM_CHAT_ID=CHAT, TG_WEBHOOK="1",
                      GITHUB_REPOSITORY="sabriemin/bilgimakasi", GITHUB_TOKEN="ghs_TEST", GITHUB_REF_NAME="main")
    for k in ("BEST_TIMES", "EXTRA_TIMES", "MIN_GAP_HOURS"):
        os.environ.pop(k, None)
    sys.path.insert(0, str(root))
    for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
        del sys.modules[ad]
    import shortgen.telegram_bot as tb
    import shortgen.trends as trends
    assert Path(tb.__file__).resolve().parent == (root / "shortgen").resolve()
    req = SahteRequests()
    tb.requests = req
    tb.dt = FAKE_DT
    tb._refresh_videos = lambda: None
    trends.load_saved = lambda: [dict(x) for x in ONERILER]
    return tb, req


def videolar(tb) -> dict:
    return {v["tag"]: v for v in json.loads(tb.VIDEOS.read_text(encoding="utf-8"))}


def cq(data, mid=2):
    return {"callback_query": {"id": "q1", "from": {"id": int(CHAT)}, "data": data,
                               "message": {"message_id": mid, "chat": {"id": int(CHAT)},
                                           "reply_markup": {"inline_keyboard": [[{"text": "x", "callback_data": data}]]}}}}


def msg(text):
    return {"message": {"message_id": 70, "chat": {"id": int(CHAT)}, "text": text}}


T, Z, Y = "short-20261104-1019", "short-20261104-2023", "short-20261104-1307"
DUGME_SENARYOLARI = [
    ("ok", cq(f"ok:{T}")), ("back", cq(f"back:{T}")), ("at best", cq(f"at:{T}:best")), ("at now", cq(f"at:{T}:now")),
    ("at b19", cq(f"at:{T}:b19")), ("at y12", cq(f"at:{T}:y12")), ("no", cq(f"no:{T}")),
    ("cancel zamanlandi", cq(f"cancel:{Z}", 44)), ("cancel paylaşılmış", cq(f"cancel:{Y}", 8)),
    ("rt", cq(f"rt:{Y}", 8)), ("tp", cq("tp:_:1")), ("tp yok", cq("tp:_:9")),
    ("/durum", msg("/durum")), ("/saatler", msg("/saatler")), ("/uret", msg("/uret kara delikler")),
    ("/oneri", msg("/oneri")), ("/start", msg("/start")),
]


def dugme_senaryolari(root: Path) -> list:
    tb, req = kur(root)
    out = []
    for ad, u in DUGME_SENARYOLARI:
        durum_sifirla(root)
        req.cagrilar.clear()
        once = videolar(tb)
        with contextlib.redirect_stdout(io.StringIO()):
            tb.process_update(u, CHAT)
        sonra = videolar(tb)
        fark = {t: sonra[t] for t in sonra if sonra[t] != once.get(t)}
        out.append({"ad": ad, "cagrilar": req.cagrilar[:], "degisen": fark})
    return out


# ====================================================================== testler
class Ortak(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = kok_hazirla(REPO)
        cls.tb, cls.req = kur(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        sys.path.remove(str(cls.root))

    def setUp(self):
        durum_sifirla(self.root)
        self.req.cagrilar.clear()
        self.req.dispatch_durum = 204
        FakeDateTime.simdi = SIMDI

    def panel(self, **p):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.tb.process_update({"panel": p}, CHAT)
        self.cikti = out.getvalue()
        return self.req.cagrilar[:]

    def tg(self, cagrilar, yontem=None):
        return [c for c in cagrilar if "tg" in c and (yontem is None or c["tg"] == yontem)]

    def mesajlar(self, cagrilar):
        return [c["data"]["text"] for c in self.tg(cagrilar, "sendMessage")]

    def vid(self, tag):
        return videolar(self.tb)[tag]

    def video_degistir(self, tag, **alanlar):
        vs = json.loads(self.tb.VIDEOS.read_text(encoding="utf-8"))
        for v in vs:
            if v["tag"] == tag:
                v.update(alanlar)
        self.tb.VIDEOS.write_text(json.dumps(vs, ensure_ascii=False), encoding="utf-8")


class DugmeDavranisi(Ortak):
    def test_dugmeler_onceki_surumle_ayni(self):
        golden = json.loads((FIX / "buttons_golden.json").read_text(encoding="utf-8"))
        yeni = dugme_senaryolari(self.root)
        self.tb, self.req = kur(self.root)  # kur() modülü yeniden yükledi
        type(self).tb, type(self).req = self.tb, self.req
        self.assertEqual(len(yeni), len(golden))
        for g, y in zip(golden, yeni):
            if g["ad"] == "/start":  # tek bilinçli fark: yardım metninde /panel satırı
                self.assertEqual(y["cagrilar"][0]["data"]["text"], g["cagrilar"][0]["data"]["text"].replace(
                    "/yardim: bu liste", "/panel: yönetim paneline giriş bağlantısı\n/yardim: bu liste"))
                continue
            self.assertEqual(y, g, g["ad"])

    def test_komut_menusunde_panel(self):
        self.assertIn({"command": "panel", "description": "Yönetim paneline giriş bağlantısı"}, self.tb.COMMANDS)


class PanelIslemleri(Ortak):
    def test_onay_en_iyi_saat(self):
        c = self.panel(action="approve", tag=T, code="best", rid="r1")
        v = self.vid(T)
        self.assertEqual(v["status"], "zamanlandi")
        self.assertEqual(set(v["schedule"]), {"youtube", "instagram", "tiktok"})
        self.assertEqual(v["publish_at"], min(v["schedule"].values()))
        kb = self.tg(c, "editMessageReplyMarkup")
        self.assertEqual(kb[0]["data"]["message_id"], 2)
        self.assertEqual(kb[0]["data"]["reply_markup"], {"inline_keyboard": [[{"text": "🚫 Paylaşımı iptal et",
                                                                               "callback_data": f"cancel:{T}"}]]})
        m = self.tg(c, "sendMessage")[-1]["data"]
        self.assertTrue(m["text"].startswith("🖥 Panelden: ✅ Onaylandı. Her platform kendi en iyi saatinde"))
        self.assertTrue(m["text"].endswith(v["title"]))
        self.assertEqual(m["reply_to_message_id"], 2)

    def test_onay_kodlari_dugmeyle_ayni_saati_verir(self):
        for kod, beklenen in (("now", "2026-11-04T21:45:00+00:00"), ("b12", "2026-11-05T09:00:00+00:00"),
                              ("b19", "2026-11-05T16:00:00+00:00"), ("y12", "2026-11-06T09:00:00+00:00"),
                              ("y19", "2026-11-06T16:00:00+00:00")):
            durum_sifirla(self.root)
            self.panel(action="approve", tag=T, code=kod)
            v = self.vid(T)
            self.assertEqual((v["status"], v["publish_at"], v["schedule"]), ("zamanlandi", beklenen, None), kod)

    def test_cift_onay_ikinci_kez_bir_sey_degistirmez(self):
        self.panel(action="approve", tag=T, code="b19")
        ilk = self.vid(T)
        self.req.cagrilar.clear()
        c = self.panel(action="approve", tag=T, code="now")
        self.assertEqual(self.vid(T), ilk, "ikinci onay planı değiştirmemeli")
        self.assertIn("İşlem yapılmadı", self.mesajlar(c)[0])
        # kapının '⏳ İşleniyor' kilidi geri alınır: durumuna uygun düğme
        self.assertEqual(self.tg(c, "editMessageReplyMarkup")[0]["data"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"],
                         f"cancel:{T}")

    def test_gecersiz_saat_kodu(self):
        c = self.panel(action="approve", tag=T, code="x99")
        self.assertEqual(self.vid(T)["status"], "onay_bekliyor")
        self.assertIn("⚠️ İşlem yapılamadı", self.mesajlar(c)[-1])

    def test_reddet_ve_seri(self):
        self.video_degistir(T, title="Melas Seli (1. Bölüm)")
        (self.root / "state" / "seri.json").write_text(json.dumps({"bekleyen": {"title": "Melas Seli (1. Bölüm)"}}),
                                                       encoding="utf-8")
        c = self.panel(action="reject", tag=T)
        self.assertEqual(self.vid(T)["status"], "reddedildi")
        self.assertEqual(self.tg(c, "editMessageReplyMarkup")[0]["data"]["reply_markup"], {"inline_keyboard": []})
        self.assertEqual(self.mesajlar(c), ["🖥 Panelden: ❌ Reddedildi. Serinin 2. bölümü de iptal edildi.\nMelas Seli (1. Bölüm)"])
        self.assertNotIn("bekleyen", json.loads((self.root / "state" / "seri.json").read_text()))
        self.req.cagrilar.clear()
        c = self.panel(action="reject", tag=T)
        self.assertIn("İşlem yapılmadı", self.mesajlar(c)[0])

    def test_iptal(self):
        c = self.panel(action="cancel", tag=Z)
        v = self.vid(Z)
        self.assertEqual((v["status"], v["publish_at"], v["schedule"]), ("onay_bekliyor", None, None))
        self.assertEqual(self.tg(c, "editMessageReplyMarkup")[0]["data"]["message_id"], 44)
        self.assertEqual(self.mesajlar(c)[0], "🖥 Panelden: Paylaşım iptal edildi, video yeniden onay bekliyor.\n" + v["title"])
        c = self.panel(action="cancel", tag=Y)
        self.assertEqual(self.vid(Y)["status"], "yayinlandi")

    def test_tekrar_dene(self):
        self.video_degistir(Y, status="kismen", platforms={"youtube": {"status": "ok", "url": "u"},
                                                            "instagram": {"status": "hata", "error": "x"}})
        c = self.panel(action="retry", tag=Y)
        v = self.vid(Y)
        self.assertEqual((v["status"], v["schedule"], v["publish_at"]), ("zamanlandi", None, "2026-11-04T21:45:00+00:00"))
        self.assertEqual(self.tg(c, "editMessageReplyMarkup")[0]["data"]["reply_markup"], {"inline_keyboard": []})
        self.assertTrue(self.mesajlar(c)[0].startswith("🖥 Panelden: 🔁 Hatalı platformlar"))
        self.req.cagrilar.clear()
        self.panel(action="retry", tag=T)  # onay bekleyen video: değişmez
        self.assertEqual(self.vid(T)["status"], "onay_bekliyor")

    def test_duzenle(self):
        c = self.panel(action="edit", tag=T, title="  Yeni <b>Başlık</b> & ötesi ", description="Yeni bilgi metni.\r\n")
        v = self.vid(T)
        self.assertEqual(v["title"], "Yeni <b>Başlık</b> & ötesi")
        self.assertEqual(v["duzenleme"]["description"], "Yeni bilgi metni.")
        cap = self.tg(c, "editMessageCaption")[0]["data"]
        self.assertTrue(cap["caption"].startswith("🎬 <b>Yeni &lt;b&gt;Başlık&lt;/b&gt; &amp; ötesi</b>"))
        self.assertEqual(cap["parse_mode"], "HTML")
        self.assertEqual(cap["reply_markup"]["inline_keyboard"][0][0]["callback_data"], f"ok:{T}")
        self.assertTrue(self.mesajlar(c)[0].startswith("🖥 Panelden: ✏️ Başlık ve açıklama düzenlendi"))

    def test_duzenle_sinirlar_ve_durum(self):
        for title, desc in (("a" * 101, "b"), ("", "b"), ("a", ""), ("a", "b" * 2001)):
            durum_sifirla(self.root)
            self.req.cagrilar.clear()
            c = self.panel(action="edit", tag=T, title=title, description=desc)
            self.assertNotIn("duzenleme", self.vid(T))
            self.assertIn("⚠️ İşlem yapılamadı", self.mesajlar(c)[-1])
        self.panel(action="edit", tag=T, title="a" * 100, description="ç" * 2000)
        self.assertEqual(self.vid(T)["title"], "a" * 100)
        self.panel(action="edit", tag=Y, title="x", description="y")
        self.assertNotIn("duzenleme", self.vid(Y))

    def _paylas(self, meta):
        """publish_due'yu sahte indirme/yükleme ile çalıştırır; platformlara giden meta'yı döndürür."""
        import shortgen.publish as P
        giden = {}

        def fetch_release(tag, dest):
            (dest / "video.mp4").write_bytes(b"x")
            return dest / "video.mp4", json.loads(json.dumps(meta))

        def publish(video, m, only=None):
            giden.update(m)
            return {p: {"status": "ok", "url": f"https://{p}/1"} for p in only}
        P.fetch_release, P.publish = fetch_release, publish
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.publish_due()
        return giden

    META = {"title": "Eski başlık", "hashtags": ["tarih"], "topic": "t",
            "description": "Eski bilgi.\n\n#tarih #boston\n\n📷 John Doe (CC BY-SA 4.0)"}

    def test_duzenleme_paylasimda_kullanilir(self):
        self.panel(action="edit", tag=T, title="Yeni başlık", description="Yeni bilgi.\nİkinci satır.")
        self.panel(action="approve", tag=T, code="now")
        m = self._paylas(self.META)
        self.assertEqual(m["title"], "Yeni başlık")
        self.assertEqual(m["description"], "Yeni bilgi.\nİkinci satır.\n\n#tarih #boston\n\n📷 John Doe (CC BY-SA 4.0)")
        self.assertEqual(self.vid(T)["status"], "yayinlandi")

    def test_duzenlemede_kendi_etiketleri_varsa_yalniz_atif_eklenir(self):
        self.panel(action="edit", tag=T, title="B", description="Bilgi.\n\n#yeni #etiket")
        self.panel(action="approve", tag=T, code="now")
        m = self._paylas(self.META)
        self.assertEqual(m["description"], "Bilgi.\n\n#yeni #etiket\n\n📷 John Doe (CC BY-SA 4.0)")

    def test_duzenleme_yoksa_meta_aynen(self):
        self.panel(action="approve", tag=T, code="now")
        self.assertEqual(self._paylas(self.META), self.META)

    def test_oneriden_uret(self):
        c = self.panel(action="produce_suggestion", index=1, topic=ONERILER[1]["topic"])
        gh = [x for x in c if "gh" in x]
        it = ONERILER[1]
        self.assertEqual(gh, [{"gh": "uret.yml", "json": {"ref": "main", "inputs": {
            "topic": f"{it['topic']} (kanca: {it['hook']}; gündem: {it['trend']})"}}}])
        self.assertTrue(self.mesajlar(c)[0].startswith("🖥 Panelden: 🎬 Üretim başladı: 'Kasım'"))
        for p in ({"index": 1, "topic": "başka"}, {"index": 9}, {"index": True}, {"index": "1"}):
            self.req.cagrilar.clear()
            c = self.panel(action="produce_suggestion", **p)
            self.assertFalse([x for x in c if "gh" in x], p)
            self.assertIn("Öneri bulunamadı", self.mesajlar(c)[0])

    def test_konudan_uret_ve_oneri_iste(self):
        c = self.panel(action="produce_topic", topic="  kara   delikler ")
        self.assertEqual([x for x in c if "gh" in x][0]["json"]["inputs"], {"topic": "kara delikler"})
        self.req.cagrilar.clear()
        c = self.panel(action="produce_topic", topic="")
        self.assertEqual([x for x in c if "gh" in x][0]["json"]["inputs"], {"topic": ""})
        self.assertIn("sıradan veya gündemden", self.mesajlar(c)[0])
        self.req.cagrilar.clear()
        c = self.panel(action="refresh_suggestions")
        self.assertEqual([x["gh"] for x in c if "gh" in x], ["oneri.yml"])
        self.assertEqual(self.mesajlar(c), ["🖥 Panelden: 🔎 Gündem taranıyor, öneriler 2-3 dakikada gelir."])
        self.req.cagrilar.clear()
        self.req.dispatch_durum = 403
        c = self.panel(action="produce_topic", topic="x")
        self.assertEqual(self.mesajlar(c), ["🖥 Panelden: ⚠️ Üretim başlatılamadı."])

    def test_rapor_ve_istatistik_gecmisi(self):
        import shortgen.stats as st
        snap = json.loads((FIX / "state" / "stats.json").read_text(encoding="utf-8"))
        snap["time"] = "2026-11-05T00:45+03:00"
        snap["platforms"]["youtube"]["videos"]["short-20260901-1000"] = {"views": 5, "likes": 1}  # 30 günden eski
        snap["platforms"]["tiktok"] = {"error": "bağlı değil"}
        st.collect = lambda: json.loads(json.dumps(snap))
        st.dt = FAKE_DT
        hist = self.root / "state" / "stats_gecmis.jsonl"
        once = hist.read_text(encoding="utf-8").splitlines()
        c = self.panel(action="report")
        msj = self.mesajlar(c)
        self.assertEqual(msj[0], "🖥 Panelden: 📊 Rapor istendi, hazırlanıyor.")
        self.assertTrue(msj[1].startswith("📊 Bilgi Makası raporu"))
        self.assertEqual(json.loads((self.root / "state" / "stats.json").read_text())["time"], "2026-11-05T00:45+03:00")
        sonra = hist.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sonra[:-1], once)
        son = json.loads(sonra[-1])
        self.assertEqual(son["time"], "2026-11-05T00:45+03:00")
        self.assertEqual(set(son["hesap"]), {"youtube", "instagram"})
        self.assertEqual(son["hesap"]["youtube"], {"followers": 893, "views": 173861, "videos": 169})
        self.assertEqual(son["video"]["short-20261104-2033"], {"youtube": [3, 0], "instagram": [1105, 31]})
        self.assertNotIn("short-20260901-1000", son["video"])
        self.assertNotIn(" ", sonra[-1].replace("Bilgi", ""), "kısa (boşluksuz) JSON satırı")
        self.assertLess(len(sonra[-1]), 1000)

    def test_konu_sirasi(self):
        c = self.panel(action="queue_set", queue=["  bir   konu ", "iki", "iki", ""])
        d = json.loads((self.root / "state" / "konu_sirasi.json").read_text(encoding="utf-8"))
        self.assertEqual(d["konular"], ["bir konu", "iki"])
        self.assertEqual(self.mesajlar(c), ["🖥 Panelden: 📋 Konu sırası kaydedildi (2 konu).\nSıradaki: bir konu"])
        for kotu in ([f"k{i}" for i in range(31)], ["x" * 301], "metin", [3]):
            self.req.cagrilar.clear()
            c = self.panel(action="queue_set", queue=kotu)
            self.assertIn("⚠️ İşlem yapılamadı", self.mesajlar(c)[0])
        self.assertEqual(json.loads((self.root / "state" / "konu_sirasi.json").read_text())["konular"], ["bir konu", "iki"])
        self.panel(action="queue_set", queue=[])
        self.assertEqual(json.loads((self.root / "state" / "konu_sirasi.json").read_text())["konular"], [])

    def test_bilinmeyen_ve_bulunamayan(self):
        c = self.panel(action="sil")
        self.assertEqual(self.mesajlar(c), ["🖥 Panelden: ⚠️ Bilinmeyen panel işlemi: sil"])
        self.req.cagrilar.clear()
        c = self.panel(action="approve", tag="short-20990101-0000", code="now")
        self.assertEqual(self.mesajlar(c), ["🖥 Panelden: ⚠️ Video bulunamadı: short-20990101-0000"])
        self.req.cagrilar.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.process_update({"panel": "bozuk"}, CHAT)
        self.assertEqual(self.req.cagrilar, [])

    def test_panel_komutu_dinleme_modunda(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.process_update(msg("/panel"), CHAT)
        self.assertIn("Panel bağlantısını 7/24 kapı verir", self.req.cagrilar[0]["data"]["text"])


class KonuSirasiUretim(Ortak):
    def _main(self, argv, uret=None, oneri=None):
        import shortgen.pipeline as pl
        import shortgen.script as sc
        import shortgen.trends as tr
        demo = sc.load_script(self.root / "demo" / "demo_script.json")
        cagri = {}

        def generate_script(history, topic=None, templates=None, series_prev=None, allow_series=False):
            cagri["topic"] = topic
            if uret:
                uret()
            return demo
        pl.generate_script = generate_script
        pl.pick_template = lambda s, o=None: "kolaj"
        pl.build = lambda *a, **k: self.root / "output" / "video.mp4"
        tr.suggest = oneri or (lambda n=5: (_ for _ in ()).throw(AssertionError("gündeme gidilmemeli")))
        os.environ["SERIES_LABEL"] = "0"
        old = sys.argv
        sys.argv = ["pipeline", *argv, "--out", str(self.root / "output")]
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                pl.main()
        finally:
            sys.argv = old
        return cagri, out.getvalue()

    def kuyruk(self):
        return json.loads((self.root / "state" / "konu_sirasi.json").read_text(encoding="utf-8"))["konular"]

    def test_ilk_konu_alinir_ve_cikarilir(self):
        ilk = self.kuyruk()
        cagri, out = self._main([])
        self.assertEqual(cagri["topic"], ilk[0])
        self.assertEqual(self.kuyruk(), ilk[1:])
        self.assertIn("Konu sırasından alınan konu: " + ilk[0], out)
        self.assertIn("Konu sırasından çıkarıldı: " + ilk[0], out)

    def test_konu_verilirse_sira_degismez(self):
        ilk = self.kuyruk()
        cagri, _ = self._main(["--topic", "elle konu"])
        self.assertEqual(cagri["topic"], "elle konu")
        self.assertEqual(self.kuyruk(), ilk)

    def test_bekleyen_senaryo_varsa_sira_degismez(self):
        ilk = self.kuyruk()
        shutil.copy(self.root / "demo" / "demo_script.json", self.root / "state" / "bekleyen_senaryo.json")
        self._main([])
        self.assertEqual(self.kuyruk(), ilk)

    def test_senaryo_yazilamazsa_konu_sirada_kalir(self):
        ilk = self.kuyruk()

        def patla():
            raise RuntimeError("Claude bütçesi doldu")
        with self.assertRaises(RuntimeError):
            self._main([], uret=patla)
        self.assertEqual(self.kuyruk(), ilk)

    def test_sira_bossa_gundem(self):
        (self.root / "state" / "konu_sirasi.json").unlink()
        s0 = types.SimpleNamespace(topic="Gündem konusu", hook="kanca", trend="gündem")
        cagri, _ = self._main([], oneri=lambda n=5: [s0])
        self.assertEqual(cagri["topic"], "Gündem konusu (kanca: kanca; gündem: gündem)")

    def test_uret_yml_durumu_kaydeder(self):
        y = (REPO / ".github" / "workflows" / "uret.yml").read_text(encoding="utf-8")
        uret = y.index("python -m shortgen.pipeline")
        self.assertIn("python -m shortgen.state_sync", y[uret:y.index("Hata olursa")], "başarılı üretimde kayıt")
        self.assertIn("python -m shortgen.state_sync", y[y.index("Hata olursa"):], "hatada da kayıt")
        import shortgen.state_sync as ss
        self.assertIn("state", ss.PATHS)


class Birlestirme(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(REPO))
        from shortgen import konu_sirasi, state_sync
        self.k, self.ss = konu_sirasi, state_sync

    def tearDown(self):
        sys.path.remove(str(REPO))

    def m(self, b, r, l):
        d = lambda x: None if x is None else json.dumps({"konular": x})  # noqa: E731
        return json.loads(self.ss._merge("state/konu_sirasi.json", d(b), d(r), d(l)))["konular"]

    def test_uretim_ilk_konuyu_alirken_panelden_sira_degisti(self):
        # yerel = üretim (ilk konuyu çıkardı), uzak = panel (sırayı değiştirip konu ekledi)
        self.assertEqual(self.m(["a", "b", "c"], ["c", "b", "a", "d"], ["b", "c"]), ["c", "b", "d"])
        # tersi: yerel = panel düzenlemesi, uzak = üretim
        self.assertEqual(self.m(["a", "b", "c"], ["b", "c"], ["c", "b", "a", "d"]), ["c", "b", "d"])
        # ikisi de düzenledi
        self.assertEqual(self.m(["a", "b"], ["b", "x"], ["a", "y", "b"]), ["y", "b", "x"])
        # yalnız bir taraf değişti
        self.assertEqual(self.m(["a"], ["a"], ["a", "b"]), ["a", "b"])
        self.assertEqual(self.m(None, ["a"], None), ["a"])

    def test_temizle(self):
        self.assertEqual(self.k.clean([" a ", "a", "", "b\nc"]), ["a", "b c"])
        for kotu in ("x", [1], ["x" * 301], [str(i) for i in range(31)]):
            with self.assertRaises(ValueError):
                self.k.clean(kotu)


class KapiIleTutarlilik(unittest.TestCase):
    """cloudflare/panel.js içindeki sabitler Python'dakilerle aynı olmalı."""

    def setUp(self):
        sys.path.insert(0, str(REPO))
        for k in ("BEST_TIMES", "EXTRA_TIMES"):
            os.environ.pop(k, None)
        for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
            del sys.modules[ad]
        import shortgen.telegram_bot as tb
        self.tb = tb
        self.js = (REPO / "cloudflare" / "panel.js").read_text(encoding="utf-8")

    def tearDown(self):
        sys.path.remove(str(REPO))

    def js_nesne(self, ad):
        m = re.search(rf"{ad} = (\{{.*?\}});", self.js, re.S)
        metin = re.sub(r",(\s*\})", r"\1", m.group(1))  # sondaki virgül
        return json.loads(re.sub(r"([{,]\s*)(\w+):", r'\1"\2":', metin))

    def test_saatler(self):
        self.assertEqual(self.js_nesne("BEST_TIMES"), self.tb.BEST_TIMES)
        self.assertEqual(self.js_nesne("EXTRA_TIMES"), self.tb.EXTRA_TIMES)

    def test_islem_durumlari_ve_korunan_satirlar(self):
        self.assertEqual({k: tuple(v) for k, v in self.js_nesne("VIDEO_ISLEM").items()}, self.tb.PANEL_VIDEO_ACTIONS)
        bas = json.loads(re.search(r"KUYRUK_BASI = (\[.*?\]);", self.js).group(1))
        self.assertEqual(tuple(bas), self.tb._TAIL)
        kod = json.loads(re.search(r"KODLAR = (\[.*?\]);", self.js).group(1))
        self.assertEqual(tuple(kod), self.tb.SLOT_CODES)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--dugme"]:
        print(json.dumps(dugme_senaryolari(Path(sys.argv[2])), ensure_ascii=False, indent=1))
    else:
        unittest.main(verbosity=2)
