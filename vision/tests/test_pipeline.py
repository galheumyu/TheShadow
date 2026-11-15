import base64
import socket
import time
import unittest

import cv2
import numpy as np

from vision.calibration import Calibration, find_corners_auto
from vision.frame_source import SyntheticSource
from vision.matcher import MatchTracker
from vision.pipeline import VisionPipeline
from vision.protocol import decode_message, encode_message, make_set_target
from vision.segmenter import ShadowSegmenter
from vision.shapes import make_shape_mask, shift_mask
from vision.transport import UdpTransport

WORK = (640, 360)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.godot = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.godot.bind(("127.0.0.1", 0))
        self.godot.settimeout(1.0)
        self.transport = UdpTransport(("127.0.0.1", 0), self.godot.getsockname())
        self.source = SyntheticSource(screen_size=WORK)
        corners = find_corners_auto(self.source.read())
        self.calib = Calibration(corners=corners, camera_size=(960, 540))

    def tearDown(self):
        self.godot.close()
        self.transport.close()

    def make_pipeline(self, calibration="default"):
        calib = self.calib if calibration == "default" else calibration
        return VisionPipeline(self.source, calib, ShadowSegmenter(),
                              MatchTracker(smoothing=1.0), self.transport, WORK)

    def send_target(self, target_id, shape_name):
        packet = encode_message(make_set_target(target_id, make_shape_mask(shape_name, WORK)))
        self.godot.sendto(packet, ("127.0.0.1", self.transport.listen_port))

    def step_until_target(self, pipeline):
        for _ in range(100):
            out = pipeline.step()
            if pipeline.target_id is not None:
                return out
            time.sleep(0.01)
        self.fail("set_target never arrived")

    def drain(self):
        messages = []
        self.godot.settimeout(0.2)
        try:
            while True:
                data, _ = self.godot.recvfrom(65535)
                messages.append(decode_message(data))
        except socket.timeout:
            pass
        return messages

    def test_perfect_shadow_matches(self):
        self.source.set_shadow(make_shape_mask("circle", WORK))
        pipeline = self.make_pipeline()
        self.send_target(1, "circle")
        out = self.step_until_target(pipeline)
        self.assertTrue(out.result["valid"])
        self.assertEqual(out.result["target_id"], 1)
        self.assertGreater(out.result["iou"], 0.9)
        self.assertTrue(out.result["matched"])

    def test_match_carries_the_shadow_shape(self):
        shadow = make_shape_mask("circle", WORK)
        self.source.set_shadow(shadow)
        pipeline = self.make_pipeline()
        self.send_target(1, "circle")
        out = self.step_until_target(pipeline)
        raw = base64.b64decode(out.result["shadow_png_b64"])
        img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        expected = cv2.resize(out.shadow.astype(np.uint8) * 255, (320, 180),
                              interpolation=cv2.INTER_NEAREST) > 0
        self.assertTrue(np.array_equal(img[:, :, 3] > 0, expected))
        self.assertGreater(np.count_nonzero(out.shadow & shadow) / np.count_nonzero(shadow), 0.9)

    def test_no_shadow_png_when_invalid(self):
        self.source.set_shadow(make_shape_mask("circle", WORK))
        pipeline = self.make_pipeline(calibration=None)
        self.send_target(1, "circle")
        out = self.step_until_target(pipeline)
        self.assertFalse(out.result["valid"])
        self.assertNotIn("shadow_png_b64", out.result)

    def test_shifted_shadow_does_not_match(self):
        self.source.set_shadow(shift_mask(make_shape_mask("circle", WORK), 150, 0))
        pipeline = self.make_pipeline()
        self.send_target(1, "circle")
        out = self.step_until_target(pipeline)
        self.assertLess(out.result["iou"], 0.5)
        self.assertFalse(out.result["matched"])

    def test_wrong_shape_does_not_match(self):
        self.source.set_shadow(make_shape_mask("square", WORK))
        pipeline = self.make_pipeline()
        self.send_target(1, "triangle")
        out = self.step_until_target(pipeline)
        self.assertFalse(out.result["matched"])

    def test_ack_comes_before_results(self):
        pipeline = self.make_pipeline()
        self.send_target(5, "circle")
        self.step_until_target(pipeline)
        pipeline.step()
        messages = self.drain()
        acks = [m for m in messages if m["type"] == "target_ack"]
        self.assertEqual(len(acks), 1)
        self.assertTrue(acks[0]["ok"])
        self.assertEqual(acks[0]["target_id"], 5)
        self.assertTrue(any(m["type"] == "match" for m in messages))

    def test_bad_target_is_nacked(self):
        pipeline = self.make_pipeline()
        msg = make_set_target(2, make_shape_mask("circle", WORK))
        msg["w"] = 5
        self.godot.sendto(encode_message(msg), ("127.0.0.1", self.transport.listen_port))
        for _ in range(50):
            pipeline.step()
            time.sleep(0.01)
            if any(m["type"] == "target_ack" for m in self.drain()):
                break
        self.assertIsNone(pipeline.target_id)

    def test_not_valid_without_target(self):
        out = self.make_pipeline().step()
        self.assertFalse(out.result["valid"])
        self.assertIsNone(out.result["target_id"])

    def test_not_valid_without_calibration(self):
        pipeline = self.make_pipeline(calibration=None)
        self.send_target(1, "circle")
        out = self.step_until_target(pipeline)
        self.assertFalse(out.result["valid"])

    def test_new_target_resets_tracking(self):
        self.source.set_shadow(make_shape_mask("circle", WORK))
        pipeline = self.make_pipeline()
        self.send_target(1, "circle")
        self.assertTrue(self.step_until_target(pipeline).result["matched"])
        self.send_target(2, "triangle")
        for _ in range(100):
            out = pipeline.step()
            if pipeline.target_id == 2:
                break
            time.sleep(0.01)
        self.assertEqual(out.result["target_id"], 2)
        self.assertFalse(out.result["matched"])


if __name__ == "__main__":
    unittest.main()
