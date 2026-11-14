"""Where camera frames come from. All sources return BGR uint8 images (or None)."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)


class FrameSource(ABC):
    @abstractmethod
    def read(self) -> Optional[np.ndarray]:
        """Return the next BGR frame, or None if no frame is available."""

    def close(self) -> None:
        pass


class WebcamSource(FrameSource):
    def __init__(self, index: int = 0, size: Optional[Tuple[int, int]] = None,
                 exposure: Optional[float] = None):
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError("could not open camera %d" % index)
        if size is not None:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        if exposure is not None:
            # Whether and how this works depends on the camera driver; auto exposure
            # may also have to be switched off in the camera's own settings.
            if not self._cap.set(cv2.CAP_PROP_EXPOSURE, float(exposure)):
                log.warning("camera driver refused exposure=%s", exposure)

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        self._cap.release()


class VideoFileSource(FrameSource):
    """Replay a recorded video (useful for tests without a projector)."""

    def __init__(self, path: str, loop: bool = True):
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise RuntimeError("could not open video file %r" % path)
        self._loop = loop

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self._cap.read()
        if not ok and self._loop:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        self._cap.release()


class SyntheticSource(FrameSource):
    """Fake camera: a projected screen seen at an angle, with an optional shadow.

    The projected screen is lit (bright) with the shadow region dark, warped into the
    camera frame by a known perspective transform on a dim background. Used for tests
    and demos; `corners` is the ground truth for calibration.
    """

    DEFAULT_CORNERS = ((150, 90), (830, 70), (860, 470), (120, 450))   # TL, TR, BR, BL

    def __init__(self, camera_size: Tuple[int, int] = (960, 540),
                 screen_size: Tuple[int, int] = (640, 360), corners=None,
                 bg_level: int = 50, lit_level: int = 220, shadow_level: int = 10,
                 noise: float = 0.0, seed: int = 0):
        self.camera_size = (int(camera_size[0]), int(camera_size[1]))
        self.screen_size = (int(screen_size[0]), int(screen_size[1]))
        self.corners = np.array(corners if corners is not None else self.DEFAULT_CORNERS,
                                dtype=np.float32)
        self.bg_level = bg_level
        self.lit_level = lit_level
        self.shadow_level = shadow_level
        self.noise = noise
        self._rng = np.random.default_rng(seed)
        sw, sh = self.screen_size
        screen_pts = np.array([[0, 0], [sw - 1, 0], [sw - 1, sh - 1], [0, sh - 1]],
                              dtype=np.float32)
        self._h = cv2.getPerspectiveTransform(screen_pts, self.corners)   # screen -> camera
        self._shadow: Optional[np.ndarray] = None

    def set_shadow(self, shadow_mask: Optional[np.ndarray]) -> None:
        """Set the shadow as a bool mask in screen coordinates (h, w), or None."""
        if shadow_mask is not None:
            shadow_mask = np.asarray(shadow_mask, dtype=bool)
            sw, sh = self.screen_size
            if shadow_mask.shape != (sh, sw):
                raise ValueError("shadow mask must have shape %s, got %s"
                                 % ((sh, sw), shadow_mask.shape))
        self._shadow = shadow_mask

    def read(self) -> Optional[np.ndarray]:
        sw, sh = self.screen_size
        screen = np.full((sh, sw), self.lit_level, dtype=np.uint8)
        if self._shadow is not None:
            screen[self._shadow] = self.shadow_level
        cam = cv2.warpPerspective(screen, self._h, self.camera_size, flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=self.bg_level)
        if self.noise > 0:
            noisy = cam.astype(np.float32) + self._rng.normal(0.0, self.noise, cam.shape)
            cam = np.clip(noisy, 0, 255).astype(np.uint8)
        return cv2.cvtColor(cam, cv2.COLOR_GRAY2BGR)
