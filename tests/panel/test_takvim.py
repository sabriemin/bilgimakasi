"""Haftalık yayın takvimi (shortgen/takvim.py)."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shortgen import takvim as tk  # noqa: E402

TR = tk.TR


class Takvim(unittest.TestCase):
    def test_haftada_18_video(self):
        self.assertEqual(sum(len(g) for g in tk.HAFTA.values()), 18)

    def test_seri_tahmini(self):
        self.assertEqual(tk.seri_of({"structure": "nasil", "template": "kart"}), "nasil")
        self.assertEqual(tk.seri_of({"template": "uretim"}), "uretim")
        self.assertEqual(tk.seri_of({"template": "ajanda"}), "olsaydin")
        self.assertEqual(tk.seri_of({"template": "kolaj", "structure": "hikaye"}), "genel")

    def test_sonraki_bos_saat(self):
        now = dt.datetime(2026, 11, 5, 23, 0, tzinfo=TR)  # Perşembe gecesi
        self.assertEqual(tk.sonraki_saat("nasil", [], now), dt.datetime(2026, 11, 6, 11, 30, tzinfo=TR))
        dolu = [dt.datetime(2026, 11, 6, 11, 30, tzinfo=TR)]
        self.assertEqual(tk.sonraki_saat("nasil", dolu, now), dt.datetime(2026, 11, 9, 11, 30, tzinfo=TR))
        self.assertEqual(tk.sonraki_saat("uretim", [], now), dt.datetime(2026, 11, 8, 16, 30, tzinfo=TR))

    def test_kapali_saat_atlanir(self):
        now = dt.datetime(2026, 11, 10, 9, 0, tzinfo=TR)  # 10 Kasım akşamı Genel yok
        self.assertEqual(tk.sonraki_saat("genel", [], now), dt.datetime(2026, 11, 11, 18, 0, tzinfo=TR))

    def test_plan_dosyasi_tek_kaynak(self):
        # state/yayin_plani.json okunuyor ve koddaki yedek sabitlerle aynı haftayı veriyor
        p = tk.plan_oku()
        self.assertIsNotNone(p)
        yedek = {0: [("11:30", "nasil"), ("18:00", "genel"), ("21:00", "karar")],
                 1: [("13:00", "efsane"), ("18:00", "genel"), ("22:00", "kitap")],
                 2: [("16:30", "uretim"), ("18:00", "genel"), ("21:00", "karar")],
                 3: [("18:00", "genel"), ("19:30", "olsaydin")],
                 4: [("11:30", "nasil"), ("18:00", "genel"), ("21:00", "karar")],
                 5: [("13:00", "efsane"), ("19:30", "olsaydin")],
                 6: [("16:30", "uretim"), ("22:00", "kitap")]}
        self.assertEqual(p["hafta"], yedek)
        self.assertEqual(tk.HAFTA, yedek)
        self.assertIn("2026-11-10 18:00", p["kapali"])
        self.assertEqual(set(p["seri_adi"]), {"genel", "nasil", "efsane", "uretim", "olsaydin", "kitap", "karar"})
        self.assertEqual(p["sablon_seri"]["cizgi"], "karar")

    def test_plan_dosyasi_yoksa_ya_da_bozuksa_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(tk.plan_oku(Path(d) / "yok.json"))
            bozuk = Path(d) / "bozuk.json"
            bozuk.write_text('{"hafta": [{"gun": "Pazartesi", "slotlar": [{"saat": "25:00", "seri": "x"}]}]}', encoding="utf-8")
            self.assertIsNone(tk.plan_oku(bozuk))

    def test_karar_senin_ilk_bolumden_once_saat_vermez(self):
        now = dt.datetime(2026, 11, 5, 23, 0, tzinfo=TR)
        self.assertEqual(tk.sonraki_saat("karar", [], now), dt.datetime(2026, 11, 16, 21, 0, tzinfo=TR))


if __name__ == "__main__":
    unittest.main()
