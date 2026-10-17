"""
news.py — what Kenya is talking about this week, so the writer reacts to real stories (with links).

Reads free RSS feeds (Google News searches for Kenyan politics, plus Kenyan outlets) listed in
content/news_feeds.json, keeps the last few days, removes duplicates, and hands the writer a short list
of headlines with their outlet and link. Every claim drawn from them must cite that link in `source`.

    python news.py            # fetch now and print the list
"""
from __future__ import annotations

import datetime as dt
import email.utils
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
FEEDS = HERE / "content" / "news_feeds.json"
OUT = HERE / "state" / "news.json"
MAX_AGE = dt.timedelta(days=4)


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (jua-kesho news reader)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _when(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    try:
        d = email.utils.parsedate_to_datetime(text)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def parse(xml: bytes, feed_name: str) -> list[dict]:
    root = ET.fromstring(xml)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = it.find("source")
        outlet = (src.text.strip() if src is not None and src.text else feed_name)
        # Google News titles end with " - Outlet": keep the headline clean
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -len(outlet) - 3]
        if title and link:
            items.append({"title": title, "link": link, "outlet": outlet, "published": _when(it.findtext("pubDate"))})
    return items


def _key(title: str) -> str:
    return " ".join(sorted(set(re.findall(r"[a-z0-9]{4,}", title.lower())))[:8])


def collect() -> dict:
    cfg = json.loads(FEEDS.read_text(encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    seen, items, errors = set(), [], {}
    for feed in cfg["feeds"]:
        try:
            for it in parse(_get(feed["url"]), feed["name"]):
                if it["published"] and now - it["published"] > MAX_AGE:
                    continue
                k = _key(it["title"])
                if k in seen:
                    continue
                seen.add(k)
                items.append({**it, "published": it["published"].isoformat() if it["published"] else "",
                              "topic": feed.get("topic", "politics")})
        except Exception as e:   # one feed down never stops the week
            errors[feed["name"]] = str(e)[:160]
    items.sort(key=lambda x: x["published"], reverse=True)
    data = {"fetched": now.isoformat(), "items": items[:60], "errors": errors}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


MAX_ITEMS = 18


def refs(max_items: int = MAX_ITEMS) -> dict[str, dict]:
    """The headlines the writer sees, by the short id it cites them with: {"n1": item, ...}."""
    if not OUT.exists():
        return {}
    data = json.loads(OUT.read_text(encoding="utf-8"))
    return {f"n{i + 1}": x for i, x in enumerate(data.get("items", [])[:max_items])}


def prompt_block(max_items: int = MAX_ITEMS, max_age_hours: int = 30) -> str:
    """Headlines for the writer; empty if there's no fresh data."""
    if not OUT.exists():
        return ""
    data = json.loads(OUT.read_text(encoding="utf-8"))
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(data["fetched"])
    if age > dt.timedelta(hours=max_age_hours) or not data.get("items"):
        return ""
    lines = [f"- [{k}] [{x['outlet']}] {x['title']} ({x['published'][:10]})" for k, x in refs(max_items).items()]
    return ("\nTHIS WEEK IN KENYA (real headlines, newest first, each with its id in brackets)\n" + "\n".join(lines) +
            "\nBuild most posts on these stories: what Kenyans are already talking about. Use only facts these "
            "headlines state or that an official record states. In `source` (and `claim_source` for quotes) write "
            "the headline id(s) you used, e.g. \"n3\" or \"n3, n7\"; the system replaces them with the article "
            "links. Never invent a detail a headline doesn't give; if a story is unclear, pick another. Prefer "
            "stories that touch people's pockets, rights, safety and votes.\n")


def resolve(post: dict, table: dict[str, dict] | None = None) -> dict:
    """Turns headline ids in `source` / `claim_source` ("n3") into the outlet and date, and records the real
    article links in `source_links`, once, at drafting: later news can't change what an id meant."""
    table = refs() if table is None else table
    links = list(post.get("source_links") or [])
    for field in ("source", "claim_source"):
        text = str(post.get(field) or "")
        def sub(m):
            x = table.get(m.group(0).lower())
            if not x:
                return m.group(0)
            if x["link"] not in [l["link"] for l in links]:
                links.append({"outlet": x["outlet"], "title": x["title"], "link": x["link"],
                              "published": x.get("published", "")[:10]})
            return f"{x['outlet']}, {x.get('published', '')[:10]}"
        new = re.sub(r"\b[nN]\d{1,2}\b", sub, text)
        if new != text:
            post[field] = new
    if links:
        post["source_links"] = links
    return post


if __name__ == "__main__":
    d = collect()
    print(f"{len(d['items'])} stories, errors: {d['errors'] or 'none'}")
    for x in d["items"][:20]:
        print(f"  [{x['outlet']}] {x['title']}")
