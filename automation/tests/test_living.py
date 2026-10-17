"""The realistic presenter: how a portrait is brought to life (no network, no face model needed)."""
import os
import sys
import unittest
from pathlib import Path

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np  # noqa: E402

import living  # noqa: E402


class Mouth(unittest.TestCase):
    def test_mouth_opens_as_an_oval_not_a_box(self):
        self.assertAlmostEqual(living.profile(100, 100, 80), 1.0, places=3)
        self.assertLess(living.profile(140, 100, 80), 0.2)           # corners barely move
        self.assertGreater(living.profile(110, 100, 80), living.profile(130, 100, 80))

    def test_every_rhubarb_shape_has_a_pose(self):
        for s in "ABCDEFGHX":
            jaw, width, teeth = living.SHAPES[s]
            self.assertTrue(0 <= jaw <= 1 and 0.6 < width < 1.2 and 0 <= teeth <= 1)
        self.assertEqual(living.SHAPES["A"][0], 0.0)                 # M, B, P: lips together


class Performance(unittest.TestCase):
    CUES = [{"start": 0.0, "end": 0.2, "value": "X"}, {"start": 0.2, "end": 0.6, "value": "D"},
            {"start": 0.6, "end": 0.9, "value": "A"}, {"start": 0.9, "end": 8.0, "value": "C"}]

    def setUp(self):
        self.perf = living.performance(self.CUES, 8.0, seed=3)

    def test_one_pose_per_frame(self):
        self.assertEqual(len(self.perf), 8 * living.FPS)

    def test_jaw_moves_like_a_muscle_never_jumps(self):
        jaws = [p[0] for p in self.perf]
        self.assertLess(max(abs(a - b) for a, b in zip(jaws, jaws[1:])), 0.5)
        self.assertGreater(max(jaws[:20]), 0.5)                      # but it does open for the AA

    def test_blinks_and_a_living_head(self):
        self.assertTrue(any(p[3] >= 1.0 for p in self.perf))
        for _, _, _, _, (dx, dy, deg) in self.perf:
            self.assertLess(abs(dx), 5)
            self.assertLess(abs(dy), 5)
            self.assertLess(abs(deg), 2)


class Crop(unittest.TestCase):
    def test_head_and_shoulders_at_the_window_size(self):
        img = np.zeros((900, 700, 3), np.uint8)
        lm = np.zeros((478, 2), np.float32)
        lm[10], lm[152], lm[1] = (350, 200), (350, 420), (350, 320)
        face = living.Face(img=img, lm=lm)
        out = living.head_crop(img, face, (460, 560))
        self.assertEqual(out.shape[:2], (560, 460))
        # a face near the edge still gives a full window (edges are extended, never black)
        lm[1] = (40, 320)
        self.assertEqual(living.head_crop(img, face, (460, 560)).shape[:2], (560, 460))


if __name__ == "__main__":
    unittest.main()
