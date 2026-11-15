"""Default settings. Every number marked PLACEHOLDER has not been tuned on real hardware."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

DEFAULT_CALIBRATION_PATH = str(Path(__file__).resolve().parent / "calibration.json")


@dataclass
class Config:
    # Working resolution = size of the projected-screen coordinate frame (same aspect as
    # the Godot window, 16:9). Incoming target masks are resized to this.
    work_size: Tuple[int, int] = (640, 360)

    # Shadow segmentation (PLACEHOLDER values).
    threshold: int = 150       # gray level below which a pixel counts as shadow
    blur_ksize: int = 5        # odd; 1 disables
    open_ksize: int = 5        # removes small specks
    close_ksize: int = 7       # fills small holes
    border_margin: int = 12    # pixels ignored along the edge of the calibrated image
                               # (the warp picks up a strip of wall outside the projection)

    # Match decision (PLACEHOLDER values).
    iou_smoothing: float = 0.5   # EMA alpha in (0, 1]; 1.0 = no smoothing
    match_enter: float = 0.6     # smoothed IoU needed to become "matched"
    match_exit: float = 0.5      # smoothed IoU below which "matched" drops again

    # UDP endpoints (PLACEHOLDER ports).
    listen_addr: Tuple[str, int] = ("127.0.0.1", 9001)   # vision listens here (Godot -> vision)
    godot_addr: Tuple[str, int] = ("127.0.0.1", 9002)    # vision sends results here

    calibration_path: str = DEFAULT_CALIBRATION_PATH
    target_fps: float = 30.0
