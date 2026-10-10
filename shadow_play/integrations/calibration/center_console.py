#!/usr/bin/env python3
"""Dedicated unloaded centering service: one channel, 1500 us, 5 s deadline.

No commissioning records are changed. Startup is read-only. The board deadline
and FPGA heartbeat watchdog are independent of the Windows user interface.
"""
import copy
import json
import os
import re
import select
import sys
import time

from board_server import require
from servo_pwm_device import PwmDevice, Registers
from tcp_bridge import parse_json

PREFIX = '@@SP10@@'
SERVICE = 'unloaded-center-v1'
HOLD_SECONDS = 5.0


class CenterController:
    service_name = SERVICE
    motion_operations = ('center',)
    hold_seconds = HOLD_SECONDS

    def __init__(self, device, clock=time.monotonic):
        self.device = device
        self.clock = clock
        self.deadline = None
        self.cache = {}
        state = device.status()
        require(not state['armed'] and state['enabled_mask'] == 0 and not state['pending'],
                'All outputs must be OFF before starting the centering service')

    def tick(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            self.device.off()
            self.deadline = None

    def status(self):
        state = self.device.status()
        state.update(service=self.service_name, center_hold_seconds=self.hold_seconds,
                     center_remaining_seconds=max(0, self.deadline-self.clock())
                     if self.deadline is not None else 0)
        return state

    def decode_motion(self, operation, payload):
        require(set(payload) == {'channel', 'unloaded_confirmed'}, 'center accepts one channel and confirmation')
        channel = payload['channel']
        require(type(channel) is int and 1 <= channel <= 10, 'channel must be 1..10')
        require(payload['unloaded_confirmed'] is True, 'detach linkage AND interfering bracket before centering')
        return channel, 1500

    def validate_motion_state(self, state, channel):
        require(not state['armed'] and state['enabled_mask'] == 0 and not state['pending'],
                'Outputs already active; stop before choosing another servo')
        return True  # An explicit new command may arm an idle output.

    def handle(self, request):
        self.tick()
        require(isinstance(request, dict), 'request object required')
        ident = request.get('transport_id')
        require(isinstance(ident, str) and re.fullmatch(r'[a-f0-9]{32}', ident), 'invalid transport ID')
        encoded = json.dumps(request, sort_keys=True, allow_nan=False)
        if ident in self.cache:
            previous, ack = self.cache[ident]
            require(previous == encoded, 'transport ID reused with different request')
            return copy.deepcopy(ack)  # Never re-execute an uncertain/replayed action.
        require(len(self.cache) < 20000 or request.get('operation') in ('hello', 'status', 'heartbeat', 'off'),
                'motion session exhausted; restart the board service before further motion')
        ack = {'transport_id': ident, 'ok': False}
        try:
            require(set(request) == {'transport_id', 'operation', 'payload'}, 'invalid envelope')
            operation, payload = request['operation'], request['payload']
            require(isinstance(payload, dict), 'payload object required')
            if operation in ('hello', 'status', 'heartbeat', 'off'):
                require(not payload, 'unexpected payload')
                if operation == 'off':
                    self.device.off()
                    self.deadline = None
                elif operation == 'heartbeat':
                    self.device.kick()
            elif operation in self.motion_operations:
                channel, pulse = self.decode_motion(operation, payload)
                state = self.device.status()
                allow_arm = self.validate_motion_state(state, channel)
                pulses = state['pulse_us'][:]
                pulses[channel-1] = pulse
                self.deadline = (self.clock() + self.hold_seconds
                                 if self.hold_seconds is not None else None)
                try:
                    self.device.commit(pulses, 1 << (channel-1), allow_arm=allow_arm)
                except BaseException:
                    self.device.off()
                    self.deadline = None
                    raise
            else:
                raise ValueError('Only status, off and unloaded center are available')
            ack.update(ok=True, result=self.status())
        except Exception as error:
            ack['error'] = str(error)
        # Idle status/heartbeats are repeatable and must not exhaust the motion
        # replay cache during a long mechanical assembly session. OFF remains
        # available even when the bounded motion cache is full.
        if request.get('operation') not in ('hello', 'status', 'heartbeat') and len(self.cache) < 20000:
            self.cache[ident] = (encoded, copy.deepcopy(ack))
        return ack


def serve(controller, input_fd, emit):
    """Use unbuffered fd reads so a partial serial line cannot block the deadline."""
    buffered = b''
    while True:
        controller.tick()
        if not select.select([input_fd], [], [], .05)[0]:
            continue
        chunk = os.read(input_fd, 4096)
        if not chunk:
            return
        buffered += chunk
        while b'\n' in buffered:
            line, buffered = buffered.split(b'\n', 1)
            if len(line) > 4096:
                raise ValueError('oversized console frame')
            if not line.strip():
                # A blank line is a read-only connection probe from the host.
                emit({'ready': True, 'state': controller.status()})
                continue
            try:
                emit(controller.handle(parse_json(line.decode('utf-8'))))
            except Exception as error:
                emit({'protocol_error': str(error)})
        if len(buffered) > 4096:
            raise ValueError('oversized partial console frame')


def run_controller(controller_type=CenterController):
    registers = Registers()  # Refuses MMIO without this boot's verified image marker.
    device = PwmDevice(registers)
    controller = None
    try:
        controller = controller_type(device)
        emit = lambda message: print(PREFIX + json.dumps(message, allow_nan=False), flush=True)
        emit({'ready': True, 'state': controller.status()})
        serve(controller, sys.stdin.fileno(), emit)
    except KeyboardInterrupt:
        pass
    finally:
        if controller is not None:
            device.off()
        registers.close()


if __name__ == '__main__':
    run_controller()
