"""Glue: Godot target -> camera frame -> calibrated screen image -> shadow -> scores -> Godot."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import cv2
import numpy as np

from .calibration import Calibration, find_corners_auto_color
from .frame_source import FrameSource
from .matcher import MatchTracker, compute_scores
from .protocol import make_ack, make_calibrate_ack, make_match, parse_set_target
from .segmenter import ShadowSegmenter
from .transport import UdpTransport

log = logging.getLogger(__name__)


@dataclass
class StepResult:
    result: dict                          # the match message that was sent
    screen: Optional[np.ndarray]          # calibrated camera image (None if not valid)
    shadow: Optional[np.ndarray]          # bool shadow mask (None if not valid)


class VisionPipeline:
    def __init__(self, source: FrameSource, calibration: Optional[Calibration],
                 segmenter: ShadowSegmenter, tracker: MatchTracker,
                 transport: UdpTransport, work_size: Tuple[int, int] = (640, 360),
                 target_fps: float = 30.0, calibration_path: Optional[str] = None):
        self.source = source
        self.calibration = calibration
        self.segmenter = segmenter
        self.tracker = tracker
        self.transport = transport
        self.work_size = (int(work_size[0]), int(work_size[1]))
        self.target_fps = target_fps
        self.target_id: Optional[int] = None
        self.target_mask: Optional[np.ndarray] = None     # bool (h, w) at work_size
        self.frame_id = 0
        self.calibration_path = calibration_path
        self._calibrate_until = 0.0     # nonzero while a calibrate request is pending
        self._calibrate_prev: Optional[np.ndarray] = None
        self._calibrate_hits = 0
        self._last_log = 0.0
        self._t0 = time.monotonic()

    def _handle_messages(self) -> None:
        for msg in self.transport.poll():
            kind = msg.get("type")
            if kind == "set_target":
                self._handle_set_target(msg)
            elif kind == "calibrate":
                # The projector needs a frame or two to switch to the colour screen.
                self._calibrate_until = time.monotonic() + 3.0
                self._calibrate_prev = None
                self._calibrate_hits = 0
                log.info("calibration requested")
            else:
                log.debug("ignoring message of type %r", kind)

    def _handle_set_target(self, msg: dict) -> None:
        try:
            target_id, mask = parse_set_target(msg)
        except ValueError as exc:
            log.warning("bad set_target: %s", exc)
            raw_id = msg.get("target_id")
            self.transport.send(make_ack(raw_id if isinstance(raw_id, int) else None,
                                         False, str(exc)))
            return
        w, h = self.work_size
        if mask.shape != (h, w):
            src_aspect = mask.shape[1] / mask.shape[0]
            if abs(src_aspect - w / h) > 0.01:
                log.warning("target mask aspect %.3f differs from work aspect %.3f; "
                            "it will be stretched", src_aspect, w / h)
            mask = cv2.resize(mask.astype(np.uint8), (w, h),
                              interpolation=cv2.INTER_NEAREST) > 0
        self.target_id = target_id
        self.target_mask = mask
        self.tracker.reset()
        self.transport.send(make_ack(target_id, True))
        log.info("target %d set (%d shape pixels)", target_id, int(mask.sum()))

    def _try_calibrate(self, frame: np.ndarray) -> None:
        """Calibrate from a camera frame showing the coloured screen, or give up.

        The corners have to stay put for a few frames before they are accepted, so a
        frame caught mid-transition (or a hand moving through the shot) does not get
        baked into the calibration.
        """
        h, w = frame.shape[:2]
        corners = find_corners_auto_color(frame)
        if corners is None:
            self._calibrate_prev = None
            self._calibrate_hits = 0
            if time.monotonic() > self._calibrate_until:
                self._calibrate_until = 0.0
                log.warning("calibration failed: no coloured screen in view")
                self.transport.send(make_calibrate_ack(False, "no coloured screen in view"))
            return
        if self._calibrate_prev is not None and \
                np.abs(corners - self._calibrate_prev).max() < 8.0:
            self._calibrate_hits += 1
        else:
            self._calibrate_hits = 1
        self._calibrate_prev = corners
        if self._calibrate_hits < 3:
            return
        self._calibrate_until = 0.0
        self.calibration = Calibration(corners=corners, camera_size=(w, h))
        if self.calibration_path:
            self.calibration.save(self.calibration_path)
        self.tracker.reset()
        self.transport.send(make_calibrate_ack(True))
        log.info("calibrated from the colour screen (%dx%d)", w, h)

    def step(self) -> Optional[StepResult]:
        """Process one camera frame. Returns None if the camera gave no frame."""
        self._handle_messages()
        frame = self.source.read()
        if frame is None:
            if self._calibrate_until and time.monotonic() > self._calibrate_until:
                self._calibrate_until = 0.0
                self.transport.send(make_calibrate_ack(False, "no camera frame"))
            return None

        if self._calibrate_until:
            self._try_calibrate(frame)
            if self._calibrate_until:
                return None     # still looking for the colour screen
        self.frame_id += 1
        t = time.monotonic() - self._t0

        valid = (self.calibration is not None and self.calibration.matches_frame(frame)
                 and self.target_mask is not None)
        if not valid:
            if self.calibration is not None and not self.calibration.matches_frame(frame):
                log.warning("camera resolution changed since calibration; recalibrate")
            result = make_match(self.target_id, self.frame_id, t, 0.0, 0.0, 0.0, 0.0,
                                False, False)
            self.transport.send(result)
            return StepResult(result, None, None)

        screen = self.calibration.warp(frame, self.work_size)
        shadow = self.segmenter.segment(screen)
        scores = compute_scores(shadow, self.target_mask)
        now = time.monotonic()
        if now - self._last_log > 2.0:
            self._last_log = now
            log.info("shadow %.1f%%  iou %.2f  coverage %.2f  overflow %.2f",
                     100.0 * shadow.mean(), scores.iou, scores.coverage, scores.overflow)
        iou_smoothed, matched = self.tracker.update(scores.iou)
        result = make_match(self.target_id, self.frame_id, t, iou_smoothed, scores.iou,
                            scores.coverage, scores.overflow, matched, True, shadow)
        self.transport.send(result)
        return StepResult(result, screen, shadow)

    def run(self, on_step: Optional[Callable[[Optional[StepResult]], Optional[bool]]] = None,
            max_frames: Optional[int] = None) -> None:
        """Loop until max_frames iterations, or until on_step returns False."""
        period = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
        count = 0
        while max_frames is None or count < max_frames:
            started = time.monotonic()
            out = self.step()
            count += 1
            if on_step is not None and on_step(out) is False:
                break
            if out is None:
                time.sleep(0.01)      # no frame; avoid a busy loop
            elapsed = time.monotonic() - started
            if elapsed < period:
                time.sleep(period - elapsed)


def render_debug(screen: Optional[np.ndarray], shadow: Optional[np.ndarray],
                 target: Optional[np.ndarray]) -> Optional[np.ndarray]:
    """Calibrated image dimmed, shadow tinted red, target outline in green."""
    if screen is None:
        return None
    vis = (screen.astype(np.float32) * 0.6).astype(np.uint8)
    if shadow is not None:
        vis[shadow] = (0.5 * vis[shadow] + 0.5 * np.array([0, 0, 255])).astype(np.uint8)
    if target is not None:
        contours, _ = cv2.findContours(target.astype(np.uint8), cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, contours, -1, (0, 255, 0), 2)
    return vis
