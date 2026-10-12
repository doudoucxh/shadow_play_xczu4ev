"""Attended comparison of fixed three-rod paths; not a general axis envelope.

Keeps the inspected reference and incident locks. A stage is a single fixed
vector round trip. Only visually accepted stages can be replayed in the demo.
Axis 4 and the tiger remain unchanged. An explicit bilateral diagnostic may
move axis 2 downward on a fixed path; loss of observation stops output.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import time

# The board uses immutable, versioned /tmp modules; local tests use the source.
if Path(__file__).with_name('person_visible_motion_session_20261012_r4.py').exists():
    from person_visible_motion_session_20261012_r4 import VisibleSession, validate_plan as validate_reference
else:
    from person_visible_motion_session import VisibleSession, validate_plan as validate_reference
from person_recovery_session import HostControl, ObservationLost
from servo_pwm_device import PwmDevice, Registers

APPROVAL = 'attended-person-linkage-comparison-20261012'
INTERVAL = .05
# These are trial caps, not a calibrated rectangular workspace.
CAPS = (40, 0, 40, 0, 60, 120)
BILATERAL_MIN = (0, -40, 0, 0, 0, 0)


def reference_plan(plan):
    p = dict(plan)
    for k in ('stages', 'demo_stages', 'bilateral_hand_diagnostic'):
        p.pop(k, None)
    p['approval'] = 'attended-unchanged-person-continuation-20261012'
    p['motion_axes'] = [1, 2, 3, 5, 6] if plan.get('bilateral_hand_diagnostic') is True else [1, 3, 5, 6]
    return p


def validate_plan(plan, wall=None):
    if not isinstance(plan, dict) or plan.get('approval') != APPROVAL:
        raise ValueError('Explicit attended linkage comparison receipt required')
    bilateral = 'bilateral_hand_diagnostic' in plan
    if bilateral and plan['bilateral_hand_diagnostic'] is not True:
        raise ValueError('Bilateral diagnostic must be explicitly true')
    validate_reference(reference_plan(plan), wall)
    stages = plan.get('stages')
    if not isinstance(stages, list) or not 1 <= len(stages) <= 6:
        raise ValueError('One to six fixed vector stages required')
    for vector in stages:
        if (not isinstance(vector, list) or len(vector) != 6
                or any(type(v) is not int or not low <= v <= cap
                       for v, low, cap in zip(vector, BILATERAL_MIN if bilateral else (0,)*6, CAPS))
                or not any(vector)):
            raise ValueError('Only bounded, explicitly selected person trial offsets allowed')
        if bilateral and not (vector[1] < 0 and vector[5] > 0):
            raise ValueError('Bilateral paths require opposite pitch directions for both hands')
    demo = plan.get('demo_stages')
    if (not isinstance(demo, list) or not 1 <= len(demo) <= 6
            or any(type(v) is not int or not 1 <= v <= len(stages) for v in demo)):
        raise ValueError('Demo must select explicit reviewed stage IDs')


class LinkageSession(VisibleSession):
    def __init__(self, registers, plan, host, **kwargs):
        validate_plan(plan, kwargs.get('wall'))
        super().__init__(registers, reference_plan(plan), host, **kwargs)
        self.linkage_plan = json.loads(json.dumps(plan))
        self.expected_waypoint = None
        self.completed = set()
        self.reviewed = set()
        self.active_stage = None

    def adopt(self, pulses, mask):
        if self.phase == 'resume':
            return super().adopt(pulses, mask)
        self.check()
        if (self.phase != 'linkage' or self.clock() >= self.deadline
                or mask != 63 or pulses != self.expected_waypoint):
            raise RuntimeError('Only the next waypoint on the fixed vector path')
        if any(abs(a-b) > 1 for a, b in zip(pulses, self.pulses)):
            raise RuntimeError('Each component limited to one microsecond per step')
        if self.last_commit is not None and self.clock()-self.last_commit < INTERVAL-1e-9:
            raise RuntimeError('No accelerated catch-up')
        self.inside = True
        try:
            state = PwmDevice.commit(self, pulses, mask, allow_arm=False)
        except BaseException:
            self.failed = True
            raise
        finally:
            self.inside = False
        self.pulses = pulses[:]
        self.sequence = state['sequence']
        self.last_commit = self.clock()
        self.expected_waypoint = None
        return state

    def probe(self, stage, emit, sleep):
        if type(stage) is not int or not 1 <= stage <= len(self.linkage_plan['stages']):
            raise RuntimeError('Unspecified linkage stage')
        base = self.plan['expected_pulses_us']
        if self.pulses != base:
            raise RuntimeError('Each vector starts at the inspected reference')
        offsets = self.linkage_plan['stages'][stage-1]
        extent = max(abs(v) for v in offsets)
        count = math.ceil(extent*math.pi/1.8)
        self.phase = 'linkage'
        self.active_stage = stage
        emit({'event':'probe_started', 'axis':stage, 'offset_us':extent,
              'vector_us':offsets, 'steps_per_leg':count, 'state':self.check()})
        for returning in (False, True):
            for step in range(1, count+1):
                self.wait(INTERVAL, sleep)
                fraction = .5*(1-math.cos(math.pi*step/count))
                if returning:
                    fraction = 1-fraction
                p = base[:]
                for i, delta in enumerate(offsets):
                    p[i] += round(delta*fraction)
                self.expected_waypoint = p[:]
                emit({'event':'probe_step', 'axis':stage, 'returning':returning,
                      'step':step, 'vector_us':offsets, 'state':self.adopt(p,63)})
            if not returning:
                emit({'event':'probe_peak', 'axis':stage, 'offset_us':extent,
                      'vector_us':offsets, 'state':self.check()})
                self.wait(2,sleep)
        self.phase = 'holding'
        self.completed.add(stage)
        emit({'event':'probe_complete', 'axis':stage, 'vector_us':offsets,
              'offset_us':extent, 'state':self.check()})


def run_session(d, emit, *, sleep=time.sleep):
    frame_stop = False
    try:
        emit({'event':'reference_held', 'state':d.adopt(d.pulses[:],63),
              'linkage_comparison':True, 'position_feedback':None})
        d.phase = 'holding'
        d.wait(2,sleep)
        next_report = d.clock()
        while d.clock() < d.deadline:
            d.check(); d.kick()
            if d.host.action is not None:
                action, sequence = d.host.action
                d.host.action = None
                if sequence != d.sequence:
                    raise RuntimeError('Stale action; no retry')
                if action == 'finish':
                    frame_stop = True
                    break
                if action.startswith('probe_'):
                    stage = int(action[-1])
                    if d.completed-d.reviewed or stage in d.completed:
                        raise RuntimeError('Review each completed stage before another comparison')
                    d.probe(stage,emit,sleep)
                elif action.startswith('review_'):
                    stage = int(action[-1])
                    if stage not in d.completed or stage in d.reviewed:
                        raise RuntimeError('Only a new completed stage can be visually accepted')
                    d.reviewed.add(stage)
                    emit({'event':'path_reviewed', 'axis':stage, 'state':d.check()})
                elif action == 'demo':
                    selected = d.linkage_plan['demo_stages']
                    if d.demo_used or not set(selected) <= d.reviewed:
                        raise RuntimeError('Demo requires prior visual review of every selected vector')
                    d.demo_used = True
                    for stage in selected:
                        d.probe(stage,emit,sleep)
                    emit({'event':'demo_complete', 'state':d.check()})
                else:
                    raise RuntimeError('Unknown linkage action')
            if d.clock() >= next_report:
                emit({'event':'hold_alive', 'state':d.check(),
                      'remaining_seconds':max(0,d.deadline-d.clock())})
                next_report = d.clock()+1
            d.wait(.03,sleep)
        frame_stop = True
    except ObservationLost:
        frame_stop = True
        raise
    finally:
        state = d.stop_after_frame() if frame_stop else d.off()
        emit({'event':'outputs_off', 'state':state, 'normal_frame_stop':frame_stop,
              'incident_locks_removed':False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path)
    parser.add_argument('--execute-attended-linkage-comparison',action='store_true')
    parser.add_argument('--expected-plan-sha256')
    args=parser.parse_args()
    raw=args.plan.read_bytes(); plan=json.loads(raw); validate_plan(plan)
    if not args.execute_attended_linkage_comparison:
        print(json.dumps({'dry_run':True,'vectors_us':plan['stages'],
                          'demo_stage_ids':plan['demo_stages'],'workspace_calibrated':False}))
        return
    if not args.expected_plan_sha256 or hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:
        raise ValueError('Host-reviewed plan hash required before MMIO')
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt); signal.signal(signal.SIGTERM,interrupt)
    host=HostControl(sys.stdin.fileno())
    print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not host.received:host.check();time.sleep(.02)
    registers=Registers()
    try:
        d=LinkageSession(registers,plan,host)
        run_session(d,lambda row:print(json.dumps(row),flush=True))
    finally:registers.close()


if __name__=='__main__':main()
