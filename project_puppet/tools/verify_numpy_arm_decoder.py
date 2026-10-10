"""Check the Cortex-A53 NumPy decoder against the validated PyTorch implementation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import torch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(r"E:\pytorch_work"))
    parser.add_argument(
        "--release", type=Path,
        default=Path(__file__).resolve().parents[1] / "deploy/dpu_arm_chain",
    )
    args = parser.parse_args()
    root, release = args.source_root.resolve(), args.release.resolve()
    sys.path.insert(0, str(root))
    from pose_model.arm_decoder import ArmChainRanker, build_arm_chains
    from pose_model.dataset_shadow import ShadowNinePointDataset
    from pose_model.model import make_pose_model
    from pose_model.webcam_test import decode_arm_structured

    spec = importlib.util.spec_from_file_location("arm_chain_dpu", release / "runtime/arm_chain_dpu.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)

    def load_pose(path):
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        model = make_pose_model("v2")
        model.load_state_dict(checkpoint["model"], strict=True)
        return model.eval()

    baseline = load_pose(root / "pose_model/runs/Data_004_baseline_40/best.pt")
    wrist = load_pose(root / "pose_model/runs/Data_004_wrist_repair/candidate_best.pt")
    checkpoint = torch.load(
        root / "pose_model/runs/Data_004_arm_chain_decoder/best.pt",
        map_location="cpu", weights_only=True,
    )
    ranker = ArmChainRanker(int(checkpoint["feature_count"])).eval()
    ranker.load_state_dict(checkpoint["model"], strict=True)
    image = ShadowNinePointDataset(
        root / "Data_004/Data_004_shadow_validation.json", training=False
    )[0][0].unsqueeze(0)
    with torch.no_grad():
        base_logits, wrist_logits = baseline(image), wrist(image)
        torch_chains, torch_features, torch_anchors = build_arm_chains(base_logits, wrist_logits)
        torch_result = decode_arm_structured(
            base_logits, wrist_logits, ranker, None, None, .35, .45, .5
        )
    numpy_chains, numpy_features, numpy_anchors = runtime.build_arm_chains(
        base_logits.numpy(), wrist_logits.numpy()
    )
    decoder = runtime.ArmChainDecoder(release / "decoder/arm_chain_ranker.npz", .35, .45, .5)
    numpy_result = decoder.decode(base_logits.numpy(), wrist_logits.numpy())
    errors = {
        "chain_max_abs": float(np.max(np.abs(torch_chains.numpy() - numpy_chains))),
        "feature_max_abs": float(np.max(np.abs(torch_features.numpy() - numpy_features))),
        "anchor_max_abs": float(np.max(np.abs(torch_anchors.numpy() - numpy_anchors))),
        "point_max_abs": float(np.max(np.abs(torch_result[0] - numpy_result[0]))),
        "confidence_max_abs": float(np.max(np.abs(torch_result[1] - numpy_result[1]))),
        "forearm_ratio_max_abs": float(np.max(np.abs(torch_result[4].numpy() - numpy_result[2]))),
        "down_match": bool(torch_result[5] == numpy_result[3]),
    }
    passed = (
        errors["chain_max_abs"] == 0.0
        and errors["feature_max_abs"] < 2e-5
        and errors["point_max_abs"] == 0.0
        and errors["confidence_max_abs"] < 2e-6
        and errors["forearm_ratio_max_abs"] < 2e-6
        and errors["down_match"]
    )
    report = {"passed": passed, "sample": 0, "errors": errors}
    destination = release / "numpy_decoder_equivalence.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
