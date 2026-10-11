#!/usr/bin/env python3
"""One bounded, attended trial from a user-authorized visual estimate.

This is not the unloaded console and does not verify an actual joint angle.
The first activation may jump to the requested position. Only use when the
operator has explicitly chosen this procedure and can immediately cut power.
No image loading, all-channel initialization, motion retry or automatic sweep.
"""
import argparse
import json
import math
import time


def trial(device, channel, pulse_us, *, observer_present=False,
          estimated_start_authorized=False, hold_seconds=1.0, emit=None):
    if observer_present is not True or estimated_start_authorized is not True:
        raise ValueError('Explicit attended estimated-start authorization required')
    if type(channel) is not int or not 1 <= channel <= 10:
        raise ValueError('One channel in 1..10 required')
    if type(pulse_us) is not int or not 500 <= pulse_us <= 2500:
        raise ValueError('Integer pulse in 500..2500 required')
    if (type(hold_seconds) not in (int, float) or
            not math.isfinite(hold_seconds) or not .2 <= hold_seconds <= 2):
        raise ValueError('Trial duration must be 0.2..2 seconds')
    before = device.status()
    if (before.get('identity') != 'SP10' or before.get('clock_hz') != 100000000 or
            before.get('period_us') != 20000 or before.get('armed') is not False or
            before.get('enabled_mask') != 0 or before.get('pending') is not False or
            before.get('faults') != 0):
        raise RuntimeError('Verified SP10 and all outputs off without faults required')
    pulses = before['pulse_us'][:]
    if len(pulses) != 10:
        raise ValueError('Ten adopted pulse registers required')
    pulses[channel-1] = pulse_us
    report = emit or (lambda event: None)
    # Start the OFF guarantee before commit: an uncertain commit must not retry.
    try:
        adopted = device.commit(pulses, 1 << (channel-1), allow_arm=True)
        if (adopted['enabled_mask'] != 1 << (channel-1) or
                adopted['pulse_us'] != pulses or not adopted['armed'] or
                adopted['pending'] or adopted['faults']):
            raise RuntimeError('Adopted trial state does not match the request')
        report({'event': 'adopted', 'channel': channel, 'state': adopted,
                'reference_basis': 'user_authorized_visual_estimate',
                'actual_position_verified': False})
        deadline = time.monotonic() + hold_seconds
        while time.monotonic() < deadline:
            state = device.status()
            if (not state['armed'] or state['faults'] or state['pending'] or
                    state['enabled_mask'] != 1 << (channel-1) or
                    state['pulse_us'] != pulses):
                raise RuntimeError('Trial interrupted; inspect state, do not retry')
            device.kick()
            time.sleep(.05)
    finally:
        stopped = device.off()
        report({'event': 'outputs_off', 'state': stopped})
    return adopted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', type=int, choices=range(1, 11), required=True)
    parser.add_argument('--pulse-us', type=int, required=True)
    parser.add_argument('--hold-seconds', type=float, default=1.0)
    parser.add_argument('--observer-present', action='store_true')
    parser.add_argument('--estimated-start-authorized', action='store_true')
    parser.add_argument('--execute', action='store_true',
                        help='Without this flag, print the proposal without opening hardware')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'dry_run': True, 'channel': args.channel,
                          'pulse_us': args.pulse_us, 'hold_seconds': args.hold_seconds,
                          'actual_position_verified': False}))
        return
    from servo_pwm_device import Registers, PwmDevice
    registers = Registers()
    try:
        trial(PwmDevice(registers), args.channel, args.pulse_us,
              observer_present=args.observer_present,
              estimated_start_authorized=args.estimated_start_authorized,
              hold_seconds=args.hold_seconds,
              emit=lambda event: print(json.dumps(event), flush=True))
    finally:
        registers.close()


if __name__ == '__main__':
    main()
