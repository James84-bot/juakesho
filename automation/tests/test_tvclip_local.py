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
    return {"id": i, "status": "approved", "publish_at": "2026-11-08T12:45:00+03:00", "tv_clip": CLIP, **k}


class Helper(unittest.TestCase):
    def test_only_waiting_news_posts_with_a_clip_and_time_left(self):
        posts = [post("a"), post("b", status="published"), post("c", tv_clip=None), post("d", tv_clip_used={"x": 1}),
                 post("e", publish_at="2026-11-08T10:20:00+03:00"), post("f")]
        self.assertEqual([p["id"] for p in tl.wanted(posts, {"f"}, NOW)], ["a"])   # f was already tried

    def test_reads_this_week_and_on_sunday_the_next(self):
        self.assertEqual(tl.week_labels(dt.datetime(2026, 11, 7, 10, tzinfo=tl.EAT)), ["2026-W45"])
        self.assertEqual(tl.week_labels(dt.datetime(2026, 11, 8, 20, tzinfo=tl.EAT)), ["2026-W45", "2026-W46"])

    def test_nothing_is_sent_without_its_keys(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"KOR_TELEGRAM_BOT_TOKEN": "", "KOR_TELEGRAM_CHAT_ID": "", "KOR_GITHUB_TOKEN": ""}):
            self.assertEqual(tl.main([]), 1)


if __name__ == "__main__":
    unittest.main()
