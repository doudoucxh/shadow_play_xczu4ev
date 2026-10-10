#!/usr/bin/env python3
"""Build and exercise the PC-only controller; retain logs and demonstration traces."""

import argparse
import csv
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import time
import wave


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csv_summary(path, calibration):
    ranges = {}
    modes, states = set(), set()
    samples = 0
    previous = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            axis = row["axis_id"]
            require(axis in calibration, "Unknown axis in trace: " + axis)
            angle, when = float(row["angle_deg"]), float(row["time_s"])
            require(math.isfinite(angle) and math.isfinite(when), "Non-finite trace value")
            limits = calibration[axis]
            require(float(limits["min_deg"]) - 1e-5 <= angle <= float(limits["max_deg"]) + 1e-5,
                    "Simulation angle outside calibration: " + axis)
            if axis in previous:
                old_time, old_angle = previous[axis]
                require(when > old_time, "Trace time did not increase for " + axis)
                speed = float(limits["max_speed_deg_s"])
                # CSV rounds both timestamps and angles to six decimal places.
                # Each difference can therefore deviate by up to 1e-6. Include
                # the time quantization in degrees, especially for realtime runs.
                rounding_deg = speed * 1e-6 + 1e-6 + 1e-9
                require(abs(angle - old_angle) <= speed * (when - old_time) + rounding_deg,
                        "Simulation speed limit exceeded: " + axis)
            previous[axis] = (when, angle)
            span = ranges.setdefault(axis, [angle, angle])
            span[0], span[1] = min(span[0], angle), max(span[1], angle)
            modes.add(row["mode"])
            states.add(row["input_state"])
            samples += 1
    require(samples > 0, "Empty trace")
    return {"samples": samples, "modes": sorted(modes), "input_states": sorted(states), "angle_ranges_deg": ranges}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--build-dir", default="build-vm")
    args = parser.parse_args()
    require(1 <= args.jobs <= 16, "--jobs must be 1..16")
    source = Path(__file__).resolve().parent.parent
    build = Path(args.build_dir)
    if not build.is_absolute():
        build = source / build
    build = build.resolve()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    result_dir = source / "output" / ("pc-check-" + stamp)
    result_dir.mkdir(parents=True, exist_ok=False)
    report = {"scope": "Ubuntu PC simulation only", "status": "running", "source": str(source),
              "build": str(build), "result_dir": str(result_dir), "started": datetime.datetime.now().astimezone().isoformat(),
              "checks": [], "environment": {}, "traces": {}}

    def run(name, command, timeout=120, stdout_file=None, env=None):
        print("[RUN] " + name, flush=True)
        report["checks"].append({"name": name, "command": [str(part) for part in command], "status": "running"})
        check = report["checks"][-1]
        started = time.monotonic()
        with (result_dir / (name + ".stderr.log")).open("w", encoding="utf-8") as errors:
            destination = Path(stdout_file) if stdout_file else result_dir / (name + ".stdout.log")
            with destination.open("x", encoding="utf-8") as output:
                completed = subprocess.run([str(part) for part in command], cwd=str(source),
                                           stdout=output, stderr=errors, timeout=timeout, env=env)
        check["seconds"] = round(time.monotonic() - started, 3)
        check["exit_code"] = completed.returncode
        check["status"] = "passed" if completed.returncode == 0 else "failed"
        require(completed.returncode == 0, name + " failed; inspect logs in " + str(result_dir))
        return destination

    try:
        require(platform.system() == "Linux", "Run this entry point inside Ubuntu")
        report["environment"]["platform"] = platform.platform()
        report["environment"]["architecture"] = platform.machine()
        report["environment"]["python"] = sys.version
        report["environment"]["os_release"] = Path("/etc/os-release").read_text(encoding="utf-8")
        required_tools = ("g++", "cmake", "ctest", "ninja", "pkg-config")
        missing = [name for name in required_tools if not shutil.which(name)]
        require(not missing, "Missing tools: " + ", ".join(missing) +
                ". Install: sudo apt install build-essential cmake ninja-build pkg-config libasound2-dev python3")
        for name in required_tools:
            version = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=10)
            report["environment"][name] = version.stdout.splitlines()[0]
        alsa = subprocess.run(["pkg-config", "--modversion", "alsa"], capture_output=True, text=True, timeout=10)
        require(alsa.returncode == 0, "ALSA development files missing. Install: sudo apt install libasound2-dev")
        report["environment"]["alsa"] = alsa.stdout.strip()
        cache = build / "CMakeCache.txt"
        if cache.exists():
            text = cache.read_text(encoding="utf-8")
            require("CMAKE_HOME_DIRECTORY:INTERNAL=" + str(source) + "\n" in text,
                    "Build cache belongs to a different source path; choose a new --build-dir")
        run("01-configure", ["cmake", "-S", source, "-B", build, "-G", "Ninja",
                             "-DCMAKE_BUILD_TYPE=Debug", "-DSHADOW_REQUIRE_ALSA=ON", "-DBUILD_TESTING=ON"])
        run("02-build", ["cmake", "--build", build, "--parallel", str(args.jobs)], timeout=600)
        ctest_env = dict(os.environ, SHADOW_TEST_ALSA_NULL="1")
        # CMake 3.16-compatible: execute ctest in the build directory.
        run("03-ctest", ["cmake", "-E", "chdir", build, "ctest", "--output-on-failure"],
            timeout=180, env=ctest_env)
        listing = subprocess.run(["cmake", "-E", "chdir", str(build), "ctest", "-N"],
                                 capture_output=True, text=True, timeout=15)
        require(listing.returncode == 0 and "Total Tests: 9" in listing.stdout,
                "Expected all 9 Linux/Python tests to be registered")
        report["ctest_count"] = 9
        test_log = build / "Testing" / "Temporary" / "LastTest.log"
        if test_log.exists():
            shutil.copyfile(str(test_log), str(result_dir / "LastTest.log"))
        show, preview = build / "shadow_show", build / "trace_preview"
        with (source / "config/calibration.simulation.csv").open(encoding="utf-8") as handle:
            calibration = {row["axis_id"]: row for row in csv.DictReader(line for line in handle if not line.startswith("#"))}
        scenarios = {
            "rehearsal90": ["--seconds", "92"],
            "touch": ["--mode", "touch", "--seconds", "4", "--replay", "assets/touch_demo.jsonl"],
            "camera": ["--mode", "camera", "--seconds", "4", "--replay", "assets/camera_demo.jsonl"],
            "three_modes": ["--seconds", "12", "--commands", "assets/mode_session.csv",
                            "--replay-at", "3500", "assets/touch_demo.jsonl",
                            "--replay-at", "7000", "assets/camera_demo.jsonl",
                            "--record-input", str(result_dir / "mode_inputs.jsonl"),
                            "--record-commands", str(result_dir / "mode_commands.csv")],
        }
        for name, options in scenarios.items():
            target = result_dir / (name + ".csv")
            run("04-" + name, [show] + options + ["--output", target])
            report["traces"][name] = csv_summary(target, calibration)
            run("05-preview-" + name, [preview, target, result_dir / (name + ".svg")])
        require(report["traces"]["rehearsal90"]["samples"] == 46010, "Unexpected 90-second rehearsal sample count")
        require(set(report["traces"]["three_modes"]["modes"]) == {"script", "paused", "touch", "camera", "stopped"},
                "Three-mode demonstration missed a state")
        replay = result_dir / "three_modes_replayed.csv"
        run("06-replay", [show, "--seconds", "12", "--commands", result_dir / "mode_commands.csv",
                           "--replay", result_dir / "mode_inputs.jsonl", "--output", replay])
        require(sha256(replay) == sha256(result_dir / "three_modes.csv"), "Deterministic replay changed trace")
        report["replay_sha256"] = sha256(replay)
        synthetic = result_dir / "synthetic_pose9.jsonl"
        run("07-synthetic-input", [sys.executable, source / "integrations/follow/pose_sender.py",
                                   "--seconds", "3", "--jsonl"], stdout_file=synthetic)
        run("08-grouped-targets", [show, "--mode", "camera", "--seconds", "4", "--replay", synthetic,
                                   "--motor-format", "jsonl", "--output", result_dir / "motor_targets.jsonl"])
        with (result_dir / "motor_targets.jsonl").open(encoding="utf-8") as handle:
            grouped = [json.loads(line) for line in handle]
        require(len(grouped) == 201 and all(len(row["axes"]) == len(calibration) for row in grouped),
                "Grouped targets missing a tick or simulated axis")
        report["grouped_target_frames"] = len(grouped)
        spec = importlib.util.spec_from_file_location("pc_pose_sender", source / "integrations/follow/pose_sender.py")
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        live_output = result_dir / "live_motor_targets.jsonl"
        live_log = result_dir / "live_udp.log"
        print("[RUN] live UDP sender -> controller -> targets", flush=True)
        with live_log.open("x", encoding="utf-8") as log:
            process = subprocess.Popen([str(show), "--mode", "camera", "--seconds", "3", "--realtime",
                                        "--listen", str(port), "--record-input", str(result_dir / "live_inputs.jsonl"),
                                        "--motor-format", "jsonl", "--output", str(live_output)],
                                       cwd=str(source), stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 2
                while "Input UDP:" not in live_log.read_text(encoding="utf-8"):
                    require(process.poll() is None and time.monotonic() < deadline, "Live controller did not become ready")
                    time.sleep(0.02)
                origin = time.monotonic()
                with adapter.PoseSender(port) as sender:
                    for sequence in range(1, 61):
                        elapsed = time.monotonic() - origin
                        sender.publish(adapter.demo_pose(elapsed) if sequence <= 45 else None,
                                       sequence, time.monotonic(), 1)
                        time.sleep(1 / 30.0)
                    report["live_sender"] = sender.stats
                require(process.wait(timeout=5) == 0, "Live controller failed")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
        live_rows = [json.loads(line) for line in live_output.read_text(encoding="utf-8").splitlines()]
        require(any(abs(axis["angle_deg"] - 90) > 1 for row in live_rows for axis in row["axes"]
                    if axis["rod"] == "wusong_left"), "Live hand input did not change simulated output")
        require(any(axis["input_state"] == "returning_to_neutral" for row in live_rows for axis in row["axes"]),
                "Live lost-person messages did not trigger timeout handling")
        require(all(abs(axis["angle_deg"] - 90) < 0.1 for axis in live_rows[-1]["axes"]),
                "Live simulation did not return to neutral after loss")
        require(all(abs(axis["angle_deg"] - 90) < 1e-8 for row in live_rows for axis in row["axes"]
                    if axis["rod"].startswith("tiger_")), "Camera mode changed a tiger rod")
        report["checks"].append({"name": "09-live-udp-and-loss", "status": "passed"})
        live_stats = live_log.read_text(encoding="utf-8")
        require("malformed=0" in live_stats and "lifecycle_rejections=0" in live_stats,
                "Live controller rejected messages; inspect live_udp.log")
        cue = result_dir / "cue90.wav"
        run("10-cue-wav", [build / "make_cue_wav", cue, "90"])
        with wave.open(str(cue), "rb") as audio:
            require(audio.getnchannels() == 1 and audio.getsampwidth() == 2 and
                    audio.getframerate() == 48000 and audio.getnframes() == 4320000, "Unexpected cue WAV format")
            report["cue_wav"] = {"duration_s": 90, "sample_rate": 48000, "channels": 1, "sample_bits": 16}
        stage = result_dir / "install-stage"
        # Exercise the actual WAV installation rule using a uniquely named test
        # resource, and remove only that resource after installation.
        install_fixture = source / "assets" / ("pc_check_cue_" + stamp + ".wav")
        require(not install_fixture.exists(), "Installation fixture path already exists")
        try:
            shutil.copyfile(str(cue), str(install_fixture))
            run("11-install", ["cmake", "--install", build, "--prefix", stage])
            installed_cue = stage / "share/shadow-play/assets" / install_fixture.name
            require(installed_cue.exists() and sha256(installed_cue) == sha256(cue),
                    "Installation omitted or changed WAV resource")
            report["wav_install_verified"] = True
        finally:
            if install_fixture.exists():
                install_fixture.unlink()
        run("12-installed-app", [stage / "bin/shadow_show", "--seconds", "1",
                                  "--script", stage / "share/shadow-play/assets/rehearsal90.json",
                                  "--calibration", stage / "share/shadow-play/config/calibration.simulation.csv",
                                  "--retarget", stage / "share/shadow-play/config/retarget.simulation.json",
                                  "--output", result_dir / "installed_app.csv"])
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        print("[FAIL] " + str(error), file=sys.stderr)
    finally:
        report["finished"] = datetime.datetime.now().astimezone().isoformat()
        (result_dir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = ["# Ubuntu 电脑端验证结果", "", "- 状态：" + report["status"],
                 "- 工程：`" + str(source) + "`", "- 输出：`" + str(result_dir) + "`",
                 "- 范围：模拟输入与电机指令计算；没有连接开发板、真实电机或摄像头。", ""]
        if report.get("error"):
            lines += ["失败原因：" + report["error"], ""]
        lines += ["| 步骤 | 结果 |", "| --- | --- |"]
        lines += ["| " + item["name"] + " | " + item["status"] + " |" for item in report["checks"]]
        lines += ["", "详情见 summary.json、CTest 日志及各步骤日志。",
                  "", "rehearsal90.svg：90 秒排练；three_modes.svg：三模式与暂停恢复；camera.svg：模拟体感；touch.svg：模拟触控。",
                  "", "cue90.wav 仅为测试节拍，不是正式配音。ALSA null 测试不证明扬声器或板端音画同步。"]
        (result_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("RESULT_DIR=" + str(result_dir), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
