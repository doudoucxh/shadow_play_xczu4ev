"""Structured wrist candidate decoding shared by training and webcam inference."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


WRIST_CHANNELS = (5, 6)
SIDE_ANCHORS = ((1, 3, 2, 4), (2, 4, 1, 3))


class WristCandidateRanker(nn.Module):
    """Score wrist heatmap peaks using appearance and arm geometry."""

    def __init__(self, feature_count: int = 21):
        super().__init__()
        self.feature_count = feature_count
        self.network = nn.Sequential(
            nn.Linear(feature_count, 48),
            nn.ReLU(),
            nn.Linear(48, 24),
            nn.ReLU(),
            nn.Linear(24, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features).squeeze(-1)


def argmax_xy(logits: torch.Tensor) -> torch.Tensor:
    width = logits.shape[-1]
    index = logits.flatten(2).argmax(dim=2)
    return torch.stack((index % width, index // width), dim=-1).float()


def local_topk(logits: torch.Tensor, k: int = 3):
    """Return spatially distinct local maxima for each heatmap channel."""
    pooled = F.max_pool2d(logits, kernel_size=5, stride=1, padding=2)
    peaks = logits.masked_fill(logits < pooled, float("-inf"))
    values, indices = peaks.flatten(2).topk(k, dim=2)
    width = logits.shape[-1]
    points = torch.stack((indices % width, indices // width), dim=-1).float()
    return values, points


def _standardize_heatmaps(logits: torch.Tensor) -> torch.Tensor:
    flat = logits.flatten(2)
    mean = flat.mean(dim=2, keepdim=True)
    std = flat.std(dim=2, keepdim=True).clamp_min(1e-4)
    return ((flat - mean) / std).reshape_as(logits)


def _gather_maps(maps: torch.Tensor, points: torch.Tensor) -> torch.Tensor:
    """Gather C heatmaps at SxK points -> BxSxKxC."""
    batch, channels, _, width = maps.shape
    index = (points[..., 1].long() * width + points[..., 0].long())
    flat = maps.flatten(2)
    expanded = flat[:, None, :, :].expand(-1, points.shape[1], -1, -1)
    gather_index = index[:, :, None, :].expand(-1, -1, channels, -1)
    values = torch.gather(expanded, 3, gather_index)
    return values.permute(0, 1, 3, 2)


def build_wrist_candidates(
    baseline_logits: torch.Tensor,
    wrist_logits: torch.Tensor,
    peaks_per_model: int = 3,
):
    """Build candidate locations and ranker features for both wrists."""
    _, base_points = local_topk(
        baseline_logits[:, WRIST_CHANNELS], peaks_per_model
    )
    _, wrist_points = local_topk(
        wrist_logits[:, WRIST_CHANNELS], peaks_per_model
    )
    candidates = torch.cat((base_points, wrist_points), dim=2)
    batch, sides, candidate_count, _ = candidates.shape
    height, width = baseline_logits.shape[-2:]

    base_z = _standardize_heatmaps(baseline_logits[:, WRIST_CHANNELS])
    wrist_z = _standardize_heatmaps(wrist_logits[:, WRIST_CHANNELS])
    evidence = torch.cat(
        (_gather_maps(base_z, candidates), _gather_maps(wrist_z, candidates)),
        dim=3,
    )
    anchors = argmax_xy(baseline_logits)
    body_scale = torch.linalg.vector_norm(
        anchors[:, 1] - anchors[:, 2], dim=1
    ).clamp_min(4.0)
    body_center = (anchors[:, 1] + anchors[:, 2]) * 0.5

    feature_sides = []
    for side, (own_shoulder, own_elbow, other_shoulder, other_elbow) in enumerate(
        SIDE_ANCHORS
    ):
        point = candidates[:, side]
        own_s = anchors[:, own_shoulder, None]
        own_e = anchors[:, own_elbow, None]
        other_s = anchors[:, other_shoulder, None]
        other_e = anchors[:, other_elbow, None]
        scale = body_scale[:, None, None]
        upper = torch.linalg.vector_norm(own_e - own_s, dim=2).clamp_min(1.0)
        fore = torch.linalg.vector_norm(point - own_e, dim=2)

        coordinate = torch.stack(
            (point[..., 0] / max(width - 1, 1), point[..., 1] / max(height - 1, 1)),
            dim=2,
        )
        own_elbow_vector = (point - own_e) / scale
        own_shoulder_vector = (point - own_s) / scale
        other_elbow_vector = (point - other_e) / scale
        center_vector = (point - body_center[:, None]) / scale
        length_features = torch.stack(
            (
                fore / upper,
                fore / body_scale[:, None],
                torch.linalg.vector_norm(point - other_e, dim=2) / body_scale[:, None],
                torch.linalg.vector_norm(point - other_s, dim=2) / body_scale[:, None],
            ),
            dim=2,
        )
        side_evidence = evidence[:, side]
        evidence_delta = torch.stack(
            (
                side_evidence[..., side] - side_evidence[..., 1 - side],
                side_evidence[..., 2 + side] - side_evidence[..., 3 - side],
            ),
            dim=2,
        )
        source = point.new_zeros(batch, candidate_count, 1)
        source[:, peaks_per_model:] = 1.0
        side_value = point.new_full((batch, candidate_count, 1), float(side))
        features = torch.cat(
            (
                coordinate,
                own_elbow_vector,
                own_shoulder_vector,
                other_elbow_vector,
                center_vector,
                length_features,
                side_evidence,
                evidence_delta,
                source,
                side_value,
            ),
            dim=2,
        )
        feature_sides.append(features)
    return candidates, torch.stack(feature_sides, dim=1), anchors


def decode_wrists(
    baseline_logits: torch.Tensor,
    wrist_logits: torch.Tensor,
    ranker: WristCandidateRanker,
    peaks_per_model: int = 3,
):
    candidates, features, anchors = build_wrist_candidates(
        baseline_logits, wrist_logits, peaks_per_model
    )
    scores = ranker(features)
    choice = scores.argmax(dim=2)
    selected = torch.gather(
        candidates, 2, choice[:, :, None, None].expand(-1, -1, 1, 2)
    ).squeeze(2)
    points = anchors.clone()
    points[:, 5:7] = selected
    return points, scores, candidates


def correct_arm_identity(
    points: torch.Tensor,
    elbow_margin: float = 0.75,
    wrist_margin: float = 2.0,
):
    """Correct elbow and wrist identities independently from limb geometry.

    The live model can swap only the elbow channels while both wrists remain
    correct, so the two joint pairs must not be exchanged as one rigid arm.
    Elbows are first assigned to shoulders, then wrists are assigned to the
    corrected elbows.  A conservative margin preserves genuine arm crossing.
    """
    corrected = points.clone()
    shoulder_span = torch.linalg.vector_norm(
        points[:, 1] - points[:, 2], dim=1
    ).clamp_min(1.0)
    normal = (
        torch.linalg.vector_norm(points[:, 1] - points[:, 3], dim=1)
        + torch.linalg.vector_norm(points[:, 2] - points[:, 4], dim=1)
    )
    swapped = (
        torch.linalg.vector_norm(points[:, 1] - points[:, 4], dim=1)
        + torch.linalg.vector_norm(points[:, 2] - points[:, 3], dim=1)
    )
    elbow_swap = swapped + elbow_margin * shoulder_span < normal
    if elbow_swap.any():
        left_value = corrected[elbow_swap, 3].clone()
        corrected[elbow_swap, 3] = corrected[elbow_swap, 4]
        corrected[elbow_swap, 4] = left_value

    normal_wrist = (
        torch.linalg.vector_norm(corrected[:, 3] - corrected[:, 5], dim=1)
        + torch.linalg.vector_norm(corrected[:, 4] - corrected[:, 6], dim=1)
    )
    swapped_wrist = (
        torch.linalg.vector_norm(corrected[:, 3] - corrected[:, 6], dim=1)
        + torch.linalg.vector_norm(corrected[:, 4] - corrected[:, 5], dim=1)
    )
    wrist_swap = swapped_wrist + wrist_margin * shoulder_span < normal_wrist
    if wrist_swap.any():
        left_value = corrected[wrist_swap, 5].clone()
        corrected[wrist_swap, 5] = corrected[wrist_swap, 6]
        corrected[wrist_swap, 6] = left_value
    return corrected, torch.stack((elbow_swap, wrist_swap), dim=1)
