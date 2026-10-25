"""Auto-approval: only posts that pass every check; everything else waits for a person (no network)."""
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


def good(**kw):
    p = {"id": "x", "template": "money", "status": "awaiting", "publish_at": "2026-10-26T07:30:00+03:00",
         "guard": {"errors": [], "warnings": []}, "critic": {"avg": 8.6}, "source_links": [{"link": "https://a.example"}],
         "photo_kind": "symbolic"}
    p.update(kw)
    return p


class AutoOk(unittest.TestCase):
    def test_clean_post_passes(self):
        self.assertEqual(pl.auto_ok(good()), "")

    def test_each_failure_waits_for_a_person(self):
        cases = {
            "promise": good(template="promise"),
            "scorecard": good(template="scorecard"),
            "guard error": good(guard={"errors": ["x"], "warnings": []}),
            "named person": good(guard={"errors": [], "warnings": ["possible named person(s): A B"]}),
            "low score": good(critic={"avg": 7.2}),
            "no score": good(critic=None),
            "no source": good(source_links=None),
            "portrait": good(photo_kind="file"),
            "politics": good(hot=True, beat="politics"),
        }
        for name, post in cases.items():
            self.assertNotEqual(pl.auto_ok(post), "", name)

    def test_hand_written_post_needs_no_score_but_not_a_low_one(self):
        self.assertEqual(pl.auto_ok(good(critic=None, hand=True)), "")
        self.assertNotEqual(pl.auto_ok(good(critic={"avg": 6}, hand=True)), "")


class AutoApprove(unittest.TestCase):
    def run_it(self, posts, on=True):
        with tempfile.TemporaryDirectory() as d:
            weeks = Path(d) / "weeks"
            weeks.mkdir()
            (weeks / "2026-W44.json").write_text(json.dumps({"collection": "2026-W44", "posts": posts}))
            policy = Path(d) / "policy.json"
            policy.write_text(json.dumps({"auto_approve": on}))
            notes = []
            with mock.patch.object(pl, "WEEKS", weeks), mock.patch.object(pl, "POLICY", policy), \
                 mock.patch.object(pl, "_notify", notes.append):
                done = pl.auto_approve()
            return done, json.loads((weeks / "2026-W44.json").read_text())["posts"], notes

    def test_approves_only_the_eligible(self):
        done, posts, notes = self.run_it([good(id="a"), good(id="b", template="promise"), good(id="c", group="g")])
        self.assertEqual([p["status"] for p in posts], ["approved", "awaiting", "awaiting"])
        self.assertTrue(posts[0]["auto"])
        self.assertEqual(len(done), 1)
        self.assertEqual(len(notes), 1)

    def test_policy_off_changes_nothing(self):
        done, posts, notes = self.run_it([good()], on=False)
        self.assertEqual((done, posts[0]["status"], notes), ([], "awaiting", []))

    def test_cross_stops_an_auto_approved_post_but_not_a_hand_approved_one(self):
        data = {"posts": [good(id="a", status="approved", auto=True), good(id="b", status="approved")]}
        self.assertEqual(pl.apply_decision(data, "a", False), ["a"])
        self.assertEqual(pl.apply_decision(data, "b", False), [])
        self.assertEqual([p["status"] for p in data["posts"]], ["rejected", "approved"])


if __name__ == "__main__":
    unittest.main()
