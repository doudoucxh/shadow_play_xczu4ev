"""Typed board protocol. No arbitrary command, pin, address, or shell RPC."""
import argparse
import json
import math
import os
from pathlib import Path
import select
import sys
import time

from .device import BusDevice, Mmio, SimulationDevice
from .model import Profile
from .protocol import integer, ServoUnavailable

PREFIX = '@@BUS10@@'
BOARD_ONLY = 'board-only-v1'
SELECTED_RELEASE = 'selected-release-v1'
ADAPTIVE_PLAYBACK = 'adaptive-playback-v1'
CONTINUOUS_PLAYBACK = 'continuous-playback-v1'


class Controller:
    def __init__(self, profile, device, allow_motion=False, allow_release=False, clock=time.monotonic, sleep=time.sleep):
        self.profile, self.device = profile, device
        self.allow_motion = allow_motion
        self.allow_release = allow_release
        self.last_sequence = 0
        self.closed = False
        self.verified = set(profile.axes) if device.simulation else set()
        self.clock, self.sleep = clock, sleep
        self.playback_due = None
        self.playback_sequence = 0
        self.playback_axes = None

    def playback_step(self, payload, seq):
        """One explicitly requested successor, checked while the prior move runs.

        No stored trajectory or background movement. The PC sends at most one
        successor early; this bounded RPC waits for the board's cadence, then
        sends once. Each call reads actual feedback and retains the FPGA lease.
        """
        self.permitted(payload)
        if self.profile.data.get('playback_speed_limit_enabled', True) is not False:
            raise ValueError('Timed playback requires the operator-confirmed recording-speed setting')
        targets = payload['targets']
        if not isinstance(targets, dict) or not targets or any(str(int(n)) != n for n in targets):
            raise ValueError('Canonical axis-number keys required')
        axes = self.profile.select([int(n) for n in targets])
        numbers = [a.number for a in axes]
        self.require_servos(numbers)
        duration = integer(payload['duration_ms'], 20, 9999, 'Duration')
        previous = integer(payload['previous'], 0, 2**31-1, 'Previous playback sequence')
        started = self.clock()
        if previous:
            if previous != self.playback_sequence or self.playback_axes != set(numbers) or self.playback_due is None:
                raise ValueError('Playback chain/axes mismatch; no continuation')
            if started-self.playback_due > 1:
                raise TimeoutError('Playback successor arrived over one second late; no resume')
            gate = self.playback_due
        else:
            if self.playback_due is not None and started < self.playback_due:
                raise ValueError('Previous playback segment is still active')
            gate = started
        if gate-started > .35:
            raise ValueError('Playback successor requested too early')
        for a in axes:
            a.check_position(targets[str(a.number)])
        before = self.device.read(numbers)
        if set(before) != set(numbers):
            raise ValueError('Playback feedback axis set mismatch')
        for a in axes:
            a.degrees(before[a.number]['p'])
        # Bounded wait, never advance or shrink the recorded movement duration.
        while self.clock() < gate:
            self.sleep(min(.005, gate-self.clock()))
        if self.clock()-started > .65 or any(self.clock()-row['at'] > .5 for row in before.values()):
            raise TimeoutError('Playback feedback became stale before dispatch')
        dispatch = self.clock()
        self.device.move(targets, duration)
        # Start-to-start cadence avoids adding read/USB/ACK time to every frame.
        # UART axes are still sequential, not hardware-synchronous triggers.
        self.playback_due = dispatch+duration/1000
        self.playback_sequence, self.playback_axes = seq, set(numbers)
        return dict(sent=True, duration_ms=duration, requested_duration_ms=duration,
                    chain=seq, dispatch_age_s=self.clock()-dispatch,
                    feedback=[[n,before[n]['p'],round(before[n]['at'],6)] for n in numbers])

    def require_servos(self, numbers):
        self.profile.select(numbers)
        if not set(numbers) <= self.verified:
            raise ServoUnavailable('板子已连接，所选舵机尚未检测；供电后点击“检测所选舵机”。')

    def query(self, action):
        was_claimed = getattr(self.device, 'claimed', False)
        try:
            return action()
        except Exception as exc:
            self.verified.clear()
            # Active motion failures still terminate the session and request stop.
            # Only idle feedback failure preserves the board link; no retry.
            if self.device.simulation or was_claimed:
                raise
            self.device.failed = True
            raise ServoUnavailable('舵机未取得有效反馈（可能未供电或未连接），板子连接保留。'
                                   '检查供电、ID和接线后，断开重连再手动检测；未自动重试。详情：' + str(exc)) from exc

    def release_allowed(self):
        return self.device.simulation or (self.profile.data.get('electrical_3v3_verified') is True
            and (self.allow_release or (self.allow_motion and all(self.profile.data.get(k) is True
                for k in ('hardware_verified', 'mechanical_limits_verified')))))

    def permitted(self, payload, *, release=False):
        if payload.get('attended') is not True:
            raise ValueError('Onsite operator acknowledgement required')
        if release:
            if not self.release_allowed():
                raise RuntimeError('板端尚未开放所选轴卸力；请更新卸力服务配置。')
            return
        if not self.device.simulation:
            for key in ('hardware_verified', 'electrical_3v3_verified', 'mechanical_limits_verified'):
                if self.profile.data.get(key) is not True:
                    raise RuntimeError(f'Commissioning incomplete: {key}')
            if not self.allow_motion:
                raise RuntimeError('Board service is read-only; commissioning release required')

    def execute(self, request):
        if set(request) != {'seq', 'op', 'payload'} or not isinstance(request['payload'], dict):
            raise ValueError('Invalid request envelope')
        seq = integer(request['seq'], 1, 2**31 - 1, 'Sequence')
        if seq != self.last_sequence + 1:
            raise ValueError('Out-of-order or duplicate request; never re-execute')
        self.last_sequence = seq
        op, payload = request['op'], request['payload']
        if op == 'hello':
            return {'service': 'bus-teach-v1', 'profile': self.profile.fingerprint,
                    'simulation': self.device.simulation,
                    'motion_allowed': self.device.simulation or (self.allow_motion and all(self.profile.data.get(k) is True
                        for k in ('hardware_verified', 'electrical_3v3_verified', 'mechanical_limits_verified'))),
                    'release_allowed': self.release_allowed(),
                    'capabilities': [BOARD_ONLY, SELECTED_RELEASE, ADAPTIVE_PLAYBACK, CONTINUOUS_PLAYBACK],
                    'playback_speed_limit_enabled': self.profile.data.get('playback_speed_limit_enabled', True),
                    'positions': self.device.connect() if self.device.simulation else {},
                    'board': None if self.device.simulation else self.device.board_status()}
        if op == 'status':
            return {'board': None if self.device.simulation else self.device.board_status(),
                    'verified': sorted(self.verified)}
        if op == 'probe':
            numbers = payload['numbers']
            self.profile.select(numbers)
            if getattr(self.device, 'claimed', False):
                raise RuntimeError('请先停止当前运动会话，再检测舵机。')
            self.verified.clear()
            rows = self.query(lambda: self.device.read(numbers) if self.device.simulation else self.device.connect(numbers))
            self.verified = set(numbers)
            return rows
        if op == 'read':
            self.require_servos(payload['numbers'])
            return self.query(lambda: self.device.read(payload['numbers']))
        if op == 'play_step':
            return self.playback_step(payload, seq)
        if op == 'move':
            self.playback_sequence, self.playback_due = 0, None
            self.permitted(payload)
            targets = payload['targets']
            if not isinstance(targets, dict) or not targets or any(str(int(n)) != n for n in targets):
                raise ValueError('Canonical axis-number keys required')
            axes = self.profile.select([int(n) for n in targets])
            self.require_servos([a.number for a in axes])
            duration = integer(payload['duration_ms'], 20, 9999, 'Duration')
            adaptive = payload.get('adaptive_duration', False)
            if type(adaptive) is not bool:
                raise ValueError('Adaptive duration must be boolean')
            requested_duration = duration
            for a in axes:
                a.check_position(targets[str(a.number)])
            # Validate the whole selected group before sending any target.
            before = self.device.read([a.number for a in axes])
            for a in axes:
                delta = abs(a.degrees(targets[str(a.number)]) - a.degrees(before[a.number]['p']))
                if adaptive:
                    # Recorded targets are not measured arrival positions. Use
                    # fresh feedback to give the entire group enough time.
                    duration = max(duration, math.ceil(delta / a.max_speed * 1000 - 1e-8))
                    if duration > 9999:
                        raise ValueError(f'{a.number}号从实际位置到目标需要超过9999ms，请分步接近目标。')
                if delta > a.max_speed * duration / 1000 + .2:
                    raise ValueError(f'Axis {a.number}: increase move duration or reduce target distance')
            self.device.move(targets, duration)
            return {'sent': True, 'physical_arrival_verified': False,
                    'duration_ms': duration, 'requested_duration_ms': requested_duration}
        if op == 'release':
            self.playback_sequence, self.playback_due = 0, None
            self.permitted(payload, release=True)
            self.require_servos(payload['numbers'])
            # Validate fresh feedback for the entire group before any torque-off.
            self.query(lambda: self.device.read(payload['numbers']))
            self.device.release(payload['numbers'])
            return {'release_acknowledged': payload['numbers'], 'physical_release_verified': False}
        if op == 'stop':
            self.playback_sequence, self.playback_due = 0, None
            if not self.device.simulation and not getattr(self.device, 'claimed', False):
                return {'state': 'no_motion_lease', 'physical_stop_verified': False}
            return {'state': self.device.stop()}
        if op == 'quit':
            self.closed = True
            return {'closing': True}
        raise ValueError('Unsupported operation')


def serve(controller, fd, emit, clock=time.monotonic):
    emit({'ready': True, 'service': 'bus-teach-v1', 'capabilities': [BOARD_ONLY, SELECTED_RELEASE, ADAPTIVE_PLAYBACK, CONTINUOUS_PLAYBACK]})
    buffer = b''
    last = clock()
    while not controller.closed:
        # The FPGA lease is refreshed ONLY by accepted host operations, not by
        # this loop. A stuck host, process, serial link or poller expires it.
        if clock() - last > 2:
            break
        if not select.select([fd], [], [], .05)[0]:
            continue
        data = os.read(fd, 4096)
        if not data:
            break
        buffer += data
        if len(buffer) > 8192:
            raise ValueError('Oversized host request')
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            if not line.strip():
                continue
            request = json.loads(line)
            try:
                result = controller.execute(request)
                last = clock()
                emit({'seq': request['seq'], 'ok': True, 'result': result})
            except Exception as exc:
                if isinstance(exc, ServoUnavailable) and not getattr(controller.device, 'claimed', False):
                    last = clock()
                    emit({'seq': request.get('seq'), 'ok': False, 'error': str(exc),
                          'servo_unavailable': True})
                    continue
                # End a failed session. Do not consume a later queued movement.
                if getattr(controller.device, 'claimed', False):
                    controller.device.stop()
                emit({'seq': request.get('seq'), 'ok': False, 'error': str(exc)})
                controller.closed = True
                break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--simulate', action='store_true')
    parser.add_argument('--allow-motion', action='store_true')
    parser.add_argument('--allow-release', action='store_true', help='Allow explicit selected-axis torque release without enabling angle commands')
    args = parser.parse_args()
    profile = Profile.load(args.profile)
    if not args.simulate and not args.manifest:
        parser.error('--manifest required for hardware')
    if not args.simulate and profile.data.get('electrical_3v3_verified') is not True:
        parser.error('Verify bus electrical compatibility before transmitting even read-only queries')
    device = SimulationDevice(profile) if args.simulate else BusDevice(
        profile, Mmio(args.manifest, expected_layout=profile.layout.name))
    controller = Controller(profile, device, args.allow_motion, args.allow_release)
    fd = sys.stdin.fileno()
    previous = None
    try:
        if os.isatty(fd):
            import termios
            import tty
            previous = termios.tcgetattr(fd)
            tty.setraw(fd)
        serve(controller, fd, lambda value: print(PREFIX + json.dumps(value, separators=(',', ':'), allow_nan=False), flush=True))
    finally:
        device.close()
        if previous is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)


if __name__ == '__main__':
    main()
