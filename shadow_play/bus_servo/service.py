"""Typed board protocol. No arbitrary command, pin, address, or shell RPC."""
import argparse
import json
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


class Controller:
    def __init__(self, profile, device, allow_motion=False):
        self.profile, self.device = profile, device
        self.allow_motion = allow_motion
        self.last_sequence = 0
        self.closed = False
        self.verified = set(profile.axes) if device.simulation else set()

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

    def permitted(self, payload):
        if payload.get('attended') is not True:
            raise ValueError('Onsite operator acknowledgement required')
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
                    'capabilities': [BOARD_ONLY],
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
        if op == 'move':
            self.permitted(payload)
            targets = payload['targets']
            if not isinstance(targets, dict) or not targets or any(str(int(n)) != n for n in targets):
                raise ValueError('Canonical axis-number keys required')
            axes = self.profile.select([int(n) for n in targets])
            self.require_servos([a.number for a in axes])
            duration = integer(payload['duration_ms'], 20, 9999, 'Duration')
            for a in axes:
                a.check_position(targets[str(a.number)])
            # Validate the whole selected group before sending any target.
            before = self.device.read([a.number for a in axes])
            for a in axes:
                delta = abs(a.degrees(targets[str(a.number)]) - a.degrees(before[a.number]['p']))
                if delta > a.max_speed * duration / 1000 + .2:
                    raise ValueError(f'Axis {a.number}: increase move duration or reduce target distance')
            self.device.move(targets, duration)
            return {'sent': True, 'physical_arrival_verified': False}
        if op == 'release':
            self.permitted(payload)
            self.require_servos(payload['numbers'])
            self.device.release(payload['numbers'])
            return {'released': payload['numbers']}
        if op == 'stop':
            if not self.device.simulation and not getattr(self.device, 'claimed', False):
                return {'state': 'no_motion_lease', 'physical_stop_verified': False}
            return {'state': self.device.stop()}
        if op == 'quit':
            self.closed = True
            return {'closing': True}
        raise ValueError('Unsupported operation')


def serve(controller, fd, emit, clock=time.monotonic):
    emit({'ready': True, 'service': 'bus-teach-v1', 'capabilities': [BOARD_ONLY]})
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
    args = parser.parse_args()
    profile = Profile.load(args.profile)
    if not args.simulate and not args.manifest:
        parser.error('--manifest required for hardware')
    if not args.simulate and profile.data.get('electrical_3v3_verified') is not True:
        parser.error('Verify bus electrical compatibility before transmitting even read-only queries')
    device = SimulationDevice(profile) if args.simulate else BusDevice(
        profile, Mmio(args.manifest, expected_layout=profile.layout.name))
    controller = Controller(profile, device, args.allow_motion)
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
