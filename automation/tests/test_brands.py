"""One engine, several brands: Kenya on Record unchanged, every other brand on its own files and its own accounts,
never Kenya on Record's."""
import importlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import brands  # noqa: E402

PAGES = json.dumps({"data": [{"id": "111", "name": "Kenya on Record", "access_token": "KOR-PAGE"},
                             {"id": "222", "name": "Full Time Kenya", "access_token": "FTK-PAGE"}]})


class Brands(unittest.TestCase):
    def tearDown(self):
        with mock.patch.dict(os.environ, {"KOR_BRAND": ""}):
            importlib.reload(brands)

    def load(self, slug):
        with mock.patch.dict(os.environ, {"KOR_BRAND": slug}):
            return importlib.reload(brands)

    def test_main_brand_keeps_its_places_and_keys(self):
        b = self.load("")
        self.assertTrue(b.MAIN)
        self.assertEqual(b.STATE, HERE / "state")
        self.assertEqual(b.CONTENT / "weeks", HERE / "content" / "weeks")
        self.assertEqual(b.EXPORTS, HERE.parent / "exports")
        env = {"META_ACCESS_TOKEN": "KOR", "TELEGRAM_BOT_TOKEN": "BOT"}
        self.assertEqual(b.apply_env(env), [])
        self.assertEqual(env["META_ACCESS_TOKEN"], "KOR")

    def test_another_brand_has_its_own_folder_and_never_the_main_accounts(self):
        b = self.load("Full Time Kenya")
        self.assertEqual(b.SLUG, "fulltimekenya")
        self.assertEqual(b.HOME, HERE / "brands" / "fulltimekenya")
        self.assertEqual(b.EXPORTS, HERE.parent / "exports" / "fulltimekenya")
        self.assertEqual(b.URL_PATH, "exports/fulltimekenya")
        env = {"META_ACCESS_TOKEN": "KOR", "META_PAGE_ID": "111", "META_IG_USER_ID": "9", "YT_REFRESH_TOKEN": "KOR-YT",
               "TELEGRAM_BOT_TOKEN": "KOR-BOT", "META_PAGES": PAGES,
               "BRAND_SECRETS": json.dumps({"TELEGRAM_BOT_TOKEN__FULLTIMEKENYA": "FTK-BOT"})}
        with mock.patch.object(b, "brand", lambda slug=None: {"facebook_page_id": "222"}):
            missing = b.apply_env(env)
        self.assertEqual(env["META_ACCESS_TOKEN"], "FTK-PAGE")    # its Page's token, from the one me/accounts paste
        self.assertEqual(env["META_PAGE_ID"], "222")
        self.assertEqual(env["TELEGRAM_BOT_TOKEN"], "FTK-BOT")    # its own bot
        self.assertEqual(env["YT_REFRESH_TOKEN"], "")             # no YouTube of its own: none at all, not ours
        self.assertEqual(env["META_IG_USER_ID"], "")              # looked up from its Page at run time
        self.assertEqual(set(missing), {"META_IG_USER_ID", "YT_REFRESH_TOKEN", "TIKTOK_REFRESH_TOKEN"})

    def test_a_brand_whose_page_is_not_in_the_paste_gets_no_meta_access(self):
        b = self.load("shillingbrief")
        env = {"META_ACCESS_TOKEN": "KOR", "META_PAGE_ID": "111", "META_PAGES": PAGES}
        with mock.patch.object(b, "brand", lambda slug=None: {"facebook_page_id": "333"}):
            b.apply_env(env)
        self.assertEqual((env["META_ACCESS_TOKEN"], env["META_PAGE_ID"]), ("", ""))

    def test_a_page_named_exactly_like_the_brand_is_its_page_when_no_id_is_set(self):
        b = self.load("fulltimekenya")
        env = {"META_PAGES": PAGES}
        with mock.patch.object(b, "brand", lambda slug=None: {"name": "Full Time Kenya"}):
            b.apply_env(env)
        self.assertEqual((env["META_ACCESS_TOKEN"], env["META_PAGE_ID"]), ("FTK-PAGE", "222"))
        env = {"META_PAGES": PAGES}
        with mock.patch.object(b, "brand", lambda slug=None: {"name": "Kenya on Record Fans"}):   # no near-misses
            b.apply_env(env)
        self.assertEqual(env["META_ACCESS_TOKEN"], "")

    def test_pages_paste_is_read_whole_or_as_a_list(self):
        self.assertEqual(len(brands._pages(PAGES)), 2)
        self.assertEqual(len(brands._pages(json.dumps(json.loads(PAGES)["data"]))), 2)
        self.assertEqual(brands._pages("not json"), [])


if __name__ == "__main__":
    unittest.main()


class RadarApi(unittest.TestCase):
    def test_uploads_through_the_data_api_when_rss_is_refused(self):
        import datetime as dt
        import radar
        now = dt.datetime(2026, 11, 8, 8, 0, tzinfo=dt.timezone.utc)
        calls = []

        def get(url, timeout=30):
            calls.append(url)
            if "playlistItems" in url:
                return json.dumps({"items": [
                    {"contentDetails": {"videoId": "v1", "videoPublishedAt": "2026-11-08T06:00:00Z"},
                     "snippet": {"title": "Police teargas FKF meeting in Meru"}},
                    {"contentDetails": {"videoId": "v2"}, "snippet": {"title": "no date"}}]}).encode()
            return json.dumps({"items": [{"id": "v1", "statistics": {"viewCount": "4000"}}]}).encode()

        got = radar.youtube_api("UCabc123", "NTV Kenya", now, key="k", get=get)
        self.assertIn("playlistId=UUabc123", calls[0])          # the channel's uploads playlist
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["views"], 4000)
        self.assertEqual(got[0]["per_hour"], 2000)
        self.assertEqual(got[0]["url"], "https://www.youtube.com/watch?v=v1")
        with self.assertRaises(RuntimeError):
            with mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": ""}):
                radar.youtube_api("UCabc", "x", now)
