# vision: shadow detection for The Shadow

Python process that watches the wall with a webcam, finds the player's shadow, scores it
against the target shape Godot is showing, and sends the result back to Godot over UDP.

```
projector light + objects -> shadow on wall -> webcam
webcam frame -> [calibrate: camera -> projected screen] -> [segment: dark = shadow]
             -> shadow mask -> IoU vs. target mask (from Godot) -> match message -> Godot
```

Godot is not touched by this folder. `.gdignore` keeps Godot from scanning it.

## Setup

```
pip install -r vision/requirements.txt
```

Run everything from the repository root. If `python` is not on PATH, use a virtual
environment and call it explicitly:

```
python3 -m venv .venv
.venv/bin/pip install -r vision/requirements.txt
.venv/bin/python -m vision.main run --source webcam:0 --size 1280x720 --show
```

On macOS the program that runs vision needs camera permission (System Settings -> Privacy &
Security -> Camera); restart it after granting, or capture fails with "not authorized".

## Running it

Two terminals: Godot runs the game, this folder runs vision.

1. Start the game (F5). It should be fullscreen on the projector.
2. Start vision, with the same resolution that was calibrated:
   ```
   python -m vision.main run --source webcam:0 --size 1280x720 --show
   ```
   `--show` opens a debug window (calibrated image, shadow in red, target outline in green)
   with a threshold slider.
3. In the game press R (or ENTER) to start a round.

`--size` is not optional: the calibration corners are stored for one camera resolution, and
vision reports `valid: false` for every frame when the camera delivers another one.

Godot sends `set_target` only when a round starts, so a vision process started after the
game has no target until the next round (press R).

## Calibrating

Once per camera/projector position, and again whenever either moves or the resolution
changes.

1. With the game running, press **C**: the projector shows a plain green screen.
2. ```
   python -m vision.main calibrate --source webcam:0 --size 1280x720 --mode color --no-confirm
   ```
3. Press C again to hide the green screen.

The green screen is found by saturation, so a white wall lit by a lamp does not confuse it;
a white screen would, because the brightness difference between projection and wall is too
small. The result goes to `vision/calibration.json` (ignored by git).

Other calibration modes:

| `--mode` | What it does |
|---|---|
| `color` | Saturated (green) area; needs the game's C screen. Most robust. |
| `auto` | Brightest quad, for a plain white screen. Shows the result for confirmation. |
| `manual` | Click the four corners in a live window; R resets, Enter accepts, Esc cancels. |
| `auto_then_manual` | Default: try `auto`, fall back to `manual`. |

## Without camera or Godot

Two terminals:
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
same convention as the existing `hole_mask` textures. Godot sends it at 320x180; vision
resizes it to its working size (640x360).

Vision -> Godot:
```json
{"type": "target_ack", "target_id": 3, "ok": true, "error": ""}
{"type": "match", "target_id": 3, "frame_id": 812, "t": 27.1, "iou": 0.64, "iou_raw": 0.67,
 "coverage": 0.81, "overflow": 0.22, "matched": true, "valid": true,
 "shadow_png_b64": "<base64 PNG>"}
```
- `shadow_png_b64` is the shadow found in that frame (screen coordinates, downscaled to at
  most 320x180 and grown by `SHADOW_DILATE_PX`), as a PNG where the shadow is opaque and
  everything else transparent. The dilation moves the outline the particles gather on out
  of the dark edge and into the lit area; raise it if the ring still sits in the shadow.
  Sending it at working resolution made datagrams too large: a shadow is a jagged blob and
  compresses badly. Godot reads the alpha channel as a mask. Load it with
  `Image.load_png_from_buffer()` then `ImageTexture.create_from_image()`, or
  `ImageTexture.update()` while the size stays the same. Missing when `valid` is false.
- `match` is sent for every camera frame. Ignore results whose `target_id` is not the
  current round's, and ignore the scores when `valid` is false (no calibration or no target).
- `matched` has hysteresis (see `config.py`). The "hold for N seconds" timer stays in Godot
  (`MATCH_HOLD_DURATION` in `ParticleWall.gd`), driven by `matched` (SPACE still works as a
  manual override for testing without a camera).

## Layout

| File | Job |
|---|---|
| `frame_source.py` | webcam, video file, synthetic camera (for tests) |
| `calibration.py` | find the 4 corners (color / auto / manual), homography, save/load |
| `segmenter.py` | dark pixels = shadow, then morphology |
| `matcher.py` | IoU, coverage, overflow; EMA + hysteresis |
| `protocol.py`, `transport.py` | messages and UDP |
| `pipeline.py` | one `step()` per camera frame |
| `main.py` | CLI (`calibrate`, `run`) |
| `tools/mock_godot.py` | fake Godot for testing |

## Godot side

`VisionLink.gd` in the repository root is the other end. It is a child node of `main.tscn`:
it sends `set_target` at the start of every round and receives `match`, exposing `iou`,
`matched` and `shadow_texture` (the detected shadow as a texture).

`ParticleWall.gd` hands that texture to `ParticleField`, whose motion shader reads its alpha
and pulls particles onto the shadow's outline: the player's silhouette appears as a ring of
particles on the wall. Inside the shadow the pull points outward, outside it points inward,
so particles gather on the contour instead of filling or avoiding it. `show_overlay` also
draws the raw mask over the screen; it is off by default.

The mask is sampled with wall UV, not screen UV. The wall fills almost the whole projected
image, so this is off by a couple of percent; it would need a proper mapping if the wall and
the projection ever differ more than that.

### Score API

Any other script can read the similarity score from the `VisionLink` node (child of the
scene root):

| Member | Type | Meaning |
|---|---|---|
| `iou` | `float` | smoothed similarity, 0..1 — **this is the score to show or use** |
| `matched` | `bool` | `iou` passed the enter threshold (with hysteresis); requires `valid` |
| `valid` | `bool` | false until calibration and a target exist; ignore the score then |
| `shadow_texture` | `Texture2D` | the detected shadow as a mask (alpha) |
| `score_received` | `signal(iou: float, matched: bool)` | emitted on every camera frame |

```gdscript
@onready var _link: VisionLink = $VisionLink

func _ready() -> void:
    _link.score_received.connect(func(iou, matched): print(iou, matched))
    # or poll _link.iou in _process
```

Raw values arrive in the `match` datagram: `iou` (smoothed), `iou_raw` (this frame),
`coverage` (how much of the target is covered), `overflow` (how much of the shadow lies
outside the target), `matched`, `valid`. Smoothing, thresholds and hysteresis live in
`matcher.py` and `config.py`.

`ParticleWall.gd` calls `set_target()` whenever a round starts, and press **C** to show the
green calibration screen.

## Tuning and known limitations

- The numbers in `config.py` were tuned on one setup and will not transfer. Measured there:
  shadow on the lit wall 113-122 gray, lit particle field 184-218 -> `threshold = 150`.
  Auto exposure and white balance shift this, and this camera cannot lock exposure from
  OpenCV (`CAP_PROP_EXPOSURE`, `CAP_PROP_GAIN` return -1), so re-check the threshold when the
  room light changes.
- Segmentation is an absolute dark threshold with no reference frame: anything dark in the
  projected picture itself counts as shadow. The projected image has to stay clearly
  brighter than the shadow everywhere the player can stand.
- For the same reason the target shape must be lighter than its surroundings. Drawn as a
  dark hole, a shadow falling into it is invisible.
- The interactive calibration windows (`confirm_corners`, `find_corners_manual`) have still
  never been run; calibration in practice uses `--mode color`.
- `border_margin` in `config.py` ignores a strip along the edge of the calibrated image.
  The calibration quad sits on the outermost pixels of the projection, so the warp pulls in
  a little of the dark wall around it, which would otherwise read as shadow. Raise it if a
  dark strip still shows up along the edges.
- No lens-distortion correction; check that the edges look straight after calibrating.
- Ports are placeholders.
