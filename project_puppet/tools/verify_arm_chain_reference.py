"""Reproduce the frozen ARM-CHAIN checkpoint metrics on the 371-image validation set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(r"E:\pytorch_work"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "deploy/dpu_arm_chain/reference_validation.json",
    )
    parser.add_argument("--batch-size", type=int, default=24)
    args = parser.parse_args()
    root = args.source_root.resolve()
    sys.path.insert(0, str(root))

    from pose_model.arm_decoder import ArmChainRanker
    from pose_model.dataset_shadow import ShadowNinePointDataset
    from pose_model.train_arm_decoder import collect, evaluate, load_model

    baseline_path = root / "pose_model/runs/Data_004_baseline_40/best.pt"
    wrist_path = root / "pose_model/runs/Data_004_wrist_repair/candidate_best.pt"
    decoder_path = root / "pose_model/runs/Data_004_arm_chain_decoder/best.pt"
    annotations = root / "Data_004/Data_004_shadow_validation.json"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    baseline = load_model(baseline_path, device)
    wrist = load_model(wrist_path, device)
    checkpoint = torch.load(decoder_path, map_location=device, weights_only=True)
    ranker = ArmChainRanker(int(checkpoint["feature_count"])).to(device).eval()
    ranker.load_state_dict(checkpoint["model"], strict=True)
    validation = collect(
        ShadowNinePointDataset(annotations, training=False),
        baseline,
        wrist,
        device,
        args.batch_size,
    )
    features, _, _, candidates, gt_elbow, gt_wrist = (
        value.to(device) for value in validation
    )
    actual = evaluate(ranker, features, candidates, gt_elbow, gt_wrist)
    expected = checkpoint.get("metrics", {})
    differences = {key: actual[key] - float(expected[key]) for key in actual}
    passed = all(abs(value) < 1e-7 for value in differences.values())
    report = {
        "passed": passed,
        "device": str(device),
        "validation_images": len(ShadowNinePointDataset(annotations, training=False)),
        "evaluated_visible_arm_sides": int(features.shape[0]),
        "actual": actual,
        "checkpoint_expected": expected,
        "difference": differences,
        "note": "This reproduces checkpoint ranking metrics before temporal/DOWN video priors.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
