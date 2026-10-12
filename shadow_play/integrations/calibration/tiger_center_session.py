"""Explicit attended loaded-tiger centering, with incident locks retained.

This exception accepts only sequential 1500-us centering of axes 7..10.
The initial register values are concurrency guards, never shaft feedback.
The first activation from an unknown position is not a gradual return.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import sys
import time

from person_recovery_session import HostControl, ObservationLost
from servo_pwm_device import PwmDevice, Registers

APPROVAL = 'attended-loaded-tiger-centering-20261012'


def validate_plan(p, wall=None):
    fields = {'approval','session_id','expected_sequence','expected_pulses_us',
              'observer_ready','loaded_centering_explicitly_authorized',
              'dual_view_clearance_reviewed','reviewed_at_unix_ms','duration_seconds'}
    if not isinstance(p,dict) or set(p)!=fields or p['approval']!=APPROVAL:
        raise ValueError('Exact explicit loaded-tiger centering plan required')
    if not isinstance(p['session_id'],str) or not re.fullmatch('[a-z0-9-]{1,80}',p['session_id']):
        raise ValueError('Unique safe session ID required')
    if any(p[k] is not True for k in ('observer_ready','loaded_centering_explicitly_authorized','dual_view_clearance_reviewed')):
        raise ValueError('Explicit loaded-centering authorization, observer and dual views required')
    if type(p['expected_sequence']) is not int or not 0<=p['expected_sequence']<2**32:
        raise ValueError('Inspected OFF sequence required')
    values=p['expected_pulses_us']
    if not isinstance(values,list) or len(values)!=10 or any(type(v) is not int or not 500<=v<=2500 for v in values):
        raise ValueError('Ten inspected command registers required, not angle feedback')
    # Windows verifies the host timestamp before launch. The board wall clock
    # is not synchronized; ongoing camera/host leases use monotonic time.
    if type(p['reviewed_at_unix_ms']) is not int or p['reviewed_at_unix_ms']<=0:
        raise ValueError('Scene review timestamp required')
    if wall is not None and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000:
        raise ValueError('Fresh scene review required')
    if type(p['duration_seconds']) is not int or not 60<=p['duration_seconds']<=600:
        raise ValueError('Attended centering duration limited to 60..600 seconds')


class TigerCenterSession(PwmDevice):
    def __init__(self,r,plan,host,*,motion_inhibit_paths=None,
                 cancel_path='/run/shadow-pwm-recovery-cancel',clock=time.monotonic,wall=None):
        validate_plan(plan,wall);super().__init__(r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan));self.host=host;self.clock=clock
        self.deadline=clock()+plan['duration_seconds'];self.cancel=Path(cancel_path)
        self.hashes=self.lock_hashes();self.pulses=plan['expected_pulses_us'][:]
        self.sequence=plan['expected_sequence'];self.mask=0;self.inside=False
        self.completed=0;self.failed=False

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

    def center(self,stage,emit,sleep=time.sleep):
        self.check()
        if type(stage) is not int or stage!=self.completed+1 or not 1<=stage<=4:
            raise RuntimeError('Center only the next tiger axis, once')
        if self.clock()>=self.deadline:
            raise ObservationLost('Attended duration expired')
        pulses=self.pulses[:];axis=stage+6;pulses[axis-1]=1500
        mask=((1<<stage)-1)<<6
        self.inside=True
        try:s=super().commit(pulses,mask,allow_arm=self.mask==0)
        except BaseException:self.failed=True;raise
        finally:self.inside=False
        self.pulses=pulses;self.mask=mask;self.sequence=s['sequence']
        emit({'event':'axis_centered','axis':axis,'state':s,'position_feedback':None,
              'startup_is_not_rate_limited':True,'incident_locks_removed':False})
        self.wait(3,sleep)
        self.completed=stage
        emit({'event':'probe_complete','axis':stage,'centered_servo':axis,'state':self.check()})

    def wait(self,seconds,sleep=time.sleep):
        end=self.clock()+seconds
        while self.clock()<end:
            self.check();self.kick()
            if self.clock()>=self.deadline:raise ObservationLost('Attended duration expired')
            sleep(min(.03,max(0,end-self.clock())))


def run_session(d,emit,*,sleep=time.sleep):
    normal=False
    try:
        emit({'event':'reference_held','phase':'await_sequential_centering','state':d.check(),
              'position_feedback':None,'incident_locks_removed':False})
        report=d.clock()+1
        while d.clock()<d.deadline:
            d.check();d.kick()
            if d.host.action is not None:
                action,sequence=d.host.action;d.host.action=None
                if sequence!=d.sequence:raise RuntimeError('Stale action; no retry')
                if action=='finish':normal=True;break
                if not re.fullmatch('probe_[1-4]',action):
                    raise RuntimeError('Only sequential centering or finish is authorized')
                d.center(int(action[-1]),emit,sleep)
                if d.completed==4:
                    emit({'event':'center_reference_held','state':d.check(),'position_feedback':None,
                          'incident_locks_removed':False})
            if d.clock()>=report:
                emit({'event':'hold_alive','state':d.check(),'centered_axes':list(range(7,7+d.completed)),
                      'remaining_seconds':max(0,d.deadline-d.clock())})
                report=d.clock()+1
            d.wait(.03,sleep)
        normal=True
    except ObservationLost:
        normal=True;raise
    finally:
        s=d.stop_after_frame() if normal else d.off()
        emit({'event':'outputs_off','state':s,'normal_frame_stop':normal,'incident_locks_removed':False})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan',type=Path)
    p.add_argument('--expected-plan-sha256',required=True)
    p.add_argument('--execute-attended-loaded-centering',action='store_true');a=p.parse_args()
    raw=a.plan.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=a.expected_plan_sha256:raise ValueError('Reviewed plan hash mismatch')
    plan=json.loads(raw);validate_plan(plan)
    if not a.execute_attended_loaded_centering:
        print(json.dumps({'dry_run':True,'axes':[7,8,9,10],'target_us':1500,
                          'initial_position_unknown':True,'startup_is_not_rate_limited':True}));return
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostControl(sys.stdin.fileno());print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=Registers()
    try:run_session(TigerCenterSession(r,plan,host),lambda row:print(json.dumps(row),flush=True))
    finally:r.close()


if __name__=='__main__':main()
