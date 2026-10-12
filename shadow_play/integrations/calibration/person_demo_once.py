#!/usr/bin/env python3
"""One attended 70-second person gesture, limited to the tested single-axis paths.

This session-bound demonstration is not a general trajectory/replay interface.
Every phrase returns its command to the reference before the next axis moves.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import select
import signal
import sys
import time

from servo_pwm_device import PwmDevice, Registers

REFERENCE = [1537,1352,1537,1574,1508,1500,1500,1426,1500,1500]
PHRASES = [('right_sweep',5,24,10),('right_lower',6,24,10),
           ('head_turn',3,24,10),('head_nod',4,48,20),
           ('left_sweep',1,24,10),('left_lower',2,-24,10)]
INTERVAL = .125
APPROVAL = 'attended-person-demo-once-20261011'


class VideoLeaseUnavailable(RuntimeError):
    """Stop at the next PWM frame boundary without changing the last target."""


def validate_plan(p):
    fields={'approval','expected_sequence','expected_pulses_us','reference_session',
            'observer_ready','views_reviewed','mechanism_unchanged'}
    if not isinstance(p,dict) or set(p)!=fields or p['approval']!=APPROVAL:
        raise ValueError('Exact session-bound demo plan required')
    if type(p['expected_sequence']) is not int or not 0<=p['expected_sequence']<2**32:
        raise ValueError('Inspected OFF sequence required')
    if p['expected_pulses_us']!=REFERENCE or any(type(v) is not int for v in p['expected_pulses_us']):
        raise ValueError('Only the reviewed person assembly command reference is supported')
    if not isinstance(p['reference_session'],str) or not p['reference_session'].strip():
        raise ValueError('Physical session reference required')
    if any(p[k] is not True for k in ('observer_ready','views_reviewed','mechanism_unchanged')):
        raise ValueError('Attended unchanged mechanism and reviewed views required')


def trajectory():
    rows=[('initial',REFERENCE[:])]
    for name,ch,amplitude,seconds in PHRASES:
        count=round(seconds/INTERVAL)
        for i in range(1,count+1):
            pulses=REFERENCE[:]
            pulses[ch-1]+=round(amplitude*.5*(1-math.cos(2*math.pi*i/count)))
            rows.append((name,pulses))
    return rows


class HostLease:
    def __init__(self,fd,clock=time.monotonic):
        self.fd=fd;self.clock=clock;self.last=clock();self.received=False;self.buffer=b''

    def check(self):
        if select.select([self.fd],[],[],0)[0]:
            data=os.read(self.fd,1024)
            if not data:raise VideoLeaseUnavailable('Host input closed')
            self.buffer+=data
            while b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                if line.strip()==b': # PERSON_DEMO_VIDEO_STOP':
                    raise VideoLeaseUnavailable('Host reported unavailable video')
                if line.strip()!=b': # PERSON_DEMO_LEASE':raise RuntimeError('Unexpected host input')
                self.last=self.clock();self.received=True
            if len(self.buffer)>100:raise RuntimeError('Oversized lease input')
        if self.clock()-self.last>1.5:raise VideoLeaseUnavailable('Host/video lease expired')


class DemoDevice(PwmDevice):
    def __init__(self,r,plan,*,lease_check,motion_inhibit_paths=None,
                 cancel_path='/run/shadow-pwm-recovery-cancel',clock=time.monotonic):
        validate_plan(plan)
        super().__init__(r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan));self.path=trajectory();self.index=0
        self.clock=clock;self.expires=clock()+90;self.lease_check=lease_check
        self.cancel=Path(cancel_path);self.lock_hashes=self._hashes()
        self.inside=False;self.failed=False;self.last_commit=None

    def _hashes(self):
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in self.motion_inhibit_paths)

    def check(self):
        if self.failed or self.cancel.exists() or self.clock()>=self.expires or self._hashes()!=self.lock_hashes:
            raise RuntimeError('Demo cancelled, expired, failed or incident lock changed')
        s=self.status();active=self.index>0
        expected=self.path[self.index-1][1] if active else REFERENCE
        if (s['period_us']!=20000 or s['clock_hz']!=100000000 or s['faults'] or s['pending']
            or s['armed']!=active or s['enabled_mask']!=(63 if active else 0)
            or s['pulse_us']!=expected or s['sequence']!=(self.plan['expected_sequence']+self.index)%2**32):
            raise RuntimeError('Demo state changed; no rearm or retry')
        self.lease_check()
        return s

    def _check_motion_allowed(self):
        if self.inside:self.check()
        else:super()._check_motion_allowed()

    def commit(self,pulses,mask,allow_arm=False):
        self.check()
        if self.index>=len(self.path) or pulses!=self.path[self.index][1] or mask!=63 or allow_arm is not (self.index==0):
            raise RuntimeError('Only the next fixed demonstration step is permitted')
        if self.last_commit is not None and self.clock()-self.last_commit<INTERVAL-1e-9:
            raise RuntimeError('Demo cannot accelerate to catch up')
        self.inside=True
        try:state=super().commit(pulses,mask,allow_arm)
        except BaseException:
            self.failed=True;raise
        finally:self.inside=False
        self.index+=1;self.last_commit=self.clock()
        return state


def run_once(device,emit,*,clock=time.monotonic,sleep=time.sleep):
    frame_stop=False;last_label=None
    try:
        for i,(label,pulses) in enumerate(device.path):
            state=device.commit(pulses,63,allow_arm=i==0)
            emit({'event':'demo_step','step':i,'label':label,'state':state,'monotonic_seconds':clock()})
            if label!=last_label:
                emit({'event':'phrase_begin','label':label,'step':i,'state':state})
                last_label=label
            until=clock()+(1. if i==len(device.path)-1 else INTERVAL)
            while clock()<until:
                device.check();device.kick();sleep(min(.03,max(0,until-clock())))
        frame_stop=True
    except VideoLeaseUnavailable:
        # Loss of observation is a stop request, not a new angle command.
        # Hardware/cancel faults are checked first and still use emergency OFF.
        frame_stop=True
        raise
    finally:
        state=device.stop_after_frame() if frame_stop else device.off()
        emit({'event':'outputs_off','state':state,'normal_frame_stop':frame_stop,'incident_locks_removed':False})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan',type=Path)
    p.add_argument('--execute-attended-demo',action='store_true');a=p.parse_args()
    plan=json.loads(a.plan.read_text());validate_plan(plan)
    if not a.execute_attended_demo:
        print(json.dumps({'dry_run':True,'steps':len(trajectory()),'nominal_seconds':71,
                          'max_adjacent_us':1,'mask':63,'phrases':PHRASES}));return
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    lease=HostLease(sys.stdin.fileno());print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not lease.received:lease.check();time.sleep(.02)
    r=Registers()
    try:
        d=DemoDevice(r,plan,lease_check=lease.check)
        run_once(d,lambda row:print(json.dumps(row),flush=True))
    finally:r.close()


if __name__=='__main__':main()
