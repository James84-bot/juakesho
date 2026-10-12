"""
trends.py — what Kenya is searching right now, filtered so the brand can ride it safely.

Source: Google Trends "Trending now" RSS (https://trends.google.com/trending/rss?geo=KE).
Every topic passes the same banned-topic rules as posts, plus a tragedy filter:
we never newsjack deaths, disasters or crime. Political trends are kept and marked `civic`:
the writer may cover them only with sourced facts (Set It Straight, Explained, Promise Tracker).

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

# Never ride these: tragedy, crime, betting, gossip. (Divisive/tribal politics is civic: called out, with care.)
UNSAFE = re.compile(
    r"\b(death|dies|died|dead|killed|kill|murder|shooting|shot|accident|crash|fire|flood|attack|funeral|"
    r"burial|rape|assault|abduct|kidnap|missing|suicide|war|bomb|terror|"
    r"bet|betting|odds|jackpot|sportpesa|casino|gambling|nude|leaked|scandal)\b", re.I)
# Political and civic trends: in scope, but flagged so the writer treats them with extra care
CIVIC = re.compile(
    r"\b(president|presidential|governor|senator|mp|mca|cabinet|minister|parliament|election|elections|iebc|"
    r"campaign|party|bid|impeach|impeachment|protest|protests|maandamano|bill|budget|tax|taxes|court|ruling|"
    r"arrest|arrested|trial|tribe|tribal|tribalism|hate speech|ncic|church|clergy|pastor|bishop|mosque|imam|abduction|abducted|goons|police)\b", re.I)


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


def collect(geos=("KE",)) -> dict:
    safe, dropped, errors = [], [], {}
    for geo in geos:
        try:
            for t in fetch(geo):
                ok, why = is_safe(t)
                if ok and CIVIC.search(" ".join([t["title"]] + [n["title"] for n in t["news"]])):
                    t = {**t, "civic": True}
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
        tag = "civic, " if t.get("civic") else ""
        lines.append(f"- [{tag}{t['geo']}] {t['title']} ({t['traffic']} searches){' · ' + head if head else ''}")
    return ("\nTRENDING NOW (Google Trends, already filtered for safety)\n" + "\n".join(lines) +
            "\nRide the Kenyan ones hard: use up to 4 per week. Civic trends: only with sourced facts, as Set It Straight, Explained (decode/makanga), "
            "Follow the Money or Promise Tracker; never rumours, never someone's private life, never a court case's "
            "outcome before the court decides. Other trends need a genuine knowledge, money, tech or future angle. "
            "Put the trend in a `trend` field on that post. A weak trend-jack is worse than none.\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geo", action="append", help="country code, repeatable (default KE)")
    a = ap.parse_args()
    data = collect(tuple(a.geo) if a.geo else ("KE",))
    print(f"safe {len(data['safe'])}, dropped {len(data['dropped'])}, errors {data['errors'] or 'none'}")
    for t in data["safe"][:15]:
        print(f"  ✓ [{t['geo']}] {t['title']}  {t['traffic']}")
    for d in data["dropped"][:15]:
        print(f"  ✗ {d['title']}  ({d['why']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
