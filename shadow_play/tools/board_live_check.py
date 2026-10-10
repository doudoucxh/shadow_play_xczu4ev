#!/usr/bin/env python3
"""Run real FOLLOW plus the CSV-only controller; retain reproducible evidence.

Run as root from the extracted board package after stopping the original FOLLOW
service. Video must already be initialized. This entry never changes boot files.
"""
import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from pc_check import csv_summary, require


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
            raise RuntimeError("Process required forced termination; reinitialize video before retrying")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    require(10 <= args.seconds <= 3600, "--seconds must be 10..3600")
    require(os.geteuid() == 0, "FOLLOW requires root for DPU/video access")
    root = Path(__file__).resolve().parent.parent
    output = root / "output" / ("board-live-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    output.mkdir(parents=True, exist_ok=False)
    (root / "output/latest-live.txt").write_text(str(output) + "\n")
    report = {"status": "running", "scope": "real camera/DPU, CSV motor backend, silent audio clock",
              "output": str(output), "requested_vision_seconds": args.seconds}
    controller = vision = None
    interrupted = False

    def interrupt(*_):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        with (output / "controller.log").open("w") as ctl_log, (output / "vision.log").open("w") as vision_log:
            controller = subprocess.Popen([
                str(root / "bin/shadow_show"), "--mode", "camera", "--seconds", str(args.seconds + 4),
                "--realtime", "--audio", "clock", "--listen", "56000", "--control-port", "56001",
                "--motor-format", "csv", "--output", str(output / "angles.csv"),
                "--record-input", str(output / "inputs.jsonl"),
                "--record-commands", str(output / "commands.csv")],
                cwd=str(root), stdout=ctl_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 5
            while "Control UDP: 127.0.0.1:56001" not in (output / "controller.log").read_text():
                require(controller.poll() is None, "Controller exited before readiness")
                require(time.monotonic() < deadline, "Controller UDP readiness timed out")
                time.sleep(.05)
            vision = subprocess.Popen([sys.executable, "-u", str(root / "follow/board_follow_with_sender.py")],
                                      cwd=str(root / "follow"), stdout=vision_log, stderr=subprocess.STDOUT,
                                      env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            report.update(controller_pid=controller.pid, vision_pid=vision.pid)
            (output / "running.json").write_text(json.dumps(report, indent=2) + "\n")
            print("LIVE_RESULT_DIR=" + str(output), flush=True)
            started = time.monotonic()
            while time.monotonic() - started < args.seconds and not interrupted:
                require(controller.poll() is None, "Controller exited during live capture")
                require(vision.poll() is None, "Vision exited during live capture; inspect vision.log")
                time.sleep(.1)
            stop(vision)
            report["vision_exit_code"] = vision.returncode
            require(vision.returncode == 0, "Vision cleanup failed")
            if interrupted:
                stop(controller)
            else:
                controller.wait(timeout=8)
            report["controller_exit_code"] = controller.returncode
            require(controller.returncode == 0, "Controller exited with an error")
        with (root / "config/calibration.simulation.csv").open() as handle:
            calibration = {r["axis_id"]: r for r in csv.DictReader(x for x in handle if not x.startswith("#"))}
        report["trace"] = csv_summary(output / "angles.csv", calibration)
        for axis, span in report["trace"]["angle_ranges_deg"].items():
            if axis.startswith("tiger_"):
                require(span == [90.0, 90.0], "Camera mode changed a tiger axis")
        count = detected = empty = 0
        sessions, tracks = set(), set()
        with (output / "inputs.jsonl").open() as handle:
            for line in handle:
                frame = json.loads(line)["frame"]
                count += 1
                detected += bool(frame.get("detected"))
                empty += not bool(frame.get("detected"))
                sessions.add(frame.get("session_id"))
                tracks.add(frame.get("track_id"))
        report["input"] = dict(frames=count, detected=detected, not_detected=empty,
                               sessions=sorted(sessions), tracks=sorted(tracks))
        status = [json.loads(x[len("YOLO_STATUS "):]) for x in (output / "vision.log").read_text().splitlines()
                  if x.startswith("YOLO_STATUS ")]
        settled = [x for x in status if x["frames"] > 1]
        if settled:
            report["vision"] = dict(status_samples=len(settled), last=settled[-1],
                                    mean_reported_fps=sum(x["fps"] for x in settled) / len(settled))
        ctl = (output / "controller.log").read_text()
        report["controller_summary"] = ctl.splitlines()[-8:]
        require(count > 0, "No real FOLLOW frames reached the controller")
        require("malformed=0" in ctl, "Malformed input frames observed")
        report["status"] = "interrupted" if interrupted else "passed" if detected else "no_person_detected"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        print(str(exc), file=sys.stderr, flush=True)
    finally:
        for process in (vision, controller):
            try:
                stop(process)
            except Exception as exc:
                report.setdefault("cleanup_errors", []).append(str(exc))
                report["status"] = "failed"
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print("LIVE_CHECK_STATUS=" + report["status"], flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
