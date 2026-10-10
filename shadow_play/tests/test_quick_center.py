"""Hardware-free checks for fixed-pulse centering and its independent deadline."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/calibration'))
sys.path.insert(0, str(ROOT/'tools'))
from center_console import CenterController, serve
from servo_pwm_device import PwmDevice
from servo_center_session import CenterSession
from test_servo_commissioning import FakeRegisters


class QuickCenterTests(unittest.TestCase):
    def setUp(self):
        self.reg = FakeRegisters()
        self.now = 0
        self.controller = CenterController(PwmDevice(self.reg), clock=lambda: self.now)

    def request(self, operation, payload=None):
        return {'transport_id': uuid.uuid4().hex, 'operation': operation, 'payload': payload or {}}

    def center(self, channel=1):
        return self.request('center', {'channel': channel, 'unloaded_confirmed': True})

    def test_startup_status_and_unarmed_heartbeat_never_write(self):
        for operation in ('hello', 'status', 'heartbeat'):
            self.assertTrue(self.controller.handle(self.request(operation))['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_every_channel_exactly_one_output_fixed_pulse(self):
        for channel in range(1, 11):
            self.reg.values[0x80+4*(channel-1)] = 1400
            result = self.controller.handle(self.center(channel))
            self.assertTrue(result['ok'])
            self.assertEqual(result['result']['enabled_mask'], 1 << (channel-1))
            self.assertEqual(result['result']['pulse_us'][channel-1], 1500)
            self.controller.handle(self.request('off'))

    def test_invalid_confirmation_channel_pulse_or_duration_cannot_move(self):
        for channel in (True, 0, 11, 1.0, '1'):
            self.assertFalse(self.controller.handle(self.center(channel))['ok'])
        for confirm in (False, 1, 'true', None):
            request = self.center(); request['payload']['unloaded_confirmed'] = confirm
            self.assertFalse(self.controller.handle(request)['ok'])
        for extra in ({'pulse_us': 1600}, {'hold_seconds': 50}, {'channels': [1, 2]}):
            request = self.center(); request['payload'].update(extra)
            self.assertFalse(self.controller.handle(request)['ok'])
        for operation in ('initialize', 'jog', 'capture'):
            self.assertFalse(self.controller.handle(self.request(operation))['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_second_channel_rejected_while_first_active(self):
        self.controller.handle(self.center(2))
        before = len(self.reg.writes)
        self.assertFalse(self.controller.handle(self.center(3))['ok'])
        self.assertEqual(len(self.reg.writes), before)
        self.assertEqual(self.controller.status()['enabled_mask'], 2)

    def test_duplicate_request_never_rearms_even_after_timeout(self):
        request = self.center(10)
        first = self.controller.handle(request)
        count = len(self.reg.writes)
        self.assertEqual(self.controller.handle(request), first)
        self.assertEqual(len(self.reg.writes), count)
        self.now = 5
        self.controller.tick()
        count = len(self.reg.writes)
        self.controller.handle(request)
        self.assertEqual(len(self.reg.writes), count)
        self.assertFalse(self.controller.status()['armed'])
        changed = copy.deepcopy(request); changed['payload']['channel'] = 9
        with self.assertRaisesRegex(ValueError, 'reused'):
            self.controller.handle(changed)

    def test_heartbeat_at_deadline_turns_off_and_cannot_rearm(self):
        self.controller.handle(self.center())
        self.now = 4.99
        self.controller.tick()
        self.assertTrue(self.controller.status()['armed'])
        self.now = 5.0
        self.controller.handle(self.request('heartbeat'))
        self.assertFalse(self.controller.status()['armed'])
        self.assertEqual(self.controller.status()['enabled_mask'], 0)

    def test_partial_serial_frame_does_not_suspend_deadline(self):
        self.controller.handle(self.center())
        rounds = iter((1, 6, 7))
        def selectable(*args):
            self.now = next(rounds)
            return ([5], [], [])
        with patch('center_console.select.select', side_effect=selectable), \
             patch('center_console.os.read', side_effect=[b'{"unfinished":', b' ', b'']):
            serve(self.controller, 5, lambda x: None)
        self.assertFalse(self.controller.status()['armed'])

    def test_unknown_commit_is_stopped_and_not_retried(self):
        self.reg.apply = False
        ack = self.controller.handle(self.center())
        self.assertFalse(ack['ok'])
        self.assertFalse(self.controller.status()['armed'])
        self.assertFalse(self.controller.status()['pending'])
        self.assertEqual(sum(address == 0x18 for address, _ in self.reg.writes), 1)

    def test_host_rejects_bad_selection_without_serial(self):
        session = CenterSession.__new__(CenterSession)
        for channel, confirmation in ((0, True), (11, True), (True, True), (1, False)):
            with self.assertRaises(ValueError):
                session.center(channel, confirmation)

    def test_host_stops_on_wrong_channel_ack_without_retry(self):
        session = CenterSession.__new__(CenterSession)
        off = {'armed': False, 'enabled_mask': 0, 'pending': False}
        wrong = {'armed': True, 'enabled_mask': 3, 'pending': False, 'faults': 0, 'pulse_us': [1500]*10}
        with patch.object(session, 'status', return_value=off), \
             patch.object(session, '_request', return_value=wrong) as request, \
             patch.object(session, 'stop') as stop:
            with self.assertRaises(RuntimeError):
                session.center(1, True)
        request.assert_called_once_with('center', {'channel': 1, 'unloaded_confirmed': True})
        stop.assert_called_once()


if __name__ == '__main__':
    unittest.main()
