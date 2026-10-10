"""Structured shoulder-elbow-wrist chain decoding."""

from __future__ import annotations

import torch
from torch import nn

from .wrist_decoder import argmax_xy, local_topk


class ArmChainRanker(nn.Module):
    """Rank complete elbow/wrist chains for an anatomical side."""

    def __init__(self, feature_count: int = 32):
        super().__init__()
        self.feature_count = feature_count
        self.network = nn.Sequential(
            nn.Linear(feature_count, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features).squeeze(-1)


def _standardize(logits):
    flat = logits.flatten(2)
    return ((flat - flat.mean(dim=2, keepdim=True)) / flat.std(
        dim=2, keepdim=True
    ).clamp_min(1e-4)).reshape_as(logits)


def _gather(maps, points):
    batch, channels, _, width = maps.shape
    index = points[..., 1].long() * width + points[..., 0].long()
    values = torch.gather(
        maps.flatten(2), 2, index[:, None].expand(-1, channels, -1)
    )
    return values.permute(0, 2, 1)


def build_arm_chains(baseline_logits, specialist_logits, peaks_per_channel=3):
    """Return Bx2x72 chain candidates, features, and baseline anchors."""
    _, elbow_peaks = local_topk(baseline_logits[:, 3:5], peaks_per_channel)
    _, base_wrist_peaks = local_topk(
        baseline_logits[:, 5:7], peaks_per_channel
    )
    _, specialist_wrist_peaks = local_topk(
        specialist_logits[:, 5:7], peaks_per_channel
    )
    elbow_pool = elbow_peaks.flatten(1, 2)
    wrist_pool = torch.cat(
        (base_wrist_peaks.flatten(1, 2), specialist_wrist_peaks.flatten(1, 2)),
        dim=1,
    )
    elbow_count = elbow_pool.shape[1]
    wrist_count = wrist_pool.shape[1]
    elbows = elbow_pool[:, :, None, :].expand(-1, -1, wrist_count, -1)
    wrists = wrist_pool[:, None, :, :].expand(-1, elbow_count, -1, -1)
    chains = torch.stack((elbows, wrists), dim=3).flatten(1, 2)

    anchors = argmax_xy(baseline_logits)
    body_scale = torch.linalg.vector_norm(
        anchors[:, 1] - anchors[:, 2], dim=1
    ).clamp_min(4.0)
    height, width = baseline_logits.shape[-2:]
    base_elbow_z = _standardize(baseline_logits[:, 3:5])
    specialist_elbow_z = _standardize(specialist_logits[:, 3:5])
    base_wrist_z = _standardize(baseline_logits[:, 5:7])
    specialist_wrist_z = _standardize(specialist_logits[:, 5:7])

    feature_sides = []
    for side, (shoulder, other_shoulder) in enumerate(((1, 2), (2, 1))):
        elbow = chains[:, :, 0]
        wrist = chains[:, :, 1]
        own_shoulder = anchors[:, shoulder, None]
        other = anchors[:, other_shoulder, None]
        scale = body_scale[:, None, None]
        upper_vector = (elbow - own_shoulder) / scale
        fore_vector = (wrist - elbow) / scale
        full_vector = (wrist - own_shoulder) / scale
        upper_length = torch.linalg.vector_norm(upper_vector, dim=2)
        fore_length = torch.linalg.vector_norm(fore_vector, dim=2)
        full_length = torch.linalg.vector_norm(full_vector, dim=2)
        ratio = fore_length / upper_length.clamp_min(0.05)
        other_distance = torch.linalg.vector_norm(elbow - other, dim=2) / body_scale[:, None]
        angle = (upper_vector * fore_vector).sum(dim=2) / (
            upper_length * fore_length
        ).clamp_min(0.01)
        coordinate = torch.cat(
            (
                elbow / elbow.new_tensor((max(width - 1, 1), max(height - 1, 1))),
                wrist / wrist.new_tensor((max(width - 1, 1), max(height - 1, 1))),
            ),
            dim=2,
        )
        lengths = torch.stack(
            (upper_length, fore_length, ratio, full_length, other_distance, angle),
            dim=2,
        )
        elbow_evidence = torch.cat(
            (_gather(base_elbow_z, elbow), _gather(specialist_elbow_z, elbow)),
            dim=2,
        )
        wrist_evidence = torch.cat(
            (_gather(base_wrist_z, wrist), _gather(specialist_wrist_z, wrist)),
            dim=2,
        )
        evidence_delta = torch.stack(
            (
                elbow_evidence[..., side] - elbow_evidence[..., 1 - side],
                elbow_evidence[..., 2 + side] - elbow_evidence[..., 3 - side],
                wrist_evidence[..., side] - wrist_evidence[..., 1 - side],
                wrist_evidence[..., 2 + side] - wrist_evidence[..., 3 - side],
            ),
            dim=2,
        )

        elbow_source_channel = torch.arange(
            2, device=chains.device, dtype=chains.dtype
        ).repeat_interleave(peaks_per_channel)
        elbow_own_source = (elbow_source_channel == side).to(chains.dtype)
        elbow_own_source = elbow_own_source[:, None].expand(-1, wrist_count).reshape(-1)
        elbow_own_source = elbow_own_source[None, :, None].expand(chains.shape[0], -1, -1)

        wrist_source_model = torch.arange(
            2, device=chains.device, dtype=chains.dtype
        ).repeat_interleave(2 * peaks_per_channel)
        wrist_source_channel = torch.arange(
            2, device=chains.device, dtype=chains.dtype
        ).repeat_interleave(peaks_per_channel).repeat(2)
        wrist_source_model = wrist_source_model[None].expand(elbow_count, -1).reshape(-1)
        wrist_own_source = (wrist_source_channel == side).to(chains.dtype)
        wrist_own_source = wrist_own_source[None].expand(elbow_count, -1).reshape(-1)
        sources = torch.stack(
            (elbow_own_source[0, :, 0], wrist_source_model, wrist_own_source), dim=1
        )[None].expand(chains.shape[0], -1, -1)
        side_feature = chains.new_full(
            (chains.shape[0], chains.shape[1], 1), float(side)
        )
        features = torch.cat(
            (
                coordinate,
                upper_vector,
                fore_vector,
                full_vector,
                lengths,
                elbow_evidence,
                wrist_evidence,
                evidence_delta,
                sources,
                side_feature,
            ),
            dim=2,
        )
        feature_sides.append(features)
    return chains[:, None].expand(-1, 2, -1, -1, -1), torch.stack(
        feature_sides, dim=1
    ), anchors


def apply_arm_pose_priors(
    scores,
    chains,
    anchors,
    min_forearm_ratio=0.45,
    down_pose_weight=2.0,
):
    """Apply conservative anatomical priors to candidate-chain scores."""
    shoulder = torch.stack((anchors[:, 1], anchors[:, 2]), dim=1)
    hip = torch.stack((anchors[:, 7], anchors[:, 8]), dim=1)
    body_scale = torch.linalg.vector_norm(
        anchors[:, 1] - anchors[:, 2], dim=1
    ).clamp_min(4.0)
    elbow = chains[..., 0, :]
    wrist = chains[..., 1, :]
    upper_vector = elbow - shoulder[:, :, None]
    fore_vector = wrist - elbow
    upper_length = torch.linalg.vector_norm(upper_vector, dim=3).clamp_min(1.0)
    fore_length = torch.linalg.vector_norm(fore_vector, dim=3).clamp_min(1.0)
    forearm_ratio = fore_length / upper_length
    adjusted = scores - 8.0 * torch.relu(min_forearm_ratio - forearm_ratio)
    adjusted = adjusted - 2.0 * torch.relu(forearm_ratio - 1.9)

    baseline_upper = torch.stack(
        (anchors[:, 3] - anchors[:, 1], anchors[:, 4] - anchors[:, 2]), dim=1
    )
    baseline_downness = baseline_upper[..., 1] / torch.linalg.vector_norm(
        baseline_upper, dim=2
    ).clamp_min(1.0)
    # Activate only when both independently decoded upper arms indicate the
    # characteristic relaxed, near-vertical pose.  Candidate-specific gating
    # can accidentally reward a bad downward elbow in unrelated poses.
    relaxed_down = baseline_downness.amin(dim=1)
    down_activation = ((relaxed_down - 0.72) / 0.16).clamp(0.0, 1.0)
    down_activation = down_activation[:, None, None]
    hip_distance = torch.linalg.vector_norm(
        wrist - hip[:, :, None], dim=3
    ) / body_scale[:, None, None]
    down_penalty = 4.0 * torch.relu(hip_distance - 1.10)
    adjusted = adjusted - down_pose_weight * down_activation * down_penalty
    return adjusted, forearm_ratio, down_activation


def decode_arm_chains(baseline_logits, specialist_logits, ranker):
    chains, features, anchors = build_arm_chains(
        baseline_logits, specialist_logits
    )
    scores = ranker(features)
    choice = scores.argmax(dim=2)
    selected = torch.gather(
        chains,
        2,
        choice[:, :, None, None, None].expand(-1, -1, 1, 2, 2),
    ).squeeze(2)
    points = anchors.clone()
    points[:, 3] = selected[:, 0, 0]
    points[:, 5] = selected[:, 0, 1]
    points[:, 4] = selected[:, 1, 0]
    points[:, 6] = selected[:, 1, 1]
    return points, scores, chains
