#!/usr/bin/env python3
"""Finite attended jog for reviewed person gimbals; incident locks stay intact.

This does not commission loaded motion. The operator must have confirmed rod
release and clearance, and the observed start pose must match the last command.
No register value is interpreted as measured shaft feedback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from servo_pwm_device import PwmDevice, Registers

APPROVAL = 'attended-unloaded-small-steps'
STEP_US = 8
INTERVAL_SECONDS = .12
HOLD_SECONDS = 1.2


def validate_plan(plan):
    fields = {'approval', 'channel', 'expected_sequence', 'expected_pulses_us',
              'target_us', 'linkage_disconnected', 'sweep_clear', 'observer_ready',
              'start_pose_reviewed'}
    free_fields = fields | {'free_single_connection', 'puppet_other_rods_disconnected'}
    if not isinstance(plan, dict) or set(plan) not in (fields, free_fields):
        raise ValueError('Exact attended unloaded-jog plan required')
    free_connection = set(plan) == free_fields
    if plan['approval'] != APPROVAL:
        raise ValueError('Attended jog authorization required')
    allowed = (5, 6) if free_connection else (1, 2, 3, 4)
    if type(plan['channel']) is not int or plan['channel'] not in allowed:
        raise ValueError('Only the two detached gimbals are eligible')
    if free_connection:
        if (plan['linkage_disconnected'] is not False or plan['free_single_connection'] is not True
                or plan['puppet_other_rods_disconnected'] is not True):
            raise ValueError('Third gimbal requires one free connection with other puppet rods detached')
    elif plan['linkage_disconnected'] is not True:
        raise ValueError('Detached gimbals required')
    for name in ('sweep_clear', 'observer_ready', 'start_pose_reviewed'):
        if plan[name] is not True:
            raise ValueError('Physical conditions must be reviewed: '+name)
    if type(plan['expected_sequence']) is not int or not 0 <= plan['expected_sequence'] < 2**32:
        raise ValueError('Inspected sequence required')
    pulses = plan['expected_pulses_us']
    if not isinstance(pulses, list) or len(pulses) != 10 or any(
            type(p) is not int or not 500 <= p <= 2500 for p in pulses):
        raise ValueError('Ten inspected command registers required')
    start = pulses[plan['channel']-1]
    target = plan['target_us']
    if (type(target) is not int or not 1300 <= start <= 1700
            or not 1300 <= target <= 1700 or not 0 < abs(target-start) <= 150):
        raise ValueError('Jog must stay in 1300..1700 us with excursion at most 150 us')


def pulse_path(plan):
    validate_plan(plan)
    value = plan['expected_pulses_us'][plan['channel']-1]
    result = [value]
    target = plan['target_us']
    while value != target:
        value += max(-STEP_US, min(STEP_US, target-value))
        result.append(value)
    return result


class RecoveryJogDevice(PwmDevice):
    def __init__(self, registers, plan, *, motion_inhibit_paths=None,
                 cancel_path='/run/shadow-pwm-recovery-cancel', clock=time.monotonic):
        validate_plan(plan)
        super().__init__(registers, motion_inhibit_paths=motion_inhibit_paths)
        self.plan = json.loads(json.dumps(plan))
        self.path = pulse_path(plan)
        self.cancel_path = Path(cancel_path)
        self.clock = clock
        self.expires = clock()+15
        self.index = 0
        self.finished = False
        self.failed = False
        self.inside_commit = False
        self.last_commit_at = None
        self.lock_hashes = self._lock_hashes()

    def _lock_hashes(self):
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest()
                     for p in self.motion_inhibit_paths)

    def check_recovery(self):
        if self.finished or self.failed or self.cancel_path.exists() or self.clock() >= self.expires:
            raise RuntimeError('Recovery finished, failed, cancelled or expired; no retry')
        if self._lock_hashes() != self.lock_hashes:
            raise RuntimeError('Incident lock changed')

    def _check_motion_allowed(self):
        if self.inside_commit:
            self.check_recovery()
        else:
            super()._check_motion_allowed()

    def expected_state(self):
        pulses = self.plan['expected_pulses_us'][:]
        if self.index:
            pulses[self.plan['channel']-1] = self.path[self.index-1]
        return pulses, (self.plan['expected_sequence']+self.index) & 0xffffffff

    def check_state(self):
        self.check_recovery()
        state = self.status()
        pulses, sequence = self.expected_state()
        mask = (1 << (self.plan['channel']-1)) if self.index else 0
        if (state['identity'] != 'SP10' or state['period_us'] != 20000
                or state['clock_hz'] != 100000000 or state['pending'] or state['faults']
                or state['armed'] != bool(self.index) or state['enabled_mask'] != mask
                or state['sequence'] != sequence or state['pulse_us'] != pulses):
            raise RuntimeError('Reviewed command state changed; no re-arm or retry')
        return state

    def commit(self, pulses, mask, allow_arm=False):
        self.check_recovery()
        if self.index >= len(self.path):
            raise RuntimeError('Finite jog already submitted')
        target = self.plan['expected_pulses_us'][:]
        target[self.plan['channel']-1] = self.path[self.index]
        if (pulses != target or mask != 1 << (self.plan['channel']-1)
                or allow_arm is not (self.index == 0)):
            raise RuntimeError('Only the next single-channel step is permitted')
        if self.last_commit_at is not None and self.clock()-self.last_commit_at < INTERVAL_SECONDS-1e-9:
            raise RuntimeError('Jog rate exceeded')
        self.check_state()
        self.inside_commit = True
        try:
            state = super().commit(pulses, mask, allow_arm=allow_arm)
        except BaseException:
            self.failed = True
            raise
        finally:
            self.inside_commit = False
        self.index += 1
        self.last_commit_at = self.clock()
        return state


def run_once(device, emit, *, clock=time.monotonic, sleep=time.sleep):
    completed = False
    def hold(seconds):
        deadline = clock()+seconds
        while clock() < deadline:
            device.check_state()
            device.kick()
            sleep(min(.04, max(0, deadline-clock())))
    try:
        for index, value in enumerate(device.path):
            if index:
                hold(INTERVAL_SECONDS)
            pulses = device.plan['expected_pulses_us'][:]
            pulses[device.plan['channel']-1] = value
            state = device.commit(pulses, 1 << (device.plan['channel']-1), allow_arm=index == 0)
            emit({'event': 'jog_step', 'channel': device.plan['channel'], 'step': index,
                  'state': state, 'position_feedback': None})
        hold(HOLD_SECONDS)
        completed = True
    finally:
        device.finished = True
        state = device.stop_after_frame() if completed else device.off()
        emit({'event': 'outputs_off', 'state': state, 'normal_frame_stop': completed,
              'incident_locks_removed': False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--execute-attended-unloaded-jog', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    path = pulse_path(plan)
    if not args.execute_attended_unloaded_jog:
        print(json.dumps({'dry_run': True, 'channel': plan['channel'], 'pulse_path_us': path,
                          'interval_seconds': INTERVAL_SECONDS, 'hold_seconds': HOLD_SECONDS}))
        return
    registers = Registers()
    try:
        device = RecoveryJogDevice(registers, plan)
        run_once(device, lambda event: print(json.dumps(event), flush=True))
    finally:
        registers.close()


if __name__ == '__main__':
    main()
