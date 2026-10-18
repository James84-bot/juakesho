"""
material.py — the real thing each everyday series is built on, chosen by the system, never by the writer.

The writer (a free AI model) kept citing whatever headline came first, and invented prices and "viral
messages". So for the series that must never be made up, the system picks the material before anything is
written and locks it into the post:

    Kenya at its best / Built in Kenya   one verified entry from content/facts.json (fact + its page)
    The Real Price                       a newsroom report about a price
    Guess the Price                      a newsroom headline that states the price (so the answer is real)
    Myth or Fact                         a fact-check, or a report on a rumour or fake
    Usiibiwe!                            a report or warning about a scam

A slot with no honest material is held with the reason, instead of being written around nothing.
Used material is remembered (state/material_used.json) so a fact or a report is not reused.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BANK = HERE / "content" / "facts.json"
NEWS = HERE / "state" / "news.json"
USED = HERE / "state" / "material_used.json"
BANK_REST = dt.timedelta(days=120)   # a showcase fact comes back at most three times a year

PRICE = re.compile(r"\b(price|prices|priced|cost|costs|cheaper|costlier|unga|maize flour|fuel|petrol|diesel|"
                   r"kerosene|fares?|rent|fees?|tariffs?|sugar|bread|milk|cooking gas|lpg|electricity|tokens|"
                   r"bundles?|inflation|epra)\b", re.I)
FIGURE = re.compile(r"\b(?:k?sh\.?|kes)\s?\d[\d,]*(?:\.\d+)?\b", re.I)
MYTH = re.compile(r"\b(fake|false|hoax|fact.?check\w*|misleading|debunk\w*|not true|doctored|fabricated|"
                  r"misinformation|disinformation|rumou?rs?)\b|pesacheck|africa check", re.I)
SCAM = re.compile(r"\b(scams?|scammers?|fraud\w*|conm[ae]n|con artists?|phishing|swindl\w*)\b", re.I)

WHY = {
    "bank": "no verified fact left in content/facts.json for this series (all used recently): add entries",
    "price": "no newsroom report about a price in this week's news, so there is nothing real to build The Real "
             "Price on",
    "price_figure": "no headline this week states a price, so Guess the Price would have no real answer",
    "myth": "no fact-check or report on a rumour this week, so Myth or Fact would have to invent the rumour",
    "scam": "no report or warning about a scam this week",
}


def kind(slot: dict) -> str | None:
    """What real material this slot needs, or None if the writer works from the news list as usual."""
    series, angle, tpl = slot.get("series") or "", slot.get("angle") or "", slot.get("template")
    if slot.get("hot") or slot.get("breaking"):
        return None
    if tpl == "kenya" and series in {"Kenya at its best", "Built in Kenya"}:
        return "bank"
    if angle == "price_quiz" or series == "Guess the Price":
        return "price_figure"
    if angle == "real_price" or series == "The Real Price":
        return "price"
    if angle == "myth" or series == "Myth or Fact":
        return "myth"
    if tpl == "usiibiwe":
        return "scam"
    return None


def _used() -> dict:
    try:
        return json.loads(USED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _news() -> list[dict]:
    try:
        data = json.loads(NEWS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return list(data.get("series") or []) + list(data.get("items") or [])


def _fits(k: str, title: str) -> bool:
    if k == "price":
        return bool(PRICE.search(title))
    if k == "price_figure":
        return bool(PRICE.search(title) and FIGURE.search(title))
    if k == "myth":
        return bool(MYTH.search(title))
    if k == "scam":
        return bool(SCAM.search(title))
    return False


def pick(slot: dict, taken: set[str], used: dict | None = None, today: dt.date | None = None,
         bank: list[dict] | None = None, news: list[dict] | None = None) -> dict | None:
    """The material for one slot (None if nothing honest is available). `taken`: keys already given out."""
    k = kind(slot)
    if not k:
        return None
    used = _used() if used is None else used
    today = today or dt.date.today()
    if k == "bank":
        entries = json.loads(BANK.read_text(encoding="utf-8"))["entries"] if bank is None else bank
        def rested(e):
            when = used.get("bank:" + e["id"])
            return not when or today - dt.date.fromisoformat(when) >= BANK_REST
        fresh = [e for e in entries if e["series"] == slot.get("series") and "bank:" + e["id"] not in taken
                 and rested(e)]
        if not fresh:
            return None
        fresh.sort(key=lambda e: used.get("bank:" + e["id"], ""))   # never used first, then the longest rested
        e = fresh[0]
        return {"kind": "bank", "key": "bank:" + e["id"], **e}
    for x in (_news() if news is None else news):
        key = "news:" + x["link"]
        if key in taken or key in used or not _fits(k, x["title"]):
            continue
        return {"kind": k, "key": key, "title": x["title"], "outlet": x["outlet"], "link": x["link"],
                "published": (x.get("published") or "")[:10]}
    return None


def attach(slots: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Gives each series slot its material. Returns (slots to write, [(slot, why it is held)])."""
    used, taken = _used(), set()
    ready, held = [], []
    for s in slots:
        k = kind(s)
        if not k:
            ready.append(s)
            continue
        m = pick(s, taken, used)
        if not m:
            held.append((s, WHY[k]))
            continue
        taken.add(m["key"])
        s = {**s, "material": m}
        if m["kind"] == "bank":
            s.update(place=m["place"], fact=m["fact"], source=m["source"], photo_query=m["photo_query"],
                     source_links=[{"outlet": m["outlet"], "title": f"{m['name']}: {m['fact']}", "link": m["source"],
                                    "published": ""}])
        else:
            s.update(source=f"{m['outlet']}, {m['published']}",
                     source_links=[{k2: m[k2] for k2 in ("outlet", "title", "link", "published")}])
        ready.append(s)
    return ready, held


LOCKED = ("material", "place", "fact", "source", "photo_query", "source_links")


def lock(post: dict, slot: dict) -> dict:
    """After writing: the material's fields are the system's, whatever the writer put there."""
    if slot.get("material"):
        for k in LOCKED:
            if k in slot:
                post[k] = slot[k]
    return post


def brief(m: dict) -> str:
    """What the writer is told about its material."""
    if m["kind"] == "bank":
        return (f"VERIFIED MATERIAL (write from this only): {m['name']} ({m['place']}). Fact: {m['fact']} "
                f"`place`, `fact`, `source` and `photo_query` are filled in for you. Use no other number, year or "
                f"size than the ones in this fact; describe the place in plain words.")
    base = (f"MATERIAL: build this post on THIS report only: [{m['outlet']}] {m['title']} ({m['published']}). "
            f"Every fact and every number must come from this headline; `source` is filled in for you.")
    if m["kind"] == "price_figure":
        base += (" The correct option is the price in this headline (same item, same size); the other option is a "
                 "plausible wrong price. The last beat reveals the answer with that price.")
    if m["kind"] == "myth":
        base += " The claim is the rumour this report checks; the verdict is what the report found."
    if m["kind"] == "scam":
        base += " Explain THIS scam and how to spot it; never a different one."
    return base


def numbers_problem(post: dict) -> str:
    """Every figure in the post must be in its material (the fact, or the headline)."""
    m = post.get("material")
    if not isinstance(m, dict):
        return ""
    allowed = m.get("fact") if m.get("kind") == "bank" else m.get("title")
    keys = ("line", "message", "headline", "claim", "truth", "question", "hook", "number", "what", "verdict")
    body = " ".join(str(post.get(k) or "") for k in keys)
    body += " " + " ".join(str(b) for b in post.get("beats") or [])
    body += " " + " ".join(str(o) for o in post.get("options") or [])
    num = re.compile(r"\d[\d,]*(?:\.\d+)?")
    norm = lambda s: re.sub(r"[,\s]", "", s.lower()).rstrip(".")
    have = {norm(n) for n in num.findall(str(allowed or ""))}
    exact = set(have)
    if m.get("published"):   # "on 17 Oct": the report's own date may be named
        have |= {str(int(x)) for x in str(m["published"]).split("-") if x.isdigit()}
    if m.get("kind") == "price_figure":
        have = exact | {str(int(x)) for x in str(m.get("published") or "").split("-") if x.isdigit()}
        # the wrong option is meant to differ from the headline; the answer in the last beat must not
        last = {norm(n) for n in num.findall(str((post.get("beats") or [""])[-1]))}
        if not last & exact:
            return f"Guess the Price: the last beat must give the price in the headline ({str(allowed)[:90]})"
        options = [num.findall(str(o)) for o in post.get("options") or []]
        if sum(1 for o in options if {norm(n) for n in o} & exact) != 1:
            return "Guess the Price: exactly one option must be the price in the headline"
        have |= {norm(n) for o in options for n in o}
    bad = [n for n in num.findall(body) if norm(n) not in have]
    if bad:
        return (f"'{bad[0]}' is not in this post's material ({str(allowed)[:90]}): use only the numbers it gives")
    return ""


def mark(posts: list[dict], today: dt.date | None = None) -> None:
    """Remember the material of posts that were written, so it is not used again."""
    keys = [p["material"]["key"] for p in posts if isinstance(p.get("material"), dict)]
    if not keys:
        return
    used = _used()
    for k in keys:
        used[k] = (today or dt.date.today()).isoformat()
    USED.parent.mkdir(exist_ok=True)
    USED.write_text(json.dumps(used, indent=1, sort_keys=True), encoding="utf-8")
