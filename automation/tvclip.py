"""
tvclip.py — the TV clip of a news story, cut into the Reel: our hook, then up to QUOTE_S seconds of the station's own
footage with live captions and the station named on screen, then what it means. Kenya's Copyright Act allows a short
excerpt for reporting current events with acknowledgement; the cap and the on-screen credit keep it short and named.

The clip comes from the station's YouTube upload (radar.clip_for finds it). YouTube refuses many downloads from
cloud servers, so download() can fail; the Reel then stays the photo Reel it already is. Nothing here is fatal.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

QUOTE_S = 8.0
FIRST_S = 150   # only the first minutes of a story clip are fetched: the moment is near the start


def download(url: str, dest: Path, seconds: int = FIRST_S, timeout: int = 240) -> None:
    """The first `seconds` of a YouTube clip at 720p or below, with sound. Raises with yt-dlp's reason."""
    exe = shutil.which("yt-dlp")
    if not exe:
        raise RuntimeError("yt-dlp is not installed")
    import video
    r = subprocess.run([exe, "-q", "--no-playlist", "--no-warnings", "--ffmpeg-location", video.ffmpeg_bin(), "-f",
                        "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]",
                        "--merge-output-format", "mp4", "--download-sections", f"*0-{seconds}",
                        "-o", str(dest), url], capture_output=True, text=True, timeout=timeout)
    if r.returncode or not dest.exists():
        raise RuntimeError("yt-dlp: " + (r.stderr.strip().splitlines() or ["failed"])[-1][:240])


def check(url: str) -> str:
    """One real download attempt (10 s of the clip): 'ok, N bytes' or the reason it failed."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "t.mp4"
        try:
            download(url, dest, seconds=10, timeout=120)
            return f"ok, {dest.stat().st_size} bytes"
        except Exception as e:
            return f"failed: {str(e)[:300]}"
