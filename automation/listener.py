"""
listener.py — makes the Telegram bot feel live without a server.

GitHub's schedule is best-effort: "every 2 hours" often fires every 6 to 8, so a tap could wait hours. This runs
inside a GitHub Actions job for ~5h45m at a time (free on a public repo) and:

  * answers every ✅/❌/🎵 tap within seconds, so the button stops spinning and you know it landed;
  * starts the autopilot `tick` run right away (taps a few seconds apart share one run);
  * acknowledges clips and photos you send (the tick run makes the Reel or swaps the post's picture);
  * keeps the clock for the daily hot post (09:05 EAT) and Sunday's new week (17:00 EAT); the autopilot's own
    schedule stays as a backup, and the commands are safe to run twice; Wednesday's run writes Friday-Sunday;
  * starts `tick` the moment an approved post is due, so it publishes on time instead of whenever the
    schedule wakes up (a post that is too late is skipped as missed, so this matters).

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


CLOCK = (("hot", None, 6, 5), ("week", 6, 14, 0), ("this-week", 2, 14, 0))   # Wed 17:00 EAT: write Fri-Sun   # (command, weekday Mon=0 or None for daily, UTC hour, minute)


def clock_due(utc, fired: set[str]) -> list[str]:
    """Commands whose time came in the last hour and that this listener hasn't started yet."""
    out = []
    for command, weekday, hour, minute in CLOCK:
        start = utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
        key = f"{command}-{utc:%Y-%m-%d}"
        if (weekday is None or utc.weekday() == weekday) and start <= utc < start.replace(minute=0) + _HOUR and key not in fired:
            fired.add(key)
            out.append(command)
    return out


def classify(update: dict, chat: str) -> str | None:
    """'tap' or 'clip' for an update from the owner's chat that needs a run; None to ignore it."""
    msg = update.get("message")
    if msg:
        own = str(msg.get("chat", {}).get("id")) == chat
        wake = any(k in msg for k in ("video", "document", "photo", "voice", "audio")) or \
            str(msg.get("text", "")).lower().startswith("/voice")
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
    started: set[str] = set()
    fired: set[str] = set()             # clock commands already started by this listener           # posts already given a publishing run
    upcoming: list[tuple[str, float]] = []
    next_check = 0.0
    while time.time() < end:
        for command in clock_due(dt.datetime.fromtimestamp(time.time(), dt.timezone.utc), fired):
            log(f"clock: starting {command}")
            dispatch(command)
        if time.time() >= next_check:
            try:
                upcoming = schedule()
            except Exception as e:
                log(f"schedule read failed: {e!r}")
            next_check = time.time() + DUE_CHECK_SECONDS
        ready = [k for k, at in upcoming if at <= time.time() and k not in started]
        if ready:
            started.update(ready)
            due = time.time() if due is None else min(due, time.time())
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
            if dispatch("tick"):
                log("started autopilot tick")
            due = None
        time.sleep(POLL_SECONDS)
    if due is not None:                 # never drop a tap that came in during the last seconds
        dispatch("tick")


if __name__ == "__main__":
    run(float(os.environ.get("LISTEN_MINUTES", "345")))
    sys.exit(0)
