"""The published Reel is also sent to Telegram for a manual TikTok upload (no network)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pipeline  # noqa: E402

REEL = {"id": "2026-w45-hot-1107", "reel": True, "message": "Fuel prices rise.", "caption": "A caption #Kenya"}


class TikTok(unittest.TestCase):
    def run_pkg(self, post, on=True):
        calls = []
        with mock.patch.object(pipeline, "tiktok_packages_on", return_value=on), \
             mock.patch.object(pipeline, "tg", lambda m, f=None, files=None: calls.append((m, f, files))), \
             mock.patch.object(pipeline, "need", lambda *k: {"TELEGRAM_CHAT_ID": "1"}), \
             mock.patch.object(pipeline, "caption_for", lambda p, credits=False: p["caption"]):
            pipeline._tiktok_package("2026-W45", post)
        return calls

    def test_a_published_reel_is_sent_with_its_caption(self):
        calls = self.run_pkg(REEL)
        self.assertEqual(len(calls), 1)
        method, fields, files = calls[0]
        self.assertEqual(method, "sendVideo")
        self.assertIn("A caption #Kenya", fields["caption"])
        self.assertTrue(str(files["video"]).endswith("2026-w45-hot-1107.mp4"))

    def test_a_card_that_is_not_a_reel_or_with_the_switch_off_sends_nothing(self):
        self.assertEqual(self.run_pkg({**REEL, "reel": False}), [])
        self.assertEqual(self.run_pkg(REEL, on=False), [])

    def test_a_long_caption_is_trimmed_to_telegrams_limit(self):
        calls = self.run_pkg({**REEL, "caption": "x" * 3000})
        self.assertLessEqual(len(calls[0][1]["caption"]), 1000)

    def test_a_failed_send_never_raises(self):
        with mock.patch.object(pipeline, "tiktok_packages_on", return_value=True), \
             mock.patch.object(pipeline, "tg", side_effect=RuntimeError("down")), \
             mock.patch.object(pipeline, "need", lambda *k: {"TELEGRAM_CHAT_ID": "1"}), \
             mock.patch.object(pipeline, "caption_for", lambda p: "c"):
            pipeline._tiktok_package("2026-W45", REEL)


if __name__ == "__main__":
    unittest.main()
