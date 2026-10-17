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
