"""Attended comparison of fixed three-rod paths; not a general axis envelope.

Keeps the inspected reference and incident locks. A stage is a single fixed
vector round trip. Only visually accepted stages can be replayed in the demo.
An explicit bilateral diagnostic may move axis 2 downward on a fixed path.
An exclusive head-support diagnostic may raise axis 4, with every other axis
fixed. The tiger remains unchanged; loss of observation stops output.
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
if Path(__file__).with_name('person_visible_motion_session_20261012_r5.py').exists():
    from person_visible_motion_session_20261012_r5 import VisibleSession, validate_plan as validate_reference
elif Path(__file__).with_name('person_visible_motion_session_20261012_r4.py').exists():
    from person_visible_motion_session_20261012_r4 import VisibleSession, validate_plan as validate_reference
else:
    from person_visible_motion_session import VisibleSession, validate_plan as validate_reference
from person_recovery_session import HostControl, ObservationLost
from servo_pwm_device import PwmDevice, Registers

APPROVAL = 'attended-person-linkage-comparison-20261012'
INTERVAL = .05
# These are trial caps, not a calibrated rectangular workspace.
CAPS = (40, 0, 40, 0, 60, 120)
BILATERAL_MIN = (0, -80, 0, 0, 0, 0)
HEAD_SUPPORT_MIN = (0, 0, 0, -80, 0, 0)


def reference_plan(plan):
    p = dict(plan)
    for k in ('stages', 'demo_stages', 'bilateral_hand_diagnostic', 'head_support_diagnostic',
              'head_supported_bilateral_diagnostic', 'head_support_offset_us',
              'supported_martial_diagnostic', 'tempo_step_us', 'peak_hold_ms'):
        p.pop(k, None)
    p['approval'] = 'attended-unchanged-person-continuation-20261012'
    if plan.get('head_support_diagnostic') is True:
        p['motion_axes'] = [4]
        p['head_pitch_diagnostic'] = True
    else:
        p['motion_axes'] = [1, 2, 3, 5, 6] if plan.get('bilateral_hand_diagnostic') is True else [1, 3, 5, 6]
    return p


def validate_plan(plan, wall=None):
    if not isinstance(plan, dict) or plan.get('approval') != APPROVAL:
        raise ValueError('Explicit attended linkage comparison receipt required')
    bilateral = 'bilateral_hand_diagnostic' in plan
    head_support = 'head_support_diagnostic' in plan
    supported = 'head_supported_bilateral_diagnostic' in plan
    martial = 'supported_martial_diagnostic' in plan
    if bilateral and plan['bilateral_hand_diagnostic'] is not True:
        raise ValueError('Bilateral diagnostic must be explicitly true')
    if head_support and (bilateral or plan['head_support_diagnostic'] is not True):
        raise ValueError('Head support requires an exclusive explicit diagnostic')
    if supported and (plan['head_supported_bilateral_diagnostic'] is not True
            or not bilateral or head_support or type(plan.get('head_support_offset_us')) is not int
            or plan['head_support_offset_us'] not in (-40, -60, -80)):
        raise ValueError('Supported bilateral paths require a reviewed exclusive support lift')
    if 'head_support_offset_us' in plan and not supported:
        raise ValueError('Support offset requires explicit supported bilateral mode')
    if martial and (plan['supported_martial_diagnostic'] is not True or not bilateral
            or supported or head_support or plan.get('head_support_reference_offset_us') != -60
            or type(plan.get('tempo_step_us')) is not int or plan['tempo_step_us'] not in (2,3)
            or type(plan.get('peak_hold_ms')) is not int or plan['peak_hold_ms'] != 400):
        raise ValueError('Alternating hand paths require the held head support and explicit bounded tempo')
    if not martial and ('tempo_step_us' in plan or 'peak_hold_ms' in plan):
        raise ValueError('Tempo changes require the supported martial diagnostic')
    validate_reference(reference_plan(plan), wall)
    stages = plan.get('stages')
    if not isinstance(stages, list) or not 1 <= len(stages) <= 6:
        raise ValueError('One to six fixed vector stages required')
    for vector in stages:
        if (not isinstance(vector, list) or len(vector) != 6
                or any(type(v) is not int or not low <= v <= cap
                       for v, low, cap in zip(vector,
                           HEAD_SUPPORT_MIN if head_support else BILATERAL_MIN if bilateral else (0,)*6,
                           (0,)*6 if head_support else CAPS))
                or not any(vector)):
            raise ValueError('Only bounded, explicitly selected person trial offsets allowed')
        if martial and not (vector[1] < 0 or vector[5] > 0):
            raise ValueError('Select a hand pitch path for each martial stage')
        if bilateral and not martial and not (vector[1] < 0 and vector[5] > 0):
            raise ValueError('Bilateral paths require opposite pitch directions for both hands')
        if head_support and vector[3] >= 0:
            raise ValueError('Exclusive head-support paths must raise axis 4')
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
        self.step_limit = plan.get('tempo_step_us', 1)
        self.peak_hold = plan.get('peak_hold_ms', 2000)/1000
        self.support_base = self.plan['expected_pulses_us'][:]
        if plan.get('head_supported_bilateral_diagnostic') is True:
            self.support_base[3] += plan['head_support_offset_us']

    def adopt(self, pulses, mask):
        if self.phase == 'resume':
            return super().adopt(pulses, mask)
        self.check()
        if (self.phase not in ('linkage', 'supporting') or self.clock() >= self.deadline
                or mask != 63 or pulses != self.expected_waypoint):
            raise RuntimeError('Only the next waypoint on the fixed vector path')
        if any(abs(a-b) > self.step_limit for a, b in zip(pulses, self.pulses)):
            raise RuntimeError('Each component must respect the explicitly selected step limit')
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

    def set_support(self, enabled, emit, sleep):
        reference = self.plan['expected_pulses_us']
        source, target = (reference, self.support_base) if enabled else (self.support_base, reference)
        if self.pulses != source or source == target:
            raise RuntimeError('Support transfer must start from its exact inspected waypoint')
        count = math.ceil(abs(target[3]-source[3])*math.pi/1.8)
        self.phase = 'supporting'
        emit({'event':'support_started','enabled':enabled,'state':self.check()})
        for step in range(1,count+1):
            self.wait(INTERVAL,sleep)
            fraction = .5*(1-math.cos(math.pi*step/count))
            p = source[:];p[3] += round((target[3]-source[3])*fraction)
            self.expected_waypoint = p[:]
            emit({'event':'support_step','enabled':enabled,'state':self.adopt(p,63)})
        self.phase = 'holding'
        emit({'event':'support_established' if enabled else 'reference_restored','state':self.check()})
        self.wait(2,sleep)

    def probe(self, stage, emit, sleep):
        if type(stage) is not int or not 1 <= stage <= len(self.linkage_plan['stages']):
            raise RuntimeError('Unspecified linkage stage')
        base = self.support_base
        if self.pulses != base:
            raise RuntimeError('Each vector starts at the inspected reference')
        offsets = self.linkage_plan['stages'][stage-1]
        extent = max(abs(v) for v in offsets)
        count = math.ceil(extent*math.pi/(1.8*self.step_limit))
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
                self.wait(self.peak_hold,sleep)
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
        if d.linkage_plan.get('head_supported_bilateral_diagnostic') is True:
            d.set_support(True,emit,sleep)
        next_report = d.clock()
        while d.clock() < d.deadline:
            d.check(); d.kick()
            if d.host.action is not None:
                action, sequence = d.host.action
                d.host.action = None
                if sequence != d.sequence:
                    raise RuntimeError('Stale action; no retry')
                if action == 'finish':
                    if d.linkage_plan.get('head_supported_bilateral_diagnostic') is True:
                        d.set_support(False,emit,sleep)
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
