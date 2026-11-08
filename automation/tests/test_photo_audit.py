"""Posts not yet out are checked once for an outlet's own graphic; one that has it gets new photos (same words), and
the card says why. Every card carries the system's own call and its reason."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import picture  # noqa: E402
import pipeline as pl  # noqa: E402
import posted  # noqa: E402

LATER = (dt.datetime.now(pl.EAT) + dt.timedelta(hours=10)).isoformat()


def post(pid, status="approved", **kw):
    return {"id": pid, "template": "money", "status": status, "publish_at": LATER, "photo_query": "fuel pump Nairobi",
            "photo_kind": "posted", "photo_outlet": "Kenyans.co.ke", "photo_file": "/x.jpg",
            "photo_source": f"https://www.kenyans.co.ke/news/{pid}", "critic": {"avg": 8.3},
            "guard": {"errors": [], "warnings": []}, "source_links": [{"outlet": "Kenyans.co.ke", "link": "https://k"}], **kw}


class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.weeks = Path(self.tmp.name)
        self.p = [mock.patch.object(pl, "WEEKS", self.weeks), mock.patch.object(pl, "log", lambda *a: None),
                  mock.patch.object(posted, "feed_items", lambda: [])]
        for x in self.p:
            x.start()
        pl.save_week({"collection": "2026-W46", "created": LATER, "scripts": {},
                      "posts": [post("2026-w46-d1-money"), post("2026-w46-d2-clean"),
                                post("2026-w46-d3-out", status="published")]})

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def run_audit(self, verdicts):
        with mock.patch.object(posted, "_photo_of", lambda item, check=True: (item["link"].encode(), {})), \
                mock.patch.object(picture, "outlet_edit", lambda data: verdicts[data.decode().rsplit("/", 1)[1]]):
            return pl.photo_audit()

    def test_a_graphic_gets_new_photos_and_the_reason(self):
        weeks = self.run_audit({"2026-w46-d1-money": "Two photos joined side by side.", "2026-w46-d2-clean": ""})
        self.assertEqual(weeks, ["2026-W46"])
        posts = {p["id"]: p for p in pl.load_week("2026-W46")["posts"]}
        new = posts["2026-w46-d1-money-r2"]
        self.assertEqual(new["status"], "drafted")
        self.assertEqual(new["rephoto_reason"], "Kenyans.co.ke's own edit (Two photos joined side by side)")
        self.assertTrue(new["words_approved"])                       # you approved the words; only the picture changes
        self.assertNotIn("photo_file", new)
        self.assertTrue(posts["2026-w46-d2-clean"]["photo_checked"])  # checked once, never fetched again
        self.assertNotIn("photo_checked", posts["2026-w46-d3-out"])   # already out: left alone

    def test_a_picture_nobody_could_judge_is_tried_again(self):
        self.run_audit({"2026-w46-d1-money": None, "2026-w46-d2-clean": None})
        posts = {p["id"]: p for p in pl.load_week("2026-W46")["posts"]}
        self.assertNotIn("photo_checked", posts["2026-w46-d1-money"])
        self.assertEqual(posts["2026-w46-d1-money"]["status"], "approved")


class Decision(unittest.TestCase):
    def line(self, p, auto=True):
        with mock.patch.object(pl, "auto_approve_on", lambda: auto):
            return pl.decision_line(p)

    def test_goes_out_by_itself(self):
        self.assertIn("goes out by itself", self.line(post("a", status="rendered")))

    def test_failed_checks_say_no(self):
        self.assertIn("don't post", self.line(post("a", guard={"errors": ["closer: x"], "warnings": []})))

    def test_waiting_post_says_why(self):
        p = post("a", hot=True, beat="politics")
        text = self.line(p)
        self.assertIn("post it", text)
        self.assertIn("a political story", text)

    def test_your_approval_carries_over_a_new_photo(self):
        p = post("a", hot=True, beat="politics", words_approved=True)
        self.assertEqual(pl.auto_ok(p), "")
        self.assertEqual(pl.auto_ok({**p, "photo_kind": "file"}), "uses a named person's portrait")

    def test_card_shows_the_call_and_the_new_photo_reason(self):
        p = post("a", status="rendered", rephoto_reason="Kenyans.co.ke's own edit (Two photos joined)")
        with mock.patch.object(pl, "auto_approve_on", lambda: True):
            text = pl._preview_text(p)
        self.assertTrue(text.startswith("🤖"))
        self.assertIn("New photo, same words: the old one was Kenyans.co.ke&#x27;s own edit", text)


if __name__ == "__main__":
    unittest.main()
