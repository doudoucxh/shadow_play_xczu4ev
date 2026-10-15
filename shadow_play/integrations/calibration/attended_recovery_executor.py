"""One attended recovery route from an already active, reviewed pose.

Never arms OFF hardware. Unknown-angle cold recovery is deliberately unsupported.
Incident files remain present; ordinary driver objects remain inhibited.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import signal
import time

from attended_recovery_review import review
from servo_pwm_device import PwmDevice, Registers


class RecoveryDevice(PwmDevice):
    def __init__(self, registers, plan, expected_sequence, *, clock=time.monotonic,
                 cancel_path='/run/shadow-pwm-recovery-cancel', motion_inhibit_paths=None):
        result = review(plan)
        if result['reasons']:
            raise ValueError('Recovery review blocked: ' + ', '.join(result['reasons']))
        if type(expected_sequence) is not int or not 0 <= expected_sequence < 2**32:
            raise ValueError('Inspected sequence required')
        super().__init__(registers, motion_inhibit_paths=motion_inhibit_paths)
        self.plan = copy.deepcopy(plan)
        self.frames = self.plan['route']['frames_us']
        self.index = 0
        self.sequence = expected_sequence
        self.clock = clock
        self.deadline = clock() + 65
        self.cancel_path = Path(cancel_path)
        self.hashes = self.lock_hashes()
        self.inside = False
        self.consumed = False

    def lock_hashes(self):
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest()
                     for p in self.motion_inhibit_paths)

    def check(self):
        if self.cancel_path.exists() or self.clock() >= self.deadline:
            raise RuntimeError('Recovery cancelled or expired')
        if self.hashes != self.lock_hashes():
            raise RuntimeError('Incident locks changed')
        s = self.status()
        if (s['identity'] != 'SP10' or s['period_us'] != 20000 or
                s['clock_hz'] != 100000000 or not s['armed'] or
                s['enabled_mask'] != 1023 or s['faults'] or s['pending'] or
                s['sequence'] != self.sequence or s['pulse_us'] != self.frames[self.index]):
            raise RuntimeError('Reviewed active pose lost; never re-arm or retry')
        return s

    def _check_motion_allowed(self):
        if not self.inside:
            return super()._check_motion_allowed()
        self.check()

    def commit(self, pulses, mask, allow_arm=False):
        raise RuntimeError('Use fixed-route advance only; arbitrary targets forbidden')

    def advance(self):
        self.check()
        if self.index + 1 >= len(self.frames):
            raise RuntimeError('Route exhausted')
        self.inside = True
        try:
            s = super().commit(self.frames[self.index+1], 1023, allow_arm=False)
        except BaseException:
            self.deadline = float('-inf')
            raise
        finally:
            self.inside = False
        self.index += 1
        self.sequence = s['sequence']
        return s


def run(device, emit, *, clock=time.monotonic, sleep=time.sleep):
    if device.consumed:
        raise RuntimeError('Session already consumed')
    device.consumed = True
    complete = False
    try:
        emit({'event': 'start', 'state': device.check(), 'position_feedback': None})
        # Pace after adoption, never skip frames or catch up after a stall.
        # Blocking frame adoption may lengthen the route; log actual times.
        started = clock()
        for _ in device.frames[1:]:
            due = clock() + .02
            while clock() < due:
                device.check()
                device.kick()
                sleep(min(.005, due-clock()))
            if clock()-due > .04:
                raise RuntimeError('Scheduler stalled; no catch-up')
            state = device.advance()
            emit({'event': 'frame', 'index': device.index,
                  'elapsed_seconds': clock()-started, 'state': state})
        # Brief settling hold; no indefinite energization.
        until = clock() + 1
        while clock() < until:
            device.check()
            device.kick()
            sleep(min(.01, until-clock()))
        complete = True
    finally:
        state = device.stop_after_frame() if complete else device.off()
        emit({'event': 'off', 'state': state, 'route_complete': complete,
              'physical_pose_verified': False, 'incident_locks_removed': False})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan', type=Path)
    p.add_argument('--expected-sequence', type=int)
    p.add_argument('--execute-reviewed-active-route', action='store_true')
    p.add_argument('--log', type=Path)
    args = p.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
    result = review(plan)
    if not args.execute_reviewed_active_route:
        print(json.dumps(result))
        return 2 if result['reasons'] else 0
    if result['reasons'] or args.expected_sequence is None or args.log is None:
        p.error('Passing review, inspected sequence and fresh log path required')
    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    with args.log.open('x', encoding='utf-8') as log:
        def emit(row):
            log.write(json.dumps(row)+'\n')
            log.flush()
        registers = Registers()
        try:
            device = RecoveryDevice(registers, plan, args.expected_sequence)
            run(device, emit)
        finally:
            registers.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
