"""Photo sources: licence and place filters, and the civic fallback (no network)."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):   # AI keys never reach the tests: no real calls, no spend
    os.environ.pop(_k, None)
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import posted as _posted  # noqa: E402
_posted._live_items = lambda: []                  # tests never read live news feeds
_posted.ARCHIVE = Path("/nonexistent/feed_photos.json")   # ...nor the bot's real archive

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
    def test_last_resort_is_the_real_institution_not_a_stand_in_object(self):
        self.assertEqual(photos.symbols_for({"line": "The state owes Kenya Power Sh7.35bn"})[:2],
                         ["Stima Plaza Nairobi", "Kenya Power"])
        self.assertIn("Anniversary Towers Nairobi", photos.symbols_for({"line": "IEBC adds 9,164 polling stations"}))
        self.assertIn("Times Tower Nairobi", photos.symbols_for({"line": "KRA uncovers Ksh 4 billion VAT fraud"}))
        every = [q for _, qs in photos.SYMBOLS for q in qs]
        self.assertFalse([q for q in every if re.search(r"banknote|pylon|ballot box|power lines|title deed", q, re.I)])
        self.assertEqual(photos.symbols_for({"line": "Nice weather"}), [])


def _wiki(page: dict, file_info: dict | None):
    """A fake _get for wiki_photo: the Wikipedia article, then its Commons file, then the image bytes."""
    def get(url, headers=None, timeout=30):
        if "wikipedia.org" in url:
            return json.dumps({"query": {"pages": {"1": page}}}).encode()
        if "commons.wikimedia.org" in url:
            return json.dumps({"query": {"pages": {"-1": {"imageinfo": [file_info]} if file_info else {"missing": ""}}}}).encode()
        return b"JPEGDATA"
    return get


PORTRAIT = {"mime": "image/jpeg", "width": 900, "url": "https://up/r.jpg", "thumburl": "https://up/r-1600.jpg",
            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "Artist": {"value": "<a>PCS Kenya</a>"}}}
RUTO = {"title": "William Ruto", "pageimage": "Ruto.jpg", "extract": "William Ruto is a Kenyan politician..."}


class SubjectPhoto(unittest.TestCase):
    def test_the_named_person_gets_their_licensed_portrait(self):
        with mock.patch.object(photos, "_get", _wiki(RUTO, PORTRAIT)):
            data, meta = photos.subject_photo({"id": "p", "who": "President William Ruto"})
        self.assertEqual(meta["kind"], "portrait")
        self.assertEqual(meta["credit"], "Photo: PCS Kenya / Wikimedia Commons, CC BY-SA 4.0")

    def test_namesakes_disambiguation_logos_and_restrictive_licences_are_refused(self):
        cases = [
            (dict(RUTO, extract="William Ruto is a footballer from Ghana."), PORTRAIT),   # not about Kenya
            (dict(RUTO, pageprops={"disambiguation": ""}), PORTRAIT),
            (RUTO, dict(PORTRAIT, mime="image/svg+xml")),                                   # a logo
            (RUTO, dict(PORTRAIT, extmetadata={"LicenseShortName": {"value": "CC BY-NC 2.0"}})),
            (RUTO, None),                                                                    # a local, non-free file
        ]
        for page, info in cases:
            with mock.patch.object(photos, "_get", _wiki(page, info)):
                self.assertIsNone(photos.wiki_photo("William Ruto"), (page.get("extract"), info and info.get("mime")))

    def test_an_institution_story_gets_the_institution_photo(self):
        kra = {"title": "Kenya Revenue Authority", "pageimage": "Times_Tower.jpg", "extract": "The KRA..."}
        with mock.patch.object(photos, "_get", _wiki(kra, dict(PORTRAIT, width=2000))):
            data, meta = photos.subject_photo({"id": "k", "line": "KRA uncovered a Ksh 4 billion VAT fraud"})
        self.assertEqual(meta["kind"], "institution")

    def test_person_names_come_out_of_who(self):
        for who, name in [("Energy CS Opiyo Wandayi", "Opiyo Wandayi"), ("Hassan Omar, UDA Secretary-General", "Hassan Omar"),
                          ("National Assembly Public Debt Committee", ""), ("Senator Samson Cherargei", "Samson Cherargei")]:
            self.assertEqual(photos.person_name(who), name)


class ExtraPhotos(unittest.TestCase):
    def _img(self, box):
        import io
        from PIL import Image
        b = io.BytesIO(); im = Image.new("RGB", (1600, 900), "white"); im.paste("black", box); im.save(b, "JPEG")
        return b.getvalue()

    def test_reel_gets_other_real_photos_of_the_story_once_each_and_cached(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            main = d / "m.jpg"; main.write_bytes(self._img((0, 0, 800, 900)))
            same, other = self._img((0, 0, 800, 900)), self._img((0, 0, 1600, 450))
            post = {"id": "x", "template": "sauti", "who": "Kenya Revenue Authority"}
            found = [(same, {"credit": "Photo: Nation", "kind": "posted"}), (other, {"credit": "Photo: KBC", "kind": "posted"})]
            with mock.patch("posted.find_all", lambda p, n: list(found)), \
                    mock.patch.object(photos, "subject_photo", lambda p: None):
                got = photos.extras(post, d, {"file": str(main), "kind": "posted"})
            self.assertEqual([g["credit"] for g in got], ["Photo: KBC"])     # the copy of the main photo is dropped
            with mock.patch("posted.find_all", side_effect=AssertionError("searched again")):
                self.assertEqual(photos.extras(post, d, {"file": str(main), "kind": "posted"}), got)   # cached

    def test_no_extras_behind_a_stand_in_scene(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(photos.extras({"id": "y", "template": "sauti"}, Path(d), {"file": "", "kind": "symbolic"}), [])
