"""Local attended single-axis boundary probing; no automatic choreography unlock."""
import json
import sys
from attended_center_console import AttendedCenterDevice
from board_server import require
from center_console import PREFIX, serve
from manual_servo_console import ManualController
from servo_pwm_device import PwmDevice, Registers


class AttendedAngleDevice(AttendedCenterDevice):
    def commit(self, pulses, mask, allow_arm=False):
        permit, self.permit = self.permit, None
        require(permit is not None, 'Explicit attended single-axis target required')
        channel, pulse, sequence = permit
        before = self.status()
        require(not before['pending'] and not before['faults'], 'Pending or fault state')
        require(before['sequence'] == sequence, 'State changed after operator request')
        idle = not before['armed'] and before['enabled_mask'] == 0
        same = before['armed'] and before['enabled_mask'] == 1 << (channel-1)
        require(idle or same, 'Stop before selecting another axis')
        require(allow_arm is idle, 'No unexpected re-arm')
        expected = before['pulse_us'][:]; expected[channel-1] = pulse
        require(pulses == expected and mask == 1 << (channel-1), 'Only the selected target may change')
        self.inside = True
        try:
            return PwmDevice.commit(self, pulses, mask, allow_arm=allow_arm)
        finally:
            self.inside = False


class AttendedAngleController(ManualController):
    service_name = 'attended-angle-v1'
    motion_operations = ('move',)

    def status(self):
        state = super().status()
        state.update(manual_command_policy='attended-single-axis',
                     manual_diagnostics_available=self.device.lock_state() == self.device.lock_snapshot,
                     incident_lock_retained=any(x is not None for x in self.device.lock_snapshot),
                     manual_channel_range=[1,10], manual_requires_observer=True)
        return state

    def decode_motion(self, operation, payload):
        require(set(payload) == {'channel','pulse_us','observer_confirmed','initial_jump_acknowledged','sequence'},
                'Single target, observer, initial travel and current sequence required')
        channel, pulse = payload['channel'], payload['pulse_us']
        require(type(channel) is int and 1 <= channel <= 10, 'channel must be 1..10')
        require(type(pulse) is int and 500 <= pulse <= 2500, 'pulse_us must be 500..2500')
        require(type(payload['sequence']) is int, 'Integer sequence required')
        require(payload['observer_confirmed'] is True and payload['initial_jump_acknowledged'] is True,
                'Onsite observation and initial travel acknowledgement required')
        self.device.permit = (channel,pulse,payload['sequence'])
        return channel,pulse

    def handle(self, request):
        try:
            return super().handle(request)
        finally:
            self.device.permit = None

    def tick(self):
        if self.device.lock_state() != self.device.lock_snapshot and self.device.status()['armed']:
            self.device.off()
        super().tick()


def main():
    r = Registers(); d = AttendedAngleDevice(r); controller = None
    try:
        controller = AttendedAngleController(d)
        emit = lambda value: print(PREFIX+json.dumps(value,allow_nan=False),flush=True)
        emit(dict(ready=True,state=controller.status()))
        serve(controller,sys.stdin.fileno(),emit)
    except KeyboardInterrupt:
        pass
    finally:
        if controller is not None:d.off()
        r.close()

if __name__ == '__main__': main()
