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


if __name__ == "__main__":
    unittest.main()
