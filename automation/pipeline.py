"""
pipeline.py — the Kenya on Record autopilot.

    python pipeline.py week   [--week 2026-W40] [--mock]   plan → draft → check → render → ask for approval
    python pipeline.py hot                                  today's extra post on the biggest Kenyan story (daily)
    python pipeline.py tick   [--dry-run]                   collect approvals → publish what's due
    python pipeline.py learn                                score recent posts from Instagram insights
    python pipeline.py status [--week 2026-W40]             show every post's state

Individual steps: plan, draft, render, ask, collect, publish.

Every post moves through:
  planned → drafted → rendered → awaiting → approved → published
                 ↘ needs_human (guard failed)   ↘ rejected   ↘ manual (you post it in the app, with a trending sound)
                                                              ↘ publish_failed (retried up to 3x)

State lives in content/weeks/<week>.json, so every step is safe to re-run.
Nothing is published without a human tap on ✅ in Telegram.

Environment (.env next to this file or real env vars):
  ANTHROPIC_API_KEY, JUA_MODEL                     drafting
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID             approval
  META_ACCESS_TOKEN, META_PAGE_ID, META_IG_USER_ID publishing (Page token)
  META_GRAPH_VERSION                               default v26.0
  PUBLIC_BASE_URL                                  where exports/ is publicly served, e.g.
                                                   https://raw.githubusercontent.com/<user>/<repo>/main
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import re
import shutil
import tempfile
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WEEKS = HERE / "content" / "weeks"
STATE = HERE / "state"
EXPORTS = ROOT / "exports"
EAT = dt.timezone(dt.timedelta(hours=3))
BRAND = json.loads((HERE / "brand.json").read_text(encoding="utf-8"))
MAX_PUBLISH_ATTEMPTS = 3
EXPIRE_AFTER = dt.timedelta(hours=2)  # a card nobody tapped this long after its slot is dropped: no tap = no post
LATE_LIMIT = dt.timedelta(hours=36)  # a post this late is marked "missed", never dumped out as a backlog
META_KEYS = ("META_ACCESS_TOKEN", "META_PAGE_ID", "META_IG_USER_ID")


# ---------------------------------------------------------------------------
# Config and small utilities
# ---------------------------------------------------------------------------
def load_env() -> None:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def need(*names: str) -> dict:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(f"Missing settings: {', '.join(missing)} (see .env.example)")
    return {n: os.environ[n] for n in names}


def now() -> dt.datetime:
    return dt.datetime.now(EAT)


def current_week_label(d: dt.date | None = None, ahead: int = 1) -> str:
    """The week being prepared. On Sunday we prepare next week, hence ahead=1."""
    d = (d or now().date()) + dt.timedelta(weeks=ahead)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_file(label: str) -> Path:
    return WEEKS / f"{label}.json"


def load_week(label: str) -> dict:
    f = week_file(label)
    if not f.exists():
        raise SystemExit(f"No plan for {label}. Run: python pipeline.py plan --week {label}")
    return json.loads(f.read_text(encoding="utf-8"))


def save_week(data: dict) -> None:
    WEEKS.mkdir(parents=True, exist_ok=True)
    tmp = week_file(data["collection"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(week_file(data["collection"]))  # atomic: a crash never leaves half a file


def log(msg: str) -> None:
    print(f"[{now():%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# HTTP (plain urllib so the pipeline has no extra dependencies)
# ---------------------------------------------------------------------------
def http(method: str, url: str, fields: dict | None = None, files: dict | None = None, timeout: int = 60) -> dict:
    data, headers = None, {}
    if files:
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in (fields or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for k, path in files.items():
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{Path(path).name}"\r\n'
                         f"Content-Type: {ctype}\r\n\r\n".encode() + Path(path).read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif fields is not None:
        data = urllib.parse.urlencode(fields).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if files:   # uploads (Reels, albums) need far longer than a plain API call
        timeout = max(timeout, 240)
    where = url.split("?")[0].split("/bot")[0]   # never put a bot token in an error message
    last: Exception | None = None
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:600]
            if e.code in (409, 429, 500, 502, 503, 504) and attempt < 2:   # 409: another getUpdates reader
                last = e
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"{method} {where} → {e.code}: {detail}") from e
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            last = e
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{method} {where} failed after 3 tries: {last!r}")


# ---------------------------------------------------------------------------
# 1. Plan
# ---------------------------------------------------------------------------
def _pick(value, week_no: int):
    return value[week_no % len(value)] if isinstance(value, list) else value


EVIDENCE_SKIP = {"status", "guard", "critic", "ink", "symbol_box", "seed", "attempts", "last_error", "photo_file", "person_file", "tg_msg"}


def record_evidence(members: list[dict]) -> None:
    """The defence file: exactly what went out, when, and on what sources. Append-only, one JSON line per post,
    committed with the state. If anyone challenges a post, this is the record of what was said and why."""
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "evidence.jsonl").open("a", encoding="utf-8") as f:
        for m in members:
            f.write(json.dumps({k: v for k, v in m.items() if k not in EVIDENCE_SKIP}, ensure_ascii=False) + "\n")


def _anniversaries(posts: list[dict], year: int, wk: int) -> None:
    """Hatutasahau: in the week of an anniversary, the nearest Mon-Fri single post becomes a remembrance post."""
    path = HERE / "content" / "remember.json"
    if not path.exists():
        return
    for item in json.loads(path.read_text(encoding="utf-8"))["dates"]:
        when = dt.date.fromisoformat(item["date"])
        try:
            this_year = when.replace(year=year)
        except ValueError:   # 29 February
            continue
        iso = this_year.isocalendar()
        if (iso[0], iso[1]) != (year, wk) or this_year.year <= when.year:
            continue
        singles = [p for p in posts if not p.get("group") and p.get("size") != "story"
                   and dt.date.fromisoformat(p["publish_at"][:10]).isoweekday() <= 5 and p["template"] != "kumbuka"]
        if not singles:
            continue
        target = min(singles, key=lambda p: abs(dt.date.fromisoformat(p["publish_at"][:10]) - this_year))
        target.update(template="kumbuka", remember={"date": item["date"], "event": item["event"],
                                                    "years": this_year.year - when.year},
                      id=target["id"].rsplit("-", 1)[0] + "-kumbuka")
        target.pop("series", None)


HOT = {"time": (12, 45), "template": "sauti", "min_lead": dt.timedelta(hours=3)}
# News posts every day, each on a different story: morning, lunchtime and evening editions, plus "breaking" posts
# when several newsrooms report one story at once. A breaking post is due 20 minutes after drafting (time to
# render), so it goes out on the run your ✅ triggers; unapproved, it expires as usual. At most BREAKING_MAX a day.
EDITIONS = {"morning": {"time": (9, 45), "suffix": "m"}, "midday": {"time": (12, 45), "suffix": ""},
            "evening": {"time": (19, 30), "suffix": "e"}}
BREAKING_LEAD, BREAKING_MAX = dt.timedelta(minutes=20), 2


def _clear_of(when: dt.datetime, posts: list[dict], gap: dt.timedelta = dt.timedelta(minutes=90)) -> dt.datetime:
    """Two posts close together split the audience: move the hot post until it is `gap` from every other post."""
    taken = [dt.datetime.fromisoformat(p["publish_at"]) for p in posts
             if p.get("publish_at") and p.get("status") not in {"rejected", "expired", "missed"}]
    while any(abs(when - t) < gap for t in taken):
        when += dt.timedelta(minutes=30)
    return when


def hot_slot(mock: bool = False, evening: bool = False, edition: str | None = None) -> str | None:
    """A news post on the biggest Kenyan story right now, never one already covered today.
    Editions: morning, midday (lunchtime) and evening, drafted about three hours before they go out; and
    "breaking", only when three or more newsrooms report one story within three hours and we haven't covered it,
    out as soon as you approve it, at most BREAKING_MAX a day.
    Adds a planned Sauti post to this week's file (made if missing); returns the week label, or None if there is
    nothing to do (this edition exists, no fresh news, or no breaking story)."""
    edition = edition or ("evening" if evening else "midday")
    label = current_week_label(ahead=0)
    today = now().date()
    if week_file(label).exists():
        data = load_week(label)
    else:
        data = {"collection": label, "created": now().isoformat(), "posts": [], "scripts": {}}
    todays = [p for p in data["posts"] if p.get("hot") and p["publish_at"][:10] == today.isoformat()]
    covered = [str(p.get("message") or p.get("line") or p.get("breaking", {}).get("title") or "") for p in todays]
    covered = [c for c in covered if c]
    extra: dict = {}
    if edition == "breaking":
        import news
        if sum(1 for p in todays if p.get("breaking")) >= BREAKING_MAX:
            log("breaking: today's limit reached")
            return None
        story = next((c for c in news.breaking() if not any(news.same_story(c["title"], x) for x in covered)), None)
        if not story:
            log("breaking: nothing new is being reported by several newsrooms at once")
            return None
        hot_id = f"{label.lower()}-hot-{today:%m%d}b{now():%H%M}"
        when = (now() + BREAKING_LEAD).replace(second=0, microsecond=0)
        extra = {"breaking": {"title": story["title"], "outlets": story["outlets"]},
                 "source_links": [{"outlet": x["outlet"], "title": x["title"], "link": x["link"],
                                   "published": x.get("published", "")[:10]} for x in story["items"][:4]]}
    else:
        hot_id = f"{label.lower()}-hot-{today:%m%d}{EDITIONS[edition]['suffix']}"
        if any(p["id"] == hot_id for p in data["posts"]):
            log(f"today's {edition} news post {hot_id} already exists")
            return None
        if not mock:
            import news
            if not news.prompt_block():
                log("hot: no fresh news to react to, skipping")
                return None
        when = dt.datetime(today.year, today.month, today.day, *EDITIONS[edition]["time"], tzinfo=EAT)
        if when - now() < HOT["min_lead"]:   # late start: give the owner time to approve
            when = (now() + HOT["min_lead"]).replace(second=0, microsecond=0)
        when = _clear_of(when, data["posts"])
    post = {"id": hot_id, "template": HOT["template"], "bg": "usiku", "lane": "everyone",
            "publish_at": when.isoformat(), "status": "planned", "hot": True, **extra}
    if covered:   # never two posts on the same story in one day
        post["avoid"] = covered[:4]
    data["posts"].append(post)
    save_week(data)
    log(f"hot ({edition}): planned {hot_id} for {when:%a %H:%M} EAT")
    return label


def _calendar_posts(label: str) -> list[dict]:
    """The week's slots from calendar.json, planned (not yet drafted)."""
    cal = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))
    year, wk = int(label[:4]), int(label.split("W")[1])
    posts = []
    for slot in cal["slots"]:
        day = dt.date.fromisocalendar(year, wk, slot["day"])
        hh, mm = map(int, slot["time"].split(":"))
        when = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=EAT).isoformat()
        template = _pick(slot["template"], wk)
        lane = _pick(slot["lanes"], wk)
        bg = _pick(slot["bg"], wk)
        base_id = f"{label.lower()}-d{slot['day']}-{template}"
        post = {"id": base_id, "template": template, "bg": bg, "lane": lane, "publish_at": when, "status": "planned"}
        if slot.get("size"):
            post["size"] = slot["size"]
        if slot.get("angle"):
            post["angle"] = slot["angle"]
        series = slot.get("series")
        if isinstance(series, dict):   # {"hack": "Civic 101"}: a series name for one of the slot's templates
            series = series.get(template)
        if series:
            post["series"] = _pick(series, wk)
        if slot.get("carousel"):
            group = base_id
            post["group"] = group
            posts.append(post)
            c = slot["carousel"]
            for n in range(1, c["slides"] + 1):
                posts.append({"id": f"{label.lower()}-d{slot['day']}-{c['template']}-{n}", "template": c["template"], "bg": bg, "lane": lane,
                              "publish_at": when, "status": "planned", "group": group, "n": n, "total": c["slides"]})
            continue
        posts.append(post)
    _anniversaries(posts, year, wk)
    return posts


TRACKER_ANGLES = ["done", "stalled", "ignored", "diverted", "stalled"]   # one of each, plus a second stalled


def tracker(label: str) -> list[str]:
    """Development Tracker week: every planned post becomes a project check (done, stalled, ignored or money
    diverted), the polls ask about a project people can see. Only a week nobody has decided anything in."""
    data = load_week(label) if week_file(label).exists() else {"collection": label, "created": now().isoformat(),
                                                                "posts": _calendar_posts(label), "scripts": {}}
    if any(p["status"] not in {"planned", "drafted", "rendered", "needs_human"} for p in data["posts"]):
        log(f"tracker {label}: posts already sent or decided; not replanning")
        return []
    angles = iter(TRACKER_ANGLES)
    out = []
    for p in data["posts"]:
        if p.get("group"):
            continue
        if p["template"] == "glasspoll":
            p.update(angle="tracker_poll", series="Development Tracker")
        else:
            p.update(template="promise", angle=next(angles, "stalled"), series="Development Tracker",
                     id=re.sub(r"-d(\d)-[a-z]+$", r"-d\1-promise", p["id"]))
        p["status"] = "planned"
        out.append(p)
    data["posts"] = out
    save_week(data)
    log(f"tracker {label}: {[(p['id'], p.get('angle')) for p in out]}")
    return [p["id"] for p in out]


def plan(label: str) -> dict:
    if week_file(label).exists():
        log(f"{label} already planned, keeping it")
        return load_week(label)
    posts = _calendar_posts(label)
    data = {"collection": label, "created": now().isoformat(), "posts": posts, "scripts": {}}
    save_week(data)
    log(f"planned {len(posts)} designs for {label}")
    return data


# ---------------------------------------------------------------------------
# 2. Draft
# ---------------------------------------------------------------------------
DRAFT_AHEAD = dt.timedelta(days=4, hours=12)   # Sunday writes Mon-Thu; Wednesday writes Fri-Sun: news stays fresh


def draft(label: str, mock: bool = False, horizon: dt.timedelta | None = DRAFT_AHEAD) -> dict:
    import draft as drafter
    data = load_week(label)
    todo = [p for p in data["posts"] if p["status"] == "planned"]
    if horizon is not None and not mock:   # a carousel's slides share one slot, so they stay together
        later = [p["id"] for p in todo if dt.datetime.fromisoformat(p["publish_at"]) - now() > horizon]
        todo = [p for p in todo if p["id"] not in later]
        if later:
            log(f"written closer to their slot (midweek run): {later}")
    if not todo:
        log("nothing to draft")
        return data
    lanes = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))["lanes"]
    drafter.TAKEN = [p for p in data["posts"] if p["status"] not in {"planned", "rejected", "missed"}]
    drafted, scripts = drafter.draft_week(label, todo, lanes, mock=mock)
    data_spend = round(drafter.SPEND["usd"], 4)
    for p in drafted:
        p.setdefault("drafted_at", now().isoformat())
    by_id = {p["id"]: p for p in drafted}
    data["posts"] = [by_id.get(p["id"], p) for p in data["posts"]]
    data["scripts"] = scripts or data.get("scripts", {})
    data["spend_usd"] = round(data.get("spend_usd", 0) + data_spend, 4)   # this week's AI cost, for the owner
    save_week(data)
    log(f"AI spend this week: ${data['spend_usd']:.3f} (cap ${drafter.budget():.2f})")
    bad = [p["id"] for p in drafted if p["status"] == "needs_human"]
    log(f"drafted {len(drafted)}; needs a human: {bad or 'none'}")
    return data


# ---------------------------------------------------------------------------
# 3. Render (PNG for Telegram/WhatsApp, JPEG for Instagram)
# ---------------------------------------------------------------------------
PLAN_KEYS = {"id", "template", "bg", "lane", "publish_at", "size", "group", "n", "total", "series", "remember", "hot", "angle"}


def redo(label: str) -> list[str]:
    """Held posts (status needs_human) go back to 'planned' so draft → render → ask runs again for them only.
    A carousel is redone as a whole, so its slides stay consistent."""
    data = load_week(label)
    groups = {p["group"] for p in data["posts"] if p["status"] == "needs_human" and p.get("group")}
    reset = []
    for i, p in enumerate(data["posts"]):
        if p["status"] == "needs_human" or (p.get("group") in groups and p["status"] != "published"):
            data["posts"][i] = {k: v for k, v in p.items() if k in PLAN_KEYS} | {"status": "planned"}
            reset.append(p["id"])
    save_week(data)
    log(f"redo {label}: {reset or 'nothing held'}")
    return reset


def _next_rev(pid: str) -> str:
    m = re.match(r"^(.*)-r(\d+)$", pid)
    return f"{m.group(1)}-r{int(m.group(2)) + 1}" if m else f"{pid}-r2"


def remake(label: str, replace_approved: bool = False) -> list[str]:
    """Re-plans the rest of the week from the CURRENT calendar and drafts it from scratch with the current rules.
    Kept: published, approved and hand-posted posts, hot posts and Tazama Hii clips. Everything else still waiting
    is dropped; slots already past (or under two hours away) are not refilled. New ids carry a revision (…-r2),
    so a tap on an older Telegram card can never approve the new version unseen.
    replace_approved (the `renew` command): approved posts that haven't gone out yet are redrafted too, for when
    the rules change after you approved a batch; they come back to you for approval."""
    data = load_week(label)
    keep = {"published", "manual"} if replace_approved else {"published", "approved", "manual"}
    kept = [p for p in data["posts"] if p["status"] in keep or p.get("hot") or p.get("template") == "tazama"]
    rev = int(data.get("revision", 1)) + 1
    taken = {p["id"] for p in data["posts"]}
    decided_days = {p["publish_at"][:10] for p in kept if not p.get("hot") and p.get("template") != "tazama"}
    soon = now() + dt.timedelta(hours=2)
    fresh = []
    for p in _calendar_posts(label):
        if dt.datetime.fromisoformat(p["publish_at"]) < soon or p["publish_at"][:10] in decided_days:
            continue
        p["id"] = f"{p['id']}-r{rev}"
        if p.get("group"):
            p["group"] = f"{p['group']}-r{rev}"
        while p["id"] in taken:
            p["id"] += "x"
        fresh.append(p)
    data["posts"] = kept + fresh
    data["revision"] = rev
    save_week(data)
    ids = [p["id"] for p in fresh if not p.get("n")]
    log(f"remake {label}: kept {len(kept)}, {len(ids)} new post(s) from the current calendar")
    return ids


def rephoto(label: str) -> list[str]:
    """Keeps the words, finds the photos again (after the photo rules change) and re-sends the posts.
    New ids, as in remake, so an older card can't approve the new picture unseen. Decided posts are kept."""
    data = load_week(label)
    groups: dict[str, str] = {}
    changed = []
    for p in data["posts"]:
        if p["status"] not in {"awaiting", "drafted", "rendered"} or not (p.get("photo_query") or p.get("photo")):
            continue
        old = p["id"]
        p["id"] = _next_rev(old)
        if p.get("group"):
            p["group"] = groups.setdefault(p["group"], _next_rev(p["group"]))
        for k in ("photo_file", "photo_credit", "photo_kind", "photo_outlet", "video_file", "video_credit", "video_source"):
            p.pop(k, None)
        p["status"] = "drafted"
        changed.append(p["id"])
    # a carousel goes out whole: slides without a photo query still need the new group and a re-send
    for p in data["posts"]:
        if p.get("group") in groups and p["id"] not in changed and p["status"] in {"awaiting", "drafted", "rendered"}:
            p["group"], p["id"], p["status"] = groups[p["group"]], _next_rev(p["id"]), "drafted"
            changed.append(p["id"])
    save_week(data)
    log(f"rephoto {label}: {len(changed)} post(s) get new photos")
    return changed


PHOTO_HOW_TO = ("📷 To put a photo on a post: <b>reply to that post's card</b> with the photo, and make the caption's "
                 "first line say where it came from:\n<code>yangu</code>  we took it\n"
                 "<code>ruhusa @who (how they said yes)</code>  the photographer agreed\n"
                 "<code>chanzo @StateHouseKenya https://link</code>  a photo already posted online, credited to "
                 "whoever posted it (news and commentary use, with credit)\n"
                 "Photo agencies (Getty, AFP, Reuters, AP...) are the exception: they sell their photos and bill for reuse.")
SOURCE_LINE = re.compile(r"^\s*(chanzo|source|via|kutoka|credit)\b[\s:,-]*(.+)$", re.I)
# Agencies and stock libraries license photos for money and file claims; a credit is not enough for them
PAID_PHOTOS = re.compile(r"\b(getty|afp|reuters|associated press|\bap\b|ap photo|shutterstock|alamy|xinhua|anadolu|"
                         r"epa|istock|adobe stock|dreamstime|bloomberg)\b", re.I)


def _posted_source(caption: str) -> dict | None:
    """'chanzo @StateHouseKenya https://x.com/...' -> the credit for a photo already posted online."""
    first = next((ln.strip() for ln in (caption or "").splitlines() if ln.strip()), "")
    m = SOURCE_LINE.match(first)
    if not m:
        return None
    url = re.search(r"https?://\S+", m.group(2))
    credit = re.sub(r"https?://\S+", "", m.group(2)).strip(" ,;-")
    if len(credit) < 2 and url:
        credit = urllib.parse.urlsplit(url.group(0)).netloc.removeprefix("www.")
    if len(credit) < 2:
        return None
    return {"rights": "posted", "credit": credit[:60], "source": url.group(0) if url else "", "evidence": first[:160]}


def _is_image(msg: dict) -> bool:
    doc = msg.get("document") or {}
    return bool(msg.get("photo")) or str(doc.get("mime_type", "")).startswith("image/")


def _photo_intake(msg: dict, chat: str) -> None:
    """You replied to a card with a photo: that post gets your picture, a new id and a fresh card.
    Only photos you took or have permission for (first caption line, as for clips)."""
    import tazama

    def reply(text: str) -> None:
        try:
            tg("sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML", "reply_to_message_id": msg["message_id"]})
        except Exception as e:
            log(f"photo reply skipped: {e}")

    target = (msg.get("reply_to_message") or {}).get("message_id")
    hit = None
    for f in sorted(WEEKS.glob("*.json"), reverse=True)[:3] if target else []:
        data = json.loads(f.read_text(encoding="utf-8"))
        post = next((p for p in data["posts"] if p.get("tg_msg") == target), None)
        if post:
            hit = (data, post)
            break
    if not hit:
        return reply(PHOTO_HOW_TO)
    data, post = hit
    if post["status"] not in {"awaiting", "approved"} or post.get("group"):
        return reply(f"📷 <b>{_esc(post['id'])}</b> can't take a new photo now ({_esc(post['status'])}).")
    rights = tazama.parse_caption(msg.get("caption", ""))
    if not rights or rights["rights"] not in {"own", "permission"}:
        rights = _posted_source(msg.get("caption", ""))
    if not rights:
        return reply("📷 Got the photo, but I can't use it yet.\n\n" + PHOTO_HOW_TO)
    if rights["rights"] == "posted" and PAID_PHOTOS.search(rights["evidence"]):
        return reply("📷 That's an agency photo: agencies sell their photos and bill for reuse, so a credit isn't "
                     "enough. Use the same moment from the office's or politician's own page instead.")
    photo = (msg.get("document") if not msg.get("photo") else max(msg["photo"], key=lambda x: x.get("width", 0)))
    if not msg.get("document") and photo.get("width", 0) < 800:
        return reply("📷 That photo is too small (under 800 px wide). Send the original, or send it as a file.")
    label = data["collection"]
    new_id = _next_rev(post["id"])
    rel = Path("exports") / label / "photos" / f"{new_id}-sent.jpg"
    try:
        (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
        tazama.download(_tg_file_path, need("TELEGRAM_BOT_TOKEN")["TELEGRAM_BOT_TOKEN"], photo["file_id"], ROOT / rel)
        from PIL import Image
        with Image.open(ROOT / rel) as im:   # whatever arrived (PNG, HEIC-as-JPEG...), store a clean JPEG
            im.convert("RGB").save(ROOT / rel, "JPEG", quality=92)
    except Exception as e:
        return reply(f"📷 Couldn't download that photo ({_esc(str(e)[:120])}). Try again.")
    credit = {"own": "Photo: Kenya on Record", "permission": f"Photo: {rights['credit']} (with permission)",
              "posted": f"Photo: {rights['credit']}"}[rights["rights"]]
    for k in ("photo_file", "photo_credit", "photo_kind", "tg_msg", "decided_at", "video_file", "video_credit", "video_source"):
        post.pop(k, None)
    post.update(id=new_id, photo=f"sent:{rel.as_posix()}", photo_rights_credit=credit, photo_rights=rights["evidence"],
                photo_source=rights.get("source", ""), photo_use=rights["rights"], status="drafted")
    save_week(data)
    log(f"photo swap: {new_id} ({rights['rights']})")
    reply(f"📷 Got it. <b>{_esc(new_id)}</b> gets your photo; the new card comes back here in a few minutes for ✅. "
          "The old card's buttons no longer do anything.")


def swapwork() -> int:
    """Renders and re-sends posts whose photo you swapped (status drafted after a photo reply)."""
    done = 0
    for f in sorted(WEEKS.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if any(p["status"] == "drafted" and str(p.get("photo", "")).startswith("sent:") for p in data["posts"]):
            render_week(data["collection"])
            ask(data["collection"])
            done += 1
    return done


def _clip_intake(msg: dict, chat: str) -> None:
    import tazama
    reply, clip = tazama.intake(msg, now())
    if clip:
        data = tazama.load()
        data["clips"].append(clip)
        tazama.save(data)
        log(f"clip queued: {clip['id']} ({clip['rights']})")
    if reply:
        try:
            tg("sendMessage", {"chat_id": chat, "text": reply, "parse_mode": "HTML", "reply_to_message_id": msg["message_id"]})
        except Exception as e:
            log(f"clip reply skipped: {e}")


def _tg_file_path(file_id: str) -> str:
    return tg("getFile", {"file_id": file_id})["result"]["file_path"]


def _next_slot(min_lead: dt.timedelta = dt.timedelta(hours=2)) -> dt.datetime:
    """The next prime-time slot (12:30 or 19:00 EAT) at least two hours away."""
    t = now()
    for day in range(3):
        d = (t + dt.timedelta(days=day)).date()
        for hh, mm in ((12, 30), (19, 0)):
            slot = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=EAT)
            if slot - t >= min_lead:
                return slot
    return t + min_lead


def process_clips(dry_run: bool = False) -> int:
    """Turns queued clips into Tazama Hii Reels and sends them for approval. Raw clips stay in a temp folder."""
    import draft as drafter
    import guard
    import news
    import radar
    import tazama
    data = tazama.load()
    queued = [c for c in data["clips"] if c["status"] == "queued"]
    if not queued or dry_run:
        log(f"clips: {len(queued)} queued{' (dry run)' if dry_run else ''}")
        return 0
    token = need("TELEGRAM_BOT_TOKEN")["TELEGRAM_BOT_TOKEN"]
    label = current_week_label(ahead=0)
    made = 0
    for c in queued:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "clip.mp4"
                tazama.download(_tg_file_path, token, c["file_id"], src)
                import video
                meta = tazama.probe(video.ffmpeg_bin(), src)
                segments = tazama.transcribe(src)
                post = tazama.write(drafter.call_claude, c, meta["duration"], segments,
                                    news.prompt_block() + radar.prompt_block())
                post.update(id=f"{label.lower()}-tazama-{c['id'][5:]}", publish_at=_next_slot().isoformat(), clip=c["id"])
                a, b = tazama.window(post, c, meta["duration"])
                post["clip_window"] = [a, b]
                report = guard.check(post)
                post["guard"] = {"errors": report.errors, "warnings": report.warnings}
                if not report.ok:
                    raise RuntimeError("; ".join(report.errors)[:300])
                tazama.make(post, c, src, segments, EXPORTS / label)
            post["status"] = "rendered"
            week = load_week(label) if week_file(label).exists() else {"collection": label, "created": now().isoformat(),
                                                                        "posts": [], "scripts": {}}
            week["posts"].append(post)
            save_week(week)
            c.update(status="made", post=post["id"])
            made += 1
        except Exception as e:
            c.update(status="failed", error=str(e)[:300])
            log(f"clip {c['id']} failed: {e}")
            _notify(f"🎬 Couldn't make the Reel from your clip ({_esc(c['id'])}): {_esc(str(e)[:250])}")
        tazama.save(data)
    if made:
        ask(label)
    return made


def send_reels(label: str, dry_run: bool = False) -> int:
    """Re-sends this week's Reels that still wait for your decision, each with its ✅/❌/🎵 buttons."""
    data = load_week(label)
    fresh = {p["id"] for p in data["posts"] if p["status"] == "rendered"}
    if fresh:   # cards whose upload failed last time: send them once, with buttons
        data = ask(label, dry_run=dry_run)
    chat = "dry-run" if dry_run else need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"]
    sent = 0
    for p in data["posts"]:
        video = EXPORTS / label / f"{p['id']}.mp4"
        if p["status"] != "awaiting" or p.get("n") or not video.exists() or p["id"] in fresh:
            continue
        if dry_run:
            log(f"[dry-run] would send reel {p['id']}")
        else:
            tg("sendVideo", {"chat_id": chat, "caption": _preview_text(p), "parse_mode": "HTML", "supports_streaming": "true",
                             "reply_markup": _buttons(f"{label}|{p['id']}", reel=True)}, {"video": video})
        sent += 1
    log(f"reels sent: {sent}")
    return sent


def balance_note(data: dict) -> str | None:
    """Fairness check for the week: who we held to account and who we credited, so no side gets a free pass."""
    posts = [p for p in data["posts"] if not p.get("n") and p["status"] in {"awaiting", "approved", "published", "manual"}]
    if len(posts) < 3:
        return None
    count = lambda side, tone: sum(1 for p in posts if p.get("side") in {side, "both"} and p.get("tone") == tone)
    g_c, g_k, o_c, o_k = count("government", "criticism"), count("government", "credit"), count("opposition", "criticism"), count("opposition", "credit")
    lines = [f"⚖️ <b>Balance this week</b>: government {g_c} criticised · {g_k} credited; opposition {o_c} criticised · {o_k} credited."]
    if g_c + o_c >= 3 and (g_c == 0 or o_c == 0):
        lines.append("Every criticism is on one side. If the other side did wrong this week, a post on it keeps us fair.")
    if g_k + o_k == 0:
        lines.append("No credit yet. If someone delivered something real, one sourced line of credit makes our criticism believable.")
    return "\n".join(lines)


def held_summary(data: dict) -> str | None:
    held = [p for p in data["posts"] if p["status"] == "needs_human"]
    if not held:
        return None
    from html import escape as esc
    lines = [f"• <b>{esc(p['id'])}</b>: {esc('; '.join((p.get('guard') or {}).get('errors') or ['check needed'])[:160])}" for p in held]
    return (f"🛠 {len(held)} post(s) held back, not sent for approval:\n" + "\n".join(lines) +
            "\n\nTo fix automatically: GitHub → Actions → autopilot → Run workflow → <code>redo</code>.")


def render_week(label: str) -> dict:
    import render as renderer
    from PIL import Image

    data = load_week(label)
    todo = [p for p in data["posts"] if p["status"] == "drafted"]
    if not todo:
        log("nothing to render")
        return data
    out_dir = EXPORTS / label
    import photos
    photos.attach(todo, out_dir)   # real photos where the writer asked for one (skipped quietly without a key)
    try:   # the TV clip of the story, for the card: you can add up to 8 s of it as a Tazama Hii Reel
        import radar
        for p in todo:
            if p["template"] in CLIP_TEMPLATES or p.get("hot"):
                clip = radar.clip_for(p)
                if clip:
                    p["tv_clip"] = clip
    except Exception as e:
        log(f"TV clip match skipped: {e}")
    import videos
    try:   # real moving footage for showcase Reels and posts that only have a symbolic photo
        videos.attach([p for p in todo if is_reel(p)], out_dir)
    except Exception as e:   # footage is a bonus: the photo Reel still goes out
        log(f"footage skipped: {e}")
    qa: dict = {}
    renderer.render(todo, out_dir, qa=qa)
    for p in todo:
        png = out_dir / f"{p['id']}.png"
        Image.open(png).convert("RGB").save(out_dir / f"{p['id']}.jpg", "JPEG", quality=90, optimize=True)
        if p["template"] == "kenya" and not p.get("photo_file"):   # a showcase without the real place is nothing
            p["status"] = "needs_human"
            p.setdefault("guard", {}).setdefault("errors", []).append(
                "no real photo of this place or project was found: redraft with another one")
        elif qa.get(p["id"]):  # visual QA found overflow or collisions: a human must look first
            p["status"] = "needs_human"
            p.setdefault("guard", {}).setdefault("errors", []).extend(f"visual QA: {i['what']}" for i in qa[p["id"]])
        else:
            p["status"] = "rendered"
    reel_posts = [p for p in todo if p["status"] == "rendered" and is_reel(p)]
    if reel_posts:
        import video
        video.make_reels(reel_posts, out_dir)
        for p in reel_posts:
            p["reel"] = True
    save_week(data)
    log(f"rendered {len(todo)} designs ({len(reel_posts)} reels) → {out_dir}")
    return data


CLIP_TEMPLATES = {"sauti", "straight", "promise", "kumbuka", "scorecard", "money", "glasspoll"}


def is_reel(p: dict) -> bool:
    cal = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))
    # polls are 9:16 already: as a Reel they reach the feed, and comments (the votes) push them further
    return (p["template"] in set(cal.get("reel_templates", [])) and not p.get("group")
            and (p.get("size", "post") == "post" or p["template"] == "glasspoll"))


# ---------------------------------------------------------------------------
# 4. Ask for approval (Telegram)
# ---------------------------------------------------------------------------
def tg(method: str, fields: dict | None = None, files: dict | None = None) -> dict:
    token = need("TELEGRAM_BOT_TOKEN")["TELEGRAM_BOT_TOKEN"]
    res = http("POST", f"https://api.telegram.org/bot{token}/{method}", fields=fields or {}, files=files)
    if not res.get("ok", True):
        raise RuntimeError(f"Telegram {method}: {res}")
    return res


def _buttons(key: str, reel: bool = False) -> str:
    row = [{"text": "✅ Approve", "callback_data": f"a|{key}"}, {"text": "❌ Reject", "callback_data": f"r|{key}"}]
    if reel:   # real, trending music only exists inside the apps: post it by hand and pick the sound there
        row.append({"text": "🎵 I'll post it", "callback_data": f"m|{key}"})
    return json.dumps({"inline_keyboard": [row]})


def _preview_text(p: dict) -> str:
    """Approval card text (Telegram HTML). Everything from the post is escaped: a caption with '&' or '<3'
    must never break the message. The caption is trimmed on its own so no HTML tag is ever cut in half."""
    from html import escape as esc
    warn = p.get("guard", {}).get("warnings", [])
    when = dt.datetime.fromisoformat(p["publish_at"]).strftime("%a %d %b, %H:%M")
    cap = brand_tags(p.get("caption", ""))
    cap = cap if len(cap) <= 420 else cap[:417].rstrip() + "..."
    lines = [f"<b>{esc(p['id'])}</b> · {esc(p['template'])} · lane: {esc(str(p.get('lane', '-')))}", f"🕒 {when} EAT"]
    if p.get("breaking"):   # several newsrooms are on it now: approve fast and it goes out on the next run
        b = p["breaking"]
        lines = [f"🔴 <b>BREAKING</b>: {esc(b['title'][:120])} ({esc(', '.join(b['outlets'][:4]))}). "
                 "Approve now and it goes out within minutes."] + lines
    if p.get("message"):
        lines += [f"🎯 <i>{esc(p['message'])}</i>" + (f"  ({esc(p['symbol'])})" if p.get("symbol") else "")]
    if p.get("impact"):
        lines += [f"💡 {esc(p['impact'])}"]
    if p.get("action"):
        lines += [f"👉 <b>{esc(p['action'])}</b>"]
    if p.get("side") or p.get("tone"):
        lines += [f"⚖️ {esc(str(p.get('tone', '?')))} · {esc(str(p.get('side', '?')))}"]
    lines += ["", esc(cap)]
    if p.get("trend"):
        lines += ["", f"📈 Riding trend: {esc(str(p['trend']))}"]
    if not p.get("critic") and p.get("template") not in {"tazama"}:
        lines += ["", "⚠️ Not scored by the editor this run: judge it yourself."]
    if p.get("critic"):
        c = p["critic"]
        parts = " · ".join(f"{k} {c[k]}" for k in ("hook", "clarity", "picture", "send", "fresh") if c.get(k) is not None)
        lines += ["", f"⭐ {c.get('avg')}/10  {parts}", f"✏️ {esc(str(c.get('note', '')))}"]
    if p.get("video_file"):
        lines += [f"🎥 Real footage behind the Reel ({esc(str(p.get('video_credit') or ''))})"]
    clip = p.get("tv_clip")
    if clip:
        lines += [f"🎬 TV clip of this story: <a href=\"{esc(clip['url'])}\">{esc(clip['channel'])}: {esc(clip['title'][:80])}</a>",
                  "To add the real footage: screen-record up to 8 seconds of the key moment and send it to me with",
                  f"<code>nukuu {esc(clip['channel'])} {esc(clip['url'])}</code>"]
    kind = p.get("photo_kind")
    if kind == "event":
        lines += ["📷 Photo from the event itself (licensed)"]
    elif kind == "posted":
        lines += [f"📷 The day's photo, from {esc(str(p.get('photo_outlet') or 'the news report'))} (credited)"]
    elif kind == "place":
        lines += ["📷 A real photo of the place itself (licensed, credited)"]
    elif p.get("template") == "kenya" and not p.get("photo_file"):
        lines += ["⚠️ No photo of this place was found. Reply to this card with a real photo, or reject it."]
    elif kind == "file":
        lines += [f"📷 File photo of who the post is about ({esc(str(p.get('photo_outlet') or 'Wikimedia Commons'))}, credited). "
                  "Reply with the day's photo to swap it."]
    elif kind == "yours":
        lines += ["📷 Posted photo, credited (news and commentary use)" if p.get("photo_use") == "posted" else "📷 Your photo"]
    elif p.get("photo_file") and p.get("template") != "tazama" and not p.get("group"):
        lines += ["🖼 Symbolic photo: no licensed photo of the day was found. Reply to this card with the day's photo to swap it."]
    for credit in (p.get("person_credit") or p.get("photo_credit"), p.get("track_credit")):
        if credit:
            lines += [f"©️ {esc(credit)}"]
    if p.get("source"):
        lines += ["", f"📎 Source: {esc(str(p['source']))[:200]}"]
    if warn:
        lines += ["", "⚠️ " + "\n⚠️ ".join(esc(w) for w in warn[:4])]
    text = "\n".join(lines)
    while len(text) > 1024 and len(lines) > 4:   # Telegram caption limit: drop whole lines from the end, never cut a tag
        lines.pop()
        text = "\n".join(lines)
    return text[:1024]


def ask(label: str, dry_run: bool = False) -> dict:
    data = load_week(label)
    chat = need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"] if not dry_run else "dry-run"
    out_dir = EXPORTS / label
    sent_groups: set = set()
    failed: list[str] = []
    for p in data["posts"]:
        if p["status"] != "rendered":
            continue
        group = p.get("group")
        if group:
            if group in sent_groups:
                continue
            members = [m for m in data["posts"] if m.get("group") == group and m["status"] == "rendered"]
            if dry_run:
                log(f"[dry-run] would send carousel {group} ({len(members)} slides)")
            else:
                media = [{"type": "photo", "media": f"attach://f{i}"} for i in range(len(members))]
                try:
                    tg("sendMediaGroup", {"chat_id": chat, "media": json.dumps(media[:10])},
                       {f"f{i}": out_dir / f"{m['id']}.png" for i, m in enumerate(members[:10])})
                    tg("sendMessage", {"chat_id": chat, "text": _preview_text(members[0]), "parse_mode": "HTML",
                                       "reply_markup": _buttons(f"{label}|{group}")})
                except Exception as e:   # one bad upload must not lose the rest of the batch
                    failed.append(group)
                    log(f"send failed for carousel {group}: {e}")
                    sent_groups.add(group)
                    continue
            for m in members:
                m["status"] = "awaiting"
            sent_groups.add(group)
            save_week(data)
            continue
        if dry_run:
            log(f"[dry-run] would send {p['id']}{' (reel)' if p.get('reel') else ''}")
        else:
            try:
                _send_card(chat, label, p, out_dir)
            except Exception as e:
                failed.append(p["id"])
                log(f"send failed for {p['id']}: {e}")
                continue   # stays "rendered", so the next ask/reels run sends it again
        p["status"] = "awaiting"
        save_week(data)
    save_week(data)
    balance = balance_note(data)
    if balance and not dry_run:
        try:
            tg("sendMessage", {"chat_id": chat, "text": balance, "parse_mode": "HTML"})
        except Exception as e:
            log(f"balance note skipped: {e}")
    note = held_summary(data)
    if note:
        log(note.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
        if not dry_run:
            _notify(note)
    if failed and not dry_run:
        _notify(f"📶 {len(failed)} card(s) didn't upload ({', '.join(failed)[:300]}). "
                "They're kept: Run workflow → <code>reels</code> sends them again.")
    return data


def _send_card(chat: str, label: str, p: dict, out_dir: Path) -> None:
    """One approval card. A Reel that won't upload falls back to its still image, so you still get to decide.
    The card's message id is kept on the post: replying to the card with a photo swaps the picture."""
    res = None
    if p.get("reel") and (out_dir / f"{p['id']}.mp4").exists():
        try:
            res = tg("sendVideo", {"chat_id": chat, "caption": _preview_text(p), "parse_mode": "HTML", "supports_streaming": "true",
                                   "reply_markup": _buttons(f"{label}|{p['id']}", reel=True)},
                     {"video": out_dir / f"{p['id']}.mp4"})
        except Exception as e:
            log(f"reel upload failed for {p['id']}, sending the still: {e}")
    if res is None:
        res = tg("sendPhoto", {"chat_id": chat, "caption": _preview_text(p), "parse_mode": "HTML",
                               "reply_markup": _buttons(f"{label}|{p['id']}", reel=bool(p.get("reel")))},
                 {"photo": out_dir / f"{p['id']}.png"})
    msg_id = ((res or {}).get("result") or {}).get("message_id")
    if msg_id:
        p["tg_msg"] = msg_id


# ---------------------------------------------------------------------------
# 5. Collect approvals
# ---------------------------------------------------------------------------
def apply_decision(data: dict, key: str, approve: bool | str) -> list[str]:
    """key = post id or carousel group id; approve = True / False / "manual" (you post it in the app).
    Returns the ids changed."""
    changed = []
    for p in data["posts"]:
        if (p["id"] == key or p.get("group") == key) and p["status"] == "awaiting":
            p["status"] = "manual" if approve == "manual" else "approved" if approve else "rejected"
            p["decided_at"] = now().isoformat()
            changed.append(p["id"])
    return changed


FRESH_WINDOW = dt.timedelta(hours=30)   # check a post this long before its slot
FRESH_RULES = """You check whether a social media post written days ago is still true and still timely TODAY,
against today's Kenyan headlines. Outdated means: the story moved on (the project was finished, the bill passed or
was withdrawn, the official resigned, a court ruled, the deadline passed), a number or date in it is now wrong, or
it reads as old news next to what Kenyans are talking about now. A post that is still accurate is fine even if the
story is quiet. Return ONLY JSON: {"verdict": "ok" | "outdated", "reason": "one sentence, specific"}"""


def freshness_check(dry_run: bool = False) -> list[str]:
    """Posts written ahead get one check against today's news ~a day before they go out. Outdated ones are held
    (never published stale) and redrafted by the run that follows, so a fresh card reaches you in time."""
    import draft as drafter
    try:
        import news
        headlines = news.prompt_block()
    except Exception:
        headlines = ""
    held = []
    for f in sorted(WEEKS.glob("*.json"))[-2:]:
        data = json.loads(f.read_text(encoding="utf-8"))
        changed = False
        for p in data["posts"]:
            if p["status"] not in {"approved", "awaiting"} or p.get("hot") or p.get("n") or p.get("fresh_checked") \
                    or p.get("template") == "tazama":
                continue
            due = dt.datetime.fromisoformat(p["publish_at"]) - now()
            written = dt.datetime.fromisoformat(p.get("drafted_at") or data.get("created") or now().isoformat())
            if not (dt.timedelta(0) < due <= FRESH_WINDOW) or now() - written < dt.timedelta(hours=20):
                continue
            body = json.dumps({k: p.get(k) for k in ("message", "impact", "action", "caption", "who", "where", "when",
                                                        "promise", "reality", "claim", "fact", "line", "question", "verdict")
                               if p.get(k)}, ensure_ascii=False)
            try:
                reply = drafter.extract_json(drafter.call_claude(FRESH_RULES, f"TODAY: {now():%A %d %B %Y}\n{headlines}\n\nPOST:\n{body}",
                                                                 max_tokens=400))
            except Exception as e:
                log(f"freshness check skipped for {p['id']}: {str(e)[:120]}")
                continue
            p["fresh_checked"] = now().isoformat()
            changed = True
            if str(reply.get("verdict", "ok")).lower() == "outdated" and not dry_run:
                why = str(reply.get("reason", "the story has moved on"))[:200]
                p["status"] = "needs_human"
                p.setdefault("guard", {}).setdefault("errors", []).append(f"outdated: {why}")
                held.append(p["id"])
                _notify(f"⏱ <b>{_esc(p['id'])}</b> was held: it went stale since it was written ({_esc(why)}). "
                        "A fresh version is being written now and comes back for ✅.")
        if changed:
            save_week(data)
    log(f"freshness: {held or 'all still current'}")
    return held


def expire_unanswered() -> list[str]:
    """Cards you never tapped don't hang around: two hours after their slot they are marked 'expired' and
    you get one note. Nothing is ever posted without your ✅."""
    gone = []
    for f in sorted(WEEKS.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        hit = [p for p in data["posts"] if p["status"] == "awaiting"
               and now() - dt.datetime.fromisoformat(p["publish_at"]) > EXPIRE_AFTER]
        for p in hit:
            p["status"] = "expired"
        if hit:
            save_week(data)
            gone += sorted({p.get("group") or p["id"] for p in hit})
    if gone:
        log(f"expired (never approved): {gone}")
        _notify("⌛ Not approved in time, so not posted: " + ", ".join(f"<b>{_esc(g)}</b>" for g in gone)
                + ". Their buttons no longer do anything.")
    return gone


def _answer(cq_id: str, text: str) -> None:
    """Stops the button spinner. Telegram refuses answers to taps older than a few minutes; the decision
    still counts, so a refused answer is never an error (the listener usually answered it already)."""
    try:
        tg("answerCallbackQuery", {"callback_query_id": cq_id, "text": text})
    except Exception as e:
        log(f"tap answer skipped: {str(e)[:120]}")


def collect() -> None:
    STATE.mkdir(exist_ok=True)
    offset_file = STATE / "telegram_offset.txt"
    offset = int(offset_file.read_text()) if offset_file.exists() else 0
    allowed_chat = str(need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"])
    updates = tg("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": json.dumps(["callback_query", "message"])})
    weeks: dict[str, dict] = {}
    for u in updates.get("result", []):
        offset = max(offset, u["update_id"] + 1)
        msg = u.get("message")
        if msg and str(msg.get("chat", {}).get("id")) == allowed_chat:
            if _is_image(msg):            # a photo you replied to a card with: swaps that post's picture
                _photo_intake(msg, allowed_chat)
            else:                         # a clip you sent for a Tazama Hii Reel
                _clip_intake(msg, allowed_chat)
            continue
        cq = u.get("callback_query")
        if not cq:
            continue
        if str(cq.get("message", {}).get("chat", {}).get("id")) != allowed_chat:
            continue  # only the owner's chat can approve
        try:
            action, label, key = cq["data"].split("|", 2)
        except ValueError:
            continue
        if action == "c":   # a comment card: c|r|cid reply, c|h|cid hide, c|s|cid skip
            import engage
            if key.startswith("sample-"):
                result = "Sample only: nothing was posted"
            else:
                result = engage.act(STATE, graph, label, key) if meta_ready() else "Instagram isn't connected"
            _answer(cq["id"], result[:190])
            log(f"comment {key}: {result}")
            continue
        if not week_file(label).exists():
            continue
        data = weeks.setdefault(label, load_week(label))
        changed = apply_decision(data, key, "manual" if action == "m" else action == "a")
        verdict = {"a": "Approved ✅", "m": "Yours to post 🎵"}.get(action, "Rejected ❌")
        if not changed:   # an expired, replaced or already-decided card
            _answer(cq["id"], "This card is no longer active (expired or already decided).")
            if action == "a":
                _notify(f"ℹ️ That ✅ was on <b>{_esc(key)}</b>, which is no longer active (expired or already decided). Nothing was posted.")
            continue
        _answer(cq["id"], f"{verdict} ({len(changed)})")
        if action == "a" and changed:   # TikTok, YouTube Shorts and WhatsApp: ready-to-paste, posted from your phone
            post = next(q for q in data["posts"] if q["id"] == changed[0])
            try:
                tg("sendMessage", {"chat_id": allowed_chat, "parse_mode": "HTML", "text": crosspost_text(post)})
            except Exception as e:
                log(f"cross-post package skipped: {e}")
        if action == "m" and changed:
            post = next(q for q in data["posts"] if q["id"] == changed[0])
            from html import escape as esc
            _notify((
                "🎵 <b>Post this Reel yourself</b> (the bot won't): save the video above, then in Instagram or TikTok "
                "tap <b>Add audio</b>, pick a trending Kenyan sound, and turn <b>Original audio</b> down to 0. "
                "The platform licenses that music, so it won't be muted. Caption to paste:\n\n"
                f"<code>{esc(caption_for(post))[:3500]}</code>"))
        log(f"{verdict}: {key}")
    for data in weeks.values():
        save_week(data)
    offset_file.write_text(str(offset))


# ---------------------------------------------------------------------------
# 6. Publish (Instagram + Facebook Page via Graph API)
# ---------------------------------------------------------------------------
def graph(path: str, fields: dict) -> dict:
    cfg = need("META_ACCESS_TOKEN")
    version = os.environ.get("META_GRAPH_VERSION", "v26.0")
    return http("POST", f"https://graph.facebook.com/{version}/{path}", {**fields, "access_token": cfg["META_ACCESS_TOKEN"]})


def public_url(label: str, post_id: str, ext: str = "jpg") -> str:
    base = need("PUBLIC_BASE_URL")["PUBLIC_BASE_URL"].rstrip("/")
    return f"{base}/exports/{label}/{post_id}.{ext}"


def graph_get(path: str, fields: dict) -> dict:
    cfg = need("META_ACCESS_TOKEN")
    version = os.environ.get("META_GRAPH_VERSION", "v26.0")
    q = urllib.parse.urlencode({**fields, "access_token": cfg["META_ACCESS_TOKEN"]})
    return http("GET", f"https://graph.facebook.com/{version}/{path}?{q}")


def meta_check(dry_run: bool = False) -> bool:
    """Reads (never posts) the Page and the Instagram account with the stored token, and says what works."""
    lines, ok = [], True
    if not meta_ready():
        lines.append("❌ Missing secrets: " + ", ".join(k for k in META_KEYS if not os.environ.get(k)))
        ok = False
    else:
        checks = [("Facebook Page", lambda: graph_get(os.environ["META_PAGE_ID"], {"fields": "name,followers_count"}),
                   lambda r: f"{r.get('name')} ({r.get('followers_count', '?')} followers)"),
                  ("Instagram", lambda: graph_get(os.environ["META_IG_USER_ID"], {"fields": "username,followers_count,media_count"}),
                   lambda r: f"@{r.get('username')} ({r.get('followers_count', '?')} followers)"),
                  ("Page link", lambda: graph_get(os.environ["META_PAGE_ID"], {"fields": "instagram_business_account"}),
                   lambda r: "Instagram is linked to the Page" if (r.get("instagram_business_account") or {}).get("id") == os.environ["META_IG_USER_ID"]
                   else "⚠️ the Page links a different Instagram account (check META_IG_USER_ID)")]
        for name, call, show in checks:
            try:
                lines.append(f"✅ {name}: {show(call())}")
            except Exception as e:
                ok = False
                lines.append(f"❌ {name}: {str(e)[:200]}")
        if ok:   # what Instagram actually shows: the latest posts, their type and whether they're live
            try:
                media = graph_get(f"{os.environ['META_IG_USER_ID']}/media", {
                    "fields": "timestamp,media_product_type,media_type,permalink,caption", "limit": "6"}).get("data", [])
                lines.append(f"📸 Latest on Instagram ({len(media)}):")
                for m in media:
                    when = dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")).astimezone(EAT)
                    lines.append(f"  {when:%a %d %b %H:%M} · {m.get('media_product_type', '?')} · "
                                 f"{(m.get('caption') or '')[:50]!s} · {m.get('permalink', '')}")
            except Exception as e:
                lines.append(f"⚠️ Couldn't list Instagram posts: {str(e)[:150]}")
    text = "🔌 <b>Meta connection check</b> (nothing was posted)\n" + "\n".join(_esc(x) for x in lines)
    log(text.replace("<b>", "").replace("</b>", ""))
    if os.environ.get("GITHUB_ACTIONS"):   # readable from the run page and the API, not only the raw log
        print("::notice title=metacheck::" + " | ".join(lines).replace("\n", " ")[:3500])
    if not dry_run:
        _notify(text + ("\n\nAll set: approved posts will publish at their times." if ok else ""))
    return ok


def preflight(url: str, kind: str) -> None:
    """Instagram only accepts media it can fetch with the right Content-Type. Check before we ask it to."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "jua-kesho/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"media not reachable ({e.code}): {url}. Has GitHub Pages finished deploying?") from e
    if not ctype.startswith(kind + "/"):
        raise RuntimeError(f"{url} is served as '{ctype}', Instagram needs {kind}/*. Use GitHub Pages for PUBLIC_BASE_URL.")


def wait_until_ready(container: str, timeout_s: int = 300, every_s: int = 10) -> None:
    """Video containers must finish processing before media_publish."""
    waited = 0
    while waited <= timeout_s:
        status = graph_get(container, {"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            return
        if status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram could not process the video (status {status})")
        time.sleep(every_s)
        waited += every_s
    raise RuntimeError("Instagram video processing timed out")


def share_story(label: str, members: list[dict]) -> str | None:
    """Puts a post that just went out on the Instagram Story too: followers see Stories first, and a Story
    of every post keeps the account in their top row. Same content you approved; never blocks publishing.
    (The API can't add interactive stickers, so polls are voted on in the post's comments.)"""
    first = members[0]
    if first.get("size") == "story" and not first.get("reel"):
        return None   # it already was a Story
    try:
        ig = need("META_IG_USER_ID")["META_IG_USER_ID"]
        if first.get("reel"):
            container = graph(f"{ig}/media", {"media_type": "STORIES", "video_url": public_url(label, first["id"], "mp4")})["id"]
            wait_until_ready(container)
        else:
            container = graph(f"{ig}/media", {"media_type": "STORIES", "image_url": public_url(label, first["id"])})["id"]
            time.sleep(3)
        sid = graph(f"{ig}/media_publish", {"creation_id": container})["id"]
        log(f"story {first['id']}: {sid}")
        return sid
    except Exception as e:
        log(f"story skipped for {first['id']}: {str(e)[:200]}")
        return None


OLD_TAGS = ("#JuaKesho", "#KenyansAreAsking")   # drafts written before a rename carry an old tag


def brand_tags(cap: str) -> str:
    tag = BRAND.get("hashtag", "")
    for old in OLD_TAGS:
        if tag and old != tag:
            cap = cap.replace(old, tag)
    return cap


def caption_for(post: dict) -> str:
    """The approved caption plus credits: the photographer of a real photo, the artist of a licensed track.
    The post's action is always in the caption: added as the last line if the writer left it out."""
    cap = brand_tags(post.get("caption", ""))
    imp = str(post.get("impact") or "").strip()
    if imp and imp.lower()[:30] not in cap.lower():   # what the news changes for Kenyans, above the action
        tags = re.search(r"(\s*(#\w+\s*)+)$", cap)
        body, tail = (cap[:tags.start()], cap[tags.start():]) if tags else (cap, "")
        cap = f"{body.rstrip()}\n\nWhat it means for you: {imp}{tail}"
    act = str(post.get("action") or "").strip()
    if act and act.lower()[:30] not in cap.lower():
        tags = re.search(r"(\s*(#\w+\s*)+)$", cap)
        body, tail = (cap[:tags.start()], cap[tags.start():]) if tags else (cap, "")
        cap = f"{body.rstrip()}\n\n👉 {act}{tail}"
    if post.get("hot") and "send us" not in cap.lower():   # news posts: footage from the scene, credited, is ours to use
        tags = re.search(r"(\s*(#\w+\s*)+)$", cap)
        body, tail = (cap[:tags.start()], cap[tags.start():]) if tags else (cap, "")
        cap = f"{body.rstrip()}\n\n📩 Were you there? Send us your video and we'll credit you.{tail}"
    clip = post.get("credit") if post.get("template") == "tazama" and post.get("rights_kind") != "own" else None
    credits = [f"{icon} {c}" for icon, c in (("📹 Video:", clip), ("🎥", post.get("video_credit")),
                                             ("📷", post.get("person_credit") or post.get("photo_credit")),
                                             ("🎵", post.get("track_credit"))) if c and c not in cap]
    return f"{cap}\n\n" + "\n".join(credits) if credits else cap


def publish_instagram(label: str, members: list[dict]) -> str:
    ig = need("META_IG_USER_ID")["META_IG_USER_ID"]
    first = members[0]
    if first.get("reel"):
        preflight(public_url(label, first["id"], "mp4"), "video")
    for m in members:
        preflight(public_url(label, m["id"]), "image")
    if len(members) > 1:
        children = [graph(f"{ig}/media", {"image_url": public_url(label, m["id"]), "is_carousel_item": "true"})["id"]
                    for m in members[:10]]
        container = graph(f"{ig}/media", {"media_type": "CAROUSEL", "children": ",".join(children),
                                          "caption": caption_for(first)})["id"]
    elif first.get("reel"):   # before the Story check: a 9:16 poll with a video goes out as a Reel
        container = graph(f"{ig}/media", {"media_type": "REELS", "video_url": public_url(label, first["id"], "mp4"),
                                          "cover_url": public_url(label, f"{first['id']}-cover"),
                                          "caption": caption_for(first), "share_to_feed": "true"})["id"]
        wait_until_ready(container)
    elif first.get("size") == "story":
        container = graph(f"{ig}/media", {"media_type": "STORIES", "image_url": public_url(label, first["id"])})["id"]
    else:
        container = graph(f"{ig}/media", {"image_url": public_url(label, first["id"]), "caption": caption_for(first)})["id"]
    time.sleep(3)  # give Instagram a moment to fetch the image before publishing
    return graph(f"{ig}/media_publish", {"creation_id": container})["id"]


def publish_facebook(label: str, members: list[dict]) -> str | None:
    page = need("META_PAGE_ID")["META_PAGE_ID"]
    first = members[0]
    if first.get("size") == "story" and not first.get("reel"):
        return None  # Page stories use a different API; Instagram story only
    if first.get("reel"):   # video is what Facebook pushes (and pays for in Kenya): post the Reel as a Page video
        return graph(f"{page}/videos", {"file_url": public_url(label, first["id"], "mp4"), "description": caption_for(first)})["id"]
    if len(members) == 1:
        return graph(f"{page}/photos", {"url": public_url(label, first["id"]), "caption": caption_for(first)})["id"]
    ids = [graph(f"{page}/photos", {"url": public_url(label, m["id"]), "published": "false"})["id"] for m in members[:10]]
    fields = {"message": caption_for(first)}
    for i, fbid in enumerate(ids):
        fields[f"attached_media[{i}]"] = json.dumps({"media_fbid": fbid})
    return graph(f"{page}/feed", fields)["id"]


def receipts_comment(post: dict) -> str | None:
    """The first comment under every civic post: the sources, so anyone can check us (links aren't clickable in
    Instagram captions, and Kenyans ask for receipts)."""
    parts = [str(post.get(k) or "").strip() for k in ("claim_source", "source")]
    parts = [x for x in dict.fromkeys(parts) if len(x) >= 8 and "sample" not in x.lower()]
    if not parts:
        return None
    return ("Sources:\n" + "\n".join(f"• {x}" for x in parts))[:2000]


def post_receipts(post: dict, ig_id: str | None, fb_id: str | None) -> None:
    text = receipts_comment(post)
    if not text:
        return
    for target in (ig_id, fb_id):
        if not target:
            continue
        try:
            graph(f"{target}/comments", {"message": text})
        except Exception as e:   # a missing comment never undoes a published post
            log(f"receipts comment skipped on {target}: {e}")


def shorts_title(post: dict) -> str:
    """YouTube Shorts title: the news line itself (YouTube allows 100 characters), with #Shorts."""
    first = str((post.get("beats") or [post.get("message") or ""])[0]).replace("*", "").strip()
    return (first[:90].rsplit(" ", 1)[0] if len(first) > 90 else first) + " #Shorts"


def crosspost_text(post: dict) -> str:
    """One Telegram message with everything to post the approved Reel where the API can't: TikTok (with a trending
    sound, which only the app can add), YouTube Shorts and WhatsApp. TikTok and Facebook hold Kenya's largest
    audiences; WhatsApp is where people forward what they trust."""
    from html import escape as esc
    cap = caption_for(post)
    parts = ["📲 <b>Post it everywhere</b> (save the video from the card above):"]
    if post.get("reel"):
        parts += ["", "<b>TikTok</b>: upload, tap <b>Add sound</b>, pick a trending Kenyan sound at low volume. Caption:",
                  f"<code>{esc(cap[:1500])}</code>",
                  "", "<b>YouTube Shorts</b>: title, then the caption as the description:",
                  f"<code>{esc(shorts_title(post))}</code>"]
    parts += ["", "<b>WhatsApp</b> (Channel, Status, your groups), with the image:",
              f"<code>{esc(whatsapp_text(post))[:1200]}</code>"]
    return "\n".join(parts)   # caption 1,500 + WhatsApp 1,200 + labels stay under Telegram's 4,096


def whatsapp_text(post: dict) -> str:
    """A short version for the WhatsApp Channel and Status: the hook, the receipt, where to follow."""
    beats = [b.replace("*", "") for b in (post.get("beats") or [])]
    body = " ".join(beats[:3]) if beats else str(post.get("message") or "")
    src = str(post.get("source") or "").split(";")[0].strip()
    return (body + (f"\n\nSource: {src}" if len(src) >= 8 else "") + "\n\nFollow Kenya on Record for more.").strip()


def fb_link(fb_id: str | None) -> str | None:
    """A link to the published Facebook post, so it can be shared to the owner's own profile (no API can post there)."""
    if not fb_id:
        return None
    if "_" in str(fb_id):
        page, post = str(fb_id).split("_", 1)
        return f"https://www.facebook.com/{page}/posts/{post}"
    return f"https://www.facebook.com/{fb_id}"


def first_of(members: list[dict]) -> dict:
    return next((m for m in members if not m.get("n")), members[0])


def meta_ready() -> bool:
    return all(os.environ.get(k) for k in META_KEYS)


def publish(dry_run: bool = False) -> None:
    connected = meta_ready()
    waiting = 0
    for f in sorted(WEEKS.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        label = data["collection"]
        done = set()
        for p in data["posts"]:
            key = p.get("group") or p["id"]
            if key in done or p["status"] not in {"approved", "publish_failed"}:
                continue
            if dt.datetime.fromisoformat(p["publish_at"]) > now():
                continue
            members = [m for m in data["posts"] if (m.get("group") or m["id"]) == key]
            members.sort(key=lambda m: m.get("n", 0))
            if any(m["status"] not in {"approved", "publish_failed"} for m in members):
                continue  # a carousel only goes out when every slide is approved
            if p.get("attempts", 0) >= MAX_PUBLISH_ATTEMPTS:
                continue
            done.add(key)
            if not p.get("attempts") and now() - dt.datetime.fromisoformat(p["publish_at"]) > LATE_LIMIT:
                for m in members:  # a stale post helps nobody: skip it rather than flood the feed
                    m["status"] = "missed"
                log(f"missed {key}: more than {LATE_LIMIT} past its slot")
                _notify(f"⏭ <b>{_esc(key)}</b> missed its slot and won't be posted late. Re-use the idea in a future week.")
                continue
            if not connected:
                waiting += 1  # keep it approved: it goes out once Instagram is connected (if still on time)
                continue
            if dry_run:
                log(f"[dry-run] would publish {key} ({len(members)} image(s))")
                continue
            try:
                ig_id = publish_instagram(label, members)
                fb_id = publish_facebook(label, members)
                for m in members:
                    m.update(status="published", published_at=now().isoformat(), ig_id=ig_id, fb_id=fb_id)
                post_receipts(first_of(members), ig_id, fb_id)
                story = share_story(label, members)
                if story:
                    for m in members:
                        m["story_id"] = story
                record_evidence(members)
                log(f"published {key} (ig {ig_id}, fb {fb_id})")
                link = fb_link(fb_id)
                _notify(f"✅ Published <b>{_esc(key)}</b>."
                        + (f" Share it to your profile: <a href=\"{_esc(link)}\">open the post</a> → Share." if link else "")
                        + " Forward it to the WhatsApp Channel too.")
            except Exception as e:  # keep going; record and retry next tick
                for m in members:
                    m["status"] = "publish_failed"
                    m["attempts"] = m.get("attempts", 0) + 1
                    m["last_error"] = str(e)[:400]
                log(f"FAILED {key}: {e}")
                _notify(f"⚠️ Publishing <b>{_esc(key)}</b> failed (attempt {p.get('attempts', 1)}): {_esc(str(e)[:300])}")
        save_week(data)
    if waiting and not dry_run:
        log(f"Instagram not connected yet: {waiting} approved post(s) waiting")
        flag = STATE / "meta_missing_notified.txt"
        if not flag.exists():  # tell the owner once, not every 2 hours
            _notify(f"📌 {waiting} approved post(s) are due, but Instagram isn't connected yet. "
                    "Add META_ACCESS_TOKEN, META_PAGE_ID and META_IG_USER_ID in GitHub secrets. "
                    "Posts more than 36 h late are skipped, not dumped.")
            STATE.mkdir(parents=True, exist_ok=True)
            flag.write_text(now().isoformat(), encoding="utf-8")
    elif connected:
        (STATE / "meta_missing_notified.txt").unlink(missing_ok=True)


def send_samples(dry_run: bool = False) -> None:
    """Shows the newest features on Telegram before they go live: the profile kit and sample comment cards."""
    import engage, presence, draft as drafter
    covers = presence.build()[:-1]
    if dry_run:
        log(f"[dry-run] would send {len(covers)} covers and the sample comment cards")
        return
    chat = need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"]
    names = [n for n, _, _ in presence.HIGHLIGHTS]
    media = [{"type": "photo", "media": f"attach://f{i}", "caption": names[i].title()} for i in range(len(covers))]
    media[0]["caption"] = "Highlight covers: " + ", ".join(n.title() for n in names)
    tg("sendMediaGroup", {"chat_id": chat, "media": json.dumps(media)}, {f"f{i}": f for i, f in enumerate(covers)})
    tg("sendPhoto", {"chat_id": chat, "caption": "How the row looks under the bio"},
       {"photo": presence.OUT / "highlights-row.png"})
    plan = "\n".join(f"• <b>{_esc(n.title())}</b>: {_esc(h)}" for n, _, h in presence.HIGHLIGHTS)
    tg("sendMessage", {"chat_id": chat, "parse_mode": "HTML", "text": (
        "🧪 <b>Profile kit</b>\n\n<b>Bio</b>\n<code>Facts today. A better Kenya tomorrow.\nEvery side, same standard.\n"
        "Not with any government or party. 📩 Tips: DM</code>\n\n<b>Pinned</b>\n1. Manifesto carousel: why we exist, our rules, non-partisan\n"
        "2. Best Promise Tracker post\n3. Reel: how we check our facts\n\n<b>Highlights</b>\n" + plan)})
    n = engage.samples(WEEKS, drafter.call_claude, lambda text, buttons: tg(
        "sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML", "reply_markup": buttons}))
    _notify(f"🧪 {n} sample comment cards above. A 🔥-only comment was skipped, as it would be live. "
            "When Instagram is connected these arrive every 2 hours for real.")
    log(f"samples sent: {len(covers)} covers, {n} comment cards")


def _esc(text: str) -> str:
    from html import escape
    return escape(str(text), quote=False)


def _notify(text: str) -> None:
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        try:
            tg("sendMessage", {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text, "parse_mode": "HTML"})
        except Exception as e:
            log(f"notify failed: {e}")


# ---------------------------------------------------------------------------
# Housekeeping: keep the public media folder small (GitHub Pages sites max out around 1 GB)
# ---------------------------------------------------------------------------
KEEP_WEEKS = 6


def prune(keep_weeks: int = KEEP_WEEKS) -> list[str]:
    """Deletes exports for finished weeks older than `keep_weeks`. Platforms keep their own copies once posted."""
    removed = []
    cutoff = now() - dt.timedelta(weeks=keep_weeks)
    for f in sorted(WEEKS.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        times = [dt.datetime.fromisoformat(p["publish_at"]) for p in data["posts"]]
        # Age alone decides: past LATE_LIMIT nothing in the week can publish any more, whatever its status
        # (an unanswered preview, a missed or failed post must not pin the media forever)
        folder = EXPORTS / data["collection"]
        if times and max(times) < cutoff and folder.exists():
            shutil.rmtree(folder)
            removed.append(data["collection"])
    if removed:
        log(f"pruned media for {', '.join(removed)}")
    return removed


# ---------------------------------------------------------------------------
# 7. Learn — pull Instagram results so the next week's drafts improve
# ---------------------------------------------------------------------------
LEARN_METRICS = "reach,saved,shares,comments,likes"
# Asked for separately: a Reel-only metric must never cost us the main numbers if Meta refuses it for a post
REEL_METRICS = "ig_reels_avg_watch_time"


def learn(weeks_back: int = 4) -> dict:
    """Scores every published post from the last few weeks and stores top/bottom performers."""
    token = need("META_ACCESS_TOKEN")["META_ACCESS_TOKEN"]
    version = os.environ.get("META_GRAPH_VERSION", "v26.0")
    rows = []
    for f in sorted(WEEKS.glob("*.json"))[-weeks_back:]:
        data = json.loads(f.read_text(encoding="utf-8"))
        seen = set()
        for p in data["posts"]:
            key = p.get("group") or p["id"]
            if p["status"] != "published" or not p.get("ig_id") or key in seen:
                continue
            seen.add(key)
            try:
                res = http("GET", f"https://graph.facebook.com/{version}/{p['ig_id']}/insights?"
                                  + urllib.parse.urlencode({"metric": LEARN_METRICS, "access_token": token}))
            except RuntimeError as e:
                log(f"insights unavailable for {key}: {e}")
                continue
            m = {d["name"]: (d.get("values") or [{}])[0].get("value", 0) for d in res.get("data", [])}
            if p.get("reel"):   # how long people stayed: the measure of the skip rate we can get from the API
                try:
                    rr = http("GET", f"https://graph.facebook.com/{version}/{p['ig_id']}/insights?"
                                     + urllib.parse.urlencode({"metric": REEL_METRICS, "access_token": token}))
                    ms = {d["name"]: (d.get("values") or [{}])[0].get("value", 0) for d in rr.get("data", [])}
                    if ms.get("ig_reels_avg_watch_time") is not None:
                        m["avg_watch_s"] = round(float(ms["ig_reels_avg_watch_time"]) / 1000, 1)
                except (RuntimeError, ValueError, TypeError) as e:
                    log(f"watch time unavailable for {key}: {str(e)[:120]}")
            reach = max(1, m.get("reach", 0))
            score = round((m.get("saved", 0) * 3 + m.get("shares", 0) * 4 + m.get("comments", 0) * 2
                           + m.get("likes", 0)) * 1000 / reach, 1)
            rows.append({"id": key, "series": p["template"], "lane": p.get("lane", "-"), "score": score,
                         "opening": str((p.get("beats") or [""])[0]).replace("*", "")[:90], **m})
    rows.sort(key=lambda r: r["score"], reverse=True)
    out = {"updated": now().isoformat(), "top": rows[:5], "bottom": rows[-3:] if len(rows) > 5 else [], "all": rows}
    STATE.mkdir(exist_ok=True)
    (STATE / "learnings.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"learned from {len(rows)} posts")
    return out


# ---------------------------------------------------------------------------
# Status and CLI
# ---------------------------------------------------------------------------
def status(label: str) -> None:
    data = load_week(label)
    for p in data["posts"]:
        extra = f"  ← {p['last_error'][:80]}" if p.get("last_error") else ""
        print(f"{p['status']:15} {p['publish_at'][:16]}  {p['id']}{extra}")
    if data.get("scripts"):
        print("\nscripts:", ", ".join(k for k, v in data["scripts"].items() if v))


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Say so on Telegram: a silent failure looks like "the posts never came"
        try:
            _notify(f"⚠️ Autopilot stopped: <b>{_esc(type(e).__name__)}</b>: {_esc(str(e)[:600])}\n"
                    "Nothing was posted. Fix it, then run the workflow again (Actions → autopilot → Run workflow).")
        except Exception:
            pass
        raise


def _main(argv: list[str] | None = None) -> int:
    load_env()
    sys.path.insert(0, str(HERE))
    ap = argparse.ArgumentParser(description="Kenya on Record autopilot")
    ap.add_argument("command", choices=["week", "hot", "tick", "plan", "draft", "render", "ask", "collect", "publish", "learn", "trends",
                                        "news", "status", "redo", "engage", "samples", "remake", "renew", "photocheck", "rephoto", "radar", "reels", "clips", "clipwork", "metacheck", "aicheck", "swapwork", "tracker"])
    ap.add_argument("--week", help="ISO week label, e.g. 2026-W40 (default: next week)")
    ap.add_argument("--mock", action="store_true", help="draft without the AI (testing)")
    ap.add_argument("--evening", action="store_true", help="hot: the evening edition (a different story)")
    ap.add_argument("--morning", action="store_true", help="hot: the morning edition")
    ap.add_argument("--breaking", action="store_true", help="hot: only if several newsrooms report a new story now")
    ap.add_argument("--dry-run", action="store_true", help="don't call Telegram/Meta")
    a = ap.parse_args(argv)
    label = a.week or current_week_label()

    if a.command == "learn":
        learn()
    elif a.command == "week" and not a.mock and os.environ.get("META_ACCESS_TOKEN"):
        try:   # learning from last week's numbers must never stop this week's drafts
            learn()
        except Exception as e:
            log(f"learn skipped: {e}")
    if a.command in {"week", "tracker", "hot", "trends", "news", "remake", "renew", "radar", "photocheck"} and not a.mock:
        try:
            import trends
            t = trends.collect()
            log(f"trends: {len(t['safe'])} safe, {len(t['dropped'])} dropped, errors {t['errors'] or 'none'}")
        except Exception as e:
            log(f"trends skipped: {e}")
        try:
            import news
            n = news.collect()
            log(f"news: {len(n['items'])} stories, errors {n['errors'] or 'none'}")
        except Exception as e:
            log(f"news skipped: {e}")
        try:
            import radar
            r = radar.collect()
            log(f"radar: {len(r['x'])} X trends, {len(r['videos'])} clips, errors {r['errors'] or 'none'}")
        except Exception as e:
            log(f"radar skipped: {e}")
    sent_file = STATE / "radar_sent.txt"   # the hot run can start twice (listener + schedule): one radar a day
    radar_done = a.command == "hot" and sent_file.exists() and sent_file.read_text().strip() == str(now().date())
    if a.command in {"hot", "radar"} and not a.mock and not a.dry_run and not radar_done:
        try:   # the daily radar on Telegram: live hashtags and the clips Kenya is watching, with links
            import radar
            text = radar.telegram_text()
            if text:
                tg("sendMessage", {"chat_id": need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"], "text": text,
                                   "parse_mode": "HTML", "disable_web_page_preview": "true"})
                STATE.mkdir(parents=True, exist_ok=True)
                sent_file.write_text(str(now().date()))
        except Exception as e:
            log(f"radar message skipped: {e}")
    if a.command == "hot":
        label = hot_slot(a.mock, edition="breaking" if a.breaking else "morning" if a.morning
                         else "evening" if a.evening else "midday")
        if not label:
            return 0
    if a.command == "tracker":   # next week as a Development Tracker batch, drafted and sent now
        label = a.week or current_week_label(ahead=1)
        if not tracker(label):
            return 0
    if a.command in {"week", "plan"}:
        plan(label)
    if a.command == "redo":
        if not a.week:  # the newest week that actually has held posts, whatever day it is
            held = [f.stem for f in sorted(WEEKS.glob("*.json"))
                    if any(q["status"] == "needs_human" for q in json.loads(f.read_text(encoding="utf-8"))["posts"])]
            label = held[-1] if held else label
        redo(label)
    if a.command == "remake":
        label = a.week or current_week_label(ahead=0)
        if remake(label) and not a.dry_run:
            _notify(f"♻️ Fresh batch for <b>{label}</b> coming up: new drafts, real photos. "
                    "Buttons on the older cards for these posts no longer do anything.")
    if a.command == "renew":   # next week again under the current rules, approved posts included
        label = a.week or current_week_label(ahead=1)
        if remake(label, replace_approved=True) and not a.dry_run:
            _notify(f"♻️ <b>{label}</b> redrafted under the new rules (real photos, plain sentences, demands, "
                    "Kenya showcase posts). Approve again: buttons on the older cards no longer do anything.")
    if a.command == "rephoto":
        label = a.week or current_week_label(ahead=0)
        if rephoto(label) and not a.dry_run:
            _notify(f"🖼 New photos for <b>{label}</b> coming up (same words). Buttons on the older cards no longer do anything.")
    if a.command in {"week", "tracker", "hot", "redo", "draft", "remake", "renew"}:
        # only the weekly run writes ahead in two halves; a batch you asked for, a redo or today's post is written now
        draft(label, mock=a.mock, horizon=DRAFT_AHEAD if a.command == "week" else None)
    if a.command in {"week", "tracker", "hot", "redo", "render", "remake", "renew", "rephoto"}:
        render_week(label)
    if a.command in {"week", "tracker", "hot", "redo", "ask", "remake", "renew", "rephoto"}:
        ask(label, dry_run=a.dry_run)
    if a.command in {"tick", "collect"} and not a.dry_run:
        collect()
    if a.command == "tick":
        expire_unanswered()
        if not a.dry_run:
            try:   # posts written days ahead are checked against today's news before they go out
                freshness_check()
            except Exception as e:
                log(f"freshness check failed: {e}")
        if not a.dry_run:
            try:   # keep 6 days of Kenyan news reports, so each post can find its story's photo
                import posted
                log(f"photo archive: {posted.collect()} new reports")
            except Exception as e:
                log(f"photo archive skipped: {e}")
    if a.command in {"tick", "publish"}:
        publish(dry_run=a.dry_run)
    if a.command in {"tick", "engage"} and not a.dry_run and meta_ready():
        try:   # answering comments must never stop publishing
            import engage, draft as drafter
            chat = need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"]
            own = {os.environ.get("META_IG_USER_ID", ""), os.environ.get("META_PAGE_ID", "")}
            n = engage.run(STATE, WEEKS, graph_get, drafter.call_claude,
                           lambda text, buttons: tg("sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML",
                                                                    "reply_markup": buttons}), now(), own)
            log(f"comments: {n} sent for your decision")
        except Exception as e:
            log(f"comments skipped: {e}")
    if a.command == "samples":
        send_samples(dry_run=a.dry_run)
    if a.command == "clips" and not a.dry_run:
        collect()   # pick up clips you just sent
    if a.command in {"clips", "clipwork"}:
        process_clips(dry_run=a.dry_run)
    if a.command == "swapwork" and not a.dry_run:
        swapwork()
    if a.command == "aicheck":   # one tiny call to the writer: which provider answers, and does it work
        import draft as drafter
        try:
            reply = drafter.call_claude("Answer with one word.", "Say OK.", max_tokens=20).strip()
            msg = f"🧠 Writer check: {drafter.provider()} answered '{reply[:30]}'. " + (
                "Free writer active." if drafter.provider() == "gemini" else "Using the paid Claude key.")
            log(msg)
            if not a.dry_run:
                _notify(_esc(msg))
        except Exception as e:
            log(f"writer check failed ({drafter.provider()}): {e}")
            return 1
    if a.command == "metacheck" and not meta_check(dry_run=a.dry_run):
        return 1   # a failed check shows on the run page too, with the reason
    if a.command == "reels":
        send_reels(a.week or current_week_label(ahead=0), dry_run=a.dry_run)
    if a.command == "photocheck":   # searches this week's photo queries again and explains each result (state/photos.log)
        import photos
        wk = a.week or current_week_label(ahead=0)
        posts = [dict(p) for p in load_week(wk)["posts"] if p.get("photo_query")]
        photos.attach(posts, EXPORTS / "_photocheck" / "photos")
        found = sum(1 for p in posts if p.get("photo_file"))
        log(f"photocheck {wk}: {found}/{len(posts)} found a photo (details in state/photos.log)")
        import radar
        import videos
        reels = [p for p in posts if is_reel(p)]
        videos.attach(reels, EXPORTS / "_photocheck")
        for p in posts:
            clip = radar.clip_for(p) if (p["template"] in CLIP_TEMPLATES or p.get("hot")) else None
            photos._note(f"  TV clip for {p['id']}: {clip['channel'] + ': ' + clip['title'] if clip else 'none matched'}")
            if p.get("video_file"):
                photos._note(f"  footage for {p['id']}: {p['video_credit']} ({p.get('video_source', '')})")
        (STATE / "photos.log").write_text("\n".join(photos.NOTES[-400:]) + "\n", encoding="utf-8")
        log(f"photocheck {wk}: footage for {sum(1 for p in reels if p.get('video_file'))}/{len(reels)} Reels")
    if a.command == "tick" and not a.dry_run:
        prune()
    if a.command == "status":
        status(label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
