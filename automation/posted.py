"""
posted.py — finds the photo already posted of the day's story, so a post shows the real moment.

Reads Kenyan news feeds and the government's own news agency (content/photo_feeds.json), finds the reports
of the post's story from the days around it, and takes the lead photo of the best match (RSS media, or the
article's og:image). Used under fair dealing for news and commentary, which requires a credit: the outlet
(and photographer, when the report names one) goes on the design and in the caption.

Never used: photos credited to agencies and stock libraries (Getty, AFP, Reuters, AP...), which sell their
photos and bill for reuse; small or missing images; reports that don't name the post's person or subject.

    python posted.py "Cherargei term limits"     # what it would pick, from today's feeds
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
FEEDS = HERE / "content" / "photo_feeds.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MIN_WIDTH = 900
DAYS_BEFORE, DAYS_AFTER = 4, 1
PAID = re.compile(r"\b(getty|afp|reuters|associated press|ap photo|shutterstock|alamy|xinhua|anadolu|epa-efe|"
                  r"istock|adobe ?stock|dreamstime|bloomberg)\b", re.I)
STOP = set("""a an the and or of in on at to for from by with as is are was were be been this that these those
it its into over after before about against amid says said new more most than then they them their his her he she
we our you your who what when where why how not no will would could should may might has have had do does did
kenya kenyan kenyans nairobi county national government week today year years""".split())
NS = {"media": "http://search.yahoo.com/mrss/", "content": "http://purl.org/rss/1.0/modules/content/"}
_FEED_CACHE: dict[str, list[dict]] = {}


def _note(msg: str) -> None:
    """Into the photo log (state/photos.log) with every other photo decision."""
    import photos
    photos._note(msg)


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-KE,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(8_000_000)


def _when(text: str | None) -> dt.datetime | None:
    try:
        d = email.utils.parsedate_to_datetime(text or "")
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _img_from_html(fragment: str) -> str:
    m = re.search(r"""<img[^>]+src=["']([^"']+)""", fragment or "", re.I)
    return html.unescape(m.group(1)) if m else ""


def parse_feed(xml: bytes, name: str, official: bool = False) -> list[dict]:
    """Items with title, link, date, the image the feed itself carries (if any) and its credit text."""
    out = []
    text = xml.decode("utf-8", "replace")
    text = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)(\w+);",
                  lambda m: html.unescape(f"&{m.group(1)};").replace("&", "&amp;").replace("<", "&lt;"), text)
    root = ET.fromstring(text.encode("utf-8"))
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        desc = it.findtext("description") or ""
        body = it.findtext("content:encoded", namespaces=NS) or ""
        img, credit = "", ""
        for tag in ("media:content", "media:thumbnail"):
            el = it.find(tag, NS)
            if el is not None and el.get("url") and (el.get("medium") in (None, "image") or tag == "media:thumbnail"):
                img = img or el.get("url")
                credit = credit or (el.findtext("media:credit", namespaces=NS) or "")
        enc = it.find("enclosure")
        if not img and enc is not None and str(enc.get("type", "")).startswith("image/"):
            img = enc.get("url", "")
        img = img or _img_from_html(body) or _img_from_html(desc)
        text = re.sub(r"<[^>]+>", " ", html.unescape(desc))[:300]
        out.append({"title": title, "link": link, "when": _when(it.findtext("pubDate")), "img": img,
                    "credit": credit.strip(), "text": text, "outlet": name, "official": official})
    return out


ARCHIVE = HERE / "state" / "feed_photos.json"
KEEP = dt.timedelta(days=6)


def _load_archive() -> list[dict]:
    try:
        rows = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    for r in rows:
        r["when"] = dt.datetime.fromisoformat(r["when"]) if r.get("when") else None
    return rows


def collect() -> int:
    """Reads every feed and adds new reports to a rolling 6-day archive (state/feed_photos.json), so a story
    from three days ago is still findable after it has scrolled off the live feeds. Run on every tick."""
    now = dt.datetime.now(dt.timezone.utc)
    rows = {r["link"]: r for r in _load_archive() if r["when"] is None or now - r["when"] <= KEEP}
    before = len(rows)
    for item in _live_items():
        rows.setdefault(item["link"], item)
    keep = sorted(rows.values(), key=lambda r: r["when"] or now, reverse=True)[:800]
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.write_text(json.dumps([{**r, "when": r["when"].isoformat() if r["when"] else ""} for r in keep],
                                  ensure_ascii=False), encoding="utf-8")
    _FEED_CACHE.pop("all", None)
    return len(rows) - before


def _live_items() -> list[dict]:
    if "live" in _FEED_CACHE:
        return _FEED_CACHE["live"]
    items = []
    for f in json.loads(FEEDS.read_text(encoding="utf-8"))["feeds"]:
        try:
            got = parse_feed(_get(f["url"]), f["name"], bool(f.get("official")))
            items += got
            _note(f"  feed {f['name']}: {len(got)} items, {sum(1 for x in got if x['img'])} with an image")
        except Exception as e:
            _note(f"  feed {f['name']} failed: {str(e)[:100]}")
    _FEED_CACHE["live"] = items
    return items


def feed_items() -> list[dict]:
    """Live feed items plus the 6-day archive, one per link (cached for the run)."""
    if "all" not in _FEED_CACHE:
        rows = {r["link"]: r for r in _load_archive()}
        for item in _live_items():
            rows[item["link"]] = item
        _FEED_CACHE["all"] = list(rows.values())
    return _FEED_CACHE["all"]


def terms_for(post: dict) -> tuple[str, list[str]]:
    """(surname of the post's person, the subject words) to match reports against."""
    import photos
    surname = photos._surname(str(post.get("who", "")))
    source = post.get("event_query") or " ".join(str(post.get(k, "")) for k in ("message", "headline", "title"))
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{3,}", source)]
    words = [w for w in dict.fromkeys(words) if w not in STOP and w != surname]
    return surname, words[:8]


def score(item: dict, surname: str, words: list[str]) -> int:
    """How surely this report is about the post's story. 0 = not about it.
    With a person: the report names them AND shares a subject word. Without: three subject words."""
    hay = f"{item['title']} {item['text']}".lower()
    hits = sum(1 for w in words if w[:6] in hay)
    if surname:
        return hits + 3 if surname in hay and hits >= 1 else 0
    return hits if hits >= 3 else 0


def _og_image(page: str) -> tuple[str, str]:
    """(image url, credit text near it) from an article page."""
    img = ""
    for prop in ("og:image", "twitter:image", "og:image:url"):
        m = (re.search(rf"""<meta[^>]+(?:property|name)=["']{prop}["'][^>]+content=["']([^"']+)""", page, re.I) or
             re.search(rf"""<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']{prop}["']""", page, re.I))
        if m:
            img = html.unescape(m.group(1))
            break
    cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", page, re.I | re.S)
    credit = re.sub(r"<[^>]+>", " ", cap.group(1)) if cap else ""
    m = re.search(r"(?:photo|image|picture)\s*[:|/]\s*([^<\n]{2,80})", re.sub(r"<[^>]+>", " ", page[:400_000]), re.I)
    return img, " ".join(f"{credit} {m.group(1) if m else ''}".split())[:200]


def _photographer(credit: str) -> str:
    """'PHOTO | Nation / John Doe' -> 'John Doe'. Empty when the credit names no person."""
    m = re.search(r"(?:photo|image|picture)s?\s*[:|/-]\s*(.+)", credit or "", re.I)
    parts = [p.strip(" .") for p in re.split(r"[|/,]", m.group(1) if m else credit or "") if p.strip(" .")]
    for p in reversed(parts):
        if re.search(r"\b(courtesy|file|screengrab|screenshot|handout|\.co|\.ke|\.com|media|digital|news|tv)\b", p, re.I):
            continue
        if re.fullmatch(r"[A-Z][a-z'.-]+(?: [A-Z][a-z'.-]+){1,3}", p):
            return p
    return ""


def _check_image(data: bytes) -> bool:
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
        return w >= MIN_WIDTH and 0.45 <= h / w <= 1.6     # not a banner, a logo strip or a thumbnail
    except Exception:
        return False


def find(post: dict) -> tuple[bytes, dict] | None:
    """The lead photo of the best report of this post's story, with its credit. None if nothing fits."""
    surname, words = terms_for(post)
    if not surname and len(words) < 2:
        return None
    try:
        day = dt.datetime.fromisoformat(post["publish_at"]).astimezone(dt.timezone.utc)
    except (KeyError, ValueError):
        day = dt.datetime.now(dt.timezone.utc)
    start, end = day - dt.timedelta(days=DAYS_BEFORE), day + dt.timedelta(days=DAYS_AFTER)
    ranked = sorted(((score(x, surname, words), x) for x in feed_items()
                     if x["when"] is None or start <= x["when"] <= end), key=lambda t: (-t[0], not t[1]["official"]))
    ranked = [(s, x) for s, x in ranked if s > 0][:5]
    _note(f"  posted for {post.get('id')}: {len(ranked)} matching reports (person '{surname}', words {words[:5]})")
    for s, item in ranked:
        img, credit = item["img"], item["credit"]
        try:
            if not img or not credit:
                page_img, page_credit = _og_image(_get(item["link"]).decode("utf-8", "replace"))
                img, credit = img or page_img, credit or page_credit
            if not img:
                continue
            img = urllib.parse.urljoin(item["link"], img)
            if PAID.search(f"{credit} {img}"):
                _note(f"    skipped {item['outlet']}: agency photo ({credit[:60] or img[:60]})")
                continue
            data = _get(img)
            if not _check_image(data):
                _note(f"    skipped {item['outlet']}: image too small or not a photo")
                continue
        except Exception as e:
            _note(f"    skipped {item['outlet']}: {str(e)[:80]}")
            continue
        who = _photographer(credit)
        line = f"Photo: {item['outlet']}" + (f" / {who}" if who and who.lower() not in item["outlet"].lower() else "")
        _note(f"    picked {item['outlet']} ({s}): {item['title'][:70]}")
        return data, {"credit": line, "url": item["link"], "kind": "posted", "outlet": item["outlet"]}
    return None


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Ruto State House"
    got = find({"id": "cli", "event_query": q, "who": q, "publish_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    print(got[1] if got else "nothing found")
