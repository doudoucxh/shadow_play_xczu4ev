#!/usr/bin/env python3
"""Summarize v7 board snapshots for the ten-minute real-time acceptance report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--minimum-seconds", type=float, default=600.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(args.snapshot_dir.glob("sample_*.json"))]
    if len(records) < 2:
        raise RuntimeError("at least two atomic snapshots are required")
    inference_us = np.asarray([item["inference_us"] for item in records], dtype=np.float64)
    frame_period_us = np.asarray([item["frame_period_us"] for item in records if item.get("frame_period_us", 0) > 0], dtype=np.float64)
    if frame_period_us.size == 0:
        raise RuntimeError("snapshots do not contain valid frame_period_us")
    frame_delta = int(records[-1]["frame_counter"]) - int(records[0]["frame_counter"])
    duration_s = frame_delta * float(np.median(frame_period_us)) / 1_000_000.0
    fps = 1_000_000.0 / frame_period_us
    status_ok = all(item["backend_pl"] == 1 and item["completed_layers"] == 14 and item["failed_layer"] == 0 for item in records)
    report = {
        "title": "实时链路部署检查",
        "snapshots": len(records),
        "frame_counter_delta": frame_delta,
        "estimated_duration_s": duration_s,
        "minimum_duration_s": args.minimum_seconds,
        "duration_pass": duration_s >= args.minimum_seconds,
        "pl_status_pass": status_ok,
        "inference_us": {"median": float(np.median(inference_us)), "p95": float(np.percentile(inference_us, 95))},
        "end_to_end_fps": {"median": float(np.median(fps)), "p95": float(np.percentile(fps, 95))},
        "manual_checks": {
            "camera_hdmi_continuous_no_tearing_or_color_error": None,
            "no_fixed_offset_or_left_right_swap": None,
            "pose_reasonable_for_raise_cross_fast_static": None,
        },
        "pass": bool(duration_s >= args.minimum_seconds and status_ok),
    }
    output = args.output or args.snapshot_dir.parent / "reports" / "realtime_run.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"duration_s={duration_s:.3f} inference_median_us={np.median(inference_us):.3f} inference_p95_us={np.percentile(inference_us, 95):.3f}")
    print(f"fps_median={np.median(fps):.3f} fps_p95={np.percentile(fps, 95):.3f} pl_status_pass={int(status_ok)}")
    print(f"REPORT={output}")
    if duration_s < args.minimum_seconds or not status_ok:
        raise SystemExit(5)


if __name__ == "__main__":
    main()
