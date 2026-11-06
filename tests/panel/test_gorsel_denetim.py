"""Görsel denetimi: konuya uymayan fotoğraf (ör. kedi videosunda insan) atılır, sahne çizilir."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shortgen import gorsel_denetim as G  # noqa: E402


class Denetim(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.foto = {}
        for i in range(3):
            p = self.tmp / f"f{i}.jpg"
            Image.new("RGB", (900, 600), (i * 60, 90, 90)).save(p)
            self.foto[i] = (p, f"sahne {i}: kedi yavrusu")

    def test_uymayan_reddedilir(self):
        cevap = G.Kararlar(items=[G.Karar(scene=0, uygun=True, gorulen="kedi yavrusu"),
                                  G.Karar(scene=1, uygun=False, gorulen="insan bebeği"),
                                  G.Karar(scene=2, uygun=True, gorulen="kedi")])
        with mock.patch.object(G, "ask_claude", return_value=cevap) as m:
            kotu = G.denetle(self.foto, "Bir kedinin yaşam döngüsü", self.tmp / "d")
        self.assertEqual(kotu, {1: "insan bebeği"})
        istem = m.call_args[0][0]
        self.assertIn("sahne_01.jpg", istem)
        self.assertEqual(m.call_args.kwargs["tools"], ["Read"])
        self.assertFalse((self.tmp / "d").exists(), "önizlemeler silinir")

    def test_claude_yoksa_uretim_durmaz(self):
        with mock.patch.object(G, "ask_claude", side_effect=RuntimeError("yok")):
            self.assertEqual(G.denetle(self.foto, "x", self.tmp / "d"), {})

    def test_kapali(self):
        with mock.patch.dict("os.environ", {"GORSEL_DENETIM": "0"}), mock.patch.object(G, "ask_claude") as m:
            self.assertEqual(G.denetle(self.foto, "x", self.tmp / "d"), {})
            m.assert_not_called()

    def test_istem_kurali(self):
        self.assertIn("kedi videosunda insan", G.SYSTEM)
        self.assertIn("Emin değilsen UYGUN DEĞİL", G.SYSTEM)


if __name__ == "__main__":
    unittest.main()
