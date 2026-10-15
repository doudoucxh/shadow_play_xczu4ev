#!/usr/bin/env python3
"""Select offline frame pairs inside conservatively guarded commanded holds."""
import argparse
import json
from numbers import Real
from pathlib import Path
import math
from bisect import bisect_left, bisect_right

from PIL import Image


def number(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def records(path):
    with path.open(encoding='utf-8-sig') as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError('{}:{} must be an object'.format(path, line_number))
                yield line_number, value


def extract(sessiondirs):
    windows, skipped = [], []
    for directory in sessiondirs:
        directory = Path(directory).resolve()
        source = str(directory)

        def skip(kind, line, reason):
            skipped.append(dict(source=source, kind=kind, line=line, reason=reason))

        intervals, current, start, last_time = [], None, None, None
        for line, event in records(directory / 'events.jsonl'):
            timestamp = event.get('host_unix_ms')
            if not number(timestamp):
                raise ValueError('{} events line {}: missing/invalid host_unix_ms'.format(source, line))
            if last_time is not None and timestamp < last_time:
                raise ValueError('{} events line {}: nonmonotonic host time'.format(source, line))
            last_time = timestamp
            if 'state' not in event:
                skip('event', line, 'no_state_snapshot')
                continue
            state = event['state']
            if not isinstance(state, dict):
                raise ValueError('{} events line {}: invalid state'.format(source, line))
            pulses = state.get('pulse_us')
            mask, armed = state.get('enabled_mask'), state.get('armed')
            if (not isinstance(pulses, list) or len(pulses) != 10 or
                    not all(number(v) and v > 0 for v in pulses) or
                    type(mask) is not int or not 0 <= mask <= 1023 or type(armed) is not bool):
                raise ValueError('{} events line {}: invalid complete state'.format(source, line))
            command = tuple(pulses) if mask == 1023 and armed else None
            if state.get('faults', 0) != 0 or state.get('pending', False) is not False:
                command = None
                skip('event', line, 'fault_or_pending_state_ends_hold')
            if command != current:
                if current is not None:
                    intervals.append((start, timestamp, current))
                start, current = timestamp, command
        if current is not None:
            skip('window', None, 'unterminated_final_hold')

        frames, seen_ids = [], set()
        for line, frame in records(directory / 'frames.jsonl'):
            camera, fid = frame.get('camera'), frame.get('frame_id')
            host, age = frame.get('host_unix_ns'), frame.get('age_ms')
            if camera not in ('front', 'top') or not isinstance(fid, str) or not fid.strip():
                skip('frame', line, 'invalid_camera_or_frame_id')
                continue
            identity = (camera, fid)
            if identity in seen_ids:
                skip('frame', line, 'duplicate_or_stale_frame_id')
                continue
            seen_ids.add(identity)
            if not number(host) or host <= 0 or not number(age) or age < 0:
                skip('frame', line, 'invalid_host_time_or_negative_age')
                continue
            filename = frame.get('file')
            if not isinstance(filename, str) or not filename.strip():
                skip('frame', line, 'missing_file_reference')
                continue
            path = (directory / filename).resolve()
            if directory not in path.parents or not path.is_file():
                skip('frame', line, 'missing_or_outside_session_file')
                continue
            frames.append(dict(camera=camera, file=str(path), frame_id=fid,
                               host_unix_ms=host / 1e6, age_ms=age,
                               approximate_exposure_unix_ms=host / 1e6 - age,
                               _line=line))

        decoded = {}

        def decodable(frame):
            path = frame['file']
            if path not in decoded:
                try:
                    with Image.open(path) as picture:
                        if picture.format != 'JPEG':
                            raise ValueError('not JPEG')
                        picture.load()
                    decoded[path] = True
                except (OSError, ValueError):
                    decoded[path] = False
                    skip('frame', frame['_line'], 'jpeg_decode_failed')
            return decoded[path]

        for start, end, commands in intervals:
            lower, upper = start + 2000, end - 500
            if upper <= lower:
                skip('window', None, 'hold_too_short:{}..{}'.format(start, end))
                continue
            eligible = [f for f in frames if lower <= f['approximate_exposure_unix_ms'] <= upper
                        and start <= f['host_unix_ms'] < end]
            fronts = [f for f in eligible if f['camera'] == 'front']
            tops = sorted((f for f in eligible if f['camera'] == 'top'),
                          key=lambda f: f['host_unix_ms'])
            top_times = [f['host_unix_ms'] for f in tops]
            center = (lower + upper) / 2
            pairs = []
            for front in fronts:
                lo = bisect_left(top_times, front['host_unix_ms'] - 100)
                hi = bisect_right(top_times, front['host_unix_ms'] + 100)
                pairs.extend((front, top) for top in tops[lo:hi])
            pairs.sort(key=lambda p: (abs((p[0]['approximate_exposure_unix_ms'] +
                                          p[1]['approximate_exposure_unix_ms']) / 2 - center),
                                     abs(p[0]['host_unix_ms'] - p[1]['host_unix_ms']),
                                     p[0]['_line'], p[1]['_line']))
            pair = None
            for candidate in pairs:
                front_ok = decodable(candidate[0])
                top_ok = decodable(candidate[1])
                if front_ok and top_ok:
                    pair = candidate
                    break
            if pair is None:
                skip('window', None, 'no_decodable_guarded_front_top_pair:{}..{}'.format(start, end))
                continue
            windows.append(dict(source=source, status='commanded_hold_candidate',
                commands=list(commands), duration_ms=end-start, start_host_unix_ms=start,
                end_host_unix_ms=end, guarded_start_unix_ms=lower, guarded_end_unix_ms=upper,
                frames={camera: {k: v for k, v in frame.items() if k != '_line'}
                        for camera, frame in zip(('front', 'top'), pair)}, context_verified=False,
                annotation_verified=False, command_frame_pair_verified=False,
                physical_stability_verified=False))
    return dict(version=1, type='offline_commanded_hold_frame_candidates', deployment_ready=False,
                windows=windows, skipped=skipped,
                limitations=['Host timestamps are receipt times; host minus age is only an exposure approximation.',
                             'JPEG decoding is lazy: only candidate pairs visited before selection are decoded; unused files are not audited.',
                             'A commanded_hold_candidate is not measured stability or approved command/frame pairing.',
                             'No coordinates, actual joint feedback, motion authorization or hardware operations are supplied.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sessiondirs', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = extract(args.sessiondirs)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    print('{} offline candidate windows'.format(len(report['windows'])))


if __name__ == '__main__':
    main()
