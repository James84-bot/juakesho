"""Tests for answering comments: sorting, the reply guard, Telegram cards, and posting/hiding on your tap."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):   # AI keys never reach the tests: no real calls, no spend
    os.environ.pop(_k, None)

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import engage  # noqa: E402

NOW = dt.datetime(2026, 10, 12, 12, tzinfo=dt.timezone(dt.timedelta(hours=3)))


def week(root: Path, posts: list[dict]) -> Path:
    d = root / "weeks"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-W42.json").write_text(json.dumps({"collection": "2026-W42", "posts": posts}), encoding="utf-8")
    return d


class Engage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"

    def tearDown(self):
        self.tmp.cleanup()

    def test_recent_targets_only_published_recent_first_slides(self):
        old = (NOW - dt.timedelta(days=9)).isoformat()
        fresh = (NOW - dt.timedelta(days=1)).isoformat()
        d = week(self.root, [
            {"id": "a", "status": "published", "published_at": fresh, "publish_at": fresh},
            {"id": "b", "status": "published", "published_at": old, "publish_at": old},
            {"id": "c", "status": "approved", "publish_at": fresh},
            {"id": "d2", "n": 2, "status": "published", "published_at": fresh, "publish_at": fresh}])
        self.assertEqual([p["id"] for p in engage.recent_targets(d, NOW)], ["a"])

    def test_fetch_skips_our_own_comments(self):
        def get(path, fields):
            if path.startswith("IG1"):
                return {"data": [{"id": "1", "text": "source?", "username": "wanjiku", "timestamp": "2026-10-12T08:00",
                                  "from": {"id": "u1"}},
                                 {"id": "2", "text": "Receipts: ...", "username": "juakesho", "timestamp": "2026-10-12T07:00",
                                  "from": {"id": "ig"}}]}
            return {"data": [{"id": "p_3", "message": "Kweli", "from": {"id": "f9", "name": "Otieno"},
                              "created_time": "2026-10-12T09:00"}]}
        got = engage.fetch(get, [{"id": "a", "ig_id": "IG1", "fb_id": "FB1"}], own={"ig", "page"})
        self.assertEqual([(c["cid"], c["platform"]) for c in got], [("1", "ig"), ("p_3", "fb")])

    def test_hate_hidden_without_ai(self):
        def call(*a, **k):
            raise AssertionError("AI must not be asked")
        out = engage.draft(call, [{"cid": "1", "text": "hao ni madoadoa", "message": "", "source": ""}])
        self.assertEqual(out[0]["action"], "hide")

    def test_bad_draft_becomes_flag_and_unknown_action_skips(self):
        long = "Asante " * 60
        reply = json.dumps({"replies": [{"cid": "1", "action": "reply", "reply": long},
                                        {"cid": "2", "action": "attack", "reply": "x"},
                                        {"cid": "3", "action": "reply", "reply": "Check the Auditor-General report, page 12."}]})
        cs = [{"cid": i, "text": "?", "message": "", "source": ""} for i in "123"]
        out = {c["cid"]: c["action"] for c in engage.draft(lambda *a, **k: reply, cs)}
        self.assertEqual(out, {"1": "flag", "2": "skip", "3": "reply"})

    def test_check_reply_catches_em_dash(self):
        self.assertTrue(engage.check_reply("Fair point — here is the source."))
        self.assertEqual(engage.check_reply("Fair point. Source is in the first comment."), [])

    def test_card_buttons(self):
        c = {"cid": "17", "platform": "ig", "user": "w", "post_id": "a", "text": "<b>hi</b>", "action": "reply",
             "reply": "Asante!", "why": ""}
        text, kb = engage.card(c)
        self.assertIn("&lt;b&gt;", text)
        data = [b["callback_data"] for b in json.loads(kb)["inline_keyboard"][0]]
        self.assertEqual(data, ["c|r|17", "c|h|17", "c|s|17"])
        _, kb = engage.card({**c, "action": "hide"})
        self.assertNotIn("c|r|17", kb)

    def test_run_stores_no_personal_data_and_act_routes(self):
        fresh = (NOW - dt.timedelta(hours=3)).isoformat()
        d = week(self.root, [{"id": "a", "status": "published", "published_at": fresh, "publish_at": fresh,
                              "ig_id": "IG1", "fb_id": "FB1"}])

        def get(path, fields):
            if path.startswith("IG1"):
                return {"data": [{"id": "17", "text": "where is the source", "username": "wanjiku",
                                  "timestamp": "2026-10-12T08:00", "from": {"id": "u"}}]}
            return {"data": [{"id": "p_9", "message": "spam link", "from": {"id": "x", "name": "Bot"},
                              "created_time": "2026-10-12T09:00"}]}
        reply = json.dumps({"replies": [{"cid": "17", "action": "reply", "reply": "It's in the first comment."},
                                        {"cid": "p_9", "action": "hide", "why": "spam"}]})
        sent = []
        n = engage.run(self.state, d, get, lambda *a, **k: reply, lambda t, b: sent.append(b), NOW)
        self.assertEqual(n, 2)
        stored = (self.state / "comments.json").read_text(encoding="utf-8")
        self.assertNotIn("wanjiku", stored)
        self.assertNotIn("where is the source", stored)
        # a second run sends nothing new
        self.assertEqual(engage.run(self.state, d, get, lambda *a, **k: reply, lambda t, b: sent.append(b), NOW), 0)

        calls = []
        self.assertEqual(engage.act(self.state, lambda p, f: calls.append((p, f)), "r", "17"), "replied")
        self.assertEqual(engage.act(self.state, lambda p, f: calls.append((p, f)), "h", "p_9"), "hidden")
        self.assertEqual(calls, [("17/replies", {"message": "It's in the first comment."}),
                                 ("p_9", {"is_hidden": "true"})])
        self.assertEqual(engage.act(self.state, lambda p, f: None, "r", "17"), "already handled")

    def test_failed_post_stays_pending(self):
        engage.save(self.state, {"seen": ["5"], "pending": {"5": {"platform": "fb", "reply": "Asante", "post_id": "a",
                                                                   "action": "reply"}}})

        def boom(p, f):
            raise RuntimeError("token expired")
        self.assertTrue(engage.act(self.state, boom, "r", "5").startswith("failed"))
        self.assertIn("5", engage.load(self.state)["pending"])

    def test_samples_send_cards_and_store_nothing(self):
        reply = json.dumps({"replies": [{"cid": "sample-0", "action": "reply", "reply": "It's in the first comment."}]})
        out = []
        n = engage.samples(self.root / "none", lambda *a, **k: reply, lambda t, b: out.append(t))
        self.assertEqual(n, 2)   # the reply + the auto-hidden slur; the rest have no draft and are skipped
        self.assertTrue(all(t.startswith("🧪") for t in out))
        self.assertFalse((self.state / "comments.json").exists())


if __name__ == "__main__":
    unittest.main()
