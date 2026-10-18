"""
takes.py — James on camera: the presenter is a real person reading the script, not an AI.

    1. You approve a Reel in Telegram  -> the bot sends its script (the lines + the sign-off).
    2. You reply to that message with a selfie video of you reading it.
    3. The next run cleans the sound, finds where each line starts (speech recognition, or the pauses),
       trims the silence, and builds the Reel: the lines and photo on top, you full-width below.
    4. You get the finished Reel with ✅ Use this take / 🔁 Record again.
    5. ✅ swaps it in for the text Reel (kept as <id>-text.mp4); it goes out at its time.
       No recording, or no ✅ before its time: it goes out as the text Reel. Nothing waits on you.

Your raw selfie video is never stored in the repo: only Telegram's file id is kept, and the video is
downloaded for the build and deleted after.

    python takes.py pending     # exit 0 if a recording is waiting to be built (the workflow installs tools then)
    python takes.py build       # build every waiting recording and send it for review
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TAKE_H = 960                 # the presenter's half of the 1080x1920 Reel (bottom)
LEAD_IN, LEAD_OUT = 0.25, 0.45   # air kept before the first word and after the last
MIN_LEAD = dt.timedelta(minutes=50)   # closer to the slot than this, there is no time to record and build
MAX_BYTES = 20 * 1024 * 1024  # the Telegram bot API downloads files up to 20 MB
CLEAN = ("highpass=f=80,afftdn=nf=-25,agate=threshold=-42dB:ratio=2:attack=5:release=200,"
         "equalizer=f=180:t=q:w=1:g=1.5,equalizer=f=3500:t=q:w=1.2:g=2,deesser=i=0.3,"
         "acompressor=threshold=-18dB:ratio=3:attack=10:release=120,loudnorm=I=-16:TP=-1.5:LRA=11")
TIPS = ("Phone upright at eye level, face a window (daylight on your face, never behind you), quiet room. "
        "Read naturally and pause one breath between lines. Send it as a normal video, not as a file.")


def _p():
    import pipeline
    return pipeline


# ---------------------------------------------------------------------------
# the script
# ---------------------------------------------------------------------------
def script_lines(post: dict) -> list[str]:
    """What you read: the Reel's lines, then the sign-off."""
    import video
    beats = video.beat_reel(post)
    lines = [re.sub(r"\*", "", b).strip() for b in (beats or {}).get("beats", [])]
    return lines + [video.SIGN_OFF]


def ask_text(post: dict, label: str) -> str:
    from html import escape
    when = dt.datetime.fromisoformat(post["publish_at"])
    lines = script_lines(post)
    body = "\n".join(f"{i}. {escape(l)}" for i, l in enumerate(lines[:-1], 1))
    return (f"🎬 <b>Record this one</b> ({escape(post.get('series') or post['template'])}, goes out "
            f"{when:%a %d %b %H:%M})\n\nReply to <b>this message</b> with a selfie video of you reading:\n\n{body}\n"
            f"<i>{escape(lines[-1])}</i>\n\n{TIPS}\n\nNo recording before then: it goes out as the text Reel.\n"
            f"<code>{escape(label)}|{escape(post['id'])}</code>")


def ask(post: dict, label: str, chat: str) -> bool:
    """Sends the script for an approved Reel. False when there is no time left or it isn't a Reel."""
    P = _p()
    import video
    if not P.is_reel(post) or post.get("template") == "tazama" or not video.beat_reel(post):
        return False   # a Reel without lines has no script to read
    if dt.datetime.fromisoformat(post["publish_at"]) - P.now() < MIN_LEAD:
        return False
    import twin
    if twin.ready():   # the AI presenter already reads it
        return False
    res = P.tg("sendMessage", {"chat_id": chat, "text": ask_text(post, label), "parse_mode": "HTML",
                               "reply_markup": json.dumps({"force_reply": True, "input_field_placeholder":
                                                           "Reply with your video"})})
    post["take"] = {"status": "asked", "ask_msg": res["result"]["message_id"]}
    return True


# ---------------------------------------------------------------------------
# your video arrives
# ---------------------------------------------------------------------------
def video_of(msg: dict) -> dict | None:
    """The video in a message: a normal video, a round video note, or a video sent as a file."""
    if msg.get("video"):
        return msg["video"]
    if msg.get("video_note"):
        return msg["video_note"]
    doc = msg.get("document") or {}
    return doc if str(doc.get("mime_type", "")).startswith("video/") else None


def find(reply_to: int | None, weeks: list[Path] | None = None) -> tuple[Path, dict, dict] | None:
    """The week file, week data and post whose script (or review) message this replies to."""
    if not reply_to:
        return None
    P = _p()
    for f in weeks if weeks is not None else sorted(P.WEEKS.glob("*.json"), reverse=True)[:3]:
        data = json.loads(f.read_text(encoding="utf-8"))
        for post in data["posts"]:
            t = post.get("take") or {}
            if reply_to in (t.get("ask_msg"), t.get("review_msg")):
                return f, data, post
    return None


def is_take(msg: dict) -> bool:
    return bool(video_of(msg) and find((msg.get("reply_to_message") or {}).get("message_id")))


def intake(msg: dict, chat: str, weeks: dict | None = None) -> str:
    """Saves the recording's Telegram file id on its post; returns the reply for you.
    weeks: Telegram's batch of weeks already open (pipeline.collect saves them at the end): the recording is
    written into that copy, so a button tap in the same batch can't overwrite it."""
    P = _p()
    hit = find((msg.get("reply_to_message") or {}).get("message_id"))
    if not hit:
        return ""
    _, data, post = hit
    if weeks is not None:
        data = weeks.setdefault(data["collection"], data)
        post = next(p for p in data["posts"] if p["id"] == post["id"])
    v = video_of(msg)
    if post["status"] in {"published", "rejected", "missed", "manual"}:
        return f"🎬 {post['id']} is {post['status']}: this recording isn't needed any more."
    if dt.datetime.fromisoformat(post["publish_at"]) <= P.now():
        return f"🎬 {post['id']} has already gone out, so this recording isn't used."
    if msg.get("video_note"):
        return ("🎬 That's a round video note: it's too small (384 px) for a Reel. Record a normal video with the "
                "camera and reply with that.")
    if int(v.get("file_size") or 0) > MAX_BYTES:
        return (f"🎬 That file is {int(v['file_size']) // (1024 * 1024)} MB; the bot can only fetch up to 20 MB. "
                "Send it as a normal video (not as a file) so Telegram compresses it, or record in 1080p, not 4K.")
    if int(v.get("duration") or 99) < 5:
        return "🎬 That's under 5 seconds. Reply again with the whole script read out."
    post["take"] = {**(post.get("take") or {}), "status": "received", "file_id": v["file_id"],
                    "duration": v.get("duration"), "received_at": P.now().isoformat()}
    if weeks is None:
        P.save_week(data)
    return (f"🎬 Got it ({v.get('duration', '?')} s). Building your Reel now: it comes back here in a few minutes "
            "for ✅.")


def pending(weeks: list[Path] | None = None) -> list[tuple[Path, str]]:
    P = _p()
    out = []
    for f in weeks if weeks is not None else sorted(P.WEEKS.glob("*.json"))[-3:]:
        for post in json.loads(f.read_text(encoding="utf-8"))["posts"]:
            if (post.get("take") or {}).get("status") == "received":
                out.append((f, post["id"]))
    return out


# ---------------------------------------------------------------------------
# timing: where each line starts in your recording
# ---------------------------------------------------------------------------
def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def transcribe(wav: Path) -> list[dict] | None:
    """Words with start/end times (faster-whisper on the CPU). None when it isn't installed."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(wav), language="en", word_timestamps=True, vad_filter=True)
    return [{"w": w.word.strip(), "s": float(w.start), "e": float(w.end)} for s in segs for w in (s.words or [])]


def align(lines: list[str], words: list[dict]) -> tuple[list[float], float] | None:
    """The start time of each line in the recording, and how much of the script was matched (0-1).
    None if a line can't be placed (skipped or changed too much)."""
    script = [(i, _norm(w)) for i, l in enumerate(lines) for w in l.split() if _norm(w)]
    heard = [_norm(w["w"]) for w in words]
    sm = difflib.SequenceMatcher(None, [w for _, w in script], heard, autojunk=False)
    hit: dict[int, int] = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            hit[a + k] = b + k
    starts = []
    for i in range(len(lines)):
        idx = [k for k, (li, _) in enumerate(script) if li == i]
        got = [hit[k] for k in idx if k in hit]
        if not got:
            return None
        first = min(got)
        # words before the first matched one were said too (just heard differently): step back over them
        lead = min(k for k in idx if k in hit) - idx[0]
        starts.append(words[max(0, first - lead)]["s"] if lead else words[first]["s"])
    if any(b < a for a, b in zip(starts, starts[1:])):
        return None
    return starts, len(hit) / max(1, len(script))


def speech_span(ff: str, wav: Path) -> tuple[float, float, list[tuple[float, float]]]:
    """(first sound, last sound, the pauses in between) from ffmpeg's silence detector."""
    res = subprocess.run([ff, "-hide_banner", "-i", str(wav), "-af", "silencedetect=noise=-38dB:d=0.28", "-f", "null",
                          "-"], capture_output=True, text=True)
    total = float(re.search(r"Duration: (\d+):(\d+):([\d.]+)", res.stderr).groups()[2]) + \
        60 * float(re.search(r"Duration: (\d+):(\d+)", res.stderr).groups()[1])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]
    gaps = list(zip(starts, ends + [total] * (len(starts) - len(ends))))
    first = gaps[0][1] if gaps and gaps[0][0] < 0.05 else 0.0
    last = gaps[-1][0] if gaps and gaps[-1][1] >= total - 0.05 else total
    inner = [(s, e) for s, e in gaps if s > first + 0.1 and e < last - 0.1]
    return first, last, inner


def pause_starts(lines: list[str], first: float, last: float, pauses: list[tuple[float, float]]) -> list[float]:
    """Without speech recognition: the longest pauses split the lines; else by word count."""
    need = len(lines) - 1
    if len(pauses) >= need:
        cuts = sorted(sorted(pauses, key=lambda g: g[1] - g[0], reverse=True)[:need])
        return [round(first, 3)] + [round(e - 0.05, 3) for _, e in cuts]
    counts = [max(1, len(l.split())) for l in lines]
    span, out, t = last - first, [], first
    for c in counts:
        out.append(round(t, 3))
        t += span * c / sum(counts)
    return out


# ---------------------------------------------------------------------------
# building the Reel
# ---------------------------------------------------------------------------
def face_y(ff: str, video: Path, at: float) -> float:
    """Where your face is, top to bottom (0-1), in one frame of the recording. 0.4 if not found."""
    try:
        import cv2
        import photos
        with tempfile.TemporaryDirectory() as t:
            png = Path(t) / "f.png"
            subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
                            str(png)], check=True)
            img = cv2.imread(str(png))
        h, w = img.shape[:2]
        det = cv2.FaceDetectorYN.create(str(photos.FACE_MODEL), "", (w, h), 0.7)
        _, faces = det.detect(img)
        if faces is None or not len(faces):
            return 0.4
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])[:4]
        return float((y + fh / 2) / h)
    except Exception:
        return 0.4


def presenter_graph(face: float, src_w: int, src_h: int) -> str:
    """Scale your video to fill 1080 wide and crop TAKE_H tall around your face (eyes about a third down)."""
    scaled_h = round(src_h * 1080 / src_w / 2) * 2
    if scaled_h < TAKE_H:   # a landscape recording: fill the height instead
        return f"scale=-2:{TAKE_H},crop=1080:{TAKE_H},setsar=1"
    y = int(min(max(face * scaled_h - TAKE_H * 0.42, 0), scaled_h - TAKE_H))
    return f"scale=1080:{scaled_h},crop=1080:{TAKE_H}:0:{y},setsar=1"


def probe(ff: str, video: Path) -> tuple[int, int]:
    res = subprocess.run([ff, "-hide_banner", "-i", str(video)], capture_output=True, text=True)
    m = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", res.stderr)
    w, h = (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)
    if re.search(r"rotate\s*:\s*-?(90|270)|displaymatrix: rotation of -?90", res.stderr):
        w, h = h, w   # phones store portrait video sideways with a rotation flag; ffmpeg turns it upright
    return w, h


def prepare(ff: str, raw: Path, lines: list[str], work: Path) -> dict:
    """Clean sound, line timing, trim and crop. Returns the voice dict video.make_reel uses, plus notes."""
    asr = work / "asr.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-vn", "-ac", "1", "-ar", "16000", str(asr)],
                   check=True)
    first, last, pauses = speech_span(ff, asr)
    words = transcribe(asr)
    notes, heard = [], ""
    starts = None
    if words:
        heard = " ".join(w["w"] for w in words)
        got = align(lines, words)
        if got:
            starts, matched = got
            first, last = min(first, words[0]["s"]), max(words[-1]["e"], min(last, words[-1]["e"] + 0.6))
            if matched < 0.8:
                notes.append(f"about {round(100 * (1 - matched))}% of the script wasn't heard as written")
        else:
            notes.append("couldn't match every line to your recording, so the lines follow your pauses")
    if not starts:
        starts = pause_starts(lines, first, last, pauses)
    t0, t1 = max(0.0, first - LEAD_IN), last + LEAD_OUT
    clean = work / "voice.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(raw), "-vn",
                    "-af", CLEAN, "-ac", "1", "-ar", "44100", str(clean)], check=True)
    w, h = probe(ff, raw)
    graph = presenter_graph(face_y(ff, raw, (first + last) / 2), w, h)
    clip = work / "presenter.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(raw), "-an",
                    "-vf", f"{graph},fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    str(clip)], check=True)
    rel = [s - t0 for s in starts]
    rel[0] = 0.0
    ends = rel[1:] + [t1 - t0]
    durs = [round(max(0.8, e - s), 3) for s, e in zip(rel, ends)]
    return {"wav": clean, "durs": durs[:-1], "tail": durs[-1], "script": " ".join(lines), "name": "",
            "take": clip, "notes": notes, "heard": heard, "seconds": round(t1 - t0, 1)}


def build_one(week: Path, post_id: str, dry: bool = False) -> str:
    """Downloads, builds and sends one recording for review. Returns what happened (for the log)."""
    P = _p()
    import tazama
    import video
    data = json.loads(week.read_text(encoding="utf-8"))
    post = next(p for p in data["posts"] if p["id"] == post_id)
    label = data["collection"]
    out_dir = P.EXPORTS / label
    work = Path(tempfile.mkdtemp(prefix="take-"))
    try:
        raw = work / "raw.mp4"
        tazama.download(P._tg_file_path, P.need("TELEGRAM_BOT_TOKEN")["TELEGRAM_BOT_TOKEN"], post["take"]["file_id"], raw)
        ff = video.ffmpeg_bin()
        voice = prepare(ff, raw, script_lines(post), work)
        made = render_take(post, voice, out_dir, ff)
        take = post["take"]
        take.update(status="review", file=made.name, seconds=voice["seconds"], notes=voice["notes"],
                    heard=voice["heard"][:900])
        if not dry:
            res = P.tg("sendVideo", {"chat_id": P.need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"],
                                     "caption": review_text(post, voice), "parse_mode": "HTML",
                                     "supports_streaming": "true", "reply_markup": review_buttons(label, post["id"])},
                       {"video": made})
            take["review_msg"] = res["result"]["message_id"]
        P.save_week(data)
        return f"take built for {post_id} ({voice['seconds']} s)"
    except Exception as e:
        post["take"].update(status="failed", error=str(e)[:300])
        P.save_week(data)
        if not dry:
            P._notify(f"🎬 Couldn't build your recording for <b>{P._esc(post_id)}</b> ({P._esc(str(e)[:160])}). "
                      "Reply to the script message with the video again.")
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)   # your raw video is never kept


def render_take(post: dict, voice: dict, out_dir: Path, ff: str) -> Path:
    """The Reel with you in it, as <id>-take.mp4 next to the text Reel."""
    import render
    import video
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1920})
        path = video.make_reel(page, render.make_env(), dict(post), out_dir, ff, voice=voice, name=f"{post['id']}-take")
        browser.close()
    return path


def review_text(post: dict, voice: dict) -> str:
    from html import escape
    lines = [f"🎬 <b>Your take</b> for {escape(post['id'])} ({voice['seconds']} s).",
             "✅ uses it in place of the text Reel; it goes out at its time."]
    for n in voice["notes"]:
        lines.append(f"⚠️ {escape(n)}")
    if voice.get("heard"):
        lines.append(f"\n<i>What I heard:</i> {escape(voice['heard'][:600])}")
    return "\n".join(lines)[:1000]


def review_buttons(label: str, pid: str) -> str:
    return json.dumps({"inline_keyboard": [[{"text": "✅ Use this take", "callback_data": f"t|{label}|ok:{pid}"[:64]},
                                            {"text": "🔁 Record again", "callback_data": f"t|{label}|re:{pid}"[:64]}]]})


def decide(data: dict, key: str, chat: str) -> str:
    """✅ Use this take / 🔁 Record again. Returns the short answer for the button."""
    P = _p()
    verb, _, pid = key.partition(":")
    post = next((p for p in data["posts"] if p["id"] == pid), None)
    take = (post or {}).get("take") or {}
    if not post or take.get("status") != "review":
        return "This take is no longer waiting for a decision."
    if post["status"] in {"published", "rejected", "missed"}:
        return f"{pid} is already {post['status']}."
    out_dir = P.EXPORTS / data["collection"]
    if verb == "ok":
        reel, made = out_dir / f"{pid}.mp4", out_dir / take["file"]
        if not made.exists():
            return "The take's video is missing: tap 🔁 Record again."
        text = out_dir / f"{pid}-text.mp4"
        if reel.exists() and not text.exists():
            shutil.copy(reel, text)
        shutil.copy(made, reel)
        take["status"] = "ok"
        post["presenter"] = "recorded"
        return "✅ Your take goes out with this post."
    if verb == "re":
        res = P.tg("sendMessage", {"chat_id": chat, "text": ask_text(post, data["collection"]), "parse_mode": "HTML",
                                   "reply_markup": json.dumps({"force_reply": True})})
        post["take"] = {"status": "asked", "ask_msg": res["result"]["message_id"]}
        return "🔁 Script sent again: reply to it with the new video."
    return "Unknown choice."


def build_all(dry: bool = False) -> int:
    done = 0
    for week, pid in pending():
        try:
            print("  " + build_one(week, pid, dry))
            done += 1
        except Exception as e:
            print(f"::warning title=take::{pid}: {type(e).__name__}: {str(e)[:300]}", flush=True)
    return done


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "pending":
        sys.exit(0 if pending() else 1)
    if cmd == "build":
        build_all()
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
