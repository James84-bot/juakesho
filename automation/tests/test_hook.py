"""Hook test: a Reel's first line must be short and carry a figure or a named person, place or body."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402


class Hook(unittest.TestCase):
    def test_good_hooks_pass(self):
        for line in ["Super petrol now costs *Sh226.96* a litre in Nairobi.",
                     "Bankers urge the state to cut *PAYE tax* by five per cent.",
                     "A mugumo fig in the Aberdares was a *secret message drop*.",
                     "Kenya Met warns of heavy rain in *44 counties* this week."]:
            self.assertEqual(guard.hook_problem(line), "", line)

    def test_filler_openers_fail(self):
        for line in ["Here's what you need to know about fuel prices in Kenya 2026.",
                     "Did you know Kenya has 47 counties?",
                     "Today we look at the new Finance Bill.",
                     "The latest on the 2027 election timetable."]:
            self.assertIn("filler", guard.hook_problem(line), line)

    def test_topic_without_figure_or_name_fails(self):
        self.assertIn("topic, not a hook", guard.hook_problem("Parliament passes a bill about breastfeeding rooms."))

    def test_too_long_fails(self):
        self.assertIn("words", guard.hook_problem("Kenya " + "word " * 20))

    def test_check_flags_only_reel_scripts(self):
        rep = guard.Report("x")
        guard._check_hook({"template": "money", "beats": ["Fuel is dear.", "b b b", "c c c"]}, rep)
        self.assertTrue(any(e.startswith("hook:") for e in rep.errors))
        rep2 = guard.Report("y")
        guard._check_hook({"template": "money", "beats": []}, rep2)
        guard._check_hook({"template": "decode", "beats": ["It comes back every year.", "b", "c"]}, rep2)
        guard._check_hook({"template": "glasspoll", "beats": ["Which is it?", "b", "c"]}, rep2)
        self.assertEqual(rep2.errors, [])


if __name__ == "__main__":
    unittest.main()
