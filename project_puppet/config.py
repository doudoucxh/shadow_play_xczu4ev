"""Shared constants for the upper-body pose pipeline."""

INPUT_WIDTH = 256
INPUT_HEIGHT = 144
HEATMAP_WIDTH = 64
HEATMAP_HEIGHT = 36
HEATMAP_STRIDE = 4

# The order is also the output-channel order of the network.
KEYPOINT_NAMES = (
    "head",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
)

LEFT_RIGHT_PAIRS = (
    (1, 2),
    (3, 4),
    (5, 6),
    (7, 8),
)

# Live preprocessing in pose_preprocess_axis.v:
# 1024x600 -> crop [0, 1024) x [12, 588) -> nearest-neighbour / 4.
CAMERA_ROI_X = 0
CAMERA_ROI_Y = 12
CAMERA_SCALE = 4
