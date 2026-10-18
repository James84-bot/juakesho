"""Notes to the team from Telegram: texts and voice notes are kept for Claude, never lost (no network)."""
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


def msg(**extra):
    return {"message_id": 7, "chat": {"id": 42}, **extra}


class Notes(unittest.TestCase):
    def collect(self, update):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(pipeline, "STATE", Path(d)), \
             mock.patch.object(pipeline, "need", return_value={"TELEGRAM_CHAT_ID": "42"}), \
             mock.patch.object(pipeline, "tg", return_value={"result": [update]}) as tg, \
             mock.patch.object(pipeline, "_clip_intake") as clip:
            pipeline.collect()
            saved = [json.loads(l) for l in (Path(d) / "inbox.jsonl").read_text().splitlines()]
        return saved, tg, clip

    def test_a_text_message_is_kept_and_acknowledged(self):
        saved, tg, _ = self.collect({"update_id": 6, "message": msg(text="Use the calm voice please")})
        self.assertEqual(saved[0]["text"], "Use the calm voice please")
        self.assertIn("Noted", tg.call_args_list[-1][0][1]["text"])

    def test_a_voice_note_is_kept_as_a_note_not_a_clip(self):
        saved, tg, clip = self.collect({"update_id": 7, "message": msg(voice={"file_id": "V", "duration": 12})})
        self.assertEqual((saved[0]["voice_file_id"], saved[0]["duration"]), ("V", 12))
        clip.assert_not_called()
        self.assertIn("voice note", tg.call_args_list[-1][0][1]["text"])

    def test_voice_notes_audio_files_count_photos_and_videos_do_not(self):
        self.assertTrue(pipeline._voice_of(msg(voice={"file_id": "v"})))
        self.assertTrue(pipeline._voice_of(msg(document={"file_id": "d", "mime_type": "audio/mpeg"})))
        self.assertFalse(pipeline._voice_of(msg(photo=[{"file_id": "p"}])))
        self.assertFalse(pipeline._voice_of(msg(video={"file_id": "x"})))


class Listener(unittest.TestCase):
    def test_a_voice_note_or_text_wakes_the_autopilot(self):
        self.assertEqual(listener.classify({"message": msg(voice={"file_id": "v"})}, "42"), "clip")
        self.assertEqual(listener.classify({"message": msg(text="hi")}, "42"), "clip")
        self.assertIsNone(listener.classify({"message": msg(voice={"file_id": "v"})}, "99"))


if __name__ == "__main__":
    unittest.main()
