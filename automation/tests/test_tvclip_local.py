"""The helper on James's computer: which posts get a TV clip, which weeks it reads (no network)."""
import datetime as dt
import os
import sys
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tvclip_local as tl  # noqa: E402

NOW = dt.datetime(2026, 11, 8, 10, 0, tzinfo=tl.EAT)
CLIP = {"url": "https://www.youtube.com/watch?v=x", "channel": "Citizen TV", "title": "Sugar prices fall"}


def post(i, **k):
    return {"id": i, "status": "approved", "publish_at": "2026-11-08T12:45:00+03:00", "tv_clip": CLIP, "beats": ["a", "b", "c"], **k}


class Helper(unittest.TestCase):
    def test_only_waiting_news_posts_with_time_left(self):
        posts = [post("a"), post("b", status="published"), post("c", tv_clip=None), post("d", tv_clip_used={"x": 1}),
                 post("e", publish_at="2026-11-08T10:20:00+03:00"), post("f"), post("g", tv_clip=None, hot=True)]
        # c: no clip and not a news post; f: already tried; g: a news post the computer will search for
        self.assertEqual([p["id"] for p in tl.wanted(posts, {"f"}, NOW)], ["a", "g"])

    def test_a_tv_title_matches_on_names_and_shared_words(self):
        p = {"message": "FKF expels McDonald Mariga and six officials after Meru chaos."}
        self.assertIn("Mariga", tl.keywords(p))
        self.assertTrue(tl.matches("Mariga na maafisa 6 wa baraza kuu la FKF watimuliwa", p))   # names work in Swahili
        self.assertFalse(tl.matches("Shabana yaizamisha Mombasa United 3-2", p))
        ebola = {"message": "Kenya has marked 18 days without a new Ebola case. All six patients recovered."}
        self.assertFalse(tl.matches("Burial of Kenya's first Ebola patient. Were protocols observed?", ebola))   # same topic, other event
        self.assertTrue(tl.matches("Ebola: all six patients recovered, 18 days without new cases", ebola))

    def test_reads_this_week_and_on_sunday_the_next(self):
        self.assertEqual(tl.week_labels(dt.datetime(2026, 11, 7, 10, tzinfo=tl.EAT)), ["2026-W45"])
        self.assertEqual(tl.week_labels(dt.datetime(2026, 11, 8, 20, tzinfo=tl.EAT)), ["2026-W45", "2026-W46"])

    def test_nothing_is_sent_without_its_keys(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"KOR_TELEGRAM_BOT_TOKEN": "", "KOR_TELEGRAM_CHAT_ID": "", "KOR_GITHUB_TOKEN": ""}):
            self.assertEqual(tl.main([]), 1)


if __name__ == "__main__":
    unittest.main()
