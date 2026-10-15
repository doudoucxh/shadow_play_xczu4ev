import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from attended_center_console import AttendedCenterDevice, AttendedCenterController
from servo_pwm_device import PwmDevice
from test_servo_commissioning import FakeRegisters


class AttendedTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.lock = Path(self.folder.name)/'lock'
        self.lock.write_text('incident retained')
        self.reg = FakeRegisters()
        self.device = AttendedCenterDevice(self.reg, motion_inhibit_paths=[self.lock])
        self.now = 0
        self.controller = AttendedCenterController(self.device, clock=lambda: self.now)

    def request(self, channel=1, **updates):
        payload = dict(channel=channel, observer_confirmed=True,
                       initial_jump_acknowledged=True, sequence=self.reg.read(0x20))
        payload.update(updates)
        return dict(transport_id=uuid.uuid4().hex, operation='center', payload=payload)

    def test_readonly_start_and_fixed_single_channel_deadline(self):
        self.controller.status()
        self.assertEqual(self.reg.writes, [])
        for channel in range(1, 11):
            ack = self.controller.handle(self.request(channel))
            self.assertTrue(ack['ok'], ack)
            self.assertEqual(ack['result']['enabled_mask'], 1 << (channel-1))
            self.assertEqual(ack['result']['pulse_us'][channel-1], 1500)
            self.now += 5.1
            self.controller.tick()
            self.assertFalse(self.device.status()['armed'])
        self.assertEqual(self.lock.read_text(), 'incident retained')

    def test_no_generic_lock_bypass(self):
        with self.assertRaises(ValueError):
            self.device.commit([1500]*10, 1, allow_arm=True)
        with self.assertRaises(RuntimeError):
            PwmDevice(self.reg, motion_inhibit_paths=[self.lock]).commit([1500]*10, 1, True)
        self.assertEqual(self.reg.writes, [])

    def test_confirmations_and_no_arbitrary_targets(self):
        for updates in ({'observer_confirmed':False}, {'initial_jump_acknowledged':False},
                        {'pulse_us':1600}, {'channel':True}, {'sequence':99}):
            ack = self.controller.handle(self.request(**updates))
            self.assertFalse(ack['ok'])
            self.assertIsNone(self.device.permit)
        self.assertFalse(self.device.status()['armed'])
        self.assertFalse(any(a == 0x10 for a, _ in self.reg.writes))

    def test_replay_never_reexecutes_and_live_channel_blocks_second(self):
        req = self.request()
        self.assertTrue(self.controller.handle(req)['ok'])
        count = len(self.reg.writes)
        self.assertTrue(self.controller.handle(req)['ok'])
        self.assertEqual(len(self.reg.writes), count)
        self.assertFalse(self.controller.handle(self.request(2))['ok'])

    def test_lock_change_stops_and_cannot_reenable(self):
        self.assertTrue(self.controller.handle(self.request())['ok'])
        self.lock.write_text('new incident')
        self.controller.tick()
        self.assertFalse(self.device.status()['armed'])
        self.assertFalse(self.controller.handle(self.request())['ok'])

    def test_timeout_has_one_commit_and_off(self):
        self.reg.apply = False
        self.assertFalse(self.controller.handle(self.request())['ok'])
        self.assertEqual(sum(a == 0x18 for a, _ in self.reg.writes), 1)
        self.assertFalse(self.device.status()['armed'])


if __name__ == '__main__':
    unittest.main()
