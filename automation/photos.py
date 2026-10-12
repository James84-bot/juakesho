"""
photos.py — real photos for posts that need them, safely licensed and on-brand.

Sources, in order:
  1. Your own photos: put them in automation/content/photos/ and set  "photo": "own:matatu-stage.jpg"
     (most authentic; you own the rights).
  2. For the writer's  "photo_query":
     - Wikimedia Commons: real Kenyan places and scenes, free, no key. Only CC0 / public domain / CC BY
       (credited on the image); share-alike, non-commercial and no-derivatives licences are skipped.
     - Pexels: free for commercial use (we credit anyway). Needs PEXELS_API_KEY (free at pexels.com/api).
     Kenyan queries (Nairobi, matatu, M-Pesa...) try Commons first; others try Pexels first. Each falls back
     to the other. Nothing found: the post renders type-only.

Rules (enforced in guard.py): scenes, places and objects; no faces on critical posts; a photo never stands in
for a real person or project we're talking about. On civic posts the design is labelled "illustrative photo".
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OWN = HERE / "content" / "photos"
API = "https://api.pexels.com/v1/search"
COMMONS = "https://commons.wikimedia.org/w/api.php"
# Licences that allow a credited photo inside our design without other conditions
OK_LICENCES = re.compile(r"^(cc0|public domain|pd\b|cc by \d(\.\d)?|cc-by-\d(\.\d)?)", re.I)


def _get(url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "jua-kesho/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


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
    pick = found[zlib.crc32(pid.encode()) % min(5, len(found))]   # varied but reproducible
    data = _get(pick["src"].get("large2x") or pick["src"]["original"])
    return data, {"credit": f"Photo: {pick.get('photographer', 'Pexels')} / Pexels", "url": pick.get("url", "")}


def _licence_ok(lic: str) -> bool:
    low = f" {lic.lower()} "
    return bool(OK_LICENCES.match(lic)) and not re.search(r"[\s-](sa|nc|nd)[\s-]", low)


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


def commons(query: str, pid: str) -> tuple[bytes, dict] | None:
    """A real photo from Wikimedia Commons that we may use in a design with a credit (CC0 / PD / CC BY)."""
    for q in _query_ladder(query):
        got = _commons_once(q, pid)
        if got:
            return got
    return None


def _commons_once(query: str, pid: str) -> tuple[bytes, dict] | None:
    q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
                                "gsrnamespace": 6, "gsrlimit": 25, "prop": "imageinfo",
                                "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1600, "format": "json"})
    pages = json.loads(_get(f"{COMMONS}?{q}")).get("query", {}).get("pages", {})
    good = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        md = info.get("extmetadata", {})
        lic = re.sub(r"<[^>]+>", "", md.get("LicenseShortName", {}).get("value", "")).strip()
        if info.get("mime") not in {"image/jpeg", "image/png"} or info.get("width", 0) < 1000 or info.get("height", 0) < 700:
            continue
        if not _licence_ok(lic):
            continue
        artist = re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "unknown")).strip()[:50]
        good.append((info.get("thumburl") or info["url"], {"credit": f"Photo: {artist} / Wikimedia Commons, {lic}",
                                                         "url": info.get("descriptionurl", "")}))
    if not good:
        return None
    url, meta = good[zlib.crc32(pid.encode()) % min(4, len(good))]
    return _get(url), meta


def fetch(post: dict, out_dir: Path) -> dict | None:
    """Resolves the post's photo to a local file. Returns {"file", "credit", "url"} or None (never raises)."""
    try:
        own = str(post.get("photo", ""))
        if own.startswith("own:"):
            f = OWN / Path(own[4:]).name
            return {"file": str(f), "credit": "", "url": ""} if f.exists() else None
        query = (post.get("photo_query") or "").strip()
        if not query:
            return None
        hit = _cached(out_dir, post["id"])
        if hit:
            return hit
        order = (commons, pexels) if LOCAL.search(query) else (pexels, commons)
        for source in order:
            try:
                got = source(query, post["id"])
            except Exception as e:   # one source down: try the next
                print(f"  photo source {source.__name__} failed for {post.get('id')}: {e}")
                got = None
            if got:
                return _save(out_dir, post["id"], *got)
        return None
    except Exception as e:   # a missing photo must never block the week
        print(f"  photo skipped for {post.get('id')}: {e}")
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
            if not OK_LICENCES.match(lic) or "sa" in lic.lower().split("-") or " sa " in f" {lic.lower()} ":
                print(f"  person photo skipped for {post['id']}: licence '{lic}' needs more than a credit")
                return None
            artist = re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "unknown")).strip()[:60]
            target.write_bytes(_get(info.get("thumburl") or info["url"]))
            data = {"credit": f"Photo: {artist} / Wikimedia Commons, {lic}"}
            meta.write_text(json.dumps(data), encoding="utf-8")
            return {**data, "file": str(target)}
    except Exception as e:
        print(f"  person photo skipped for {post.get('id')}: {e}")
    return None


def attach(posts: list[dict], out_dir: Path) -> None:
    """Sets photo_file / photo_credit (scenes) and person_file / person_credit (people we celebrate)."""
    for p in posts:
        if p.get("person_photo"):
            got = person(p, out_dir / "photos")
            if got:
                p["person_file"], p["person_credit"] = got["file"], got["credit"]
            else:
                p.pop("person_file", None)
                p.pop("person_credit", None)
        if p.get("photo") or p.get("photo_query"):
            got = fetch(p, out_dir / "photos")
            if got:
                p["photo_file"], p["photo_credit"] = got["file"], got["credit"]
            else:
                p.pop("photo_file", None)
                p.pop("photo_credit", None)
