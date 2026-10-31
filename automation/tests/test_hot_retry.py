"""A held news post is replaced by a fresh draft instead of blocking its slot (no network)."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pipeline  # noqa: E402

EAT = dt.timezone(dt.timedelta(hours=3))
NOW = dt.datetime(2026, 10, 31, 12, 0, tzinfo=EAT)


def held(pid="2026-w44-hot-1031", **extra):
    return {"id": pid, "template": "sauti", "bg": "usiku", "lane": "everyone", "hot": True, "beat": "life",
            "publish_at": "2026-10-31T12:45:00+03:00", "status": "needs_human", "message": "Old story about a crash",
            "drafted_at": "2026-10-31T09:00:00+03:00", "guard": {"errors": ["weak"]}, **extra}


class Retry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.label = "2026-W44"
        self.patches = [mock.patch.object(pipeline, "WEEKS", d), mock.patch.object(pipeline, "now", lambda: NOW)]
        for p in self.patches:
            p.start()
        self.drafts = 0

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def save(self, posts):
        (pipeline.WEEKS / f"{self.label}.json").write_text(json.dumps({"collection": self.label, "posts": posts}), encoding="utf-8")

    def load(self):
        return json.loads((pipeline.WEEKS / f"{self.label}.json").read_text(encoding="utf-8"))["posts"]

    def fake_draft(self, status):
        def run(label, mock=False, horizon=None):
            self.drafts += 1
            data = json.loads((pipeline.WEEKS / f"{label}.json").read_text(encoding="utf-8"))
            for p in data["posts"]:
                if p["status"] == "planned":
                    p["status"], p["drafted_at"], p["message"] = status, NOW.isoformat(), f"Story {p['id']}"
            (pipeline.WEEKS / f"{label}.json").write_text(json.dumps(data), encoding="utf-8")
        return run

    def test_a_held_post_is_closed_and_replaced_with_the_old_story_to_avoid(self):
        self.save([held()])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            made = pipeline.retry_held_hot(self.label)
        self.assertEqual(made, ["2026-w44-hot-1031-r2"])
        posts = {p["id"]: p for p in self.load()}
        self.assertEqual(posts["2026-w44-hot-1031"]["status"], "rejected")
        self.assertEqual(posts["2026-w44-hot-1031-r2"]["status"], "drafted")
        self.assertIn("Old story about a crash", posts["2026-w44-hot-1031-r2"]["avoid"])
        self.assertEqual(self.drafts, 1)

    def test_it_stops_after_the_retry_limit_when_every_draft_is_held(self):
        self.save([held()])
        with mock.patch.object(pipeline, "draft", self.fake_draft("needs_human")):
            made = pipeline.retry_held_hot(self.label)
        self.assertEqual(len(made), pipeline.HOT_RETRIES)
        self.assertEqual(self.drafts, pipeline.HOT_RETRIES)

    def test_breaking_posts_published_posts_and_other_days_are_left_alone(self):
        self.save([held("a", breaking={"title": "x"}), held("b", drafted_at="2026-10-30T09:00:00+03:00"),
                   {**held("c"), "status": "published"}])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            self.assertEqual(pipeline.retry_held_hot(self.label), [])
        self.assertEqual(self.drafts, 0)

    def test_a_post_already_on_its_last_attempt_is_not_retried_again(self):
        self.save([held("2026-w44-hot-1031-r3")])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            self.assertEqual(pipeline.retry_held_hot(self.label), [])

    def test_a_late_slot_is_moved_to_at_least_twenty_minutes_from_now(self):
        self.save([held(publish_at="2026-10-31T07:00:00+03:00")])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            pipeline.retry_held_hot(self.label)
        new = [p for p in self.load() if p["id"].endswith("-r2")][0]
        self.assertEqual(dt.datetime.fromisoformat(new["publish_at"]), NOW + dt.timedelta(minutes=20))


if __name__ == "__main__":
    unittest.main()
