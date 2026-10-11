#!/usr/bin/env python3
"""Retired visual-estimate trial entry point; proposals only, never hardware.

On 2026-10-11 a loaded tiger puppet was pulled during the session. An estimated
shaft angle and an old command register cannot establish its current position.
Keep this entry point to reject old invocations explicitly, including imports.
"""
import argparse
import json


RETIRED_REASON = ('Visual-estimate loaded start is disabled after puppet pulling; '
                  'inspect the linkage and establish a verified unloaded start first')


def trial(device, channel, pulse_us, *, observer_present=False,
          estimated_start_authorized=False, hold_seconds=1.0, emit=None):
    # Retain the old signature for callers, but never touch even device.status().
    raise RuntimeError(RETIRED_REASON)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', type=int, choices=range(1, 11), required=True)
    parser.add_argument('--pulse-us', type=int, required=True)
    parser.add_argument('--hold-seconds', type=float, default=1.0)
    parser.add_argument('--observer-present', action='store_true')
    parser.add_argument('--estimated-start-authorized', action='store_true')
    parser.add_argument('--execute', action='store_true', help='Retired; execution is always rejected')
    args = parser.parse_args()
    if args.execute:
        parser.error(RETIRED_REASON)
    print(json.dumps({'dry_run': True, 'execution_allowed': False,
                      'reason': RETIRED_REASON, 'channel': args.channel,
                      'pulse_us': args.pulse_us, 'hold_seconds': args.hold_seconds,
                      'actual_position_verified': False}))


if __name__ == '__main__':
    main()
