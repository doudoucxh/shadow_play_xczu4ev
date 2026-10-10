#!/usr/bin/env python3
"""Validate FP32 -> fixed INT8 -> FPGA consistency on identical inputs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import OrderedDict
from pathlib import Path

import numpy as np
import torch

from export_pose_hls import (
    KEYPOINTS,
    ROOT,
    SPECS,
    decode_input_coordinates,
    discover_inputs,
    fixed_forward,
    float_forward,
    fused_parameters,
    load_checkpoint,
    read_rgb,
    sha256_file,
    to_tensor,
)

KEYPOINT_NAMES = (
    "head", "left_shoulder", "right_shoulder", "left_elbow",
    "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip",
)


def load_export(metadata_path: Path, npz_path: Path, params: OrderedDict[str, dict]):
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    archive = np.load(npz_path, allow_pickle=False)
    activations = OrderedDict(
        (name, (float(item["scale"]), int(item["zero_point"])))
        for name, item in metadata["activation_qparams"].items()
    )
    quantized: OrderedDict[str, dict] = OrderedDict()
    for spec in SPECS:
        item = metadata["layers"][spec.name]
        entry = {
            "weight": archive[spec.name + "__weight"],
            "bias": archive[spec.name + "__bias"],
            "weight_scale": archive[spec.name + "__weight_scale"],
            "multiplier": archive[spec.name + "__multiplier"],
            "shift": archive[spec.name + "__shift"],
            "input_scale": float(item["input_scale"]),
            "input_zero_point": int(item["input_zero_point"]),
            "output_scale": float(item["output_scale"]),
            "output_zero_point": int(item["output_zero_point"]),
            "kind": item["kind"],
        }
        if spec.residual_name:
            entry.update(
                residual_scale=float(item["residual_scale"]),
                residual_zero_point=int(item["residual_zero_point"]),
                residual_multiplier=int(item["residual_multiplier"]),
                residual_shift=int(item["residual_shift"]),
            )
        quantized[spec.name] = entry
    return metadata, quantized, activations


def percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q)) if values.size else float("nan")


def decode_board_coordinates(heatmaps: torch.Tensor, roi: list[int]) -> np.ndarray:
    array = heatmaps[0, :KEYPOINTS].detach().cpu().numpy().reshape(KEYPOINTS, -1)
    best = array.argmax(axis=1)
    roi_x, roi_y, roi_width, roi_height = roi
    points = []
    for pixel in best:
        heatmap_x = int(pixel % 64)
        heatmap_y = int(pixel // 64)
        x = roi_x * 5 + ((((heatmap_x * 8 + 3) * roi_width * 5 + 256) >> 9))
        y_numerator = (heatmap_y * 8 + 3) * roi_height * 5 + 144
        y = roi_y * 5 + ((y_numerator * 58255) >> 24)
        points.append((x, y))
    return np.asarray(points, dtype=np.int64)


def validate_board_sample(sample_dir: Path, stem: str, fixed: torch.Tensor, checkpoint_sha: str) -> dict:
    heatmap_path = sample_dir / f"{stem}.heatmap.bin"
    meta_path = sample_dir / f"{stem}.json"
    if not heatmap_path.exists() or not meta_path.exists():
        raise RuntimeError(f"incomplete FPGA sample {stem}")
    raw = np.fromfile(heatmap_path, dtype=np.uint8)
    if raw.size != 36 * 64 * 16:
        raise RuntimeError(f"{heatmap_path}: {raw.size} bytes, expected 36864")
    fpga_hwc = raw.reshape(36, 64, 16)
    fixed_hwc = fixed[0].permute(1, 2, 0).cpu().numpy()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta["model_sha256"].lower() != checkpoint_sha.lower():
        raise RuntimeError(f"{meta_path}: model SHA256 does not match the host export")
    fixed_points = decode_board_coordinates(fixed, meta["roi"])
    fpga_points = np.stack((np.asarray(meta["points_x"], dtype=np.int64), np.asarray(meta["points_y"], dtype=np.int64)), axis=1)
    return {
        "heatmap_equal": bool(np.array_equal(fpga_hwc, fixed_hwc)),
        "heatmap_mismatch_bytes": int(np.count_nonzero(fpga_hwc != fixed_hwc)),
        "points_equal": bool(np.array_equal(fpga_points, fixed_points)),
        "backend_pl": int(meta["backend_pl"]),
        "completed_layers": int(meta["completed_layers"]),
        "failed_layer": int(meta["failed_layer"]),
        "inference_us": int(meta["inference_us"]),
        "snapshot_sequence": int(meta["snapshot_sequence"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "best.pt")
    parser.add_argument("--metadata", type=Path, default=ROOT / "ultral_xczu4ev" / "vitis" / "ov5640_hdmi" / "src" / "pose_model_int8_weights.json")
    parser.add_argument("--npz", type=Path, default=ROOT / "deploy" / "artifacts" / "pose_model_int8.npz")
    parser.add_argument("--validation-dir", type=Path, required=True)
    parser.add_argument("--validation-count", type=int, default=50)
    parser.add_argument("--validation-offset", type=int, default=200)
    parser.add_argument("--fpga-dir", type=Path)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "deploy" / "reports")
    return parser.parse_args()


def main() -> None:
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    args = parse_args()
    model, _ = load_checkpoint(args.checkpoint.resolve())
    params = fused_parameters(model)
    metadata, quantized, activations = load_export(args.metadata, args.npz, params)
    if metadata["checkpoint_sha256"] != sha256_file(args.checkpoint):
        raise RuntimeError("checkpoint SHA256 does not match exported metadata")

    paths = discover_inputs(args.validation_dir)
    selected = paths[args.validation_offset:args.validation_offset + args.validation_count]
    if len(selected) != args.validation_count:
        raise RuntimeError(f"need {args.validation_count} validation inputs, found {len(selected)}")
    calibration_hashes = {item["sha256"] for item in metadata["calibration"]["samples"]}
    overlap = [str(path) for path in selected if sha256_file(path) in calibration_hashes]
    if overlap:
        raise RuntimeError(f"calibration/validation overlap: {overlap[:3]}")

    coordinate_errors = []
    frame_rows = []
    board_rows = []
    with torch.inference_mode():
        for frame, path in enumerate(selected):
            rgb = read_rgb(path)
            fp32, _ = float_forward(to_tensor(rgb), params)
            fixed = fixed_forward(rgb, params, quantized, activations)
            fp32_points = decode_input_coordinates(fp32)
            fixed_points = decode_input_coordinates(fixed)
            errors = np.linalg.norm(fp32_points - fixed_points, axis=1)
            coordinate_errors.append(errors)
            row = {"frame": frame, "input": str(path.resolve()), "input_sha256": sha256_file(path)}
            for index, name in enumerate(KEYPOINT_NAMES):
                row[f"{name}_fp32_x"] = float(fp32_points[index, 0])
                row[f"{name}_fp32_y"] = float(fp32_points[index, 1])
                row[f"{name}_int8_x"] = float(fixed_points[index, 0])
                row[f"{name}_int8_y"] = float(fixed_points[index, 1])
                row[f"{name}_delta_px"] = float(errors[index])
            frame_rows.append(row)

            if args.fpga_dir:
                stem = path.name[:-10] if path.name.lower().endswith(".input.bin") else path.stem
                board_rows.append({"frame": frame, "input": str(path.resolve()), **validate_board_sample(args.fpga_dir, stem, fixed, metadata["checkpoint_sha256"])})

    error_array = np.stack(coordinate_errors)
    per_keypoint = {}
    for index, name in enumerate(KEYPOINT_NAMES):
        values = error_array[:, index]
        per_keypoint[name] = {"mean_px": float(values.mean()), "p95_px": percentile(values, 95), "max_px": float(values.max())}
    aggregate = {
        "mean_px": float(error_array.mean()),
        "p95_px": percentile(error_array.reshape(-1), 95),
        "max_px": float(error_array.max()),
        "fraction_le_8px": float(np.mean(error_array <= 8.0)),
    }
    fp32_int8_pass = aggregate["mean_px"] <= 2.0 and aggregate["fraction_le_8px"] >= 0.98
    board_pass = None
    if board_rows:
        board_pass = all(row["heatmap_equal"] and row["points_equal"] and row["backend_pl"] == 1 and row["completed_layers"] == 14 and row["failed_layer"] == 0 for row in board_rows)

    args.report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "title": "部署一致性验证",
        "not_ground_truth_pck": True,
        "checkpoint_sha256": metadata["checkpoint_sha256"],
        "calibration_kind": metadata["calibration"]["kind"],
        "calibration_count": metadata["calibration"]["count"],
        "validation_count": len(selected),
        "calibration_validation_overlap": 0,
        "fp32_to_fixed_int8": {"acceptance": {"mean_px_lte": 2.0, "fraction_le_8px_gte": 0.98}, "aggregate": aggregate, "per_keypoint": per_keypoint, "pass": fp32_int8_pass},
        "fixed_int8_to_fpga": {"samples": len(board_rows), "pass": board_pass, "rows": board_rows},
    }
    json_path = args.report_dir / "deployment_consistency.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = args.report_dir / "frame_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(frame_rows[0].keys()))
        writer.writeheader()
        writer.writerows(frame_rows)
    markdown = [
        "# 部署一致性验证",
        "",
        "> 本报告只比较同一输入在 FP32、Python 定点 INT8 与（如提供）FPGA HLS INT8 间的一致性；没有人工真值，不代表也不宣称真实 PCK。",
        "",
        f"- 模型 SHA256：`{metadata['checkpoint_sha256']}`",
        f"- 校准集：{metadata['calibration']['count']} 帧，类型 `{metadata['calibration']['kind']}`",
        f"- 独立验证集：{len(selected)} 帧，交集 0",
        f"- FP32 → INT8：平均 {aggregate['mean_px']:.3f} px，P95 {aggregate['p95_px']:.3f} px，最大 {aggregate['max_px']:.3f} px，≤8 px 比例 {aggregate['fraction_le_8px']:.4%}，结论 {'通过' if fp32_int8_pass else '未通过'}",
        f"- INT8 → FPGA：样本 {len(board_rows)}，结论 {('通过' if board_pass else '未通过') if board_pass is not None else '待板卡快照'}",
        "",
        "| 关键点 | 均值(px) | P95(px) | 最大(px) |",
        "|---|---:|---:|---:|",
    ]
    for name in KEYPOINT_NAMES:
        item = per_keypoint[name]
        markdown.append(f"| {name} | {item['mean_px']:.3f} | {item['p95_px']:.3f} | {item['max_px']:.3f} |")
    md_path = args.report_dir / "deployment_consistency.md"
    md_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(f"FP32_INT8_PASS={int(fp32_int8_pass)} mean_px={aggregate['mean_px']:.6f} le8={aggregate['fraction_le_8px']:.6f}")
    print(f"FPGA_SAMPLES={len(board_rows)} FPGA_PASS={board_pass}")
    print(f"REPORT={json_path}")
    if not fp32_int8_pass:
        raise SystemExit(3)
    if board_pass is False:
        raise SystemExit(4)


if __name__ == "__main__":
    main()
