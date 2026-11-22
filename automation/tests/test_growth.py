import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pipeline as pl  # noqa: E402

ROWS = [
    {"at": "2026-11-08T06:37+03:00", "facebook": {"followers": 5}, "instagram": {"followers": 1053},
     "youtube": {"subscribers": 1, "views": 4126}},
    {"at": "2026-11-15T06:37+03:00", "facebook": {"followers": 6}, "instagram": {"followers": 1050},
     "youtube": {"subscribers": 4, "views": 7000}},
    {"at": "2026-11-22T06:37+03:00", "facebook": {"followers": 7}, "instagram": {"followers": 1047},
     "youtube": {"subscribers": 9, "views": 11382}, "facebook_reels": []},
]
LEARNED = {"all": [{"opening": "Safaricom asks for old phones", "reach": 129}, {"opening": "x", "reach": 3}],
           "youtube": [{"opening": "Opposition walked out of IEBC", "views": 1158}]}


class Growth(unittest.TestCase):
    def test_the_week_against_seven_days_ago_with_the_best_posts(self):
        t = pl.growth_text(ROWS, LEARNED)
        self.assertIn("last 7 days", t)
        self.assertIn("Instagram followers: 1,047 (-3)", t)
        self.assertIn("YouTube subscribers: 9 (+5)", t)
        self.assertIn("YouTube views: 11,382 (+4,382)", t)
        self.assertIn("Safaricom", t)
        self.assertIn("1158 views", t)

    def test_a_platform_with_an_error_is_left_out_and_one_line_is_not_enough(self):
        rows = [dict(ROWS[1], facebook={"error": "x"}), ROWS[2]]
        self.assertNotIn("Facebook", pl.growth_text(rows, {}))
        self.assertEqual(pl.growth_text(ROWS[:1], LEARNED), "")

    def test_sent_on_mondays_once_a_week(self):
        import datetime as dt
        with tempfile.TemporaryDirectory() as d:
            stats = Path(d) / "stats.jsonl"
            stats.write_text("\n".join(__import__("json").dumps(r) for r in ROWS), encoding="utf-8")
            sent = []
            monday = dt.datetime(2026, 11, 23, 6, 40, tzinfo=dt.timezone(dt.timedelta(hours=3)))
            with mock.patch.object(pl, "STATE", Path(d)), mock.patch.object(pl, "STATS_LOG", stats), \
                    mock.patch.object(pl, "_notify", sent.append), mock.patch.object(pl, "now", lambda: monday):
                self.assertTrue(pl.growth_note())
                self.assertFalse(pl.growth_note())   # same week
            with mock.patch.object(pl, "STATE", Path(d)), mock.patch.object(pl, "STATS_LOG", stats), \
                    mock.patch.object(pl, "_notify", sent.append), \
                    mock.patch.object(pl, "now", lambda: monday + dt.timedelta(days=1)):
                self.assertFalse(pl.growth_note())   # not a Monday
            self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()
