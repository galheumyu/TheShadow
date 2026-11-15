import unittest

import numpy as np

from vision.segmenter import ShadowSegmenter


class SegmenterTest(unittest.TestCase):
    def setUp(self):
        self.img = np.full((360, 640, 3), 200, dtype=np.uint8)

    def test_dark_blob_is_shadow(self):
        self.img[100:200, 100:300] = 5
        mask = ShadowSegmenter(threshold=60).segment(self.img)
        self.assertTrue(mask[150, 200])
        self.assertFalse(mask[300, 500])
        self.assertAlmostEqual(mask.sum() / (100 * 200), 1.0, delta=0.1)

    def test_bright_image_has_no_shadow(self):
        self.assertFalse(ShadowSegmenter().segment(self.img).any())

    def test_specks_are_removed(self):
        self.img[50:53, 50:53] = 0
        self.assertFalse(ShadowSegmenter(open_ksize=5).segment(self.img).any())

    def test_threshold_matters(self):
        self.img[100:200, 100:300] = 90       # dim region, not "pure black"
        self.assertFalse(ShadowSegmenter(threshold=60).segment(self.img).any())
        self.assertTrue(ShadowSegmenter(threshold=120).segment(self.img).any())

    def test_border_margin_clears_the_edges(self):
        dark = np.zeros((100, 100, 3), dtype=np.uint8)      # all "shadow"
        mask = ShadowSegmenter(threshold=60, border_margin=10).segment(dark)
        self.assertFalse(mask[:10, :].any())
        self.assertFalse(mask[:, :10].any())
        self.assertFalse(mask[:, -10:].any())
        self.assertTrue(mask[10:-10, 10:-10].all())

    def test_even_blur_kernel_rejected(self):
        with self.assertRaises(ValueError):
            ShadowSegmenter(blur_ksize=4)


if __name__ == "__main__":
    unittest.main()
