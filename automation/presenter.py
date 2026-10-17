"""
presenter.py — makes the illustrated presenter talk, on our own machines at no cost.

    voice (wav) ──► Rhubarb Lip Sync (MIT) ──► mouth shape per moment ──► sprite sequence ──► presenter.mov (alpha)

  * sprites(): every mouth shape x {eyes open, eyes closed}, drawn once from presenter_art.py with Playwright,
    transparent PNGs with a soft rim light so he reads on dark photos.
  * cues(): Rhubarb turns the audio (+ the script, for accuracy) into timed mouth shapes A-H, X.
  * talk(): one video with an alpha channel: the right mouth at every frame, natural blinks every 3-5 s,
    a slow head sway. video.py lays it over the Reel.

    python presenter.py demo voice.wav "the script"   # writes presenter-demo.mov + a preview mp4
"""
from __future__ import annotations

import json
import os
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import presenter_art as art

HERE = Path(__file__).resolve().parent
FPS = 30
SPRITE_W, SPRITE_H = 600, 760
RHUBARB_VERSION = "1.14.0"
RHUBARB_URL = (f"https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v{RHUBARB_VERSION}/"
               f"Rhubarb-Lip-Sync-{RHUBARB_VERSION}-Linux.zip")
CACHE = Path(os.environ.get("PRESENTER_CACHE", Path(tempfile.gettempdir()) / "kor-presenter"))
BLINK_FRAMES = 4                # ~130 ms: a natural blink (half, closed, closed, half)
BLINK_GAP = (3.0, 5.0)          # seconds between blinks


def log(msg: str) -> None:
    print(f"presenter: {msg}", flush=True)


# ---------------------------------------------------------------------------
# Sprites
# ---------------------------------------------------------------------------
def _layered(mouth: str, eyes: str, brows: str = "calm") -> str:
    """One full face: base + brows + eyes + mouth, as an HTML page with a transparent background."""
    layers = art.BASE + art.BROWS[brows] + art.EYES[eyes] + art.MOUTHS[mouth]
    return ("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;background:transparent}"
            f"#c{{position:relative;width:{SPRITE_W}px;height:{SPRITE_H}px;"
            "filter:drop-shadow(0 0 2px rgba(255,255,255,.32)) drop-shadow(0 18px 30px rgba(0,0,0,.45))}"
            f"</style></head><body><div id='c'>{layers}</div></body></html>")


def sprite_name(mouth: str, eyes: str, brows: str = "calm") -> str:
    return f"{mouth}-{eyes}-{brows}.png"


def sprites(out: Path, brows: str = "calm") -> Path:
    """Draws every mouth with eyes open, half and closed (once; kept in `out` for the run)."""
    out.mkdir(parents=True, exist_ok=True)
    wanted = [(m, e) for m in list(art.MOUTHS) for e in art.EYES]
    if all((out / sprite_name(m, e, brows)).exists() for m, e in wanted):
        return out
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": SPRITE_W, "height": SPRITE_H})
        for m, e in wanted:
            page.set_content(_layered(m, e, brows))
            page.locator("#c").screenshot(path=str(out / sprite_name(m, e, brows)), omit_background=True)
        b.close()
    log(f"{len(wanted)} sprites drawn")
    return out


# ---------------------------------------------------------------------------
# Lip sync
# ---------------------------------------------------------------------------
def rhubarb() -> Path:
    """The Rhubarb binary: on PATH, or downloaded once from its official GitHub release."""
    found = shutil.which("rhubarb")
    if found:
        return Path(found)
    exe = CACHE / f"Rhubarb-Lip-Sync-{RHUBARB_VERSION}-Linux" / "rhubarb"
    if not exe.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        zpath = CACHE / "rhubarb.zip"
        with urllib.request.urlopen(RHUBARB_URL, timeout=300) as r:
            zpath.write_bytes(r.read())
        with zipfile.ZipFile(zpath) as z:
            z.extractall(CACHE)
        zpath.unlink()
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def cues(wav: Path, script: str = "") -> list[dict]:
    """Timed mouth shapes for the audio. The script (when given) makes Rhubarb's recognition far more accurate."""
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "cues.json"
        args = [str(rhubarb()), "-q", "-f", "json", "--extendedShapes", "GHX", "-o", str(out)]
        if script.strip():
            (Path(t) / "script.txt").write_text(script, encoding="utf-8")
            args += ["-d", str(Path(t) / "script.txt")]
        res = subprocess.run(args + [str(wav)], capture_output=True, text=True)
        if res.returncode:
            raise RuntimeError(f"rhubarb failed: {res.stderr[-400:]}")
        return json.loads(out.read_text())["mouthCues"]


def timeline(mouth_cues: list[dict], duration: float, seed: int = 0, smile_ends: bool = True) -> list[str]:
    """Sprite file name for every frame: the cue's mouth, blinks every BLINK_GAP seconds (never over a frame
    where the mouth is wide open, which reads as a wince), and a small smile in the last half second."""
    frames = max(1, round(duration * FPS))
    mouth = ["X"] * frames
    for c in mouth_cues:
        a, b = int(c["start"] * FPS), int(c["end"] * FPS)
        for i in range(max(0, a), min(frames, max(b, a + 1))):
            mouth[i] = c["value"] if c["value"] in art.MOUTHS else "X"
    if smile_ends:
        for i in range(max(0, frames - FPS // 2), frames):
            if mouth[i] == "X":
                mouth[i] = "SMILE"
    eyes = ["open"] * frames
    rng = random.Random(seed)
    t = rng.uniform(1.0, 2.0)
    while t * FPS < frames - BLINK_FRAMES:
        i = int(t * FPS)
        if mouth[i] not in ("D",):
            for k, e in enumerate(("half", "closed", "closed", "half")):
                eyes[i + k] = e
        t += rng.uniform(*BLINK_GAP)
    return [sprite_name(m, e) for m, e in zip(mouth, eyes)]


def seconds(wav: Path) -> float:
    import wave
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def talk(wav: Path, script: str, out: Path, ff: str, seed: int = 0) -> Path:
    """The talking presenter as a .mov with alpha (PNG codec), exactly as long as the audio."""
    dur = seconds(wav)
    sheet = sprites(CACHE / "sprites")
    seq = timeline(cues(wav, script), dur, seed)
    with tempfile.TemporaryDirectory() as t:
        listing = Path(t) / "frames.txt"
        rows, run, prev = [], 0, None
        for name in seq + [None]:      # collapse repeats: one entry per held mouth shape
            if name == prev:
                run += 1
                continue
            if prev is not None:
                rows += [f"file '{sheet / prev}'", f"duration {run / FPS:.4f}"]
            prev, run = name, 1
        rows.append(f"file '{sheet / seq[-1]}'")    # concat demuxer: the last file is listed twice
        listing.write_text("\n".join(rows) + "\n")
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-vf", f"fps={FPS},format=rgba", "-t", f"{dur:.3f}", "-c:v", "png", str(out)], check=True)
    return out


def overlay_graph(base_label: str, presenter_label: str, out_label: str, width: int = 520, right: int = 24,
                  bottom: int = 0) -> str:
    """ffmpeg filter: the presenter scaled to `width`, bottom-right, with a slow natural sway (a few pixels)."""
    h = round(width * SPRITE_H / SPRITE_W)
    return (f"[{presenter_label}]scale={width}:{h}:flags=lanczos,format=rgba[pp];"
            f"[{base_label}][pp]overlay=x=W-w-{right}+3*sin(2*PI*t/4.3):y=H-h-{bottom}+6+4*sin(2*PI*t/3.1)"
            f":format=auto[{out_label}]")


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "demo":
        from video import ffmpeg_bin
        ff = ffmpeg_bin()
        wav, script = Path(argv[1]), argv[2]
        mov = talk(wav, script, Path("presenter-demo.mov"), ff)
        dur = seconds(wav)
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=#0E0C0B:s=1080x1920:d={dur:.2f}",
                        "-i", str(mov), "-i", str(wav), "-filter_complex", overlay_graph("0:v", "1:v", "v"),
                        "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", "presenter-demo.mp4"], check=True)
        log("wrote presenter-demo.mov and presenter-demo.mp4")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
