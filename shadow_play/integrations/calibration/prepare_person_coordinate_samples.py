"""Index historical command/frame pairs for annotation; never contacts hardware.

Historical command records are candidates, not measured shaft positions or
time-aligned observations. Missing points and unverified context stay explicit.
"""
import argparse
import json
from pathlib import Path
import numpy as np

RODS = ('wusong_left', 'wusong_neck', 'wusong_right')


def prepare(records, evidence_root):
    index = {}
    for path in evidence_root.rglob('*.jpg'):
        index.setdefault(path.name, []).append(path)
    samples = []
    for path in records:
        record = json.loads(path.read_text(encoding='utf-8-sig'))
        for i, phase in enumerate(record.get('phases', []) + record.get('checkpoints', [])):
            pulses = phase.get('command_pulses_us')
            if not isinstance(pulses, list) or len(pulses) != 10:
                raise ValueError('expected ten recorded commands: {} phase {}'.format(path, i))
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and
                       np.isfinite(v) and 500 <= v <= 2500 for v in pulses):
                raise ValueError('invalid command values')
            frames = phase.get('frame_evidence', phase.get('frames', {}))
            evidence = {}
            for view in ('front', 'top'):
                frame = frames.get(view, {})
                matches = index.get(frame.get('file'), [])
                # A duplicate filename is not silently assigned to an arbitrary session.
                evidence[view + '_file'] = str(matches[0].resolve()) if len(matches) == 1 else None
                evidence[view + '_metadata'] = frame
                evidence[view + '_match_count'] = len(matches)
            samples.append({
                'sample_id': '{}:{}'.format(path.stem, i),
                'source_record': str(path.resolve()),
                'source_phase': phase.get('label', phase.get('event')),
                'command_us': pulses[:6], 'other_command_us': pulses[6:],
                'points': {rod: None for rod in RODS},
                'evidence': evidence,
                'annotation_verified': False,
                'command_frame_pair_verified': False,
                'actual_axis_feedback': None,
            })
    if not samples:
        raise ValueError('no command/frame candidates')
    commands = np.unique(np.array([s['command_us'] for s in samples], float), axis=0)
    centered = commands - commands.mean(axis=0)
    return {
        'version': 1, 'type': 'historical_person_coordinate_candidates',
        'simulation_only': False, 'context_verified': False,
        'geometry_id': 'UNVERIFIED-historical-rod-assembly',
        'camera_id': 'UNVERIFIED-historical-front-view',
        'coordinate_system': 'normalized_curtain',
        'coordinate_convention': 'x audience right, y up; [0,1] in the curtain plane',
        'deployment_ready': False, 'samples': samples,
        'coverage': {
            'candidate_count': len(samples),
            'distinct_command_groups': len(commands),
            'centered_command_rank': int(np.linalg.matrix_rank(centered)),
            'command_min_us': commands.min(axis=0).tolist(),
            'command_max_us': commands.max(axis=0).tolist(),
            'resolved_dual_frame_count': sum(bool(s['evidence']['front_file'] and
                                                   s['evidence']['top_file']) for s in samples),
            'verified_three_point_samples': 0,
        },
        'limitations': [
            'Command rank alone does not establish spatial coverage or an inverse model.',
            'Verify assembly, camera framing and command/frame timing before fitting.',
            'Annotate actual rod attachment centres; leave occluded points null.',
            'Do not use an old curtain homography after camera movement.',
            'Normalized curtain coordinates are planar projections, not 3D rod positions.',
            'Historical command extrema are not validated loaded motion limits.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('records', nargs='+', type=Path)
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    dataset = prepare(args.records, args.evidence_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(dataset, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dataset['coverage'], ensure_ascii=False))


if __name__ == '__main__':
    main()
