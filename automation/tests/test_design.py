"""The news look, 22 Nov: the story's person leads, a club's story takes its colours, our mark reads on a phone,
and a short exact quote may open the Reel."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402
import photos  # noqa: E402
import teams  # noqa: E402

BRUNO = {"who": "Manchester United", "hot": True,
         "message": "Bruno Fernandes puts new contract talks on hold as Manchester United struggle.",
         "beats": ["Bruno Fernandes puts talks on *hold*.", "The club sits outside the top four.",
                   "Fans watch to see if he stays.", "Tell us below: will Fernandes sign?"]}


class StoryPerson(unittest.TestCase):
    def test_the_person_a_headline_opens_with_leads_even_when_who_is_the_club(self):
        self.assertEqual(photos.story_person(BRUNO), "Bruno Fernandes")
        self.assertEqual(photos.lead_person(BRUNO), "Bruno Fernandes")

    def test_who_names_the_person_when_it_can(self):
        self.assertEqual(photos.story_person({"who": "Energy CS Opiyo Wandayi", "message": "Fuel prices drop."}),
                         "Opiyo Wandayi")

    def test_clubs_bodies_and_openers_are_not_people(self):
        for post in ({"who": "Gor Mahia", "message": "Gor Mahia beat AFC Leopards in the Mashemeji derby."},
                     {"who": "KRA", "message": "KRA will use bank data to find missing tax returns."},
                     {"who": "", "message": "Aston Villa sack their coach after a loss."},
                     {"who": "", "message": "Breaking News Kenya update on fuel prices."},
                     {"who": "CAF", "message": "CAF names Nairobi as Kenya's sole host city for AFCON 2027."}):
            self.assertEqual(photos.story_person(post), "", post["message"])

    def test_no_face_is_asked_for_beside_an_allegation(self):
        accused = {"who": "Governor John Doe", "message": "Governor John Doe charged with fraud over a road tender."}
        self.assertEqual(photos.lead_person(accused), "")


class ClubColours(unittest.TestCase):
    def test_a_club_story_takes_its_clubs_colour_and_readable_ink(self):
        got = teams.accent_for(BRUNO)
        self.assertEqual((got["club"], got["colour"], got["ink"]), ("Manchester United", "#DA291C", "#FFFFFF"))
        city = teams.accent_for({"message": "Man City beat Arsenal 2-1 at the Etihad."})
        self.assertEqual((city["club"], city["ink"]), ("Manchester City", "#0E0C0B"))   # sky blue: dark ink reads

    def test_politics_and_stories_without_a_known_club_keep_the_brand_red(self):
        self.assertIsNone(teams.accent_for({"beat": "politics", "message": "Arsenal fan MP tables a bill."}))
        self.assertIsNone(teams.accent_for({"message": "Harambee Stars lose 2-0 to Gabon."}))
        self.assertIsNone(teams.accent_for({"message": "United Nations warns on drought."}))   # not "Man United"


class QuoteOpening(unittest.TestCase):
    def test_a_short_exact_quote_may_open_the_reel(self):
        self.assertEqual(guard.hook_problem("Kalonzo: “We came to the IEBC today in good faith”"), "")

    def test_a_long_one_goes_second(self):
        self.assertIn("open with the news",
                      guard.hook_problem("Gachagua: “Since our meeting then in January, you have never called us for "
                                         "a meeting, and this is the first time”"))


class Template(unittest.TestCase):
    def test_the_mark_is_on_the_picture_big_enough_and_a_clubs_colour_reaches_the_css(self):
        src = (Path(__file__).resolve().parent.parent / "templates" / "reel.html.j2").read_text(encoding="utf-8")
        self.assertIn(".top img { height: 44px", src)
        self.assertIn("--shuka-500: {{ accent.colour }}", src)
        self.assertIn("--sfx: {{ sh.fx", src)


if __name__ == "__main__":
    unittest.main()
