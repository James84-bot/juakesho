"""An alert when nothing has been posted for a long stretch (no network)."""
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


class Quiet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "weeks").mkdir()
        (d / "state").mkdir()
        self.patches = [mock.patch.object(pipeline, "WEEKS", d / "weeks"), mock.patch.object(pipeline, "STATE", d / "state")]
        for p in self.patches:
            p.start()
        self.sent = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def week(self, posts):
        (pipeline.WEEKS / "2026-W44.json").write_text(json.dumps({"posts": posts}), encoding="utf-8")

    def run_check(self, hour=12, day=31):
        return pipeline.quiet_check(dt.datetime(2026, 10, day, hour, 0, tzinfo=EAT), self.sent.append)

    def test_recent_post_means_no_alert(self):
        self.week([{"id": "a", "status": "published", "published_at": "2026-10-31T09:00:00+03:00"}])
        self.assertIsNone(self.run_check())
        self.assertEqual(self.sent, [])

    def test_a_long_silence_alerts_with_the_main_reason(self):
        self.week([{"id": "a", "status": "published", "published_at": "2026-10-27T19:58:00+03:00"},
                   {"id": "b", "status": "needs_human", "guard": {"errors": ["beats[0] is too long: max 12 words / 72 characters"]}},
                   {"id": "c", "status": "needs_human", "guard": {"errors": ["beats[0] is too long: max 12 words / 72 characters"]}}])
        msg = self.run_check()
        self.assertIn("Nothing has been posted", msg)
        self.assertIn("too long", msg)
        self.assertIn("x2", msg)
        self.assertEqual(len(self.sent), 1)

    def test_only_one_alert_per_twelve_hours_and_none_at_night(self):
        self.week([{"id": "a", "status": "published", "published_at": "2026-10-27T19:58:00+03:00"}])
        self.assertIsNotNone(self.run_check(hour=12))
        self.assertIsNone(self.run_check(hour=14))
        self.assertIsNone(self.run_check(hour=23))
        self.assertEqual(len(self.sent), 1)

    def test_night_hours_stay_quiet(self):
        self.week([{"id": "a", "status": "published", "published_at": "2026-10-27T19:58:00+03:00"}])
        self.assertIsNone(self.run_check(hour=2))
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
