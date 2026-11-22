"""
searching.py — "What Kenya is searching": a daily Instagram Story of Google's top trending searches in Kenya, each
with the news headline behind it. The feed and its safety filter are trends.py's (Google Trends' public RSS, no key;
no tragedy, crime or banned topic).

The Story shows what people are looking for and why, in our design, at night when people scroll. A trend with no
news behind it is left out (a search alone says nothing), and so is one whose headline carries an allegation (no name
beside an accusation).
"""
from __future__ import annotations

import datetime as dt
import re

TOP = 5
SERIES = "What Kenya is searching"
# Searches for a way to watch or download (a TV stream, an app) are not news, and a stream may be a pirate one
NAVIGATION = re.compile(r"\b(live ?stream(ing)?|watch (live|online)|stream(ing)? (free|online)|apk|free download)\b", re.I)


def traffic(label: str) -> int:
    """'50K+' / '50,000+' / '2k+' -> 50000 / 50000 / 2000 (0 when unreadable)."""
    m = re.match(r"\s*([\d,.]+)\s*([kKmM]?)", str(label or ""))
    if not m:
        return 0
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0
    return int(n * {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1))


def pick(items: list[dict], n: int = TOP) -> list[dict]:
    """The biggest trends that can go on the Story: safe (trends.is_safe), with a news headline behind them, no
    allegation in it. Each: {"query", "label", "title", "source", "url"}."""
    import guard
    import trends
    out, seen = [], set()
    for t in sorted(items, key=lambda x: -traffic(x.get("traffic", ""))):
        ok, _ = trends.is_safe(t)
        news = [x for x in t.get("news") or [] if x.get("title") and x.get("url")]
        if not ok or not t.get("title") or not news or NAVIGATION.search(t["title"]):
            continue
        head = news[0]
        if guard.CRIME_WORDS.search(f"{t['title']} {head['title']}") or head["url"] in seen:
            continue   # an allegation, or the same story as a bigger search already on the list
        seen.add(head["url"])
        out.append({"query": t["title"], "label": short(traffic(t.get("traffic", ""))), "title": head["title"][:110],
                    "source": head.get("source") or "", "url": head["url"]})
        if len(out) == n:
            break
    return out


def short(n: int) -> str:
    """10000 -> '10K+', 2500000 -> '2.5M+'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M+"
    if n >= 1_000:
        return f"{n // 1_000}K+"
    return f"{n}+" if n else ""


def post_for(rows: list[dict], label: str, at: dt.datetime, publish_at: dt.datetime) -> dict:
    """The Story post: searching.html.j2 at Story size, published as an Instagram Story (no caption)."""
    return {"id": f"{label.lower()}-searching-{at:%m%d}", "template": "searching", "size": "story", "hand": True,
            "searching": True, "bg": "usiku", "kicker": SERIES, "day": f"{at:%A} {at.day} {at:%B}",
            "rows": rows, "source": "Google Trends, Kenya (trends.google.com/trending?geo=KE)",
            "source_links": [{"outlet": r["source"], "link": r["url"], "title": r["title"]} for r in rows],
            "publish_at": publish_at.isoformat(), "status": "drafted", "drafted_at": at.isoformat(timespec="seconds")}
