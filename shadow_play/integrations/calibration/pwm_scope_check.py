#!/usr/bin/env python3
"""Finite oscilloscope signal check with the external servo supply OFF.

Enable one channel at its existing command; never recenter or sweep. Register
readback is not proof of a waveform at the connector. Default is read-only.
"""
import argparse
import json
import time
import hashlib
from pathlib import Path
from servo_pwm_device import PwmDevice


class PowerOffScopeDevice(PwmDevice):
    """One finite check may retain incident locks and enable an unchanged signal.

    The external supply must be physically OFF. This is not a motion recovery:
    no pulse change, other channel, second arm, or lock removal is permitted.
    """
    def __init__(self, registers, channel, *, servo_power_off_confirmed=False,
                 motion_inhibit_paths=None):
        if servo_power_off_confirmed is not True or type(channel) is not int or not 1 <= channel <= 10:
            raise ValueError('Power OFF confirmation and one channel required')
        super().__init__(registers, motion_inhibit_paths=motion_inhibit_paths)
        self.mask = 1 << (channel - 1)
        self.lock_receipt = self._locks()
        self.initial = super().status()
        self.used = False
        self.inside_check = False

    def _locks(self):
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest()
                     if Path(p).exists() else None for p in self.motion_inhibit_paths)

    def _verify_locks(self):
        if self._locks() != self.lock_receipt:
            raise RuntimeError('Incident lock state changed; stop signal check')

    def status(self):
        self._verify_locks()
        return super().status()

    def _check_motion_allowed(self):
        self._verify_locks()
        if not self.inside_check:
            raise RuntimeError('Only the single power-OFF signal check is permitted')

    def commit(self, pulses, mask, allow_arm=False):
        if (self.used or mask != self.mask or allow_arm is not True
                or pulses != self.initial['pulse_us'] or self.status() != self.initial
                or self.initial['armed'] or self.initial['enabled_mask']
                or self.initial['pending'] or self.initial['faults']):
            raise RuntimeError('Only one unchanged, selected-channel signal may be enabled')
        self.used = True
        self.inside_check = True
        try:
            return super().commit(pulses, mask, allow_arm=True)
        finally:
            self.inside_check = False


def scope_check(device, channel, expected_sequence, seconds=30, *,
                servo_power_off_confirmed=False, emit=print,
                clock=time.monotonic, sleep=time.sleep):
    if servo_power_off_confirmed is not True:
        raise ValueError('External servo power must be confirmed OFF')
    if type(channel) is not int or not 1 <= channel <= 10:
        raise ValueError('One channel in 1..10 required')
    if type(seconds) is not int or not 1 <= seconds <= 60:
        raise ValueError('Finite integer duration in 1..60 seconds required')
    if type(expected_sequence) is not int or expected_sequence < 0:
        raise ValueError('Inspected sequence required')
    before = device.status()
    if (before.get('identity') != 'SP10' or before.get('clock_hz') != 100000000 or
            before.get('period_us') != 20000 or before.get('armed') is not False or
            before.get('enabled_mask') != 0 or before.get('pending') is not False or
            before.get('faults') != 0 or before.get('sequence') != expected_sequence):
        raise RuntimeError('Inspected fault-free OFF state required; do not retry')
    pulses = before['pulse_us'][:]
    if len(pulses) != 10 or any(type(v) is not int or not 500 <= v <= 2500 for v in pulses):
        raise ValueError('Ten valid existing command registers required')
    mask = 1 << (channel - 1)

    def verify(state):
        if (state['enabled_mask'] != mask or not state['armed'] or state['faults'] or
                state['pending'] or state['pulse_us'] != pulses):
            raise RuntimeError('Signal check interrupted; no retry or rearm')

    try:
        adopted = device.commit(pulses, mask, allow_arm=True)
        verify(adopted)
        emit({'event': 'scope_signal_on', 'channel': channel, 'seconds': seconds,
              'servo_supply': 'operator_confirmed_off', 'state': adopted})
        deadline = clock() + seconds
        while clock() < deadline:
            verify(device.status())
            device.kick()
            sleep(.05)
    finally:
        emit({'event': 'outputs_off', 'state': device.off()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', type=int, required=True)
    parser.add_argument('--expected-sequence', type=int, required=True)
    parser.add_argument('--seconds', type=int, default=30)
    parser.add_argument('--servo-power-off-confirmed', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'dry_run': True, 'channel': args.channel, 'seconds': args.seconds,
                          'changes_commanded_pulse': False}))
        return
    if not args.servo_power_off_confirmed:
        parser.error('--execute requires --servo-power-off-confirmed')
    from servo_pwm_device import Registers, PwmDevice
    registers = Registers()
    try:
        scope_check(PowerOffScopeDevice(registers, args.channel, servo_power_off_confirmed=True),
                    args.channel, args.expected_sequence, args.seconds,
                    servo_power_off_confirmed=True,
                    emit=lambda event: print(json.dumps(event), flush=True))
    finally:
        registers.close()


if __name__ == '__main__':
    main()
