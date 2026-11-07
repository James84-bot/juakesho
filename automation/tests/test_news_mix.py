"""The writer's headline list is a mix of topics, not just the newest politics (no network)."""
import os
import sys
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import news  # noqa: E402


def item(topic, i):
    return {"topic": topic, "title": f"{topic} {i}", "outlet": "Capital FM News", "published": f"2026-11-0{7 - i}"}


class Mix(unittest.TestCase):
    def test_each_topic_is_capped_so_politics_cannot_crowd_out_sport(self):
        items = [item("politics", i % 7) for i in range(30)] + [item("sport", 1)]
        kept = news._per_topic(items, 8)
        self.assertEqual(sum(1 for x in kept if x["topic"] == "politics"), 8)
        self.assertEqual(sum(1 for x in kept if x["topic"] == "sport"), 1)

    def test_the_writers_list_takes_turns_across_topics_newest_first(self):
        items = [item("politics", 0), item("politics", 1), item("politics", 2), item("sport", 0), item("health", 0), item("pride", 0)]
        out = news._spread(items, 5)
        self.assertEqual([x["topic"] for x in out], ["politics", "sport", "health", "pride", "politics"])
        self.assertEqual(out[0]["title"], "politics 0")

    def test_a_short_list_returns_everything_and_never_loops_forever(self):
        items = [item("sport", 0), item("health", 0)]
        self.assertEqual(len(news._spread(items, 18)), 2)
        self.assertEqual(news._spread([], 18), [])

    def test_the_new_feeds_are_configured_with_their_topics(self):
        import json
        feeds = json.loads((Path(news.__file__).parent / "content" / "news_feeds.json").read_text(encoding="utf-8"))["feeds"]
        topics = {f["topic"] for f in feeds}
        self.assertTrue({"sport", "sport_world", "entertainment", "tech", "health", "pride"} <= topics)

    def test_sport_headlines_are_added_beyond_the_mix_with_stable_ids(self):
        import json
        import tempfile
        from unittest import mock
        topics = ["politics", "money", "health", "tech", "pride", "rights", "news", "elections", "counties",
                  "accountability", "entertainment", "sport", "sport_world"]
        items = [item(t, i) for i in range(3) for t in topics]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "news.json"
            out.write_text(json.dumps({"fetched": "2026-11-07T00:00:00+00:00", "items": items}))
            with mock.patch.object(news, "OUT", out):
                first, again = news.refs(), news.refs()
        self.assertEqual(first, again)   # an id means the same story in the prompt and when it is resolved
        sport = [x for x in first.values() if x["topic"] in news.SPORT_TOPICS]
        self.assertEqual(len(sport), 6)   # all six: 2 in the 18-headline mix, 4 added after it
        self.assertEqual(len(first), news.MAX_ITEMS + 4)
        self.assertEqual(len({x["title"] for x in first.values()}), len(first))   # nothing listed twice

    def test_sport_bodies_and_sport_newsrooms_are_sources_betting_blogs_are_not(self):
        for ok in ("BBC Sport", "Sky Sports", "ESPN", "The Athletic", "World Athletics", "Premier League", "UEFA.com"):
            self.assertTrue(news.newsroom(ok), ok)
        for no in ("SportPesa News", "Betika Blog", "Mozzart Sport", "Goal.com"):
            self.assertFalse(news.newsroom(no), no)


if __name__ == "__main__":
    unittest.main()
