"""Shadow segmentation: dark pixels in the (already calibrated) screen image are shadow."""
from __future__ import annotations

import cv2
import numpy as np


def _odd(value: int, name: str) -> int:
    if value < 1 or value % 2 == 0:
        raise ValueError("%s must be a positive odd number, got %r" % (name, value))
    return value


class ShadowSegmenter:
    """Absolute dark threshold, then morphology to remove specks and fill small holes.

    No reference frame: anything darker than `threshold` is shadow. The threshold
    depends on the camera exposure and room light and has to be tuned on site.
    """

    def __init__(self, threshold: int = 60, blur_ksize: int = 5, open_ksize: int = 5,
                 close_ksize: int = 7, border_margin: int = 0):
        self.threshold = int(threshold)
        self.blur_ksize = _odd(blur_ksize, "blur_ksize")
        self.open_ksize = int(open_ksize)
        self.close_ksize = int(close_ksize)
        # The calibration quad sits on the outermost pixels of the projected area, so the
        # warp picks up a strip of the dark wall around it. Ignoring that margin keeps the
        # strip out of the shadow mask.
        self.border_margin = max(0, int(border_margin))

    def segment(self, screen_img: np.ndarray) -> np.ndarray:
        """Return a bool mask (h, w), True where there is shadow."""
        gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY) if screen_img.ndim == 3 else screen_img
        if self.blur_ksize > 1:
            gray = cv2.GaussianBlur(gray, (self.blur_ksize, self.blur_ksize), 0)
        mask = (gray < self.threshold).astype(np.uint8) * 255
        if self.open_ksize > 1:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.open_ksize, self.open_ksize))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
        if self.close_ksize > 1:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.close_ksize, self.close_ksize))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
        shadow = mask > 0
        m = self.border_margin
        if m > 0:
            shadow[:m, :] = False
            shadow[-m:, :] = False
            shadow[:, :m] = False
            shadow[:, -m:] = False
        return shadow
