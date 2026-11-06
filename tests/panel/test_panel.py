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
    def __init__(self, status=200, data=None, content=None):
        self.status_code, self._d = status, data if data is not None else {"ok": True, "result": {"message_id": 900}}
        self.ok = status < 400
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(self._d)
        self.content = content if content is not None else self.text.encode()

    def json(self):
        return self._d


GH_SURUM = "https://api.github.com/repos/sabriemin/bilgimakasi/releases/"


class SahteRequests:
    """telegram_bot.requests yerine: Telegram ve GitHub dispatch çağrılarını, release'ten metadata.json okumayı kaydeder.
    isler / isler_durum: onay.yml iş listesinin (GET …/onay.yml/runs) cevabı."""

    def __init__(self):
        self.cagrilar: list[dict] = []
        self.sifirla()

    def sifirla(self):
        self.dispatch_durum = 204
        self.hatalar: dict[str, str] = {}  # Telegram yöntemi -> hata açıklaması (400 döner)
        self.mesaj_no: dict[str, int] = {}  # Telegram yöntemi -> dönen message_id (varsayılan 900)
        self.surumler: dict[str, dict] = {}  # etiket -> GitHub Release'teki metadata.json (yoksa 404)
        self.isler: list[dict] = []
        self.isler_durum = 200

    def post(self, url, timeout=None, data=None, json=None, headers=None, files=None, **kw):  # noqa: A002
        if "api.telegram.org" in url:
            d = dict(data or {})
            for k in ("reply_markup", "commands"):
                if isinstance(d.get(k), str):
                    d[k] = __import__("json").loads(d[k])
            yontem = url.rsplit("/", 1)[1]
            self.cagrilar.append({"tg": yontem, "data": d})
            if yontem in self.hatalar:
                return Yanit(400, {"ok": False, "description": self.hatalar[yontem]})
            return Yanit(data={"ok": True, "result": {"message_id": self.mesaj_no.get(yontem, 900)}})
        m = re.search(r"/actions/workflows/([\w.]+)/dispatches$", url)
        if m:
            self.cagrilar.append({"gh": m.group(1), "json": json})
            return Yanit(self.dispatch_durum, {})
        raise AssertionError("beklenmeyen istek: " + url)

    def get(self, url, params=None, headers=None, timeout=None, **kw):
        if url.endswith("/actions/workflows/onay.yml/runs"):
            self.cagrilar.append({"gh_get": "onay.yml/runs", "params": params,
                                  "auth": (headers or {}).get("Authorization")})
            return Yanit(self.isler_durum, {"total_count": len(self.isler), "workflow_runs": self.isler})
        self.cagrilar.append({"get": url, "accept": (headers or {}).get("Accept"),
                              "yetki": (headers or {}).get("Authorization")})
        etiketler = list(self.surumler)
        m = re.fullmatch(re.escape(GH_SURUM) + r"tags/([\w.-]+)", url)
        if m:
            if m.group(1) not in self.surumler:
                return Yanit(404, {"message": "Not Found"})
            no = etiketler.index(m.group(1)) + 1
            return Yanit(200, {"tag_name": m.group(1), "assets": [
                {"name": "video.mp4", "url": f"{GH_SURUM}assets/{no}0"},
                {"name": "metadata.json", "url": f"{GH_SURUM}assets/{no}1"}]})
        m = re.fullmatch(re.escape(GH_SURUM) + r"assets/(\d+)1", url)
        if m and (headers or {}).get("Accept") == "application/octet-stream":
            meta = self.surumler[etiketler[int(m.group(1)) - 1]]
            return Yanit(200, {}, content=__import__("json").dumps(meta, ensure_ascii=False).encode("utf-8"))
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


def uretim_sablonu(kok: Path) -> None:
    """Geçici kökün templates/ klasöründe uretim şablonu yoksa sözleşmedeki alanlarla yazar (renderer nasil, yapi
    uretim). Depoda templates/uretim.json varsa (kopyalanmıştır) ona dokunmaz."""
    yol = kok / "templates" / "uretim.json"
    if not yol.exists():
        t = json.loads((REPO / "templates" / "nasil.json").read_text(encoding="utf-8"))
        t.update(name="Nasıl üretiliyor?", description="Aşama kartları (deneme)", renderer="nasil", yapi="uretim")
        yol.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")


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
        # kur() shortgen'i geçici kökten yükler; sınıf bitince önceki modüller geri konur (aynı süreçte sonra koşan
        # test dosyalarının pipeline'ı, silinen geçici kökten kart/nasil içe aktarmaya çalışmasın)
        cls._eski_moduller = {m: mod for m, mod in sys.modules.items() if m == "shortgen" or m.startswith("shortgen.")}
        cls.root = kok_hazirla(REPO)
        cls.tb, cls.req = kur(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        sys.path.remove(str(cls.root))
        for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
            del sys.modules[ad]
        sys.modules.update(cls._eski_moduller)

    def setUp(self):
        durum_sifirla(self.root)
        self.req.cagrilar.clear()
        self.req.sifirla()
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
            # bilinçli fark (haftalık takvim): 🎯 düğmesi serinin takvim saatini seçer
            g = json.loads(json.dumps(g, ensure_ascii=False).replace("🎯 Her platform en iyi saatinde",
                                                                     "🎯 Serinin takvim saatinde"))
            if g["ad"] == "/start":  # bilinçli farklar: yardım metninde /panel satırı, yedi seriden 21 öneri ve
                # yazılan konudan seri seçimi
                self.assertEqual(y["cagrilar"][0]["data"]["text"], g["cagrilar"][0]["data"]["text"].replace(
                    "/yardim: bu liste", "/panel: yönetim paneline giriş bağlantısı\n/yardim: bu liste").replace(
                    "/oneri: gündemden 5 konu önerisi", "/oneri: 7 seriden 21 konu önerisi").replace(
                    "(konu isteğe bağlı)", "(konu isteğe bağlı; 'Kuyumcu olsaydın', 'Çay nasıl demlenir?' gibi "
                    "konularda seri kendiliğinden seçilir, başına 'genel:' yazarsan serbest kalır)"))
                continue
            if g["ad"] in self.SAAT_METNI:
                # bilinçli fark (panel takvimi): yalnız en iyi saatler (ek saat yok), ⭐ prime time işareti, uzun
                # "Asıl en iyi saatler…" açıklaması yerine panel notu. Seçilen saatler, düğmeler ve kayıt aynı.
                beklenen = json.loads(json.dumps(g))
                beklenen["cagrilar"][-1]["data"]["text"] = self.SAAT_METNI[g["ad"]]
                if g["ad"] == "at best":  # 🎯: Genel serisinin takvimdeki sıradaki boş saati, üç platform aynı anda
                    t = "2026-11-09T15:00:00+00:00"
                    for rec in beklenen["degisen"].values():
                        rec.update(publish_at=t, schedule={"youtube": t, "instagram": t, "tiktok": t})
                self.assertEqual(y, beklenen, g["ad"])
                continue
            self.assertEqual(y, g, g["ad"])

    SAAT_METNI = {
        "at best": "✅ Onaylandı. Genel serisinin takvim saatinde, üç platformda birden paylaşılacak: "
                   "9 Kasım Pazartesi 18:00\n"
                   "Saatleri değiştirmek için panelde Takvim: /panel\nBir Mahalleyi Melas Dalgası Yuttu: 1919 Boston Faciası",
        "/saatler": "Platformların en iyi paylaşım saatleri (Türkiye, ⭐ prime time):\n• YouTube: 18:00, 21:00\n"
                    "• Instagram: 12:30, 20:00\n• TikTok: 19:30, 22:00\n\nOnaylarken '🎯 Serinin takvim saatinde' seçersen "
                    "video serisinin haftalık takvimdeki sıradaki boş saatinde üç platformda birden paylaşılır.\nSaatleri değiştirmek için panelde Takvim: /panel",
    }

    def test_komut_menusunde_panel(self):
        self.assertIn({"command": "panel", "description": "Yönetim paneline giriş bağlantısı"}, self.tb.COMMANDS)


class PanelIslemleri(Ortak):
    def test_onay_en_iyi_saat(self):
        c = self.panel(action="approve", tag=T, code="best", rid="r1")
        v = self.vid(T)
        self.assertEqual(v["status"], "zamanlandi")
        self.assertEqual(set(v["schedule"]), {"youtube", "instagram", "tiktok"})
        self.assertEqual(v["publish_at"], min(v["schedule"].values()))
        self.assertEqual(len(set(v["schedule"].values())), 1, "takvim saati: üç platform aynı anda")
        kb = self.tg(c, "editMessageReplyMarkup")
        self.assertEqual(kb[0]["data"]["message_id"], 2)
        self.assertEqual(kb[0]["data"]["reply_markup"], {"inline_keyboard": [[{"text": "🚫 Paylaşımı iptal et",
                                                                               "callback_data": f"cancel:{T}"}]]})
        m = self.tg(c, "sendMessage")[-1]["data"]
        self.assertTrue(m["text"].startswith("🖥 Panelden: ✅ Onaylandı. Genel serisinin takvim saatinde"))
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
        # kısa video başlığı: yalnız başlık ve şablon (Konu satırı yok)
        self.assertEqual(cap["caption"], "🎬 <b>Yeni &lt;b&gt;Başlık&lt;/b&gt; &amp; ötesi</b>\nŞablon: " + v["template"])
        self.assertEqual(cap["parse_mode"], "HTML")
        self.assertEqual(cap["reply_markup"]["inline_keyboard"][0][0]["callback_data"], f"ok:{T}")
        # onay mesajı metni tekrar yazmaz. Fikstürde release (metadata.json) yok: eksik açıklama mesajı yazılmaz, uyarılır
        onay, = self.tg(c, "sendMessage")
        self.assertEqual(onay["data"]["text"],
                         "🖥 Panelden: ✏️ Başlık ve açıklama güncellendi; paylaşımda yeni metin kullanılacak.\n"
                         "⚠️ Açıklama mesajı şimdi güncellenemedi; TikTok taslağı gönderilirken yenilenecek.")
        self.assertEqual(onay["data"]["reply_to_message_id"], 2)
        self.assertNotIn("aciklama_message_id", v)

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

    def _paylas(self, meta, sonuc=None):
        """publish_due'yu sahte indirme/yükleme ile çalıştırır; platformlara giden meta'yı döndürür.
        sonuc: platform -> yükleme sonucu (verilmeyen platform bağlantısıyla paylaşılmış sayılır)."""
        import shortgen.publish as P
        giden = {}

        def fetch_release(tag, dest):
            (dest / "video.mp4").write_bytes(b"x")
            return dest / "video.mp4", json.loads(json.dumps(meta))

        def publish(video, m, only=None):
            giden.update(m)
            return {p: dict((sonuc or {}).get(p) or {"status": "ok", "url": f"https://{p}/1"}) for p in only}
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

    def test_efsane_serisi_etiketi(self):
        import shortgen.publish as P
        meta = {**self.META, "structure": "efsane", "hashtags": ["a", "b", "c", "d", "bilgimakasi"],
                "description": "Bilgi.\n\n#a #b #c #d #bilgimakasi\n\n📷 John Doe (CC BY-SA 4.0)"}
        self.panel(action="approve", tag=T, code="now")
        m = self._paylas(meta)
        # en çok 5 etiket: seri etiketi son konu etiketinin yerine, kanal etiketinin önüne
        self.assertEqual(m["hashtags"], ["a", "b", "c", "EfsaneMiGerçekMi", "bilgimakasi"])
        self.assertEqual(m["description"], "Bilgi.\n\n#a #b #c #EfsaneMiGerçekMi #bilgimakasi\n\n📷 John Doe (CC BY-SA 4.0)")
        self.assertEqual(P.apply_series_tag(m), m)  # iki kez eklenmez
        diger = {**meta, "structure": "neden"}
        self.assertEqual(P.apply_series_tag(diger), diger)
        # panelde kendi etiketlerini yazdıysa onunkiler geçerli
        durum_sifirla(self.root)
        self.panel(action="edit", tag=T, title="B", description="Bilgi.\n\n#benim #etiketim")
        self.panel(action="approve", tag=T, code="now")
        self.assertEqual(self._paylas(meta)["hashtags"], ["benim", "etiketim"])

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
        for baslik in ("A&B " * 25, "&\"<" * 100):  # ikincisi kaçışla 1000'i aşar: başlık kısalır
            v = dict(self.vid(T), title=baslik, topic=("xyz&" * 220))
            self.req.cagrilar.clear()
            self.tb._edit_caption(v, CHAT)
            cap = self.tg(self.req.cagrilar, "editMessageCaption")[0]["data"]["caption"]
            self.assertLessEqual(len(cap), 1000)
            self.assertFalse(re.search(r"&[a-z#0-9]*</b>", cap), "kesik HTML varlığı")
            self.assertTrue(cap.startswith("🎬 <b>") and cap.endswith("</b>\nŞablon: " + (v.get("template") or "-")), cap)
            self.assertNotIn("Konu", cap)
        # başlık ve düğmeler aynıysa Telegram "not modified" der: hata sayılmaz, günlüğe yazılmaz
        self.req.hatalar["editMessageCaption"] = "Bad Request: message is not modified: specified new message content"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.tb._edit_caption(v, CHAT)
        self.assertEqual(out.getvalue(), "")

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

    def test_yazilan_konudan_seri_secilir(self):
        # Sabri'nin örnekleri ("Kuyumcu olsaydın", "Piyango sana çıksaydı") panelden ve /uret'ten kendi serisiyle üretilir
        c = self.panel(action="produce_topic", topic="Kuyumcu olsaydın ayda ne kazanırdın?")
        self.assertEqual([x for x in c if "gh" in x][0]["json"]["inputs"],
                         {"topic": "Kuyumcu olsaydın ayda ne kazanırdın?", "kalip": "olsaydin"})
        self.assertIn("(Ya sen olsaydın? serisi; genel video için konunun başına 'genel:' yaz)", self.mesajlar(c)[0])
        self.req.cagrilar.clear()
        c = self.panel(action="produce_topic", topic="genel: Piyango sana çıksaydı")
        self.assertEqual([x for x in c if "gh" in x][0]["json"]["inputs"], {"topic": "Piyango sana çıksaydı"})
        self.assertNotIn("serisi", self.mesajlar(c)[0])
        for metin, kalip, konu in (("/uret Çay nasıl demlenir?", "nasil", "Çay nasıl demlenir?"),
                                   ("/uret@BilgiMakasiBot uretim: Cam şişe", "uretim", "Cam şişe"),
                                   ("/uret kara delikler", None, "kara delikler")):
            self.req.cagrilar.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                self.tb.process_update(msg(metin), CHAT)
            gh = [x for x in self.req.cagrilar if "gh" in x]
            beklenen = {"topic": konu, **({"kalip": kalip} if kalip else {})}
            self.assertEqual(gh[0]["json"]["inputs"], beklenen, metin)
            yanit = self.tg(self.req.cagrilar, "sendMessage")[-1]["data"]["text"]
            self.assertEqual("serisi;" in yanit, bool(kalip), yanit)

    def test_seri_tahmini(self):
        from shortgen.trends import seri_tahmini
        ornekler = {
            "Piyango sana çıksaydı": "olsaydin", "Kuyumcu olsaydın": "olsaydin",
            "İstanbul'da yaşasaydın kira ne olurdu": "olsaydin", "Titanik batmasaydı ne olurdu": "",
            "Kurşun kalem nasıl üretiliyor?": "uretim", "Çikolata fabrikada nasıl yapılıyor": "uretim",
            "Çay nasıl demlenir?": "nasil", "Lavabo tıkanıklığı nasıl giderilir": "nasil",
            "Piramitler nasıl yapıldı?": "", "Mars'tan Dünya nasıl görünür?": "", "Kara delikler nasıl oluşur": "",
            "Japonlar hiç hasta olmaz, doğru mu?": "efsane", "Saat 12:30'da ne oldu": "", "": "",
            "Ya Sen Olsaydın: Osmanlı'da yaşamak": "olsaydin", "NASIL YAPILIR: Raf takmak": "nasil",
            "genel: Çay nasıl demlenir?": "", "efsane:": "",
            "kitap: Kürk Mantolu Madonna": "kitap", "Bir Kitap Bir Dakika: Dönüşüm": "kitap",
            "Kürk Mantolu Madonna": "", "Dönüşüm kitabı nasıl yazıldı?": "",
        }
        for konu, kalip in ornekler.items():
            self.assertEqual(seri_tahmini(konu)[0], kalip, konu)
        self.assertEqual(seri_tahmini("  Ya Sen Olsaydın:  Osmanlı'da   yaşamak "), ("olsaydin", "Osmanlı'da yaşamak"))
        self.assertEqual(seri_tahmini("Saat 12:30'da ne oldu"), ("", "Saat 12:30'da ne oldu"))
        self.assertEqual(seri_tahmini("KİTAP: Kürk Mantolu Madonna"), ("kitap", "Kürk Mantolu Madonna"))

    def test_zamanli_olcum_rapor_gondermez(self):
        # Sabri (2026-11-05): istatistik yalnız istediğinde gelsin. rapor.yml artık "kaydet" çalıştırır:
        # Telegram'a hiçbir şey gitmez, stats.json (son rapor) değişmez, panel geçmişine bir satır eklenir.
        import shortgen.stats as st
        snap = json.loads((FIX / "state" / "stats.json").read_text(encoding="utf-8"))
        snap["time"] = "2026-11-05T10:00+03:00"
        self.addCleanup(setattr, st, "collect", st.collect)
        st.collect = lambda: json.loads(json.dumps(snap))
        hist = self.root / "state" / "stats_gecmis.jsonl"
        once = hist.read_text(encoding="utf-8").splitlines()
        son_rapor = (self.root / "state" / "stats.json").read_text(encoding="utf-8")
        self.req.cagrilar.clear()
        st.record()
        self.assertEqual([x for x in self.req.cagrilar if "telegram" in str(x).lower()], [])
        self.assertEqual((self.root / "state" / "stats.json").read_text(encoding="utf-8"), son_rapor)
        sonra = hist.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sonra[:-1], once)
        self.assertEqual(json.loads(sonra[-1])["time"], "2026-11-05T10:00+03:00")
        wf = (REPO / ".github" / "workflows" / "rapor.yml").read_text(encoding="utf-8")
        self.assertIn("python -m shortgen.stats kaydet", wf)
        self.assertNotIn("shortgen.stats report", wf)

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
        self.assertTrue(msj[1].startswith("📊 <b>Bilgi Makası raporu</b>"))
        rapor = self.tg(c, "sendMessage")[1]["data"]
        self.assertEqual(rapor["parse_mode"], "HTML")
        self.assertIn("⚠️ TikTok: bağlı değil", rapor["text"])
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


class SadeMesajlar(Ortak):
    """Video ve açıklama ayrı mesaj; açıklama bir daha gelmez: paylaşım sonucu ve panel düzenlemesi metni tekrar yazmaz,
    düzenlemede açıklama mesajı yerinde güncellenir."""
    TAG = "short-20261105-134746"
    META = {"title": "Kraliçe <b>& Hitit</b> kralı", "topic": "Kraliçenin mektubu (kanca: dul kraliçe; gündem: Hititler)",
            "category": "tarih", "template": "kart", "created": "2026-11-05T13:47:46", "structure": "efsane",
            "hashtags": ["Hititler", "Hattuşa", "tarih", "Mısır", "bilgimakasi"],
            "description": "Dul kraliçe Hitit kralından koca istedi.\n\n#Hititler #Hattuşa #tarih #Mısır #bilgimakasi"
                           "\n\n📷 John Doe (CC BY-SA 4.0)"}
    SURUM = {"title": "Eski başlık", "hashtags": ["tarih", "boston"], "structure": "efsane",
             "description": "Eski bilgi.\n\n#tarih #boston\n\n📷 John Doe (CC BY-SA 4.0)"}
    ONAY = "🖥 Panelden: ✏️ Başlık ve açıklama güncellendi; paylaşımda yeni metin kullanılacak."
    YENI = "Yeni başlık\n\nYeni bilgi.\nİkinci satır.\n\n📷 John Doe (CC BY-SA 4.0)\n\n#tarih #boston #EfsaneMiGerçekMi"

    def bildir(self, meta=None):
        d = Path(tempfile.mkdtemp(prefix="bildir_", dir=self.root))
        (d / "metadata.json").write_text(json.dumps(meta or self.META, ensure_ascii=False), encoding="utf-8")
        (d / "video.mp4").write_bytes(b"x")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.tb.notify(d, self.TAG)
        self.cikti = out.getvalue()
        return self.req.cagrilar[:]

    # ------------------------------------------------------------ yeni video
    def test_video_kisa_baslikla_aciklama_ayri_mesajla_gelir(self):
        import shortgen.publish as P
        self.req.mesaj_no.update(sendVideo=501, sendMessage=502)
        c = self.bildir()
        self.assertEqual([x["tg"] for x in c], ["sendVideo", "sendMessage"])
        video, aciklama = c[0]["data"], c[1]["data"]
        self.assertEqual(video["caption"], "🎬 <b>Kraliçe &lt;b&gt;&amp; Hitit&lt;/b&gt; kralı</b>\nŞablon: kart")
        self.assertEqual(video["parse_mode"], "HTML")
        self.assertEqual(video["reply_markup"], {"inline_keyboard": [[
            {"text": "✅ Onayla", "callback_data": f"ok:{self.TAG}"}, {"text": "❌ Reddet", "callback_data": f"no:{self.TAG}"}]]})
        # açıklama: videoya yanıt değil, başlıksız düz metin; TikTok'a gidecek açıklamanın aynısı (seri etiketi dahil)
        self.assertEqual(aciklama["text"], P.tiktok_caption(P.apply_series_tag(self.META)))
        self.assertEqual(aciklama["text"], "Kraliçe <b>& Hitit</b> kralı\n\nDul kraliçe Hitit kralından koca istedi.\n\n"
                         "📷 John Doe (CC BY-SA 4.0)\n\n#Hititler #Hattuşa #tarih #EfsaneMiGerçekMi #bilgimakasi")
        self.assertNotIn("reply_to_message_id", aciklama)
        self.assertNotIn("parse_mode", aciklama)
        v = self.vid(self.TAG)
        self.assertEqual((v["status"], v["telegram_message_id"], v["aciklama_message_id"]), ("onay_bekliyor", 501, 502))
        self.assertEqual((v["title"], v["topic"], v["template"]), (self.META["title"], self.META["topic"], "kart"))

    def test_aciklama_gonderilemezse_video_yine_kayda_gecer(self):
        self.req.mesaj_no["sendVideo"] = 501
        self.req.hatalar["sendMessage"] = "Bad Request: chat not found"
        c = self.bildir()
        self.assertEqual([x["tg"] for x in c], ["sendVideo", "sendMessage"])
        v = self.vid(self.TAG)
        self.assertEqual((v["status"], v["telegram_message_id"]), ("onay_bekliyor", 501))
        self.assertNotIn("aciklama_message_id", v)
        self.assertIn("Açıklama mesajı gönderilemedi", self.cikti)
        # onay akışı bozulmaz
        self.req.hatalar.clear()
        self.panel(action="approve", tag=self.TAG, code="now")
        self.assertEqual(self.vid(self.TAG)["status"], "zamanlandi")

    # ------------------------------------------------------------ paylaşım sonucu
    def paylas(self, tiktok, **alanlar):
        """T'yi onaylayıp paylaştırır (YouTube ve Instagram bağlantıyla); TikTok sonucu verilir."""
        self.panel(action="approve", tag=T, code="now")
        if alanlar:
            self.video_degistir(T, **alanlar)
        self.req.cagrilar.clear()
        PanelIslemleri._paylas(self, PanelIslemleri.META, sonuc={"tiktok": tiktok})
        return self.req.cagrilar[:]

    SONUC = "📢 Paylaşıldı\n{}\n\n✅ YouTube: https://youtube/1\n✅ Instagram: https://instagram/1\n"
    KOPYALA = "✅ TikTok: taslak gönderildi. Açıklamayı yanıtlanan mesajdan kopyala."

    def test_paylasim_sonucu_aciklamayi_tekrar_yazmaz(self):
        cap = "Başlık\n\nTikTok bilgi metni.\n\n#tarih"
        self.panel(action="approve", tag=T, code="now")
        self.video_degistir(T, aciklama_message_id=55)
        self.req.cagrilar.clear()
        self.req.hatalar["editMessageText"] = "Bad Request: message is not modified: specified new message content"
        PanelIslemleri._paylas(self, PanelIslemleri.META, sonuc={
            "instagram": {"status": "ok", "url": "https://www.instagram.com/reel/X/", "note": "Kapak seçilemedi"},
            "tiktok": {"status": "ok", "id": "v_inbox", "draft": True, "caption": cap}})
        c = self.req.cagrilar
        # açıklama mesajı TikTok'a giden metne getirilir (aynıysa Telegram "not modified" der); yeni mesaj gitmez
        self.assertEqual([x["tg"] for x in c], ["editMessageText", "editMessageReplyMarkup", "sendMessage"])
        self.assertEqual((c[0]["data"]["message_id"], c[0]["data"]["text"]), (55, cap))
        m = c[-1]["data"]
        self.assertEqual(m["text"], f"📢 Paylaşıldı\n{self.vid(T)['title']}\n\n✅ YouTube: https://youtube/1\n"
                         "✅ Instagram: https://www.instagram.com/reel/X/\n   ⚠️ Kapak seçilemedi\n" + self.KOPYALA)
        self.assertNotIn("TikTok bilgi metni", m["text"])
        # sonuç açıklama mesajına yanıt: alıntıya dokununca kopyalanacak metin açılır (videonun düğmeleri yine videoda)
        self.assertEqual((m["reply_to_message_id"], m["allow_sending_without_reply"]), (55, "true"))
        self.assertEqual(c[1]["data"]["message_id"], 2)
        # açıklama panelin "Açıklamayı kopyala" düğmesi için kayıtta kalır
        self.assertEqual(self.vid(T)["platforms"]["tiktok"]["caption"], cap)
        self.assertEqual(self.vid(T)["aciklama_message_id"], 55)

    def test_paylasimda_eski_aciklama_mesaji_tiktok_metnine_getirilir(self):
        # ör. düzenlemede metadata.json alınamadığı için açıklama mesajı eski kaldı
        c = self.paylas({"status": "ok", "id": "v", "draft": True, "caption": self.YENI}, aciklama_message_id=55)
        ed, = self.tg(c, "editMessageText")
        self.assertEqual((ed["data"]["message_id"], ed["data"]["text"]), (55, self.YENI))
        m, = self.tg(c, "sendMessage")
        self.assertEqual(m["data"]["text"], self.SONUC.format(self.vid(T)["title"]) + self.KOPYALA)
        self.assertEqual(m["data"]["reply_to_message_id"], 55)

    def test_eski_videoda_aciklama_paylasimda_bir_kez_gonderilir(self):
        """Bu sürümden önce bildirilen videoların (ve notify'da açıklaması gönderilemeyenlerin) açıklama mesajı yok:
        videonun altındaki eski yanıt TikTok açıklaması değildir. TikTok'a giden metin bir kez ayrı mesajla gelir."""
        cap = "Başlık\n\nTikTok bilgi metni.\n\n📷 John Doe (CC BY-SA 4.0)\n\n#tarih #EfsaneMiGerçekMi"
        self.req.mesaj_no["sendMessage"] = 61
        c = self.paylas({"status": "ok", "id": "v", "draft": True, "caption": cap,
                         "note": "TikTok taslağı hâlâ işliyor, birkaç dakikada gelir"})
        self.assertEqual([x["tg"] for x in c], ["sendMessage", "editMessageReplyMarkup", "sendMessage"])
        aciklama, sonuc = c[0]["data"], c[2]["data"]
        self.assertEqual(aciklama["text"], cap)
        self.assertNotIn("reply_to_message_id", aciklama)
        self.assertEqual(sonuc["text"], self.SONUC.format(self.vid(T)["title"]) + self.KOPYALA
                         + "\n   ⚠️ TikTok taslağı hâlâ işliyor, birkaç dakikada gelir")
        self.assertNotIn("TikTok bilgi metni", sonuc["text"])
        self.assertEqual(sonuc["reply_to_message_id"], 61)
        self.assertEqual(self.vid(T)["aciklama_message_id"], 61)
        # tekrar denemede (aynı metin) yeni mesaj gitmez: aynı mesaj kullanılır
        durum_sifirla(self.root)
        self.req.hatalar["editMessageText"] = "Bad Request: message is not modified"
        c = self.paylas({"status": "ok", "id": "v", "draft": True, "caption": cap}, aciklama_message_id=61)
        self.assertEqual([x["tg"] for x in c], ["editMessageText", "editMessageReplyMarkup", "sendMessage"])
        self.assertEqual(c[-1]["data"]["reply_to_message_id"], 61)

    def test_aciklama_mesaji_yazilamazsa_aciklama_sonucta_gelir(self):
        cap = "Başlık\n\nTikTok bilgi metni.\n\n#tarih"
        asil, ilk = self.req.post, []

        def post(url, **kw):
            if url.endswith("/sendMessage") and not ilk:  # açıklama mesajı gitmez; sonuç mesajı gider
                ilk.append(url)
                return Yanit(429, {"ok": False, "description": "Too Many Requests: retry after 5"})
            return asil(url, **kw)
        self.panel(action="approve", tag=T, code="now")
        self.req.cagrilar.clear()
        self.req.post = post
        try:
            PanelIslemleri._paylas(self, PanelIslemleri.META, sonuc={
                "tiktok": {"status": "ok", "id": "v", "draft": True, "caption": cap}})
        finally:
            self.req.post = asil
        self.assertEqual(len(ilk), 1)
        m = self.tg(self.req.cagrilar, "sendMessage")[-1]["data"]
        # tek kopya sonuçta: eskisi gibi açıklama burada, sonuç videoya yanıt
        self.assertEqual(m["text"], self.SONUC.format(self.vid(T)["title"]) + f"✅ TikTok: taslak gönderildi.\n\n{cap}\n")
        self.assertEqual(m["reply_to_message_id"], 2)
        self.assertNotIn("allow_sending_without_reply", m)
        self.assertNotIn("aciklama_message_id", self.vid(T))

    def test_duzenlenen_eski_videonun_sonucu_yeni_aciklama_mesajina_yanittir(self):
        """Eski videoda panel düzenlemesi açıklamayı sohbetin sonuna yeni mesajla gönderir; videonun hemen altındaki
        eski yanıt düzenlenmemiş metindir. Sonuç yeni açıklama mesajına yanıt olur ki yanlış metin kopyalanmasın."""
        self.req.surumler[T] = self.SURUM
        self.req.mesaj_no["sendMessage"] = 77
        self.duzenle()
        self.assertEqual(self.vid(T)["aciklama_message_id"], 77)
        self.req.mesaj_no.clear()
        self.req.hatalar["editMessageText"] = "Bad Request: message is not modified"
        c = self.paylas({"status": "ok", "id": "v", "draft": True, "caption": self.YENI})
        self.assertEqual(self.tg(c, "editMessageText")[0]["data"]["message_id"], 77)
        m, = self.tg(c, "sendMessage")
        self.assertEqual(m["data"]["text"], self.SONUC.format("Yeni başlık") + self.KOPYALA)
        self.assertEqual(m["data"]["reply_to_message_id"], 77)

    def test_paylasim_sonucunda_diger_notlar_gorunur(self):
        c = self.paylas({"status": "ok", "url": "https://www.tiktok.com/@b/video/7",
                         "note": "Video 'yalnızca ben' olarak paylaşıldı"}, aciklama_message_id=55)
        m, = self.tg(c, "sendMessage")
        self.assertTrue(m["data"]["text"].endswith(
            "✅ TikTok: https://www.tiktok.com/@b/video/7\n   ⚠️ Video 'yalnızca ben' olarak paylaşıldı"), m)
        # taslak değilse açıklama mesajına dokunulmaz, sonuç videoya yanıttır
        self.assertEqual(self.tg(c, "editMessageText"), [])
        self.assertEqual(m["data"]["reply_to_message_id"], 2)

    # ------------------------------------------------------------ panel düzenlemesi
    def duzenle(self, **kw):
        p = {"title": "Yeni başlık", "description": "Yeni bilgi.\nİkinci satır.", **kw}
        return self.panel(action="edit", tag=T, **p)

    def test_duzenleme_aciklama_mesajini_yerinde_gunceller(self):
        import shortgen.publish as P
        self.video_degistir(T, aciklama_message_id=55)
        self.req.surumler[T] = self.SURUM
        c = self.duzenle()
        v = self.vid(T)
        ed = self.tg(c, "editMessageText")
        self.assertEqual(len(ed), 1)
        self.assertEqual((ed[0]["data"]["chat_id"], ed[0]["data"]["message_id"]), (CHAT, 55))
        self.assertEqual(ed[0]["data"]["text"],
                         P.tiktok_caption(self.tb._apply_edit(P.apply_series_tag(self.SURUM), v["duzenleme"])))
        self.assertEqual(ed[0]["data"]["text"], self.YENI)
        self.assertNotIn("parse_mode", ed[0]["data"])
        # yalnız release bilgisi ve metadata.json okunur (video indirilmez); anahtar yalnız GitHub API'ye gider
        gets = [x for x in c if "get" in x]
        self.assertEqual([x["get"] for x in gets], [GH_SURUM + "tags/" + T, GH_SURUM + "assets/11"])
        self.assertEqual(gets[1]["accept"], "application/octet-stream")
        self.assertEqual({x["yetki"] for x in gets}, {"Bearer ghs_TEST"})
        # onay mesajı kısa ve metni tekrar etmez; yeni açıklama mesajı gönderilmez
        self.assertEqual(self.mesajlar(c), [self.ONAY])
        self.assertEqual(v["aciklama_message_id"], 55)
        cap = self.tg(c, "editMessageCaption")[0]["data"]["caption"]
        self.assertEqual(cap, "🎬 <b>Yeni başlık</b>\nŞablon: " + v["template"])

    def test_paylasilmis_platform_notu_kalir(self):
        self.video_degistir(T, aciklama_message_id=55, status="zamanlandi", schedule=None,
                            publish_at=(SIMDI + _dt.timedelta(minutes=30)).isoformat(),
                            platforms={"youtube": {"status": "ok", "url": "u"}})
        self.req.surumler[T] = self.SURUM
        c = self.duzenle()
        self.assertEqual(self.mesajlar(c), [self.ONAY + "\n(Zaten paylaşılan YouTube paylaşımında eski metin kalır.)"])

    def test_degismeyen_aciklama_hata_sayilmaz(self):
        self.video_degistir(T, aciklama_message_id=55)
        self.req.surumler[T] = self.SURUM
        self.req.hatalar["editMessageText"] = ("Bad Request: message is not modified: specified new message content and "
                                               "reply markup of the specified message are exactly the same")
        c = self.duzenle()
        self.assertEqual(len(self.tg(c, "editMessageText")), 1)
        self.assertEqual(self.mesajlar(c), [self.ONAY])
        self.assertEqual(self.vid(T)["aciklama_message_id"], 55)
        self.assertNotIn("düzenlenemedi", self.cikti)

    def test_eski_videoda_aciklama_yeni_mesajla_gelir_ve_kaydedilir(self):
        self.req.surumler[T] = self.SURUM
        self.req.mesaj_no["sendMessage"] = 77
        c = self.duzenle()
        self.assertEqual(self.tg(c, "editMessageText"), [])
        aciklama, onay = self.tg(c, "sendMessage")
        self.assertEqual(aciklama["data"]["text"], self.YENI)
        self.assertNotIn("reply_to_message_id", aciklama["data"])
        self.assertEqual(onay["data"]["text"], self.ONAY)
        self.assertEqual(self.vid(T)["aciklama_message_id"], 77)
        # sonraki düzenleme o mesajı yerinde günceller
        self.req.cagrilar.clear()
        c = self.duzenle(title="Üçüncü başlık")
        self.assertEqual(self.tg(c, "editMessageText")[0]["data"]["message_id"], 77)
        self.assertTrue(self.tg(c, "editMessageText")[0]["data"]["text"].startswith("Üçüncü başlık\n\n"))
        self.assertEqual(self.mesajlar(c), [self.ONAY])

    def test_silinmis_aciklama_mesaji_yerine_yenisi_gonderilir(self):
        self.video_degistir(T, aciklama_message_id=55)
        self.req.surumler[T] = self.SURUM
        self.req.hatalar["editMessageText"] = "Bad Request: message to edit not found"
        self.req.mesaj_no["sendMessage"] = 78
        c = self.duzenle()
        self.assertEqual(self.mesajlar(c), [self.YENI, self.ONAY])
        self.assertEqual(self.vid(T)["aciklama_message_id"], 78)

    UYARI = "\n⚠️ Açıklama mesajı şimdi güncellenemedi; TikTok taslağı gönderilirken yenilenecek."

    def test_metadata_alinamazsa_aciklama_mesajina_dokunulmaz_ve_uyarilir(self):
        """metadata.json yoksa TikTok açıklaması kurulamaz: görsel atfı ve etiketleri eksik metin yazılmaz, onayda uyarı
        çıkar; TikTok taslağı gönderilirken açıklama mesajı TikTok'a giden metinle yenilenir."""
        self.video_degistir(T, aciklama_message_id=55)  # release yok (404)
        c = self.duzenle()
        self.assertEqual(self.tg(c, "editMessageText"), [])
        self.assertIn("metadata.json alınamadı", self.cikti)
        self.assertIn("404", self.cikti)
        self.assertEqual(self.vid(T)["duzenleme"]["title"], "Yeni başlık")
        self.assertEqual(self.vid(T)["aciklama_message_id"], 55)
        self.assertEqual(self.mesajlar(c), [self.ONAY + self.UYARI])
        # sonra paylaşımda mesaj tam TikTok açıklamasına getirilir
        c = self.paylas({"status": "ok", "id": "v", "draft": True, "caption": self.YENI})
        self.assertEqual(self.tg(c, "editMessageText")[0]["data"]["text"], self.YENI)
        # anahtar tanımlı değilse de aynı yol; GitHub'a istek gitmez
        durum_sifirla(self.root)
        self.video_degistir(T, aciklama_message_id=55)
        self.req.surumler[T] = self.SURUM
        self.req.cagrilar.clear()
        eski = {k: os.environ.pop(k) for k in ("GITHUB_TOKEN", "GH_TOKEN") if k in os.environ}
        try:
            c = self.duzenle()
        finally:
            os.environ.update(eski)
        self.assertEqual([x for x in c if "get" in x], [])
        self.assertEqual(self.tg(c, "editMessageText"), [])
        self.assertEqual(self.mesajlar(c), [self.ONAY + self.UYARI])
        # eski videoda (açıklama mesajı yok) eksik metinle yeni mesaj da gönderilmez
        durum_sifirla(self.root)
        self.req.surumler.clear()
        self.req.cagrilar.clear()
        c = self.duzenle()
        self.assertEqual(self.mesajlar(c), [self.ONAY + self.UYARI])
        self.assertNotIn("aciklama_message_id", self.vid(T))

    def test_tiktok_paylasildiysa_uyari_cikmaz(self):
        self.video_degistir(T, aciklama_message_id=55, status="zamanlandi", schedule=None,
                            publish_at=(SIMDI + _dt.timedelta(minutes=30)).isoformat(),
                            platforms={"tiktok": {"status": "ok", "url": "u"}})
        c = self.duzenle()  # release yok: mesaj güncellenemez ama TikTok'a artık kopyalanmayacak
        self.assertEqual(self.mesajlar(c), [self.ONAY + "\n(Zaten paylaşılan TikTok paylaşımında eski metin kalır.)"])

    def test_beklenmeyen_dosya_adresine_anahtar_gitmez(self):
        self.video_degistir(T, aciklama_message_id=55)
        asil = self.req.get

        def get(url, headers=None, **kw):
            self.req.cagrilar.append({"get": url})
            return Yanit(200, {"assets": [{"name": "metadata.json", "url": "https://baska.example/metadata.json"}]})
        self.req.get = get
        try:
            c = self.duzenle()
        finally:
            self.req.get = asil
        self.assertEqual([x["get"] for x in c if "get" in x], [GH_SURUM + "tags/" + T])
        self.assertEqual(self.tg(c, "editMessageText"), [])
        self.assertEqual(self.mesajlar(c), [self.ONAY + self.UYARI])

    def test_aciklama_mesaji_yazilamazsa_duzenleme_yine_kaydedilir(self):
        self.video_degistir(T, aciklama_message_id=55)
        self.req.surumler[T] = self.SURUM
        self.req.hatalar["editMessageText"] = "Bad Request: message can't be edited"
        asil, ilk = self.req.post, []

        def post(url, **kw):
            if url.endswith("/sendMessage") and not ilk:  # yeni açıklama mesajı da gitmez; onay mesajı gider
                ilk.append(url)
                return Yanit(429, {"ok": False, "description": "Too Many Requests: retry after 5"})
            return asil(url, **kw)
        self.req.post = post
        try:
            c = self.duzenle()
        finally:
            self.req.post = asil
        self.assertEqual(len(ilk), 1)
        self.assertEqual(self.vid(T)["duzenleme"]["description"], "Yeni bilgi.\nİkinci satır.")
        self.assertEqual(self.vid(T)["aciklama_message_id"], 55)
        self.assertEqual(self.mesajlar(c), [self.ONAY + self.UYARI])
        self.assertIn("Açıklama mesajı güncellenemedi", self.cikti)

    def test_uzun_aciklama_telegram_sinirina_sigar(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb._send_desc(CHAT, "😀" * 3000)  # TikTok açıklaması 2200'ü geçmez; yine de sınır korunur
        metin = self.tg(self.req.cagrilar, "sendMessage")[0]["data"]["text"]
        self.assertLessEqual(len(metin.encode("utf-16-le")) // 2, 4096)

    # ------------------------------------------------------------ TikTok açıklaması değişmedi
    def _tiktok(self, meta, taslak=False):
        import shortgen.publish as P
        giden = {}

        class R:
            def __init__(s, d):
                s._d, s.ok, s.status_code, s.text = d, True, 200, ""

            def json(s):
                return s._d

        def post(url, headers=None, json=None, timeout=None, **kw):  # noqa: A002
            if url.endswith("/creator_info/query/"):
                return R({"data": {"privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]}})
            if url.endswith("/post/publish/video/init/"):
                giden["title"] = json["post_info"]["title"]
                if taslak:
                    return R({"error": {"code": "unaudited_client_can_only_post_to_private_accounts"}})
                return R({"data": {"publish_id": "p1", "upload_url": "https://up"}, "error": {"code": "ok"}})
            if url.endswith("/post/publish/inbox/video/init/"):
                return R({"data": {"publish_id": "p1", "upload_url": "https://up"}, "error": {"code": "ok"}})
            if url.endswith("/status/fetch/"):
                return R({"data": {"status": "SEND_TO_USER_INBOX"} if taslak
                          else {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [7]}})
            raise AssertionError(url)
        eski = (P._tt_token, P.requests)
        P._tt_token = lambda: "act.test"
        P.requests = types.SimpleNamespace(post=post, put=lambda *a, **k: types.SimpleNamespace(status_code=201, text=""))
        try:
            video = self.root / "tt.mp4"
            video.write_bytes(b"x")
            res = P.tiktok(video, meta)
        finally:
            P._tt_token, P.requests = eski
        return giden["title"], res

    TT_META = {"title": "Tutankamon'un dul eşi & Hitit kralı",
               "hashtags": ["Tutankamon Mektubu", "Hititler", "Hattuşa", "tarih", "bilgimakasi", "fazla"],
               "description": "Firavunun dul eşi, Hattuşa'daki kraldan oğullarından birini koca istedi. 😀 #gömülü\n"
                              "Sence prens Mısır'a varsaydı ne olurdu?   \n\n\nKaynaklar: Wikipedia\n"
                              "🎙 Seslendirme: yapay zekâ\n\n#TutankamonHititMektubu #Hititler #Hattuşa #tarih #bilgimakasi"
                              "\n\n📷 Scan by Pataki Márta (CC BY-SA 3.0), Celpunken (CC BY 3.0)",
               "structure": "efsane"}

    def test_tiktok_aciklamasi_onceki_surumle_ayni(self):
        """Beklenen metinler tiktok_caption ayrılmadan önceki tiktok() ile üretildi."""
        import hashlib
        import shortgen.publish as P
        eski = ("Tutankamon'un dul eşi & Hitit kralı\n\nFiravunun dul eşi, Hattuşa'daki kraldan oğullarından birini koca "
                "istedi. 😀\nSence prens Mısır'a varsaydı ne olurdu?\n\n📷 Scan by Pataki Márta (CC BY-SA 3.0), Celpunken "
                "(CC BY 3.0)\n\n#TutankamonMektubu #Hititler #Hattuşa #tarih #bilgimakasi")
        baslik, res = self._tiktok(self.TT_META)
        self.assertEqual(baslik, eski)
        self.assertEqual(P.tiktok_caption(self.TT_META), eski)
        self.assertEqual(res, {"id": "7", "privacy": "PUBLIC_TO_EVERYONE", "url": "https://www.tiktok.com/@bilgimakasi/video/7"})
        seri, _ = self._tiktok(P.apply_series_tag(self.TT_META))
        self.assertEqual(seri, eski.replace("#tarih #bilgimakasi", "#EfsaneMiGerçekMi #bilgimakasi"))
        uzun = {**self.TT_META, "description": ("Uzun bilgi cümlesi 😀. " * 200) + "\n\n#a #b\n\n📷 Jane Doe (CC BY-SA 3.0)"}
        baslik, _ = self._tiktok(uzun)
        self.assertEqual(hashlib.sha256(baslik.encode()).hexdigest(),
                         "c5cac939c94c5b8057ae480c1e919f8ba317be90e60b43cd485ff07d54cc1c1c")
        self.assertEqual(P._u16(baslik), 2200)
        # taslak: aynı açıklama saklanır (panelin kopyala düğmesi), uzun yapıştırma notu yok
        baslik, res = self._tiktok(self.TT_META, taslak=True)
        self.assertEqual(baslik, eski)
        self.assertEqual(res, {"id": "p1", "draft": True, "caption": eski})


def utc(s: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


class Takvim(Ortak):
    """Panel takvimi (action "schedule"), en iyi saat planı ve saati gelen paylaşım için iş başlatma."""

    def setUp(self):
        super().setUp()
        self.uzak = None  # _origin_record'un döndüreceği uzak kayıt (None: alınamadı)
        self._eski_origin = self.tb._origin_record
        self.tb._origin_record = lambda tag: json.loads(json.dumps(self.uzak)) if self.uzak else None

    def tearDown(self):
        self.tb._origin_record = self._eski_origin

    def takvim(self, tag, **sched):
        return self.panel(action="schedule", tag=tag, schedule=sched, rid="r1")

    def kismen(self, saat="2026-11-05T10:00:00Z"):
        """Z: Instagram 12:30'da paylaşıldı, sıradaki YouTube 18:00 (TR)."""
        FakeDateTime.simdi = utc(saat)
        self.video_degistir(Z, platforms={"instagram": {"status": "ok", "url": "u", "at": "2026-11-05T12:30:05+03:00"}},
                            publish_at="2026-11-05T15:00:00+00:00")

    def test_onay_bekleyen_video_takvimdeki_saatlerle_onaylanir(self):
        c = self.takvim(T, youtube="2026-11-05T18:00:00+03:00", instagram="2026-11-05T09:30:20Z",
                        tiktok="2026-11-05T14:17:40+00:00")
        v = self.vid(T)
        self.assertEqual(v["schedule"], {"youtube": "2026-11-05T15:00:00+00:00", "instagram": "2026-11-05T09:30:00+00:00",
                                         "tiktok": "2026-11-05T14:18:00+00:00"})
        self.assertEqual((v["status"], v["publish_at"], v["decided"]),
                         ("zamanlandi", "2026-11-05T09:30:00+00:00", "2026-11-05T00:45:00+03:00"))
        self.assertEqual(self.tg(c, "editMessageReplyMarkup")[-1]["data"]["reply_markup"],
                         {"inline_keyboard": [[{"text": "🚫 Paylaşımı iptal et", "callback_data": f"cancel:{T}"}]]})
        m = self.tg(c, "sendMessage")[-1]["data"]
        self.assertEqual(m["text"], "🖥 Panelden: ✅ Onaylandı, takvimdeki saatlerde paylaşılacak:\n"
                         "• Instagram: 5 Kasım Perşembe 12:30 ⭐\n• TikTok: 5 Kasım Perşembe 17:18\n"
                         "• YouTube: 5 Kasım Perşembe 18:00 ⭐\nBir Mahalleyi Melas Dalgası Yuttu: 1919 Boston Faciası")
        self.assertEqual(m["reply_to_message_id"], 2)
        self.assertEqual([x for x in c if "gh" in x], [], "olay işi paylaşım başlatmaz (dispatch-if-due başlatır)")
        # ikinci istek (çift basış): video artık onay beklemiyor değil, saatleri değişir; aynı saatlerse dokunulmaz
        self.req.cagrilar.clear()
        c = self.takvim(T, youtube="2026-11-05T15:00:00+00:00", instagram="2026-11-05T09:30:00+00:00",
                        tiktok="2026-11-05T14:18:00+00:00")
        self.assertEqual(self.vid(T), v)
        self.assertIn("ℹ️ Saatler zaten böyle", self.mesajlar(c)[-1])

    def test_gecersiz_takvim_videoyu_degistirmez(self):
        tam = {"youtube": "2026-11-05T15:00:00+00:00", "instagram": "2026-11-05T09:30:00+00:00",
               "tiktok": "2026-11-05T16:30:00+00:00"}
        for sched, hata in (({k: tam[k] for k in ("youtube", "instagram")}, "üç platformun da saati"),
                            ({**tam, "facebook": tam["tiktok"]}, "bilinmeyen platform"),
                            ({}, "platform saatleri eksik"), (["x"], "platform saatleri eksik"),
                            ({**tam, "tiktok": "yarın"}, "TikTok saati geçersiz"),
                            ({**tam, "tiktok": "2026-11-05T16:30:00"}, "TikTok saati geçersiz"),  # saat dilimi yok
                            ({**tam, "tiktok": 1762360200}, "TikTok saati geçersiz"),
                            ({**tam, "youtube": "2026-11-04T21:41:00+00:00"}, "YouTube saati geçmişte kaldı"),
                            ({**tam, "youtube": "2026-12-05T21:46:00+00:00"}, "en çok 30 gün")):
            durum_sifirla(self.root)
            self.req.cagrilar.clear()
            once = self.vid(T)
            c = self.panel(action="schedule", tag=T, schedule=sched)
            self.assertEqual(self.vid(T), once, sched)
            self.assertIn("⚠️ İşlem yapılamadı: ", self.mesajlar(c)[-1])
            self.assertIn(hata, self.mesajlar(c)[-1], sched)
            # kapının '⏳ İşleniyor' kilidi geri alınır
            self.assertEqual(self.tg(c, "editMessageReplyMarkup")[-1]["data"]["reply_markup"]["inline_keyboard"][0][0]
                             ["callback_data"], f"ok:{T}")
        # yanlış durumdaki video (paylaşılmış): işlem yapılmaz
        once = self.vid(Y)
        c = self.panel(action="schedule", tag=Y, schedule={"tiktok": tam["tiktok"]})
        self.assertEqual(self.vid(Y), once)
        self.assertIn("ℹ️ İşlem yapılmadı: video şu an 'paylaşıldı' durumunda", self.mesajlar(c)[-1])

    def test_kapidan_gec_gelen_saat_simdiye_cekilir(self):
        # kapı şimdi+2 dk'yı denetler; iş 1-2 dk geç başlarsa saat geçmiş olabilir: 3 dk'ya kadar şimdiye çekilir
        FakeDateTime.simdi = SIMDI + _dt.timedelta(seconds=20)
        self.takvim(T, youtube="2026-11-04T21:43:00+00:00", instagram="2026-11-04T21:47:00+00:00",
                    tiktok="2026-11-05T16:30:00+00:00")
        v = self.vid(T)
        self.assertEqual((v["schedule"]["youtube"], v["schedule"]["instagram"], v["publish_at"]),
                         ("2026-11-04T21:45:20+00:00", "2026-11-04T21:47:00+00:00", "2026-11-04T21:45:20+00:00"))

    def test_zamanlanmis_videoda_yalniz_verilen_platformun_saati_degisir(self):
        FakeDateTime.simdi = utc("2026-11-05T05:00:00Z")
        c = self.takvim(Z, tiktok="2026-11-05T19:00:00+00:00")
        v = self.vid(Z)
        self.assertEqual(v["schedule"], {"youtube": "2026-11-05T15:00:00+00:00", "instagram": "2026-11-05T09:30:00+00:00",
                                         "tiktok": "2026-11-05T19:00:00+00:00"})
        self.assertEqual((v["status"], v["publish_at"]), ("zamanlandi", "2026-11-05T09:30:00+00:00"))
        self.assertEqual(v["decided"], "2026-11-04T23:38:40+03:00", "onay anı değişmez")
        self.assertEqual(self.mesajlar(c)[-1], "🖥 Panelden: 🗓 Paylaşım saatleri değişti:\n"
                         "• Instagram: 5 Kasım Perşembe 12:30 ⭐\n• YouTube: 5 Kasım Perşembe 18:00 ⭐\n"
                         "• TikTok: 5 Kasım Perşembe 22:00 ⭐\n" + v["title"])
        self.assertEqual(self.tg(c, "editMessageReplyMarkup")[-1]["data"]["reply_markup"]["inline_keyboard"][0][0]
                         ["callback_data"], f"cancel:{Z}")
        # en erken saat öne alınırsa publish_at da öne gelir
        self.takvim(Z, instagram="2026-11-05T05:30:00+00:00")
        self.assertEqual(self.vid(Z)["publish_at"], "2026-11-05T05:30:00+00:00")

    def test_kismen_paylasilmis_videoda_paylasilan_platformun_saati_degismez(self):
        self.kismen()
        once = self.vid(Z)
        c = self.takvim(Z, instagram="2026-11-05T17:00:00+00:00", tiktok="2026-11-05T17:00:00+00:00")
        self.assertEqual(self.vid(Z), once)
        self.assertIn("ℹ️ Saatler değiştirilmedi: Instagram zaten paylaşıldı.", self.mesajlar(c)[-1])
        self.assertEqual(self.tg(c, "editMessageReplyMarkup")[-1]["data"]["reply_markup"]["inline_keyboard"][0][0]
                         ["callback_data"], f"cancel:{Z}")
        c = self.takvim(Z, youtube="2026-11-05T17:00:00+00:00")
        v = self.vid(Z)
        self.assertEqual(v["schedule"]["instagram"], "2026-11-05T09:30:00+00:00", "paylaşılan platformun saati kalır")
        self.assertEqual(v["platforms"], once["platforms"])
        self.assertEqual((v["schedule"]["youtube"], v["publish_at"]), ("2026-11-05T17:00:00+00:00", "2026-11-05T16:30:00+00:00"))
        # mesajda yalnız bekleyen platformlar; 20:00 YouTube için prime time değil
        self.assertEqual(self.mesajlar(c)[-1].split("\n")[1:3], ["• TikTok: 5 Kasım Perşembe 19:30 ⭐",
                                                                  "• YouTube: 5 Kasım Perşembe 20:00"])

    def test_uzak_kayit_esas_alinir(self):
        # bu işin kopyası eski: uzakta YouTube az önce paylaşıldı
        FakeDateTime.simdi = utc("2026-11-05T10:00:00Z")
        self.video_degistir(Z, publish_at="2026-11-05T15:00:00+00:00",
                            platforms={"instagram": {"status": "ok", "url": "u"}})
        self.uzak = {**self.vid(Z), "platforms": {"instagram": {"status": "ok", "url": "u"},
                                                  "youtube": {"status": "ok", "url": "y"}},
                     "publish_at": "2026-11-05T16:30:00+00:00"}
        once = self.vid(Z)
        c = self.takvim(Z, youtube="2026-11-05T17:00:00+00:00")
        self.assertEqual(self.vid(Z), once)
        self.assertIn("YouTube zaten paylaşıldı", self.mesajlar(c)[-1])
        c = self.takvim(Z, tiktok="2026-11-05T18:00:00+00:00")
        v = self.vid(Z)
        # publish_at yalnız bekleyen platformdan (TikTok) hesaplanır; YouTube'un eski saati onu öne çekmez
        self.assertEqual((v["schedule"]["tiktok"], v["publish_at"]), ("2026-11-05T18:00:00+00:00", "2026-11-05T18:00:00+00:00"))
        self.assertEqual(self.mesajlar(c)[-1].split("\n")[1:-1], ["• TikTok: 5 Kasım Perşembe 21:00"])
        # uzakta iptal edilmiş
        self.uzak = {**self.vid(Z), "status": "onay_bekliyor", "publish_at": None}
        once = self.vid(Z)
        c = self.takvim(Z, tiktok="2026-11-05T19:00:00+00:00")
        self.assertEqual(self.vid(Z), once)
        self.assertIn("ℹ️ Saatler değiştirilmedi: video şu an 'onay bekliyor' durumunda.", self.mesajlar(c)[-1])
        self.assertEqual(self.tg(c, "editMessageReplyMarkup")[-1]["data"]["reply_markup"]["inline_keyboard"][0][0]
                         ["callback_data"], f"ok:{Z}")

    def test_paylasima_10_dk_kala_saat_degismez(self):
        self.kismen("2026-11-05T14:51:00Z")  # YouTube 15:00Z: 9 dk kaldı
        once = self.vid(Z)
        c = self.takvim(Z, tiktok="2026-11-05T19:00:00+00:00")
        self.assertEqual(self.vid(Z), once)
        self.assertIn("ℹ️ Saatler değiştirilmedi: bir paylaşım şu an sürüyor ya da 10 dakika içinde", self.mesajlar(c)[-1])
        # uzak kayıtta paylaşım anı yakınsa da (yerel kopya eski) değişmez
        self.kismen("2026-11-05T10:00:00Z")
        self.uzak = {**self.vid(Z), "publish_at": "2026-11-05T10:05:00+00:00",
                     "schedule": {**self.vid(Z)["schedule"], "youtube": "2026-11-05T10:05:00+00:00"}}
        c = self.takvim(Z, tiktok="2026-11-05T19:00:00+00:00")
        self.assertIn("10 dakika içinde", self.mesajlar(c)[-1])
        # eskimiş publish_at (bekleyen platformların hepsi daha sonra) kilitlemez
        self.uzak = None
        self.video_degistir(Z, publish_at="2026-11-05T09:30:00+00:00")
        self.takvim(Z, tiktok="2026-11-05T19:00:00+00:00")
        self.assertEqual(self.vid(Z)["schedule"]["tiktok"], "2026-11-05T19:00:00+00:00")

    def test_paylasim_ani(self):
        v = {"status": "zamanlandi", "publish_at": "2026-11-05T09:30:00+00:00",
             "schedule": {"youtube": "2026-11-05T15:00:00+00:00", "instagram": "2026-11-05T09:30:00+00:00",
                          "tiktok": "2026-11-05T16:30:00+00:00"}, "platforms": {}}
        self.assertEqual(self.tb._due_at(v), utc("2026-11-05T09:30:00Z"))
        v["platforms"] = {"instagram": {"status": "ok"}}  # eskimiş publish_at: sıradaki YouTube
        self.assertEqual(self.tb._due_at(v), utc("2026-11-05T15:00:00Z"))
        v["platforms"] = {"instagram": {"status": "hata"}}  # saati geçip paylaşılamayan platform publish_at'te denenir
        v["publish_at"] = "2026-11-05T15:00:00+00:00"
        self.assertEqual(self.tb._due_at(v), utc("2026-11-05T15:00:00Z"))
        self.assertEqual(self.tb._due_at({"status": "zamanlandi", "publish_at": "2026-11-05T12:00:00+00:00", "schedule": None}),
                         utc("2026-11-05T12:00:00Z"))
        self.assertIsNone(self.tb._due_at({**v, "status": "onay_bekliyor"}))
        self.assertIsNone(self.tb._due_at({"status": "zamanlandi"}))

    def dispatch(self, saat):
        """dispatch_if_due: (sonuç, başlatılan onay.yml işleri, iş listesi istekleri)."""
        FakeDateTime.simdi = utc(saat)
        self.req.cagrilar.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc = self.tb.dispatch_if_due()
        return sonuc, [c for c in self.req.cagrilar if "gh" in c], [c for c in self.req.cagrilar if "gh_get" in c]

    @staticmethod
    def is_(st, dk, ad, simdi, sonuc=None):
        """onay.yml iş listesindeki bir iş: simdi'den dk dakika önce başlatılmış."""
        return {"display_title": ad, "name": "Telegram onaylarını işle", "status": st, "conclusion": sonuc,
                "created_at": (utc(simdi) - _dt.timedelta(minutes=dk)).isoformat().replace("+00:00", "Z")}

    def test_saati_yaklasan_paylasim_icin_onay_isi_hedefle_baslatilir(self):
        calistir = self.dispatch
        # fikstürdeki en yakın paylaşım: GTA (Z) 09:30Z; iş en çok 3 dk önce başlatılır (kurulum ~1 dk, boş bekleme olmasın)
        ok, d, g = calistir("2026-11-05T09:27:30Z")
        self.assertTrue(ok)
        self.assertEqual(d, [{"gh": "onay.yml", "json": {"ref": "main", "inputs": {"dakika": "5", "hedef": "2026-11-05T09:30Z"}}}])
        self.assertEqual(g, [{"gh_get": "onay.yml/runs", "params": {"per_page": 20}, "auth": "Bearer ghs_TEST"}])
        self.assertEqual(calistir("2026-11-05T09:26:30Z")[:2], (False, []), "3 dakikadan uzak")
        self.assertEqual(calistir("2026-11-05T09:29:50Z")[1][0]["json"]["inputs"], {"dakika": "3", "hedef": "2026-11-05T09:30Z"})
        # aynı hedefle bekleyen iş ya da son 30 dk'da başlatılmış iş varsa başlatılmaz
        is_ = lambda st, dk, ad="Paylaşım 2026-11-05T09:30Z": self.is_(st, dk, ad, "2026-11-05T09:28:00Z")  # noqa: E731
        for isler in ([is_("queued", 1)], [is_("in_progress", 40)], [is_("completed", 20)]):
            self.req.isler = isler
            self.assertEqual(calistir("2026-11-05T09:28:00Z")[:2], (False, []), isler)
        iptal = {**is_("completed", 5), "conclusion": "cancelled"}  # state grubunda çalışmadan iptal edilmiş
        for isler in ([is_("completed", 31)], [is_("queued", 1, "Paylaşım 2026-11-05T12:00Z")], [is_("queued", 1, "Telegram onaylarını işle")],
                      [iptal]):
            self.req.isler = isler
            self.assertTrue(calistir("2026-11-05T09:28:00Z")[0], isler)
        # iş listesi alınamazsa yine başlatılır (bu adım her kayıttan sonra bir kez çalışır, döngü yapmaz)
        self.req.isler, self.req.isler_durum = [], 500
        self.assertTrue(calistir("2026-11-05T09:28:00Z")[0])
        self.req.isler_durum, self.req.dispatch_durum = 200, 422
        self.assertFalse(calistir("2026-11-05T09:28:00Z")[0])
        self.req.dispatch_durum = 204
        # saati 3 saatten eski takılı kayıt (Z, 09:30Z) sayılmaz: sıradaki (2048, 17:00Z) için başlatılır
        self.video_degistir("short-20261104-2100", status="iptal")
        self.assertEqual(calistir("2026-11-05T16:57:30Z")[1][0]["json"]["inputs"], {"dakika": "5", "hedef": "2026-11-05T17:00Z"})
        self.video_degistir("short-20261104-2048", status="iptal")
        self.assertEqual(calistir("2026-11-05T16:57:30Z")[:2], (False, []), "yalnız takılı kayıt ve uzak saat kaldı")

    def test_saati_gecmis_kaydin_isi_sonraki_videonun_paylasimini_bekletmez(self):
        # A (GTA) 40 dk önce paylaşılacaktı, hâlâ bekliyor; B (Açlık Oyunları) Instagram'ı 1,5 dk sonra
        simdi, A, B = "2026-11-05T14:52:30Z", "2026-11-05T14:12Z", "2026-11-05T14:54Z"
        self.video_degistir("short-20261104-2100", status="iptal")
        self.video_degistir(Z, publish_at="2026-11-05T14:12:00+00:00", schedule={p: "2026-11-05T14:12:00+00:00" for p in
                                                                                  ("youtube", "instagram", "tiktok")})
        self.video_degistir("short-20261104-2048", publish_at="2026-11-05T14:54:00+00:00",
                            schedule={"youtube": "2026-11-05T18:00:00+00:00", "instagram": "2026-11-05T14:54:00+00:00",
                                      "tiktok": "2026-11-05T19:00:00+00:00"})
        is_ = lambda st, dk, ad, sonuc=None: self.is_(st, dk, ad, simdi, sonuc)  # noqa: E731
        b_isi = {"ref": "main", "inputs": {"dakika": "4", "hedef": B}}
        # A'nın işi hata aldı (20 dk önce) ya da hâlâ yüklüyor: B için ayrıca başlatılır
        for isler in ([is_("completed", 20, f"Paylaşım {A}", "failure")], [is_("in_progress", 39, f"Paylaşım {A}")]):
            self.req.isler = isler
            ok, d, g = self.dispatch(simdi)
            self.assertEqual((ok, [x["json"] for x in d], len(g)), (True, [b_isi], 1), isler)
        # A'nın işi yok (ör. 30 dk'dan eski): önce A için başlatılır (hemen paylaşır; B 2 dk'lık pencerede)
        self.req.isler = [is_("completed", 45, f"Paylaşım {A}", "failure")]
        self.assertEqual(self.dispatch(simdi)[1][0]["json"]["inputs"], {"dakika": "2", "hedef": A})
        # B'nin işi kuyrukta, A'nınki onun yüzünden iptal oldu: başlamamış iş A'yı da paylaşır, yenisi başlatılmaz
        # (başlatılsaydı kuyruktaki B işini iptal eder, iki hedef birbirini iptal edip dururdu)
        self.req.isler = [is_("queued", 1, f"Paylaşım {B}"), is_("completed", 2, f"Paylaşım {A}", "cancelled")]
        self.assertEqual(self.dispatch(simdi)[:2], (False, []))
        # başlamamış başka iş, saati henüz gelmemiş B'yi üstlenmez
        self.req.isler = [is_("completed", 20, f"Paylaşım {A}", "failure"), is_("queued", 1, "Telegram onaylarını işle")]
        self.assertEqual([x["json"] for x in self.dispatch(simdi)[1]], [b_isi])

    def test_kismen_paylasilip_iptal_edilen_video_takvimden_onaylanir(self):
        # Instagram paylaşıldı, kalanlar iptal edildi: video yeniden onay bekler, Instagram kaydı kalır
        self.kismen("2026-11-05T13:00:00Z")
        self.panel(action="cancel", tag=Z)
        v = self.vid(Z)
        self.assertEqual((v["status"], v["schedule"], v["platforms"]["instagram"]["status"]), ("onay_bekliyor", None, "ok"))
        once = self.vid(Z)
        for sched, hata in (({"youtube": "2026-11-05T15:00:00Z", "instagram": "2026-11-05T15:00:00Z", "tiktok": "2026-11-05T16:30:00Z"},
                             "Instagram zaten paylaşıldı"),
                            ({"youtube": "2026-11-05T15:00:00Z"}, "onay için TikTok saati de seçilmeli")):
            self.req.cagrilar.clear()
            c = self.takvim(Z, **sched)
            self.assertEqual(self.vid(Z), once, sched)
            self.assertIn(hata, self.mesajlar(c)[-1])
        # paylaşılmamış platformların saatiyle onaylanır; Instagram yeniden paylaşılmaz
        c = self.takvim(Z, youtube="2026-11-05T16:00:00Z", tiktok="2026-11-05T15:20:00Z")
        v = self.vid(Z)
        self.assertEqual((v["status"], v["publish_at"], v["platforms"]), ("zamanlandi", "2026-11-05T15:20:00+00:00", once["platforms"]))
        self.assertEqual(v["schedule"], {"youtube": "2026-11-05T16:00:00+00:00", "tiktok": "2026-11-05T15:20:00+00:00"})
        self.assertEqual(self.mesajlar(c)[-1].split("\n")[:3], ["🖥 Panelden: ✅ Onaylandı, takvimdeki saatlerde paylaşılacak:",
                                                               "• TikTok: 5 Kasım Perşembe 18:20", "• YouTube: 5 Kasım Perşembe 19:00"])
        self.assertEqual(self.tb._due_at(v), utc("2026-11-05T15:20:00Z"))

    def test_hata_alan_platform_baska_saat_one_alininca_kendi_saatinde_kalir(self):
        # YouTube 15:00'te hata aldı (sıradaki turda, publish_at 16:30'da yeniden denenecek), Instagram paylaşıldı
        FakeDateTime.simdi = utc("2026-11-05T15:10:00Z")
        self.video_degistir(Z, publish_at="2026-11-05T16:30:00+00:00",
                            platforms={"instagram": {"status": "ok", "url": "u"}, "youtube": {"status": "hata", "error": "x"}})
        c = self.takvim(Z, tiktok="2026-11-05T15:30:00Z")
        v = self.vid(Z)
        self.assertEqual(v["schedule"], {"youtube": "2026-11-05T16:30:00+00:00", "instagram": "2026-11-05T09:30:00+00:00",
                                         "tiktok": "2026-11-05T15:30:00+00:00"})
        self.assertEqual(v["publish_at"], "2026-11-05T15:30:00+00:00")
        # mesaj kaydedilen planla (ve panelle) aynı: YouTube 19:30'da (16:30Z) denenir, TikTok'la öne çekilmez
        self.assertEqual(self.mesajlar(c)[-1].split("\n")[1:3], ["• TikTok: 5 Kasım Perşembe 18:30", "• YouTube: 5 Kasım Perşembe 19:30"])
        self.assertEqual(self.tb._pending_sched(v), {"youtube": "2026-11-05T16:30:00+00:00", "tiktok": "2026-11-05T15:30:00+00:00"})

    def test_en_iyi_saat_yalniz_prime_time(self):
        self.assertEqual(self.tb.EXTRA_TIMES, {"youtube": [], "instagram": [], "tiktok": []})
        # 5 Kasım 08:00 TR: bugünün en iyi saatleri boş
        now = _dt.datetime(2026, 11, 5, 8, 0, tzinfo=TRZ)
        self.assertEqual(self.tb._best_schedule(now, ignore_busy=True),
                         {"youtube": "2026-11-05T15:00:00+00:00", "instagram": "2026-11-05T09:30:00+00:00",
                          "tiktok": "2026-11-05T16:30:00+00:00"})
        # fikstürde 5 Kasım'ın saatleri dolu: ek saate (15:00/17:00) değil ertesi günün en iyi saatine geçer
        sec = self.tb._best_schedule(now, exclude=T)
        for p, t in sec.items():
            self.assertTrue(self.tb._is_prime(p, t), (p, t))
        # Instagram 12:30 ve 20:00 (5 Kasım) ile 12:30 (6 Kasım) dolu: 6 Kasım 20:00
        self.assertEqual(sec["instagram"], "2026-11-06T17:00:00+00:00")
        # EXTRA_TIMES ortam değişkeniyle verilirse ek saat yine kullanılır
        eski = self.tb.EXTRA_TIMES
        try:
            self.tb.EXTRA_TIMES = {"youtube": [], "instagram": ["23:00"], "tiktok": []}
            self.assertEqual(self.tb._best_schedule(now, exclude=T)["instagram"], "2026-11-05T20:00:00+00:00")
        finally:
            self.tb.EXTRA_TIMES = eski

    def test_plan_metni_prime_time_ve_panel_notu(self):
        s = {"tiktok": "2026-11-05T16:31:00+00:00", "youtube": "2026-11-05T15:00:00+00:00"}
        self.assertEqual(self.tb._plan_text(s), "• YouTube: 5 Kasım Perşembe 18:00 ⭐\n• TikTok: 5 Kasım Perşembe 19:31\n"
                                                "Saatleri değiştirmek için panelde Takvim: /panel")
        self.assertEqual(self.tb._plan_text({}), "")
        self.assertTrue(self.tb._is_prime("instagram", "2026-11-05T12:30:00+03:00"))
        self.assertFalse(self.tb._is_prime("youtube", "2026-11-05T12:30:00+03:00"))
        # düzeltme mesajı: uzun açıklama ve "(günün ek saati)" yok
        self.kismen("2026-11-05T05:00:00Z")
        self.req.cagrilar.clear()
        self.tb.duzelt(Z)
        metin = self.mesajlar(self.req.cagrilar)[-1]
        self.assertNotIn("Asıl en iyi", metin)
        self.assertNotIn("ek saat", metin)
        self.assertIn("✅ Instagram: paylaşıldı (5 Kasım Perşembe 12:30)\n• YouTube: 5 Kasım Perşembe 18:00 ⭐\n"
                      "• TikTok: 5 Kasım Perşembe 19:30 ⭐\nSaatleri değiştirmek için panelde Takvim: /panel", metin)
        # yeniden hesapla: yalnız en iyi saatlere
        self.req.cagrilar.clear()
        self.tb.duzelt(Z, "yeniden")
        v = self.vid(Z)
        self.assertEqual(v["schedule"]["instagram"], "2026-11-05T09:30:00+00:00")
        for p in ("youtube", "tiktok"):
            self.assertTrue(self.tb._is_prime(p, v["schedule"][p]), v["schedule"])



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

    def test_rapor_tablosu(self):
        import html as H
        import shortgen.stats as st
        snap = json.loads((FIX / "state" / "stats.json").read_text(encoding="utf-8"))
        snap["time"] = "2026-11-05T07:19+03:00"
        snap["titles"] = {t: "Uzun <b>başlık</b> & 🎬 emoji " * 3 for t in snap.get("titles", {})} or snap.get("titles")
        prev = json.loads(json.dumps(snap))
        prev["time"] = "2026-11-04T21:00+03:00"
        for d in prev["platforms"].values():
            for k, v in list((d.get("account") or {}).items()):
                if k == "views" and isinstance(v, int):
                    d["account"][k] = v - 10
        txt = st.render(snap, prev)
        self.assertTrue(txt.startswith("📊 <b>Bilgi Makası raporu</b> · 5 Kas 07:19"))
        bloklar = re.findall(r"<pre>(.*?)</pre>", txt, re.S)
        self.assertGreaterEqual(len(bloklar), 1)
        for b in bloklar:  # telefonda kaymasın: her satır W karakteri geçmez, tablo içinde emoji yok
            gorunen = H.unescape(b)
            self.assertLessEqual(max(len(x) for x in gorunen.split("\n")), st.W, gorunen)
            self.assertNotIn("🎬", gorunen)
            self.assertNotIn("<b>", b)  # başlıktaki etiket kaçışlı
        n = sum(1 for d in snap["platforms"].values() if isinstance((d.get("account") or {}).get("views"), int))
        self.assertIn(f"(toplam +{10 * n} izlenme)", txt)
        self.assertRegex(H.unescape(txt), r"\nİzlenme +\+10 +\+10 +\+10(\n|</pre>)")  # platform platform değişim
        # büyük sayılar: tablo yine W'yi geçmez (sayılar kısalır, video adı daralır)
        buyuk = json.loads(json.dumps(snap))
        for d in buyuk["platforms"].values():
            if isinstance((d.get("account") or {}).get("views"), int):
                d["account"]["views"] = 12345678
            for v in (d.get("videos") or {}).values():
                v.update(views=1234567, likes=123456)
        t2 = st.render(buyuk, prev)
        for b in re.findall(r"<pre>(.*?)</pre>", t2, re.S):
            self.assertLessEqual(max(len(x) for x in H.unescape(b).split("\n")), st.W, H.unescape(b))
        self.assertIn("12Mn", t2)
        # bir platformda düşüş, ötekinde artış birbirini götürmez
        az = json.loads(json.dumps(prev))
        p1, p2 = [k for k, d in snap["platforms"].items() if isinstance((d.get("account") or {}).get("followers"), int)][:2]
        az["platforms"][p1]["account"]["followers"] += 3
        az["platforms"][p2]["account"]["followers"] -= 3
        satir = [x for x in H.unescape(st.render(snap, az)).split("\n") if x.startswith("Takipçi") and ("−3" in x)]
        self.assertTrue(satir and "+3" in satir[0], satir)
        # ayrışık (NFD) Türkçe ad sütunları kaydırmaz
        import unicodedata
        self.assertEqual(st._plain(unicodedata.normalize("NFD", "Şişli İğneada")), "Şişli İğneada")
        # önceki ölçüm yoksa değişim satırı yok; hatalı platform tabloya girmez, notta görünür
        snap["platforms"]["youtube"] = {"error": "bağlı değil"}
        txt = st.render(snap, None)
        self.assertNotIn("Son rapordan", txt)
        self.assertIn("⚠️ YouTube: bağlı değil", txt)
        self.assertNotIn("YouTube", re.findall(r"<pre>(.*?)</pre>", txt, re.S)[0])
        # azalma eksi ile yazılır; düz yazı hâli etiketsiz
        prev["platforms"]["instagram"]["account"]["followers"] = snap["platforms"]["instagram"]["account"]["followers"] + 2
        self.assertRegex(st.render(snap, prev), r"\nTakipçi +−2 ")
        self.assertNotIn("<", st.plain(st.render(snap, prev)).replace("Uzun <b>", ""))

    def test_rapor_html_reddedilirse_duz_metin_gider(self):
        import shortgen.stats as st
        snap = json.loads((FIX / "state" / "stats.json").read_text(encoding="utf-8"))
        eski_collect = st.collect
        self.addCleanup(setattr, st, "collect", eski_collect)
        st.collect = lambda: json.loads(json.dumps(snap))
        giden = []

        def api(method, data=None, **kw):
            giden.append(data)
            if data.get("parse_mode"):
                raise RuntimeError("Telegram sendMessage hatası 400: can't parse entities")
        eski = self.tb.api
        self.tb.api = api
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                st.report()
        finally:
            self.tb.api = eski
        self.assertEqual(len(giden), 2)
        self.assertNotIn("parse_mode", giden[1])
        self.assertNotIn("<pre>", giden[1]["text"])
        self.assertTrue(giden[1]["text"].startswith("📊 Bilgi Makası raporu"))

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

        def generate_script(history, topic=None, templates=None, series_prev=None, allow_series=False, kart=False,
                            structure=None, adim_kartlari=False, sablon_kurali=""):
            cagri.update(topic=topic, kart=kart, structure=structure, allow_series=allow_series)
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
        acik = bool(json.loads((REPO / "templates" / "eslesme.json").read_text(encoding="utf-8"))["kart"]["acik"])
        self.assertEqual(cagri["kart"], acik, "kart yönergesi yalnız kart açıkken (eslesme.json) istenir")
        self.assertEqual(self.kuyruk(), ilk[1:])
        self.assertIn("Konu sırasından alınan konu: " + ilk[0], out)
        self.assertIn("Konu sırasından çıkarıldı: " + ilk[0], out)

    def test_siradaki_konunun_serisi_tahmin_edilir(self):
        f = self.root / "state" / "konu_sirasi.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d["konular"] = ["Kuyumcu olsaydın", "genel: Piyango sana çıksaydı"]
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        cagri, out = self._main([])
        self.assertEqual((cagri["topic"], cagri["structure"]), ("Kuyumcu olsaydın", "olsaydin"))
        self.assertIn("Sabit anlatım kalıbı: olsaydin", out)
        cagri, _ = self._main([])
        self.assertEqual((cagri["topic"], cagri["structure"]), ("Piyango sana çıksaydı", None))
        self.assertEqual(self.kuyruk(), [], "önekli konu da sıradan çıkar")

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
        cagri, _ = self._main([], oneri=lambda **kw: [s0])
        self.assertEqual(cagri["topic"], "Gündem konusu (kanca: kanca; gündem: gündem)")

    def test_uret_yml_durumu_kaydeder(self):
        y = (REPO / ".github" / "workflows" / "uret.yml").read_text(encoding="utf-8")
        uret = y.index("python -m shortgen.pipeline")
        self.assertIn("python -m shortgen.state_sync", y[uret:y.index("Hata olursa")], "başarılı üretimde kayıt")
        self.assertIn("python -m shortgen.state_sync", y[y.index("Hata olursa"):], "hatada da kayıt")
        import shortgen.state_sync as ss
        self.assertIn("state", ss.PATHS)

    def test_sabit_kalip_uretime_gecer(self):
        cagri, out = self._main(["--topic", "muz", "--structure", "nasil"])
        self.assertEqual((cagri["topic"], cagri["structure"]), ("muz", "nasil"))
        self.assertFalse(cagri["allow_series"], "seri formatı videoları iki bölüme ayrılmaz")
        self.assertTrue(cagri["kart"], "nasil yapi_sablon ile karta gittiği için kart yönergesi istenir")
        self.assertIn("Sabit anlatım kalıbı: nasil", out)
        cagri, _ = self._main(["--topic", "muz"])
        self.assertIsNone(cagri["structure"])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self._main(["--topic", "muz", "--structure", "x; rm -rf /"])  # geçersiz kalıp argparse'ta durur

    def test_otomatik_uretim_nasil_serisini_secmez(self):
        import shortgen.trends as tr
        (self.root / "state" / "konu_sirasi.json").unlink()
        ortak = dict(hook="kanca", trend="neden", scope="TR", category="bilim")
        oneriler = [tr.Suggestion(topic="Nasıl konusu", score=10, seri="nasil", **ortak),
                    tr.Suggestion(topic="Efsane konusu", score=9, seri="efsane", **ortak),
                    tr.Suggestion(topic="Popüler konu", score=8, seri="populer", **ortak)]
        istek = []

        def oneri(**kw):
            istek.append(kw)
            return tr.sirala(oneriler)
        h = self.root / "history.jsonl"
        cagri, _ = self._main([], oneri=oneri)
        # nasil en yüksek puanlı olsa da seçilmez; otomatik üretim sahibin öneri listesini değiştirmez
        self.assertEqual(istek, [{"kaydet": False, "seriler": tr.OTOMATIK_SERILER}])
        self.assertEqual(cagri["topic"], "Efsane konusu (kanca: kanca; neden ilgi çeker: neden)")
        self.assertEqual(cagri["structure"], "efsane", "efsane önerisi efsane kalıbıyla üretilir")
        self.assertFalse(cagri["allow_series"])
        # son video efsane kalıbındaysa Efsane önerisi seçilmez (kalıp dönüşümü)
        h.write_text(json.dumps({"topic": "önceki", "structure": "efsane"}) + "\n", encoding="utf-8")
        cagri, _ = self._main([], oneri=oneri)
        self.assertEqual((cagri["topic"], cagri["structure"]), ("Popüler konu (kanca: kanca; gündem: neden)", None))
        h.write_text("", encoding="utf-8")
        oneriler[1].score = 8  # eşitlikte seri sırası: Popüler önce
        cagri, _ = self._main([], oneri=oneri)
        self.assertEqual((cagri["topic"], cagri["structure"]), ("Popüler konu (kanca: kanca; gündem: neden)", None))


class OneriSerileri(Ortak):
    SERILI = json.loads((FIX / "oneriler_seriler.json").read_text(encoding="utf-8"))["items"]

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # geçici kökten yüklenen paket silinen klasörü gösterir: sonraki sınıflar depodaki paketi yüklesin
        for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
            del sys.modules[ad]

    def setUp(self):
        super().setUp()
        import shortgen.trends as tr
        self.tr = tr
        tr.load_saved = lambda: [dict(x) for x in self.SERILI]
        self.addCleanup(setattr, tr, "load_saved", lambda: [dict(x) for x in ONERILER])

    def uzunluk16(self, t):
        return len(t.encode("utf-16-le")) // 2

    BASLIKLAR = (["🔥 Popüler", "📚 Konular", "🧐 Efsane mi, gerçek mi?"],
                 ["🛠 Nasıl yapılır?", "🏭 Nasıl üretiliyor?", "💭 Ya sen olsaydın?"],
                 ["📖 Bir Kitap Bir Dakika"])

    def test_telegram_mesaji_seri_seri_ve_kesintisiz_numara(self):
        msjlar = self.tr.mesajlar(self.SERILI)
        self.assertEqual(len(msjlar), 3, "21 öneri: üçer serilik mesajlar, Bir Kitap Bir Dakika üçüncü mesajda")
        d = self.tr.damga(self.SERILI)
        self.assertRegex(d, r"^[0-9a-f]{8}$")
        for k, ((metin, rows), basliklar) in enumerate(zip(msjlar, self.BASLIKLAR)):
            self.assertTrue(metin.startswith(f"🗂 Bugünün konu önerileri ({k + 1}/3)\n\n" + basliklar[0] + "\n"))
            konum = [metin.index("\n" + b + "\n") for b in basliklar]
            self.assertEqual(konum, sorted(konum))
            numaralar = [int(x) for x in re.findall(r"^(\d+)\. ", metin, re.M)]
            self.assertEqual(numaralar, list(range(9 * k + 1, 9 * k + 1 + 3 * len(basliklar))),
                             "numaralar mesajlar boyunca kesintisiz")
            # her numara kendi serisinin başlığı altında
            for j, b in enumerate(basliklar):
                ilk = metin.index(f"\n{9 * k + 3 * j + 1}. ")
                self.assertLess(konum[j], ilk, b)
                if j + 1 < len(basliklar):
                    self.assertLess(metin.index(f"\n{9 * k + 3 * j + 3}. "), konum[j + 1], b)
            # düğmeler kayıttaki sırayı gösterir: tp:<damga>:<sıra>
            self.assertEqual(rows, [[(f"🎬 {i}", f"tp:{d}:{i - 1}") for i in range(n, n + 3)]
                                    for n in range(9 * k + 1, 9 * k + 1 + 3 * len(basliklar), 3)])
            self.assertLessEqual(self.uzunluk16(metin), 4096)
            self.assertTrue(metin.endswith("Üretmek istediğin konunun numarasına bas."))
        self.assertLessEqual(max(len(c.encode()) for _, r in msjlar for row in r for _, c in row), 64,
                             "Telegram callback_data sınırı")
        for i, it in enumerate(self.SERILI):  # her düğme kendi önerisinin konusunu taşıyan satırda
            metin = msjlar[i // 9][0]
            self.assertIn(f"\n{i + 1}. ", metin)
            self.assertIn(it["topic"][:40], metin.split(f"\n{i + 1}. ", 1)[1].split("\n", 1)[0])
        self.assertIn("📈 Milli takımın", msjlar[0][0])  # Popüler'in gerekçesi gündem
        self.assertIn("💡 Etilen gazını", msjlar[1][0])
        self.assertIn("💡 Altın fiyatları", msjlar[1][0])
        self.assertIn("💡 Yeni sinema uyarlamasıyla", msjlar[2][0])

    def test_uzun_oneriler_sinira_zarifce_sigar(self):
        uzun = [{**it, "topic": it["topic"] + " ayrıntı" * 80, "hook": it["hook"] + " 😀" * 40,
                 "trend": it["trend"] + " gündem" * 40} for it in self.SERILI]
        for items in (uzun, [{**it, "topic": "çok " * 2000} for it in uzun]):
            msjlar = self.tr.mesajlar(items)
            for metin, _ in msjlar:
                self.assertLessEqual(self.uzunluk16(metin), 4096)
                self.assertTrue(metin.endswith("numarasına bas."), "kısaltma kelime ortasında kesmez, son satır kalır")
            self.assertEqual([int(x) for m, _ in msjlar for x in re.findall(r"^(\d+)\. ", m, re.M)], list(range(1, 22)))
            self.assertEqual(sum(len(r) for _, rows in msjlar for r in rows), 21)
        self.assertIn("…", msjlar[0][0])

    def test_eski_oneriler_populer_sayilir(self):
        msjlar = self.tr.mesajlar(ONERILER)
        self.assertEqual(len(msjlar), 1, "tek gruplu liste tek mesaj")
        metin, rows = msjlar[0]
        self.assertTrue(metin.startswith("🗂 Bugünün konu önerileri\n"), "tek mesajda (1/1) yazılmaz")
        self.assertIn("\n🔥 Popüler\n", metin)
        self.assertNotIn("Konular", metin)
        d = self.tr.damga(ONERILER)
        self.assertEqual(rows, [[("🎬 1", f"tp:{d}:0"), ("🎬 2", f"tp:{d}:1"), ("🎬 3", f"tp:{d}:2")]])
        self.assertEqual({self.tr.seri_of(x) for x in ONERILER}, {"populer"})
        self.assertEqual(self.tr.seri_of({"seri": "bilinmeyen"}), "populer")
        self.assertEqual({self.tr.kalip_of(x) for x in ONERILER}, {""})
        # sıralama: seri sırası, seri içinde puan; eski öğeler Popüler'e katılır
        karisik = [self.SERILI[20], self.SERILI[16], self.SERILI[9], self.SERILI[3], ONERILER[2], self.SERILI[0],
                   self.SERILI[13], self.SERILI[6]]
        self.assertEqual([self.tr.seri_of(x) for x in self.tr.sirala(karisik)],
                         ["populer", "populer", "konu", "efsane", "nasil", "uretim", "olsaydin", "kitap"])
        self.assertEqual(self.tr.sirala(karisik)[0]["score"], 9)
        # eski 12 önerilik liste (dört seri): Nasıl yapılır? ikinci mesajda, numarası 10'dan sürer
        eski = self.tr.mesajlar(self.SERILI[:12])
        self.assertEqual([len(r) for _, r in eski], [3, 1])
        self.assertTrue(eski[1][0].startswith("🗂 Bugünün konu önerileri (2/2)\n\n🛠 Nasıl yapılır?\n10. "))
        # eski 18 önerilik liste (altı seri): iki mesaj, üçüncü mesaj yok
        alti = self.tr.mesajlar(self.SERILI[:18])
        self.assertEqual([len(r) for _, r in alti], [3, 3])
        self.assertTrue(alti[1][0].startswith("🗂 Bugünün konu önerileri (2/2)\n\n🛠 Nasıl yapılır?\n10. "))

    def test_notify_seri_mesajlari_ve_klavye(self):
        oneriler = [self.tr.Suggestion(**x) for x in reversed(self.SERILI)]
        eski, self.tr.suggest = self.tr.suggest, lambda: self.tr.sirala(oneriler)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.tr.notify()
        finally:
            self.tr.suggest = eski
        g = self.tg(self.req.cagrilar, "sendMessage")
        self.assertEqual(len(g), 3, "üçer serilik mesajlar: 3 + 3 + 1 seri")
        d = self.tr.damga([x.model_dump() for x in self.tr.sirala(oneriler)])  # damga kayıttaki sıradan
        for k, m in enumerate(g):
            kb = m["data"]["reply_markup"]["inline_keyboard"]
            self.assertEqual([[b["callback_data"] for b in r] for r in kb],
                             [[f"tp:{d}:{i}" for i in range(n, n + 3)] for n in range(9 * k, min(9 * k + 9, 21), 3)])
            self.assertLessEqual(self.uzunluk16(m["data"]["text"]), 4096)
        self.assertTrue(g[0]["data"]["text"].startswith("🗂 Bugünün konu önerileri (1/3)\n\n🔥 Popüler\n1. 🇹🇷 1954"))
        self.assertTrue(g[1]["data"]["text"].startswith("🗂 Bugünün konu önerileri (2/3)\n\n🛠 Nasıl yapılır?\n10. "))
        self.assertIn("\n💭 Ya sen olsaydın?\n16. 🇹🇷 Kuyumcu olsaydın", g[1]["data"]["text"])
        self.assertTrue(g[2]["data"]["text"].startswith("🗂 Bugünün konu önerileri (3/3)\n\n📖 Bir Kitap Bir Dakika\n"
                                                        "19. 🇹🇷 Sabahattin Ali, Kürk Mantolu Madonna"))

    def test_otomatik_oneri_kaydedilmez_ve_nasil_istenmez(self):
        tr = self.tr
        once = tr.STATE.read_text(encoding="utf-8")
        ortak = dict(hook="kanca", trend="neden", scope="TR", category="bilim")
        istekler = []

        def ask(prompt, schema, system, web=False):
            istekler.append(prompt)
            return tr.Suggestions(items=[tr.Suggestion(topic=f"{s} konusu", score=5, seri=s, **ortak) for s in tr.SERILER])
        eski, tr.ask_claude = tr.ask_claude, ask
        try:
            items = tr.suggest(kaydet=False, seriler=tr.OTOMATIK_SERILER)
            self.assertEqual(tr.STATE.read_text(encoding="utf-8"), once, "otomatik üretim listeyi değiştirmez")
            self.assertEqual([tr.seri_of(x) for x in items], ["populer", "konu", "efsane"])
            self.assertIn("(toplam 9): populer, konu, efsane.", istekler[0])
            tr.suggest()  # /oneri: yedi seri istenir ve liste kaydedilir
            self.assertIn("(toplam 21): populer, konu, efsane, nasil, uretim, olsaydin, kitap.", istekler[1])
            self.assertEqual(len(json.loads(tr.STATE.read_text(encoding="utf-8"))["items"]), 7)
            # otomatik üretim (best) yalnız OTOMATIK_SERILER'i ister; nasil, uretim, olsaydin, kitap hiç seçilmez
            self.assertEqual(tr.OTOMATIK_SERILER, ("populer", "konu", "efsane"))
            istekler.clear()

            def ask_hepsi(prompt, schema, system, web=False):  # yanıt istenmeyen serilerde çok yüksek puan taşısa da
                istekler.append(prompt)
                return tr.Suggestions(items=[tr.Suggestion(topic=f"{s} konusu", score=10 if s in ("nasil", "uretim",
                                             "olsaydin", "kitap") else 5, seri=s, **ortak) for s in tr.SERILER])
            tr.ask_claude = ask_hepsi
            secilen = tr.best()
            self.assertIn(tr.seri_of(secilen), tr.OTOMATIK_SERILER)
            self.assertNotIn("uretim", istekler[0])
            self.assertNotIn("olsaydin", istekler[0])
            self.assertNotIn("kitap", istekler[0])
        finally:
            tr.ask_claude = eski

    def test_eski_mesajdaki_dugme_yeni_listeden_uretmez(self):
        d = self.tr.damga(self.SERILI)
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.process_update(cq(f"tp:{d}:9"), CHAT)  # damga tutuyor: üretim başlar
        self.assertEqual([x["json"]["inputs"].get("kalip") for x in self.req.cagrilar if "gh" in x], ["nasil"])
        self.req.cagrilar.clear()
        yeni = [dict(x) for x in self.SERILI]
        yeni[9]["topic"] = "Liste yenilendi: başka bir konu"
        self.tr.load_saved = lambda: [dict(x) for x in yeni]
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.process_update(cq(f"tp:{d}:9"), CHAT)  # eski mesajın düğmesi
        self.assertFalse([x for x in self.req.cagrilar if "gh" in x], "eski listenin düğmesi başka konuyu üretmez")
        m = self.mesajlar(self.req.cagrilar)
        self.assertEqual(len(m), 1, "uyarı tek mesaj")
        self.assertIn("öneri listesi kayıtlı listeyle aynı değil", m[0])
        self.req.cagrilar.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.process_update(cq("tp:_:9"), CHAT)  # damgasız eski düğmeler önceki gibi çalışır
        self.assertEqual(len([x for x in self.req.cagrilar if "gh" in x]), 1)

    def test_seriden_uretim_kalibi_sabitler(self):
        beklenen = {0: None, 3: None, 6: "efsane", 9: "nasil", 12: "uretim", 15: "olsaydin", 17: "olsaydin", 18: "kitap",
                    20: "kitap"}
        for i, kalip in beklenen.items():
            self.req.cagrilar.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                self.tb.process_update(cq(f"tp:_:{i}"), CHAT)
            gh = [x["json"]["inputs"] for x in self.req.cagrilar if "gh" in x]
            it = self.SERILI[i]
            etiket = "gündem" if i == 0 else "neden ilgi çeker"
            girdi = {"topic": f"{it['topic']} (kanca: {it['hook']}; {etiket}: {it['trend']})"}
            self.assertEqual(gh, [{**girdi, **({"kalip": kalip} if kalip else {})}], i)
            # panelden aynı öneri aynı girdiyle
            c = self.panel(action="produce_suggestion", index=i, topic=it["topic"])
            self.assertEqual([x["json"]["inputs"] for x in c if "gh" in x][-1], gh[0], i)

    def test_gecersiz_kalip_gonderilmez(self):
        with self.assertRaises(ValueError):
            self.tb._dispatch("konu", kalip="nasil; rm -rf /")
        self.assertFalse([x for x in self.req.cagrilar if "gh" in x])
        # kayıtta bozuk seri: Popüler sayılır, kalıp gönderilmez
        self.tr.load_saved = lambda: [{**self.SERILI[9], "seri": "$(id)"}]
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.process_update(cq("tp:_:0"), CHAT)
        self.assertNotIn("kalip", [x for x in self.req.cagrilar if "gh" in x][0]["json"]["inputs"])

    def test_uret_yml_kalip_ortamdan_gecer(self):
        y = (REPO / ".github" / "workflows" / "uret.yml").read_text(encoding="utf-8")
        self.assertRegex(y, r"\n      kalip:\n        description: .+\n        required: false\n")
        self.assertIn("KALIP: ${{ github.event.inputs.kalip }}", y)
        self.assertEqual(y.count("inputs.kalip"), 1, "kalıp betiğin içine doğrudan yazılmaz")
        self.assertIn('[ -n "$KALIP" ] && ARGS+=(--structure "$KALIP")', y)
        aciklama = re.search(r"\n      kalip:\n        description: (.+)\n", y).group(1)
        for k in ("efsane", "nasil", "uretim", "olsaydin", "kitap"):
            self.assertIn(k, aciklama)
        for k in ("uretim", "kitap"):
            self.assertIn(k, re.search(r"\n      template:\n        description: (.+)\n", y).group(1))

    def test_nasil_dusumde_yok_ve_sabit_kalip_korunur(self):
        import shortgen.script as sc
        h = self.root / "history.jsonl"
        self.assertEqual(sc.FORCED_ONLY, {"nasil", "uretim", "olsaydin", "kitap"})
        for son in ([], ["hikaye", "hikaye", "efsane"], ["nasil"], ["efsane", "neden", "sayac"], ["uretim"],
                    ["olsaydin", "uretim", "nasil"], ["kitap"], ["kitap", "hikaye", "kitap"]):
            h.write_text("".join(json.dumps({"topic": f"t{i}", "structure": k}) + "\n" for i, k in enumerate(son)),
                         encoding="utf-8")
            for k in sc.FORCED_ONLY:
                self.assertNotIn(k, sc.allowed_structures(h), son)
            self.assertTrue(sc.allowed_structures(h), son)
        h.write_text("", encoding="utf-8")
        self.assertEqual(sc.STRUCTURES["nasil"][0], "NASIL YAPILIR?")
        self.assertEqual(sc.STRUCTURES["uretim"][0], "NASIL ÜRETİLİYOR?")
        self.assertEqual(list(sc.STRUCTURES)[-3:], ["uretim", "olsaydin", "kitap"])
        self.assertEqual(sc.STRUCTURES["kitap"][0], "BİR KİTAP BİR DAKİKA")
        self.assertLessEqual(set(self.tr.SERI_KALIP.values()), set(sc.STRUCTURES), "seri kalıpları geçerli kalıp")
        demo = sc.load_script(self.root / "demo" / "demo_script.json")
        istekler = []

        def ask(prompt, schema, system, web=False):  # her geçiş kalıbı değiştirmeye çalışır
            istekler.append(prompt)
            if schema is sc.ShortScript:
                return demo.model_copy(update={"structure": "hikaye"}, deep=True)
            if schema is sc.Review:
                return sc.Review(ok=True, problems=[], fixed=demo.model_copy(update={"structure": "neden"}, deep=True))
            return sc.Polished(notes=[], fixed=demo.model_copy(update={"structure": "sayac"}, deep=True))
        eski, sc.ask_claude = sc.ask_claude, ask
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                out = sc.generate_script(h, "muz", structure="nasil")
                serbest = sc.generate_script(h, "muz")
                with self.assertRaises(ValueError):
                    sc.generate_script(h, "muz", structure="yok")
        finally:
            sc.ask_claude = eski
        self.assertEqual(out.structure, "nasil")
        self.assertIn("ANLATIM KALIBI (SABİT)", istekler[0])
        self.assertIn("- nasil: NASIL YAPILIR:", istekler[0])
        self.assertNotIn("- hikaye:", istekler[0])
        self.assertIn("SABİT", istekler[1])
        self.assertEqual(serbest.structure, "neden", "serbest kalıpta doğrulayıcının kalıbı geçerli")
        for k in sc.FORCED_ONLY:  # dönüşümden (serbest kalıp) yazılan senaryoya seri kalıpları sunulmaz
            self.assertNotIn(f"- {k}:", istekler[3])
        self.assertIn("- hikaye:", istekler[3])

    def test_serbest_kalipta_nasil_secilemez(self):
        import shortgen.script as sc
        h = self.root / "history.jsonl"
        h.write_text(json.dumps({"topic": "t", "structure": "hikaye"}) + "\n", encoding="utf-8")
        self.assertIn("nasil", sc.ShortScript.model_json_schema()["properties"]["structure"]["enum"], "şema izin verir")
        demo = sc.load_script(self.root / "demo" / "demo_script.json")
        uretici, istekler = [], []

        def ask(prompt, schema, system, web=False):  # sunulmadığı hâlde üretici ya da doğrulayıcı nasil'i seçer
            istekler.append(prompt)
            if schema is sc.ShortScript:
                return demo.model_copy(update={"structure": uretici[0]}, deep=True)
            if schema is sc.Review:
                return sc.Review(ok=True, problems=[], fixed=demo.model_copy(update={"structure": "nasil"}, deep=True))
            return sc.Polished(notes=[], fixed=demo.model_copy(update={"structure": "nasil"}, deep=True))
        eski, sc.ask_claude = sc.ask_claude, ask
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                uretici[:] = ["nasil"]
                ikisi = sc.generate_script(h, "Muzlar neden kararır")
                uretici[:] = ["neden"]
                yalniz_dogrulayici = sc.generate_script(h, "Muzlar neden kararır")
        finally:
            sc.ask_claude = eski
        self.assertEqual(ikisi.structure, sc.allowed_structures(h)[0], "dönüşümdeki ilk kalıba döner")
        self.assertNotEqual(ikisi.structure, "nasil")
        self.assertIn(f'"structure": "{ikisi.structure}"', istekler[1], "doğrulayıcıya nasil gitmez")
        self.assertIn("'nasil', 'uretim', 'olsaydin', 'kitap' kalıplarına geçme", istekler[1])
        self.assertEqual(yalniz_dogrulayici.structure, "neden", "doğrulayıcı nasil'e geçemez: üreticinin kalıbı kalır")

    def test_serbest_kalipta_uretim_ve_olsaydin_secilemez(self):
        """Otomatik üretim (serbest kalıp): üretici ve doğrulayıcı uretim, olsaydin ya da kitap seçse de dönüşümdeki
        kalıp kullanılır; bu kalıpların yönergesi ve web araması istenmez."""
        import shortgen.script as sc
        h = self.root / "history.jsonl"
        h.write_text(json.dumps({"topic": "t", "structure": "hikaye"}) + "\n", encoding="utf-8")
        demo = sc.load_script(self.root / "demo" / "demo_script.json")
        for k in ("uretim", "olsaydin", "kitap"):
            cagri = []

            def ask(prompt, schema, system, web=False, k=k):
                cagri.append((schema.__name__, system, web))
                s = demo.model_copy(update={"structure": k}, deep=True)
                if schema is sc.ShortScript:
                    return s
                if schema is sc.Review:
                    return sc.Review(ok=True, problems=[], fixed=s)
                return sc.Polished(notes=[], fixed=s)
            eski, sc.ask_claude = sc.ask_claude, ask
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    out = sc.generate_script(h, "Muzlar neden kararır", kart=True, adim_kartlari=True)
            finally:
                sc.ask_claude = eski
            self.assertEqual(out.structure, sc.allowed_structures(h)[0], k)
            self.assertEqual([(c[0], c[2]) for c in cagri], [("ShortScript", False), ("Review", True), ("Polished", False)])
            for _, system, _ in cagri:
                for kural in (sc.URETIM_RULES, sc.OLSAYDIN_RULES, sc.EDITOR_URETIM, sc.EDITOR_OLSAYDIN, sc.KITAP_RULES,
                              sc.EDITOR_KITAP):
                    self.assertNotIn(kural, system, k)

    def test_nasil_guvenlik_sinirlari(self):
        import shortgen.script as sc
        for alan in ("ya da kimyasalları (çamaşır suyu, tuz ruhu, kireç çözücü, amonyak) birbiriyle ya da herhangi bir "
                     "şeyle (sirke ve limon dahil) karıştırma", "gıda güvenliği", "kızgın yağ", "evcil hayvan",
                     "konumunu, mesajlarını", "güvenlik önlemlerini aşma", "ilaç", "elektrik tesisatı (priz, sigorta, "
                     "kablo bağlama)", "gaz tesisatı", "yüksekte çalışma", "ağır elektrikli aletler (taşlama, motorlu "
                     "testere)", "son kullanma tarihi", "alkollü içecek tarifi"):
            self.assertIn(alan, sc.NASIL_YASAK)
        # izin verilenler: tek başına tek ürün ya da mutfak malzemesi, olağan pişirme ve kızartma
        for serbest in ("tek bir ürünü etiketindeki talimatla tek başına kullanmak ya da sirke, karbonat, limon gibi "
                        "mutfak malzemeleriyle temizlik serbest", "olağan pişirme, olağan kızartma ve su kaynatma hariç"):
            self.assertIn(serbest, sc.NASIL_YASAK)
        self.assertIn(sc.NASIL_GUVENLIK, sc.STRUCTURES["nasil"][1], "alet işinde güvenlik notu")
        self.assertIn(sc.NASIL_GUVENLIK, sc.NASIL_RULES)
        self.assertIn("koruyucu gözlük", sc.NASIL_GUVENLIK)
        self.assertIn("kablo ve boru kontrolü", sc.NASIL_GUVENLIK)
        # kart şablonu (nasil'in şimdiki yolu) callout çizmez: not dış seste söylenmeli
        self.assertIn("bir adımın dış sesinde (narration) söylensin", sc.NASIL_GUVENLIK)
        self.assertIn("yalnız callout'ta kalmasın", sc.NASIL_GUVENLIK)
        self.assertNotIn("bir adımda ya da callout'ta", sc.NASIL_GUVENLIK)
        self.assertIn(sc.NASIL_YASAK, sc.STRUCTURES["nasil"][1], "senaryo yönergesi")
        self.assertIn(sc.NASIL_YASAK, self.tr.SYSTEM, "öneri yönergesi")
        demo = sc.load_script(self.root / "demo" / "demo_script.json")
        istekler = []

        def ask(prompt, schema, system, web=False):
            istekler.append(prompt)
            return sc.Review(ok=True, problems=[], fixed=demo)
        eski, sc.ask_claude = sc.ask_claude, ask
        try:
            sc.verify_script(demo.model_copy(update={"structure": "nasil"}), keep_structure=True)
            sc.verify_script(demo.model_copy(update={"structure": "efsane"}))
        finally:
            sc.ask_claude = eski
        self.assertIn("Güvenli olmayan ya da şu alanlara giren adımı çıkar veya güvenli bir adımla değiştir: "
                      + sc.NASIL_YASAK, istekler[0])
        self.assertNotIn("Güvenli olmayan", istekler[1], "diğer kalıpların doğrulama yönergesi değişmez")
        self.assertIn("güvenlik notu", istekler[0])
        self.assertIn("dış sesinde (narration) yoksa ekle (yalnız callout'ta olması yetmez", istekler[0])
        # alanlar: öneri yönergesi altı alanı numaralı sayar, her öneri farklı alandan
        for alan in ("ev işleri ve temizlik", "matkapla dübel takma", "Türk mutfağı", "alkolsüz kokteyl", "yurt ya da küçük "
                     "oda düzeni", "ev hanımları için pratikler: çamaşır, ütü, leke çıkarma"):
            self.assertIn(alan, self.tr.SYSTEM)
        self.assertIn("3 önerinin her biri farklı bir alandan", self.tr.SYSTEM)
        self.assertIn("(6) evi çekip çevirenler", self.tr.SYSTEM)

    def test_yapi_sablon_ve_seri_etiketi(self):
        import shortgen.pipeline as pl
        import shortgen.script as sc
        m = json.loads((REPO / "templates" / "eslesme.json").read_text(encoding="utf-8"))
        self.assertEqual(m["yapi_sablon"]["nasil"], "nasil")
        self.assertEqual((m["yapi_sablon"]["uretim"], m["yapi_sablon"]["olsaydin"]), ("isemri", "ajanda"))
        self.assertEqual(m["yapi_sablon"]["kitap"], "kitap")
        self.assertTrue(m["yapi_sablon"]["_aciklama"])
        demo = sc.load_script(self.root / "demo" / "demo_script.json")
        nasil = demo.model_copy(update={"structure": "nasil", "category": "uzay"})
        self.assertEqual(pl.pick_template(nasil), "nasil", "yapı eşleşmesi kategori eşleşmesinden önce")
        self.assertEqual(pl.pick_template(nasil, "kolaj"), "kolaj", "elle seçilen şablon kazanır")
        self.assertEqual(pl.pick_template(demo.model_copy(update={"structure": "hikaye", "category": "uzay"})), "gece")
        self.assertEqual(pl.series_label(nasil, self.root / "history.jsonl"), "NASIL YAPILIR? #1")
        olsaydin = demo.model_copy(update={"structure": "olsaydin", "category": "uzay"})
        self.assertEqual(pl.pick_template(olsaydin), "ajanda", "olsaydin Ajanda şablonunda")
        self.assertEqual(pl.series_label(olsaydin, self.root / "history.jsonl"),
                         sc.STRUCTURES["olsaydin"][0] + " #1")
        uretim = demo.model_copy(update={"structure": "uretim", "category": "uzay"})
        self.assertEqual(pl.series_label(uretim, self.root / "history.jsonl"), "NASIL ÜRETİLİYOR? #1")

    def test_nasil_yapilir_etiketi(self):
        import shortgen.publish as P
        meta = {"structure": "nasil", "hashtags": ["muznasilsaklanir", "muz", "mutfak", "etilen", "bilgimakasi"],
                "description": "Bilgi.\n\n#muznasilsaklanir #muz #mutfak #etilen #bilgimakasi\n\n📷 John Doe (CC BY-SA 4.0)"}
        m = P.apply_series_tag(meta)
        self.assertEqual(m["hashtags"], ["muznasilsaklanir", "muz", "mutfak", "NasılYapılır", "bilgimakasi"])
        self.assertEqual(m["description"], "Bilgi.\n\n#muznasilsaklanir #muz #mutfak #NasılYapılır #bilgimakasi"
                                           "\n\n📷 John Doe (CC BY-SA 4.0)")
        self.assertEqual(P.apply_series_tag(m), m)

    def test_kart_basliginda_adim_numarasi(self):
        try:
            import shortgen.kart as k
        except ImportError as e:  # numpy/Pillow yoksa
            self.skipTest(str(e))
        sahne = lambda *hl: types.SimpleNamespace(headline=list(hl), kicker="")  # noqa: E731
        v = types.SimpleNamespace(structure="nasil", n=3, scenes=[sahne("MUZU", "TAZE TUT"), sahne("ADIM 2", "SAPI SAR"),
                                                                   sahne("adım 3")])
        self.assertEqual([k.KartVideo.right_label(v, i) for i in range(3)], ["NASIL?", "ADIM 2", "ADIM 3"])


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

    def test_aciklama_mesaji_numarasi_karar_sayilmaz_ve_kaybolmaz(self):
        b = {"tag": "t", "title": "Eski", "status": "zamanlandi", "publish_at": "P", "platforms": {}}
        d = lambda v: json.dumps([v])  # noqa: E731
        # eski videoda panel düzenlemesi açıklamayı yeni mesajla gönderdi; uzakta aynı anda reddedildi: ret geçerli
        l = {**b, "title": "Yeni", "duzenleme": {"title": "Yeni"}, "aciklama_message_id": 77}
        r = {**b, "status": "reddedildi", "publish_at": None}
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(r), d(l)))[0]
        self.assertEqual(out, {**r, "title": "Yeni", "duzenleme": {"title": "Yeni"}, "aciklama_message_id": 77})
        # paylaşım işi (yerel) kaydı yazarken uzakta açıklama mesajı numarası kaydedildi: numara kalır
        r = {**b, "aciklama_message_id": 77}
        l = {**b, "platforms": {"youtube": {"status": "ok"}}}
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(r), d(l)))[0]
        self.assertEqual(out, {**l, "aciklama_message_id": 77})
        # paylaşım işi eski videonun açıklama mesajını gönderdi; uzakta aynı anda kalanlar iptal edildi: numara kalır
        l = {**b, "platforms": {"tiktok": {"status": "ok", "draft": True}}, "aciklama_message_id": 61}
        r = {**b, "status": "iptal", "publish_at": None}
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(r), d(l)))[0]
        self.assertEqual((out["status"], out["aciklama_message_id"]), ("iptal", 61))
        self.assertEqual(out["platforms"]["tiktok"]["status"], "ok")

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

    def test_takvim_degisikligi_ve_paylasim_birlikte(self):
        d = lambda v: json.dumps([v])  # noqa: E731
        sch = {"youtube": "Y15", "instagram": "I09", "tiktok": "T16"}
        b = {"tag": "t", "status": "zamanlandi", "publish_at": "I09", "schedule": sch, "platforms": {}}
        paylasim = {**b, "publish_at": "Y15", "platforms": {"instagram": {"status": "ok", "url": "u"}}}
        takvim = {**b, "schedule": {**sch, "tiktok": "T19"}}  # panel: yalnız TikTok'un saati
        # paylaşım işi önce kaydetti (uzak), takvim işi sonra (yerel): yeni saat kalır, paylaşılan platform kaybolmaz
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(paylasim), d(takvim)))[0]
        self.assertEqual(out["schedule"], {**sch, "tiktok": "T19"})
        self.assertEqual(out["platforms"], {"instagram": {"status": "ok", "url": "u"}})
        self.assertEqual(out["status"], "zamanlandi")
        # tersi: takvim önce (uzak), paylaşım işi sonra (yerel): kullanıcı kararı (saat) geçerli, paylaşım korunur
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(takvim), d(paylasim)))[0]
        self.assertEqual(out["schedule"], {**sch, "tiktok": "T19"})
        self.assertEqual(out["platforms"], {"instagram": {"status": "ok", "url": "u"}})
        # takvim işi paylaşılmış platformun saatini eski kopyadan yazmış olsa bile uzaktaki gerçek saat kalır
        eski = {**b, "schedule": {**sch, "instagram": "I08", "tiktok": "T19"}}
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(paylasim), d(eski)))[0]
        self.assertEqual(out["schedule"]["instagram"], "I09")
        # son platform da paylaşılıp video bittiyse (uzak), takvim işinin bekleyen kalmayan kaydı durumu geri almaz
        bitti = {**b, "status": "yayinlandi", "published": "P", "platforms": {p: {"status": "ok"} for p in sch}}
        out = json.loads(self.ss._merge("state/videos.json", d(b), d(bitti), d(takvim)))[0]
        self.assertEqual((out["status"], out["published"]), ("yayinlandi", "P"))

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

    def test_zamanlayici_kurallari(self):
        # kapının zamanlayıcısı (worker.js) ve dispatch-if-due aynı pencere ve "başlamamış iş" durumlarıyla çalışır
        w = (REPO / "cloudflare" / "worker.js").read_text(encoding="utf-8")
        self.assertEqual(int(re.search(r"const ONCE_MS = (\d+) \* 60e3;", w).group(1)) * 60, self.tb.DUE_WINDOW.total_seconds())
        self.assertEqual(tuple(json.loads(re.search(r"const BASLAMAMIS = (\[.*?\]);", w).group(1))), self.tb.NOT_STARTED)
        self.assertIn("Math.ceil((an - simdi) / 60e3)) + 2)", w)  # dakika = kalan + 2 (telegram_bot._due_inputs)


class NasilSablonu(unittest.TestCase):
    """Nasıl yapılır? şablonu: sahne alanları, şablon seçimi, nasil yönergesi, adım düzeni, sahne planı ve ornek.yml."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO))
        for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
            del sys.modules[ad]
        import shortgen.pipeline as pl
        import shortgen.script as sc
        cls.pl, cls.sc = pl, sc
        cls.cay = sc.load_script(REPO / "demo" / "nasil" / "ornek_cay.json")

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(REPO))
        for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
            del sys.modules[ad]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nasil_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def yama(self, nesne, ad, deger):
        eski = getattr(nesne, ad)
        setattr(nesne, ad, deger)
        self.addCleanup(setattr, nesne, ad, eski)

    def kart_modulu(self):
        try:
            from shortgen import kart, nasil
        except ImportError as e:  # numpy/Pillow/cairosvg yoksa
            self.skipTest(str(e))
        return kart, nasil

    # ------------------------------------------------------------ şema
    def test_sahne_alanlari_varsayilan_ve_eski_senaryolar(self):
        sc = self.sc
        for yol in (REPO / "demo" / "demo_script.json", REPO / "demo" / "kart" / "ornek_cin_seddi.json"):
            s = sc.load_script(yol)
            self.assertTrue(s.scenes)
            self.assertEqual({(x.step, tuple(x.callouts)) for x in s.scenes}, {(0, ())}, yol.name)
        ham = json.loads((REPO / "demo" / "demo_script.json").read_text(encoding="utf-8"))
        ham["scenes"][0]["step"] = -1
        with self.assertRaises(Exception):
            sc.ShortScript.model_validate(ham)
        ozellik = sc.ShortScript.model_json_schema()["$defs"]["Scene"]["properties"]
        self.assertIn("step", ozellik)
        self.assertIn("callouts", ozellik)

    def test_ornek_cay_senaryosu(self):
        s = self.cay
        self.assertEqual((s.structure, s.template), ("nasil", "nasil"))
        self.assertEqual([x.step for x in s.scenes], [0, 1, 2, 3, 4, 0])
        self.assertEqual(len(s.hashtags), 5)
        kelime = sum(len(x.narration.split()) for x in s.scenes)
        self.assertTrue(65 <= kelime <= 78, kelime)
        self.assertTrue(s.scenes[-1].narration.rstrip().endswith("Yorumlara yaz."))
        for x in s.scenes[1:5]:
            self.assertRegex(x.headline[0], r"^ADIM \d$")
            self.assertLessEqual(len(x.callouts), 2)
            self.assertTrue(8 <= len(x.narration.split()) <= 14, x.narration)
            baslik = " ".join(x.headline[1:])
            for c in x.callouts:  # not başlığı tekrarlamaz, en çok 3 kelime / 18 karakter
                self.assertTrue(len(c.split()) <= 3 and len(c) <= 18, c)
                self.assertNotIn(c, baslik)
        # su önce kaynar, demlik o sıcak suyla ısıtılır; özetteki neden ilk adımın püf noktasına bağlanır
        self.assertIn("suyu kaynat", s.scenes[1].narration)
        self.assertIn("demliği bu sıcak suyla", s.scenes[2].narration)
        self.assertTrue(s.scenes[-1].narration.startswith("Uzun kaynayan su"))
        for x in s.scenes[:5]:
            self.assertTrue(x.illustration.startswith("local:demo/nasil/"), x.illustration)
            self.assertTrue((REPO / x.illustration[6:]).is_file(), x.illustration)
        kopya = s.model_copy(deep=True)
        self.assertEqual(self.sc.normalize_nasil(kopya).model_dump(), s.model_dump(), "örnek zaten düzenli")

    # ------------------------------------------------------------ şablon seçimi
    def test_sablon_secimi(self):
        pl = self.pl
        cat = pl.template_catalog()
        self.assertIn("nasil", cat)
        t = json.loads((REPO / "templates" / "nasil.json").read_text(encoding="utf-8"))
        self.assertEqual(t["renderer"], "nasil")
        self.assertEqual(json.loads((REPO / "templates" / "kart.json").read_text(encoding="utf-8"))["renderer"], "kart")
        m = json.loads((REPO / "templates" / "eslesme.json").read_text(encoding="utf-8"))
        self.assertEqual(m["yapi_sablon"]["nasil"], "nasil", "Sabri onayladı: nasil kalıbı kendi şablonunda")
        self.assertEqual({k: v for k, v in m["yapi_sablon"].items() if not k.startswith("_")},
                         {"nasil": "nasil", "uretim": "isemri", "olsaydin": "ajanda", "efsane": "dosya", "kitap": "kitap"})
        s = self.cay
        self.assertEqual(pl.pick_template(s, "nasil"), "nasil")
        self.assertEqual(pl.pick_template(s), "nasil")
        # Claude'un önerisi nasil olsa da (claude_secsin) nasil yalnız yapi_sablon ya da --template ile seçilir
        kok = self.tmp / "kok"
        shutil.copytree(REPO / "templates", kok / "templates")
        m2 = dict(m, claude_secsin=True, yapi_sablon={"nasil": "nasil"}, kart=dict(m.get("kart") or {}, acik=False))
        (kok / "templates" / "eslesme.json").write_text(json.dumps(m2, ensure_ascii=False), encoding="utf-8")
        self.yama(pl, "ROOT", kok)
        self.assertEqual(pl.pick_template(s), "nasil", "eşleşme nasil'e çevrilince nasil kalıbı nasil şablonuna gider")
        baska = s.model_copy(update={"structure": "hikaye", "template": "nasil", "category": "uzay"})
        self.assertNotEqual(pl.pick_template(baska), "nasil")
        self.assertEqual(pl.pick_template(s.model_copy(update={"template": "kolaj", "structure": "hikaye"})), "kolaj")
        self.assertIn("nasil", pl.kendi_secimli(), "Claude'un şablon listesine girmez")
        self.assertIn("kart", pl.kendi_secimli())
        # kurgu modüllü her şablon (ör. uretim, ajanda) adından bağımsız olarak kendi kuralıyla seçilir
        uretim_sablonu(kok)
        (kok / "templates" / "deneme.json").write_text(json.dumps({"description": "d", "renderer": "nasil"}),
                                                       encoding="utf-8")
        # depodaki diğer kurgu modüllü şablonlar (ör. ajanda, dosya) da bu gruptadır; renderer'sız şablonlar hiç girmez
        kendi = pl.kendi_secimli()
        self.assertTrue({"kart", "nasil", "uretim", "ajanda", "dosya", "deneme", "kitap"} <= kendi)
        self.assertFalse(kendi & {"kolaj", "gazete", "retro", "minimal", "doga", "gece"})
        self.assertEqual((pl.sablon_yapisi("deneme"), pl.sablon_yapisi("nasil"), pl.sablon_yapisi("uretim"),
                          pl.sablon_yapisi("kart"), pl.sablon_yapisi("kolaj"), pl.sablon_yapisi("yok")),
                         ("nasil", "nasil", "uretim", "", "", ""), "yapi yoksa nasil")
        for oneri in ("uretim", "deneme", "kart"):
            self.assertNotEqual(pl.pick_template(s.model_copy(update={"template": oneri, "structure": "hikaye"})),
                                oneri, oneri)
        # kart/nasil dışındaki kurgu modülleri (shortgen/<renderer>.py) de kendi kuralıyla seçilir ve kalıbını sabitler
        (kok / "templates" / "ozel.json").write_text(json.dumps({"description": "o", "renderer": "ozel", "yapi": "efsane"}),
                                                     encoding="utf-8")
        (kok / "templates" / "ozel2.json").write_text(json.dumps({"description": "o", "renderer": "ozel"}), encoding="utf-8")
        self.assertTrue({"ozel", "ozel2"} <= pl.kendi_secimli())
        self.assertEqual((pl.sablon_yapisi("ozel"), pl.sablon_yapisi("ozel2")), ("efsane", ""))

    def test_template_nasil_kalibi_sabitler(self):
        pl = self.pl
        kok = self.tmp / "kok"
        shutil.copytree(REPO / "templates", kok / "templates")
        (kok / "state").mkdir()
        self.yama(pl, "ROOT", kok)
        cagri = {}

        def generate_script(history, topic=None, templates=None, series_prev=None, allow_series=False, kart=False,
                            structure=None, adim_kartlari=False, sablon_kurali=""):
            cagri.update(topic=topic, structure=structure, kart=kart, templates=templates, adim_kartlari=adim_kartlari)
            return self.cay.model_copy(deep=True)
        self.yama(pl, "generate_script", generate_script)
        self.yama(pl, "build", lambda script, out, **k: cagri.update(sablon=k["template"]) or out / "video.mp4")
        eski_etiket = os.environ.get("SERIES_LABEL")
        os.environ["SERIES_LABEL"] = "0"
        self.addCleanup(lambda: os.environ.__setitem__("SERIES_LABEL", eski_etiket) if eski_etiket is not None
                        else os.environ.pop("SERIES_LABEL", None))
        def calistir(*argv):
            eski = sys.argv
            sys.argv = ["pipeline", *argv, "--out", str(self.tmp / "out")]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    pl.main()
            finally:
                sys.argv = eski
        for argv, kalip, sablon in ((["--topic", "çay", "--template", "nasil"], "nasil", "nasil"),
                                    (["--topic", "çay", "--template", "nasil", "--structure", "nasil"], "nasil", "nasil"),
                                    (["--topic", "çay", "--structure", "nasil"], "nasil", "nasil")):
            cagri.clear()
            calistir(*argv)
            self.assertEqual((cagri["structure"], cagri["sablon"]), (kalip, sablon), argv)
            self.assertNotIn("nasil", cagri["templates"] or {}, "nasil Claude'a önerilmez")
            acik = bool((json.loads((REPO / "templates" / "eslesme.json").read_text(encoding="utf-8"))
                         .get("kart") or {}).get("acik"))
            self.assertEqual(cagri["kart"], acik or sablon == "kart", "nasil şablonu kart yönergesi istemez")
            # Adım kartları düzeni yalnız video nasil şablonuyla çizilecekse istenir (kart'a giden nasil genel kurallarla)
            self.assertEqual(cagri["adim_kartlari"], sablon == "nasil", argv)
        # eşleşme nasil şablonuna çevrilince kalıpla gelen nasil da Adım kartları düzeniyle yazılır
        m = json.loads((kok / "templates" / "eslesme.json").read_text(encoding="utf-8"))
        m["yapi_sablon"]["nasil"] = "nasil"
        (kok / "templates" / "eslesme.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        cagri.clear()
        calistir("--topic", "çay", "--structure", "nasil")
        self.assertEqual((cagri["sablon"], cagri["adim_kartlari"]), ("nasil", True))
        # nasil şablonu başka kalıpla kullanılmaz: Claude'a gitmeden (ya da kurguya geçmeden) durur
        cagri.clear()
        with self.assertRaises(SystemExit) as hata:
            calistir("--topic", "çay", "--template", "nasil", "--structure", "efsane")
        self.assertIn("nasil kalıbıyla", str(hata.exception))
        self.assertEqual(cagri, {}, "senaryo yazdırılmadı")
        efsane = self.tmp / "efsane.json"
        efsane.write_text(self.cay.model_copy(update={"structure": "efsane"}).model_dump_json(), encoding="utf-8")
        with self.assertRaises(SystemExit):
            calistir("--script", str(efsane), "--template", "nasil", "--no-voice")
        self.assertNotIn("sablon", cagri, "kurgu başlamadı")

    # ------------------------------------------------------------ senaryo yönergesi
    def test_nasil_yonergesi_yalniz_nasil_kalibinda(self):
        sc = self.sc
        h = self.tmp / "history.jsonl"
        h.write_text("", encoding="utf-8")
        sistem = []

        def ask(prompt, schema, system, web=False):
            sistem.append((schema.__name__, system, prompt))
            s = self.cay.model_copy(deep=True)
            if schema is sc.ShortScript:
                return s
            if schema is sc.Review:
                return sc.Review(ok=True, problems=[], fixed=s)
            return sc.Polished(notes=[], fixed=s)
        self.yama(sc, "ask_claude", ask)
        with contextlib.redirect_stdout(io.StringIO()):
            sc.generate_script(h, "çay", structure="nasil", adim_kartlari=True)
            nasil = sistem[:]
            sistem.clear()
            sc.generate_script(h, "çay", structure="nasil")   # yapi_sablon nasil -> kart: genel sahne kuralları
            kart = sistem[:]
            sistem.clear()
            sc.generate_script(h, "çay", structure="efsane", adim_kartlari=True)
            efsane = sistem[:]
            sistem.clear()
            sc.generate_script(h, None, series_prev={"structure": "nasil", "title": "t", "topic": "çay", "brief": "b",
                                                     "narration": "n", "category": "bilim"}, adim_kartlari=True)
            seri = sistem[:]
        adlar = [a for a, _, _ in nasil]
        self.assertEqual(adlar, ["ShortScript", "Review", "Polished"])
        self.assertIn(sc.NASIL_RULES, nasil[0][1], "üretici")
        self.assertIn(sc.NASIL_RULES, nasil[1][1], "doğrulayıcı")
        self.assertIn("numaralı adım sahneleri", nasil[1][2])
        self.assertIn("step/callouts", nasil[2][1], "editör adım alanlarına dokunmaz")
        self.assertIn(sc.EDITOR_NASIL, nasil[2][1], "editör Adım kartlarının başlıklarına dokunmaz")
        self.assertIn(sc.NASIL_RULES, seri[0][1])
        self.assertEqual([a for a, _, _ in kart], ["ShortScript", "Review", "Polished"])
        for ad, system, prompt in kart + efsane:
            self.assertNotIn(sc.NASIL_RULES, system, ad)
            self.assertNotIn(sc.EDITOR_NASIL, system, ad)
            self.assertNotIn("numaralı adım sahneleri", prompt, ad)
        self.assertIn("Güvenli olmayan", kart[1][2], "güvenlik süzgeci şablondan bağımsız")
        # Adım kartlarında cümle sahneler arasında bölünmez, özetteki neden Makas'ın yorumunun yerine geçer
        for parca in ("cümleyi sahneler arasında BÖLME", "ayrıca yorum cümlesi ekleme", "başlıkta yazanı tekrarlamasın",
                      '"4 ADIM" ekranda kendiliğinden çıkar'):
            self.assertIn(parca, sc.NASIL_RULES)
        # ocakta olağan pişirme yasak değil (çay demleme adımı), açık ateş püf noktaları yasak
        self.assertIn("açık ateş", sc.NASIL_YASAK)
        self.assertIn("ocakta ya da fırında olağan pişirme, olağan kızartma ve su kaynatma hariç", sc.NASIL_YASAK)
        self.assertIn("NASIL YAPILIR:", sc.STRUCTURES["nasil"][1])
        self.assertIn(sc.NASIL_YASAK, sc.STRUCTURES["nasil"][1])
        self.assertIn(sc.NASIL_YASAK, sc.NASIL_RULES)

    def test_dil_duzeltmesi_adim_alanlarini_korur(self):
        sc = self.sc
        bozuk = self.cay.model_copy(deep=True)
        for x in bozuk.scenes:
            x.step, x.callouts = 0, []
        bozuk.scenes[0].headline, bozuk.scenes[0].highlight_line = ["ÇAYI ACI YAPAN", "DEMLEME SÜRESİ"], 0
        bozuk.scenes[2].headline = ["ADIM 2", "DEMLİĞİ SICAK SUYLA ISIT"]
        sistem = []

        def ask(prompt, schema, system, web=False):
            sistem.append(system)
            return sc.Polished(notes=[], fixed=bozuk.model_copy(deep=True))
        self.yama(sc, "ask_claude", ask)
        out = sc.polish_script(self.cay.model_copy(deep=True))
        self.assertEqual([x.step for x in out.scenes], [0, 1, 2, 3, 4, 0])
        self.assertEqual(out.scenes[3].callouts, ["KİŞİ BAŞI", "1 TATLI KAŞIĞI"])
        self.assertEqual(out.scenes[0].headline, ["ÇAYI ACI YAPAN", "DEMLEME SÜRESİ"], "kart şablonunda editör yazar")
        self.assertNotIn(sc.EDITOR_NASIL, sistem[-1])
        # Adım kartları: soru kancası, adım ve özet başlıkları editörden önceki hâliyle kalır
        out = sc.polish_script(self.cay.model_copy(deep=True), adim_kartlari=True)
        self.assertIn(sc.EDITOR_NASIL, sistem[-1])
        self.assertEqual([x.headline for x in out.scenes], [x.headline for x in self.cay.scenes])
        self.assertEqual([x.highlight_line for x in out.scenes], [x.highlight_line for x in self.cay.scenes])
        efsane = self.cay.model_copy(update={"structure": "efsane"}, deep=True)
        out = sc.polish_script(efsane, adim_kartlari=True)
        self.assertEqual(out.scenes[0].headline, ["ÇAYI ACI YAPAN", "DEMLEME SÜRESİ"], "başka kalıpta etkisiz")

    def test_adim_duzeni_normallestirilir(self):
        sc = self.sc
        s = self.cay.model_copy(deep=True)
        # doğrulayıcı step alanlarını silmiş, adımları atlamalı numaralamış, bir adımı iki sahneye bölmüş olsun
        for x in s.scenes:
            x.step = 0
        s.scenes[1].headline, s.scenes[1].highlight_line = ["adım 2: demliği ısıt"], 0   # tek satırda önek
        s.scenes[2].headline = ["3. ADIM", "SUYU KAYNAT"]
        s.scenes[3].headline = ["KAYNAMAYI BEKLE"]                     # iki adım arası adımsız: önceki adımın devamı
        s.scenes[4].headline, s.scenes[4].highlight_line, s.scenes[4].step = ["ÇAYI KOY"], 0, 6  # yalnız step alanı
        out = sc.normalize_nasil(s)
        self.assertEqual([x.step for x in out.scenes], [0, 1, 2, 2, 3, 0])
        self.assertEqual(out.scenes[1].headline, ["ADIM 1", "DEMLİĞİ ISIT"])
        self.assertEqual(out.scenes[1].highlight_line, 1, "vurgu aynı satırda kalır")
        self.assertEqual(out.scenes[2].headline, ["ADIM 2", "SUYU KAYNAT"])
        self.assertEqual(out.scenes[3].headline, ["KAYNAMAYI BEKLE"], "devam sahnesine numara eklenmez")
        self.assertEqual((out.scenes[4].headline, out.scenes[4].highlight_line), (["ADIM 3", "ÇAYI KOY"], 1))
        self.assertEqual(out.scenes[5].headline, ["ÇAY DEMLEME"])
        efsane = self.cay.model_copy(update={"structure": "efsane"}, deep=True)
        efsane.scenes[1].headline = ["ADIM 7"]
        self.assertEqual(sc.normalize_nasil(efsane).scenes[1].headline, ["ADIM 7"], "başka kalıpta dokunulmaz")

    def test_adim_sayisi_basligi_adim_sanilmaz(self):
        sc = self.sc
        for silinmis in (False, True):     # step alanları duruyor / doğrulayıcı silmiş
            s = self.cay.model_copy(deep=True)
            if silinmis:
                for x in s.scenes:
                    x.step = 0
            s.scenes[0].headline = ["4 ADIM", "ÇAY NASIL DEMLENİR?"]
            s.scenes[-1].headline = ["4 ADIM", "ÇAY DEMLEME"]
            out = sc.normalize_nasil(s)
            self.assertEqual([x.step for x in out.scenes], [0, 1, 2, 3, 4, 0], silinmis)
            self.assertEqual(out.scenes[0].headline, ["4 ADIM", "ÇAY NASIL DEMLENİR?"], "kanca başlığı kalır")
            self.assertEqual(out.scenes[-1].headline, ["4 ADIM", "ÇAY DEMLEME"], "özet adıma katılmaz")
        # ilk ve son sahnede 'ADIM n' de okunmaz; ters biçimde sıra noktası şart
        s = self.cay.model_copy(deep=True)
        for x in s.scenes:
            x.step = 0
        s.scenes[-1].headline = ["ADIM 4", "TAM KIVAM ÇAY"]
        self.assertEqual([x.step for x in sc.normalize_nasil(s).scenes], [0, 1, 2, 3, 4, 0])
        for satir, beklenen in (("ADIM 1", 1), ("1. ADIM", 1), ("1.ADIM: ÇAYI KOY", 1), ("ADIM 2: SUYU KAYNAT", 2),
                                ("adım 3", 3), ("4 ADIM", 0), ("3 ADIM:", 0), ("4 ADIMDA ÇAY", 0), ("ADIM ADIM", 0),
                                ("AŞAMA 1", 1), ("2. AŞAMA", 2), ("aşama 3: grafit pişirilir", 3), ("2.AŞAMA", 2),
                                ("4 AŞAMA", 0), ("4 AŞAMADA KALEM", 0), ("AŞAMA AŞAMA", 0), ("AŞAMALAR", 0)):
            self.assertEqual(sc.adim_isaretleri([0, 0, 0], ["", satir, ""])[1], beklenen, satir)

    def test_son_adimin_devami_ozete_kaymaz(self):
        sc = self.sc
        s = self.cay.model_copy(deep=True)
        # son adım iki sahneye bölünmüş, yalnız ilki işaretli: devam sahnesi son adımda kalır, özet yalnız son sahne
        devam = s.scenes[4].model_copy(update={"step": 0, "headline": ["DEMLİK ÜSTTE"], "narration": "Kapağı açma."})
        s.scenes.insert(5, devam)
        out = sc.normalize_nasil(s)
        self.assertEqual([x.step for x in out.scenes], [0, 1, 2, 3, 4, 4, 0])
        self.assertEqual(out.scenes[5].headline, ["DEMLİK ÜSTTE"], "devam sahnesine numara eklenmez")
        self.assertEqual(sc.adim_gruplari([0, 1, 0, 2, 0, 3, 0, 0]), ([0], [(1, [1, 2]), (2, [3, 4]), (3, [5, 6])], [7]))
        self.assertEqual(sc.adim_gruplari([0, 1, 2, 3]), ([0], [(1, [1]), (2, [2]), (3, [3])], []))

    # ------------------------------------------------------------ kurgu planı
    def test_sahne_plani(self):
        _, nasil = self.kart_modulu()
        S = lambda hl, step=0, callouts=(), sprite=None, image=None, hlx=-1: types.SimpleNamespace(  # noqa: E731
            headline=list(hl), highlight_line=hlx, sprite=sprite, image=image,
            card={"step": step, "callouts": list(callouts), "mascot": "auto"})
        specs = [S(["ÇAY NASIL", "DEMLENİR?"], hlx=1, sprite=Path("k.png")),
                 S(["ADIM 1", "demliği ısıt"], 1, ["sıcak su", "", "a", "b"]),
                 S(["DEVAMI"], 1, sprite=Path("a1.png")),
                 S(["ARA"], 0),
                 S(["ADIM 2: suyu kaynat"], 5, image=Path("f.jpg")),
                 S(["ÇAY DEMLEME"]), S(["SON"])]
        segs = nasil.plan(specs)
        self.assertEqual([(g.kind, g.scenes, g.number) for g in segs],
                         [("hook", [0], 0), ("step", [1, 2, 3], 1), ("step", [4, 5], 2), ("recap", [6], 0)],
                         "son adımdan sonraki adımsız sahne son adımın devamı, özet yalnız son sahne")
        self.assertEqual(segs[0].hl, 1)
        self.assertEqual(segs[1].title, ["DEMLİĞİ ISIT"])
        self.assertEqual(segs[1].callouts, ["SICAK SU", "A"], "boş not atlanır, en çok 2 not, Türkçe büyük harf")
        self.assertEqual(segs[1].sprite, Path("a1.png"), "bölümün ilk çizimi")
        self.assertEqual((segs[2].title, segs[2].image), (["SUYU KAYNAT"], Path("f.jpg")))
        # yalnız başlıktaki adım işaretleri
        b = nasil.plan([S(["KANCA"]), S(["ADIM 1", "X"]), S(["2. ADIM", "Y"]), S(["adım 3", "Z"]), S(["ÖZET"])])
        self.assertEqual([(g.kind, g.number, g.title) for g in b],
                         [("hook", 0, ["KANCA"]), ("step", 1, ["X"]), ("step", 2, ["Y"]), ("step", 3, ["Z"]),
                          ("recap", 0, ["ÖZET"])])
        # adım işareti yok (başka kalıpta yazılmış senaryo): ilk sahne kanca, son sahne özet
        c = nasil.plan([S([str(i)]) for i in range(5)])
        self.assertEqual([(g.kind, g.scenes, g.number) for g in c],
                         [("hook", [0], 0), ("step", [1], 1), ("step", [2], 2), ("step", [3], 3), ("recap", [4], 0)])
        self.assertEqual([g.title for g in c][1], ["1"], "işaretsiz adımın başlığı sahne başlığıdır")
        self.assertEqual([g.kind for g in nasil.plan([S(["A"]), S(["B"])])], ["hook", "step"])
        self.assertEqual(nasil.plan([]), [])
        # kancada ya da özette adım sayısı ('4 ADIM') adım işareti değildir
        d = nasil.plan([S(["4 ADIM", "MUZ NASIL", "TAZE KALIR?"]), S(["ADIM 1", "SAR"], 1), S(["ADIM 2", "AS"], 2),
                        S(["4 ADIM", "MUZ SAKLAMA"])])
        self.assertEqual([(g.kind, g.scenes, g.title) for g in d],
                         [("hook", [0], ["4 ADIM", "MUZ NASIL", "TAZE KALIR?"]), ("step", [1], ["SAR"]),
                          ("step", [2], ["AS"]), ("recap", [3], ["4 ADIM", "MUZ SAKLAMA"])])

    def test_balon_sayfalari(self):
        kart, nasil = self.kart_modulu()
        from shortgen.voice import Word
        metin = ("Çünkü uzun kaynayan su çayı yavanlaştırır, fazla demlenen çay da tanen salıp acılaşır. "
                 "Sen çayını kaç dakika demliyorsun? Yorumlara yaz.")
        words = [Word(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(metin.split())]
        soru = metin.split().index("Sen")
        sp = nasil.Speech(words, 0, len(words), (112, 1100, 880, 1230), breaks={soru})
        sayfa = [i for p0, p1 in sp.pages for i in range(p0, p1)]
        self.assertEqual(sayfa, list(range(len(words))), "her kelime bir kez, sırayla")
        self.assertIn(soru, sp.page_starts, "soru cümlesi yeni sayfada başlar")
        self.assertTrue(sp.page_kind(soru, {soru}))
        self.assertFalse(sp.page_kind(0, {soru}))
        for pi, lines in sp.lines.items():
            self.assertLessEqual(len(lines), sp.max_lines)
            for L in lines:
                self.assertLessEqual(kart.tw(" ".join(words[i].text for i in L), sp.FONT, sp.size), sp.width + 0.5)
            if len(lines) > 1:
                self.assertGreater(len(lines[-1]), 1, "son satırda tek kelime kalmaz")
        # uzun tek cümle önce yan cümleden bölünür
        uzun = [Word(w, 0, 0) for w in ("Son olarak demliği çaydanlığın üstüne koy, kısık ateşte on iki ila on beş "
                                        "dakika boyunca hiç kapağını açmadan sabırla demle.").split()]
        sp2 = nasil.Speech(uzun, 0, len(uzun), (112, 1380, 880, 1500), sizes=(40,), max_lines=2)
        self.assertGreater(len(sp2.pages), 1)
        self.assertEqual(uzun[sp2.pages[0][1] - 1].text, "koy,", "sayfa yan cümle sonunda biter")

    # ------------------------------------------------------------ kurgu ayrıntıları
    def nasil_video(self, adim=4, ozet="Uzun kaynayan su çayı yavanlaştırır, fazla demlenen çay acılaşır. "
                    "Sen çayını kaç dakika demliyorsun? Yorumlara yaz.", sprite=None):
        kart, nasil = self.kart_modulu()
        from shortgen.voice import Word
        metinler = (["Çayı acı yapan çoğu zaman demleme süresi."]
                    + [f"Adım {k} için kısa bir cümle söyle." for k in range(1, adim + 1)] + [ozet])
        words, scenes, t = [], [], 0.0
        for i, m in enumerate(metinler):
            ws = [Word(w, t + j * 0.4, t + j * 0.4 + 0.35) for j, w in enumerate(m.split())]
            start, t = t, t + len(ws) * 0.4 + 0.3
            words += ws
            step = i if 0 < i <= adim else 0
            hl = (["ÇAY NASIL", "DEMLENİR?"] if i == 0 else
                  [f"ADIM {i}", "KISIK ATEŞTE", "DEMLE"] if step else ["ÇAY DEMLEME"])
            scenes.append(types.SimpleNamespace(words=ws, start=start, end=t, kicker="", headline=hl, highlight_line=-1,
                                                sprite=sprite if step else None, image=None,
                                                card={"step": step, "callouts": [], "mascot": "auto"}))
        return nasil.NasilVideo(scenes, words, {}, {}), nasil, kart

    def test_baslik_satirlari_turkce_cengellerle_cakismaz(self):
        kart, nasil = self.kart_modulu()
        from PIL import Image, ImageDraw
        import numpy as np
        for lines, size, acilir in ((["KISIK ATEŞTE", "12-15 DK DEMLE"], 100, True),
                                    (["ÇAYI KOY,", "KAYNAR SUYU DÖK"], 88, True),
                                    (["SUYU KAYNAT", "AMA TAŞIRMA"], 100, False)):
            p = nasil.title_pitch(lines, size)
            taban = nasil.cap_h("anton", size) * 1.12 + size * 0.1
            self.assertEqual(p > taban + 1, acilir, lines)
            # iki satırı ayrı ayrı çiz: üst satırın mürekkebi (2 px payla) alttakine değmez
            f = kart.fnt("anton", size)
            maske = []
            for k, L in enumerate(lines):
                im = Image.new("L", (int(f.getlength(L)) + 40, int(size * 3)), 0)
                ImageDraw.Draw(im).text((10, size * 1.1 + k * p), L, font=f, fill=255, anchor="ls")
                maske.append(np.asarray(im) > 96)
            w = min(m.shape[1] for m in maske)
            ust = np.zeros_like(maske[0][:, :w])
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    ust |= np.roll(np.roll(maske[0][:, :w], dy, 0), dx, 1)
            self.assertFalse((ust & maske[1][:, :w]).any(), lines)
        # boyut seçimi çizimdeki satır aralığıyla ölçer: blok başlık alanına (196 px) sığar
        for baslik in (["KISIK ATEŞTE", "12-15 DK DEMLE"], ["ÇAYI KOY,", "KAYNAR SUYU DÖK"], ["ŞİŞEYİ ÇALKALA,", "ÇÖZ"]):
            size, lines = nasil.fit_lines(baslik, "anton", 618, 112, 54, 3, 196, pitch=nasil.title_pitch)
            blok = nasil.cap_h("anton", size) + (len(lines) - 1) * nasil.title_pitch(lines, size)
            self.assertLessEqual(blok, 196, baslik)

    def test_ilerleme_makasi_son_dugumu_kapatmaz(self):
        for adim in (3, 4, 5):
            v, nasil, _ = self.nasil_video(adim)
            son, nx = v.steps[-1], v.node_x
            for lt in (nasil.T_REACH + 0.35, 1.0, son.end - son.start - 0.05):
                x, dy, kesiyor, bar = v.scissors_at(son.start + lt)
                sag, sol = x + nasil.SC_W * (1 - nasil.SC_PIN), x - nasil.SC_W * nasil.SC_PIN
                self.assertLessEqual(sag, nx[-1] - 52 + 0.5, (adim, lt))         # kırmızı düğümün solunda
                self.assertGreaterEqual(sol, nx[-2] + 40 - 0.5, (adim, lt))      # önceki düğüme de binmez
                if adim <= 4:
                    self.assertLessEqual(sag, nx[-1] - 52 * 1.25, "düğüm patlarken bile")
                self.assertEqual((bar, kesiyor), (nx[-1], False), "son çizgi kesilmiş")
            # ara adımlarda makas düğümün sağında bir sonrakine doğru keser (değişmedi)
            x, _, kesiyor, bar = v.scissors_at(v.steps[0].end - 0.05)
            self.assertTrue(kesiyor and nx[0] + 52 < x - nasil.SC_W * nasil.SC_PIN + 30 and bar == x)

    def test_ozet_eski_kart_kesildikten_sonra_gelir(self):
        from PIL import Image
        v, nasil, _ = self.nasil_video(4)
        self.assertGreaterEqual(nasil.RECAP0, nasil.CUT)
        seg = v.segs[-1]
        bos = Image.new("RGBA", (nasil.W, nasil.H), (0, 0, 0, 0))
        for lt in (0.0, 0.2, nasil.CUT - 0.01):
            img = bos.copy()
            v.draw_recap(img, seg, lt, seg.start + lt)
            self.assertIsNone(img.getbbox(), f"özet {lt:.2f} sn'de çizilmemeli")
        img = bos.copy()
        v.draw_recap(img, seg, nasil.RECAP0 + 0.2, seg.start + nasil.RECAP0 + 0.2)
        self.assertIsNotNone(img.getbbox())

    def test_yorum_cagrisi_ekranda_bir_kez(self):
        from PIL import Image
        kart, _ = self.kart_modulu()
        konan = []
        eski = kart.put
        self.yama(kart, "put", lambda img, layer, *a, **k: (konan.append(layer), eski(img, layer, *a, **k)))
        for ozet, cagri in (("Uzun kaynayan su çayı yavanlaştırır. Sen çayını kaç dakika demliyorsun? Yorumlara yaz.",
                             True),
                            ("Uzun kaynayan su çayı yavanlaştırır. Sen çayını kaç dakika demliyorsun?", False)):
            v, nasil, kart = self.nasil_video(4, ozet)
            seg = v.segs[-1]
            sp, R, cta = v.speech(seg), v.recap_parts(seg), v.recap_cta(seg)
            soru = min(v.recap_breaks(seg))
            self.assertEqual(v.words[soru].text, "Sen")
            if cagri:
                self.assertEqual((v.words[cta].text, sp.b), ("Yorumlara", cta), "çağrı kutuya yazılmaz")
                an = v.words[cta].start
            else:
                self.assertIsNone(cta)
                self.assertEqual(sp.b, seg.b)
                an = v.words[soru].start
            self.assertTrue(all(i < sp.b for p0, p1 in sp.pages for i in range(p0, p1)))
            for t, beklenen in ((an - 0.3, False), (an + 0.1, True), (seg.end - 0.05, True)):
                konan.clear()
                v.draw_recap(Image.new("RGBA", (nasil.W, nasil.H)), seg, t - seg.start, t)
                self.assertEqual(any(x is R["sticker"] for x in konan), beklenen, (ozet, t))
                self.assertEqual(any(x is R["save"] for x in konan), not beklenen, "kaydet etiketi çıkartmadan önce")

    def test_yeni_kart_sag_kenarda_yumusak_belirir(self):
        from PIL import Image
        import numpy as np
        _, nasil = self.kart_modulu()
        kat = Image.new("RGBA", (300, 4), (0, 0, 0, 255))
        a = np.asarray(nasil.feather_right(kat, 700).getchannel("A"))[0]
        self.assertEqual(a[875 - 700], 255)
        self.assertLess(a[934 - 700], 10)
        self.assertTrue(100 < a[905 - 700] < 160)
        self.assertIs(nasil.feather_right(kat, 700, strength=0), kat, "yerinde duran kart yumuşatılmaz")
        self.assertIs(nasil.feather_right(kat, 500), kat, "kenara uzanmayan katman")
        # kayan kartın kağıdı x=930'da arka plandan ayrışmaz; oturmuş kartın sağ kenarı tam görünür
        v, nasil, _ = self.nasil_video(4)
        seg = v.steps[1]
        zemin = np.asarray(nasil.yellow_bg().convert("RGB")).astype(int)
        for lt in (nasil.SLIDE0 + 0.03, nasil.SLIDE0 + 0.06, nasil.SLIDE0 + 0.1):
            img = nasil.yellow_bg().copy()
            v.draw_step(img, seg, lt, True)
            fark = np.abs(np.asarray(img.convert("RGB")).astype(int) - zemin).sum(axis=2)
            self.assertLess(fark[nasil.CARD[1] + 20:nasil.CARD[3] - 20, 930].max(), 60, lt)
        img = nasil.yellow_bg().copy()
        v.draw_step(img, seg, 2.0, True)
        fark = np.abs(np.asarray(img.convert("RGB")).astype(int) - zemin).sum(axis=2)
        self.assertGreater(fark[700, 916:921].max(), 400, "kartın mürekkep çerçevesi")

    def test_makas_adim_cizimini_kapatmaz(self):
        import numpy as np
        for ad in ("adim1_kaynat", "adim2_demlik", "adim3_koy", "adim4_demle"):
            v, nasil, _ = self.nasil_video(4, sprite=REPO / "demo" / "nasil" / f"{ad}.png")
            seg = v.steps[0]
            kutu = (nasil.CARD[0] + 30, 790, nasil.CARD[2] - 150, nasil.CARD[3] - 28)
            d, dx, dy = v.fit_drawing(seg, kutu)
            zone, zx, zy = v.mascot_zone(seg)
            a = np.asarray(d.getchannel("A").resize((int(d.width / 2), int(d.height / 2)))) > 140
            ekran = np.zeros((nasil.H, nasil.W), bool)
            ekran[int(dy):int(dy) + a.shape[0], int(dx):int(dx) + a.shape[1]] = a
            self.assertLessEqual(int((ekran[zy:zy + zone.shape[0], zx:zx + zone.shape[1]] & zone).sum()), 40, ad)
            self.assertGreaterEqual(max(d.width / 2 / (kutu[2] - kutu[0]), d.height / 2 / (kutu[3] - kutu[1])), 0.65, ad)

    def test_kurgu_nasil_modulune_gider(self):
        _, nasil = self.kart_modulu()
        pl = self.pl
        cap = {}
        self.yama(nasil, "render_nasil", lambda specs, words, out, mp3, music, meta: cap.update(
            specs=specs, words=words, meta=meta))
        from shortgen import render
        self.addCleanup(render.apply_template, "kolaj")
        with contextlib.redirect_stdout(io.StringIO()):
            pl.build(self.cay.model_copy(deep=True), self.tmp / "out", use_voice=False, music=None, template="nasil")
        self.assertEqual([s.card["step"] for s in cap["specs"]], [0, 1, 2, 3, 4, 0])
        self.assertEqual(cap["specs"][2].card["callouts"], ["ÇALKALA, BOŞALT", "SICAK SU"])
        self.assertEqual([s.sprite.name if s.sprite else None for s in cap["specs"]],
                         ["kanca_cay.png", "adim1_kaynat.png", "adim2_demlik.png", "adim3_koy.png", "adim4_demle.png",
                          None])
        self.assertEqual(len(cap["words"]), 74)
        self.assertEqual(cap["meta"]["structure"], "nasil")
        self.assertEqual([g.kind for g in nasil.plan(cap["specs"])], ["hook", "step", "step", "step", "step", "recap"])

    # ------------------------------------------------------------ iş akışı
    def test_ornek_yml_kalip_ortamdan_gecer(self):
        y = (REPO / ".github" / "workflows" / "ornek.yml").read_text(encoding="utf-8")
        self.assertRegex(y, r"\n      kalip:\n        description: .+\n        required: false\n")
        self.assertEqual(y.count("${{ github.event.inputs.kalip }}"), 2, "kalıp yalnız env ile geçer")
        self.assertEqual(y.count("KALIP: ${{ github.event.inputs.kalip }}"), 2)
        self.assertIn('[ -z "$SENARYO" ] && [ -n "$KALIP" ] && ARGS+=(--structure "$KALIP")', y)
        self.assertIn("nasil", re.search(r"\n      sablon:\n        description: (.+)\n", y).group(1))
        self.assertIn("uretim", re.search(r"\n      sablon:\n        description: (.+)\n", y).group(1))
        for k in ("uretim", "olsaydin"):
            self.assertIn(k, re.search(r"\n      kalip:\n        description: (.+)\n", y).group(1))
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML yok")
        adimlar = yaml.safe_load(y)["jobs"]["ornek"]["steps"]
        girdi = next(a for a in adimlar if a.get("name") == "Girdiler")
        sonuc = {}
        for kalip in ("", "nasil", "efsane", "uretim", "olsaydin", "Nasil", "nasil; id", "$(id)", "a" * 21):
            env = dict(os.environ, SENARYO="", KONU="çay", KALIP=kalip)
            r = __import__("subprocess").run(["bash", "-c", girdi["run"]], env=env, capture_output=True, text=True)
            sonuc[kalip] = r.returncode
        self.assertEqual(sonuc, {"": 0, "nasil": 0, "efsane": 0, "uretim": 0, "olsaydin": 0, "Nasil": 1, "nasil; id": 1,
                                 "$(id)": 1, "a" * 21: 1})
        uret = next(a for a in adimlar if a.get("name") == "Örnek videoyu üret")
        self.assertNotIn("inputs.", uret["run"], "girdiler betiğe doğrudan yazılmaz")


class YeniSeriler(unittest.TestCase):
    """Nasıl üretiliyor? (uretim) ve Ya sen olsaydın? (olsaydin) serileri: istemler, aşama düzeni, şablon yönlendirme,
    hesap fişi denetimi, açıklamadaki uyarı satırı ve alkollü içecek anahtarı. Mevcut kalıpların istemleri değişmez."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO))
        for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
            del sys.modules[ad]
        import shortgen.pipeline as pl
        import shortgen.publish as P
        import shortgen.script as sc
        import shortgen.trends as tr
        cls.pl, cls.P, cls.sc, cls.tr = pl, P, sc, tr
        cls.cay = sc.load_script(REPO / "demo" / "nasil" / "ornek_cay.json")
        cls.demo = sc.load_script(REPO / "demo" / "demo_script.json")

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(REPO))
        for ad in [m for m in sys.modules if m == "shortgen" or m.startswith("shortgen.")]:
            del sys.modules[ad]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="seri_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.h = self.tmp / "history.jsonl"
        self.h.write_text("", encoding="utf-8")

    def yama(self, nesne, ad, deger):
        eski = getattr(nesne, ad)
        setattr(nesne, ad, deger)
        self.addCleanup(setattr, nesne, ad, eski)

    def uret(self, donen, **kw):
        """generate_script'i sahte Claude ile çalıştırır; (çıktı, [(şema, sistem, istem, web)], günlük) döndürür.
        donen: her geçişin döndüreceği senaryo (kopyası)."""
        sc = self.sc
        cagri = []

        def ask(prompt, schema, system, web=False):
            cagri.append((schema.__name__, system, prompt, web))
            s = donen.model_copy(deep=True)
            if schema is sc.ShortScript:
                return s
            if schema is sc.Review:
                return sc.Review(ok=True, problems=[], fixed=s)
            return sc.Polished(notes=[], fixed=s)
        self.yama(sc, "ask_claude", ask)
        with contextlib.redirect_stdout(io.StringIO()) as gunluk:
            out = sc.generate_script(self.h, kw.pop("konu", "konu"), **kw)
        return out, cagri, gunluk.getvalue()

    # ------------------------------------------------------------ mevcut kalıplar
    def test_mevcut_kaliplarin_istemleri_degismez(self):
        """hikaye/efsane/sayac/neden (ve serbest dönüşüm) istemleri origin/main'dekiyle (fixtures/istem_golden.json)
        harfi harfine aynı: sistem istemleri (üretici, doğrulayıcı, editör) ve üreticinin istemi."""
        golden = json.loads((FIX / "istem_golden.json").read_text(encoding="utf-8"))
        metin = golden["metinler"]
        for d in golden["durumlar"]:
            _, cagri, _ = self.uret(self.demo.model_copy(update={"structure": d["kalip"] or "hikaye"}),
                                    konu="muz", structure=d["kalip"], kart=d["kart"], adim_kartlari=d["adim_kartlari"])
            ad = (d["kalip"], d["kart"], d["adim_kartlari"])
            self.assertEqual([c[0] for c in cagri], [g["sema"] for g in d["cagrilar"]], ad)
            for c, g in zip(cagri, d["cagrilar"]):
                self.assertEqual(c[1], metin[g["system"]], (ad, g["sema"]))
                self.assertEqual(c[3], g["web"], (ad, g["sema"]))
                if "prompt" in g:
                    self.assertEqual(c[2], metin[g["prompt"]], ad)
        for k in ("hikaye", "efsane", "sayac", "neden"):  # yeni yönergeler (kitap dahil) bu kalıplara eklenmez
            self.assertEqual(self.sc.kalip_kurallari(k, True), "")
            self.assertEqual(self.sc.kalip_kurallari(k, False), "")
        self.assertNotIn("receipt", self.sc.KART_RULES, "hesap fişi yönergesi yalnız OLSAYDIN_RULES'ta")

    # ------------------------------------------------------------ Nasıl üretiliyor?
    def uretim_senaryosu(self):
        s = self.cay.model_copy(update={"structure": "uretim", "template": "uretim"}, deep=True)
        for x in s.scenes:
            x.headline = ["AŞAMA" + h[4:] if h.startswith("ADIM") else h for h in x.headline]
        return s

    def test_uretim_istemleri(self):
        sc = self.sc
        out, cagri, _ = self.uret(self.cay.model_copy(update={"structure": "uretim"}), konu="kurşun kalem",
                                  structure="uretim", adim_kartlari=True)
        self.assertEqual([(c[0], c[3]) for c in cagri], [("ShortScript", True), ("Review", True), ("Polished", False)],
                         "senaryo web aramasıyla araştırılarak yazılır")
        self.assertIn(sc.URETIM_RULES, cagri[0][1])
        self.assertIn(sc.URETIM_RULES, cagri[1][1])
        self.assertNotIn(sc.NASIL_RULES, cagri[0][1])
        self.assertNotIn(sc.OLSAYDIN_RULES, cagri[0][1])
        self.assertIn("- uretim: NASIL ÜRETİLİYOR:", cagri[0][2])
        self.assertIn("üretim sürecini web aramasıyla araştır", cagri[0][2])
        self.assertIn("ANLATIM KALIBI (SABİT)", cagri[0][2])
        for parca in ("numaralı aşama sahneleri", "'AŞAMA n'", "Aşamaların sırasını", "ölçek bilgisini", sc.URETIM_YASAK):
            self.assertIn(parca, cagri[1][2])
        self.assertIn(sc.EDITOR_URETIM, cagri[2][1])
        self.assertIn(sc.EDITOR_NASIL, cagri[2][1], "Adım kartlarında başlıklar editörden korunur")
        # çıktı: aşama numaraları 'AŞAMA n' (yazar 'ADIM n' yazsa da)
        self.assertEqual(out.structure, "uretim")
        self.assertEqual([x.step for x in out.scenes], [0, 1, 2, 3, 4, 0])
        self.assertEqual([x.headline[0] for x in out.scenes[1:5]], [f"AŞAMA {n}" for n in range(1, 5)])
        # Adım kartları dışında (ör. --template kart): ekran düzeni istenmez, araştırma ve editör kuralı kalır
        _, cagri, _ = self.uret(self.cay.model_copy(update={"structure": "uretim"}), structure="uretim", kart=True)
        self.assertNotIn(sc.URETIM_RULES, cagri[0][1])
        self.assertTrue(cagri[0][3])
        self.assertIn(sc.EDITOR_URETIM, cagri[2][1])
        self.assertNotIn(sc.EDITOR_NASIL, cagri[2][1])
        # yönerge içeriği
        for parca in ("AŞAMA n", "geniş zaman edilgen", "1.000°C", "72 SAAT", "image_mode none", "Yorumlara yaz.",
                      "yılda kaç tane", "Türkiye'nin üretimi", "Kurşun kalemin içinde tek gram kurşun yok.",
                      "çay, fındık, lokum, cam, porselen, halı, bakır cezve, çini, nazar boncuğu, beyaz"):
            self.assertIn(parca, sc.URETIM_RULES)
        for yasak in ("silah", "mühimmat", "patlayıcı", "uyuşturucu", "alkol ve tütün ürünleri", "tehlikeli kimyasalların",
                      "hayvan kesiminin", "evde denemeye teşvik", "gizli tarifini"):
            self.assertIn(yasak, sc.URETIM_YASAK)
        for yer in (sc.STRUCTURES["uretim"][1], sc.URETIM_RULES, self.tr.SYSTEM):
            self.assertIn(sc.URETIM_YASAK, yer)
        # anlatı zamanı her yerde aynı ad ve örnekle: geniş zaman ('pişirilir'); ekrandaki soru serinin adıyla aynı
        for yer in (sc.STRUCTURES["uretim"][1], sc.URETIM_RULES, sc.EDITOR_URETIM):
            self.assertIn("geniş\n" if yer is sc.EDITOR_URETIM else "geniş", yer)
            self.assertIn("zaman edilgen", yer)
            self.assertIn("pişirilir", yer)
            self.assertNotIn("şimdiki", yer)
        self.assertIn('"KURŞUN KALEM" / "NASIL" / "ÜRETİLİYOR?"', sc.URETIM_RULES)
        self.assertNotIn("ÜRETİLİR?", sc.URETIM_RULES)

    def test_uretim_asama_duzeni(self):
        sc = self.sc
        s = self.uretim_senaryosu()
        for x in s.scenes:
            x.step = 0
        s.scenes[1].headline, s.scenes[1].highlight_line = ["aşama 2: grafit öğütülür"], 0
        s.scenes[2].headline = ["3. AŞAMA", "KİLLE KARIŞTIRILIR"]
        s.scenes[3].headline = ["ADIM 4", "FIRINDA PİŞİRİLİR"]   # yazar adım yazmış: aşamaya çevrilir
        s.scenes[4].headline = ["KURUTULUR"]                       # iki aşama arası işaretsiz: önceki aşamanın devamı
        s.scenes[-1].headline = ["4 AŞAMA", "KURŞUN KALEM"]
        out = sc.normalize_nasil(s)
        self.assertEqual([x.step for x in out.scenes], [0, 1, 2, 3, 3, 0])
        self.assertEqual(out.scenes[1].headline, ["AŞAMA 1", "GRAFİT ÖĞÜTÜLÜR"])
        self.assertEqual(out.scenes[1].highlight_line, 1)
        self.assertEqual(out.scenes[2].headline, ["AŞAMA 2", "KİLLE KARIŞTIRILIR"])
        self.assertEqual(out.scenes[3].headline, ["AŞAMA 3", "FIRINDA PİŞİRİLİR"])
        self.assertEqual(out.scenes[4].headline, ["KURUTULUR"], "devam sahnesine numara eklenmez")
        self.assertEqual(out.scenes[-1].headline, ["4 AŞAMA", "KURŞUN KALEM"], "özet başlığı aşama sayılmaz")
        # yalnız step alanı: başlığa kalıbın kelimesi eklenir
        s = self.uretim_senaryosu()
        s.scenes[1].headline = ["GRAFİT ÖĞÜTÜLÜR"]
        self.assertEqual(sc.normalize_nasil(s).scenes[1].headline, ["AŞAMA 1", "GRAFİT ÖĞÜTÜLÜR"])
        # nasil 'ADIM' kelimesinde kalır ('AŞAMA' yazılsa da), diğer kalıplara dokunulmaz
        n = self.cay.model_copy(deep=True)
        n.scenes[1].headline = ["AŞAMA 1", "SUYU KAYNAT"]
        self.assertEqual(sc.normalize_nasil(n).scenes[1].headline, ["ADIM 1", "SUYU KAYNAT"])
        for k in ("olsaydin", "efsane"):
            e = self.uretim_senaryosu().model_copy(update={"structure": k}, deep=True)
            for x in e.scenes:
                x.step = 0
            once = e.model_dump()
            self.assertEqual(sc.normalize_nasil(e).model_dump(), once, k)
        self.assertEqual(sc.ADIM_KELIMESI, {"nasil": "ADIM", "uretim": "AŞAMA"})

    def test_uretim_sablonu_kalibi_sabitler(self):
        pl = self.pl
        kok = self.tmp / "kok"
        shutil.copytree(REPO / "templates", kok / "templates")
        uretim_sablonu(kok)
        (kok / "state").mkdir()
        self.yama(pl, "ROOT", kok)
        cagri = {}

        def generate_script(history, topic=None, templates=None, series_prev=None, allow_series=False, kart=False,
                            structure=None, adim_kartlari=False, sablon_kurali=""):
            cagri.update(structure=structure, kart=kart, templates=templates, adim_kartlari=adim_kartlari)
            return self.cay.model_copy(update={"structure": structure or "hikaye"}, deep=True)
        self.yama(pl, "generate_script", generate_script)
        self.yama(pl, "build", lambda script, out, **k: cagri.update(sablon=k["template"]) or out / "video.mp4")
        eski_etiket = os.environ.get("SERIES_LABEL")
        os.environ["SERIES_LABEL"] = "0"
        self.addCleanup(lambda: os.environ.__setitem__("SERIES_LABEL", eski_etiket) if eski_etiket is not None
                        else os.environ.pop("SERIES_LABEL", None))

        def calistir(*argv):
            eski = sys.argv
            sys.argv = ["pipeline", *argv, "--out", str(self.tmp / "out")]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    pl.main()
            finally:
                sys.argv = eski
        acik = bool((json.loads((kok / "templates" / "eslesme.json").read_text(encoding="utf-8")).get("kart") or {})
                    .get("acik"))
        for argv, beklenen in ((["--topic", "kalem", "--template", "uretim"], ("uretim", "uretim", True, acik)),
                               (["--topic", "kalem", "--structure", "uretim"], ("uretim", "isemri", True, acik)),
                               (["--topic", "kalem", "--template", "uretim", "--structure", "uretim"],
                                ("uretim", "uretim", True, acik)),
                               (["--topic", "kuyumcu", "--structure", "olsaydin"], ("olsaydin", "ajanda", False, True)),
                               (["--topic", "çay", "--structure", "nasil"], ("nasil", "nasil", True, True))):
            cagri.clear()
            calistir(*argv)
            self.assertEqual((cagri["structure"], cagri["sablon"], cagri["adim_kartlari"], cagri["kart"]), beklenen, argv)
        # şablonun kalıbıyla çelişen kalıp: Claude'a gitmeden durur
        for argv, mesaj in ((["--topic", "x", "--template", "uretim", "--structure", "nasil"], "uretim kalıbıyla"),
                            (["--topic", "x", "--template", "nasil", "--structure", "uretim"], "nasil kalıbıyla"),
                            (["--topic", "x", "--template", "uretim", "--structure", "olsaydin"], "uretim kalıbıyla")):
            cagri.clear()
            with self.assertRaises(SystemExit) as hata:
                calistir(*argv)
            self.assertIn(mesaj, str(hata.exception), argv)
            self.assertEqual(cagri, {}, argv)
        # hazır senaryo başka kalıpta: kurguya geçmez
        nasil = self.tmp / "nasil.json"
        nasil.write_text(self.cay.model_dump_json(), encoding="utf-8")
        with self.assertRaises(SystemExit) as hata:
            calistir("--script", str(nasil), "--template", "uretim", "--no-voice")
        self.assertIn("uretim kalıbındaki senaryoyla", str(hata.exception))
        self.assertNotIn("sablon", cagri)
        # Claude'un şablon listesine kart/nasil kurgu modüllü şablonlar girmez
        m = json.loads((kok / "templates" / "eslesme.json").read_text(encoding="utf-8"))
        (kok / "templates" / "eslesme.json").write_text(json.dumps(dict(m, claude_secsin=True), ensure_ascii=False),
                                                        encoding="utf-8")
        cagri.clear()
        calistir("--topic", "kalem")
        self.assertTrue(cagri["templates"])
        self.assertFalse({"kart", "nasil", "uretim"} & set(cagri["templates"]))

    # ------------------------------------------------------------ Ya sen olsaydın?
    def test_olsaydin_istemleri(self):
        sc = self.sc
        out, cagri, gunluk = self.uret(self.paralı(self.demo).model_copy(update={"structure": "olsaydin"}),
                                       konu="kuyumcu", structure="olsaydin", kart=True)
        self.assertEqual([(c[0], c[3]) for c in cagri], [("ShortScript", True), ("Review", True), ("Polished", False)])
        self.assertIn(sc.OLSAYDIN_RULES, cagri[0][1])
        self.assertIn(sc.KART_RULES, cagri[0][1])
        self.assertIn(sc.OLSAYDIN_RULES, cagri[1][1])
        self.assertIn(f"{sc.YIL} Türkiye", cagri[0][2])
        self.assertIn("- olsaydin: " + sc.STRUCTURES["olsaydin"][1], cagri[0][2])
        for parca in (f"Her rakamı {sc.YIL} Türkiye'si için", "card_lines satırlarının toplamı card_value'ya tam eşit",
                      "gelir eksi gider", sc.OLSAYDIN_YASAK, 'hesap fişi (card "receipt") yok'):
            self.assertIn(parca, cagri[1][2])
        self.assertIn(sc.EDITOR_OLSAYDIN, cagri[2][1])
        self.assertIn('UYARI hesap fişi: hesap fişi (card "receipt") yok', gunluk)
        self.assertEqual(out.structure, "olsaydin")
        # parasız gün akışında fiş istenmez (ne günlükte ne doğrulayıcıda)
        _, cagri_gun, gunluk_gun = self.uret(self.demo.model_copy(update={"structure": "olsaydin"}),
                                             konu="Elektrikçi olsaydın günün nasıl geçerdi", structure="olsaydin")
        self.assertNotIn("hesap fişi", gunluk_gun)
        self.assertNotIn('hesap fişi (card "receipt") yok', cagri_gun[1][2])
        for parca in ("Elektrikçi olsaydın günün nasıl geçerdi", "GÜN AKIŞI", 'kicker saat olur (ör. "07:30")',
                      "gün akışı konusunda para geçmiyorsa fiş yok", "uydurma ayrıntı ya da abartılı tehlike yok"):
            self.assertIn(parca, sc.OLSAYDIN_RULES)
        self.assertIn("Gün akışı anlatılıyorsa", cagri_gun[1][2])
        self.assertIn("günün nasıl geçerdi", sc.STRUCTURES["olsaydin"][1])
        self.assertIn("Elektrikçi olsaydın", self.tr.SYSTEM)
        # kart yönergesi kapalıyken de olsaydin düzeni istenir
        _, cagri, _ = self.uret(self.demo.model_copy(update={"structure": "olsaydin"}), structure="olsaydin")
        self.assertIn(sc.OLSAYDIN_RULES, cagri[0][1])
        self.assertNotIn(sc.KART_RULES, cagri[0][1])
        # yönerge içeriği
        for parca in ('card "counter"', '"1,2 MİLYON ₺", "%25", "18 AY"', 'card "receipt"', '"KALEM|TUTAR"',
                      '"KİRA +\n  DEPOZİTO|135.000 ₺"', "2-5 satır", "card_value'ya tam eşit", '"TOPLAM"',
                      f'"Tahmini · Kasım {sc.YIL}"', "Sen olsan ne yapardın? Yorumlara yaz.", "Resmî Gazete",
                      "ÇSGB ve SGK", "TÜİK", "Milli Piyango'nun resmî", "meslek odaları", "ilan sitelerinin",
                      "yaklaşık", "şehir adı", "kazanma olasılığı açıkça söylenir", "Kuyumcu olsaydın",
                      "Piyango sana çıksaydı", "Yurt\n  dışına taşınsaydın", "Bir köyde yaşamaya başlasaydın",
                      "description alanına yazma"):
            self.assertIn(parca, sc.OLSAYDIN_RULES)
        # sayaç kuralı KART_RULES'takiyle (yalnız sayı) çelişmesin: bu kalıpta açıkça onun yerine geçer
        self.assertIn("yalnız sayı", sc.KART_RULES)
        self.assertIn("genel counter kuralının yerine geçer: birim card_value'da kalır, card_label'a yazılmaz",
                      " ".join(sc.OLSAYDIN_RULES.split()))
        self.assertIn("olsaydin kalıbında birimiyle", sc.Scene.model_fields["card_value"].description)
        for yasak in ("yasa dışı ya da ruhsatsız", "kumar ve bahis", "alkol ya da tütün satışına", "kripto para, borsa, "
                      "forex", "yatırım ürünü", "saadet zinciri", "MLM", "kredi çekme tavsiyesi", "vergi kaçırma",
                      "gelirini ifşa", "garanti kazanç", "sağlık ve tıbbi", "siyasi kutuplaştırıcı"):
            self.assertIn(yasak, sc.OLSAYDIN_YASAK)
        for yer in (sc.STRUCTURES["olsaydin"][1], sc.OLSAYDIN_RULES, self.tr.SYSTEM):
            self.assertIn(sc.OLSAYDIN_YASAK, yer)
        # öneri yönergesi: üç tür karışık, somut durum adıyla
        for parca in ("YEDİ SERİDE", "Kapalıçarşı'da bir kuyumcunun bir günü ve ayda kalan para",
                      "Piyango sana\n  çıksaydı", "Yurt\n  dışına taşınsaydın ilk ay kaç lira harcardın",
                      "Bir köyde yaşamaya başlasaydın", "türlere karışık", "somut durumu adıyla"):
            self.assertIn(parca, self.tr.SYSTEM)
        self.assertNotIn("DÖRT SERİDE", self.tr.SYSTEM)
        self.assertNotIn("ALTI SERİDE", self.tr.SYSTEM)
        self.assertEqual(list(self.tr.SERILER), ["populer", "konu", "efsane", "nasil", "uretim", "olsaydin", "kitap"])
        self.assertEqual((self.tr.SERI_IKON["uretim"], self.tr.SERI_IKON["olsaydin"]), ("🏭", "💭"))
        self.assertEqual(self.tr.SERILER["uretim"], "Nasıl üretiliyor?")
        self.assertEqual(self.tr.Suggestion.model_json_schema()["properties"]["seri"]["enum"], list(self.tr.SERILER))
        self.assertLessEqual(set(self.tr.SERI_KALIP.values()), set(sc.STRUCTURES))

    def test_fis_denetimi(self):
        sc = self.sc
        S = types.SimpleNamespace
        fis = lambda deger, *satir: S(card="receipt", card_value=deger, card_lines=list(satir))  # noqa: E731
        sayac = S(card="counter", card_value="1,2 MİLYON ₺")

        def sorun(*sahneler):
            return sc.fis_sorunlari(S(scenes=list(sahneler)))
        self.assertEqual(sorun(sayac, fis("420.000 ₺", "KİRA + DEPOZİTO|135.000 ₺", "UÇAK BİLETİ|15.000 ₺",
                                          "EŞYA|270.000 ₺")), [])
        self.assertEqual(sorun(fis("800.000 ₺", "BRÜT İKRAMİYE|1.000.000 ₺", "VERGİ|-200.000 ₺")), [], "eksi kalem")
        self.assertEqual(sorun(fis("1,2 MİLYON ₺", "A|700.000 ₺", "B|480.000 ₺")), [], "yuvarlanmış toplam (±50 bin)")
        self.assertEqual(sorun(fis("48 BİN ₺", "A|30.000 ₺", "B|18.200 ₺")), [], "48 bin: ±500")
        self.assertEqual(sorun(fis("420.000 ₺", "A|135.000 ₺", "B|270.000 ₺")),
                         ["1. sahnenin fişinde satırların toplamı 405.000 ama card_value 420.000 ₺"])
        self.assertEqual(sorun(fis("1,2 MİLYON ₺", "A|700.000 ₺", "B|400.000 ₺")),
                         ["1. sahnenin fişinde satırların toplamı 1.100.000 ama card_value 1,2 MİLYON ₺"])
        self.assertEqual(sorun(sayac), ['hesap fişi (card "receipt") yok'])
        self.assertEqual(sorun(S(card="auto", narration="Sabah 07.30'da ilk arızaya gidersin.", card_value="")), [],
                         "parasız gün akışında fiş istenmez")
        for parasiz in ("Öğlen kiraz toplarsın.", "Akşam eve geç gelirsin."):
            self.assertFalse(sc.para_var(S(scenes=[S(card="auto", narration=parasiz, card_value="")])), parasiz)
        for parali in ("Kirası ayda 20 bin.", "Giderleri düşünce elde ne kalır?", "Kredi çekmen gerekir."):
            self.assertTrue(sc.para_var(S(scenes=[S(card="auto", narration=parali, card_value="")])), parali)
        self.assertEqual(sorun(S(card="auto", narration="Ayda 48 bin lira kazanırdın.", card_value="")),
                         ['hesap fişi (card "receipt") yok'])
        self.assertEqual(sorun(sayac, fis("100 ₺", "A|100 ₺")), ["2. sahnenin fişinde 1 satır var (2-5 olmalı)"])
        self.assertEqual(sorun(fis("100 ₺", "A 50 ₺", "B|50 ₺")),
                         ["1. sahnenin fiş satırı 'KALEM|TUTAR' biçiminde değil: A 50 ₺"])
        self.assertEqual(sorun(fis("TOPLAM", "A|50 ₺", "B|50 ₺")),
                         ["1. sahnenin fişinde toplam (card_value) okunamadı: 'TOPLAM'"])
        self.assertEqual(sc.tutar("1,2 milyon ₺"), (1_200_000.0, 50_000.0))
        self.assertEqual(sc.tutar("-200.000 ₺"), (-200_000.0, 0.5))
        self.assertIsNone(sc.tutar("yok"))

    def test_dil_duzeltmesi_sayilari_ve_kartlari_korur(self):
        sc = self.sc
        s = self.demo.model_copy(update={"structure": "olsaydin"}, deep=True)
        s.scenes[1].narration = "Kirası ayda yaklaşık 48 bin lira tutardı."
        s.scenes[1].card, s.scenes[1].card_value, s.scenes[1].card_label = "counter", "48 BİN ₺", "AYLIK KİRA"
        alanlar = "card_lines" in sc.Scene.model_fields
        if alanlar:
            s.scenes[2].card_lines = ["KİRA|48.000 ₺", "AİDAT|2.000 ₺"]
        duz = s.model_copy(deep=True)
        duz.scenes[1].narration = "Kirası ayda yaklaşık 48.000 lira tutardı."   # sayının yazılışı değişti
        duz.scenes[1].headline = ["48.000 LİRA"]
        duz.scenes[1].card_value = "50 BİN ₺"
        duz.scenes[3].narration = "On üç kadın, astronotlarla aynı zorlu sınavlardan geçiyor."  # sayısız düzeltme
        if alanlar:
            duz.scenes[2].card_lines = ["KİRA|50.000 ₺"]
        sistem = []
        self.yama(sc, "ask_claude", lambda prompt, schema, system, web=False: (
            sistem.append(system), sc.Polished(notes=[], fixed=duz.model_copy(deep=True)))[1])
        with contextlib.redirect_stdout(io.StringIO()) as gunluk:
            out = sc.polish_script(s)
        self.assertIn(sc.EDITOR_OLSAYDIN, sistem[-1])
        self.assertEqual(out.scenes[1].narration, "Kirası ayda yaklaşık 48 bin lira tutardı.", "sayılar korunur")
        self.assertEqual(out.scenes[1].headline, s.scenes[1].headline)
        self.assertEqual((out.scenes[1].card_value, out.scenes[1].card_label), ("48 BİN ₺", "AYLIK KİRA"))
        self.assertEqual(out.scenes[3].narration, duz.scenes[3].narration, "sayısız dil düzeltmesi geçer")
        self.assertIn("2. sahnenin sayılarını değiştirdi", gunluk.getvalue())
        if alanlar:
            self.assertEqual(out.scenes[2].card_lines, ["KİRA|48.000 ₺", "AİDAT|2.000 ₺"], "fiş satırları korunur")
        # diğer kalıplarda sayı koruması yok (önceki davranış)
        out = sc.polish_script(s.model_copy(update={"structure": "hikaye"}, deep=True))
        self.assertEqual(out.scenes[1].narration, "Kirası ayda yaklaşık 48.000 lira tutardı.")
        self.assertNotIn(sc.EDITOR_OLSAYDIN, sistem[-1])

    # ------------------------------------------------------------ açıklama: uyarı satırı ve seri etiketleri
    def paralı(self, s):
        """Demo senaryosuna para geçen bir sahne ekler (Ya sen olsaydın? para konusu)."""
        s = s.model_copy(deep=True)
        s.scenes[1].narration = "Ayda yaklaşık 48 bin lira kazanırdın."
        return s

    def olsaydin_meta(self, **kw):
        s = self.paralı(self.demo).model_copy(update={
            "structure": "olsaydin", "description": "Kuyumcu olsaydın ayda ne kalırdı? Sence değer mi?",
            "hashtags": ["kuyumcuolsaydın", "altın", "kapalıçarşı", "meslek", "bilgimakasi"], **kw})
        kredi = self.pl.images.ImageCredit(file="f", title="t", author="John Doe", license="CC BY-SA 4.0", page="p")
        return self.pl.yayin_paketi(s, "kart", [kredi], True)

    def test_olsaydin_uyarisi_her_metinde_bir_kez(self):
        P = self.P
        uyari = P.OLSAYDIN_UYARI.format(yil=_dt.date.today().year)
        if _dt.date.today().year == 2026:
            self.assertEqual(uyari, "Rakamlar 2026 Türkiye verilerine dayanan yaklaşık hesaplardır; kişiye ve şehre "
                                    "göre değişir. Yatırım tavsiyesi değildir.")
        m = self.olsaydin_meta()
        self.assertEqual(m["description"], "Kuyumcu olsaydın ayda ne kalırdı? Sence değer mi?\n\n" + uyari +
                         "\n\n#kuyumcuolsaydın #altın #kapalıçarşı #YaSenOlsaydın #bilgimakasi\n\n📷 John Doe (CC BY-SA 4.0)")
        self.assertEqual(m["hashtags"][-2:], ["YaSenOlsaydın", "bilgimakasi"])
        self.assertEqual(P.apply_disclaimer(m), m, "iki kez eklenmez")
        yt, ig, tt = P.youtube_description(m), P.instagram_caption(m), P.tiktok_caption(m)
        for ad, metin in (("youtube", yt), ("instagram", ig), ("tiktok", tt)):
            self.assertEqual(metin.count(uyari), 1, ad)
            self.assertLess(metin.index("Sence değer mi?"), metin.index(uyari), ad)      # bilgi metninden sonra
            self.assertLess(metin.index(uyari), metin.index("#kuyumcuolsaydın"), ad)     # etiketlerden önce
        # eski paket (uyarısız açıklama, üretim tarihi yok): paylaşımda eklenir, yılı bu yıl
        eski = {**m, "description": "Bilgi.\n\n#a #b\n\n📷 John Doe (CC BY-SA 4.0)"}
        eski.pop("created")
        self.assertEqual(P.apply_disclaimer(eski)["description"], f"Bilgi.\n\n{uyari}\n\n#a #b\n\n📷 John Doe (CC BY-SA 4.0)")
        for metin in (P.youtube_description(eski), P.instagram_caption(eski), P.tiktok_caption(eski)):
            self.assertEqual(metin.count(uyari), 1)
        # videonun yılı: 2025'te üretilmiş paket kendi yılını taşır, ikinci uyarı eklenmez
        y25 = {**eski, "created": "2025-12-30T10:00:00"}
        self.assertIn("Rakamlar 2025 Türkiye", P.apply_disclaimer(y25)["description"])
        self.assertEqual(P.apply_disclaimer(P.apply_disclaimer(y25)), P.apply_disclaimer(y25))
        # uzun bilgi metni kısalırken uyarı, atıf ve etiketler kalır
        uzun = {**m, "description": m["description"].replace("Sence değer mi?", "Uzun cümle 😀. " * 400)}
        for metin, sinir, olc in ((P.tiktok_caption(uzun), 2200, P._u16), (P.instagram_caption(uzun), 2152, len)):
            self.assertLessEqual(olc(metin), sinir)
            self.assertEqual(metin.count(uyari), 1)
            self.assertIn("📷 John Doe (CC BY-SA 4.0)", metin)
            self.assertTrue(metin.endswith("#bilgimakasi"))
        # parasız gün akışı ("Elektrikçi olsaydın günün nasıl geçerdi"): rakam uyarısı eklenmez
        gun = self.pl.yayin_paketi(self.demo.model_copy(update={"structure": "olsaydin", "description": "Bir gün."}),
                                   "kart", [], True)
        self.assertTrue(gun.get("rakamsiz"))
        self.assertNotIn("Yatırım tavsiyesi", gun["description"])
        self.assertNotIn("Yatırım tavsiyesi", P.tiktok_caption(gun))
        self.assertNotIn("rakamsiz", m, "para geçen videoda bayrak yok")
        # başka kalıplarda uyarı yok
        for k in ("hikaye", "efsane", "nasil", "uretim"):
            d = {**m, "structure": k, "description": "Bilgi.\n\n#a"}
            self.assertEqual(P.apply_disclaimer(d), d, k)
            self.assertNotIn("Yatırım tavsiyesi", P.tiktok_caption(d), k)

    def test_uretim_ve_olsaydin_seri_etiketleri(self):
        P = self.P
        self.assertEqual(P.SERIES_TAGS, {"efsane": "EfsaneMiGerçekMi", "nasil": "NasılYapılır",
                                         "uretim": "NasılÜretiliyor", "olsaydin": "YaSenOlsaydın",
                                         "kitap": "BirKitapBirDakika"})
        self.assertEqual(set(P.SERIES_TAGS), set(self.tr.SERI_KALIP.values()))
        meta = {"structure": "uretim", "hashtags": ["kurşunkalem", "grafit", "fabrika", "kalem", "bilgimakasi"],
                "description": "Bilgi.\n\n#kurşunkalem #grafit #fabrika #kalem #bilgimakasi"}
        m = P.apply_series_tag(meta)
        self.assertEqual(m["hashtags"], ["kurşunkalem", "grafit", "fabrika", "NasılÜretiliyor", "bilgimakasi"])
        self.assertEqual(m["description"], "Bilgi.\n\n#kurşunkalem #grafit #fabrika #NasılÜretiliyor #bilgimakasi")
        self.assertEqual(P.apply_disclaimer(m), m, "uretim videosunda uyarı yok")

    # ------------------------------------------------------------ alkollü içecek anahtarı
    def test_alkol_anahtari_kapali(self):
        sc, P = self.sc, self.P
        self.assertFalse(sc.ALKOLLU_ICECEK)
        self.assertIn("alkollü içecek tarifi (kokteyl ve içecekler alkolsüz)", sc.NASIL_YASAK)
        self.assertIn("alkolsüz kokteyl ve içecekler: mocktail, limonata, şerbet, ev yapımı soğuk kahve",
                      sc.nasil_alanlari())
        self.assertNotIn("alkollu", sc.STRUCTURES["nasil"][1], "kapalıyken alan istenmez")
        # Claude alkollü tarif yazsa da yayına gitmez
        with self.assertRaises(RuntimeError) as hata:
            self.uret(self.cay.model_copy(update={"alkollu": True}), structure="nasil")
        self.assertIn("ALKOLLU_ICECEK kapalı", str(hata.exception))
        out, _, _ = self.uret(self.cay, structure="nasil")
        self.assertFalse(out.alkollu)
        # nasil dışındaki kalıplarda alan hep false
        out, _, _ = self.uret(self.demo.model_copy(update={"structure": "efsane", "alkollu": True}), structure="efsane")
        self.assertFalse(out.alkollu)
        # açıklama: alkolsüz tarifte yaş uyarısı yok
        m = self.pl.yayin_paketi(self.cay, "kart", [], True)
        self.assertNotIn("alkollu", m)
        self.assertNotIn(P.ALKOL_UYARI, m["description"])
        self.assertNotIn(P.ALKOL_UYARI, P.tiktok_caption(m))

    def test_alkol_anahtari_acik(self):
        sc, P = self.sc, self.P
        self.assertNotIn("alkollü içecek tarifi", sc.nasil_yasak(True))
        self.assertIn("alkolü özendiren ya da aşırı tüketimi öven anlatım", sc.nasil_yasak(True))
        self.assertIn("alkollü kokteyl de olabilir", "; ".join(sc.nasil_alanlari(True)))
        self.yama(sc, "ALKOLLU_ICECEK", True)
        out, cagri, _ = self.uret(self.cay.model_copy(update={"alkollu": True}), structure="nasil")
        self.assertTrue(out.alkollu)
        self.assertIn("'alkollu' alanını true", cagri[1][2], "doğrulayıcı alanı denetler")
        m = self.pl.yayin_paketi(out, "kart", [], True)
        self.assertTrue(m["alkollu"])
        self.assertEqual(m["description"].count(P.ALKOL_UYARI), 1)
        self.assertLess(m["description"].index(P.ALKOL_UYARI), m["description"].index("#"))
        for metin in (P.youtube_description(m), P.instagram_caption(m), P.tiktok_caption(m)):
            self.assertEqual(metin.count("18 yaş altı için uygun değildir; sorumlu tüketin."), 1)
        self.assertEqual(P.apply_disclaimer(m), m)
        # anahtar dosyada açılınca bütün yönergeler (modül yüklenirken kurulur) alkollü tarife izin verir
        kok = self.tmp / "alkol"
        shutil.copytree(REPO / "shortgen", kok / "shortgen", ignore=shutil.ignore_patterns("__pycache__"))
        yol = kok / "shortgen" / "script.py"
        kaynak = yol.read_text(encoding="utf-8")
        self.assertEqual(kaynak.count("\nALKOLLU_ICECEK = False\n"), 1)
        yol.write_text(kaynak.replace("\nALKOLLU_ICECEK = False\n", "\nALKOLLU_ICECEK = True\n"), encoding="utf-8")
        eski = {ad: mod for ad, mod in sys.modules.items() if ad == "shortgen" or ad.startswith("shortgen.")}

        def geri():
            for ad in [x for x in sys.modules if x == "shortgen" or x.startswith("shortgen.")]:
                del sys.modules[ad]
            sys.modules.update(eski)
            sys.path.remove(str(kok))
        for ad in eski:
            del sys.modules[ad]
        sys.path.insert(0, str(kok))
        self.addCleanup(geri)
        import shortgen.script as sc2
        import shortgen.trends as tr2
        self.assertTrue(sc2.ALKOLLU_ICECEK)
        self.assertNotIn("alkollü içecek tarifi", sc2.NASIL_YASAK)
        self.assertIn("'alkollu' alanını true", sc2.STRUCTURES["nasil"][1])
        self.assertIn("'alkollu' alanını true", sc2.NASIL_RULES)
        self.assertIn("alkollü kokteyl de olabilir", tr2.SYSTEM)
        self.assertNotIn("alkollü içecek tarifi", tr2.SYSTEM)


class YeniSeriMesajlari(Ortak):
    """Ya sen olsaydın? uyarı satırı Telegram açıklama mesajında, panel düzenlemesinden sonra ve paylaşımda bir kez."""
    TAG = "short-20261105-180000"
    BILGI = "Kuyumcu olsaydın, vitrindeki altının çoğu senin olmazdı. Sence değer mi?"
    META = {"title": "Kuyumcu olsaydın ayda ne kalırdı?", "topic": "Kuyumcu olsaydın", "category": "ekonomi ve markalar",
            "template": "kart", "created": "2026-11-05T18:00:00", "structure": "olsaydin",
            "hashtags": ["kuyumcuolsaydın", "altın", "kapalıçarşı", "YaSenOlsaydın", "bilgimakasi"],
            "description": BILGI + "\n\n#kuyumcuolsaydın #altın #kapalıçarşı #YaSenOlsaydın #bilgimakasi"
                                   "\n\n📷 John Doe (CC BY-SA 4.0)"}

    def setUp(self):
        super().setUp()
        import shortgen.publish as P
        self.P = P
        self.uyari = P.OLSAYDIN_UYARI.format(yil=2026)

    def bildir(self, meta):
        d = Path(tempfile.mkdtemp(prefix="bildir_", dir=self.root))
        (d / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        (d / "video.mp4").write_bytes(b"x")
        with contextlib.redirect_stdout(io.StringIO()):
            self.tb.notify(d, self.TAG)
        return self.req.cagrilar[:]

    def test_aciklama_mesajinda_uyari_bir_kez(self):
        uyarili = self.P.apply_disclaimer(self.META)
        self.assertIn("\n\n" + self.uyari + "\n\n#kuyumcuolsaydın", uyarili["description"])
        for meta in (self.META, uyarili):  # eski paket (uyarısız) ve yeni paket
            self.req.cagrilar.clear()
            c = self.bildir(meta)
            metin = self.tg(c, "sendMessage")[0]["data"]["text"]
            self.assertEqual(metin, f"{self.META['title']}\n\n{self.BILGI}\n\n{self.uyari}\n\n📷 John Doe (CC BY-SA 4.0)\n\n"
                                    "#kuyumcuolsaydın #altın #kapalıçarşı #YaSenOlsaydın #bilgimakasi")

    def test_panel_duzenlemesi_uyariyi_dusurmez_ve_cogaltmaz(self):
        uyarili = self.P.apply_disclaimer(self.META)
        self.req.surumler[T] = uyarili
        # panel bilgi metnini (uyarı dahil) gösterir; kullanıcı uyarıyı silse de, olduğu gibi bıraksa da bir kez kalır
        for aciklama in ("Yeni bilgi.", f"Yeni bilgi.\n\n{self.uyari}", f"Yeni bilgi. {self.uyari}",
                         f"Yeni bilgi.\n\n{self.uyari}\n\n#benim #etiketim"):
            durum_sifirla(self.root)
            self.video_degistir(T, aciklama_message_id=55)
            self.req.cagrilar.clear()
            c = self.panel(action="edit", tag=T, title="Yeni başlık", description=aciklama)
            self.assertIn("duzenleme", self.vid(T), aciklama)
            metin = self.tg(c, "editMessageText")[0]["data"]["text"]
            self.assertEqual(metin.count(self.uyari), 1, aciklama)
            self.assertLess(metin.index("Yeni bilgi."), metin.index(self.uyari))
            self.assertLess(metin.index(self.uyari), metin.index("📷 John Doe"))
            # paylaşım: platformlara giden açıklamalarda da bir kez
            giden = self.paylas(uyarili)
            for ad, yazi in giden.items():
                self.assertEqual(yazi.count(self.uyari), 1, (aciklama, ad))
                self.assertIn("Yeni bilgi.", yazi, ad)

    def paylas(self, meta):
        """publish_due -> gerçek publish(): platform işlevleri yerine metinleri toplayan sahteler."""
        P = self.P
        self.panel(action="approve", tag=T, code="now")
        giden = {}

        def fetch_release(tag, dest):
            (dest / "video.mp4").write_bytes(b"x")
            return dest / "video.mp4", json.loads(json.dumps(meta))
        sahte = {"youtube": lambda v, m: giden.update(youtube=P.youtube_description(m)) or {"url": "y"},
                 "instagram": lambda v, m: giden.update(instagram=P.instagram_caption(m)) or {"url": "i"},
                 "tiktok": lambda v, m: giden.update(tiktok=P.tiktok_caption(m)) or {"url": "t"}}
        eski = (P.fetch_release, dict(P.PLATFORMS))
        P.fetch_release = fetch_release
        P.PLATFORMS.update(sahte)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.tb.publish_due()
        finally:
            P.fetch_release = eski[0]
            P.PLATFORMS.clear()
            P.PLATFORMS.update(eski[1])
        self.assertEqual(set(giden), {"youtube", "instagram", "tiktok"})
        return giden


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
