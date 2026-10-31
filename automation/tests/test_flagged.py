"""A post that fails a check is sent to Telegram marked with what failed, and is never auto-approved (no network)."""
import os
import sys
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import draft  # noqa: E402
import pipeline  # noqa: E402

POST = {"id": "2026-w44-hot-1031", "template": "sauti", "lane": "everyone", "publish_at": "2026-10-31T12:45:00+03:00",
        "message": "Fuel shortages loom.", "caption": "A caption.", "source_links": [{"outlet": "X", "link": "https://x"}],
        "critic": {"avg": 9.0}, "guard": {"errors": ["beats[0] is too long: max 12 words / 72 characters"], "warnings": []}}


class Flagged(unittest.TestCase):
    def test_a_post_with_text_counts_as_content_and_an_empty_slot_does_not(self):
        self.assertTrue(draft.has_content(POST))
        self.assertFalse(draft.has_content({"id": "x", "template": "sauti"}))

    def test_the_card_lists_what_failed_above_the_story(self):
        text = pipeline._preview_text(POST)
        self.assertIn("Did not pass our checks", text)
        self.assertIn("too long", text)
        self.assertLess(text.index("Did not pass"), text.index("Fuel shortages"))

    def test_a_clean_card_has_no_warning_block(self):
        self.assertNotIn("Did not pass", pipeline._preview_text({**POST, "guard": {"errors": [], "warnings": []}}))

    def test_auto_approval_never_takes_a_failed_post(self):
        self.assertEqual(pipeline.auto_ok(POST), "failed a guard rule")

    def test_the_failure_text_is_escaped_for_telegram(self):
        bad = {**POST, "guard": {"errors": ["use <b> & 'x'"], "warnings": []}}
        self.assertIn("&lt;b&gt;", pipeline._preview_text(bad))


if __name__ == "__main__":
    unittest.main()
