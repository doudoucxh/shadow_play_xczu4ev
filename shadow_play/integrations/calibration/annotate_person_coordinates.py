"""Convert reviewed per-frame pixel annotations into normalized curtain points.

Offline only. No motion, no reuse of an old camera homography. Input annotations
must name real rod attachment centres, not the head silhouette or shoulder.
"""
import argparse
import copy
import json
from pathlib import Path
import numpy as np

RODS = ('wusong_left', 'wusong_neck', 'wusong_right')


def normalize(corners, points):
    corners = np.asarray(corners, dtype=float)
    if corners.shape != (4, 2) or not np.isfinite(corners).all():
        raise ValueError('four finite corners required: bottom-left, bottom-right, top-right, top-left')
    edges = np.roll(corners, -1, axis=0) - corners
    crosses = edges[:, 0]*np.roll(edges[:, 1], -1) - edges[:, 1]*np.roll(edges[:, 0], -1)
    if not (np.all(crosses > 1e-6) or np.all(crosses < -1e-6)):
        raise ValueError('corners must form a convex non-degenerate quadrilateral')
    matrix, target = [], []
    for (x, y), (u, v) in zip(corners, ((0,0), (1,0), (1,1), (0,1))):
        matrix += [[x,y,1,0,0,0,-u*x,-u*y], [0,0,0,x,y,1,-v*x,-v*y]]
        target += [u,v]
    h = np.append(np.linalg.solve(matrix, target), 1).reshape(3,3)
    result = {}
    for rod in RODS:
        point = points.get(rod)
        if point is None:
            result[rod] = None
            continue
        p = np.asarray(point, dtype=float)
        if p.shape != (2,) or not np.isfinite(p).all():
            raise ValueError('invalid pixel point: ' + rod)
        q = h @ np.append(p, 1)
        if abs(q[2]) < 1e-9:
            raise ValueError('point near projective infinity')
        q = q[:2]/q[2]
        if not np.isfinite(q).all() or np.any(q < -1e-8) or np.any(q > 1+1e-8):
            raise ValueError('point outside curtain; do not clamp observations')
        result[rod] = np.clip(q, 0, 1).tolist()
    return result


def annotate(dataset, annotations):
    result = copy.deepcopy(dataset)
    samples = {s['sample_id']: s for s in result['samples']}
    if len(samples) != len(result['samples']):
        raise ValueError('duplicate sample IDs')
    seen = set()
    for item in annotations:
        key = item['sample_id']
        if key not in samples or key in seen:
            raise ValueError('unknown or duplicate annotation sample ID')
        seen.add(key)
        sample = samples[key]
        # Bind clicks to the specific evidence file, not merely the sample label.
        if item.get('front_file') != sample['evidence']['front_file'] or not item.get('front_file'):
            raise ValueError('annotation evidence does not match sample')
        sample['points'] = normalize(item['corners_px'], item['points_px'])
        sample['pixel_annotation'] = copy.deepcopy(item)
        sample['annotation_verified'] = item.get('annotation_verified') is True
        # Pixel annotation does not establish command/frame timing or assembly context.
    result['deployment_ready'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('annotations', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = annotate(json.loads(args.dataset.read_text(encoding='utf-8-sig')),
                      json.loads(args.annotations.read_text(encoding='utf-8-sig')))
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
