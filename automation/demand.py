"""
demand.py — "give Kenyans what they want": ranks this week's stories by how much Kenyans are actually on them.

A story scores when several independent signals point at it at once:
    outlets      how many news outlets carry it                    (news.py, state/news.json)
    X            a live Kenyan X trend names the same people/places (radar.py, trends24)
    TV clips     Kenyan TV uploads about it, weighted by views/hour  (radar.py, YouTube RSS)
    searches     a Google Trends topic matches it                   (trends.py)
Matching is by the names in a headline (people, places, institutions), so "Ruto attacks Uhuru" on Citizen TV,
"Tapeli Uhuru Kenyatta" on X and a Nation headline about Uhuru all count toward one story.
The writer gets the ranked list and builds most posts on the top of it.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
COMMON = {"kenya", "kenyan", "kenyans", "nairobi", "president", "government", "county", "national", "news", "live",
          "today", "breaking", "update", "video", "watch", "full", "says", "said", "after", "over", "with", "from",
          "this", "that", "what", "when", "will", "into", "about", "their", "they", "citizen", "ntv", "ktn", "the",
          "and", "for", "new", "how", "why", "who", "brief", "briefs", "dear", "inside", "week", "year", "day",
          "market", "forest", "commissioner", "police", "court", "school", "hospital", "road", "plan", "plans",
          "development", "tour", "service", "statement", "number", "people", "club", "golf", "modern", "focus",
          "delivers", "next", "first", "last", "more", "over-the-counter"}


def names(text: str) -> set[str]:
    """The names in a headline or trend: capitalised words and hashtag parts (lower-cased), minus filler."""
    words = []
    for tag in re.findall(r"#(\w+)", text):
        words += re.findall(r"[A-Z][a-z]+|[A-Z]{2,}(?![a-z])", tag)
    words += re.findall(r"\b[A-Z][A-Za-z'’-]+\b", re.sub(r"#\w+", " ", text))
    out = set()
    for w in words:
        w = re.sub(r"['’]s$", "", w).lower()
        if len(w) >= 4 and w not in COMMON:
            out.add(w)
    return out


def _load(name: str) -> dict:
    try:
        return json.loads((STATE / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def rank(news: list[dict], x: list[dict], videos: list[dict], gtrends: list[dict], top: int = 10) -> list[dict]:
    """Stories (clusters of headlines sharing names) with a demand score and the signals behind it."""
    # a name in almost every headline ("ruto") proves little on its own; rare names ("kericho", "cherargei") a lot
    df: dict[str, int] = {}
    for item in news:
        for n in names(item["title"]):
            df[n] = df.get(n, 0) + 1
    common = {n for n, c in df.items() if c > max(3, len(news) // 8)}

    def hit(a: set[str], b: set[str]) -> bool:
        shared = a & b
        return len(shared) >= 2 or bool(shared - common)

    stories: list[dict] = []
    for item in news:
        n = names(item["title"])
        if not n:
            continue
        home = next((s for s in stories if len(s["names"] & n) >= 2 or (len(n) == 1 and n <= s["names"])), None)
        if home:
            home["items"].append(item)
            home["names"] |= n
        else:
            stories.append({"names": set(n), "items": [item]})
    for s in stories:
        outlets = {i.get("outlet", "") for i in s["items"]}
        x_hits = [t["name"] for t in x if hit(names(t["name"]), s["names"])]
        v_hits = [v for v in videos if hit(names(v["title"]), s["names"])]
        g_hits = [g["title"] for g in gtrends if hit(names(g["title"]), s["names"])]
        views = sum(v.get("per_hour", 0) for v in v_hits)
        s.update(outlets=len(outlets), x=x_hits[:4], clips=len(v_hits), views_per_hour=views, searches=g_hits[:3],
                 score=round(len(outlets) + 3 * min(len(x_hits), 3) + 2 * min(len(v_hits), 3)
                             + (math.log10(views + 1) if views else 0) + 2 * min(len(g_hits), 2), 1))
    stories.sort(key=lambda s: -s["score"])
    out = []
    for s in stories[:top]:
        lead = s["items"][0]
        out.append({"story": lead["title"], "link": lead["link"], "score": s["score"], "outlets": s["outlets"],
                    "x": s["x"], "clips": s["clips"], "searches": s["searches"],
                    "names": sorted(s["names"])[:8]})
    return out


def current(top: int = 10) -> list[dict]:
    news = _load("news.json").get("items", [])
    radar = _load("radar.json")
    trends = _load("trends.json").get("safe", [])
    return rank(news, radar.get("x", []), radar.get("videos", []), trends, top)


def prompt_block(top: int = 10) -> str:
    ranked = current(top)
    if not ranked:
        return ""
    lines = []
    for i, s in enumerate(ranked, 1):
        why = [f"{s['outlets']} outlets"] + ([f"on X: {', '.join(s['x'])}"] if s["x"] else []) + \
              ([f"{s['clips']} TV clips"] if s["clips"] else []) + ([f"searched: {', '.join(s['searches'])}"] if s["searches"] else [])
        lines.append(f"{i}. {s['story']} ({'; '.join(why)}) {s['link']}")
    return ("\nWHAT KENYA IS ON THIS WEEK (ranked by demand: outlets + X trends + TV clips + searches)\n" + "\n".join(lines) +
            "\nGive Kenyans what they are already talking about: build most posts on stories 1-5, every post on the "
            "list unless it is an anniversary (Hatutasahau) or a deadline this week. Find the angle nobody has posted "
            "yet: the document, the number, the promise they made last time. Put the rank in a `demand` field.\n")
