"""
sound.py — Jua Kesho's original audio: the "Jua chime" sonic logo and a light kalimba bed.

Everything is synthesised here (no samples, no licensed music), so every Reel ships
with original audio: Instagram requires audio for Reels to be recommended, and
original audio counts toward originality. Swap in a trending sound in-app when
posting to TikTok manually; that's still the strongest move there.

    python sound.py 9.5 out.wav [seed]
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 100

# A major pentatonic across two octaves (Hz): bright, open, no "wrong" notes possible
PENTA = [220.00, 246.94, 277.18, 329.63, 369.99, 440.00, 493.88, 554.37, 659.25, 739.99, 880.00]
# Chord roots as indices into PENTA: A - E - F#m - D feel, stays inside the pentatonic
PROGRESSIONS = [[0, 3, 4, 1], [0, 4, 3, 1], [5, 3, 0, 4]]


def kalimba(freq: float, dur: float = 1.1, vel: float = 1.0) -> np.ndarray:
    """Thumb-piano tone: fundamental + the kalimba's bright inharmonic partials, fast attack, exponential decay."""
    t = np.arange(int(SR * dur)) / SR
    env = np.exp(-t * 4.2) * (1 - np.exp(-t * 900))
    tone = (np.sin(2 * np.pi * freq * t)
            + 0.30 * np.sin(2 * np.pi * freq * 5.4 * t) * np.exp(-t * 14)
            + 0.12 * np.sin(2 * np.pi * freq * 13.2 * t) * np.exp(-t * 30))
    return (tone * env * vel).astype(np.float32)


def kick(dur: float = 0.35) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    f = 50 + 70 * np.exp(-t * 30)
    phase = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(phase) * np.exp(-t * 11)).astype(np.float32)


def shaker(rng: np.random.Generator, dur: float = 0.07) -> np.ndarray:
    n = int(SR * dur)
    noise = rng.standard_normal(n).astype(np.float32)
    noise = np.diff(noise, prepend=0)  # crude high-pass: keeps it airy, not hissy-low
    return noise * np.exp(-np.arange(n) / SR * 60)


def _place(buf: np.ndarray, sample: np.ndarray, at: float, gain: float) -> None:
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sample))
    buf[i:j] += sample[: j - i] * gain


def pluck(freq: float, dur: float = 0.5, rng: np.random.Generator | None = None, bright: float = 0.5) -> np.ndarray:
    """Karplus-Strong plucked string: the bright, dry guitar of benga (a noise burst through a tuned delay line)."""
    rng = rng or np.random.default_rng(0)
    n = int(SR * dur)
    period = max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, period).astype(np.float32)
    out = np.empty(n, dtype=np.float32)
    decay = 0.996
    for i in range(n):
        j = i % period
        out[i] = buf[j]
        buf[j] = decay * (bright * buf[j] + (1 - bright) * buf[(j + 1) % period])
    return out * np.exp(-np.arange(n) / SR * 3.0)


def chime() -> np.ndarray:
    """The sonic logo: three rising notes, like the sun coming up."""
    out = np.zeros(int(SR * 1.6), dtype=np.float32)
    for k, (note, at) in enumerate(((440.00, 0.0), (554.37, 0.14), (659.25, 0.28))):
        _place(out, kalimba(note, 1.3, 1.0 - k * 0.1), at, 0.55)
        _place(out, kalimba(note * 2, 0.8, 0.5), at, 0.12)
    return out


def bed(duration: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    beat = 60 / BPM
    out = np.zeros(int(SR * (duration + 1.5)), dtype=np.float32)
    prog = PROGRESSIONS[seed % len(PROGRESSIONS)]
    start = 1.0  # after the chime has spoken
    _place(out, chime(), 0.0, 1.0)
    t, bar = start, 0
    while t < duration:
        root = prog[bar % len(prog)]
        pattern = [root, root + 2, root + 4, root + 2, root + 5, root + 4, root + 2, root + 4]
        for step, idx in enumerate(pattern):  # eighth notes
            at = t + step * beat / 2
            if at >= duration:
                break
            note = PENTA[min(idx, len(PENTA) - 1)]
            vel = 0.8 if step % 2 == 0 else 0.55
            _place(out, kalimba(note, 0.9, vel), at, 0.32)
        for q in range(4):  # quarter-note pulse
            at = t + q * beat
            if at < duration:
                _place(out, kick(), at, 0.55 if q in (0, 2) else 0.0)
                for s in range(2):
                    _place(out, shaker(rng), at + s * beat / 2 + beat / 4, 0.05)
        _place(out, kalimba(PENTA[root] / 2, 2.2, 0.9), t, 0.28)  # bass note per bar
        # benga-style guitar: quick interlocking sixteenths on the off-beats, high up the neck, kept quiet
        for q in range(16):
            if q % 4 in (1, 3) and t + q * beat / 4 < duration:
                idx = [root + 4, root + 5, root + 7, root + 5][(q // 2) % 4]
                _place(out, pluck(PENTA[min(idx, len(PENTA) - 1)], 0.35, rng), t + q * beat / 4, 0.16)
        t += beat * 4
        bar += 1
    out = out[: int(SR * duration)]
    fade_in, fade_out = int(SR * 0.05), int(SR * 0.9)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out) ** 1.5
    peak = np.max(np.abs(out)) or 1.0
    out = out / peak
    out = np.tanh(2.2 * out) / np.tanh(2.2)  # soft-clip limiter: louder on phone speakers, no harsh clipping
    return (out * 0.89).astype(np.float32)   # about -1 dBFS peak


def tension(duration: float, hits: list[float] | None = None, seed: int = 0) -> np.ndarray:
    """The urgent bed for civic Reels: a low pulse like a heartbeat, a clock ticking, a hit on every new line,
    and a rising tone into the last one. Original, synthesised, no licence needed."""
    rng = np.random.default_rng(seed)
    n = int(SR * (duration + 1.0))
    out = np.zeros(n, dtype=np.float32)
    t = np.arange(n) / SR
    # low drone: A1 + E2, slowly swelling
    swell = np.clip(t / max(duration, 1), 0, 1) * 0.6 + 0.4
    drone = (np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.41 * t) + 0.25 * np.sin(2 * np.pi * 110 * t))
    out += (drone * swell * 0.10).astype(np.float32)
    # heartbeat: lub-dub every 0.85s
    beat = 0.85
    k = 0.0
    while k < duration:
        _place(out, kick(0.3), k, 0.75)
        _place(out, kick(0.25), k + 0.22, 0.45)
        k += beat
    # clock tick on every half second
    tick = np.diff(rng.standard_normal(int(SR * 0.012)).astype(np.float32), prepend=0) * np.exp(-np.arange(int(SR * 0.012)) / SR * 400)
    k = 0.25
    while k < duration:
        _place(out, tick, k, 0.22)
        k += 0.5
    # a hit on every new line: low boom + bright noise burst
    for h in hits or []:
        if h < duration:
            _place(out, kick(0.6), h, 1.0)
            burst = rng.standard_normal(int(SR * 0.18)).astype(np.float32) * np.exp(-np.arange(int(SR * 0.18)) / SR * 22)
            _place(out, np.diff(burst, prepend=0), h, 0.18)
    # riser into the last line
    if hits:
        r0 = max(0.0, hits[-1] - 1.2)
        rt = np.arange(int(SR * (hits[-1] - r0))) / SR
        if len(rt):
            f = 220 + 660 * (rt / rt[-1] if rt[-1] else rt) ** 2
            riser = np.sin(2 * np.pi * np.cumsum(f) / SR) * (rt / (rt[-1] or 1)) * 0.12
            _place(out, riser.astype(np.float32), r0, 1.0)
    out = out[: int(SR * duration)]
    fade_out = int(SR * 0.7)
    out[-fade_out:] *= np.linspace(1, 0, fade_out) ** 1.5
    peak = np.max(np.abs(out)) or 1.0
    out = np.tanh(2.0 * out / peak) / np.tanh(2.0)
    return (out * 0.89).astype(np.float32)


def whoosh(dur: float = 0.34, seed: int = 0) -> np.ndarray:
    """An air whoosh for a transition: noise through a filter that opens and closes, swelling then gone."""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    noise = rng.standard_normal(n).astype(np.float32)
    t = np.arange(n) / n
    cutoff = 300 + 5200 * np.sin(np.pi * t) ** 2            # Hz: opens to ~5.5 kHz at the middle, closes again
    alpha = 1 - np.exp(-2 * np.pi * cutoff / SR)            # one-pole low-pass, coefficient per sample
    out, y = np.empty(n, dtype=np.float32), 0.0
    for i in range(n):
        y += alpha[i] * (noise[i] - y)
        out[i] = y
    env = np.sin(np.pi * t) ** 1.5
    return (out * env * 0.9).astype(np.float32)


def impact(dur: float = 0.5) -> np.ndarray:
    """A low hit when a figure lands: a deep kick and a short sub tail."""
    t = np.arange(int(SR * dur)) / SR
    sub = np.sin(2 * np.pi * 48 * t) * np.exp(-t * 7)
    return (kick(dur) * 0.8 + sub * 0.5).astype(np.float32)


def sfx(duration: float, cuts: list[float], lands: list[float] | None = None, seed: int = 0) -> np.ndarray:
    """The sound design laid over the music: a whoosh centred on every cut between lines, a hit where a figure
    lands. Silence everywhere else, so it sits on any track."""
    out = np.zeros(int(SR * (duration + 1.0)), dtype=np.float32)
    for k, c in enumerate(cuts):
        w = whoosh(seed=seed + k)
        _place(out, w, max(0.0, c - len(w) / SR / 2), 0.5)
    for h in lands or []:
        _place(out, impact(), h, 0.55)
    out = out[: int(SR * duration)]
    peak = float(np.abs(out).max()) if len(out) else 0.0
    return out * (0.6 / peak) if peak > 0.6 else out   # under the music, never clipping


# ---------------------------------------------------------------------------
# Mtaa Mode: an original street groove under the chat, and the cue sounds (all synthesised here)
# ---------------------------------------------------------------------------
STREET_BPM = 112
A_MINOR = [55.00, 61.74, 65.41, 73.42, 82.41, 87.31, 98.00, 110.00]   # A1 natural minor, the log drum's range


def log_drum(freq: float, dur: float = 0.38) -> np.ndarray:
    """The amapiano log drum: a pitched thump that bends down onto its note, slightly driven."""
    t = np.arange(int(SR * dur)) / SR
    f = freq * (1 + 0.7 * np.exp(-t * 45))
    phase = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(phase) + 0.35 * np.sin(2 * phase) + 0.12 * np.sin(3 * phase)
    return (np.tanh(1.8 * tone) * np.exp(-t * 7.5) * (1 - np.exp(-t * 600))).astype(np.float32)


def clap(rng: np.random.Generator, dur: float = 0.18) -> np.ndarray:
    """Three quick noise bursts, then a short tail: a hand clap."""
    n = int(SR * dur)
    noise = np.diff(rng.standard_normal(n).astype(np.float32), prepend=0)
    t = np.arange(n) / SR
    env = sum(np.where(t >= k * 0.011, np.exp(-(t - k * 0.011) * 160), 0.0) for k in range(3)) + 0.5 * np.exp(-t * 28)
    return (noise * env * 0.5).astype(np.float32)


def blip(f0: float = 880.0, f1: float = 1320.0, dur: float = 0.09) -> np.ndarray:
    """A message landing: a short rising tone with a soft click on the front."""
    t = np.arange(int(SR * dur)) / SR
    f = f0 + (f1 - f0) * np.minimum(1.0, t / (dur * 0.6))
    phase = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(phase) * np.exp(-t * 32) * (1 - np.exp(-t * 2500))).astype(np.float32)


def reveal() -> np.ndarray:
    """#1 lights up: three quick rising blips and a low hit."""
    out = np.zeros(int(SR * 0.7), dtype=np.float32)
    for k, (a, b) in enumerate(((660, 880), (880, 1100), (1100, 1480))):
        _place(out, blip(a, b, 0.12), k * 0.07, 0.8)
    _place(out, impact(0.5), 0.0, 0.45)
    return out


def womp(dur: float = 0.62) -> np.ndarray:
    """The twist: a falling tone with a wobble, the comic 'oh no'."""
    t = np.arange(int(SR * dur)) / SR
    f = 330 * np.exp(-t * 1.6) * (1 + 0.03 * np.sin(2 * np.pi * 7 * t))
    phase = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(phase) + 0.4 * np.sin(2 * phase)
    return (np.tanh(1.4 * tone) * np.exp(-t * 2.5) * (1 - np.exp(-t * 300)) * 0.7).astype(np.float32)


def typing_pops() -> np.ndarray:
    """The street brand's end-card sound: three pops, like the typing dots."""
    out = np.zeros(int(SR * 1.2), dtype=np.float32)
    for k in range(3):
        _place(out, blip(700 + 140 * k, 1000 + 180 * k, 0.1), 0.42 + k * 0.18, 0.7)
    return out


def knock() -> np.ndarray:
    """Three knocks on a steel door: short low thuds with a metallic ring."""
    out = np.zeros(int(SR * 0.75), dtype=np.float32)
    for k in range(3):
        t = np.arange(int(SR * 0.14)) / SR
        hit = (np.sin(2 * np.pi * 150 * t) + 0.35 * np.sin(2 * np.pi * 410 * t)) * np.exp(-t * 38)
        _place(out, hit.astype(np.float32), k * 0.2, 0.9)
    return out


def slap() -> np.ndarray:
    """A facepalm: a short bright smack."""
    rng = np.random.default_rng(5)
    n = int(SR * 0.12)
    noise = np.diff(rng.standard_normal(n).astype(np.float32), prepend=0)
    return (noise * np.exp(-np.arange(n) / SR * 55) * 0.6).astype(np.float32)


def buzz() -> np.ndarray:
    """A phone on vibrate: two short buzzes."""
    out = np.zeros(int(SR * 0.7), dtype=np.float32)
    t = np.arange(int(SR * 0.22)) / SR
    b = (np.sign(np.sin(2 * np.pi * 150 * t)) * 0.25 * (1 - np.exp(-t * 80)) * np.exp(-t * 3)).astype(np.float32)
    _place(out, b, 0.0, 0.8)
    _place(out, b, 0.36, 0.8)
    return out


def steps() -> np.ndarray:
    """Footsteps for a walk in or out (one every 0.31 s, as the cast's stride)."""
    out = np.zeros(int(SR * 1.4), dtype=np.float32)
    for k in range(4):
        t = np.arange(int(SR * 0.09)) / SR
        s = (np.sin(2 * np.pi * (95 + 10 * (k % 2)) * t) * np.exp(-t * 45)).astype(np.float32)
        _place(out, s, 0.08 + k * 0.31, 0.7)
    return out


def hit() -> np.ndarray:
    """The punchline lands: a soft low hit with a bright blip."""
    out = np.zeros(int(SR * 0.6), dtype=np.float32)
    _place(out, impact(0.5), 0.0, 0.55)
    _place(out, blip(880, 1320, 0.1), 0.0, 0.5)
    return out


CUE_SOUNDS = {"pop": (blip, 0.35), "reveal": (reveal, 0.75), "twist": (womp, 0.7), "knock": (knock, 0.8),
              "slap": (slap, 0.6), "buzz": (buzz, 0.55), "steps": (steps, 0.55), "whoosh": (lambda: whoosh(0.34, 3), 0.5),
              "hit": (hit, 0.75)}


def street(duration: float, cues: list[tuple[float, str]] | None = None, seed: int = 0) -> np.ndarray:
    """An original groove for Mtaa Mode (112 BPM: soft four-on-the-floor kick, log drum, claps on 2 and 4,
    shaker sixteenths) kept low, with the cue sounds on top: what the cast do, each line, each chart row."""
    rng = np.random.default_rng(seed)
    beat = 60 / STREET_BPM
    n = int(SR * (duration + 1.0))
    groove = np.zeros(n, dtype=np.float32)
    patterns = [[0, 3, 6, 10, 11, 14], [0, 3, 7, 10, 13], [0, 2, 6, 9, 12, 14]]
    pat = patterns[seed % len(patterns)]
    notes = [A_MINOR[i] for i in ((0, 4, 3, 2), (0, 2, 4, 6), (0, 3, 4, 0))[seed % 3]]
    t, bar = 0.0, 0
    while t < duration:
        for q in range(4):
            _place(groove, kick(), t + q * beat, 0.42)
            if q in (1, 3):
                _place(groove, clap(rng), t + q * beat, 0.32)
        for k in range(16):
            _place(groove, shaker(rng), t + k * beat / 4, 0.05 if k % 2 else 0.025)
        for i, step in enumerate(pat):
            _place(groove, log_drum(notes[(bar + i) % len(notes)] * (2 if i % 3 == 2 else 1)), t + step * beat / 4, 0.5)
        t += 4 * beat
        bar += 1
    peak = float(np.abs(groove).max()) or 1.0
    out = groove / peak * 0.42          # the groove sits under the cues
    for at, kind in cues or []:
        make, gain = CUE_SOUNDS.get(kind, CUE_SOUNDS["pop"])
        x = make()
        _place(out, x / (float(np.abs(x).max()) or 1.0), max(0.0, at), gain)   # each cue at its own level, never louder
    out = out[: int(SR * duration)]
    fade_in, fade_out = int(SR * 0.02), int(SR * 0.7)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out) ** 1.5
    out = np.tanh(1.6 * out) / np.tanh(1.6)
    peak = float(np.abs(out).max()) or 1.0
    return (out / peak * 0.89).astype(np.float32)


def write_wav(samples: np.ndarray, path: Path) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("bed.wav")
    write_wav(bed(dur, int(sys.argv[3]) if len(sys.argv) > 3 else 0), target)
    print("wrote", target)
