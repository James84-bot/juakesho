"""
fbdigest.py — the Facebook-native evening post, and the daily share kit for the owner's own profile.

Facebook readers in Kenya read: an evening post that tells the day's stories in a few plain lines, with the day's
designed pictures as an album, suits the Page better than one more video. It is built only from posts that already
went out today (their approved captions), so it states nothing new and needs no writer.

No API can post to a personal profile (Meta removed it), so once the digest is live the owner gets one Telegram
message a day with its link: open, tap Share. That is the share kit.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

WINDOW = ((20, 30), (23, 0))   # EAT: after the evening post (19:30) has gone out, while Kenya is still scrolling
MIN_POSTS = 2                  # one story is not a digest: the share kit then points at that post instead
MAX_ITEMS = 5
ITEM_MAX = 260                 # characters per story: two sentences at most
TAGS = re.compile(r"(\s*#\w+)+\s*$")


def due(now: dt.datetime, state: dict) -> bool:
    """Inside the evening window and not done today."""
    start, end = (now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in WINDOW)
    return start <= now < end and state.get("date") != now.date().isoformat()


def today_posts(weeks: list[dict], now: dt.datetime) -> list[dict]:
    """Posts that went out on the Page today, oldest first (a Story or a carousel slide is not a story of its own)."""
    out = []
    for data in weeks:
        for p in data.get("posts", []):
            if p.get("status") != "published" or not p.get("fb_id") or p.get("n"):
                continue
            try:
                at = dt.datetime.fromisoformat(p.get("published_at") or p["publish_at"]).astimezone(now.tzinfo)
            except (KeyError, ValueError):
                continue
            if at.date() == now.date() and at <= now:
                out.append({**p, "_label": data.get("collection", ""), "_at": at})
    return sorted(out, key=lambda p: p["_at"])


def story_line(post: dict) -> str:
    """The news of one post in at most two sentences, from its approved caption: no hashtags, no question to the
    reader, no "what it means" or call-to-action lines (the digest has its own question)."""
    cap = TAGS.sub("", str(post.get("caption") or "")).strip()
    for para in [x.strip() for x in re.split(r"\n\s*\n", cap) if x.strip()]:
        if para.endswith("?") or re.match(r"^(what it means|👉|tell us|share|follow)", para, re.I):
            continue
        sentences = re.findall(r"[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$", para)
        line = ""
        for s in sentences[:2]:
            if len(line) + len(s) > ITEM_MAX and line:
                break
            line += s
        line = line.strip()
        if len(line) > ITEM_MAX:
            line = line[:ITEM_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        if line:
            return line
    return str(post.get("message") or "").strip()


def message(posts: list[dict], now: dt.datetime, brand: dict) -> str:
    items = [story_line(p) for p in posts[:MAX_ITEMS]]
    items = [x for x in items if x]
    tag = "#" + re.sub(r"\W", "", str(brand.get("name") or "KenyaOnRecord").title())
    return (f"Kenya today, {now:%A %-d %B} 🇰🇪\n\n" + "\n\n".join(f"▪️ {x}" for x in items)
            + "\n\nWhich of these affects you most? Tell us below 👇"
            + "\n\nThe sources for every story are in the first comment under its post on this Page."
            + f"\n\n{tag}")


def share_text(link: str, digest: bool) -> str:
    what = "Today's digest is on the Page" if digest else "Today's post is on the Page"
    return (f"📣 <b>Share kit</b>: {what}. Open it, tap <b>Share → Share now</b> to put it on your profile.\n"
            f"<a href=\"{link}\">Open the post</a>\n\n"
            "Line to add if you like: <i>What happened in Kenya today, in one post 👇</i>")


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
