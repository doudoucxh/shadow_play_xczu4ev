"""Freeze the validated two-network ARM-CHAIN release without touching training files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch


KEYPOINTS = [
    "head", "left_shoulder", "right_shoulder", "left_elbow",
    "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pose_model(path: Path, source_root: Path):
    sys.path.insert(0, str(source_root))
    from pose_model.model import make_pose_model

    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    architecture = checkpoint.get("architecture", "v1")
    if architecture != "v2":
        raise RuntimeError(f"{path} is {architecture!r}; ARM-CHAIN release requires v2")
    model = make_pose_model(architecture)
    model.load_state_dict(checkpoint["model"], strict=True)
    return model.eval(), architecture


def export_onnx(model, destination: Path) -> None:
    sample = torch.zeros(1, 3, 144, 256, dtype=torch.float32)
    torch.onnx.export(
        model,
        sample,
        destination,
        input_names=["image"],
        output_names=["heatmaps"],
        opset_version=13,
        do_constant_folding=True,
        dynamo=False,
    )
    checked = onnx.load(destination)
    onnx.checker.check_model(checked)


def compare_onnx(model, path: Path) -> dict[str, float]:
    generator = torch.Generator().manual_seed(20260920)
    sample = torch.rand((1, 3, 144, 256), generator=generator) * 2.0 - 1.0
    with torch.no_grad():
        expected = model(sample).numpy()
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    actual = session.run(None, {session.get_inputs()[0].name: sample.numpy()})[0]
    error = np.abs(expected - actual)
    return {
        "max_abs_error": float(error.max()),
        "mean_abs_error": float(error.mean()),
    }


def export_ranker(path: Path, destination: Path, source_root: Path) -> dict:
    sys.path.insert(0, str(source_root))
    from pose_model.arm_decoder import ArmChainRanker

    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    feature_count = int(checkpoint["feature_count"])
    if feature_count != 32:
        raise RuntimeError(f"ranker feature count is {feature_count}, expected 32")
    ranker = ArmChainRanker(feature_count)
    ranker.load_state_dict(checkpoint["model"], strict=True)
    state = ranker.state_dict()
    arrays = {name.replace("network.", ""): value.numpy() for name, value in state.items()}
    np.savez(destination, **arrays)
    return {
        "feature_count": feature_count,
        "layers": [32, 64, 32, 1],
        "metrics": checkpoint.get("metrics", {}),
        "npz_keys": sorted(arrays),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(r"E:\pytorch_work"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "deploy" / "dpu_arm_chain",
    )
    args = parser.parse_args()
    root = args.source_root.resolve()
    output = args.output.resolve()
    fp32_dir = output / "models" / "fp32"
    decoder_dir = output / "decoder"
    source_dir = output / "reference_source"
    for directory in (fp32_dir, decoder_dir, source_dir):
        directory.mkdir(parents=True, exist_ok=True)

    inputs = {
        "baseline_weight": root / "pose_model/runs/Data_004_baseline_40/best.pt",
        "wrist_weight": root / "pose_model/runs/Data_004_wrist_repair/candidate_best.pt",
        "arm_decoder_weight": root / "pose_model/runs/Data_004_arm_chain_decoder/best.pt",
        "webcam_test": root / "pose_model/webcam_test.py",
        "arm_decoder_source": root / "pose_model/arm_decoder.py",
        "wrist_decoder_source": root / "pose_model/wrist_decoder.py",
        "model_source": root / "pose_model/model.py",
    }
    missing = [str(path) for path in inputs.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing release inputs:\n" + "\n".join(missing))

    baseline, baseline_arch = load_pose_model(inputs["baseline_weight"], root)
    wrist, wrist_arch = load_pose_model(inputs["wrist_weight"], root)
    baseline_onnx = fp32_dir / "pose_baseline_v2.onnx"
    wrist_onnx = fp32_dir / "pose_wrist_v2.onnx"
    export_onnx(baseline, baseline_onnx)
    export_onnx(wrist, wrist_onnx)
    comparisons = {
        "baseline": compare_onnx(baseline, baseline_onnx),
        "wrist": compare_onnx(wrist, wrist_onnx),
    }
    for name, result in comparisons.items():
        if result["max_abs_error"] > 1e-4:
            raise RuntimeError(f"{name} ONNX mismatch: {result}")

    ranker_info = export_ranker(
        inputs["arm_decoder_weight"], decoder_dir / "arm_chain_ranker.npz", root
    )
    for key in ("webcam_test", "arm_decoder_source", "wrist_decoder_source", "model_source"):
        shutil.copy2(inputs[key], source_dir / inputs[key].name)

    artifacts = [baseline_onnx, wrist_onnx, decoder_dir / "arm_chain_ranker.npz"]
    manifest = {
        "release": "data004-dual-v2-arm-chain",
        "created_by": "tools/export_dpu_arm_chain.py",
        "immutable_sources": {
            name: {
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in inputs.items()
        },
        "artifacts": {
            path.relative_to(output).as_posix(): {
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in artifacts
        },
        "model": {
            "architectures": [baseline_arch, wrist_arch],
            "input": {"shape": [1, 3, 144, 256], "layout": "NCHW", "range": [-1.0, 1.0]},
            "output": {"shape": [1, 9, 36, 64], "layout": "NCHW"},
            "keypoints": KEYPOINTS,
        },
        "decoder": {
            **ranker_info,
            "peaks_per_channel": 3,
            "chains_per_side": 72,
            "joint_pair_search": True,
            "same_elbow_penalty": {"minimum_normalized_separation": 0.18, "weight": 10.0},
            "temporal_weight": 0.35,
            "min_forearm_ratio": 0.45,
            "down_pose_weight": 0.5,
            "velocity_clip_shoulder_span": 0.35,
        },
        "onnx_equivalence": comparisons,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"output": str(output), "onnx_equivalence": comparisons}, indent=2))


if __name__ == "__main__":
    main()
