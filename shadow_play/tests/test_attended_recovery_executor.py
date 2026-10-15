from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from attended_recovery_executor import RecoveryDevice, run
from servo_pwm_device import PwmDevice
from test_servo_commissioning import FakeRegisters


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.locks = [self.root/'lock1', self.root/'lock2']
        for p in self.locks:
            p.write_text('incident')
        self.reg = FakeRegisters()
        self.reg.values.update({8: 1023, 0x10: 1})
        for i in range(10):
            self.reg.values[0x80+4*i] = 1490
        self.now = 0
        self.events = []
        self.plan = dict(operator_authorized=True, observer_ready=True,
                         linkage_clearance_reviewed=True,
                         start=dict(basis='observed_commanded_pose_unchanged',
                                    axes_moved_since_verification=False,
                                    evidence='simulation only', pulses_us=[1490]*10),
                         route=dict(loaded_path_reviewed=True, frame_period_ms=20,
                                    frames_us=[[1490]*10, [1495]*10, [1500]*10]))

    def device(self):
        return RecoveryDevice(self.reg, self.plan, 0, clock=lambda: self.now,
                              cancel_path=self.root/'cancel', motion_inhibit_paths=self.locks)

    def sleep(self, dt):
        self.now += dt

    def execute(self, d, sleep=None, emit=None):
        run(d, emit or self.events.append, clock=lambda: self.now, sleep=sleep or self.sleep)

    def test_fixed_route_finishes_stops_and_preserves_locks(self):
        d = self.device()
        self.execute(d)
        self.assertTrue(self.events[-1]['route_complete'])
        self.assertFalse(d.status()['armed'])
        self.assertEqual(d.status()['pulse_us'], [1500]*10)
        self.assertTrue(all(p.read_text() == 'incident' for p in self.locks))
        self.assertFalse(any(a == 0x10 for a, v in self.reg.writes))
        with self.assertRaises(RuntimeError):
            PwmDevice(self.reg, motion_inhibit_paths=self.locks).commit([1500]*10, 1023, True)
        with self.assertRaises(RuntimeError):
            self.execute(d)

    def test_off_state_never_rearms(self):
        self.reg.values.update({8: 0, 0x10: 0})
        with self.assertRaises(RuntimeError):
            self.execute(self.device())
        self.assertFalse(any(a in (0x10, 0x18) for a, v in self.reg.writes))

    def test_stale_sequence_rejected(self):
        self.reg.values[0x20] = 9
        with self.assertRaises(RuntimeError):
            self.execute(self.device())
        self.assertFalse(any(a == 0x18 for a, v in self.reg.writes))

    def test_cancel_lock_change_stall_and_external_stop(self):
        for action in ('cancel', 'lock', 'stall', 'stop'):
            with self.subTest(action=action):
                self.setUp()
                d = self.device()
                def disturb(dt):
                    self.sleep(dt)
                    if action == 'cancel': (self.root/'cancel').write_text('stop')
                    if action == 'lock': self.locks[0].write_text('changed')
                    if action == 'stall': self.now += .1
                    if action == 'stop': self.reg.values.update({8: 0, 0x10: 0})
                with self.assertRaises(RuntimeError): self.execute(d, sleep=disturb)
                self.assertFalse(d.status()['armed'])
                self.assertFalse(any(a == 0x18 for a, v in self.reg.writes))

    def test_arbitrary_commit_rejected(self):
        with self.assertRaises(RuntimeError): self.device().commit([1500]*10, 1023, True)
        self.assertEqual(self.reg.writes, [])

    def test_log_failure_stops_output(self):
        def bad_log(row):
            if row['event'] == 'frame': raise OSError('disk full')
            self.events.append(row)
        with self.assertRaises(OSError): self.execute(self.device(), emit=bad_log)
        self.assertFalse(self.reg.read(0x10))

    def test_interrupt_stops_output(self):
        def interrupt(dt): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.execute(self.device(), sleep=interrupt)
        self.assertFalse(self.reg.read(0x10))

    def test_timeout_does_not_retry_commit(self):
        self.reg.apply = False
        with self.assertRaises(TimeoutError): self.execute(self.device())
        self.assertEqual(sum(a == 0x18 for a, v in self.reg.writes), 1)
        self.assertFalse(self.reg.read(0x10))


if __name__ == '__main__': unittest.main()
