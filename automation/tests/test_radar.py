"""Trend radar parsing (no network)."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import radar  # noqa: E402

PAGE = """<div class="trend-card"><h3 class="title" data-timestamp="1">1 hour ago</h3>
<ol class="trend-card__list"><li><span class="trend-name"><a href="https://twitter.com/search?q=%23RutoMustGo" class="trend-link">#RutoMustGo</a>
<span class="tweet-count" data-count="45000">45K</span></span></li>
<li><span class="trend-name"><a href="x" class="trend-link">Mp Naisula Lesuuda</a></span></li>
<li><span class="trend-name"><a href="x" class="trend-link">Kenya &amp; Nigeria</a></span></li></ol></div>
<div class="trend-card"><ol class="trend-card__list"><li><a class="trend-link">#OldTrend</a></li></ol></div>"""

FEED = b"""<?xml version="1.0"?><feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
<entry><yt:videoId>abc</yt:videoId><title>Police teargas protesters in CBD</title><published>2026-10-12T08:00:00+00:00</published>
<media:group><media:community><media:statistics views="40000"/></media:community></media:group></entry>
<entry><yt:videoId>old</yt:videoId><title>Old clip</title><published>2026-10-01T08:00:00+00:00</published>
<media:group><media:community><media:statistics views="900000"/></media:community></media:group></entry></feed>"""


class Radar(unittest.TestCase):
    def test_newest_x_card_only(self):
        got = radar.parse_trends24(PAGE)
        self.assertEqual([t["name"] for t in got], ["#RutoMustGo", "Mp Naisula Lesuuda", "Kenya & Nigeria"])
        self.assertEqual(got[0]["tweets"], "45000")

    def test_youtube_views_per_hour(self):
        now = dt.datetime(2026, 10, 12, 12, tzinfo=dt.timezone.utc)
        vids = radar.parse_youtube(FEED, "Citizen TV", now)
        self.assertEqual(vids[0]["per_hour"], 10000)
        self.assertEqual(vids[0]["url"], "https://www.youtube.com/watch?v=abc")


if __name__ == "__main__":
    unittest.main()
