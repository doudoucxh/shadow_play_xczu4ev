"""One attended channel-7 direction check; no story, audio or slide entry point.

This explicit exception preserves incident locks and cannot enable other axes.
The fixed 1500 -> 1540 -> 1500 us route needs a fresh OFF-state binding.
Nominal schedule is twelve seconds; this isolated check has no audio clock.
Operator-reported midpoint is a reference, never measured shaft feedback.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import sys
import time

from servo_pwm_device import PwmDevice, Registers

SCHEMA = 'attended-v20-first-direction-v3'
IMAGE = '824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'
HISTORICAL_SOURCE = 'a0a7af4128b1eee714b62f7a87ed4b286eeb960b9f9468b06fa9188d176860ab'
MASK = 64
MIDPOINT = [1500] * 10
INTERVAL = .04
INTERRUPTION_LOG_SHA = '072903723911f382bc61177471afd550aa082711375aee1ee042b256d6956332'
INTERRUPTED_PULSES = MIDPOINT[:6] + [1501] + MIDPOINT[7:]
INTERRUPTED_BOOT = '8b5372c2-00de-459e-ad96-371ec5ea0ef9'
INTERRUPTION_LOG = '/run/media/mmcblk0p2/piying/v20-first-direction-20261018/run-02c74785894841a883e958797b582107.board.jsonl'
LATEST_PULSES = MIDPOINT[:6] + [1524] + MIDPOINT[7:]
LATEST_LOG_SHA = '351c781eee9c705383b181f7666b8c08459d2cb121d1bbddf84af21067225880'
LATEST_LOG = '/run/media/mmcblk0p2/piying/v20-first-direction-20261018-r2/run-ea9fb1a0fd2147f59d0cc22fc3f9bce2.board.jsonl'
PREFIX = '@@V20STEP@@'


def route(initial=1500):
    if type(initial) is not int or initial not in (1500, 1501, 1524):
        raise ValueError('Only recorded starting commands are supported')
    rows = []
    for i in range(301):
        t = i / 50
        u = .5 - .5 * math.cos(math.pi * min(t, 2) / 2) if t <= 3 else (
            .5 + .5 * math.cos(math.pi * min(t - 3, 2) / 2))
        pulses = MIDPOINT[:]
        base = initial if t <= 3 else 1500
        pulses[6] = base + int(math.floor((1540 - base) * u + .5))
        rows.append(pulses)
    return rows


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


ROUTE = route()


def validate_plan(p):
    fields = {'schema', 'session_id', 'boot_id', 'expected_sequence', 'expected_pulse_us',
              'route_sha256', 'historical_source_sha256', 'operator_midpoint_reference',
              'onsite_observer', 'camera_required', 'enabled_mask', 'interruption_reviewed'}
    if not isinstance(p, dict) or set(p) != fields or p['schema'] != SCHEMA:
        raise ValueError('Exact first-direction plan required')
    if not re.fullmatch('[a-f0-9]{32}', p['session_id']):
        raise ValueError('Unique session ID required')
    if not re.fullmatch('[a-f0-9-]{36}', p['boot_id']):
        raise ValueError('Boot binding required')
    if type(p['expected_sequence']) is not int or not 0 <= p['expected_sequence'] < 2**32:
        raise ValueError('Fresh sequence required')
    if p['interruption_reviewed'] is True:
        references = {14: INTERRUPTED_PULSES, 72: LATEST_PULSES}
        if (p['expected_pulse_us'] != references.get(p['expected_sequence']) or p['boot_id'] != INTERRUPTED_BOOT):
            raise ValueError('Only a recorded interruption may use its new onsite review')
    elif p['interruption_reviewed'] is not False or p['expected_pulse_us'] != MIDPOINT:
        raise ValueError('Operator midpoint reference required')
    if (p['route_sha256'] != digest(route(p['expected_pulse_us'][6]))
            or p['enabled_mask'] != MASK or type(p['enabled_mask']) is not int
            or p['operator_midpoint_reference'] is not True or p['onsite_observer'] is not True
            or type(p['camera_required']) is not bool
            or p['historical_source_sha256'] != HISTORICAL_SOURCE):
        raise ValueError('Only the attended fixed midpoint/7-axis route is allowed')


def validate_interruption(p, raw):
    if not p['interruption_reviewed']:
        return
    expected_hash = {14: INTERRUPTION_LOG_SHA, 72: LATEST_LOG_SHA}[p['expected_sequence']]
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError('Original interruption evidence changed')
    last = json.loads(raw.splitlines()[-1])
    s = last['state']
    if (last['event'] != 'outputs_off' or last['route_complete'] is not False
            or s['sequence'] != p['expected_sequence'] or s['pulse_us'] != p['expected_pulse_us']
            or s['armed'] or s['enabled_mask'] or s['faults'] or s['pending']):
        raise ValueError('Original interrupted OFF state mismatch')


class HostLease:
    def __init__(self, fd, session_id, clock=time.monotonic):
        self.fd = fd
        self.clock = clock
        self.session_id = session_id
        self.last = clock()
        self.begun = False
        self.buffer = b''

    def check(self):
        if select.select([self.fd], [], [], 0)[0]:
            data = os.read(self.fd, 1024)
            if not data:
                raise RuntimeError('Host input closed')
            self.buffer += data
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                text = line.strip().decode('ascii')
                if text == ': # V20_BEGIN ' + self.session_id and not self.begun:
                    self.begun = True
                    self.last = self.clock()
                elif text == ': # V20_LEASE ' + self.session_id and self.begun:
                    self.last = self.clock()
                else:
                    raise RuntimeError('Host stop or unexpected input; no retry')
            if len(self.buffer) > 120:
                raise RuntimeError('Oversized host input')
        if self.clock() - self.last > 1.5:
            raise RuntimeError('Host lease expired')


class FirstDirectionDevice(PwmDevice):
    def __init__(self, registers, plan, host, *, boot_id, marker, used_path,
                 motion_inhibit_paths=None, cancel_path='/run/v20-first-direction-stop',
                 clock=time.monotonic):
        validate_plan(plan)
        if boot_id != plan['boot_id'] or marker.get('boot_id') != boot_id or marker.get('sha256') != IMAGE:
            raise ValueError('Current boot/image differs from the inspected binding')
        super().__init__(registers, motion_inhibit_paths=motion_inhibit_paths)
        self.plan = json.loads(json.dumps(plan))
        self.host = host
        self.clock = clock
        self.cancel = Path(cancel_path)
        self.used_path = Path(used_path)
        self.hashes = self.lock_hashes()
        self.sequence = plan['expected_sequence']
        self.pulses = plan['expected_pulse_us'][:]
        self.frames = route(self.pulses[6])
        self.mask = 0
        self.index = 0
        self.inside = False
        self.started = False
        self.failed = False
        self.last_issue = None
        self.deadline = None
        self.check()

    def lock_hashes(self):
        # Both expected incident markers must still exist; no silent unlock.
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in self.motion_inhibit_paths)

    def check(self):
        if self.failed or self.cancel.exists() or self.hashes != self.lock_hashes():
            raise RuntimeError('Stopped, failed or incident lock changed')
        self.host.check()
        if self.deadline is not None and self.clock() >= self.deadline:
            raise RuntimeError('Bounded check duration expired')
        s = self.status()
        if (s['period_us'] != 20000 or s['clock_hz'] != 100000000 or s['faults'] or s['pending']
                or s['armed'] != bool(self.mask) or s['enabled_mask'] != self.mask
                or s['sequence'] != self.sequence or s['pulse_us'] != self.pulses):
            raise RuntimeError('Unexpected PWM state; no rearm or retry')
        return s

    def _check_motion_allowed(self):
        if self.inside:
            self.check()
        else:
            super()._check_motion_allowed()

    def begin(self):
        self.check()
        if self.started or not self.host.begun:
            raise RuntimeError('Single explicit start and active host required')
        # Consume before the first write, including attempts that fail adoption.
        with self.used_path.open('x') as f:
            f.write(digest(self.plan))
            f.flush()
            os.fsync(f.fileno())
        self.started = True
        self.deadline = self.clock() + 16

    def commit(self, pulses, mask, allow_arm=False):
        self.check()
        if not self.started or self.index >= len(self.frames):
            raise RuntimeError('No further motion in this one-use check')
        if pulses != self.frames[self.index] or mask != MASK or allow_arm is not (self.index == 0):
            raise ValueError('Only the exact next fixed frame and single-axis mask are allowed')
        now = self.clock()
        if self.last_issue is not None and now - self.last_issue < INTERVAL - 1e-8:
            raise RuntimeError('No accelerated catch-up')
        self.inside = True
        try:
            state = super().commit(pulses, mask, allow_arm=allow_arm)
        except BaseException:
            self.failed = True
            raise
        finally:
            self.inside = False
        self.last_issue = now
        self.pulses = pulses[:]
        self.mask = MASK
        self.sequence = state['sequence']
        self.index += 1
        return state


def run_check(d, emit, *, sleep=time.sleep):
    complete = False
    try:
        d.begin()
        start = d.clock()
        for i, pulses in enumerate(d.frames):
            scheduled = max(start + i * INTERVAL,
                            (d.last_issue + INTERVAL) if d.last_issue is not None else start)
            while d.clock() < scheduled:
                d.check()
                d.kick()
                sleep(max(0., min(.005, scheduled - d.clock())))
            # This is an unsynchronized direction check. Small scheduling
            # delays may accumulate, but no command can catch up faster than
            # INTERVAL. Bound individual gaps and the whole session instead
            # of aborting on accumulated phase error against an audio clock.
            if d.last_issue is not None and d.clock() - d.last_issue > .15:
                raise RuntimeError('Command interval stalled; abort rather than catch up')
            d.check()
            d.kick()
            state = d.commit(pulses, MASK, allow_arm=(i == 0))
            emit({'event': 'frame', 'index': i, 'elapsed_s': d.clock() - start, 'state': state})
        complete = True
    finally:
        # Failure stops in place. Never automatically return after a fault.
        state = d.stop_after_frame() if complete else d.off()
        emit({'event': 'outputs_off', 'route_complete': complete, 'state': state,
              'incident_locks_removed': False, 'position_feedback': None})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--execute-one-direction-check', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    validate_plan(plan)
    if not args.execute_one_direction_check:
        print(json.dumps({'dry_run': True, 'frames': len(ROUTE), 'enabled_mask': MASK,
                          'duration_s': 12, 'route_sha256': plan['route_sha256']}))
        return
    if plan['interruption_reviewed']:
        evidence_path = {14: INTERRUPTION_LOG, 72: LATEST_LOG}[plan['expected_sequence']]
        validate_interruption(plan, Path(evidence_path).read_bytes())
    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    host = HostLease(sys.stdin.fileno(), plan['session_id'])
    marker = json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    used = '/run/v20-first-direction-{}-{}.used'.format(boot, plan['expected_sequence'])
    registers = Registers()
    try:
        d = FirstDirectionDevice(registers, plan, host, boot_id=boot, marker=marker, used_path=used)
        # Open the log before offering a start. Each run gets its own file.
        with args.plan.with_suffix('.board.jsonl').open('x') as log:
            def emit(row):
                log.write(json.dumps(row) + '\n')
                if row.get('event') != 'frame' or row['index'] % 50 == 0:
                    print(PREFIX + json.dumps(row), flush=True)
            print(PREFIX + json.dumps({'event': 'ready', 'session_id': plan['session_id'],
                                      'state': d.check()}), flush=True)
            while not host.begun:
                host.check()
                time.sleep(.01)
            run_check(d, emit)
            log.flush()
            os.fsync(log.fileno())
    finally:
        registers.close()


if __name__ == '__main__':
    main()
