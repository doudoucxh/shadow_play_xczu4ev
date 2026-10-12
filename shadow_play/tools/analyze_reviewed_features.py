#!/usr/bin/env python3
"""Offline image-texture displacement diagnostic; no hardware or motor output.

Uses manually named image features, not verified puppet joint coordinates.
Each reviewed path is compared with its own BEFORE image. No millimeter
conversion, inverse controller, or automatic replay permission is produced.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def match(template, image, xy, radius=8, search=24):
    x, y = xy
    region = image[y-radius-search:y+radius+search+1,
                   x-radius-search:x+radius+search+1]
    if region.shape != (2*(radius+search)+1,)*2:
        raise ValueError('Feature search region crosses the image edge')
    windows = np.lib.stride_tricks.sliding_window_view(region, template.shape)
    centered = windows-windows.mean(axis=(-1, -2), keepdims=True)
    target = template-template.mean()
    norm = float(np.sqrt(np.sum(target*target)))
    if norm < 1e-6:
        raise ValueError('Flat template is not trackable')
    score = np.sum(centered*target, axis=(-1, -2))/(np.sqrt(
        np.sum(centered*centered, axis=(-1, -2)))*norm+1e-8)
    iy, ix = np.unravel_index(np.argmax(score), score.shape)
    quality = float(score[iy, ix])
    boundary = abs(ix-search) == search or abs(iy-search) == search
    return {'dx': int(ix-search), 'dy': int(iy-search),
            'ncc': round(quality, 4), 'search_boundary_reached': bool(boundary),
            'usable_texture_match': quality >= .85 and not boundary}


def analyze(selection, seeds):
    paths = [Path(row['file']) for row in selection['views']['front']['frames']]
    # selection.json paths are filenames relative to the private session root.
    images = [np.asarray(Image.open(seeds['root']/p).convert('L'), dtype=float)
              for p in paths]
    if any(im.shape != (360, 640) for im in images):
        raise ValueError('This seed file requires the reviewed 640x360 front view')
    result = {}
    for label, xy in seeds['features'].items():
        x, y = xy
        template = images[0][y-8:y+9, x-8:x+9]
        result[label] = {'seed_pixel': xy,
                         'peak': match(template, images[1], xy),
                         'return': match(template, images[2], xy)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seed_file', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    seed = json.loads(args.seed_file.read_text(encoding='utf-8-sig'))
    records = []
    for item in seed['selections']:
        selection = json.loads(Path(item).read_text(encoding='utf-8-sig'))
        root = Path(item).parent.parent
        records.append({'selection': item, 'axis': selection['axis'],
                        'offset_us': selection['offset_us'],
                        'features': analyze(selection, {'root': root,
                                            'features': seed['features']})})
    output = {'schema_version': 1, 'method': '17x17 normalized texture correlation, +/-24 pixel search',
              'image_size': [640, 360], 'feature_points_are_verified_joints': False,
              'metric_coordinates_calibrated': False, 'automatic_motion_allowed': False,
              'limitations': ['Texture matches can follow shadows, deformation or nearby similar patterns',
                              'Low quality or boundary matches must not be used as joint displacement',
                              'Pixel shifts do not establish millimeter mapping or a simultaneous-axis envelope'],
              'records': records}
    args.output.write_text(json.dumps(output, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'records': len(records), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
