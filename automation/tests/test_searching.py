"""'What Kenya is searching': the nightly Story from Google Trends Kenya (searching.py)."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402
import render  # noqa: E402
import searching  # noqa: E402

ITEMS = [
    {"title": "leeds vs spurs", "traffic": "50000+", "news": [{"title": "Leeds hold Tottenham", "url": "https://a/1", "source": "Sky"}]},
    {"title": "nottm forest vs man city", "traffic": "100K+", "news": [{"title": "Forest 1-2 City", "url": "https://a/2", "source": "BBC"}]},
    {"title": "mp arrested", "traffic": "90000+", "news": [{"title": "MP arrested over fraud claims", "url": "https://a/3", "source": "Star"}]},
    {"title": "kmtc intake", "traffic": "5,000+", "news": []},
    {"title": "state house nairobi", "traffic": "2k+", "news": [{"title": "Ruto hosts governors at State House", "url": "https://a/4", "source": "KBC"}]},
]


class Picking(unittest.TestCase):
    def test_biggest_first_with_news_behind_them_and_nothing_unsafe(self):
        rows = searching.pick(ITEMS)
        self.assertEqual([r["query"] for r in rows], ["nottm forest vs man city", "leeds vs spurs", "state house nairobi"])
        self.assertEqual([r["label"] for r in rows], ["100K+", "50K+", "2K+"])

    def test_a_way_to_watch_and_a_repeat_of_the_same_story_are_left_out(self):
        items = [{"title": "citizen tv live streaming", "traffic": "9K+", "news": [{"title": "Citizen TV schedule", "url": "https://c/1"}]},
                 {"title": "getafe vs atlético", "traffic": "2K+", "news": [{"title": "Getafe 0-1 Atlético", "url": "https://g/1"}]},
                 {"title": "getafe vs atletico madrid", "traffic": "1K+", "news": [{"title": "Getafe 0-1 Atlético", "url": "https://g/1"}]},
                 {"title": "víctor muñoz", "traffic": "200+", "news": [{"title": "Víctor Muñoz on the move", "url": "https://v/1"}]}]
        self.assertEqual([r["query"] for r in searching.pick(items)], ["getafe vs atlético", "víctor muñoz"])

    def test_last_nights_misses_are_left_out(self):
        # 23 Nov, live: the five rows Google gave, and what each should do
        rows = [("citizen tv live now", "2K+", "Citizen TV's KES 350 YouTube Package Tests Whether Kenyans Will Pay"),
                ("jensen huang", "2K+", "NVIDIA Board Reinstates Jensen Huang as President, CEO and Board Director"),
                ("al-shamal vs al-ahli", "500+", "Al-Shamal vs Al Ahli: TV channel, live stream and kick-off time for AFC"),
                ("forex factory", "500+", "How Global X Gold Bullion ETF (ASX:GXLD) Tracks Gold in Australian Dollars"),
                ("xabi alonso", "200+", "Dibu Martínez volvió a jugar en Chelsea tras la fractura de mandíbula"),
                ("víctor muñoz", "200+", "Victor Munoz linked with a January move")]
        items = [{"title": q, "traffic": v, "news": [{"title": h, "url": f"https://n/{i}", "source": "x"}]}
                 for i, (q, v, h) in enumerate(rows)]
        self.assertEqual([r["query"] for r in searching.pick(items)], ["jensen huang", "víctor muñoz"])

    def test_traffic_reads_every_way_google_writes_it(self):
        self.assertEqual([searching.traffic(x) for x in ("50K+", "50,000+", "2k+", "1.5M+", "")], [50000, 50000, 2000, 1500000, 0])
        self.assertEqual(searching.short(2_500_000), "2.5M+")


class ThePost(unittest.TestCase):
    def test_a_story_that_passes_the_guard_and_names_its_sources(self):
        at = dt.datetime(2026, 11, 22, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))
        post = searching.post_for(searching.pick(ITEMS), "2026-W47", at, at + dt.timedelta(minutes=30))
        self.assertEqual((post["id"], post["size"], post["day"]), ("2026-w47-searching-1122", "story", "Sunday 22 November"))
        self.assertEqual(len(post["source_links"]), 3)
        self.assertEqual(guard.check(post).errors, [])

    def test_a_search_reads_as_a_headline(self):
        self.assertEqual(render.headline_case("nottm forest vs man city"), "Nottm Forest vs Man City")
        self.assertEqual(render.headline_case("the KMTC intake"), "The KMTC Intake")
        self.assertEqual(render.headline_case("víctor muñoz"), "Víctor Muñoz")

    def test_it_may_go_out_by_itself(self):
        import pipeline as pl
        post = {"template": "searching", "hand": True, "source_links": [{"link": "https://a/1"}],
                "guard": {"errors": [], "warnings": []}}
        self.assertEqual(pl.auto_ok(post), "")


class NeverLateNeverStale(unittest.TestCase):
    """23 Nov: the Story was made before the picker learned to drop 'citizen tv live now' and unrelated headlines, and
    the Meta token was down at 20:30. It must not go out later with those rows, nor the next day."""
    AT = dt.datetime(2026, 11, 23, 20, 30, tzinfo=dt.timezone(dt.timedelta(hours=3)))

    def story(self, rows):
        return {"publish_at": self.AT.isoformat(), "rows": rows}

    def test_tonights_story_as_made_is_not_posted(self):
        rows = [{"query": "citizen tv live now", "title": "Citizen TV’s KES 350 YouTube Package Tests Whether"},
                {"query": "jensen huang", "title": "NVIDIA Board Reinstates Jensen Huang as President"},
                {"query": "forex factory", "title": "How Global X Gold Bullion ETF (ASX:GXLD) Tracks Gold"},
                {"query": "xabi alonso", "title": "Dibu Martínez volvió a jugar en Chelsea tras la fractura"}]
        why = searching.still_good(self.story(rows), self.AT)
        self.assertIn("citizen tv live now", why)
        self.assertIn("forex factory", why)
        self.assertIn("xabi alonso", why)
        self.assertNotIn("jensen huang", why)

    def test_a_good_story_goes_out_on_time_but_not_hours_late(self):
        rows = [{"query": "jensen huang", "title": "NVIDIA Board Reinstates Jensen Huang as President"}]
        self.assertEqual(searching.still_good(self.story(rows), self.AT + dt.timedelta(minutes=50)), "")
        self.assertIn("old news", searching.still_good(self.story(rows), self.AT + dt.timedelta(hours=4)))


def _has_browser() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_has_browser(), "needs Playwright Chromium (light-install runs have none)")
class OneNight(unittest.TestCase):
    """20:00 EAT: the Story is made, approves itself, and goes out at 20:30 as an Instagram and Facebook Story."""

    def test_made_approved_and_published_as_a_story(self):
        import os
        import tempfile
        from unittest import mock
        import pipeline as pl
        import trends
        clock = {"t": dt.datetime(2026, 11, 23, 17, 0, 30, tzinfo=dt.timezone.utc)}
        calls = []

        def fake(method, url, fields=None, files=None, timeout=60):
            calls.append((url.split("/v26.0/")[-1], dict(fields or {})))
            return {"ok": True, "id": f"id{len(calls)}", "result": {"message_id": len(calls)}}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(pl, "WEEKS", Path(d) / "weeks"), mock.patch.object(pl, "STATE", Path(d) / "state"), \
                mock.patch.object(pl, "EXPORTS", Path(d) / "exports"), mock.patch.object(pl, "http", fake), \
                mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "42", "META_ACCESS_TOKEN": "m",
                                             "META_PAGE_ID": "page", "META_IG_USER_ID": "ig",
                                             "PUBLIC_BASE_URL": "https://x.test/repo/"}), \
                mock.patch.object(pl.time, "sleep", lambda s: None), mock.patch.object(pl, "preflight", lambda u, k: None), \
                mock.patch.object(pl, "use_page_token", lambda: False), mock.patch.object(pl, "now", lambda: clock["t"]), \
                mock.patch.object(pl, "auto_approve_on", lambda: True), mock.patch.object(trends, "fetch", lambda geo: ITEMS):
            pl.save_week({"collection": "2026-W48", "posts": [], "scripts": {}})
            pid = pl.make_searching()
            self.assertEqual(pid, "2026-w48-searching-1123")
            post = pl.load_week("2026-W48")["posts"][0]
            self.assertEqual((post["status"], post["publish_at"]), ("approved", "2026-11-23T20:30:00+03:00"))
            self.assertIsNone(pl.make_searching())                       # once a night
            clock["t"] += dt.timedelta(minutes=31)
            calls.clear()
            pl.publish()
            self.assertEqual(pl.load_week("2026-W48")["posts"][0]["status"], "published")
            first_night = list(calls)
            # the next night's Story, with the Meta token down: it waits, then is dropped quietly once stale
            pl.save_week({"collection": "2026-W48", "posts": [], "scripts": {}})
            clock["t"] = dt.datetime(2026, 11, 24, 17, 0, 30, tzinfo=dt.timezone.utc)
            pl.make_searching()
            calls.clear()
            with mock.patch.object(pl, "meta_ready", lambda: False):
                clock["t"] += dt.timedelta(minutes=31)
                pl.publish()
                self.assertEqual(pl.load_week("2026-W48")["posts"][0]["status"], "approved")
                clock["t"] += dt.timedelta(hours=3)
                pl.publish()
            self.assertEqual(pl.load_week("2026-W48")["posts"][0]["status"], "missed")
            self.assertFalse([f.get("text", "")[:120] for p, f in calls if "sendMessage" in p and "searching" in f.get("text", "")])   # no notice to James for it
        paths = [p for p, _ in first_night]
        self.assertTrue(any(f.get("media_type") == "STORIES" for p, f in first_night if p == "ig/media"))
        self.assertIn("page/photo_stories", paths)
        self.assertFalse([p for p in paths if p.endswith("/comments")])   # Stories take no comments


if __name__ == "__main__":
    unittest.main()
