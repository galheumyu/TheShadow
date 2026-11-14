"""Scoring a shadow against the target shape, and deciding when it counts as matched."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass(frozen=True)
class Scores:
    iou: float        # |S & T| / |S | T|
    coverage: float   # |S & T| / |T|  : how much of the target is covered
    overflow: float   # |S - T| / |S|  : how much of the shadow lies outside the target


def compute_scores(shadow: np.ndarray, target: np.ndarray) -> Scores:
    shadow = np.asarray(shadow, dtype=bool)
    target = np.asarray(target, dtype=bool)
    if shadow.shape != target.shape:
        raise ValueError("shadow %s and target %s must have the same shape"
                         % (shadow.shape, target.shape))
    inter = int(np.count_nonzero(shadow & target))
    union = int(np.count_nonzero(shadow | target))
    s = int(np.count_nonzero(shadow))
    t = int(np.count_nonzero(target))
    return Scores(
        iou=inter / union if union else 0.0,
        coverage=inter / t if t else 0.0,
        overflow=(s - inter) / s if s else 0.0,
    )


class MatchTracker:
    """Smooths the IoU (EMA) and turns it into a matched flag with hysteresis.

    Hysteresis: become matched at >= enter, stay matched until < exit. This avoids
    flicker around a single threshold. The hold timer ("keep it for 2 s") lives in Godot.
    """

    def __init__(self, enter: float = 0.6, exit: float = 0.5, smoothing: float = 0.5):
        if exit > enter:
            raise ValueError("exit threshold must not exceed enter threshold")
        if not 0.0 < smoothing <= 1.0:
            raise ValueError("smoothing must be in (0, 1]")
        self.enter = enter
        self.exit = exit
        self.smoothing = smoothing
        self.reset()

    def reset(self) -> None:
        self._value = None
        self._matched = False

    def update(self, iou: float) -> Tuple[float, bool]:
        """Feed one raw IoU; return (smoothed iou, matched)."""
        if self._value is None:
            self._value = float(iou)
        else:
            self._value = self.smoothing * float(iou) + (1.0 - self.smoothing) * self._value
        if not self._matched and self._value >= self.enter:
            self._matched = True
        elif self._matched and self._value < self.exit:
            self._matched = False
        return self._value, self._matched
