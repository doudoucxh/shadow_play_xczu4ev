"""Bench targets, continuous hold, explicit stop and replay checks; no hardware."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/calibration'))
sys.path.insert(0, str(ROOT/'tools'))
from manual_servo_console import ManualController
from center_console import CenterController
from servo_pwm_device import PwmDevice
from servo_manual_session import ManualSession, angle_to_pulse, pulse_to_angle, jog_pulse
from test_servo_commissioning import FakeRegisters


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.reg = FakeRegisters()
        self.controller = ManualController(PwmDevice(self.reg), clock=lambda: self.now)

    def request(self, operation='move', payload=None):
        return {'transport_id': uuid.uuid4().hex, 'operation': operation,
                'payload': payload if payload is not None else {'channel': 2, 'pulse_us': 1537, 'unloaded_confirmed': True}}

    def test_conversion_endpoints_center_and_roundtrip(self):
        for angle, pulse in ((0, 500), (135, 1500), (270, 2500), (140, 1537), (130, 1463)):
            self.assertEqual(angle_to_pulse(angle), pulse)
        for pulse in range(500, 2501):
            self.assertEqual(angle_to_pulse(pulse_to_angle(pulse)), pulse)

    def test_invalid_angles_never_clamp_or_wrap(self):
        for value in (-.1, 270.1, float('nan'), float('inf'), True, '', 'abc'):
            with self.assertRaises(ValueError): angle_to_pulse(value)
        with self.assertRaises(ValueError): jog_pulse(2500, 1)
        with self.assertRaises(ValueError): jog_pulse(500, -1)
        self.assertEqual(jog_pulse(1500, 5), 1537)

    def test_targets_change_only_selected_channel_with_exact_mask(self):
        for channel in range(1, 11):
            for pulse in (500, 1463, 1537, 2500):
                before = self.controller.status()['pulse_us']
                ack = self.controller.handle(self.request(payload={'channel': channel, 'pulse_us': pulse, 'unloaded_confirmed': True}))
                self.assertTrue(ack['ok'])
                expected = before[:]; expected[channel-1] = pulse
                self.assertEqual(ack['result']['pulse_us'], expected)
                self.assertEqual(ack['result']['enabled_mask'], 1 << (channel-1))
                self.controller.handle(self.request('off', {}))

    def test_bad_payloads_and_missing_unload_confirmation_write_nothing(self):
        for key, values in (('channel', [0, 11, True, 1.0, '2']),
                            ('pulse_us', [499, 2501, True, 1500.0, '1500', float('inf')]),
                            ('unloaded_confirmed', [False, 1, None, 'true'])):
            for value in values:
                req = self.request(); req['payload'][key] = value
                try: ack = self.controller.handle(req)
                except ValueError: continue  # JSON rejects non-finite values before device access.
                self.assertFalse(ack['ok'])
        req = self.request(); req['payload']['hold_seconds'] = 100
        self.assertFalse(self.controller.handle(req)['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_legacy_center_service_cannot_accept_arbitrary_target(self):
        original = CenterController(PwmDevice(self.reg))
        self.assertFalse(original.handle(self.request())['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_move_replay_and_second_channel_cannot_enable_again(self):
        req = self.request()
        ack = self.controller.handle(req)
        writes = len(self.reg.writes)
        self.assertEqual(self.controller.handle(req), ack)
        self.assertEqual(len(self.reg.writes), writes)
        other = self.request(); other['payload']['channel'] = 3
        self.assertFalse(self.controller.handle(other)['ok'])
        self.assertEqual(len(self.reg.writes), writes)
        self.now = 5
        self.controller.handle(self.request('heartbeat', {}))
        self.assertTrue(self.controller.status()['armed'])
        self.controller.handle(self.request('off', {}))
        self.controller.handle(req)
        self.assertFalse(self.controller.status()['armed'])

    def test_hold_has_no_five_second_or_long_session_deadline(self):
        self.assertTrue(self.controller.handle(self.request())['ok'])
        for elapsed in (4.99, 5, 6, 3600, 86400):
            self.now = elapsed
            self.controller.tick()
            state = self.controller.handle(self.request('heartbeat', {}))['result']
            self.assertTrue(state['armed'])
            self.assertEqual(state['enabled_mask'], 2)
            self.assertIsNone(state['center_hold_seconds'])
            self.assertIsNone(state['center_remaining_seconds'])
            self.assertEqual(state['hold_mode'], 'until_stopped')
        self.assertIsNone(self.controller.deadline)
        state = self.controller.handle(self.request('off', {}))['result']
        self.assertFalse(state['armed'])
        self.assertEqual(state['enabled_mask'], 0)

    def test_same_channel_updates_without_rearming_or_disabling(self):
        self.controller.handle(self.request())
        self.reg.writes.clear()
        ack = self.controller.handle(self.request(payload={'channel': 2, 'pulse_us': 1544, 'unloaded_confirmed': True}))
        self.assertTrue(ack['ok'])
        self.assertEqual(ack['result']['pulse_us'][1], 1544)
        self.assertEqual(ack['result']['enabled_mask'], 2)
        self.assertFalse(any(address in (0x0c, 0x10) for address, _ in self.reg.writes))
        ack = self.controller.handle(self.request('center', {'channel': 2, 'unloaded_confirmed': True}))
        self.assertTrue(ack['ok'])
        self.assertEqual(ack['result']['pulse_us'][1], 1500)

    def test_watchdog_fault_rejects_motion_and_heartbeat_cannot_rearm(self):
        self.controller.handle(self.request())
        # Model the existing FPGA watchdog dropping the output and latching a fault.
        self.reg.values.update({0x10: 0, 8: 0, 0x0c: 1})
        self.reg.writes.clear()
        self.assertTrue(self.controller.handle(self.request('heartbeat', {}))['ok'])
        self.assertFalse(self.controller.handle(self.request())['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_watchdog_expiry_between_validation_and_commit_cannot_rearm(self):
        self.controller.handle(self.request())
        original = self.controller.validate_motion_state
        def expire_after_check(state, channel):
            result = original(state, channel)
            self.reg.values.update({0x10: 0, 8: 0, 0x0c: 1})
            return result
        self.reg.writes.clear()
        with patch.object(self.controller, 'validate_motion_state', side_effect=expire_after_check):
            self.assertFalse(self.controller.handle(self.request())['ok'])
        self.assertFalse(any(address == 0x10 for address, _ in self.reg.writes))
        self.assertFalse(self.controller.status()['armed'])

    def test_host_requires_matching_continuous_service_version(self):
        session = ManualSession.__new__(ManualSession)
        state = self.controller.status()
        self.assertTrue(session.valid_service(state))
        for patch_values in ({'service': 'unloaded-manual-v1'}, {'center_hold_seconds': 5},
                             {'hold_mode': 'timed'}, {'same_channel_updates': False}):
            self.assertFalse(session.valid_service(dict(state, **patch_values)))

    def test_host_allows_same_channel_but_rejects_other_channel_before_send(self):
        session = ManualSession.__new__(ManualSession)
        state = self.controller.handle(self.request())['result']
        adopted = dict(state, pulse_us=[1500, 1544] + [1500]*8)
        with patch.object(session, 'status', return_value=state), patch.object(session, '_request', return_value=adopted) as send:
            self.assertEqual(session.move(2, 1544, True), adopted)
            send.reset_mock()
            with self.assertRaises(RuntimeError): session.move(3, 1544, True)
            send.assert_not_called()

    def test_readonly_traffic_does_not_consume_motion_cache(self):
        for operation in ('hello', 'heartbeat', 'status'):
            for _ in range(30):
                self.assertTrue(self.controller.handle(self.request(operation, {}))['ok'])
        self.assertEqual(self.controller.cache, {})
        self.assertEqual(self.reg.writes, [])
        self.controller.cache = {str(i): (None, None) for i in range(20000)}
        self.assertTrue(self.controller.handle(self.request('off', {}))['ok'])
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            self.controller.handle(self.request())

    def test_host_bad_target_never_opens_serial(self):
        session = ManualSession.__new__(ManualSession)
        for channel, pulse, ready in ((0, 1500, True), (1, 2501, True), (1, True, True), (2, 1537, False)):
            with self.assertRaises(ValueError): session.move(channel, pulse, ready)

    def test_host_pulse_mismatch_stops_without_retry(self):
        session = ManualSession.__new__(ManualSession)
        off = {'armed': False, 'enabled_mask': 0, 'pending': False}
        wrong = dict(off, armed=True, enabled_mask=2, faults=0, pulse_us=[1500]*10)
        with patch.object(session, 'status', return_value=off), patch.object(session, '_request', return_value=wrong) as request, patch.object(session, 'stop') as stop:
            with self.assertRaises(RuntimeError): session.move(2, 1537, True)
        request.assert_called_once_with('move', {'channel': 2, 'pulse_us': 1537, 'unloaded_confirmed': True})
        stop.assert_called_once()


if __name__ == '__main__': unittest.main()
