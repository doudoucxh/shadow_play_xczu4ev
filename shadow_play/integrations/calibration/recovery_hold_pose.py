#!/usr/bin/env python3
"""Attended static assembly hold; never changes adopted pulse values.

Selected person axes must already have observed, reviewed starting poses.
Incident locks remain present. This program cannot jog or enable tiger axes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import time

from servo_pwm_device import PwmDevice, Registers

APPROVAL = 'attended-static-assembly-hold'


def validate_plan(plan):
    fields = {'approval', 'session_id', 'channels', 'expected_sequence',
              'expected_pulses_us', 'duration_seconds', 'start_poses_reviewed',
              'observer_ready', 'assembly_clearance_reviewed'}
    if not isinstance(plan, dict) or set(plan) != fields or plan['approval'] != APPROVAL:
        raise ValueError('Exact attended assembly plan required')
    if not isinstance(plan['session_id'], str) or not re.fullmatch('[a-z0-9-]{1,40}', plan['session_id']):
        raise ValueError('Invalid session identifier')
    if plan['channels'] not in ([1,2,3,4], [1,2,3,4,5,6]) or any(
            type(c) is not int for c in plan['channels']):
        raise ValueError('Hold only reviewed person gimbals, never tiger axes')
    if any(plan[k] is not True for k in ('start_poses_reviewed','observer_ready','assembly_clearance_reviewed')):
        raise ValueError('Reviewed poses, clearance and attendance required')
    if type(plan['expected_sequence']) is not int or not 0 <= plan['expected_sequence'] < 2**32:
        raise ValueError('Inspected sequence required')
    pulses = plan['expected_pulses_us']
    if not isinstance(pulses,list) or len(pulses)!=10 or any(type(p) is not int or not 500<=p<=2500 for p in pulses):
        raise ValueError('Ten command register values required')
    if any(not 1300<=pulses[c-1]<=1700 for c in plan['channels']):
        raise ValueError('Reviewed recovery pulse window exceeded')
    if type(plan['duration_seconds']) is not int or not 1<=plan['duration_seconds']<=300:
        raise ValueError('Static hold limited to at most five minutes')


class PoseHoldDevice(PwmDevice):
    def __init__(self, registers, plan, *, motion_inhibit_paths=None,
                 cancel_root='/run', clock=time.monotonic):
        validate_plan(plan)
        super().__init__(registers, motion_inhibit_paths=motion_inhibit_paths)
        self.plan = json.loads(json.dumps(plan))
        self.mask = sum(1 << (c-1) for c in plan['channels'])
        self.clock = clock
        self.expires = clock()+plan['duration_seconds']+5
        self.cancel_path = Path(cancel_root)/('shadow-pwm-hold-'+plan['session_id']+'.cancel')
        self.global_cancel = Path(cancel_root)/'shadow-pwm-recovery-cancel'
        self.lock_hashes = self._lock_hashes()
        self.used = False
        self.inside_commit = False

    def _lock_hashes(self):
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in self.motion_inhibit_paths)

    def check_hold(self):
        if self.cancel_path.exists() or self.global_cancel.exists() or self.clock()>=self.expires:
            raise RuntimeError('Assembly hold cancelled or expired')
        if self._lock_hashes()!=self.lock_hashes:
            raise RuntimeError('Incident lock changed')

    def _check_motion_allowed(self):
        if self.inside_commit:
            self.check_hold()
        else:
            super()._check_motion_allowed()

    def check_state(self, *, active):
        self.check_hold()
        s = self.status()
        if (s['identity']!='SP10' or s['clock_hz']!=100000000 or s['period_us']!=20000
                or s['pending'] or s['faults'] or s['armed']!=active
                or s['enabled_mask']!=(self.mask if active else 0)
                or s['sequence']!=(self.plan['expected_sequence']+int(active))%2**32
                or s['pulse_us']!=self.plan['expected_pulses_us']):
            raise RuntimeError('Assembly hold state changed; do not re-arm')
        return s

    def commit(self, pulses, mask, allow_arm=False):
        if self.used or pulses!=self.plan['expected_pulses_us'] or mask!=self.mask or allow_arm is not True:
            raise RuntimeError('Only one unchanged-pulse static hold is permitted')
        self.check_state(active=False)
        self.used = True
        self.inside_commit = True
        try:
            return super().commit(pulses,mask,allow_arm=True)
        finally:
            self.inside_commit = False


def run_hold(device, emit, *, clock=time.monotonic, sleep=time.sleep):
    try:
        state = device.commit(device.plan['expected_pulses_us'],device.mask,allow_arm=True)
        emit({'event':'hold_started','state':state,'duration_seconds':device.plan['duration_seconds'],
              'cancel_path':str(device.cancel_path),'position_feedback':None})
        deadline = clock()+device.plan['duration_seconds']
        while clock()<deadline:
            device.check_state(active=True)
            device.kick()
            sleep(min(.04,max(0,deadline-clock())))
    finally:
        emit({'event':'outputs_off','state':device.off(),'incident_locks_removed':False})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan',type=Path)
    p.add_argument('--execute-attended-static-hold',action='store_true')
    args=p.parse_args()
    plan=json.loads(args.plan.read_text(encoding='utf-8'));validate_plan(plan)
    if not args.execute_attended_static_hold:
        print(json.dumps({'dry_run':True,'channels':plan['channels'],'duration_seconds':plan['duration_seconds']}))
        return
    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,interrupt)
    signal.signal(signal.SIGINT,interrupt)
    registers=Registers()
    try:
        device=PoseHoldDevice(registers,plan)
        run_hold(device,lambda row:print(json.dumps(row),flush=True))
    finally:
        registers.close()


if __name__=='__main__':main()
