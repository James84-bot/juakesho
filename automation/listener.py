"""
listener.py — makes the Telegram bot feel live without a server.

GitHub's schedule is best-effort: "every 2 hours" often fires every 6 to 8, so a tap could wait hours. This runs
inside a GitHub Actions job for ~5h45m at a time (free on a public repo) and:

  * answers every ✅/❌/🎵 tap within seconds, so the button stops spinning and you know it landed;
  * starts the autopilot `tick` run right away (taps a few seconds apart share one run);
  * acknowledges clips and photos you send (the tick run makes the Reel or swaps the post's picture);
  * keeps the whole clock: the four daily news editions, the breaking-news checks, the two-hourly tick, Sunday's
    new week, Wednesday's Friday-Sunday drafts and Saturday's weekly show. The autopilot's own schedule stays as a
    backup and the commands are safe to run twice (on 19 Nov the schedule started the 06:35 morning run at 15:04);
  * starts `tick` the moment an approved post is due, so it publishes on time instead of whenever the
    schedule wakes up (a post that is too late is skipped as missed, so this matters);
  * starts a run only while no other autopilot run is waiting: GitHub keeps one waiting run per group and a newer
    one cancels it, so two quick starts would silently lose the first. Commands wait their turn here instead.

It never applies a decision itself and never confirms updates to Telegram (no getUpdates offset), so the
autopilot's collect() still reads every tap and stays the only writer of state. Standard library only.

    python listener.py              # runs until LISTEN_MINUTES (default 345) are up
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

_HOUR = dt.timedelta(hours=1)
POLL_SECONDS = 2.5
DEBOUNCE_SECONDS = 12          # wait this long after the last tap so a burst of taps rides one run
DUE_CHECK_SECONDS = 300        # how often to re-read the week files for posts coming due
REPO = os.environ.get("GITHUB_REPOSITORY", "")
VERDICT = {"a": "✅ Approved. Saving it now; it goes out at its time.",
           "r": "❌ Rejected. It won't be posted.",
           "m": "🎵 Noted. The caption to paste is on its way."}


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def tg(method: str, fields: dict) -> dict:
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}"
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def dispatch(command: str) -> bool:
    """Starts autopilot with `command` (GITHUB_TOKEN may start workflow_dispatch runs)."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/actions/workflows/autopilot.yml/dispatches",
        data=json.dumps({"ref": os.environ.get("GITHUB_REF_NAME", "main"), "inputs": {"command": command}}).encode(),
        method="POST", headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception as e:
        log(f"dispatch {command} failed: {e}")
        return False


def _gh(path: str, raw: bool = False):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/contents/{path}?ref={os.environ.get('GITHUB_REF_NAME', 'main')}",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def schedule() -> list[tuple[str, float]]:
    """(key, epoch) for every approved post in the two newest weeks, read live from the repo so approvals
    made after this listener started are included. key changes with each publish attempt, so a retry is
    started again but a post is never started twice for the same attempt."""
    names = sorted(e["name"] for e in _gh("automation/content/weeks") if e["name"].endswith(".json"))[-2:]
    out = []
    for name in names:
        for p in _gh(f"automation/content/weeks/{name}", raw=True).get("posts", []):
            if p.get("status") in {"approved", "publish_failed"} and p.get("publish_at"):
                at = dt.datetime.fromisoformat(p["publish_at"])
                if at.tzinfo is None:
                    at = at.replace(tzinfo=dt.timezone(dt.timedelta(hours=3)))   # times are EAT
                out.append((f"{p.get('group') or p['id']}#{p.get('attempts', 0)}", at.timestamp()))
    return out


# (command, weekday Mon=0 or None for daily, UTC hour, minute): the same times as autopilot.yml's schedule
CLOCK = (("hot --morning", None, 3, 35),     # 06:35 EAT, out 09:45
         ("hot", None, 6, 5),                # 09:05 EAT, out 12:45
         ("hot --afternoon", None, 9, 30),   # 12:30 EAT, out 15:30
         ("hot --evening", None, 13, 5),     # 16:05 EAT, out 19:30
         *(("hot --breaking", None, h, 40) for h in range(5, 18, 2)),   # 08:40-20:40 EAT
         *(("tick", None, h, 20) for h in range(0, 24, 2)),
         ("week", 6, 14, 0),                 # Sunday 17:00 EAT: next week
         ("this-week", 2, 14, 10),           # Wednesday 17:10 EAT: Friday-Sunday
         ("weekly", 5, 6, 0))                # Saturday 09:00 EAT: Kenya This Week
WAITING = {"queued", "pending", "waiting", "requested"}
PENDING_CHECK_SECONDS = 20     # how often to ask GitHub whether a run is still waiting, while one of ours is held
REDO_DUE_SECONDS = 900         # a due post still unpublished this long after its run (cancelled?) gets another
REDO_DUE_MAX = 3


CLIP_CHECK_SECONDS = 120       # how often to look for TV clips your computer queued (state/tvclips, tvclip_queue.py)


def clips_waiting() -> list[str]:
    """File names of TV clips waiting in state/tvclips; [] when the folder doesn't exist (nothing queued yet)."""
    try:
        return sorted(e["name"] for e in _gh("automation/state/tvclips") if e.get("name", "").endswith(".json"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise


def waiting_runs() -> int:
    """Autopilot runs not yet started (a newer dispatch would cancel the newest of them)."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/actions/workflows/autopilot.yml/runs?per_page=20",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return sum(1 for x in json.loads(r.read()).get("workflow_runs", []) if x.get("status") in WAITING)


def clock_due(utc, fired: set[str]) -> list[str]:
    """Commands whose time came within the same clock hour and that this listener hasn't started yet."""
    out = []
    for command, weekday, hour, minute in CLOCK:
        start = utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
        key = f"{command}-{utc:%Y-%m-%d}-{hour:02d}"   # the tick and breaking checks come several times a day
        if (weekday is None or utc.weekday() == weekday) and start <= utc < start.replace(minute=0) + _HOUR and key not in fired:
            fired.add(key)
            out.append(command)
    return out


def classify(update: dict, chat: str) -> str | None:
    """'tap' or 'clip' for an update from the owner's chat that needs a run; None to ignore it."""
    msg = update.get("message")
    if msg:
        own = str(msg.get("chat", {}).get("id")) == chat
        wake = any(k in msg for k in ("video", "video_note", "document", "photo", "voice", "audio")) or \
            bool(str(msg.get("text", "")).strip())
        return "clip" if own and wake else None
    cq = update.get("callback_query")
    if cq and str(cq.get("message", {}).get("chat", {}).get("id")) == chat:
        return "tap"
    return None


def ack_text(update: dict) -> str:
    data = (update.get("callback_query") or {}).get("data", "")
    if data.startswith("c|"):
        return "Got it. Working on it now."
    return VERDICT.get(data.split("|", 1)[0], "Got it.")


def run(minutes: float) -> None:
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    end = time.time() + minutes * 60
    seen: set[int] = set()
    due: float | None = None            # when to start the tick run
    first = True
    started: dict[str, tuple[float, int]] = {}   # post key -> (when its publishing run was started, how many times)
    fired: set[str] = set()             # clock commands already queued by this listener
    queue: list[str] = []               # commands waiting for a free turn (no autopilot run waiting to start)
    failures: dict[str, int] = {}
    next_turn = 0.0
    upcoming: list[tuple[str, float]] = []
    next_check = 0.0
    next_clips = 0.0

    def enqueue(command: str) -> None:
        if command not in queue:
            queue.append(command)

    def take_turn() -> None:
        """Starts the first queued command once no autopilot run is waiting, so nothing is cancelled."""
        nonlocal next_turn
        if not queue or time.time() < next_turn:
            return
        next_turn = time.time() + PENDING_CHECK_SECONDS
        try:
            if waiting_runs():
                return
        except Exception as e:
            log(f"run check failed ({e!r}); starting anyway")
        command = queue.pop(0)
        if dispatch(command):
            log(f"started autopilot {command}")
        elif failures.setdefault(command, 0) < 4:
            failures[command] += 1
            queue.insert(0, command)    # GitHub refused or the line dropped: try again on the next turn

    while time.time() < end:
        for command in clock_due(dt.datetime.fromtimestamp(time.time(), dt.timezone.utc), fired):
            log(f"clock: {command}")
            enqueue(command)
        if time.time() >= next_check:
            try:
                upcoming = schedule()
            except Exception as e:
                log(f"schedule read failed: {e!r}")
            next_check = time.time() + DUE_CHECK_SECONDS
        if time.time() >= next_clips:
            next_clips = time.time() + CLIP_CHECK_SECONDS
            try:
                clips = clips_waiting()
            except Exception as e:
                log(f"TV clip check failed: {e!r}")
                clips = []
            t = time.time()
            fresh = []
            for name in clips:   # a clip still waiting long after its run started: that run was cancelled or died
                when, n = started.get(f"clip:{name}", (None, 0))
                if when is None or (t - when >= REDO_DUE_SECONDS and n < REDO_DUE_MAX):
                    started[f"clip:{name}"] = (t, n + 1)
                    fresh.append(name)
            if fresh:
                log(f"TV clip waiting: {', '.join(fresh)}")
                enqueue("tvclipwork")
        t = time.time()
        ready = []
        for key, at in upcoming:
            when, n = started.get(key, (None, 0))
            # a post still approved long after its run started: that run was cancelled or died, start another
            if at <= t and (when is None or (t - when >= REDO_DUE_SECONDS and n < REDO_DUE_MAX)):
                started[key] = (t, n + 1)
                ready.append(key)
        if ready:
            due = t if due is None else min(due, t)
            log(f"due now: {', '.join(ready)}")
        try:
            res = tg("getUpdates", {"timeout": 0, "allowed_updates": json.dumps(["callback_query", "message"])})
        except urllib.error.HTTPError as e:
            if e.code != 409:           # 409: the autopilot is reading updates this second; just try again
                log(f"getUpdates {e.code}")
            time.sleep(POLL_SECONDS * 2)
            continue
        except Exception as e:
            log(f"getUpdates failed: {e!r}")
            time.sleep(POLL_SECONDS * 4)
            continue
        for u in res.get("result", []):
            if u["update_id"] in seen:
                continue
            seen.add(u["update_id"])
            kind = classify(u, chat)
            if not kind:
                continue
            if not first:               # leftovers from before this listener started are too old to answer
                try:
                    if kind == "tap":
                        tg("answerCallbackQuery", {"callback_query_id": u["callback_query"]["id"], "text": ack_text(u)})
                    else:
                        tg("sendMessage", {"chat_id": chat, "text": "📥 Got it. Working on it now.",
                                           "reply_to_message_id": u["message"]["message_id"]})
                except Exception as e:
                    log(f"ack failed: {e}")
            due = time.time() + (0 if first else DEBOUNCE_SECONDS)
            log(f"{kind} {u['update_id']}: run queued")
        first = False
        if due is not None and time.time() >= due:
            enqueue("tick")
            due = None
        take_turn()
        time.sleep(POLL_SECONDS)
    if due is not None:                 # never drop a tap that came in during the last seconds
        enqueue("tick")
    # the next listener knows nothing of this queue: hand every command over, each in its own turn (the job has
    # ten minutes of room after LISTEN_MINUTES)
    stop = time.time() + 8 * 60
    while queue and time.time() < stop:
        take_turn()
        time.sleep(POLL_SECONDS)
    if queue:   # starting now would cancel the run that is waiting; the next listener sees due posts and taps again
        log(f"not started (a run was still waiting): {', '.join(queue)}")


if __name__ == "__main__":
    run(float(os.environ.get("LISTEN_MINUTES", "345")))
    sys.exit(0)
