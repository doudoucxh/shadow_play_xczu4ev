#!/usr/bin/env python3
"""Explicit single-servo bench targets, within the supplied K15 PWM limits.

Holds until explicit stop/disconnect, with replay protection and FPGA watchdog.
Only use after releasing both rod and bracket constraints. No position feedback.
"""
from board_server import require
from center_console import CenterController, run_controller

SERVICE = 'unloaded-manual-v2'


class ManualController(CenterController):
    service_name = SERVICE
    motion_operations = ('center', 'move')
    hold_seconds = None

    def validate_motion_state(self, state, channel):
        require(not state['pending'] and not state['faults'],
                'PWM pending/fault state; stop and inspect before another command')
        if not state['armed'] and state['enabled_mask'] == 0:
            return True
        require(state['armed'] and state['enabled_mask'] == 1 << (channel-1),
                'Stop the active output before choosing another servo')
        # Do not re-arm if the watchdog expires between status and commit.
        return False

    def decode_motion(self, operation, payload):
        if operation == 'center':
            return super().decode_motion(operation, payload)
        require(set(payload) == {'channel', 'pulse_us', 'unloaded_confirmed'},
                'move accepts one channel, integer pulse_us and unloaded confirmation')
        channel, pulse = payload['channel'], payload['pulse_us']
        require(type(channel) is int and 1 <= channel <= 10, 'channel must be 1..10')
        require(type(pulse) is int and 500 <= pulse <= 2500, 'pulse_us must be an integer in 500..2500')
        require(payload['unloaded_confirmed'] is True, 'free servo shaft and observer required')
        return channel, pulse

    def status(self):
        state = super().status()
        state['manual_pulse_range_us'] = [500, 2500]
        state['hold_mode'] = 'until_stopped'
        state['same_channel_updates'] = True
        state['center_remaining_seconds'] = None if state['armed'] else 0
        return state


if __name__ == '__main__':
    run_controller(ManualController)
