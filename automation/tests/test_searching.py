"""'What Kenya is searching': the nightly Story from Google Trends Kenya (searching.py)."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402
import render  # noqa: E402
import searching  # noqa: E402

ITEMS = [
    {"title": "leeds vs spurs", "traffic": "50000+", "news": [{"title": "Leeds hold Tottenham", "url": "https://a/1", "source": "Sky"}]},
    {"title": "nottm forest vs man city", "traffic": "100K+", "news": [{"title": "Forest 1-2 City", "url": "https://a/2", "source": "BBC"}]},
    {"title": "mp arrested", "traffic": "90000+", "news": [{"title": "MP arrested over fraud claims", "url": "https://a/3", "source": "Star"}]},
    {"title": "kmtc intake", "traffic": "5,000+", "news": []},
    {"title": "state house nairobi", "traffic": "2k+", "news": [{"title": "Ruto hosts governors", "url": "https://a/4", "source": "KBC"}]},
]


class Picking(unittest.TestCase):
    def test_biggest_first_with_news_behind_them_and_nothing_unsafe(self):
        rows = searching.pick(ITEMS)
        self.assertEqual([r["query"] for r in rows], ["nottm forest vs man city", "leeds vs spurs", "state house nairobi"])
        self.assertEqual([r["label"] for r in rows], ["100K+", "50K+", "2K+"])

    def test_traffic_reads_every_way_google_writes_it(self):
        self.assertEqual([searching.traffic(x) for x in ("50K+", "50,000+", "2k+", "1.5M+", "")], [50000, 50000, 2000, 1500000, 0])
        self.assertEqual(searching.short(2_500_000), "2.5M+")


class ThePost(unittest.TestCase):
    def test_a_story_that_passes_the_guard_and_names_its_sources(self):
        at = dt.datetime(2026, 11, 22, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))
        post = searching.post_for(searching.pick(ITEMS), "2026-W47", at, at + dt.timedelta(minutes=30))
        self.assertEqual((post["id"], post["size"], post["day"]), ("2026-w47-searching-1122", "story", "Sunday 22 November"))
        self.assertEqual(len(post["source_links"]), 3)
        self.assertEqual(guard.check(post).errors, [])

    def test_a_search_reads_as_a_headline(self):
        self.assertEqual(render.headline_case("nottm forest vs man city"), "Nottm Forest vs Man City")
        self.assertEqual(render.headline_case("the KMTC intake"), "The KMTC Intake")

    def test_it_may_go_out_by_itself(self):
        import pipeline as pl
        post = {"template": "searching", "hand": True, "source_links": [{"link": "https://a/1"}],
                "guard": {"errors": [], "warnings": []}}
        self.assertEqual(pl.auto_ok(post), "")


if __name__ == "__main__":
    unittest.main()
