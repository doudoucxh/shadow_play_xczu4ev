#!/usr/bin/env python3
"""One attended 8-us person-axis probe after rod reattachment at a reviewed pose.

All six person axes stay enabled together. The selected axis moves once and
returns; tiger axes never enable. This is not a trajectory player or calibration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import time

from servo_pwm_device import PwmDevice, Registers

APPROVAL = 'attended-person-local-probe'


def validate_plan(p):
    fields = {'approval','reference_session','channel','target_us','expected_sequence',
              'expected_pulses_us','rods_connected_without_moving_axes','observer_ready','views_reviewed'}
    if not isinstance(p,dict) or set(p)!=fields or p['approval']!=APPROVAL:
        raise ValueError('Exact reviewed person probe plan required')
    if not isinstance(p['reference_session'],str) or not p['reference_session'].strip():
        raise ValueError('Reviewed static reference session required')
    if any(p[k] is not True for k in ('rods_connected_without_moving_axes','observer_ready','views_reviewed')):
        raise ValueError('Reattachment, attendance and views must be reviewed')
    if type(p['channel']) is not int or not 1<=p['channel']<=6:
        raise ValueError('Person axes 1..6 only')
    if type(p['expected_sequence']) is not int or not 0<=p['expected_sequence']<2**32:
        raise ValueError('Inspected sequence required')
    pulses=p['expected_pulses_us']
    if not isinstance(pulses,list) or len(pulses)!=10 or any(type(v) is not int or not 500<=v<=2500 for v in pulses):
        raise ValueError('Ten inspected integer pulses required')
    if any(not 1300<=v<=1700 for v in pulses[:6]):
        raise ValueError('Person reference outside recovery window')
    target=p['target_us']; start=pulses[p['channel']-1]
    if type(target) is not int or not 1300<=target<=1700 or not 0<abs(target-start)<=8:
        raise ValueError('One probe must change only 1..8 us')


class PersonProbeDevice(PwmDevice):
    def __init__(self, registers, plan, *, motion_inhibit_paths=None,
                 cancel_path='/run/shadow-pwm-recovery-cancel',clock=time.monotonic):
        validate_plan(plan)
        super().__init__(registers,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan)); self.clock=clock
        self.expires=clock()+12; self.cancel=Path(cancel_path)
        self.lock_hashes=self._hashes(); self.index=0; self.failed=False; self.inside=False
        start=plan['expected_pulses_us'][:]; target=start[:]
        target[plan['channel']-1]=plan['target_us']
        self.path=[start,target,start]
        self.last_commit=None

    def _hashes(self):
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in self.motion_inhibit_paths)

    def check(self):
        if self.failed or self.cancel.exists() or self.clock()>=self.expires or self._hashes()!=self.lock_hashes:
            raise RuntimeError('Probe failed, cancelled, expired or incident lock changed')
        s=self.status(); active=self.index>0
        expected=self.path[self.index-1] if active else self.path[0]
        if (s['period_us']!=20000 or s['clock_hz']!=100000000 or s['pending'] or s['faults']
                or s['armed']!=active or s['enabled_mask']!=(63 if active else 0)
                or s['pulse_us']!=expected or s['sequence']!=(self.plan['expected_sequence']+self.index)%2**32):
            raise RuntimeError('Probe command state changed; no rearm or retry')
        return s

    def _check_motion_allowed(self):
        if self.inside:self.check()
        else:super()._check_motion_allowed()

    def commit(self,pulses,mask,allow_arm=False):
        self.check()
        if (self.index>=3 or pulses!=self.path[self.index] or mask!=63
                or allow_arm is not (self.index==0)):
            raise RuntimeError('Only the next fixed probe step is allowed')
        if self.last_commit is not None and self.clock()-self.last_commit<1.-1e-9:
            raise RuntimeError('One second settling interval required')
        self.inside=True
        try:s=super().commit(pulses,mask,allow_arm)
        except BaseException:
            self.failed=True
            raise
        finally:self.inside=False
        self.index+=1; self.last_commit=self.clock()
        return s


def run_once(device,emit,*,clock=time.monotonic,sleep=time.sleep):
    completed=False
    try:
        for i,pulses in enumerate(device.path):
            s=device.commit(pulses,63,allow_arm=i==0)
            emit({'event':'person_probe_step','step':i,'state':s,'monotonic_seconds':clock()})
            deadline=clock()+(1.2 if i==2 else 1.)
            while clock()<deadline:
                device.check(); device.kick(); sleep(min(.04,max(0,deadline-clock())))
        completed=True
    finally:
        s=device.stop_after_frame() if completed else device.off()
        emit({'event':'outputs_off','state':s,'normal_frame_stop':completed,'incident_locks_removed':False})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path)
    parser.add_argument('--execute-attended-person-probe',action='store_true')
    args=parser.parse_args(); plan=json.loads(args.plan.read_text());validate_plan(plan)
    if not args.execute_attended_person_probe:
        print(json.dumps({'dry_run':True,'channel':plan['channel'],'target_us':plan['target_us']}));return
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    r=Registers()
    try:run_once(PersonProbeDevice(r,plan),lambda row:print(json.dumps(row),flush=True))
    finally:r.close()


if __name__=='__main__':main()
