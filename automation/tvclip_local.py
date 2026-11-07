"""
tvclip_local.py — runs on YOUR computer (YouTube refuses downloads from cloud servers, not from a home connection).

Every run it reads this week's posts from the public repo, finds news posts the system matched to a TV clip
(Citizen, NTV, KTN... on YouTube) that haven't gone out yet, downloads the first 2.5 minutes of each clip, sends it
to your Telegram bot (quietly) and tells the autopilot. The autopilot then cuts up to 8 seconds of it into that post's
Reel, with the station named on screen. Each clip is done once.

One-time setup (Windows, PowerShell):
    pip install yt-dlp imageio-ffmpeg
    setx KOR_TELEGRAM_BOT_TOKEN "<the bot token>"      (the same value as the GitHub secret TELEGRAM_BOT_TOKEN)
    setx KOR_TELEGRAM_CHAT_ID "<your chat id>"         (the same value as TELEGRAM_CHAT_ID)
    setx KOR_GITHUB_TOKEN "<fine-grained token>"       (repo James84-bot/juakesho, permission: Contents read and write)
    schtasks /Create /SC MINUTE /MO 30 /TN "KenyaOnRecord TV clips" /TR "python <path>\\tvclip_local.py"

    python tvclip_local.py           # one run
    python tvclip_local.py --check   # says what it would do, sends nothing
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO = "James84-bot/juakesho"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/automation/content/weeks/{{}}.json"
EAT = dt.timezone(dt.timedelta(hours=3))
DONE = Path(__file__).resolve().with_name("tvclip_local_done.json")
SECONDS = 150
MAX_BYTES = 19 * 1024 * 1024        # the bot can fetch files up to 20 MB
WAITING = {"rendered", "awaiting", "approved"}
LEAD = dt.timedelta(minutes=40)     # time the server needs to make the Reel before the post's slot


def _get(url: str, headers: dict | None = None, data: bytes | None = None, method: str = "GET", timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"User-Agent": "KenyaOnRecord-tvclip/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def week_labels(now: dt.datetime) -> list[str]:
    """This ISO week and, on Sunday evening, the next (posts for Monday morning are written the day before)."""
    labels = [f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"]
    nxt = now + dt.timedelta(days=1)
    if nxt.isocalendar()[1] != now.isocalendar()[1]:
        labels.append(f"{nxt.isocalendar()[0]}-W{nxt.isocalendar()[1]:02d}")
    return labels


def wanted(posts: list[dict], done: set[str], now: dt.datetime) -> list[dict]:
    """News posts with a matched TV clip, not yet out, not yet given a clip, with time left to make the Reel."""
    out = []
    for p in posts:
        clip = p.get("tv_clip") or {}
        if not clip.get("url") or p["id"] in done or p.get("tv_clip_used") or p.get("status") not in WAITING:
            continue
        try:
            when = dt.datetime.fromisoformat(p["publish_at"])
        except (KeyError, ValueError):
            continue
        if when - now > LEAD:
            out.append(p)
    return out


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def fetch(url: str, out: Path, ff: str) -> None:
    """The first SECONDS of the clip, made small enough for the bot (540p, re-encoded until it fits)."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.mp4"
        r = subprocess.run([sys.executable, "-m", "yt_dlp", "-q", "--no-playlist", "--no-warnings", "--ffmpeg-location", ff,
                            "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]",
                            "--merge-output-format", "mp4", "--download-sections", f"*0-{SECONDS}", "-o", str(raw), url],
                           capture_output=True, text=True, timeout=600)
        if r.returncode or not raw.exists():
            raise RuntimeError("yt-dlp: " + (r.stderr.strip().splitlines() or ["failed"])[-1][:200])
        for crf in (28, 32, 36):
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-t", str(SECONDS), "-vf", "scale=-2:540",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-c:a", "aac", "-b:a", "96k",
                            "-movflags", "+faststart", str(out)], check=True)
            if out.stat().st_size <= MAX_BYTES:
                return
        raise RuntimeError(f"still {out.stat().st_size // 1_000_000} MB after compressing")


def send_to_bot(token: str, chat: str, video: Path, caption: str) -> str:
    """Uploads the clip to your chat as the bot, without a notification sound; returns its Telegram file id."""
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in {"chat_id": chat, "caption": caption, "disable_notification": "true", "supports_streaming": "true"}.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"clip.mp4\"\r\n"
                 f"Content-Type: video/mp4\r\n\r\n".encode() + video.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    res = json.loads(_get(f"https://api.telegram.org/bot{token}/sendVideo", data=b"".join(parts), method="POST",
                          headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=300))
    media = (res.get("result") or {}).get("video") or (res.get("result") or {}).get("document") or {}
    if not media.get("file_id"):
        raise RuntimeError(f"Telegram did not return the file: {str(res)[:200]}")
    return media["file_id"]


def tell_autopilot(token: str, post: dict, file_id: str) -> None:
    clip = post["tv_clip"]
    body = json.dumps({"event_type": "tvclip", "client_payload": {
        "post": post["id"], "file_id": file_id, "channel": clip.get("channel", "TV"), "url": clip["url"]}}).encode()
    _get(f"https://api.github.com/repos/{REPO}/dispatches", data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"})


def main(argv: list[str]) -> int:
    check = "--check" in argv
    keys = {k: os.environ.get(k, "") for k in ("KOR_TELEGRAM_BOT_TOKEN", "KOR_TELEGRAM_CHAT_ID", "KOR_GITHUB_TOKEN")}
    missing = [k for k, v in keys.items() if not v]
    if missing and not check:
        print("Set these first (see the top of this file): " + ", ".join(missing))
        return 1
    done = set(json.loads(DONE.read_text(encoding="utf-8"))) if DONE.exists() else set()
    now = dt.datetime.now(EAT)
    todo = []
    for label in week_labels(now):
        try:
            todo += wanted(json.loads(_get(RAW.format(label)))["posts"], done, now)
        except urllib.error.HTTPError as e:
            if e.code != 404:   # next week's file may not exist yet
                print(f"{label}: {e}")
    if not todo:
        print(f"{now:%H:%M} nothing waiting for a TV clip")
        return 0
    ff = ffmpeg()
    for p in todo:
        clip = p["tv_clip"]
        print(f"{p['id']}: {clip.get('channel')} | {clip.get('title', '')[:70]}")
        if check:
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                small = Path(tmp) / "clip.mp4"
                fetch(clip["url"], small, ff)
                fid = send_to_bot(keys["KOR_TELEGRAM_BOT_TOKEN"], keys["KOR_TELEGRAM_CHAT_ID"], small,
                                  f"📺 TV clip for {p['id']} (from your computer, for the autopilot)")
            tell_autopilot(keys["KOR_GITHUB_TOKEN"], p, fid)
            print("   sent; the autopilot is making the Reel")
        except Exception as e:
            print(f"   skipped: {e}")
        done.add(p["id"])   # tried once: a clip that fails is not retried every half hour
    DONE.write_text(json.dumps(sorted(done)[-300:]), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
