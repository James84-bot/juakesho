"""
tazama.py — "Tazama Hii" (watch this): a clip someone filmed becomes OUR Reel, with our take around it.

You send a video to the Telegram bot with one line that says where it came from:
    ruhusa @kevo254 DM 12 Oct      (permission: the person who filmed it said yes; credit them)
    yangu                          (we filmed it)
    nukuu Citizen TV https://...   (a short quote from news footage, for commentary: max 8 seconds)
and, on the next lines, what it is about. Nothing without that line is ever used.

The Reel, 1080x1920:
    1. HOOK    1-2 beats over a still of the clip, urgent sound
    2. CLIP    the moment, boxed in our frame: headline on top, live captions from the real audio, credit below
    3. VERDICT 2-4 beats: what the record says, the receipts, the question for the leaders
The raw clip never enters the public repo; only the finished, credited Reel does.
"""
from __future__ import annotations

import datetime as dt
import html as htmlmod
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STATE_FILE = HERE / "state" / "clips.json"
MAX_SECONDS = {"quote": 8.0, "permission": 40.0, "own": 40.0}
TG_MAX_BYTES = 20 * 1024 * 1024        # Telegram bots can download files up to 20 MB
BOX_TOP, BOX_MAX_H, MARGIN = 430, 1000, 48

RIGHTS = [
    ("permission", re.compile(r"^\s*(ruhusa|permission|perm|ameruhusu)\b[\s:,-]*(.+)$", re.I)),
    ("own", re.compile(r"^\s*(yangu|mine|own|tumerekodi|we filmed)\b[\s:,-]*(.*)$", re.I)),
    ("quote", re.compile(r"^\s*(nukuu|quote|news)\b[\s:,-]*(.+)$", re.I)),
]

TAZAMA_RULES = """You write "Tazama Hii" Reels for WANJIKU ASKS: informed ordinary Kenyans who show a real clip and say what it
means, with receipts. You get: the owner's note on what the clip is, how we may use it (rights), the credit, the clip
length, the transcript with timestamps (may be empty), and this week's real headlines.

Return ONLY JSON:
{"headline": "max 70 chars, one *marker* on the words that hit hardest (sits above the clip)",
 "hook": ["1-2 beats before the clip: why you must watch, max 8 words / 44 chars each"],
 "start": seconds, "end": seconds,
 "verdict": ["2-4 beats after the clip: what the record says, the receipt, the question for the leaders; one *marker* max per beat"],
 "message": "the one thing the viewer must walk away with (max 120)",
 "caption": "Instagram caption in our KOT voice, credit the source by name, 2-4 live hashtags that fit, ask a question",
 "source": "links that back the verdict (from the headlines or official records); empty only if the verdict states no fact",
 "lane": "everyone"}

Rules:
- The window (start-end) is the moment that proves the point. Quotes from news footage: max 8 seconds. Others: max 40.
- Only say what the transcript, the note or the sources support. Never put words in anyone's mouth, never describe
  footage you weren't told about, never guess who someone is. If the note is thin, keep the verdict to the question.
- No name-calling, no tribe, no campaigning, no violence, no em dashes. Sound like Kenyans online, not a newsroom.
"""


# ---------------------------------------------------------------------------
# Intake (from Telegram)
# ---------------------------------------------------------------------------
def parse_caption(text: str) -> dict | None:
    """{"rights", "credit", "source", "note"} from the caption, or None if it doesn't say where the clip came from."""
    lines = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    if not lines:
        return None
    for kind, rx in RIGHTS:
        m = rx.match(lines[0])
        if m:
            rest = m.group(2).strip()
            url = re.search(r"https?://\S+", rest)
            credit = re.sub(r"https?://\S+", "", rest).strip(" ,;-") if kind != "own" else "Wanjiku Asks"
            if kind != "own" and len(credit) < 2:
                return None   # permission or a quote must say from whom
            return {"rights": kind, "credit": credit[:60], "source": url.group(0) if url else "",
                    "evidence": lines[0][:120], "note": "\n".join(lines[1:])[:600]}
    return None


HOW_TO = ("To use a clip, send the video with a caption whose FIRST line says where it came from:\n"
          "<code>ruhusa @who (how they said yes)</code>  the person who filmed it agreed\n"
          "<code>yangu</code>  we filmed it\n"
          "<code>nukuu Citizen TV https://link</code>  a short news quote (max 8 s)\n"
          "Then, on the next lines, what the clip is about.")


def load() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {"clips": []}


def save(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["clips"] = data["clips"][-200:]
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def intake(msg: dict, now: dt.datetime) -> tuple[str, dict | None]:
    """A Telegram message with a video. Returns (reply text, queued clip or None)."""
    media = msg.get("video") or (msg.get("document") if str((msg.get("document") or {}).get("mime_type", "")).startswith("video/") else None)
    if not media:
        return "", None
    info = parse_caption(msg.get("caption", ""))
    if not info:
        return "🎬 Got the video, but I can't use it yet.\n\n" + HOW_TO, None
    if int(media.get("file_size") or 0) > TG_MAX_BYTES:
        return "🎬 That file is over 20 MB, the most a Telegram bot can download. Trim it or send it compressed (not as a file).", None
    clip = {"id": f"clip-{now:%m%d%H%M%S}", "file_id": media["file_id"], "duration": media.get("duration"),
            "received": now.isoformat(), "status": "queued", **info}
    return (f"🎬 Clip queued (<b>{htmlmod.escape(info['rights'])}</b>, credit {htmlmod.escape(info['credit'])}). "
            "Your Tazama Hii Reel comes back here for ✅ within about 2 hours."), clip


def download(tg_get_file, token: str, file_id: str, target: Path) -> None:
    path = tg_get_file(file_id)
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{path}", timeout=120) as r:
        target.write_bytes(r.read())


# ---------------------------------------------------------------------------
# The clip itself
# ---------------------------------------------------------------------------
def probe(ff: str, clip: Path) -> dict:
    """Duration, display size (rotation applied) and whether there is sound."""
    out = subprocess.run([ff, "-hide_banner", "-i", str(clip)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    v = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", out)
    w, h = (int(v.group(1)), int(v.group(2))) if v else (1080, 1920)
    rot = re.search(r"rotat(?:e|ion of)\s*:?\s*(-?\d+)", out)
    if rot and abs(int(float(rot.group(1)))) % 180 == 90:
        w, h = h, w
    return {"duration": dur, "w": w, "h": h, "audio": "Audio:" in out}


def transcribe(clip: Path) -> list[dict]:
    """Timestamped speech from the clip's real audio (faster-whisper, runs on the CPU). Empty if unavailable."""
    try:
        import os
        from faster_whisper import WhisperModel
        model = WhisperModel(os.environ.get("JUA_WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
        segs, _ = model.transcribe(str(clip), vad_filter=True, beam_size=1)
        return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs if s.text.strip()]
    except Exception as e:
        print(f"  transcript skipped: {e}")
        return []


def captions(segments: list[dict], start: float, end: float, max_words: int = 7) -> list[dict]:
    """Caption cards inside the window, re-timed to the clip's own clock, at most ~7 words each."""
    out = []
    for s in segments:
        a, b = max(s["start"], start), min(s["end"], end)
        if b <= a:
            continue
        words = s["text"].split()
        chunks = [words[i:i + max_words] for i in range(0, len(words), max_words)] or [[]]
        step = (b - a) / len(chunks)
        for i, c in enumerate(chunks):
            if c:
                out.append({"start": round(a - start + i * step, 2), "end": round(a - start + (i + 1) * step, 2), "text": " ".join(c)})
    return out


def window(post: dict, info: dict, length: float) -> tuple[float, float]:
    cap = MAX_SECONDS[info["rights"]]
    try:
        a, b = float(post.get("start", 0)), float(post.get("end", length))
    except (TypeError, ValueError):
        a, b = 0.0, length
    a = min(max(0.0, a), max(0.0, length - 1))
    b = min(max(a + 1, b), length, a + cap)
    return round(a, 2), round(b, 2)


def box(info: dict) -> tuple[int, int, int, int]:
    """Where the clip sits: as wide as the margins allow, never taller than the box. Even sizes for H.264."""
    w = 1080 - 2 * MARGIN
    h = round(w * info["h"] / max(info["w"], 1))
    if h > BOX_MAX_H:
        h = BOX_MAX_H
        w = round(h * info["w"] / max(info["h"], 1))
    w, h = w - w % 2, h - h % 2
    top = max(BOX_TOP, 880 - h // 2)   # a wide clip sits in the middle of the screen, not at the top
    return (1080 - w) // 2, top, w, h


# ---------------------------------------------------------------------------
# Drawing (HTML -> PNG with the brand fonts)
# ---------------------------------------------------------------------------
def _marked(text: str) -> str:
    parts = re.split(r"\*", htmlmod.escape(text))
    return "".join(f"<mark>{p}</mark>" if i % 2 else p for i, p in enumerate(parts))


def frame_html(post: dict, info: dict, bx: tuple[int, int, int, int]) -> str:
    import brandkit as bk
    import render
    x, y, w, h = bx
    credit = (f"📹 {info['credit']} · used with permission" if info["rights"] == "permission" else
              "📹 Wanjiku Asks" if info["rights"] == "own" else f"📺 Clip: {info['credit']} · short excerpt for commentary")
    logo = (render.LOGO / "wordmark-on-dark.svg").as_uri()
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{bk.font_faces(render.FONTS)}
html,body{{margin:0;width:1080px;height:1920px;background:#0E0C0B;color:#fff;font-family:Inter,sans-serif;overflow:hidden}}
.top{{position:absolute;left:48px;right:48px;top:150px;display:flex;justify-content:space-between;align-items:center}}
.tag{{font:800 24px/1 "Inter Tight";letter-spacing:.08em;text-transform:uppercase;background:#C4111A;padding:10px 14px}}
.top img{{height:34px}}
h1{{position:absolute;left:48px;right:48px;bottom:{1920 - y + 44}px;margin:0;font:800 68px/1.04 "Inter Tight";letter-spacing:-.025em}}
mark{{background:#C4111A;color:#fff;padding:0 .08em}}
.box{{position:absolute;left:{x - 6}px;top:{y - 6}px;width:{w + 12}px;height:{h + 12}px;background:#1B1917;border-radius:6px}}
.credit{{position:absolute;left:48px;right:48px;top:1760px;font:600 30px/1.3 Inter;color:#CAC8C7}}
</style></head><body><div class="top"><span class="tag">Tazama Hii</span><img src="{logo}"></div>
<h1>{_marked(post.get("headline", ""))}</h1><div class="box"></div>
<div class="credit">{htmlmod.escape(credit)}</div></body></html>"""


def caption_html(text: str, top: int) -> str:
    import brandkit as bk
    import render
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{bk.font_faces(render.FONTS)}
html,body{{margin:0;width:1080px;height:1920px;background:transparent}}
p{{position:absolute;left:60px;right:60px;top:{top}px;margin:0;text-align:center}}
span{{font:800 46px/1.25 "Inter Tight";color:#fff;background:rgba(14,12,11,.82);padding:6px 14px;
box-decoration-break:clone;-webkit-box-decoration-break:clone}}</style></head>
<body><p><span>{htmlmod.escape(text)}</span></p></body></html>"""


def _shoot(page, html: str, path: Path, transparent: bool = False) -> None:
    page_file = path.with_suffix(".html")
    page_file.write_text(html, encoding="utf-8")
    page.goto(page_file.as_uri())
    page.evaluate("document.fonts.ready")
    page.screenshot(path=str(path), omit_background=transparent)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def clip_segment(ff: str, page, post: dict, info: dict, src: Path, meta: dict, a: float, b: float,
                 caps: list[dict], out: Path, tmp: Path) -> None:
    bx = box(meta)
    _shoot(page, frame_html(post, info, bx), tmp / "frame.png")
    cap_top = min(1700, bx[1] + bx[3] + 36)
    inputs = ["-loop", "1", "-i", str(tmp / "frame.png"), "-ss", str(a), "-t", str(b - a), "-i", str(src)]
    graph = [f"[1:v]scale={bx[2]}:{bx[3]},fps=30,setsar=1[c]", f"[0:v][c]overlay={bx[0]}:{bx[1]}:shortest=1[v0]"]
    last = "v0"
    for i, c in enumerate(caps[:60]):
        png = tmp / f"cap{i:02d}.png"
        _shoot(page, caption_html(c["text"], cap_top), png, transparent=True)
        inputs += ["-i", str(png)]
        graph.append(f"[{last}][{i + 2}:v]overlay=0:0:enable='between(t,{c['start']},{c['end']})'[v{i + 1}]")
        last = f"v{i + 1}"
    graph.append(f"[{last}]format=yuv420p[v]")
    if meta["audio"]:
        graph.append("[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100[a]")
    else:
        inputs += ["-f", "lavfi", "-t", str(b - a), "-i", "anullsrc=r=44100:cl=stereo"]
        graph.append(f"[{len(caps[:60]) + 2}:a]anull[a]")
    subprocess.run([ff, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(graph),
                    "-map", "[v]", "-map", "[a]", "-t", str(b - a), "-r", "30",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "aac", "-b:a", "160k",
                    "-ar", "44100", "-ac", "2", str(out)], check=True)


def make(post: dict, info: dict, src: Path, segments: list[dict], out_dir: Path) -> Path:
    """Builds <id>.mp4 and <id>-cover.jpg in out_dir."""
    from playwright.sync_api import sync_playwright
    import render
    import video
    ff = video.ffmpeg_bin()
    meta = probe(ff, src)
    a, b = window(post, info, meta["duration"])
    post["clip_window"] = [a, b]
    out_dir.mkdir(parents=True, exist_ok=True)
    env = render.make_env()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        still = tmp / "still.jpg"   # the clip's own frame behind the hook and verdict beats
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(round((a + b) / 2, 2)), "-i", str(src),
                        "-frames:v", "1", "-q:v", "2", str(still)], check=True)
        base = {**post, "photo_file": str(still)}
        video.beats_segment(env, base, post["hook"], "Tazama Hii", tmp / "a.mp4", ff, tail=0.3)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            clip_segment(ff, page, post, info, src, meta, a, b, captions(segments, a, b), tmp / "b.mp4", tmp)
            browser.close()
        video.beats_segment(env, base, post["verdict"], "Tazama Hii", tmp / "c.mp4", ff, tail=1.2)
        target = out_dir / f"{post['id']}.mp4"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(tmp / "a.mp4"), "-i", str(tmp / "b.mp4"), "-i", str(tmp / "c.mp4"),
                        "-filter_complex", "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[v][a]",
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(target)], check=True)
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", "1.0", "-i", str(tmp / "a.mp4"), "-frames:v", "1",
                        "-q:v", "2", str(out_dir / f"{post['id']}-cover.jpg")], check=True)
    return target


def write(call, info: dict, length: float, segments: list[dict], news_block: str) -> dict:
    """The writer's take on the clip (JSON), shaped into a post."""
    import draft as drafter
    ask = json.dumps({"note": info["note"], "rights": info["rights"], "credit": info["credit"],
                      "clip_source": info["source"], "clip_seconds": round(length, 1),
                      "max_window_seconds": MAX_SECONDS[info["rights"]],
                      "transcript": [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments][:80]},
                     ensure_ascii=False, indent=1)
    got = drafter.extract_json(call(drafter.BRAND_RULES + "\n" + TAZAMA_RULES + news_block, ask, max_tokens=3000))
    hook = [str(x) for x in got.get("hook") or []][:2]
    verdict = [str(x) for x in got.get("verdict") or []][:4]
    sources = " ".join(x for x in [str(got.get("source") or "").strip(), info["source"]] if x)
    return {"template": "tazama", "headline": str(got.get("headline", "")), "hook": hook, "verdict": verdict,
            "beats": hook + verdict, "start": got.get("start", 0), "end": got.get("end", length),
            "message": str(got.get("message", "")), "caption": str(got.get("caption", "")),
            "source": sources, "lane": got.get("lane") or "everyone", "credit": info["credit"],
            "rights": info["evidence"], "rights_kind": info["rights"], "reel": True}
