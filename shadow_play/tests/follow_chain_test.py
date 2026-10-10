#!/usr/bin/env python3
"""Exercise FOLLOW's Python adapter through the real C++ executable, without hardware."""

import importlib.util
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


RODS = ("wusong_neck", "wusong_left", "wusong_right", "tiger_head", "tiger_tail")
AXES = {rod + "_" + direction: rod for rod in RODS for direction in ("pan", "tilt")}
SESSION = "0123456789abcdef0123456789abcdef"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_output(text):
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    require(rows, "C++ emitted no grouped motor frames")
    previous_time = -1.0
    for index, row in enumerate(rows, 1):
        require(row["version"] == 1 and row["type"] == "motor_targets", "wrong output protocol")
        require(row["seq"] == index, "grouped output sequence was not consecutive")
        require(math.isfinite(row["time_s"]) and row["time_s"] >= previous_time, "invalid output time")
        previous_time = row["time_s"]
        require(len(row["axes"]) == 10, "a tick must contain all ten simulated axes")
        require({axis["axis_id"]: axis["rod"] for axis in row["axes"]} == AXES,
                "axis IDs or canonical five-rod association changed")
        for axis in row["axes"]:
            require(math.isfinite(axis["angle_deg"]), "non-finite motor target")
            if axis["rod"].startswith("tiger_"):
                require(abs(axis["angle_deg"] - 90.0) < 1e-9, "camera unexpectedly moved a tiger rod")
    return rows


def axis_at(row, name):
    return next(axis for axis in row["axes"] if axis["axis_id"] == name)


def frame_at(rows, when):
    row = min(rows, key=lambda candidate: abs(candidate["time_s"] - when))
    require(abs(row["time_s"] - when) < 1e-8, "missing offline control tick")
    return row


def poses(adapter):
    rest = adapter.demo_pose(0.0)
    # Wrists at their own shoulders make the baseline hand targets neutral.
    rest[5][:2] = rest[1][:2]
    rest[6][:2] = rest[2][:2]
    moved = [list(point) for point in rest]
    for shoulder in (1, 2):
        moved[shoulder][0] += 128.0
        moved[shoulder][1] -= 72.0
    moved[5][:2] = [moved[1][0] + 256.0, moved[1][1] - 72.0]
    moved[6][:2] = [moved[2][0] - 256.0, moved[2][1] + 72.0]
    require(all(rest[index] == moved[index] for index in (0, 7, 8)), "test must keep head and hips fixed")
    return rest, moved


def offline_chain(executable, source, directory, adapter):
    rest, moved = poses(adapter)
    schedule = [(0.0, rest)] + [(index / 10.0, moved) for index in range(1, 7)]
    schedule += [(seconds, None) for seconds in (0.62, 0.8, 1.0, 1.2)]
    records = [
        {"arrival_ms": seconds * 1000.0,
         "frame": adapter.build_frame(pose, index, 100.0 + seconds, 1, SESSION)}
        for index, (seconds, pose) in enumerate(schedule, 1)
    ]
    fixture = directory / "follow_input.jsonl"
    fixture.write_text("".join(json.dumps(record, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    recording = directory / "received.jsonl"
    command = [str(executable), "--mode", "camera", "--seconds", "1.5", "--motor-format", "jsonl"]
    result = subprocess.run(command + ["--replay", str(fixture), "--record-input", str(recording)],
                            cwd=str(source), capture_output=True, text=True, timeout=1.9)
    require(result.returncode == 0, "offline C++ failed: " + result.stderr)
    require("malformed=0" in result.stderr and "lifecycle_rejections=0" in result.stderr,
            "adapter frames were rejected: " + result.stderr)
    rows = parse_output(result.stdout)
    require(len(rows) == 76, "1.5 seconds at 50 Hz must emit exactly 76 complete ticks")
    require(all(row["mode"] == "camera" for row in rows), "unexpected mode change")
    require(all(abs(axis["angle_deg"] - 90.0) < 1e-9 for axis in frame_at(rows, 0.06)["axes"]),
            "resting shoulder midpoint did not produce neutral commands")

    moving = frame_at(rows, 0.6)
    # Pixel translation (+128, -72) means neck target (+0.2, +0.2).
    # With the actual simulation calibration the settled angles are (96, 94).
    require(95.8 < axis_at(moving, "wusong_neck_pan")["angle_deg"] <= 96.0 + 1e-9,
            "neck did not follow shoulders independently of the fixed head/hips")
    require(93.8 < axis_at(moving, "wusong_neck_tilt")["angle_deg"] <= 94.0 + 1e-9,
            "neck vertical pixel normalization or direction is wrong")
    require(axis_at(moving, "wusong_left_pan")["angle_deg"] > 112.0 and
            axis_at(moving, "wusong_right_pan")["angle_deg"] > 112.0,
            "wrist movements did not reach their calibrated hand axes")
    require(axis_at(moving, "wusong_left_tilt")["angle_deg"] > 97.0 and
            axis_at(moving, "wusong_right_tilt")["angle_deg"] < 83.0,
            "left/right wrist vertical direction changed")
    require(axis_at(frame_at(rows, 0.8), "wusong_neck_pan")["input_state"] == "tracking_or_holding",
            "brief loss did not preserve the configured hold interval")
    require(axis_at(frame_at(rows, 1.0), "wusong_neck_pan")["input_state"] == "returning_to_neutral",
            "loss heartbeats renewed old neck coordinates")
    require(all(abs(axis["angle_deg"] - 90.0) < 0.05 for axis in rows[-1]["axes"]),
            "expired inputs did not return all axes to neutral")

    received = read_jsonl(recording)
    require(len(received) == len(records), "input recording lost frames")
    for actual, expected in zip(received, records):
        expected_frame = dict(expected["frame"])
        expected_frame["points"] = {name: dict(point, valid=True)
                                    for name, point in expected_frame["points"].items()}
        require(actual["frame"] == expected_frame, "recording changed v2 metadata or point values")
        require(abs(actual["arrival_ms"] - expected["arrival_ms"]) < 1e-7,
                "recording changed tick-aligned arrival time")
    replayed = subprocess.run(command + ["--replay", str(recording)], cwd=str(source),
                              capture_output=True, text=True, timeout=1.9)
    require(replayed.returncode == 0, "recorded replay failed: " + replayed.stderr)
    require(parse_output(replayed.stdout) == rows, "record/replay changed final motor commands")
    print("PASS FOLLOW pixels -> C++ neck/hands -> grouped motors -> loss -> recorded replay")


def stop_child(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=0.5)


def live_chain(executable, source, directory, adapter):
    _, moved = poses(adapter)
    for attempt in range(3):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        output_path = directory / ("live_{}.jsonl".format(attempt))
        error_path = directory / ("live_{}.log".format(attempt))
        command = [str(executable), "--mode", "camera", "--seconds", "1", "--realtime",
                   "--listen", str(port), "--motor-format", "jsonl"]
        with output_path.open("w", encoding="utf-8") as output, error_path.open("w", encoding="utf-8") as errors:
            process = subprocess.Popen(command, cwd=str(source), stdout=output, stderr=errors)
            try:
                ready = False
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    log = error_path.read_text(encoding="utf-8")
                    if "Input UDP: 127.0.0.1:{}".format(port) in log:
                        ready = True
                        break
                    if process.poll() is not None:
                        # Retry only an ephemeral-port reservation/bind race.
                        if "bind" in log.lower() and attempt < 2:
                            break
                        raise AssertionError("live C++ exited before readiness: " + log)
                    time.sleep(0.01)
                if not ready and process.poll() is not None and "bind" in log.lower() and attempt < 2:
                    continue
                require(ready, "timed out waiting for input UDP readiness: " + log)
                with adapter.PoseSender(port) as sender:
                    for sequence in range(1, 9):
                        require(sender.publish(moved, sequence, time.monotonic(), 1),
                                "local UDP sender dropped a test frame")
                        time.sleep(0.02)
                    require(sender.stats["sent"] == 8, "PoseSender did not submit all frames")
                process.wait(timeout=1.5)
                require(process.returncode == 0, "live C++ failed: " + error_path.read_text(encoding="utf-8"))
            finally:
                stop_child(process)
        log = error_path.read_text(encoding="utf-8")
        require("malformed=0" in log and "lifecycle_rejections=0" in log,
                "live adapter messages rejected: " + log)
        rows = parse_output(output_path.read_text(encoding="utf-8"))
        require(any(axis_at(row, "wusong_neck_pan")["angle_deg"] > 90.5 for row in rows),
                "real UDP publish did not reach the neck motor output")
        require(any(axis_at(row, "wusong_left_pan")["angle_deg"] > 90.5 for row in rows),
                "real UDP publish did not reach a hand motor output")
        print("PASS PoseSender.publish -> loopback UDP -> C++ -> grouped motor targets")
        return
    raise AssertionError("could not bind a reserved loopback UDP port")


def main():
    require(len(sys.argv) == 3, "usage: follow_chain_test.py SHADOW_SHOW SOURCE_DIR")
    executable = Path(sys.argv[1]).resolve()
    source = Path(sys.argv[2]).resolve()
    spec = importlib.util.spec_from_file_location("follow_pose_sender", source / "integrations/follow/pose_sender.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    with tempfile.TemporaryDirectory(prefix="shadow_follow_chain_") as temporary:
        directory = Path(temporary)
        offline_chain(executable, source, directory, adapter)
        live_chain(executable, source, directory, adapter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
