"""Wire protocol between the Godot game and the vision process.

Transport: UDP, one UTF-8 JSON object per datagram.

Godot -> vision
    set_target  {"type": "set_target", "target_id": int, "w": int, "h": int,
                 "mask_png_b64": str}
        The target shape in *projected screen coordinates*, as a PNG (base64).
        Grayscale or RGB(A); only the first channel is read. Convention, the same as
        the existing hole_mask textures in the Godot project:
            shape = dark (< 128), background = light.
        w/h must equal the decoded image size. Send once per round; resend until a
        target_ack arrives (UDP can drop packets).

vision -> Godot
    target_ack  {"type": "target_ack", "target_id": int|null, "ok": bool, "error": str}
    match       {"type": "match", "target_id": int|null, "frame_id": int, "t": float,
                 "iou": float, "iou_raw": float, "coverage": float, "overflow": float,
                 "matched": bool, "valid": bool}
        Sent once per camera frame.
        iou       smoothed intersection-over-union of shadow and target
        iou_raw   unsmoothed IoU of this frame
        coverage  fraction of the target covered by shadow
        overflow  fraction of the shadow lying outside the target
        matched   iou passed the enter threshold (with hysteresis); Godot owns the hold timer
        valid     False if there is no calibration or no target yet; ignore the scores then
        target_id lets Godot discard results that belong to the previous round.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

MAX_DATAGRAM = 60000      # stay below the 65507-byte UDP payload limit
SHAPE_THRESHOLD = 128     # pixel values below this count as "shape"


def encode_message(msg: Dict[str, Any]) -> bytes:
    data = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_DATAGRAM:
        raise ValueError("message too large for one UDP datagram (%d bytes)" % len(data))
    return data


def decode_message(data: bytes) -> Dict[str, Any]:
    msg = json.loads(data.decode("utf-8"))
    if not isinstance(msg, dict) or "type" not in msg:
        raise ValueError("message must be a JSON object with a 'type' field")
    return msg


def mask_to_png_b64(shape_mask: np.ndarray) -> str:
    """Bool mask (True = shape) -> base64 PNG using the Godot convention (shape dark)."""
    gray = np.where(np.asarray(shape_mask, dtype=bool), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", gray)
    if not ok:
        raise ValueError("PNG encoding failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def png_b64_to_mask(b64: str) -> np.ndarray:
    """Base64 PNG -> bool mask (True = shape)."""
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception as exc:
        raise ValueError("mask_png_b64 is not valid base64") from exc
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("mask_png_b64 is not a decodable PNG")
    if img.ndim == 3:
        img = img[:, :, 0]
    if img.dtype == np.uint16:
        img = (img >> 8).astype(np.uint8)
    return img < SHAPE_THRESHOLD


def make_set_target(target_id: int, shape_mask: np.ndarray) -> Dict[str, Any]:
    h, w = shape_mask.shape[:2]
    return {
        "type": "set_target",
        "target_id": int(target_id),
        "w": int(w),
        "h": int(h),
        "mask_png_b64": mask_to_png_b64(shape_mask),
    }


def parse_set_target(msg: Dict[str, Any]) -> Tuple[int, np.ndarray]:
    """Validate a set_target message and return (target_id, bool shape mask)."""
    if msg.get("type") != "set_target":
        raise ValueError("not a set_target message")
    try:
        target_id = int(msg["target_id"])
        w = int(msg["w"])
        h = int(msg["h"])
        b64 = msg["mask_png_b64"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("set_target has a missing or malformed field: %r" % (exc,)) from exc
    mask = png_b64_to_mask(b64)
    if mask.shape != (h, w):
        raise ValueError("decoded mask is %dx%d but the message says %dx%d"
                         % (mask.shape[1], mask.shape[0], w, h))
    return target_id, mask


def make_ack(target_id: Optional[int], ok: bool, error: str = "") -> Dict[str, Any]:
    return {"type": "target_ack", "target_id": target_id, "ok": bool(ok), "error": error}


def make_match(target_id: Optional[int], frame_id: int, t: float, iou: float, iou_raw: float,
               coverage: float, overflow: float, matched: bool, valid: bool) -> Dict[str, Any]:
    return {
        "type": "match",
        "target_id": target_id,
        "frame_id": int(frame_id),
        "t": round(float(t), 3),
        "iou": round(float(iou), 4),
        "iou_raw": round(float(iou_raw), 4),
        "coverage": round(float(coverage), 4),
        "overflow": round(float(overflow), 4),
        "matched": bool(matched),
        "valid": bool(valid),
    }
