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

    def run_audit(self, verdicts, fits=None):
        fits = fits or {}
        with mock.patch.object(posted, "_photo_of", lambda item, check=True: (item["link"].encode(), {})), \
                mock.patch.object(picture, "outlet_edit", lambda data: verdicts[data.decode().rsplit("/", 1)[1]]), \
                mock.patch.object(picture, "fits", lambda data, about: fits.get(data.decode().rsplit("/", 1)[1], "")):
            return pl.photo_audit()

    def test_a_picture_that_does_not_fit_the_story_gets_new_photos(self):   # 22 Nov: armed fighters on a SHA post
        weeks = self.run_audit({"2026-w46-d1-money": "", "2026-w46-d2-clean": ""},
                               {"2026-w46-d1-money": "armed fighters, not this story"})
        self.assertEqual(weeks, ["2026-W46"])
        posts = {p["id"]: p for p in pl.load_week("2026-W46")["posts"]}
        self.assertEqual(posts["2026-w46-d1-money-r2"]["rephoto_reason"],
                         "a picture that does not fit (armed fighters, not this story)")
        self.assertNotIn("photo_fit", posts["2026-w46-d1-money-r2"])
        self.assertTrue(posts["2026-w46-d2-clean"]["photo_fit"])

    def test_a_post_checked_for_graphics_before_is_still_checked_for_fit(self):
        data = pl.load_week("2026-W46")
        for p in data["posts"]:
            p["photo_checked"] = "2026-11-22T09:21:55+03:00"
        pl.save_week(data)
        weeks = self.run_audit({}, {"2026-w46-d2-clean": "lawyers protesting, not a concert"})
        self.assertEqual(weeks, ["2026-W46"])   # outlet_edit was not asked again (the dict above is empty)

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
        p = post("a", guard={"errors": [], "warnings": ["possible named person(s): Jane Doe. Civic posts target systems"]})
        text = self.line(p)
        self.assertIn("post it", text)
        self.assertIn("may name a person", text)

    def test_your_approval_carries_over_a_new_photo(self):
        p = post("a", hot=True, beat="politics", words_approved=True)
        self.assertEqual(pl.auto_ok(p), "")
        self.assertEqual(pl.auto_ok({**p, "photo_kind": "file"}), "")
        self.assertEqual(pl.auto_ok({**p, "photo_kind": "file", "message": "The MP was charged with fraud."}),
                         "a face beside an allegation")

    def test_card_shows_the_call_and_the_new_photo_reason(self):
        p = post("a", status="rendered", rephoto_reason="Kenyans.co.ke's own edit (Two photos joined)")
        with mock.patch.object(pl, "auto_approve_on", lambda: True):
            text = pl._preview_text(p)
        self.assertTrue(text.startswith("🤖"))
        self.assertIn("New photo, same words: the old one was Kenyans.co.ke&#x27;s own edit", text)


if __name__ == "__main__":
    unittest.main()


class Takedown(unittest.TestCase):
    """22 Nov: "pull down all the posts with wrong details". Removed everywhere, kept in the record."""

    def test_a_published_post_comes_down_everywhere_and_the_record_says_what_happened(self):
        import youtube
        with tempfile.TemporaryDirectory() as d:
            calls, sent = [], []

            def http(method, url, fields=None, files=None, timeout=60):
                calls.append((method, url.split("?")[0].rsplit("/", 1)[1]))
                if "ig-1" in url:
                    raise RuntimeError("HTTP 403 (#10) Application does not have permission")
                return {"success": True}
            with mock.patch.object(pl, "WEEKS", Path(d)), mock.patch.object(pl, "log", lambda *a: None), \
                    mock.patch.object(pl, "http", http), mock.patch.object(pl, "_notify", sent.append), \
                    mock.patch.object(youtube, "delete", lambda vid: calls.append(("DELETE", vid))):
                pl.save_week({"collection": "2026-W47", "scripts": {}, "posts": [
                    post("2026-w47-hot-1122m", status="published", ig_id="ig-1", story_id="st-1", fb_id="fb-1",
                         fb_story_id="fbs-1", yt_id="yt-1")]})
                done = pl.takedown("2026-w47-hot-1122m", "armed fighters on a SHA story")
                saved = pl.load_week("2026-W47")["posts"][0]
            self.assertEqual(sorted(c[1] for c in calls), ["fb-1", "fbs-1", "ig-1", "st-1", "yt-1"])
            self.assertTrue(done["Instagram"].startswith("not removed"))
            self.assertEqual(done["YouTube"], "removed")
            self.assertEqual(saved["status"], "removed")
            self.assertEqual(saved["removed_why"], "armed fighters on a SHA story")
            self.assertIn("Still up, remove by hand: Instagram", sent[0])

    def test_a_removed_post_is_retried_only_where_it_failed(self):
        import youtube
        with tempfile.TemporaryDirectory() as d:
            calls, sent = [], []

            def http(method, url, fields=None, files=None, timeout=60):
                calls.append((method, url.split("?")[0].rsplit("/", 1)[1]))
                return {"success": True}
            with mock.patch.object(pl, "WEEKS", Path(d)), mock.patch.object(pl, "log", lambda *a: None), \
                    mock.patch.object(pl, "http", http), mock.patch.object(pl, "_notify", sent.append), \
                    mock.patch.object(youtube, "delete", lambda vid: calls.append(("DELETE", vid))):
                pl.save_week({"collection": "2026-W47", "scripts": {}, "posts": [
                    post("2026-w47-hot-1122m", status="removed", ig_id="ig-1", fb_id="fb-1", yt_id="yt-1",
                         removed_why="armed fighters", removed_at="2026-11-22T13:40:00+03:00",
                         removed={"Instagram": "not removed: (#10)", "Facebook": "removed", "YouTube": "removed"})]})
                done = pl.takedown("2026-w47-hot-1122m", "armed fighters")
                saved = pl.load_week("2026-W47")["posts"][0]
            self.assertEqual(calls, [("DELETE", "ig-1")])   # Facebook and YouTube are not touched again
            self.assertEqual(done, {"Instagram": "removed"})
            self.assertEqual(saved["removed"], {"Instagram": "removed", "Facebook": "removed", "YouTube": "removed"})
            self.assertEqual(saved["removed_at"], "2026-11-22T13:40:00+03:00")

    def test_only_a_published_post(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pl, "WEEKS", Path(d)):
            pl.save_week({"collection": "2026-W47", "scripts": {}, "posts": [post("2026-w47-x", status="approved")]})
            with self.assertRaises(SystemExit):
                pl.takedown("2026-w47-x", "x")
