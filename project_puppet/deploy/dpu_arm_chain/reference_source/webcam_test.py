from __future__ import annotations

import argparse
import time
import cv2
import numpy as np
import torch

from .arm_decoder import ArmChainRanker, apply_arm_pose_priors, build_arm_chains
from .model import make_pose_model
from .wrist_decoder import (
    WristCandidateRanker,
    build_wrist_candidates,
    correct_arm_identity,
)

INPUT_W = 256
INPUT_H = 144

KEYPOINT_NAMES = [
    "head", "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
]

SKELETON = [
    (0, 1), (0, 2), (1, 2),
    (1, 3), (3, 5),
    (2, 4), (4, 6),
    (1, 7), (2, 8), (7, 8),
]

POINT_COLORS = [
    (0, 255, 255),
    (0, 255, 0), (255, 255, 0),
    (0, 220, 0), (220, 220, 0),
    (0, 180, 0), (180, 180, 0),
    (0, 140, 0), (140, 140, 0),
]


def center_crop_16_9(frame: np.ndarray):
    h, w = frame.shape[:2]
    target = 16.0 / 9.0
    if w / h > target:
        crop_h = h
        crop_w = int(round(h * target))
        x0 = (w - crop_w) // 2
        y0 = 0
    else:
        crop_w = w
        crop_h = int(round(w / target))
        x0 = 0
        y0 = (h - crop_h) // 2
    crop = frame[y0:y0 + crop_h, x0:x0 + crop_w]
    return crop, (x0, y0, crop_w, crop_h)


def expand_roi_16_9(selection, margin: float):
    """Expand a tight upper-body selection like the training crop."""
    x, y, w, h = (float(value) for value in selection)
    if w <= 0 or h <= 0:
        raise ValueError("ROI width and height must be positive")

    centre_x = x + w * 0.5
    centre_y = y + h * 0.5
    w *= 1.0 + 2.0 * margin
    h *= 1.0 + 2.0 * margin
    target = INPUT_W / float(INPUT_H)
    if w / h < target:
        w = h * target
    else:
        h = w / target
    return centre_x - w * 0.5, centre_y - h * 0.5, w, h


def crop_with_padding(frame: np.ndarray, box):
    """Crop a possibly out-of-frame box, matching PIL's black padding."""
    x, y, w, h = box
    x0, y0 = int(round(x)), int(round(y))
    x1, y1 = int(round(x + w)), int(round(y + h))
    crop_w = max(1, x1 - x0)
    crop_h = max(1, y1 - y0)
    crop = np.zeros((crop_h, crop_w, 3), dtype=frame.dtype)

    src_x0 = max(0, x0)
    src_y0 = max(0, y0)
    src_x1 = min(frame.shape[1], x1)
    src_y1 = min(frame.shape[0], y1)
    if src_x1 > src_x0 and src_y1 > src_y0:
        dst_x0 = src_x0 - x0
        dst_y0 = src_y0 - y0
        crop[
            dst_y0:dst_y0 + (src_y1 - src_y0),
            dst_x0:dst_x0 + (src_x1 - src_x0),
        ] = frame[src_y0:src_y1, src_x0:src_x1]
    return crop, (x0, y0, crop_w, crop_h)


def select_manual_roi(frame: np.ndarray, margin: float):
    window = "Select ROI: head + shoulders + elbows + wrists + hips"
    selection = cv2.selectROI(window, frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(window)
    if selection[2] <= 0 or selection[3] <= 0:
        return None
    return expand_roi_16_9(selection, margin)


def preprocess(crop_bgr: np.ndarray, device: torch.device):
    resized = cv2.resize(crop_bgr, (INPUT_W, INPUT_H), interpolation=cv2.INTER_NEAREST)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb).permute(2, 0, 1).contiguous().float()
    tensor = tensor / 127.5 - 1.0
    return tensor.unsqueeze(0).to(device)


def decode(logits: torch.Tensor):
    _, k, hh, hw = logits.shape
    flat = logits.reshape(1, k, -1)
    idx = flat.argmax(dim=2)[0]
    confidence = flat.softmax(dim=2).amax(dim=2)[0]
    xh = (idx % hw).float()
    yh = torch.div(idx, hw, rounding_mode="floor").float()
    x = xh * (INPUT_W / float(hw))
    y = yh * (INPUT_H / float(hh))
    return (
        torch.stack((x, y), dim=1).cpu().numpy(),
        confidence.cpu().numpy(),
    )


def decode_structured(
    baseline_logits: torch.Tensor,
    wrist_logits: torch.Tensor,
    ranker: WristCandidateRanker,
    previous_wrists: torch.Tensor | None,
    wrist_velocity: torch.Tensor | None,
    temporal_weight: float,
    identity_margin: float,
    wrist_identity_margin: float,
):
    candidates, features, anchors = build_wrist_candidates(
        baseline_logits, wrist_logits
    )
    scores = ranker(features)[0]
    if previous_wrists is not None:
        predicted = previous_wrists
        if wrist_velocity is not None:
            predicted = predicted + wrist_velocity
        shoulder_span = torch.linalg.vector_norm(
            anchors[0, 1] - anchors[0, 2]
        ).clamp_min(4.0)
        temporal_distance = torch.linalg.vector_norm(
            candidates[0] - predicted[:, None], dim=2
        ) / shoulder_span
        scores = scores - temporal_weight * temporal_distance.square().clamp_max(4.0)
    choice = scores.argmax(dim=1)
    selected = torch.gather(
        candidates[0], 1, choice[:, None, None].expand(-1, 1, 2)
    ).squeeze(1)
    points_heatmap = anchors[0].clone()
    points_heatmap[5:7] = selected
    points_heatmap, identity_swapped = correct_arm_identity(
        points_heatmap.unsqueeze(0), identity_margin, wrist_identity_margin
    )
    points_heatmap = points_heatmap[0]

    if previous_wrists is None:
        new_velocity = torch.zeros_like(selected)
    else:
        measured_velocity = selected - previous_wrists
        new_velocity = (
            measured_velocity
            if wrist_velocity is None
            else 0.65 * wrist_velocity + 0.35 * measured_velocity
        )

    hh, hw = baseline_logits.shape[-2:]
    points_input = points_heatmap.clone()
    points_input[:, 0] *= INPUT_W / float(hw)
    points_input[:, 1] *= INPUT_H / float(hh)
    base_confidence = baseline_logits.flatten(2).softmax(dim=2).amax(dim=2)[0]
    wrist_confidence = wrist_logits.flatten(2).softmax(dim=2).amax(dim=2)[0]
    base_confidence[5:7] = torch.maximum(
        base_confidence[5:7], wrist_confidence[5:7]
    )
    return (
        points_input.cpu().numpy(),
        base_confidence.cpu().numpy(),
        selected.detach(),
        new_velocity.detach(),
        tuple(bool(value) for value in identity_swapped[0].tolist()),
    )


def decode_arm_structured(
    baseline_logits: torch.Tensor,
    specialist_logits: torch.Tensor,
    ranker: ArmChainRanker,
    previous_arms: torch.Tensor | None,
    arm_velocity: torch.Tensor | None,
    temporal_weight: float,
    min_forearm_ratio: float,
    down_pose_weight: float,
):
    chains, features, anchors = build_arm_chains(
        baseline_logits, specialist_logits
    )
    scores = ranker(features)[0]
    candidates = chains[0]
    shoulder_span = torch.linalg.vector_norm(
        anchors[0, 1] - anchors[0, 2]
    ).clamp_min(4.0)

    adjusted, forearm_ratio, down_activation = apply_arm_pose_priors(
        scores.unsqueeze(0),
        chains,
        anchors,
        min_forearm_ratio=min_forearm_ratio,
        down_pose_weight=down_pose_weight,
    )
    scores = adjusted[0]

    if previous_arms is not None:
        predicted = previous_arms
        if arm_velocity is not None:
            velocity_length = torch.linalg.vector_norm(
                arm_velocity, dim=2, keepdim=True
            ).clamp_min(1e-6)
            clipped_velocity = arm_velocity * torch.clamp(
                0.35 * shoulder_span / velocity_length, max=1.0
            )
            predicted = predicted + clipped_velocity
        temporal_distance = torch.linalg.vector_norm(
            candidates - predicted[:, None], dim=3
        ) / shoulder_span
        scores = scores - temporal_weight * temporal_distance.square().sum(dim=2).clamp_max(6.0)

    # Select both sides jointly so they cannot collapse onto the same elbow.
    pair_score = scores[0, :, None] + scores[1, None, :]
    elbow_separation = torch.linalg.vector_norm(
        candidates[0, :, None, 0] - candidates[1, None, :, 0], dim=2
    ) / shoulder_span
    pair_score = pair_score - 10.0 * torch.relu(0.18 - elbow_separation)
    flat_choice = pair_score.argmax()
    right_count = pair_score.shape[1]
    choices = torch.stack(
        (torch.div(flat_choice, right_count, rounding_mode="floor"), flat_choice % right_count)
    )
    selected = torch.stack(
        (candidates[0, choices[0]], candidates[1, choices[1]]), dim=0
    )

    if previous_arms is None:
        new_velocity = torch.zeros_like(selected)
    else:
        measured_velocity = selected - previous_arms
        new_velocity = (
            measured_velocity
            if arm_velocity is None
            else 0.65 * arm_velocity + 0.35 * measured_velocity
        )
        velocity_length = torch.linalg.vector_norm(
            new_velocity, dim=2, keepdim=True
        ).clamp_min(1e-6)
        new_velocity = new_velocity * torch.clamp(
            0.35 * shoulder_span / velocity_length, max=1.0
        )

    points_heatmap = anchors[0].clone()
    points_heatmap[3] = selected[0, 0]
    points_heatmap[5] = selected[0, 1]
    points_heatmap[4] = selected[1, 0]
    points_heatmap[6] = selected[1, 1]
    hh, hw = baseline_logits.shape[-2:]
    points_input = points_heatmap.clone()
    points_input[:, 0] *= INPUT_W / float(hw)
    points_input[:, 1] *= INPUT_H / float(hh)
    base_confidence = baseline_logits.flatten(2).softmax(dim=2).amax(dim=2)[0]
    specialist_confidence = specialist_logits.flatten(2).softmax(dim=2).amax(dim=2)[0]
    base_confidence[5:7] = torch.maximum(
        base_confidence[5:7], specialist_confidence[5:7]
    )
    return (
        points_input.cpu().numpy(),
        base_confidence.cpu().numpy(),
        selected.detach(),
        new_velocity.detach(),
        forearm_ratio[0, torch.arange(2, device=choices.device), choices].detach(),
        bool(down_activation[0, 0, 0].item() > 0.0),
    )


def stabilize_pose(current: np.ndarray, previous: np.ndarray | None):
    """Reject isolated torso jumps while keeping wrist motion responsive."""
    if previous is None:
        return current.copy()
    torso_scale = max(float(np.linalg.norm(current[1] - current[2])), 24.0)
    displacement = np.linalg.norm(current - previous, axis=1) / torso_scale
    alpha = np.full(9, 0.58, dtype=np.float32)
    alpha[3:7] = 0.72
    # A shoulder/head/hip cannot teleport by this much in one 30 FPS frame.
    stable_joint = np.array([True, True, True, False, False, False, False, True, True])
    alpha[stable_joint & (displacement > 0.35)] = 0.16
    alpha[5:7][displacement[5:7] > 1.0] = 0.42
    return previous + alpha[:, None] * (current - previous)


def map_to_frame(points_input: np.ndarray, box):
    x0, y0, cw, ch = box
    out = np.empty_like(points_input, dtype=np.float32)
    out[:, 0] = x0 + points_input[:, 0] * cw / INPUT_W
    out[:, 1] = y0 + points_input[:, 1] * ch / INPUT_H
    return out


def draw_pose(
    frame: np.ndarray,
    points: np.ndarray,
    confidence: np.ndarray,
    min_confidence: float,
):
    pts = [(int(round(x)), int(round(y))) for x, y in points]

    for a, b in SKELETON:
        if confidence[a] >= min_confidence and confidence[b] >= min_confidence:
            cv2.line(frame, pts[a], pts[b], (255, 255, 255), 2, cv2.LINE_AA)

    for i, (x, y) in enumerate(pts):
        if confidence[i] < min_confidence:
            continue
        cv2.circle(frame, (x, y), 5, POINT_COLORS[i], -1, cv2.LINE_AA)
        cv2.putText(
            frame, f"{i}:{confidence[i]:.2f}", (x + 6, y - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            POINT_COLORS[i], 1, cv2.LINE_AA
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", required=True)
    parser.add_argument(
        "--wrist-weights",
        help="Optional wrist-specialized V2 model used only for wrist candidate peaks.",
    )
    parser.add_argument(
        "--wrist-decoder",
        help="Structured wrist candidate ranker checkpoint.",
    )
    parser.add_argument(
        "--arm-decoder",
        help="Structured shoulder-elbow-wrist chain ranker checkpoint.",
    )
    parser.add_argument("--temporal-weight", type=float, default=0.45)
    parser.add_argument("--min-forearm-ratio", type=float, default=0.45)
    parser.add_argument("--down-pose-weight", type=float, default=0.5)
    parser.add_argument(
        "--identity-margin",
        type=float,
        default=0.75,
        help="Minimum opposite-shoulder advantage before swapping complete arms.",
    )
    parser.add_argument(
        "--wrist-identity-margin",
        type=float,
        default=2.0,
        help="Conservative threshold for an independent left/right wrist swap.",
    )
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument(
        "--manual-roi",
        action="store_true",
        help="Select a tight upper-body box before inference; press R to reselect.",
    )
    parser.add_argument("--roi-margin", type=float, default=0.28)
    parser.add_argument("--min-confidence", type=float, default=0.0)
    args = parser.parse_args()

    device = torch.device(
        "cpu" if args.cpu or not torch.cuda.is_available() else "cuda"
    )

    checkpoint = torch.load(args.weights, map_location=device, weights_only=True)
    architecture = checkpoint.get("architecture", "v2")
    if architecture != "v2":
        raise ValueError(f"Expected v2 checkpoint, got {architecture!r}")

    model = make_pose_model("v2").to(device)
    model.load_state_dict(checkpoint["model"])
    model.eval()

    if args.wrist_decoder and args.arm_decoder:
        raise ValueError("use either --wrist-decoder or --arm-decoder, not both")
    if bool(args.wrist_weights) != bool(args.wrist_decoder or args.arm_decoder):
        raise ValueError(
            "--wrist-weights must be paired with --wrist-decoder or --arm-decoder"
        )
    wrist_model = None
    wrist_ranker = None
    arm_ranker = None
    if args.wrist_weights:
        wrist_checkpoint = torch.load(
            args.wrist_weights, map_location=device, weights_only=True
        )
        wrist_model = make_pose_model("v2").to(device)
        wrist_model.load_state_dict(wrist_checkpoint["model"])
        wrist_model.eval()
        decoder_path = args.arm_decoder or args.wrist_decoder
        decoder_checkpoint = torch.load(
            decoder_path, map_location=device, weights_only=True
        )
        if args.arm_decoder:
            arm_ranker = ArmChainRanker(decoder_checkpoint["feature_count"]).to(device)
            arm_ranker.load_state_dict(decoder_checkpoint["model"])
            arm_ranker.eval()
        else:
            wrist_ranker = WristCandidateRanker(
                decoder_checkpoint["feature_count"]
            ).to(device)
            wrist_ranker.load_state_dict(decoder_checkpoint["model"])
            wrist_ranker.eval()

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(args.camera)

    if not cap.isOpened():
        raise RuntimeError(
            f"Cannot open camera {args.camera}. Try --camera 1."
        )

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    print(f"Device: {device}")
    print("Press Q or ESC to quit.")
    print("Press R to select/reselect a tight upper-body ROI.")

    fps = None
    last = time.perf_counter()
    manual_box = None
    previous_wrists = None
    wrist_velocity = None
    filtered_points = None
    identity_swapped = (False, False)
    previous_arms = None
    arm_velocity = None
    selected_forearm_ratio = None
    down_pose_guard = False

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if args.manual_roi and manual_box is None:
                manual_box = select_manual_roi(frame, args.roi_margin)

            if manual_box is None:
                crop, box = center_crop_16_9(frame)
                roi_mode = "FULL FRAME"
            else:
                crop, box = crop_with_padding(frame, manual_box)
                roi_mode = "MANUAL ROI"
            tensor = preprocess(crop, device)

            t0 = time.perf_counter()
            with torch.no_grad():
                logits = model(tensor)
                if wrist_model is not None:
                    wrist_logits = wrist_model(tensor)
                    if arm_ranker is not None:
                        (
                            points,
                            confidence,
                            previous_arms,
                            arm_velocity,
                            selected_forearm_ratio,
                            down_pose_guard,
                        ) = decode_arm_structured(
                            logits,
                            wrist_logits,
                            arm_ranker,
                            previous_arms,
                            arm_velocity,
                            args.temporal_weight,
                            args.min_forearm_ratio,
                            args.down_pose_weight,
                        )
                    else:
                        (
                            points,
                            confidence,
                            previous_wrists,
                            wrist_velocity,
                            identity_swapped,
                        ) = decode_structured(
                            logits,
                            wrist_logits,
                            wrist_ranker,
                            previous_wrists,
                            wrist_velocity,
                            args.temporal_weight,
                            args.identity_margin,
                            args.wrist_identity_margin,
                        )
                else:
                    points, confidence = decode(logits)
            if device.type == "cuda":
                torch.cuda.synchronize()
            infer_ms = (time.perf_counter() - t0) * 1000.0

            points = map_to_frame(points, box)
            filtered_points = stabilize_pose(points, filtered_points)
            points = filtered_points

            display = frame.copy()
            x0, y0, cw, ch = box
            cv2.rectangle(
                display,
                (x0, y0),
                (x0 + cw - 1, y0 + ch - 1),
                (128, 128, 128),
                1,
            )

            draw_pose(display, points, confidence, args.min_confidence)

            now = time.perf_counter()
            inst = 1.0 / max(now - last, 1e-9)
            last = now
            fps = inst if fps is None else 0.9 * fps + 0.1 * inst

            if arm_ranker is not None:
                decoder_mode = "ARM-CHAIN"
                if down_pose_guard:
                    decoder_mode += "+DOWN"
                ratio_text = "/".join(f"{value:.2f}" for value in selected_forearm_ratio.tolist())
                decoder_mode += f" F:{ratio_text}"
            else:
                decoder_mode = "STRUCTURED" if wrist_ranker is not None else "ARGMAX"
            if any(identity_swapped):
                corrected_pairs = "".join(
                    name for name, active in zip(("E", "W"), identity_swapped) if active
                )
                decoder_mode += f"+ARM-ID:{corrected_pairs}"
            cv2.putText(
                display,
                f"{roi_mode} | {decoder_mode} | {device} | FPS {fps:.1f} | infer {infer_ms:.2f} ms | conf {confidence.mean():.3f}",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("Upper Pose V2 - Webcam Test", display)

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
                selected = select_manual_roi(frame, args.roi_margin)
                if selected is not None:
                    manual_box = selected
                    previous_wrists = None
                    wrist_velocity = None
                    previous_arms = None
                    arm_velocity = None
                    filtered_points = None
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
