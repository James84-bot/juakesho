"""The presenter's voice: taking James's recording from Telegram and the voice lab's bookkeeping (no network)."""
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
import voicelab  # noqa: E402


def voice_msg(**extra):
    return {"message_id": 7, "chat": {"id": 42}, **extra}


class Intake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.patches = [mock.patch.object(pipeline, "STATE", self.state),
                        mock.patch.object(voicelab, "VOICE_STATE", self.state / "voice.json"),
                        mock.patch.object(pipeline, "tg", return_value={"ok": True})]
        self.tg = [p.start() for p in self.patches][-1]

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_voice_notes_audio_and_audio_documents_count_photos_and_videos_do_not(self):
        self.assertTrue(pipeline._voice_of(voice_msg(voice={"file_id": "v"})))
        self.assertTrue(pipeline._voice_of(voice_msg(audio={"file_id": "a"})))
        self.assertTrue(pipeline._voice_of(voice_msg(document={"file_id": "d", "mime_type": "audio/mpeg"})))
        self.assertFalse(pipeline._voice_of(voice_msg(document={"file_id": "d", "mime_type": "video/mp4"})))
        self.assertFalse(pipeline._voice_of(voice_msg(photo=[{"file_id": "p"}])))
        self.assertFalse(pipeline._voice_of(voice_msg(video={"file_id": "x"})))

    def test_saves_newest_recording_and_flags_it_pending_until_made(self):
        pipeline._voice_intake(voice_msg(voice={"file_id": "v1", "file_unique_id": "u1", "duration": 95}), "42")
        rec = json.loads((self.state / "voice.json").read_text())
        self.assertEqual((rec["file_id"], rec["duration"]), ("v1", 95))
        self.assertTrue(voicelab.pending())
        rec["made_for"] = "u1"
        (self.state / "voice.json").write_text(json.dumps(rec))
        self.assertFalse(voicelab.pending())
        pipeline._voice_intake(voice_msg(voice={"file_id": "v2", "file_unique_id": "u2", "duration": 80}), "42")
        self.assertTrue(voicelab.pending())          # a newer recording replaces the old one

    def test_short_recording_gets_a_warning_reply(self):
        pipeline._voice_intake(voice_msg(voice={"file_id": "v", "file_unique_id": "u", "duration": 8}), "42")
        text = self.tg.call_args[0][1]["text"]
        self.assertIn("8 s", text)
        self.assertIn("short", text)

    def test_nothing_pending_without_a_recording(self):
        self.assertFalse(voicelab.pending())

    def test_collect_routes_a_voice_note_to_the_voice_not_to_clips(self):
        update = {"update_id": 5, "message": voice_msg(voice={"file_id": "v", "file_unique_id": "u", "duration": 60})}
        with mock.patch.object(pipeline, "need", return_value={"TELEGRAM_CHAT_ID": "42"}), \
             mock.patch.object(pipeline, "tg", return_value={"result": [update]}), \
             mock.patch.object(pipeline, "_voice_intake") as voice, \
             mock.patch.object(pipeline, "_clip_intake") as clip:
            pipeline.collect()
        voice.assert_called_once()
        clip.assert_not_called()


class Notes(unittest.TestCase):
    def test_a_text_message_is_kept_for_claude_and_acknowledged(self):
        update = {"update_id": 6, "message": voice_msg(text="Use the calm voice please")}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(pipeline, "STATE", Path(d)), \
             mock.patch.object(pipeline, "need", return_value={"TELEGRAM_CHAT_ID": "42"}), \
             mock.patch.object(pipeline, "tg", return_value={"result": [update]}) as tg:
            pipeline.collect()
            saved = [json.loads(l) for l in (Path(d) / "inbox.jsonl").read_text().splitlines()]
        self.assertEqual(saved[0]["text"], "Use the calm voice please")
        self.assertIn("Noted", tg.call_args_list[-1][0][1]["text"])


class Listener(unittest.TestCase):
    def test_a_voice_note_wakes_the_autopilot(self):
        self.assertEqual(listener.classify({"message": voice_msg(voice={"file_id": "v"})}, "42"), "clip")
        self.assertEqual(listener.classify({"message": voice_msg(audio={"file_id": "a"})}, "42"), "clip")
        self.assertIsNone(listener.classify({"message": voice_msg(voice={"file_id": "v"})}, "99"))


class Character(unittest.TestCase):
    def test_character_shift_keeps_length_and_writes_mp3(self):
        import numpy as np
        try:
            import soundfile as sf
        except ImportError:
            self.skipTest("soundfile not installed")
        with tempfile.TemporaryDirectory() as t:
            wav = Path(t) / "x.wav"
            sr = 24000
            tone = 0.2 * np.sin(2 * np.pi * 180 * np.arange(sr * 3) / sr).astype("float32")
            sf.write(str(wav), tone, sr)
            for _, _, rate, tempo in voicelab.CHARACTERS:
                mp3 = voicelab.to_mp3(wav, Path(t) / f"{rate}.mp3", rate, tempo)
                got = voicelab.seconds(mp3)
                self.assertAlmostEqual(got, 3.0 / tempo, delta=0.25)


if __name__ == "__main__":
    unittest.main()
