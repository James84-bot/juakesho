"""
cc_local.py — bring a Creative Commons YouTube video into the pipeline from YOUR computer.

YouTube refuses downloads from cloud servers ("confirm you're not a bot"), so this part runs on your own machine, on
your own connection. It does what the server cannot, and nothing else:

  1. checks the video's own licence through the YouTube Data API: only CC BY ("creativeCommon") is accepted
  2. downloads it at 720p or lower and trims it to 40 seconds (or less)
  3. sends it to your Telegram bot with a caption in the Tazama Hii format, so it comes back as a Reel with the
     channel credited on screen:   ruhusa <channel> (CC BY) <url>

Run (Windows, from the repo folder):
    pip install yt-dlp requests
    set YOUTUBE_API_KEY=...  &  set TELEGRAM_BOT_TOKEN=...  &  set TELEGRAM_CHAT_ID=...
    python automation/cc_local.py https://www.youtube.com/watch?v=VIDEO_ID "What the clip shows, in a line or two"

Keep the keys in your own environment or automation/.env, never in the repo.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

MAX_S = 40
TG_MAX_BYTES = 19 * 1024 * 1024   # bots can download 20 MB at most; stay under it


def video_id(url: str) -> str:
    u = urllib.parse.urlparse(url)
    if u.netloc.endswith("youtu.be"):
        return u.path.strip("/")
    return urllib.parse.parse_qs(u.query).get("v", [""])[0]


def check_licence(vid: str, key: str, get=None) -> dict:
    """The video's channel and URL, or raises ValueError when it is not licensed CC BY."""
    get = get or (lambda url: urllib.request.urlopen(url, timeout=30).read())
    data = json.loads(get("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(
        {"part": "snippet,status", "id": vid, "key": key})))
    items = data.get("items") or []
    if not items:
        raise ValueError("video not found")
    v = items[0]
    if (v.get("status") or {}).get("license") != "creativeCommon":
        raise ValueError("this video is not under the Creative Commons licence: it cannot be used")
    return {"channel": str(v["snippet"].get("channelTitle") or "")[:50], "title": v["snippet"].get("title", ""),
            "url": f"https://www.youtube.com/watch?v={vid}"}


def caption(info: dict, about: str) -> str:
    """First line says where it came from (tazama.parse_caption), the rest is what it shows."""
    return f"ruhusa {info['channel']} (CC BY) {info['url']}\n{about}".strip()


def download_and_shrink(vid: str, out: Path) -> None:
    ytdlp = shutil.which("yt-dlp") or sys.exit("install yt-dlp first: pip install yt-dlp")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.mp4"
        subprocess.run([ytdlp, "-q", "--no-playlist", "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]",
                        "--merge-output-format", "mp4", "-o", str(raw), f"https://www.youtube.com/watch?v={vid}"], check=True)
        ff = shutil.which("ffmpeg")
        if not ff:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        for crf in (26, 30, 34):   # until it fits what a Telegram bot can download
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-t", str(MAX_S), "-vf", "scale='min(720,iw)':-2",
                            "-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k",
                            "-movflags", "+faststart", str(out)], check=True)
            if out.stat().st_size <= TG_MAX_BYTES:
                return
    raise RuntimeError("could not get the clip under 19 MB: pick a shorter video")


def send(token: str, chat: str, video: Path, text: str) -> None:
    """Multipart upload with the standard library only."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", chat), ("caption", text)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="video"; filename="clip.mp4"\r\n'
                  "Content-Type: video/mp4\r\n\r\n").encode() + video.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendVideo", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(req, timeout=180).read()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    key, token, chat = (os.environ.get(k) for k in ("YOUTUBE_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))
    if not (key and token and chat):
        print("Set YOUTUBE_API_KEY, TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your environment first.")
        return 1
    vid = video_id(argv[1])
    if not vid:
        print("That does not look like a YouTube link.")
        return 1
    try:
        info = check_licence(vid, key)
    except ValueError as e:
        print(f"Not used: {e}")
        return 2
    out = Path(tempfile.gettempdir()) / f"cc-{vid}.mp4"
    download_and_shrink(vid, out)
    send(token, chat, out, caption(info, " ".join(argv[2:])))
    out.unlink(missing_ok=True)
    print(f"Sent to Telegram: {info['title']} ({info['channel']}). The Reel comes back for approval within about 2 hours.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
