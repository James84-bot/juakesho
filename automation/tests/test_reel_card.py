"""News photos in a Reel: the same picture never twice, soft pictures left out, landscape photos whole and sharp in
a card (never blown up to fill 9:16), each picture on the line its report is about, one red block per marker."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
import picture  # noqa: E402
import render  # noqa: E402
import video  # noqa: E402
from test_posted import _photo, _resaved  # noqa: E402


class Picture(unittest.TestCase):
    def test_sharp_and_soft_pictures_are_told_apart(self):
        from PIL import Image, ImageFilter
        sharp = _photo(7)
        self.assertGreater(picture.detail(sharp), picture.SOFT_BELOW)
        self.assertLess(picture.detail(_photo(7, soft=True)), picture.SOFT_BELOW)      # blown up 3x
        out = io.BytesIO()
        Image.open(io.BytesIO(sharp)).filter(ImageFilter.GaussianBlur(2)).save(out, "JPEG", quality=85)
        self.assertLess(picture.detail(out.getvalue()), picture.SOFT_BELOW)            # out of focus
        self.assertEqual(picture.detail(b"not an image"), 0.0)

    def test_the_same_picture_resized_is_the_same_another_is_not(self):
        a = picture.dhash(_photo(1))
        self.assertTrue(picture.near_same(a, picture.dhash(_resaved(_photo(1)))))
        self.assertFalse(picture.near_same(a, picture.dhash(_photo(2))))
        self.assertIsNone(picture.dhash(b"x"))
        self.assertFalse(picture.near_same(None, a))


class Layout(unittest.TestCase):
    def test_only_a_picture_that_can_fill_9_16_sharply_fills_it(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            land, tall = Path(d) / "l.jpg", Path(d) / "t.jpg"
            Image.new("RGB", (1800, 1200)).save(land)
            Image.new("RGB", (1500, 2600)).save(tall)
            self.assertFalse(render.fills_frame(land, 1080, 1920))   # 1.6x to fill: soft
            self.assertTrue(render.fills_frame(tall, 1080, 1920))

    def test_a_small_picture_is_shown_whole_in_the_card_not_blown_up(self):
        from PIL import Image
        cw, ch = render.card_size(1080)
        self.assertEqual((cw, ch), (936, 702))
        with tempfile.TemporaryDirectory() as d:
            small, big = Path(d) / "s.jpg", Path(d) / "b.jpg"
            Image.new("RGB", (700, 350)).save(small)
            Image.new("RGB", (1366, 768)).save(big)
            self.assertIsNone(render.card_fit(big, cw, ch))           # fills the card at 0.9x
            fit = render.card_fit(small, cw, ch)                      # 2x to fill: shown whole at 1.34x
            self.assertEqual((fit["w"], fit["h"], fit["x"], fit["y"]), (936, 468, 0, 117))

    def test_landscape_news_photos_sit_in_the_card_with_their_own_credit(self):
        with tempfile.TemporaryDirectory() as d:
            files = []
            for k in range(3):
                f = Path(d) / f"p{k}.jpg"
                f.write_bytes(_photo(k + 1))
                files.append(str(f))
            post = {"id": "x", "template": "sauti", "bg": "usiku", "kicker": "Fans", "line": "l", "hot": True,
                    "beat": "sport", "photo_kind": "posted", "photo_file": files[0], "extra_photos": files[1:],
                    "photo_credit": "Photo: A · Photo: B",
                    "shot_info": [{"credit": "Photo: A", "title": "Mariga ousted in Meru"},
                                  {"credit": "Photo: B", "title": "Police teargas disrupts the FKF meeting in Meru"},
                                  {"credit": "Photo: C", "title": "Delegates vote at FKF meeting"}],
                    "beats": ["FKF ousted *McDonald Mariga* and six others.",
                              "Delegates spoke for hours at the hotel.",
                              "Police fired *teargas* before the FKF meeting began.",
                              "Tell us below: fair call, or a purge?"]}
            reel = video.beat_reel(post)
            self.assertEqual(reel["kicker"], "Sport")   # a news post says what it is
            html = render.build_html(render.make_env(), reel, motion=True)
        self.assertIn('class="card"', html)
        self.assertNotIn('class="blur"', html)
        for c in ("Photo: A", "Photo: B", "Photo: C"):
            self.assertIn(f'<span class="cr">{c}</span>', html)
        self.assertIn('class="t m j"', html)          # "McDonald" joins "Mariga" in one marker
        self.assertIn("@keyframes wipec", html)        # the wipe stays inside the card

    def test_each_picture_goes_on_the_line_its_report_is_about(self):
        beats = ["FKF ousted *McDonald Mariga* and six others.", "Delegates spoke for hours at the hotel.",
                 "Police fired *teargas* before the FKF meeting began.", "Tell us below: fair call, or a purge?"]
        titles = ["Mariga ousted", "Police teargas disrupts the FKF meeting in Meru", "Delegates vote at FKF meeting"]
        seq = render.match_shots(beats, titles)
        self.assertEqual(seq[0], 0)                    # the thumbnail line keeps the lead photo
        self.assertEqual(seq[2], 1)                    # the teargas picture on the teargas line
        self.assertEqual(set(seq), {0, 1, 2})          # every picture is shown
        self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])))   # never the same picture twice in a row
        self.assertEqual(render.match_shots(beats, ["only"]), [0, 0, 0, 0])
        self.assertEqual(render.match_shots(beats[:3], ["a", "b", "c", "d"]), [0, 1, 2])

    def test_marker_words_join(self):
        self.assertEqual(render.beat_marks("We pay *Sh4bn more* now"),
                         [("We", False, False), ("pay", False, False), ("Sh4bn", True, True), ("more", True, False),
                          ("now", False, False)])


if __name__ == "__main__":
    unittest.main()
