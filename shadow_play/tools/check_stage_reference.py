#!/usr/bin/env python3
"""Compare four fixed image anchors; saved-image diagnostic, never a motion gate.

Requires NumPy and Pillow. No camera, serial, network, board or motor interface.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


def match_anchor(reference, current, pixel, patch_radius=7, search_radius=10):
    x, y = (int(round(float(v))) for v in pixel)
    margin = patch_radius + search_radius
    height, width = reference.shape
    if not (margin <= x < width-margin and margin <= y < height-margin):
        raise ValueError('Reference marker too near image edge for the search window')
    patch = reference[y-patch_radius:y+patch_radius+1, x-patch_radius:x+patch_radius+1]
    patch = patch-patch.mean()
    norm = float(np.linalg.norm(patch))
    if norm < 1e-6:
        raise ValueError('Reference marker has no measurable image contrast')
    best = (-2.0, 0, 0)
    for dy in range(-search_radius, search_radius+1):
        for dx in range(-search_radius, search_radius+1):
            candidate = current[y+dy-patch_radius:y+dy+patch_radius+1,
                                x+dx-patch_radius:x+dx+patch_radius+1]
            candidate = candidate-candidate.mean()
            denominator = norm*float(np.linalg.norm(candidate))
            score = float(np.sum(patch*candidate)/denominator) if denominator > 1e-9 else -1.0
            if score > best[0]:
                best = score, dx, dy
    score, dx, dy = best
    return {'reference_pixel': [x, y], 'matched_pixel': [x+dx, y+dy],
            'shift_px': [dx, dy], 'distance_px': math.hypot(dx, dy), 'ncc': score}


def compare(spec, reference, current, *, min_ncc=0.90, max_shift_px=2.0):
    if reference.ndim != 2 or current.shape != reference.shape:
        raise ValueError('Reference and current grayscale image dimensions must match')
    if list(reference.shape[::-1]) != [spec['image_width'], spec['image_height']]:
        raise ValueError('Image dimensions do not match the geometry reference')
    points = np.asarray(spec['reference_pixels'], dtype=float)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError('Four finite image reference points required')
    results = [match_anchor(reference, current, point) for point in points]
    for label, result in zip(('LL', 'LR', 'UR', 'UL'), results):
        result['label'] = label
        result['within_diagnostic_tolerance'] = result['ncc'] >= min_ncc and result['distance_px'] <= max_shift_px
    return {
        'method': '15x15 grayscale NCC patches, integer translation within +/-10 pixels',
        'anchors': results,
        'thresholds': {'min_ncc': min_ncc, 'max_shift_px': max_shift_px},
        'same_view_candidate': all(r['within_diagnostic_tolerance'] for r in results),
        'metric_accuracy_verified': False, 'actual_servo_position_known': False,
        'motion_permission': False,
        'limitations': ['Checks selected image patches only; visual review still required.',
                       'Does not verify camera freshness, physical marker placement, rod position or joint angle.',
                       'Thresholds are diagnostic tolerances, not validated mechanical safety limits.']
    }


def load_gray(path):
    with Image.open(path) as frame:
        return np.array(frame.convert('L'), dtype=float)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('geometry', type=Path)
    parser.add_argument('reference_image', type=Path)
    parser.add_argument('current_image', type=Path)
    parser.add_argument('new_report', type=Path)
    args = parser.parse_args()
    spec = json.loads(args.geometry.read_text(encoding='utf-8'))
    reference_hash = hashlib.sha256(args.reference_image.read_bytes()).hexdigest()
    expected = spec.get('reference_selection', {}).get('reference_frame_sha256')
    if not expected or reference_hash != expected:
        raise ValueError('Reference image hash does not match the recorded geometry')
    report = compare(spec, load_gray(args.reference_image), load_gray(args.current_image))
    report['reference_image_sha256'] = reference_hash
    report['current_image_sha256'] = hashlib.sha256(args.current_image.read_bytes()).hexdigest()
    with args.new_report.open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
    print(json.dumps(report))
    return 0 if report['same_view_candidate'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
