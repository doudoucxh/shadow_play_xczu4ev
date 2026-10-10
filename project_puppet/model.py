"""Quantisation-friendly tiny upper-body pose network."""

from __future__ import annotations

try:
    import torch
    from torch import nn
except ImportError as exc:  # Keep the error actionable when tools inspect this file.
    raise ImportError(
        "pose_model.model requires PyTorch; install pose_model/requirements.txt"
    ) from exc


class ConvBnRelu(nn.Sequential):
    def __init__(self, in_channels: int, out_channels: int, kernel: int, stride: int = 1):
        padding = kernel // 2
        super().__init__(
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel,
                stride=stride,
                padding=padding,
                bias=False,
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=False),
        )


class DepthwiseSeparable(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, stride: int = 1):
        super().__init__()
        self.use_residual = stride == 1 and in_channels == out_channels
        self.depthwise = nn.Sequential(
            nn.Conv2d(
                in_channels,
                in_channels,
                3,
                stride=stride,
                padding=1,
                groups=in_channels,
                bias=False,
            ),
            nn.BatchNorm2d(in_channels),
            nn.ReLU(inplace=False),
        )
        self.pointwise = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=False),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.pointwise(self.depthwise(x))
        return y + x if self.use_residual else y


class TinyUpperPoseNet(nn.Module):
    """256x144 RGB input -> 9x36x64 heatmap logits.

    The low-resolution context branch costs few MACs. Its nearest-neighbour
    upsample and add operations map directly to simple PL streaming hardware.
    """

    def __init__(self, keypoints: int = 9):
        super().__init__()
        self.stem = ConvBnRelu(3, 16, 3, stride=2)       # 128 x 72
        self.high = DepthwiseSeparable(16, 24, stride=2) # 64 x 36
        self.low = nn.Sequential(
            DepthwiseSeparable(24, 32, stride=2),        # 32 x 18
            DepthwiseSeparable(32, 32),
            DepthwiseSeparable(32, 32),
        )
        self.context_projection = nn.Sequential(
            nn.Conv2d(32, 24, 1, bias=False),
            nn.BatchNorm2d(24),
            nn.ReLU(inplace=False),
        )
        self.refine = nn.Sequential(
            DepthwiseSeparable(24, 24),
            DepthwiseSeparable(24, 24),
        )
        self.head = nn.Conv2d(24, keypoints, 1, bias=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        high = self.high(self.stem(x))
        context = self.context_projection(self.low(high))
        context = torch.nn.functional.interpolate(context, scale_factor=2, mode="nearest")
        return self.head(self.refine(high + context))


class TinyUpperPoseNetV2(nn.Module):
    """Higher-capacity FPGA-friendly network for reliable left/right limbs.

    It retains only 3x3 depthwise and 1x1 pointwise convolutions after the
    stem.  Wider features and extra 64x36 refinement blocks improve spatial
    identity while keeping the design suitable for an INT8 streaming engine.
    """

    def __init__(self, keypoints: int = 9):
        super().__init__()
        self.stem = ConvBnRelu(3, 24, 3, stride=2)
        self.high = DepthwiseSeparable(24, 32, stride=2)
        self.high_refine = nn.Sequential(
            DepthwiseSeparable(32, 32),
            DepthwiseSeparable(32, 32),
        )
        self.low = nn.Sequential(
            DepthwiseSeparable(32, 48, stride=2),
            DepthwiseSeparable(48, 48),
            DepthwiseSeparable(48, 48),
            DepthwiseSeparable(48, 48),
        )
        self.context_projection = nn.Sequential(
            nn.Conv2d(48, 32, 1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=False),
        )
        self.refine = nn.Sequential(
            DepthwiseSeparable(32, 32),
            DepthwiseSeparable(32, 32),
            DepthwiseSeparable(32, 32),
        )
        self.head = nn.Conv2d(32, keypoints, 1, bias=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        high = self.high_refine(self.high(self.stem(x)))
        context = self.context_projection(self.low(high))
        context = torch.nn.functional.interpolate(context, scale_factor=2, mode="nearest")
        return self.head(self.refine(high + context))


def make_pose_model(architecture: str = "v1", keypoints: int = 9) -> nn.Module:
    if architecture == "v1":
        return TinyUpperPoseNet(keypoints)
    if architecture == "v2":
        return TinyUpperPoseNetV2(keypoints)
    raise ValueError(f"unknown pose architecture: {architecture}")


if __name__ == "__main__":
    sample = torch.zeros(1, 3, 144, 256)
    for architecture in ("v1", "v2"):
        network = make_pose_model(architecture).eval()
        with torch.no_grad():
            output = network(sample)
        parameters = sum(p.numel() for p in network.parameters())
        print(f"architecture={architecture}, output={tuple(output.shape)}, parameters={parameters}")
