"""Photos used only with written permission on record (no network, nothing assumed)."""
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
import photos  # noqa: E402

GOOD = {"grantor": "Example Press Office", "credit": "Photo: Example Press Office", "granted_on": "2026-11-02",
        "evidence": "email reply 2 Nov 2026, kept in Gmail", "photos": [
            {"file": "a-old.jpg", "person": "Jane Wanjiku", "taken": "2026-09-01"},
            {"file": "a-new.jpg", "person": "Jane Wanjiku", "taken": "2026-10-20"}]}
POST = {"id": "p1", "who": "Governor Jane Wanjiku", "template": "sauti", "message": "Jane Wanjiku opened a clinic."}


class Permissions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "a-old.jpg").write_bytes(b"OLD")
        (self.dir / "a-new.jpg").write_bytes(b"NEW")
        self.reg = self.dir / "permissions.json"
        self.patches = [mock.patch.object(photos, "PERMISSIONS", self.reg), mock.patch.object(photos, "APPROVED", self.dir)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def write(self, *grants):
        self.reg.write_text(json.dumps({"grants": list(grants)}), encoding="utf-8")

    def test_the_shipped_register_is_empty_so_nothing_is_assumed(self):
        with mock.patch.object(photos, "PERMISSIONS", Path(photos.__file__).parent / "content" / "permissions.json"):
            self.assertEqual(photos.grants(), [])

    def test_newest_photo_of_the_named_person_with_the_grantors_credit(self):
        self.write(GOOD)
        data, meta = photos.approved_photo(POST)
        self.assertEqual(data, b"NEW")
        self.assertEqual(meta["credit"], "Photo: Example Press Office")
        self.assertEqual(meta["kind"], "approved")

    def test_no_record_of_permission_means_not_used(self):
        for broken in ({**GOOD, "evidence": ""}, {**GOOD, "credit": ""}, {**GOOD, "granted_on": "soon"},
                       {**GOOD, "grantor": " "}, {**GOOD, "photos": []}):
            self.write(broken)
            self.assertIsNone(photos.approved_photo(POST), broken)

    def test_an_expired_permission_is_not_used(self):
        self.write({**GOOD, "expires": "2020-01-01"})
        self.assertIsNone(photos.approved_photo(POST))

    def test_only_the_person_named_and_never_beside_an_allegation(self):
        self.write(GOOD)
        self.assertIsNone(photos.approved_photo({**POST, "who": "Governor Peter Otieno"}))
        self.assertIsNone(photos.approved_photo({**POST, "message": "Jane Wanjiku was charged with fraud."}))
        self.assertIsNone(photos.approved_photo({**POST, "who": "Kenya National Assembly"}))

    def test_a_listed_file_that_is_missing_is_skipped(self):
        (self.dir / "a-new.jpg").unlink()
        (self.dir / "a-old.jpg").unlink()
        self.write(GOOD)
        self.assertIsNone(photos.approved_photo(POST))

    def test_fetch_prefers_a_photo_with_permission(self):
        self.write(GOOD)
        out = self.dir / "out"
        got = photos.fetch(POST, out)
        self.assertEqual(got["credit"], "Photo: Example Press Office")
        self.assertEqual(Path(got["file"]).read_bytes(), b"NEW")


if __name__ == "__main__":
    unittest.main()
