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

    def test_a_leading_credit_is_dropped_the_source_is_in_the_comment(self):
        self.assertEqual(beat0("Capital FM reports: Short one."), "Short one.")
        self.assertEqual(beat0("KNBS says: Kenyan women now have *3 children* on average."),
                         "Kenyan women now have *3 children* on average.")
        cap = draft.tidy_beats({"beats": ["a"], "caption": "Capital FM News reports: Sugar is Sh32 cheaper.\n#Sugar"})["caption"]
        self.assertEqual(cap, "Sugar is Sh32 cheaper.\n#Sugar")

    def test_on_an_allegation_the_credit_moves_after_the_fact(self):
        self.assertEqual(beat0("Citizen Digital reports: Corruption costs Kenya billions every year."),
                         "Corruption costs Kenya billions every year, Citizen Digital reports.")
        out = draft.tidy_beats({"beats": ["The Star reports: Police arrested 3 over the fraud."],
                                "caption": "The Star reports: 3 arrested."})
        self.assertEqual(out["beats"][0], "Police arrested 3 over the fraud, The Star reports.")
        self.assertEqual(out["caption"], "The Star reports: 3 arrested.")   # an allegation keeps its credit

    def test_a_line_without_a_leading_credit_is_left_alone(self):
        self.assertEqual(beat0("Kenyan women now have 3 children on average, KNBS reports."),
                         "Kenyan women now have 3 children on average, KNBS reports.")

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


class Rewrite(unittest.TestCase):
    POST = {"id": "w-x", "template": "sauti", "message": "Sugar is Sh32 cheaper.", "source": "Capital FM, 2026-11-07",
            "beats": ["Kenya sugar output rose 56.7%, dropping 2kg prices by *Sh32.*", "Local factories boosted milling.",
                      "Cheaper sugar brings relief."], "caption": "Sugar is cheaper. #KenyaOnRecord"}

    def run_with(self, reply):
        from unittest import mock
        with mock.patch.object(draft, "call_claude", lambda *a, **k: reply):
            return draft.rewrite_script(dict(self.POST))

    def test_a_new_script_that_keeps_the_rules_is_used(self):
        new = self.run_with('{"beats": ["Sugar just got *Sh32* cheaper.", "Factories milled 56.7% more cane.", '
                            '"Has your shop dropped the price yet?"], "caption": "Sugar just got Sh32 cheaper. #KenyaOnRecord"}')
        self.assertEqual(new["beats"][0], "Sugar just got *Sh32* cheaper.")

    def test_a_script_that_breaks_a_rule_or_is_malformed_is_dropped(self):
        too_long = "This line is far too long for a Reel beat and it keeps on going and going."
        self.assertIsNone(self.run_with('{"beats": ["' + too_long + '", "b c.", "d e."], "caption": "c"}'))
        self.assertIsNone(self.run_with('{"beats": ["only one"], "caption": "c"}'))
        self.assertIsNone(self.run_with("not json"))
