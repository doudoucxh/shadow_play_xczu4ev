"""Attended, unchanged-pose continuation after a verified normal session stop.

This is NOT recovery from an unknown/manual pose. A new operator report and
fresh dual-view comparison are required; saved register values alone never
authorize startup. Incident locks remain in place. Only right-hand axes 5/6
are explored, one at a time, in reviewed 40/80/120-us stages.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import time

from person_recovery_session import RecoverySession, HostControl, ObservationLost, REFERENCE
from servo_pwm_device import PwmDevice, Registers

APPROVAL = 'attended-unchanged-person-continuation-20261012'
LEVELS = (40, 80, 120)
INTERVAL = .05


def validate_plan(plan, wall=None):
    fields = {'approval', 'session_id', 'expected_sequence', 'expected_pulses_us',
              'operator_unchanged_report', 'observer_ready', 'dual_view_pose_reviewed',
              'reviewed_at_unix_ms', 'previous_held_state', 'previous_off_state',
              'previous_normal_frame_stop', 'duration_seconds'}
    if not isinstance(plan, dict) or set(plan) != fields or plan['approval'] != APPROVAL:
        raise ValueError('Exact attended continuation receipt required')
    if plan['operator_unchanged_report'] != '电源和机构都没动':
        raise ValueError('New operator report required; no manual-pose reset')
    if plan['observer_ready'] is not True or plan['dual_view_pose_reviewed'] is not True:
        raise ValueError('Onsite cutoff and fresh physical pose review required')
    if type(plan['reviewed_at_unix_ms']) is not int or plan['reviewed_at_unix_ms'] <= 0:
        raise ValueError('Host comparison timestamp required')
    # Host wall time is verified by the Windows launcher. Zynq's un-synchronized
    # wall clock must not be compared with it; live leases use monotonic time.
    if wall is not None and not 0 <= wall()*1000-plan['reviewed_at_unix_ms'] < 120000:
        raise ValueError('Physical comparison receipt expired')
    if type(plan['duration_seconds']) is not int or not 120 <= plan['duration_seconds'] <= 900:
        raise ValueError('Attended duration must be 120..900 seconds')
    held, off = plan['previous_held_state'], plan['previous_off_state']
    pulses = plan['expected_pulses_us']
    if (not isinstance(pulses, list) or len(pulses) != 10 or pulses[:6] != REFERENCE
            or any(type(v) is not int or not 500 <= v <= 2500 for v in pulses)):
        raise ValueError('Only the previous inspected person reference is allowed')
    if (plan['previous_normal_frame_stop'] is not True or held['enabled_mask'] != 63
            or held['armed'] is not True or off['enabled_mask'] != 0 or off['armed'] is not False
            or held['pulse_us'] != pulses or off['pulse_us'] != pulses
            or held['faults'] or held['pending'] or off['faults'] or off['pending']
            or type(plan['expected_sequence']) is not int
            or off['sequence'] != plan['expected_sequence']
            or off['sequence'] != (held['sequence']+1) % 2**32):
        raise ValueError('Previous normal held-to-OFF transition not verified')


class VisibleSession(RecoverySession):
    def __init__(self, registers, plan, host, *, motion_inhibit_paths=None,
                 cancel_path='/run/shadow-pwm-recovery-cancel', clock=time.monotonic,
                 wall=None):
        validate_plan(plan, wall)
        PwmDevice.__init__(self, registers, motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan)); self.host=host; self.clock=clock
        self.deadline=clock()+plan['duration_seconds']; self.cancel=Path(cancel_path)
        self.hashes=self.lock_hashes(); self.pulses=plan['expected_pulses_us'][:]
        self.sequence=plan['expected_sequence']; self.mask=0; self.inside=False
        self.failed=False; self.phase='resume'; self.last_commit=None
        self.completed={}; self.reviewed={}; self.demo_used=False
        self.active_axis=None; self.active_offset=0

    def adopt(self, pulses, mask):
        self.check()
        if self.clock() >= self.deadline or mask != 63 or len(pulses) != 10:
            raise RuntimeError('Expired or invalid person-only command')
        base=self.plan['expected_pulses_us']
        if self.phase == 'resume':
            if self.mask or pulses != base:
                raise RuntimeError('Resume can enable the inspected reference only once')
        elif self.phase == 'motion':
            for i, value in enumerate(pulses):
                if i == self.active_axis-1:
                    if type(value) is not int or not base[i] <= value <= base[i]+self.active_offset:
                        raise RuntimeError('Outside the current reviewed-stage interval')
                elif value != base[i]:
                    raise RuntimeError('All other person/tiger commands must remain unchanged')
            changed=[i for i,(a,b) in enumerate(zip(self.pulses,pulses)) if a != b]
            if len(changed)>1 or any(abs(pulses[i]-self.pulses[i])>1 for i in changed):
                raise RuntimeError('Only one axis and one microsecond per step')
            if self.last_commit is not None and self.clock()-self.last_commit < INTERVAL-1e-9:
                raise RuntimeError('No accelerated catch-up')
        else:
            raise RuntimeError('No target changes during static hold')
        self.inside=True
        try:
            state=PwmDevice.commit(self,pulses,mask,allow_arm=self.mask==0)
        except BaseException:
            self.failed=True
            raise
        finally:
            self.inside=False
        self.pulses=pulses[:]; self.mask=mask; self.sequence=state['sequence']; self.last_commit=self.clock()
        return state

    def probe(self, axis, offset, emit, sleep):
        if axis not in (5,6) or offset not in LEVELS:
            raise RuntimeError('Only the current right-hand stage is allowed')
        if self.pulses != self.plan['expected_pulses_us']:
            raise RuntimeError('A path must begin at its inspected reference')
        self.phase='motion'; self.active_axis=axis; self.active_offset=offset
        count=math.ceil(offset*math.pi/1.8)
        base=self.plan['expected_pulses_us'][axis-1]
        emit({'event':'probe_started','axis':axis,'offset_us':offset,'steps_per_leg':count,'state':self.check()})
        for returning in (False,True):
            for step in range(1,count+1):
                self.wait(INTERVAL,sleep)
                delta=round(offset*.5*(1-math.cos(math.pi*step/count)))
                p=self.pulses[:];p[axis-1]=base+(offset-delta if returning else delta)
                emit({'event':'probe_step','axis':axis,'returning':returning,'step':step,
                      'offset_us':offset,'state':self.adopt(p,63)})
            if not returning:
                emit({'event':'probe_peak','axis':axis,'offset_us':offset,'state':self.check()})
                self.wait(2,sleep)
        self.phase='holding'; self.completed[axis]=offset
        emit({'event':'probe_complete','axis':axis,'offset_us':offset,'state':self.check()})


def run_session(device, emit, *, sleep=time.sleep):
    d=device; frame_stop=False
    try:
        emit({'event':'reference_held','state':d.adopt(d.pulses[:],63),
              'attended_unchanged_pose_continuation':True,'position_feedback':None})
        d.phase='holding'; d.wait(2,sleep); next_report=d.clock()
        while d.clock()<d.deadline:
            d.check(); d.kick()
            if d.host.action is not None:
                action,seq=d.host.action;d.host.action=None
                if seq!=d.sequence:raise RuntimeError('Stale request; no retry')
                if action=='finish':frame_stop=True;break
                if action.startswith('probe_'):
                    axis=int(action[-1]); old=d.reviewed.get(axis,0)
                    if axis not in (5,6) or d.completed.get(axis,0)!=old or old==LEVELS[-1]:
                        raise RuntimeError('Only the next visually reviewed right-hand stage')
                    offset=LEVELS[0] if not old else LEVELS[LEVELS.index(old)+1]
                    d.probe(axis,offset,emit,sleep)
                elif action.startswith('review_'):
                    axis=int(action[-1]);level=d.completed.get(axis)
                    if not level or d.reviewed.get(axis)==level:raise RuntimeError('No new completed stage to review')
                    d.reviewed[axis]=level
                    emit({'event':'path_reviewed','axis':axis,'offset_us':level,'state':d.check()})
                elif action=='demo':
                    if d.demo_used or any(d.reviewed.get(axis,0)<80 for axis in (5,6)):
                        raise RuntimeError('Visible paths must first be separately reviewed')
                    d.demo_used=True
                    for axis in (6,5):d.probe(axis,d.reviewed[axis],emit,sleep)
                    emit({'event':'demo_complete','state':d.check()})
                else:raise RuntimeError('No other action is authorized')
            if d.clock()>=next_report:
                emit({'event':'hold_alive','state':d.check(),'remaining_seconds':max(0,d.deadline-d.clock())})
                next_report=d.clock()+1
            d.wait(.03,sleep)
        frame_stop=True
    except ObservationLost:
        frame_stop=True
        raise
    finally:
        state=d.stop_after_frame() if frame_stop else d.off()
        emit({'event':'outputs_off','state':state,'normal_frame_stop':frame_stop,'incident_locks_removed':False})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path)
    parser.add_argument('--execute-attended-unchanged-continuation',action='store_true')
    parser.add_argument('--expected-plan-sha256')
    args=parser.parse_args();raw=args.plan.read_bytes();plan=json.loads(raw);validate_plan(plan)
    if not args.execute_attended_unchanged_continuation:
        print(json.dumps({'dry_run':True,'right_hand_offsets_us':LEVELS,'manual_pose_recovery':False}));return
    if not args.expected_plan_sha256 or hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:
        raise ValueError('Exact host-reviewed plan hash required before MMIO access')
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostControl(sys.stdin.fileno());print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not host.received:host.check();time.sleep(.02)
    registers=Registers()
    try:
        d=VisibleSession(registers,plan,host)
        run_session(d,lambda row:print(json.dumps(row),flush=True))
    finally:registers.close()


if __name__=='__main__':main()
