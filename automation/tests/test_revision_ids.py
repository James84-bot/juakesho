"""25 Nov: a new photo turned 'hot-1125-r2' into 'hot-1125-r3' while its replacement draft already had that id."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pipeline as pl  # noqa: E402


class NextRevision(unittest.TestCase):
    def test_counts_up_and_skips_ids_in_use(self):
        self.assertEqual(pl._next_rev("w-hot-1125"), "w-hot-1125-r2")
        self.assertEqual(pl._next_rev("w-hot-1125-r2"), "w-hot-1125-r3")
        self.assertEqual(pl._next_rev("w-hot-1125-r2", {"w-hot-1125-r3", "w-hot-1125-r4"}), "w-hot-1125-r5")

    def test_new_photos_never_take_the_replacements_id(self):
        posts = [{"id": "2026-w48-hot-1125", "status": "needs_human", "hot": True, "replaced_by": "2026-w48-hot-1125-r2"},
                 {"id": "2026-w48-hot-1125-r2", "status": "awaiting", "hot": True, "photo_query": "budget forum",
                  "replaced_by": "2026-w48-hot-1125-r3", "tg_msg": 7},
                 {"id": "2026-w48-hot-1125-r3", "status": "awaiting", "hot": True, "photo_query": "police"}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pl, "WEEKS", Path(d)):
            pl.save_week({"collection": "2026-W48", "posts": posts, "scripts": {}})
            changed = pl.rephoto("2026-W48", only="2026-w48-hot-1125-r2")
            ids = [p["id"] for p in pl.load_week("2026-W48")["posts"]]
        self.assertEqual(changed, ["2026-w48-hot-1125-r4"])
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
