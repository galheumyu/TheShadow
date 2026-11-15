import base64
import unittest

import cv2
import numpy as np

from vision.protocol import (MAX_DATAGRAM, decode_message, encode_message, make_set_target,
                             parse_set_target, shadow_to_png_b64)
from vision.shapes import SHAPE_NAMES, make_shape_mask


class ProtocolTest(unittest.TestCase):
    def test_set_target_round_trip(self):
        for name in SHAPE_NAMES:
            shape = make_shape_mask(name, (640, 360))
            data = encode_message(make_set_target(7, shape))
            target_id, mask = parse_set_target(decode_message(data))
            self.assertEqual(target_id, 7)
            self.assertTrue(np.array_equal(mask, shape), name)

    def test_full_hd_mask_fits_one_datagram(self):
        shape = make_shape_mask("triangle", (1280, 720))
        data = encode_message(make_set_target(1, shape))
        self.assertLess(len(data), MAX_DATAGRAM)

    def test_size_mismatch_is_rejected(self):
        msg = make_set_target(1, make_shape_mask("circle", (640, 360)))
        msg["w"] = 100
        with self.assertRaises(ValueError):
            parse_set_target(msg)

    def test_garbage_is_rejected(self):
        msg = make_set_target(1, make_shape_mask("circle", (64, 36)))
        msg["mask_png_b64"] = "AAAA"          # valid base64, not a PNG
        with self.assertRaises(ValueError):
            parse_set_target(msg)
        msg["mask_png_b64"] = "not base64!!"
        with self.assertRaises(ValueError):
            parse_set_target(msg)
        with self.assertRaises(ValueError):
            parse_set_target({"type": "set_target"})

    def test_shadow_png_round_trip(self):
        shadow = make_shape_mask("circle", (320, 180))
        raw = base64.b64decode(shadow_to_png_b64(shadow))
        img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertEqual(img.shape[:2], shadow.shape)
        self.assertTrue(np.array_equal(img[:, :, 3] > 0, shadow))

    def test_shadow_png_is_downscaled(self):
        raw = base64.b64decode(shadow_to_png_b64(make_shape_mask("circle", (640, 360))))
        img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertEqual(img.shape[:2], (180, 320))

    def test_shadow_png_fits_one_datagram(self):
        b64 = shadow_to_png_b64(make_shape_mask("triangle", (640, 360)))
        self.assertLess(len(b64), MAX_DATAGRAM)

    def test_decode_requires_type(self):
        with self.assertRaises(ValueError):
            decode_message(b'{"hello": 1}')


if __name__ == "__main__":
    unittest.main()
