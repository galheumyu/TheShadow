# vision: shadow detection for The Shadow

Python process that watches the wall with a webcam, finds the player's shadow, scores it
against the target shape Godot is showing, and sends the result back to Godot over UDP.

```
projector light + objects -> shadow on wall -> webcam
webcam frame -> [calibrate: camera -> projected screen] -> [segment: dark = shadow]
             -> shadow mask -> IoU vs. target mask (from Godot) -> match message -> Godot
```

Godot is not touched by this folder. `.gdignore` keeps Godot from scanning it.

## Setup (Windows)

```
pip install -r vision/requirements.txt
```

Run everything from the repository root.

## Usage

1. **Calibrate** once per camera/projector position. Show a plain white full-screen image
   on the projector, make sure the camera sees all four corners of it, then:
   ```
   python -m vision.main calibrate --source webcam:0
   ```
   It tries to find the white area automatically and shows it for confirmation
   (Enter = accept, Esc or M = click the corners yourself). In manual mode click the four
   corners; R resets, Enter accepts, Esc cancels. The result is saved to
   `vision/calibration.json` (ignored by git). Recalibrate if the camera or projector moves
   or the camera resolution changes.
2. **Run**:
   ```
   python -m vision.main run --source webcam:0 --show
   ```
   `--show` opens a debug window (calibrated image, shadow in red, target outline in green)
   with a threshold slider.

Without camera or Godot (two terminals):
```
python -m vision.main run --source synthetic --synthetic-shadow circle --show
python -m vision.tools.mock_godot --shape circle
```
`--synthetic-shift 150` moves the fake shadow 150 px to the side so the match drops.

Tests: `python -m unittest discover -s vision/tests -t .`

## Interface (UDP, one JSON object per datagram)

Defaults: vision listens on `127.0.0.1:9001`, results go to `127.0.0.1:9002` (`config.py`).
The full description is in the docstring of `protocol.py`.

Godot -> vision, once per round (resend until acked):
```json
{"type": "set_target", "target_id": 3, "w": 1280, "h": 720, "mask_png_b64": "<base64 PNG>"}
```
The mask is in **projected screen coordinates**, shape dark (< 128) on a light background,
same convention as the existing `hole_mask` textures. A 1280x720 simple shape is a few KB.
Vision resizes it to its working size (640x360); keep the aspect ratio of the screen.

Vision -> Godot:
```json
{"type": "target_ack", "target_id": 3, "ok": true, "error": ""}
{"type": "match", "target_id": 3, "frame_id": 812, "t": 27.1, "iou": 0.64, "iou_raw": 0.67,
 "coverage": 0.81, "overflow": 0.22, "matched": true, "valid": true}
```
- `match` is sent for every camera frame. Ignore results whose `target_id` is not the
  current round's, and ignore the scores when `valid` is false (no calibration or no target).
- `matched` has hysteresis (see `config.py`). The "hold for N seconds" timer stays in Godot
  (`MATCH_HOLD_DURATION` in `ParticleWall.gd`): replace the SPACE key with `matched`.
- In Godot, `PacketPeerUDP`, `JSON`, `Image.save_png_to_buffer()` and
  `Marshalls.raw_to_base64()` should cover the sending side. Not tried yet.

## Layout

| File | Job |
|---|---|
| `frame_source.py` | webcam, video file, synthetic camera (for tests) |
| `calibration.py` | find the 4 corners (auto / manual), homography, save/load |
| `segmenter.py` | dark pixels = shadow, then morphology |
| `matcher.py` | IoU, coverage, overflow; EMA + hysteresis |
| `protocol.py`, `transport.py` | messages and UDP |
| `pipeline.py` | one `step()` per camera frame |
| `main.py` | CLI (`calibrate`, `run`) |
| `tools/mock_godot.py` | fake Godot for testing |

## Not validated yet

- All numbers in `config.py` marked PLACEHOLDER: shadow threshold, IoU enter/exit, smoothing,
  ports. They need tuning with the real camera, projector and room.
- Real webcam capture, and the interactive calibration windows (`confirm_corners`,
  `find_corners_manual`): written but never run. Everything else is covered by tests that use
  a synthetic camera.
- Segmentation is an absolute dark threshold with no reference frame. Auto exposure and
  white balance of the camera will shift it; the camera setup may need exposure locked.
- If Godot's target shape is drawn darker than its surroundings, it will look like a shadow.
  Make the inside of the target lighter, as planned.
- No lens-distortion correction; check that the edges look straight after calibrating.
