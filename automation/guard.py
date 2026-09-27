"""
guard.py — every post passes this before it can be rendered or published.

Checks, per post:
  1. Schema: the template exists and every required field is present and not too long.
  2. Clean content: nothing a grandmother, a child or a boss would object to.
  3. Brand rules: no hype words, max 3 hashtags, no betting or get-rich-quick.
  4. Facts: posts that state numbers or history must carry a `source`.

Errors block the post. Warnings are shown to the human approver.

    python guard.py content/posts.json
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# field -> max characters. Keeps text inside the designed boxes.
SCHEMAS: dict[str, dict[str, int]] = {
    "intro":    {"hello": 30, "community": 90},
    "neno":     {"word": 14, "full": 34, "say": 20, "sw": 120, "en": 110, "note": 60, "example": 130},
    "makanga":  {"topic": 22, "like": 34, "explain": 190, "punch": 60},
    "ukweli":   {"claim": 60, "verdict_text": 18, "truth": 160},
    "tool":     {"title": 40, "warn": 50},
    "usiibiwe": {"title": 50, "sender": 24, "sms": 120},
    "shosh":    {"question": 70, "answer": 150, "punch": 60},
    "africa":   {"year": 4, "name": 16, "country": 16, "fact": 170, "now": 50},
    "hapa":     {"topic": 34, "hapa": 110, "huko": 110, "ask": 60},
    "cover":    {"series": 20, "kicker": 40},
    "kesho":    {"headline": 60, "leo": 120, "kesho": 120, "anza": 110},
    "poll":     {"question": 40, "cta": 30},
    "vichekesho": {"title": 30, "punch": 50},
    "hack":     {"hook": 40, "title": 60, "payoff": 50},
    "decode":   {"hook": 40, "word": 14, "meaning": 130, "try_this": 140},
    "cap":      {"claim": 70, "real": 170},
    "pov":      {"year": 4, "pov": 110, "real": 150},
    "build":    {"hook": 40, "title": 60, "result": 60},
    "glasspoll": {"hook": 30, "question": 40, "cta": 30},
    "still":    {"industry": 16, "thing": 70, "old": 110, "new": 130, "cta": 50},
    "spotlight": {"kind": 14, "name": 22, "country": 20, "what": 140, "why": 130, "cta": 50},
    "money":    {"hook": 40, "number": 14, "unit": 40, "what": 140, "why": 120, "check": 110},
    "avatar":   {},
    "banner":   {"line": 40, "sub": 50},
}
LISTS: dict[str, dict[str, tuple[int, int, int]]] = {  # field -> (min items, max items, max chars each)
    "intro": {"promise": (2, 3, 50)},
    "tool": {"steps": (2, 4, 70)},
    "usiibiwe": {"tips": (2, 3, 70)},
    "cover": {"lines": (2, 4, 14)},
    "poll": {"options": (2, 2, 18)},
    "hack": {"moves": (2, 4, 70)},
    "build": {"flow": (3, 6, 45), "stack": (1, 5, 14)},
    "glasspoll": {"options": (2, 2, 22)},
}
CHOICES = {
    "ukweli": {"verdict": {"uongo", "ukweli", "kiasi"}},
    "cap": {"verdict": {"cap", "nocap", "kinda"}},
}
FACT_TEMPLATES = {"africa", "hapa", "usiibiwe", "kesho", "pov", "cap", "spotlight", "money"}
CIVIC_SERIES = {"money", "See Through It"}  # must carry a source

# Clean-content list: English, Kiswahili and Sheng. Whole-word matches only.
# Kept deliberately mild here; extend blocklist.txt for your own additions.
BLOCK = {
    "damn", "hell", "crap", "stupid", "idiot", "shut up", "sexy", "nude", "drunk", "weed",
    "dumb", "useless people", "lazy africans", "backward people", "clowns", "trash people",
    "shenzi", "mjinga", "pumbavu", "mavi", "malaya", "fala", "bangi", "chang'aa",
}
# Topics the brand never touches (keeps it for everyone, everywhere)
BANNED_TOPICS = {
    "betting": r"\b(bet|betting|sportpesa|odds|jackpot|kamari)\b",
    "get-rich-quick": r"\b(get rich|guaranteed (profit|income|returns)|double your money|100% win)\b",
    "politics": r"\b(ruto|raila|uhuru|odm|uda|jubilee|azimio|election|siasa|mp for)\b",
    "tribe": r"\b(tribe|tribal|kabila)\b",
    "crypto-shill": r"\b(buy (now|this coin)|to the moon|pump)\b",
}
NEVER_WORDS = {"leverage", "seamless", "game-changer", "game changer", "cutting-edge", "revolutionary",
               "delve", "passionate", "unlock your potential"}

_extra = Path(__file__).with_name("blocklist.txt")
if _extra.exists():
    BLOCK |= {w.strip().lower() for w in _extra.read_text(encoding="utf-8").splitlines() if w.strip()}


@dataclass
class Report:
    id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _all_text(post: dict) -> str:
    parts = []
    for k, v in post.items():
        if k in {"id", "template", "bg", "size", "expr", "seed", "status", "source", "publish_at", "platforms", "trend", "lane", "guard"}:
            continue
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, dict):  # comic panels: collect what people say
                    for side in ("left", "right"):
                        c = x.get(side) or {}
                        parts.extend(str(c.get(k, "")) for k in ("say", "sms"))
                else:
                    parts.append(str(x))
    return " ".join(parts)


SAFE_NAMES = {"Jua Kesho", "Bwana Ahadi", "Mama Mboga", "Google Translate", "National Assembly", "Mombasa Gate Bridge",
              "Controller Budget", "Auditor General", "Follow The Money", "See Through It"}


NOT_NAMES = {"The", "This", "That", "These", "Your", "Just", "Check", "Real", "Nobody", "Blocked", "Ksh", "See",
             "Through", "Why", "What", "How", "Read", "Save", "Send", "Kazi", "Tag", "Follow", "Money", "Every", "Some"}


def check(post: dict) -> Report:
    rep = Report(post.get("id", "?"))
    tpl = post.get("template")
    if tpl not in SCHEMAS:
        rep.errors.append(f"unknown template '{tpl}'")
        return rep
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", str(post.get("id", ""))):
        rep.errors.append("id must be lowercase letters, digits and dashes")

    for f, limit in SCHEMAS[tpl].items():
        v = post.get(f)
        if not isinstance(v, str) or not v.strip():
            rep.errors.append(f"missing field '{f}'")
        elif len(v) > limit:
            rep.errors.append(f"'{f}' is {len(v)} chars (max {limit})")
    for f, (lo, hi, each) in LISTS.get(tpl, {}).items():
        v = post.get(f)
        if not isinstance(v, list) or not (lo <= len(v) <= hi):
            rep.errors.append(f"'{f}' needs {lo}-{hi} items")
            continue
        for i, item in enumerate(v):
            if len(str(item)) > each:
                rep.errors.append(f"'{f}[{i}]' is {len(str(item))} chars (max {each})")
    for f, allowed in CHOICES.get(tpl, {}).items():
        if post.get(f) not in allowed:
            rep.errors.append(f"'{f}' must be one of {sorted(allowed)}")

    if tpl == "vichekesho":
        _check_comic(post, rep)
    if tpl == "pov":
        cast = post.get("cast")
        if not isinstance(cast, list) or not 1 <= len(cast) <= 3:
            rep.errors.append("'cast' needs 1-3 characters")
        else:
            for c in cast:
                if not isinstance(c, dict) or c.get("who") not in COMIC_CAST:
                    rep.errors.append(f"pov cast: unknown character {c!r}")
                elif c.get("who") != "jua" and c.get("pose", "stand") not in COMIC_POSES:
                    rep.errors.append(f"pov cast: unknown pose '{c.get('pose')}'")

    text = _all_text(post)
    low = text.lower()
    for w in BLOCK:
        if re.search(rf"(?<![a-z']){re.escape(w)}(?![a-z'])", low):
            rep.errors.append(f"not clean for everyone: '{w}'")
    for topic, pattern in BANNED_TOPICS.items():
        if re.search(pattern, low):
            rep.errors.append(f"banned topic: {topic}")
    for w in NEVER_WORDS:
        if w in low:
            rep.warnings.append(f"off-voice word: '{w}'")

    caption = post.get("caption", "")
    if caption:
        tags = re.findall(r"#[A-Za-z]\w*", caption)
        if len(tags) > 3:
            rep.errors.append(f"caption has {len(tags)} hashtags (max 3)")
        if len(caption) > 2000:
            rep.errors.append("caption over 2,000 characters")
    elif tpl not in {"avatar", "banner"}:
        rep.warnings.append("no caption yet")
    if caption and not re.search(r"\b(send|share|tag|save|comment|reply|vote|drop)\b", caption.lower()):
        rep.warnings.append("caption has no send/share/save call: sends and saves drive reach")

    # Civic content: systems and money, never accusations against a named person
    if tpl == "money" or post.get("series") in CIVIC_SERIES or any(c.get("who") == "ahadi" for p in post.get("panels", []) or [] for c in (p.get("left") or {}, p.get("right") or {})):
        if not post.get("source"):
            rep.errors.append("civic post needs a `source` (report, audit, study)")
        names = {m for m in re.findall(r"\b(?:[A-Z][a-z]{2,}\s){1,2}[A-Z][a-z]{2,}\b", text)
                 if m not in SAFE_NAMES and not set(m.split()) & NOT_NAMES}
        if names:
            rep.warnings.append(f"possible named person(s): {', '.join(sorted(names))}. Civic posts target systems, not people.")
    if tpl in FACT_TEMPLATES and not post.get("source"):
        rep.warnings.append("states facts but has no `source`; verify before approving")
    if re.search(r"\b(19|20)\d{2}\b|\d+%|\bksh\s?\d", low) and not post.get("source"):
        rep.warnings.append("contains a year, % or amount with no `source`")
    return rep


COMIC_CAST = {"shosh", "makanga", "mama_mboga", "boda", "student", "pro", "farmer", "creator", "techie", "ahadi", "jua"}
COMIC_POSES = {"stand", "wave", "point", "think", "cheer", "walk", "phone", "shrug", "sit"}
COMIC_BGS = {"jua", "pwani", "waridi", "maziwa", "ziwa"}  # light panels keep dark ink readable


def _check_comic(post: dict, rep: Report) -> None:
    panels = post.get("panels")
    if not isinstance(panels, list) or len(panels) != 3:
        rep.errors.append("'panels' needs exactly 3 panels")
        return
    for i, p in enumerate(panels, 1):
        if p.get("bg") not in COMIC_BGS:
            rep.errors.append(f"panel {i}: bg must be one of {sorted(COMIC_BGS)}")
        slots = []
        for side in ("left", "right"):
            c = p.get(side)
            if not c:
                continue
            if c.get("who") not in COMIC_CAST:
                rep.errors.append(f"panel {i} {side}: unknown character '{c.get('who')}'")
            if c.get("who") != "jua" and c.get("pose", "stand") not in COMIC_POSES:
                rep.errors.append(f"panel {i} {side}: unknown pose '{c.get('pose')}'")
            if c.get("say"):
                slots.append("a" if side == "left" else "b")
                if len(c["say"]) > 80:
                    rep.errors.append(f"panel {i} {side}: 'say' is {len(c['say'])} chars (max 80)")
            if c.get("sms"):
                slots.append("b" if side == "left" else "a")
                if len(c["sms"]) > 90:
                    rep.errors.append(f"panel {i} {side}: 'sms' is {len(c['sms'])} chars (max 90)")
        if len(slots) != len(set(slots)):
            rep.errors.append(f"panel {i}: two bubbles would overlap (one speech + one SMS max, from different sides)")
        if not p.get("left") and not p.get("right"):
            rep.errors.append(f"panel {i}: empty")
    if not rep.errors:  # geometry: measured with the real font, so a panel that can't fit fails here, not on render
        try:
            import render
            render.comic_layout(panels, 1080, 0)
        except ValueError as e:
            rep.errors.append(str(e))


def check_all(posts: list[dict]) -> list[Report]:
    reports = [check(p) for p in posts]
    ids = [p.get("id") for p in posts]
    for r in reports:
        if ids.count(r.id) > 1:
            r.errors.append("duplicate id")
    return reports


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "content" / "posts.json")
    posts = json.loads(path.read_text(encoding="utf-8"))["posts"]
    reports = check_all(posts)
    bad = 0
    for r in reports:
        mark = "✓" if r.ok else "✗"
        print(f"{mark} {r.id}")
        for e in r.errors:
            print(f"    ERROR   {e}")
        for w in r.warnings:
            print(f"    warning {w}")
        bad += not r.ok
    print(f"\n{len(reports) - bad}/{len(reports)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
