"""showcase: real samples of the current rules, nothing posted (no network, no browser)."""
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
import pipeline as pl  # noqa: E402

POSTS = [{"id": "w-hot-1", "hot": True, "status": "published", "beats": ["EACC recovers *2.7 acres*.", "b", "c"],
          "source": "Capital FM News, 2026-10-27", "photo_file": "old.jpg", "photo_credit": "OLD CREDIT"},
         {"id": "w-hot-2", "hot": True, "status": "published", "beats": ["KPC drops cases.", "b", "c"], "source": "Tuko"},
         {"id": "w-d1", "status": "published", "beats": ["Not a news post.", "b", "c"]}]


class Showcase(unittest.TestCase):
    def run_it(self, found):
        from PIL import Image
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name)

        def attach(posts, d):   # the photo search: found for the first post only
            for q in posts:
                self.assertNotIn("photo_credit", q)   # stale photos from the original are never reused
            if found:
                posts[0].update(photo_file="x.jpg", photo_credit="Photo: Agency / Outlet", photo_kind="news")

        def render(posts, d, qa=None):
            for q in posts:
                Image.new("RGB", (20, 20)).save(Path(d) / f"{q['id']}.png")
        with mock.patch.object(pl, "PREVIEW", out), mock.patch.object(pl, "load_week", lambda label: {"posts": POSTS}), \
                mock.patch("photos.attach", attach), mock.patch("render.render", render):
            n = pl.showcase("2026-W44")
        return n, json.loads((out / "manifest.json").read_text(encoding="utf-8")), out

    def test_samples_are_news_posts_with_the_credit_found_under_todays_rules(self):
        n, manifest, out = self.run_it(found=True)
        self.assertEqual(n, 2)                                   # the non-news post is not a sample
        self.assertTrue((out / "showcase-1.jpg").exists())
        self.assertIn("Photo: Agency / Outlet (news)", manifest[0]["caption"])
        self.assertNotIn("Photo: Photo:", manifest[0]["caption"])
        self.assertIn("EACC recovers 2.7 acres.", manifest[0]["caption"])   # markers stripped
        self.assertIn("No real photo found", manifest[1]["caption"])         # said plainly, never invented

    def test_no_photo_found_is_stated(self):
        _, manifest, _ = self.run_it(found=False)
        self.assertTrue(all("No real photo found" in m["caption"] for m in manifest))


if __name__ == "__main__":
    unittest.main()
