"""Closing line: generic asks are rejected; a specific action passes; a slogan closer is flagged."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402


class Closer(unittest.TestCase):
    def test_specific_actions_pass(self):
        for line in ["Tell us your town and what your station charges.", "Tag someone who would make the trip.",
                     "Call toll-free *1199* to report flood emergencies immediately.",
                     "Track the Bill's status on parliament.go.ke."]:
            self.assertEqual(guard.closer_problem(line), "", line)

    def test_generic_asks_fail(self):
        for line in ["Send this to someone who needs to see it.", "Share to spread awareness.", "Follow us for more.",
                     "What do you think?"]:
            self.assertTrue(guard.closer_problem(line) and not guard.closer_problem(line).startswith("WARN"), line)

    def test_slogan_is_a_warning_not_a_hold(self):
        rep = guard.Report("x")
        guard._check_closer({"template": "sauti", "beats": ["a b c", "d e f", "Kenyans demand: the Treasury cuts income tax."]}, rep)
        self.assertEqual(rep.errors, [])
        self.assertTrue(any(w.startswith("closer:") for w in rep.warnings))
        rep2 = guard.Report("y")
        guard._check_closer({"template": "sauti", "beats": ["a b c", "d e f", "Send this to someone who needs it."]}, rep2)
        self.assertTrue(any(e.startswith("closer:") for e in rep2.errors))


if __name__ == "__main__":
    unittest.main()
