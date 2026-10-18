"""
twin.py — the AI presenter, built from a real video of James so it moves and sounds like him.

Why this looks real where the old one didn't: the old presenter animated ONE photo (frozen head, fixed
stare). The twin starts from a real 60-90 s video of James talking, so the head movement, blinks and
expressions are his own; only the mouth is redrawn to match the new words:

    voice   ElevenLabs instant voice clone of James (his accent), with the timing of every character
    mouth   LatentSync (ByteDance, Apache-2.0) on Replicate: re-syncs the lips of a slice of the real video
    Reel    the same split layout as a recorded take (takes.py): lines on top, presenter full-width below

Setup, once:
    1. Send the bot a 60-90 s video of you talking naturally, captioned  #presenter
       (daylight on your face, phone upright at eye level on something steady, final outfit and haircut).
    2. GitHub secrets ELEVENLABS_API_KEY and REPLICATE_API_TOKEN.
    The next run makes the voice and a sample Reel and sends it with ✅ Use the AI presenter / ❌ Not yet.
    Only after ✅ do Reels use it. Every Reel with it says the presenter is AI-generated.

    python twin.py pending      exit 0 if a #presenter video is waiting to be set up
    python twin.py setup        crop the video, clone the voice, make and send the sample
"""
from __future__ import annotations

import base64
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state" / "twin.json"
BASE = HERE / "content" / "presenter" / "base.mp4"   # the real video, cropped to the presenter's frame, no sound
ELEVEN = "https://api.elevenlabs.io/v1"
REPLICATE = "https://api.replicate.com/v1"
LIPSYNC_MODEL = "bytedance/latentsync"
VOICE_MODEL = os.environ.get("TWIN_VOICE_MODEL", "eleven_multilingual_v2")
VOICE_SETTINGS = {"stability": 0.45, "similarity_boost": 0.9, "style": 0.15, "use_speaker_boost": True}
FPS = 25                     # LatentSync works at 25 fps
MIN_BASE, MAX_BASE = 30, 180  # seconds of base video
SAMPLE = ["Ministries owe Kenya Power billions in unpaid bills.", "That is your money, sitting unpaid.",
          "Facts today. A better Kenya tomorrow."]


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------
def load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(rec: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")


def keys() -> tuple[str, str]:
    return os.environ.get("ELEVENLABS_API_KEY", ""), os.environ.get("REPLICATE_API_TOKEN", "")


def ready() -> bool:
    """Reels use the twin only once you tapped ✅ on its sample, and while both services are reachable."""
    rec = load()
    eleven, rep = keys()
    return bool(rec.get("approved") and rec.get("voice_id") and BASE.exists() and eleven and rep
                and os.environ.get("PRESENTER", "") != "off")


def pending() -> bool:
    return load().get("status") == "received"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _call(method: str, url: str, headers: dict, body: bytes | None = None, ctype: str | None = None,
          timeout: int = 120, raw: bool = False):
    h = dict(headers)
    if ctype:
        h["Content-Type"] = ctype
    for attempt in range(3):
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                return data if raw else json.loads(data or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(8 * (attempt + 1))
                continue
            raise RuntimeError(f"{url.split('?')[0]} {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                time.sleep(8 * (attempt + 1))
                continue
            raise RuntimeError(f"{url.split('?')[0]} unreachable: {e}") from e


def _multipart(fields: dict, files: list[tuple[str, Path, str]]) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    for name, path, ctype in files:
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                     f"Content-Type: {ctype}\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


# ---------------------------------------------------------------------------
# voice (ElevenLabs)
# ---------------------------------------------------------------------------
def clone_voice(sample: Path) -> str:
    eleven, _ = keys()
    body, ctype = _multipart({"name": "Kenya on Record presenter", "remove_background_noise": "true",
                              "description": "James Ndaiga, Kenyan English"}, [("files", sample, "audio/mpeg")])
    res = _call("POST", f"{ELEVEN}/voices/add", {"xi-api-key": eleven}, body, ctype, timeout=240)
    return res["voice_id"]


def line_times(lines: list[str], alignment: dict) -> list[float]:
    """When each line starts, from ElevenLabs' per-character times. The text is the lines joined by spaces."""
    starts_at = alignment["character_start_times_seconds"]
    out, pos = [], 0
    for line in lines:
        out.append(round(float(starts_at[min(pos, len(starts_at) - 1)]), 3))
        pos += len(line) + 1
    return out


def speak(lines: list[str], out_mp3: Path) -> list[float]:
    """James's cloned voice reads the lines; returns when each line starts (seconds)."""
    eleven, _ = keys()
    rec = load()
    text = " ".join(lines)
    body = json.dumps({"text": text, "model_id": VOICE_MODEL, "voice_settings": VOICE_SETTINGS}).encode()
    res = _call("POST", f"{ELEVEN}/text-to-speech/{rec['voice_id']}/with-timestamps?output_format=mp3_44100_128",
                {"xi-api-key": eleven}, body, "application/json", timeout=180)
    out_mp3.write_bytes(base64.b64decode(res["audio_base64"]))
    return line_times(lines, res["alignment"])


# ---------------------------------------------------------------------------
# mouth (LatentSync on Replicate)
# ---------------------------------------------------------------------------
def _upload(path: Path, ctype: str) -> str:
    _, token = keys()
    body, mp = _multipart({}, [("content", path, ctype)])
    res = _call("POST", f"{REPLICATE}/files", {"Authorization": f"Bearer {token}"}, body, mp, timeout=300)
    return res["urls"]["get"]


def lipsync(video: Path, audio: Path, out: Path, seed: int = 0, wait: int = 900) -> Path:
    """LatentSync redraws the mouth of `video` to match `audio`. Costs about $0.10 a run (Replicate, Oct 2026)."""
    _, token = keys()
    auth = {"Authorization": f"Bearer {token}"}
    version = _call("GET", f"{REPLICATE}/models/{LIPSYNC_MODEL}", auth)["latest_version"]["id"]
    inputs = {"video": _upload(video, "video/mp4"), "audio": _upload(audio, "audio/mpeg"),
              "guidance_scale": 1.5, "inference_steps": 20, "seed": seed or 0}
    pred = _call("POST", f"{REPLICATE}/predictions", auth,
                 json.dumps({"version": version, "input": inputs}).encode(), "application/json")
    end = time.time() + wait
    while pred.get("status") not in {"succeeded", "failed", "canceled"}:
        if time.time() > end:
            raise RuntimeError("lip sync took too long")
        time.sleep(5)
        pred = _call("GET", f"{REPLICATE}/predictions/{pred['id']}", auth)
    if pred["status"] != "succeeded":
        raise RuntimeError(f"lip sync {pred['status']}: {str(pred.get('error'))[:300]}")
    url = pred["output"] if isinstance(pred["output"], str) else pred["output"][0]
    out.write_bytes(_call("GET", url, {}, raw=True, timeout=300))
    return out


# ---------------------------------------------------------------------------
# the base video
# ---------------------------------------------------------------------------
def slice_plan(base_len: float, need: float, seed: int) -> tuple[float, bool]:
    """(start, loop?) for a slice of the base video `need` seconds long: a slice inside the video when it is long
    enough (a different moment for each Reel), else the video from the start, looped."""
    if base_len >= need + 0.2:
        return round(random.Random(seed).uniform(0, base_len - need), 2), False
    return 0.0, True


def base_slice(ff: str, need: float, seed: int, out: Path) -> Path:
    """`need` seconds of the base video: a different moment for each Reel, looped only if the video is shorter."""
    res = subprocess.run([ff, "-hide_banner", "-i", str(BASE)], capture_output=True, text=True)
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", res.stderr).groups()
    start, loop = slice_plan(int(h) * 3600 + int(m) * 60 + float(s), need, seed)
    src = ["-stream_loop", "-1"] if loop else ["-ss", f"{start:.3f}"]
    subprocess.run([ff, "-y", "-loglevel", "error", *src, "-i", str(BASE), "-t", f"{need:.3f}", "-an", "-r", str(FPS),
                    "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def prepare_base(ff: str, raw: Path) -> tuple[Path, Path, float]:
    """Your video -> the presenter frame (1080 x TAKE_H around your face, 25 fps, no sound) and a clean voice
    sample for the clone. Returns (base, voice sample, seconds)."""
    import takes
    work = Path(tempfile.mkdtemp(prefix="twin-"))
    asr = work / "a.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-vn", "-ac", "1", "-ar", "16000", str(asr)],
                   check=True)
    first, last, _ = takes.speech_span(ff, asr)
    seconds = last - first
    w, h = takes.probe(ff, raw)
    graph = takes.presenter_graph(takes.face_y(ff, raw, (first + last) / 2), w, h)
    BASE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-an", "-t", str(MAX_BASE),
                    "-vf", f"{graph},fps={FPS},format=yuv420p", "-c:v", "libx264", "-crf", "19", "-preset", "slow",
                    str(BASE)], check=True)
    sample = work / "voice.mp3"
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{max(0, first - 0.2):.2f}", "-to", f"{last + 0.3:.2f}",
                    "-i", str(raw), "-vn", "-af", takes.CLEAN, "-ac", "1", "-ar", "44100", "-b:a", "192k", str(sample)],
                   check=True)
    return BASE, sample, seconds


# ---------------------------------------------------------------------------
# what the Reel builder calls
# ---------------------------------------------------------------------------
def voice_for(lines: list[str], work: Path, seed: int, ff: str) -> dict:
    """The twin reads `lines` (the last is the sign-off). Returns the same dict a recorded take gives
    video.make_reel: clean audio, each line's length, and the lip-synced presenter clip."""
    mp3 = work / "twin.mp3"
    starts = speak(lines, mp3)
    res = subprocess.run([ff, "-hide_banner", "-i", str(mp3)], capture_output=True, text=True)
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", res.stderr).groups()
    total = int(h) * 3600 + int(m) * 60 + float(s)
    ends = starts[1:] + [total]
    durs = [round(max(0.8, e - a), 3) for a, e in zip(starts, ends)]
    durs[0] = round(durs[0] + starts[0], 3)   # any air before the first word belongs to the first line
    wav = work / "twin.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "44100", str(wav)], check=True)
    piece = base_slice(ff, total + 0.4, seed, work / "base.mp4")
    clip = lipsync(piece, mp3, work / "synced.mp4", seed=seed % 100000 + 1)
    return {"wav": wav, "durs": durs[:-1], "tail": durs[-1], "script": " ".join(lines), "name": "AI presenter",
            "take": clip, "ai": True}


# ---------------------------------------------------------------------------
# Telegram: your #presenter video, the sample, ✅ / ❌
# ---------------------------------------------------------------------------
def is_base(msg: dict) -> bool:
    import takes
    return bool(takes.video_of(msg) and "#presenter" in str(msg.get("caption", "")).lower())


def intake(msg: dict) -> str:
    import takes
    v = takes.video_of(msg)
    if msg.get("video_note"):
        return "🧑🏾‍💼 A round video note is too small. Record a normal video and send it with the caption #presenter."
    if int(v.get("file_size") or 0) > takes.MAX_BYTES:
        return ("🧑🏾‍💼 That file is over 20 MB, the most the bot can fetch. Send it as a normal video (not a file) so "
                "Telegram compresses it, or keep it to about 60 seconds.")
    if int(v.get("duration") or 0) < MIN_BASE:
        return f"🧑🏾‍💼 That's {v.get('duration', 0)} s. I need {MIN_BASE}-90 s of you talking naturally."
    rec = load()
    rec.update(status="received", file_id=v["file_id"], duration=v.get("duration"), approved=False)
    save(rec)
    return ("🧑🏾‍💼 Got your presenter video. Next run: your voice clone and a sample Reel come back here for ✅."
            + ("" if all(keys()) else "\n\n⚠️ First add the GitHub secrets ELEVENLABS_API_KEY and "
               "REPLICATE_API_TOKEN, or the sample can't be made."))


def setup(dry: bool = False) -> str:
    import pipeline as P
    import tazama
    import video
    rec = load()
    if not all(keys()):
        rec["status"] = "needs_keys"
        save(rec)
        if not dry:
            P._notify("🧑🏾‍💼 Your presenter video is saved, but the AI presenter needs two GitHub secrets: "
                      "<code>ELEVENLABS_API_KEY</code> and <code>REPLICATE_API_TOKEN</code>. Add them, then send the "
                      "video again with #presenter.")
        return "needs keys"
    ff = video.ffmpeg_bin()
    work = Path(tempfile.mkdtemp(prefix="twin-setup-"))
    raw = work / "raw.mp4"
    tazama.download(P._tg_file_path, P.need("TELEGRAM_BOT_TOKEN")["TELEGRAM_BOT_TOKEN"], rec["file_id"], raw)
    _, sample, seconds = prepare_base(ff, raw)
    rec["voice_id"] = clone_voice(sample)
    rec.update(status="sample", base_seconds=round(seconds, 1))
    save(rec)
    v = voice_for(SAMPLE, work, 7, ff)
    out = work / "sample.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(v["take"]), "-i", str(v["wav"]), "-map", "0:v",
                    "-map", "1:a", "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(out)], check=True)
    if not dry:
        P.tg("sendVideo", {"chat_id": P.need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"], "supports_streaming": "true",
                           "caption": "🧑🏾‍💼 <b>Your AI presenter</b>: your video, your cloned voice, new words. "
                                      "Judge it like a stranger would. ✅ and every Reel uses it (labelled as AI); "
                                      "❌ and nothing changes.",
                           "parse_mode": "HTML",
                           "reply_markup": json.dumps({"inline_keyboard": [[
                               {"text": "✅ Use the AI presenter", "callback_data": "w|twin|yes"},
                               {"text": "❌ Not yet", "callback_data": "w|twin|no"}]]})}, {"video": out})
    return f"sample sent ({seconds:.0f} s of base video)"


def decide(yes: bool) -> str:
    rec = load()
    if rec.get("status") != "sample" or not rec.get("voice_id"):
        return "There's no AI presenter sample waiting."
    rec["approved"] = yes
    rec["status"] = "approved" if yes else "declined"
    save(rec)
    return ("✅ New Reels will use the AI presenter, labelled as AI." if yes
            else "❌ Not used. Send a better #presenter video any time.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "pending":
        sys.exit(0 if pending() else 1)
    if cmd == "setup":
        print(setup())
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
