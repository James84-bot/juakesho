"""Accusation rules, single-source attribution and no faces for allegations (no network)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import draft  # noqa: E402
import guard  # noqa: E402


def _post(**kw):
    base = {"template": "sauti", "beats": ["a b c", "d e f", "g h i"], "caption": "x", "line": "x", "message": "x"}
    base.update(kw)
    return base


class Accusation(unittest.TestCase):
    def test_no_face_beside_an_allegation(self):
        pr = guard.accusation_problems(_post(line="Court charged the clerk with fraud", photo_kind="file"))
        self.assertTrue(any("no face" in m for m in pr))
        self.assertEqual(guard.accusation_problems(_post(line="Court charged the clerk with fraud", photo_kind="symbolic")), [])

    def test_named_person_needs_two_outlets_or_an_official_source(self):
        text = "Governor Wanjiru was charged with fraud, the court said"
        one = guard.accusation_problems(_post(line=text, source_links=[{"outlet": "The Star", "link": "https://x"}]))
        self.assertTrue(any("two outlets" in m for m in one))
        two = guard.accusation_problems(_post(line=text, source_links=[{"outlet": "The Star", "link": "https://x"},
                                                                         {"outlet": "Nation", "link": "https://y"}]))
        self.assertEqual(two, [])
        official = guard.accusation_problems(_post(line=text, source="Judiciary https://judiciary.go.ke/case",
                                                   source_links=[{"outlet": "The Star", "link": "https://x"}]))
        self.assertEqual(official, [])

    def test_guilt_stated_as_fact_is_rejected(self):
        two = [{"outlet": "A", "link": "https://x"}, {"outlet": "B", "link": "https://y"}]
        pr = guard.accusation_problems(_post(line="Governor Wanjiru stole public money", source_links=two))
        self.assertTrue(any("who says it" in m for m in pr))

    def test_institution_stories_pass(self):
        self.assertEqual(guard.accusation_problems(_post(line="EACC recovers Sh40 million in grabbed land",
                                                         source_links=[{"outlet": "Capital FM", "link": "https://x"}])), [])


class SingleSource(unittest.TestCase):
    def test_one_outlet_is_named_in_caption_and_first_beat(self):
        p = draft.attribute_single_source({"caption": "Sh40m recovered.", "beats": ["EACC recovers Sh40 million.", "b b", "c c"],
                                           "source_links": [{"outlet": "Capital FM", "link": "https://x"}]})
        self.assertTrue(p["caption"].startswith("Capital FM reports: "))
        self.assertEqual(p["beats"][0], "Capital FM reports: EACC recovers Sh40 million.")

    def test_two_outlets_and_own_data_are_left_alone(self):
        two = {"caption": "c", "beats": ["a b", "c d", "e f"], "source_links": [{"outlet": "A"}, {"outlet": "B"}]}
        self.assertEqual(draft.attribute_single_source(dict(two))["caption"], "c")
        bank = {"caption": "c", "beats": ["a b", "c d", "e f"], "material": {"kind": "bank"}, "source_links": [{"outlet": "EPRA"}]}
        self.assertEqual(draft.attribute_single_source(dict(bank))["caption"], "c")


if __name__ == "__main__":
    unittest.main()
