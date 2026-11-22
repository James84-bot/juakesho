"""James, 23 Nov: "if we quote someone use their picture or video". The line that gives someone's words shows them."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import photos  # noqa: E402
import pipeline as pl  # noqa: E402
import render  # noqa: E402

QUOTES = [{"speaker": "Treasury CS John Mbadi", "text": "We will not raise taxes on fuel this year", "outlet": "Nation",
           "context": "Treasury CS John Mbadi told the Senate on Tuesday."}]


def post(beats, **kw):
    return {"id": "2026-w48-hot-1123a", "template": "reel", "hot": True, "beats": beats, "quotes": QUOTES,
            "who": "National Treasury", "source_links": [{"title": "Mbadi rules out new fuel taxes", "link": "https://n/1"}],
            **kw}


QUOTE_LINE = "Treasury CS Mbadi: “We will not raise taxes on fuel this year”"


class WhoIsQuoted(unittest.TestCase):
    def test_the_speaker_by_full_name_and_their_line(self):
        p = post(["Fuel taxes stay where they are for 2027.", QUOTE_LINE, "Will pump prices still rise?"])
        self.assertEqual(photos.quoted_speaker(p, lookup=False), ("John Mbadi", 1))

    def test_a_body_or_an_allegation_gets_no_face(self):
        body = post(["Inflation eased in October.", "KNBS: “Prices rose 4.1% over the year to October”", "Is it felt?"])
        self.assertEqual(photos.quoted_speaker(body, lookup=False), ("", -1))
        accused = post(["An MP was charged with fraud today.", QUOTE_LINE, "What next?"])
        self.assertEqual(photos.quoted_speaker(accused, lookup=False), ("", -1))

    def test_a_reel_that_opens_with_their_words_leads_with_their_picture(self):
        with mock.patch("whosaid.wikidata_name", lambda w, get=None: ""):
            self.assertEqual(photos.lead_person(post([QUOTE_LINE, "He told the Senate on Tuesday.", "Fair?"])), "John Mbadi")
            self.assertEqual(photos.lead_person(post(["Fuel taxes stay as they are.", QUOTE_LINE, "Fair?"])), "")


class TheirLine(unittest.TestCase):
    def test_their_picture_goes_on_their_line_and_nowhere_else(self):
        self.assertEqual(render.place_speaker([0, 1, 2, 1], [3, 2], 3), [0, 1, 0, 2])
        self.assertEqual(render.place_speaker([0, -1, 1, -1], [3, -1], 2), [0, -1, 1, -1])   # the clip of them
        self.assertEqual(render.place_speaker([0, 1, 2], [0, 2], 3), [0, 1, 2])             # the cover stays
        self.assertEqual(render.place_speaker([0, 1, 2], None, 3), [0, 1, 2])

    def test_a_picture_of_them_is_added_for_their_line(self):
        p = post(["Fuel taxes stay as they are.", QUOTE_LINE, "Fair?"], extra_photos=["b.jpg"],
                 shot_info=[{"credit": "Photo: Nation"}, {"credit": "Photo: Star"}], photo_credit="Photo: Nation")
        face = {"file": "mbadi.jpg", "credit": "File photo: Citizen Digital", "kind": "file"}
        with mock.patch.object(photos, "speaker_photo", lambda q, name, out: face if name == "John Mbadi" else None), \
                mock.patch("whosaid.wikidata_name", lambda w, get=None: ""):
            photos._speaker_line(p, {"kind": "topic"}, "", Path("."))
        self.assertEqual(p["extra_photos"], ["b.jpg", "mbadi.jpg"])
        self.assertEqual(p["speaker_shot"], [1, 2])
        self.assertIn("File photo: Citizen Digital", p["photo_credit"])

    def test_the_lead_picture_when_it_is_of_them(self):
        p = post([QUOTE_LINE, "He told the Senate on Tuesday.", "Fair?"])
        with mock.patch.object(photos, "speaker_photo", lambda *a: self.fail("no second picture needed")), \
                mock.patch("whosaid.wikidata_name", lambda w, get=None: ""):
            photos._speaker_line(p, {"kind": "posted"}, "John Mbadi", Path("."))
        self.assertEqual(p["speaker_shot"], [0, 0])

    def test_the_reel_shows_their_picture_on_their_line(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            files = []
            for n, c in (("a", (90, 60, 40)), ("b", (40, 60, 90)), ("face", (200, 180, 160))):
                f = Path(tmp) / f"{n}.jpg"
                Image.new("RGB", (1600, 1200), c).save(f)
                files.append(str(f))
            p = post(["Fuel taxes stay as they are.", "Pump prices rose twice this year.", QUOTE_LINE, "Fair?"],
                     size="story", bg="usiku", kicker="Money", publish_at="2026-11-23T12:45:00+03:00",
                     photo_file=files[0], photo_credit="Photo: Nation", extra_photos=files[1:],
                     shot_info=[{}, {}, {"speaker": "John Mbadi"}], speaker_shot=[2, 2])
            html = render.build_html(render.make_env(), p, motion=True)
        block = re.search(r"@keyframes vis3 \{(.*?)\n\}", html, re.S).group(1)
        lines = [re.findall(r"opacity: (\d)", ln) for ln in block.strip().splitlines() if "opacity" in ln]
        self.assertEqual([x[0] for x in lines], ["0", "0", "1", "0"])   # the speaker's picture: their line only


class TheClipOfThemSayingIt(unittest.TestCase):
    SEGS = [{"start": 0.0, "end": 4.0, "text": "Good evening, here is the news."},
            {"start": 4.0, "end": 11.5, "text": "The Treasury appeared before senators today on the budget."},
            {"start": 12.0, "end": 16.0, "text": "We will not raise taxes on fuel this year, he said."},
            {"start": 16.0, "end": 22.0, "text": "Motorists have welcomed the news."}]

    def test_the_window_starts_where_they_say_it(self):
        self.assertEqual(pl.quote_moment(self.SEGS, "We will not raise taxes on fuel this year", 30.0), (12.0, 20.0))

    def test_a_clip_without_their_words_is_not_them_saying_it(self):
        self.assertIsNone(pl.quote_moment(self.SEGS, "Kenya will host the 2027 AFCON final in Nairobi", 30.0))
        self.assertIsNone(pl.quote_moment(self.SEGS, "Yes we can", 30.0))   # too short to tell


if __name__ == "__main__":
    unittest.main()
