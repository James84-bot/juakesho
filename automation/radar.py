"""
radar.py — what Kenya is talking about RIGHT NOW, with no API keys or logins.

  X (Twitter) Kenya trends   trends24.in/kenya (public page, refreshed hourly): the live hashtags and names
  Trending Kenyan videos     the public YouTube RSS feeds of Kenyan TV channels (content/video_feeds.json),
                             newest uploads ranked by views per hour

The writer gets both as context (real hashtags for captions, real moments to react to). The owner gets a short
"Trend radar" on Telegram with links: react with our own Reel, or stitch/duet the clip inside the app, where the
platform licenses it. We never download and re-upload someone else's video.

    python radar.py            # fetch now and print
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
FEEDS = HERE / "content" / "video_feeds.json"
OUT = HERE / "state" / "radar.json"
TRENDS24 = "https://trends24.in/kenya/"
UA = "Mozilla/5.0 (JuaKesho trend radar; https://github.com/James84-bot/juakesho)"
SEARCH = re.compile(r"(?:twitter|x)\.com/search")
NS = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/",
      "yt": "http://www.youtube.com/xml/schemas/2015"}


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------
# X trends
# ---------------------------------------------------------------------------
def parse_trends24(page: str, limit: int = 30) -> list[dict]:
    """The newest hourly card on trends24: [{"name", "tweets"}], in rank order.
    The page lists several hourly cards, newest first; we read the first list only."""
    # the first ordered list whose links are X searches is the newest hourly card (site chrome has no such links)
    block = next((ol for ol in re.findall(r"<ol[^>]*>(.*?)</ol>", page, re.S) if SEARCH.search(ol)), "")
    out, seen = [], set()
    for li in re.findall(r"<li[^>]*>(.*?)</li>", block, re.S):
        a = re.search(r"<a[^>]*href=\"[^\"]*(?:twitter|x)\.com/search[^\"]*\"[^>]*>(.*?)</a>", li, re.S)
        if not a:
            continue
        name = html.unescape(re.sub(r"<[^>]+>", "", a.group(1))).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        tag = re.search(r"<[^>]*tweet-count[^>]*>([^<]*)<", li)
        num = re.search(r"data-count=\"(\d+)\"", tag.group(0)) if tag else None
        tweets = (num.group(1) if num else tag.group(1).strip()) if tag else ""
        out.append({"name": name, "tweets": tweets})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Kenyan TV on YouTube (public RSS, no key)
# ---------------------------------------------------------------------------
def parse_youtube(xml: bytes, channel: str, now: dt.datetime) -> list[dict]:
    root = ET.fromstring(xml)
    vids = []
    for e in root.findall("a:entry", NS):
        published = dt.datetime.fromisoformat(e.findtext("a:published", "", NS).replace("Z", "+00:00"))
        stats = e.find("media:group/media:community/media:statistics", NS)
        views = int(stats.get("views", 0)) if stats is not None else 0
        hours = max((now - published).total_seconds() / 3600, 1.0)
        vid = e.findtext("yt:videoId", "", NS)
        vids.append({"title": e.findtext("a:title", "", NS), "channel": channel, "views": views,
                     "published": published.isoformat(), "per_hour": round(views / hours),
                     "url": f"https://www.youtube.com/watch?v={vid}" if vid else "",
                     "short": f"https://youtube.com/shorts/{vid}" if vid else ""})
    return vids


def collect(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    data = {"fetched": now.isoformat(), "x": [], "videos": [], "errors": {}}
    try:
        page = _get(TRENDS24).decode("utf-8", "replace")
        data["x"] = parse_trends24(page)
        if not data["x"]:   # the page changed: keep a few links so the parser can be fixed
            data["errors"]["x"] = "no trends parsed; sample links: " + " | ".join(re.findall(r"<a[^>]*href=\"([^\"]+)\"", page)[10:30])
    except Exception as e:   # one source down never stops the run
        data["errors"]["x"] = str(e)[:160]
    feeds = json.loads(FEEDS.read_text(encoding="utf-8"))["channels"] if FEEDS.exists() else []
    vids = []
    for ch in feeds:
        try:
            vids += parse_youtube(_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"), ch["name"], now)
        except Exception as e:
            data["errors"][ch["name"]] = str(e)[:160]
    fresh = [v for v in vids if now - dt.datetime.fromisoformat(v["published"]) <= dt.timedelta(hours=36)]
    data["videos"] = sorted(fresh, key=lambda v: -v["per_hour"])[:15]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def _load(max_age_hours: int) -> dict | None:
    if not OUT.exists():
        return None
    data = json.loads(OUT.read_text(encoding="utf-8"))
    if dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(data["fetched"]) > dt.timedelta(hours=max_age_hours):
        return None
    return data


def hashtags(limit: int = 12) -> list[str]:
    """Live Kenyan X trends that are hashtags (for captions)."""
    data = _load(30) or {}
    return [t["name"] for t in data.get("x", []) if t["name"].startswith("#")][:limit]


def prompt_block() -> str:
    data = _load(30)
    if not data or not (data.get("x") or data.get("videos")):
        return ""
    lines = []
    if data.get("x"):
        lines.append("ON X KENYA THIS HOUR (trends24): " + ", ".join(
            f"{t['name']}{' (' + t['tweets'] + ')' if t['tweets'] else ''}" for t in data["x"][:20]))
    if data.get("videos"):
        lines.append("MOST-WATCHED KENYAN TV CLIPS (last 36 h, views per hour):")
        lines += [f"- {v['title']} [{v['channel']}, {v['views']:,} views] {v['url']}" for v in data["videos"][:8]]
    return ("\nLIVE RADAR\n" + "\n".join(lines) +
            "\nThese are what Kenyans are watching and typing this hour. Build hot posts on them. Use the exact live "
            "hashtags in captions (2-4, only ones that fit the post; never hijack a tragedy or a hashtag you don't "
            "understand). A clip is a source to react to: tell the moment in our own `beats` and put its link in "
            "`source`; never describe footage you haven't been given.\n")


def telegram_text(limit_x: int = 10, limit_v: int = 5) -> str | None:
    data = _load(6)
    if not data or not (data.get("x") or data.get("videos")):
        return None
    esc = html.escape
    parts = ["📡 <b>Trend radar</b> (Kenya, now)"]
    if data.get("x"):
        parts.append("<b>On X:</b> " + " · ".join(esc(t["name"]) for t in data["x"][:limit_x]))
    if data.get("videos"):
        parts.append("<b>Most-watched clips:</b>")
        parts += [f"• <a href=\"{esc(v['url'])}\">{esc(v['title'][:90])}</a> ({esc(v['channel'])}, {v['views']:,})"
                  for v in data["videos"][:limit_v]]
        parts.append("To react to a clip: <b>Remix / Stitch</b> it in Instagram or TikTok (licensed there), "
                     "or tell me and the next hot post becomes our own Reel on it.")
    return "\n".join(parts)


if __name__ == "__main__":
    d = collect()
    print(f"x: {len(d['x'])}, videos: {len(d['videos'])}, errors: {d['errors'] or 'none'}")
    for t in d["x"][:15]:
        print(f"  {t['name']} {t['tweets']}")
    for v in d["videos"][:8]:
        print(f"  [{v['channel']}] {v['title']} ({v['views']:,})")
