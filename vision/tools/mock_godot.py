"""Stand-in for the Godot side: sends a target mask, prints what vision answers.

    python -m vision.tools.mock_godot --shape circle
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

from ..main import parse_addr
from ..protocol import decode_message, encode_message, make_set_target
from ..shapes import SHAPE_NAMES, make_shape_mask


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape", choices=SHAPE_NAMES, default="circle")
    parser.add_argument("--target-id", type=int, default=1)
    parser.add_argument("--size", default="640x360", help="mask size WxH (screen coordinates)")
    parser.add_argument("--vision", type=parse_addr, default=("127.0.0.1", 9001),
                        help="where the vision process listens")
    parser.add_argument("--listen", type=parse_addr, default=("127.0.0.1", 9002),
                        help="where this mock listens for results")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="stop after this many seconds (0 = until Ctrl+C)")
    args = parser.parse_args(argv)

    w, h = (int(v) for v in args.size.lower().split("x"))
    packet = encode_message(make_set_target(args.target_id, make_shape_mask(args.shape, (w, h))))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(args.listen)
    sock.settimeout(0.1)

    acked = False
    last_send = 0.0
    last_print = 0.0
    start = time.monotonic()
    print("sending target %d (%s, %dx%d) to %s:%d" % (args.target_id, args.shape, w, h, *args.vision))
    try:
        while args.duration <= 0 or time.monotonic() - start < args.duration:
            now = time.monotonic()
            if not acked and now - last_send > 1.0:     # UDP may drop: resend until acked
                sock.sendto(packet, args.vision)
                last_send = now
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
            msg = decode_message(data)
            if msg["type"] == "target_ack":
                acked = msg["ok"]
                print("ack:", msg)
            elif msg["type"] == "match" and now - last_print > 0.5:
                last_print = now
                print("match target=%s iou=%.2f cov=%.2f over=%.2f matched=%s valid=%s"
                      % (msg["target_id"], msg["iou"], msg["coverage"], msg["overflow"],
                         msg["matched"], msg["valid"]))
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
