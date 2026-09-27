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
