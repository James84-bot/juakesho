"""A photo the person in the story posted themselves (22 Nov: "if the headline is about Bien use Bien's image")."""
import datetime as dt
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import picture  # noqa: E402
import socialpics  # noqa: E402


def wikidata(url):
    if "list=search" in url:
        return {"query": {"search": [{"title": "Q1"}, {"title": "Q2"}]}}
    if "wbsearchentities" in url:
        return {"search": [{"id": "Q1"}, {"id": "Q2"}]}
    return {"entities": {
        "Q1": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q482994"}}}}]},   # an album
               "labels": {"en": {"value": "Alusa Continua"}}},
        "Q2": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
                          "P2003": [{"mainsnak": {"datavalue": {"value": "bien_test"}}}]},
               "labels": {"en": {"value": "Bien-Aimé Baraza"}}}}}


def photo(seed):
    import random
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    im = Image.new("RGB", (1200, 900), (rnd.randrange(256), 90, 40))
    d = ImageDraw.Draw(im)
    for _ in range(80):
        x, y = rnd.randrange(1200), rnd.randrange(900)
        d.ellipse((x, y, x + rnd.randrange(8, 300), y + rnd.randrange(8, 300)), fill=tuple(rnd.randrange(256) for _ in range(3)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


class TheirOwnPhoto(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"META_IG_USER_ID": "17", "META_ACCESS_TOKEN": "t"})
        p.start()
        self.addCleanup(p.stop)

    def test_the_username_comes_from_wikidata_for_a_person_only(self):
        self.assertEqual(socialpics.instagram_username("Bien Aime Baraza", wikidata), "bien_test")
        self.assertIsNone(socialpics.instagram_username("Nobody Here", lambda u: {"search": [], "query": {"search": []}}))

    def test_a_recent_plain_photo_that_fits_is_used_cover_art_and_old_posts_are_not(self):
        now = dt.datetime.now(dt.timezone.utc)
        media = [{"media_type": "VIDEO", "media_url": "v", "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S+0000")},
                 {"media_type": "IMAGE", "media_url": "cover", "permalink": "https://ig/p/1",
                  "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S+0000")},
                 {"media_type": "IMAGE", "media_url": "studio", "permalink": "https://ig/p/2",
                  "timestamp": (now - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S+0000")},
                 {"media_type": "IMAGE", "media_url": "old", "permalink": "https://ig/p/3",
                  "timestamp": (now - dt.timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%S+0000")}]
        asked = {}

        def graph(path, fields):
            asked.update(fields)
            return {"business_discovery": {"media": {"data": media}}}
        pics = {"cover": photo(1), "studio": photo(2), "old": photo(3)}
        with mock.patch.object(picture, "outlet_edit", lambda d: "album cover art" if d == pics["cover"] else ""), \
                mock.patch.object(picture, "fits", lambda d, about: ""):
            got = socialpics.their_photo({"id": "p"}, ["Bien Aime Baraza"], "Bien dropped his album", pics.__getitem__,
                                         graph_get=graph, get=wikidata)
        self.assertEqual(got[1], {"credit": "Photo: @bien_test on Instagram", "url": "https://ig/p/2", "kind": "file"})
        self.assertIn("business_discovery.username(bien_test)", asked["fields"])

    def test_the_username_from_the_reports_must_carry_their_name(self):
        pages = ['<a href="https://www.instagram.com/kbcchannel1/">KBC</a> <blockquote data-instgrm-permalink='
                 '"https://www.instagram.com/p/DAbc123/">A post shared by Bien (@bienaimesol)</blockquote>',
                 '<a href="https://instagram.com/bienaimesol">', '<a href="https://www.instagram.com/reel/XYZ/">']
        self.assertEqual(socialpics.handle_in_pages(pages, "Bien Aime Baraza"), "bienaimesol")
        self.assertIsNone(socialpics.handle_in_pages(pages[:1][:0] + ['instagram.com/kbcchannel1'], "Bien Aime Baraza"))

    def test_the_username_can_come_from_their_youtube_channel(self):
        def yt(url):
            if "search?" in url:
                return {"items": [{"snippet": {"channelId": "UC1", "channelTitle": "Bien"}},
                                  {"snippet": {"channelId": "UC2", "channelTitle": "Some Fan Page"}}]}
            self.assertIn("id=UC1", url)
            return {"items": [{"snippet": {"description": "Official. IG: instagram.com/bien_test"}}]}
        with mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": "k"}):
            self.assertEqual(socialpics.handle_from_youtube("Bien Aime Baraza", "bien", yt), "bien_test")

    def test_nothing_is_used_when_the_account_cannot_be_read(self):
        def graph(path, fields):
            raise RuntimeError("(#10) Not enough permission")
        self.assertIsNone(socialpics.their_photo({"id": "p"}, ["Bien Aime Baraza"], "s", lambda u: b"",
                                                 graph_get=graph, get=wikidata))


if __name__ == "__main__":
    unittest.main()
