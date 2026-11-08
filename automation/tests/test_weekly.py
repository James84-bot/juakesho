"""Kenya This Week: the week's stories picked from what went out, a script that states nothing its posts don't,
one voice note per part, chapters and a Sunday 18:00 release."""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import weekly  # noqa: E402

EAT = dt.timezone(dt.timedelta(hours=3))


def post(pid, day, beats, **kw):
    return {"id": pid, "status": "published", "publish_at": f"2026-11-0{day}T12:45:00+03:00",
            "published_at": f"2026-11-0{day}T12:46:00+03:00", "beats": beats, **kw}


FKF = post("fkf", 8, ["FKF ousted vice-president *McDonald Mariga* and six other officials.",
                      "Police fired *teargas* before the special meeting in Meru began."],
           caption="FKF removed Mariga and six officials on Saturday.", source_links=[{"outlet": "Capital FM", "title": "Mariga ousted", "link": "https://c/1"}])
SUGAR = post("sugar", 7, ["Sugar is *Sh32* cheaper for a 2kg packet.", "Factories milled 56.7% more cane."],
             caption="Sugar output rose 56.7%.")


def words(n):
    """n words of filler, in sentences of ten (a script is read aloud: no endless sentences)."""
    w = ["word"] * n
    return " ".join(" ".join(w[i:i + 10]) + "." for i in range(0, n, 10))


class Pick(unittest.TestCase):
    def test_only_published_scripted_posts_in_the_window(self):
        weeks = [{"collection": "2026-W45", "posts": [FKF, SUGAR, {**SUGAR, "id": "x", "status": "approved"},
                                                      {**SUGAR, "id": "y", "beats": []}, {**SUGAR, "id": "z", "template": "tazama"}]}]
        got = weekly.candidates(weeks, dt.datetime(2026, 11, 2, tzinfo=EAT), dt.datetime(2026, 11, 8, 18, tzinfo=EAT))
        self.assertEqual({p["id"] for p in got}, {"fkf", "sugar"})

    def test_most_watched_first_then_in_order_and_never_the_same_story_twice(self):
        twin = {**FKF, "id": "fkf2", "published_at": "2026-11-08T15:00:00+03:00"}
        learned = {"youtube": [{"id": "fkf", "views": 900}, {"id": "fkf2", "views": 800}, {"id": "sugar", "views": 10}]}
        got = weekly.pick([FKF, twin, SUGAR], learned, n=3)
        self.assertEqual([p["id"] for p in got], ["sugar", "fkf"])   # by date; the twin story is left out


class Script(unittest.TestCase):
    def script(self, fkf_text=None, intro=None):
        return {"title": "FKF ousts Mariga, sugar gets cheaper and more", "thumbnail": "Mariga out",
                "intro": intro or words(60), "outro": words(50),
                "stories": [{"id": "sugar", "chapter": "Sugar gets cheaper", "script": words(150) + " Sh32 and 56.7% cheaper."},
                            {"id": "fkf", "chapter": "FKF ousts Mariga", "script": fkf_text or words(160)}]}

    def test_a_clean_script_passes(self):
        self.assertEqual(weekly.check(self.script(), [SUGAR, FKF]), [])

    def test_a_number_its_story_does_not_state_fails(self):
        problems = weekly.check(self.script(fkf_text=words(160) + " The vote was 45 to 12."), [SUGAR, FKF])
        self.assertTrue(any("fkf: numbers not in its story: 12, 45" in p for p in problems), problems)

    def test_too_many_demands_and_endless_sentences_fail(self):
        s = self.script(intro=words(40) + " Kenyans demand this. They demand that. We demand more. " + " ".join(["long"] * 30) + ".")
        problems = " | ".join(weekly.check(s, [SUGAR, FKF]))
        self.assertIn("'demand' is said more than twice", problems)
        self.assertIn("over 28 words", problems)

    def test_wrong_order_banned_words_and_em_dashes_fail(self):
        s = self.script(intro=words(55) + " Let's delve into it — now.")
        s["stories"].reverse()
        problems = " | ".join(weekly.check(s, [SUGAR, FKF]))
        self.assertIn("exactly the given ids", problems)
        self.assertIn("delve", problems)
        self.assertIn("em dash", problems)

    def test_the_writer_is_asked_again_with_what_was_wrong(self):
        asked = []

        def ask(system, user):
            asked.append(user)
            return self.script(fkf_text=words(160) + " 99 people.") if len(asked) == 1 else self.script()

        script, problems = weekly.write([SUGAR, FKF], "1 to 8 Nov 2026", ask=ask)
        self.assertEqual(problems, [])
        self.assertIn("numbers not in its story: 99", asked[1])

    def test_dates_are_the_same_number_however_written(self):
        self.assertEqual(weekly.numbers("on 07 Nov, Sh1,200 and 56.7%"), {"7", "1200", "56.7"})
        s = self.script(intro=words(60) + " From 1 to 8 November.")
        self.assertEqual(weekly.check(s, [SUGAR, FKF], extra="1 to 8 Nov 2026"), [])

    def test_parts_and_voice_notes(self):
        state = {"status": "recording", "parts": weekly.parts(self.script())}
        self.assertEqual([p["key"] for p in state["parts"]], ["intro", "sugar", "fkf", "outro"])
        for i, p in enumerate(state["parts"]):
            p["msg"] = 100 + i
        self.assertIsNone(weekly.file_voice(state, 999, {"file_id": "x"}))
        for i in range(4):
            weekly.file_voice(state, 100 + i, {"file_id": f"v{i}", "duration": 30})
        self.assertEqual(state["status"], "ready")
        weekly.file_voice(state, 101, {"file_id": "again"})          # re-recorded: the last one counts
        self.assertEqual(state["parts"][1]["voice"]["file_id"], "again")


class Release(unittest.TestCase):
    def test_sunday_six_pm_or_now_when_it_has_passed(self):
        sat = dt.datetime(2026, 11, 14, 9, 0, tzinfo=EAT)
        self.assertEqual(weekly.publish_at(sat), dt.datetime(2026, 11, 15, 18, 0, tzinfo=EAT))
        self.assertIsNone(weekly.publish_at(dt.datetime(2026, 11, 15, 19, 0, tzinfo=EAT)))

    def test_chapters_start_at_zero(self):
        self.assertEqual(weekly.chapters([("Intro", 32.4), ("Sugar gets cheaper", 75.0), ("FKF ousts Mariga", 80.2)]),
                         "0:00 Intro\n0:32 Sugar gets cheaper\n1:47 FKF ousts Mariga")

    def test_description_has_chapters_and_sources(self):
        d = weekly.description({"summary": "The week."}, [FKF], "0:00 Intro")
        self.assertIn("Chapters\n0:00 Intro", d)
        self.assertIn("Capital FM: Mariga ousted https://c/1", d)


class Pictures(unittest.TestCase):
    def test_a_big_photo_fills_the_plate_and_a_small_one_sits_whole_and_sharp(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            big, small = Path(d) / "b.jpg", Path(d) / "s.jpg"
            Image.new("RGB", (2400, 1350), (200, 30, 30)).save(big)
            Image.new("RGB", (700, 400), (30, 200, 30)).save(small)
            for src in (big, small):
                out = weekly.plate(src, Path(d) / f"p-{src.name}")
                with Image.open(out) as im:
                    self.assertEqual(im.size, weekly.PLATE)
            with Image.open(Path(d) / "p-s.jpg") as im:
                px = im.getpixel((5, 5))
            self.assertLess(max(px), 120)   # the blurred, darkened copy behind the small photo

    def test_a_new_picture_about_every_nine_seconds(self):
        self.assertEqual(weekly.shots(36, 2), [(0, 9.0), (1, 9.0), (0, 9.0), (1, 9.0)])
        self.assertEqual(weekly.shots(4, 3), [(0, 4.0)])


if __name__ == "__main__":
    unittest.main()
