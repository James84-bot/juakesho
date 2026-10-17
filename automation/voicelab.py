"""
voicelab.py — the presenter's voice, made on our own machines at no cost.

Two engines, both open source and free for commercial use, run on GitHub's free CPU runners:

  * Kokoro-82M (Apache-2.0): ready-made synthetic voices. Fast, but American or British accents only.
  * Chatterbox-Turbo (MIT, Resemble AI): clones a voice from a 5 s+ reference clip. Every file it makes carries
    Resemble's inaudible Perth watermark, so the audio can always be identified as AI-made.

The presenter must sound Kenyan, and no free model ships a Kenyan voice, so the character voice is made from a
real Kenyan recording given with consent (James's own voice note to the bot). It is then shifted into a distinct
character with plain ffmpeg filters, so it does not sound like James.

    python voicelab.py kokoro       # synthetic voices: accent check + CPU speed, sent to Telegram
    python voicelab.py clone        # the character voices from the newest voice note James sent the bot
    python voicelab.py clone --dry  # same, but writes files to ./voicelab-out and sends nothing
    python voicelab.py pending      # exit 0 when a new recording is waiting (the tick runs clone then)

Nothing here posts publicly: samples only go to the owner's Telegram chat.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pipeline as P

VOICE_STATE = P.STATE / "voice.json"
RECORDING = P.HERE / "content" / "presenter" / "voice.mp3"   # James reading the script, noise removed and EQ'd
MIN_REF_SECONDS = 6.0       # Chatterbox refuses references of 5 s or less; keep a margin
REF_SECONDS = 20.0          # it only conditions on the first ~10-15 s; 20 s of clean speech is plenty

# The script the samples read: the channel's real voice (news first, a demand, the sign-off).
LINES = [
    "Ministries owe Kenya Power seven point three five billion shillings in unpaid bills.",
    "Ordinary customers lose power the moment their tokens run out.",
    "Kenyans demand that the Treasury publishes a date for paying this debt.",
    "Facts today. A better Kenya tomorrow.",
]
SCRIPT = " ".join(LINES)

KOKORO_VOICES = [("am_michael", "American male"), ("am_fenrir", "American male, deeper"),
                 ("bm_george", "British male"), ("bm_fable", "British male, younger")]

# Character voices made from one clean clone. asetrate shifts pitch and formants together (a different-sounding
# person, not a chipmunk at these small steps); atempo puts the speed back; the EQ/compressor give broadcast body.
BODY = "highpass=f=70,equalizer=f=180:t=q:w=1:g=2,equalizer=f=3500:t=q:w=1.2:g=2,acompressor=threshold=-18dB:ratio=3:attack=10:release=120,loudnorm=I=-16:TP=-1.5:LRA=11"
CHARACTERS = [
    ("Calm anchor", "Your clone, deeper and slower: steady and trusted", 0.92, 0.97),
    ("Street reporter", "Your clone, a little brighter and quicker: young and energetic", 1.05, 1.04),
    ("Your voice, polished", "Your own voice, studio-cleaned and a touch slower: the most natural", 1.0, 0.97),
]


def log(msg: str) -> None:
    P.log(f"voicelab: {msg}")
    if os.environ.get("GITHUB_ACTIONS"):   # readable on the run page and through the API (logs are not)
        print(f"::notice title=voicelab::{msg}", flush=True)


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args: list[str]) -> None:
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed: {res.stderr[-600:]}")


def seconds(path: Path) -> float:
    import soundfile as sf
    info = sf.info(str(path))
    return info.frames / info.samplerate


def to_mp3(wav: Path, mp3: Path, rate: float = 1.0, tempo: float = 1.0) -> Path:
    """Character shift + broadcast polish, encoded for Telegram's audio player."""
    chain = []
    if rate != 1.0:
        chain += [f"asetrate=24000*{rate}", "aresample=24000", f"atempo={tempo / rate:.4f}"]
    elif tempo != 1.0:
        chain += [f"atempo={tempo:.4f}"]
    chain.append(BODY)
    run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav), "-af", ",".join(chain),
         "-ar", "44100", "-ac", "1", "-b:a", "128k", str(mp3)])
    return mp3


def send(mp3: Path, title: str, caption: str, dry: bool, choice: str | None = None) -> None:
    if dry:
        log(f"{title}: {mp3} ({caption})")
        return
    chat = P.need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"]
    fields = {"chat_id": chat, "title": title, "performer": "Kenya on Record voice lab",
              "caption": caption[:1000], "parse_mode": "HTML"}
    if choice:   # one tap makes this the presenter's voice (pipeline.collect handles v|voice|<name>)
        fields["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": "✅ Use this voice",
                                                                    "callback_data": f"v|voice|{choice}"}]]})
    P.tg("sendAudio", fields, files={"audio": mp3})


def note(text: str, dry: bool) -> None:
    if dry:
        log(text)
        return
    P.tg("sendMessage", {"chat_id": P.need("TELEGRAM_CHAT_ID")["TELEGRAM_CHAT_ID"], "text": text, "parse_mode": "HTML"})


# ---------------------------------------------------------------------------
# Kokoro: ready-made synthetic voices
# ---------------------------------------------------------------------------
def kokoro(out: Path, dry: bool) -> None:
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    note("🎙 <b>Voice lab 1/2: ready-made AI voices</b> (Kokoro, free, open source). Listen for the accent: "
         "none of these is Kenyan, which is why the presenter's voice will come from your recording.", dry)
    pipes = {}
    for voice, label in KOKORO_VOICES:
        lang = voice[0]                        # 'a' American, 'b' British
        pipes.setdefault(lang, KPipeline(lang_code=lang))
        t0 = time.time()
        audio = np.concatenate([a for _, _, a in pipes[lang](SCRIPT, voice=voice)])
        took = time.time() - t0
        wav = out / f"kokoro-{voice}.wav"
        sf.write(str(wav), audio, 24000)
        dur = seconds(wav)
        send(to_mp3(wav, out / f"kokoro-{voice}.mp3"), f"Kokoro · {label}",
             f"<b>{label}</b> ({voice})\n{dur:.0f} s of speech made in {took:.1f} s on GitHub's free 4-core machine "
             f"({dur / max(took, 0.01):.1f}× real time).", dry)
        log(f"{voice}: {dur:.1f}s audio in {took:.1f}s")


# ---------------------------------------------------------------------------
# Chatterbox: the character voice, cloned from James's voice note
# ---------------------------------------------------------------------------
def reference(tmp: Path) -> Path:
    """Downloads the voice note the collector saved (state/voice.json) and cuts a clean reference clip:
    mono 24 kHz, leading silence and long pauses removed, the first REF_SECONDS of speech."""
    if not VOICE_STATE.exists():
        raise SystemExit("No voice recording yet: send a voice note (or an audio file) to the bot first.")
    rec = json.loads(VOICE_STATE.read_text())
    if rec.get("file_id") == "repo":   # the studio-cleaned recording kept with the presenter's photos
        raw = RECORDING
    else:
        token = P.need("TELEGRAM_BOT_TOKEN")["TELEGRAM_BOT_TOKEN"]
        path = P._tg_file_path(rec["file_id"])
        raw = tmp / ("source" + (Path(path).suffix or ".ogg"))
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{path}", timeout=120) as r:
            raw.write_bytes(r.read())
    ref = tmp / "reference.wav"
    run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(raw), "-af",
         "highpass=f=70,silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=-1:stop_duration=0.6:stop_threshold=-45dB,"
         "loudnorm=I=-20:TP=-2", "-t", str(REF_SECONDS), "-ac", "1", "-ar", "24000", str(ref)])
    got = seconds(ref)
    if got < MIN_REF_SECONDS:
        raise SystemExit(f"The recording has only {got:.1f} s of speech after trimming silence; "
                         f"at least {MIN_REF_SECONDS:.0f} s is needed. Please send a longer one.")
    log(f"reference: {got:.1f}s of speech from {rec.get('duration', '?')}s recording")
    return ref


def stand_in(tmp: Path) -> Path:
    """A reference clip from Chatterbox's own built-in voice: proves the whole clone path works before James's
    recording arrives. Never used for a real post."""
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    t0 = time.time()
    model = ChatterboxTTS.from_pretrained(device="cpu")
    wav = model.generate("This is a stand-in voice for testing. It reads a few plain sentences so the clone has "
                         "enough clean speech to learn from, and then the real recording replaces it.")
    ref = tmp / "stand-in.wav"
    ta.save(str(ref), wav, model.sr)
    log(f"stand-in reference: {seconds(ref):.1f}s made in {time.time() - t0:.0f}s")
    return ref


def clone(out: Path, dry: bool, selftest: bool = False) -> None:
    import torch
    import torchaudio as ta
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    with tempfile.TemporaryDirectory() as t:
        ref = stand_in(Path(t)) if selftest else reference(Path(t))
        t0 = time.time()
        model = ChatterboxTurboTTS.from_pretrained(device="cpu")
        load = time.time() - t0
        t0 = time.time()
        parts = [model.generate(line, audio_prompt_path=str(ref)) for line in LINES]
        took = time.time() - t0
    gap = torch.zeros(1, int(model.sr * 0.35))
    wav = torch.cat([x for p in parts for x in (p, gap)], dim=1)
    base = out / "clone.wav"
    ta.save(str(base), wav, model.sr)
    dur = seconds(base)
    log(f"clone: {dur:.1f}s audio in {took:.1f}s (+{load:.0f}s model load)")
    note(("🧪 <b>Voice lab self-test</b> (a stand-in voice, not yours): proves the clone works on our free machines. "
          if selftest else "🎙 <b>Voice lab 2/2: the presenter's voice</b>, made from your recording on our own free machines. ") +
         f"{dur:.0f} s of speech took {took:.0f} s ({dur / max(took, 0.01):.2f}× real time). "
         "Pick the one that sounds right; each carries an inaudible AI watermark.", dry)
    for name, why, rate, tempo in CHARACTERS:
        mp3 = to_mp3(base, out / f"{name.lower().replace(' ', '-')}.mp3", rate, tempo)
        send(mp3, name, f"<b>{name}</b>: {why}", dry, None if selftest else name)
    if not dry and not selftest:   # the tick only remakes the voice when a newer recording arrives
        rec = json.loads(VOICE_STATE.read_text())
        rec["made_for"] = rec.get("file_unique_id") or rec["file_id"]
        rec["made_at"] = P.now().isoformat()
        VOICE_STATE.write_text(json.dumps(rec, indent=2) + "\n")


def chosen() -> tuple[str, float, float] | None:
    """The character voice James picked (name, rate, tempo), or None: no presenter until he picks one."""
    if os.environ.get("PRESENTER", "").lower() in {"0", "off", "no"} or not VOICE_STATE.exists():
        return None
    name = json.loads(VOICE_STATE.read_text()).get("chosen")
    return next(((n, r, t) for n, _, r, t in CHARACTERS if n == name), None)


def choose(name: str) -> bool:
    """Called from the Telegram tap: makes `name` the presenter's voice. False for an unknown name."""
    if not VOICE_STATE.exists() or name not in {n for n, *_ in CHARACTERS}:
        return False
    rec = json.loads(VOICE_STATE.read_text())
    rec["chosen"], rec["chosen_at"] = name, P.now().isoformat()
    VOICE_STATE.write_text(json.dumps(rec, indent=2) + "\n")
    return True


def choose_off() -> None:
    """/voice-off in Telegram: Reels go back to on-screen text only, until a voice is tapped again."""
    if VOICE_STATE.exists():
        rec = json.loads(VOICE_STATE.read_text())
        rec.pop("chosen", None)
        rec["off_at"] = P.now().isoformat()
        VOICE_STATE.write_text(json.dumps(rec, indent=2) + "\n")


_MODEL: dict = {}


def speak(lines: list[str], out_wav: Path, character: tuple[str, float, float], gap: float = 0.28,
          stand_in_voice: bool = False) -> list[float]:
    """Reads each line in the presenter's voice into one wav (44.1 kHz mono, broadcast-polished) and returns how
    long each line lasts in it, gap included, so the Reel can hold each beat exactly as long as it is spoken."""
    import numpy as np
    import soundfile as sf
    import torch
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    _, rate, tempo = character
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        if "ref" not in _MODEL or not Path(_MODEL["ref"]).exists():
            keep = Path(tempfile.mkdtemp(prefix="voice-ref-"))
            _MODEL["ref"] = str(stand_in(keep) if stand_in_voice else reference(keep))
        if "tts" not in _MODEL:
            _MODEL["tts"] = ChatterboxTurboTTS.from_pretrained(device="cpu")
        model = _MODEL["tts"]
        raw, lens = [], []
        for line in lines:
            wav = model.generate(line.replace("*", ""), audio_prompt_path=_MODEL["ref"]).squeeze(0).numpy()
            pad = np.zeros(int(model.sr * gap), dtype=wav.dtype)
            raw += [wav, pad]
            lens.append((len(wav) + len(pad)) / model.sr)
        sf.write(str(t / "raw.wav"), np.concatenate(raw), model.sr)
        chain = []
        if rate != 1.0:
            chain += [f"asetrate={model.sr}*{rate}", f"aresample={model.sr}", f"atempo={tempo / rate:.4f}"]
        elif tempo != 1.0:
            chain.append(f"atempo={tempo:.4f}")
        chain.append(BODY)
        run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(t / "raw.wav"), "-af", ",".join(chain),
             "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)])
    return [round(x / tempo, 3) for x in lens]   # rate and tempo together change the speed by `tempo` only


def pending() -> bool:
    """True when a recording arrived that has no voice samples yet (the tick's cue to run clone)."""
    if not VOICE_STATE.exists():
        return False
    rec = json.loads(VOICE_STATE.read_text())
    return rec.get("made_for") != (rec.get("file_unique_id") or rec["file_id"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("step", choices=["kokoro", "clone", "pending"])
    ap.add_argument("--dry", action="store_true", help="write files to ./voicelab-out, send nothing")
    ap.add_argument("--selftest", action="store_true", help="clone a stand-in voice instead of James's recording")
    a = ap.parse_args(argv)
    if a.step == "pending":   # exit 0 = a new recording is waiting for its voice
        return 0 if pending() else 1
    out = Path("voicelab-out") if a.dry else Path(tempfile.mkdtemp(prefix="voicelab-"))
    out.mkdir(exist_ok=True)
    if a.step == "kokoro":
        kokoro(out, a.dry)
    else:
        clone(out, a.dry, a.selftest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
