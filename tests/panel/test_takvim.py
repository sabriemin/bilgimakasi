"""Haftalık yayın takvimi (shortgen/takvim.py)."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shortgen import takvim as tk  # noqa: E402

TR = tk.TR


class Takvim(unittest.TestCase):
    def test_haftada_20_video(self):
        self.assertEqual(sum(len(g) for g in tk.HAFTA.values()), 20)

    def test_seri_tahmini(self):
        self.assertEqual(tk.seri_of({"structure": "nasil", "template": "kart"}), "nasil")
        self.assertEqual(tk.seri_of({"template": "uretim"}), "uretim")
        self.assertEqual(tk.seri_of({"template": "ajanda"}), "olsaydin")
        self.assertEqual(tk.seri_of({"template": "kolaj", "structure": "hikaye"}), "genel")

    def test_sonraki_bos_saat(self):
        now = dt.datetime(2026, 11, 5, 23, 0, tzinfo=TR)  # Perşembe gecesi
        self.assertEqual(tk.sonraki_saat("nasil", [], now), dt.datetime(2026, 11, 6, 12, 0, tzinfo=TR))
        dolu = [dt.datetime(2026, 11, 6, 12, 0, tzinfo=TR)]
        self.assertEqual(tk.sonraki_saat("nasil", dolu, now), dt.datetime(2026, 11, 9, 12, 0, tzinfo=TR))
        self.assertEqual(tk.sonraki_saat("uretim", [], now), dt.datetime(2026, 11, 8, 15, 30, tzinfo=TR))

    def test_kapali_saat_atlanir(self):
        now = dt.datetime(2026, 11, 10, 9, 0, tzinfo=TR)  # 10 Kasım akşamı Genel yok
        self.assertEqual(tk.sonraki_saat("genel", [], now), dt.datetime(2026, 11, 11, 17, 0, tzinfo=TR))

    def test_plan_dosyasi_tek_kaynak(self):
        # state/yayin_plani.json okunuyor ve koddaki yedek sabitlerle aynı haftayı veriyor
        p = tk.plan_oku()
        self.assertIsNotNone(p)
        yedek = {0: [("12:00", "nasil"), ("17:00", "genel"), ("21:00", "belgesel")],
                 1: [("12:00", "efsane"), ("17:00", "genel"), ("21:00", "kitap")],
                 2: [("12:00", "uretim"), ("17:00", "genel"), ("21:00", "belgesel")],
                 3: [("12:00", "koken"), ("17:00", "genel"), ("21:00", "olsaydin")],
                 4: [("12:00", "nasil"), ("17:00", "genel"), ("21:00", "belgesel")],
                 5: [("11:30", "efsane"), ("15:30", "olsaydin")],
                 6: [("11:30", "koken"), ("15:30", "uretim"), ("20:30", "kitap")]}
        self.assertEqual(p["hafta"], yedek)
        self.assertEqual(tk.HAFTA, yedek)
        self.assertIn("2026-11-10 17:00", p["kapali"])
        self.assertEqual(set(p["seri_adi"]), {"genel", "nasil", "efsane", "uretim", "olsaydin", "kitap", "belgesel", "koken"})
        self.assertEqual(p["sablon_seri"]["belgesel"], "belgesel")
        self.assertNotIn("cizgi", p["sablon_seri"])

    def test_plan_dosyasi_yoksa_ya_da_bozuksa_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(tk.plan_oku(Path(d) / "yok.json"))
            bozuk = Path(d) / "bozuk.json"
            bozuk.write_text('{"hafta": [{"gun": "Pazartesi", "slotlar": [{"saat": "25:00", "seri": "x"}]}]}', encoding="utf-8")
            self.assertIsNone(tk.plan_oku(bozuk))

    def test_belgesel_pzt_car_cum(self):
        now = dt.datetime(2026, 11, 5, 23, 0, tzinfo=TR)  # Perşembe gecesi
        self.assertEqual(tk.sonraki_saat("belgesel", [], now), dt.datetime(2026, 11, 6, 21, 0, tzinfo=TR))
        self.assertIsNone(tk.sonraki_saat("karar", [], now), "Karar Senin takvimden çıktı")

if __name__ == "__main__":
    unittest.main()
