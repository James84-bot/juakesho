"""Tests for the autopilot: planning, approvals, publishing rules and the content guard.
Run: python -m unittest discover -s tests -v   (no network, no credentials needed)"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):   # AI keys never reach the tests: no real calls, no spend
    os.environ.pop(_k, None)
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import posted as _posted  # noqa: E402
_posted.feed_items = lambda: []   # tests never read live news feeds

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
        cal = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))["slots"]
        expected = sum(1 + s["carousel"]["slides"] for s in cal if s.get("carousel"))
        self.assertEqual(len([p for p in data["posts"] if p.get("group")]), expected)  # cover + slides per carousel
        self.assertEqual(len(data["posts"]), len(cal) - len([s for s in cal if s.get("carousel")]) + expected)
        self.assertEqual(len({p["id"] for p in data["posts"]}), len(data["posts"]))  # unique ids

    def test_plan_is_idempotent(self):
        a = pl.plan("2026-W41")
        a["posts"][0]["status"] = "approved"
        pl.save_week(a)
        b = pl.plan("2026-W41")
        self.assertEqual(b["posts"][0]["status"], "approved")


class HotPostTests(TempWeeks):
    def test_one_hot_post_a_day_with_time_to_approve(self):
        morning = dt.datetime(2026, 10, 13, 9, 5, tzinfo=pl.EAT)
        with mock.patch.object(pl, "now", lambda: morning):
            label = pl.hot_slot(mock=True)
            self.assertEqual(label, "2026-W42")
            post = pl.load_week(label)["posts"][-1]
            self.assertEqual((post["id"], post["template"], post["status"], post["hot"]), ("2026-w42-hot-1013", "sauti", "planned", True))
            self.assertEqual(post["publish_at"], "2026-10-13T18:30:00+03:00")
            self.assertIsNone(pl.hot_slot(mock=True))   # never twice a day
        late = dt.datetime(2026, 10, 14, 17, 0, tzinfo=pl.EAT)
        with mock.patch.object(pl, "now", lambda: late):
            pl.hot_slot(mock=True)
            post = pl.load_week("2026-W42")["posts"][-1]
            self.assertEqual(post["publish_at"], "2026-10-14T20:00:00+03:00")   # 3 hours to approve


class ReachTests(unittest.TestCase):
    def test_receipts_comment_and_whatsapp_text(self):
        post = {"claim_source": "Capital FM, 12 Oct 2026 (link)", "source": "Auditor-General report 2025; Capital FM",
                "beats": ["*Sh304bn.* Idle.", "59% never used.", "14 projects waiting.", "Ask your MP."], "message": "m"}
        c = pl.receipts_comment(post)
        self.assertTrue(c.startswith("Receipts"))
        self.assertIn("Auditor-General", c)
        self.assertIsNone(pl.receipts_comment({"source": "Rehearsal sample: not real data"}))
        w = pl.whatsapp_text(post)
        self.assertTrue(w.startswith("Sh304bn. Idle. 59% never used. 14 projects waiting."))
        self.assertIn("Receipts: Auditor-General report 2025", w)


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

    def test_collect_routes_comment_taps(self):
        import engage
        engage.save(pl.STATE, {"seen": ["17"], "pending": {"17": {"platform": "ig", "reply": "Asante", "post_id": "a",
                                                                    "action": "reply"}}})
        updates = {"ok": True, "result": [
            {"update_id": 20, "callback_query": {"id": "a", "data": "c|r|17", "message": {"chat": {"id": 42}}}}]}
        calls = []

        def fake(method, url, fields=None, files=None, timeout=60):
            calls.append((url.rsplit("/", 1)[-1].split("?")[0], fields))
            return updates if url.endswith("getUpdates") else {"ok": True, "id": "r1"}

        with mock.patch.object(pl, "http", fake):
            pl.collect()
        self.assertIn(("answerCallbackQuery", {"callback_query_id": "a", "text": "replied"}), calls)
        self.assertEqual(engage.load(pl.STATE)["pending"], {})

    def test_remake_replans_the_rest_of_the_week_from_the_calendar(self):
        self.week([{"id": "p1", "status": "awaiting", "template": "hack", "publish_at": "2026-10-07T07:30:00+03:00"},
                   {"id": "p2", "status": "approved", "template": "sauti", "publish_at": "2026-10-08T18:30:00+03:00"},
                   {"id": "h", "hot": True, "status": "awaiting", "publish_at": "2026-10-05T18:30:00+03:00"}])
        with mock.patch.object(pl, "now", lambda: dt.datetime(2026, 10, 6, 20, 0, tzinfo=pl.EAT)):   # Tuesday evening
            ids = pl.remake("2026-W41")
        posts = {p["id"]: p for p in pl.load_week("2026-W41")["posts"]}
        self.assertIn("p2", posts)
        self.assertIn("h", posts)
        self.assertNotIn("p1", posts)   # an undecided old post is dropped, its old card now matches nothing
        days = sorted({posts[i]["publish_at"][:10] for i in ids})
        self.assertTrue(all(d >= "2026-10-07" for d in days))   # nothing planned in the past
        self.assertNotIn("2026-10-08", days)                    # the approved post's day is not doubled
        self.assertTrue(all(i.endswith("-r2") for i in ids))
        self.assertTrue(all(posts[i]["status"] == "planned" for i in ids))
        self.assertEqual(pl.apply_decision(pl.load_week("2026-W41"), "p1", True), [])
        self.assertEqual(pl._next_rev("p1-r2"), "p1-r3")

    def test_rephoto_keeps_words_new_ids_whole_carousel(self):
        self.week([{"id": "p1", "status": "awaiting", "line": "kept", "photo_query": "x", "photo_file": "f", "photo_credit": "c",
                    "publish_at": "2026-10-05T07:15:00+03:00"},
                   {"id": "p2", "status": "approved", "photo_query": "x", "publish_at": "2026-10-05T07:15:00+03:00"},
                   {"id": "c-1", "group": "c", "status": "awaiting", "photo_query": "y", "publish_at": "2026-10-05T07:15:00+03:00"},
                   {"id": "c-2", "group": "c", "status": "awaiting", "publish_at": "2026-10-05T07:15:00+03:00"}])
        pl.rephoto("2026-W41")
        posts = {p["id"]: p for p in pl.load_week("2026-W41")["posts"]}
        self.assertEqual(set(posts), {"p1-r2", "p2", "c-1-r2", "c-2-r2"})
        self.assertEqual(posts["p1-r2"]["line"], "kept")
        self.assertNotIn("photo_file", posts["p1-r2"])
        self.assertEqual({posts["c-1-r2"]["group"], posts["c-2-r2"]["group"]}, {"c-r2"})
        self.assertEqual(posts["p1-r2"]["status"], "drafted")

    def test_send_reels_only_waiting_videos(self):
        self.week([{"id": "v1", "status": "awaiting", "publish_at": "2026-10-05T07:15:00+03:00"},
                   {"id": "v2", "status": "approved", "publish_at": "2026-10-05T07:15:00+03:00"},
                   {"id": "v3", "status": "awaiting", "publish_at": "2026-10-05T07:15:00+03:00"}])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pl, "EXPORTS", Path(d)):
            (Path(d) / "2026-W41").mkdir()
            for i in ("v1", "v2"):
                (Path(d) / "2026-W41" / f"{i}.mp4").write_bytes(b"x")
            self.assertEqual(pl.send_reels("2026-W41", dry_run=True), 1)

    def test_collect_queues_a_clip_from_the_owner_only(self):
        import tazama
        updates = {"ok": True, "result": [
            {"update_id": 30, "message": {"message_id": 1, "chat": {"id": 42}, "caption": "ruhusa @kevo254 DM\nMCA road",
                                          "video": {"file_id": "F1", "file_size": 1000, "duration": 20}}},
            {"update_id": 31, "message": {"message_id": 2, "chat": {"id": 999}, "caption": "yangu",
                                          "video": {"file_id": "F2", "file_size": 1000}}}]}
        sent = []

        def fake(method, url, fields=None, files=None, timeout=60):
            sent.append(url.rsplit("/", 1)[-1])
            return updates if url.endswith("getUpdates") else {"ok": True}
        with mock.patch.object(tazama, "STATE_FILE", pl.STATE / "clips.json"), mock.patch.object(pl, "http", fake):
            pl.collect()
            clips = tazama.load()["clips"]
        self.assertEqual([c["file_id"] for c in clips], ["F1"])
        self.assertIn("sendMessage", sent)


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
                "caption": "Set It Straight. Send this to a friend.\n\n#KenyansAreAsking"}
        post.update(kw)
        return post

    def test_symbols_are_validated(self):
        self.assertTrue(guard.check(self.base_straight()).ok)
        r = guard.check(self.base_straight(symbol="dragon"))
        self.assertTrue(any("unknown symbol" in e for e in r.errors))

    def test_set_it_straight_needs_claim_source_and_never_attacks_people(self):
        self.assertTrue(any("claim_source" in e for e in guard.check(self.base_straight(claim_source="")).errors))
        r = guard.check(self.base_straight(pride="She is a liar and a fraud."))
        self.assertTrue(any("not the person" in e for e in r.errors))
        r = guard.check(self.base_straight(pride="The governor is a thief."))
        self.assertTrue(any("not the person" in e for e in r.errors))
        r = guard.check(self.base_straight(verdict="lies"))
        self.assertFalse(r.ok)

    def test_quoted_insults_are_still_blocked(self):
        r = guard.check(self.base_straight(claim="Kenyans are stupid and lazy people."))
        self.assertTrue(any("not clean" in e for e in r.errors))
        r = guard.check(self.base_straight(photo_query="drunk party crowd"))
        self.assertTrue(any("not clean" in e for e in r.errors))

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
                "symbol": "music", "caption": "Put Us On. Share this.\n\n#KenyansAreAsking"}
        self.assertTrue(guard.check({**spot, "person_photo": "people/amina.jpg", "photo_rights": "permission from her manager, Oct 2026"}).ok)
        self.assertTrue(any("photo_rights" in e for e in guard.check({**spot, "person_photo": "people/amina.jpg"}).errors))
        self.assertTrue(any("must be" in e for e in guard.check({**spot, "person_photo": "https://instagram.com/x.jpg"}).errors))
        hack = {"id": "x-hack", "template": "hack", "hook": "h", "title": "t", "moves": ["a", "b"], "payoff": "p",
                "caption": "Save this.", "person_photo": "commons:File:X.jpg"}
        self.assertTrue(any("only on Put Us On" in e for e in guard.check(hack).errors))

    def test_public_office_holders_on_the_record(self):
        # Allowed: a named office holder's own public statement, their licensed photo, their office, sourced facts
        on_record = self.base_straight(who="A. Name, Cabinet Secretary (TV interview, 3 Oct 2026)",
                                       person_photo="commons:File:A_Name_official.jpg", person_role="Cabinet Secretary")
        self.assertTrue(guard.check(on_record).ok, guard.check(on_record).errors)
        self.assertTrue(any("person_role" in e for e in guard.check({**on_record, "person_role": ""}).errors))
        # Names of politicians are no longer banned; telling people how to vote is
        self.assertTrue(guard.check(self.base_straight(who="Ruto, State House statement, 3 Oct")).ok)
        self.assertTrue(any("party-campaigning" in e for e in guard.check(self.base_straight(pride="Vote them out in 2027.")).errors))
        # Serious allegations must be attributed to the record
        r = guard.check(self.base_straight(proof=["The Auditor-General found Sh2bn was looted.", "b", "c"]))
        self.assertTrue(any("allegation" in w for w in r.warnings))

    def test_nicknames_people_relate_to(self):
        post = self.base_straight(pride="The Botanist promised. The record says otherwise.")
        self.assertTrue(any("needs the real name" in e for e in guard.check(post).errors))
        self.assertTrue(guard.check({**post, "who": "William Ruto, President (State House, 3 Oct)"}).ok)
        mocking = self.base_straight(who="William Ruto, President", pride="Zakayo strikes again.")
        self.assertTrue(any("mocking nickname" in e for e in guard.check(mocking).errors))
        quoted = self.base_straight(who="William Ruto, President", pride='Kenyans call him "Zakayo". Here are the numbers.')
        self.assertTrue(guard.check(quoted).ok, guard.check(quoted).errors)
        slogan = self.base_straight(pride="Wantam!")
        self.assertTrue(any("campaign slogan" in e for e in guard.check(slogan).errors))
        checked = self.base_straight(claim="Wantam will fix the economy overnight.")
        self.assertFalse(any("campaign slogan" in e for e in guard.check(checked).errors))

    def test_campaigning_and_violence_blocked_civic_education_allowed(self):
        self.assertTrue(any("party-campaigning" in e for e in guard.check(self.base_straight(pride="Vote for Ruto.")).errors))
        self.assertTrue(guard.check(self.base_straight(pride="Register, then vote for six leaders.")).ok)
        self.assertTrue(any("violence" in e for e in guard.check(self.base_straight(pride="Storm parliament.")).errors))
        self.assertTrue(guard.check(self.base_straight(pride="Show up for public participation.")).ok)

    def test_promise_tracker_schema(self):
        import draft
        sample = {**draft.MOCK_SAMPLES["promise"], "id": "w-3"}
        self.assertTrue(guard.check(sample).ok, guard.check(sample).errors)
        self.assertFalse(guard.check({**sample, "verdict": "lies"}).ok)
        self.assertFalse(guard.check({**sample, "measure": "x" * 17}).ok)
        self.assertFalse(guard.check({**sample, "source": ""}).ok)

    def test_commons_scene_photos_licence_filtered_and_credited(self):
        import photos
        def page(i, lic, w=1600, mime="image/jpeg"):
            return {"index": i, "imageinfo": [{"mime": mime, "width": w, "height": 1100, "url": f"https://x.test/{i}.jpg",
                    "thumburl": f"https://x.test/{i}-t.jpg", "descriptionurl": f"https://c.test/{i}",
                    "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": f"<a>Artist {i}</a>"},
                                    "Categories": {"value": "Matatu stages in Nairobi"}}}]}
        api = {"query": {"pages": {"1": page(1, "CC BY-SA 4.0"), "2": page(2, "CC BY 4.0", w=600),
                                   "3": page(3, "CC BY 4.0"), "4": page(4, "CC BY-NC 2.0")}}}
        calls = []
        def fake_get(url, headers=None, timeout=30):
            calls.append(url)
            return json.dumps(api).encode() if "api.php" in url else b"JPEG"
        with tempfile.TemporaryDirectory() as d, mock.patch.object(photos, "_get", fake_get), \
                mock.patch.object(photos, "faces_ok", lambda data: True), mock.patch.dict(os.environ, {"PEXELS_API_KEY": ""}):
            got = photos.fetch({"id": "w-1", "photo_query": "matatu stage Nairobi"}, Path(d))
            self.assertEqual(Path(got["file"]).read_bytes(), b"JPEG")
            # 1 (BY-SA) and 3 (BY) qualify; 2 is too small and 4 is non-commercial
            self.assertRegex(got["credit"], r"Artist [13] / Wikimedia Commons, CC BY(-SA)? 4.0")
            self.assertRegex(calls[-1], r"/[13]-t\.jpg$")
            again = photos.fetch({"id": "w-1", "photo_query": "matatu stage Nairobi"}, Path(d))
            self.assertEqual(again["credit"], got["credit"])   # cached: stable across re-renders
        with tempfile.TemporaryDirectory() as d, mock.patch.object(photos, "_get", side_effect=OSError("offline")):
            self.assertIsNone(photos.fetch({"id": "w-2", "photo_query": "Nairobi"}, Path(d)))   # never raises

    def test_kenyan_story_never_gets_a_foreign_photo(self):
        import photos
        def page(i, title, cats):
            return {"index": i, "title": title, "imageinfo": [{"mime": "image/jpeg", "width": 1600, "height": 1100,
                    "url": f"https://x.test/{i}.jpg", "thumburl": f"https://x.test/{i}.jpg",
                    "extmetadata": {"LicenseShortName": {"value": "CC BY 2.0"}, "Artist": {"value": f"A{i}"},
                                    "Categories": {"value": cats}}}]}
        api = {"query": {"pages": {"1": page(1, "File:Capitol riot tear gas.jpg", "Washington, D.C."),
                                   "2": page(2, "File:Nairobi protest 2024.jpg", "Protests in Kenya|Nairobi")}}}
        fake = lambda url, headers=None, timeout=30: json.dumps(api).encode() if "api.php" in url else b"JPEG"
        with mock.patch.object(photos, "_get", fake), mock.patch.object(photos, "faces_ok", lambda data: True):
            got = photos.commons("police tear gas protest Kenya", "x")
        self.assertIn("A2", got[1]["credit"])

    def test_marker_emphasis(self):
        import render
        self.assertEqual(str(render.mark("We pay *4.25%* & wait")), "We pay <mark>4.25%</mark> &amp; wait")
        self.assertTrue(any("unbalanced" in e for e in guard.check(self.base_straight(truth="*54 countries.")).errors))

    def test_divisive_politics_called_out_never_practised(self):
        callout = self.base_straight(claim="Our people must not let those people take this county.",
                                     who="A. Name, MP (rally, 3 Oct 2026)", truth="That is *tribal politics*, and hate speech is an offence.")
        self.assertTrue(guard.check(callout).ok, guard.check(callout).errors)
        named = self.base_straight(truth="He attacked the Kalenjins.")
        self.assertTrue(any("names a community" in e for e in guard.check(named).errors))
        hack = {"id": "x-hack", "template": "decode", "hook": "h", "word": "Tribe", "meaning": "m", "try_this": "t",
                "number": "1", "caption": "Save this."}
        self.assertTrue(any("tribe only comes up" in e for e in guard.check(hack).errors))

    def test_ai_sounding_copy_blocked(self):
        r = guard.check(self.base_straight(pride="Let's delve into it \u2014 a pivotal moment."))
        self.assertTrue(sum("sounds AI-written" in e for e in r.errors) >= 2)

    def test_evidence_log_on_publish(self):
        import pipeline
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pipeline, "STATE", Path(d)):
            pipeline.record_evidence([{"id": "w-1", "status": "published", "claim": "c", "source": "s", "ink": {"1": "#FFFFFF"}}])
            rows = [json.loads(l) for l in (Path(d) / "evidence.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows, [{"id": "w-1", "claim": "c", "source": "s"}])

    def test_hatutasahau_and_chapter_six_samples_pass(self):
        import draft
        for tpl in ("kumbuka", "scorecard"):
            sample = {**draft.MOCK_SAMPLES[tpl], "id": f"w-{tpl}"}
            self.assertTrue(guard.check(sample).ok, (tpl, guard.check(sample).errors))
        bad = {**draft.MOCK_SAMPLES["scorecard"], "id": "w-s", "checks": [{"test": "x", "result": "maybe", "note": "n"}]}
        self.assertFalse(guard.check(bad).ok)

    def test_anniversary_takes_the_nearest_weekday(self):
        import pipeline
        posts = [{"id": f"2025-w26-d{d}-hack", "template": "hack", "publish_at": f"2025-06-{22 + d:02d}T12:00:00+03:00"} for d in range(1, 8)]
        posts[6]["size"] = "story"
        with mock.patch.object(pipeline, "HERE", HERE):
            pipeline._anniversaries(posts, 2026, dt.date(2026, 6, 25).isocalendar()[1])   # 25 June 2026: anniversary week
        # the planner works on 2026 dates; rebuild posts for that week
        week = dt.date(2026, 6, 25).isocalendar()[1]
        posts = [{"id": f"2026-w{week}-d{d}-hack", "template": "hack",
                  "publish_at": dt.date.fromisocalendar(2026, week, d).isoformat() + "T12:00:00+03:00"} for d in range(1, 8)]
        posts[6]["size"] = "story"
        pipeline._anniversaries(posts, 2026, week)
        hit = [p for p in posts if p["template"] == "kumbuka"]
        self.assertTrue(hit)
        self.assertTrue(all(dt.date.fromisoformat(p["publish_at"][:10]).isoweekday() <= 5 for p in hit))
        self.assertTrue(any(p["remember"]["date"].endswith("-06-25") for p in hit))

    def test_reel_beats(self):
        import render, video
        ok = self.base_straight(beats=["Check your payslip.", "*4.25%* gone.", "Tunalipa. *Tunapata nini?*"])
        self.assertTrue(guard.check(ok).ok, guard.check(ok).errors)
        long = self.base_straight(beats=["This line is far too long to read in one second on a phone", "b", "c"])
        self.assertTrue(any("punchy line" in e for e in guard.check(long).errors))
        self.assertTrue(any("3-6" in e for e in guard.check(self.base_straight(beats=["a"])).errors))
        self.assertEqual(render.beat_tokens("We pay *4.25% now* ok"), [("We", False), ("pay", False), ("4.25%", True), ("now", True), ("ok", False)])
        self.assertTrue(render.BEAT["min"] <= render.beat_seconds("one two three four five six seven eight") <= render.BEAT["max"])
        reel = video.beat_reel({**ok, "id": "x"})
        self.assertEqual((reel["template"], reel["size"], reel["kicker"]), ("reel", "story", "Set It Straight"))
        self.assertIsNone(video.beat_reel({"id": "y", "template": "hack", "beats": ["a", "b"]}))

    def test_music_picked_by_mood_only_with_rights(self):
        import video
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for f in ("drum.mp3", "song.mp3", "norights.mp3"):
                (d / f).write_bytes(b"x")
            (d / "tracks.json").write_text(json.dumps({"tracks": [
                {"file": "drum.mp3", "mood": "urgent", "rights": "Pixabay licence, page saved", "clean": True},
                {"file": "song.mp3", "mood": "uplifting", "rights": "permission by email 12 Oct", "clean": True},
                {"file": "norights.mp3", "mood": "any", "rights": "", "clean": True}]}))
            with mock.patch.object(video, "MUSIC", d):
                self.assertEqual(video.music_track({"id": "a", "template": "sauti"})["file"], "drum.mp3")
                self.assertEqual(video.music_track({"id": "b", "template": "africa"})["file"], "song.mp3")
                self.assertIsNone(video.music_track({"id": "c", "template": "africa", "track": "norights.mp3"}))

    def test_manual_post_decision(self):
        data = {"posts": [{"id": "r1", "status": "awaiting"}]}
        self.assertEqual(pl.apply_decision(data, "r1", "manual"), ["r1"])
        self.assertEqual(data["posts"][0]["status"], "manual")
        self.assertIn("m|w|r1", pl._buttons("w|r1", reel=True))
        self.assertNotIn("m|", pl._buttons("w|r1"))

    def test_news_feed_parsing_and_prompt(self):
        import news
        rss = b"""<rss><channel>
<item><title>MPs pass Finance Bill - Capital FM</title><link>https://x.test/1</link><source url="https://c.test">Capital FM</source>
<pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>MPs pass the Finance Bill</title><link>https://x.test/2</link><pubDate>Mon, 12 Oct 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""
        items = news.parse(rss, "Feed")
        self.assertEqual(items[0]["title"], "MPs pass Finance Bill")
        self.assertEqual(items[0]["outlet"], "Capital FM")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(news, "OUT", Path(d) / "n.json"), \
                mock.patch.object(news, "_get", lambda url, timeout=20: rss), \
                mock.patch.object(news, "MAX_AGE", dt.timedelta(days=36500)):
            data = news.collect()
            self.assertEqual(len(data["items"]), 1)   # the same story from two feeds counts once
            self.assertIn("https://x.test/1", news.prompt_block())

    def test_commons_licences(self):
        import photos
        for ok in ("CC0", "Public domain", "CC BY 4.0", "CC BY 2.0", "CC BY-SA 4.0", "CC BY-SA 3.0"):
            self.assertTrue(photos._licence_ok(ok), ok)
        for bad in ("CC BY-NC 2.0", "CC BY-NC-SA 4.0", "CC BY-ND 4.0", "All rights reserved", "Fair use"):
            self.assertFalse(photos._licence_ok(bad), bad)

    def test_music_only_with_rights_and_credited(self):
        import video
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(video, "MUSIC", Path(tmp)):
            Path(tmp, "a.mp3").write_bytes(b"x")
            Path(tmp, "tracks.json").write_text(json.dumps({"tracks": [
                {"file": "a.mp3", "artist": "Amina", "title": "Kesho", "rights": "permission by email, Oct 2026", "clean": True},
                {"file": "b.mp3", "artist": "X", "title": "Y", "rights": "", "clean": True},
                {"file": "d.mp3", "artist": "Z", "title": "W", "rights": "permission by email, Oct 2026"}]}))
            Path(tmp, "b.mp3").write_bytes(b"x")
            Path(tmp, "d.mp3").write_bytes(b"x")
            self.assertEqual(video.music_track({"track": "a.mp3"})["artist"], "Amina")
            self.assertIsNone(video.music_track({"track": "b.mp3"}))       # no rights recorded
            self.assertIsNone(video.music_track({"track": "d.mp3"}))       # lyrics not confirmed clean
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

    def test_photos_skip_quietly_when_no_source_answers(self):
        import photos
        post = {"id": "p1", "photo_query": "farm at sunrise"}
        with mock.patch.dict(os.environ, {"PEXELS_API_KEY": ""}), \
                mock.patch.object(photos, "_get", side_effect=OSError("offline")):   # no network in tests
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
        self.assertLessEqual(textfit.width("Supercalifragilistic", long, *textfit.DISPLAY), 580)

    def test_budget_cap_blocks_optional_passes(self):
        import draft
        def no_call(*a, **k):
            raise AssertionError("the API must not be called once the budget (and the critic's slack) is spent")
        with mock.patch.dict(draft.SPEND, {"usd": 0.4999, "calls": 5}), mock.patch.object(draft, "call_claude", no_call), \
                mock.patch.dict(os.environ, {"JUA_WEEKLY_BUDGET_USD": "0.50", "JUA_PROVIDER": "anthropic"}):
            self.assertFalse(draft.can_afford(10000, 5000))
            self.assertTrue(draft.can_afford(2000, 600, draft.critic_model(), slack=draft.CRITIC_SLACK))  # the editor still runs
        with mock.patch.dict(draft.SPEND, {"usd": 0.80, "calls": 9}), mock.patch.object(draft, "call_claude", no_call), \
                mock.patch.dict(os.environ, {"JUA_WEEKLY_BUDGET_USD": "0.50", "JUA_PROVIDER": "anthropic"}):
            self.assertEqual(draft.critique([{"id": "x", "template": "hack"}]), {})   # past the slack too: skipped
        with mock.patch.dict(draft.SPEND, {"usd": 0.0, "calls": 0}):
            self.assertTrue(draft.can_afford(10000, 5000))

    def test_spend_is_counted_from_real_usage(self):
        import draft
        body = json.dumps({"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
                           "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000}}).encode()
        resp = mock.MagicMock(); resp.read.return_value = body; resp.__enter__.return_value = resp
        with mock.patch.dict(draft.SPEND, {"usd": 0.0, "calls": 0}), \
                mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k", "JUA_MODEL": "", "JUA_PROVIDER": "anthropic"}), \
                mock.patch.object(draft.urllib.request, "urlopen", lambda req, timeout: resp):
            draft.call_claude("s", "u", model="claude-haiku-4-5-20251001")
            self.assertAlmostEqual(draft.SPEND["usd"], 1.0 + 0.5)   # $1/M in + $5/M out


class FreeProviderTests(unittest.TestCase):
    """Gemini free tier: used when its key is set; small batches fit the free quota."""

    def setUp(self):
        import draft
        self.draft = draft
        self.patches = [mock.patch.dict(os.environ, {"GEMINI_API_KEY": "gm-test", "ANTHROPIC_API_KEY": "a", "JUA_PROVIDER": "",
                                                     "JUA_GEMINI_MODEL": ""}),
                        mock.patch.object(draft.time, "sleep", lambda s: None),
                        mock.patch.dict(draft.SPEND, {"usd": 0.0, "calls": 0})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    @staticmethod
    def _reply(text="ok", finish="STOP"):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]}).encode()
        resp.headers = {"Content-Type": "application/json"}
        resp.__enter__.return_value = resp
        return resp

    def test_free_writer_when_its_key_is_set(self):
        self.assertEqual(self.draft.provider(), "gemini")
        seen = []
        def fake(req, timeout):
            seen.append((req.full_url, req.get_header("X-goog-api-key"), json.loads(req.data)))
            return self._reply("hi")
        with mock.patch.object(self.draft.urllib.request, "urlopen", fake):
            self.assertEqual(self.draft.call_claude("sys", "user", max_tokens=99999), "hi")
        url, key, body = seen[0]
        self.assertEqual(url, self.draft.GEMINI_URL.format(model=self.draft.GEMINI_MODELS[0]))
        self.assertEqual(key, "gm-test")
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], self.draft.GEMINI_LIMITS["out"] + self.draft.GEMINI_THINK_ROOM)  # reply + room to think
        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "sys"}]})
        self.assertEqual(self.draft._price("anything"), (0.0, 0.0))      # costs nothing

    def test_provider_choice(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertEqual(self.draft.provider(), "anthropic")          # only the Claude key: Claude
        with mock.patch.dict(os.environ, {"JUA_PROVIDER": "anthropic"}):
            self.assertEqual(self.draft.provider(), "anthropic")          # forced
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                self.draft.call_claude("s", "u")                          # no key: a clear message

    def test_falls_back_when_a_model_is_unavailable(self):
        import io, urllib.error
        tried = []
        def fake(req, timeout):
            m = req.full_url.split("/models/")[1].split(":")[0]
            tried.append(m)
            if m == self.draft.GEMINI_MODELS[0]:
                raise urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b'{"error":"model not found"}'))
            return self._reply("from fallback")
        with mock.patch.object(self.draft.urllib.request, "urlopen", fake):
            self.assertEqual(self.draft.call_claude("s", "u"), "from fallback")
        self.assertEqual(tried, self.draft.GEMINI_MODELS[:2])

    def test_cut_off_reply_non_json_and_call_cap(self):
        with mock.patch.object(self.draft.urllib.request, "urlopen", lambda req, timeout: self._reply("{", "MAX_TOKENS")):
            with self.assertRaisesRegex(RuntimeError, "cut off"):
                self.draft.call_claude("s", "u")
        bad = mock.MagicMock()
        bad.read.return_value = b"OK\r\n"
        bad.headers = {"Content-Type": "text/plain"}
        bad.__enter__.return_value = bad
        with mock.patch.object(self.draft.urllib.request, "urlopen", lambda req, timeout: bad):
            with self.assertRaisesRegex(RuntimeError, "not JSON"):
                self.draft.call_claude("s", "u")
        with mock.patch.dict(self.draft.SPEND, {"calls": self.draft.GEMINI_LIMITS["calls"]}):
            with self.assertRaisesRegex(RuntimeError, "call cap"):
                self.draft.call_claude("s", "u")

    def test_elevate_survives_a_skipped_critic_batch(self):
        posts = [{"id": "a", "template": "hack", "status": "drafted"}, {"id": "b", "template": "hack", "status": "drafted"}]
        with mock.patch.object(self.draft, "critique", lambda ps: {"a": {"avg": 8.0, "note": "good"}}), \
                mock.patch.object(self.draft, "call_claude", side_effect=AssertionError("no rewrite needed")):
            out = self.draft.elevate("2026-W42", [], {}, posts)   # "b" was never scored: not weak, no crash
        self.assertEqual(out[0]["critic"]["avg"], 8.0)
        self.assertNotIn("critic", out[1])

    def test_batches_keep_carousels_whole(self):
        slots = [{"id": f"s{i}"} for i in range(3)] + [{"id": f"c{i}", "group": "g"} for i in range(6)] + [{"id": "s9"}]
        out = self.draft.batches(slots)
        self.assertTrue(all(len(b) <= 4 or all(x.get("group") == "g" for x in b) for b in out))
        self.assertEqual(sum(len(b) for b in out), len(slots))
        self.assertTrue(any(len([x for x in b if x.get("group") == "g"]) == 6 for b in out))


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
        self.env = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "JUA_MODEL": "", "JUA_PROVIDER": "anthropic"})
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



class HttpRetryTests(unittest.TestCase):
    def test_timeout_is_retried_and_token_never_in_error(self):
        calls = []

        def boom(req, timeout):
            calls.append(timeout)
            raise TimeoutError("The read operation timed out")
        with mock.patch.object(pl.urllib.request, "urlopen", boom), mock.patch.object(pl.time, "sleep", lambda s: None):
            with self.assertRaises(RuntimeError) as cm:
                pl.http("POST", "https://api.telegram.org/botSECRET123/sendVideo", {"a": 1}, {"video": __file__})
        self.assertEqual(len(calls), 3)
        self.assertGreaterEqual(calls[0], 240)          # uploads get a long timeout
        self.assertNotIn("SECRET123", str(cm.exception))

    def test_failed_upload_keeps_the_rest_of_the_batch(self):
        sent = []

        def card(chat, label, p, out_dir):
            if p["id"] == "bad":
                raise RuntimeError("timeout")
            sent.append(p["id"])
        data = {"week": "2026-W42", "posts": [{"id": "bad", "status": "rendered"}, {"id": "good", "status": "rendered"}]}
        with mock.patch.object(pl, "load_week", lambda l: data), mock.patch.object(pl, "save_week", lambda d: None), \
                mock.patch.object(pl, "need", lambda k: {k: "1"}), mock.patch.object(pl, "_send_card", card), \
                mock.patch.object(pl, "_notify", lambda t: None), mock.patch.object(pl, "balance_note", lambda d: None):
            pl.ask("2026-W42")
        self.assertEqual(sent, ["good"])
        self.assertEqual([p["status"] for p in data["posts"]], ["rendered", "awaiting"])


class ExpiryTests(TempWeeks):
    def test_untapped_card_expires_two_hours_after_its_slot(self):
        t = pl.now()
        self.week([{"id": "old", "status": "awaiting", "publish_at": (t - pl.dt.timedelta(hours=3)).isoformat()},
                   {"id": "soon", "status": "awaiting", "publish_at": (t - pl.dt.timedelta(minutes=30)).isoformat()},
                   {"id": "ok", "status": "approved", "publish_at": (t - pl.dt.timedelta(hours=5)).isoformat()}])
        notes = []
        with mock.patch.object(pl, "_notify", notes.append):
            self.assertEqual(pl.expire_unanswered(), ["old"])
        self.assertEqual([p["status"] for p in pl.load_week("2026-W41")["posts"]], ["expired", "awaiting", "approved"])
        self.assertEqual(len(notes), 1)
        data = pl.load_week("2026-W41")
        self.assertEqual(pl.apply_decision(data, "old", True), [])   # a late ✅ can't revive it


class HotSpacingTests(unittest.TestCase):
    def test_hot_post_moves_clear_of_a_planned_post(self):
        base = pl.dt.datetime(2026, 10, 14, 18, 30, tzinfo=pl.EAT)
        posts = [{"publish_at": base.isoformat(), "status": "approved"}]
        self.assertEqual(pl._clear_of(base, posts), base.replace(hour=20, minute=0))
        self.assertEqual(pl._clear_of(base, [{"publish_at": base.isoformat(), "status": "rejected"}]), base)


class PhotoSwapTests(TempWeeks):
    def setUp(self):
        super().setUp()
        t = pl.now() + pl.dt.timedelta(days=1)
        self.week([{"id": "p1-r3", "template": "sauti", "status": "awaiting", "publish_at": t.isoformat(), "tg_msg": 77,
                    "photo_file": "x.jpg", "photo_kind": "symbolic"}])
        self.sent = []
        self.root = Path(self.tmp.name)

    def intake(self, caption, reply_to=77, width=1600):
        msg = {"message_id": 5, "caption": caption, "photo": [{"file_id": "small", "width": 320}, {"file_id": "big", "width": width}],
               "chat": {"id": 42}}
        if reply_to:
            msg["reply_to_message"] = {"message_id": reply_to}

        def download(get_path, token, file_id, target):
            from PIL import Image
            Image.new("RGB", (width, 900), "red").save(target, "PNG")
        import tazama
        with mock.patch.object(pl, "tg", lambda m, f=None, files=None: self.sent.append((m, f)) or {"ok": True}), \
                mock.patch.object(pl, "ROOT", self.root), mock.patch.object(tazama, "download", download):
            pl._photo_intake(msg, "42")
        return pl.load_week("2026-W41")["posts"][0]

    def test_reply_with_own_photo_swaps_the_picture_and_resends(self):
        p = self.intake("yangu\nAt the Senate this morning")
        self.assertEqual((p["id"], p["status"]), ("p1-r4", "drafted"))
        self.assertTrue(p["photo"].startswith("sent:exports/2026-W41/photos/p1-r4-sent.jpg"))
        self.assertEqual(p["photo_rights_credit"], "Photo: Kenyans Are Asking")
        self.assertNotIn("photo_file", p)
        self.assertTrue((self.root / p["photo"][5:]).exists())

    def test_no_rights_line_no_swap(self):
        p = self.intake("nukuu Citizen TV")       # a TV station's photo needs their permission
        self.assertEqual(p["status"], "awaiting")
        self.assertIn("can't use it yet", self.sent[-1][1]["text"])

    def test_photo_not_replying_to_a_card_gets_the_how_to(self):
        p = self.intake("yangu", reply_to=None)
        self.assertEqual(p["status"], "awaiting")
        self.assertIn("reply to that post", self.sent[-1][1]["text"])

    def test_posted_photo_is_credited_and_agency_photo_refused(self):
        p = self.intake("chanzo @StateHouseKenya https://x.com/StateHouseKenya/status/1")
        self.assertEqual((p["status"], p["photo_use"]), ("drafted", "posted"))
        self.assertEqual(p["photo_rights_credit"], "Photo: @StateHouseKenya")
        self.assertIn("📷 Photo: @StateHouseKenya", pl.caption_for({**p, "caption": "c", "photo_credit": p["photo_rights_credit"]}))

    def test_agency_photo_is_refused(self):
        p = self.intake("chanzo Reuters/Monicah Mwangi")
        self.assertEqual(p["status"], "awaiting")
        self.assertIn("agency photo", self.sent[-1][1]["text"])

    def test_card_says_which_photo_it_carries(self):
        p = dict(pl.load_week("2026-W41")["posts"][0], caption="c")
        self.assertIn("Symbolic photo", pl._preview_text(p))
        self.assertIn("from the event", pl._preview_text({**p, "photo_kind": "event"}))

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
            # tragedy dropped; politics kept and flagged civic (sorted by traffic)
            self.assertEqual(titles, ["edwin sifuna presidential bid 2027", "man utd vs west ham"])
            self.assertTrue(data["safe"][0].get("civic"))
            self.assertFalse(data["safe"][1].get("civic"))
            self.assertEqual(len(data["dropped"]), 1)
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
        # far more text than the guard allows: even after auto-fit shrinks it, it overflows, and QA must catch it
        broken = {**good, "id": "qa-broken", "moves": ["Record the whole lecture on your phone and keep it safe " * 5] * 4}
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
