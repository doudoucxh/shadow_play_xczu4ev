"""Validated wiring, angle conversion and portable feedback recordings."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .protocol import integer

SCHEMA = 'shadow.bus-teach.v1'


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
        self.axes = {}
        for row in data['axes']:
            n = integer(row['number'], 1, 10, 'Axis number')
            bus = 'person' if n <= 6 else 'tiger'
            if row['bus'] != bus or n in self.axes:
                raise ValueError('Expected person 1–6 and tiger 7–10, once each')
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
        if set(self.axes) != set(range(1, 11)):
            raise ValueError('Exactly ten axes required')
        for bus in ('person', 'tiger'):
            ids = [a.ident for a in self.axes.values() if a.bus == bus]
            if len(set(ids)) != len(ids):
                raise ValueError(f'Duplicate IDs on {bus}')
        if data.get('pins') != {'person': 'E14', 'tiger': 'E15'}:
            raise ValueError('Expected original servo 9 E14 / servo 10 E15')
        if data.get('baudrate') != 115200:
            raise ValueError('This FPGA build supports 115200 baud')

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8-sig')))

    @property
    def fingerprint(self):
        fields = {k: self.data[k] for k in ('axes', 'pins', 'baudrate')}
        return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=True).encode()).hexdigest()

    def select(self, numbers):
        if not isinstance(numbers, list) or not numbers or len(numbers) != len(set(numbers)):
            raise ValueError('Select one or more distinct axes')
        return [self.axes[integer(n, 1, 10, 'Axis')] for n in numbers]


def new_recording(profile, numbers, simulation, rate):
    profile.select(numbers)
    finite(rate, 1, 20, 'Sample rate')
    return {'schema': SCHEMA, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'profile_sha256': profile.fingerprint, 'profile': profile.data,
            'source': 'simulation' if simulation else 'servo_feedback',
            'selected': numbers[:], 'requested_hz': rate,
            'complete': False, 'end_reason': 'recording', 'samples': []}


def validate_recording(record, profile, live=False):
    if not isinstance(record, dict) or record.get('schema') != SCHEMA:
        raise ValueError('Not a bus-servo feedback recording')
    if record.get('profile_sha256') != profile.fingerprint:
        raise ValueError('Recording wiring/IDs/calibration differ from current profile')
    if record.get('source') not in ('servo_feedback', 'simulation'):
        raise ValueError('Unknown feedback source')
    if live and record['source'] != 'servo_feedback':
        raise ValueError('Simulation recordings cannot drive hardware')
    if record.get('complete') is not True:
        raise ValueError('Recording is incomplete; inspect/re-record before playback')
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
        if set(sample['axis_t']) != set(sample['positions']):
            raise ValueError('Missing per-axis acquisition timestamps')
        for axis in axes:
            axis.check_position(sample['positions'][str(axis.number)])
            finite(sample['axis_t'][str(axis.number)], max(0, t - .5), t + .001, 'Acquisition time')
    if samples[0]['t'] > .5 or samples[-1]['t'] <= samples[0]['t']:
        raise ValueError('Invalid recording time origin')
    return record


def save_recording(path, record):
    # Never overwrite a take. Even interrupted recordings remain recoverable.
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def playback_plan(record, profile, numbers, speed):
    validate_recording(record, profile)
    axes = profile.select(numbers)
    if not set(numbers) <= set(record['selected']):
        raise ValueError('Selected axis was not recorded')
    speed = finite(speed, .1, 2, 'Playback speed')
    samples = record['samples']
    plan = []
    for previous, current in zip(samples, samples[1:]):
        dt = (current['t'] - previous['t']) / speed
        if not .02 <= dt <= 9.999:
            raise ValueError('Sample interval cannot be replayed at this speed')
        targets = {str(a.number): current['positions'][str(a.number)] for a in axes}
        for a in axes:
            change = abs(a.degrees(targets[str(a.number)]) - a.degrees(previous['positions'][str(a.number)]))
            if change / dt > a.max_speed + .01:
                raise ValueError(f'Axis {a.number}: recording exceeds speed limit; reduce playback speed')
        plan.append(((previous['t'] - samples[0]['t']) / speed, targets, round(dt * 1000)))
    return plan
