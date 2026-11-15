"""Camera -> projected-screen calibration.

Goal: map camera pixels onto projected-screen coordinates (the coordinate frame of the
target masks Godot sends). The wall is flat and the shadow lies on it, so a homography
(perspective transform) from the four corners of the projected area is enough. It covers
offset, scale and perspective in one step.

Where the four corners come from:
  * auto:   project a plain white full-screen image; the projected area is the largest
            bright quadrilateral in the camera image.
  * manual: click the four corners in the live camera image (with a magnifier).
`calibrate()` tries auto first, lets the user confirm the result, and falls back to manual.

The interactive parts (confirm_corners, find_corners_manual) open OpenCV windows and have
not been run yet. The auto detection and the homography are covered by synthetic tests.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from .frame_source import FrameSource

log = logging.getLogger(__name__)

CORNER_NAMES = ("top-left", "top-right", "bottom-right", "bottom-left")


def order_corners(points) -> np.ndarray:
    """Return the 4 points ordered top-left, top-right, bottom-right, bottom-left.

    Works for any input order as long as the quad is not rotated by more than ~45 degrees.
    """
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)                 # x + y
    d = np.diff(pts, axis=1).ravel()    # y - x
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


@dataclass
class Calibration:
    corners: np.ndarray                 # (4, 2) TL, TR, BR, BL in camera pixels
    camera_size: Tuple[int, int]        # (w, h) of the frames used for calibration
    _cache: Dict[Tuple[int, int], np.ndarray] = field(default_factory=dict, init=False,
                                                      repr=False, compare=False)

    def homography(self, out_size: Tuple[int, int]) -> np.ndarray:
        key = (int(out_size[0]), int(out_size[1]))
        if key not in self._cache:
            w, h = key
            dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
            self._cache[key] = cv2.getPerspectiveTransform(self.corners.astype(np.float32), dst)
        return self._cache[key]

    def warp(self, frame: np.ndarray, out_size: Tuple[int, int]) -> np.ndarray:
        """Camera frame -> image in projected-screen coordinates of size out_size (w, h)."""
        return cv2.warpPerspective(frame, self.homography(out_size),
                                   (int(out_size[0]), int(out_size[1])))

    def matches_frame(self, frame: np.ndarray) -> bool:
        """False if the camera resolution changed since calibrating (corners would be wrong)."""
        return (frame.shape[1], frame.shape[0]) == tuple(self.camera_size)

    def save(self, path: str) -> None:
        data = {
            "corners": np.asarray(self.corners, dtype=float).tolist(),
            "camera_size": list(self.camera_size),
            "corner_order": list(CORNER_NAMES),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Calibration":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        corners = np.array(data["corners"], dtype=np.float32).reshape(4, 2)
        w, h = data["camera_size"]
        return cls(corners=corners, camera_size=(int(w), int(h)))


def _quad_from_binary(binary: np.ndarray, what: str, min_area_ratio: float = 0.05,
                      border_margin: int = 2) -> Optional[np.ndarray]:
    """Largest quadrilateral in a binary mask, as 4 corners, or None."""
    h, w = binary.shape
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        log.info("auto calibration: no %s found", what)
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < min_area_ratio * w * h:
        log.info("auto calibration: %s is too small", what)
        return None
    hull = cv2.convexHull(largest)
    perimeter = cv2.arcLength(hull, True)
    quad = None
    for eps in np.linspace(0.01, 0.10, 19):
        approx = cv2.approxPolyDP(hull, eps * perimeter, True)
        if len(approx) == 4:
            quad = approx.reshape(4, 2)
            break
        if len(approx) < 4:
            break
    if quad is None:
        log.info("auto calibration: %s is not a quadrilateral", what)
        return None
    near_border = ((quad[:, 0] < border_margin) | (quad[:, 0] > w - 1 - border_margin) |
                   (quad[:, 1] < border_margin) | (quad[:, 1] > h - 1 - border_margin))
    if near_border.any():
        log.info("auto calibration: %s touches the camera frame border", what)
        return None
    return order_corners(quad)


def find_corners_auto(frame: np.ndarray, min_area_ratio: float = 0.05,
                      border_margin: int = 2) -> Optional[np.ndarray]:
    """Find the projected area (a plain white screen) in a camera frame.

    Returns the 4 corners (TL, TR, BR, BL) or None. Fails if the bright area is too small,
    is not a quadrilateral, or touches the frame border (then part of the projection is
    probably outside the camera's view).
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    return _quad_from_binary(binary, "bright area", min_area_ratio, border_margin)


def find_corners_auto_color(frame: np.ndarray, hue_range: Tuple[int, int] = (35, 90),
                            min_saturation: int = 100, min_value: int = 100,
                            min_area_ratio: float = 0.05, min_fill: float = 0.85,
                            border_margin: int = 2) -> Optional[np.ndarray]:
    """Find the green calibration screen.

    A saturated screen is much easier to separate from a white wall lit by a lamp than a
    white one: the wall has low saturation whatever its brightness is. The hue gate keeps
    other coloured things in the room (clothes, the lamp) from being picked up, and the
    fill ratio rejects a screen that is partly hidden behind the player.
    """
    if frame.ndim != 3:
        raise ValueError("color calibration needs a BGR frame")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    mask = ((hue >= hue_range[0]) & (hue <= hue_range[1]) &
            (sat >= min_saturation) & (val >= min_value)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    corners = _quad_from_binary(mask, "green area", min_area_ratio, border_margin)
    if corners is None:
        return None
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    largest = max(contours, key=cv2.contourArea)
    quad_area = cv2.contourArea(corners.astype(np.float32))
    fill = cv2.contourArea(largest) / quad_area if quad_area > 0 else 0.0
    if fill < min_fill:
        log.info("auto calibration: green area only fills %.0f%% of its quad "
                 "(something is in the way?)", 100 * fill)
        return None
    return corners


def _draw_quad(img: np.ndarray, pts, color=(0, 255, 0)) -> None:
    pts = [tuple(int(round(v)) for v in p) for p in pts]
    for i, p in enumerate(pts):
        cv2.circle(img, p, 5, color, -1)
        cv2.putText(img, str(i + 1), (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, color, 2)
    if len(pts) >= 2:
        cv2.polylines(img, [np.array(pts, dtype=np.int32)], len(pts) == 4, color, 2)


def _draw_magnifier(img: np.ndarray, center, half: int = 15, zoom: int = 6) -> None:
    """Paste a zoomed crop around `center` into the top-right corner of img."""
    h, w = img.shape[:2]
    x, y = center
    x0, y0 = max(0, x - half), max(0, y - half)
    x1, y1 = min(w, x + half + 1), min(h, y + half + 1)
    patch = img[y0:y1, x0:x1]
    if patch.size == 0:
        return
    big = cv2.resize(patch, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    bh, bw = big.shape[:2]
    if bh > h or bw > w:
        return
    cx, cy = (x - x0) * zoom + zoom // 2, (y - y0) * zoom + zoom // 2
    cv2.line(big, (cx - 12, cy), (cx + 12, cy), (0, 255, 255), 1)
    cv2.line(big, (cx, cy - 12), (cx, cy + 12), (0, 255, 255), 1)
    cv2.rectangle(big, (0, 0), (bw - 1, bh - 1), (255, 255, 255), 1)
    img[0:bh, w - bw:w] = big


def confirm_corners(source: FrameSource, corners: np.ndarray,
                    window: str = "Calibration") -> bool:
    """Show the detected corners over the live image. Enter = accept, Esc/M = reject."""
    cv2.namedWindow(window)
    try:
        empty = 0
        while True:
            frame = source.read()
            if frame is None:
                empty += 1
                if empty > 100:
                    return False
                cv2.waitKey(10)
                continue
            vis = frame.copy()
            _draw_quad(vis, corners)
            cv2.putText(vis, "Enter = accept   Esc / M = click corners manually", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow(window, vis)
            key = cv2.waitKey(30) & 0xFF
            if key in (13, 10):
                return True
            if key in (27, ord("m"), ord("M")):
                return False
    finally:
        cv2.destroyWindow(window)


def find_corners_manual(source: FrameSource, window: str = "Calibration") -> Optional[np.ndarray]:
    """Let the user click the four corners of the projected area in the live image.

    Click order does not matter (the points are sorted afterwards), but the prompt asks
    for top-left, top-right, bottom-right, bottom-left. R = reset, Enter = accept
    (after 4 clicks), Esc = cancel.
    """
    clicked = []
    mouse = [0, 0]

    def on_mouse(event, x, y, flags, param):
        mouse[0], mouse[1] = x, y
        if event == cv2.EVENT_LBUTTONDOWN and len(clicked) < 4:
            clicked.append((x, y))

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)
    try:
        empty = 0
        while True:
            frame = source.read()
            if frame is None:
                empty += 1
                if empty > 100:
                    return None
                cv2.waitKey(10)
                continue
            vis = frame.copy()
            _draw_quad(vis, clicked)
            if len(clicked) < 4:
                text = "Click the %s corner of the projected area" % CORNER_NAMES[len(clicked)]
            else:
                text = "Enter = accept   R = reset   Esc = cancel"
            cv2.putText(vis, text, (10, vis.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 255), 2)
            _draw_magnifier(vis, (mouse[0], mouse[1]))
            cv2.imshow(window, vis)
            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                return None
            if key in (ord("r"), ord("R")):
                clicked.clear()
            if key in (13, 10) and len(clicked) == 4:
                return order_corners(clicked)
    finally:
        cv2.destroyWindow(window)


def calibrate(source: FrameSource, mode: str = "auto_then_manual", confirm: bool = True,
              warmup_frames: int = 15) -> Optional[Calibration]:
    """Run calibration and return a Calibration, or None if it was cancelled or failed.

    mode: "auto", "color", "manual" or "auto_then_manual".
    confirm: show the auto result and ask for confirmation (needs a display).
    The projector must show a plain white full-screen image ("auto") or a plain colored
    one ("color"; the game shows green when you press C).
    """
    if mode not in ("auto", "color", "manual", "auto_then_manual"):
        raise ValueError("unknown calibration mode %r" % mode)
    frame = None
    for _ in range(warmup_frames):      # let exposure settle
        latest = source.read()
        if latest is not None:
            frame = latest
    if frame is None:
        raise RuntimeError("the camera produced no frames")

    corners = None
    if mode == "color":
        corners = find_corners_auto_color(frame)
    elif mode in ("auto", "auto_then_manual"):
        corners = find_corners_auto(frame)
        if corners is not None and confirm and not confirm_corners(source, corners):
            corners = None
        if corners is None and mode == "auto":
            return None
    if corners is None:
        corners = find_corners_manual(source)
    if corners is None:
        return None
    return Calibration(corners=corners, camera_size=(frame.shape[1], frame.shape[0]))
