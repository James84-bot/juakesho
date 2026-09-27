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
    @property
    def PAST(self):  # due an hour ago: on time, so it should publish
        return (pl.now() - dt.timedelta(hours=1)).isoformat()

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

    def test_waits_quietly_until_instagram_is_connected(self):
        no_meta = {"META_ACCESS_TOKEN": "", "META_PAGE_ID": "", "META_IG_USER_ID": ""}
        with mock.patch.dict(os.environ, no_meta):
            calls, posts = self.run_publish([{"id": "p", "status": "approved", "publish_at": self.PAST}])
            self.assertEqual(posts[0]["status"], "approved")      # not failed, retries not used
            self.assertNotIn("attempts", posts[0])
            self.assertEqual(sum("sendMessage" in c[0] for c in calls), 1)   # owner told...
            self.assertFalse(any("/media" in c[0] for c in calls))
            calls, posts = self.run_publish(posts)
            self.assertEqual(calls, [])                                       # ...only once
        # Now connected (keys from setUp): it publishes, and the notice flag is cleared
        calls, posts = self.run_publish(posts)
        self.assertEqual(posts[0]["status"], "published")
        self.assertFalse((pl.STATE / "meta_missing_notified.txt").exists())

    def test_stale_post_is_missed_not_dumped(self):
        old = (pl.now() - dt.timedelta(hours=40)).isoformat()
        calls, posts = self.run_publish([{"id": "p", "status": "approved", "publish_at": old}])
        self.assertEqual(posts[0]["status"], "missed")
        self.assertFalse(any("/media" in c[0] for c in calls))


class PruneTests(TempWeeks):
    def test_old_weeks_are_pruned_whatever_their_status(self):
        exports = Path(self.tmp.name) / "exports"
        with mock.patch.object(pl, "EXPORTS", exports):
            old = (pl.now() - dt.timedelta(weeks=7)).isoformat()
            recent = (pl.now() - dt.timedelta(days=3)).isoformat()
            self.week([{"id": "a", "status": "awaiting", "publish_at": old},
                       {"id": "b", "status": "missed", "publish_at": old}], label="2026-W30")
            self.week([{"id": "c", "status": "awaiting", "publish_at": recent}], label="2026-W39")
            for w in ("2026-W30", "2026-W39"):
                (exports / w).mkdir(parents=True)
                (exports / w / "x.png").write_bytes(b"x")
            self.assertEqual(pl.prune(), ["2026-W30"])
            self.assertFalse((exports / "2026-W30").exists())
            self.assertTrue((exports / "2026-W39" / "x.png").exists())


class RepairTests(unittest.TestCase):
    def test_repair_retries_until_the_post_passes(self):
        import draft
        slot = {"id": "2026-w40-d5-spotlight", "template": "spotlight", "bg": "usiku", "lane": "creator"}
        good = {"id": "2026-w40-d5-spotlight", "template": "spotlight", "kind": "Startup", "name": "Ushahidi", "country": "Kenya",
                "what": "Open-source crowdmapping born in Nairobi, used worldwide.",
                "why": "Proof that African tech can serve the whole world.",
                "cta": "Follow their story.", "source": "ushahidi.com/about",
                "caption": "Put Us On: Ushahidi. Share this with a comrade.\n\n#PutUsOn"}
        long = {**good, "cta": "Follow their story and see how far this build scales."}  # 53 chars
        replies = iter([json.dumps({"posts": [long]}), "no json here", json.dumps({"posts": [good]})])
        posts = draft._merge([slot], [long])
        reports = guard.check_all(posts)
        self.assertFalse(reports[0].ok)
        with mock.patch.object(draft, "call_claude", lambda system, user: next(replies)), \
                mock.patch.object(draft, "build_prompt", lambda *a: ("sys", "user")):
            posts, reports = draft.repair("2026-W40", [slot], {}, posts, reports)
        self.assertTrue(reports[0].ok, reports[0].errors)
        self.assertEqual(posts[0]["cta"], "Follow their story.")


class RedoTests(TempWeeks):
    def test_redo_resets_only_held_posts_and_whole_carousels(self):
        when = "2026-10-01T19:30:00+03:00"
        self.week([
            {"id": "a", "template": "hack", "bg": "usiku", "lane": "campus", "publish_at": when, "status": "awaiting", "title": "keep"},
            {"id": "b", "template": "spotlight", "bg": "usiku", "lane": "creator", "publish_at": when,
             "status": "needs_human", "cta": "x" * 53, "guard": {"errors": ["'cta' is 53 chars (max 50)"]}},
            {"id": "c", "template": "cover", "bg": "usiku", "lane": "all", "publish_at": when, "status": "awaiting", "group": "c"},
            {"id": "c-1", "template": "kesho", "bg": "usiku", "lane": "all", "publish_at": when, "status": "needs_human",
             "group": "c", "n": 1, "total": 1}], label="2026-W40")
        with mock.patch.object(pl, "tg", lambda *a, **k: {"ok": True}):
            note = pl.held_summary(pl.load_week("2026-W40"))
            self.assertIn("53 chars", note)
            with mock.patch.object(pl, "draft", lambda label, mock=False: None), \
                    mock.patch.object(pl, "render_week", lambda label: None), \
                    mock.patch.object(pl, "ask", lambda label, dry_run=False: None), \
                    mock.patch.object(pl, "current_week_label", lambda: "2026-W41"):
                pl.main(["redo"])   # finds W40 by itself, although "next week" is W41
        posts = {p["id"]: p for p in pl.load_week("2026-W40")["posts"]}
        self.assertEqual(posts["a"]["status"], "awaiting")      # untouched, still in your Telegram
        self.assertEqual(posts["a"]["title"], "keep")
        self.assertEqual(posts["b"], {"id": "b", "template": "spotlight", "bg": "usiku", "lane": "creator",
                                      "publish_at": when, "status": "planned"})   # old content and errors cleared
        self.assertEqual(posts["c"]["status"], "planned")       # whole carousel redone together
        self.assertEqual(posts["c-1"]["n"], 1)


class QualitySystemTests(unittest.TestCase):
    """Symbols, Set It Straight, photos, budget: the rules that keep quality high and spend flat."""

    def base_straight(self, **kw):
        post = {"id": "2026-w41-d2-straight", "template": "straight", "bg": "usiku", "symbol": "magnifier",
                "claim": "Africa is one country.", "who": "a viral post", "claim_source": "Viral X post, May 2026 (link)",
                "verdict": "false", "truth": "54 countries.", "proof": ["UN lists 54 African member states.", "Over 2,000 languages."],
                "pride": "One continent. 54 flags.", "source": "un.org member states",
                "caption": "Set It Straight. Send this to a friend.\n\n#JuaKesho"}
        post.update(kw)
        return post

    def test_symbols_are_validated(self):
        self.assertTrue(guard.check(self.base_straight()).ok)
        r = guard.check(self.base_straight(symbol="dragon"))
        self.assertTrue(any("unknown symbol" in e for e in r.errors))

    def test_set_it_straight_needs_claim_source_and_never_attacks_people(self):
        self.assertTrue(any("claim_source" in e for e in guard.check(self.base_straight(claim_source="")).errors))
        r = guard.check(self.base_straight(pride="She is a liar and a fraud."))
        self.assertTrue(any("never attacks the person" in e for e in r.errors))
        r = guard.check(self.base_straight(verdict="lies"))
        self.assertFalse(r.ok)

    def test_photo_rules(self):
        ok = guard.check(self.base_straight(photo_query="Nairobi skyline at dusk"))
        self.assertTrue(ok.ok, ok.errors)
        people = guard.check(self.base_straight(photo_query="angry man shouting"))
        self.assertTrue(any("not people" in e for e in people.errors))
        logo = guard.check(self.base_straight(photo_query="safaricom logo"))
        self.assertTrue(any("logos" in e for e in logo.errors))

    def test_real_people_photos_need_rights(self):
        spot = {"id": "2026-w41-d5-spotlight", "template": "spotlight", "kind": "Artist", "name": "Amina", "country": "Kenya",
                "what": "Makes music.", "why": "Proof our sound travels.", "cta": "Stream her.", "source": "her site",
                "symbol": "music", "caption": "Put Us On. Share this.\n\n#JuaKesho"}
        self.assertTrue(guard.check({**spot, "person_photo": "people/amina.jpg", "photo_rights": "permission from her manager, Oct 2026"}).ok)
        self.assertTrue(any("photo_rights" in e for e in guard.check({**spot, "person_photo": "people/amina.jpg"}).errors))
        self.assertTrue(any("must be" in e for e in guard.check({**spot, "person_photo": "https://instagram.com/x.jpg"}).errors))
        money = {**self.base_straight(), "person_photo": "commons:File:X.jpg"}
        self.assertTrue(any("only on Put Us On" in e for e in guard.check(money).errors))

    def test_commons_licences(self):
        import photos
        for ok in ("CC0", "Public domain", "CC BY 4.0", "CC BY 2.0"):
            self.assertTrue(photos.OK_LICENCES.match(ok), ok)
        for bad in ("CC BY-SA 4.0", "CC BY-NC 2.0", "All rights reserved", "Fair use"):
            self.assertFalse(photos.OK_LICENCES.match(bad) and "sa" not in bad.lower().split("-"), bad)

    def test_music_only_with_rights_and_credited(self):
        import video
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(video, "MUSIC", Path(tmp)):
            Path(tmp, "a.mp3").write_bytes(b"x")
            Path(tmp, "tracks.json").write_text(json.dumps({"tracks": [
                {"file": "a.mp3", "artist": "Amina", "title": "Kesho", "rights": "permission by email, Oct 2026"},
                {"file": "b.mp3", "artist": "X", "title": "Y", "rights": ""}]}))
            Path(tmp, "b.mp3").write_bytes(b"x")
            self.assertEqual(video.music_track({"track": "a.mp3"})["artist"], "Amina")
            self.assertIsNone(video.music_track({"track": "b.mp3"}))       # no rights recorded
            self.assertIsNone(video.music_track({"track": "c.mp3"}))       # not registered
        cap = pl.caption_for({"caption": "Hi", "photo_credit": "Photo: A / Pexels", "track_credit": "Amina - Kesho (used with permission)"})
        self.assertEqual(cap, "Hi\n\n📷 Photo: A / Pexels\n🎵 Amina - Kesho (used with permission)")
        self.assertTrue(any("track" in e for e in guard.check(self.base_straight(track="../../etc/passwd")).errors))

    def test_approval_card_escapes_html_and_never_cuts_a_tag(self):
        post = {"id": "p", "template": "hack", "lane": "campus", "publish_at": "2026-10-05T07:30:00+03:00",
                "caption": "Q&A <3 " + "x" * 2000, "message": "Use <b> & win", "symbol": "key",
                "critic": {"avg": 8, "hook": 8, "clarity": 9, "picture": 7, "send": 8, "fresh": 7, "note": "a < b"},
                "guard": {"warnings": ["w1 <x>"] * 10}, "source": "s & t"}
        text = pl._preview_text(post)
        self.assertLessEqual(len(text), 1024)
        self.assertIn("Q&amp;A &lt;3", text)
        self.assertNotIn("<3", text)
        import re
        self.assertEqual(re.findall(r"<(/?)(\w+)", text).count(("", "b")), re.findall(r"<(/?)(\w+)", text).count(("/", "b")))

    def test_photos_skip_quietly_without_a_key(self):
        import photos
        post = {"id": "p1", "photo_query": "farm at sunrise"}
        with mock.patch.dict(os.environ, {"PEXELS_API_KEY": ""}):
            photos.attach([post], Path(tempfile.mkdtemp()))
        self.assertNotIn("photo_file", post)

    def test_caption_gets_photo_credit_once(self):
        self.assertEqual(pl.caption_for({"caption": "Hi"}), "Hi")
        c = pl.caption_for({"caption": "Hi", "photo_credit": "Photo: A / Pexels"})
        self.assertTrue(c.endswith("Photo: A / Pexels"))
        self.assertEqual(pl.caption_for({"caption": c, "photo_credit": "Photo: A / Pexels"}), c)

    def test_free_square_avoids_every_obstacle(self):
        import render
        rects = [[0, 0, 1080, 500], [0, 500, 600, 1350]]          # top band and left column taken
        x, y, size = render.free_square(1080, 1350, rects)
        self.assertGreaterEqual(size, render.SYMBOL["min"])
        self.assertGreaterEqual(x, 600 + render.SYMBOL["pad"] - render.SYMBOL["cell"])
        self.assertGreaterEqual(y, 500 + render.SYMBOL["pad"] - render.SYMBOL["cell"])
        self.assertIsNone(render.free_square(1080, 1350, [[0, 0, 1080, 1350]]))

    def test_headline_fit_shrinks_for_a_long_single_word(self):
        import textfit
        short = textfit.fit_display("Prompt", 580, 1, 190)
        long = textfit.fit_display("Supercalifragilistic", 580, 2, 190)
        self.assertLess(long, short)
        self.assertLessEqual(textfit.width("Supercalifragilistic", long, "Unbounded", 800, -0.03), 580)

    def test_budget_cap_blocks_optional_passes(self):
        import draft
        with mock.patch.dict(draft.SPEND, {"usd": 0.4999, "calls": 5}), \
                mock.patch.dict(os.environ, {"JUA_WEEKLY_BUDGET_USD": "0.50"}):
            self.assertFalse(draft.can_afford(10000, 5000))
            self.assertEqual(draft.critique([{"id": "x", "template": "hack"}]), {})   # skipped, no API call
        with mock.patch.dict(draft.SPEND, {"usd": 0.0, "calls": 0}):
            self.assertTrue(draft.can_afford(10000, 5000))

    def test_spend_is_counted_from_real_usage(self):
        import draft
        body = json.dumps({"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
                           "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000}}).encode()
        resp = mock.MagicMock(); resp.read.return_value = body; resp.__enter__.return_value = resp
        with mock.patch.dict(draft.SPEND, {"usd": 0.0, "calls": 0}), \
                mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k", "JUA_MODEL": ""}), \
                mock.patch.object(draft.urllib.request, "urlopen", lambda req, timeout: resp):
            draft.call_claude("s", "u", model="claude-haiku-4-5-20251001")
            self.assertAlmostEqual(draft.SPEND["usd"], 1.0 + 0.5)   # $1/M in + $5/M out


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

    def test_workspace_header_only_when_set(self):
        seen = []
        def fake(req, timeout):
            seen.append({k.lower(): v for k, v in req.header_items()})
            return self._ok()
        with mock.patch.object(self.draft.urllib.request, "urlopen", fake):
            self.draft.call_claude("s", "u")
            with mock.patch.dict(os.environ, {"ANTHROPIC_WORKSPACE_ID": " wrkspc_123 "}):
                self.draft.call_claude("s", "u")
        self.assertNotIn("anthropic-workspace-id", seen[0])
        self.assertEqual(seen[1]["anthropic-workspace-id"], "wrkspc_123")

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

    def test_bubbles_that_cannot_fit_are_rejected_at_draft_time(self):
        long = "Manze, hii CV imeandikwa na AI na bado haijaniletea kazi hata moja wiki hii."
        panels = [{"bg": "jua", "left": {"who": "student", "pose": "phone", "say": long, "sms": long[:88]},
                   "right": {"who": "techie", "pose": "think"}}] + self.PANELS[1:]
        r = guard.check({"id": "c-3", "template": "vichekesho", "title": "t", "punch": "p", "caption": "x", "panels": panels})
        self.assertTrue(any("too long to fit" in e for e in r.errors), r.errors)
        ok = guard.check({"id": "c-4", "template": "vichekesho", "title": "t", "punch": "p", "caption": "x",
                          "panels": self.PANELS})
        self.assertFalse(any("fit" in e for e in ok.errors), ok.errors)

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

        def fake_claude(system, user, max_tokens=12000, **_kw):
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
    @property
    def PAST(self):
        return (pl.now() - dt.timedelta(hours=1)).isoformat()

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
