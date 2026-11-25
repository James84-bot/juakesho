"""22 Nov: with the Meta token dead, every insights call failed and the empty result replaced what the writer had
learned from 54 posts. No numbers must not wipe the numbers we had."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pipeline as pl  # noqa: E402

OLD = {"updated": "2026-11-22T11:58:00+03:00", "top": [{"id": "a", "score": 9}], "bottom": [{"id": "z", "score": 1}],
       "all": [{"id": "a", "score": 9}, {"id": "z", "score": 1}], "youtube": []}


class KeepWhatWeLearned(unittest.TestCase):
    def run_learn(self, http, dead=False):
        with tempfile.TemporaryDirectory() as d:
            weeks, state = Path(d) / "weeks", Path(d) / "state"
            state.mkdir()
            (state / "learnings.json").write_text(json.dumps(OLD), encoding="utf-8")
            post = {"id": "w-1", "status": "published", "ig_id": "17", "template": "sauti", "beats": ["x"],
                    "publish_at": "2026-11-20T12:00:00+03:00"}
            with mock.patch.object(pl, "WEEKS", weeks), mock.patch.object(pl, "STATE", state), \
                    mock.patch.object(pl, "http", http), mock.patch.object(pl, "learn_youtube", lambda w: [{"id": "yt"}]), \
                    mock.patch.dict(pl.STORED_TOKEN, {"dead": dead}), mock.patch.dict(os.environ, {"META_ACCESS_TOKEN": "m"}), \
                    mock.patch.object(pl, "now", lambda: dt.datetime(2026, 11, 25, 16, 0, tzinfo=dt.timezone.utc)):
                pl.save_week({"collection": "2026-W47", "posts": [post], "scripts": {}})
                pl.learn()
                return json.loads((state / "learnings.json").read_text(encoding="utf-8"))

    def test_refused_calls_keep_the_last_numbers_and_refresh_youtube(self):
        def refused(*a, **k):
            raise RuntimeError("400: Session has expired")
        got = self.run_learn(refused)
        self.assertEqual((got["top"], got["all"], got["updated"]), (OLD["top"], OLD["all"], OLD["updated"]))
        self.assertEqual(got["youtube"], [{"id": "yt"}])

    def test_a_dead_token_asks_nothing_and_keeps_them(self):
        got = self.run_learn(lambda *a, **k: self.fail("no call with a dead token"), dead=True)
        self.assertEqual(got["all"], OLD["all"])

    def test_real_numbers_still_replace_them(self):
        def ok(method, url, *a, **k):
            return {"data": [{"name": "reach", "values": [{"value": 400}]}, {"name": "saved", "values": [{"value": 4}]}]}
        got = self.run_learn(ok)
        self.assertEqual([r["id"] for r in got["all"]], ["w-1"])


if __name__ == "__main__":
    unittest.main()
