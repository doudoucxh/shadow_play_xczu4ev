"""Disable-only sequencing and failures; HDL bench verifies pulse completeness."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from servo_pwm_device import PwmDevice
from test_servo_commissioning import FakeRegisters


class FrameStopTests(unittest.TestCase):
    def setUp(self):
        self.reg=FakeRegisters()
        self.reg.values.update({8:63,0x10:1,0x20:351})
        self.reg.values[0x80]=1537
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.lock=Path(self.tmp.name)/'inhibit';self.lock.write_text('incident')
        self.d=PwmDevice(self.reg,motion_inhibit_paths=[self.lock])

    def test_locked_disable_preserves_pulses_and_never_arms(self):
        s=self.d.stop_after_frame()
        self.assertEqual((s['sequence'],s['enabled_mask'],s['armed']),(352,0,False))
        self.assertEqual(s['pulse_us'],[1537]+[1500]*9)
        self.assertEqual([v for a,v in self.reg.writes if a==0x14],[0])
        self.assertFalse(any(a==0x10 for a,v in self.reg.writes))
        self.assertEqual(self.reg.writes[-1],(0x0c,0))
        self.assertEqual(self.lock.read_text(),'incident')
        with self.assertRaises(RuntimeError):self.d.commit([1500]*10,1,True)

    def test_off_state_does_not_commit(self):
        self.reg.values.update({8:0,0x10:0})
        self.d.stop_after_frame()
        self.assertEqual(self.reg.writes,[(0x0c,0)])

    def test_pending_or_faulted_state_immediately_off(self):
        for addr in (0x24,0x0c):
            with self.subTest(addr=addr):
                self.reg.values.update({8:1,0x10:1,0x24:0,0x0c:0})
                self.reg.values[addr]=1;self.reg.writes.clear()
                with self.assertRaises(RuntimeError):self.d.stop_after_frame()
                self.assertEqual(self.reg.writes,[(0x0c,0)])

    def test_unknown_commit_stops_without_retry(self):
        self.reg.apply=False
        with self.assertRaises(TimeoutError):self.d.stop_after_frame()
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)
        self.assertEqual(self.reg.writes[-1],(0x0c,0))
        self.assertFalse(self.d.status()['armed'])

    def test_mismatched_adoption_stops(self):
        original=self.reg.write
        def corrupt(addr,value):
            original(addr,value)
            if addr==0x18:self.reg.values[8]=1
        self.reg.write=corrupt
        with self.assertRaises(RuntimeError):self.d.stop_after_frame()
        self.assertFalse(self.d.status()['armed'])

    def test_sequence_wrap(self):
        self.reg.values[0x20]=0xffffffff
        self.assertEqual(self.d.stop_after_frame()['sequence'],0)


if __name__=='__main__':unittest.main()
