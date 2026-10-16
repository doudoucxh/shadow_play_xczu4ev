import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/calibration'))
sys.path.insert(0, str(ROOT/'tools'))
from mechanism_manual_console import MechanismManualController, MechanismManualDevice
from mechanism_servo_session import MechanismServoSession
from servo_pwm_device import PwmDevice
from test_servo_commissioning import FakeRegisters


class MechanismServoTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.lock = Path(folder.name)/'lock'
        self.lock.write_text('retained incident')
        self.reg = FakeRegisters()
        self.device = MechanismManualDevice(self.reg, motion_inhibit_paths=[self.lock])
        self.controller = MechanismManualController(self.device)

    def request(self, channel=1, pulse=1500, **changes):
        state = self.device.status()
        payload = dict(channel=channel, pulse_us=pulse, observer_confirmed=True,
                       initial_jump_acknowledged=True, sequence=state['sequence'],
                       expected_mask=state['enabled_mask'])
        payload.update(changes)
        return dict(transport_id=uuid.uuid4().hex, operation='move', payload=payload)

    def off(self):
        return self.controller.handle(dict(transport_id=uuid.uuid4().hex, operation='off', payload={}))

    def test_startup_readonly_and_active_owner_not_disarmed(self):
        state = self.controller.status()
        self.assertTrue(state['retaining_other_outputs'])
        self.assertIsNone(state['center_hold_seconds'])
        self.assertEqual(self.reg.writes, [])
        self.reg.values.update({8:1, 0x10:1})
        with self.assertRaises(ValueError):
            MechanismManualController(self.device)
        self.assertEqual(self.reg.writes, [])

    def test_add_axes_one_by_one_and_preserve_all_other_commands(self):
        pulses = [1500]*10
        mask = 0
        for channel in range(1, 11):
            self.reg.writes.clear()
            pulses[channel-1] = 500 + channel*100
            ack = self.controller.handle(self.request(channel, pulses[channel-1]))
            self.assertTrue(ack['ok'], ack)
            mask |= 1 << (channel-1)
            self.assertEqual(ack['result']['enabled_mask'], mask)
            self.assertEqual(ack['result']['pulse_us'], pulses)
            self.assertEqual(sum(a == 0x10 for a, v in self.reg.writes), int(channel == 1))
        self.assertEqual(self.lock.read_text(), 'retained incident')
        self.reg.writes.clear()
        ack = self.controller.handle(self.request(4, 2500))
        pulses[3] = 2500
        self.assertEqual(ack['result']['pulse_us'], pulses)
        self.assertFalse(any(a in (0x0c, 0x10) for a, v in self.reg.writes))
        self.assertTrue(self.off()['ok'])
        self.assertEqual(self.device.status()['enabled_mask'], 0)

    def test_explicit_ack_target_sequence_and_mask_required(self):
        for changes in ({'channel':True}, {'channel':0}, {'channel':11}, {'pulse_us':499},
                        {'pulse_us':2501}, {'pulse_us':1500.0}, {'observer_confirmed':False},
                        {'initial_jump_acknowledged':False}, {'sequence':99}, {'sequence':True},
                        {'expected_mask':1}, {'expected_mask':False}, {'extra':1}):
            self.assertFalse(self.controller.handle(self.request(**changes))['ok'], changes)
            self.assertIsNone(self.device.permit)
        self.assertFalse(any(a in (0x10, 0x18) for a, v in self.reg.writes))

    def test_no_batch_or_choreography_entry_and_generic_driver_stays_locked(self):
        for operation in ('center', 'demo', 'arm', 'initialize', 'batch', 'jog'):
            req = self.request()
            req['operation'] = operation
            self.assertFalse(self.controller.handle(req)['ok'])
        with self.assertRaises(ValueError):
            self.device.commit([1500]*10, 1023, True)
        with self.assertRaises(RuntimeError):
            PwmDevice(self.reg, motion_inhibit_paths=[self.lock]).commit([1500]*10, 1, True)
        self.assertEqual(self.reg.writes, [])

    def test_duplicate_request_does_not_move_again(self):
        request = self.request(3, 1700)
        self.assertTrue(self.controller.handle(request)['ok'])
        writes = len(self.reg.writes)
        self.assertTrue(self.controller.handle(request)['ok'])
        self.assertEqual(len(self.reg.writes), writes)
        request['payload']['pulse_us'] = 1800
        with self.assertRaises(ValueError):
            self.controller.handle(request)

    def test_watchdog_loss_cannot_automatically_rearm(self):
        self.assertTrue(self.controller.handle(self.request())['ok'])
        self.device.off()  # Simulated independent FPGA watchdog expiry.
        self.reg.writes.clear()
        self.assertFalse(self.controller.handle(self.request(2, 1600))['ok'])
        self.assertTrue(self.controller.status()['output_lost'])
        self.assertFalse(any(a in (0x10, 0x18) for a, v in self.reg.writes))
        self.assertTrue(self.off()['ok'])
        self.assertTrue(self.controller.handle(self.request(2, 1600))['ok'])

    def test_lock_change_stops_and_never_modifies_lock(self):
        self.assertTrue(self.controller.handle(self.request())['ok'])
        self.lock.write_text('operator changed stop')
        self.controller.tick()
        self.assertFalse(self.device.status()['armed'])
        self.assertFalse(self.controller.handle(self.request())['ok'])
        self.off()
        self.assertFalse(self.controller.handle(self.request())['ok'])
        self.assertEqual(self.lock.read_text(), 'operator changed stop')

    def test_unknown_commit_stops_without_retry(self):
        self.reg.apply = False
        self.assertFalse(self.controller.handle(self.request())['ok'])
        self.assertFalse(self.device.status()['armed'])
        self.assertIsNone(self.device.permit)
        self.assertEqual(sum(a == 0x18 for a, v in self.reg.writes), 1)

    def test_host_binds_whole_snapshot_and_stops_bad_ack(self):
        session = MechanismServoSession.__new__(MechanismServoSession)
        before = dict(sequence=14, pulse_us=[1500]*10, armed=True, enabled_mask=1,
                      pending=False, faults=0, output_lost=False)
        session.status = Mock(return_value=before)
        expected = dict(before, sequence=15, pulse_us=[1500,1600]+[1500]*8, enabled_mask=3)
        session._request = Mock(return_value=expected)
        session.stop = Mock()
        self.assertEqual(session.move(2, 1600, True), expected)
        operation, payload = session._request.call_args.args
        self.assertEqual(operation, 'move')
        self.assertEqual(payload['sequence'], 14)
        self.assertEqual(payload['expected_mask'], 1)
        for changed in (dict(expected, enabled_mask=2), dict(expected, sequence=16),
                        dict(expected, pulse_us=[1499,1600]+[1500]*8), dict(expected, armed=False),
                        dict(expected, sequence=15.0), None):
            session._request.return_value = changed
            with self.assertRaises(RuntimeError):
                session.move(2, 1600, True)
        self.assertEqual(session.stop.call_count, 6)

    def test_host_validation_and_state_flags(self):
        session = MechanismServoSession.__new__(MechanismServoSession)
        session.status = Mock()
        for channel, pulse, confirmed in ((True,1500,True), (1,499,True), (1,1500,False)):
            with self.assertRaises(ValueError):
                session.move(channel, pulse, confirmed)
        session.status.assert_not_called()
        self.assertTrue(session.valid_service(dict(service=session.service, center_hold_seconds=None,
                                                   hold_mode='until_stopped', retaining_other_outputs=True)))
        self.assertFalse(session.valid_service(dict(service='attended-angle-v1', center_hold_seconds=None,
                                                    hold_mode='until_stopped', retaining_other_outputs=True)))


if __name__ == '__main__':
    unittest.main()
