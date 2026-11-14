"""Webcam palm distance -> localhost UDP. Q exits; N/F calibrate near/far."""
import argparse
import json
import math
from pathlib import Path
import socket
import time
import urllib.request

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"


def palm_distance(hands, width, height):
    """Distance as fraction of image width; correct for image aspect ratio."""
    # Average the wrist (0) and four finger bases (5, 9, 13, 17)
    # to approximate each palm center in normalized image coordinates.
    centers = [(sum(h[i].x for i in (0, 5, 9, 13, 17)) / 5,
                sum(h[i].y for i in (0, 5, 9, 13, 17)) / 5) for h in hands]
    # Both palms must be visible before their separation is meaningful.
    if len(centers) != 2:
        return None, centers
    a, b = centers
    # x is measured in image widths, y in image heights. Convert y to
    # image-width units before calculating the Euclidean distance.
    return math.hypot(a[0] - b[0], (a[1] - b[1]) * height / width), centers


def proximity(distance, near, far):
    # Map near -> 1 and far -> 0. Keep values outside calibration in range.
    return max(0.0, min(1.0, (far - distance) / (far - near)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--port", type=int, default=4242)
    parser.add_argument("--near", type=float, default=0.12)
    parser.add_argument("--far", type=float, default=0.65)
    parser.add_argument("--simulate", action="store_true", help="Send fake data without camera/dependencies")
    args = parser.parse_args()
    # Ordered endpoints avoid division by zero and reversed interaction.
    if not 0 <= args.near < args.far:
        parser.error("Require 0 <= near < far")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(valid, distance=None, centers=None):
        # UDP sends one JSON message to Godot on the same computer.
        # Invalid measurements use null distance and a neutral target.
        payload = dict(version=1, valid=valid, hand_count=len(centers or []),
                       distance_norm=distance,
                       proximity=proximity(distance, args.near, args.far) if valid else 0.0,
                       centers=centers or [])
        sock.sendto(json.dumps(payload).encode(), ("127.0.0.1", args.port))

    # Simulation exercises the Godot connection without a camera or model.
    if args.simulate:
        print("Simulating -> UDP 127.0.0.1:%d. Ctrl+C to stop." % args.port)
        try:
            while True:
                d = args.near + (args.far - args.near) * (math.sin(time.monotonic()) + 1) / 2
                send(True, d, [(0.5 - d / 2, 0.5), (0.5 + d / 2, 0.5)])
                time.sleep(1 / 30)
        except KeyboardInterrupt:
            pass
        finally:
            send(False)
            sock.close()
        return

    import cv2
    import mediapipe as mp
    model = Path(__file__).with_name("hand_landmarker.task")
    # Download once, then reuse the local model on later runs.
    if not model.exists():
        print("Downloading official MediaPipe hand model...")
        temporary = model.with_suffix(".download")
        urllib.request.urlretrieve(MODEL_URL, temporary)
        temporary.replace(model)
    # VIDEO mode tracks hands across frames; at most two hands are detected.
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
        min_hand_detection_confidence=0.5, min_tracking_confidence=0.5)
    # OpenCV reads camera images; camera 0 is normally the default device.
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        cap.release()
        sock.close()
        raise RuntimeError("Cannot open camera. Close other camera apps or try --camera 1")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("Q: quit | N: set near distance | F: set far distance")
    last_timestamp = -1
    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
            while True:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera stopped delivering frames")
                # Mirror the preview so hand movements feel like a mirror.
                frame = cv2.flip(frame, 1)
                height, width = frame.shape[:2]
                # OpenCV supplies BGR pixels; MediaPipe expects RGB pixels.
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # VIDEO mode requires strictly increasing millisecond timestamps.
                timestamp = max(last_timestamp + 1, time.monotonic_ns() // 1_000_000)
                last_timestamp = timestamp
                # The model returns 21 landmarks for each detected hand.
                result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
                distance, centers = palm_distance(result.hand_landmarks, width, height)
                valid = distance is not None
                send(valid, distance, centers)
                # Convert normalized centers to pixels only for drawing.
                pixels = [(int(x * width), int(y * height)) for x, y in centers]
                for point in pixels:
                    cv2.circle(frame, point, 9, (0, 220, 255), -1)
                if valid:
                    cv2.line(frame, pixels[0], pixels[1], (0, 220, 255), 2)
                lines = [f"Hands: {len(centers)}/2  " + (f"distance: {distance:.3f}  proximity: {proximity(distance, args.near, args.far):.2f}" if valid else "tracking lost"),
                         f"Near: {args.near:.3f}  Far: {args.far:.3f} | N/F calibrate | Q quit"]
                for i, line in enumerate(lines):
                    cv2.putText(frame, line, (12, 28 + 28 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.imshow("Hand distance (2D, not centimeters)", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                # Calibration keeps a small gap between the two endpoints.
                # These values last for this run; printed values can be reused
                # with --near and --far on the next run.
                if valid and key == ord("n") and distance < args.far - 0.02:
                    args.near = distance
                    print(f"Near calibrated: {args.near:.4f}")
                if valid and key == ord("f") and distance > args.near + 0.02:
                    args.far = distance
                    print(f"Far calibrated: {args.far:.4f}")
    finally:
        # Tell Godot tracking ended and release the camera for other apps.
        send(False)
        cap.release()
        cv2.destroyAllWindows()
        sock.close()


if __name__ == "__main__":
    main()
