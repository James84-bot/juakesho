"""
tvclip_local.py — runs on YOUR computer (YouTube refuses downloads from cloud servers, not from a home connection).

Every run it reads this week's posts from the public repo, takes the news posts that haven't gone out yet, finds the
TV story about each one (the clip the system matched, or a search of the last 3 days of Kenyan stations' YouTube
uploads whose title names the same thing), downloads its first 2.5 minutes, sends it to your Telegram bot (quietly)
and tells the autopilot. The autopilot then cuts up to 8 seconds of it into that post's
Reel, with the station named on screen. Each clip is done once.

One-time setup (Windows, PowerShell): keys are typed at a hidden prompt and kept as user environment variables.
    pip install yt-dlp imageio-ffmpeg
    KOR_TELEGRAM_BOT_TOKEN   the same value as the GitHub secret TELEGRAM_BOT_TOKEN
    KOR_TELEGRAM_CHAT_ID     the same value as TELEGRAM_CHAT_ID
    KOR_GITHUB_TOKEN         a fine-grained token: repository James84-bot/juakesho, permission Contents: read and write
    schtasks /Create /SC MINUTE /MO 30 /TN "KenyaOnRecord TV clips" /TR "python <path>\\tvclip_local.py"

    python tvclip_local.py           # one run
    python tvclip_local.py --check   # says what it would do, sends nothing
    python tvclip_local.py --sample  # a sample Reel with a TV clip, on a news post that already went out
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


STATIONS = ("citizen tv", "ntv kenya", "ktn news", "k24 tv", "kbc channel 1", "tv47", "inooro tv", "kameme tv",
            "ramogi tv", "citizen digital", "nation", "the standard")   # Kenyan newsrooms' own YouTube channels
STOP = set("the a an and or of to in on for at by with from as is are was were be been has have had it its this that "
           "these those our your their his her they we you kenya kenyan kenyans now new over after into says said "
           "all six five four three two one first last days day week weeks case cases marked without more less "
           "every each today year years month people government county".split())   # words any story on the topic shares


def keywords(post: dict, n: int = 6) -> list[str]:
    """The words a TV story's title would share with the post: names and numbers first, then the content words."""
    import re
    text = str(post.get("message") or (post.get("beats") or [""])[0]).replace("*", "")
    words = re.findall(r"[A-Za-z][\w'-]+|\d[\d,.]*", text)
    names = [w for w in words if w[0].isupper() and w.lower() not in STOP]
    rest = [w for w in words if w not in names and w.lower() not in STOP and len(w) > 3]
    seen, out = set(), []
    for w in names + rest:
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out[:n]


def matches(title: str, post: dict, need: int = 3) -> bool:
    """A TV story about the same event: its title shares a name and another keyword with the post, or three keywords
    (a name counts double). "Ebola" alone would put a burial clip on a recovery story; "Mariga" + "FKF" is the event."""
    low = title.lower()
    score = sum(2 if k[0].isupper() else 1 for k in keywords(post) if k.lower()[:6] in low)
    return score >= need


def search_clip(post: dict, ff: str, days: int = 3) -> dict | None:
    """Looks the story up on YouTube from this computer: a station's own upload of the last 3 days whose title
    names the same thing. {"url", "channel", "title"} or None."""
    q = " ".join(keywords(post))
    if not q:
        return None
    r = subprocess.run([sys.executable, "-m", "yt_dlp", "-q", "--no-warnings", "--skip-download", "--dateafter",
                        f"now-{days}days", "--match-filter", "duration > 25 & duration < 900", "-J", f"ytsearch10:{q} Kenya news"],
                       capture_output=True, text=True, timeout=300)
    try:
        entries = json.loads(r.stdout or "{}").get("entries") or []
    except ValueError:
        return None
    for e in entries:
        channel = str(e.get("channel") or e.get("uploader") or "")
        if channel.lower().startswith(STATIONS) and matches(str(e.get("title") or ""), post):
            return {"url": e.get("webpage_url") or f"https://www.youtube.com/watch?v={e.get('id')}",
                    "channel": channel, "title": str(e.get("title") or "")}
    return None


def wanted(posts: list[dict], done: set[str], now: dt.datetime) -> list[dict]:
    """News posts not yet out and not yet given a clip, with time left to make the Reel."""
    out = []
    for p in posts:
        if not p.get("hot") and not (p.get("tv_clip") or {}).get("url"):
            continue
        if p["id"] in done or p.get("tv_clip_used") or p.get("status") not in WAITING or not p.get("beats"):
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
        base = [sys.executable, "-m", "yt_dlp", "-q", "--no-playlist", "--no-warnings", "--ffmpeg-location", ff,
                "--merge-output-format", "mp4", "-o", str(raw)]
        # first just the opening minutes; some uploads make ffmpeg fail on a partial download, so then the whole clip
        # (stations' story clips are a few minutes) at the smaller progressive format, cut here afterwards
        attempts = [["-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]",
                     "--download-sections", f"*0-{SECONDS}"],
                    ["-f", "b[height<=480][ext=mp4]/b[height<=720][ext=mp4]/bv*[height<=480]+ba/b"]]
        err = ""
        for extra in attempts:
            raw.unlink(missing_ok=True)
            r = subprocess.run(base + extra + [url], capture_output=True, text=True, timeout=900)
            if not r.returncode and raw.exists():
                break
            err = (r.stderr.strip().splitlines() or ["failed"])[-1][:200]
        else:
            raise RuntimeError("yt-dlp: " + err)
        for crf in (28, 32, 36):
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-t", str(SECONDS), "-vf", "scale=-2:540",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-c:a", "aac", "-b:a", "96k",
                            "-movflags", "+faststart", str(out)], check=True)
            if out.stat().st_size <= MAX_BYTES:
                return
        raise RuntimeError(f"still {out.stat().st_size // 1_000_000} MB after compressing")


def send_to_bot(token: str, chat: str, video: Path, caption: str) -> tuple[str, int | None]:
    """Uploads the clip to your chat as the bot, without a notification sound; returns its Telegram file id and the
    message id (the autopilot deletes that message once it has the file, so the raw clip doesn't clutter the chat)."""
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
    return media["file_id"], (res.get("result") or {}).get("message_id")


def tell_autopilot(token: str, post: dict, file_id: str, message_id: int | None = None, sample: bool = False) -> None:
    clip = post["tv_clip"]
    body = json.dumps({"event_type": "tvclip", "client_payload": {
        "post": post["id"], "file_id": file_id, "channel": clip.get("channel", "TV"), "url": clip["url"],
        "title": clip.get("title", ""), "message_id": message_id, "sample": sample}}).encode()
    _get(f"https://api.github.com/repos/{REPO}/dispatches", data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"})


def sample(keys: dict, labels: list[str], want: int = 3) -> int:
    """--sample: the newest news posts that already went out; for up to `want` of them with a TV story, the clip is
    sent and the autopilot checks it is the same event and, if so, makes a sample Reel (sent to Telegram, nothing
    posted, nothing changed). Several are sent because the autopilot turns down clips of another event."""
    posts = []
    for label in labels:
        try:
            posts += json.loads(_get(RAW.format(label)))["posts"]
        except urllib.error.HTTPError:
            pass
    news = sorted((p for p in posts if p.get("hot") and p.get("status") == "published" and p.get("beats")),
                  key=lambda p: p["publish_at"], reverse=True)[:12]
    ff, sent = ffmpeg(), 0
    for p in news:
        clip = search_clip(p, ff, days=8)   # posts that already went out: their TV story is a few days old
        print(f"{p['id']}: " + (f"{clip['channel']} | {clip['title'][:70]}" if clip else
                                f"no TV story found for '{' '.join(keywords(p))}'"))
        if not clip:
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                small = Path(tmp) / "clip.mp4"
                fetch(clip["url"], small, ff)
                fid, mid = send_to_bot(keys["KOR_TELEGRAM_BOT_TOKEN"], keys["KOR_TELEGRAM_CHAT_ID"], small,
                                       f"📺 TV clip for a sample of {p['id']} (from your computer)")
            tell_autopilot(keys["KOR_GITHUB_TOKEN"], {**p, "tv_clip": clip}, fid, mid, sample=True)
        except Exception as e:
            print(f"   skipped: {e}")
            continue
        sent += 1
        print("   sent for the same-event check")
        if sent >= want:
            break
    print(f"{sent} clip(s) sent: the ones that pass the check come back as sample Reels in about 10-20 minutes"
          if sent else "none of the recent news posts has a matching TV story on the stations' channels")
    return 0 if sent else 1


def main(argv: list[str]) -> int:
    check = "--check" in argv
    keys = {k: os.environ.get(k, "") for k in ("KOR_TELEGRAM_BOT_TOKEN", "KOR_TELEGRAM_CHAT_ID", "KOR_GITHUB_TOKEN")}
    missing = [k for k, v in keys.items() if not v]
    if missing and not check:
        print("Set these first (see the top of this file): " + ", ".join(missing))
        return 1
    now = dt.datetime.now(EAT)
    if "--sample" in argv:
        prev = now - dt.timedelta(days=7)
        return sample(keys, [f"{prev.isocalendar()[0]}-W{prev.isocalendar()[1]:02d}"] + week_labels(now))
    done = set(json.loads(DONE.read_text(encoding="utf-8"))) if DONE.exists() else set()
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
        clip = (p.get("tv_clip") or {}) if (p.get("tv_clip") or {}).get("url") else (search_clip(p, ff) or {})
        if not clip.get("url"):
            print(f"{p['id']}: no TV story found for '{' '.join(keywords(p))}'")
            if not check:
                done.add(p["id"])
            continue
        p["tv_clip"] = clip
        print(f"{p['id']}: {clip.get('channel')} | {clip.get('title', '')[:70]}")
        if check:
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                small = Path(tmp) / "clip.mp4"
                fetch(clip["url"], small, ff)
                fid, mid = send_to_bot(keys["KOR_TELEGRAM_BOT_TOKEN"], keys["KOR_TELEGRAM_CHAT_ID"], small,
                                       f"📺 TV clip for {p['id']} (from your computer, for the autopilot)")
            tell_autopilot(keys["KOR_GITHUB_TOKEN"], p, fid, mid)
            print("   sent; the autopilot is making the Reel")
        except Exception as e:
            print(f"   skipped: {e}")
        done.add(p["id"])   # tried once: a clip that fails is not retried every half hour
    DONE.write_text(json.dumps(sorted(done)[-300:]), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
