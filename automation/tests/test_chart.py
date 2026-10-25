"""A Reel with chart data shows the rise per fuel (computed from the data) and no third-party photo."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import render  # noqa: E402
import video  # noqa: E402


class ChartReel(unittest.TestCase):
    def test_rise_and_no_photo(self):
        with tempfile.TemporaryDirectory() as t:
            ph = Path(t) / "third-party.jpg"
            ph.write_bytes(b"x")
            post = {"id": "c1", "template": "money", "size": "story", "bg": "shuka", "series": "The Real Price",
                    "beats": ["a *b* c", "d e f", "g h i"], "photo_file": str(ph), "photo_kind": "posted",
                    "chart": [{"label": "Diesel", "old": 217.86, "new": 227.76}]}
            html = render.build_html(render.make_env(), video.beat_reel(post), motion=True)
        self.assertIn("+Sh9.90", html)
        self.assertIn("Sh217.86 to Sh227.76", html)
        self.assertNotIn("third-party.jpg", html)


if __name__ == "__main__":
    unittest.main()


class Stake(unittest.TestCase):
    def test_stake_line_is_computed_from_the_chart(self):
        chart = [{"label": "Super petrol", "old": 214.03, "new": 226.96}]
        self.assertEqual(render.stake_line(chart, 20), "A 20-litre fill-up of super petrol now costs Sh258.60 more.")
        self.assertEqual(render.stake_line(chart, None), "")
        self.assertEqual(render.stake_line([], 20), "")
        down = [{"label": "Diesel", "old": 230.0, "new": 225.0}]
        self.assertIn("Sh100.00 less", render.stake_line(down, 20))
