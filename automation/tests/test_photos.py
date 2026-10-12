"""Photo sources: licence and place filters, and the civic fallback (no network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
