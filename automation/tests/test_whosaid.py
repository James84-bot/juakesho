"""'Who said it?': the weekly quote quiz (whosaid.py)."""
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402
import whosaid  # noqa: E402

NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))
IEBC = {"id": "2026-w47-hot-1119b1743", "hot": True, "drafted_at": "2026-11-19T17:43:00+03:00",
        "who": "Opposition leaders", "message": "Rigathi Gachagua and Kalonzo Musyoka walked out of an IEBC meeting.",
        "beats": ["Opposition leaders *walked out* of an IEBC meeting.", "Do you trust the IEBC?"],
        "quotes": [
            {"speaker": "Kalonzo", "text": "We came to the IEBC today in good faith", "outlet": "The Star",
             "link": "https://star.test/a", "context": "Wiper leader Kalonzo Musyoka said they came in good faith."},
            {"speaker": "Gachagua", "text": "Since our meeting then in January, you have never called us for a "
             "meeting. This is the first time", "outlet": "The Star", "link": "https://star.test/a", "context": ""},
            {"speaker": "IEBC", "text": "The commission remains open to all political parties at all times",
             "outlet": "KBC", "link": "https://kbc.test/b", "context": ""}]}


class Candidates(unittest.TestCase):
    def test_short_exact_quotes_by_a_named_person_only(self):
        got = whosaid.candidates([IEBC], NOW, used=set())
        self.assertEqual([(c["name"], c["words"]) for c in got],   # Gachagua's opens with 14 words; IEBC is a body
                         [("Kalonzo Musyoka", "We came to the IEBC today in good faith"),
                          ("Rigathi Gachagua", "Since our meeting then in January, you have never called us for a meeting")])

    def test_old_posts_used_quotes_and_allegations_are_left_out(self):
        old = {**IEBC, "drafted_at": "2026-11-10T09:00:00+03:00"}
        self.assertEqual(whosaid.candidates([old], NOW, used=set()), [])
        used = {whosaid._key("We came to the IEBC today in good faith"),
                whosaid._key("Since our meeting then in January, you have never called us for a meeting")}
        self.assertEqual(whosaid.candidates([IEBC], NOW, used=used), [])
        accused = {**IEBC, "message": "MP charged with fraud over a road tender walked out of an IEBC meeting."}
        self.assertEqual(whosaid.candidates([accused], NOW, used=set()), [])

    def test_a_long_quote_gives_its_opening_sentence_or_clause_word_for_word(self):
        self.assertEqual(whosaid.excerpt("We came to the IEBC today in good faith, and we expected the same in "
                                         "return. Good faith is a two-way street."),
                         "We came to the IEBC today in good faith")
        self.assertEqual(whosaid.excerpt("Since our meeting then in January, you have never called us for a meeting. "
                                         "This is the first time"),
                         "Since our meeting then in January, you have never called us for a meeting")
        self.assertEqual(whosaid.excerpt("Yes."), "")
        import quotes
        q = [{"speaker": "Kalonzo", "text": "We came to the IEBC today in good faith, and we expected the same."}]
        self.assertEqual(quotes.problem("Who said it?: “We came to the IEBC today in good faith”", q), "")

    def test_a_one_word_speaker_is_looked_up_only_when_one_kenyan_figure_fits(self):
        one = {"search": [{"label": "Rigathi Gachagua", "description": "Kenyan politician, Deputy President 2022-2024"},
                          {"label": "Gachagua", "description": "family name"}]}
        self.assertEqual(whosaid.wikidata_name("Gachagua", get=lambda url: one), "Rigathi Gachagua")
        two = {"search": [{"label": "John Ochieng", "description": "Kenyan politician"},
                          {"label": "Paul Ochieng", "description": "Kenyan footballer"}]}
        self.assertEqual(whosaid.wikidata_name("Ochieng", get=lambda url: two), "")
        self.assertEqual(whosaid.wikidata_name("Ochieng", get=lambda url: (_ for _ in ()).throw(OSError())), "")

    def test_a_dependent_clause_is_not_a_quote_on_its_own(self):
        self.assertEqual(whosaid.excerpt("When a player is called up for Kenya, he should know he will eat well."), "")

    def test_a_surname_alone_is_not_enough_to_search_a_face(self):
        self.assertEqual(whosaid.full_name("Mr Singh", ["Investors are worried, Mr Singh said."]), "")
        self.assertEqual(whosaid.full_name("Treasury CS Mbadi", ["CS John Mbadi told MPs"]), "John Mbadi")


class Choosing(unittest.TestCase):
    def setUp(self):
        self.c = whosaid.candidates([IEBC], NOW, used=set())

    def test_the_writers_pick_and_a_clue_that_keeps_the_answer_hidden(self):
        call = lambda system, user, max_tokens=0: '{"pick": 0, "clue": "He leads the Wiper party, the report says."}'
        c, clue = whosaid.choose(self.c, call)
        self.assertEqual(c["name"], "Kalonzo Musyoka")
        self.assertTrue(clue.startswith("He leads"))

    def test_a_clue_that_names_them_or_runs_long_is_refused(self):
        for clue in ("Kalonzo said it at the IEBC.", "A clue that runs on and on for far more than twelve words in total.",
                     "He leads Wiper"):
            call = lambda system, user, max_tokens=0, clue=clue: json.dumps({"pick": 0, "clue": clue})
            self.assertIsNone(whosaid.choose(self.c, call), clue)
        self.assertIsNone(whosaid.choose(self.c, lambda *a, **k: '{"pick": -1, "clue": ""}'))


class ThePost(unittest.TestCase):
    def test_the_quote_hides_the_speaker_until_the_last_line_and_passes_the_guard(self):
        from PIL import Image
        c = whosaid.candidates([IEBC], NOW, used=set())[0]
        with tempfile.TemporaryDirectory() as tmp:
            face = Path(tmp) / "face.jpg"
            Image.new("RGB", (800, 600), (180, 120, 90)).save(face)
            post = whosaid.post_for(c, "He leads the Wiper party, the report says.", "2026-w47-whosaid-1122",
                                    "2026-11-28T17:30:00+03:00", {"file": str(face), "credit": "Photo: The Star",
                                                                  "kind": "posted"}, Path(tmp), NOW)
            self.assertTrue(Path(post["photo_file"]).exists())
            self.assertNotEqual(Path(post["photo_file"]).read_bytes(), face.read_bytes())   # blurred, not the face
        self.assertEqual(guard.quote_beat(post["beats"][0]), ("Who said it?", "We came to the IEBC today in good faith"))
        self.assertEqual(guard.quote_beat(post["beats"][-1])[0], "Kalonzo Musyoka")
        self.assertEqual(post["shot_seq"], [0, 0, 0, 1])
        hidden = " ".join(post["beats"][:3]) + post["caption"] + post["quote"] + post["kicker"]
        self.assertNotIn("Kalonzo", hidden)
        self.assertNotIn("Musyoka", hidden)
        self.assertEqual(guard.check(post).errors, [])


class Slot(unittest.TestCase):
    def test_saturday_1730_with_three_hours_notice(self):
        import pipeline as pl
        sat_morning = dt.datetime(2026, 11, 28, 11, 0, tzinfo=pl.EAT)
        self.assertEqual(pl.whosaid_slot(sat_morning), dt.datetime(2026, 11, 28, 17, 30, tzinfo=pl.EAT))
        sat_late = dt.datetime(2026, 11, 28, 15, 0, tzinfo=pl.EAT)
        self.assertEqual(pl.whosaid_slot(sat_late), dt.datetime(2026, 12, 5, 17, 30, tzinfo=pl.EAT))
        self.assertEqual(pl.whosaid_slot(NOW), dt.datetime(2026, 11, 28, 17, 30, tzinfo=pl.EAT))

    def test_the_quiz_may_go_out_by_itself_with_the_speakers_face(self):
        import pipeline as pl
        post = {"template": "sauti", "hand": True, "whosaid": True, "source_links": [{"link": "x"}],
                "photo_kind": "file", "guard": {"errors": [], "warnings": []}}
        self.assertEqual(pl.auto_ok(post), "")
        self.assertEqual(pl.auto_ok({**post, "whosaid": False}), "uses a named person's portrait")


if __name__ == "__main__":
    unittest.main()
