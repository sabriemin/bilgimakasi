"""Örnek videoyu yayına alma testleri (ağ yok, GitHub yok, Telegram taklit):
- iş çıktısının düzeni (shortgen.ornek_yayin.klasorler): tek video kökte, Mini Belgesel bölümleri alt klasörde,
- etiketler (plan): üretim anından, bölümler sıralı ve çakışmasız, daha önce kayda alınan bölüm kendi etiketini korur,
- kayıt (kaydet): uret.yml'deki gibi onay_bekliyor kaydı ve Onayla/Reddet mesajı; seri_id ve bölüm korunur, 1. bölüm
  onaylanınca 2. bölüm kendiliğinden zamanlanır; ikinci çalıştırma yinelemez,
- örnek mesajı (telegram_bot.preview) '📥 Yayına al' düğmesi ve telegram.json; düğme basışı (oy:<run_id>) yalnız
  Sabri'den, ornek_yayinla.yml'i başlatır,
- iş akışları: ornek.yml iş çıktısına mesaj numarasını koyar, girdiler betiğe ortam değişkeniyle geçer.

    python3 tests/panel/test_ornek_yayin.py
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
from shortgen import ornek_yayin as oy  # noqa: E402
from shortgen import takvim  # noqa: E402
from shortgen import telegram_bot as tb  # noqa: E402

CHAT = "424242"
RUN = "42161338083"
WF = REPO / ".github" / "workflows"


def meta(**k) -> dict:
    m = {"title": "Kedi | Bölüm 1/2", "topic": "Bir kedinin yaşam döngüsü", "category": "hayvanlar",
         "template": "belgesel", "structure": "belgesel", "created": "2026-11-06T04:16:12",
         "description": "Mini Belgesel · Bölüm 1/2", "hashtags": [], "search_phrase": "kedi", "series_part": 1}
    m.update(k)
    return m


def klasor(kok: Path, ad: str, m: dict, mid: int | None = None) -> Path:
    d = kok / ad if ad else kok
    d.mkdir(parents=True, exist_ok=True)
    (d / "video.mp4").write_bytes(b"0")
    (d / "script.json").write_text("{}", encoding="utf-8")
    (d / "metadata.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    if mid:
        (d / oy.ONIZLEME).write_text(json.dumps({"message_id": mid}), encoding="utf-8")
    return d


def belgesel(kok: Path, mids=(31, 32)) -> None:
    """ornek.yml'in Mini Belgesel çıktısı: iki bölüm, iki alt klasör (iş çıktısında da bu düzen)."""
    for no, mid in zip((1, 2), mids):
        klasor(kok, f"2026-11-06_0415_bir-kedinin-yasam-dongusu-b{no}", meta(
            title=f"Kedi | Bölüm {no}/2", created=f"2026-11-06T04:{16 + 5 * no}:12", seri_id="202611060415-kedi",
            bolum=no, bolum_sayisi=2, series_part=no), mid)


class Temel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ornek-yayin-"))
        self.kok = self.tmp / "ornek"
        self.cagri = []
        self.gh = []
        self.dispatch_ok = True
        self.p = [mock.patch.object(tb, "VIDEOS", self.tmp / "videos.json"),
                  mock.patch.object(oy, "ROOT", self.tmp),
                  mock.patch.object(tb, "api", lambda m, **k: self.cagri.append((m, k)) or {"message_id": 900 + len(self.cagri)}),
                  mock.patch.object(tb, "_dispatch", lambda *a, **k: self.gh.append((a, k)) or self.dispatch_ok),
                  mock.patch.object(tb, "_refresh_videos", lambda: None),
                  mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": CHAT, "TG_WEBHOOK": "1"}),
                  mock.patch("builtins.print")]
        for x in self.p:
            x.start()
        os.environ.pop("GITHUB_ENV", None)

    def tearDown(self):
        for x in self.p:
            x.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def videolar(self) -> dict:
        return {v["tag"]: v for v in tb.load(tb.VIDEOS, [])}

    def tg(self, yontem):
        return [k["data"] for m, k in self.cagri if m == yontem]


# ---------------------------------------------------------------- iş çıktısı ve etiketler
class Klasorler(Temel):
    def test_tek_video_kokte(self):
        klasor(self.kok, "", meta(title="Ahtapot", structure="neden", template="kart", series_part=0))
        self.assertEqual(oy.klasorler(self.kok), [self.kok])

    def test_belgesel_bolum_sirasiyla(self):
        belgesel(self.kok)
        (self.kok / "bos").mkdir()  # metadata'sız klasör sayılmaz
        self.assertEqual([d.name[-2:] for d in oy.klasorler(self.kok)], ["b1", "b2"])
        # ad sırası bölüm sırasından farklı olsa da bölüm numarası belirler
        for d in list(self.kok.iterdir()):
            if d.name.endswith("b1"):
                d.rename(self.kok / "z-b1")
        self.assertEqual([d.name for d in oy.klasorler(self.kok)][0], "z-b1")

    def test_eksik_ve_ilgisiz(self):
        self.kok.mkdir()
        with self.assertRaises(SystemExit):
            oy.klasorler(self.kok)  # boş
        belgesel(self.kok)
        next(self.kok.glob("*-b2")).joinpath("script.json").unlink()
        with self.assertRaises(SystemExit) as e:
            oy.klasorler(self.kok)
        self.assertIn("script.json", str(e.exception))
        shutil.rmtree(self.kok)
        klasor(self.kok, "a", meta(seri_id="s1", bolum=1))
        klasor(self.kok, "b", meta(seri_id="s2", bolum=2))
        with self.assertRaises(SystemExit):
            oy.klasorler(self.kok)  # iki ayrı serinin bölümleri birlikte alınmaz


class Etiketler(Temel):
    def test_uretim_anindan_ve_sirali(self):
        belgesel(self.kok)
        p = oy.plan(oy.klasorler(self.kok), [])
        self.assertEqual([(t, y) for t, _, y in p], [("short-20261106-042112", True), ("short-20261106-042612", True)])

    def test_ayni_saniye_ve_dolu_etiket_kayar(self):
        klasor(self.kok, "a-b1", meta(seri_id="s", bolum=1, created="2026-11-06T04:16:12"))
        klasor(self.kok, "a-b2", meta(seri_id="s", bolum=2, created="2026-11-06T04:16:12"))
        dolu = [{"tag": "short-20261106-041612", "created": "x", "topic": "başka"}]
        p = oy.plan(oy.klasorler(self.kok), dolu)
        self.assertEqual([t for t, _, _ in p], ["short-20261106-041613", "short-20261106-041614"])

    def test_kayitli_bolum_etiketini_korur(self):
        belgesel(self.kok)
        b1 = oy._meta(oy.klasorler(self.kok)[0])
        kayit = [{"tag": "short-20261106-050000", "created": b1["created"], "topic": b1["topic"], "bolum": 1}]
        p = oy.plan(oy.klasorler(self.kok), kayit)
        self.assertEqual([(t, y) for t, _, y in p], [("short-20261106-050000", False), ("short-20261106-050001", True)])

    def test_hazirla_plan_ve_ortam(self):
        belgesel(self.kok)
        env = self.tmp / "env"
        with mock.patch.dict(os.environ, {"GITHUB_ENV": str(env)}):
            oy.hazirla(self.kok, RUN)
        self.assertEqual(env.read_text(), "TAG=short-20261106-042112\nYENI=2\n")
        self.assertEqual([(t, y) for t, _, y in oy.plan_oku(self.kok)],
                         [("short-20261106-042112", True), ("short-20261106-042612", True)])


# ---------------------------------------------------------------- kayıt ve onay akışı
class Kayit(Temel):
    def test_belgesel_iki_bolum_onaya_gelir_ve_bolum2_zamanlanir(self):
        belgesel(self.kok)
        oy.hazirla(self.kok, RUN)
        self.assertEqual(oy.kaydet(self.kok, RUN), ["short-20261106-042112", "short-20261106-042612"])
        vs = self.videolar()
        v1, v2 = vs["short-20261106-042112"], vs["short-20261106-042612"]
        for no, v in ((1, v1), (2, v2)):
            self.assertEqual(v["status"], "onay_bekliyor")
            self.assertEqual((v["seri_id"], v["bolum"], v["bolum_sayisi"]), ("202611060415-kedi", no, 2))
            self.assertEqual(v["template"], "belgesel")
        # normal onay mesajı: uret.yml'deki notify ile aynı düğmeler
        videolar = self.tg("sendVideo")
        self.assertEqual(len(videolar), 2)
        self.assertEqual(json.loads(videolar[0]["reply_markup"])["inline_keyboard"][0][0]["callback_data"],
                         "ok:short-20261106-042112")
        gecmis = [json.loads(x) for x in (self.tmp / "history.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(g["dir"], g["series_part"]) for g in gecmis], [(f"ornek:{RUN}", 1), (f"ornek:{RUN}", 2)])
        # ikinci çalıştırma (çift basış, yeniden deneme) yinelemez
        oy.hazirla(self.kok, RUN)
        self.assertEqual(oy.kaydet(self.kok, RUN), [])
        self.assertEqual(len(tb.load(tb.VIDEOS, [])), 2)
        # 1. bölüm 🎯 ile onaylanınca 2. bölüm serinin sıradaki belgesel saatine kendiliğinden zamanlanır
        not_ = tb._approve("short-20261106-042112", "best", CHAT, v1["telegram_message_id"])
        self.assertIn("Bölüm 2/2 de otomatik zamanlandı", not_)
        v2 = self.videolar()["short-20261106-042612"]
        self.assertEqual(v2["status"], "zamanlandi")
        t2 = dt.datetime.fromisoformat(v2["publish_at"]).astimezone(takvim.TR)
        self.assertTrue(any(s == "belgesel" and hm == f"{t2:%H:%M}" for hm, s in takvim.HAFTA.get(t2.weekday(), [])))

    def test_yarida_kalan_is_kalan_bolumden_surer(self):
        belgesel(self.kok)
        oy.hazirla(self.kok, RUN)
        gercek = tb.notify
        sayac = []

        def notify(d, tag):
            if sayac:
                raise RuntimeError("Telegram düştü")
            sayac.append(tag)
            gercek(d, tag)
        with mock.patch.object(tb, "notify", notify), self.assertRaises(RuntimeError):
            oy.kaydet(self.kok, RUN)
        self.assertEqual(list(self.videolar()), ["short-20261106-042112"])
        oy.hazirla(self.kok, RUN)  # yeniden çalışan iş: kayıtlı bölüm yeni değil
        self.assertEqual([y for _, _, y in oy.plan_oku(self.kok)], [False, True])
        self.assertEqual(oy.kaydet(self.kok, RUN), ["short-20261106-042612"])

    def test_tek_video(self):
        klasor(self.kok, "", meta(title="Ahtapot", structure="neden", template="kart", series_part=0, bolum=None))
        oy.hazirla(self.kok, RUN)
        (tag,) = oy.kaydet(self.kok, RUN)
        v = self.videolar()[tag]
        self.assertEqual(v["status"], "onay_bekliyor")
        self.assertNotIn("seri_id", v)


# ---------------------------------------------------------------- örnek mesajı ve düğme
class Dugme(Temel):
    def test_preview_dugme_ve_mesaj_numarasi(self):
        d = klasor(self.tmp / "o", "x-b1", meta())
        tb.preview(d, "not", RUN)
        (gonder,) = self.tg("sendVideo")
        self.assertEqual(json.loads(gonder["reply_markup"]),
                         {"inline_keyboard": [[{"text": "📥 Yayına al", "callback_data": f"oy:{RUN}"}]]})
        self.assertIn("Örnek video, paylaşılmayacak", gonder["caption"])
        self.assertEqual(json.loads((d / oy.ONIZLEME).read_text())["message_id"], 901)
        self.assertLessEqual(len(f"oy:{RUN}".encode()), 64)  # Telegram callback_data sınırı

    def test_preview_run_id_yoksa_dugmesiz(self):
        for rid in ("", "12; rm -rf /"):
            self.cagri.clear()
            d = klasor(self.tmp / f"o{len(rid)}", "", meta())
            tb.preview(d, "", rid)
            self.assertNotIn("reply_markup", self.tg("sendVideo")[0])
            self.assertFalse((d / oy.ONIZLEME).exists())

    def cq(self, data, kimden=CHAT):
        return {"callback_query": {"id": "q", "from": {"id": int(kimden)}, "data": data,
                                   "message": {"message_id": 31, "chat": {"id": int(CHAT)},
                                               "reply_markup": {"inline_keyboard": [[{"text": "📥 Yayına al",
                                                                                     "callback_data": data}]]}}}}

    def test_basis_yayinlama_isini_baslatir(self):
        tb.process_update(self.cq(f"oy:{RUN}"), CHAT)
        self.assertEqual(self.gh, [(("", "ornek_yayinla.yml"), {"inputs": {"run_id": RUN, "mesaj": "31"}})])
        kb = self.tg("editMessageReplyMarkup")[-1]
        self.assertEqual((kb["message_id"], json.loads(kb["reply_markup"])["inline_keyboard"][0][0]["text"]),
                         (31, "⏳ Yayına alınıyor…"))
        self.assertEqual(tb.load(tb.VIDEOS, []), [], "kaydı düğme değil yayına alma işi yazar")

    def test_yalniz_sabri(self):
        tb.process_update(self.cq(f"oy:{RUN}", kimden="999"), CHAT)
        self.assertEqual((self.gh, self.cagri), ([], []))

    def test_gecersiz_ve_baslatilamayan(self):
        for veri in ("oy:abc", "oy:", f"oy:{'1' * 30}"):
            self.cagri.clear()
            tb.process_update(self.cq(veri), CHAT)
            self.assertEqual(self.gh, [], veri)
            self.assertEqual(json.loads(self.tg("editMessageReplyMarkup")[-1]["reply_markup"])["inline_keyboard"][0][0]
                             ["callback_data"], veri, "basılan klavye geri konur")
        self.dispatch_ok = False
        self.cagri.clear()
        tb.process_update(self.cq(f"oy:{RUN}"), CHAT)
        self.assertEqual(json.loads(self.tg("editMessageReplyMarkup")[-1]["reply_markup"])["inline_keyboard"][0][0]
                         ["text"], "📥 Yayına al")
        self.assertIn("başlatılamadı", self.tg("answerCallbackQuery")[-1]["text"])

    def test_tazeleme_oy_dugmesine_dokunmaz(self):
        tb.refresh_kb(self.cq(f"oy:{RUN}"), CHAT)
        self.assertEqual(self.cagri, [])

    def test_onizleme_alindi_zaten_geri(self):
        belgesel(self.kok)
        oy.hazirla(self.kok, RUN)
        oy.onizleme(self.kok, "alindi", RUN, "31")
        kbs = self.tg("editMessageReplyMarkup")
        self.assertEqual([(k["message_id"], json.loads(k["reply_markup"])) for k in kbs],
                         [(31, {"inline_keyboard": []}), (32, {"inline_keyboard": []})])
        (m,) = self.tg("sendMessage")
        self.assertEqual(m["reply_to_message_id"], 31)
        self.assertIn("short-20261106-042112, short-20261106-042612", m["text"])
        self.cagri.clear()
        oy.onizleme(self.kok, "zaten", RUN)
        self.assertIn("zaten yayına alınmış", self.tg("sendMessage")[0]["text"])
        self.cagri.clear()
        oy.onizleme(self.kok, "geri", RUN, "77")  # iş yarım kaldı: düğme geri gelir, mesaj gönderilmez
        self.assertEqual([k["message_id"] for k in self.tg("editMessageReplyMarkup")], [31, 32, 77])
        self.assertEqual(json.loads(self.tg("editMessageReplyMarkup")[0]["reply_markup"])["inline_keyboard"][0][0]
                         ["callback_data"], f"oy:{RUN}")
        self.assertEqual(self.tg("sendMessage"), [])

    def test_onizleme_is_ciktisi_yoksa_basilan_mesaj(self):
        oy.onizleme(self.tmp / "yok", "geri", RUN, "31")
        self.assertEqual([k["message_id"] for k in self.tg("editMessageReplyMarkup")], [31])


# ---------------------------------------------------------------- iş akışları
class IsAkislari(unittest.TestCase):
    def test_ornek_yml_mesaj_numarasini_cikti_ile_saklar(self):
        y = (WF / "ornek.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", y, "örnek işi depoya yazmaz")
        self.assertLess(y.index("telegram_bot preview"), y.index("actions/upload-artifact"))
        self.assertIn("ORNEK_RUN_ID: ${{ github.run_id }}", y)
        self.assertIn("${{ runner.temp }}/ornek/*/telegram.json", y)
        self.assertIn("name: ornek-video", y)

    def test_ornek_yayinla_girdileri_ortamdan(self):
        y = (WF / "ornek_yayinla.yml").read_text(encoding="utf-8")
        # girdiler betiğe doğrudan gömülmez (yalnız env:, with: ve if: satırlarında)
        for satir in y.splitlines():
            if "${{ inputs." in satir:
                self.assertRegex(satir.strip(), r"^(RUN_ID|MESAJ|run-id|if):", satir)
        for parca in ("python -m shortgen.ornek_yayin hazirla", "python -m shortgen.ornek_yayin kaydet",
                      "name: ornek-video", 'gh release create "$T" "$D/video.mp4" "$D/metadata.json" "$D/script.json"',
                      "--prerelease", "group: ornek-yayinla", ".github/workflows/ornek.yml", "mesaj:"):
            self.assertIn(parca, y)
        self.assertNotIn("set -x", y)

    def test_kapi_oy_dugmesini_kilitler(self):
        w = (REPO / "cloudflare" / "worker.js").read_text(encoding="utf-8")
        self.assertIn('"rt", "oy"].includes(action)', w)


if __name__ == "__main__":
    unittest.main()
