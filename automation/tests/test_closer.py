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


class WriterExamples(unittest.TestCase):
    """The closing questions the writer is shown as examples must pass the guard themselves: an example the guard
    rejects teaches the writer to fail (it once showed "...PIN? Tell us below.", a question with text after it)."""

    def test_example_closers_pass_the_guard(self):
        import re
        import draft
        para = draft.CRAFT_RULES.split("- The LAST line", 1)[1].split("\n- ", 1)[0]
        examples = [q for q in re.findall(r'"([A-Z][^"]+\?)"', para)]
        self.assertGreaterEqual(len(examples), 4, examples)
        for line in examples:
            self.assertEqual(guard.fragment(line), "", line)
            self.assertFalse(guard.closer_problem(line) and not guard.closer_problem(line).startswith("WARN"), line)

    def test_text_after_the_question_is_still_rejected(self):
        self.assertIn("teaser question", guard.fragment("Did you pay for your KRA PIN? Tell us below."))


class NewsEndsOnAQuestion(unittest.TestCase):
    """A news Reel (hot) without a closing question fails the guard, so the repair pass rewrites it before it is
    sent; other templates keep the softer warning."""

    BEATS = ["Kenya records *18 days* without a new Ebola infection.", "All six infected patients have now recovered."]

    def errors(self, last, hot=True):
        rep = guard.Report("x")
        guard._check_closer({"template": "sauti", "hot": hot, "beats": self.BEATS + [last]}, rep)
        return rep.errors

    def test_statement_closer_fails_on_news(self):
        self.assertTrue(any(e.startswith("closer:") for e in self.errors("Zero new cases keep clinics and families *safe*.")))

    def test_question_closer_passes(self):
        self.assertEqual(self.errors("Tell us below: has your clinic changed how it checks *visitors*?"), [])

    def test_other_posts_keep_the_warning(self):
        self.assertEqual(self.errors("Zero new cases keep clinics and families safe.", hot=False), [])

    def test_a_rewrite_must_end_on_a_question(self):
        import json
        from unittest import mock
        import draft
        post = {"id": "2026-w45-hot-1107-sample", "template": "sauti", "hot": True, "caption": "Ebola update.",
                "beats": self.BEATS + ["Kenyans demand: the Health Ministry keeps *border checks*."]}
        flat = json.dumps({"beats": self.BEATS + ["Zero new cases keep clinics and families safe."], "caption": "x"})
        asks = json.dumps({"beats": self.BEATS + ["Tell us below: has your clinic changed its checks?"], "caption": "x"})
        with mock.patch.object(draft, "call_claude", lambda *a, **k: flat):
            self.assertIsNone(draft.rewrite_script(post))
        with mock.patch.object(draft, "call_claude", lambda *a, **k: asks):
            self.assertTrue(draft.rewrite_script(post)["beats"][-1].endswith("?"))


if __name__ == "__main__":
    unittest.main()
