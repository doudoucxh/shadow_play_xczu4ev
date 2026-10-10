"""COCO person-keypoint dataset adapter for the project's nine points."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import torch
from PIL import Image, ImageEnhance
from torch.utils.data import Dataset

from .config import (
    HEATMAP_HEIGHT,
    HEATMAP_WIDTH,
    INPUT_HEIGHT,
    INPUT_WIDTH,
    LEFT_RIGHT_PAIRS,
)
from .geometry import coco_to_upper_body


def _upper_body_crop(points, fallback_bbox, margin=0.22):
    visible = [(x, y) for x, y, v in points if v > 0]
    if len(visible) >= 3:
        xs, ys = zip(*visible)
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
    else:
        left, top, width, height = fallback_bbox
        right, bottom = left + width, top + height

    width = max(32.0, right - left)
    height = max(32.0, bottom - top)
    centre_x = (left + right) * 0.5
    centre_y = (top + bottom) * 0.5
    width *= 1.0 + 2.0 * margin
    height *= 1.0 + 2.0 * margin

    target_aspect = INPUT_WIDTH / INPUT_HEIGHT
    if width / height < target_aspect:
        width = height * target_aspect
    else:
        height = width / target_aspect
    return centre_x - width / 2, centre_y - height / 2, width, height


def _make_heatmaps(points, sigma=1.5):
    ys = torch.arange(HEATMAP_HEIGHT, dtype=torch.float32).view(1, HEATMAP_HEIGHT, 1)
    xs = torch.arange(HEATMAP_WIDTH, dtype=torch.float32).view(1, 1, HEATMAP_WIDTH)
    heatmaps = []
    visibility = []
    for x, y, visible in points:
        if visible > 0 and 0 <= x < INPUT_WIDTH and 0 <= y < INPUT_HEIGHT:
            hx = x * HEATMAP_WIDTH / INPUT_WIDTH
            hy = y * HEATMAP_HEIGHT / INPUT_HEIGHT
            heatmaps.append(torch.exp(-((xs - hx) ** 2 + (ys - hy) ** 2) / (2 * sigma**2)))
            visibility.append(1.0)
        else:
            heatmaps.append(torch.zeros(1, HEATMAP_HEIGHT, HEATMAP_WIDTH))
            visibility.append(0.0)
    return torch.cat(heatmaps, dim=0), torch.tensor(visibility, dtype=torch.float32)


class CocoUpperBodyDataset(Dataset):
    def __init__(self, image_dir, annotation_file, training=True, limit=None):
        self.image_dir = Path(image_dir)
        self.training = training
        with open(annotation_file, "r", encoding="utf-8") as handle:
            coco = json.load(handle)
        images = {item["id"]: item for item in coco["images"]}
        self.samples = []
        for annotation in coco["annotations"]:
            if annotation.get("category_id") != 1 or annotation.get("num_keypoints", 0) < 5:
                continue
            image = images.get(annotation["image_id"])
            if image is not None:
                self.samples.append((image["file_name"], annotation))
        if limit is not None and len(self.samples) > limit:
            self.samples = random.Random(20260908).sample(self.samples, limit)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        file_name, annotation = self.samples[index]
        image = Image.open(self.image_dir / file_name).convert("RGB")
        points = coco_to_upper_body(annotation["keypoints"])
        margin = random.uniform(0.18, 0.38) if self.training else 0.28
        crop_x, crop_y, crop_w, crop_h = _upper_body_crop(points, annotation["bbox"], margin=margin)
        if self.training:
            crop_x += random.uniform(-0.06, 0.06) * crop_w
            crop_y += random.uniform(-0.06, 0.06) * crop_h
        image = image.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
        image = image.resize((INPUT_WIDTH, INPUT_HEIGHT), Image.Resampling.BILINEAR)

        if self.training:
            image = ImageEnhance.Brightness(image).enhance(random.uniform(0.75, 1.25))
            image = ImageEnhance.Contrast(image).enhance(random.uniform(0.80, 1.20))

        mapped = []
        for x, y, visible in points:
            mapped.append(
                (
                    (x - crop_x) * INPUT_WIDTH / crop_w,
                    (y - crop_y) * INPUT_HEIGHT / crop_h,
                    visible,
                )
            )

        if self.training and random.random() < 0.5:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            mapped = [(INPUT_WIDTH - 1 - x, y, v) for x, y, v in mapped]
            mapped = list(mapped)
            for left, right in LEFT_RIGHT_PAIRS:
                mapped[left], mapped[right] = mapped[right], mapped[left]

        raw = torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8)
        tensor = raw.view(INPUT_HEIGHT, INPUT_WIDTH, 3).permute(2, 0, 1).float()
        tensor = tensor / 127.5 - 1.0
        heatmaps, visibility = _make_heatmaps(mapped)
        return tensor, heatmaps, visibility
