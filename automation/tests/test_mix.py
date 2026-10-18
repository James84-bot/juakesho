"""Six in ten posts about everyday life: the new series and the news beats (no network)."""
import json
import os
import sys
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import draft  # noqa: E402
import pipeline  # noqa: E402

LIFE = {"The Real Price", "Kenya at its best", "Guess the Price", "Myth or Fact", "Built in Kenya"}


class WeeklyMix(unittest.TestCase):
    def test_new_everyday_series_are_scheduled_with_their_angles(self):
        posts = pipeline._calendar_posts("2026-W44")
        by_series = {p.get("series"): p for p in posts}
        for s in ("Guess the Price", "Myth or Fact"):
            self.assertIn(s, by_series)
        self.assertEqual(by_series["Myth or Fact"]["angle"], "myth")
        self.assertEqual(by_series["Guess the Price"]["angle"], "price_quiz")
        money = [p for w in ("2026-W44", "2026-W45") for p in pipeline._calendar_posts(w) if p["template"] == "money"]
        self.assertTrue(money)
        self.assertTrue(all(p["angle"] == "real_price" and p["series"] == "The Real Price" for p in money))
        usi = [p for w in ("2026-W44", "2026-W45") for p in pipeline._calendar_posts(w) if p["template"] == "usiibiwe"]
        self.assertTrue(all("angle" not in p for p in usi))   # the price angle never lands on a scam post

    def test_six_in_ten_are_everyday_life(self):
        weekly = pipeline._calendar_posts("2026-W44")
        life_weekly = sum(1 for p in weekly if p.get("series") in LIFE or p["template"] == "usiibiwe")
        life_news = sum(1 for e in pipeline.EDITIONS.values() if e["beat"] == "life") * 7
        total = len(weekly) + len(pipeline.EDITIONS) * 7
        self.assertGreaterEqual((life_weekly + life_news) / total, 0.6)


class NewsBeat(unittest.TestCase):
    def test_life_beat_asks_for_a_non_political_story(self):
        slot = {"id": "x", "template": "sauti", "lane": "everyone", "hot": True, "beat": "life"}
        _, user = draft.build_prompt("2026-W44", [slot], {}, [], scripts=False)
        self.assertIn("EVERYDAY-LIFE", user)
        slot["beat"] = "politics"
        _, user = draft.build_prompt("2026-W44", [slot], {}, [], scripts=False)
        self.assertIn("political story", user)


if __name__ == "__main__":
    unittest.main()


class SeriesRules(unittest.TestCase):
    def setUp(self):
        import guard
        self.guard = guard

    def errs(self, post):
        rep = self.guard.Report(id="t")
        self.guard.series_rules(post, rep)
        return " ".join(rep.errors)

    def test_scam_numbers_must_be_masked(self):
        self.assertIn("masked", self.errs({"template": "usiibiwe", "sender": "+254 712 345 678"}))
        self.assertEqual("", self.errs({"template": "usiibiwe", "sender": "+254 7XX XXX XXX"}))

    def test_price_needs_a_price_report_and_the_quiz_its_answer(self):
        post = {"template": "glasspoll", "series": "Guess the Price", "question": "How much is 2kg of unga now?",
                "options": ["A: Sh140", "B: Sh160"],
                "beats": ["How much?", "A or B?", "Comment!"],
                "source_links": [{"title": "Luxury car stolen in UK traced to Nairobi"}]}
        e = self.errs(post)
        self.assertIn("report about that price", e)
        self.assertIn("LAST beat", e)
        post["source_links"] = [{"title": "Unga prices drop to Sh160 as maize harvest arrives"}]
        post["beats"][-1] = "The answer is B: Sh160."
        self.assertEqual("", self.errs(post))

    def test_myth_needs_proof_the_rumour_exists(self):
        post = {"template": "straight", "series": "Myth or Fact", "caption": "Myth or Fact: ...",
                "claim": "A herbal tea is an Ebola cure.",
                "source_links": [{"title": "Ebola cases rise to 7"}]}
        self.assertIn("really circulating", self.errs(post))
        post["source_links"].append({"title": "Health ministry warns of fake Ebola cure messages"})
        self.assertEqual("", self.errs(post))

    def test_linked_report_must_be_about_the_story(self):
        post = {"template": "straight", "claim": "Free laptops for every student this week.",
                "source_links": [{"title": "JKIA cleaner arrested carrying bags containing 52 phones"}]}
        self.assertIn("not about this story", self.errs(post))

    def test_no_blame_polls(self):
        self.assertIn("blame", self.errs({"template": "glasspoll", "question": "Who caused the Kitale clashes?"}))

    def test_caption_uses_the_new_series_name(self):
        post = {"template": "straight", "series": "Myth or Fact", "caption": "Set It Straight: x",
                "source_links": [{"title": "PesaCheck: fake notice"}]}
        self.assertIn("series is 'Myth or Fact'", self.errs(post))
