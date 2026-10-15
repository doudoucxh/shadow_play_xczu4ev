#!/usr/bin/env python3
"""Fit coupled three-point/six-command linear candidates, strictly offline.

Coordinates are normalized curtain x-right/y-up, not measured servo angles.
Run: python fit_person_coordinates.py dataset.json --output new-report.json
"""
import argparse
import json
from numbers import Real
from pathlib import Path
import sys

import numpy as np


POINT_NAMES = ('wusong_left', 'wusong_neck', 'wusong_right')
CONDITION_LIMIT = 1e6


def require(ok, message):
    if not ok:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def vector(value, size, label):
    require(isinstance(value, (list, tuple)) and len(value) == size,
            label + ' must contain {} numbers'.format(size))
    require(all(isinstance(v, Real) and not isinstance(v, bool) and np.isfinite(v)
                for v in value), label + ' must contain finite numbers')
    return list(map(float, value))


def train(x, y):
    """Normalized affine least squares with six independent input dimensions."""
    center, scale = x.mean(axis=0), x.std(axis=0)
    require(np.all(scale > 1e-9), 'rank deficient: all six input dimensions must vary')
    matrix = np.column_stack((np.ones(len(x)), (x - center) / scale))
    require(np.linalg.matrix_rank(matrix) == 7, 'rank deficient six-dimensional design')
    condition = float(np.linalg.cond(matrix))
    require(condition < CONDITION_LIMIT, 'poorly conditioned six-dimensional design')
    return dict(center=center.tolist(), scale=scale.tolist(),
                coefficients=np.linalg.lstsq(matrix, y, rcond=None)[0].tolist(),
                condition=condition, design_rank=7)


def predict(model, values):
    values = np.asarray(values, dtype=float)
    matrix = np.column_stack((np.ones(len(values)),
                              (values - model['center']) / model['scale']))
    return matrix @ np.asarray(model['coefficients'])


def fit(dataset):
    require(isinstance(dataset, dict), 'dataset must be an object')
    require(type(dataset.get('version')) is int and dataset['version'] == 1, 'version must be 1')
    for key in ('geometry_id', 'camera_id'):
        require(nonempty(dataset.get(key)), key + ' must be nonempty')
    require(dataset.get('coordinate_system') == 'normalized_curtain', 'coordinate_system mismatch')
    require(type(dataset.get('simulation_only')) is bool, 'simulation_only must be boolean')
    require(dataset.get('context_verified') is True, 'context_verified must be true')
    samples = dataset.get('samples')
    require(isinstance(samples, list), 'samples must be a list')
    seen, ids, commands, points, excluded = set(), [], [], [], []
    for sample in samples:
        require(isinstance(sample, dict), 'sample must be an object')
        sid = sample.get('sample_id')
        require(nonempty(sid) and sid not in seen, 'sample_id must be nonempty and unique')
        seen.add(sid)
        for key in ('geometry_id', 'camera_id', 'coordinate_system', 'simulation_only'):
            require(key not in sample or (type(sample[key]) is type(dataset[key]) and
                                         sample[key] == dataset[key]), 'sample ' + key + ' mismatch')
        command = vector(sample.get('command_us'), 6, 'command_us')
        raw = sample.get('points')
        require(isinstance(raw, dict) and set(raw) == set(POINT_NAMES), 'points must name all three control points')
        flat, missing = [], False
        for name in POINT_NAMES:
            if raw[name] is None:
                missing = True
            else:
                point = vector(raw[name], 2, name)
                require(all(0 <= v <= 1 for v in point), 'coordinates must be in 0..1')
                flat.extend(point)
        reasons = []
        if missing:
            reasons.append('missing_points')
        if sample.get('annotation_verified') is not True:
            reasons.append('annotation_unverified')
        if sample.get('command_frame_pair_verified') is not True:
            reasons.append('command_frame_pair_unverified')
        evidence = sample.get('evidence')
        if not isinstance(evidence, dict) or not all(nonempty(evidence.get(k)) for k in ('front_file', 'top_file')):
            reasons.append('missing_evidence_references')
        if reasons:
            excluded.append(dict(sample_id=sid, reasons=reasons))
            continue
        ids.append(sid)
        commands.append(command)
        points.append(flat)
    groups = sorted(set(map(tuple, commands)))
    require(len(groups) >= 14, 'need at least 14 distinct complete verified six-axis commands; excluded {} samples'.format(len(excluded)))
    commands, points = np.asarray(commands), np.asarray(points)
    forward, inverse = train(commands, points), train(points, commands)
    fwd_error, inv_error = np.empty_like(points), np.empty_like(commands)
    folds, spreads = [], []
    for group in groups:
        held = np.all(commands == group, axis=1)
        fwd_model = train(commands[~held], points[~held])
        inv_model = train(points[~held], commands[~held])
        fwd_error[held] = predict(fwd_model, commands[held]) - points[held]
        inv_error[held] = predict(inv_model, points[held]) - commands[held]
        folds.append(dict(held_sample_ids=[sid for sid, flag in zip(ids, held) if flag],
                          training_sample_count=int((~held).sum()),
                          forward_condition=fwd_model['condition'], inverse_condition=inv_model['condition']))
        if held.sum() > 1:
            deviation = (points[held] - points[held].mean(axis=0)).reshape(-1, 3, 2)
            spreads.append(dict(sample_ids=[sid for sid, flag in zip(ids, held) if flag],
                                max_distance_from_mean_per_point=np.linalg.norm(deviation, axis=2).max(axis=0).tolist()))
    distances = np.linalg.norm(fwd_error.reshape(-1, 3, 2), axis=2)
    return dict(version=1, type='offline_person_coupled_linear_fit', deployment_ready=False,
                simulation_only=dataset['simulation_only'], geometry_id=dataset['geometry_id'],
                camera_id=dataset['camera_id'], context_verified=True,
                coordinate_system='normalized_curtain', coordinate_convention='x_right_y_up',
                point_order=list(POINT_NAMES), command_axis_order=[1, 2, 3, 4, 5, 6],
                source_sample_ids=ids, sample_count=len(ids), distinct_command_count=len(groups),
                excluded_sample_count=len(excluded), excluded_samples=excluded,
                forward_commands_to_coordinates=forward, inverse_coordinates_to_commands=inverse,
                validation=dict(method='leave_one_entire_six_axis_command_group_out', folds=folds,
                    forward_rmse_per_point_normalized=np.sqrt(np.mean(distances**2, axis=0)).tolist(),
                    forward_max_error_per_point_normalized=distances.max(axis=0).tolist(),
                    inverse_rmse_per_axis_us=np.sqrt(np.mean(inv_error**2, axis=0)).tolist(),
                    inverse_max_error_per_axis_us=np.abs(inv_error).max(axis=0).tolist(),
                    repeated_command_group_count=len(spreads), repeated_command_spreads=spreads),
                limitations=['Offline linear candidate only; no motion commands or hardware access.',
                    'Simulation data do not validate the physical mechanism.',
                    'Evidence references and verification flags are assertions, not automatic frame verification.',
                    'Cross-validation is prediction error, not physical target-tracking or linkage-clearance approval.',
                    'Valid only for the recorded geometry and camera; no extrapolation, cold-start recovery or lock removal.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = fit(json.loads(args.dataset.read_text(encoding='utf-8-sig')))
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    print('Offline candidate saved; deployment_ready=false; simulation_only={}'.format(report['simulation_only']))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
