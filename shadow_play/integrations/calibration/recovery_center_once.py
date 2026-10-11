#!/usr/bin/env python3
"""Explicit, attended centering exception after an incident.

Normal host/board incident locks remain present. This separate entry point can
make exactly one fixed 1500-us commit on one approved channel, then turns OFF.
It cannot jog, resume a multiply constrained pose, or clear a lock. Physical
release and sweep clearance must be reviewed. Axes 5/6 additionally accept an
explicitly reviewed single free puppet connection, without claiming rod removal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from servo_pwm_device import PwmDevice, Registers

APPROVAL = 'single-unloaded-center-with-incident-locks-retained'
FREE_APPROVAL = 'single-free-connection-center-with-incident-locks-retained'
HOLD_SECONDS = 3.0


def validate_plan(plan):
    fields = {'approval', 'channel', 'expected_sequence', 'expected_pulses_us',
              'linkage_disconnected', 'remaining_bracket_and_rod_clear', 'observer_ready'}
    free_fields = fields | {'free_single_connection', 'puppet_other_rods_disconnected'}
    if not isinstance(plan, dict) or set(plan) not in (fields, free_fields):
        raise ValueError('Exact unloaded-recovery plan fields required')
    free_connection = set(plan) == free_fields
    if plan['approval'] != (FREE_APPROVAL if free_connection else APPROVAL):
        raise ValueError('Specific operator approval required; ordinary continuation is insufficient')
    if type(plan['channel']) is not int or not 1 <= plan['channel'] <= 10:
        raise ValueError('One channel required')
    if free_connection:
        if (plan['channel'] not in (5, 6) or plan['linkage_disconnected'] is not False
                or plan['free_single_connection'] is not True
                or plan['puppet_other_rods_disconnected'] is not True):
            raise ValueError('Only reviewed axes 5/6 with one free puppet connection are eligible')
    elif plan['linkage_disconnected'] is not True:
        raise ValueError('Disconnected load must be confirmed')
    if any(plan[key] is not True for key in
           ('remaining_bracket_and_rod_clear', 'observer_ready')):
        raise ValueError('Disconnected load, clear sweep and observer must be confirmed')
    if type(plan['expected_sequence']) is not int or not 0 <= plan['expected_sequence'] < 2**32:
        raise ValueError('Inspected sequence required')
    pulses = plan['expected_pulses_us']
    if not isinstance(pulses, list) or len(pulses) != 10 or any(
            type(p) is not int or not 500 <= p <= 2500 for p in pulses):
        raise ValueError('Ten inspected command registers required; these are not shaft feedback')


class RecoveryCenterDevice(PwmDevice):
    """Only this object receives the explicit one-commit exception.

    Other driver objects and programs continue to enforce the incident locks.
    Keeping the marker files intact also preserves their state after power loss.
    """
    def __init__(self, registers, plan, *, motion_inhibit_paths=None,
                 cancel_path='/run/shadow-pwm-recovery-cancel', clock=time.monotonic):
        validate_plan(plan)
        super().__init__(registers, motion_inhibit_paths=motion_inhibit_paths)
        self.plan = json.loads(json.dumps(plan))
        self.cancel_path = Path(cancel_path)
        self.clock = clock
        self.expires = clock() + 15.0
        self.used = False
        self.inside_center_commit = False
        self.lock_hashes = self._lock_hashes()

    def _lock_hashes(self):
        # Missing, unreadable or replaced incident records invalidate recovery.
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest()
                     for p in self.motion_inhibit_paths)

    def check_recovery(self):
        if self.cancel_path.exists() or self.clock() >= self.expires:
            raise RuntimeError('Recovery cancelled or expired; no retry')
        if self._lock_hashes() != self.lock_hashes:
            raise RuntimeError('Incident lock changed; stop and review')

    def _check_motion_allowed(self):
        if not self.inside_center_commit:
            return super()._check_motion_allowed()
        self.check_recovery()

    def commit(self, pulses, mask, allow_arm=False):
        target = self.plan['expected_pulses_us'][:]
        target[self.plan['channel']-1] = 1500
        if (self.used or pulses != target or mask != 1 << (self.plan['channel']-1)
                or allow_arm is not True):
            raise RuntimeError('Recovery permits one fixed-pulse, single-channel centering commit only')
        before = self.status()
        if (before['identity'] != 'SP10' or before['period_us'] != 20000
                or before['clock_hz'] != 100000000 or before['armed']
                or before['enabled_mask'] or before['pending'] or before['faults']
                or before['sequence'] != self.plan['expected_sequence']
                or before['pulse_us'] != self.plan['expected_pulses_us']):
            raise RuntimeError('Inspected OFF state changed; no recovery or retry')
        self.check_recovery()
        self.used = True  # Even an uncertain/failed attempt must not be repeated.
        self.inside_center_commit = True
        try:
            return super().commit(pulses, mask, allow_arm=True)
        finally:
            self.inside_center_commit = False


def run_once(device, emit, *, clock=time.monotonic, sleep=time.sleep):
    plan = device.plan
    target = plan['expected_pulses_us'][:]
    target[plan['channel']-1] = 1500
    mask = 1 << (plan['channel']-1)
    completed = False
    try:
        state = device.commit(target, mask, allow_arm=True)
        emit({'event': 'center_started', 'channel': plan['channel'], 'state': state,
              'hold_seconds': HOLD_SECONDS, 'actual_position_verified': False})
        deadline = clock() + HOLD_SECONDS
        while clock() < deadline:
            device.check_recovery()
            state = device.status()
            if (not state['armed'] or state['enabled_mask'] != mask or state['pending']
                    or state['faults'] or state['pulse_us'] != target
                    or state['sequence'] != (plan['expected_sequence']+1) % 2**32):
                raise RuntimeError('Recovery state changed; no retry')
            device.kick()
            sleep(min(.04, max(0.0, deadline-clock())))
        completed = True
    finally:
        state = device.stop_after_frame() if completed else device.off()
        emit({'event': 'outputs_off', 'state': state, 'normal_frame_stop': completed,
              'incident_locks_removed': False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--execute-approved-unloaded-center', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    validate_plan(plan)
    if not args.execute_approved_unloaded_center:
        print(json.dumps({'dry_run': True, 'channel': plan['channel'], 'pulse_us': 1500,
                          'hold_seconds': HOLD_SECONDS, 'incident_locks_removed': False}))
        return
    registers = Registers()  # Existing image checks and exclusive MMIO lock.
    try:
        device = RecoveryCenterDevice(registers, plan)
        run_once(device, lambda row: print(json.dumps(row), flush=True))
    finally:
        registers.close()


if __name__ == '__main__':
    main()
