#!/usr/bin/env python3
"""Record byte-exact Python fixed INT8 versus Vitis HLS C-sim evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("python_heatmap", type=Path)
    parser.add_argument("hls_heatmap", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = np.fromfile(args.python_heatmap, dtype=np.uint8)
    actual = np.fromfile(args.hls_heatmap, dtype=np.uint8)
    mismatches = int(np.count_nonzero(expected != actual)) if expected.size == actual.size else max(expected.size, actual.size)
    report = {
        "title": "Python 定点 INT8 与 Vitis HLS C-sim 一致性",
        "expected_bytes": 36 * 64 * 16,
        "python_bytes": int(expected.size),
        "hls_bytes": int(actual.size),
        "python_sha256": digest(args.python_heatmap),
        "hls_sha256": digest(args.hls_heatmap),
        "mismatch_bytes": mismatches,
        "pass": bool(expected.size == 36 * 64 * 16 and actual.size == expected.size and mismatches == 0),
        "scope": "HLS C-sim only; physical FPGA validation is still required",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not report["pass"]:
        raise SystemExit(6)


if __name__ == "__main__":
    main()
