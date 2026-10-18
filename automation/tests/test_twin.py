"""The AI presenter built from James's real video: gating, timing, the lip-sync call and the Telegram flow (no network)."""
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
import takes  # noqa: E402
import twin  # noqa: E402

KEYS = {"ELEVENLABS_API_KEY": "e", "REPLICATE_API_TOKEN": "r"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "base.mp4").write_bytes(b"v")
        self.patches = [mock.patch.object(twin, "STATE", d / "twin.json"), mock.patch.object(twin, "BASE", d / "base.mp4")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()


class Gate(Base):
    def test_only_after_your_tick_and_with_both_keys(self):
        twin.save({"voice_id": "v", "status": "sample"})
        with mock.patch.dict(os.environ, KEYS):
            self.assertFalse(twin.ready())                 # sample not approved yet
            self.assertIn("✅", twin.decide(True))
            self.assertTrue(twin.ready())
            with mock.patch.dict(os.environ, {"PRESENTER": "off"}):
                self.assertFalse(twin.ready())
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "", "REPLICATE_API_TOKEN": ""}):
            self.assertFalse(twin.ready())

    def test_not_yet_keeps_it_off(self):
        twin.save({"voice_id": "v", "status": "sample"})
        twin.decide(False)
        with mock.patch.dict(os.environ, KEYS):
            self.assertFalse(twin.ready())

    def test_when_the_twin_reads_reels_you_are_not_asked_to_record(self):
        twin.save({"voice_id": "v", "status": "approved", "approved": True})
        post = {"id": "p", "template": "kenya", "size": "post", "beats": ["One two three four.", "Five six seven.",
                                                                          "Eight nine ten."],
                "publish_at": (pipeline.now() + pipeline.dt.timedelta(days=1)).isoformat()}
        with mock.patch.dict(os.environ, KEYS), mock.patch.object(pipeline, "tg") as tg:
            self.assertFalse(takes.ask(post, "2026-W43", "42"))
        tg.assert_not_called()


class Timing(unittest.TestCase):
    def test_each_line_starts_at_its_first_character(self):
        lines = ["Ab cd.", "Ef.", "Gh ij."]
        text = " ".join(lines)
        al = {"character_start_times_seconds": [i * 0.1 for i in range(len(text))]}
        self.assertEqual(twin.line_times(lines, al), [0.0, 0.7, 1.1])

    def test_a_different_moment_of_your_video_for_each_reel(self):
        a, loop_a = twin.slice_plan(90, 25, seed=1)
        b, _ = twin.slice_plan(90, 25, seed=2)
        self.assertFalse(loop_a)
        self.assertNotEqual(a, b)
        self.assertTrue(0 <= a <= 65)
        self.assertEqual(twin.slice_plan(20, 25, seed=1), (0.0, True))


class LipSync(Base):
    def test_uploads_runs_the_latest_version_and_downloads_the_result(self):
        calls = []

        def fake(method, url, headers, body=None, ctype=None, timeout=120, raw=False):
            calls.append((method, url))
            if url.endswith("/models/bytedance/latentsync"):
                return {"latest_version": {"id": "VER"}}
            if url.endswith("/files"):
                return {"urls": {"get": f"https://f/{len(calls)}"}}
            if url.endswith("/predictions") and method == "POST":
                sent = json.loads(body)
                self.assertEqual(sent["version"], "VER")
                self.assertEqual(set(sent["input"]), {"video", "audio", "guidance_scale", "inference_steps", "seed"})
                return {"id": "P", "status": "starting"}
            if "/predictions/P" in url:
                return {"id": "P", "status": "succeeded", "output": "https://out/x.mp4"}
            if url == "https://out/x.mp4":
                return b"MP4"
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, KEYS), \
             mock.patch.object(twin, "_call", fake), mock.patch.object(twin.time, "sleep"):
            v, a = Path(d) / "v.mp4", Path(d) / "a.mp3"
            v.write_bytes(b"v")
            a.write_bytes(b"a")
            out = twin.lipsync(v, a, Path(d) / "o.mp4")
            self.assertEqual(out.read_bytes(), b"MP4")

    def test_a_failed_run_says_why(self):
        def fake(method, url, *a, **k):
            if url.endswith("latentsync"):
                return {"latest_version": {"id": "V"}}
            if url.endswith("/files"):
                return {"urls": {"get": "u"}}
            return {"id": "P", "status": "failed", "error": "no face found"}
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, KEYS), mock.patch.object(twin, "_call", fake):
            (Path(d) / "v").write_bytes(b"v")
            with self.assertRaisesRegex(RuntimeError, "no face"):
                twin.lipsync(Path(d) / "v", Path(d) / "v", Path(d) / "o")


class Telegram(Base):
    def test_a_presenter_video_is_kept_for_the_next_run(self):
        msg = {"message_id": 1, "chat": {"id": 42}, "caption": "#presenter",
               "video": {"file_id": "F", "file_size": 12_000_000, "duration": 75}}
        self.assertTrue(twin.is_base(msg))
        with mock.patch.dict(os.environ, KEYS):
            self.assertIn("Got your presenter video", twin.intake(msg))
        self.assertTrue(twin.pending())
        self.assertFalse(twin.is_base({**msg, "caption": "own"}))

    def test_short_or_huge_videos_get_a_clear_answer(self):
        base = {"message_id": 1, "chat": {"id": 42}, "caption": "#presenter"}
        self.assertIn("30-90", twin.intake({**base, "video": {"file_id": "F", "file_size": 1000, "duration": 12}}))
        self.assertIn("20 MB", twin.intake({**base, "video": {"file_id": "F", "file_size": 50_000_000, "duration": 70}}))
        self.assertFalse(twin.pending())

    def test_without_keys_the_owner_is_told_which_secrets(self):
        twin.save({"status": "received", "file_id": "F"})
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "", "REPLICATE_API_TOKEN": ""}), \
             mock.patch.object(pipeline, "_notify") as note:
            self.assertEqual(twin.setup(), "needs keys")
        self.assertIn("REPLICATE_API_TOKEN", note.call_args[0][0])

    def test_tapping_use_the_ai_presenter_turns_it_on(self):
        twin.save({"voice_id": "v", "status": "sample"})
        tap = {"update_id": 4, "callback_query": {"id": "q", "data": "w|twin|yes", "message": {"chat": {"id": 42}}}}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(pipeline, "STATE", Path(d)), \
             mock.patch.object(pipeline, "need", return_value={"TELEGRAM_CHAT_ID": "42"}), \
             mock.patch.object(pipeline, "tg", return_value={"result": [tap]}), \
             mock.patch.object(pipeline, "_answer") as answer:
            pipeline.collect()
        self.assertTrue(twin.load()["approved"])
        self.assertIn("AI presenter", answer.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
