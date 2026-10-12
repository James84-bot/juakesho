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
        with mock.patch.object(photos, "_get", lambda u, h=None, timeout=30: json.dumps(fake).encode() if "openverse" in u else b"IMG"):
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
