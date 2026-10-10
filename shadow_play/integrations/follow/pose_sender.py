#!/usr/bin/env python3
"""Bridge FOLLOW's final nine-point pose to shadow_play's camera v2 UDP input.

This module needs only Python 3's standard library. Import it into board_follow.py;
do not feed it raw DPU tensors or unselected detections. It never writes hardware.
"""

import argparse
import errno
import json
import math
import numbers
import socket
import sys
import time
import uuid


KEYPOINT_NAMES = (
    "head", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
)
IMAGE_WIDTH = 1280.0
IMAGE_HEIGHT = 720.0
MIN_POINT_CONFIDENCE = 0.25
MAX_DATAGRAM_BYTES = 16 * 1024
UINT64_MAX = (1 << 64) - 1


def _uint64(value, name):
    # numbers.Integral also accepts NumPy integer scalars without importing NumPy.
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ValueError("{} must be an unsigned 64-bit integer".format(name))
    value = int(value)
    if not 0 <= value <= UINT64_MAX:
        raise ValueError("{} must be an unsigned 64-bit integer".format(name))
    return value


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    try:
        value = float(value)
    except (OverflowError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _session_id(value):
    if (not isinstance(value, str) or len(value) != 32 or
            any(character not in "0123456789abcdef" for character in value)):
        raise ValueError("session_id must be a 32-character lowercase UUID hex string")
    return value


def build_frame(pose, sequence, captured_s, track_id, session_id):
    """Return a JSON-ready camera v2 frame from FOLLOW's final pose or None.

    pose has exactly nine [pixel_x, pixel_y, confidence] rows. Coordinates already
    refer to the upright 1280x720 image. Invalid individual points are omitted;
    a malformed array or metadata raises ValueError instead of inventing data.
    Neck is derived from the two shoulders by C++; hips are never substituted.
    """
    sequence = _uint64(sequence, "sequence")
    track_id = _uint64(track_id, "track_id")
    captured_s = _finite_number(captured_s)
    if captured_s is None or captured_s < 0:
        raise ValueError("captured_s must be a finite nonnegative monotonic timestamp")
    session_id = _session_id(session_id)
    detected = pose is not None
    if detected and track_id == 0:
        raise ValueError("a detected pose requires a positive track_id")
    points = {}
    if detected:
        try:
            if len(pose) != len(KEYPOINT_NAMES):
                raise ValueError("pose must contain exactly nine [x, y, confidence] rows")
            for name, row in zip(KEYPOINT_NAMES, pose):
                if len(row) != 3:
                    raise ValueError("each pose row must contain exactly three values")
                x, y, confidence = (_finite_number(value) for value in row)
                if x is None or y is None or confidence is None:
                    continue
                if not (0.0 <= x <= IMAGE_WIDTH and 0.0 <= y <= IMAGE_HEIGHT):
                    continue
                if not MIN_POINT_CONFIDENCE <= confidence <= 1.0:
                    continue
                points[name] = {
                    "x": x / IMAGE_WIDTH,
                    "y": y / IMAGE_HEIGHT,
                    "confidence": confidence,
                }
        except TypeError as error:
            raise ValueError("pose must be an indexable nine-row numeric array") from error
    return {
        "version": 2,
        "source": "camera",
        "session_id": session_id,
        "seq": sequence,
        "track_id": track_id,
        "captured_s": captured_s,
        "detected": detected,
        "points": points,
    }


def encode_frame(frame):
    """Encode one complete UDP message, enforcing the receiver's size limit."""
    packet = json.dumps(frame, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(packet) > MAX_DATAGRAM_BYTES:
        raise ValueError("pose message exceeds the 16 KiB UDP limit")
    return packet


class PoseSender:
    """Send each current pose once, without a background queue or retry.

    Construct one instance before FOLLOW's loop and close it in finally. A new
    instance gets a new session ID; never recreate it for every frame. publish
    returns True when the OS accepted the datagram, not when C++ received it.
    The private _socket argument permits deterministic tests without hardware.
    """

    def __init__(self, port=56000, _socket=None):
        if isinstance(port, bool) or not isinstance(port, numbers.Integral) or not 1 <= port <= 65535:
            raise ValueError("port must be an integer in [1, 65535]")
        self.session_id = uuid.uuid4().hex
        self.destination = ("127.0.0.1", int(port))
        self._socket = _socket if _socket is not None else socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._socket.setblocking(False)
        except Exception:
            self._socket.close()
            raise
        self._closed = False
        self._last_sequence = None
        self._attempted = self._sent = self._dropped = 0
        self._invalid_frames = self._send_errors = 0

    @property
    def stats(self):
        return {
            "attempted": self._attempted,
            "sent": self._sent,
            "dropped": self._dropped,
            "invalid_frames": self._invalid_frames,
            "send_errors": self._send_errors,
        }

    def publish(self, pose, sequence, captured_s, track_id):
        if self._closed:
            raise RuntimeError("PoseSender is closed")
        try:
            frame = build_frame(pose, sequence, captured_s, track_id, self.session_id)
            if self._last_sequence is not None and frame["seq"] <= self._last_sequence:
                raise ValueError("sequence must strictly increase within this sender session")
            packet = encode_frame(frame)
        except (TypeError, ValueError) as error:
            self._invalid_frames += 1
            raise ValueError("invalid FOLLOW frame: {}".format(error)) from error
        self._last_sequence = frame["seq"]
        self._attempted += 1
        try:
            written = self._socket.sendto(packet, self.destination)
            if written != len(packet):
                raise OSError(errno.EIO, "incomplete UDP datagram send")
        except OSError as error:
            # Windows Winsock uses its own values for would-block/no-buffer.
            transient = {errno.EAGAIN, errno.EWOULDBLOCK, errno.ENOBUFS, 10035, 10055}
            if error.errno in transient or getattr(error, "winerror", None) in transient:
                self._dropped += 1
                return False
            self._send_errors += 1
            raise
        self._sent += 1
        return True

    def close(self):
        if not self._closed:
            self._closed = True
            self._socket.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def demo_pose(seconds):
    """Synthetic nine-point data only; useful for PC software integration."""
    wave = math.sin(seconds * 2.0)
    return [
        [640, 160, 0.95], [768, 288, 0.95], [512, 288, 0.95],
        [896, 324, 0.9], [384, 324, 0.9],
        [960, 260 + 80 * wave, 0.92], [320, 340 - 80 * wave, 0.92],
        [730, 490, 0.9], [550, 490, 0.9],
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate synthetic FOLLOW input for PC simulation only")
    parser.add_argument("--port", type=int, default=56000, help="loopback UDP destination port")
    parser.add_argument("--seconds", type=float, default=3.0, help="demo duration (0 < value <= 3600)")
    parser.add_argument("--jsonl", action="store_true", help="write replay records to stdout instead of sending UDP")
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 3600:
        parser.error("--seconds must be finite and in (0, 3600]")
    count = max(1, int(math.ceil(args.seconds * 30.0)))
    if args.jsonl:
        session_id = uuid.uuid4().hex
        for index in range(count):
            elapsed = index / 30.0
            frame = build_frame(demo_pose(elapsed), index + 1, elapsed, 1, session_id)
            print(json.dumps({"arrival_ms": elapsed * 1000.0, "frame": frame}, allow_nan=False, separators=(",", ":")))
    else:
        # Pacing exists only in this standalone demo, never in publish or FOLLOW.
        with PoseSender(args.port) as sender:
            started = time.monotonic()
            for index in range(count):
                due = started + index / 30.0
                remaining = due - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
                captured = time.monotonic()
                sender.publish(demo_pose(captured - started), index + 1, captured, 1)
            print(json.dumps(sender.stats), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
