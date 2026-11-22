import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tvclip_queue as q  # noqa: E402

GOOD = {"post": "2026-w47-hot-1122a", "file_id": "BAACAgQAAxkDAAIB", "channel": "Citizen TV",
        "url": "https://www.youtube.com/watch?v=abc", "title": "CAF picks Nairobi", "message_id": 812}


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "tvclips"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_clip_is_kept_with_only_the_fields_the_work_reads(self):
        got = q.clean({**GOOD, "extra": "x"})
        self.assertEqual(got, {**{k: GOOD[k] for k in GOOD}, "sample": False})

    def test_anything_from_outside_that_could_misfire_is_refused(self):
        for bad in ({**GOOD, "post": "../../weeks/x"}, {**GOOD, "post": ""}, {**GOOD, "file_id": "short"},
                    {**GOOD, "file_id": "has spaces in it ok"}, {**GOOD, "url": "https://evil.test/watch?v=1"},
                    {**GOOD, "url": "javascript:alert(1)"}, "not an object"):
            with self.assertRaises(ValueError, msg=str(bad)[:60]):
                q.clean(bad)

    def test_loose_fields_are_tidied_not_trusted(self):
        got = q.clean({**GOOD, "channel": "KTN <b>News</b>;rm", "message_id": "77", "sample": "yes", "title": "t" * 900})
        self.assertEqual((got["channel"], got["message_id"], got["sample"], len(got["title"])), ("KTN bNewsbrm", 77, False, 300))
        self.assertIsNone(q.clean({**GOOD, "message_id": True})["message_id"])   # a bool is not a message id
        self.assertEqual(q.clean({**GOOD, "url": ""})["url"], "")                 # no link is fine: the clip is the file

    def test_one_file_per_clip_and_none_is_overwritten(self):
        at = dt.datetime(2026, 11, 22, 10, 50, 1, tzinfo=dt.timezone.utc)
        a = q.add(GOOD, now=at, folder=self.dir)
        b = q.add({**GOOD, "file_id": "BAACAgQAAxkDAAIC"}, now=at, folder=self.dir)
        self.assertEqual([p.name for p in q.pending(self.dir)], [a.name, b.name])
        self.assertEqual(json.loads(a.read_text())["file_id"], "BAACAgQAAxkDAAIB")
        self.assertEqual(json.loads(b.read_text())["queued_at"], "2026-11-22T10:50:01+00:00")
        self.assertEqual(json.loads(b.read_text())["tries"], 0)

    def test_the_oldest_clip_comes_first(self):
        q.add(GOOD, now=dt.datetime(2026, 11, 22, 11, 0, tzinfo=dt.timezone.utc), folder=self.dir)
        q.add({**GOOD, "post": "2026-w47-hot-1122"}, now=dt.datetime(2026, 11, 22, 9, 0, tzinfo=dt.timezone.utc),
              folder=self.dir)
        self.assertTrue(q.pending(self.dir)[0].name.startswith("20261122T090000"))
        self.assertEqual(q.pending(Path(self.tmp.name) / "missing"), [])

    def test_a_refused_payload_writes_nothing_and_does_not_fail_the_run(self):
        with mock.patch.object(q, "DIR", self.dir), mock.patch.dict(os.environ, {"PAYLOAD": '{"post": "x"}'}):
            self.assertEqual(q.main(), 0)
        self.assertEqual(q.pending(self.dir), [])
        with mock.patch.object(q, "DIR", self.dir), mock.patch.dict(os.environ, {"PAYLOAD": json.dumps(GOOD)}):
            self.assertEqual(q.main(), 0)
        self.assertEqual(len(q.pending(self.dir)), 1)


if __name__ == "__main__":
    unittest.main()
