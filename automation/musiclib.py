"""
musiclib.py — fills content/music with real, licensed instrumental tracks, so Reels carry music instead of the
synthesised bed.

Source: Kevin MacLeod (incompetech.com), whose catalogue is licensed Creative Commons Attribution 4.0: free for
commercial use, including social video, on condition of credit. The credit goes where our credits go (the Sources
comment on Instagram and Facebook, the end of the description on YouTube and TikTok). Instrumental only, so every
track is clean for everyone.

Each track is cut to CUT_S seconds from a little way in (past the quiet intro), at 128 kbps, so the folder stays small.
Moods: "urgent" for civic posts, "uplifting" for good news (video.music_track picks by mood).

    python musiclib.py            # fetch (skips files already there)
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUSIC = HERE / "content" / "music"
PIECES = "https://incompetech.com/music/royalty-free/pieces.json"
MP3 = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/{}.mp3"
LICENCE = "CC BY 4.0 (creativecommons.org/licenses/by/4.0), incompetech.com"
CUT_S = 45
PER_MOOD = 6
MOODS = {
    "urgent": ("driving", "intense", "tense", "suspense", "action", "pulsing", "serious", "dark", "epic", "urgent"),
    "uplifting": ("bright", "uplifting", "happy", "hopeful", "inspiring", "upbeat", "positive", "grooving", "triumphant"),
}
AVOID = ("horror", "creepy", "christmas", "holiday", "comedy", "silly", "funny", "lullaby", "wedding", "funeral", "sad")


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Kenya on Record music library)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _text(piece: dict) -> str:
    return " ".join(str(v) for v in piece.values() if isinstance(v, (str, int, float))).lower()


def _filename(piece: dict) -> str:
    return str(piece.get("filename") or piece.get("file") or piece.get("title") or "").strip()


def pick(pieces: list[dict], per_mood: int = PER_MOOD) -> list[tuple[str, dict]]:
    """(mood, piece) pairs: the pieces whose feel or genre names the mood, never a mood we avoid, each piece once."""
    used, out = set(), []
    for mood, words in MOODS.items():
        got = 0
        for p in pieces:
            name, text = _filename(p), _text(p)
            if not name or name in used or any(w in text for w in AVOID):
                continue
            feel = " ".join(str(p.get(k, "")) for k in ("feel", "genre", "description")).lower() or text
            if any(re.search(rf"\b{w}\b", feel) for w in words):
                out.append((mood, p))
                used.add(name)
                got += 1
                if got >= per_mood:
                    break
    return out


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] + ".mp3"


def entry(mood: str, piece: dict, file: str, start: float) -> dict:
    title = str(piece.get("title") or _filename(piece))
    return {"file": file, "artist": "Kevin MacLeod", "title": title, "mood": mood, "start": 0.0,
            "rights": LICENCE, "clean": True, "source": MP3.format(urllib.parse.quote(_filename(piece))),
            "credit": f'Music: "{title}" by Kevin MacLeod (incompetech.com), CC BY 4.0', "cut_from": round(start, 1)}


def cut(ff: str, raw: Path, out: Path) -> float:
    """CUT_S seconds from past the intro (15% in, at most 20 s), faded at both ends; returns where the cut starts."""
    probe = subprocess.run([ff, "-hide_banner", "-i", str(raw)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    start = min(20.0, dur * 0.15) if dur > CUT_S + 5 else 0.0
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", str(CUT_S), "-i", str(raw),
                    "-af", f"afade=t=in:st=0:d=0.6,afade=t=out:st={CUT_S - 1.5}:d=1.5", "-ac", "2", "-ar", "44100",
                    "-b:a", "128k", str(out)], check=True)
    return start


def fetch(per_mood: int = PER_MOOD, get=_get, ff: str | None = None) -> dict:
    """Adds tracks to tracks.json; returns {"added", "kept", "errors"}. Never removes a track already there."""
    import video
    ff = ff or video.ffmpeg_bin()
    reg_file = MUSIC / "tracks.json"
    reg = json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.exists() else {"tracks": []}
    have = {t["file"] for t in reg.get("tracks", [])}
    pieces = json.loads(get(PIECES))
    if isinstance(pieces, dict):   # the list may sit under a key
        pieces = next((v for v in pieces.values() if isinstance(v, list)), [])
    added, errors = [], []
    for mood, piece in pick([p for p in pieces if isinstance(p, dict)], per_mood):
        file = slug(_filename(piece))
        if file in have:
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / "raw.mp3"
                raw.write_bytes(get(MP3.format(urllib.parse.quote(_filename(piece))), 120))
                start = cut(ff, raw, MUSIC / file)
            reg.setdefault("tracks", []).append(entry(mood, piece, file, start))
            added.append(f"{mood}: {piece.get('title') or file}")
        except Exception as e:   # one track failing never stops the rest
            errors.append(f"{_filename(piece)}: {str(e)[:120]}")
    MUSIC.mkdir(parents=True, exist_ok=True)
    reg_file.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"added": added, "kept": len(have), "errors": errors, "sample_keys": sorted(pieces[0])[:20] if pieces else []}


if __name__ == "__main__":
    print(json.dumps(fetch(), indent=1))
