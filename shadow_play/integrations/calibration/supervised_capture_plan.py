#!/usr/bin/env python3
"""Bounded, attended loaded-mechanism sampling plan; no position feedback.

Startup is read-only. Plans explicitly match the current OFF readback, enable
one channel at a time, and move one enabled axis at a time within local bounds.
The host must supervise both cameras and interrupt on loss. Hardware watchdog
and finally-OFF remain independent of the host. This is not autonomous replay.
"""
import argparse
import json
import math
import os
import select
import sys
import time


def validate_plan(plan):
    if plan.get('observer_present') is not True or plan.get('estimated_start_authorized') is not True:
        raise ValueError('Explicit attended loaded-start authorization required')
    pulses = plan['expected_pulses_us'][:]
    if len(pulses) != 10 or any(type(p) is not int or not 500 <= p <= 2500 for p in pulses):
        raise ValueError('Ten integer expected command registers required')
    if type(plan['expected_sequence']) is not int or plan['expected_sequence'] < 0:
        raise ValueError('Expected sequence required')
    bounds = plan['local_bounds_us']
    if not isinstance(bounds, dict) or not bounds or set(bounds) - set('123456'):
        raise ValueError('Only attended human channels 1..6 are supported')
    for key, limits in bounds.items():
        if (not isinstance(limits, list) or len(limits) != 2 or
                any(type(p) is not int for p in limits) or
                not 500 <= limits[0] <= limits[1] <= 2500 or
                limits[1]-limits[0] > 112):
            raise ValueError('Explicit narrow local pulse bounds required (span <=112 us)')
    steps = plan['steps']
    if not 1 <= len(steps) <= 24:
        raise ValueError('Expected 1..24 finite steps')
    enabled = set(); duration = 0.0; labels = set()
    for step in steps:
        if set(step) != {'label', 'channel', 'pulse_us', 'hold_seconds'}:
            raise ValueError('Unexpected step fields')
        ch, pulse, hold = step['channel'], step['pulse_us'], step['hold_seconds']
        if type(ch) is not int or str(ch) not in bounds or type(pulse) is not int:
            raise ValueError('Channel/pulse not in plan bounds')
        if not bounds[str(ch)][0] <= pulse <= bounds[str(ch)][1]:
            raise ValueError('Target outside local bounds')
        if type(hold) not in (int, float) or not math.isfinite(hold) or not 1 <= hold <= 5:
            raise ValueError('Settling hold must be 1..5 seconds')
        if not isinstance(step['label'], str) or not step['label'] or step['label'] in labels:
            raise ValueError('Unique sample label required')
        labels.add(step['label'])
        delta = abs(pulse-pulses[ch-1])
        if ch not in enabled:
            if delta:
                raise ValueError('First enable uses exactly the inspected command register')
            enabled.add(ch)
        elif delta > 37:
            raise ValueError('Adjacent targets may differ by at most 37 us (~5 degrees)')
        duration += hold + math.ceil(delta / 4) * .08
        pulses[ch-1] = pulse
    if duration > 60:
        raise ValueError('Plan exceeds 60-second motion window')
    return duration


class HostLease:
    """A host liveness token expires even while this board process is alive."""
    def __init__(self, fd, clock=time.monotonic):
        self.fd = fd; self.clock = clock; self.last = clock(); self.buffer = b''

    def check(self):
        if select.select([self.fd], [], [], 0)[0]:
            chunk = os.read(self.fd, 1024)
            if not chunk: raise RuntimeError('Host input closed')
            self.buffer += chunk
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                if line.strip() != b': # CAPTURE_LEASE':
                    raise RuntimeError('Unexpected host input during motion')
                self.last = self.clock()
            if len(self.buffer) > 100: raise RuntimeError('Oversized host lease')
        if self.clock()-self.last > 1.5:
            raise RuntimeError('Host lease expired; stop and inspect, no automatic rearm')


def run_plan(device, plan, emit, clock=time.monotonic, sleep=time.sleep, lease_check=lambda:None):
    validate_plan(plan)
    before = device.status()
    if (before.get('identity') != 'SP10' or before.get('clock_hz') != 100000000 or
            before.get('period_us') != 20000 or before.get('armed') is not False or
            before.get('enabled_mask') != 0 or before.get('pending') is not False or
            before.get('faults') != 0 or before['sequence'] != plan['expected_sequence'] or
            before['pulse_us'] != plan['expected_pulses_us']):
        raise RuntimeError('Inspected OFF state changed; do not run or retry the plan')
    pulses = before['pulse_us'][:]; mask = 0; deadline = clock() + 65

    def wait(seconds):
        until = clock() + seconds
        while clock() < until:
            lease_check()
            s = device.status()
            if (clock() > deadline or not s['armed'] or s['faults'] or s['pending'] or
                    s['enabled_mask'] != mask or s['pulse_us'] != pulses):
                raise RuntimeError('Plan interrupted; no retry or rearm')
            device.kick(); sleep(.04)

    def adopt(allow_arm=False):
        lease_check()
        s = device.commit(pulses, mask, allow_arm=allow_arm)
        if not s['armed'] or s['enabled_mask'] != mask or s['pulse_us'] != pulses or s['faults'] or s['pending']:
            raise RuntimeError('Adopted state mismatch')
        return s

    try:
        for step in plan['steps']:
            ch = step['channel']; bit = 1 << (ch-1)
            if not mask & bit:
                first = mask == 0; mask |= bit
                adopt(allow_arm=first)
            target = step['pulse_us']
            while pulses[ch-1] != target:
                remaining = target-pulses[ch-1]
                pulses[ch-1] += max(-4, min(4, remaining))
                adopt(); wait(.08)
            emit({'event': 'sample_begin', 'label': step['label'], 'state': device.status(),
                  'actual_position_verified': False})
            wait(step['hold_seconds'])
            emit({'event': 'sample_end', 'label': step['label'], 'state': device.status()})
    finally:
        emit({'event': 'outputs_off', 'state': device.off()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan'); p.add_argument('--execute', action='store_true')
    p.add_argument('--require-host-lease', action='store_true')
    args = p.parse_args()
    with open(args.plan) as f: plan = json.load(f)
    duration = validate_plan(plan)
    if not args.execute:
        print(json.dumps({'dry_run': True, 'duration_bound_seconds': duration, 'steps': len(plan['steps'])})); return
    if not args.require_host_lease:
        raise ValueError('Execution requires a live host lease; use the supervised capture host')
    from servo_pwm_device import PwmDevice, Registers
    reg = Registers()
    try:
        lease = HostLease(sys.stdin.fileno())
        run_plan(PwmDevice(reg), plan, lambda row: print(json.dumps(row), flush=True), lease_check=lease.check)
    finally:
        reg.close()


if __name__ == '__main__': main()
