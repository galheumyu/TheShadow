"""Command line entry point.

Run from the repository root:
    python -m vision.main calibrate --source webcam:0
    python -m vision.main run --source webcam:0 --show

Demo without a camera or Godot (two terminals):
    python -m vision.main run --source synthetic --synthetic-shadow circle --show
    python -m vision.tools.mock_godot --shape circle
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional, Tuple

import cv2

from .calibration import Calibration, calibrate
from .config import Config
from .frame_source import FrameSource, SyntheticSource, VideoFileSource, WebcamSource
from .matcher import MatchTracker
from .pipeline import VisionPipeline, render_debug
from .segmenter import ShadowSegmenter
from .shapes import SHAPE_NAMES, make_shape_mask, shift_mask
from .transport import UdpTransport

log = logging.getLogger("vision")


def parse_addr(text: str) -> Tuple[str, int]:
    host, _, port = text.rpartition(":")
    if not host or not port.isdigit():
        raise argparse.ArgumentTypeError("expected HOST:PORT, got %r" % text)
    return host, int(port)


def parse_size(text: str) -> Tuple[int, int]:
    w, _, h = text.lower().partition("x")
    if not w.isdigit() or not h.isdigit():
        raise argparse.ArgumentTypeError("expected WxH, got %r" % text)
    return int(w), int(h)


def build_source(spec: str, cfg: Config, shadow: str = "none", shift: float = 0.0,
                 size: Optional[Tuple[int, int]] = None) -> FrameSource:
    if spec == "synthetic":
        src = SyntheticSource(screen_size=cfg.work_size)
        if shadow != "none":
            mask = make_shape_mask(shadow, cfg.work_size)
            src.set_shadow(shift_mask(mask, shift, 0.0))
        return src
    if spec == "webcam" or spec.startswith("webcam:"):
        index = int(spec.split(":", 1)[1]) if ":" in spec else 0
        return WebcamSource(index, size)
    if spec.startswith("video:"):
        return VideoFileSource(spec[len("video:"):])
    raise SystemExit("unknown --source %r (use webcam[:N], video:PATH or synthetic)" % spec)


def cmd_calibrate(args: argparse.Namespace) -> int:
    cfg = Config()
    source = build_source(args.source, cfg, size=args.size)
    try:
        calib = calibrate(source, mode=args.mode, confirm=not args.no_confirm)
    finally:
        source.close()
    if calib is None:
        print("Calibration failed or was cancelled.")
        return 1
    calib.save(args.out)
    print("Saved calibration to %s" % args.out)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = Config()
    if args.listen:
        cfg.listen_addr = args.listen
    if args.godot:
        cfg.godot_addr = args.godot
    if args.threshold is not None:
        cfg.threshold = args.threshold

    source = build_source(args.source, cfg, args.synthetic_shadow, args.synthetic_shift,
                          args.size)
    calib: Optional[Calibration] = None
    if args.source == "synthetic" and not os.path.exists(args.calibration):
        # Demo convenience: calibrate against the synthetic white screen automatically.
        shadow_free = SyntheticSource(screen_size=cfg.work_size)
        calib = calibrate(shadow_free, mode="auto", confirm=False)
        log.info("synthetic source: auto-calibrated")
    elif os.path.exists(args.calibration):
        calib = Calibration.load(args.calibration)
    else:
        log.warning("no calibration file at %s; results will be invalid. "
                    "Run 'calibrate' first.", args.calibration)

    segmenter = ShadowSegmenter(cfg.threshold, cfg.blur_ksize, cfg.open_ksize, cfg.close_ksize)
    tracker = MatchTracker(cfg.match_enter, cfg.match_exit, cfg.iou_smoothing)
    transport = UdpTransport(cfg.listen_addr, cfg.godot_addr)
    pipeline = VisionPipeline(source, calib, segmenter, tracker, transport,
                              cfg.work_size, cfg.target_fps)
    log.info("listening on %s:%d, sending to %s:%d", cfg.listen_addr[0],
             transport.listen_port, cfg.godot_addr[0], cfg.godot_addr[1])

    on_step = None
    if args.show:
        window = "vision debug (q = quit)"
        cv2.namedWindow(window)
        cv2.createTrackbar("threshold", window, segmenter.threshold, 255,
                           lambda v: setattr(segmenter, "threshold", v))

        def on_step(out):
            if out is not None and out.screen is not None:
                vis = render_debug(out.screen, out.shadow, pipeline.target_mask)
                text = "iou %.2f%s" % (out.result["iou"], "  MATCHED" if out.result["matched"] else "")
                cv2.putText(vis, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                            (0, 255, 255), 2)
                cv2.imshow(window, vis)
            return cv2.waitKey(1) & 0xFF != ord("q")

    try:
        pipeline.run(on_step=on_step)
    except KeyboardInterrupt:
        pass
    finally:
        source.close()
        transport.close()
        if args.show:
            cv2.destroyAllWindows()
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = Config()
    parser = argparse.ArgumentParser(prog="python -m vision.main", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_cal = sub.add_parser("calibrate", help="calibrate camera -> projected screen")
    p_cal.add_argument("--source", default="webcam:0", help="webcam[:N], video:PATH or synthetic")
    p_cal.add_argument("--mode", choices=("auto", "color", "manual", "auto_then_manual"),
                       default="auto_then_manual",
                       help="color = the game shows a plain green screen (press C in game)")
    p_cal.add_argument("--size", type=parse_size, help="camera capture WxH, e.g. 1280x720")
    p_cal.add_argument("--out", default=cfg.calibration_path)
    p_cal.add_argument("--no-confirm", action="store_true",
                       help="accept the auto result without showing a window")
    p_cal.set_defaults(func=cmd_calibrate)

    p_run = sub.add_parser("run", help="detect shadows and talk to Godot")
    p_run.add_argument("--source", default="webcam:0", help="webcam[:N], video:PATH or synthetic")
    p_run.add_argument("--calibration", default=cfg.calibration_path)
    p_run.add_argument("--show", action="store_true", help="debug window with threshold slider")
    p_run.add_argument("--listen", type=parse_addr, help="HOST:PORT to receive from Godot")
    p_run.add_argument("--godot", type=parse_addr, help="HOST:PORT to send results to")
    p_run.add_argument("--threshold", type=int, help="shadow gray-level threshold")
    p_run.add_argument("--size", type=parse_size,
                       help="camera capture WxH; must match the resolution used to calibrate")
    p_run.add_argument("--synthetic-shadow", choices=("none",) + SHAPE_NAMES, default="none",
                       help="(synthetic source) shape the fake shadow has")
    p_run.add_argument("--synthetic-shift", type=float, default=0.0,
                       help="(synthetic source) shift the fake shadow right by this many pixels")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
