#!/usr/bin/env python3
"""Finite oscilloscope signal check with the external servo supply OFF.

Enable one channel at its existing command; never recenter or sweep. Register
readback is not proof of a waveform at the connector. Default is read-only.
"""
import argparse
import json
import time


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
        scope_check(PwmDevice(registers), args.channel, args.expected_sequence, args.seconds,
                    servo_power_off_confirmed=True,
                    emit=lambda event: print(json.dumps(event), flush=True))
    finally:
        registers.close()


if __name__ == '__main__':
    main()
