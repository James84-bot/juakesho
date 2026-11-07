"""Tazama Hii: clip rights, intake, window caps, captions and the guard (no network, no rendering)."""
import datetime as dt
import os
import sys
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):   # AI keys never reach the tests: no real calls, no spend
    os.environ.pop(_k, None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402
import tazama  # noqa: E402

NOW = dt.datetime(2026, 10, 12, 20, tzinfo=dt.timezone(dt.timedelta(hours=3)))


class Tazama(unittest.TestCase):
    def test_caption_must_say_where_the_clip_came_from(self):
        self.assertEqual(tazama.parse_caption("ruhusa @kevo254 DM 12 Oct\nMCA road promise")["rights"], "permission")
        self.assertEqual(tazama.parse_caption("yangu\nwe filmed the queue")["credit"], "Kenya on Record")
        q = tazama.parse_caption("nukuu Citizen TV https://youtu.be/x\nCS on teargas")
        self.assertEqual((q["rights"], q["credit"], q["source"]), ("quote", "Citizen TV", "https://youtu.be/x"))
        own = tazama.parse_caption("check this out\nthe queue at Huduma https://x.com/a/1")   # no rights line: yours
        self.assertEqual((own["rights"], own["credit"], own["source"]), ("owner", "", "https://x.com/a/1"))
        self.assertIn("queue at Huduma", own["note"])
        self.assertEqual(tazama.parse_caption("")["rights"], "owner")   # no caption at all is fine too
        self.assertIsNone(tazama.parse_caption("check this out", owner_default=False))
        self.assertIsNone(tazama.parse_caption("ruhusa"))   # permission from whom?

    def test_intake(self):
        video = {"file_id": "F", "file_size": 5_000_000, "duration": 30}
        reply, clip = tazama.intake({"video": video, "caption": "hii ni moto"}, NOW)
        self.assertEqual((clip["rights"], clip["credit"]), ("owner", ""))   # sent by you: used, no credit
        self.assertIn("posted at the next free slot", reply)
        self.assertNotIn("credit", reply)
        reply, clip = tazama.intake({"video": video, "caption": "ruhusa"}, NOW)
        self.assertIsNone(clip)   # asked for a credit but named nobody
        reply, clip = tazama.intake({"video": {**video, "file_size": 30_000_000}, "caption": "yangu"}, NOW)
        self.assertIsNone(clip)
        reply, clip = tazama.intake({"document": {**video, "mime_type": "video/mp4"}, "caption": "yangu\nqueue at Huduma"}, NOW)
        self.assertEqual((clip["status"], clip["rights"], clip["file_id"]), ("queued", "own", "F"))
        self.assertEqual(tazama.intake({"text": "hello"}, NOW), ("", None))

    def test_window_caps(self):
        self.assertEqual(tazama.window({"start": 3, "end": 30}, {"rights": "quote"}, 60), (3.0, 11.0))
        self.assertEqual(tazama.window({"start": 0, "end": 90}, {"rights": "permission"}, 60), (0.0, 40.0))
        self.assertEqual(tazama.window({"start": "x"}, {"rights": "own"}, 12), (0.0, 12.0))

    def test_captions_retimed_and_chunked(self):
        segs = [{"start": 2.0, "end": 6.0, "text": "one two three four five six seven eight"}, {"start": 20, "end": 22, "text": "late"}]
        caps = tazama.captions(segs, 2.0, 12.0)
        self.assertEqual([c["text"] for c in caps], ["one two three four five six seven", "eight"])
        self.assertEqual((caps[0]["start"], caps[1]["end"]), (0.0, 4.0))

    def test_box_even_and_inside_the_screen(self):
        for w, h in ((1280, 720), (720, 1280), (1080, 1080)):
            x, y, bw, bh = tazama.box({"w": w, "h": h})
            self.assertEqual((bw % 2, bh % 2), (0, 0))
            self.assertTrue(x >= 0 and bw <= 1080 and bh <= tazama.BOX_MAX_H and y + bh < 1700)

    def test_guard(self):
        post = {"id": "2026-w42-tazama-1", "template": "tazama", "headline": "Barabara *itajengwa kesho*",
                "credit": "@kevo254", "rights": "ruhusa @kevo254", "rights_kind": "permission",
                "hook": ["Watch what he promised."], "verdict": ["Same promise in *2022*.", "Kesho ni lini?"],
                "beats": ["Watch what he promised.", "Same promise in *2022*.", "Kesho ni lini?"],
                "caption": "c", "clip_window": [0, 20]}
        self.assertEqual(guard.check(post).errors, [])
        self.assertTrue(guard.check({**post, "rights_kind": ""}).errors)
        self.assertEqual(guard.check({**post, "rights_kind": "owner", "credit": ""}).errors, [])
        self.assertTrue(guard.check({**post, "rights_kind": "quote"}).errors)   # 20 s of news footage is too long


class OwnerClips(unittest.TestCase):
    def test_your_clip_has_no_credit_anywhere_and_is_approved_by_itself(self):
        import pipeline
        info = {"rights": "owner", "credit": ""}
        self.assertNotIn("📹", tazama.frame_html({"headline": "h"}, info, (48, 430, 984, 554)).split("class=\"credit\">")[1][:5])
        post = {"id": "w-tazama-1", "template": "tazama", "rights_kind": "owner", "credit": "", "caption": "c #KenyaOnRecord",
                "status": "awaiting", "guard": {"errors": [], "warnings": []}}
        self.assertNotIn("Video:", pipeline.caption_for(post))
        self.assertEqual(pipeline.auto_ok(post), "")
        self.assertTrue(pipeline.auto_ok({**post, "guard": {"errors": ["x"]}}))   # a failed rule still waits for you

    def test_your_clip_goes_out_clear_of_other_posts_and_never_at_night(self):
        import pipeline
        from unittest import mock
        eat = pipeline.EAT
        busy = {"posts": [{"publish_at": "2026-10-13T12:45:00+03:00", "status": "approved"}]}
        with mock.patch.object(pipeline, "now", lambda: dt.datetime(2026, 10, 13, 9, 0, tzinfo=eat)), \
                mock.patch.object(pipeline, "week_file", lambda l: Path(__file__)), \
                mock.patch.object(pipeline, "load_week", lambda l: busy):
            when = pipeline._clip_slot("2026-W42")
        self.assertGreaterEqual(abs(when - dt.datetime(2026, 10, 13, 12, 45, tzinfo=eat)), dt.timedelta(minutes=60))
        self.assertTrue(7 <= when.hour < pipeline.QUIET_FROM)
        late = {"posts": [{"publish_at": "2026-10-13T19:00:00+03:00", "status": "approved"},
                          {"publish_at": "2026-10-13T20:00:00+03:00", "status": "approved"}]}
        with mock.patch.object(pipeline, "now", lambda: dt.datetime(2026, 10, 13, 16, 30, tzinfo=eat)), \
                mock.patch.object(pipeline, "week_file", lambda l: Path(__file__)), \
                mock.patch.object(pipeline, "load_week", lambda l: late):
            when = pipeline._clip_slot("2026-W42")
        self.assertEqual((when.day, when.hour), (14, 9))   # 19:00 and 20:00 are taken, 21:00 is night: next morning

    def test_a_credited_clip_keeps_its_credit(self):
        import pipeline
        cap = pipeline.caption_for({"template": "tazama", "rights_kind": "permission", "credit": "@kevo254", "caption": "c"})
        self.assertIn("📹 Video: @kevo254", cap)


class Calm(unittest.TestCase):
    def test_urgent_not_shouty(self):
        self.assertEqual(guard._shouting(["Sh7.35bn unpaid. Your MP hasn't said how he'll vote on Thursday."]), "")
        self.assertIn("capitals", guard._shouting(["THEY STOLE OUR MONEY"]))
        self.assertIn("exclamation", guard._shouting(["Read this!!"]))
        self.assertIn("breaking", guard._shouting(["Breaking: the CS resigns"]).lower())
        self.assertIn("alarm", guard._shouting(["🚨🚨 Share this"]))
        self.assertEqual(guard._shouting(["IEBC, KRA and the MCA all said no. KSh 2bn gone."]), "")


class Action(unittest.TestCase):
    def test_every_new_post_says_what_to_do(self):
        import pipeline
        post = {"id": "w-a", "template": "sauti", "kicker": "Taxpayers", "line": "We pay *4.25%* in levies.",
                "fact": "1.5% housing levy and 2.75% SHIF, Finance Act 2023.", "source": "https://kra.go.ke",
                "photo_query": "payslip Kenya", "message": "We pay levies every month.", "caption": "What do we get? #KenyaOnRecord"}
        self.assertTrue(any("no `action`" in e for e in guard.check(post).errors))
        self.assertTrue(any("vague" in e for e in guard.check({**post, "action": "Stay informed."}).errors))
        ok = {**post, "action": "Ask your MP what the levy built: parliament.go.ke"}
        self.assertFalse([e for e in guard.check(ok).errors if "action" in e])
        cap = pipeline.caption_for(ok)
        self.assertIn("👉 Ask your MP", cap)
        self.assertTrue(cap.rstrip().endswith("#KenyaOnRecord"))   # the action sits above the hashtags


class Fairness(unittest.TestCase):
    def test_balance_note_flags_one_sided_weeks(self):
        import pipeline
        week = {"posts": [{"id": f"p{i}", "status": "awaiting", "side": "government", "tone": "criticism"} for i in range(4)]}
        note = pipeline.balance_note(week)
        self.assertIn("one side", note)
        self.assertIn("No credit yet", note)
        week["posts"] += [{"id": "o", "status": "awaiting", "side": "opposition", "tone": "criticism"},
                          {"id": "c", "status": "awaiting", "side": "government", "tone": "credit"}]
        note = pipeline.balance_note(week)
        self.assertNotIn("one side", note)
        self.assertNotIn("No credit", note)
        self.assertTrue(any("'side'" in e for e in guard.check({"id": "x", "template": "sauti", "side": "ruto"}).errors))


if __name__ == "__main__":
    unittest.main()


class WhoWhereWhen(unittest.TestCase):
    def test_civic_posts_say_who_where_when(self):
        post = {"id": "w-w", "template": "sauti", "kicker": "Taxpayers", "line": "The state owes *Sh7.35bn*.",
                "fact": "State agencies owe Kenya Power Sh7.35bn, Business Daily.", "source": "https://x",
                "photo_query": "power lines Kenya", "message": "m", "action": "Ask your MP: parliament.go.ke",
                "caption": "c #KenyaOnRecord"}
        errs = guard.check(post).errors
        self.assertTrue(all(any(f"no `{f}`" in e for e in errs) for f in ("who", "where", "when")))
        ok = {**post, "who": "National Treasury", "where": "National", "when": "12 Oct 2026"}
        self.assertFalse([e for e in guard.check(ok).errors if "`who`" in e or "`where`" in e or "`when`" in e])


class TvClipMoment(unittest.TestCase):
    def test_the_window_is_where_the_speech_says_what_the_post_says(self):
        import pipeline
        segs = [{"start": 0.0, "end": 4.0, "text": "Good evening, this is the news at nine."},
                {"start": 4.0, "end": 9.0, "text": "Weather across the country remains mild."},
                {"start": 30.0, "end": 36.0, "text": "Sugar prices have fallen by thirty two shillings as millers increase production."},
                {"start": 36.0, "end": 40.0, "text": "Back to the studio."}]
        post = {"message": "Sugar prices fell by Sh32 as millers raised production.", "beats": ["Sugar just got *Sh32* cheaper."]}
        a, b = pipeline.clip_moment(segs, post, 120.0)
        self.assertEqual((a, b), (30.0, 38.0))
        self.assertEqual(pipeline.clip_moment([], post, 120.0), (2.0, 10.0))   # no speech: just past the station ident
        self.assertEqual(pipeline.clip_moment([], post, 5.0), (0.0, 5.0))      # a short clip is used whole
