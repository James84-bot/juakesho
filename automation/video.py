"""
video.py — turns any Kenya on Record post into a 9:16 Reel / TikTok / Short.

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
KICKERS = {"sauti": "The People's Voice", "straight": "Set It Straight", "promise": "Promise Tracker", "kumbuka": "We Remember",
           "scorecard": "Chapter Six Test", "money": "Follow the Money", "usiibiwe": "Scam alert", "cap": "Cap or No Cap?",
           "still": "Still in 2026?", "decode": "Decode", "spotlight": "Put Us On", "africa": "Made in Africa",
           "hack": "Civic 101", "makanga": "Explained", "cover": "Kenya on Record", "glasspoll": "Your Say", "build": "Build With Me",
           "tazama": "Watch This"}


def beat_reel(post: dict) -> dict | None:
    """The beat-by-beat Reel version of a post, when the writer gave it a script (`beats`)."""
    beats = [b for b in (post.get("beats") or []) if isinstance(b, str) and b.strip()]
    if len(beats) < 3:
        return None
    reel = {k: v for k, v in post.items() if k not in {"template", "size", "ink"}}
    reel.update(template="reel", size="story", beats=beats,
                kicker=post.get("series") or KICKERS.get(post["template"], "Kenya on Record"))
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
    """Renders every n-th frame in its own browser (frames are independent once time is seeked).
    alpha: transparent PNGs (the words and scrim only), for laying over moving footage."""
    html_path, frame_dir, frames, k, n, w, h, alpha = args
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        _open(page, Path(html_path))
        for f in range(k, frames, n):
            page.evaluate(f"window.__seek({f / FPS})")
            if alpha:
                page.screenshot(path=f"{frame_dir}/f{f:04d}.png", type="png", omit_background=True,
                                clip={"x": 0, "y": 0, "width": w, "height": h}, animations="allow")
            else:
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


def render_frames(html_path: Path, frame_dir: Path, frames: int, w: int = 1080, h: int = 1920, alpha: bool = False) -> None:
    """Every frame of an animated page as f0000.jpg... (or transparent f0000.png), rendered in parallel browsers."""
    n = workers()
    ctx = mp.get_context("spawn")
    with ctx.Pool(n) as pool:
        pool.map(_frame_worker, [(str(html_path), str(frame_dir), frames, k, n, w, h, alpha) for k in range(n)])


def footage_graph(dur: float) -> str:
    """The clip filling 9:16 (cropped from the centre, looped if short), slightly darkened and moving, with the
    transparent design frames on top."""
    return ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,"
            f"eq=brightness=-0.08:saturation=1.05,trim=duration={dur},setpts=PTS-STARTPTS[bg];"
            "[bg][1:v]overlay=0:0:format=auto:shortest=1,format=yuv420p[v]")


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


SIGN_OFF = "Facts today. A better Kenya tomorrow."
PRESENTER_W = 440          # px on the 1080-wide Reel: head and shoulders, bottom-right, clear of the lines
VOICE_DELAY = 0.15         # s of air before the first word


def voice_for(post: dict, lines: list[str], work: Path) -> dict | None:
    """The presenter reads the beats, then the sign-off. None when no voice has been chosen yet, or if anything
    fails: a voiced Reel is a bonus and must never stop the post."""
    try:
        import voicelab
        character = voicelab.chosen()
        if not character:
            return None
        wav = work / "voice.wav"
        durs = voicelab.speak(lines + [SIGN_OFF], wav, character, stand_in_voice=bool(os.environ.get("VOICE_STAND_IN")))
        script = " ".join(l.replace("*", "") for l in lines + [SIGN_OFF])
        return {"wav": wav, "durs": durs[:-1], "tail": durs[-1], "script": script, "name": character[0]}
    except Exception as e:
        print(f"  voice skipped for {post['id']}: {str(e)[:200]}")
        return None


def mix_voice(ff: str, voice: Path, bed: Path, out: Path) -> None:
    """The voice up front, the music bed low underneath, as long as the bed."""
    ms = int(VOICE_DELAY * 1000)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(bed), "-i", str(voice), "-filter_complex",
                    f"[0:a]volume=0.16[b];[1:a]adelay={ms}|{ms},apad[v];[b][v]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "[a]", "-ar", "44100", "-ac", "2", str(out)], check=True)


PORTRAIT = HERE / "content" / "presenter" / "portrait.jpg"   # the realistic presenter's one photo


def presenter_style() -> str:
    """'pip': the realistic presenter (a portrait brought to life) in a studio window; 'illustrated': the drawn
    host. Realistic whenever the portrait and its face-mapping library are available."""
    if PORTRAIT.exists():
        try:
            import mediapipe  # noqa: F401
            return "pip"
        except ImportError:
            print("  realistic presenter unavailable (mediapipe not installed): using the illustrated host")
    return "illustrated"


def add_presenter(ff: str, reel: Path, voice: dict, work: Path, seed: int, style: str = "illustrated",
                  dur: float = 0.0) -> None:
    """Lays the talking presenter over the finished Reel (same audio), in place."""
    out = work / "voiced.mp4"
    if style == "pip":
        import living
        clip = living.talk(PORTRAIT, voice["wav"], voice["script"], work / "presenter.mp4", ff, seed)
        graph = living.overlay_graph("0:v", "pv", "v")
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(reel), "-i", str(clip),
                        "-filter_complex", f"[1:v]setpts=PTS-STARTPTS+{VOICE_DELAY}/TB[pv];" + graph,
                        "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart"]
                       + (["-t", f"{dur:.3f}"] if dur else []) + [str(out)], check=True)
        shutil.move(str(out), str(reel))
        return
    import presenter
    mov = presenter.talk(voice["wav"], voice["script"], work / "presenter.mov", ff, seed)
    graph = presenter.overlay_graph("0:v", "pv", "v", width=PRESENTER_W, right=20)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(reel), "-i", str(mov),
                    "-filter_complex", f"[1:v]setpts=PTS-STARTPTS+{VOICE_DELAY}/TB[pv];" + graph,
                    "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                    "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out)], check=True)
    shutil.move(str(out), str(reel))


def make_reel(page, env, post: dict, out_dir: Path, ff: str) -> Path:
    is_story = post.get("size", "post") == "story"
    beats = beat_reel(post)
    voice_dir = Path(tempfile.mkdtemp(prefix="reel-voice-"))
    voice = voice_for(post, beats["beats"], voice_dir) if beats and post.get("template") != "tazama" else None
    render.SPOKEN.clear()
    style = presenter_style() if voice else ""
    if voice:   # each line stays up exactly as long as the presenter takes to say it
        render.SPOKEN.update(zip(beats["beats"], voice["durs"]))
        beats["presenter"] = style
    if beats:   # the Reel is its own script: one punchy line at a time, over the real photo
        html = render.build_html(env, beats, motion=True, reel=False)
        starts, t = [], 0.0
        for b in beats["beats"]:
            starts.append(t)
            t += render.beat_seconds(b)
    else:
        html = render.build_html(env, post, motion=True, reel=not is_story)
    footage = beats and post.get("video_file") and Path(post["video_file"]).exists()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "page.html").write_text(html, encoding="utf-8")
        _open(page, tmp / "page.html")
        tail = max(1.2, voice["tail"] + VOICE_DELAY + 0.3) if voice else 1.2   # the sign-off is said over the last line
        dur = round(t + tail, 2) if beats else duration_for(post, page.evaluate("window.__motionEnd()"))
        frames = int(dur * FPS)
        render_frames(tmp / "page.html", tmp, frames, alpha=bool(footage))
        seed = zlib.crc32(post["id"].encode()) % 1000
        track = music_track(post)
        if track:   # an artist's track we have permission for: chime first, then their hook
            mix_track(ff, track, dur, tmp / "audio.wav")
            post["track_credit"] = f"{track['artist']} - {track['title']} (used with permission)"
        elif post["template"] in URGENT_TEMPLATES:
            sound.write_wav(sound.tension(dur, starts if beats else [0.0], seed), tmp / "audio.wav")
        else:
            sound.write_wav(sound.bed(dur, seed), tmp / "audio.wav")
        if voice:
            shutil.move(str(tmp / "audio.wav"), str(tmp / "bed.wav"))
            mix_voice(ff, voice["wav"], tmp / "bed.wav", tmp / "audio.wav")
        target_mp4 = out_dir / f"{post['id']}.mp4"
        if footage:   # real moving footage underneath, the design frames on top
            cmd = [ff, "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(post["video_file"]),
                   "-framerate", str(FPS), "-i", str(tmp / "f%04d.png"), "-i", str(tmp / "audio.wav"),
                   "-filter_complex", footage_graph(dur), "-map", "[v]", "-map", "2:a",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                   "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-t", str(dur),
                   "-movflags", "+faststart", str(target_mp4)]
        else:
            cmd = [ff, "-y", "-loglevel", "error",
                   "-framerate", str(FPS), "-i", str(tmp / "f%04d.jpg"),
                   "-i", str(tmp / "audio.wav"),
                   "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                   "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
                   "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                   "-shortest", "-movflags", "+faststart", str(target_mp4)]
        subprocess.run(cmd, check=True)
        render.SPOKEN.clear()
        if voice:
            try:
                add_presenter(ff, target_mp4, voice, voice_dir, seed, style, dur)
                post["voiced"] = voice["name"]
            except Exception as e:   # the Reel without the presenter is still a good Reel
                print(f"  presenter skipped for {post['id']}: {str(e)[:200]}")
        # Cover frame: the hook line fully landed (beat Reels), or the fully-built design
        from PIL import Image
        cover = min(frames - 1, int((min(1.2, render.beat_seconds(beats["beats"][0]) - 0.2)) * FPS)) if beats else frames - 1
        if footage:   # the finished picture at that moment, footage included
            subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{cover / FPS:.2f}", "-i", str(target_mp4),
                            "-frames:v", "1", "-q:v", "3", str(out_dir / f"{post['id']}-cover.jpg")], check=True)
        else:
            Image.open(tmp / f"f{cover:04d}.jpg").convert("RGB").save(out_dir / f"{post['id']}-cover.jpg", quality=90)
    shutil.rmtree(voice_dir, ignore_errors=True)
    return target_mp4


STING_S = 1.8   # the end card: three voices, one question, then the name
STING_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>__FONTS__
html,body{margin:0;width:1080px;height:1920px;background:#0E0C0B;overflow:hidden}
svg{position:absolute;inset:0} #handle{position:absolute;left:0;right:0;top:1300px;text-align:center;
font:600 40px/1 Inter,system-ui,sans-serif;color:#A8A5A3;letter-spacing:.01em}
#red{animation:pop .42s cubic-bezier(.3,1.6,.5,1) .05s both}
#green{animation:pop .42s cubic-bezier(.3,1.6,.5,1) .22s both}
#black{animation:drop .5s cubic-bezier(.25,1.45,.5,1) .42s both}
#q{animation:pop .36s cubic-bezier(.3,1.9,.5,1) .78s both}
#word{animation:rise .5s ease-out 1.0s both} #handle{animation:rise .5s ease-out 1.12s both}
@keyframes pop{from{transform:scale(.2);opacity:0}to{transform:scale(1);opacity:1}}
@keyframes drop{from{transform:translateY(-160px) scale(.7);opacity:0}to{transform:none;opacity:1}}
@keyframes rise{from{transform:translateY(30px);opacity:0}to{transform:none;opacity:1}}
</style></head><body>__SVG__<div id="handle">__HANDLE__</div>
<script>document.getAnimations().forEach(a=>a.pause());
window.__seek=t=>document.getAnimations().forEach(a=>{a.currentTime=t*1000});</script></body></html>"""
_STING: dict[str, Path] = {}


def sting(ff: str, work: Path) -> Path | None:
    """The animated end card as an mp4 (made once per run): red pops, green pops, the black bubble drops in and
    asks, then KENYA ON RECORD and the handle. A soft chime; silence underneath so it joins any Reel."""
    if "mp4" in _STING and _STING["mp4"].exists():
        return _STING["mp4"]
    svg = ROOT / "assets" / "logo" / "sting.svg"
    if not svg.exists():
        return None
    try:
        brand = json.loads((HERE / "brand.json").read_text(encoding="utf-8"))
        work.mkdir(parents=True, exist_ok=True)
        page = work / "sting.html"
        import brandkit
        fonts = brandkit.font_faces((ROOT / "assets" / "fonts").as_uri())
        page.write_text(STING_HTML.replace("__FONTS__", fonts).replace("__SVG__", svg.read_text(encoding="utf-8"))
                        .replace("__HANDLE__", brand.get("handle", "")), encoding="utf-8")
        frames = int(STING_S * FPS)
        render_frames(page, work, frames)
        tail = np.zeros(int(sound.SR * STING_S), dtype=np.float32)
        ch = sound.chime()[: len(tail)] * 0.6
        tail[int(sound.SR * 0.78): int(sound.SR * 0.78) + len(ch)] += ch[: len(tail) - int(sound.SR * 0.78)]
        sound.write_wav(tail, work / "sting.wav")
        out = work / "sting.mp4"
        subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(work / "f%04d.jpg"),
                        "-i", str(work / "sting.wav"), "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                        "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-shortest", str(out)], check=True)
        _STING["mp4"] = out
        return out
    except Exception as e:   # an end card must never cost us the Reel
        print(f"  sting skipped: {e}")
        return None


def add_sting(ff: str, reel: Path, card: Path) -> None:
    """Joins the end card to a finished Reel (re-encoded once so both halves match exactly)."""
    joined = reel.with_name(reel.stem + ".joined.mp4")
    graph = ("[0:v]fps=30,format=yuv420p,setsar=1[v0];[1:v]fps=30,format=yuv420p,setsar=1[v1];"
             "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
             "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    try:
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(reel), "-i", str(card), "-filter_complex", graph,
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(joined)], check=True)
        joined.replace(reel)
    except Exception as e:
        print(f"  sting not joined to {reel.name}: {e}")
        joined.unlink(missing_ok=True)


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
            card = sting(ff, Path(tempfile.gettempdir()) / "kaa-sting")
            if card and post.get("template") != "tazama":
                add_sting(ff, path, card)
            made.append(path)
            print(f"  ✓ {path.name}  ({path.stat().st_size // 1024} KB)")
        browser.close()
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description="Render Kenya on Record Reels")
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
