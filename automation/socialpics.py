"""
socialpics.py — a photo the person in the story posted themselves, when the news has none of them.

22 Nov: a post about Bien's new album showed concert stock footage and a stranger's concert, because the album
report's only picture was the cover art. "If the headline is about Bien use Bien's image ... what people have
posted." The person's own public Instagram is the next place to look:

  1. their Instagram username comes from Wikidata (property P2003), never guessed from the name;
  2. their recent public posts come from Instagram's own Business Discovery API, with our account's token
     (it works for business and creator accounts, which is what artists, politicians and clubs use);
  3. each picture must be a recent plain photo (not a flyer or cover art: picture.outlet_edit), sharp, and seen
     to fit the story (picture.fits) before it is used. Credited "Photo: @username on Instagram".

Never raises: None when anything is missing (no Wikidata entry, no username, a personal account, no token).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request

WIKIDATA = "https://www.wikidata.org/w/api.php"
UA = "KenyaOnRecord/1.0 (https://github.com/James84-bot/juakesho)"
RECENT_DAYS = 60    # an older post is a file photo of a different moment
NOTES: list[str] = []


def _note(msg: str) -> None:
    NOTES.append(msg)
    print(msg)


def _get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def instagram_username(name: str, get=_get_json) -> str | None:
    """The person's Instagram username as Wikidata records it (P2003), for a human (P31 = Q5) whose label or alias
    carries the name's last word. Wikidata's full-text search is used, which ignores accents and hyphens
    ("Bien Aime Baraza" finds "Bien-Aimé Baraza") and can ask only for people that have a username at all.
    None when Wikidata has no such person or no username."""
    words = re.findall(r"[a-z'-]{3,}", _plain(name).replace("-", " "))
    if not words:
        return None
    q = {"action": "query", "list": "search", "srnamespace": 0, "srlimit": 5, "format": "json",
         "srsearch": f"{name} haswbstatement:P31=Q5 haswbstatement:P2003"}
    ids = [x["title"] for x in get(f"{WIKIDATA}?{urllib.parse.urlencode(q)}").get("query", {}).get("search", [])]
    if not ids:
        q2 = {"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 5, "format": "json"}
        ids = [x["id"] for x in get(f"{WIKIDATA}?{urllib.parse.urlencode(q2)}").get("search", [])]
    if not ids:
        _note(f"    Wikidata: nobody found for '{name}'")
        return None
    ents = get(f"{WIKIDATA}?{urllib.parse.urlencode({'action': 'wbgetentities', 'ids': '|'.join(ids), 'props': 'claims|labels|aliases', 'languages': 'en', 'format': 'json'})}").get("entities", {})
    for qid in ids:   # search order: the best match first
        e = ents.get(qid, {})
        claims = e.get("claims", {})
        human = any(c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5" for c in claims.get("P31", []))
        names = [e.get("labels", {}).get("en", {}).get("value", "")] + [a.get("value", "") for a in e.get("aliases", {}).get("en", [])]
        plain = [_plain(n).replace("-", " ") for n in names]
        handle = next((c.get("mainsnak", {}).get("datavalue", {}).get("value") for c in claims.get("P2003", [])), None)
        _note(f"    Wikidata {qid}: {names[0] or '?'} (person: {human}, Instagram: {handle or 'none'})")
        if not human or not any(re.search(rf"\b{re.escape(words[-1])}\b", n) for n in plain):
            continue
        if isinstance(handle, str) and re.fullmatch(r"[A-Za-z0-9._]{1,30}", handle):
            return handle
    return None


NOT_HANDLES = {"p", "reel", "reels", "tv", "explore", "stories", "accounts", "about", "developer", "legal", "direct",
               "instagram", "embed", "web", "static"}


def handle_in_pages(pages: list[str], name: str) -> str | None:
    """An Instagram username that news reports about the person link to or embed ("A post shared by Bien
    (@bienaimesol)"), when Wikidata has none. Only a username that carries one of their names counts: a news
    site's own account sits in every page footer and never does."""
    words = [w for w in re.findall(r"[a-z]{4,}", _plain(name))]
    seen: dict[str, int] = {}
    for page in pages:
        found = re.findall(r"instagram\.com/([A-Za-z0-9._]{2,30})", page) + re.findall(r"\(@([A-Za-z0-9._]{2,30})\)", page)
        for h in found:
            h = h.rstrip(".")
            if h.lower() in NOT_HANDLES or not any(w in h.lower() for w in words):
                continue
            seen[h] = seen.get(h, 0) + 1
    return max(seen, key=seen.get) if seen else None


def recent_posts(username: str, graph_get, ig_user: str) -> list[dict]:
    """Their newest public posts that are pictures: [{url, permalink, timestamp, caption}], newest first."""
    media = "media.limit(15){media_type,media_url,permalink,timestamp,caption}"
    got = graph_get(ig_user, {"fields": f"business_discovery.username({username}){{{media}}}"})
    items = (((got.get("business_discovery") or {}).get("media") or {}).get("data")) or []
    out = []
    for m in items:
        if m.get("media_type") in {"IMAGE", "CAROUSEL_ALBUM"} and m.get("media_url"):
            out.append({"url": m["media_url"], "permalink": m.get("permalink", ""), "timestamp": m.get("timestamp", ""),
                        "caption": str(m.get("caption") or "")[:200]})
    return out


def _graph_get(path: str, fields: dict) -> dict:
    version = os.environ.get("META_GRAPH_VERSION", "v26.0")
    q = urllib.parse.urlencode({**fields, "access_token": os.environ["META_ACCESS_TOKEN"].strip()})
    return _get_json(f"https://graph.facebook.com/{version}/{path}?{q}")


def their_photo(post: dict, names: list[str], story: str, fetch, graph_get=None, get=_get_json,
                pages: list[str] | None = None) -> tuple[bytes, dict] | None:
    """A recent photo the person posted themselves that fits `story`, with its credit. `names`: what they are
    called, most complete first ("Bien Aime Baraza", "Aime Baraza"); `fetch(url) -> bytes`; `pages`: the HTML of
    news reports about them, searched for their username when Wikidata has none."""
    import picture
    ig_user = os.environ.get("META_IG_USER_ID", "").strip()
    names = [n for n in dict.fromkeys(names) if n]
    if not names or not ig_user or not os.environ.get("META_ACCESS_TOKEN", "").strip():
        return None
    handle = None
    for name in names:
        try:
            handle = instagram_username(name, get)
        except Exception as e:
            _note(f"  own posts for {post.get('id')}: Wikidata not read ({str(e)[:100]})")
            return None
        if handle:
            break
    if not handle and pages:
        handle = handle_in_pages(pages, names[0])
        if handle:
            _note(f"  own posts for {post.get('id')}: @{handle}, linked from the news reports")
    if not handle:
        _note(f"  own posts for {post.get('id')}: no Instagram account known for {names[0]}")
        return None
    try:
        posts = recent_posts(handle, graph_get or _graph_get, ig_user)
    except Exception as e:   # a personal account, or a token without the permission
        _note(f"  own posts for {post.get('id')}: @{handle} not readable ({str(e)[:160]})")
        return None
    now = dt.datetime.now(dt.timezone.utc)
    fresh = []
    for m in posts:
        try:
            when = dt.datetime.strptime(m["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if now - when <= dt.timedelta(days=RECENT_DAYS):
            fresh.append(m)
    _note(f"  own posts for {post.get('id')}: @{handle} has {len(posts)} recent picture posts, {len(fresh)} from the last {RECENT_DAYS} days")
    for m in fresh[:6]:
        try:
            data = fetch(m["url"])
        except Exception as e:
            _note(f"    @{handle} picture not fetched ({str(e)[:80]})")
            continue
        if picture.detail(data) < picture.SOFT_BELOW:
            _note(f"    @{handle}: soft picture")
            continue
        edit = picture.outlet_edit(data)
        if edit != "":   # cover art, flyers and posters are designs, not photographs (or nobody could look)
            _note(f"    @{handle}: {edit or 'not looked at'}")
            continue
        fit = picture.fits(data, story)
        if fit != "":
            _note(f"    @{handle}: {fit or 'not looked at'}")
            continue
        _note(f"    picked @{handle}'s post {m['permalink']}")
        return data, {"credit": f"Photo: @{handle} on Instagram", "url": m["permalink"], "kind": "file"}
    return None
