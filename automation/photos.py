"""
photos.py — real photos for posts that need them, safely licensed and on-brand.

Sources, in order:
  1. Your own photos: put them in automation/content/photos/ and set  "photo": "own:matatu-stage.jpg"
     (most authentic; you own the rights).
  2. For the writer's  "photo_query":
     - Wikimedia Commons: real Kenyan places and scenes, free, no key. Only CC0 / public domain / CC BY
       (credited on the image); share-alike, non-commercial and no-derivatives licences are skipped.
     - Openverse: Flickr and other open collections (lots of real Kenyan street, market and protest photos),
       free, no key. Same licence rule: CC0 / public domain / CC BY only, credited.
     - Pexels: free for commercial use (we credit anyway). Needs PEXELS_API_KEY (free at pexels.com/api).
     Kenyan queries (Nairobi, matatu, M-Pesa...) try Commons, then Openverse, then Pexels; others the reverse.
  3. Still nothing on a Kenyan civic post: a real symbolic Kenyan photo (Parliament, the flag, Nairobi's CBD),
     so a political post never goes out as plain type.

Rules (enforced in guard.py): scenes, places and objects; no faces on critical posts; a photo never stands in
for a real person or project we're talking about. On civic posts the design is labelled "illustrative photo".
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTES: list[str] = []   # what each search found and why photos were passed over (saved to state/photos.log)


def _note(msg: str) -> None:
    print(msg)
    NOTES.append(msg.strip())
OWN = HERE / "content" / "photos"
API = "https://api.pexels.com/v1/search"
COMMONS = "https://commons.wikimedia.org/w/api.php"
OPENVERSE = "https://api.openverse.org/v1/images/"
# Symbolic backgrounds: when a post's own search finds nothing, a real photo of the object or place that stands for its
# topic, picked by the words in the post. Never people. The last resort for any civic post is Parliament or the flag.
SYMBOLS = [
    (r"\b(power|electricity|kplc|tokens?|blackouts?)\b", ["power lines Kenya", "electricity pylon Kenya"]),
    (r"\b(tax|budget|treasury|levy|debt|loan|billion|shilling|revenue|kra|money|funds?|bills?)\b|\bsh ?[\d.,]+ ?(bn|m)?\b|\d(bn|m)\b",
     ["Kenyan shilling banknotes", "Central Bank of Kenya"]),
    (r"\b(court|judge|judiciary|ruling|petition|case)\b", ["Supreme Court of Kenya", "Milimani Law Courts"]),
    (r"\b(iebc|election|vote|voters?|ballot|2027|polling)\b", ["ballot box Kenya", "Kenya election"]),
    (r"\b(hospital|health|shif|sha|doctors?|nurses?|clinic)\b", ["hospital ward Kenya", "Kenyatta National Hospital"]),
    (r"\b(school|students?|university|helb|lecturers?|teachers?|exam)\b", ["classroom Kenya", "University of Nairobi"]),
    (r"\b(road|bridge|project|stalled|construction|housing)\b", ["road construction Kenya", "construction site Nairobi"]),
    (r"\b(police|abduct\w*|killed|teargas|protest\w*)\b", ["Flag of Kenya", "Kenya police vehicle"]),
    (r"\b(land|title)\b", ["title deed Kenya", "farmland Kenya"]),
    (r"\b(farm\w*|maize|tea|coffee|fertili[sz]er)\b", ["maize farm Kenya", "tea plantation Kenya"]),
    (r"\b(mp|mps|parliament|bill|senate|law)\b", ["Kenya National Assembly", "Parliament Buildings Nairobi"]),
]
CIVIC_FALLBACK = ["Parliament Buildings Nairobi", "Kenya National Assembly", "Flag of Kenya", "Nairobi Central Business District"]


def symbols_for(post: dict) -> list[str]:
    """Symbolic searches for this post's topic, most specific first."""
    text = " ".join(str(v) for k, v in post.items() if isinstance(v, str) and k not in {"id", "source", "photo_query"}).lower()
    out = []
    for rx, queries in SYMBOLS:
        if re.search(rx, text):
            out += [q for q in queries if q not in out]
    return out[:4]
CIVIC_TEMPLATES = {"sauti", "promise", "kumbuka", "scorecard", "straight", "money", "decode", "usiibiwe", "spotlight"}
# Licences that allow a credited photo inside our design, commercial use included. CC BY-SA is allowed: the post
# that uses it is shared under the same licence, which suits us (we want it shared). NC and ND never.
OK_LICENCES = re.compile(r"^(cc0|public domain|pd\b|cc[ -]by(-sa)?[ -]\d(\.\d)?)", re.I)
UA = "JuaKesho/1.0 (https://github.com/James84-bot/juakesho)"   # Wikimedia asks every bot to identify itself
_LAST: dict[str, float] = {}
_SEEN: dict[str, bytes] = {}


def _get(url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    """Polite fetch: identifies us, paces calls to each host, retries when rate-limited, and remembers search
    results for the run (the same query is often asked for two posts)."""
    host = urllib.parse.urlsplit(url).netloc
    api = "api.php" in url or "api.openverse" in host
    if api and url in _SEEN:
        return _SEEN[url]
    for attempt in range(4):
        wait = 1.0 - (time.monotonic() - _LAST.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _LAST[host] = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if api:
                _SEEN[url] = data
            return data
        except urllib.error.HTTPError as e:
            if e.code not in {429, 503} or attempt == 3:
                raise
            retry = e.headers.get("Retry-After", "") if e.headers else ""
            time.sleep(min(float(retry), 30) if retry.replace(".", "", 1).isdigit() else 4 * 2 ** attempt)
    raise RuntimeError("unreachable")


LOCAL = re.compile(r"\b(kenya|kenyan|nairobi|mombasa|kisumu|nakuru|eldoret|matatu|m-?pesa|shilling|boda|kibera|"
                   r"mathare|africa|african|swahili|maasai|safaricom|parliament|state house)\b", re.I)


def _cached(out_dir: Path, pid: str) -> dict | None:
    target, meta = out_dir / f"{pid}-photo.jpg", out_dir / f"{pid}-photo.json"
    if target.exists() and meta.exists():   # already fetched this week: stay stable across re-renders
        return {**json.loads(meta.read_text(encoding="utf-8")), "file": str(target)}
    return None


def _save(out_dir: Path, pid: str, data: bytes, info: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    target, meta = out_dir / f"{pid}-photo.jpg", out_dir / f"{pid}-photo.json"
    target.write_bytes(data)
    meta.write_text(json.dumps(info), encoding="utf-8")
    return {**info, "file": str(target)}


def pexels(query: str, pid: str) -> tuple[bytes, dict] | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 12, "size": "large"})
    found = json.loads(_get(f"{API}?{q}", {"Authorization": key})).get("photos", [])
    if not found:
        return None
    good = [(f["src"].get("large2x") or f["src"]["original"],
             {"credit": f"Photo: {f.get('photographer', 'Pexels')} / Pexels", "url": f.get("url", "")}) for f in found]
    return _pick(good, pid)


def openverse(query: str, pid: str) -> tuple[bytes, dict] | None:
    """A real photo from Openverse (Flickr and other open collections): CC0, public domain mark or CC BY only."""
    place = _place(query)
    for q in _query_ladder(query):
        got = _openverse_once(q, pid, place, query)
        if got:
            return got
    return None


def _openverse_once(query: str, pid: str, place: str | None = None, full: str | None = None) -> tuple[bytes, dict] | None:
    place = _place(query) if place is None else place
    q = urllib.parse.urlencode({"q": query, "license": "cc0,pdm,by", "size": "large", "mature": "false",
                                "page_size": 20})
    results = json.loads(_get(f"{OPENVERSE}?{q}", {"User-Agent": UA})).get("results", [])
    good, why = [], {"size": 0, "licence": 0, "place": 0, "subject": 0}
    for r in results:
        if r.get("license") not in {"cc0", "pdm", "by"}:
            why["licence"] += 1
            continue
        if (r.get("width") or 0) and ((r.get("width") or 0) < 1000 or (r.get("height") or 0) < 700):
            why["size"] += 1
            continue
        about = " ".join([r.get("title") or "", " ".join(t.get("name", "") for t in r.get("tags") or [])]).lower()
        if place and place.lower() not in about and "kenya" not in about:   # same place rule as Commons
            why["place"] += 1
            continue
        if not _relevant(about, full or query):
            why["subject"] += 1
            continue
        lic = {"cc0": "CC0", "pdm": "public domain", "by": f"CC BY {r.get('license_version') or ''}".strip()}[r["license"]]
        who = (r.get("creator") or "unknown").strip()[:50]
        good.append((r["url"], {"credit": f"Photo: {who} / {(r.get('source') or 'Openverse').title()}, {lic}",
                                "url": r.get("foreign_landing_url") or ""}))
    _note(f"  openverse '{query}' for {pid}: {len(results)} found, {len(good)} usable, dropped {why}")
    return _pick(good, pid)


def commons_newest(query: str, pid: str) -> tuple[bytes, dict] | None:
    return commons(query, pid, newest=True)


def _licence_ok(lic: str) -> bool:
    low = f" {lic.lower()} "
    return bool(OK_LICENCES.match(lic)) and not re.search(r"[\s-](nc|nd)[\s-]", low)


STOP = {"and", "with", "on", "in", "the", "a", "an", "of", "at", "for", "to", "from", "by", "their", "his", "her",
        "our", "your", "showing", "using", "holding", "office", "desk", "photo", "image", "close", "up", "view"}


def _query_ladder(query: str) -> list[str]:
    """Commons search matches every word, so long writer queries often find nothing: try shorter versions too."""
    words = [w for w in re.findall(r"[A-Za-z][\w-]+", query) if w.lower() not in STOP]
    place = next((w for w in words if LOCAL.search(w)), "")
    core = [w for w in words if w != place]
    # never shorter than two content words: a lone "Kenya" or "hands" finds a photo that says nothing
    ladder = [query, " ".join(core[:3] + ([place] if place else [])), " ".join(core[:2]) if len(core) >= 2 else ""]
    out = []
    for q in ladder:
        q = q.strip()
        if q and q.lower() not in {x.lower() for x in out}:
            out.append(q)
    return out


def _core(query: str) -> list[str]:
    """The words that say what the photo is OF (not where): at least one must appear in the photo's own metadata."""
    return [w.lower() for w in re.findall(r"[A-Za-z][\w-]+", query)
            if w.lower() not in STOP and len(w) > 3 and not LOCAL.fullmatch(w)]


def _relevant(about: str, query: str) -> bool:
    core = _core(query)
    return not core or any(w[:5] in about for w in core)   # 5-letter stems: "student" ~ "students"


FACE_MODEL = HERE / "content" / "models" / "face_detection_yunet_2023mar.onnx"
FACE_MAX = 0.09   # a face wider than 9% of the photo is "prominent"


def faces_ok(data: bytes) -> bool:
    """False when a person's face is prominent. A stranger's face never stands in for a story we tell
    (that's how a random person ends up 'the corrupt official'). Crowds and small figures are fine.
    Uses OpenCV's YuNet detector; a false alarm only costs us the next photo in line."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        _note("  face check skipped: opencv not installed")
        return True
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return False
    h, w = img.shape[:2]
    img = cv2.resize(img, (900, max(1, int(h * 900 / max(w, 1)))))
    det = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (img.shape[1], img.shape[0]), 0.75)
    _, faces = det.detect(img)
    return faces is None or not any(f[2] >= FACE_MAX * img.shape[1] for f in faces)


def _pick(good: list[tuple[str, dict]], pid: str, tries: int = 4) -> tuple[bytes, dict] | None:
    if not good:
        return None
    start = zlib.crc32(pid.encode()) % min(4, len(good))
    for url, meta in (good[start:] + good[:start])[:tries]:
        data = _get(url)
        if faces_ok(data):
            return data, meta
        _note(f"  photo skipped for {pid}: a face fills the frame ({meta.get('url') or url})")
    return None


def _place(query: str) -> str:
    m = LOCAL.search(query)
    return m.group(0) if m and m.group(0).lower() not in {"africa", "african"} else ""


def commons(query: str, pid: str, newest: bool = False) -> tuple[bytes, dict] | None:
    """A real photo from Wikimedia Commons that we may use in a design with a credit (CC0 / PD / CC BY).
    The place and the subject come from the FULL query: a shorter retry ("university campus") must still be a
    Kenyan photo of that subject."""
    place = _place(query)
    for q in _query_ladder(query):
        got = _commons_once(q, pid, place, query, newest)
        if got:
            return got
    return None


def _commons_once(query: str, pid: str, place: str | None = None, full: str | None = None,
                   newest: bool = False) -> tuple[bytes, dict] | None:
    place = _place(query) if place is None else place
    params = {"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
              "gsrnamespace": 6, "gsrlimit": 25, "prop": "imageinfo",
              "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1600, "format": "json"}
    if newest:   # a breaking story: the most recent uploads first (Kenyan photographers upload protests within days)
        params["gsrsort"] = "create_timestamp_desc"
    q = urllib.parse.urlencode(params)
    pages = json.loads(_get(f"{COMMONS}?{q}")).get("query", {}).get("pages", {})
    good, why = [], {"size": 0, "licence": 0, "place": 0, "subject": 0}
    for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        md = info.get("extmetadata", {})
        lic = re.sub(r"<[^>]+>", "", md.get("LicenseShortName", {}).get("value", "")).strip()
        if info.get("mime") not in {"image/jpeg", "image/png"} or info.get("width", 0) < 1000 or info.get("height", 0) < 700:
            why["size"] += 1
            continue
        if not _licence_ok(lic):
            why["licence"] += 1
            continue
        # A Kenyan story never gets a photo from somewhere else: when the search names a place, the photo's own
        # title, description or categories must name it too (or Kenya)
        about = " ".join([page.get("title", ""), md.get("ImageDescription", {}).get("value", ""),
                          md.get("Categories", {}).get("value", "")]).lower()
        if place and place.lower() not in about and "kenya" not in about:
            why["place"] += 1
            continue
        if not _relevant(about, full or query):   # "Kenya" alone isn't enough: it must be a photo OF the subject
            why["subject"] += 1
            continue
        artist = html.unescape(re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "unknown"))).strip()[:50]
        good.append((info.get("thumburl") or info["url"], {"credit": f"Photo: {artist} / Wikimedia Commons, {lic}",
                                                         "url": info.get("descriptionurl", "")}))
    _note(f"  commons '{query}' for {pid}: {len(pages)} found, {len(good)} usable, dropped {why}")
    return _pick(good, pid)


EVENT_DAYS_BEFORE, EVENT_DAYS_AFTER = 4, 1   # a photo taken/uploaded in this window around the post counts as "of the day"


TITLES = {"president", "deputy", "senator", "governor", "speaker", "minister", "cabinet", "secretary", "chief",
          "justice", "hon", "honourable", "dr", "prof", "mp", "mca", "cs", "ps", "cj", "dp", "former", "the", "leader",
          "commissioner", "chairperson", "chair", "chairman", "nominated", "woman", "rep", "member", "principal"}
INSTITUTION = re.compile(r"^(kenya\w*|nairobi|national|county|assembly|senate|parliament|committee|commission|bureau|"
                         r"bank|ministry|authority|kwanza|azimio|iebc|government|office|department|house|state|court|"
                         r"police|service|board|council|agency|fund|treasury|registration|public|debt|privatisation|"
                         r"central|youth|charter|manifesto|energy|interior|health|education|finance|opposition|"
                         r"united|democratic|party|movement|alliance|coalition|republic|east|africa|african|"
                         r"constitution|act|bill|report|annual|statistical|bulletin|development|management|urban|"
                         r"housing|roads?|transport|infrastructure|sports|power|lighting|company|limited|corporation|"
                         r"directorate|division|revenue|market|bridge|stadium|leaders?|political|politicians?|"
                         r"officials?|residents?|traders?|students?|farmers?|members?|kenyans?|workers?|teachers?|"
                         r"doctors?|nurses?|lawmakers?|mps|mcas|governors?|senators?|citizens?|voters?|youths?)$", re.I)


def _surname(who: str) -> str:
    """The surname of the PERSON in `who` ('Energy CS Opiyo Wandayi' -> 'wandayi'); '' when `who` is an
    institution ('National Assembly Public Debt Committee') or names nobody."""
    words = re.findall(r"[A-Z][a-z'-]{2,}", who or "")
    names = [w for w in words if w.lower() not in TITLES and not INSTITUTION.match(w)]
    # a person is at least a first name and a surname next to each other in the text
    pairs = [last for first, last in zip(names, names[1:]) if re.search(rf"\b{first}\s+{last}\b", who)]
    return pairs[-1].lower() if pairs else ""


def _event_window(post: dict) -> tuple[dt.datetime, dt.datetime]:
    try:
        day = dt.datetime.fromisoformat(post["publish_at"]).astimezone(dt.timezone.utc)
    except (KeyError, ValueError):
        day = dt.datetime.now(dt.timezone.utc)
    start = min(day, dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=EVENT_DAYS_BEFORE)   # story precedes the slot
    return start, day + dt.timedelta(days=EVENT_DAYS_AFTER)


def _when_taken(info: dict) -> dt.datetime | None:
    md = info.get("extmetadata", {})
    raw = re.sub(r"<[^>]+>", "", md.get("DateTimeOriginal", {}).get("value", "")).strip()
    m = re.match(r"(\d{4})[-:](\d{2})[-:](\d{2})", raw)
    if m:
        return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, tzinfo=dt.timezone.utc)
    ts = info.get("timestamp")   # upload time: a fresh upload of an older photo still fails the window below
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None


def event_photo(post: dict) -> tuple[bytes, dict] | None:
    """A licensed photo OF the story, taken in the days around it (Wikimedia Commons, newest first).
    A named public figure may be in it (their name must be in the photo's own description); anyone else's
    face still may not fill the frame."""
    query = (post.get("event_query") or "").strip()
    if not query:
        return None
    start, end = _event_window(post)
    surname = _surname(str(post.get("who", "")))
    for q in _query_ladder(query):
        params = {"action": "query", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6,
                  "gsrlimit": 30, "gsrsort": "create_timestamp_desc", "prop": "imageinfo",
                  "iiprop": "url|extmetadata|size|mime|timestamp", "iiurlwidth": 1600, "format": "json"}
        pages = json.loads(_get(f"{COMMONS}?{urllib.parse.urlencode(params)}")).get("query", {}).get("pages", {})
        good, why = [], {"size": 0, "licence": 0, "date": 0, "subject": 0}
        for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
            info = (page.get("imageinfo") or [{}])[0]
            md = info.get("extmetadata", {})
            lic = re.sub(r"<[^>]+>", "", md.get("LicenseShortName", {}).get("value", "")).strip()
            if info.get("mime") not in {"image/jpeg", "image/png"} or info.get("width", 0) < 1000 or info.get("height", 0) < 700:
                why["size"] += 1
                continue
            if not _licence_ok(lic):
                why["licence"] += 1
                continue
            taken = _when_taken(info)
            if not taken or not (start <= taken <= end):
                why["date"] += 1
                continue
            about = " ".join([page.get("title", ""), md.get("ImageDescription", {}).get("value", ""),
                              md.get("Categories", {}).get("value", "")]).lower()
            if not _relevant(about, query) or ("kenya" not in about and not (surname and surname in about)):
                why["subject"] += 1
                continue
            artist = html.unescape(re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "unknown"))).strip()[:50]
            good.append((info.get("thumburl") or info["url"],
                         {"credit": f"Photo: {artist} / Wikimedia Commons, {lic}", "url": info.get("descriptionurl", ""),
                          "kind": "event", "named": bool(surname and surname in about)}))
        _note(f"  event '{q}' for {post['id']} ({start:%d %b}-{end:%d %b}): {len(pages)} found, {len(good)} usable, dropped {why}")
        for url, meta in good[:4]:
            data = _get(url)
            if meta.pop("named") or faces_ok(data):   # the named office holder may be the face; a stranger may not
                return data, meta
            _note(f"  event photo skipped for {post['id']}: an unnamed face fills the frame ({meta.get('url')})")
    return None


def full_name(who: str) -> str:
    """'Energy CS Opiyo Wandayi' -> 'Opiyo Wandayi'; '' when `who` names no person."""
    surname = _surname(who)
    if not surname:
        return ""
    m = re.search(rf"\b([A-Z][a-z'-]{{2,}})\s+({surname})\b", who or "", re.I)
    return f"{m.group(1)} {m.group(2).title()}" if m and m.group(1).lower() not in TITLES else ""


def commons_portrait(post: dict) -> tuple[bytes, dict] | None:
    """A licensed photo of the public figure the post is about (Wikimedia Commons, CC0 / PD / CC BY / BY-SA),
    found by their full name, which must be in the file's title. Labelled "File photo": it shows the real person,
    not the day itself."""
    name = full_name(str(post.get("who", "")))
    if not name:
        return None
    surname = name.split()[-1].lower()
    params = {"action": "query", "generator": "search", "gsrsearch": f'"{name}" filetype:bitmap', "gsrnamespace": 6,
              "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1600,
              "format": "json"}
    pages = json.loads(_get(f"{COMMONS}?{urllib.parse.urlencode(params)}")).get("query", {}).get("pages", {})
    good = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        md = info.get("extmetadata", {})
        lic = re.sub(r"<[^>]+>", "", md.get("LicenseShortName", {}).get("value", "")).strip()
        if surname not in page.get("title", "").lower():   # a photo OF them, not one that merely mentions them
            continue
        if info.get("mime") not in {"image/jpeg", "image/png"} or info.get("width", 0) < 800 or not _licence_ok(lic):
            continue
        artist = html.unescape(re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "unknown"))).strip()[:50]
        good.append((info.get("thumburl") or info["url"],
                     {"credit": f"File photo: {artist} / Wikimedia Commons, {lic}", "url": info.get("descriptionurl", ""),
                      "kind": "file"}))
    _note(f"  portrait '{name}' for {post.get('id')}: {len(pages)} found, {len(good)} usable")
    for url, meta in good[:2]:
        return _get(url), meta
    return None


def fetch(post: dict, out_dir: Path) -> dict | None:
    """Resolves the post's photo to a local file. Returns {"file", "credit", "url"} or None (never raises)."""
    try:
        own = str(post.get("photo", ""))
        if own.startswith("own:"):
            f = OWN / Path(own[4:]).name
            return {"file": str(f), "credit": "", "url": ""} if f.exists() else None
        if own.startswith("sent:"):   # a photo you replied to the card with (rights given in its caption)
            f = HERE.parent / own[5:]
            return ({"file": str(f), "credit": post.get("photo_rights_credit", ""), "url": "", "kind": "yours"}
                    if f.exists() else None)
        query = (post.get("photo_query") or "").strip()
        hit = _cached(out_dir, post["id"])
        if hit:
            return hit
        if post.get("template") in CIVIC_TEMPLATES | {"glasspoll"} and not post.get("group"):
            import posted
            try:
                got = event_photo(post)
            except Exception as e:
                _note(f"  event photo search failed for {post.get('id')}: {e}")
                got = None
            if got:
                return _save(out_dir, post["id"], *got)
            try:   # the photo already posted of the day's story (credited, news and commentary use)
                import posted
                got = posted.find(post)
            except Exception as e:
                _note(f"  posted-photo search failed for {post.get('id')}: {e}")
                got = None
            if got:
                return _save(out_dir, post["id"], *got)
            # nothing of the day itself: a real file photo of the person or body the post is about, before any symbol
            for name, step in (("file photo from the news", lambda: posted.find_named(post)),
                               ("portrait", lambda: commons_portrait(post))):
                try:
                    got = step()
                except Exception as e:
                    _note(f"  {name} search failed for {post.get('id')}: {e}")
                    got = None
                if got:
                    return _save(out_dir, post["id"], *got)
        if not query:
            return None
        order = (commons, openverse, pexels) if LOCAL.search(query) else (pexels, openverse, commons)
        if post.get("template") == "kenya":   # the real place itself: documentary sources only, never stock or a symbol
            tries = [(commons, query), (openverse, query)]
            for source, q in tries:
                try:
                    got = source(q, post["id"])
                except Exception as e:
                    _note(f"  photo source {source.__name__} failed for {post.get('id')}: {e}")
                    got = None
                if got:
                    got[1]["kind"] = "place"
                    return _save(out_dir, post["id"], *got)
            _note(f"  no photo of '{query}' for {post['id']}: a showcase post needs one (reply to its card with a photo)")
            return None
        tries = [(source, query) for source in order]
        if post.get("hot"):   # today's story: try this week's real photos of it first
            tries.insert(0, (commons_newest, query))
        tries += [(commons, q) for q in symbols_for(post)]
        if post.get("template") in CIVIC_TEMPLATES:
            tries += [(commons, q) for q in CIVIC_FALLBACK if q not in symbols_for(post)]
        for source, q in tries:
            try:
                got = source(q, post["id"])
            except Exception as e:   # one source down: try the next
                _note(f"  photo source {source.__name__} failed for {post.get('id')}: {e}")
                got = None
            if got:
                if q != query:
                    _note(f"  photo for {post['id']}: nothing for '{query}', used '{q}'")
                got[1].setdefault("kind", "symbolic")
                return _save(out_dir, post["id"], *got)
        _note(f"  no photo found for {post['id']} ('{query}')")
        return None
    except Exception as e:   # a missing photo must never block the week
        _note(f"  photo skipped for {post.get('id')}: {e}")
        return None


PEOPLE = HERE / "content" / "people"


def person(post: dict, out_dir: Path) -> dict | None:
    """The REAL photo of someone we celebrate. Two legal routes:
      "people/amina.jpg" + photo_rights ("permission from Amina's team, 12 Oct", "press kit: <url>")
      "commons:File:Name.jpg" (Wikimedia Commons; accepted only if CC0 / public domain / CC BY, credited)."""
    ref = str(post.get("person_photo") or "")
    try:
        if ref.startswith("people/"):
            f = PEOPLE / Path(ref).name
            rights = str(post.get("photo_rights") or "").strip()
            return {"file": str(f), "credit": f"Photo: {rights}"} if f.exists() and len(rights) >= 8 else None
        if ref.startswith("commons:"):
            title = ref[len("commons:"):]
            if not title.startswith("File:"):
                title = "File:" + title
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"{post['id']}-person.jpg"
            meta = out_dir / f"{post['id']}-person.json"
            if target.exists() and meta.exists():
                return {**json.loads(meta.read_text(encoding="utf-8")), "file": str(target)}
            q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "imageinfo", "format": "json",
                                        "iiprop": "url|extmetadata", "iiurlwidth": 1200})
            pages = json.loads(_get(f"{COMMONS}?{q}"))["query"]["pages"]
            info = next(iter(pages.values()))["imageinfo"][0]
            md = info.get("extmetadata", {})
            lic = re.sub(r"<[^>]+>", "", md.get("LicenseShortName", {}).get("value", "")).strip()
            if not _licence_ok(lic):
                _note(f"  person photo skipped for {post['id']}: licence '{lic}' needs more than a credit")
                return None
            artist = re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "unknown")).strip()[:60]
            target.write_bytes(_get(info.get("thumburl") or info["url"]))
            data = {"credit": f"Photo: {artist} / Wikimedia Commons, {lic}"}
            meta.write_text(json.dumps(data), encoding="utf-8")
            return {**data, "file": str(target)}
    except Exception as e:
        _note(f"  person photo skipped for {post.get('id')}: {e}")
    return None


def attach(posts: list[dict], out_dir: Path) -> None:
    """Sets photo_file / photo_credit (scenes) and person_file / person_credit (people we celebrate).
    Leaves state/photos.log: what every search found, so a missing photo can be explained."""
    NOTES.clear()
    try:
        _attach(posts, out_dir)
    finally:
        # only real renders (under exports/) write the log; tests and scratch renders keep it clean
        if HERE.parent / "exports" in Path(out_dir).resolve().parents:
            try:
                (HERE / "state").mkdir(exist_ok=True)
                (HERE / "state" / "photos.log").write_text("\n".join(NOTES[-400:]) + "\n", encoding="utf-8")
            except OSError:
                pass


def _attach(posts: list[dict], out_dir: Path) -> None:
    for p in posts:
        if p.get("person_photo"):
            got = person(p, out_dir / "photos")
            if got:
                p["person_file"], p["person_credit"] = got["file"], got["credit"]
            else:
                p.pop("person_file", None)
                p.pop("person_credit", None)
        if p.get("photo") or p.get("photo_query") or p.get("event_query"):
            got = fetch(p, out_dir / "photos")
            if got:
                p["photo_file"], p["photo_credit"] = got["file"], got["credit"]
                p["photo_kind"] = got.get("kind", "symbolic")
                p["photo_outlet"] = got.get("outlet", "")
                p["photo_source"] = p.get("photo_source") or got.get("url", "")
            else:
                for k in ("photo_file", "photo_credit", "photo_kind", "photo_outlet"):
                    p.pop(k, None)
