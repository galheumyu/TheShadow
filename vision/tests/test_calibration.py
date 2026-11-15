import itertools
import os
import tempfile
import unittest

import cv2
import numpy as np

from vision.calibration import (Calibration, find_corners_auto, find_corners_auto_color,
                                order_corners)
from vision.frame_source import SyntheticSource


class OrderCornersTest(unittest.TestCase):
    def test_any_input_order(self):
        tl, tr, br, bl = (10, 20), (200, 15), (210, 150), (5, 140)
        expected = np.array([tl, tr, br, bl], dtype=np.float32)
        for perm in itertools.permutations([tl, tr, br, bl]):
            np.testing.assert_allclose(order_corners(perm), expected)


class AutoCornersTest(unittest.TestCase):
    def test_finds_projection_quad(self):
        src = SyntheticSource()
        corners = find_corners_auto(src.read())
        self.assertIsNotNone(corners)
        self.assertLess(np.abs(corners - src.corners).max(), 4.0)

    def test_works_with_camera_noise(self):
        src = SyntheticSource(noise=8.0)
        corners = find_corners_auto(src.read())
        self.assertIsNotNone(corners)
        self.assertLess(np.abs(corners - src.corners).max(), 5.0)

    def test_finds_colored_screen(self):
        frame = np.full((360, 640, 3), 60, dtype=np.uint8)      # grey wall, no saturation
        quad = np.array([[80, 60], [560, 70], [540, 300], [60, 290]], dtype=np.int32)
        cv2.fillPoly(frame, [quad], (0, 255, 0))                # the game's green screen
        corners = find_corners_auto_color(frame)
        self.assertIsNotNone(corners)
        for got, want in zip(corners, order_corners(quad)):
            self.assertLess(np.linalg.norm(got - want), 3.0)

    def test_color_needs_a_colored_area(self):
        frame = np.full((360, 640, 3), 60, dtype=np.uint8)
        self.assertIsNone(find_corners_auto_color(frame))

    def test_rejects_uniform_frame(self):
        self.assertIsNone(find_corners_auto(np.full((540, 960, 3), 40, np.uint8)))

    def test_rejects_projection_touching_border(self):
        src = SyntheticSource(corners=((0, 0), (900, 40), (860, 470), (30, 500)))
        self.assertIsNone(find_corners_auto(src.read()))


class CalibrationTest(unittest.TestCase):
    def setUp(self):
        self.src = SyntheticSource()
        self.frame = self.src.read()
        self.calib = Calibration(corners=find_corners_auto(self.frame), camera_size=(960, 540))

    def test_warp_fills_the_output_with_the_projected_area(self):
        warped = self.calib.warp(self.frame, (640, 360))
        self.assertEqual(warped.shape, (360, 640, 3))
        self.assertGreater((warped[:, :, 0] > 128).mean(), 0.97)

    def test_shadow_lands_where_it_was_drawn(self):
        mask = np.zeros((360, 640), dtype=bool)
        mask[100:200, 400:500] = True
        self.src.set_shadow(mask)
        warped = self.calib.warp(self.src.read(), (640, 360))
        dark = warped[:, :, 0] < 100
        inter = (dark & mask).sum()
        self.assertGreater(inter / mask.sum(), 0.9)
        self.assertGreater(inter / dark.sum(), 0.9)

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "calibration.json")
            self.calib.save(path)
            loaded = Calibration.load(path)
        np.testing.assert_allclose(loaded.corners, self.calib.corners, atol=1e-4)
        self.assertEqual(tuple(loaded.camera_size), (960, 540))

    def test_detects_resolution_change(self):
        self.assertTrue(self.calib.matches_frame(self.frame))
        self.assertFalse(self.calib.matches_frame(np.zeros((480, 640, 3), np.uint8)))


if __name__ == "__main__":
    unittest.main()
