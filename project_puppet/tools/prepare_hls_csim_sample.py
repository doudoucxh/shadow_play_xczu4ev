#!/usr/bin/env python3
"""Create one raw BGR input and Python fixed-INT8 reference heatmap for HLS C-sim."""

from __future__ import annotations

import argparse
from pathlib import Path

from export_pose_hls import ROOT, fixed_forward, fused_parameters, load_checkpoint, read_rgb
from validate_pose_consistency import load_export


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("output_dir", type=Path, default=ROOT / "deploy" / "csim", nargs="?")
    args = parser.parse_args()
    model, _ = load_checkpoint(ROOT / "best.pt")
    params = fused_parameters(model)
    _, quantized, activations = load_export(
        ROOT / "ultral_xczu4ev" / "vitis" / "ov5640_hdmi" / "src" / "pose_model_int8_weights.json",
        ROOT / "deploy" / "artifacts" / "pose_model_int8.npz", params)
    rgb = read_rgb(args.image)
    fixed = fixed_forward(rgb, params, quantized, activations)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "input_bgr.bin").write_bytes(rgb[:, :, ::-1].tobytes())
    (args.output_dir / "python_heatmap.bin").write_bytes(fixed[0].permute(1, 2, 0).numpy().tobytes())
    print(args.output_dir)


if __name__ == "__main__":
    main()
