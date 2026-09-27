"""
pipeline.py — the Jua Kesho autopilot.

    python pipeline.py week   [--week 2026-W40] [--mock]   plan → draft → check → render → ask for approval
    python pipeline.py tick   [--dry-run]                   collect approvals → publish what's due
    python pipeline.py learn                                score recent posts from Instagram insights
    python pipeline.py status [--week 2026-W40]             show every post's state

Individual steps: plan, draft, render, ask, collect, publish.

Every post moves through:
  planned → drafted → rendered → awaiting → approved → published
                 ↘ needs_human (guard failed)   ↘ rejected   ↘ publish_failed (retried up to 3x)

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
import shutil
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
MAX_PUBLISH_ATTEMPTS = 3


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
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:600]
        raise RuntimeError(f"{method} {url.split('?')[0]} → {e.code}: {detail}") from e


# ---------------------------------------------------------------------------
# 1. Plan
# ---------------------------------------------------------------------------
def _pick(value, week_no: int):
    return value[week_no % len(value)] if isinstance(value, list) else value


def plan(label: str) -> dict:
    if week_file(label).exists():
        log(f"{label} already planned, keeping it")
        return load_week(label)
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
    data = {"collection": label, "created": now().isoformat(), "posts": posts, "scripts": {}}
    save_week(data)
    log(f"planned {len(posts)} designs for {label}")
    return data


# ---------------------------------------------------------------------------
# 2. Draft
# ---------------------------------------------------------------------------
def draft(label: str, mock: bool = False) -> dict:
    import draft as drafter
    data = load_week(label)
    todo = [p for p in data["posts"] if p["status"] == "planned"]
    if not todo:
        log("nothing to draft")
        return data
    lanes = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))["lanes"]
    drafted, scripts = drafter.draft_week(label, todo, lanes, mock=mock)
    by_id = {p["id"]: p for p in drafted}
    data["posts"] = [by_id.get(p["id"], p) for p in data["posts"]]
    data["scripts"] = scripts or data.get("scripts", {})
    save_week(data)
    bad = [p["id"] for p in drafted if p["status"] == "needs_human"]
    log(f"drafted {len(drafted)}; needs a human: {bad or 'none'}")
    return data


# ---------------------------------------------------------------------------
# 3. Render (PNG for Telegram/WhatsApp, JPEG for Instagram)
# ---------------------------------------------------------------------------
def render_week(label: str) -> dict:
    import render as renderer
    from PIL import Image

    data = load_week(label)
    todo = [p for p in data["posts"] if p["status"] == "drafted"]
    if not todo:
        log("nothing to render")
        return data
    out_dir = EXPORTS / label
    qa: dict = {}
    renderer.render(todo, out_dir, qa=qa)
    for p in todo:
        png = out_dir / f"{p['id']}.png"
        Image.open(png).convert("RGB").save(out_dir / f"{p['id']}.jpg", "JPEG", quality=90, optimize=True)
        if qa.get(p["id"]):  # visual QA found overflow or collisions: a human must look first
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


def is_reel(p: dict) -> bool:
    cal = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))
    return (p["template"] in set(cal.get("reel_templates", [])) and not p.get("group")
            and p.get("size", "post") == "post")


# ---------------------------------------------------------------------------
# 4. Ask for approval (Telegram)
# ---------------------------------------------------------------------------
def tg(method: str, fields: dict | None = None, files: dict | None = None) -> dict:
    token = need("TELEGRAM_BOT_TOKEN")["TELEGRAM_BOT_TOKEN"]
    res = http("POST", f"https://api.telegram.org/bot{token}/{method}", fields=fields or {}, files=files)
    if not res.get("ok", True):
        raise RuntimeError(f"Telegram {method}: {res}")
    return res


def _buttons(key: str) -> str:
    return json.dumps({"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"a|{key}"},
        {"text": "❌ Reject", "callback_data": f"r|{key}"},
    ]]})


def _preview_text(p: dict) -> str:
    warn = p.get("guard", {}).get("warnings", [])
    when = dt.datetime.fromisoformat(p["publish_at"]).strftime("%a %d %b, %H:%M")
    lines = [f"<b>{p['id']}</b> · {p['template']} · lane: {p.get('lane', '-')}", f"🕒 {when} EAT", "", p.get("caption", "")]
    if p.get("trend"):
        lines += ["", f"📈 Riding trend: {p['trend']}"]
    if p.get("critic"):
        c = p["critic"]
        lines += ["", f"⭐ {c['avg']}/10  hook {c['hook']} · send {c['send']} · fresh {c['fresh']} · voice {c['voice']}",
                  f"✏️ {c['note']}"]
    if p.get("source"):
        lines += ["", f"📎 Source: {p['source']}"]
    if warn:
        lines += ["", "⚠️ " + "\n⚠️ ".join(warn)]
    return "\n".join(lines)[:1024]  # Telegram caption limit


def ask(label: str, dry_run: bool = False) -> dict:
    data = load_week(label)
    chat = need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"] if not dry_run else "dry-run"
    out_dir = EXPORTS / label
    sent_groups = set()
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
                tg("sendMediaGroup", {"chat_id": chat, "media": json.dumps(media[:10])},
                   {f"f{i}": out_dir / f"{m['id']}.png" for i, m in enumerate(members[:10])})
                tg("sendMessage", {"chat_id": chat, "text": _preview_text(members[0]), "parse_mode": "HTML",
                                   "reply_markup": _buttons(f"{label}|{group}")})
            for m in members:
                m["status"] = "awaiting"
            sent_groups.add(group)
            continue
        if dry_run:
            log(f"[dry-run] would send {p['id']}{' (reel)' if p.get('reel') else ''}")
        elif p.get("reel"):
            tg("sendVideo", {"chat_id": chat, "caption": _preview_text(p), "parse_mode": "HTML", "supports_streaming": "true",
                             "reply_markup": _buttons(f"{label}|{p['id']}")},
               {"video": out_dir / f"{p['id']}.mp4"})
        else:
            tg("sendPhoto", {"chat_id": chat, "caption": _preview_text(p), "parse_mode": "HTML",
                             "reply_markup": _buttons(f"{label}|{p['id']}")},
               {"photo": out_dir / f"{p['id']}.png"})
        p["status"] = "awaiting"
    save_week(data)
    return data


# ---------------------------------------------------------------------------
# 5. Collect approvals
# ---------------------------------------------------------------------------
def apply_decision(data: dict, key: str, approve: bool) -> list[str]:
    """key = post id or carousel group id. Returns the ids changed."""
    changed = []
    for p in data["posts"]:
        if (p["id"] == key or p.get("group") == key) and p["status"] == "awaiting":
            p["status"] = "approved" if approve else "rejected"
            p["decided_at"] = now().isoformat()
            changed.append(p["id"])
    return changed


def collect() -> None:
    STATE.mkdir(exist_ok=True)
    offset_file = STATE / "telegram_offset.txt"
    offset = int(offset_file.read_text()) if offset_file.exists() else 0
    allowed_chat = str(need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"])
    updates = tg("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": json.dumps(["callback_query"])})
    weeks: dict[str, dict] = {}
    for u in updates.get("result", []):
        offset = max(offset, u["update_id"] + 1)
        cq = u.get("callback_query")
        if not cq:
            continue
        if str(cq.get("message", {}).get("chat", {}).get("id")) != allowed_chat:
            continue  # only the owner's chat can approve
        try:
            action, label, key = cq["data"].split("|", 2)
        except ValueError:
            continue
        if not week_file(label).exists():
            continue
        data = weeks.setdefault(label, load_week(label))
        changed = apply_decision(data, key, action == "a")
        verdict = "Approved ✅" if action == "a" else "Rejected ❌"
        tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": f"{verdict} ({len(changed)})"})
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
                                          "caption": first.get("caption", "")})["id"]
    elif first.get("size") == "story":
        container = graph(f"{ig}/media", {"media_type": "STORIES", "image_url": public_url(label, first["id"])})["id"]
    elif first.get("reel"):
        container = graph(f"{ig}/media", {"media_type": "REELS", "video_url": public_url(label, first["id"], "mp4"),
                                          "cover_url": public_url(label, f"{first['id']}-cover"),
                                          "caption": first.get("caption", ""), "share_to_feed": "true"})["id"]
        wait_until_ready(container)
    else:
        container = graph(f"{ig}/media", {"image_url": public_url(label, first["id"]), "caption": first.get("caption", "")})["id"]
    time.sleep(3)  # give Instagram a moment to fetch the image before publishing
    return graph(f"{ig}/media_publish", {"creation_id": container})["id"]


def publish_facebook(label: str, members: list[dict]) -> str | None:
    page = need("META_PAGE_ID")["META_PAGE_ID"]
    first = members[0]
    if first.get("size") == "story":
        return None  # Page stories use a different API; Instagram story only
    if len(members) == 1:
        return graph(f"{page}/photos", {"url": public_url(label, first["id"]), "caption": first.get("caption", "")})["id"]
    ids = [graph(f"{page}/photos", {"url": public_url(label, m["id"]), "published": "false"})["id"] for m in members[:10]]
    fields = {"message": first.get("caption", "")}
    for i, fbid in enumerate(ids):
        fields[f"attached_media[{i}]"] = json.dumps({"media_fbid": fbid})
    return graph(f"{page}/feed", fields)["id"]


def publish(dry_run: bool = False) -> None:
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
            if dry_run:
                log(f"[dry-run] would publish {key} ({len(members)} image(s))")
                continue
            try:
                ig_id = publish_instagram(label, members)
                fb_id = publish_facebook(label, members)
                for m in members:
                    m.update(status="published", published_at=now().isoformat(), ig_id=ig_id, fb_id=fb_id)
                log(f"published {key} (ig {ig_id}, fb {fb_id})")
                _notify(f"✅ Published <b>{key}</b>. Forward it to the WhatsApp Channel too.")
            except Exception as e:  # keep going; record and retry next tick
                for m in members:
                    m["status"] = "publish_failed"
                    m["attempts"] = m.get("attempts", 0) + 1
                    m["last_error"] = str(e)[:400]
                log(f"FAILED {key}: {e}")
                _notify(f"⚠️ Publishing <b>{key}</b> failed (attempt {p.get('attempts', 1)}): {str(e)[:300]}")
        save_week(data)


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
        finished = all(p["status"] in {"published", "rejected"} for p in data["posts"])
        folder = EXPORTS / data["collection"]
        if times and max(times) < cutoff and finished and folder.exists():
            shutil.rmtree(folder)
            removed.append(data["collection"])
    if removed:
        log(f"pruned media for {', '.join(removed)}")
    return removed


# ---------------------------------------------------------------------------
# 7. Learn — pull Instagram results so the next week's drafts improve
# ---------------------------------------------------------------------------
LEARN_METRICS = "reach,saved,shares,comments,likes"


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
            reach = max(1, m.get("reach", 0))
            score = round((m.get("saved", 0) * 3 + m.get("shares", 0) * 4 + m.get("comments", 0) * 2
                           + m.get("likes", 0)) * 1000 / reach, 1)
            rows.append({"id": key, "series": p["template"], "lane": p.get("lane", "-"), "score": score, **m})
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
    load_env()
    sys.path.insert(0, str(HERE))
    ap = argparse.ArgumentParser(description="Jua Kesho autopilot")
    ap.add_argument("command", choices=["week", "tick", "plan", "draft", "render", "ask", "collect", "publish", "learn", "trends", "status"])
    ap.add_argument("--week", help="ISO week label, e.g. 2026-W40 (default: next week)")
    ap.add_argument("--mock", action="store_true", help="draft without the AI (testing)")
    ap.add_argument("--dry-run", action="store_true", help="don't call Telegram/Meta")
    a = ap.parse_args(argv)
    label = a.week or current_week_label()

    if a.command == "learn" or (a.command == "week" and not a.mock and os.environ.get("META_ACCESS_TOKEN")):
        learn()
    if a.command in {"week", "trends"} and not a.mock:
        try:
            import trends
            t = trends.collect()
            log(f"trends: {len(t['safe'])} safe, {len(t['dropped'])} dropped, errors {t['errors'] or 'none'}")
        except Exception as e:
            log(f"trends skipped: {e}")
    if a.command in {"week", "plan"}:
        plan(label)
    if a.command in {"week", "draft"}:
        draft(label, mock=a.mock)
    if a.command in {"week", "render"}:
        render_week(label)
    if a.command in {"week", "ask"}:
        ask(label, dry_run=a.dry_run)
    if a.command in {"tick", "collect"} and not a.dry_run:
        collect()
    if a.command in {"tick", "publish"}:
        publish(dry_run=a.dry_run)
    if a.command == "tick" and not a.dry_run:
        prune()
    if a.command == "status":
        status(label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
