"""Attended, one-target-at-a-time commands retaining manually enabled outputs.

This is not a choreography or automatic recovery interface. Incident lock files
are retained. Startup is read-only and refuses another owner's active outputs.
"""
import copy
import json
import re
import sys

from attended_center_console import AttendedCenterDevice
from board_server import require
from center_console import CenterController, PREFIX, serve
from servo_pwm_device import PwmDevice, Registers


class MechanismManualDevice(AttendedCenterDevice):
    def commit(self, pulses, mask, allow_arm=False):
        permit, self.permit = self.permit, None
        require(permit is not None, 'Explicit attended single-target request required')
        channel, pulse, sequence, expected_mask = permit
        before = self.status()
        require(not before['pending'] and not before['faults'], 'Pending or fault state')
        require(before['sequence'] == sequence and before['enabled_mask'] == expected_mask,
                'Output state changed after operator request')
        idle = before['armed'] is False and expected_mask == 0
        active = before['armed'] is True and 0 < expected_mask < 1024
        require(idle or active, 'Output state is inconsistent')
        require(allow_arm is idle, 'Watchdog expiry must not automatically re-arm')
        expected = before['pulse_us'][:]
        expected[channel-1] = pulse
        require(pulses == expected and mask == expected_mask | (1 << (channel-1)),
                'Only selected target may change; previously enabled outputs must remain')
        self.inside = True
        try:
            return PwmDevice.commit(self, pulses, mask, allow_arm=allow_arm)
        finally:
            self.inside = False


class MechanismManualController(CenterController):
    service_name = 'attended-mechanism-v1'
    hold_seconds = None

    def __init__(self, device, **kwargs):
        super().__init__(device, **kwargs)
        self.owned_mask = 0
        self.output_lost = False

    def tick(self):
        state = self.device.status()
        if self.owned_mask and (state['armed'] is not True or state['enabled_mask'] != self.owned_mask
                                or state['pending'] or state['faults']):
            self.output_lost = True
            self.device.off()
        if self.device.lock_state() != self.device.lock_snapshot:
            self.output_lost = True
            if state['armed'] or state['enabled_mask']:
                self.device.off()

    def status(self):
        state = super().status()
        state.update(retaining_other_outputs=True, hold_mode='until_stopped',
                     manual_pulse_range_us=[500, 2500], position_feedback=None,
                     output_lost=self.output_lost)
        return state

    def handle(self, request):
        self.tick()
        require(isinstance(request, dict), 'Request object required')
        ident = request.get('transport_id')
        require(isinstance(ident, str) and re.fullmatch(r'[a-f0-9]{32}', ident), 'Invalid transport ID')
        encoded = json.dumps(request, sort_keys=True, allow_nan=False)
        if ident in self.cache:
            previous, ack = self.cache[ident]
            require(previous == encoded, 'Transport ID reused with different request')
            return copy.deepcopy(ack)
        ack = dict(transport_id=ident, ok=False)
        try:
            require(set(request) == {'transport_id', 'operation', 'payload'}, 'Invalid envelope')
            operation, payload = request['operation'], request['payload']
            require(isinstance(payload, dict), 'Payload object required')
            if operation in ('hello', 'status', 'heartbeat', 'off'):
                require(not payload, 'Unexpected payload')
                if operation == 'off':
                    self.device.off()
                    self.owned_mask = 0
                    self.output_lost = False
                elif operation == 'heartbeat':
                    self.device.kick()
            elif operation == 'move':
                require(len(self.cache) < 20000, 'Manual session exhausted; reconnect after stopping')
                require(set(payload) == {'channel', 'pulse_us', 'observer_confirmed',
                        'initial_jump_acknowledged', 'sequence', 'expected_mask'}, 'Explicit single target required')
                channel, pulse = payload['channel'], payload['pulse_us']
                require(type(channel) is int and 1 <= channel <= 10, 'channel must be 1..10')
                require(type(pulse) is int and 500 <= pulse <= 2500, 'pulse_us must be 500..2500')
                require(type(payload['sequence']) is int and 0 <= payload['sequence'] <= 0xffffffff,
                        'Current integer sequence required')
                require(type(payload['expected_mask']) is int and 0 <= payload['expected_mask'] < 1024,
                        'Current ten-bit mask required')
                require(payload['observer_confirmed'] is True and payload['initial_jump_acknowledged'] is True,
                        'Onsite observer and initial travel acknowledgement required')
                require(not self.output_lost, 'Output was lost; explicitly stop and inspect before another command')
                state = self.device.status()
                require(not state['pending'] and not state['faults'], 'Pending or fault state')
                require(state['enabled_mask'] == self.owned_mask, 'Outputs are not owned by this session')
                require(state['sequence'] == payload['sequence'] and state['enabled_mask'] == payload['expected_mask'],
                        'State changed after operator request')
                idle = state['armed'] is False and self.owned_mask == 0
                require(idle or (state['armed'] is True and self.owned_mask != 0), 'Inconsistent output state')
                pulses = state['pulse_us'][:]
                pulses[channel-1] = pulse
                mask = self.owned_mask | (1 << (channel-1))
                self.device.permit = (channel, pulse, payload['sequence'], payload['expected_mask'])
                try:
                    self.device.commit(pulses, mask, allow_arm=idle)
                    self.owned_mask = mask
                except BaseException:
                    self.output_lost = True
                    self.device.off()
                    raise
                finally:
                    self.device.permit = None
            else:
                raise ValueError('Only explicit move, status, heartbeat and off are available')
            ack.update(ok=True, result=self.status())
        except Exception as error:
            ack['error'] = str(error)
        if request.get('operation') not in ('hello', 'status', 'heartbeat') and len(self.cache) < 20000:
            self.cache[ident] = (encoded, copy.deepcopy(ack))
        return ack


def main():
    registers = Registers()
    device = MechanismManualDevice(registers)
    controller = None
    try:
        controller = MechanismManualController(device)
        emit = lambda value: print(PREFIX+json.dumps(value, allow_nan=False), flush=True)
        emit(dict(ready=True, state=controller.status()))
        serve(controller, sys.stdin.fileno(), emit)
    except KeyboardInterrupt:
        pass
    finally:
        # A rejected startup must not stop outputs owned by another service.
        if controller is not None:
            device.off()
        registers.close()


if __name__ == '__main__':
    main()
