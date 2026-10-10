"""Model-input orientation and explicit mapping back to raw camera pixels."""
import cv2
import numpy as np

INPUT_ROTATION = 180

def orient_frame(frame, rotation=INPUT_ROTATION):
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 0:
        return frame
    raise ValueError('Only 0 or 180 degree rotation is supported')

def keypoints_to_camera(points, width, height, rotation=INPUT_ROTATION):
    """Preserve keypoint IDs/confidence; transform pixel centers, not body sides."""
    result = np.asarray(points).copy()
    if rotation == 180:
        result[..., 0] = width - 1 - result[..., 0]
        result[..., 1] = height - 1 - result[..., 1]
    elif rotation != 0:
        raise ValueError('Only 0 or 180 degree rotation is supported')
    return result
