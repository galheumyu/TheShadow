"""Simple mock target shapes in projected-screen coordinates.

These are NOT the shapes Godot draws; they only exist so the vision side can be
tested and demoed without Godot.
"""
from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np

SHAPE_NAMES = ("circle", "triangle", "square")


def make_shape_mask(name: str, size: Tuple[int, int] = (640, 360)) -> np.ndarray:
    """Bool mask of shape (h, w), True inside the shape, centered on the screen."""
    w, h = size
    img = np.zeros((h, w), dtype=np.uint8)
    cx, cy = w // 2, h // 2
    r = int(0.28 * h)
    if name == "circle":
        cv2.circle(img, (cx, cy), r, 255, -1)
    elif name == "square":
        cv2.rectangle(img, (cx - r, cy - r), (cx + r, cy + r), 255, -1)
    elif name == "triangle":
        pts = np.array([(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r)], dtype=np.int32)
        cv2.fillPoly(img, [pts], 255)
    else:
        raise ValueError("unknown shape %r (expected one of %s)" % (name, ", ".join(SHAPE_NAMES)))
    return img > 0


def shift_mask(mask: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Translate a bool mask by (dx, dy) pixels; uncovered area becomes False."""
    h, w = mask.shape
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    out = cv2.warpAffine(mask.astype(np.uint8) * 255, m, (w, h), flags=cv2.INTER_NEAREST)
    return out > 0
