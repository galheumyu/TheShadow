import unittest

import numpy as np

from vision.matcher import MatchTracker, compute_scores


def block(x0, x1, shape=(20, 40)):
    m = np.zeros(shape, dtype=bool)
    m[5:15, x0:x1] = True
    return m


class ScoresTest(unittest.TestCase):
    def test_identical(self):
        s = compute_scores(block(10, 20), block(10, 20))
        self.assertEqual((s.iou, s.coverage, s.overflow), (1.0, 1.0, 0.0))

    def test_disjoint(self):
        s = compute_scores(block(0, 10), block(20, 30))
        self.assertEqual((s.iou, s.coverage, s.overflow), (0.0, 0.0, 1.0))

    def test_half_overlap(self):
        # target columns 10-19, shadow columns 15-24: 50 shared px, 150 in the union
        s = compute_scores(block(15, 25), block(10, 20))
        self.assertAlmostEqual(s.iou, 1 / 3)
        self.assertAlmostEqual(s.coverage, 0.5)
        self.assertAlmostEqual(s.overflow, 0.5)

    def test_big_shadow_is_penalised(self):
        everything = np.ones((20, 40), dtype=bool)
        s = compute_scores(everything, block(10, 20))
        self.assertAlmostEqual(s.coverage, 1.0)
        self.assertLess(s.iou, 0.15)

    def test_empty_shadow(self):
        s = compute_scores(np.zeros((20, 40), dtype=bool), block(10, 20))
        self.assertEqual((s.iou, s.coverage, s.overflow), (0.0, 0.0, 0.0))

    def test_shape_mismatch(self):
        with self.assertRaises(ValueError):
            compute_scores(np.zeros((2, 2), dtype=bool), np.zeros((3, 3), dtype=bool))


class TrackerTest(unittest.TestCase):
    def test_hysteresis(self):
        t = MatchTracker(enter=0.6, exit=0.5, smoothing=1.0)
        seq = [0.4, 0.65, 0.55, 0.45, 0.55, 0.7]
        self.assertEqual([t.update(v)[1] for v in seq],
                         [False, True, True, False, False, True])

    def test_smoothing(self):
        t = MatchTracker(smoothing=0.5)
        self.assertAlmostEqual(t.update(1.0)[0], 1.0)
        self.assertAlmostEqual(t.update(0.0)[0], 0.5)

    def test_reset(self):
        t = MatchTracker(enter=0.6, exit=0.5, smoothing=1.0)
        t.update(0.9)
        t.reset()
        self.assertFalse(t.update(0.55)[1])

    def test_bad_parameters(self):
        with self.assertRaises(ValueError):
            MatchTracker(enter=0.4, exit=0.5)
        with self.assertRaises(ValueError):
            MatchTracker(smoothing=0.0)


if __name__ == "__main__":
    unittest.main()
