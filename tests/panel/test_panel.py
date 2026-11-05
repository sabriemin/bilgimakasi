#!/usr/bin/env python3
"""Panelin Python tarafı testleri (gerçek Telegram/GitHub çağrısı yok; durum geçici klasörde).

    python -B tests/panel/test_panel.py              # tüm testler
    python -B tests/panel/test_panel.py --dugme <kök>  # <kök>/shortgen'in geçici kopyasıyla düğme senaryolarını çalıştırıp JSON yazar

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

    def test_baslik_duzenlenmis_1_bolum_reddedilince_seri_iptal(self):
        self.video_degistir(T, title="Melas Seli (1. Bölüm)")
        (self.root / "state" / "seri.json").write_text(json.dumps({"bekleyen": {"title": "Melas Seli (1. Bölüm)"}}),
                                                       encoding="utf-8")
        self.panel(action="edit", tag=T, title="Melas Seli: Boston 1919", description="Yeni bilgi.")
        self.panel(action="edit", tag=T, title="Melas Seli: ikinci düzenleme", description="Yeni bilgi.")
        self.assertEqual(self.vid(T)["duzenleme"]["ilk_baslik"], "Melas Seli (1. Bölüm)")
        self.req.cagrilar.clear()
        c = self.panel(action="reject", tag=T)
        self.assertIn("Serinin 2. bölümü de iptal edildi", self.mesajlar(c)[0])
        self.assertNotIn("bekleyen", json.loads((self.root / "state" / "seri.json").read_text()))

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

    def test_duzenleme_paylasima_10_dk_kala_reddedilir(self):
        # paylaşım işi publish_at'te başlar, durumu yüklemeden sonra kaydeder: o pencerede metin değişmez
        yakin = (SIMDI + _dt.timedelta(minutes=9)).isoformat()
        self.video_degistir(T, status="zamanlandi", publish_at=yakin, schedule=None)
        c = self.panel(action="edit", tag=T, title="Yeni", description="Yeni bilgi.")
        self.assertNotIn("duzenleme", self.vid(T))
        self.assertIn("ℹ️ Düzenleme yapılmadı", self.mesajlar(c)[-1])
        # 10 dakikadan uzaksa düzenlenir; paylaşılmış platform varsa eski metnin orada kaldığı söylenir
        uzak = (SIMDI + _dt.timedelta(minutes=30)).isoformat()
        self.video_degistir(T, publish_at=uzak, platforms={"instagram": {"status": "ok", "url": "u"}})
        c = self.panel(action="edit", tag=T, title="Yeni", description="Yeni bilgi.")
        self.assertEqual(self.vid(T)["duzenleme"]["title"], "Yeni")
        self.assertIn("Zaten paylaşılan Instagram paylaşımında eski metin kalır", self.mesajlar(c)[-1])

    def test_metnin_altindaki_etiket_satiri_kendi_etiketleri_sayilir(self):
        m = self.tb._apply_edit(self.META, {"title": "T", "description": "Metin.\n#kendi1 #kendi2"})
        self.assertEqual(m["hashtags"], ["kendi1", "kendi2"])
        self.assertEqual(m["description"], "Metin.\n\n#kendi1 #kendi2\n\n📷 John Doe (CC BY-SA 4.0)")
        # metnin içinde geçen # etiket sayılmaz
        m = self.tb._apply_edit(self.META, {"title": "T", "description": "#1 numaralı kural\nMetin."})
        self.assertEqual(m["hashtags"], self.META["hashtags"])
        # yalnız rakamdan oluşan "#1 #2" satırı etiket satırı sayılmaz
        m = self.tb._apply_edit(self.META, {"title": "T", "description": "Sıralama:\n#1 #2"})
        self.assertEqual(m["hashtags"], self.META["hashtags"])
        self.assertTrue(m["description"].startswith("Sıralama:\n#1 #2\n\n#tarih #boston"), m["description"])

    def test_uzun_duzenlemede_gorsel_atfi_kesilmez(self):
        import shortgen.publish as P
        cred = "📷 Jane Doe (CC BY-SA 3.0), Ahmet Yılmaz (CC BY 2.0), ESA/Hubble (CC BY 4.0)"
        head = "B" * 100 + "\n\n" + "Uzun bilgi. " * 170 + "\n\n" + cred
        for limit, ölç in ((2200, None), (2152, len)):
            cap = P._fit_caption(head, "#a #b", limit, ölç)
            self.assertTrue(cap.endswith(cred + "\n\n#a #b"), cap[-120:])
            self.assertLessEqual((ölç or P._u16)(cap), limit)
        # sığan metin aynen kalır (üretimdeki kısa açıklamalar değişmez)
        self.assertEqual(P._fit_caption("Kısa.\n\n" + cred, "#a", 2200), "Kısa.\n\n" + cred + "\n\n#a")
        # 📷 ile başlamayan satır içeren paragraf korunmaz (kullanıcı metni atıf gibi davranamaz)
        karisik = "Bilgi " * 600 + "\n\n📷 Sahte\nUzun metin " + "x" * 3000
        cap = P._fit_caption(karisik, "#a", 2200)
        self.assertLessEqual(P._u16(cap), 2200)
        self.assertTrue(cap.endswith("#a"))
        # atıf tek başına sınırı aşsa bile sonuç sınırı aşmaz
        cap = P._fit_caption("Kısa.\n\n📷 " + "Ç" * 3000, "#a", 2152, len)
        self.assertLessEqual(len(cap), 2152)

    def dugme(self, data):
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.process_update(cq(data), CHAT)
        return self.req.cagrilar[:]

    def test_eski_onay_dugmesi_karar_verilmis_videoyu_degistirmez(self):
        for durum in ("reddedildi", "zamanlandi", "yayinlandi"):
            durum_sifirla(self.root)
            self.req.cagrilar.clear()
            self.video_degistir(T, status=durum)
            once = self.vid(T)
            for data in (f"ok:{T}", f"at:{T}:now", f"no:{T}"):
                c = self.dugme(data)
                self.assertEqual(self.vid(T), once, (durum, data))
                cevap = self.mesajlar(c)[-1]  # webhook modunda baloncuk notu mesaj olarak gider
                self.assertIn("artık onay beklemiyor", cevap)
            kb = self.tg(c, "editMessageReplyMarkup")[-1]["data"]["reply_markup"]["inline_keyboard"]
            self.assertEqual(kb, [[{"text": t, "callback_data": d} for t, d in r] for r in self.tb._kb_rows(T, durum)])

    def test_kayit_sonrasi_dugmeler_birlesmis_duruma_gore_tazelenir(self):
        def tazele(u):
            self.req.cagrilar.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                self.tb.refresh_kb(u, CHAT)
            return [c["data"]["reply_markup"]["inline_keyboard"] for c in self.tg(self.req.cagrilar, "editMessageReplyMarkup")]
        # başka bir iş videoyu reddetti: panel düzenlemesinin koyduğu Onayla/Reddet kaldırılır
        self.video_degistir(T, status="reddedildi")
        self.assertEqual(tazele({"panel": {"action": "edit", "tag": T}}), [[]])
        self.assertEqual(tazele(cq(f"no:{T}")), [[]])
        # zamanlanmış: iptal düğmesi
        self.video_degistir(T, status="zamanlandi")
        self.assertEqual(tazele(cq(f"at:{T}:now"))[0][0][0]["callback_data"], f"cancel:{T}")
        # onay bekleyen: saat seçimi düğmelerine dokunulmaz; panel düzenlemesinden sonra Onayla/Reddet konur
        self.video_degistir(T, status="onay_bekliyor")
        self.assertEqual(tazele(cq(f"ok:{T}")), [])
        self.assertEqual(tazele({"panel": {"action": "edit", "tag": T}})[0][0][0]["callback_data"], f"ok:{T}")
        # video dışı düğmeler ve bilinmeyen video
        self.assertEqual(tazele(cq("cm:ok:abc")), [])
        self.assertEqual(tazele(cq("tp:2")), [])
        self.assertEqual(tazele({"panel": {"action": "report"}}), [])
        self.assertEqual(tazele(cq("no:yok-boyle-video")), [])

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
        # Instagram/TikTok etiketleri ve YouTube etiket alanı da kullanıcının etiketlerini kullanır
        self.assertEqual(m["hashtags"], ["yeni", "etiket"])

    def test_duzenlemede_etiket_yoksa_orijinal_etiketler_kalir(self):
        m = self.tb._apply_edit(self.META, {"title": "T", "description": "Yeni bilgi."})
        self.assertEqual(m["hashtags"], self.META["hashtags"])

    def test_duzenleme_yoksa_meta_aynen(self):
        self.panel(action="approve", tag=T, code="now")
        self.assertEqual(self._paylas(self.META), self.META)

    def test_gorsel_atfi_her_zaman_korunur(self):
        """Kullanıcı metninde Kaynaklar/Görseller/🎙/📷 paragrafı olsa da (eski kayıt) yayımlanan açıklamada atıf kalır."""
        import shortgen.publish as P
        for desc in ("Yeni bilgi.\n\nKaynaklar: X", "Yeni bilgi.\n\nGörseller: Wikimedia Commons",
                     "Yeni bilgi.\n\n🎙 Seslendirme: yapay zekâ", "Yeni bilgi.\n\n📷 Ben", "Yeni bilgi.\n\n#yeni"):
            m = self.tb._apply_edit(self.META, {"title": "T", "description": desc})
            yt = P._clean_desc(m["description"])
            self.assertIn("📷 John Doe (CC BY-SA 4.0)", yt, desc)
            self.assertTrue(yt.startswith("Yeni bilgi."), desc)
        # kendi # satırı yalnız etiket satırının yerine geçer
        m = self.tb._apply_edit(self.META, {"title": "T", "description": "Yeni bilgi.\n\n#yeni"})
        self.assertEqual(m["description"], "Yeni bilgi.\n\n#yeni\n\n📷 John Doe (CC BY-SA 4.0)")
        # etiket ve atıf aynı paragraftaysa yalnız etiket satırı düşer
        meta = {**self.META, "description": "Eski.\n\n#tarih\n📷 John Doe (CC BY-SA 4.0)"}
        self.assertEqual(self.tb._apply_edit(meta, {"description": "Yeni.\n\n#yeni"})["description"],
                         "Yeni.\n\n#yeni\n\n📷 John Doe (CC BY-SA 4.0)")
        # tam açıklama aynen yapıştırılırsa ek paragraflar iki kez eklenmez
        self.assertEqual(self.tb._apply_edit(self.META, {"description": self.META["description"]})["description"],
                         self.META["description"])

    def test_duzenleme_kaynak_ve_atif_satirini_reddeder(self):
        for desc in ("Bilgi.\n\nKaynaklar: X", "Bilgi.\n\n📷 Ben", "Bilgi.\n\n#etiket\n🎙 ses", "😀" * 1001):
            durum_sifirla(self.root)
            self.req.cagrilar.clear()
            c = self.panel(action="edit", tag=T, title="Başlık", description=desc)
            self.assertNotIn("duzenleme", self.vid(T), desc[:20])
            self.assertIn("⚠️ İşlem yapılamadı", self.mesajlar(c)[-1])
        self.panel(action="edit", tag=T, title="Başlık", description="Bilgi.\n\n#etiket #iki\n#uc")
        self.assertEqual(self.vid(T)["duzenleme"]["description"], "Bilgi.\n\n#etiket #iki\n#uc")
        durum_sifirla(self.root)
        self.panel(action="edit", tag=T, title="Başlık", description="ğ" * 2000)  # 4000 bayt: sınırda
        self.assertIn("duzenleme", self.vid(T))

    def test_youtube_aciklamasi_5000_bayti_gecmez(self):
        import shortgen.publish as P
        giden = {}

        class R:
            ok, status_code, text = True, 200, ""
            headers = {"Location": "https://upload/x"}

            def json(self):
                return {"id": "v1", "status": {"privacyStatus": "public"}}

        def post(url, **kw):
            giden.update(json.loads(kw["data"]))
            return R()
        eski = (P._yt_token, P.requests)
        P._yt_token = lambda: "ya29.test"
        P.requests = types.SimpleNamespace(post=post, put=lambda *a, **k: R())
        try:
            video = self.root / "v.mp4"
            video.write_bytes(b"x")
            m = self.tb._apply_edit({"title": "t", "hashtags": [], "description": "Bilgi.\n\n#a\n\n📷 John Doe (CC BY-SA 4.0)"},
                                    {"title": "t", "description": "😀" * 2000})
            P.youtube(video, m)
        finally:
            P._yt_token, P.requests = eski
        d = giden["snippet"]["description"]
        self.assertLessEqual(len(d.encode("utf-8")), 4900)
        self.assertTrue(d.startswith("😀"))
        d.encode("utf-8").decode("utf-8")  # yarım karakter kalmadı

    def test_video_mesaji_basligi_html_varligini_bolmez(self):
        v = dict(self.vid(T), title="A&B " * 25, topic=("xyz&" * 220))
        self.req.cagrilar.clear()
        self.tb._edit_caption(v, CHAT)
        cap = self.tg(self.req.cagrilar, "editMessageCaption")[0]["data"]["caption"]
        self.assertLessEqual(len(cap), 1000)
        self.assertFalse(re.search(r"&[a-z]*$", cap.split("\nŞablon")[0]), "kesik HTML varlığı")
        self.assertTrue(cap.endswith("Şablon: " + (v.get("template") or "-")))

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

    def test_konu_sirasi_taban_ile_birlestirilir(self):
        """Sayfa sırayı yükledikten sonra üretim ilk konuyu aldıysa, eski sayfadan kaydetmek onu geri getirmez."""
        f = self.root / "state" / "konu_sirasi.json"
        f.write_text(json.dumps({"konular": ["b", "c"], "rid": "uretim-oncesi"}), encoding="utf-8")  # üretim "a"yı aldı
        c = self.panel(action="queue_set", queue=["c", "b", "a", "d"], queue_base=["a", "b", "c"], rid="r-42")
        d = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(d["konular"], ["c", "b", "d"])
        self.assertEqual(d["rid"], "r-42")
        self.assertEqual(self.mesajlar(c), ["🖥 Panelden: 📋 Konu sırası kaydedildi (3 konu).\nSıradaki: c"])
        # taban yoksa (eski sayfa) liste aynen yazılır
        self.panel(action="queue_set", queue=["x"], rid="r-43")
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")), {**json.loads(f.read_text(encoding="utf-8")),
                                                                     "konular": ["x"], "rid": "r-43"})
        # üretim konu çıkarınca son panel kaydının numarası korunur
        import shortgen.konu_sirasi as ks
        ks.FILE = f
        self.assertTrue(ks.remove("x", f))
        self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["rid"], "r-43")

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


class Gizleme(Ortak):
    """Hata metinlerindeki anahtarlar (Instagram access_token, bot anahtarı) videos.json'a, Telegram'a, günlüğe gitmez."""
    IG = "IGAAJx8TEStoken0123456789abcdefABCDEF_uzun"
    AG_HATASI = ("HTTPSConnectionPool(host='graph.instagram.com', port=443): Max retries exceeded with url: "
                 "/v26.0/18012345678901234?fields=status_code%2Cstatus&access_token={tok} (Caused by "
                 "NameResolutionError(\"<urllib3.connection.HTTPSConnection object at 0x7f>: Failed to resolve\"))")

    def test_redact_kaliplari(self):
        from shortgen.publish import _redact, _remember_secret
        self.assertEqual(_redact("u?access_token=abc&x=1 key=K code=C client_secret=S"),
                         "u?access_token=***&x=1 key=*** code=*** client_secret=***")
        self.assertEqual(_redact("/bot123456789:AAHk-abcdefghijklmnopqrstuvwxyz012/getMe"), "/bot***/getMe")
        self.assertEqual(_redact("EAAGm0PX4ZCpsBAKexampleexample ya29.a0AfB_byC1234567890abc ghs_abcdefghijklmnop1234"),
                         "*** *** ***")
        self.assertEqual(_redact("{'access_token': 'act.123abc', 'refresh_token': 'rft.456def'}"),
                         "{'access_token': '***', 'refresh_token': '***'}")
        self.assertEqual(_redact("Authorization: OAuth IGQWRabcdefgh"), "Authorization: OAuth ***")
        self.assertEqual(_redact("Media upload has failed with error code 2207026"), "Media upload has failed with error code 2207026")
        os.environ["IG_ACCESS_TOKEN"] = "tamamen-farkli-bicim-123"
        try:
            self.assertEqual(_redact("x tamamen-farkli-bicim-123 y"), "x *** y")
        finally:
            del os.environ["IG_ACCESS_TOKEN"]
        _remember_secret("yenilenmis-anahtar-999")
        self.assertEqual(_redact("[yenilenmis-anahtar-999]"), "[***]")

    def test_paylasim_hatasi_kayda_ve_gunluge_anahtarsiz_gecer(self):
        import shortgen.publish as P
        hata = self.AG_HATASI.format(tok=self.IG)

        def patla(video, meta):
            raise RuntimeError(hata)
        eski = dict(P.PLATFORMS)
        P.PLATFORMS.update(youtube=patla, instagram=patla, tiktok=patla)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                res = P.publish(Path("v.mp4"), {"title": "t", "description": ""}, ["instagram"])
        finally:
            P.PLATFORMS.clear()
            P.PLATFORMS.update(eski)
        self.assertNotIn(self.IG, json.dumps(res))
        self.assertNotIn(self.IG[:20], out.getvalue())
        self.assertIn("access_token=*** (Caused by NameResolutionError", res["instagram"]["error"])
        self.assertNotIn("IGAA", res["instagram"]["error"][:220])

    def test_indirme_hatasi_ve_telegram_mesaji_anahtarsiz(self):
        import shortgen.publish as P
        hata = self.AG_HATASI.format(tok=self.IG)

        def fetch_release(tag, dest):
            raise RuntimeError(hata)
        eski = P.fetch_release
        P.fetch_release = fetch_release
        try:
            self.panel(action="approve", tag=T, code="now")
            self.req.cagrilar.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                self.tb.publish_due()
        finally:
            P.fetch_release = eski
        kayit = json.dumps(self.vid(T))
        self.assertNotIn(self.IG, kayit)
        self.assertIn("access_token=***", kayit)
        for m in self.mesajlar(self.req.cagrilar):
            self.assertNotIn("IGAA", m)

    def test_istatistik_hatasi_anahtarsiz(self):
        import shortgen.stats as st
        hata = self.AG_HATASI.format(tok=self.IG)

        def patla(videos):
            raise RuntimeError(hata)
        eski = dict(st.FETCH)
        st.FETCH.update(youtube=patla, instagram=patla, tiktok=patla)
        try:
            snap = st.collect()
        finally:
            st.FETCH.clear()
            st.FETCH.update(eski)
        self.assertNotIn("IGAA", json.dumps(snap))
        self.assertTrue(snap["platforms"]["instagram"]["error"].startswith("okunamadı ("))

    def _ag_hatasi(self):
        import requests as gercek
        return gercek.exceptions.ProxyError(
            "HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded with url: "
            "/bot123:TEST/editMessageReplyMarkup (Caused by ProxyError('Unable to connect to proxy'))")

    def test_panel_islemi_ag_hatasi_sohbete_anahtar_yazmaz(self):
        hata, ilk = self._ag_hatasi(), {"n": 0}
        asil = self.req.post

        def post(url, **kw):
            if "editMessageReplyMarkup" in url and not ilk["n"]:
                ilk["n"] += 1
                raise hata
            return asil(url, **kw)
        self.req.post = post
        os.environ.update(GITHUB_RUN_ID="777", GITHUB_SERVER_URL="https://github.com")
        try:
            c = self.panel(action="approve", tag=T, code="now")
        finally:
            self.req.post = asil
            del os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_SERVER_URL"]
        son = self.mesajlar(c)[-1]
        self.assertTrue(son.startswith("🖥 Panelden: ⚠️ İşlem yapılamadı: Telegram veya GitHub'a bağlanılamadı"), son)
        self.assertIn("https://github.com/sabriemin/bilgimakasi/actions/runs/777", son)
        for m in self.mesajlar(c):
            self.assertNotIn("123:TEST", m)
        self.assertNotIn("123:TEST", self.cikti)
        self.assertIn("bot***", self.cikti)  # ayrıntı günlükte, maskelenmiş

    def test_dugme_ve_rapor_hatasi_sohbete_anahtar_yazmaz(self):
        hata = self._ag_hatasi()
        asil = self.req.post

        def post(url, **kw):
            if "editMessageReplyMarkup" in url:
                raise hata
            return asil(url, **kw)
        self.req.post = post
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.tb.process_update(cq(f"ok:{T}"), CHAT)
        finally:
            self.req.post = asil
        m = self.mesajlar(self.req.cagrilar)
        self.assertTrue(m and m[-1].startswith("⚠️ Düğme işlenemedi: Telegram veya GitHub'a bağlanılamadı"), m)
        self.assertNotIn("123:TEST", json.dumps(self.req.cagrilar) + out.getvalue())
        import shortgen.stats as st
        eski = st.report

        def rapor():
            raise RuntimeError(f"okunamadı: url /v26.0/me?access_token={self.IG}")
        st.report = rapor
        self.req.cagrilar.clear()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.tb.process_update(msg("/rapor"), CHAT)
        finally:
            st.report = eski
        self.assertEqual(self.mesajlar(self.req.cagrilar), ["Rapor hazırlanamadı: okunamadı: url /v26.0/me?access_token=***"])

    def test_uzun_panel_mesaji_telegram_sinirina_sigar(self):
        t = self.tb._cut16("🖥 Panelden: " + "😀" * 3000, 4000)
        self.assertLessEqual(len(t.encode("utf-16-le")) // 2, 4000)
        self.assertTrue(t.endswith("…"))
        self.assertEqual(self.tb._cut16("kısa"), "kısa")


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

    def test_paylasim_kaydi_panel_duzenlemesini_silmez(self):
        b = {"tag": "t", "title": "Eski", "status": "zamanlandi", "platforms": {}}
        r = {**b, "title": "Yeni", "duzenleme": {"title": "Yeni", "description": "d"}}  # panel önce kaydetti
        l = {**b, "status": "zamanlandi", "platforms": {"youtube": {"status": "ok"}}}  # paylaşım işi sonra
        d = lambda v: json.dumps([v])  # noqa: E731
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(r), d(l)))[0]
        self.assertEqual((out["title"], out["duzenleme"]["title"]), ("Yeni", "Yeni"))
        self.assertEqual(out["platforms"]["youtube"]["status"], "ok")
        # panel kullanılmadıysa: uzaktaki kullanıcı kararı (durum değişti, platforms aynı) geçerli olur,
        # bu çalışmanın paylaşımı (ok) korunur
        out = json.loads(self.ss._merge("state/videos.json", d(b), d({**b, "status": "x"}), d(l)))[0]
        self.assertEqual(out, {**b, "status": "x", "platforms": {"youtube": {"status": "ok"}}})
        # uzakta yalnız durum dışı bir alan değişmediyse (ör. yalnız panel düzenlemesi) yerel kayıt kazanır
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(b), d(l)))[0]
        self.assertEqual(out, l)

    def test_yalniz_metin_duzenleyen_calisma_uzaktaki_karari_ezmez(self):
        b = {"tag": "t", "title": "Eski", "status": "zamanlandi", "publish_at": "P", "platforms": {}}
        d = lambda v: json.dumps([v])  # noqa: E731
        l = {**b, "title": "Yeni", "duzenleme": {"title": "Yeni", "description": "d"}}  # panel düzenlemesi
        for r in ({**b, "status": "onay_bekliyor", "publish_at": None},  # iptal
                  {**b, "status": "reddedildi", "publish_at": None},  # ret
                  {**b, "status": "kismen", "platforms": {"youtube": {"status": "ok"}, "instagram": {"status": "hata"}}}):
            out = json.loads(self.ss._merge("state/videos.json", d(b), d(r), d(l)))[0]
            self.assertEqual(out, {**r, "title": "Yeni", "duzenleme": l["duzenleme"]})

    def test_uzaktaki_yalniz_baslik_degisikligi_korunur(self):
        b = {"tag": "t", "title": "Eski", "status": "zamanlandi", "platforms": {}}
        d = lambda v: json.dumps([v])  # noqa: E731
        r = {**b, "title": "Yeni"}  # başka bir iş yalnız başlığı değiştirdi
        l = {**b, "platforms": {"youtube": {"status": "ok"}}}  # bu çalışma paylaştı
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(r), d(l)))[0]
        self.assertEqual((out["title"], out["platforms"]), ("Yeni", {"youtube": {"status": "ok"}}))
        # bu çalışma da başlığı değiştirdiyse kendi başlığı kalır
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(r), d({**l, "title": "Benim"})))[0]
        self.assertEqual(out["title"], "Benim")

    def test_birlestirme_panel_kayit_numarasini_korur(self):
        d = lambda x, rid=None: json.dumps({"konular": x, **({"rid": rid} if rid else {})})  # noqa: E731
        # panel kaydetti (uzak, rid=p1), bu çalışma (üretim) ilk konuyu çıkardı (yerel, eski rid)
        out = json.loads(self.ss._merge("state/konu_sirasi.json", d(["a", "b"], "p0"), d(["b", "a", "c"], "p1"), d(["b"], "p0")))
        self.assertEqual((out["konular"], out["rid"]), (["b", "c"], "p1"))
        out = json.loads(self.ss._merge("state/konu_sirasi.json", d(["a", "b"], "p0"), d(["b"], "p0"), d(["b", "a", "c"], "p1")))
        self.assertEqual((out["konular"], out["rid"]), (["b", "c"], "p1"))

    def test_bos_konu_sirayi_tikamaz(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "k.json"
            f.write_text(json.dumps({"konular": ["", "  ", " Gerçek   konu "]}), encoding="utf-8")
            self.assertEqual(self.k.peek(f), "Gerçek konu")
            self.assertTrue(self.k.remove("Gerçek konu", f))
            self.assertIsNone(self.k.peek(f))

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
        ui = (REPO / "cloudflare" / "panel_ui.js").read_text(encoding="utf-8")
        bas = json.loads(re.search(r"KUYRUK_BASI = (\[.*?\]);", ui).group(1))
        self.assertEqual(tuple(bas), self.tb._TAIL)
        sinir = re.search(r"SINIR = \{ baslik: (\d+), aciklama: (\d+), aciklamaBayt: (\d+) \};", ui).groups()
        self.assertEqual(tuple(map(int, sinir)), (100, 2000, 4000))  # _check_edit ile aynı sınırlar
        kod = json.loads(re.search(r"KODLAR = (\[.*?\]);", self.js).group(1))
        self.assertEqual(tuple(kod), self.tb.SLOT_CODES)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--dugme"]:
        # geçici kopyada çalışır: verilen kökün state/ klasörü ve history.jsonl dosyası silinmez
        kok = kok_hazirla(Path(sys.argv[2]).resolve())
        try:
            print(json.dumps(dugme_senaryolari(kok), ensure_ascii=False, indent=1))
        finally:
            sys.path.remove(str(kok))
            shutil.rmtree(kok, ignore_errors=True)
    else:
        unittest.main(verbosity=2)
