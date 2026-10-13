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
        old = dict(POST, publish_at="2026-12-01T18:30:00+03:00")
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


if __name__ == "__main__":
    unittest.main()
