"""YouTube'a yeniden yükleme: yalnız YouTube sıraya girer, diğer platformlar yeniden yüklenmez."""
import datetime as dt
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shortgen import youtube_tekrar as Y  # noqa: E402

TR = dt.timezone(dt.timedelta(hours=3))


def video(**ek):
    v = {"tag": "short-20261105-061537", "status": "yayinlandi", "title": "Kredi kartı",
         "schedule": {"youtube": "2026-11-05T10:30:00+00:00", "instagram": "2026-11-05T10:30:00+00:00",
                      "tiktok": "2026-11-05T10:30:00+00:00"},
         "platforms": {"youtube": {"status": "ok", "id": "abc"}, "instagram": {"status": "ok"},
                       "tiktok": {"status": "ok"}}}
    v.update(ek)
    return v


class Tekrar(unittest.TestCase):
    def test_yalniz_youtube(self):
        vs = [video()]
        z = dt.datetime(2026, 11, 13, 18, 0, tzinfo=TR)
        v = Y.isaretle(vs, "short-20261105-061537", z)
        self.assertEqual(v["status"], "zamanlandi")
        self.assertEqual(v["schedule"]["youtube"], "2026-11-13T18:00:00+03:00")
        self.assertEqual(v["publish_at"], "2026-11-13T18:00:00+03:00")
        self.assertNotIn("youtube", v["platforms"])
        self.assertEqual(v["youtube_onceki"], [{"status": "ok", "id": "abc"}])
        self.assertEqual(set(v["platforms"]), {"instagram", "tiktok"}, "diğerleri paylaşılmış kalır")

    def test_paylasim_islemi_yalniz_youtube_yukler(self):
        # telegram_bot paylaşım döngüsünün kuralı: ok olan platform yeniden yüklenmez
        v = Y.isaretle([video()], "short-20261105-061537", dt.datetime(2026, 11, 13, 18, 0, tzinfo=TR))
        done = {k for k, r in v["platforms"].items() if r.get("status") == "ok"}
        todo = [p for p in ("youtube", "instagram", "tiktok") if p not in done]
        self.assertEqual(todo, ["youtube"])

    def test_diger_platform_paylasilmamissa_durur(self):
        vs = [video(platforms={"youtube": {"status": "ok"}, "instagram": {"status": "ok"}, "tiktok": {"status": "hata"}})]
        with self.assertRaises(ValueError):
            Y.isaretle(vs, "short-20261105-061537", dt.datetime.now(TR))

    def test_bilinmeyen_ve_paylasilan(self):
        with self.assertRaises(ValueError):
            Y.isaretle([video()], "short-20990101-000000", dt.datetime.now(TR))
        with self.assertRaises(ValueError):
            Y.isaretle([video(status="yayinlaniyor")], "short-20261105-061537", dt.datetime.now(TR))

    def test_is_akisi(self):
        p = Path(__file__).resolve().parents[2] / ".github/workflows/youtube_tekrar.yml"
        w = yaml.safe_load(p.read_text(encoding="utf-8"))
        self.assertIn("${{ inputs.tag }}", p.read_text(encoding="utf-8"))
        self.assertNotIn("${{ inputs.tag }}\n", [l.split("run:")[-1] for l in p.read_text().splitlines() if "run:" in l])
        self.assertIn("tekrar", w["jobs"])


if __name__ == "__main__":
    unittest.main()
