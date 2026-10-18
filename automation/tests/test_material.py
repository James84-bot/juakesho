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



class Tightened(unittest.TestCase):
    def test_quiz_needs_a_stated_price_not_a_proposal(self):
        self.assertFalse(material._fits("price_figure", "Nyoro's PPK proposes Sh29 fuel price cut, calls for Sh5.5 billion subsidy"))
        self.assertTrue(material._fits("price_figure", "EPRA: petrol now Sh217 per litre in Nairobi"))
        self.assertTrue(material._fits("price_figure", "Unga prices drop to Sh160 for 2kg packet"))

    def test_a_court_fraud_case_is_not_a_scam_tip(self):
        self.assertFalse(material._fits("scam", "Sh3.9bn VAT fraud: Court issues arrest warrants for missing suspects"))
        self.assertTrue(material._fits("scam", "Fraudsters target M-Pesa users with fake reversal texts"))

    def test_scorecard_without_a_report_is_held(self):
        rep = guard.Report(id="x")
        guard.series_rules({"template": "scorecard", "who": "William Ruto", "source": "Constitution of Kenya, Chapter Six"}, rep)
        self.assertTrue(any("report" in e for e in rep.errors))

    def test_old_series_name_as_a_hashtag_is_caught(self):
        rep = guard.Report(id="x")
        guard.series_rules({"template": "straight", "series": "Myth or Fact", "caption": "Verify. #SetItStraight"}, rep)
        self.assertTrue(any("Set It Straight" in e for e in rep.errors))



class Round5(unittest.TestCase):
    def test_quiz_falls_back_to_a_verified_price_valid_on_the_day(self):
        slot = {"id": "q", "template": "glasspoll", "series": "Guess the Price", "publish_at": "2026-10-22T18:00:00+03:00"}
        m = material.pick(slot, set(), used={}, news=[])
        self.assertIn("226.96", m["title"])
        late = {**slot, "publish_at": "2026-12-01T18:00:00+03:00"}
        self.assertIsNone(material.pick(late, set(), used={}, news=[]))

    def test_added_claims_are_caught(self):
        m = {"kind": "bank", "fact": "The 27.1-kilometre road opened on 14 May 2022."}
        self.assertIn("Thousands", material.numbers_problem({"material": m, "beats": ["Thousands use it every day."]}))
        self.assertIn("nationwide", material.numbers_problem({"material": {"kind": "scam", "title": "DCI warns of SIM swap scam"},
                                                              "beats": ["A nationwide crackdown began."]}))
        self.assertEqual(material.numbers_problem({"material": m, "beats": ["It opened in 2022."],
                                                   "caption": "Built in Kenya. Facts on 18 Oct 2026."}), "")

    def test_court_cases_are_not_scam_tips_and_doctored_counts_as_a_check(self):
        self.assertFalse(material._fits("scam", "Congolese in Sh10bn gold scam case charged over fake Kenyan passport"))
        rep = guard.Report(id="x")
        guard.series_rules({"template": "straight", "series": "Myth or Fact", "source_links": [
            {"title": "Image of Kenyan senator Edwin Sifuna asleep at public event is doctored"}],
            "claim": "Image shows senator Edwin Sifuna asleep at public event", "beats": ["The image is doctored."]}, rep)
        self.assertFalse(any("circulating" in e for e in rep.errors), rep.errors)

    def test_a_showcase_keeps_its_own_series_name(self):
        rep = guard.Report(id="x")
        guard.series_rules({"template": "kenya", "series": "Built in Kenya", "beats": ["Kenya at its best: a road."]}, rep)
        self.assertTrue(any("must not call itself" in e for e in rep.errors))



class Round6(unittest.TestCase):
    def test_every_bank_entry_passes_the_showcase_photo_rule(self):
        for e in json.loads(material.BANK.read_text(encoding="utf-8"))["entries"]:
            rep = guard.Report(id=e["id"])
            post = {"template": "kenya", "place": e["place"], "photo_query": e["photo_query"]}
            guard._check_template(post, rep) if hasattr(guard, "_check_template") else None
            place = {w.lower() for w in __import__("re").findall(r"[A-Za-z']{4,}", e["place"])}
            query = {w.lower() for w in __import__("re").findall(r"[A-Za-z']{4,}", e["photo_query"])}
            self.assertTrue(place & query and "kenya" in e["photo_query"].lower(), e["id"])

    def test_a_photo_from_another_story_is_refused(self):
        import posted
        story = "Image of Kenyan senator Edwin Sifuna asleep at public event is doctored"
        self.assertFalse(posted.same_story("Winnie Odinga declares bid for Nairobi senate seat", story))
        self.assertTrue(posted.same_story("Africa Check: doctored image of Sifuna asleep at event", story))

    def test_the_chapter_six_test_is_never_auto_written(self):
        rep = guard.Report(id="x")
        guard.series_rules({"template": "scorecard", "who": "Rigathi Gachagua",
                            "source_links": [{"title": "Fires await Rigathi Gachagua on return from US trip"}]}, rep)
        self.assertTrue(any("researched" in e for e in rep.errors))



class Round7(unittest.TestCase):
    def test_the_writer_cannot_mark_its_own_work_researched(self):
        out = draft._merge([{"id": "s", "template": "scorecard"}], [{"id": "s", "researched": True, "who": "X Y"}])
        self.assertNotIn("researched", out[0])

    def test_guard_message_does_not_explain_how_to_get_past_it(self):
        rep = guard.Report(id="x")
        guard.series_rules({"template": "scorecard", "who": "George Natembeya", "source_links": [{"title": "t"}]}, rep)
        self.assertFalse(any("`researched`" in e for e in rep.errors))


if __name__ == "__main__":
    unittest.main()
