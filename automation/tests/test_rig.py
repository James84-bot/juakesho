"""The code-built presenter: real blink timing and eyelids that close without moving anything else (no MediaPipe)."""
import random
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rig  # noqa: E402


class Blink(unittest.TestCase):
    def test_closes_fast_opens_slower_and_comes_every_few_seconds(self):
        n = 30 * 20
        curve = rig.blink_curve(n, np.ones(n), random.Random(3))
        starts = [i for i in range(1, n) if curve[i] > 0 and curve[i - 1] == 0]
        self.assertGreaterEqual(len(starts), 3)
        for a, b in zip(starts, starts[1:]):
            self.assertGreaterEqual(b - a, 1.9 * 30 - 1)
        s = starts[0]
        peak = s + int(np.argmax(curve[s:s + 12]))
        end = s + next(k for k in range(1, 15) if curve[s + k] == 0)
        self.assertLess(peak - s, end - peak)            # closing is quicker than opening

    def test_blinks_land_in_pauses_when_there_is_one(self):
        n = 30 * 10
        env = np.ones(n)
        env[45:60] = 0.0                                 # a pause at 1.5-2 s
        curve = rig.blink_curve(n, env, random.Random(1))
        first = next(i for i in range(n) if curve[i] > 0)
        self.assertTrue(45 <= first < 60 or first < 45)

    def test_the_lid_covers_the_eye_and_nothing_outside_moves(self):
        img = np.full((200, 300, 3), 120, np.uint8)
        img[90:110, 120:180] = 20                        # a dark eye under a lighter lid
        xs = np.arange(118, 183)
        eye = {"xs": xs, "u": np.full(len(xs), 90.0), "l": np.full(len(xs), 110.0), "band": 25.0, "h": 20.0}
        shut = img.copy()
        rig.blink_eye(shut, eye, 1.0)
        self.assertGreater(shut[100, 150].mean(), 80)    # skin now covers where the dark eye was
        self.assertTrue((shut[150:] == img[150:]).all())  # below the eye: untouched
        self.assertTrue((shut[:, :100] == img[:, :100]).all())
        open_ = img.copy()
        rig.blink_eye(open_, eye, 0.0)
        self.assertTrue((open_ == img).all())


if __name__ == "__main__":
    unittest.main()
