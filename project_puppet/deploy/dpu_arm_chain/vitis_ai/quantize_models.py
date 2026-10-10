"""Vitis AI 3.0 PyTorch quantization for both ARM-CHAIN V2 pose networks.

Run this inside the Vitis AI 3.0 PyTorch container.  The script deliberately
quantizes two independent CNNs; the ARM-CHAIN MLP stays on the A53 CPU.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from pytorch_nndct.apis import torch_quantizer


def load_model(path: Path, source_root: Path, device: torch.device):
    sys.path.insert(0, str(source_root))
    from pose_model.model import make_pose_model

    checkpoint = torch.load(path, map_location="cpu")
    if checkpoint.get("architecture", "v1") != "v2":
        raise RuntimeError(f"{path} is not a V2 pose checkpoint")
    model = make_pose_model("v2")
    model.load_state_dict(checkpoint["model"], strict=True)
    return model.eval().to(device)


def calibration_loader(source_root: Path, annotations: Path, batch_size: int):
    sys.path.insert(0, str(source_root))
    from pose_model.dataset_shadow import ShadowNinePointDataset

    dataset = ShadowNinePointDataset(annotations, training=False)
    # The frozen JSON was produced on Windows and intentionally remains
    # read-only.  Resolve its drive-qualified root and backslash-separated
    # filenames against the Linux container's read-only source mount.
    dataset.image_dir = source_root
    for sample in dataset.samples:
        sample["file_name"] = sample["file_name"].replace("\\", "/")
    return DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)


def quantize_one(name, weight, source_root, annotations, destination, mode, batch_size):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_model(weight, source_root, device)
    dummy = torch.zeros((batch_size, 3, 144, 256), device=device)
    output_dir = destination / name
    output_dir.mkdir(parents=True, exist_ok=True)
    quantizer = torch_quantizer(
        mode,
        model,
        (dummy,),
        output_dir=str(output_dir),
        device=device,
    )
    quant_model = quantizer.quant_model.eval()
    loader = calibration_loader(source_root, annotations, batch_size)
    with torch.no_grad():
        for images, _, _ in loader:
            quant_model(images.to(device))
    if mode == "calib":
        quantizer.export_quant_config()
    else:
        # Batch 1 is required by the DPU deployment graph.
        quantizer.export_xmodel(output_dir=str(output_dir), deploy_check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("/workspace/pytorch_work"))
    parser.add_argument("--mode", choices=("calib", "test"), required=True)
    parser.add_argument("--output", type=Path, default=Path("quantized"))
    parser.add_argument("--batch-size", type=int, default=1)
    args = parser.parse_args()
    root = args.source_root.resolve()
    annotations = root / "Data_004/Data_004_shadow_validation.json"
    models = {
        "pose_baseline_v2": root / "pose_model/runs/Data_004_baseline_40/best.pt",
        "pose_wrist_v2": root / "pose_model/runs/Data_004_wrist_repair/candidate_best.pt",
    }
    for name, weight in models.items():
        quantize_one(
            name, weight, root, annotations, args.output.resolve(), args.mode, args.batch_size
        )
        print(f"{args.mode}: {name} complete", flush=True)


if __name__ == "__main__":
    main()
