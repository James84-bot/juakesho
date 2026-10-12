"""
video.py — turns any Jua Kesho post into a 9:16 Reel / TikTok / Short.

The post's own HTML gets motion (staggered entrances, word-by-word headlines,
sticker pops, a bobbing Jua, drifting aurora). Animations are paused and stepped
frame by frame, so output is identical on every run and never drops frames.
Audio: the Jua chime + an original kalimba bed from sound.py.

    python video.py                          # every post in content/posts.json
    python video.py --only 01-hack-lecture-notes
    python video.py --file content/weeks/2026-W41.json --out ../exports/2026-W41

Output: <id>.mp4 (1080x1920, H.264 + AAC, 30 fps, faststart), and <id>-cover.jpg.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import shutil
import subprocess
import tempfile
import zlib
from pathlib import Path

import numpy as np

import render
import sound

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FPS = 30
MIN_S, MAX_S = 6.0, 14.0
READ_WPS = 3.6            # on-screen reading speed for young, fast readers (words/s)
SKIP_TEMPLATES = {"avatar", "banner"}
# Serious topics get the urgent bed; good news keeps the kalimba-and-benga one
URGENT_TEMPLATES = {"tazama", "sauti", "straight", "promise", "kumbuka", "scorecard", "money", "usiibiwe", "cap", "still"}
KICKERS = {"sauti": "Sauti ya Mwananchi", "straight": "Set It Straight", "promise": "Promise Tracker", "kumbuka": "Hatutasahau",
           "scorecard": "Chapter Six Test", "money": "Follow the Money", "usiibiwe": "Scam alert", "cap": "Cap or No Cap?",
           "still": "Still in 2026?", "decode": "Decode", "spotlight": "Put Us On", "africa": "Made in Africa",
           "hack": "Civic 101", "makanga": "Explained", "cover": "Jua Kesho", "glasspoll": "Jua Asks", "build": "Build With Me",
           "tazama": "Tazama Hii"}


def beat_reel(post: dict) -> dict | None:
    """The beat-by-beat Reel version of a post, when the writer gave it a script (`beats`)."""
    beats = [b for b in (post.get("beats") or []) if isinstance(b, str) and b.strip()]
    if len(beats) < 3:
        return None
    reel = {k: v for k, v in post.items() if k not in {"template", "size", "ink"}}
    reel.update(template="reel", size="story", beats=beats,
                kicker=post.get("series") or KICKERS.get(post["template"], "Jua Kesho"))
    return reel


def ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg  # pip install imageio-ffmpeg (bundled static binary)
    return imageio_ffmpeg.get_ffmpeg_exe()


def words_on_screen(post: dict) -> int:
    text = " ".join(str(v) for k, v in post.items()
                    if isinstance(v, str) and k not in {"id", "template", "bg", "size", "caption", "source", "expr", "lane", "trend"})
    for v in post.values():
        if isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    text += " " + x
                elif isinstance(x, dict):
                    for side in ("left", "right"):
                        c = x.get(side) or {}
                        text += " " + " ".join(str(c.get(k, "")) for k in ("say", "sms"))
    return len(text.split())


def duration_for(post: dict, motion_end: float) -> float:
    """Long enough to read everything once after it lands; short enough to invite a replay."""
    reading = words_on_screen(post) / READ_WPS
    return round(min(MAX_S, max(MIN_S, motion_end + 1.5, reading + 1.0)), 2)


def _open(page, html_path: Path) -> None:
    page.goto(html_path.as_uri())
    page.evaluate("document.fonts.ready.then(() => window.__fit ? window.__fit() : 1)")
    page.evaluate("Promise.all([...document.images].map(i => i.decode().catch(() => {})))")


def _frame_worker(args) -> int:
    """Renders every n-th frame in its own browser (frames are independent once time is seeked)."""
    html_path, frame_dir, frames, k, n, w, h = args
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        _open(page, Path(html_path))
        for f in range(k, frames, n):
            page.evaluate(f"window.__seek({f / FPS})")
            page.screenshot(path=f"{frame_dir}/f{f:04d}.jpg", type="jpeg", quality=93,
                            clip={"x": 0, "y": 0, "width": w, "height": h}, animations="allow")
        browser.close()
    return k


MUSIC = HERE / "content" / "music"


def _library() -> list[dict]:
    """Real tracks we may use: recorded rights, confirmed clean lyrics, file present."""
    try:
        reg = json.loads((MUSIC / "tracks.json").read_text(encoding="utf-8")).get("tracks", [])
    except (OSError, ValueError):
        return []
    return [{**t, "path": MUSIC / Path(str(t.get("file", ""))).name} for t in reg
            if len(str(t.get("rights", ""))) >= 8 and t.get("clean") is True and (MUSIC / Path(str(t.get("file", ""))).name).is_file()]


def music_track(post: dict) -> dict | None:
    """Real music for the Reel: the track the post asked for, else one from the licensed library that fits the
    mood (urgent for civic posts, uplifting for good news), chosen the same way every time for the same post.
    Nothing licensed: the original synthesised bed."""
    lib = _library()
    if post.get("track"):
        return next((t for t in lib if t["file"] == post["track"]), None)
    mood = "urgent" if post.get("template") in URGENT_TEMPLATES else "uplifting"
    fits = [t for t in lib if t.get("mood", "any") in {mood, "any"}]
    return fits[zlib.crc32(post["id"].encode()) % len(fits)] if fits else None


def mix_track(ff: str, track: dict, dur: float, out: Path) -> None:
    """Jua chime, then the track's hook: trimmed, faded, loudness-balanced for phone speakers (-14 LUFS)."""
    chime_wav = out.with_name("chime.wav")
    sound.write_wav(np.concatenate([sound.chime(), np.zeros(int(sound.SR * 0.1), dtype=np.float32)]), chime_wav)
    start = float(track.get("start", 0))
    fade_out = max(0.0, dur - 1.0)
    graph = (f"[1:a]atrim=start={start}:duration={dur},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.8,"
             f"afade=t=out:st={fade_out}:d=1.0,volume=0.85[m];"
             f"[0:a][m]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,"
             f"atrim=duration={dur}[a]")
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(chime_wav), "-i", str(track["path"]),
                    "-filter_complex", graph, "-map", "[a]", "-ar", "44100", "-ac", "2", str(out)], check=True)


def workers() -> int:
    return max(1, min(int(os.environ.get("JUA_VIDEO_WORKERS", "0")) or (os.cpu_count() or 2), 6))


def render_frames(html_path: Path, frame_dir: Path, frames: int, w: int = 1080, h: int = 1920) -> None:
    """Every frame of an animated page as f0000.jpg..., rendered in parallel browsers."""
    n = workers()
    ctx = mp.get_context("spawn")
    with ctx.Pool(n) as pool:
        pool.map(_frame_worker, [(str(html_path), str(frame_dir), frames, k, n, w, h) for k in range(n)])


def beats_segment(env, post: dict, beats: list[str], kicker: str, out_mp4: Path, ff: str, tail: float = 0.5) -> float:
    """A short run of beats (any count) over the post's photo, with the urgent bed: one piece of a longer Reel.
    Returns its length in seconds."""
    reel = {k: v for k, v in post.items() if k not in {"template", "size", "ink"}}
    reel.update(template="reel", size="story", beats=beats, kicker=kicker)
    starts, t = [], 0.0
    for b in beats:
        starts.append(t)
        t += render.beat_seconds(b)
    dur = round(t + tail, 2)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "page.html").write_text(render.build_html(env, reel, motion=True, reel=False), encoding="utf-8")
        frames = int(dur * FPS)
        render_frames(tmp / "page.html", tmp, frames)
        sound.write_wav(sound.tension(dur, starts, zlib.crc32(post["id"].encode()) % 1000), tmp / "audio.wav")
        subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "f%04d.jpg"),
                        "-i", str(tmp / "audio.wav"), "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                        "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-shortest", str(out_mp4)], check=True)
    return dur


def make_reel(page, env, post: dict, out_dir: Path, ff: str) -> Path:
    is_story = post.get("size", "post") == "story"
    beats = beat_reel(post)
    if beats:   # the Reel is its own script: one punchy line at a time, over the real photo
        html = render.build_html(env, beats, motion=True, reel=False)
        starts, t = [], 0.0
        for b in beats["beats"]:
            starts.append(t)
            t += render.beat_seconds(b)
    else:
        html = render.build_html(env, post, motion=True, reel=not is_story)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "page.html").write_text(html, encoding="utf-8")
        _open(page, tmp / "page.html")
        dur = round(t + 1.2, 2) if beats else duration_for(post, page.evaluate("window.__motionEnd()"))
        frames = int(dur * FPS)
        render_frames(tmp / "page.html", tmp, frames)
        seed = zlib.crc32(post["id"].encode()) % 1000
        track = music_track(post)
        if track:   # an artist's track we have permission for: chime first, then their hook
            mix_track(ff, track, dur, tmp / "audio.wav")
            post["track_credit"] = f"{track['artist']} - {track['title']} (used with permission)"
        elif post["template"] in URGENT_TEMPLATES:
            sound.write_wav(sound.tension(dur, starts if beats else [0.0], seed), tmp / "audio.wav")
        else:
            sound.write_wav(sound.bed(dur, seed), tmp / "audio.wav")
        target_mp4 = out_dir / f"{post['id']}.mp4"
        cmd = [ff, "-y", "-loglevel", "error",
               "-framerate", str(FPS), "-i", str(tmp / "f%04d.jpg"),
               "-i", str(tmp / "audio.wav"),
               "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
               "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
               "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
               "-shortest", "-movflags", "+faststart", str(target_mp4)]
        subprocess.run(cmd, check=True)
        # Cover frame: the hook line fully landed (beat Reels), or the fully-built design
        from PIL import Image
        cover = min(frames - 1, int((min(1.2, render.beat_seconds(beats["beats"][0]) - 0.2)) * FPS)) if beats else frames - 1
        Image.open(tmp / f"f{cover:04d}.jpg").convert("RGB").save(out_dir / f"{post['id']}-cover.jpg", quality=90)
    return target_mp4


def make_reels(posts: list[dict], out_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    env = render.make_env()
    ff = ffmpeg_bin()
    made = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1920})
        for post in posts:
            if post["template"] in SKIP_TEMPLATES:
                continue
            path = make_reel(page, env, post, out_dir, ff)
            made.append(path)
            print(f"  ✓ {path.name}  ({path.stat().st_size // 1024} KB)")
        browser.close()
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description="Render Jua Kesho Reels")
    ap.add_argument("--file", default=str(HERE / "content" / "posts.json"))
    ap.add_argument("--only")
    ap.add_argument("--out", default=str(ROOT / "exports" / "reels"))
    a = ap.parse_args()
    posts = json.loads(Path(a.file).read_text(encoding="utf-8"))["posts"]
    if a.only:
        posts = [p for p in posts if p["id"] == a.only]
    make_reels(posts, Path(a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
