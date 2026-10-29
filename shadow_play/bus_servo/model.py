"""Validated wiring, angle conversion and portable feedback recordings."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .protocol import integer
from .layouts import get_layout

SCHEMA = 'shadow.bus-teach.v1'
MOTION_SCHEMA = 'shadow.bus-motion.v1'
PLAYBACK_DEADBAND_DEG = .5


def finite(value, low, high, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label} must be finite in {low}..{high}')
    return float(value)


@dataclass(frozen=True)
class Axis:
    number: int
    bus: str
    ident: int
    label: str
    span: int
    minimum: float
    maximum: float
    max_speed: float

    def degrees(self, position):
        integer(position, 500, 2500, 'Position')
        return (position - 500) * self.span / 2000

    def position(self, degrees):
        degrees = finite(degrees, self.minimum, self.maximum, self.label)
        return round(500 + degrees * 2000 / self.span)

    def check_position(self, position):
        angle = self.degrees(position)
        # Round-trip quantization is at most half one count.
        tolerance = self.span / 4000 + 1e-9
        finite(angle, self.minimum - tolerance, self.maximum + tolerance, self.label)
        return position


class Profile:
    def __init__(self, data):
        self.data = data
        if data.get('schema') != 'shadow.bus-profile.v1':
            raise ValueError('Wrong bus profile schema')
        self.layout = get_layout(data.get('layout', 'dual'))
        expected = dict(self.layout.axis_buses)
        self.axes = {}
        for row in data['axes']:
            n = integer(row['number'], 1, 10, 'Axis number')
            bus = expected.get(n)
            if row['bus'] != bus or n in self.axes:
                raise ValueError('Axis / bus mapping does not match the selected wiring layout')
            ident = integer(row['id'], 0, 253, 'Bus ID')
            span = row['span_deg']
            if type(span) is not int or span not in (180, 270, 360):
                raise ValueError('Angle span must be 180, 270 or 360')
            lo = finite(row['min_deg'], 0, span, 'Minimum')
            hi = finite(row['max_deg'], lo, span, 'Maximum')
            if hi - lo < 1:
                raise ValueError('Angle range too narrow')
            speed = finite(row['max_speed_deg_s'], 1, 180, 'Maximum speed')
            self.axes[n] = Axis(n, bus, ident, str(row['label']), span, lo, hi, speed)
        if set(self.axes) != set(expected):
            raise ValueError('Profile must contain exactly the axes in its wiring layout')
        for bus in self.layout.pins:
            ids = [a.ident for a in self.axes.values() if a.bus == bus]
            if len(set(ids)) != len(ids):
                raise ValueError(f'Duplicate IDs on {bus}')
        if data.get('pins') != self.layout.pins:
            raise ValueError('Package pins do not match the selected wiring layout')
        if data.get('baudrate') != 115200:
            raise ValueError('This FPGA build supports 115200 baud')
        if type(data.get('playback_speed_limit_enabled', True)) is not bool:
            raise ValueError('Playback speed limit setting must be boolean')

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8-sig')))

    @property
    def fingerprint(self):
        fields = {k: self.data[k] for k in ('axes', 'pins', 'baudrate')}
        # Preserve the original dual-bus fingerprint and its saved recordings.
        if self.layout.name != 'dual':
            fields['layout'] = self.layout.name
        return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=True).encode()).hexdigest()

    def select(self, numbers):
        if not isinstance(numbers, list) or not numbers or len(numbers) != len(set(numbers)):
            raise ValueError('Select one or more distinct axes')
        checked = [integer(n, 1, 10, 'Axis') for n in numbers]
        if any(n not in self.axes for n in checked):
            raise ValueError('Selected axis is absent from this wiring layout')
        return [self.axes[n] for n in checked]


def new_recording(profile, numbers, simulation, rate):
    profile.select(numbers)
    finite(rate, 1, 20, 'Sample rate')
    return {'schema': SCHEMA, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'profile_sha256': profile.fingerprint, 'profile': profile.data,
            'source': 'simulation' if simulation else 'servo_feedback',
            'selected': numbers[:], 'requested_hz': rate,
            'complete': False, 'end_reason': 'recording', 'samples': []}


def validate_recording(record, profile, live=False):
    if not isinstance(record, dict) or record.get('schema') not in (SCHEMA, MOTION_SCHEMA):
        raise ValueError('Not a bus-servo feedback recording')
    if record.get('profile_sha256') != profile.fingerprint:
        raise ValueError('Recording wiring/IDs/calibration differ from current profile')
    planned = record['schema'] == MOTION_SCHEMA
    sources = ('edited_feedback', 'simulation') if planned else ('servo_feedback', 'simulation')
    if record.get('source') not in sources:
        raise ValueError('Unknown feedback source')
    if live and record['source'] == 'simulation':
        raise ValueError('Simulation recordings cannot drive hardware')
    if record.get('complete') is not True:
        raise ValueError('Recording is incomplete; inspect/re-record before playback')
    if planned:
        if 'av_project' in record:
            from .av_editing import verify_compiled
        else:
            from .editing import verify_compiled
        verify_compiled(record, profile)
    axes = profile.select(record['selected'])
    samples = record['samples']
    if not isinstance(samples, list) or not 2 <= len(samples) <= 100000:
        raise ValueError('Recording requires 2..100000 complete samples')
    prev = -1.0
    for sample in samples:
        t = finite(sample['t'], 0, 3600, 'Sample time')
        if t <= prev:
            raise ValueError('Sample timestamps must strictly increase')
        prev = t
        if set(sample['positions']) != {str(a.number) for a in axes}:
            raise ValueError('Sample has missing or extra axes')
        if not planned and set(sample['axis_t']) != set(sample['positions']):
            raise ValueError('Missing per-axis acquisition timestamps')
        for axis in axes:
            axis.check_position(sample['positions'][str(axis.number)])
            if not planned:
                finite(sample['axis_t'][str(axis.number)], max(0, t - .5), t + .001, 'Acquisition time')
    if samples[0]['t'] > .5 or samples[-1]['t'] <= samples[0]['t']:
        raise ValueError('Invalid recording time origin')
    return record


def save_recording(path, record):
    # Never overwrite a take. Even interrupted recordings remain recoverable.
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


class PlaybackPlan(list):
    """Command schedule plus a map back to the unchanged recording time axis."""
    def __init__(self):
        super().__init__()
        self.playback_times = [0.0]
        self.source_times = [0.0]
        self.filtered_samples = 0
        self.retimed_intervals = 0


def playback_plan(record, profile, numbers, speed):
    validate_recording(record, profile)
    axes = profile.select(numbers)
    if not set(numbers) <= set(record['selected']):
        raise ValueError('Selected axis was not recorded')
    speed = finite(speed, .1, 2, 'Playback speed')
    samples = record['samples']
    plan = PlaybackPlan()
    plan.speed_limited = profile.data.get('playback_speed_limit_enabled', True)
    held = {str(a.number): samples[0]['positions'][str(a.number)] for a in axes}
    elapsed_ms = 0
    for previous, current in zip(samples, samples[1:]):
        dt = (current['t'] - previous['t']) / speed
        if dt > 9.999:
            raise ValueError('该倍率下相邻帧间隔超过9.999秒，请检查素材时间或提高倍率。')
        targets = {}
        required = 0
        for a in axes:
            key = str(a.number)
            target = current['positions'][key]
            change = abs(a.degrees(target) - a.degrees(held[key]))
            # Anchor to the last retained target, not the previous raw sample:
            # slow intentional movement must eventually cross the deadband.
            if change <= PLAYBACK_DEADBAND_DEG + 1e-9:
                plan.filtered_samples += target != held[key]
                target = held[key]
                change = 0
            targets[key] = target
            if plan.speed_limited:
                required = max(required, change/a.max_speed)
        requested_ms = (round((current['t']-samples[0]['t'])/speed*1000) -
                        round((previous['t']-samples[0]['t'])/speed*1000)) if not plan.speed_limited else round(dt*1000)
        duration_ms = max(20, requested_ms, math.ceil(required*1000-1e-8))
        if duration_ms > 9999:
            raise ValueError('该段位移在当前限速下需要超过9.999秒，请在编辑器增加中间姿势。')
        plan.retimed_intervals += duration_ms > requested_ms
        plan.append((elapsed_ms/1000, targets, duration_ms))
        elapsed_ms += duration_ms
        plan.playback_times.append(elapsed_ms/1000)
        plan.source_times.append(current['t'] - samples[0]['t'])
        held = targets
    return plan
