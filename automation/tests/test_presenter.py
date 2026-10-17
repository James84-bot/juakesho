"""The illustrated presenter: lip-sync timeline, the voice choice, and how a voiced Reel is labelled (no network)."""
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
import presenter  # noqa: E402
import presenter_art  # noqa: E402
import render  # noqa: E402
import voicelab  # noqa: E402


class Art(unittest.TestCase):
    def test_every_rhubarb_shape_and_blink_state_is_drawn(self):
        for shape in presenter_art.SHAPES + ["SMILE"]:
            self.assertIn(shape, presenter_art.MOUTHS)
        self.assertEqual(set(presenter_art.EYES), {"open", "half", "closed"})
        for layer in [presenter_art.BASE, *presenter_art.MOUTHS.values(), *presenter_art.EYES.values()]:
            self.assertTrue(layer.startswith("<svg viewBox=\"0 0 600 760\""))   # layers stack exactly


class Timeline(unittest.TestCase):
    CUES = [{"start": 0.0, "end": 0.4, "value": "B"}, {"start": 0.4, "end": 1.0, "value": "D"},
            {"start": 1.0, "end": 6.0, "value": "C"}, {"start": 6.0, "end": 9.0, "value": "X"}]

    def test_mouth_follows_the_cues_frame_by_frame(self):
        seq = presenter.timeline(self.CUES, 9.0, seed=1)
        self.assertEqual(len(seq), 9 * presenter.FPS)
        self.assertTrue(seq[0].startswith("B-"))
        self.assertTrue(seq[int(0.7 * presenter.FPS)].startswith("D-"))

    def test_blinks_come_every_few_seconds_and_never_on_a_wide_open_mouth(self):
        seq = presenter.timeline(self.CUES, 9.0, seed=1)
        closed = [i for i, s in enumerate(seq) if "-closed-" in s]
        self.assertTrue(closed, "he must blink")
        starts = [i for i in closed if i - 1 not in closed]
        self.assertGreaterEqual(len(starts), 1)
        for a, b in zip(starts, starts[1:]):
            self.assertGreaterEqual((b - a) / presenter.FPS, presenter.BLINK_GAP[0] - 0.01)
        self.assertFalse(any(s.startswith("D-") and "-closed-" in s for s in seq))

    def test_ends_on_a_small_smile(self):
        seq = presenter.timeline(self.CUES, 9.0, seed=1)
        self.assertTrue(seq[-1].startswith("SMILE-"))

    def test_sway_never_lifts_him_off_the_bottom_edge(self):
        g = presenter.overlay_graph("0:v", "1:v", "v", width=440, right=20)
        self.assertIn("y=H-h-0+6+4*sin", g)   # +6 always covers the 4 px sway


class VoiceChoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "voice.json"
        self.state.write_text(json.dumps({"file_id": "f", "file_unique_id": "u"}))
        self.p = mock.patch.object(voicelab, "VOICE_STATE", self.state)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_no_presenter_until_a_voice_is_picked(self):
        self.assertIsNone(voicelab.chosen())

    def test_pick_then_turn_off(self):
        self.assertTrue(voicelab.choose("Calm anchor"))
        self.assertEqual(voicelab.chosen()[0], "Calm anchor")
        with mock.patch.dict(os.environ, {"PRESENTER": "off"}):
            self.assertIsNone(voicelab.chosen())
        voicelab.choose_off()
        self.assertIsNone(voicelab.chosen())

    def test_tapping_use_this_voice_in_telegram_picks_it(self):
        tap = {"update_id": 9, "callback_query": {"id": "q", "data": "v|voice|Street reporter",
                                                   "message": {"chat": {"id": 42}}}}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(pipeline, "STATE", Path(d)), \
             mock.patch.object(pipeline, "need", return_value={"TELEGRAM_CHAT_ID": "42"}), \
             mock.patch.object(pipeline, "tg", return_value={"result": [tap]}), \
             mock.patch.object(pipeline, "_answer") as answer, mock.patch.object(pipeline, "_notify"):
            pipeline.collect()
        self.assertEqual(voicelab.chosen()[0], "Street reporter")
        self.assertIn("presenter's voice", answer.call_args[0][1])

    def test_unknown_voice_is_refused(self):
        self.assertFalse(voicelab.choose("Someone else"))
        self.assertIsNone(voicelab.chosen())


class VoicedReel(unittest.TestCase):
    def test_each_beat_lasts_as_long_as_it_is_spoken(self):
        line = "Ministries owe Kenya Power *Sh7.35bn*."
        normal = render.beat_seconds(line)
        render.SPOKEN[line] = 4.21
        try:
            self.assertEqual(render.beat_seconds(line), 4.21)
        finally:
            render.SPOKEN.clear()
        self.assertEqual(render.beat_seconds(line), normal)

    def test_caption_says_the_voice_is_ai(self):
        post = {"caption": "Ministries owe Kenya Power. #KenyaOnRecord", "voiced": "Calm anchor"}
        self.assertIn("AI-generated", pipeline.caption_for(post))
        self.assertNotIn("AI-generated", pipeline.caption_for({"caption": "x #KenyaOnRecord"}))

    def test_cross_post_reminds_to_switch_on_the_ai_labels(self):
        post = {"id": "p", "caption": "x", "reel": True, "voiced": "Calm anchor", "beats": ["a b c."]}
        with mock.patch.object(pipeline, "shorts_title", return_value="t"):
            text = pipeline.crosspost_text(post)
        self.assertIn("AI-generated content", text)


if __name__ == "__main__":
    unittest.main()
