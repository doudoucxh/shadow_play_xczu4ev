"""Convert approved SHADOW annotations to nine-point YOLO without GT cropping."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
from PIL import Image

NAMES = ['head', 'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
         'left_wrist', 'right_wrist', 'left_hip', 'right_hip']


def prepare(source, output):
    output.mkdir(parents=True, exist_ok=True)
    inputs = {'train': 'Data_005_video_review/Data_005_combined_train.json',
              'val': 'Data_005_video_review/Data_004_validation_remapped.json',
              'test': 'Data_005_video_review/Data_005_video03_validation.json'}
    report = {'splits': {}, 'policy': 'Preserve supplied splits; video03 is test only.',
              'keypoints': NAMES, 'preprocessing': 'Full image; RGB; no ground-truth crop.',
              'annotations': {}, 'duplicates_removed': []}
    records, owners = {}, {}
    # Held-out data take precedence if a duplicate occurs.
    for split in ('test', 'val', 'train'):
        annotation = source / inputs[split]
        data = json.loads(annotation.read_text(encoding='utf-8'))
        assert data['schema'] == 'shadow_pose_review_v1'
        assert data['keypoint_names'] == NAMES
        if split == 'train' and not data.get('training_allowed'):
            raise ValueError('Training annotation is not approved')
        report['annotations'][split] = {'path': str(annotation),
            'sha256': hashlib.sha256(annotation.read_bytes()).hexdigest()}
        records[split] = []
        for item in data['images']:
            if item.get('review_status') != 'approved':
                continue
            path = source / item['file_name'].replace('\\', '/')
            with Image.open(path) as im:
                im = im.convert('RGB')
                width, height = im.size
                # Pixel identity also detects identical images in different encodings.
                digest = hashlib.sha256(f'{width},{height}:'.encode() + im.tobytes()).hexdigest()
                if digest in owners:
                    report['duplicates_removed'].append({'file': str(path), 'split': split,
                                                         'kept_in': owners[digest]})
                    continue
                owners[digest] = split
                if (width, height) != (item['width'], item['height']):
                    raise ValueError(f'Image dimensions disagree: {path}')
                points = item['points']
                if [p['name'] for p in points] != NAMES:
                    raise ValueError(f'Wrong keypoint order: {path}')
                visible = []
                triples = []
                for p in points:
                    v, x, y = int(p['v']), float(p['x']), float(p['y'])
                    if v not in (0, 1, 2):
                        raise ValueError(f'Invalid visibility: {path}')
                    if v and not (0 <= x <= width and 0 <= y <= height):
                        raise ValueError(f'Visible keypoint outside image: {path}, {p}')
                    triples.extend([x / width, y / height, v] if v else [0, 0, 0])
                    if v:
                        visible.append((x, y))
                if not visible:
                    raise ValueError(f'No labeled points: {path}')
                x1, y1, x2, y2 = map(float, item['bbox_xyxy'])
                # Detector proposals can exclude manually corrected wrists.
                x1 = max(0, min(x1, min(x for x, _ in visible) - 2))
                y1 = max(0, min(y1, min(y for _, y in visible) - 2))
                x2 = min(width, max(x2, max(x for x, _ in visible) + 2))
                y2 = min(height, max(y2, max(y for _, y in visible) + 2))
                if x2 <= x1 or y2 <= y1:
                    raise ValueError(f'Invalid box: {path}')
                stem = digest[:24]
                image_out = output / 'images' / split / f'{stem}.png'
                label_out = output / 'labels' / split / f'{stem}.txt'
                image_out.parent.mkdir(parents=True, exist_ok=True)
                label_out.parent.mkdir(parents=True, exist_ok=True)
                im.save(image_out, compress_level=1)
                row = [0, (x1+x2)/2/width, (y1+y2)/2/height,
                       (x2-x1)/width, (y2-y1)/height] + triples
                label_out.write_text(' '.join(f'{x:.8g}' for x in row) + '\n')
                records[split].append({'file': str(image_out.resolve()), 'source': str(path),
                    'pixel_sha256': digest, 'points': points, 'bbox_xyxy': [x1,y1,x2,y2],
                    'width': width, 'height': height})
        report['splits'][split] = {'count': len(records[split]),
            'point_reviewed': sum(p.get('reviewed', False) for r in records[split] for p in r['points']),
            'point_total': len(records[split])*9,
            'sources': dict(collections.Counter(Path(r['source']).parent.name for r in records[split]))}
    (output / 'records.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    yaml = f'path: {output.resolve().as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nkpt_shape: [9, 3]\nflip_idx: [0, 2, 1, 4, 3, 6, 5, 8, 7]\nnames: {{0: person}}\n'
    (output / 'data.yaml').write_text(yaml, encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, default=Path('D:/pytorch_work'))
    p.add_argument('--output', type=Path, default=Path(__file__).parent / 'dataset')
    a = p.parse_args()
    prepare(a.source, a.output)
