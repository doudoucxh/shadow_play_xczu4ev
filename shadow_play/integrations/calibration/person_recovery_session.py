#!/usr/bin/env python3
"""Attended person recovery with a continuous hold across rod reconnection.

Only released axes 1..4 and a single free connection on axes 5/6 can start.
Incident locks remain intact. No saved command is used as shaft feedback.
After recovery, each loaded path requires a separate visual review before demo.
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

APPROVAL = 'released-person-continuous-recovery-20261012'
REFERENCE = [1537, 1352, 1537, 1574, 1508, 1500]
INTERVAL = .125
PROBE_OFFSETS = {1:12, 2:-12, 3:12, 4:12, 5:12, 6:12}
DEMO_AXES = (5, 6, 3, 1, 2)


class ObservationLost(RuntimeError):
    pass


def validate_plan(p):
    fields = {'approval','session_id','expected_sequence','expected_pulses_us',
              'axes_1_to_4_released','axes_5_6_single_free_connection',
              'clearance_reviewed','observer_ready','duration_seconds'}
    if not isinstance(p,dict) or set(p)!=fields or p['approval']!=APPROVAL:
        raise ValueError('Exact released-person recovery plan required')
    if not isinstance(p['session_id'],str) or not re.fullmatch('[a-z0-9-]{1,40}',p['session_id']):
        raise ValueError('Session ID required')
    if any(p[k] is not True for k in ('axes_1_to_4_released',
            'axes_5_6_single_free_connection','clearance_reviewed','observer_ready')):
        raise ValueError('Released loads, one free connection, clearance and observer required')
    if type(p['expected_sequence']) is not int or not 0<=p['expected_sequence']<2**32:
        raise ValueError('Inspected OFF sequence required')
    pulses=p['expected_pulses_us']
    if not isinstance(pulses,list) or len(pulses)!=10 or any(type(v) is not int or not 500<=v<=2500 for v in pulses):
        raise ValueError('Ten inspected command values required; no position feedback')
    if type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=900:
        raise ValueError('Attended session limited to 120..900 seconds')


class HostControl:
    def __init__(self,fd,clock=time.monotonic,*,max_stage=6):
        if type(max_stage) is not int or not 1<=max_stage<=8:
            raise ValueError('Protocol stage count must be between one and eight')
        self.fd=fd;self.clock=clock;self.last=clock();self.received=False
        self.buffer=b'';self.action=None
        self.action_pattern=re.compile((': # PERSON_RECOVERY_ACTION '
            '(reconnected|probe_[1-%d]|review_[1-%d]|demo|finish) ([0-9]{1,10})'
            %(max_stage,max_stage)).encode('ascii'))

    def check(self):
        if select.select([self.fd],[],[],0)[0]:
            data=os.read(self.fd,1024)
            if not data:raise ObservationLost('Host input closed')
            self.buffer+=data
            while b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1);line=line.strip()
                if line==b': # PERSON_RECOVERY_LEASE':
                    self.last=self.clock();self.received=True
                elif line==b': # PERSON_RECOVERY_VIDEO_STOP':
                    raise ObservationLost('Video unavailable')
                else:
                    match=self.action_pattern.fullmatch(line)
                    if not match or self.action is not None:raise RuntimeError('Unexpected or concurrent host action')
                    self.action=(match[1].decode(),int(match[2]))
            if len(self.buffer)>150:raise RuntimeError('Oversized host input')
        if self.clock()-self.last>1.5:raise ObservationLost('Host/video lease expired')


class RecoverySession(PwmDevice):
    def __init__(self,r,plan,host,*,motion_inhibit_paths=None,
                 cancel_path='/run/shadow-pwm-recovery-cancel',clock=time.monotonic):
        validate_plan(plan);super().__init__(r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan));self.host=host;self.clock=clock
        self.deadline=clock()+plan['duration_seconds'];self.cancel=Path(cancel_path)
        self.hashes=self.lock_hashes();self.pulses=plan['expected_pulses_us'][:]
        self.sequence=plan['expected_sequence'];self.mask=0;self.inside=False
        self.phase='initializing';self.last_commit=None;self.probed=set();self.reviewed=set()
        self.reconnected=False;self.demo_used=False;self.failed=False

    def lock_hashes(self):
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in self.motion_inhibit_paths)

    def check(self):
        if self.failed or self.cancel.exists() or self.lock_hashes()!=self.hashes:
            raise RuntimeError('Cancelled, failed or incident lock changed')
        s=self.status()
        if (s['period_us']!=20000 or s['clock_hz']!=100000000 or s['faults'] or s['pending']
                or s['armed']!=bool(self.mask) or s['enabled_mask']!=self.mask
                or s['pulse_us']!=self.pulses or s['sequence']!=self.sequence):
            raise RuntimeError('PWM state changed; no rearm or retry')
        self.host.check()
        return s

    def _check_motion_allowed(self):
        if self.inside:self.check()
        else:super()._check_motion_allowed()

    def adopt(self,pulses,mask):
        self.check()
        if self.clock()>=self.deadline:raise RuntimeError('Session expired before command')
        if len(pulses)!=10 or pulses[6:]!=self.pulses[6:] or mask&~63:
            raise RuntimeError('Tiger outputs and commands cannot change')
        if self.phase=='initializing':
            channel=self.mask.bit_length()+1
            expected=self.pulses[:];expected[channel-1]=1500
            if channel>6 or mask!=(1<<channel)-1 or pulses!=expected:
                raise RuntimeError('Only the next released axis may be centered')
        else:
            if mask!=63 or any(not 1300<=v<=1700 for v in pulses[:6]):
                raise RuntimeError('Person recovery window exceeded')
            changed=[i for i,(a,b) in enumerate(zip(pulses,self.pulses)) if a!=b]
            if len(changed)>1 or any(abs(pulses[i]-self.pulses[i])>1 for i in changed):
                raise RuntimeError('Only one axis and one microsecond per step')
            if self.phase=='reference':
                for i in changed:
                    if not min(1500,REFERENCE[i])<=pulses[i]<=max(1500,REFERENCE[i]):
                        raise RuntimeError('Outside released recovery path')
            elif self.phase=='probe':
                for i,value in enumerate(pulses[:6]):
                    offset=PROBE_OFFSETS[self.active_axis] if i==self.active_axis-1 else 0
                    if not min(REFERENCE[i],REFERENCE[i]+offset)<=value<=max(REFERENCE[i],REFERENCE[i]+offset):
                        raise RuntimeError('Outside current single-axis probe path')
            else:raise RuntimeError('No targets may change during static hold')
            if self.last_commit is not None and self.clock()-self.last_commit<INTERVAL-1e-9:
                raise RuntimeError('Cannot accelerate to catch up')
        self.inside=True
        try:state=super().commit(pulses,mask,allow_arm=self.mask==0)
        except BaseException:self.failed=True;raise
        finally:self.inside=False
        self.pulses=pulses[:];self.mask=mask;self.sequence=state['sequence'];self.last_commit=self.clock()
        return state

    def wait(self,seconds,sleep):
        end=self.clock()+seconds
        while self.clock()<end:
            self.check();self.kick()
            if self.clock()>=self.deadline:raise ObservationLost('Attended session duration ended')
            sleep(min(.03,max(0,end-self.clock())))

    def probe(self,axis,emit,sleep):
        self.phase='probe';self.active_axis=axis
        for step in range(1,65):
            self.wait(INTERVAL,sleep)
            pulses=self.pulses[:]
            pulses[axis-1]=REFERENCE[axis-1]+round(PROBE_OFFSETS[axis]*.5*(1-math.cos(2*math.pi*step/64)))
            emit({'event':'probe_step','axis':axis,'step':step,'state':self.adopt(pulses,63)})
        self.phase='holding';self.probed.add(axis)
        emit({'event':'probe_complete','axis':axis,'state':self.check()})


def run_session(d,emit,*,sleep=time.sleep):
    frame_stop=False
    try:
        for axis in range(1,7):
            if d.host.action is not None:raise RuntimeError('Action received before recovery complete')
            pulses=d.pulses[:];pulses[axis-1]=1500
            emit({'event':'axis_centered','axis':axis,'state':d.adopt(pulses,(1<<axis)-1),
                  'position_feedback':None})
            d.wait(3,sleep)
        d.phase='reference'
        for axis,target in enumerate(REFERENCE):
            while d.pulses[axis]!=target:
                d.wait(INTERVAL,sleep);pulses=d.pulses[:]
                pulses[axis]+=1 if target>pulses[axis] else -1
                emit({'event':'reference_step','axis':axis+1,'state':d.adopt(pulses,63)})
        d.phase='holding';emit({'event':'reference_held','state':d.check(),
            'remaining_seconds':max(0,d.deadline-d.clock()),'incident_locks_removed':False})
        next_report=d.clock()+1
        while d.clock()<d.deadline:
            d.check();d.kick()
            if d.host.action is not None:
                action,sequence=d.host.action;d.host.action=None
                if sequence!=d.sequence:raise RuntimeError('Stale action sequence; no retry')
                if action=='finish':frame_stop=True;break
                if action=='reconnected':
                    if d.reconnected:raise RuntimeError('Reconnection already recorded')
                    d.reconnected=True
                    emit({'event':'reconnection_recorded','state':d.check()})
                elif action.startswith('probe_'):
                    if not d.reconnected:raise RuntimeError('Loaded linkage review required')
                    d.probe(int(action[-1]),emit,sleep)
                elif action.startswith('review_'):
                    axis=int(action[-1])
                    if axis not in d.probed:raise RuntimeError('Unobserved probe cannot be reviewed')
                    d.reviewed.add(axis);emit({'event':'path_reviewed','axis':axis,'state':d.check()})
                elif action=='demo':
                    if d.demo_used or not set(DEMO_AXES)<=d.reviewed:
                        raise RuntimeError('New loaded paths require review; demo is one-use')
                    d.demo_used=True
                    for axis in DEMO_AXES:d.probe(axis,emit,sleep)
                    emit({'event':'demo_complete','state':d.check()})
            if d.clock()>=next_report:
                emit({'event':'hold_alive','state':d.check(),'remaining_seconds':max(0,d.deadline-d.clock())})
                next_report=d.clock()+1
            d.wait(.03,sleep)
        frame_stop=True
    except ObservationLost:
        frame_stop=True;raise
    finally:
        state=d.stop_after_frame() if frame_stop else d.off()
        emit({'event':'outputs_off','state':state,'normal_frame_stop':frame_stop,'incident_locks_removed':False})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan',type=Path)
    p.add_argument('--execute-released-person-recovery',action='store_true');a=p.parse_args()
    plan=json.loads(a.plan.read_text());validate_plan(plan)
    if not a.execute_released_person_recovery:
        print(json.dumps({'dry_run':True,'reference_us':REFERENCE,'duration_seconds':plan['duration_seconds'],
                          'initialization_requires_released_load':True}));return
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostControl(sys.stdin.fileno());print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=Registers()
    try:
        d=RecoverySession(r,plan,host)
        run_session(d,lambda row:print(json.dumps(row),flush=True))
    finally:r.close()


if __name__=='__main__':main()
