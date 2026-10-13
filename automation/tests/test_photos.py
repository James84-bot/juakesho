"""Photo sources: licence and place filters, and the civic fallback (no network)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):   # AI keys never reach the tests: no real calls, no spend
    os.environ.pop(_k, None)
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import posted as _posted  # noqa: E402
_posted.feed_items = lambda: []   # tests never read live news feeds

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import photos  # noqa: E402

HIT = {"title": "Matatu in Nairobi", "tags": [{"name": "kenya"}], "license": "by", "license_version": "2.0",
       "creator": "Joe", "source": "flickr", "url": "https://x/a.jpg", "foreign_landing_url": "https://f/x",
       "width": 2000, "height": 1500}


class Photos(unittest.TestCase):
    def test_openverse_keeps_only_credited_licences_from_the_place(self):
        fake = {"results": [{**HIT, "title": "Bus in London", "tags": []}, {**HIT, "license": "by-sa"},
                            {**HIT, "license": "by-nc"}, HIT]}
        with mock.patch.object(photos, "_get", lambda u, h=None, timeout=30: json.dumps(fake).encode() if "openverse" in u else b"IMG"), \
                mock.patch.object(photos, "faces_ok", lambda data: True):
            data, meta = photos.openverse("matatu Nairobi", "p1")
        self.assertEqual(meta["credit"], "Photo: Joe / Flickr, CC BY 2.0")

    def test_civic_post_falls_back_to_a_real_kenyan_symbol(self):
        seen = []

        def commons(q, pid):
            seen.append(q)
            return (b"IMG", {"credit": "Photo: X / Wikimedia Commons, CC BY 4.0", "url": ""}) if q == photos.CIVIC_FALLBACK[0] else None
        with tempfile.TemporaryDirectory() as d, mock.patch.object(photos, "commons", commons), \
                mock.patch.object(photos, "openverse", lambda q, p: None), mock.patch.object(photos, "pexels", lambda q, p: None):
            got = photos.fetch({"id": "s1", "template": "sauti", "photo_query": "payslip on desk Kenya"}, Path(d))
            self.assertTrue(got and got["credit"].startswith("Photo: X"))
            none = photos.fetch({"id": "s2", "template": "glasspoll", "photo_query": "payslip on desk Kenya"}, Path(d))
            self.assertIsNone(none)   # non-civic posts never get a stand-in



def _page(title, desc, taken, lic="CC BY-SA 4.0", idx=1):
    return {"index": idx, "title": f"File:{title}.jpg", "imageinfo": [{
        "mime": "image/jpeg", "width": 3000, "height": 2000, "url": f"https://c/{title}.jpg",
        "descriptionurl": f"https://c/File:{title}", "timestamp": "2020-01-01T00:00:00Z",
        "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": "Wanjiru"},
                        "ImageDescription": {"value": desc}, "DateTimeOriginal": {"value": taken}}}]}


class EventPhotos(unittest.TestCase):
    POST = {"id": "e1", "template": "promise", "publish_at": "2026-10-14T18:30:00+03:00",
            "who": "Senator Samson Cherargei", "event_query": "Cherargei Senate", "photo_query": "Kenya National Assembly"}

    def run_search(self, pages, faces=False):
        fake = {"query": {"pages": {str(i): p for i, p in enumerate(pages)}}}
        with mock.patch.object(photos, "_get", lambda u, h=None, timeout=30: json.dumps(fake).encode() if "api.php" in u else b"IMG"), \
                mock.patch.object(photos, "faces_ok", lambda data: faces):
            return photos.event_photo(self.POST)

    def test_only_a_photo_taken_in_the_days_around_the_story_counts(self):
        old = _page("Cherargei 2019", "Senator Cherargei in the Senate, Kenya", "2019-05-02")
        self.assertIsNone(self.run_search([old]))
        new = _page("Cherargei Oct", "Senator Cherargei speaks in the Senate, Nairobi, Kenya", "2026-10-12 10:00")
        data, meta = self.run_search([old, new])
        self.assertEqual(meta["kind"], "event")
        self.assertIn("Wanjiru", meta["credit"])

    def test_named_office_holder_may_be_the_face_a_stranger_may_not(self):
        named = _page("Senate sitting", "Senator Cherargei in the Senate, Kenya", "2026-10-13")
        self.assertIsNotNone(self.run_search([named], faces=False))
        stranger = _page("Senate visitors", "Visitors at the Senate gallery, Kenya", "2026-10-13")
        self.assertIsNone(self.run_search([stranger], faces=False))

    def test_no_licence_no_photo(self):
        self.assertIsNone(self.run_search([_page("Cherargei", "Cherargei Senate Kenya", "2026-10-13", lic="CC BY-NC 4.0")]))

    def test_event_photo_comes_before_the_symbolic_one(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(photos, "event_photo", lambda p: (b"EVT", {"credit": "Photo: W", "url": "", "kind": "event"})), \
                mock.patch.object(photos, "commons", lambda q, p: (b"SYM", {"credit": "Photo: S", "url": ""})):
            got = photos.fetch(dict(self.POST), Path(d))
            self.assertEqual(got["kind"], "event")
            self.assertEqual(Path(got["file"]).read_bytes(), b"EVT")

if __name__ == "__main__":
    unittest.main()


class Batches(unittest.TestCase):
    def test_cut_off_reply_is_retried_in_halves(self):
        import draft
        calls = []

        def call(system, user, max_tokens=0, model=None):
            n = user.count('"id":')
            calls.append(n)
            if n > 2:
                raise RuntimeError("Anthropic API: reply was cut off at max_tokens (raise max_tokens)")
            return json.dumps({"posts": [{"id": f"x{len(calls)}"}]})
        slots = [{"id": f"s{i}", "template": "sauti", "lane": "everyone", "publish_at": "2026-10-12T07:00:00+03:00"} for i in range(4)]
        with mock.patch.object(draft, "call_claude", call), \
                mock.patch.object(draft, "build_prompt", lambda w, b, l, e, scripts=False: ("s", json.dumps(b))):
            got = draft._draft_batch("2026-W42", slots, {}, [])
        self.assertEqual(calls, [4, 2, 2])
        self.assertEqual(len(got), 2)


class PlaceKept(unittest.TestCase):
    def test_shorter_retry_still_needs_kenya(self):
        asked = []

        def once(q, pid, place=None, full=None, newest=False):
            asked.append((q, place))
            return None
        with mock.patch.object(photos, "_commons_once", once):
            photos.commons("Kenyan university campus students", "p")
        self.assertTrue(all(place == "Kenyan" for _, place in asked))
        self.assertIn("university campus", [q for q, _ in asked])


class Relevance(unittest.TestCase):
    def test_photo_must_be_of_the_subject_not_just_kenyan(self):
        self.assertFalse(photos._relevant("file:uk shop bin.jpg kenya trip", "Nairobi plastic recycling bricks factory"))
        self.assertTrue(photos._relevant("plastic bricks made in nairobi", "Nairobi plastic recycling bricks factory"))
        self.assertTrue(photos._relevant("students at kenyatta university", "university student Kenya"))

    def test_face_filled_photo_is_passed_over(self):
        good = [("a", {"url": "A"}), ("b", {"url": "B"})]
        with mock.patch.object(photos, "_get", lambda u, h=None, timeout=30: u.encode()), \
                mock.patch.object(photos, "faces_ok", lambda d: d == b"b"):
            data, meta = photos._pick(good, "pid-with-start-0" if True else "")
        self.assertEqual(meta["url"], "B")

    def test_blank_image_has_no_face(self):
        import numpy as np
        import cv2
        blank = cv2.imencode(".jpg", np.full((800, 1200, 3), 128, np.uint8))[1].tobytes()
        self.assertTrue(photos.faces_ok(blank))


class Symbolic(unittest.TestCase):
    def test_topic_picks_a_symbolic_background(self):
        self.assertEqual(photos.symbols_for({"line": "The state owes Kenya Power Sh7.35bn"})[:2],
                         ["power lines Kenya", "electricity pylon Kenya"])
        self.assertIn("ballot box Kenya", photos.symbols_for({"line": "IEBC adds 9,164 polling stations"}))
        self.assertEqual(photos.symbols_for({"line": "Nice weather"}), [])
