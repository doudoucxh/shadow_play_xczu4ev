"""Manual calibration records; this module never sends hardware commands.

Axes in ``bounds``/``axis_limits`` are servo1..servo10 (microseconds) and
rail1/rail2 (millimetres). A forbidden box is a conjunction of its dimensions;
the entire straight command segment is checked. Passing a check means only
that no *recorded* restriction was hit, never that the mechanism is safe.
OFF pulse history has no current-position meaning. ``manual_measured`` is an
explicit operator measurement, while an enabled command remains an estimate.
"""

import copy
import csv
import datetime as dt
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

AXES = tuple('servo%d' % i for i in range(1, 11)) + ('rail1', 'rail2')
RISKS = ('safe', 'near_danger', 'forbidden')
PROVENANCE = ('unknown', 'commanded_estimate', 'manual_measured', 'simulation_command')
RAIL_PROVENANCE = ('unknown', 'commanded_estimate', 'manual_measured', 'simulated')
SCHEMA_VERSION = 1


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('%s must be a finite number' % name)
    return value


def _string(value, name):
    if not isinstance(value, str):
        raise ValueError('%s must be text' % name)
    return value


def _keys(value, required, name):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError('%s has invalid fields' % name)


def _bounds(bounds):
    if not isinstance(bounds, dict) or not bounds or set(bounds) - set(AXES):
        raise ValueError('bounds must name at least one valid axis')
    for axis, pair in bounds.items():
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('bounds need [minimum, maximum]')
        lo, hi = (_number(v, axis) for v in pair)
        if lo > hi:
            raise ValueError('%s bounds are reversed' % axis)
        if axis.startswith('servo') and not 500 <= lo <= hi <= 2500:
            raise ValueError('servo bounds must be within 500..2500 us')


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def new_project(geometry_id=''):
    """Return an empty project. Geometry notes identify rod lengths/camera/setup.

    Rail ``drive_enabled`` defaults false: no rail transport is implemented by
    this data model. ``axis_limits`` are explicit opt-in observations, not
    automatically derived from samples.
    """
    _string(geometry_id, 'geometry_id')
    return {'schema_version': SCHEMA_VERSION, 'geometry_id': geometry_id,
            'geometry_notes': '',
            'rails': {a: {'drive_enabled': False, 'notes': ''} for a in ('rail1', 'rail2')},
            'axis_limits': {}, 'samples': [], 'forbidden_boxes': []}


def new_snapshot(pulse_us=None, enabled_mask=0, servo_provenance=None, rails=None):
    """Create a validated snapshot without inferring shaft feedback.

    Pulse history may be supplied even while OFF. Such entries default to
    ``unknown``; enabled entries default to ``commanded_estimate``. A caller
    must explicitly label actual operator measurements ``manual_measured``.
    Rails are dictionaries with position_mm, origin_known and position_kind.
    """
    pulses = list(pulse_us) if pulse_us is not None else [None] * 10
    if isinstance(enabled_mask, bool) or not isinstance(enabled_mask, int) or not 0 <= enabled_mask <= 1023:
        raise ValueError('enabled_mask must be an integer 0..1023')
    for pulse in pulses:
        if pulse is not None:
            _number(pulse, 'pulse_us')
    provenance = (list(servo_provenance) if servo_provenance is not None else
                  ['commanded_estimate' if enabled_mask & (1 << i) and p is not None
                   else 'unknown' for i, p in enumerate(pulses)])
    snapshot = {'pulse_us': pulses,
                'nominal_angle_deg': [None if p is None else (p - 500) * 270 / 2000 for p in pulses],
                'enabled_mask': enabled_mask, 'feedback': None,
                'servo_provenance': provenance,
                'rails': {a: {'position_mm': None, 'origin_known': False,
                              'position_kind': 'unknown'} for a in ('rail1', 'rail2')}}
    if rails is not None:
        if not isinstance(rails, dict) or set(rails) - {'rail1', 'rail2'}:
            raise ValueError('unknown rail')
        for axis, value in rails.items():
            snapshot['rails'][axis] = copy.deepcopy(value)
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot):
    """Raise ValueError for malformed data. No coercion of booleans/NaN/Infinity."""
    _keys(snapshot, ('pulse_us', 'nominal_angle_deg', 'enabled_mask', 'feedback',
                     'servo_provenance', 'rails'), 'snapshot')
    mask = snapshot['enabled_mask']
    if isinstance(mask, bool) or not isinstance(mask, int) or not 0 <= mask <= 1023:
        raise ValueError('enabled_mask must be an integer 0..1023')
    if snapshot['feedback'] is not None:
        raise ValueError('actual shaft feedback is unavailable and must be null')
    for field in ('pulse_us', 'nominal_angle_deg', 'servo_provenance'):
        if not isinstance(snapshot[field], list) or len(snapshot[field]) != 10:
            raise ValueError('%s must contain ten entries' % field)
    for i, pulse in enumerate(snapshot['pulse_us']):
        angle = snapshot['nominal_angle_deg'][i]
        kind = snapshot['servo_provenance'][i]
        if kind not in PROVENANCE:
            raise ValueError('invalid servo provenance')
        if pulse is None:
            if angle is not None or kind != 'unknown':
                raise ValueError('unknown pulse must have null angle and unknown provenance')
        else:
            if not 500 <= _number(pulse, 'pulse_us') <= 2500:
                raise ValueError('pulse_us outside 500..2500')
            _number(angle, 'nominal_angle_deg')
            if not math.isclose(angle, (pulse - 500) * 270 / 2000, abs_tol=1e-8):
                raise ValueError('nominal angle does not match pulse')
        if kind in ('commanded_estimate', 'simulation_command') and not mask & (1 << i):
            raise ValueError('OFF history cannot be a commanded current-position estimate')
    _keys(snapshot['rails'], ('rail1', 'rail2'), 'snapshot rails')
    for axis, rail in snapshot['rails'].items():
        _keys(rail, ('position_mm', 'origin_known', 'position_kind'), axis)
        if type(rail['origin_known']) is not bool or rail['position_kind'] not in RAIL_PROVENANCE:
            raise ValueError('invalid rail origin/provenance')
        pos = rail['position_mm']
        if pos is not None:
            _number(pos, axis)
        if rail['position_kind'] != 'unknown' and (pos is None or not rail['origin_known']):
            raise ValueError('known rail position needs a known origin and numeric position')
        if pos is None and rail['position_kind'] != 'unknown':
            raise ValueError('null rail position must be unknown')
    return snapshot


def axis_value(snapshot, axis):
    """Return usable command/measurement coordinate or None (never OFF history)."""
    if axis not in AXES:
        raise ValueError('unknown axis')
    if axis.startswith('servo'):
        i = int(axis[5:]) - 1
        kind = snapshot['servo_provenance'][i]
        if kind == 'manual_measured' or (kind in ('commanded_estimate', 'simulation_command') and snapshot['enabled_mask'] & (1 << i)):
            return snapshot['pulse_us'][i]
        return None
    rail = snapshot['rails'][axis]
    return rail['position_mm'] if rail['origin_known'] and rail['position_kind'] != 'unknown' else None


def record_sample(project, snapshot, label='', risk='safe', notes=''):
    """Append an observation and return it. A safe point grants no safe region."""
    validate_project(project)
    validate_snapshot(snapshot)
    if risk not in RISKS:
        raise ValueError('invalid risk label')
    sample = {'id': uuid.uuid4().hex, 'timestamp': _now(),
              'geometry_id': project['geometry_id'], 'label': _string(label, 'label'),
              'risk': risk, 'notes': _string(notes, 'notes'), 'snapshot': copy.deepcopy(snapshot)}
    project['samples'].append(sample)
    return sample


def add_zone(project, name, bounds, geometry_id=None):
    """Append an explicit forbidden conjunction; every listed dimension applies."""
    validate_project(project)
    _bounds(bounds)
    geometry = project['geometry_id'] if geometry_id is None else _string(geometry_id, 'geometry_id')
    if geometry != project['geometry_id']:
        raise ValueError('zone geometry differs from current project')
    zone = {'id': uuid.uuid4().hex, 'name': _string(name, 'name'),
            'geometry_id': geometry, 'bounds': {a: list(v) for a, v in bounds.items()}}
    project['forbidden_boxes'].append(zone)
    return zone


def set_axis_limit(project, axis, minimum, maximum, enabled=True):
    """Opt in to a manually specified one-axis interval. Does not certify coupling."""
    validate_project(project)
    _bounds({axis: [minimum, maximum]})
    if type(enabled) is not bool:
        raise ValueError('enabled must be boolean')
    project['axis_limits'][axis] = {'minimum': minimum, 'maximum': maximum,
                                   'enabled': enabled, 'geometry_id': project['geometry_id']}


def check_move(project, start, end):
    """Check a straight segment through all recorded forbidden closed boxes.

    Unknown coordinates required by any enabled limit or forbidden box block
    evaluation. This is conservative, even if another dimension lies outside.
    This checker cannot certify a curved motion, backlash, flex or unrecorded
    obstacles. Callers must not translate allowed=True into physical clearance.
    """
    validate_project(project)
    validate_snapshot(start)
    validate_snapshot(end)
    reasons, intersections = [], []
    for axis, limit in project['axis_limits'].items():
        if not limit['enabled']:
            continue
        if limit['geometry_id'] != project['geometry_id']:
            reasons.append('axis limit geometry mismatch: %s' % axis)
            continue
        a, b = axis_value(start, axis), axis_value(end, axis)
        if a is None or b is None:
            reasons.append('unknown coordinate for enabled limit: %s' % axis)
        elif min(a, b) < limit['minimum'] or max(a, b) > limit['maximum']:
            reasons.append('axis limit exceeded: %s' % axis)
    for zone in project['forbidden_boxes']:
        if zone['geometry_id'] != project['geometry_id']:
            reasons.append('forbidden zone geometry mismatch: %s' % zone['name'])
            continue
        missing = [a for a in zone['bounds'] if axis_value(start, a) is None or axis_value(end, a) is None]
        if missing:
            reasons.append('unknown coordinates for zone %s: %s' % (zone['name'], ', '.join(missing)))
            continue
        enter, leave = 0.0, 1.0
        for axis, (lo, hi) in zone['bounds'].items():
            a, b = axis_value(start, axis), axis_value(end, axis)
            # Scale before subtraction so finite extreme inputs cannot overflow
            # delta and accidentally turn a crossing into a missed interval.
            scale = max(abs(a), abs(b), abs(lo), abs(hi), 1.0)
            a, b, lo, hi = (v / scale for v in (a, b, lo, hi))
            delta = b - a
            if delta == 0:
                if not lo <= a <= hi:
                    enter, leave = 1.0, 0.0
                    break
            else:
                t0, t1 = (lo - a) / delta, (hi - a) / delta
                enter, leave = max(enter, min(t0, t1)), min(leave, max(t0, t1))
                if enter > leave:
                    break
        if enter <= leave:
            intersections.append(zone['name'])
            reasons.append('segment intersects forbidden zone: %s' % zone['name'])
    return {'allowed': not reasons, 'reasons': reasons, 'intersections': intersections,
            'clearance_certified': False}


def validate_project(project):
    """Validate the complete persisted schema, including every archived sample."""
    _keys(project, ('schema_version', 'geometry_id', 'geometry_notes', 'rails',
                    'axis_limits', 'samples', 'forbidden_boxes'), 'project')
    if type(project['schema_version']) is not int or project['schema_version'] != SCHEMA_VERSION:
        raise ValueError('unsupported schema version')
    _string(project['geometry_id'], 'geometry_id')
    _string(project['geometry_notes'], 'geometry_notes')
    _keys(project['rails'], ('rail1', 'rail2'), 'rail configuration')
    for rail in project['rails'].values():
        _keys(rail, ('drive_enabled', 'notes'), 'rail configuration')
        if type(rail['drive_enabled']) is not bool:
            raise ValueError('drive_enabled must be boolean')
        _string(rail['notes'], 'rail notes')
    if not isinstance(project['axis_limits'], dict) or set(project['axis_limits']) - set(AXES):
        raise ValueError('invalid axis limits')
    for axis, limit in project['axis_limits'].items():
        _keys(limit, ('minimum', 'maximum', 'enabled', 'geometry_id'), 'axis limit')
        _bounds({axis: [limit['minimum'], limit['maximum']]})
        if type(limit['enabled']) is not bool:
            raise ValueError('enabled must be boolean')
        _string(limit['geometry_id'], 'geometry_id')
    for field in ('samples', 'forbidden_boxes'):
        if not isinstance(project[field], list):
            raise ValueError('%s must be a list' % field)
    ids = set()
    for sample in project['samples']:
        _keys(sample, ('id', 'timestamp', 'geometry_id', 'label', 'risk', 'notes', 'snapshot'), 'sample')
        for field in ('id', 'timestamp', 'geometry_id', 'label', 'risk', 'notes'):
            _string(sample[field], field)
        if sample['id'] in ids or sample['risk'] not in RISKS:
            raise ValueError('duplicate id or invalid sample risk')
        ids.add(sample['id'])
        validate_snapshot(sample['snapshot'])
    for zone in project['forbidden_boxes']:
        _keys(zone, ('id', 'name', 'geometry_id', 'bounds'), 'forbidden box')
        for field in ('id', 'name', 'geometry_id'):
            _string(zone[field], field)
        if zone['id'] in ids:
            raise ValueError('duplicate id')
        ids.add(zone['id'])
        _bounds(zone['bounds'])
    return project


def save_project(project, path):
    """Validate then atomically replace JSON in the destination directory."""
    validate_project(project)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temp = Path(stream.name)
            json.dump(project, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def _reject_constant(value):
    raise ValueError('non-finite JSON number: ' + value)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field: ' + key)
        result[key] = value
    return result


def load_project(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        project = json.load(stream, parse_constant=_reject_constant, object_pairs_hook=_unique_pairs)
    return validate_project(project)


def export_csv(project, path):
    """Export observations with raw command history, provenance and usable values."""
    validate_project(project)
    fields = ['id', 'timestamp', 'geometry_id', 'label', 'risk', 'notes', 'enabled_mask', 'feedback']
    for i in range(1, 11):
        fields += ['servo%d_pulse_us' % i, 'servo%d_nominal_angle_deg' % i,
                   'servo%d_provenance' % i, 'servo%d_usable_coordinate_us' % i]
    for axis in ('rail1', 'rail2'):
        fields += [axis + '_position_mm', axis + '_origin_known', axis + '_position_kind']
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for sample in project['samples']:
            row = {f: sample[f] for f in ('id', 'timestamp', 'geometry_id', 'label', 'risk', 'notes')}
            snapshot = sample['snapshot']
            row.update(enabled_mask=snapshot['enabled_mask'], feedback='unavailable')
            for i in range(1, 11):
                row['servo%d_pulse_us' % i] = snapshot['pulse_us'][i - 1]
                row['servo%d_nominal_angle_deg' % i] = snapshot['nominal_angle_deg'][i - 1]
                row['servo%d_provenance' % i] = snapshot['servo_provenance'][i - 1]
                row['servo%d_usable_coordinate_us' % i] = axis_value(snapshot, 'servo%d' % i)
            for axis in ('rail1', 'rail2'):
                for field, value in snapshot['rails'][axis].items():
                    row[axis + '_' + field] = value
            writer.writerow(row)
