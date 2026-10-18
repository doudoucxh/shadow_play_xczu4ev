"""Explicitly requested one-axis tiger-head check, not a V20 score player.

Only axis 8, 1500..1540 us, one outbound/return path. Existing axis-7 plans
and historical stop records remain unchanged. No generic unlock operation.
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

from servo_pwm_device import PwmDevice, Registers
from v20_first_direction import FirstDirectionDevice, HostLease, IMAGE, MIDPOINT, digest, PREFIX

SCHEMA = 'attended-v20-head-lift-v1'
PHONE_SCHEMA = 'attended-v20-head-lift-phone-v2'
PHONE_LOG = '/run/media/mmcblk0p2/piying/v20-head-lift-20261018/run-0c451e645e15404780636d43ae828f20.board.jsonl'
PHONE_LOG_SHA = 'bcf97fce41451cac943f089cd0905a5a8a0e71f13548c3b09f5b49f280858a53'
MASK = 128
INTERVAL = .04
SOURCE_SHA = 'a0a7af4128b1eee714b62f7a87ed4b286eeb960b9f9468b06fa9188d176860ab'
PRIOR_LOG = '/run/media/mmcblk0p2/piying/v20-first-direction-20261018-r4/run-'


def route():
    frames = []
    for i in range(301):
        t = i / 50
        u = .5 - .5 * math.cos(math.pi * min(t, 2) / 2) if t <= 3 else (
            .5 + .5 * math.cos(math.pi * min(t - 3, 2) / 2))
        pulses = MIDPOINT[:]
        pulses[7] += int(math.floor(40 * u + .5))
        frames.append(pulses)
    return frames


FRAMES = route()


def validate_plan(p):
    required = {'schema', 'session_id', 'boot_id', 'expected_sequence', 'expected_pulse_us',
                'route_sha256', 'historical_source_sha256', 'camera_required', 'onsite_observer',
                'new_request_id', 'new_hardware_request', 'prior_log_path', 'prior_log_sha256'}
    if not isinstance(p, dict):
        raise ValueError('Dedicated axis-8 plan required')
    phone = p.get('schema') == PHONE_SCHEMA
    if phone:
        required = required | {'camera_views'}
    if set(p) != required or p['schema'] not in (SCHEMA, PHONE_SCHEMA):
        raise ValueError('Dedicated axis-8 plan required')
    for key in ('session_id', 'new_request_id'):
        if not isinstance(p[key], str) or not re.fullmatch('[a-f0-9]{32}', p[key]):
            raise ValueError('Unique request/run binding required')
    if not isinstance(p['boot_id'], str) or not re.fullmatch('[a-f0-9-]{36}', p['boot_id']):
        raise ValueError('Fresh boot required')
    if type(p['expected_sequence']) is not int or not 0 <= p['expected_sequence'] < 2**32:
        raise ValueError('Fresh sequence required')
    if (p['expected_pulse_us'] != MIDPOINT or p['route_sha256'] != digest(FRAMES)
            or p['historical_source_sha256'] != SOURCE_SHA
            or any(p[k] is not True for k in ('new_hardware_request', 'onsite_observer', 'camera_required'))):
        raise ValueError('Only a new attended axis-8 fixed route is allowed')
    if phone:
        if (p['camera_views'] != ['phone_mechanism'] or p['expected_sequence'] != 978
                or p['prior_log_path'] != PHONE_LOG or p['prior_log_sha256'] != PHONE_LOG_SHA):
            raise ValueError('Phone review must bind the actual OFF978 completion')
    elif (not re.fullmatch(re.escape(PRIOR_LOG) + '[a-f0-9]{32}\\.board\\.jsonl', p['prior_log_path'])
            or not re.fullmatch('[a-f0-9]{64}', p['prior_log_sha256'])):
        raise ValueError('Original completed-run evidence required')


def validate_prior(p, raw):
    if hashlib.sha256(raw).hexdigest() != p['prior_log_sha256']:
        raise ValueError('Prior evidence changed')
    last = json.loads(raw.splitlines()[-1])
    state = last['state']
    if (last['event'] != 'outputs_off' or last['route_complete'] is not True
            or state['armed'] or state['enabled_mask'] or state['pending'] or state['faults']
            or state['sequence'] != p['expected_sequence'] or state['pulse_us'] != MIDPOINT):
        raise ValueError('Prior completion is not the inspected midpoint command reference')


class HeadLiftDevice(FirstDirectionDevice):
    """Share lock/state/lease lifecycle; replace the entire axis-7 permission path."""
    def __init__(self, registers, plan, host, *, boot_id, marker, used_path,
                 motion_inhibit_paths=None, cancel_path='/run/v20-head-lift-stop', clock=time.monotonic):
        validate_plan(plan)
        if plan['boot_id'] != boot_id or marker.get('boot_id') != boot_id or marker.get('sha256') != IMAGE:
            raise ValueError('Inspected boot/image changed')
        PwmDevice.__init__(self, registers, motion_inhibit_paths=motion_inhibit_paths)
        self.plan = json.loads(json.dumps(plan))
        self.host = host
        self.clock = clock
        self.used_path = Path(used_path)
        self.cancel = Path(cancel_path)
        self.hashes = self.lock_hashes()
        self.sequence = plan['expected_sequence']
        self.pulses = MIDPOINT[:]
        self.frames = FRAMES
        self.mask = self.index = 0
        self.inside = self.started = self.failed = False
        self.last_issue = self.deadline = None
        self.check()

    def commit(self, pulses, mask, allow_arm=False):
        self.check()
        if not self.started or self.index >= len(FRAMES):
            raise RuntimeError('No next frame in this one-use head-lift check')
        if pulses != FRAMES[self.index] or mask != MASK or allow_arm is not (self.index == 0):
            raise ValueError('Only the exact next axis-8 frame is allowed')
        issued = self.clock()
        if self.last_issue is not None and issued - self.last_issue < INTERVAL - 1e-8:
            raise RuntimeError('No accelerated catch-up')
        self.inside = True
        try:
            state = PwmDevice.commit(self, pulses, MASK, allow_arm=allow_arm)
        except BaseException:
            self.failed = True
            raise
        finally:
            self.inside = False
        self.sequence = state['sequence']
        self.pulses = pulses[:]
        self.mask = MASK
        self.last_issue = issued
        self.index += 1
        return state


def run(d, emit, sleep=time.sleep):
    complete = False
    try:
        d.begin()
        start = d.clock()
        for index, pulses in enumerate(FRAMES):
            scheduled = max(start + index * INTERVAL,
                            d.last_issue + INTERVAL if d.last_issue is not None else start)
            while d.clock() < scheduled:
                d.check(); d.kick()
                sleep(max(0., min(.005, scheduled - d.clock())))
            if d.last_issue is not None and d.clock() - d.last_issue > .15:
                raise RuntimeError('Individual command interval stalled')
            d.check(); d.kick()
            state = d.commit(pulses, MASK, allow_arm=(index == 0))
            emit(dict(event='frame', index=index, elapsed_s=d.clock() - start, state=state))
        complete = True
    except BaseException as error:
        emit(dict(event='failure', reason=type(error).__name__ + ': ' + str(error)))
        raise
    finally:
        state = d.stop_after_frame() if complete else d.off()
        emit(dict(event='outputs_off', route_complete=complete, state=state,
                  incident_locks_removed=False, position_feedback=None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--execute-one-head-lift', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    validate_plan(plan)
    if not args.execute_one_head_lift:
        print(json.dumps(dict(dry_run=True, mask=MASK, frames=301, nominal_duration_s=12,
                              route_sha256=digest(FRAMES))))
        return
    validate_prior(plan, Path(plan['prior_log_path']).read_bytes())
    def interrupt(signum, frame): raise KeyboardInterrupt()
    signal.signal(signal.SIGINT, interrupt); signal.signal(signal.SIGTERM, interrupt)
    host = HostLease(sys.stdin.fileno(), plan['session_id'])
    marker = json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    registers = Registers()
    try:
        d = HeadLiftDevice(registers, plan, host, boot_id=boot, marker=marker,
                          used_path='/run/v20-head-lift-{}-{}.used'.format(boot, plan['expected_sequence']))
        log_path = args.plan.with_suffix('.board.jsonl')
        with log_path.open('x') as log:
            def emit(row):
                log.write(json.dumps(row) + '\n')
                if row.get('event') != 'frame' or row['index'] % 50 == 0:
                    print(PREFIX + json.dumps(row), flush=True)
            print(PREFIX + json.dumps(dict(event='ready', session_id=plan['session_id'], state=d.check())), flush=True)
            while not host.begun:
                host.check(); time.sleep(.01)
            run(d, emit)
        print(PREFIX + json.dumps(dict(event='audit', board_log=str(log_path),
            board_log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest())), flush=True)
    finally:
        registers.close()


if __name__ == '__main__': main()
