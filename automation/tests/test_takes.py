"""James on camera: the script request, taking his reply, line timing and the review buttons (no network)."""
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
import listener  # noqa: E402
import pipeline  # noqa: E402
import takes  # noqa: E402

LINES = ["Hell's Gate sits on the Rift Valley floor.", "It was gazetted in 1984.", "Facts today. A better Kenya tomorrow."]
BEATS = ["Hell's Gate sits on the *Rift* Valley floor.", "It was gazetted in 1984.", "Visitors climb its towering cliffs."]


def words(text: str, gap_after: dict | None = None, rate: float = 0.35) -> list[dict]:
    out, t = [], 0.4
    for i, w in enumerate(text.split()):
        out.append({"w": w, "s": round(t, 2), "e": round(t + rate * 0.8, 2)})
        t += rate + (gap_after or {}).get(i, 0)
    return out


class Timing(unittest.TestCase):
    def test_each_line_starts_where_its_first_word_is_heard(self):
        heard = words(" ".join(LINES), gap_after={7: 0.6, 12: 0.5})
        starts, matched = takes.align(LINES, heard)
        self.assertEqual(matched, 1.0)
        self.assertEqual(starts[0], heard[0]["s"])
        self.assertEqual(starts[1], heard[8]["s"])     # "It"
        self.assertEqual(starts[2], heard[13]["s"])    # "Facts"

    def test_misheard_words_still_place_the_line(self):
        heard = words("Hells gate sits on the rift valley flaw. It was gazetted in nineteen eighty four. "
                      "Facts today a better Kenya tomorrow")
        got = takes.align(LINES, heard)
        self.assertIsNotNone(got)
        self.assertLess(got[1], 1.0)

    def test_a_skipped_line_cannot_be_placed(self):
        self.assertIsNone(takes.align(LINES, words("Hell's Gate sits on the Rift Valley floor. Facts today.")[:8]))

    def test_without_recognition_the_longest_pauses_split_the_lines(self):
        starts = takes.pause_starts(LINES, 0.5, 9.0, [(2.0, 2.1), (3.4, 4.2), (6.0, 6.9)])
        self.assertEqual(starts, [0.5, 4.15, 6.85])

    def test_without_pauses_lines_share_the_time_by_length(self):
        starts = takes.pause_starts(LINES, 0.0, 10.0, [])
        self.assertEqual(starts[0], 0.0)
        self.assertTrue(starts[0] < starts[1] < starts[2] < 10.0)


class Crop(unittest.TestCase):
    def test_portrait_video_fills_the_width_with_the_face_in_frame(self):
        g = takes.presenter_graph(0.35, 1080, 1920)
        self.assertIn("scale=1080:1920", g)
        y = int(g.split("crop=1080:960:0:")[1].split(",")[0])
        self.assertTrue(0 <= y <= 960)
        self.assertLess(y, 0.35 * 1920)               # the face is inside the crop
        self.assertGreater(y + 960, 0.35 * 1920)

    def test_landscape_video_fills_the_height(self):
        self.assertIn(f"scale=-2:{takes.TAKE_H}", takes.presenter_graph(0.5, 1920, 1080))


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.weeks = Path(self.tmp.name)
        self.when = (pipeline.now() + dt.timedelta(days=1)).isoformat()
        self.post = {"id": "p1", "template": "kenya", "series": "Kenya at its best", "status": "approved",
                     "publish_at": self.when, "beats": BEATS, "size": "post"}
        (self.weeks / "2026-W43.json").write_text(json.dumps({"collection": "2026-W43", "posts": [self.post]}))
        self.patches = [mock.patch.object(pipeline, "WEEKS", self.weeks),
                        mock.patch.object(pipeline, "week_file", lambda label: self.weeks / f"{label}.json")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_approving_a_reel_sends_its_script_to_record(self):
        post = dict(self.post)
        with mock.patch.object(pipeline, "tg", return_value={"result": {"message_id": 77}}) as tg:
            self.assertTrue(takes.ask(post, "2026-W43", "42"))
        text = tg.call_args[0][1]["text"]
        self.assertIn("Rift Valley floor", text)
        self.assertIn("Facts today. A better Kenya tomorrow.", text)
        self.assertEqual(post["take"], {"status": "asked", "ask_msg": 77})

    def test_no_script_for_a_reel_without_lines(self):
        with mock.patch.object(pipeline, "tg") as tg:
            self.assertFalse(takes.ask({**self.post, "beats": BEATS[:2]}, "2026-W43", "42"))
        tg.assert_not_called()

    def test_no_script_when_the_slot_is_too_close(self):
        post = {**self.post, "publish_at": (pipeline.now() + dt.timedelta(minutes=20)).isoformat()}
        with mock.patch.object(pipeline, "tg") as tg:
            self.assertFalse(takes.ask(post, "2026-W43", "42"))
        tg.assert_not_called()

    def _asked(self):
        data = json.loads((self.weeks / "2026-W43.json").read_text())
        data["posts"][0]["take"] = {"status": "asked", "ask_msg": 77}
        (self.weeks / "2026-W43.json").write_text(json.dumps(data))

    def test_a_video_reply_to_the_script_is_saved_for_the_build(self):
        self._asked()
        msg = {"message_id": 9, "chat": {"id": 42}, "reply_to_message": {"message_id": 77},
               "video": {"file_id": "F", "file_size": 9_000_000, "duration": 28}}
        self.assertTrue(takes.is_take(msg))
        weeks = {}
        reply = takes.intake(msg, "42", weeks)
        self.assertIn("Got it", reply)
        self.assertEqual(weeks["2026-W43"]["posts"][0]["take"]["file_id"], "F")

    def test_too_big_round_or_unrelated_videos_get_a_clear_answer(self):
        self._asked()
        base = {"message_id": 9, "chat": {"id": 42}, "reply_to_message": {"message_id": 77}}
        self.assertIn("20 MB", takes.intake({**base, "video": {"file_id": "F", "file_size": 60_000_000, "duration": 28}}, "42"))
        self.assertIn("round video", takes.intake({**base, "video_note": {"file_id": "F", "duration": 20}}, "42"))
        self.assertFalse(takes.is_take({**base, "reply_to_message": {"message_id": 5}, "video": {"file_id": "F"}}))

    def test_collect_routes_the_reply_to_the_take_not_to_clips(self):
        self._asked()
        update = {"update_id": 3, "message": {"message_id": 9, "chat": {"id": 42}, "reply_to_message": {"message_id": 77},
                                               "video": {"file_id": "F", "file_size": 1000, "duration": 20}}}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(pipeline, "STATE", Path(d)), \
             mock.patch.object(pipeline, "need", return_value={"TELEGRAM_CHAT_ID": "42"}), \
             mock.patch.object(pipeline, "tg", return_value={"result": [update]}), \
             mock.patch.object(pipeline, "_clip_intake") as clip:
            pipeline.collect()
        clip.assert_not_called()
        saved = json.loads((self.weeks / "2026-W43.json").read_text())["posts"][0]["take"]
        self.assertEqual(saved["status"], "received")
        self.assertEqual([p for _, p in takes.pending([self.weeks / "2026-W43.json"])], ["p1"])

    def test_use_this_take_swaps_the_reel_and_keeps_the_text_version(self):
        with tempfile.TemporaryDirectory() as ex:
            out = Path(ex) / "2026-W43"
            out.mkdir()
            (out / "p1.mp4").write_bytes(b"text")
            (out / "p1-take.mp4").write_bytes(b"take")
            data = {"collection": "2026-W43", "posts": [{**self.post, "take": {"status": "review", "file": "p1-take.mp4"}}]}
            with mock.patch.object(pipeline, "EXPORTS", Path(ex)):
                said = takes.decide(data, "ok:p1", "42")
            self.assertIn("goes out", said)
            self.assertEqual((out / "p1.mp4").read_bytes(), b"take")
            self.assertEqual((out / "p1-text.mp4").read_bytes(), b"text")
            self.assertEqual(data["posts"][0]["take"]["status"], "ok")
            self.assertNotIn("voiced", data["posts"][0])   # your own voice is not labelled as AI

    def test_record_again_sends_the_script_again(self):
        data = {"collection": "2026-W43", "posts": [{**self.post, "take": {"status": "review", "file": "x"}}]}
        with mock.patch.object(pipeline, "tg", return_value={"result": {"message_id": 88}}):
            takes.decide(data, "re:p1", "42")
        self.assertEqual(data["posts"][0]["take"], {"status": "asked", "ask_msg": 88})

    def test_a_round_video_wakes_the_autopilot(self):
        self.assertEqual(listener.classify({"message": {"chat": {"id": 42}, "video_note": {"file_id": "v"}}}, "42"), "clip")


if __name__ == "__main__":
    unittest.main()
