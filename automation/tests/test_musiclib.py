"""The licensed music library: picking by mood, the credit, and a fetch that never stops on one bad track (no network)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import musiclib  # noqa: E402

PIECES = [
    {"title": "Volatile Reaction", "filename": "Volatile Reaction.mp3", "feel": "Driving, Intense", "genre": "Electronica", "bpm": "120"},
    {"title": "Happy Bee", "filename": "Happy Bee.mp3", "feel": "Bright, Uplifting", "genre": "Pop", "bpm": "110"},
    {"title": "Sergio's Magic Dustbin", "filename": "Sergio's Magic Dustbin.mp3", "feel": "Driving, Quirky", "genre": "Electronica", "bpm": "120"},
    {"title": "Slow Burn", "filename": "Slow Burn.mp3", "feel": "Tense", "genre": "Soundtrack", "bpm": "60"},
    {"title": "Spooky Halls", "filename": "Spooky Halls", "feel": "Dark, Tense", "genre": "Horror"},
    {"title": "Deck the Halls", "filename": "Deck the Halls", "feel": "Bright", "genre": "Holiday"},
    {"title": "Calm Waters", "filename": "Calm Waters", "feel": "Calming", "genre": "Ambient"},
]


class Library(unittest.TestCase):
    def test_pick_by_mood_and_never_horror_or_holiday(self):
        got = [(m, p["title"]) for m, p in musiclib.pick(PIECES)]
        self.assertEqual(got, [("urgent", "Volatile Reaction"), ("uplifting", "Happy Bee")])

    def test_quirky_and_out_of_tempo_pieces_are_never_picked(self):
        names = [p["title"] for _, p in musiclib.pick(PIECES)]
        self.assertNotIn("Sergio's Magic Dustbin", names)
        self.assertNotIn("Slow Burn", names)                      # 60 bpm drags under a 3-second line

    def test_replace_removes_only_the_tracks_this_module_added(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(musiclib, "MUSIC", Path(d)):
            Path(d, "old.mp3").write_bytes(b"x")
            Path(d, "artist.mp3").write_bytes(b"x")
            Path(d, "tracks.json").write_text(json.dumps({"tracks": [
                {"file": "old.mp3", "source": "https://incompetech.com/x.mp3"},
                {"file": "artist.mp3", "source": "permission by email"}]}))
            with mock.patch.object(musiclib, "cut", lambda ff, raw, out: out.write_bytes(b"m") or 10.0):
                musiclib.fetch(get=lambda u, t=60: json.dumps([]).encode() if u == musiclib.PIECES else b"", ff="ffmpeg", replace=True)
            reg = json.loads(Path(d, "tracks.json").read_text())
            self.assertEqual([t["file"] for t in reg["tracks"]], ["artist.mp3"])
            self.assertFalse(Path(d, "old.mp3").exists())

    def test_sung_tracks_are_never_picked(self):
        sung = [{"title": "Galactic Rap", "filename": "Galactic Rap.mp3", "feel": "Driving", "genre": "Hip Hop", "bpm": "100"}]
        self.assertEqual(musiclib.pick(sung), [])

    def test_entry_is_licensed_clean_and_credited(self):
        e = musiclib.entry("urgent", PIECES[0], "volatile-reaction.mp3", 12.0)
        self.assertTrue(e["clean"])
        self.assertIn("CC BY 4.0", e["rights"])
        self.assertEqual(e["credit"], 'Music: "Volatile Reaction" by Kevin MacLeod (incompetech.com), CC BY 4.0')
        self.assertTrue(e["source"].endswith("Volatile%20Reaction.mp3"))

    def test_fetch_adds_tracks_keeps_old_ones_and_survives_a_bad_download(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(musiclib, "MUSIC", Path(d)):
            Path(d, "tracks.json").write_text(json.dumps({"tracks": [{"file": "happy-bee.mp3", "rights": "x" * 9}]}))

            def get(url, timeout=60):
                if url == musiclib.PIECES:
                    return json.dumps(PIECES).encode()
                raise OSError("404")
            with mock.patch.object(musiclib, "cut", lambda ff, raw, out: out.write_bytes(b"m") or 10.0):
                got = musiclib.fetch(get=get, ff="ffmpeg")
            self.assertEqual(got["added"], [])                        # the one new track failed to download
            self.assertEqual(len(got["errors"]), 1)
            self.assertEqual(got["kept"], 1)                          # the old track is never removed

            def ok(url, timeout=60):
                return json.dumps(PIECES).encode() if url == musiclib.PIECES else b"ID3"
            with mock.patch.object(musiclib, "cut", lambda ff, raw, out: out.write_bytes(b"m") or 10.0):
                got = musiclib.fetch(get=ok, ff="ffmpeg")
            self.assertEqual(got["added"], ["urgent: Volatile Reaction (Driving, Intense; Electronica; 120 bpm)"])
            reg = json.loads(Path(d, "tracks.json").read_text())
            self.assertEqual([t["file"] for t in reg["tracks"]], ["happy-bee.mp3", "volatile-reaction.mp3"])

    def test_the_reel_credits_a_library_track_with_its_own_credit(self):
        import video
        with tempfile.TemporaryDirectory() as d, mock.patch.object(video, "MUSIC", Path(d)):
            Path(d, "v.mp3").write_bytes(b"x")
            Path(d, "tracks.json").write_text(json.dumps({"tracks": [musiclib.entry("urgent", PIECES[0], "v.mp3", 0)]}))
            t = video.music_track({"id": "p", "template": "sauti"})
        self.assertEqual(t["credit"], 'Music: "Volatile Reaction" by Kevin MacLeod (incompetech.com), CC BY 4.0')


if __name__ == "__main__":
    unittest.main()
