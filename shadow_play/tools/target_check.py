#!/usr/bin/env python3
"""Run the controller's software checks on Linux using prebuilt target binaries."""
import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from pc_check import csv_summary, require, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", default="bin")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    binary = (root / args.bin_dir).resolve()
    output = root / "output" / ("target-check-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "platform": platform.platform(), "architecture": platform.machine(),
              "root": str(root), "output": str(output), "scope": "software tests, exported motor commands only",
              "tests": [], "traces": {}}

    def run(name, command, timeout=60):
        print("[RUN] " + name, flush=True)
        check = {"name": name, "status": "running"}
        report["tests"].append(check)
        started = time.monotonic()
        with (output / (name + ".log")).open("w", encoding="utf-8") as log:
            result = subprocess.run([str(part) for part in command], cwd=str(root), stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout,
                                    env=dict(os.environ, SHADOW_TEST_ALSA_NULL="1"))
        check.update(exit_code=result.returncode, seconds=round(time.monotonic() - started, 3),
                     status="passed" if result.returncode == 0 else "failed")
        require(result.returncode == 0, name + " failed; inspect " + str(output / (name + ".log")))

    try:
        require(platform.system() == "Linux", "Target must run Linux")
        for suite in ("mapper", "script_audio", "input", "controller", "motor_protocol"):
            run(suite + "_tests", [binary / (suite + "_tests")])
        run("follow_sender", [sys.executable, root / "tests/test_follow_sender.py"])
        run("follow_chain", [sys.executable, root / "tests/follow_chain_test.py", binary / "shadow_show", root])
        run("live_udp", [binary / "live_udp_tests", binary / "shadow_show", root])
        with (root / "config/calibration.simulation.csv").open(encoding="utf-8") as handle:
            calibration = {row["axis_id"]: row for row in csv.DictReader(line for line in handle if not line.startswith("#"))}
        scenarios = {
            "rehearsal90": ["--seconds", "92"],
            "touch": ["--mode", "touch", "--seconds", "4", "--replay", "assets/touch_demo.jsonl"],
            "camera": ["--mode", "camera", "--seconds", "4", "--replay", "assets/camera_demo.jsonl"],
            "three_modes": ["--seconds", "12", "--commands", "assets/mode_session.csv",
                            "--replay-at", "3500", "assets/touch_demo.jsonl", "--replay-at", "7000", "assets/camera_demo.jsonl",
                            "--record-input", str(output / "mode_inputs.jsonl"),
                            "--record-commands", str(output / "mode_commands.csv")],
        }
        for name, arguments in scenarios.items():
            destination = output / (name + ".csv")
            run(name, [binary / "shadow_show"] + arguments + ["--output", destination])
            report["traces"][name] = csv_summary(destination, calibration)
            run("preview_" + name, [binary / "trace_preview", destination, output / (name + ".svg")])
        require(report["traces"]["rehearsal90"]["samples"] == 46010, "Incorrect rehearsal sample count")
        require(set(report["traces"]["three_modes"]["modes"]) == {"script", "paused", "touch", "camera", "stopped"},
                "Missing mode in demonstration")
        replay = output / "three_modes_replayed.csv"
        run("recorded_replay", [binary / "shadow_show", "--seconds", "12", "--replay", output / "mode_inputs.jsonl",
                                "--commands", output / "mode_commands.csv", "--output", replay])
        require(sha256(replay) == sha256(output / "three_modes.csv"), "Recorded replay differs")
        report["replay_sha256"] = sha256(replay)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("TARGET_RESULT_DIR=" + str(output), flush=True)
        print("TARGET_CHECK_STATUS=" + report["status"], flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
