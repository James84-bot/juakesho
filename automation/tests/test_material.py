"""Real material for the everyday series: picked by the system, locked into the post, numbers checked (no network)."""
import datetime as dt
import json
import os
import sys
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import draft  # noqa: E402
import guard  # noqa: E402
import material  # noqa: E402

NEWS = [
    {"title": "Ruto defends UDA-ODM pact in Eldoret", "outlet": "Daily Nation", "link": "https://x/1", "published": "2026-10-17"},
    {"title": "Unga prices drop to Sh160 for 2kg packet in Nairobi", "outlet": "The Star", "link": "https://x/2", "published": "2026-10-16"},
    {"title": "EPRA raises fuel prices in latest review", "outlet": "Capital FM", "link": "https://x/3", "published": "2026-10-15"},
    {"title": "PesaCheck: Viral claim of free laptops for students is FALSE", "outlet": "PesaCheck", "link": "https://x/4", "published": "2026-10-14"},
    {"title": "DCI warns of new M-Pesa reversal scam", "outlet": "Kenyans.co.ke", "link": "https://x/5", "published": "2026-10-13"},
]


class Bank(unittest.TestCase):
    def test_every_fact_is_short_sourced_and_in_a_known_series(self):
        entries = json.loads(material.BANK.read_text(encoding="utf-8"))["entries"]
        self.assertGreaterEqual(len(entries), 12)
        self.assertEqual(len({e["id"] for e in entries}), len(entries))
        for e in entries:
            self.assertIn(e["series"], {"Kenya at its best", "Built in Kenya"})
            self.assertLessEqual(len(e["fact"]), 150, e["id"])
            self.assertTrue(e["source"].startswith("https://"), e["id"])
            self.assertLessEqual(len(e["place"]), 40, e["id"])

    def test_showcase_gets_an_unused_fact_and_rests_it(self):
        slot = {"id": "s", "template": "kenya", "series": "Built in Kenya"}
        first = material.pick(slot, set(), used={})
        self.assertEqual(first["kind"], "bank")
        again = material.pick(slot, set(), used={first["key"]: dt.date.today().isoformat()})
        self.assertNotEqual(again["key"], first["key"])
        self.assertIsNone(material.pick(slot, set(), used={}, bank=[]))


class News(unittest.TestCase):
    def test_each_series_takes_only_a_report_about_its_subject(self):
        def get(**slot):
            return material.pick({"id": "s", **slot}, set(), used={}, news=NEWS)
        self.assertEqual(get(template="glasspoll", series="Guess the Price")["link"], "https://x/2")   # states a price
        self.assertEqual(get(template="money", angle="real_price")["link"], "https://x/2")
        self.assertEqual(get(template="straight", series="Myth or Fact")["link"], "https://x/4")
        self.assertEqual(get(template="usiibiwe")["link"], "https://x/5")
        self.assertIsNone(get(template="glasspoll", hot=True))
        self.assertIsNone(material.pick({"id": "s", "template": "usiibiwe"}, set(), used={}, news=NEWS[:1]))

    def test_used_or_taken_reports_are_not_reused(self):
        slot = {"id": "s", "template": "money", "angle": "real_price"}
        self.assertEqual(material.pick(slot, {"news:https://x/2"}, used={}, news=NEWS)["link"], "https://x/3")
        self.assertIsNone(material.pick(slot, set(), used={"news:https://x/2": "x", "news:https://x/3": "x"}, news=NEWS))


class Locked(unittest.TestCase):
    def test_writer_cannot_change_the_material(self):
        slot = {"id": "s", "template": "kenya", "series": "Kenya at its best"}
        m = material.pick(slot, set(), used={})
        slot = {**slot, "material": m, "fact": m["fact"], "source": m["source"], "place": m["place"],
                "photo_query": m["photo_query"], "source_links": [{"title": m["name"], "link": m["source"]}]}
        out = material.lock({"id": "s", "fact": "Invented 1950 fact", "source": "n3", "source_links": []}, slot)
        self.assertEqual((out["fact"], out["source"]), (m["fact"], m["source"]))

    def test_prompt_carries_the_material(self):
        m = {"kind": "price_figure", "title": NEWS[1]["title"], "outlet": "The Star", "published": "2026-10-16"}
        system, user = draft.build_prompt("2026-W43", [{"id": "s", "template": "glasspoll", "lane": "everyone",
                                                         "material": m}], {}, [])
        self.assertIn("Sh160 for 2kg", system + user)


class Numbers(unittest.TestCase):
    QUIZ = {"kind": "price_figure", "title": "Unga prices drop to Sh160 for 2kg packet in Nairobi", "published": "2026-10-16"}

    def quiz(self, options, last):
        return {"template": "glasspoll", "material": self.QUIZ, "question": "How much is a 2kg packet of unga?",
                "options": options, "beats": ["Unga is cheaper this week.", last]}

    def test_guess_the_price_answer_must_be_the_reported_price(self):
        self.assertEqual(material.numbers_problem(self.quiz(["A: Sh140", "B: Sh160"], "The answer is B: Sh160.")), "")
        self.assertIn("last beat", material.numbers_problem(self.quiz(["A: Sh140", "B: Sh160"], "The answer is A: Sh140.")))
        self.assertIn("exactly one", material.numbers_problem(self.quiz(["A: Sh140", "B: Sh150"], "The answer is Sh160.")))

    def test_showcase_numbers_only_from_the_fact(self):
        m = {"kind": "bank", "fact": "Gazetted in 1984, the park covers about 68 square kilometres."}
        ok = {"material": m, "beats": ["Since 1984 it has covered 68 square kilometres."]}
        bad = {"material": m, "beats": ["It covers 767 square kilometres."]}
        self.assertEqual(material.numbers_problem(ok), "")
        self.assertIn("767", material.numbers_problem(bad))

    def test_the_reports_own_date_may_be_named(self):
        m = {"kind": "scam", "title": "DCI warns of new M-Pesa reversal scam", "published": "2026-10-13"}
        self.assertEqual(material.numbers_problem({"material": m, "beats": ["On 13 Oct, the DCI warned Kenyans."]}), "")

    def test_guard_runs_the_number_check(self):
        post = {"template": "kenya", "material": {"kind": "bank", "fact": "Opened in 2022."}, "beats": ["Opened in 2019."]}
        rep = guard.Report(id="x") if hasattr(guard, "Report") else None
        guard.series_rules(post, rep)
        self.assertTrue(any("2019" in e for e in rep.errors))


if __name__ == "__main__":
    unittest.main()
