"""The evening Facebook digest: built only from today's published posts, once a day, in the evening window,
with the owner's one daily share link."""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
import fbdigest  # noqa: E402
import pipeline as pl  # noqa: E402
from test_pipeline import TempWeeks  # noqa: E402

EAT = dt.timezone(dt.timedelta(hours=3))
NIGHT = dt.datetime(2026, 10, 5, 21, 20, tzinfo=EAT)


def post(pid, hour, caption, **kw):
    return {"id": pid, "status": "published", "fb_id": f"page_{pid}", "publish_at": f"2026-10-05T{hour:02d}:45:00+03:00",
            "published_at": f"2026-10-05T{hour:02d}:46:00+03:00", "caption": caption, **kw}


FKF = ("FKF's special general meeting in Meru removed vice-president McDonald Mariga and six other members of its "
       "executive committee on Saturday. Police fired teargas at the venue before proceedings began.\n\n"
       "The federation cites breaches of its constitution.\n\nFair call, or a purge? Tell us below.\n\n#FKF #KenyaOnRecord")


class Digest(unittest.TestCase):
    def test_window_and_once_a_day(self):
        self.assertTrue(fbdigest.due(NIGHT, {}))
        self.assertFalse(fbdigest.due(NIGHT.replace(hour=19), {}))
        self.assertFalse(fbdigest.due(NIGHT.replace(hour=23, minute=20), {}))
        self.assertFalse(fbdigest.due(NIGHT, {"date": "2026-10-05"}))

    def test_only_todays_published_page_posts(self):
        weeks = [{"collection": "2026-W41", "posts": [
            post("a", 12, "A."), post("b", 9, "B."),
            {**post("c", 15, "C."), "status": "approved"},           # not out
            {**post("d", 15, "D."), "fb_id": None},                  # not on the Page
            {**post("e", 15, "E."), "n": 2},                         # a carousel slide
            {**post("f", 15, "F."), "published_at": "2026-10-04T15:46:00+03:00"}]}]   # yesterday
        self.assertEqual([p["id"] for p in fbdigest.today_posts(weeks, NIGHT)], ["b", "a"])

    def test_the_story_line_is_the_news_not_the_question_or_tags(self):
        line = fbdigest.story_line({"caption": FKF})
        self.assertTrue(line.startswith("FKF's special general meeting in Meru removed"))
        self.assertTrue(line.endswith("before proceedings began."))
        self.assertNotIn("#", line)
        self.assertNotIn("?", line)
        self.assertLessEqual(len(fbdigest.story_line({"caption": "word " * 200})), fbdigest.ITEM_MAX + 1)

    def test_message(self):
        text = fbdigest.message([post("a", 9, FKF), post("b", 12, "Fuel prices stay the same this month.\n\n#Fuel")],
                                NIGHT, {"name": "Kenya on Record"})
        self.assertTrue(text.startswith("Kenya today, Monday 5 October"))
        self.assertIn("▪️ Fuel prices stay the same this month.", text)
        self.assertTrue(text.rstrip().endswith("#KenyaOnRecord"))
        self.assertNotIn("1.", text)   # no numbering in content


class DigestPublish(TempWeeks):
    def setUp(self):
        super().setUp()
        self.calls, self.notes = [], []
        self.more = [mock.patch.object(pl, "now", lambda: NIGHT),
                     mock.patch.object(pl, "graph", self.fake_graph),
                     mock.patch.object(pl, "_notify", self.notes.append)]
        for m in self.more:
            m.start()

    def tearDown(self):
        for m in self.more:
            m.stop()
        super().tearDown()

    def fake_graph(self, path, fields):
        self.calls.append((path, fields))
        return {"id": "page_99" if path.endswith("/feed") else f"photo{len(self.calls)}"}

    def test_posts_the_album_once_and_sends_one_share_link(self):
        self.week([post("a", 9, FKF), post("b", 12, "Fuel prices stay the same.\n\n#Fuel")])
        text = pl.fb_digest()
        self.assertIn("▪️ FKF's special general meeting", text)
        feed = [f for p, f in self.calls if p.endswith("/feed")]
        self.assertEqual(len(feed), 1)
        self.assertEqual(sum(k.startswith("attached_media") for k in feed[0]), 2)
        self.assertTrue(all(f.get("published") == "false" for p, f in self.calls if p.endswith("/photos")))
        self.assertEqual(len(self.notes), 1)
        self.assertIn("https://www.facebook.com/page/posts/99", self.notes[0])
        self.assertIsNone(pl.fb_digest())    # not twice in a day
        self.assertEqual(len(self.notes), 1)

    def test_one_post_day_shares_that_post_and_posts_nothing_new(self):
        self.week([post("a", 9, FKF)])
        self.assertIsNone(pl.fb_digest())
        self.assertEqual(self.calls, [])
        self.assertIn("https://www.facebook.com/page/posts/a", self.notes[0])

    def test_nothing_out_today_nothing_happens(self):
        self.week([{**post("a", 9, FKF), "status": "approved"}])
        self.assertIsNone(pl.fb_digest())
        self.assertEqual((self.calls, self.notes), ([], []))
        self.assertFalse((pl.STATE / "fb_digest.json").exists())   # tries again next tick


if __name__ == "__main__":
    unittest.main()
