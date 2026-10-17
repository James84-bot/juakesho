"""
videos.py — real moving footage behind a Reel, legally: the place itself, not a still photo slowly zooming.

Sources, in order:
  1. Wikimedia Commons videos: real footage people uploaded under open licences. Only CC0 / public domain /
     CC BY / CC BY-SA (credited on the Reel and in the caption), the same rule as photos.py.
  2. Pixabay videos: free for commercial use under the Pixabay Content License (we credit anyway). Needs
     PIXABAY_API_KEY. Searches are cached for 24 hours, as Pixabay's API terms ask.
  3. Pexels videos: same idea, under the Pexels licence. Needs PEXELS_API_KEY (Pexels paused new keys in Oct 2026).
  Stock search is loose, so a clip counts only if its own tags or page name the place we asked for.

Used only where it beats what the post already has: a showcase post (Kenya at its best, Built in Kenya) or a
post whose photo is symbolic. A real news photo of the day's story is never swapped for generic footage.
On accountability posts, footage where a stranger's face fills the frame is skipped (photos.faces_ok), because a
random person must never look like the subject of a critical post.

The clip is cut to CLIP_S seconds, 1080 px wide, H.264, no sound, and kept next to the post's renders.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

import photos

HERE = Path(__file__).resolve().parent
COMMONS = photos.COMMONS
PEXELS = "https://api.pexels.com/videos/search"
PIXABAY = "https://pixabay.com/api/videos/"
PIXABAY_CACHE = HERE / "state" / "pixabay_cache.json"
DAY = 86400
CLIP_S = 20            # longer than any beat Reel; the composer loops a shorter clip
MAX_BYTES = 150_000_000
MIN_WIDTH = 1280       # landscape footage is cropped to 9:16, so it needs width to spare
SHOWCASE = {"kenya"}
GENERIC_PLACES = {"kenya", "kenyan", "africa", "african"}
GENERIC_WORDS = {"mount", "park", "national", "view", "city", "town", "aerial", "landscape", "scene", "kenya", "kenyan",
                 "africa", "african", "footage", "video", "station", "road", "building", "street"}
_note = photos._note


def wanted(post: dict) -> bool:
    """Footage only where it improves the post: a showcase, or a symbolic photo (never over a real news photo)."""
    if not post.get("beats") or post.get("template") == "tazama" or post.get("group"):
        return False
    if post.get("template") in SHOWCASE:
        return True
    return post.get("photo_kind") in {None, "symbolic"} and bool(post.get("photo_query"))


def _query(post: dict) -> str:
    return str(post.get("video_query") or post.get("photo_query") or "").strip()


def _licence_ok(lic: str) -> bool:
    return photos._licence_ok(lic)


def commons_video(query: str, pid: str) -> tuple[str, dict] | None:
    """(download url, meta) of an openly licensed Commons video that is OF the query's subject and place."""
    place = photos._place(query)
    for q in photos._query_ladder(query):
        params = {"action": "query", "generator": "search", "gsrsearch": f"{q} filetype:video", "gsrnamespace": 6,
                  "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "format": "json"}
        pages = json.loads(photos._get(f"{COMMONS}?{urllib.parse.urlencode(params)}")).get("query", {}).get("pages", {})
        why = {"size": 0, "licence": 0, "subject": 0}
        for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
            info = (page.get("imageinfo") or [{}])[0]
            md = info.get("extmetadata", {})
            lic = re.sub(r"<[^>]+>", "", md.get("LicenseShortName", {}).get("value", "")).strip()
            if info.get("width", 0) < MIN_WIDTH or info.get("size", 0) > MAX_BYTES:
                why["size"] += 1
                continue
            if not _licence_ok(lic):
                why["licence"] += 1
                continue
            about = " ".join([page.get("title", ""), md.get("ImageDescription", {}).get("value", ""),
                              md.get("Categories", {}).get("value", "")]).lower()
            if not photos._relevant(about, query) or (place and place.lower() not in about):
                why["subject"] += 1
                continue
            artist = html.unescape(re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "unknown"))).strip()[:50]
            _note(f"  video '{q}' for {pid}: Commons {page.get('title', '')[:70]}")
            return info["url"], {"credit": f"Footage: {artist} / Wikimedia Commons, {lic}",
                                 "url": info.get("descriptionurl", ""), "source": "commons"}
        _note(f"  video '{q}' for {pid}: Commons {len(pages)} found, none usable {why}")
    return None


def pexels_video(query: str, pid: str) -> tuple[str, dict] | None:
    """(download url, meta) of a Pexels video whose page names the query's place or subject."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    place = photos._place(query).lower()
    named = place if place and place not in GENERIC_PLACES else ""
    core = [w for w in photos._core(query) if w not in GENERIC_WORDS]
    params = urllib.parse.urlencode({"query": query, "per_page": 15, "size": "medium"})
    data = json.loads(photos._get(f"{PEXELS}?{params}", headers={"Authorization": key}))
    for v in data.get("videos", []):
        slug = urllib.parse.unquote(str(v.get("url", ""))).lower()
        # Pexels returns any skyline for "Nairobi skyline": the clip's page must name the place (Nairobi) and,
        # when the query has one, the distinctive subject (Longonot); "Kenya" alone names nothing
        if (named and named not in slug) or (core and not any(w[:5] in slug for w in core)) or not (named or core):
            continue
        files = sorted((f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"
                        and max(f.get("width") or 0, f.get("height") or 0) >= 1080),
                       key=lambda f: (f.get("height") or 0) > (f.get("width") or 0), reverse=True)   # portrait first
        if not files:
            continue
        who = str((v.get("user") or {}).get("name") or "Pexels")[:50]
        _note(f"  video '{query}' for {pid}: Pexels {slug[:80]}")
        return files[0]["link"], {"credit": f"Footage: {who} / Pexels", "url": v.get("url", ""), "source": "pexels"}
    _note(f"  video '{query}' for {pid}: Pexels {len(data.get('videos', []))} found, none of the named place")
    return None


def _named_in(text: str, query: str) -> bool:
    """The clip's own words (tags, page address) name the place and, when the query has one, the subject:
    'Nairobi skyline' needs Nairobi; 'Mount Longonot Kenya' needs Longonot. 'Kenya' alone names nothing."""
    text = text.lower()
    place = photos._place(query).lower()
    named = place if place and place not in GENERIC_PLACES else ""
    core = [w for w in photos._core(query) if w not in GENERIC_WORDS]
    if not (named or core):
        return False
    return (not named or named in text) and (not core or any(w[:5] in text for w in core))


def _pixabay_search(query: str, key: str) -> dict:
    """One search, cached for 24 hours on disk (Pixabay's terms); the key never goes into the cache."""
    import time
    try:
        cache = json.loads(PIXABAY_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    now = time.time()
    cache = {q: v for q, v in cache.items() if now - v.get("at", 0) < DAY}
    if query not in cache:
        params = urllib.parse.urlencode({"key": key, "q": query[:100], "per_page": 20, "safesearch": "true",
                                         "video_type": "film"})
        cache[query] = {"at": now, "data": json.loads(photos._get(f"{PIXABAY}?{params}"))}
        try:
            PIXABAY_CACHE.parent.mkdir(exist_ok=True)
            PIXABAY_CACHE.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
    return cache[query]["data"]


def pixabay_video(query: str, pid: str) -> tuple[str, dict] | None:
    """(download url, meta) of a Pixabay video whose tags or page name the query's place and subject."""
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return None
    data = _pixabay_search(query, key)
    hits = data.get("hits", [])
    for h in hits:
        if not _named_in(f"{h.get('tags', '')} {urllib.parse.unquote(str(h.get('pageURL', '')))}", query):
            continue
        sizes = h.get("videos") or {}
        pick = next((sizes[k] for k in ("large", "medium") if (sizes.get(k) or {}).get("url")
                     and (sizes[k].get("width") or 0) >= MIN_WIDTH and 0 < (sizes[k].get("size") or 0) <= MAX_BYTES), None)
        if not pick:
            continue
        _note(f"  video '{query}' for {pid}: Pixabay {h.get('pageURL', '')[:80]}")
        return pick["url"], {"credit": f"Footage: {str(h.get('user') or 'Pixabay')[:50]} / Pixabay",
                             "url": h.get("pageURL", ""), "source": "pixabay"}
    _note(f"  video '{query}' for {pid}: Pixabay {len(hits)} found, none of the named place")
    return None


def _ffmpeg() -> str:
    import video
    return video.ffmpeg_bin()


def _duration(path: Path) -> float:
    ff = _ffmpeg()
    out = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def cut(src: Path, out: Path) -> bool:
    """CLIP_S seconds from just past the start (openings are often titles or a shaky pan), 1080 wide, no sound."""
    total = _duration(src)
    start = min(total * 0.1, max(0.0, total - CLIP_S)) if total else 0.0
    r = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(src), "-t", str(CLIP_S),
                        "-an", "-vf", "scale='min(1920,iw)':-2,fps=30,format=yuv420p", "-c:v", "libx264",
                        "-preset", "medium", "-crf", "20", "-movflags", "+faststart", str(out)],
                       capture_output=True, text=True)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 10_000


def frames_ok(clip: Path) -> bool:
    """No stranger's face filling the frame at the start, middle or end of the clip."""
    for t in (0.5, CLIP_S / 2, CLIP_S - 1):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
            subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", str(t), "-i", str(clip), "-frames:v", "1", f.name])
            data = Path(f.name).read_bytes() if Path(f.name).exists() else b""
            if data and not photos.faces_ok(data):
                return False
    return True


def fetch(post: dict, out_dir: Path) -> dict | None:
    """The post's footage as a local clip: {"file", "credit", "url"}, or None (never raises)."""
    query = _query(post)
    if not query:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    clip, meta = out_dir / f"{post['id']}-video.mp4", out_dir / f"{post['id']}-video.json"
    if clip.exists() and meta.exists():   # stable across re-renders: what you approved is what goes out
        return {**json.loads(meta.read_text(encoding="utf-8")), "file": str(clip)}
    for source in (commons_video, pixabay_video, pexels_video):
        try:
            got = source(query, post["id"])
            if not got:
                continue
            url, info = got
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / "raw"
                raw.write_bytes(photos._get(url, timeout=120))
                if not cut(raw, clip):
                    _note(f"  video for {post['id']} could not be converted ({url[:80]})")
                    continue
            if post.get("template") not in SHOWCASE and not frames_ok(clip):
                _note(f"  video for {post['id']} skipped: a face fills the frame ({info.get('url')})")
                clip.unlink(missing_ok=True)
                continue
            meta.write_text(json.dumps(info), encoding="utf-8")
            return {**info, "file": str(clip)}
        except Exception as e:   # one source down: try the next
            _note(f"  video source {source.__name__} failed for {post.get('id')}: {str(e)[:120]}")
    return None


def attach(posts: list[dict], out_dir: Path) -> None:
    """Sets video_file / video_credit / video_source on the posts that should move."""
    for p in posts:
        if not wanted(p):
            continue
        got = fetch(p, out_dir / "videos")
        if got:
            p["video_file"], p["video_credit"], p["video_source"] = got["file"], got["credit"], got.get("url", "")
        else:
            for k in ("video_file", "video_credit", "video_source"):
                p.pop(k, None)
