"""A held news post is replaced by a fresh draft instead of blocking its slot (no network)."""
import datetime as dt
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
import pipeline  # noqa: E402

EAT = dt.timezone(dt.timedelta(hours=3))
NOW = dt.datetime(2026, 10, 31, 12, 0, tzinfo=EAT)


def held(pid="2026-w44-hot-1031", **extra):
    return {"id": pid, "template": "sauti", "bg": "usiku", "lane": "everyone", "hot": True, "beat": "life",
            "publish_at": "2026-10-31T12:45:00+03:00", "status": "needs_human", "message": "Old story about a crash",
            "drafted_at": "2026-10-31T09:00:00+03:00", "guard": {"errors": ["weak"]},
            "source_links": [{"title": "Crash on Thika Road", "link": "https://n.test/1"}], **extra}


class Retry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.label = "2026-W44"
        self.patches = [mock.patch.object(pipeline, "WEEKS", d), mock.patch.object(pipeline, "now", lambda: NOW)]
        for p in self.patches:
            p.start()
        self.drafts = 0

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def save(self, posts):
        (pipeline.WEEKS / f"{self.label}.json").write_text(json.dumps({"collection": self.label, "posts": posts}), encoding="utf-8")

    def load(self):
        return json.loads((pipeline.WEEKS / f"{self.label}.json").read_text(encoding="utf-8"))["posts"]

    def fake_draft(self, status, crit=8.6):
        def run(label, mock=False, horizon=None):
            self.drafts += 1
            data = json.loads((pipeline.WEEKS / f"{label}.json").read_text(encoding="utf-8"))
            for p in data["posts"]:
                if p["status"] == "planned":
                    p["status"], p["drafted_at"], p["message"] = status, NOW.isoformat(), f"Story {p['id']}"
                    p["critic"] = {"avg": crit}
                    p["source_links"] = [{"title": f"Report for {p['id']}", "link": "https://n.test/2"}]   # as the writer does
            (pipeline.WEEKS / f"{label}.json").write_text(json.dumps(data), encoding="utf-8")
        return run

    def test_a_held_post_is_closed_and_replaced_with_the_old_story_to_avoid(self):
        self.save([held()])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            made = pipeline.retry_held_hot(self.label)
        self.assertEqual(made, ["2026-w44-hot-1031-r2"])
        posts = {p["id"]: p for p in self.load()}
        self.assertEqual(posts["2026-w44-hot-1031"]["status"], "rejected")
        self.assertEqual(posts["2026-w44-hot-1031-r2"]["status"], "drafted")
        self.assertIn("Old story about a crash", posts["2026-w44-hot-1031-r2"]["avoid"])
        self.assertEqual(self.drafts, 1)

    def test_it_stops_after_the_retry_limit_when_every_draft_is_held(self):
        self.save([held()])
        with mock.patch.object(pipeline, "draft", self.fake_draft("needs_human")):
            made = pipeline.retry_held_hot(self.label)
        self.assertEqual(len(made), pipeline.HOT_RETRIES)
        self.assertEqual(self.drafts, pipeline.HOT_RETRIES)

    def test_breaking_posts_published_posts_and_other_days_are_left_alone(self):
        self.save([held("a", breaking={"title": "x"}), held("b", drafted_at="2026-10-30T09:00:00+03:00"),
                   {**held("c"), "status": "published"}])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            self.assertEqual(pipeline.retry_held_hot(self.label), [])
        self.assertEqual(self.drafts, 0)

    def test_a_post_already_on_its_last_attempt_is_not_retried_again(self):
        self.save([held(f"2026-w44-hot-1031-r{pipeline.HOT_RETRIES + 1}")])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            self.assertEqual(pipeline.retry_held_hot(self.label), [])

    def test_a_late_slot_is_moved_to_at_least_twenty_minutes_from_now(self):
        self.save([held(publish_at="2026-10-31T07:00:00+03:00")])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            pipeline.retry_held_hot(self.label)
        new = [p for p in self.load() if p["id"].endswith("-r2")][0]
        self.assertEqual(dt.datetime.fromisoformat(new["publish_at"]), NOW + dt.timedelta(minutes=20))

    def test_a_weak_post_sent_to_you_gets_a_replacement_and_its_card_stays_yours(self):
        # 21 Nov: all four editions were weak, went to Telegram, and expired untapped
        self.save([held(status="awaiting", critic={"avg": 5.1}, guard={"errors": ["weak: editor scored 5.1/10."]})])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            made = pipeline.retry_held_hot(self.label)
        self.assertEqual(made, ["2026-w44-hot-1031-r2"])
        posts = {p["id"]: p for p in self.load()}
        self.assertEqual(posts["2026-w44-hot-1031"]["status"], "awaiting")        # still yours to approve
        self.assertEqual(posts["2026-w44-hot-1031"]["replaced_by"], "2026-w44-hot-1031-r2")
        self.assertEqual(posts["2026-w44-hot-1031-r2"]["publish_at"], "2026-10-31T12:45:00+03:00")   # same slot

    def test_a_draft_under_the_bar_is_retried_in_the_same_run(self):
        self.save([held(status="drafted", critic={"avg": 6.4}, guard={"errors": []})])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted", crit=7.4)):
            self.assertEqual(pipeline.retry_held_hot(self.label), ["2026-w44-hot-1031-r2"])
        self.assertEqual(self.drafts, 1)                                         # the replacement passed: no more

    def test_a_news_post_the_editor_calls_good_is_kept_and_may_go_out_by_itself(self):
        good = held(status="drafted", critic={"avg": 7.3}, guard={"errors": []})
        self.save([good])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            self.assertEqual(pipeline.retry_held_hot(self.label), [])
        self.assertNotEqual(pipeline.auto_ok({**good, "beat": "sport", "source": "https://x"}),
                            "the editor's score is missing or under the bar")
        planned = {**good, "hot": False, "source": "https://x"}   # written days ahead: the higher bar stays
        self.assertEqual(pipeline.auto_ok(planned), "the editor's score is missing or under the bar")

    def test_a_writer_failure_keeps_the_replacements_already_written(self):
        self.save([held(status="drafted", critic={"avg": 5.0}, guard={"errors": ["weak"]})])
        calls = []

        def flaky(label, mock=False, horizon=None):
            calls.append(1)
            if len(calls) == 2:
                raise ValueError("Extra data: line 22 column 3 (char 1088)")
            self.fake_draft("drafted", crit=5.5)(label)
        with mock.patch.object(pipeline, "draft", flaky), mock.patch.object(pipeline, "log", lambda m: None):
            made = pipeline.retry_held_hot(self.label)
        self.assertEqual(made, ["2026-w44-hot-1031-r2", "2026-w44-hot-1031-r3"])
        self.assertEqual(pipeline.unrendered_hot(self.label), ["2026-w44-hot-1031", "2026-w44-hot-1031-r2"])
        self.assertEqual(pipeline.stuck_hot(self.label), ["2026-w44-hot-1031-r3"])   # the catch-up writes it

    def test_a_good_post_is_never_replaced_and_a_good_political_one_goes_out_by_itself(self):
        self.save([held(status="drafted", critic={"avg": 8.4}, guard={"errors": []}),
                   held("2026-w44-hot-1031e", status="awaiting", beat="politics", critic={"avg": 9.0}, guard={"errors": []})])
        with mock.patch.object(pipeline, "draft", self.fake_draft("drafted")):
            self.assertEqual(pipeline.retry_held_hot(self.label), [])
        self.assertEqual(self.drafts, 0)
        self.assertEqual(pipeline.auto_ok(self.load()[1]), "")   # 26 Nov: no longer waits for being political

    def test_no_card_expires_it_is_replaced_fixed_or_dropped_with_a_reason(self):
        # 26 Nov, James: "no post should expire"; he chose "fix it, then post"
        late = "2026-10-31T07:00:00+03:00"   # five hours ago
        self.save([held(status="awaiting", publish_at=late, replaced_by="2026-w44-hot-1031-r2"),
                   held("2026-w44-hot-1031-r2", status="approved", publish_at="2026-10-31T12:20:00+03:00"),
                   held("2026-w44-hot-1031a", status="awaiting", publish_at=late),                          # 1st version
                   held(f"2026-w44-hot-1031b-r{pipeline.HOT_RETRIES + 1}", status="awaiting", publish_at=late),  # last one
                   held("2026-w44-hot-1031c", status="awaiting", publish_at=late, template="promise"),
                   held("2026-w44-hot-1031d", status="awaiting", publish_at="2026-10-31T10:00:00+03:00")])     # 2 h ago
        told = []
        with mock.patch.object(pipeline, "_notify", told.append), mock.patch.object(pipeline, "log", lambda m: None):
            pipeline.expire_unanswered()
        st = {p["id"]: p["status"] for p in self.load()}
        self.assertEqual(st["2026-w44-hot-1031"], "replaced")               # its replacement is going out
        self.assertEqual(st["2026-w44-hot-1031a"], "awaiting")              # another version is still due
        self.assertEqual(st[f"2026-w44-hot-1031b-r{pipeline.HOT_RETRIES + 1}"], "dropped")   # every version failed
        self.assertEqual(st["2026-w44-hot-1031c"], "awaiting")              # a person's record: waits for you
        self.assertEqual(st["2026-w44-hot-1031d"], "awaiting")
        self.assertNotIn("expired", st.values())
        self.assertEqual(len(told), 1)
        self.assertIn("Sat 07:00 news post: every version failed a check", told[0])

    def test_a_chain_of_versions_renamed_by_new_photos_closes_together(self):
        # 26 Nov: photo swaps renamed versions, 'replaced_by' pointed at ids that no longer existed, and four midday
        # drafts waited all day. Every one of them is closed in one tick, with one line for the slot.
        late = "2026-10-31T07:00:00+03:00"
        self.save([held(status="awaiting", publish_at=late, replaced_by="2026-w44-hot-1031-r2"),          # gone
                   held("2026-w44-hot-1031-r6", status="awaiting", publish_at=late, replaced_by="2026-w44-hot-1031-r3"),
                   held("2026-w44-hot-1031-r3", status="awaiting", publish_at=late, replaced_by="2026-w44-hot-1031-r4"),
                   held("2026-w44-hot-1031-r4", status="awaiting", publish_at=late, replaced_by="2026-w44-hot-1031-r5")])
        told = []
        with mock.patch.object(pipeline, "_notify", told.append), mock.patch.object(pipeline, "log", lambda m: None):
            self.assertEqual(len(pipeline.expire_unanswered()), 4)
        self.assertEqual({p["status"] for p in self.load()}, {"dropped"})
        self.assertEqual(told[0].count("•"), 1)
        self.assertIn("none of 4 versions passed", told[0])

    def test_new_photos_keep_the_link_from_the_version_before(self):
        self.save([held(status="rejected", replaced_by="2026-w44-hot-1031-r2"),
                   held("2026-w44-hot-1031-r2", status="awaiting", photo_query="crash")])
        with mock.patch.object(pipeline, "log", lambda m: None):
            pipeline.rephoto(self.label, only="2026-w44-hot-1031-r2")
        first, second = self.load()
        self.assertEqual(first["replaced_by"], second["id"])
        self.assertNotEqual(second["id"], "2026-w44-hot-1031-r2")

    def test_the_editor_judges_sport_and_life_posts_in_their_own_lane(self):
        import draft
        self.assertIn("NOT the yardstick for those lanes", draft.CRITIC_RUBRIC)


if __name__ == "__main__":
    unittest.main()
