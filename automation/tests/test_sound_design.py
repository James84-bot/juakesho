"""Sound design: whooshes on the cuts, hits where figures land, never clipping (no network)."""
import os
import sys
import unittest
from pathlib import Path

import numpy as np

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import render  # noqa: E402
import sound  # noqa: E402
import video  # noqa: E402


class SoundDesign(unittest.TestCase):
    def test_marks_follow_the_lines_and_the_counted_figures(self):
        beats = ["Sugar output rose by *Sh32.*", "Factories milled *40%* more.", "Prices fell.", "Tell us."]
        cuts, lands = video.sound_marks(beats)
        starts = [0.0]
        for b in beats[:-1]:
            starts.append(starts[-1] + render.beat_seconds(b))
        self.assertEqual(cuts, [round(x, 3) for x in starts[1:]])     # one whoosh per cut, none before line 1
        self.assertEqual(len(lands), 1)                                  # line 1 never counts (it is the thumbnail)
        self.assertGreater(lands[0], cuts[0])

    def test_sfx_is_silent_between_marks_and_never_clips(self):
        fx = sound.sfx(8.0, [3.0], [5.0])
        self.assertEqual(len(fx), int(sound.SR * 8.0))
        self.assertLessEqual(float(np.abs(fx).max()), 0.6 + 1e-6)
        self.assertLess(float(np.abs(fx[: int(sound.SR * 2.5)]).max()), 1e-6)   # nothing before the first cut
        self.assertGreater(float(np.abs(fx[int(sound.SR * 2.9): int(sound.SR * 3.1)]).max()), 0.05)


if __name__ == "__main__":
    unittest.main()


class Counting(unittest.TestCase):
    def test_amounts_count_up_phone_lines_days_and_years_do_not(self):
        for w in ("Sh32.", "*Sh32*", "56.7%,", "Sh4bn", "557,930", "KSh1,200", "40%", "3.2m"):
            self.assertTrue(render.counts(w), w)
        for w in ("719", "18", "2026", "2kg", "six", "M-Pesa", "n3"):
            self.assertFalse(render.counts(w), w)
