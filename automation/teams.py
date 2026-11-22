"""
teams.py — a football club's colours for a sport post's accents (the highlight, the rule under the picture, the
quote mark), so a Manchester United story reads red and a Chelsea one blue at a glance.

Colours only. Club crests are the clubs' trademarks and artwork: they are never drawn or pasted in. The player's
own photo usually shows the crest on the shirt anyway, as the news photo it is.

Each club: the names the news uses for it, its primary colour, and the ink a highlighted word takes on it (white on
a dark colour, near-black on a light one). Only clubs whose colours are widely known; anything else keeps the brand
red. No party colours for politicians: a person's party changes and the page takes no side.
"""
from __future__ import annotations

import re

INK_DARK, INK_LIGHT = "#0E0C0B", "#FFFFFF"

CLUBS: dict[str, tuple[tuple[str, ...], str]] = {
    "Manchester United": (("manchester united", "man united", "man utd"), "#DA291C"),
    "Liverpool": (("liverpool",), "#C8102E"),
    "Arsenal": (("arsenal", "gunners"), "#EF0107"),
    "Chelsea": (("chelsea",), "#034694"),
    "Manchester City": (("manchester city", "man city"), "#6CABDD"),
    "Tottenham Hotspur": (("tottenham", "spurs"), "#132257"),
    "Newcastle United": (("newcastle",), "#FFFFFF"),
    "Aston Villa": (("aston villa",), "#670E36"),
    "Everton": (("everton",), "#003399"),
    "West Ham United": (("west ham",), "#7A263A"),
    "Barcelona": (("barcelona", "barca", "barça"), "#A50044"),
    "Real Madrid": (("real madrid",), "#FEBE10"),
    "Atletico Madrid": (("atletico madrid", "atlético madrid"), "#CB3524"),
    "Bayern Munich": (("bayern",), "#DC052D"),
    "Paris Saint-Germain": (("paris saint-germain", "psg"), "#004170"),
    "Juventus": (("juventus",), "#FFFFFF"),
    "AC Milan": (("ac milan",), "#FB090B"),
    "Inter Milan": (("inter milan",), "#0068A8"),
    "Gor Mahia": (("gor mahia", "k'ogalo"), "#00843D"),
    "AFC Leopards": (("afc leopards", "ingwe"), "#1E73BE"),
}

# names of clubs, for code that must not take "Gor Mahia" or "Aston Villa" for a person
NAME_WORDS = {w for names, _ in CLUBS.values() for n in names for w in n.split()} | {"fc", "afc", "sc"}


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ink_for(hex_colour: str) -> str:
    """The text colour that reads best on `hex_colour` (WCAG contrast against white vs near-black)."""
    lum = _luminance(hex_colour)
    on_white = 1.05 / (lum + 0.05)
    on_dark = (lum + 0.05) / (_luminance(INK_DARK) + 0.05)
    return INK_LIGHT if on_white >= on_dark else INK_DARK


def club_in(text: str) -> str:
    """The first club the text names ('' if none), by where it first appears."""
    low = (text or "").lower()
    best, at = "", len(low) + 1
    for club, (names, _) in CLUBS.items():
        for n in names:
            m = re.search(rf"(?<![\w'])({re.escape(n)})(?![\w'])", low)
            if m and m.start() < at:
                best, at = club, m.start()
    return best


def accent_for(post: dict) -> dict | None:
    """{"club", "colour", "ink"} for a sport story that names a known club, else None (the brand red stays).
    Politics never takes club or party colours."""
    if post.get("beat") == "politics":
        return None
    text = " ".join(str(post.get(k) or "") for k in ("who", "message", "headline", "title")) + " " + \
        " ".join(str(b) for b in post.get("beats") or [])
    club = club_in(text)
    if not club:
        return None
    colour = CLUBS[club][1]
    return {"club": club, "colour": colour, "ink": ink_for(colour)}
