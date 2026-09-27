"""Tests for the autopilot: planning, approvals, publishing rules and the content guard.
Run: python -m unittest discover -s tests -v   (no network, no credentials needed)"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402
import pipeline as pl  # noqa: E402

REAL_PREFLIGHT = pl.preflight  # captured before any test stubs it


class TempWeeks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(pl, "WEEKS", root / "weeks"),
            mock.patch.object(pl, "STATE", root / "state"),
            mock.patch.dict(os.environ, {
                "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "42", "META_ACCESS_TOKEN": "m",
                "META_PAGE_ID": "page", "META_IG_USER_ID": "ig", "PUBLIC_BASE_URL": "https://x.test/repo/"}),
            mock.patch.object(pl.time, "sleep", lambda s: None),
            mock.patch.object(pl, "preflight", lambda url, kind: None),  # real check covered in ReelPublishTests
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def week(self, posts, label="2026-W41"):
        data = {"collection": label, "posts": posts, "scripts": {}}
        pl.save_week(data)
        return data


class PlanTests(TempWeeks):
    def test_dates_times_and_carousel(self):
        data = pl.plan("2026-W41")
        first = data["posts"][0]
        monday = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))["slots"][0]["time"]
        self.assertEqual(first["publish_at"], f"2026-10-05T{monday}:00+03:00")  # Monday 5 Oct 2026, EAT
        group = [p for p in data["posts"] if p.get("group")]
        self.assertEqual(len(group), 6)  # cover + 5 slides
        self.assertEqual(len({p["id"] for p in data["posts"]}), len(data["posts"]))  # unique ids

    def test_plan_is_idempotent(self):
        a = pl.plan("2026-W41")
        a["posts"][0]["status"] = "approved"
        pl.save_week(a)
        b = pl.plan("2026-W41")
        self.assertEqual(b["posts"][0]["status"], "approved")


class ApprovalTests(TempWeeks):
    def test_group_decision_applies_to_all_slides(self):
        data = {"posts": [{"id": "c", "group": "g", "status": "awaiting"},
                          {"id": "c-1", "group": "g", "status": "awaiting"},
                          {"id": "x", "status": "awaiting"}]}
        changed = pl.apply_decision(data, "g", True)
        self.assertEqual(changed, ["c", "c-1"])
        self.assertEqual(data["posts"][2]["status"], "awaiting")

    def test_collect_only_trusts_owner_chat(self):
        self.week([{"id": "p1", "status": "awaiting", "publish_at": "2026-10-05T07:15:00+03:00"},
                   {"id": "p2", "status": "awaiting", "publish_at": "2026-10-05T07:15:00+03:00"}])
        updates = {"ok": True, "result": [
            {"update_id": 10, "callback_query": {"id": "a", "data": "a|2026-W41|p1", "message": {"chat": {"id": 42}}}},
            {"update_id": 11, "callback_query": {"id": "b", "data": "a|2026-W41|p2", "message": {"chat": {"id": 999}}}},
        ]}
        calls = []

        def fake(method, url, fields=None, files=None, timeout=60):
            calls.append(url.rsplit("/", 1)[-1])
            return updates if url.endswith("getUpdates") else {"ok": True}

        with mock.patch.object(pl, "http", fake):
            pl.collect()
        posts = {p["id"]: p["status"] for p in pl.load_week("2026-W41")["posts"]}
        self.assertEqual(posts, {"p1": "approved", "p2": "awaiting"})
        self.assertEqual((pl.STATE / "telegram_offset.txt").read_text(), "12")


class PublishTests(TempWeeks):
    PAST = "2026-01-01T09:00:00+03:00"

    def run_publish(self, posts, fail=False):
        self.week(posts)
        calls = []

        def fake(method, url, fields=None, files=None, timeout=60):
            calls.append((url.split("/v26.0/")[-1], dict(fields or {})))
            if fail:
                raise RuntimeError("boom")
            return {"id": f"id{len(calls)}", "ok": True}

        with mock.patch.object(pl, "http", fake):
            pl.publish()
        return calls, pl.load_week("2026-W41")["posts"]

    def test_single_post_goes_to_instagram_and_facebook(self):
        calls, posts = self.run_publish([{"id": "p", "status": "approved", "publish_at": self.PAST, "caption": "Hi"}])
        paths = [c[0] for c in calls if "graph" not in c[0]]
        self.assertIn("ig/media", paths)
        self.assertIn("ig/media_publish", paths)
        self.assertIn("page/photos", paths)
        media = next(f for p, f in calls if p == "ig/media")
        self.assertEqual(media["image_url"], "https://x.test/repo/exports/2026-W41/p.jpg")
        self.assertEqual(posts[0]["status"], "published")

    def test_not_due_is_not_published(self):
        future = (pl.now() + dt.timedelta(days=2)).isoformat()
        calls, posts = self.run_publish([{"id": "p", "status": "approved", "publish_at": future}])
        self.assertEqual([c for c in calls if "graph" in c[0] or "/" in c[0]], [])
        self.assertEqual(posts[0]["status"], "approved")

    def test_carousel_waits_for_every_slide(self):
        calls, posts = self.run_publish([
            {"id": "c", "group": "g", "status": "approved", "publish_at": self.PAST},
            {"id": "c-1", "group": "g", "n": 1, "status": "awaiting", "publish_at": self.PAST}])
        self.assertEqual(calls, [])

    def test_carousel_publishes_as_one_post(self):
        calls, posts = self.run_publish([
            {"id": "c", "group": "g", "status": "approved", "publish_at": self.PAST, "caption": "Swipe"},
            {"id": "c-1", "group": "g", "n": 1, "status": "approved", "publish_at": self.PAST},
            {"id": "c-2", "group": "g", "n": 2, "status": "approved", "publish_at": self.PAST}])
        ig_media = [f for p, f in calls if p == "ig/media"]
        self.assertEqual(sum(1 for f in ig_media if f.get("is_carousel_item") == "true"), 3)
        self.assertTrue(any(f.get("media_type") == "CAROUSEL" for f in ig_media))
        self.assertTrue(any(p == "page/feed" for p, _ in calls))
        self.assertTrue(all(p["status"] == "published" for p in posts))

    def test_story_is_instagram_only(self):
        calls, _ = self.run_publish([{"id": "s", "size": "story", "status": "approved", "publish_at": self.PAST}])
        self.assertTrue(any(f.get("media_type") == "STORIES" for p, f in calls if p == "ig/media"))
        self.assertFalse(any(p.startswith("page/") for p, _ in calls))

    def test_failure_is_recorded_and_retries_stop(self):
        post = {"id": "p", "status": "approved", "publish_at": self.PAST}
        _, posts = self.run_publish([post], fail=True)
        self.assertEqual(posts[0]["status"], "publish_failed")
        self.assertEqual(posts[0]["attempts"], 1)
        _, posts = self.run_publish([{**posts[0], "attempts": 3}], fail=True)
        self.assertEqual(posts[0]["attempts"], 3)  # no 4th attempt


class GuardTests(unittest.TestCase):
    def test_launch_posts_pass(self):
        posts = json.loads((HERE / "content" / "posts.json").read_text(encoding="utf-8"))["posts"]
        self.assertTrue(all(r.ok for r in guard.check_all(posts)))

    def test_blocks_unclean_and_banned(self):
        r = guard.check({"id": "bad-1", "template": "shosh", "question": "Shosh, bet on the jackpot?",
                         "answer": "Wewe ni mjinga.", "punch": "haha", "caption": "x"})
        self.assertTrue(any("betting" in e for e in r.errors))
        self.assertTrue(any("mjinga" in e for e in r.errors))

    def test_length_limits(self):
        r = guard.check({"id": "long-1", "template": "poll", "question": "x" * 80, "options": ["a", "b"], "cta": "go"})
        self.assertTrue(any("question" in e for e in r.errors))


class ApiCallTests(unittest.TestCase):
    """call_claude: model id fallback, retries on temporary errors, no retry on real errors."""

    def setUp(self):
        import draft
        self.draft = draft
        self.env = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "JUA_MODEL": ""})
        self.env.start()
        self.sleep = mock.patch.object(draft.time, "sleep")
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()
        self.env.stop()

    @staticmethod
    def _ok(text="hi", stop="end_turn"):
        body = json.dumps({"content": [{"type": "text", "text": text}], "stop_reason": stop}).encode()
        resp = mock.MagicMock()
        resp.read.return_value = body
        resp.__enter__.return_value = resp
        return resp

    @staticmethod
    def _http(code):
        import io
        import urllib.error
        return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(b'{"error":"x"}'))

    def test_empty_env_var_falls_back_to_default_model(self):
        self.assertEqual(self.draft.model_id(), self.draft.DEFAULT_MODEL)
        sent = {}
        def fake(req, timeout):
            sent.update(json.loads(req.data))
            return self._ok()
        with mock.patch.object(self.draft.urllib.request, "urlopen", fake):
            self.assertEqual(self.draft.call_claude("s", "u"), "hi")
        self.assertEqual(sent["model"], self.draft.DEFAULT_MODEL)

    def test_retries_overloaded_then_succeeds(self):
        calls = [self._http(529), self._http(429), self._ok("done")]
        def fake(req, timeout):
            c = calls.pop(0)
            if isinstance(c, Exception):
                raise c
            return c
        with mock.patch.object(self.draft.urllib.request, "urlopen", fake):
            self.assertEqual(self.draft.call_claude("s", "u"), "done")
        self.assertEqual(calls, [])

    def test_bad_request_is_not_retried(self):
        n = {"calls": 0}
        def fake(req, timeout):
            n["calls"] += 1
            raise self._http(400)
        with mock.patch.object(self.draft.urllib.request, "urlopen", fake):
            with self.assertRaisesRegex(RuntimeError, "400"):
                self.draft.call_claude("s", "u")
        self.assertEqual(n["calls"], 1)

    def test_cut_off_reply_is_an_error(self):
        with mock.patch.object(self.draft.urllib.request, "urlopen", lambda req, timeout: self._ok("{", "max_tokens")):
            with self.assertRaisesRegex(RuntimeError, "max_tokens"):
                self.draft.call_claude("s", "u")


if __name__ == "__main__":
    unittest.main()


class ComicTests(unittest.TestCase):
    PANELS = [
        {"bg": "pwani", "left": {"who": "mama_mboga", "pose": "phone", "say": "Eh!", "sms": "Send it back"}},
        {"bg": "jua", "left": {"who": "shosh", "pose": "think", "say": "Hmm?"},
         "right": {"who": "makanga", "pose": "point", "say": "Check first!"}},
        {"bg": "waridi", "right": {"who": "jua", "say": "Usiibiwe!"}},
    ]

    def test_sms_points_at_the_phone_and_speech_at_the_head(self):
        import render
        import brandkit as bk
        layout = render.comic_layout(self.PANELS, 1080, 7)
        first = layout[0]
        speech, sms = sorted(first["bubbles"], key=lambda b: b["sms"])
        j = bk.skeleton(185, first["top"] + 330 - 34, "phone", 1.12)
        self.assertAlmostEqual(speech["target"][1], j["head"][1])
        self.assertLess(sms["target"][1], j["r_hand"][1])  # just above the hand, where the phone is
        self.assertNotEqual(speech["slot"], sms["slot"])

    def test_overlapping_bubbles_are_rejected(self):
        import render
        bad = [{"bg": "jua", "left": {"who": "boda", "say": "a"}, "right": {"who": "pro", "sms": "b"}}] + self.PANELS[1:]
        with self.assertRaises(ValueError):
            render.comic_layout(bad, 1080, 1)
        r = guard.check({"id": "c-1", "template": "vichekesho", "title": "t", "punch": "p", "caption": "x", "panels": bad})
        self.assertTrue(any("overlap" in e for e in r.errors))

    def test_comic_speech_is_checked_for_clean_content(self):
        panels = [dict(self.PANELS[0], left={"who": "boda", "say": "Wewe mjinga!"})] + self.PANELS[1:]
        r = guard.check({"id": "c-2", "template": "vichekesho", "title": "t", "punch": "p", "caption": "x", "panels": panels})
        self.assertTrue(any("mjinga" in e for e in r.errors))


SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>man utd vs west ham</title><ht:approx_traffic>1000+</ht:approx_traffic>
 <ht:news_item><ht:news_item_title>Team news and live text</ht:news_item_title><ht:news_item_url>https://x.test/a</ht:news_item_url><ht:news_item_source>BBC</ht:news_item_source></ht:news_item></item>
<item><title>edwin sifuna presidential bid 2027</title><ht:approx_traffic>2000+</ht:approx_traffic></item>
<item><title>new phone launch</title><ht:approx_traffic>5,000+</ht:approx_traffic>
 <ht:news_item><ht:news_item_title>Tragic accident at launch venue</ht:news_item_title></ht:news_item></item>
</channel></rss>"""


class TrendTests(unittest.TestCase):
    def test_parse_filter_and_prompt(self):
        import trends

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return SAMPLE_RSS

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(trends, "OUT", Path(d) / "trends.json"), \
                mock.patch.object(trends.urllib.request, "urlopen", lambda *a, **k: Resp()):
            data = trends.collect(("KE",))
            titles = [t["title"] for t in data["safe"]]
            self.assertEqual(titles, ["man utd vs west ham"])  # politics and tragedy dropped
            self.assertEqual(len(data["dropped"]), 2)
            block = trends.prompt_block()
            self.assertIn("man utd vs west ham", block)
            self.assertIn("Team news", block)

    def test_fetch_failure_never_blocks(self):
        import trends
        with tempfile.TemporaryDirectory() as d, mock.patch.object(trends, "OUT", Path(d) / "t.json"), \
                mock.patch.object(trends.urllib.request, "urlopen", side_effect=OSError("offline")):
            data = trends.collect(("KE",))
        self.assertEqual(data["safe"], [])
        self.assertIn("KE", data["errors"])


def _has_browser() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_has_browser(), "needs Playwright Chromium")
class VisualQATests(unittest.TestCase):
    def test_qa_passes_launch_posts_and_catches_a_broken_layout(self):
        import render
        posts = json.loads((HERE / "content" / "posts.json").read_text(encoding="utf-8"))["posts"]
        good = next(p for p in posts if p["template"] == "hack")
        broken = {**good, "id": "qa-broken", "title": "W" * 58}  # passes the length check, breaks the layout
        with tempfile.TemporaryDirectory() as d:
            qa = {}
            render.render([good, broken], Path(d), qa=qa)
        self.assertEqual(qa[good["id"]], [])
        self.assertTrue(any(k in i["what"] for i in qa["qa-broken"] for k in ("collides", "off the canvas", "wider than its box")))


class CriticTests(unittest.TestCase):
    def test_weak_post_is_rewritten_only_if_it_scores_higher(self):
        import draft
        base = json.loads((HERE / "content" / "posts.json").read_text(encoding="utf-8"))["posts"]
        hack = next(p for p in base if p["template"] == "hack")
        strong = next(p for p in base if p["template"] == "cap")
        slots = [{"id": "w-1", "template": "hack", "bg": "usiku", "lane": "campus", "publish_at": "2026-10-05T07:30:00+03:00"},
                 {"id": "w-2", "template": "cap", "bg": "usiku", "lane": "campus", "publish_at": "2026-10-06T12:45:00+03:00"}]
        posts = [{**hack, "id": "w-1", "status": "drafted"}, {**strong, "id": "w-2", "status": "drafted"}]
        better_title = "Your lecture as notes before the matatu hits town"
        calls = []

        def fake_claude(system, user, max_tokens=12000):
            calls.append(system[:30])
            if system.startswith("You are the toughest editor"):
                weak_round = "matatu" not in user
                s1 = 5 if weak_round else 9
                return json.dumps({"scores": [
                    {"id": "w-1", "hook": s1, "send": s1, "clarity": s1, "fresh": s1, "voice": s1, "craft": s1, "note": "Generic hook."},
                    {"id": "w-2", "hook": 8, "send": 8, "clarity": 8, "fresh": 8, "voice": 8, "craft": 8, "note": "Fine."}]})
            return json.dumps({"posts": [{**hack, "id": "w-1", "title": better_title}]})

        with mock.patch.object(draft, "call_claude", fake_claude):
            out = draft.elevate("2026-W41", slots, {}, posts)
        by = {p["id"]: p for p in out}
        self.assertEqual(by["w-1"]["title"], better_title)
        self.assertEqual(by["w-1"]["critic"]["avg"], 9.0)
        self.assertEqual(by["w-2"]["critic"]["avg"], 8.0)
        self.assertEqual(len(calls), 3)  # score, rewrite, re-score


class ReelPublishTests(TempWeeks):
    PAST = "2026-01-01T09:00:00+03:00"

    def test_reel_waits_for_processing_and_checks_media_types(self):
        self.week([{"id": "r", "status": "approved", "publish_at": self.PAST, "caption": "c", "reel": True}])
        calls, statuses = [], iter(["IN_PROGRESS", "FINISHED"])

        def fake_http(method, url, fields=None, files=None, timeout=60):
            calls.append((method, url.split("/v26.0/")[-1].split("?")[0], dict(fields or {})))
            if method == "GET":
                return {"status_code": next(statuses)}
            return {"id": f"id{len(calls)}"}

        checked = []
        with mock.patch.object(pl, "http", fake_http), \
                mock.patch.object(pl, "preflight", lambda url, kind: checked.append((url.rsplit(".", 1)[-1], kind))):
            pl.publish()
        media = next(f for m, p, f in calls if p == "ig/media")
        self.assertEqual(media["media_type"], "REELS")
        self.assertTrue(media["video_url"].endswith("/exports/2026-W41/r.mp4"))
        self.assertEqual(sum(1 for m, p, f in calls if m == "GET"), 2)  # polled until FINISHED
        self.assertIn(("mp4", "video"), checked)
        self.assertEqual(pl.load_week("2026-W41")["posts"][0]["status"], "published")

    def test_wrong_content_type_blocks_publishing(self):
        class Resp:
            headers = {"Content-Type": "text/plain; charset=utf-8"}
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch.object(pl.urllib.request, "urlopen", lambda *a, **k: Resp()):
            with self.assertRaises(RuntimeError) as ctx:
                REAL_PREFLIGHT("https://x.test/a.mp4", "video")
        self.assertIn("text/plain", str(ctx.exception))
