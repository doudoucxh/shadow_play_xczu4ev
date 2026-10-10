#!/usr/bin/env python3
"""Offline local fit: one rod, fixed other axes/slides, one curtain calibration.

Outputs an analysis model, never motor commands or production calibration.csv.
Requires numpy. Cross-validation leaves entire repeated-command groups out.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def features(values, degree):
    x, y = values[:, 0], values[:, 1]
    columns = [np.ones(len(x)), x, y]
    if degree == 2:
        columns += [x*x, x*y, y*y]
    return np.column_stack(columns)


def train(x, y, degree):
    center, scale = x.mean(axis=0), x.std(axis=0)
    require(np.all(scale > 1e-9), 'both input dimensions must vary')
    matrix = features((x-center)/scale, degree)
    require(np.linalg.matrix_rank(matrix) == matrix.shape[1], 'rank deficient grid; collect two-dimensional coverage')
    condition = float(np.linalg.cond(matrix))
    require(condition < 1e6, 'poorly conditioned samples; expand coverage')
    coef = np.linalg.lstsq(matrix, y, rcond=None)[0]
    return {'center': center.tolist(), 'scale': scale.tolist(), 'coefficients': coef.tolist(),
            'degree': degree, 'condition': condition}


def predict(model, x):
    return features((x-np.array(model['center']))/np.array(model['scale']), model['degree']) @ np.array(model['coefficients'])


def fit(session, rod, degree=1, allow_manual=False):
    config, meta = read(session/'config.snapshot.json'), read(session/'metadata.json')
    require(config.get('simulation_only') is False and meta.get('simulation_only') is False,
            'demo/simulation data cannot fit a real mechanism')
    require(meta.get('reference_view') == config.get('reference_view') in ('front', 'rear'), 'view mismatch')
    specs = config['axes']
    axes = [a for a in specs if a['rod'] == rod]
    require(len(axes) == 2, 'local tool requires exactly two configured axes for this rod')
    require(all(a['unit'] != 'demo' for a in specs+config['slides']), 'demo units are not real measurements')
    selected = []
    for line in (session/'samples.jsonl').read_text(encoding='utf-8').splitlines():
        item = json.loads(line)
        if item.get('rod') == rod:
            selected.append(item)
    require(bool(selected), 'no samples for selected rod')
    seen, contexts, xy, commands, ids = set(), set(), [], [], []
    for sample in selected:
        require(sample['sample_id'] not in seen, 'duplicate sample ID')
        seen.add(sample['sample_id'])
        require(sample['session_id'] == meta['session_id'], 'session mismatch')
        require(sample.get('reference_view', config['reference_view']) == config['reference_view'], 'sample view mismatch')
        state = sample['state']
        require(state['accepted'] is True, 'unaccepted sample')
        require((state['backend'] == 'external' and state['confirmed'] is True) or
                (allow_manual and state['backend'] == 'manual_unconfirmed' and state['confirmed'] is False),
                'only external confirmed data accepted; audited hand entries require --allow-manual')
        values = {a['axis_id']: a for a in state['axes']}
        require(len(values) == len(state['axes']) and set(values) == {a['id'] for a in specs}, 'axis set mismatch')
        for axis in specs:
            value = values[axis['id']]
            require(value['unit'] == axis['unit'] and np.isfinite(value['value']) and
                    axis['min'] <= value['value'] <= axis['max'], 'axis value/unit invalid')
        slide_values = {s['id']: s for s in state['slides']}
        require(len(slide_values) == len(state['slides']) and set(slide_values) == {s['id'] for s in config['slides']}, 'slide set mismatch')
        for slide in config['slides']:
            value = slide_values[slide['id']]
            require(value['unit'] == slide['unit'] and value['state_kind'] == slide['state_kind'] and
                    np.isfinite(value['value']), 'slide value/unit/state mismatch')
        context = {'calibration_id': sample['calibration_id'],
                   'other_axes': sorted((k, v['value'], v['unit']) for k, v in values.items() if k not in {a['id'] for a in axes}),
                   'slides': sorted((k, v['value'], v['unit'], v['state_kind']) for k,v in slide_values.items())}
        contexts.add(json.dumps(context, sort_keys=True))
        frame = (session/sample['frame_path']).resolve()
        require(session.resolve() in frame.parents and frame.is_file(), 'missing/invalid evidence frame')
        point = [sample['stage_mm']['x'], sample['stage_mm']['y']]
        require(np.all(np.isfinite(point)) and 0 <= point[0] <= config['stage']['width_mm'] and
                0 <= point[1] <= config['stage']['height_mm'], 'point outside effective curtain')
        xy.append(point)
        commands.append([values[a['id']]['value'] for a in axes])
        ids.append(sample['sample_id'])
    require(len(contexts) == 1, 'other axes, slides or curtain calibration changed; collect a separate fixed-condition session')
    context = json.loads(next(iter(contexts)))
    calibration_name = context['calibration_id']
    require(isinstance(calibration_name, str) and Path(calibration_name).name == calibration_name,
            'invalid calibration ID')
    calibration = read(session/(calibration_name+'.json'))
    require(calibration['reference_view'] == config['reference_view'], 'calibration view mismatch')
    xy, commands = np.array(xy, dtype=float), np.array(commands, dtype=float)
    groups = sorted(set(map(tuple, commands.tolist())))
    require(len(groups) >= (12 if degree == 1 else 20), 'collect at least 12 (linear) or 20 (quadratic) distinct command pairs')
    inv_error, fwd_error = np.empty_like(commands), np.empty_like(xy)
    repeat_spreads = []
    for pair in groups:
        held = np.all(commands == pair, axis=1)
        inv_error[held] = predict(train(xy[~held], commands[~held], degree), xy[held])-commands[held]
        fwd_error[held] = predict(train(commands[~held], xy[~held], degree), commands[held])-xy[held]
        if held.sum() > 1:
            repeat_spreads.append(float(np.max(np.linalg.norm(xy[held]-xy[held].mean(axis=0), axis=1))))
    distance = np.linalg.norm(fwd_error, axis=1)
    return {
        'version': 1, 'type': 'offline_local_fit', 'deployment_ready': False,
        'reference_view': config['reference_view'], 'stage': config['stage'], 'rod': rod,
        'source_session': meta['session_id'], 'source_sample_ids': ids, 'fixed_context': context,
        'axes': [{'id': a['id'], 'unit': a['unit'], 'min': a['min'], 'max': a['max']} for a in axes],
        'sample_count': len(xy), 'distinct_command_pairs': len(groups),
        'contains_manual_entries': any(s['state']['backend'] == 'manual_unconfirmed' for s in selected),
        'feature_order': ['1', 'u', 'v'] + (['u*u', 'u*v', 'v*v'] if degree == 2 else []),
        'inverse_xy_mm_to_commands': train(xy, commands, degree),
        'forward_commands_to_xy_mm': train(commands, xy, degree),
        'validation': {'method': 'leave_one_entire_command_pair_out',
            'inverse_rmse_per_axis_in_command_units': np.sqrt(np.mean(inv_error**2, axis=0)).tolist(),
            'forward_rmse_mm': float(np.sqrt(np.mean(distance**2))),
            'forward_max_error_mm': float(distance.max()),
            'repeated_command_group_count': len(repeat_spreads),
            'max_repeat_deviation_from_group_mean_mm': max(repeat_spreads) if repeat_spreads else None},
        'observed_xy_mm': xy.tolist(), 'observed_commands': commands.tolist(),
        'limitations': ['Only the recorded fixed context is modeled; no extrapolation or full-puppet IK.',
            'Forward CV error is model prediction error, NOT a physical target-tracking acceptance test.',
            'Perform independent low-speed point tests and coupled-motion validation before deployment.',
            'Existing C++ motion_mapper does not consume this JSON; runtime integration is a separate task.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('--rod', required=True)
    parser.add_argument('--degree', type=int, choices=(1, 2), default=1)
    parser.add_argument('--allow-manual', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = fit(args.session, args.rod, args.degree, args.allow_manual)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(report, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    print(json.dumps(report['validation'], ensure_ascii=False, indent=2))
    print('Offline analysis saved to {}; deployment_ready=false'.format(args.output))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        sys.exit(str(error))
