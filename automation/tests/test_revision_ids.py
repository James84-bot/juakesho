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


class Versions(unittest.TestCase):
    """26 Nov: photo swaps took the midday slot from -r2 to -r8 and used up its rewrites before the writer had them."""

    def test_new_photos_keep_the_version_and_only_rewrites_count(self):
        post = {"id": "w-hot-1126-r2", "status": "awaiting", "hot": True, "photo_query": "x", "version": 1}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pl, "WEEKS", Path(d)):
            pl.save_week({"collection": "2026-W48", "posts": [post], "scripts": {}})
            pl.rephoto("2026-W48", only="w-hot-1126-r2")
            pl.rephoto("2026-W48", only="w-hot-1126-r3")
            got = pl.load_week("2026-W48")["posts"][0]
        self.assertEqual((got["id"], pl._version(got)), ("w-hot-1126-r4", 1))

    def test_an_old_post_without_a_version_counts_its_id(self):
        self.assertEqual(pl._version({"id": "w-hot-1126-r3"}), 2)
        self.assertEqual(pl._version({"id": "w-hot-1126-r8", "version": 2}), 2)


class CivicNames(unittest.TestCase):
    """26 Nov: 'Easy Coach' and 'National November' held a Money post that scored 8.3."""

    def post(self, message):
        return {"id": "m", "template": "money", "source": "Nation, 25 Nov", "message": message,
                "caption": "Share this with the friend who travels.", "beats": [message]}

    def test_a_company_or_a_quoted_spokesperson_is_not_a_hold(self):
        import guard
        w = guard.check(self.post("Easy Coach raised fares by Sh200, says manager Bellarmine Bulinda.")).warnings
        self.assertFalse([x for x in w if "named person" in x])

    def test_a_name_beside_an_allegation_still_waits(self):
        import guard
        w = guard.check(self.post("Easy Coach boss John Kamau was charged with fraud over fares.")).warnings
        self.assertTrue([x for x in w if "named person" in x])


class Repairs(unittest.TestCase):
    """26 Nov: drafts broke the length rules, no repair ran (Gemini's calls for the run were spent), and each was
    thrown away for a new story. The free backups cost nothing, so repairs go on with them."""

    def test_repairs_run_on_the_free_backups_once_gemini_is_spent(self):
        import os
        import draft
        with mock.patch.dict(draft.SPEND, {"calls": draft.GEMINI_LIMITS["calls"], "usd": 0.0}), \
                mock.patch.object(draft, "provider", lambda: "gemini"):
            with mock.patch.dict(os.environ, {"GROQ_API_KEY": "", "OPENROUTER_API_KEY": "", "MISTRAL_API_KEY": ""}):
                self.assertFalse(draft.can_afford(5000, 700))
            with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}):
                self.assertTrue(draft.can_afford(5000, 700))


if __name__ == "__main__":
    unittest.main()
