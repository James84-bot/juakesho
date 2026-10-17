"""posted.py: finding the photo already posted of the day's story (no network)."""
import datetime as dt
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import posted  # noqa: E402

FEED = b"""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item><title>Cherargei renews push to extend presidential term to seven years</title><link>https://k.test/a</link>
<pubDate>Mon, 12 Oct 2026 09:00:00 +0300</pubDate><description>Nandi Senator Samson Cherargei...</description>
<media:content url="https://k.test/cherargei.jpg" medium="image"><media:credit>Photo | Kenyans.co.ke / Jane Wanjiru</media:credit></media:content></item>
<item><title>Ruto opens road in Kisumu</title><link>https://k.test/b</link><pubDate>Mon, 12 Oct 2026 09:00:00 +0300</pubDate>
<enclosure url="https://k.test/road.jpg" type="image/jpeg"/></item>
<item><title>Cherargei term limits bill: what senators said</title><link>https://k.test/c</link>
<pubDate>Mon, 12 Oct 2026 08:00:00 +0300</pubDate><media:content url="https://k.test/afp.jpg" medium="image"><media:credit>AFP</media:credit></media:content></item>
</channel></rss>"""
POST = {"id": "p", "template": "promise", "who": "Senator Samson Cherargei", "event_query": "Cherargei term limits Senate",
        "publish_at": "2026-10-14T18:30:00+03:00"}


def jpeg(w=1600, h=900):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), "gray").save(b, "JPEG")
    return b.getvalue()


class Posted(unittest.TestCase):
    def setUp(self):
        self.items = posted.parse_feed(FEED, "Kenyans.co.ke")

    def test_feed_items_carry_their_image_and_credit(self):
        self.assertEqual(self.items[0]["img"], "https://k.test/cherargei.jpg")
        self.assertIn("Jane Wanjiru", self.items[0]["credit"])
        self.assertEqual(self.items[1]["img"], "https://k.test/road.jpg")

    def test_report_must_name_the_person(self):
        s, w = posted.terms_for(POST)
        self.assertEqual(s, "cherargei")
        self.assertGreater(posted.score(self.items[0], s, w), 0)
        self.assertEqual(posted.score(self.items[1], s, w), 0)

    def test_a_leader_in_another_story_is_not_a_match(self):
        post = {"who": "President William Ruto", "message": "Over 100,000 comrades graduate annually into unpaid work "
                "despite a promise of guaranteed paid internships."}
        other = {"title": "Ruto mocks 'Shakahola Hospital', promises to fix Trans Nzoia health crisis", "text": ""}
        s, w = posted.terms_for(post)
        self.assertEqual(posted.score(other, s, w), 0)

    def test_picks_the_credited_photo_and_skips_agency_ones(self):
        got_urls = []

        def get(url, timeout=20):
            got_urls.append(url)
            return jpeg()
        with mock.patch.object(posted, "feed_items", lambda: self.items), mock.patch.object(posted, "_get", get):
            data, meta = posted.find(POST)
        self.assertEqual(meta["kind"], "posted")
        self.assertEqual(meta["credit"], "Photo: Kenyans.co.ke / Jane Wanjiru")
        self.assertNotIn("https://k.test/afp.jpg", got_urls)

    def test_old_reports_and_small_images_are_not_used(self):
        old = dict(POST, publish_at="2026-09-01T18:30:00+03:00")   # a post from September: October reports are too new
        with mock.patch.object(posted, "feed_items", lambda: self.items), mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg()):
            self.assertIsNone(posted.find(old))
        with mock.patch.object(posted, "feed_items", lambda: self.items[:1]), \
                mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg(400, 300)):
            self.assertIsNone(posted.find(POST))

    def test_article_page_supplies_og_image_when_feed_has_none(self):
        item = dict(self.items[0], img="", credit="")
        page = b'<html><meta property="og:image" content="/img/lead.jpg"><figure><figcaption>PHOTO | Nation / John Doe</figcaption></figure></html>'
        with mock.patch.object(posted, "feed_items", lambda: [item]), \
                mock.patch.object(posted, "_get", lambda u, timeout=20: page if u == "https://k.test/a" else jpeg()):
            data, meta = posted.find(POST)
        self.assertEqual(meta["credit"], "Photo: Kenyans.co.ke / John Doe")


    def test_archive_keeps_reports_after_they_leave_the_live_feed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, mock.patch.object(posted, "ARCHIVE", Path(d) / "a.json"):
            now = dt.datetime.now(dt.timezone.utc)
            fresh = [dict(self.items[0], when=now - dt.timedelta(days=2)), dict(self.items[1], when=now - dt.timedelta(days=9))]
            posted._FEED_CACHE.clear()
            with mock.patch.object(posted, "_live_items", lambda: fresh):
                self.assertEqual(posted.collect(), 2)
            posted._FEED_CACHE.clear()
            with mock.patch.object(posted, "_live_items", lambda: []):
                self.assertEqual(posted.collect(), 0)
                links = [r["link"] for r in posted.feed_items()]
            self.assertEqual(links, ["https://k.test/a"])   # the 9-day-old report aged out
            posted._FEED_CACHE.clear()

    def test_full_size_article_photo_beats_the_feed_thumbnail(self):
        item = dict(self.items[0], img="https://k.test/thumb.jpg")
        page = b'<html><meta property="og:image" content="https://k.test/full.jpg"></html>'

        def get(u, timeout=20):
            return {"https://k.test/a": page, "https://k.test/thumb.jpg": jpeg(300, 200)}.get(u, jpeg())
        with mock.patch.object(posted, "feed_items", lambda: [item]), mock.patch.object(posted, "_get", get):
            data, meta = posted.find(POST)
        self.assertEqual(len(data), len(jpeg()))
        # and the thumbnail is still the fallback when the page can't be read
        def get2(u, timeout=20):
            if u == "https://k.test/a":
                raise OSError("down")
            return jpeg()
        with mock.patch.object(posted, "feed_items", lambda: [item]), mock.patch.object(posted, "_get", get2):
            self.assertIsNotNone(posted.find(POST))


class Matching(unittest.TestCase):
    """Real cases from October 2026 that the old matcher got wrong."""

    def test_names_are_distinctive_words_not_titles_or_sentence_starts(self):
        post = {"who": "Energy CS Opiyo Wandayi", "message": "Kenya Power cuts tokens over Sh50 while IEBC waits.",
                "fact": "The State Department for Housing and Urban Development stalled Masinde Muliro market."}
        names = posted.names_for(post)
        for w in ("wandayi", "iebc", "masinde", "muliro"):
            self.assertIn(w, names)
        for w in ("c", "cs", "power", "kenya", "development", "state", "the"):
            self.assertNotIn(w, names)

    def test_an_institution_is_not_a_surname(self):
        import photos
        self.assertEqual(photos._surname("State Department for Housing and Urban Development"), "")
        self.assertEqual(photos._surname("Kenya Power Management"), "")
        self.assertEqual(photos._surname("Energy CS Opiyo Wandayi"), "wandayi")
        self.assertEqual(photos.full_name("Energy CS Opiyo Wandayi"), "Opiyo Wandayi")
        self.assertEqual(photos.full_name("Kenya Revenue Authority"), "")
        self.assertEqual(photos._surname("Political Leaders in Bungoma"), "")   # live check, 17 Oct

    def test_a_foreign_story_sharing_common_words_is_not_a_match(self):
        post = {"template": "glasspoll", "message": "Should Kenya Power demand upfront electricity payment while it "
                "chases public debts?"}
        kyiv = {"title": "Russian strikes hit key power plant in Kyiv, Zelensky says", "text": "electricity supply cut while"}
        s, w = posted.terms_for(post)
        self.assertEqual(posted.score(kyiv, s, w, posted.names_for(post)), 0)

    def test_a_shared_acronym_finds_the_same_story(self):
        post = {"who": "Kenya Revenue Authority", "message": "KRA uncovered a Sh4 billion VAT fraud using fake invoices."}
        report = {"title": "Sh3.9bn VAT fraud: Court issues arrest warrants for missing suspects", "text": ""}
        s, w = posted.terms_for(post)
        self.assertGreater(posted.score(report, s, w, posted.names_for(post), posted.acronyms_for(post)), 0)

    def test_a_shared_place_name_alone_is_not_the_same_story(self):
        post = {"who": "State Department for Housing and Urban Development", "where": "Trans Nzoia",
                "promise": "Complete the modern Masinde Muliro commercial market in Kitale town",
                "message": "Masinde Muliro Market in Kitale remains stalled after years of promises, leaving 4,000 traders stranded."}
        report = {"title": "Ruto turns Trans Nzoia tour into campaign to unseat Natembeya", "text": "market"}
        s, w = posted.terms_for(post)
        self.assertEqual(posted.score(report, s, w, posted.names_for(post), posted.acronyms_for(post)), 0)


class FilePhoto(unittest.TestCase):
    NOW = dt.datetime.now(dt.timezone.utc)

    def item(self, title, link, days=1):
        return {"title": title, "link": link, "when": self.NOW - dt.timedelta(days=days), "img": link + ".jpg",
                "credit": "", "text": "", "outlet": "Capital FM", "official": False}

    def test_newest_report_naming_the_person_gives_a_labelled_file_photo(self):
        items = [self.item("CS Ruku revokes payroll access for 84 HR officers", "https://k.test/ruku", 2),
                 self.item("Ruku meets unions", "https://k.test/ruku2", 1)]
        post = {"id": "p", "who": "Public Service CS Geoffrey Ruku", "message": "Civil servants wait for promotions."}
        with mock.patch.object(posted, "feed_items", lambda: items), mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg()):
            data, meta = posted.find_named(post)
        self.assertEqual(meta["kind"], "file")
        self.assertEqual(meta["url"], "https://k.test/ruku2")   # the newest
        self.assertTrue(meta["credit"].startswith("File photo: Capital FM"))

    def test_never_by_place_and_never_from_an_old_report(self):
        post = {"id": "p", "who": "Ministry of Sports", "message": "Kamariny stadium in Iten is still unfinished."}
        items = [self.item("Kipruto from Iten wins Chicago marathon", "https://k.test/iten")]
        with mock.patch.object(posted, "feed_items", lambda: items), mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg()):
            self.assertIsNone(posted.find_named(post))
        post = {"id": "p", "who": "IEBC", "message": "IEBC targets 6.3 million new voters."}
        items = [self.item("IEBC chair speaks", "https://k.test/old", days=30)]
        with mock.patch.object(posted, "feed_items", lambda: items), mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg()):
            self.assertIsNone(posted.find_named(post))
        items = [self.item("IEBC chair speaks", "https://k.test/new", days=2)]
        with mock.patch.object(posted, "feed_items", lambda: items), mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg()):
            self.assertEqual(posted.find_named(post)[1]["url"], "https://k.test/new")

    def test_same_surname_different_person_is_not_a_file_photo(self):
        # live check, 17 Oct 2026: Hassan Omar (UDA) got a photo of Ilhan Omar (US Congress)
        post = {"id": "p", "who": "Hassan Omar, UDA Secretary-General", "message": "IEBC says dead voters cannot vote."}
        items = [self.item("Federal raid on Ilhan Omar's home signals threat to her US citizenship", "https://k.test/ilhan", 1),
                 self.item("IEBC summons Hassan Omar over deceased voters remarks", "https://k.test/hassan", 3)]
        with mock.patch.object(posted, "feed_items", lambda: items), mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg()):
            self.assertEqual(posted.find_named(post)[1]["url"], "https://k.test/hassan")

    def test_a_tax_is_not_an_institution(self):
        # live check: a VAT-fraud post got a photo of a fuel-VAT story
        post = {"id": "p", "who": "Kenya Revenue Authority", "message": "KRA uncovered Sh4bn in fake VAT invoices."}
        items = [self.item("Ruto signs fuel VAT extension", "https://k.test/fuel", 1)]
        with mock.patch.object(posted, "feed_items", lambda: items), mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg()):
            self.assertIsNone(posted.find_named(post))
        items.append(self.item("KRA boss speaks on revenue targets", "https://k.test/kra", 2))
        with mock.patch.object(posted, "feed_items", lambda: items), mock.patch.object(posted, "_get", lambda u, timeout=20: jpeg()):
            self.assertEqual(posted.find_named(post)[1]["url"], "https://k.test/kra")

    def test_full_size_originals_are_tried_first(self):
        self.assertEqual(posted._originals("https://www.kenyans.co.ke/files/styles/article_style/public/images/media/a.jpg")[0],
                         "https://www.kenyans.co.ke/files/images/media/a.jpg")
        self.assertEqual(posted._originals("https://capitalfm.africa/wp-content/uploads/2026/10/x-1024x683.jpeg")[0],
                         "https://capitalfm.africa/wp-content/uploads/2026/10/x.jpeg")
        self.assertEqual(posted._originals("https://k.test/plain.jpg"), ["https://k.test/plain.jpg"])


class Colour(unittest.TestCase):
    def test_archive_black_and_white_photos_are_not_a_place_today(self):
        import photos
        from PIL import Image
        def img(colour):
            b = io.BytesIO()
            Image.new("RGB", (400, 300), colour).save(b, "JPEG")
            return b.getvalue()
        self.assertFalse(photos.in_colour(img((128, 128, 128))))
        self.assertTrue(photos.in_colour(img((40, 120, 60))))


class Band(unittest.TestCase):
    def test_small_news_photos_are_shown_as_a_sharp_band(self):
        import tempfile
        import render
        with tempfile.TemporaryDirectory() as d:
            small, big = Path(d) / "s.jpg", Path(d) / "b.jpg"
            small.write_bytes(jpeg(800, 535))
            big.write_bytes(jpeg(1600, 1067))
            self.assertEqual(render.photo_band(small, 1080), 722)   # 800px wide: blown up 2-4x if it filled the frame
            self.assertEqual(render.photo_band(big, 1080), 0)


if __name__ == "__main__":
    unittest.main()
