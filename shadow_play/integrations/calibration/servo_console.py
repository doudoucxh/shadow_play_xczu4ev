#!/usr/bin/env python3
"""Framed PS-console service. Startup never enables a servo or changes its pulse.

Launch from a known root shell with console echo disabled. A host heartbeat only
keeps an already armed peripheral alive; it cannot rearm a timed-out peripheral.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
from board_server import Controller, require, validate_config
from servo_pwm_device import CaptureDriver, IDS, PwmDevice, Registers
from tcp_bridge import parse_json

PREFIX = '@@SP10@@'


class ConsoleController:
    def __init__(self, device, config=None, commissioning=None):
        self.device = device
        self.config = config
        self.commissioning = commissioning or {}
        self.capture = None
        self.cache = {}
        if config is not None:
            validate_config(config)

    def handle(self, req):
        require(isinstance(req, dict), 'request object required')
        ident = req.get('transport_id')
        require(isinstance(ident, str) and re.fullmatch(r'[a-f0-9]{32}', ident), 'invalid transport ID')
        encoded = json.dumps(req, sort_keys=True, allow_nan=False)
        if ident in self.cache:
            old, ack = self.cache[ident]
            require(old == encoded, 'transport ID reused with different request')
            return copy.deepcopy(ack)
        require(len(self.cache) < 20000, 'service session exhausted; OFF and start a new session')
        ack = {'transport_id': ident, 'ok': False}
        try:
            require(set(req) == {'transport_id', 'operation', 'payload'}, 'invalid envelope fields')
            operation, payload = req['operation'], req['payload']
            require(isinstance(payload, dict), 'payload object required')
            if operation in ('hello', 'status', 'heartbeat', 'off'):
                require(not payload, 'unexpected payload')
                if operation == 'heartbeat':
                    self.device.kick()
                elif operation == 'off':
                    self.device.off()
                    self.capture = None
                result = self.device.status()
            elif operation == 'initialize':
                require(self.capture is None or self.capture.owner is None,
                        'Capture GUI owns the current state; use GUI controls or explicitly turn outputs OFF')
                require(set(payload) == {'channel'}, 'initialize accepts one channel only')
                channel = payload['channel']
                require(type(channel) is int and 1 <= channel <= 10, 'channel must be 1..10')
                spec = self.commissioning.get(IDS[channel-1])
                require(isinstance(spec, dict), 'channel has no commissioning record')
                require(spec.get('reference_verified') is True and
                        spec.get('basis') in ('unloaded_center', 'installed_verified_reference'),
                        'known starting reference/unloaded linkage required')
                pulse = spec.get('initial_us')
                require(type(pulse) is int and type(spec.get('min_us')) is int and
                        type(spec.get('max_us')) is int and
                        500 <= spec['min_us'] <= pulse <= spec['max_us'] <= 2500,
                        'invalid commissioned pulse interval')
                state = self.device.status()
                require(not state['pending'] and not state['enabled_mask'] & (1 << (channel-1)),
                        'channel already enabled or update pending')
                require(not state['armed'] or not state['faults'], 'inspect fault and explicitly turn outputs OFF first')
                pulses = state['pulse_us'][:]
                pulses[channel-1] = pulse
                result = self.device.commit(pulses, state['enabled_mask'] | (1 << (channel-1)), allow_arm=True)
                self.capture = None
            elif operation == 'jog':
                require(self.capture is None or self.capture.owner is None,
                        'Capture GUI owns the current state; use GUI controls or explicitly turn outputs OFF')
                require(set(payload) == {'channel', 'delta_us'}, 'jog accepts channel and delta_us only')
                channel, delta = payload['channel'], payload['delta_us']
                require(type(channel) is int and 1 <= channel <= 10 and type(delta) is int and
                        0 < abs(delta) <= 5, 'one channel, integer 1..5 us step required')
                spec = self.commissioning.get(IDS[channel-1], {})
                require(spec.get('reference_verified') is True, 'uncommissioned channel')
                state = self.device.status()
                require(state['armed'] and state['enabled_mask'] & (1 << (channel-1)) and
                        not state['faults'] and not state['pending'], 'channel not ready')
                pulses = state['pulse_us'][:]
                pulses[channel-1] += delta
                require(spec['min_us'] <= pulses[channel-1] <= spec['max_us'], 'outside commissioned interval')
                result = self.device.commit(pulses, state['enabled_mask'])
                self.capture = None
            elif operation == 'capture':
                require(self.config is not None, 'validated real capture configuration required')
                if self.capture is None:
                    self.capture = Controller(self.config, CaptureDriver(self.config, self.device))
                result = self.capture.handle(payload)
            else:
                raise ValueError('unknown operation')
            ack.update(ok=True, result=result)
        except Exception as error:
            ack['error'] = str(error)
        # Cache failures too: no uncertain motion is retried on transport replay.
        self.cache[ident] = (encoded, copy.deepcopy(ack))
        return ack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--commissioning', type=Path)
    args = parser.parse_args()
    config = parse_json(args.config.read_text(encoding='utf-8-sig')) if args.config else None
    commissioning = parse_json(args.commissioning.read_text(encoding='utf-8-sig')) if args.commissioning else None
    registers = Registers()
    device = PwmDevice(registers)
    controller = ConsoleController(device, config, commissioning)
    print(PREFIX + json.dumps({'ready': True, 'state': device.status()}), flush=True)
    try:
        while True:
            line = sys.stdin.buffer.readline(4097)
            if not line:
                break
            if len(line) > 4096 or not line.endswith(b'\n'):
                raise ValueError('oversized/incomplete console frame')
            try:
                result = controller.handle(parse_json(line.decode('utf-8')))
                print(PREFIX + json.dumps(result, allow_nan=False, separators=(',', ':')), flush=True)
            except Exception as error:
                print(PREFIX + json.dumps({'protocol_error': str(error)}), flush=True)
    except KeyboardInterrupt:
        pass  # A deliberate Ctrl-C is a normal service shutdown.
    finally:
        device.off()
        registers.close()


if __name__ == '__main__':
    main()
