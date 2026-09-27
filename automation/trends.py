"""
trends.py — what Kenya is searching right now, filtered so the brand can ride it safely.

Source: Google Trends "Trending now" RSS (https://trends.google.com/trending/rss?geo=KE).
Every topic passes the same banned-topic rules as posts, plus a tragedy filter:
we never newsjack deaths, disasters, crime or politics.

    python trends.py            # prints safe topics for KE (+ NG, ZA, US for a global view)
    python trends.py --geo KE   # one country

Output: state/trends.json, read by draft.py. A failed fetch never blocks the week.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import guard

HERE = Path(__file__).resolve().parent
OUT = HERE / "state" / "trends.json"
FEED = "https://trends.google.com/trending/rss?geo={geo}"

# Never ride these: tragedy, crime, and anything political or divisive.
UNSAFE = re.compile(
    r"\b(death|dies|died|dead|killed|kill|murder|shooting|shot|accident|crash|fire|flood|attack|funeral|"
    r"burial|arrest|arrested|court|trial|rape|assault|abduct|kidnap|missing|suicide|war|bomb|terror|"
    r"president|presidential|governor|senator|mp|mca|cabinet|minister|parliament|election|elections|"
    r"campaign|party|bid|impeach|protest|protests|maandamano|tribe|church|mosque|pastor|imam|"
    r"bet|betting|odds|jackpot|sportpesa|casino|gambling|nude|leaked|scandal)\b", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fetch(geo: str, timeout: int = 20) -> list[dict]:
    req = urllib.request.Request(FEED.format(geo=geo), headers={"User-Agent": "jua-kesho/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        root = ET.fromstring(r.read())
    items = []
    for item in root.iter("item"):
        row = {"geo": geo, "title": "", "traffic": "", "news": []}
        for el in item:
            name = _local(el.tag)
            if name == "title":
                row["title"] = (el.text or "").strip()
            elif name == "approx_traffic":
                row["traffic"] = (el.text or "").strip()
            elif name == "news_item":
                news = {_local(c.tag): (c.text or "").strip() for c in el}
                row["news"].append({"title": news.get("news_item_title", ""), "url": news.get("news_item_url", ""),
                                    "source": news.get("news_item_source", "")})
        if row["title"]:
            items.append(row)
    return items


def is_safe(topic: dict) -> tuple[bool, str]:
    text = " ".join([topic["title"]] + [n["title"] for n in topic["news"]])
    m = UNSAFE.search(text)
    if m:
        return False, f"unsafe: '{m.group(0)}'"
    for name, pattern in guard.BANNED_TOPICS.items():
        if re.search(pattern, text.lower()):
            return False, f"banned: {name}"
    return True, ""


def traffic_value(t: str) -> int:
    m = re.match(r"([\d,]+)", t or "")
    return int(m.group(1).replace(",", "")) if m else 0


def collect(geos=("KE", "NG", "ZA", "US")) -> dict:
    safe, dropped, errors = [], [], {}
    for geo in geos:
        try:
            for t in fetch(geo):
                ok, why = is_safe(t)
                (safe if ok else dropped).append({**t, **({} if ok else {"why": why})})
        except Exception as e:  # network or format change: note it, carry on
            errors[geo] = str(e)[:200]
    safe.sort(key=lambda t: (t["geo"] != "KE", -traffic_value(t["traffic"])))
    data = {"fetched": dt.datetime.now(dt.timezone.utc).isoformat(), "safe": safe[:25],
            "dropped": [{"title": d["title"], "why": d["why"]} for d in dropped], "errors": errors}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def prompt_block(max_items: int = 12, max_age_hours: int = 48) -> str:
    """Text for the drafter; empty if there is no fresh data."""
    if not OUT.exists():
        return ""
    data = json.loads(OUT.read_text(encoding="utf-8"))
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(data["fetched"])
    if age > dt.timedelta(hours=max_age_hours) or not data.get("safe"):
        return ""
    lines = []
    for t in data["safe"][:max_items]:
        head = t["news"][0]["title"] if t["news"] else ""
        lines.append(f"- [{t['geo']}] {t['title']} ({t['traffic']} searches){' · ' + head if head else ''}")
    return ("\nTRENDING NOW (Google Trends, already filtered for safety)\n" + "\n".join(lines) +
            "\nUse at most 2 per week, and only with a genuine tech, AI or future angle (e.g. a big match → "
            "\"how clubs use data\"; a new phone launch → a hack). Put the trend in a `trend` field on that post. "
            "Never force it; a weak trend-jack is worse than none.\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geo", action="append", help="country code, repeatable (default KE NG ZA US)")
    a = ap.parse_args()
    data = collect(tuple(a.geo) if a.geo else ("KE", "NG", "ZA", "US"))
    print(f"safe {len(data['safe'])}, dropped {len(data['dropped'])}, errors {data['errors'] or 'none'}")
    for t in data["safe"][:15]:
        print(f"  ✓ [{t['geo']}] {t['title']}  {t['traffic']}")
    for d in data["dropped"][:15]:
        print(f"  ✗ {d['title']}  ({d['why']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
