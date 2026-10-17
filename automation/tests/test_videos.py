"""videos.py: real footage behind Reels, and the TV clip of the day's story (no network)."""
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
import videos  # noqa: E402


def commons_reply(*pages):
    return json.dumps({"query": {"pages": {str(i): p for i, p in enumerate(pages)}}}).encode()


def page(title, lic="CC BY-SA 4.0", width=1920, desc="", cats="", size=5_000_000):
    return {"index": 1, "title": title, "imageinfo": [{"url": "https://upload.test/v.webm", "width": width, "size": size,
            "descriptionurl": "https://commons.test/" + title, "extmetadata": {
                "LicenseShortName": {"value": lic}, "Artist": {"value": "Jane Doe"},
                "ImageDescription": {"value": desc}, "Categories": {"value": cats}}}]}


class Wanted(unittest.TestCase):
    def test_footage_replaces_symbols_never_a_news_photo(self):
        beats = ["a b c d.", "e f g h.", "i j k l."]
        self.assertTrue(videos.wanted({"template": "kenya", "beats": beats}))
        self.assertTrue(videos.wanted({"template": "sauti", "beats": beats, "photo_kind": "symbolic", "photo_query": "x"}))
        self.assertFalse(videos.wanted({"template": "sauti", "beats": beats, "photo_kind": "posted", "photo_query": "x"}))
        self.assertFalse(videos.wanted({"template": "sauti", "beats": beats, "photo_kind": "file", "photo_query": "x"}))
        self.assertFalse(videos.wanted({"template": "tazama", "beats": beats}))
        self.assertFalse(videos.wanted({"template": "kenya"}))   # no beats, no Reel to move


class Sources(unittest.TestCase):
    def test_commons_needs_an_open_licence_and_the_place_itself(self):
        reply = commons_reply(page("File:Some lake.webm", desc="a lake in Canada"),
                              page("File:Longonot rim.webm", lic="CC BY-NC 4.0", desc="Mount Longonot, Kenya"),
                              page("File:Longonot crater walk.webm", desc="Walking the rim of Mount Longonot", cats="Kenya"))
        with mock.patch.object(videos.photos, "_get", lambda url, headers=None, timeout=30: reply):
            url, meta = videos.commons_video("Mount Longonot Kenya", "p")
        self.assertIn("Longonot crater walk", meta["url"])
        self.assertTrue(meta["credit"].startswith("Footage: Jane Doe / Wikimedia Commons, CC BY-SA 4.0"))

    def test_pexels_clip_must_name_the_place(self):
        reply = json.dumps({"videos": [
            {"url": "https://www.pexels.com/video/city-skyline-at-night-1/", "user": {"name": "A"},
             "video_files": [{"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://p.test/1.mp4"}]},
            {"url": "https://www.pexels.com/video/nairobi-skyline-at-dusk-2/", "user": {"name": "B"},
             "video_files": [{"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://p.test/2.mp4"}]}]}).encode()
        with mock.patch.dict(os.environ, {"PEXELS_API_KEY": "k"}), \
                mock.patch.object(videos.photos, "_get", lambda url, headers=None, timeout=30: reply):
            url, meta = videos.pexels_video("Nairobi skyline", "p")
        self.assertEqual(url, "https://p.test/2.mp4")
        self.assertEqual(meta["credit"], "Footage: B / Pexels")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PEXELS_API_KEY", None)
            self.assertIsNone(videos.pexels_video("Nairobi skyline", "p"))   # no key: skipped quietly

    def test_a_stranger_filling_the_frame_is_skipped_on_critical_posts(self):
        with tempfile.TemporaryDirectory() as d:
            post = {"id": "p", "template": "sauti", "beats": ["x"] * 3, "photo_kind": "symbolic", "photo_query": "Nairobi CBD"}
            with mock.patch.object(videos, "commons_video", lambda q, pid: ("https://u.test/v", {"credit": "c", "url": "u"})), \
                    mock.patch.object(videos, "pexels_video", lambda q, pid: None), \
                    mock.patch.object(videos.photos, "_get", lambda url, headers=None, timeout=30: b"raw"), \
                    mock.patch.object(videos, "cut", lambda src, out: out.write_bytes(b"x" * 20000) or True), \
                    mock.patch.object(videos, "frames_ok", lambda clip: False):
                self.assertIsNone(videos.fetch(post, Path(d)))
                with mock.patch.object(videos, "frames_ok", lambda clip: True):
                    got = videos.fetch(post, Path(d))
            self.assertEqual(got["credit"], "c")
            self.assertTrue(Path(got["file"]).exists())


class Render(unittest.TestCase):
    def test_only_beat_reels_with_a_clip_are_drawn_transparent(self):
        import render
        env = render.make_env()
        with tempfile.TemporaryDirectory() as d:
            clip = Path(d) / "c.mp4"
            clip.write_bytes(b"x")
            reel = {"id": "r", "template": "reel", "size": "story", "bg": "usiku", "kicker": "Kenya at its best",
                    "beats": ["Hell's Gate is a park you can cycle through.", "b c d e.", "f g h i."],
                    "video_file": str(clip), "video_credit": "Footage: A / Pexels"}
            html = render.build_html(env, reel, motion=True)
            self.assertIn("background: transparent", html)
            self.assertIn("Footage: A / Pexels", html)
            html = render.build_html(env, dict(reel, video_file=str(Path(d) / "missing.mp4")), motion=True)
            self.assertNotIn("Footage: A / Pexels", html)



class TvClip(unittest.TestCase):
    CLIPS = {"catalog": [
        {"title": "FRIDAY NIGHT NEWS ~ Oct 16, 2026", "channel": "Citizen TV", "url": "https://y.test/bulletin", "per_hour": 9999},
        {"title": "Former Nairobi PC Davis Chelogoi Convicted in Sh1.3 Billion Land Fraud", "channel": "KTN News",
         "url": "https://y.test/chelogoi", "per_hour": 10},
        {"title": "Sifuna renews attack on Ruto, vowing to scrap housing levy if elected", "channel": "NTV Kenya",
         "url": "https://y.test/levy", "per_hour": 10}]}

    def test_the_story_clip_is_found_and_bulletins_are_not(self):
        import radar
        post = {"template": "scorecard", "who": "Davis Chelogoi, former Nairobi PC",
                "message": "Former Nairobi PC Davis Chelogoi was convicted over Sh1.35bn land fraud."}
        self.assertEqual(radar.clip_for(post, self.CLIPS)["url"], "https://y.test/chelogoi")
        self.assertEqual(radar.clip_for({"template": "glasspoll", "message": "Opposition leaders pledge to scrap the housing levy."},
                                        self.CLIPS)["url"], "https://y.test/levy")
        self.assertIsNone(radar.clip_for({"template": "sauti", "who": "Kenya Revenue Authority",
                                          "message": "KRA uncovers VAT fraud."}, self.CLIPS))


if __name__ == "__main__":
    unittest.main()
