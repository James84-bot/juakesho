"""
tvclip_queue.py — the waiting line for TV clips your computer sends (tvclip_local.py).

Your computer fetches a clip, uploads it to the Telegram bot and fires a `tvclip` repository_dispatch. That used to
start an autopilot run directly, and GitHub keeps only one waiting run per group: the clip's run cancelled whatever
run was waiting (a news post's publishing run included), or a later run cancelled the clip's (2 of 10 were lost).

Now the dispatch starts the small intake workflow (.github/workflows/tvclip.yml), which only writes one file per
clip into automation/state/tvclips/ and commits it. One file per clip: two intakes never touch the same file, and an
autopilot run never touches a waiting one, so nothing conflicts. The listener sees the file and starts `tvclipwork`
when no run is waiting; pipeline.py makes the Reel and deletes the file. A run that is cancelled loses nothing: the
file stays, and the listener starts another.

Standard library only: the intake job runs this without installing anything.
    PAYLOAD='{"post": ..., "file_id": ...}' python automation/tvclip_queue.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent / "state" / "tvclips"
MAX_TRIES = 3                       # a clip whose run errors is tried this many times, then dropped
MAX_AGE = dt.timedelta(hours=12)    # older than this, its post has gone out: dropped unused
URL = re.compile(r"https://(www\.|m\.)?(youtube\.com|youtu\.be)/")


def clean(payload: dict) -> dict:
    """The fields tvclip_work reads, checked: the payload comes from outside the repo. ValueError if unusable."""
    if not isinstance(payload, dict):
        raise ValueError("payload is not an object")
    post = str(payload.get("post") or "")
    file_id = str(payload.get("file_id") or "")
    url = str(payload.get("url") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", post):
        raise ValueError(f"bad post id {post[:40]!r}")
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,300}", file_id):
        raise ValueError("bad Telegram file id")
    if url and not URL.match(url):
        raise ValueError(f"not a YouTube link: {url[:60]!r}")
    mid = payload.get("message_id")
    whole = (isinstance(mid, int) and not isinstance(mid, bool)) or (isinstance(mid, str) and mid.isdigit())
    mid = int(mid) if whole else None
    return {"post": post, "file_id": file_id,
            "channel": re.sub(r"[^\w .&'-]", "", str(payload.get("channel") or "TV"))[:60].strip() or "TV",
            "url": url, "title": str(payload.get("title") or "")[:300], "message_id": mid,
            "sample": payload.get("sample") is True}


def add(payload: dict, now: dt.datetime | None = None, folder: Path | None = None) -> Path:
    """Writes one clip's file and returns its path. ValueError if the payload is unusable (nothing written)."""
    entry = clean(payload)
    now = now or dt.datetime.now(dt.timezone.utc)
    folder = folder or DIR
    entry.update(queued_at=now.isoformat(timespec="seconds"), tries=0)
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{now:%Y%m%dT%H%M%S}-{entry['post']}"
    n = 0
    while (folder / f"{stem}-{n}.json").exists():   # two in the same second: numbered, still oldest first
        n += 1
    path = folder / f"{stem}-{n}.json"
    path.write_text(json.dumps(entry, indent=1), encoding="utf-8")
    return path


def pending(folder: Path | None = None) -> list[Path]:
    """The clips still waiting, oldest first (file names start with the time they came in)."""
    folder = folder or DIR
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def main() -> int:
    try:
        path = add(json.loads(os.environ.get("PAYLOAD") or "{}"))
    except (ValueError, TypeError) as e:   # nothing queued; the run still succeeds so it doesn't page anyone
        print(f"::warning title=tvclip intake::refused: {e}")
        return 0
    print(f"queued {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
