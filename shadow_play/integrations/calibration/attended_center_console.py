"""Operator-selected single-channel midpoint exception; never a story unlock.

Fixed 1500 us, five seconds maximum. First travel speed is NOT controlled.
No actual shaft feedback. The incident lock files remain unchanged.
"""
import hashlib
from pathlib import Path
import sys

LIB = '/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration'
if LIB not in sys.path:
    sys.path.append(LIB)
from board_server import require
from center_console import CenterController, serve, PREFIX
from servo_pwm_device import PwmDevice, Registers


class AttendedCenterDevice(PwmDevice):
    def __init__(self, registers, **kwargs):
        super().__init__(registers, **kwargs)
        self.permit = None
        self.inside = False
        self.lock_snapshot = self.lock_state()

    def lock_state(self):
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest()
                     if Path(p).exists() else None for p in self.motion_inhibit_paths)

    def _check_motion_allowed(self):
        if not self.inside:
            return super()._check_motion_allowed()
        require(self.lock_state() == self.lock_snapshot, 'Incident lock changed; reconnect and inspect')

    def commit(self, pulses, mask, allow_arm=False):
        permit, self.permit = self.permit, None
        require(permit is not None, 'Explicit operator midpoint request required')
        channel, sequence = permit
        before = self.status()
        require(not before['armed'] and before['enabled_mask'] == 0 and
                not before['pending'] and not before['faults'], 'All outputs must be OFF without faults')
        require(before['sequence'] == sequence, 'State changed after operator request')
        expected = before['pulse_us'][:]
        expected[channel-1] = 1500
        require(pulses == expected and mask == 1 << (channel-1) and allow_arm is True,
                'Only one selected channel at 1500 us is allowed')
        self.inside = True
        try:
            return super().commit(pulses, mask, allow_arm=True)
        finally:
            self.inside = False


class AttendedCenterController(CenterController):
    service_name = 'attended-midpoint-v1'

    def decode_motion(self, operation, payload):
        require(set(payload) == {'channel', 'observer_confirmed', 'initial_jump_acknowledged', 'sequence'},
                'Explicit observer, travel and sequence acknowledgement required')
        channel = payload['channel']
        require(type(channel) is int and 1 <= channel <= 10, 'channel must be 1..10')
        require(payload['observer_confirmed'] is True and payload['initial_jump_acknowledged'] is True,
                'Observer and uncontrolled initial travel acknowledgement required')
        require(type(payload['sequence']) is int, 'Sequence must be an integer')
        self.device.permit = (channel, payload['sequence'])
        return channel, 1500

    def tick(self):
        if self.deadline is not None and self.device.lock_state() != self.device.lock_snapshot:
            self.device.off()
            self.deadline = None
        super().tick()

    def handle(self, request):
        try:
            return super().handle(request)
        finally:
            self.device.permit = None


def main():
    import json
    registers = Registers()
    device = AttendedCenterDevice(registers)
    controller = None
    try:
        controller = AttendedCenterController(device)
        emit = lambda value: print(PREFIX + json.dumps(value), flush=True)
        emit({'ready': True, 'state': controller.status()})
        serve(controller, sys.stdin.fileno(), emit)
    except KeyboardInterrupt:
        pass
    finally:
        if controller is not None:
            device.off()
        registers.close()


if __name__ == '__main__':
    main()
