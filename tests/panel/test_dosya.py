#!/usr/bin/env python3
"""Dava Dosyası şablonu (templates/dosya.json, shortgen/dosya.py; "Efsane mi, Gerçek mi?" serisi) testleri. Ağ yok,
ses yok (kelime süreleri voice.estimate ile, pipeline'ın --no-voice yolu gibi):

- sahne planı: açık delil numaraları (Scene.delil), numarasız eski senaryolar, yeniden numaralama ve sınır,
- yardımcılar: iddia metni, seri etiketi ve dosya numarası, hüküm,
- yerleşim: her parçanın (kapak, İDDİA fişi, delil belgeleri, etiketler, hüküm damgası, GERÇEK şeridi, SENCE? sırası,
  tutanak satırları) güvenli alanda kalması, birbirine ve Makas'a binmemesi; uzun Türkçe kelimeler; 6-10 sahne,
- senaryo modeli: yeni alanlar isteğe bağlı (eski JSON yüklenir), doğrulama ve dil düzeltmesi geçişleri korur,
- şablon kaydı: yalnız --template ile seçilir (eslesme.json değişmez), kalıbı efsane,
- uçtan uca: python -m shortgen.pipeline --script demo/dosya/cin_seddi.json --no-voice --template dosya (geçici
  kökte; depoya yazmaz).

    python -B tests/panel/test_dosya.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True

from PIL import Image, ImageDraw  # noqa: E402

from shortgen import dosya as D, kart as K, pipeline as PL, render, script as S  # noqa: E402
from shortgen.voice import estimate  # noqa: E402

DEMO = REPO / "demo" / "dosya" / "cin_seddi.json"
KART_DEMO = REPO / "demo" / "kart" / "ornek_cin_seddi.json"
BCFG = {"enabled": True, "handle": "@bilgimakasi", "intro_cut": True, "subtitle_handle": True,
        "watermark_switch_seconds": 7}
SAFE = K.SAFE
UZUN = "ÇEKOSLOVAKYALILAŞTIRAMADIKLARIMIZDANMIŞSINIZCASINA"
UZUN2 = "MUVAFFAKİYETSİZLEŞTİRİCİLEŞTİRİVEREMEYEBİLECEKLERİMİZDENMİŞSİNİZCESİNE"


def demo_dict(path: Path = DEMO) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sahneler(script: S.ShortScript, fotolar: dict | None = None, kunye: dict | None = None):
    """pipeline.build'in genel kurgu dalının kurduğu sahneler (fotoğraf indirilmez, depodaki çizimler kullanılır,
    kelime süreleri voice.estimate): (sahneler, kelimeler, meta). fotolar: {sahne: yol}, kunye: {sahne: künye}."""
    specs = []
    for i, sc in enumerate(script.scenes):
        ill = sc.illustration.strip()
        sprite = (REPO / ill[6:]) if ill.startswith("local:") else None
        img = (fotolar or {}).get(i)
        specs.append(render.SceneSpec(
            narration=sc.narration, kicker=sc.kicker, headline=list(sc.headline), highlight_line=sc.highlight_line,
            strike=list(sc.strike), theme=sc.theme, image_mode="framed" if img else "none", image=img, icon="none",
            sprite=None if img else sprite, motion="still" if sprite and not img else "none", drawn=True))
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
    for j, (spec, sc) in enumerate(zip(specs, script.scenes)):
        spec.card = sc.model_dump()
        if (kunye or {}).get(j):
            spec.card["credit"] = kunye[j]
    tcfg = json.loads((REPO / "templates" / "dosya.json").read_text(encoding="utf-8"))
    meta = {"topic": script.topic, "structure": script.structure, "title": script.title, "category": script.category,
            "sablon": tcfg, "script": script.model_dump(), "tarih": "05.11.2026"}
    return specs, words, meta


def video(script: S.ShortScript, yalniz_icerik=True, **kw):
    specs, words, meta = sahneler(script, **kw)
    return D.DosyaVideo(specs, words, meta, BCFG, yalniz_icerik=yalniz_icerik)


def alt_senaryo(sira: list[int]) -> S.ShortScript:
    """Demo senaryosunun seçilen sahneleriyle kısaltılmış hâli (6-10 sahne denemeleri)."""
    d = demo_dict()
    d["scenes"] = [d["scenes"][i] for i in sira]
    return S.ShortScript.model_validate(d)


def bas(s: str) -> str:
    """Türkçe baş harf büyük, gerisi küçük."""
    return s[:1] + K.tr_lower(s[1:])


def uzun_senaryo() -> S.ShortScript:
    """Her metin alanında çok uzun Türkçe kelimeler."""
    d = demo_dict()
    sc = d["scenes"]
    d["topic"] = f"{bas(UZUN)} insanlar uzaydan görünür mü"
    sc[0]["headline"] = [UZUN, "UZAYDAN", UZUN2]
    sc[0]["narration"] = f"{bas(UZUN)} {K.tr_lower(UZUN2)} görünmez."
    sc[1]["card_myth"] = f"{bas(UZUN)} {K.tr_lower(UZUN2)} görünür"
    sc[1]["card_fact"] = f"*{K.tr_lower(UZUN2)}* seçilemiyor"
    sc[1]["headline"] = [UZUN2]
    sc[2]["card_label"] = f"Manzara {K.tr_lower(UZUN2)} güzeldi ama {K.tr_lower(UZUN)} göremedim."
    sc[2]["card_note"] = f"{bas(UZUN)} Liwei · {K.tr_lower(UZUN2)} · 2003"
    sc[2]["narration"] = f"{bas(UZUN2)} {K.tr_lower(UZUN)} söyledi."
    sc[3]["card_label"] = UZUN2
    sc[3]["card_note"] = UZUN
    sc[3]["headline"] = [UZUN2, UZUN]
    sc[4]["headline"] = ["AMA ASIL", UZUN2]
    sc[5]["card_note"] = f"{K.tr_lower(UZUN)} {K.tr_lower(UZUN2)}"
    sc[5]["headline"] = [UZUN, UZUN2, UZUN, UZUN2]
    sc[8]["headline"] = [UZUN2, "DOĞAN", UZUN]
    sc[8]["narration"] = f"Yani {K.tr_lower(UZUN2)} {K.tr_lower(UZUN)} bir yanılgı."
    return S.ShortScript.model_validate(d)


def ns(card="auto", delil=0, narration="Kısa bir cümle.", headline=("BAŞLIK",), **kw):
    """plan() için en küçük sahne (spec.card: Scene alanlarının adlarıyla)."""
    c = {"card": card, "card_value": "", "card_label": "", "card_myth": "", "card_fact": "", "card_note": "",
         "card_lines": [], "mascot": "auto", "delil": delil}
    c.update(kw)
    return types.SimpleNamespace(card=c, headline=list(headline), narration=narration, sprite=None, image=None)


def kutu(im: Image.Image | None, x: float, y: float):
    """Katmanın saydam olmayan kısmının ekran kutusu."""
    if im is None:
        return None
    bb = im.getchannel("A").getbbox()
    return None if bb is None else (x + bb[0], y + bb[1], x + bb[2], y + bb[3])


# ---------------------------------------------------------------- sahne planı
class Plan(unittest.TestCase):
    def ozet(self, pages):
        return [(p.kind, p.scenes, p.belge, p.no) for p in pages]

    def test_demo_acik_numaralar(self):
        specs, _, _ = sahneler(S.load_script(DEMO))
        self.assertEqual(self.ozet(D.plan(specs)), [
            ("kapak", [0], "", 0), ("ozet", [1], "kayit", 0), ("delil", [2], "ifade", 1), ("delil", [3], "olcum", 2),
            ("ara", [4], "", 2), ("delil", [5], "cizim", 3), ("delil", [6], "cizim", 3), ("delil", [7], "olcum", 4),
            ("hukum", [8, 9], "", 4)])

    def test_numarasiz_eski_senaryo(self):
        """delil alanı olmayan (kart demosu) senaryo: kendi belgesi olan sahne delil olur; cümlenin ortasından başlayan
        sahne aynı delilin yeni belgesi; sondaki yazı sahneleri (en çok üç) hüküm."""
        script = S.load_script(KART_DEMO)
        self.assertFalse(any(sc.delil for sc in script.scenes))
        specs, _, _ = sahneler(script)
        self.assertEqual(self.ozet(D.plan(specs)), [
            ("kapak", [0], "", 0), ("ozet", [1], "kayit", 0), ("delil", [2], "ifade", 1), ("delil", [3], "olcum", 2),
            ("ara", [4], "", 2), ("delil", [5], "cizim", 3), ("delil", [6], "cizim", 3), ("hukum", [7, 8, 9], "", 3)])

    def test_yeniden_numaralama(self):
        specs = [ns(headline=["KANCA"]), ns("compare", card_myth="Bal bozulmaz", card_fact="Doğru"),
                 ns("quote", 5, card_label="Bir alıntı."), ns("quote", 5, card_label="İkinci alıntı."),
                 ns("text", 0), ns("counter", 9, card_value="12"), ns("text"), ns("cta")]
        self.assertEqual(self.ozet(D.plan(specs)), [
            ("kapak", [0], "", 0), ("ozet", [1], "kayit", 0), ("delil", [2], "ifade", 1),
            ("delil", [3, 4], "ifade", 1), ("delil", [5], "olcum", 2), ("hukum", [6, 7], "", 2)])

    def test_en_cok_alti_delil(self):
        specs = [ns()] + [ns("quote", k, card_label=f"Alıntı {k}.") for k in range(1, 9)] + [ns("cta")]
        pages = D.plan(specs)
        self.assertEqual([p.no for p in pages if p.kind == "delil"], [1, 2, 3, 4, 5, 6, 6, 6])
        self.assertEqual(pages[-1].scenes, [9])

    def test_hukum_en_cok_son_uc_sahne(self):
        specs = [ns(), ns("quote", 1, card_label="Alıntı.")] + [ns("text") for _ in range(5)] + [ns("cta")]
        pages = D.plan(specs)
        self.assertEqual(pages[-1].scenes, [5, 6, 7])
        self.assertEqual(pages[1].scenes, [1, 2, 3, 4], "numarasız sahneler delil sayfasında kalır")

    def test_kisa_senaryolar(self):
        self.assertEqual(self.ozet(D.plan([ns()])), [("kapak", [0], "", 0)])
        self.assertEqual(self.ozet(D.plan([ns(), ns("cta")])), [("kapak", [0], "", 0), ("hukum", [1], "", 0)])
        self.assertEqual(D.plan([]), [])

    def test_delilsiz_senaryoda_yazili_deliller(self):
        """Kendi belgesi olan sahne hiç yoksa kapaktan sonraki yazı sahneleri birer yazılı delil olur."""
        specs = [ns(), ns("text", narration="Bir."), ns("text", narration="İki."), ns("text", narration="Üç."),
                 ns("text"), ns("text"), ns("cta")]
        pages = D.plan(specs)
        self.assertEqual([(p.kind, p.belge, p.no) for p in pages],
                         [("kapak", "", 0), ("delil", "not", 1), ("delil", "not", 2), ("delil", "not", 3),
                          ("hukum", "", 3)], "hüküm en çok son üç sahne")


class Yardimcilar(unittest.TestCase):
    def test_iddia_metni(self):
        meta = {"topic": "Çin Seddi uzaydan görünür mü"}
        self.assertEqual(D.iddia_metni([ns("compare", card_myth="Çin Seddi *uzaydan* görünür.")], meta),
                         "Çin Seddi uzaydan görünür")
        self.assertEqual(D.iddia_metni([ns()], meta), "Çin Seddi uzaydan görünür")
        self.assertEqual(D.iddia_metni([ns()], {"topic": "Bal hiç bozulmaz mı?"}), "Bal hiç bozulmaz")
        self.assertEqual(D.iddia_metni([ns()], {"topic": "Akvaryum balıkları üç saniye hatırlar mıydı"}),
                         "Akvaryum balıkları üç saniye hatırlar")
        self.assertEqual(D.iddia_metni([ns(headline=["BAL", "BOZULMAZ"])], {"topic": "Bal efsanesi"}), "BAL BOZULMAZ")

    def test_seri_bilgisi(self):
        self.assertEqual(D.seri_bilgisi("EFSANE Mİ, GERÇEK Mİ? #4"), (["EFSANE Mİ,", "GERÇEK Mİ?"], 4))
        self.assertEqual(D.seri_bilgisi("efsane mi, gerçek mi? # 12"), (["EFSANE Mİ,", "GERÇEK Mİ?"], 12))
        self.assertEqual(D.seri_bilgisi(""), (["EFSANE Mİ,", "GERÇEK Mİ?"], 1), "etiket yoksa seri adı ve 01")
        self.assertEqual(D.seri_bilgisi("2. BÖLÜM"), (["2. BÖLÜM"], 1))
        self.assertEqual(S.STRUCTURES["efsane"][0], "EFSANE Mİ, GERÇEK Mİ?")

    def test_hukum(self):
        self.assertEqual(D.hukum_of([ns()], {"script": {"hukum": "GERÇEK"}}), "GERÇEK")
        self.assertEqual(D.hukum_of([ns()], {"script": {"hukum": "kısmen doğru"}}), "KISMEN DOĞRU")
        self.assertEqual(D.hukum_of([ns(), ns("compare", card_myth="a", card_fact="b")], {}), "EFSANE",
                         "compare kartı varsa EFSANE")
        self.assertEqual(D.hukum_of([ns(), ns("text")], {"script": {"hukum": ""}}), "")

    def test_dosya_numarasi_ve_tarafsiz_damga(self):
        script = alt_senaryo([0, 2, 3, 5, 8, 9])
        script.scenes[0].kicker = "EFSANE Mİ, GERÇEK Mİ? #7"
        script.hukum = ""
        v = video(script)
        self.assertEqual((v.dosya_no, v.hukum), (7, ""), "compare yok, hüküm boş: tarafsız damga")
        P = v.hukum_parts(v.pages[-1])
        self.assertIsNotNone(P["stamp"])
        self.assertEqual(v.strike_words(["ÇİN SEDDİ UZAYDAN GÖRÜNÜR"]), [], "hüküm EFSANE değilse çizik yok")


# ---------------------------------------------------------------- yerleşim
class Yerlesim(unittest.TestCase):
    """Her parçanın kırpılmadan önceki kutusu güvenli alanda; belgeler Makas'a ve tutanağa binmez."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        foto = Path(cls.tmp.name) / "foto.jpg"
        im = Image.new("RGB", (900, 640), (120, 140, 170))
        d = ImageDraw.Draw(im)
        for k in range(0, 900, 60):
            d.rectangle([k, 300 + (k % 120), k + 40, 640], fill=(80 + k % 90, 70, 60))
        im.save(foto, quality=90)
        cls.foto = foto
        cls.kunye = {"author": "Örnek Fotoğrafçı", "license": "CC BY-SA 4.0", "source": "wikimedia"}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def icinde(self, b, alan, msg):
        if b is None:
            return
        x0, y0, x1, y1 = b
        self.assertGreaterEqual(x0, alan[0] - 1, msg)
        self.assertGreaterEqual(y0, alan[1] - 1, msg)
        self.assertLessEqual(x1, alan[2] + 1, msg)
        self.assertLessEqual(y1, alan[3] + 1, msg)

    def denetle(self, v: D.DosyaVideo, ad: str):
        tut_ust = D.TUTANAK[1]
        alan = (SAFE[0], SAFE[1], SAFE[2], tut_ust)        # tutanağın üstü
        # kapak
        kap = v.pages[0]
        P = v.kapak_parts(kap)
        self.icinde(kutu(P["base"], 0, 0), alan, f"{ad}: kapak üst sırası")
        kart_kutu = kutu(P["card"], 0, 0)
        self.icinde(kart_kutu, alan, f"{ad}: İDDİA fişi")
        if "label" in P:
            im, x, y = P["label"]
            self.icinde(kutu(im, x, y), (SAFE[0], SAFE[1], SAFE[2], 1250), f"{ad}: kanca etiketi")
        if v.tags_row() is not None:
            self.icinde(kutu(v.tags_row(), 0, 1200), alan, f"{ad}: delil işaretleri sırası")
            self.assertLessEqual(kart_kutu[3], 1250, f"{ad}: İDDİA fişi işaret sırasına binmez")
        # iç sayfalar
        for pg in v.pages[1:-1]:
            base, cur, xy = v.top_row(pg)
            self.icinde(kutu(base, D.TOP[0], D.TOP[1]), alan, f"{ad}: üst sıra {pg.scenes}")
            if cur is not None:
                self.icinde(kutu(cur, *xy), alan, f"{ad}: şimdiki işaret {pg.scenes}")
            for si in pg.scenes:
                if si != pg.scenes[0] and not v.belge_of(si):
                    continue
                P = v.page_parts(pg, si)
                msg = f"{ad}: sahne {si} ({pg.kind}/{pg.belge})"
                for im, x, y in P["labels"]:
                    self.icinde(kutu(im, x, y), (SAFE[0], D.CONTENT[1], SAFE[2], D.CONTENT[3]), msg + " manşet")
                parts = [P.get("doc"), P.get("tag"), P.get("chip")]
                if P.get("dyn") is not None:
                    parts += [P["dyn"](0.0), P["dyn"](0.9), P["dyn"](1e9)]
                for part in parts:
                    if part is not None:
                        self.icinde(kutu(*part), (SAFE[0], D.CONTENT[1], SAFE[2], tut_ust - 4), msg)
                if P.get("doc") is not None:
                    b = kutu(*P["doc"])
                    if b[2] > D.MASKOT_X0:
                        self.assertLessEqual(b[3], D.DOC_Y1 + 20, msg + ": belge Makas'a binmez")
                    lab_alt = max((kutu(im, x, y)[3] for im, x, y in P["labels"]), default=0)
                    self.assertLessEqual(lab_alt, b[1] + 70, msg)
        # hüküm
        hk = v.pages[-1]
        if hk.kind == "hukum":
            P = v.hukum_parts(hk)
            msg = f"{ad}: hüküm"
            card = kutu(P["card"], 0, 0)
            self.icinde(card, (SAFE[0], SAFE[1], SAFE[2], D.STRIP_Y1 + 2), msg + " fişi")
            st = P["stamp"]
            cx, cy = P["stamp_c"]
            sb = kutu(st, cx - st.width / 2, cy - st.height / 2)
            self.icinde(sb, (SAFE[0], SAFE[1], SAFE[2], D.STRIP_Y1), msg + " damgası")
            self.assertLessEqual(sb[3], card[3] + 2, msg + ": damga fişin içinde")
            if P["strip"] is not None:
                im, x, y = P["strip"]
                # şeridin sol üstündeki GERÇEK/SONUÇ etiketi fişin alt kenarına biraz biner (damga sağda kalır)
                self.icinde(kutu(im, x, y), (SAFE[0], card[3] - 44, SAFE[2], D.STRIP_Y1 + 2), msg + " şeridi")
                self.assertGreaterEqual(P["strip_box"][1], card[3] - 2, msg + ": şerit fişin altında")
            sx, sy = P["sticker_xy"]
            stb = kutu(P["sticker"], sx, sy)
            self.icinde(stb, (SAFE[0], SAFE[1], D.MASKOT_X0 + 4, tut_ust), msg + " yorum çıkartması")
            lab = P["sence"]
            self.assertLessEqual(D.X0 + 6 + lab.w, sx, msg + ": SENCE? çıkartmaya binmez")
        # tutanak satırları
        x0, _, x1, _ = D.TUTANAK
        genislik = (x1 - 48) - (x0 + 48) - 30
        for si in range(v.n):
            a, b = v.ranges[si]
            if a >= b:
                continue
            size, lines = v.tut_lines(si, b)
            for L in lines:
                metin = " ".join(v.words[i].text for i in L)
                self.assertLessEqual(K.tw(metin, "courier", size), genislik + 1, f"{ad}: tutanak satırı {metin!r}")
        # kareler: her sayfanın girişi, ortası ve sonu, geçişler ve hükmün olayları
        ts = {0.0, 0.3, 0.9}
        for pg in v.pages:
            ts.update({pg.start + 0.05, pg.start + 0.2, pg.start + 0.45, (pg.start + pg.end) / 2, pg.end - 0.03})
        if hk.kind == "hukum":
            P = v.hukum_parts(hk)
            for k in ("land", "strip_t", "q_t", "cta_t"):
                if P.get(k) is not None:
                    ts.update({hk.start + P[k] - 0.05, hk.start + P[k] + 0.1})
        for t in sorted(ts):
            if t < 0 or t > v.scenes[-1].end:
                continue
            im = v.frame(t)
            self.icinde(kutu(im, 0, 0), SAFE, f"{ad}: kare {t:.2f}")

    def test_demo(self):
        self.denetle(video(S.load_script(DEMO)), "demo")

    def test_sahne_sayilari(self):
        for sira in ([0, 1, 2, 3, 8, 9], [0, 1, 2, 3, 4, 5, 8, 9], [0, 2, 3, 4, 5, 6, 7, 8, 9]):
            with self.subTest(n=len(sira)):
                v = video(alt_senaryo(sira))
                self.assertEqual(len(v.scenes), len(sira))
                self.assertEqual(v.pages[-1].kind, "hukum")
                self.denetle(v, f"{len(sira)} sahne")

    def test_uzun_turkce_kelimeler(self):
        self.denetle(video(uzun_senaryo()), "uzun kelimeler")

    def test_delil_torbasi_ve_kunye(self):
        """Fotoğraflı delil torbada; künye çipi kalır."""
        script = S.load_script(DEMO)
        sc = script.scenes[7]
        sc.card, sc.card_value, sc.card_label, sc.card_note = "photo", "", "", "yörüngeden çekim"
        v = video(script, fotolar={7: self.foto}, kunye={7: self.kunye})
        pg = next(p for p in v.pages if 7 in p.scenes)
        self.assertEqual((pg.kind, pg.belge, pg.no), ("delil", "torba", 4))
        P = v.page_parts(pg, 7)
        self.assertIsNotNone(P.get("chip"), "künye çipi")
        self.denetle(v, "torba")
        # kapakta fotoğraf: polaroit ve künye
        script = S.load_script(DEMO)
        v = video(script, fotolar={0: self.foto}, kunye={0: self.kunye})
        self.denetle(v, "kapak fotoğrafı")

    def test_gercek_ve_kismen(self):
        for h in ("GERÇEK", "KISMEN DOĞRU"):
            with self.subTest(h=h):
                script = S.load_script(DEMO)
                script.hukum = h
                v = video(script)
                self.assertEqual(v.hukum, h)
                self.assertEqual(v.strike_words(["ÇİN SEDDİ UZAYDAN GÖRÜNÜR"]), [])
                self.denetle(v, h)

    def test_kapak_cizigi_ve_etiket(self):
        v = video(S.load_script(DEMO))
        self.assertEqual(v.iddia, "Çin Seddi uzaydan görünür")
        lines = v.kapak_parts(v.pages[0])["lines"]
        self.assertEqual(v.strike_words(lines), [(len(lines) - 1, 0, 0)], "kancada geçmeyen kelime: GÖRÜNÜR")
        self.assertEqual(v.hook_label(), "GÖRÜNMEZ")
        self.assertEqual((v.seri, v.dosya_no, v.N), (["EFSANE Mİ,", "GERÇEK Mİ?"], 1, 4))

    def test_dis_ses_zamanlari(self):
        """Sayaç değeri söylendiğinde oturur; SENCE? soru başlarken, YORUMLARA YAZ 'Yorumlara yaz' söylenince; yorum
        çağrısı tutanağa yazılmaz."""
        v = video(S.load_script(DEMO))
        pg = next(p for p in v.pages if p.belge == "olcum")
        P = v.page_parts(pg, pg.scenes[0])
        soylenen = next(w for w in v.scenes[pg.scenes[0]].words if "21.196" in w.text)
        self.assertAlmostEqual(P["count"][1], soylenen.start - pg.start + 0.05, places=3)
        hk = v.pages[-1]
        H = v.hukum_parts(hk)
        soru = next(i for i in range(hk.a, hk.b) if v.words[i].text == "Sence")
        cagri = next(i for i in range(hk.a, hk.b) if v.words[i].text == "Yorumlara")
        self.assertAlmostEqual(H["q_t"], v.words[soru].start - 0.1 - hk.start, places=3)
        self.assertAlmostEqual(H["cta_t"], v.words[cagri].start - 0.08 - hk.start, places=3)
        self.assertLess(H["land"], H["strip_t"])
        _, lines = v.tut_lines(v.n - 1, cagri)
        self.assertNotIn(cagri, [i for L in lines for i in L])

    def test_tam_kare(self):
        """Masa ve dosyayla tam kare: boyut ve dosya kartonunun rengi (kraft değil manila)."""
        v = video(S.load_script(DEMO), yalniz_icerik=False)
        im = v.frame(1.0, grain=False)
        self.assertEqual((im.size, im.mode), ((1080, 1920), "RGB"))
        r, g, b = im.crop((300, 1560, 700, 1640)).resize((1, 1), Image.BOX).getpixel((0, 0))
        self.assertLess(abs(r - D.MANILA[0]) + abs(g - D.MANILA[1]) + abs(b - D.MANILA[2]), 45)
        self.assertNotEqual(D.MANILA, tuple(json.loads((REPO / "templates" / "uretim.json").read_text())["colors"]["light"]))


# ---------------------------------------------------------------- senaryo modeli
class Senaryo(unittest.TestCase):
    def test_eski_json_yuklenir(self):
        script = S.load_script(KART_DEMO)
        self.assertEqual(script.hukum, "")
        self.assertEqual({sc.delil for sc in script.scenes}, {0})
        schema = S.ShortScript.model_json_schema()
        self.assertNotIn("hukum", schema.get("required", []))
        self.assertNotIn("delil", schema["$defs"]["Scene"].get("required", []))

    def test_demo_senaryosu(self):
        script = S.load_script(DEMO)
        self.assertEqual((script.structure, script.hukum), ("efsane", "EFSANE"))
        self.assertTrue(6 <= len(script.scenes) <= 10)
        kelime = sum(len(sc.narration.split()) for sc in script.scenes)
        self.assertTrue(65 <= kelime <= 78, kelime)
        self.assertEqual([sc.delil for sc in script.scenes], [0, 0, 1, 2, 0, 3, 3, 4, 0, 0])
        self.assertLessEqual(len(script.scenes[1].card_myth.split()), 6)
        self.assertTrue(script.scenes[-1].narration.endswith("Yorumlara yaz."))
        for sc in script.scenes:
            self.assertEqual(sc.image_queries, [], "ağ yok: yalnız depodaki çizimler")
            if sc.illustration:
                self.assertTrue(sc.illustration.startswith("local:"))
                self.assertTrue((REPO / sc.illustration[6:]).is_file(), sc.illustration)
        metin = json.dumps(demo_dict(), ensure_ascii=False)
        self.assertNotIn("TEST", metin)
        self.assertIn("Yang Liwei", metin)

    def test_dogrulama_alanlari_korur(self):
        s = S.load_script(DEMO)
        bos = s.model_copy(deep=True)
        bos.hukum = ""
        for sc in bos.scenes:
            sc.delil = 0
        with mock.patch.object(S, "ask_claude", lambda prompt, schema, system, web=False:
                               S.Review(ok=True, problems=[], fixed=bos.model_copy(deep=True))):
            out = S.verify_script(s, keep_structure=True)
        self.assertEqual(out.hukum, "EFSANE", "doğrulayıcı alanı atlarsa yazarınki kalır")
        self.assertEqual([sc.delil for sc in out.scenes], [sc.delil for sc in s.scenes])
        degisen = s.model_copy(deep=True)
        degisen.hukum = "KISMEN DOĞRU"
        degisen.scenes[7].delil = 0
        with mock.patch.object(S, "ask_claude", lambda prompt, schema, system, web=False:
                               S.Review(ok=False, problems=["hüküm"], fixed=degisen.model_copy(deep=True))), \
                mock.patch("builtins.print"):
            out = S.verify_script(s, keep_structure=True)
        self.assertEqual(out.hukum, "KISMEN DOĞRU", "doğrulayıcı hükmü düzeltebilir")
        self.assertEqual(out.scenes[7].delil, 0, "numaraları kendisi verdiyse onunki")

    def test_dogrulayici_sahne_cikarirsa_deliller_eslenir(self):
        """Doğrulayıcı bir sahneyi çıkarıp numaraları düşürürse yazarın delilleri kart türü ve dış ses benzerliğiyle
        eşlenir, boşluksuz yeniden sıralanır; istemde delil alanını koruma ve yeniden numaralama kuralı vardır."""
        s = S.load_script(DEMO)
        kisa = s.model_copy(deep=True)
        del kisa.scenes[3]                       # 2. delil sahnesi çıkarıldı
        for sc in kisa.scenes:
            sc.delil = 0
        istem = []

        def sahte(prompt, schema, system, web=False):
            istem.append(prompt)
            return S.Review(ok=False, problems=["sahne"], fixed=kisa.model_copy(deep=True))
        with mock.patch.object(S, "ask_claude", sahte), mock.patch("builtins.print"):
            out = S.verify_script(s, keep_structure=True)
        self.assertEqual([sc.delil for sc in out.scenes], [0, 0, 1, 0, 2, 2, 3, 0, 0])
        self.assertIn("'delil' alanını koru", istem[0])

    def test_dil_duzeltmesi_alanlari_korur(self):
        s = S.load_script(DEMO)
        duz = s.model_copy(deep=True)
        duz.hukum = "GERÇEK"
        for sc in duz.scenes:
            sc.delil = 0
        duz.scenes[2].narration = "Çin'in ilk astronotu Yang Liwei bile 2003'te onu göremediğini anlattı."
        with mock.patch.object(S, "ask_claude", lambda prompt, schema, system, web=False:
                               S.Polished(notes=[], fixed=duz.model_copy(deep=True))):
            out = S.polish_script(s)
        self.assertEqual(out.hukum, "EFSANE")
        self.assertEqual([sc.delil for sc in out.scenes], [sc.delil for sc in s.scenes])
        self.assertEqual(out.scenes[2].narration, duz.scenes[2].narration, "dil düzeltmesi geçer")


# ---------------------------------------------------------------- şablon kaydı
class Sablon(unittest.TestCase):
    def test_sablon_dosyasi(self):
        t = json.loads((REPO / "templates" / "dosya.json").read_text(encoding="utf-8"))
        self.assertEqual((t["renderer"], t["yapi"]), ("dosya", "efsane"))
        self.assertTrue({"colors", "fonts", "name", "description", "istem"} <= set(t))
        for k in ("hukum", "delil", "compare", "Yorumlara yaz"):
            self.assertIn(k, t["istem"])
        self.assertEqual(PL.sablon_renderer("dosya"), "dosya")
        self.assertEqual(PL.sablon_yapisi("dosya"), "efsane")
        self.assertIn("dosya", PL.kendi_secimli(), "Claude'un şablon listesine girmez")
        self.assertTrue(callable(D.render))

    def test_kart_alanlari_bayragi(self):
        """Kart alanlarını okuyan şablon (dosya, ajanda) seçildiğinde kart yönergesi eslesme.json'daki kart
        anahtarından bağımsız olarak istenir."""
        for ad in ("dosya", "ajanda"):
            self.assertTrue(PL._sablon(ad).get("kart_alanlari"), ad)
        self.assertFalse(PL._sablon("nasil").get("kart_alanlari"))
        self.assertIn('_sablon((a.template or "").strip()).get("kart_alanlari")',
                      (REPO / "shortgen" / "pipeline.py").read_text(encoding="utf-8"))

    def test_yalniz_elle_secilir(self):
        m = json.loads((REPO / "templates" / "eslesme.json").read_text(encoding="utf-8"))
        self.assertNotIn("dosya", [v for k, v in m["yapi_sablon"].items() if not k.startswith("_")])
        self.assertNotIn("dosya", m["kategoriler"].values())
        script = S.load_script(DEMO)
        self.assertNotEqual(PL.pick_template(script, None), "dosya")
        self.assertEqual(PL.pick_template(script, "dosya"), "dosya")


# ---------------------------------------------------------------- uçtan uca
class UcUca(unittest.TestCase):
    def test_pipeline_sessiz(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg yok")
        with tempfile.TemporaryDirectory() as tmp:
            kok = Path(tmp) / "kok"
            shutil.copytree(REPO / "shortgen", kok / "shortgen", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(REPO / "templates", kok / "templates")
            shutil.copy2(REPO / "brand.json", kok / "brand.json")
            for d in ("demo/dosya", "demo/kart"):
                shutil.copytree(REPO / d, kok / d)
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            r = subprocess.run([sys.executable, "-B", "-m", "shortgen.pipeline", "--script",
                                str(kok / "demo/dosya/cin_seddi.json"), "--no-voice", "--template", "dosya",
                                "--out", str(kok / "out")], cwd=kok, env=env, capture_output=True, text=True,
                               timeout=1200)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
            self.assertIn("Şablon: dosya", r.stdout)
            self.assertIn("EFSANE Mİ, GERÇEK Mİ? #1", r.stdout)
            dirs = list((kok / "out").iterdir())
            self.assertEqual(len(dirs), 1)
            mp4 = dirs[0] / "video.mp4"
            self.assertTrue(mp4.is_file())
            self.assertEqual(json.loads((dirs[0] / "script.json").read_text(encoding="utf-8"))["hukum"], "EFSANE")
            self.assertEqual(json.loads((dirs[0] / "metadata.json").read_text(encoding="utf-8"))["template"], "dosya")
            pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height:format=duration", "-of", "json", str(mp4)],
                                capture_output=True, text=True, timeout=60)
            info = json.loads(pr.stdout)
            self.assertEqual((info["streams"][0]["width"], info["streams"][0]["height"]), (1080, 1920))
            sure = float(info["format"]["duration"])
            words = estimate(" ".join(sc.narration for sc in S.load_script(DEMO).scenes))
            self.assertAlmostEqual(sure, words[-1].end + 0.35, delta=0.6)
            kare = Path(tmp) / "kare.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.5", "-i", str(mp4), "-frames:v", "1", str(kare)],
                           check=True, timeout=60)
            r_, g_, b_ = Image.open(kare).convert("RGB").crop((300, 1560, 700, 1640)).resize((1, 1), Image.BOX) \
                .getpixel((0, 0))
            self.assertLess(abs(r_ - D.MANILA[0]) + abs(g_ - D.MANILA[1]) + abs(b_ - D.MANILA[2]), 50)
            self.assertTrue((kok / "history.jsonl").is_file())
        self.assertFalse((REPO / "out").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
