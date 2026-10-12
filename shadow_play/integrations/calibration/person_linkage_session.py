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
import re
import signal
import sys
import time

# The board uses immutable, versioned /tmp modules; local tests use the source.
if Path(__file__).with_name('person_visible_motion_session_20261012_r9.py').exists():
    from person_visible_motion_session_20261012_r9 import VisibleSession, validate_plan as validate_reference
elif Path(__file__).with_name('person_visible_motion_session_20261012_r8.py').exists():
    from person_visible_motion_session_20261012_r8 import VisibleSession, validate_plan as validate_reference
elif Path(__file__).with_name('person_visible_motion_session_20261012_r7.py').exists():
    from person_visible_motion_session_20261012_r7 import VisibleSession, validate_plan as validate_reference
elif Path(__file__).with_name('person_visible_motion_session_20261012_r6.py').exists():
    from person_visible_motion_session_20261012_r6 import VisibleSession, validate_plan as validate_reference
elif Path(__file__).with_name('person_visible_motion_session_20261012_r5.py').exists():
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
LOW_GUARD = (0,-140,0,0,0,240)
COMBINED_LOWERING_RECEIPT = '1747fc93e1473da1015326c0b2e9f6e37d8e4b979ad306d5a56c0a706960d0f9'
LOW_GUARD_GEOMETRY_RECEIPT = '1639361a56578d3ffb9a1a08b7d168da1f6abb2f658dd67f0660ce7da5a5c10b'
LOW_GUARD_REVIEWED_PATHS = ((0,140,0,0,0,0),(0,0,0,0,0,-240),(0,140,0,0,0,-240))
LOW_HEAD_FOLLOW_RECEIPT = 'a83323b9593830ca97fda4eafedb02d1213ed1bc98ab358c316565d8257968c5'
LOW_HEAD_FOLLOW_PATHS = ((0,0,0,-40,0,0),(0,140,0,-40,0,0),(0,0,0,-40,0,-240),(0,140,0,-40,0,-240))
HEAD_FOLLOW_GEOMETRY_RECEIPT = 'dc933480a54ecd51d242a66a41923032aae1df60b9823a9b8e7445c3aba3c16f'


def reference_plan(plan):
    p = dict(plan)
    for k in ('stages', 'demo_stages', 'bilateral_hand_diagnostic', 'head_support_diagnostic',
              'head_supported_bilateral_diagnostic', 'head_support_offset_us',
              'supported_martial_diagnostic', 'tempo_step_us', 'peak_hold_ms',
              'motion_interval_ms', 'lower_hands_diagnostic', 'combined_lower_hands_diagnostic',
              'low_guard_diagnostic', 'combined_lowering_receipt_sha256',
              'low_guard_performance', 'low_guard_geometry_receipt_sha256', 'head_follow_receipt_sha256',
              'low_guard_head_follow_performance', 'head_follow_geometry_receipt_sha256'):
        p.pop(k, None)
    p['approval'] = 'attended-unchanged-person-continuation-20261012'
    if plan.get('head_support_diagnostic') is True:
        p['motion_axes'] = [4]
        p['head_pitch_diagnostic'] = True
    else:
        p['motion_axes'] = [2,4,6] if plan.get('low_guard_head_follow') is True else [2,6] if plan.get('low_guard_diagnostic') is True else [1, 2, 3, 5, 6] if plan.get('bilateral_hand_diagnostic') is True else [1, 3, 5, 6]
    return p


def validate_plan(plan, wall=None):
    if not isinstance(plan, dict) or plan.get('approval') != APPROVAL:
        raise ValueError('Explicit attended linkage comparison receipt required')
    bilateral = 'bilateral_hand_diagnostic' in plan
    head_support = 'head_support_diagnostic' in plan
    supported = 'head_supported_bilateral_diagnostic' in plan
    martial = 'supported_martial_diagnostic' in plan
    lower = 'lower_hands_diagnostic' in plan
    combined_lower = 'combined_lower_hands_diagnostic' in plan
    guard = 'low_guard_diagnostic' in plan
    guard_performance = 'low_guard_performance' in plan
    low_head = 'lowered_head_support_diagnostic' in plan
    follow = 'low_guard_head_follow' in plan
    follow_fast = 'low_guard_head_follow_performance' in plan
    if not isinstance(plan.get('session_id'),str) or not re.fullmatch('[a-z0-9-]{1,80}', plan['session_id']):
        raise ValueError('Safe unique session ID required')
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
            or type(plan.get('tempo_step_us')) is not int or plan['tempo_step_us'] not in (2,3,6,8)
            or type(plan.get('peak_hold_ms')) is not int or plan['peak_hold_ms'] not in (100,400)):
        raise ValueError('Alternating hand paths require the held head support and explicit bounded tempo')
    if lower and (plan['lower_hands_diagnostic'] is not True or not martial
            or plan['tempo_step_us'] != 3):
        raise ValueError('New low-hand geometry requires the separate three-microsecond diagnostic')
    if combined_lower and (plan['combined_lower_hands_diagnostic'] is not True or not lower):
        raise ValueError('Combined lowering requires the explicit slow low-hand diagnostic')
    if guard and (plan['low_guard_diagnostic'] is not True or not martial or lower
            or plan['tempo_step_us'] != (8 if guard_performance or follow_fast else 3) or plan.get('motion_interval_ms') != 20
            or plan.get('combined_lowering_receipt_sha256') != COMBINED_LOWERING_RECEIPT):
        raise ValueError('Low guard requires the reviewed combined lowering and a separate slow diagnostic')
    if guard_performance and (plan['low_guard_performance'] is not True or not guard
            or plan.get('low_guard_geometry_receipt_sha256') != LOW_GUARD_GEOMETRY_RECEIPT):
        raise ValueError('Fast low guard requires the three physically reviewed guard paths')
    if not guard_performance and 'low_guard_geometry_receipt_sha256' in plan:
        raise ValueError('Guard geometry receipt requires explicit performance mode')
    if low_head and (plan['lowered_head_support_diagnostic'] is not True or not head_support
            or guard or lower or plan.get('tempo_step_us') != 3 or plan.get('motion_interval_ms') != 20
            or plan.get('peak_hold_ms') != 400 or plan.get('combined_lowering_receipt_sha256') != COMBINED_LOWERING_RECEIPT
            or plan.get('lowered_hands_reference_offset_us') != list(LOW_GUARD)):
        raise ValueError('Further head lift requires an exclusive slow diagnostic with both hands at the reviewed low pose')
    if follow and (plan['low_guard_head_follow'] is not True or not guard or low_head or guard_performance
            or 'lowered_hands_reference_offset_us' not in plan
            or plan.get('head_follow_receipt_sha256') != LOW_HEAD_FOLLOW_RECEIPT):
        raise ValueError('Coordinated head follow requires the separate reviewed 40-us head lift and slow guard diagnostic')
    if not follow and 'head_follow_receipt_sha256' in plan:
        raise ValueError('Head-follow receipt requires the explicit fixed-path diagnostic')
    if follow_fast and (plan['low_guard_head_follow_performance'] is not True or not follow
            or plan.get('peak_hold_ms')!=400
            or plan.get('head_follow_geometry_receipt_sha256')!=HEAD_FOLLOW_GEOMETRY_RECEIPT):
        raise ValueError('Fast head follow requires the four reviewed combined paths and 400-ms peak')
    if not follow_fast and 'head_follow_geometry_receipt_sha256' in plan:
        raise ValueError('Combined-path receipt requires explicit head-follow performance mode')
    if not guard and not low_head and ('combined_lowering_receipt_sha256' in plan or 'lowered_hands_reference_offset_us' in plan):
        raise ValueError('Lowered reference is reserved for the fixed low-guard actor')
    if 'motion_interval_ms' in plan and (not (martial or low_head)
            or type(plan['motion_interval_ms']) is not int or plan['motion_interval_ms'] not in (20,50)):
        raise ValueError('Only explicit 20/50 ms person motion periods allowed')
    if not martial and not low_head and ('tempo_step_us' in plan or 'peak_hold_ms' in plan):
        raise ValueError('Tempo changes require the supported martial diagnostic')
    validate_reference(reference_plan(plan), wall)
    stages = plan.get('stages')
    if not isinstance(stages, list) or not 1 <= len(stages) <= 6:
        raise ValueError('One to six fixed vector stages required')
    for vector in stages:
        if (not isinstance(vector, list) or len(vector) != 6
                or any(type(v) is not int or not low <= v <= cap
                       for v, low, cap in zip(vector,
                           (0,0,0,-40,0,-240) if follow else (0,0,0,0,0,-240) if guard else HEAD_SUPPORT_MIN if head_support else (0,-140,0,0,0,0) if lower else BILATERAL_MIN if bilateral else (0,)*6,
                           (0,140,0,0,0,0) if guard else (0,)*6 if head_support else (40,0,40,0,60,240) if lower else CAPS))
                or not any(vector)):
            raise ValueError('Only bounded, explicitly selected person trial offsets allowed')
        if martial and not guard and not (vector[1] < 0 or vector[5] > 0):
            raise ValueError('Select a hand pitch path for each martial stage')
        if guard_performance and tuple(vector) not in LOW_GUARD_REVIEWED_PATHS:
            raise ValueError('Performance may select only the three reviewed low-guard paths')
        if follow and tuple(vector) not in LOW_HEAD_FOLLOW_PATHS:
            raise ValueError('Select one of the four fixed head-follow guard paths')
        if lower and (any(vector[i] for i in (0,2,3,4))
                or (not (vector[1] < 0 and vector[5] > 0) if combined_lower
                    else bool(vector[1]) == bool(vector[5]))):
            raise ValueError('Low-hand diagnostics require exclusive pitch paths or explicit combined lowering')
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
        self.motion_interval = plan.get('motion_interval_ms', 50)/1000
        self.support_base = self.plan['expected_pulses_us'][:]
        if plan.get('head_supported_bilateral_diagnostic') is True:
            self.support_base[3] += plan['head_support_offset_us']
        if plan.get('low_guard_diagnostic') is True and 'lowered_hands_reference_offset_us' not in plan:
            for i,delta in enumerate(LOW_GUARD):self.support_base[i] += delta

    def adopt(self, pulses, mask):
        if self.phase == 'resume':
            return super().adopt(pulses, mask)
        self.check()
        if (self.phase not in ('linkage', 'supporting') or self.clock() >= self.deadline
                or mask != 63 or pulses != self.expected_waypoint):
            raise RuntimeError('Only the next waypoint on the fixed vector path')
        if any(abs(a-b) > self.step_limit for a, b in zip(pulses, self.pulses)):
            raise RuntimeError('Each component must respect the explicitly selected step limit')
        if self.last_commit is not None and self.clock()-self.last_commit < self.motion_interval-1e-9:
            raise RuntimeError('No accelerated catch-up')
        self.inside = True
        commit_started = self.clock()
        try:
            state = PwmDevice.commit(self, pulses, mask, allow_arm=False)
        except BaseException:
            self.failed = True
            raise
        finally:
            self.inside = False
        self.pulses = pulses[:]
        self.sequence = state['sequence']
        self.last_commit = commit_started if self.motion_interval == .02 else self.clock()
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

    def establish_low_guard(self, emit, sleep):
        source=self.plan['expected_pulses_us'];target=self.support_base
        if self.pulses != source:raise RuntimeError('Guard transfer requires the exact inspected source')
        if source != target:
            count=math.ceil(max(abs(a-b) for a,b in zip(source,target))*math.pi/(1.8*3))
            self.phase='supporting'
            emit({'event':'support_started','low_guard':True,'state':self.check()})
            for step in range(1,count+1):
                delay=max(0,self.last_commit+self.motion_interval-self.clock()) if self.last_commit is not None else self.motion_interval
                self.wait(delay,sleep)
                fraction=.5*(1-math.cos(math.pi*step/count))
                pulses=[a+round((b-a)*fraction) for a,b in zip(source,target)]
                self.expected_waypoint=pulses[:]
                emit({'event':'support_step','low_guard':True,'state':self.adopt(pulses,63)})
        self.phase='holding'
        emit({'event':'support_established','low_guard':True,'state':self.check()})
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
                # The driver already waits for frame adoption. Do not add a
                # second full frame delay to the explicit performance mode.
                delay = self.motion_interval
                if self.motion_interval == .02 and self.last_commit is not None:
                    delay = max(0, self.last_commit+self.motion_interval-self.clock())
                self.wait(delay, sleep)
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
        if d.linkage_plan.get('low_guard_diagnostic') is True:
            d.establish_low_guard(emit,sleep)
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


def motion_emitter(log, output, clock=time.monotonic):
    """Preserve every state locally without flooding a 115200-baud console."""
    last_step = -math.inf
    def emit(row):
        nonlocal last_step
        now = clock()
        row = dict(row, board_monotonic_seconds=now)
        log.write(json.dumps(row)+'\n')
        step = row['event'] in ('probe_step','support_step')
        if not step or now-last_step >= .2:
            log.flush()
            output(row)
            if step:last_step=now
    return emit


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
        output=lambda row:print(json.dumps(row),flush=True)
        if plan.get('motion_interval_ms') == 20:
            log_path=Path('/tmp')/('person-linkage-'+plan['session_id']+'.jsonl')
            with log_path.open('x',encoding='utf-8') as log:
                output({'event':'local_motion_log','path':str(log_path)})
                run_session(d,motion_emitter(log,output))
        else:
            run_session(d,output)
    finally:registers.close()


if __name__=='__main__':main()
