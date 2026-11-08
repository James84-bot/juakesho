"""
mtaa.py — Mtaa Mode, the street brand, made with no filming and no graphics card. Sheng is the voice of the page,
never its subject.

    scene   Maisha ya Mtaa   our own cast, drawn and animated by the system, living real days in real places
                             (the plot, a matatu, the kibanda, Mathe's sitting room); the script by the AI writer
    chart   Ngoma za Wiki    the music trending on YouTube in Kenya, ranked by views per day since release

The chart is never written by AI: the songs and the views come from the YouTube Data API at the time printed on the
post. The scenes are fiction and say so on screen and in the caption. No voices yet: every line is a speech bubble,
timed as if spoken (a voice track per line can be added later on the same timeline).

    python mtaa.py chart           # today's chart, printed (needs YOUTUBE_API_KEY)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import brands
import mtaa_art

TEMPLATES = {"scene", "chart"}
DATA_TEMPLATES = {"chart"}   # built by code from a source, never by the writer
# A chart is built this close to its slot, so the views are hours old, not days (the day runs build it)
FRESH_LEAD = {"chart": dt.timedelta(hours=6)}
EAT = dt.timezone(dt.timedelta(hours=3))
UA = "MtaaModeBot/1.0 (https://james84-bot.github.io/juakesho; Kenyan culture page)"

# ---------------------------------------------------------------------------
# The cast. Name colours are checked against white bubbles and the night ground.
# ---------------------------------------------------------------------------
CAST = {
    "brayo":    {"name": "Brayo", "color": "#C3F62A", "who": "broke and endlessly optimistic; every plan needs someone else's money"},
    "sasha":    {"name": "Sasha", "color": "#FE80B8", "who": "the sharp one; screenshots everything, keeps the group's accounts, replies in one line"},
    "kevo":     {"name": "Kevo", "color": "#6FD2FF", "who": "always 'niko njiani', never arrives; lives on data bundles and excuses"},
    "dee":      {"name": "Dee", "color": "#F9B64F", "who": "seven side hustles; sells something to everyone, even at the worst moment"},
    "mathe":    {"name": "Mathe", "color": "#CEB5FF", "who": "Brayo's mum; long blessings, forwards everything, the most savage line"},
    "landlord": {"name": "Landlord", "color": "#DFDFE3", "who": "polite and warm until the 5th of the month; carries the rent book"},
}
# How each one is drawn (templates/mtaa_rig.js). Original designs; their colours echo the brand (Brayo in lime).
LOOKS = {
    "brayo":    {"skin": "#6B4226", "hair": "fade", "hairColor": "#17110E", "top": "hoodie", "topColor": "#C3F62A",
                 "trim": "#0E0E12", "sleeve": "#C3F62A", "forearm": "#C3F62A", "pants": "#2C3E66", "shoe": "#F4F4F2"},
    "sasha":    {"skin": "#5A3520", "hair": "braids", "hairColor": "#1B1210", "top": "jacket", "topColor": "#FC4AA1",
                 "tee": "#F7F7F9", "sleeve": "#FC4AA1", "forearm": "#FC4AA1", "pants": "#7FA6D6", "shoe": "#1E1E24"},
    "kevo":     {"skin": "#7A4B2A", "hair": "twists", "hairColor": "#1A120E", "top": "jersey", "topColor": "#6FD2FF",
                 "trim": "#0E2A44", "number": "7", "sleeve": "#6FD2FF", "forearm": "#7A4B2A", "pants": "#1E1E24", "shoe": "#E8452C"},
    "dee":      {"skin": "#4A2C1A", "hair": "cap", "hairColor": "#120C0A", "capColor": "#F9B64F", "top": "bomber",
                 "topColor": "#F9B64F", "trim": "#2A1C10", "sleeve": "#F9B64F", "forearm": "#F9B64F", "pants": "#3C3F2A", "shoe": "#F4F4F2"},
    "mathe":    {"skin": "#6B4226", "hair": "wrap", "hairColor": "#7B4FD0", "pattern": "#F9B64F", "top": "dress",
                 "topColor": "#7B4FD0", "sleeve": "#7B4FD0", "forearm": "#6B4226", "pants": "#6B4226", "legW": 30,
                 "shoe": "#8A5A2B", "glasses": True},
    "landlord": {"skin": "#5C3A21", "hair": "grey", "hairColor": "#C9C8CD", "top": "vest", "topColor": "#6E6A64",
                 "tee": "#F2EFE6", "tie": "#7A2E2E", "sleeve": "#F2EFE6", "forearm": "#F2EFE6", "pants": "#5B4330",
                 "shoe": "#2A1C14", "mustache": "#C9C8CD", "prop": "book"},
}


# ---------------------------------------------------------------------------
# Timing: the animation, the bubbles, the sound and the Reel's length all come from these numbers
# ---------------------------------------------------------------------------
SAY_WPS = 3.0      # words said per second (the mouth moves, the words appear)
READ_FLOOR = 1.5   # a line stays at least this long
WALK_S = 1.0       # walking in or out (the template reads it from the timeline)
HOLD_S = 1.6       # the punchline's reaction stays this long
WALK_IN_TALK = 0.45  # someone walking in starts their line this far into the walk (no dead air at the start)
SCALE = {2: 1.12, 3: 1.0}   # two people are drawn bigger than three
W_FRAME = mtaa_art.W
ACTIONS = ("none", "point", "shrug", "facepalm", "phone", "knock", "wave", "cross", "think", "laugh", "angry", "cheer",
           "beg", "walk_in", "walk_out")
FACES = ("neutral", "happy", "laugh", "sad", "angry", "shock", "smug")
# a name's colour on a white bubble (contrast above 4.5:1)
NAME_ON_WHITE = {"brayo": "#4D6A02", "sasha": "#B70C6C", "kevo": "#0B6E9E", "dee": "#9A5B00", "mathe": "#6A3FC0",
                 "landlord": "#4B4847"}


def scene_timeline(post: dict) -> dict:
    """When each line starts, when its words are all said, when it ends; who walks in and out and when; where each
    one stands; the punchline (the last line) the camera cuts in on; the end."""
    lines, t = [], 0.15
    for l in post.get("lines") or []:
        words = max(1, len(str(l.get("text", "")).split()))
        walk_in = l.get("do") == "walk_in"
        start = round(t + (WALK_IN_TALK if walk_in else 0), 2)   # they start talking as they arrive
        talk = 0.2 + words / SAY_WPS
        end = round(start + max(READ_FLOOR, talk + 0.7), 2)
        lines.append({"who": l.get("who"), "text": str(l.get("text", "")), "do": l.get("do") or "none",
                      "face": l.get("face") or "neutral", "react": l.get("react") or "", "start": start,
                      "talk_end": round(start + talk, 2), "end": end})
        t = end + (WALK_S if l.get("do") == "walk_out" else 0) + 0.12
    keys = list(dict.fromkeys(post.get("cast") or [l["who"] for l in lines]))
    spots = mtaa_art.SPOTS.get(len(keys), mtaa_art.SPOTS[3])
    seated = post.get("place") in mtaa_art.SEATED
    cast = []
    for i, k in enumerate(keys):
        mine = [l for l in lines if l["who"] == k]
        first_in = next((l for l in mine if l["do"] == "walk_in"), None)
        scale = SCALE.get(len(keys), 1.0)
        out = next((l for l in mine if l["do"] == "walk_out"), None)
        x = spots[i]
        side = -1 if x < 540 else 1   # walk in from (and out to) their own side of the frame, from just past its edge
        cast.append({"key": k, "x": x, "scale": scale, "seated": seated and not first_in, "seed": i * 3 + 1,
                     "facing0": 1 if x < 540 else -1, "walk": (W_FRAME + 150 - x) if side > 0 else (x + 150),
                     "enter": round(max(0.0, first_in["start"] - WALK_IN_TALK), 2) if first_in else None, "from": side,
                     "exit": out["end"] if out else None, "to": side,
                     "acts": [{"do": l["do"], "at": round(l["start"] + 0.08, 2)} for l in mine
                              if l["do"] not in {"walk_in", "walk_out", "none"}]})
    end = round(t + HOLD_S, 2)
    punch = {"who": lines[-1]["who"], "at": lines[-1]["start"]} if len(lines) >= 3 else None
    if punch and next((c for c in cast if c["key"] == punch["who"] and c["exit"] is not None
                       and c["exit"] <= lines[-1]["end"]), None):
        punch = None   # never cut in on someone walking out of the frame
    return {"lines": lines, "cast": cast, "end": end, "punch": punch, "floor": mtaa_art.FLOOR, "walk_s": WALK_S}


CHART_T = {"head": 0.1, "first_row": 1.1, "row_s": 1.25}


def chart_timeline(n: int) -> dict:
    """Rows land from the bottom of the chart (#10) up to #1, then #1 lights up."""
    rows = [round(CHART_T["first_row"] + (n - 1 - i) * CHART_T["row_s"], 2) for i in range(n)]   # index 0 is #1
    top = round(max(rows) + 0.6, 2) if rows else 1.0
    return {"rows": rows, "top": top, "end": round(top + 3.4, 2)}


def duration(post: dict) -> float:
    """The Reel's length for these templates (video.py): the template's own timeline, never cut at 14 s."""
    if post["template"] == "scene":
        return scene_timeline(post)["end"]
    if post["template"] == "chart":
        return chart_timeline(len(post.get("songs") or []))["end"]
    raise ValueError(post["template"])


def still_time(post: dict) -> float | None:
    """The moment of the still frame and the Reel's cover: a scene's hook line, fully said (None: the last frame)."""
    if post.get("template") != "scene":
        return None
    lines = scene_timeline(post)["lines"]
    return round(lines[0]["end"] - 0.05, 2) if lines else None


SOUND_OF = {"knock": "knock", "facepalm": "slap", "phone": "buzz", "cheer": "whoosh", "walk_in": "steps", "walk_out": "steps"}


def cues(post: dict) -> list[tuple[float, str]]:
    """The sound design's hits: (time, kind). A scene: what people do (a knock, a slap, a phone, footsteps), a soft
    pop as each line appears, a hit on the punchline. A chart: a pop per row, a reveal on #1."""
    if post["template"] == "chart":
        tl = chart_timeline(len(post.get("songs") or []))
        return [(x, "pop") for x in sorted(tl["rows"])] + [(tl["top"], "reveal")]
    tl = scene_timeline(post)
    out = []
    for c in tl["cast"]:
        if c["enter"] is not None:
            out.append((c["enter"], "steps"))
        if c["exit"] is not None:
            out.append((c["exit"], "steps"))
    for i, l in enumerate(tl["lines"]):
        out.append((l["start"], "hit" if tl["punch"] and i == len(tl["lines"]) - 1 else "pop"))
        if l["do"] in SOUND_OF and l["do"] not in {"walk_in", "walk_out"}:
            out.append((l["start"] + 0.1, SOUND_OF[l["do"]]))
    return sorted(out)


def context(post: dict) -> dict:
    """What the templates need beyond the post's own fields (render.build_html adds it)."""
    if post["template"] == "scene":
        from markupsafe import Markup
        tl = scene_timeline(post)
        keys = [c["key"] for c in tl["cast"]]
        return {"scene": tl, "looks": {k: LOOKS[k] for k in keys if k in LOOKS},
                "backdrop": Markup(mtaa_art.backdrop(post.get("place") or "plot")),
                "names": {k: CAST[k]["name"] for k in keys if k in CAST},
                "colors": {k: NAME_ON_WHITE.get(k, "#141418") for k in keys},
                "still_t": still_time(post) or 0.0, "end": tl["end"]}
    if post["template"] == "chart":
        tl = chart_timeline(len(post.get("songs") or []))
        return {"T": CHART_T, "row_at": tl["rows"], "top_at": tl["top"], "end": tl["end"]}
    return {}


# ---------------------------------------------------------------------------
# Network (stdlib only, so the day runs need nothing installed)
# ---------------------------------------------------------------------------
def _get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


TAGS = {"chart": "#MtaaMode #KenyanMusic #NgomaZaWiki", "scene": "#MtaaMode #Nairobi"}


# ---------------------------------------------------------------------------
# Ngoma za Wiki (YouTube, most-popular music for Kenya)
# ---------------------------------------------------------------------------
YT = "https://www.googleapis.com/youtube/v3/videos?"
LATIN = re.compile(r"^[ -ɏ‘-‟–—…]+$")   # what the fonts draw
NOISE = re.compile(r"\s*[\(\[][^)\]]*\b(official|video|audio|lyrics?|visuali[sz]er|music|clip|4k|hd|dance)\b[^)\]]*[\)\]]\s*", re.I)


def _title_case(s: str) -> str:
    """ALL-CAPS names as people write them ('NIWA YIULU' -> 'Niwa Yiulu'); anything already mixed-case is kept."""
    if s.upper() != s or not re.search(r"[A-Z]{2}", s):
        return s.strip()
    return " ".join(w.lower() if w.lower() in {"x", "ft", "ft.", "feat.", "feat"} else w.capitalize() for w in s.split()).strip()


FEAT = re.compile(r"\s*[\(\[]?\s*\b(?:feat\.?|ft\.?|featuring)\s+([^)\]]+?)\s*[\)\]]?\s*$", re.I)


def split_title(title: str, channel: str) -> tuple[str, str]:
    """(artist, song) from a music video title, as a chart prints it:
    'BIEN - I'll Be Okay (Official Music Video)'            -> ('Bien', "I'll Be Okay")
    'NIWA YIULU - WILBERFORCE MUSYOKA' (channel Wilberforce) -> ('Wilberforce Musyoka', 'Niwa Yiulu')
    'Zzero Sufuri   Otero Ft  Toxic Lyrikali' (no dash)      -> ('Zzero Sufuri ft Toxic Lyrikali', 'Otero')"""
    t = NOISE.sub(" ", title)
    t = re.sub(r"\s*\|.*$", "", t)          # "Song | Album" -> "Song"
    t = re.sub(r"\s+", " ", t).strip(" -")
    ch = re.sub(r"\b(official|music|tv|vevo)\b", "", channel, flags=re.I).strip(" -")
    m = re.match(r"^(.{2,160}?)\s+[-\u2013\u2014]\s+(.{1,120})$", t)   # the first dash: "Artists - Song"
    if m:
        artist, song = m.group(1), m.group(2)
        if ch and ch.lower() in song.lower() and ch.lower() not in artist.lower():   # "SONG - ARTIST"
            artist, song = song, artist
    elif ch and t.lower().startswith(ch.lower()):   # "ARTIST-SONG" or "Artist Song ft Other"
        artist, song = t[:len(ch)], t[len(ch):].strip(" -\u2013")
    else:
        artist, song = ch or channel, t
    f = FEAT.search(song)
    if f and song[:f.start()].strip():   # a featured artist belongs with the artist
        artist, song = f"{artist} ft {f.group(1)}", song[:f.start()]
    artist = re.sub(r"\b(?:feat\.?|ft\.?|featuring)\s+", "ft ", _title_case(artist), flags=re.I)
    song = re.sub(r"\s*[-\u2013]\s*$", "", song).strip()
    dash = lambda x: re.sub(r"\s*[\u2013\u2014]\s*", " - ", re.sub(r"\s+", " ", x)).strip(" ,;-")
    artist, song = dash(artist), dash(_title_case(song))
    # never a cut name: the screen ellipsizes a long one. A split that leaves nothing sensible falls back to the channel
    # and the whole title, so a song is never shown as ", Xduppy & Dj Maphorisa"
    if not song or not artist or not re.match(r"[\w'\u2018\u201C\"(]", song) or re.match(r"(?i)(ft|feat|featuring)\b", song):
        artist, song = dash(ch or channel), dash(_title_case(t))
    return artist[:120], song[:120]


def chart_songs(key: str | None = None, now: dt.datetime | None = None, get=None, n: int = 10,
                max_age_days: int = 60) -> tuple[list[dict], str]:
    """Up to n songs from YouTube's most-popular music list for Kenya, ranked by views per day since release.
    Returns (songs, the time the views were read, as printed on the post)."""
    key = key or os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no YOUTUBE_API_KEY")
    now = now or dt.datetime.now(EAT)
    get = get or _get
    q = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": "KE", "videoCategoryId": "10",
         "maxResults": 50, "key": key}
    items = json.loads(get(YT + urllib.parse.urlencode(q))).get("items", [])
    songs = []
    for v in items:
        s, st = v.get("snippet", {}), v.get("statistics", {})
        if not LATIN.match(s.get("title", "")) or not LATIN.match(s.get("channelTitle", "")):
            continue   # a title the fonts can't draw is left out, never shown as boxes
        pub = dt.datetime.fromisoformat(s["publishedAt"].replace("Z", "+00:00"))
        days = max((now - pub).total_seconds() / 86400, 1.0)
        if days > max_age_days or "viewCount" not in st:
            continue
        artist, song = split_title(s["title"], s.get("channelTitle", ""))
        if not artist or not song:
            continue   # nothing readable to show
        views = int(st["viewCount"])
        songs.append({"artist": artist, "song": song, "title": s["title"], "views": views, "per_day": round(views / days),
                      "days": round(days, 1), "url": f"https://www.youtube.com/watch?v={v['id']}",
                      "channel": s.get("channelTitle", "")})
    songs.sort(key=lambda x: -x["per_day"])
    return songs[:n], now.astimezone(EAT).strftime("%-d %b %Y, %H:%M EAT")


def short_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def fit(text: str, cap: int) -> str:
    """What fits on a chart row: the whole text, or cut at a word or comma before `cap` with an ellipsis (the
    caption keeps every name in full)."""
    text = str(text).strip()
    if len(text) <= cap:
        return text
    cut = text[:cap - 1]
    cut = cut[:max(cut.rfind(" "), cut.rfind(","))] if max(cut.rfind(" "), cut.rfind(",")) > cap // 2 else cut
    return cut.rstrip(" ,&-x") + "\u2026"


ROW_SONG, ROW_ARTIST = 30, 42   # characters a chart row shows (Inter Tight 34px, Inter 25px, in 600px)


def chart_post(slot: dict, songs: list[dict], as_of: str) -> dict:
    lines = [f"{i + 1}. {s['artist']} - {s['song']} ({short_number(s['per_day'])} views a day)" for i, s in enumerate(songs)]
    cap = ("Ngoma za Wiki: what Kenya is playing on YouTube right now.\n\n" + "\n".join(lines)
           + "\n\nWhich one is on repeat for you? Send this to the friend who won't stop playing it."
           + f"\n\nRanked by views per day since release, from YouTube's most-popular music list for Kenya, {as_of}."
           + f"\n\n{TAGS['chart']}")
    for s in songs:
        s["per_day_text"] = short_number(s["per_day"])
        s["song_row"], s["artist_row"] = fit(s["song"], ROW_SONG), fit(s["artist"], ROW_ARTIST)
    return {**slot, "songs": songs, "as_of": as_of, "caption": cap,
            "source": f"YouTube Data API, most-popular music videos for Kenya, read {as_of}",
            "shorts_title": "Ngoma za Wiki: what Kenya is playing right now #Shorts",
            "material": {"kind": "chart", "as_of": as_of}}


# ---------------------------------------------------------------------------
# Maisha ya Mtaa: the scene, written by the AI writer
# ---------------------------------------------------------------------------
POLITICS = re.compile(r"\b(ruto|raila|gachagua|kalonzo|uhuru|matiang'?i|sakaja|mudavadi|wetang'?ula|kindiki|kenyatta|odinga|"
                      r"uda|odm|jubilee|azimio|kenya kwanza|wiper|dcp|president|rais|serikali|government|gava|parliament|"
                      r"bunge|senator|governor|gavana|mca|mheshimiwa|mbunge|minister|waziri|election|uchaguzi|kura|vote|"
                      r"campaign|politic\w*|siasa|finance bill|maandamano|protest\w*|tax(es)?|ushuru|zakayo|kasongo)\b", re.I)
# Communities with their Swahili prefixes (wakikuyu, mjaluo, wakamba). Names that are mostly places in a scene
# (Meru, Embu, Kisii town, Turkana, Maasai Mara) are left to the editor, so a matatu to Embu is not blocked.
TRIBE = re.compile(r"\b(?:wa|m|mu|ji|a)?(kikuyu|gikuyu|luo|kalenjin|luhya|luyha|mijikenda)\b|"
                   r"\b(wakamba|mkamba|akamba|wakisii|mkisii|abagusii|wameru|mmeru|waembu|mjaluo|jaluo|mjango|majango|"
                   r"kao|kabila|makabila|tribe|tribes|tribal|ethnic\w*)\b", re.I)
RELIGION_TARGET = re.compile(r"\b(pastor|pasta|church|kanisa|mosque|msikiti|imam|sheikh|bishop|askofu|prophet|nabii|"
                             r"bible|biblia|quran|koran|tithe|sadaka|sermon)\b", re.I)
VICES = re.compile(r"\b(sex|ngono|condom|beer|pombe|keg|chang'?aa|mzinga|weed|bangi|ganja|miraa|veve|muguka|drunk|"
                   r"walevi|mlevi|betting|kamari|odds|jackpot|loan app|fuliza|okash)\b", re.I)
REAL_PEOPLE = re.compile(r"\b(bien|sauti sol|nameless|khaligraph|otile|nadia|akothee|eric omondi|terence|jalang'?o|"
                         r"diamond|zuchu|harmonize|safaricom|airtel|kplc|kenya power|equity|kcb|ncba|naivas|quickmart|"
                         r"carrefour|java|kfc|chicken inn)\b", re.I)


LIMITS = {"title": 40, "text": 80, "words": 13, "lines": (4, 8), "total_words": 75}


def check(post: dict) -> tuple[list[str], list[str]]:
    """The street checks for these templates: (errors, warnings). guard.check calls this."""
    errs, warns = [], []
    t = post.get("template")
    if t == "scene":
        title = str(post.get("title") or "")
        if not 3 <= len(title) <= LIMITS["title"]:
            errs.append(f"'title' must be 3-{LIMITS['title']} chars")
        if post.get("place") not in mtaa_art.PLACES:
            errs.append(f"'place' must be one of {list(mtaa_art.PLACES)}")
        cast = post.get("cast")
        if not isinstance(cast, list) or not 2 <= len(set(cast)) <= 3 or any(k not in CAST for k in cast):
            errs.append(f"'cast' needs 2-3 of {sorted(CAST)}")
            cast = []
        lines = post.get("lines")
        lo, hi = LIMITS["lines"]
        if not isinstance(lines, list) or not lo <= len(lines) <= hi:
            errs.append(f"'lines' needs {lo}-{hi} lines")
            return errs, warns
        spoke = set()
        for i, l in enumerate(lines):
            if not isinstance(l, dict) or l.get("who") not in (cast or CAST):
                errs.append(f"lines[{i}]: 'who' must be someone in the cast")
                continue
            spoke.add(l["who"])
            txt = str(l.get("text") or "").strip()
            if not txt:
                errs.append(f"lines[{i}] is empty")
            elif len(txt) > LIMITS["text"]:
                errs.append(f"lines[{i}] is {len(txt)} chars (max {LIMITS['text']})")
            elif len(txt.split()) > LIMITS["words"]:
                errs.append(f"lines[{i}] is {len(txt.split())} words (max {LIMITS['words']})")
            if re.search(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", txt) or "#" in txt or "http" in txt.lower():
                errs.append(f"lines[{i}] has an emoji, a hashtag or a link")
            if (l.get("do") or "none") not in ACTIONS:
                errs.append(f"lines[{i}]: 'do' must be one of {list(ACTIONS)}")
            for f in ("face", "react"):
                if l.get(f) and l[f] not in FACES:
                    errs.append(f"lines[{i}]: '{f}' must be one of {list(FACES)}")
        if cast and set(cast) - spoke:
            errs.append("everyone in the cast says at least one line")
        ins = [l["who"] for l in lines if isinstance(l, dict) and l.get("do") == "walk_in"]
        outs = [l["who"] for l in lines if isinstance(l, dict) and l.get("do") == "walk_out"]
        for who in set(ins):
            first = next(i for i, l in enumerate(lines) if isinstance(l, dict) and l.get("who") == who)
            if lines[first].get("do") != "walk_in" or ins.count(who) > 1:
                errs.append(f"{who} walks in on their first line only")
        for who in set(outs):
            after = [l for l in lines[[i for i, l in enumerate(lines) if isinstance(l, dict) and l.get("who") == who
                                       and l.get("do") == "walk_out"][0] + 1:] if isinstance(l, dict) and l.get("who") == who]
            if after or outs.count(who) > 1:
                errs.append(f"{who} walks out on their last line only")
        if post.get("place") in mtaa_art.SEATED and ins + outs:
            errs.append("nobody walks in or out of a moving matatu")
        words = sum(len(str(l.get("text", "")).split()) for l in lines if isinstance(l, dict))
        if words > LIMITS["total_words"]:
            errs.append(f"the scene is {words} words (max {LIMITS['total_words']}): it must play in under 35 seconds")
        text = " ".join([title, str(post.get("caption") or "")] + [str(l.get("text", "")) for l in lines if isinstance(l, dict)])
        for rx, why in ((POLITICS, "politics"), (TRIBE, "tribe or ethnicity"), (RELIGION_TARGET, "religion as the target"),
                        (VICES, "sex, alcohol, drugs, betting or loans"), (REAL_PEOPLE, "a real person or brand")):
            m = rx.search(text)
            if m:
                errs.append(f"{why} ('{m.group(0)}'): Mtaa Mode never goes there")
        if not post.get("caption"):
            errs.append("missing 'caption'")
    elif t == "chart":
        songs = post.get("songs")
        if not isinstance(songs, list) or not 5 <= len(songs) <= 10:
            errs.append("'songs' needs 5-10 songs")
        elif any(not s.get("artist") or not s.get("song") or not isinstance(s.get("per_day"), int) for s in songs):
            errs.append("every song needs an artist, a title and its views per day")
        if not post.get("as_of"):
            errs.append("missing 'as_of' (when the views were read)")
    return errs, warns


SCENE_RULES = """You write MAISHA YA MTAA scenes for Mtaa Mode: short animated cartoon scenes in which our own fixed
cast live a real day in Nairobi. The system draws and animates them: you write who is there, where, what each says
(shown in a speech bubble) and what they do while saying it. Open in the middle of a real moment, every line moves it
forward, the turn comes near the end, and the LAST line is the punchline (the camera cuts in on whoever says it).

PLACES (pick the one the moment happens in): plot (the courtyard of a rental block: doors, a washing line, a
jerrycan), matatu (inside a moving matatu: everyone is seated, nobody walks in or out), kibanda (a roadside kiosk run
by its owner, no waiters: chai, mandazi, chapati, a bench), nyumbani (Mathe's sitting room). What is said must fit the
place and what the cast can see there.

KISWAHILI AND SHENG MUST BE CORRECT. Check every verb: kununua is to buy, kuuza to sell, kutuma to send, kukopa to
borrow, kukopesha to lend ("Nitumie fifty bob", "Nikopeshe fifty bob", never "Niuzie fifty bob" for asking for
money). A line that would make a Nairobian say "hiyo si Kiswahili" ruins the joke.
ACTIONS (`do`, what the speaker does on that line): none, point, shrug, facepalm, phone (on a call, holds until their
next action), knock, wave, cross (arms folded, holds), think, laugh, angry (hands on hips, holds), cheer, beg,
walk_in (only on someone's first line: they arrive), walk_out (only on someone's last line: they leave).
FACES (`face` for the speaker, optional `react` for everyone else during that line): neutral, happy, laugh, sad,
angry, shock, smug.

FORMAT (JSON only). For each slot, return:
{"id": "<the slot id>", "template": "scene", "title": "<the moment in a few words, max 40 chars, in the page's voice,
 e.g. 'Tarehe 5 kwa ploti', 'Matatu ya 7am'>", "place": "...", "cast": ["<2 or 3 cast keys>"],
 "lines": [{"who": "<cast key>", "text": "<max 13 words>", "do": "...", "face": "...", "react": "<optional>"}, ...4 to 8],
 "caption": "<1-2 short lines that set it up without giving the punchline away, then a question people will answer in
 the comments; end with: #MtaaMode #Nairobi>",
 "situation": "<3-6 words naming the situation, for our records>"}
Everyone in the cast speaks. The whole scene stays under 75 words so it plays in under 35 seconds. Every scene is a
DIFFERENT situation and most use a different place from the one before."""


def writer_brief() -> str:
    cast = "\n".join(f"- {k}: {v['name']}, {v['who']}" for k, v in CAST.items())
    own = (brands.HOME / "writer.md")
    brief = own.read_text(encoding="utf-8") if own.exists() else ""
    return f"{brief}\n\nCAST KEYS\n{cast}\n\n{SCENE_RULES}"


SCORE_RULES = """You are the head writer of a Kenyan street comedy page. Score each animated scene 1-10 on:
funny (does the last line land as a real punchline?), true (would a young Nairobian say 'this is literally us'?),
voice (natural Nairobi speech: Sheng/Kiswahili/English mixed correctly, characters stay in character; any word
used wrongly, such as "niuzie" (sell me) where "nitumie" (send me) is meant, caps voice at 5 and the note names it;
anything that does not fit the place, such as a waiter at a kibanda, caps true at 6),
clean (laughs at the situation, never at a tribe, religion, body, gender, poverty or a real person).
Be strict: most scenes are a 6. Return ONLY JSON: {"scores": [{"id": "...", "funny": n, "true": n, "voice": n,
"clean": n, "note": "<one line: what would make the punchline hit harder>"}]}"""
SCORE_BAR = 7.0
CLEAN_BAR = 8.0   # auto-approval also needs the editor sure it is clean for everyone
KEEP = ("title", "place", "cast", "lines", "caption", "situation")


def _score(posts: list[dict], call) -> dict[str, dict]:
    import draft as drafter
    body = json.dumps([{"id": p["id"], **{k: p.get(k) for k in ("title", "place", "cast", "lines")}} for p in posts],
                      ensure_ascii=False)
    try:
        got = drafter.extract_json(call(SCORE_RULES, body, 3000))
    except Exception as e:
        print(f"  scene scoring skipped: {e}")
        return {}
    out = {}
    for s in got.get("scores", []):
        try:
            avg = sum(float(s[k]) for k in ("funny", "true", "voice", "clean")) / 4
        except (KeyError, TypeError, ValueError):
            continue
        out[s.get("id")] = {"avg": round(avg, 2), "note": str(s.get("note") or "")[:200],
                            **{k: float(s[k]) for k in ("funny", "true", "voice", "clean")}}
    return out


def write_scenes(slots: list[dict], call=None, taken: list[str] | None = None) -> list[dict]:
    """The scenes for these slots: written, checked, scored; a weak or failing one gets one rewrite with the note,
    and the rewrite is kept only when it passes and scores at least as well."""
    import draft as drafter
    call = call or (lambda system, user, n: drafter.call_claude(system, user, max_tokens=n))
    system = writer_brief()
    avoid = ("\nSituations already used recently (pick others): " + "; ".join(taken[-30:])) if taken else ""
    user = ("Write one scene for each slot. Slots: " + json.dumps([{"id": s["id"], "publish_at": s.get("publish_at")}
                                                                   for s in slots], ensure_ascii=False)
            + avoid + '\nReturn ONLY JSON: {"posts": [...]}')
    try:
        got = drafter.extract_json(call(system, user, 7000)).get("posts", [])
    except Exception as e:
        print(f"  scenes not written: {e}")
        got = []
    by_id = {p.get("id"): p for p in got if isinstance(p, dict)}
    take = lambda s, p: {**s, **{k: p[k] for k in KEEP if k in p}}
    posts = [take(s, by_id[s["id"]]) if s["id"] in by_id else {**s} for s in slots]
    scores = _score([p for p in posts if p.get("lines")], call)
    redo = []
    for p in posts:
        errs, _ = check(p)
        sc = scores.get(p["id"])
        if errs or not sc or sc["avg"] < SCORE_BAR:
            redo.append((p, errs, sc))
    if redo:
        notes = [{"id": p["id"], "your_draft": {k: p.get(k) for k in KEEP},
                  "problems": errs, "editor": (sc or {}).get("note", "no score")} for p, errs, sc in redo]
        try:
            again = drafter.extract_json(call(system, "Rewrite these scenes, fixing every problem and taking the "
                                              "editor's note. Keep each id. " + json.dumps(notes, ensure_ascii=False)
                                              + '\nReturn ONLY JSON: {"posts": [...]}', 7000)).get("posts", [])
        except Exception as e:
            print(f"  scene rewrite skipped: {e}")
            again = []
        fixed = {p.get("id"): p for p in again if isinstance(p, dict)}
        cands = {p["id"]: take(p, fixed[p["id"]]) for p, _, _ in redo if p["id"] in fixed}
        rescored = _score(list(cands.values()), call)
        for i, p in enumerate(posts):
            cand = cands.get(p["id"])
            if cand:
                old = scores.get(p["id"], {}).get("avg", 0)
                new = rescored.get(p["id"], {}).get("avg", 0)
                if not check(cand)[0] and (new >= old or check(p)[0]):
                    posts[i], scores[p["id"]] = cand, rescored.get(p["id"], scores.get(p["id"], {}))
    for p in posts:
        p["critic"] = scores.get(p["id"]) or {}
        p["shorts_title"] = (str(p.get("title") or "Maisha ya Mtaa") + " #Shorts")[:100]
        cap = str(p.get("caption") or "").strip()
        if cap and "fictional" not in cap.lower():
            tags = re.search(r"(\s*(#\w+\s*)+)$", cap)
            body, tail = (cap[:tags.start()], cap[tags.start():]) if tags else (cap, "\n\n" + TAGS["scene"])
            p["caption"] = f"{body.rstrip()}\n\nAnimated skit: characters are fictional.{tail}"
    return posts


# ---------------------------------------------------------------------------
# Drafting (draft.draft_week hands these templates here)
# ---------------------------------------------------------------------------
SITUATIONS = brands.STATE / "skit_situations.json"   # what the scenes were about, so the next weeks pick others
BATCH = 6   # scenes per writer call: a call that has to return two dozen comes back cut short or samey


def auto_problem(p: dict) -> str:
    """'' when the system may post this by itself (pipeline.auto_ok), else why it waits for the owner's tap."""
    if p.get("template") == "chart":
        return "" if isinstance(p.get("material"), dict) and p.get("songs") else "no chart data behind it"
    c = p.get("critic") or {}
    if c.get("avg") is None:
        return "the scene editor's score is missing"
    if c["avg"] < SCORE_BAR:
        return f"the scene editor scored it {c['avg']} (the bar is {SCORE_BAR})"
    if c.get("clean", 0) < CLEAN_BAR:
        return "the editor was not sure it is clean for everyone"
    return ""


def _situations() -> list[str]:
    try:
        return [str(x) for x in json.loads(SITUATIONS.read_text(encoding="utf-8"))][-80:]
    except (OSError, ValueError):
        return []


def draft(slots: list[dict], mock: bool = False, call=None, get=None, now: dt.datetime | None = None,
          taken: list[dict] | None = None, remember: bool = True) -> tuple[list[dict], list[tuple[dict, str]]]:
    """(posts, held): the chart built from YouTube, the scenes written. A slot with no honest material is held with
    the reason; a source that is down is never written around. remember=False (samples): the situations used are
    not kept, so samples never take a situation away from the real weeks."""
    posts, held = [], []
    charts = [s for s in slots if s["template"] == "chart"]
    if charts:
        try:
            songs, as_of = chart_songs(get=get, now=now) if not mock else (_mock_songs(), "1 Jan 2026, 12:00 EAT")
        except Exception as e:
            songs, as_of = [], ""
            for s in charts:
                held.append((s, f"the YouTube chart could not be read: {str(e)[:120]}"))
            charts = []
        for s in charts:
            if len(songs) < 5:
                held.append((s, f"only {len(songs)} songs on YouTube's Kenya list could be shown"))
            else:
                posts.append(chart_post(s, [dict(x) for x in songs], as_of))
    scenes = sorted([s for s in slots if s["template"] == "scene"], key=lambda s: s["publish_at"])
    if scenes:
        if mock:
            posts += [{**s, **MOCK_SCENE} for s in scenes]
        else:
            used = _situations() + [str(p.get("situation") or p.get("title") or "") for p in (taken or [])
                                    if p.get("template") == "scene"]
            for k in range(0, len(scenes), BATCH):
                done = write_scenes(scenes[k:k + BATCH], call=call, taken=used)
                posts += done
                used += [str(p.get("situation") or p.get("title") or "") for p in done if p.get("lines")]
            if not remember:
                return posts, held
            SITUATIONS.parent.mkdir(parents=True, exist_ok=True)
            SITUATIONS.write_text(json.dumps([u for u in dict.fromkeys(u for u in used if u)][-80:], ensure_ascii=False,
                                             indent=1), encoding="utf-8")
    return posts, held


def _mock_songs() -> list[dict]:
    return [{"artist": f"Artist {i}", "song": f"Song {i}", "views": 100000 * (11 - i), "per_day": 10000 * (11 - i),
             "days": 10.0, "url": "https://www.youtube.com/watch?v=x", "channel": f"Artist {i}"} for i in range(1, 11)]


MOCK_SCENE = {"title": "Rent day (layout test)", "place": "plot", "cast": ["brayo", "landlord"],
              "lines": [{"who": "landlord", "text": "Layout test line one.", "do": "walk_in", "face": "happy"},
                        {"who": "brayo", "text": "Layout test line two.", "do": "shrug", "face": "neutral"},
                        {"who": "landlord", "text": "Layout test line three.", "do": "point", "face": "angry"},
                        {"who": "brayo", "text": "Layout test line four.", "do": "facepalm", "face": "sad", "react": "smug"}],
              "caption": "Layout test.\n\nAnimated skit: characters are fictional.\n\n#MtaaMode #Nairobi"}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "chart":
        songs, as_of = chart_songs()
        print(as_of)
        for i, s in enumerate(songs):
            print(f"  {i + 1}. {s['artist']} - {s['song']} | {s['per_day']}/day | {s['views']} views in {s['days']} days")
    else:
        print(__doc__)
