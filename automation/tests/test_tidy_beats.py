"""The writer's "<Outlet> reports:" opener must not hold a whole post back for length (no network)."""
import os
import sys
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import draft  # noqa: E402


def beat0(b):
    return draft.tidy_beats({"beats": [b, "x", "y"]})["beats"][0]


class TidyBeats(unittest.TestCase):
    def test_a_too_long_attribution_opener_loses_only_the_attribution(self):
        self.assertEqual(beat0("Capital FM News reports: Over *2.5 million learners* completed national assessments."),
                         "Over *2.5 million learners* completed national assessments.")
        self.assertEqual(beat0("People Daily reports: KRA targets 1 million landlords in new rental tax audits."),
                         "KRA targets 1 million landlords in new rental tax audits.")

    def test_a_line_that_already_fits_is_left_alone(self):
        self.assertEqual(beat0("Capital FM reports: Short one."), "Capital FM reports: Short one.")

    def test_a_long_line_without_an_attribution_is_not_touched(self):
        long = "KRA says tax rises 5% for landlords across Kenya next year, officials warn today."
        self.assertEqual(beat0(long), long)

    def test_the_real_held_lines_now_pass_the_length_check(self):
        for b in ("Capital FM News reports: UASU and the State agree to reopen 35 public universities.",
                  "Capital FM News reports: Fuel shortages loom as dealers protest price caps."):
            plain = beat0(b).replace("*", "")
            self.assertLessEqual(len(plain), 72)
            self.assertLessEqual(len(plain.split()), 12)

    def test_other_fields_are_untouched(self):
        post = {"beats": ["Capital FM News reports: Fuel shortages loom as dealers protest price caps.", "a", "b"],
                "source": "Capital FM News, 2026-10-28", "message": "m"}
        out = draft.tidy_beats(post)
        self.assertEqual({k: v for k, v in out.items() if k != "beats"}, {k: v for k, v in post.items() if k != "beats"})


if __name__ == "__main__":
    unittest.main()
